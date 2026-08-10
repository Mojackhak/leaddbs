"""Pure post-executor reporting from plans, outcomes, and typed records."""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from dual_frequency.catalog import CatalogStatus, EndpointRecord
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BranchRecord,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    RecordError,
    SensitiveRecord,
    SourceRecord,
    SubjectExclusionRecord,
    TaskKey,
)
from dual_frequency.reporting import (
    ArtifactIndexError,
    FinalDecisionRecord,
    ReportingError,
    aggregate_final_decisions,
    build_artifact_index,
    build_endpoint_summary,
    build_report_documents,
    build_run_report,
)
from dual_frequency.workflow import (
    ExecutionPlan,
    RunResult,
    ServiceResult,
    TaskOutcome,
    TaskSpec,
)


@dataclass(frozen=True)
class ReportingFixture:
    plan: ExecutionPlan
    catalog: tuple[EndpointRecord, ...]
    result: RunResult
    records: dict[str, object]
    envelope_only: ArtifactRef


def _artifact(
    kind: str,
    digest: str,
    axis: AxisRef,
    *,
    units: str = "score",
) -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        schema_version="synthetic_v1",
        uri=f"memory://current-run/{kind}/{digest[:8]}",
        sha256=digest,
        dtype="float32",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=units,
        space=None,
        producer_id="synthetic_service",
        producer_version="1",
    )


def _endpoint(
    name: str,
    model_family: str,
    *,
    requested: bool,
    connectome_id: str = "none",
    connectome_role: str = "none",
    final_eligible: bool = True,
    matched_reference_endpoint_id: str | None = None,
) -> EndpointRecord:
    key = EndpointKey(
        study_id="study",
        scale_id=name,
        endpoint_binding_id=f"binding_{name}",
        model_family=model_family,
        connectome_id=connectome_id,
    )
    return EndpointRecord(
        key=key,
        scale_label=name,
        scale_direction="lower",
        baseline_binding_id=f"baseline_{name}",
        outcome_binding_id=f"outcome_{name}",
        matched_reference_endpoint_id=matched_reference_endpoint_id,
        connectome_role=connectome_role,
        final_eligible=final_eligible,
        requested=requested,
        subject_ids=("s1", "s2", "s3", "s4"),
        minimum_subjects=3,
        status=CatalogStatus.DATA_AVAILABLE,
    )


def _task(
    endpoint: EndpointRecord,
    stage: str,
    output_record_type: str,
    *,
    dependencies: tuple[str, ...] = (),
) -> TaskSpec:
    return TaskSpec(
        key=TaskKey(
            endpoint_id=endpoint.endpoint_id,
            stage=stage,
            parameter_identity="synthetic_configuration",
        ),
        endpoint_id=endpoint.endpoint_id,
        model_family=endpoint.key.model_family,
        connectome_role=endpoint.connectome_role,
        stage=stage,
        round_id="round_test",
        phase="observed",
        service_id=f"service_{endpoint.key.scale_id}_{stage}",
        dependencies=dependencies,
        gates=(),
        output_record_type=output_record_type,
    )


def _source(endpoint: EndpointRecord, digest: str) -> SourceRecord:
    feature_axis = AxisRef(
        f"features_{endpoint.key.scale_id}",
        2,
        digest,
    )
    artifact = _artifact(
        f"source_{endpoint.key.scale_id}",
        digest,
        feature_axis,
    )
    return SourceRecord(
        endpoint=endpoint.key,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_predictive",
        threshold_source="pre_specified",
        selected_tau=0.5,
        selected_coverage=2,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "synthetic_feature_ids"),
        artifacts=(artifact,),
    )


def _reference_final(endpoint: EndpointRecord, digest: str) -> FinalModelRecord:
    source = _source(endpoint, digest)
    return FinalModelRecord(
        endpoint=endpoint.key,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint_id=endpoint.endpoint_id,
            final_branch="reference",
            selected_tau=0.5,
            selected_coverage=2,
            estimator="synthetic_estimator",
        ),
        selected_source=source,
        selected_branch=None,
        artifacts=source.artifacts,
    )


