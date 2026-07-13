"""Synthetic fixture builders for seed-target connectivity tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np

from my_helper.fiber.core.seed_target_connectivity.identity import canonical_hash
from my_helper.fiber.core.seed_target_connectivity.config import effective_config, resolve_config
from my_helper.fiber.core.seed_target_connectivity.models import (
    ConnectomeMetadata,
    FiberChunk,
    ResolvedAtlas,
    ResolvedMask,
)


def effective_test_config(**sections):
    """Build one schema-v2 effective config for unit-level algorithm tests."""

    document = {
        "schema_version": 2,
        "inputs": {
            "target_atlas_root": "/synthetic-atlas",
            "seed_rois": {"seed": "/synthetic-seed.nii.gz"},
            "connectome": "/synthetic-connectome",
        },
        "output": {
            "output_root": "/synthetic-results",
            "run_name": "synthetic",
            "cache_root": "/synthetic-cache",
        },
    }
    document.update(sections)
    return effective_config(resolve_config(document), "seed")


def write_mask(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray | None = None,
) -> Path:
    """Write a small NIfTI mask and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_affine = np.eye(4, dtype=np.float64) if affine is None else np.asarray(affine, dtype=np.float64)
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), resolved_affine), str(path))
    return path


def line(*points: tuple[float, float, float]) -> np.ndarray:
    """Build one float32 streamline."""
    return np.asarray(points, dtype=np.float32)


def write_hdf5_connectome(path: Path, streamlines: list[np.ndarray]) -> Path:
    """Write a minimal Lead-DBS MATLAB v7.3-style connectome."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lengths = np.asarray([streamline.shape[0] for streamline in streamlines], dtype=np.float64)
    point_count = int(np.sum(lengths))
    fibers = np.empty((4, point_count), dtype=np.float32)
    cursor = 0
    for fiber_id, streamline in enumerate(streamlines, start=1):
        stop = cursor + streamline.shape[0]
        fibers[0:3, cursor:stop] = np.asarray(streamline, dtype=np.float32).T
        fibers[3, cursor:stop] = float(fiber_id)
        cursor = stop
    with h5py.File(path, "w") as handle:
        handle.create_dataset("idx", data=lengths.reshape(1, -1))
        handle.create_dataset("fibers", data=fibers)
    return path


def mutate_fourth_row(path: Path, value: float, point_index: int = 0) -> None:
    """Replace one stored point-level canonical ID."""
    with h5py.File(path, "r+") as handle:
        handle["fibers"][3, point_index] = value


def resolved_mask(
    voxels: list[tuple[int, int, int]],
    *,
    shape: tuple[int, int, int] = (4, 4, 4),
    affine: np.ndarray | None = None,
    roi_id: str = "target",
    role: str = "target",
) -> ResolvedMask:
    """Build one in-memory resolved mask for geometry tests."""
    resolved_affine = np.eye(4, dtype=np.float64) if affine is None else np.asarray(affine, dtype=np.float64)
    if voxels:
        coordinates = np.asarray(voxels, dtype=np.int64).T
        flat = np.ravel_multi_index(coordinates, shape, order="C").astype(np.int64)
        flat.sort()
    else:
        flat = np.empty(0, dtype=np.int64)
    flat.setflags(write=False)
    resolved_affine.setflags(write=False)
    return ResolvedMask(
        roi_id=roi_id,
        role=role,
        source_path=Path(f"/{roi_id}.nii.gz"),
        relative_path=f"{roi_id}.nii.gz",
        target_group="synthetic",
        source_value_type="binary",
        probability_threshold=None,
        threshold_source="not_applicable",
        source_hash="a" * 64,
        voxel_count=int(flat.size),
        physical_volume_mm3=float(flat.size * abs(np.linalg.det(resolved_affine[:3, :3]))),
        resolved_mask_hash=(roi_id.encode("utf-8").hex() + "0" * 64)[:64],
        status="valid" if flat.size else "empty_after_threshold",
        shape=shape,
        affine=resolved_affine,
        flat_voxel_indices=flat,
    )


def fiber_chunk(streamlines: list[np.ndarray], first_id: int = 1) -> FiberChunk:
    """Build one in-memory fiber chunk."""
    lengths = np.asarray([streamline.shape[0] for streamline in streamlines], dtype=np.int64)
    offsets = np.empty(lengths.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])
    points = np.concatenate(streamlines, axis=0).astype(np.float32)
    ids = np.arange(first_id, first_id + lengths.size, dtype=np.int64)
    return FiberChunk(fiber_ids=ids, point_offsets=offsets, points=points)


def resolved_atlas(masks: list[ResolvedMask]) -> ResolvedAtlas:
    """Build one in-memory resolved atlas with a content-derived identity."""
    atlas_hash = canonical_hash(
        [
            {
                "roi_id": mask.roi_id,
                "mask_hash": mask.resolved_mask_hash,
                "voxels": mask.flat_voxel_indices.tolist(),
            }
            for mask in masks
        ]
    )
    return ResolvedAtlas(root=Path("/synthetic-atlas"), targets=tuple(masks), atlas_hash=atlas_hash)


class RecordingAdapter:
    """Small deterministic in-memory adapter that records traversal calls."""

    def __init__(self, streamlines: list[np.ndarray], identity: str = "c" * 64):
        self.streamlines = [np.asarray(streamline, dtype=np.float32) for streamline in streamlines]
        self.iteration_count = 0
        n_points = sum(streamline.shape[0] for streamline in self.streamlines)
        self._metadata = ConnectomeMetadata(
            connectome_id="synthetic",
            source_path=Path("/synthetic/data.mat"),
            source_hash="d" * 64,
            geometry_hash=identity,
            ordered_fiber_id_hash=hashlib.sha256(
                np.arange(1, len(streamlines) + 1, dtype="<i8").tobytes()
            ).hexdigest(),
            connectome_identity=canonical_hash({"geometry": identity, "count": len(streamlines)}),
            identity_source="synthetic_one_based_order",
            adapter_name="recording_adapter",
            adapter_version="1",
            n_fibers=len(streamlines),
            n_points=n_points,
        )

    @property
    def metadata(self) -> ConnectomeMetadata:
        return self._metadata

    def iter_chunks(self, chunk_size: int):
        self.iteration_count += 1
        for start in range(0, len(self.streamlines), chunk_size):
            yield fiber_chunk(
                self.streamlines[start : start + chunk_size],
                first_id=start + 1,
            )
