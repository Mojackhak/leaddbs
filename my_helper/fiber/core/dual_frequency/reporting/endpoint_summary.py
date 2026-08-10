"""Pure terminal decisions and endpoint summaries for completed executions."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from ..catalog import CatalogStatus, EndpointRecord
from ..contracts import (
    BranchRecord,
    EndpointInputRecord,
    FinalDecisionRecord,
    FinalModelRecord,
    FinalSelectionRecord,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SourceRecord,
)
from ..workflow import ExecutionPlan, RunResult, TaskOutcome, TaskSpec
from .artifact_index import (
    ReportingError,
    _ReportingInputs,
    _validate_reporting_inputs,
    record_artifact_closure,
)


DECISION_STATUSES = frozenset(
    {
        "realized_primary",
        "realized_fallback",
        "no_final_model",
        "dependency_failure",
        "execution_failure",
    }
)


def _decision_payload(decision: FinalDecisionRecord) -> dict[str, Any]:
    final_model_record_id = (
        decision.final_model.identifier if decision.final_model is not None else None
    )
    final_model_id = (
        decision.final_model.final_key.identifier
        if decision.final_model is not None
        and decision.final_model.final_key is not None
        else None
    )
    return {
        "decision_id": decision.identifier,
        "endpoint_id": decision.endpoint.identifier,
        "decision_status": decision.decision_status,
        "reason_code": decision.reason_code,
        "final_model_record_id": final_model_record_id,
        "final_model_id": final_model_id,
        "causal_task_ids": list(decision.causal_task_ids),
    }


def _records_for_endpoint(
    inputs: _ReportingInputs,
    endpoint_id: str,
    record_type: type[object] | None = None,
) -> tuple[tuple[str, object], ...]:
    output = []
    for task_id, record in inputs.typed_records.items():
        if inputs.outcomes[task_id].endpoint_id != endpoint_id:
            continue
        if record_type is not None and not isinstance(record, record_type):
            continue
        output.append((task_id, record))
    return tuple(sorted(output, key=lambda item: item[0]))


def _local_tasks(inputs: _ReportingInputs, endpoint_id: str) -> tuple[TaskSpec, ...]:
    return tuple(task for task in inputs.plan.tasks if task.endpoint_id == endpoint_id)


def _dependency_reason_task_ids(
    reason: str,
    inputs: _ReportingInputs,
) -> tuple[str, ...]:
    if not reason.startswith("dependency_failure"):
        return ()
    _, separator, suffix = reason.partition(":")
    if not separator:
        return ()
    task_ids = tuple(item for item in suffix.split(",") if item in inputs.tasks)
    return tuple(sorted(set(task_ids)))


def _root_failure_ids(
    task_id: str,
    inputs: _ReportingInputs,
    visited: set[str] | None = None,
) -> set[str]:
    seen = set() if visited is None else visited
    if task_id in seen:
        return set()
    seen.add(task_id)
    outcome = inputs.outcomes[task_id]
    if outcome.status == "failed":
        return {task_id}
    if outcome.status != "skipped" or not outcome.reason.startswith(
        "dependency_failure"
    ):
        return set()
    referenced = _dependency_reason_task_ids(outcome.reason, inputs)
    if not referenced:
        referenced = inputs.tasks[task_id].dependencies
    failures: set[str] = set()
    for dependency_id in referenced:
        failures.update(_root_failure_ids(dependency_id, inputs, seen))
    return failures


def _dependency_failure(
    endpoint: EndpointRecord,
    inputs: _ReportingInputs,
) -> tuple[str, tuple[str, ...]] | None:
    selection_records = tuple(
        (task_id, record)
        for task_id, record in _records_for_endpoint(
            inputs, endpoint.endpoint_id, FinalSelectionRecord
        )
    )
    if len(selection_records) > 1:
        raise ReportingError(
            f"endpoint {endpoint.endpoint_id!r} has multiple final selections"
        )
    if selection_records:
        task_id, selection = selection_records[0]
        if selection.selection_status == "dependency_failure":
            causal = selection.causal_task_ids or (task_id,)
            return selection.reason_codes[0], tuple(sorted(causal))

    dependency_records = tuple(
        (task_id, record)
        for task_id, record in _records_for_endpoint(inputs, endpoint.endpoint_id)
        if isinstance(record, ReferenceDependencyRecord)
        and record.dependency_status != "ready"
    )
    if dependency_records:
        statuses = {record.dependency_status for _, record in dependency_records}
        if len(statuses) != 1:
            raise ReportingError(
                f"endpoint {endpoint.endpoint_id!r} has contradictory dependency states"
            )
        return (
            f"reference_dependency_{next(iter(statuses))}",
            tuple(sorted(task_id for task_id, _ in dependency_records)),
        )

    external_failures: set[str] = set()
    for task in _local_tasks(inputs, endpoint.endpoint_id):
        outcome = inputs.outcomes[task.task_id]
        if outcome.status == "skipped" and outcome.reason.startswith(
            "dependency_failure"
        ):
            external_failures.update(_root_failure_ids(task.task_id, inputs))
        for dependency_id in task.dependencies:
            dependency_task = inputs.tasks[dependency_id]
            if dependency_task.endpoint_id != endpoint.endpoint_id:
                external_failures.update(
                    _root_failure_ids(dependency_id, inputs)
                )
    external_failures = {
        task_id
        for task_id in external_failures
        if inputs.tasks[task_id].endpoint_id != endpoint.endpoint_id
    }
    if external_failures:
        return "cross_endpoint_execution_failure", tuple(sorted(external_failures))

    matched_reference_id = endpoint.matched_reference_endpoint_id
    if matched_reference_id is not None:
        matched = inputs.endpoints[matched_reference_id]
        if matched.status != CatalogStatus.DATA_AVAILABLE:
            return f"matched_reference_{matched.status.value}", ()
    return None


def _endpoint_input_record(
    inputs: _ReportingInputs,
    endpoint_id: str,
) -> tuple[str, EndpointInputRecord] | None:
    matches = tuple(
        (task_id, record)
        for task_id, record in _records_for_endpoint(inputs, endpoint_id)
        if isinstance(record, EndpointInputRecord)
    )
    if len(matches) > 1:
        raise ReportingError(
            f"endpoint {endpoint_id!r} has multiple EndpointInputRecord values"
        )
    return matches[0] if matches else None


def _cohort_payload(
    endpoint: EndpointRecord,
    inputs: _ReportingInputs,
) -> dict[str, Any]:
    match = _endpoint_input_record(inputs, endpoint.endpoint_id)
    if match is None:
        return {
            "input_record_id": None,
            "readiness_status": "not_available",
            "candidate_subject_count": None,
            "included_subject_count": None,
            "excluded_subject_count": None,
            "exclusion_reason_counts": [],
        }
    task_id, record = match
    outcome = inputs.outcomes[task_id]
    if outcome.result is None:
        raise ReportingError("completed endpoint input task lacks a service result")
    if record.endpoint != endpoint.key:
        raise ReportingError("EndpointInputRecord endpoint does not match its task")
    if record.candidate_subject_ids != endpoint.subject_ids:
        raise ReportingError(
            "EndpointInputRecord candidates must match the endpoint catalog"
        )
    if record.minimum_subjects != endpoint.minimum_subjects:
        raise ReportingError(
            "EndpointInputRecord minimum_subjects must match the endpoint catalog"
        )
    reason_counts = Counter(exclusion.reason_code for exclusion in record.exclusions)
    return {
        "input_record_id": outcome.result.record_id,
        "readiness_status": record.readiness_status,
        "candidate_subject_count": len(record.candidate_subject_ids),
        "included_subject_count": len(record.included_subject_ids),
        "excluded_subject_count": len(record.exclusions),
        "exclusion_reason_counts": [
            {"reason_code": reason_code, "count": reason_counts[reason_code]}
            for reason_code in sorted(reason_counts)
        ],
    }


def _no_final_reason(endpoint: EndpointRecord, inputs: _ReportingInputs) -> str:
    if endpoint.status != CatalogStatus.DATA_AVAILABLE:
        return f"catalog_{endpoint.status.value}"
    selection_records = tuple(
        record
        for _, record in _records_for_endpoint(
            inputs, endpoint.endpoint_id, FinalSelectionRecord
        )
    )
    if len(selection_records) > 1:
        raise ReportingError(
            f"endpoint {endpoint.endpoint_id!r} has multiple final selections"
        )
    if selection_records and selection_records[0].selection_status == "no_final_model":
        return selection_records[0].reason_codes[0]
    input_match = _endpoint_input_record(inputs, endpoint.endpoint_id)
    if input_match is not None:
        readiness = input_match[1].readiness_status
        if readiness and readiness not in {"ready", "valid", "data_available"}:
            return f"endpoint_input_{readiness}"

    source_records = tuple(
        record
        for _, record in _records_for_endpoint(
            inputs, endpoint.endpoint_id, SourceRecord
        )
    )
    absent_statuses = sorted(
        {record.source_status for record in source_records if record.source_status not in {
            "pre_specified_accepted",
            "scan_fallback_accepted",
        }}
    )
    if absent_statuses:
        return absent_statuses[0]
    branch_records = tuple(
        record
        for _, record in _records_for_endpoint(
            inputs, endpoint.endpoint_id, BranchRecord
        )
    )
    if branch_records and not any(
        record.source is not None
        and record.source.source_status
        in {"pre_specified_accepted", "scan_fallback_accepted"}
        for record in branch_records
    ):
        return "no_accepted_branch_source"

    skip_reasons = {
        "no_final_model": "no_final_model",
        "not_run_no_final_model": "no_final_model",
        "not_run_reference_source_absent": "reference_source_absent",
        "not_run_delta_inputs_invalid": "delta_inputs_invalid",
        "not_run_catalog_unavailable": "catalog_unavailable",
        "not_run_reference_dependency_failure": "reference_dependency_failure",
        "not_run_batch_aborted": "batch_aborted",
    }
    for task in _local_tasks(inputs, endpoint.endpoint_id):
        if task.stage != "final_realization":
            continue
        outcome = inputs.outcomes[task.task_id]
        if outcome.status == "skipped" and outcome.reason in skip_reasons:
            return skip_reasons[outcome.reason]
    return "no_final_model"


def aggregate_final_decisions(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
    *,
    external_causal_task_ids: Sequence[str] = (),
) -> tuple[FinalDecisionRecord, ...]:
    """Build one deterministic terminal decision for every requested endpoint."""

    inputs = _validate_reporting_inputs(
        plan, endpoint_catalog, run_result, typed_records
    )
    plan_task_ids = set(inputs.tasks)
    external_task_ids = {str(task_id) for task_id in external_causal_task_ids}
    if "" in external_task_ids:
        raise ReportingError("external causal task IDs must be nonempty")
    allowed_causal_task_ids = plan_task_ids | external_task_ids
    decisions = []
    for endpoint in sorted(
        (item for item in inputs.catalog if item.requested),
        key=lambda item: item.endpoint_id,
    ):
        if endpoint.connectome_role == "sensitive":
            decision = FinalDecisionRecord(
                endpoint=endpoint.key,
                decision_status="no_final_model",
                final_model=None,
                reason_code="not_final_eligible_sensitive_connectome",
                causal_task_ids=(),
            )
            decisions.append(decision)
            continue

        selection_records = tuple(
            (task_id, record)
            for task_id, record in _records_for_endpoint(
                inputs, endpoint.endpoint_id, FinalSelectionRecord
            )
        )
        if len(selection_records) > 1:
            raise ReportingError(
                f"endpoint {endpoint.endpoint_id!r} has multiple final selections"
            )
        root_final_records = tuple(
            (task_id, record)
            for task_id, record in _records_for_endpoint(
                inputs, endpoint.endpoint_id, FinalModelRecord
            )
        )
        final_candidates: dict[str, tuple[FinalModelRecord, set[str]]] = {}
        for task_id, final_model in root_final_records:
            final_candidates.setdefault(
                final_model.identifier, (final_model, set())
            )[1].add(task_id)
        if selection_records:
            task_id, selection = selection_records[0]
            if selection.final_model is not None:
                _, causal_task_ids = final_candidates.setdefault(
                    selection.final_model.identifier,
                    (selection.final_model, set()),
                )
                causal_task_ids.add(task_id)
                causal_task_ids.update(selection.causal_task_ids)
        if len(final_candidates) > 1:
            raise ReportingError(
                f"endpoint {endpoint.endpoint_id!r} has multiple realized finals"
            )
        if final_candidates:
            final_model, final_task_ids = next(iter(final_candidates.values()))
            if not endpoint.final_eligible:
                raise ReportingError(
                    f"endpoint {endpoint.endpoint_id!r} is not final eligible"
                )
            status = (
                "realized_primary"
                if final_model.final_status == "final_model_realized"
                else "realized_fallback"
            )
            decision = FinalDecisionRecord(
                endpoint=endpoint.key,
                decision_status=status,
                final_model=final_model,
                reason_code=final_model.final_status,
                causal_task_ids=tuple(sorted(final_task_ids)),
            )
            decisions.append(decision)
            continue

        local_failed = tuple(
            sorted(
                task.task_id
                for task in _local_tasks(inputs, endpoint.endpoint_id)
                if inputs.outcomes[task.task_id].status == "failed"
            )
        )
        if local_failed:
            decisions.append(
                FinalDecisionRecord(
                    endpoint=endpoint.key,
                    decision_status="execution_failure",
                    final_model=None,
                    reason_code="endpoint_execution_failure",
                    causal_task_ids=local_failed,
                )
            )
            continue

        if selection_records:
            task_id, selection = selection_records[0]
            if selection.selection_status == "execution_failure":
                decisions.append(
                    FinalDecisionRecord(
                        endpoint=endpoint.key,
                        decision_status="execution_failure",
                        final_model=None,
                        reason_code=selection.reason_codes[0],
                        causal_task_ids=selection.causal_task_ids or (task_id,),
                    )
                )
                continue

        dependency_failure = _dependency_failure(endpoint, inputs)
        if dependency_failure is not None:
            reason_code, causal_task_ids = dependency_failure
            decisions.append(
                FinalDecisionRecord(
                    endpoint=endpoint.key,
                    decision_status="dependency_failure",
                    final_model=None,
                    reason_code=reason_code,
                    causal_task_ids=causal_task_ids,
                )
            )
            continue

        no_final_tasks = tuple(
            sorted(
                task.task_id
                for task in _local_tasks(inputs, endpoint.endpoint_id)
                if task.stage == "final_realization"
                and inputs.outcomes[task.task_id].status == "skipped"
            )
        )
        if selection_records:
            selection_task_id, selection = selection_records[0]
            if selection.selection_status not in {
                "no_final_model",
                "dependency_failure",
            }:
                raise ReportingError(
                    f"unsupported non-realized final selection {selection.selection_status!r}"
                )
            no_final_tasks = tuple(
                sorted(selection.causal_task_ids or (selection_task_id,))
            )
        decisions.append(
            FinalDecisionRecord(
                endpoint=endpoint.key,
                decision_status="no_final_model",
                final_model=None,
                reason_code=_no_final_reason(endpoint, inputs),
                causal_task_ids=no_final_tasks,
            )
        )

    for decision in decisions:
        if not set(decision.causal_task_ids).issubset(allowed_causal_task_ids):
            raise ReportingError(
                "decision causal task IDs must belong to the plan or declared parent lineage"
            )
    return tuple(decisions)


def final_decisions_document(
    run_id: str,
    decisions: Sequence[FinalDecisionRecord],
) -> dict[str, Any]:
    """Return the JSON-safe aggregate document for terminal decisions."""

    decision_values = tuple(decisions)
    if not all(isinstance(item, FinalDecisionRecord) for item in decision_values):
        raise TypeError("decisions must contain only FinalDecisionRecord values")
    endpoint_ids = [item.endpoint.identifier for item in decision_values]
    if len(set(endpoint_ids)) != len(endpoint_ids):
        raise ReportingError("terminal decisions must be unique by endpoint")
    ordered = sorted(decision_values, key=lambda item: item.endpoint.identifier)
    return {
        "schema_version": "dual_frequency_final_decisions_v1",
        "run_id": str(run_id),
        "decisions": [_decision_payload(item) for item in ordered],
    }


def _terminal_reason(outcome: TaskOutcome) -> str:
    if outcome.status == "completed":
        return "none"
    if outcome.status == "failed":
        return "execution_failure"
    if outcome.reason.startswith("dependency_failure"):
        return "dependency_failure"
    safe_skip_reasons = {
        "no_final_model",
        "not_run_batch_aborted",
        "not_run_catalog_unavailable",
        "not_run_delta_inputs_invalid",
        "not_run_formal_incomplete",
        "not_run_formal_source_unavailable",
        "not_run_no_final_model",
        "not_run_reference_dependency_failure",
        "not_run_reference_source_absent",
    }
    return outcome.reason if outcome.reason in safe_skip_reasons else "skipped"


def _task_rows(inputs: _ReportingInputs, endpoint_id: str) -> list[dict[str, Any]]:
    rows = []
    for task in _local_tasks(inputs, endpoint_id):
        outcome = inputs.outcomes[task.task_id]
        record = inputs.typed_records.get(task.task_id)
        artifact_ids = (
            [artifact.identifier for artifact in record_artifact_closure(record)]
            if record is not None
            else []
        )
        rows.append(
            {
                "task_id": task.task_id,
                "stage": task.stage,
                "round_id": task.round_id,
                "phase": task.phase,
                "service_id": task.service_id,
                "status": outcome.status,
                "reason_code": _terminal_reason(outcome),
                "output_record_type": task.output_record_type,
                "record_id": (
                    outcome.result.record_id if outcome.result is not None else None
                ),
                "artifact_ids": artifact_ids,
            }
        )
    return rows


def _final_model_payload(decision: FinalDecisionRecord) -> dict[str, Any] | None:
    final_model = decision.final_model
    if final_model is None or final_model.final_key is None:
        return None
    source = final_model.selected_source
    branch = final_model.selected_branch
    if source is None and branch is not None:
        source = branch.source
    return {
        "final_model_record_id": final_model.identifier,
        "final_model_id": final_model.final_key.identifier,
        "final_status": final_model.final_status,
        "realization_role": final_model.realization_role,
        "selected_branch": final_model.final_key.final_branch,
        "source_status": source.source_status if source is not None else None,
        "selected_tau": final_model.final_key.selected_tau,
        "selected_coverage": final_model.final_key.selected_coverage,
        "artifact_ids": [
            artifact.identifier for artifact in record_artifact_closure(final_model)
        ],
    }


def _sensitivity_evidence_payload(
    endpoint: EndpointRecord,
    inputs: _ReportingInputs,
    decision: FinalDecisionRecord,
) -> list[dict[str, Any]]:
    if endpoint.connectome_role != "sensitive":
        return []
    records = tuple(
        (task_id, record)
        for task_id, record in _records_for_endpoint(
            inputs, endpoint.endpoint_id, SensitiveRecord
        )
    )
    if len(records) > 1:
        raise ReportingError(
            f"sensitive endpoint {endpoint.endpoint_id!r} has multiple evidence records"
        )
    if not records:
        return [
            {
                "sensitivity_record_id": None,
                "evidence_status": "not_available",
                "formal_endpoint_id": None,
                "input_status": None,
                "cell_computability_status": None,
                "prediction_status": None,
                "evaluated_tau": None,
                "evaluated_coverage": None,
                "final_model_id": None,
                "artifact_ids": [],
                "causal_task_ids": list(decision.causal_task_ids),
            }
        ]
    task_id, record = records[0]
    return [
        {
            "sensitivity_record_id": record.identifier,
            "evidence_status": "recorded",
            "formal_endpoint_id": record.formal_endpoint_id,
            "input_status": record.input_status,
            "cell_computability_status": record.cell_computability_status,
            "prediction_status": record.prediction_status,
            "evaluated_tau": record.evaluated_tau,
            "evaluated_coverage": record.evaluated_coverage,
            "final_model_id": None,
            "artifact_ids": [
                artifact.identifier for artifact in record_artifact_closure(record)
            ],
            "causal_task_ids": [task_id],
        }
    ]


def build_endpoint_summary(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
    *,
    decisions: Sequence[FinalDecisionRecord] | None = None,
) -> dict[str, Any]:
    """Build requested endpoint summaries without numerical reconstruction."""

    inputs = _validate_reporting_inputs(
        plan, endpoint_catalog, run_result, typed_records
    )
    if plan.through != "report":
        raise ReportingError("endpoint summary requires the report execution cutoff")
    decision_values = (
        aggregate_final_decisions(plan, endpoint_catalog, run_result, typed_records)
        if decisions is None
        else tuple(decisions)
    )
    decision_by_endpoint = {
        decision.endpoint.identifier: decision for decision in decision_values
    }
    requested = tuple(item for item in inputs.catalog if item.requested)
    expected_endpoint_ids = {item.endpoint_id for item in requested}
    if set(decision_by_endpoint) != expected_endpoint_ids:
        raise ReportingError(
            "final decisions must exactly cover requested catalog endpoints"
        )

    endpoint_rows = []
    for endpoint in sorted(requested, key=lambda item: item.endpoint_id):
        decision = decision_by_endpoint[endpoint.endpoint_id]
        task_rows = _task_rows(inputs, endpoint.endpoint_id)
        task_counts = Counter(row["status"] for row in task_rows)
        endpoint_rows.append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "endpoint": endpoint.key.as_dict(),
                "component_role": (
                    "reference"
                    if endpoint.key.model_family.startswith("reference_")
                    else "addon"
                ),
                "representation": (
                    "direct_voxel"
                    if endpoint.key.model_family.endswith("voxel")
                    else "individualized_seed_target"
                    if endpoint.key.model_family.endswith("individualized")
                    else "normative_fiber"
                ),
                "scale_label": endpoint.scale_label,
                "scale_direction": endpoint.scale_direction,
                "baseline_binding_id": endpoint.baseline_binding_id,
                "outcome_binding_id": endpoint.outcome_binding_id,
                "matched_reference_endpoint_id": endpoint.matched_reference_endpoint_id,
                "connectome_role": endpoint.connectome_role,
                "catalog_status": endpoint.status.value,
                "final_eligible": endpoint.final_eligible,
                **_cohort_payload(endpoint, inputs),
                "decision": _decision_payload(decision),
                "final_model": _final_model_payload(decision),
                "sensitivity_evidence": _sensitivity_evidence_payload(
                    endpoint, inputs, decision
                ),
                "task_status_counts": {
                    status: task_counts.get(status, 0)
                    for status in ("completed", "failed", "skipped")
                },
                "tasks": task_rows,
            }
        )
    return {
        "schema_version": "dual_frequency_endpoint_summary_v1",
        "run_id": run_result.run_id,
        "configuration_hash": plan.configuration_hash,
        "scientific_configuration_hash": plan.scientific_configuration_hash,
        "through": plan.through,
        "endpoints": endpoint_rows,
    }


build_final_decisions = aggregate_final_decisions


__all__ = [
    "DECISION_STATUSES",
    "FinalDecisionRecord",
    "aggregate_final_decisions",
    "build_endpoint_summary",
    "build_final_decisions",
    "final_decisions_document",
]
