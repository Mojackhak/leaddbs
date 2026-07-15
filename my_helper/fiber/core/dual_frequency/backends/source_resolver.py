"""Outcome-performance-independent tau/Coverage source resolution."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Generic, Protocol, TypeVar, runtime_checkable

from ..contracts import SourceGrid


PRE_SPECIFIED_ACCEPTED = "pre_specified_accepted"
SCAN_FALLBACK_ACCEPTED = "scan_fallback_accepted"
ABSENT_NO_STABLE_GRID = "absent_no_stable_grid"


class SourceResolverError(ValueError):
    """Raised when grid metrics cannot be resolved deterministically."""


@runtime_checkable
class GridCellMetric(Protocol):
    """Structural fields required from a backend-specific grid metric."""

    @property
    def tau(self) -> float: ...

    @property
    def coverage(self) -> int: ...

    @property
    def fold_n_features_min(self) -> int: ...

    @property
    def passes_hard_computability(self) -> bool: ...

    @property
    def prediction_status(self) -> str: ...

    @property
    def mae_model(self) -> float: ...

    @property
    def mae_baseline(self) -> float: ...

    @property
    def rmse_model(self) -> float: ...

    @property
    def rmse_baseline(self) -> float: ...


MetricT = TypeVar("MetricT", bound=GridCellMetric)


@dataclass(frozen=True)
class SourceResolution(Generic[MetricT]):
    """Immutable source and prediction classification for one endpoint."""

    source_status: str
    prediction_status: str
    threshold_source: str
    selected: MetricT | None
    adjacent_support: int | None
    failure_reason: str | None

    @property
    def accepted(self) -> bool:
        return self.source_status in {PRE_SPECIFIED_ACCEPTED, SCAN_FALLBACK_ACCEPTED}


def _position(
    cell: GridCellMetric,
    tau_values: tuple[float, ...],
    coverage_values: tuple[int, ...],
) -> tuple[int, int] | None:
    try:
        return (
            tau_values.index(float(cell.tau)),
            coverage_values.index(int(cell.coverage)),
        )
    except ValueError:
        return None


def is_adjacent(
    first: GridCellMetric,
    second: GridCellMetric,
    grid: SourceGrid,
) -> bool:
    """Return whether cells are horizontal, vertical, or diagonal neighbors."""

    first_position = _position(first, grid.tau_values, grid.coverage_values)
    second_position = _position(second, grid.tau_values, grid.coverage_values)
    if first_position is None or second_position is None:
        return False
    tau_delta = abs(first_position[0] - second_position[0])
    coverage_delta = abs(first_position[1] - second_position[1])
    return tau_delta <= 1 and coverage_delta <= 1 and tau_delta + coverage_delta > 0


def adjacent_passing_count(
    cells: tuple[MetricT, ...],
    selected: MetricT,
    grid: SourceGrid,
) -> int:
    """Count adjacent cells that pass hard computability."""

    return sum(
        cell.passes_hard_computability and is_adjacent(cell, selected, grid)
        for cell in cells
    )


def _validate_cells(
    cells: tuple[MetricT, ...],
    grid: SourceGrid,
) -> dict[tuple[float, int], MetricT]:
    expected = {
        (float(tau), int(coverage))
        for tau in grid.tau_values
        for coverage in grid.coverage_values
    }
    observed: dict[tuple[float, int], MetricT] = {}
    for cell in cells:
        key = (float(cell.tau), int(cell.coverage))
        if key in observed:
            raise SourceResolverError(f"duplicate grid cell {key}")
        if key not in expected:
            raise SourceResolverError(f"undeclared grid cell {key}")
        observed[key] = cell
    missing = expected - set(observed)
    if missing:
        raise SourceResolverError(f"missing declared grid cells: {sorted(missing)}")
    return observed


def _fallback_key(
    cell: MetricT,
    cells: tuple[MetricT, ...],
    grid: SourceGrid,
) -> tuple[int, int, int, int, float]:
    position = _position(cell, grid.tau_values, grid.coverage_values)
    primary_position = (
        grid.tau_values.index(grid.pre_specified_tau),
        grid.coverage_values.index(grid.pre_specified_coverage),
    )
    if position is None:
        raise SourceResolverError("fallback cell is outside the declared grid")
    grid_distance = abs(position[0] - primary_position[0]) + abs(
        position[1] - primary_position[1]
    )
    return (
        grid_distance,
        -adjacent_passing_count(cells, cell, grid),
        -int(cell.fold_n_features_min),
        -int(cell.coverage),
        -float(cell.tau),
    )


def _require_accepted_prediction_metrics(cell: GridCellMetric) -> None:
    if cell.prediction_status not in {"error_predictive", "error_nonpredictive"}:
        raise SourceResolverError(
            "an accepted grid cell requires an error-prediction classification"
        )
    errors = (
        cell.mae_model,
        cell.mae_baseline,
        cell.rmse_model,
        cell.rmse_baseline,
    )
    if not all(math.isfinite(value) for value in errors):
        raise SourceResolverError("an accepted grid cell must have finite error metrics")


def resolve_source(
    cells: tuple[MetricT, ...],
    grid: SourceGrid,
) -> SourceResolution[MetricT]:
    """Resolve the pre-specified source or one stable scan fallback."""

    if not isinstance(grid, SourceGrid):
        raise SourceResolverError("grid must be a SourceGrid")
    cells = tuple(cells)
    cell_map = _validate_cells(cells, grid)
    primary = cell_map[(grid.pre_specified_tau, grid.pre_specified_coverage)]
    primary_adjacent = adjacent_passing_count(cells, primary, grid)
    if (
        primary.passes_hard_computability
        and primary_adjacent >= grid.minimum_adjacent_passing_cells
    ):
        _require_accepted_prediction_metrics(primary)
        return SourceResolution(
            source_status=PRE_SPECIFIED_ACCEPTED,
            prediction_status=primary.prediction_status,
            threshold_source="pre_specified",
            selected=primary,
            adjacent_support=primary_adjacent,
            failure_reason=None,
        )

    passing = tuple(cell for cell in cells if cell.passes_hard_computability)
    eligible = tuple(
        cell
        for cell in passing
        if adjacent_passing_count(cells, cell, grid)
        >= grid.minimum_adjacent_passing_cells
    )
    if not eligible:
        return SourceResolution(
            source_status=ABSENT_NO_STABLE_GRID,
            prediction_status="not_applicable",
            threshold_source="none",
            selected=None,
            adjacent_support=None,
            failure_reason=(
                "no_grid_cell_met_adjacent_support"
                if passing
                else "no_grid_cell_passed_hard_computability"
            ),
        )
    selected = min(eligible, key=lambda cell: _fallback_key(cell, cells, grid))
    _require_accepted_prediction_metrics(selected)
    return SourceResolution(
        source_status=SCAN_FALLBACK_ACCEPTED,
        prediction_status=selected.prediction_status,
        threshold_source="scan_fallback",
        selected=selected,
        adjacent_support=adjacent_passing_count(cells, selected, grid),
        failure_reason=None,
    )


__all__ = [
    "ABSENT_NO_STABLE_GRID",
    "GridCellMetric",
    "PRE_SPECIFIED_ACCEPTED",
    "SCAN_FALLBACK_ACCEPTED",
    "SourceResolution",
    "SourceResolverError",
    "adjacent_passing_count",
    "is_adjacent",
    "resolve_source",
]
