#!/usr/bin/env python3
"""Smoke/equivalence tests for the shared STN/SNr statistical kernel."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from stnsnr_four_model_stats import (
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    fiber_net_score,
    fold_coverage_by_subtraction,
    freedman_lane_permuted_outcomes,
    mean_map_score,
    partial_spearman_loop_reference,
    partial_spearman_matrix,
    plus_one_two_sided_p,
    suprathreshold_matrix,
)


def _assert_close(name: str, observed: np.ndarray | float, expected: np.ndarray | float, atol: float = 1e-12) -> None:
    if not np.allclose(observed, expected, equal_nan=True, atol=atol, rtol=0):
        raise AssertionError(f"{name} mismatch\nobserved={observed}\nexpected={expected}")


def run_selftest() -> dict[str, object]:
    rng = np.random.default_rng(42)
    y = np.array([42, 37, 39, 35, 31, 34, 30, 28], dtype=float)
    baseline = np.array([58, 55, 55, 52, 47, 50, 44, 43], dtype=float)
    exposure = np.array(
        [
            [210, 900, 0, 400, 5, 1, 15],
            [220, 850, 5, 410, 5, 2, 14],
            [180, 810, 2, 405, 5, 1, 13],
            [250, 780, 0, 390, 5, 3, 12],
            [260, 700, 8, 420, 5, 4, 11],
            [230, 760, 7, 415, 5, 5, 10],
            [270, 640, 9, 430, 5, 6, 9],
            [280, 620, 10, 440, 5, 7, 8],
        ],
        dtype=float,
    )
    exposure += rng.normal(0, 0.01, exposure.shape)
    exposure[:, 4] = 5.0

    rho_vec = partial_spearman_matrix(y, exposure, baseline)
    rho_ref = partial_spearman_loop_reference(y, exposure, baseline)
    _assert_close("partial_spearman_vectorized_vs_reference", rho_vec, rho_ref, atol=1e-12)

    weights = benefit_oriented_weights(rho_vec, "lower")
    if not np.allclose(weights, -rho_vec, equal_nan=True):
        raise AssertionError("lower-is-better benefit orientation failed")

    s_tau = suprathreshold_matrix(exposure, 200)
    coverage_all = coverage_from_suprathreshold(s_tau)
    for heldout in range(exposure.shape[0]):
        by_subtraction = fold_coverage_by_subtraction(s_tau, heldout)
        brute = s_tau[np.arange(exposure.shape[0]) != heldout].sum(axis=0)
        _assert_close(f"coverage_fold_{heldout}", by_subtraction, brute)

    mask = candidate_mask_from_coverage(coverage_all, 3)
    scores, n_valid = mean_map_score(exposure, weights, mask)
    manual = exposure[:, mask & np.isfinite(weights)] @ weights[mask & np.isfinite(weights)] / n_valid
    _assert_close("mean_map_score", scores, manual)

    fiber_weights = np.array([0.4, 0.3, -0.5, -0.2, np.nan, 0.0, 0.1], dtype=float)
    fiber_candidate = np.array([True, True, True, True, True, True, True])
    net = fiber_net_score(exposure, fiber_weights, fiber_candidate)
    expected_sweet = np.mean(
        np.column_stack(
            [
                exposure[:, 0] * 0.4,
                exposure[:, 1] * 0.3,
                exposure[:, 6] * 0.1,
            ]
        ),
        axis=1,
    )
    expected_sour = np.mean(
        np.column_stack(
            [
                exposure[:, 2] * 0.5,
                exposure[:, 3] * 0.2,
            ]
        ),
        axis=1,
    )
    _assert_close("fiber_sweet_peak", net.sweet_peak5, expected_sweet)
    _assert_close("fiber_sour_peak", net.sour_peak5, expected_sour)
    _assert_close("fiber_net_score", net.net_score, expected_sweet - expected_sour)
    _assert_close("fiber_sweet_ids", net.sweet_fiber_ids, np.array([0, 1, 6]))
    _assert_close("fiber_sour_ids", net.sour_fiber_ids, np.array([2, 3]))
    if net.fiber_score_support_status != "limited_two_sign":
        raise AssertionError(f"unexpected fiber support status {net.fiber_score_support_status}")

    perm_a = freedman_lane_permuted_outcomes(y, baseline, n_perm=5, seed=42)
    perm_b = freedman_lane_permuted_outcomes(y, baseline, n_perm=5, seed=42)
    _assert_close("freedman_lane_seed_reproducibility", perm_a, perm_b)
    if perm_a.shape != (5, y.shape[0]):
        raise AssertionError(f"unexpected Freedman-Lane shape {perm_a.shape}")

    p_value = plus_one_two_sided_p(0.5, np.array([0.1, -0.6, 0.2, 0.8]))
    _assert_close("plus_one_two_sided_p", p_value, 3 / 5)

    return {
        "status": "PASS",
        "n_subjects": int(exposure.shape[0]),
        "n_features": int(exposure.shape[1]),
        "partial_spearman_max_abs_diff": float(np.nanmax(np.abs(rho_vec - rho_ref))),
        "coverage_all": coverage_all.astype(int).tolist(),
        "n_score_features": int(n_valid),
        "fiber_sweet_ids": net.sweet_fiber_ids.astype(int).tolist(),
        "fiber_sour_ids": net.sour_fiber_ids.astype(int).tolist(),
        "freedman_lane_shape": list(perm_a.shape),
        "plus_one_p_example": p_value,
    }


def main() -> int:
    result = run_selftest()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
