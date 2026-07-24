"""Atomic scientific-cache publication and strict array materialization."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from threading import RLock
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

import numpy as np

from ..contracts.records import ArtifactRef, AxisRef, IndexedArrayView
from ..instrumentation import increment_performance_event
from .identity import CacheIdentityError, ScientificCacheKey, sha256_file, sha256_stream


MANIFEST_NAME = "manifest.json"


class CacheError(RuntimeError):
    """Base error for cache publication and materialization failures."""


class CacheIdentityMismatch(CacheError):
    """Raised when an occupied cache identity contains different content."""


class CacheCorruption(CacheIdentityMismatch):
    """Raised when persisted cache content does not match its manifest."""


class ArtifactValidationError(CacheError):
    """Raised when an artifact is unsafe or violates expected array semantics."""


class ArtifactPublicationError(CacheError):
    """Raised when a run-scoped artifact cannot be published without overwrite."""


class IndexedArrayReader:
    """Context-managed, byte-bounded reader for one verified indexed view."""

    def __init__(
        self,
        parent: np.ndarray,
        row_positions: np.ndarray | None,
        column_positions: np.ndarray | None,
        *,
        logical_shape: tuple[int, int],
        max_block_bytes: int,
    ) -> None:
        self._parent = parent
        self._row_positions = row_positions
        self._column_positions = column_positions
        self.shape = logical_shape
        self.ndim = 2
        self.dtype = parent.dtype
        self.max_block_bytes = max_block_bytes
        self._closed = False

    @staticmethod
    def _logical_positions(
        key: object,
        size: int,
        role: str,
    ) -> tuple[slice | np.ndarray, int, bool]:
        if type(key) is int:
            index = int(key)
            if index < 0:
                index += size
            if index < 0 or index >= size:
                raise IndexError(f"{role} index is outside the logical axis")
            return np.asarray([index], dtype=np.int64), 1, True
        if isinstance(key, slice):
            start, stop, step = key.indices(size)
            if step != 1:
                raise ArtifactValidationError(
                    f"{role} slice must use a positive unit step"
                )
            return slice(start, stop), max(0, stop - start), False
        values = np.asarray(key)
        if values.ndim != 1 or values.dtype == np.dtype(bool) or not np.issubdtype(
            values.dtype,
            np.integer,
        ):
            raise ArtifactValidationError(
                f"{role} selector must be an integer, unit-step slice, "
                "or one-dimensional integer positions"
            )
        indices = np.asarray(values, dtype=np.int64)
        if indices.size and (
            int(indices.min()) < -size or int(indices.max()) >= size
        ):
            raise IndexError(f"{role} positions exceed the logical axis")
        indices = np.where(indices < 0, indices + size, indices).astype(
            np.int64,
            copy=False,
        )
        return indices, int(indices.size), False

    @staticmethod
    def _parent_selector(
        logical: slice | np.ndarray,
        persisted: np.ndarray | None,
    ) -> slice | np.ndarray:
        if persisted is None:
            return logical
        return persisted[logical]

    def __getitem__(self, key: object) -> np.ndarray:
        if self._closed:
            raise ArtifactValidationError("IndexedArrayReader is closed")
        if not isinstance(key, tuple) or len(key) != 2:
            raise ArtifactValidationError(
                "IndexedArrayReader requires explicit two-dimensional indexing"
            )
        logical_rows, row_count, row_scalar = self._logical_positions(
            key[0],
            self.shape[0],
            "row",
        )
        logical_columns, column_count, column_scalar = self._logical_positions(
            key[1],
            self.shape[1],
            "column",
        )
        requested_bytes = row_count * column_count * self.dtype.itemsize
        if requested_bytes > self.max_block_bytes:
            raise ArtifactValidationError(
                "IndexedArrayReader request exceeds its block byte budget"
            )
        rows = self._parent_selector(logical_rows, self._row_positions)
        columns = self._parent_selector(logical_columns, self._column_positions)
        if isinstance(rows, slice) and isinstance(columns, slice):
            selected = self._parent[rows, columns]
        elif isinstance(rows, slice):
            selected = self._parent[rows, columns]
        elif isinstance(columns, slice):
            selected = self._parent[rows, columns]
        else:
            selected = self._parent[np.ix_(rows, columns)]
        block = np.array(selected, dtype=self.dtype, copy=True)
        if row_scalar:
            block = block[0]
        if column_scalar:
            block = block[..., 0]
        block.flags.writeable = False
        return block

    def __array__(
        self,
        dtype: np.dtype | None = None,
        copy: bool | None = None,
    ) -> np.ndarray:
        del dtype, copy
        raise ArtifactValidationError(
            "IndexedArrayReader forbids implicit NumPy materialization"
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        mmap = getattr(self._parent, "_mmap", None)
        close = getattr(mmap, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "IndexedArrayReader":
        if self._closed:
            raise ArtifactValidationError("IndexedArrayReader is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise CacheIdentityMismatch(f"{field} must be nonempty")
    return token


def _sha256(value: str, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CacheIdentityMismatch(f"{field} must be a 64-character SHA-256 digest")
    return digest


def _relative_path(value: str) -> str:
    text = _token(value, "cache relative path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or text != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CacheIdentityMismatch(f"unsafe cache relative path {value!r}")
    if path.as_posix() == MANIFEST_NAME:
        raise CacheIdentityMismatch(f"{MANIFEST_NAME} is reserved")
    return path.as_posix()


def _is_platform_sidecar(path: Path) -> bool:
    """Return whether a descendant is macOS AppleDouble filesystem metadata."""

    return any(part.startswith("._") for part in path.parts)


@dataclass(frozen=True, order=True, slots=True)
class CacheItem:
    """One stable item identity inside an ordered cache axis."""

    item_id: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _token(self.item_id, "item_id"))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "item sha256"))

    def as_dict(self) -> dict[str, str]:
        return {"item_id": self.item_id, "sha256": self.sha256}


@dataclass(frozen=True, order=True, slots=True)
class CacheShardInterval:
    """One half-open interval in a complete ordered shard set."""

    set_id: str
    axis_id: str
    start: int
    stop: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_id", _token(self.set_id, "shard set_id"))
        object.__setattr__(self, "axis_id", _token(self.axis_id, "shard axis_id"))
        object.__setattr__(self, "start", int(self.start))
        object.__setattr__(self, "stop", int(self.stop))
        if self.start < 0 or self.stop <= self.start:
            raise CacheIdentityMismatch("shard interval must be nonempty and nonnegative")

    def as_dict(self) -> dict[str, object]:
        return {
            "set_id": self.set_id,
            "axis_id": self.axis_id,
            "start": self.start,
            "stop": self.stop,
        }


@dataclass(frozen=True, order=True, slots=True)
class CacheFileMetadata:
    """Portable structural metadata for one cached payload."""

    dtype: str | None = None
    shape: tuple[int, ...] | None = None
    axes: tuple[AxisRef, ...] = ()
    units: str | None = None
    space: str | None = None
    shard_interval: CacheShardInterval | None = None

    def __post_init__(self) -> None:
        axes = tuple(self.axes)
        if not all(isinstance(axis, AxisRef) for axis in axes):
            raise CacheIdentityMismatch("cache file axes must contain only AxisRef values")
        object.__setattr__(self, "axes", axes)
        if self.dtype is None:
            if self.shape is not None or axes or self.units is not None or self.space is not None:
                raise CacheIdentityMismatch(
                    "non-array cache files cannot declare array metadata"
                )
            if self.shard_interval is not None:
                raise CacheIdentityMismatch("non-array cache files cannot be shards")
            return
        try:
            object.__setattr__(self, "dtype", np.dtype(self.dtype).name)
        except TypeError as exc:
            raise CacheIdentityMismatch("cache file dtype is invalid") from exc
        if np.dtype(self.dtype) == np.dtype(object):
            raise CacheIdentityMismatch("object arrays are forbidden in the cache")
        if self.shape is None:
            raise CacheIdentityMismatch("array cache files require shape")
        shape = tuple(int(value) for value in self.shape)
        if not shape or any(value < 1 for value in shape):
            raise CacheIdentityMismatch("array cache file shape must be nonempty and positive")
        object.__setattr__(self, "shape", shape)
        if len(axes) != len(shape):
            raise CacheIdentityMismatch("array cache file axes must match shape rank")
        interval = self.shard_interval
        if interval is not None and not isinstance(interval, CacheShardInterval):
            raise CacheIdentityMismatch("shard_interval must be a CacheShardInterval")
        shard_matches = 0
        for dimension, axis in zip(shape, axes, strict=True):
            if interval is not None and axis.axis_id == interval.axis_id:
                shard_matches += 1
                if dimension != interval.stop - interval.start or interval.stop > axis.count:
                    raise CacheIdentityMismatch("shard interval does not match array metadata")
            elif dimension != axis.count:
                raise CacheIdentityMismatch("array shape does not match ordered axes")
        if interval is not None and shard_matches != 1:
            raise CacheIdentityMismatch("shard axis must occur exactly once in ordered axes")
        object.__setattr__(
            self,
            "units",
            None if self.units is None else _token(self.units, "cache file units"),
        )
        object.__setattr__(
            self,
            "space",
            None if self.space is None else _token(self.space, "cache file space"),
        )

    @property
    def is_array(self) -> bool:
        return self.dtype is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "dtype": self.dtype,
            "shape": None if self.shape is None else list(self.shape),
            "axes": [
                {"axis_id": axis.axis_id, "count": axis.count, "sha256": axis.sha256}
                for axis in self.axes
            ],
            "units": self.units,
            "space": self.space,
            "shard_interval": (
                None if self.shard_interval is None else self.shard_interval.as_dict()
            ),
        }


@dataclass(frozen=True, order=True, slots=True)
class CachedFile:
    """One file covered by a complete cache manifest."""

    relative_path: str
    sha256: str
    size_bytes: int
    metadata: CacheFileMetadata = CacheFileMetadata()

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _relative_path(self.relative_path))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "file sha256"))
        object.__setattr__(self, "size_bytes", int(self.size_bytes))
        if self.size_bytes < 0:
            raise CacheIdentityMismatch("file size_bytes must be nonnegative")
        if not isinstance(self.metadata, CacheFileMetadata):
            raise CacheIdentityMismatch("file metadata must be CacheFileMetadata")

    def as_dict(self) -> dict[str, object]:
        payload = {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }
        payload.update(self.metadata.as_dict())
        return payload


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Validated cache entry returned by publication or lookup."""

    path: Path
    key: ScientificCacheKey
    files: tuple[CachedFile, ...]
    items: tuple[CacheItem, ...]
    reused: bool

    @property
    def manifest_path(self) -> Path:
        return self.path / MANIFEST_NAME

    def file_path(self, relative_path: str) -> Path:
        normalized = _relative_path(relative_path)
        if normalized not in {item.relative_path for item in self.files}:
            raise KeyError(normalized)
        return self.path / normalized


