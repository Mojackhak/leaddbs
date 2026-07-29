"""Read-only comparison of two phase-encoding preprocessing candidates."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
import yaml


class PhaseEncodingQcError(RuntimeError):
    """Raised when phase-encoding QC inputs violate the comparison contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _resolve(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _load_config(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise PhaseEncodingQcError("configuration must contain one mapping")
    allowed = {"schema_version", "output_root", "b0_threshold", "candidates"}
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise PhaseEncodingQcError(f"unknown configuration fields: {unknown}")
    if document.get("schema_version") != 1:
        raise PhaseEncodingQcError("schema_version must equal 1")
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise PhaseEncodingQcError("candidates must contain exactly two mappings")
    required = {"label", "dwi", "bval", "mask", "synthetic_b0"}
    labels: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != required:
            raise PhaseEncodingQcError(
                "each candidate must contain label, dwi, bval, mask, and synthetic_b0"
            )
        label = str(candidate["label"])
        if label in labels:
            raise PhaseEncodingQcError(f"duplicate candidate label: {label}")
        labels.add(label)
    return document


def _load_candidate(record: dict[str, Any], base: Path, threshold: float) -> dict[str, Any]:
    paths = {key: _resolve(record[key], base) for key in ("dwi", "bval", "mask", "synthetic_b0")}
    for path in paths.values():
        if not path.is_file():
            raise PhaseEncodingQcError(f"input does not exist: {path}")
    dwi_image = nib.load(paths["dwi"])
    dwi = np.asanyarray(dwi_image.dataobj, dtype=np.float32)
    if dwi.ndim != 4:
        raise PhaseEncodingQcError(f"DWI must be four-dimensional: {paths['dwi']}")
    bvals = np.asarray(np.loadtxt(paths["bval"]), dtype=np.float64).reshape(-1)
    if bvals.size != dwi.shape[3]:
        raise PhaseEncodingQcError(f"DWI/bval count mismatch: {paths['dwi']}")
    b0_indices = np.flatnonzero(bvals < threshold)
    if b0_indices.size == 0:
        raise PhaseEncodingQcError(f"no b0 volume found: {paths['dwi']}")
    mask_image = nib.load(paths["mask"])
    synthetic_image = nib.load(paths["synthetic_b0"])
    mask = np.asanyarray(mask_image.dataobj) > 0
    synthetic = np.asanyarray(synthetic_image.dataobj, dtype=np.float32)
    if mask.shape != dwi.shape[:3] or synthetic.shape != dwi.shape[:3]:
        raise PhaseEncodingQcError(f"candidate grids do not match for {record['label']}")
    for image in (mask_image, synthetic_image):
        if not np.allclose(image.affine, dwi_image.affine, atol=1e-5):
            raise PhaseEncodingQcError(f"candidate affines do not match for {record['label']}")
    return {
        "label": str(record["label"]),
        "paths": paths,
        "image": dwi_image,
        "dwi": dwi,
        "bvals": bvals,
        "b0_indices": b0_indices,
        "selected_b0": dwi[..., int(b0_indices[-1])],
        "mask": mask,
        "synthetic": synthetic,
    }


def _metrics(reference: np.ndarray, candidate: np.ndarray, mask: np.ndarray) -> dict[str, float | int]:
    valid = mask & np.isfinite(reference) & np.isfinite(candidate)
    x = reference[valid].astype(np.float64)
    y = candidate[valid].astype(np.float64)
    if x.size < 2:
        raise PhaseEncodingQcError("comparison mask contains fewer than two voxels")
    scale = max(float(np.median(np.abs(x))), np.finfo(float).eps)
    hist, _, _ = np.histogram2d(x, y, bins=64)
    probability = hist / max(float(hist.sum()), 1.0)
    px = probability.sum(axis=1)
    py = probability.sum(axis=0)
    nz = probability > 0
    mutual_information = float(
        np.sum(probability[nz] * np.log(probability[nz] / np.outer(px, py)[nz]))
    )
    return {
        "masked_voxels": int(x.size),
        "pearson_r": float(np.corrcoef(x, y)[0, 1]),
        "normalized_mae": float(np.mean(np.abs(x - y)) / scale),
        "normalized_rmse": float(np.sqrt(np.mean((x - y) ** 2)) / scale),
        "mutual_information": mutual_information,
    }


def _canonical(data: np.ndarray, image: nib.spatialimages.SpatialImage) -> np.ndarray:
    return np.asanyarray(nib.as_closest_canonical(nib.Nifti1Image(data, image.affine)).dataobj)


def _write_montage(path: Path, first: dict[str, Any], second: dict[str, Any]) -> None:
    arrays = [
        _canonical(first["selected_b0"], first["image"]),
        _canonical(second["selected_b0"], second["image"]),
        _canonical(np.abs(first["selected_b0"] - second["selected_b0"]), first["image"]),
        _canonical(first["synthetic"], first["image"]),
        _canonical(second["synthetic"], second["image"]),
        _canonical(np.abs(first["selected_b0"] - first["synthetic"]), first["image"]),
        _canonical(np.abs(second["selected_b0"] - second["synthetic"]), second["image"]),
    ]
    labels = [
        f"{first['label']} corrected b0",
        f"{second['label']} corrected b0",
        "absolute corrected-b0 difference",
        f"{first['label']} synthetic b0",
        f"{second['label']} synthetic b0",
        f"{first['label']} corrected-synthetic difference",
        f"{second['label']} corrected-synthetic difference",
    ]
    support = np.flatnonzero(np.any(arrays[0] > 0, axis=(0, 1)))
    slices = np.unique(np.linspace(int(support[0]), int(support[-1]), 10, dtype=int))
    intensity = float(np.percentile(arrays[0][arrays[0] > 0], 99.5))
    differences = np.concatenate([array[array > 0] for array in (arrays[2], arrays[5], arrays[6])])
    difference_intensity = float(np.percentile(differences, 99.0))
    figure, axes = plt.subplots(len(arrays), len(slices), figsize=(20, 13))
    for row, (array, label) in enumerate(zip(arrays, labels, strict=True)):
        for column, index in enumerate(slices):
            axis = axes[row, column]
            vmax = difference_intensity if row in {2, 5, 6} else intensity
            axis.imshow(np.rot90(array[..., index]), cmap="gray", vmin=0, vmax=max(vmax, 1.0))
            axis.axis("off")
            if row == 0:
                axis.set_title(f"z={index}", fontsize=8)
            if column == 0:
                axis.set_ylabel(label, fontsize=8)
    figure.suptitle("SNr022 phase-encoding candidate comparison", fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(path, dpi=180, facecolor="black")
    plt.close(figure)


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = _load_config(config_path)
    threshold = float(config["b0_threshold"])
    if not np.isfinite(threshold) or threshold <= 0:
        raise PhaseEncodingQcError("b0_threshold must be positive")
    output_root = _resolve(config["output_root"], config_path.parent)
    if output_root.exists():
        raise PhaseEncodingQcError(f"output already exists: {output_root}")
    first, second = [
        _load_candidate(candidate, config_path.parent, threshold)
        for candidate in config["candidates"]
    ]
    if first["dwi"].shape != second["dwi"].shape or not np.allclose(
        first["image"].affine, second["image"].affine, atol=1e-5
    ):
        raise PhaseEncodingQcError("candidate DWI grids do not match")
    if not np.array_equal(first["bvals"], second["bvals"]):
        raise PhaseEncodingQcError("candidate b-values do not match")
    mask = first["mask"] & second["mask"]
    output_root.mkdir(parents=True)
    volume_rows: list[dict[str, Any]] = []
    for index in range(first["dwi"].shape[3]):
        row = {"volume_index_one_based": index + 1, "bvalue": float(first["bvals"][index])}
        row.update(_metrics(first["dwi"][..., index], second["dwi"][..., index], mask))
        volume_rows.append(row)
    with (output_root / "per_volume_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(volume_rows[0]))
        writer.writeheader()
        writer.writerows(volume_rows)
    result = {
        "schema_version": 1,
        "b0_threshold": threshold,
        "selected_b0_index_one_based": int(first["b0_indices"][-1]) + 1,
        "candidate_labels": [first["label"], second["label"]],
        "inputs": {
            candidate["label"]: {
                key: {"path": str(path), "sha256": _sha256(path)}
                for key, path in candidate["paths"].items()
            }
            for candidate in (first, second)
        },
        "candidate_to_candidate": _metrics(first["selected_b0"], second["selected_b0"], mask),
        "candidate_to_synthetic": {
            first["label"]: _metrics(first["synthetic"], first["selected_b0"], mask),
            second["label"]: _metrics(second["synthetic"], second["selected_b0"], mask),
        },
        "per_volume_summary": {
            "mean_pearson_r": float(np.mean([row["pearson_r"] for row in volume_rows])),
            "minimum_pearson_r": float(np.min([row["pearson_r"] for row in volume_rows])),
            "mean_normalized_mae": float(np.mean([row["normalized_mae"] for row in volume_rows])),
            "maximum_normalized_mae": float(np.max([row["normalized_mae"] for row in volume_rows])),
        },
        "artifacts": {
            "per_volume_comparison": "per_volume_comparison.csv",
            "montage": "phase_encoding_comparison.png",
        },
    }
    _write_montage(output_root / "phase_encoding_comparison.png", first, second)
    (output_root / "phase_encoding_comparison.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result
