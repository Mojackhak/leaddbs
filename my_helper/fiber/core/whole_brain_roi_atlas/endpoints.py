"""Exact strict-voxel endpoint assignment for Lead-DBS HDF5 connectomes."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from my_helper.fiber.core.seed_target_connectivity.connectome import open_connectome
from my_helper.fiber.core.seed_target_connectivity.errors import ConnectomeError

from .errors import EndpointCensusError
from .models import EndpointCensus, EndpointLabelCount, ResolvedLabel


def _lookup_labels(
    points: np.ndarray,
    inverse_affine: np.ndarray,
    data: np.ndarray,
) -> np.ndarray:
    homogeneous = np.c_[points.astype(np.float64, copy=False), np.ones(points.shape[0])]
    voxel = homogeneous @ inverse_affine.T
    indices = np.floor(voxel[:, :3] + 0.5).astype(np.int64)
    inside = np.all(indices >= 0, axis=1) & np.all(indices < np.asarray(data.shape), axis=1)
    values = np.zeros(points.shape[0], dtype=np.int64)
    values[inside] = data[tuple(indices[inside].T)]
    return values


def compute_endpoint_census(
    connectome_path: Path | str,
    label_image: nib.spatialimages.SpatialImage,
    labels: tuple[ResolvedLabel, ...],
    chunk_size: int,
) -> EndpointCensus:
    """Assign both endpoints of every fiber to one exact voxel label or zero."""

    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
        raise EndpointCensusError("chunk_size must be a positive integer")
    data = np.asanyarray(label_image.dataobj)
    if data.ndim != 3 or not np.all(data == np.rint(data)):
        raise EndpointCensusError("endpoint label image must contain three-dimensional integers")
    data = data.astype(np.int64, copy=False)
    label_ids = tuple(item.label_id for item in labels)
    if len(label_ids) != len(set(label_ids)):
        raise EndpointCensusError("resolved endpoint label IDs must be unique")
    unknown = set(int(item) for item in np.unique(data) if int(item) != 0) - set(label_ids)
    if unknown:
        raise EndpointCensusError(f"label image contains unresolved label ID {min(unknown)}")
    maximum = max(label_ids, default=0)
    endpoint_counts = np.zeros(maximum + 1, dtype=np.int64)
    fiber_counts = np.zeros(maximum + 1, dtype=np.int64)
    unassigned_fiber_count = 0
    inverse_affine = np.linalg.inv(label_image.affine)
    try:
        connectome = open_connectome(connectome_path)
        for chunk in connectome.iter_chunks(chunk_size):
            first = chunk.point_offsets[:-1]
            last = chunk.point_offsets[1:] - 1
            endpoints = np.concatenate((chunk.points[first], chunk.points[last]), axis=0)
            values = _lookup_labels(endpoints, inverse_affine, data)
            fiber_count = chunk.fiber_ids.size
            first_values = values[:fiber_count]
            last_values = values[fiber_count:]
            endpoint_counts += np.bincount(values, minlength=maximum + 1)[: maximum + 1]
            fiber_counts += np.bincount(first_values, minlength=maximum + 1)[: maximum + 1]
            different = last_values != first_values
            fiber_counts += np.bincount(
                last_values[different],
                minlength=maximum + 1,
            )[: maximum + 1]
            unassigned_fiber_count += int(np.count_nonzero((first_values == 0) | (last_values == 0)))
    except ConnectomeError as exc:
        raise EndpointCensusError(str(exc)) from exc

    n_fibers = connectome.metadata.n_fibers
    n_endpoints = 2 * n_fibers
    if int(np.sum(endpoint_counts, dtype=np.int64)) != n_endpoints:
        raise EndpointCensusError("endpoint assignment totals do not reconcile")
    rows = tuple(
        EndpointLabelCount(
            label_id=label_id,
            endpoint_count=int(endpoint_counts[label_id]),
            endpoint_fraction=float(endpoint_counts[label_id] / n_endpoints),
            fiber_count=int(fiber_counts[label_id]),
            fiber_fraction=float(fiber_counts[label_id] / n_fibers),
        )
        for label_id in label_ids
    )
    return EndpointCensus(
        n_fibers=n_fibers,
        n_endpoints=n_endpoints,
        labels=rows,
        unassigned_endpoint_count=int(endpoint_counts[0]),
        unassigned_endpoint_fraction=float(endpoint_counts[0] / n_endpoints),
        unassigned_fiber_count=unassigned_fiber_count,
        unassigned_fiber_fraction=float(unassigned_fiber_count / n_fibers),
        connectome_source_hash=connectome.metadata.source_hash,
    )
