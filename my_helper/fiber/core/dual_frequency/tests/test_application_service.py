"""Application orchestration tests for post-executor reporting and finalization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from dual_frequency.application import service as service_module
from dual_frequency.application.service import (
    WorkflowRequest,
    WorkflowService,
)
from dual_frequency.config import WorkflowOverrides, load_workflow
from dual_frequency.workflow import RunResult, RunStore, ServiceRegistry

try:
    from .test_application_cli import _write_fixture
except ImportError:  # unittest discovery loads this module without a package name
    from test_application_cli import _write_fixture


def _report_request(root: Path, *, resume: bool = False) -> WorkflowRequest:
    base = _write_fixture(root)
    return WorkflowRequest(
        study_base=base.study_base,
        direct_voxel_model=base.direct_voxel_model,
        normative_fiber_model=base.normative_fiber_model,
        workflow_profile=base.workflow_profile,
        overrides=WorkflowOverrides(
            all_available=True,
            through="report",
            resume=resume,
        ),
    )


def _report_documents(run_id: str) -> dict[str, dict[str, object]]:
    return {
        "final_decisions.json": {
            "schema_version": "dual_frequency_final_decisions_v1",
            "run_id": run_id,
            "decisions": [],
        },
        "endpoint_summary.json": {
            "schema_version": "dual_frequency_endpoint_summary_v1",
            "run_id": run_id,
            "endpoints": [],
        },
        "run_report.json": {
            "schema_version": "dual_frequency_run_report_v1",
            "run_id": run_id,
            "technical_status": "completed",
        },
        "artifact_index.json": {
            "schema_version": "dual_frequency_artifact_index_v2",
            "run_id": run_id,
            "artifacts": [],
        },
    }


class WorkflowServiceOrchestrationTest(unittest.TestCase):
    def test_production_default_registry_is_constructible(self) -> None:
        registry = WorkflowService._default_registry()
        self.assertTrue(registry.service_ids)

    def test_input_bundle_carries_portable_tracking_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            request = _report_request(root)
            validated = WorkflowService().plan(request).validated
            run_root = root / "portable-run"
            run_root.mkdir()

            WorkflowService._publish_input_bundle(run_root, validated)

            bundle_root = run_root / "inputs"
            manifest = json.loads(
                (bundle_root / "input_bundle.json").read_text(encoding="utf-8")
            )
            bundled_model = yaml.safe_load(
                (
                    bundle_root
                    / manifest["files"]["individualized_seed_target_model"][
                        "relative_path"
                    ].split("/")[-1]
                ).read_text(encoding="utf-8")
            )
            tracking_entry = manifest["files"]["mrtrix_seed_target"]
            tracking_path = run_root / tracking_entry["relative_path"]
            tracking_is_file = tracking_path.is_file()
            reloaded = load_workflow(
                bundle_root / request.workflow_profile.name,
                request.overrides,
            )

        self.assertTrue(tracking_is_file)
        self.assertEqual(
            bundled_model["tractography"]["tracking_config"],
            tracking_path.name,
        )
        self.assertEqual(
            reloaded.individualized_seed_target.tractography.space,
            validated.configuration.individualized_seed_target.tractography.space,
        )
        self.assertEqual(
            reloaded.scientific_configuration_hash,
            validated.configuration.scientific_configuration_hash,
        )

    def test_exact_run_root_rejects_malformed_manifest_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            root.mkdir()
            manifest = root / RunStore.MANIFEST_NAME
            manifest.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(
                service_module.ApplicationError,
                "run manifest is unreadable",
            ):
                WorkflowService._exact_run_root(root)
            manifest.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(
                service_module.ApplicationError,
                "must be a JSON object",
            ):
                WorkflowService._exact_run_root(root)

    def test_existing_sensitivity_plan_requires_its_task_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sensitivity_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "dual_frequency_sensitivity_plan_v1",
                        "analyses": ["oss"],
                        "plan": {"tasks": []},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                service_module.ApplicationError,
                "structurally incomplete",
            ):
                service_module._persisted_sensitivity_plan(
                    path,
                    configuration_hash="a" * 64,
                )

    def test_v1_sensitivity_plan_accepts_omitted_scheduler_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sensitivity_plan.json"
            persisted = {
                "schema_version": "dual_frequency_sensitivity_plan_v1",
                "analyses": ["oss"],
                "plan": {
                    "tasks": [
                        {
                            "key": {"stage": "oss_activation"},
                            "dependencies": ["task_parent"],
                        }
                    ]
                },
            }
            path.write_text(
                json.dumps(persisted, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            original_bytes = path.read_bytes()
            current = json.loads(json.dumps(persisted))
            current["plan"]["tasks"][0].update(
                {
                    "timeout_seconds": None,
                    "transient_safe": False,
                    "max_transient_retries": 0,
                }
            )

            WorkflowService._write_immutable_sensitivity_plan(path, current)

            self.assertEqual(path.read_bytes(), original_bytes)

    def test_existing_sensitivity_plan_is_not_compared_on_resume(self) -> None:
        persisted = {
            "schema_version": "dual_frequency_sensitivity_plan_v1",
            "analyses": ["oss"],
            "plan": {"tasks": [{"key": {"stage": "oss_activation"}}]},
        }
        nondefault_values = (
            ("timeout_seconds", 60),
            ("transient_safe", True),
            ("max_transient_retries", 1),
        )
        for field, value in nondefault_values:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    path = Path(temporary_directory) / "sensitivity_plan.json"
                    path.write_text(
                        json.dumps(persisted, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    current = json.loads(json.dumps(persisted))
                    current["plan"]["tasks"][0][field] = value

                    WorkflowService._write_immutable_sensitivity_plan(
                        path,
                        current,
                    )
                    self.assertEqual(
                        json.loads(path.read_text(encoding="utf-8")),
                        persisted,
                    )

    def test_existing_scientific_plan_is_not_compared_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sensitivity_plan.json"
            persisted = {
                "schema_version": "dual_frequency_sensitivity_plan_v1",
                "analyses": ["oss"],
                "plan": {
                    "tasks": [
                        {
                            "key": {
                                "stage": "oss_activation",
                                "tau": "400",
                            }
                        }
                    ]
                },
            }
            path.write_text(
                json.dumps(persisted, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            current = json.loads(json.dumps(persisted))
            current["plan"]["tasks"][0]["key"]["tau"] = "600"

            WorkflowService._write_immutable_sensitivity_plan(path, current)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                persisted,
            )

    def test_reporting_publication_rolls_back_all_replaced_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            documents = _report_documents("rollback-run")
            old_bytes: dict[str, bytes] = {}
            for name in documents:
                payload = f'{{"old_document":"{name}"}}\n'.encode("utf-8")
                (root / name).write_bytes(payload)
                old_bytes[name] = payload

            original_replace = service_module.os.replace
            publication_count = 0
            injected = False

            def replace(source, destination):
                nonlocal publication_count, injected
                source_path = Path(source)
                if (
                    source_path.parent.name.startswith(".reporting-stage-")
                    and source_path.suffix == ".json"
                ):
                    publication_count += 1
                    if publication_count == 3 and not injected:
                        injected = True
                        raise OSError("injected publication failure")
                return original_replace(source, destination)

            with patch.object(service_module.os, "replace", side_effect=replace):
                with self.assertRaisesRegex(OSError, "injected publication failure"):
                    WorkflowService._publish_reporting_documents(
                        root,
                        documents,
                        through="report",
                    )

            restored = {name: (root / name).read_bytes() for name in documents}
            staging_directories = tuple(root.glob(".reporting-stage-*"))

        self.assertEqual(restored, old_bytes)
        self.assertFalse(staging_directories)

    def test_explicit_dependencies_publish_before_one_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request = _report_request(root)
            registry = ServiceRegistry()
            provider = object()
            service = WorkflowService(registry=registry, provider=provider)
            contexts = []

            def execute(plan, context):
                contexts.append(context)
                return RunResult(context.run_store.run_id, (), 0)

            def reports(plan, catalog, result, typed_records):
                self.assertEqual(typed_records, {})
                return _report_documents(result.run_id)

            original_finalize = RunStore.finalize
            finalizations: list[str] = []

            def finalize(store: RunStore, status: str) -> None:
                for name in _report_documents(store.run_id):
                    self.assertTrue((store.root / name).is_file())
                finalizations.append(status)
                original_finalize(store, status)

            with (
                patch.object(service_module, "execute_plan", side_effect=execute),
                patch.object(
                    service_module,
                    "build_report_documents",
                    side_effect=reports,
                ),
                patch.object(RunStore, "finalize", new=finalize),
            ):
                result = service.run(request, run_id="application-report")

            run_root = root / "runs" / "synthetic" / "application-report"
            manifest = json.loads(
                (run_root / "run_manifest.json").read_text(encoding="utf-8")
            )
            published = {
                name: json.loads((run_root / name).read_text(encoding="utf-8"))
                for name in _report_documents(result.run_id)
            }

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(finalizations, ["completed"])
        self.assertEqual(len(contexts), 1)
        self.assertIs(contexts[0].registry, registry)
        self.assertIs(contexts[0].provider, provider)
        self.assertEqual(manifest["final_status"], "completed")
        self.assertEqual(
            set(published),
            {
                "final_decisions.json",
                "endpoint_summary.json",
                "run_report.json",
                "artifact_index.json",
            },
        )

    def test_default_registry_and_provider_receive_current_run_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request = _report_request(root)
            registry = ServiceRegistry()
            provider = object()
            service = WorkflowService()
            captured_contexts = []

            def execute(plan, context):
                captured_contexts.append(context)
                return RunResult(context.run_store.run_id, (), 0)

            with (
                patch.object(
                    WorkflowService,
                    "_default_registry",
                    return_value=registry,
                ) as registry_builder,
                patch.object(
                    WorkflowService,
                    "_default_provider",
                    return_value=provider,
                ) as provider_builder,
                patch.object(service_module, "execute_plan", side_effect=execute),
                patch.object(
                    service_module,
                    "build_report_documents",
                    side_effect=lambda plan, catalog, result, records: (
                        _report_documents(result.run_id)
                    ),
                ),
            ):
                service.run(request, run_id="default-dependencies")

            provider_call = provider_builder.call_args
            validated = provider_call.args[0]
            work_root = provider_call.kwargs["work_root"]
            artifact_store = provider_call.kwargs["artifact_store"]

        registry_builder.assert_called_once_with()
        self.assertEqual(validated.study.study_id, "synthetic")
        self.assertEqual(tuple(validated.catalog), validated.catalog)
        self.assertEqual(
            work_root,
            (
                root
                / "runs"
                / "synthetic"
                / "default-dependencies"
                / "runtime_work"
            ).resolve(),
        )
        self.assertIsNotNone(artifact_store)
        self.assertEqual(len(captured_contexts), 1)
        self.assertIs(captured_contexts[0].registry, registry)
        self.assertIs(captured_contexts[0].provider, provider)

    def test_resume_of_completed_run_returns_without_reaggregation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request = _report_request(root)
            registry = ServiceRegistry()
            provider = object()
            service = WorkflowService(registry=registry, provider=provider)

            def execute(plan, context):
                return RunResult(context.run_store.run_id, (), 0)

            with (
                patch.object(service_module, "execute_plan", side_effect=execute),
                patch.object(
                    service_module,
                    "build_report_documents",
                    side_effect=lambda plan, catalog, result, records: (
                        _report_documents(result.run_id)
                    ),
                ),
            ):
                service.run(request, run_id="resume-report")

            run_root = root / "runs" / "synthetic" / "resume-report"
            decision_path = run_root / "final_decisions.json"
            original_decisions = decision_path.read_bytes()
            resumed_request = _report_request(root, resume=True)
            original_finalize = RunStore.finalize
            finalizations: list[str] = []

            def finalize(store: RunStore, status: str) -> None:
                finalizations.append(status)
                original_finalize(store, status)

            aggregation_calls = 0

            def fail_if_aggregated(*_args, **_kwargs):
                nonlocal aggregation_calls
                aggregation_calls += 1
                raise RuntimeError("report aggregation failed")

            with (
                patch.object(service_module, "execute_plan", side_effect=execute),
                patch.object(
                    service_module,
                    "build_report_documents",
                    side_effect=fail_if_aggregated,
                ),
                patch.object(
                    WorkflowService,
                    "_configuration_sources",
                    side_effect=AssertionError(
                        "resume must not recompute configuration-source hashes"
                    ),
                ),
                patch.object(
                    service_module,
                    "compile_execution_plan",
                    side_effect=AssertionError(
                        "completed run resume must not compile the DAG"
                    ),
                ),
                patch.object(
                    RunStore,
                    "read_task_completion",
                    side_effect=AssertionError(
                        "completed run resume must not read task states"
                    ),
                ),
                patch.object(RunStore, "finalize", new=finalize),
            ):
                result = service.run(resumed_request, run_id="resume-report")

            manifest = json.loads(
                (run_root / "run_manifest.json").read_text(encoding="utf-8")
            )
            preserved_decisions = decision_path.read_bytes()

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(aggregation_calls, 0)
        self.assertEqual(finalizations, [])
        self.assertEqual(manifest["final_status"], "completed")
        self.assertEqual(preserved_decisions, original_decisions)


if __name__ == "__main__":
    unittest.main()
