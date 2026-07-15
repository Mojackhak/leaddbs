"""Application orchestration tests for post-executor reporting and finalization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dual_frequency.application import service as service_module
from dual_frequency.application.service import (
    ApplicationError,
    WorkflowRequest,
    WorkflowService,
)
from dual_frequency.config import WorkflowOverrides
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

    def test_resume_aggregation_failure_preserves_prior_decisions_and_fails_run(self) -> None:
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

            with (
                patch.object(service_module, "execute_plan", side_effect=execute),
                patch.object(
                    service_module,
                    "build_report_documents",
                    side_effect=RuntimeError("report aggregation failed"),
                ),
                patch.object(RunStore, "finalize", new=finalize),
            ):
                with self.assertRaisesRegex(
                    ApplicationError,
                    "report aggregation failed",
                ):
                    service.run(resumed_request, run_id="resume-report")

            manifest = json.loads(
                (run_root / "run_manifest.json").read_text(encoding="utf-8")
            )
            preserved_decisions = decision_path.read_bytes()

        self.assertEqual(finalizations, ["failed"])
        self.assertEqual(manifest["final_status"], "failed")
        self.assertEqual(preserved_decisions, original_decisions)


if __name__ == "__main__":
    unittest.main()
