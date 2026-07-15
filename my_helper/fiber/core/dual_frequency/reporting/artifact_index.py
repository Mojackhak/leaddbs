"""Deterministic artifact indexing over codec-restored record closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..catalog import EndpointRecord
from ..contracts import ArtifactRef
from ..runtime import (
    RecordCodecError,
    record_artifacts,
    record_identifier,
)
from ..workflow import ExecutionError, ExecutionPlan, RunResult, TaskOutcome, TaskSpec


class ReportingError(ValueError):
    """Raised when a reporting snapshot is incomplete or inconsistent."""


class ArtifactIndexError(ReportingError):
    """Raised when typed artifact closure is internally inconsistent."""


@dataclass(frozen=True)
class _ReportingInputs:
    plan: ExecutionPlan
    catalog: tuple[EndpointRecord, ...]
    run_result: RunResult
    typed_records: Mapping[str, object]
    tasks: Mapping[str, TaskSpec]
    outcomes: Mapping[str, TaskOutcome]
    endpoints: Mapping[str, EndpointRecord]


def _validate_reporting_inputs(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
    *,
    error_type: type[ReportingError] = ReportingError,
) -> _ReportingInputs:
    if not isinstance(plan, ExecutionPlan):
        raise TypeError("plan must be an ExecutionPlan")
    if not isinstance(run_result, RunResult):
        raise TypeError("run_result must be a RunResult")
    if not str(run_result.run_id).strip():
        raise error_type("run_result run_id must be nonempty")
    if not isinstance(endpoint_catalog, Sequence) or isinstance(
        endpoint_catalog, (str, bytes)
    ):
        raise TypeError("endpoint_catalog must be a sequence of EndpointRecord values")
    catalog = tuple(endpoint_catalog)
    if not all(isinstance(endpoint, EndpointRecord) for endpoint in catalog):
        raise TypeError("endpoint_catalog must contain only EndpointRecord values")
    if not isinstance(typed_records, Mapping):
        raise TypeError("typed_records must map task IDs to restored typed records")
    if not all(type(task_id) is str for task_id in typed_records):
        raise TypeError("typed_records keys must be task ID strings")

    endpoints = {endpoint.endpoint_id: endpoint for endpoint in catalog}
    if len(endpoints) != len(catalog):
        raise error_type("endpoint catalog contains duplicate endpoint IDs")
    tasks = {task.task_id: task for task in plan.tasks}
    if len(tasks) != len(plan.tasks):
        raise error_type("execution plan contains duplicate task IDs")
    unknown_task_endpoints = sorted(
        task.task_id for task in plan.tasks if task.endpoint_id not in endpoints
    )
    if unknown_task_endpoints:
        raise error_type(
            "planned tasks reference endpoints outside the endpoint catalog: "
            f"{unknown_task_endpoints}"
        )

    outcomes: dict[str, TaskOutcome] = {}
    for outcome in run_result.outcomes:
        if not isinstance(outcome, TaskOutcome):
            raise error_type("run outcomes must contain only TaskOutcome values")
        if outcome.task_id in outcomes:
            raise error_type(f"duplicate task outcome {outcome.task_id!r}")
        outcomes[outcome.task_id] = outcome
    missing_outcomes = sorted(set(tasks) - set(outcomes))
    extra_outcomes = sorted(set(outcomes) - set(tasks))
    if missing_outcomes or extra_outcomes:
        raise error_type(
            "run outcomes must exactly cover the execution plan; "
            f"missing={missing_outcomes}, extra={extra_outcomes}"
        )
    for task_id, task in tasks.items():
        outcome = outcomes[task_id]
        if (
            outcome.endpoint_id != task.endpoint_id
            or outcome.service_id != task.service_id
        ):
            raise error_type(f"task outcome identity mismatch for {task_id!r}")
    expected_exit_code = 1 if any(
        outcome.status == "failed" for outcome in outcomes.values()
    ) else 0
    if run_result.exit_code != expected_exit_code:
        raise error_type("run_result exit_code does not match terminal task outcomes")

    completed_task_ids = {
        task_id for task_id, outcome in outcomes.items() if outcome.status == "completed"
    }
    record_task_ids = set(typed_records)
    if record_task_ids != completed_task_ids:
        raise error_type(
            "typed records must exactly cover completed tasks; "
            f"missing={sorted(completed_task_ids - record_task_ids)}, "
            f"extra={sorted(record_task_ids - completed_task_ids)}"
        )
    normalized_records: dict[str, object] = {}
    for task_id in sorted(completed_task_ids):
        record = typed_records[task_id]
        outcome = outcomes[task_id]
        if outcome.result is None:
            raise error_type(f"completed task {task_id!r} lacks a service result")
        task = tasks[task_id]
        if outcome.result.output_record_type != task.output_record_type:
            raise error_type(f"service result type does not match plan for {task_id!r}")
        record_type = type(record).__name__
        if record_type != outcome.result.output_record_type:
            raise error_type(
                f"typed record type mismatch for {task_id!r}: "
                f"{record_type!r} != {outcome.result.output_record_type!r}"
            )
        try:
            decoded_record = outcome.result.decode_record()
            identifier = record_identifier(record)
            artifact_closure = record_artifacts(record)
        except (ExecutionError, RecordCodecError) as exc:
            raise error_type(
                f"typed record for {task_id!r} is not a codec-restored root: {exc}"
            ) from exc
        if decoded_record != record:
            raise error_type(
                f"codec-restored record does not match typed_records for {task_id!r}"
            )
        if identifier != outcome.result.record_id:
            raise error_type(f"typed record identifier mismatch for {task_id!r}")
        if artifact_closure != outcome.result.artifacts:
            raise error_type(
                f"service result artifact closure mismatch for {task_id!r}"
            )
        normalized_records[task_id] = record

    for endpoint in catalog:
        reference_id = endpoint.matched_reference_endpoint_id
        if reference_id is not None and reference_id not in endpoints:
            raise error_type(
                f"endpoint {endpoint.endpoint_id!r} has an unknown matched reference"
            )

    return _ReportingInputs(
        plan=plan,
        catalog=catalog,
        run_result=run_result,
        typed_records=normalized_records,
        tasks=tasks,
        outcomes=outcomes,
        endpoints=endpoints,
    )


def record_artifact_closure(record: object) -> tuple[ArtifactRef, ...]:
    """Return the immutable ``ArtifactRef`` closure of one typed record."""

    try:
        artifacts = record_artifacts(record)
    except RecordCodecError as exc:
        raise ArtifactIndexError(str(exc)) from exc
    return tuple(sorted(artifacts, key=lambda artifact: artifact.identifier))


def _artifact_payload(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": artifact.identifier,
        "kind": artifact.kind,
        "schema_version": artifact.schema_version,
        "uri": artifact.uri,
        "sha256": artifact.sha256,
        "dtype": artifact.dtype,
        "shape": list(artifact.shape) if artifact.shape is not None else None,
        "axes": [
            {
                "axis_id": axis.axis_id,
                "count": axis.count,
                "sha256": axis.sha256,
            }
            for axis in artifact.axis_refs
        ],
        "units": artifact.units,
        "space": artifact.space,
        "producer_id": artifact.producer_id,
        "producer_version": artifact.producer_version,
    }


def _task_reference(inputs: _ReportingInputs, task_id: str) -> dict[str, str]:
    outcome = inputs.outcomes[task_id]
    if outcome.result is None:
        raise ArtifactIndexError("artifact references require a completed task result")
    return {
        "task_id": task_id,
        "endpoint_id": outcome.endpoint_id,
        "service_id": outcome.service_id,
        "output_record_type": outcome.result.output_record_type,
        "record_id": outcome.result.record_id,
    }


def build_artifact_index(
    plan: ExecutionPlan,
    endpoint_catalog: Sequence[EndpointRecord],
    run_result: RunResult,
    typed_records: Mapping[str, object],
) -> dict[str, Any]:
    """Build a JSON-safe index without inspecting artifact paths or envelopes."""

    inputs = _validate_reporting_inputs(
        plan,
        endpoint_catalog,
        run_result,
        typed_records,
        error_type=ArtifactIndexError,
    )
    indexed: dict[str, dict[str, Any]] = {}
    references: dict[str, dict[str, dict[str, str]]] = {}
    for task_id in sorted(inputs.typed_records):
        record = inputs.typed_records[task_id]
        reference = _task_reference(inputs, task_id)
        for artifact in record_artifact_closure(record):
            payload = _artifact_payload(artifact)
            artifact_id = artifact.identifier
            previous = indexed.get(artifact_id)
            if previous is not None and previous != payload:
                raise ArtifactIndexError(
                    f"artifact identifier collision for {artifact_id!r}"
                )
            indexed[artifact_id] = payload
            references.setdefault(artifact_id, {})[task_id] = reference

    artifacts = []
    for artifact_id in sorted(indexed):
        payload = dict(indexed[artifact_id])
        payload["task_references"] = [
            references[artifact_id][task_id]
            for task_id in sorted(references[artifact_id])
        ]
        artifacts.append(payload)
    return {
        "schema_version": "dual_frequency_artifact_index_v2",
        "run_id": run_result.run_id,
        "artifacts": artifacts,
    }


__all__ = [
    "ArtifactIndexError",
    "ReportingError",
    "build_artifact_index",
    "record_artifact_closure",
]
