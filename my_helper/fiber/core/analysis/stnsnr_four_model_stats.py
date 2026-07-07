#!/usr/bin/env python3
"""Shared statistical utilities for STN/SNr four-model execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class FiberNetScoreResult:
    """Patient-level net sweet-minus-sour fiber scores."""

    sweet_peak5: np.ndarray
    sour_peak5: np.ndarray
    net_score: np.ndarray
    sweet_fiber_ids: np.ndarray
    sour_fiber_ids: np.ndarray
    n_sweet_peak_fibers: int
    n_sour_peak_fibers: int


def average_rank_1d(values: np.ndarray) -> np.ndarray:
    """Return 1-based average ranks with NaNs preserved."""
    x = np.asarray(values, dtype=float)
    ranks = np.full(x.shape, np.nan, dtype=float)
    finite = np.isfinite(x)
    finite_values = x[finite]
    if finite_values.size == 0:
        return ranks

    order = np.argsort(finite_values, kind="mergesort")
    sorted_values = finite_values[order]
    sorted_ranks = np.empty(sorted_values.shape, dtype=float)
    start = 0
    while start < sorted_values.size:
        stop = start + 1
        while stop < sorted_values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        sorted_ranks[start:stop] = (start + 1 + stop) / 2.0
        start = stop

    finite_ranks = np.empty(sorted_ranks.shape, dtype=float)
    finite_ranks[order] = sorted_ranks
    ranks[finite] = finite_ranks
    return ranks


def rank_columns(matrix: np.ndarray) -> np.ndarray:
    """Rank each column using average ranks."""
    x = np.asarray(matrix, dtype=float)
    if x.ndim == 1:
        return average_rank_1d(x)
    ranked = np.empty(x.shape, dtype=float)
    for col in range(x.shape[1]):
        ranked[:, col] = average_rank_1d(x[:, col])
    return ranked


def _as_2d_covariates(covariates: np.ndarray | None, n_rows: int) -> np.ndarray:
    if covariates is None:
        return np.empty((n_rows, 0), dtype=float)
    cov = np.asarray(covariates, dtype=float)
    if cov.ndim == 1:
        cov = cov[:, None]
    if cov.shape[0] != n_rows:
        raise ValueError(f"covariates has {cov.shape[0]} rows; expected {n_rows}")
    return cov


def residualize(values: np.ndarray, covariates: np.ndarray | None = None) -> np.ndarray:
    """Residualize one or more columns against an intercept and covariates."""
    y = np.asarray(values, dtype=float)
    one_dimensional = y.ndim == 1
    if one_dimensional:
        y = y[:, None]
    n_rows = y.shape[0]
    cov = _as_2d_covariates(covariates, n_rows)
    design = np.column_stack([np.ones(n_rows, dtype=float), cov])

    finite_rows = np.all(np.isfinite(design), axis=1)
    out = np.full(y.shape, np.nan, dtype=float)
    for col in range(y.shape[1]):
        finite = finite_rows & np.isfinite(y[:, col])
        if finite.sum() <= design.shape[1]:
            continue
        beta, *_ = np.linalg.lstsq(design[finite], y[finite, col], rcond=None)
        out[finite, col] = y[finite, col] - design[finite] @ beta
    return out[:, 0] if one_dimensional else out


def pearson_corr_columns(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Pearson correlation between one vector and each matrix column."""
    y_arr = np.asarray(y, dtype=float)
    x_arr = np.asarray(x, dtype=float)
    if x_arr.ndim == 1:
        x_arr = x_arr[:, None]
    if y_arr.shape[0] != x_arr.shape[0]:
        raise ValueError("y and x must have the same number of rows")

    out = np.full(x_arr.shape[1], np.nan, dtype=float)
    for col in range(x_arr.shape[1]):
        finite = np.isfinite(y_arr) & np.isfinite(x_arr[:, col])
        if finite.sum() < 3:
            continue
        yy = y_arr[finite] - np.mean(y_arr[finite])
        xx = x_arr[finite, col] - np.mean(x_arr[finite, col])
        denom = np.sqrt(np.sum(yy * yy) * np.sum(xx * xx))
        if denom > 0:
            out[col] = float(np.sum(yy * xx) / denom)
    return out


def partial_spearman_matrix(y: np.ndarray, exposure: np.ndarray, covariates: np.ndarray | None = None) -> np.ndarray:
    """Baseline/nuisance-adjusted partial Spearman for every feature column."""
    y_arr = np.asarray(y, dtype=float)
    x_arr = np.asarray(exposure, dtype=float)
    if x_arr.ndim != 2:
        raise ValueError("exposure must be a subject-by-feature matrix")
    if y_arr.shape[0] != x_arr.shape[0]:
        raise ValueError("y and exposure must have the same number of rows")

    cov = _as_2d_covariates(covariates, y_arr.shape[0])
    y_rank = average_rank_1d(y_arr)
    cov_rank = rank_columns(cov) if cov.shape[1] else cov
    x_rank = rank_columns(x_arr)
    y_resid = residualize(y_rank, cov_rank)
    x_resid = residualize(x_rank, cov_rank)
    return pearson_corr_columns(y_resid, x_resid)


