"""Whole-connectome seed-voxel target-pattern composition."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
from numba import njit

from my_helper.fiber.core.seed_target_connectivity.connectome import (
    ConnectomeAdapter,
)
from my_helper.fiber.core.seed_target_connectivity.models import (
    FiberChunk,
    ResolvedMask,
)
from my_helper.fiber.core.seed_target_connectivity.traversal import (
    build_sparse_lookup,
    optimized_membership,
)


COMPOSITION_ALGORITHM = "whole_connectome_seed_voxel_target_patterns"
COMPOSITION_VERSION = "2"


@dataclass(frozen=True)
class SeedPatternCounts:
    """Sparse target-membership pattern counts for one role seed."""

    role: str
    seed_voxel_indices: np.ndarray
    voxel_pattern_indptr: np.ndarray
    pattern_bits: np.ndarray
    pattern_counts: np.ndarray


@dataclass(frozen=True)
class WholeConnectomeComposition:
    """Model-independent physical composition for both role seeds."""

    target_ids: tuple[str, ...]
    n_all_fibers: int
    fiber_target_bits: np.ndarray
    roles: tuple[SeedPatternCounts, ...]
    fiber_chunk_size: int
    ordered_fiber_id_hash: str

    def for_role(self, role: str) -> SeedPatternCounts:
        """Return the unique seed composition for one model role."""

        matches = [value for value in self.roles if value.role == role]
        if len(matches) != 1:
            raise KeyError(f"whole-connectome composition lacks unique role {role!r}")
        return matches[0]


@dataclass(frozen=True)
class TargetConditionedProjection:
    """Endpoint-specific score projected through physical pattern counts."""

    seed_voxel_indices: np.ndarray
    target_conditioned_score: np.ndarray
    all_streamline_support_count: np.ndarray
    target_scored_streamline_count: np.ndarray
    target_unscored_streamline_count: np.ndarray
    target_assignment_fraction: np.ndarray
    finite_target_count: int
    scored_pattern_count: int
    unscored_pattern_count: int


@dataclass(frozen=True)
class _SeedTraversalGrid:
    seed_voxel_indices: np.ndarray
    inverse_affine: np.ndarray
    lower_bound: np.ndarray
    upper_bound: np.ndarray
    crop_shape: np.ndarray
    compact_index: np.ndarray


def _seed_grid(seed: ResolvedMask) -> _SeedTraversalGrid:
    indices = np.asarray(seed.flat_voxel_indices, dtype=np.int64)
    if indices.size == 0:
        raise ValueError(f"composition seed {seed.roi_id!r} is empty")
    coordinates = np.asarray(
        np.unravel_index(indices, seed.shape, order="C"), dtype=np.int64
    ).T
    lower = np.min(coordinates, axis=0)
    upper = np.max(coordinates, axis=0) + 1
    crop_shape = upper - lower
    compact = np.full(int(np.prod(crop_shape, dtype=np.int64)), -1, dtype=np.int32)
    local = coordinates - lower
    local_flat = np.ravel_multi_index(local.T, tuple(crop_shape), order="C")
    compact[local_flat] = np.arange(indices.size, dtype=np.int32)
    inverse_affine = np.linalg.inv(np.asarray(seed.affine, dtype=np.float64))
    for value in (indices, inverse_affine, lower, upper, crop_shape, compact):
        value.setflags(write=False)
    return _SeedTraversalGrid(
        seed_voxel_indices=indices,
        inverse_affine=inverse_affine,
        lower_bound=lower,
        upper_bound=upper,
        crop_shape=crop_shape,
        compact_index=compact,
    )


@njit(cache=True, nogil=True)
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


@njit(cache=True, nogil=True)
def _clip_segment(
    start: np.ndarray,
    stop: np.ndarray,
    lower_bound: np.ndarray,
    upper_bound: np.ndarray,
) -> tuple[bool, float, float]:
    enter = 0.0
    leave = 1.0
    for axis in range(3):
        direction = stop[axis] - start[axis]
        lower = float(lower_bound[axis])
        upper = np.nextafter(float(upper_bound[axis]), -np.inf)
        if direction == 0.0:
            if start[axis] < lower or start[axis] > upper:
                return False, 0.0, 0.0
            continue
        first = (lower - start[axis]) / direction
        second = (upper - start[axis]) / direction
        if first > second:
            first, second = second, first
        if first > enter:
            enter = first
        if second < leave:
            leave = second
        if enter > leave:
            return False, 0.0, 0.0
    if leave < 0.0 or enter > 1.0:
        return False, 0.0, 0.0
    return True, max(0.0, enter), min(1.0, leave)


@njit(cache=True, nogil=True)
def _seed_incidence_counts(
    points: np.ndarray,
    offsets: np.ndarray,
    inverse_affine: np.ndarray,
    lower_bound: np.ndarray,
    upper_bound: np.ndarray,
    crop_shape: np.ndarray,
    compact_index: np.ndarray,
    seed_voxel_count: int,
) -> np.ndarray:
    counts = np.zeros(offsets.size - 1, dtype=np.int64)
    last_seen = np.full(seed_voxel_count, -1, dtype=np.int64)
    maximum_steps = int(np.sum(upper_bound - lower_bound) + 3)
    for fiber_index in range(offsets.size - 1):
        for point_index in range(offsets[fiber_index], offsets[fiber_index + 1] - 1):
            start = _transform_point(points[point_index], inverse_affine)
            stop = _transform_point(points[point_index + 1], inverse_affine)
            intersects, enter, leave = _clip_segment(
                start, stop, lower_bound, upper_bound
            )
            if not intersects:
                continue
            original_direction = stop - start
            clipped_start = start + original_direction * enter
            clipped_stop = start + original_direction * leave
            direction = clipped_stop - clipped_start
            cell = np.floor(clipped_start).astype(np.int64)
            end_cell = np.floor(clipped_stop).astype(np.int64)
            step = np.zeros(3, dtype=np.int64)
            next_boundary = np.full(3, np.inf, dtype=np.float64)
            delta = np.full(3, np.inf, dtype=np.float64)
            for axis in range(3):
                cell[axis] = min(max(cell[axis], lower_bound[axis]), upper_bound[axis] - 1)
                end_cell[axis] = min(
                    max(end_cell[axis], lower_bound[axis]), upper_bound[axis] - 1
                )
                if direction[axis] > 0.0:
                    step[axis] = 1
                    next_boundary[axis] = (
                        float(cell[axis] + 1) - clipped_start[axis]
                    ) / direction[axis]
                    delta[axis] = 1.0 / direction[axis]
                elif direction[axis] < 0.0:
                    step[axis] = -1
                    next_boundary[axis] = (
                        float(cell[axis]) - clipped_start[axis]
                    ) / direction[axis]
                    delta[axis] = -1.0 / direction[axis]
            for _ in range(maximum_steps):
                local_x = cell[0] - lower_bound[0]
                local_y = cell[1] - lower_bound[1]
                local_z = cell[2] - lower_bound[2]
                local_flat = (
                    (local_x * crop_shape[1] + local_y) * crop_shape[2] + local_z
                )
                seed_index = int(compact_index[local_flat])
                if seed_index >= 0 and last_seen[seed_index] != fiber_index:
                    last_seen[seed_index] = fiber_index
                    counts[fiber_index] += 1
                if (
                    cell[0] == end_cell[0]
                    and cell[1] == end_cell[1]
                    and cell[2] == end_cell[2]
                ):
                    break
                minimum_t = min(next_boundary[0], next_boundary[1], next_boundary[2])
                tolerance = 1e-12 * max(1.0, abs(minimum_t))
                for axis in range(3):
                    if next_boundary[axis] <= minimum_t + tolerance:
                        cell[axis] += step[axis]
                        next_boundary[axis] += delta[axis]
    return counts


@njit(cache=True, nogil=True)
def _seed_incidence_fill(
    points: np.ndarray,
    offsets: np.ndarray,
    inverse_affine: np.ndarray,
    lower_bound: np.ndarray,
    upper_bound: np.ndarray,
    crop_shape: np.ndarray,
    compact_index: np.ndarray,
    indptr: np.ndarray,
    seed_voxel_count: int,
) -> np.ndarray:
    indices = np.empty(indptr[-1], dtype=np.int32)
    write_positions = indptr[:-1].copy()
    last_seen = np.full(seed_voxel_count, -1, dtype=np.int64)
    maximum_steps = int(np.sum(upper_bound - lower_bound) + 3)
    for fiber_index in range(offsets.size - 1):
        for point_index in range(offsets[fiber_index], offsets[fiber_index + 1] - 1):
            start = _transform_point(points[point_index], inverse_affine)
            stop = _transform_point(points[point_index + 1], inverse_affine)
            intersects, enter, leave = _clip_segment(
                start, stop, lower_bound, upper_bound
            )
            if not intersects:
                continue
            original_direction = stop - start
            clipped_start = start + original_direction * enter
            clipped_stop = start + original_direction * leave
            direction = clipped_stop - clipped_start
            cell = np.floor(clipped_start).astype(np.int64)
            end_cell = np.floor(clipped_stop).astype(np.int64)
            step = np.zeros(3, dtype=np.int64)
            next_boundary = np.full(3, np.inf, dtype=np.float64)
            delta = np.full(3, np.inf, dtype=np.float64)
            for axis in range(3):
                cell[axis] = min(max(cell[axis], lower_bound[axis]), upper_bound[axis] - 1)
                end_cell[axis] = min(
                    max(end_cell[axis], lower_bound[axis]), upper_bound[axis] - 1
                )
                if direction[axis] > 0.0:
                    step[axis] = 1
                    next_boundary[axis] = (
                        float(cell[axis] + 1) - clipped_start[axis]
                    ) / direction[axis]
                    delta[axis] = 1.0 / direction[axis]
                elif direction[axis] < 0.0:
                    step[axis] = -1
                    next_boundary[axis] = (
                        float(cell[axis]) - clipped_start[axis]
                    ) / direction[axis]
                    delta[axis] = -1.0 / direction[axis]
            for _ in range(maximum_steps):
                local_x = cell[0] - lower_bound[0]
                local_y = cell[1] - lower_bound[1]
                local_z = cell[2] - lower_bound[2]
                local_flat = (
                    (local_x * crop_shape[1] + local_y) * crop_shape[2] + local_z
                )
                seed_index = int(compact_index[local_flat])
                if seed_index >= 0 and last_seen[seed_index] != fiber_index:
                    last_seen[seed_index] = fiber_index
                    position = write_positions[fiber_index]
                    indices[position] = seed_index
                    write_positions[fiber_index] += 1
                if (
                    cell[0] == end_cell[0]
                    and cell[1] == end_cell[1]
                    and cell[2] == end_cell[2]
                ):
                    break
                minimum_t = min(next_boundary[0], next_boundary[1], next_boundary[2])
                tolerance = 1e-12 * max(1.0, abs(minimum_t))
                for axis in range(3):
                    if next_boundary[axis] <= minimum_t + tolerance:
                        cell[axis] += step[axis]
                        next_boundary[axis] += delta[axis]
    return indices


def _seed_voxel_incidence_grid(
    chunk: FiberChunk,
    grid: _SeedTraversalGrid,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(chunk.points, dtype=np.float32)
    offsets = np.asarray(chunk.point_offsets, dtype=np.int64)
    counts = _seed_incidence_counts(
        points,
        offsets,
        grid.inverse_affine,
        grid.lower_bound,
        grid.upper_bound,
        grid.crop_shape,
        grid.compact_index,
        grid.seed_voxel_indices.size,
    )
    indptr = np.empty(counts.size + 1, dtype=np.int64)
    indptr[0] = 0
    np.cumsum(counts, out=indptr[1:])
    indices = _seed_incidence_fill(
        points,
        offsets,
        grid.inverse_affine,
        grid.lower_bound,
        grid.upper_bound,
        grid.crop_shape,
        grid.compact_index,
        indptr,
        grid.seed_voxel_indices.size,
    )
    indptr.setflags(write=False)
    indices.setflags(write=False)
    return indptr, indices


def seed_voxel_incidence(
    chunk: FiberChunk,
    seed: ResolvedMask,
) -> tuple[np.ndarray, np.ndarray]:
    """Return compact seed-voxel CSR incidence for one fiber chunk."""

    return _seed_voxel_incidence_grid(chunk, _seed_grid(seed))


def _membership_bits(membership: np.ndarray) -> np.ndarray:
    if membership.ndim != 2 or membership.shape[1] > 32:
        raise ValueError("target membership must have at most 32 targets")
    bits = np.zeros(membership.shape[0], dtype=np.uint32)
    for target_index in range(membership.shape[1]):
        bits |= membership[:, target_index].astype(np.uint32) << np.uint32(
            target_index
        )
    return bits


def _chunk_pattern_counts(
    indptr: np.ndarray,
    seed_indices: np.ndarray,
    fiber_patterns: np.ndarray,
    target_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    repetitions = np.diff(indptr)
    if int(np.sum(repetitions, dtype=np.int64)) != seed_indices.size:
        raise ValueError("seed incidence CSR is inconsistent")
    if seed_indices.size == 0:
        return np.empty(0, dtype=np.uint64), np.empty(0, dtype=np.int64)
    patterns = np.repeat(fiber_patterns, repetitions).astype(np.uint64, copy=False)
    codes = (seed_indices.astype(np.uint64) << np.uint64(target_count)) | patterns
    unique_codes, counts = np.unique(codes, return_counts=True)
    return unique_codes, counts.astype(np.int64, copy=False)


def _merge_pattern_parts(
    *,
    role: str,
    seed: ResolvedMask,
    target_count: int,
    code_parts: Sequence[np.ndarray],
    count_parts: Sequence[np.ndarray],
) -> SeedPatternCounts:
    if code_parts:
        codes = np.concatenate(code_parts)
        counts = np.concatenate(count_parts)
        order = np.argsort(codes, kind="stable")
        codes = codes[order]
        counts = counts[order]
        starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
        merged_codes = codes[starts]
        merged_counts = np.add.reduceat(counts, starts).astype(np.int64, copy=False)
    else:
        merged_codes = np.empty(0, dtype=np.uint64)
        merged_counts = np.empty(0, dtype=np.int64)
    voxel_positions = (merged_codes >> np.uint64(target_count)).astype(
        np.int64, copy=False
    )
    pattern_mask = np.uint64((1 << target_count) - 1)
    patterns = (merged_codes & pattern_mask).astype(np.uint32, copy=False)
    entry_counts = np.bincount(
        voxel_positions, minlength=seed.flat_voxel_indices.size
    ).astype(np.int64, copy=False)
    indptr = np.empty(entry_counts.size + 1, dtype=np.int64)
    indptr[0] = 0
    np.cumsum(entry_counts, out=indptr[1:])
    seed_indices = np.asarray(seed.flat_voxel_indices, dtype=np.int64)
    for value in (seed_indices, indptr, patterns, merged_counts):
        value.setflags(write=False)
    return SeedPatternCounts(
        role=role,
        seed_voxel_indices=seed_indices,
        voxel_pattern_indptr=indptr,
        pattern_bits=patterns,
        pattern_counts=merged_counts,
    )


def build_whole_connectome_composition(
    *,
    connectome: ConnectomeAdapter,
    seeds: Mapping[str, ResolvedMask],
    targets: Sequence[ResolvedMask],
    fiber_chunk_size: int,
    progress_callback: Callable[[Mapping[str, int]], None] | None = None,
) -> WholeConnectomeComposition:
    """Scan the formal connectome once and aggregate both role seeds."""

    if not isinstance(fiber_chunk_size, int) or isinstance(fiber_chunk_size, bool):
        raise ValueError("fiber_chunk_size must be an integer")
    if fiber_chunk_size <= 0:
        raise ValueError("fiber_chunk_size must be positive")
    if not seeds:
        raise ValueError("at least one role seed is required")
    if not targets or len(targets) > 32:
        raise ValueError("whole-connectome composition requires 1 to 32 targets")
    target_lookup = build_sparse_lookup(targets)
    role_order = tuple(sorted(str(role) for role in seeds))
    seed_grids = {role: _seed_grid(seeds[role]) for role in role_order}
    code_parts: dict[str, list[np.ndarray]] = {role: [] for role in role_order}
    count_parts: dict[str, list[np.ndarray]] = {role: [] for role in role_order}
    metadata = connectome.metadata
    fiber_bits = np.zeros(metadata.n_fibers, dtype=np.uint32)
    seen_fibers = 0
    ordered_digest = hashlib.sha256()
    for chunk in connectome.iter_chunks(fiber_chunk_size):
        chunk_ids = np.asarray(chunk.fiber_ids, dtype=np.int64)
        if chunk_ids.size == 0 or np.any(chunk_ids != np.arange(
            seen_fibers + 1, seen_fibers + chunk_ids.size + 1, dtype=np.int64
        )):
            raise ValueError("formal connectome chunks must use contiguous canonical IDs")
        ordered_digest.update(np.asarray(chunk_ids, dtype="<i8").tobytes())
        membership = optimized_membership(chunk, target_lookup)
        patterns = _membership_bits(membership)
        fiber_bits[chunk_ids - 1] = patterns
        role_incidence: dict[str, int] = {}
        for role in role_order:
            indptr, seed_indices = _seed_voxel_incidence_grid(
                chunk, seed_grids[role]
            )
            role_incidence[role] = int(seed_indices.size)
            codes, counts = _chunk_pattern_counts(
                indptr,
                seed_indices,
                patterns,
                len(targets),
            )
            if codes.size:
                code_parts[role].append(codes)
                count_parts[role].append(counts)
        seen_fibers += int(chunk_ids.size)
        if progress_callback is not None:
            progress_callback(
                {
                    "seen_fibers": seen_fibers,
                    "n_all_fibers": metadata.n_fibers,
                    **{
                        f"{role}_chunk_incidence": role_incidence[role]
                        for role in role_order
                    },
                }
            )
    if seen_fibers != metadata.n_fibers:
        raise ValueError(
            f"formal connectome yielded {seen_fibers} fibers; expected {metadata.n_fibers}"
        )
    ordered_hash = ordered_digest.hexdigest()
    if ordered_hash != metadata.ordered_fiber_id_hash:
        raise ValueError("formal connectome canonical fiber order changed during scan")
    roles = tuple(
        _merge_pattern_parts(
            role=role,
            seed=seeds[role],
            target_count=len(targets),
            code_parts=code_parts[role],
            count_parts=count_parts[role],
        )
        for role in role_order
    )
    fiber_bits.setflags(write=False)
    return WholeConnectomeComposition(
        target_ids=tuple(target.roi_id for target in targets),
        n_all_fibers=metadata.n_fibers,
        fiber_target_bits=fiber_bits,
        roles=roles,
        fiber_chunk_size=fiber_chunk_size,
        ordered_fiber_id_hash=ordered_hash,
    )


def target_membership_from_bits(
    fiber_target_bits: np.ndarray,
    fiber_ids: Sequence[int] | np.ndarray,
    target_count: int,
) -> np.ndarray:
    """Resolve selected-fiber binary target membership from physical bits."""

    ids = np.asarray(fiber_ids, dtype=np.int64)
    bits = np.asarray(fiber_target_bits, dtype=np.uint32)
    if ids.ndim != 1 or np.any(ids < 1) or np.any(ids > bits.size):
        raise ValueError("selected canonical fiber ID is outside physical cache")
    membership = np.zeros((ids.size, target_count), dtype=np.bool_)
    selected_bits = bits[ids - 1]
    for target_index in range(target_count):
        membership[:, target_index] = (
            selected_bits & (np.uint32(1) << np.uint32(target_index))
        ) != 0
    return membership


def compute_target_scores(
    *,
    fiber_scores: Sequence[float] | np.ndarray,
    target_membership: np.ndarray,
) -> np.ndarray:
    """Compute target scores from an aligned scored-fiber axis."""

    scores = np.asarray(fiber_scores, dtype=np.float64)
    membership = np.asarray(target_membership, dtype=np.bool_)
    if membership.ndim != 2 or scores.shape != (membership.shape[0],):
        raise ValueError("fiber scores and target membership are not aligned")
    if not np.all(np.isfinite(scores)):
        raise ValueError("target-score inputs must be finite")
    denominator = np.sum(membership, axis=0, dtype=np.float64)
    numerator = membership.astype(np.float64).T @ scores
    target_scores = np.full(membership.shape[1], np.nan, dtype=np.float64)
    available = denominator > 0.0
    target_scores[available] = numerator[available] / denominator[available]
    return target_scores


def compute_selected_target_scores(
    *,
    selected_scores: Sequence[float] | np.ndarray,
    target_membership: np.ndarray,
) -> np.ndarray:
    """Compute selected-library target scores with uniform streamline weight."""

    return compute_target_scores(
        fiber_scores=selected_scores,
        target_membership=target_membership,
    )


def _pattern_scores(
    patterns: np.ndarray,
    target_scores: np.ndarray,
) -> tuple[np.ndarray, int, int]:
    unique_patterns, inverse = np.unique(patterns, return_inverse=True)
    scores = np.full(unique_patterns.size, np.nan, dtype=np.float64)
    finite_targets = np.isfinite(target_scores)
    for index, pattern in enumerate(unique_patterns):
        active = np.asarray(
            [
                bool(pattern & (np.uint32(1) << np.uint32(target_index)))
                for target_index in range(target_scores.size)
            ],
            dtype=np.bool_,
        )
        active &= finite_targets
        if np.any(active):
            scores[index] = float(np.mean(target_scores[active]))
    expanded = scores[inverse]
    return expanded, int(np.sum(np.isfinite(scores))), int(np.sum(~np.isfinite(scores)))


def apply_target_scores_to_composition(
    *,
    composition: SeedPatternCounts,
    target_scores: Sequence[float] | np.ndarray,
) -> TargetConditionedProjection:
    """Apply endpoint target scores to cached all-connectome composition."""

    scores = np.asarray(target_scores, dtype=np.float64)
    if scores.ndim != 1 or scores.size > 32:
        raise ValueError("target scores must be a vector with at most 32 values")
    entry_scores, scored_patterns, unscored_patterns = _pattern_scores(
        composition.pattern_bits, scores
    )
    n_voxels = composition.seed_voxel_indices.size
    total = np.zeros(n_voxels, dtype=np.float64)
    scored = np.zeros(n_voxels, dtype=np.float64)
    weighted = np.zeros(n_voxels, dtype=np.float64)
    for voxel_index in range(n_voxels):
        start = int(composition.voxel_pattern_indptr[voxel_index])
        stop = int(composition.voxel_pattern_indptr[voxel_index + 1])
        counts = composition.pattern_counts[start:stop].astype(np.float64, copy=False)
        values = entry_scores[start:stop]
        total[voxel_index] = float(np.sum(counts))
        finite = np.isfinite(values)
        if np.any(finite):
            scored[voxel_index] = float(np.sum(counts[finite]))
            weighted[voxel_index] = float(np.sum(counts[finite] * values[finite]))
    unscored = total - scored
    target_conditioned = np.full(n_voxels, np.nan, dtype=np.float64)
    has_scored = scored > 0.0
    target_conditioned[has_scored] = weighted[has_scored] / scored[has_scored]
    assignment = np.full(n_voxels, np.nan, dtype=np.float64)
    has_total = total > 0.0
    assignment[has_total] = scored[has_total] / total[has_total]
    return TargetConditionedProjection(
        seed_voxel_indices=composition.seed_voxel_indices,
        target_conditioned_score=target_conditioned,
        all_streamline_support_count=total,
        target_scored_streamline_count=scored,
        target_unscored_streamline_count=unscored,
        target_assignment_fraction=assignment,
        finite_target_count=int(np.sum(np.isfinite(scores))),
        scored_pattern_count=scored_patterns,
        unscored_pattern_count=unscored_patterns,
    )


__all__ = [
    "COMPOSITION_ALGORITHM",
    "COMPOSITION_VERSION",
    "SeedPatternCounts",
    "TargetConditionedProjection",
    "WholeConnectomeComposition",
    "apply_target_scores_to_composition",
    "build_whole_connectome_composition",
    "compute_selected_target_scores",
    "compute_target_scores",
    "seed_voxel_incidence",
    "target_membership_from_bits",
]