@dataclass(frozen=True, slots=True)
class ReindexedView:
    """A deterministic reordering over an otherwise identical item axis."""

    scientific_identity: str
    source_items: tuple[CacheItem, ...]
    view_items: tuple[CacheItem, ...]
    source_indices: tuple[int, ...]

    def as_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "scientific_cache_reindexed_view_v1",
            "scientific_identity": self.scientific_identity,
            "source_items": [item.as_dict() for item in self.source_items],
            "view_items": [item.as_dict() for item in self.view_items],
            "source_indices": list(self.source_indices),
        }


def _cache_items(values: Sequence[CacheItem | tuple[str, str]]) -> tuple[CacheItem, ...]:
    items = tuple(value if isinstance(value, CacheItem) else CacheItem(*value) for value in values)
    identifiers = tuple(item.item_id for item in items)
    if len(set(identifiers)) != len(identifiers):
        raise CacheIdentityMismatch("cache item IDs must be unique")
    return items


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class ContentAddressedCache:
    """Publish and validate immutable cache entries by scientific identity."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise CacheError(f"cache root is not a directory: {self.root}")
        self._verified_entries: set[tuple[str, str]] = set()

    def entry_path(self, key: ScientificCacheKey) -> Path:
        if not isinstance(key, ScientificCacheKey):
            raise TypeError("key must be a ScientificCacheKey")
        kind = _relative_path(key.kind)
        if "/" in kind:
            raise CacheIdentityMismatch("cache kind must be one path component")
        return self.root / "shared_exposure_v2" / kind / key.digest

    def publish(
        self,
        key: ScientificCacheKey,
        files: Mapping[str, str | Path],
        *,
        items: Sequence[CacheItem | tuple[str, str]] = (),
        metadata: Mapping[str, CacheFileMetadata] | None = None,
    ) -> CacheEntry:
        """Atomically publish files while hashing the final bytes during the write."""

        if not isinstance(key, ScientificCacheKey):
            raise TypeError("key must be a ScientificCacheKey")
        if not isinstance(files, Mapping) or not files:
            raise CacheIdentityMismatch("files must be a nonempty relative-path mapping")
        normalized_sources: dict[str, Path] = {}
        for relative_path, source in files.items():
            normalized = _relative_path(relative_path)
            if normalized in normalized_sources:
                raise CacheIdentityMismatch("cache file paths must be unique")
            source_path = Path(source).expanduser().resolve()
            if not source_path.is_file():
                raise CacheIdentityMismatch(f"cache source is not a file: {source_path}")
            normalized_sources[normalized] = source_path
        normalized_items = _cache_items(items)
        normalized_metadata = self._normalize_metadata(normalized_sources, metadata)

        destination = self.entry_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{key.digest}.tmp-", dir=destination.parent)
        )
        try:
            cached_files: list[CachedFile] = []
            for relative_path, source in sorted(normalized_sources.items()):
                target = staging / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size_bytes = self._copy_and_hash(source, target)
                cached_files.append(
                    CachedFile(
                        relative_path,
                        digest,
                        size_bytes,
                        normalized_metadata[relative_path],
                    )
                )
            expected_files = tuple(cached_files)
            for record in expected_files:
                self._validate_file_structure(staging / record.relative_path, record)
            self._validate_shards(expected_files)
            payload = self._manifest_payload(key, expected_files, normalized_items)
            _write_json(staging / MANIFEST_NAME, payload)

            if destination.exists():
                existing = self._load_entry(destination, expected_key=key, reused=True)
                self._require_exact_publication(existing, expected_files, normalized_items)
                return existing

            try:
                os.replace(staging, destination)
            except OSError:
                if not destination.exists():
                    raise
                existing = self._load_entry(destination, expected_key=key, reused=True)
                self._require_exact_publication(existing, expected_files, normalized_items)
                return existing
            return self._load_entry(
                destination,
                expected_key=key,
                reused=False,
                trust_publisher_payloads=True,
            )
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def publish_generated(
        self,
        key: ScientificCacheKey,
        producer: Callable[[Path], Sequence[CachedFile]],
        *,
        items: Sequence[CacheItem | tuple[str, str]] = (),
    ) -> CacheEntry:
        """Atomically publish payloads written and hashed once by a trusted producer."""

        if not isinstance(key, ScientificCacheKey):
            raise TypeError("key must be a ScientificCacheKey")
        if not callable(producer):
            raise TypeError("producer must be callable")
        normalized_items = _cache_items(items)
        destination = self.entry_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return self._load_entry(destination, expected_key=key, reused=True)

        staging = Path(
            tempfile.mkdtemp(prefix=f".{key.digest}.tmp-", dir=destination.parent)
        )
        try:
            generated = tuple(producer(staging))
            if not generated or not all(
                isinstance(record, CachedFile) for record in generated
            ):
                raise CacheIdentityMismatch(
                    "generated cache producer must return CachedFile records"
                )
            expected_files = tuple(
                sorted(generated, key=lambda record: record.relative_path)
            )
            if expected_files != generated:
                raise CacheIdentityMismatch(
                    "generated cache files must be returned in path order"
                )
            names = tuple(record.relative_path for record in expected_files)
            if len(set(names)) != len(names):
                raise CacheIdentityMismatch(
                    "generated cache file paths must be unique"
                )
            descendants = tuple(staging.rglob("*"))
            if any(path.is_symlink() for path in descendants):
                raise CacheIdentityMismatch(
                    "generated cache payloads cannot contain symbolic links"
                )
            actual = {
                path.relative_to(staging).as_posix()
                for path in descendants
                if path.is_file()
                and not _is_platform_sidecar(path.relative_to(staging))
            }
            if actual != set(names):
                raise CacheIdentityMismatch(
                    "generated cache file records do not cover the staging generation"
                )
            for record in expected_files:
                path = staging / record.relative_path
                if path.stat().st_size != record.size_bytes:
                    raise CacheIdentityMismatch(
                        f"generated cache size changed: {record.relative_path}"
                    )
                self._validate_file_structure(path, record)
            self._validate_shards(expected_files)
            _write_json(
                staging / MANIFEST_NAME,
                self._manifest_payload(key, expected_files, normalized_items),
            )

            if destination.exists():
                existing = self._load_entry(
                    destination,
                    expected_key=key,
                    reused=True,
                )
                self._require_exact_publication(
                    existing,
                    expected_files,
                    normalized_items,
                )
                return existing
            try:
                os.replace(staging, destination)
            except OSError:
                if not destination.exists():
                    raise
                existing = self._load_entry(
                    destination,
                    expected_key=key,
                    reused=True,
                )
                self._require_exact_publication(
                    existing,
                    expected_files,
                    normalized_items,
                )
                return existing
            return self._load_entry(
                destination,
                expected_key=key,
                reused=False,
                trust_publisher_payloads=True,
            )
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def resolve(self, key: ScientificCacheKey) -> CacheEntry | None:
        """Return a validated cache entry, or None when it is absent."""

        destination = self.entry_path(key)
        if not destination.exists():
            return None
        return self._load_entry(destination, expected_key=key, reused=True)

    def resolve_identity(self, kind: str, semantic_sha256: str) -> CacheEntry | None:
        """Validate a directly copied entry from only its portable identity."""

        normalized_kind = _relative_path(kind)
        if "/" in normalized_kind:
            raise CacheIdentityMismatch("cache kind must be one path component")
        digest = _sha256(semantic_sha256, "semantic_sha256")
        destination = self.root / "shared_exposure_v2" / normalized_kind / digest
        if not destination.exists():
            return None
        manifest_path = destination / MANIFEST_NAME
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            key = ScientificCacheKey.from_dict(payload["scientific_cache_key"])
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, CacheIdentityError) as exc:
            raise CacheCorruption(f"cache manifest identity is unreadable: {manifest_path}") from exc
        if key.kind != normalized_kind or key.digest != digest:
            raise CacheIdentityMismatch("copied cache directory identity does not match manifest")
        verified_key = (key.kind, key.digest)
        required_full_verification = verified_key not in self._verified_entries
        entry = self._load_entry(destination, expected_key=key, reused=True)
        if required_full_verification:
            increment_performance_event(
                "direct_copy_verification",
                key=f"{key.kind}:{key.digest}",
            )
        return entry

    @contextmanager
    def producer_lease(
        self,
        key: ScientificCacheKey,
        *,
        timeout_seconds: float = 600.0,
    ):
        """Serialize one cache miss across processes without hiding corrupt entries."""

        if not isinstance(key, ScientificCacheKey):
            raise TypeError("key must be a ScientificCacheKey")
        destination = self.entry_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = destination.parent / f".{key.digest}.produce.lock"
        deadline = time.monotonic() + float(timeout_seconds)
        owned = False
        while True:
            if destination.exists():
                yield False
                return
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if self._quarantine_stale_lock(lock):
                    continue
                if self._producer_is_alive(lock) is True:
                    deadline = time.monotonic() + float(timeout_seconds)
                if time.monotonic() > deadline:
                    raise CacheError(f"timed out waiting for cache producer lease: {lock}")
                time.sleep(0.05)
                continue
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(f"pid={os.getpid()}\n")
                stream.flush()
                os.fsync(stream.fileno())
            owned = True
            break
        try:
            yield True
        finally:
            if owned:
                lock.unlink(missing_ok=True)

    @staticmethod
    def _producer_is_alive(lock: Path) -> bool | None:
        try:
            text = lock.read_text(encoding="ascii").strip()
            pid = int(text.removeprefix("pid="))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @classmethod
    def _quarantine_stale_lock(cls, lock: Path) -> bool:
        if cls._producer_is_alive(lock) is not False:
            return False
        try:
            descriptor = os.open(lock, os.O_RDONLY)
        except FileNotFoundError:
            return True
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            try:
                claimed = os.fstat(descriptor)
                try:
                    current = lock.stat()
                except FileNotFoundError:
                    return True
                if (claimed.st_dev, claimed.st_ino) != (
                    current.st_dev,
                    current.st_ino,
                ):
                    return False
                if cls._producer_is_alive(lock) is not False:
                    return False
                cls._quarantine_orphan_staging(lock)
                quarantine = lock.with_name(
                    f"{lock.name}.stale-{time.time_ns()}"
                )
                try:
                    os.replace(lock, quarantine)
                except FileNotFoundError:
                    pass
                return True
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @staticmethod
    def _quarantine_orphan_staging(lock: Path) -> None:
        suffix = ".produce.lock"
        if not lock.name.startswith(".") or not lock.name.endswith(suffix):
            raise CacheError(f"invalid producer lock name: {lock}")
        digest = lock.name[1:-len(suffix)]
        for staging in tuple(lock.parent.glob(f".{digest}.tmp-*")):
            quarantine = Path(
                tempfile.mkdtemp(
                    prefix=f".{digest}.orphan-",
                    dir=lock.parent,
                )
            )
            try:
                os.replace(staging, quarantine / "payload")
            except FileNotFoundError:
                quarantine.rmdir()

    def reindexed_view(
        self,
        key: ScientificCacheKey,
        ordered_items: Sequence[CacheItem | tuple[str, str]],
    ) -> ReindexedView:
        """Build an exact full-axis reordering without copying scientific data."""

        entry = self.resolve(key)
        if entry is None:
            raise CacheIdentityMismatch(f"cache entry does not exist: {key.digest}")
        requested = _cache_items(ordered_items)
        source_by_id = {
            item.item_id: (index, item.sha256) for index, item in enumerate(entry.items)
        }
        requested_ids = {item.item_id for item in requested}
        source_ids = set(source_by_id)
        if requested_ids != source_ids or len(requested) != len(entry.items):
            missing = sorted(source_ids - requested_ids)
            extra = sorted(requested_ids - source_ids)
            raise CacheIdentityMismatch(
                f"reindexed item set mismatch: missing={missing!r}, extra={extra!r}"
            )
        indices: list[int] = []
        for item in requested:
            source_index, source_hash = source_by_id[item.item_id]
            if item.sha256 != source_hash:
                raise CacheIdentityMismatch(f"item hash changed for {item.item_id!r}")
            indices.append(source_index)
        return ReindexedView(key.digest, entry.items, requested, tuple(indices))

    @staticmethod
    def _manifest_payload(
        key: ScientificCacheKey,
        files: tuple[CachedFile, ...],
        items: tuple[CacheItem, ...],
    ) -> dict[str, object]:
        return {
            "schema_version": "scientific_cache_entry_v2",
            "completed": True,
            "scientific_identity": key.digest,
            "scientific_cache_key": key.as_dict(),
            "files": [item.as_dict() for item in files],
            "items": [item.as_dict() for item in items],
        }

    @staticmethod
    def _cached_file_from_dict(value: object) -> CachedFile:
        if not isinstance(value, dict):
            raise CacheIdentityMismatch("cache file record must be an object")
        expected = {
            "relative_path",
            "sha256",
            "size_bytes",
            "dtype",
            "shape",
            "axes",
            "units",
            "space",
            "shard_interval",
        }
        if set(value) != expected:
            raise CacheIdentityMismatch("cache file record has unexpected fields")
        axes_value = value["axes"]
        if not isinstance(axes_value, list):
            raise CacheIdentityMismatch("cache file axes must be an array")
        axes: list[AxisRef] = []
        for axis in axes_value:
            if not isinstance(axis, dict) or set(axis) != {"axis_id", "count", "sha256"}:
                raise CacheIdentityMismatch("cache axis record is invalid")
            axes.append(AxisRef(axis["axis_id"], axis["count"], axis["sha256"]))
        shard_value = value["shard_interval"]
        shard: CacheShardInterval | None = None
        if shard_value is not None:
            if not isinstance(shard_value, dict) or set(shard_value) != {
                "set_id",
                "axis_id",
                "start",
                "stop",
            }:
                raise CacheIdentityMismatch("cache shard interval record is invalid")
            shard = CacheShardInterval(
                shard_value["set_id"],
                shard_value["axis_id"],
                shard_value["start"],
                shard_value["stop"],
            )
        shape_value = value["shape"]
        if shape_value is not None and not isinstance(shape_value, list):
            raise CacheIdentityMismatch("cache file shape must be an array or null")
        metadata = CacheFileMetadata(
            dtype=value["dtype"],
            shape=None if shape_value is None else tuple(shape_value),
            axes=tuple(axes),
            units=value["units"],
            space=value["space"],
            shard_interval=shard,
        )
        return CachedFile(
            value["relative_path"],
            value["sha256"],
            value["size_bytes"],
            metadata,
        )

    @staticmethod
    def _validate_file_structure(path: Path, record: CachedFile) -> None:
        metadata = record.metadata
        if not metadata.is_array:
            return
        if path.suffix != ".npy":
            raise CacheCorruption(f"array cache file is not NPY: {record.relative_path}")
        try:
            array = np.load(path, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError) as exc:
            raise CacheCorruption(
                f"cache array header is invalid: {record.relative_path}"
            ) from exc
        try:
            if not isinstance(array, np.ndarray):
                raise CacheCorruption(
                    f"cache array did not materialize as ndarray: {record.relative_path}"
                )
            if array.dtype != np.dtype(metadata.dtype) or array.shape != metadata.shape:
                raise CacheCorruption(
                    f"cache array metadata mismatch: {record.relative_path}"
                )
        finally:
            mmap = getattr(array, "_mmap", None)
            if mmap is not None:
                mmap.close()

    @staticmethod
    def _validate_shards(files: tuple[CachedFile, ...]) -> None:
        groups: dict[str, list[tuple[CacheShardInterval, AxisRef]]] = {}
        for record in files:
            interval = record.metadata.shard_interval
            if interval is None:
                continue
            matching = tuple(
                axis for axis in record.metadata.axes if axis.axis_id == interval.axis_id
            )
            if len(matching) != 1:
                raise CacheCorruption("cache shard axis metadata is inconsistent")
            groups.setdefault(interval.set_id, []).append((interval, matching[0]))
        for set_id, members in groups.items():
            first_axis = members[0][1]
            if any(axis != first_axis for _interval, axis in members):
                raise CacheCorruption(f"cache shard axis changed within set {set_id!r}")
            intervals = [interval for interval, _axis in members]
            if intervals != sorted(intervals, key=lambda value: value.start):
                raise CacheCorruption(f"cache shard intervals are reordered in set {set_id!r}")
            expected_start = 0
            for interval in intervals:
                if interval.start != expected_start:
                    raise CacheCorruption(
                        f"cache shard intervals are missing or overlapping in set {set_id!r}"
                    )
                expected_start = interval.stop
            if expected_start != first_axis.count:
                raise CacheCorruption(f"cache shard set {set_id!r} is incomplete")

    @staticmethod
    def _normalize_metadata(
        files: Mapping[str, Path],
        metadata: Mapping[str, CacheFileMetadata] | None,
    ) -> dict[str, CacheFileMetadata]:
        supplied = {} if metadata is None else dict(metadata)
        normalized: dict[str, CacheFileMetadata] = {}
        for relative_path, value in supplied.items():
            path = _relative_path(relative_path)
            if path not in files:
                raise CacheIdentityMismatch(
                    f"cache metadata names an undeclared file: {path}"
                )
            if not isinstance(value, CacheFileMetadata):
                raise CacheIdentityMismatch("cache metadata values must be CacheFileMetadata")
            normalized[path] = value
        for relative_path in files:
            value = normalized.get(relative_path, CacheFileMetadata())
            if relative_path.endswith(".npy") and not value.is_array:
                raise CacheIdentityMismatch(
                    f"NumPy cache payload requires structural metadata: {relative_path}"
                )
            if not relative_path.endswith(".npy") and value.is_array:
                raise CacheIdentityMismatch(
                    f"array cache payload must use the .npy format: {relative_path}"
                )
            normalized[relative_path] = value
        return normalized

    @staticmethod
    def _copy_and_hash(source: Path, target: Path) -> tuple[str, int]:
        import hashlib

        digest = hashlib.sha256()
        size_bytes = 0
        with source.open("rb") as input_stream, target.open("xb") as output_stream:
            while True:
                chunk = input_stream.read(1024 * 1024)
                if not chunk:
                    break
                output_stream.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        shutil.copystat(source, target, follow_symlinks=False)
        increment_performance_event("payload_read_bytes", amount=size_bytes)
        increment_performance_event("payload_write_bytes", amount=size_bytes)
        increment_performance_event("payload_hash_bytes", amount=size_bytes)
        return digest.hexdigest(), size_bytes

    @staticmethod
    def _require_exact_publication(
        entry: CacheEntry,
        files: tuple[CachedFile, ...],
        items: tuple[CacheItem, ...],
    ) -> None:
        if entry.files != files or entry.items != items:
            raise CacheIdentityMismatch(
                "existing scientific identity contains different files or item metadata"
            )

    def _load_entry(
        self,
        path: Path,
        *,
        expected_key: ScientificCacheKey,
        reused: bool,
        trust_publisher_payloads: bool = False,
    ) -> CacheEntry:
        manifest_path = path / MANIFEST_NAME
        if path.is_symlink() or not path.is_dir():
            raise CacheCorruption(f"cache entry is not a physical directory: {path}")
        if manifest_path.is_symlink():
            raise CacheCorruption(f"cache manifest cannot be a symbolic link: {manifest_path}")
        if not manifest_path.is_file():
            raise CacheCorruption(f"cache manifest is missing: {manifest_path}")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CacheCorruption(f"cache manifest is unreadable: {manifest_path}") from exc
        expected_fields = {
            "schema_version",
            "completed",
            "scientific_identity",
            "scientific_cache_key",
            "files",
            "items",
        }
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            raise CacheCorruption("cache manifest has unexpected fields")
        if payload["schema_version"] != "scientific_cache_entry_v2":
            raise CacheCorruption("unsupported cache manifest schema")
        if payload["completed"] is not True:
            raise CacheCorruption("cache manifest is not complete")
        try:
            actual_key = ScientificCacheKey.from_dict(payload["scientific_cache_key"])
        except CacheIdentityError as exc:
            raise CacheCorruption("cache manifest contains an invalid scientific key") from exc
        if actual_key != expected_key or payload["scientific_identity"] != expected_key.digest:
            raise CacheIdentityMismatch(
                "cache manifest scientific identity does not match the request"
            )
        if actual_key.digest != payload["scientific_identity"]:
            raise CacheCorruption("cache manifest scientific identity digest is inconsistent")

        try:
            files = tuple(self._cached_file_from_dict(item) for item in payload["files"])
            items = _cache_items(
                tuple((item["item_id"], item["sha256"]) for item in payload["items"])
            )
        except (CacheIdentityMismatch, KeyError, TypeError, ValueError) as exc:
            raise CacheCorruption("cache manifest file or item records are invalid") from exc
        if tuple(sorted(files, key=lambda item: item.relative_path)) != files:
            raise CacheCorruption("cache manifest files must be unique and sorted")
        file_names = tuple(item.relative_path for item in files)
        if len(set(file_names)) != len(file_names):
            raise CacheCorruption("cache manifest file paths must be unique")
        declared = set(file_names)
        descendants = tuple(path.rglob("*"))
        if any(
            descendant.is_symlink()
            for descendant in descendants
            if not _is_platform_sidecar(descendant.relative_to(path))
        ):
            raise CacheCorruption("cache entries cannot contain symbolic links")
        actual = {
            file.relative_to(path).as_posix()
            for file in descendants
            if file.is_file()
            and file != manifest_path
            and not _is_platform_sidecar(file.relative_to(path))
        }
        if actual != declared:
            raise CacheCorruption(
                f"cache manifest is incomplete: missing={sorted(declared - actual)!r}, "
                f"extra={sorted(actual - declared)!r}"
            )
        verified_key = (expected_key.kind, expected_key.digest)
        verify_payloads = verified_key not in self._verified_entries
        for record in files:
            file_path = path / record.relative_path
            if file_path.stat().st_size != record.size_bytes:
                raise CacheCorruption(f"cache file failed verification: {record.relative_path}")
            self._validate_file_structure(file_path, record)
            if verify_payloads and not trust_publisher_payloads:
                actual_sha256 = sha256_file(file_path)
                increment_performance_event(
                    "payload_read_bytes",
                    amount=record.size_bytes,
                )
                increment_performance_event(
                    "payload_hash_bytes",
                    amount=record.size_bytes,
                )
                if actual_sha256 != record.sha256:
                    raise CacheCorruption(
                        f"cache file failed verification: {record.relative_path}"
                    )
        self._validate_shards(files)
        if verify_payloads and not trust_publisher_payloads:
            increment_performance_event(
                "cache_full_verification",
                key=f"{expected_key.kind}:{expected_key.digest}",
            )
        self._verified_entries.add(verified_key)
        return CacheEntry(path, actual_key, files, items, reused)


class ArtifactStore:
    """Materialize verified ArtifactRef payloads from configured roots."""

    def __init__(self, allowed_roots: Sequence[str | Path]) -> None:
        roots = tuple(Path(root).expanduser().resolve() for root in allowed_roots)
        if not roots:
            raise ArtifactValidationError("at least one allowed artifact root is required")
        if any(not root.is_dir() for root in roots):
            raise ArtifactValidationError(
                "every allowed artifact root must be an existing directory"
            )
        self.allowed_roots = roots
        self._verified_artifacts: dict[
            tuple[Path, str],
            tuple[int, int, int, int, int],
        ] = {}
        self._verification_lock = RLock()

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int, int, int, int]:
        status = path.stat()
        return (
            int(status.st_dev),
            int(status.st_ino),
            int(status.st_size),
            int(status.st_mtime_ns),
            int(status.st_ctime_ns),
        )

    def _verify_payload(
        self,
        path: Path,
        expected_sha256: str,
    ) -> tuple[int, int, int, int, int]:
        identity = (path, expected_sha256)
        with self._verification_lock:
            signature = self._file_signature(path)
            if self._verified_artifacts.get(identity) == signature:
                return signature
            try:
                with path.open("rb") as handle:
                    digest = sha256_stream(handle)
            except OSError as exc:
                raise ArtifactValidationError(
                    f"artifact payload cannot be read: {path}"
                ) from exc
            final_signature = self._file_signature(path)
            if final_signature != signature:
                raise ArtifactValidationError(
                    "artifact file changed during SHA-256 verification"
                )
            if digest != expected_sha256:
                raise ArtifactValidationError(
                    "artifact file SHA-256 does not match ArtifactRef"
                )
            self._verified_artifacts[identity] = final_signature
            return final_signature

    def materialize(
        self,
        artifact: ArtifactRef,
        *,
        expected_dtype: str | np.dtype,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None = None,
    ) -> np.ndarray:
        """Load one array only after metadata, path, and content verification."""

        if not isinstance(artifact, ArtifactRef):
            raise TypeError("artifact must be an ArtifactRef; bare paths are forbidden")
        if mmap_mode not in {None, "r"}:
            raise ArtifactValidationError("mmap_mode must be None or read-only 'r'")
        expected_shape = tuple(int(value) for value in expected_shape)
        expected_axes = tuple(expected_axes)
        if not all(isinstance(axis, AxisRef) for axis in expected_axes):
            raise TypeError("expected_axes must contain only AxisRef values")
        expected_dtype_value = np.dtype(expected_dtype)
        if artifact.shape != expected_shape:
            raise ArtifactValidationError("artifact shape does not match the explicit requirement")
        if np.dtype(artifact.dtype) != expected_dtype_value:
            raise ArtifactValidationError("artifact dtype does not match the explicit requirement")
        if artifact.axis_refs != expected_axes or artifact.axis_hashes != tuple(
            axis.sha256 for axis in expected_axes
        ):
            raise ArtifactValidationError(
                "artifact ordered axes do not match the explicit requirement"
            )
        if artifact.units != expected_units:
            raise ArtifactValidationError("artifact units do not match the explicit requirement")
        if artifact.space != expected_space:
            raise ArtifactValidationError("artifact space does not match the explicit requirement")

        path = self._safe_file_path(artifact.uri)
        if path.suffix != ".npy":
            raise ArtifactValidationError("ArtifactStore supports only .npy array artifacts")
        verified_signature = self._verify_payload(path, artifact.sha256)
        try:
            if mmap_mode is None:
                with path.open("rb") as handle:
                    array = np.load(handle, allow_pickle=False)
            else:
                array = np.load(path, allow_pickle=False, mmap_mode=mmap_mode)
        except ArtifactValidationError:
            raise
        except (OSError, ValueError) as exc:
            raise ArtifactValidationError(f"artifact array cannot be loaded: {path}") from exc
        if self._file_signature(path) != verified_signature:
            raise ArtifactValidationError("artifact file changed during materialization")
        if not isinstance(array, np.ndarray):
            close = getattr(array, "close", None)
            if callable(close):
                close()
            raise ArtifactValidationError("artifact did not materialize as one NumPy array")
        if array.shape != expected_shape or array.dtype != expected_dtype_value:
            raise ArtifactValidationError("materialized array metadata differs from ArtifactRef")
        array.flags.writeable = False
        return array

    def _materialize_view_positions(
        self,
        selector: ArtifactRef | None,
        *,
        output_axis: AxisRef,
        parent_count: int,
        role: str,
    ) -> np.ndarray | None:
        if selector is None:
            return None
        positions = self.materialize(
            selector,
            expected_dtype="int64",
            expected_shape=(output_axis.count,),
            expected_axes=(output_axis,),
            expected_units="index",
            expected_space=None,
        )
        values = np.asarray(positions, dtype=np.int64)
        if values.size < 1:
            raise ArtifactValidationError(f"{role} positions cannot be empty")
        if int(values.min()) < 0 or int(values.max()) >= parent_count:
            raise ArtifactValidationError(f"{role} positions exceed the parent axis")
        if np.unique(values).size != values.size:
            raise ArtifactValidationError(f"{role} positions contain duplicate values")
        values.flags.writeable = False
        return values

    def iter_indexed_array_view_blocks(
        self,
        view: IndexedArrayView,
        *,
        block_columns: int,
    ):
        """Yield verified logical column blocks without a full view allocation."""

        if not isinstance(view, IndexedArrayView):
            raise TypeError("view must be an IndexedArrayView")
        if type(block_columns) is not int or block_columns < 1:
            raise ArtifactValidationError("block_columns must be a positive integer")
        maximum_columns = min(block_columns, view.shape[1])
        block_budget = (
            view.shape[0] * maximum_columns * np.dtype(view.dtype).itemsize
        )
        with self.open_indexed_array_view(
            view,
            max_block_bytes=block_budget,
        ) as reader:
            for start in range(0, view.shape[1], block_columns):
                stop = min(start + block_columns, view.shape[1])
                block = reader[:, start:stop]
                expected_shape = (view.shape[0], stop - start)
                if block.shape != expected_shape:
                    raise ArtifactValidationError(
                        "IndexedArrayView block shape differs from its logical axes"
                    )
                yield start, stop, block

    def open_indexed_array_view(
        self,
        view: IndexedArrayView,
        *,
        max_block_bytes: int,
    ) -> IndexedArrayReader:
        """Open one verified logical view for explicitly bounded indexed reads."""

        if not isinstance(view, IndexedArrayView):
            raise TypeError("view must be an IndexedArrayView")
        if type(max_block_bytes) is not int or max_block_bytes < 1:
            raise ArtifactValidationError(
                "max_block_bytes must be a positive integer"
            )
        row_positions = self._materialize_view_positions(
            view.row_positions,
            output_axis=view.axis_refs[0],
            parent_count=view.parent.shape[0],
            role="row",
        )
        column_positions = self._materialize_view_positions(
            view.column_positions,
            output_axis=view.axis_refs[1],
            parent_count=view.parent.shape[1],
            role="column",
        )
        parent = self.materialize(
            view.parent,
            expected_dtype=view.dtype,
            expected_shape=view.parent.shape,
            expected_axes=view.parent.axis_refs,
            expected_units=view.units,
            expected_space=view.space,
            mmap_mode="r",
        )
        return IndexedArrayReader(
            parent,
            row_positions,
            column_positions,
            logical_shape=view.shape,
            max_block_bytes=max_block_bytes,
        )

    def materialize_indexed_array_view(
        self,
        view: IndexedArrayView,
        *,
        max_bytes: int,
        block_columns: int = 256,
    ) -> np.ndarray:
        """Explicitly materialize one verified view within a caller byte budget."""

        if not isinstance(view, IndexedArrayView):
            raise TypeError("view must be an IndexedArrayView")
        if type(max_bytes) is not int or max_bytes < 1:
            raise ArtifactValidationError("max_bytes must be a positive integer")
        logical_bytes = int(np.prod(view.shape, dtype=np.int64)) * np.dtype(
            view.dtype
        ).itemsize
        if logical_bytes > max_bytes:
            raise ArtifactValidationError(
                "IndexedArrayView logical bytes exceed the explicit materialization budget"
            )
        output = np.empty(view.shape, dtype=np.dtype(view.dtype))
        for start, stop, block in self.iter_indexed_array_view_blocks(
            view,
            block_columns=block_columns,
        ):
            output[:, start:stop] = block
        output.flags.writeable = False
        return output

    def materialize_document(
        self,
        artifact: ArtifactRef,
        *,
        expected_kind: str,
    ) -> dict[str, Any]:
        """Load one JSON object only after metadata, path, and content verification."""

        if not isinstance(artifact, ArtifactRef):
            raise TypeError("artifact must be an ArtifactRef; bare paths are forbidden")
        if artifact.schema_version != "dual_frequency_document_v1":
            raise ArtifactValidationError("unsupported document artifact schema")
        if artifact.kind != expected_kind:
            raise ArtifactValidationError("artifact kind does not match the explicit requirement")
        if (
            artifact.dtype is not None
            or artifact.shape is not None
            or artifact.axis_refs
            or artifact.axis_hashes
            or artifact.units is not None
            or artifact.space is not None
        ):
            raise ArtifactValidationError(
                "document artifacts cannot declare dtype, shape, axes, units, or space"
            )

        path = self._safe_file_path(artifact.uri)
        if path.suffix != ".json":
            raise ArtifactValidationError("ArtifactStore supports only .json document artifacts")
        verified_signature = self._verify_payload(path, artifact.sha256)
        try:
            with path.open("rb") as handle:
                payload = json.loads(handle.read().decode("utf-8"))
        except ArtifactValidationError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactValidationError(
                f"artifact document cannot be loaded as UTF-8 JSON: {path}"
            ) from exc
        if self._file_signature(path) != verified_signature:
            raise ArtifactValidationError("artifact file changed during materialization")
        if not isinstance(payload, dict):
            raise ArtifactValidationError("artifact document must contain one JSON object")
        return payload

    def _safe_file_path(self, uri: str) -> Path:
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "file"
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
        ):
            raise ArtifactValidationError("artifact URI must be a local absolute file URI")
        try:
            path = Path(unquote(parsed.path)).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ArtifactValidationError(
                "artifact URI does not resolve to an existing file"
            ) from exc
        if not path.is_file():
            raise ArtifactValidationError("artifact URI does not resolve to a file")
        if not any(self._is_within(path, root) for root in self.allowed_roots):
            raise ArtifactValidationError("artifact path is outside configured roots")
        return path

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True


@dataclass(frozen=True)
class RunScopedArtifactPublisher:
    """Publish immutable arrays and JSON documents beneath one exact task root."""

    root: Path
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        root = Path(self.root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise ArtifactPublicationError(f"artifact root is not a directory: {root}")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "producer_id", _token(self.producer_id, "producer_id"))
        object.__setattr__(
            self,
            "producer_version",
            _token(self.producer_version, "producer_version"),
        )

    def array(
        self,
        filename: str,
        value: np.ndarray,
        *,
        kind: str,
        axes: tuple[AxisRef, ...],
        units: str | None,
        space: str | None,
    ) -> ArtifactRef:
        array = np.asarray(value)
        kind = self._publication_token(kind, "kind")
        units = self._optional_publication_token(units, "units")
        space = self._optional_publication_token(space, "space")
        if (
            array.dtype == object
            or not array.shape
            or any(dimension < 1 for dimension in array.shape)
        ):
            raise ArtifactPublicationError(
                "published arrays must be nonempty and non-object"
            )
        if tuple(axis.count for axis in axes) != array.shape:
            raise ArtifactPublicationError(
                "published array shape does not match its axes"
            )
        target = self._target(filename, ".npy")
        temporary = self._temporary(target)
        try:
            with temporary.open("wb") as stream:
                np.save(stream, array, allow_pickle=False)
            payload_hash = sha256_file(temporary)
            metadata = self._metadata_payload(
                target=target,
                payload_sha256=payload_hash,
                kind=kind,
                schema_version="dual_frequency_array_v1",
                dtype=np.dtype(array.dtype).name,
                shape=tuple(int(dimension) for dimension in array.shape),
                axes=axes,
                units=units,
                space=space,
            )
            self._publish_with_metadata(temporary, target, metadata)
        finally:
            temporary.unlink(missing_ok=True)
        return ArtifactRef(
            kind=kind,
            schema_version="dual_frequency_array_v1",
            uri=target.as_uri(),
            sha256=payload_hash,
            dtype=np.dtype(array.dtype).name,
            shape=tuple(int(dimension) for dimension in array.shape),
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space=space,
            producer_id=self.producer_id,
            producer_version=self.producer_version,
        )

    def document(
        self,
        filename: str,
        payload: dict[str, Any],
        *,
        kind: str,
    ) -> ArtifactRef:
        kind = self._publication_token(kind, "kind")
        target = self._target(filename, ".json")
        temporary = self._temporary(target)
        try:
            temporary.write_text(
                json.dumps(
                    payload,
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            payload_hash = sha256_file(temporary)
            metadata = self._metadata_payload(
                target=target,
                payload_sha256=payload_hash,
                kind=kind,
                schema_version="dual_frequency_document_v1",
                dtype=None,
                shape=None,
                axes=(),
                units=None,
                space=None,
            )
            self._publish_with_metadata(temporary, target, metadata)
        finally:
            temporary.unlink(missing_ok=True)
        return ArtifactRef(
            kind=kind,
            schema_version="dual_frequency_document_v1",
            uri=target.as_uri(),
            sha256=payload_hash,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id=self.producer_id,
            producer_version=self.producer_version,
        )

    def _target(self, filename: str, suffix: str) -> Path:
        if Path(filename).name != filename or not filename.endswith(suffix):
            raise ArtifactPublicationError(f"unsafe artifact filename: {filename!r}")
        return self.root / filename

    def _temporary(self, target: Path) -> Path:
        descriptor, path = tempfile.mkstemp(prefix=f".{target.name}.", dir=self.root)
        os.close(descriptor)
        return Path(path)

    @staticmethod
    def _publication_token(value: str, field: str) -> str:
        token = str(value).strip()
        if not token:
            raise ArtifactPublicationError(f"{field} must be nonempty")
        return token

    @classmethod
    def _optional_publication_token(
        cls,
        value: str | None,
        field: str,
    ) -> str | None:
        return None if value is None else cls._publication_token(value, field)

    def _metadata_payload(
        self,
        *,
        target: Path,
        payload_sha256: str,
        kind: str,
        schema_version: str,
        dtype: str | None,
        shape: tuple[int, ...] | None,
        axes: tuple[AxisRef, ...],
        units: str | None,
        space: str | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "dual_frequency_artifact_metadata_v1",
            "filename": target.name,
            "payload_sha256": payload_sha256,
            "artifact": {
                "kind": str(kind),
                "schema_version": schema_version,
                "dtype": dtype,
                "shape": list(shape) if shape is not None else None,
                "axes": [
                    {
                        "axis_id": axis.axis_id,
                        "count": axis.count,
                        "sha256": axis.sha256,
                    }
                    for axis in axes
                ],
                "units": units,
                "space": space,
                "producer_id": self.producer_id,
                "producer_version": self.producer_version,
            },
        }

    def _publish_with_metadata(
        self,
        temporary: Path,
        target: Path,
        metadata: dict[str, Any],
    ) -> None:
        expected_payload_hash = str(metadata["payload_sha256"])
        metadata_target = target.with_name(f"{target.name}.artifact.json")
        metadata_temporary = self._temporary(metadata_target)
        try:
            metadata_temporary.write_text(
                json.dumps(
                    metadata,
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            expected_metadata_hash = sha256_file(metadata_temporary)
            lock = target.with_name(f".{target.name}.publish.lock")
            descriptor = self._acquire_publication_lock(lock)
            try:
                payload_exists = os.path.lexists(target)
                metadata_exists = os.path.lexists(metadata_target)
                if payload_exists:
                    self._validate_existing(target, expected_payload_hash)
                if metadata_exists:
                    self._validate_existing(metadata_target, expected_metadata_hash)
                if payload_exists != metadata_exists:
                    raise ArtifactPublicationError(
                        f"artifact payload and metadata sidecar are incomplete: {target}"
                    )
                if payload_exists:
                    return
                os.replace(temporary, target)
                os.replace(metadata_temporary, metadata_target)
            finally:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
        finally:
            metadata_temporary.unlink(missing_ok=True)

    @staticmethod
    def _acquire_publication_lock(lock: Path) -> int:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ArtifactPublicationError(
                f"artifact publication lock already exists: {lock}"
            ) from None
        except OSError as exc:
            raise ArtifactPublicationError(
                f"cannot acquire artifact publication lock: {lock}"
            ) from exc
        try:
            os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
            os.fsync(descriptor)
        except OSError:
            os.close(descriptor)
            lock.unlink(missing_ok=True)
            raise
        return descriptor

    @staticmethod
    def _validate_existing(target: Path, expected_hash: str) -> None:
        if (
            target.is_symlink()
            or not target.is_file()
            or sha256_file(target) != expected_hash
        ):
            raise ArtifactPublicationError(
                f"refusing to overwrite a different artifact: {target}"
            )
