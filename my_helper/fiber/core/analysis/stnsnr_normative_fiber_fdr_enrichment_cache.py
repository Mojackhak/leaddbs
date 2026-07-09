#!/usr/bin/env python3
"""Generate FDR and enrichment caches for final STN/SNr normative-fiber targets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import nibabel as nib
import numpy as np
from scipy.stats import fisher_exact

from stnsnr_four_model_final_reporting import FORMAL_ROOT
from stnsnr_four_model_readiness import DEFAULT_CANONICAL_ASSET_ROOT
from stnsnr_four_model_stats import average_rank_1d, freedman_lane_permuted_outcomes, rank_columns, residualize
from stnsnr_io import iso_now, read_csv, read_json, write_csv, write_json
from stnsnr_normative_fiber_density_cache import fiber_offsets, unique_inside_voxels


FDR_FIELDS = [
    "model_id",
    "endpoint_slug",
    "connectome",
    "branch",
    "fiber_id",
    "selected_tau",
    "selected_coverage",
    "nuisance_model",
    "rho_observed",
    "benefit_oriented_effect",
    "p_raw_two_sided",
    "q_bh_fdr",
    "n_permutations",
    "seed",
    "tested_fiber_universe_hash",
    "source_manifest_hash",
]
ENRICHMENT_FIELDS = [
    "model_id",
    "endpoint_slug",
    "connectome",
    "branch",
    "foreground_family",
    "foreground_definition",
    "background_definition",
    "region_label",
    "n_foreground",
    "n_background",
    "foreground_in_region",
    "foreground_outside_region",
    "background_nonforeground_in_region",
    "background_nonforeground_outside_region",
    "odds_ratio",
    "enrichment_ratio",
    "p_fisher_greater",
    "q_bh_fdr",
    "label_cache_hash",
    "fdr_cache_hash",
]
SUMMARY_FIELDS = [
    "model_id",
    "branch_dir",
    "fdr_cache_status",
    "enrichment_cache_status",
    "n_tested_fibers",
    "n_permutations",
    "n_confirmatory_sweet",
    "n_confirmatory_sour",
    "fdr_cache_csv",
    "fdr_cache_manifest_json",
    "enrichment_cache_csv",
    "enrichment_cache_manifest_json",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_int_array(values: np.ndarray) -> str:
    arr = np.asarray(values, dtype=np.int64)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def bh_fdr(p_values: np.ndarray) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    q = np.full(p.shape, np.nan, dtype=float)
    finite = np.isfinite(p)
    if not np.any(finite):
        return q
    finite_p = p[finite]
    order = np.argsort(finite_p, kind="mergesort")
    ranked = finite_p[order]
    m = ranked.size
    adjusted = ranked * m / np.arange(1, m + 1, dtype=float)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    restored = np.empty_like(adjusted)
    restored[order] = adjusted
    q[finite] = restored
    return q


def _correlate_residualized(y_resid: np.ndarray, x_resid: np.ndarray, x_norm: np.ndarray) -> np.ndarray:
    y = np.asarray(y_resid, dtype=float)
    y = y - np.nanmean(y)
    denom_y = float(np.sqrt(np.nansum(y * y)))
    out = np.full(x_resid.shape[1], np.nan, dtype=float)
    valid = denom_y > 0
    if not valid:
        return out
    denom = denom_y * x_norm
    nonzero = denom > 0
    out[nonzero] = (y @ x_resid[:, nonzero]) / denom[nonzero]
    return out


def partial_spearman_precomputed(
    *,
    y: np.ndarray,
    x_resid: np.ndarray,
    x_norm: np.ndarray,
    cov_rank: np.ndarray,
) -> np.ndarray:
    y_rank = average_rank_1d(np.asarray(y, dtype=float))
    y_resid = residualize(y_rank, cov_rank if cov_rank.shape[1] else None)
    return _correlate_residualized(y_resid, x_resid, x_norm)


def precompute_rank_residualized_exposure(x: np.ndarray, covariates: np.ndarray | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cov = np.empty((x.shape[0], 0), dtype=float) if covariates is None else np.asarray(covariates, dtype=float)
    if cov.ndim == 1:
        cov = cov[:, None]
    cov_rank = rank_columns(cov) if cov.shape[1] else cov
    x_rank = rank_columns(np.asarray(x, dtype=float))
    x_resid = residualize(x_rank, cov_rank if cov_rank.shape[1] else None)
    x_resid = x_resid - np.nanmean(x_resid, axis=0)
    x_norm = np.sqrt(np.nansum(x_resid * x_resid, axis=0))
    return x_resid, x_norm, cov_rank


def candidate_weights(weights_csv: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = read_csv(Path(weights_csv))
    ids: list[int] = []
    weights: list[float] = []
    for row in rows:
        if str(row.get("is_candidate", "")).lower() not in {"true", "1", "yes"}:
            continue
        weight_text = row.get("M_HF", "") or row.get("M_ULF", "")
        if not row.get("fiber_id") or not weight_text:
            continue
        try:
            fiber_id = int(float(row["fiber_id"]))
            weight = float(weight_text)
        except ValueError:
            continue
        if np.isfinite(weight):
            ids.append(fiber_id)
            weights.append(weight)
    if not ids:
        raise RuntimeError(f"no candidate fiber rows found in {weights_csv}")
    return np.asarray(ids, dtype=np.int64), np.asarray(weights, dtype=float)


def load_scores(scores_csv: Path, model_id: str, branch: str) -> tuple[np.ndarray, np.ndarray, str]:
    rows = read_csv(Path(scores_csv))
    if not rows:
        raise RuntimeError(f"no score rows found in {scores_csv}")
    y = np.asarray([float(row["Y_post"]) for row in rows], dtype=float)
    if model_id.startswith("B_"):
        nuisance = np.asarray([float(row["Y_base"]) for row in rows], dtype=float)[:, None]
        return y, nuisance, "Y_post ~ Y_base"
    y_hf_ref = np.asarray([float(row["Y_HF_ref"]) for row in rows], dtype=float)
    if "delta_hf_adjusted" in branch:
        delta = np.asarray([float(row.get("DeltaHFFiberScore") or "nan") for row in rows], dtype=float)
        nuisance = np.column_stack([y_hf_ref, delta])
        return y, nuisance, "Y_post ~ Y_HF_ref + DeltaHFScore"
    return y, y_hf_ref[:, None], "Y_post ~ Y_HF_ref"


def exposure_path_for_target(manifest: dict[str, Any], model_id: str, branch_dir: Path) -> Path:
    if model_id.startswith("B_"):
        preprocess = Path(manifest.get("outputs", {}).get("preprocess_dir", branch_dir / "preprocess"))
        return preprocess / "X_HF_fiber_float32_subject_major.npy"
    parent_preprocess = branch_dir.parent / "preprocess"
    if "delta_hf_adjusted" in branch_dir.name:
        candidate = parent_preprocess / "X_ULF_only_fiber_float32_subject_major.npy"
    else:
        candidate = parent_preprocess / "X_ULF_only_fiber_float32_subject_major.npy"
    return candidate


def fiber_ids_path_for_target(manifest: dict[str, Any], model_id: str, branch_dir: Path) -> Path:
    if model_id.startswith("B_"):
        preprocess = Path(manifest.get("outputs", {}).get("preprocess_dir", branch_dir / "preprocess"))
        return preprocess / "fiber_ids.npy"
    return branch_dir.parent.parent / "peak_efield_tau800_observed" / "preprocess" / "fiber_ids.npy"


def subset_exposure(exposure_path: Path, atlas_fiber_ids_path: Path, candidate_ids: np.ndarray) -> np.ndarray:
    x_full = np.load(exposure_path, mmap_mode="r")
    atlas_ids = np.load(atlas_fiber_ids_path, mmap_mode="r")
    if atlas_ids.shape[0] == x_full.shape[1] and np.array_equal(atlas_ids[:10], np.arange(1, min(11, atlas_ids.shape[0] + 1))):
        return np.asarray(x_full[:, candidate_ids - 1], dtype=np.float64)
    id_to_index = {int(fiber_id): idx for idx, fiber_id in enumerate(np.asarray(atlas_ids, dtype=np.int64))}
    indices = np.asarray([id_to_index[int(fiber_id)] for fiber_id in candidate_ids], dtype=np.int64)
    return np.asarray(x_full[:, indices], dtype=np.float64)


def endpoint_slug_from_manifest_path(path: Path) -> str:
    parts = list(Path(path).parts)
    for idx, part in enumerate(parts):
        if part in {"hf", "ulf"} and idx + 2 < len(parts):
            return parts[idx + 2]
    return Path(path).parent.name


def compute_fdr_rows(
    *,
    model_id: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    branch_dir: Path,
    candidate_ids: np.ndarray,
    effect_weights: np.ndarray,
    x_candidate: np.ndarray,
    y: np.ndarray,
    nuisance: np.ndarray,
    nuisance_model: str,
    n_permutations: int,
    seed: int,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    x_resid, x_norm, cov_rank = precompute_rank_residualized_exposure(x_candidate, nuisance)
    rho_observed = partial_spearman_precomputed(y=y, x_resid=x_resid, x_norm=x_norm, cov_rank=cov_rank)
    counts = np.zeros(rho_observed.shape, dtype=np.int64)
    y_perm = freedman_lane_permuted_outcomes(y, nuisance, n_permutations, seed=seed)
    for idx in range(int(n_permutations)):
        rho_perm = partial_spearman_precomputed(y=y_perm[idx], x_resid=x_resid, x_norm=x_norm, cov_rank=cov_rank)
        counts += np.abs(rho_perm) >= np.abs(rho_observed)
    p_raw = (1.0 + counts.astype(float)) / (float(n_permutations) + 1.0)
    q = bh_fdr(p_raw)
    parameters = manifest.get("parameters", {})
    selected_tau = parameters.get("tau_v_per_m", "")
    selected_coverage = parameters.get("min_coverage", "")
    connectome = manifest.get("connectome_slug") or manifest.get("connectome", "")
    branch = manifest.get("branch") or branch_dir.name
    universe_hash = sha256_int_array(candidate_ids)
    source_hash = sha256_file(manifest_path)
    rows: list[dict[str, Any]] = []
    endpoint_slug = endpoint_slug_from_manifest_path(manifest_path)
    for fiber_id, rho, effect, p_value, q_value in zip(candidate_ids, rho_observed, effect_weights, p_raw, q, strict=True):
        rows.append(
            {
                "model_id": model_id,
                "endpoint_slug": endpoint_slug,
                "connectome": connectome,
                "branch": branch,
                "fiber_id": int(fiber_id),
                "selected_tau": selected_tau,
                "selected_coverage": selected_coverage,
                "nuisance_model": nuisance_model,
                "rho_observed": float(rho) if np.isfinite(rho) else "",
                "benefit_oriented_effect": float(effect) if np.isfinite(effect) else "",
                "p_raw_two_sided": float(p_value) if np.isfinite(p_value) else "",
                "q_bh_fdr": float(q_value) if np.isfinite(q_value) else "",
                "n_permutations": int(n_permutations),
                "seed": int(seed),
                "tested_fiber_universe_hash": universe_hash,
                "source_manifest_hash": source_hash,
            }
        )
    return rows, q


def label_membership(
    *,
    data_mat: Path,
    template_path: Path,
    label_cache_csv: Path,
    candidate_ids: np.ndarray,
) -> tuple[list[dict[str, str]], np.ndarray]:
    label_rows = read_csv(label_cache_csv)
    valid_label_rows = [row for row in label_rows if row.get("mask_path") and Path(row["mask_path"]).is_file()]
    template = nib.load(str(template_path))
    shape = tuple(int(item) for item in template.shape[:3])
    masks: list[np.ndarray] = []
    for row in valid_label_rows:
        mask_img = nib.load(row["mask_path"])
        if tuple(int(item) for item in mask_img.shape[:3]) != shape:
            masks.append(np.zeros(int(np.prod(shape)), dtype=bool))
        else:
            masks.append(np.asarray(mask_img.dataobj).reshape(-1) > 0)
    membership = np.zeros((candidate_ids.size, len(valid_label_rows)), dtype=bool)
    with h5py.File(data_mat, "r") as handle:
        offsets = fiber_offsets(np.asarray(handle["idx"][0, :], dtype=np.int64), [int(item) for item in candidate_ids])
        fibers = handle["fibers"]
        for row_idx, fiber_id in enumerate(candidate_ids):
            if int(fiber_id) not in offsets:
                continue
            start, stop = offsets[int(fiber_id)]
            xyz = np.asarray(fibers[0:3, start:stop], dtype=np.float32).T
            flat = unique_inside_voxels(xyz, template)
            if flat.size == 0:
                continue
            for label_idx, mask in enumerate(masks):
                membership[row_idx, label_idx] = bool(np.any(mask[flat]))
    return valid_label_rows, membership


def top_display_mask(effect_weights: np.ndarray, positive: bool) -> np.ndarray:
    weights = np.asarray(effect_weights, dtype=float)
    mask = weights > 0 if positive else weights < 0
    indices = np.flatnonzero(mask)
    out = np.zeros(weights.shape, dtype=bool)
    if indices.size == 0:
        return out
    percent = 0.01 if positive else 0.005
    count = max(1, int(np.ceil(percent * indices.size)))
    order = np.lexsort((indices, -weights[indices] if positive else weights[indices]))
    out[indices[order[:count]]] = True
    return out


def enrichment_rows_for_target(
    *,
    model_id: str,
    manifest: dict[str, Any],
    manifest_path: Path,
    branch_dir: Path,
    candidate_ids: np.ndarray,
    effect_weights: np.ndarray,
    q_values: np.ndarray,
    fdr_cache_csv: Path,
) -> list[dict[str, Any]]:
    label_cache_csv = branch_dir / ("normative_HF_fiber_label_cache.csv" if model_id.startswith("B_") else "normative_ULF_fiber_label_cache.csv")
    if not label_cache_csv.is_file():
        return []
    data_mat = Path(manifest.get("data_mat", ""))
    asset_root = Path(manifest.get("asset_root", DEFAULT_CANONICAL_ASSET_ROOT))
    template_path = asset_root / "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz"
    if not data_mat.is_file() or not template_path.is_file():
        return []
    label_rows, membership = label_membership(
        data_mat=data_mat,
        template_path=template_path,
        label_cache_csv=label_cache_csv,
        candidate_ids=candidate_ids,
    )
    foregrounds = {
        "confirmatory_sweet": (q_values <= 0.05) & (effect_weights > 0),
        "confirmatory_sour": (q_values <= 0.05) & (effect_weights < 0),
        "display_only_not_confirmatory_sweet": top_display_mask(effect_weights, positive=True),
        "display_only_not_confirmatory_sour": top_display_mask(effect_weights, positive=False),
    }
    parameters = manifest.get("parameters", {})
    connectome = manifest.get("connectome_slug") or manifest.get("connectome", "")
    branch = manifest.get("branch") or branch_dir.name
    endpoint_slug = endpoint_slug_from_manifest_path(manifest_path)
    background_definition = "all tested candidate fibers in the selected final branch"
    rows: list[dict[str, Any]] = []
    for foreground_family, foreground_mask in foregrounds.items():
        p_values: list[float] = []
        interim: list[dict[str, Any]] = []
        n_foreground = int(np.count_nonzero(foreground_mask))
        n_background = int(candidate_ids.size)
        for label_idx, label_row in enumerate(label_rows):
            in_region = membership[:, label_idx]
            fg_in = int(np.count_nonzero(foreground_mask & in_region))
            fg_out = int(np.count_nonzero(foreground_mask & ~in_region))
            bg_nonfg_in = int(np.count_nonzero(~foreground_mask & in_region))
            bg_nonfg_out = int(np.count_nonzero(~foreground_mask & ~in_region))
            if n_foreground == 0:
                odds_ratio = np.nan
                p_value = 1.0
            else:
                odds_ratio, p_value = fisher_exact([[fg_in, fg_out], [bg_nonfg_in, bg_nonfg_out]], alternative="greater")
            background_in_region = fg_in + bg_nonfg_in
            foreground_fraction = fg_in / n_foreground if n_foreground else 0.0
            background_fraction = background_in_region / n_background if n_background else 0.0
            enrichment_ratio = foreground_fraction / background_fraction if background_fraction > 0 else np.nan
            region_label = "|".join(
                [
                    str(label_row.get("atlas_name", "")),
                    str(label_row.get("roi_name", "")),
                    str(label_row.get("side", "")),
                    str(label_row.get("role", "")),
                ]
            )
            interim.append(
                {
                    "model_id": model_id,
                    "endpoint_slug": endpoint_slug,
                    "connectome": connectome,
                    "branch": branch,
                    "foreground_family": foreground_family,
                    "foreground_definition": foreground_family,
                    "background_definition": background_definition,
                    "region_label": region_label,
                    "n_foreground": n_foreground,
                    "n_background": n_background,
                    "foreground_in_region": fg_in,
                    "foreground_outside_region": fg_out,
                    "background_nonforeground_in_region": bg_nonfg_in,
                    "background_nonforeground_outside_region": bg_nonfg_out,
                    "odds_ratio": float(odds_ratio) if np.isfinite(odds_ratio) else "",
                    "enrichment_ratio": float(enrichment_ratio) if np.isfinite(enrichment_ratio) else "",
                    "p_fisher_greater": float(p_value),
                    "label_cache_hash": sha256_file(label_cache_csv),
                    "fdr_cache_hash": sha256_file(fdr_cache_csv),
                }
            )
            p_values.append(float(p_value))
        q_values_region = bh_fdr(np.asarray(p_values, dtype=float))
        for row, q_value in zip(interim, q_values_region, strict=True):
            row["q_bh_fdr"] = float(q_value) if np.isfinite(q_value) else ""
            rows.append(row)
    return rows


def process_target(row: dict[str, str], *, n_permutations: int, seed: int) -> dict[str, Any]:
    model_id = row["model_id"]
    manifest_path = Path(row["latest_manifest"])
    manifest = read_json(manifest_path)
    branch_dir = Path(manifest.get("outputs", {}).get("branch_dir") or manifest.get("output_root") or manifest_path.parent)
    weights_csv = Path(manifest.get("outputs", {}).get("weights_csv", branch_dir / "weights.csv"))
    scores_csv = Path(manifest.get("outputs", {}).get("scores_csv", branch_dir / "scores.csv"))
    candidate_ids, effect_weights = candidate_weights(weights_csv)
    exposure_path = exposure_path_for_target(manifest, model_id, branch_dir)
    fiber_ids_path = fiber_ids_path_for_target(manifest, model_id, branch_dir)
    x_candidate = subset_exposure(exposure_path, fiber_ids_path, candidate_ids)
    y, nuisance, nuisance_model = load_scores(scores_csv, model_id, branch_dir.name)
    fdr_rows, q_values = compute_fdr_rows(
        model_id=model_id,
        manifest_path=manifest_path,
        manifest=manifest,
        branch_dir=branch_dir,
        candidate_ids=candidate_ids,
        effect_weights=effect_weights,
        x_candidate=x_candidate,
        y=y,
        nuisance=nuisance,
        nuisance_model=nuisance_model,
        n_permutations=n_permutations,
        seed=seed,
    )
    prefix = "normative_HF" if model_id.startswith("B_") else "normative_ULF"
    fdr_csv = branch_dir / f"{prefix}_fiber_fdr_cache.csv"
    fdr_manifest = branch_dir / f"{prefix}_fiber_fdr_cache_manifest.json"
    write_csv(fdr_csv, fdr_rows, FDR_FIELDS)
    write_json(
        fdr_manifest,
        {
            "generated_at": iso_now(),
            "model_id": model_id,
            "endpoint_slug": endpoint_slug_from_manifest_path(manifest_path),
            "connectome": manifest.get("connectome_slug") or manifest.get("connectome", ""),
            "branch": manifest.get("branch") or branch_dir.name,
            "selected_tau": manifest.get("parameters", {}).get("tau_v_per_m", ""),
            "selected_coverage": manifest.get("parameters", {}).get("min_coverage", ""),
            "n_subjects": int(x_candidate.shape[0]),
            "n_tested_fibers": int(candidate_ids.size),
            "n_permutations": int(n_permutations),
            "seed": int(seed),
            "nuisance_model": nuisance_model,
            "permutation_method": "patient_level_freedman_lane",
            "p_value_method": "plus_one_two_sided",
            "fdr_method": "benjamini_hochberg_within_model_endpoint_connectome_branch_universe",
            "tested_fiber_universe_hash": sha256_int_array(candidate_ids),
            "input_manifest_hashes": {"source_manifest_hash": sha256_file(manifest_path)},
            "outputs": {"fdr_cache_csv": str(fdr_csv), "fdr_cache_manifest_json": str(fdr_manifest)},
        },
        add_code_provenance=True,
    )
    enrichment_rows = enrichment_rows_for_target(
        model_id=model_id,
        manifest=manifest,
        manifest_path=manifest_path,
        branch_dir=branch_dir,
        candidate_ids=candidate_ids,
        effect_weights=effect_weights,
        q_values=q_values,
        fdr_cache_csv=fdr_csv,
    )
    enrichment_csv = branch_dir / f"{prefix}_fiber_enrichment_cache.csv"
    enrichment_manifest = branch_dir / f"{prefix}_fiber_enrichment_cache_manifest.json"
    write_csv(enrichment_csv, enrichment_rows, ENRICHMENT_FIELDS)
    write_json(
        enrichment_manifest,
        {
            "generated_at": iso_now(),
            "model_id": model_id,
            "endpoint_slug": endpoint_slug_from_manifest_path(manifest_path),
            "connectome": manifest.get("connectome_slug") or manifest.get("connectome", ""),
            "branch": manifest.get("branch") or branch_dir.name,
            "foreground_families": sorted({item["foreground_family"] for item in enrichment_rows}),
            "background_definition": "all tested candidate fibers in the selected final branch",
            "n_background": int(candidate_ids.size),
            "label_source": str(branch_dir / f"{prefix}_fiber_label_cache.csv"),
            "label_cache_hash": sha256_file(branch_dir / f"{prefix}_fiber_label_cache.csv") if (branch_dir / f"{prefix}_fiber_label_cache.csv").is_file() else "",
            "fdr_cache_hash": sha256_file(fdr_csv),
            "fdr_threshold": 0.05,
            "test_method": "one_sided_fisher_exact_greater",
            "fdr_method": "benjamini_hochberg_within_model_endpoint_branch_foreground_family",
            "outputs": {
                "enrichment_cache_csv": str(enrichment_csv),
                "enrichment_cache_manifest_json": str(enrichment_manifest),
            },
        },
        add_code_provenance=True,
    )
    return {
        "model_id": model_id,
        "branch_dir": str(branch_dir),
        "fdr_cache_status": "complete",
        "enrichment_cache_status": "complete" if enrichment_rows else "complete_empty_no_label_rows",
        "n_tested_fibers": int(candidate_ids.size),
        "n_permutations": int(n_permutations),
        "n_confirmatory_sweet": int(np.count_nonzero((q_values <= 0.05) & (effect_weights > 0))),
        "n_confirmatory_sour": int(np.count_nonzero((q_values <= 0.05) & (effect_weights < 0))),
        "fdr_cache_csv": str(fdr_csv),
        "fdr_cache_manifest_json": str(fdr_manifest),
        "enrichment_cache_csv": str(enrichment_csv),
        "enrichment_cache_manifest_json": str(enrichment_manifest),
    }


def target_rows(final_report_csv: Path, include_observed: bool) -> list[dict[str, str]]:
    rows = read_csv(final_report_csv)
    targets = []
    for row in rows:
        if row.get("analysis_family") != "normative_fiber":
            continue
        if not row.get("latest_manifest"):
            continue
        if include_observed or row.get("formal_target_status") == "READY_FOR_FORMAL_RESAMPLING":
            targets.append(row)
    return targets


def run_cache_generation(args: argparse.Namespace) -> int:
    final_report_csv = Path(args.final_report_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    rows = target_rows(final_report_csv, include_observed=args.include_observed)
    if not rows:
        raise RuntimeError("no normative-fiber target rows found")
    summary_rows = []
    for row in rows:
        print(f"Generating normative-fiber FDR/enrichment cache for {row['model_id']}", flush=True)
        summary_rows.append(process_target(row, n_permutations=args.n_permutations, seed=args.seed))
    summary_csv = output_dir / "normative_fiber_fdr_enrichment_cache_summary.csv"
    manifest_json = output_dir / "normative_fiber_fdr_enrichment_cache_manifest.json"
    write_csv(summary_csv, summary_rows, SUMMARY_FIELDS)
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "final_report_csv": str(final_report_csv),
            "include_observed": bool(args.include_observed),
            "n_rows": len(summary_rows),
            "n_permutations": int(args.n_permutations),
            "seed": int(args.seed),
            "outputs": {
                "summary_csv": str(summary_csv),
                "manifest_json": str(manifest_json),
            },
        },
        add_code_provenance=True,
    )
    print(f"Normative-fiber FDR/enrichment cache summary: {summary_csv}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-report-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_final_report.csv"),
        help="Final report CSV used to locate final normative-fiber targets.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "normative_fiber_fdr_enrichment_cache"),
        help="Cross-target FDR/enrichment cache summary directory.",
    )
    parser.add_argument("--n-permutations", type=int, default=10000, help="Number of Freedman-Lane permutations.")
    parser.add_argument("--seed", type=int, default=42, help="Permutation seed.")
    parser.add_argument(
        "--include-observed",
        action="store_true",
        help="Also generate caches for observed robustness normative-fiber rows.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_cache_generation(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
