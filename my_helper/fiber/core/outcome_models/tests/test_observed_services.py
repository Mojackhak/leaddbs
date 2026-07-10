"""Tests for explicit configured A/B observed-service requests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import (
    RunContext,
    ServiceRegistry,
    TaskArtifact,
    TaskStatus,
    execute_plan,
)
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
        with tempfile.TemporaryDirectory() as tmp:
            config, catalog, plan, context = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "hf_voxel" and item.key.execution_stage == "observed_source_resolver"
            )
            task_root = context.store.run_root / "models" / task.endpoint.identifier / "tasks" / task.task_id
            task_root.mkdir(parents=True, exist_ok=True)
            axis_path = task_root / "candidate_flat_indices.npy"
            exposure = task_root / "exposure.npy"
            np.save(axis_path, np.arange(3, dtype=np.int64))
            np.save(exposure, np.ones((12, 3), dtype=np.float32))
            artifacts = []
            for kind, name in (
                ("source_status", "source.json"),
                ("selected_source", "selected.json"),
                ("selected_manifest", "manifest.json"),
                ("selected_scores", "scores.csv"),
            ):
                path = task_root / name
                path.write_text("{}\n", encoding="utf-8")
                artifacts.append(TaskArtifact(kind, path))
            artifacts.append(TaskArtifact("exposure_matrix", exposure))
            output = ObservedServiceOutput(
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=200,
                selected_coverage=5,
                adjacent_support=3,
                subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
                feature_axis=FeatureAxisRef(axis_path, 3, "a" * 64, "candidate_flat_indices"),
                artifacts=tuple(artifacts),
            )
            direct_runner = CaptureRunner(output)
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

    def test_hf_direct_observed_rounds_satisfy_executor_artifact_contract(self) -> None:
        def sidecar_runner(request):
            request.output_root.mkdir(parents=True, exist_ok=True)
            sidecar_index = request.output_root / "sidecar_index.json"
            qc = request.output_root / "qc.json"
            sidecar_index.write_text("{}\n", encoding="utf-8")
            qc.write_text("{}\n", encoding="utf-8")
            return (TaskArtifact("sidecar_index", sidecar_index), TaskArtifact("qc", qc))

        def resolver_runner(request):
            request.output_root.mkdir(parents=True, exist_ok=True)
            source_status = request.output_root / "source_status.json"
            selected_source = request.output_root / "selected_source.json"
            source_status.write_text("{}\n", encoding="utf-8")
            selected_source.write_text("{}\n", encoding="utf-8")
            selected_manifest = request.output_root / "selected_manifest.json"
            selected_scores = request.output_root / "selected_scores.csv"
            exposure = request.output_root / "exposure.npy"
            axis = request.output_root / "candidate_flat_indices.npy"
            selected_manifest.write_text("{}\n", encoding="utf-8")
            selected_scores.write_text("{}\n", encoding="utf-8")
            np.save(exposure, np.ones((12, 3), dtype=np.float32))
            np.save(axis, np.arange(3, dtype=np.int64))
            return ObservedServiceOutput(
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=200,
                selected_coverage=5,
                adjacent_support=3,
                subject_order=request.endpoint.subject_ids,
                feature_axis=FeatureAxisRef(
                    axis,
                    3,
                    "a" * 64,
                    "candidate_flat_indices",
                ),
                artifacts=(
                    TaskArtifact("source_status", source_status),
                    TaskArtifact("selected_source", selected_source),
                    TaskArtifact("selected_manifest", selected_manifest),
                    TaskArtifact("selected_scores", selected_scores),
                    TaskArtifact("exposure_matrix", exposure),
                ),
            )

        with tempfile.TemporaryDirectory() as tmp:
            config, _, plan, context = self._fixture(Path(tmp))
            config.study.paths.stimulation_table.write_text("ID\n", encoding="utf-8")
            config.study.paths.leaddbs_derivatives.mkdir(parents=True, exist_ok=True)
            Path(config.study.space["brainmask"]).parent.mkdir(parents=True, exist_ok=True)
            Path(config.study.space["brainmask"]).write_text("fixture\n", encoding="utf-8")
            direct_tasks = tuple(task for task in plan.tasks if task.endpoint.model_family == "hf_voxel")
            direct_plan = replace(plan, tasks=direct_tasks)
            service = HFObservedService(
                direct_sidecar_runner=sidecar_runner,
                direct_runner=resolver_runner,
            )
            result = execute_plan(
                direct_plan,
                context,
                ServiceRegistry(by_model_family={"hf_voxel": service}),
            )

        self.assertEqual([record.result.status for record in result.tasks], [TaskStatus.COMPLETED] * 3)
        self.assertEqual(result.exit_code, 0)

    def test_hf_fiber_request_locks_connectome_and_feature_order(self) -> None:
        fiber_primary = CaptureRunner(ObservedServiceOutput.empty())
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
            task_root = context.store.run_root / "models" / resolver_task.endpoint.identifier / "tasks" / resolver_task.task_id
            task_root.mkdir(parents=True, exist_ok=True)
            axis_path = task_root / "fiber_ids.npy"
            exposure = task_root / "exposure.npy"
            np.save(axis_path, np.arange(3, dtype=np.int64))
            np.save(exposure, np.ones((12, 3), dtype=np.float32))
            artifact_rows = []
            for kind, name in (
                ("source_status", "source.json"),
                ("selected_source", "selected.json"),
                ("selected_manifest", "manifest.json"),
                ("selected_scores", "scores.csv"),
            ):
                path = task_root / name
                path.write_text("{}\n", encoding="utf-8")
                artifact_rows.append(TaskArtifact(kind, path))
            artifact_rows.append(TaskArtifact("exposure_matrix", exposure))
            output = ObservedServiceOutput(
                source_status="scan_fallback_accepted",
                prediction_status="error_nonpredictive",
                threshold_source="scan_fallback",
                selected_tau=1000,
                selected_coverage=6,
                adjacent_support=4,
                subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
                feature_axis=FeatureAxisRef(axis_path, 3, "b" * 64, "data.mat:idx"),
                artifacts=tuple(artifact_rows),
            )
            fiber_resolver = CaptureRunner(output)
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
                "ids_path": str(axis_path),
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
        self.assertEqual(request.score["sweet_fraction"], 0.01)
        self.assertEqual(request.cheap_observed_sensitivity["high_tau_v_per_m"], 1500)
        self.assertEqual(request.cheap_observed_sensitivity["sweet_top_count"], 1500)

    def test_hf_fiber_observed_rounds_satisfy_executor_artifact_contract(self) -> None:
        shared = {}

        def artifact_runner(kind):
            def run(request):
                request.output_root.mkdir(parents=True, exist_ok=True)
                path = request.output_root / f"{kind}.json"
                path.write_text("{}\n", encoding="utf-8")
                if kind == "sidecar_index":
                    qc = request.output_root / "qc.json"
                    qc.write_text("{}\n", encoding="utf-8")
                    axis = request.model_root / "cache" / "fiber_ids.npy"
                    axis.parent.mkdir(parents=True, exist_ok=True)
                    np.save(axis, np.arange(3, dtype=np.int64))
                    exposure = request.model_root / "cache" / "exposure.npy"
                    np.save(exposure, np.ones((12, 3), dtype=np.float32))
                    shared.update(axis=axis, exposure=exposure)
                    return (TaskArtifact("sidecar_index", path), TaskArtifact("qc", qc))
                return (TaskArtifact(kind, path),)

            return run

        def primary_runner(request):
            request.output_root.mkdir(parents=True, exist_ok=True)
            metrics = request.output_root / "observed_metrics.json"
            predictions = request.output_root / "loocv_predictions.csv"
            metrics.write_text("{}\n", encoding="utf-8")
            predictions.write_text("{}\n", encoding="utf-8")
            return ObservedServiceOutput(
                "not_applicable",
                "not_applicable",
                "pre_specified",
                request.primary_tau,
                request.primary_coverage,
                None,
                request.endpoint.subject_ids,
                FeatureAxisRef(shared["axis"], 3, "b" * 64, "data.mat:idx"),
                (TaskArtifact("observed_metrics", metrics), TaskArtifact("loocv_predictions", predictions)),
            )

        def resolver_runner(request):
            request.output_root.mkdir(parents=True, exist_ok=True)
            paths = {}
            for kind, name in (
                ("source_status", "source.json"),
                ("selected_source", "selected.json"),
                ("selected_manifest", "manifest.json"),
                ("selected_scores", "scores.csv"),
            ):
                path = request.output_root / name
                path.write_text("{}\n", encoding="utf-8")
                paths[kind] = path
            paths["exposure_matrix"] = shared["exposure"]
            return ObservedServiceOutput(
                "pre_specified_accepted",
                "error_nonpredictive",
                "pre_specified",
                request.primary_tau,
                request.primary_coverage,
                2,
                request.endpoint.subject_ids,
                FeatureAxisRef(shared["axis"], 3, "b" * 64, "data.mat:idx"),
                tuple(TaskArtifact(kind, path) for kind, path in paths.items()),
            )

        with tempfile.TemporaryDirectory() as tmp:
            config, _, plan, context = self._fixture(Path(tmp))
            config.study.paths.stimulation_table.write_text("ID\n", encoding="utf-8")
            config.study.paths.leaddbs_derivatives.mkdir(parents=True, exist_ok=True)
            config.study.paths.asset_root.mkdir(parents=True, exist_ok=True)
            connectome = config.study.connectomes["dtor"].path
            connectome.parent.mkdir(parents=True, exist_ok=True)
            connectome.write_text("fixture\n", encoding="utf-8")
            fiber_tasks = tuple(task for task in plan.tasks if task.endpoint.model_family == "hf_fiber")
            fiber_plan = replace(plan, tasks=fiber_tasks)
            service = HFObservedService(
                fiber_sidecar_runner=artifact_runner("sidecar_index"),
                fiber_primary_runner=primary_runner,
                fiber_control_runner=artifact_runner("control_metrics"),
                fiber_sensitivity_runner=artifact_runner("sensitivity_results"),
                fiber_resolver_runner=resolver_runner,
            )
            result = execute_plan(
                fiber_plan,
                context,
                ServiceRegistry(by_model_family={"hf_fiber": service}),
            )

        self.assertEqual([record.result.status for record in result.tasks], [TaskStatus.COMPLETED] * 6)
        self.assertEqual(result.exit_code, 0)

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
