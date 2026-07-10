#!/usr/bin/env python3
"""Observed-only ULF normative connectome fiber driver."""

from __future__ import annotations

import argparse
import csv
import hashlib
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

from stnsnr_four_model_resolver import (
    branch_nuisance_design_status,
    classify_prediction_status,
    resolve_hf_source,
    safe_pearson,
    safe_spearman,
)
from stnsnr_four_model_readiness import (
    detect_asset_root,
    infer_scale_direction,
    parse_endpoint_scale,
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


ULF_NORM_FIBER_TAU_GRID = [400, 600, 800, 1000, 1200, 1500, 2000]
ULF_NORM_FIBER_COVERAGE_GRID = [5, 6, 7, 8, 10, 12]
ULF_NORM_FIBER_PRIMARY_TAU = 800
ULF_NORM_FIBER_PRIMARY_COVERAGE = 5


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


def ulf_fiber_branch_name(tau: float, coverage: int, branch: str, *, legacy: bool = False) -> str:
    """Return a branch name that preserves the configured threshold identity."""
    if branch not in {"no_delta_hf", "delta_hf_adjusted"}:
        raise ValueError(f"unsupported ULF normative-fiber branch {branch!r}")
    if legacy:
        return f"ulf_peak_efield_{tau_slug(tau)}_{branch}"
    return f"ulf_peak_efield_{tau_slug(tau)}_cov{int(coverage)}_{branch}"


def ulf_fiber_artifact_names(
    tau: float,
    coverage: int,
    branch: str,
    *,
    dynamic: bool,
) -> dict[str, str]:
    """Return configured names while retaining the legacy wrapper names on request."""
    if not dynamic:
        return {
            "weights_csv": "normative_ULF_fiber_weights.csv",
            "scores_csv": "normative_ULF_fiber_scores.csv",
            "predictions_csv": "normative_ULF_fiber_loocv_predictions.csv",
            "qc_json": "normative_ULF_fiber_mapping_qc.json",
            "branch_manifest": "normative_ULF_fiber_generation_manifest.json",
            "resolver_scan": "normative_ULF_fiber_tau_coverage_source_resolver_scan.csv",
            "resolver_manifest": "normative_ULF_fiber_tau_coverage_source_resolver_manifest.json",
            "selected_source": "normative_ULF_fiber_selected_source.json",
        }
    token = ulf_fiber_branch_name(tau, coverage, branch).removeprefix("ulf_peak_efield_")
    return {
        "weights_csv": f"normative_ULF_fiber_{token}_weights.csv",
        "scores_csv": f"normative_ULF_fiber_{token}_scores.csv",
        "predictions_csv": f"normative_ULF_fiber_{token}_loocv_predictions.csv",
        "qc_json": f"normative_ULF_fiber_{token}_mapping_qc.json",
        "branch_manifest": f"normative_ULF_fiber_{token}_generation_manifest.json",
        "resolver_scan": f"normative_ULF_fiber_{token}_source_resolver_scan.csv",
        "resolver_manifest": f"normative_ULF_fiber_{token}_source_resolver_manifest.json",
        "selected_source": f"normative_ULF_fiber_{token}_selected_source.json",
    }


def component_phase_from_post_scale(post_scale: str) -> str:
    """Return the STN+SNr component phase required by a ULF endpoint row."""
    _, post_protocol, post_phase = parse_endpoint_scale(post_scale)
    if post_protocol != "STN+SNr":
        raise ValueError(f"ULF normative fiber post scale must use STN+SNr protocol, got {post_scale!r}")
    return post_phase


def component_phase_slug_token(component_phase: str) -> str:
    """Return the scale-slug suffix that identifies an STN+SNr component phase."""
    return slugify(f"placeholder (STN+SNr, {component_phase})").removeprefix("placeholder_")


def component_cache_complete(preprocess_dir: Path) -> bool:
    required = [
        "X_HF_component_fiber_float32_subject_major.npy",
        "X_ULF_component_fiber_float32_subject_major.npy",
        "fiber_ids.npy",
    ]
    return all((preprocess_dir / name).is_file() for name in required)


def score_subject_ids_for_component_cache(preprocess_dir: Path, tau_name: str) -> list[str] | None:
    scores_csv = preprocess_dir.parent / f"ulf_peak_efield_{tau_name}_no_delta_hf" / "normative_ULF_fiber_scores.csv"
    if not scores_csv.is_file():
        return None
    table = pd.read_csv(scores_csv)
    if "subject_id" not in table.columns:
        return None
    return table["subject_id"].astype(str).tolist()


def find_reusable_component_preprocess_dir(
    output_root: Path,
    *,
    connectome_slug: str,
    component_phase: str,
    subject_ids: list[str],
    tau_name: str,
) -> Path | None:
    """Find a complete same-phase component cache with the same subject order."""
    connectome_root = Path(output_root) / connectome_slug
    if not connectome_root.is_dir():
        return None
    phase_token = component_phase_slug_token(component_phase)
    for scale_dir in sorted(path for path in connectome_root.iterdir() if path.is_dir()):
        if not scale_dir.name.endswith(phase_token):
            continue
        preprocess_dir = scale_dir / f"peak_efield_{tau_name}_observed" / "preprocess"
        if not component_cache_complete(preprocess_dir):
            continue
        cached_subject_ids = score_subject_ids_for_component_cache(preprocess_dir, tau_name)
        if cached_subject_ids == subject_ids:
            return preprocess_dir
    return None


def read_b_normative_fiber_dependency(
    hf_output_root: Path,
    connectome_slug: str,
    hf_ref_scale: str,
    gate_status_path: Path,
    connectome_key: str,
) -> dict[str, Any]:
    """Read the locked B-model normative fiber resolver for the matched HF reference endpoint."""
    hf_slug = slugify(hf_ref_scale)
    manifest_path = (
        hf_output_root
        / connectome_slug
        / hf_slug
        / "tau_coverage_source_resolver_scan"
        / "normative_HF_fiber_tau_coverage_source_resolver_manifest.json"
    )
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_status = str(data.get("hf_norm_fiber_source_status", "") or "")
        prediction_status = str(data.get("hf_norm_fiber_prediction_status", "") or "")
        if source_status in {"pre_specified_accepted", "scan_fallback_accepted"} and prediction_status == "error_predictive":
            primary = "delta_hf_adjusted"
            delta_role = "primary_error_predictive_hf_adjustment"
        elif source_status in {"pre_specified_accepted", "scan_fallback_accepted"}:
            primary = "no_delta_hf"
            delta_role = "stable_error_nonpredictive_hf_adjustment_sensitivity"
        else:
            primary = "no_delta_hf"
            delta_role = "not_run_no_stable_hf_norm_fiber_source"
        return {
            "model_id": gate_model_id_for_connectome(connectome_key),
            "gate_decision": "RESOLVED_FROM_HF_NORM_FIBER_SOURCE_SCAN",
            "hf_prediction_validity_status": prediction_status or "not_applicable",
            "hf_norm_fiber_source_status": source_status,
            "hf_norm_fiber_prediction_status": prediction_status or "not_applicable",
            "hf_norm_fiber_threshold_source": data.get("hf_norm_fiber_threshold_source", ""),
            "hf_norm_fiber_selected_tau_v_per_m": data.get(
                "hf_norm_fiber_selected_tau_v_per_m", ULF_NORM_FIBER_PRIMARY_TAU
            ),
            "hf_norm_fiber_selected_coverage": data.get(
                "hf_norm_fiber_selected_coverage", ULF_NORM_FIBER_PRIMARY_COVERAGE
            ),
            "ulf_primary_branch": primary,
            "delta_hfscore_role": delta_role,
            "source_resolver_manifest": str(manifest_path),
        }
    legacy = read_b_gate_status(gate_status_path, connectome_key)
    legacy.setdefault("hf_norm_fiber_source_status", "")
    legacy.setdefault("hf_norm_fiber_prediction_status", legacy.get("hf_prediction_validity_status", ""))
    legacy.setdefault("hf_norm_fiber_threshold_source", "legacy_gate_status")
    legacy.setdefault("hf_norm_fiber_selected_tau_v_per_m", ULF_NORM_FIBER_PRIMARY_TAU)
    legacy.setdefault("hf_norm_fiber_selected_coverage", ULF_NORM_FIBER_PRIMARY_COVERAGE)
    return legacy


def hf_overlap_tau_from_norm_dependency(dependency: dict[str, Any], fallback_tau: float) -> float:
    if dependency.get("hf_norm_fiber_source_status") in {"pre_specified_accepted", "scan_fallback_accepted"}:
        try:
            return float(dependency.get("hf_norm_fiber_selected_tau_v_per_m", fallback_tau))
        except (TypeError, ValueError):
            return float(fallback_tau)
    return math.inf


def apply_ulf_only_fiber_rule(
    hf_component: np.ndarray,
    ulf_component: np.ndarray,
    tau: float,
    *,
    hf_overlap_tau: float | None = None,
) -> np.ndarray:
    """Keep ULF exposure only where ULF is active and HF is not active."""
    hf = np.asarray(hf_component, dtype=np.float32)
    ulf = np.asarray(ulf_component, dtype=np.float32)
    if hf.shape != ulf.shape:
        raise ValueError("HF and ULF component matrices must have the same shape")
    locked_hf_tau = float(tau) if hf_overlap_tau is None else float(hf_overlap_tau)
    hf_active = np.zeros_like(hf, dtype=bool) if math.isinf(locked_hf_tau) else hf > locked_hf_tau
    return np.where((ulf > float(tau)) & ~hf_active, ulf, 0.0).astype(np.float32)


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
    fold_candidate_counts: list[int] = []
    net_score_nonconstant_all_folds = True
    for heldout in range(y_post.shape[0]):
        train = np.array([idx for idx in range(y_post.shape[0]) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty ULF fold candidate set for heldout {subject_ids[heldout]}")
        fold_candidate_counts.append(int(np.count_nonzero(candidate_fold)))
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
        if np.nanstd(fold_net.net_score[train]) == 0:
            net_score_nonconstant_all_folds = False
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

    fold_count_array = np.asarray(fold_candidate_counts, dtype=float)
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
        "fold_n_candidate_fibers_min": int(np.nanmin(fold_count_array)) if fold_count_array.size else 0,
        "fold_n_candidate_fibers_median": float(np.nanmedian(fold_count_array)) if fold_count_array.size else 0.0,
        "fold_n_candidate_fibers_max": int(np.nanmax(fold_count_array)) if fold_count_array.size else 0,
        "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
        "netulfscore_nonconstant_all_folds": bool(net_score_nonconstant_all_folds),
        "all_predictions_finite": bool(np.all(np.isfinite(pred)) and np.all(np.isfinite(pred_base))),
    }


def ulf_norm_fiber_hard_computability_passes(row: dict[str, Any]) -> bool:
    min_fibers = 1000 if str(row.get("connectome_key", "")) == "dtor" else 100
    return (
        float(row.get("n_subjects", 0) or 0) >= 12
        and float(row.get("fold_n_candidate_fibers_min", 0) or 0) >= min_fibers
        and bool(row.get("selected_fiber_pools_computable", False))
        and bool(row.get("netulfscore_nonconstant_all_folds", False))
        and str(row.get("branch_nuisance_design_status", "")) == "valid"
        and bool(row.get("all_predictions_finite", False))
    )


def ulf_norm_fiber_empty_scan_row(
    *,
    branch: str,
    branch_role: str,
    connectome_key: str,
    tau: int,
    coverage: int,
    n_subjects: int,
    branch_nuisance_design_status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "branch": branch,
        "branch_role": branch_role,
        "connectome_key": connectome_key,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": n_subjects,
        "n_candidate_fibers": 0,
        "fold_n_candidate_fibers_min": 0,
        "fold_n_candidate_fibers_median": 0,
        "fold_n_candidate_fibers_max": 0,
        "selected_fiber_pools_computable": False,
        "netulfscore_nonconstant_all_folds": False,
        "branch_nuisance_design_status": branch_nuisance_design_status,
        "all_predictions_finite": False,
        "loocv_spearman_rho": math.nan,
        "loocv_spearman_nominal_p": math.nan,
        "loocv_pearson_r": math.nan,
        "loocv_pearson_nominal_p": math.nan,
        "q2": math.nan,
        "mae_model": math.nan,
        "mae_baseline": math.nan,
        "rmse_model": math.nan,
        "rmse_baseline": math.nan,
        "passes_all_hard_filters": False,
        "ulf_norm_fiber_prediction_status": "not_applicable",
        "failure_reason": reason,
    }


def evaluate_ulf_norm_fiber_grid_cell(
    *,
    branch: str,
    branch_role: str,
    connectome_key: str,
    x_ulf_only: np.ndarray,
    y_post: np.ndarray,
    y_hf_ref: np.ndarray,
    nuisance_full: np.ndarray | None,
    nuisance_fold_provider: Any,
    subject_ids: list[str],
    scale_direction: str,
    tau: int,
    coverage: int,
    fiber_ids: np.ndarray,
) -> dict[str, Any]:
    design_status = branch_nuisance_design_status(y_hf_ref=y_hf_ref, delta_hfscore=nuisance_full)
    if design_status != "valid":
        return ulf_norm_fiber_empty_scan_row(
            branch=branch,
            branch_role=branch_role,
            connectome_key=connectome_key,
            tau=tau,
            coverage=coverage,
            n_subjects=int(y_post.shape[0]),
            branch_nuisance_design_status=design_status,
            reason=design_status,
        )
    try:
        result = run_ulf_fiber_branch(
            branch_name=ulf_fiber_branch_name(float(tau), int(coverage), branch),
            x_ulf_only=x_ulf_only,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            nuisance_full=nuisance_full,
            nuisance_fold_provider=nuisance_fold_provider,
            subject_ids=subject_ids,
            scale_direction=scale_direction,
            tau=float(tau),
            min_coverage=int(coverage),
            fiber_ids=fiber_ids,
        )
    except Exception as exc:
        return ulf_norm_fiber_empty_scan_row(
            branch=branch,
            branch_role=branch_role,
            connectome_key=connectome_key,
            tau=tau,
            coverage=coverage,
            n_subjects=int(y_post.shape[0]),
            branch_nuisance_design_status=design_status,
            reason=str(exc),
        )
    y_true = np.array([row["Y_post"] for row in result["fold_rows"]], dtype=float)
    pred = np.array([row["prediction_NetFiberScore_model"] for row in result["fold_rows"]], dtype=float)
    pred_base = np.array([row["prediction_baseline_only"] for row in result["fold_rows"]], dtype=float)
    residual_model = y_true - pred
    residual_base = y_true - pred_base
    rho, rho_p = safe_spearman(y_true, pred)
    pearson, pearson_p = safe_pearson(y_true, pred)
    row = {
        "branch": branch,
        "branch_role": branch_role,
        "connectome_key": connectome_key,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": int(y_post.shape[0]),
        "n_candidate_fibers": int(result["n_candidate_fibers"]),
        "fold_n_candidate_fibers_min": int(result["fold_n_candidate_fibers_min"]),
        "fold_n_candidate_fibers_median": float(result["fold_n_candidate_fibers_median"]),
        "fold_n_candidate_fibers_max": int(result["fold_n_candidate_fibers_max"]),
        "selected_fiber_pools_computable": bool(
            result["n_sweet_selected_fibers"] > 0 and result["n_sour_selected_fibers"] > 0
        ),
        "netulfscore_nonconstant_all_folds": bool(result["netulfscore_nonconstant_all_folds"]),
        "branch_nuisance_design_status": design_status,
        "all_predictions_finite": bool(result["all_predictions_finite"]),
        "loocv_spearman_rho": rho,
        "loocv_spearman_nominal_p": rho_p,
        "loocv_pearson_r": pearson,
        "loocv_pearson_nominal_p": pearson_p,
        "q2": result["metrics"].get("q2", math.nan),
        "mae_model": float(np.mean(np.abs(residual_model))),
        "mae_baseline": float(np.mean(np.abs(residual_base))),
        "rmse_model": float(np.sqrt(np.mean(residual_model * residual_model))),
        "rmse_baseline": float(np.sqrt(np.mean(residual_base * residual_base))),
        "failure_reason": "",
    }
    row["passes_all_hard_filters"] = ulf_norm_fiber_hard_computability_passes(row)
    row["ulf_norm_fiber_prediction_status"] = (
        classify_prediction_status(row) if row["passes_all_hard_filters"] else "not_applicable"
    )
    return row


def resolve_ulf_norm_fiber_branch(
    rows: list[dict[str, Any]],
    *,
    tau_grid: tuple[float, ...] | list[float] = tuple(ULF_NORM_FIBER_TAU_GRID),
    coverage_grid: tuple[int, ...] | list[int] = tuple(ULF_NORM_FIBER_COVERAGE_GRID),
    primary_tau: float = ULF_NORM_FIBER_PRIMARY_TAU,
    primary_coverage: int = ULF_NORM_FIBER_PRIMARY_COVERAGE,
) -> dict[str, Any]:
    resolved = resolve_hf_source(
        rows,
        primary_tau=float(primary_tau),
        primary_coverage=int(primary_coverage),
        tau_grid=tuple(float(value) for value in tau_grid),
        coverage_grid=tuple(int(value) for value in coverage_grid),
        pass_predicate=ulf_norm_fiber_hard_computability_passes,
    )
    return {
        "ulf_norm_fiber_source_status": resolved["source_status"],
        "ulf_norm_fiber_prediction_status": resolved["prediction_status"],
        "ulf_norm_fiber_threshold_source": resolved["threshold_source"],
        "ulf_norm_fiber_selected_tau_v_per_m": resolved["selected_tau"],
        "ulf_norm_fiber_selected_coverage": resolved["selected_coverage"],
        "ulf_norm_fiber_selected_adjacent_passing_grid_cells": resolved["selected_adjacent_passing_grid_cells"],
        "ulf_norm_fiber_source_failure_reasons": resolved["source_failure_reasons"],
    }


def ulf_norm_fiber_endpoint_status_for_primary(primary_resolution: dict[str, Any]) -> str:
    source_status = primary_resolution.get("ulf_norm_fiber_source_status", "")
    prediction_status = primary_resolution.get("ulf_norm_fiber_prediction_status", "")
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"} and prediction_status == "error_predictive":
        return "primary_branch_error_predictive"
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"} and prediction_status == "error_nonpredictive":
        return "primary_branch_error_nonpredictive"
    if source_status == "absent_no_stable_grid":
        return "absent_no_stable_ulf_grid"
    return "primary_branch_input_failure"


def write_ulf_norm_fiber_source_scan_outputs(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]],
    branch_resolutions: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    scan_filename: str = "normative_ULF_fiber_tau_coverage_source_resolver_scan.csv",
    manifest_filename: str = "normative_ULF_fiber_tau_coverage_source_resolver_manifest.json",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scan_csv = output_dir / scan_filename
    manifest_json = output_dir / manifest_filename
    fieldnames = [
        "branch",
        "branch_role",
        "connectome_key",
        "tau",
        "coverage",
        "n_subjects",
        "n_candidate_fibers",
        "fold_n_candidate_fibers_min",
        "fold_n_candidate_fibers_median",
        "fold_n_candidate_fibers_max",
        "selected_fiber_pools_computable",
        "netulfscore_nonconstant_all_folds",
        "branch_nuisance_design_status",
        "all_predictions_finite",
        "loocv_spearman_rho",
        "loocv_spearman_nominal_p",
        "loocv_pearson_r",
        "loocv_pearson_nominal_p",
        "q2",
        "mae_model",
        "mae_baseline",
        "rmse_model",
        "rmse_baseline",
        "passes_all_hard_filters",
        "ulf_norm_fiber_prediction_status",
        "failure_reason",
    ]
    write_csv(scan_csv, rows, fieldnames)
    write_json(
        manifest_json,
        {
            **manifest,
            "branch_resolutions": branch_resolutions,
            "n_grid_rows": len(rows),
            "n_passing_grid_rows": int(sum(ulf_norm_fiber_hard_computability_passes(row) for row in rows)),
            "outputs": {"scan_csv": str(scan_csv), "manifest_json": str(manifest_json)},
        },
    )
    return {"scan_csv": str(scan_csv), "manifest_json": str(manifest_json)}


def write_branch_outputs(
    branch_dir: Path,
    branch: dict[str, Any],
    fiber_ids: np.ndarray,
    qc_common: dict[str, Any],
    manifest_common: dict[str, Any],
    *,
    artifact_names: dict[str, str] | None = None,
) -> None:
    branch_dir.mkdir(parents=True, exist_ok=True)
    names = artifact_names or ulf_fiber_artifact_names(800, 5, "no_delta_hf", dynamic=False)
    coverage_column = f"coverage_{tau_slug(float(manifest_common.get('selected_tau_v_per_m', 800)))}"
    candidate_indices = np.where(branch["candidate"])[0]
    weight_rows = [
        {
            "fiber_id": int(fiber_ids[idx]),
            coverage_column: int(branch["coverage"][idx]),
            "rho_ULF": float(branch["rho"][idx]) if np.isfinite(branch["rho"][idx]) else "",
            "M_ULF": float(branch["weights"][idx]) if np.isfinite(branch["weights"][idx]) else "",
            "is_candidate": True,
        }
        for idx in candidate_indices
    ]
    write_csv(
        branch_dir / names["weights_csv"],
        weight_rows,
        ["fiber_id", coverage_column, "rho_ULF", "M_ULF", "is_candidate"],
    )
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
    write_csv(branch_dir / names["scores_csv"], branch["score_rows"], score_fields)
    write_csv(branch_dir / names["predictions_csv"], branch["fold_rows"], fold_fields)
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
                "weights_csv": str(branch_dir / names["weights_csv"]),
                "scores_csv": str(branch_dir / names["scores_csv"]),
                "loocv_predictions_csv": str(branch_dir / names["predictions_csv"]),
                "mapping_qc_json": str(branch_dir / names["qc_json"]),
                "generation_manifest_json": str(branch_dir / names["branch_manifest"]),
            },
        }
    )
    write_json(branch_dir / names["qc_json"], qc)
    write_json(branch_dir / names["branch_manifest"], manifest)


