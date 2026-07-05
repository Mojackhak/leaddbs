#!/usr/bin/env python3
"""HF direct voxel primary observed smoke driver."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pandas as pd
from scipy.ndimage import map_coordinates

from stnsnr_four_model_readiness import (
    DEFAULT_CANONICAL_ASSET_ROOT,
    DEFAULT_CLINICAL_ROOT,
    DEFAULT_MATLAB,
    DEFAULT_VAL_ROOT,
    HF_DEFAULT_SCALES,
    RAW_CLINICAL_FILE,
    STIM_FILE,
    STIM_SHEET,
    detect_asset_root,
    expected_efield_paths,
    infer_scale_direction,
    repo_root_from_file,
    sanitize,
)
from stnsnr_four_model_stats import (
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    fit_linear_prediction,
    mean_map_score,
    partial_spearman_matrix,
    regression_metrics,
    suprathreshold_matrix,
)


@dataclass(frozen=True)
class SubjectRecord:
    subject_id: str
    y_post: float
    y_base: float


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return slug or "scale"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def matlab_string(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_command(cmd: list[str], timeout_s: int | None = None) -> dict[str, Any]:
    started = iso_now()
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
    return {
        "cmd": cmd,
        "started_at": started,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def load_subject_records(clinical_root: Path, scale: str) -> list[SubjectRecord]:
    raw_path = clinical_root / RAW_CLINICAL_FILE
    raw_df = pd.read_excel(raw_path)
    subset = raw_df[raw_df["Scale"].astype(str).eq(scale)].copy()
    subset = subset.sort_values("ID")
    records: list[SubjectRecord] = []
    for _, row in subset.iterrows():
        if pd.isna(row["Value"]) or pd.isna(row["Baseline"]):
            continue
        records.append(SubjectRecord(sanitize(row["ID"]), float(row["Value"]), float(row["Baseline"])))
    if len(records) < 12:
        raise RuntimeError(f"scale {scale!r} has only {len(records)} valid subjects")
    return records


def load_stim_table(clinical_root: Path) -> pd.DataFrame:
    stim_path = clinical_root / STIM_FILE
    return pd.read_excel(stim_path, sheet_name=STIM_SHEET)


def filter_hf_stn_rows(stim_df: pd.DataFrame, subject_ids: set[str]) -> pd.DataFrame:
    rows = stim_df[
        stim_df["ID"].astype(str).isin(subject_ids)
        & stim_df["Phase"].astype(str).eq("3m")
        & stim_df["Protocol"].astype(str).eq("STN")
        & stim_df["Target"].astype(str).eq("STN")
    ].copy()
    rows["Frequency"] = pd.to_numeric(rows["Frequency"], errors="coerce")
    rows = rows[rows["Frequency"] >= 100].copy()
    return rows


def unique_existing_efields(rows: pd.DataFrame, derivatives_root: Path, side: str) -> list[Path]:
    paths: list[Path] = []
    for _, row in rows[rows["Side"].astype(str).eq(side)].iterrows():
        for path in expected_efield_paths(derivatives_root, row):
            if path.is_file():
                paths.append(path)
    unique = sorted({path.resolve() for path in paths})
    if not unique:
        return []
    return unique


def collect_side_field_paths(
    records: list[SubjectRecord],
    stim_rows: pd.DataFrame,
    derivatives_root: Path,
) -> tuple[dict[tuple[str, str], list[Path]], list[dict[str, Any]]]:
    side_paths: dict[tuple[str, str], list[Path]] = {}
    qc_rows: list[dict[str, Any]] = []
    for record in records:
        subject_rows = stim_rows[stim_rows["ID"].astype(str).eq(record.subject_id)]
        if subject_rows.empty:
            raise RuntimeError(f"no HF STN stimulation rows for {record.subject_id}")
        for side in ["L", "R"]:
            paths = unique_existing_efields(subject_rows, derivatives_root, side)
            if not paths:
                raise RuntimeError(f"missing e-field paths for {record.subject_id} side {side}")
            side_paths[(record.subject_id, side)] = paths
            grids = []
            for path in paths:
                img = nib.load(str(path))
                grids.append({"path": str(path), "shape": list(img.shape), "affine": np.round(img.affine, 6).tolist()})
            qc_rows.append(
                {
                    "subject_id": record.subject_id,
                    "side": side,
                    "n_source_paths": len(paths),
                    "source_paths": [str(path) for path in paths],
                    "grids": grids,
                    "max_combination_space": "right_canonical_sampled_feature_space",
                }
            )
    return side_paths, qc_rows


def flip_left_fields_with_matlab(
    repo_root: Path,
    matlab_bin: Path,
    side_paths: dict[tuple[str, str], list[Path]],
    preprocess_dir: Path,
    force: bool,
) -> tuple[dict[str, list[Path]], dict[str, Any]]:
    flipped_dir = preprocess_dir / "flipped_left_to_right"
    flipped_dir.mkdir(parents=True, exist_ok=True)
    left_to_right: dict[str, list[Path]] = {}
    jobs: list[tuple[Path, Path]] = []
    for subject_id, side in sorted(side_paths):
        if side != "L":
            continue
        outputs: list[Path] = []
        for source_idx, input_path in enumerate(side_paths[(subject_id, side)], start=1):
            output_path = flipped_dir / f"{subject_id}_hemi-L_src-{source_idx:02d}_to_R.nii"
            outputs.append(output_path)
            if force or not output_path.is_file():
                jobs.append((input_path, output_path))
        left_to_right[subject_id] = outputs

    if not jobs:
        return left_to_right, {"status": "SKIPPED", "detail": "all flipped files already exist", "n_jobs": 0}

    script_path = preprocess_dir / "run_left_to_right_flip.m"
    lines = [
        f"cd({matlab_string(repo_root)});",
        "addpath(genpath(pwd));",
        "try",
    ]
    for input_path, output_path in jobs:
        lines.append(f"ea_flip_lr_nonlinear({matlab_string(input_path)}, {matlab_string(output_path)});")
    lines.extend(
        [
            "catch ME",
            "disp(getReport(ME, 'extended'));",
            "exit(1);",
            "end",
            "exit(0);",
        ]
    )
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = run_command([str(matlab_bin), "-batch", f"run({matlab_string(script_path)})"], timeout_s=None)
    status = "PASS" if result["returncode"] == 0 and all(out.is_file() for _, out in jobs) else "FAIL"
    result.update({"status": status, "n_jobs": len(jobs), "script_path": str(script_path)})
    if status != "PASS":
        raise RuntimeError("MATLAB left-to-right flip failed; see manifest for stdout/stderr")
    return left_to_right, result


def right_brainmask_voxels(asset_root: Path) -> tuple[nib.Nifti1Image, np.ndarray, np.ndarray, np.ndarray]:
    brainmask_path = asset_root / "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz"
    ref_img = nib.load(str(brainmask_path))
    mask = np.asarray(ref_img.dataobj) > 0
    ijk = np.argwhere(mask)
    xyz = nib.affines.apply_affine(ref_img.affine, ijk)
    right = xyz[:, 0] > 0
    ijk = ijk[right].astype(np.int32)
    xyz = xyz[right].astype(np.float32)
    flat = np.ravel_multi_index((ijk[:, 0], ijk[:, 1], ijk[:, 2]), ref_img.shape).astype(np.int64)
    return ref_img, ijk, xyz, flat


def sample_image_at_xyz(path: Path, xyz: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    img = nib.load(str(path))
    data = np.asarray(img.dataobj, dtype=np.float32)
    inv_affine = np.linalg.inv(img.affine)
    vox = nib.affines.apply_affine(inv_affine, xyz)
    inside = (
        (vox[:, 0] >= 0)
        & (vox[:, 0] <= data.shape[0] - 1)
        & (vox[:, 1] >= 0)
        & (vox[:, 1] <= data.shape[1] - 1)
        & (vox[:, 2] >= 0)
        & (vox[:, 2] <= data.shape[2] - 1)
    )
    values = np.zeros(xyz.shape[0], dtype=np.float32)
    if np.any(inside):
        sampled = map_coordinates(
            data,
            [vox[inside, 0], vox[inside, 1], vox[inside, 2]],
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        ).astype(np.float32)
        values[inside] = sampled
    negative = values < 0
    min_before = float(values.min()) if values.size else 0.0
    n_negative = int(np.count_nonzero(negative))
    if n_negative:
        values[negative] = 0
    qc = {
        "path": str(path),
        "shape": list(img.shape),
        "inside_voxels": int(np.count_nonzero(inside)),
        "nonzero_sampled_voxels": int(np.count_nonzero(values)),
        "negative_clamped_voxels": n_negative,
        "min_before_clamp": min_before,
        "max_after_clamp": float(values.max()) if values.size else 0.0,
    }
    return values, qc


def sample_max_at_xyz(paths: list[Path], xyz: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if not paths:
        raise ValueError("no images provided for sampled max")
    max_values = np.zeros(xyz.shape[0], dtype=np.float32)
    qc_rows: list[dict[str, Any]] = []
    for path in paths:
        values, qc = sample_image_at_xyz(path, xyz)
        max_values = np.maximum(max_values, values)
        qc_rows.append(qc)
    return max_values, qc_rows


def build_exposure_matrix(
    records: list[SubjectRecord],
    side_paths: dict[tuple[str, str], list[Path]],
    flipped_left_paths: dict[str, list[Path]],
    xyz: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    x = np.zeros((len(records), xyz.shape[0]), dtype=np.float32)
    qc_rows: list[dict[str, Any]] = []
    for row_idx, record in enumerate(records):
        right_values, right_qc = sample_max_at_xyz(side_paths[(record.subject_id, "R")], xyz)
        left_values, left_qc = sample_max_at_xyz(flipped_left_paths[record.subject_id], xyz)
        x[row_idx] = (right_values + left_values) / 2.0
        qc_rows.append(
            {
                "subject_id": record.subject_id,
                "right": right_qc,
                "left_to_right": left_qc,
                "bilateral_nonzero_voxels": int(np.count_nonzero(x[row_idx])),
                "bilateral_max": float(np.max(x[row_idx])),
                "bilateral_sum": float(np.sum(x[row_idx], dtype=np.float64)),
            }
        )
    return x, qc_rows


def write_nifti_from_flat(
    path: Path,
    ref_img: nib.Nifti1Image,
    flat_indices: np.ndarray,
    values: np.ndarray,
    dtype: np.dtype | str,
    fill_value: float,
) -> None:
    data = np.full(ref_img.shape, fill_value, dtype=dtype)
    flat_data = data.reshape(-1)
    flat_data[flat_indices] = np.asarray(values, dtype=dtype)
    out = nib.Nifti1Image(data, ref_img.affine, ref_img.header)
    out.header.set_data_dtype(np.dtype(dtype))
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out, str(path))


def fit_baseline_only(train_y: np.ndarray, train_base: np.ndarray, test_base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train_design = np.column_stack([np.ones(train_y.shape[0]), train_base])
    test_design = np.column_stack([np.ones(test_base.shape[0]), test_base])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return test_design @ beta, beta


def run_hf_direct_voxel_smoke(args: argparse.Namespace) -> int:
    started = time.time()
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    derivatives_root = Path(args.leaddbs_derivatives).expanduser().resolve()
    matlab_bin = Path(args.matlab_bin).expanduser().resolve()
    scale = args.scale
    scale_slug = slugify(scale)
    output_root = Path(args.output_root).expanduser().resolve() / scale_slug
    preprocess_dir = output_root / "preprocess"
    branch_dir = output_root / "tau200" / "partial_spearman"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    branch_dir.mkdir(parents=True, exist_ok=True)

    records = load_subject_records(clinical_root, scale)
    subject_ids = {record.subject_id for record in records}
    stim_rows = filter_hf_stn_rows(load_stim_table(clinical_root), subject_ids)
    if stim_rows["ID"].nunique() != len(records):
        missing_subjects = sorted(subject_ids - set(stim_rows["ID"].astype(str).unique()))
        raise RuntimeError("missing HF STN stimulation rows for subjects: " + ", ".join(missing_subjects))

    scale_direction, scale_direction_source = infer_scale_direction(scale)
    if scale_direction not in {"lower", "higher"}:
        raise RuntimeError(f"unknown scale direction for {scale!r}; provide explicit direction before running")

    side_paths, side_field_qc = collect_side_field_paths(records, stim_rows, derivatives_root)
    flipped_left_paths, flip_result = flip_left_fields_with_matlab(
        repo_root=asset_root,
        matlab_bin=matlab_bin,
        side_paths=side_paths,
        preprocess_dir=preprocess_dir,
        force=args.force_flip,
    )

    ref_img, right_ijk, right_xyz, right_flat = right_brainmask_voxels(asset_root)
    exposure_all, sampling_qc = build_exposure_matrix(records, side_paths, flipped_left_paths, right_xyz)
    candidate_sparse = np.any(exposure_all > args.candidate_threshold, axis=0)
    candidate_flat = right_flat[candidate_sparse]
    candidate_ijk = right_ijk[candidate_sparse]
    candidate_xyz = right_xyz[candidate_sparse]
    x = exposure_all[:, candidate_sparse].astype(np.float32)

    np.save(preprocess_dir / "X_HF_float32_subject_major.npy", x)
    np.save(preprocess_dir / "candidate_flat_indices.npy", candidate_flat)
    np.save(preprocess_dir / "candidate_ijk.npy", candidate_ijk)
    np.save(preprocess_dir / "candidate_xyz.npy", candidate_xyz)
    write_csv(preprocess_dir / "subjects.csv", [asdict(record) for record in records], ["subject_id", "y_post", "y_base"])
    write_json(
        preprocess_dir / "direct_voxel_HF_preprocess_qc.json",
        {
            "scale": scale,
            "scale_direction": scale_direction,
            "n_subjects": len(records),
            "right_brainmask_voxels": int(right_flat.size),
            "candidate_threshold_v_per_m": args.candidate_threshold,
            "n_candidate_voxels": int(candidate_flat.size),
            "side_fields": side_field_qc,
            "flip_result": flip_result,
            "sampling_qc": sampling_qc,
        },
    )

    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    subject_id_list = [record.subject_id for record in records]

    s_tau = suprathreshold_matrix(x, args.tau)
    coverage = coverage_from_suprathreshold(s_tau)
    omega = candidate_mask_from_coverage(coverage, args.min_coverage)
    if not np.any(omega):
        raise RuntimeError(f"empty Omega for tau={args.tau} and min_coverage={args.min_coverage}")

    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_omega = partial_spearman_matrix(y_post, x[:, omega], y_base)
    rho[omega] = rho_omega.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_scores, n_valid_full = mean_map_score(x, weights, omega)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_id_list):
        score_rows.append(
            {
                "subject_id": subject_id,
                "Y_post": y_post[idx],
                "Y_base": y_base[idx],
                "HFScore_mean_main": full_scores[idx],
                "exposure_sum_valid_voxels": float(np.sum(x[idx, omega & np.isfinite(weights)], dtype=np.float64)),
                "n_valid_score_voxels": n_valid_full,
                "score_map_source": "full_sample",
                "is_primary_score": True,
            }
        )

    fold_rows: list[dict[str, Any]] = []
    stability_positive = np.zeros(x.shape[1], dtype=np.int16)
    stability_valid = np.zeros(x.shape[1], dtype=np.int16)
    loocv_pred = np.full(len(records), np.nan, dtype=float)
    loocv_base_pred = np.full(len(records), np.nan, dtype=float)
    loocv_score = np.full(len(records), np.nan, dtype=float)
    for heldout in range(len(records)):
        train = np.array([idx for idx in range(len(records)) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        omega_fold = candidate_mask_from_coverage(coverage_fold, args.min_coverage)
        if not np.any(omega_fold):
            raise RuntimeError(f"empty LOOCV Omega for held-out {subject_id_list[heldout]}")
        rho_fold = partial_spearman_matrix(y_post[train], x[train][:, omega_fold], y_base[train])
        weights_fold_local = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[omega_fold] = weights_fold_local
        valid_fold = omega_fold & np.isfinite(weights_fold)
        if not np.any(valid_fold):
            raise RuntimeError(f"no valid LOOCV scoring voxels for held-out {subject_id_list[heldout]}")
        stability_valid[valid_fold] += 1
        stability_positive[valid_fold & (weights_fold > 0)] += 1
        fold_scores, n_valid_fold = mean_map_score(x, weights_fold, valid_fold)
        pred, beta = fit_linear_prediction(
            y_post[train],
            fold_scores[train],
            y_base[train],
            fold_scores[[heldout]],
            y_base[[heldout]],
        )
        base_pred, base_beta = fit_baseline_only(y_post[train], y_base[train], y_base[[heldout]])
        loocv_pred[heldout] = pred[0]
        loocv_base_pred[heldout] = base_pred[0]
        loocv_score[heldout] = fold_scores[heldout]
        fold_rows.append(
            {
                "fold_id": heldout + 1,
                "heldout_subject_id": subject_id_list[heldout],
                "Y_post": y_post[heldout],
                "Y_base": y_base[heldout],
                "HFScore_LOOCV": fold_scores[heldout],
                "prediction_HFScore_model": pred[0],
                "prediction_baseline_only": base_pred[0],
                "residual_HFScore_model": y_post[heldout] - pred[0],
                "residual_baseline_only": y_post[heldout] - base_pred[0],
                "n_train": len(train),
                "n_valid_score_voxels": n_valid_fold,
                "delta": beta[1],
                "beta_Y_base": beta[2],
                "baseline_beta_Y_base": base_beta[1],
            }
        )

    metrics = regression_metrics(y_post, loocv_pred, loocv_base_pred)
    stability = np.full(x.shape[1], np.nan, dtype=np.float32)
    nonzero_valid = stability_valid > 0
    stability[nonzero_valid] = stability_positive[nonzero_valid] / len(records)

    write_nifti_from_flat(branch_dir / "direct_voxel_HF_coverage.nii.gz", ref_img, candidate_flat, coverage, np.int16, 0)
    write_nifti_from_flat(branch_dir / "direct_voxel_HF_coef.nii.gz", ref_img, candidate_flat, rho, np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_HF_sweet_sour.nii.gz", ref_img, candidate_flat, weights, np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_HF_stability.nii.gz", ref_img, candidate_flat, stability, np.float32, np.nan)
    write_csv(
        branch_dir / "direct_voxel_HF_scores.csv",
        score_rows,
        [
            "subject_id",
            "Y_post",
            "Y_base",
            "HFScore_mean_main",
            "exposure_sum_valid_voxels",
            "n_valid_score_voxels",
            "score_map_source",
            "is_primary_score",
        ],
    )
    write_csv(
        branch_dir / "direct_voxel_HF_loocv_predictions.csv",
        fold_rows,
        [
            "fold_id",
            "heldout_subject_id",
            "Y_post",
            "Y_base",
            "HFScore_LOOCV",
            "prediction_HFScore_model",
            "prediction_baseline_only",
            "residual_HFScore_model",
            "residual_baseline_only",
            "n_train",
            "n_valid_score_voxels",
            "delta",
            "beta_Y_base",
            "baseline_beta_Y_base",
        ],
    )

    qc = {
        "scale": scale,
        "scale_slug": scale_slug,
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "n_subjects": len(records),
        "tau_v_per_m": args.tau,
        "candidate_threshold_v_per_m": args.candidate_threshold,
        "min_coverage": args.min_coverage,
        "right_brainmask_voxels": int(right_flat.size),
        "n_candidate_voxels": int(candidate_flat.size),
        "n_omega_voxels": int(np.count_nonzero(omega)),
        "n_valid_full_score_voxels": int(n_valid_full),
        "coverage_min": int(np.min(coverage)) if coverage.size else 0,
        "coverage_max": int(np.max(coverage)) if coverage.size else 0,
        "coverage_mean": float(np.mean(coverage)) if coverage.size else 0.0,
        "loocv_metrics": metrics,
        "corr_HFScore_mean_main_Y_base": float(np.corrcoef(full_scores, y_base)[0, 1]),
        "negative_clamped_voxels_total": int(
            sum(
                sum(item["negative_clamped_voxels"] for item in row["right"])
                + sum(item["negative_clamped_voxels"] for item in row["left_to_right"])
                for row in sampling_qc
            )
        ),
        "resampling_status": "not_run_smoke_observed_only",
    }
    manifest = {
        "generated_at": iso_now(),
        "model": "HF direct voxel",
        "branch": "tau200/partial_spearman",
        "status": "PASS",
        "repo_root": str(repo_root),
        "asset_root": str(asset_root),
        "clinical_root": str(clinical_root),
        "derivatives_root": str(derivatives_root),
        "output_root": str(output_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        },
        "parameters": {
            "scale": scale,
            "tau_v_per_m": args.tau,
            "candidate_threshold_v_per_m": args.candidate_threshold,
            "min_coverage": args.min_coverage,
            "random_seed": 42,
        },
        "outputs": {
            "preprocess_dir": str(preprocess_dir),
            "branch_dir": str(branch_dir),
            "scores_csv": str(branch_dir / "direct_voxel_HF_scores.csv"),
            "loocv_predictions_csv": str(branch_dir / "direct_voxel_HF_loocv_predictions.csv"),
            "mapping_qc_json": str(branch_dir / "direct_voxel_HF_mapping_qc.json"),
            "generation_manifest_json": str(branch_dir / "direct_voxel_HF_generation_manifest.json"),
        },
        "runtime_profile": {
            "total_s": time.time() - started,
            "preprocess_s": None,
            "observed_loocv_s": None,
            "permutation_s": None,
            "bootstrap_s": None,
            "jitter_s": None,
            "n_voxels_candidate": int(candidate_flat.size),
            "n_voxels_tau200": int(np.count_nonzero(omega)),
        },
    }
    write_json(branch_dir / "direct_voxel_HF_mapping_qc.json", qc)
    write_json(branch_dir / "direct_voxel_HF_generation_manifest.json", manifest)

    print(f"HF direct voxel smoke output: {branch_dir}")
    print(f"LOOCV Spearman rho: {metrics['spearman_rho']:.6g}")
    print(f"LOOCV Q2: {metrics['q2']:.6g}")
    print(f"Candidate voxels: {candidate_flat.size}; Omega voxels: {np.count_nonzero(omega)}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default=str(DEFAULT_CANONICAL_ASSET_ROOT), help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_VAL_ROOT / "summary/direct_voxel/hf"), help="HF direct voxel output root.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--scale", default=HF_DEFAULT_SCALES[0], help="Raw clinical scale to run.")
    parser.add_argument("--tau", type=float, default=200.0, help="Primary coverage threshold in V/m.")
    parser.add_argument("--candidate-threshold", type=float, default=180.0, help="Sparse candidate threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Minimum subject coverage.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_hf_direct_voxel_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