def partial_spearman_loop_reference(y: np.ndarray, exposure: np.ndarray, covariates: np.ndarray | None = None) -> np.ndarray:
    """Slow reference implementation used by equivalence tests."""
    x_arr = np.asarray(exposure, dtype=float)
    out = np.full(x_arr.shape[1], np.nan, dtype=float)
    for col in range(x_arr.shape[1]):
        out[col] = partial_spearman_matrix(y, x_arr[:, [col]], covariates)[0]
    return out


def benefit_oriented_weights(rho: np.ndarray, scale_direction: str) -> np.ndarray:
    """Convert raw association coefficients so positive values mean benefit-associated."""
    direction = scale_direction.lower().strip()
    if direction == "lower":
        return -np.asarray(rho, dtype=float)
    if direction == "higher":
        return np.asarray(rho, dtype=float)
    raise ValueError("scale_direction must be 'lower' or 'higher'")


def suprathreshold_matrix(exposure: np.ndarray, tau: float) -> np.ndarray:
    """Boolean subject-by-feature threshold matrix."""
    return np.asarray(exposure, dtype=float) > float(tau)


def coverage_from_suprathreshold(suprathreshold: np.ndarray) -> np.ndarray:
    """Feature-wise coverage count."""
    return np.asarray(suprathreshold, dtype=bool).sum(axis=0).astype(np.int32)


def fold_coverage_by_subtraction(suprathreshold: np.ndarray, heldout_index: int) -> np.ndarray:
    """Training-fold coverage obtained by subtracting the held-out subject."""
    s = np.asarray(suprathreshold, dtype=bool)
    if heldout_index < 0 or heldout_index >= s.shape[0]:
        raise IndexError("heldout_index out of bounds")
    return coverage_from_suprathreshold(s) - s[heldout_index].astype(np.int32)


def candidate_mask_from_coverage(coverage: np.ndarray, min_coverage: int) -> np.ndarray:
    """Feature candidate mask from coverage counts."""
    return np.asarray(coverage) >= int(min_coverage)