def _fallback_final(endpoint: EndpointRecord, digest: str) -> FinalModelRecord:
    source = _source(endpoint, digest)
    branch = BranchRecord(
        endpoint=endpoint.key,
        branch="no_delta_reference",
        intended_role="fallback_eligible",
        input_status="valid",
        nuisance_design_status="valid",
        source=source,
        artifacts=source.artifacts,
    )
    return FinalModelRecord(
        endpoint=endpoint.key,
        final_status="fallback_final_realized",
        realization_role="fallback_final",
        final_key=FinalModelKey(
            endpoint_id=endpoint.endpoint_id,
            final_branch="no_delta_reference",
            selected_tau=0.5,
            selected_coverage=2,
            estimator="synthetic_estimator",
        ),
        selected_source=None,
        selected_branch=branch,
        artifacts=source.artifacts,
    )


def _realized_selection(final_model: FinalModelRecord) -> FinalSelectionRecord:
    return FinalSelectionRecord(
        endpoint=final_model.endpoint,
        selection_status=final_model.final_status,
        final_model=final_model,
        reason_codes=(final_model.final_status,),
        causal_task_ids=(),
    )


def _no_final_selection(endpoint: EndpointRecord) -> FinalSelectionRecord:
    return FinalSelectionRecord(
        endpoint=endpoint.key,
        selection_status="no_final_model",
        final_model=None,
        reason_codes=("no_stable_source",),
        causal_task_ids=(),
    )


def _input_record(
    endpoint: EndpointRecord,
    subject_axis: AxisRef,
    baseline: ArtifactRef,
    outcome: ArtifactRef,
) -> EndpointInputRecord:
    return EndpointInputRecord(
        endpoint=endpoint.key,
        readiness_status="ready",
        candidate_subject_ids=("s1", "s2", "s3", "s4"),
        included_subject_ids=("s1", "s2", "s3"),
        exclusions=(SubjectExclusionRecord("s4", "missing_addon_exposure"),),
        minimum_subjects=3,
        subject_axis=subject_axis,
        baseline=baseline,
        outcome=outcome,
    )


def _completed(
    task: TaskSpec,
    record: object,
) -> TaskOutcome:
    return TaskOutcome(
        task_id=task.task_id,
        endpoint_id=task.endpoint_id,
        service_id=task.service_id,
        status="completed",
        reason="none",
        result=ServiceResult.from_record(record),
    )


def _terminal(task: TaskSpec, status: str, reason: str) -> TaskOutcome:
    return TaskOutcome(
        task_id=task.task_id,
        endpoint_id=task.endpoint_id,
        service_id=task.service_id,
        status=status,
        reason=reason,
        result=None,
    )


