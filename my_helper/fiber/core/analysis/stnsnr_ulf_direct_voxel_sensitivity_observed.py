#!/usr/bin/env python3
"""Observed-only C direct-voxel gain and total-ULF sensitivity branches."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT, infer_scale_direction
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
from stnsnr_hf_direct_voxel_smoke import slugify, write_nifti_from_flat
from stnsnr_io import iso_now, write_csv, write_json
from stnsnr_ulf_direct_voxel_observed import DEFAULT_POST_SCALE


DEFAULT_ULF_OUTPUT_ROOT = DEFAULT_VAL_ROOT / "summary/direct_voxel/ulf"


@dataclass(frozen=True)
class SensitivityInputs:
    subject_ids: list[str]
    y_post: np.ndarray
    y_hf_ref: np.ndarray
    gain: np.ndarray
    delta_hfscore: np.ndarray
    x_ulf_only: np.ndarray
    x_ulf_total: np.ndarray
    candidate_flat: np.ndarray
    ref_img_path: Path
    scale_direction: str
    tau: float
    min_coverage: int
    output_root: Path
    post_scale: str
    hf_reference_scale: str


def as_2d_covariates(covariates: np.ndarray | None, n_rows: int) -> np.ndarray:
    if covariates is None:
        return np.empty((n_rows, 0), dtype=float)
    cov = np.asarray(covariates, dtype=float)
    if cov.ndim == 1:
        cov = cov[:, None]
    if cov.shape[0] != n_rows:
        raise ValueError(f"covariates has {cov.shape[0]} rows; expected {n_rows}")
    return cov


def fit_baseline_prediction(train_y: np.ndarray, train_covariates: np.ndarray, test_covariates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train_cov = as_2d_covariates(train_covariates, train_y.shape[0])
    test_cov = as_2d_covariates(test_covariates, test_covariates.shape[0])
    train_design = np.column_stack([np.ones(train_y.shape[0]), train_cov])
    test_design = np.column_stack([np.ones(test_cov.shape[0]), test_cov])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return test_design @ beta, beta


def compute_observed_sensitivity_branch(
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
    fold_covariates: np.ndarray | None = None,
) -> dict[str, Any]:
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
    omega = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(omega):
        raise RuntimeError(f"empty sensitivity Omega for {branch_name}")
    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_omega = partial_spearman_matrix(y, x[:, omega], cov_full if cov_full.shape[1] else None)
    rho[omega] = rho_omega.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid_full = omega & np.isfinite(weights)
    full_scores, n_valid_full = mean_map_score(x, weights, valid_full)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_ids):
        row = {
            "subject_id": subject_id,
            "Y_sensitivity": float(y[idx]),
            "SensitivityScore_mean_main": float(full_scores[idx]),
            "exposure_sum_valid_voxels": float(np.sum(x[idx, valid_full], dtype=np.float64)),
            "n_valid_score_voxels": int(n_valid_full),
            "score_map_source": "full_sample",
            "is_primary_score": False,
        }
        for cov_idx, name in enumerate(covariate_names):
            row[name] = float(cov_full[idx, cov_idx])
        score_rows.append(row)

    n_subjects = y.shape[0]
    loocv_pred = np.full(n_subjects, np.nan, dtype=float)
    loocv_base_pred = np.full(n_subjects, np.nan, dtype=float)
    stability_positive = np.zeros(x.shape[1], dtype=np.int16)
    stability_valid = np.zeros(x.shape[1], dtype=np.int16)
    fold_rows: list[dict[str, Any]] = []
    fold_valid_counts: list[int] = []
    for heldout in range(n_subjects):
        train = np.array([idx for idx in range(n_subjects) if idx != heldout], dtype=int)
        fold_cov = cov_full if cov_folds is None else cov_folds[heldout]
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        omega_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(omega_fold):
            raise RuntimeError(f"empty sensitivity fold Omega for held-out {subject_ids[heldout]}")
        rho_fold = partial_spearman_matrix(
            y[train],
            x[train][:, omega_fold],
            fold_cov[train] if fold_cov.shape[1] else None,
        )
        weights_fold_local = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[omega_fold] = weights_fold_local
        valid_fold = omega_fold & np.isfinite(weights_fold)
        if not np.any(valid_fold):
            raise RuntimeError(f"no valid sensitivity score voxels for {subject_ids[heldout]}")
        stability_valid[valid_fold] += 1
        stability_positive[valid_fold & (weights_fold > 0)] += 1
        fold_scores, n_valid_fold = mean_map_score(x, weights_fold, valid_fold)
        fold_valid_counts.append(int(n_valid_fold))
        pred, beta = fit_linear_prediction(
            y[train],
            fold_scores[train],
            fold_cov[train] if fold_cov.shape[1] else None,
            fold_scores[[heldout]],
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
            "SensitivityScore_LOOCV": float(fold_scores[heldout]),
            "prediction_sensitivity_model": float(pred[0]),
            "prediction_baseline_only": float(base_pred[0]),
            "residual_sensitivity_model": float(y[heldout] - pred[0]),
            "residual_baseline_only": float(y[heldout] - base_pred[0]),
            "n_train": int(train.size),
            "n_valid_score_voxels": int(n_valid_fold),
            "delta_SensitivityScore": float(beta[1]),
        }
        for cov_idx, name in enumerate(covariate_names):
            row[name] = float(fold_cov[heldout, cov_idx])
            row[f"beta_{name}"] = float(beta[2 + cov_idx])
            row[f"baseline_beta_{name}"] = float(base_beta[1 + cov_idx])
        fold_rows.append(row)

    stability = np.full(x.shape[1], np.nan, dtype=np.float32)
    valid_stability = stability_valid > 0
    stability[valid_stability] = stability_positive[valid_stability] / n_subjects
    metrics = regression_metrics(y, loocv_pred, loocv_base_pred)
    fold_valid = np.asarray(fold_valid_counts, dtype=float)
    return {
        "branch_name": branch_name,
        "rho": rho,
        "weights": weights,
        "coverage": coverage,
        "stability": stability,
        "score_rows": score_rows,
        "fold_rows": fold_rows,
        "metrics": metrics,
        "n_omega_voxels": int(np.count_nonzero(omega)),
        "n_valid_full_score_voxels": int(n_valid_full),
        "fold_n_valid_score_voxels_min": int(np.nanmin(fold_valid)),
        "fold_n_valid_score_voxels_median": float(np.nanmedian(fold_valid)),
        "fold_n_valid_score_voxels_max": int(np.nanmax(fold_valid)),
        "all_predictions_finite": bool(np.all(np.isfinite(loocv_pred)) and np.all(np.isfinite(loocv_base_pred))),
    }


def write_sensitivity_branch(
    *,
    branch_dir: Path,
    ref_img: nib.Nifti1Image,
    candidate_flat: np.ndarray,
    branch: dict[str, Any],
    inputs: SensitivityInputs,
    outcome_label: str,
    exposure_label: str,
    covariate_names: list[str],
) -> dict[str, Any]:
    branch_dir.mkdir(parents=True, exist_ok=True)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_coverage.nii.gz", ref_img, candidate_flat, branch["coverage"], np.int16, 0)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_coef.nii.gz", ref_img, candidate_flat, branch["rho"], np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_sweet_sour.nii.gz", ref_img, candidate_flat, branch["weights"], np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_stability.nii.gz", ref_img, candidate_flat, branch["stability"], np.float32, np.nan)
    score_fields = [
        "subject_id",
        "Y_sensitivity",
        *covariate_names,
        "SensitivityScore_mean_main",
        "exposure_sum_valid_voxels",
        "n_valid_score_voxels",
        "score_map_source",
        "is_primary_score",
    ]
    fold_fields = [
        "fold_id",
        "heldout_subject_id",
        "Y_sensitivity",
        *covariate_names,
        "SensitivityScore_LOOCV",
        "prediction_sensitivity_model",
        "prediction_baseline_only",
        "residual_sensitivity_model",
        "residual_baseline_only",
        "n_train",
        "n_valid_score_voxels",
        "delta_SensitivityScore",
        *[f"beta_{name}" for name in covariate_names],
        *[f"baseline_beta_{name}" for name in covariate_names],
    ]
    write_csv(branch_dir / "direct_voxel_ULF_only_scores.csv", branch["score_rows"], score_fields)
    write_csv(branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv", branch["fold_rows"], fold_fields)
    qc = {
        "generated_at": iso_now(),
        "model": "ULF direct voxel sensitivity",
        "branch": branch["branch_name"],
        "post_scale": inputs.post_scale,
        "hf_reference_scale": inputs.hf_reference_scale,
        "outcome_label": outcome_label,
        "exposure_label": exposure_label,
        "scale_direction": inputs.scale_direction,
        "n_subjects": len(inputs.subject_ids),
        "tau_v_per_m": inputs.tau,
        "min_coverage": inputs.min_coverage,
        "n_omega_voxels": branch["n_omega_voxels"],
        "n_valid_full_score_voxels": branch["n_valid_full_score_voxels"],
        "fold_n_valid_score_voxels_min": branch["fold_n_valid_score_voxels_min"],
        "fold_n_valid_score_voxels_median": branch["fold_n_valid_score_voxels_median"],
        "fold_n_valid_score_voxels_max": branch["fold_n_valid_score_voxels_max"],
        "all_predictions_finite": branch["all_predictions_finite"],
        "loocv_metrics": branch["metrics"],
        "resampling_status": "not_run_observed_only",
    }
    manifest = {
        "generated_at": iso_now(),
        "model": "ULF direct voxel sensitivity",
        "branch": branch["branch_name"],
        "status": "PASS",
        "post_scale": inputs.post_scale,
        "hf_reference_scale": inputs.hf_reference_scale,
        "outcome_label": outcome_label,
        "exposure_label": exposure_label,
        "parameters": {"tau_v_per_m": inputs.tau, "min_coverage": inputs.min_coverage},
        "resampling_status": "not_run_observed_only",
        "resampling_reason": "observed sensitivity branch; formal resampling restricted to selected final model",
        "outputs": {
            "branch_dir": str(branch_dir),
            "scores_csv": str(branch_dir / "direct_voxel_ULF_only_scores.csv"),
            "loocv_predictions_csv": str(branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv"),
            "mapping_qc_json": str(branch_dir / "direct_voxel_ULF_only_mapping_qc.json"),
            "generation_manifest_json": str(branch_dir / "direct_voxel_ULF_only_generation_manifest.json"),
        },
    }
    write_json(branch_dir / "direct_voxel_ULF_only_mapping_qc.json", qc)
    write_json(branch_dir / "direct_voxel_ULF_only_generation_manifest.json", manifest, add_code_provenance=True)
    return {
        "branch": branch["branch_name"],
        "branch_dir": str(branch_dir),
        "spearman_rho": branch["metrics"].get("spearman_rho", np.nan),
        "q2": branch["metrics"].get("q2", np.nan),
        "resampling_status": "not_run_observed_only",
    }


def build_sensitivity_branches(inputs: SensitivityInputs) -> list[dict[str, Any]]:
    ref_img = nib.load(str(inputs.ref_img_path))
    gain_branch = compute_observed_sensitivity_branch(
        branch_name="partial_spearman_gain_endpoint",
        exposure=inputs.x_ulf_only,
        outcome=inputs.gain,
        covariates=inputs.delta_hfscore,
        covariate_names=["DeltaHFScore"],
        scale_direction=inputs.scale_direction,
        tau=inputs.tau,
        min_coverage=inputs.min_coverage,
        subject_ids=inputs.subject_ids,
    )
    total_branch = compute_observed_sensitivity_branch(
        branch_name="partial_spearman_total_ulf_exposure",
        exposure=inputs.x_ulf_total,
        outcome=inputs.y_post,
        covariates=inputs.y_hf_ref,
        covariate_names=["Y_HF_ref"],
        scale_direction=inputs.scale_direction,
        tau=inputs.tau,
        min_coverage=inputs.min_coverage,
        subject_ids=inputs.subject_ids,
    )
    return [
        write_sensitivity_branch(
            branch_dir=inputs.output_root / "partial_spearman_gain_endpoint",
            ref_img=ref_img,
            candidate_flat=inputs.candidate_flat,
            branch=gain_branch,
            inputs=inputs,
            outcome_label="Gain_chronic",
            exposure_label="HF_overlap_excluded_ULF_only",
            covariate_names=["DeltaHFScore"],
        ),
        write_sensitivity_branch(
            branch_dir=inputs.output_root / "partial_spearman_total_ulf_exposure",
            ref_img=ref_img,
            candidate_flat=inputs.candidate_flat,
            branch=total_branch,
            inputs=inputs,
            outcome_label="Y_post_chronic",
            exposure_label="total_ULF_component",
            covariate_names=["Y_HF_ref"],
        ),
    ]


def _configured_score_columns(target: Any) -> dict[str, np.ndarray]:
    with Path(target.scores_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError("configured sensitivity scores table is empty")
    subject_order = tuple(str(row.get("subject_id", "")) for row in rows)
    if subject_order != tuple(target.subject_order):
        raise RuntimeError("configured sensitivity score subject order mismatch")
    columns: dict[str, np.ndarray] = {}
    for key in rows[0]:
        if key == "subject_id":
            columns[key] = np.asarray([row[key] for row in rows])
        else:
            try:
                columns[key] = np.asarray([float(row[key]) for row in rows], dtype=float)
            except (TypeError, ValueError):
                continue
    return columns


def _configured_delta(target: Any) -> tuple[np.ndarray | None, np.ndarray | None]:
    if target.delta_full_path is None or target.delta_fold_path is None:
        return None, None
    full = np.asarray(np.load(target.delta_full_path, mmap_mode="r"), dtype=float)
    folds = np.asarray(np.load(target.delta_fold_path, mmap_mode="r"), dtype=float)
    n_subjects = len(target.subject_order)
    if full.shape != (n_subjects,) or folds.shape != (n_subjects, n_subjects):
        raise RuntimeError("configured DeltaHF artifacts have invalid shapes")
    if not np.all(np.isfinite(full)) or not np.all(np.isfinite(folds)):
        raise RuntimeError("configured DeltaHF artifacts contain non-finite values")
    return full, folds


def _branch_covariates(
    y_hf_ref: np.ndarray,
    delta_full: np.ndarray | None,
    delta_folds: np.ndarray | None,
    *,
    adjusted: bool,
) -> tuple[np.ndarray, np.ndarray | None, list[str]]:
    if not adjusted:
        return y_hf_ref[:, None], None, ["Y_HF_ref"]
    if delta_full is None or delta_folds is None:
        raise RuntimeError("delta_hf_adjusted sensitivity requires valid DeltaHF artifacts")
    n_subjects = y_hf_ref.shape[0]
    full = np.column_stack([y_hf_ref, delta_full])
    folds = np.concatenate(
        [
            np.broadcast_to(y_hf_ref[None, :, None], (n_subjects, n_subjects, 1)),
            delta_folds[:, :, None],
        ],
        axis=2,
    )
    return full, folds, ["Y_HF_ref", "DeltaHFScore"]


def _configured_branch_result(
    *,
    name: str,
    exposure: np.ndarray,
    outcome: np.ndarray,
    covariates: np.ndarray | None,
    fold_covariates: np.ndarray | None,
    covariate_names: list[str],
    target: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        branch = compute_observed_sensitivity_branch(
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
        )
    except (RuntimeError, ValueError) as exc:
        return {"status": "not_computable", "reason": str(exc)}, None
    return {
        "status": "complete",
        "branch": name,
        "loocv_metrics": branch["metrics"],
        "n_omega_voxels": int(branch["n_omega_voxels"]),
        "all_predictions_finite": bool(branch["all_predictions_finite"]),
    }, branch


def _support_diagnostic(target: Any) -> dict[str, Any]:
    if target.delta_support_path is None:
        return {"status": "not_computable", "reason": "invalid_or_missing_delta_hf_support"}
    with Path(target.delta_support_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    values: list[float] = []
    for row in rows:
        text = row.get("HF_out_support_fraction", row.get("hf_out_support_fraction", ""))
        try:
            values.append(float(text))
        except (TypeError, ValueError):
            continue
    if not values:
        return {"status": "not_computable", "reason": "support_rows_missing_out_fraction"}
    fractions = np.asarray(values, dtype=float)
    category = "adequate"
    if (
        float(np.median(fractions)) > 0.50
        or float(np.mean(fractions > 0.80)) > 0.25
        or float(np.max(fractions)) > 0.95
    ):
        category = "invalid_extreme_out_of_support"
    elif not (
        float(np.median(fractions)) <= 0.20
        and float(np.mean(fractions > 0.50)) <= 0.25
    ):
        category = "limited"
    return {
        "status": "complete",
        "observed_support_category": category,
        "median_out_support_fraction": float(np.median(fractions)),
        "fraction_over_0_50": float(np.mean(fractions > 0.50)),
        "fraction_over_0_80": float(np.mean(fractions > 0.80)),
        "maximum_out_support_fraction": float(np.max(fractions)),
        "invalid_extreme_threshold": 0.95,
    }


def _collinearity_diagnostic(
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
        [row["SensitivityScore_mean_main"] for row in branch["score_rows"]],
        dtype=float,
    )
    columns = [scores, y_hf_ref]
    names = ["ULFScore", "Y_HF_ref"]
    if target.final_branch == "delta_hf_adjusted":
        if delta_full is None:
            return {"status": "not_computable", "reason": "missing_delta_hf"}
        columns.append(delta_full)
        names.append("DeltaHFScore")
    columns.append(y_base)
    names.append("Y_base")
    design = np.column_stack(columns)
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
    """Run task-local ULF direct-voxel sensitivities without classification feedback."""
    columns = _configured_score_columns(target)
    y_post = np.asarray(columns["Y_post"], dtype=float)
    y_hf_ref = np.asarray(columns["Y_HF_ref"], dtype=float)
    delta_full, delta_folds = _configured_delta(target)
    selected_exposure = np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32)
    total_path = target.component_paths.get("ulf_component_exposure")
    analyses: dict[str, Any] = {}

    selected_adjusted = target.final_branch == "delta_hf_adjusted"
    selected_cov, selected_fold_cov, selected_names = _branch_covariates(
        y_hf_ref,
        delta_full,
        delta_folds,
        adjusted=selected_adjusted,
    )
    selected_result, selected_branch = _configured_branch_result(
        name=f"selected_{target.final_branch}",
        exposure=selected_exposure,
        outcome=y_post,
        covariates=selected_cov,
        fold_covariates=selected_fold_cov,
        covariate_names=selected_names,
        target=target,
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
            analyses["nonfinal_branch"], _ = _configured_branch_result(
                name=("delta_hf_adjusted" if nonfinal_adjusted else "no_delta_hf"),
                exposure=selected_exposure,
                outcome=y_post,
                covariates=cov,
                fold_covariates=fold_cov,
                covariate_names=names,
                target=target,
            )
        except RuntimeError as exc:
            analyses["nonfinal_branch"] = {"status": "not_computable", "reason": str(exc)}

    if "gain" in enabled_analyses:
        gain = y_hf_ref - y_post if target.scale_direction == "lower" else y_post - y_hf_ref
        gain_cov = delta_full[:, None] if selected_adjusted and delta_full is not None else None
        gain_folds = delta_folds[:, :, None] if selected_adjusted and delta_folds is not None else None
        gain_names = ["DeltaHFScore"] if gain_cov is not None else []
        analyses["gain"], _ = _configured_branch_result(
            name="gain_endpoint",
            exposure=selected_exposure,
            outcome=gain,
            covariates=gain_cov,
            fold_covariates=gain_folds,
            covariate_names=gain_names,
            target=target,
        )

    if "total_exposure" in enabled_analyses:
        if total_path is None:
            analyses["total_exposure"] = {
                "status": "not_computable",
                "reason": "missing_raw_ulf_component_exposure",
            }
        else:
            total_exposure = np.asarray(np.load(total_path, mmap_mode="r"), dtype=np.float32)
            analyses["total_exposure"], _ = _configured_branch_result(
                name="total_ulf_exposure",
                exposure=total_exposure,
                outcome=y_post,
                covariates=selected_cov,
                fold_covariates=selected_fold_cov,
                covariate_names=selected_names,
                target=target,
            )

    if "support" in enabled_analyses:
        analyses["support"] = _support_diagnostic(target)
    if "collinearity" in enabled_analyses:
        analyses["collinearity"] = _collinearity_diagnostic(
            target,
            selected_branch,
            y_hf_ref,
            delta_full,
        )
    analyses["selected_branch_reference"] = selected_result

    summary_path = target.output_root / "ulf_direct_voxel_additional_sensitivities.csv"
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
    }


def load_delta_hfscore(delta_scores_csv: Path, subject_ids: list[str]) -> np.ndarray:
    if not delta_scores_csv.is_file():
        raise FileNotFoundError(f"missing DeltaHFScore source scores CSV: {delta_scores_csv}")
    with delta_scores_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_subject = {row.get("subject_id", ""): row for row in rows}
    values: list[float] = []
    for subject_id in subject_ids:
        row = by_subject.get(subject_id)
        if row is None or not row.get("DeltaHFScore"):
            raise RuntimeError(f"missing DeltaHFScore for {subject_id}")
        values.append(float(row["DeltaHFScore"]))
    return np.asarray(values, dtype=float)


def load_inputs_from_existing_outputs(args: argparse.Namespace) -> SensitivityInputs:
    output_root = Path(args.output_root).expanduser().resolve()
    post_scale = args.post_scale
    scale_slug = slugify(post_scale)
    scale_root = output_root / scale_slug
    preprocess_dir = scale_root / "preprocess"
    tau_root = scale_root / f"tau{int(args.tau)}"
    subjects_csv = preprocess_dir / "subjects.csv"
    if not subjects_csv.is_file():
        raise FileNotFoundError(f"missing ULF preprocess subjects CSV: {subjects_csv}")
    with subjects_csv.open(newline="", encoding="utf-8") as handle:
        subject_rows = list(csv.DictReader(handle))
    subject_ids = [row["subject_id"] for row in subject_rows]
    y_post = np.asarray([float(row["y_post"]) for row in subject_rows], dtype=float)
    y_hf_ref = np.asarray([float(row["y_hf_ref"]) for row in subject_rows], dtype=float)
    scale_direction, _ = infer_scale_direction(post_scale)
    if scale_direction == "lower":
        gain = y_hf_ref - y_post
    elif scale_direction == "higher":
        gain = y_post - y_hf_ref
    else:
        raise RuntimeError(f"unknown scale direction for {post_scale!r}")
    x_ulf_only = np.load(preprocess_dir / "X_ULF_only_float32_subject_major.npy")
    x_ulf_total = np.load(preprocess_dir / "E_ULF_component_float32_subject_major.npy")
    candidate_flat = np.load(preprocess_dir / "candidate_flat_indices.npy")
    delta_hfscore = load_delta_hfscore(
        tau_root / "partial_spearman_delta_hf_adjusted" / "direct_voxel_ULF_only_scores.csv",
        subject_ids,
    )
    ref_img_path = Path(args.ref_img).expanduser().resolve() if args.ref_img else (
        tau_root / "partial_spearman_no_delta_hf" / "direct_voxel_ULF_only_coef.nii.gz"
    )
    return SensitivityInputs(
        subject_ids=subject_ids,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        gain=gain,
        delta_hfscore=delta_hfscore,
        x_ulf_only=x_ulf_only,
        x_ulf_total=x_ulf_total,
        candidate_flat=candidate_flat,
        ref_img_path=ref_img_path,
        scale_direction=scale_direction,
        tau=float(args.tau),
        min_coverage=int(args.min_coverage),
        output_root=tau_root,
        post_scale=post_scale,
        hf_reference_scale=args.hf_reference_scale,
    )


def run_sensitivity_observed(args: argparse.Namespace) -> int:
    rows = build_sensitivity_branches(load_inputs_from_existing_outputs(args))
    summary_path = Path(args.output_root).expanduser().resolve() / slugify(args.post_scale) / f"tau{int(args.tau)}" / "direct_voxel_ULF_only_sensitivity_summary.csv"
    write_csv(summary_path, rows, ["branch", "branch_dir", "spearman_rho", "q2", "resampling_status"])
    print(f"ULF direct voxel sensitivity summary: {summary_path}")
    for row in rows:
        print(f"{row['branch']}: rho={row['spearman_rho']}; q2={row['q2']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=str(DEFAULT_ULF_OUTPUT_ROOT), help="ULF direct voxel output root.")
    parser.add_argument("--post-scale", default=DEFAULT_POST_SCALE, help="Raw STN+SNr post endpoint.")
    parser.add_argument("--hf-reference-scale", default="MDS-UPDRS III score (STN, 3 m)", help="HF reference endpoint label.")
    parser.add_argument("--tau", type=float, default=200.0, help="Selected ULF threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Selected ULF coverage threshold.")
    parser.add_argument("--ref-img", default="", help="Optional reference NIfTI path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_sensitivity_observed(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
