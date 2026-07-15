"""Tests for immutable HF-derived ULF branch requests."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext
from outcome_models.planner import compile_execution_plan
from outcome_models.records import ArtifactRef, DeltaHFBundle, FeatureAxisRef, HFSourceRecord, RecordError
from outcome_models.run_store import ConfiguredRunStore
from outcome_models.services.ulf_observed import ULFObservedRequest, validate_hf_source_for_ulf
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class ULFServiceContractTests(unittest.TestCase):
    def _artifact(self, kind: str, name: str, shape=()) -> ArtifactRef:
        return ArtifactRef("task_hf", kind, f"tasks/task_hf/{name}", "a" * 64, shape)

    def _source(self, *, accepted=True, model_family="hf_voxel") -> HFSourceRecord:
        axis = FeatureAxisRef(
            Path("candidate_ids.npy"),
            3,
            "b" * 64,
            "candidate_flat_indices" if model_family == "hf_voxel" else "data.mat:idx",
        )
        return HFSourceRecord.create(
            resolver_task_id="task_hf_resolver",
            endpoint_model_id="endpoint_hf",
            input_status="valid" if accepted else "unavailable",
            source_status="scan_fallback_accepted" if accepted else "absent_no_stable_grid",
            prediction_status="error_predictive" if accepted else "not_applicable",
            threshold_source="scan_fallback" if accepted else "none",
            selected_tau=250 if accepted else None,
            selected_coverage=6 if accepted else None,
            subject_order=("sub-01", "sub-02"),
            feature_axis=axis if accepted else None,
            artifacts=(self._artifact("source_manifest", "source.json"),) if accepted else (),
        )

    def _delta(self, support_status="adequate") -> DeltaHFBundle:
        valid = support_status in {"adequate", "limited"}
        return DeltaHFBundle(
            input_status="valid" if valid else "invalid",
            support_status=support_status,
            selected_hf_tau=250,
            selected_hf_coverage=6,
            full_scores=self._artifact("delta_hf_full_scores", "full.npy", (2,)) if valid else None,
            fold_scores=self._artifact("delta_hf_fold_scores", "folds.npy", (2, 2)) if valid else None,
            support_rows=self._artifact("delta_hf_support_rows", "support.csv", (2,)),
            failure_stage="" if valid else "support_qc",
            failure_detail="" if valid else "extreme out of support",
        )

    def _context(self, root: Path):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = ["ulf-voxel"]
            profiles["workflow"]["execution"]["through"] = "observed"
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
        endpoint = next(row for row in catalog if row.key.model_family == "ulf_voxel")
        tasks = {
            (task.key.execution_stage, task.key.branch): task
            for task in plan.tasks
            if task.endpoint.identifier == endpoint.endpoint_model_id
        }
        return context, endpoint, tasks

    def test_selected_hf_cell_drives_overlap_delta_and_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, endpoint, tasks = self._context(Path(tmp))
            source = self._source()
            delta = self._delta("limited")
            request = ULFObservedRequest.from_context(
                endpoint,
                tasks[("observed_branch_resolver", "delta_hf_adjusted")],
                context,
                hf_source=source,
                delta_hf=delta,
            )

        self.assertEqual(request.hf_overlap_tau, 250)
        self.assertEqual(request.hf_overlap_coverage, 6)
        self.assertEqual(request.delta_hf.selected_hf_tau, request.hf_overlap_tau)
        self.assertEqual(request.delta_hf.selected_hf_coverage, request.hf_overlap_coverage)
        self.assertEqual(request.nuisance.columns, ("Y_HF_ref", "DeltaHFScore"))
        self.assertEqual(request.delta_hf.support_status, "limited")

    def test_absent_hf_uses_infinite_overlap_and_allows_only_no_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, endpoint, tasks = self._context(Path(tmp))
            source = self._source(accepted=False)
            no_delta = ULFObservedRequest.from_context(
                endpoint,
                tasks[("observed_branch_resolver", "no_delta_hf")],
                context,
                hf_source=source,
                delta_hf=None,
            )
            with self.assertRaises(RecordError):
                ULFObservedRequest.from_context(
                    endpoint,
                    tasks[("observed_branch_resolver", "delta_hf_adjusted")],
                    context,
                    hf_source=source,
                    delta_hf=None,
                )

        self.assertTrue(math.isinf(no_delta.hf_overlap_tau))
        self.assertEqual(no_delta.nuisance.columns, ("Y_HF_ref",))

    def test_invalid_delta_fails_adjusted_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, endpoint, tasks = self._context(Path(tmp))
            source = self._source()
            invalid = self._delta("invalid_extreme_out_of_support")
            no_delta = ULFObservedRequest.from_context(
                endpoint,
                tasks[("observed_branch_resolver", "no_delta_hf")],
                context,
                hf_source=source,
                delta_hf=invalid,
            )
            with self.assertRaises(RecordError):
                ULFObservedRequest.from_context(
                    endpoint,
                    tasks[("observed_branch_resolver", "delta_hf_adjusted")],
                    context,
                    hf_source=source,
                    delta_hf=invalid,
                )

        self.assertEqual(no_delta.branch, "no_delta_hf")

    def test_hf_dependency_rejects_subject_or_feature_axis_mismatch(self) -> None:
        source = self._source()
        validate_hf_source_for_ulf(source, expected_subject_order=("sub-01", "sub-02"), expected_feature_sha="b" * 64)
        with self.assertRaises(RecordError):
            validate_hf_source_for_ulf(source, expected_subject_order=("sub-02", "sub-01"), expected_feature_sha="b" * 64)
        with self.assertRaises(RecordError):
            validate_hf_source_for_ulf(source, expected_subject_order=("sub-01", "sub-02"), expected_feature_sha="c" * 64)


if __name__ == "__main__":
    unittest.main()