def _build_fixture() -> ReportingFixture:
    primary = _endpoint("primary", "reference_voxel", requested=True)
    fallback = _endpoint(
        "primary",
        "addon_voxel",
        requested=True,
        matched_reference_endpoint_id=primary.endpoint_id,
    )
    execution = _endpoint("execution", "reference_voxel", requested=True)
    dependency_reference = _endpoint(
        "dependency", "reference_voxel", requested=False
    )
    dependency = _endpoint(
        "dependency",
        "addon_voxel",
        requested=True,
        matched_reference_endpoint_id=dependency_reference.endpoint_id,
    )
    no_final = _endpoint("no_final", "reference_voxel", requested=True)
    formal_fiber = _endpoint(
        "sensitivity",
        "reference_fiber",
        requested=False,
        connectome_id="formal_connectome",
        connectome_role="formal",
    )
    sensitive = _endpoint(
        "sensitivity",
        "reference_fiber",
        requested=True,
        connectome_id="sensitive_connectome",
        connectome_role="sensitive",
        final_eligible=False,
    )
    catalog = (
        primary,
        fallback,
        execution,
        dependency_reference,
        dependency,
        no_final,
        formal_fiber,
        sensitive,
    )

    primary_input = _task(primary, "input_readiness", "EndpointInputRecord")
    primary_final = _task(
        primary,
        "final_realization",
        "FinalSelectionRecord",
        dependencies=(primary_input.task_id,),
    )
    primary_late_failure = _task(
        primary,
        "formal_permutation",
        "FormalResult",
        dependencies=(primary_final.task_id,),
    )
    fallback_input = _task(fallback, "input_readiness", "EndpointInputRecord")
    fallback_final = _task(
        fallback,
        "final_realization",
        "FinalSelectionRecord",
        dependencies=(fallback_input.task_id,),
    )
    execution_final = _task(execution, "final_realization", "FinalModelRecord")
    dependency_source = _task(
        dependency_reference, "source_resolver", "SourceRecord"
    )
    dependency_final = _task(
        dependency,
        "final_realization",
        "FinalModelRecord",
        dependencies=(dependency_source.task_id,),
    )
    no_final_input = _task(no_final, "input_readiness", "EndpointInputRecord")
    no_final_task = _task(
        no_final,
        "final_realization",
        "FinalSelectionRecord",
        dependencies=(no_final_input.task_id,),
    )
    formal_source = _task(formal_fiber, "source_resolver", "SourceRecord")
    sensitive_input = _task(sensitive, "input_readiness", "EndpointInputRecord")
    sensitive_evaluation = _task(
        sensitive,
        "formal_source_evaluation",
        "SensitiveRecord",
        dependencies=(formal_source.task_id, sensitive_input.task_id),
    )
    sensitive_late_failure = _task(
        sensitive,
        "sensitivity_followup",
        "SensitivityResult",
        dependencies=(sensitive_evaluation.task_id,),
    )
    tasks = (
        primary_input,
        primary_final,
        primary_late_failure,
        fallback_input,
        fallback_final,
        execution_final,
        dependency_source,
        dependency_final,
        no_final_input,
        no_final_task,
        formal_source,
        sensitive_input,
        sensitive_evaluation,
        sensitive_late_failure,
    )
    plan = ExecutionPlan(
        configuration_hash="configuration_hash",
        scientific_configuration_hash="scientific_configuration_hash",
        through="report",
        tasks=tasks,
    )

    subject_axis = AxisRef("included_subjects", 3, "1" * 64)
    baseline = _artifact("baseline_scores", "2" * 64, subject_axis)
    outcome = _artifact("outcome_scores", "3" * 64, subject_axis)
    envelope_only = _artifact("envelope_only", "4" * 64, subject_axis)
    primary_input_record = _input_record(primary, subject_axis, baseline, outcome)
    fallback_input_record = _input_record(fallback, subject_axis, baseline, outcome)
    no_final_input_record = _input_record(no_final, subject_axis, baseline, outcome)
    sensitive_input_record = _input_record(sensitive, subject_axis, baseline, outcome)
    primary_final_record = _reference_final(primary, "5" * 64)
    fallback_final_record = _fallback_final(fallback, "6" * 64)
    primary_selection = _realized_selection(primary_final_record)
    fallback_selection = _realized_selection(fallback_final_record)
    no_final_selection = _no_final_selection(no_final)
    formal_source_record = _source(formal_fiber, "7" * 64)
    sensitive_artifact = _artifact(
        "sensitive_scores",
        "8" * 64,
        formal_source_record.feature_axis.axis,
    )
    sensitive_record = SensitiveRecord(
        endpoint=sensitive.key,
        formal_endpoint_id=formal_fiber.endpoint_id,
        evaluated_tau=0.5,
        evaluated_coverage=2,
        input_status="valid",
        cell_computability_status="computable",
        prediction_status="error_nonpredictive",
        feature_axis=formal_source_record.feature_axis,
        artifacts=(sensitive_artifact,),
    )

    completed_records = {
        primary_input.task_id: primary_input_record,
        primary_final.task_id: primary_selection,
        fallback_input.task_id: fallback_input_record,
        fallback_final.task_id: fallback_selection,
        no_final_input.task_id: no_final_input_record,
        no_final_task.task_id: no_final_selection,
        formal_source.task_id: formal_source_record,
        sensitive_input.task_id: sensitive_input_record,
        sensitive_evaluation.task_id: sensitive_record,
    }
    outcomes = (
        _completed(primary_input, primary_input_record),
        _completed(primary_final, primary_selection),
        _terminal(primary_late_failure, "failed", "synthetic_late_failure"),
        _completed(fallback_input, fallback_input_record),
        _completed(fallback_final, fallback_selection),
        _terminal(execution_final, "failed", "synthetic_execution_failure"),
        _terminal(dependency_source, "failed", "synthetic_dependency_failure"),
        _terminal(
            dependency_final,
            "skipped",
            f"dependency_failure:{dependency_source.task_id}",
        ),
        _completed(no_final_input, no_final_input_record),
        _completed(no_final_task, no_final_selection),
        _completed(formal_source, formal_source_record),
        _completed(sensitive_input, sensitive_input_record),
        _completed(sensitive_evaluation, sensitive_record),
        _terminal(
            sensitive_late_failure,
            "failed",
            "synthetic_sensitive_followup_failure",
        ),
    )
    return ReportingFixture(
        plan=plan,
        catalog=catalog,
        result=RunResult("run_1", outcomes, exit_code=1),
        records=completed_records,
        envelope_only=envelope_only,
    )


