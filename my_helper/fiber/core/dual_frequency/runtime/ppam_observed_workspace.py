"""Persistence boundary for pPAM observed state and operator scratch."""

from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path

import numpy as np

from ..backends.activation.operator_scratch import (
    PPAMOperatorScratchDescriptor,
    _publish_ppam_operator_scratch,
    cleanup_ppam_operator_scratch,
    close_ppam_operator_scratch,
    open_ppam_operator_scratch,
    reopen_ppam_permutation_workspace,
)
from ..backends.activation.fitting import (
    PPAMFitResult,
    PPAMObservedState,
    PPAMPermutationWorkspace,
)
from ..backends.formal.operator_scratch import ScratchArrayDescriptor
from ..contracts import (
    ActivationArtifact,
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    FinalModelRecord,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    PPAMObservedWorkspaceRecord,
    ScratchArrayRecord,
    canonical_hash,
)
from ..backends.formal.common import materialize_array
from ..backends.protocols import ArtifactPublisher


class PPAMObservedWorkspaceError(RuntimeError):
    """Raised when a durable pPAM workspace cannot be bound or reopened."""


def publish_ppam_operator_scratch(
    parent: Path,
    workspace: PPAMPermutationWorkspace,
) -> PPAMOperatorScratchDescriptor:
    """Publish one run-scoped pPAM operator generation."""

    return _publish_ppam_operator_scratch(parent, workspace)


def _artifact(value: object, field: str) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise PPAMObservedWorkspaceError(
            f"persisted pPAM {field} must be an ArtifactRef"
        )
    return value


def _artifact_identity(value: ArtifactRef | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "kind": value.kind,
        "schema_version": value.schema_version,
        "sha256": value.sha256,
        "dtype": value.dtype,
        "shape": value.shape,
        "axis_hashes": value.axis_hashes,
        "units": value.units,
        "space": value.space,
    }


def ppam_observed_input_identity(
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
) -> str:
    """Bind one durable pPAM workspace to exact scientific content."""

    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    activation_probability = _artifact(
        request.activation_probability,
        "activation_probability",
    )
    outcome = _artifact(request.outcome, "outcome")
    baseline = _artifact(request.baseline, "baseline")
    peak = _artifact(request.peak_final_score, "peak_final_score")
    feature_ids = _artifact(request.feature_ids, "feature_ids")
    activation_feature_ids = _artifact(
        request.activation_feature_ids,
        "activation_feature_ids",
    )
    overlap = (
        None
        if request.reference_overlap_mask is None
        else _artifact(request.reference_overlap_mask, "reference_overlap_mask")
    )
    nuisance = tuple(
        _artifact(value, f"nuisance_inputs[{index}]")
        for index, value in enumerate(request.nuisance_inputs)
    )
    return canonical_hash(
        {
            "schema_version": "dual_frequency_ppam_observed_input_v1",
            "final_model_id": request.final_model.identifier,
            "final_branch": request.final_model.final_key.final_branch,
            "subject_axis": asdict(request.subject_axis),
            "feature_axis": asdict(request.feature_axis),
            "activation_probability": _artifact_identity(activation_probability),
            "binary_exposure": _artifact_identity(binary),
            "outcome": _artifact_identity(outcome),
            "baseline": _artifact_identity(baseline),
            "peak_final_score": _artifact_identity(peak),
            "feature_ids": _artifact_identity(feature_ids),
            "activation_feature_ids": _artifact_identity(
                activation_feature_ids
            ),
            "reference_overlap_mask": _artifact_identity(overlap),
            "nuisance_inputs": tuple(
                _artifact_identity(value) for value in nuisance
            ),
            "outcome_direction": request.outcome_direction,
            "hard_computability": asdict(request.hard_computability),
            "connectome_role": request.connectome_role,
            "fiber_score_settings": asdict(request.fiber_score_settings),
            "fitting_probability_threshold": (
                request.fitting_probability_threshold
            ),
            "permutation_resamples": request.permutation_resamples,
            "seed": request.seed,
        }
    )


