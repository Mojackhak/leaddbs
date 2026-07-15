"""Pure direct-voxel observed-model numerical kernels."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from typing import Any

import numpy as np
from scipy.stats import pearsonr, spearmanr

from ...contracts import HardComputabilityLimits


class DirectVoxelKernelError(ValueError):
    """Raised when direct-voxel numerical inputs violate the kernel contract."""


@dataclass(frozen=True)
class GridCellMetrics:
    """Scalar observed and LOOCV results for one tau/Coverage cell."""

    tau: float
    coverage: int
    n_subjects: int
    n_features_full: int
    n_valid_full_features: int
    fold_n_features_min: int
    fold_n_features_median: float
    fold_n_features_max: int
    score_nonconstant_all_folds: bool
    all_predictions_finite: bool
    loocv_spearman_rho: float
    loocv_spearman_nominal_p: float
    loocv_pearson_r: float
    loocv_pearson_nominal_p: float
    q2: float
    mae_model: float
    mae_baseline: float
    rmse_model: float
    rmse_baseline: float
    full_score_baseline_pearson_r: float
    full_score_baseline_spearman_rho: float
    score_slope_median: float
    score_slope_min: float
    score_slope_max: float
    passes_n_subjects: bool
    passes_n_features_full: bool
    passes_fold_n_features_min: bool
    passes_score_nonconstant: bool
    passes_predictions_finite: bool
    passes_hard_computability: bool
    prediction_status: str
    failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.tau)) or self.tau <= 0:
            raise DirectVoxelKernelError("grid-cell tau must be finite and positive")
        if type(self.coverage) is not int or self.coverage < 1:
            raise DirectVoxelKernelError("grid-cell coverage must be a positive integer")
        for field in (
            "n_subjects",
            "n_features_full",
            "n_valid_full_features",
            "fold_n_features_min",
            "fold_n_features_max",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise DirectVoxelKernelError(f"{field} must be a nonnegative integer")
        if (
            not math.isfinite(float(self.fold_n_features_median))
            or self.fold_n_features_median < 0
        ):
            raise DirectVoxelKernelError(
                "fold_n_features_median must be finite and nonnegative"
            )
        if self.n_valid_full_features > self.n_features_full:
            raise DirectVoxelKernelError(
                "n_valid_full_features cannot exceed n_features_full"
            )
        if not (
            self.fold_n_features_min
            <= self.fold_n_features_median
            <= self.fold_n_features_max
        ):
            raise DirectVoxelKernelError(
                "fold feature minimum, median, and maximum are inconsistent"
            )
        if self.passes_score_nonconstant != self.score_nonconstant_all_folds:
            raise DirectVoxelKernelError("score nonconstant flags are contradictory")
        if self.passes_predictions_finite != self.all_predictions_finite:
            raise DirectVoxelKernelError("prediction finite flags are contradictory")
        expected_hard = bool(
            self.passes_n_subjects
            and self.passes_n_features_full
            and self.passes_fold_n_features_min
            and self.passes_score_nonconstant
            and self.passes_predictions_finite
        )
        if self.passes_hard_computability != expected_hard:
            raise DirectVoxelKernelError("hard-computability flags are contradictory")
        if expected_hard:
            if self.prediction_status not in {"error_predictive", "error_nonpredictive"}:
                raise DirectVoxelKernelError(
                    "computable grid cells require an error-prediction status"
                )
            error_metrics = (
                self.mae_model,
                self.mae_baseline,
                self.rmse_model,
                self.rmse_baseline,
            )
            if not all(math.isfinite(value) for value in error_metrics):
                raise DirectVoxelKernelError(
                    "computable grid cells require finite error metrics"
                )
        elif self.prediction_status != "not_applicable":
            raise DirectVoxelKernelError(
                "noncomputable grid cells require prediction_status='not_applicable'"
            )
        reasons = tuple(str(reason).strip() for reason in self.failure_reasons)
        if any(not reason for reason in reasons):
            raise DirectVoxelKernelError("failure reasons must be nonempty strings")
        object.__setattr__(self, "failure_reasons", reasons)

    def as_json_dict(self) -> dict[str, Any]:
        """Return a strict-JSON representation with nonfinite values as null."""

        return _json_safe(asdict(self))


@dataclass(frozen=True)
class GridCellArrays:
    """Full-sample and fold-specific arrays retained for one selected cell."""

    full_support_mask: np.ndarray
    full_valid_mask: np.ndarray
    full_weights: np.ndarray
    full_scores: np.ndarray
    fold_support_masks: np.ndarray
    fold_valid_masks: np.ndarray
    fold_weights: np.ndarray
    fold_scores: np.ndarray
    heldout_scores: np.ndarray
    heldout_predictions: np.ndarray
    baseline_predictions: np.ndarray
    score_slopes: np.ndarray

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            value.flags.writeable = False


@dataclass(frozen=True)
class GridCellComputation:
    """One grid-cell result with optional retained numerical arrays."""

    metrics: GridCellMetrics
    arrays: GridCellArrays | None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    return value


def _real_array(value: np.ndarray, name: str, dimensions: int) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != dimensions:
        raise DirectVoxelKernelError(f"{name} must be {dimensions}-dimensional")
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise DirectVoxelKernelError(f"{name} must contain numeric values")
    if np.iscomplexobj(array):
        raise DirectVoxelKernelError(f"{name} must contain real values")
    return np.asarray(array, dtype=np.float64)


def _covariate_matrix(
    baseline: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
    n_subjects: int,
) -> np.ndarray:
    columns = [_real_array(baseline, "baseline", 1)[:, None]]
    for index, value in enumerate(nuisance_inputs):
        array = np.asarray(value)
        if array.ndim == 1:
            array = _real_array(array, f"nuisance_inputs[{index}]", 1)[:, None]
        else:
            array = _real_array(array, f"nuisance_inputs[{index}]", 2)
        columns.append(array)
    if any(value.shape[0] != n_subjects for value in columns):
        raise DirectVoxelKernelError("all nuisance inputs must match the subject axis")
    covariates = np.column_stack(columns)
    if not np.all(np.isfinite(covariates)):
        raise DirectVoxelKernelError("baseline and nuisance inputs must be finite")
    return covariates


def average_rank(values: np.ndarray) -> np.ndarray:
    """Return one-based average ranks while preserving nonfinite positions."""

    array = _real_array(values, "values", 1)
    ranks = np.full(array.shape, np.nan, dtype=np.float64)
    finite = np.isfinite(array)
    finite_values = array[finite]
    if finite_values.size == 0:
        return ranks
    order = np.argsort(finite_values, kind="mergesort")
    sorted_values = finite_values[order]
    sorted_ranks = np.empty(sorted_values.shape, dtype=np.float64)
    start = 0
    while start < sorted_values.size:
        stop = start + 1
        while stop < sorted_values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        sorted_ranks[start:stop] = (start + 1 + stop) / 2.0
        start = stop
    finite_ranks = np.empty(sorted_ranks.shape, dtype=np.float64)
    finite_ranks[order] = sorted_ranks
    ranks[finite] = finite_ranks
    return ranks


def rank_columns(matrix: np.ndarray) -> np.ndarray:
    """Rank each feature column independently."""

    array = _real_array(matrix, "matrix", 2)
    ranked = np.empty(array.shape, dtype=np.float64)
    for column in range(array.shape[1]):
        ranked[:, column] = average_rank(array[:, column])
    return ranked


def residualize(values: np.ndarray, covariates: np.ndarray) -> np.ndarray:
    """Residualize each value column against an intercept and covariates."""

    array = np.asarray(values, dtype=np.float64)
    one_dimensional = array.ndim == 1
    if one_dimensional:
        array = array[:, None]
    if array.ndim != 2:
        raise DirectVoxelKernelError("values must be one- or two-dimensional")
    covariate_array = _real_array(covariates, "covariates", 2)
    if covariate_array.shape[0] != array.shape[0]:
        raise DirectVoxelKernelError("values and covariates must share a subject axis")
    design = np.column_stack([np.ones(array.shape[0]), covariate_array])
    finite_design = np.all(np.isfinite(design), axis=1)
    output = np.full(array.shape, np.nan, dtype=np.float64)
    for column in range(array.shape[1]):
        finite = finite_design & np.isfinite(array[:, column])
        if int(finite.sum()) <= design.shape[1]:
            continue
        try:
            beta, *_ = np.linalg.lstsq(design[finite], array[finite, column], rcond=None)
        except np.linalg.LinAlgError:
            continue
        output[finite, column] = array[finite, column] - design[finite] @ beta
    return output[:, 0] if one_dimensional else output


def _pearson_columns(vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    y = _real_array(vector, "vector", 1)
    x = _real_array(matrix, "matrix", 2)
    if y.shape[0] != x.shape[0]:
        raise DirectVoxelKernelError("vector and matrix must share a subject axis")
    output = np.full(x.shape[1], np.nan, dtype=np.float64)
    for column in range(x.shape[1]):
        finite = np.isfinite(y) & np.isfinite(x[:, column])
        if int(finite.sum()) < 3:
            continue
        centered_y = y[finite] - np.mean(y[finite])
        centered_x = x[finite, column] - np.mean(x[finite, column])
        denominator = np.sqrt(np.sum(centered_y**2) * np.sum(centered_x**2))
        if denominator > 0:
            output[column] = np.sum(centered_y * centered_x) / denominator
    return output


def partial_spearman_weights(
    outcome: np.ndarray,
    exposure: np.ndarray,
    nuisance: np.ndarray,
) -> np.ndarray:
    """Compute nuisance-adjusted partial Spearman coefficients by feature."""

    y = _real_array(outcome, "outcome", 1)
    x = _real_array(exposure, "exposure", 2)
    covariates = _real_array(nuisance, "nuisance", 2)
    if y.shape[0] != x.shape[0] or y.shape[0] != covariates.shape[0]:
        raise DirectVoxelKernelError("outcome, exposure, and nuisance must share subjects")
    ranked_covariates = rank_columns(covariates)
    outcome_residual = residualize(average_rank(y), ranked_covariates)
    exposure_residual = residualize(rank_columns(x), ranked_covariates)
    return _pearson_columns(outcome_residual, exposure_residual)


def benefit_oriented_weights(coefficients: np.ndarray, outcome_direction: str) -> np.ndarray:
    """Orient coefficients so positive values consistently indicate benefit."""

    direction = str(outcome_direction).strip().lower()
    coefficients = np.asarray(coefficients, dtype=np.float64)
    if direction == "lower":
        return -coefficients
    if direction == "higher":
        return coefficients
    raise DirectVoxelKernelError("outcome_direction must be 'lower' or 'higher'")


def continuous_mean_score(
    exposure: np.ndarray,
    weights: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Score continuous exposure over the valid support selected by tau/Coverage."""

    x = _real_array(exposure, "exposure", 2)
    weight_array = _real_array(weights, "weights", 1)
    mask = np.asarray(valid_mask, dtype=bool) & np.isfinite(weight_array)
    if x.shape[1] != weight_array.size or mask.size != weight_array.size:
        raise DirectVoxelKernelError("exposure, weights, and valid_mask must share features")
    count = int(mask.sum())
    if count == 0:
        raise DirectVoxelKernelError("continuous score requires at least one valid feature")
    return x[:, mask] @ weight_array[mask] / count


