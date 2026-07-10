#!/usr/bin/env python3
"""Formal Freedman-Lane permutation for final STN/SNr direct-voxel models."""

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
    freedman_lane_permuted_outcomes,
    plus_one_two_sided_p,
    rank_columns,
    regression_metrics,
    residualize,
)
from stnsnr_run_provenance import git_provenance

FORMAL_DIRECT_MODEL_IDS = {"A", "C"}


@dataclass(frozen=True)
class DirectVoxelTarget:
    model_id: str
    manifest_path: Path
    branch_dir: Path
    x_path: Path
    subjects_csv: Path
    outcome_column: str
    nuisance_columns: tuple[str, ...]
    scale_direction: str
    tau: float
    min_coverage: int
    feature_ids_path: Path | None = None
    subject_order: tuple[str, ...] = ()
    output_prefix: str = ""
    final_record_hash: str = ""
    delta_hf_full_path: Path | None = None
    delta_hf_fold_path: Path | None = None
    spatial_reference_path: Path | None = None


@dataclass(frozen=True)
class FoldScoreOperator:
    heldout: int
    train: np.ndarray
    nuisance_train: np.ndarray
    nuisance_test: np.ndarray
    nuisance_rank_train: np.ndarray
    score_operator: np.ndarray
    n_valid_score_features: int


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
    if name == "direct_voxel_HF_generation_manifest.json":
        return "direct_voxel_HF"
    if name == "direct_voxel_ULF_only_generation_manifest.json":
        return "direct_voxel_ULF_only"
    raise ValueError(f"unsupported direct-voxel manifest: {manifest_path}")


def target_file_prefix(target: DirectVoxelTarget) -> str:
    """Return an explicit configured prefix or the legacy manifest-derived prefix."""
    return target.output_prefix or file_prefix_for_manifest(target.manifest_path)