def _configured_clinical_records(config: Any) -> tuple[list[ULFRecord], np.ndarray, np.ndarray, np.ndarray]:
    """Load one configured endpoint without inferring scale, protocol, phase, or subjects."""
    path = Path(config.clinical_table)
    if not path.is_file():
        raise FileNotFoundError(f"configured clinical table is missing: {path}")
    if path.suffix.lower() == ".csv":
        table = pd.read_csv(path)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        table = pd.read_excel(path)
    else:
        raise ValueError(f"unsupported configured clinical table format: {path.suffix}")
    columns = dict(config.clinical_columns)
    missing = sorted(set(columns.values()).difference(table.columns))
    if missing:
        raise RuntimeError("configured clinical table is missing columns: " + ", ".join(missing))

    def condition(protocol: str, phase: str) -> pd.DataFrame:
        return table[
            table[columns["scale"]].astype(str).eq(config.scale)
            & table[columns["protocol"]].astype(str).eq(protocol)
            & table[columns["phase"]].astype(str).eq(phase)
        ].copy()

    post = condition(config.endpoint_protocol, config.endpoint_phase)
    reference = condition(config.hf_reference_protocol, config.hf_reference_phase)
    subject_column = columns["subject_id"]
    for label, rows in (("post", post), ("HF reference", reference)):
        duplicates = rows[rows.duplicated(subject_column, keep=False)][subject_column].astype(str).unique()
        if duplicates.size:
            raise RuntimeError(f"duplicate configured {label} rows: {','.join(sorted(duplicates))}")
    post_by_subject = post.set_index(post[subject_column].astype(str), drop=False)
    reference_by_subject = reference.set_index(reference[subject_column].astype(str), drop=False)
    records: list[ULFRecord] = []
    for subject_id in config.subject_order:
        if subject_id not in post_by_subject.index or subject_id not in reference_by_subject.index:
            raise RuntimeError(f"configured endpoint subject is missing clinical rows: {subject_id}")
        post_row = post_by_subject.loc[subject_id]
        reference_row = reference_by_subject.loc[subject_id]
        values = (
            float(post_row[columns["value"]]),
            float(reference_row[columns["value"]]),
            float(post_row[columns["baseline"]]),
        )
        if not all(np.isfinite(value) for value in values):
            raise RuntimeError(f"configured endpoint subject has nonfinite clinical values: {subject_id}")
        records.append(ULFRecord(subject_id=subject_id, y_post=values[0], y_hf_ref=values[1], y_base=values[2]))
    y_post = np.asarray([record.y_post for record in records], dtype=float)
    y_hf_ref = np.asarray([record.y_hf_ref for record in records], dtype=float)
    y_base = np.asarray([record.y_base for record in records], dtype=float)
    return records, y_post, y_hf_ref, y_base


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ulf_normative_fiber_hf_component_configured(config: Any) -> dict[str, Any]:
    """Build endpoint-ordered HF-component exposure on an explicit normative-fiber axis."""
    required = (
        "scale",
        "endpoint_protocol",
        "endpoint_phase",
        "connectome_id",
        "connectome_path",
        "output_dir",
    )
    missing = [name for name in required if not str(getattr(config, name, "")).strip()]
    if missing:
        raise ValueError("configured HF-component fiber input is missing: " + ", ".join(missing))
    records, _, _, _ = _configured_clinical_records(config)
    subject_ids = [record.subject_id for record in records]
    if tuple(subject_ids) != tuple(config.subject_order):
        raise RuntimeError("configured HF-component clinical subject order drifted")
    availability = load_component_availability(Path(config.readiness_csv))
    for column in ("protocol", "phase"):
        if column not in availability.columns:
            raise RuntimeError(f"configured component readiness CSV is missing {column!r}")
    availability = availability[
        availability["protocol"].astype(str).eq(config.endpoint_protocol)
        & availability["phase"].astype(str).eq(config.endpoint_phase)
    ].copy()
    if availability.empty:
        raise RuntimeError("configured component readiness has no rows for the requested endpoint phase")

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samplers, sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "HF",
        Path(config.asset_root),
        Path(config.matlab_bin),
        output_dir,
        bool(config.force_flip),
    )
    exposure, fiber_ids, exposure_qc = load_or_build_component_exposure(
        Path(config.connectome_path),
        records,
        samplers,
        output_dir,
        "HF_component",
        max_fibers=int(config.max_fibers),
        fiber_chunk_size=int(config.fiber_chunk_size),
        force_rebuild=bool(config.force_rebuild),
    )
    exposure_path = output_dir / "X_HF_component_fiber_float32_subject_major.npy"
    fiber_ids_path = output_dir / "fiber_ids.npy"
    observed_shape = tuple(int(value) for value in np.asarray(exposure).shape)
    if observed_shape != (len(subject_ids), int(np.asarray(fiber_ids).size)):
        raise RuntimeError("configured HF-component exposure shape is inconsistent")
    return {
        "exposure_matrix": str(exposure_path),
        "exposure_sha256": _file_sha256(exposure_path),
        "fiber_ids": str(fiber_ids_path),
        "fiber_ids_file_sha256": _file_sha256(fiber_ids_path),
        "feature_axis_sha256": _array_sha256(np.asarray(fiber_ids)),
        "feature_axis_count": int(np.asarray(fiber_ids).size),
        "feature_identity_source": config.connectome_identity_source,
        "subject_order": subject_ids,
        "component_sampler_qc": sampler_qc,
        "component_exposure_qc": exposure_qc,
    }


