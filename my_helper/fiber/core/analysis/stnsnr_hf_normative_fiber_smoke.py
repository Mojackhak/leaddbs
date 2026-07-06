#!/usr/bin/env python3
"""HF normative connectome fiber observed smoke driver."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import h5py
import nibabel as nib
import numpy as np
import pandas as pd
from scipy.ndimage import map_coordinates

from stnsnr_four_model_readiness import (
    DEFAULT_CANONICAL_ASSET_ROOT,
    DEFAULT_CLINICAL_ROOT,
    DEFAULT_MATLAB,
    DEFAULT_VAL_ROOT,
    HF_DEFAULT_SCALES,
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
from stnsnr_hf_direct_voxel_smoke import (
    collect_side_field_paths,
    filter_hf_stn_rows,
    flip_left_fields_with_matlab,
    fit_baseline_only,
    load_stim_table,
    load_subject_records,
    slugify,
)


CONNECTOMES = {
    "ppmi": {
        "slug": "ppmi_85_ewert_2017",
        "label": "PPMI 85 (Ewert 2017)",
        "path": Path("connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat"),
    },
    "mgh": {
        "slug": "mgh_usc_hcp_32_horn_2017",
        "label": "MGH-USC HCP 32 (Horn 2017)",
        "path": Path("connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat"),
    },
    "dtor": {
        "slug": "dtor_985_full_elias_2024",
        "label": "dTOR-985 Full (Elias 2024)",
        "path": Path("connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat"),
    },
}


@dataclass(frozen=True)
class ImageSampler:
    path: str
    data: np.ndarray
    inv_affine: np.ndarray
    shape: tuple[int, int, int]


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


def fiber_block_slices(lengths: np.ndarray, fiber_chunk_size: int) -> Iterable[tuple[int, int, int, int]]:
    """Yield fiber and point start/stop indices for chunked connectome processing."""
    lengths_arr = np.asarray(lengths, dtype=np.int64)
    if fiber_chunk_size <= 0:
        raise ValueError("fiber_chunk_size must be positive")
    point_start = 0
    for fiber_start in range(0, lengths_arr.size, fiber_chunk_size):
        fiber_stop = min(lengths_arr.size, fiber_start + fiber_chunk_size)
        point_stop = point_start + int(np.sum(lengths_arr[fiber_start:fiber_stop]))
        yield fiber_start, fiber_stop, point_start, point_stop
        point_start = point_stop


def reduce_point_values_to_fiber_peaks(point_values: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Reduce sampled point values to peak value per fiber."""
    values = np.asarray(point_values, dtype=np.float32)
    lengths_arr = np.asarray(lengths, dtype=np.int64)
    if np.any(lengths_arr <= 0):
        raise ValueError("fiber lengths must be positive")
    if values.size != int(np.sum(lengths_arr)):
        raise ValueError(f"point_values length {values.size} does not match sum(lengths) {int(np.sum(lengths_arr))}")
    offsets = np.concatenate([[0], np.cumsum(lengths_arr[:-1])])
    return np.maximum.reduceat(values, offsets).astype(np.float32)


def load_idx_lengths(data_mat: Path, max_fibers: int = 0) -> np.ndarray:
    with h5py.File(data_mat, "r") as handle:
        lengths = np.asarray(handle["idx"][0, :], dtype=np.int64)
    if max_fibers and max_fibers > 0:
        lengths = lengths[:max_fibers]
    return lengths


def load_image_sampler(path: Path) -> ImageSampler:
    img = nib.load(str(path))
    return ImageSampler(
        path=str(path),
        data=np.asarray(img.dataobj, dtype=np.float32),
        inv_affine=np.linalg.inv(img.affine),
        shape=tuple(int(item) for item in img.shape[:3]),
    )


def load_image_samplers(paths: list[Path]) -> list[ImageSampler]:
    return [load_image_sampler(path) for path in paths]


