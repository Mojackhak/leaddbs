"""Tests for explicit configured A/B observed-service requests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.run_store import ConfiguredRunStore
from outcome_models.services.observed import (
    FeatureAxisRef,
    HFDirectVoxelRequest,
    HFNormativeFiberRequest,
    HFObservedService,
    ObservedServiceOutput,
    direct_source_branch_name,
    fiber_primary_branch_name,
)
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class CaptureRunner:
    def __init__(self, output: ObservedServiceOutput) -> None:
        self.output = output
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.output


class ObservedServiceTests(unittest.TestCase):
    def _fixture(self, root: Path):
        def mutate(profiles):
            profiles["workflow"]["execution"]["through"] = "observed"
            profiles["study"]["paths"]["output_root"] = str(root / "outputs")

        workflow_path = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow_path, WorkflowOverrides())
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
        return config, catalog, plan, RunContext(store=store, catalog=tuple(catalog), config=config)

    def test_hf_direct_request_has_no_scale_or_path_defaults(self) -> None:
        output = ObservedServiceOutput(
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            adjacent_support=3,
            subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
            feature_axis=FeatureAxisRef(Path("candidate_flat_indices.npy"), 3, "a" * 64, "candidate_flat_indices"),
        )
        direct_runner = CaptureRunner(output)
        with tempfile.TemporaryDirectory() as tmp:
            config, catalog, plan, context = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "hf_voxel" and item.key.execution_stage == "observed_source_resolver"
            )
            service = HFObservedService(direct_runner=direct_runner)
            result = service.execute(task, context)
            request = direct_runner.requests[0]

        self.assertIsInstance(request, HFDirectVoxelRequest)
        self.assertEqual(request.endpoint.scale_label, "Scale One")
        self.assertEqual((request.endpoint.outcome_protocol, request.endpoint.outcome_phase), ("STN", "3m"))
        self.assertEqual(request.clinical_table, config.study.paths.clinical_table)
        self.assertEqual(request.stimulation_table, config.study.paths.stimulation_table)
        self.assertEqual(request.brainmask, Path(config.study.space["brainmask"]))
        self.assertEqual(request.tau_grid, tuple(config.model.direct_voxel["tau_grid_v_per_m"]))
        self.assertEqual(request.coverage_grid, tuple(config.model.direct_voxel["coverage_grid"]))
        self.assertEqual(request.candidate_threshold, min(request.tau_grid))
        self.assertEqual(request.model_root, context.store.run_root / "models" / task.endpoint.identifier)
        self.assertEqual(request.output_root, request.model_root / "tasks" / task.task_id)
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.facts["source_accepted"])

    def test_hf_fiber_request_locks_connectome_and_feature_order(self) -> None:
        output = ObservedServiceOutput(
            source_status="scan_fallback_accepted",
            prediction_status="error_nonpredictive",
            threshold_source="scan_fallback",
            selected_tau=1000,
            selected_coverage=6,
            adjacent_support=4,
            subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
            feature_axis=FeatureAxisRef(Path("fiber_ids.npy"), 3, "b" * 64, "data.mat:idx"),
        )
        fiber_primary = CaptureRunner(ObservedServiceOutput.empty())
        fiber_resolver = CaptureRunner(output)
        with tempfile.TemporaryDirectory() as tmp:
            config, _, plan, context = self._fixture(Path(tmp))
            primary_task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "hf_fiber"
                and item.endpoint.connectome == "dtor"
                and item.key.execution_stage == "observed_primary"
            )
            resolver_task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "hf_fiber"
                and item.endpoint.connectome == "dtor"
                and item.key.execution_stage == "observed_source_resolver"
            )
            service = HFObservedService(
                fiber_primary_runner=fiber_primary,
                fiber_resolver_runner=fiber_resolver,
            )
            primary_result = service.execute(primary_task, context)
            resolver_result = service.execute(resolver_task, context)
            request = fiber_resolver.requests[0]

        self.assertEqual(primary_result.status, TaskStatus.COMPLETED)
        self.assertEqual(
            resolver_result.facts["feature_axis"],
            {
                "ids_path": "fiber_ids.npy",
                "count": 3,
                "sha256": "b" * 64,
                "identity_source": "data.mat:idx",
            },
        )
        self.assertIsInstance(request, HFNormativeFiberRequest)
        self.assertEqual(request.connectome.connectome_id, "dtor")
        self.assertEqual(request.connectome.path, config.study.connectomes["dtor"].path)
        self.assertEqual(request.tau_grid, tuple(config.model.normative_fiber["tau_grid_v_per_m"]))
        self.assertEqual(request.primary_tau, 800)
        self.assertEqual(request.primary_coverage, 5)

    def test_branch_names_reflect_requested_tau_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, _, plan, context = self._fixture(Path(tmp))
            endpoint = context.catalog[0]
            direct_plan_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == endpoint.endpoint_model_id
                and task.key.execution_stage == "observed_source_resolver"
            )
            direct = HFDirectVoxelRequest.from_context(endpoint, direct_plan_task, context)
            fiber_endpoint = next(row for row in context.catalog if row.key.model_family == "hf_fiber")
            fiber_plan_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == fiber_endpoint.endpoint_model_id
                and task.key.execution_stage == "observed_primary"
            )
            fiber = HFNormativeFiberRequest.from_context(fiber_endpoint, fiber_plan_task, context)

        self.assertEqual(direct_source_branch_name(direct, 200, 5), "tau200_cov5")
        self.assertEqual(direct_source_branch_name(direct, 350, 8), "tau350_cov8")
        self.assertEqual(fiber_primary_branch_name(fiber), "peak_efield_tau800_cov5_primary")
        self.assertEqual(
            fiber_primary_branch_name(replace(fiber, primary_tau=1500, primary_coverage=7)),
            "peak_efield_tau1500_cov7_primary",
        )


if __name__ == "__main__":
    unittest.main()
