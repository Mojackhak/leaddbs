"""Tests for configured task execution and the public workflow CLI."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.cli import main as cli_main
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import (
    ExitCode,
    RunContext,
    ServiceRegistry,
    TaskArtifact,
    TaskResult,
    TaskStatus,
    execute_plan,
)
from outcome_models.planner import compile_execution_plan
from outcome_models.run_store import ConfiguredRunStore, REQUIRED_RUN_ARTIFACTS
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class DeterministicService:
    def __init__(self, outcomes=None) -> None:
        self.outcomes = dict(outcomes or {})
        self.calls: list[str] = []
        self.configs = []

    def execute(self, task, context) -> TaskResult:
        self.calls.append(task.task_id)
        self.configs.append(context.config)
        if task.task_id in self.outcomes:
            return self._with_artifacts(task, context, self.outcomes[task.task_id])
        facts: dict[str, object] = {}
        if task.key.execution_stage == "preprocessing_sidecars" and task.endpoint.model_family.startswith("ulf_"):
            facts["delta_hfscore_inputs_valid"] = True
        if task.key.execution_stage == "observed_source_resolver":
            facts.update(
                {
                    "source_accepted": True,
                    "source_status": "pre_specified_accepted",
                    "prediction_status": "error_predictive",
                }
            )
        if task.key.execution_stage == "final_model_realization":
            facts.update(
                {
                    "final_model_realized": True,
                    "final_model_id": f"final-{task.endpoint.identifier}",
                    "final_role": "primary",
                }
            )
        if task.workflow_phase == "formal":
            facts["formal_complete"] = True
        return self._with_artifacts(task, context, TaskResult(status=TaskStatus.COMPLETED, detail="ok", facts=facts))

    @staticmethod
    def _with_artifacts(task, context, result: TaskResult) -> TaskResult:
        if result.status != TaskStatus.COMPLETED:
            return result
        artifacts = list(result.artifacts)
        existing = {artifact.kind for artifact in artifacts}
        for kind in task.expected_artifact_kinds:
            if kind == "task_manifest" or kind in existing:
                continue
            path = context.store.run_root / "tasks" / task.task_id / f"{kind}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"kind": kind, "task_id": task.task_id}) + "\n", encoding="utf-8")
            artifacts.append(TaskArtifact(kind, path))
        return TaskResult(result.status, result.detail, result.facts, tuple(artifacts))


class EmptyArtifactService:
    def execute(self, task, context) -> TaskResult:
        del task, context
        return TaskResult(TaskStatus.COMPLETED, "incorrectly claims completion")


class ExecutorAndCliTests(unittest.TestCase):
    def _bundle(self, root: Path, *, through="observed", mutate=None, rows=None):
        def combined(profiles):
            profiles["workflow"]["execution"]["through"] = through
            profiles["study"]["paths"]["output_root"] = str(root / "configured-output")
            if mutate is not None:
                mutate(profiles)

        workflow_path = write_profile_bundle(root, mutate=combined)
        write_clinical_rows(root, rows or clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow_path, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        return workflow_path, config, catalog, plan

    def _store(self, root: Path, config, catalog, plan) -> ConfiguredRunStore:
        store = ConfiguredRunStore.create(
            output_root=root / "configured-output",
            study_id=config.study.study_id,
            provenance={
                "configuration_hash": config.configuration_hash,
                "input_hashes": {"clinical_table": "clinical", "stimulation_table": "stimulation"},
                "code_provenance": {"commit": "abc123", "dirty": False, "environment": "leaddbs"},
            },
            started_at=datetime(2026, 7, 9, 13, 0, 0, tzinfo=timezone.utc),
        )
        store.initialize(
            resolved_workflow={"configuration_hash": config.configuration_hash},
            endpoint_catalog=[row.as_dict() for row in catalog],
            execution_plan=plan.as_dict(),
        )
        return store

    def test_endpoint_input_failure_does_not_stop_other_scale(self) -> None:
        def mutate(profiles):
            second = dict(profiles["scales"]["scales"][0])
            second.update({"scale_id": "scale_two", "label": "Scale Two"})
            second["endpoint_bindings"] = dict(second["endpoint_bindings"])
            profiles["scales"]["scales"].append(second)
            profiles["workflow"]["selection"]["scales"] = ["scale_one", "scale_two"]

        rows = clinical_rows_for_scale("Scale One") + clinical_rows_for_scale("Scale Two", subject_prefix="two")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root, mutate=mutate, rows=rows)
            failed = next(
                task
                for task in plan.tasks
                if task.endpoint.scale_id == "scale_one" and task.key.execution_stage in {"input_readiness", "version_input_freeze"}
            )
            service = DeterministicService(
                {failed.task_id: TaskResult(TaskStatus.INPUT_FAILURE, "synthetic input failure")}
            )
            store = self._store(root, config, catalog, plan)
            result = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog)),
                ServiceRegistry(default=service),
            )

        scale_two = [record for record in result.tasks if record.task.endpoint.scale_id == "scale_two"]
        self.assertEqual(result.exit_code, ExitCode.PLANNED_INPUT_FAILURE)
        self.assertTrue(any(record.result.status == TaskStatus.COMPLETED for record in scale_two))
        self.assertEqual(len({record.task.task_id for record in result.tasks}), len(result.tasks))

    def test_completed_service_result_missing_expected_artifacts_becomes_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root)
            store = self._store(root, config, catalog, plan)
            result = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog), config=config),
                ServiceRegistry(default=EmptyArtifactService()),
            )

        first = result.tasks[0]
        self.assertEqual(first.result.status, TaskStatus.EXECUTION_FAILURE)
        self.assertIn("missing_expected_artifacts", first.result.detail)

    def test_failed_hf_resolver_releases_no_delta_and_skips_adjusted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root)
            hf_resolver = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_voxel" and task.key.execution_stage == "observed_source_resolver"
            )
            service = DeterministicService(
                {hf_resolver.task_id: TaskResult(TaskStatus.EXECUTION_FAILURE, "synthetic resolver failure")}
            )
            store = self._store(root, config, catalog, plan)
            result = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog)),
                ServiceRegistry(default=service),
            )

        no_delta = next(
            record
            for record in result.tasks
            if record.task.endpoint.model_family == "ulf_voxel" and record.task.key.branch == "no_delta_hf"
        )
        adjusted = next(
            record
            for record in result.tasks
            if record.task.endpoint.model_family == "ulf_voxel" and record.task.key.branch == "delta_hf_adjusted"
        )
        self.assertEqual(no_delta.result.status, TaskStatus.COMPLETED)
        self.assertEqual(adjusted.result.status, TaskStatus.SKIPPED_GATE)
        self.assertEqual(result.exit_code, ExitCode.EXECUTION_OR_NO_FINAL_FAILURE)

    def test_delta_gate_reads_exact_sidecar_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root)
            hf_lock = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "input_hf_lock"
            )
            sidecar = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "preprocessing_sidecars"
            )
            service = DeterministicService(
                {
                    hf_lock.task_id: TaskResult(
                        TaskStatus.COMPLETED,
                        "unrelated fact must not open adjusted gate",
                        {"delta_hfscore_inputs_valid": True},
                    ),
                    sidecar.task_id: TaskResult(TaskStatus.COMPLETED, "sidecar has no Delta bundle", {}),
                }
            )
            store = self._store(root, config, catalog, plan)
            result = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog), config=config),
                ServiceRegistry(default=service),
            )

        adjusted = next(
            record
            for record in result.tasks
            if record.task.endpoint.model_family == "ulf_voxel" and record.task.key.branch == "delta_hf_adjusted"
        )
        self.assertEqual(adjusted.result.status, TaskStatus.SKIPPED_GATE)

    def test_no_final_model_skips_formal_but_report_still_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root, through="report")
            final = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "final_model_realization"
            )
            service = DeterministicService(
                {final.task_id: TaskResult(TaskStatus.NO_FINAL_MODEL, "no stable ULF source")}
            )
            store = self._store(root, config, catalog, plan)
            result = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog)),
                ServiceRegistry(default=service),
            )

        ulf_formal = [
            record
            for record in result.tasks
            if record.task.endpoint.model_family == "ulf_voxel" and record.task.workflow_phase == "formal"
        ]
        ulf_reports = [
            record
            for record in result.tasks
            if record.task.endpoint.model_family == "ulf_voxel" and record.task.workflow_phase == "report"
        ]
        self.assertTrue(all(record.result.status == TaskStatus.SKIPPED_DEPENDENCY for record in ulf_formal))
        self.assertTrue(all(record.result.status == TaskStatus.COMPLETED for record in ulf_reports))
        self.assertEqual(result.exit_code, ExitCode.EXECUTION_OR_NO_FINAL_FAILURE)

    def test_resume_reuses_completed_tasks_without_service_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config, catalog, plan = self._bundle(root)
            store = self._store(root, config, catalog, plan)
            first_service = DeterministicService()
            first = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog)),
                ServiceRegistry(default=first_service),
            )
            second_service = DeterministicService()
            second = execute_plan(
                plan,
                RunContext(store=store, catalog=tuple(catalog), resume=True),
                ServiceRegistry(default=second_service),
            )

        self.assertEqual(first.exit_code, ExitCode.SUCCESS)
        self.assertEqual(second.exit_code, ExitCode.SUCCESS)
        self.assertEqual(second_service.calls, [])
        self.assertTrue(all(record.reused for record in second.tasks))

    def test_cli_validate_plan_run_status_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_path, _, _, _ = self._bundle(root)
            registry = ServiceRegistry(default=DeterministicService())

            self.assertEqual(cli_main(["validate", "--config", str(workflow_path)]), ExitCode.SUCCESS)
            plan_output = io.StringIO()
            with contextlib.redirect_stdout(plan_output):
                plan_code = cli_main(["plan", "--config", str(workflow_path), "--models", "ulf-voxel"])
            plan_payload = json.loads(plan_output.getvalue())
            families = {task["endpoint"]["model_family"] for task in plan_payload["tasks"]}
            self.assertEqual(plan_code, ExitCode.SUCCESS)
            self.assertEqual(families, {"hf_voxel", "ulf_voxel"})

            run_output = io.StringIO()
            with contextlib.redirect_stdout(run_output):
                run_code = cli_main(
                    ["run", "--config", str(workflow_path)],
                    service_registry=registry,
                    now=datetime(2026, 7, 9, 14, 0, 0, tzinfo=timezone.utc),
                )
            run_payload = json.loads(run_output.getvalue())
            run_root = Path(run_payload["run_root"])
            self.assertEqual(run_code, ExitCode.SUCCESS)
            self.assertTrue(all((run_root / name).is_file() for name in REQUIRED_RUN_ARTIFACTS))

            status_output = io.StringIO()
            with contextlib.redirect_stdout(status_output):
                status_code = cli_main(
                    [
                        "status",
                        "--output-root",
                        str(root / "configured-output"),
                        "--run-id",
                        run_payload["run_id"],
                    ]
                )
            status_payload = json.loads(status_output.getvalue())
            self.assertEqual(status_code, ExitCode.SUCCESS)
            self.assertTrue(status_payload["tasks"])

            artifact_output = io.StringIO()
            with contextlib.redirect_stdout(artifact_output):
                artifact_code = cli_main(
                    [
                        "artifacts",
                        "--output-root",
                        str(root / "configured-output"),
                        "--run-id",
                        run_payload["run_id"],
                    ]
                )
            artifact_payload = json.loads(artifact_output.getvalue())
            self.assertEqual(artifact_code, ExitCode.SUCCESS)
            self.assertTrue(artifact_payload["artifacts"])
            self.assertTrue(registry.default.configs)
            self.assertTrue(all(config is not None for config in registry.default.configs))

    def test_cli_selection_and_run_lookup_argument_errors_return_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_path, _, _, _ = self._bundle(Path(tmp))
            cases = [
                ["plan", "--config", str(workflow_path), "--scale", "scale_one", "--all-available"],
                ["run", "--config", str(workflow_path), "--resume"],
                ["status", "--run-id", "missing-output-root"],
                ["artifacts", "--output-root", str(Path(tmp))],
                ["plan", "--config", str(workflow_path), "--candidate-threshold-v-per-m", "100"],
            ]
            codes = []
            for argv in cases:
                with contextlib.redirect_stderr(io.StringIO()):
                    codes.append(cli_main(argv))

        self.assertEqual(codes, [ExitCode.CONFIGURATION_ERROR] * len(cases))

    def test_cli_help_is_a_successful_terminal_command(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli_main(["--help"])
        self.assertEqual(code, ExitCode.SUCCESS)

    def test_cli_repeatable_scale_all_available_and_through_overrides(self) -> None:
        def mutate(profiles):
            second = dict(profiles["scales"]["scales"][0])
            second.update({"scale_id": "scale_two", "label": "Scale Two"})
            second["endpoint_bindings"] = dict(second["endpoint_bindings"])
            profiles["scales"]["scales"].append(second)

        rows = clinical_rows_for_scale("Scale One") + clinical_rows_for_scale("Scale Two", subject_prefix="two")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_path, _, _, _ = self._bundle(root, mutate=mutate, rows=rows)
            explicit_output = io.StringIO()
            with contextlib.redirect_stdout(explicit_output):
                explicit_code = cli_main(
                    [
                        "plan",
                        "--config",
                        str(workflow_path),
                        "--scale",
                        "scale_one",
                        "--scale",
                        "scale_two",
                        "--models",
                        "ulf-voxel",
                        "--phases",
                        "chronic",
                        "--connectomes",
                        "dtor",
                        "--through",
                        "formal",
                    ]
                )
            explicit = json.loads(explicit_output.getvalue())
            available_output = io.StringIO()
            with contextlib.redirect_stdout(available_output):
                available_code = cli_main(["plan", "--config", str(workflow_path), "--all-available"])
            available = json.loads(available_output.getvalue())

        self.assertEqual(explicit_code, ExitCode.SUCCESS)
        self.assertEqual({task["endpoint"]["scale_id"] for task in explicit["tasks"]}, {"scale_one", "scale_two"})
        self.assertEqual({task["endpoint"]["model_family"] for task in explicit["tasks"]}, {"hf_voxel", "ulf_voxel"})
        self.assertTrue(all(task["workflow_phase"] in {"observed", "formal"} for task in explicit["tasks"]))
        self.assertEqual(available_code, ExitCode.SUCCESS)
        self.assertEqual({task["endpoint"]["scale_id"] for task in available["tasks"]}, {"scale_one", "scale_two"})

    def test_cli_resume_reuses_same_run_and_force_records_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_path, _, _, _ = self._bundle(root)
            first_output = io.StringIO()
            with contextlib.redirect_stdout(first_output):
                first_code = cli_main(
                    ["run", "--config", str(workflow_path)],
                    service_registry=ServiceRegistry(default=DeterministicService()),
                    now=datetime(2026, 7, 9, 15, 0, 0, tzinfo=timezone.utc),
                )
            first = json.loads(first_output.getvalue())

            resumed_service = DeterministicService()
            resumed_output = io.StringIO()
            with contextlib.redirect_stdout(resumed_output):
                resumed_code = cli_main(
                    ["run", "--config", str(workflow_path), "--resume", "--run-id", first["run_id"]],
                    service_registry=ServiceRegistry(default=resumed_service),
                )
            resumed = json.loads(resumed_output.getvalue()) if resumed_output.getvalue() else {}

            forced_output = io.StringIO()
            with contextlib.redirect_stdout(forced_output):
                forced_code = cli_main(
                    ["run", "--config", str(workflow_path), "--force", "--run-id", first["run_id"]],
                    service_registry=ServiceRegistry(default=DeterministicService()),
                    now=datetime(2026, 7, 9, 15, 0, 1, tzinfo=timezone.utc),
                )
            forced = json.loads(forced_output.getvalue())
            forced_manifest = json.loads((Path(forced["run_root"]) / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(first_code, ExitCode.SUCCESS)
        self.assertEqual(resumed_code, ExitCode.SUCCESS)
        self.assertEqual(resumed["run_id"], first["run_id"])
        self.assertEqual(resumed_service.calls, [])
        self.assertEqual(forced_code, ExitCode.SUCCESS)
        self.assertNotEqual(forced["run_id"], first["run_id"])
        self.assertEqual(forced_manifest["supersedes_run_id"], first["run_id"])


if __name__ == "__main__":
    unittest.main()
