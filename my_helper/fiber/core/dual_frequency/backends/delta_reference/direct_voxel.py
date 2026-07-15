"""Direct-voxel DeltaReferenceScore construction on a locked reference source."""

from __future__ import annotations

import math
from typing import TypeAlias

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
from ..protocols import ArtifactPublisher


ScientificArray: TypeAlias = np.ndarray | ArtifactRef


class DeltaReferenceDirectVoxelError(ValueError):
    """Raised when locked reference inputs cannot produce a safe score bundle."""


def _materialize(
    value: ScientificArray,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    artifact_store: ArtifactStore | None,
) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asarray(value)
    if not isinstance(value, ArtifactRef):
        raise TypeError(f"{name} must be a NumPy array or ArtifactRef")
    if artifact_store is None:
        raise DeltaReferenceDirectVoxelError(
            f"{name} is artifact-backed but no ArtifactStore was provided"
        )
    if value.dtype is None or value.shape is None:
        raise DeltaReferenceDirectVoxelError(f"{name} must reference an array artifact")
    return artifact_store.materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=tuple(axis.count for axis in expected_axes),
        expected_axes=expected_axes,
        expected_units=expected_units,
        expected_space=value.space,
        mmap_mode="r",
    )


def _real_array(value: np.ndarray, name: str, dimensions: int) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != dimensions:
        raise DeltaReferenceDirectVoxelError(
            f"{name} must be {dimensions}-dimensional"
        )
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise DeltaReferenceDirectVoxelError(f"{name} must contain numeric values")
    if np.iscomplexobj(array):
        raise DeltaReferenceDirectVoxelError(f"{name} must contain real values")
    return np.asarray(array, dtype=np.float64)


def _selected_indices(value: np.ndarray, count: int) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 1 or array.shape != (count,):
        raise DeltaReferenceDirectVoxelError(
            "selected_feature_indices must match the selected reference feature axis"
        )
    if not np.issubdtype(array.dtype, np.integer):
        raise DeltaReferenceDirectVoxelError(
            "selected_feature_indices must contain integer parent-axis positions"
        )
    indices = np.asarray(array, dtype=np.int64)
    if indices.size and (indices[0] < 0 or np.any(np.diff(indices) <= 0)):
        raise DeltaReferenceDirectVoxelError(
            "selected_feature_indices must be unique and strictly increasing"
        )
    return indices


def _require_source_artifact(
    value: ScientificArray,
    source: SourceRecord,
    name: str,
) -> None:
    if isinstance(value, ArtifactRef) and value not in source.artifacts:
        raise DeltaReferenceDirectVoxelError(
            f"artifact-backed {name} must be carried by the accepted reference source"
        )


def _validate_support_profile(profile: DeltaReferenceSupportProfile) -> None:
    if not isinstance(profile, DeltaReferenceSupportProfile):
        raise TypeError("support_profile must be a DeltaReferenceSupportProfile")
    values = (
        profile.adequate.cohort_median_out_support_max,
        profile.adequate.subject_out_support_threshold,
        profile.adequate.subject_fraction_max,
        profile.invalid.cohort_median_out_support_min_exclusive,
        profile.invalid.subject_out_support_threshold,
        profile.invalid.subject_fraction_min_exclusive,
        profile.invalid.individual_out_support_min_exclusive,
    )
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        raise DeltaReferenceDirectVoxelError(
            "all DeltaReferenceScore support thresholds must be finite fractions"
        )
    if (
        profile.adequate.cohort_median_out_support_max
        >= profile.invalid.cohort_median_out_support_min_exclusive
    ):
        raise DeltaReferenceDirectVoxelError(
            "adequate and invalid median thresholds must leave a limited range"
        )
    if (
        profile.invalid.individual_out_support_min_exclusive
        <= profile.invalid.subject_out_support_threshold
    ):
        raise DeltaReferenceDirectVoxelError(
            "individual extreme threshold must exceed the cohort subject threshold"
        )


