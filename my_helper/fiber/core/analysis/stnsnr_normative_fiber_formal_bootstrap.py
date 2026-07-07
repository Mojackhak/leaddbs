#!/usr/bin/env python3
"""Subject-level bootstrap for dTOR normative-fiber final models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import average_rank_1d, benefit_oriented_weights, fiber_net_score, rank_columns, residualize
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    NormativeFiberTarget,
    _as_2d,
    _float_column,
    _load_score_columns,
    default_cross_target_output_dir,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    prepare_candidate_union,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance

try:
    from scipy.stats import rankdata as scipy_rankdata
except Exception:  # pragma: no cover - exercised only if SciPy is unavailable.
    scipy_rankdata = None


def rank_columns_fast(values: np.ndarray) -> np.ndarray:
    """Rank columns with average ties; use SciPy's vectorized path when available."""
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        return average_rank_1d(arr)
    if scipy_rankdata is not None:
        return np.asarray(scipy_rankdata(arr, axis=0, method="average", nan_policy="omit"), dtype=float)
    return rank_columns(arr)


def residualize_complete(values: np.ndarray, covariates: np.ndarray) -> np.ndarray:
    """Residualize complete finite matrices against an intercept and covariates."""
    y = np.asarray(values, dtype=float)
    one_dimensional = y.ndim == 1
    if one_dimensional:
        y = y[:, None]
    cov = _as_2d(covariates)
    if not (np.all(np.isfinite(y)) and np.all(np.isfinite(cov))):
        out = residualize(y, cov)
        return out[:, 0] if one_dimensional and out.ndim == 2 else out
    design = np.column_stack([np.ones(y.shape[0], dtype=float), cov])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    out = y - design @ beta
    return out[:, 0] if one_dimensional else out


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
    """Fit one bootstrap fiber-weight vector over a fixed reduced candidate universe."""
    x_sample = np.asarray(x[sample_indices], dtype=float)
    y_sample = np.asarray(y_post[sample_indices], dtype=float)
    nuisance_sample = _as_2d(nuisance)[sample_indices]
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


def _frequency(counts: np.ndarray, denominator: int) -> np.ndarray:
    if denominator <= 0:
        return np.zeros(counts.shape, dtype=float)
    return np.asarray(counts, dtype=float) / float(denominator)


def _frequency_by_fiber(counts: np.ndarray, denominators: np.ndarray) -> np.ndarray:
    out = np.zeros(counts.shape, dtype=float)
    valid = denominators > 0
    out[valid] = np.asarray(counts[valid], dtype=float) / np.asarray(denominators[valid], dtype=float)
    return out


def _table_value(value: float | int | str) -> float | int | str:
    if isinstance(value, float) and not np.isfinite(value):
        return ""
    return value


