#!/usr/bin/env python3
"""Shared resolver helpers for the STN/SNr four-model execution program."""

from __future__ import annotations

import math
from typing import Any


HF_SOURCE_PRE_SPECIFIED = "pre_specified_accepted"
HF_SOURCE_SCAN_FALLBACK = "scan_fallback_accepted"
HF_SOURCE_ABSENT = "absent_no_stable_grid"

PREDICTION_ERROR_PREDICTIVE = "error_predictive"
PREDICTION_ERROR_NONPREDICTIVE = "error_nonpredictive"
PREDICTION_NOT_APPLICABLE = "not_applicable"

DEFAULT_TAU_GRID = [100, 150, 180, 200, 220, 250, 300, 350, 400, 500]
DEFAULT_COVERAGE_GRID = [5, 6, 7, 8, 10, 12]


def as_bool(value: Any) -> bool:
    """Return a permissive boolean interpretation for manifest/table values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass"}
    return bool(value)


def finite_float(value: Any) -> float:
    """Return a float or NaN for nonnumeric values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def hard_computability_passes(row: dict[str, Any]) -> bool:
    """Return whether one HF grid cell passes the intended computability filter."""
    return (
        finite_float(row.get("n_subjects")) >= 12
        and finite_float(row.get("n_voxels_full")) >= 20
        and finite_float(row.get("fold_n_voxels_min")) >= 10
        and as_bool(row.get("hfscore_nonconstant_all_folds"))
        and as_bool(row.get("all_predictions_finite"))
    )


def classify_prediction_status(row: dict[str, Any]) -> str:
    """Classify prediction-error status from MAE and RMSE improvement."""
    if (
        finite_float(row.get("mae_model")) < finite_float(row.get("mae_baseline"))
        and finite_float(row.get("rmse_model")) < finite_float(row.get("rmse_baseline"))
    ):
        return PREDICTION_ERROR_PREDICTIVE
    return PREDICTION_ERROR_NONPREDICTIVE


def _grid_position(
    row: dict[str, Any],
    *,
    tau_grid: list[int],
    coverage_grid: list[int],
) -> tuple[int, int] | None:
    tau = int(finite_float(row.get("tau"))) if math.isfinite(finite_float(row.get("tau"))) else None
    coverage = int(finite_float(row.get("coverage"))) if math.isfinite(finite_float(row.get("coverage"))) else None
    if tau not in tau_grid or coverage not in coverage_grid:
        return None
    return tau_grid.index(tau), coverage_grid.index(coverage)


def is_adjacent_cell(
    row: dict[str, Any],
    selected: dict[str, Any],
    *,
    tau_grid: list[int] | None = None,
    coverage_grid: list[int] | None = None,
) -> bool:
    """Return whether one grid cell is adjacent to another in tau/Coverage space."""
    tau_values = DEFAULT_TAU_GRID if tau_grid is None else tau_grid
    coverage_values = DEFAULT_COVERAGE_GRID if coverage_grid is None else coverage_grid
    row_pos = _grid_position(row, tau_grid=tau_values, coverage_grid=coverage_values)
    selected_pos = _grid_position(selected, tau_grid=tau_values, coverage_grid=coverage_values)
    if row_pos is None or selected_pos is None:
        return False
    delta_tau = abs(row_pos[0] - selected_pos[0])
    delta_coverage = abs(row_pos[1] - selected_pos[1])
    return delta_tau <= 1 and delta_coverage <= 1 and delta_tau + delta_coverage > 0


def adjacent_passing_count(
    rows: list[dict[str, Any]],
    selected: dict[str, Any],
    *,
    tau_grid: list[int] | None = None,
    coverage_grid: list[int] | None = None,
) -> int:
    """Count adjacent grid cells that pass hard computability."""
    return sum(
        1
        for row in rows
        if hard_computability_passes(row)
        and is_adjacent_cell(row, selected, tau_grid=tau_grid, coverage_grid=coverage_grid)
    )


