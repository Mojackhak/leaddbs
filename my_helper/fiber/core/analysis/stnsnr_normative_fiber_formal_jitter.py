#!/usr/bin/env python3
"""Spatial jitter QC for dTOR normative-fiber final models."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from stnsnr_direct_voxel_formal_jitter import (
    _CONFIGURED_JITTER_CHECKPOINT_INTERVAL,
    _CONFIGURED_JITTER_CHECKPOINT_SCHEMA,
    _configured_jitter_checkpoint_identity,
    _finalize_streaming_spatial_qc,
    _load_configured_jitter_checkpoint,
    _missing_spatial_qc,
    _new_streaming_spatial_qc,
    _save_configured_jitter_checkpoint,
    _sha256_file,
    _update_streaming_spatial_qc,
)
from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_stats import benefit_oriented_weights, fiber_net_score, partial_spearman_matrix
from stnsnr_hf_normative_fiber_smoke import (
    load_image_samplers,
    reduce_point_values_to_fiber_peaks,
    sample_max_samplers_at_points,
)
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    NormativeFiberTarget,
    _as_2d,
    _float_column,
    _load_json,
    _load_score_columns,
    default_cross_target_output_dir,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    normative_fiber_loocv_statistic,
    prepare_candidate_union,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


_NORMATIVE_FIBER_JITTER_METHOD_VERSION = "normative_fiber_minimum_count_spatial_jitter_v3"


def _candidate_fiber_ids(weights_csv: Path) -> np.ndarray:
    rows = []
    with weights_csv.open(newline="", encoding="utf-8") as handle:
        import csv

        rows = list(csv.DictReader(handle))
    ids: list[int] = []
    for row in rows:
        if str(row.get("is_candidate", "")).lower() not in {"true", "1", "yes"}:
            continue
        try:
            ids.append(int(float(row["fiber_id"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not ids:
        raise RuntimeError(f"no candidate fiber ids found in {weights_csv}")
    return np.asarray(ids, dtype=np.int64)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _append_csv_row(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def _observed_weight_vector(weights_csv: Path, candidate_ids: np.ndarray) -> np.ndarray:
    rows = []
    with weights_csv.open(newline="", encoding="utf-8") as handle:
        import csv

        rows = list(csv.DictReader(handle))
    by_id: dict[int, float] = {}
    for row in rows:
        weight_text = row.get("M_HF", "") or row.get("M_ULF", "")
        try:
            fiber_id = int(float(row["fiber_id"]))
            weight = float(weight_text)
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(weight):
            by_id[fiber_id] = weight
    return np.asarray([by_id.get(int(fiber_id), np.nan) for fiber_id in candidate_ids], dtype=np.float32)


def _candidate_points(data_mat: Path, candidate_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ids = np.asarray(candidate_ids, dtype=np.int64)
    with h5py.File(data_mat, "r") as handle:
        lengths_all = np.asarray(handle["idx"][0, :], dtype=np.int64)
        offsets = np.concatenate([[0], np.cumsum(lengths_all)])
        lengths = lengths_all[ids - 1]
        coords_blocks = []
        fibers = handle["fibers"]
        for fiber_id in ids:
            start = int(offsets[fiber_id - 1])
            stop = int(offsets[fiber_id])
            coords_blocks.append(np.asarray(fibers[0:3, start:stop], dtype=np.float32).T)
    return np.vstack(coords_blocks).astype(np.float32), lengths.astype(np.int64)


def _jitter_vector(rng: np.random.Generator, sigma_mm: float) -> np.ndarray:
    return rng.normal(loc=0.0, scale=float(sigma_mm), size=3).astype(np.float32)


def _sample_shifted_peak(samplers: list[Any], coords: np.ndarray, lengths: np.ndarray, shift_mm: np.ndarray) -> np.ndarray:
    if not samplers:
        return np.zeros(lengths.shape[0], dtype=np.float32)
    shifted = np.asarray(coords, dtype=np.float32) - np.asarray(shift_mm, dtype=np.float32).reshape(1, 3)
    values, _ = sample_max_samplers_at_points(samplers, shifted)
    return reduce_point_values_to_fiber_peaks(values, lengths)


def _side_rows_to_samplers(rows: list[dict[str, Any]], *, flipped_root: Path | None = None) -> dict[str, dict[str, list[Any]]]:
    by_subject: dict[str, dict[str, list[Any]]] = {}
    for row in rows:
        subject_id = str(row.get("subject_id", ""))
        side = str(row.get("side", ""))
        by_subject.setdefault(subject_id, {"R": [], "L_to_R": []})
        if side == "R":
            paths = [Path(path) for path in row.get("source_paths", []) if path]
            by_subject[subject_id]["R"] = load_image_samplers(paths) if paths else []
        elif side == "L":
            if flipped_root is None:
                paths = [Path(path) for path in row.get("source_paths", []) if path]
            else:
                n_paths = len(row.get("source_paths", []) or [])
                paths = [flipped_root / f"{subject_id}_hemi-L_src-{idx:02d}_to_R.nii" for idx in range(1, n_paths + 1)]
            by_subject[subject_id]["L_to_R"] = load_image_samplers([path for path in paths if path.is_file()]) if paths else []
    return by_subject


def _subject_ids(scores_csv: Path) -> list[str]:
    table = _load_score_columns(scores_csv)
    if "subject_id" not in table:
        raise KeyError(f"missing subject_id column in {scores_csv}")
    return [str(value) for value in table["subject_id"]]


def _hf_samplers(manifest: dict[str, Any], qc: dict[str, Any]) -> dict[str, dict[str, list[Any]]]:
    preprocess_dir = Path(manifest["outputs"]["preprocess_dir"]).expanduser().resolve()
    return _side_rows_to_samplers(
        qc["sampler_qc"]["side_fields"],
        flipped_root=preprocess_dir / "flipped_left_to_right",
    )


def _component_samplers(manifest: dict[str, Any], component: str) -> dict[str, dict[str, list[Any]]]:
    component_preprocess_dir = Path(manifest["component_preprocess_dir"]).expanduser().resolve()
    flipped_root = component_preprocess_dir / f"{component.lower()}_component" / "flipped_left_to_right"
    return _side_rows_to_samplers(
        manifest["component_sampler_qc"][component]["side_paths"],
        flipped_root=flipped_root,
    )


def _hf_jitter_matrix(
    subject_ids: list[str],
    samplers: dict[str, dict[str, list[Any]]],
    coords: np.ndarray,
    lengths: np.ndarray,
    rng: np.random.Generator,
    sigma_mm: float,
) -> np.ndarray:
    x = np.zeros((len(subject_ids), lengths.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        subject = samplers.get(subject_id)
        if subject is None:
            raise KeyError(f"missing HF sampler rows for {subject_id}")
        right = _sample_shifted_peak(subject.get("R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        left = _sample_shifted_peak(subject.get("L_to_R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        x[row_idx] = (right + left) / 2.0
    return x


def _ulf_jitter_matrix(
    subject_ids: list[str],
    hf_samplers: dict[str, dict[str, list[Any]]],
    ulf_samplers: dict[str, dict[str, list[Any]]],
    coords: np.ndarray,
    lengths: np.ndarray,
    rng: np.random.Generator,
    sigma_mm: float,
    *,
    tau: float,
    hf_overlap_tau: float,
) -> np.ndarray:
    x = np.zeros((len(subject_ids), lengths.shape[0]), dtype=np.float32)
    for row_idx, subject_id in enumerate(subject_ids):
        hf_subject = hf_samplers.get(subject_id, {"R": [], "L_to_R": []})
        ulf_subject = ulf_samplers.get(subject_id, {"R": [], "L_to_R": []})
        hf_right = _sample_shifted_peak(hf_subject.get("R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        hf_left = _sample_shifted_peak(hf_subject.get("L_to_R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        ulf_right = _sample_shifted_peak(ulf_subject.get("R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        ulf_left = _sample_shifted_peak(ulf_subject.get("L_to_R", []), coords, lengths, _jitter_vector(rng, sigma_mm))
        hf_component = (hf_right + hf_left) / 2.0
        ulf_component = (ulf_right + ulf_left) / 2.0
        hf_active = hf_component > float(hf_overlap_tau)
        ulf_active = ulf_component > float(tau)
        x[row_idx] = np.where(ulf_active & ~hf_active, ulf_component, 0.0).astype(np.float32)
    return x


def _fit_full_weights(
    *,
    x: np.ndarray,
    y_post: np.ndarray,
    nuisance: np.ndarray,
    scale_direction: str,
    tau: float,
    min_coverage: int,
) -> tuple[np.ndarray, np.ndarray]:
    candidate = np.sum(np.asarray(x) > float(tau), axis=0) >= int(min_coverage)
    weights = np.full(x.shape[1], np.nan, dtype=np.float32)
    if not np.any(candidate):
        return weights, candidate
    rho = partial_spearman_matrix(y_post, x[:, candidate], nuisance)
    weights[candidate] = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid = candidate & np.isfinite(weights)
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
    if denom <= 0.0:
        return float("nan")
    return float(np.sum(xx * yy) / denom)


def _support_overlap(observed_valid: np.ndarray, jitter_valid: np.ndarray, observed_weights: np.ndarray, jitter_weights: np.ndarray) -> dict[str, Any]:
    intersection = observed_valid & jitter_valid
    union = observed_valid | jitter_valid
    return {
        "support_intersection_fibers": int(np.count_nonzero(intersection)),
        "support_union_fibers": int(np.count_nonzero(union)),
        "valid_support_jaccard": float(np.count_nonzero(intersection) / np.count_nonzero(union)) if np.any(union) else float("nan"),
        "sign_consistency_fraction": float(np.mean(np.sign(observed_weights[intersection]) == np.sign(jitter_weights[intersection])))
        if np.any(intersection)
        else float("nan"),
    }


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
    columns = _load_score_columns(target.scores_path)
    subject_column = next(
        (column for column in columns if column.strip().lower() == "subject_id"),
        None,
    )
    if subject_column is None:
        raise KeyError("configured sensitivity scores are missing subject_id")
    if tuple(str(value) for value in columns[subject_column]) != tuple(target.subject_order):
        raise ValueError("configured sensitivity score subject order mismatch")
    y_post = _float_column(columns, "Y_post")
    baseline_column = "Y_base" if target.final_branch == "hf_source" else "Y_HF_ref"
    baseline = _float_column(columns, baseline_column)[:, None]
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


def _configured_valid_columns(target: Any, *, matched_hf: bool = False) -> tuple[np.ndarray, np.ndarray]:
    paths = target.matched_hf_paths if matched_hf else {
        "feature_ids": target.feature_ids_path,
        "valid_feature_ids": target.valid_feature_ids_path,
    }
    parent_path = paths.get("feature_ids")
    valid_path = paths.get("valid_feature_ids")
    if parent_path is None or valid_path is None:
        raise ValueError("configured fiber jitter requires parent and valid feature axes")
    parent = np.asarray(np.load(parent_path, mmap_mode="r"), dtype=np.int64)
    valid = np.asarray(np.load(valid_path, mmap_mode="r"), dtype=np.int64)
    positions = {int(fiber_id): index for index, fiber_id in enumerate(parent)}
    try:
        columns = np.asarray([positions[int(fiber_id)] for fiber_id in valid], dtype=np.int64)
    except KeyError as exc:
        raise ValueError("configured fiber jitter valid axis is not a parent-axis subset") from exc
    if columns.size == 0 or np.any(columns[1:] <= columns[:-1]):
        raise ValueError("configured fiber jitter valid axis must preserve parent order")
    return columns, valid


def _configured_observed_weights(target: Any) -> tuple[np.ndarray, np.ndarray]:
    y_post, nuisance, _ = _configured_outcome_and_nuisance(target)
    valid_columns, _ = _configured_valid_columns(target)
    exposure = np.asarray(np.load(target.exposure_path, mmap_mode="r"), dtype=np.float32)
    return _fit_full_weights(
        x=exposure[:, valid_columns],
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
    """Run observed fiber LOOCV around one immutable selected source."""
    y_post, nuisance, fold_nuisance = _configured_outcome_and_nuisance(target)
    valid_columns, fiber_ids = _configured_valid_columns(target)
    cells: list[dict[str, Any]] = []
    for multiplier in tau_multipliers:
        tau = float(target.selected_tau) * float(multiplier)
        try:
            exposure = _configured_neighborhood_exposure(target, tau)
            reduced = prepare_candidate_union(
                x=exposure[:, valid_columns],
                fiber_ids=fiber_ids,
                tau=tau,
                min_coverage=int(target.selected_coverage),
            )
            metrics = normative_fiber_loocv_statistic(
                reduced=reduced,
                y_post=y_post,
                nuisance=nuisance,
                fold_nuisance=fold_nuisance,
                scale_direction=target.scale_direction,
                score_config=target.score_config,
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
    summary_path = target.output_root / "normative_fiber_selected_source_neighborhood.csv"
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
        "score": {
            "sweet_fraction": target.score_config.sweet_fraction,
            "sour_fraction": target.score_config.sour_fraction,
            "weighted_peak_fraction": target.score_config.weighted_peak_fraction,
            "sweet_selected_min_count": target.score_config.sweet_selected_min_count,
            "sour_selected_min_count": target.score_config.sour_selected_min_count,
            "weighted_peak_min_count": target.score_config.weighted_peak_min_count,
        },
        "classification_feedback": "none",
    }


def _configured_sampler_rows(
    manifest_path: Path,
    rows: Any,
    subject_order: tuple[str, ...],
    label: str,
) -> dict[str, dict[str, list[Any]]]:
    from stnsnr_direct_voxel_formal_jitter import _validated_sampling_rows

    validated = _validated_sampling_rows(manifest_path, rows, subject_order, label)
    samplers: dict[str, dict[str, list[Any]]] = {}
    for row in validated:
        samplers[row["subject_id"]] = {
            "R": load_image_samplers([Path(item["path"]) for item in row["right"]]),
            "L_to_R": load_image_samplers(
                [Path(item["path"]) for item in row["left_to_right"]]
            ),
        }
    return samplers


def _sample_fiber_component(
    subject_order: tuple[str, ...],
    samplers: dict[str, dict[str, list[Any]]],
    coords: np.ndarray,
    lengths: np.ndarray,
    shifts: dict[tuple[str, str], np.ndarray],
) -> np.ndarray:
    matrix = np.zeros((len(subject_order), lengths.shape[0]), dtype=np.float32)
    for index, subject_id in enumerate(subject_order):
        subject = samplers[subject_id]
        right = _sample_shifted_peak(
            subject["R"], coords, lengths, shifts[(subject_id, "right")]
        )
        left = _sample_shifted_peak(
            subject["L_to_R"],
            coords,
            lengths,
            shifts[(subject_id, "left_to_right")],
        )
        matrix[index] = (right + left) / 2.0
    return matrix


def _default_configured_geometry_builder(
    target: Any,
    rng: np.random.Generator,
    sigma_mm: float,
) -> dict[str, Any]:
    from stnsnr_direct_voxel_formal_jitter import _manifest_artifact_path

    manifest = target.jitter_input_manifest
    if not isinstance(manifest, dict) or target.jitter_input_manifest_path is None:
        raise ValueError("configured fiber jitter requires a validated jitter input manifest")
    geometry = manifest.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("builder") != "normative_fiber_efield_resample_v1":
        raise ValueError(
            "jitter geometry requires builder='normative_fiber_efield_resample_v1'"
        )
    manifest_path = Path(target.jitter_input_manifest_path)
    data_mat = _manifest_artifact_path(
        manifest_path,
        geometry.get("connectome_data_mat"),
        "connectome_data_mat",
    )
    _, final_ids = _configured_valid_columns(target)
    final_coords, final_lengths = _candidate_points(data_mat, final_ids)

    def shifts() -> dict[tuple[str, str], np.ndarray]:
        return {
            (subject_id, side): _jitter_vector(rng, sigma_mm)
            for subject_id in target.subject_order
            for side in ("right", "left_to_right")
        }

    if target.model_family == "hf_fiber":
        reference = _configured_sampler_rows(
            manifest_path,
            geometry.get("hf_reference_sampling_qc"),
            target.subject_order,
            "hf_reference",
        )
        return {
            "final_exposure": _sample_fiber_component(
                target.subject_order,
                reference,
                final_coords,
                final_lengths,
                shifts(),
            )
        }

    hf_samplers = _configured_sampler_rows(
        manifest_path,
        geometry.get("hf_component_sampling_qc"),
        target.subject_order,
        "hf_component",
    )
    ulf_samplers = _configured_sampler_rows(
        manifest_path,
        geometry.get("ulf_component_sampling_qc"),
        target.subject_order,
        "ulf_component",
    )
    hf_shifts = shifts()
    result: dict[str, Any] = {
        "hf_component": _sample_fiber_component(
            target.subject_order,
            hf_samplers,
            final_coords,
            final_lengths,
            hf_shifts,
        ),
        "ulf_component": _sample_fiber_component(
            target.subject_order,
            ulf_samplers,
            final_coords,
            final_lengths,
            shifts(),
        ),
        "fiber_ids": final_ids,
    }
    if target.hf_overlap_tau is not None and not math.isinf(float(target.hf_overlap_tau)):
        if target.matched_hf_final is None:
            raise ValueError("finite HF-overlap fiber jitter requires matched_hf_final")
        _, matched_ids = _configured_valid_columns(target, matched_hf=True)
        matched_coords, matched_lengths = _candidate_points(data_mat, matched_ids)
        reference = _configured_sampler_rows(
            manifest_path,
            geometry.get("hf_reference_sampling_qc"),
            target.subject_order,
            "hf_reference",
        )
        result.update(
            {
                "hf_reference": _sample_fiber_component(
                    target.subject_order,
                    reference,
                    matched_coords,
                    matched_lengths,
                    shifts(),
                ),
                "hf_reprogrammed": _sample_fiber_component(
                    target.subject_order,
                    hf_samplers,
                    matched_coords,
                    matched_lengths,
                    hf_shifts,
                ),
                "matched_fiber_ids": matched_ids,
            }
        )
    return result


def _default_configured_delta_builder(target: Any, geometry: dict[str, Any]) -> dict[str, Any]:
    from stnsnr_direct_voxel_formal_jitter import _support_category, _support_fraction
    from stnsnr_ulf_normative_fiber_observed import fit_hf_delta_fold, fit_hf_delta_full

    if target.matched_hf_final is None:
        raise ValueError("ULF fiber jitter DeltaHF rebuild requires matched_hf_final")
    if target.y_base_path is None:
        raise ValueError("ULF fiber jitter DeltaHF rebuild requires Y_base")
    required = {"hf_reference", "hf_reprogrammed", "matched_fiber_ids"}
    missing = sorted(required - set(geometry))
    if missing:
        raise ValueError("ULF fiber jitter geometry is missing DeltaHF inputs: " + ",".join(missing))
    columns = _load_score_columns(target.scores_path)
    y_hf_ref = _float_column(columns, "Y_HF_ref")
    y_base = np.asarray(np.load(target.y_base_path, mmap_mode="r"), dtype=float)
    reference = np.asarray(geometry["hf_reference"], dtype=np.float32)
    component = np.asarray(geometry["hf_reprogrammed"], dtype=np.float32)
    fiber_ids = np.asarray(geometry["matched_fiber_ids"], dtype=np.int64)
    tau = float(target.matched_hf_final.selected_tau)
    coverage = int(target.matched_hf_final.selected_coverage)
    full = fit_hf_delta_full(
        reference,
        component,
        y_hf_ref,
        y_base,
        target.scale_direction,
        tau,
        coverage,
        fiber_ids,
        target.score_config,
    )
    full_support = np.asarray(full["candidate"], dtype=bool) & np.isfinite(full["weights"])
    subject_fractions, any_zero = _support_fraction(component, full_support, tau)
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
            coverage,
            fiber_ids,
            target.score_config,
        )
        fold_scores[heldout] = fold["delta"]
        fold_support = np.asarray(fold["candidate"], dtype=bool) & np.isfinite(fold["weights"])
        fractions, fold_zero = _support_fraction(
            component, fold_support, tau
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
    columns = _load_score_columns(target.scores_path)
    y_post = _float_column(columns, "Y_post")
    if target.model_family == "hf_fiber":
        exposure = np.asarray(geometry["final_exposure"], dtype=np.float32)
        _, fiber_ids = _configured_valid_columns(target)
        nuisance = _float_column(columns, "Y_base")[:, None]
        reduced = prepare_candidate_union(
            x=exposure,
            fiber_ids=fiber_ids,
            tau=float(target.selected_tau),
            min_coverage=int(target.selected_coverage),
        )
        metrics = normative_fiber_loocv_statistic(
            reduced=reduced,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            score_config=target.score_config,
        )
        weights, valid = _fit_full_weights(
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
    from stnsnr_ulf_normative_fiber_observed import run_ulf_fiber_branch

    ulf = np.asarray(geometry["ulf_component"], dtype=np.float32)
    hf = np.asarray(geometry["hf_component"], dtype=np.float32)
    hf_active = (
        np.zeros_like(hf, dtype=bool)
        if target.hf_overlap_tau is None or math.isinf(float(target.hf_overlap_tau))
        else hf > float(target.hf_overlap_tau)
    )
    x = np.where((ulf > float(target.selected_tau)) & ~hf_active, ulf, 0.0).astype(np.float32)
    adjusted = target.final_branch == "delta_hf_adjusted"
    if adjusted and (delta is None or delta.get("status") not in {"adequate", "limited"}):
        return {"status": "not_computable", "reason": "jitter_delta_hf_invalid"}
    nuisance_full = np.asarray(delta["full_scores"], dtype=float) if adjusted else None
    nuisance_provider = (
        (lambda heldout: np.asarray(delta["fold_scores"], dtype=float)[heldout])
        if adjusted
        else None
    )
    branch = run_ulf_fiber_branch(
        branch_name=target.final_branch,
        x_ulf_only=x,
        y_post=y_post,
        y_hf_ref=_float_column(columns, "Y_HF_ref"),
        nuisance_full=nuisance_full,
        nuisance_fold_provider=nuisance_provider,
        subject_ids=list(target.subject_order),
        scale_direction=target.scale_direction,
        tau=float(target.selected_tau),
        min_coverage=int(target.selected_coverage),
        fiber_ids=np.asarray(geometry["fiber_ids"]),
        sweet_fraction=target.score_config.sweet_fraction,
        sour_fraction=target.score_config.sour_fraction,
        weighted_peak_fraction=target.score_config.weighted_peak_fraction,
        sweet_selected_min_count=target.score_config.sweet_selected_min_count,
        sour_selected_min_count=target.score_config.sour_selected_min_count,
        weighted_peak_min_count=target.score_config.weighted_peak_min_count,
    )
    return {
        "status": "complete",
        **branch["metrics"],
        "_spatial_weights": branch["weights"],
        "_spatial_valid": np.asarray(branch["candidate"], dtype=bool)
        & np.isfinite(branch["weights"]),
    }


def _normative_fiber_checkpoint_identity(
    target: Any,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float,
    seed: int,
) -> tuple[dict[str, Any], str]:
    identity, _ = _configured_jitter_checkpoint_identity(
        target,
        n_jitters=n_jitters,
        jitter_fwhm_mm=jitter_fwhm_mm,
        seed=seed,
    )
    identity["method_version"] = _NORMATIVE_FIBER_JITTER_METHOD_VERSION
    identity["valid_feature_axis_file_sha256"] = _sha256_file(
        target.valid_feature_ids_path
    )
    identity["score"] = {
        "sweet_fraction": target.score_config.sweet_fraction,
        "sour_fraction": target.score_config.sour_fraction,
        "weighted_peak_fraction": target.score_config.weighted_peak_fraction,
        "sweet_selected_min_count": target.score_config.sweet_selected_min_count,
        "sour_selected_min_count": target.score_config.sour_selected_min_count,
        "weighted_peak_min_count": target.score_config.weighted_peak_min_count,
    }
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return identity, key


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
    """Run final-linked normative-fiber jitter with per-replicate rebuilds."""
    geometry_runner = geometry_builder or _default_configured_geometry_builder
    delta_runner = delta_builder or _default_configured_delta_builder
    branch_runner = branch_fitter or _default_configured_branch_fitter
    sigma_mm = float(jitter_fwhm_mm) / 2.3548200450309493
    observed_weights, observed_valid = _configured_observed_weights(target)
    spatial_state = _new_streaming_spatial_qc(observed_weights, observed_valid)
    checkpoint_identity, checkpoint_key = _normative_fiber_checkpoint_identity(
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
                completed += int(status == "complete")
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
            "no configured normative-fiber jitter replicate completed: "
            + ";".join(failures)
        )
    summary_path = target.output_root / "normative_fiber_configured_jitter_replicates.csv"
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
        artifact_prefix="normative_fiber_configured_jitter",
        feature_unit="fiber",
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
            "method_version": _NORMATIVE_FIBER_JITTER_METHOD_VERSION,
            "method_key": checkpoint_key,
            "path": str(checkpoint_path),
            "sha256": _sha256_file(checkpoint_path),
            "resumed_replicates": resumed_replicates,
            "checkpointed_replicates": len(rows),
        },
        "score": checkpoint_identity["score"],
        "classification_feedback": "none",
    }


def _target_manifest_and_qc(target: NormativeFiberTarget) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(target.manifest_path)
    qc_path = Path(manifest["outputs"]["mapping_qc_json"]).expanduser().resolve()
    return manifest, _load_json(qc_path)


def run_target_jitter(
    target: NormativeFiberTarget,
    *,
    n_jitters: int,
    jitter_fwhm_mm: float = 2.0,
    seed: int = 42,
) -> dict[str, Any]:
    provenance = git_provenance()
    manifest, qc = _target_manifest_and_qc(target)
    prefix = file_prefix_for_manifest(target.manifest_path)
    weights_csv = Path(manifest["outputs"]["weights_csv"]).expanduser().resolve()
    candidate_ids = _candidate_fiber_ids(weights_csv)
    observed_weights = _observed_weight_vector(weights_csv, candidate_ids)
    observed_valid = np.isfinite(observed_weights)
    coords, lengths = _candidate_points(Path(manifest["data_mat"]).expanduser().resolve(), candidate_ids)
    subject_ids = _subject_ids(target.scores_csv)
    score_columns = _load_score_columns(target.scores_csv)
    y_post = _float_column(score_columns, target.outcome_column)
    nuisance = np.column_stack([_float_column(score_columns, column) for column in target.nuisance_columns])
    sigma_mm = float(jitter_fwhm_mm) / 2.3548200450309493
    if target.model_id == "B_DTOR":
        hf_samplers = _hf_samplers(manifest, qc)
        matrix_builder = lambda jitter_rng: _hf_jitter_matrix(subject_ids, hf_samplers, coords, lengths, jitter_rng, sigma_mm)
    elif target.model_id == "D_DTOR":
        hf_samplers = _component_samplers(manifest, "HF")
        ulf_samplers = _component_samplers(manifest, "ULF")
        hf_overlap_tau = float(manifest["parameters"].get("hf_overlap_tau_v_per_m", 800.0))
        matrix_builder = lambda jitter_rng: _ulf_jitter_matrix(
            subject_ids,
            hf_samplers,
            ulf_samplers,
            coords,
            lengths,
            jitter_rng,
            sigma_mm,
            tau=target.tau,
            hf_overlap_tau=hf_overlap_tau,
        )
    else:
        raise ValueError(f"unsupported normative-fiber jitter target: {target.model_id}")

    similarity_path = target.branch_dir / f"{prefix}_jitter_model_similarity.csv"
    overlap_path = target.branch_dir / f"{prefix}_jitter_selected_overlap.csv"
    summary_path = target.branch_dir / f"{prefix}_jitter_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_jitter_manifest.json"
    progress_similarity_path = target.branch_dir / f"{prefix}_jitter_model_similarity_in_progress.csv"
    progress_overlap_path = target.branch_dir / f"{prefix}_jitter_selected_overlap_in_progress.csv"
    similarity_rows: list[dict[str, Any]] = [dict(row) for row in _read_csv_rows(progress_similarity_path)]
    overlap_rows: list[dict[str, Any]] = [dict(row) for row in _read_csv_rows(progress_overlap_path)]
    start_idx = min(len(similarity_rows), len(overlap_rows), int(n_jitters))
    similarity_fields = [
        "jitter_index",
        "loocv_spearman_rho",
        "loocv_pearson_r",
        "mae",
        "rmse",
        "q2",
        "map_pearson_r",
        "n_finite_map_fibers",
        "failure",
    ]
    overlap_fields = [
        "jitter_index",
        "support_intersection_fibers",
        "support_union_fibers",
        "valid_support_jaccard",
        "sign_consistency_fraction",
    ]
    for idx in range(start_idx, int(n_jitters)):
        jitter_rng = np.random.default_rng(int(seed) + (idx + 1) * 104729 + (0 if target.model_id == "B_DTOR" else 1000003))
        jitter_x = matrix_builder(jitter_rng)
        jitter_weights, jitter_valid = _fit_full_weights(
            x=jitter_x,
            y_post=y_post,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            tau=target.tau,
            min_coverage=target.min_coverage,
        )
        try:
            reduced = prepare_candidate_union(
                x=jitter_x,
                fiber_ids=candidate_ids,
                tau=target.tau,
                min_coverage=target.min_coverage,
            )
            metrics = normative_fiber_loocv_statistic(
                reduced=reduced,
                y_post=y_post,
                nuisance=nuisance,
                scale_direction=target.scale_direction,
            )
        except Exception as exc:
            metrics = {"spearman_rho": np.nan, "pearson_r": np.nan, "mae": np.nan, "rmse": np.nan, "q2": np.nan, "failure": str(exc)}
        overlap = _support_overlap(observed_valid, jitter_valid, observed_weights, jitter_weights)
        similarity_row = {
            "jitter_index": idx + 1,
            "loocv_spearman_rho": metrics.get("spearman_rho", np.nan),
            "loocv_pearson_r": metrics.get("pearson_r", np.nan),
            "mae": metrics.get("mae", np.nan),
            "rmse": metrics.get("rmse", np.nan),
            "q2": metrics.get("q2", np.nan),
            "map_pearson_r": _pearson(observed_weights, jitter_weights),
            "n_finite_map_fibers": int(np.count_nonzero(np.isfinite(jitter_weights))),
            "failure": metrics.get("failure", ""),
        }
        overlap_row = {"jitter_index": idx + 1, **overlap}
        similarity_rows.append(similarity_row)
        overlap_rows.append(overlap_row)
        _append_csv_row(progress_similarity_path, similarity_row, similarity_fields)
        _append_csv_row(progress_overlap_path, overlap_row, overlap_fields)
        if (idx + 1) % 25 == 0 or idx + 1 == int(n_jitters):
            print(f"  {target.model_id}: completed {idx + 1}/{int(n_jitters)} normative-fiber jitters", flush=True)

    similarity_rows = similarity_rows[: int(n_jitters)]
    overlap_rows = overlap_rows[: int(n_jitters)]
    finite_jitter_count = sum(int(float(row.get("n_finite_map_fibers", "0") or 0)) > 0 for row in similarity_rows)
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
        "n_candidate_fibers": int(candidate_ids.shape[0]),
        "map_pearson_r_median": float(np.nanmedian(map_corr)) if map_corr.size else np.nan,
        "map_pearson_r_min": float(np.nanmin(map_corr)) if np.any(np.isfinite(map_corr)) else np.nan,
        "loocv_spearman_rho_median": float(np.nanmedian(loocv_rho)) if loocv_rho.size else np.nan,
        "support_jaccard_median": float(np.nanmedian(support_jaccard)) if support_jaccard.size else np.nan,
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
            "candidate_fiber_ids_source": str(weights_csv),
            "code_provenance": provenance,
            "method": "Final selected-source candidate-fiber spatial jitter with raw/flipped E-field resampling",
            "outputs": {
                "summary_csv": str(summary_path),
                "model_similarity_csv": str(similarity_path),
                "selected_overlap_csv": str(overlap_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    return summary


def run_formal_jitter(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no dTOR normative-fiber formal jitter targets found")
    rows = []
    for target in targets:
        print(f"Running normative-fiber formal jitter QC for {target.model_id} ({args.n_jitters} jitters)")
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
    summary_path = output_dir / "normative_fiber_formal_jitter_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "normative_fiber_formal_jitter_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "n_jitters": int(args.n_jitters),
            "jitter_fwhm_mm": float(args.jitter_fwhm_mm),
            "seed": int(args.seed),
            "code_provenance": git_provenance(),
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"Normative-fiber formal jitter summary: {summary_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_formal_jitter"),
        help="Cross-target normative-fiber formal jitter summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    parser.add_argument("--n-jitters", type=int, default=1000, help="Number of spatial jitter resamples.")
    parser.add_argument("--jitter-fwhm-mm", type=float, default=2.0, help="Gaussian translation FWHM in millimeters.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_formal_jitter(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