def run_target_bootstrap(target: NormativeFiberTarget, *, n_bootstraps: int, seed: int = 42) -> dict[str, Any]:
    provenance = git_provenance()
    x = np.load(target.x_path, mmap_mode="r")
    fiber_ids = np.load(target.fiber_ids_path, mmap_mode="r")
    reduced = prepare_candidate_union(x=x, fiber_ids=fiber_ids, tau=target.tau, min_coverage=target.min_coverage)
    score_columns = _load_score_columns(target.scores_csv)
    y_post = _float_column(score_columns, target.outcome_column)
    nuisance = np.column_stack([_float_column(score_columns, column) for column in target.nuisance_columns])

    n_fibers = int(reduced.x.shape[1])
    rng = np.random.default_rng(seed)
    bootstrap_indices = rng.integers(0, int(y_post.shape[0]), size=(int(n_bootstraps), int(y_post.shape[0])))
    weight_sum = np.zeros(n_fibers, dtype=np.float64)
    weight_sq_sum = np.zeros(n_fibers, dtype=np.float64)
    finite_count = np.zeros(n_fibers, dtype=np.int32)
    positive_count = np.zeros(n_fibers, dtype=np.int32)
    negative_count = np.zeros(n_fibers, dtype=np.int32)
    zero_count = np.zeros(n_fibers, dtype=np.int32)
    sweet_count = np.zeros(n_fibers, dtype=np.int32)
    sour_count = np.zeros(n_fibers, dtype=np.int32)
    candidate_counts: list[int] = []
    sweet_selected_counts: list[int] = []
    sour_selected_counts: list[int] = []
    finite_bootstraps = 0

    fiber_index = {int(fiber_id): idx for idx, fiber_id in enumerate(np.asarray(reduced.fiber_ids, dtype=np.int64))}
    for idx, sample_indices in enumerate(bootstrap_indices):
        weights, n_candidate = bootstrap_weights_for_sample(
            x=reduced.x,
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
            finite_weights = weights[finite].astype(float)
            weight_sum[finite] += finite_weights
            weight_sq_sum[finite] += finite_weights * finite_weights
            finite_count[finite] += 1
            positive_count[finite & (weights > 0)] += 1
            negative_count[finite & (weights < 0)] += 1
            zero_count[finite & (weights == 0)] += 1
            score = fiber_net_score(reduced.x, weights, finite, fiber_ids=reduced.fiber_ids)
            sweet_selected_counts.append(int(score.sweet_fiber_ids.size))
            sour_selected_counts.append(int(score.sour_fiber_ids.size))
            for fiber_id in score.sweet_fiber_ids:
                sweet_count[fiber_index[int(fiber_id)]] += 1
            for fiber_id in score.sour_fiber_ids:
                sour_count[fiber_index[int(fiber_id)]] += 1
        else:
            sweet_selected_counts.append(0)
            sour_selected_counts.append(0)
        candidate_counts.append(int(n_candidate))
        if (idx + 1) % 100 == 0 or idx + 1 == int(n_bootstraps):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_bootstraps)} formal bootstraps", flush=True)

    with np.errstate(invalid="ignore", divide="ignore"):
        weight_mean = weight_sum / finite_count
        variance = (weight_sq_sum - (weight_sum * weight_sum / finite_count)) / np.maximum(finite_count - 1, 1)
        weight_se = np.sqrt(np.maximum(variance, 0.0))
    weight_mean[finite_count == 0] = np.nan
    weight_se[finite_count <= 1] = np.nan

    prefix = file_prefix_for_manifest(target.manifest_path)
    summary_path = target.branch_dir / f"{prefix}_bootstrap_summary.csv"
    se_path = target.branch_dir / f"{prefix}_bootstrap_se.csv"
    selection_path = target.branch_dir / f"{prefix}_bootstrap_selection_frequency.csv"
    sign_path = target.branch_dir / f"{prefix}_bootstrap_sign_stability.csv"
    manifest_path = target.branch_dir / f"{prefix}_bootstrap_manifest.json"

    se_rows = [
        {
            "fiber_id": int(fiber_id),
            "finite_count": int(finite_count[idx]),
            "weight_mean": _table_value(float(weight_mean[idx])),
            "weight_se": _table_value(float(weight_se[idx])),
        }
        for idx, fiber_id in enumerate(reduced.fiber_ids)
    ]
    write_csv(se_path, se_rows, ["fiber_id", "finite_count", "weight_mean", "weight_se"])

    selection_rows = [
        {
            "fiber_id": int(fiber_id),
            "sweet_selection_count": int(sweet_count[idx]),
            "sweet_selection_frequency": float(_frequency(sweet_count, finite_bootstraps)[idx]),
            "sour_selection_count": int(sour_count[idx]),
            "sour_selection_frequency": float(_frequency(sour_count, finite_bootstraps)[idx]),
        }
        for idx, fiber_id in enumerate(reduced.fiber_ids)
    ]
    write_csv(
        selection_path,
        selection_rows,
        ["fiber_id", "sweet_selection_count", "sweet_selection_frequency", "sour_selection_count", "sour_selection_frequency"],
    )

    positive_frequency = _frequency_by_fiber(positive_count, finite_count)
    negative_frequency = _frequency_by_fiber(negative_count, finite_count)
    zero_frequency = _frequency_by_fiber(zero_count, finite_count)
    sign_rows = []
    for idx, fiber_id in enumerate(reduced.fiber_ids):
        counts = {"positive": int(positive_count[idx]), "negative": int(negative_count[idx]), "zero": int(zero_count[idx])}
        dominant = max(counts, key=counts.get) if finite_count[idx] else "not_finite"
        dominant_frequency = float(counts[dominant] / finite_count[idx]) if finite_count[idx] else 0.0
        sign_rows.append(
            {
                "fiber_id": int(fiber_id),
                "positive_count": int(positive_count[idx]),
                "positive_frequency": float(positive_frequency[idx]),
                "negative_count": int(negative_count[idx]),
                "negative_frequency": float(negative_frequency[idx]),
                "zero_count": int(zero_count[idx]),
                "zero_frequency": float(zero_frequency[idx]),
                "dominant_sign": dominant,
                "dominant_sign_frequency": dominant_frequency,
            }
        )
    write_csv(
        sign_path,
        sign_rows,
        [
            "fiber_id",
            "positive_count",
            "positive_frequency",
            "negative_count",
            "negative_frequency",
            "zero_count",
            "zero_frequency",
            "dominant_sign",
            "dominant_sign_frequency",
        ],
    )

    candidate_array = np.asarray(candidate_counts, dtype=float)
    sweet_array = np.asarray(sweet_selected_counts, dtype=float)
    sour_array = np.asarray(sour_selected_counts, dtype=float)
    summary = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "B": int(n_bootstraps),
        "seed": int(seed),
        "bootstrap_status": "complete",
        "finite_bootstrap_count": int(finite_bootstraps),
        "n_original_fibers": int(reduced.n_original_fibers),
        "n_candidate_union_fibers": int(n_fibers),
        "bootstrap_candidate_fibers_min": int(np.min(candidate_array)) if candidate_array.size else 0,
        "bootstrap_candidate_fibers_median": float(np.median(candidate_array)) if candidate_array.size else 0.0,
        "bootstrap_candidate_fibers_max": int(np.max(candidate_array)) if candidate_array.size else 0,
        "bootstrap_sweet_selected_min": int(np.min(sweet_array)) if sweet_array.size else 0,
        "bootstrap_sweet_selected_median": float(np.median(sweet_array)) if sweet_array.size else 0.0,
        "bootstrap_sour_selected_min": int(np.min(sour_array)) if sour_array.size else 0,
        "bootstrap_sour_selected_median": float(np.median(sour_array)) if sour_array.size else 0.0,
        "generated_at": iso_now(),
    }
    write_csv(summary_path, [summary], list(summary.keys()))
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "model_id": target.model_id,
            "target_manifest": str(target.manifest_path),
            "n_bootstraps": int(n_bootstraps),
            "seed": int(seed),
            "code_provenance": provenance,
            "method": "Subject-level dTOR normative-fiber bootstrap over selected candidate union",
            "outputs": {
                "summary_csv": str(summary_path),
                "bootstrap_se_csv": str(se_path),
                "bootstrap_selection_frequency_csv": str(selection_path),
                "bootstrap_sign_stability_csv": str(sign_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    return summary


def run_formal_bootstrap(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no dTOR normative-fiber formal bootstrap targets found")
    rows = []
    for target in targets:
        print(f"Running dTOR normative-fiber formal bootstrap for {target.model_id} ({args.n_bootstraps} bootstraps)")
        rows.append(run_target_bootstrap(target, n_bootstraps=args.n_bootstraps, seed=args.seed))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "normative_fiber_formal_bootstrap_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "normative_fiber_formal_bootstrap_manifest.json",
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
    print(f"dTOR normative-fiber formal bootstrap summary: {summary_path}")
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
        default=str(default_cross_target_output_dir("formal").parent / "normative_fiber_formal_bootstrap"),
        help="Cross-target bootstrap summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-bootstraps", type=int, default=10000, help="Number of subject-level bootstrap resamples.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_bootstrap(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
