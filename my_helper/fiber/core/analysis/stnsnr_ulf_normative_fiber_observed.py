#!/usr/bin/env python3
"""Observed-only ULF normative connectome fiber driver."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

from stnsnr_four_model_readiness import (
    detect_asset_root,
    infer_scale_direction,
    repo_root_from_file,
)
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
from stnsnr_hf_direct_voxel_smoke import fit_baseline_only, slugify
from stnsnr_hf_normative_fiber_smoke import (
    CONNECTOMES,
    fiber_block_slices,
    load_idx_lengths,
    load_image_samplers,
    reduce_point_values_to_fiber_peaks,
    sample_max_samplers_at_points,
)
from stnsnr_ulf_direct_voxel_observed import (
    ULFRecord,
    component_side_paths,
    fit_baseline_with_covariates,
    flip_component_left_fields,
    load_component_availability,
    load_ulf_records,
    resolve_readiness_csv,
    top_percent_mean,
)


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def required_arg(args: argparse.Namespace, name: str) -> str:
    value = getattr(args, name, "")
    if value is None or str(value).strip() == "":
        flag = name.replace("_", "-")
        raise ValueError(f"--{flag} is required by the backend; project workflows must pass it explicitly")
    return str(value)


def tau_slug(tau: float) -> str:
    value = float(tau)
    if value.is_integer():
        return f"tau{int(value)}"
    return "tau" + str(value).replace(".", "p")


def apply_ulf_only_fiber_rule(hf_component: np.ndarray, ulf_component: np.ndarray, tau: float) -> np.ndarray:
    """Keep ULF exposure only where ULF is active and HF is not active."""
    hf = np.asarray(hf_component, dtype=np.float32)
    ulf = np.asarray(ulf_component, dtype=np.float32)
    if hf.shape != ulf.shape:
        raise ValueError("HF and ULF component matrices must have the same shape")
    return np.where((ulf > float(tau)) & ~(hf > float(tau)), ulf, 0.0).astype(np.float32)


def classify_b_dependency(decision: str) -> dict[str, str]:
    """Resolve D branch roles from a matched B gate decision."""
    if decision == "PASS_TO_NEXT_ROUND":
        return {
            "hf_prediction_validity_status": "predictive_valid",
            "ulf_primary_branch": "delta_hf_adjusted",
            "delta_hfscore_role": "primary_nuisance_adjustment",
        }
    if decision == "STOP_FORMAL_REMAIN_EXPLORATORY":
        return {
            "hf_prediction_validity_status": "failed_unstable",
            "ulf_primary_branch": "no_delta_hf",
            "delta_hfscore_role": "unstable_generated_covariate_sensitivity",
        }
    return {
        "hf_prediction_validity_status": "unknown_or_missing",
        "ulf_primary_branch": "no_delta_hf",
        "delta_hfscore_role": "exploratory_only_or_not_run",
    }


def gate_model_id_for_connectome(connectome_key: str) -> str:
    return {"ppmi": "B_PPMI", "mgh": "B_MGH", "dtor": "B_DTOR"}.get(connectome_key, "B_DTOR")


def read_b_gate_status(gate_status_path: Path, connectome_key: str) -> dict[str, str]:
    model_id = gate_model_id_for_connectome(connectome_key)
    if not gate_status_path.is_file():
        return {"model_id": model_id, "gate_decision": "MISSING_GATE_STATUS", **classify_b_dependency("MISSING_GATE_STATUS")}
    table = pd.read_csv(gate_status_path)
    row = table[table["model_id"].astype(str).eq(model_id)]
    decision = "MISSING_OUTPUT" if row.empty else str(row.iloc[0].get("decision", "MISSING_OUTPUT"))
    return {"model_id": model_id, "gate_decision": decision, **classify_b_dependency(decision)}


def make_optional_samplers(path_dict: dict[tuple[str, str], list[Path]], flipped_left: dict[str, list[Path]], records: list[ULFRecord]) -> dict[str, dict[str, list[Any]]]:
    samplers: dict[str, dict[str, list[Any]]] = {}
    for record in records:
        samplers[record.subject_id] = {
            "R": load_image_samplers(path_dict.get((record.subject_id, "R"), [])),
            "L_to_R": load_image_samplers(flipped_left.get(record.subject_id, [])),
        }
    return samplers


def prepare_component_fiber_samplers(
    availability: pd.DataFrame,
    records: list[ULFRecord],
    frequency_class: str,
    asset_root: Path,
    matlab_bin: Path,
    preprocess_dir: Path,
    force_flip: bool,
) -> tuple[dict[str, dict[str, list[Any]]], dict[str, Any]]:
    side_paths, side_qc = component_side_paths(availability, records, frequency_class)
    flipped, flip_result = flip_component_left_fields(
        asset_root,
        matlab_bin,
        side_paths,
        preprocess_dir,
        frequency_class.lower(),
        force_flip,
    )
    return make_optional_samplers(side_paths, flipped, records), {"side_paths": side_qc, "flip_result": flip_result}


def sample_optional_max(samplers: list[Any], xyz: np.ndarray) -> np.ndarray:
    if not samplers:
        return np.zeros(xyz.shape[0], dtype=np.float32)
    values, _ = sample_max_samplers_at_points(samplers, xyz)
    return values


def build_fiber_exposure_sidecar(
    data_mat: Path,
    records: list[ULFRecord],
    samplers: dict[str, dict[str, list[Any]]],
    output_npy: Path,
    fiber_ids_npy: Path,
    *,
    max_fibers: int,
    fiber_chunk_size: int,
) -> dict[str, Any]:
    """Sample component e-fields along public connectome fibers into a sidecar."""
    lengths = load_idx_lengths(data_mat, max_fibers=max_fibers)
    n_fibers = int(lengths.size)
    x = np.lib.format.open_memmap(output_npy, mode="w+", dtype=np.float32, shape=(len(records), n_fibers))
    fiber_ids = np.arange(1, n_fibers + 1, dtype=np.int64)
    np.save(fiber_ids_npy, fiber_ids)
    block_rows: list[dict[str, Any]] = []
    started = time.time()
    with h5py.File(data_mat, "r") as handle:
        fibers = handle["fibers"]
        for block_index, (fiber_start, fiber_stop, point_start, point_stop) in enumerate(
            fiber_block_slices(lengths, fiber_chunk_size=fiber_chunk_size),
            start=1,
        ):
            coords = np.asarray(fibers[0:3, point_start:point_stop], dtype=np.float32).T
            lengths_block = lengths[fiber_start:fiber_stop]
            for subject_index, record in enumerate(records):
                right_points = sample_optional_max(samplers[record.subject_id]["R"], coords)
                left_points = sample_optional_max(samplers[record.subject_id]["L_to_R"], coords)
                right_peaks = reduce_point_values_to_fiber_peaks(right_points, lengths_block)
                left_peaks = reduce_point_values_to_fiber_peaks(left_points, lengths_block)
                x[subject_index, fiber_start:fiber_stop] = (right_peaks + left_peaks) / 2.0
            block_rows.append(
                {
                    "block_index": block_index,
                    "fiber_start_0based": fiber_start,
                    "fiber_stop_0based": fiber_stop,
                    "point_start_0based": point_start,
                    "point_stop_0based": point_stop,
                    "n_fibers": fiber_stop - fiber_start,
                    "n_points": point_stop - point_start,
                }
            )
    x.flush()
    return {
        "data_mat": str(data_mat),
        "output_npy": str(output_npy),
        "fiber_ids_npy": str(fiber_ids_npy),
        "n_subjects": len(records),
        "n_fibers": n_fibers,
        "n_points": int(np.sum(lengths)),
        "max_fibers": int(max_fibers),
        "fiber_chunk_size": int(fiber_chunk_size),
        "elapsed_s": time.time() - started,
        "blocks": block_rows,
    }


def load_or_build_component_exposure(
    data_mat: Path,
    records: list[ULFRecord],
    samplers: dict[str, dict[str, list[Any]]],
    preprocess_dir: Path,
    label: str,
    *,
    max_fibers: int,
    fiber_chunk_size: int,
    force_rebuild: bool,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    output_npy = preprocess_dir / f"X_{label}_fiber_float32_subject_major.npy"
    fiber_ids_npy = preprocess_dir / "fiber_ids.npy"
    if output_npy.is_file() and fiber_ids_npy.is_file() and not force_rebuild:
        x = np.load(output_npy, mmap_mode="r")
        fiber_ids = np.load(fiber_ids_npy)
        return x, fiber_ids, {
            "status": "reused_existing_sidecar",
            "label": label,
            "output_npy": str(output_npy),
            "fiber_ids_npy": str(fiber_ids_npy),
            "n_subjects": int(x.shape[0]),
            "n_fibers": int(x.shape[1]),
        }
    qc = build_fiber_exposure_sidecar(
        data_mat,
        records,
        samplers,
        output_npy,
        fiber_ids_npy,
        max_fibers=max_fibers,
        fiber_chunk_size=fiber_chunk_size,
    )
    qc["label"] = label
    return np.load(output_npy, mmap_mode="r"), np.load(fiber_ids_npy), qc


def load_hf_reference_sidecar(
    hf_output_root: Path,
    connectome_slug: str,
    hf_ref_scale: str,
    n_fibers: int,
) -> tuple[np.ndarray, np.ndarray, Path]:
    hf_slug = slugify(hf_ref_scale)
    preprocess_dir = hf_output_root / connectome_slug / hf_slug / "peak_efield_tau800_primary" / "preprocess"
    x_path = preprocess_dir / "X_HF_fiber_float32_subject_major.npy"
    fiber_ids_path = preprocess_dir / "fiber_ids.npy"
    if not x_path.is_file() or not fiber_ids_path.is_file():
        raise FileNotFoundError(f"Missing matched HF fiber sidecar under {preprocess_dir}")
    x = np.load(x_path, mmap_mode="r")
    fiber_ids = np.load(fiber_ids_path)
    if x.shape[1] < n_fibers or fiber_ids.shape[0] < n_fibers:
        raise RuntimeError("matched HF sidecar has fewer fibers than the ULF component sidecar")
    return x[:, :n_fibers], fiber_ids[:n_fibers], preprocess_dir


def delta_hf_fiber_scores_from_weights(
    hf_reference: np.ndarray,
    hf_component: np.ndarray,
    weights: np.ndarray,
    candidate: np.ndarray,
    fiber_ids: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute DeltaHFFiberScore using the normative HF NetFiberScore definition."""
    ids = np.arange(1, weights.shape[0] + 1, dtype=np.int64) if fiber_ids is None else fiber_ids
    ref_net = fiber_net_score(hf_reference, weights, candidate, fiber_ids=ids)
    component_net = fiber_net_score(hf_component, weights, candidate, fiber_ids=ids)
    return {
        "delta": component_net.net_score - ref_net.net_score,
        "reference_score": ref_net.net_score,
        "component_score": component_net.net_score,
        "n_sweet_selected_fibers": int(ref_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(ref_net.sour_fiber_ids.size),
        "n_sweet_peak_fibers": int(ref_net.n_sweet_peak_fibers),
        "n_sour_peak_fibers": int(ref_net.n_sour_peak_fibers),
        "sweet_fiber_ids": ref_net.sweet_fiber_ids,
        "sour_fiber_ids": ref_net.sour_fiber_ids,
    }


def hf_support_row(
    *,
    subject_id: str,
    endpoint: str,
    connectome: str,
    tau: float,
    fold_id: int,
    hf_component: np.ndarray,
    support: np.ndarray,
    delta_hf_score: float,
    n_sweet_selected: int,
    n_sour_selected: int,
) -> dict[str, Any]:
    in_support = hf_component[support]
    out_support = hf_component[~support]
    total_sum = float(np.sum(hf_component, dtype=np.float64))
    in_sum = float(np.sum(in_support, dtype=np.float64))
    out_sum = max(0.0, total_sum - in_sum)
    out_touched = out_support[out_support > tau]
    return {
        "subject_id": subject_id,
        "endpoint": endpoint,
        "connectome": connectome,
        "tau": tau,
        "fold_id": fold_id,
        "score_map_source": "loocv_training_fold",
        "n_hf_score_fibers": int(np.count_nonzero(support)),
        "n_sweet_selected_fibers": int(n_sweet_selected),
        "n_sour_selected_fibers": int(n_sour_selected),
        "HF_in_support_sum": in_sum,
        "HF_total_sum": total_sum,
        "HF_out_support_sum": out_sum,
        "HF_out_support_fraction": out_sum / total_sum if total_sum > 0 else 0.0,
        "HF_out_support_touched_count": int(out_touched.size),
        "HF_out_support_top5": top_percent_mean(out_touched, 0.05),
        "DeltaHFFiberScore_in_support": float(delta_hf_score),
        "DeltaHFFiberScore_source_branch": "hf_normative_fiber_fold_local",
    }


def fit_hf_delta_full(
    hf_reference: np.ndarray,
    hf_component: np.ndarray,
    y_hf_ref: np.ndarray,
    y_base: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
    fiber_ids: np.ndarray,
) -> dict[str, Any]:
    s_tau = suprathreshold_matrix(hf_reference, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError("empty matched HF fiber candidate set")
    rho = np.full(hf_reference.shape[1], np.nan, dtype=np.float32)
    rho_candidate = partial_spearman_matrix(y_hf_ref, np.asarray(hf_reference[:, candidate]), y_base)
    rho[candidate] = rho_candidate.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    score = delta_hf_fiber_scores_from_weights(hf_reference, hf_component, weights, candidate, fiber_ids)
    score.update({"s_tau": s_tau, "coverage": coverage, "candidate": candidate, "weights": weights})
    return score


def fit_hf_delta_fold(
    hf_reference: np.ndarray,
    hf_component: np.ndarray,
    y_hf_ref: np.ndarray,
    y_base: np.ndarray,
    scale_direction: str,
    s_tau: np.ndarray,
    heldout: int,
    min_coverage: int,
    fiber_ids: np.ndarray,
) -> dict[str, Any]:
    train = np.array([idx for idx in range(y_hf_ref.shape[0]) if idx != heldout], dtype=int)
    coverage_fold = coverage_from_suprathreshold(s_tau) - s_tau[heldout].astype(np.int32)
    candidate = candidate_mask_from_coverage(coverage_fold, min_coverage)
    if not np.any(candidate):
        raise RuntimeError(f"empty matched HF fold candidate set for heldout {heldout}")
    rho_fold = partial_spearman_matrix(y_hf_ref[train], np.asarray(hf_reference[train][:, candidate]), y_base[train])
    weights = np.full(hf_reference.shape[1], np.nan, dtype=np.float32)
    weights[candidate] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
    score = delta_hf_fiber_scores_from_weights(hf_reference, hf_component, weights, candidate, fiber_ids)
    score.update({"candidate": candidate, "weights": weights})
    return score


def run_ulf_fiber_branch(
    *,
    branch_name: str,
    x_ulf_only: np.ndarray,
    y_post: np.ndarray,
    y_hf_ref: np.ndarray,
    nuisance_full: np.ndarray | None,
    nuisance_fold_provider: Any,
    subject_ids: list[str],
    scale_direction: str,
    tau: float,
    min_coverage: int,
    fiber_ids: np.ndarray,
) -> dict[str, Any]:
    s_tau = suprathreshold_matrix(x_ulf_only, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError(f"empty ULF fiber candidate set for branch {branch_name}")
    cov_full = y_hf_ref if nuisance_full is None else np.column_stack([y_hf_ref, nuisance_full])
    rho = np.full(x_ulf_only.shape[1], np.nan, dtype=np.float32)
    rho_candidate = partial_spearman_matrix(y_post, np.asarray(x_ulf_only[:, candidate]), cov_full)
    rho[candidate] = rho_candidate.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_net = fiber_net_score(np.asarray(x_ulf_only), weights, candidate, fiber_ids=fiber_ids)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_ids):
        row = {
            "subject_id": subject_id,
            "Y_post": y_post[idx],
            "Y_HF_ref": y_hf_ref[idx],
            "SweetPeak5": full_net.sweet_peak5[idx],
            "SourPeak5": full_net.sour_peak5[idx],
            "NetULFFiberScore": full_net.net_score[idx],
            "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
            "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
            "n_sweet_peak_fibers": int(full_net.n_sweet_peak_fibers),
            "n_sour_peak_fibers": int(full_net.n_sour_peak_fibers),
            "score_map_source": "full_sample",
            "is_primary_score": True,
        }
        if nuisance_full is not None:
            row["DeltaHFFiberScore"] = float(nuisance_full[idx])
        score_rows.append(row)

    pred = np.full(y_post.shape[0], np.nan, dtype=float)
    pred_base = np.full(y_post.shape[0], np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    support_rows: list[dict[str, Any]] = []
    for heldout in range(y_post.shape[0]):
        train = np.array([idx for idx in range(y_post.shape[0]) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty ULF fold candidate set for heldout {subject_ids[heldout]}")
        nuisance_fold_result = nuisance_fold_provider(heldout) if nuisance_fold_provider is not None else None
        nuisance_fold = nuisance_fold_result
        support_row = None
        if isinstance(nuisance_fold_result, dict):
            nuisance_fold = nuisance_fold_result["delta"]
            support_row = nuisance_fold_result.get("support_row")
        cov_train = y_hf_ref[train] if nuisance_fold is None else np.column_stack([y_hf_ref[train], nuisance_fold[train]])
        cov_test = y_hf_ref[[heldout]] if nuisance_fold is None else np.column_stack([y_hf_ref[[heldout]], nuisance_fold[[heldout]]])
        rho_fold = partial_spearman_matrix(y_post[train], np.asarray(x_ulf_only[train][:, candidate_fold]), cov_train)
        weights_fold = np.full(x_ulf_only.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(np.asarray(x_ulf_only), weights_fold, candidate_fold, fiber_ids=fiber_ids)
        fold_pred, beta = fit_linear_prediction(
            y_post[train],
            fold_net.net_score[train],
            cov_train,
            fold_net.net_score[[heldout]],
            cov_test,
        )
        fold_base, base_beta = fit_baseline_with_covariates(y_post[train], cov_train, cov_test)
        pred[heldout] = fold_pred[0]
        pred_base[heldout] = fold_base[0]
        row = {
            "fold_id": heldout + 1,
            "heldout_subject_id": subject_ids[heldout],
            "Y_post": y_post[heldout],
            "Y_HF_ref": y_hf_ref[heldout],
            "SweetPeak5_LOOCV": fold_net.sweet_peak5[heldout],
            "SourPeak5_LOOCV": fold_net.sour_peak5[heldout],
            "NetULFFiberScore_LOOCV": fold_net.net_score[heldout],
            "prediction_NetFiberScore_model": fold_pred[0],
            "prediction_baseline_only": fold_base[0],
            "residual_NetFiberScore_model": y_post[heldout] - fold_pred[0],
            "residual_baseline_only": y_post[heldout] - fold_base[0],
            "n_train": int(train.size),
            "n_candidate_fibers": int(np.count_nonzero(candidate_fold)),
            "n_sweet_selected_fibers": int(fold_net.sweet_fiber_ids.size),
            "n_sour_selected_fibers": int(fold_net.sour_fiber_ids.size),
            "delta_NetULFFiberScore": beta[1],
            "beta_Y_HF_ref": beta[2],
            "baseline_beta_Y_HF_ref": base_beta[1],
        }
        if nuisance_fold is not None:
            row["DeltaHFFiberScore_LOOCV"] = float(nuisance_fold[heldout])
            row["gamma_DeltaHFFiberScore"] = float(beta[3])
            row["baseline_gamma_DeltaHFFiberScore"] = float(base_beta[2])
            if support_row is not None:
                support_rows.append(support_row)
        fold_rows.append(row)

    return {
        "branch_name": branch_name,
        "score_rows": score_rows,
        "fold_rows": fold_rows,
        "support_rows": support_rows,
        "metrics": regression_metrics(y_post, pred, pred_base),
        "coverage": coverage,
        "rho": rho,
        "weights": weights,
        "candidate": candidate,
        "n_candidate_fibers": int(np.count_nonzero(candidate)),
        "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
    }


def write_branch_outputs(branch_dir: Path, branch: dict[str, Any], fiber_ids: np.ndarray, qc_common: dict[str, Any], manifest_common: dict[str, Any]) -> None:
    branch_dir.mkdir(parents=True, exist_ok=True)
    candidate_indices = np.where(branch["candidate"])[0]
    weight_rows = [
        {
            "fiber_id": int(fiber_ids[idx]),
            "coverage_tau800": int(branch["coverage"][idx]),
            "rho_ULF": float(branch["rho"][idx]) if np.isfinite(branch["rho"][idx]) else "",
            "M_ULF": float(branch["weights"][idx]) if np.isfinite(branch["weights"][idx]) else "",
            "is_candidate": True,
        }
        for idx in candidate_indices
    ]
    write_csv(branch_dir / "normative_ULF_fiber_weights.csv", weight_rows, ["fiber_id", "coverage_tau800", "rho_ULF", "M_ULF", "is_candidate"])
    score_fields = [
        "subject_id",
        "Y_post",
        "Y_HF_ref",
        "DeltaHFFiberScore",
        "SweetPeak5",
        "SourPeak5",
        "NetULFFiberScore",
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
        "Y_post",
        "Y_HF_ref",
        "DeltaHFFiberScore_LOOCV",
        "SweetPeak5_LOOCV",
        "SourPeak5_LOOCV",
        "NetULFFiberScore_LOOCV",
        "prediction_NetFiberScore_model",
        "prediction_baseline_only",
        "residual_NetFiberScore_model",
        "residual_baseline_only",
        "n_train",
        "n_candidate_fibers",
        "n_sweet_selected_fibers",
        "n_sour_selected_fibers",
        "delta_NetULFFiberScore",
        "beta_Y_HF_ref",
        "gamma_DeltaHFFiberScore",
        "baseline_beta_Y_HF_ref",
        "baseline_gamma_DeltaHFFiberScore",
    ]
    write_csv(branch_dir / "normative_ULF_fiber_scores.csv", branch["score_rows"], score_fields)
    write_csv(branch_dir / "normative_ULF_fiber_loocv_predictions.csv", branch["fold_rows"], fold_fields)
    if branch["support_rows"]:
        write_csv(
            branch_dir / "normative_ULF_fiber_delta_hf_support_summary.csv",
            branch["support_rows"],
            [
                "subject_id",
                "endpoint",
                "connectome",
                "tau",
                "fold_id",
                "score_map_source",
                "n_hf_score_fibers",
                "n_sweet_selected_fibers",
                "n_sour_selected_fibers",
                "HF_in_support_sum",
                "HF_total_sum",
                "HF_out_support_sum",
                "HF_out_support_fraction",
                "HF_out_support_touched_count",
                "HF_out_support_top5",
                "DeltaHFFiberScore_in_support",
                "DeltaHFFiberScore_source_branch",
            ],
        )
    qc = dict(qc_common)
    qc.update(
        {
            "branch": branch["branch_name"],
            "n_candidate_fibers": branch["n_candidate_fibers"],
            "n_sweet_selected_fibers": branch["n_sweet_selected_fibers"],
            "n_sour_selected_fibers": branch["n_sour_selected_fibers"],
            "loocv_metrics": branch["metrics"],
            "resampling_status": "not_run_observed_only",
        }
    )
    manifest = dict(manifest_common)
    manifest.update(
        {
            "branch": branch["branch_name"],
            "status": "PASS",
            "outputs": {
                "branch_dir": str(branch_dir),
                "weights_csv": str(branch_dir / "normative_ULF_fiber_weights.csv"),
                "scores_csv": str(branch_dir / "normative_ULF_fiber_scores.csv"),
                "loocv_predictions_csv": str(branch_dir / "normative_ULF_fiber_loocv_predictions.csv"),
                "mapping_qc_json": str(branch_dir / "normative_ULF_fiber_mapping_qc.json"),
                "generation_manifest_json": str(branch_dir / "normative_ULF_fiber_generation_manifest.json"),
            },
        }
    )
    write_json(branch_dir / "normative_ULF_fiber_mapping_qc.json", qc)
    write_json(branch_dir / "normative_ULF_fiber_generation_manifest.json", manifest)


def run_ulf_normative_fiber_observed(args: argparse.Namespace) -> int:
    started = time.time()
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(required_arg(args, "asset_root")).expanduser().resolve())
    clinical_root = Path(required_arg(args, "clinical_root")).expanduser().resolve()
    matlab_bin = Path(required_arg(args, "matlab_bin")).expanduser().resolve()
    readiness_csv = resolve_readiness_csv(Path(required_arg(args, "readiness_root")).expanduser().resolve(), args.readiness_csv)
    required_arg(args, "gate_status")
    required_arg(args, "output_root")
    required_arg(args, "hf_output_root")
    required_arg(args, "post_scale")
    connectome_key = required_arg(args, "connectome")
    if connectome_key not in CONNECTOMES:
        raise ValueError(f"unsupported connectome {connectome_key!r}; expected one of {sorted(CONNECTOMES)}")
    connectome_info = CONNECTOMES[connectome_key]
    connectome_slug = connectome_info["slug"]
    data_mat = asset_root / connectome_info["path"]
    if not data_mat.is_file():
        raise RuntimeError(f"connectome data.mat missing: {data_mat}")

    records, hf_ref_scale = load_ulf_records(clinical_root, args.post_scale)
    subject_ids = [record.subject_id for record in records]
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_hf_ref = np.array([record.y_hf_ref for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    scale_direction, scale_direction_source = infer_scale_direction(args.post_scale)
    if scale_direction not in {"lower", "higher"}:
        raise RuntimeError(f"unknown scale direction for {args.post_scale!r}")

    availability = load_component_availability(readiness_csv)
    availability = availability[
        availability["protocol"].astype(str).eq("STN+SNr")
        & availability["phase"].astype(str).eq("3m")
    ].copy()
    tau_name = tau_slug(args.tau)
    output_root = Path(args.output_root).expanduser().resolve() / connectome_slug / slugify(args.post_scale) / f"peak_efield_{tau_name}_observed"
    preprocess_dir = output_root / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)

    hf_samplers, hf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "HF",
        asset_root,
        matlab_bin,
        preprocess_dir,
        args.force_flip,
    )
    ulf_samplers, ulf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "ULF",
        asset_root,
        matlab_bin,
        preprocess_dir,
        args.force_flip,
    )
    x_hf_component, fiber_ids, hf_component_qc = load_or_build_component_exposure(
        data_mat,
        records,
        hf_samplers,
        preprocess_dir,
        "HF_component",
        max_fibers=args.max_fibers,
        fiber_chunk_size=args.fiber_chunk_size,
        force_rebuild=args.force_rebuild,
    )
    x_ulf_component, fiber_ids_ulf, ulf_component_qc = load_or_build_component_exposure(
        data_mat,
        records,
        ulf_samplers,
        preprocess_dir,
        "ULF_component",
        max_fibers=args.max_fibers,
        fiber_chunk_size=args.fiber_chunk_size,
        force_rebuild=args.force_rebuild,
    )
    if not np.array_equal(fiber_ids, fiber_ids_ulf):
        raise RuntimeError("HF and ULF component fiber IDs do not match")
    hf_reference_x, hf_reference_ids, hf_reference_preprocess = load_hf_reference_sidecar(
        Path(args.hf_output_root).expanduser().resolve(),
        connectome_slug,
        hf_ref_scale,
        int(x_hf_component.shape[1]),
    )
    if not np.array_equal(fiber_ids, hf_reference_ids):
        raise RuntimeError("ULF component fiber IDs do not match matched HF reference fiber IDs")

    x_ulf_only = apply_ulf_only_fiber_rule(x_hf_component, x_ulf_component, args.tau)
    np.save(preprocess_dir / "X_ULF_only_fiber_float32_subject_major.npy", np.asarray(x_ulf_only, dtype=np.float32))

    hf_delta_full = fit_hf_delta_full(
        np.asarray(hf_reference_x),
        np.asarray(x_hf_component),
        y_hf_ref,
        y_base,
        scale_direction,
        args.tau,
        args.min_coverage,
        fiber_ids,
    )

    def fold_delta_provider(heldout: int) -> dict[str, Any]:
        fold = fit_hf_delta_fold(
            np.asarray(hf_reference_x),
            np.asarray(x_hf_component),
            y_hf_ref,
            y_base,
            scale_direction,
            hf_delta_full["s_tau"],
            heldout,
            args.min_coverage,
            fiber_ids,
        )
        support = np.asarray(fold["candidate"], dtype=bool) & np.isfinite(fold["weights"])
        return {
            "delta": np.asarray(fold["delta"], dtype=float),
            "support_row": hf_support_row(
                subject_id=subject_ids[heldout],
                endpoint=args.post_scale,
                connectome=connectome_info["label"],
                tau=args.tau,
                fold_id=heldout + 1,
                hf_component=np.asarray(x_hf_component[heldout], dtype=float),
                support=support,
                delta_hf_score=float(fold["delta"][heldout]),
                n_sweet_selected=int(fold["n_sweet_selected_fibers"]),
                n_sour_selected=int(fold["n_sour_selected_fibers"]),
            ),
        }

    no_delta = run_ulf_fiber_branch(
        branch_name=f"ulf_peak_efield_{tau_name}_no_delta_hf",
        x_ulf_only=np.asarray(x_ulf_only),
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=None,
        nuisance_fold_provider=None,
        subject_ids=subject_ids,
        scale_direction=scale_direction,
        tau=args.tau,
        min_coverage=args.min_coverage,
        fiber_ids=fiber_ids,
    )
    delta = run_ulf_fiber_branch(
        branch_name=f"ulf_peak_efield_{tau_name}_delta_hf_adjusted",
        x_ulf_only=np.asarray(x_ulf_only),
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=np.asarray(hf_delta_full["delta"], dtype=float),
        nuisance_fold_provider=fold_delta_provider,
        subject_ids=subject_ids,
        scale_direction=scale_direction,
        tau=args.tau,
        min_coverage=args.min_coverage,
        fiber_ids=fiber_ids,
    )

    gate = read_b_gate_status(Path(args.gate_status).expanduser().resolve(), args.connectome)
    qc_common = {
        "model": "ULF normative connectome fiber",
        "post_scale": args.post_scale,
        "hf_reference_scale": hf_ref_scale,
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "connectome": connectome_info["label"],
        "connectome_slug": connectome_slug,
        "n_subjects": len(records),
        "tau_v_per_m": args.tau,
        "min_coverage": args.min_coverage,
        "n_fibers": int(x_ulf_only.shape[1]),
        "n_ulf_only_nonzero_subjects": int(np.count_nonzero(np.sum(x_ulf_only, axis=1) > 0)),
        "hf_component_qc": hf_component_qc,
        "ulf_component_qc": ulf_component_qc,
    }
    manifest_common = {
        "generated_at": iso_now(),
        "model": "ULF normative connectome fiber",
        "repo_root": str(repo_root),
        "asset_root": str(asset_root),
        "clinical_root": str(clinical_root),
        "readiness_csv": str(readiness_csv),
        "connectome": connectome_info["label"],
        "connectome_slug": connectome_slug,
        "data_mat": str(data_mat),
        "matched_hf_reference_preprocess": str(hf_reference_preprocess),
        "output_root": str(output_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        },
        "parameters": {
            "post_scale": args.post_scale,
            "hf_reference_scale": hf_ref_scale,
            "tau_v_per_m": args.tau,
            "min_coverage": args.min_coverage,
            "connectome": args.connectome,
            "max_fibers": int(args.max_fibers),
            "fiber_chunk_size": int(args.fiber_chunk_size),
            "random_seed": 42,
        },
        "hf_prediction_validity_status": gate["hf_prediction_validity_status"],
        "hf_gate_decision": gate["gate_decision"],
        "hf_gate_model_id": gate["model_id"],
        "ulf_primary_branch": gate["ulf_primary_branch"],
        "ulf_core_branches_run": [
            f"ulf_peak_efield_{tau_name}_no_delta_hf",
            f"ulf_peak_efield_{tau_name}_delta_hf_adjusted",
        ],
        "delta_hfscore_role": gate["delta_hfscore_role"],
        "branch_role_decision_reason": "Resolved from matched B gate status; no-DeltaHF remains primary unless matched B is predictive_valid.",
        "hf_model_support_status": "matched_hf_normative_fiber_sidecar_used_for_delta_hfscore",
        "resampling_status": "not_run_observed_only",
        "component_sampler_qc": {"HF": hf_sampler_qc, "ULF": ulf_sampler_qc},
        "runtime_profile": {"total_s": time.time() - started, "n_fibers": int(x_ulf_only.shape[1])},
    }
    write_branch_outputs(output_root / f"ulf_peak_efield_{tau_name}_no_delta_hf", no_delta, fiber_ids, qc_common, manifest_common)
    write_branch_outputs(output_root / f"ulf_peak_efield_{tau_name}_delta_hf_adjusted", delta, fiber_ids, qc_common, manifest_common)
    print(f"ULF normative fiber observed output: {output_root}")
    print(f"No-DeltaHF LOOCV Spearman rho: {no_delta['metrics']['spearman_rho']:.6g}; Q2: {no_delta['metrics']['q2']:.6g}")
    print(f"DeltaHF-adjusted LOOCV Spearman rho: {delta['metrics']['spearman_rho']:.6g}; Q2: {delta['metrics']['q2']:.6g}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default="", help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default="", help="Clinical workbook directory.")
    parser.add_argument("--readiness-root", default="", help="ULF component readiness run root.")
    parser.add_argument("--readiness-csv", default="", help="Explicit ULF component e-field availability CSV.")
    parser.add_argument("--gate-status", default="", help="A/B gate status CSV.")
    parser.add_argument("--output-root", default="", help="ULF normative fiber output root.")
    parser.add_argument("--hf-output-root", default="", help="Matched HF normative fiber output root.")
    parser.add_argument("--matlab-bin", default="", help="MATLAB executable.")
    parser.add_argument("--post-scale", default="", help="Raw STN+SNr post endpoint.")
    parser.add_argument("--connectome", choices=sorted(CONNECTOMES), default="", help="Public connectome to process.")
    parser.add_argument("--tau", type=float, default=800.0, help="Fiber inclusion threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Minimum subject coverage.")
    parser.add_argument("--fiber-chunk-size", type=int, default=10000, help="Number of fibers per sampling chunk.")
    parser.add_argument("--max-fibers", type=int, default=0, help="Development-only cap; 0 means full connectome.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    parser.add_argument("--force-rebuild", action="store_true", help="Regenerate component exposure sidecars.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_ulf_normative_fiber_observed(args)


if __name__ == "__main__":
    raise SystemExit(main())
