"""Pure individualized target-burden observed-model kernels."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...contracts import HardComputabilityLimits
from ..direct_voxel.kernel import (
    GridCellArrays,
    GridCellComputation,
    GridCellMetrics,
)
from ..nuisance import NuisancePlan
from ..statistics import (
    benjamini_hochberg,
    benefit_oriented_weights,
    classify_prediction_status,
    linear_prediction,
    partial_spearman_coefficients_and_pvalues,
    safe_correlation,
)


class IndividualizedTargetKernelError(ValueError):
    """Raised when target-burden inputs violate the numerical contract."""


@dataclass(frozen=True)
class TargetCellArrays:
    """Retained arrays for one selected individualized target cell."""

    full_support_mask: np.ndarray
    full_valid_mask: np.ndarray
    full_weights: np.ndarray
    full_nominal_p: np.ndarray
    full_fdr_q: np.ndarray
    full_centers: np.ndarray
    full_scales: np.ndarray
    full_scores: np.ndarray
    fold_support_masks: np.ndarray
    fold_valid_masks: np.ndarray
    fold_weights: np.ndarray
    fold_centers: np.ndarray
    fold_scales: np.ndarray
    fold_scores: np.ndarray
    heldout_scores: np.ndarray
    heldout_predictions: np.ndarray
    baseline_predictions: np.ndarray
    score_slopes: np.ndarray


@dataclass(frozen=True)
class TargetCellComputation:
    """Metrics and optional retained arrays for one target grid cell."""

    metrics: GridCellMetrics
    arrays: TargetCellArrays | None


def _target_scaling(
    exposure: np.ndarray,
    valid_mask: np.ndarray,
    training_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return training-only centers, scales, and the usable target mask."""

    x = np.asarray(exposure, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool)
    train = np.asarray(training_rows, dtype=bool)
    if x.ndim != 2 or valid.shape != (x.shape[1],):
        raise IndividualizedTargetKernelError(
            "target exposure and valid_mask must share the target axis"
        )
    if train.shape != (x.shape[0],) or not np.any(train):
        raise IndividualizedTargetKernelError(
            "training_rows must select at least one subject"
        )
    centers = np.full(x.shape[1], np.nan, dtype=np.float64)
    scales = np.full(x.shape[1], np.nan, dtype=np.float64)
    candidate_indices = np.flatnonzero(valid)
    if candidate_indices.size:
        candidate = x[train][:, candidate_indices]
        with np.errstate(invalid="ignore"):
            centers[candidate_indices] = np.nanmean(candidate, axis=0)
            scales[candidate_indices] = np.nanstd(candidate, axis=0)
    usable = (
        valid
        & np.isfinite(centers)
        & np.isfinite(scales)
        & (scales > 0)
    )
    return centers, scales, usable


