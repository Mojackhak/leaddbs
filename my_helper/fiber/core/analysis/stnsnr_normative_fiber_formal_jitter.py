#!/usr/bin/env python3
"""Spatial jitter QC for dTOR normative-fiber final models."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

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
        if np.any(np.isfinite(jitter_weights)):
            finite_jitter_count += 1
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
