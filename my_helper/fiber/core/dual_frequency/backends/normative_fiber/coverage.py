"""Chunked tau/Coverage operations for normative-fiber exposure matrices."""

from __future__ import annotations

import math

import numpy as np


class FiberCoverageError(ValueError):
    """Raised when normative-fiber coverage inputs violate the contract."""


def _exposure_matrix(value: np.ndarray) -> np.ndarray:
    array = np.asanyarray(value)
    if array.ndim != 2 or not all(dimension > 0 for dimension in array.shape):
        raise FiberCoverageError("exposure must be a nonempty subject-by-fiber matrix")
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise FiberCoverageError("exposure must contain numeric values")
    if np.iscomplexobj(array):
        raise FiberCoverageError("exposure must contain real values")
    return array


def _tau(value: float) -> float:
    tau = float(value)
    if not math.isfinite(tau) or tau <= 0:
        raise FiberCoverageError("tau must be finite and positive")
    return tau


def _coverage(value: int) -> int:
    if type(value) is not int or value < 1:
        raise FiberCoverageError("coverage must be a positive integer")
    return value


def _chunk_size(value: int) -> int:
    if type(value) is not int or value < 1:
        raise FiberCoverageError("chunk_size must be a positive integer")
    return value


def coverage_counts(
    exposure: np.ndarray,
    tau: float,
    *,
    chunk_size: int = 262_144,
) -> np.ndarray:
    """Count subjects with exposure strictly greater than tau for each fiber."""

    matrix = _exposure_matrix(exposure)
    threshold = _tau(tau)
    step = _chunk_size(chunk_size)
    counts = np.empty(matrix.shape[1], dtype=np.int32)
    for start in range(0, matrix.shape[1], step):
        stop = min(start + step, matrix.shape[1])
        block = np.asarray(matrix[:, start:stop])
        if not np.all(np.isfinite(block)):
            raise FiberCoverageError("exposure must contain only finite values")
        counts[start:stop] = np.count_nonzero(block > threshold, axis=0)
    counts.flags.writeable = False
    return counts


def candidate_mask(counts: np.ndarray, coverage: int) -> np.ndarray:
    """Return the fibers whose subject coverage reaches the requested minimum."""

    values = np.asarray(counts)
    minimum = _coverage(coverage)
    if values.ndim != 1 or values.dtype == object or not np.issubdtype(
        values.dtype, np.integer
    ):
        raise FiberCoverageError("counts must be a one-dimensional integer array")
    if np.any(values < 0):
        raise FiberCoverageError("counts cannot be negative")
    mask = np.asarray(values > minimum, dtype=bool)
    mask.flags.writeable = False
    return mask


def heldout_fold_candidate_mask(
    exposure: np.ndarray,
    full_counts: np.ndarray,
    heldout_index: int,
    tau: float,
    coverage: int,
    *,
    chunk_size: int = 262_144,
) -> np.ndarray:
    """Derive one training-fold mask without retaining all fold masks in memory."""

    matrix = _exposure_matrix(exposure)
    counts = np.asarray(full_counts)
    threshold = _tau(tau)
    minimum = _coverage(coverage)
    step = _chunk_size(chunk_size)
    if type(heldout_index) is not int or not 0 <= heldout_index < matrix.shape[0]:
        raise FiberCoverageError("heldout_index is outside the subject axis")
    if counts.ndim != 1 or counts.shape[0] != matrix.shape[1] or not np.issubdtype(
        counts.dtype, np.integer
    ):
        raise FiberCoverageError("full_counts must match the fiber axis")
    if np.any(counts < 0) or np.any(counts > matrix.shape[0]):
        raise FiberCoverageError("full_counts are incompatible with the subject axis")

    mask = np.empty(matrix.shape[1], dtype=bool)
    for start in range(0, matrix.shape[1], step):
        stop = min(start + step, matrix.shape[1])
        heldout = np.asarray(matrix[heldout_index, start:stop])
        if not np.all(np.isfinite(heldout)):
            raise FiberCoverageError("exposure must contain only finite values")
        training_counts = counts[start:stop] - (heldout > threshold)
        mask[start:stop] = training_counts > minimum
    mask.flags.writeable = False
    return mask
