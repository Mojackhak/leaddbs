"""Normative-fiber DeltaReferenceScore construction on a locked local source."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import TypeAlias

import numpy as np

from ...cache import ArtifactStore
from ...config.models import DeltaReferenceSupportProfile
from ...contracts import (
    ArtifactRef,
    AxisRef,
    DeltaReferenceBundle,
    NormativeFiberScoreSettings,
    SensitiveRecord,
    SourceRecord,
    canonical_hash,
)
from ...contracts.records import ACCEPTED_SOURCE_STATUSES
from ..normative_fiber.scoring import FiberScoreError, score_signed_fibers
from ..protocols import ArtifactPublisher
from .cohort import DeltaReferenceCohortError, reference_fold_indices


ScientificArray: TypeAlias = np.ndarray | ArtifactRef
ReferenceRecord: TypeAlias = SourceRecord | SensitiveRecord
_BOUNDARY_ABS_TOL = 1e-12


class DeltaReferenceFiberError(ValueError):
    """Raised when a local locked fiber operator violates its contract."""


def _strictly_below(value: float, cutoff: float) -> bool:
    return bool(
        value < cutoff
        and not math.isclose(value, cutoff, rel_tol=0.0, abs_tol=_BOUNDARY_ABS_TOL)
    )


def _strictly_above(value: float, cutoff: float) -> bool:
    return bool(
        value > cutoff
        and not math.isclose(value, cutoff, rel_tol=0.0, abs_tol=_BOUNDARY_ABS_TOL)
    )


def _strictly_above_array(values: np.ndarray, cutoff: float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return (array > cutoff) & ~np.isclose(
        array,
        cutoff,
        rtol=0.0,
        atol=_BOUNDARY_ABS_TOL,
    )


@dataclass(frozen=True)
class _LockedReference:
    endpoint_id: str
    connectome_id: str
    selected_tau: float
    selected_coverage: int
    selected_axis: AxisRef
    artifacts: tuple[ArtifactRef, ...]
    record_type: str


def _materialize(
    value: ScientificArray,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    artifact_store: ArtifactStore | None,
) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asanyarray(value)
    if not isinstance(value, ArtifactRef):
        raise TypeError(f"{name} must be a NumPy array or ArtifactRef")
    if artifact_store is None:
        raise DeltaReferenceFiberError(
            f"{name} is artifact-backed but no ArtifactStore was provided"
        )
    if value.dtype is None or value.shape is None:
        raise DeltaReferenceFiberError(f"{name} must reference an array artifact")
    if value.axis_refs != expected_axes:
        raise DeltaReferenceFiberError(
            f"{name} artifact axes do not match the declared axes"
        )
    if value.units != expected_units:
        raise DeltaReferenceFiberError(
            f"{name} artifact units do not match the required units"
        )
    return artifact_store.materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=tuple(axis.count for axis in expected_axes),
        expected_axes=expected_axes,
        expected_units=expected_units,
        expected_space=value.space,
        mmap_mode="r",
    )


def _fiber_ids(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.ndim != 1
        or array.shape != (count,)
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.integer)
    ):
        raise DeltaReferenceFiberError(
            f"{name} must be a matching one-dimensional integer array"
        )
    if np.issubdtype(array.dtype, np.unsignedinteger) and np.any(
        array > np.iinfo(np.int64).max
    ):
        raise DeltaReferenceFiberError(f"{name} exceed the canonical int64 range")
    output = np.asarray(array, dtype=np.int64)
    if np.unique(output).size != output.size:
        raise DeltaReferenceFiberError(f"{name} must contain unique IDs")
    return output


def _real_array(value: np.ndarray, name: str, dimensions: int) -> np.ndarray:
    array = np.asanyarray(value)
    if array.ndim != dimensions:
        raise DeltaReferenceFiberError(
            f"{name} must be {dimensions}-dimensional"
        )
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise DeltaReferenceFiberError(f"{name} must contain numeric values")
    if np.iscomplexobj(array):
        raise DeltaReferenceFiberError(f"{name} must contain real values")
    return array


def _boolean_array(value: np.ndarray, name: str, dimensions: int) -> np.ndarray:
    array = np.asanyarray(value)
    if array.ndim != dimensions or array.dtype != np.dtype(bool):
        raise DeltaReferenceFiberError(
            f"{name} must be a {dimensions}-dimensional boolean array"
        )
    return array


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
        raise DeltaReferenceFiberError(
            "all DeltaReferenceScore support thresholds must be finite fractions"
        )
    if (
        profile.adequate.cohort_median_out_support_max
        >= profile.invalid.cohort_median_out_support_min_exclusive
    ):
        raise DeltaReferenceFiberError(
            "adequate and invalid median thresholds must leave a limited range"
        )
    if (
        profile.invalid.individual_out_support_min_exclusive
        <= profile.invalid.subject_out_support_threshold
    ):
        raise DeltaReferenceFiberError(
            "individual extreme threshold must exceed the cohort subject threshold"
        )


def _locked_reference(
    reference_record: ReferenceRecord,
    *,
    matched_reference_endpoint_id: str,
    matched_reference_connectome_id: str,
) -> _LockedReference:
    endpoint_id = str(matched_reference_endpoint_id).strip()
    connectome_id = str(matched_reference_connectome_id).strip()
    if not endpoint_id:
        raise DeltaReferenceFiberError(
            "matched_reference_endpoint_id must be nonempty"
        )
    if not connectome_id or connectome_id == "none":
        raise DeltaReferenceFiberError(
            "matched_reference_connectome_id must identify a normative connectome"
        )
    if not isinstance(reference_record, (SourceRecord, SensitiveRecord)):
        raise TypeError("reference_record must be a SourceRecord or SensitiveRecord")
    if reference_record.endpoint.model_family != "reference_fiber":
        raise DeltaReferenceFiberError(
            "DeltaReferenceScore fiber input requires a reference_fiber record"
        )
    if reference_record.endpoint.identifier != endpoint_id:
        raise DeltaReferenceFiberError(
            "local reference record does not match matched_reference_endpoint_id"
        )
    if reference_record.endpoint.connectome_id != connectome_id:
        raise DeltaReferenceFiberError(
            "local reference record does not match matched_reference_connectome_id"
        )

    if isinstance(reference_record, SourceRecord):
        if reference_record.source_status not in ACCEPTED_SOURCE_STATUSES:
            raise DeltaReferenceFiberError(
                "formal DeltaReferenceScore construction requires an accepted source"
            )
        if (
            reference_record.selected_tau is None
            or reference_record.selected_coverage is None
            or reference_record.feature_axis is None
        ):
            raise DeltaReferenceFiberError(
                "accepted formal reference source is missing locked source fields"
            )
        tau = reference_record.selected_tau
        coverage = reference_record.selected_coverage
        selected_axis = reference_record.feature_axis
        record_type = "formal_source"
    else:
        if (
            reference_record.input_status != "valid"
            or reference_record.cell_computability_status != "computable"
            or reference_record.feature_axis is None
        ):
            raise DeltaReferenceFiberError(
                "sensitive DeltaReferenceScore construction requires computable local evidence"
            )
        tau = reference_record.evaluated_tau
        coverage = reference_record.evaluated_coverage
        selected_axis = reference_record.feature_axis
        record_type = "sensitive_local_evidence"

    if (
        selected_axis.identity_source
        != "selected_normative_fiber_full_fold_valid_union"
    ):
        raise DeltaReferenceFiberError(
            "local reference feature axis is not a normative-fiber valid union"
        )
    return _LockedReference(
        endpoint_id=endpoint_id,
        connectome_id=connectome_id,
        selected_tau=float(tau),
        selected_coverage=int(coverage),
        selected_axis=selected_axis.axis,
        artifacts=tuple(reference_record.artifacts),
        record_type=record_type,
    )


def _require_reference_artifact(
    value: ScientificArray,
    locked: _LockedReference,
    *,
    name: str,
    expected_kind: str,
) -> None:
    if not isinstance(value, ArtifactRef):
        return
    if value not in locked.artifacts:
        raise DeltaReferenceFiberError(
            f"artifact-backed {name} must be carried by the local reference record"
        )
    if value.kind != expected_kind:
        raise DeltaReferenceFiberError(
            f"{name} artifact kind must be {expected_kind!r}"
        )


def _validate_artifact_spaces(values: tuple[ScientificArray, ...]) -> None:
    spaces = {
        value.space
        for value in values
        if isinstance(value, ArtifactRef) and value.space is not None
    }
    if len(spaces) > 1:
        raise DeltaReferenceFiberError(
            "artifact spaces do not match the local reference connectome"
        )


def _parent_positions(
    parent_fiber_ids: np.ndarray,
    valid_fiber_ids: np.ndarray,
) -> np.ndarray:
    order = np.argsort(parent_fiber_ids, kind="stable")
    sorted_parent = parent_fiber_ids[order]
    insertion = np.searchsorted(sorted_parent, valid_fiber_ids)
    within = insertion < sorted_parent.size
    matches = np.zeros(valid_fiber_ids.size, dtype=bool)
    matches[within] = (
        sorted_parent[insertion[within]] == valid_fiber_ids[within]
    )
    if not np.all(matches):
        raise DeltaReferenceFiberError(
            "valid-union fiber IDs are not present on the parent fiber axis"
        )
    positions = np.asarray(order[insertion], dtype=np.int64)
    if positions.size and (positions[0] < 0 or np.any(np.diff(positions) <= 0)):
        raise DeltaReferenceFiberError(
            "valid-union fiber IDs must preserve deterministic parent order"
        )
    return positions


def _validate_selected_axis(
    locked: _LockedReference,
    parent_fiber_axis: AxisRef,
    valid_fiber_ids: np.ndarray,
) -> None:
    selected_id_digest = hashlib.sha256(
        np.ascontiguousarray(valid_fiber_ids, dtype=np.int64).tobytes(order="C")
    ).hexdigest()
    expected_hash = canonical_hash(
        {
            "parent_axis_sha256": parent_fiber_axis.sha256,
            "selected_fiber_ids_sha256": selected_id_digest,
            "tau": locked.selected_tau,
            "coverage": locked.selected_coverage,
        }
    )
    if locked.selected_axis.sha256 != expected_hash:
        raise DeltaReferenceFiberError(
            "valid-union fiber IDs do not match the locked parent fiber axis"
        )


def _operator_score(
    addon_exposure: np.ndarray,
    reference_exposure: np.ndarray,
    weights: np.ndarray,
    valid_mask: np.ndarray,
    fiber_ids: np.ndarray,
    settings: NormativeFiberScoreSettings,
    *,
    label: str,
) -> np.ndarray:
    if not np.any(valid_mask):
        raise DeltaReferenceFiberError(
            f"{label} reference operator has no finite valid support"
        )
    try:
        addon_result = score_signed_fibers(
            addon_exposure,
            weights,
            fiber_ids,
            settings,
            candidate_mask=valid_mask,
        )
        reference_result = score_signed_fibers(
            reference_exposure,
            weights,
            fiber_ids,
            settings,
            candidate_mask=valid_mask,
        )
    except FiberScoreError as error:
        raise DeltaReferenceFiberError(
            f"{label} locked signed-fiber operator is invalid: {error}"
        ) from error
    if addon_result.fiber_score_support_status == "absent_no_valid_signed_fibers":
        raise DeltaReferenceFiberError(
            f"{label} reference operator has no valid signed fibers"
        )
    delta = np.asarray(
        addon_result.net_score - reference_result.net_score,
        dtype=np.float64,
    )
    if not np.all(np.isfinite(delta)):
        raise DeltaReferenceFiberError(
            f"{label} DeltaReferenceScore produced nonfinite values"
        )
    return delta


def _locked_scores(
    addon_exposure: np.ndarray,
    reference_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
    fold_valid_masks: np.ndarray,
    fiber_ids: np.ndarray,
    settings: NormativeFiberScoreSettings,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    full_valid = np.isfinite(full_weights)
    if not np.any(full_valid):
        raise DeltaReferenceFiberError(
            "full-sample reference weights have no finite valid support"
        )
    if np.any(np.sum(fold_valid_masks, axis=1) == 0):
        raise DeltaReferenceFiberError(
            "every reference training fold requires finite valid support"
        )
    full_scores = _operator_score(
        addon_exposure,
        reference_exposure,
        full_weights,
        full_valid,
        fiber_ids,
        settings,
        label="full-sample",
    )
    n_subjects = addon_exposure.shape[0]
    fold_scores = np.empty((n_subjects, n_subjects), dtype=np.float64)
    for heldout_index in range(n_subjects):
        fold_scores[heldout_index] = _operator_score(
            addon_exposure,
            reference_exposure,
            fold_weights[heldout_index],
            fold_valid_masks[heldout_index],
            fiber_ids,
            settings,
            label=f"fold {heldout_index}",
        )
    return full_scores, fold_scores, full_valid, fold_valid_masks


def _support_rows(
    addon_reference_exposure: np.ndarray,
    selected_parent_positions: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
    selected_tau: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    n_subjects = addon_reference_exposure.shape[0]
    total = np.zeros(n_subjects, dtype=np.int64)
    selected_active = np.empty(
        (n_subjects, selected_parent_positions.size),
        dtype=bool,
    )

    chunk_size = 65_536
    for start in range(0, addon_reference_exposure.shape[1], chunk_size):
        stop = min(start + chunk_size, addon_reference_exposure.shape[1])
        active = np.asarray(addon_reference_exposure[:, start:stop]) >= selected_tau
        total += np.count_nonzero(active, axis=1)

        selected_start = int(np.searchsorted(selected_parent_positions, start))
        selected_stop = int(np.searchsorted(selected_parent_positions, stop))
        if selected_start == selected_stop:
            continue
        selected_slice = slice(selected_start, selected_stop)
        local_positions = selected_parent_positions[selected_slice] - start
        selected_active[:, selected_slice] = active[:, local_positions]

    return _support_rows_from_selected(
        selected_active,
        total,
        full_valid,
        fold_valid,
    )


def _support_rows_from_selected(
    selected_active: np.ndarray,
    total: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    active = np.asarray(selected_active, dtype=bool)
    totals = np.asarray(total, dtype=np.int64)
    if active.ndim != 2:
        raise DeltaReferenceFiberError(
            "compact DeltaReferenceScore support inputs are inconsistent"
        )
    n_subjects = active.shape[0]
    if (
        totals.shape != (n_subjects,)
        or full_valid.shape != (active.shape[1],)
        or fold_valid.shape != (n_subjects, active.shape[1])
        or np.any(totals < 0)
    ):
        raise DeltaReferenceFiberError(
            "compact DeltaReferenceScore support inputs are inconsistent"
        )
    full_in_support = np.count_nonzero(active[:, full_valid], axis=1)
    fold_in_support = np.empty((n_subjects, n_subjects), dtype=np.int64)
    for heldout_index in range(n_subjects):
        fold_in_support[heldout_index] = np.count_nonzero(
            active[:, fold_valid[heldout_index]],
            axis=1,
        )
    if np.any(full_in_support > totals) or np.any(
        fold_in_support > totals[None, :]
    ):
        raise DeltaReferenceFiberError(
            "compact support counts exceed complete-parent totals"
        )

    full_out_count = totals - full_in_support
    fold_out_count = totals[None, :] - fold_in_support

    full_out_fraction = np.full(n_subjects, np.nan, dtype=np.float64)
    fold_out_fraction = np.full(
        (n_subjects, n_subjects),
        np.nan,
        dtype=np.float64,
    )
    nonzero = totals > 0
    full_out_fraction[nonzero] = (
        full_out_count[nonzero] / totals[nonzero]
    )
    fold_out_fraction[:, nonzero] = (
        fold_out_count[:, nonzero] / totals[nonzero][None, :]
    )

    labels = (
        "total_suprathreshold_count",
        "full_in_support_count",
        "full_out_support_fraction",
        *(f"fold_{index}_out_support_fraction" for index in range(n_subjects)),
    )
    rows = np.column_stack(
        (
            totals.astype(np.float64),
            full_in_support.astype(np.float64),
            full_out_fraction,
            fold_out_fraction.T,
        )
    )
    return rows, totals, full_out_fraction, labels


def _classify_support(
    total: np.ndarray,
    full_out_fraction: np.ndarray,
    support_rows: np.ndarray,
    profile: DeltaReferenceSupportProfile,
) -> str:
    if np.any(total == 0):
        return "invalid_no_reference_component_exposure"

    fold_out_fraction = support_rows[:, 3:]
    all_required = np.concatenate((full_out_fraction, fold_out_fraction.ravel()))
    if not np.all(np.isfinite(all_required)):
        raise DeltaReferenceFiberError(
            "nonzero reference-component support must produce finite fractions"
        )
    median_out = float(np.median(full_out_fraction))
    invalid_subject_fraction = float(
        np.mean(
            _strictly_above_array(
                full_out_fraction,
                profile.invalid.subject_out_support_threshold,
            )
        )
    )
    if (
        _strictly_above(
            median_out,
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
                full_out_fraction,
                profile.adequate.subject_out_support_threshold,
            )
        )
    )
    if (
        _strictly_below(
            median_out,
            profile.adequate.cohort_median_out_support_max,
        )
        and _strictly_below(
            adequate_subject_fraction,
            profile.adequate.subject_fraction_max,
        )
    ):
        return "adequate"
    return "limited"


def _score_settings_payload(
    settings: NormativeFiberScoreSettings,
) -> dict[str, float | int]:
    return {
        "sweet_fraction": settings.sweet_fraction,
        "sour_fraction": settings.sour_fraction,
        "weighted_peak_fraction": settings.weighted_peak_fraction,
        "sweet_selected_min_count": settings.sweet_selected_min_count,
        "sour_selected_min_count": settings.sour_selected_min_count,
        "weighted_peak_min_count": settings.weighted_peak_min_count,
    }


def _publish_compact_result(
    *,
    locked: _LockedReference,
    parent_fiber_axis: AxisRef,
    subject_axis: AxisRef,
    fiber_score_settings: NormativeFiberScoreSettings,
    support_profile: DeltaReferenceSupportProfile,
    support_rows: np.ndarray,
    total: np.ndarray,
    full_out_fraction: np.ndarray,
    support_labels: tuple[str, ...],
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
    full_scores: np.ndarray,
    fold_scores: np.ndarray,
    publisher: ArtifactPublisher,
) -> DeltaReferenceBundle:
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
            "model_family": "normative_fiber",
            "support_status": support_status,
            "matched_reference_endpoint_id": locked.endpoint_id,
            "matched_reference_connectome_id": locked.connectome_id,
            "reference_record_type": locked.record_type,
            "parent_fiber_axis_sha256": parent_fiber_axis.sha256,
            "valid_union_axis_sha256": locked.selected_axis.sha256,
            "selected_reference_tau": locked.selected_tau,
            "selected_reference_coverage": locked.selected_coverage,
            "threshold_rule": (
                "reference_component_exposure_not_below_selected_reference_tau"
            ),
            "support_scope": "complete_parent_fiber_axis",
            "out_support_fraction_formula": (
                "count(suprathreshold fibers outside finite valid support) / "
                "count(all suprathreshold fibers)"
            ),
            "support_fields": list(support_labels),
            "fiber_score_settings": _score_settings_payload(
                fiber_score_settings
            ),
            "full_finite_valid_count": int(np.count_nonzero(full_valid)),
            "fold_finite_valid_counts": [
                int(value) for value in np.sum(fold_valid, axis=1)
            ],
            "zero_total_suprathreshold_count": int(
                np.count_nonzero(total == 0)
            ),
            "cohort_median_out_support_fraction": (
                float(np.median(finite_full)) if finite_full.size else None
            ),
            "subject_fraction_over_0p50": (
                float(np.mean(finite_full > 0.50))
                if finite_full.size
                else None
            ),
            "subject_fraction_over_0p80": (
                float(np.mean(finite_full > 0.80))
                if finite_full.size
                else None
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
        axis_id=f"{subject_axis.axis_id}:delta-reference-fiber-support-fields",
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
            selected_reference_tau=locked.selected_tau,
            selected_reference_coverage=locked.selected_coverage,
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
        selected_reference_tau=locked.selected_tau,
        selected_reference_coverage=locked.selected_coverage,
        full_scores=full_artifact,
        fold_scores=fold_artifact,
        support_rows=support_artifact,
        support_qc=support_qc_artifact,
    )


def build_delta_reference_fiber(
    *,
    matched_reference_endpoint_id: str,
    matched_reference_connectome_id: str,
    reference_record: ReferenceRecord,
    parent_fiber_ids: ScientificArray,
    valid_fiber_ids: ScientificArray,
    full_weights: ScientificArray,
    fold_weights: ScientificArray,
    fold_valid_masks: ScientificArray,
    reference_condition_exposure: ScientificArray,
    addon_reference_component_exposure: ScientificArray,
    subject_axis: AxisRef,
    reference_subject_axis: AxisRef,
    addon_subject_ids: tuple[str, ...],
    reference_subject_ids: tuple[str, ...],
    parent_fiber_axis: AxisRef,
    fiber_score_settings: NormativeFiberScoreSettings,
    support_profile: DeltaReferenceSupportProfile,
    publisher: ArtifactPublisher,
    artifact_store: ArtifactStore | None = None,
    reference_parent_fiber_axis: AxisRef | None = None,
) -> DeltaReferenceBundle:
    """Build full/fold fiber DeltaReferenceScore artifacts without refitting."""

    if (
        not isinstance(subject_axis, AxisRef)
        or not isinstance(reference_subject_axis, AxisRef)
        or not isinstance(parent_fiber_axis, AxisRef)
    ):
        raise TypeError(
            "subject_axis, reference_subject_axis, and parent_fiber_axis must be AxisRef values"
        )
    if reference_parent_fiber_axis is not None and not isinstance(
        reference_parent_fiber_axis,
        AxisRef,
    ):
        raise TypeError("reference_parent_fiber_axis must be an AxisRef or None")
    selected_axis_parent = (
        parent_fiber_axis
        if reference_parent_fiber_axis is None
        else reference_parent_fiber_axis
    )
    if not isinstance(fiber_score_settings, NormativeFiberScoreSettings):
        raise TypeError(
            "fiber_score_settings must be a NormativeFiberScoreSettings"
        )
    if not isinstance(publisher, ArtifactPublisher):
        raise TypeError("publisher must implement ArtifactPublisher")
    if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
        raise TypeError("artifact_store must be an ArtifactStore or None")
    _validate_support_profile(support_profile)
    locked = _locked_reference(
        reference_record,
        matched_reference_endpoint_id=matched_reference_endpoint_id,
        matched_reference_connectome_id=matched_reference_connectome_id,
    )
    try:
        fold_indices = reference_fold_indices(
            addon_subject_ids=addon_subject_ids,
            reference_subject_ids=reference_subject_ids,
            addon_subject_axis=subject_axis,
            reference_subject_axis=reference_subject_axis,
        )
    except DeltaReferenceCohortError as error:
        raise DeltaReferenceFiberError(str(error)) from error

    for value, name, kind in (
        (
            valid_fiber_ids,
            "valid_fiber_ids",
            "normative_fiber_valid_union_ids",
        ),
        (full_weights, "full_weights", "benefit_oriented_fiber_weights"),
        (
            fold_weights,
            "fold_weights",
            "loocv_benefit_oriented_fiber_weights",
        ),
        (
            fold_valid_masks,
            "fold_valid_masks",
            "loocv_valid_fiber_masks",
        ),
    ):
        _require_reference_artifact(
            value,
            locked,
            name=name,
            expected_kind=kind,
        )
    _validate_artifact_spaces(
        (
            parent_fiber_ids,
            valid_fiber_ids,
            full_weights,
            fold_weights,
            fold_valid_masks,
            reference_condition_exposure,
            addon_reference_component_exposure,
        )
    )

    parent_ids = _fiber_ids(
        _materialize(
            parent_fiber_ids,
            name="parent_fiber_ids",
            expected_axes=(parent_fiber_axis,),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "parent_fiber_ids",
        parent_fiber_axis.count,
    )
    valid_ids = _fiber_ids(
        _materialize(
            valid_fiber_ids,
            name="valid_fiber_ids",
            expected_axes=(locked.selected_axis,),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "valid_fiber_ids",
        locked.selected_axis.count,
    )
    selected_parent_positions = _parent_positions(parent_ids, valid_ids)
    _validate_selected_axis(locked, selected_axis_parent, valid_ids)

    full_weight_array = np.asarray(
        _real_array(
            _materialize(
                full_weights,
                name="full_weights",
                expected_axes=(locked.selected_axis,),
                expected_units="coefficient",
                artifact_store=artifact_store,
            ),
            "full_weights",
            1,
        ),
        dtype=np.float64,
    )
    fold_weight_array = np.asarray(
        _real_array(
            _materialize(
                fold_weights,
                name="fold_weights",
                expected_axes=(reference_subject_axis, locked.selected_axis),
                expected_units="coefficient",
                artifact_store=artifact_store,
            ),
            "fold_weights",
            2,
        ),
        dtype=np.float64,
    )
    fold_mask_array = _boolean_array(
        _materialize(
            fold_valid_masks,
            name="fold_valid_masks",
            expected_axes=(reference_subject_axis, locked.selected_axis),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "fold_valid_masks",
        2,
    )
    expected_full_shape = (locked.selected_axis.count,)
    expected_fold_shape = (
        reference_subject_axis.count,
        locked.selected_axis.count,
    )
    if full_weight_array.shape != expected_full_shape:
        raise DeltaReferenceFiberError(
            "full_weights do not match the valid-union fiber axis"
        )
    if fold_weight_array.shape != expected_fold_shape:
        raise DeltaReferenceFiberError(
            "fold_weights do not match the reference-subject and valid-union axes"
        )
    if fold_mask_array.shape != expected_fold_shape:
        raise DeltaReferenceFiberError(
            "fold_valid_masks do not match the reference-subject and valid-union axes"
        )
    if np.any(np.isinf(full_weight_array)) or np.any(
        np.isinf(fold_weight_array)
    ):
        raise DeltaReferenceFiberError(
            "invalid reference weight positions must be NaN, not infinite"
        )
    if not np.array_equal(fold_mask_array, np.isfinite(fold_weight_array)):
        raise DeltaReferenceFiberError(
            "fold_valid_masks must exactly match finite fold weight support"
        )
    addon_fold_weights = fold_weight_array[fold_indices]
    addon_fold_masks = fold_mask_array[fold_indices]

    reference_exposure = _real_array(
        _materialize(
            reference_condition_exposure,
            name="reference_condition_exposure",
            expected_axes=(subject_axis, parent_fiber_axis),
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
            expected_axes=(subject_axis, parent_fiber_axis),
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        "addon_reference_component_exposure",
        2,
    )
    expected_exposure_shape = (subject_axis.count, parent_fiber_axis.count)
    if reference_exposure.shape != expected_exposure_shape:
        raise DeltaReferenceFiberError(
            "reference_condition_exposure does not match the declared axes"
        )
    if addon_reference_exposure.shape != expected_exposure_shape:
        raise DeltaReferenceFiberError(
            "addon_reference_component_exposure does not match the declared axes"
        )
    if not np.all(np.isfinite(reference_exposure)) or not np.all(
        np.isfinite(addon_reference_exposure)
    ):
        raise DeltaReferenceFiberError(
            "reference-component exposure matrices must contain only finite values"
        )

    selected_reference_exposure = reference_exposure[:, selected_parent_positions]
    selected_addon_exposure = addon_reference_exposure[
        :,
        selected_parent_positions,
    ]
    full_valid = np.isfinite(full_weight_array)
    fold_valid = addon_fold_masks
    if not np.any(full_valid):
        raise DeltaReferenceFiberError(
            "full-sample reference weights have no finite valid support"
        )
    if np.any(np.sum(fold_valid, axis=1) == 0):
        raise DeltaReferenceFiberError(
            "every reference training fold requires finite valid support"
        )
    support_rows, total, full_out_fraction, support_labels = _support_rows(
        addon_reference_exposure,
        selected_parent_positions,
        full_valid,
        fold_valid,
        locked.selected_tau,
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
            "model_family": "normative_fiber",
            "support_status": support_status,
            "matched_reference_endpoint_id": locked.endpoint_id,
            "matched_reference_connectome_id": locked.connectome_id,
            "reference_record_type": locked.record_type,
            "parent_fiber_axis_sha256": parent_fiber_axis.sha256,
            "valid_union_axis_sha256": locked.selected_axis.sha256,
            "selected_reference_tau": locked.selected_tau,
            "selected_reference_coverage": locked.selected_coverage,
            "threshold_rule": (
                "reference_component_exposure_not_below_selected_reference_tau"
            ),
            "support_scope": "complete_parent_fiber_axis",
            "out_support_fraction_formula": (
                "count(suprathreshold fibers outside finite valid support) / "
                "count(all suprathreshold fibers)"
            ),
            "support_fields": list(support_labels),
            "fiber_score_settings": _score_settings_payload(
                fiber_score_settings
            ),
            "full_finite_valid_count": int(np.count_nonzero(full_valid)),
            "fold_finite_valid_counts": [
                int(value) for value in np.sum(fold_valid, axis=1)
            ],
            "zero_total_suprathreshold_count": int(
                np.count_nonzero(total == 0)
            ),
            "cohort_median_out_support_fraction": (
                float(np.median(finite_full)) if finite_full.size else None
            ),
            "subject_fraction_over_0p50": (
                float(np.mean(finite_full > 0.50))
                if finite_full.size
                else None
            ),
            "subject_fraction_over_0p80": (
                float(np.mean(finite_full > 0.80))
                if finite_full.size
                else None
            ),
            "maximum_required_out_support_fraction": (
                float(np.max(finite_required))
                if finite_required.size
                else None
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
        axis_id=f"{subject_axis.axis_id}:delta-reference-fiber-support-fields",
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
            selected_reference_tau=locked.selected_tau,
            selected_reference_coverage=locked.selected_coverage,
            full_scores=None,
            fold_scores=None,
            support_rows=support_artifact,
            support_qc=support_qc_artifact,
            failure_stage="support_qc",
            failure_detail=support_status,
        )

    full_scores, fold_scores, _, _ = _locked_scores(
        selected_addon_exposure,
        selected_reference_exposure,
        full_weight_array,
        addon_fold_weights,
        addon_fold_masks,
        valid_ids,
        fiber_score_settings,
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
        selected_reference_tau=locked.selected_tau,
        selected_reference_coverage=locked.selected_coverage,
        full_scores=full_artifact,
        fold_scores=fold_artifact,
        support_rows=support_artifact,
        support_qc=support_qc_artifact,
    )


def build_compact_delta_reference_fiber(
    *,
    matched_reference_endpoint_id: str,
    matched_reference_connectome_id: str,
    reference_record: ReferenceRecord,
    valid_fiber_ids: ScientificArray,
    full_weights: ScientificArray,
    fold_weights: ScientificArray,
    fold_valid_masks: ScientificArray,
    selected_reference_condition_exposure: ScientificArray,
    selected_addon_reference_component_exposure: ScientificArray,
    total_suprathreshold_count: ScientificArray,
    subject_axis: AxisRef,
    reference_subject_axis: AxisRef,
    addon_subject_ids: tuple[str, ...],
    reference_subject_ids: tuple[str, ...],
    support_parent_fiber_axis: AxisRef,
    reference_parent_fiber_axis: AxisRef,
    fiber_score_settings: NormativeFiberScoreSettings,
    support_profile: DeltaReferenceSupportProfile,
    publisher: ArtifactPublisher,
    artifact_store: ArtifactStore | None = None,
) -> DeltaReferenceBundle:
    """Rebuild fiber DeltaReferenceScore from selected rows and parent counts."""

    for axis, name in (
        (subject_axis, "subject_axis"),
        (reference_subject_axis, "reference_subject_axis"),
        (support_parent_fiber_axis, "support_parent_fiber_axis"),
        (reference_parent_fiber_axis, "reference_parent_fiber_axis"),
    ):
        if not isinstance(axis, AxisRef):
            raise TypeError(f"{name} must be an AxisRef")
    if not isinstance(fiber_score_settings, NormativeFiberScoreSettings):
        raise TypeError("fiber_score_settings must be NormativeFiberScoreSettings")
    if not isinstance(publisher, ArtifactPublisher):
        raise TypeError("publisher must implement ArtifactPublisher")
    if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
        raise TypeError("artifact_store must be an ArtifactStore or None")
    _validate_support_profile(support_profile)
    locked = _locked_reference(
        reference_record,
        matched_reference_endpoint_id=matched_reference_endpoint_id,
        matched_reference_connectome_id=matched_reference_connectome_id,
    )
    try:
        fold_indices = reference_fold_indices(
            addon_subject_ids=addon_subject_ids,
            reference_subject_ids=reference_subject_ids,
            addon_subject_axis=subject_axis,
            reference_subject_axis=reference_subject_axis,
        )
    except DeltaReferenceCohortError as error:
        raise DeltaReferenceFiberError(str(error)) from error
    for value, name, kind in (
        (valid_fiber_ids, "valid_fiber_ids", "normative_fiber_valid_union_ids"),
        (full_weights, "full_weights", "benefit_oriented_fiber_weights"),
        (
            fold_weights,
            "fold_weights",
            "loocv_benefit_oriented_fiber_weights",
        ),
        (
            fold_valid_masks,
            "fold_valid_masks",
            "loocv_valid_fiber_masks",
        ),
    ):
        _require_reference_artifact(
            value,
            locked,
            name=name,
            expected_kind=kind,
        )
    _validate_artifact_spaces(
        (
            valid_fiber_ids,
            full_weights,
            fold_weights,
            fold_valid_masks,
            selected_reference_condition_exposure,
            selected_addon_reference_component_exposure,
        )
    )
    valid_ids = _fiber_ids(
        _materialize(
            valid_fiber_ids,
            name="valid_fiber_ids",
            expected_axes=(locked.selected_axis,),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "valid_fiber_ids",
        locked.selected_axis.count,
    )
    _validate_selected_axis(locked, reference_parent_fiber_axis, valid_ids)
    full_weight_array = np.asarray(
        _real_array(
            _materialize(
                full_weights,
                name="full_weights",
                expected_axes=(locked.selected_axis,),
                expected_units="coefficient",
                artifact_store=artifact_store,
            ),
            "full_weights",
            1,
        ),
        dtype=np.float64,
    )
    fold_weight_array = np.asarray(
        _real_array(
            _materialize(
                fold_weights,
                name="fold_weights",
                expected_axes=(reference_subject_axis, locked.selected_axis),
                expected_units="coefficient",
                artifact_store=artifact_store,
            ),
            "fold_weights",
            2,
        ),
        dtype=np.float64,
    )
    fold_mask_array = _boolean_array(
        _materialize(
            fold_valid_masks,
            name="fold_valid_masks",
            expected_axes=(reference_subject_axis, locked.selected_axis),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "fold_valid_masks",
        2,
    )
    if not np.array_equal(fold_mask_array, np.isfinite(fold_weight_array)):
        raise DeltaReferenceFiberError(
            "fold_valid_masks must exactly match finite fold weight support"
        )
    reference_exposure = _real_array(
        _materialize(
            selected_reference_condition_exposure,
            name="selected_reference_condition_exposure",
            expected_axes=(subject_axis, locked.selected_axis),
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        "selected_reference_condition_exposure",
        2,
    )
    addon_reference_exposure = _real_array(
        _materialize(
            selected_addon_reference_component_exposure,
            name="selected_addon_reference_component_exposure",
            expected_axes=(subject_axis, locked.selected_axis),
            expected_units="V/m",
            artifact_store=artifact_store,
        ),
        "selected_addon_reference_component_exposure",
        2,
    )
    totals = _real_array(
        _materialize(
            total_suprathreshold_count,
            name="total_suprathreshold_count",
            expected_axes=(subject_axis,),
            expected_units=None,
            artifact_store=artifact_store,
        ),
        "total_suprathreshold_count",
        1,
    )
    expected_selected_shape = (subject_axis.count, locked.selected_axis.count)
    if (
        full_weight_array.shape != (locked.selected_axis.count,)
        or fold_weight_array.shape
        != (reference_subject_axis.count, locked.selected_axis.count)
        or fold_mask_array.shape
        != (reference_subject_axis.count, locked.selected_axis.count)
        or reference_exposure.shape != expected_selected_shape
        or addon_reference_exposure.shape != expected_selected_shape
        or totals.shape != (subject_axis.count,)
        or not np.all(np.isfinite(reference_exposure))
        or not np.all(np.isfinite(addon_reference_exposure))
        or not np.all(np.isfinite(totals))
        or np.any(totals < 0.0)
        or np.any(totals > support_parent_fiber_axis.count)
        or np.any(totals != np.floor(totals))
    ):
        raise DeltaReferenceFiberError(
            "compact DeltaReferenceScore arrays do not match their declared axes"
        )
    addon_fold_weights = fold_weight_array[fold_indices]
    addon_fold_masks = fold_mask_array[fold_indices]
    full_scores, fold_scores, full_valid, fold_valid = _locked_scores(
        addon_reference_exposure,
        reference_exposure,
        full_weight_array,
        addon_fold_weights,
        addon_fold_masks,
        valid_ids,
        fiber_score_settings,
    )
    support_rows, total, full_out_fraction, support_labels = (
        _support_rows_from_selected(
            addon_reference_exposure >= locked.selected_tau,
            np.asarray(totals, dtype=np.int64),
            full_valid,
            fold_valid,
        )
    )
    return _publish_compact_result(
        locked=locked,
        parent_fiber_axis=support_parent_fiber_axis,
        subject_axis=subject_axis,
        fiber_score_settings=fiber_score_settings,
        support_profile=support_profile,
        support_rows=support_rows,
        total=total,
        full_out_fraction=full_out_fraction,
        support_labels=support_labels,
        full_valid=full_valid,
        fold_valid=fold_valid,
        full_scores=full_scores,
        fold_scores=fold_scores,
        publisher=publisher,
    )


__all__ = [
    "DeltaReferenceFiberError",
    "build_compact_delta_reference_fiber",
    "build_delta_reference_fiber",
]