def _configured_delta_inputs(config: Any, subject_ids: list[str]) -> tuple[np.ndarray | None, Any, list[dict[str, Any]]]:
    if config.branch == "no_delta_hf":
        if config.delta_full_scores_path is not None or config.delta_fold_scores_path is not None:
            raise ValueError("no_delta_hf must not receive DeltaHF score artifacts")
        return None, None, []
    if config.branch != "delta_hf_adjusted":
        raise ValueError(f"unsupported configured ULF normative-fiber branch {config.branch!r}")
    if config.delta_full_scores_path is None or config.delta_fold_scores_path is None:
        raise ValueError("delta_hf_adjusted requires full and fold-by-subject DeltaHF artifacts")
    full_scores = np.asarray(np.load(config.delta_full_scores_path), dtype=float)
    fold_scores = np.asarray(np.load(config.delta_fold_scores_path), dtype=float)
    n_subjects = len(subject_ids)
    if full_scores.shape != (n_subjects,):
        raise ValueError(f"DeltaHF full-score shape must be {(n_subjects,)}, got {full_scores.shape}")
    if fold_scores.shape != (n_subjects, n_subjects):
        raise ValueError(
            f"DeltaHF fold-by-subject shape must be {(n_subjects, n_subjects)}, got {fold_scores.shape}"
        )
    if not np.all(np.isfinite(full_scores)) or not np.all(np.isfinite(fold_scores)):
        raise ValueError("DeltaHF full and fold-by-subject scores must be finite")
    support_rows: list[dict[str, Any]] = []
    if config.delta_support_rows_path is not None:
        support_rows = pd.read_csv(config.delta_support_rows_path).to_dict(orient="records")

    def fold_provider(heldout: int) -> dict[str, Any]:
        def matches(item: dict[str, Any]) -> bool:
            if str(item.get("subject_id", "")) == subject_ids[heldout]:
                return True
            fold_id = pd.to_numeric(pd.Series([item.get("fold_id")]), errors="coerce").iloc[0]
            return bool(np.isfinite(fold_id) and int(fold_id) == heldout + 1)

        row = next(
            (item for item in support_rows if matches(item)),
            None,
        )
        return {"delta": fold_scores[heldout], "support_row": row}

    return full_scores, fold_provider, support_rows