def _row_matches(row: dict[str, Any], tau: int, coverage: int) -> bool:
    return int(finite_float(row.get("tau"))) == tau and int(finite_float(row.get("coverage"))) == coverage


def _distance_to_primary(row: dict[str, Any], primary_tau: int, primary_coverage: int) -> tuple[float, float]:
    return (abs(finite_float(row.get("tau")) - primary_tau), abs(finite_float(row.get("coverage")) - primary_coverage))


def _fallback_sort_key(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    primary_tau: int,
    primary_coverage: int,
    tau_grid: list[int],
    coverage_grid: list[int],
) -> tuple[float, float, float, float, float, float]:
    tau_distance, coverage_distance = _distance_to_primary(row, primary_tau, primary_coverage)
    return (
        tau_distance + coverage_distance,
        tau_distance,
        coverage_distance,
        -adjacent_passing_count(rows, row, tau_grid=tau_grid, coverage_grid=coverage_grid),
        -finite_float(row.get("fold_n_voxels_min")),
        -finite_float(row.get("coverage")),
        -finite_float(row.get("tau")),
    )


def _source_payload(
    *,
    source_status: str,
    selected: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    threshold_source: str,
    tau_grid: list[int],
    coverage_grid: list[int],
) -> dict[str, Any]:
    if selected is None:
        return {
            "source_status": source_status,
            "prediction_status": PREDICTION_NOT_APPLICABLE,
            "threshold_source": "none",
            "selected_tau": "",
            "selected_coverage": "",
            "selected_adjacent_passing_grid_cells": 0,
            "source_failure_reasons": "no_grid_cell_passed_hard_computability",
        }
    return {
        "source_status": source_status,
        "prediction_status": classify_prediction_status(selected),
        "threshold_source": threshold_source,
        "selected_tau": int(finite_float(selected.get("tau"))),
        "selected_coverage": int(finite_float(selected.get("coverage"))),
        "selected_adjacent_passing_grid_cells": adjacent_passing_count(
            rows, selected, tau_grid=tau_grid, coverage_grid=coverage_grid
        ),
        "source_failure_reasons": "",
    }


def resolve_hf_source(
    rows: list[dict[str, Any]],
    *,
    primary_tau: int,
    primary_coverage: int,
    tau_grid: list[int] | None = None,
    coverage_grid: list[int] | None = None,
) -> dict[str, Any]:
    """Resolve a foundational HF source from pre-specified and scan grid rows."""
    tau_values = DEFAULT_TAU_GRID if tau_grid is None else tau_grid
    coverage_values = DEFAULT_COVERAGE_GRID if coverage_grid is None else coverage_grid
    primary_rows = [row for row in rows if _row_matches(row, primary_tau, primary_coverage)]
    primary = primary_rows[0] if primary_rows else None
    if primary is not None and hard_computability_passes(primary):
        primary_adjacent = adjacent_passing_count(rows, primary, tau_grid=tau_values, coverage_grid=coverage_values)
        if primary_adjacent >= 2:
            return _source_payload(
                source_status=HF_SOURCE_PRE_SPECIFIED,
                selected=primary,
                rows=rows,
                threshold_source="pre_specified",
                tau_grid=tau_values,
                coverage_grid=coverage_values,
            )

    eligible = [row for row in rows if hard_computability_passes(row)]
    if not eligible:
        return _source_payload(
            source_status=HF_SOURCE_ABSENT,
            selected=None,
            rows=rows,
            threshold_source="none",
            tau_grid=tau_values,
            coverage_grid=coverage_values,
        )
    selected = sorted(
        eligible,
        key=lambda row: _fallback_sort_key(
            row,
            rows,
            primary_tau=primary_tau,
            primary_coverage=primary_coverage,
            tau_grid=tau_values,
            coverage_grid=coverage_values,
        ),
    )[0]
    return _source_payload(
        source_status=HF_SOURCE_SCAN_FALLBACK,
        selected=selected,
        rows=rows,
        threshold_source="scan_fallback",
        tau_grid=tau_values,
        coverage_grid=coverage_values,
    )
