"""Tests for mirrored target-score raincloud figures."""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest
from matplotlib import colors as mpl_colors
from matplotlib.collections import LineCollection, PathCollection, PolyCollection

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from my_helper.fiber.core.viz.target_score_raincloud import (
    _significance_stars,
    build_target_fiber_distribution_rows,
    plot_target_score_dual_raincloud,
    ranked_target_indices,
    shared_asymmetric_target_limits,
    target_order_indices,
)


def _synthetic_target_data() -> dict[str, object]:
    return {
        "target_ids": ("target_a", "target_b", "target_c"),
        "target_scores": np.asarray([0.4, -0.3, np.nan]),
        "coverage_fiber_ids": np.asarray([10, 20, 30, 40, 50, 60], dtype=np.int64),
        "coverage_scores": np.asarray([0.5, 0.3, -0.2, -0.4, 0.1, -0.1]),
        "selected_fiber_ids": np.asarray([10, 20, 30, 40], dtype=np.int64),
        "selected_is_sweet": np.asarray([True, True, False, False]),
        "coverage_target_membership": np.asarray(
            [
                [True, False, False],
                [True, False, False],
                [False, True, False],
                [False, True, False],
                [True, False, True],
                [False, True, True],
            ],
            dtype=np.bool_,
        ),
    }


def test_ranked_target_indices_puts_finite_scores_first_with_stable_rules() -> None:
    order = ranked_target_indices(
        ("z_target", "a_target", "missing_first", "missing_second"),
        np.asarray([0.2, 0.2, np.nan, np.nan]),
    )
    assert order.tolist() == [1, 0, 2, 3]


def test_configured_target_order_preserves_catalog_and_display_labels() -> None:
    order = target_order_indices(
        ("z_target", "a_target"),
        np.asarray([-0.4, 0.8]),
        order_policy="configured_target_catalog",
    )
    assert order.tolist() == [0, 1]

    data = _synthetic_target_data()
    figure = plot_target_score_dual_raincloud(
        **data,
        target_display_labels=("Target A", "Target B", "Target C"),
        target_order_policy="configured_target_catalog",
        scale_display_name="PDQ-39",
        shared_y_limits=(-0.49, 0.635),
        style_config={"dpi": 72, "formats": ("png",), "rasterize_jitter": False},
    )
    metadata = getattr(figure, "_mh_viz_target_score_metadata")
    assert metadata["target_order"] == ["target_a", "target_b", "target_c"]
    assert metadata["target_display_labels"] == [
        "Target A",
        "Target B",
        "Target C",
    ]
    assert metadata["target_order_policy"] == "configured_target_catalog"
    plt.close(figure)


def test_distribution_rows_partition_selected_and_unselected_fibers() -> None:
    data = _synthetic_target_data()
    rows = build_target_fiber_distribution_rows(model_role="reference", **data)

    assert len(rows) == 8
    assert {row["fiber_class"] for row in rows} == {
        "sweet",
        "sour",
        "unselected",
    }
    assert sum(bool(row["is_selected"]) for row in rows) == 4
    target_a = [row for row in rows if row["target_id"] == "target_a"]
    assert len(target_a) == 3
    assert {row["selected_target_fiber_count"] for row in target_a} == {2}
    assert {row["coverage_target_fiber_count"] for row in target_a} == {3}
    assert {row["selected_target_score"] for row in target_a} == {0.4}
    assert len({row["all_coverage_target_mean"] for row in target_a}) == 1
    assert target_a[0]["all_coverage_target_mean"] == pytest.approx(0.3)
    target_c = [row for row in rows if row["target_id"] == "target_c"]
    assert all(row["selected_target_score"] == "" for row in target_c)
    assert len({row["all_coverage_target_mean"] for row in target_c}) == 1
    assert target_c[0]["all_coverage_target_mean"] == pytest.approx(0.0)


def test_shared_limits_pad_scatter_range_asymmetrically() -> None:
    limits = shared_asymmetric_target_limits(
        (np.asarray([-0.5, 0.2]), np.asarray([0.4, np.nan])),
        lower_padding_fraction=0.10,
        upper_padding_fraction=0.15,
    )
    assert limits == pytest.approx((-0.59, 0.535))


def test_shared_limits_keep_constant_scatter_axis_nonzero() -> None:
    limits = shared_asymmetric_target_limits((np.asarray([0.25, 0.25]),))
    assert limits == pytest.approx((0.15, 0.40))