def _validate_locked_source(
    source: SourceRecord,
    parent_feature_axis: AxisRef,
    selected_indices: np.ndarray,
) -> None:
    if not isinstance(source, SourceRecord):
        raise TypeError("reference_source must be a SourceRecord")
    if source.endpoint.model_family != "reference_voxel":
        raise DeltaReferenceDirectVoxelError(
            "DeltaReferenceScore direct-voxel input requires a reference_voxel source"
        )
    if source.source_status not in ACCEPTED_SOURCE_STATUSES:
        raise DeltaReferenceDirectVoxelError(
            "DeltaReferenceScore construction requires an accepted reference source"
        )
    if (
        source.selected_tau is None
        or source.selected_coverage is None
        or source.feature_axis is None
    ):
        raise DeltaReferenceDirectVoxelError(
            "accepted reference source is missing locked source fields"
        )
    if selected_indices.size and selected_indices[-1] >= parent_feature_axis.count:
        raise DeltaReferenceDirectVoxelError(
            "selected_feature_indices exceed the parent feature axis"
        )
    expected_hash = canonical_hash(
        {
            "parent_axis_sha256": parent_feature_axis.sha256,
            "selected_indices": selected_indices.tolist(),
            "tau": source.selected_tau,
            "coverage": source.selected_coverage,
        }
    )
    if source.feature_axis.axis.sha256 != expected_hash:
        raise DeltaReferenceDirectVoxelError(
            "selected_feature_indices do not match the locked source feature-axis hash"
        )


