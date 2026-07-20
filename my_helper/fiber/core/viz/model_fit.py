"""Paired in-sample and LOOCV fit visualization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib import colormaps, font_manager

from .layout import FigureLayout, build_figure_layout
from .plugin.default import get_fit_cfg

try:
    from scipy.stats import t as student_t
except ImportError:  # pragma: no cover - SciPy is present in the supported environment
    student_t = None


def _resolve_font(preferred: str, fallbacks: Sequence[str]) -> str:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in (preferred, *fallbacks):
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _format_number(value: Any, digits: int = 3) -> str:
    number = _finite_number(value)
    if number is None:
        return "NA"
    return f"{number:.{digits}f}"


def _format_permutation_p(value: Any) -> str:
    number = _finite_number(value)
    if number is None:
        return "p = NA"
    if number < 0.001:
        return "p < 0.001 (***)"
    if number < 0.01:
        suffix = "(**)"
    elif number < 0.05:
        suffix = "(*)"
    else:
        suffix = "(n.s.)"
    return f"p = {number:.3f} {suffix}"


def _summary_value(summary: Mapping[str, Any], prefix: str, suffix: str) -> Any:
    return summary.get(f"{prefix}_{suffix}")


def _annotation_lines(summary: Mapping[str, Any], prefix: str) -> list[str]:
    """Return the compact, publication-backed panel annotation."""

    return [
        "ρ = "
        f"{_format_number(_summary_value(summary, prefix, 'spearman_rho'))}",
        _format_permutation_p(
            _summary_value(summary, prefix, "permutation_p_plus_one_two_sided")
        ),
    ]


@dataclass(frozen=True)
class _FitDisplayData:
    x: np.ndarray
    y: np.ndarray
    x_grid: np.ndarray
    fitted: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


def _compute_display_fit(
    x: np.ndarray,
    y: np.ndarray,
    *,
    confidence_level: float,
) -> _FitDisplayData:
    empty = np.asarray([], dtype=float)
    base = _FitDisplayData(x, y, empty, empty, empty, empty)
    if x.size < 3 or np.ptp(x) <= np.finfo(float).eps:
        return base
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    centered_x = x - x_mean
    sxx = float(np.sum(centered_x**2))
    if sxx <= np.finfo(float).eps:
        return base
    slope = float(np.sum(centered_x * (y - y_mean)) / sxx)
    intercept = y_mean - slope * x_mean
    x_grid = np.linspace(float(np.min(x)), float(np.max(x)), 200)
    fitted = intercept + slope * x_grid

    residuals = y - (intercept + slope * x)
    degrees = x.size - 2
    if degrees < 1 or student_t is None:
        return _FitDisplayData(x, y, x_grid, fitted, empty, empty)
    residual_variance = float(np.sum(residuals**2) / degrees)
    if not np.isfinite(residual_variance):
        return _FitDisplayData(x, y, x_grid, fitted, empty, empty)
    standard_error = np.sqrt(
        residual_variance
        * (1.0 / x.size + ((x_grid - x_mean) ** 2) / sxx)
    )
    critical = float(student_t.ppf(0.5 + float(confidence_level) / 2.0, degrees))
    if not np.isfinite(critical):
        return _FitDisplayData(x, y, x_grid, fitted, empty, empty)
    return _FitDisplayData(
        x,
        y,
        x_grid,
        fitted,
        fitted - critical * standard_error,
        fitted + critical * standard_error,
    )


def _display_fit(
    ax: plt.Axes,
    data: _FitDisplayData,
    *,
    point_colors: np.ndarray,
    line_color: str,
    point_size: float,
    point_alpha: float,
    line_width: float,
    ribbon_alpha: float,
) -> None:
    ax.scatter(
        data.x,
        data.y,
        s=point_size,
        color=point_colors,
        edgecolor="none",
        linewidth=0.0,
        alpha=point_alpha,
        zorder=2,
    )
    if not data.x_grid.size:
        return
    if data.lower.size and data.upper.size:
        ax.fill_between(
            data.x_grid,
            data.lower,
            data.upper,
            color=line_color,
            alpha=ribbon_alpha,
            linewidth=0,
            zorder=1.5,
        )
    ax.plot(
        data.x_grid,
        data.fitted,
        color=line_color,
        linewidth=line_width,
        zorder=3,
    )


def _auto_limits(
    x_arrays: Sequence[np.ndarray],
    y_arrays: Sequence[np.ndarray],
    *,
    padding_fraction: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        _padded_limits(x_arrays, padding_fraction=padding_fraction),
        _padded_limits(y_arrays, padding_fraction=padding_fraction),
    )


def _padded_limits(
    arrays: Sequence[np.ndarray],
    *,
    padding_fraction: float,
) -> tuple[float, float]:
    parts = [array[np.isfinite(array)] for array in arrays if array.size]
    values = np.concatenate(parts) if parts else np.asarray([], dtype=float)
    if not values.size:
        raise ValueError("no finite values are available for an axis limit")
    lower, upper = float(np.min(values)), float(np.max(values))
    padding = (upper - lower) * float(padding_fraction)
    return lower - padding, upper + padding


def _add_strip(
    fig: plt.Figure,
    layout: FigureLayout,
    column: int,
    text: str,
    *,
    facecolor: str,
    text_color: str,
    fontsize: float,
    font_family: str,
    fontweight: str,
) -> None:
    strip = fig.add_axes(layout.top_strip_position(0, column))
    strip.set_facecolor(facecolor)
    strip.text(
        0.5,
        0.5,
        text,
        ha="center",
        va="center",
        color=text_color,
        fontsize=fontsize,
        fontfamily=font_family,
        fontweight=fontweight,
    )
    strip.set_xticks([])
    strip.set_yticks([])
    for spine in strip.spines.values():
        spine.set_visible(False)


def _add_panel_annotation(
    ax: plt.Axes,
    text: str,
    *,
    inset_fraction: Sequence[float],
    location: str,
    fontsize: float,
    font_family: str,
    box_alpha: float,
) -> None:
    x, y = (float(value) for value in inset_fraction)
    normalized_location = str(location).strip().lower()
    if normalized_location != "upper left":
        raise ValueError("paired-fit annotation_location must be 'upper left'")
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=fontsize,
        fontfamily=font_family,
        linespacing=1.0,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": float(box_alpha),
        },
        zorder=10,
        clip_on=False,
    )


def _measure_text_mm(
    text: str,
    *,
    fontsize: float,
    font_family: str,
    dpi: int,
    rotation: float = 0.0,
) -> tuple[float, float]:
    probe = plt.figure(figsize=(2.0, 2.0), dpi=dpi)
    probe.patch.set_alpha(0.0)
    artist = probe.text(
        0.0,
        0.0,
        text,
        fontsize=fontsize,
        fontfamily=font_family,
        rotation=rotation,
    )
    probe.canvas.draw()
    bounds = artist.get_window_extent(renderer=probe.canvas.get_renderer())
    plt.close(probe)
    return bounds.width / dpi * 25.4, bounds.height / dpi * 25.4


def _reference_layout(
    *,
    boxsize: Sequence[float],
    panel_gap: Sequence[float],
    style: Mapping[str, Any],
    font_family: str,
    dpi: int,
) -> FigureLayout:
    x_label = "Observed outcome"
    y_label = "Predicted outcome"
    _, x_label_height = _measure_text_mm(
        x_label,
        fontsize=float(style["axis_label_fontsize"]),
        font_family=font_family,
        dpi=dpi,
    )
    y_label_width, _ = _measure_text_mm(
        y_label,
        fontsize=float(style["axis_label_fontsize"]),
        font_family=font_family,
        dpi=dpi,
        rotation=90.0,
    )
    mylfp_padding_mm = 0.03 * 25.4
    margins = (
        float(style["y_label_offset_mm"]) + y_label_width + mylfp_padding_mm,
        float(style["x_label_offset_mm"]) + x_label_height + mylfp_padding_mm,
        0.0,
        0.0,
    )
    return build_figure_layout(
        1,
        2,
        boxsize=boxsize,
        panel_gap=panel_gap,
        margins=margins,
        top_strip_mm=float(style["strip_top_height_mm"]),
        strip_pad_mm=float(style["strip_pad_mm"]),
    )


def _save_figure(
    fig: plt.Figure,
    output_paths: Sequence[str | Path],
    *,
    dpi: int,
    transparent: bool,
) -> None:
    for output_path in output_paths:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            path,
            dpi=dpi,
            bbox_inches="tight",
        )


def plot_in_sample_loocv_fit(
    subjects: pd.DataFrame,
    endpoint_summary: Mapping[str, Any],
    *,
    subject_id_column: str = "subject_id",
    outcome_column: str = "outcome",
    in_sample_column: str = "in_sample_prediction",
    loocv_column: str = "loocv_prediction",
    style_config: Mapping[str, Any] | None = None,
    boxsize: Sequence[float] | None = None,
    panel_gap: Sequence[float] | None = None,
    dpi: int | None = None,
    font_family: str | None = None,
    point_size: float | None = None,
    point_alpha: float | None = None,
    show_identity: bool | None = None,
    output_paths: Sequence[str | Path] = (),
    transparent: bool | None = None,
) -> plt.Figure:
    """Plot paired in-sample and LOOCV predictions for one final endpoint.

    Stored endpoint metrics are displayed verbatim after numeric formatting.
    The descriptive fit line and confidence band are computed only for display.
    """

    required = (subject_id_column, outcome_column, in_sample_column, loocv_column)
    missing = [column for column in required if column not in subjects.columns]
    if missing:
        raise ValueError(f"subject table is missing required columns: {missing}")
    if not isinstance(endpoint_summary, Mapping):
        raise TypeError("endpoint_summary must be a mapping")

    style = get_fit_cfg(style_config)
    resolved_boxsize = tuple(boxsize or style["boxsize"])
    resolved_panel_gap = tuple(panel_gap or style["panel_gap"])
    resolved_dpi = int(dpi if dpi is not None else style["dpi"])
    resolved_font_family = str(font_family or style["font_family"])
    resolved_point_size = float(
        point_size if point_size is not None else style["jitter_size"]
    )
    resolved_point_alpha = float(
        point_alpha if point_alpha is not None else style["jitter_alpha"]
    )
    resolved_show_identity = bool(
        show_identity if show_identity is not None else style["identity_line"]
    )
    resolved_transparent = bool(
        transparent if transparent is not None else style["transparent"]
    )

    font = _resolve_font(
        resolved_font_family,
        ("Helvetica", "Arial Unicode MS", "DejaVu Sans"),
    )
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = list(
        dict.fromkeys(
            [font, "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"]
        )
    )
    mpl.rcParams["axes.linewidth"] = float(style["axes_line_width"])
    mpl.rcParams["xtick.major.width"] = float(style["major_tick_width"])
    mpl.rcParams["ytick.major.width"] = float(style["major_tick_width"])
    mpl.rcParams["xtick.major.pad"] = float(style["major_tick_padding"])
    mpl.rcParams["ytick.major.pad"] = float(style["major_tick_padding"])
    mpl.rcParams["axes.labelpad"] = float(style["axis_label_padding"])
    mpl.rcParams["xtick.major.size"] = float(style["major_tick_length"])
    mpl.rcParams["ytick.major.size"] = float(style["major_tick_length"])

    layout = _reference_layout(
        boxsize=resolved_boxsize,
        panel_gap=resolved_panel_gap,
        style=style,
        font_family=font,
        dpi=resolved_dpi,
    )
    fig = plt.figure(
        figsize=layout.figure_size_inches,
        dpi=resolved_dpi,
        facecolor="none" if resolved_transparent else "white",
    )
    setattr(fig, "_mh_viz_layout", layout)
    setattr(fig, "_mh_viz_style", dict(style))

    outcome = pd.to_numeric(subjects[outcome_column], errors="coerce").to_numpy(dtype=float)
    in_sample = pd.to_numeric(subjects[in_sample_column], errors="coerce").to_numpy(dtype=float)
    loocv = pd.to_numeric(subjects[loocv_column], errors="coerce").to_numpy(dtype=float)

    subject_ids = subjects[subject_id_column].astype(str).to_numpy()
    ordered_ids = tuple(dict.fromkeys(subject_ids.tolist()))
    color_map = colormaps.get_cmap(str(style["palette"]))
    color_positions = np.linspace(0.0, 1.0, max(len(ordered_ids), 1))
    color_by_subject = {
        subject_id: color_map(position)
        for subject_id, position in zip(ordered_ids, color_positions, strict=True)
    }
    point_colors = np.asarray([color_by_subject[item] for item in subject_ids])

    panel_specs = (
        ("In-sample", "in_sample", in_sample),
        ("LOOCV", "loocv", loocv),
    )
    panel_data: list[
        tuple[str, str, np.ndarray, _FitDisplayData, np.ndarray]
    ] = []
    for label, prefix, prediction in panel_specs:
        finite = np.isfinite(prediction) & np.isfinite(outcome)
        display = _compute_display_fit(
            outcome[finite],
            prediction[finite],
            confidence_level=float(style["confidence_level"]),
        )
        panel_data.append(
            (label, prefix, prediction, display, point_colors[finite])
        )

    x_arrays: list[np.ndarray] = []
    for _, _, _, display, _ in panel_data:
        x_arrays.extend((display.x, display.x_grid))
    x_limits = _padded_limits(
        x_arrays,
        padding_fraction=float(style["axis_padding_fraction"]),
    )
    y_arrays: list[np.ndarray] = []
    for _, _, _, display, _ in panel_data:
        y_arrays.extend((display.y, display.fitted, display.lower, display.upper))
    y_limits = _padded_limits(
        y_arrays,
        padding_fraction=float(style["axis_padding_fraction"]),
    )
    setattr(
        fig,
        "_mh_viz_axis_limits",
        {"x": x_limits, "y": y_limits},
    )
    setattr(
        fig,
        "_mh_viz_fit_displays",
        tuple(display for _, _, _, display, _ in panel_data),
    )

    for column, (label, prefix, _, display, display_colors) in enumerate(panel_data):
        ax = fig.add_axes(layout.panel_position(0, column))
        _display_fit(
            ax,
            display,
            point_colors=display_colors,
            line_color=str(style["curve_line_color"]),
            point_size=resolved_point_size,
            point_alpha=resolved_point_alpha,
            line_width=float(style["curve_line_width"]),
            ribbon_alpha=float(style["ribbon_alpha"]),
        )
        if resolved_show_identity:
            identity_lower = max(x_limits[0], y_limits[0])
            identity_upper = min(x_limits[1], y_limits[1])
            if identity_lower < identity_upper:
                ax.plot(
                    (identity_lower, identity_upper),
                    (identity_lower, identity_upper),
                    color=str(style["identity_line_color"]),
                    linewidth=float(style["identity_line_width"]),
                    linestyle=str(style["identity_line_style"]),
                    zorder=2,
                )
        ax.set_xlim(*x_limits)
        ax.set_ylim(*y_limits)
        if bool(style["grid"]):
            ax.grid(True, zorder=0)
        else:
            ax.grid(False)
        ax.set_axisbelow(True)
        show_top_right = bool(style["show_top_right_axes"])
        ax.spines["top"].set_visible(show_top_right)
        ax.spines["right"].set_visible(show_top_right)
        ax.tick_params(
            labelsize=float(style["tick_label_fontsize"]),
            width=float(style["major_tick_width"]),
            length=float(style["major_tick_length"]),
            pad=float(style["major_tick_padding"]),
            labelleft=column == 0,
        )
        for spine in ax.spines.values():
            spine.set_linewidth(float(style["axes_line_width"]))
        for tick in (*ax.get_xticklabels(), *ax.get_yticklabels()):
            tick.set_fontfamily(font)
        _add_panel_annotation(
            ax,
            "\n".join(_annotation_lines(endpoint_summary, prefix)),
            inset_fraction=style["annotation_inset_fraction"],
            location=str(style["annotation_location"]),
            fontsize=float(style["annotation_fontsize"]),
            font_family=font,
            box_alpha=float(style["annotation_box_alpha"]),
        )
        _add_strip(
            fig,
            layout,
            column,
            label,
            facecolor=str(style["label_top_bg_color"]),
            text_color=str(style["label_text_color"]),
            fontsize=float(style["label_fontsize"]),
            font_family=font,
            fontweight=str(style["label_fontweight"]),
        )

    left, bottom, right, top = layout.margins_mm
    figure_width, figure_height = layout.figure_size_mm
    panel_grid_left = left / figure_width
    panel_grid_right = (figure_width - right) / figure_width
    panel_grid_bottom = bottom / figure_height
    panel_grid_top = (
        figure_height
        - top
        - float(style["strip_top_height_mm"])
        - float(style["strip_pad_mm"])
    ) / figure_height
    fig.text(
        panel_grid_left + (panel_grid_right - panel_grid_left) / 2.0,
        panel_grid_bottom - float(style["x_label_offset_mm"]) / figure_height,
        "Observed outcome",
        ha="center",
        va="top",
        fontsize=float(style["axis_label_fontsize"]),
        fontfamily=font,
    )
    fig.text(
        panel_grid_left - float(style["y_label_offset_mm"]) / figure_width,
        panel_grid_bottom + (panel_grid_top - panel_grid_bottom) / 2.0,
        "Predicted outcome",
        ha="right",
        va="center",
        rotation=90,
        fontsize=float(style["axis_label_fontsize"]),
        fontfamily=font,
    )
    _save_figure(
        fig,
        output_paths,
        dpi=resolved_dpi,
        transparent=resolved_transparent,
    )
    return fig


__all__ = ["plot_in_sample_loocv_fit"]
