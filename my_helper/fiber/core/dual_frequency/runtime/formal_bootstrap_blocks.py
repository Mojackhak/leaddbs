"""Durable publication and restoration of formal bootstrap blocks."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..backends.formal.common import (
    BootstrapBlockComputation,
    ReplicateBlock,
    materialize_array,
)
from ..backends.protocols import ArtifactPublisher
from ..contracts import (
    AxisRef,
    BootstrapBlockRecord,
    ResamplingScheduleRecord,
    resampling_block_axis,
)


BOOTSTRAP_EVIDENCE_SCHEMA = "dual_frequency_formal_bootstrap_evidence_block_v1"


class FormalBootstrapBlockError(RuntimeError):
    """Raised when one bootstrap block violates its durable parent contract."""


def _publish_array(
    publisher: ArtifactPublisher,
    filename: str,
    value: np.ndarray,
    *,
    kind: str,
    axis: AxisRef,
    units: str,
    space: str | None,
) -> object:
    return publisher.array(
        filename,
        value,
        kind=kind,
        axes=(axis,),
        units=units,
        space=space,
    )


def publish_formal_bootstrap_block(
    result: BootstrapBlockComputation,
    schedule: ResamplingScheduleRecord,
    feature_axis: AxisRef,
    feature_space: str,
    publisher: ArtifactPublisher,
) -> BootstrapBlockRecord:
    """Publish one mergeable bootstrap interval and its complete typed record."""

    if not isinstance(result, BootstrapBlockComputation):
        raise FormalBootstrapBlockError("bootstrap block result is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise FormalBootstrapBlockError("resampling schedule record is invalid")
    if not isinstance(feature_axis, AxisRef):
        raise FormalBootstrapBlockError("bootstrap feature axis is invalid")
    normalized_space = str(feature_space).strip()
    block = result.block
    if (
        schedule.resampling_kind != "bootstrap"
        or result.schedule_sha256 != schedule.schedule_sha256
        or block.total != schedule.replicate_count
        or result.weight_sum.shape != (feature_axis.count,)
        or not normalized_space
    ):
        raise FormalBootstrapBlockError(
            "bootstrap block does not match its parent schedule or feature axis"
        )
    block_axis = resampling_block_axis(
        schedule.replicate_axis,
        block.start,
        block.stop,
    )
    feature_arrays = (
        (
            "formal_bootstrap_weight_sum_block",
            result.weight_sum,
            "coefficient_sum",
        ),
        (
            "formal_bootstrap_weight_square_sum_block",
            result.weight_square_sum,
            "coefficient_squared_sum",
        ),
        (
            "formal_bootstrap_finite_weight_count_block",
            result.finite_weight_count,
            "count",
        ),
        (
            "formal_bootstrap_candidate_count_block",
            result.candidate_count,
            "count",
        ),
        (
            "formal_bootstrap_positive_count_block",
            result.positive_count,
            "count",
        ),
        (
            "formal_bootstrap_negative_count_block",
            result.negative_count,
            "count",
        ),
    )
    replicate_arrays = (
        (
            "formal_bootstrap_replicate_candidate_count_block",
            result.replicate_candidate_count,
            "count",
        ),
        (
            "formal_bootstrap_replicate_valid_weight_count_block",
            result.replicate_valid_weight_count,
            "count",
        ),
        (
            "formal_bootstrap_replicate_support_code_block",
            result.replicate_support_code,
            "ordinal_code",
        ),
    )
    artifacts = [
        _publish_array(
            publisher,
            f"{kind}.npy",
            value,
            kind=kind,
            axis=feature_axis,
            units=units,
            space=normalized_space,
        )
        for kind, value, units in feature_arrays
    ]
    selection_mode = "none"
    if result.sweet_count is not None and result.sour_count is not None:
        selection_mode = "sweet_sour"
        for kind, value in (
            ("formal_bootstrap_sweet_count_block", result.sweet_count),
            ("formal_bootstrap_sour_count_block", result.sour_count),
        ):
            artifacts.append(
                _publish_array(
                    publisher,
                    f"{kind}.npy",
                    value,
                    kind=kind,
                    axis=feature_axis,
                    units="count",
                    space=normalized_space,
                )
            )
    for kind, value, units in replicate_arrays:
        artifacts.append(
            _publish_array(
                publisher,
                f"{kind}.npy",
                value,
                kind=kind,
                axis=block_axis,
                units=units,
                space=None,
            )
        )
    nuisance_evidence_mode = (
        "complete_adjusted"
        if result.require_complete_nuisance_evidence
        else "none"
    )
    artifacts.append(
        publisher.document(
            "formal_bootstrap_evidence_block.json",
            {
                "schema_version": BOOTSTRAP_EVIDENCE_SCHEMA,
                "target_id": schedule.target_id,
                "schedule_id": schedule.identifier,
                "schedule_sha256": schedule.schedule_sha256,
                "block_index": block.index,
                "start": block.start,
                "stop": block.stop,
                "total": block.total,
                "selection_mode": selection_mode,
                "nuisance_evidence_mode": nuisance_evidence_mode,
                "nuisance_evidence": [dict(item) for item in result.nuisance_evidence],
                "nonestimable_replicates": [
                    dict(item) for item in result.nonestimable_replicates
                ],
            },
            kind="formal_bootstrap_evidence_block",
        )
    )
    finite_replicates = int(
        np.count_nonzero(result.replicate_valid_weight_count > 0)
    )
    return BootstrapBlockRecord(
        target_id=schedule.target_id,
        schedule_id=schedule.identifier,
        feature_axis=feature_axis,
        feature_space=normalized_space,
        replicate_axis=schedule.replicate_axis,
        block_axis=block_axis,
        block_index=block.index,
        start=block.start,
        stop=block.stop,
        total=block.total,
        schedule_sha256=schedule.schedule_sha256,
        selection_mode=selection_mode,
        nuisance_evidence_mode=nuisance_evidence_mode,
        technical_status=(
            "completed"
            if finite_replicates == block.count
            else "completed_with_nonfinite_replicates"
        ),
        artifacts=tuple(artifacts),
    )


def _load_array(
    artifacts: dict[str, object],
    kind: str,
    *,
    axis: AxisRef,
    units: str,
    space: str | None,
    artifact_store: object,
) -> np.ndarray:
    return np.asarray(
        materialize_array(
            artifacts[kind],
            name=kind,
            expected_axes=(axis,),
            expected_units=units,
            expected_space=space,
            artifact_store=artifact_store,
            memory_map=True,
        )
    )


def _load_evidence(
    record: BootstrapBlockRecord,
    schedule: ResamplingScheduleRecord,
    artifact: object,
    artifact_store: object,
) -> dict[str, Any]:
    materialize_document = getattr(artifact_store, "materialize_document", None)
    if not callable(materialize_document):
        raise FormalBootstrapBlockError(
            "bootstrap evidence requires a document-capable ArtifactStore"
        )
    payload = materialize_document(
        artifact,
        expected_kind="formal_bootstrap_evidence_block",
    )
    expected_scalars = {
        "schema_version": BOOTSTRAP_EVIDENCE_SCHEMA,
        "target_id": schedule.target_id,
        "schedule_id": schedule.identifier,
        "schedule_sha256": schedule.schedule_sha256,
        "block_index": record.block_index,
        "start": record.start,
        "stop": record.stop,
        "total": record.total,
        "selection_mode": record.selection_mode,
        "nuisance_evidence_mode": record.nuisance_evidence_mode,
    }
    expected_fields = {
        *expected_scalars,
        "nuisance_evidence",
        "nonestimable_replicates",
    }
    if set(payload) != expected_fields or any(
        payload[key] != value for key, value in expected_scalars.items()
    ):
        raise FormalBootstrapBlockError(
            "bootstrap evidence does not match its block record"
        )
    for field in ("nuisance_evidence", "nonestimable_replicates"):
        if not isinstance(payload[field], list) or not all(
            isinstance(item, dict) for item in payload[field]
        ):
            raise FormalBootstrapBlockError(
                f"bootstrap evidence field {field!r} is invalid"
            )
    return payload


def load_formal_bootstrap_block(
    record: BootstrapBlockRecord,
    schedule: ResamplingScheduleRecord,
    feature_axis: AxisRef,
    feature_space: str,
    artifact_store: object,
) -> BootstrapBlockComputation:
    """Restore one bootstrap block after validating its complete parent binding."""

    if not isinstance(record, BootstrapBlockRecord):
        raise FormalBootstrapBlockError("bootstrap block record is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise FormalBootstrapBlockError("resampling schedule record is invalid")
    if not isinstance(feature_axis, AxisRef):
        raise FormalBootstrapBlockError("bootstrap feature axis is invalid")
    normalized_space = str(feature_space).strip()
    if (
        schedule.resampling_kind != "bootstrap"
        or record.target_id != schedule.target_id
        or record.schedule_id != schedule.identifier
        or record.feature_axis != feature_axis
        or record.feature_space != normalized_space
        or record.replicate_axis != schedule.replicate_axis
        or record.total != schedule.replicate_count
        or record.schedule_sha256 != schedule.schedule_sha256
    ):
        raise FormalBootstrapBlockError(
            "bootstrap block record does not match its parent schedule or feature axis"
        )
    block = ReplicateBlock(
        record.block_index,
        record.start,
        record.stop,
        record.total,
    )
    artifacts = {artifact.kind: artifact for artifact in record.artifacts}
    try:
        evidence = _load_evidence(
            record,
            schedule,
            artifacts["formal_bootstrap_evidence_block"],
            artifact_store,
        )
        feature_values = {
            "weight_sum": _load_array(
                artifacts,
                "formal_bootstrap_weight_sum_block",
                axis=feature_axis,
                units="coefficient_sum",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
            "weight_square_sum": _load_array(
                artifacts,
                "formal_bootstrap_weight_square_sum_block",
                axis=feature_axis,
                units="coefficient_squared_sum",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
            "finite_weight_count": _load_array(
                artifacts,
                "formal_bootstrap_finite_weight_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
            "candidate_count": _load_array(
                artifacts,
                "formal_bootstrap_candidate_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
            "positive_count": _load_array(
                artifacts,
                "formal_bootstrap_positive_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
            "negative_count": _load_array(
                artifacts,
                "formal_bootstrap_negative_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            ),
        }
        if record.selection_mode == "sweet_sour":
            feature_values["sweet_count"] = _load_array(
                artifacts,
                "formal_bootstrap_sweet_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            )
            feature_values["sour_count"] = _load_array(
                artifacts,
                "formal_bootstrap_sour_count_block",
                axis=feature_axis,
                units="count",
                space=normalized_space,
                artifact_store=artifact_store,
            )
        replicate_values = {
            "replicate_candidate_count": _load_array(
                artifacts,
                "formal_bootstrap_replicate_candidate_count_block",
                axis=record.block_axis,
                units="count",
                space=None,
                artifact_store=artifact_store,
            ),
            "replicate_valid_weight_count": _load_array(
                artifacts,
                "formal_bootstrap_replicate_valid_weight_count_block",
                axis=record.block_axis,
                units="count",
                space=None,
                artifact_store=artifact_store,
            ),
            "replicate_support_code": _load_array(
                artifacts,
                "formal_bootstrap_replicate_support_code_block",
                axis=record.block_axis,
                units="ordinal_code",
                space=None,
                artifact_store=artifact_store,
            ),
        }
        return BootstrapBlockComputation(
            block=block,
            schedule_sha256=record.schedule_sha256,
            **feature_values,
            **replicate_values,
            require_complete_nuisance_evidence=(
                record.nuisance_evidence_mode == "complete_adjusted"
            ),
            nuisance_evidence=tuple(evidence["nuisance_evidence"]),
            nonestimable_replicates=tuple(
                evidence["nonestimable_replicates"]
            ),
        )
    except FormalBootstrapBlockError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise FormalBootstrapBlockError(str(error)) from error


__all__ = [
    "BOOTSTRAP_EVIDENCE_SCHEMA",
    "FormalBootstrapBlockError",
    "load_formal_bootstrap_block",
    "publish_formal_bootstrap_block",
]
