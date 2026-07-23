"""Generic connectome adapter protocol and Lead-DBS HDF5 implementation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Protocol, Sequence, runtime_checkable

import h5py
import numpy as np

from .errors import ConnectomeError
from .identity import canonical_hash, sha256_file
from .models import ConnectomeMetadata, FiberChunk


_ADAPTER_NAME = "leaddbs_hdf5_idx"
_ADAPTER_VERSION = "1"
_COORDINATE_BYTES_PER_POINT = 3 * np.dtype(np.float32).itemsize


@runtime_checkable
class ConnectomeAdapter(Protocol):
    """Protocol required by the generic membership engine."""

    @property
    def metadata(self) -> ConnectomeMetadata:
        """Return stable connectome metadata without traversing streamlines."""

    def iter_chunks(self, chunk_size: int) -> Iterator[FiberChunk]:
        """Yield deterministic bounded fiber chunks."""


def _ordered_id_hash(n_fibers: int, block_size: int = 1_000_000) -> str:
    digest = hashlib.sha256()
    for start in range(1, n_fibers + 1, block_size):
        stop = min(start + block_size, n_fibers + 1)
        digest.update(np.arange(start, stop, dtype="<i8").tobytes())
    return digest.hexdigest()


def _read_lengths(dataset: h5py.Dataset) -> np.ndarray:
    if dataset.ndim not in (1, 2) or (dataset.ndim == 2 and 1 not in dataset.shape):
        raise ConnectomeError("idx must be a vector or singleton-axis matrix")
    raw = np.asarray(dataset[...], dtype=np.float64).reshape(-1)
    if raw.size == 0:
        raise ConnectomeError("idx must contain at least one fiber length")
    if not np.all(np.isfinite(raw)) or not np.all(raw == np.floor(raw)):
        raise ConnectomeError("idx fiber lengths must be finite integers")
    lengths = raw.astype(np.int64)
    if np.any(lengths < 2):
        raise ConnectomeError("every valid streamline must contain at least two points")
    lengths.setflags(write=False)
    return lengths


def _point_offsets(lengths: np.ndarray) -> np.ndarray:
    offsets = np.empty(lengths.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])
    offsets.setflags(write=False)
    return offsets


def _validate_point_ids(
    point_ids: np.ndarray,
    local_offsets: np.ndarray,
    first_fiber_id: int,
) -> bool:
    """Validate every point ID with fiber-sized rather than point-sized scratch."""

    values = np.asarray(point_ids, dtype=np.float32)
    offsets = np.asarray(local_offsets, dtype=np.int64)
    expected = np.arange(
        first_fiber_id,
        first_fiber_id + offsets.size - 1,
        dtype=np.float32,
    )
    starts = offsets[:-1]
    return bool(
        np.array_equal(np.minimum.reduceat(values, starts), expected)
        and np.array_equal(np.maximum.reduceat(values, starts), expected)
    )


class LeadDBSHDF5Connectome:
    """Chunked adapter for Lead-DBS MATLAB v7.3 `fibers`/`idx` files."""

    def __init__(self, data_mat: Path | str):
        path = Path(data_mat).expanduser()
        if not path.is_file():
            raise ConnectomeError(f"connectome data file does not exist: {path}")
        self._path = path.resolve()
        try:
            with h5py.File(self._path, "r") as handle:
                if "idx" not in handle:
                    raise ConnectomeError("connectome is missing required idx dataset")
                if "fibers" not in handle:
                    raise ConnectomeError("connectome is missing required fibers dataset")
                lengths = _read_lengths(handle["idx"])
                fibers = handle["fibers"]
                if fibers.ndim != 2 or fibers.shape[0] < 4:
                    raise ConnectomeError("fibers must have shape (at least 4, n_points)")
                n_points = int(np.sum(lengths, dtype=np.int64))
                if fibers.shape[1] != n_points:
                    raise ConnectomeError(
                        f"idx point count {n_points} does not match fibers point count {fibers.shape[1]}"
                    )
                raw_point_chunk_size = (
                    int(fibers.chunks[1])
                    if fibers.chunks is not None and len(fibers.chunks) > 1
                    else None
                )
        except ConnectomeError:
            raise
        except Exception as exc:
            raise ConnectomeError(f"failed to inspect connectome {self._path}: {exc}") from exc

        self._lengths = lengths
        self._point_offsets = _point_offsets(lengths)
        self._raw_point_chunk_size = raw_point_chunk_size
        source_hash = sha256_file(self._path)
        ordered_hash = _ordered_id_hash(int(lengths.size))
        lengths_hash = hashlib.sha256(np.asarray(lengths, dtype="<i8").tobytes()).hexdigest()
        geometry_hash = canonical_hash(
            {
                "source_hash": source_hash,
                "idx_lengths_hash": lengths_hash,
                "n_fibers": int(lengths.size),
                "n_points": n_points,
                "adapter_name": _ADAPTER_NAME,
                "adapter_version": _ADAPTER_VERSION,
            }
        )
        connectome_id = self._path.parent.name or self._path.stem
        identity_source = "data.mat:idx_position_one_based_validated_against_fibers_row_4"
        self._metadata = ConnectomeMetadata(
            connectome_id=connectome_id,
            source_path=self._path,
            source_hash=source_hash,
            geometry_hash=geometry_hash,
            ordered_fiber_id_hash=ordered_hash,
            connectome_identity=canonical_hash(
                {
                    "connectome_id": connectome_id,
                    "geometry_hash": geometry_hash,
                    "ordered_fiber_id_hash": ordered_hash,
                    "identity_source": identity_source,
                }
            ),
            identity_source=identity_source,
            adapter_name=_ADAPTER_NAME,
            adapter_version=_ADAPTER_VERSION,
            n_fibers=int(lengths.size),
            n_points=n_points,
        )

    @property
    def metadata(self) -> ConnectomeMetadata:
        """Return immutable source and canonical-ID metadata."""
        return self._metadata

    @property
    def point_offsets(self) -> np.ndarray:
        """Return the immutable complete zero-based point-boundary axis."""

        return self._point_offsets

    @property
    def raw_point_chunk_size(self) -> int | None:
        """Return the HDF5 raw point chunk width when the source is chunked."""

        return self._raw_point_chunk_size

    def point_balanced_ranges(
        self,
        point_byte_budget: int,
        *,
        coordinate_bytes_per_point: int = _COORDINATE_BYTES_PER_POINT,
    ) -> tuple[tuple[int, int], ...]:
        """Return the fewest consecutive fiber ranges below a point-byte budget.

        A single fiber may exceed the budget. Among boundaries that preserve the
        minimal greedy range count, prefer the boundary closest to an HDF5 raw
        point-chunk boundary. Returned indexes are zero-based half-open fibers.
        """

        if (
            not isinstance(point_byte_budget, int)
            or isinstance(point_byte_budget, bool)
            or point_byte_budget < 1
        ):
            raise ConnectomeError("point byte budget must be a positive integer")
        if (
            not isinstance(coordinate_bytes_per_point, int)
            or isinstance(coordinate_bytes_per_point, bool)
            or coordinate_bytes_per_point < 1
        ):
            raise ConnectomeError(
                "coordinate bytes per point must be a positive integer"
            )
        max_points = max(1, point_byte_budget // coordinate_bytes_per_point)
        offsets = self._point_offsets
        fiber_count = self._metadata.n_fibers

        def greedy_stop(start: int) -> int:
            target = int(offsets[start]) + max_points
            stop = int(np.searchsorted(offsets, target, side="right") - 1)
            return min(fiber_count, max(start + 1, stop))

        def greedy_count(start: int) -> int:
            count = 0
            while start < fiber_count:
                start = greedy_stop(start)
                count += 1
            return count

        remaining = greedy_count(0)
        ranges: list[tuple[int, int]] = []
        start = 0
        raw_chunk = self._raw_point_chunk_size
        while start < fiber_count:
            stop = greedy_stop(start)
            if raw_chunk is not None and remaining > 1:
                point_limit = int(offsets[stop])
                raw_boundary = (point_limit // raw_chunk) * raw_chunk
                candidate_indexes: set[int] = {stop}
                for boundary in (raw_boundary, raw_boundary - raw_chunk):
                    if boundary <= int(offsets[start]):
                        continue
                    insertion = int(np.searchsorted(offsets, boundary, side="left"))
                    candidate_indexes.update((insertion - 1, insertion))
                viable = tuple(
                    candidate
                    for candidate in candidate_indexes
                    if start < candidate <= stop
                    and greedy_count(candidate) <= remaining - 1
                )
                if viable:
                    stop = min(
                        viable,
                        key=lambda candidate: (
                            min(
                                int(offsets[candidate]) % raw_chunk,
                                raw_chunk - int(offsets[candidate]) % raw_chunk,
                            ),
                            -candidate,
                        ),
                    )
            ranges.append((start, stop))
            start = stop
            remaining -= 1
        return tuple(ranges)

    def iter_chunks(self, chunk_size: int) -> Iterator[FiberChunk]:
        """Yield deterministic chunks and validate every stored point-level ID."""
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
            raise ConnectomeError("fiber chunk size must be a positive integer")
        ranges = tuple(
            (start, min(start + chunk_size, self._metadata.n_fibers))
            for start in range(0, self._metadata.n_fibers, chunk_size)
        )
        yield from self._iter_ranges(ranges)

    def iter_point_balanced_chunks(
        self,
        point_byte_budget: int,
        *,
        coordinate_bytes_per_point: int = _COORDINATE_BYTES_PER_POINT,
    ) -> Iterator[FiberChunk]:
        """Yield complete fibers in deterministic point-byte-balanced ranges."""

        yield from self._iter_ranges(
            self.point_balanced_ranges(
                point_byte_budget,
                coordinate_bytes_per_point=coordinate_bytes_per_point,
            )
        )

    def _iter_ranges(
        self,
        ranges: Sequence[tuple[int, int]],
    ) -> Iterator[FiberChunk]:
        """Read validated chunks for explicit zero-based half-open fiber ranges."""

        try:
            with h5py.File(self._path, "r") as handle:
                fibers = handle["fibers"]
                for fiber_start, fiber_stop in ranges:
                    point_start = int(self._point_offsets[fiber_start])
                    point_stop = int(self._point_offsets[fiber_stop])
                    block = np.asarray(fibers[0:4, point_start:point_stop], dtype=np.float32)
                    coordinates = np.ascontiguousarray(block[0:3, :].T)
                    if not np.all(np.isfinite(coordinates)):
                        raise ConnectomeError(
                            f"connectome contains nonfinite coordinates in fibers {fiber_start + 1}:{fiber_stop}"
                        )
                    fiber_ids = np.arange(fiber_start + 1, fiber_stop + 1, dtype=np.int64)
                    offsets = (
                        self._point_offsets[fiber_start : fiber_stop + 1]
                        - point_start
                    )
                    if not _validate_point_ids(
                        block[3, :],
                        offsets,
                        fiber_start + 1,
                    ):
                        raise ConnectomeError(
                            f"point-level canonical fiber ID mismatch in fibers {fiber_start + 1}:{fiber_stop}"
                        )
                    offsets = np.asarray(offsets, dtype=np.int64)
                    fiber_ids.setflags(write=False)
                    offsets.setflags(write=False)
                    coordinates.setflags(write=False)
                    yield FiberChunk(
                        fiber_ids=fiber_ids,
                        point_offsets=offsets,
                        points=coordinates,
                    )
        except ConnectomeError:
            raise
        except Exception as exc:
            raise ConnectomeError(f"failed while reading connectome {self._path}: {exc}") from exc

    def load_streamlines(self, fiber_ids: Sequence[int]) -> tuple[np.ndarray, ...]:
        """Load a small requested set of one-based canonical fibers in request order."""
        requested = np.asarray(fiber_ids, dtype=np.int64)
        if requested.ndim != 1:
            raise ConnectomeError("requested canonical fiber IDs must be one-dimensional")
        if np.unique(requested).size != requested.size:
            raise ConnectomeError("requested canonical fiber IDs must be unique")
        if np.any(requested < 1) or np.any(requested > self._metadata.n_fibers):
            raise ConnectomeError("requested canonical fiber ID is outside the connectome")
        if requested.size == 0:
            return ()
        point_stops = np.cumsum(self._lengths, dtype=np.int64)
        streamlines: list[np.ndarray] = []
        try:
            with h5py.File(self._path, "r") as handle:
                fibers = handle["fibers"]
                for fiber_id in requested:
                    index = int(fiber_id) - 1
                    point_start = 0 if index == 0 else int(point_stops[index - 1])
                    point_stop = int(point_stops[index])
                    block = np.asarray(fibers[0:4, point_start:point_stop], dtype=np.float32)
                    coordinates = np.ascontiguousarray(block[0:3, :].T)
                    if not np.all(np.isfinite(coordinates)):
                        raise ConnectomeError(f"canonical fiber {int(fiber_id)} contains nonfinite coordinates")
                    if not np.all(block[3, :] == np.float32(fiber_id)):
                        raise ConnectomeError(f"canonical fiber ID mismatch while loading fiber {int(fiber_id)}")
                    coordinates.setflags(write=False)
                    streamlines.append(coordinates)
        except ConnectomeError:
            raise
        except Exception as exc:
            raise ConnectomeError(f"failed to load sampled fibers from {self._path}: {exc}") from exc
        return tuple(streamlines)


def open_connectome(path: Path | str) -> LeadDBSHDF5Connectome:
    """Open a Lead-DBS connectome directory or its `data.mat` file."""
    source = Path(path).expanduser()
    if source.is_dir():
        source = source / "data.mat"
    return LeadDBSHDF5Connectome(source)
