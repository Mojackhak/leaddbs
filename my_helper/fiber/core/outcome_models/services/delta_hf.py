"""Shared DeltaHFScore support classification and sidecar helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DeltaHFSupportAssessment:
    status: str
    cohort_median: float
    subject_fraction_over_0_50: float
    subject_fraction_over_0_80: float
    maximum_required_fraction: float

    @property
    def valid(self) -> bool:
        return self.status in {"adequate", "limited"}


def _fractions(values: tuple[float, ...], label: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{label} must contain at least one fraction")
    if not np.all(np.isfinite(array)) or np.any(array < 0.0) or np.any(array > 1.0):
        raise ValueError(f"{label} must contain finite fractions in [0, 1]")
    return array


def classify_delta_hf_support(
    *,
    subject_out_fractions: tuple[float, ...],
    fold_out_fractions: tuple[float, ...],
    any_zero_total: bool,
    zero_status: str,
) -> DeltaHFSupportAssessment:
    """Apply the locked adequate/limited/invalid support thresholds."""
    subjects = _fractions(subject_out_fractions, "subject_out_fractions")
    folds = _fractions(fold_out_fractions, "fold_out_fractions")
    if not zero_status.startswith("invalid_no_hfcomponent_"):
        raise ValueError("zero_status must identify the model-specific no-HF-component failure")
    median = float(np.median(subjects))
    over_50 = float(np.mean(subjects > 0.50))
    over_80 = float(np.mean(subjects > 0.80))
    maximum = float(max(np.max(subjects), np.max(folds)))
    if any_zero_total:
        status = zero_status
    elif median > 0.50 or over_80 > 0.25 or maximum > 0.95:
        status = "invalid_extreme_out_of_support"
    elif median <= 0.20 and over_50 <= 0.25:
        status = "adequate"
    else:
        status = "limited"
    return DeltaHFSupportAssessment(
        status=status,
        cohort_median=median,
        subject_fraction_over_0_50=over_50,
        subject_fraction_over_0_80=over_80,
        maximum_required_fraction=maximum,
    )


__all__ = ["DeltaHFSupportAssessment", "classify_delta_hf_support"]
