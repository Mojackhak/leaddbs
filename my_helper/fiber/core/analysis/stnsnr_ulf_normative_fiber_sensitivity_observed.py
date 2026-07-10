#!/usr/bin/env python3
"""Observed-only D normative-fiber gain and total-ULF sensitivity branches."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT, infer_scale_direction
from stnsnr_four_model_stats import (
    NormativeFiberScoreConfig,
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    fiber_net_score,
    fit_linear_prediction,
    partial_spearman_matrix,
    regression_metrics,
    score_support_fields,
    suprathreshold_matrix,
)
from stnsnr_hf_normative_fiber_smoke import NORMATIVE_FIBER_SCORE_SUPPORT_FIELDS
from stnsnr_hf_direct_voxel_smoke import slugify
from stnsnr_io import iso_now, read_csv, write_csv, write_json
from stnsnr_ulf_direct_voxel_sensitivity_observed import (
    _branch_covariates,
    _configured_delta,
    _configured_score_columns,
    _support_diagnostic,
    as_2d_covariates,
    fit_baseline_prediction,
)
from stnsnr_ulf_normative_fiber_observed import (
    CONNECTOMES,
    ULF_NORM_FIBER_PRIMARY_TAU,
    tau_slug,
)


DEFAULT_OUTPUT_ROOT = DEFAULT_VAL_ROOT / "summary/normative_connectome_fiber/ulf"
DEFAULT_POST_SCALE = "MDS-UPDRS III score (STN+SNr, 3 m)"
DEFAULT_CONNECTOMES = ["ppmi", "dtor"]


@dataclass(frozen=True)
class FiberSensitivityInputs:
    subject_ids: list[str]
    y_post: np.ndarray
    y_hf_ref: np.ndarray
    gain: np.ndarray
    delta_hfscore: np.ndarray
    x_ulf_only: np.ndarray
    x_ulf_total: np.ndarray
    fiber_ids: np.ndarray
    scale_direction: str
    tau: float
    min_coverage: int
    output_root: Path
    post_scale: str
    hf_reference_scale: str
    connectome_key: str
    connectome_slug: str
    selected_tau: float
    selected_coverage: int


def parse_connectomes(value: str) -> list[str]:
    connectomes = [item.strip() for item in str(value).split(",") if item.strip()]
    if not connectomes:
        raise ValueError("--connectomes must include at least one connectome key")
    unknown = [item for item in connectomes if item not in CONNECTOMES]
    if unknown:
        raise ValueError(f"unsupported connectomes: {', '.join(unknown)}")
    return connectomes


def compute_observed_fiber_sensitivity_branch(
    *,
    branch_name: str,
    exposure: np.ndarray,
    outcome: np.ndarray,
    covariates: np.ndarray | None,
    covariate_names: list[str],
    scale_direction: str,
    tau: float,
    min_coverage: int,
    subject_ids: list[str],
    fiber_ids: np.ndarray,
    fold_covariates: np.ndarray | None = None,
    score_config: NormativeFiberScoreConfig | None = None,
) -> dict[str, Any]:
    policy = score_config or NormativeFiberScoreConfig()
    x = np.asarray(exposure, dtype=np.float32)
    y = np.asarray(outcome, dtype=float)
    cov_full = as_2d_covariates(covariates, y.shape[0])
    cov_folds = None if fold_covariates is None else np.asarray(fold_covariates, dtype=float)
    if cov_folds is not None:
        if cov_folds.ndim == 2:
            cov_folds = cov_folds[:, :, None]
        if cov_folds.shape[:2] != (y.shape[0], y.shape[0]):
            raise ValueError("fold_covariates must be fold-by-subject")
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError(f"empty sensitivity fiber candidate set for {branch_name}")
    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_candidate = partial_spearman_matrix(y, np.asarray(x[:, candidate]), cov_full if cov_full.shape[1] else None)
    rho[candidate] = rho_candidate.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_net = fiber_net_score(
        x,
        weights,
        candidate,
        fiber_ids=fiber_ids,
        score_config=policy,
    )
    full_support = score_support_fields(full_net, policy)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_ids):
        row = {
            "subject_id": subject_id,
            "Y_sensitivity": float(y[idx]),
            "SweetPeak5": float(full_net.sweet_peak5[idx]),
            "SourPeak5": float(full_net.sour_peak5[idx]),
            "NetULFFiberSensitivityScore": float(full_net.net_score[idx]),
            "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
            "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
            "n_sweet_peak_fibers": int(full_net.n_sweet_peak_fibers),
            "n_sour_peak_fibers": int(full_net.n_sour_peak_fibers),
            **full_support,
            "score_map_source": "full_sample",
            "is_primary_score": False,
        }
        for cov_idx, name in enumerate(covariate_names):
            row[name] = float(cov_full[idx, cov_idx])
        score_rows.append(row)

    n_subjects = y.shape[0]
    loocv_pred = np.full(n_subjects, np.nan, dtype=float)
    loocv_base_pred = np.full(n_subjects, np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    fold_candidate_counts: list[int] = []
    for heldout in range(n_subjects):
        train = np.array([idx for idx in range(n_subjects) if idx != heldout], dtype=int)
        fold_cov = cov_full if cov_folds is None else cov_folds[heldout]
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty sensitivity fold candidate set for held-out {subject_ids[heldout]}")
        fold_candidate_counts.append(int(np.count_nonzero(candidate_fold)))
        rho_fold = partial_spearman_matrix(
            y[train],
            np.asarray(x[train][:, candidate_fold]),
            fold_cov[train] if fold_cov.shape[1] else None,
        )
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(
            x,
            weights_fold,
            candidate_fold,
            fiber_ids=fiber_ids,
            score_config=policy,
        )
        fold_support = score_support_fields(fold_net, policy)
        pred, beta = fit_linear_prediction(
            y[train],
            fold_net.net_score[train],
            fold_cov[train] if fold_cov.shape[1] else None,
            fold_net.net_score[[heldout]],
            fold_cov[[heldout]] if fold_cov.shape[1] else None,
        )
        base_pred, base_beta = fit_baseline_prediction(
            y[train], fold_cov[train], fold_cov[[heldout]]
        )
        loocv_pred[heldout] = pred[0]
        loocv_base_pred[heldout] = base_pred[0]
        row = {
            "fold_id": heldout + 1,
            "heldout_subject_id": subject_ids[heldout],
            "Y_sensitivity": float(y[heldout]),
            "SweetPeak5_LOOCV": float(fold_net.sweet_peak5[heldout]),
            "SourPeak5_LOOCV": float(fold_net.sour_peak5[heldout]),
            "NetULFFiberSensitivityScore_LOOCV": float(fold_net.net_score[heldout]),
            "prediction_NetFiberScore_model": float(pred[0]),
            "prediction_baseline_only": float(base_pred[0]),
            "residual_NetFiberScore_model": float(y[heldout] - pred[0]),
            "residual_baseline_only": float(y[heldout] - base_pred[0]),
            "n_train": int(train.size),
            "n_candidate_fibers": int(np.count_nonzero(candidate_fold)),
            "n_sweet_selected_fibers": int(fold_net.sweet_fiber_ids.size),
            "n_sour_selected_fibers": int(fold_net.sour_fiber_ids.size),
            **fold_support,
            "delta_NetULFFiberSensitivityScore": float(beta[1]),
        }
        for cov_idx, name in enumerate(covariate_names):
            row[name] = float(fold_cov[heldout, cov_idx])
            row[f"beta_{name}"] = float(beta[2 + cov_idx])
            row[f"baseline_beta_{name}"] = float(base_beta[1 + cov_idx])
        fold_rows.append(row)

    fold_counts = np.asarray(fold_candidate_counts, dtype=float)
    metrics = regression_metrics(y, loocv_pred, loocv_base_pred)
    return {
        "branch_name": branch_name,
        "coverage": coverage,
        "rho": rho,
        "weights": weights,
        "candidate": candidate,
        "score_rows": score_rows,
        "fold_rows": fold_rows,
        "metrics": metrics,
        "n_candidate_fibers": int(np.count_nonzero(candidate)),
        "fold_n_candidate_fibers_min": int(np.nanmin(fold_counts)) if fold_counts.size else 0,
        "fold_n_candidate_fibers_median": float(np.nanmedian(fold_counts)) if fold_counts.size else 0.0,
        "fold_n_candidate_fibers_max": int(np.nanmax(fold_counts)) if fold_counts.size else 0,
        "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
        "score_support": full_support,
        "all_predictions_finite": bool(np.all(np.isfinite(loocv_pred)) and np.all(np.isfinite(loocv_base_pred))),
    }


def write_fiber_sensitivity_branch(
    *,
    branch_dir: Path,
    branch: dict[str, Any],
    inputs: FiberSensitivityInputs,
    outcome_label: str,
    exposure_label: str,
    covariate_names: list[str],
) -> dict[str, Any]:
    branch_dir.mkdir(parents=True, exist_ok=True)
    candidate_indices = np.where(branch["candidate"])[0]
    weight_rows = [
        {
            "fiber_id": int(inputs.fiber_ids[idx]),
            "coverage": int(branch["coverage"][idx]),
            "rho_ULF_sensitivity": float(branch["rho"][idx]) if np.isfinite(branch["rho"][idx]) else "",
            "M_ULF_sensitivity": float(branch["weights"][idx]) if np.isfinite(branch["weights"][idx]) else "",
            "is_candidate": True,
        }
        for idx in candidate_indices
    ]
    write_csv(
        branch_dir / "normative_ULF_fiber_weights.csv",
        weight_rows,
        ["fiber_id", "coverage", "rho_ULF_sensitivity", "M_ULF_sensitivity", "is_candidate"],
    )
    score_fields = [
        "subject_id",
        "Y_sensitivity",
        *covariate_names,
        "SweetPeak5",
        "SourPeak5",
        "NetULFFiberSensitivityScore",
        "n_sweet_selected_fibers",
        "n_sour_selected_fibers",
        "n_sweet_peak_fibers",
        "n_sour_peak_fibers",
        *NORMATIVE_FIBER_SCORE_SUPPORT_FIELDS,
        "score_map_source",
        "is_primary_score",
    ]
    fold_fields = [
        "fold_id",
        "heldout_subject_id",
        "Y_sensitivity",
        *covariate_names,
        "SweetPeak5_LOOCV",
        "SourPeak5_LOOCV",
        "NetULFFiberSensitivityScore_LOOCV",
        "prediction_NetFiberScore_model",
        "prediction_baseline_only",
        "residual_NetFiberScore_model",
        "residual_baseline_only",
        "n_train",
        "n_candidate_fibers",
        "n_sweet_selected_fibers",
        "n_sour_selected_fibers",
        *NORMATIVE_FIBER_SCORE_SUPPORT_FIELDS,
        "delta_NetULFFiberSensitivityScore",
        *[f"beta_{name}" for name in covariate_names],
        *[f"baseline_beta_{name}" for name in covariate_names],
    ]
    write_csv(branch_dir / "normative_ULF_fiber_scores.csv", branch["score_rows"], score_fields)
    write_csv(branch_dir / "normative_ULF_fiber_loocv_predictions.csv", branch["fold_rows"], fold_fields)
    qc = {
        "generated_at": iso_now(),
        "model": "ULF normative fiber sensitivity",
        "branch": branch["branch_name"],
        "post_scale": inputs.post_scale,
        "hf_reference_scale": inputs.hf_reference_scale,
        "connectome_key": inputs.connectome_key,
        "connectome_slug": inputs.connectome_slug,
        "outcome_label": outcome_label,
        "exposure_label": exposure_label,
        "scale_direction": inputs.scale_direction,
        "n_subjects": len(inputs.subject_ids),
        "selected_tau_v_per_m": float(inputs.selected_tau),
        "selected_coverage": int(inputs.selected_coverage),
        "tau_v_per_m": float(inputs.tau),
        "min_coverage": int(inputs.min_coverage),
        "n_candidate_fibers": int(branch["n_candidate_fibers"]),
        "fold_n_candidate_fibers_min": int(branch["fold_n_candidate_fibers_min"]),
        "fold_n_candidate_fibers_median": float(branch["fold_n_candidate_fibers_median"]),
        "fold_n_candidate_fibers_max": int(branch["fold_n_candidate_fibers_max"]),
        "n_sweet_selected_fibers": int(branch["n_sweet_selected_fibers"]),
        "n_sour_selected_fibers": int(branch["n_sour_selected_fibers"]),
        "all_predictions_finite": bool(branch["all_predictions_finite"]),
        "loocv_metrics": branch["metrics"],
        "resampling_status": "not_run_observed_only",
    }
    manifest = {
        "generated_at": iso_now(),
        "model": "ULF normative fiber sensitivity",
        "branch": branch["branch_name"],
        "status": "PASS",
        "post_scale": inputs.post_scale,
        "hf_reference_scale": inputs.hf_reference_scale,
        "connectome_key": inputs.connectome_key,
        "connectome_slug": inputs.connectome_slug,
        "outcome_label": outcome_label,
        "exposure_label": exposure_label,
        "parameters": {
            "selected_tau_v_per_m": float(inputs.selected_tau),
            "selected_coverage": int(inputs.selected_coverage),
            "tau_v_per_m": float(inputs.tau),
            "min_coverage": int(inputs.min_coverage),
        },
        "resampling_status": "not_run_observed_only",
        "resampling_reason": "observed sensitivity branch; formal resampling restricted to selected final model",
        "outputs": {
            "branch_dir": str(branch_dir),
            "weights_csv": str(branch_dir / "normative_ULF_fiber_weights.csv"),
            "scores_csv": str(branch_dir / "normative_ULF_fiber_scores.csv"),
            "loocv_predictions_csv": str(branch_dir / "normative_ULF_fiber_loocv_predictions.csv"),
            "mapping_qc_json": str(branch_dir / "normative_ULF_fiber_mapping_qc.json"),
            "generation_manifest_json": str(branch_dir / "normative_ULF_fiber_generation_manifest.json"),
        },
    }
    write_json(branch_dir / "normative_ULF_fiber_mapping_qc.json", qc)
    write_json(branch_dir / "normative_ULF_fiber_generation_manifest.json", manifest, add_code_provenance=True)
    return {
        "branch": branch["branch_name"],
        "branch_dir": str(branch_dir),
        "spearman_rho": branch["metrics"].get("spearman_rho", np.nan),
        "q2": branch["metrics"].get("q2", np.nan),
        "resampling_status": "not_run_observed_only",
    }


def build_sensitivity_branches(inputs: FiberSensitivityInputs) -> list[dict[str, Any]]:
    gain_branch = compute_observed_fiber_sensitivity_branch(
        branch_name="normative_fiber_gain_endpoint",
        exposure=inputs.x_ulf_only,
        outcome=inputs.gain,
        covariates=inputs.delta_hfscore,
        covariate_names=["DeltaHFFiberScore"],
        scale_direction=inputs.scale_direction,
        tau=inputs.tau,
        min_coverage=inputs.min_coverage,
        subject_ids=inputs.subject_ids,
        fiber_ids=inputs.fiber_ids,
    )
    total_branch = compute_observed_fiber_sensitivity_branch(
        branch_name="normative_fiber_total_ulf_exposure",
        exposure=inputs.x_ulf_total,
        outcome=inputs.y_post,
        covariates=inputs.y_hf_ref,
        covariate_names=["Y_HF_ref"],
        scale_direction=inputs.scale_direction,
        tau=inputs.tau,
        min_coverage=inputs.min_coverage,
        subject_ids=inputs.subject_ids,
        fiber_ids=inputs.fiber_ids,
    )
    return [
        write_fiber_sensitivity_branch(
            branch_dir=inputs.output_root / "normative_fiber_gain_endpoint",
            branch=gain_branch,
            inputs=inputs,
            outcome_label="Gain_chronic",
            exposure_label="HF_overlap_excluded_ULF_only",
            covariate_names=["DeltaHFFiberScore"],
        ),
        write_fiber_sensitivity_branch(
            branch_dir=inputs.output_root / "normative_fiber_total_ulf_exposure",
            branch=total_branch,
            inputs=inputs,
            outcome_label="Y_post_chronic",
            exposure_label="total_ULF_component",
            covariate_names=["Y_HF_ref"],
        ),
    ]


def _configured_fiber_branch_result(
    *,
    name: str,
    exposure: np.ndarray,
    outcome: np.ndarray,
    covariates: np.ndarray | None,
    fold_covariates: np.ndarray | None,
    covariate_names: list[str],
    target: Any,
    fiber_ids: np.ndarray,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        branch = compute_observed_fiber_sensitivity_branch(
            branch_name=name,
            exposure=exposure,
            outcome=outcome,
            covariates=covariates,
            fold_covariates=fold_covariates,
            covariate_names=covariate_names,
            scale_direction=target.scale_direction,
            tau=float(target.selected_tau),
            min_coverage=int(target.selected_coverage),
            subject_ids=list(target.subject_order),
            fiber_ids=fiber_ids,
            score_config=target.score_config,
        )
    except (RuntimeError, ValueError) as exc:
        return {"status": "not_computable", "reason": str(exc)}, None
    return {
        "status": "complete",
        "branch": name,
        "loocv_metrics": branch["metrics"],
        "n_candidate_fibers": int(branch["n_candidate_fibers"]),
        "all_predictions_finite": bool(branch["all_predictions_finite"]),
    }, branch


def _configured_valid_fiber_columns(target: Any) -> tuple[np.ndarray, np.ndarray]:
    if target.valid_feature_ids_path is None:
        raise ValueError("configured normative-fiber sensitivity has no valid feature axis")
    parent = np.asarray(np.load(target.feature_ids_path, mmap_mode="r"), dtype=np.int64)
    valid = np.asarray(np.load(target.valid_feature_ids_path, mmap_mode="r"), dtype=np.int64)
    positions = {int(fiber_id): index for index, fiber_id in enumerate(parent)}
    try:
        columns = np.asarray([positions[int(fiber_id)] for fiber_id in valid], dtype=np.int64)
    except KeyError as exc:
        raise ValueError("valid fiber axis is not a subset of the parent axis") from exc
    if columns.size == 0 or np.any(columns[1:] <= columns[:-1]):
        raise ValueError("valid fiber axis must preserve nonempty parent-axis order")
    return columns, valid


def _fiber_collinearity_diagnostic(
    target: Any,
    branch: dict[str, Any] | None,
    y_hf_ref: np.ndarray,
    delta_full: np.ndarray | None,
) -> dict[str, Any]:
    if target.y_base_path is None:
        return {"status": "not_computable", "reason": "missing_y_base"}
    if branch is None:
        return {"status": "not_computable", "reason": "selected_branch_not_computable"}
    y_base = np.asarray(np.load(target.y_base_path, mmap_mode="r"), dtype=float)
    if y_base.shape != y_hf_ref.shape:
        return {"status": "not_computable", "reason": "y_base_shape_mismatch"}
    scores = np.asarray(
        [row["NetULFFiberSensitivityScore"] for row in branch["score_rows"]],
        dtype=float,
    )
    values = [scores, y_hf_ref]
    names = ["NetULFFiberScore", "Y_HF_ref"]
    if target.final_branch == "delta_hf_adjusted":
        if delta_full is None:
            return {"status": "not_computable", "reason": "missing_delta_hf"}
        values.append(delta_full)
        names.append("DeltaHFScore")
    values.append(y_base)
    names.append("Y_base")
    design = np.column_stack(values)
    if not np.all(np.isfinite(design)):
        return {"status": "not_computable", "reason": "nonfinite_collinearity_design"}
    centered = design - np.mean(design, axis=0, keepdims=True)
    scale = np.std(centered, axis=0, ddof=1)
    if np.any(scale <= 0):
        return {"status": "not_computable", "reason": "constant_collinearity_column"}
    standardized = centered / scale
    correlations = np.corrcoef(standardized, rowvar=False)
    off_diagonal = np.abs(correlations[np.triu_indices_from(correlations, k=1)])
    maximum = float(np.max(off_diagonal)) if off_diagonal.size else 0.0
    warning = "acceptable" if maximum < 0.85 else "high" if maximum < 0.95 else "severe"
    return {
        "status": "complete",
        "columns": names,
        "correlation_matrix": correlations.tolist(),
        "maximum_absolute_pairwise_correlation": maximum,
        "collinearity_warning": warning,
        "condition_number": float(np.linalg.cond(standardized)),
    }


def run_configured_additional_sensitivities(
    target: Any,
    *,
    enabled_analyses: tuple[str, ...],
) -> dict[str, Any]:
    """Run task-local ULF normative-fiber sensitivity models."""
    columns = _configured_score_columns(target)
    y_post = np.asarray(columns["Y_post"], dtype=float)
    y_hf_ref = np.asarray(columns["Y_HF_ref"], dtype=float)
    delta_full, delta_folds = _configured_delta(target)
    selected_parent = np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32)
    valid_columns, fiber_ids = _configured_valid_fiber_columns(target)
    selected_exposure = selected_parent[:, valid_columns]
    total_path = target.component_paths.get("ulf_component_exposure")
    analyses: dict[str, Any] = {}

    selected_adjusted = target.final_branch == "delta_hf_adjusted"
    selected_cov, selected_fold_cov, selected_names = _branch_covariates(
        y_hf_ref,
        delta_full,
        delta_folds,
        adjusted=selected_adjusted,
    )
    selected_result, selected_branch = _configured_fiber_branch_result(
        name=f"selected_{target.final_branch}",
        exposure=selected_exposure,
        outcome=y_post,
        covariates=selected_cov,
        fold_covariates=selected_fold_cov,
        covariate_names=selected_names,
        target=target,
        fiber_ids=fiber_ids,
    )

    if "nonfinal_branch" in enabled_analyses:
        nonfinal_adjusted = not selected_adjusted
        try:
            cov, fold_cov, names = _branch_covariates(
                y_hf_ref,
                delta_full,
                delta_folds,
                adjusted=nonfinal_adjusted,
            )
            analyses["nonfinal_branch"], _ = _configured_fiber_branch_result(
                name=("delta_hf_adjusted" if nonfinal_adjusted else "no_delta_hf"),
                exposure=selected_exposure,
                outcome=y_post,
                covariates=cov,
                fold_covariates=fold_cov,
                covariate_names=names,
                target=target,
                fiber_ids=fiber_ids,
            )
        except RuntimeError as exc:
            analyses["nonfinal_branch"] = {"status": "not_computable", "reason": str(exc)}

    if "gain" in enabled_analyses:
        gain = y_hf_ref - y_post if target.scale_direction == "lower" else y_post - y_hf_ref
        gain_cov = delta_full[:, None] if selected_adjusted and delta_full is not None else None
        gain_folds = delta_folds[:, :, None] if selected_adjusted and delta_folds is not None else None
        analyses["gain"], _ = _configured_fiber_branch_result(
            name="gain_endpoint",
            exposure=selected_exposure,
            outcome=gain,
            covariates=gain_cov,
            fold_covariates=gain_folds,
            covariate_names=(["DeltaHFScore"] if gain_cov is not None else []),
            target=target,
            fiber_ids=fiber_ids,
        )

    if "total_exposure" in enabled_analyses:
        if total_path is None:
            analyses["total_exposure"] = {
                "status": "not_computable",
                "reason": "missing_raw_ulf_component_exposure",
            }
        else:
            total_exposure = np.asarray(np.load(total_path, mmap_mode="r"), dtype=np.float32)
            analyses["total_exposure"], _ = _configured_fiber_branch_result(
                name="total_ulf_exposure",
                exposure=total_exposure[:, valid_columns],
                outcome=y_post,
                covariates=selected_cov,
                fold_covariates=selected_fold_cov,
                covariate_names=selected_names,
                target=target,
                fiber_ids=fiber_ids,
            )

    if "support" in enabled_analyses:
        analyses["support"] = _support_diagnostic(target)
    if "collinearity" in enabled_analyses:
        analyses["collinearity"] = _fiber_collinearity_diagnostic(
            target,
            selected_branch,
            y_hf_ref,
            delta_full,
        )
    analyses["selected_branch_reference"] = selected_result

    summary_path = target.output_root / "ulf_normative_fiber_additional_sensitivities.csv"
    write_csv(
        summary_path,
        [
            {
                "analysis": name,
                "status": result.get("status", ""),
                "reason": result.get("reason", ""),
            }
            for name, result in analyses.items()
        ],
        ["analysis", "status", "reason"],
    )
    return {
        "status": "complete",
        "analyses": analyses,
        "summary_csv": str(summary_path),
        "score": {
            "sweet_fraction": target.score_config.sweet_fraction,
            "sour_fraction": target.score_config.sour_fraction,
            "weighted_peak_fraction": target.score_config.weighted_peak_fraction,
            "sweet_selected_min_count": target.score_config.sweet_selected_min_count,
            "sour_selected_min_count": target.score_config.sour_selected_min_count,
            "weighted_peak_min_count": target.score_config.weighted_peak_min_count,
        },
    }


def _top_fraction_mean_rows(exposure: np.ndarray, fraction: float = 0.05) -> np.ndarray:
    x = np.asarray(exposure, dtype=float)
    if x.ndim != 2 or x.shape[1] == 0:
        raise ValueError("top-fraction exposure must be a nonempty subject-by-fiber matrix")
    count = max(1, int(np.ceil(x.shape[1] * float(fraction))))
    split = x.shape[1] - count
    return np.mean(np.partition(x, split, axis=1)[:, split:], axis=1)


def _top_fraction_mean(values: np.ndarray, fraction: float = 0.05) -> float:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("top-fraction values must be one-dimensional")
    if array.size == 0:
        return 0.0
    count = max(1, int(np.ceil(array.size * float(fraction))))
    return float(np.mean(np.partition(array, array.size - count)[-count:]))


def _plain_ulf_only_burden(
    target: Any,
) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    try:
        exposure = np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32)
    except (OSError, ValueError) as exc:
        return {
            "status": "not_computable",
            "reason": f"invalid_final_ulf_only_exposure:{exc}",
        }, None
    expected_shape = (len(target.subject_order), np.asarray(np.load(target.feature_ids_path)).size)
    if exposure.ndim != 2 or exposure.shape != expected_shape:
        return {
            "status": "not_computable",
            "reason": "final_ulf_only_exposure_shape_mismatch",
        }, None
    if not np.all(np.isfinite(exposure)):
        return {
            "status": "not_computable",
            "reason": "nonfinite_final_ulf_only_exposure",
        }, None

    touched = suprathreshold_matrix(exposure, float(target.selected_tau))
    coverage = coverage_from_suprathreshold(touched)
    candidate = candidate_mask_from_coverage(coverage, int(target.selected_coverage))
    if not np.any(candidate):
        return {"status": "not_computable", "reason": "empty_selected_candidate_universe"}, None

    counts = np.count_nonzero(touched & candidate[None, :], axis=1).astype(np.int64)
    if np.any(counts == 0):
        missing = [
            str(target.subject_order[index])
            for index in np.flatnonzero(counts == 0)
        ]
        return {
            "status": "not_computable",
            "reason": "no_touched_candidate_fibers",
            "affected_subject_ids": missing,
            "candidate_fiber_count": int(np.count_nonzero(candidate)),
        }, None

    sums = np.zeros(exposure.shape[0], dtype=np.float64)
    top5 = np.zeros(exposure.shape[0], dtype=np.float64)
    for index in range(exposure.shape[0]):
        values = exposure[index, touched[index] & candidate]
        sums[index] = np.sum(values, dtype=np.float64)
        top5[index] = _top_fraction_mean(values)
    values = {"touched_count": counts, "exposure_sum": sums, "exposure_top5": top5}
    return {
        "status": "complete",
        "definition": "top_5_percent_among_suprathreshold_selected_candidate_fibers",
        "selected_tau": float(target.selected_tau),
        "selected_coverage": int(target.selected_coverage),
        "candidate_fiber_count": int(np.count_nonzero(candidate)),
    }, values


def _fit_qc_ols(
    outcome: np.ndarray,
    predictors: list[np.ndarray],
    predictor_names: list[str],
) -> dict[str, Any]:
    y = np.asarray(outcome, dtype=float)
    columns = [np.asarray(values, dtype=float) for values in predictors]
    if any(values.shape != y.shape for values in columns):
        return {"status": "not_computable", "reason": "model_column_shape_mismatch"}
    design = np.column_stack([np.ones(y.size, dtype=float), *columns])
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(design)):
        return {"status": "not_computable", "reason": "nonfinite_model_design"}
    rank = int(np.linalg.matrix_rank(design))
    if rank < design.shape[1]:
        return {
            "status": "not_computable",
            "reason": "singular_model_design",
            "predictor_names": predictor_names,
            "design_rank": rank,
            "n_parameters": int(design.shape[1]),
        }
    if y.size <= design.shape[1]:
        return {
            "status": "not_computable",
            "reason": "insufficient_residual_degrees_of_freedom",
            "predictor_names": predictor_names,
        }

    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ beta
    residual = y - fitted
    residual_sum_squares = float(np.sum(residual * residual))
    total_sum_squares = float(np.sum((y - np.mean(y)) ** 2))
    if total_sum_squares <= 0:
        return {
            "status": "not_computable",
            "reason": "constant_outcome",
            "predictor_names": predictor_names,
        }
    r_squared = 1.0 - residual_sum_squares / total_sum_squares
    residual_degrees = y.size - design.shape[1]
    adjusted_r_squared = 1.0 - (1.0 - r_squared) * (y.size - 1) / residual_degrees
    coefficient_names = ["intercept", *predictor_names]
    return {
        "status": "complete",
        "method": "descriptive_full_sample_ols_qc",
        "predictor_names": predictor_names,
        "n_subjects": int(y.size),
        "n_parameters": int(design.shape[1]),
        "design_rank": rank,
        "coefficients": {
            name: float(value) for name, value in zip(coefficient_names, beta, strict=True)
        },
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "r_squared": float(r_squared),
        "adjusted_r_squared": float(adjusted_r_squared),
    }


def _branch_nuisance_model_comparisons(
    target: Any,
    plain_top5: np.ndarray | None,
) -> dict[str, Any]:
    branch = str(target.final_branch)
    nuisance_names = ["Y_HF_ref"]
    if branch == "delta_hf_adjusted":
        nuisance_names.append("DeltaHFScore")
    elif branch != "no_delta_hf":
        return {
            "status": "not_computable",
            "reason": "unsupported_realized_final_branch",
            "realized_final_branch": branch,
            "nuisance_columns": nuisance_names,
        }
    if plain_top5 is None:
        return {
            "status": "not_computable",
            "reason": "plain_ulf_only_exposure_not_computable",
            "realized_final_branch": branch,
            "nuisance_columns": nuisance_names,
        }

    try:
        columns = _configured_score_columns(target)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "not_computable",
            "reason": f"invalid_final_scores:{exc}",
            "realized_final_branch": branch,
            "nuisance_columns": nuisance_names,
        }
    required = ("Y_post", "Y_HF_ref", "NetULFFiberScore")
    if any(name not in columns for name in required):
        return {
            "status": "not_computable",
            "reason": "missing_final_score_columns",
            "realized_final_branch": branch,
            "nuisance_columns": nuisance_names,
        }

    nuisance = [np.asarray(columns["Y_HF_ref"], dtype=float)]
    if branch == "delta_hf_adjusted":
        if target.delta_full_path is None:
            return {
                "status": "not_computable",
                "reason": "missing_final_branch_delta_hf",
                "realized_final_branch": branch,
                "nuisance_columns": nuisance_names,
            }
        try:
            delta = np.asarray(np.load(target.delta_full_path, mmap_mode="r"), dtype=float)
        except (OSError, ValueError) as exc:
            return {
                "status": "not_computable",
                "reason": f"invalid_final_branch_delta_hf:{exc}",
                "realized_final_branch": branch,
                "nuisance_columns": nuisance_names,
            }
        if delta.shape != np.asarray(columns["Y_post"]).shape or not np.all(np.isfinite(delta)):
            return {
                "status": "not_computable",
                "reason": "invalid_final_branch_delta_hf",
                "realized_final_branch": branch,
                "nuisance_columns": nuisance_names,
            }
        nuisance.append(delta)

    outcome = np.asarray(columns["Y_post"], dtype=float)
    net_score = np.asarray(columns["NetULFFiberScore"], dtype=float)
    models = {
        "nuisance_only": _fit_qc_ols(outcome, nuisance, nuisance_names),
        "plain_plus_nuisance": _fit_qc_ols(
            outcome,
            [plain_top5, *nuisance],
            ["PlainULFOnlyExposureTop5", *nuisance_names],
        ),
        "net_plus_nuisance": _fit_qc_ols(
            outcome,
            [net_score, *nuisance],
            ["NetULFFiberScore", *nuisance_names],
        ),
        "joint": _fit_qc_ols(
            outcome,
            [net_score, plain_top5, *nuisance],
            ["NetULFFiberScore", "PlainULFOnlyExposureTop5", *nuisance_names],
        ),
    }
    status = "complete" if all(model["status"] == "complete" for model in models.values()) else "partial"
    result: dict[str, Any] = {
        "status": status,
        "method": "descriptive_full_sample_ols_qc",
        "realized_final_branch": branch,
        "nuisance_columns": nuisance_names,
        "models": models,
    }
    nuisance_model = models["nuisance_only"]
    if nuisance_model["status"] == "complete":
        result["comparisons_vs_nuisance"] = {
            name: {
                "r_squared_gain": float(model["r_squared"] - nuisance_model["r_squared"]),
                "rmse_reduction": float(nuisance_model["rmse"] - model["rmse"]),
            }
            for name, model in models.items()
            if name != "nuisance_only" and model["status"] == "complete"
        }
    return result


def _hf_out_of_support_burden(
    target: Any,
) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    matched = target.matched_hf_final
    if matched is None:
        return {"status": "not_computable", "reason": "missing_matched_hf_final"}, None
    hf_component_path = target.component_paths.get("hf_component_exposure")
    if hf_component_path is None:
        return {"status": "not_computable", "reason": "missing_hf_component_exposure"}, None
    reference_path = target.matched_hf_paths.get("exposure")
    hf_ids_path = target.matched_hf_paths.get("feature_ids")
    if reference_path is None or hf_ids_path is None:
        return {"status": "not_computable", "reason": "missing_matched_hf_candidate_inputs"}, None

    try:
        component = np.asarray(np.load(hf_component_path, mmap_mode="r"), dtype=np.float32)
        reference = np.asarray(np.load(reference_path, mmap_mode="r"), dtype=np.float32)
        ulf_ids = np.asarray(np.load(target.feature_ids_path, mmap_mode="r"))
        hf_ids = np.asarray(np.load(hf_ids_path, mmap_mode="r"))
    except (OSError, ValueError) as exc:
        return {"status": "not_computable", "reason": f"invalid_matched_hf_inputs:{exc}"}, None
    expected_shape = (len(target.subject_order), ulf_ids.size)
    if component.shape != expected_shape or reference.shape != expected_shape:
        return {"status": "not_computable", "reason": "matched_hf_exposure_shape_mismatch"}, None
    if hf_ids.shape != ulf_ids.shape or not np.array_equal(hf_ids, ulf_ids):
        return {"status": "not_computable", "reason": "matched_hf_feature_axis_mismatch"}, None
    if not np.all(np.isfinite(component)) or not np.all(np.isfinite(reference)):
        return {"status": "not_computable", "reason": "nonfinite_matched_hf_exposure"}, None

    tau = float(matched.selected_tau)
    reference_touched = suprathreshold_matrix(reference, tau)
    candidate = candidate_mask_from_coverage(
        coverage_from_suprathreshold(reference_touched),
        int(matched.selected_coverage),
    )
    if not np.any(candidate):
        return {"status": "not_computable", "reason": "empty_matched_hf_candidate_universe"}, None

    touched = suprathreshold_matrix(component, tau)
    suprathreshold = np.where(touched, component, 0.0)
    outside = touched & ~candidate[None, :]
    counts = np.count_nonzero(outside, axis=1).astype(np.int64)
    sums = np.sum(np.where(outside, component, 0.0), axis=1, dtype=np.float64)
    total_sums = np.sum(suprathreshold, axis=1, dtype=np.float64)
    fractions = np.divide(sums, total_sums, out=np.zeros_like(sums), where=total_sums > 0)
    top5 = np.asarray(
        [_top_fraction_mean(component[index, outside[index]]) for index in range(component.shape[0])],
        dtype=np.float64,
    )
    values = {
        "touched_count": counts,
        "exposure_sum": sums,
        "exposure_top5": top5,
        "exposure_fraction": fractions,
    }
    return {
        "status": "complete",
        "definition": "suprathreshold_hf_component_outside_matched_hf_candidate_universe",
        "matched_hf_final_model_id": str(matched.final_model_id),
        "matched_hf_tau": tau,
        "matched_hf_coverage": int(matched.selected_coverage),
        "hf_candidate_fiber_count": int(np.count_nonzero(candidate)),
    }, values


def _descriptive_burdens(
    target: Any,
) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    ulf_path = target.component_paths.get("ulf_component_exposure")
    if ulf_path is None:
        return {"status": "not_computable", "reason": "missing_raw_ulf_component_exposure"}, None
    try:
        ulf = np.asarray(np.load(ulf_path, mmap_mode="r"), dtype=np.float32)
    except (OSError, ValueError) as exc:
        return {"status": "not_computable", "reason": f"invalid_raw_ulf_component_exposure:{exc}"}, None
    expected_shape = (len(target.subject_order), np.asarray(np.load(target.feature_ids_path)).size)
    if ulf.shape != expected_shape or not np.all(np.isfinite(ulf)):
        return {"status": "not_computable", "reason": "invalid_raw_ulf_component_exposure"}, None

    hf_path = target.component_paths.get("hf_component_exposure")
    hf = None
    if hf_path is not None:
        try:
            hf = np.asarray(np.load(hf_path, mmap_mode="r"), dtype=np.float32)
        except (OSError, ValueError):
            hf = None
    if hf is not None and (hf.shape != ulf.shape or not np.all(np.isfinite(hf))):
        hf = None

    ulf_active = suprathreshold_matrix(ulf, float(target.selected_tau))
    total_sum = np.sum(ulf, axis=1, dtype=np.float64)
    values: dict[str, np.ndarray] = {
        "ulf_total_top5": _top_fraction_mean_rows(ulf),
        "ulf_only_to_total_fraction": np.zeros(ulf.shape[0], dtype=np.float64),
        "hf_component_top5": np.full(ulf.shape[0], np.nan),
        "hf_overlap_top5": np.full(ulf.shape[0], np.nan),
        "hf_overlap_fraction": np.full(ulf.shape[0], np.nan),
    }
    if hf is None or target.hf_overlap_tau is None:
        return {
            "status": "partial",
            "reason": "missing_or_invalid_hf_component_exposure",
        }, values

    hf_active = (
        np.zeros_like(hf, dtype=bool)
        if np.isinf(float(target.hf_overlap_tau))
        else suprathreshold_matrix(hf, float(target.hf_overlap_tau))
    )
    overlap = np.where(ulf_active & hf_active, ulf, 0.0)
    ulf_only = np.where(ulf_active & ~hf_active, ulf, 0.0)
    only_sum = np.sum(ulf_only, axis=1, dtype=np.float64)
    overlap_sum = np.sum(overlap, axis=1, dtype=np.float64)
    values.update(
        {
            "ulf_only_to_total_fraction": np.divide(
                only_sum,
                total_sum,
                out=np.zeros_like(only_sum),
                where=total_sum > 0,
            ),
            "hf_component_top5": _top_fraction_mean_rows(hf),
            "hf_overlap_top5": _top_fraction_mean_rows(overlap),
            "hf_overlap_fraction": np.divide(
                overlap_sum,
                total_sum,
                out=np.zeros_like(overlap_sum),
                where=total_sum > 0,
            ),
        }
    )
    return {"status": "complete"}, values


def run_configured_plain_burden_controls(
    target: Any,
    *,
    enabled_analyses: tuple[str, ...],
) -> dict[str, Any]:
    """Compute final-linked Round 3 controls without classification feedback.

    Plain ULF-only exposure is summarized among suprathreshold fibers in the
    realized final model's selected tau/coverage candidate universe. Model
    comparisons use only the realized branch's nuisance columns. HF
    out-of-support burden uses the matched immutable HF candidate universe when
    that input is available. Each control reports ``not_computable``
    independently when one of its required inputs is unavailable.
    """
    del enabled_analyses
    plain_analysis, plain_values = _plain_ulf_only_burden(target)
    comparison_analysis = _branch_nuisance_model_comparisons(
        target,
        None if plain_values is None else plain_values["exposure_top5"],
    )
    hf_support_analysis, hf_support_values = _hf_out_of_support_burden(target)
    descriptive_analysis, descriptive_values = _descriptive_burdens(target)
    analyses = {
        "plain_ulf_only_exposure": plain_analysis,
        "branch_nuisance_model_comparisons": comparison_analysis,
        "hf_out_of_support_burden": hf_support_analysis,
        "descriptive_burdens": descriptive_analysis,
    }

    rows = [{"subject_id": subject_id} for subject_id in target.subject_order]
    for index, row in enumerate(rows):
        row.update(
            {
                "PlainULFOnlyTouchedCount": (
                    int(plain_values["touched_count"][index]) if plain_values is not None else ""
                ),
                "PlainULFOnlyExposureSum": (
                    float(plain_values["exposure_sum"][index]) if plain_values is not None else ""
                ),
                "PlainULFOnlyExposureTop5": (
                    float(plain_values["exposure_top5"][index]) if plain_values is not None else ""
                ),
                "PlainULFTotalExposureTop5": (
                    float(descriptive_values["ulf_total_top5"][index])
                    if descriptive_values is not None
                    else ""
                ),
                "PlainHFComponentExposureTop5": (
                    float(descriptive_values["hf_component_top5"][index])
                    if descriptive_values is not None
                    and np.isfinite(descriptive_values["hf_component_top5"][index])
                    else ""
                ),
                "PlainHFOverlapExposureTop5": (
                    float(descriptive_values["hf_overlap_top5"][index])
                    if descriptive_values is not None
                    and np.isfinite(descriptive_values["hf_overlap_top5"][index])
                    else ""
                ),
                "PlainHFOutSupportTop5": (
                    float(hf_support_values["exposure_top5"][index])
                    if hf_support_values is not None
                    else ""
                ),
                "HFOverlapFraction": (
                    float(descriptive_values["hf_overlap_fraction"][index])
                    if descriptive_values is not None
                    and np.isfinite(descriptive_values["hf_overlap_fraction"][index])
                    else ""
                ),
                "ULFOnlyToTotalULFFraction": (
                    float(descriptive_values["ulf_only_to_total_fraction"][index])
                    if descriptive_values is not None
                    else ""
                ),
                "HFOutSupportTouchedCount": (
                    int(hf_support_values["touched_count"][index])
                    if hf_support_values is not None
                    else ""
                ),
                "HFOutSupportExposureSum": (
                    float(hf_support_values["exposure_sum"][index])
                    if hf_support_values is not None
                    else ""
                ),
                "HFOutSupportExposureFraction": (
                    float(hf_support_values["exposure_fraction"][index])
                    if hf_support_values is not None
                    else ""
                ),
            }
        )
    path = target.output_root / "ulf_normative_fiber_plain_burden_controls.csv"
    write_csv(
        path,
        rows,
        [
            "subject_id",
            "PlainULFOnlyTouchedCount",
            "PlainULFOnlyExposureSum",
            "PlainULFOnlyExposureTop5",
            "PlainULFTotalExposureTop5",
            "PlainHFComponentExposureTop5",
            "PlainHFOverlapExposureTop5",
            "PlainHFOutSupportTop5",
            "HFOverlapFraction",
            "ULFOnlyToTotalULFFraction",
            "HFOutSupportTouchedCount",
            "HFOutSupportExposureSum",
            "HFOutSupportExposureFraction",
        ],
    )
    statuses = [analysis["status"] for analysis in analyses.values()]
    status = (
        "complete"
        if all(value == "complete" for value in statuses)
        else "partial"
        if any(value in {"complete", "partial"} for value in statuses)
        else "not_computable"
    )
    return {
        "status": status,
        "control_definition": "final_linked_ulf_fiber_plain_burden_v2",
        "final_model_id": str(target.final_model_id),
        "final_record_hash": str(target.final_record_hash),
        "final_branch": str(target.final_branch),
        "classification_feedback": "none",
        "analyses": analyses,
        "n_subjects": len(rows),
        "control_table": str(path),
        "ulf_only_top5_mean": (
            float(np.mean(plain_values["exposure_top5"])) if plain_values is not None else None
        ),
        "ulf_total_top5_mean": (
            float(np.mean(descriptive_values["ulf_total_top5"]))
            if descriptive_values is not None
            else None
        ),
        "ulf_only_to_total_fraction_mean": (
            float(np.mean(descriptive_values["ulf_only_to_total_fraction"]))
            if descriptive_values is not None
            else None
        ),
        "hf_out_support_top5_mean": (
            float(np.mean(hf_support_values["exposure_top5"]))
            if hf_support_values is not None
            else None
        ),
    }


def run_configured_cheap_observed_sensitivity(
    target: Any,
    *,
    enabled_analyses: tuple[str, ...],
    tau_multipliers: tuple[float, float],
) -> dict[str, Any]:
    """Aggregate all request-defined cheap ULF fiber sensitivity analyses."""
    additional = run_configured_additional_sensitivities(
        target,
        enabled_analyses=enabled_analyses,
    )
    controls = run_configured_plain_burden_controls(
        target,
        enabled_analyses=enabled_analyses,
    )
    return {
        "status": "complete",
        "aggregate_definition": "request_defined_ulf_fiber_cheap_observed_v1",
        "tau_multipliers": [float(value) for value in tau_multipliers],
        "additional_sensitivities": additional,
        "plain_burden_controls": controls,
        "high_tau_top_k_hf_neighbor": {
            "status": "not_applicable",
            "reason": (
                "no separate high-tau, top-k, or HF-neighbor parameters are present "
                "in the immutable SensitivityRequest"
            ),
        },
        "classification_feedback": "none",
    }


def load_scores_by_subject(scores_csv: Path, subject_ids: list[str], column: str) -> np.ndarray:
    rows = read_csv(scores_csv)
    by_subject = {row.get("subject_id", ""): row for row in rows}
    values: list[float] = []
    for subject_id in subject_ids:
        row = by_subject.get(subject_id)
        if row is None or row.get(column, "") == "":
            raise RuntimeError(f"missing {column} for {subject_id} in {scores_csv}")
        values.append(float(row[column]))
    return np.asarray(values, dtype=float)


def selected_source_from_manifest(output_root: Path, connectome_slug: str, scale_slug: str) -> dict[str, Any]:
    manifest_path = (
        output_root
        / connectome_slug
        / scale_slug
        / f"peak_efield_{tau_slug(ULF_NORM_FIBER_PRIMARY_TAU)}_observed"
        / "tau_coverage_source_resolver_scan"
        / "normative_ULF_fiber_tau_coverage_source_resolver_manifest.json"
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing D source resolver manifest: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    primary = str(data.get("ulf_primary_branch") or "no_delta_hf")
    branch_resolution = (data.get("branch_resolutions") or {}).get(primary)
    if not branch_resolution:
        raise RuntimeError(f"missing branch resolution for primary branch {primary!r} in {manifest_path}")
    selected_tau = float(branch_resolution["ulf_norm_fiber_selected_tau_v_per_m"])
    selected_coverage = int(branch_resolution["ulf_norm_fiber_selected_coverage"])
    return {
        "manifest_path": manifest_path,
        "primary_branch": primary,
        "selected_tau": selected_tau,
        "selected_coverage": selected_coverage,
        "branch_resolution": branch_resolution,
    }


def load_inputs_from_existing_outputs(args: argparse.Namespace, connectome_key: str) -> FiberSensitivityInputs:
    output_root = Path(args.output_root).expanduser().resolve()
    if connectome_key not in CONNECTOMES:
        raise ValueError(f"unsupported connectome {connectome_key!r}")
    connectome_slug = str(CONNECTOMES[connectome_key]["slug"])
    post_scale = str(args.post_scale)
    scale_slug = slugify(post_scale)
    selected = selected_source_from_manifest(output_root, connectome_slug, scale_slug)
    selected_tau = float(selected["selected_tau"])
    selected_coverage = int(selected["selected_coverage"])
    selected_tau_name = tau_slug(selected_tau)
    selected_root = output_root / connectome_slug / scale_slug / f"peak_efield_{selected_tau_name}_observed"
    default_root = output_root / connectome_slug / scale_slug / f"peak_efield_{tau_slug(ULF_NORM_FIBER_PRIMARY_TAU)}_observed"
    no_delta_scores = selected_root / f"ulf_peak_efield_{selected_tau_name}_no_delta_hf" / "normative_ULF_fiber_scores.csv"
    delta_scores = selected_root / f"ulf_peak_efield_{selected_tau_name}_delta_hf_adjusted" / "normative_ULF_fiber_scores.csv"
    score_rows = read_csv(no_delta_scores)
    if not score_rows:
        raise FileNotFoundError(f"missing selected-source no-DeltaHF scores: {no_delta_scores}")
    subject_ids = [row["subject_id"] for row in score_rows]
    y_post = np.asarray([float(row["Y_post"]) for row in score_rows], dtype=float)
    y_hf_ref = np.asarray([float(row["Y_HF_ref"]) for row in score_rows], dtype=float)
    scale_direction, _ = infer_scale_direction(post_scale)
    if scale_direction == "lower":
        gain = y_hf_ref - y_post
    elif scale_direction == "higher":
        gain = y_post - y_hf_ref
    else:
        raise RuntimeError(f"unknown scale direction for {post_scale!r}")
    delta_hfscore = load_scores_by_subject(delta_scores, subject_ids, "DeltaHFFiberScore")
    selected_preprocess = selected_root / "preprocess"
    default_preprocess = default_root / "preprocess"
    x_ulf_only = np.load(selected_preprocess / "X_ULF_only_fiber_float32_subject_major.npy", mmap_mode="r")
    total_path = selected_preprocess / "X_ULF_component_fiber_float32_subject_major.npy"
    if not total_path.is_file():
        total_path = default_preprocess / "X_ULF_component_fiber_float32_subject_major.npy"
    if not total_path.is_file():
        raise FileNotFoundError(f"missing total ULF component exposure sidecar for {connectome_key}: {total_path}")
    x_ulf_total = np.load(total_path, mmap_mode="r")
    fiber_ids_path = selected_preprocess / "fiber_ids.npy"
    if not fiber_ids_path.is_file():
        fiber_ids_path = default_preprocess / "fiber_ids.npy"
    fiber_ids = np.load(fiber_ids_path)
    if x_ulf_only.shape != x_ulf_total.shape:
        raise RuntimeError(f"ULF-only and total-ULF exposure shapes differ for {connectome_key}")
    return FiberSensitivityInputs(
        subject_ids=subject_ids,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        gain=gain,
        delta_hfscore=delta_hfscore,
        x_ulf_only=np.asarray(x_ulf_only),
        x_ulf_total=np.asarray(x_ulf_total),
        fiber_ids=np.asarray(fiber_ids),
        scale_direction=scale_direction,
        tau=selected_tau,
        min_coverage=selected_coverage,
        output_root=selected_root,
        post_scale=post_scale,
        hf_reference_scale=str(args.hf_reference_scale),
        connectome_key=connectome_key,
        connectome_slug=connectome_slug,
        selected_tau=selected_tau,
        selected_coverage=selected_coverage,
    )


def run_sensitivity_observed(args: argparse.Namespace) -> int:
    all_rows: list[dict[str, Any]] = []
    for connectome_key in parse_connectomes(args.connectomes):
        rows = build_sensitivity_branches(load_inputs_from_existing_outputs(args, connectome_key))
        for row in rows:
            row["connectome"] = connectome_key
            all_rows.append(row)
            print(f"{connectome_key} {row['branch']}: rho={row['spearman_rho']}; q2={row['q2']}")
    summary_dir = Path(args.output_root).expanduser().resolve() / "sensitivity_observed"
    summary_csv = summary_dir / "normative_ULF_fiber_sensitivity_summary.csv"
    manifest_json = summary_dir / "normative_ULF_fiber_sensitivity_manifest.json"
    write_csv(summary_csv, all_rows, ["connectome", "branch", "branch_dir", "spearman_rho", "q2", "resampling_status"])
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "model": "ULF normative fiber sensitivity",
            "post_scale": args.post_scale,
            "connectomes": parse_connectomes(args.connectomes),
            "n_rows": len(all_rows),
            "resampling_status": "not_run_observed_only",
            "outputs": {"summary_csv": str(summary_csv), "manifest_json": str(manifest_json)},
        },
        add_code_provenance=True,
    )
    print(f"ULF normative fiber sensitivity summary: {summary_csv}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="ULF normative fiber output root.")
    parser.add_argument("--post-scale", default=DEFAULT_POST_SCALE, help="Raw STN+SNr post endpoint.")
    parser.add_argument("--hf-reference-scale", default="MDS-UPDRS III score (STN, 3 m)", help="HF reference endpoint label.")
    parser.add_argument("--connectomes", default=",".join(DEFAULT_CONNECTOMES), help="Comma-separated connectome keys.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_sensitivity_observed(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
