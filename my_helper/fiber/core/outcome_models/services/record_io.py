"""Persist immutable source and final-model records inside configured runs."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from ..catalog import EndpointRecord
from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..identity import FinalModelKey
from ..planner import TaskSpec
from ..records import (
    ArtifactRef,
    DeltaHFBundle,
    FinalArtifactRecord,
    HFSourceRecord,
    NuisancePlan,
    RecordError,
)
from ..run_store import sha256_file
from ..state import ACCEPTED_SOURCE_STATUSES


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _artifact_shape(path: Path) -> tuple[int, ...]:
    if path.suffix != ".npy":
        return ()
    try:
        return tuple(int(value) for value in np.load(path, mmap_mode="r").shape)
    except (OSError, ValueError) as exc:
        raise RecordError(f"cannot read NPY artifact shape for {path}: {exc}") from exc


def artifact_ref_for_task(
    artifact: TaskArtifact,
    *,
    task: TaskSpec,
    context: RunContext,
) -> ArtifactRef:
    path = Path(artifact.path).expanduser().resolve()
    try:
        relative = path.relative_to(context.store.run_root).as_posix()
    except ValueError as exc:
        raise RecordError(f"artifact {artifact.kind!r} is outside the configured run root") from exc
    if not path.is_file():
        raise RecordError(f"artifact {artifact.kind!r} is missing: {path}")
    return ArtifactRef(
        task_id=task.task_id,
        kind=artifact.kind,
        relative_path=relative,
        sha256=sha256_file(path),
        shape=_artifact_shape(path),
    )


def _estimator(task: TaskSpec, context: RunContext) -> str:
    if context.config is None:
        raise RecordError("HF record persistence requires resolved workflow context")
    if task.endpoint.model_family == "hf_voxel":
        return str(context.config.model.direct_voxel["estimator"])
    if task.endpoint.model_family == "hf_fiber":
        return f"{context.config.model.normative_fiber['exposure']}_partial_spearman"
    raise RecordError(f"unsupported HF model family {task.endpoint.model_family!r}")


def persist_hf_resolver_output(
    output: Any,
    endpoint: EndpointRecord,
    task: TaskSpec,
    context: RunContext,
) -> TaskResult:
    """Persist one resolver result and its unique HF final record when accepted."""
    if task.key.execution_stage != "observed_source_resolver":
        raise RecordError("HF source records may only be persisted by the resolver task")
    artifact_refs = tuple(
        artifact_ref_for_task(artifact, task=task, context=context)
        for artifact in output.artifacts
    )
    source = HFSourceRecord.create(
        resolver_task_id=task.task_id,
        endpoint_model_id=endpoint.endpoint_model_id,
        input_status="valid",
        source_status=str(output.source_status),
        prediction_status=str(output.prediction_status),
        threshold_source=str(output.threshold_source),
        selected_tau=output.selected_tau,
        selected_coverage=output.selected_coverage,
        subject_order=tuple(output.subject_order),
        feature_axis=output.feature_axis,
        artifacts=artifact_refs,
    )
    task_root = context.store.run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
    source_path = task_root / "hf_source_record.json"
    _write_json_atomic(source_path, source.as_dict())
    artifacts = list(output.artifacts)
    artifacts.append(TaskArtifact("hf_source_record", source_path))
    facts: dict[str, object] = {
        "source_accepted": source.accepted,
        "source_status": source.source_status,
        "prediction_status": source.prediction_status,
        "threshold_source": source.threshold_source,
        "selected_tau": source.selected_tau,
        "selected_coverage": source.selected_coverage,
        "adjacent_support": output.adjacent_support,
        "subject_order": list(source.subject_order),
        "feature_axis": source.feature_axis.as_dict() if source.feature_axis is not None else None,
        "hf_source_record": source.as_dict(),
        "hf_source_record_hash": source.record_hash,
        "final_model_realized": False,
    }
    if source.source_status not in ACCEPTED_SOURCE_STATUSES:
        return TaskResult(
            TaskStatus.COMPLETED,
            "hf_source_absent",
            facts=facts,
            artifacts=tuple(artifacts),
        )

    refs_by_kind = {artifact.kind: artifact for artifact in artifact_refs}
    required = {"selected_manifest", "exposure_matrix", "selected_scores"}
    missing = sorted(required - set(refs_by_kind))
    if missing:
        raise RecordError("accepted HF source is missing final artifacts: " + ",".join(missing))
    if source.feature_axis is None or source.selected_tau is None or source.selected_coverage is None:
        raise RecordError("accepted HF source is missing feature or threshold identity")
    final_key = FinalModelKey(
        endpoint_model_id=endpoint.endpoint_model_id,
        final_branch="hf_source",
        selected_tau=source.selected_tau,
        selected_coverage=source.selected_coverage,
        estimator=_estimator(task, context),
    )
    final = FinalArtifactRecord.create(
        final_model_id=final_key.identifier,
        endpoint_model_id=endpoint.endpoint_model_id,
        final_branch="hf_source",
        final_role="realized_final",
        selected_tau=source.selected_tau,
        selected_coverage=source.selected_coverage,
        estimator=final_key.estimator,
        scale_direction=endpoint.direction,
        subject_order=source.subject_order,
        nuisance=NuisancePlan.for_branch("hf_source", None),
        manifest=refs_by_kind["selected_manifest"],
        exposure=refs_by_kind["exposure_matrix"],
        scores=refs_by_kind["selected_scores"],
        feature_axis=source.feature_axis,
        spatial_reference=refs_by_kind.get("coefficient_nifti"),
    )
    final_path = task_root / "final_model_record.json"
    _write_json_atomic(final_path, final.as_dict())
    artifacts.append(TaskArtifact("final_model_record", final_path))
    facts.update(
        {
            "final_model_realized": True,
            "final_model_id": final.final_model_id,
            "final_record_hash": final.record_hash,
            "final_model_record": final.as_dict(),
        }
    )
    return TaskResult(
        TaskStatus.COMPLETED,
        "hf_source_and_final_persisted",
        facts=facts,
        artifacts=tuple(artifacts),
    )


def load_final_record(task: TaskSpec, context: RunContext) -> FinalArtifactRecord:
    """Load the one immutable final record for a task endpoint."""
    payloads = [
        record.result.facts.get("final_model_record")
        for record in context.results.values()
        if record.task.endpoint.identifier == task.endpoint.identifier
        and isinstance(record.result.facts.get("final_model_record"), dict)
    ]
    if len(payloads) != 1:
        raise RecordError(
            f"expected exactly one final-model record for {task.endpoint.identifier}; found {len(payloads)}"
        )
    return FinalArtifactRecord.from_dict(dict(payloads[0]))


def load_delta_bundle_for_final(
    final: FinalArtifactRecord,
    context: RunContext,
) -> DeltaHFBundle | None:
    """Load the exact Delta bundle referenced by an adjusted final nuisance plan."""
    record_hash = final.nuisance.delta_hf_record_hash
    if record_hash is None:
        return None
    matches: list[DeltaHFBundle] = []
    for record in context.results.values():
        if record.task.endpoint.identifier != final.endpoint_model_id:
            continue
        payload = record.result.facts.get("delta_hf_bundle")
        if not isinstance(payload, dict):
            continue
        bundle = DeltaHFBundle.from_dict(dict(payload))
        if bundle.record_hash == record_hash:
            matches.append(bundle)
    if len(matches) != 1:
        raise RecordError(
            f"expected exactly one DeltaHF bundle for final record {final.final_model_id}; found {len(matches)}"
        )
    return matches[0]


def load_delta_bundle_for_endpoint(
    endpoint_model_id: str,
    context: RunContext,
    *,
    expected_hf_source_hash: str,
) -> DeltaHFBundle:
    """Load the endpoint-local Delta bundle bound to one exact HF source lock."""
    matches: list[DeltaHFBundle] = []
    for record in context.results.values():
        if (
            record.task.endpoint.identifier != endpoint_model_id
            or record.task.key.execution_stage != "preprocessing_sidecars"
        ):
            continue
        source_hash = record.result.facts.get("hf_source_record_hash")
        if source_hash != expected_hf_source_hash:
            raise RecordError(
                "ULF DeltaHF sidecar does not match the endpoint's locked HF source"
            )
        payload = record.result.facts.get("delta_hf_bundle")
        if not isinstance(payload, dict):
            raise RecordError("ULF preprocessing sidecar is missing its DeltaHF bundle")
        matches.append(DeltaHFBundle.from_dict(dict(payload)))
    if len(matches) != 1:
        raise RecordError(
            f"expected exactly one endpoint-local DeltaHF bundle for {endpoint_model_id}; "
            f"found {len(matches)}"
        )
    return matches[0]


__all__ = [
    "artifact_ref_for_task",
    "load_delta_bundle_for_endpoint",
    "load_delta_bundle_for_final",
    "load_final_record",
    "persist_hf_resolver_output",
]
