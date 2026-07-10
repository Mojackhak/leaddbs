"""Tests for final-record-driven formal service requests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskArtifact, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.run_store import ConfiguredRunStore
from outcome_models.services.formal import FormalRequest, FormalService, FormalServiceOutput
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class CaptureFormalRunner:
    def __init__(self, artifact: Path) -> None:
        self.requests = []
        self.artifact = artifact

    def __call__(self, request):
        self.requests.append(request)
        self.artifact.parent.mkdir(parents=True, exist_ok=True)
        self.artifact.write_text("formal result\n", encoding="utf-8")
        return FormalServiceOutput((TaskArtifact("permutation_results", self.artifact),))


class FormalServiceTests(unittest.TestCase):
    def _artifact(self, kind, name, shape=()):
        return ArtifactRef("task_final", kind, f"tasks/task_final/{name}", "a" * 64, shape)

    def _fixture(self, root: Path):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = ["ulf-voxel"]
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
            provenance={"configuration_hash": config.configuration_hash, "input_hashes": {}, "code_provenance": {}},
        )
        store.initialize(resolved_workflow={}, endpoint_catalog=[row.as_dict() for row in catalog], execution_plan=plan.as_dict())
        context = RunContext(store=store, catalog=tuple(catalog), config=config)
        task = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "formal_permutation"
        )
        return context, task

    def _delta(self):
        return DeltaHFBundle(
            input_status="valid",
            support_status="adequate",
            selected_hf_tau=200,
            selected_hf_coverage=5,
            full_scores=self._artifact("delta_hf_full_scores", "full.npy", (12,)),
            fold_scores=self._artifact("delta_hf_fold_scores", "folds.npy", (12, 12)),
            support_rows=self._artifact("delta_hf_support_rows", "support.csv", (12,)),
        )

    def _final(self, endpoint_id, branch, nuisance, tau=250, coverage=6):
        return FinalArtifactRecord.create(
            final_model_id="final_selected",
            endpoint_model_id=endpoint_id,
            final_branch=branch,
            final_role="primary",
            selected_tau=tau,
            selected_coverage=coverage,
            estimator="partial_spearman",
            nuisance=nuisance,
            manifest=self._artifact("final_manifest", "manifest.json"),
            exposure=self._artifact("exposure", "exposure.npy", (12, 20)),
            scores=self._artifact("scores", "scores.csv", (12,)),
            feature_axis=FeatureAxisRef(Path("features.npy"), 20, "b" * 64, "candidate_flat_indices"),
        )

    def test_adjusted_formal_request_uses_final_branch_delta_nuisance_and_selected_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task = self._fixture(Path(tmp))
            final = self._final(task.endpoint.identifier, "delta_hf_adjusted", NuisancePlan.for_branch("delta_hf_adjusted", self._delta()))
            request = FormalRequest.from_context(task, context, final)

        self.assertEqual(request.final.final_branch, "delta_hf_adjusted")
        self.assertEqual(request.final.nuisance.columns, ("Y_HF_ref", "DeltaHFScore"))
        self.assertEqual((request.final.selected_tau, request.final.selected_coverage), (250, 6))
        self.assertEqual(request.permutations, 10000)
        self.assertEqual(request.seed, 42)
        self.assertEqual(request.output_root, context.store.run_root / "models" / task.endpoint.identifier / "tasks" / task.task_id)

    def test_no_delta_formal_request_never_injects_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task = self._fixture(Path(tmp))
            final = self._final(task.endpoint.identifier, "no_delta_hf", NuisancePlan.for_branch("no_delta_hf", None))
            request = FormalRequest.from_context(task, context, final)

        self.assertEqual(request.final.nuisance.columns, ("Y_HF_ref",))
        self.assertIsNone(request.final.nuisance.delta_hf_record_hash)

    def test_formal_request_rejects_final_from_another_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task = self._fixture(Path(tmp))
            final = self._final("different_endpoint", "no_delta_hf", NuisancePlan.for_branch("no_delta_hf", None))
            with self.assertRaises(RecordError):
                FormalRequest.from_context(task, context, final)

    def test_formal_service_reports_inference_without_classification_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context, task = self._fixture(root)
            final = self._final(task.endpoint.identifier, "no_delta_hf", NuisancePlan.for_branch("no_delta_hf", None))
            runner = CaptureFormalRunner(root / "outputs" / "formal.csv")
            result = FormalService(runner=runner, final_loader=lambda _task, _context: final).execute(task, context)

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.facts["formal_complete"])
        self.assertNotIn("source_status", result.facts)
        self.assertNotIn("prediction_status", result.facts)
        self.assertNotIn("final_branch", result.facts)


if __name__ == "__main__":
    unittest.main()
