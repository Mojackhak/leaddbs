"""Segment-aware selected-fiber projections for spatial visualization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import nibabel as nib
import numpy as np

from my_helper.fiber.core.seed_target_connectivity.models import (
    FiberChunk,
    ResolvedMask,
)
from my_helper.fiber.core.seed_target_connectivity.traversal import (
    build_sparse_lookup,
    optimized_membership,
)


PROJECTION_ALGORITHM = "segment_aware_selected_fiber_direct_projection"
PROJECTION_VERSION = "2"


@dataclass(frozen=True)
class SelectedDirectProjection:
    """Sparse complete-path projection for the selected fiber library."""

    fiber_ids: np.ndarray
    scores: np.ndarray
    is_sweet: np.ndarray
    voxel_indptr: np.ndarray
    voxel_indices: np.ndarray
    seed_hits: np.ndarray
    direct_voxel_indices: np.ndarray
    direct_score_mean: np.ndarray
    direct_support_count: np.ndarray
    direct_sweet_count: np.ndarray
    direct_sour_count: np.ndarray


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _resolved_mask_hash(mask: np.ndarray, affine: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(mask.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(affine, dtype="<f8").tobytes(order="C"))
    digest.update(
        np.packbits(mask.reshape(-1, order="C"), bitorder="little").tobytes()
    )
    return digest.hexdigest()


def load_binary_projection_mask(
    path: str | Path,
    *,
    roi_id: str,
    role: str,
) -> ResolvedMask:
    """Load one explicit binary mask without atlas discovery or resampling."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"projection mask is missing: {source}")
    image = nib.as_closest_canonical(nib.load(str(source)))
    if len(image.shape) != 3:
        raise ValueError(f"projection mask must be three-dimensional: {source}")
    if tuple(nib.aff2axcodes(image.affine)) != ("R", "A", "S"):
        raise ValueError(f"projection mask must resolve to canonical RAS: {source}")
    data = np.asarray(image.dataobj, dtype=np.float32)
    if not np.all(np.isfinite(data)):
        raise ValueError(f"projection mask contains nonfinite values: {source}")
    nonzero = data[data != 0.0]
    if nonzero.size and not np.all(np.abs(nonzero - 1.0) <= 1e-6):
        raise ValueError(f"projection mask must be binary: {source}")
    resolved = data > 0.0
    flat_indices = np.flatnonzero(resolved.reshape(-1, order="C")).astype(
        np.int64
    )
    if role == "seed" and flat_indices.size == 0:
        raise ValueError(f"projection seed is empty: {source}")
    affine = np.asarray(image.affine, dtype=np.float64)
    voxel_volume = float(abs(np.linalg.det(affine[:3, :3])))
    if not np.isfinite(voxel_volume) or voxel_volume <= 0.0:
        raise ValueError(f"projection mask has invalid voxel volume: {source}")
    flat_indices.setflags(write=False)
    affine.setflags(write=False)
    return ResolvedMask(
        roi_id=str(roi_id),
        role=str(role),
        source_path=source,
        relative_path=source.name,
        target_group="",
        source_value_type="binary",
        probability_threshold=None,
        threshold_source="not_applicable",
        source_hash=_sha256_file(source),
        voxel_count=int(flat_indices.size),
        physical_volume_mm3=float(flat_indices.size) * voxel_volume,
        resolved_mask_hash=_resolved_mask_hash(resolved, affine),
        status="valid" if flat_indices.size else "empty",
        shape=tuple(int(value) for value in image.shape),
        affine=affine,
        flat_voxel_indices=flat_indices,
    )


def validate_exact_mask_geometry(
    seed: ResolvedMask,
    targets: Sequence[ResolvedMask],
) -> None:
    """Require every computational mask to share the exact seed grid."""

    for target in targets:
        if target.shape != seed.shape or not np.array_equal(target.affine, seed.affine):
            raise ValueError(
                f"projection target {target.roi_id!r} does not match the seed grid"
            )


def _clip_segment_to_grid(
    start: np.ndarray,
    stop: np.ndarray,
    shape: np.ndarray,
) -> tuple[bool, float, float]:
    enter = 0.0
    leave = 1.0
    for axis in range(3):
        direction = float(stop[axis] - start[axis])
        lower = 0.0
        upper = float(np.nextafter(float(shape[axis]), -np.inf))
        if direction == 0.0:
            if start[axis] < lower or start[axis] > upper:
                return False, 0.0, 0.0
            continue
        first = (lower - float(start[axis])) / direction
        second = (upper - float(start[axis])) / direction
        if first > second:
            first, second = second, first
        enter = max(enter, first)
        leave = min(leave, second)
        if enter > leave:
            return False, 0.0, 0.0
    if leave < 0.0 or enter > 1.0:
        return False, 0.0, 0.0
    return True, max(0.0, enter), min(1.0, leave)


