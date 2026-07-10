#!/usr/bin/env python3
"""Observed-only ULF direct voxel driver for the four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pandas as pd

from stnsnr_four_model_resolver import (
    branch_nuisance_design_status,
    classify_prediction_status,
    resolve_hf_source,
    safe_pearson,
    safe_spearman,
)
from stnsnr_four_model_execution_status import latest_run_dir
from stnsnr_four_model_readiness import (
    DEFAULT_CANONICAL_ASSET_ROOT,
    DEFAULT_CLINICAL_ROOT,
    DEFAULT_MATLAB,
    DEFAULT_VAL_ROOT,
    RAW_CLINICAL_FILE,
    detect_asset_root,
    infer_scale_direction,
    parse_endpoint_scale,
    repo_root_from_file,
)
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
from stnsnr_hf_direct_voxel_smoke import (
    SubjectRecord,
    collect_side_field_paths,
    filter_hf_stn_rows,
    fit_baseline_only,
    flip_left_fields_with_matlab,
    load_stim_table,
    right_brainmask_voxels,
    right_brainmask_voxels_from_path,
    sample_max_at_xyz,
    slugify,
    write_nifti_from_flat,
)


DEFAULT_OUTPUT_ROOT = DEFAULT_VAL_ROOT / "summary/direct_voxel/ulf"
DEFAULT_READINESS_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution/ulf_component_readiness"
DEFAULT_GATE_STATUS = DEFAULT_VAL_ROOT / "summary/four_model_execution/gate_status/four_model_gate_status.csv"
DEFAULT_POST_SCALE = "MDS-UPDRS III score (STN+SNr, 3 m)"
ULF_DIRECT_TAU_GRID = [100, 150, 180, 200, 220, 250, 300, 350, 400, 500]
ULF_DIRECT_COVERAGE_GRID = [5, 6, 7, 8, 10, 12]
ULF_DIRECT_PRIMARY_TAU = 200
ULF_DIRECT_PRIMARY_COVERAGE = 5
ULF_DIRECT_CANDIDATE_THRESHOLD = 100.0


@dataclass(frozen=True)
class ConfiguredULFDirectVoxelRun:
    """Complete configured input for exactly one ULF direct-voxel branch."""

    endpoint_id: str
    scale_label: str
    direction: str
    outcome_protocol: str
    outcome_phase: str
    hf_reference_protocol: str
    hf_reference_phase: str
    subject_order: tuple[str, ...]
    branch: str
    branch_name: str
    nuisance_columns: tuple[str, ...]
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    brainmask: Path
    asset_root: Path
    readiness_csv: Path
    matlab_bin: Path
    model_cache_root: Path
    output_root: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    hf_overlap_tau: float
    hf_overlap_coverage: int | None
    delta_hf_tau: float | None
    delta_hf_coverage: int | None
    delta_full_scores: Path | None
    delta_fold_scores: Path | None
    delta_support_rows: Path | None

    def __post_init__(self) -> None:
        if not self.endpoint_id or not self.scale_label:
            raise ValueError("configured ULF endpoint id and scale label must be nonempty")
        if self.direction not in {"lower", "higher"}:
            raise ValueError("configured ULF scale direction must be lower or higher")
        if self.branch not in {"no_delta_hf", "delta_hf_adjusted"}:
            raise ValueError(f"unsupported configured ULF branch {self.branch!r}")
        if not self.subject_order:
            raise ValueError("configured ULF subject order must be nonempty")
        if not self.tau_grid or not self.coverage_grid:
            raise ValueError("configured ULF tau and coverage grids must be nonempty")
        if self.primary_tau not in self.tau_grid or self.primary_coverage not in self.coverage_grid:
            raise ValueError("configured ULF primary cell must be present in its scan grids")
        expected_nuisance = (
            ("Y_HF_ref",)
            if self.branch == "no_delta_hf"
            else ("Y_HF_ref", "DeltaHFScore")
        )
        if self.nuisance_columns != expected_nuisance:
            raise ValueError("configured ULF nuisance columns do not match the requested branch")
        if self.branch == "delta_hf_adjusted":
            if not math.isfinite(self.hf_overlap_tau):
                raise ValueError("adjusted ULF branch requires a finite selected HF threshold")
            if self.delta_hf_tau != self.hf_overlap_tau:
                raise ValueError("selected HF tau must drive overlap and DeltaHFScore")
            if self.delta_hf_coverage != self.hf_overlap_coverage:
                raise ValueError("selected HF coverage must drive overlap and DeltaHFScore")
            if any(
                path is None
                for path in (self.delta_full_scores, self.delta_fold_scores, self.delta_support_rows)
            ):
                raise ValueError("adjusted ULF branch requires full, fold, and support DeltaHF artifacts")


def _threshold_token(value: int | float) -> str:
    return f"{float(value):g}".replace("-", "neg").replace(".", "p")


def ulf_direct_branch_name(branch: str, tau: float, coverage: int) -> str:
    """Return a branch name bound to the actual ULF source cell."""
    if branch not in {"no_delta_hf", "delta_hf_adjusted"}:
        raise ValueError(f"unsupported ULF direct branch {branch!r}")
    return f"tau{_threshold_token(tau)}_cov{int(coverage)}_{branch}"


@dataclass(frozen=True)
class ULFRecord:
    subject_id: str
    y_post: float
    y_hf_ref: float
    y_base: float


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


def _sanitize(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "pass"}


def load_ulf_records(clinical_root: Path, post_scale: str) -> tuple[list[ULFRecord], str]:
    """Load raw post-HF+ULF scores and matched HF-only reference scores."""
    raw_path = clinical_root / RAW_CLINICAL_FILE
    raw_df = pd.read_excel(raw_path)
    base_scale, post_protocol, post_phase = parse_endpoint_scale(post_scale)
    if post_protocol != "STN+SNr":
        raise ValueError(f"ULF direct voxel post scale must use STN+SNr protocol, got {post_scale!r}")

    hf_ref_scale = f"{base_scale} (STN, 3 m)"
    post_rows = raw_df[
        raw_df["Scale"].astype(str).eq(base_scale)
        & raw_df["Protocol"].astype(str).eq("STN+SNr")
        & raw_df["Phase"].astype(str).eq(post_phase)
    ].copy()
    hf_rows = raw_df[
        raw_df["Scale"].astype(str).eq(base_scale)
        & raw_df["Protocol"].astype(str).eq("STN")
        & raw_df["Phase"].astype(str).eq("3m")
    ].copy()
    merged = post_rows[["ID", "Value", "Baseline"]].rename(
        columns={"Value": "Y_post", "Baseline": "Baseline_post"}
    ).merge(
        hf_rows[["ID", "Value", "Baseline"]].rename(columns={"Value": "Y_HF_ref", "Baseline": "Baseline_hf"}),
        on="ID",
        how="inner",
    )
    merged = merged.sort_values("ID")
    records: list[ULFRecord] = []
    for _, row in merged.iterrows():
        if pd.isna(row["Y_post"]) or pd.isna(row["Y_HF_ref"]) or pd.isna(row["Baseline_post"]):
            continue
        records.append(
            ULFRecord(
                subject_id=_sanitize(row["ID"]),
                y_post=float(row["Y_post"]),
                y_hf_ref=float(row["Y_HF_ref"]),
                y_base=float(row["Baseline_post"]),
            )
        )
    if len(records) < 12:
        raise RuntimeError(f"post scale {post_scale!r} has only {len(records)} valid paired subjects")
    return records, hf_ref_scale


def resolve_readiness_csv(readiness_root: Path, explicit_csv: str | None) -> Path:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    run_dir = latest_run_dir(readiness_root)
    if run_dir is None:
        return Path("")
    return run_dir / "ulf_component_efield_availability.csv"


def load_component_availability(readiness_csv: Path) -> pd.DataFrame:
    if not readiness_csv.is_file():
        raise FileNotFoundError(f"Missing ULF component readiness CSV: {readiness_csv}")
    table = pd.read_csv(readiness_csv)
    required = {"subject_id", "side", "frequency_class", "efield_exists", "efield_path", "status"}
    missing = sorted(required.difference(table.columns))
    if missing:
        raise RuntimeError("component readiness CSV is missing columns: " + ", ".join(missing))
    return table


def component_side_paths(
    availability: pd.DataFrame,
    records: list[ULFRecord],
    frequency_class: str,
) -> tuple[dict[tuple[str, str], list[Path]], list[dict[str, Any]]]:
    """Return existing component e-field paths grouped by subject and side."""
    subject_ids = {record.subject_id for record in records}
    rows = availability[
        availability["subject_id"].astype(str).isin(subject_ids)
        & availability["frequency_class"].astype(str).eq(frequency_class)
    ].copy()
    side_paths: dict[tuple[str, str], list[Path]] = {}
    qc_rows: list[dict[str, Any]] = []
    for record in records:
        for side in ["L", "R"]:
            side_rows = rows[rows["subject_id"].astype(str).eq(record.subject_id) & rows["side"].astype(str).eq(side)]
            paths = [
                Path(str(path)).expanduser().resolve()
                for path in side_rows["efield_path"].dropna().astype(str).tolist()
                if str(path).strip()
            ]
            missing = [str(path) for path in paths if not path.is_file()]
            if missing:
                raise FileNotFoundError(
                    f"Missing {frequency_class} component e-field for {record.subject_id} side {side}: "
                    + "; ".join(missing)
                )
            unique_paths = sorted({path for path in paths if path.is_file()})
            side_paths[(record.subject_id, side)] = unique_paths
            qc_rows.append(
                {
                    "subject_id": record.subject_id,
                    "side": side,
                    "frequency_class": frequency_class,
                    "n_source_paths": len(unique_paths),
                    "source_paths": [str(path) for path in unique_paths],
                    "path_mode": sorted(set(side_rows.get("path_mode", pd.Series(dtype=str)).astype(str).tolist())),
                }
            )
    return side_paths, qc_rows


def flip_component_left_fields(
    repo_root: Path,
    matlab_bin: Path,
    side_paths: dict[tuple[str, str], list[Path]],
    preprocess_dir: Path,
    component_label: str,
    force: bool,
) -> tuple[dict[str, list[Path]], dict[str, Any]]:
    """Flip non-empty left component fields and keep empty-left subjects as zero exposure."""
    nonempty = {key: value for key, value in side_paths.items() if key[1] == "L" and value}
    if not nonempty:
        return {}, {"status": "SKIPPED", "detail": f"no left {component_label} fields", "n_jobs": 0}
    component_dir = preprocess_dir / f"{component_label}_component"
    return flip_left_fields_with_matlab(repo_root, matlab_bin, nonempty, component_dir, force)


def build_component_exposure_matrix(
    records: list[ULFRecord],
    side_paths: dict[tuple[str, str], list[Path]],
    flipped_left_paths: dict[str, list[Path]],
    xyz: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Build bilateral component exposure, using zeros when one side has no component."""
    x = np.zeros((len(records), xyz.shape[0]), dtype=np.float32)
    qc_rows: list[dict[str, Any]] = []
    for row_idx, record in enumerate(records):
        right_paths = side_paths.get((record.subject_id, "R"), [])
        left_paths = flipped_left_paths.get(record.subject_id, [])
        right_qc: list[dict[str, Any]] = []
        left_qc: list[dict[str, Any]] = []
        if right_paths:
            right_values, right_qc = sample_max_at_xyz(right_paths, xyz)
        else:
            right_values = np.zeros(xyz.shape[0], dtype=np.float32)
        if left_paths:
            left_values, left_qc = sample_max_at_xyz(left_paths, xyz)
        else:
            left_values = np.zeros(xyz.shape[0], dtype=np.float32)
        x[row_idx] = (right_values + left_values) / 2.0
        qc_rows.append(
            {
                "subject_id": record.subject_id,
                "n_right_paths": len(right_paths),
                "n_left_paths": len(left_paths),
                "right": right_qc,
                "left_to_right": left_qc,
                "bilateral_nonzero_voxels": int(np.count_nonzero(x[row_idx])),
                "bilateral_max": float(np.max(x[row_idx])),
                "bilateral_sum": float(np.sum(x[row_idx], dtype=np.float64)),
            }
        )
    return x, qc_rows


