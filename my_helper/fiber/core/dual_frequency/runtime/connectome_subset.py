"""Exact final-axis connectome filtering and pPAM state aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import h5py
import numpy as np
from scipy.io import loadmat

from ..backends.activation.canonical_mapping import activation_universe
from ..backends.activation.ppam import validate_ten_sample_probabilities


class ConnectomeSubsetError(RuntimeError):
    """Raised when a connectome cannot be restricted to an exact fiber axis."""


@dataclass(frozen=True, slots=True)
class FilteredConnectome:
    """One local Lead-DBS fiber file plus its exact final-axis mapping."""

    path: Path
    feature_ids: np.ndarray
    local_fiber_ids: np.ndarray
    point_counts: np.ndarray
    parent_fiber_count: int

    def __post_init__(self) -> None:
        path = Path(self.path).expanduser().resolve()
        if not path.is_file():
            raise ConnectomeSubsetError(f"filtered connectome is missing: {path}")
        feature_ids = activation_universe(self.feature_ids)
        local_ids = np.asarray(self.local_fiber_ids, dtype=np.int64)
        point_counts = np.asarray(self.point_counts, dtype=np.int64)
        expected = np.arange(1, feature_ids.size + 1, dtype=np.int64)
        if not np.array_equal(local_ids, expected):
            raise ConnectomeSubsetError("local fiber IDs must be contiguous and one-based")
        if point_counts.shape != feature_ids.shape or np.any(point_counts < 1):
            raise ConnectomeSubsetError("every filtered fiber requires a positive point count")
        if type(self.parent_fiber_count) is not int or self.parent_fiber_count < feature_ids.size:
            raise ConnectomeSubsetError("parent_fiber_count is inconsistent")
        feature_ids.flags.writeable = False
        local_ids.flags.writeable = False
        point_counts.flags.writeable = False
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "feature_ids", feature_ids)
        object.__setattr__(self, "local_fiber_ids", local_ids)
        object.__setattr__(self, "point_counts", point_counts)


def _integer_lengths(value: np.ndarray) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    rounded = np.rint(array).astype(np.int64)
    if (
        array.size == 0
        or not np.all(np.isfinite(array))
        or not np.allclose(array, rounded, rtol=0.0, atol=0.0)
        or np.any(rounded < 1)
    ):
        raise ConnectomeSubsetError("connectome idx must contain positive integers")
    return rounded


def _normalize_fibers(value: np.ndarray) -> np.ndarray:
    fibers = np.asarray(value)
    if fibers.ndim != 2:
        raise ConnectomeSubsetError("connectome fibers must be two-dimensional")
    if fibers.shape[0] in {4, 5}:
        normalized = fibers
    elif fibers.shape[1] in {4, 5}:
        normalized = fibers.T
    else:
        raise ConnectomeSubsetError("connectome fibers require four or five coordinate rows")
    if not np.issubdtype(normalized.dtype, np.number):
        raise ConnectomeSubsetError("connectome fibers must be numeric")
    if not np.all(np.isfinite(normalized[:3, :])):
        raise ConnectomeSubsetError("connectome coordinates must be finite")
    return normalized


def _load_parent(source: Path) -> tuple[np.ndarray, np.ndarray]:
    try:
        with h5py.File(source, "r") as handle:
            if "fibers" not in handle or "idx" not in handle:
                raise ConnectomeSubsetError("Lead-DBS connectome lacks fibers or idx")
            return _normalize_fibers(handle["fibers"][:]), _integer_lengths(handle["idx"][:])
    except OSError:
        try:
            payload = loadmat(source)
        except (OSError, ValueError, NotImplementedError) as exc:
            raise ConnectomeSubsetError(f"connectome cannot be loaded: {source}") from exc
        if "fibers" not in payload or "idx" not in payload:
            raise ConnectomeSubsetError("Lead-DBS connectome lacks fibers or idx")
        return _normalize_fibers(payload["fibers"]), _integer_lengths(payload["idx"])


def _copy_selected_hdf5(
    source: Path,
    target: Path,
    feature_ids: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Stream an HDF5 parent without loading its complete point matrix."""

    with h5py.File(source, "r") as parent:
        if "fibers" not in parent or "idx" not in parent:
            raise ConnectomeSubsetError("Lead-DBS connectome lacks fibers or idx")
        source_fibers = parent["fibers"]
        if source_fibers.ndim != 2:
            raise ConnectomeSubsetError(
                "HDF5 Lead-DBS fibers must be two-dimensional"
            )
        if source_fibers.shape[0] in {4, 5}:
            row_major = True
            point_count_total = int(source_fibers.shape[1])
        elif source_fibers.shape[1] in {4, 5}:
            row_major = False
            point_count_total = int(source_fibers.shape[0])
        else:
            raise ConnectomeSubsetError(
                "HDF5 Lead-DBS fibers require four or five coordinate columns"
            )
        lengths = _integer_lengths(parent["idx"][:])
        parent_count = int(lengths.size)
        if int(np.sum(lengths, dtype=np.int64)) != point_count_total:
            raise ConnectomeSubsetError("connectome idx does not span the point matrix")
        if np.any(feature_ids < 1) or np.any(feature_ids > parent_count):
            raise ConnectomeSubsetError("final fiber ID is outside the formal connectome")
        offsets = np.empty(parent_count + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(lengths, dtype=np.int64, out=offsets[1:])
        selected_lengths = lengths[feature_ids - 1]
        total_points = int(np.sum(selected_lengths, dtype=np.int64))

        target.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(target, "x") as filtered:
            output = filtered.create_dataset(
                "fibers",
                shape=(4, total_points),
                dtype=source_fibers.dtype,
            )
            cursor = 0
            for local_id, (feature_id, point_count) in enumerate(
                zip(feature_ids.tolist(), selected_lengths.tolist(), strict=True),
                start=1,
            ):
                start = int(offsets[feature_id - 1])
                stop = int(offsets[feature_id])
                if row_major:
                    block = np.asarray(source_fibers[:3, start:stop])
                else:
                    block = np.asarray(source_fibers[start:stop, :3]).T
                if block.shape != (3, point_count) or not np.all(np.isfinite(block)):
                    raise ConnectomeSubsetError("selected fiber coordinates are invalid")
                output[:3, cursor : cursor + point_count] = block
                output[3, cursor : cursor + point_count] = local_id
                cursor += point_count
            filtered.create_dataset(
                "idx",
                data=selected_lengths.reshape(1, -1).astype(np.float64),
            )
            filtered.create_dataset(
                "origNum",
                data=np.asarray([[feature_ids.size]], dtype=np.float64),
            )
            for name in ("ea_fibformat", "fourindex", "voxmm"):
                if name in parent:
                    filtered.create_dataset(name, data=parent[name][()])
        return selected_lengths, parent_count


def write_filtered_connectome(
    source_path: str | Path,
    target_path: str | Path,
    feature_ids: np.ndarray,
) -> FilteredConnectome:
    """Write one right-canonical Lead-DBS file in exact final-axis order."""

    source = Path(source_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    ids = activation_universe(feature_ids)
    if not source.is_file():
        raise ConnectomeSubsetError(f"formal connectome is missing: {source}")
    if target.exists():
        raise ConnectomeSubsetError(f"refusing to overwrite filtered connectome: {target}")

    try:
        with h5py.File(source, "r"):
            is_hdf5 = True
    except OSError:
        is_hdf5 = False
    if is_hdf5:
        lengths, parent_count = _copy_selected_hdf5(source, target, ids)
    else:
        fibers, parent_lengths = _load_parent(source)
        parent_count = int(parent_lengths.size)
        if int(np.sum(parent_lengths, dtype=np.int64)) != int(fibers.shape[1]):
            raise ConnectomeSubsetError("connectome idx does not span the point matrix")
        if np.any(ids < 1) or np.any(ids > parent_count):
            raise ConnectomeSubsetError("final fiber ID is outside the formal connectome")
        offsets = np.concatenate(
            (np.asarray([0], dtype=np.int64), np.cumsum(parent_lengths, dtype=np.int64))
        )
        lengths = parent_lengths[ids - 1]
        selected = np.empty((4, int(np.sum(lengths))), dtype=fibers.dtype)
        cursor = 0
        for local_id, feature_id in enumerate(ids.tolist(), start=1):
            start = int(offsets[feature_id - 1])
            stop = int(offsets[feature_id])
            count = stop - start
            selected[:3, cursor : cursor + count] = fibers[:3, start:stop]
            selected[3, cursor : cursor + count] = local_id
            cursor += count
        target.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(target, "x") as filtered:
            filtered.create_dataset("fibers", data=selected)
            filtered.create_dataset("idx", data=lengths.reshape(1, -1).astype(np.float64))
            filtered.create_dataset("origNum", data=np.asarray([[ids.size]], dtype=np.float64))

    return FilteredConnectome(
        path=target,
        feature_ids=ids,
        local_fiber_ids=np.arange(1, ids.size + 1, dtype=np.int64),
        point_counts=lengths,
        parent_fiber_count=parent_count,
    )


def load_local_activation_status(path: str | Path) -> dict[int, int]:
    """Read one OSS Axon_state file as local-fiber activation status."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ConnectomeSubsetError(f"Axon_state file is missing: {source}")
    if source.suffix.lower() == ".mat":
        try:
            payload = loadmat(source)
        except (OSError, ValueError, NotImplementedError) as exc:
            raise ConnectomeSubsetError(f"Axon_state MAT cannot be read: {source}") from exc
        fibers = np.asarray(payload.get("fibers"), dtype=np.float64)
    elif source.suffix.lower() == ".csv":
        try:
            fibers = np.asarray(np.loadtxt(source, delimiter=",", skiprows=1), dtype=np.float64)
        except (OSError, ValueError) as exc:
            raise ConnectomeSubsetError(f"Axon_state CSV cannot be read: {source}") from exc
    else:
        raise ConnectomeSubsetError(f"unsupported Axon_state format: {source.suffix}")
    if fibers.ndim == 1:
        fibers = fibers.reshape(1, -1)
    if fibers.ndim != 2 or fibers.shape[1] < 5:
        raise ConnectomeSubsetError("Axon_state fibers require at least five columns")
    ids_raw = fibers[:, 3]
    status_raw = fibers[:, 4]
    ids = np.rint(ids_raw).astype(np.int64)
    statuses = np.rint(status_raw).astype(np.int64)
    if (
        not np.all(np.isfinite(ids_raw))
        or not np.all(np.isfinite(status_raw))
        or not np.allclose(ids_raw, ids, rtol=0.0, atol=0.0)
        or not np.allclose(status_raw, statuses, rtol=0.0, atol=0.0)
    ):
        raise ConnectomeSubsetError("Axon_state local IDs/statuses must be finite integers")
    if not set(np.unique(statuses).tolist()).issubset({-2, -1, 0, 1}):
        raise ConnectomeSubsetError(
            "Axon_state statuses must be activated, inactive, CSF, or electrode-intersection codes"
        )
    output: dict[int, int] = {}
    for local_id in np.unique(ids):
        if local_id <= 0:
            continue
        values = np.unique(statuses[ids == local_id])
        if values.size != 1:
            raise ConnectomeSubsetError(
                f"Axon_state has inconsistent status for local fiber {local_id}"
            )
        output[int(local_id)] = int(values[0])
    if not output:
        raise ConnectomeSubsetError("Axon_state contains no positive local fiber IDs")
    return output


def aggregate_activation_probabilities(
    sample_state_paths: Iterable[str | Path],
    feature_ids: np.ndarray,
) -> np.ndarray:
    """Return exact activated-count/10 probabilities on the final fiber axis."""

    states = load_activation_state_matrix(sample_state_paths, feature_ids)
    counts = np.count_nonzero(states == 1, axis=0)
    probabilities = (counts.astype(np.float64) / 10.0).astype(np.float32)
    return validate_ten_sample_probabilities(probabilities)


def load_activation_state_matrix(
    sample_state_paths: Iterable[str | Path],
    feature_ids: np.ndarray,
) -> np.ndarray:
    """Return the exact ten-sample OSS state matrix on one ordered fiber axis."""

    paths = tuple(Path(path).expanduser().resolve() for path in sample_state_paths)
    ids = activation_universe(feature_ids)
    if len(paths) != 10 or len(set(paths)) != 10:
        raise ConnectomeSubsetError("pPAM aggregation requires ten unique samples")
    expected = set(range(1, ids.size + 1))
    states = np.empty((10, ids.size), dtype=np.int8)
    for sample_index, path in enumerate(paths, start=1):
        statuses = load_local_activation_status(path)
        if set(statuses) != expected:
            missing = sorted(expected - set(statuses))
            extra = sorted(set(statuses) - expected)
            raise ConnectomeSubsetError(
                f"sample {sample_index} local axis mismatch: missing={missing}, extra={extra}"
            )
        states[sample_index - 1, :] = np.asarray(
            [statuses[local_id] for local_id in range(1, ids.size + 1)],
            dtype=np.int8,
        )
    states.flags.writeable = False
    return states


__all__ = [
    "ConnectomeSubsetError",
    "FilteredConnectome",
    "aggregate_activation_probabilities",
    "load_activation_state_matrix",
    "load_local_activation_status",
    "write_filtered_connectome",
]
