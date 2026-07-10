"""Reference and optimized segment-aware voxel traversal kernels."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numba import njit

from .errors import TraversalError
from .models import FiberChunk, ResolvedMask


TRAVERSAL_ALGORITHM = "segment_aware_voxel_traversal"
TRAVERSAL_VERSION = "1"


@dataclass(frozen=True)
class SparseVoxelGroup:
    """Sparse occupied-voxel lookup for masks on one exact grid."""

    shape: np.ndarray
    inverse_affine: np.ndarray
    voxel_keys: np.ndarray
    voxel_target_bits: np.ndarray
    full_target_bits: np.ndarray


@dataclass(frozen=True)
class SparseVoxelLookup:
    """Ordered target identities and one or more exact-grid sparse lookups."""

    target_ids: tuple[str, ...]
    groups: tuple[SparseVoxelGroup, ...]
    target_count: int
    word_count: int
    algorithm: str = TRAVERSAL_ALGORITHM
    version: str = TRAVERSAL_VERSION


def _geometry_key(mask: ResolvedMask) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(mask.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(mask.affine, dtype="<f8").tobytes(order="C"))
    return digest.hexdigest()


def build_sparse_lookup(masks: Sequence[ResolvedMask]) -> SparseVoxelLookup:
    """Combine ordered masks into sparse bitsets grouped by exact grid geometry."""
    if not masks:
        raise TraversalError("at least one resolved mask is required")
    target_count = len(masks)
    word_count = (target_count + 63) // 64
    grouped: dict[str, list[tuple[int, ResolvedMask]]] = {}
    for target_index, mask in enumerate(masks):
        if len(mask.shape) != 3 or any(int(size) <= 0 for size in mask.shape):
            raise TraversalError(f"mask {mask.roi_id!r} has invalid shape {mask.shape}")
        maximum_key = int(np.prod(mask.shape, dtype=np.int64))
        keys = np.asarray(mask.flat_voxel_indices, dtype=np.int64)
        if keys.ndim != 1 or np.any(keys < 0) or np.any(keys >= maximum_key):
            raise TraversalError(f"mask {mask.roi_id!r} has invalid flat voxel indices")
        if keys.size and np.any(keys[1:] <= keys[:-1]):
            raise TraversalError(f"mask {mask.roi_id!r} voxel indices must be unique and sorted")
        if keys.size:
            grouped.setdefault(_geometry_key(mask), []).append((target_index, mask))

    groups: list[SparseVoxelGroup] = []
    for geometry_key in sorted(grouped):
        entries = grouped[geometry_key]
        all_keys = np.concatenate(
            [np.asarray(mask.flat_voxel_indices, dtype=np.int64) for _, mask in entries]
        )
        voxel_keys = np.unique(all_keys)
        voxel_bits = np.zeros((voxel_keys.size, word_count), dtype=np.uint64)
        for target_index, mask in entries:
            positions = np.searchsorted(voxel_keys, mask.flat_voxel_indices)
            word_index = target_index // 64
            bit = np.uint64(1) << np.uint64(target_index % 64)
            voxel_bits[positions, word_index] |= bit
        full_bits = np.bitwise_or.reduce(voxel_bits, axis=0)
        shape = np.asarray(entries[0][1].shape, dtype=np.int64)
        try:
            inverse_affine = np.linalg.inv(np.asarray(entries[0][1].affine, dtype=np.float64))
        except np.linalg.LinAlgError as exc:
            raise TraversalError(f"mask grid {geometry_key} has a singular affine") from exc
        for array in (voxel_keys, voxel_bits, full_bits, shape, inverse_affine):
            array.setflags(write=False)
        groups.append(
            SparseVoxelGroup(
                shape=shape,
                inverse_affine=inverse_affine,
                voxel_keys=voxel_keys,
                voxel_target_bits=voxel_bits,
                full_target_bits=full_bits,
            )
        )
    return SparseVoxelLookup(
        target_ids=tuple(mask.roi_id for mask in masks),
        groups=tuple(groups),
        target_count=target_count,
        word_count=word_count,
    )


def _segment_intersects_half_open_voxel(
    start: np.ndarray,
    stop: np.ndarray,
    voxel: np.ndarray,
) -> bool:
    lower = voxel.astype(np.float64) - 0.5
    upper = np.nextafter(voxel.astype(np.float64) + 0.5, -np.inf)
    direction = stop - start
    enter = 0.0
    leave = 1.0
    for axis in range(3):
        if direction[axis] == 0.0:
            if start[axis] < lower[axis] or start[axis] > upper[axis]:
                return False
            continue
        first = (lower[axis] - start[axis]) / direction[axis]
        second = (upper[axis] - start[axis]) / direction[axis]
        if first > second:
            first, second = second, first
        enter = max(enter, first)
        leave = min(leave, second)
        if enter > leave:
            return False
    return leave >= 0.0 and enter <= 1.0


def reference_membership(
    streamlines: Sequence[np.ndarray],
    masks: Sequence[ResolvedMask],
) -> np.ndarray:
    """Compute membership with an intentionally slow independent slab kernel."""
    result = np.zeros((len(streamlines), len(masks)), dtype=bool)
    for mask_index, mask in enumerate(masks):
        if mask.flat_voxel_indices.size == 0:
            continue
        inverse_affine = np.linalg.inv(np.asarray(mask.affine, dtype=np.float64))
        occupied = np.column_stack(
            np.unravel_index(mask.flat_voxel_indices, mask.shape, order="C")
        ).astype(np.float64)
        for fiber_index, streamline in enumerate(streamlines):
            points = np.asarray(streamline, dtype=np.float64)
            if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
                raise TraversalError("each reference streamline must have shape (n_points >= 2, 3)")
            voxel_points = points @ inverse_affine[:3, :3].T + inverse_affine[:3, 3]
            hit = False
            for segment_index in range(voxel_points.shape[0] - 1):
                start = voxel_points[segment_index]
                stop = voxel_points[segment_index + 1]
                for voxel in occupied:
                    if _segment_intersects_half_open_voxel(start, stop, voxel):
                        hit = True
                        break
                if hit:
                    break
            result[fiber_index, mask_index] = hit
    return result


@njit(cache=True)
def _binary_search(keys: np.ndarray, value: int) -> int:
    left = 0
    right = keys.size
    while left < right:
        middle = (left + right) // 2
        candidate = keys[middle]
        if candidate < value:
            left = middle + 1
        else:
            right = middle
    if left < keys.size and keys[left] == value:
        return left
    return -1


@njit(cache=True)
def _transform_point(point: np.ndarray, inverse_affine: np.ndarray) -> np.ndarray:
    transformed = np.empty(3, dtype=np.float64)
    for axis in range(3):
        transformed[axis] = (
            inverse_affine[axis, 0] * point[0]
            + inverse_affine[axis, 1] * point[1]
            + inverse_affine[axis, 2] * point[2]
            + inverse_affine[axis, 3]
            + 0.5
        )
    return transformed


@njit(cache=True)
def _clip_segment_to_grid(
    start: np.ndarray,
    stop: np.ndarray,
    shape: np.ndarray,
) -> tuple[bool, float, float]:
    enter = 0.0
    leave = 1.0
    for axis in range(3):
        direction = stop[axis] - start[axis]
        lower = 0.0
        upper = np.nextafter(float(shape[axis]), -np.inf)
        if direction == 0.0:
            if start[axis] < lower or start[axis] > upper:
                return False, 0.0, 0.0
            continue
        first = (lower - start[axis]) / direction
        second = (upper - start[axis]) / direction
        if first > second:
            temporary = first
            first = second
            second = temporary
        if first > enter:
            enter = first
        if second < leave:
            leave = second
        if enter > leave:
            return False, 0.0, 0.0
    if leave < 0.0 or enter > 1.0:
        return False, 0.0, 0.0
    if enter < 0.0:
        enter = 0.0
    if leave > 1.0:
        leave = 1.0
    return True, enter, leave


@njit(cache=True)
def _all_group_targets_found(row: np.ndarray, full_bits: np.ndarray) -> bool:
    for word_index in range(full_bits.size):
        if (row[word_index] & full_bits[word_index]) != full_bits[word_index]:
            return False
    return True


@njit(cache=True)
def _traverse_group(
    points: np.ndarray,
    point_offsets: np.ndarray,
    inverse_affine: np.ndarray,
    shape: np.ndarray,
    voxel_keys: np.ndarray,
    voxel_bits: np.ndarray,
    full_bits: np.ndarray,
    output_words: np.ndarray,
) -> None:
    for fiber_index in range(point_offsets.size - 1):
        point_start = point_offsets[fiber_index]
        point_stop = point_offsets[fiber_index + 1]
        for point_index in range(point_start, point_stop - 1):
            start = _transform_point(points[point_index], inverse_affine)
            stop = _transform_point(points[point_index + 1], inverse_affine)
            intersects, enter, leave = _clip_segment_to_grid(start, stop, shape)
            if not intersects:
                continue
            original_direction = stop - start
            clipped_start = start + original_direction * enter
            clipped_stop = start + original_direction * leave
            direction = clipped_stop - clipped_start
            cell = np.empty(3, dtype=np.int64)
            end_cell = np.empty(3, dtype=np.int64)
            step = np.zeros(3, dtype=np.int64)
            next_boundary_t = np.empty(3, dtype=np.float64)
            delta_t = np.empty(3, dtype=np.float64)
            for axis in range(3):
                cell[axis] = int(np.floor(clipped_start[axis]))
                end_cell[axis] = int(np.floor(clipped_stop[axis]))
                if cell[axis] < 0:
                    cell[axis] = 0
                elif cell[axis] >= shape[axis]:
                    cell[axis] = shape[axis] - 1
                if end_cell[axis] < 0:
                    end_cell[axis] = 0
                elif end_cell[axis] >= shape[axis]:
                    end_cell[axis] = shape[axis] - 1
                if direction[axis] > 0.0:
                    step[axis] = 1
                    next_boundary_t[axis] = (float(cell[axis] + 1) - clipped_start[axis]) / direction[axis]
                    delta_t[axis] = 1.0 / direction[axis]
                elif direction[axis] < 0.0:
                    step[axis] = -1
                    next_boundary_t[axis] = (float(cell[axis]) - clipped_start[axis]) / direction[axis]
                    delta_t[axis] = -1.0 / direction[axis]
                else:
                    next_boundary_t[axis] = np.inf
                    delta_t[axis] = np.inf

            maximum_steps = int(shape[0] + shape[1] + shape[2] + 3)
            for _ in range(maximum_steps):
                flat_key = (cell[0] * shape[1] + cell[1]) * shape[2] + cell[2]
                key_index = _binary_search(voxel_keys, flat_key)
                if key_index >= 0:
                    for word_index in range(output_words.shape[1]):
                        output_words[fiber_index, word_index] |= voxel_bits[key_index, word_index]
                    if _all_group_targets_found(output_words[fiber_index], full_bits):
                        break
                if (
                    cell[0] == end_cell[0]
                    and cell[1] == end_cell[1]
                    and cell[2] == end_cell[2]
                ):
                    break
                minimum_t = min(next_boundary_t[0], next_boundary_t[1], next_boundary_t[2])
                tolerance = 1e-12 * max(1.0, abs(minimum_t))
                for axis in range(3):
                    if next_boundary_t[axis] <= minimum_t + tolerance:
                        cell[axis] += step[axis]
                        next_boundary_t[axis] += delta_t[axis]
            if _all_group_targets_found(output_words[fiber_index], full_bits):
                break


def optimized_membership(chunk: FiberChunk, lookup: SparseVoxelLookup) -> np.ndarray:
    """Compute independent mask membership with sparse Numba 3D DDA traversal."""
    points = np.asarray(chunk.points, dtype=np.float32)
    offsets = np.asarray(chunk.point_offsets, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise TraversalError("chunk points must have shape (n_points, 3)")
    if offsets.ndim != 1 or offsets.size != chunk.fiber_ids.size + 1:
        raise TraversalError("chunk point offsets must have one boundary per fiber")
    if offsets[0] != 0 or offsets[-1] != points.shape[0] or np.any(offsets[1:] - offsets[:-1] < 2):
        raise TraversalError("chunk point offsets do not define valid streamlines")
    output_words = np.zeros((chunk.fiber_ids.size, lookup.word_count), dtype=np.uint64)
    for group in lookup.groups:
        _traverse_group(
            points,
            offsets,
            group.inverse_affine,
            group.shape,
            group.voxel_keys,
            group.voxel_target_bits,
            group.full_target_bits,
            output_words,
        )
    result = np.zeros((chunk.fiber_ids.size, lookup.target_count), dtype=bool)
    for target_index in range(lookup.target_count):
        word_index = target_index // 64
        bit = np.uint64(1) << np.uint64(target_index % 64)
        result[:, target_index] = (output_words[:, word_index] & bit) != 0
    return result
