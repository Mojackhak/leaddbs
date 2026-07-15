"""Deterministic direct-voxel exposure and outcome fixtures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


N_SUBJECTS = 16
N_SIGNAL_VOXELS = 24
N_BACKGROUND_VOXELS = 8
N_VOXELS = N_SIGNAL_VOXELS + N_BACKGROUND_VOXELS
TAU_GRID = (100, 150, 180, 200, 220, 250, 300, 350, 400, 500)
COVERAGE_GRID = (5, 6, 7, 8, 10, 12)


def subject_ids() -> tuple[str, ...]:
    """Return stable synthetic subject identifiers."""
    return tuple(f"sub-{index:02d}" for index in range(1, N_SUBJECTS + 1))


def latent_values() -> np.ndarray:
    """Return the exposure-linked subject latent variable."""
    return np.linspace(-1.5, 1.5, N_SUBJECTS, dtype=np.float64)


def baseline_values() -> np.ndarray:
    """Return a fixed, nonconstant baseline vector."""
    return np.array(
        [17, 23, 19, 26, 21, 16, 25, 20, 24, 18, 27, 22, 15, 28, 14, 29],
        dtype=np.float64,
    )


def delta_reference_scores() -> np.ndarray:
    """Return a fixed DeltaReferenceScore vector independent of the baseline."""
    return np.array(
        [-1.2, 0.4, 1.1, -0.7, 0.2, 1.4, -0.3, 0.8, -1.0, 0.6, 1.3, -0.5, 0.0, 1.0, -0.9, 0.3],
        dtype=np.float64,
    )


def predictive_outcome() -> np.ndarray:
    """Return an outcome strongly predicted by the exposure latent variable."""
    index = np.arange(1, N_SUBJECTS + 1, dtype=np.float64)
    epsilon = 0.15 * np.sin(1.7 * index)
    return 40.0 - 8.0 * latent_values() + 0.3 * baseline_values() + epsilon


def nonpredictive_outcome() -> np.ndarray:
    """Return a frozen outcome whose LOOCV exposure model loses to baseline-only."""
    residual = np.array(
        [2, -1, 3, -2, 1, -3, 2, -2, 3, -1, 1, -3, 2, -1, 3, -2],
        dtype=np.float64,
    )
    return 0.6 * baseline_values() + residual


def addon_outcome() -> np.ndarray:
    """Return a deterministic outcome with baseline, delta, and add-on effects."""
    index = np.arange(1, N_SUBJECTS + 1, dtype=np.float64)
    epsilon = 0.1 * np.sin(2.3 * index)
    return (
        0.6 * baseline_values()
        + 4.0 * delta_reference_scores()
        - 8.0 * latent_values()
        + epsilon
    )


def exposure_matrix(kind: str) -> np.ndarray:
    """Return one pre-specified, fallback, or absent exposure matrix."""
    parameters = {
        "pre_specified": (260.0, 20.0),
        "scan_fallback": (190.0, 4.0),
        "absent": (70.0, 0.0),
    }
    if kind not in parameters:
        raise ValueError(f"unknown direct-voxel fixture kind: {kind!r}")
    intercept, slope = parameters[kind]
    subjects = np.arange(1, N_SUBJECTS + 1, dtype=np.float64)[:, None]
    signal_voxels = np.arange(1, N_SIGNAL_VOXELS + 1, dtype=np.float64)[None, :]
    background_voxels = np.arange(
        N_SIGNAL_VOXELS + 1,
        N_VOXELS + 1,
        dtype=np.float64,
    )[None, :]
    loadings = np.linspace(0.8, 1.2, N_SIGNAL_VOXELS, dtype=np.float64)[None, :]
    signal = (
        intercept
        + slope * latent_values()[:, None] * loadings
        + 0.25 * np.sin(subjects * signal_voxels)
    )
    if kind == "absent":
        signal = 70.0 + 5.0 * np.sin(subjects * signal_voxels)
    background = 40.0 + 0.25 * np.sin(subjects * background_voxels)
    exposure = np.column_stack([signal, background]).astype(np.float64, copy=False)
    if exposure.shape != (N_SUBJECTS, N_VOXELS):
        raise AssertionError(f"unexpected fixture shape: {exposure.shape}")
    return exposure


def evaluate_full_grid(
    evaluator: Callable[..., dict[str, Any]],
    *,
    exposure_kind: str,
    outcome: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Evaluate the complete production grid through the supplied production kernel."""
    x = exposure_matrix(exposure_kind)
    y = predictive_outcome() if outcome is None else np.asarray(outcome, dtype=np.float64)
    baseline = baseline_values()
    return [
        evaluator(x, y, baseline, "lower", tau, coverage)
        for tau in TAU_GRID
        for coverage in COVERAGE_GRID
    ]


def synthetic_nifti_data() -> np.ndarray:
    """Return a small positive 4x4x2 image for adapter tests."""
    return np.arange(1, N_VOXELS + 1, dtype=np.float32).reshape((4, 4, 2))


__all__ = [
    "COVERAGE_GRID",
    "N_BACKGROUND_VOXELS",
    "N_SIGNAL_VOXELS",
    "N_SUBJECTS",
    "N_VOXELS",
    "TAU_GRID",
    "addon_outcome",
    "baseline_values",
    "delta_reference_scores",
    "evaluate_full_grid",
    "exposure_matrix",
    "latent_values",
    "nonpredictive_outcome",
    "predictive_outcome",
    "subject_ids",
    "synthetic_nifti_data",
]
