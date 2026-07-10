#!/usr/bin/env python3
"""Spatial jitter QC for final STN/SNr direct-voxel models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from stnsnr_direct_voxel_formal_permutation import (
    FORMAL_DIRECT_MODEL_IDS,
    DirectVoxelTarget,
    _float_column,
    direct_voxel_loocv_statistic,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    load_subject_table,
    write_csv,
    write_json,
)
from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import (
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    partial_spearman_matrix,
    suprathreshold_matrix,
)
from stnsnr_hf_direct_voxel_smoke import sample_image_at_xyz
from stnsnr_run_provenance import git_provenance


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _subject_ids(subjects_csv: Path) -> list[str]:
    table = load_subject_table(subjects_csv)
    if "subject_id" not in table:
        raise KeyError(f"missing subject_id column in {subjects_csv}")
    return [str(value) for value in table["subject_id"]]


def _qc_rows_by_subject(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("subject_id", "")): row for row in rows}


def _paths_from_qc(row: dict[str, Any], key: str) -> list[Path]:
    out: list[Path] = []
    for item in row.get(key, []) or []:
        path_text = item.get("path", "") if isinstance(item, dict) else ""
        if path_text:
            out.append(Path(path_text))
    return out


def _sample_paths_with_shift(paths: list[Path], xyz: np.ndarray, shift_mm: np.ndarray) -> np.ndarray:
    if not paths:
        return np.zeros(xyz.shape[0], dtype=np.float32)
    shifted_xyz = np.asarray(xyz, dtype=np.float32) - np.asarray(shift_mm, dtype=np.float32).reshape(1, 3)
    values = np.zeros(xyz.shape[0], dtype=np.float32)
    for path in paths:
        sampled, _ = sample_image_at_xyz(path, shifted_xyz)
        values = np.maximum(values, sampled.astype(np.float32))
    return values


def _jitter_vector(rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    return rng.normal(loc=0.0, scale=float(sigma_mm), size=3).astype(np.float32)


def _build_hf_jitter_matrix(qc: dict[str, Any], subject_ids: list[str], xyz: np.ndarray, rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    rows_by_subject = _qc_rows_by_subject(qc.get("sampling_qc", []))
    x = np.zeros((len(subject_ids), xyz.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        row = rows_by_subject.get(subject_id)
        if row is None:
            raise KeyError(f"missing HF sampling QC row for {subject_id}")
        right = _sample_paths_with_shift(_paths_from_qc(row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        left = _sample_paths_with_shift(_paths_from_qc(row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        x[row_idx] = (right + left) / 2.0
    return x


def _build_ulf_jitter_matrix(
    qc: dict[str, Any],
    subject_ids: list[str],
    xyz: np.ndarray,
    rng: np.random.Generator,
    sigma_mm: float,
    *,
    tau: float,
) -> np.ndarray:
    hf_rows = _qc_rows_by_subject(qc.get("component_hf_sampling_qc", []))
    ulf_rows = _qc_rows_by_subject(qc.get("component_ulf_sampling_qc", []))
    try:
        hf_overlap_tau = float(qc.get("hf_overlap_tau_v_per_m", tau))
    except (TypeError, ValueError):
        hf_overlap_tau = float(tau)
    x = np.zeros((len(subject_ids), xyz.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        hf_row = hf_rows.get(subject_id, {})
        ulf_row = ulf_rows.get(subject_id, {})
        hf_right = _sample_paths_with_shift(_paths_from_qc(hf_row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        hf_left = _sample_paths_with_shift(_paths_from_qc(hf_row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        ulf_right = _sample_paths_with_shift(_paths_from_qc(ulf_row, "right"), xyz, _jitter_vector(rng, sigma_mm))
        ulf_left = _sample_paths_with_shift(_paths_from_qc(ulf_row, "left_to_right"), xyz, _jitter_vector(rng, sigma_mm))
        hf_component = (hf_right + hf_left) / 2.0
        ulf_component = (ulf_right + ulf_left) / 2.0
        hf_active = np.zeros_like(hf_component, dtype=bool) if math.isinf(hf_overlap_tau) else hf_component > hf_overlap_tau
        ulf_active = ulf_component > float(tau)
        x[row_idx] = np.where(ulf_active & ~hf_active, ulf_component, 0.0).astype(np.float32)
    return x


def _full_weights(
    *,
    x: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
) -> tuple[np.ndarray, np.ndarray]:
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    omega = candidate_mask_from_coverage(coverage, min_coverage)
    weights = np.full(x.shape[1], np.nan, dtype=np.float32)
    if not np.any(omega):
        return weights, omega
    rho = partial_spearman_matrix(y_post, x[:, omega], nuisance)
    weights[omega] = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid = omega & np.isfinite(weights)
    return weights, valid


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(finite) < 2:
        return float("nan")
    xx = x[finite] - np.mean(x[finite])
    yy = y[finite] - np.mean(y[finite])
    denom = float(np.sqrt(np.sum(xx * xx) * np.sum(yy * yy)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(xx * yy) / denom)


def _support_overlap(observed_valid: np.ndarray, jitter_valid: np.ndarray, observed_weights: np.ndarray, jitter_weights: np.ndarray) -> dict[str, Any]:
    intersection = observed_valid & jitter_valid
    union = observed_valid | jitter_valid
    if np.any(intersection):
        sign_consistency = float(np.mean(np.sign(observed_weights[intersection]) == np.sign(jitter_weights[intersection])))
    else:
        sign_consistency = float("nan")
    return {
        "support_intersection_voxels": int(np.count_nonzero(intersection)),
        "support_union_voxels": int(np.count_nonzero(union)),
        "valid_support_jaccard": float(np.count_nonzero(intersection) / np.count_nonzero(union)) if np.any(union) else float("nan"),
        "sign_consistency_fraction": sign_consistency,
    }


def _new_streaming_spatial_qc(
    observed_weights: np.ndarray,
    observed_valid: np.ndarray,
) -> dict[str, np.ndarray]:
    weights = np.asarray(observed_weights, dtype=np.float32)
    valid = np.asarray(observed_valid, dtype=bool)
    if weights.ndim != 1 or valid.shape != weights.shape:
        raise ValueError("observed spatial weights and support must be aligned vectors")
    valid = valid & np.isfinite(weights)
    return {
        "observed_weights": weights,
        "observed_valid": valid,
        "mean": np.zeros(weights.shape, dtype=np.float64),
        "m2": np.zeros(weights.shape, dtype=np.float64),
        "finite_count": np.zeros(weights.shape, dtype=np.uint32),
    }


def _update_streaming_spatial_qc(
    state: dict[str, np.ndarray],
    jitter_weights: np.ndarray,
    jitter_valid: np.ndarray,
) -> dict[str, Any]:
    weights = np.asarray(jitter_weights, dtype=np.float32)
    valid = np.asarray(jitter_valid, dtype=bool)
    observed_weights = state["observed_weights"]
    observed_valid = state["observed_valid"]
    if weights.shape != observed_weights.shape or valid.shape != weights.shape:
        raise ValueError("jitter spatial weights and support must match the final feature axis")
    valid = valid & np.isfinite(weights)
    finite_count = state["finite_count"]
    if np.any(valid):
        values = weights[valid].astype(np.float64)
        finite_count[valid] += 1
        delta = values - state["mean"][valid]
        state["mean"][valid] += delta / finite_count[valid]
        delta2 = values - state["mean"][valid]
        state["m2"][valid] += delta * delta2

    intersection = observed_valid & valid
    union = observed_valid | valid
    observed_map = np.where(observed_valid, observed_weights, np.nan)
    jitter_map = np.where(valid, weights, np.nan)
    return {
        "spatial_qc_status": "complete",
        "spatial_failure": "",
        "map_pearson_r": _pearson(observed_map, jitter_map),
        "n_finite_map_features": int(np.count_nonzero(valid)),
        "support_intersection_features": int(np.count_nonzero(intersection)),
        "support_union_features": int(np.count_nonzero(union)),
        "valid_support_jaccard": (
            float(np.count_nonzero(intersection) / np.count_nonzero(union))
            if np.any(union)
            else float("nan")
        ),
        "sign_consistency_fraction": (
            float(
                np.mean(
                    np.sign(observed_weights[intersection])
                    == np.sign(weights[intersection])
                )
            )
            if np.any(intersection)
            else float("nan")
        ),
    }


def _missing_spatial_qc(reason: str) -> dict[str, Any]:
    return {
        "spatial_qc_status": "not_computable",
        "spatial_failure": reason,
        "map_pearson_r": np.nan,
        "n_finite_map_features": 0,
        "support_intersection_features": 0,
        "support_union_features": 0,
        "valid_support_jaccard": np.nan,
        "sign_consistency_fraction": np.nan,
    }


def _write_npy_atomic(path: Path, values: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, values, allow_pickle=False)
    temporary.replace(path)
    return path


_CONFIGURED_JITTER_CHECKPOINT_SCHEMA = "stnsnr_configured_jitter_checkpoint_v1"
_CONFIGURED_JITTER_METHOD_VERSION = "full_process_spatial_jitter_v2"
_CONFIGURED_JITTER_CHECKPOINT_INTERVAL = 10


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configured_jitter_checkpoint_identity(
    target: Any,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float,
    seed: int,
) -> tuple[dict[str, Any], str]:
    input_manifest = getattr(target, "jitter_input_manifest_path", None)
    input_manifest_hash = None
    if input_manifest is not None:
        input_manifest_path = Path(input_manifest).expanduser().resolve()
        if not input_manifest_path.is_file():
            raise FileNotFoundError(
                f"configured jitter input manifest is missing: {input_manifest_path}"
            )
        input_manifest_hash = _sha256_file(input_manifest_path)
    identity = {
        "schema_version": _CONFIGURED_JITTER_CHECKPOINT_SCHEMA,
        "method_version": _CONFIGURED_JITTER_METHOD_VERSION,
        "model_family": str(target.model_family),
        "final_model_id": str(target.final_model_id),
        "final_record_hash": str(target.final_record_hash),
        "final_branch": str(target.final_branch),
        "selected_tau": float(target.selected_tau),
        "selected_coverage": int(target.selected_coverage),
        "seed": int(seed),
        "jitter_fwhm_mm": float(jitter_fwhm_mm),
        "requested_replicates": int(n_jitters),
        "jitter_input_manifest_sha256": input_manifest_hash,
    }
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return identity, key


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"unsupported checkpoint value {type(value).__name__}")


def _save_configured_jitter_checkpoint(
    path: Path,
    *,
    identity: dict[str, Any],
    rows: list[dict[str, Any]],
    spatial_state: dict[str, np.ndarray],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    identity_bytes = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    rows_bytes = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    with temporary.open("wb") as handle:
        np.savez_compressed(
            handle,
            identity_json=np.frombuffer(identity_bytes, dtype=np.uint8),
            rows_json=np.frombuffer(rows_bytes, dtype=np.uint8),
            next_index=np.asarray([len(rows)], dtype=np.int64),
            mean=np.asarray(spatial_state["mean"], dtype=np.float64),
            m2=np.asarray(spatial_state["m2"], dtype=np.float64),
            finite_count=np.asarray(spatial_state["finite_count"], dtype=np.uint32),
        )
    temporary.replace(path)


def _load_configured_jitter_checkpoint(
    path: Path,
    *,
    identity: dict[str, Any],
    spatial_state: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        with np.load(path, allow_pickle=False) as checkpoint:
            observed_identity = json.loads(
                np.asarray(checkpoint["identity_json"], dtype=np.uint8).tobytes().decode("utf-8")
            )
            rows = json.loads(
                np.asarray(checkpoint["rows_json"], dtype=np.uint8).tobytes().decode("utf-8")
            )
            next_index = int(np.asarray(checkpoint["next_index"], dtype=np.int64).reshape(-1)[0])
            mean = np.asarray(checkpoint["mean"], dtype=np.float64)
            m2 = np.asarray(checkpoint["m2"], dtype=np.float64)
            finite_count = np.asarray(checkpoint["finite_count"], dtype=np.uint32)
    except (KeyError, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return []
    if observed_identity != identity or not isinstance(rows, list) or next_index != len(rows):
        return []
    if next_index > int(identity["requested_replicates"]):
        return []
    if [row.get("jitter_index") for row in rows if isinstance(row, dict)] != list(
        range(1, next_index + 1)
    ):
        return []
    expected_shape = spatial_state["mean"].shape
    if mean.shape != expected_shape or m2.shape != expected_shape or finite_count.shape != expected_shape:
        return []
    spatial_state["mean"][:] = mean
    spatial_state["m2"][:] = m2
    spatial_state["finite_count"][:] = finite_count
    return [dict(row) for row in rows]


def _finite_summary(rows: list[dict[str, Any]], key: str, statistic: str) -> float:
    values = np.asarray([row.get(key, np.nan) for row in rows], dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")
    if statistic == "median":
        return float(np.median(finite))
    if statistic == "minimum":
        return float(np.min(finite))
    raise ValueError(f"unsupported spatial summary statistic: {statistic}")


def _finalize_streaming_spatial_qc(
    state: dict[str, np.ndarray],
    rows: list[dict[str, Any]],
    *,
    output_root: Path,
    artifact_prefix: str,
    feature_unit: str,
    requested_replicates: int,
) -> dict[str, Any]:
    count = state["finite_count"]
    mean = np.full(count.shape, np.nan, dtype=np.float32)
    has_value = count > 0
    mean[has_value] = state["mean"][has_value].astype(np.float32)
    sd = np.full(count.shape, np.nan, dtype=np.float32)
    has_sd = count > 1
    sd[has_sd] = np.sqrt(
        state["m2"][has_sd] / (count[has_sd].astype(np.float64) - 1.0)
    ).astype(np.float32)

    observed_path = _write_npy_atomic(
        output_root / f"{artifact_prefix}_observed_final_weights.npy",
        state["observed_weights"],
    )
    mean_path = _write_npy_atomic(
        output_root / f"{artifact_prefix}_map_mean.npy",
        mean,
    )
    sd_path = _write_npy_atomic(
        output_root / f"{artifact_prefix}_map_sd.npy",
        sd,
    )
    count_path = _write_npy_atomic(
        output_root / f"{artifact_prefix}_map_finite_count.npy",
        count,
    )
    completed = sum(row.get("spatial_qc_status") == "complete" for row in rows)
    return {
        "status": (
            "complete"
            if completed == int(requested_replicates)
            else "partial"
            if completed > 0
            else "not_computable"
        ),
        "feature_unit": feature_unit,
        "requested_replicates": int(requested_replicates),
        "completed_replicates": int(completed),
        "observed_final_weights_source": "recomputed_from_immutable_final_inputs",
        "observed_final_weights_npy": str(observed_path),
        "n_observed_valid_features": int(
            np.count_nonzero(state["observed_valid"])
        ),
        "map_pearson_r_median": _finite_summary(rows, "map_pearson_r", "median"),
        "map_pearson_r_minimum": _finite_summary(rows, "map_pearson_r", "minimum"),
        "valid_support_jaccard_median": _finite_summary(
            rows,
            "valid_support_jaccard",
            "median",
        ),
        "valid_support_jaccard_minimum": _finite_summary(
            rows,
            "valid_support_jaccard",
            "minimum",
        ),
        "sign_consistency_fraction_median": _finite_summary(
            rows,
            "sign_consistency_fraction",
            "median",
        ),
        "sign_consistency_fraction_minimum": _finite_summary(
            rows,
            "sign_consistency_fraction",
            "minimum",
        ),
        "streaming_variability_method": "per-feature Welford mean and sample SD over finite supported weights",
        "streaming_memory_complexity": "O(n_features)",
        "map_variability_artifacts": {
            "mean_npy": str(mean_path),
            "sd_npy": str(sd_path),
            "finite_count_npy": str(count_path),
        },
    }


def _write_jitter_se_nifti(target: DirectVoxelTarget, prefix: str, se_values: np.ndarray) -> Path:
    flat_indices = np.asarray(np.load(target.x_path.parent / "candidate_flat_indices.npy"), dtype=np.int64)
    template = nib.load(str(target.branch_dir / f"{prefix}_coef.nii.gz"))
    if flat_indices.shape[0] != se_values.shape[0]:
        raise ValueError("candidate_flat_indices length must match jitter SE length")
    flat = np.full(int(np.prod(template.shape)), np.nan, dtype=np.float32)
    flat[flat_indices] = np.asarray(se_values, dtype=np.float32)
    image = nib.Nifti1Image(flat.reshape(template.shape), template.affine, template.header)
    output_path = target.branch_dir / f"{prefix}_jitter_se.nii.gz"
    nib.save(image, str(output_path))
    return output_path


def _jitter_matrix_for_target(target: DirectVoxelTarget, qc: dict[str, Any], subject_ids: list[str], xyz: np.ndarray, rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    if target.model_id == "A":
        return _build_hf_jitter_matrix(qc, subject_ids, xyz, rng, sigma_mm)
    if target.model_id == "C":
        return _build_ulf_jitter_matrix(qc, subject_ids, xyz, rng, sigma_mm, tau=target.tau)
    raise ValueError(f"unsupported direct-voxel jitter target: {target.model_id}")


def _configured_neighborhood_exposure(target: Any, tau: float) -> np.ndarray:
    if not str(target.model_family).startswith("ulf_"):
        return np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32)
    try:
        ulf_path = target.component_paths["ulf_component_exposure"]
    except KeyError as exc:
        raise ValueError(
            "ULF selected-source neighborhood requires raw ulf_component_exposure"
        ) from exc
    ulf = np.asarray(np.load(ulf_path, mmap_mode="r"), dtype=np.float32)
    if target.hf_overlap_tau is None:
        raise ValueError("ULF selected-source neighborhood requires hf_overlap_tau")
    if math.isinf(float(target.hf_overlap_tau)):
        hf_active = np.zeros_like(ulf, dtype=bool)
    else:
        try:
            hf_path = target.component_paths["hf_component_exposure"]
        except KeyError as exc:
            raise ValueError(
                "finite HF overlap requires raw hf_component_exposure"
            ) from exc
        hf = np.asarray(np.load(hf_path, mmap_mode="r"), dtype=np.float32)
        if hf.shape != ulf.shape:
            raise ValueError("HF and ULF raw component exposure shapes differ")
        hf_active = hf > float(target.hf_overlap_tau)
    return np.where((ulf > float(tau)) & ~hf_active, ulf, 0.0).astype(np.float32)


def _configured_outcome_and_nuisance(
    target: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    table = load_subject_table(target.scores_path)
    subject_column = next(
        (column for column in table if column.strip().lower() == "subject_id"),
        None,
    )
    if subject_column is None:
        raise KeyError("configured sensitivity scores are missing subject_id")
    if tuple(str(value) for value in table[subject_column]) != tuple(target.subject_order):
        raise ValueError("configured sensitivity score subject order mismatch")
    y_post = _float_column(table, "Y_post")
    baseline_column = "Y_base" if target.final_branch == "hf_source" else "Y_HF_ref"
    baseline = _float_column(table, baseline_column)[:, None]
    if target.final_branch != "delta_hf_adjusted":
        return y_post, baseline, None
    if target.delta_full_path is None or target.delta_fold_path is None:
        raise ValueError("adjusted neighborhood requires full and fold DeltaHF artifacts")
    full_delta = np.asarray(np.load(target.delta_full_path, mmap_mode="r"), dtype=float)
    fold_delta = np.asarray(np.load(target.delta_fold_path, mmap_mode="r"), dtype=float)
    n_subjects = len(target.subject_order)
    if full_delta.shape != (n_subjects,) or fold_delta.shape != (n_subjects, n_subjects):
        raise ValueError("adjusted neighborhood DeltaHF shape mismatch")
    nuisance = np.column_stack([baseline[:, 0], full_delta])
    fold_nuisance = np.concatenate(
        [np.broadcast_to(baseline, (n_subjects, *baseline.shape)), fold_delta[:, :, None]],
        axis=2,
    )
    return y_post, nuisance, fold_nuisance


def _configured_observed_weights(target: Any) -> tuple[np.ndarray, np.ndarray]:
    y_post, nuisance, _ = _configured_outcome_and_nuisance(target)
    return _full_weights(
        x=np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32),
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        tau=float(target.selected_tau),
        min_coverage=int(target.selected_coverage),
    )


def run_configured_neighborhood_sensitivity(
    target: Any,
    *,
    tau_multipliers: tuple[float, float],
) -> dict[str, Any]:
    """Run observed LOOCV at 0.9x and 1.1x of one selected source tau."""
    y_post, nuisance, fold_nuisance = _configured_outcome_and_nuisance(target)
    cells: list[dict[str, Any]] = []
    for multiplier in tau_multipliers:
        tau = float(target.selected_tau) * float(multiplier)
        try:
            exposure = _configured_neighborhood_exposure(target, tau)
            metrics = direct_voxel_loocv_statistic(
                x=exposure,
                y_post=y_post,
                nuisance=nuisance,
                fold_nuisance=fold_nuisance,
                scale_direction=target.scale_direction,
                tau=tau,
                min_coverage=int(target.selected_coverage),
            )
            cell = {
                "status": "complete",
                "tau_multiplier": float(multiplier),
                "tau_v_per_m": tau,
                "selected_coverage": int(target.selected_coverage),
                **metrics,
            }
        except (RuntimeError, ValueError) as exc:
            cell = {
                "status": "not_computable",
                "reason": str(exc),
                "tau_multiplier": float(multiplier),
                "tau_v_per_m": tau,
                "selected_coverage": int(target.selected_coverage),
            }
        cells.append(cell)
    summary_path = target.output_root / "direct_voxel_selected_source_neighborhood.csv"
    fields = sorted({key for cell in cells for key in cell})
    write_csv(summary_path, cells, fields)
    return {
        "status": "complete",
        "final_model_id": target.final_model_id,
        "final_record_hash": target.final_record_hash,
        "selected_tau": float(target.selected_tau),
        "selected_coverage": int(target.selected_coverage),
        "cells": cells,
        "summary_csv": str(summary_path),
        "classification_feedback": "none",
    }


def _manifest_artifact_path(manifest_path: Path, entry: Any, label: str) -> Path:
    if not isinstance(entry, dict):
        raise ValueError(f"jitter geometry requires {label} artifact metadata")
    path = Path(str(entry.get("path", ""))).expanduser()
    path = path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"jitter geometry {label} artifact is missing: {path}")
    expected_sha = str(entry.get("sha256", ""))
    if len(expected_sha) != 64:
        raise ValueError(f"jitter geometry {label} requires SHA-256 provenance")
    import hashlib

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected_sha:
        raise ValueError(f"jitter geometry {label} SHA-256 mismatch")
    return path


def _validated_sampling_rows(
    manifest_path: Path,
    rows: Any,
    subject_order: tuple[str, ...],
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"jitter geometry requires {label} sampling rows")
    by_subject: dict[str, dict[str, Any]] = {}
    validated: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError(f"jitter geometry {label} rows must be objects")
        subject_id = str(raw.get("subject_id", ""))
        if subject_id in by_subject:
            raise ValueError(f"duplicate {label} sampling row for {subject_id}")
        row: dict[str, Any] = {"subject_id": subject_id}
        for side in ("right", "left_to_right"):
            entries = raw.get(side, [])
            if not isinstance(entries, list):
                raise ValueError(f"{label} {side} entries must be a list")
            row[side] = [
                {
                    "path": str(
                        _manifest_artifact_path(
                            manifest_path,
                            entry,
                            f"{label}:{subject_id}:{side}",
                        )
                    )
                }
                for entry in entries
            ]
        by_subject[subject_id] = row
        validated.append(row)
    if tuple(by_subject) != tuple(subject_order):
        raise ValueError(f"jitter geometry {label} subject order mismatch")
    return validated


def _sample_component_rows(
    rows: list[dict[str, Any]],
    subject_order: tuple[str, ...],
    xyz: np.ndarray,
    shifts: dict[tuple[str, str], np.ndarray],
) -> np.ndarray:
    by_subject = _qc_rows_by_subject(rows)
    matrix = np.zeros((len(subject_order), xyz.shape[0]), dtype=np.float32)
    for index, subject_id in enumerate(subject_order):
        row = by_subject[subject_id]
        right = _sample_paths_with_shift(
            _paths_from_qc(row, "right"),
            xyz,
            shifts[(subject_id, "right")],
        )
        left = _sample_paths_with_shift(
            _paths_from_qc(row, "left_to_right"),
            xyz,
            shifts[(subject_id, "left_to_right")],
        )
        matrix[index] = (right + left) / 2.0
    return matrix


def _default_configured_geometry_builder(
    target: Any,
    rng: np.random.Generator,
    sigma_mm: float,
) -> dict[str, Any]:
    manifest = target.jitter_input_manifest
    if not isinstance(manifest, dict) or target.jitter_input_manifest_path is None:
        raise ValueError("configured jitter requires a validated jitter input manifest")
    geometry = manifest.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("builder") != "direct_efield_resample_v1":
        raise ValueError("jitter geometry requires builder='direct_efield_resample_v1'")
    manifest_path = Path(target.jitter_input_manifest_path)
    final_xyz_path = _manifest_artifact_path(
        manifest_path,
        geometry.get("final_candidate_xyz"),
        "final_candidate_xyz",
    )
    final_xyz = np.asarray(np.load(final_xyz_path, mmap_mode="r"), dtype=np.float32)
    if final_xyz.shape != (len(np.load(target.feature_ids_path, mmap_mode="r")), 3):
        raise ValueError("final jitter xyz does not match final feature order")

    def shifts() -> dict[tuple[str, str], np.ndarray]:
        return {
            (subject_id, side): _jitter_vector(rng, sigma_mm)
            for subject_id in target.subject_order
            for side in ("right", "left_to_right")
        }

    if target.model_family == "hf_voxel":
        rows = _validated_sampling_rows(
            manifest_path,
            geometry.get("hf_reference_sampling_qc"),
            target.subject_order,
            "hf_reference",
        )
        return {
            "final_exposure": _sample_component_rows(
                rows,
                target.subject_order,
                final_xyz,
                shifts(),
            )
        }

    hf_rows = _validated_sampling_rows(
        manifest_path,
        geometry.get("hf_component_sampling_qc"),
        target.subject_order,
        "hf_component",
    )
    ulf_rows = _validated_sampling_rows(
        manifest_path,
        geometry.get("ulf_component_sampling_qc"),
        target.subject_order,
        "ulf_component",
    )
    hf_shifts = shifts()
    ulf_shifts = shifts()
    result: dict[str, Any] = {
        "hf_component": _sample_component_rows(
            hf_rows,
            target.subject_order,
            final_xyz,
            hf_shifts,
        ),
        "ulf_component": _sample_component_rows(
            ulf_rows,
            target.subject_order,
            final_xyz,
            ulf_shifts,
        ),
    }
    if target.hf_overlap_tau is not None and not math.isinf(float(target.hf_overlap_tau)):
        matched_xyz_path = _manifest_artifact_path(
            manifest_path,
            geometry.get("matched_hf_candidate_xyz"),
            "matched_hf_candidate_xyz",
        )
        support_xyz_path = _manifest_artifact_path(
            manifest_path,
            geometry.get("hf_support_xyz"),
            "hf_support_xyz",
        )
        matched_indices_path = _manifest_artifact_path(
            manifest_path,
            geometry.get("matched_hf_candidate_indices_in_support"),
            "matched_hf_candidate_indices_in_support",
        )
        matched_xyz = np.asarray(np.load(matched_xyz_path, mmap_mode="r"), dtype=np.float32)
        support_xyz = np.asarray(np.load(support_xyz_path, mmap_mode="r"), dtype=np.float32)
        matched_indices = np.asarray(np.load(matched_indices_path, mmap_mode="r"), dtype=np.int64)
        hf_reference_rows = _validated_sampling_rows(
            manifest_path,
            geometry.get("hf_reference_sampling_qc"),
            target.subject_order,
            "hf_reference",
        )
        reference_shifts = shifts()
        result.update(
            {
                "hf_reference": _sample_component_rows(
                    hf_reference_rows,
                    target.subject_order,
                    matched_xyz,
                    reference_shifts,
                ),
                "hf_reprogrammed": _sample_component_rows(
                    hf_rows,
                    target.subject_order,
                    matched_xyz,
                    hf_shifts,
                ),
                "hf_reprogrammed_support": _sample_component_rows(
                    hf_rows,
                    target.subject_order,
                    support_xyz,
                    hf_shifts,
                ),
                "matched_hf_candidate_indices_in_support": matched_indices,
            }
        )
    return result


def _support_fraction(
    exposure: np.ndarray,
    support: np.ndarray,
    tau: float,
) -> tuple[np.ndarray, bool]:
    active = np.asarray(exposure) > float(tau)
    total = np.sum(active, axis=1)
    out = np.sum(active & ~np.asarray(support, dtype=bool)[None, :], axis=1)
    fractions = np.divide(
        out,
        total,
        out=np.ones(total.shape, dtype=float),
        where=total > 0,
    )
    return fractions, bool(np.any(total == 0))


def _support_category(subject_values: np.ndarray, fold_values: np.ndarray, any_zero: bool) -> str:
    if any_zero:
        return "invalid_no_hfcomponent_total_exposure"
    if (
        float(np.median(subject_values)) > 0.50
        or float(np.mean(subject_values > 0.80)) > 0.25
        or float(max(np.max(subject_values), np.max(fold_values))) > 0.95
    ):
        return "invalid_extreme_out_of_support"
    if (
        float(np.median(subject_values)) <= 0.20
        and float(np.mean(subject_values > 0.50)) <= 0.25
    ):
        return "adequate"
    return "limited"


def _default_configured_delta_builder(target: Any, geometry: dict[str, Any]) -> dict[str, Any]:
    if target.matched_hf_final is None:
        raise ValueError("ULF jitter with finite HF overlap requires matched_hf_final")
    required = {
        "hf_reference",
        "hf_reprogrammed",
        "hf_reprogrammed_support",
        "matched_hf_candidate_indices_in_support",
    }
    missing = sorted(required - set(geometry))
    if missing:
        raise ValueError("ULF jitter geometry is missing DeltaHF inputs: " + ",".join(missing))
    if target.y_base_path is None:
        raise ValueError("ULF jitter DeltaHF rebuild requires Y_base")
    from stnsnr_ulf_direct_voxel_observed import fit_hf_delta_fold, fit_hf_delta_full

    table = load_subject_table(target.scores_path)
    y_hf_ref = _float_column(table, "Y_HF_ref")
    y_base = np.asarray(np.load(target.y_base_path, mmap_mode="r"), dtype=float)
    hf_tau = float(target.matched_hf_final.selected_tau)
    hf_coverage = int(target.matched_hf_final.selected_coverage)
    reference = np.asarray(geometry["hf_reference"], dtype=np.float32)
    component = np.asarray(geometry["hf_reprogrammed"], dtype=np.float32)
    component_support = np.asarray(geometry["hf_reprogrammed_support"], dtype=np.float32)
    indices = np.asarray(geometry["matched_hf_candidate_indices_in_support"], dtype=np.int64)
    full = fit_hf_delta_full(
        reference,
        component,
        y_hf_ref,
        y_base,
        target.scale_direction,
        hf_tau,
        hf_coverage,
    )
    support_full = np.zeros(component_support.shape[1], dtype=bool)
    support_full[indices[np.asarray(full["valid_mask"], dtype=bool)]] = True
    subject_fractions, any_zero = _support_fraction(
        component_support,
        support_full,
        hf_tau,
    )
    n_subjects = len(target.subject_order)
    fold_scores = np.full((n_subjects, n_subjects), np.nan, dtype=float)
    fold_out = np.full((n_subjects, n_subjects), np.nan, dtype=float)
    for heldout in range(n_subjects):
        fold = fit_hf_delta_fold(
            reference,
            component,
            y_hf_ref,
            y_base,
            target.scale_direction,
            full["s_tau"],
            heldout,
            hf_coverage,
        )
        fold_scores[heldout] = fold["delta"]
        fold_support = np.zeros(component_support.shape[1], dtype=bool)
        fold_support[indices[np.asarray(fold["valid_mask"], dtype=bool)]] = True
        fractions, fold_zero = _support_fraction(
            component_support,
            fold_support,
            hf_tau,
        )
        fold_out[heldout] = fractions
        any_zero = any_zero or fold_zero
    category = _support_category(subject_fractions, fold_out, any_zero)
    return {
        "status": category,
        "full_scores": np.asarray(full["delta"], dtype=float),
        "fold_scores": fold_scores,
        "support": {
            "median_out_support_fraction": float(np.median(subject_fractions)),
            "maximum_out_support_fraction": float(max(np.max(subject_fractions), np.max(fold_out))),
            "invalid_extreme_threshold": 0.95,
            "fold_subject_fraction_shape": list(fold_out.shape),
            "n_fold_subject_pairs_evaluated": int(fold_out.size),
            "n_extreme_fold_subject_pairs": int(np.count_nonzero(fold_out > 0.95)),
        },
    }


def _default_configured_branch_fitter(
    target: Any,
    geometry: dict[str, Any],
    delta: dict[str, Any] | None,
) -> dict[str, Any]:
    table = load_subject_table(target.scores_path)
    y_post = _float_column(table, "Y_post")
    if target.model_family == "hf_voxel":
        nuisance = _float_column(table, "Y_base")[:, None]
        exposure = np.asarray(geometry["final_exposure"], dtype=np.float32)
        metrics = direct_voxel_loocv_statistic(
            x=exposure,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=float(target.selected_tau),
            min_coverage=int(target.selected_coverage),
        )
        weights, valid = _full_weights(
            x=exposure,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=float(target.selected_tau),
            min_coverage=int(target.selected_coverage),
        )
        return {
            "status": "complete",
            **metrics,
            "_spatial_weights": weights,
            "_spatial_valid": valid,
        }
    from stnsnr_ulf_direct_voxel_observed import compute_branch

    ulf = np.asarray(geometry["ulf_component"], dtype=np.float32)
    hf = np.asarray(geometry["hf_component"], dtype=np.float32)
    hf_active = (
        np.zeros_like(hf, dtype=bool)
        if target.hf_overlap_tau is None or math.isinf(float(target.hf_overlap_tau))
        else hf > float(target.hf_overlap_tau)
    )
    x = np.where((ulf > float(target.selected_tau)) & ~hf_active, ulf, 0.0).astype(np.float32)
    s_tau = suprathreshold_matrix(x, float(target.selected_tau))
    adjusted = target.final_branch == "delta_hf_adjusted"
    if adjusted and (delta is None or delta.get("status") not in {"adequate", "limited"}):
        return {"status": "not_computable", "reason": "jitter_delta_hf_invalid"}
    nuisance_full = np.asarray(delta["full_scores"], dtype=float) if adjusted else None
    nuisance_provider = (
        (lambda heldout: np.asarray(delta["fold_scores"], dtype=float)[heldout])
        if adjusted
        else None
    )
    branch = compute_branch(
        branch_name=target.final_branch,
        x_ulf_only=x,
        coverage=coverage_from_suprathreshold(s_tau),
        s_tau_ulf_only=s_tau,
        y_post=y_post,
        y_hf_ref=_float_column(table, "Y_HF_ref"),
        nuisance_full=nuisance_full,
        nuisance_fold_provider=nuisance_provider,
        scale_direction=target.scale_direction,
        min_coverage=int(target.selected_coverage),
        subject_ids=list(target.subject_order),
    )
    return {
        "status": "complete",
        **branch["metrics"],
        "_spatial_weights": branch["weights"],
        "_spatial_valid": np.asarray(branch["omega"], dtype=bool)
        & np.isfinite(branch["weights"]),
    }


def run_configured_jitter(
    target: Any,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float,
    seed: int,
    geometry_builder: Any = None,
    delta_builder: Any = None,
    branch_fitter: Any = None,
) -> dict[str, Any]:
    """Rebuild every geometry-derived ULF input within each jitter replicate."""
    geometry_runner = geometry_builder or _default_configured_geometry_builder
    delta_runner = delta_builder or _default_configured_delta_builder
    branch_runner = branch_fitter or _default_configured_branch_fitter
    sigma_mm = float(jitter_fwhm_mm) / 2.3548200450309493
    observed_weights, observed_valid = _configured_observed_weights(target)
    spatial_state = _new_streaming_spatial_qc(observed_weights, observed_valid)
    checkpoint_identity, checkpoint_key = _configured_jitter_checkpoint_identity(
        target,
        n_jitters=int(n_jitters),
        jitter_fwhm_mm=float(jitter_fwhm_mm),
        seed=int(seed),
    )
    checkpoint_path = (
        target.output_root / f"configured_jitter_checkpoint_{checkpoint_key}.npz"
    )
    rows = _load_configured_jitter_checkpoint(
        checkpoint_path,
        identity=checkpoint_identity,
        spatial_state=spatial_state,
    )
    resumed_replicates = len(rows)
    completed = sum(str(row.get("status")) == "complete" for row in rows)
    try:
        for index in range(len(rows), int(n_jitters)):
            rng = np.random.default_rng(int(seed) + (index + 1) * 104729)
            try:
                geometry = geometry_runner(target, rng, sigma_mm)
                delta = None
                if str(target.model_family).startswith("ulf_"):
                    if target.hf_overlap_tau is not None and math.isinf(
                        float(target.hf_overlap_tau)
                    ):
                        delta = {"status": "not_applicable_no_hf_source"}
                    else:
                        delta = delta_runner(target, geometry)
                branch = branch_runner(target, geometry, delta)
                status = str(branch.get("status", "complete"))
                if status == "complete":
                    completed += 1
                row = {
                    "jitter_index": index + 1,
                    "status": status,
                    "delta_support_status": (delta or {}).get("status", "not_applicable"),
                    "failure": branch.get("reason", ""),
                    "loocv_spearman_rho": branch.get("spearman_rho", np.nan),
                    "loocv_pearson_r": branch.get("pearson_r", np.nan),
                    "q2": branch.get("q2", np.nan),
                    "mae": branch.get("mae", np.nan),
                    "rmse": branch.get("rmse", np.nan),
                }
                if status == "complete" and "_spatial_weights" in branch:
                    try:
                        row.update(
                            _update_streaming_spatial_qc(
                                spatial_state,
                                branch["_spatial_weights"],
                                branch.get(
                                    "_spatial_valid",
                                    np.isfinite(branch["_spatial_weights"]),
                                ),
                            )
                        )
                    except (TypeError, ValueError) as exc:
                        row.update(_missing_spatial_qc(str(exc)))
                else:
                    row.update(
                        _missing_spatial_qc(
                            "completed branch did not expose spatial weights"
                            if status == "complete"
                            else "prediction replicate was not computable"
                        )
                    )
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                row = {
                    "jitter_index": index + 1,
                    "status": "not_computable",
                    "delta_support_status": "not_computable",
                    "failure": str(exc),
                    "loocv_spearman_rho": np.nan,
                    "loocv_pearson_r": np.nan,
                    "q2": np.nan,
                    "mae": np.nan,
                    "rmse": np.nan,
                    **_missing_spatial_qc("prediction replicate was not computable"),
                }
            rows.append(row)
            if (
                len(rows) % _CONFIGURED_JITTER_CHECKPOINT_INTERVAL == 0
                or len(rows) == int(n_jitters)
            ):
                _save_configured_jitter_checkpoint(
                    checkpoint_path,
                    identity=checkpoint_identity,
                    rows=rows,
                    spatial_state=spatial_state,
                )
    except BaseException:
        _save_configured_jitter_checkpoint(
            checkpoint_path,
            identity=checkpoint_identity,
            rows=rows,
            spatial_state=spatial_state,
        )
        raise
    _save_configured_jitter_checkpoint(
        checkpoint_path,
        identity=checkpoint_identity,
        rows=rows,
        spatial_state=spatial_state,
    )
    if completed == 0:
        failures = sorted({str(row["failure"]) for row in rows if row.get("failure")})
        raise RuntimeError(
            "no configured direct-voxel jitter replicate completed: "
            + ";".join(failures)
        )
    summary_path = target.output_root / "direct_voxel_configured_jitter_replicates.csv"
    write_csv(
        summary_path,
        rows,
        [
            "jitter_index",
            "status",
            "delta_support_status",
            "failure",
            "loocv_spearman_rho",
            "loocv_pearson_r",
            "q2",
            "mae",
            "rmse",
            "spatial_qc_status",
            "spatial_failure",
            "map_pearson_r",
            "n_finite_map_features",
            "support_intersection_features",
            "support_union_features",
            "valid_support_jaccard",
            "sign_consistency_fraction",
        ],
    )
    spatial_robustness = _finalize_streaming_spatial_qc(
        spatial_state,
        rows,
        output_root=target.output_root,
        artifact_prefix="direct_voxel_configured_jitter",
        feature_unit="voxel",
        requested_replicates=int(n_jitters),
    )
    return {
        "status": "complete" if completed == int(n_jitters) else "partial",
        "requested_replicates": int(n_jitters),
        "completed_replicates": completed,
        "jitter_fwhm_mm": float(jitter_fwhm_mm),
        "jitter_sigma_mm": sigma_mm,
        "seed": int(seed),
        "selected_source_identity_fixed": True,
        "final_model_id": target.final_model_id,
        "final_record_hash": target.final_record_hash,
        "selected_tau": float(target.selected_tau),
        "selected_coverage": int(target.selected_coverage),
        "final_branch": target.final_branch,
        "replicates": rows,
        "summary_csv": str(summary_path),
        "spatial_robustness": spatial_robustness,
        "checkpoint": {
            "schema_version": _CONFIGURED_JITTER_CHECKPOINT_SCHEMA,
            "method_version": _CONFIGURED_JITTER_METHOD_VERSION,
            "method_key": checkpoint_key,
            "path": str(checkpoint_path),
            "sha256": _sha256_file(checkpoint_path),
            "resumed_replicates": resumed_replicates,
            "checkpointed_replicates": len(rows),
        },
        "classification_feedback": "none",
    }


def _qc_path_for_target(target: DirectVoxelTarget) -> Path:
    if target.model_id == "A":
        return target.x_path.parent / "direct_voxel_HF_preprocess_qc.json"
    if target.model_id == "C":
        return target.x_path.parent / "direct_voxel_ULF_only_preprocess_qc.json"
    raise ValueError(f"unsupported direct-voxel jitter target: {target.model_id}")


def run_target_jitter(
    target: DirectVoxelTarget,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float = 2.0,
    seed: int = 42,
) -> dict[str, Any]:
    provenance = git_provenance()
    prefix = file_prefix_for_manifest(target.manifest_path)
    subject_ids = _subject_ids(target.subjects_csv)
    xyz = np.asarray(np.load(target.x_path.parent / "candidate_xyz.npy"), dtype=np.float32)
    qc = _load_json(_qc_path_for_target(target))
    table = load_subject_table(target.subjects_csv)
    y_post = _float_column(table, target.outcome_column)
    nuisance = np.column_stack([_float_column(table, column) for column in target.nuisance_columns])
    observed_x = np.asarray(np.load(target.x_path, mmap_mode="r"), dtype=np.float32)
    observed_weights, observed_valid = _full_weights(
        x=observed_x,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        tau=target.tau,
        min_coverage=target.min_coverage,
    )

    sigma_mm = float(jitter_fwhm_mm) / 2.3548200450309493
    rng = np.random.default_rng(seed)
    mean = np.zeros(observed_weights.shape[0], dtype=np.float64)
    m2 = np.zeros(observed_weights.shape[0], dtype=np.float64)
    finite_count = np.zeros(observed_weights.shape[0], dtype=np.int32)
    similarity_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    finite_jitter_count = 0

    for idx in range(int(n_jitters)):
        jitter_x = _jitter_matrix_for_target(target, qc, subject_ids, xyz, rng, sigma_mm)
        jitter_weights, jitter_valid = _full_weights(
            x=jitter_x,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=target.tau,
            min_coverage=target.min_coverage,
        )
        finite = np.isfinite(jitter_weights)
        if np.any(finite):
            finite_jitter_count += 1
            values = jitter_weights[finite].astype(np.float64)
            finite_count[finite] += 1
            delta = values - mean[finite]
            mean[finite] += delta / finite_count[finite]
            delta2 = values - mean[finite]
            m2[finite] += delta * delta2
        try:
            metrics = direct_voxel_loocv_statistic(
                x=jitter_x,
                y_post=y_post,
                nuisance=nuisance,
                scale_direction=target.scale_direction,
                tau=target.tau,
                min_coverage=target.min_coverage,
            )
        except Exception as exc:  # keep QC resumable; failures are summarized.
            metrics = {"spearman_rho": np.nan, "pearson_r": np.nan, "mae": np.nan, "rmse": np.nan, "q2": np.nan, "failure": str(exc)}
        map_r = _pearson(observed_weights, jitter_weights)
        overlap = _support_overlap(observed_valid, jitter_valid, observed_weights, jitter_weights)
        similarity_rows.append(
            {
                "jitter_index": idx + 1,
                "loocv_spearman_rho": metrics.get("spearman_rho", np.nan),
                "loocv_pearson_r": metrics.get("pearson_r", np.nan),
                "mae": metrics.get("mae", np.nan),
                "rmse": metrics.get("rmse", np.nan),
                "q2": metrics.get("q2", np.nan),
                "map_pearson_r": map_r,
                "n_finite_map_voxels": int(np.count_nonzero(finite)),
                "failure": metrics.get("failure", ""),
            }
        )
        overlap_rows.append({"jitter_index": idx + 1, **overlap})
        if (idx + 1) % 25 == 0 or idx + 1 == int(n_jitters):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_jitters)} formal jitters", flush=True)

    se = np.full(observed_weights.shape[0], np.nan, dtype=np.float32)
    valid_se = finite_count > 1
    se[valid_se] = np.sqrt(m2[valid_se] / (finite_count[valid_se] - 1)).astype(np.float32)
    se_path = _write_jitter_se_nifti(target, prefix, se)

    similarity_path = target.branch_dir / f"{prefix}_jitter_model_similarity.csv"
    overlap_path = target.branch_dir / f"{prefix}_jitter_selected_overlap.csv"
    summary_path = target.branch_dir / f"{prefix}_jitter_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_jitter_manifest.json"
    write_csv(similarity_path, similarity_rows, list(similarity_rows[0].keys()))
    write_csv(overlap_path, overlap_rows, list(overlap_rows[0].keys()))

    map_corr = np.asarray([row["map_pearson_r"] for row in similarity_rows], dtype=float)
    loocv_rho = np.asarray([row["loocv_spearman_rho"] for row in similarity_rows], dtype=float)
    support_jaccard = np.asarray([row["valid_support_jaccard"] for row in overlap_rows], dtype=float)
    summary = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "B": int(n_jitters),
        "seed": int(seed),
        "jitter_status": "complete" if finite_jitter_count == int(n_jitters) else "partial",
        "jitter_fwhm_mm": float(jitter_fwhm_mm),
        "jitter_sigma_mm": sigma_mm,
        "finite_jitter_count": int(finite_jitter_count),
        "map_pearson_r_median": float(np.nanmedian(map_corr)) if map_corr.size else np.nan,
        "map_pearson_r_min": float(np.nanmin(map_corr)) if np.any(np.isfinite(map_corr)) else np.nan,
        "loocv_spearman_rho_median": float(np.nanmedian(loocv_rho)) if loocv_rho.size else np.nan,
        "support_jaccard_median": float(np.nanmedian(support_jaccard)) if support_jaccard.size else np.nan,
        "jitter_se_nifti": str(se_path),
        "generated_at": iso_now(),
    }
    write_csv(summary_path, [summary], list(summary.keys()))
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "model_id": target.model_id,
            "target_manifest": str(target.manifest_path),
            "n_jitters": int(n_jitters),
            "jitter_fwhm_mm": float(jitter_fwhm_mm),
            "jitter_sigma_mm": sigma_mm,
            "seed": int(seed),
            "code_provenance": provenance,
            "method": "Subject-side spatial jitter with raw/flipped e-field resampling on the final candidate grid",
            "outputs": {
                "summary_csv": str(summary_path),
                "model_similarity_csv": str(similarity_path),
                "selected_overlap_csv": str(overlap_path),
                "jitter_se_nifti": str(se_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    return summary


def run_formal_jitter(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no direct-voxel formal jitter targets found")
    rows = []
    for target in targets:
        print(f"Running direct-voxel formal jitter QC for {target.model_id} ({args.n_jitters} jitters)")
        rows.append(
            run_target_jitter(
                target,
                n_jitters=args.n_jitters,
                jitter_fwhm_mm=args.jitter_fwhm_mm,
                seed=args.seed,
            )
        )
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "direct_voxel_formal_jitter_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "direct_voxel_formal_jitter_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_jitters": int(args.n_jitters),
            "jitter_fwhm_mm": float(args.jitter_fwhm_mm),
            "seed": int(args.seed),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"Direct-voxel formal jitter summary: {summary_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/direct_voxel_formal_jitter"),
        help="Cross-target direct-voxel formal jitter summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(FORMAL_DIRECT_MODEL_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-jitters", type=int, default=1000, help="Number of spatial jitter resamples.")
    parser.add_argument("--jitter-fwhm-mm", type=float, default=2.0, help="Gaussian translation FWHM in millimeters.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_jitter(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
