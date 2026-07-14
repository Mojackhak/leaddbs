"""One-pass segment-aware classification of TCK chunks against all targets."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import nibabel as nib
import numpy as np

from ..seed_target_connectivity.models import FiberChunk, ResolvedMask
from ..seed_target_connectivity.traversal import (
    SparseVoxelLookup,
    build_sparse_lookup,
    optimized_membership,
)

from .errors import ValidationError
from .identity import file_sha256


CLASSIFIER_NAME = "segment_aware_voxel_traversal"
CLASSIFIER_VERSION = "1"


def _resolved_mask(target_id: str, path: Path) -> ResolvedMask:
    image = nib.load(path)
    if len(image.shape) != 3:
        raise ValidationError(f"target mask must be 3D: {path}")
    data = np.asanyarray(image.dataobj) > 0
    indices = np.flatnonzero(data.reshape(-1, order="C")).astype(np.int64)
    if indices.size == 0:
        raise ValidationError(f"target mask is empty: {path}")
    indices.setflags(write=False)
    voxel_volume = float(abs(np.linalg.det(image.affine[:3, :3])))
    return ResolvedMask(
        roi_id=target_id,
        role="target",
        source_path=path,
        relative_path=path.name,
        target_group="dwi",
        source_value_type="binary",
        probability_threshold=None,
        threshold_source="binary",
        source_hash=file_sha256(path),
        voxel_count=int(indices.size),
        physical_volume_mm3=float(indices.size) * voxel_volume,
        resolved_mask_hash=file_sha256(path),
        status="valid",
        shape=tuple(int(value) for value in image.shape),
        affine=np.asarray(image.affine, dtype=np.float64),
        flat_voxel_indices=indices,
    )


def build_target_lookup(
    target_ids: Sequence[str],
    target_paths: Sequence[Path | str],
) -> SparseVoxelLookup:
    """Build one simultaneous sparse lookup for the ordered cleaned targets."""

    if len(target_ids) != len(target_paths) or not target_ids:
        raise ValidationError("target IDs and paths must be nonempty and equally sized")
    masks = [
        _resolved_mask(str(target_id), Path(path))
        for target_id, path in zip(target_ids, target_paths, strict=True)
    ]
    first = masks[0]
    for mask in masks[1:]:
        if mask.shape != first.shape or not np.allclose(
            mask.affine, first.affine, atol=1e-7, rtol=0
        ):
            raise ValidationError("all cleaned targets must share one exact DWI grid")
    return build_sparse_lookup(masks)


def streamlines_to_fiber_chunk(streamlines: Sequence[np.ndarray]) -> FiberChunk:
    """Pack one generated TCK chunk into the traversal kernel's bounded form."""

    offsets = np.zeros(len(streamlines) + 1, dtype=np.int64)
    normalized: list[np.ndarray] = []
    for index, streamline in enumerate(streamlines):
        points = np.asarray(streamline, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
            raise ValidationError("every generated streamline must have at least two 3D points")
        if not np.all(np.isfinite(points)):
            raise ValidationError("generated streamline contains nonfinite coordinates")
        normalized.append(points)
        offsets[index + 1] = offsets[index] + points.shape[0]
    points = (
        np.concatenate(normalized, axis=0)
        if normalized
        else np.empty((0, 3), dtype=np.float32)
    )
    return FiberChunk(
        fiber_ids=np.arange(len(streamlines), dtype=np.int64),
        point_offsets=offsets,
        points=points,
    )


def classify_streamlines(
    streamlines: Sequence[np.ndarray],
    lookup: SparseVoxelLookup,
) -> np.ndarray:
    """Return one boolean row per streamline and one column per ordered target."""

    if not streamlines:
        return np.zeros((0, lookup.target_count), dtype=bool)
    result = optimized_membership(streamlines_to_fiber_chunk(streamlines), lookup)
    if result.shape != (len(streamlines), lookup.target_count):
        raise ValidationError("classifier returned an invalid membership shape")
    return result
