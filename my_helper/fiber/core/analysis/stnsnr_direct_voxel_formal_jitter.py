#!/usr/bin/env python3
"""Spatial jitter QC for final STN/SNr direct-voxel models."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from stnsnr_direct_voxel_formal_permutation import (
    FORMAL_DIRECT_MODEL_IDS,
    DirectVoxelTarget,
    _float_column,
    direct_voxel_loocv_statistic,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    load_subject_table,
    write_csv,
    write_json,
)
from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import (
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    partial_spearman_matrix,
    suprathreshold_matrix,
)
from stnsnr_hf_direct_voxel_smoke import sample_image_at_xyz


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_provenance(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or default_repo_root()
    dirty_files = _run_git(root, ["status", "--short"]).splitlines()
    return {
        "repo_root": str(root),
        "git_branch": _run_git(root, ["branch", "--show-current"]),
        "git_commit": _run_git(root, ["rev-parse", "HEAD"]),
        "git_short_commit": _run_git(root, ["rev-parse", "--short", "HEAD"]),
        "git_dirty": bool(dirty_files),
        "git_dirty_files": dirty_files,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _subject_ids(subjects_csv: Path) -> list[str]:
    table = load_subject_table(subjects_csv)
    if "subject_id" not in table:
        raise KeyError(f"missing subject_id column in {subjects_csv}")
    return [str(value) for value in table["subject_id"]]


def _qc_rows_by_subject(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("subject_id", "")): row for row in rows}


def _paths_from_qc(row: dict[str, Any], key: str) -> list[Path]:
    out: list[Path] = []
    for item in row.get(key, []) or []:
        path_text = item.get("path", "") if isinstance(item, dict) else ""
        if path_text:
            out.append(Path(path_text))
    return out


def _sample_paths_with_shift(paths: list[Path], xyz: np.ndarray, shift_mm: np.ndarray) -> np.ndarray:
    if not paths:
        return np.zeros(xyz.shape[0], dtype=np.float32)
    shifted_xyz = np.asarray(xyz, dtype=np.float32) - np.asarray(shift_mm, dtype=np.float32).reshape(1, 3)
    values = np.zeros(xyz.shape[0], dtype=np.float32)
    for path in paths:
        sampled, _ = sample_image_at_xyz(path, shifted_xyz)
        values = np.maximum(values, sampled.astype(np.float32))
    return values


def _jitter_vector(rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    return rng.normal(loc=0.0, scale=float(sigma_mm), size=3).astype(np.float32)


def _build_hf_jitter_matrix(qc: dict[str, Any], subject_ids: list[str], xyz: np.ndarray, rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    rows_by_subject = _qc_rows_by_subject(qc.get("sampling_qc", []))
    x = np.zeros((len(subject_ids), xyz.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        row = rows_by_subject.get(subject_id)
        if row is None:
            raise KeyError(f"missing HF sampling QC row for {subject_id}")
        right = _sample_paths_with_shift(_paths_from_qc(row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        left = _sample_paths_with_shift(_paths_from_qc(row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        x[row_idx] = (right + left) / 2.0
    return x


def _build_ulf_jitter_matrix(
    qc: dict[str, Any],
    subject_ids: list[str],
    xyz: np.ndarray,
    rng: np.random.Generator,
    sigma_mm: float,
    *,
    tau: float,
) -> np.ndarray:
    hf_rows = _qc_rows_by_subject(qc.get("component_hf_sampling_qc", []))
    ulf_rows = _qc_rows_by_subject(qc.get("component_ulf_sampling_qc", []))
    try:
        hf_overlap_tau = float(qc.get("hf_overlap_tau_v_per_m", tau))
    except (TypeError, ValueError):
        hf_overlap_tau = float(tau)
    x = np.zeros((len(subject_ids), xyz.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        hf_row = hf_rows.get(subject_id, {})
        ulf_row = ulf_rows.get(subject_id, {})
        hf_right = _sample_paths_with_shift(_paths_from_qc(hf_row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        hf_left = _sample_paths_with_shift(_paths_from_qc(hf_row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        ulf_right = _sample_paths_with_shift(_paths_from_qc(ulf_row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        ulf_left = _sample_paths_with_shift(_paths_from_qc(ulf_row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        hf_component = (hf_right + hf_left) / 2.0
        ulf_component = (ulf_right + ulf_left) / 2.0
        hf_active = np.zeros_like(hf_component, dtype=bool) if math.isinf(hf_overlap_tau) else hf_component > hf_overlap_tau
        ulf_active = ulf_component > float(tau)
        x[row_idx] = np.where(ulf_active & ~hf_active, ulf_component, 0.0).astype(np.float32)
    return x


def _full_weights(
    *,
    x: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
) -> tuple[np.ndarray, np.ndarray]:
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    omega = candidate_mask_from_coverage(coverage, min_coverage)
    weights = np.full(x.shape[1], np.nan, dtype=np.float32)
    if not np.any(omega):
        return weights, omega
    rho = partial_spearman_matrix(y_post, x[:, omega], nuisance)
    weights[omega] = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid = omega & np.isfinite(weights)
    return weights, valid


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(finite) < 2:
        return float("nan")
    xx = x[finite] - np.mean(x[finite])
    yy = y[finite] - np.mean(y[finite])
    denom = float(np.sqrt(np.sum(xx * xx) * np.sum(yy * yy)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(xx * yy) / denom)


def _support_overlap(observed_valid: np.ndarray, jitter_valid: np.ndarray, observed_weights: np.ndarray, jitter_weights: np.ndarray) -> dict[str, Any]:
    intersection = observed_valid & jitter_valid
    union = observed_valid | jitter_valid
    if np.any(intersection):
        sign_consistency = float(np.mean(np.sign(observed_weights[intersection]) == np.sign(jitter_weights[intersection])))
    else:
        sign_consistency = float("nan")
    return {
        "support_intersection_voxels": int(np.count_nonzero(intersection)),
        "support_union_voxels": int(np.count_nonzero(union)),
        "valid_support_jaccard": float(np.count_nonzero(intersection) / np.count_nonzero(union)) if np.any(union) else float("nan"),
        "sign_consistency_fraction": sign_consistency,
    }


def _write_jitter_se_nifti(target: DirectVoxelTarget, prefix: str, se_values: np.ndarray) -> Path:
    flat_indices = np.asarray(np.load(target.x_path.parent / "candidate_flat_indices.npy"), dtype=np.int64)
    template = nib.load(str(target.branch_dir / f"{prefix}_coef.nii.gz"))
    if flat_indices.shape[0] != se_values.shape[0]:
        raise ValueError("candidate_flat_indices length must match jitter SE length")
    flat = np.full(int(np.prod(template.shape)), np.nan, dtype=np.float32)
    flat[flat_indices] = np.asarray(se_values, dtype=np.float32)
    image = nib.Nifti1Image(flat.reshape(template.shape), template.affine, template.header)
    output_path = target.branch_dir / f"{prefix}_jitter_se.nii.gz"
    nib.save(image, str(output_path))
    return output_path


def _jitter_matrix_for_target(target: DirectVoxelTarget, qc: dict[str, Any], subject_ids: list[str], xyz: np.ndarray, rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    if target.model_id == "A":
        return _build_hf_jitter_matrix(qc, subject_ids, xyz, rng, sigma_mm)
    if target.model_id == "C":
        return _build_ulf_jitter_matrix(qc, subject_ids, xyz, rng, sigma_mm, tau=target.tau)
    raise ValueError(f"unsupported direct-voxel jitter target: {target.model_id}")


def _qc_path_for_target(target: DirectVoxelTarget) -> Path:
    if target.model_id == "A":
        return target.x_path.parent / "direct_voxel_HF_preprocess_qc.json"
    if target.model_id == "C":
        return target.x_path.parent / "direct_voxel_ULF_only_preprocess_qc.json"
    raise ValueError(f"unsupported direct-voxel jitter target: {target.model_id}")


def run_target_jitter(
    target: DirectVoxelTarget,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float = 2.0,
    seed: int = 42,
) -> dict[str, Any]:
    provenance = git_provenance()
    prefix = file_prefix_for_manifest(target.manifest_path)
    subject_ids = _subject_ids(target.subjects_csv)
    xyz = np.asarray(np.load(target.x_path.parent / "candidate_xyz.npy"), dtype=np.float32)
    qc = _load_json(_qc_path_for_target(target))
    table = load_subject_table(target.subjects_csv)
    y_post = _float_column(table, target.outcome_column)
    nuisance = np.column_stack([_float_column(table, column) for column in target.nuisance_columns])
    observed_x = np.asarray(np.load(target.x_path, mmap_mode="r"), dtype=np.float32)
    observed_weights, observed_valid = _full_weights(
        x=observed_x,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        tau=target.tau,
        min_coverage=target.min_coverage,
    )

    sigma_mm = float(jitter_fwhm_mm) / 2.3548200450309493
    rng = np.random.default_rng(seed)
    mean = np.zeros(observed_weights.shape[0], dtype=np.float64)
    m2 = np.zeros(observed_weights.shape[0], dtype=np.float64)
    finite_count = np.zeros(observed_weights.shape[0], dtype=np.int32)
    similarity_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    finite_jitter_count = 0

    for idx in range(int(n_jitters)):
        jitter_x = _jitter_matrix_for_target(target, qc, subject_ids, xyz, rng, sigma_mm)
        jitter_weights, jitter_valid = _full_weights(
            x=jitter_x,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=target.tau,
            min_coverage=target.min_coverage,
        )
        finite = np.isfinite(jitter_weights)
        if np.any(finite):
            finite_jitter_count += 1
            values = jitter_weights[finite].astype(np.float64)
            finite_count[finite] += 1
            delta = values - mean[finite]
            mean[finite] += delta / finite_count[finite]
            delta2 = values - mean[finite]
            m2[finite] += delta * delta2
        try:
            metrics = direct_voxel_loocv_statistic(
                x=jitter_x,
                y_post=y_post,
                nuisance=nuisance,
                scale_direction=target.scale_direction,
                tau=target.tau,
                min_coverage=target.min_coverage,
            )
        except Exception as exc:  # keep QC resumable; failures are summarized.
            metrics = {"spearman_rho": np.nan, "pearson_r": np.nan, "mae": np.nan, "rmse": np.nan, "q2": np.nan, "failure": str(exc)}
        map_r = _pearson(observed_weights, jitter_weights)
        overlap = _support_overlap(observed_valid, jitter_valid, observed_weights, jitter_weights)
        similarity_rows.append(
            {
                "jitter_index": idx + 1,
                "loocv_spearman_rho": metrics.get("spearman_rho", np.nan),
                "loocv_pearson_r": metrics.get("pearson_r", np.nan),
                "mae": metrics.get("mae", np.nan),
                "rmse": metrics.get("rmse", np.nan),
                "q2": metrics.get("q2", np.nan),
                "map_pearson_r": map_r,
                "n_finite_map_voxels": int(np.count_nonzero(finite)),
                "failure": metrics.get("failure", ""),
            }
        )
        overlap_rows.append({"jitter_index": idx + 1, **overlap})
        if (idx + 1) % 25 == 0 or idx + 1 == int(n_jitters):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_jitters)} formal jitters", flush=True)

    se = np.full(observed_weights.shape[0], np.nan, dtype=np.float32)
    valid_se = finite_count > 1
    se[valid_se] = np.sqrt(m2[valid_se] / (finite_count[valid_se] - 1)).astype(np.float32)
    se_path = _write_jitter_se_nifti(target, prefix, se)

    similarity_path = target.branch_dir / f"{prefix}_jitter_model_similarity.csv"
    overlap_path = target.branch_dir / f"{prefix}_jitter_selected_overlap.csv"
    summary_path = target.branch_dir / f"{prefix}_jitter_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_jitter_manifest.json"
    write_csv(similarity_path, similarity_rows, list(similarity_rows[0].keys()))
    write_csv(overlap_path, overlap_rows, list(overlap_rows[0].keys()))

    map_corr = np.asarray([row["map_pearson_r"] for row in similarity_rows], dtype=float)
    loocv_rho = np.asarray([row["loocv_spearman_rho"] for row in similarity_rows], dtype=float)
    support_jaccard = np.asarray([row["valid_support_jaccard"] for row in overlap_rows], dtype=float)
    summary = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "B": int(n_jitters),
        "seed": int(seed),
        "jitter_status": "complete" if finite_jitter_count == int(n_jitters) else "partial",
        "jitter_fwhm_mm": float(jitter_fwhm_mm),
        "jitter_sigma_mm": sigma_mm,
        "finite_jitter_count": int(finite_jitter_count),
        "map_pearson_r_median": float(np.nanmedian(map_corr)) if map_corr.size else np.nan,
        "map_pearson_r_min": float(np.nanmin(map_corr)) if np.any(np.isfinite(map_corr)) else np.nan,
        "loocv_spearman_rho_median": float(np.nanmedian(loocv_rho)) if loocv_rho.size else np.nan,
        "support_jaccard_median": float(np.nanmedian(support_jaccard)) if support_jaccard.size else np.nan,
        "jitter_se_nifti": str(se_path),
        "generated_at": iso_now(),
    }
    write_csv(summary_path, [summary], list(summary.keys()))
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "model_id": target.model_id,
            "target_manifest": str(target.manifest_path),
            "n_jitters": int(n_jitters),
            "jitter_fwhm_mm": float(jitter_fwhm_mm),
            "jitter_sigma_mm": sigma_mm,
            "seed": int(seed),
            "code_provenance": provenance,
            "method": "Subject-side spatial jitter with raw/flipped e-field resampling on the final candidate grid",
            "outputs": {
                "summary_csv": str(summary_path),
                "model_similarity_csv": str(similarity_path),
                "selected_overlap_csv": str(overlap_path),
                "jitter_se_nifti": str(se_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    return summary


def run_formal_jitter(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no direct-voxel formal jitter targets found")
    rows = []
    for target in targets:
        print(f"Running direct-voxel formal jitter QC for {target.model_id} ({args.n_jitters} jitters)")
        rows.append(
            run_target_jitter(
                target,
                n_jitters=args.n_jitters,
                jitter_fwhm_mm=args.jitter_fwhm_mm,
                seed=args.seed,
            )
        )
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "direct_voxel_formal_jitter_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "direct_voxel_formal_jitter_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_jitters": int(args.n_jitters),
            "jitter_fwhm_mm": float(args.jitter_fwhm_mm),
            "seed": int(args.seed),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"Direct-voxel formal jitter summary: {summary_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readiness-csv",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_readiness/four_model_formal_readiness.csv"),
        help="Formal readiness CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/direct_voxel_formal_jitter"),
        help="Cross-target direct-voxel formal jitter summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(FORMAL_DIRECT_MODEL_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-jitters", type=int, default=1000, help="Number of spatial jitter resamples.")
    parser.add_argument("--jitter-fwhm-mm", type=float, default=2.0, help="Gaussian translation FWHM in millimeters.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_jitter(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
