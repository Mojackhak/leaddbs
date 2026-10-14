"""Lead-DBS MNI-to-anchor preparation and affine-aware native-DWI ROI resampling."""

from __future__ import annotations

import os
from pathlib import Path
import uuid
from typing import Any, Callable, Mapping

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform

from .discovery import load_tmat
from .errors import ToolError, ValidationError
from .identity import file_sha256, canonical_hash, callable_implementation_hash
from .models import BatchConfig, ResolvedSubjectInputs, ToolIdentity
from .state import atomic_write_json, read_json
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
    return list(dict.fromkeys(
        roi.path.resolve() for seed in config.atlas.seeds for roi in (seed, *seed.targets)
    ))


def roi_transform_inputs(subject: ResolvedSubjectInputs) -> dict[str, Any]:
    """Read only the geometry and transforms consumed by ROI resampling."""

    geometry = {}
    for name in ("b0", "anchor_native_reference"):
        image = nib.load(getattr(subject, name))
        geometry[name] = {
            "shape": list(image.shape), "affine": image.affine.tolist(),
            "qform": image.get_qform().tolist(), "sform": image.get_sform().tolist(),
            "qform_code": int(image.header["qform_code"]),
            "sform_code": int(image.header["sform_code"]),
        }
    return {
        "geometry": geometry,
        "anchor_to_b0_tmat": load_tmat(subject.anchor_to_b0_transform).tolist(),
        "mni_to_anchor_sha256": file_sha256(subject.target_to_anchor_image_deformation),
        "space": subject.target_space,
    }


def roi_implementation_hash() -> str:
    """Identify ROI computation without FOD or unrelated repository code."""

    backend = Path(__file__).resolve().parents[1] / "tracking" / "mh_fiber_prepare_mrtrix_seed_target_subject.m"
    return callable_implementation_hash(
        resample_anchor_mask_to_b0, load_tmat,
        constants={"matlab_backend": file_sha256(backend)},
    )


def target_qc(
    target_data: np.ndarray, seed_data: np.ndarray, tracking_mask: np.ndarray,
) -> dict[str, Any]:
    """Distinguish unavailable targets, valid zeros and seed overlap."""

    count = int(np.count_nonzero(target_data))
    covered = int(np.count_nonzero(target_data & tracking_mask))
    overlap = int(np.count_nonzero(target_data & seed_data))
    reason = "empty_native_roi" if count == 0 else ("outside_tracking_mask" if covered == 0 else None)
    return {
        "available": reason is None,
        "unavailable_reason": reason,
        "voxel_count": count,
        "tracking_mask_voxel_count": covered,
        "tracking_mask_fraction": covered / count if count else None,
        "partial_tracking_mask_coverage": 0 < covered < count,
        "seed_overlap_voxels": overlap,
        "seed_overlap_fraction": overlap / count if count else None,
    }


