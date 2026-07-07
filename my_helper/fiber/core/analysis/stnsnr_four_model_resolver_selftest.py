#!/usr/bin/env python3
"""Self-tests for shared STN/SNr four-model resolver helpers."""

from __future__ import annotations

import json
import math

import numpy as np

from stnsnr_four_model_resolver import (
    HF_SOURCE_ABSENT,
    HF_SOURCE_PRE_SPECIFIED,
    HF_SOURCE_SCAN_FALLBACK,
    PREDICTION_ERROR_NONPREDICTIVE,
    PREDICTION_ERROR_PREDICTIVE,
    adjacent_passing_count,
    branch_nuisance_design_status,
    classify_prediction_status,
    hard_computability_passes,
    resolve_hf_source,
    safe_pearson,
    safe_spearman,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def base_row(**overrides):
    row = {
        "tau": 200,
        "coverage": 5,
        "n_subjects": 16,
        "n_voxels_full": 30,
        "fold_n_voxels_min": 12,
        "hfscore_nonconstant_all_folds": True,
        "all_predictions_finite": True,
        "q2": -0.5,
        "loocv_spearman_rho": -0.4,
        "mae_model": 12.0,
        "mae_baseline": 10.0,
        "rmse_model": 14.0,
        "rmse_baseline": 11.0,
    }
    row.update(overrides)
    return row


def test_hard_computability_excludes_predictive_metrics() -> None:
    row = base_row()
    assert_equal(hard_computability_passes(row), True, "computability ignores q2/rho/mae/rmse")
    row["n_subjects"] = 11
    assert_equal(hard_computability_passes(row), False, "n_subjects threshold")


def test_prediction_status_uses_mae_and_rmse_only() -> None:
    row = base_row(mae_model=8.0, mae_baseline=10.0, rmse_model=9.0, rmse_baseline=11.0)
    assert_equal(classify_prediction_status(row), PREDICTION_ERROR_PREDICTIVE, "MAE and RMSE improved")
    row["rmse_model"] = 12.0
    assert_equal(classify_prediction_status(row), PREDICTION_ERROR_NONPREDICTIVE, "RMSE not improved")


def test_pre_specified_source_requires_adjacent_support() -> None:
    rows = [
        base_row(tau=200, coverage=5),
        base_row(tau=180, coverage=5),
        base_row(tau=220, coverage=6),
    ]
    resolved = resolve_hf_source(rows, primary_tau=200, primary_coverage=5)
    assert_equal(resolved["source_status"], HF_SOURCE_PRE_SPECIFIED, "pre-specified source accepted")
    assert_equal(resolved["selected_tau"], 200, "selected primary tau")
    assert_equal(resolved["selected_coverage"], 5, "selected primary coverage")
    assert_equal(resolved["selected_adjacent_passing_grid_cells"], 2, "adjacent support count")


def test_scan_fallback_priority_after_unstable_primary() -> None:
    rows = [
        base_row(tau=200, coverage=5, fold_n_voxels_min=3),
        base_row(tau=180, coverage=5, fold_n_voxels_min=12),
        base_row(tau=220, coverage=5, fold_n_voxels_min=14),
        base_row(tau=220, coverage=6, fold_n_voxels_min=14),
    ]
    resolved = resolve_hf_source(rows, primary_tau=200, primary_coverage=5)
    assert_equal(resolved["source_status"], HF_SOURCE_SCAN_FALLBACK, "fallback source accepted")
    assert_equal(resolved["selected_tau"], 220, "fallback tie chooses higher fold support before coverage")
    assert_equal(resolved["selected_coverage"], 5, "fallback selected coverage")


def test_absent_source_when_no_stable_grid() -> None:
    rows = [
        base_row(tau=200, coverage=5, n_voxels_full=0),
        base_row(tau=180, coverage=5, fold_n_voxels_min=1),
    ]
    resolved = resolve_hf_source(rows, primary_tau=200, primary_coverage=5)
    assert_equal(resolved["source_status"], HF_SOURCE_ABSENT, "absent source")
    assert_equal(resolved["prediction_status"], "not_applicable", "absent prediction status")


def test_adjacent_count_uses_grid_coordinates() -> None:
    selected = base_row(tau=200, coverage=5)
    rows = [
        selected,
        base_row(tau=180, coverage=5),
        base_row(tau=220, coverage=6),
        base_row(tau=300, coverage=12),
    ]
    assert_equal(adjacent_passing_count(rows, selected), 2, "adjacent passing cells")


def test_safe_correlations_reject_constant_vectors() -> None:
    r, p = safe_pearson(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]))
    assert_equal(math.isnan(r) and math.isnan(p), True, "constant Pearson vector")
    rho, rho_p = safe_spearman(np.array([1.0, 2.0, 3.0]), np.array([3.0, 3.0, 3.0]))
    assert_equal(math.isnan(rho) and math.isnan(rho_p), True, "constant Spearman vector")


def test_branch_nuisance_design_status() -> None:
    y_hf_ref = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    delta = np.array([1.0, 1.5, 2.5, 3.5, 5.0])
    assert_equal(
        branch_nuisance_design_status(y_hf_ref=y_hf_ref, delta_hfscore=delta),
        "valid",
        "two-covariate nuisance design",
    )
    assert_equal(
        branch_nuisance_design_status(y_hf_ref=y_hf_ref, delta_hfscore=np.ones_like(y_hf_ref)),
        "invalid_nuisance_design",
        "constant DeltaHFScore",
    )


def run_selftest() -> dict[str, object]:
    test_hard_computability_excludes_predictive_metrics()
    test_prediction_status_uses_mae_and_rmse_only()
    test_pre_specified_source_requires_adjacent_support()
    test_scan_fallback_priority_after_unstable_primary()
    test_absent_source_when_no_stable_grid()
    test_adjacent_count_uses_grid_coordinates()
    test_safe_correlations_reject_constant_vectors()
    test_branch_nuisance_design_status()
    return {"status": "PASS", "tests": 8}


def main() -> int:
    print(json.dumps(run_selftest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
