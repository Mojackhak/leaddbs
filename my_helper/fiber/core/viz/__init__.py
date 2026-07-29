"""Reusable spatial and statistical visualization primitives.

The Python API is intentionally independent from MATLAB and Lead-DBS startup.
MATLAB scene helpers live beside this package and are discovered through the
repository's recursive MATLAB path setup.
"""

from .layout import DEFAULT_BOXSIZE_MM, FigureLayout, build_figure_layout
from .plugin.default import (
    DEFAULT_FIBER_SECTION_CONFIG,
    DEFAULT_FIT_CONFIG,
    DEFAULT_TARGET_SCORE_RAINCLOUD_CONFIG,
    DEFAULT_VOXEL_SECTION_CONFIG,
    fiber_section_cfg,
    fit_cfg,
    get_target_score_raincloud_cfg,
    get_fiber_section_cfg,
    get_fit_cfg,
    get_voxel_section_cfg,
    voxel_section_cfg,
    target_score_raincloud_cfg,
)

__all__ = [
    "DEFAULT_BOXSIZE_MM",
    "DEFAULT_FIBER_SECTION_CONFIG",
    "DEFAULT_FIT_CONFIG",
    "DEFAULT_TARGET_SCORE_RAINCLOUD_CONFIG",
    "DEFAULT_VOXEL_SECTION_CONFIG",
    "FigureLayout",
    "SpatialLayer",
    "build_figure_layout",
    "fiber_section_cfg",
    "fit_cfg",
    "get_fit_cfg",
    "get_target_score_raincloud_cfg",
    "get_fiber_section_cfg",
    "get_voxel_section_cfg",
    "plot_in_sample_loocv_fit",
    "plot_signed_voxel_sections",
    "plot_sweet_sour_slices",
    "run_formal_postprocess",
    "validate_formal_postprocess",
    "validate_formal_postprocess_output",
    "run_single_scale_paired_fit_postprocess",
    "run_single_scale_fiber_section_postprocess",
    "run_single_scale_voxel_section_postprocess",
    "voxel_section_cfg",
    "target_score_raincloud_cfg",
    "plot_target_score_dual_raincloud",
]


def __getattr__(name: str):
    """Load Matplotlib and NIfTI helpers only when their API is requested."""

    if name == "plot_in_sample_loocv_fit":
        from .model_fit import plot_in_sample_loocv_fit

        return plot_in_sample_loocv_fit
    if name == "plot_target_score_dual_raincloud":
        from .target_score_raincloud import plot_target_score_dual_raincloud

        return plot_target_score_dual_raincloud
    if name in {"SpatialLayer", "plot_sweet_sour_slices"}:
        from .spatial import SpatialLayer, plot_sweet_sour_slices

        return {
            "SpatialLayer": SpatialLayer,
            "plot_sweet_sour_slices": plot_sweet_sour_slices,
        }[name]
    if name == "run_single_scale_paired_fit_postprocess":
        from .paired_fit_postprocess import run_single_scale_paired_fit_postprocess

        return run_single_scale_paired_fit_postprocess
    if name in {
        "run_formal_postprocess",
        "validate_formal_postprocess",
        "validate_formal_postprocess_output",
    }:
        from .formal_postprocess import (
            run_formal_postprocess,
            validate_formal_postprocess,
            validate_formal_postprocess_output,
        )

        return {
            "run_formal_postprocess": run_formal_postprocess,
            "validate_formal_postprocess": validate_formal_postprocess,
            "validate_formal_postprocess_output": validate_formal_postprocess_output,
        }[name]
    if name == "run_single_scale_fiber_section_postprocess":
        from .fiber_section_postprocess import (
            run_single_scale_fiber_section_postprocess,
        )

        return run_single_scale_fiber_section_postprocess
    if name == "plot_signed_voxel_sections":
        from .voxel_sections import plot_signed_voxel_sections

        return plot_signed_voxel_sections
    if name == "run_single_scale_voxel_section_postprocess":
        from .voxel_section_postprocess import (
            run_single_scale_voxel_section_postprocess,
        )

        return run_single_scale_voxel_section_postprocess
    raise AttributeError(name)
