"""Default visual style for dual-frequency postprocess figures.

This module contains rendering choices only. Scientific model selections and
statistics are always loaded from completed canonical publications.
"""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Final, Mapping


FIT_BOXSIZE_MM: Final[tuple[float, float]] = (30.0, 25.0)
FIT_PANEL_GAP_MM: Final[tuple[float, float]] = (3.0, 3.0)
VOXEL_SECTION_BOXSIZE_MM: Final[tuple[float, float]] = (30.0, 25.0)
VOXEL_SECTION_PANEL_GAP_MM: Final[tuple[float, float]] = (3.0, 3.0)

_FIT_CONFIG: Final[dict[str, Any]] = {
    "style_id": "paired_in_sample_loocv_fit_mylfp_v1",
    "boxsize": FIT_BOXSIZE_MM,
    "panel_gap": FIT_PANEL_GAP_MM,
    "dpi": 600,
    "formats": ("png", "pdf"),
    "font_family": "Arial",
    "palette": "viridis",
    "color_var": "subject_id",
    "jitter_alpha": 1.0,
    "jitter_size": 2.0,
    "curve_line_color": "black",
    "curve_line_width": 1.0,
    "ribbon_alpha": 0.30,
    "confidence_level": 0.95,
    "grid": False,
    "show_top_right_axes": True,
    "label_fontsize": 7.0,
    "label_top_bg_color": "#D7E3E0",
    "label_text_color": "#000000",
    "label_fontweight": "bold",
    "strip_top_height_mm": 4.5,
    "strip_right_width_mm": 0.0,
    "strip_pad_mm": 2.0,
    "x_label_offset_mm": 5.0,
    "y_label_offset_mm": 5.0,
    "title_fontsize": 7.0,
    "axis_label_fontsize": 7.0,
    "tick_label_fontsize": 6.0,
    "annotation_fontsize": 6.0,
    "annotation_location": "upper left",
    "annotation_inset_fraction": (0.05, 0.95),
    "annotation_box_alpha": 0.0,
    "annotation_metrics": (
        "spearman_rho",
        "permutation_p_plus_one_two_sided",
    ),
    "identity_line": False,
    "identity_line_color": "#404040",
    "identity_line_style": "--",
    "identity_line_width": 1.0,
    "share_x": True,
    "share_y": True,
    "axis_padding_fraction": 0.05,
    "legend_location": "none",
    "axes_line_width": 1.0,
    "major_tick_width": 1.0,
    "major_tick_length": 2.0,
    "major_tick_padding": 1.0,
    "axis_label_padding": 1.0,
    "tight_bounding_box": True,
    "transparent": True,
}

DEFAULT_FIT_CONFIG: Final[Mapping[str, Any]] = MappingProxyType(_FIT_CONFIG)
fit_cfg: Final[Mapping[str, Any]] = DEFAULT_FIT_CONFIG


_VOXEL_SECTION_CONFIG: Final[dict[str, Any]] = {
    "style_id": "pdq39_voxel_sections_mylfp_v2",
    "boxsize": VOXEL_SECTION_BOXSIZE_MM,
    "panel_gap": VOXEL_SECTION_PANEL_GAP_MM,
    "percent_list": (25.0, 50.0, 75.0),
    "facets": ("Ax", "Cor", "Sag"),
    "resolution_mm": 0.1,
    "heat_support_mode": "finite",
    "heat_colormap": "vik",
    "heat_scale_mode": "symmetric",
    "heat_alpha": 0.95,
    "background_colormap": "gray",
    "background_percentiles": (0.0, 100.0),
    "background_gamma": 1.0,
    "background_alpha": 1.0,
    "mask_threshold": 0.05,
    "mask_color": "#000000",
    "mask_alpha": 1.0,
    "mask_linewidth_pt": 1.0,
    "mask_layer": "top",
    "global_span_mode": "max",
    "enforce_global_box_span": True,
    "global_box_span_mm": (12.0, 10.0),
    "x_label": "Slice position (%)",
    "y_label": "Slice plane",
    "show_tick_labels": False,
    "title": None,
    "font_family": "Arial",
    "label_fontsize": 7.0,
    "label_top_bg_color": "#D7E3E0",
    "label_right_bg_color": "#E3DCCF",
    "label_text_color": "#000000",
    "label_fontweight": "bold",
    "axis_label_fontsize": 7.0,
    "tick_label_fontsize": 7.0,
    "strip_top_height_mm": 4.5,
    "strip_right_width_mm": 4.5,
    "strip_pad_mm": 2.0,
    "x_label_offset_mm": 5.0,
    "y_label_offset_mm": 5.0,
    "colorbar_width_mm": 3.0,
    "colorbar_pad_mm": 2.0,
    "colorbar_label_offset_mm": 9.0,
    "colorbar_label": "Benefit-oriented partial Spearman ρ",
    "draw_global_scale_bar": True,
    "global_scale_bar_length_mm": 2.0,
    "global_scale_bar_position": (0.815, 0.05),
    "global_scale_bar_color": "#000000",
    "global_scale_bar_alpha": 1.0,
    "global_scale_bar_height_mm": 1.5,
    "global_scale_bar_label": "2 mm",
    "global_scale_bar_label_fontsize": 6.0,
    "global_scale_bar_label_color": "#000000",
    "global_scale_bar_label_padding_mm": 1.0,
    "dpi": 600,
    "formats": ("png", "pdf"),
    "transparent": True,
    "tight_bounding_box": True,
}

DEFAULT_VOXEL_SECTION_CONFIG: Final[Mapping[str, Any]] = MappingProxyType(
    _VOXEL_SECTION_CONFIG
)
voxel_section_cfg: Final[Mapping[str, Any]] = DEFAULT_VOXEL_SECTION_CONFIG


def get_fit_cfg(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return an isolated fit-style configuration with validated overrides."""

    config = deepcopy(dict(DEFAULT_FIT_CONFIG))
    if overrides is None:
        return config
    unknown = sorted(set(overrides) - set(DEFAULT_FIT_CONFIG))
    if unknown:
        raise KeyError(f"unknown fit visualization settings: {unknown}")
    config.update(dict(overrides))
    return config


def get_voxel_section_cfg(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an isolated direct-voxel section style configuration."""

    config = deepcopy(dict(DEFAULT_VOXEL_SECTION_CONFIG))
    if overrides is None:
        return config
    unknown = sorted(set(overrides) - set(DEFAULT_VOXEL_SECTION_CONFIG))
    if unknown:
        raise KeyError(f"unknown voxel-section visualization settings: {unknown}")
    config.update(dict(overrides))
    return config


__all__ = [
    "DEFAULT_FIT_CONFIG",
    "DEFAULT_VOXEL_SECTION_CONFIG",
    "FIT_BOXSIZE_MM",
    "FIT_PANEL_GAP_MM",
    "VOXEL_SECTION_BOXSIZE_MM",
    "VOXEL_SECTION_PANEL_GAP_MM",
    "fit_cfg",
    "get_fit_cfg",
    "get_voxel_section_cfg",
    "voxel_section_cfg",
]
