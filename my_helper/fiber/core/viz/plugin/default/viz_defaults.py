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


__all__ = [
    "DEFAULT_FIT_CONFIG",
    "FIT_BOXSIZE_MM",
    "FIT_PANEL_GAP_MM",
    "fit_cfg",
    "get_fit_cfg",
]