def _as_2d(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr[:, None]
    return arr


def _nuisance_design(nuisance: np.ndarray) -> np.ndarray:
    cov = _as_2d(nuisance)
    return np.column_stack([np.ones(cov.shape[0], dtype=float), cov])


def _fit_predict_with_score(
    train_y: np.ndarray,
    train_score: np.ndarray,
    train_nuisance: np.ndarray,
    test_score: float,
    test_nuisance: np.ndarray,
) -> tuple[float, float]:
    train_cov = _as_2d(train_nuisance)
    test_cov = _as_2d(test_nuisance)
    train_design = np.column_stack([np.ones(train_y.shape[0], dtype=float), train_score, train_cov])
    test_design = np.column_stack([np.ones(1, dtype=float), np.asarray([test_score], dtype=float), test_cov.reshape(1, -1)])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return float((test_design @ beta)[0]), float(beta[1])


def _fit_predict_nuisance_only(train_y: np.ndarray, train_nuisance: np.ndarray, test_nuisance: np.ndarray) -> float:
    train_design = _nuisance_design(train_nuisance)
    test_cov = _as_2d(test_nuisance)
    test_design = np.column_stack([np.ones(1, dtype=float), test_cov.reshape(1, -1)])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return float((test_design @ beta)[0])


def _direction_sign(scale_direction: str) -> float:
    direction = scale_direction.strip().lower()
    if direction == "lower":
        return -1.0
    if direction == "higher":
        return 1.0
    raise ValueError("scale_direction must be 'lower' or 'higher'")


def build_fold_score_operators(
    *,
    x: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
    fold_nuisance: np.ndarray | None = None,
) -> list[FoldScoreOperator]:
    x_arr = np.asarray(x, dtype=float)
    nuisance_arr = _as_2d(nuisance)
    if x_arr.ndim != 2:
        raise ValueError("x must be a subject-by-feature matrix")
    if nuisance_arr.shape[0] != x_arr.shape[0]:
        raise ValueError("nuisance row count must match x")
    fold_nuisance_arr = None if fold_nuisance is None else np.asarray(fold_nuisance, dtype=float)
    if fold_nuisance_arr is not None and fold_nuisance_arr.shape != (
        x_arr.shape[0],
        x_arr.shape[0],
        nuisance_arr.shape[1],
    ):
        raise ValueError("fold_nuisance must be fold-by-subject-by-nuisance")

    direction_sign = _direction_sign(scale_direction)
    suprathreshold = x_arr > float(tau)
    coverage = suprathreshold.sum(axis=0).astype(np.int32)
    operators: list[FoldScoreOperator] = []
    for heldout in range(x_arr.shape[0]):
        train = np.array([idx for idx in range(x_arr.shape[0]) if idx != heldout], dtype=int)
        coverage_fold = coverage - suprathreshold[heldout].astype(np.int32)
        candidate = coverage_fold >= int(min_coverage)
        if not np.any(candidate):
            raise RuntimeError(f"empty fold candidate set for heldout index {heldout}")

        nuisance_fold = nuisance_arr if fold_nuisance_arr is None else fold_nuisance_arr[heldout]
        nuisance_train = nuisance_fold[train]
        nuisance_rank_train = rank_columns(nuisance_train)
        x_rank_train = rank_columns(x_arr[train][:, candidate])
        x_resid = residualize(x_rank_train, nuisance_rank_train)
        denom = np.sqrt(np.sum(x_resid * x_resid, axis=0))
        valid_local = np.isfinite(denom) & (denom > 0.0) & np.all(np.isfinite(x_resid), axis=0)
        if not np.any(valid_local):
            raise RuntimeError(f"no valid residualized exposure features for heldout index {heldout}")

        candidate_idx = np.flatnonzero(candidate)
        valid_idx = candidate_idx[valid_local]
        z = x_resid[:, valid_local] / denom[valid_local]
        score_operator = direction_sign * (x_arr[:, valid_idx] @ z.T) / float(valid_idx.size)
        operators.append(
            FoldScoreOperator(
                heldout=heldout,
                train=train,
                nuisance_train=nuisance_train,
                nuisance_test=nuisance_fold[[heldout]],
                nuisance_rank_train=nuisance_rank_train,
                score_operator=score_operator,
                n_valid_score_features=int(valid_idx.size),
            )
        )
    return operators


def direct_voxel_loocv_statistic(
    *,
    x: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
    fold_operators: list[FoldScoreOperator] | None = None,
    fold_nuisance: np.ndarray | None = None,
) -> dict[str, Any]:
    y = np.asarray(y_post, dtype=float)
    nuisance_arr = _as_2d(nuisance)
    operators = fold_operators or build_fold_score_operators(
        x=x,
        nuisance=nuisance_arr,
        scale_direction=scale_direction,
        tau=tau,
        min_coverage=min_coverage,
        fold_nuisance=fold_nuisance,
    )
    pred = np.full(y.shape[0], np.nan, dtype=float)
    base_pred = np.full(y.shape[0], np.nan, dtype=float)
    score = np.full(y.shape[0], np.nan, dtype=float)
    deltas = np.full(y.shape[0], np.nan, dtype=float)
    valid_counts: list[int] = []
    for operator in operators:
        train = operator.train
        y_rank_train = average_rank_1d(y[train])
        y_resid = residualize(y_rank_train, operator.nuisance_rank_train)
        denom = float(np.sqrt(np.sum(y_resid * y_resid)))
        if not np.isfinite(denom) or denom <= 0.0:
            continue
        all_scores = operator.score_operator @ (y_resid / denom)
        heldout_score = float(all_scores[operator.heldout])
        model_pred, delta = _fit_predict_with_score(
            y[train],
            all_scores[train],
            operator.nuisance_train,
            heldout_score,
            operator.nuisance_test,
        )
        pred[operator.heldout] = model_pred
        base_pred[operator.heldout] = _fit_predict_nuisance_only(y[train], operator.nuisance_train, operator.nuisance_test)
        score[operator.heldout] = heldout_score
        deltas[operator.heldout] = delta
        valid_counts.append(operator.n_valid_score_features)

    metrics = regression_metrics(y, pred, base_pred)
    return {
        **metrics,
        "n_subjects": int(y.shape[0]),
        "all_predictions_finite": bool(np.all(np.isfinite(pred)) and np.all(np.isfinite(base_pred))),
        "fold_n_valid_score_voxels_min": int(np.min(valid_counts)) if valid_counts else 0,
        "fold_n_valid_score_voxels_median": float(np.median(valid_counts)) if valid_counts else 0.0,
        "fold_n_valid_score_voxels_max": int(np.max(valid_counts)) if valid_counts else 0,
        "prediction_delta_min": float(np.nanmin(deltas)) if np.any(np.isfinite(deltas)) else np.nan,
        "prediction_delta_max": float(np.nanmax(deltas)) if np.any(np.isfinite(deltas)) else np.nan,
        "score_min": float(np.nanmin(score)) if np.any(np.isfinite(score)) else np.nan,
        "score_max": float(np.nanmax(score)) if np.any(np.isfinite(score)) else np.nan,
    }


def load_subject_table(path: Path) -> dict[str, np.ndarray]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"empty subject table: {path}")
    columns = {key: [] for key in rows[0].keys()}
    for row in rows:
        for key in columns:
            columns[key].append(row.get(key, ""))
    return {key: np.asarray(values) for key, values in columns.items()}


