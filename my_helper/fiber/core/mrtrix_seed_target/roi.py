"""Lead-DBS MNI-to-anchor preparation and affine-aware native-DWI ROI resampling."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform

from .discovery import load_tmat
from .errors import ToolError, ValidationError
from .identity import file_sha256
from .models import BatchConfig, ResolvedSubjectInputs, ToolIdentity
from .state import atomic_write_json
from .tools import run_command


def _matlab_quote(path: Path | str) -> str:
    return str(path).replace("'", "''")


def resample_anchor_mask_to_b0(
    anchor_mask_path: Path | str,
    b0_reference_path: Path | str,
    tmat_path: Path | str,
    output_path: Path | str,
) -> int:
    """Apply a world-coordinate anchor-to-b0 tmat with nearest-neighbor sampling."""

    anchor = nib.load(anchor_mask_path)
    b0 = nib.load(b0_reference_path)
    if len(anchor.shape) != 3 or len(b0.shape) != 3:
        raise ValidationError("anchor mask and b0 reference must both be 3D")
    source = np.asanyarray(anchor.dataobj) > 0
    tmat = load_tmat(tmat_path)
    output_to_input = np.linalg.inv(tmat @ anchor.affine) @ b0.affine
    resampled = affine_transform(
        source.astype(np.uint8),
        matrix=output_to_input[:3, :3],
        offset=output_to_input[:3, 3],
        output_shape=tuple(int(value) for value in b0.shape),
        order=0,
        mode="constant",
        cval=0,
        prefilter=False,
    ).astype(np.uint8)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = b0.header.copy()
    header.set_data_dtype(np.uint8)
    image = nib.Nifti1Image(resampled, b0.affine, header=header)
    qform, qcode = b0.get_qform(coded=True)
    sform, scode = b0.get_sform(coded=True)
    if qform is not None:
        image.set_qform(qform, int(qcode))
    if sform is not None:
        image.set_sform(sform, int(scode))
    nib.save(image, destination)
    return int(np.count_nonzero(resampled))


def clean_target_mask(
    target_path: Path | str,
    seed_path: Path | str,
    output_path: Path | str,
) -> tuple[int, int]:
    """Write `target AND NOT seed` on the exact final DWI grid."""

    target = nib.load(target_path)
    seed = nib.load(seed_path)
    if target.shape != seed.shape or not np.allclose(
        target.affine, seed.affine, atol=1e-7, rtol=0
    ):
        raise ValidationError("seed and target masks do not share the exact final grid")
    target_data = np.asanyarray(target.dataobj) > 0
    seed_data = np.asanyarray(seed.dataobj) > 0
    overlap = int(np.count_nonzero(target_data & seed_data))
    cleaned = (target_data & ~seed_data).astype(np.uint8)
    count = int(np.count_nonzero(cleaned))
    if count == 0:
        raise ValidationError(
            f"target becomes empty after seed subtraction: {target_path}"
        )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = target.header.copy()
    header.set_data_dtype(np.uint8)
    image = nib.Nifti1Image(cleaned, target.affine, header=header)
    qform, qcode = target.get_qform(coded=True)
    sform, scode = target.get_sform(coded=True)
    if qform is not None:
        image.set_qform(qform, int(qcode))
    if sform is not None:
        image.set_sform(sform, int(scode))
    nib.save(image, destination)
    return count, overlap


def _unique_roi_sources(config: BatchConfig) -> list[Path]:
    sources: list[Path] = []
    seen: set[Path] = set()
    for seed in config.atlas.seeds:
        for roi in (seed, *seed.targets):
            source = roi.path.resolve()
            if source not in seen:
                seen.add(source)
                sources.append(source)
    return sources


def prepare_rois(
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    preparation_dir: Path,
    matlab: ToolIdentity,
    repo_root: Path,
    memory_observer: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Transform all unique atlas ROIs and build seed-specific cleaned targets."""

    anchor_dir = preparation_dir / "rois" / "anchorNative"
    dwi_dir = preparation_dir / "rois" / "dwi"
    log_dir = preparation_dir / "logs"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    dwi_dir.mkdir(parents=True, exist_ok=True)
    sources = _unique_roi_sources(config)
    source_records: list[dict[str, str]] = []
    source_to_anchor: dict[Path, Path] = {}
    source_to_dwi: dict[Path, Path] = {}
    for index, source in enumerate(sources):
        token = file_sha256(source)[:16]
        anchor_output = anchor_dir / f"roi-{index:03d}-{token}.nii"
        dwi_output = dwi_dir / f"roi-{index:03d}-{token}.nii.gz"
        source_to_anchor[source] = anchor_output
        source_to_dwi[source] = dwi_output
        source_records.append(
            {
                "source": str(source),
                "anchor_output": str(anchor_output),
            }
        )

    manifest_path = preparation_dir / "matlab_roi_manifest.json"
    result_path = preparation_dir / "matlab_roi_result.json"
    atomic_write_json(
        manifest_path,
        {
            "subject_id": subject.subject_id,
            "subject_dir": str(subject.subject_dir),
            "anchor_native_reference": str(subject.anchor_native_reference),
            "rois": source_records,
            "result_path": str(result_path),
        },
    )
    batch = (
        f"addpath(genpath('{_matlab_quote(repo_root)}')); "
        "mh_fiber_prepare_mrtrix_seed_target_subject("
        f"'{_matlab_quote(manifest_path)}');"
    )
    run_command(
        [
            matlab.executable,
            "-noFigureWindows",
            "-nosplash",
            "-batch",
            batch,
        ],
        log_path=log_dir / "matlab_roi_preparation.log",
        memory_observer=memory_observer,
    )
    if not result_path.is_file():
        raise ToolError(f"MATLAB did not write its ROI result: {result_path}")
    try:
        matlab_result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ToolError(f"invalid MATLAB ROI result {result_path}: {exc}") from exc
    if matlab_result.get("status") != "complete":
        raise ToolError(f"MATLAB ROI preparation did not report complete: {result_path}")

    base_records: dict[str, dict[str, Any]] = {}
    for source in sources:
        anchor_output = source_to_anchor[source]
        if not anchor_output.is_file():
            raise ToolError(f"MATLAB did not create transformed ROI: {anchor_output}")
        voxel_count = resample_anchor_mask_to_b0(
            anchor_output,
            subject.b0,
            subject.anchor_to_b0_transform,
            source_to_dwi[source],
        )
        if voxel_count == 0:
            raise ValidationError(
                f"ROI is empty after transformation to native DWI: {source}"
            )
        base_records[str(source)] = {
            "source": str(source),
            "anchor_path": str(anchor_output),
            "dwi_path": str(source_to_dwi[source]),
            "dwi_voxel_count": voxel_count,
            "dwi_hash": file_sha256(source_to_dwi[source]),
        }

    seed_records: dict[str, Any] = {}
    for seed in config.atlas.seeds:
        seed_path = source_to_dwi[seed.path.resolve()]
        target_records: list[dict[str, Any]] = []
        for target in seed.targets:
            clean_path = (
                preparation_dir
                / "rois"
                / "cleaned"
                / seed.side
                / seed.roi_id
                / target.side
                / f"{target.roi_id}.nii.gz"
            )
            voxel_count, removed_overlap = clean_target_mask(
                source_to_dwi[target.path.resolve()], seed_path, clean_path
            )
            target_records.append(
                {
                    "id": target.roi_id,
                    "side": target.side,
                    "key": target.key,
                    "source_path": str(target.path),
                    "path": str(clean_path),
                    "voxel_count": voxel_count,
                    "removed_seed_overlap_voxels": removed_overlap,
                    "hash": file_sha256(clean_path),
                }
            )
        seed_records[seed.key] = {
            "id": seed.roi_id,
            "side": seed.side,
            "key": seed.key,
            "source_path": str(seed.path),
            "path": str(seed_path),
            "voxel_count": base_records[str(seed.path.resolve())]["dwi_voxel_count"],
            "hash": file_sha256(seed_path),
            "targets": target_records,
        }
    return {
        "base_rois": base_records,
        "seeds": seed_records,
        "matlab_result": matlab_result,
    }
