#!/usr/bin/env python3
"""Post-hoc tau/coverage threshold scan for the HF direct voxel model."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

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
    fit_linear_prediction,
    mean_map_score,
    partial_spearman_matrix,
    suprathreshold_matrix,
)
from stnsnr_hf_direct_voxel_smoke import (
    build_exposure_matrix,
    collect_side_field_paths,
    filter_hf_stn_rows,
    fit_baseline_only,
    flip_left_fields_with_matlab,
    load_stim_table,
    load_subject_records,
    right_brainmask_voxels,
    slugify,
    write_csv,
    write_json,
)


TAU_GRID = [100, 150, 180, 200, 220, 250, 300, 350, 400, 500]
COVERAGE_GRID = [5, 6, 7, 8, 10, 12]
PRIMARY_TAU = 200
PRIMARY_COVERAGE = 5
POSTHOC_CANDIDATE_THRESHOLD = 100.0
SHARED_PREPROCESS_RELATIVE = Path("_shared/posthoc_threshold_scan/preprocess_candidate_tau100")
ANNOTATED_RHO_REQUIRED_COLUMNS = [
    "tau",
    "coverage",
    "loocv_spearman_rho",
    "loocv_spearman_nominal_p",
    "passes_all_hard_filters",
]


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass"}
    return bool(value)


def _finite_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def safe_pearson(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 3:
        return math.nan, math.nan
    if np.nanstd(x[finite]) == 0 or np.nanstd(y[finite]) == 0:
        return math.nan, math.nan
    stat = pearsonr(x[finite], y[finite])
    return float(stat.statistic), float(stat.pvalue)


def safe_spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 3:
        return math.nan, math.nan
    if np.nanstd(x[finite]) == 0 or np.nanstd(y[finite]) == 0:
        return math.nan, math.nan
    stat = spearmanr(x[finite], y[finite])
    return float(stat.statistic), float(stat.pvalue)


def row_passes_hard_filters(row: dict[str, Any]) -> bool:
    """Return whether one grid cell passes the locked post-hoc stability filter."""
    return (
        _finite_float(row.get("n_voxels_full")) >= 20
        and _finite_float(row.get("fold_n_voxels_min")) >= 10
        and _as_bool(row.get("hfscore_nonconstant_all_folds"))
        and _as_bool(row.get("all_predictions_finite"))
        and _finite_float(row.get("q2")) > 0
        and _finite_float(row.get("loocv_spearman_rho")) > 0
        and _finite_float(row.get("mae_model")) < _finite_float(row.get("mae_baseline"))
        and _finite_float(row.get("rmse_model")) < _finite_float(row.get("rmse_baseline"))
    )


def _primary_distance(row: dict[str, Any]) -> tuple[float, float]:
    return (abs(_finite_float(row.get("tau")) - PRIMARY_TAU), abs(_finite_float(row.get("coverage")) - PRIMARY_COVERAGE))


def select_best_grid_cell(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the best exploratory grid cell among rows passing all hard filters."""
    eligible = [row for row in rows if row_passes_hard_filters(row)]
    if not eligible:
        return None

    def sort_key(row: dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
        tau_distance, coverage_distance = _primary_distance(row)
        return (
            -_finite_float(row.get("q2")),
            -_finite_float(row.get("loocv_spearman_rho")),
            -_finite_float(row.get("fold_n_voxels_min")),
            tau_distance,
            coverage_distance,
            -_finite_float(row.get("coverage")),
            -_finite_float(row.get("tau")),
        )

    return sorted(eligible, key=sort_key)[0]


def build_heatmap(rows: list[dict[str, Any]], value_column: str) -> pd.DataFrame:
    """Build a tau-by-coverage heatmap table for one result column."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    heatmap = frame.pivot(index="tau", columns="coverage", values=value_column)
    heatmap = heatmap.reindex(index=sorted(frame["tau"].unique()), columns=sorted(frame["coverage"].unique()))
    heatmap.index.name = "tau"
    heatmap.columns.name = "coverage"
    return heatmap


def scale_names_from_raw_dataframe(raw_df: pd.DataFrame) -> list[str]:
    """Return STN 3m endpoint names in first-seen raw scale order."""
    required = {"Scale", "Protocol", "Phase"}
    missing = sorted(required.difference(raw_df.columns))
    if missing:
        raise ValueError("raw clinical dataframe is missing " + ", ".join(missing))
    subset = raw_df[
        raw_df["Protocol"].astype(str).eq("STN")
        & raw_df["Phase"].astype(str).eq("3m")
    ]
    return [f"{scale} (STN, 3 m)" for scale in subset["Scale"].dropna().drop_duplicates().astype(str).tolist()]


def load_all_scale_names(clinical_root: Path) -> list[str]:
    """Load all scale names from the raw clinical workbook."""
    raw_path = clinical_root / "subject_effect_origin.xlsx"
    return scale_names_from_raw_dataframe(pd.read_excel(raw_path))


def endpoint_family_for_scale(scale: str) -> str:
    """Classify a scale for all-scale HF direct voxel summaries."""
    scale_text = str(scale)
    if "(STN+SNr, immediate)" in scale_text:
        return "raw_stnplus_snr_immediate"
    if "(STN, immediate)" in scale_text:
        return "raw_stn_immediate"
    if "(STN+SNr, 3 m)" in scale_text:
        return "raw_stnplus_snr_3m"
    if "(STN, 3 m)" in scale_text:
        return "hf_stn3m"
    return "hf_stn3m"


def build_all_scale_long_table(per_scale_results: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the all-scale long table from per-scale grid rows."""
    rows: list[dict[str, Any]] = []
    for result in per_scale_results:
        selected = result.get("selected") or {}
        selected_tau = selected.get("tau")
        selected_coverage = selected.get("coverage")
        for row in result["rows"]:
            out = dict(row)
            out.update(
                {
                    "scale": result["scale"],
                    "scale_slug": result["scale_slug"],
                    "scale_direction": result["scale_direction"],
                    "endpoint_family": endpoint_family_for_scale(result["scale"]),
                    "n_subjects": result["n_subjects"],
                    "n_candidate_voxels": result["n_candidate_voxels"],
                    "is_selected_grid_cell": bool(
                        selected_tau is not None
                        and selected_coverage is not None
                        and int(row["tau"]) == int(selected_tau)
                        and int(row["coverage"]) == int(selected_coverage)
                    ),
                }
            )
            rows.append(out)
    return pd.DataFrame(rows)


def build_all_scale_summary_table(per_scale_results: list[dict[str, Any]]) -> pd.DataFrame:
    """Build one summary row per scale."""
    rows: list[dict[str, Any]] = []
    for result in per_scale_results:
        grid_rows = result["rows"]
        selected = result.get("selected")
        n_passing = int(sum(_as_bool(row.get("passes_all_hard_filters")) for row in grid_rows))
        row = {
            "scale": result["scale"],
            "scale_slug": result["scale_slug"],
            "scale_direction": result["scale_direction"],
            "endpoint_family": endpoint_family_for_scale(result["scale"]),
            "n_subjects": result["n_subjects"],
            "n_candidate_voxels": result["n_candidate_voxels"],
            "n_grid_cells": len(grid_rows),
            "n_passing_grid_cells": n_passing,
            "has_selected_grid_cell": selected is not None,
            "selected_tau": np.nan,
            "selected_coverage": np.nan,
            "selected_loocv_spearman_rho": np.nan,
            "selected_loocv_spearman_nominal_p": np.nan,
            "selected_loocv_pearson_r": np.nan,
            "selected_q2": np.nan,
            "selected_n_voxels_full": np.nan,
            "selected_fold_n_voxels_min": np.nan,
            "selected_fold_n_voxels_median": np.nan,
            "selected_fold_n_voxels_max": np.nan,
        }
        if selected is not None:
            row.update(
                {
                    "selected_tau": selected.get("tau", np.nan),
                    "selected_coverage": selected.get("coverage", np.nan),
                    "selected_loocv_spearman_rho": selected.get("loocv_spearman_rho", np.nan),
                    "selected_loocv_spearman_nominal_p": selected.get("loocv_spearman_nominal_p", np.nan),
                    "selected_loocv_pearson_r": selected.get("loocv_pearson_r", np.nan),
                    "selected_q2": selected.get("q2", np.nan),
                    "selected_n_voxels_full": selected.get("n_voxels_full", np.nan),
                    "selected_fold_n_voxels_min": selected.get("fold_n_voxels_min", np.nan),
                    "selected_fold_n_voxels_median": selected.get("fold_n_voxels_median", np.nan),
                    "selected_fold_n_voxels_max": selected.get("fold_n_voxels_max", np.nan),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def significance_stars(p_value: float) -> str:
    """Return nominal-p significance stars for annotated heatmaps."""
    p = _finite_float(p_value)
    if not np.isfinite(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def validate_annotated_rho_input(rows: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """Validate and return rows needed to draw the annotated rho heatmap."""
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    missing = [column for column in ANNOTATED_RHO_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("annotated rho heatmap input is missing columns: " + ", ".join(missing))
    return frame


def grid_cell_position(
    tau: int | float,
    coverage: int | float,
    tau_order: list[int] | None = None,
    coverage_order: list[int] | None = None,
) -> tuple[int, int]:
    """Return zero-based x/y cell coordinates for a tau/coverage grid cell."""
    tau_values = TAU_GRID if tau_order is None else tau_order
    coverage_values = COVERAGE_GRID if coverage_order is None else coverage_order
    tau_int = int(tau)
    coverage_int = int(coverage)
    if tau_int not in tau_values:
        raise ValueError(f"tau {tau_int} is not in the heatmap tau grid")
    if coverage_int not in coverage_values:
        raise ValueError(f"coverage {coverage_int} is not in the heatmap coverage grid")
    return tau_values.index(tau_int), coverage_values.index(coverage_int)


def build_annotated_rho_source(
    rows: list[dict[str, Any]] | pd.DataFrame,
    *,
    selected_tau: int | float | None,
    selected_coverage: int | float | None,
) -> pd.DataFrame:
    """Build source data for the annotated rho heatmap."""
    frame = validate_annotated_rho_input(rows).copy()
    frame["tau"] = frame["tau"].astype(int)
    frame["coverage"] = frame["coverage"].astype(int)
    frame["rho"] = pd.to_numeric(frame["loocv_spearman_rho"], errors="coerce")
    frame["nominal_p"] = pd.to_numeric(frame["loocv_spearman_nominal_p"], errors="coerce")
    frame["stars"] = frame["nominal_p"].map(significance_stars)
    frame["cell_label"] = frame.apply(
        lambda row: "" if not np.isfinite(row["rho"]) else f"{row['rho']:.2f}" + (f"\n{row['stars']}" if row["stars"] else ""),
        axis=1,
    )
    frame["passes_all_hard_filters"] = frame["passes_all_hard_filters"].map(_as_bool)
    frame["is_primary_branch"] = (frame["tau"] == PRIMARY_TAU) & (frame["coverage"] == PRIMARY_COVERAGE)
    if selected_tau is None or selected_coverage is None:
        frame["is_selected_branch"] = False
    else:
        frame["is_selected_branch"] = (frame["tau"] == int(selected_tau)) & (frame["coverage"] == int(selected_coverage))
    columns = [
        "tau",
        "coverage",
        "rho",
        "nominal_p",
        "stars",
        "cell_label",
        "passes_all_hard_filters",
        "is_primary_branch",
        "is_selected_branch",
    ]
    return frame.sort_values(["coverage", "tau"])[columns]


def _pivot_annotated_source(source: pd.DataFrame, value_column: str) -> pd.DataFrame:
    heatmap = source.pivot(index="coverage", columns="tau", values=value_column)
    return heatmap.reindex(index=COVERAGE_GRID, columns=TAU_GRID)


def write_annotated_rho_heatmap(scan_dir: Path) -> dict[str, Any]:
    """Render the post-hoc rho heatmap with nominal-p stars and branch outlines."""
    results_path = scan_dir / "posthoc_threshold_scan_results.csv"
    manifest_path = scan_dir / "posthoc_selected_threshold_manifest.json"
    if not results_path.is_file():
        raise FileNotFoundError(f"missing post-hoc scan results: {results_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing selected threshold manifest: {manifest_path}")

    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    selected = manifest.get("selected_grid_cell") or {}
    source = build_annotated_rho_source(
        pd.read_csv(results_path),
        selected_tau=selected.get("tau"),
        selected_coverage=selected.get("coverage"),
    )
    source_path = scan_dir / "posthoc_threshold_scan_heatmap_rho_annotated_source.csv"
    source.to_csv(source_path, index=False)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        from matplotlib.colors import TwoSlopeNorm
        from matplotlib.patches import Rectangle
    except Exception as exc:  # pragma: no cover - optional plotting dependency
        return {"status": "SKIPPED", "reason": str(exc), "source_csv": str(source_path)}

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.linewidth": 0.8,
            "axes.spines.right": False,
            "axes.spines.top": False,
        }
    )
    rho_grid = _pivot_annotated_source(source, "rho").astype(float)
    label_grid = _pivot_annotated_source(source, "cell_label")
    pass_grid = _pivot_annotated_source(source, "passes_all_hard_filters").fillna(False).astype(bool)
    values = rho_grid.to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    max_abs = float(np.max(np.abs(finite_values))) if finite_values.size else 1.0
    max_abs = max(max_abs, 0.1)

    fig, ax = plt.subplots(figsize=(7.2, 4.45))
    fig.subplots_adjust(left=0.08, right=0.88, bottom=0.2, top=0.9)
    norm = TwoSlopeNorm(vcenter=0.0, vmin=-max_abs, vmax=max_abs)
    image = ax.imshow(values, cmap="RdBu_r", norm=norm, aspect="auto")
    ax.set_xlabel("E-field threshold tau (V/m)")
    ax.set_ylabel("Coverage threshold")
    ax.set_title("HF direct voxel post-hoc threshold scan", pad=7)
    ax.set_xticks(np.arange(len(TAU_GRID)))
    ax.set_xticklabels([str(item) for item in TAU_GRID])
    ax.set_yticks(np.arange(len(COVERAGE_GRID)))
    ax.set_yticklabels([str(item) for item in COVERAGE_GRID])
    ax.set_xticks(np.arange(-0.5, len(TAU_GRID), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(COVERAGE_GRID), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.9)
    ax.tick_params(which="minor", bottom=False, left=False)

    for y_idx, coverage in enumerate(COVERAGE_GRID):
        for x_idx, tau in enumerate(TAU_GRID):
            label = label_grid.loc[coverage, tau]
            rho = rho_grid.loc[coverage, tau]
            if isinstance(label, str) and label:
                text_color = "white" if np.isfinite(rho) and abs(float(rho)) > 0.55 * max_abs else "black"
                ax.text(x_idx, y_idx, label, ha="center", va="center", fontsize=6.5, color=text_color, linespacing=0.9)
            if bool(pass_grid.loc[coverage, tau]):
                ax.scatter(x_idx + 0.34, y_idx - 0.34, s=12, c="#BDBDBD", edgecolors="none", zorder=4)

    primary_x, primary_y = grid_cell_position(PRIMARY_TAU, PRIMARY_COVERAGE)
    ax.add_patch(Rectangle((primary_x - 0.5, primary_y - 0.5), 1, 1, fill=False, edgecolor="black", linewidth=1.0, zorder=5))
    if selected.get("tau") is not None and selected.get("coverage") is not None:
        selected_x, selected_y = grid_cell_position(selected["tau"], selected["coverage"])
        ax.add_patch(Rectangle((selected_x - 0.5, selected_y - 0.5), 1, 1, fill=False, edgecolor="black", linewidth=2.2, zorder=6))

    colorbar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.025)
    colorbar.set_label("LOOCV Spearman rho")
    ax.text(
        0,
        -0.18,
        "Post-hoc exploratory grid search. Stars show nominal p only (* p<0.05, ** p<0.01, *** p<0.001); not FDR/max-stat corrected. Gray dot: passes hard filters.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=6.5,
    )

    base = scan_dir / "posthoc_threshold_scan_heatmap_rho_annotated"
    outputs = {
        "source_csv": str(source_path),
        "svg": str(base.with_suffix(".svg")),
        "pdf": str(base.with_suffix(".pdf")),
        "png": str(base.with_suffix(".png")),
    }
    fig.savefig(outputs["svg"], bbox_inches="tight")
    fig.savefig(outputs["pdf"], bbox_inches="tight")
    fig.savefig(outputs["png"], dpi=600, bbox_inches="tight")
    plt.close(fig)

    manifest["annotated_rho_heatmap"] = {
        "status": "PASS",
        "generated_at": iso_now(),
        "source_results_csv": str(results_path),
        "outputs": outputs,
        "x_axis": "tau (V/m)",
        "y_axis": "Coverage threshold",
        "color_value": "LOOCV Spearman rho",
        "color_center": 0,
        "significance_column": "loocv_spearman_nominal_p",
        "significance_note": "Nominal p only; not FDR or max-stat corrected.",
        "stars": {"p<0.05": "*", "p<0.01": "**", "p<0.001": "***"},
        "primary_branch": {"tau": PRIMARY_TAU, "coverage": PRIMARY_COVERAGE, "outline": "thin black"},
        "selected_branch": {
            "tau": selected.get("tau"),
            "coverage": selected.get("coverage"),
            "outline": "thick black",
        },
        "hard_filter_marker": "light gray dot",
    }
    write_json(manifest_path, manifest)
    return {"status": "PASS", "outputs": outputs}


def write_heatmap_figure(path: Path, heatmap: pd.DataFrame, title: str) -> str:
    """Write a simple heatmap PNG when matplotlib is available."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - optional plotting dependency
        return f"SKIPPED: {exc}"

    values = heatmap.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(8.5, 5.0), constrained_layout=True)
    image = ax.imshow(values, aspect="auto", origin="lower")
    ax.set_title(title)
    ax.set_xlabel("Coverage")
    ax.set_ylabel("tau (V/m)")
    ax.set_xticks(np.arange(len(heatmap.columns)))
    ax.set_xticklabels([str(item) for item in heatmap.columns])
    ax.set_yticks(np.arange(len(heatmap.index)))
    ax.set_yticklabels([str(item) for item in heatmap.index])
    fig.colorbar(image, ax=ax)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return "PASS"


def load_or_build_posthoc_preprocess(args: argparse.Namespace, output_root: Path, scale_slug: str) -> dict[str, Any]:
    """Load or build a candidate-threshold-100 exposure sidecar for the post-hoc scan."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    derivatives_root = Path(args.leaddbs_derivatives).expanduser().resolve()
    matlab_bin = Path(args.matlab_bin).expanduser().resolve()
    scale = args.scale

    scan_dir = output_root / scale_slug / "posthoc_threshold_scan"
    preprocess_dir = scan_dir / "preprocess_candidate_tau100"
    primary_preprocess_dir = output_root / scale_slug / "preprocess"
    x_path = preprocess_dir / "X_HF_float32_subject_major.npy"
    flat_path = preprocess_dir / "candidate_flat_indices.npy"
    ijk_path = preprocess_dir / "candidate_ijk.npy"
    xyz_path = preprocess_dir / "candidate_xyz.npy"
    subjects_path = preprocess_dir / "subjects.csv"
    qc_path = preprocess_dir / "direct_voxel_HF_posthoc_preprocess_qc.json"

    records = load_subject_records(clinical_root, scale)
    subject_ids = {record.subject_id for record in records}
    scale_direction, scale_direction_source = infer_scale_direction(scale)
    if scale_direction not in {"lower", "higher"}:
        raise RuntimeError(f"unknown scale direction for {scale!r}; provide explicit direction before running")

    required = [x_path, flat_path, ijk_path, xyz_path, subjects_path, qc_path]
    if not args.force_preprocess and all(path.is_file() for path in required):
        subjects = pd.read_csv(subjects_path)
        expected_subjects = [record.subject_id for record in records]
        observed_subjects = subjects["subject_id"].astype(str).tolist()
        if observed_subjects != expected_subjects:
            raise RuntimeError("post-hoc preprocess subjects do not match current clinical records")
        return {
            "repo_root": repo_root,
            "asset_root": asset_root,
            "clinical_root": clinical_root,
            "derivatives_root": derivatives_root,
            "scan_dir": scan_dir,
            "preprocess_dir": preprocess_dir,
            "records": records,
            "scale_direction": scale_direction,
            "scale_direction_source": scale_direction_source,
            "x": np.load(x_path, mmap_mode="r"),
            "candidate_flat": np.load(flat_path),
            "candidate_ijk": np.load(ijk_path),
            "candidate_xyz": np.load(xyz_path),
            "preprocess_status": "reused",
            "preprocess_qc_path": qc_path,
        }

    preprocess_dir.mkdir(parents=True, exist_ok=True)
    stim_rows = filter_hf_stn_rows(load_stim_table(clinical_root), subject_ids)
    if stim_rows["ID"].nunique() != len(records):
        missing_subjects = sorted(subject_ids - set(stim_rows["ID"].astype(str).unique()))
        raise RuntimeError("missing HF STN stimulation rows for subjects: " + ", ".join(missing_subjects))

    side_paths, side_field_qc = collect_side_field_paths(records, stim_rows, derivatives_root)
    flipped_left_paths, flip_result = flip_left_fields_with_matlab(
        repo_root=asset_root,
        matlab_bin=matlab_bin,
        side_paths=side_paths,
        preprocess_dir=primary_preprocess_dir,
        force=args.force_flip,
    )
    ref_img, right_ijk, right_xyz, right_flat = right_brainmask_voxels(asset_root)
    exposure_all, sampling_qc = build_exposure_matrix(records, side_paths, flipped_left_paths, right_xyz)
    candidate_sparse = np.any(exposure_all > POSTHOC_CANDIDATE_THRESHOLD, axis=0)
    candidate_flat = right_flat[candidate_sparse]
    candidate_ijk = right_ijk[candidate_sparse]
    candidate_xyz = right_xyz[candidate_sparse]
    x = exposure_all[:, candidate_sparse].astype(np.float32)

    np.save(x_path, x)
    np.save(flat_path, candidate_flat)
    np.save(ijk_path, candidate_ijk)
    np.save(xyz_path, candidate_xyz)
    write_csv(subjects_path, [asdict(record) for record in records], ["subject_id", "y_post", "y_base"])
    write_json(
        qc_path,
        {
            "generated_at": iso_now(),
            "scale": scale,
            "scale_direction": scale_direction,
            "scale_direction_source": scale_direction_source,
            "n_subjects": len(records),
            "right_brainmask_voxels": int(right_flat.size),
            "candidate_threshold_v_per_m": POSTHOC_CANDIDATE_THRESHOLD,
            "n_candidate_voxels": int(candidate_flat.size),
            "primary_preprocess_dir_for_flips": str(primary_preprocess_dir),
            "side_fields": side_field_qc,
            "flip_result": flip_result,
            "sampling_qc": sampling_qc,
        },
    )

    return {
        "repo_root": repo_root,
        "asset_root": asset_root,
        "clinical_root": clinical_root,
        "derivatives_root": derivatives_root,
        "scan_dir": scan_dir,
        "preprocess_dir": preprocess_dir,
        "records": records,
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "x": np.load(x_path, mmap_mode="r"),
        "candidate_flat": candidate_flat,
        "candidate_ijk": candidate_ijk,
        "candidate_xyz": candidate_xyz,
        "preprocess_status": "built",
        "preprocess_qc_path": qc_path,
    }


def _posthoc_preprocess_required_files(preprocess_dir: Path) -> dict[str, Path]:
    return {
        "x": preprocess_dir / "X_HF_float32_subject_major.npy",
        "flat": preprocess_dir / "candidate_flat_indices.npy",
        "ijk": preprocess_dir / "candidate_ijk.npy",
        "xyz": preprocess_dir / "candidate_xyz.npy",
    }


def _load_subject_ids_from_csv(path: Path) -> list[str]:
    frame = pd.read_csv(path)
    if "subject_id" not in frame.columns:
        raise RuntimeError(f"subject file is missing subject_id: {path}")
    return frame["subject_id"].astype(str).tolist()


def load_or_build_shared_posthoc_preprocess(args: argparse.Namespace, output_root: Path) -> dict[str, Any]:
    """Load or build the all-scale shared HF exposure cache."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    derivatives_root = Path(args.leaddbs_derivatives).expanduser().resolve()
    shared_dir = output_root / SHARED_PREPROCESS_RELATIVE
    shared_subjects_path = shared_dir / "shared_subjects.csv"
    shared_qc_path = shared_dir / "direct_voxel_HF_posthoc_shared_preprocess_qc.json"
    required = _posthoc_preprocess_required_files(shared_dir)
    base_records = load_subject_records(clinical_root, HF_DEFAULT_SCALES[0])
    expected_subjects = [record.subject_id for record in base_records]

    if (
        not args.force_preprocess
        and all(path.is_file() for path in required.values())
        and shared_subjects_path.is_file()
        and shared_qc_path.is_file()
    ):
        observed_subjects = _load_subject_ids_from_csv(shared_subjects_path)
        if observed_subjects != expected_subjects:
            raise RuntimeError("shared post-hoc preprocess subjects do not match current clinical records")
        return {
            "repo_root": repo_root,
            "asset_root": asset_root,
            "clinical_root": clinical_root,
            "derivatives_root": derivatives_root,
            "preprocess_dir": shared_dir,
            "preprocess_status": "shared_reused",
            "preprocess_qc_path": shared_qc_path,
            "subject_ids": expected_subjects,
            "x": np.load(required["x"], mmap_mode="r"),
            "candidate_flat": np.load(required["flat"]),
            "candidate_ijk": np.load(required["ijk"]),
            "candidate_xyz": np.load(required["xyz"]),
        }

    seed_args = argparse.Namespace(**vars(args))
    seed_args.scale = HF_DEFAULT_SCALES[0]
    seed_slug = slugify(HF_DEFAULT_SCALES[0])
    seed_preprocess = load_or_build_posthoc_preprocess(seed_args, output_root, seed_slug)
    seed_dir = Path(seed_preprocess["preprocess_dir"])
    seed_subjects_path = seed_dir / "subjects.csv"
    observed_subjects = _load_subject_ids_from_csv(seed_subjects_path)
    if observed_subjects != expected_subjects:
        raise RuntimeError("seed post-hoc preprocess subjects do not match current clinical records")

    shared_dir.mkdir(parents=True, exist_ok=True)
    seed_required = _posthoc_preprocess_required_files(seed_dir)
    for key, source in seed_required.items():
        shutil.copy2(source, required[key])
    write_csv(shared_subjects_path, [{"subject_id": subject_id} for subject_id in expected_subjects], ["subject_id"])
    write_json(
        shared_qc_path,
        {
            "generated_at": iso_now(),
            "status": "PASS",
            "source": "copied_from_single_scale_tau100_cache",
            "source_scale": HF_DEFAULT_SCALES[0],
            "source_preprocess_dir": str(seed_dir),
            "candidate_threshold_v_per_m": POSTHOC_CANDIDATE_THRESHOLD,
            "n_subjects": len(expected_subjects),
            "n_candidate_voxels": int(np.load(required["flat"]).shape[0]),
        },
    )
    return {
        "repo_root": repo_root,
        "asset_root": asset_root,
        "clinical_root": clinical_root,
        "derivatives_root": derivatives_root,
        "preprocess_dir": shared_dir,
        "preprocess_status": "shared_copied_from_single_scale",
        "preprocess_qc_path": shared_qc_path,
        "subject_ids": expected_subjects,
        "x": np.load(required["x"], mmap_mode="r"),
        "candidate_flat": np.load(required["flat"]),
        "candidate_ijk": np.load(required["ijk"]),
        "candidate_xyz": np.load(required["xyz"]),
    }


def _empty_grid_result(tau: int, coverage_min: int, reason: str) -> dict[str, Any]:
    return {
        "tau": tau,
        "coverage": coverage_min,
        "n_voxels_full": 0,
        "fold_n_voxels_min": 0,
        "fold_n_voxels_median": 0,
        "fold_n_voxels_max": 0,
        "loocv_spearman_rho": math.nan,
        "loocv_spearman_nominal_p": math.nan,
        "loocv_pearson_r": math.nan,
        "loocv_pearson_nominal_p": math.nan,
        "q2": math.nan,
        "mae_model": math.nan,
        "mae_baseline": math.nan,
        "rmse_model": math.nan,
        "rmse_baseline": math.nan,
        "corr_HFScore_mean_main_Y_base": math.nan,
        "spearman_HFScore_mean_main_Y_base": math.nan,
        "delta_median": math.nan,
        "delta_min": math.nan,
        "delta_max": math.nan,
        "hfscore_nonconstant_all_folds": False,
        "all_predictions_finite": False,
        "passes_all_hard_filters": False,
        "failure_reason": reason,
    }


def evaluate_grid_cell(
    x: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    scale_direction: str,
    tau: int,
    coverage_min: int,
) -> dict[str, Any]:
    s_tau = suprathreshold_matrix(x, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    omega = candidate_mask_from_coverage(coverage, coverage_min)
    n_voxels_full = int(np.count_nonzero(omega))
    if n_voxels_full == 0:
        return _empty_grid_result(tau, coverage_min, "empty_full_sample_omega")

    rho = np.full(x.shape[1], np.nan, dtype=np.float32)
    rho_omega = partial_spearman_matrix(y_post, x[:, omega], y_base)
    rho[omega] = rho_omega.astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    valid_full = omega & np.isfinite(weights)
    if not np.any(valid_full):
        return _empty_grid_result(tau, coverage_min, "no_valid_full_sample_weights")
    full_scores, n_valid_full = mean_map_score(x, weights, valid_full)

    n_subjects = y_post.shape[0]
    loocv_pred = np.full(n_subjects, np.nan, dtype=float)
    loocv_base_pred = np.full(n_subjects, np.nan, dtype=float)
    loocv_score = np.full(n_subjects, np.nan, dtype=float)
    fold_n_voxels: list[int] = []
    deltas: list[float] = []
    nonconstant_all_folds = True
    failure_reasons: list[str] = []

    for heldout in range(n_subjects):
        train = np.array([idx for idx in range(n_subjects) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        omega_fold = candidate_mask_from_coverage(coverage_fold, coverage_min)
        n_fold = int(np.count_nonzero(omega_fold))
        fold_n_voxels.append(n_fold)
        if n_fold == 0:
            nonconstant_all_folds = False
            failure_reasons.append(f"empty_fold_{heldout + 1}")
            continue

        rho_fold = partial_spearman_matrix(y_post[train], x[train][:, omega_fold], y_base[train])
        weights_fold_local = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[omega_fold] = weights_fold_local
        valid_fold = omega_fold & np.isfinite(weights_fold)
        if not np.any(valid_fold):
            nonconstant_all_folds = False
            failure_reasons.append(f"no_valid_fold_weights_{heldout + 1}")
            continue

        fold_scores, _ = mean_map_score(x, weights_fold, valid_fold)
        if np.nanstd(fold_scores[train]) == 0:
            nonconstant_all_folds = False
            failure_reasons.append(f"constant_training_score_fold_{heldout + 1}")
            continue

        pred, beta = fit_linear_prediction(
            y_post[train],
            fold_scores[train],
            y_base[train],
            fold_scores[[heldout]],
            y_base[[heldout]],
        )
        base_pred, _ = fit_baseline_only(y_post[train], y_base[train], y_base[[heldout]])
        loocv_pred[heldout] = pred[0]
        loocv_base_pred[heldout] = base_pred[0]
        loocv_score[heldout] = fold_scores[heldout]
        deltas.append(float(beta[1]))

    finite_pred = np.isfinite(loocv_pred)
    finite_base = np.isfinite(loocv_base_pred)
    all_predictions_finite = bool(np.all(finite_pred) and np.all(finite_base))
    loocv_spearman_rho, loocv_spearman_p = safe_spearman(y_post, loocv_pred)
    loocv_pearson_r, loocv_pearson_p = safe_pearson(y_post, loocv_pred)

    finite_model = np.isfinite(y_post) & np.isfinite(loocv_pred)
    residual_model = y_post[finite_model] - loocv_pred[finite_model]
    mae_model = float(np.mean(np.abs(residual_model))) if residual_model.size else math.nan
    rmse_model = float(np.sqrt(np.mean(residual_model * residual_model))) if residual_model.size else math.nan

    finite_baseline = np.isfinite(y_post) & np.isfinite(loocv_base_pred)
    residual_base = y_post[finite_baseline] - loocv_base_pred[finite_baseline]
    mae_baseline = float(np.mean(np.abs(residual_base))) if residual_base.size else math.nan
    rmse_baseline = float(np.sqrt(np.mean(residual_base * residual_base))) if residual_base.size else math.nan

    finite_q2 = np.isfinite(y_post) & np.isfinite(loocv_pred) & np.isfinite(loocv_base_pred)
    sse_model = float(np.sum((y_post[finite_q2] - loocv_pred[finite_q2]) ** 2))
    sse_baseline = float(np.sum((y_post[finite_q2] - loocv_base_pred[finite_q2]) ** 2))
    q2 = float(1.0 - sse_model / sse_baseline) if sse_baseline > 0 else math.nan

    corr_score_base, _ = safe_pearson(full_scores, y_base)
    spearman_score_base, _ = safe_spearman(full_scores, y_base)
    fold_array = np.asarray(fold_n_voxels, dtype=float)
    deltas_array = np.asarray(deltas, dtype=float)
    row = {
        "tau": tau,
        "coverage": coverage_min,
        "n_voxels_full": n_voxels_full,
        "n_valid_full_score_voxels": int(n_valid_full),
        "fold_n_voxels_min": int(np.nanmin(fold_array)) if fold_array.size else 0,
        "fold_n_voxels_median": float(np.nanmedian(fold_array)) if fold_array.size else math.nan,
        "fold_n_voxels_max": int(np.nanmax(fold_array)) if fold_array.size else 0,
        "loocv_spearman_rho": loocv_spearman_rho,
        "loocv_spearman_nominal_p": loocv_spearman_p,
        "loocv_pearson_r": loocv_pearson_r,
        "loocv_pearson_nominal_p": loocv_pearson_p,
        "q2": q2,
        "mae_model": mae_model,
        "mae_baseline": mae_baseline,
        "rmse_model": rmse_model,
        "rmse_baseline": rmse_baseline,
        "corr_HFScore_mean_main_Y_base": corr_score_base,
        "spearman_HFScore_mean_main_Y_base": spearman_score_base,
        "delta_median": float(np.nanmedian(deltas_array)) if deltas_array.size else math.nan,
        "delta_min": float(np.nanmin(deltas_array)) if deltas_array.size else math.nan,
        "delta_max": float(np.nanmax(deltas_array)) if deltas_array.size else math.nan,
        "hfscore_nonconstant_all_folds": nonconstant_all_folds,
        "all_predictions_finite": all_predictions_finite,
        "failure_reason": ";".join(failure_reasons),
    }
    row.update(
        {
            "passes_n_voxels_full": _finite_float(row["n_voxels_full"]) >= 20,
            "passes_fold_n_voxels_min": _finite_float(row["fold_n_voxels_min"]) >= 10,
            "passes_hfscore_nonconstant": nonconstant_all_folds,
            "passes_predictions_finite": all_predictions_finite,
            "passes_q2_positive": _finite_float(row["q2"]) > 0,
            "passes_spearman_positive": _finite_float(row["loocv_spearman_rho"]) > 0,
            "passes_mae_improvement": _finite_float(row["mae_model"]) < _finite_float(row["mae_baseline"]),
            "passes_rmse_improvement": _finite_float(row["rmse_model"]) < _finite_float(row["rmse_baseline"]),
        }
    )
    row["passes_all_hard_filters"] = row_passes_hard_filters(row)
    return row


def write_scan_outputs(scan_dir: Path, rows: list[dict[str, Any]], selected: dict[str, Any] | None, manifest: dict[str, Any]) -> None:
    results_path = scan_dir / "posthoc_threshold_scan_results.csv"
    fieldnames = [
        "tau",
        "coverage",
        "n_voxels_full",
        "n_valid_full_score_voxels",
        "fold_n_voxels_min",
        "fold_n_voxels_median",
        "fold_n_voxels_max",
        "loocv_spearman_rho",
        "loocv_spearman_nominal_p",
        "loocv_pearson_r",
        "loocv_pearson_nominal_p",
        "q2",
        "mae_model",
        "mae_baseline",
        "rmse_model",
        "rmse_baseline",
        "corr_HFScore_mean_main_Y_base",
        "spearman_HFScore_mean_main_Y_base",
        "delta_median",
        "delta_min",
        "delta_max",
        "hfscore_nonconstant_all_folds",
        "all_predictions_finite",
        "passes_n_voxels_full",
        "passes_fold_n_voxels_min",
        "passes_hfscore_nonconstant",
        "passes_predictions_finite",
        "passes_q2_positive",
        "passes_spearman_positive",
        "passes_mae_improvement",
        "passes_rmse_improvement",
        "passes_all_hard_filters",
        "failure_reason",
    ]
    write_csv(results_path, rows, fieldnames)

    heatmap_outputs: dict[str, str] = {}
    for value_column, suffix, title in [
        ("q2", "q2", "Post-hoc threshold scan Q2"),
        ("loocv_spearman_rho", "rho", "Post-hoc threshold scan LOOCV Spearman rho"),
        ("n_voxels_full", "n_voxels", "Post-hoc threshold scan full-sample voxel count"),
    ]:
        heatmap = build_heatmap(rows, value_column)
        csv_path = scan_dir / f"posthoc_threshold_scan_heatmap_{suffix}.csv"
        heatmap.to_csv(csv_path)
        heatmap_outputs[str(csv_path.name)] = str(csv_path)
        png_path = scan_dir / f"posthoc_threshold_scan_heatmap_{suffix}.png"
        figure_status = write_heatmap_figure(png_path, heatmap, title)
        heatmap_outputs[str(png_path.name)] = figure_status if figure_status != "PASS" else str(png_path)

    manifest = dict(manifest)
    manifest["selected_grid_cell"] = selected
    manifest["outputs"] = {
        "results_csv": str(results_path),
        "selected_manifest_json": str(scan_dir / "posthoc_selected_threshold_manifest.json"),
        "heatmaps": heatmap_outputs,
    }
    write_json(scan_dir / "posthoc_selected_threshold_manifest.json", manifest)
    annotated_status = write_annotated_rho_heatmap(scan_dir)
    if annotated_status.get("status") != "PASS":
        manifest["annotated_rho_heatmap"] = annotated_status
        write_json(scan_dir / "posthoc_selected_threshold_manifest.json", manifest)


def run_scale_posthoc_threshold_scan(
    args: argparse.Namespace,
    scale: str,
    *,
    shared_preprocess: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the post-hoc threshold scan for one scale and return table data."""
    started = time.time()
    output_root = Path(args.output_root).expanduser().resolve()
    scale_slug = slugify(scale)
    scan_dir = output_root / scale_slug / "posthoc_threshold_scan"
    scan_dir.mkdir(parents=True, exist_ok=True)

    if shared_preprocess is None:
        scale_args = argparse.Namespace(**vars(args))
        scale_args.scale = scale
        preprocess = load_or_build_posthoc_preprocess(scale_args, output_root, scale_slug)
        records = preprocess["records"]
        scale_direction = preprocess["scale_direction"]
        scale_direction_source = preprocess["scale_direction_source"]
    else:
        clinical_root = Path(args.clinical_root).expanduser().resolve()
        records = load_subject_records(clinical_root, scale)
        subject_ids = [record.subject_id for record in records]
        if subject_ids != shared_preprocess["subject_ids"]:
            raise RuntimeError(f"subject order for {scale!r} does not match shared HF exposure cache")
        scale_direction, scale_direction_source = infer_scale_direction(scale)
        if scale_direction not in {"lower", "higher"}:
            raise RuntimeError(f"unknown scale direction for {scale!r}; provide explicit direction before running")
        preprocess = shared_preprocess

    x = np.asarray(preprocess["x"], dtype=np.float32)
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    rows: list[dict[str, Any]] = []
    for tau in TAU_GRID:
        for coverage_min in COVERAGE_GRID:
            print(f"[{scale_slug}] Evaluating tau={tau} V/m, Coverage>={coverage_min}", flush=True)
            rows.append(evaluate_grid_cell(x, y_post, y_base, scale_direction, tau, coverage_min))

    selected = select_best_grid_cell(rows)
    manifest = {
        "generated_at": iso_now(),
        "model": "HF direct voxel",
        "analysis": "posthoc_tau_coverage_threshold_scan",
        "interpretation": "post-hoc exploratory threshold optimization; does not replace tau200/Coverage>=5 primary branch",
        "scale": scale,
        "scale_slug": scale_slug,
        "endpoint": scale,
        "endpoint_family": endpoint_family_for_scale(scale),
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "estimator": "baseline-adjusted partial Spearman",
        "score": "HFScore_mean_main",
        "validation": "LOOCV",
        "baseline_model": "Y_post ~ Y_base",
        "primary_branch": {"tau_v_per_m": PRIMARY_TAU, "coverage": PRIMARY_COVERAGE},
        "tau_grid_v_per_m": TAU_GRID,
        "coverage_grid": COVERAGE_GRID,
        "n_grid_cells": len(rows),
        "candidate_sparse_threshold_v_per_m": POSTHOC_CANDIDATE_THRESHOLD,
        "preprocess_status": preprocess["preprocess_status"],
        "preprocess_dir": str(preprocess["preprocess_dir"]),
        "preprocess_qc_json": str(preprocess["preprocess_qc_path"]),
        "n_subjects": len(records),
        "n_candidate_voxels": int(x.shape[1]),
        "n_passing_grid_cells": int(sum(row_passes_hard_filters(row) for row in rows)),
        "selection_rule": [
            "passes all hard stability filters",
            "highest Q2",
            "higher LOOCV Spearman rho",
            "higher fold_n_voxels_min",
            "closer to tau200/Coverage>=5",
            "stricter Coverage then higher tau if still tied",
        ],
        "max_stat_permutation": {
            "status": "not_run",
            "smoke_B": 1000,
            "formal_B": 10000,
            "seed": 42,
            "reason": "initial post-hoc scan only",
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        },
        "runtime_profile": {"total_s": time.time() - started},
    }
    write_scan_outputs(scan_dir, rows, selected, manifest)
    print(f"Post-hoc threshold scan output: {scan_dir}")
    if selected:
        print(
            "Selected exploratory branch: "
            f"tau={selected['tau']}, Coverage>={selected['coverage']}, "
            f"rho={selected['loocv_spearman_rho']:.6g}, Q2={selected['q2']:.6g}"
        )
    else:
        print("No grid cell passed all hard stability filters.")
    return {
        "scale": scale,
        "scale_slug": scale_slug,
        "scale_direction": scale_direction,
        "scale_direction_source": scale_direction_source,
        "n_subjects": len(records),
        "n_candidate_voxels": int(x.shape[1]),
        "rows": rows,
        "selected": selected,
        "scan_dir": str(scan_dir),
        "manifest": manifest,
    }


def write_all_scale_outputs(
    output_root: Path,
    per_scale_results: list[dict[str, Any]],
    runtime_s: float,
    *,
    mode: str,
) -> dict[str, Path]:
    """Write long, summary, and manifest outputs for all-scale scans."""
    summary_dir = output_root / "posthoc_threshold_scan_all_scales"
    summary_dir.mkdir(parents=True, exist_ok=True)
    long_table = build_all_scale_long_table(per_scale_results)
    summary_table = build_all_scale_summary_table(per_scale_results)
    long_path = summary_dir / "all_scales_posthoc_threshold_scan_long.csv"
    summary_path = summary_dir / "all_scales_posthoc_threshold_scan_summary.csv"
    manifest_path = summary_dir / "all_scales_posthoc_threshold_scan_manifest.json"
    long_table.to_csv(long_path, index=False)
    summary_table.to_csv(summary_path, index=False)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "analysis": "all_scales_posthoc_tau_coverage_threshold_scan",
            "mode": mode,
            "interpretation": "post-hoc exploratory all-scale threshold scan; nominal p values are not multiplicity corrected",
            "n_scales": len(per_scale_results),
            "n_grid_cells_per_scale": len(TAU_GRID) * len(COVERAGE_GRID),
            "n_grid_cells_total": int(long_table.shape[0]),
            "n_long_rows": int(long_table.shape[0]),
            "tau_grid_v_per_m": TAU_GRID,
            "coverage_grid": COVERAGE_GRID,
            "output_long_csv": str(long_path),
            "output_summary_csv": str(summary_path),
            "runtime_s": runtime_s,
            "scales": [
                {
                    "scale": result["scale"],
                    "scale_slug": result["scale_slug"],
                    "endpoint_family": endpoint_family_for_scale(result["scale"]),
                    "scan_dir": result["scan_dir"],
                    "n_passing_grid_cells": int(sum(_as_bool(row.get("passes_all_hard_filters")) for row in result["rows"])),
                    "selected": result.get("selected"),
                }
                for result in per_scale_results
            ],
        },
    )
    return {"summary_dir": summary_dir, "long_csv": long_path, "summary_csv": summary_path, "manifest_json": manifest_path}


def run_posthoc_threshold_scan(args: argparse.Namespace) -> int:
    run_scale_posthoc_threshold_scan(args, args.scale)
    return 0


def collect_scale_result_from_outputs(args: argparse.Namespace, scale: str) -> dict[str, Any]:
    """Collect one scale result from existing output files."""
    output_root = Path(args.output_root).expanduser().resolve()
    scale_slug = slugify(scale)
    scan_dir = output_root / scale_slug / "posthoc_threshold_scan"
    results_path = scan_dir / "posthoc_threshold_scan_results.csv"
    manifest_path = scan_dir / "posthoc_selected_threshold_manifest.json"
    if not results_path.is_file():
        raise FileNotFoundError(f"missing post-hoc scan results for {scale}: {results_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing post-hoc manifest for {scale}: {manifest_path}")
    rows = pd.read_csv(results_path).to_dict(orient="records")
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    return {
        "scale": scale,
        "scale_slug": scale_slug,
        "scale_direction": manifest.get("scale_direction", ""),
        "scale_direction_source": manifest.get("scale_direction_source", ""),
        "n_subjects": int(manifest.get("n_subjects", 0)),
        "n_candidate_voxels": int(manifest.get("n_candidate_voxels", 0)),
        "rows": rows,
        "selected": manifest.get("selected_grid_cell"),
        "scan_dir": str(scan_dir),
        "manifest": manifest,
    }


def run_plot_only(args: argparse.Namespace) -> int:
    """Generate annotated post-hoc rho heatmap from existing scan outputs."""
    scale_slug = slugify(args.scale)
    output_root = Path(args.output_root).expanduser().resolve()
    scan_dir = output_root / scale_slug / "posthoc_threshold_scan"
    result = write_annotated_rho_heatmap(scan_dir)
    if result.get("status") != "PASS":
        raise RuntimeError("annotated rho heatmap generation failed: " + json.dumps(result, sort_keys=True))
    print(f"Annotated rho heatmap output: {scan_dir}")
    for key, value in result["outputs"].items():
        print(f"{key}: {value}")
    return 0


def run_all_scales(args: argparse.Namespace) -> int:
    """Run the post-hoc threshold scan for every raw clinical scale."""
    started = time.time()
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    scales = load_all_scale_names(clinical_root)
    shared_preprocess = load_or_build_shared_posthoc_preprocess(args, output_root)
    per_scale_results: list[dict[str, Any]] = []
    for idx, scale in enumerate(scales, start=1):
        print(f"Running all-scale post-hoc scan {idx}/{len(scales)}: {scale}", flush=True)
        per_scale_results.append(run_scale_posthoc_threshold_scan(args, scale, shared_preprocess=shared_preprocess))
    outputs = write_all_scale_outputs(output_root, per_scale_results, time.time() - started, mode="scan")
    print(f"All-scale post-hoc scan summary: {outputs['summary_dir']}")
    print(f"Long table: {outputs['long_csv']}")
    print(f"Summary table: {outputs['summary_csv']}")
    return 0


def run_all_scales_plot_only(args: argparse.Namespace) -> int:
    """Regenerate annotated rho heatmaps and all-scale summary from existing scale outputs."""
    started = time.time()
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    scales = load_all_scale_names(clinical_root)
    per_scale_results: list[dict[str, Any]] = []
    for scale in scales:
        scale_slug = slugify(scale)
        scan_dir = output_root / scale_slug / "posthoc_threshold_scan"
        result = write_annotated_rho_heatmap(scan_dir)
        if result.get("status") != "PASS":
            raise RuntimeError(f"annotated rho heatmap generation failed for {scale}: {json.dumps(result, sort_keys=True)}")
        per_scale_results.append(collect_scale_result_from_outputs(args, scale))
    outputs = write_all_scale_outputs(output_root, per_scale_results, time.time() - started, mode="plot_only")
    print(f"All-scale plot-only summary: {outputs['summary_dir']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default=str(DEFAULT_CANONICAL_ASSET_ROOT), help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_VAL_ROOT / "summary/direct_voxel/hf"), help="HF direct voxel output root.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--scale", default=HF_DEFAULT_SCALES[0], help="Raw clinical scale to run.")
    parser.add_argument("--all-scales", action="store_true", help="Run every Scale from subject_effect_origin.xlsx.")
    parser.add_argument("--plot-only", action="store_true", help="Only draw annotated rho heatmap from existing post-hoc scan outputs.")
    parser.add_argument("--force-preprocess", action="store_true", help="Regenerate the post-hoc tau100 sparse exposure sidecar.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.all_scales and args.plot_only:
        return run_all_scales_plot_only(args)
    if args.all_scales:
        return run_all_scales(args)
    if args.plot_only:
        return run_plot_only(args)
    return run_posthoc_threshold_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