def _float_column(table: dict[str, np.ndarray], column: str) -> np.ndarray:
    if column not in table:
        raise KeyError(f"missing subject column {column!r}")
    return np.asarray(table[column], dtype=float)


def load_target_nuisance(
    target: DirectVoxelTarget,
    table: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray | None]:
    """Load full and fold-specific nuisance designs for one exact target."""
    base = np.column_stack([_float_column(table, column) for column in target.nuisance_columns])
    if target.delta_hf_full_path is None and target.delta_hf_fold_path is None:
        return base, None
    if target.delta_hf_full_path is None or target.delta_hf_fold_path is None:
        raise ValueError("adjusted formal target requires both full and fold-specific DeltaHF paths")
    full_delta = np.asarray(np.load(target.delta_hf_full_path, mmap_mode="r"), dtype=float)
    fold_delta = np.asarray(np.load(target.delta_hf_fold_path, mmap_mode="r"), dtype=float)
    n_subjects = base.shape[0]
    if full_delta.shape != (n_subjects,):
        raise ValueError("full DeltaHF scores must have one value per subject")
    if fold_delta.shape != (n_subjects, n_subjects):
        raise ValueError("fold-specific DeltaHF scores must be fold-by-subject")
    full_nuisance = np.column_stack([base, full_delta])
    fold_nuisance = np.concatenate(
        [np.broadcast_to(base, (n_subjects, *base.shape)), fold_delta[:, :, None]],
        axis=2,
    )
    return full_nuisance, fold_nuisance


