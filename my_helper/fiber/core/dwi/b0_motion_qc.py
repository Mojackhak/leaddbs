"""Read-only multi-b0 motion QC with an explicit reference selection."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any
import uuid

from dipy.align.imaffine import (
    AffineRegistration,
    MutualInformationMetric,
    transform_centers_of_mass,
)
from dipy.align.transforms import RigidTransform3D
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from scipy.spatial.transform import Rotation
import yaml


class B0MotionQcError(RuntimeError):
    """Raised when the b0 motion-QC contract is violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_config(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise B0MotionQcError(f"cannot read configuration {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise B0MotionQcError("configuration must contain one YAML mapping")
    allowed = {"schema_version", "output_root", "reference", "subjects"}
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise B0MotionQcError(f"unknown configuration fields: {unknown}")
    if document.get("schema_version") != 1:
        raise B0MotionQcError("schema_version must equal 1")
    reference = document.get("reference")
    if not isinstance(reference, dict) or set(reference) != {"strategy", "b0_threshold"}:
        raise B0MotionQcError(
            "reference must contain exactly strategy and b0_threshold"
        )
    if reference["strategy"] != "last":
        raise B0MotionQcError("only the explicit last-b0 strategy is supported")
    threshold = float(reference["b0_threshold"])
    if not math.isfinite(threshold) or threshold <= 0:
        raise B0MotionQcError("reference.b0_threshold must be positive")
    subjects = document.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise B0MotionQcError("subjects must be a nonempty sequence")
    seen: set[str] = set()
    for record in subjects:
        if not isinstance(record, dict) or set(record) != {"id", "dwi", "bval"}:
            raise B0MotionQcError(
                "each subject must contain exactly id, dwi, and bval"
            )
        subject_id = str(record["id"])
        if subject_id in seen:
            raise B0MotionQcError(f"duplicate subject id: {subject_id}")
        seen.add(subject_id)
    return document


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _load_subject(record: dict[str, Any], base: Path, threshold: float) -> dict[str, Any]:
    dwi_path = _resolve_path(str(record["dwi"]), base)
    bval_path = _resolve_path(str(record["bval"]), base)
    for path in (dwi_path, bval_path):
        if not path.is_file():
            raise B0MotionQcError(f"input does not exist: {path}")
    image = nib.load(dwi_path)
    data = np.asanyarray(image.dataobj, dtype=np.float32)
    if data.ndim != 4:
        raise B0MotionQcError(f"DWI must be four-dimensional: {dwi_path}")
    bvals = np.asarray(np.loadtxt(bval_path), dtype=np.float64).reshape(-1)
    if bvals.size != data.shape[3]:
        raise B0MotionQcError(
            f"DWI/bval count mismatch for {record['id']}: {data.shape[3]} vs {bvals.size}"
        )
    b0_indices = np.flatnonzero(bvals < threshold)
    if b0_indices.size < 2:
        raise B0MotionQcError(
            f"{record['id']} requires at least two b0 volumes; found {b0_indices.size}"
        )
    return {
        "id": str(record["id"]),
        "dwi_path": dwi_path,
        "bval_path": bval_path,
        "image": image,
        "data": data,
        "bvals": bvals,
        "b0_indices": b0_indices,
        "reference_index": int(b0_indices[-1]),
    }


def _masked_metrics(static: np.ndarray, moving: np.ndarray) -> dict[str, float]:
    finite = np.isfinite(static) & np.isfinite(moving)
    positive = static[finite & (static > 0)]
    if positive.size == 0:
        raise B0MotionQcError("reference b0 contains no positive finite voxels")
    mask = finite & (static > np.percentile(positive, 20.0))
    x = static[mask].astype(np.float64)
    y = moving[mask].astype(np.float64)
    correlation = float(np.corrcoef(x, y)[0, 1]) if x.size > 1 else float("nan")
    scale = float(np.median(np.abs(x)))
    normalized_mae = float(np.mean(np.abs(x - y)) / max(scale, np.finfo(float).eps))
    hist, _, _ = np.histogram2d(x, y, bins=64)
    probability = hist / max(float(hist.sum()), 1.0)
    px = probability.sum(axis=1)
    py = probability.sum(axis=0)
    nz = probability > 0
    mutual_information = float(
        np.sum(
            probability[nz]
            * np.log(
                probability[nz]
                / np.outer(px, py)[nz]
            )
        )
    )
    return {
        "masked_voxels": int(mask.sum()),
        "pearson_r": correlation,
        "normalized_mae": normalized_mae,
        "mutual_information": mutual_information,
    }


def _rigid_register(static: np.ndarray, moving: np.ndarray, affine: np.ndarray):
    center = transform_centers_of_mass(static, affine, moving, affine)
    registration = AffineRegistration(
        metric=MutualInformationMetric(nbins=32, sampling_proportion=None),
        level_iters=[500, 100, 25],
        sigmas=[3.0, 1.0, 0.0],
        factors=[4, 2, 1],
    )
    rigid = registration.optimize(
        static,
        moving,
        RigidTransform3D(),
        params0=None,
        static_grid2world=affine,
        moving_grid2world=affine,
        starting_affine=center.affine,
    )
    return rigid.transform(moving).astype(np.float32), np.asarray(rigid.affine)


def _transform_summary(matrix: np.ndarray) -> dict[str, Any]:
    rotation = Rotation.from_matrix(matrix[:3, :3])
    return {
        "moving_world_to_reference_world": matrix.tolist(),
        "translation_mm": matrix[:3, 3].tolist(),
        "translation_norm_mm": float(np.linalg.norm(matrix[:3, 3])),
        "rotation_xyz_degrees": rotation.as_euler("xyz", degrees=True).tolist(),
        "rotation_magnitude_degrees": float(np.degrees(rotation.magnitude())),
    }


def _display_volume(data: np.ndarray, affine: np.ndarray) -> np.ndarray:
    image = nib.Nifti1Image(data.astype(np.float32), affine)
    return np.asanyarray(nib.as_closest_canonical(image).dataobj)


def _slice_indices(reference: np.ndarray, count: int = 10) -> np.ndarray:
    support = np.flatnonzero(np.any(reference > 0, axis=(0, 1)))
    if support.size == 0:
        return np.linspace(0, reference.shape[2] - 1, count, dtype=int)
    lo, hi = int(support[0]), int(support[-1])
    return np.unique(np.linspace(lo, hi, count, dtype=int))


def _write_montage(
    path: Path,
    subject_id: str,
    moving: np.ndarray,
    reference: np.ndarray,
    registered: np.ndarray,
    affine: np.ndarray,
    moving_index: int,
    reference_index: int,
) -> None:
    moving_c = _display_volume(moving, affine)
    reference_c = _display_volume(reference, affine)
    registered_c = _display_volume(registered, affine)
    difference_c = np.abs(reference_c - registered_c)
    slices = _slice_indices(reference_c)
    arrays = (moving_c, reference_c, registered_c, difference_c)
    labels = (
        f"raw b0 volume {moving_index + 1}",
        f"reference b0 volume {reference_index + 1}",
        "rigidly registered moving b0",
        "absolute post-registration difference",
    )
    vmax = float(np.percentile(reference_c[reference_c > 0], 99.5))
    diff_vmax = float(np.percentile(difference_c[difference_c > 0], 99.0))
    figure, axes = plt.subplots(len(arrays), len(slices), figsize=(2.0 * len(slices), 7.5))
    for row, (array, label) in enumerate(zip(arrays, labels, strict=True)):
        for column, index in enumerate(slices):
            axis = axes[row, column]
            upper = diff_vmax if row == 3 else vmax
            axis.imshow(np.rot90(array[:, :, index]), cmap="gray", vmin=0, vmax=max(upper, 1.0))
            axis.axis("off")
            if row == 0:
                axis.set_title(f"z={index}", fontsize=8)
            if column == 0:
                axis.set_ylabel(label, fontsize=8)
    figure.suptitle(f"{subject_id}: last b0 is the explicit reference", fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(path, dpi=180, facecolor="black")
    plt.close(figure)


def _write_nifti(path: Path, data: np.ndarray, source: nib.spatialimages.SpatialImage) -> None:
    header = source.header.copy()
    header.set_data_dtype(np.float32)
    nib.save(nib.Nifti1Image(data.astype(np.float32), source.affine, header), path)


def _run_subject(subject: dict[str, Any], output_root: Path) -> dict[str, Any]:
    subject_dir = output_root / subject["id"]
    if subject_dir.exists():
        raise B0MotionQcError(f"output already exists: {subject_dir}")
    staging = output_root / f".{subject['id']}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    try:
        reference_index = subject["reference_index"]
        reference = subject["data"][:, :, :, reference_index]
        reference_path = staging / f"b0-volume-{reference_index + 1:03d}-reference.nii.gz"
        _write_nifti(reference_path, reference, subject["image"])
        comparisons: list[dict[str, Any]] = []
        for moving_index in subject["b0_indices"][:-1]:
            moving_index = int(moving_index)
            moving = subject["data"][:, :, :, moving_index]
            registered, matrix = _rigid_register(reference, moving, subject["image"].affine)
            moving_path = staging / f"b0-volume-{moving_index + 1:03d}-raw.nii.gz"
            registered_path = staging / f"b0-volume-{moving_index + 1:03d}-registered-to-reference.nii.gz"
            difference_path = staging / f"b0-volume-{moving_index + 1:03d}-absolute-difference.nii.gz"
            montage_path = staging / f"b0-volume-{moving_index + 1:03d}-motion-qc.png"
            _write_nifti(moving_path, moving, subject["image"])
            _write_nifti(registered_path, registered, subject["image"])
            _write_nifti(difference_path, np.abs(reference - registered), subject["image"])
            _write_montage(
                montage_path,
                subject["id"],
                moving,
                reference,
                registered,
                subject["image"].affine,
                moving_index,
                reference_index,
            )
            comparisons.append(
                {
                    "moving_volume_index_one_based": moving_index + 1,
                    "reference_volume_index_one_based": reference_index + 1,
                    "metrics_before": _masked_metrics(reference, moving),
                    "metrics_after": _masked_metrics(reference, registered),
                    "rigid_transform": _transform_summary(matrix),
                    "artifacts": {
                        "moving_b0": moving_path.name,
                        "registered_b0": registered_path.name,
                        "absolute_difference": difference_path.name,
                        "montage": montage_path.name,
                    },
                }
            )
        manifest = {
            "schema_version": 1,
            "subject_id": subject["id"],
            "reference_strategy": "last",
            "b0_indices_one_based": [int(value) + 1 for value in subject["b0_indices"]],
            "selected_reference_index_one_based": reference_index + 1,
            "inputs": {
                "dwi": {
                    "path": str(subject["dwi_path"]),
                    "sha256": _sha256(subject["dwi_path"]),
                },
                "bval": {
                    "path": str(subject["bval_path"]),
                    "sha256": _sha256(subject["bval_path"]),
                },
            },
            "reference_b0_sha256": _sha256(reference_path),
            "comparisons": comparisons,
        }
        (staging / "b0_motion_qc.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, subject_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def run(config_path: Path | str) -> dict[str, Any]:
    """Run the configured read-only b0 motion QC and return a summary."""

    source = Path(config_path).expanduser().resolve()
    document = _load_config(source)
    output_root = _resolve_path(str(document["output_root"]), source.parent)
    output_root.mkdir(parents=True, exist_ok=True)
    threshold = float(document["reference"]["b0_threshold"])
    subjects = [
        _load_subject(record, source.parent, threshold)
        for record in document["subjects"]
    ]
    manifests = [_run_subject(subject, output_root) for subject in subjects]
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        for comparison in manifest["comparisons"]:
            before = comparison["metrics_before"]
            after = comparison["metrics_after"]
            transform = comparison["rigid_transform"]
            rows.append(
                {
                    "subject_id": manifest["subject_id"],
                    "moving_volume_one_based": comparison["moving_volume_index_one_based"],
                    "reference_volume_one_based": comparison["reference_volume_index_one_based"],
                    "translation_norm_mm": transform["translation_norm_mm"],
                    "rotation_magnitude_degrees": transform["rotation_magnitude_degrees"],
                    "pearson_r_before": before["pearson_r"],
                    "pearson_r_after": after["pearson_r"],
                    "normalized_mae_before": before["normalized_mae"],
                    "normalized_mae_after": after["normalized_mae"],
                    "mutual_information_before": before["mutual_information"],
                    "mutual_information_after": after["mutual_information"],
                }
            )
    summary_path = output_root / "b0_motion_qc_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "status": "complete",
        "configuration": str(source),
        "output_root": str(output_root),
        "reference_strategy": "last",
        "subjects": [manifest["subject_id"] for manifest in manifests],
        "summary_csv": str(summary_path),
    }
    (output_root / "run_manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