def sample_sampler_at_points(sampler: ImageSampler, xyz: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    vox = nib.affines.apply_affine(sampler.inv_affine, xyz)
    inside = (
        (vox[:, 0] >= 0)
        & (vox[:, 0] <= sampler.shape[0] - 1)
        & (vox[:, 1] >= 0)
        & (vox[:, 1] <= sampler.shape[1] - 1)
        & (vox[:, 2] >= 0)
        & (vox[:, 2] <= sampler.shape[2] - 1)
    )
    values = np.zeros(xyz.shape[0], dtype=np.float32)
    if np.any(inside):
        values[inside] = map_coordinates(
            sampler.data,
            [vox[inside, 0], vox[inside, 1], vox[inside, 2]],
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        ).astype(np.float32)
    negative = values < 0
    n_negative = int(np.count_nonzero(negative))
    min_before = float(values.min()) if values.size else 0.0
    if n_negative:
        values[negative] = 0
    return values, {
        "path": sampler.path,
        "inside_points": int(np.count_nonzero(inside)),
        "nonzero_points": int(np.count_nonzero(values)),
        "negative_clamped_points": n_negative,
        "min_before_clamp": min_before,
        "max_after_clamp": float(values.max()) if values.size else 0.0,
    }


def sample_max_samplers_at_points(samplers: list[ImageSampler], xyz: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if not samplers:
        raise ValueError("no samplers provided")
    max_values = np.zeros(xyz.shape[0], dtype=np.float32)
    qc: list[dict[str, Any]] = []
    for sampler in samplers:
        values, row = sample_sampler_at_points(sampler, xyz)
        max_values = np.maximum(max_values, values)
        qc.append(row)
    return max_values, qc


def prepare_subject_samplers(
    records: list[Any],
    stim_rows: pd.DataFrame,
    derivatives_root: Path,
    repo_root: Path,
    matlab_bin: Path,
    preprocess_dir: Path,
    force_flip: bool,
) -> tuple[dict[str, dict[str, list[ImageSampler]]], dict[str, Any]]:
    side_paths, side_field_qc = collect_side_field_paths(records, stim_rows, derivatives_root)
    flipped_left_paths, flip_result = flip_left_fields_with_matlab(
        repo_root=repo_root,
        matlab_bin=matlab_bin,
        side_paths=side_paths,
        preprocess_dir=preprocess_dir,
        force=force_flip,
    )
    samplers: dict[str, dict[str, list[ImageSampler]]] = {}
    for record in records:
        samplers[record.subject_id] = {
            "R": load_image_samplers(side_paths[(record.subject_id, "R")]),
            "L_to_R": load_image_samplers(flipped_left_paths[record.subject_id]),
        }
    return samplers, {"side_fields": side_field_qc, "flip_result": flip_result}


def build_fiber_exposure_sidecar(
    data_mat: Path,
    records: list[Any],
    samplers: dict[str, dict[str, list[ImageSampler]]],
    output_npy: Path,
    fiber_ids_npy: Path,
    *,
    max_fibers: int,
    fiber_chunk_size: int,
) -> dict[str, Any]:
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
                right_points, _ = sample_max_samplers_at_points(samplers[record.subject_id]["R"], coords)
                left_points, _ = sample_max_samplers_at_points(samplers[record.subject_id]["L_to_R"], coords)
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


def load_or_build_exposure(
    data_mat: Path,
    records: list[Any],
    samplers: dict[str, dict[str, list[ImageSampler]]],
    preprocess_dir: Path,
    *,
    max_fibers: int,
    fiber_chunk_size: int,
    force_rebuild: bool,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    output_npy = preprocess_dir / "X_HF_fiber_float32_subject_major.npy"
    fiber_ids_npy = preprocess_dir / "fiber_ids.npy"
    if output_npy.is_file() and fiber_ids_npy.is_file() and not force_rebuild:
        x = np.load(output_npy, mmap_mode="r")
        fiber_ids = np.load(fiber_ids_npy)
        return x, fiber_ids, {
            "status": "reused_existing_sidecar",
            "output_npy": str(output_npy),
            "fiber_ids_npy": str(fiber_ids_npy),
            "n_subjects": int(x.shape[0]),
            "n_fibers": int(x.shape[1]),
        }
    sidecar_qc = build_fiber_exposure_sidecar(
        data_mat,
        records,
        samplers,
        output_npy,
        fiber_ids_npy,
        max_fibers=max_fibers,
        fiber_chunk_size=fiber_chunk_size,
    )
    return np.load(output_npy, mmap_mode="r"), np.load(fiber_ids_npy), sidecar_qc


def run_observed_loocv(
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    subject_ids: list[str],
    scale_direction: str,
    tau: float,
    min_coverage: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError(f"empty fiber candidate set for tau={tau} Coverage>={min_coverage}")

    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_candidate = partial_spearman_matrix(y_post, np.asarray(x[:, candidate]), y_base)
    rho[candidate] = rho_candidate.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_net = fiber_net_score(np.asarray(x), weights, candidate, fiber_ids=fiber_ids)

    score_rows: list[dict[str, Any]] = []
    for idx, subject_id in enumerate(subject_ids):
        score_rows.append(
            {
                "subject_id": subject_id,
                "Y_post": y_post[idx],
                "Y_base": y_base[idx],
                "SweetPeak5": full_net.sweet_peak5[idx],
                "SourPeak5": full_net.sour_peak5[idx],
                "NetFiberScore": full_net.net_score[idx],
                "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
                "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
                "n_sweet_peak_fibers": int(full_net.n_sweet_peak_fibers),
                "n_sour_peak_fibers": int(full_net.n_sour_peak_fibers),
                "score_map_source": "full_sample",
                "is_primary_score": True,
            }
        )

    pred = np.full(y_post.shape[0], np.nan, dtype=float)
    pred_base = np.full(y_post.shape[0], np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    for heldout in range(y_post.shape[0]):
        train = np.array([idx for idx in range(y_post.shape[0]) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty candidate set for held-out {subject_ids[heldout]}")
        rho_fold = partial_spearman_matrix(y_post[train], np.asarray(x[train][:, candidate_fold]), y_base[train])
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(np.asarray(x), weights_fold, candidate_fold, fiber_ids=fiber_ids)
        fold_pred, beta = fit_linear_prediction(
            y_post[train],
            fold_net.net_score[train],
            y_base[train],
            fold_net.net_score[[heldout]],
            y_base[[heldout]],
        )
        fold_base, base_beta = fit_baseline_only(y_post[train], y_base[train], y_base[[heldout]])
        pred[heldout] = fold_pred[0]
        pred_base[heldout] = fold_base[0]
        fold_rows.append(
            {
                "fold_id": heldout + 1,
                "heldout_subject_id": subject_ids[heldout],
                "Y_post": y_post[heldout],
                "Y_base": y_base[heldout],
                "SweetPeak5_LOOCV": fold_net.sweet_peak5[heldout],
                "SourPeak5_LOOCV": fold_net.sour_peak5[heldout],
                "NetFiberScore_LOOCV": fold_net.net_score[heldout],
                "prediction_NetFiberScore_model": fold_pred[0],
                "prediction_baseline_only": fold_base[0],
                "residual_NetFiberScore_model": y_post[heldout] - fold_pred[0],
                "residual_baseline_only": y_post[heldout] - fold_base[0],
                "n_train": int(train.size),
                "n_candidate_fibers": int(np.count_nonzero(candidate_fold)),
                "n_sweet_selected_fibers": int(fold_net.sweet_fiber_ids.size),
                "n_sour_selected_fibers": int(fold_net.sour_fiber_ids.size),
                "delta": beta[1],
                "beta_Y_base": beta[2],
                "baseline_beta_Y_base": base_beta[1],
            }
        )

    metrics = regression_metrics(y_post, pred, pred_base)
    qc = {
        "tau_v_per_m": tau,
        "min_coverage": min_coverage,
        "n_fibers": int(x.shape[1]),
        "n_candidate_fibers": int(np.count_nonzero(candidate)),
        "coverage_min": int(np.min(coverage)) if coverage.size else 0,
        "coverage_max": int(np.max(coverage)) if coverage.size else 0,
        "coverage_mean": float(np.mean(coverage)) if coverage.size else 0.0,
        "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
        "loocv_metrics": metrics,
        "resampling_status": "not_run_smoke_observed_only",
    }
    return score_rows, fold_rows, qc, coverage, rho, weights


def run_hf_normative_fiber_smoke(args: argparse.Namespace) -> int:
    started = time.time()
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    derivatives_root = Path(args.leaddbs_derivatives).expanduser().resolve()
    matlab_bin = Path(args.matlab_bin).expanduser().resolve()
    connectome_info = CONNECTOMES[args.connectome]
    connectome_slug = connectome_info["slug"]
    data_mat = asset_root / connectome_info["path"]
    if not data_mat.is_file():
        raise RuntimeError(f"connectome data.mat missing: {data_mat}")

    scale = args.scale
    scale_slug = slugify(scale)
    output_root = Path(args.output_root).expanduser().resolve() / connectome_slug / scale_slug / "peak_efield_tau800_primary"
    preprocess_dir = output_root / "preprocess"
    branch_dir = output_root
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    branch_dir.mkdir(parents=True, exist_ok=True)

    records = load_subject_records(clinical_root, scale)
    subject_ids = [record.subject_id for record in records]
    stim_rows = filter_hf_stn_rows(load_stim_table(clinical_root), set(subject_ids))
    scale_direction, scale_direction_source = infer_scale_direction(scale)
    if scale_direction not in {"lower", "higher"}:
        raise RuntimeError(f"unknown scale direction for {scale!r}")

    samplers, sampler_qc = prepare_subject_samplers(
        records=records,
        stim_rows=stim_rows,
        derivatives_root=derivatives_root,
        repo_root=asset_root,
        matlab_bin=matlab_bin,
        preprocess_dir=preprocess_dir,
        force_flip=args.force_flip,
    )
    x, fiber_ids, sidecar_qc = load_or_build_exposure(
        data_mat,
        records,
        samplers,
        preprocess_dir,
        max_fibers=args.max_fibers,
        fiber_chunk_size=args.fiber_chunk_size,
        force_rebuild=args.force_rebuild,
    )
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    score_rows, fold_rows, qc, coverage, rho, weights = run_observed_loocv(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        y_base=y_base,
        subject_ids=subject_ids,
        scale_direction=scale_direction,
        tau=args.tau,
        min_coverage=args.min_coverage,
    )

    candidate = candidate_mask_from_coverage(coverage, args.min_coverage)
    weight_rows: list[dict[str, Any]] = []
    for col in np.where(candidate)[0]:
        weight_rows.append(
            {
                "fiber_id": int(fiber_ids[col]),
                "coverage_tau800": int(coverage[col]),
                "rho_HF": float(rho[col]) if np.isfinite(rho[col]) else "",
                "M_HF": float(weights[col]) if np.isfinite(weights[col]) else "",
                "is_candidate": True,
            }
        )

    np.save(preprocess_dir / "coverage_tau800.npy", coverage.astype(np.int16))
    np.save(preprocess_dir / "rho_HF_float32.npy", rho.astype(np.float32))
    np.save(preprocess_dir / "M_HF_float32.npy", weights.astype(np.float32))
    write_csv(
        branch_dir / "normative_HF_fiber_weights.csv",
        weight_rows,
        ["fiber_id", "coverage_tau800", "rho_HF", "M_HF", "is_candidate"],
    )
    write_csv(
        branch_dir / "normative_HF_fiber_scores.csv",
        score_rows,
        [
            "subject_id",
            "Y_post",
            "Y_base",
            "SweetPeak5",
            "SourPeak5",
            "NetFiberScore",
            "n_sweet_selected_fibers",
            "n_sour_selected_fibers",
            "n_sweet_peak_fibers",
            "n_sour_peak_fibers",
            "score_map_source",
            "is_primary_score",
        ],
    )
    write_csv(
        branch_dir / "normative_HF_fiber_loocv_predictions.csv",
        fold_rows,
        [
            "fold_id",
            "heldout_subject_id",
            "Y_post",
            "Y_base",
            "SweetPeak5_LOOCV",
            "SourPeak5_LOOCV",
            "NetFiberScore_LOOCV",
            "prediction_NetFiberScore_model",
            "prediction_baseline_only",
            "residual_NetFiberScore_model",
            "residual_baseline_only",
            "n_train",
            "n_candidate_fibers",
            "n_sweet_selected_fibers",
            "n_sour_selected_fibers",
            "delta",
            "beta_Y_base",
            "baseline_beta_Y_base",
        ],
    )

    qc.update(
        {
            "scale": scale,
            "scale_direction": scale_direction,
            "scale_direction_source": scale_direction_source,
            "connectome": connectome_info["label"],
            "connectome_slug": connectome_slug,
            "max_fibers": int(args.max_fibers),
            "sampler_qc": sampler_qc,
            "sidecar_qc": sidecar_qc,
        }
    )
    manifest = {
        "generated_at": iso_now(),
        "model": "HF normative connectome fiber",
        "branch": "peak_efield_tau800_primary",
        "status": "PASS",
        "repo_root": str(repo_root),
        "asset_root": str(asset_root),
        "clinical_root": str(clinical_root),
        "derivatives_root": str(derivatives_root),
        "connectome": connectome_info["label"],
        "data_mat": str(data_mat),
        "output_root": str(output_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        },
        "parameters": {
            "scale": scale,
            "tau_v_per_m": args.tau,
            "min_coverage": args.min_coverage,
            "max_fibers": int(args.max_fibers),
            "fiber_chunk_size": int(args.fiber_chunk_size),
            "random_seed": 42,
        },
        "outputs": {
            "preprocess_dir": str(preprocess_dir),
            "weights_csv": str(branch_dir / "normative_HF_fiber_weights.csv"),
            "scores_csv": str(branch_dir / "normative_HF_fiber_scores.csv"),
            "loocv_predictions_csv": str(branch_dir / "normative_HF_fiber_loocv_predictions.csv"),
            "mapping_qc_json": str(branch_dir / "normative_HF_fiber_mapping_qc.json"),
            "generation_manifest_json": str(branch_dir / "normative_HF_fiber_generation_manifest.json"),
        },
        "runtime_profile": {
            "total_s": time.time() - started,
            "n_fibers": int(x.shape[1]),
            "n_candidate_fibers": int(qc["n_candidate_fibers"]),
        },
    }
    write_json(branch_dir / "normative_HF_fiber_mapping_qc.json", qc)
    write_json(branch_dir / "normative_HF_fiber_generation_manifest.json", manifest)
    print(f"HF normative fiber smoke output: {branch_dir}")
    print(f"LOOCV Spearman rho: {qc['loocv_metrics']['spearman_rho']:.6g}")
    print(f"LOOCV Q2: {qc['loocv_metrics']['q2']:.6g}")
    print(f"Fibers: {x.shape[1]}; candidate fibers: {qc['n_candidate_fibers']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default=str(DEFAULT_CANONICAL_ASSET_ROOT), help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_VAL_ROOT / "summary/normative_connectome_fiber/hf"), help="HF normative fiber output root.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--scale", default=HF_DEFAULT_SCALES[0], help="Raw clinical scale to run.")
    parser.add_argument("--connectome", choices=sorted(CONNECTOMES), default="ppmi", help="Public connectome to process.")
    parser.add_argument("--tau", type=float, default=800.0, help="Primary fiber inclusion threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Minimum subject coverage.")
    parser.add_argument("--fiber-chunk-size", type=int, default=10000, help="Number of fibers per sampling chunk.")
    parser.add_argument("--max-fibers", type=int, default=0, help="Development-only cap; 0 means full connectome.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    parser.add_argument("--force-rebuild", action="store_true", help="Regenerate exposure sidecar even if present.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_hf_normative_fiber_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
