"""Tests for fixed internal technical qualification tasks."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.records import ArtifactRef, FeatureAxisRef, FinalArtifactRecord, NuisancePlan
from outcome_models.run_store import ConfiguredRunStore
from outcome_models.services.qualification import (
    QualificationRequest,
    QualificationRun,
    QualificationService,
    run_technical_qualification,
)
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class QualificationServiceTests(unittest.TestCase):
    def _artifact(self, kind: str, name: str, shape: tuple[int, ...] = ()) -> ArtifactRef:
        return ArtifactRef("task_final", kind, f"tasks/task_final/{name}", "a" * 64, shape)

    def _fixture(self, root: Path, model: str):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = [model]
            profiles["workflow"]["execution"]["through"] = "formal"
            profiles["study"]["paths"]["output_root"] = str(root / "outputs")

        workflow = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        store = ConfiguredRunStore.create(
            output_root=root / "outputs",
            study_id=config.study.study_id,
            provenance={
                "configuration_hash": config.configuration_hash,
                "input_hashes": {},
                "code_provenance": {},
            },
        )
        store.initialize(
            resolved_workflow={},
            endpoint_catalog=[row.as_dict() for row in catalog],
            execution_plan=plan.as_dict(),
        )
        context = RunContext(store=store, catalog=tuple(catalog), config=config)
        stage = "equivalence_smoke" if model.endswith("voxel") else "candidate_source_smoke"
        task = next(task for task in plan.tasks if task.key.execution_stage == stage)
        return context, task

    def _final(self, endpoint_id: str, family: str) -> FinalArtifactRecord:
        feature_kind = "candidate_flat_indices" if family.endswith("voxel") else "fiber_ids"
        fiber_kwargs = (
            {
                "full_weights": self._artifact(
                    "selected_full_weights",
                    "weights.npy",
                    (32,),
                ),
                "valid_feature_axis": FeatureAxisRef(
                    Path("valid_fiber_ids.npy"),
                    24,
                    "c" * 64,
                    "fiber_ids",
                ),
            }
            if family.endswith("fiber")
            else {}
        )
        return FinalArtifactRecord.create(
            final_model_id="final_selected",
            endpoint_model_id=endpoint_id,
            final_branch="hf_source",
            final_role="realized_final",
            selected_tau=200 if family.endswith("voxel") else 800,
            selected_coverage=5,
            estimator=(
                "peak_efield_partial_spearman"
                if family.endswith("fiber")
                else "partial_spearman"
            ),
            scale_direction="lower",
            subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
            nuisance=NuisancePlan.for_branch("hf_source", None),
            manifest=self._artifact("final_manifest", "manifest.json"),
            exposure=self._artifact("exposure", "exposure.npy", (12, 32)),
            scores=self._artifact("scores", "scores.csv", (12,)),
            feature_axis=FeatureAxisRef(Path("features.npy"), 32, "b" * 64, feature_kind),
            **fiber_kwargs,
        )

    def test_service_writes_only_task_local_qualification_status_without_classification_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root, "hf-voxel")
            final = self._final(task.endpoint.identifier, task.endpoint.model_family)

            def runner(request):
                self.assertEqual(request.operation, "equivalence_smoke")
                return QualificationRun(True, "optimized_reference_equivalent", {"max_abs_difference": 0.0})

            result = QualificationService(
                final_loader=lambda _task, _context: final,
                runner=runner,
            ).execute(task, context)

            status_path = (
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
                / "qualification_status.json"
            )
            payload = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(
            set(task.expected_artifact_kinds),
            {"task_manifest", "qualification_status"},
        )
        self.assertEqual({artifact.kind for artifact in result.artifacts}, {"qualification_status"})
        self.assertEqual(result.artifacts[0].path, status_path)
        self.assertTrue(payload["qualification_passed"])
        forbidden = {"source_status", "prediction_status", "final_branch", "final_role", "final_status"}
        self.assertTrue(forbidden.isdisjoint(result.facts))
        self.assertTrue(forbidden.isdisjoint(payload))

    def test_failed_qualification_writes_status_and_blocks_the_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root, "hf-voxel")
            final = self._final(task.endpoint.identifier, task.endpoint.model_family)
            result = QualificationService(
                final_loader=lambda _task, _context: final,
                runner=lambda _request: QualificationRun(False, "optimized_reference_mismatch", {"max_abs_difference": 1.0}),
            ).execute(task, context)
            payload = json.loads(result.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, TaskStatus.EXECUTION_FAILURE)
        self.assertFalse(payload["qualification_passed"])
        self.assertEqual(payload["detail"], "optimized_reference_mismatch")

    def test_actual_equivalence_kernel_is_deterministic_and_matches_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root, "hf-voxel")
            final = self._final(task.endpoint.identifier, task.endpoint.model_family)
            request = QualificationRequest.from_context(task, context, final)
            rng = np.random.default_rng(7)
            exposure = rng.integers(0, 7, size=(12, 32)).astype(np.float64)
            exposure_path = root / "exposure.npy"
            np.save(exposure_path, exposure)
            scores_path = root / "scores.csv"
            with scores_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("subject_id", "Y_post", "Y_base"))
                writer.writeheader()
                for index in range(12):
                    writer.writerow(
                        {
                            "subject_id": f"sub-{index + 1:02d}",
                            "Y_post": float((index * 5) % 11),
                            "Y_base": float((index * 3) % 7),
                        }
                    )
            target = SimpleNamespace(
                x_path=exposure_path,
                scores_csv=scores_path,
                outcome_column="Y_post",
                nuisance_columns=("Y_base",),
                delta_hf_full_path=None,
                branch_dir=request.output_root,
            )
            first = run_technical_qualification(request, target_builder=lambda _request: target)
            second = run_technical_qualification(request, target_builder=lambda _request: target)

        self.assertTrue(first.passed)
        self.assertEqual(first, second)
        self.assertEqual(first.metrics["reference_kernel"], "partial_spearman_loop_reference")
        self.assertGreater(first.metrics["finite_comparison_count"], 0)
        self.assertLessEqual(first.metrics["max_abs_difference"], 1e-12)

    def test_actual_equivalence_reads_direct_voxel_subjects_csv_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root, "hf-voxel")
            final = self._final(task.endpoint.identifier, task.endpoint.model_family)
            request = QualificationRequest.from_context(task, context, final)
            rng = np.random.default_rng(11)
            exposure_path = root / "exposure.npy"
            np.save(exposure_path, rng.integers(0, 9, size=(12, 24)).astype(float))
            subjects_path = root / "subjects.csv"
            with subjects_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("subject_id", "Y_post", "Y_base"),
                )
                writer.writeheader()
                for index in range(12):
                    writer.writerow(
                        {
                            "subject_id": f"sub-{index + 1:02d}",
                            "Y_post": float((index * 7) % 13),
                            "Y_base": float((index * 5) % 9),
                        }
                    )
            target = SimpleNamespace(
                x_path=exposure_path,
                subjects_csv=subjects_path,
                outcome_column="Y_post",
                nuisance_columns=("Y_base",),
                delta_hf_full_path=None,
                branch_dir=request.output_root,
            )

            result = run_technical_qualification(
                request,
                target_builder=lambda _request: target,
            )

        self.assertTrue(result.passed)
        self.assertGreater(result.metrics["finite_comparison_count"], 0)

    def test_candidate_source_smoke_uses_fixed_internal_counts_and_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root, "hf-fiber")
            final = self._final(task.endpoint.identifier, task.endpoint.model_family)
            request = QualificationRequest.from_context(task, context, final)
            calls = []
            target = SimpleNamespace(
                x_path=root / "exposure.npy",
                scores_csv=root / "scores.csv",
                outcome_column="Y_post",
                nuisance_columns=("Y_base",),
                delta_hf_full_path=None,
                branch_dir=request.output_root,
            )
            np.save(target.x_path, np.arange(12 * 32, dtype=float).reshape(12, 32))
            with target.scores_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("subject_id", "Y_post", "Y_base"))
                writer.writeheader()
                for index in range(12):
                    writer.writerow(
                        {"subject_id": f"sub-{index + 1:02d}", "Y_post": index, "Y_base": index % 4}
                    )

            def permutation(_target, *, n_permutations, seed, tier):
                calls.append(("permutation", n_permutations, seed, tier))
                return {
                    "permutation_status": "complete",
                    "p_plus_one_two_sided": 0.5,
                    "null_finite_count": n_permutations,
                    "fold_n_candidate_fibers_min": 3,
                }

            def bootstrap(_target, *, n_bootstraps, seed):
                calls.append(("bootstrap", n_bootstraps, seed))
                return {"bootstrap_status": "complete", "finite_bootstrap_count": n_bootstraps}

            result = run_technical_qualification(
                request,
                target_builder=lambda _request: target,
                fiber_permutation_runner=permutation,
                fiber_bootstrap_runner=bootstrap,
            )

        self.assertTrue(result.passed)
        self.assertEqual(
            calls,
            [("permutation", 1000, 42, "smoke"), ("bootstrap", 1000, 42)],
        )
        self.assertEqual(result.metrics["smoke_permutations"], 1000)
        self.assertEqual(result.metrics["smoke_bootstraps"], 1000)


if __name__ == "__main__":
    unittest.main()
