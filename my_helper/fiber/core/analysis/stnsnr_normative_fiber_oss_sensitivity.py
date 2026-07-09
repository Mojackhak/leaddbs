#!/usr/bin/env python3
"""Run dTOR normative-fiber OSS activation sensitivity fitting."""

from __future__ import annotations

import argparse
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
    partial_spearman_matrix,
    pearson_corr_columns,
    plus_one_two_sided_p,
    rank_columns,
    regression_metrics,
    residualize,
)
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    NormativeFiberTarget,
    _float_column,
    _load_score_columns,
    _target_from_readiness_row,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    read_csv,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


DEFAULT_READINESS_CSV = DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_readiness/four_model_formal_readiness.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_oss_sensitivity"


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


def _oss_paths(target: NormativeFiberTarget) -> tuple[Path, Path]:
    if target.model_id == "B_DTOR":
        preprocess_dir = target.branch_dir / "preprocess"
    elif target.model_id == "D_DTOR":
        preprocess_dir = target.branch_dir.parent / "preprocess"
    else:
        raise RuntimeError(f"unsupported target for OSS sensitivity: {target.model_id}")
    return preprocess_dir / "X_oss_float32_fiber_major.npy", preprocess_dir / "oss_fiber_ids.npy"


def _load_oss_matrix(target: NormativeFiberTarget) -> tuple[np.ndarray, np.ndarray]:
    x_path, ids_path = _oss_paths(target)
    if not x_path.is_file() or not ids_path.is_file():
        raise RuntimeError(f"missing OSS sidecar files for {target.model_id}: {x_path}; {ids_path}")
    x = np.asarray(np.load(x_path), dtype=np.float32)
    ids = np.asarray(np.load(ids_path), dtype=np.int64)
    if x.ndim != 2 or ids.ndim != 1 or x.shape[1] != ids.shape[0]:
        raise RuntimeError(f"invalid OSS sidecar shape for {target.model_id}: x={x.shape}, ids={ids.shape}")
    if not np.all(np.isfinite(x)) or float(np.min(x)) < 0.0 or float(np.max(x)) > 1.0:
        raise RuntimeError(f"invalid OSS values for {target.model_id}")
    return x, ids