def test_raincloud_uses_all_fibers_colors_boxsize_and_deterministic_jitter(
    tmp_path,
) -> None:
    data = _synthetic_target_data()
    output = tmp_path / "target_scores.png"
    style = {"dpi": 72, "formats": ("png",), "rasterize_jitter": False}
    first = plot_target_score_dual_raincloud(
        **data,
        scale_display_name="PDQ-39",
        shared_y_limits=(-0.49, 0.635),
        style_config=style,
        output_paths=(output,),
    )
    second = plot_target_score_dual_raincloud(
        **data,
        scale_display_name="PDQ-39",
        shared_y_limits=(-0.49, 0.635),
        style_config=style,
    )
    first_metadata = getattr(first, "_mh_viz_target_score_metadata")
    second_metadata = getattr(second, "_mh_viz_target_score_metadata")

    assert output.is_file()
    assert first_metadata["target_order"] == ["target_a", "target_b", "target_c"]
    assert first_metadata["missing_selected_target_ids"] == ["target_c"]
    assert first_metadata["target_display_labels"] == [
        "target a",
        "target b",
        "target c",
    ]
    assert first_metadata["boxsize_mm"] == [24.0, 25.0]
    assert first_metadata["shared_y_limits"] == [-0.49, 0.635]
    assert first_metadata["local_jitter_score_bounds"] == [-0.4, 0.5]
    assert first_metadata["counts_by_target"]["target_a"] == {
        "coverage": 3,
        "selected": 2,
        "sweet": 2,
        "sour": 0,
        "unselected": 1,
    }
    assert first_metadata["counts_by_target"]["target_c"] == {
        "coverage": 2,
        "selected": 0,
        "sweet": 0,
        "sour": 0,
        "unselected": 2,
    }
    assert first_metadata["all_coverage_target_means"]["target_a"] == pytest.approx(
        0.3
    )
    assert first_metadata["jitter_offset_sha256_by_target"] == second_metadata[
        "jitter_offset_sha256_by_target"
    ]
    assert first_metadata["mean_line_width_fraction"] == 0.70
    assert first_metadata["box_width"] == 0.20
    assert first_metadata["box_center_matches_violin_flat_edge"] is True
    assert first_metadata["selected_violin_color_rule"] == (
        "score_lt_zero_blue_score_ge_zero_red"
    )
    assert first_metadata["jitter_zorder"] < first_metadata["violin_zorder"]
    assert first_metadata["violin_zorder"] < first_metadata["box_zorder"]
    assert first_metadata["all_coverage_distribution_includes_selected"] is True
    assert first.axes[0].get_xlabel() == "Target"
    assert all(tick.get_rotation() == 90.0 for tick in first.axes[0].get_xticklabels())
    assert all(tick.get_ha() == "center" for tick in first.axes[0].get_xticklabels())
    first.canvas.draw()
    renderer = first.canvas.get_renderer()
    for position, tick in enumerate(first.axes[0].get_xticklabels()):
        tick_display_x = first.axes[0].transData.transform((float(position), 0.0))[0]
        tick_box = tick.get_window_extent(renderer=renderer)
        assert tick_box.x0 + tick_box.width / 2.0 == pytest.approx(
            tick_display_x, abs=0.5
        )
    assert first.axes[0].get_ylabel() == (
        "Target-derived fiber\npartial Spearman ρ\nwith PDQ-39"
    )

    scatter_colors = {
        tuple(collection.get_facecolors()[0])
        for collection in first.axes[0].collections
        if isinstance(collection, PathCollection)
        and collection.get_facecolors().size
    }
    assert mpl_colors.to_rgba("#F2000E") in scatter_colors
    assert mpl_colors.to_rgba("#0E6AAF") in scatter_colors
    assert mpl_colors.to_rgba("#CCCCCC") in scatter_colors
    plt.close(first)
    plt.close(second)


def test_significance_star_thresholds_are_strict() -> None:
    assert _significance_stars(0.05) is None
    assert _significance_stars(0.049) == "*"
    assert _significance_stars(0.01) == "*"
    assert _significance_stars(0.009) == "**"
    assert _significance_stars(0.001) == "**"
    assert _significance_stars(0.0009) == "***"