class FinalDecisionTest(unittest.TestCase):
    def test_precedence_and_sensitive_override_are_deterministic(self) -> None:
        fixture = _build_fixture()
        decisions = aggregate_final_decisions(
            fixture.plan, fixture.catalog, fixture.result, fixture.records
        )
        reverse = aggregate_final_decisions(
            fixture.plan,
            fixture.catalog,
            RunResult(
                fixture.result.run_id,
                tuple(reversed(fixture.result.outcomes)),
                fixture.result.exit_code,
            ),
            dict(reversed(tuple(fixture.records.items()))),
        )
        self.assertEqual(decisions, reverse)
        by_scale_family_connectome = {
            (
                item.endpoint.scale_id,
                item.endpoint.model_family,
                item.endpoint.connectome_id,
            ): item
            for item in decisions
        }
        primary = by_scale_family_connectome[("primary", "reference_voxel", "none")]
        fallback = by_scale_family_connectome[("primary", "addon_voxel", "none")]
        execution = by_scale_family_connectome[("execution", "reference_voxel", "none")]
        dependency = by_scale_family_connectome[("dependency", "addon_voxel", "none")]
        no_final = by_scale_family_connectome[("no_final", "reference_voxel", "none")]
        sensitive = by_scale_family_connectome[
            ("sensitivity", "reference_fiber", "sensitive_connectome")
        ]
        self.assertEqual(primary.decision_status, "realized_primary")
        self.assertEqual(fallback.decision_status, "realized_fallback")
        self.assertEqual(execution.decision_status, "execution_failure")
        self.assertEqual(dependency.decision_status, "dependency_failure")
        self.assertEqual(no_final.decision_status, "no_final_model")
        self.assertEqual(sensitive.decision_status, "no_final_model")
        self.assertEqual(
            sensitive.reason_code,
            "not_final_eligible_sensitive_connectome",
        )
        self.assertIsNone(sensitive.final_model)
        self.assertEqual(len(decisions), 6)

    def test_final_decision_contract_rejects_status_mismatch(self) -> None:
        fixture = _build_fixture()
        final = next(
            record.final_model
            for record in fixture.records.values()
            if isinstance(record, FinalSelectionRecord)
            and record.selection_status == "final_model_realized"
        )
        self.assertIsNotNone(final)
        with self.assertRaisesRegex(RecordError, "must agree"):
            FinalDecisionRecord(
                endpoint=final.endpoint,
                decision_status="realized_fallback",
                final_model=final,
                reason_code="mismatch",
                causal_task_ids=(),
            )