def _valid_oss_candidate_mask(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    finite = np.all(np.isfinite(arr), axis=0)
    nonconstant = np.nanmax(arr, axis=0) > np.nanmin(arr, axis=0)
    activated = np.nanmax(arr, axis=0) > 0.0
    return finite & nonconstant & activated


def _loocv_oss(
    *,
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    y = np.asarray(y_post, dtype=float)
    cov = _as_2d(nuisance)
    pred = np.full(y.shape[0], np.nan, dtype=float)
    base_pred = np.full(y.shape[0], np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    for heldout in range(y.shape[0]):
        train = np.array([idx for idx in range(y.shape[0]) if idx != heldout], dtype=int)
        x_train = x[train]
        candidate = _valid_oss_candidate_mask(x_train)
        if not np.any(candidate):
            continue
        nuisance_train = cov[train]
        nuisance_rank = rank_columns(nuisance_train)
        x_rank = rank_columns(np.asarray(x_train[:, candidate], dtype=float))
        x_resid = residualize(x_rank, nuisance_rank)
        denom = np.sqrt(np.sum(x_resid * x_resid, axis=0))
        valid_local = np.isfinite(denom) & (denom > 0.0) & np.all(np.isfinite(x_resid), axis=0)
        candidate_indices = np.flatnonzero(candidate)
        valid_candidate = np.zeros(candidate.shape, dtype=bool)
        valid_candidate[candidate_indices[valid_local]] = True
        if not np.any(valid_candidate):
            continue
        y_rank = average_rank_1d(y[train])
        y_resid = residualize(y_rank, nuisance_rank)
        y_denom = float(np.sqrt(np.sum(y_resid * y_resid)))
        if not np.isfinite(y_denom) or y_denom <= 0.0:
            continue
        z = x_resid[:, valid_local] / denom[valid_local]
        rho_fold = z.T @ (y_resid / y_denom)
        weights = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights[valid_candidate] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(x, weights, valid_candidate, fiber_ids=fiber_ids)
        fold_pred, _ = fit_linear_prediction(
            y[train],
            fold_net.net_score[train],
            nuisance_train,
            fold_net.net_score[[heldout]],
            cov[[heldout]],
        )
        pred[heldout] = fold_pred[0]
        base_pred[heldout] = _fit_baseline_with_covariates(y[train], nuisance_train, cov[[heldout]])
        fold_rows.append(
            {
                "heldout_index": heldout,
                "n_candidate_fibers": int(np.count_nonzero(valid_candidate)),
                "n_sweet_selected_fibers": int(fold_net.sweet_fiber_ids.size),
                "n_sour_selected_fibers": int(fold_net.sour_fiber_ids.size),
                "heldout_prediction": float(pred[heldout]),
                "heldout_baseline_prediction": float(base_pred[heldout]),
                "heldout_net_score_oss": float(fold_net.net_score[heldout]),
            }
        )
    metrics = regression_metrics(y, pred, base_pred)
    observed = {
        **metrics,
        "n_subjects": int(y.shape[0]),
        "n_original_fibers": int(x.shape[1]),
        "n_candidate_union_fibers": int(np.count_nonzero(_valid_oss_candidate_mask(x))),
        "n_full_candidate_fibers": int(np.count_nonzero(_valid_oss_candidate_mask(x))),
        "fold_n_candidate_fibers_min": int(min((row["n_candidate_fibers"] for row in fold_rows), default=0)),
        "fold_n_candidate_fibers_median": float(np.median([row["n_candidate_fibers"] for row in fold_rows])) if fold_rows else 0.0,
        "fold_n_candidate_fibers_max": int(max((row["n_candidate_fibers"] for row in fold_rows), default=0)),
        "all_predictions_finite": bool(np.all(np.isfinite(pred)) and np.all(np.isfinite(base_pred))),
        "predictions": pred,
        "baseline_predictions": base_pred,
    }
    return observed, fold_rows


def _full_sample_weights_scores(
    *,
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
) -> tuple[np.ndarray, Any]:
    candidate = _valid_oss_candidate_mask(x)
    rho = np.full(x.shape[1], np.nan, dtype=float)
    rho[candidate] = partial_spearman_matrix(y_post, x[:, candidate], nuisance)
    weights = np.full(x.shape[1], np.nan, dtype=np.float32)
    valid = candidate & np.isfinite(rho)
    weights[valid] = benefit_oriented_weights(rho[valid], scale_direction).astype(np.float32)
    scores = fiber_net_score(x, weights, valid, fiber_ids=fiber_ids)
    return weights, scores


def _plain_activation_controls(x: np.ndarray) -> dict[str, np.ndarray]:
    activated = x > 0
    count = activated.sum(axis=1).astype(float)
    total = np.sum(x, axis=1).astype(float)
    top5 = np.zeros(x.shape[0], dtype=float)
    for row_idx in range(x.shape[0]):
        values = np.asarray(x[row_idx, activated[row_idx]], dtype=float)
        if values.size:
            n_top = max(1, int(np.ceil(0.05 * values.size)))
            top5[row_idx] = float(np.mean(np.sort(values)[::-1][:n_top]))
    return {
        "PlainOSSActivationCount": count,
        "PlainOSSActivationSum": total,
        "PlainOSSActivationTop5": top5,
    }


def _fit_full_model_metrics(y: np.ndarray, score: np.ndarray, nuisance: np.ndarray) -> dict[str, float]:
    design = np.column_stack([np.ones(y.shape[0]), np.asarray(score, dtype=float), _as_2d(nuisance)])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    pred = design @ beta
    metrics = regression_metrics(y, pred)
    return {
        "coef_score": float(beta[1]),
        "in_sample_spearman": metrics["spearman_rho"],
        "in_sample_pearson": metrics["pearson_r"],
        "in_sample_mae": metrics["mae"],
        "in_sample_rmse": metrics["rmse"],
    }


def _comparison_rows(y: np.ndarray, net_score: np.ndarray, plain_top5: np.ndarray, nuisance: np.ndarray) -> list[dict[str, Any]]:
    rows = []
    for name, score in (
        ("plain_oss_activation_top5", plain_top5),
        ("oss_net_score", net_score),
    ):
        rows.append({"model": name, **_fit_full_model_metrics(y, score, nuisance)})
    joint_design = np.column_stack([np.ones(y.shape[0]), net_score, plain_top5, _as_2d(nuisance)])
    beta, *_ = np.linalg.lstsq(joint_design, y, rcond=None)
    pred = joint_design @ beta
    metrics = regression_metrics(y, pred)
    rows.append(
        {
            "model": "oss_net_score_plus_plain_top5",
            "coef_score": float(beta[1]),
            "coef_plain_top5": float(beta[2]),
            "in_sample_spearman": metrics["spearman_rho"],
            "in_sample_pearson": metrics["pearson_r"],
            "in_sample_mae": metrics["mae"],
            "in_sample_rmse": metrics["rmse"],
        }
    )
    return rows


def run_target_oss_sensitivity(target: NormativeFiberTarget, *, n_permutations: int, seed: int) -> dict[str, Any]:
    provenance = git_provenance()
    x, fiber_ids = _load_oss_matrix(target)
    score_columns = _load_score_columns(target.scores_csv)
    subjects = [str(subject) for subject in score_columns["subject_id"]]
    y_post = _float_column(score_columns, target.outcome_column)
    nuisance = np.column_stack([_float_column(score_columns, column) for column in target.nuisance_columns])
    observed, fold_rows = _loocv_oss(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
    )
    weights, scores = _full_sample_weights_scores(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
    )
    plain = _plain_activation_controls(x)
    peak_score_column = "NetFiberScore" if target.model_id == "B_DTOR" else "NetULFFiberScore"
    peak_score = _float_column(score_columns, peak_score_column)
    score_corr = float(pearson_corr_columns(scores.net_score, peak_score)[0])
    if not observed["all_predictions_finite"] or not np.isfinite(scores.net_score).all() or np.nanmax(x) <= 0:
        oss_result_status = "failed_activation_degenerate"
    elif score_corr > 0:
        oss_result_status = "passed_activation_consistent"
    else:
        oss_result_status = "passed_activation_model_dependent"

    y_perm = freedman_lane_permuted_outcomes(y_post, nuisance, int(n_permutations), seed=seed)
    null_stats = np.full(int(n_permutations), np.nan, dtype=float)
    for idx, y_star in enumerate(y_perm):
        permuted, _ = _loocv_oss(
            x=x,
            fiber_ids=fiber_ids,
            y_post=y_star,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
        )
        null_stats[idx] = permuted["spearman_rho"]
        if (idx + 1) % 100 == 0 or idx + 1 == int(n_permutations):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_permutations)} OSS smoke permutations", flush=True)

    prefix = file_prefix_for_manifest(target.manifest_path)
    branch_dir = target.branch_dir
    oss_prefix = f"{prefix}_oss"
    activation_summary_path = branch_dir / f"{prefix}_oss_activation_matrix_summary.csv"
    loocv_path = branch_dir / f"{prefix}_oss_loocv_predictions.csv"
    permutation_summary_path = branch_dir / f"{prefix}_oss_permutation_summary.csv"
    null_path = branch_dir / f"{prefix}_oss_permutation_null_stats.npy"
    weights_path = branch_dir / f"{prefix}_oss_weights.csv"
    scores_path = branch_dir / f"{prefix}_oss_scores.csv"
    plain_summary_path = branch_dir / f"{prefix}_plain_oss_activation_summary.csv"
    plain_comparison_path = branch_dir / f"{prefix}_plain_oss_activation_model_comparison.csv"
    status_path = branch_dir / f"{prefix}_oss_sensitivity_status.json"
    manifest_path = branch_dir / f"{prefix}_oss_sensitivity_manifest.json"

    np.save(null_path, null_stats)
    activation_summary = {
        "model_id": target.model_id,
        "oss_result_status": oss_result_status,
        "x_oss_shape": f"{x.shape[0]}x{x.shape[1]}",
        "x_oss_min": float(np.min(x)),
        "x_oss_max": float(np.max(x)),
        "x_oss_nonzero_count": int(np.count_nonzero(x)),
        "x_oss_nonzero_fraction": float(np.count_nonzero(x) / x.size),
        "n_valid_oss_candidate_fibers": int(np.count_nonzero(_valid_oss_candidate_mask(x))),
        "corr_net_score_oss_vs_peak": score_corr,
        "generated_at": iso_now(),
    }
    write_csv(activation_summary_path, [activation_summary], list(activation_summary.keys()))

    prediction_rows = []
    for idx, subject_id in enumerate(subjects):
        prediction_rows.append(
            {
                "model_id": target.model_id,
                "subject_id": subject_id,
                "Y_post": float(y_post[idx]),
                "prediction_oss": float(observed["predictions"][idx]),
                "prediction_baseline": float(observed["baseline_predictions"][idx]),
                "NetFiberScore_OSS" if target.model_id == "B_DTOR" else "NetULFFiberScore_OSS": float(scores.net_score[idx]),
                "PlainOSSActivationTop5": float(plain["PlainOSSActivationTop5"][idx]),
            }
        )
    write_csv(loocv_path, prediction_rows, list(prediction_rows[0].keys()))
    for idx, row in enumerate(fold_rows):
        row["subject_id"] = subjects[int(row["heldout_index"])]

    weight_rows = []
    for idx, fiber_id in enumerate(fiber_ids):
        weight_rows.append(
            {
                "fiber_id": int(fiber_id),
                "weight_oss": float(weights[idx]) if np.isfinite(weights[idx]) else "",
                "is_candidate": bool(np.isfinite(weights[idx])),
            }
        )
    write_csv(weights_path, weight_rows, ["fiber_id", "weight_oss", "is_candidate"])

    score_name = "NetFiberScore_OSS" if target.model_id == "B_DTOR" else "NetULFFiberScore_OSS"
    score_rows = []
    for idx, subject_id in enumerate(subjects):
        score_rows.append(
            {
                "subject_id": subject_id,
                "SweetPeak5_OSS": float(scores.sweet_peak5[idx]),
                "SourPeak5_OSS": float(scores.sour_peak5[idx]),
                score_name: float(scores.net_score[idx]),
                "PlainOSSActivationCount": float(plain["PlainOSSActivationCount"][idx]),
                "PlainOSSActivationSum": float(plain["PlainOSSActivationSum"][idx]),
                "PlainOSSActivationTop5": float(plain["PlainOSSActivationTop5"][idx]),
                "is_primary_score": True,
            }
        )
    write_csv(scores_path, score_rows, list(score_rows[0].keys()))
    write_csv(plain_summary_path, score_rows, list(score_rows[0].keys()))
    comparison_rows = _comparison_rows(y_post, scores.net_score, plain["PlainOSSActivationTop5"], nuisance)
    write_csv(plain_comparison_path, comparison_rows, sorted({key for row in comparison_rows for key in row.keys()}))

    permutation_summary = {
        "model_id": target.model_id,
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
        "oss_result_status": oss_result_status,
        "permutation_status": "complete",
        "resampling_tier": "oss_smoke",
        "generated_at": iso_now(),
    }
    write_csv(permutation_summary_path, [permutation_summary], list(permutation_summary.keys()))
    status = {
        **activation_summary,
        **permutation_summary,
        "technical_pass_criteria": {
            "oss_activation_matrix_not_all_nan": bool(np.all(np.isfinite(x))),
            "oss_activation_matrix_not_all_zero": bool(np.count_nonzero(x) > 0),
            "oss_net_score_nonzero_variance": bool(np.nanmax(scores.net_score) > np.nanmin(scores.net_score)),
            "oss_loocv_fit": bool(observed["all_predictions_finite"]),
            "oss_smoke_permutation_complete": True,
            "plain_oss_activation_top5_computable": bool(np.all(np.isfinite(plain["PlainOSSActivationTop5"]))),
        },
        "code_provenance": provenance,
        "outputs": {
            "activation_matrix_summary_csv": str(activation_summary_path),
            "loocv_predictions_csv": str(loocv_path),
            "permutation_summary_csv": str(permutation_summary_path),
            "permutation_null_stats_npy": str(null_path),
            "weights_csv": str(weights_path),
            "scores_csv": str(scores_path),
            "plain_activation_summary_csv": str(plain_summary_path),
            "plain_activation_model_comparison_csv": str(plain_comparison_path),
            "status_json": str(status_path),
            "manifest_json": str(manifest_path),
        },
    }
    write_json(status_path, status)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "model_id": target.model_id,
            "target_manifest": str(target.manifest_path),
            "n_permutations": int(n_permutations),
            "seed": int(seed),
            "code_provenance": provenance,
            "method": "dTOR normative-fiber OSS activation sensitivity with stored float32 p(A)",
            "outputs": status["outputs"],
        },
    )
    return {
        **permutation_summary,
        "manifest_path": str(manifest_path),
        "status_json": str(status_path),
        "activation_summary_csv": str(activation_summary_path),
    }


def run_oss_sensitivity(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    targets = [target for target in targets if target.model_id in DTOR_NORMATIVE_TARGET_IDS]
    if not targets:
        raise RuntimeError("no dTOR normative-fiber targets found for OSS sensitivity")
    rows: list[dict[str, Any]] = []
    for target in targets:
        print(f"Running normative-fiber OSS sensitivity for {target.model_id} ({args.n_permutations} smoke permutations)")
        rows.append(run_target_oss_sensitivity(target, n_permutations=args.n_permutations, seed=args.seed))
    summary_path = output_dir / "normative_fiber_oss_sensitivity_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "normative_fiber_oss_sensitivity_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_permutations": int(args.n_permutations),
            "seed": int(args.seed),
            "code_provenance": git_provenance(),
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"OSS sensitivity summary: {summary_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-csv", default=str(DEFAULT_READINESS_CSV), help="Formal readiness CSV.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Cross-target OSS sensitivity summary directory.")
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-permutations", type=int, default=1000, help="Smoke Freedman-Lane permutation count.")
    parser.add_argument("--seed", type=int, default=42, help="Permutation seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_oss_sensitivity(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