def prepare_rois(
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    preparation_dir: Path,
    matlab: ToolIdentity,
    repo_root: Path,
    memory_observer: Callable[[float], None] | None = None,
    *,
    transform_inputs: Mapping[str, Any] | None = None,
    source_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reuse each transformed ROI independently, then assemble seed-specific QC."""

    transform = dict(transform_inputs) if transform_inputs is not None else roi_transform_inputs(subject)
    implementation = roi_implementation_hash()
    sources = _unique_roi_sources(config)
    base_records: dict[str, dict[str, Any]] = {}
    source_identities: dict[str, str] = {}
    source_content_hashes: dict[str, str] = {}
    pending: list[tuple[Path, Path, Path, str]] = []
    batch_dir = preparation_dir.parent / "staging" / f"rois-{uuid.uuid4().hex}"
    for source in sources:
        source_hash = source_hashes[str(source)] if source_hashes is not None else file_sha256(source)
        source_content_hashes[str(source)] = source_hash
        identity = canonical_hash({
            "source": source_hash, "transform": transform,
            "implementation": implementation, "matlab": matlab.version,
        })
        source_identities[str(source)] = identity
        destination = preparation_dir / "rois" / identity
        if destination.exists():
            record = read_json(destination / "roi.json")
            if record.get("identity") != identity:
                raise ValidationError(f"invalid ROI preparation blocks reuse: {destination}")
            for name in ("anchor", "dwi"):
                path = Path(record[f"{name}_path"])
                if not path.is_file() or file_sha256(path) != record[f"{name}_hash"]:
                    raise ValidationError(f"ROI preparation artifact mismatch: {path}")
            base_records[str(source)] = {**record, "source": str(source)}
        else:
            staging = batch_dir / identity
            if not staging.exists():
                staging.mkdir(parents=True, exist_ok=False)
                pending.append((source, staging, destination, identity))

    matlab_result: dict[str, Any] = {"status": "reused", "roi_count": 0}
    if pending:
        manifest_path = batch_dir / "matlab_roi_manifest.json"
        result_path = batch_dir / "matlab_roi_result.json"
        atomic_write_json(manifest_path, {
            "subject_id": subject.subject_id, "subject_dir": str(subject.subject_dir),
            "anchor_native_reference": str(subject.anchor_native_reference),
            "rois": [{"source": str(src), "anchor_output": str(staging / "anchor.nii")}
                     for src, staging, _, _ in pending],
            "result_path": str(result_path),
        })
        batch = (
            f"addpath(genpath('{_matlab_quote(repo_root)}')); "
            "mh_fiber_prepare_mrtrix_seed_target_subject("
            f"'{_matlab_quote(manifest_path)}');"
        )
        run_command(
            [matlab.executable, "-noFigureWindows", "-nosplash", "-batch", batch],
            log_path=batch_dir / "matlab_roi_preparation.log",
            memory_observer=memory_observer,
        )
        if not result_path.is_file():
            raise ToolError(f"MATLAB did not write its ROI result: {result_path}")
        matlab_result = read_json(result_path)
        if matlab_result.get("status") != "complete":
            raise ToolError(f"MATLAB ROI preparation did not report complete: {result_path}")
        for source, staging, destination, identity in pending:
            anchor = staging / "anchor.nii"
            dwi = staging / "dwi.nii.gz"
            voxel_count = resample_anchor_mask_to_b0(anchor, subject.b0, subject.anchor_to_b0_transform, dwi)
            record = {
                "identity": identity, "source": str(source),
                "anchor_path": str(destination / anchor.name), "anchor_hash": file_sha256(anchor),
                "dwi_path": str(destination / dwi.name), "dwi_hash": file_sha256(dwi),
                "dwi_voxel_count": voxel_count,
            }
            atomic_write_json(staging / "roi.json", record)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
            base_records[str(source)] = record

    records_by_identity = {record["identity"]: record for record in base_records.values()}
    for source, identity in source_identities.items():
        base_records[source] = {**records_by_identity[identity], "source": source,
                                "source_hash": source_content_hashes[source]}

    tracking_image = nib.load(subject.tracking_mask)
    tracking_mask = np.asanyarray(tracking_image.dataobj) > 0
    voxel_volume = float(abs(np.linalg.det(tracking_image.affine[:3, :3])))
    seed_masks: dict[str, np.ndarray] = {}
    for seed in config.atlas.seeds:
        record = base_records[str(seed.path.resolve())]
        data = np.asanyarray(nib.load(record["dwi_path"]).dataobj) > 0
        if not np.any(data) or not np.any(data & tracking_mask):
            raise ValidationError(f"seed is empty or outside the tracking mask: {seed.key}")
        seed_masks[seed.key] = data

    seed_records: dict[str, Any] = {}
    for seed in config.atlas.seeds:
        record = base_records[str(seed.path.resolve())]
        seed_path = Path(record["dwi_path"])
        seed_data = seed_masks[seed.key]
        peers = [other for other in config.atlas.seeds if other.side == seed.side]
        targets = []
        for target in seed.targets:
            base = base_records[str(target.path.resolve())]
            target_path = Path(base["dwi_path"])
            target_data = np.asanyarray(nib.load(target_path).dataobj) > 0
            qc = target_qc(target_data, seed_data, tracking_mask)
            qc["volume_mm3"] = qc["voxel_count"] * voxel_volume
            peer_overlap = {
                other.key: int(np.count_nonzero(target_data & seed_masks[other.key]))
                for other in peers
            }
            removed = 0
            if not config.tracking.unrestricted_targets:
                if not qc["available"]:
                    raise ValidationError(f"target unavailable for {seed.key}: {target.key}: {qc['unavailable_reason']}")
                clean_identity = canonical_hash({"target": base["dwi_hash"], "seed": record["dwi_hash"],
                                                 "code": callable_implementation_hash(clean_target_mask, constants={})})
                cleaned = preparation_dir / "cleaned" / clean_identity / "target.nii.gz"
                metadata_path = cleaned.parent / "cleaned.json"
                if cleaned.parent.exists():
                    metadata = read_json(metadata_path, default={})
                    if (metadata.get("identity") != clean_identity or not cleaned.is_file()
                            or file_sha256(cleaned) != metadata.get("sha256")):
                        raise ValidationError(f"invalid cleaned target blocks reuse: {cleaned}")
                    removed = qc["seed_overlap_voxels"]
                else:
                    _, removed = clean_target_mask(target_path, seed_path, cleaned)
                    atomic_write_json(metadata_path, {"identity": clean_identity, "sha256": file_sha256(cleaned)})
                target_path = cleaned
                qc["voxel_count"] = int(np.count_nonzero(np.asanyarray(nib.load(cleaned).dataobj)))
            targets.append({
                "id": target.roi_id, "side": target.side, "key": target.key,
                "source_path": str(target.path), "path": str(target_path),
                "source_sha256": base["source_hash"],
                "hash": file_sha256(target_path), **qc,
                "removed_seed_overlap_voxels": removed,
                "peer_seed_overlap_voxels": peer_overlap,
                "comparison_eligible": qc["available"] and not any(peer_overlap.values()),
                "relative_side": ("midline" if target.side == "midline" else
                                  "ipsilateral" if seed.side == target.side else "contralateral"),
            })
        seed_records[seed.key] = {
            "id": seed.roi_id, "side": seed.side, "key": seed.key,
            "source_path": str(seed.path), "path": str(seed_path),
            "source_sha256": record["source_hash"],
            "hash": record["dwi_hash"], "voxel_count": int(np.count_nonzero(seed_data)),
            "volume_mm3": int(np.count_nonzero(seed_data)) * voxel_volume,
            "seed_overlap_voxels": {
                other.key: int(np.count_nonzero(seed_data & other_data))
                for other in config.atlas.seeds
                if other.key != seed.key
                for other_data in (seed_masks[other.key],)
            },
            "targets": targets,
        }
    return {"base_rois": base_records, "seeds": seed_records, "matlab_result": matlab_result}