def test_raincloud_adds_targetwise_stars_inside_unchanged_axis() -> None:
    data = _synthetic_target_data()
    figure = plot_target_score_dual_raincloud(
        **data,
        scale_display_name="PDQ-39",
        shared_y_limits=(-0.49, 0.635),
        targetwise_p_values={
            "target_a": 0.032,
            "target_b": 0.0001,
            "target_c": 0.009,
        },
        style_config={"dpi": 72, "formats": ("png",), "rasterize_jitter": False},
    )
    metadata = getattr(figure, "_mh_viz_target_score_metadata")
    assert len(figure.axes) == 1
    assert figure.axes[0].get_ylim() == pytest.approx((-0.49, 0.635))
    assert metadata["boxsize_mm"] == [24.0, 25.0]
    assert metadata["annotation_strip_mm"] == 0.0
    assert metadata["formal_inference_annotation"] == (
        "p_net_targetwise_significance_stars"
    )
    assert metadata["targetwise_significance_star_by_target"] == {
        "target_a": "*",
        "target_b": "***",
        "target_c": "**",
    }
    assert len(figure.axes[0].texts) == 3
    assert all(text.get_position()[1] == 0.90 for text in figure.axes[0].texts)
    assert all(text.get_fontsize() == 7.0 for text in figure.axes[0].texts)
    plt.close(figure)


def test_raincloud_splits_selected_density_at_zero_and_layers_jitter_lowest() -> None:
    figure = plot_target_score_dual_raincloud(
        target_ids=("signed_target",),
        target_scores=np.asarray([0.13333333333333333]),
        coverage_fiber_ids=np.asarray([1, 2, 3], dtype=np.int64),
        coverage_scores=np.asarray([-0.4, 0.2, 0.6]),
        selected_fiber_ids=np.asarray([1, 2, 3], dtype=np.int64),
        selected_is_sweet=np.asarray([False, True, True]),
        coverage_target_membership=np.ones((3, 1), dtype=np.bool_),
        scale_display_name="PDQ-39",
        shared_y_limits=(-0.5, 0.75),
        style_config={"dpi": 72, "formats": ("png",), "rasterize_jitter": False},
    )
    axis = figure.axes[0]
    jitter = [
        collection
        for collection in axis.collections
        if isinstance(collection, PathCollection)
    ]
    violins = [
        collection
        for collection in axis.collections
        if isinstance(collection, PolyCollection)
    ]
    summary_lines = [
        collection
        for collection in axis.collections
        if isinstance(collection, LineCollection)
    ]
    violin_colors = {
        tuple(collection.get_facecolors()[0])
        for collection in violins
        if collection.get_facecolors().size
    }
    box_centers = sorted(
        patch.get_x() + patch.get_width() / 2.0 for patch in axis.patches
    )
    mean_lines = [
        collection
        for collection in summary_lines
        if collection.get_zorder() == 6.0
    ]
    mean_segments = [
        segment for collection in mean_lines for segment in collection.get_segments()
    ]
    mean_centers = sorted(
        (float(segment[0, 0]) + float(segment[1, 0])) / 2.0
        for segment in mean_segments
    )
    mean_widths = [
        float(segment[1, 0]) - float(segment[0, 0]) for segment in mean_segments
    ]

    assert mpl_colors.to_rgba("#0E6AAF", 0.30) in violin_colors
    assert mpl_colors.to_rgba("#F2000E", 0.30) in violin_colors
    assert mpl_colors.to_rgba("#CCCCCC", 0.30) in violin_colors
    assert {collection.get_zorder() for collection in jitter} == {0.5}
    assert {collection.get_zorder() for collection in violins} == {2.0}
    assert {patch.get_zorder() for patch in axis.patches} == {4.0}
    assert box_centers == pytest.approx([-0.22, 0.22])
    assert len(mean_lines) == 2
    assert mean_centers == pytest.approx(box_centers)
    assert mean_widths == pytest.approx([0.20 * 0.70, 0.20 * 0.70])
    plt.close(figure)


def test_raincloud_validation_rejects_target_mean_mismatch() -> None:
    data = _synthetic_target_data()
    data["target_scores"] = np.asarray([0.45, -0.3, np.nan])
    with pytest.raises(ValueError, match="selected-fiber mean"):
        build_target_fiber_distribution_rows(model_role="reference", **data)


def test_raincloud_validation_rejects_selected_fiber_outside_coverage_axis() -> None:
    data = _synthetic_target_data()
    data["selected_fiber_ids"] = np.asarray([10, 20, 30, 99], dtype=np.int64)
    with pytest.raises(ValueError, match="absent from the coverage-qualified axis"):
        build_target_fiber_distribution_rows(model_role="reference", **data)
