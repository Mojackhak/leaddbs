"""Tests for final-linked sensitivity and reporting contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskArtifact, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.records import ArtifactRef, DeltaHFBundle, FeatureAxisRef, FinalArtifactRecord, NuisancePlan, RecordError
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.reporting import FinalLinkedArtifact, ReportingRequest
from outcome_models.services.sensitivity import (
    SensitivityRequest,
    SensitivityRuntimeInputs,
    SensitivityService,
    SensitivityServiceOutput,
)
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class SensitivityReportingContractTests(unittest.TestCase):
    def _artifact(self, kind, name, shape=()):
        return ArtifactRef("task_final", kind, f"tasks/task_final/{name}", "a" * 64, shape)

    def _delta(self):
        return DeltaHFBundle(
            input_status="valid",
            support_status="limited",
            selected_hf_tau=200,
            selected_hf_coverage=5,
            full_scores=self._artifact("delta_hf_full_scores", "full.npy", (12,)),
            fold_scores=self._artifact("delta_hf_fold_scores", "folds.npy", (12, 12)),
            support_rows=self._artifact("delta_hf_support_rows", "support.csv", (12,)),
        )

    def _final(self, endpoint_id, branch, nuisance):
        return FinalArtifactRecord.create(
            final_model_id="final_selected",
            endpoint_model_id=endpoint_id,
            final_branch=branch,
            final_role="primary",
            selected_tau=250,
            selected_coverage=6,
            estimator="partial_spearman",
            scale_direction="lower",
            subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
            nuisance=nuisance,
            manifest=self._artifact("final_manifest", "manifest.json"),
            exposure=self._artifact("exposure", "exposure.npy", (12, 20)),
            scores=self._artifact("scores", "scores.csv", (12,)),
            feature_axis=FeatureAxisRef(Path("features.npy"), 20, "b" * 64, "candidate_flat_indices"),
        )

    def _jitter_inputs(self):
        return {
            "component_exposures": (
                self._artifact("hf_component_exposure", "hf_component.npy", (12, 20)),
                self._artifact("ulf_component_exposure", "ulf_component.npy", (12, 20)),
            ),
            "jitter_input_manifest": self._artifact(
                "jitter_input_manifest", "jitter_inputs.json"
            ),
            "y_base": self._artifact("y_base", "y_base.npy", (12,)),
            "hf_overlap_tau": 200.0,
        }

    def _fixture(self, root: Path):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = ["ulf-voxel"]
            profiles["workflow"]["execution"]["through"] = "report"
            profiles["study"]["paths"]["output_root"] = str(root / "outputs")

        workflow = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        store = ConfiguredRunStore.create(
            output_root=root / "outputs",
            study_id=config.study.study_id,
            provenance={"configuration_hash": config.configuration_hash, "input_hashes": {}, "code_provenance": {}},
        )
        store.initialize(resolved_workflow={}, endpoint_catalog=[row.as_dict() for row in catalog], execution_plan=plan.as_dict())
        context = RunContext(store=store, catalog=tuple(catalog), config=config)
        return context, plan

    def test_adjusted_ulf_jitter_rebuilds_geometry_delta_support_and_nuisance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "spatial_jitter"
            )
            delta = self._delta()
            final = self._final(task.endpoint.identifier, "delta_hf_adjusted", NuisancePlan.for_branch("delta_hf_adjusted", delta))
            matched_hf_final = self._final(
                "matched-hf-endpoint",
                "hf_source",
                NuisancePlan.for_branch("hf_source", None),
            )
            request = SensitivityRequest.from_context(
                task,
                context,
                final,
                delta_hf=delta,
                matched_hf_final=matched_hf_final,
                **self._jitter_inputs(),
            )

        self.assertTrue(request.rebuild_geometry)
        self.assertTrue(request.rebuild_delta_hf)
        self.assertTrue(request.rebuild_support_qc)
        self.assertTrue(request.rebuild_nuisance)
        self.assertEqual(request.final.selected_tau, 250)
        self.assertEqual(request.selected_tau_multipliers, (0.9, 1.1))
        self.assertEqual(request.jitter_resamples, 1000)
        self.assertEqual(request.seed, 42)
        self.assertEqual(
            request.enabled_ulf_analyses,
            ("nonfinal_branch", "gain", "total_exposure", "support", "collinearity"),
        )
        self.assertEqual(request.hf_overlap_tau, 200.0)
        self.assertIs(request.matched_hf_final, matched_hf_final)

    def test_no_delta_jitter_never_injects_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "spatial_jitter"
            )
            final = self._final(task.endpoint.identifier, "no_delta_hf", NuisancePlan.for_branch("no_delta_hf", None))
            request = SensitivityRequest.from_context(
                task,
                context,
                final,
                delta_hf=None,
                **self._jitter_inputs(),
            )

        self.assertTrue(request.rebuild_geometry)
        self.assertFalse(request.rebuild_delta_hf)
        self.assertFalse(request.rebuild_support_qc)

    def test_ulf_jitter_rejects_missing_explicit_rebuild_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel"
                and task.key.execution_stage == "spatial_jitter"
            )
            final = self._final(
                task.endpoint.identifier,
                "no_delta_hf",
                NuisancePlan.for_branch("no_delta_hf", None),
            )
            with self.assertRaisesRegex(RecordError, "component exposure"):
                SensitivityRequest.from_context(task, context, final, delta_hf=None)

    def test_adjusted_sensitivity_rejects_wrong_delta_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "spatial_jitter"
            )
            delta = self._delta()
            final = self._final(task.endpoint.identifier, "delta_hf_adjusted", NuisancePlan.for_branch("delta_hf_adjusted", delta))
            wrong = DeltaHFBundle(
                input_status="valid",
                support_status="adequate",
                selected_hf_tau=220,
                selected_hf_coverage=5,
                full_scores=delta.full_scores,
                fold_scores=delta.fold_scores,
                support_rows=delta.support_rows,
            )
            with self.assertRaises(RecordError):
                SensitivityRequest.from_context(
                    task,
                    context,
                    final,
                    delta_hf=wrong,
                    matched_hf_final=self._final(
                        "matched-hf-endpoint",
                        "hf_source",
                        NuisancePlan.for_branch("hf_source", None),
                    ),
                    **self._jitter_inputs(),
                )

    def test_reporting_rejects_artifact_from_another_final_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "endpoint_report"
            )
            final = self._final(task.endpoint.identifier, "no_delta_hf", NuisancePlan.for_branch("no_delta_hf", None))
            matching = FinalLinkedArtifact("final_selected", final.record_hash, self._artifact("formal", "formal.csv"))
            request = ReportingRequest.from_context(task, context, final, artifacts=(matching,))
            self.assertEqual(request.final.final_model_id, "final_selected")
            wrong = FinalLinkedArtifact("different_final", final.record_hash, self._artifact("oss", "oss.csv"))
            with self.assertRaises(RecordError):
                ReportingRequest.from_context(task, context, final, artifacts=(wrong,))

    def test_sensitivity_service_indexes_the_generated_jitter_input_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel"
                and task.key.execution_stage == "spatial_jitter"
            )
            final = self._final(
                task.endpoint.identifier,
                "no_delta_hf",
                NuisancePlan.for_branch("no_delta_hf", None),
            )
            manifest_path = context.store.run_root / "jitter_input_manifest.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            manifest = ArtifactRef(
                task_id=task.task_id,
                kind="jitter_input_manifest",
                relative_path=manifest_path.relative_to(context.store.run_root).as_posix(),
                sha256=sha256_file(manifest_path),
            )
            output_path = context.store.run_root / "jitter_results.json"

            def runner(_request):
                output_path.write_text("{}\n", encoding="utf-8")
                return SensitivityServiceOutput(
                    (TaskArtifact("jitter_results", output_path),)
                )

            raw_inputs = self._jitter_inputs()
            service = SensitivityService(
                runner=runner,
                final_loader=lambda _task, _context: final,
                inputs_loader=lambda _task, _context, _final: SensitivityRuntimeInputs(
                    component_exposures=raw_inputs["component_exposures"],
                    jitter_input_manifest=manifest,
                    y_base=raw_inputs["y_base"],
                    hf_overlap_tau=raw_inputs["hf_overlap_tau"],
                ),
            )

            result = service.execute(task, context)

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(
            [artifact.kind for artifact in result.artifacts],
            ["jitter_results", "jitter_input_manifest"],
        )


if __name__ == "__main__":
    unittest.main()