def activation_request_from_ppam_workspace(
    record: PPAMObservedWorkspaceRecord,
    final_model: FinalModelRecord,
) -> ActivationRequest:
    """Reconstruct the exact typed request without a physical OSS provider."""

    if not isinstance(record, PPAMObservedWorkspaceRecord):
        raise PPAMObservedWorkspaceError("pPAM observed workspace record is invalid")
    if not isinstance(final_model, FinalModelRecord):
        raise PPAMObservedWorkspaceError("pPAM final model is invalid")
    if (
        record.target_id != final_model.identifier
        or record.model_family != final_model.endpoint.model_family
        or record.final_branch != final_model.final_key.final_branch
        or record.feature_axis != final_model.valid_feature_axis.axis
    ):
        raise PPAMObservedWorkspaceError(
            "pPAM observed workspace does not match the final model"
        )
    return ActivationRequest(
        final_model=final_model,
        activation_probability=record.activation_probability,
        reference_overlap_mask=record.reference_overlap_mask,
        outcome=record.outcome,
        baseline=record.baseline,
        peak_final_score=record.peak_final_score,
        nuisance_inputs=record.nuisance_inputs,
        subject_axis=record.subject_axis,
        feature_axis=record.feature_axis,
        feature_ids=record.feature_ids,
        activation_feature_ids=record.activation_feature_ids,
        outcome_direction=record.outcome_direction,
        hard_computability=HardComputabilityLimits(
            record.n_subjects_min,
            None,
            record.fold_n_features_min,
        ),
        connectome_role="formal",
        fiber_score_settings=NormativeFiberScoreSettings(
            sweet_fraction=record.sweet_fraction,
            sour_fraction=record.sour_fraction,
            weighted_peak_fraction=record.weighted_peak_fraction,
            sweet_selected_min_count=record.sweet_selected_min_count,
            sour_selected_min_count=record.sour_selected_min_count,
            weighted_peak_min_count=record.weighted_peak_min_count,
        ),
        fitting_probability_threshold=record.fitting_probability_threshold,
        permutation_resamples=record.permutation_resamples,
        seed=record.seed,
    )