def build_hf_reference_exposure(
    records: list[ULFRecord],
    clinical_root: Path,
    derivatives_root: Path,
    asset_root: Path,
    matlab_bin: Path,
    preprocess_dir: Path,
    force_flip: bool,
    xyz: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    """Build the matched STN 3m HF-only reference exposure matrix."""
    hf_records = [SubjectRecord(record.subject_id, record.y_hf_ref, record.y_base) for record in records]
    subject_ids = {record.subject_id for record in records}
    stim_rows = filter_hf_stn_rows(load_stim_table(clinical_root), subject_ids, protocol="STN", phase="3m", target="STN")
    if stim_rows["ID"].nunique() != len(records):
        missing = sorted(subject_ids - set(stim_rows["ID"].astype(str).unique()))
        raise RuntimeError("missing HF-only STN reference rows for subjects: " + ", ".join(missing))
    side_paths, side_qc = collect_side_field_paths(hf_records, stim_rows, derivatives_root)
    flipped_left_paths, flip_result = flip_left_fields_with_matlab(
        repo_root=asset_root,
        matlab_bin=matlab_bin,
        side_paths=side_paths,
        preprocess_dir=preprocess_dir / "hf_reference",
        force=force_flip,
    )
    exposure, sampling_qc = build_component_exposure_matrix(records, side_paths, flipped_left_paths, xyz)
    return exposure, side_qc + sampling_qc, flip_result


def read_a_gate_status(gate_status_path: Path) -> dict[str, Any]:
    if not gate_status_path.is_file():
        return {
            "hf_prediction_validity_status": "unknown",
            "gate_decision": "MISSING_GATE_STATUS",
            "delta_hfscore_role": "exploratory_only_or_not_run",
            "ulf_primary_branch": "no_delta_hf",
        }
    table = pd.read_csv(gate_status_path)
    row = table[table["model_id"].astype(str).eq("A")]
    if row.empty:
        decision = "MISSING_OUTPUT"
    else:
        decision = str(row.iloc[0].get("decision", "MISSING_OUTPUT"))
    if decision == "PASS_TO_NEXT_ROUND":
        status = "predictive_valid"
        role = "primary_nuisance_adjustment"
        primary = "delta_hf_adjusted"
    elif decision == "STOP_FORMAL_REMAIN_EXPLORATORY":
        status = "failed_unstable"
        role = "unstable_generated_covariate_sensitivity"
        primary = "no_delta_hf"
    else:
        status = "unknown_or_missing"
        role = "exploratory_only_or_not_run"
        primary = "no_delta_hf"
    return {
        "hf_prediction_validity_status": status,
        "gate_decision": decision,
        "delta_hfscore_role": role,
        "ulf_primary_branch": primary,
    }


def read_a_direct_voxel_dependency(output_root: Path, hf_ref_scale: str, gate_status_path: Path) -> dict[str, Any]:
    """Read the locked A-model direct voxel resolver for the matched HF reference endpoint."""
    scale_slug = slugify(hf_ref_scale)
    summary_path = (
        output_root.parent
        / "hf"
        / "posthoc_threshold_scan_all_scales"
        / "all_scales_posthoc_threshold_scan_summary.csv"
    )
    if summary_path.is_file():
        table = pd.read_csv(summary_path)
        if "scale_slug" in table.columns:
            matched = table[table["scale_slug"].astype(str).eq(scale_slug)]
        else:
            matched = table.iloc[0:1]
        if not matched.empty:
            row = matched.iloc[0]
            source_status = _sanitize(row.get("hf_voxel_source_status", ""))
            prediction_status = _sanitize(row.get("hf_voxel_prediction_status", ""))
            selected_tau = row.get("hf_voxel_selected_tau_v_per_m", row.get("selected_tau", ULF_DIRECT_PRIMARY_TAU))
            selected_coverage = row.get("hf_voxel_selected_coverage", row.get("selected_coverage", ULF_DIRECT_PRIMARY_COVERAGE))
            if source_status in {"pre_specified_accepted", "scan_fallback_accepted"}:
                if prediction_status == "error_predictive":
                    primary = "delta_hf_adjusted"
                    delta_role = "primary_error_predictive_hf_adjustment"
                else:
                    primary = "no_delta_hf"
                    delta_role = "stable_error_nonpredictive_hf_adjustment_sensitivity"
            else:
                primary = "no_delta_hf"
                delta_role = "not_run_no_stable_hf_voxel_source"
            return {
                "hf_voxel_source_status": source_status,
                "hf_voxel_prediction_status": prediction_status or "not_applicable",
                "hf_voxel_threshold_source": _sanitize(row.get("hf_voxel_threshold_source", "")),
                "hf_voxel_selected_tau_v_per_m": float(selected_tau) if str(selected_tau).strip() else ULF_DIRECT_PRIMARY_TAU,
                "hf_voxel_selected_coverage": int(float(selected_coverage)) if str(selected_coverage).strip() else ULF_DIRECT_PRIMARY_COVERAGE,
                "hf_prediction_validity_status": prediction_status or "not_applicable",
                "gate_decision": "RESOLVED_FROM_HF_VOXEL_SOURCE_SCAN",
                "ulf_primary_branch": primary,
                "delta_hfscore_role": delta_role,
            }
    legacy = read_a_gate_status(gate_status_path)
    legacy.setdefault("hf_voxel_source_status", "")
    legacy.setdefault("hf_voxel_prediction_status", legacy.get("hf_prediction_validity_status", ""))
    legacy.setdefault("hf_voxel_threshold_source", "legacy_gate_status")
    legacy.setdefault("hf_voxel_selected_tau_v_per_m", ULF_DIRECT_PRIMARY_TAU)
    legacy.setdefault("hf_voxel_selected_coverage", ULF_DIRECT_PRIMARY_COVERAGE)
    return legacy


def hf_overlap_tau_from_dependency(dependency: dict[str, Any], fallback_tau: float) -> float:
    """Return the locked HF-overlap threshold; +Inf means no HF overlap exclusion."""
    if dependency.get("hf_voxel_source_status") in {"pre_specified_accepted", "scan_fallback_accepted"}:
        try:
            return float(dependency.get("hf_voxel_selected_tau_v_per_m", fallback_tau))
        except (TypeError, ValueError):
            return float(fallback_tau)
    return math.inf


def fit_baseline_with_covariates(train_y: np.ndarray, train_covariates: np.ndarray, test_covariates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train_cov = np.asarray(train_covariates, dtype=float)
    test_cov = np.asarray(test_covariates, dtype=float)
    if train_cov.ndim == 1:
        train_cov = train_cov[:, None]
    if test_cov.ndim == 1:
        test_cov = test_cov[:, None]
    train_design = np.column_stack([np.ones(train_y.shape[0]), train_cov])
    test_design = np.column_stack([np.ones(test_cov.shape[0]), test_cov])
    beta, *_ = np.linalg.lstsq(train_design, train_y, rcond=None)
    return test_design @ beta, beta


def delta_hf_scores_from_map(
    hf_reference_x: np.ndarray,
    hf_component_x: np.ndarray,
    weights_hf: np.ndarray,
    score_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    valid = np.asarray(score_mask, dtype=bool) & np.isfinite(weights_hf)
    reference_score, n_valid = mean_map_score(hf_reference_x, weights_hf, valid)
    component_score, _ = mean_map_score(hf_component_x, weights_hf, valid)
    return component_score - reference_score, reference_score, component_score, n_valid


def top_percent_mean(values: np.ndarray, percent: float) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0
    count = max(1, int(math.ceil(float(percent) * finite.size)))
    return float(np.mean(np.sort(finite)[::-1][:count]))


def hf_support_summary_for_subject(
    *,
    subject_id: str,
    endpoint: str,
    phase: str,
    tau: float,
    score_map_source: str,
    fold_id: int | str,
    hf_component_full: np.ndarray,
    hf_candidate_sparse: np.ndarray,
    valid_candidate_mask: np.ndarray,
    delta_hf_score: float,
    n_hf_score_voxels: int,
    voxel_volume_mm3: float,
) -> dict[str, Any]:
    """Summarize how much HF component exposure is inside learned HF support."""
    full_support = np.zeros(hf_component_full.shape[0], dtype=bool)
    full_support[hf_candidate_sparse] = np.asarray(valid_candidate_mask, dtype=bool)
    in_support = hf_component_full[full_support]
    out_support = hf_component_full[~full_support]
    hf_in_support_sum = float(np.sum(in_support, dtype=np.float64))
    hf_total_sum = float(np.sum(hf_component_full, dtype=np.float64))
    hf_out_support_sum = max(0.0, hf_total_sum - hf_in_support_sum)
    out_suprathreshold = out_support[out_support > float(tau)]
    return {
        "subject_id": subject_id,
        "endpoint": endpoint,
        "phase": phase,
        "tau": tau,
        "score_map_source": score_map_source,
        "fold_id": fold_id,
        "n_hf_score_voxels": int(n_hf_score_voxels),
        "HF_in_support_sum": hf_in_support_sum,
        "HF_total_sum": hf_total_sum,
        "HF_out_support_sum": hf_out_support_sum,
        "HF_out_support_fraction": hf_out_support_sum / hf_total_sum if hf_total_sum > 0 else 0.0,
        "HF_out_support_volume_tau": float(out_suprathreshold.size * voxel_volume_mm3),
        "HF_out_support_top5": top_percent_mean(out_suprathreshold, 0.05),
        "DeltaHFScore_in_support": float(delta_hf_score),
        "DeltaHFScore_source_branch": "hf_direct_voxel_fold_local",
    }


def fit_hf_delta_full(
    hf_reference_x: np.ndarray,
    hf_component_x: np.ndarray,
    y_hf_ref: np.ndarray,
    y_base: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
) -> dict[str, Any]:
    s_tau = suprathreshold_matrix(hf_reference_x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    omega = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(omega):
        raise RuntimeError("empty HF Omega while computing DeltaHFScore")
    rho = np.full(hf_reference_x.shape[1], np.nan, dtype=np.float32)
    rho_omega = partial_spearman_matrix(y_hf_ref, hf_reference_x[:, omega], y_base)
    rho[omega] = rho_omega.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    delta, ref_score, component_score, n_valid = delta_hf_scores_from_map(hf_reference_x, hf_component_x, weights, omega)
    return {
        "s_tau": s_tau,
        "coverage": coverage,
        "omega": omega,
        "rho": rho,
        "weights": weights,
        "valid_mask": omega & np.isfinite(weights),
        "delta": delta,
        "reference_score": ref_score,
        "component_score": component_score,
        "n_valid": n_valid,
    }


def fit_hf_delta_fold(
    hf_reference_x: np.ndarray,
    hf_component_x: np.ndarray,
    y_hf_ref: np.ndarray,
    y_base: np.ndarray,
    scale_direction: str,
    s_tau: np.ndarray,
    heldout: int,
    min_coverage: int,
) -> dict[str, Any]:
    train = np.array([idx for idx in range(y_hf_ref.shape[0]) if idx != heldout], dtype=int)
    coverage_fold = coverage_from_suprathreshold(s_tau) - s_tau[heldout].astype(np.int32)
    omega_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
    if not np.any(omega_fold):
        raise RuntimeError(f"empty HF fold Omega for held-out index {heldout}")
    rho_fold = partial_spearman_matrix(y_hf_ref[train], hf_reference_x[train][:, omega_fold], y_base[train])
    weights_local = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
    weights_fold = np.full(hf_reference_x.shape[1], np.nan, dtype=np.float32)
    weights_fold[omega_fold] = weights_local
    delta, ref_score, component_score, n_valid = delta_hf_scores_from_map(
        hf_reference_x,
        hf_component_x,
        weights_fold,
        omega_fold,
    )
    return {
        "delta": delta,
        "reference_score": ref_score,
        "component_score": component_score,
        "n_valid": n_valid,
        "valid_mask": omega_fold & np.isfinite(weights_fold),
        "n_hf_score_voxels": int(np.count_nonzero(omega_fold & np.isfinite(weights_fold))),
    }


def compute_branch(
    *,
    branch_name: str,
    x_ulf_only: np.ndarray,
    coverage: np.ndarray,
    s_tau_ulf_only: np.ndarray,
    y_post: np.ndarray,
    y_hf_ref: np.ndarray,
    nuisance_full: np.ndarray | None,
    nuisance_fold_provider: Any,
    scale_direction: str,
    min_coverage: int,
    subject_ids: list[str],
) -> dict[str, Any]:
    """Compute one ULF observed branch with full-sample and LOOCV outputs."""
    omega = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(omega):
        raise RuntimeError(f"empty ULF Omega for branch {branch_name}")
    cov_full = y_hf_ref if nuisance_full is None else np.column_stack([y_hf_ref, nuisance_full])
    rho = np.full(x_ulf_only.shape[1], np.nan, dtype=np.float32)
    rho_omega = partial_spearman_matrix(y_post, x_ulf_only[:, omega], cov_full)
    rho[omega] = rho_omega.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid_full = omega & np.isfinite(weights)
    full_scores, n_valid_full = mean_map_score(x_ulf_only, weights, valid_full)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_ids):
        row = {
            "subject_id": subject_id,
            "Y_post": y_post[idx],
            "Y_HF_ref": y_hf_ref[idx],
            "ULFScore_mean_main": full_scores[idx],
            "exposure_sum_valid_voxels": float(np.sum(x_ulf_only[idx, valid_full], dtype=np.float64)),
            "n_valid_score_voxels": n_valid_full,
            "score_map_source": "full_sample",
            "is_primary_score": True,
        }
        if nuisance_full is not None:
            row["DeltaHFScore"] = float(nuisance_full[idx])
        score_rows.append(row)

    n_subjects = y_post.shape[0]
    stability_positive = np.zeros(x_ulf_only.shape[1], dtype=np.int16)
    stability_valid = np.zeros(x_ulf_only.shape[1], dtype=np.int16)
    loocv_pred = np.full(n_subjects, np.nan, dtype=float)
    loocv_base_pred = np.full(n_subjects, np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    support_rows: list[dict[str, Any]] = []
    fold_valid_score_voxels: list[int] = []
    ulfscore_nonconstant_all_folds = True

    for heldout in range(n_subjects):
        train = np.array([idx for idx in range(n_subjects) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau_ulf_only[heldout].astype(np.int32)
        omega_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(omega_fold):
            raise RuntimeError(f"empty ULF fold Omega for held-out {subject_ids[heldout]}")
        nuisance_fold_result = nuisance_fold_provider(heldout) if nuisance_fold_provider is not None else None
        nuisance_fold = nuisance_fold_result
        support_payload: dict[str, Any] | None = None
        if isinstance(nuisance_fold_result, dict):
            nuisance_fold = nuisance_fold_result["delta"]
            support_payload = nuisance_fold_result.get("support_row")
        cov_train = y_hf_ref[train] if nuisance_fold is None else np.column_stack([y_hf_ref[train], nuisance_fold[train]])
        cov_test = y_hf_ref[[heldout]] if nuisance_fold is None else np.column_stack([y_hf_ref[[heldout]], nuisance_fold[[heldout]]])
        rho_fold = partial_spearman_matrix(y_post[train], x_ulf_only[train][:, omega_fold], cov_train)
        weights_fold_local = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        weights_fold = np.full(x_ulf_only.shape[1], np.nan, dtype=np.float32)
        weights_fold[omega_fold] = weights_fold_local
        valid_fold = omega_fold & np.isfinite(weights_fold)
        if not np.any(valid_fold):
            raise RuntimeError(f"no valid ULF scoring voxels for held-out {subject_ids[heldout]}")
        stability_valid[valid_fold] += 1
        stability_positive[valid_fold & (weights_fold > 0)] += 1
        fold_scores, n_valid_fold = mean_map_score(x_ulf_only, weights_fold, valid_fold)
        fold_valid_score_voxels.append(int(n_valid_fold))
        if np.nanstd(fold_scores[train]) == 0:
            ulfscore_nonconstant_all_folds = False
        pred, beta = fit_linear_prediction(
            y_post[train],
            fold_scores[train],
            cov_train,
            fold_scores[[heldout]],
            cov_test,
        )
        base_pred, base_beta = fit_baseline_with_covariates(y_post[train], cov_train, cov_test)
        loocv_pred[heldout] = pred[0]
        loocv_base_pred[heldout] = base_pred[0]
        row = {
            "fold_id": heldout + 1,
            "heldout_subject_id": subject_ids[heldout],
            "Y_post": y_post[heldout],
            "Y_HF_ref": y_hf_ref[heldout],
            "ULFScore_LOOCV": fold_scores[heldout],
            "prediction_ULFScore_model": pred[0],
            "prediction_baseline_only": base_pred[0],
            "residual_ULFScore_model": y_post[heldout] - pred[0],
            "residual_baseline_only": y_post[heldout] - base_pred[0],
            "n_train": len(train),
            "n_valid_score_voxels": n_valid_fold,
            "delta_ULFScore": beta[1],
            "beta_Y_HF_ref": beta[2],
            "baseline_beta_Y_HF_ref": base_beta[1],
        }
        if nuisance_fold is not None:
            row["DeltaHFScore_LOOCV"] = float(nuisance_fold[heldout])
            row["gamma_DeltaHFScore"] = float(beta[3])
            row["baseline_gamma_DeltaHFScore"] = float(base_beta[2])
            if support_payload is not None:
                support_rows.append(support_payload)
            else:
                support_rows.append(
                    {
                        "fold_id": heldout + 1,
                        "subject_id": subject_ids[heldout],
                        "DeltaHFScore_in_support": float(nuisance_fold[heldout]),
                    }
                )
        fold_rows.append(row)

    metrics = regression_metrics(y_post, loocv_pred, loocv_base_pred)
    stability = np.full(x_ulf_only.shape[1], np.nan, dtype=np.float32)
    nonzero_valid = stability_valid > 0
    stability[nonzero_valid] = stability_positive[nonzero_valid] / n_subjects
    fold_valid_array = np.asarray(fold_valid_score_voxels, dtype=float)
    return {
        "branch_name": branch_name,
        "omega": omega,
        "rho": rho,
        "weights": weights,
        "coverage": coverage,
        "stability": stability,
        "score_rows": score_rows,
        "fold_rows": fold_rows,
        "support_rows": support_rows,
        "metrics": metrics,
        "n_valid_full_score_voxels": int(n_valid_full),
        "fold_n_valid_score_voxels_min": int(np.nanmin(fold_valid_array)) if fold_valid_array.size else 0,
        "fold_n_valid_score_voxels_median": float(np.nanmedian(fold_valid_array)) if fold_valid_array.size else 0.0,
        "fold_n_valid_score_voxels_max": int(np.nanmax(fold_valid_array)) if fold_valid_array.size else 0,
        "ulfscore_nonconstant_all_folds": bool(ulfscore_nonconstant_all_folds),
        "all_predictions_finite": bool(np.all(np.isfinite(loocv_pred)) and np.all(np.isfinite(loocv_base_pred))),
        "n_omega_voxels": int(np.count_nonzero(omega)),
    }


def ulf_direct_hard_computability_passes(row: dict[str, Any]) -> bool:
    return (
        float(row.get("n_subjects", 0) or 0) >= 12
        and float(row.get("n_voxels_full", 0) or 0) >= 20
        and float(row.get("fold_n_voxels_min", 0) or 0) >= 10
        and _as_bool(row.get("ulfscore_nonconstant_all_folds"))
        and str(row.get("branch_nuisance_design_status", "")) == "valid"
        and _as_bool(row.get("all_predictions_finite"))
    )


def ulf_direct_scan_empty_row(
    *,
    branch: str,
    tau: int,
    coverage: int,
    n_subjects: int,
    branch_role: str,
    branch_nuisance_design_status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "branch": branch,
        "branch_role": branch_role,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": n_subjects,
        "n_voxels_full": 0,
        "fold_n_voxels_min": 0,
        "fold_n_voxels_median": 0,
        "fold_n_voxels_max": 0,
        "branch_nuisance_design_status": branch_nuisance_design_status,
        "ulfscore_nonconstant_all_folds": False,
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
        "ulf_voxel_prediction_status": "not_applicable",
        "failure_reason": reason,
    }


def evaluate_ulf_direct_grid_cell(
    *,
    branch: str,
    branch_role: str,
    x_ulf_only: np.ndarray,
    coverage_array: np.ndarray,
    s_tau_ulf_only: np.ndarray,
    y_post: np.ndarray,
    y_hf_ref: np.ndarray,
    nuisance_full: np.ndarray | None,
    nuisance_fold_provider: Any,
    scale_direction: str,
    subject_ids: list[str],
    tau: int,
    coverage: int,
) -> dict[str, Any]:
    design_status = branch_nuisance_design_status(y_hf_ref=y_hf_ref, delta_hfscore=nuisance_full)
    if design_status != "valid":
        return ulf_direct_scan_empty_row(
            branch=branch,
            tau=tau,
            coverage=coverage,
            n_subjects=int(y_post.shape[0]),
            branch_role=branch_role,
            branch_nuisance_design_status=design_status,
            reason=design_status,
        )
    try:
        result = compute_branch(
            branch_name=f"tau{tau}/partial_spearman_{branch}",
            x_ulf_only=x_ulf_only,
            coverage=coverage_array,
            s_tau_ulf_only=s_tau_ulf_only,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            nuisance_full=nuisance_full,
            nuisance_fold_provider=nuisance_fold_provider,
            scale_direction=scale_direction,
            min_coverage=coverage,
            subject_ids=subject_ids,
        )
    except Exception as exc:
        return ulf_direct_scan_empty_row(
            branch=branch,
            tau=tau,
            coverage=coverage,
            n_subjects=int(y_post.shape[0]),
            branch_role=branch_role,
            branch_nuisance_design_status=design_status,
            reason=str(exc),
        )
    metrics = result["metrics"]
    y_true = np.array([row["Y_post"] for row in result["fold_rows"]], dtype=float)
    pred = np.array([row["prediction_ULFScore_model"] for row in result["fold_rows"]], dtype=float)
    pred_base = np.array([row["prediction_baseline_only"] for row in result["fold_rows"]], dtype=float)
    rho, rho_p = safe_spearman(y_true, pred)
    pearson, pearson_p = safe_pearson(y_true, pred)
    residual_model = y_true - pred
    residual_base = y_true - pred_base
    row = {
        "branch": branch,
        "branch_role": branch_role,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": int(y_post.shape[0]),
        "n_voxels_full": int(result["n_valid_full_score_voxels"]),
        "fold_n_voxels_min": int(result["fold_n_valid_score_voxels_min"]),
        "fold_n_voxels_median": float(result["fold_n_valid_score_voxels_median"]),
        "fold_n_voxels_max": int(result["fold_n_valid_score_voxels_max"]),
        "branch_nuisance_design_status": design_status,
        "ulfscore_nonconstant_all_folds": bool(result["ulfscore_nonconstant_all_folds"]),
        "all_predictions_finite": bool(result["all_predictions_finite"]),
        "loocv_spearman_rho": rho,
        "loocv_spearman_nominal_p": rho_p,
        "loocv_pearson_r": pearson,
        "loocv_pearson_nominal_p": pearson_p,
        "q2": metrics.get("q2", math.nan),
        "mae_model": float(np.mean(np.abs(residual_model))),
        "mae_baseline": float(np.mean(np.abs(residual_base))),
        "rmse_model": float(np.sqrt(np.mean(residual_model * residual_model))),
        "rmse_baseline": float(np.sqrt(np.mean(residual_base * residual_base))),
        "failure_reason": "",
    }
    row["passes_all_hard_filters"] = ulf_direct_hard_computability_passes(row)
    row["ulf_voxel_prediction_status"] = (
        classify_prediction_status(row) if row["passes_all_hard_filters"] else "not_applicable"
    )
    return row


def resolve_ulf_direct_branch(
    rows: list[dict[str, Any]],
    *,
    primary_tau: float = ULF_DIRECT_PRIMARY_TAU,
    primary_coverage: int = ULF_DIRECT_PRIMARY_COVERAGE,
    tau_grid: list[float] | tuple[float, ...] = tuple(ULF_DIRECT_TAU_GRID),
    coverage_grid: list[int] | tuple[int, ...] = tuple(ULF_DIRECT_COVERAGE_GRID),
) -> dict[str, Any]:
    resolved = resolve_hf_source(
        rows,
        primary_tau=primary_tau,
        primary_coverage=primary_coverage,
        tau_grid=list(tau_grid),
        coverage_grid=list(coverage_grid),
        pass_predicate=ulf_direct_hard_computability_passes,
    )
    return {
        "ulf_voxel_source_status": resolved["source_status"],
        "ulf_voxel_prediction_status": resolved["prediction_status"],
        "ulf_voxel_threshold_source": resolved["threshold_source"],
        "ulf_voxel_selected_tau_v_per_m": resolved["selected_tau"],
        "ulf_voxel_selected_coverage": resolved["selected_coverage"],
        "ulf_voxel_selected_adjacent_passing_grid_cells": resolved["selected_adjacent_passing_grid_cells"],
        "ulf_voxel_source_failure_reasons": resolved["source_failure_reasons"],
    }


def ulf_endpoint_status_for_primary(primary_resolution: dict[str, Any]) -> str:
    source_status = primary_resolution.get("ulf_voxel_source_status", "")
    prediction_status = primary_resolution.get("ulf_voxel_prediction_status", "")
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"} and prediction_status == "error_predictive":
        return "primary_branch_error_predictive"
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"} and prediction_status == "error_nonpredictive":
        return "primary_branch_error_nonpredictive"
    if source_status == "absent_no_stable_grid":
        return "absent_no_stable_ulf_grid"
    return "primary_branch_input_failure"


def write_ulf_direct_source_scan_outputs(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]],
    branch_resolutions: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scan_csv = output_dir / "direct_voxel_ULF_only_tau_coverage_source_resolver_scan.csv"
    manifest_json = output_dir / "direct_voxel_ULF_only_tau_coverage_source_resolver_manifest.json"
    fieldnames = [
        "branch",
        "branch_role",
        "tau",
        "coverage",
        "n_subjects",
        "n_voxels_full",
        "fold_n_voxels_min",
        "fold_n_voxels_median",
        "fold_n_voxels_max",
        "branch_nuisance_design_status",
        "ulfscore_nonconstant_all_folds",
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
        "ulf_voxel_prediction_status",
        "failure_reason",
    ]
    write_csv(scan_csv, rows, fieldnames)
    write_json(
        manifest_json,
        {
            **manifest,
            "branch_resolutions": branch_resolutions,
            "n_grid_rows": len(rows),
            "n_passing_grid_rows": int(sum(ulf_direct_hard_computability_passes(row) for row in rows)),
            "outputs": {"scan_csv": str(scan_csv), "manifest_json": str(manifest_json)},
        },
    )
    return {"scan_csv": str(scan_csv), "manifest_json": str(manifest_json)}


def write_branch_outputs(
    branch_dir: Path,
    ref_img: nib.Nifti1Image,
    candidate_flat: np.ndarray,
    branch: dict[str, Any],
    qc_common: dict[str, Any],
    manifest_common: dict[str, Any],
) -> None:
    branch_dir.mkdir(parents=True, exist_ok=True)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_coverage.nii.gz", ref_img, candidate_flat, branch["coverage"], np.int16, 0)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_coef.nii.gz", ref_img, candidate_flat, branch["rho"], np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_sweet_sour.nii.gz", ref_img, candidate_flat, branch["weights"], np.float32, np.nan)
    write_nifti_from_flat(branch_dir / "direct_voxel_ULF_only_stability.nii.gz", ref_img, candidate_flat, branch["stability"], np.float32, np.nan)
    score_fields = [
        "subject_id",
        "Y_post",
        "Y_HF_ref",
        "DeltaHFScore",
        "ULFScore_mean_main",
        "exposure_sum_valid_voxels",
        "n_valid_score_voxels",
        "score_map_source",
        "is_primary_score",
    ]
    fold_fields = [
        "fold_id",
        "heldout_subject_id",
        "Y_post",
        "Y_HF_ref",
        "DeltaHFScore_LOOCV",
        "ULFScore_LOOCV",
        "prediction_ULFScore_model",
        "prediction_baseline_only",
        "residual_ULFScore_model",
        "residual_baseline_only",
        "n_train",
        "n_valid_score_voxels",
        "delta_ULFScore",
        "beta_Y_HF_ref",
        "gamma_DeltaHFScore",
        "baseline_beta_Y_HF_ref",
        "baseline_gamma_DeltaHFScore",
    ]
    write_csv(branch_dir / "direct_voxel_ULF_only_scores.csv", branch["score_rows"], score_fields)
    write_csv(branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv", branch["fold_rows"], fold_fields)
    if branch["support_rows"]:
        write_csv(
            branch_dir / "direct_voxel_ULF_only_delta_hf_support_summary.csv",
            branch["support_rows"],
            [
                "subject_id",
                "endpoint",
                "phase",
                "tau",
                "score_map_source",
                "fold_id",
                "n_hf_score_voxels",
                "HF_in_support_sum",
                "HF_total_sum",
                "HF_out_support_sum",
                "HF_out_support_fraction",
                "HF_out_support_volume_tau",
                "HF_out_support_top5",
                "DeltaHFScore_in_support",
                "DeltaHFScore_source_branch",
            ],
        )
    qc = dict(qc_common)
    qc.update(
        {
            "branch": branch["branch_name"],
            "n_omega_voxels": branch["n_omega_voxels"],
            "n_valid_full_score_voxels": branch["n_valid_full_score_voxels"],
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
                "scores_csv": str(branch_dir / "direct_voxel_ULF_only_scores.csv"),
                "loocv_predictions_csv": str(branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv"),
                "mapping_qc_json": str(branch_dir / "direct_voxel_ULF_only_mapping_qc.json"),
                "generation_manifest_json": str(branch_dir / "direct_voxel_ULF_only_generation_manifest.json"),
            },
        }
    )
    write_json(branch_dir / "direct_voxel_ULF_only_mapping_qc.json", qc)
    write_json(branch_dir / "direct_voxel_ULF_only_generation_manifest.json", manifest)


def _read_configured_clinical_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"unsupported configured clinical table format: {path}")


def load_configured_ulf_records(config: ConfiguredULFDirectVoxelRun) -> list[ULFRecord]:
    """Load exactly the configured endpoint and preserve its immutable subject order."""
    raw_df = _read_configured_clinical_table(config.clinical_table)
    post_rows = raw_df[
        raw_df["Scale"].astype(str).eq(config.scale_label)
        & raw_df["Protocol"].astype(str).eq(config.outcome_protocol)
        & raw_df["Phase"].astype(str).eq(config.outcome_phase)
    ].copy()
    hf_rows = raw_df[
        raw_df["Scale"].astype(str).eq(config.scale_label)
        & raw_df["Protocol"].astype(str).eq(config.hf_reference_protocol)
        & raw_df["Phase"].astype(str).eq(config.hf_reference_phase)
    ].copy()
    if post_rows["ID"].astype(str).duplicated().any() or hf_rows["ID"].astype(str).duplicated().any():
        raise RuntimeError("configured ULF endpoint contains duplicate subject rows")
    merged = post_rows[["ID", "Value", "Baseline"]].rename(
        columns={"Value": "Y_post", "Baseline": "Y_base"}
    ).merge(
        hf_rows[["ID", "Value"]].rename(columns={"Value": "Y_HF_ref"}),
        on="ID",
        how="inner",
        validate="one_to_one",
    )
    merged["ID"] = merged["ID"].astype(str)
    by_subject = merged.set_index("ID")
    missing = [subject for subject in config.subject_order if subject not in by_subject.index]
    if missing:
        raise RuntimeError("configured ULF endpoint is missing subjects: " + ", ".join(missing))
    records: list[ULFRecord] = []
    for subject in config.subject_order:
        row = by_subject.loc[subject]
        values = (row["Y_post"], row["Y_HF_ref"], row["Y_base"])
        if not all(np.isfinite(float(value)) for value in values):
            raise RuntimeError(f"configured ULF endpoint has nonfinite clinical data for {subject}")
        records.append(ULFRecord(subject, float(values[0]), float(values[1]), float(values[2])))
    return records


def _configured_component_exposure(
    config: ConfiguredULFDirectVoxelRun,
    records: list[ULFRecord],
    availability: pd.DataFrame,
    frequency_class: str,
    xyz: np.ndarray,
    *,
    flip_backend: Any,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    side_paths, path_qc = component_side_paths(availability, records, frequency_class)
    nonempty_left = {key: value for key, value in side_paths.items() if key[1] == "L" and value}
    if nonempty_left:
        flipped, flip_qc = flip_backend(
            repo_root=config.asset_root,
            matlab_bin=config.matlab_bin,
            side_paths=nonempty_left,
            preprocess_dir=config.model_cache_root / "preprocess" / frequency_class.lower(),
            force=False,
        )
    else:
        flipped = {}
        flip_qc = {"status": "SKIPPED", "detail": f"no left {frequency_class} fields", "n_jobs": 0}
    exposure, sampling_qc = build_component_exposure_matrix(records, side_paths, flipped, xyz)
    return exposure, path_qc + sampling_qc, flip_qc


def build_configured_hf_component_exposure_on_axis(
    *,
    subject_order: tuple[str, ...],
    outcome_protocol: str,
    outcome_phase: str,
    readiness_csv: Path,
    brainmask: Path,
    asset_root: Path,
    matlab_bin: Path,
    candidate_flat: np.ndarray,
    sidecar_root: Path,
    flip_backend: Any = flip_left_fields_with_matlab,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Sample add-on HF-component fields on the immutable HF feature axis."""
    flat = np.asarray(candidate_flat, dtype=np.int64)
    if flat.ndim != 1 or flat.size == 0:
        raise ValueError("configured HF feature axis must be a nonempty one-dimensional array")
    if len(np.unique(flat)) != flat.size:
        raise ValueError("configured HF feature axis contains duplicate flat voxel IDs")
    reference = nib.load(str(brainmask))
    mask = np.asarray(reference.dataobj) > 0
    if np.any(flat < 0) or np.any(flat >= int(np.prod(reference.shape))):
        raise ValueError("configured HF feature axis contains out-of-range flat voxel IDs")
    ijk = np.column_stack(np.unravel_index(flat, reference.shape)).astype(np.int32)
    if not np.all(mask[tuple(ijk.T)]):
        raise ValueError("configured HF feature axis contains voxels outside the configured brainmask")
    xyz = nib.affines.apply_affine(reference.affine, ijk).astype(np.float32)
    if not np.all(xyz[:, 0] > 0):
        raise ValueError("configured HF feature axis is not entirely in right-canonical space")

    availability = load_component_availability(readiness_csv)
    availability = availability[
        availability["protocol"].astype(str).eq(outcome_protocol)
        & availability["phase"].astype(str).eq(outcome_phase)
    ].copy()
    records = [ULFRecord(subject, 0.0, 0.0, 0.0) for subject in subject_order]
    side_paths, path_qc = component_side_paths(availability, records, "HF")
    nonempty_left = {key: value for key, value in side_paths.items() if key[1] == "L" and value}
    if nonempty_left:
        flipped, flip_qc = flip_backend(
            repo_root=asset_root,
            matlab_bin=matlab_bin,
            side_paths=nonempty_left,
            preprocess_dir=sidecar_root / "hf_component_left_to_right",
            force=False,
        )
    else:
        flipped = {}
        flip_qc = {"status": "SKIPPED", "detail": "no left HF component fields", "n_jobs": 0}
    exposure, sampling_qc = build_component_exposure_matrix(records, side_paths, flipped, xyz)
    return exposure.astype(np.float32), {
        "subject_order": list(subject_order),
        "outcome_protocol": outcome_protocol,
        "outcome_phase": outcome_phase,
        "readiness_csv": str(readiness_csv),
        "brainmask": str(brainmask),
        "feature_count": int(flat.size),
        "path_qc": path_qc,
        "sampling_qc": sampling_qc,
        "flip_qc": flip_qc,
    }


def _load_configured_delta(
    config: ConfiguredULFDirectVoxelRun,
) -> tuple[np.ndarray | None, np.ndarray | None, pd.DataFrame | None]:
    if config.branch == "no_delta_hf":
        return None, None, None
    assert config.delta_full_scores is not None
    assert config.delta_fold_scores is not None
    assert config.delta_support_rows is not None
    full = np.asarray(np.load(config.delta_full_scores), dtype=float)
    folds = np.asarray(np.load(config.delta_fold_scores), dtype=float)
    expected_n = len(config.subject_order)
    if full.shape != (expected_n,):
        raise RuntimeError(f"DeltaHF full-score shape must be {(expected_n,)}, got {full.shape}")
    if folds.shape != (expected_n, expected_n):
        raise RuntimeError(
            f"DeltaHF fold-by-subject shape must be {(expected_n, expected_n)}, got {folds.shape}"
        )
    if not np.all(np.isfinite(full)) or not np.all(np.isfinite(folds)):
        raise RuntimeError("DeltaHF full and fold-by-subject scores must be finite")
    support = pd.read_csv(config.delta_support_rows)
    if "subject_id" not in support.columns:
        raise RuntimeError("DeltaHF support rows must include subject_id")
    support_subjects = tuple(support["subject_id"].astype(str))
    if support_subjects != config.subject_order:
        raise RuntimeError("DeltaHF support-row subject order does not match the configured endpoint")
    return full, folds, support


def run_configured_ulf_direct_voxel(
    config: ConfiguredULFDirectVoxelRun,
    *,
    flip_backend: Any = flip_left_fields_with_matlab,
) -> dict[str, Any]:
    """Run one endpoint/branch source resolver from explicit configured inputs."""
    records = load_configured_ulf_records(config)
    subject_ids = [record.subject_id for record in records]
    y_post = np.asarray([record.y_post for record in records], dtype=float)
    y_hf_ref = np.asarray([record.y_hf_ref for record in records], dtype=float)
    config.model_cache_root.mkdir(parents=True, exist_ok=True)
    config.output_root.mkdir(parents=True, exist_ok=True)

    availability = load_component_availability(config.readiness_csv)
    availability = availability[
        availability["protocol"].astype(str).eq(config.outcome_protocol)
        & availability["phase"].astype(str).eq(config.outcome_phase)
    ].copy()
    if availability.empty:
        raise RuntimeError(
            f"no component e-fields found for {config.outcome_protocol} {config.outcome_phase}"
        )
    ref_img, right_ijk, right_xyz, right_flat = right_brainmask_voxels_from_path(config.brainmask)
    ulf_component_all, ulf_qc, ulf_flip = _configured_component_exposure(
        config,
        records,
        availability,
        "ULF",
        right_xyz,
        flip_backend=flip_backend,
    )
    if math.isfinite(config.hf_overlap_tau):
        hf_component_all, hf_qc, hf_flip = _configured_component_exposure(
            config,
            records,
            availability,
            "HF",
            right_xyz,
            flip_backend=flip_backend,
        )
    else:
        hf_component_all = np.zeros_like(ulf_component_all)
        hf_qc = []
        hf_flip = {"status": "SKIPPED", "detail": "HF source absent; overlap exclusion disabled"}

    candidate_threshold = float(min(config.tau_grid))
    candidate_sparse = np.any(ulf_component_all > candidate_threshold, axis=0)
    if not np.any(candidate_sparse):
        raise RuntimeError("empty configured ULF sparse candidate mask")
    candidate_flat = right_flat[candidate_sparse]
    candidate_ijk = right_ijk[candidate_sparse]
    ulf_component = ulf_component_all[:, candidate_sparse].astype(np.float32)
    hf_component = hf_component_all[:, candidate_sparse].astype(np.float32)
    feature_ids_path = config.model_cache_root / "candidate_flat_indices.npy"
    np.save(feature_ids_path, candidate_flat)
    np.save(config.model_cache_root / "candidate_ijk.npy", candidate_ijk)

    delta_full, delta_folds, delta_support = _load_configured_delta(config)

    def fold_delta_provider(heldout: int) -> dict[str, Any] | None:
        if delta_folds is None or delta_support is None:
            return None
        support_row = delta_support.iloc[heldout].to_dict()
        support_row["fold_id"] = heldout + 1
        support_row["DeltaHFScore_in_support"] = float(delta_folds[heldout, heldout])
        return {"delta": delta_folds[heldout], "support_row": support_row}

    rows: list[dict[str, Any]] = []
    for tau in config.tau_grid:
        ulf_active = ulf_component > float(tau)
        hf_active = (
            np.zeros_like(hf_component, dtype=bool)
            if math.isinf(config.hf_overlap_tau)
            else hf_component > float(config.hf_overlap_tau)
        )
        x_ulf_only = np.where(ulf_active & ~hf_active, ulf_component, 0.0).astype(np.float32)
        s_tau = suprathreshold_matrix(x_ulf_only, float(tau))
        coverage_array = coverage_from_suprathreshold(s_tau)
        for coverage in config.coverage_grid:
            rows.append(
                evaluate_ulf_direct_grid_cell(
                    branch=config.branch,
                    branch_role="resolver_candidate",
                    x_ulf_only=x_ulf_only,
                    coverage_array=coverage_array,
                    s_tau_ulf_only=s_tau,
                    y_post=y_post,
                    y_hf_ref=y_hf_ref,
                    nuisance_full=delta_full,
                    nuisance_fold_provider=(fold_delta_provider if delta_full is not None else None),
                    scale_direction=config.direction,
                    subject_ids=subject_ids,
                    tau=float(tau),
                    coverage=int(coverage),
                )
            )
    resolution = resolve_ulf_direct_branch(
        rows,
        primary_tau=config.primary_tau,
        primary_coverage=config.primary_coverage,
        tau_grid=config.tau_grid,
        coverage_grid=config.coverage_grid,
    )
    scan_outputs = write_ulf_direct_source_scan_outputs(
        config.output_root / "source_scan",
        rows=rows,
        branch_resolutions={config.branch: resolution},
        manifest={
            "generated_at": iso_now(),
            "analysis": "configured_ulf_direct_voxel_source_resolver",
            "endpoint_id": config.endpoint_id,
            "scale_label": config.scale_label,
            "outcome_protocol": config.outcome_protocol,
            "outcome_phase": config.outcome_phase,
            "subject_order": subject_ids,
            "branch": config.branch,
            "nuisance_columns": list(config.nuisance_columns),
            "tau_grid_v_per_m": list(config.tau_grid),
            "coverage_grid": list(config.coverage_grid),
            "pre_specified_tau_v_per_m": config.primary_tau,
            "pre_specified_coverage": config.primary_coverage,
            "candidate_sparse_threshold_v_per_m": candidate_threshold,
            "hf_overlap_tau_v_per_m": (
                config.hf_overlap_tau if math.isfinite(config.hf_overlap_tau) else "+Inf"
            ),
            "delta_hf_tau_v_per_m": config.delta_hf_tau,
            "delta_hf_coverage": config.delta_hf_coverage,
            "ulf_component_qc": ulf_qc,
            "hf_component_qc": hf_qc,
            "ulf_flip_qc": ulf_flip,
            "hf_flip_qc": hf_flip,
            "input_paths": {
                "clinical_table": str(config.clinical_table),
                "stimulation_table": str(config.stimulation_table),
                "derivatives_root": str(config.derivatives_root),
                "brainmask": str(config.brainmask),
                "readiness_csv": str(config.readiness_csv),
            },
        },
    )
    artifact_paths = {
        "source_scan": scan_outputs["scan_csv"],
        "source_scan_manifest": scan_outputs["manifest_json"],
    }
    selected_tau = resolution.get("ulf_voxel_selected_tau_v_per_m")
    selected_coverage = resolution.get("ulf_voxel_selected_coverage")
    realized_branch_name = config.branch_name
    if selected_tau is not None and selected_coverage is not None:
        selected_tau = float(selected_tau)
        selected_coverage = int(selected_coverage)
        realized_branch_name = ulf_direct_branch_name(config.branch, selected_tau, selected_coverage)
        ulf_active = ulf_component > selected_tau
        hf_active = (
            np.zeros_like(hf_component, dtype=bool)
            if math.isinf(config.hf_overlap_tau)
            else hf_component > float(config.hf_overlap_tau)
        )
        x_selected = np.where(ulf_active & ~hf_active, ulf_component, 0.0).astype(np.float32)
        s_selected = suprathreshold_matrix(x_selected, selected_tau)
        selected_result = compute_branch(
            branch_name=realized_branch_name,
            x_ulf_only=x_selected,
            coverage=coverage_from_suprathreshold(s_selected),
            s_tau_ulf_only=s_selected,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            nuisance_full=delta_full,
            nuisance_fold_provider=(fold_delta_provider if delta_full is not None else None),
            scale_direction=config.direction,
            min_coverage=selected_coverage,
            subject_ids=subject_ids,
        )
        branch_dir = config.output_root / realized_branch_name
        write_branch_outputs(
            branch_dir,
            ref_img,
            candidate_flat,
            selected_result,
            {
                "model": "ULF direct voxel",
                "endpoint_id": config.endpoint_id,
                "branch": config.branch,
                "tau_v_per_m": selected_tau,
                "min_coverage": selected_coverage,
                "hf_overlap_tau_v_per_m": (
                    config.hf_overlap_tau if math.isfinite(config.hf_overlap_tau) else "+Inf"
                ),
            },
            {
                "generated_at": iso_now(),
                "model": "ULF direct voxel",
                "endpoint_id": config.endpoint_id,
                "branch": config.branch,
                "scale_direction": config.direction,
                "subject_order": subject_ids,
                "nuisance_columns": list(config.nuisance_columns),
            },
        )
        exposure_path = branch_dir / "X_ULF_only_float32_subject_major.npy"
        np.save(exposure_path, x_selected)
        artifact_paths.update(
            {
                "observed_metrics": str(branch_dir / "direct_voxel_ULF_only_mapping_qc.json"),
                "loocv_predictions": str(
                    branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv"
                ),
                "selected_manifest": str(
                    branch_dir / "direct_voxel_ULF_only_generation_manifest.json"
                ),
                "selected_scores": str(branch_dir / "direct_voxel_ULF_only_scores.csv"),
                "exposure_matrix": str(exposure_path),
                "coefficient_nifti": str(
                    branch_dir / "direct_voxel_ULF_only_sweet_sour.nii.gz"
                ),
            }
        )
    return {
        "branch": config.branch,
        "branch_name": realized_branch_name,
        "source_resolution": {
            "source_status": resolution["ulf_voxel_source_status"],
            "prediction_status": resolution["ulf_voxel_prediction_status"],
            "threshold_source": resolution["ulf_voxel_threshold_source"],
            "selected_tau": selected_tau,
            "selected_coverage": selected_coverage,
            "selected_adjacent_passing_grid_cells": resolution[
                "ulf_voxel_selected_adjacent_passing_grid_cells"
            ],
        },
        "subject_ids": subject_ids,
        "feature_ids_path": str(feature_ids_path),
        "feature_count": int(candidate_flat.size),
        "artifact_paths": artifact_paths,
    }


def run_ulf_direct_voxel_observed(args: argparse.Namespace) -> int:
    started = time.time()
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    derivatives_root = Path(args.leaddbs_derivatives).expanduser().resolve()
    matlab_bin = Path(args.matlab_bin).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    readiness_csv = resolve_readiness_csv(Path(args.readiness_root).expanduser().resolve(), args.readiness_csv)
    gate_status_path = Path(args.gate_status).expanduser().resolve()

    post_scale = args.post_scale
    scale_slug = slugify(post_scale)
    output_scale_root = output_root / scale_slug
    preprocess_dir = output_scale_root / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)

    records, hf_ref_scale = load_ulf_records(clinical_root, post_scale)
    gate_status = read_a_direct_voxel_dependency(output_root, hf_ref_scale, gate_status_path)
    locked_hf_overlap_tau = hf_overlap_tau_from_dependency(gate_status, args.hf_tau)
    subject_ids = [record.subject_id for record in records]
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_hf_ref = np.array([record.y_hf_ref for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    scale_direction, scale_direction_source = infer_scale_direction(post_scale)
    if scale_direction not in {"lower", "higher"}:
        raise RuntimeError(f"unknown scale direction for {post_scale!r}; provide explicit direction before running")

    availability = load_component_availability(readiness_csv)
    component_protocol = "STN+SNr"
    component_phase = parse_endpoint_scale(post_scale)[2]
    availability = availability[
        availability["protocol"].astype(str).eq(component_protocol)
        & availability["phase"].astype(str).eq(component_phase)
    ].copy()
    if availability.empty:
        raise RuntimeError(f"no component e-fields found for {component_protocol} {component_phase}")

    ref_img, right_ijk, right_xyz, right_flat = right_brainmask_voxels(asset_root)
    hf_paths, hf_path_qc = component_side_paths(availability, records, "HF")
    ulf_paths, ulf_path_qc = component_side_paths(availability, records, "ULF")
    hf_flipped, hf_flip_result = flip_component_left_fields(asset_root, matlab_bin, hf_paths, preprocess_dir, "hf", args.force_flip)
    ulf_flipped, ulf_flip_result = flip_component_left_fields(asset_root, matlab_bin, ulf_paths, preprocess_dir, "ulf", args.force_flip)
    hf_component_all, hf_component_sampling_qc = build_component_exposure_matrix(records, hf_paths, hf_flipped, right_xyz)
    ulf_component_all, ulf_sampling_qc = build_component_exposure_matrix(records, ulf_paths, ulf_flipped, right_xyz)
    hf_reference_all, hf_reference_qc, hf_reference_flip = build_hf_reference_exposure(
        records,
        clinical_root,
        derivatives_root,
        asset_root,
        matlab_bin,
        preprocess_dir,
        args.force_flip,
        right_xyz,
    )

    ulf_candidate_sparse = np.any(ulf_component_all > args.candidate_threshold, axis=0)
    if not np.any(ulf_candidate_sparse):
        raise RuntimeError("empty ULF sparse candidate mask")
    ulf_candidate_flat = right_flat[ulf_candidate_sparse]
    ulf_candidate_ijk = right_ijk[ulf_candidate_sparse]
    ulf_candidate_xyz = right_xyz[ulf_candidate_sparse]
    hf_component_x = hf_component_all[:, ulf_candidate_sparse].astype(np.float32)
    ulf_component_x = ulf_component_all[:, ulf_candidate_sparse].astype(np.float32)
    ulf_active = ulf_component_x > args.tau
    hf_active_for_overlap = np.zeros_like(hf_component_x, dtype=bool) if math.isinf(locked_hf_overlap_tau) else hf_component_x > locked_hf_overlap_tau
    x_ulf_only = np.where(ulf_active & ~hf_active_for_overlap, ulf_component_x, 0.0).astype(np.float32)
    s_tau_ulf_only = suprathreshold_matrix(x_ulf_only, args.tau)
    ulf_coverage = coverage_from_suprathreshold(s_tau_ulf_only)

    hf_candidate_sparse = np.any(hf_reference_all > args.candidate_threshold, axis=0)
    if not np.any(hf_candidate_sparse):
        raise RuntimeError("empty HF reference sparse candidate mask for DeltaHFScore")
    hf_reference_x = hf_reference_all[:, hf_candidate_sparse].astype(np.float32)
    hf_component_for_delta_x = hf_component_all[:, hf_candidate_sparse].astype(np.float32)
    voxel_volume_mm3 = float(abs(np.linalg.det(ref_img.affine[:3, :3])))
    hf_delta_full = fit_hf_delta_full(
        hf_reference_x,
        hf_component_for_delta_x,
        y_hf_ref,
        y_base,
        scale_direction,
        args.hf_tau,
        args.hf_min_coverage,
    )

    def fold_delta_provider(heldout: int) -> np.ndarray:
        fold = fit_hf_delta_fold(
            hf_reference_x,
            hf_component_for_delta_x,
            y_hf_ref,
            y_base,
            scale_direction,
            hf_delta_full["s_tau"],
            heldout,
            args.hf_min_coverage,
        )
        support_row = hf_support_summary_for_subject(
            subject_id=subject_ids[heldout],
            endpoint=post_scale,
            phase=component_phase,
            tau=args.hf_tau,
            score_map_source="loocv_training_fold",
            fold_id=heldout + 1,
            hf_component_full=hf_component_all[heldout],
            hf_candidate_sparse=hf_candidate_sparse,
            valid_candidate_mask=fold["valid_mask"],
            delta_hf_score=float(fold["delta"][heldout]),
            n_hf_score_voxels=int(fold["n_hf_score_voxels"]),
            voxel_volume_mm3=voxel_volume_mm3,
        )
        return {"delta": np.asarray(fold["delta"], dtype=float), "support_row": support_row}

    np.save(preprocess_dir / "E_HF_component_float32_subject_major.npy", hf_component_x)
    np.save(preprocess_dir / "E_ULF_component_float32_subject_major.npy", ulf_component_x)
    np.save(preprocess_dir / "candidate_flat_indices.npy", ulf_candidate_flat)
    np.save(preprocess_dir / "candidate_ijk.npy", ulf_candidate_ijk)
    np.save(preprocess_dir / "candidate_xyz.npy", ulf_candidate_xyz)
    write_csv(preprocess_dir / "subjects.csv", [asdict(record) for record in records], ["subject_id", "y_post", "y_hf_ref", "y_base"])

    if args.source_resolver_scan:
        rows: list[dict[str, Any]] = []
        branch_resolutions: dict[str, dict[str, Any]] = {}
        branch_specs: list[tuple[str, str, np.ndarray | None, Any]] = [
            (
                "no_delta_hf",
                "primary" if gate_status["ulf_primary_branch"] == "no_delta_hf" else "sensitivity",
                None,
                None,
            )
        ]
        if gate_status.get("hf_voxel_source_status") in {"pre_specified_accepted", "scan_fallback_accepted"}:
            branch_specs.append(
                (
                    "delta_hf_adjusted",
                    "primary" if gate_status["ulf_primary_branch"] == "delta_hf_adjusted" else "sensitivity",
                    np.asarray(hf_delta_full["delta"], dtype=float),
                    fold_delta_provider,
                )
            )
        for tau in ULF_DIRECT_TAU_GRID:
            ulf_active_tau = ulf_component_x > float(tau)
            hf_active_tau = (
                np.zeros_like(hf_component_x, dtype=bool)
                if math.isinf(locked_hf_overlap_tau)
                else hf_component_x > locked_hf_overlap_tau
            )
            x_ulf_only_tau = np.where(ulf_active_tau & ~hf_active_tau, ulf_component_x, 0.0).astype(np.float32)
            s_tau = suprathreshold_matrix(x_ulf_only_tau, tau)
            coverage_tau = coverage_from_suprathreshold(s_tau)
            for branch_name, branch_role, nuisance_full, nuisance_provider in branch_specs:
                for coverage_min in ULF_DIRECT_COVERAGE_GRID:
                    print(
                        f"[{scale_slug}/{branch_name}] Evaluating tau={tau} V/m, Coverage>={coverage_min}",
                        flush=True,
                    )
                    rows.append(
                        evaluate_ulf_direct_grid_cell(
                            branch=branch_name,
                            branch_role=branch_role,
                            x_ulf_only=x_ulf_only_tau,
                            coverage_array=coverage_tau,
                            s_tau_ulf_only=s_tau,
                            y_post=y_post,
                            y_hf_ref=y_hf_ref,
                            nuisance_full=nuisance_full,
                            nuisance_fold_provider=nuisance_provider,
                            scale_direction=scale_direction,
                            subject_ids=subject_ids,
                            tau=tau,
                            coverage=coverage_min,
                        )
                    )
        for branch_name, _, _, _ in branch_specs:
            branch_rows = [row for row in rows if row["branch"] == branch_name]
            branch_resolutions[branch_name] = resolve_ulf_direct_branch(branch_rows)
        intended_primary_branch = gate_status["ulf_primary_branch"]
        primary_resolution = branch_resolutions.get(intended_primary_branch, {})
        endpoint_status = ulf_endpoint_status_for_primary(primary_resolution) if primary_resolution else "primary_branch_input_failure"
        scan_dir = output_scale_root / "tau_coverage_source_resolver_scan"
        outputs = write_ulf_direct_source_scan_outputs(
            scan_dir,
            rows=rows,
            branch_resolutions=branch_resolutions,
            manifest={
                "generated_at": iso_now(),
                "analysis": "ulf_direct_voxel_tau_coverage_source_resolver_scan",
                "model": "ULF direct voxel",
                "post_scale": post_scale,
                "hf_reference_scale": hf_ref_scale,
                "scale_slug": scale_slug,
                "scale_direction": scale_direction,
                "scale_direction_source": scale_direction_source,
                "candidate_sparse_threshold_v_per_m": args.candidate_threshold,
                "tau_grid_v_per_m": ULF_DIRECT_TAU_GRID,
                "coverage_grid": ULF_DIRECT_COVERAGE_GRID,
                "pre_specified_tau_v_per_m": ULF_DIRECT_PRIMARY_TAU,
                "pre_specified_coverage": ULF_DIRECT_PRIMARY_COVERAGE,
                "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
                "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
                "hf_voxel_source_status": gate_status.get("hf_voxel_source_status", ""),
                "hf_voxel_prediction_status": gate_status.get("hf_voxel_prediction_status", ""),
                "hf_voxel_threshold_source": gate_status.get("hf_voxel_threshold_source", ""),
                "hf_voxel_selected_tau_v_per_m": gate_status.get("hf_voxel_selected_tau_v_per_m", ""),
                "hf_voxel_selected_coverage": gate_status.get("hf_voxel_selected_coverage", ""),
                "intended_primary_branch": intended_primary_branch,
                "ulf_primary_branch": intended_primary_branch,
                "delta_hfscore_role": gate_status["delta_hfscore_role"],
                "ulf_endpoint_model_status": endpoint_status,
                "runtime_s": time.time() - started,
            },
        )
        print(f"ULF direct voxel source resolver output: {scan_dir}")
        print(json.dumps({"branch_resolutions": branch_resolutions, "ulf_endpoint_model_status": endpoint_status}, indent=2, sort_keys=True))
        print(f"Scan CSV: {outputs['scan_csv']}")
        return 0

    no_delta_branch = compute_branch(
        branch_name="tau200/partial_spearman_no_delta_hf",
        x_ulf_only=x_ulf_only,
        coverage=ulf_coverage,
        s_tau_ulf_only=s_tau_ulf_only,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=None,
        nuisance_fold_provider=None,
        scale_direction=scale_direction,
        min_coverage=args.min_coverage,
        subject_ids=subject_ids,
    )
    delta_branch = compute_branch(
        branch_name="tau200/partial_spearman_delta_hf_adjusted",
        x_ulf_only=x_ulf_only,
        coverage=ulf_coverage,
        s_tau_ulf_only=s_tau_ulf_only,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=np.asarray(hf_delta_full["delta"], dtype=float),
        nuisance_fold_provider=fold_delta_provider,
        scale_direction=scale_direction,
        min_coverage=args.min_coverage,
        subject_ids=subject_ids,
    )

    np.save(preprocess_dir / "X_ULF_only_float32_subject_major.npy", x_ulf_only)
    write_json(
        preprocess_dir / "direct_voxel_ULF_only_preprocess_qc.json",
        {
            "generated_at": iso_now(),
            "post_scale": post_scale,
            "hf_reference_scale": hf_ref_scale,
            "scale_direction": scale_direction,
            "scale_direction_source": scale_direction_source,
            "n_subjects": len(records),
            "right_brainmask_voxels": int(right_flat.size),
            "candidate_threshold_v_per_m": args.candidate_threshold,
            "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
            "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
            "n_ulf_candidate_voxels": int(ulf_candidate_flat.size),
            "n_hf_delta_candidate_voxels": int(np.count_nonzero(hf_candidate_sparse)),
            "n_ulf_only_nonzero_subjects": int(np.count_nonzero(np.sum(x_ulf_only, axis=1) > 0)),
            "component_readiness_csv": str(readiness_csv),
            "component_hf_paths": hf_path_qc,
            "component_ulf_paths": ulf_path_qc,
            "component_hf_flip": hf_flip_result,
            "component_ulf_flip": ulf_flip_result,
            "hf_reference_flip": hf_reference_flip,
            "component_hf_sampling_qc": hf_component_sampling_qc,
            "component_ulf_sampling_qc": ulf_sampling_qc,
            "hf_reference_qc": hf_reference_qc,
        },
    )

    qc_common = {
        "model": "ULF direct voxel",
        "post_scale": post_scale,
        "hf_reference_scale": hf_ref_scale,
        "scale_slug": scale_slug,
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "n_subjects": len(records),
        "tau_v_per_m": args.tau,
        "candidate_threshold_v_per_m": args.candidate_threshold,
        "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
        "hf_overlap_rule": "locked_hf_selected_tau" if math.isfinite(locked_hf_overlap_tau) else "no_hf_source_no_overlap_exclusion",
        "min_coverage": args.min_coverage,
        "n_candidate_voxels": int(ulf_candidate_flat.size),
        "n_ulf_only_nonzero_subjects": int(np.count_nonzero(np.sum(x_ulf_only, axis=1) > 0)),
        "hf_delta_n_valid_full_score_voxels": int(hf_delta_full["n_valid"]),
    }
    manifest_common = {
        "generated_at": iso_now(),
        "model": "ULF direct voxel",
        "repo_root": str(repo_root),
        "asset_root": str(asset_root),
        "clinical_root": str(clinical_root),
        "derivatives_root": str(derivatives_root),
        "readiness_csv": str(readiness_csv),
        "output_root": str(output_scale_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        },
        "parameters": {
            "post_scale": post_scale,
            "hf_reference_scale": hf_ref_scale,
            "tau_v_per_m": args.tau,
            "candidate_threshold_v_per_m": args.candidate_threshold,
            "min_coverage": args.min_coverage,
            "hf_tau_v_per_m": args.hf_tau,
            "hf_overlap_tau_v_per_m": locked_hf_overlap_tau if math.isfinite(locked_hf_overlap_tau) else "+Inf",
            "hf_min_coverage": args.hf_min_coverage,
            "random_seed": 42,
        },
        "hf_prediction_validity_status": gate_status["hf_prediction_validity_status"],
        "hf_voxel_source_status": gate_status.get("hf_voxel_source_status", ""),
        "hf_voxel_prediction_status": gate_status.get("hf_voxel_prediction_status", ""),
        "hf_voxel_threshold_source": gate_status.get("hf_voxel_threshold_source", ""),
        "hf_voxel_selected_tau_v_per_m": gate_status.get("hf_voxel_selected_tau_v_per_m", ""),
        "hf_voxel_selected_coverage": gate_status.get("hf_voxel_selected_coverage", ""),
        "hf_gate_decision": gate_status["gate_decision"],
        "ulf_primary_branch": gate_status["ulf_primary_branch"],
        "ulf_core_branches_run": [
            "tau200/partial_spearman_no_delta_hf",
            "tau200/partial_spearman_delta_hf_adjusted",
        ],
        "delta_hfscore_role": gate_status["delta_hfscore_role"],
        "branch_role_decision_reason": "Resolved from current A gate status; no-DeltaHF remains interpretation-primary unless matched HF is predictive_valid.",
        "hf_model_support_status": "fold_local_hf_map_used_for_delta_hfscore",
        "resampling_status": "not_run_observed_only",
        "runtime_profile": {
            "total_s": None,
            "preprocess_s": None,
            "observed_loocv_s": None,
            "permutation_s": None,
            "bootstrap_s": None,
            "jitter_s": None,
        },
    }
    branch_root = output_scale_root / f"tau{int(args.tau)}"
    write_branch_outputs(
        branch_root / "partial_spearman_no_delta_hf",
        ref_img,
        ulf_candidate_flat,
        no_delta_branch,
        qc_common,
        {**manifest_common, "runtime_profile": {**manifest_common["runtime_profile"], "total_s": time.time() - started}},
    )
    write_branch_outputs(
        branch_root / "partial_spearman_delta_hf_adjusted",
        ref_img,
        ulf_candidate_flat,
        delta_branch,
        qc_common,
        {**manifest_common, "runtime_profile": {**manifest_common["runtime_profile"], "total_s": time.time() - started}},
    )
    print(f"ULF direct voxel observed output: {branch_root}")
    print(
        "No-DeltaHF LOOCV Spearman rho: "
        f"{no_delta_branch['metrics']['spearman_rho']:.6g}; Q2: {no_delta_branch['metrics']['q2']:.6g}"
    )
    print(
        "DeltaHF-adjusted LOOCV Spearman rho: "
        f"{delta_branch['metrics']['spearman_rho']:.6g}; Q2: {delta_branch['metrics']['q2']:.6g}"
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default=str(DEFAULT_CANONICAL_ASSET_ROOT), help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--readiness-root", default=str(DEFAULT_READINESS_ROOT), help="ULF component readiness run root.")
    parser.add_argument("--readiness-csv", default="", help="Explicit ULF component e-field availability CSV.")
    parser.add_argument("--gate-status", default=str(DEFAULT_GATE_STATUS), help="A/B gate status CSV.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="ULF direct voxel output root.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--post-scale", default=DEFAULT_POST_SCALE, help="Raw STN+SNr post endpoint.")
    parser.add_argument("--tau", type=float, default=200.0, help="ULF activity and coverage threshold in V/m.")
    parser.add_argument("--candidate-threshold", type=float, default=ULF_DIRECT_CANDIDATE_THRESHOLD, help="Sparse ULF candidate threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Minimum ULF-only subject coverage.")
    parser.add_argument("--hf-tau", type=float, default=200.0, help="Matched HF map threshold in V/m for DeltaHFScore.")
    parser.add_argument("--hf-min-coverage", type=int, default=5, help="Matched HF map minimum coverage for DeltaHFScore.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    parser.add_argument("--source-resolver-scan", action="store_true", help="Run the ULF direct voxel tau/Coverage source resolver scan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_ulf_direct_voxel_observed(args)


if __name__ == "__main__":
    raise SystemExit(main())
