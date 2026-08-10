"""Individualized-target DeltaReferenceScore on a locked reference source."""

from __future__ import annotations

import math

import numpy as np

from ...cache import ArtifactStore
from ...config.models import DeltaReferenceSupportProfile
from ...contracts import (
    ArtifactRef,
    AxisRef,
    DeltaReferenceBundle,
    SourceRecord,
    canonical_hash,
)
from ...contracts.records import ACCEPTED_SOURCE_STATUSES
from ..individualized_target import (
    IndividualizedTargetKernelError,
    apply_target_operator,
)
from ..protocols import ArtifactPublisher
from .cohort import DeltaReferenceCohortError, reference_fold_indices


_BOUNDARY_ABS_TOL = 1e-12


class DeltaReferenceIndividualizedTargetError(ValueError):
    """Raised when locked target inputs cannot produce a delta score."""


def _materialize(
    artifact: ArtifactRef,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    artifact_store: ArtifactStore | None,
) -> np.ndarray:
    if not isinstance(artifact, ArtifactRef):
        raise TypeError(f"{name} must be an ArtifactRef")
    if artifact_store is None:
        raise DeltaReferenceIndividualizedTargetError(
            f"{name} requires an ArtifactStore"
        )
    return np.asarray(
        artifact_store.materialize(
            artifact,
            expected_dtype=artifact.dtype,
            expected_shape=tuple(axis.count for axis in expected_axes),
            expected_axes=expected_axes,
            expected_units=expected_units,
            expected_space=artifact.space,
        )
    )


