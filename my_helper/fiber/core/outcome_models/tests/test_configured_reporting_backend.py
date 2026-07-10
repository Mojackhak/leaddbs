"""Tests for final-record-driven configured endpoint reporting."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import (
    RunContext,
    TaskArtifact,
    TaskExecutionRecord,
    TaskResult,
    TaskStatus,
)
from outcome_models.planner import compile_execution_plan
from outcome_models.records import (
    ArtifactRef,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.legacy_reporting import run_configured_reporting
from outcome_models.services.reporting import (
    FinalLinkedArtifact,
    ReportingRequest,
    ReportingService,
)
from outcome_models.tests.helpers import (
    clinical_rows_for_scale,
    write_clinical_rows,
    write_profile_bundle,
)


class ConfiguredReportingBackendTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[RunContext, object]:
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
        return RunContext(store=store, catalog=tuple(catalog), config=config), plan

    @staticmethod
    def _placeholder(kind: str, name: str, shape: tuple[int, ...] = ()) -> ArtifactRef:
        return ArtifactRef(
            "final-task",
            kind,
            f"models/final-task/{name}",
            "a" * 64,
            shape,
        )

    def _final(self, endpoint_model_id: str) -> FinalArtifactRecord:
        return FinalArtifactRecord.create(
            final_model_id="final-selected-model",
            endpoint_model_id=endpoint_model_id,
            final_branch="no_delta_hf",
            final_role="fallback_final",
            selected_tau=250,
            selected_coverage=6,
            estimator="partial_spearman",
            scale_direction="lower",
            subject_order=tuple(f"sub-{index:02d}" for index in range(1, 13)),
            nuisance=NuisancePlan.for_branch("no_delta_hf", None),
            manifest=self._placeholder("selected_manifest", "manifest.json"),
            exposure=self._placeholder("exposure_matrix", "exposure.npy", (12, 20)),
            scores=self._placeholder("selected_scores", "scores.csv", (12,)),
            feature_axis=FeatureAxisRef(
                Path("feature_ids.npy"),
                20,
                "b" * 64,
                "candidate_flat_indices",
            ),
        )

    @staticmethod
    def _linked_csv(
        context: RunContext,
        final: FinalArtifactRecord,
        *,
        kind: str,
        name: str,
        rows: list[dict[str, object]],
    ) -> FinalLinkedArtifact:
        path = context.store.run_root / "explicit_inputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        artifact = ArtifactRef(
            task_id=f"task-{kind}",
            kind=kind,
            relative_path=path.relative_to(context.store.run_root).as_posix(),
            sha256=sha256_file(path),
        )
        return FinalLinkedArtifact(final.final_model_id, final.record_hash, artifact)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_endpoint_summary_emits_only_planner_summary_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_summary"
            )
            final = self._final(task.endpoint.identifier)
            formal = self._linked_csv(
                context,
                final,
                kind="permutation_results",
                name="formal.csv",
                rows=[
                    {"p_plus_one_two_sided": 0.04, "q2": 0.10, "note": "observed"},
                    {"p_plus_one_two_sided": 0.02, "q2": -0.20, "note": "observed"},
                ],
            )
            request = ReportingRequest.from_context(task, context, final, artifacts=(formal,))

            output = run_configured_reporting(request)

            self.assertEqual([artifact.kind for artifact in output.artifacts], ["endpoint_summary"])
            rows = self._read_csv(output.artifacts[0].path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["final_model_id"], final.final_model_id)
            self.assertEqual(rows[0]["final_record_hash"], final.record_hash)
            self.assertEqual(rows[0]["linked_artifact_count"], "1")
            self.assertEqual(rows[0]["numeric_metric_count"], "2")

    def test_endpoint_report_uses_only_explicit_artifacts_and_marks_missing_optionals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_report"
            )
            final = self._final(task.endpoint.identifier)
            formal = self._linked_csv(
                context,
                final,
                kind="permutation_results",
                name="formal.csv",
                rows=[{"p_plus_one_two_sided": 0.04, "permutation_count": 10000}],
            )
            orphan = context.store.run_root / "unlinked" / "fdr_density_label_cache.csv"
            orphan.parent.mkdir(parents=True, exist_ok=True)
            orphan.write_text("q_value,density,label\n0.01,12,STN\n", encoding="utf-8")
            request = ReportingRequest.from_context(task, context, final, artifacts=(formal,))

            output = run_configured_reporting(request)

            self.assertEqual(
                [artifact.kind for artifact in output.artifacts],
                ["endpoint_report", "artifact_index"],
            )
            report_rows = self._read_csv(output.artifacts[0].path)
            self.assertGreaterEqual(len(report_rows), 1)
            for row in report_rows:
                self.assertEqual(row["final_model_id"], final.final_model_id)
                self.assertEqual(row["final_record_hash"], final.record_hash)
                self.assertEqual(row["fdr_status"], "missing_optional_artifact")
                self.assertEqual(row["density_status"], "missing_optional_artifact")
                self.assertEqual(row["labels_status"], "missing_optional_artifact")
            index_rows = self._read_csv(output.artifacts[1].path)
            self.assertEqual({row["artifact_kind"] for row in index_rows}, {"permutation_results", "endpoint_report"})
            self.assertNotIn(str(orphan), {row["artifact_path"] for row in index_rows})
            for row in index_rows:
                self.assertEqual(row["final_model_id"], final.final_model_id)
                self.assertEqual(row["final_record_hash"], final.record_hash)

    def test_explicit_optional_artifacts_are_reported_without_fabrication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_report"
            )
            final = self._final(task.endpoint.identifier)
            artifacts = tuple(
                self._linked_csv(
                    context,
                    final,
                    kind=kind,
                    name=f"{kind}.csv",
                    rows=[row],
                )
                for kind, row in (
                    ("fdr_results", {"q_value": 0.03}),
                    ("density_results", {"fiber_density": 18.0}),
                    ("label_results", {"label": "motor_STN"}),
                )
            )
            request = ReportingRequest.from_context(task, context, final, artifacts=artifacts)

            output = run_configured_reporting(request)

            rows = self._read_csv(output.artifacts[0].path)
            self.assertTrue(rows)
            self.assertEqual({row["fdr_status"] for row in rows}, {"available_explicit_artifact"})
            self.assertEqual({row["density_status"] for row in rows}, {"available_explicit_artifact"})
            self.assertEqual({row["labels_status"] for row in rows}, {"available_explicit_artifact"})
            self.assertNotIn("source_status", rows[0])
            self.assertNotIn("prediction_status", rows[0])
            self.assertNotIn("source_status", output.facts)
            self.assertNotIn("prediction_status", output.facts)

    def test_rejects_tampered_explicit_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_report"
            )
            final = self._final(task.endpoint.identifier)
            formal = self._linked_csv(
                context,
                final,
                kind="permutation_results",
                name="formal.csv",
                rows=[{"p_plus_one_two_sided": 0.04}],
            )
            source_path = context.store.run_root / formal.artifact.relative_path
            source_path.write_text("p_plus_one_two_sided\n0.99\n", encoding="utf-8")
            request = ReportingRequest.from_context(task, context, final, artifacts=(formal,))

            with self.assertRaises(RecordError):
                run_configured_reporting(request)

    def _install_dependency_results(
        self,
        context: RunContext,
        plan,
        reporting_task,
        *,
        final: FinalArtifactRecord | None,
        terminal_status: TaskStatus = TaskStatus.COMPLETED,
        terminal_detail: str = "",
        artifact: TaskArtifact | None = None,
    ) -> None:
        tasks = {task.task_id: task for task in plan.tasks}
        pending = [dependency.task_id for dependency in reporting_task.dependencies]
        closure: list[object] = []
        seen: set[str] = set()
        while pending:
            task_id = pending.pop()
            if task_id in seen:
                continue
            seen.add(task_id)
            dependency_task = tasks[task_id]
            closure.append(dependency_task)
            pending.extend(item.task_id for item in dependency_task.dependencies)
        for dependency_task in closure:
            context.results[dependency_task.task_id] = TaskExecutionRecord(
                task=dependency_task,
                result=TaskResult(TaskStatus.COMPLETED, "dependency_completed"),
            )
        first_task = tasks[reporting_task.dependencies[0].task_id]
        facts = {}
        artifacts = ()
        if final is not None:
            facts = {
                "final_model_realized": True,
                "final_model_record": final.as_dict(),
            }
        if artifact is not None:
            artifacts = (artifact,)
            context.store.record_artifact(
                task_id=first_task.task_id,
                kind=artifact.kind,
                path=artifact.path,
            )
        context.results[first_task.task_id] = TaskExecutionRecord(
            task=first_task,
            result=TaskResult(
                terminal_status,
                terminal_detail,
                facts=facts,
                artifacts=artifacts,
            ),
        )

    def test_reporting_service_loads_exact_final_and_only_direct_dependency_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_summary"
            )
            final = self._final(task.endpoint.identifier)
            source = context.store.run_root / "explicit_inputs" / "formal.csv"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("p_plus_one_two_sided\n0.04\n", encoding="utf-8")
            direct_artifact = TaskArtifact("permutation_results", source)
            self._install_dependency_results(
                context,
                plan,
                task,
                final=final,
                artifact=direct_artifact,
            )

            unrelated_task = next(
                item
                for item in plan.tasks
                if item.endpoint.identifier == task.endpoint.identifier
                and item.task_id not in {dependency.task_id for dependency in task.dependencies}
                and item.task_id != task.task_id
            )
            unrelated_path = context.store.run_root / "unrelated" / "should_not_report.csv"
            unrelated_path.parent.mkdir(parents=True, exist_ok=True)
            unrelated_path.write_text("q_value\n0.01\n", encoding="utf-8")
            unrelated_artifact = TaskArtifact("fdr_results", unrelated_path)
            context.store.record_artifact(
                task_id=unrelated_task.task_id,
                kind=unrelated_artifact.kind,
                path=unrelated_artifact.path,
            )
            context.results[unrelated_task.task_id] = TaskExecutionRecord(
                task=unrelated_task,
                result=TaskResult(
                    TaskStatus.COMPLETED,
                    artifacts=(unrelated_artifact,),
                ),
            )

            result = ReportingService(runner=run_configured_reporting).execute(task, context)

            self.assertEqual(result.status, TaskStatus.COMPLETED)
            self.assertEqual(result.facts["final_model_id"], final.final_model_id)
            self.assertEqual(result.facts["final_record_hash"], final.record_hash)
            self.assertTrue(result.facts["reporting_complete"])
            self.assertNotIn("source_status", result.facts)
            self.assertNotIn("prediction_status", result.facts)
            summary_rows = self._read_csv(result.artifacts[0].path)
            self.assertEqual(summary_rows[0]["linked_artifact_count"], "1")
            self.assertEqual(summary_rows[0]["fdr_status"], "missing_optional_artifact")

    def test_reporting_service_rejects_dependency_artifact_index_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_summary"
            )
            final = self._final(task.endpoint.identifier)
            source = context.store.run_root / "explicit_inputs" / "formal.csv"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("p_value\n0.04\n", encoding="utf-8")
            self._install_dependency_results(
                context,
                plan,
                task,
                final=final,
                artifact=TaskArtifact("permutation_results", source),
            )
            source.write_text("p_value\n0.99\n", encoding="utf-8")

            result = ReportingService(runner=run_configured_reporting).execute(task, context)

            self.assertEqual(result.status, TaskStatus.EXECUTION_FAILURE)
            self.assertIn("artifact index SHA-256 mismatch", result.detail)

    def test_no_final_summary_and_report_complete_without_fabricated_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            summary_task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_summary"
            )
            report_task = next(
                item
                for item in plan.tasks
                if item.endpoint.identifier == summary_task.endpoint.identifier
                and item.key.execution_stage == "endpoint_report"
            )
            self._install_dependency_results(
                context,
                plan,
                summary_task,
                final=None,
                terminal_status=TaskStatus.NO_FINAL_MODEL,
                terminal_detail="no_stable_source_or_fallback",
            )
            service = ReportingService(runner=run_configured_reporting)

            summary_result = service.execute(summary_task, context)

            self.assertEqual(summary_result.status, TaskStatus.COMPLETED)
            self.assertEqual(summary_result.facts["endpoint_terminal_status"], "no_final_model")
            self.assertEqual(summary_result.facts["final_model_id"], "")
            self.assertEqual(summary_result.facts["final_record_hash"], "")
            summary_rows = self._read_csv(summary_result.artifacts[0].path)
            self.assertEqual(summary_rows[0]["endpoint_terminal_status"], "no_final_model")
            self.assertEqual(summary_rows[0]["final_model_id"], "")
            self.assertEqual(summary_rows[0]["final_record_hash"], "")
            self.assertEqual(summary_rows[0]["fdr_status"], "not_applicable_no_final_model")
            self.assertEqual(summary_rows[0]["density_status"], "not_applicable_no_final_model")
            self.assertEqual(summary_rows[0]["labels_status"], "not_applicable_no_final_model")

            context.store.record_artifact(
                task_id=summary_task.task_id,
                kind=summary_result.artifacts[0].kind,
                path=summary_result.artifacts[0].path,
            )
            context.results[summary_task.task_id] = TaskExecutionRecord(
                task=summary_task,
                result=summary_result,
            )
            report_result = service.execute(report_task, context)

            self.assertEqual(report_result.status, TaskStatus.COMPLETED)
            self.assertEqual(report_result.facts["endpoint_terminal_status"], "no_final_model")
            report_rows = self._read_csv(report_result.artifacts[0].path)
            self.assertTrue(report_rows)
            self.assertEqual({row["final_model_id"] for row in report_rows}, {""})
            self.assertEqual({row["final_record_hash"] for row in report_rows}, {""})
            self.assertEqual(
                {row["endpoint_terminal_status"] for row in report_rows},
                {"no_final_model"},
            )

    def test_input_failure_summary_completes_with_explicit_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            task = next(
                item
                for item in plan.tasks
                if item.endpoint.model_family == "ulf_voxel"
                and item.key.execution_stage == "endpoint_summary"
            )
            self._install_dependency_results(
                context,
                plan,
                task,
                final=None,
                terminal_status=TaskStatus.INPUT_FAILURE,
                terminal_detail="missing_required_endpoint_values",
            )

            result = ReportingService(runner=run_configured_reporting).execute(task, context)

            self.assertEqual(result.status, TaskStatus.COMPLETED)
            self.assertEqual(result.facts["endpoint_terminal_status"], "input_failure")
            rows = self._read_csv(result.artifacts[0].path)
            self.assertEqual(rows[0]["endpoint_terminal_status"], "input_failure")
            self.assertIn("missing_required_endpoint_values", rows[0]["endpoint_terminal_detail"])
            self.assertEqual(rows[0]["fdr_status"], "not_applicable_input_failure")


if __name__ == "__main__":
    unittest.main()
