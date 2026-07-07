#!/usr/bin/env python3
"""Generate basic streamline voxel-density caches for final normative-fiber models."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import h5py
import nibabel as nib
import numpy as np

from stnsnr_four_model_final_reporting import FORMAL_ROOT, count_by
from stnsnr_four_model_readiness import DEFAULT_CANONICAL_ASSET_ROOT
from stnsnr_hf_normative_fiber_smoke import CONNECTOMES
from stnsnr_io import iso_now, read_csv, write_csv, write_json


SUMMARY_FIELDS = [
    "model_id",
    "branch_dir",
    "density_cache_status",
    "label_cache_status",
    "n_selected_fibers",
    "n_density_voxels_nonzero",
    "density_map",
    "weighted_density_map",
    "positive_weighted_density_map",
    "negative_weighted_density_map",
    "density_cache_npz",
    "label_cache_csv",
    "label_cache_manifest_json",
    "manifest_json",
]
LABEL_CACHE_FIELDS = [
    "atlas_name",
    "roi_name",
    "side",
    "role",
    "category",
    "mask_path",
    "n_label_voxels",
    "n_overlap_voxels",
    "support_voxel_fraction",
    "label_coverage_fraction",
    "density_sum_in_label",
    "weighted_density_sum_in_label",
    "positive_weighted_density_sum_in_label",
    "negative_weighted_density_sum_in_label",
]
CONNECTED_REGION_ATLAS_NAMES = [
    "STN-connected regions",
    "SNr-connected regions",
    "STNSNr-connected regions",
]


def load_fiber_weights(weights_csv: Path) -> dict[int, float]:
    rows = read_csv(Path(weights_csv))
    weights: dict[int, float] = {}
    for row in rows:
        if str(row.get("is_candidate", "")).lower() not in {"true", "1", "yes"}:
            continue
        fiber_id_text = row.get("fiber_id", "")
        if not fiber_id_text:
            continue
        weight_text = row.get("M_HF", "") or row.get("M_ULF", "")
        if not weight_text:
            continue
        try:
            fiber_id = int(float(fiber_id_text))
            weight = float(weight_text)
        except ValueError:
            continue
        if np.isfinite(weight):
            weights[fiber_id] = weight
    return weights


def fiber_offsets(lengths: np.ndarray, selected_fiber_ids: list[int]) -> dict[int, tuple[int, int]]:
    lengths_arr = np.asarray(lengths, dtype=np.int64).reshape(-1)
    starts = np.concatenate([[0], np.cumsum(lengths_arr[:-1], dtype=np.int64)])
    offsets: dict[int, tuple[int, int]] = {}
    for fiber_id in selected_fiber_ids:
        index = fiber_id - 1
        if index < 0 or index >= lengths_arr.size:
            continue
        start = int(starts[index])
        stop = start + int(lengths_arr[index])
        offsets[fiber_id] = (start, stop)
    return offsets


def unique_inside_voxels(xyz: np.ndarray, template: nib.Nifti1Image) -> np.ndarray:
    if xyz.size == 0:
        return np.array([], dtype=np.int64)
    vox = nib.affines.apply_affine(np.linalg.inv(template.affine), xyz)
    ijk = np.rint(vox).astype(np.int64)
    shape = np.asarray(template.shape[:3], dtype=np.int64)
    inside = np.all((ijk >= 0) & (ijk < shape), axis=1)
    if not np.any(inside):
        return np.array([], dtype=np.int64)
    flat = np.ravel_multi_index(ijk[inside].T, tuple(int(item) for item in shape))
    return np.unique(flat.astype(np.int64))


def save_float_image(path: Path, flat: np.ndarray, template: nib.Nifti1Image) -> None:
    data = np.asarray(flat, dtype=np.float32).reshape(template.shape[:3])
    image = nib.Nifti1Image(data, template.affine, template.header)
    image.set_data_dtype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(image, str(path))


def default_connected_region_label_atlas_dirs(asset_root: Path) -> list[Path]:
    atlas_root = Path(asset_root) / "templates/space/MNI152NLin2009bAsym/atlases"
    return [atlas_root / name for name in CONNECTED_REGION_ATLAS_NAMES]


def _resolve_roi_mask_path(atlas_dir: Path, row: dict[str, str]) -> Path:
    output_file = str(row.get("output_file", "") or "")
    if output_file:
        path = Path(output_file)
        if path.is_file():
            return path
        fallback = atlas_dir / path.name
        if fallback.is_file():
            return fallback
    side = str(row.get("side", "") or "").lower()
    roi_name = str(row.get("roi_name", "") or "")
    side_dir = {"l": "lh", "left": "lh", "r": "rh", "right": "rh"}.get(side, side)
    for suffix in (".nii.gz", ".nii"):
        fallback = atlas_dir / side_dir / f"{roi_name}{suffix}"
        if fallback.is_file():
            return fallback
    return Path(output_file)


def build_connected_region_label_cache(
    *,
    branch_dir: Path,
    output_prefix: str,
    template: nib.Nifti1Image,
    nonzero_flat: np.ndarray,
    density: np.ndarray,
    weighted: np.ndarray,
    positive: np.ndarray,
    negative: np.ndarray,
    label_atlas_dirs: list[Path],
) -> dict[str, str]:
    label_rows: list[dict[str, Any]] = []
    n_support = int(nonzero_flat.size)
    shape = tuple(int(item) for item in template.shape[:3])
    for atlas_dir in [Path(item) for item in label_atlas_dirs]:
        manifest_csv = atlas_dir / "roi_manifest.csv"
        if not manifest_csv.is_file():
            continue
        for roi_row in read_csv(manifest_csv):
            mask_path = _resolve_roi_mask_path(atlas_dir, roi_row)
            if not mask_path.is_file():
                continue
            mask_img = nib.load(str(mask_path))
            if tuple(int(item) for item in mask_img.shape[:3]) != shape:
                continue
            mask_flat = np.asarray(mask_img.dataobj).reshape(-1) > 0
            n_label_voxels = int(np.count_nonzero(mask_flat))
            if n_label_voxels == 0:
                overlap = np.zeros(nonzero_flat.shape, dtype=bool)
            else:
                overlap = mask_flat[nonzero_flat]
            n_overlap = int(np.count_nonzero(overlap))
            overlap_indices = nonzero_flat[overlap]
            density_sum = float(np.sum(density[overlap_indices])) if n_overlap else 0.0
            weighted_sum = float(np.sum(weighted[overlap_indices])) if n_overlap else 0.0
            positive_sum = float(np.sum(positive[overlap_indices])) if n_overlap else 0.0
            negative_sum = float(np.sum(negative[overlap_indices])) if n_overlap else 0.0
            label_rows.append(
                {
                    "atlas_name": roi_row.get("atlas_name", atlas_dir.name),
                    "roi_name": roi_row.get("roi_name", ""),
                    "side": roi_row.get("side", ""),
                    "role": roi_row.get("role", ""),
                    "category": roi_row.get("category", ""),
                    "mask_path": str(mask_path),
                    "n_label_voxels": n_label_voxels,
                    "n_overlap_voxels": n_overlap,
                    "support_voxel_fraction": float(n_overlap / n_support) if n_support else 0.0,
                    "label_coverage_fraction": float(n_overlap / n_label_voxels) if n_label_voxels else 0.0,
                    "density_sum_in_label": density_sum,
                    "weighted_density_sum_in_label": weighted_sum,
                    "positive_weighted_density_sum_in_label": positive_sum,
                    "negative_weighted_density_sum_in_label": negative_sum,
                }
            )

    label_cache_csv = Path(branch_dir) / f"{output_prefix}_fiber_label_cache.csv"
    label_manifest_json = Path(branch_dir) / f"{output_prefix}_fiber_label_cache_manifest.json"
    write_csv(label_cache_csv, label_rows, LABEL_CACHE_FIELDS)
    write_json(
        label_manifest_json,
        {
            "generated_at": iso_now(),
            "label_cache_status": "complete_connected_region_label_cache",
            "scope": "connected_region_density_overlap_labels_only",
            "does_not_compute": ["fdr", "endpoint_enrichment", "plain_touched_streamline_background"],
            "label_atlas_dirs": [str(Path(item)) for item in label_atlas_dirs],
            "n_rows": len(label_rows),
            "outputs": {
                "label_cache_csv": str(label_cache_csv),
                "label_cache_manifest_json": str(label_manifest_json),
            },
        },
        add_code_provenance=True,
    )
    return {
        "label_cache_status": "complete_connected_region_label_cache",
        "label_cache_csv": str(label_cache_csv),
        "label_cache_manifest_json": str(label_manifest_json),
    }


def build_density_cache_for_branch(
    *,
    model_id: str,
    branch_dir: Path,
    weights_csv: Path,
    data_mat: Path,
    template_path: Path,
    output_prefix: str,
    label_atlas_dirs: list[Path] | None = None,
) -> dict[str, str]:
    branch_dir = Path(branch_dir)
    weights = load_fiber_weights(Path(weights_csv))
    if not weights:
        raise RuntimeError(f"no candidate fiber weights found in {weights_csv}")
    selected_fiber_ids = sorted(weights)
    template = nib.load(str(template_path))
    n_voxels = int(np.prod(template.shape[:3]))
    density = np.zeros(n_voxels, dtype=np.float32)
    weighted = np.zeros(n_voxels, dtype=np.float32)
    positive = np.zeros(n_voxels, dtype=np.float32)
    negative = np.zeros(n_voxels, dtype=np.float32)

    with h5py.File(data_mat, "r") as handle:
        lengths = np.asarray(handle["idx"][0, :], dtype=np.int64)
        offsets = fiber_offsets(lengths, selected_fiber_ids)
        fibers = handle["fibers"]
        for fiber_id in selected_fiber_ids:
            if fiber_id not in offsets:
                continue
            start, stop = offsets[fiber_id]
            xyz = np.asarray(fibers[0:3, start:stop], dtype=np.float32).T
            flat = unique_inside_voxels(xyz, template)
            if flat.size == 0:
                continue
            weight = float(weights[fiber_id])
            density[flat] += 1.0
            weighted[flat] += weight
            if weight >= 0:
                positive[flat] += weight
            else:
                negative[flat] += weight

    density_map = branch_dir / f"{output_prefix}_fiber_density_map.nii.gz"
    weighted_density_map = branch_dir / f"{output_prefix}_fiber_unthresholded_weighted_density.nii.gz"
    positive_weighted_density_map = branch_dir / f"{output_prefix}_fiber_positive_weighted_density.nii.gz"
    negative_weighted_density_map = branch_dir / f"{output_prefix}_fiber_negative_weighted_density.nii.gz"
    density_cache_npz = branch_dir / f"{output_prefix}_streamline_voxel_density_cache.npz"
    manifest_json = branch_dir / f"{output_prefix}_fiber_density_cache_manifest.json"

    save_float_image(density_map, density, template)
    save_float_image(weighted_density_map, weighted, template)
    save_float_image(positive_weighted_density_map, positive, template)
    save_float_image(negative_weighted_density_map, negative, template)
    nonzero_flat = np.flatnonzero(density > 0).astype(np.int64)
    np.savez_compressed(
        density_cache_npz,
        nonzero_flat_indices=nonzero_flat,
        density=density[nonzero_flat].astype(np.float32),
        weighted_density=weighted[nonzero_flat].astype(np.float32),
        positive_weighted_density=positive[nonzero_flat].astype(np.float32),
        negative_weighted_density=negative[nonzero_flat].astype(np.float32),
        selected_fiber_ids=np.asarray(selected_fiber_ids, dtype=np.int64),
    )
    label_outputs = {
        "label_cache_status": "not_run_no_label_atlas_dirs",
        "label_cache_csv": "",
        "label_cache_manifest_json": "",
    }
    existing_label_dirs = [Path(item) for item in (label_atlas_dirs or []) if Path(item).is_dir()]
    if existing_label_dirs:
        label_outputs = build_connected_region_label_cache(
            branch_dir=branch_dir,
            output_prefix=output_prefix,
            template=template,
            nonzero_flat=nonzero_flat,
            density=density,
            weighted=weighted,
            positive=positive,
            negative=negative,
            label_atlas_dirs=existing_label_dirs,
        )
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "model_id": model_id,
            "density_cache_status": "complete_basic_density_cache",
            "label_cache_status": label_outputs["label_cache_status"],
            "scope": "basic_streamline_voxel_density_with_optional_connected_region_label_cache",
            "does_not_compute": ["oss_dbs", "spatial_jitter", "fdr", "endpoint_enrichment"],
            "inputs": {
                "weights_csv": str(weights_csv),
                "data_mat": str(data_mat),
                "template_path": str(template_path),
                "label_atlas_dirs": [str(item) for item in existing_label_dirs],
            },
            "n_selected_fibers": len(selected_fiber_ids),
            "n_density_voxels_nonzero": int(nonzero_flat.size),
            "outputs": {
                "density_map": str(density_map),
                "weighted_density_map": str(weighted_density_map),
                "positive_weighted_density_map": str(positive_weighted_density_map),
                "negative_weighted_density_map": str(negative_weighted_density_map),
                "density_cache_npz": str(density_cache_npz),
                "label_cache_csv": label_outputs["label_cache_csv"],
                "label_cache_manifest_json": label_outputs["label_cache_manifest_json"],
                "manifest_json": str(manifest_json),
            },
        },
        add_code_provenance=True,
    )
    return {
        "density_map": str(density_map),
        "weighted_density_map": str(weighted_density_map),
        "positive_weighted_density_map": str(positive_weighted_density_map),
        "negative_weighted_density_map": str(negative_weighted_density_map),
        "density_cache_npz": str(density_cache_npz),
        "manifest_json": str(manifest_json),
        "n_selected_fibers": str(len(selected_fiber_ids)),
        "n_density_voxels_nonzero": str(int(nonzero_flat.size)),
        **label_outputs,
    }


def connectome_data_mat_for_manifest(manifest_path: str, asset_root: Path) -> Path:
    manifest_text = str(manifest_path)
    for spec in CONNECTOMES.values():
        if str(spec["slug"]) in manifest_text:
            return Path(asset_root) / spec["path"]
    raise ValueError(f"could not infer connectome from manifest path: {manifest_path}")


def target_prefix_and_weights(branch_dir: Path, model_id: str) -> tuple[str, Path]:
    if model_id.startswith("B_"):
        return "normative_HF", branch_dir / "normative_HF_fiber_weights.csv"
    if model_id.startswith("D_"):
        return "normative_ULF", branch_dir / "normative_ULF_fiber_weights.csv"
    raise ValueError(f"not a normative-fiber model id: {model_id}")


def build_density_cache_from_final_report(
    *,
    final_report_csv: Path,
    asset_root: Path,
    output_dir: Path,
    model_ids: set[str] | None = None,
    label_atlas_dirs: list[Path] | None = None,
) -> dict[str, str]:
    final_rows = read_csv(Path(final_report_csv))
    if not final_rows:
        raise RuntimeError(f"no final report rows found in {final_report_csv}")
    template_path = Path(asset_root) / "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz"
    atlas_dirs = label_atlas_dirs
    if atlas_dirs is None:
        atlas_dirs = default_connected_region_label_atlas_dirs(Path(asset_root))
    summary_rows: list[dict[str, Any]] = []
    for row in final_rows:
        model_id = row.get("model_id", "")
        if row.get("analysis_family") != "normative_fiber":
            continue
        if model_ids is not None and model_id not in model_ids:
            continue
        manifest_path = row.get("latest_manifest", "")
        branch_dir = Path(manifest_path).parent
        output_prefix, weights_csv = target_prefix_and_weights(branch_dir, model_id)
        data_mat = connectome_data_mat_for_manifest(manifest_path, Path(asset_root))
        outputs = build_density_cache_for_branch(
            model_id=model_id,
            branch_dir=branch_dir,
            weights_csv=weights_csv,
            data_mat=data_mat,
            template_path=template_path,
            output_prefix=output_prefix,
            label_atlas_dirs=atlas_dirs,
        )
        summary_rows.append(
            {
                "model_id": model_id,
                "branch_dir": str(branch_dir),
                "density_cache_status": "complete_basic_density_cache",
                "label_cache_status": outputs["label_cache_status"],
                **outputs,
            }
        )
    output_dir = Path(output_dir)
    summary_csv = output_dir / "normative_fiber_density_cache_summary.csv"
    manifest_json = output_dir / "normative_fiber_density_cache_manifest.json"
    write_csv(summary_csv, summary_rows, SUMMARY_FIELDS)
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "inputs": {
                "final_report_csv": str(final_report_csv),
                "asset_root": str(asset_root),
                "label_atlas_dirs": [str(Path(item)) for item in atlas_dirs],
            },
            "n_rows": len(summary_rows),
            "density_cache_status_counts": count_by(summary_rows, "density_cache_status"),
            "label_cache_status_counts": count_by(summary_rows, "label_cache_status"),
            "outputs": {
                "summary_csv": str(summary_csv),
                "manifest_json": str(manifest_json),
            },
        },
        add_code_provenance=True,
    )
    return {"summary_csv": str(summary_csv), "manifest_json": str(manifest_json)}


def run_density_cache(args: argparse.Namespace) -> int:
    label_atlas_dirs = [Path(item).expanduser().resolve() for item in args.label_atlas_dir] if args.label_atlas_dir else None
    outputs = build_density_cache_from_final_report(
        final_report_csv=Path(args.final_report_csv).expanduser().resolve(),
        asset_root=Path(args.asset_root).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
        model_ids=set(args.model_id) if args.model_id else None,
        label_atlas_dirs=label_atlas_dirs,
    )
    print(f"Normative-fiber density cache summary: {outputs['summary_csv']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-report-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_final_report.csv"),
        help="Final report CSV with selected final model manifests.",
    )
    parser.add_argument(
        "--asset-root",
        default=str(DEFAULT_CANONICAL_ASSET_ROOT),
        help="Lead-DBS asset root containing connectomes and templates.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "normative_fiber_density_cache"),
        help="Density-cache summary output directory.",
    )
    parser.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Optional normative-fiber model ID to process. May be passed multiple times. Defaults to all normative-fiber rows.",
    )
    parser.add_argument(
        "--label-atlas-dir",
        action="append",
        default=[],
        help="Optional connected-region atlas directory for density-label overlap caches. May be passed multiple times.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_density_cache(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
