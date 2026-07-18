"""Boxsize-driven MNI section visualization for sweet and sour maps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import ListedColormap, to_rgba
from matplotlib.patches import Patch

from .layout import DEFAULT_BOXSIZE_MM, FigureLayout, build_figure_layout

try:
    import nibabel as nib
    from scipy.ndimage import map_coordinates
except ImportError:  # pragma: no cover - checked at public API entry
    nib = None
    map_coordinates = None


ImageInput = str | Path | Any


@dataclass(frozen=True)
class SpatialLayer:
    """One spatial overlay sampled in its own world-coordinate image grid."""

    image: ImageInput
    label: str
    color: str
    threshold: float = 0.5
    alpha: float = 0.62
    sampling_order: int = 0
    outline_only: bool = False
    linewidth: float = 0.8


@dataclass(frozen=True)
class _Volume:
    data: np.ndarray
    affine: np.ndarray
    inverse_affine: np.ndarray


_PLANE_AXES = {
    "Ax": (0, 1, 2, "MNI x (mm)", "MNI y (mm)"),
    "Cor": (0, 2, 1, "MNI x (mm)", "MNI z (mm)"),
    "Sag": (1, 2, 0, "MNI y (mm)", "MNI z (mm)"),
}


def _require_spatial_dependencies() -> None:
    if nib is None or map_coordinates is None:
        raise ImportError(
            "spatial visualization requires nibabel and scipy in the active environment"
        )


def _resolve_font(preferred: str) -> str:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in (preferred, "Helvetica", "Arial Unicode MS", "DejaVu Sans"):
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def _load_volume(image: ImageInput) -> _Volume:
    _require_spatial_dependencies()
    loaded = nib.load(str(image)) if isinstance(image, (str, Path)) else image
    if not isinstance(loaded, nib.spatialimages.SpatialImage):
        raise TypeError("spatial image inputs must be paths or nibabel spatial images")
    canonical = nib.as_closest_canonical(loaded)
    data = np.asarray(canonical.get_fdata(dtype=np.float32))
    if data.ndim != 3:
        raise ValueError("spatial visualization requires three-dimensional NIfTI images")
    affine = np.asarray(canonical.affine, dtype=float)
    return _Volume(data=data, affine=affine, inverse_affine=np.linalg.inv(affine))


def _support_world_bounds(volumes: Sequence[_Volume], thresholds: Sequence[float]) -> np.ndarray:
    world_points: list[np.ndarray] = []
    for volume, threshold in zip(volumes, thresholds, strict=True):
        support = np.isfinite(volume.data) & (np.abs(volume.data) > float(threshold))
        indices = np.argwhere(support)
        if not indices.size:
            continue
        lower = np.min(indices, axis=0)
        upper = np.max(indices, axis=0)
        corners = np.asarray(
            [
                (x, y, z)
                for x in (lower[0], upper[0])
                for y in (lower[1], upper[1])
                for z in (lower[2], upper[2])
            ],
            dtype=float,
        )
        world_points.append(nib.affines.apply_affine(volume.affine, corners))
    if not world_points:
        raise ValueError("sweet and sour inputs contain no finite suprathreshold support")
    joined = np.concatenate(world_points, axis=0)
    return np.vstack((np.min(joined, axis=0), np.max(joined, axis=0)))


def _slice_coordinates(
    facets: Sequence[str],
    bounds: np.ndarray,
    percent_list: Sequence[float],
    explicit: Mapping[str, Sequence[float]] | None,
) -> dict[str, tuple[float, ...]]:
    output: dict[str, tuple[float, ...]] = {}
    expected_count: int | None = None
    for plane in facets:
        if plane not in _PLANE_AXES:
            raise ValueError(f"unsupported plane: {plane}")
        fixed_axis = _PLANE_AXES[plane][2]
        if explicit is not None and plane in explicit:
            values = tuple(float(item) for item in explicit[plane])
        else:
            values = tuple(
                float(bounds[0, fixed_axis] + float(percent) * 0.01 * np.ptp(bounds[:, fixed_axis]))
                for percent in percent_list
            )
        if not values or not all(np.isfinite(item) for item in values):
            raise ValueError(f"slice coordinates for {plane} must be finite and nonempty")
        if expected_count is None:
            expected_count = len(values)
        elif len(values) != expected_count:
            raise ValueError("every plane must contain the same number of slice coordinates")
        output[plane] = values
    return output


def _global_ranges(
    bounds: np.ndarray,
    facets: Sequence[str],
    boxsize: Sequence[float],
    padding_fraction: float,
    minimum_span_mm: float,
) -> tuple[float, float, dict[str, tuple[tuple[float, float], tuple[float, float]]]]:
    if padding_fraction < 0 or not np.isfinite(padding_fraction):
        raise ValueError("padding_fraction must be finite and nonnegative")
    spans: list[tuple[float, float]] = []
    for plane in facets:
        horizontal_axis, vertical_axis = _PLANE_AXES[plane][:2]
        spans.append(
            (
                max(float(np.ptp(bounds[:, horizontal_axis])), minimum_span_mm),
                max(float(np.ptp(bounds[:, vertical_axis])), minimum_span_mm),
            )
        )
    span_x = max(item[0] for item in spans) * (1.0 + 2.0 * padding_fraction)
    span_y = max(item[1] for item in spans) * (1.0 + 2.0 * padding_fraction)
    target_ratio = float(boxsize[1]) / float(boxsize[0])
    if span_y / span_x < target_ratio:
        span_y = span_x * target_ratio
    else:
        span_x = span_y / target_ratio

    centers = np.mean(bounds, axis=0)
    ranges: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for plane in facets:
        horizontal_axis, vertical_axis = _PLANE_AXES[plane][:2]
        cx = float(centers[horizontal_axis])
        cy = float(centers[vertical_axis])
        ranges[plane] = (
            (cx - span_x / 2.0, cx + span_x / 2.0),
            (cy - span_y / 2.0, cy + span_y / 2.0),
        )
    return span_x, span_y, ranges


def _sampling_grid(
    plane: str,
    fixed_coordinate: float,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    resolution_mm: float,
) -> tuple[np.ndarray, list[float]]:
    if not np.isfinite(resolution_mm) or resolution_mm <= 0:
        raise ValueError("resolution_mm must be a positive finite number")
    nx = max(2, int(round((x_limits[1] - x_limits[0]) / resolution_mm)) + 1)
    ny = max(2, int(round((y_limits[1] - y_limits[0]) / resolution_mm)) + 1)
    x = np.linspace(x_limits[0], x_limits[1], nx)
    y = np.linspace(y_limits[0], y_limits[1], ny)
    horizontal, vertical = np.meshgrid(x, y)
    fixed = np.full_like(horizontal, fixed_coordinate)
    if plane == "Ax":
        world = np.stack((horizontal, vertical, fixed), axis=-1)
    elif plane == "Cor":
        world = np.stack((horizontal, fixed, vertical), axis=-1)
    else:
        world = np.stack((fixed, horizontal, vertical), axis=-1)
    return world, [x_limits[0], x_limits[1], y_limits[0], y_limits[1]]


def _sample(volume: _Volume, world: np.ndarray, *, order: int, fill: float) -> np.ndarray:
    flat = world.reshape(-1, 3)
    voxel = nib.affines.apply_affine(volume.inverse_affine, flat)
    sampled = map_coordinates(
        volume.data,
        (voxel[:, 0], voxel[:, 1], voxel[:, 2]),
        order=int(order),
        mode="constant",
        cval=float(fill),
        prefilter=False,
    )
    return sampled.reshape(world.shape[:2])


def _add_top_strip(
    fig: plt.Figure,
    layout: FigureLayout,
    row: int,
    column: int,
    label: str,
    *,
    font: str,
    fontsize: float,
    facecolor: str,
) -> None:
    strip = fig.add_axes(layout.top_strip_position(row, column))
    strip.set_facecolor(facecolor)
    strip.text(0.5, 0.5, label, ha="center", va="center", fontsize=fontsize, fontfamily=font)
    strip.set_xticks([])
    strip.set_yticks([])
    for spine in strip.spines.values():
        spine.set_visible(False)


def _add_right_strip(
    fig: plt.Figure,
    layout: FigureLayout,
    row: int,
    label: str,
    *,
    font: str,
    fontsize: float,
    facecolor: str,
) -> None:
    strip = fig.add_axes(layout.right_strip_position(row))
    strip.set_facecolor(facecolor)
    strip.text(
        0.5,
        0.5,
        label,
        ha="center",
        va="center",
        rotation=-90,
        fontsize=fontsize,
        fontfamily=font,
    )
    strip.set_xticks([])
    strip.set_yticks([])
    for spine in strip.spines.values():
        spine.set_visible(False)


def _save(fig: plt.Figure, output_paths: Sequence[str | Path], dpi: int, transparent: bool) -> None:
    for output_path in output_paths:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            path,
            dpi=dpi,
            transparent=transparent,
            facecolor="none" if transparent else "white",
        )


def plot_sweet_sour_slices(
    sweet_image: ImageInput,
    sour_image: ImageInput,
    *,
    background_image: ImageInput | None = None,
    atlas_layers: Sequence[SpatialLayer] = (),
    sweet_label: str = "Sweet",
    sour_label: str = "Sour",
    sweet_color: str = "#C43C4E",
    sour_color: str = "#3268A8",
    sweet_threshold: float = 0.5,
    sour_threshold: float = 0.5,
    layer_alpha: float = 0.68,
    percent_list: Sequence[float] = (25.0, 50.0, 75.0),
    slice_coordinates_mm: Mapping[str, Sequence[float]] | None = None,
    facets: Sequence[str] = ("Ax", "Cor", "Sag"),
    resolution_mm: float = 0.5,
    boxsize: Sequence[float] = DEFAULT_BOXSIZE_MM,
    panel_gap: Sequence[float] = (3.0, 3.0),
    support_padding_fraction: float = 0.12,
    minimum_span_mm: float = 12.0,
    background_percentiles: tuple[float, float] = (2.0, 98.0),
    background_gamma: float = 1.0,
    title: str | None = None,
    font_family: str = "Arial",
    dpi: int = 300,
    output_paths: Sequence[str | Path] = (),
    transparent: bool = False,
) -> plt.Figure:
    """Plot sweet and sour NIfTI support in canonical MNI sections.

    Fiber models use this function with sweet and sour density NIfTIs. Such
    inputs remain display derivatives of fiber-level models.
    """

    _require_spatial_dependencies()
    if not 0 <= layer_alpha <= 1:
        raise ValueError("layer_alpha must be between zero and one")
    if not np.isfinite(background_gamma) or background_gamma <= 0:
        raise ValueError("background_gamma must be positive and finite")
    if not facets:
        raise ValueError("facets must contain at least one plane")

    sweet = _load_volume(sweet_image)
    sour = _load_volume(sour_image)
    background = _load_volume(background_image) if background_image is not None else None
    resolved_atlas = [(layer, _load_volume(layer.image)) for layer in atlas_layers]
    bounds = _support_world_bounds((sweet, sour), (sweet_threshold, sour_threshold))
    coordinates = _slice_coordinates(facets, bounds, percent_list, slice_coordinates_mm)
    _, _, ranges = _global_ranges(
        bounds,
        facets,
        boxsize,
        support_padding_fraction,
        minimum_span_mm,
    )

    ncols = len(coordinates[facets[0]])
    layout = build_figure_layout(
        len(facets),
        ncols,
        boxsize=boxsize,
        panel_gap=panel_gap,
        margins=(13.0, 13.0, 6.0, 10.0),
        top_strip_mm=4.0,
        strip_pad_mm=0.4,
        right_strip_mm=4.0,
    )
    fig = plt.figure(figsize=layout.figure_size_inches, dpi=dpi, facecolor="white")
    setattr(fig, "_mh_viz_layout", layout)
    setattr(
        fig,
        "_mh_viz_spatial_metadata",
        {
            "bounds_mm": bounds.tolist(),
            "slice_coordinates_mm": {key: list(value) for key, value in coordinates.items()},
            "facets": list(facets),
            "fiber_density_is_display_derivative": True,
        },
    )
    font = _resolve_font(font_family)

    background_limits: tuple[float, float] | None = None
    if background is not None:
        finite_background = background.data[np.isfinite(background.data)]
        if finite_background.size:
            lower, upper = np.percentile(finite_background, background_percentiles)
            if np.isfinite(lower) and np.isfinite(upper) and upper > lower:
                background_limits = (float(lower), float(upper))

    layer_specs = (
        SpatialLayer(sweet_image, sweet_label, sweet_color, sweet_threshold, layer_alpha),
        SpatialLayer(sour_image, sour_label, sour_color, sour_threshold, layer_alpha),
    )
    volume_by_label = {sweet_label: sweet, sour_label: sour}

    for row, plane in enumerate(facets):
        x_limits, y_limits = ranges[plane]
        _, _, _, _, y_axis_label = _PLANE_AXES[plane]
        for column, fixed_coordinate in enumerate(coordinates[plane]):
            ax = fig.add_axes(layout.panel_position(row, column))
            world, extent = _sampling_grid(
                plane,
                fixed_coordinate,
                x_limits,
                y_limits,
                resolution_mm,
            )
            ax.set_facecolor("#0C0C0C")
            if background is not None:
                bg = _sample(background, world, order=1, fill=np.nan)
                if background_limits is not None:
                    lower, upper = background_limits
                    scaled = np.clip((bg - lower) / (upper - lower), 0.0, 1.0)
                    scaled = np.power(scaled, background_gamma)
                    ax.imshow(
                        scaled,
                        extent=extent,
                        origin="lower",
                        cmap="gray",
                        vmin=0.0,
                        vmax=1.0,
                        interpolation="bilinear",
                        zorder=0,
                    )
            for layer in layer_specs:
                sampled = _sample(volume_by_label[layer.label], world, order=0, fill=0.0)
                mask = sampled > layer.threshold
                masked = np.ma.masked_where(~mask, mask.astype(float))
                ax.imshow(
                    masked,
                    extent=extent,
                    origin="lower",
                    cmap=ListedColormap([to_rgba(layer.color, layer.alpha)]),
                    vmin=0.0,
                    vmax=1.0,
                    interpolation="nearest",
                    zorder=2,
                )
            for layer, volume in resolved_atlas:
                sampled = _sample(
                    volume,
                    world,
                    order=int(layer.sampling_order),
                    fill=0.0,
                )
                if np.nanmax(sampled) > layer.threshold and np.nanmin(sampled) < layer.threshold:
                    ax.contour(
                        sampled,
                        levels=[layer.threshold],
                        colors=[layer.color],
                        linewidths=layer.linewidth,
                        alpha=layer.alpha,
                        extent=extent,
                        origin="lower",
                        zorder=3,
                    )
            ax.set_xlim(x_limits)
            ax.set_ylim(y_limits)
            ax.set_aspect("equal", adjustable="box")
            ax.tick_params(colors="#333333", labelsize=7.5, width=0.6, length=2.5)
            for spine in ax.spines.values():
                spine.set_color("#555555")
                spine.set_linewidth(0.55)
            if row == len(facets) - 1:
                ax.set_xlabel("MNI horizontal coordinate (mm)", fontsize=8.0, fontfamily=font)
            else:
                ax.set_xlabel("")
            if column == 0:
                ax.set_ylabel(y_axis_label, fontsize=8.0, fontfamily=font)
            else:
                ax.set_ylabel("")
            for tick in (*ax.get_xticklabels(), *ax.get_yticklabels()):
                tick.set_fontfamily(font)
            _add_top_strip(
                fig,
                layout,
                row,
                column,
                f"{fixed_coordinate:.1f} mm",
                font=font,
                fontsize=8.3,
                facecolor="#E4E4E4",
            )
        _add_right_strip(
            fig,
            layout,
            row,
            plane,
            font=font,
            fontsize=8.5,
            facecolor="#E4E4E4",
        )

    handles = [
        Patch(facecolor=to_rgba(sweet_color, layer_alpha), edgecolor="none", label=sweet_label),
        Patch(facecolor=to_rgba(sour_color, layer_alpha), edgecolor="none", label=sour_label),
    ]
    handles.extend(
        Patch(facecolor="none", edgecolor=layer.color, linewidth=layer.linewidth, label=layer.label)
        for layer in atlas_layers
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.003),
        ncol=max(2, len(handles)),
        frameon=False,
        prop={"family": font, "size": 8.5},
    )
    if title:
        fig.text(0.5, 0.995, title, ha="center", va="top", fontsize=10.5, fontfamily=font)
    _save(fig, output_paths, dpi=dpi, transparent=transparent)
    return fig


__all__ = ["SpatialLayer", "plot_sweet_sour_slices"]
