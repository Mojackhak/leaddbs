"""Load the shared voxel and fiber spatial-result visualization config."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


_EXPECTED_PROJECTION = {
    "grid_source": "role_seed",
    "direct_streamline_scope": "selected_sweet_sour_complete_path",
    "primary_target_score_fiber_scope": "final_resolver_valid_fiber_axis",
    "sensitivity_target_score_fiber_scope": "selected_sweet_sour",
    "voxel_composition_fiber_scope": "formal_connectome_all",
    "target_conditioned_scope": "seed_only",
    "per_fiber_per_voxel": "once",
    "target_hit_method": "segment_intersection",
    "target_membership": "independent_binary",
    "streamline_target_score": "equal_mean_over_finite_target_scores",
    "target_composition": "seed_voxel_target_pattern_counts",
    "streamline_weight_source": "uniform_one",
    "missing_target_score_policy": "exclude_target_then_renormalize_per_streamline",
    "no_scored_target_policy": "exclude_and_report",
}

_EXPECTED_LABELS = {
    "direct_streamline_colorbar_template": (
        "Mean selected-fiber partial Spearman ρ with {scale_display_name}"
    ),
    "target_conditioned_colorbar_template": (
        "Target-derived fiber partial Spearman ρ with {scale_display_name}"
    ),
}


def _required_mapping(
    parent: Mapping[str, Any],
    key: str,
    *,
    context: str,
) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}.{key} must be an object")
    return value


def load_spatial_result_config(path: str | Path) -> dict[str, Any]:
    """Parse and validate one spatial-result visualization YAML boundary."""

    config_path = Path(path).expanduser().resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"spatial visualization YAML object required: {config_path}")

    background = _required_mapping(payload, "background", context="root")
    if not str(background.get("path", "")).strip():
        raise ValueError("background.path must be a nonempty path")
    if background.get("loading") != "panel_local_lazy":
        raise ValueError("background.loading must be panel_local_lazy")

    display_map = _required_mapping(payload, "display_map", context="root")
    for key in ("fwhm_mm", "voxel_size_mm"):
        value = display_map.get(key)
        if type(value) not in {int, float} or float(value) <= 0.0:
            raise ValueError(f"display_map.{key} must be positive")
    support_threshold = display_map.get("support_weight_threshold")
    if (
        type(support_threshold) not in {int, float}
        or not 0.0 < float(support_threshold) < 1.0
    ):
        raise ValueError(
            "display_map.support_weight_threshold must be greater than 0 and less than 1"
        )

    outline = _required_mapping(payload, "outline", context="root")
    continuous_isovalue = outline.get("continuous_isovalue")
    if (
        type(continuous_isovalue) not in {int, float}
        or not 0.0 < float(continuous_isovalue) < 1.0
    ):
        raise ValueError(
            "outline.continuous_isovalue must be greater than 0 and less than 1"
        )

    voxel = _required_mapping(payload, "voxel", context="root")
    masks = _required_mapping(voxel, "masks", context="voxel")
    if set(masks) != {"reference", "addon"} or any(
        not str(value).strip() for value in masks.values()
    ):
        raise ValueError("voxel.masks must define reference and addon paths")
    voxel_labels = _required_mapping(voxel, "labels", context="voxel")
    if voxel_labels.get("colorbar_template") != (
        "Benefit-oriented partial Spearman ρ with {scale_display_name}"
    ):
        raise ValueError("voxel.labels.colorbar_template does not match the contract")

    fiber = _required_mapping(payload, "fiber", context="root")
    projection = _required_mapping(fiber, "projection", context="fiber")
    for key, expected in _EXPECTED_PROJECTION.items():
        if projection.get(key) != expected:
            raise ValueError(f"fiber.projection.{key} must be {expected!r}")

    cache = _required_mapping(fiber, "cache", context="fiber")
    if cache.get("physical_cache_kind") != (
        "whole_connectome_seed_voxel_target_patterns"
    ):
        raise ValueError("fiber.cache.physical_cache_kind is unsupported")
    chunk_size = cache.get("fiber_chunk_size")
    if type(chunk_size) is not int or chunk_size < 1:
        raise ValueError("fiber.cache.fiber_chunk_size must be positive")

    labels = _required_mapping(fiber, "labels", context="fiber")
    for key, expected in _EXPECTED_LABELS.items():
        if labels.get(key) != expected:
            raise ValueError(f"fiber.labels.{key} does not match the contract")

    target_chart = _required_mapping(fiber, "target_chart", context="fiber")
    if target_chart.get("order_policy") != "configured_target_catalog":
        raise ValueError(
            "fiber.target_chart.order_policy must be configured_target_catalog"
        )

    individualized = fiber.get("individualized_seed_target")
    if individualized is not None:
        if not isinstance(individualized, Mapping):
            raise ValueError("fiber.individualized_seed_target must be an object")
        color_limits = _required_mapping(fiber, "color_limits", context="fiber")
        if (
            color_limits.get("center") != 0.0
            or color_limits.get("scope") != "scale_role"
            or color_limits.get("symmetric") is not True
        ):
            raise ValueError(
                "fiber.color_limits must be zero-centered, symmetric, "
                "and scale-role local"
            )
        if individualized.get("projection_connectome_id") != "ppmi_85_ewert_2017":
            raise ValueError(
                "fiber.individualized_seed_target.projection_connectome_id "
                "is unsupported"
            )
        if not str(individualized.get("projection_connectome_path", "")).strip():
            raise ValueError(
                "fiber.individualized_seed_target.projection_connectome_path "
                "must be a nonempty path"
            )
        if individualized.get("coefficient_source") != (
            "final_benefit_oriented_partial_spearman"
        ):
            raise ValueError(
                "fiber.individualized_seed_target.coefficient_source is unsupported"
            )
        if individualized.get("shared_projection_kind") != "target_projections":
            raise ValueError(
                "fiber.individualized_seed_target.shared_projection_kind is unsupported"
            )

    seeds = _required_mapping(fiber, "seeds", context="fiber")
    if set(seeds) != {"reference", "addon"}:
        raise ValueError("fiber.seeds must define reference and addon")
    for role in ("reference", "addon"):
        seed = seeds[role]
        if (
            not isinstance(seed, Mapping)
            or seed.get("side") != "rh"
            or not str(seed.get("path", "")).strip()
        ):
            raise ValueError(
                f"fiber.seeds.{role} must define an explicit rh path"
            )
        outline_path = seed.get("outline_path")
        if outline_path is not None and not str(outline_path).strip():
            raise ValueError(
                f"fiber.seeds.{role}.outline_path must be a nonempty path"
            )

    targets = fiber.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("fiber.targets must be a nonempty ordered list")
    names: list[str] = []
    target_labels: list[str] = []
    for target in targets:
        if not isinstance(target, Mapping):
            raise ValueError("every fiber target must be an object")
        name = str(target.get("name", "")).strip()
        label = str(target.get("label", "")).strip()
        if (
            not name
            or not label
            or target.get("side") != "rh"
            or not str(target.get("path", "")).strip()
        ):
            raise ValueError(
                "every fiber target requires name, label, rh side, and path"
            )
        names.append(name)
        target_labels.append(label)
    if len(set(names)) != len(names):
        raise ValueError("fiber target names must be unique")
    if len(set(target_labels)) != len(target_labels):
        raise ValueError("fiber target labels must be unique")

    return payload


__all__ = ["load_spatial_result_config"]
