#!/usr/bin/env python3
"""Exact Freedman-Lane permutation for dTOR normative-fiber final models."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import (
    average_rank_1d,
    benefit_oriented_weights,
    fiber_net_score,
    fit_linear_prediction,
    freedman_lane_permuted_outcomes,
    plus_one_two_sided_p,
    rank_columns,
    regression_metrics,
    residualize,
)
from stnsnr_run_provenance import git_provenance

DTOR_NORMATIVE_TARGET_IDS = {"B_DTOR", "D_DTOR"}
PERMUTATION_TIERS = {"smoke", "formal"}


@dataclass(frozen=True)
class CandidateUnion:
    x: np.ndarray
    fiber_ids: np.ndarray
    fold_candidate_masks: tuple[np.ndarray, ...]
    n_full_candidate_fibers: int
    n_original_fibers: int


@dataclass(frozen=True)
class FoldFiberCache:
    heldout: int
    train: np.ndarray
    candidate_mask: np.ndarray
    valid_candidate_mask: np.ndarray
    nuisance_train: np.ndarray
    nuisance_test: np.ndarray
    nuisance_rank_train: np.ndarray
    z_exposure_rank_resid: np.ndarray


@dataclass(frozen=True)
class NormativeFiberTarget:
    model_id: str
    manifest_path: Path
    branch_dir: Path
    x_path: Path
    fiber_ids_path: Path
    scores_csv: Path
    outcome_column: str
    nuisance_columns: tuple[str, ...]
    scale_direction: str
    tau: float
    min_coverage: int


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def file_prefix_for_manifest(manifest_path: Path) -> str:
    name = manifest_path.name
    if name == "normative_HF_fiber_generation_manifest.json":
        return "normative_HF_fiber"
    if name == "normative_ULF_fiber_generation_manifest.json":
        return "normative_ULF_fiber"
    raise ValueError(f"unsupported normative-fiber manifest: {manifest_path}")


def permutation_suffix_for_tier(tier: str) -> str:
    if tier == "smoke":
        return "smoke_permutation"
    if tier == "formal":
        return "permutation"
    raise ValueError(f"unsupported permutation tier: {tier}")


def cross_target_output_stem_for_tier(tier: str) -> str:
    if tier == "smoke":
        return "normative_fiber_smoke_permutation"
    if tier == "formal":
        return "normative_fiber_formal_permutation"
    raise ValueError(f"unsupported permutation tier: {tier}")


def default_cross_target_output_dir(tier: str) -> Path:
    return DEFAULT_VAL_ROOT / "summary/four_model_execution" / cross_target_output_stem_for_tier(tier)


def prepare_candidate_union(*, x: np.ndarray, fiber_ids: np.ndarray, tau: float, min_coverage: int) -> CandidateUnion:
    """Reduce a full connectome sidecar to the union of exact fold candidates."""
    x_arr = np.asarray(x, dtype=np.float32)
    ids = np.asarray(fiber_ids, dtype=np.int64)
    if x_arr.ndim != 2:
        raise ValueError("x must be subject-by-fiber")
    if ids.shape[0] != x_arr.shape[1]:
        raise ValueError("fiber_ids length must match x columns")
    suprathreshold = x_arr > float(tau)
    coverage = suprathreshold.sum(axis=0).astype(np.int32)
    full_candidate = coverage >= int(min_coverage)
    union = np.zeros(x_arr.shape[1], dtype=bool)
    fold_masks_full: list[np.ndarray] = []
    for heldout in range(x_arr.shape[0]):
        fold_candidate = (coverage - suprathreshold[heldout].astype(np.int32)) >= int(min_coverage)
        if not np.any(fold_candidate):
            raise RuntimeError(f"empty fold candidate set for heldout index {heldout}")
        fold_masks_full.append(fold_candidate)
        union |= fold_candidate
    if not np.any(union):
        raise RuntimeError("empty candidate union")
    union_indices = np.flatnonzero(union)
    fold_masks = tuple(mask[union_indices] for mask in fold_masks_full)
    return CandidateUnion(
        x=np.asarray(x_arr[:, union_indices], dtype=np.float32),
        fiber_ids=ids[union_indices],
        fold_candidate_masks=fold_masks,
        n_full_candidate_fibers=int(np.count_nonzero(full_candidate)),
        n_original_fibers=int(x_arr.shape[1]),
    )


def _as_2d(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr[:, None]
    return arr


def _fit_baseline_with_covariates(train_y: np.ndarray, train_covariates: np.ndarray, test_covariates: np.ndarray) -> float:
    cov_train = _as_2d(train_covariates)
    cov_test = _as_2d(test_covariates)
    train_design = np.column_stack([np.ones(train_y.shape[0], dtype=float), cov_train])
    test_design = np.column_stack([np.ones(1, dtype=float), cov_test.reshape(1, -1)])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return float((test_design @ beta)[0])


def build_fold_fiber_caches(reduced: CandidateUnion, nuisance: np.ndarray) -> tuple[FoldFiberCache, ...]:
    cov = _as_2d(nuisance)
    caches: list[FoldFiberCache] = []
    for heldout, candidate in enumerate(reduced.fold_candidate_masks):
        train = np.array([idx for idx in range(reduced.x.shape[0]) if idx != heldout], dtype=int)
        nuisance_train = cov[train]
        nuisance_rank_train = rank_columns(nuisance_train)
        x_rank = rank_columns(np.asarray(reduced.x[train][:, candidate], dtype=float))
        x_resid = residualize(x_rank, nuisance_rank_train)
        denom = np.sqrt(np.sum(x_resid * x_resid, axis=0))
        valid_local = np.isfinite(denom) & (denom > 0.0) & np.all(np.isfinite(x_resid), axis=0)
        if not np.any(valid_local):
            raise RuntimeError(f"no valid residualized fiber features for heldout index {heldout}")
        z = x_resid[:, valid_local] / denom[valid_local]
        valid_candidate = np.zeros(candidate.shape, dtype=bool)
        candidate_indices = np.flatnonzero(candidate)
        valid_candidate[candidate_indices[valid_local]] = True
        caches.append(
            FoldFiberCache(
                heldout=heldout,
                train=train,
                candidate_mask=candidate,
                valid_candidate_mask=valid_candidate,
                nuisance_train=nuisance_train,
                nuisance_test=cov[[heldout]],
                nuisance_rank_train=nuisance_rank_train,
                z_exposure_rank_resid=z,
            )
        )
    return tuple(caches)


def normative_fiber_loocv_statistic(
    *,
    reduced: CandidateUnion,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    fold_caches: tuple[FoldFiberCache, ...] | None = None,
) -> dict[str, Any]:
    x = reduced.x
    y = np.asarray(y_post, dtype=float)
    cov = _as_2d(nuisance)
    caches = fold_caches or build_fold_fiber_caches(reduced, cov)
    pred = np.full(y.shape[0], np.nan, dtype=float)
    base_pred = np.full(y.shape[0], np.nan, dtype=float)
    fold_candidate_counts: list[int] = []
    selected_sweet_counts: list[int] = []
    selected_sour_counts: list[int] = []
    for cache in caches:
        heldout = cache.heldout
        train = cache.train
        candidate = cache.valid_candidate_mask
        fold_candidate_counts.append(int(np.count_nonzero(candidate)))
        y_rank = average_rank_1d(y[train])
        y_resid = residualize(y_rank, cache.nuisance_rank_train)
        y_denom = float(np.sqrt(np.sum(y_resid * y_resid)))
        if not np.isfinite(y_denom) or y_denom <= 0.0:
            continue
        rho_fold = cache.z_exposure_rank_resid.T @ (y_resid / y_denom)
        weights = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights[candidate] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(x, weights, candidate, fiber_ids=reduced.fiber_ids)
        selected_sweet_counts.append(int(fold_net.sweet_fiber_ids.size))
        selected_sour_counts.append(int(fold_net.sour_fiber_ids.size))
        fold_pred, _ = fit_linear_prediction(
            y[train],
            fold_net.net_score[train],
            cache.nuisance_train,
            fold_net.net_score[[heldout]],
            cache.nuisance_test,
        )
        pred[heldout] = fold_pred[0]
        base_pred[heldout] = _fit_baseline_with_covariates(y[train], cache.nuisance_train, cache.nuisance_test)
    metrics = regression_metrics(y, pred, base_pred)
    fold_counts = np.asarray(fold_candidate_counts, dtype=float)
    return {
        **metrics,
        "n_subjects": int(y.shape[0]),
        "n_original_fibers": reduced.n_original_fibers,
        "n_candidate_union_fibers": int(reduced.x.shape[1]),
        "n_full_candidate_fibers": reduced.n_full_candidate_fibers,
        "fold_n_candidate_fibers_min": int(np.min(fold_counts)) if fold_counts.size else 0,
        "fold_n_candidate_fibers_median": float(np.median(fold_counts)) if fold_counts.size else 0.0,
        "fold_n_candidate_fibers_max": int(np.max(fold_counts)) if fold_counts.size else 0,
        "fold_n_sweet_selected_min": int(np.min(selected_sweet_counts)) if selected_sweet_counts else 0,
        "fold_n_sour_selected_min": int(np.min(selected_sour_counts)) if selected_sour_counts else 0,
        "all_predictions_finite": bool(np.all(np.isfinite(pred)) and np.all(np.isfinite(base_pred))),
    }


def _load_score_columns(path: Path) -> dict[str, np.ndarray]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"empty scores table: {path}")
    columns = {key: [] for key in rows[0].keys()}
    for row in rows:
        for key in columns:
            columns[key].append(row.get(key, ""))
    return {key: np.asarray(values) for key, values in columns.items()}


def _float_column(table: dict[str, np.ndarray], column: str) -> np.ndarray:
    if column not in table:
        raise KeyError(f"missing score column {column!r}")
    return np.asarray(table[column], dtype=float)


def run_target_smoke_permutation(
    target: NormativeFiberTarget,
    *,
    n_permutations: int,
    seed: int = 42,
    tier: str = "smoke",
) -> dict[str, Any]:
    provenance = git_provenance()
    suffix = permutation_suffix_for_tier(tier)
    x = np.load(target.x_path, mmap_mode="r")
    fiber_ids = np.load(target.fiber_ids_path, mmap_mode="r")
    reduced = prepare_candidate_union(x=x, fiber_ids=fiber_ids, tau=target.tau, min_coverage=target.min_coverage)
    score_columns = _load_score_columns(target.scores_csv)
    y_post = _float_column(score_columns, target.outcome_column)
    nuisance = np.column_stack([_float_column(score_columns, column) for column in target.nuisance_columns])
    fold_caches = build_fold_fiber_caches(reduced, nuisance)
    observed = normative_fiber_loocv_statistic(
        reduced=reduced,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        fold_caches=fold_caches,
    )
    y_perm = freedman_lane_permuted_outcomes(y_post, nuisance, n_permutations, seed=seed)
    null_stats = np.full(int(n_permutations), np.nan, dtype=np.float64)
    for idx, y_star in enumerate(y_perm):
        permuted = normative_fiber_loocv_statistic(
            reduced=reduced,
            y_post=y_star,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            fold_caches=fold_caches,
        )
        null_stats[idx] = permuted["spearman_rho"]
        if (idx + 1) % 100 == 0 or idx + 1 == int(n_permutations):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_permutations)} {tier} permutations", flush=True)

    prefix = file_prefix_for_manifest(target.manifest_path)
    null_path = target.branch_dir / f"{prefix}_{suffix}_null_stats.npy"
    summary_path = target.branch_dir / f"{prefix}_{suffix}_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_{suffix}_manifest.json"
    np.save(null_path, null_stats)
    summary = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "B": int(n_permutations),
        "seed": int(seed),
        "observed_loocv_spearman_rho": observed["spearman_rho"],
        "observed_loocv_pearson_r": observed["pearson_r"],
        "observed_mae": observed["mae"],
        "observed_rmse": observed["rmse"],
        "observed_q2": observed["q2"],
        "p_plus_one_two_sided": plus_one_two_sided_p(float(observed["spearman_rho"]), null_stats),
        "null_abs_ge_observed_count": int(np.sum(np.abs(null_stats[np.isfinite(null_stats)]) >= abs(float(observed["spearman_rho"])))),
        "null_finite_count": int(np.sum(np.isfinite(null_stats))),
        "n_original_fibers": observed["n_original_fibers"],
        "n_candidate_union_fibers": observed["n_candidate_union_fibers"],
        "n_full_candidate_fibers": observed["n_full_candidate_fibers"],
        "fold_n_candidate_fibers_min": observed["fold_n_candidate_fibers_min"],
        "fold_n_candidate_fibers_median": observed["fold_n_candidate_fibers_median"],
        "fold_n_candidate_fibers_max": observed["fold_n_candidate_fibers_max"],
        "permutation_status": "complete",
        "resampling_tier": tier,
        "generated_at": iso_now(),
    }
    write_csv(summary_path, [summary], list(summary.keys()))
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "model_id": target.model_id,
            "target_manifest": str(target.manifest_path),
            "n_permutations": int(n_permutations),
            "seed": int(seed),
            "resampling_tier": tier,
            "code_provenance": provenance,
            "method": f"Exact dTOR normative-fiber {tier} Freedman-Lane permutation over selected candidate union",
            "outputs": {"summary_csv": str(summary_path), "null_stats_npy": str(null_path), "manifest_json": str(manifest_path)},
        },
    )
    return summary


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_from_readiness_row(row: dict[str, str]) -> NormativeFiberTarget | None:
    model_id = row.get("model_id", "")
    if model_id not in DTOR_NORMATIVE_TARGET_IDS:
        return None
    if row.get("formal_readiness_status", "") != "READY_FOR_FORMAL_DRIVER":
        return None
    manifest_path = Path(row.get("latest_manifest", "")).expanduser().resolve()
    manifest = _load_json(manifest_path)
    outputs = manifest.get("outputs", {})
    branch_dir = manifest_path.parent
    scores_csv = Path(outputs.get("scores_csv", branch_dir / "missing_scores.csv")).expanduser().resolve()
    qc_path = Path(outputs.get("mapping_qc_json", "")).expanduser().resolve()
    qc = _load_json(qc_path)
    if model_id == "B_DTOR":
        preprocess_dir = Path(outputs["preprocess_dir"]).expanduser().resolve()
        return NormativeFiberTarget(
            model_id=model_id,
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X_HF_fiber_float32_subject_major.npy",
            fiber_ids_path=preprocess_dir / "fiber_ids.npy",
            scores_csv=scores_csv,
            outcome_column="Y_post",
            nuisance_columns=("Y_base",),
            scale_direction=str(qc["scale_direction"]),
            tau=float(qc["tau_v_per_m"]),
            min_coverage=int(qc["min_coverage"]),
        )
    if model_id == "D_DTOR":
        preprocess_dir = branch_dir.parent / "preprocess"
        return NormativeFiberTarget(
            model_id=model_id,
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X_ULF_only_fiber_float32_subject_major.npy",
            fiber_ids_path=(
                DEFAULT_VAL_ROOT
                / "summary/normative_connectome_fiber/hf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_3_m/peak_efield_tau800_primary/preprocess/fiber_ids.npy"
            ),
            scores_csv=scores_csv,
            outcome_column="Y_post",
            nuisance_columns=("Y_HF_ref",),
            scale_direction=str(qc["scale_direction"]),
            tau=float(qc["tau_v_per_m"]),
            min_coverage=int(qc["min_coverage"]),
        )
    return None


def discover_targets(readiness_csv: Path, requested_model_ids: set[str] | None = None) -> list[NormativeFiberTarget]:
    targets: list[NormativeFiberTarget] = []
    for row in read_csv(readiness_csv):
        target = _target_from_readiness_row(row)
        if target is None:
            continue
        if requested_model_ids and target.model_id not in requested_model_ids:
            continue
        targets.append(target)
    return targets


def run_smoke_permutation(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    tier = str(args.tier)
    if tier not in PERMUTATION_TIERS:
        raise ValueError(f"unsupported permutation tier: {tier}")
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError(f"no dTOR normative-fiber {tier} permutation targets found")
    rows = []
    for target in targets:
        print(f"Running dTOR normative-fiber {tier} permutation for {target.model_id} ({args.n_permutations} permutations)")
        rows.append(run_target_smoke_permutation(target, n_permutations=args.n_permutations, seed=args.seed, tier=tier))
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_cross_target_output_dir(tier)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = cross_target_output_stem_for_tier(tier)
    summary_path = output_dir / f"{output_stem}_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / f"{output_stem}_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "resampling_tier": tier,
            "n_targets": len(rows),
            "n_permutations": int(args.n_permutations),
            "seed": int(args.seed),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"dTOR normative-fiber {tier} permutation summary: {summary_path}")
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
        default=None,
        help="Cross-target permutation summary directory. Defaults depend on --tier.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    parser.add_argument("--tier", choices=sorted(PERMUTATION_TIERS), default="smoke", help="Permutation tier.")
    parser.add_argument("--n-permutations", type=int, default=1000, help="Number of Freedman-Lane permutations.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_smoke_permutation(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
