"""Mirrored target-score rainclouds for selected and coverage fiber sets."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mpl_colors
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from scipy.stats import gaussian_kde

from .layout import FigureLayout, build_figure_layout
from .plugin.default import get_target_score_raincloud_cfg


_UNSELECTED = np.int8(0)
_SWEET = np.int8(1)
_SOUR = np.int8(-1)


def _resolve_font(preferred: str, fallbacks: Sequence[str]) -> str:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in (preferred, *fallbacks):
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def _validate_target_inputs(
    *,
    target_ids: Sequence[str],
    target_scores: np.ndarray,
    coverage_fiber_ids: np.ndarray,
    coverage_scores: np.ndarray,
    selected_fiber_ids: np.ndarray,
    selected_is_sweet: np.ndarray,
    coverage_target_membership: np.ndarray,
) -> tuple[
    tuple[str, ...],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    normalized_targets = tuple(str(value).strip() for value in target_ids)
    if not normalized_targets or any(not value for value in normalized_targets):
        raise ValueError("target_ids must contain nonempty values")
    if len(set(normalized_targets)) != len(normalized_targets):
        raise ValueError("target_ids must be unique")

    scores = np.asarray(target_scores, dtype=np.float64)
    fiber_ids = np.asarray(coverage_fiber_ids, dtype=np.int64)
    fiber_scores = np.asarray(coverage_scores, dtype=np.float64)
    selected_ids = np.asarray(selected_fiber_ids, dtype=np.int64)
    selected_sweet = np.asarray(selected_is_sweet, dtype=np.bool_)
    membership = np.asarray(coverage_target_membership, dtype=np.bool_)
    if scores.shape != (len(normalized_targets),):
        raise ValueError("target_scores must align with target_ids")
    if fiber_ids.ndim != 1 or fiber_scores.shape != fiber_ids.shape:
        raise ValueError("coverage fiber IDs and scores must be aligned vectors")
    if selected_ids.ndim != 1 or selected_sweet.shape != selected_ids.shape:
        raise ValueError("selected fiber IDs and classes must be aligned vectors")
    if membership.shape != (fiber_ids.size, len(normalized_targets)):
        raise ValueError("coverage_target_membership has an incompatible shape")
    if np.unique(fiber_ids).size != fiber_ids.size:
        raise ValueError("coverage fiber IDs must be unique")
    if np.unique(selected_ids).size != selected_ids.size:
        raise ValueError("selected fiber IDs must be unique")
    if not np.all(np.isfinite(fiber_scores)):
        raise ValueError("coverage fiber scores must be finite")

    index_by_id = {int(value): index for index, value in enumerate(fiber_ids)}
    missing = [int(value) for value in selected_ids if int(value) not in index_by_id]
    if missing:
        raise ValueError(
            "selected fibers are absent from the coverage-qualified axis: "
            f"{missing[:10]}"
        )
    classes = np.full(fiber_ids.size, _UNSELECTED, dtype=np.int8)
    for fiber_id, is_sweet in zip(selected_ids, selected_sweet, strict=True):
        classes[index_by_id[int(fiber_id)]] = _SWEET if is_sweet else _SOUR

    for target_index in range(len(normalized_targets)):
        selected_hits = membership[:, target_index] & (classes != _UNSELECTED)
        expected = (
            float(np.mean(fiber_scores[selected_hits], dtype=np.float64))
            if np.any(selected_hits)
            else np.nan
        )
        observed = scores[target_index]
        if np.isnan(expected):
            if np.isfinite(observed):
                raise ValueError("a no-selected-hit target cannot have a finite score")
        elif not np.isclose(observed, expected, rtol=1e-12, atol=1e-12):
            raise ValueError("target score does not equal its selected-fiber mean")

    return normalized_targets, scores, fiber_ids, fiber_scores, classes, membership


def ranked_target_indices(
    target_ids: Sequence[str], target_scores: np.ndarray
) -> np.ndarray:
    """Return finite targets descending, then no-selected-hit targets in order."""

    normalized = tuple(str(value) for value in target_ids)
    scores = np.asarray(target_scores, dtype=np.float64)
    if scores.shape != (len(normalized),):
        raise ValueError("target_scores must align with target_ids")
    finite = [index for index, value in enumerate(scores) if np.isfinite(value)]
    finite.sort(key=lambda index: (-float(scores[index]), normalized[index]))
    missing = [index for index, value in enumerate(scores) if not np.isfinite(value)]
    return np.asarray([*finite, *missing], dtype=np.int64)


def target_order_indices(
    target_ids: Sequence[str],
    target_scores: np.ndarray,
    *,
    order_policy: str,
) -> np.ndarray:
    """Resolve the explicit target-order policy."""

    policy = str(order_policy)
    if policy == "configured_target_catalog":
        return np.arange(len(target_ids), dtype=np.int64)
    if policy == "ranked_selected_score":
        return ranked_target_indices(target_ids, target_scores)
    raise ValueError(f"unsupported target order policy: {policy!r}")


def shared_asymmetric_target_limits(
    score_arrays: Sequence[np.ndarray],
    *,
    lower_padding_fraction: float = 0.10,
    upper_padding_fraction: float = 0.15,
) -> tuple[float, float]:
    """Return shared limits padded from the finite jitter-score range."""

    lower_padding = float(lower_padding_fraction)
    upper_padding = float(upper_padding_fraction)
    if not np.isfinite(lower_padding) or lower_padding < 0:
        raise ValueError(
            "lower_padding_fraction must be finite and nonnegative"
        )
    if not np.isfinite(upper_padding) or upper_padding < 0:
        raise ValueError(
            "upper_padding_fraction must be finite and nonnegative"
        )
    finite_parts = []
    for array in score_arrays:
        values = np.asarray(array, dtype=np.float64)
        finite = values[np.isfinite(values)]
        if finite.size:
            finite_parts.append(finite)
    if not finite_parts:
        raise ValueError("at least one finite score is required for a shared y-axis")
    finite_scores = np.concatenate(finite_parts)
    minimum = float(np.min(finite_scores))
    maximum = float(np.max(finite_scores))
    observed_span = maximum - minimum
    effective_span = (
        observed_span
        if observed_span > 0.0
        else max(abs(minimum), abs(maximum), 1.0)
    )
    return (
        minimum - lower_padding * effective_span,
        maximum + upper_padding * effective_span,
    )


def build_target_fiber_distribution_rows(
    *,
    model_role: str,
    target_ids: Sequence[str],
    target_scores: np.ndarray,
    coverage_fiber_ids: np.ndarray,
    coverage_scores: np.ndarray,
    selected_fiber_ids: np.ndarray,
    selected_is_sweet: np.ndarray,
    coverage_target_membership: np.ndarray,
    target_order_policy: str = "ranked_selected_score",
) -> list[dict[str, Any]]:
    """Return one descriptive row per coverage-fiber target hit."""

    (
        normalized_targets,
        scores,
        fiber_ids,
        fiber_scores,
        classes,
        membership,
    ) = _validate_target_inputs(
        target_ids=target_ids,
        target_scores=target_scores,
        coverage_fiber_ids=coverage_fiber_ids,
        coverage_scores=coverage_scores,
        selected_fiber_ids=selected_fiber_ids,
        selected_is_sweet=selected_is_sweet,
        coverage_target_membership=coverage_target_membership,
    )
    order = target_order_indices(
        normalized_targets,
        scores,
        order_policy=target_order_policy,
    )
    rows: list[dict[str, Any]] = []
    class_names = {_SWEET: "sweet", _SOUR: "sour", _UNSELECTED: "unselected"}
    for rank, target_index in enumerate(order, start=1):
        hit_indices = np.flatnonzero(membership[:, target_index])
        hit_indices = hit_indices[np.argsort(fiber_ids[hit_indices], kind="stable")]
        selected_hit_indices = hit_indices[classes[hit_indices] != _UNSELECTED]
        coverage_mean = (
            float(np.mean(fiber_scores[hit_indices], dtype=np.float64))
            if hit_indices.size
            else np.nan
        )
        selected_count = int(selected_hit_indices.size)
        coverage_count = int(hit_indices.size)
        for fiber_index in hit_indices:
            fiber_class = classes[fiber_index]
            rows.append(
                {
                    "model_role": str(model_role),
                    "target_rank": rank,
                    "configured_target_index": int(target_index),
                    "target_id": normalized_targets[target_index],
                    "fiber_id": int(fiber_ids[fiber_index]),
                    "fiber_score": float(fiber_scores[fiber_index]),
                    "is_selected": bool(fiber_class != _UNSELECTED),
                    "fiber_class": class_names[fiber_class],
                    "selected_target_score": (
                        ""
                        if not np.isfinite(scores[target_index])
                        else float(scores[target_index])
                    ),
                    "all_coverage_target_mean": coverage_mean,
                    "selected_target_fiber_count": selected_count,
                    "coverage_target_fiber_count": coverage_count,
                }
            )
    return rows


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


def _target_layout(
    *,
    labels: Sequence[str],
    y_label: str,
    y_limits: tuple[float, float],
    style: Mapping[str, Any],
    font_family: str,
    dpi: int,
) -> FigureLayout:
    rotation = float(style["x_tick_rotation_degrees"])
    tick_sizes = [
        _measure_text_mm(
            label,
            fontsize=float(style["tick_label_fontsize"]),
            font_family=font_family,
            dpi=dpi,
            rotation=rotation,
        )
        for label in labels
    ]
    maximum_tick_height = max((height for _, height in tick_sizes), default=0.0)
    _, x_label_height = _measure_text_mm(
        str(style["x_label"]),
        fontsize=float(style["axis_label_fontsize"]),
        font_family=font_family,
        dpi=dpi,
    )
    y_tick_width = max(
        _measure_text_mm(
            f"{value:.2f}",
            fontsize=float(style["tick_label_fontsize"]),
            font_family=font_family,
            dpi=dpi,
        )[0]
        for value in y_limits
    )
    y_label_width, _ = _measure_text_mm(
        y_label,
        fontsize=float(style["axis_label_fontsize"]),
        font_family=font_family,
        dpi=dpi,
        rotation=90.0,
    )
    point_to_mm = 25.4 / 72.0
    tick_extra = (
        float(style["major_tick_length"]) + float(style["major_tick_padding"])
    ) * point_to_mm
    margins = (
        y_tick_width
        + tick_extra
        + float(style["y_label_offset_mm"])
        + y_label_width
        + 1.0,
        maximum_tick_height
        + tick_extra
        + float(style["x_label_offset_mm"])
        + x_label_height
        + 1.0,
        1.5,
        1.5,
    )
    base_width, base_height = (float(value) for value in style["boxsize_base"])
    return build_figure_layout(
        1,
        1,
        boxsize=(base_width * len(labels), base_height),
        panel_gap=(0.0, 0.0),
        margins=margins,
        top_strip_mm=0.0,
        strip_pad_mm=0.0,
    )


def _normalized_targetwise_p_values(
    target_ids: Sequence[str],
    values: Mapping[str, float | None] | None,
) -> dict[str, float | None]:
    if values is None:
        return {}
    normalized_targets = tuple(str(value) for value in target_ids)
    if set(values) != set(normalized_targets):
        raise ValueError("targetwise p values must contain exactly the plotted targets")
    normalized: dict[str, float | None] = {}
    for target_id in normalized_targets:
        raw = values[target_id]
        if raw is None:
            normalized[target_id] = None
            continue
        p_value = float(raw)
        if not np.isfinite(p_value) or p_value <= 0.0 or p_value > 1.0:
            raise ValueError("targetwise p values must be in the interval (0, 1]")
        normalized[target_id] = p_value
    return normalized


def _significance_stars(p_value: float) -> str | None:
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    return None


def _save_figure(
    figure: plt.Figure,
    output_paths: Sequence[str | Path],
    *,
    dpi: int,
    transparent: bool,
    tight: bool,
) -> None:
    for output_path in output_paths:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(
            path,
            dpi=dpi,
            transparent=transparent,
            bbox_inches="tight" if tight else None,
        )


def _draw_half_violin(
    axis: plt.Axes,
    *,
    values: np.ndarray,
    position: float,
    side: str,
    color: str,
    split_at_zero: bool,
    style: Mapping[str, Any],
) -> bool:
    unique = np.unique(values)
    if values.size < 2 or unique.size < 2:
        return False
    density_model = gaussian_kde(values, bw_method="scott")
    y_values = np.linspace(
        float(np.min(values)),
        float(np.max(values)),
        int(style["violin_density_points"]),
    )
    if float(np.min(values)) < 0.0 < float(np.max(values)):
        y_values = np.unique(np.concatenate((y_values, np.asarray([0.0]))))
    density = np.asarray(density_model(y_values), dtype=np.float64)
    maximum = float(np.max(density, initial=0.0))
    if not np.isfinite(maximum) or maximum <= 0.0:
        return False
    density /= maximum
    inner = float(style["violin_inner_offset"])
    width = float(style["violin_width"])
    if side == "left":
        flat = np.full_like(y_values, position - inner)
        curved = flat - width * density
    elif side == "right":
        flat = np.full_like(y_values, position + inner)
        curved = flat + width * density
    else:
        raise ValueError("half-violin side must be left or right")
    segments = (
        (
            (y_values <= 0.0, str(style["negative_color"])),
            (y_values >= 0.0, str(style["positive_color"])),
        )
        if split_at_zero
        else ((np.ones(y_values.size, dtype=np.bool_), color),)
    )
    drawn = False
    for keep, segment_color in segments:
        if np.sum(keep) < 2:
            continue
        axis.fill_betweenx(
            y_values[keep],
            flat[keep],
            curved[keep],
            facecolor=mpl_colors.to_rgba(
                segment_color, float(style["violin_fill_alpha"])
            ),
            edgecolor=segment_color,
            linewidth=float(style["violin_edge_width_pt"]),
            zorder=float(style["violin_zorder"]),
        )
        drawn = True
    return drawn


def _distribution_summary(values: np.ndarray) -> dict[str, float]:
    q1, median, q3 = np.percentile(values, (25.0, 50.0, 75.0))
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    lower_values = values[values >= lower_fence]
    upper_values = values[values <= upper_fence]
    return {
        "q1": float(q1),
        "median": float(median),
        "q3": float(q3),
        "mean": float(np.mean(values, dtype=np.float64)),
        "whisker_low": float(np.min(lower_values)),
        "whisker_high": float(np.max(upper_values)),
    }


def _draw_box_and_mean(
    axis: plt.Axes,
    *,
    values: np.ndarray,
    position: float,
    style: Mapping[str, Any],
) -> dict[str, float]:
    summary = _distribution_summary(values)
    width = float(style["box_width"])
    color = str(style["box_color"])
    line_width = float(style["box_line_width_pt"])
    axis.add_patch(
        Rectangle(
            (position - width / 2.0, summary["q1"]),
            width,
            summary["q3"] - summary["q1"],
            facecolor=mpl_colors.to_rgba(
                str(style["box_facecolor"]), float(style["box_fill_alpha"])
            ),
            edgecolor=color,
            linewidth=line_width,
            zorder=float(style["box_zorder"]),
        )
    )
    axis.vlines(
        position,
        summary["whisker_low"],
        summary["whisker_high"],
        colors=color,
        linewidth=line_width,
        zorder=float(style["box_zorder"]),
    )
    cap_width = width * float(style["whisker_cap_width_fraction"])
    axis.hlines(
        [summary["whisker_low"], summary["whisker_high"]],
        position - cap_width / 2.0,
        position + cap_width / 2.0,
        colors=color,
        linewidth=line_width,
        zorder=float(style["box_zorder"]),
    )
    axis.hlines(
        summary["median"],
        position - width / 2.0,
        position + width / 2.0,
        colors=color,
        linestyles="-",
        linewidth=float(style["median_line_width_pt"]),
        zorder=float(style["box_zorder"]) + 1.0,
    )
    mean_width = width * float(style["mean_line_width_fraction"])
    axis.hlines(
        summary["mean"],
        position - mean_width / 2.0,
        position + mean_width / 2.0,
        colors=color,
        linestyles=str(style["mean_line_style"]),
        linewidth=float(style["mean_line_width_pt"]),
        zorder=float(style["box_zorder"]) + 2.0,
    )
    return summary


def _offset_hash(offsets: np.ndarray) -> str:
    values = np.ascontiguousarray(offsets, dtype=np.float64)
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def plot_target_score_dual_raincloud(
    *,
    target_ids: Sequence[str],
    target_scores: np.ndarray,
    coverage_fiber_ids: np.ndarray,
    coverage_scores: np.ndarray,
    selected_fiber_ids: np.ndarray,
    selected_is_sweet: np.ndarray,
    coverage_target_membership: np.ndarray,
    scale_display_name: str,
    shared_y_limits: Sequence[float],
    target_display_labels: Sequence[str] | None = None,
    target_order_policy: str = "ranked_selected_score",
    targetwise_p_values: Mapping[str, float | None] | None = None,
    style_config: Mapping[str, Any] | None = None,
    output_paths: Sequence[str | Path] = (),
) -> plt.Figure:
    """Render selected and all-coverage target distributions with full jitter."""

    (
        normalized_targets,
        scores,
        fiber_ids,
        fiber_scores,
        classes,
        membership,
    ) = _validate_target_inputs(
        target_ids=target_ids,
        target_scores=target_scores,
        coverage_fiber_ids=coverage_fiber_ids,
        coverage_scores=coverage_scores,
        selected_fiber_ids=selected_fiber_ids,
        selected_is_sweet=selected_is_sweet,
        coverage_target_membership=coverage_target_membership,
    )
    limits = np.asarray(shared_y_limits, dtype=np.float64)
    if limits.shape != (2,) or not np.all(np.isfinite(limits)):
        raise ValueError("shared_y_limits must contain two finite values")
    lower_limit, upper_limit = (float(value) for value in limits)
    if lower_limit >= upper_limit:
        raise ValueError("shared_y_limits must be strictly increasing")
    plotted_scores = fiber_scores[np.any(membership, axis=1)]
    if not plotted_scores.size:
        raise ValueError("at least one finite jitter score is required")
    if (
        np.min(plotted_scores, initial=np.inf) < lower_limit
        or np.max(plotted_scores, initial=-np.inf) > upper_limit
    ):
        raise ValueError("shared_y_limits do not contain all jitter scores")

    style = get_target_score_raincloud_cfg(style_config)
    dpi = int(style["dpi"])
    font = _resolve_font(
        str(style["font_family"]),
        ("Helvetica", "Arial Unicode MS", "DejaVu Sans"),
    )
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = list(
        dict.fromkeys([font, "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"])
    )

    order = target_order_indices(
        normalized_targets,
        scores,
        order_policy=target_order_policy,
    )
    normalized_targetwise = _normalized_targetwise_p_values(
        normalized_targets,
        targetwise_p_values,
    )
    if target_display_labels is None:
        normalized_labels = tuple(value.replace("_", " ") for value in normalized_targets)
    else:
        normalized_labels = tuple(str(value).strip() for value in target_display_labels)
        if len(normalized_labels) != len(normalized_targets) or any(
            not value for value in normalized_labels
        ):
            raise ValueError("target_display_labels must align with target_ids")
    labels = [normalized_labels[index] for index in order]
    y_label = str(style["y_label_template"]).format(
        scale_display_name=str(scale_display_name)
    )
    rendered_y_label = str(style["y_label_render_template"]).format(
        scale_display_name=str(scale_display_name)
    )
    layout = _target_layout(
        labels=labels,
        y_label=rendered_y_label,
        y_limits=(lower_limit, upper_limit),
        style=style,
        font_family=font,
        dpi=dpi,
    )
    figure = plt.figure(
        figsize=layout.figure_size_inches,
        dpi=dpi,
        facecolor="none" if bool(style["transparent"]) else "white",
    )
    axis = figure.add_axes(layout.panel_position(0, 0))
    annotation_labels: dict[str, str | None] = {}
    if normalized_targetwise:
        for position, target_index in enumerate(order):
            target_id = normalized_targets[target_index]
            p_value = normalized_targetwise[target_id]
            label = None if p_value is None else _significance_stars(p_value)
            annotation_labels[target_id] = label
            if label is not None:
                axis.text(
                    float(position),
                    0.90,
                    label,
                    ha="center",
                    va="center",
                    fontsize=7.0,
                    fontfamily=font,
                    transform=axis.get_xaxis_transform(),
                    clip_on=True,
                    zorder=float(style["box_zorder"]) + 3.0,
                )
    positions = np.arange(len(order), dtype=np.float64)
    counts_by_target: dict[str, dict[str, int]] = {}
    selected_means: dict[str, float | None] = {}
    coverage_means: dict[str, float | None] = {}
    jitter_hashes: dict[str, str] = {}
    summaries: dict[str, dict[str, dict[str, float] | None]] = {}
    violin_drawn: dict[str, dict[str, bool]] = {}

    for position, target_index in zip(positions, order, strict=True):
        target_id = normalized_targets[target_index]
        hits = membership[:, target_index]
        selected_hits = hits & (classes != _UNSELECTED)
        all_indices = np.flatnonzero(hits)
        all_indices = all_indices[np.argsort(fiber_ids[all_indices], kind="stable")]
        selected_values = fiber_scores[selected_hits]
        all_values = fiber_scores[all_indices]
        selected_mean = scores[target_index]
        coverage_mean = (
            float(np.mean(all_values, dtype=np.float64)) if all_values.size else np.nan
        )
        rng = np.random.default_rng(int(style["jitter_seed"]) + int(target_index))
        offsets = (
            (rng.random(all_indices.size) - 0.5) * float(style["jitter_width"])
            if all_indices.size
            else np.empty(0, dtype=np.float64)
        )
        local_classes = classes[all_indices]
        for fiber_class, color in (
            (_UNSELECTED, str(style["coverage_color"])),
            (_SWEET, str(style["positive_color"])),
            (_SOUR, str(style["negative_color"])),
        ):
            local = local_classes == fiber_class
            if not np.any(local):
                continue
            axis.scatter(
                position + offsets[local],
                fiber_scores[all_indices[local]],
                s=float(style["jitter_size"]),
                c=color,
                edgecolors="none",
                linewidths=0.0,
                alpha=float(style["jitter_alpha"]),
                rasterized=bool(style["rasterize_jitter"]),
                zorder=float(style["jitter_zorder"]),
            )

        left_drawn = _draw_half_violin(
            axis,
            values=selected_values,
            position=float(position),
            side="left",
            color=str(style["positive_color"]),
            split_at_zero=True,
            style=style,
        )
        right_drawn = _draw_half_violin(
            axis,
            values=all_values,
            position=float(position),
            side="right",
            color=str(style["coverage_color"]),
            split_at_zero=False,
            style=style,
        )
        left_summary = (
            _draw_box_and_mean(
                axis,
                values=selected_values,
                position=float(position) - float(style["box_position_offset"]),
                style=style,
            )
            if selected_values.size
            else None
        )
        right_summary = (
            _draw_box_and_mean(
                axis,
                values=all_values,
                position=float(position) + float(style["box_position_offset"]),
                style=style,
            )
            if all_values.size
            else None
        )

        counts_by_target[target_id] = {
            "coverage": int(all_indices.size),
            "selected": int(np.sum(local_classes != _UNSELECTED)),
            "sweet": int(np.sum(local_classes == _SWEET)),
            "sour": int(np.sum(local_classes == _SOUR)),
            "unselected": int(np.sum(local_classes == _UNSELECTED)),
        }
        selected_means[target_id] = (
            None if not np.isfinite(selected_mean) else float(selected_mean)
        )
        coverage_means[target_id] = (
            None if not np.isfinite(coverage_mean) else float(coverage_mean)
        )
        jitter_hashes[target_id] = _offset_hash(offsets)
        summaries[target_id] = {
            "selected": left_summary,
            "all_coverage": right_summary,
        }
        violin_drawn[target_id] = {
            "selected": left_drawn,
            "all_coverage": right_drawn,
        }

    axis.axhline(
        0.0,
        color=str(style["zero_line_color"]),
        linestyle=str(style["zero_line_style"]),
        linewidth=float(style["zero_line_width_pt"]),
        alpha=float(style["zero_line_alpha"]),
        zorder=1,
    )
    axis.set_xlim(-0.5, len(order) - 0.5)
    axis.set_ylim(lower_limit, upper_limit)
    axis.set_xticks(positions, labels)
    axis.tick_params(
        axis="x",
        labelrotation=float(style["x_tick_rotation_degrees"]),
        labelsize=float(style["tick_label_fontsize"]),
        width=float(style["major_tick_width"]),
        length=float(style["major_tick_length"]),
        pad=float(style["major_tick_padding"]),
    )
    axis.tick_params(
        axis="y",
        labelsize=float(style["tick_label_fontsize"]),
        width=float(style["major_tick_width"]),
        length=float(style["major_tick_length"]),
        pad=float(style["major_tick_padding"]),
    )
    for tick in axis.get_xticklabels():
        tick.set_ha(str(style["x_tick_horizontal_alignment"]))
        tick.set_fontfamily(font)
    for tick in axis.get_yticklabels():
        tick.set_fontfamily(font)
    axis.set_xlabel(
        str(style["x_label"]),
        fontsize=float(style["axis_label_fontsize"]),
        fontfamily=font,
        labelpad=float(style["x_label_offset_mm"]) * 72.0 / 25.4,
    )
    axis.set_ylabel(
        rendered_y_label,
        fontsize=float(style["axis_label_fontsize"]),
        fontfamily=font,
        labelpad=float(style["y_label_offset_mm"]) * 72.0 / 25.4,
    )
    axis.grid(bool(style["grid"]))
    axis.spines["top"].set_visible(bool(style["show_top_right_axes"]))
    axis.spines["right"].set_visible(bool(style["show_top_right_axes"]))
    for spine in axis.spines.values():
        spine.set_linewidth(float(style["axes_line_width"]))

    metadata = {
        "style_id": style["style_id"],
        "target_order_policy": str(target_order_policy),
        "target_order": [normalized_targets[index] for index in order],
        "target_display_labels": labels,
        "missing_selected_target_ids": [
            normalized_targets[index] for index in order if not np.isfinite(scores[index])
        ],
        "counts_by_target": counts_by_target,
        "selected_target_means": selected_means,
        "all_coverage_target_means": coverage_means,
        "distribution_summaries": summaries,
        "violin_drawn": violin_drawn,
        "shared_y_limits": [lower_limit, upper_limit],
        "local_jitter_score_bounds": [
            float(np.min(plotted_scores)),
            float(np.max(plotted_scores)),
        ],
        "boxsize_base_mm": [float(value) for value in style["boxsize_base"]],
        "boxsize_mm": [float(value) for value in layout.boxsize_mm],
        "figure_size_mm": [float(value) for value in layout.figure_size_mm],
        "jitter_seed": int(style["jitter_seed"]),
        "jitter_width": float(style["jitter_width"]),
        "jitter_zorder": float(style["jitter_zorder"]),
        "violin_zorder": float(style["violin_zorder"]),
        "box_zorder": float(style["box_zorder"]),
        "jitter_offset_sha256_by_target": jitter_hashes,
        "jitter_is_descriptive_only": True,
        "formal_inference_fiber_scope": (
            "all_coverage" if normalized_targetwise else None
        ),
        "formal_inference_annotation": (
            "p_net_targetwise_significance_stars"
            if normalized_targetwise
            else None
        ),
        "targetwise_significance_star_by_target": annotation_labels,
        "significance_star_thresholds": {
            "*": "p_net_targetwise < 0.05",
            "**": "p_net_targetwise < 0.01",
            "***": "p_net_targetwise < 0.001",
        },
        "significance_star_axes_y": 0.90,
        "significance_star_fontsize_pt": 7.0,
        "annotation_strip_mm": 0.0,
        "multi_target_fibers_are_repeated": True,
        "selected_distribution_scope": "selected_sweet_sour",
        "coverage_distribution_scope": "final_resolver_valid_fiber_axis",
        "all_coverage_distribution_includes_selected": True,
        "kde_method": "gaussian_scott_clipped_to_observed_range",
        "selected_violin_color_rule": "score_lt_zero_blue_score_ge_zero_red",
        "boxplot_whisker_rule": "1.5_iqr",
        "box_width": float(style["box_width"]),
        "box_center_matches_violin_flat_edge": bool(
            np.isclose(
                float(style["box_position_offset"]),
                float(style["violin_inner_offset"]),
            )
        ),
        "mean_line_width_fraction": float(style["mean_line_width_fraction"]),
        "y_label": y_label,
        "rendered_y_label": rendered_y_label,
        "font_family_requested": str(style["font_family"]),
        "font_family_resolved": font,
    }
    setattr(figure, "_mh_viz_layout", layout)
    setattr(figure, "_mh_viz_style", dict(style))
    setattr(figure, "_mh_viz_target_score_metadata", metadata)
    _save_figure(
        figure,
        output_paths,
        dpi=dpi,
        transparent=bool(style["transparent"]),
        tight=bool(style["tight_bounding_box"]),
    )
    return figure


__all__ = [
    "build_target_fiber_distribution_rows",
    "plot_target_score_dual_raincloud",
    "ranked_target_indices",
    "shared_asymmetric_target_limits",
    "target_order_indices",
]
