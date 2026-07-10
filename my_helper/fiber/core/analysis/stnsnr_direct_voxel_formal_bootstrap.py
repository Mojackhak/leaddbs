#!/usr/bin/env python3
"""Subject-level bootstrap for final STN/SNr direct-voxel models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from stnsnr_direct_voxel_formal_permutation import (
    FORMAL_DIRECT_MODEL_IDS,
    DirectVoxelTarget,
    _float_column,
    discover_targets,
    iso_now,
    load_target_nuisance,
    load_subject_table,
    target_file_prefix,
    write_csv,
    write_json,
)
from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import average_rank_1d, benefit_oriented_weights
from stnsnr_normative_fiber_formal_bootstrap import rank_columns_fast, residualize_complete
from stnsnr_run_provenance import git_provenance


def bootstrap_weights_for_sample(
    *,
    x: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    sample_indices: np.ndarray,
    tau: float,
    min_coverage: int,
    scale_direction: str,
) -> tuple[np.ndarray, int]:
    x_sample = np.asarray(x[sample_indices], dtype=float)
    y_sample = np.asarray(y_post[sample_indices], dtype=float)
    nuisance_sample = np.asarray(nuisance, dtype=float)[sample_indices]
    candidate = np.sum(x_sample > float(tau), axis=0) >= int(min_coverage)
    weights = np.full(x.shape[1], np.nan, dtype=np.float32)
    if not np.any(candidate):
        return weights, 0

    y_rank = average_rank_1d(y_sample)
    nuisance_rank = rank_columns_fast(nuisance_sample)
    x_rank = rank_columns_fast(x_sample[:, candidate])
    y_resid = residualize_complete(y_rank, nuisance_rank)
    x_resid = residualize_complete(x_rank, nuisance_rank)
    y_denom = float(np.sqrt(np.sum(y_resid * y_resid)))
    x_denom = np.sqrt(np.sum(x_resid * x_resid, axis=0))
    valid_local = np.isfinite(x_denom) & (x_denom > 0.0) & np.all(np.isfinite(x_resid), axis=0)
    if not np.isfinite(y_denom) or y_denom <= 0.0 or not np.any(valid_local):
        return weights, int(np.count_nonzero(candidate))

    candidate_indices = np.flatnonzero(candidate)
    valid_indices = candidate_indices[valid_local]
    rho = x_resid[:, valid_local].T @ (y_resid / y_denom) / x_denom[valid_local]
    weights[valid_indices] = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    return weights, int(valid_indices.size)


def _preprocess_dir(target: DirectVoxelTarget) -> Path:
    return target.x_path.parent


def _template_path(target: DirectVoxelTarget, prefix: str) -> Path:
    return target.spatial_reference_path or target.branch_dir / f"{prefix}_coef.nii.gz"


def _write_se_nifti(target: DirectVoxelTarget, prefix: str, se_values: np.ndarray) -> Path:
    preprocess_dir = _preprocess_dir(target)
    flat_indices_path = target.feature_ids_path or preprocess_dir / "candidate_flat_indices.npy"
    if not flat_indices_path.is_file():
        raise FileNotFoundError(f"missing candidate flat indices: {flat_indices_path}")
    template_path = _template_path(target, prefix)
    if not template_path.is_file():
        raise FileNotFoundError(f"missing coefficient template NIfTI: {template_path}")
    flat_indices = np.asarray(np.load(flat_indices_path), dtype=np.int64)
    if flat_indices.shape[0] != se_values.shape[0]:
        raise ValueError("candidate_flat_indices length must match bootstrap SE length")
    template = nib.load(str(template_path))
    flat = np.full(int(np.prod(template.shape)), np.nan, dtype=np.float32)
    flat[flat_indices] = np.asarray(se_values, dtype=np.float32)
    image = nib.Nifti1Image(flat.reshape(template.shape), template.affine, template.header)
    output_path = target.branch_dir / f"{prefix}_bootstrap_se.nii.gz"
    nib.save(image, str(output_path))
    return output_path


def run_target_bootstrap(target: DirectVoxelTarget, *, n_bootstraps: int, seed: int = 42) -> dict[str, Any]:
    provenance = git_provenance()
    target.branch_dir.mkdir(parents=True, exist_ok=True)
    x = np.asarray(np.load(target.x_path, mmap_mode="r"), dtype=np.float32)
    table = load_subject_table(target.subjects_csv)
    y_post = _float_column(table, target.outcome_column)
    nuisance, _ = load_target_nuisance(target, table)

    rng = np.random.default_rng(seed)
    bootstrap_indices = rng.integers(0, int(y_post.shape[0]), size=(int(n_bootstraps), int(y_post.shape[0])))
    n_voxels = int(x.shape[1])
    mean = np.zeros(n_voxels, dtype=np.float64)
    m2 = np.zeros(n_voxels, dtype=np.float64)
    finite_count = np.zeros(n_voxels, dtype=np.int32)
    candidate_counts: list[int] = []
    finite_bootstraps = 0

    for idx, sample_indices in enumerate(bootstrap_indices):
        weights, n_candidate = bootstrap_weights_for_sample(
            x=x,
            y_post=y_post,
            nuisance=nuisance,
            sample_indices=sample_indices,
            tau=target.tau,
            min_coverage=target.min_coverage,
            scale_direction=target.scale_direction,
        )
        finite = np.isfinite(weights)
        if np.any(finite):
            finite_bootstraps += 1
            values = weights[finite].astype(np.float64)
            finite_count[finite] += 1
            delta = values - mean[finite]
            mean[finite] += delta / finite_count[finite]
            delta2 = values - mean[finite]
            m2[finite] += delta * delta2
        candidate_counts.append(int(n_candidate))
        if (idx + 1) % 100 == 0 or idx + 1 == int(n_bootstraps):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_bootstraps)} formal bootstraps", flush=True)

    se = np.full(n_voxels, np.nan, dtype=np.float32)
    valid_se = finite_count > 1
    se[valid_se] = np.sqrt(m2[valid_se] / (finite_count[valid_se] - 1)).astype(np.float32)

    prefix = target_file_prefix(target)
    se_path = _write_se_nifti(target, prefix, se)
    summary_path = target.branch_dir / f"{prefix}_bootstrap_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_bootstrap_manifest.json"
    candidate_array = np.asarray(candidate_counts, dtype=float)
    finite_array = np.asarray(finite_count, dtype=float)
    summary = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "B": int(n_bootstraps),
        "seed": int(seed),
        "bootstrap_status": "complete",
        "finite_bootstrap_count": int(finite_bootstraps),
        "n_voxels": int(n_voxels),
        "bootstrap_candidate_voxels_min": int(np.min(candidate_array)) if candidate_array.size else 0,
        "bootstrap_candidate_voxels_median": float(np.median(candidate_array)) if candidate_array.size else 0.0,
        "bootstrap_candidate_voxels_max": int(np.max(candidate_array)) if candidate_array.size else 0,
        "voxel_finite_count_min": int(np.min(finite_array)) if finite_array.size else 0,
        "voxel_finite_count_median": float(np.median(finite_array)) if finite_array.size else 0.0,
        "voxel_finite_count_max": int(np.max(finite_array)) if finite_array.size else 0,
        "bootstrap_se_nifti": str(se_path),
        "generated_at": iso_now(),
    }
    if target.final_record_hash:
        summary["final_record_hash"] = target.final_record_hash
    write_csv(summary_path, [summary], list(summary.keys()))
    formal_manifest = {
        "generated_at": iso_now(),
        "model_id": target.model_id,
        "target_manifest": str(target.manifest_path),
        "n_bootstraps": int(n_bootstraps),
        "seed": int(seed),
        "code_provenance": provenance,
        "method": "Subject-level direct-voxel bootstrap with streaming SE accumulation",
        "outputs": {"summary_csv": str(summary_path), "bootstrap_se_nifti": str(se_path), "manifest_json": str(manifest_path)},
    }
    if target.final_record_hash:
        formal_manifest["final_record_hash"] = target.final_record_hash
    write_json(manifest_path, formal_manifest)
    return summary


def run_formal_bootstrap(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no direct-voxel formal bootstrap targets found")
    rows = []
    for target in targets:
        print(f"Running direct-voxel formal bootstrap for {target.model_id} ({args.n_bootstraps} bootstraps)")
        rows.append(run_target_bootstrap(target, n_bootstraps=args.n_bootstraps, seed=args.seed))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "direct_voxel_formal_bootstrap_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "direct_voxel_formal_bootstrap_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_bootstraps": int(args.n_bootstraps),
            "seed": int(args.seed),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"Direct-voxel formal bootstrap summary: {summary_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/direct_voxel_formal_bootstrap"),
        help="Cross-target direct-voxel formal bootstrap summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(FORMAL_DIRECT_MODEL_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-bootstraps", type=int, default=10000, help="Number of subject-level bootstrap resamples.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_bootstrap(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
