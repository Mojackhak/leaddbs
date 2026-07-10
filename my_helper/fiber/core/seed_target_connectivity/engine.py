"""Chunked whole-connectome membership computation and cache reuse."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .cache import (
    cache_key,
    load_seed_cache,
    load_target_cache,
    seed_cache_identity,
    target_cache_identity,
    write_seed_cache,
    write_target_cache,
)
from .connectome import ConnectomeAdapter
from .errors import MembershipError
from .models import (
    ConnectivityConfig,
    MembershipResult,
    ResolvedAtlas,
    ResolvedMask,
    TargetFiberMembership,
)
from .traversal import build_sparse_lookup, optimized_membership


def _concatenate(parts: list[np.ndarray]) -> np.ndarray:
    values = np.concatenate(parts).astype(np.int64, copy=False) if parts else np.empty(0, dtype=np.int64)
    values.setflags(write=False)
    return values


def _target_membership(target_ids: tuple[str, ...], parts: list[list[np.ndarray]]) -> TargetFiberMembership:
    arrays = [_concatenate(target_parts) for target_parts in parts]
    indptr = np.empty(len(arrays) + 1, dtype=np.int64)
    indptr[0] = 0
    for index, values in enumerate(arrays):
        indptr[index + 1] = indptr[index] + values.size
    fiber_ids = _concatenate(arrays)
    indptr.setflags(write=False)
    return TargetFiberMembership(target_ids=target_ids, indptr=indptr, fiber_ids=fiber_ids)


def compute_memberships(
    connectome: ConnectomeAdapter,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    config: ConnectivityConfig,
    cache_root: Path | str | None = None,
) -> MembershipResult:
    """Compute or reuse independent seed and target whole-connectome membership."""
    metadata = connectome.metadata
    seed_identity = seed_cache_identity(metadata, seed)
    target_identity = target_cache_identity(metadata, atlas)
    seed_key = cache_key(seed_identity)
    target_key = cache_key(target_identity)
    use_cache = config.execution.cache_membership and cache_root is not None
    root = Path(cache_root).expanduser().resolve() if cache_root is not None else None

    loaded_seed = load_seed_cache(root, seed_identity) if use_cache and root is not None else None
    loaded_target = load_target_cache(root, target_identity) if use_cache and root is not None else None
    seed_ids = loaded_seed[0] if loaded_seed is not None else None
    target_membership = loaded_target[0] if loaded_target is not None else None
    expected_target_ids = tuple(target.roi_id for target in atlas.targets)
    if target_membership is not None and target_membership.target_ids != expected_target_ids:
        raise MembershipError("target membership cache order does not match resolved atlas order")

    if seed_ids is None or target_membership is None:
        seed_lookup = build_sparse_lookup([seed]) if seed_ids is None else None
        target_lookup = build_sparse_lookup(atlas.targets) if target_membership is None else None
        seed_parts: list[np.ndarray] = []
        target_parts: list[list[np.ndarray]] = [list() for _ in atlas.targets]
        seen_fibers = 0
        ordered_id_digest = hashlib.sha256()
        for chunk in connectome.iter_chunks(config.execution.fiber_chunk_size):
            chunk_ids = np.asarray(chunk.fiber_ids, dtype=np.int64)
            if chunk_ids.ndim != 1 or chunk_ids.size == 0 or np.unique(chunk_ids).size != chunk_ids.size:
                raise MembershipError("connectome adapter yielded duplicate or invalid canonical fiber IDs")
            ordered_id_digest.update(np.asarray(chunk_ids, dtype="<i8").tobytes())
            seen_fibers += int(chunk_ids.size)
            if seed_lookup is not None:
                seed_hits = optimized_membership(chunk, seed_lookup)[:, 0]
                if np.any(seed_hits):
                    seed_parts.append(chunk_ids[seed_hits].copy())
            if target_lookup is not None:
                target_hits = optimized_membership(chunk, target_lookup)
                for target_index in range(len(atlas.targets)):
                    hits = target_hits[:, target_index]
                    if np.any(hits):
                        target_parts[target_index].append(chunk_ids[hits].copy())
        if seen_fibers != metadata.n_fibers:
            raise MembershipError(
                f"connectome adapter yielded {seen_fibers} fibers but metadata declares {metadata.n_fibers}"
            )
        if ordered_id_digest.hexdigest() != metadata.ordered_fiber_id_hash:
            raise MembershipError("yielded canonical fiber ID order does not match connectome metadata")
        if seed_ids is None:
            seed_ids = _concatenate(seed_parts)
        if target_membership is None:
            target_membership = _target_membership(expected_target_ids, target_parts)

    if seed_ids.size == 0:
        raise MembershipError("seed ROI has no connectome fiber support")
    seed_path = loaded_seed[1] if loaded_seed is not None else None
    target_path = loaded_target[1] if loaded_target is not None else None
    if use_cache and root is not None:
        if seed_path is None:
            seed_path = write_seed_cache(root, seed_identity, seed_ids)
        if target_path is None:
            target_path = write_target_cache(root, target_identity, target_membership)
    return MembershipResult(
        n_all_fibers=metadata.n_fibers,
        seed_fiber_ids=seed_ids,
        target_membership=target_membership,
        seed_cache_key=seed_key,
        target_cache_key=target_key,
        seed_cache_hit=loaded_seed is not None,
        target_cache_hit=loaded_target is not None,
        seed_cache_path=seed_path,
        target_cache_path=target_path,
    )