class ReportingDocumentsTest(unittest.TestCase):
    def test_individualized_endpoint_reports_its_own_representation(self) -> None:
        endpoint = _endpoint(
            "individualized",
            "reference_individualized",
            requested=True,
        )
        plan = ExecutionPlan(
            configuration_hash="a" * 64,
            scientific_configuration_hash="b" * 64,
            through="report",
            tasks=(),
        )
        summary = build_endpoint_summary(
            plan,
            (endpoint,),
            RunResult("representation-run", (), 0),
            {},
        )

        self.assertEqual(
            summary["endpoints"][0]["representation"],
            "individualized_seed_target",
        )

    def test_endpoint_and_run_reports_use_reference_addon_vocabulary(self) -> None:
        fixture = _build_fixture()
        endpoint_summary = build_endpoint_summary(
            fixture.plan, fixture.catalog, fixture.result, fixture.records
        )
        primary_row = next(
            row
            for row in endpoint_summary["endpoints"]
            if row["endpoint"]["scale_id"] == "primary"
            and row["component_role"] == "reference"
        )
        self.assertEqual(primary_row["candidate_subject_count"], 4)
        self.assertEqual(primary_row["included_subject_count"], 3)
        self.assertEqual(primary_row["excluded_subject_count"], 1)
        self.assertEqual(
            primary_row["exclusion_reason_counts"],
            [{"reason_code": "missing_addon_exposure", "count": 1}],
        )
        execution_row = next(
            row
            for row in endpoint_summary["endpoints"]
            if row["endpoint"]["scale_id"] == "execution"
        )
        self.assertIsNone(execution_row["candidate_subject_count"])
        self.assertIsNone(execution_row["included_subject_count"])
        self.assertIsNone(execution_row["excluded_subject_count"])

        sensitive_row = next(
            row
            for row in endpoint_summary["endpoints"]
            if row["connectome_role"] == "sensitive"
        )
        self.assertIsNone(sensitive_row["decision"]["final_model_id"])
        self.assertIsNone(sensitive_row["final_model"])
        self.assertEqual(
            sensitive_row["sensitivity_evidence"][0]["evidence_status"],
            "recorded",
        )
        self.assertIsNone(
            sensitive_row["sensitivity_evidence"][0]["final_model_id"]
        )

        run_report = build_run_report(
            fixture.plan, fixture.catalog, fixture.result, fixture.records
        )
        self.assertEqual(len(run_report["final_models"]), 2)
        self.assertTrue(
            all(row["connectome_role"] != "sensitive" for row in run_report["final_models"])
        )
        self.assertEqual(len(run_report["sensitivity_evidence"]), 1)
        self.assertIsNone(run_report["sensitivity_evidence"][0]["final_model_id"])
        serialized = json.dumps(
            {"endpoint": endpoint_summary, "run": run_report},
            sort_keys=True,
            allow_nan=False,
        ).lower()
        self.assertNotIn('"hf"', serialized)
        self.assertNotIn('"ulf"', serialized)
        self.assertNotIn("summary/spot", serialized)

    def test_document_bundle_has_only_the_four_publication_documents(self) -> None:
        fixture = _build_fixture()
        documents = build_report_documents(
            fixture.plan, fixture.catalog, fixture.result, fixture.records
        )
        self.assertEqual(
            set(documents),
            {
                "final_decisions.json",
                "endpoint_summary.json",
                "run_report.json",
                "artifact_index.json",
            },
        )
        json.dumps(documents, sort_keys=True, allow_nan=False)

    def test_lower_cutoff_emits_only_technical_terminal_documents(self) -> None:
        fixture = _build_fixture()
        observed_plan = ExecutionPlan(
            configuration_hash=fixture.plan.configuration_hash,
            scientific_configuration_hash=fixture.plan.scientific_configuration_hash,
            through="observed",
            tasks=fixture.plan.tasks,
        )
        documents = build_report_documents(
            observed_plan,
            fixture.catalog,
            fixture.result,
            fixture.records,
        )
        self.assertEqual(
            set(documents),
            {"final_decisions.json", "artifact_index.json"},
        )
        with self.assertRaisesRegex(ReportingError, "report execution cutoff"):
            build_endpoint_summary(
                observed_plan,
                fixture.catalog,
                fixture.result,
                fixture.records,
            )


