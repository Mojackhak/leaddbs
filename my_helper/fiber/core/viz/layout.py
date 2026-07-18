"""Deterministic millimetre-based figure layout helpers.

The inner plotting box of every panel is exactly ``boxsize`` on the exported
page. Decorations are allocated outside that box so changing labels, strips,
or DPI does not silently change panel geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

DEFAULT_BOXSIZE_MM = (36.0, 32.0)
MM_PER_INCH = 25.4


def _positive_pair(value: Sequence[float], name: str) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must contain width and height in millimetres")
    pair = (float(value[0]), float(value[1]))
    if not all(isfinite(item) and item > 0 for item in pair):
        raise ValueError(f"{name} entries must be positive finite numbers")
    return pair


def _nonnegative_pair(value: Sequence[float], name: str) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must contain horizontal and vertical values")
    pair = (float(value[0]), float(value[1]))
    if not all(isfinite(item) and item >= 0 for item in pair):
        raise ValueError(f"{name} entries must be finite and nonnegative")
    return pair


@dataclass(frozen=True)
class FigureLayout:
    """Physical and normalized geometry for a regular panel grid."""

    nrows: int
    ncols: int
    boxsize_mm: tuple[float, float]
    panel_gap_mm: tuple[float, float]
    margins_mm: tuple[float, float, float, float]
    top_strip_mm: float
    strip_pad_mm: float
    right_strip_mm: float
    figure_size_mm: tuple[float, float]
    panel_positions: tuple[tuple[float, float, float, float], ...]
    top_strip_positions: tuple[tuple[float, float, float, float], ...]
    right_strip_positions: tuple[tuple[float, float, float, float], ...]

    @property
    def figure_size_inches(self) -> tuple[float, float]:
        return tuple(item / MM_PER_INCH for item in self.figure_size_mm)

    def panel_position(self, row: int, column: int) -> tuple[float, float, float, float]:
        self._validate_index(row, column)
        return self.panel_positions[row * self.ncols + column]

    def top_strip_position(self, row: int, column: int) -> tuple[float, float, float, float]:
        self._validate_index(row, column)
        return self.top_strip_positions[row * self.ncols + column]

    def right_strip_position(self, row: int) -> tuple[float, float, float, float]:
        if row < 0 or row >= self.nrows:
            raise IndexError("row is outside the layout")
        return self.right_strip_positions[row]

    def _validate_index(self, row: int, column: int) -> None:
        if row < 0 or row >= self.nrows or column < 0 or column >= self.ncols:
            raise IndexError("panel index is outside the layout")


def build_figure_layout(
    nrows: int,
    ncols: int,
    *,
    boxsize: Sequence[float] = DEFAULT_BOXSIZE_MM,
    panel_gap: Sequence[float] = (3.0, 3.0),
    margins: Sequence[float] = (12.0, 11.0, 5.0, 6.0),
    top_strip_mm: float = 3.5,
    strip_pad_mm: float = 0.35,
    right_strip_mm: float = 0.0,
) -> FigureLayout:
    """Return exact page geometry for a panel grid.

    ``margins`` uses left, bottom, right, and top order. Top strips are
    allocated per panel row. A right strip is allocated once for every row.
    """

    if not isinstance(nrows, int) or not isinstance(ncols, int) or nrows < 1 or ncols < 1:
        raise ValueError("nrows and ncols must be positive integers")
    box_w, box_h = _positive_pair(boxsize, "boxsize")
    gap_x, gap_y = _nonnegative_pair(panel_gap, "panel_gap")
    if not isinstance(margins, (tuple, list)) or len(margins) != 4:
        raise ValueError("margins must contain left, bottom, right, and top values")
    left, bottom, right, top = (float(item) for item in margins)
    if not all(isfinite(item) and item >= 0 for item in (left, bottom, right, top)):
        raise ValueError("margins must be finite and nonnegative")
    top_strip = float(top_strip_mm)
    strip_pad = float(strip_pad_mm)
    right_strip = float(right_strip_mm)
    if not all(isfinite(item) and item >= 0 for item in (top_strip, strip_pad, right_strip)):
        raise ValueError("strip dimensions must be finite and nonnegative")

    row_height = box_h + (strip_pad + top_strip if top_strip > 0 else 0.0)
    grid_w = ncols * box_w + (ncols - 1) * gap_x
    grid_h = nrows * row_height + (nrows - 1) * gap_y
    right_extra = strip_pad + right_strip if right_strip > 0 else 0.0
    figure_w = left + grid_w + right_extra + right
    figure_h = bottom + grid_h + top

    panel_positions: list[tuple[float, float, float, float]] = []
    top_positions: list[tuple[float, float, float, float]] = []
    right_positions: list[tuple[float, float, float, float]] = []

    for row in range(nrows):
        row_from_bottom = nrows - row - 1
        cell_y = bottom + row_from_bottom * (row_height + gap_y)
        for column in range(ncols):
            panel_x = left + column * (box_w + gap_x)
            panel_positions.append(
                (panel_x / figure_w, cell_y / figure_h, box_w / figure_w, box_h / figure_h)
            )
            strip_y = cell_y + box_h + strip_pad
            top_positions.append(
                (
                    panel_x / figure_w,
                    strip_y / figure_h,
                    box_w / figure_w,
                    top_strip / figure_h,
                )
            )
        right_positions.append(
            (
                (left + grid_w + strip_pad) / figure_w,
                cell_y / figure_h,
                right_strip / figure_w,
                box_h / figure_h,
            )
        )

    return FigureLayout(
        nrows=nrows,
        ncols=ncols,
        boxsize_mm=(box_w, box_h),
        panel_gap_mm=(gap_x, gap_y),
        margins_mm=(left, bottom, right, top),
        top_strip_mm=top_strip,
        strip_pad_mm=strip_pad,
        right_strip_mm=right_strip,
        figure_size_mm=(figure_w, figure_h),
        panel_positions=tuple(panel_positions),
        top_strip_positions=tuple(top_positions),
        right_strip_positions=tuple(right_positions),
    )