def run_ulf_normative_fiber_configured(config: Any) -> dict[str, Any]:
    """Run one configured ULF fiber branch and resolve its source grid."""
    started = time.time()
    required = (
        "scale",
        "endpoint_protocol",
        "endpoint_phase",
        "hf_reference_protocol",
        "hf_reference_phase",
        "connectome_id",
        "connectome_path",
        "output_dir",
        "branch",
    )
    missing = [name for name in required if not str(getattr(config, name, "")).strip()]
    if missing:
        raise ValueError("configured ULF fiber input is missing: " + ", ".join(missing))
    if config.branch == "delta_hf_adjusted" and not math.isfinite(float(config.hf_overlap_tau)):
        raise ValueError("adjusted ULF fiber branch requires a finite matched HF selected tau")

    records, y_post, y_hf_ref, y_base = _configured_clinical_records(config)
    subject_ids = [record.subject_id for record in records]
    availability = load_component_availability(Path(config.readiness_csv))
    for column in ("protocol", "phase"):
        if column not in availability.columns:
            raise RuntimeError(f"configured component readiness CSV is missing {column!r}")
    availability = availability[
        availability["protocol"].astype(str).eq(config.endpoint_protocol)
        & availability["phase"].astype(str).eq(config.endpoint_phase)
    ].copy()
    if availability.empty:
        raise RuntimeError("configured component readiness has no rows for the requested endpoint phase")

    preprocess_dir = Path(config.preprocess_dir)
    output_dir = Path(config.output_dir)
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    hf_samplers, hf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "HF",
        Path(config.asset_root),
        Path(config.matlab_bin),
        preprocess_dir,
        bool(config.force_flip),
    )
    ulf_samplers, ulf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "ULF",
        Path(config.asset_root),
        Path(config.matlab_bin),
        preprocess_dir,
        bool(config.force_flip),
    )
    x_hf_component, fiber_ids, hf_component_qc = load_or_build_component_exposure(
        Path(config.connectome_path),
        records,
        hf_samplers,
        preprocess_dir,
        "HF_component",
        max_fibers=int(config.max_fibers),
        fiber_chunk_size=int(config.fiber_chunk_size),
        force_rebuild=bool(config.force_rebuild),
    )
    x_ulf_component, ulf_fiber_ids, ulf_component_qc = load_or_build_component_exposure(
        Path(config.connectome_path),
        records,
        ulf_samplers,
        preprocess_dir,
        "ULF_component",
        max_fibers=int(config.max_fibers),
        fiber_chunk_size=int(config.fiber_chunk_size),
        force_rebuild=bool(config.force_rebuild),
    )
    if not np.array_equal(fiber_ids, ulf_fiber_ids):
        raise RuntimeError("configured HF and ULF component fiber identities differ")
    axis_sha = _array_sha256(np.asarray(fiber_ids))
    if config.hf_feature_axis_sha256 is not None and axis_sha != config.hf_feature_axis_sha256:
        raise RuntimeError("configured ULF component fiber axis does not match the immutable HF source")
    hf_component_path = preprocess_dir / "X_HF_component_fiber_float32_subject_major.npy"
    ulf_component_path = preprocess_dir / "X_ULF_component_fiber_float32_subject_major.npy"
    y_base_path = preprocess_dir / "Y_base_float64.npy"
    np.save(y_base_path, np.asarray(y_base, dtype=np.float64))

    nuisance_full, nuisance_provider, _ = _configured_delta_inputs(config, subject_ids)
    rows: list[dict[str, Any]] = []
    for tau in config.tau_grid:
        x_ulf_only = apply_ulf_only_fiber_rule(
            np.asarray(x_hf_component),
            np.asarray(x_ulf_component),
            float(tau),
            hf_overlap_tau=float(config.hf_overlap_tau),
        )
        for coverage in config.coverage_grid:
            rows.append(
                evaluate_ulf_norm_fiber_grid_cell(
                    branch=config.branch,
                    branch_role="configured_candidate",
                    connectome_key=config.connectome_id,
                    x_ulf_only=x_ulf_only,
                    y_post=y_post,
                    y_hf_ref=y_hf_ref,
                    nuisance_full=nuisance_full,
                    nuisance_fold_provider=nuisance_provider,
                    subject_ids=subject_ids,
                    scale_direction=config.scale_direction,
                    tau=float(tau),
                    coverage=int(coverage),
                    fiber_ids=np.asarray(fiber_ids),
                )
            )
    resolution = resolve_ulf_norm_fiber_branch(
        rows,
        tau_grid=config.tau_grid,
        coverage_grid=config.coverage_grid,
        primary_tau=config.primary_tau,
        primary_coverage=config.primary_coverage,
    )
    names = ulf_fiber_artifact_names(
        config.primary_tau,
        config.primary_coverage,
        config.branch,
        dynamic=bool(config.dynamic_names),
    )
    scan_outputs = write_ulf_norm_fiber_source_scan_outputs(
        output_dir,
        rows=rows,
        branch_resolutions={config.branch: resolution},
        manifest={
            "generated_at": iso_now(),
            "analysis": "configured_ulf_normative_fiber_source_resolver",
            "endpoint": {
                "scale": config.scale,
                "protocol": config.endpoint_protocol,
                "phase": config.endpoint_phase,
                "subject_order": subject_ids,
            },
            "inputs": {
                "clinical_table": str(config.clinical_table),
                "stimulation_table": str(config.stimulation_table),
                "readiness_csv": str(config.readiness_csv),
                "derivatives_root": str(config.derivatives_root),
                "asset_root": str(config.asset_root),
            },
            "branch": config.branch,
            "nuisance_columns": list(config.nuisance_columns),
            "connectome_id": config.connectome_id,
            "connectome_label": config.connectome_label,
            "connectome_path": str(config.connectome_path),
            "connectome_identity_source": config.connectome_identity_source,
            "tau_grid_v_per_m": list(config.tau_grid),
            "coverage_grid": list(config.coverage_grid),
            "pre_specified_tau_v_per_m": config.primary_tau,
            "pre_specified_coverage": config.primary_coverage,
            "hf_source_status": config.hf_source_status,
            "hf_prediction_status": config.hf_prediction_status,
            "hf_source_record_hash": config.hf_source_record_hash,
            "hf_overlap_tau_v_per_m": config.hf_overlap_tau if math.isfinite(config.hf_overlap_tau) else "+Inf",
            "hf_overlap_coverage": config.hf_overlap_coverage,
            "delta_hf_record_hash": config.delta_hf_record_hash,
            "delta_support_status": config.delta_support_status,
            "delta_full_scores_path": (
                str(config.delta_full_scores_path) if config.delta_full_scores_path is not None else None
            ),
            "delta_fold_scores_path": (
                str(config.delta_fold_scores_path) if config.delta_fold_scores_path is not None else None
            ),
            "delta_support_rows_path": (
                str(config.delta_support_rows_path) if config.delta_support_rows_path is not None else None
            ),
            "runtime_s": time.time() - started,
        },
        scan_filename=names["resolver_scan"],
        manifest_filename=names["resolver_manifest"],
    )

    selected_source_path = output_dir / names["selected_source"]
    selected_payload: dict[str, Any] = {"branch": config.branch, **resolution}
    selected_artifacts: dict[str, str] = {}
    source_status = str(resolution["ulf_norm_fiber_source_status"])
    selected_tau = resolution["ulf_norm_fiber_selected_tau_v_per_m"]
    selected_coverage = resolution["ulf_norm_fiber_selected_coverage"]
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"}:
        x_selected = apply_ulf_only_fiber_rule(
            np.asarray(x_hf_component),
            np.asarray(x_ulf_component),
            float(selected_tau),
            hf_overlap_tau=float(config.hf_overlap_tau),
        )
        selected_branch = run_ulf_fiber_branch(
            branch_name=ulf_fiber_branch_name(float(selected_tau), int(selected_coverage), config.branch),
            x_ulf_only=x_selected,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            nuisance_full=nuisance_full,
            nuisance_fold_provider=nuisance_provider,
            subject_ids=subject_ids,
            scale_direction=config.scale_direction,
            tau=float(selected_tau),
            min_coverage=int(selected_coverage),
            fiber_ids=np.asarray(fiber_ids),
        )
        selected_names = ulf_fiber_artifact_names(
            float(selected_tau), int(selected_coverage), config.branch, dynamic=bool(config.dynamic_names)
        )
        branch_dir = output_dir / ulf_fiber_branch_name(float(selected_tau), int(selected_coverage), config.branch)
        write_branch_outputs(
            branch_dir,
            selected_branch,
            np.asarray(fiber_ids),
            {
                "model": "configured ULF normative connectome fiber",
                "branch": config.branch,
                "connectome_id": config.connectome_id,
                "n_subjects": len(subject_ids),
                "hf_component_qc": hf_component_qc,
                "ulf_component_qc": ulf_component_qc,
            },
            {
                "generated_at": iso_now(),
                "branch": config.branch,
                "selected_tau_v_per_m": float(selected_tau),
                "selected_coverage": int(selected_coverage),
                "scale_direction": config.scale_direction,
                "subject_order": subject_ids,
                "hf_source_record_hash": config.hf_source_record_hash,
                "delta_hf_record_hash": config.delta_hf_record_hash,
                "component_sampler_qc": {"HF": hf_sampler_qc, "ULF": ulf_sampler_qc},
            },
            artifact_names=selected_names,
        )
        exposure_path = branch_dir / "X_ULF_only_fiber_float32_subject_major.npy"
        np.save(exposure_path, np.asarray(x_selected, dtype=np.float32))
        selected_artifacts = {
            "selected_manifest": str(branch_dir / selected_names["branch_manifest"]),
            "selected_scores": str(branch_dir / selected_names["scores_csv"]),
            "exposure_matrix": str(exposure_path),
        }
        selected_payload["selected_branch_dir"] = str(branch_dir)
    write_json(selected_source_path, selected_payload)

    return {
        "branch": config.branch,
        "source_status": source_status,
        "prediction_status": resolution["ulf_norm_fiber_prediction_status"],
        "threshold_source": resolution["ulf_norm_fiber_threshold_source"],
        "selected_tau": selected_tau,
        "selected_coverage": selected_coverage,
        "adjacent_support": resolution["ulf_norm_fiber_selected_adjacent_passing_grid_cells"],
        "subject_order": subject_ids,
        "feature_axis": {
            "ids_path": str(preprocess_dir / "fiber_ids.npy"),
            "count": int(np.asarray(fiber_ids).shape[0]),
            "sha256": axis_sha,
            "identity_source": config.connectome_identity_source,
        },
        "artifacts": {
            "source_status": scan_outputs["manifest_json"],
            "selected_source": str(selected_source_path),
            "hf_component_exposure": str(hf_component_path),
            "ulf_component_exposure": str(ulf_component_path),
            "y_base": str(y_base_path),
            **selected_artifacts,
        },
    }


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

    component_phase = component_phase_from_post_scale(args.post_scale)
    availability = load_component_availability(readiness_csv)
    availability = availability[
        availability["protocol"].astype(str).eq("STN+SNr")
        & availability["phase"].astype(str).eq(component_phase)
    ].copy()
    tau_name = tau_slug(args.tau)
    output_root = Path(args.output_root).expanduser().resolve() / connectome_slug / slugify(args.post_scale) / f"peak_efield_{tau_name}_observed"
    preprocess_dir = output_root / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    base_output_root = Path(args.output_root).expanduser().resolve()
    default_component_cache = (
        base_output_root
        / connectome_slug
        / slugify(args.post_scale)
        / f"peak_efield_{tau_slug(ULF_NORM_FIBER_PRIMARY_TAU)}_observed"
        / "preprocess"
    )
    reusable_component_cache = (
        find_reusable_component_preprocess_dir(
            base_output_root,
            connectome_slug=connectome_slug,
            component_phase=component_phase,
            subject_ids=subject_ids,
            tau_name=tau_slug(ULF_NORM_FIBER_PRIMARY_TAU),
        )
        if not args.force_rebuild
        else None
    )
    if default_component_cache.is_dir() and component_cache_complete(default_component_cache) and not args.force_rebuild:
        component_preprocess_dir = default_component_cache
    elif reusable_component_cache is not None:
        component_preprocess_dir = reusable_component_cache
    else:
        component_preprocess_dir = preprocess_dir

    hf_samplers, hf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "HF",
        asset_root,
        matlab_bin,
        component_preprocess_dir,
        args.force_flip,
    )
    ulf_samplers, ulf_sampler_qc = prepare_component_fiber_samplers(
        availability,
        records,
        "ULF",
        asset_root,
        matlab_bin,
        component_preprocess_dir,
        args.force_flip,
    )
    x_hf_component, fiber_ids, hf_component_qc = load_or_build_component_exposure(
        data_mat,
        records,
        hf_samplers,
        component_preprocess_dir,
        "HF_component",
        max_fibers=args.max_fibers,
        fiber_chunk_size=args.fiber_chunk_size,
        force_rebuild=args.force_rebuild,
    )
    x_ulf_component, fiber_ids_ulf, ulf_component_qc = load_or_build_component_exposure(
        data_mat,
        records,
        ulf_samplers,
        component_preprocess_dir,
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

    gate = read_b_normative_fiber_dependency(
        Path(args.hf_output_root).expanduser().resolve(),
        connectome_slug,
        hf_ref_scale,
        Path(args.gate_status).expanduser().resolve(),
        args.connectome,
    )
    locked_hf_overlap_tau = hf_overlap_tau_from_norm_dependency(gate, args.tau)
    locked_hf_coverage = int(float(gate.get("hf_norm_fiber_selected_coverage", args.min_coverage)))

    x_ulf_only = apply_ulf_only_fiber_rule(x_hf_component, x_ulf_component, args.tau, hf_overlap_tau=locked_hf_overlap_tau)
    np.save(preprocess_dir / "X_ULF_only_fiber_float32_subject_major.npy", np.asarray(x_ulf_only, dtype=np.float32))

    hf_source_exists = gate.get("hf_norm_fiber_source_status") in {"pre_specified_accepted", "scan_fallback_accepted"}
    hf_delta_full = (
        fit_hf_delta_full(
            np.asarray(hf_reference_x),
            np.asarray(x_hf_component),
            y_hf_ref,
            y_base,
            scale_direction,
            locked_hf_overlap_tau,
            locked_hf_coverage,
            fiber_ids,
        )
        if hf_source_exists
        else None
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
            locked_hf_coverage,
            fiber_ids,
        )
        support = np.asarray(fold["candidate"], dtype=bool) & np.isfinite(fold["weights"])
        return {
            "delta": np.asarray(fold["delta"], dtype=float),
            "support_row": hf_support_row(
                subject_id=subject_ids[heldout],
                endpoint=args.post_scale,
                connectome=connectome_info["label"],
                tau=locked_hf_overlap_tau,
                fold_id=heldout + 1,
                hf_component=np.asarray(x_hf_component[heldout], dtype=float),
                support=support,
                delta_hf_score=float(fold["delta"][heldout]),
                n_sweet_selected=int(fold["n_sweet_selected_fibers"]),
                n_sour_selected=int(fold["n_sour_selected_fibers"]),
            ),
        }

    if args.source_resolver_scan:
        rows: list[dict[str, Any]] = []
        branch_resolutions: dict[str, dict[str, Any]] = {}
        branch_specs: list[tuple[str, str, np.ndarray | None, Any]] = [
            (
                "no_delta_hf",
                "primary" if gate["ulf_primary_branch"] == "no_delta_hf" else "sensitivity",
                None,
                None,
            )
        ]
        if hf_source_exists and hf_delta_full is not None:
            branch_specs.append(
                (
                    "delta_hf_adjusted",
                    "primary" if gate["ulf_primary_branch"] == "delta_hf_adjusted" else "sensitivity",
                    np.asarray(hf_delta_full["delta"], dtype=float),
                    fold_delta_provider,
                )
            )
        for tau in ULF_NORM_FIBER_TAU_GRID:
            x_ulf_only_tau = apply_ulf_only_fiber_rule(
                x_hf_component,
                x_ulf_component,
                tau,
                hf_overlap_tau=locked_hf_overlap_tau,
            )
            for branch_name, branch_role, nuisance_full, nuisance_provider in branch_specs:
                for coverage_min in ULF_NORM_FIBER_COVERAGE_GRID:
                    print(
                        f"[{connectome_slug}/{slugify(args.post_scale)}/{branch_name}] "
                        f"Evaluating tau={tau} V/m, Coverage>={coverage_min}",
                        flush=True,
                    )
                    rows.append(
                        evaluate_ulf_norm_fiber_grid_cell(
                            branch=branch_name,
                            branch_role=branch_role,
                            connectome_key=args.connectome,
                            x_ulf_only=np.asarray(x_ulf_only_tau),
                            y_post=y_post,
                            y_hf_ref=y_hf_ref,
                            nuisance_full=nuisance_full,
                            nuisance_fold_provider=nuisance_provider,
                            subject_ids=subject_ids,
                            scale_direction=scale_direction,
                            tau=tau,
                            coverage=coverage_min,
                            fiber_ids=fiber_ids,
                        )
                    )
        for branch_name, _, _, _ in branch_specs:
            branch_rows = [row for row in rows if row["branch"] == branch_name]
            branch_resolutions[branch_name] = resolve_ulf_norm_fiber_branch(branch_rows)
        intended_primary_branch = gate["ulf_primary_branch"]
        primary_resolution = branch_resolutions.get(intended_primary_branch, {})
        endpoint_status = (
            ulf_norm_fiber_endpoint_status_for_primary(primary_resolution)
            if primary_resolution
            else "primary_branch_input_failure"
        )
        scan_dir = output_root / "tau_coverage_source_resolver_scan"
        outputs = write_ulf_norm_fiber_source_scan_outputs(
            scan_dir,
            rows=rows,
            branch_resolutions=branch_resolutions,
            manifest={
                "generated_at": iso_now(),
                "analysis": "ulf_normative_fiber_tau_coverage_source_resolver_scan",
                "model": "ULF normative connectome fiber",
                "post_scale": args.post_scale,
                "hf_reference_scale": hf_ref_scale,
                "connectome": connectome_info["label"],
                "connectome_slug": connectome_slug,
                "scale_direction": scale_direction,
                "scale_direction_source": scale_direction_source,
                "tau_grid_v_per_m": ULF_NORM_FIBER_TAU_GRID,
                "coverage_grid": ULF_NORM_FIBER_COVERAGE_GRID,
                "pre_specified_tau_v_per_m": ULF_NORM_FIBER_PRIMARY_TAU,
                "pre_specified_coverage": ULF_NORM_FIBER_PRIMARY_COVERAGE,
                "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
                "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
                "hf_norm_fiber_source_status": gate.get("hf_norm_fiber_source_status", ""),
                "hf_norm_fiber_prediction_status": gate.get("hf_norm_fiber_prediction_status", ""),
                "hf_norm_fiber_threshold_source": gate.get("hf_norm_fiber_threshold_source", ""),
                "hf_norm_fiber_selected_tau_v_per_m": gate.get("hf_norm_fiber_selected_tau_v_per_m", ""),
                "hf_norm_fiber_selected_coverage": gate.get("hf_norm_fiber_selected_coverage", ""),
                "intended_primary_branch": intended_primary_branch,
                "ulf_primary_branch": intended_primary_branch,
                "delta_hfscore_role": gate["delta_hfscore_role"],
                "ulf_norm_fiber_endpoint_model_status": endpoint_status,
                "runtime_s": time.time() - started,
            },
        )
        print(f"ULF normative fiber source resolver output: {scan_dir}")
        print(
            json.dumps(
                {"branch_resolutions": branch_resolutions, "ulf_norm_fiber_endpoint_model_status": endpoint_status},
                indent=2,
                sort_keys=True,
            )
        )
        print(f"Scan CSV: {outputs['scan_csv']}")
        return 0

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
        nuisance_full=np.asarray(hf_delta_full["delta"], dtype=float) if hf_delta_full is not None else None,
        nuisance_fold_provider=fold_delta_provider if hf_delta_full is not None else None,
        subject_ids=subject_ids,
        scale_direction=scale_direction,
        tau=args.tau,
        min_coverage=args.min_coverage,
        fiber_ids=fiber_ids,
    )

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
        "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
        "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
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
        "component_preprocess_dir": str(component_preprocess_dir),
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
            "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
            "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
            "min_coverage": args.min_coverage,
            "connectome": args.connectome,
            "max_fibers": int(args.max_fibers),
            "fiber_chunk_size": int(args.fiber_chunk_size),
            "random_seed": 42,
        },
        "hf_prediction_validity_status": gate["hf_prediction_validity_status"],
        "hf_norm_fiber_source_status": gate.get("hf_norm_fiber_source_status", ""),
        "hf_norm_fiber_prediction_status": gate.get("hf_norm_fiber_prediction_status", ""),
        "hf_norm_fiber_threshold_source": gate.get("hf_norm_fiber_threshold_source", ""),
        "hf_norm_fiber_selected_tau_v_per_m": gate.get("hf_norm_fiber_selected_tau_v_per_m", ""),
        "hf_norm_fiber_selected_coverage": gate.get("hf_norm_fiber_selected_coverage", ""),
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
    parser.add_argument("--source-resolver-scan", action="store_true", help="Run the ULF normative fiber tau/Coverage source resolver scan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_ulf_normative_fiber_observed(args)


if __name__ == "__main__":
    raise SystemExit(main())