def _segment_voxels(
    start: np.ndarray,
    stop: np.ndarray,
    shape: np.ndarray,
) -> list[tuple[int, int, int]]:
    intersects, enter, leave = _clip_segment_to_grid(start, stop, shape)
    if not intersects:
        return []
    original_direction = stop - start
    clipped_start = start + original_direction * enter
    clipped_stop = start + original_direction * leave
    direction = clipped_stop - clipped_start
    cell = np.floor(clipped_start).astype(np.int64)
    end_cell = np.floor(clipped_stop).astype(np.int64)
    cell = np.clip(cell, 0, shape - 1)
    end_cell = np.clip(end_cell, 0, shape - 1)
    step = np.zeros(3, dtype=np.int64)
    next_boundary_t = np.full(3, np.inf, dtype=np.float64)
    delta_t = np.full(3, np.inf, dtype=np.float64)
    for axis in range(3):
        if direction[axis] > 0.0:
            step[axis] = 1
            next_boundary_t[axis] = (
                float(cell[axis] + 1) - clipped_start[axis]
            ) / direction[axis]
            delta_t[axis] = 1.0 / direction[axis]
        elif direction[axis] < 0.0:
            step[axis] = -1
            next_boundary_t[axis] = (
                float(cell[axis]) - clipped_start[axis]
            ) / direction[axis]
            delta_t[axis] = -1.0 / direction[axis]

    traversed: list[tuple[int, int, int]] = []
    maximum_steps = int(np.sum(shape, dtype=np.int64) + 3)
    for _ in range(maximum_steps):
        traversed.append((int(cell[0]), int(cell[1]), int(cell[2])))
        if np.array_equal(cell, end_cell):
            break
        minimum_t = float(np.min(next_boundary_t))
        tolerance = 1e-12 * max(1.0, abs(minimum_t))
        for axis in range(3):
            if next_boundary_t[axis] <= minimum_t + tolerance:
                cell[axis] += step[axis]
                next_boundary_t[axis] += delta_t[axis]
        if np.any(cell < 0) or np.any(cell >= shape):
            break
    return traversed


def streamline_flat_voxels(
    streamline: np.ndarray,
    *,
    affine: np.ndarray,
    shape: Sequence[int],
) -> np.ndarray:
    """Return unique C-order voxels crossed by one polyline segment path."""

    points = np.asarray(streamline, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
        raise ValueError("streamline must have shape (n_points >= 2, 3)")
    if not np.all(np.isfinite(points)):
        raise ValueError("streamline coordinates must be finite")
    grid_shape = np.asarray(tuple(int(value) for value in shape), dtype=np.int64)
    if grid_shape.shape != (3,) or np.any(grid_shape <= 0):
        raise ValueError("projection grid shape must contain three positive values")
    inverse_affine = np.linalg.inv(np.asarray(affine, dtype=np.float64))
    voxel_points = nib.affines.apply_affine(inverse_affine, points) + 0.5
    flat_values: list[int] = []
    for index in range(voxel_points.shape[0] - 1):
        for voxel in _segment_voxels(
            voxel_points[index], voxel_points[index + 1], grid_shape
        ):
            flat_values.append(
                int(np.ravel_multi_index(voxel, tuple(grid_shape), order="C"))
            )
    if not flat_values:
        return np.empty(0, dtype=np.int64)
    result = np.unique(np.asarray(flat_values, dtype=np.int64))
    result.setflags(write=False)
    return result


def _fiber_chunk(
    fiber_ids: np.ndarray,
    streamlines: Sequence[np.ndarray],
) -> FiberChunk:
    if len(streamlines) != fiber_ids.size:
        raise ValueError("fiber IDs and streamlines must have equal length")
    lengths = np.asarray([len(value) for value in streamlines], dtype=np.int64)
    if np.any(lengths < 2):
        raise ValueError("every selected streamline must contain at least two points")
    offsets = np.empty(fiber_ids.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])
    points = np.concatenate(
        [np.asarray(value, dtype=np.float32) for value in streamlines], axis=0
    )
    return FiberChunk(
        fiber_ids=np.asarray(fiber_ids, dtype=np.int64),
        point_offsets=offsets,
        points=np.ascontiguousarray(points),
    )


