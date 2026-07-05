#!/usr/bin/env python3
"""Self-tests for HF direct voxel post-hoc tau/coverage threshold scan helpers."""

from __future__ import annotations

import json

from stnsnr_hf_direct_voxel_posthoc_threshold_scan import (
    COVERAGE_GRID,
    TAU_GRID,
    build_heatmap,
    row_passes_hard_filters,
    select_best_grid_cell,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_grid_definition() -> None:
    assert_equal(TAU_GRID, [100, 150, 180, 200, 220, 250, 300, 350, 400, 500], "tau grid")
    assert_equal(COVERAGE_GRID, [5, 6, 7, 8, 10, 12], "coverage grid")
    assert_equal(len(TAU_GRID) * len(COVERAGE_GRID), 60, "grid cell count")


def test_hard_filter() -> None:
    passing = {
        "n_voxels_full": 21,
        "fold_n_voxels_min": 10,
        "hfscore_nonconstant_all_folds": True,
        "all_predictions_finite": True,
        "loocv_spearman_rho": 0.62,
        "q2": 0.33,
        "mae_model": 8.0,
        "mae_baseline": 10.0,
        "rmse_model": 10.0,
        "rmse_baseline": 12.0,
    }
    assert_equal(row_passes_hard_filters(passing), True, "passing hard filter")
    failing = dict(passing)
    failing["fold_n_voxels_min"] = 9
    assert_equal(row_passes_hard_filters(failing), False, "fold-min hard filter")


def test_selection_priority() -> None:
    rows = [
        {
            "tau": 250,
            "coverage": 10,
            "n_voxels_full": 21,
            "fold_n_voxels_min": 10,
            "hfscore_nonconstant_all_folds": True,
            "all_predictions_finite": True,
            "loocv_spearman_rho": 0.619,
            "q2": 0.327,
            "mae_model": 8.0,
            "mae_baseline": 10.0,
            "rmse_model": 10.0,
            "rmse_baseline": 12.0,
        },
        {
            "tau": 300,
            "coverage": 8,
            "n_voxels_full": 22,
            "fold_n_voxels_min": 12,
            "hfscore_nonconstant_all_folds": True,
            "all_predictions_finite": True,
            "loocv_spearman_rho": 0.7,
            "q2": 0.2,
            "mae_model": 8.0,
            "mae_baseline": 10.0,
            "rmse_model": 10.0,
            "rmse_baseline": 12.0,
        },
        {
            "tau": 200,
            "coverage": 5,
            "n_voxels_full": 200,
            "fold_n_voxels_min": 120,
            "hfscore_nonconstant_all_folds": True,
            "all_predictions_finite": True,
            "loocv_spearman_rho": -0.03,
            "q2": -0.22,
            "mae_model": 11.0,
            "mae_baseline": 10.0,
            "rmse_model": 13.0,
            "rmse_baseline": 12.0,
        },
    ]
    selected = select_best_grid_cell(rows)
    assert_equal(selected["tau"], 250, "selected tau")
    assert_equal(selected["coverage"], 10, "selected coverage")


def test_primary_distance_tie_break() -> None:
    rows = []
    for tau, coverage in [(180, 6), (220, 6)]:
        rows.append(
            {
                "tau": tau,
                "coverage": coverage,
                "n_voxels_full": 30,
                "fold_n_voxels_min": 12,
                "hfscore_nonconstant_all_folds": True,
                "all_predictions_finite": True,
                "loocv_spearman_rho": 0.2,
                "q2": 0.1,
                "mae_model": 8.0,
                "mae_baseline": 10.0,
                "rmse_model": 10.0,
                "rmse_baseline": 12.0,
            }
        )
    selected = select_best_grid_cell(rows)
    assert_equal(selected["tau"], 220, "higher tau tie break")


def test_heatmap_shape() -> None:
    rows = [
        {"tau": 100, "coverage": 5, "q2": 0.1},
        {"tau": 100, "coverage": 6, "q2": 0.2},
        {"tau": 150, "coverage": 5, "q2": 0.3},
    ]
    heatmap = build_heatmap(rows, "q2")
    assert_equal(list(heatmap.index), [100, 150], "heatmap tau index")
    assert_equal(list(heatmap.columns), [5, 6], "heatmap coverage columns")
    assert_equal(float(heatmap.loc[100, 6]), 0.2, "heatmap value")


def main() -> int:
    test_grid_definition()
    test_hard_filter()
    test_selection_priority()
    test_primary_distance_tie_break()
    test_heatmap_shape()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
