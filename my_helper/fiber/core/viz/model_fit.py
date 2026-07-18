"""Paired in-sample and LOOCV fit visualization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

from .layout import DEFAULT_BOXSIZE_MM, FigureLayout, build_figure_layout

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


def _format_p(value: Any) -> str:
    number = _finite_number(value)
    if number is None:
        return "NA"
    if number < 0.001:
        return f"{number:.2e}"
    return f"{number:.3f}"


def _summary_value(summary: Mapping[str, Any], prefix: str, suffix: str) -> Any:
    return summary.get(f"{prefix}_{suffix}")


def _annotation_lines(summary: Mapping[str, Any], prefix: str) -> list[str]:
    rho = _summary_value(summary, prefix, "spearman_rho")
    nominal = _summary_value(summary, prefix, "spearman_nominal_p")
    permutation = _summary_value(summary, prefix, "permutation_p_plus_one_two_sided")
    family_q = _summary_value(summary, prefix, "permutation_q_bh_model_family")
    global_q = _summary_value(summary, prefix, "permutation_q_bh_all_endpoints")
    pearson = _summary_value(summary, prefix, "pearson_r")
    pearson_p = _summary_value(summary, prefix, "pearson_nominal_p")
    requested = _summary_value(summary, prefix, "permutations_requested")
    finite_permutations = _summary_value(summary, prefix, "permutations_finite")
    n_subjects = _summary_value(summary, prefix, "n_subjects_finite")
    if prefix == "loocv":
        rmse = summary.get("loocv_rmse_model")
        mae = summary.get("loocv_mae_model")
    else:
        rmse = summary.get("in_sample_rmse")
        mae = summary.get("in_sample_mae")

    lines = [
        f"Spearman ρ  {_format_number(rho)}   nominal p  {_format_p(nominal)}",
        f"permutation p  {_format_p(permutation)}   family BH q  {_format_p(family_q)}",
        f"all-endpoint BH q  {_format_p(global_q)}   Pearson r  {_format_number(pearson)}",
        f"Pearson nominal p  {_format_p(pearson_p)}",
    ]
    if prefix == "in_sample":
        lines.append(
            "R²  "
            f"{_format_number(summary.get('in_sample_r2'))}  relative R²  "
            f"{_format_number(summary.get('in_sample_relative_r2'))}"
        )
    else:
        lines.append(
            "R²  "
            f"{_format_number(summary.get('loocv_r2'))}  Q²  "
            f"{_format_number(summary.get('loocv_q2'))}"
        )
    lines.extend(
        [
            f"RMSE  {_format_number(rmse)}   MAE  {_format_number(mae)}   n  {_format_number(n_subjects, 0)}",
            "permutations  "
            f"{_format_number(finite_permutations, 0)} / {_format_number(requested, 0)}",
        ]
    )
    return lines


def _display_fit(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    *,
    point_color: str,
    line_color: str,
    point_size: float,
    point_alpha: float,
    line_width: float,
    ribbon_alpha: float,
) -> None:
    ax.scatter(
        x,
        y,
        s=point_size,
        color=point_color,
        edgecolor="white",
        linewidth=0.45,
        alpha=point_alpha,
        zorder=4,
    )
    if x.size < 3 or np.ptp(x) <= np.finfo(float).eps:
        return
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    centered_x = x - x_mean
    sxx = float(np.sum(centered_x**2))
    if sxx <= np.finfo(float).eps:
        return
    slope = float(np.sum(centered_x * (y - y_mean)) / sxx)
    intercept = y_mean - slope * x_mean
    x_grid = np.linspace(float(np.min(x)), float(np.max(x)), 200)
    fitted = intercept + slope * x_grid
    ax.plot(x_grid, fitted, color=line_color, linewidth=line_width, zorder=5)

    residuals = y - (intercept + slope * x)
    degrees = x.size - 2
    if degrees < 1 or student_t is None:
        return
    residual_variance = float(np.sum(residuals**2) / degrees)
    if not np.isfinite(residual_variance):
        return
    standard_error = np.sqrt(
        residual_variance
        * (1.0 / x.size + ((x_grid - x_mean) ** 2) / sxx)
    )
    critical = float(student_t.ppf(0.975, degrees))
    if not np.isfinite(critical):
        return
    ax.fill_between(
        x_grid,
        fitted - critical * standard_error,
        fitted + critical * standard_error,
        color=line_color,
        alpha=ribbon_alpha,
        linewidth=0,
        zorder=3,
    )


def _shared_limits(values: Sequence[np.ndarray]) -> tuple[float, float]:
    finite_parts = [part[np.isfinite(part)] for part in values if part.size]
    finite_parts = [part for part in finite_parts if part.size]
    if not finite_parts:
        raise ValueError("no finite predictions or outcomes are available")
    joined = np.concatenate(finite_parts)
    lower = float(np.min(joined))
    upper = float(np.max(joined))
    span = upper - lower
    padding = max(span * 0.06, max(abs(lower), abs(upper), 1.0) * 0.02)
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
    )
    strip.set_xticks([])
    strip.set_yticks([])
    for spine in strip.spines.values():
        spine.set_visible(False)


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
            transparent=transparent,
            facecolor="none" if transparent else "white",
        )


def plot_in_sample_loocv_fit(
    subjects: pd.DataFrame,
    endpoint_summary: Mapping[str, Any],
    *,
    subject_id_column: str = "subject_id",
    outcome_column: str = "outcome",
    in_sample_column: str = "in_sample_prediction",
    loocv_column: str = "loocv_prediction",
    boxsize: Sequence[float] = (48.0, 42.0),
    panel_gap: Sequence[float] = (6.0, 3.0),
    dpi: int = 300,
    font_family: str = "Arial",
    point_size: float = 24.0,
    point_alpha: float = 0.82,
    show_identity: bool = True,
    output_paths: Sequence[str | Path] = (),
    transparent: bool = False,
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

    font = _resolve_font(font_family, ("Helvetica", "Arial Unicode MS", "DejaVu Sans"))
    layout = build_figure_layout(
        1,
        2,
        boxsize=boxsize,
        panel_gap=panel_gap,
        margins=(15.0, 13.0, 6.0, 10.0),
        top_strip_mm=4.5,
        strip_pad_mm=0.5,
    )
    fig = plt.figure(figsize=layout.figure_size_inches, dpi=dpi, facecolor="white")
    setattr(fig, "_mh_viz_layout", layout)

    outcome = pd.to_numeric(subjects[outcome_column], errors="coerce").to_numpy(dtype=float)
    in_sample = pd.to_numeric(subjects[in_sample_column], errors="coerce").to_numpy(dtype=float)
    loocv = pd.to_numeric(subjects[loocv_column], errors="coerce").to_numpy(dtype=float)
    limits = _shared_limits((outcome, in_sample, loocv))

    panel_specs = (
        ("In-sample", "in_sample", in_sample, "#B04759", "#7F1D3A"),
        ("LOOCV", "loocv", loocv, "#3E73A8", "#174A7E"),
    )
    for column, (label, prefix, prediction, point_color, line_color) in enumerate(panel_specs):
        ax = fig.add_axes(layout.panel_position(0, column))
        finite = np.isfinite(prediction) & np.isfinite(outcome)
        _display_fit(
            ax,
            prediction[finite],
            outcome[finite],
            point_color=point_color,
            line_color=line_color,
            point_size=point_size,
            point_alpha=point_alpha,
            line_width=1.8,
            ribbon_alpha=0.18,
        )
        if show_identity:
            ax.plot(limits, limits, color="#777777", linewidth=0.8, linestyle="--", zorder=2)
        ax.set_xlim(limits)
        ax.set_ylim(limits)
        ax.grid(True, color="#D9D9D9", linewidth=0.55, alpha=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=8.5, width=0.7, length=3)
        ax.set_xlabel("Predicted outcome", fontsize=9.5, fontfamily=font)
        if column == 0:
            ax.set_ylabel("Observed outcome", fontsize=9.5, fontfamily=font)
        else:
            ax.set_ylabel("")
        for tick in (*ax.get_xticklabels(), *ax.get_yticklabels()):
            tick.set_fontfamily(font)
        ax.text(
            0.035,
            0.965,
            "\n".join(_annotation_lines(endpoint_summary, prefix)),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.1,
            fontfamily=font,
            linespacing=1.18,
            bbox={
                "boxstyle": "round,pad=0.32",
                "facecolor": "white",
                "edgecolor": "#D0D0D0",
                "linewidth": 0.55,
                "alpha": 0.92,
            },
            zorder=10,
        )
        _add_strip(
            fig,
            layout,
            column,
            label,
            facecolor="#E5E5E5",
            text_color="#202020",
            fontsize=9.5,
            font_family=font,
        )

    model_family = str(endpoint_summary.get("model_family", "unknown model"))
    scale_id = str(endpoint_summary.get("scale_id", "unknown scale"))
    tau = _format_number(endpoint_summary.get("selected_tau"), 0)
    coverage = _format_number(endpoint_summary.get("selected_coverage"), 0)
    branch = str(endpoint_summary.get("final_branch", "unknown branch"))
    title = (
        f"{scale_id} · {model_family}\n"
        f"tau {tau} V/m · Coverage {coverage} · {branch}"
    )
    fig.text(
        0.5,
        0.992,
        title,
        ha="center",
        va="top",
        fontsize=10.5,
        fontfamily=font,
        linespacing=1.15,
    )
    _save_figure(fig, output_paths, dpi=dpi, transparent=transparent)
    return fig


__all__ = ["plot_in_sample_loocv_fit"]
