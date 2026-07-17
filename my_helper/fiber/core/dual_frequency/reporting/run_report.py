"""Run-level reporting assembled from terminal records and endpoint decisions."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from ..catalog import EndpointRecord
from ..workflow import ExecutionPlan, RunResult
from .artifact_index import ReportingError, build_artifact_index
from .endpoint_summary import (
    DECISION_STATUSES,
    FinalDecisionRecord,
    _decision_payload,
    aggregate_final_decisions,
    build_endpoint_summary,
    final_decisions_document,
)


def _validated_decisions(
    endpoint_catalog: Sequence[EndpointRecord],
    decisions: Sequence[FinalDecisionRecord],
) -> tuple[FinalDecisionRecord, ...]:
    values = tuple(decisions)
    if not all(isinstance(item, FinalDecisionRecord) for item in values):
        raise TypeError("decisions must contain only FinalDecisionRecord values")
    requested_ids = {
        endpoint.endpoint_id for endpoint in endpoint_catalog if endpoint.requested
    }
    actual_ids = {decision.endpoint.identifier for decision in values}
    if len(actual_ids) != len(values) or actual_ids != requested_ids:
        raise ReportingError(
            "final decisions must exactly and uniquely cover requested endpoints"
        )
    return tuple(sorted(values, key=lambda item: item.endpoint.identifier))


def _run_report_from_documents(
    plan: ExecutionPlan,
    run_result: RunResult,
    decisions: Sequence[FinalDecisionRecord],
    endpoint_summary: Mapping[str, Any],
    artifact_index: Mapping[str, Any],
) -> dict[str, Any]:
    decision_counts = Counter(item.decision_status for item in decisions)
    task_counts = Counter(outcome.status for outcome in run_result.outcomes)
    endpoint_rows = endpoint_summary["endpoints"]
    final_models = [
        {
            "endpoint_id": row["endpoint_id"],
            "component_role": row["component_role"],
            "representation": row["representation"],
            "connectome_role": row["connectome_role"],
            **row["final_model"],
        }
        for row in endpoint_rows
        if row["final_model"] is not None
    ]
    sensitivity_evidence = [
        {
            "endpoint_id": row["endpoint_id"],
            "component_role": row["component_role"],
            "representation": row["representation"],
            "connectome_role": row["connectome_role"],
            **evidence,
        }
        for row in endpoint_rows
        for evidence in row["sensitivity_evidence"]
    ]
    return {
        "schema_version": "dual_frequency_run_report_v1",
        "run_id": run_result.run_id,
        "configuration_hash": plan.configuration_hash,
        "scientific_configuration_hash": plan.scientific_configuration_hash,
        "through": plan.through,
        "technical_status": "failed" if task_counts.get("failed", 0) else "completed",
        "exit_code": run_result.exit_code,
        "task_status_counts": {
            status: task_counts.get(status, 0)
            for status in ("completed", "failed", "skipped")
        },
        "requested_endpoint_count": len(decisions),
        "decision_status_counts": {
            status: decision_counts.get(status, 0) for status in sorted(DECISION_STATUSES)
        },
        "artifact_count": len(artifact_index["artifacts"]),
        "endpoint_decisions": [_decision_payload(item) for item in decisions],
        "final_models": final_models,
        "sensitivity_evidence": sensitivity_evidence,
    }


def build_run_report(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
    *,
    decisions: Sequence[FinalDecisionRecord] | None = None,
) -> dict[str, Any]:
    """Build a deterministic run report without reconstructing model outputs."""

    if not isinstance(plan, ExecutionPlan):
        raise TypeError("plan must be an ExecutionPlan")
    if plan.through != "report":
        raise ReportingError("run report requires the report execution cutoff")
    decision_values = _validated_decisions(
        endpoint_catalog,
        aggregate_final_decisions(
            plan, endpoint_catalog, run_result, typed_records
        )
        if decisions is None
        else decisions,
    )
    endpoint_document = build_endpoint_summary(
        plan,
        endpoint_catalog,
        run_result,
        typed_records,
        decisions=decision_values,
    )
    artifact_document = build_artifact_index(
        plan, endpoint_catalog, run_result, typed_records
    )
    return _run_report_from_documents(
        plan,
        run_result,
        decision_values,
        endpoint_document,
        artifact_document,
    )


def build_report_documents(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
    *,
    external_causal_task_ids: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """Build current-run documents permitted by the execution cutoff."""

    decisions = aggregate_final_decisions(
        plan,
        endpoint_catalog,
        run_result,
        typed_records,
        external_causal_task_ids=external_causal_task_ids,
    )
    artifact_document = build_artifact_index(
        plan, endpoint_catalog, run_result, typed_records
    )
    documents = {
        "final_decisions.json": final_decisions_document(run_result.run_id, decisions),
        "artifact_index.json": artifact_document,
    }
    if plan.through != "report":
        return documents

    endpoint_document = build_endpoint_summary(
        plan,
        endpoint_catalog,
        run_result,
        typed_records,
        decisions=decisions,
    )
    run_document = _run_report_from_documents(
        plan,
        run_result,
        decisions,
        endpoint_document,
        artifact_document,
    )
    documents["endpoint_summary.json"] = endpoint_document
    documents["run_report.json"] = run_document
    return documents


build_reporting_documents = build_report_documents


__all__ = [
    "build_report_documents",
    "build_reporting_documents",
    "build_run_report",
]
