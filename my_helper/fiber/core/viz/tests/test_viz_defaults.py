"""Tests for the default visualization configuration plugin."""

from __future__ import annotations

import pytest

from my_helper.fiber.core.viz.plugin.default import (
    fiber_section_cfg,
    fit_cfg,
    get_fiber_section_cfg,
    get_fit_cfg,
    get_voxel_section_cfg,
    voxel_section_cfg,
)


def test_fit_cfg_preserves_reference_six_to_five_panel_geometry() -> None:
    assert fit_cfg["boxsize"] == (30.0, 25.0)
    assert fit_cfg["boxsize"][0] / fit_cfg["boxsize"][1] == pytest.approx(6.0 / 5.0)
    assert fit_cfg["panel_gap"] == (3.0, 3.0)
    assert fit_cfg["label_top_bg_color"] == "#D7E3E0"
    assert fit_cfg["label_fontsize"] == 7.0
    assert fit_cfg["axis_label_fontsize"] == 7.0
    assert fit_cfg["tick_label_fontsize"] == 6.0
    assert fit_cfg["annotation_fontsize"] == 6.0
    assert fit_cfg["strip_top_height_mm"] == 4.5
    assert fit_cfg["strip_pad_mm"] == 2.0
    assert fit_cfg["curve_line_color"] == "black"
    assert fit_cfg["curve_line_width"] == 1.0
    assert fit_cfg["ribbon_alpha"] == 0.30
    assert fit_cfg["show_top_right_axes"] is True
    assert fit_cfg["identity_line"] is False
    assert fit_cfg["share_x"] is True
    assert fit_cfg["share_y"] is True
    assert fit_cfg["annotation_location"] == "upper left"
    assert fit_cfg["transparent"] is True


def test_get_fit_cfg_returns_an_isolated_validated_copy() -> None:
    configured = get_fit_cfg({"dpi": 300})
    configured["boxsize"] = (60.0, 50.0)

    assert configured["dpi"] == 300
    assert fit_cfg["dpi"] == 600
    assert fit_cfg["boxsize"] == (30.0, 25.0)

    with pytest.raises(KeyError, match="unknown fit visualization settings"):
        get_fit_cfg({"selected_tau": 400.0})


def test_voxel_section_cfg_matches_the_accepted_mylfp_contract() -> None:
    assert voxel_section_cfg["boxsize"] == (30.0, 25.0)
    assert voxel_section_cfg["panel_gap"] == (3.0, 3.0)
    assert voxel_section_cfg["percent_list"] == (25.0, 50.0, 75.0)
    assert voxel_section_cfg["facets"] == ("Ax", "Cor", "Sag")
    assert voxel_section_cfg["resolution_mm"] == 0.1
    assert voxel_section_cfg["font_family"] == "Arial"
    assert voxel_section_cfg["background_percentiles"] == (0.0, 100.0)
    assert voxel_section_cfg["heat_scale_mode"] == "symmetric"
    assert voxel_section_cfg["mask_color"] == "#000000"
    assert voxel_section_cfg["mask_alpha"] == 1.0
    assert voxel_section_cfg["mask_linewidth_pt"] == 1.0
    assert voxel_section_cfg["mask_layer"] == "top"
    assert voxel_section_cfg["global_box_span_mm"] == (12.0, 10.0)
    assert voxel_section_cfg["colorbar_label"] == (
        "Benefit-oriented partial Spearman ρ"
    )
    assert voxel_section_cfg["label_top_bg_color"] == "#D7E3E0"
    assert voxel_section_cfg["label_right_bg_color"] == "#E3DCCF"
    assert voxel_section_cfg["global_scale_bar_length_mm"] == 2.0
    assert voxel_section_cfg["dpi"] == 600
    assert voxel_section_cfg["transparent"] is True


def test_get_voxel_section_cfg_returns_an_isolated_validated_copy() -> None:
    configured = get_voxel_section_cfg({"dpi": 72, "resolution_mm": 0.5})
    configured["boxsize"] = (12.0, 10.0)

    assert configured["dpi"] == 72
    assert configured["resolution_mm"] == 0.5
    assert voxel_section_cfg["dpi"] == 600
    assert voxel_section_cfg["boxsize"] == (30.0, 25.0)

    with pytest.raises(KeyError, match="unknown voxel-section visualization settings"):
        get_voxel_section_cfg({"scale_id": "pdq39_score"})


def test_fiber_section_cfg_reuses_the_accepted_spatial_aesthetics() -> None:
    assert fiber_section_cfg["boxsize"] == (30.0, 25.0)
    assert fiber_section_cfg["panel_gap"] == (3.0, 3.0)
    assert fiber_section_cfg["global_box_span_mm"] == (12.0, 10.0)
    assert fiber_section_cfg["font_family"] == "Arial"
    assert fiber_section_cfg["label_top_bg_color"] == "#D7E3E0"
    assert fiber_section_cfg["label_right_bg_color"] == "#E3DCCF"
    assert fiber_section_cfg["mask_linewidth_pt"] == 1.0
    assert fiber_section_cfg["background_loading_mode"] == "panel_local_lazy"
    assert fiber_section_cfg["heat_sampling_order"] == 0
    assert fiber_section_cfg["support_coordinate_mode"] == "affine_voxel_centers"
    assert fiber_section_cfg["dpi"] == 600

    configured = get_fiber_section_cfg({"dpi": 72})
    assert configured["dpi"] == 72
    assert fiber_section_cfg["dpi"] == 600