class ArtifactIndexTest(unittest.TestCase):
    def test_index_uses_typed_record_closure_and_rejects_envelope_drift(self) -> None:
        fixture = _build_fixture()
        forward = build_artifact_index(
            fixture.plan, fixture.catalog, fixture.result, fixture.records
        )
        reverse = build_artifact_index(
            fixture.plan,
            fixture.catalog,
            RunResult(
                fixture.result.run_id,
                tuple(reversed(fixture.result.outcomes)),
                fixture.result.exit_code,
            ),
            dict(reversed(tuple(fixture.records.items()))),
        )
        self.assertEqual(forward, reverse)
        artifact_ids = {item["artifact_id"] for item in forward["artifacts"]}
        self.assertNotIn(fixture.envelope_only.identifier, artifact_ids)
        baseline = next(
            item for item in forward["artifacts"] if item["kind"] == "baseline_scores"
        )
        self.assertGreater(len(baseline["task_references"]), 1)

        first = fixture.result.outcomes[0]
        self.assertIsNotNone(first.result)
        drifted = TaskOutcome(
            task_id=first.task_id,
            endpoint_id=first.endpoint_id,
            service_id=first.service_id,
            status="completed",
            reason="none",
            result=ServiceResult(
                output_record_type=first.result.output_record_type,
                record_id=first.result.record_id,
                payload_json=first.result.payload_json,
                artifacts=(fixture.envelope_only,),
            ),
        )
        drifted_result = RunResult(
            fixture.result.run_id,
            (drifted, *fixture.result.outcomes[1:]),
            fixture.result.exit_code,
        )
        with self.assertRaisesRegex(ArtifactIndexError, "artifact closure mismatch"):
            build_artifact_index(
                fixture.plan,
                fixture.catalog,
                drifted_result,
                fixture.records,
            )

    def test_duplicate_outcomes_and_missing_records_are_rejected(self) -> None:
        fixture = _build_fixture()
        duplicated = RunResult(
            fixture.result.run_id,
            fixture.result.outcomes + (fixture.result.outcomes[0],),
            fixture.result.exit_code,
        )
        with self.assertRaisesRegex(ArtifactIndexError, "duplicate task outcome"):
            build_artifact_index(
                fixture.plan, fixture.catalog, duplicated, fixture.records
            )
        incomplete = dict(fixture.records)
        incomplete.pop(next(iter(incomplete)))
        with self.assertRaisesRegex(ArtifactIndexError, "exactly cover completed"):
            build_artifact_index(
                fixture.plan, fixture.catalog, fixture.result, incomplete
            )

    def test_requires_typed_aggregate_inputs(self) -> None:
        fixture = _build_fixture()
        with self.assertRaisesRegex(TypeError, "ExecutionPlan"):
            build_artifact_index(
                {}, fixture.catalog, fixture.result, fixture.records
            )
        with self.assertRaisesRegex(TypeError, "RunResult"):
            build_artifact_index(
                fixture.plan, fixture.catalog, {}, fixture.records
            )


if __name__ == "__main__":
    unittest.main()
