"""MyLFP-compatible signed direct-voxel section visualization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from matplotlib.text import Text

from .colormaps import vik_colormap
from .plugin.default import get_voxel_section_cfg

try:
    import nibabel as nib
    from scipy.ndimage import map_coordinates
except ImportError:  # pragma: no cover - checked by the public entry point
    nib = None
    map_coordinates = None


ImageInput = str | Path | Any


@dataclass(frozen=True)
class _Volume:
    data: np.ndarray
    affine: np.ndarray
    inverse_affine: np.ndarray


@dataclass(frozen=True)
class _BackgroundCrop:
    volume: _Volume
    full_shape: tuple[int, int, int]
    full_dtype: str
    crop_shape: tuple[int, int, int]
    crop_bytes: int
    crop_slices: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]


_PLANE_AXES = {
    "Ax": (0, 1, 2),
    "Cor": (0, 2, 1),
    "Sag": (1, 2, 0),
}


def _require_dependencies() -> None:
    if nib is None or map_coordinates is None:
        raise ImportError(
            "voxel section visualization requires nibabel and scipy"
        )


def _resolve_font(preferred: str) -> str:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in (preferred, "Helvetica", "Arial Unicode MS", "DejaVu Sans"):
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def _configure_fonts(preferred: str) -> str:
    font = _resolve_font(preferred)
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = list(
        dict.fromkeys([font, "Arial", "Helvetica", "DejaVu Sans"])
    )
    return font


def _canonical_image(image: ImageInput):
    loaded = nib.load(str(image)) if isinstance(image, (str, Path)) else image
    if not isinstance(loaded, nib.spatialimages.SpatialImage):
        raise TypeError("NIfTI inputs must be paths or nibabel spatial images")
    if len(loaded.shape) != 3:
        raise ValueError("voxel section visualization requires 3D NIfTI images")
    return nib.as_closest_canonical(loaded)


def _load_volume(image: ImageInput, *, dtype: np.dtype = np.dtype(np.float32)) -> _Volume:
    canonical = _canonical_image(image)
    data = np.asarray(canonical.get_fdata(dtype=dtype))
    affine = np.asarray(canonical.affine, dtype=float)
    return _Volume(data=data, affine=affine, inverse_affine=np.linalg.inv(affine))


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int, int, int]:
    indices = np.where(mask)
    return tuple(
        value
        for axis in indices
        for value in (int(axis.min()), int(axis.max()))
    )


def _grid(
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    resolution_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    x_span = float(x_limits[1] - x_limits[0])
    y_span = float(y_limits[1] - y_limits[0])
    nx = max(2, int(round(x_span / resolution_mm)) + 1)
    ny = max(2, int(round(y_span / resolution_mm)) + 1)
    return (
        np.linspace(x_limits[0], x_limits[1], nx),
        np.linspace(y_limits[0], y_limits[1], ny),
    )


def _sample_slice(
    volume: _Volume,
    plane: str,
    fixed_mm: float,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    resolution_mm: float,
    *,
    order: int,
    fill: float,
) -> tuple[np.ndarray, list[float]]:
    x_mm, y_mm = _grid(x_limits, y_limits, resolution_mm)
    horizontal, vertical = np.meshgrid(x_mm, y_mm)
    fixed = np.full_like(horizontal, fixed_mm)
    if plane == "Ax":
        world = np.stack((horizontal, vertical, fixed), axis=-1)
    elif plane == "Cor":
        world = np.stack((horizontal, fixed, vertical), axis=-1)
    elif plane == "Sag":
        world = np.stack((fixed, horizontal, vertical), axis=-1)
    else:
        raise ValueError(f"unsupported plane: {plane}")
    voxel = nib.affines.apply_affine(volume.inverse_affine, world.reshape(-1, 3))
    sampled = map_coordinates(
        volume.data,
        (voxel[:, 0], voxel[:, 1], voxel[:, 2]),
        order=int(order),
        mode="constant",
        cval=float(fill),
        prefilter=False,
    ).reshape(horizontal.shape)
    return sampled, [x_mm[0], x_mm[-1], y_mm[0], y_mm[-1]]


def _slice_geometry(
    heat: _Volume,
    style: Mapping[str, Any],
    support_override: np.ndarray | None = None,
) -> tuple[
    np.ndarray,
    dict[tuple[str, str], dict[str, float]],
    dict[tuple[str, str], dict[str, tuple[float, float]]],
    tuple[str, ...],
    tuple[str, ...],
]:
    if support_override is None:
        support = np.isfinite(heat.data)
    else:
        support = np.asarray(support_override, dtype=bool)
        if support.shape != heat.data.shape:
            raise ValueError("slice-support mask must match its geometry volume")
    if not np.any(support):
        raise ValueError("heatmap contains no finite voxel support")
    xlo, xhi, ylo, yhi, zlo, zhi = _bbox(support)
    voxel_sizes = nib.affines.voxel_sizes(heat.affine)
    translations = heat.affine[:3, 3]
    coordinate_mode = str(style.get("support_coordinate_mode", "half_voxel_offset"))
    if coordinate_mode == "half_voxel_offset":
        coordinate_offset = 0.5
    elif coordinate_mode == "affine_voxel_centers":
        coordinate_offset = 0.0
    else:
        raise ValueError(
            "support_coordinate_mode must be half_voxel_offset or affine_voxel_centers"
        )
    x_all = translations[0] + (np.arange(xlo, xhi + 1) + coordinate_offset) * voxel_sizes[0]
    y_all = translations[1] + (np.arange(ylo, yhi + 1) + coordinate_offset) * voxel_sizes[1]
    z_all = translations[2] + (np.arange(zlo, zhi + 1) + coordinate_offset) * voxel_sizes[2]
    axes = (x_all, y_all, z_all)
    bounds = np.asarray(
        [[axis.min() for axis in axes], [axis.max() for axis in axes]],
        dtype=float,
    )
    support_sub = support[xlo : xhi + 1, ylo : yhi + 1, zlo : zhi + 1]

    facets = tuple(str(item).capitalize() for item in style["facets"])
    percent_values = tuple(float(item) for item in style["percent_list"])
    panel_labels = tuple(
        f"{int(value)}%" if value.is_integer() else f"{value:.1f}%"
        for value in percent_values
    )

    def valid_center_span(
        plane: str, fixed_mm: float
    ) -> tuple[float, float, float, float]:
        if plane == "Ax":
            index = int(np.argmin(np.abs(z_all - fixed_mm)))
            section = support_sub[:, :, index]
            horizontal_axis, vertical_axis = x_all, y_all
        elif plane == "Cor":
            index = int(np.argmin(np.abs(y_all - fixed_mm)))
            section = support_sub[:, index, :]
            horizontal_axis, vertical_axis = x_all, z_all
        elif plane == "Sag":
            index = int(np.argmin(np.abs(x_all - fixed_mm)))
            section = support_sub[index, :, :]
            horizontal_axis, vertical_axis = y_all, z_all
        else:
            raise ValueError(f"unsupported plane: {plane}")
        if np.any(section):
            indices = np.argwhere(section)
            x_min = float(np.min(horizontal_axis[indices[:, 0]]))
            x_max = float(np.max(horizontal_axis[indices[:, 0]]))
            y_min = float(np.min(vertical_axis[indices[:, 1]]))
            y_max = float(np.max(vertical_axis[indices[:, 1]]))
        else:
            x_min, x_max = float(horizontal_axis.min()), float(horizontal_axis.max())
            y_min, y_max = float(vertical_axis.min()), float(vertical_axis.max())
        return (
            0.5 * (x_min + x_max),
            0.5 * (y_min + y_max),
            max(1e-9, x_max - x_min),
            max(1e-9, y_max - y_min),
        )

    geometry: dict[tuple[str, str], dict[str, float]] = {}
    for plane in facets:
        fixed_axis = _PLANE_AXES[plane][2]
        fixed_min, fixed_max = bounds[:, fixed_axis]
        for label, percent in zip(panel_labels, percent_values, strict=True):
            fixed_mm = float(fixed_min + 0.01 * percent * (fixed_max - fixed_min))
            center_x, center_y, span_x, span_y = valid_center_span(plane, fixed_mm)
            geometry[(plane, label)] = {
                "center_x": center_x,
                "center_y": center_y,
                "span_x": span_x,
                "span_y": span_y,
                "fixed_mm": fixed_mm,
            }

    box_width, box_height = (float(item) for item in style["boxsize"])
    target_ratio = box_height / box_width
    fixed_span = style.get("global_box_span_mm")
    if fixed_span is not None:
        final_span_x, final_span_y = (float(item) for item in fixed_span)
        if final_span_x <= 0.0 or final_span_y <= 0.0:
            raise ValueError("global_box_span_mm values must be positive")
        if not np.isclose(final_span_y / final_span_x, target_ratio):
            raise ValueError(
                "global_box_span_mm must preserve the configured boxsize ratio"
            )
    else:
        raw_span_x = max(value["span_x"] for value in geometry.values())
        raw_span_y = max(value["span_y"] for value in geometry.values())
        if raw_span_y / raw_span_x <= target_ratio:
            final_span_x = raw_span_x
            final_span_y = target_ratio * raw_span_x
        else:
            final_span_y = raw_span_y
            final_span_x = raw_span_y / target_ratio

    ranges: dict[tuple[str, str], dict[str, tuple[float, float]]] = {}
    for key, value in geometry.items():
        ranges[key] = {
            "xlim": (
                value["center_x"] - final_span_x / 2.0,
                value["center_x"] + final_span_x / 2.0,
            ),
            "ylim": (
                value["center_y"] - final_span_y / 2.0,
                value["center_y"] + final_span_y / 2.0,
            ),
        }
    return bounds, geometry, ranges, facets, panel_labels


def _panel_world_bounds(
    geometry: Mapping[tuple[str, str], Mapping[str, float]],
    ranges: Mapping[tuple[str, str], Mapping[str, tuple[float, float]]],
) -> np.ndarray:
    values: list[tuple[float, float, float]] = []
    for key, item in geometry.items():
        plane, _ = key
        x_limits = ranges[key]["xlim"]
        y_limits = ranges[key]["ylim"]
        fixed = float(item["fixed_mm"])
        for horizontal in x_limits:
            for vertical in y_limits:
                if plane == "Ax":
                    values.append((horizontal, vertical, fixed))
                elif plane == "Cor":
                    values.append((horizontal, fixed, vertical))
                else:
                    values.append((fixed, horizontal, vertical))
    points = np.asarray(values, dtype=float)
    return np.vstack((np.min(points, axis=0), np.max(points, axis=0)))


def _single_panel_world_bounds(
    key: tuple[str, str],
    geometry: Mapping[tuple[str, str], Mapping[str, float]],
    ranges: Mapping[tuple[str, str], Mapping[str, tuple[float, float]]],
) -> np.ndarray:
    plane, _ = key
    fixed = float(geometry[key]["fixed_mm"])
    x_limits = ranges[key]["xlim"]
    y_limits = ranges[key]["ylim"]
    if plane == "Ax":
        values = (
            (x_limits[0], y_limits[0], fixed),
            (x_limits[0], y_limits[1], fixed),
            (x_limits[1], y_limits[0], fixed),
            (x_limits[1], y_limits[1], fixed),
        )
    elif plane == "Cor":
        values = (
            (x_limits[0], fixed, y_limits[0]),
            (x_limits[0], fixed, y_limits[1]),
            (x_limits[1], fixed, y_limits[0]),
            (x_limits[1], fixed, y_limits[1]),
        )
    else:
        values = (
            (fixed, x_limits[0], y_limits[0]),
            (fixed, x_limits[0], y_limits[1]),
            (fixed, x_limits[1], y_limits[0]),
            (fixed, x_limits[1], y_limits[1]),
        )
    points = np.asarray(values, dtype=float)
    return np.vstack((np.min(points, axis=0), np.max(points, axis=0)))


def _load_background_crop(
    image: ImageInput,
    world_bounds: np.ndarray,
) -> _BackgroundCrop:
    canonical = _canonical_image(image)
    if tuple(nib.aff2axcodes(canonical.affine)) != ("R", "A", "S"):
        raise ValueError("lazy anatomy input must be canonical RAS")
    corners = np.asarray(
        [
            (x, y, z)
            for x in world_bounds[:, 0]
            for y in world_bounds[:, 1]
            for z in world_bounds[:, 2]
        ],
        dtype=float,
    )
    voxel = nib.affines.apply_affine(np.linalg.inv(canonical.affine), corners)
    lower = np.floor(np.min(voxel, axis=0)).astype(int) - 2
    upper = np.ceil(np.max(voxel, axis=0)).astype(int) + 3
    shape = np.asarray(canonical.shape, dtype=int)
    lower = np.maximum(lower, 0)
    upper = np.minimum(upper, shape)
    if np.any(upper <= lower):
        raise ValueError("requested panels do not intersect the anatomy volume")
    slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper, strict=True))
    data = np.asanyarray(canonical.dataobj[slices])
    translation = np.eye(4, dtype=float)
    translation[:3, 3] = lower
    affine = np.asarray(canonical.affine @ translation, dtype=float)
    volume = _Volume(data=data, affine=affine, inverse_affine=np.linalg.inv(affine))
    return _BackgroundCrop(
        volume=volume,
        full_shape=tuple(int(item) for item in canonical.shape),
        full_dtype=str(canonical.get_data_dtype()),
        crop_shape=tuple(int(item) for item in data.shape),
        crop_bytes=int(data.nbytes),
        crop_slices=tuple((int(item.start), int(item.stop)) for item in slices),
    )


def _measure_text_inches(
    text: str,
    fontsize: float,
    *,
    rotation: float,
    font_family: str,
    dpi: int,
) -> tuple[float, float]:
    probe = plt.figure(figsize=(2, 2), dpi=dpi)
    artist = probe.text(
        0,
        0,
        text,
        fontsize=fontsize,
        rotation=rotation,
        fontfamily=font_family,
    )
    probe.canvas.draw()
    box = artist.get_window_extent(renderer=probe.canvas.get_renderer())
    plt.close(probe)
    return box.width / dpi, box.height / dpi


def _figure_layout(
    nrows: int,
    ncols: int,
    style: Mapping[str, Any],
    font_family: str,
) -> tuple[plt.Figure, np.ndarray, dict[str, float]]:
    box_width_mm, box_height_mm = (float(item) for item in style["boxsize"])
    gap_x_mm, gap_y_mm = (float(item) for item in style["panel_gap"])
    strip_top_mm = float(style["strip_top_height_mm"])
    strip_right_mm = float(style["strip_right_width_mm"])
    strip_pad_mm = float(style["strip_pad_mm"])
    dpi = int(style["dpi"])

    to_inches = lambda value: float(value) / 25.4
    box_width = to_inches(box_width_mm)
    box_height = to_inches(box_height_mm)
    gap_x, gap_y = to_inches(gap_x_mm), to_inches(gap_y_mm)
    grid_width = ncols * box_width + (ncols - 1) * gap_x
    grid_height = nrows * box_height + (nrows - 1) * gap_y
    right_strip_extra = to_inches(strip_right_mm + strip_pad_mm)
    top_strip_extra = to_inches(strip_top_mm + strip_pad_mm)

    left_margin = 0.03
    bottom_margin = 0.03
    if style["y_label"]:
        y_width, _ = _measure_text_inches(
            str(style["y_label"]),
            float(style["axis_label_fontsize"]),
            rotation=90,
            font_family=font_family,
            dpi=dpi,
        )
        left_margin += to_inches(style["y_label_offset_mm"]) + y_width
    if style["x_label"]:
        _, x_height = _measure_text_inches(
            str(style["x_label"]),
            float(style["axis_label_fontsize"]),
            rotation=0,
            font_family=font_family,
            dpi=dpi,
        )
        bottom_margin += to_inches(style["x_label_offset_mm"]) + x_height

    colorbar_pad = to_inches(style["colorbar_pad_mm"])
    colorbar_width = to_inches(style["colorbar_width_mm"])
    colorbar_label_width, _ = _measure_text_inches(
        str(style["colorbar_label"]),
        float(style["axis_label_fontsize"]),
        rotation=270,
        font_family=font_family,
        dpi=dpi,
    )
    colorbar_label_offset = to_inches(style["colorbar_label_offset_mm"])
    figure_width = (
        left_margin
        + grid_width
        + right_strip_extra
        + colorbar_pad
        + colorbar_width
        + colorbar_label_offset
        + colorbar_label_width
    )
    figure_height = bottom_margin + grid_height + top_strip_extra
    figure = plt.figure(
        figsize=(figure_width, figure_height),
        dpi=dpi,
        facecolor="none" if style["transparent"] else "white",
    )
    figure.set_layout_engine(None)
    axes = np.empty((nrows, ncols), dtype=object)
    panel_width_fraction = box_width / figure_width
    panel_height_fraction = box_height / figure_height
    gap_x_fraction = gap_x / figure_width
    gap_y_fraction = gap_y / figure_height
    left_fraction = left_margin / figure_width
    bottom_fraction = bottom_margin / figure_height
    for row in range(nrows):
        for column in range(ncols):
            x0 = left_fraction + column * (panel_width_fraction + gap_x_fraction)
            y0 = bottom_fraction + (nrows - 1 - row) * (
                panel_height_fraction + gap_y_fraction
            )
            axes[row, column] = figure.add_axes(
                [x0, y0, panel_width_fraction, panel_height_fraction]
            )
            if style["transparent"]:
                axes[row, column].set_facecolor("none")
    return figure, axes, {
        "figure_width_inches": figure_width,
        "figure_height_inches": figure_height,
        "left_fraction": left_fraction,
        "bottom_fraction": bottom_fraction,
        "grid_right_fraction": left_fraction + grid_width / figure_width,
        "grid_top_fraction": bottom_fraction + grid_height / figure_height,
        "colorbar_pad_fraction": colorbar_pad / figure_width,
        "colorbar_width_fraction": colorbar_width / figure_width,
        "colorbar_label_offset_fraction": colorbar_label_offset / figure_width,
    }


def _add_strips(
    figure: plt.Figure,
    axes: np.ndarray,
    column_labels: Sequence[str],
    row_labels: Sequence[str],
    style: Mapping[str, Any],
    font_family: str,
) -> float:
    figure_width, figure_height = figure.get_size_inches()
    top_height = float(style["strip_top_height_mm"]) / 25.4 / figure_height
    right_width = float(style["strip_right_width_mm"]) / 25.4 / figure_width
    pad_y = float(style["strip_pad_mm"]) / 25.4 / figure_height
    pad_x = float(style["strip_pad_mm"]) / 25.4 / figure_width
    for column, label in enumerate(column_labels):
        position = axes[0, column].get_position()
        strip = figure.add_axes(
            [position.x0, position.y1 + pad_y, position.width, top_height]
        )
        strip.set_gid("voxel-top-strip")
        strip.set_facecolor(style["label_top_bg_color"])
        strip.patch.set_visible(True)
        strip.patch.set_alpha(1.0)
        strip.text(
            0.5,
            0.5,
            label,
            ha="center",
            va="center",
            fontsize=style["label_fontsize"],
            color=style["label_text_color"],
            fontweight=style["label_fontweight"],
            fontfamily=font_family,
        )
        strip.set_xticks([])
        strip.set_yticks([])
        for spine in strip.spines.values():
            spine.set_visible(False)
    right_edge = 0.0
    for row, label in enumerate(row_labels):
        position = axes[row, -1].get_position()
        strip = figure.add_axes(
            [position.x1 + pad_x, position.y0, right_width, position.height]
        )
        strip.set_gid("voxel-right-strip")
        strip.set_facecolor(style["label_right_bg_color"])
        strip.patch.set_visible(True)
        strip.patch.set_alpha(1.0)
        strip.text(
            0.5,
            0.5,
            label,
            ha="center",
            va="center",
            rotation=-90,
            fontsize=style["label_fontsize"],
            color=style["label_text_color"],
            fontweight=style["label_fontweight"],
            fontfamily=font_family,
        )
        strip.set_xticks([])
        strip.set_yticks([])
        for spine in strip.spines.values():
            spine.set_visible(False)
        right_edge = max(right_edge, position.x1 + pad_x + right_width)
    return right_edge


def _draw_global_scale_bar(
    figure: plt.Figure,
    reference_axis: plt.Axes,
    reference_extent: Sequence[float],
    style: Mapping[str, Any],
    font_family: str,
) -> None:
    requested_mm = float(style["global_scale_bar_length_mm"])
    data_width = float(reference_extent[1] - reference_extent[0])
    axis_position = reference_axis.get_position()
    width_fraction = requested_mm / data_width * axis_position.width
    x_anchor, y_anchor = (float(item) for item in style["global_scale_bar_position"])
    width_fraction = min(width_fraction, max(0.0, x_anchor - 0.005))
    figure_height = figure.get_size_inches()[1]
    height_fraction = (
        float(style["global_scale_bar_height_mm"]) / 25.4 / figure_height
    )
    label_pad = (
        float(style["global_scale_bar_label_padding_mm"]) / 25.4 / figure_height
    )
    left = x_anchor - width_fraction
    figure.patches.append(
        Rectangle(
            (left, y_anchor),
            width_fraction,
            height_fraction,
            transform=figure.transFigure,
            facecolor=style["global_scale_bar_color"],
            edgecolor="none",
            alpha=style["global_scale_bar_alpha"],
        )
    )
    figure.text(
        left + width_fraction / 2.0,
        y_anchor - label_pad,
        style["global_scale_bar_label"],
        ha="center",
        va="top",
        fontsize=style["global_scale_bar_label_fontsize"],
        color=style["global_scale_bar_label_color"],
        fontfamily=font_family,
    )


def _save(
    figure: plt.Figure,
    output_paths: Sequence[str | Path],
    style: Mapping[str, Any],
) -> None:
    transparent_canvas = bool(style["transparent"])
    if transparent_canvas:
        figure.patch.set_facecolor((1.0, 1.0, 1.0, 0.0))
        figure.patch.set_alpha(0.0)
    for raw_path in output_paths:
        path = Path(raw_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(
            path,
            dpi=int(style["dpi"]),
            bbox_inches="tight" if style["tight_bounding_box"] else None,
            transparent=False,
            facecolor=figure.get_facecolor(),
            edgecolor="none",
        )


def plot_signed_voxel_sections(
    heat_image: ImageInput,
    *,
    background_image: ImageInput,
    mask_image: ImageInput,
    geometry_image: ImageInput | None = None,
    geometry_threshold: float = 0.0,
    style_config: Mapping[str, Any] | None = None,
    output_paths: Sequence[str | Path] = (),
) -> plt.Figure:
    """Render one signed benefit map using the accepted MyLFP section contract."""

    _require_dependencies()
    style = get_voxel_section_cfg(style_config)
    font = _configure_fonts(str(style["font_family"]))
    heat = _load_volume(heat_image)
    mask = _load_volume(mask_image)
    geometry_volume = heat
    geometry_support = None
    slice_support_source = "finite_heatmap"
    if geometry_image is not None:
        geometry_volume = _load_volume(geometry_image)
        geometry_support = (
            np.isfinite(geometry_volume.data)
            & (geometry_volume.data > float(geometry_threshold))
        )
        slice_support_source = "positive_geometry_image"
    bounds, geometry, ranges, facets, panel_labels = _slice_geometry(
        geometry_volume,
        style,
        geometry_support,
    )
    background_mode = str(
        style.get("background_loading_mode", "bounded_union_lazy")
    )
    if background_mode not in {"bounded_union_lazy", "panel_local_lazy"}:
        raise ValueError(
            "background_loading_mode must be bounded_union_lazy or panel_local_lazy"
        )
    background_crops: dict[tuple[str, str], _BackgroundCrop] = {}
    if background_mode == "bounded_union_lazy":
        shared_background = _load_background_crop(
            background_image,
            _panel_world_bounds(geometry, ranges),
        )
        for plane in facets:
            for label in panel_labels:
                background_crops[(plane, label)] = shared_background
    else:
        for plane in facets:
            for label in panel_labels:
                key = (plane, label)
                background_crops[key] = _load_background_crop(
                    background_image,
                    _single_panel_world_bounds(key, geometry, ranges),
                )

    cache: dict[
        tuple[str, str], tuple[np.ndarray, np.ma.MaskedArray, np.ndarray, list[float]]
    ] = {}
    background_values: list[np.ndarray] = []
    heat_values: list[np.ndarray] = []
    resolution = float(style["resolution_mm"])
    for plane in facets:
        for label in panel_labels:
            key = (plane, label)
            fixed = geometry[key]["fixed_mm"]
            x_limits = ranges[key]["xlim"]
            y_limits = ranges[key]["ylim"]
            anatomy_slice, _ = _sample_slice(
                background_crops[key].volume,
                plane,
                fixed,
                x_limits,
                y_limits,
                resolution,
                order=1,
                fill=np.nan,
            )
            heat_slice, extent = _sample_slice(
                heat,
                plane,
                fixed,
                x_limits,
                y_limits,
                resolution,
                order=int(style.get("heat_sampling_order", 1)),
                fill=np.nan,
            )
            heat_masked = np.ma.masked_where(~np.isfinite(heat_slice), heat_slice)
            mask_slice, _ = _sample_slice(
                mask,
                plane,
                fixed,
                x_limits,
                y_limits,
                resolution,
                order=0,
                fill=0.0,
            )
            if np.isfinite(anatomy_slice).any():
                background_values.append(anatomy_slice[np.isfinite(anatomy_slice)])
            finite_heat = heat_slice[np.isfinite(heat_slice)]
            if finite_heat.size:
                heat_values.append(finite_heat)
            cache[key] = (anatomy_slice, heat_masked, mask_slice, extent)
    if not heat_values:
        raise ValueError("sampled panels contain no finite heatmap values")
    joined_heat = np.concatenate(heat_values)
    absolute_limit = float(np.max(np.abs(joined_heat)))
    if absolute_limit <= np.finfo(float).eps:
        absolute_limit = 1.0
    heat_limits = (-absolute_limit, absolute_limit)
    if background_values:
        joined_background = np.concatenate(background_values)
        background_limits = tuple(
            float(item)
            for item in np.percentile(
                joined_background,
                tuple(style["background_percentiles"]),
            )
        )
    else:
        background_limits = (0.0, 1.0)
    if background_limits[1] <= background_limits[0]:
        background_limits = (background_limits[0], background_limits[0] + 1.0)

    figure, axes, layout = _figure_layout(
        len(facets), len(panel_labels), style, font
    )
    cmap = vik_colormap().with_extremes(bad=(0.0, 0.0, 0.0, 0.0))
    for row, plane in enumerate(facets):
        for column, label in enumerate(panel_labels):
            axis = axes[row, column]
            anatomy_slice, heat_slice, mask_slice, extent = cache[(plane, label)]
            lower, upper = background_limits
            anatomy_scaled = np.clip(
                (anatomy_slice - lower) / (upper - lower), 0.0, 1.0
            )
            if abs(float(style["background_gamma"]) - 1.0) > 1e-9:
                anatomy_scaled = np.power(
                    anatomy_scaled, float(style["background_gamma"])
                )
            axis.imshow(
                anatomy_scaled,
                extent=extent,
                origin="lower",
                cmap=style["background_colormap"],
                vmin=0.0,
                vmax=1.0,
                interpolation="nearest",
                alpha=style["background_alpha"],
                zorder=0,
            )
            axis.imshow(
                heat_slice,
                extent=extent,
                origin="lower",
                cmap=cmap,
                vmin=heat_limits[0],
                vmax=heat_limits[1],
                interpolation="nearest",
                alpha=style["heat_alpha"],
                zorder=2,
            )
            threshold = float(style["mask_threshold"])
            if np.nanmin(mask_slice) <= threshold < np.nanmax(mask_slice):
                axis.contour(
                    mask_slice,
                    levels=[threshold],
                    colors=[style["mask_color"]],
                    linewidths=[style["mask_linewidth_pt"]],
                    alpha=style["mask_alpha"],
                    extent=extent,
                    origin="lower",
                    zorder=4,
                )
            axis.set_aspect("equal")
            axis.set_xlim(extent[0], extent[1])
            axis.set_ylim(extent[2], extent[3])
            axis.set_xticks([])
            axis.set_yticks([])
            axis.set_xlabel("")
            axis.set_ylabel("")

    right_edge = _add_strips(
        figure, axes, panel_labels, facets, style, font
    )
    figure.text(
        layout["left_fraction"]
        + (layout["grid_right_fraction"] - layout["left_fraction"]) / 2.0,
        layout["bottom_fraction"]
        - float(style["x_label_offset_mm"]) / 25.4 / layout["figure_height_inches"],
        style["x_label"],
        ha="center",
        va="center",
        fontsize=style["axis_label_fontsize"],
        fontfamily=font,
    )
    figure.text(
        layout["left_fraction"]
        - float(style["y_label_offset_mm"]) / 25.4 / layout["figure_width_inches"],
        layout["bottom_fraction"]
        + (layout["grid_top_fraction"] - layout["bottom_fraction"]) / 2.0,
        style["y_label"],
        ha="center",
        va="center",
        rotation=90,
        fontsize=style["axis_label_fontsize"],
        fontfamily=font,
    )
    if style["draw_global_scale_bar"]:
        reference_axis = axes[-1, -1]
        reference_extent = cache[(facets[-1], panel_labels[-1])][3]
        _draw_global_scale_bar(
            figure, reference_axis, reference_extent, style, font
        )

    figure.canvas.draw()
    panel_bottom = min(axis.get_position().y0 for axis in axes.ravel())
    panel_top = max(axis.get_position().y1 for axis in axes.ravel())
    colorbar_x = min(0.98, right_edge + layout["colorbar_pad_fraction"])
    colorbar_width = min(
        layout["colorbar_width_fraction"], max(0.01, 0.99 - colorbar_x)
    )
    colorbar_axis = figure.add_axes(
        [colorbar_x, panel_bottom, colorbar_width, panel_top - panel_bottom]
    )
    scalar = mpl.cm.ScalarMappable(
        norm=mpl.colors.Normalize(vmin=heat_limits[0], vmax=heat_limits[1]),
        cmap=cmap,
    )
    scalar.set_array([])
    colorbar = figure.colorbar(scalar, cax=colorbar_axis)
    colorbar.ax.tick_params(labelsize=style["tick_label_fontsize"])
    for tick in colorbar.ax.get_yticklabels():
        tick.set_fontfamily(font)
    position = colorbar_axis.get_position()
    figure.text(
        position.x1 + layout["colorbar_label_offset_fraction"],
        position.y0 + position.height / 2.0,
        style["colorbar_label"],
        rotation=90,
        ha="center",
        va="center",
        fontsize=style["axis_label_fontsize"],
        fontfamily=font,
    )
    for text_artist in figure.findobj(match=Text):
        if text_artist.get_text():
            text_artist.set_fontfamily(font)

    unique_background_crops = list(
        {id(value): value for value in background_crops.values()}.values()
    )
    first_background = unique_background_crops[0]
    maximum_crop_shape = np.max(
        np.asarray([value.crop_shape for value in unique_background_crops], dtype=int),
        axis=0,
    )
    metadata = {
        "style_id": style["style_id"],
        "slice_support_source": slice_support_source,
        "bounds_mm": bounds.tolist(),
        "slice_coordinates_mm": {
            plane: [
                float(geometry[(plane, label)]["fixed_mm"])
                for label in panel_labels
            ]
            for plane in facets
        },
        "panel_ranges_mm": {
            f"{plane}:{label}": {
                "xlim": list(ranges[(plane, label)]["xlim"]),
                "ylim": list(ranges[(plane, label)]["ylim"]),
            }
            for plane in facets
            for label in panel_labels
        },
        "heat_limits": list(heat_limits),
        "background_limits": list(background_limits),
        "background_loading_mode": background_mode,
        "background_full_shape": list(first_background.full_shape),
        "background_full_dtype": first_background.full_dtype,
        "background_crop_shape": [int(value) for value in maximum_crop_shape],
        "background_crop_bytes": int(
            sum(value.crop_bytes for value in unique_background_crops)
        ),
        "background_crop_slices": [
            [list(item) for item in value.crop_slices]
            for value in unique_background_crops
        ],
        "background_crop_count": len(unique_background_crops),
        "background_full_float_loaded": False,
        "mask_threshold": style["mask_threshold"],
        "mask_color": style["mask_color"],
        "mask_alpha": style["mask_alpha"],
        "mask_linewidth_pt": style["mask_linewidth_pt"],
        "mask_layer": style["mask_layer"],
        "facets": list(facets),
        "percent_list": list(style["percent_list"]),
        "resolution_mm": style["resolution_mm"],
        "boxsize_mm": list(style["boxsize"]),
        "global_box_span_mm": (
            None
            if style["global_box_span_mm"] is None
            else list(style["global_box_span_mm"])
        ),
        "panel_gap_mm": list(style["panel_gap"]),
        "colorbar_label": style["colorbar_label"],
        "font_family": font,
        "special_character_font_policy": "fallback_only_if_missing",
        "label_top_bg_color": style["label_top_bg_color"],
        "label_right_bg_color": style["label_right_bg_color"],
        "strip_background_alpha": 1.0,
    }
    setattr(figure, "_mh_viz_voxel_section_metadata", metadata)
    setattr(figure, "_mh_viz_panel_axes", tuple(axes.ravel()))
    setattr(figure, "_mh_viz_style", dict(style))
    _save(figure, output_paths, style)
    return figure


__all__ = ["plot_signed_voxel_sections"]