def _validate_selected_fibers(
    fiber_ids: np.ndarray,
    scores: np.ndarray,
    is_sweet: np.ndarray,
    streamlines: Sequence[np.ndarray],
) -> None:
    if fiber_ids.ndim != 1 or fiber_ids.size == 0:
        raise ValueError("selected fiber IDs must be a nonempty vector")
    if np.unique(fiber_ids).size != fiber_ids.size or np.any(fiber_ids < 1):
        raise ValueError("selected fiber IDs must be unique positive integers")
    if scores.shape != fiber_ids.shape or not np.all(np.isfinite(scores)):
        raise ValueError("selected fiber scores must be finite and ID-aligned")
    if is_sweet.shape != fiber_ids.shape or is_sweet.dtype != np.bool_:
        raise ValueError("selected fiber classes must be an ID-aligned boolean vector")
    if len(streamlines) != fiber_ids.size:
        raise ValueError("selected streamline geometry must be ID-aligned")
    if np.any(scores[is_sweet] <= 0.0):
        raise ValueError("every selected sweet fiber must have a positive score")
    if np.any(scores[~is_sweet] >= 0.0):
        raise ValueError("every selected sour fiber must have a negative score")


def compute_selected_direct_projection(
    *,
    fiber_ids: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    is_sweet: Sequence[bool] | np.ndarray,
    streamlines: Sequence[np.ndarray],
    seed: ResolvedMask,
) -> SelectedDirectProjection:
    """Compute the selected library's direct complete-path projection."""

    selected_ids = np.asarray(fiber_ids, dtype=np.int64)
    selected_scores = np.asarray(scores, dtype=np.float64)
    selected_is_sweet = np.asarray(is_sweet, dtype=np.bool_)
    _validate_selected_fibers(
        selected_ids, selected_scores, selected_is_sweet, streamlines
    )
    chunk = _fiber_chunk(selected_ids, streamlines)
    lookup = build_sparse_lookup((seed,))
    seed_hits = np.asarray(optimized_membership(chunk, lookup)[:, 0], dtype=np.bool_)
    if not np.all(seed_hits):
        missing = selected_ids[~seed_hits]
        raise ValueError(
            "selected fibers do not all intersect the configured role seed: "
            + ", ".join(str(int(value)) for value in missing[:10])
        )
    voxel_lists = tuple(
        streamline_flat_voxels(
            streamline,
            affine=seed.affine,
            shape=seed.shape,
        )
        for streamline in streamlines
    )
    voxel_indptr = np.empty(selected_ids.size + 1, dtype=np.int64)
    voxel_indptr[0] = 0
    np.cumsum(
        np.asarray([value.size for value in voxel_lists], dtype=np.int64),
        out=voxel_indptr[1:],
    )
    voxel_indices = (
        np.concatenate(voxel_lists).astype(np.int64, copy=False)
        if voxel_lists
        else np.empty(0, dtype=np.int64)
    )
    if voxel_indices.size == 0:
        raise ValueError("selected streamlines do not intersect the projection grid")

    occurrence_scores = np.concatenate(
        [np.full(values.size, selected_scores[index]) for index, values in enumerate(voxel_lists)]
    )
    occurrence_sweet = np.concatenate(
        [np.full(values.size, selected_is_sweet[index]) for index, values in enumerate(voxel_lists)]
    )
    direct_voxels, direct_inverse = np.unique(
        voxel_indices, return_inverse=True
    )
    direct_support = np.bincount(direct_inverse).astype(np.float64)
    direct_sum = np.bincount(
        direct_inverse, weights=occurrence_scores, minlength=direct_voxels.size
    )
    direct_sweet = np.bincount(
        direct_inverse,
        weights=occurrence_sweet.astype(np.float64),
        minlength=direct_voxels.size,
    )
    direct_sour = direct_support - direct_sweet
    direct_mean = direct_sum / direct_support

    return SelectedDirectProjection(
        fiber_ids=selected_ids,
        scores=selected_scores,
        is_sweet=selected_is_sweet,
        voxel_indptr=voxel_indptr,
        voxel_indices=voxel_indices,
        seed_hits=seed_hits,
        direct_voxel_indices=direct_voxels,
        direct_score_mean=direct_mean,
        direct_support_count=direct_support,
        direct_sweet_count=direct_sweet,
        direct_sour_count=direct_sour,
    )


__all__ = [
    "SelectedDirectProjection",
    "PROJECTION_ALGORITHM",
    "PROJECTION_VERSION",
    "compute_selected_direct_projection",
    "load_binary_projection_mask",
    "streamline_flat_voxels",
    "validate_exact_mask_geometry",
]
