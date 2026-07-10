"""Synthetic fixture builders for seed-target connectivity tests."""

from __future__ import annotations

from pathlib import Path

import h5py
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


def line(*points: tuple[float, float, float]) -> np.ndarray:
    """Build one float32 streamline."""
    return np.asarray(points, dtype=np.float32)


def write_hdf5_connectome(path: Path, streamlines: list[np.ndarray]) -> Path:
    """Write a minimal Lead-DBS MATLAB v7.3-style connectome."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lengths = np.asarray([streamline.shape[0] for streamline in streamlines], dtype=np.float64)
    point_count = int(np.sum(lengths))
    fibers = np.empty((4, point_count), dtype=np.float32)
    cursor = 0
    for fiber_id, streamline in enumerate(streamlines, start=1):
        stop = cursor + streamline.shape[0]
        fibers[0:3, cursor:stop] = np.asarray(streamline, dtype=np.float32).T
        fibers[3, cursor:stop] = float(fiber_id)
        cursor = stop
    with h5py.File(path, "w") as handle:
        handle.create_dataset("idx", data=lengths.reshape(1, -1))
        handle.create_dataset("fibers", data=fibers)
    return path


def mutate_fourth_row(path: Path, value: float, point_index: int = 0) -> None:
    """Replace one stored point-level canonical ID."""
    with h5py.File(path, "r+") as handle:
        handle["fibers"][3, point_index] = value
