"""Deterministic artifact indexing from current-run typed records only."""

from __future__ import annotations

from typing import Any

from ..contracts import ArtifactRef
from ..workflow.executor import RunResult, TaskOutcome


class ArtifactIndexError(ValueError):
    """Raised when current-run artifact records are internally inconsistent."""


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


def _task_reference(outcome: TaskOutcome) -> dict[str, str]:
    if outcome.result is None:
        raise ArtifactIndexError("artifact references require a completed task result")
    return {
        "task_id": outcome.task_id,
        "endpoint_id": outcome.endpoint_id,
        "service_id": outcome.service_id,
        "output_record_type": outcome.result.output_record_type,
        "record_id": outcome.result.record_id,
    }


def build_artifact_index(run_result: RunResult) -> dict[str, Any]:
    """Build one JSON-safe index without inspecting artifact paths or directories."""

    if not isinstance(run_result, RunResult):
        raise TypeError("run_result must be a RunResult")
    indexed: dict[str, dict[str, Any]] = {}
    references: dict[str, dict[str, dict[str, str]]] = {}
    seen_tasks: set[str] = set()
    for outcome in run_result.outcomes:
        if not isinstance(outcome, TaskOutcome):
            raise ArtifactIndexError("run outcomes must contain only TaskOutcome values")
        if outcome.task_id in seen_tasks:
            raise ArtifactIndexError(f"duplicate task outcome {outcome.task_id!r}")
        seen_tasks.add(outcome.task_id)
        if outcome.status != "completed":
            continue
        if outcome.result is None:
            raise ArtifactIndexError("completed task outcome lacks a service result")
        reference = _task_reference(outcome)
        for artifact in outcome.result.artifacts:
            payload = _artifact_payload(artifact)
            artifact_id = artifact.identifier
            previous = indexed.get(artifact_id)
            if previous is not None and previous != payload:
                raise ArtifactIndexError(
                    f"artifact identifier collision for {artifact_id!r}"
                )
            indexed[artifact_id] = payload
            references.setdefault(artifact_id, {})[outcome.task_id] = reference

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


__all__ = ["ArtifactIndexError", "build_artifact_index"]