def _source_artifact(source: SourceRecord, kind: str) -> ArtifactRef:
    matches = tuple(item for item in source.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise DeltaReferenceIndividualizedTargetError(
            f"reference target source requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _score(
    exposure: np.ndarray,
    weights: np.ndarray,
    centers: np.ndarray,
    scales: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    try:
        output = apply_target_operator(
            exposure,
            weights,
            centers,
            scales,
            valid_mask,
        )
    except IndividualizedTargetKernelError as exc:
        raise DeltaReferenceIndividualizedTargetError(str(exc)) from exc
    if not np.all(np.isfinite(output)):
        raise DeltaReferenceIndividualizedTargetError(
            "reference target operator produced nonfinite scores"
        )
    return output


def _strictly_below(value: float, cutoff: float) -> bool:
    return bool(
        value < cutoff
        and not math.isclose(
            value,
            cutoff,
            rel_tol=0.0,
            abs_tol=_BOUNDARY_ABS_TOL,
        )
    )


def _strictly_above(value: float, cutoff: float) -> bool:
    return bool(
        value > cutoff
        and not math.isclose(
            value,
            cutoff,
            rel_tol=0.0,
            abs_tol=_BOUNDARY_ABS_TOL,
        )
    )


def _strictly_above_array(values: np.ndarray, cutoff: float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return (array > cutoff) & ~np.isclose(
        array,
        cutoff,
        rtol=0.0,
        atol=_BOUNDARY_ABS_TOL,
    )


def _support_rows(
    all_support: np.ndarray,
    selected_support: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    total = np.count_nonzero(all_support, axis=1).astype(np.int64)
    full_in = np.count_nonzero(
        selected_support[:, full_valid],
        axis=1,
    ).astype(np.int64)
    n_subjects = all_support.shape[0]
    fold_in = np.empty((n_subjects, n_subjects), dtype=np.int64)
    for fold_index in range(n_subjects):
        fold_in[fold_index] = np.count_nonzero(
            selected_support[:, fold_valid[fold_index]],
            axis=1,
        )
    full_out = np.full(n_subjects, np.nan, dtype=np.float64)
    fold_out = np.full((n_subjects, n_subjects), np.nan, dtype=np.float64)
    nonzero = total > 0
    full_out[nonzero] = 1.0 - full_in[nonzero] / total[nonzero]
    fold_out[:, nonzero] = (
        1.0 - fold_in[:, nonzero] / total[nonzero][None, :]
    )
    labels = (
        "total_supported_target_count",
        "full_in_support_target_count",
        "full_out_support_fraction",
        *(
            f"fold_{index}_out_support_fraction"
            for index in range(n_subjects)
        ),
    )
    rows = np.column_stack(
        (
            total.astype(np.float64),
            full_in.astype(np.float64),
            full_out,
            fold_out.T,
        )
    )
    return rows, total, full_out, labels


def _support_status(
    total: np.ndarray,
    full_out: np.ndarray,
    rows: np.ndarray,
    profile: DeltaReferenceSupportProfile,
) -> str:
    if np.any(total == 0):
        return "invalid_no_reference_component_coverage"
    all_required = np.concatenate((full_out, rows[:, 3:].ravel()))
    invalid_subject_fraction = float(
        np.mean(
            _strictly_above_array(
                full_out,
                profile.invalid.subject_out_support_threshold,
            )
        )
    )
    if (
        _strictly_above(
            float(np.median(full_out)),
            profile.invalid.cohort_median_out_support_min_exclusive,
        )
        or _strictly_above(
            invalid_subject_fraction,
            profile.invalid.subject_fraction_min_exclusive,
        )
        or np.any(
            _strictly_above_array(
                all_required,
                profile.invalid.individual_out_support_min_exclusive,
            )
        )
    ):
        return "invalid_extreme_out_of_support"
    adequate_subject_fraction = float(
        np.mean(
            _strictly_above_array(
                full_out,
                profile.adequate.subject_out_support_threshold,
            )
        )
    )
    if (
        _strictly_below(
            float(np.median(full_out)),
            profile.adequate.cohort_median_out_support_max,
        )
        and _strictly_below(
            adequate_subject_fraction,
            profile.adequate.subject_fraction_max,
        )
    ):
        return "adequate"
    return "limited"


def target_delta_support_evidence(
    all_support: np.ndarray,
    selected_support: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
    profile: DeltaReferenceSupportProfile,
) -> tuple[
    str,
    np.ndarray,
    tuple[str, ...],
    dict[str, float | int | str | None],
]:
    """Summarize target-axis DeltaReferenceScore support."""

    rows, total, full_out, labels = _support_rows(
        all_support,
        selected_support,
        full_valid,
        fold_valid,
    )
    status = _support_status(total, full_out, rows, profile)
    finite_full = full_out[np.isfinite(full_out)]
    required = rows[:, 2:]
    finite_required = required[np.isfinite(required)]
    return (
        status,
        rows,
        labels,
        {
            "model_family": "individualized_seed_target",
            "support_status": status,
            "zero_supported_target_count": int(np.count_nonzero(total == 0)),
            "cohort_median_out_support_fraction": (
                float(np.median(finite_full)) if finite_full.size else None
            ),
            "maximum_required_out_support_fraction": (
                float(np.max(finite_required))
                if finite_required.size
                else None
            ),
        },
    )


def build_delta_reference_individualized_target(
    *,
    matched_reference_endpoint_id: str,
    reference_source: SourceRecord,
    reference_condition_burdens: ArtifactRef,
    addon_reference_component_burdens: ArtifactRef,
    addon_reference_component_support: ArtifactRef,
    subject_axis: AxisRef,
    reference_subject_axis: AxisRef,
    target_axis: AxisRef,
    tau_axis: AxisRef,
    tau_values: tuple[float, ...],
    addon_subject_ids: tuple[str, ...],
    reference_subject_ids: tuple[str, ...],
    support_profile: DeltaReferenceSupportProfile,
    publisher: ArtifactPublisher,
    artifact_store: ArtifactStore | None = None,
) -> DeltaReferenceBundle:
    """Apply the locked reference target operator to two reference conditions."""

    if (
        reference_source.endpoint.model_family != "reference_individualized"
        or reference_source.endpoint.identifier
        != str(matched_reference_endpoint_id).strip()
        or reference_source.source_status not in ACCEPTED_SOURCE_STATUSES
        or reference_source.feature_axis is None
        or reference_source.selected_tau is None
        or reference_source.selected_coverage is None
    ):
        raise DeltaReferenceIndividualizedTargetError(
            "DeltaReferenceScore requires an accepted matched individualized "
            "reference source"
        )
    if (
        reference_source.feature_axis.identity_source
        != "selected_individualized_target_union"
    ):
        raise DeltaReferenceIndividualizedTargetError(
            "reference source does not carry a selected target axis"
        )
    try:
        tau_index = tuple(float(value) for value in tau_values).index(
            float(reference_source.selected_tau)
        )
    except ValueError as exc:
        raise DeltaReferenceIndividualizedTargetError(
            "selected reference tau is outside the prepared target grid"
        ) from exc
    try:
        fold_indices = reference_fold_indices(
            addon_subject_ids=addon_subject_ids,
            reference_subject_ids=reference_subject_ids,
            addon_subject_axis=subject_axis,
            reference_subject_axis=reference_subject_axis,
        )
    except DeltaReferenceCohortError as exc:
        raise DeltaReferenceIndividualizedTargetError(str(exc)) from exc

    selected_axis = reference_source.feature_axis.axis
    indices = np.asarray(
        _materialize(
            _source_artifact(
                reference_source,
                "individualized_selected_target_indices",
            ),
            name="selected_target_indices",
            expected_axes=(selected_axis,),
            expected_units="index",
            artifact_store=artifact_store,
        ),
        dtype=np.int64,
    )
    if (
        indices.shape != (selected_axis.count,)
        or (
            indices.size
            and (
                indices[0] < 0
                or indices[-1] >= target_axis.count
                or np.any(np.diff(indices) <= 0)
            )
        )
    ):
        raise DeltaReferenceIndividualizedTargetError(
            "selected target indices are outside the parent target axis"
        )

    def selected_vector(kind: str, units: str) -> np.ndarray:
        return np.asarray(
            _materialize(
                _source_artifact(reference_source, kind),
                name=kind,
                expected_axes=(selected_axis,),
                expected_units=units,
                artifact_store=artifact_store,
            ),
            dtype=np.float64,
        )

    def selected_fold(kind: str, units: str) -> np.ndarray:
        values = np.asarray(
            _materialize(
                _source_artifact(reference_source, kind),
                name=kind,
                expected_axes=(reference_subject_axis, selected_axis),
                expected_units=units,
                artifact_store=artifact_store,
            ),
            dtype=np.float64,
        )
        return values[fold_indices]

    full_weights = selected_vector(
        "individualized_full_target_weights",
        "coefficient",
    )
    full_centers = selected_vector(
        "individualized_full_target_centers",
        "V/m",
    )
    full_scales = selected_vector(
        "individualized_full_target_scales",
        "V/m",
    )
    full_valid = np.asarray(
        selected_vector(
            "individualized_full_target_valid_mask",
            "binary",
        ),
        dtype=bool,
    )
    fold_weights = selected_fold(
        "individualized_fold_target_weights",
        "coefficient",
    )
    fold_centers = selected_fold(
        "individualized_fold_target_centers",
        "V/m",
    )
    fold_scales = selected_fold(
        "individualized_fold_target_scales",
        "V/m",
    )
    fold_valid = np.asarray(
        selected_fold(
            "individualized_fold_target_valid_masks",
            "binary",
        ),
        dtype=bool,
    )

    patient_axes = (tau_axis, subject_axis, target_axis)
    reference_all = np.asarray(
        _materialize(
            reference_condition_burdens,
            name="reference_condition_burdens",
            expected_axes=patient_axes,
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        dtype=np.float64,
    )[tau_index]
    component_all = np.asarray(
        _materialize(
            addon_reference_component_burdens,
            name="addon_reference_component_burdens",
            expected_axes=patient_axes,
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        dtype=np.float64,
    )[tau_index]
    component_support_all = np.asarray(
        _materialize(
            addon_reference_component_support,
            name="addon_reference_component_support",
            expected_axes=patient_axes,
            expected_units="binary",
            artifact_store=artifact_store,
        ),
        dtype=bool,
    )[tau_index]
    reference_selected = reference_all[:, indices]
    component_selected = component_all[:, indices]

    full_scores = _score(
        component_selected,
        full_weights,
        full_centers,
        full_scales,
        full_valid,
    ) - _score(
        reference_selected,
        full_weights,
        full_centers,
        full_scales,
        full_valid,
    )
    fold_scores = np.empty(
        (subject_axis.count, subject_axis.count),
        dtype=np.float64,
    )
    for fold_index in range(subject_axis.count):
        fold_scores[fold_index] = _score(
            component_selected,
            fold_weights[fold_index],
            fold_centers[fold_index],
            fold_scales[fold_index],
            fold_valid[fold_index],
        ) - _score(
            reference_selected,
            fold_weights[fold_index],
            fold_centers[fold_index],
            fold_scales[fold_index],
            fold_valid[fold_index],
        )

    status, rows, labels, support_values = target_delta_support_evidence(
        component_support_all,
        component_support_all[:, indices],
        full_valid,
        fold_valid,
        support_profile,
    )
    support_axis = AxisRef(
        axis_id=f"{subject_axis.axis_id}:target-delta-support-fields",
        count=len(labels),
        sha256=canonical_hash(
            {
                "subject_axis_sha256": subject_axis.sha256,
                "support_fields": labels,
            }
        ),
    )
    support_rows = publisher.array(
        "delta_reference_support_rows.npy",
        rows,
        kind="delta_reference_support_rows",
        axes=(subject_axis, support_axis),
        units=None,
        space=None,
    )
    support_qc = publisher.document(
        "delta_reference_support_qc.json",
        {
            "selected_reference_tau": reference_source.selected_tau,
            "selected_reference_coverage": reference_source.selected_coverage,
            "support_scope": "all_configured_targets",
            "support_fields": list(labels),
            **support_values,
        },
        kind="delta_reference_support_qc",
    )
    if status not in {"adequate", "limited"}:
        return DeltaReferenceBundle(
            input_status="invalid",
            support_status=status,
            selected_reference_tau=reference_source.selected_tau,
            selected_reference_coverage=reference_source.selected_coverage,
            full_scores=None,
            fold_scores=None,
            support_rows=support_rows,
            support_qc=support_qc,
            failure_stage="support_qc",
            failure_detail=status,
        )
    full_artifact = publisher.array(
        "delta_reference_full_scores.npy",
        full_scores,
        kind="delta_reference_full_scores",
        axes=(subject_axis,),
        units="score",
        space=None,
    )
    fold_artifact = publisher.array(
        "delta_reference_fold_scores.npy",
        fold_scores,
        kind="delta_reference_fold_scores",
        axes=(subject_axis, subject_axis),
        units="score",
        space=None,
    )
    return DeltaReferenceBundle(
        input_status="valid",
        support_status=status,
        selected_reference_tau=reference_source.selected_tau,
        selected_reference_coverage=reference_source.selected_coverage,
        full_scores=full_artifact,
        fold_scores=fold_artifact,
        support_rows=support_rows,
        support_qc=support_qc,
    )


__all__ = [
    "DeltaReferenceIndividualizedTargetError",
    "build_delta_reference_individualized_target",
    "target_delta_support_evidence",
]