def _continuous_scores(
    delta_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    full_valid = np.isfinite(full_weights)
    fold_valid = np.isfinite(fold_weights)
    if not np.any(full_valid):
        raise DeltaReferenceDirectVoxelError(
            "full-sample reference weights have no finite support"
        )
    if np.any(np.sum(fold_valid, axis=1) == 0):
        raise DeltaReferenceDirectVoxelError(
            "every reference training fold requires finite weight support"
        )
    if not np.all(np.isfinite(delta_exposure)):
        raise DeltaReferenceDirectVoxelError(
            "reference-condition component exposures must be finite"
        )

    full_scores = np.mean(
        delta_exposure[:, full_valid] * full_weights[full_valid][None, :],
        axis=1,
    )
    n_subjects = delta_exposure.shape[0]
    fold_scores = np.empty((n_subjects, n_subjects), dtype=np.float64)
    for heldout_index in range(n_subjects):
        valid = fold_valid[heldout_index]
        fold_scores[heldout_index] = np.mean(
            delta_exposure[:, valid]
            * fold_weights[heldout_index, valid][None, :],
            axis=1,
        )
    if not np.all(np.isfinite(full_scores)) or not np.all(np.isfinite(fold_scores)):
        raise DeltaReferenceDirectVoxelError(
            "DeltaReferenceScore computation produced nonfinite values"
        )
    return full_scores, fold_scores, full_valid, fold_valid


def _support_rows(
    addon_reference_exposure: np.ndarray,
    selected_indices: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
    selected_tau: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    active = addon_reference_exposure > selected_tau
    total = np.sum(active, axis=1, dtype=np.int64)

    full_parent_support = np.zeros(addon_reference_exposure.shape[1], dtype=bool)
    full_parent_support[selected_indices[full_valid]] = True
    full_in_support = np.sum(active & full_parent_support[None, :], axis=1)

    n_subjects = addon_reference_exposure.shape[0]
    fold_in_support = np.empty((n_subjects, n_subjects), dtype=np.int64)
    for heldout_index in range(n_subjects):
        fold_parent_support = np.zeros(addon_reference_exposure.shape[1], dtype=bool)
        fold_parent_support[selected_indices[fold_valid[heldout_index]]] = True
        fold_in_support[heldout_index] = np.sum(
            active & fold_parent_support[None, :],
            axis=1,
        )

    full_out_fraction = np.full(n_subjects, np.nan, dtype=np.float64)
    fold_out_fraction = np.full((n_subjects, n_subjects), np.nan, dtype=np.float64)
    nonzero = total > 0
    full_out_fraction[nonzero] = 1.0 - (
        full_in_support[nonzero] / total[nonzero]
    )
    fold_out_fraction[:, nonzero] = 1.0 - (
        fold_in_support[:, nonzero] / total[nonzero][None, :]
    )

    labels = (
        "total_suprathreshold_count",
        "full_in_support_count",
        "full_out_support_fraction",
        *(f"fold_{index}_out_support_fraction" for index in range(n_subjects)),
    )
    rows = np.column_stack(
        (
            total.astype(np.float64),
            full_in_support.astype(np.float64),
            full_out_fraction,
            fold_out_fraction.T,
        )
    )
    return rows, total, full_out_fraction, labels


def _classify_support(
    total: np.ndarray,
    full_out_fraction: np.ndarray,
    support_rows: np.ndarray,
    profile: DeltaReferenceSupportProfile,
) -> str:
    if np.any(total == 0):
        return "invalid_no_reference_component_coverage"

    fold_out_fraction = support_rows[:, 3:]
    all_required = np.concatenate((full_out_fraction, fold_out_fraction.ravel()))
    median_out = float(np.median(full_out_fraction))
    invalid_subject_fraction = float(
        np.mean(
            full_out_fraction
            > profile.invalid.subject_out_support_threshold
        )
    )
    if (
        median_out > profile.invalid.cohort_median_out_support_min_exclusive
        or invalid_subject_fraction
        > profile.invalid.subject_fraction_min_exclusive
        or np.any(
            all_required
            > profile.invalid.individual_out_support_min_exclusive
        )
    ):
        return "invalid_extreme_out_of_support"

    adequate_subject_fraction = float(
        np.mean(
            full_out_fraction
            > profile.adequate.subject_out_support_threshold
        )
    )
    if (
        median_out <= profile.adequate.cohort_median_out_support_max
        and adequate_subject_fraction <= profile.adequate.subject_fraction_max
    ):
        return "adequate"
    return "limited"


def build_delta_reference_voxel(
    *,
    matched_reference_endpoint_id: str,
    reference_source: SourceRecord,
    selected_feature_indices: ScientificArray,
    full_weights: ScientificArray,
    fold_weights: ScientificArray,
    reference_condition_exposure: ScientificArray,
    addon_reference_component_exposure: ScientificArray,
    subject_axis: AxisRef,
    parent_feature_axis: AxisRef,
    support_profile: DeltaReferenceSupportProfile,
    publisher: ArtifactPublisher,
    artifact_store: ArtifactStore | None = None,
) -> DeltaReferenceBundle:
    """Build immutable full/fold DeltaReferenceScore artifacts without refitting."""

    if not isinstance(subject_axis, AxisRef) or not isinstance(parent_feature_axis, AxisRef):
        raise TypeError("subject_axis and parent_feature_axis must be AxisRef values")
    if not isinstance(publisher, ArtifactPublisher):
        raise TypeError("publisher must implement ArtifactPublisher")
    if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
        raise TypeError("artifact_store must be an ArtifactStore or None")
    _validate_support_profile(support_profile)
    if not isinstance(reference_source, SourceRecord):
        raise TypeError("reference_source must be a SourceRecord")
    matched_endpoint = str(matched_reference_endpoint_id).strip()
    if not matched_endpoint:
        raise DeltaReferenceDirectVoxelError(
            "matched_reference_endpoint_id must be nonempty"
        )
    if reference_source.endpoint.identifier != matched_endpoint:
        raise DeltaReferenceDirectVoxelError(
            "reference source does not match matched_reference_endpoint_id"
        )
    if reference_source.feature_axis is None:
        raise DeltaReferenceDirectVoxelError(
            "DeltaReferenceScore construction requires a selected feature axis"
        )
    selected_axis = reference_source.feature_axis.axis

    for value, name in (
        (selected_feature_indices, "selected_feature_indices"),
        (full_weights, "full_weights"),
        (fold_weights, "fold_weights"),
    ):
        _require_source_artifact(value, reference_source, name)

    indices = _selected_indices(
        _materialize(
            selected_feature_indices,
            name="selected_feature_indices",
            expected_axes=(selected_axis,),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        selected_axis.count,
    )
    _validate_locked_source(reference_source, parent_feature_axis, indices)

    full_weight_array = _real_array(
        _materialize(
            full_weights,
            name="full_weights",
            expected_axes=(selected_axis,),
            expected_units="coefficient",
            artifact_store=artifact_store,
        ),
        "full_weights",
        1,
    )
    fold_weight_array = _real_array(
        _materialize(
            fold_weights,
            name="fold_weights",
            expected_axes=(subject_axis, selected_axis),
            expected_units="coefficient",
            artifact_store=artifact_store,
        ),
        "fold_weights",
        2,
    )
    reference_exposure = _real_array(
        _materialize(
            reference_condition_exposure,
            name="reference_condition_exposure",
            expected_axes=(subject_axis, parent_feature_axis),
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        "reference_condition_exposure",
        2,
    )
    addon_reference_exposure = _real_array(
        _materialize(
            addon_reference_component_exposure,
            name="addon_reference_component_exposure",
            expected_axes=(subject_axis, parent_feature_axis),
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        "addon_reference_component_exposure",
        2,
    )
    expected_exposure_shape = (subject_axis.count, parent_feature_axis.count)
    if reference_exposure.shape != expected_exposure_shape:
        raise DeltaReferenceDirectVoxelError(
            "reference_condition_exposure does not match the declared axes"
        )
    if addon_reference_exposure.shape != expected_exposure_shape:
        raise DeltaReferenceDirectVoxelError(
            "addon_reference_component_exposure does not match the declared axes"
        )
    if full_weight_array.shape != (selected_axis.count,):
        raise DeltaReferenceDirectVoxelError("full_weights do not match the selected axis")
    if fold_weight_array.shape != (subject_axis.count, selected_axis.count):
        raise DeltaReferenceDirectVoxelError(
            "fold_weights do not match the subject and selected feature axes"
        )

    selected_delta = (
        addon_reference_exposure[:, indices] - reference_exposure[:, indices]
    )
    full_scores, fold_scores, full_valid, fold_valid = _continuous_scores(
        selected_delta,
        full_weight_array,
        fold_weight_array,
    )
    support_rows, total, full_out_fraction, support_labels = _support_rows(
        addon_reference_exposure,
        indices,
        full_valid,
        fold_valid,
        float(reference_source.selected_tau),
    )
    support_status = _classify_support(
        total,
        full_out_fraction,
        support_rows,
        support_profile,
    )

    finite_full = full_out_fraction[np.isfinite(full_out_fraction)]
    all_fractions = support_rows[:, 2:]
    finite_required = all_fractions[np.isfinite(all_fractions)]
    support_qc_artifact = publisher.document(
        "delta_reference_support_qc.json",
        {
            "schema_version": "delta_reference_support_qc_v1",
            "support_status": support_status,
            "selected_reference_tau": reference_source.selected_tau,
            "selected_reference_coverage": reference_source.selected_coverage,
            "threshold_rule": "reference_component_exposure > selected_reference_tau",
            "support_fields": list(support_labels),
            "zero_total_suprathreshold_count": int(np.count_nonzero(total == 0)),
            "cohort_median_out_support_fraction": (
                float(np.median(finite_full)) if finite_full.size else None
            ),
            "subject_fraction_over_0p50": (
                float(np.mean(finite_full > 0.50)) if finite_full.size else None
            ),
            "subject_fraction_over_0p80": (
                float(np.mean(finite_full > 0.80)) if finite_full.size else None
            ),
            "maximum_required_out_support_fraction": (
                float(np.max(finite_required)) if finite_required.size else None
            ),
            "classification_thresholds": {
                "adequate_cohort_median_max": (
                    support_profile.adequate.cohort_median_out_support_max
                ),
                "adequate_subject_threshold": (
                    support_profile.adequate.subject_out_support_threshold
                ),
                "adequate_subject_fraction_max": (
                    support_profile.adequate.subject_fraction_max
                ),
                "invalid_cohort_median_min_exclusive": (
                    support_profile.invalid.cohort_median_out_support_min_exclusive
                ),
                "invalid_subject_threshold": (
                    support_profile.invalid.subject_out_support_threshold
                ),
                "invalid_subject_fraction_min_exclusive": (
                    support_profile.invalid.subject_fraction_min_exclusive
                ),
                "invalid_individual_min_exclusive": (
                    support_profile.invalid.individual_out_support_min_exclusive
                ),
            },
        },
        kind="delta_reference_support_qc",
    )

    support_axis = AxisRef(
        axis_id=f"{subject_axis.axis_id}:delta-reference-support-fields",
        count=len(support_labels),
        sha256=canonical_hash(
            {
                "subject_axis_sha256": subject_axis.sha256,
                "support_fields": support_labels,
            }
        ),
    )
    support_artifact = publisher.array(
        "delta_reference_support_rows.npy",
        support_rows,
        kind="delta_reference_support_rows",
        axes=(subject_axis, support_axis),
        units=None,
        space=None,
    )

    if support_status not in {"adequate", "limited"}:
        return DeltaReferenceBundle(
            input_status="invalid",
            support_status=support_status,
            selected_reference_tau=reference_source.selected_tau,
            selected_reference_coverage=reference_source.selected_coverage,
            full_scores=None,
            fold_scores=None,
            support_rows=support_artifact,
            support_qc=support_qc_artifact,
            failure_stage="support_qc",
            failure_detail=support_status,
        )

    full_artifact = publisher.array(
        "delta_reference_full_scores.npy",
        full_scores,
        kind="delta_reference_full_scores",
        axes=(subject_axis,),
        units="V/m",
        space=None,
    )
    fold_artifact = publisher.array(
        "delta_reference_fold_scores.npy",
        fold_scores,
        kind="delta_reference_fold_scores",
        axes=(subject_axis, subject_axis),
        units="V/m",
        space=None,
    )
    return DeltaReferenceBundle(
        input_status="valid",
        support_status=support_status,
        selected_reference_tau=reference_source.selected_tau,
        selected_reference_coverage=reference_source.selected_coverage,
        full_scores=full_artifact,
        fold_scores=fold_artifact,
        support_rows=support_artifact,
        support_qc=support_qc_artifact,
    )
