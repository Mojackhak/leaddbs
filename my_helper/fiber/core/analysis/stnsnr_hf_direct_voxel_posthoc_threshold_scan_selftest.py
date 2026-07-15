#!/usr/bin/env python3
"""Self-tests for HF direct voxel post-hoc tau/coverage threshold scan helpers."""

from __future__ import annotations

import json

import pandas as pd

from stnsnr_hf_direct_voxel_posthoc_threshold_scan import (
    COVERAGE_GRID,
    TAU_GRID,
    build_all_scale_long_table,
    build_all_scale_summary_table,
    build_annotated_rho_source,
    build_heatmap,
    endpoint_family_for_scale,
    grid_cell_position,
    row_passes_hard_filters,
    scale_names_from_raw_dataframe,
    select_best_grid_cell,
    significance_stars,
    validate_annotated_rho_input,
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
        "n_subjects": 16,
        "n_voxels_full": 21,
        "fold_n_voxels_min": 10,
        "hfscore_nonconstant_all_folds": True,
        "all_predictions_finite": True,
        "loocv_spearman_rho": -0.62,
        "q2": -0.33,
        "mae_model": 12.0,
        "mae_baseline": 10.0,
        "rmse_model": 14.0,
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
            "n_subjects": 16,
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
            "n_subjects": 16,
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
            "tau": 220,
            "coverage": 12,
            "n_subjects": 16,
            "n_voxels_full": 21,
            "fold_n_voxels_min": 10,
            "hfscore_nonconstant_all_folds": True,
            "all_predictions_finite": True,
            "loocv_spearman_rho": 0.1,
            "q2": -0.1,
            "mae_model": 11.0,
            "mae_baseline": 10.0,
            "rmse_model": 13.0,
            "rmse_baseline": 12.0,
        },
        {
            "tau": 200,
            "coverage": 5,
            "n_subjects": 11,
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
    for tau, coverage in [
        (180, 6),
        (220, 6),
        (150, 5),
        (150, 7),
        (250, 5),
        (250, 7),
    ]:
        rows.append(
            {
                "tau": tau,
                "coverage": coverage,
                "n_subjects": 16,
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


def test_significance_stars() -> None:
    assert_equal(significance_stars(0.2), "", "not significant")
    assert_equal(significance_stars(0.049), "*", "p<0.05")
    assert_equal(significance_stars(0.009), "**", "p<0.01")
    assert_equal(significance_stars(0.0009), "***", "p<0.001")


def test_annotated_input_validation() -> None:
    rows = [{"tau": 100, "coverage": 5, "loocv_spearman_rho": 0.1}]
    try:
        validate_annotated_rho_input(rows)
    except ValueError as exc:
        if "loocv_spearman_nominal_p" not in str(exc):
            raise AssertionError(f"unexpected validation error: {exc}") from exc
    else:
        raise AssertionError("missing annotated heatmap columns should fail")


def test_grid_cell_position() -> None:
    assert_equal(grid_cell_position(200, 5), (3, 0), "primary position")
    assert_equal(grid_cell_position(250, 10), (5, 4), "selected position")


def test_annotated_rho_source() -> None:
    rows = [
        {
            "tau": 250,
            "coverage": 10,
            "loocv_spearman_rho": 0.619,
            "loocv_spearman_nominal_p": 0.0105,
            "passes_all_hard_filters": True,
        },
        {
            "tau": 200,
            "coverage": 5,
            "loocv_spearman_rho": -0.026,
            "loocv_spearman_nominal_p": 0.92,
            "passes_all_hard_filters": False,
        },
    ]
    source = build_annotated_rho_source(rows, selected_tau=250, selected_coverage=10)
    selected = source[(source["tau"] == 250) & (source["coverage"] == 10)].iloc[0]
    primary = source[(source["tau"] == 200) & (source["coverage"] == 5)].iloc[0]
    assert_equal(selected["stars"], "*", "selected nominal star")
    assert_equal(selected["cell_label"], "0.62\n*", "selected cell label")
    assert_equal(bool(selected["is_selected_branch"]), True, "selected branch marker")
    assert_equal(bool(primary["is_primary_branch"]), True, "primary branch marker")


def test_scale_names_and_endpoint_family() -> None:
    raw = pd.DataFrame(
        {
            "Scale": [
                "MDS-UPDRS III score",
                "MDS-UPDRS III score",
                "MDS-UPDRS III score",
                "SE-ADL score (%)",
            ],
            "Protocol": ["STN", "STN+SNr", "STN", "STN"],
            "Phase": ["3m", "3m", "immediate", "3m"],
        }
    )
    assert_equal(
        scale_names_from_raw_dataframe(raw),
        [
            "MDS-UPDRS III score (STN, 3 m)",
            "SE-ADL score (%) (STN, 3 m)",
            "MDS-UPDRS III score (STN, immediate)",
        ],
        "scale order",
    )
    assert_equal(endpoint_family_for_scale("MDS-UPDRS III score (STN, 3 m)"), "hf_stn3m", "STN family")
    assert_equal(
        endpoint_family_for_scale("MDS-UPDRS III score (STN, immediate)"),
        "raw_stn_immediate",
        "STN immediate family",
    )
    assert_equal(endpoint_family_for_scale("MDS-UPDRS III score (STN+SNr, 3 m)"), "raw_stnplus_snr_3m", "STN+SNr family")


def test_all_scale_tables() -> None:
    scan_rows = [
        {
            "tau": 100,
            "coverage": 5,
            "n_subjects": 16,
            "loocv_spearman_rho": 0.1,
            "loocv_spearman_nominal_p": 0.2,
            "q2": -0.1,
            "n_voxels_full": 30,
            "fold_n_voxels_min": 12,
            "passes_all_hard_filters": False,
        },
        {
            "tau": 250,
            "coverage": 10,
            "n_subjects": 16,
            "loocv_spearman_rho": 0.6,
            "loocv_spearman_nominal_p": 0.01,
            "q2": 0.3,
            "n_voxels_full": 21,
            "fold_n_voxels_min": 10,
            "passes_all_hard_filters": True,
        },
    ]
    per_scale = [
        {
            "scale": "MDS-UPDRS III score (STN, 3 m)",
            "scale_slug": "mds_updrs_iii_score_stn_3_m",
            "scale_direction": "lower",
            "n_subjects": 16,
            "n_candidate_voxels": 6406,
            "rows": scan_rows,
            "selected": scan_rows[1],
        },
        {
            "scale": "MDS-UPDRS III axial score (STN, 3 m)",
            "scale_slug": "mds_updrs_iii_axial_score_stn_3_m",
            "scale_direction": "lower",
            "n_subjects": 16,
            "n_candidate_voxels": 6406,
            "rows": scan_rows,
            "selected": None,
        },
    ]
    long_table = build_all_scale_long_table(per_scale)
    summary_table = build_all_scale_summary_table(per_scale)
    assert_equal(len(long_table), 4, "long table row count")
    assert_equal(len(summary_table), 2, "summary row count")
    assert_equal(summary_table.iloc[0]["endpoint_family"], "hf_stn3m", "summary family")
    assert_equal(summary_table.iloc[0]["selected_tau"], 250, "selected tau")
    assert_equal(summary_table.iloc[1]["n_passing_grid_cells"], 1, "passing count")
    assert_equal(pd.isna(summary_table.iloc[1]["selected_tau"]), True, "missing selected tau")
    assert_equal("hf_voxel_source_status" in summary_table.columns, True, "source status column")
    assert_equal("hf_voxel_prediction_status" in summary_table.columns, True, "prediction status column")


def _passing_cell(tau: int, coverage: int, *, selected: bool = False) -> dict:
    return {
        "scale": "MDS-UPDRS III score (STN, 3 m)",
        "scale_slug": "mds_updrs_iii_score_stn_3_m",
        "endpoint_family": "hf_stn3m",
        "tau": tau,
        "coverage": coverage,
        "n_subjects": 16,
        "n_voxels_full": 30,
        "fold_n_voxels_min": 12,
        "hfscore_nonconstant_all_folds": True,
        "all_predictions_finite": True,
        "loocv_spearman_rho": -0.5,
        "loocv_spearman_nominal_p": 0.9,
        "q2": -0.2,
        "mae_model": 8.0,
        "mae_baseline": 10.0,
        "rmse_model": 10.0,
        "rmse_baseline": 12.0,
        "passes_all_hard_filters": True,
        "is_selected_grid_cell": selected,
    }


def test_source_resolver_table_fields() -> None:
    rows = [
        _passing_cell(200, 5, selected=True),
        _passing_cell(180, 5),
        _passing_cell(220, 6),
    ]
    per_scale = [
        {
            "scale": "MDS-UPDRS III score (STN, 3 m)",
            "scale_slug": "mds_updrs_iii_score_stn_3_m",
            "scale_direction": "lower",
            "n_subjects": 16,
            "n_candidate_voxels": 6406,
            "rows": rows,
            "selected": rows[0],
            "source_resolution": {
                "source_status": "pre_specified_accepted",
                "prediction_status": "error_predictive",
                "threshold_source": "pre_specified",
                "selected_tau": 200,
                "selected_coverage": 5,
                "selected_adjacent_passing_grid_cells": 2,
                "source_failure_reasons": "",
            },
        }
    ]
    summary = build_all_scale_summary_table(per_scale)
    assert_equal(summary.iloc[0]["hf_voxel_source_status"], "pre_specified_accepted", "HF source status")
    assert_equal(summary.iloc[0]["hf_voxel_prediction_status"], "error_predictive", "HF prediction status")
    assert_equal(summary.iloc[0]["hf_voxel_selected_adjacent_passing_grid_cells"], 2, "adjacent support")


def main() -> int:
    test_grid_definition()
    test_hard_filter()
    test_selection_priority()
    test_primary_distance_tie_break()
    test_heatmap_shape()
    test_significance_stars()
    test_annotated_input_validation()
    test_grid_cell_position()
    test_annotated_rho_source()
    test_scale_names_and_endpoint_family()
    test_all_scale_tables()
    test_source_resolver_table_fields()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
