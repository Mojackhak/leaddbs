"""Reusable spatial and statistical visualization primitives.

The Python API is intentionally independent from MATLAB and Lead-DBS startup.
MATLAB scene helpers live beside this package and are discovered through the
repository's recursive MATLAB path setup.
"""

from .layout import DEFAULT_BOXSIZE_MM, FigureLayout, build_figure_layout

__all__ = [
    "DEFAULT_BOXSIZE_MM",
    "FigureLayout",
    "SpatialLayer",
    "build_figure_layout",
    "plot_in_sample_loocv_fit",
    "plot_sweet_sour_slices",
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
    raise AttributeError(name)