def _json_number(value: float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _document_finite_count(
    value: object,
    field: str,
    maximum: int,
) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise PPAMObservedWorkspaceError(
            f"pPAM observed {field} is not a valid finite count"
        )
    return value


def _document_number(value: object, field: str) -> float:
    if value is None:
        return math.nan
    if type(value) not in {int, float}:
        raise PPAMObservedWorkspaceError(
            f"pPAM observed {field} is not numeric"
        )
    number = float(value)
    if not math.isfinite(number):
        raise PPAMObservedWorkspaceError(
            f"pPAM observed {field} is not finite"
        )
    return number


_PPAM_PUBLIC_OBSERVED_ARRAY_KINDS = (
    "oss_fiber_ids",
    "oss_benefit_oriented_fiber_weights",
    "oss_loocv_benefit_oriented_fiber_weights",
    "oss_full_net_fiber_scores",
    "oss_loocv_fold_net_fiber_scores",
    "oss_loocv_heldout_net_fiber_scores",
    "oss_loocv_model_predictions",
    "oss_loocv_baseline_predictions",
    "oss_plain_activation_count",
    "oss_plain_activation_sum",
    "oss_plain_activation_top5",
)


def publish_ppam_nuisance_failure(
    request: ActivationRequest,
    reason: str,
    detail: str,
    publisher: ArtifactPublisher,
) -> tuple[ArtifactRef, ...]:
    """Publish one reason-coded operator-free nuisance failure state."""

    artifact = publisher.document(
        "ppam_observed_state.json",
        {
            "schema_version": "dual_frequency_ppam_observed_state_v1",
            "final_model_id": request.final_model.identifier,
            "technical_status": "nuisance_not_estimable",
            "failure_reason": str(reason),
            "failure_detail": str(detail),
        },
        kind="ppam_observed_state",
    )
    return (artifact,)


def publish_ppam_observed_state(
    state: PPAMObservedState,
    fiber_ids: np.ndarray,
    publisher: ArtifactPublisher,
) -> tuple[ArtifactRef, ...]:
    """Publish operator-free observed arrays and strict state documents."""

    if not isinstance(state, PPAMObservedState):
        raise PPAMObservedWorkspaceError("pPAM observed state is invalid")
    request = state.request
    ids = np.asarray(fiber_ids, dtype=np.int64)
    if ids.shape != (request.feature_axis.count,):
        raise PPAMObservedWorkspaceError("pPAM observed fiber IDs are invalid")
    outcome_units = (
        request.outcome.units
        if isinstance(request.outcome, ArtifactRef)
        else None
    )
    arrays = (
        publisher.array(
            "oss_fiber_ids.npy",
            ids,
            kind="oss_fiber_ids",
            axes=(request.feature_axis,),
            units="fiber_id",
            space="right_canonical",
        ),
        publisher.array(
            "oss_full_weights.npy",
            state.full_weights,
            kind="oss_benefit_oriented_fiber_weights",
            axes=(request.feature_axis,),
            units="coefficient",
            space="right_canonical",
        ),
        publisher.array(
            "oss_fold_weights.npy",
            state.fold_weights,
            kind="oss_loocv_benefit_oriented_fiber_weights",
            axes=(request.subject_axis, request.feature_axis),
            units="coefficient",
            space="right_canonical",
        ),
        publisher.array(
            "oss_full_scores.npy",
            state.full_scores,
            kind="oss_full_net_fiber_scores",
            axes=(request.subject_axis,),
            units="weighted_binary_activation",
            space=None,
        ),
        publisher.array(
            "oss_fold_scores.npy",
            state.fold_scores,
            kind="oss_loocv_fold_net_fiber_scores",
            axes=(request.subject_axis, request.subject_axis),
            units="weighted_binary_activation",
            space=None,
        ),
        publisher.array(
            "oss_heldout_scores.npy",
            state.heldout_scores,
            kind="oss_loocv_heldout_net_fiber_scores",
            axes=(request.subject_axis,),
            units="weighted_binary_activation",
            space=None,
        ),
        publisher.array(
            "oss_loocv_predictions.npy",
            state.predictions,
            kind="oss_loocv_model_predictions",
            axes=(request.subject_axis,),
            units=outcome_units,
            space=None,
        ),
        publisher.array(
            "oss_baseline_predictions.npy",
            state.baseline_predictions,
            kind="oss_loocv_baseline_predictions",
            axes=(request.subject_axis,),
            units=outcome_units,
            space=None,
        ),
        publisher.array(
            "oss_plain_activation_count.npy",
            state.plain_activation_count,
            kind="oss_plain_activation_count",
            axes=(request.subject_axis,),
            units="fiber_count",
            space=None,
        ),
        publisher.array(
            "oss_plain_activation_sum.npy",
            state.plain_activation_sum,
            kind="oss_plain_activation_sum",
            axes=(request.subject_axis,),
            units="binary_activation_sum",
            space=None,
        ),
        publisher.array(
            "oss_plain_activation_top5.npy",
            state.plain_activation_top5,
            kind="oss_plain_activation_top5",
            axes=(request.subject_axis,),
            units="binary_activation",
            space=None,
        ),
    )
    support = publisher.document(
        "oss_fiber_score_support.json",
        {
            "schema_version": "dual_frequency_ppam_support_v1",
            "full_sample": state.full_support,
            "folds": list(state.fold_support),
        },
        kind="oss_fiber_score_support",
    )
    comparison = publisher.document(
        "oss_plain_activation_model_comparison.json",
        {
            "schema_version": "dual_frequency_ppam_plain_control_v1",
            "models": list(state.plain_model_comparisons),
            "interpretation": "burden_or_placement_qc_only",
            "classification_feedback": False,
        },
        kind="oss_plain_activation_model_comparison",
    )
    state_artifact = publisher.document(
        "ppam_observed_state.json",
        {
            "schema_version": "dual_frequency_ppam_observed_state_v1",
            "final_model_id": request.final_model.identifier,
            "technical_status": (
                "permutation_ready"
                if state.can_permute
                else "observed_not_permutation_ready"
            ),
            "full_support": state.full_support,
            "fold_support": list(state.fold_support),
            "finite_full_weights": state.finite_full_weights,
            "finite_fold_weights": [
                int(value) for value in state.finite_fold_weights
            ],
            "performance": {
                key: _json_number(value)
                for key, value in state.performance.items()
            },
            "peak_score_pearson_r": _json_number(state.peak_score_pearson_r),
            "failure_reasons": list(state.failure_reasons),
            "plain_model_comparisons": list(state.plain_model_comparisons),
        },
        kind="ppam_observed_state",
    )
    return (*arrays, support, comparison, state_artifact)


def _observed_artifact(
    record: PPAMObservedWorkspaceRecord,
    kind: str,
) -> ArtifactRef:
    matches = tuple(
        artifact for artifact in record.observed_artifacts if artifact.kind == kind
    )
    if len(matches) != 1:
        raise PPAMObservedWorkspaceError(
            f"pPAM observed artifact {kind!r} is missing or duplicated"
        )
    return matches[0]


def _materialize_observed_array(
    record: PPAMObservedWorkspaceRecord,
    kind: str,
    axes: tuple[AxisRef, ...],
    units: str | None,
    space: str | None,
    artifact_store: object,
) -> np.ndarray:
    return materialize_array(
        _observed_artifact(record, kind),
        name=kind,
        expected_axes=axes,
        expected_units=units,
        expected_space=space,
        artifact_store=artifact_store,
    )


def load_ppam_observed_state(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    artifact_store: object,
) -> PPAMObservedState:
    """Restore one operator-free observed state from its exact artifact set."""

    if record.technical_status == "nuisance_not_estimable":
        raise PPAMObservedWorkspaceError(
            "nuisance-failed pPAM workspace has no observed numerical state"
        )
    materialize_document = getattr(artifact_store, "materialize_document", None)
    if not callable(materialize_document):
        raise PPAMObservedWorkspaceError(
            "pPAM observed state requires an ArtifactStore"
        )
    state_artifact = _observed_artifact(record, "ppam_observed_state")
    payload = materialize_document(
        state_artifact,
        expected_kind="ppam_observed_state",
    )
    if (
        payload.get("schema_version")
        != "dual_frequency_ppam_observed_state_v1"
        or payload.get("final_model_id") != request.final_model.identifier
        or payload.get("technical_status") != record.technical_status
    ):
        raise PPAMObservedWorkspaceError(
            "pPAM observed state document does not match its record"
        )
    failures = payload.get("failure_reasons")
    finite_full = payload.get("finite_full_weights")
    finite_fold = payload.get("finite_fold_weights")
    performance = payload.get("performance")
    full_support = payload.get("full_support")
    fold_support = payload.get("fold_support")
    comparisons = payload.get("plain_model_comparisons")
    if (
        not isinstance(failures, list)
        or not all(type(value) is str for value in failures)
        or not isinstance(finite_fold, list)
        or len(finite_fold) != request.subject_axis.count
        or not isinstance(performance, dict)
        or not all(type(key) is str and key for key in performance)
        or not isinstance(full_support, dict)
        or not isinstance(fold_support, list)
        or len(fold_support) != request.subject_axis.count
        or not all(isinstance(value, dict) for value in fold_support)
        or not isinstance(comparisons, list)
        or not all(isinstance(value, dict) for value in comparisons)
    ):
        raise PPAMObservedWorkspaceError("pPAM observed state document is malformed")
    finite_full_count = _document_finite_count(
        finite_full,
        "finite_full_weights",
        request.feature_axis.count,
    )
    finite_fold_counts = np.asarray(
        [
            _document_finite_count(
                value,
                f"finite_fold_weights[{index}]",
                request.feature_axis.count,
            )
            for index, value in enumerate(finite_fold)
        ],
        dtype=np.int64,
    )
    numeric_performance = {
        key: _document_number(value, f"performance.{key}")
        for key, value in performance.items()
    }
    peak = _document_number(
        payload.get("peak_score_pearson_r"),
        "peak_score_pearson_r",
    )
    if (
        record.technical_status == "permutation_ready" and failures
    ) or (
        record.technical_status == "observed_not_permutation_ready"
        and not failures
    ):
        raise PPAMObservedWorkspaceError(
            "pPAM observed failure state contradicts its technical status"
        )
    outcome_units = record.outcome.units
    subject = (record.subject_axis,)
    feature = (record.feature_axis,)
    subject_feature = (record.subject_axis, record.feature_axis)
    subject_subject = (record.subject_axis, record.subject_axis)
    _materialize_observed_array(
        record,
        "oss_fiber_ids",
        feature,
        "fiber_id",
        "right_canonical",
        artifact_store,
    )
    return PPAMObservedState(
        request=request,
        full_weights=_materialize_observed_array(
            record,
            "oss_benefit_oriented_fiber_weights",
            feature,
            "coefficient",
            "right_canonical",
            artifact_store,
        ),
        fold_weights=_materialize_observed_array(
            record,
            "oss_loocv_benefit_oriented_fiber_weights",
            subject_feature,
            "coefficient",
            "right_canonical",
            artifact_store,
        ),
        full_scores=_materialize_observed_array(
            record,
            "oss_full_net_fiber_scores",
            subject,
            "weighted_binary_activation",
            None,
            artifact_store,
        ),
        fold_scores=_materialize_observed_array(
            record,
            "oss_loocv_fold_net_fiber_scores",
            subject_subject,
            "weighted_binary_activation",
            None,
            artifact_store,
        ),
        heldout_scores=_materialize_observed_array(
            record,
            "oss_loocv_heldout_net_fiber_scores",
            subject,
            "weighted_binary_activation",
            None,
            artifact_store,
        ),
        predictions=_materialize_observed_array(
            record,
            "oss_loocv_model_predictions",
            subject,
            outcome_units,
            None,
            artifact_store,
        ),
        baseline_predictions=_materialize_observed_array(
            record,
            "oss_loocv_baseline_predictions",
            subject,
            outcome_units,
            None,
            artifact_store,
        ),
        full_support=full_support,
        fold_support=tuple(fold_support),
        finite_full_weights=finite_full_count,
        finite_fold_weights=finite_fold_counts,
        performance=numeric_performance,
        peak_score_pearson_r=peak,
        failure_reasons=tuple(failures),
        plain_activation_count=_materialize_observed_array(
            record,
            "oss_plain_activation_count",
            subject,
            "fiber_count",
            None,
            artifact_store,
        ),
        plain_activation_sum=_materialize_observed_array(
            record,
            "oss_plain_activation_sum",
            subject,
            "binary_activation_sum",
            None,
            artifact_store,
        ),
        plain_activation_top5=_materialize_observed_array(
            record,
            "oss_plain_activation_top5",
            subject,
            "binary_activation",
            None,
            artifact_store,
        ),
        plain_model_comparisons=tuple(comparisons),
    )


def _nuisance_failure_payload(
    record: PPAMObservedWorkspaceRecord,
    artifact_store: object,
) -> tuple[str, str]:
    materialize_document = getattr(artifact_store, "materialize_document", None)
    if not callable(materialize_document):
        raise PPAMObservedWorkspaceError(
            "pPAM nuisance state requires an ArtifactStore"
        )
    payload = materialize_document(
        _observed_artifact(record, "ppam_observed_state"),
        expected_kind="ppam_observed_state",
    )
    reason = payload.get("failure_reason")
    detail = payload.get("failure_detail")
    if (
        payload.get("schema_version")
        != "dual_frequency_ppam_observed_state_v1"
        or payload.get("final_model_id") != record.target_id
        or payload.get("technical_status") != "nuisance_not_estimable"
        or type(reason) is not str
        or not reason
        or type(detail) is not str
        or not detail
    ):
        raise PPAMObservedWorkspaceError("pPAM nuisance state document is malformed")
    return reason, detail


def publish_ppam_activation_result(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    result: PPAMFitResult | None,
    publisher: ArtifactPublisher,
    artifact_store: object,
) -> ActivationArtifact:
    """Publish the historical public activation contract from durable state."""

    if record.technical_status == "nuisance_not_estimable":
        if result is not None:
            raise PPAMObservedWorkspaceError(
                "nuisance-failed pPAM state cannot receive a fit result"
            )
        reason, detail = _nuisance_failure_payload(record, artifact_store)
        status = publisher.document(
            "oss_status.json",
            {
                "schema_version": "dual_frequency_ppam_fit_status_v1",
                "final_model_id": request.final_model.identifier,
                "oss_sensitivity_status": "failed_oss_design_or_prediction",
                "failure_reasons": [reason],
                "detail": detail,
                "reference_overlap_applied": (
                    request.reference_overlap_mask is not None
                ),
                "classification_feedback": False,
                "status": "completed_with_technical_failure",
            },
            kind="oss_sensitivity_status",
        )
        return ActivationArtifact(
            final_model_id=request.final_model.identifier,
            feature_axis=request.feature_axis,
            activation_probability=record.activation_probability,
            binary_exposure=record.binary_exposure,
            artifacts=(status,),
        )
    if not isinstance(result, PPAMFitResult):
        raise PPAMObservedWorkspaceError(
            "pPAM observed state requires a complete fit result"
        )
    observed_arrays = tuple(
        _observed_artifact(record, kind)
        for kind in _PPAM_PUBLIC_OBSERVED_ARRAY_KINDS
    )
    support = _observed_artifact(record, "oss_fiber_score_support")
    comparison = _observed_artifact(
        record,
        "oss_plain_activation_model_comparison",
    )
    permutation_axis = AxisRef(
        axis_id=f"{request.subject_axis.axis_id}:oss-permutation",
        count=request.permutation_resamples,
        sha256=canonical_hash(
            {
                "final_model_id": request.final_model.identifier,
                "count": request.permutation_resamples,
                "seed": request.seed,
            }
        ),
    )
    null = publisher.array(
        "oss_permutation_null.npy",
        result.permutation_null,
        kind="oss_permutation_null_statistics",
        axes=(permutation_axis,),
        units="loocv_spearman_rho",
        space=None,
    )
    summary = publisher.document(
        "oss_permutation_summary.json",
        {
            "schema_version": "dual_frequency_ppam_permutation_v1",
            "B": request.permutation_resamples,
            "seed": request.seed,
            "observed_loocv_spearman_rho": _json_number(
                result.performance["loocv_spearman_rho"]
            ),
            "p_plus_one_two_sided": _json_number(
                result.permutation_p_plus_one_two_sided
            ),
            "null_finite_count": int(
                np.count_nonzero(np.isfinite(result.permutation_null))
            ),
            "status": (
                "complete"
                if np.all(np.isfinite(result.permutation_null))
                else "not_complete"
            ),
        },
        kind="oss_permutation_summary",
    )
    status = publisher.document(
        "oss_status.json",
        {
            "schema_version": "dual_frequency_ppam_fit_status_v1",
            "final_model_id": request.final_model.identifier,
            "oss_sensitivity_status": result.status,
            "failure_reasons": list(result.failure_reasons),
            "n_subjects": request.subject_axis.count,
            "n_fixed_axis_fibers": request.feature_axis.count,
            "n_finite_full_sample_weights": result.finite_full_weights,
            "fold_n_finite_weight_fibers_min": int(
                np.min(result.finite_fold_weights)
            ),
            "fold_n_finite_weight_fibers_median": float(
                np.median(result.finite_fold_weights)
            ),
            "fold_n_finite_weight_fibers_max": int(
                np.max(result.finite_fold_weights)
            ),
            "corr_net_score_oss_vs_peak": _json_number(
                result.peak_score_pearson_r
            ),
            "performance": {
                key: _json_number(value)
                for key, value in result.performance.items()
            },
            "permutation_p_plus_one_two_sided": _json_number(
                result.permutation_p_plus_one_two_sided
            ),
            "candidate_axis_rule": "final.valid_feature_axis",
            "candidate_axis_rescanned": False,
            "reference_overlap_applied": (
                request.reference_overlap_mask is not None
            ),
            "classification_feedback": False,
            "status": "completed",
        },
        kind="oss_sensitivity_status",
    )
    return ActivationArtifact(
        final_model_id=request.final_model.identifier,
        feature_axis=request.feature_axis,
        activation_probability=record.activation_probability,
        binary_exposure=record.binary_exposure,
        artifacts=(
            *observed_arrays,
            null,
            support,
            summary,
            comparison,
            status,
        ),
    )


def ppam_observed_workspace_record(
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
    observed_artifacts: tuple[ArtifactRef, ...],
    technical_status: str,
    run_root: Path,
    descriptor: PPAMOperatorScratchDescriptor | None,
) -> PPAMObservedWorkspaceRecord:
    """Convert one observed state and optional scratch to a durable record."""

    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    activation_probability = _artifact(
        request.activation_probability,
        "activation_probability",
    )
    outcome = _artifact(request.outcome, "outcome")
    baseline = _artifact(request.baseline, "baseline")
    peak = _artifact(request.peak_final_score, "peak_final_score")
    feature_ids = _artifact(request.feature_ids, "feature_ids")
    activation_feature_ids = _artifact(
        request.activation_feature_ids,
        "activation_feature_ids",
    )
    overlap = (
        None
        if request.reference_overlap_mask is None
        else _artifact(request.reference_overlap_mask, "reference_overlap_mask")
    )
    nuisance = tuple(
        _artifact(value, f"nuisance_inputs[{index}]")
        for index, value in enumerate(request.nuisance_inputs)
    )
    family = request.final_model.endpoint.model_family
    if descriptor is None:
        operator_schema = None
        generation_path = None
        arrays: tuple[ScratchArrayRecord, ...] = ()
    else:
        if descriptor.model_family != family:
            raise PPAMObservedWorkspaceError(
                "pPAM scratch model family does not match the request"
            )
        root = Path(run_root).expanduser().resolve()
        try:
            relative = descriptor.root.resolve().relative_to(root)
        except ValueError as error:
            raise PPAMObservedWorkspaceError(
                "pPAM scratch generation is outside the run root"
            ) from error
        operator_schema = descriptor.schema_version
        generation_path = relative.as_posix()
        arrays = tuple(
            ScratchArrayRecord(
                name=item.name,
                filename=item.filename,
                dtype=item.dtype,
                shape=item.shape,
                fortran_order=item.fortran_order,
                nbytes=item.nbytes,
            )
            for item in descriptor.arrays
        )
    settings = request.fiber_score_settings
    limits = request.hard_computability
    fold_minimum = limits.fold_n_features_min
    if fold_minimum is None:
        raise PPAMObservedWorkspaceError("pPAM fold feature minimum is missing")
    return PPAMObservedWorkspaceRecord(
        target_id=request.final_model.identifier,
        model_family=family,
        final_branch=request.final_model.final_key.final_branch,
        subject_axis=request.subject_axis,
        feature_axis=request.feature_axis,
        input_identity=ppam_observed_input_identity(request, binary),
        technical_status=technical_status,
        outcome_direction=request.outcome_direction,
        n_subjects_min=limits.n_subjects_min,
        fold_n_features_min=fold_minimum,
        sweet_fraction=settings.sweet_fraction,
        sour_fraction=settings.sour_fraction,
        weighted_peak_fraction=settings.weighted_peak_fraction,
        sweet_selected_min_count=settings.sweet_selected_min_count,
        sour_selected_min_count=settings.sour_selected_min_count,
        weighted_peak_min_count=settings.weighted_peak_min_count,
        fitting_probability_threshold=request.fitting_probability_threshold,
        permutation_resamples=request.permutation_resamples,
        seed=request.seed,
        activation_probability=activation_probability,
        binary_exposure=binary,
        outcome=outcome,
        baseline=baseline,
        peak_final_score=peak,
        feature_ids=feature_ids,
        activation_feature_ids=activation_feature_ids,
        reference_overlap_mask=overlap,
        nuisance_inputs=nuisance,
        observed_artifacts=tuple(observed_artifacts),
        operator_schema=operator_schema,
        generation_path=generation_path,
        arrays=arrays,
        total_nbytes=sum(item.nbytes for item in arrays),
    )


def ppam_operator_scratch_descriptor(
    record: PPAMObservedWorkspaceRecord,
    run_root: Path,
) -> PPAMOperatorScratchDescriptor:
    """Resolve one recorded pPAM generation beneath the current run work root."""

    if not isinstance(record, PPAMObservedWorkspaceRecord):
        raise PPAMObservedWorkspaceError("pPAM observed workspace record is invalid")
    if (
        record.operator_schema is None
        or record.generation_path is None
        or not record.arrays
    ):
        raise PPAMObservedWorkspaceError("pPAM observed workspace has no scratch")
    root = Path(run_root).expanduser().resolve()
    work_root = (root / "work").resolve()
    generation = (root / record.generation_path).resolve()
    if generation == work_root or not generation.is_relative_to(work_root):
        raise PPAMObservedWorkspaceError(
            "pPAM scratch generation is outside the current run work root"
        )
    return PPAMOperatorScratchDescriptor(
        schema_version=record.operator_schema,
        model_family=record.model_family,
        root=generation,
        arrays=tuple(
            ScratchArrayDescriptor(
                name=item.name,
                filename=item.filename,
                dtype=item.dtype,
                shape=item.shape,
                fortran_order=item.fortran_order,
                nbytes=item.nbytes,
            )
            for item in record.arrays
        ),
    )


def _record_matches_request(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
) -> bool:
    settings = request.fiber_score_settings
    limits = request.hard_computability
    family = request.final_model.endpoint.model_family
    return bool(
        record.technical_status != "nuisance_not_estimable"
        and record.target_id == request.final_model.identifier
        and record.model_family == family
        and record.final_branch == request.final_model.final_key.final_branch
        and record.subject_axis == request.subject_axis
        and record.feature_axis == request.feature_axis
        and record.input_identity
        == ppam_observed_input_identity(request, binary_exposure)
        and record.outcome_direction == request.outcome_direction
        and record.n_subjects_min == limits.n_subjects_min
        and record.fold_n_features_min == limits.fold_n_features_min
        and record.sweet_fraction == settings.sweet_fraction
        and record.sour_fraction == settings.sour_fraction
        and record.weighted_peak_fraction == settings.weighted_peak_fraction
        and record.sweet_selected_min_count
        == settings.sweet_selected_min_count
        and record.sour_selected_min_count == settings.sour_selected_min_count
        and record.weighted_peak_min_count == settings.weighted_peak_min_count
        and record.fitting_probability_threshold
        == request.fitting_probability_threshold
        and record.permutation_resamples == request.permutation_resamples
        and record.seed == request.seed
        and record.activation_probability == request.activation_probability
        and record.binary_exposure == binary_exposure
        and record.outcome == request.outcome
        and record.baseline == request.baseline
        and record.peak_final_score == request.peak_final_score
        and record.feature_ids == request.feature_ids
        and record.activation_feature_ids == request.activation_feature_ids
        and record.reference_overlap_mask == request.reference_overlap_mask
        and record.nuisance_inputs == request.nuisance_inputs
    )


def validated_ppam_operator_scratch_descriptor(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
    run_root: Path,
) -> PPAMOperatorScratchDescriptor:
    """Bind and reopen one pPAM generation for the exact activation request."""

    if not isinstance(record, PPAMObservedWorkspaceRecord):
        raise PPAMObservedWorkspaceError("pPAM observed workspace record is invalid")
    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    if not _record_matches_request(record, request, binary):
        raise PPAMObservedWorkspaceError(
            "pPAM observed workspace does not match the activation request"
        )
    descriptor = ppam_operator_scratch_descriptor(record, run_root)
    arrays = open_ppam_operator_scratch(descriptor)
    close_ppam_operator_scratch(arrays)
    return descriptor


def validate_ppam_observed_workspace_record(
    record: PPAMObservedWorkspaceRecord,
    final_model: FinalModelRecord,
    run_root: Path,
) -> None:
    """Validate one restored observed record and its optional scratch."""

    request = activation_request_from_ppam_workspace(record, final_model)
    if record.input_identity != ppam_observed_input_identity(
        request,
        record.binary_exposure,
    ):
        raise PPAMObservedWorkspaceError(
            "pPAM observed workspace input identity changed"
        )
    if record.technical_status == "nuisance_not_estimable":
        return
    validated_ppam_operator_scratch_descriptor(
        record,
        request,
        record.binary_exposure,
        run_root,
    )


def reopen_ppam_workspace_from_record(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure_ref: ArtifactRef,
    binary_exposure: np.ndarray,
    outcome: np.ndarray,
    fiber_ids: np.ndarray,
    run_root: Path,
) -> tuple[PPAMPermutationWorkspace, dict[str, np.memmap]]:
    """Validate one record and reopen its block-ready numerical workspace."""

    descriptor = validated_ppam_operator_scratch_descriptor(
        record,
        request,
        binary_exposure_ref,
        run_root,
    )
    return reopen_ppam_permutation_workspace(
        descriptor,
        request,
        binary_exposure,
        outcome,
        fiber_ids,
    )


def cleanup_ppam_observed_workspace_record(
    record: PPAMObservedWorkspaceRecord,
    run_root: Path,
) -> None:
    """Remove only one record's enumerated pPAM scratch generation."""

    if record.technical_status == "nuisance_not_estimable":
        return
    cleanup_ppam_operator_scratch(
        ppam_operator_scratch_descriptor(record, run_root)
    )


__all__ = [
    "PPAMObservedWorkspaceError",
    "activation_request_from_ppam_workspace",
    "cleanup_ppam_observed_workspace_record",
    "load_ppam_observed_state",
    "ppam_observed_input_identity",
    "ppam_observed_workspace_record",
    "ppam_operator_scratch_descriptor",
    "publish_ppam_activation_result",
    "publish_ppam_nuisance_failure",
    "publish_ppam_observed_state",
    "publish_ppam_operator_scratch",
    "reopen_ppam_workspace_from_record",
    "validate_ppam_observed_workspace_record",
    "validated_ppam_operator_scratch_descriptor",
]