def mean_map_score(exposure: np.ndarray, weights: np.ndarray, score_mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Voxel-style mean weighted exposure score."""
    x = np.asarray(exposure, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.asarray(score_mask, dtype=bool) & np.isfinite(w)
    n_valid = int(mask.sum())
    if n_valid == 0:
        raise ValueError("score mask contains no valid features")
    scores = x[:, mask] @ w[mask] / n_valid
    return scores, n_valid


def _ceil_count(percent: float, n_items: int) -> int:
    if n_items <= 0:
        return 0
    return max(1, int(np.ceil(float(percent) * n_items)))


def _top_mean_per_row(values: np.ndarray, percent: float) -> tuple[np.ndarray, int]:
    if values.shape[1] == 0:
        return np.zeros(values.shape[0], dtype=float), 0
    count = _ceil_count(percent, values.shape[1])
    sorted_values = np.sort(values, axis=1)[:, ::-1]
    return np.mean(sorted_values[:, :count], axis=1), count


def fiber_net_score(
    exposure: np.ndarray,
    weights: np.ndarray,
    candidate_mask: np.ndarray,
    *,
    sweet_percent: float = 0.01,
    sour_percent: float = 0.005,
    peak_percent: float = 0.05,
    fiber_ids: Iterable[int] | None = None,
) -> FiberNetScoreResult:
    """Compute NetFiberScore from selected sweet and sour fibers."""
    x = np.asarray(exposure, dtype=float)
    w = np.asarray(weights, dtype=float)
    candidate = np.asarray(candidate_mask, dtype=bool) & np.isfinite(w)
    if x.ndim != 2:
        raise ValueError("exposure must be a subject-by-fiber matrix")
    if x.shape[1] != w.shape[0]:
        raise ValueError("exposure columns and weights length differ")
    if candidate.shape[0] != w.shape[0]:
        raise ValueError("candidate_mask and weights length differ")

    ids = np.arange(w.shape[0], dtype=np.int64) if fiber_ids is None else np.asarray(fiber_ids, dtype=np.int64)
    if ids.shape[0] != w.shape[0]:
        raise ValueError("fiber_ids length differs from weights length")

    positive = candidate & (w > 0)
    negative = candidate & (w < 0)
    positive_cols = np.flatnonzero(positive)
    negative_cols = np.flatnonzero(negative)
    positive_ids = ids[positive_cols]
    negative_ids = ids[negative_cols]

    n_sweet = _ceil_count(sweet_percent, positive_ids.size)
    n_sour = _ceil_count(sour_percent, negative_ids.size)
    sweet_order = np.lexsort((positive_ids, -w[positive_cols]))
    sour_order = np.lexsort((negative_ids, w[negative_cols]))
    sweet_cols = positive_cols[sweet_order[:n_sweet]].astype(np.int64)
    sour_cols = negative_cols[sour_order[:n_sour]].astype(np.int64)
    sweet_ids = ids[sweet_cols].astype(np.int64)
    sour_ids = ids[sour_cols].astype(np.int64)

    sweet_weighted = x[:, sweet_cols] * w[sweet_cols] if sweet_cols.size else np.empty((x.shape[0], 0), dtype=float)
    sour_weighted = x[:, sour_cols] * (-w[sour_cols]) if sour_cols.size else np.empty((x.shape[0], 0), dtype=float)
    sweet_peak, n_sweet_peak = _top_mean_per_row(sweet_weighted, peak_percent)
    sour_peak, n_sour_peak = _top_mean_per_row(sour_weighted, peak_percent)
    return FiberNetScoreResult(
        sweet_peak5=sweet_peak,
        sour_peak5=sour_peak,
        net_score=sweet_peak - sour_peak,
        sweet_fiber_ids=sweet_ids,
        sour_fiber_ids=sour_ids,
        n_sweet_peak_fibers=n_sweet_peak,
        n_sour_peak_fibers=n_sour_peak,
    )


def fit_linear_prediction(
    train_y: np.ndarray,
    train_score: np.ndarray,
    train_covariates: np.ndarray | None,
    test_score: np.ndarray,
    test_covariates: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit Y ~ score + covariates on training rows and predict test rows."""
    y = np.asarray(train_y, dtype=float)
    train_score_arr = np.asarray(train_score, dtype=float)[:, None]
    test_score_arr = np.asarray(test_score, dtype=float)[:, None]
    train_cov = _as_2d_covariates(train_covariates, y.shape[0])
    test_cov = _as_2d_covariates(test_covariates, test_score_arr.shape[0])
    train_design = np.column_stack([np.ones(y.shape[0], dtype=float), train_score_arr, train_cov])
    test_design = np.column_stack([np.ones(test_score_arr.shape[0], dtype=float), test_score_arr, test_cov])
    beta, *_ = np.linalg.lstsq(train_design, y, rcond=None)
    return test_design @ beta, beta


def spearman_correlation(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman correlation using average ranks."""
    return float(pearson_corr_columns(average_rank_1d(y_true), average_rank_1d(y_pred))[0])


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray, baseline_pred: np.ndarray | None = None) -> dict[str, float]:
    """Common held-out prediction metrics."""
    y = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    finite = np.isfinite(y) & np.isfinite(pred)
    if finite.sum() == 0:
        return {"spearman_rho": np.nan, "pearson_r": np.nan, "mae": np.nan, "rmse": np.nan, "q2": np.nan}
    residual = y[finite] - pred[finite]
    metrics = {
        "spearman_rho": spearman_correlation(y[finite], pred[finite]),
        "pearson_r": float(pearson_corr_columns(y[finite], pred[finite])[0]),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "q2": np.nan,
    }
    if baseline_pred is not None:
        base = np.asarray(baseline_pred, dtype=float)
        finite_base = finite & np.isfinite(base)
        sse_model = float(np.sum((y[finite_base] - pred[finite_base]) ** 2))
        sse_base = float(np.sum((y[finite_base] - base[finite_base]) ** 2))
        if sse_base > 0:
            metrics["q2"] = 1.0 - sse_model / sse_base
    return metrics


def freedman_lane_permuted_outcomes(y: np.ndarray, nuisance: np.ndarray | None, n_perm: int, seed: int = 42) -> np.ndarray:
    """Generate Freedman-Lane outcomes for a fixed nuisance model."""
    y_arr = np.asarray(y, dtype=float)
    cov = _as_2d_covariates(nuisance, y_arr.shape[0])
    design = np.column_stack([np.ones(y_arr.shape[0], dtype=float), cov])
    beta, *_ = np.linalg.lstsq(design, y_arr, rcond=None)
    fitted = design @ beta
    resid = y_arr - fitted
    rng = np.random.default_rng(seed)
    out = np.empty((int(n_perm), y_arr.shape[0]), dtype=float)
    for idx in range(int(n_perm)):
        out[idx] = fitted + resid[rng.permutation(y_arr.shape[0])]
    return out


def plus_one_two_sided_p(stat_obs: float, stat_perm: np.ndarray) -> float:
    """Plus-one two-sided permutation p value."""
    perm = np.asarray(stat_perm, dtype=float)
    finite = np.isfinite(perm)
    count = int(np.sum(np.abs(perm[finite]) >= abs(float(stat_obs))))
    b = int(np.sum(finite))
    return float((1 + count) / (b + 1))
