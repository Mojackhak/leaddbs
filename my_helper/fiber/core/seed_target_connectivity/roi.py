"""Binary and probabilistic NIfTI ROI resolution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np

from .atlas import discover_targets
from .errors import ROIResolutionError
from .identity import canonical_hash, sha256_file
from .models import ConnectivityConfig, ResolvedAtlas, ResolvedMask, TargetSource


_BINARY_TOLERANCE = 1e-6


def _mask_hash(mask: np.ndarray, affine: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(mask.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(affine, dtype="<f8").tobytes(order="C"))
    digest.update(np.packbits(mask.reshape(-1, order="C"), bitorder="little").tobytes())
    return digest.hexdigest()


def _load_image(path: Path, roi_id: str) -> tuple[np.ndarray, np.ndarray]:
    try:
        image = nib.load(str(path))
        if len(image.shape) != 3:
            raise ROIResolutionError(f"ROI {roi_id!r} must be a three-dimensional NIfTI")
        data = np.asarray(image.dataobj, dtype=np.float32)
        affine = np.asarray(image.affine, dtype=np.float64)
    except ROIResolutionError:
        raise
    except Exception as exc:
        raise ROIResolutionError(f"failed to read ROI {roi_id!r} from {path}: {exc}") from exc
    if not np.all(np.isfinite(data)):
        raise ROIResolutionError(f"ROI {roi_id!r} contains nonfinite values")
    return data, affine


def _classify(data: np.ndarray, roi_id: str) -> Literal["binary", "probabilistic"]:
    nonzero = data[data != 0]
    if nonzero.size == 0 or np.all(np.abs(nonzero - 1.0) <= _BINARY_TOLERANCE):
        return "binary"
    if np.any(data < 0) or np.any(data > 1):
        raise ROIResolutionError(f"ROI {roi_id!r} values must lie in [0, 1]")
    if np.any((data > 0) & (data < 1)):
        return "probabilistic"
    raise ROIResolutionError(f"ROI {roi_id!r} is neither binary nor probabilistic")


def _resolve(
    *,
    path: Path,
    roi_id: str,
    role: Literal["seed", "target"],
    relative_path: str,
    target_group: str,
    threshold: float | None,
    threshold_source: str,
) -> ResolvedMask:
    data, affine = _load_image(path, roi_id)
    source_value_type = _classify(data, roi_id)
    if source_value_type == "binary":
        resolved = data > 0
        applied_threshold = None
        applied_source = "not_applicable"
    else:
        if threshold is None:
            raise ROIResolutionError(f"probabilistic ROI {roi_id!r} requires an explicit probability threshold")
        resolved = data >= threshold
        applied_threshold = float(threshold)
        applied_source = threshold_source
    flat_indices = np.flatnonzero(resolved.reshape(-1, order="C")).astype(np.int64)
    flat_indices.setflags(write=False)
    voxel_count = int(flat_indices.size)
    if role == "seed" and voxel_count == 0:
        raise ROIResolutionError(f"seed ROI {roi_id!r} resolves to an empty mask")
    voxel_volume = float(abs(np.linalg.det(affine[:3, :3])))
    if not np.isfinite(voxel_volume) or voxel_volume <= 0:
        raise ROIResolutionError(f"ROI {roi_id!r} has an invalid affine voxel volume")
    affine.setflags(write=False)
    status = "valid" if voxel_count else "empty_after_threshold"
    return ResolvedMask(
        roi_id=roi_id,
        role=role,
        source_path=path.resolve(),
        relative_path=relative_path,
        target_group=target_group,
        source_value_type=source_value_type,
        probability_threshold=applied_threshold,
        threshold_source=applied_source,
        source_hash=sha256_file(path),
        voxel_count=voxel_count,
        physical_volume_mm3=voxel_count * voxel_volume,
        resolved_mask_hash=_mask_hash(resolved, affine),
        status=status,
        shape=tuple(int(value) for value in data.shape),
        affine=affine,
        flat_voxel_indices=flat_indices,
    )


def resolve_seed(path: Path | str, config: ConnectivityConfig) -> ResolvedMask:
    """Resolve exactly one seed NIfTI using the seed threshold contract."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ROIResolutionError(f"seed ROI is not an existing file: {source}")
    return _resolve(
        path=source,
        roi_id="seed",
        role="seed",
        relative_path=source.name,
        target_group="",
        threshold=config.seed.probability_threshold,
        threshold_source="seed.probability_threshold",
    )


def _target_threshold(source: TargetSource, config: ConnectivityConfig) -> tuple[float | None, str]:
    if source.target_id in config.targets.roi_thresholds:
        return (
            float(config.targets.roi_thresholds[source.target_id]),
            f"targets.roi_thresholds[{source.target_id}]",
        )
    if config.targets.probability_threshold is not None:
        return float(config.targets.probability_threshold), "targets.probability_threshold"
    return None, "unresolved"


def resolve_atlas(atlas_root: Path | str, config: ConnectivityConfig) -> ResolvedAtlas:
    """Discover and resolve an ordered target atlas."""
    root = Path(atlas_root).expanduser().resolve()
    targets: list[ResolvedMask] = []
    for source in discover_targets(root):
        threshold, threshold_source = _target_threshold(source, config)
        targets.append(
            _resolve(
                path=source.path,
                roi_id=source.target_id,
                role="target",
                relative_path=source.relative_path,
                target_group=source.target_group,
                threshold=threshold,
                threshold_source=threshold_source,
            )
        )
    identity_rows = [
        {
            "target_id": target.roi_id,
            "relative_path": target.relative_path,
            "source_hash": target.source_hash,
            "resolved_mask_hash": target.resolved_mask_hash,
            "source_value_type": target.source_value_type,
            "probability_threshold": target.probability_threshold,
            "threshold_source": target.threshold_source,
            "status": target.status,
        }
        for target in targets
    ]
    return ResolvedAtlas(root=root, targets=tuple(targets), atlas_hash=canonical_hash(identity_rows))
