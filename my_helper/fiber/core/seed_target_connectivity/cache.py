"""Independent content-addressed seed and target membership caches."""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .errors import CacheError
from .identity import canonical_hash, sha256_file
from .models import (
    ConnectomeMetadata,
    ResolvedAtlas,
    ResolvedMask,
    TargetFiberMembership,
)
from .traversal import TRAVERSAL_ALGORITHM, TRAVERSAL_VERSION


def seed_cache_identity(metadata: ConnectomeMetadata, seed: ResolvedMask) -> dict[str, Any]:
    """Return the exact reusable seed-membership identity."""
    return {
        "cache_kind": "seed_membership",
        "connectome_geometry_identity": metadata.geometry_hash,
        "ordered_canonical_fiber_id_identity": metadata.ordered_fiber_id_hash,
        "seed_resolved_mask_identity": seed.resolved_mask_hash,
        "intersection_algorithm": TRAVERSAL_ALGORITHM,
        "intersection_algorithm_version": TRAVERSAL_VERSION,
    }


def target_cache_identity(metadata: ConnectomeMetadata, atlas: ResolvedAtlas) -> dict[str, Any]:
    """Return the exact reusable target-membership identity."""
    return {
        "cache_kind": "target_membership",
        "connectome_geometry_identity": metadata.geometry_hash,
        "ordered_canonical_fiber_id_identity": metadata.ordered_fiber_id_hash,
        "target_atlas_resolved_mask_identity": atlas.atlas_hash,
        "intersection_algorithm": TRAVERSAL_ALGORITHM,
        "intersection_algorithm_version": TRAVERSAL_VERSION,
    }


def cache_key(identity: Mapping[str, Any]) -> str:
    """Return one content-addressed membership cache key."""
    return canonical_hash(dict(identity))


def seed_cache_path(root: Path, key: str) -> Path:
    return root / "seed_membership" / key / "seed_connected_fiber_ids.npy"


def target_cache_path(root: Path, key: str) -> Path:
    return root / "target_membership" / key / "target_fiber_membership.npz"


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _manifest_path(artifact_path: Path) -> Path:
    return artifact_path.parent / "cache_manifest.json"


def _write_manifest(artifact_path: Path, identity: Mapping[str, Any], key: str) -> None:
    manifest = {
        "schema_version": 1,
        "cache_key": key,
        "identity": dict(identity),
        "artifact": artifact_path.name,
        "artifact_sha256": sha256_file(artifact_path),
    }
    payload = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    _atomic_write(_manifest_path(artifact_path), payload)


def _validate_manifest(artifact_path: Path, identity: Mapping[str, Any], key: str) -> None:
    manifest_path = _manifest_path(artifact_path)
    if not manifest_path.is_file() or not artifact_path.is_file():
        raise CacheError(f"membership cache is incomplete: {artifact_path.parent}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CacheError(f"failed to read membership cache manifest {manifest_path}: {exc}") from exc
    if manifest.get("cache_key") != key or manifest.get("identity") != dict(identity):
        raise CacheError(f"membership cache identity mismatch: {artifact_path.parent}")
    expected_hash = manifest.get("artifact_sha256")
    actual_hash = sha256_file(artifact_path)
    if expected_hash != actual_hash:
        raise CacheError(
            f"membership cache artifact hash mismatch for {artifact_path}: expected {expected_hash}, got {actual_hash}"
        )


def load_seed_cache(
    root: Path,
    identity: Mapping[str, Any],
) -> tuple[np.ndarray, Path] | None:
    """Load and verify an exact seed cache, returning `None` when absent."""
    key = cache_key(identity)
    path = seed_cache_path(root, key)
    if not path.parent.exists():
        return None
    _validate_manifest(path, identity, key)
    try:
        values = np.asarray(np.load(path, allow_pickle=False), dtype=np.int64)
    except Exception as exc:
        raise CacheError(f"failed to load seed membership cache {path}: {exc}") from exc
    if values.ndim != 1 or np.unique(values).size != values.size:
        raise CacheError(f"seed membership cache IDs are not unique: {path}")
    values.setflags(write=False)
    return values, path


def write_seed_cache(
    root: Path,
    identity: Mapping[str, Any],
    fiber_ids: np.ndarray,
) -> Path:
    """Write one exact seed cache atomically."""
    key = cache_key(identity)
    path = seed_cache_path(root, key)
    if path.parent.exists():
        loaded = load_seed_cache(root, identity)
        if loaded is None:
            raise CacheError(f"seed cache directory exists without a valid artifact: {path.parent}")
        return loaded[1]
    output = io.BytesIO()
    np.save(output, np.asarray(fiber_ids, dtype=np.int64), allow_pickle=False)
    _atomic_write(path, output.getvalue())
    _write_manifest(path, identity, key)
    return path


def load_target_cache(
    root: Path,
    identity: Mapping[str, Any],
) -> tuple[TargetFiberMembership, Path] | None:
    """Load and verify an exact target cache, returning `None` when absent."""
    key = cache_key(identity)
    path = target_cache_path(root, key)
    if not path.parent.exists():
        return None
    _validate_manifest(path, identity, key)
    try:
        with np.load(path, allow_pickle=False) as archive:
            target_ids = tuple(str(value) for value in archive["target_ids"].tolist())
            indptr = np.asarray(archive["indptr"], dtype=np.int64)
            fiber_ids = np.asarray(archive["fiber_ids"], dtype=np.int64)
    except Exception as exc:
        raise CacheError(f"failed to load target membership cache {path}: {exc}") from exc
    if indptr.ndim != 1 or indptr.size != len(target_ids) + 1 or indptr[0] != 0 or indptr[-1] != fiber_ids.size:
        raise CacheError(f"target membership cache has invalid indptr: {path}")
    if np.any(indptr[1:] < indptr[:-1]):
        raise CacheError(f"target membership cache indptr is not monotonic: {path}")
    for index in range(len(target_ids)):
        values = fiber_ids[indptr[index] : indptr[index + 1]]
        if np.unique(values).size != values.size:
            raise CacheError(f"target membership cache IDs are not unique: {path}")
    indptr.setflags(write=False)
    fiber_ids.setflags(write=False)
    return TargetFiberMembership(target_ids=target_ids, indptr=indptr, fiber_ids=fiber_ids), path


def write_target_cache(
    root: Path,
    identity: Mapping[str, Any],
    membership: TargetFiberMembership,
) -> Path:
    """Write one exact target cache atomically."""
    key = cache_key(identity)
    path = target_cache_path(root, key)
    if path.parent.exists():
        loaded = load_target_cache(root, identity)
        if loaded is None:
            raise CacheError(f"target cache directory exists without a valid artifact: {path.parent}")
        return loaded[1]
    output = io.BytesIO()
    maximum_length = max((len(value) for value in membership.target_ids), default=1)
    np.savez_compressed(
        output,
        target_ids=np.asarray(membership.target_ids, dtype=f"<U{maximum_length}"),
        indptr=np.asarray(membership.indptr, dtype=np.int64),
        fiber_ids=np.asarray(membership.fiber_ids, dtype=np.int64),
    )
    _atomic_write(path, output.getvalue())
    _write_manifest(path, identity, key)
    return path
