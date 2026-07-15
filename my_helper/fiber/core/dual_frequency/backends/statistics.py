"""Shared numerical helpers for observed statistical backends."""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import pearsonr, spearmanr


class StatisticsError(ValueError):
    """Raised when shared statistical inputs violate their array contracts."""


def _real_array(value: np.ndarray, name: str, dimensions: int) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != dimensions:
        raise StatisticsError(f"{name} must be {dimensions}-dimensional")
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise StatisticsError(f"{name} must contain numeric values")
    if np.iscomplexobj(array):
        raise StatisticsError(f"{name} must contain real values")
    return np.asarray(array, dtype=np.float64)


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
    """Rank each matrix column independently."""

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
        raise StatisticsError("values must be one- or two-dimensional")
    covariate_array = _real_array(covariates, "covariates", 2)
    if covariate_array.shape[0] != array.shape[0]:
        raise StatisticsError("values and covariates must share a subject axis")
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


def pearson_columns(vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Compute a finite-pair Pearson correlation for each matrix column."""

    y = _real_array(vector, "vector", 1)
    x = _real_array(matrix, "matrix", 2)
    if y.shape[0] != x.shape[0]:
        raise StatisticsError("vector and matrix must share a subject axis")
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
        raise StatisticsError("outcome, exposure, and nuisance must share subjects")
    ranked_covariates = rank_columns(covariates)
    outcome_residual = residualize(average_rank(y), ranked_covariates)
    exposure_residual = residualize(rank_columns(x), ranked_covariates)
    return pearson_columns(outcome_residual, exposure_residual)


def benefit_oriented_weights(
    coefficients: np.ndarray,
    outcome_direction: str,
) -> np.ndarray:
    """Orient coefficients so positive values consistently indicate benefit."""

    direction = str(outcome_direction).strip().lower()
    coefficients = np.asarray(coefficients, dtype=np.float64)
    if direction == "lower":
        return -coefficients
    if direction == "higher":
        return coefficients
    raise StatisticsError("outcome_direction must be 'lower' or 'higher'")


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


def safe_correlation(
    first: np.ndarray,
    second: np.ndarray,
    *,
    method: str,
) -> tuple[float, float]:
    """Return a Pearson or Spearman result, or NaNs when it is undefined."""

    first_array = np.asarray(first, dtype=np.float64)
    second_array = np.asarray(second, dtype=np.float64)
    finite = np.isfinite(first_array) & np.isfinite(second_array)
    if int(finite.sum()) < 3:
        return math.nan, math.nan
    if np.std(first_array[finite]) == 0 or np.std(second_array[finite]) == 0:
        return math.nan, math.nan
    result = (
        pearsonr(first_array[finite], second_array[finite])
        if method == "pearson"
        else spearmanr(first_array[finite], second_array[finite])
    )
    return float(result.statistic), float(result.pvalue)


def linear_prediction(
    train_outcome: np.ndarray,
    train_score: np.ndarray | None,
    train_nuisance: np.ndarray,
    test_score: np.ndarray | None,
    test_nuisance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit an ordinary least-squares model and predict the test rows."""

    train_parts = [np.ones(train_outcome.shape[0])]
    test_parts = [np.ones(test_nuisance.shape[0])]
    if train_score is not None:
        train_parts.append(train_score)
        if test_score is None:
            raise StatisticsError("test_score is required with train_score")
        test_parts.append(test_score)
    train_parts.extend(
        train_nuisance[:, column] for column in range(train_nuisance.shape[1])
    )
    test_parts.extend(
        test_nuisance[:, column] for column in range(test_nuisance.shape[1])
    )
    train_design = np.column_stack(train_parts)
    test_design = np.column_stack(test_parts)
    if not (
        np.all(np.isfinite(train_outcome))
        and np.all(np.isfinite(train_design))
        and np.all(np.isfinite(test_design))
    ):
        return np.full(test_design.shape[0], np.nan), np.full(
            train_design.shape[1], np.nan
        )
    try:
        beta, *_ = np.linalg.lstsq(train_design, train_outcome, rcond=None)
    except np.linalg.LinAlgError:
        return np.full(test_design.shape[0], np.nan), np.full(
            train_design.shape[1], np.nan
        )
    return test_design @ beta, beta


__all__ = [
    "StatisticsError",
    "average_rank",
    "benefit_oriented_weights",
    "classify_prediction_status",
    "linear_prediction",
    "partial_spearman_weights",
    "pearson_columns",
    "rank_columns",
    "residualize",
    "safe_correlation",
]
