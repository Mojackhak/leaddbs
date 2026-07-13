"""Export resolved integer labels as Lead-DBS binary ROI files."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from .errors import PublicationError
from .models import ResolvedLabel, RoiArtifact


def _relative_path(label: ResolvedLabel) -> Path:
    side = {"L": "lh", "R": "rh", "M": "midline"}[label.hemisphere]
    if label.tissue_type == "white_matter":
        return Path(".qc") / "white_matter" / side / label.paired_filename
    return Path(side) / label.paired_filename


def _binary_image(
    mask: np.ndarray,
    reference: nib.spatialimages.SpatialImage,
) -> nib.Nifti1Image:
    header = reference.header.copy()
    header.set_data_dtype(np.uint8)
    image = nib.Nifti1Image(mask.astype(np.uint8), reference.affine, header=header)
    qform, qcode = reference.get_qform(coded=True)
    sform, scode = reference.get_sform(coded=True)
    image.set_qform(qform if qform is not None else reference.affine, code=int(qcode))
    image.set_sform(sform if sform is not None else reference.affine, code=int(scode))
    return image


def export_binary_rois(
    label_image: nib.spatialimages.SpatialImage,
    labels: tuple[ResolvedLabel, ...],
    staging_root: Path | str,
) -> tuple[RoiArtifact, ...]:
    """Write one binary NIfTI per resolved label under a staging root."""

    root = Path(staging_root)
    for directory in ("lh", "rh", "midline", "mixed"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    data = np.asanyarray(label_image.dataobj).astype(np.uint16, copy=False)
    voxel_volume = float(abs(np.linalg.det(label_image.affine[:3, :3])))
    occupied_paths: set[Path] = set()
    artifacts: list[RoiArtifact] = []
    for label in labels:
        relative = _relative_path(label)
        if relative in occupied_paths:
            raise PublicationError(f"multiple labels resolve to the same ROI path: {relative}")
        occupied_paths.add(relative)
        mask = data == label.label_id
        voxel_count = int(np.count_nonzero(mask))
        if voxel_count == 0:
            raise PublicationError(f"resampled label {label.label_id} is empty")
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(_binary_image(mask, label_image), path)
        artifacts.append(
            RoiArtifact(
                label_id=label.label_id,
                relative_path=relative.as_posix(),
                voxel_count=voxel_count,
                volume_mm3=voxel_count * voxel_volume,
            )
        )
    return tuple(artifacts)