def run_target_permutation(target: DirectVoxelTarget, *, n_permutations: int, seed: int = 42) -> dict[str, Any]:
    provenance = git_provenance()
    target.branch_dir.mkdir(parents=True, exist_ok=True)
    x = np.load(target.x_path)
    table = load_subject_table(target.subjects_csv)
    if target.subject_order:
        subject_column = next(
            (column for column in table if column.strip().lower() == "subject_id"),
            None,
        )
        if subject_column is None:
            raise KeyError("configured formal subject table is missing subject_id")
        observed_order = tuple(str(value) for value in table[subject_column])
        if observed_order != target.subject_order:
            raise ValueError("configured formal subject order mismatch")
    if target.feature_ids_path is not None:
        feature_ids = np.load(target.feature_ids_path, mmap_mode="r")
        if feature_ids.ndim != 1 or feature_ids.shape[0] != x.shape[1]:
            raise ValueError("configured formal feature axis does not match exposure columns")
    y_post = _float_column(table, target.outcome_column)
    nuisance, fold_nuisance = load_target_nuisance(target, table)
    fold_operators = build_fold_score_operators(
        x=x,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        tau=target.tau,
        min_coverage=target.min_coverage,
        fold_nuisance=fold_nuisance,
    )
    observed = direct_voxel_loocv_statistic(
        x=x,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        tau=target.tau,
        min_coverage=target.min_coverage,
        fold_operators=fold_operators,
    )
    y_perm = freedman_lane_permuted_outcomes(y_post, nuisance, n_permutations, seed=seed)
    null_stats = np.full(int(n_permutations), np.nan, dtype=np.float64)
    for idx, y_star in enumerate(y_perm):
        permuted = direct_voxel_loocv_statistic(
            x=x,
            y_post=y_star,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=target.tau,
            min_coverage=target.min_coverage,
            fold_operators=fold_operators,
        )
        null_stats[idx] = permuted["spearman_rho"]

    prefix = target_file_prefix(target)
    null_path = target.branch_dir / f"{prefix}_permutation_null_stats.npy"
    summary_path = target.branch_dir / f"{prefix}_permutation_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_permutation_manifest.json"
    np.save(null_path, null_stats)
    p_value = plus_one_two_sided_p(float(observed["spearman_rho"]), null_stats)
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
        "p_plus_one_two_sided": p_value,
        "null_abs_ge_observed_count": int(np.sum(np.abs(null_stats[np.isfinite(null_stats)]) >= abs(float(observed["spearman_rho"])))),
        "null_finite_count": int(np.sum(np.isfinite(null_stats))),
        "fold_n_valid_score_voxels_min": observed["fold_n_valid_score_voxels_min"],
        "fold_n_valid_score_voxels_median": observed["fold_n_valid_score_voxels_median"],
        "fold_n_valid_score_voxels_max": observed["fold_n_valid_score_voxels_max"],
        "permutation_status": "complete",
        "generated_at": iso_now(),
    }
    if target.final_record_hash:
        summary["final_record_hash"] = target.final_record_hash
    write_csv(summary_path, [summary], list(summary.keys()))
    formal_manifest = {
        "generated_at": iso_now(),
        "model_id": target.model_id,
        "target_manifest": str(target.manifest_path),
        "n_permutations": int(n_permutations),
        "seed": int(seed),
        "code_provenance": provenance,
        "method": "Freedman-Lane direct-voxel fold-level score operator",
        "outputs": {"summary_csv": str(summary_path), "null_stats_npy": str(null_path), "manifest_json": str(manifest_path)},
    }
    if target.final_record_hash:
        formal_manifest["final_record_hash"] = target.final_record_hash
    write_json(manifest_path, formal_manifest)
    return summary


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_from_readiness_row(row: dict[str, str]) -> DirectVoxelTarget | None:
    model_id = row.get("model_id", "")
    if model_id not in FORMAL_DIRECT_MODEL_IDS:
        return None
    if row.get("formal_readiness_status", "") != "READY_FOR_FORMAL_DRIVER":
        return None
    manifest_path = Path(row.get("latest_manifest", "")).expanduser().resolve()
    manifest = _load_json(manifest_path)
    branch_dir = manifest_path.parent
    outputs = manifest.get("outputs", {})
    preprocess_dir = Path(outputs.get("preprocess_dir", "")).expanduser() if outputs.get("preprocess_dir") else branch_dir.parent.parent / "preprocess"
    if model_id == "A":
        qc_path = preprocess_dir / "direct_voxel_HF_preprocess_qc.json"
        qc = _load_json(qc_path)
        return DirectVoxelTarget(
            model_id=model_id,
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X_HF_float32_subject_major.npy",
            subjects_csv=preprocess_dir / "subjects.csv",
            outcome_column="y_post",
            nuisance_columns=("y_base",),
            scale_direction=str(qc["scale_direction"]),
            tau=200.0,
            min_coverage=5,
        )
    if model_id == "C":
        qc_path = preprocess_dir / "direct_voxel_ULF_only_preprocess_qc.json"
        qc = _load_json(qc_path)
        return DirectVoxelTarget(
            model_id=model_id,
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X_ULF_only_float32_subject_major.npy",
            subjects_csv=preprocess_dir / "subjects.csv",
            outcome_column="y_post",
            nuisance_columns=("y_hf_ref",),
            scale_direction=str(qc["scale_direction"]),
            tau=200.0,
            min_coverage=5,
        )
    return None


def discover_targets(readiness_csv: Path, requested_model_ids: set[str] | None = None) -> list[DirectVoxelTarget]:
    targets: list[DirectVoxelTarget] = []
    for row in read_csv(readiness_csv):
        target = _target_from_readiness_row(row)
        if target is None:
            continue
        if requested_model_ids and target.model_id not in requested_model_ids:
            continue
        targets.append(target)
    return targets


def run_formal_permutation(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no direct-voxel formal targets found")
    rows = []
    for target in targets:
        print(f"Running direct-voxel formal permutation for {target.model_id} ({args.n_permutations} permutations)")
        rows.append(run_target_permutation(target, n_permutations=args.n_permutations, seed=args.seed))

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "direct_voxel_formal_permutation_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "direct_voxel_formal_permutation_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_permutations": int(args.n_permutations),
            "seed": int(args.seed),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"Direct-voxel formal permutation summary: {summary_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/direct_voxel_formal_permutation"),
        help="Cross-target direct-voxel formal permutation summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(FORMAL_DIRECT_MODEL_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-permutations", type=int, default=10000, help="Number of Freedman-Lane permutations.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_permutation(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