def score_target_operator(
    exposure: np.ndarray,
    weights: np.ndarray,
    valid_mask: np.ndarray,
    training_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return fold-standardized weighted scores and the usable target mask."""

    x = np.asarray(exposure, dtype=np.float64)
    weight_array = np.asarray(weights, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool) & np.isfinite(weight_array)
    if x.ndim != 2 or weight_array.shape != (x.shape[1],):
        raise IndividualizedTargetKernelError(
            "target exposure and weights must share the target axis"
        )
    train = np.asarray(training_rows, dtype=bool)
    if train.shape != (x.shape[0],) or not np.any(train):
        raise IndividualizedTargetKernelError(
            "training_rows must select at least one subject"
        )
    centers, scales, usable = _target_scaling(x, valid, train)
    if not np.any(usable):
        return (
            np.full(x.shape[0], np.nan, dtype=np.float64),
            usable,
            centers,
            scales,
        )
    standardized = (x[:, usable] - centers[usable]) / scales[usable]
    selected_weights = weight_array[usable]
    finite = np.isfinite(standardized)
    numerator = np.nansum(standardized * selected_weights[None, :], axis=1)
    denominator = np.sum(
        finite * np.abs(selected_weights)[None, :],
        axis=1,
    )
    scores = np.full(x.shape[0], np.nan, dtype=np.float64)
    rows = denominator > 0
    scores[rows] = numerator[rows] / denominator[rows]
    return scores, usable, centers, scales


def apply_target_operator(
    exposure: np.ndarray,
    weights: np.ndarray,
    centers: np.ndarray,
    scales: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Apply one already-fitted target operator without refitting scaling."""

    x = np.asarray(exposure, dtype=np.float64)
    weight_array = np.asarray(weights, dtype=np.float64)
    center_array = np.asarray(centers, dtype=np.float64)
    scale_array = np.asarray(scales, dtype=np.float64)
    valid = (
        np.asarray(valid_mask, dtype=bool)
        & np.isfinite(weight_array)
        & np.isfinite(center_array)
        & np.isfinite(scale_array)
        & (scale_array > 0)
    )
    if (
        x.ndim != 2
        or weight_array.shape != (x.shape[1],)
        or center_array.shape != weight_array.shape
        or scale_array.shape != weight_array.shape
        or valid.shape != weight_array.shape
        or not np.any(valid)
    ):
        raise IndividualizedTargetKernelError(
            "fitted target operator is not usable on the exposure axis"
        )
    standardized = (
        x[:, valid] - center_array[valid][None, :]
    ) / scale_array[valid][None, :]
    finite = np.isfinite(standardized)
    selected_weights = weight_array[valid]
    numerator = np.nansum(
        standardized * selected_weights[None, :],
        axis=1,
    )
    denominator = np.sum(
        finite * np.abs(selected_weights)[None, :],
        axis=1,
    )
    scores = np.full(x.shape[0], np.nan, dtype=np.float64)
    rows = denominator > 0
    scores[rows] = numerator[rows] / denominator[rows]
    return scores


def _baseline_predictions(
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
) -> np.ndarray:
    predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    all_rows = np.arange(outcome.size)
    for heldout in range(outcome.size):
        train = np.delete(all_rows, heldout)
        prediction, _ = linear_prediction(
            outcome[train],
            None,
            nuisance_plan.fold_covariates[heldout, train],
            None,
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        predictions[heldout] = prediction[0]
    return predictions


def _empty_metrics(
    tau: float,
    coverage: int,
    subject_count: int,
    limits: HardComputabilityLimits,
    reason: str,
) -> GridCellMetrics:
    passes_subjects = subject_count >= limits.n_subjects_min
    return GridCellMetrics(
        tau=float(tau),
        coverage=int(coverage),
        n_subjects=subject_count,
        n_features_full=0,
        n_valid_full_features=0,
        fold_n_features_min=0,
        fold_n_features_median=0.0,
        fold_n_features_max=0,
        score_nonconstant_all_folds=False,
        all_predictions_finite=False,
        loocv_spearman_rho=math.nan,
        loocv_spearman_nominal_p=math.nan,
        loocv_pearson_r=math.nan,
        loocv_pearson_nominal_p=math.nan,
        q2=math.nan,
        mae_model=math.nan,
        mae_baseline=math.nan,
        rmse_model=math.nan,
        rmse_baseline=math.nan,
        full_score_baseline_pearson_r=math.nan,
        full_score_baseline_spearman_rho=math.nan,
        score_slope_median=math.nan,
        score_slope_min=math.nan,
        score_slope_max=math.nan,
        passes_n_subjects=passes_subjects,
        passes_n_features_full=False,
        passes_fold_n_features_min=False,
        passes_score_nonconstant=False,
        passes_predictions_finite=False,
        passes_hard_computability=False,
        prediction_status="not_applicable",
        failure_reasons=(reason,),
    )


def evaluate_target_cell(
    exposure: np.ndarray,
    support: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    outcome_direction: str,
    tau: float,
    coverage: int,
    limits: HardComputabilityLimits,
    *,
    retain_arrays: bool = False,
) -> TargetCellComputation:
    """Evaluate one tau/Coverage cell using target support and burden."""

    x = np.asarray(exposure, dtype=np.float64)
    support_array = np.asarray(support, dtype=bool)
    y = np.asarray(outcome, dtype=np.float64)
    if x.ndim != 2 or support_array.shape != x.shape:
        raise IndividualizedTargetKernelError(
            "target burden and support must be matching subject-by-target matrices"
        )
    if y.shape != (x.shape[0],) or not np.all(np.isfinite(y)):
        raise IndividualizedTargetKernelError(
            "outcome must be a finite subject vector"
        )
    if not isinstance(nuisance_plan, NuisancePlan):
        raise IndividualizedTargetKernelError("nuisance_plan is invalid")
    if nuisance_plan.full_covariates.shape[0] != y.size:
        raise IndividualizedTargetKernelError(
            "nuisance plan does not match the subject axis"
        )
    if (
        not isinstance(limits, HardComputabilityLimits)
        or limits.n_features_full_min is None
        or limits.fold_n_features_min is None
    ):
        raise IndividualizedTargetKernelError(
            "individualized targets require full and fold target minima"
        )
    if not math.isfinite(float(tau)) or float(tau) <= 0:
        raise IndividualizedTargetKernelError("tau must be finite and positive")
    if type(coverage) is not int or coverage < 1:
        raise IndividualizedTargetKernelError(
            "coverage must be a positive integer"
        )

    subject_count, target_count = x.shape
    full_coverage = support_array.sum(axis=0)
    full_support = full_coverage >= coverage
    full_candidate_count = int(full_support.sum())
    if full_candidate_count == 0:
        return TargetCellComputation(
            _empty_metrics(
                tau,
                coverage,
                subject_count,
                limits,
                "empty_full_sample_support",
            ),
            None,
        )

    full_coefficients, supported_nominal_p = (
        partial_spearman_coefficients_and_pvalues(
            y,
            x[:, full_support],
            nuisance_plan.full_covariates,
        )
    )
    full_weights = np.full(target_count, np.nan, dtype=np.float64)
    full_nominal_p = np.full(target_count, np.nan, dtype=np.float64)
    full_fdr_q = np.full(target_count, np.nan, dtype=np.float64)
    full_weights[full_support] = benefit_oriented_weights(
        full_coefficients,
        outcome_direction,
    )
    full_nominal_p[full_support] = supported_nominal_p
    full_fdr_q[full_support] = benjamini_hochberg(supported_nominal_p)
    all_rows = np.ones(subject_count, dtype=bool)
    full_scores, full_valid, full_centers, full_scales = score_target_operator(
        x,
        full_weights,
        full_support & np.isfinite(full_weights),
        all_rows,
    )
    full_valid_count = int(full_valid.sum())
    if full_valid_count == 0:
        return TargetCellComputation(
            _empty_metrics(
                tau,
                coverage,
                subject_count,
                limits,
                "no_valid_full_sample_weights",
            ),
            None,
        )

    baseline_predictions = _baseline_predictions(y, nuisance_plan)
    heldout_predictions = np.full(subject_count, np.nan, dtype=np.float64)
    heldout_scores = np.full(subject_count, np.nan, dtype=np.float64)
    score_slopes = np.full(subject_count, np.nan, dtype=np.float64)
    fold_target_counts = np.zeros(subject_count, dtype=np.int32)
    fold_support_masks = np.zeros((subject_count, target_count), dtype=bool)
    fold_valid_masks = np.zeros((subject_count, target_count), dtype=bool)
    fold_weights = np.full(
        (subject_count, target_count),
        np.nan,
        dtype=np.float64,
    )
    fold_centers = np.full(
        (subject_count, target_count),
        np.nan,
        dtype=np.float64,
    )
    fold_scales = np.full(
        (subject_count, target_count),
        np.nan,
        dtype=np.float64,
    )
    fold_scores = np.full(
        (subject_count, subject_count),
        np.nan,
        dtype=np.float64,
    )
    failure_reasons: list[str] = []
    score_nonconstant = True

    for heldout in range(subject_count):
        train = np.ones(subject_count, dtype=bool)
        train[heldout] = False
        fold_coverage = full_coverage - support_array[heldout].astype(np.int64)
        fold_support = fold_coverage >= coverage
        fold_support_masks[heldout] = fold_support
        fold_target_counts[heldout] = int(fold_support.sum())
        if not np.any(fold_support):
            score_nonconstant = False
            failure_reasons.append(f"empty_fold_{heldout}")
            continue
        coefficients, _ = partial_spearman_coefficients_and_pvalues(
            y[train],
            x[train][:, fold_support],
            nuisance_plan.fold_covariates[heldout, train],
        )
        weights = np.full(target_count, np.nan, dtype=np.float64)
        weights[fold_support] = benefit_oriented_weights(
            coefficients,
            outcome_direction,
        )
        scores, valid, centers, scales = score_target_operator(
            x,
            weights,
            fold_support & np.isfinite(weights),
            train,
        )
        fold_weights[heldout] = weights
        fold_valid_masks[heldout] = valid
        fold_centers[heldout] = centers
        fold_scales[heldout] = scales
        fold_scores[heldout] = scores
        if (
            not np.any(valid)
            or not np.all(np.isfinite(scores[train]))
            or np.std(scores[train]) == 0
            or not np.isfinite(scores[heldout])
        ):
            score_nonconstant = False
            failure_reasons.append(
                f"constant_or_nonfinite_training_score_fold_{heldout}"
            )
            continue
        prediction, beta = linear_prediction(
            y[train],
            scores[train],
            nuisance_plan.fold_covariates[heldout, train],
            scores[[heldout]],
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        heldout_predictions[heldout] = prediction[0]
        heldout_scores[heldout] = scores[heldout]
        if beta.size > 1:
            score_slopes[heldout] = beta[1]

    all_predictions_finite = bool(
        np.all(np.isfinite(heldout_predictions))
        and np.all(np.isfinite(baseline_predictions))
    )
    spearman_rho, spearman_p = safe_correlation(
        y,
        heldout_predictions,
        method="spearman",
    )
    pearson_r, pearson_p = safe_correlation(
        y,
        heldout_predictions,
        method="pearson",
    )
    model_error = y - heldout_predictions
    baseline_error = y - baseline_predictions
    mae_model = (
        float(np.mean(np.abs(model_error)))
        if np.all(np.isfinite(model_error))
        else math.nan
    )
    rmse_model = (
        float(np.sqrt(np.mean(model_error**2)))
        if np.all(np.isfinite(model_error))
        else math.nan
    )
    mae_baseline = (
        float(np.mean(np.abs(baseline_error)))
        if np.all(np.isfinite(baseline_error))
        else math.nan
    )
    rmse_baseline = (
        float(np.sqrt(np.mean(baseline_error**2)))
        if np.all(np.isfinite(baseline_error))
        else math.nan
    )
    baseline_sse = (
        float(np.sum(baseline_error**2))
        if np.all(np.isfinite(baseline_error))
        else math.nan
    )
    q2 = (
        1.0 - float(np.sum(model_error**2)) / baseline_sse
        if math.isfinite(baseline_sse)
        and baseline_sse > 0
        and np.all(np.isfinite(model_error))
        else math.nan
    )
    baseline_column = nuisance_plan.full_covariates[:, 0]
    full_pearson, _ = safe_correlation(
        full_scores,
        baseline_column,
        method="pearson",
    )
    full_spearman, _ = safe_correlation(
        full_scores,
        baseline_column,
        method="spearman",
    )
    passes_subjects = subject_count >= limits.n_subjects_min
    passes_full = full_candidate_count >= limits.n_features_full_min
    passes_fold = int(fold_target_counts.min()) >= limits.fold_n_features_min
    passes_hard = bool(
        passes_subjects
        and passes_full
        and passes_fold
        and score_nonconstant
        and all_predictions_finite
    )
    prediction_status = (
        classify_prediction_status(
            mae_model,
            mae_baseline,
            rmse_model,
            rmse_baseline,
        )
        if passes_hard
        else "not_applicable"
    )
    finite_slopes = score_slopes[np.isfinite(score_slopes)]
    metrics = GridCellMetrics(
        tau=float(tau),
        coverage=int(coverage),
        n_subjects=subject_count,
        n_features_full=full_candidate_count,
        n_valid_full_features=full_valid_count,
        fold_n_features_min=int(fold_target_counts.min()),
        fold_n_features_median=float(np.median(fold_target_counts)),
        fold_n_features_max=int(fold_target_counts.max()),
        score_nonconstant_all_folds=score_nonconstant,
        all_predictions_finite=all_predictions_finite,
        loocv_spearman_rho=spearman_rho,
        loocv_spearman_nominal_p=spearman_p,
        loocv_pearson_r=pearson_r,
        loocv_pearson_nominal_p=pearson_p,
        q2=q2,
        mae_model=mae_model,
        mae_baseline=mae_baseline,
        rmse_model=rmse_model,
        rmse_baseline=rmse_baseline,
        full_score_baseline_pearson_r=full_pearson,
        full_score_baseline_spearman_rho=full_spearman,
        score_slope_median=(
            float(np.median(finite_slopes)) if finite_slopes.size else math.nan
        ),
        score_slope_min=(
            float(np.min(finite_slopes)) if finite_slopes.size else math.nan
        ),
        score_slope_max=(
            float(np.max(finite_slopes)) if finite_slopes.size else math.nan
        ),
        passes_n_subjects=passes_subjects,
        passes_n_features_full=passes_full,
        passes_fold_n_features_min=passes_fold,
        passes_score_nonconstant=score_nonconstant,
        passes_predictions_finite=all_predictions_finite,
        passes_hard_computability=passes_hard,
        prediction_status=prediction_status,
        failure_reasons=tuple(failure_reasons),
    )
    arrays = (
        TargetCellArrays(
            full_support_mask=full_support,
            full_valid_mask=full_valid,
            full_weights=full_weights,
            full_nominal_p=full_nominal_p,
            full_fdr_q=full_fdr_q,
            full_centers=full_centers,
            full_scales=full_scales,
            full_scores=full_scores,
            fold_support_masks=fold_support_masks,
            fold_valid_masks=fold_valid_masks,
            fold_weights=fold_weights,
            fold_centers=fold_centers,
            fold_scales=fold_scales,
            fold_scores=fold_scores,
            heldout_scores=heldout_scores,
            heldout_predictions=heldout_predictions,
            baseline_predictions=baseline_predictions,
            score_slopes=score_slopes,
        )
        if retain_arrays
        else None
    )
    return TargetCellComputation(metrics=metrics, arrays=arrays)


class IndividualizedTargetGridWorkspace:
    """Evaluate tau-indexed target burdens over one Coverage grid."""

    def __init__(
        self,
        burdens: np.ndarray,
        support: np.ndarray,
        tau_values: tuple[float, ...],
        outcome: np.ndarray,
        nuisance_plan: NuisancePlan,
        outcome_direction: str,
        limits: HardComputabilityLimits,
    ) -> None:
        burden_array = np.asarray(burdens, dtype=np.float64)
        support_array = np.asarray(support, dtype=bool)
        if burden_array.ndim != 3 or support_array.shape != burden_array.shape:
            raise IndividualizedTargetKernelError(
                "burdens and support must be matching tau-by-subject-by-target arrays"
            )
        values = tuple(float(value) for value in tau_values)
        if burden_array.shape[0] != len(values):
            raise IndividualizedTargetKernelError(
                "burden tau dimension does not match tau_values"
            )
        self.burdens = burden_array
        self.support = support_array
        self.tau_values = values
        self.outcome = np.asarray(outcome, dtype=np.float64)
        self.nuisance_plan = nuisance_plan
        self.outcome_direction = outcome_direction
        self.limits = limits

    def evaluate_cell(
        self,
        tau: float,
        coverage: int,
        *,
        retain_arrays: bool = False,
    ) -> TargetCellComputation:
        try:
            index = self.tau_values.index(float(tau))
        except ValueError as exc:
            raise IndividualizedTargetKernelError(
                "tau is outside the prepared target grid"
            ) from exc
        return evaluate_target_cell(
            self.burdens[index],
            self.support[index],
            self.outcome,
            self.nuisance_plan,
            self.outcome_direction,
            tau,
            coverage,
            self.limits,
            retain_arrays=retain_arrays,
        )

    def evaluate_grid(
        self,
        coverage_values: tuple[int, ...],
    ) -> tuple[GridCellMetrics, ...]:
        return tuple(
            self.evaluate_cell(tau, coverage).metrics
            for tau in self.tau_values
            for coverage in coverage_values
        )


__all__ = [
    "IndividualizedTargetGridWorkspace",
    "IndividualizedTargetKernelError",
    "TargetCellArrays",
    "TargetCellComputation",
    "apply_target_operator",
    "evaluate_target_cell",
    "score_target_operator",
]
