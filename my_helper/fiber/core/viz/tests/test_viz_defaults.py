"""Tests for the default visualization configuration plugin."""

from __future__ import annotations

import pytest

from my_helper.fiber.core.viz.plugin.default import fit_cfg, get_fit_cfg


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
