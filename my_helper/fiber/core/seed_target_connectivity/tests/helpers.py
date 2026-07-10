"""Synthetic fixture builders for seed-target connectivity tests."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np


def write_mask(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray | None = None,
) -> Path:
    """Write a small NIfTI mask and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_affine = np.eye(4, dtype=np.float64) if affine is None else np.asarray(affine, dtype=np.float64)
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), resolved_affine), str(path))
    return path