def _safe_correlation(
    first: np.ndarray,
    second: np.ndarray,
    *,
    method: str,
) -> tuple[float, float]:
    first_array = np.asarray(first, dtype=np.float64)
    second_array = np.asarray(second, dtype=np.float64)
    finite = np.isfinite(first_array) & np.isfinite(second_array)
    if int(finite.sum()) < 3:
        return math.nan, math.nan
    if np.std(first_array[finite]) == 0 or np.std(second_array[finite]) == 0:
        return math.nan, math.nan
    result = pearsonr(first_array[finite], second_array[finite]) if method == "pearson" else spearmanr(
        first_array[finite], second_array[finite]
    )
    return float(result.statistic), float(result.pvalue)


def _predict(
    train_outcome: np.ndarray,
    train_score: np.ndarray | None,
    train_nuisance: np.ndarray,
    test_score: np.ndarray | None,
    test_nuisance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    train_parts = [np.ones(train_outcome.shape[0])]
    test_parts = [np.ones(test_nuisance.shape[0])]
    if train_score is not None:
        train_parts.append(train_score)
        if test_score is None:
            raise DirectVoxelKernelError("test_score is required with train_score")
        test_parts.append(test_score)
    train_parts.extend(train_nuisance[:, column] for column in range(train_nuisance.shape[1]))
    test_parts.extend(test_nuisance[:, column] for column in range(test_nuisance.shape[1]))
    train_design = np.column_stack(train_parts)
    test_design = np.column_stack(test_parts)
    if not (
        np.all(np.isfinite(train_outcome))
        and np.all(np.isfinite(train_design))
        and np.all(np.isfinite(test_design))
    ):
        return np.full(test_design.shape[0], np.nan), np.full(train_design.shape[1], np.nan)
    try:
        beta, *_ = np.linalg.lstsq(train_design, train_outcome, rcond=None)
    except np.linalg.LinAlgError:
        return np.full(test_design.shape[0], np.nan), np.full(train_design.shape[1], np.nan)
    return test_design @ beta, beta


def classify_prediction_status(
    mae_model: float,
    mae_baseline: float,
    rmse_model: float,
    rmse_baseline: float,
) -> str:
    """Classify error predictiveness using only MAE and RMSE improvement."""

    if mae_model < mae_baseline and rmse_model < rmse_baseline:
        return "error_predictive"
    return "error_nonpredictive"


def _empty_metrics(
    tau: float,
    coverage: int,
    n_subjects: int,
    limits: HardComputabilityLimits,
    reason: str,
) -> GridCellMetrics:
    passes_subjects = n_subjects >= limits.n_subjects_min
    return GridCellMetrics(
        tau=float(tau),
        coverage=int(coverage),
        n_subjects=n_subjects,
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


def evaluate_grid_cell(
    exposure: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
    outcome_direction: str,
    tau: float,
    coverage: int,
    limits: HardComputabilityLimits,
    *,
    retain_arrays: bool = False,
) -> GridCellComputation:
    """Evaluate one source cell using leakage-safe LOOCV."""

    x = _real_array(exposure, "exposure", 2)
    y = _real_array(outcome, "outcome", 1)
    if x.shape[0] != y.shape[0]:
        raise DirectVoxelKernelError("exposure and outcome must share a subject axis")
    if not np.all(np.isfinite(y)):
        raise DirectVoxelKernelError("outcome must be finite")
    if not isinstance(limits, HardComputabilityLimits):
        raise DirectVoxelKernelError("limits must be HardComputabilityLimits")
    if limits.n_features_full_min is None or limits.fold_n_features_min is None:
        raise DirectVoxelKernelError(
            "direct-voxel limits require full-sample and fold feature minima"
        )
    if not math.isfinite(float(tau)) or float(tau) <= 0:
        raise DirectVoxelKernelError("tau must be finite and positive")
    if type(coverage) is not int or coverage < 1:
        raise DirectVoxelKernelError("coverage must be a positive integer")
    nuisance = _covariate_matrix(baseline, nuisance_inputs, y.size)
    benefit_oriented_weights(np.array([0.0]), outcome_direction)

    n_subjects, n_features = x.shape
    suprathreshold = np.asarray(x > float(tau), dtype=bool)
    full_coverage = suprathreshold.sum(axis=0).astype(np.int32)
    full_support = full_coverage >= coverage
    n_features_full = int(full_support.sum())
    if n_features_full == 0:
        return GridCellComputation(
            _empty_metrics(tau, coverage, n_subjects, limits, "empty_full_sample_support"),
            None,
        )

    full_coefficients = partial_spearman_weights(y, x[:, full_support], nuisance)
    full_weights = np.full(n_features, np.nan, dtype=np.float64)
    full_weights[full_support] = benefit_oriented_weights(
        full_coefficients,
        outcome_direction,
    )
    full_valid = full_support & np.isfinite(full_weights)
    n_valid_full = int(full_valid.sum())
    if n_valid_full == 0:
        return GridCellComputation(
            _empty_metrics(tau, coverage, n_subjects, limits, "no_valid_full_sample_weights"),
            None,
        )
    full_scores = continuous_mean_score(x, full_weights, full_valid)

    heldout_predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    baseline_predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    heldout_scores = np.full(n_subjects, np.nan, dtype=np.float64)
    score_slopes = np.full(n_subjects, np.nan, dtype=np.float64)
    fold_feature_counts = np.zeros(n_subjects, dtype=np.int32)
    score_nonconstant = True
    failure_reasons: list[str] = []

    fold_support_masks = np.zeros((n_subjects, n_features), dtype=bool) if retain_arrays else None
    fold_valid_masks = np.zeros((n_subjects, n_features), dtype=bool) if retain_arrays else None
    fold_weights = np.full((n_subjects, n_features), np.nan) if retain_arrays else None
    fold_scores = np.full((n_subjects, n_subjects), np.nan) if retain_arrays else None

    for heldout in range(n_subjects):
        train_mask = np.ones(n_subjects, dtype=bool)
        train_mask[heldout] = False
        fold_coverage = full_coverage - suprathreshold[heldout].astype(np.int32)
        fold_support = fold_coverage >= coverage
        fold_feature_counts[heldout] = int(fold_support.sum())
        if fold_support_masks is not None:
            fold_support_masks[heldout] = fold_support
        if not np.any(fold_support):
            score_nonconstant = False
            failure_reasons.append(f"empty_fold_{heldout}")
            continue

        fold_coefficients = partial_spearman_weights(
            y[train_mask],
            x[train_mask][:, fold_support],
            nuisance[train_mask],
        )
        local_weights = benefit_oriented_weights(fold_coefficients, outcome_direction)
        weights = np.full(n_features, np.nan, dtype=np.float64)
        weights[fold_support] = local_weights
        valid = fold_support & np.isfinite(weights)
        if fold_valid_masks is not None:
            fold_valid_masks[heldout] = valid
        if fold_weights is not None:
            fold_weights[heldout] = weights
        if not np.any(valid):
            score_nonconstant = False
            failure_reasons.append(f"no_valid_fold_weights_{heldout}")
            continue

        scores = continuous_mean_score(x, weights, valid)
        if fold_scores is not None:
            fold_scores[heldout] = scores
        if not np.all(np.isfinite(scores[train_mask])) or np.std(scores[train_mask]) == 0:
            score_nonconstant = False
            failure_reasons.append(f"constant_or_nonfinite_training_score_fold_{heldout}")
            continue

        baseline_prediction, _ = _predict(
            y[train_mask],
            None,
            nuisance[train_mask],
            None,
            nuisance[[heldout]],
        )
        model_prediction, beta = _predict(
            y[train_mask],
            scores[train_mask],
            nuisance[train_mask],
            scores[[heldout]],
            nuisance[[heldout]],
        )
        baseline_predictions[heldout] = baseline_prediction[0]
        heldout_predictions[heldout] = model_prediction[0]
        heldout_scores[heldout] = scores[heldout]
        if beta.size > 1:
            score_slopes[heldout] = beta[1]

    all_predictions_finite = bool(
        np.all(np.isfinite(heldout_predictions))
        and np.all(np.isfinite(baseline_predictions))
    )
    spearman_rho, spearman_p = _safe_correlation(y, heldout_predictions, method="spearman")
    pearson_r, pearson_p = _safe_correlation(y, heldout_predictions, method="pearson")

    finite_model = np.isfinite(heldout_predictions)
    finite_baseline = np.isfinite(baseline_predictions)
    model_residuals = y[finite_model] - heldout_predictions[finite_model]
    baseline_residuals = y[finite_baseline] - baseline_predictions[finite_baseline]
    mae_model = float(np.mean(np.abs(model_residuals))) if model_residuals.size else math.nan
    rmse_model = float(np.sqrt(np.mean(model_residuals**2))) if model_residuals.size else math.nan
    mae_baseline = (
        float(np.mean(np.abs(baseline_residuals))) if baseline_residuals.size else math.nan
    )
    rmse_baseline = (
        float(np.sqrt(np.mean(baseline_residuals**2)))
        if baseline_residuals.size
        else math.nan
    )
    finite_q2 = finite_model & finite_baseline
    sse_model = float(np.sum((y[finite_q2] - heldout_predictions[finite_q2]) ** 2))
    sse_baseline = float(np.sum((y[finite_q2] - baseline_predictions[finite_q2]) ** 2))
    q2 = 1.0 - sse_model / sse_baseline if sse_baseline > 0 else math.nan
    full_pearson, _ = _safe_correlation(full_scores, baseline, method="pearson")
    full_spearman, _ = _safe_correlation(full_scores, baseline, method="spearman")

    passes_subjects = n_subjects >= limits.n_subjects_min
    passes_full = n_features_full >= limits.n_features_full_min
    passes_fold = int(fold_feature_counts.min()) >= limits.fold_n_features_min
    passes_hard = bool(
        passes_subjects
        and passes_full
        and passes_fold
        and score_nonconstant
        and all_predictions_finite
    )
    prediction_status = (
        classify_prediction_status(mae_model, mae_baseline, rmse_model, rmse_baseline)
        if passes_hard
        else "not_applicable"
    )
    finite_slopes = score_slopes[np.isfinite(score_slopes)]
    metrics = GridCellMetrics(
        tau=float(tau),
        coverage=int(coverage),
        n_subjects=n_subjects,
        n_features_full=n_features_full,
        n_valid_full_features=n_valid_full,
        fold_n_features_min=int(fold_feature_counts.min()),
        fold_n_features_median=float(np.median(fold_feature_counts)),
        fold_n_features_max=int(fold_feature_counts.max()),
        score_nonconstant_all_folds=score_nonconstant,
        all_predictions_finite=all_predictions_finite,
        loocv_spearman_rho=spearman_rho,
        loocv_spearman_nominal_p=spearman_p,
        loocv_pearson_r=pearson_r,
        loocv_pearson_nominal_p=pearson_p,
        q2=float(q2),
        mae_model=mae_model,
        mae_baseline=mae_baseline,
        rmse_model=rmse_model,
        rmse_baseline=rmse_baseline,
        full_score_baseline_pearson_r=full_pearson,
        full_score_baseline_spearman_rho=full_spearman,
        score_slope_median=float(np.median(finite_slopes)) if finite_slopes.size else math.nan,
        score_slope_min=float(np.min(finite_slopes)) if finite_slopes.size else math.nan,
        score_slope_max=float(np.max(finite_slopes)) if finite_slopes.size else math.nan,
        passes_n_subjects=passes_subjects,
        passes_n_features_full=passes_full,
        passes_fold_n_features_min=passes_fold,
        passes_score_nonconstant=score_nonconstant,
        passes_predictions_finite=all_predictions_finite,
        passes_hard_computability=passes_hard,
        prediction_status=prediction_status,
        failure_reasons=tuple(failure_reasons),
    )
    arrays = None
    if retain_arrays:
        if fold_support_masks is None or fold_valid_masks is None or fold_weights is None or fold_scores is None:
            raise AssertionError("retained fold arrays were not initialized")
        arrays = GridCellArrays(
            full_support_mask=full_support,
            full_valid_mask=full_valid,
            full_weights=full_weights,
            full_scores=full_scores,
            fold_support_masks=fold_support_masks,
            fold_valid_masks=fold_valid_masks,
            fold_weights=fold_weights,
            fold_scores=fold_scores,
            heldout_scores=heldout_scores,
            heldout_predictions=heldout_predictions,
            baseline_predictions=baseline_predictions,
            score_slopes=score_slopes,
        )
    return GridCellComputation(metrics=metrics, arrays=arrays)


def evaluate_grid(
    exposure: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
    outcome_direction: str,
    tau_values: tuple[float, ...],
    coverage_values: tuple[int, ...],
    limits: HardComputabilityLimits,
) -> tuple[GridCellMetrics, ...]:
    """Evaluate a complete declared grid without retaining per-cell arrays."""

    return tuple(
        evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            nuisance_inputs,
            outcome_direction,
            tau,
            coverage,
            limits,
        ).metrics
        for tau in tau_values
        for coverage in coverage_values
    )
