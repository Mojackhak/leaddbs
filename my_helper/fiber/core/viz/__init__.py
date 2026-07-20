"""Reusable spatial and statistical visualization primitives.

The Python API is intentionally independent from MATLAB and Lead-DBS startup.
MATLAB scene helpers live beside this package and are discovered through the
repository's recursive MATLAB path setup.
"""

from .layout import DEFAULT_BOXSIZE_MM, FigureLayout, build_figure_layout
from .plugin.default import (
    DEFAULT_FIT_CONFIG,
    DEFAULT_VOXEL_SECTION_CONFIG,
    fit_cfg,
    get_fit_cfg,
    get_voxel_section_cfg,
    voxel_section_cfg,
)

__all__ = [
    "DEFAULT_BOXSIZE_MM",
    "DEFAULT_FIT_CONFIG",
    "DEFAULT_VOXEL_SECTION_CONFIG",
    "FigureLayout",
    "SpatialLayer",
    "build_figure_layout",
    "fit_cfg",
    "get_fit_cfg",
    "get_voxel_section_cfg",
    "plot_in_sample_loocv_fit",
    "plot_signed_voxel_sections",
    "plot_sweet_sour_slices",
    "run_single_scale_paired_fit_postprocess",
    "run_single_scale_voxel_section_postprocess",
    "voxel_section_cfg",
]


def __getattr__(name: str):
    """Load Matplotlib and NIfTI helpers only when their API is requested."""

    if name == "plot_in_sample_loocv_fit":
        from .model_fit import plot_in_sample_loocv_fit

        return plot_in_sample_loocv_fit
    if name in {"SpatialLayer", "plot_sweet_sour_slices"}:
        from .spatial import SpatialLayer, plot_sweet_sour_slices

        return {
            "SpatialLayer": SpatialLayer,
            "plot_sweet_sour_slices": plot_sweet_sour_slices,
        }[name]
    if name == "run_single_scale_paired_fit_postprocess":
        from .paired_fit_postprocess import run_single_scale_paired_fit_postprocess

        return run_single_scale_paired_fit_postprocess
    if name == "plot_signed_voxel_sections":
        from .voxel_sections import plot_signed_voxel_sections

        return plot_signed_voxel_sections
    if name == "run_single_scale_voxel_section_postprocess":
        from .voxel_section_postprocess import (
            run_single_scale_voxel_section_postprocess,
        )

        return run_single_scale_voxel_section_postprocess
    raise AttributeError(name)
