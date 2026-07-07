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
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    fiber_net_score,
    fit_linear_prediction,
    partial_spearman_matrix,
    regression_metrics,
    suprathreshold_matrix,
)
from stnsnr_hf_direct_voxel_smoke import slugify
from stnsnr_io import iso_now, read_csv, write_csv, write_json
from stnsnr_ulf_direct_voxel_sensitivity_observed import as_2d_covariates, fit_baseline_prediction
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
) -> dict[str, Any]:
    x = np.asarray(exposure, dtype=np.float32)
    y = np.asarray(outcome, dtype=float)
    cov_full = as_2d_covariates(covariates, y.shape[0])
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError(f"empty sensitivity fiber candidate set for {branch_name}")
    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_candidate = partial_spearman_matrix(y, np.asarray(x[:, candidate]), cov_full if cov_full.shape[1] else None)
    rho[candidate] = rho_candidate.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_net = fiber_net_score(x, weights, candidate, fiber_ids=fiber_ids)

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
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty sensitivity fold candidate set for held-out {subject_ids[heldout]}")
        fold_candidate_counts.append(int(np.count_nonzero(candidate_fold)))
        rho_fold = partial_spearman_matrix(
            y[train],
            np.asarray(x[train][:, candidate_fold]),
            cov_full[train] if cov_full.shape[1] else None,
        )
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(x, weights_fold, candidate_fold, fiber_ids=fiber_ids)
        pred, beta = fit_linear_prediction(
            y[train],
            fold_net.net_score[train],
            cov_full[train] if cov_full.shape[1] else None,
            fold_net.net_score[[heldout]],
            cov_full[[heldout]] if cov_full.shape[1] else None,
        )
        base_pred, base_beta = fit_baseline_prediction(y[train], cov_full[train], cov_full[[heldout]])
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
            "delta_NetULFFiberSensitivityScore": float(beta[1]),
        }
        for cov_idx, name in enumerate(covariate_names):
            row[name] = float(cov_full[heldout, cov_idx])
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
