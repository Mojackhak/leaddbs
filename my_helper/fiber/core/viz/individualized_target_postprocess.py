"""Publish individualized seed-target figures from the integrated result tree."""

from __future__ import annotations

import csv
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import nibabel as nib
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.io import savemat

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager

from my_helper.fiber.core.seed_target_connectivity.connectome import (
    ConnectomeAdapter,
    open_connectome,
)
from my_helper.fiber.core.seed_target_connectivity.models import ResolvedMask

from .artifacts import create_display_nifti
from .fiber_composition import (
    SeedPatternCounts,
    TargetConditionedProjection,
    apply_target_scores_to_composition,
    build_whole_connectome_composition,
    target_membership_from_bits,
)
from .fiber_projection import (
    load_binary_projection_mask,
    validate_exact_mask_geometry,
)
from .layout import build_figure_layout
from .model_fit import plot_in_sample_loocv_fit
from .plugin.default import get_fiber_section_cfg
from .spatial_result_config import load_spatial_result_config
from .voxel_sections import plot_signed_voxel_sections


_ROLES = ("reference", "addon")
_TARGET_COUNT = 17


@dataclass(frozen=True)
class RoleTargetProjection:
    """One role's reusable PPMI target and seed-voxel projection."""

    role: str
    fiber_ids: np.ndarray
    target_membership: sparse.csr_matrix
    voxel_patterns: SeedPatternCounts


@dataclass(frozen=True)
class TargetProjectionContext:
    """Validated resources shared by every individualized endpoint."""

    config: Mapping[str, Any]
    connectome: ConnectomeAdapter
    connectome_id: str
    targets: tuple[ResolvedMask, ...]
    target_labels: tuple[str, ...]
    seeds: Mapping[str, ResolvedMask]
    roles: Mapping[str, RoleTargetProjection]


@dataclass(frozen=True)
class _Endpoint:
    scale_id: str
    scale_display_name: str
    role: str
    root: Path
    coefficients: np.ndarray
    stability: tuple[Mapping[str, str], ...]
    bootstrap: tuple[Mapping[str, str], ...]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(fieldnames))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_array(path: Path, array: np.ndarray) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.save(handle, np.asarray(array), allow_pickle=False)
    temporary.replace(path)


def _write_complete(path: Path) -> None:
    _write_json(path, {"status": "complete"})


def _trash(path: Path) -> None:
    subprocess.run(
        ("/usr/bin/trash", str(path)),
        check=True,
        capture_output=True,
        text=True,
    )


def _configured_resources(
    config: Mapping[str, Any],
) -> tuple[
    ConnectomeAdapter,
    str,
    tuple[ResolvedMask, ...],
    tuple[str, ...],
    dict[str, ResolvedMask],
]:
    fiber = config["fiber"]
    individualized = fiber["individualized_seed_target"]
    connectome_id = str(individualized["projection_connectome_id"])
    connectome = open_connectome(
        Path(str(individualized["projection_connectome_path"]))
    )
    targets = tuple(
        load_binary_projection_mask(
            value["path"],
            roi_id=str(value["name"]),
            role="target",
        )
        for value in fiber["targets"]
    )
    labels = tuple(str(value["label"]) for value in fiber["targets"])
    seeds = {
        role: load_binary_projection_mask(
            fiber["seeds"][role]["path"],
            roi_id=role,
            role="seed",
        )
        for role in _ROLES
    }
    for seed in seeds.values():
        validate_exact_mask_geometry(seed, targets)
    return connectome, connectome_id, targets, labels, seeds


def _projection_leaf(
    shared_root: Path,
    connectome_id: str,
    role: str,
) -> Path:
    return shared_root / "target_projections" / connectome_id / role


def _write_role_projection(
    leaf: Path,
    *,
    role: str,
    connectome_id: str,
    target_ids: Sequence[str],
    target_labels: Sequence[str],
    seed: ResolvedMask,
    projection: SeedPatternCounts,
    membership: sparse.csr_matrix,
) -> None:
    leaf.mkdir(parents=True, exist_ok=True)
    _write_array(leaf / "fiber_ids.npy", projection.fiber_ids)
    membership_path = leaf / "target_membership.npz"
    if not membership_path.is_file():
        temporary = membership_path.with_name(membership_path.name + ".tmp")
        with temporary.open("wb") as handle:
            sparse.save_npz(handle, membership, compressed=True)
        temporary.replace(membership_path)
    patterns_path = leaf / "voxel_patterns.npz"
    if not patterns_path.is_file():
        temporary = patterns_path.with_name(patterns_path.name + ".tmp")
        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                seed_voxel_indices=projection.seed_voxel_indices,
                voxel_pattern_indptr=projection.voxel_pattern_indptr,
                pattern_bits=projection.pattern_bits,
                pattern_counts=projection.pattern_counts,
            )
        temporary.replace(patterns_path)
    _write_json(
        leaf / "metadata.json",
        {
            "connectome_id": connectome_id,
            "role": role,
            "fiber_scope": "role_seed_connected_with_target_hit",
            "fiber_count": int(projection.fiber_ids.size),
            "target_ids": list(target_ids),
            "target_labels": list(target_labels),
            "target_membership": "independent_binary_segment_intersection",
            "per_fiber_per_seed_voxel": "once",
            "seed_shape": list(seed.shape),
            "seed_affine": np.asarray(seed.affine).tolist(),
        },
    )
    _write_complete(leaf / "complete.json")


def _load_role_projection(leaf: Path, role: str) -> RoleTargetProjection:
    if not (leaf / "complete.json").is_file():
        raise ValueError(f"target projection is incomplete: {leaf}")
    fiber_ids = np.asarray(
        np.load(leaf / "fiber_ids.npy", allow_pickle=False),
        dtype=np.int64,
    )
    membership = sparse.load_npz(leaf / "target_membership.npz").tocsr()
    with np.load(leaf / "voxel_patterns.npz", allow_pickle=False) as payload:
        patterns = SeedPatternCounts(
            role=role,
            seed_voxel_indices=np.asarray(
                payload["seed_voxel_indices"], dtype=np.int64
            ),
            voxel_pattern_indptr=np.asarray(
                payload["voxel_pattern_indptr"], dtype=np.int64
            ),
            pattern_bits=np.asarray(payload["pattern_bits"], dtype=np.uint32),
            pattern_counts=np.asarray(payload["pattern_counts"], dtype=np.int64),
            fiber_ids=fiber_ids,
        )
    if membership.shape != (fiber_ids.size, _TARGET_COUNT):
        raise ValueError(f"target projection axis mismatch: {leaf}")
    return RoleTargetProjection(
        role=role,
        fiber_ids=fiber_ids,
        target_membership=membership,
        voxel_patterns=patterns,
    )


def prepare_target_projection_context(
    *,
    spatial_config_path: str | Path,
    shared_root: str | Path,
    force: bool = False,
) -> TargetProjectionContext:
    """Create or restore the scale-independent PPMI target projection."""

    config = load_spatial_result_config(spatial_config_path)
    root = Path(shared_root).expanduser().resolve()
    connectome, connectome_id, targets, labels, seeds = _configured_resources(
        config
    )
    target_ids = tuple(value.roi_id for value in targets)
    leaves = {
        role: _projection_leaf(root, connectome_id, role) for role in _ROLES
    }
    if force:
        for leaf in leaves.values():
            if leaf.exists():
                _trash(leaf)
    if not all((leaf / "complete.json").is_file() for leaf in leaves.values()):
        physical = build_whole_connectome_composition(
            connectome=connectome,
            seeds=seeds,
            targets=targets,
            fiber_chunk_size=int(config["fiber"]["cache"]["fiber_chunk_size"]),
        )
        if physical.target_ids != target_ids:
            raise ValueError("computed target projection order differs from config")
        for role in _ROLES:
            projection = physical.for_role(role)
            membership = sparse.csr_matrix(
                target_membership_from_bits(
                    physical.fiber_target_bits,
                    projection.fiber_ids,
                    len(target_ids),
                )
            )
            _write_role_projection(
                leaves[role],
                role=role,
                connectome_id=connectome_id,
                target_ids=target_ids,
                target_labels=labels,
                seed=seeds[role],
                projection=projection,
                membership=membership,
            )
    roles = {
        role: _load_role_projection(leaves[role], role) for role in _ROLES
    }
    return TargetProjectionContext(
        config=config,
        connectome=connectome,
        connectome_id=connectome_id,
        targets=targets,
        target_labels=labels,
        seeds=seeds,
        roles=roles,
    )


def _float(value: object) -> float:
    text = str(value).strip()
    return float(text) if text else float("nan")


def _int(value: object) -> int:
    text = str(value).strip()
    return int(text) if text else 0


def _endpoint_target_data(
    endpoint_root: Path,
    expected_target_ids: Sequence[str],
) -> tuple[np.ndarray, list[dict[str, str]], list[dict[str, str]]]:
    target_ids = tuple(
        str(value)
        for value in np.load(
            endpoint_root / "resolver/target_ids.npy",
            allow_pickle=False,
        ).tolist()
    )
    if target_ids != tuple(expected_target_ids):
        raise ValueError(f"published target order differs: {endpoint_root}")
    coefficients = np.asarray(
        np.load(
            endpoint_root / "resolver/full_weights.npy",
            allow_pickle=False,
        ),
        dtype=np.float64,
    )
    if coefficients.shape != (_TARGET_COUNT,):
        raise ValueError(f"published target coefficients differ: {endpoint_root}")
    stability = _read_csv(endpoint_root / "resolver/target_stability.csv")
    bootstrap = _read_csv(endpoint_root / "formal/bootstrap_summary.csv")
    if [row["target_id"] for row in stability] != list(target_ids):
        raise ValueError(f"target stability order differs: {endpoint_root}")
    if [row["target_id"] for row in bootstrap] != list(target_ids):
        raise ValueError(f"target bootstrap order differs: {endpoint_root}")
    return coefficients, stability, bootstrap


def _scale_catalog(manifest: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    scales = manifest.get("scales")
    if not isinstance(scales, list) or not scales:
        raise ValueError("individualized model manifest lacks its scale catalog")
    result: list[tuple[str, str]] = []
    for row in scales:
        if not isinstance(row, Mapping):
            raise ValueError("individualized scale catalog row must be an object")
        scale_id = str(row.get("scale_id", "")).strip()
        display_name = str(row.get("display_name", "")).strip()
        if not scale_id or not display_name or "/" in scale_id:
            raise ValueError("individualized scale catalog row is invalid")
        result.append((scale_id, display_name))
    if len({scale_id for scale_id, _ in result}) != len(result):
        raise ValueError("individualized scale catalog contains duplicate IDs")
    return tuple(result)


def _figure_missing_paths(component_root: Path, stem: str) -> list[Path]:
    return [
        path
        for path in (
            component_root / f"{stem}.png",
            component_root / f"{stem}.pdf",
        )
        if not path.is_file()
    ]


def _paired_metrics(summary: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key in ("in_sample", "loocv", "optimism_gaps"):
        value = summary.get(key)
        if not isinstance(value, Mapping):
            raise ValueError(f"in-sample summary lacks {key}")
        metrics.update(value)
    return metrics


def _render_paired_fit(
    *,
    endpoint_root: Path,
    scale_id: str,
    scale_display_name: str,
    role: str,
    force: bool,
) -> dict[str, Any]:
    component = endpoint_root / "visualization/paired_fit"
    complete = component / "complete.json"
    if complete.is_file() and not force:
        return _read_json(component / "result.json")
    if force and component.exists():
        _trash(component)
    component.mkdir(parents=True, exist_ok=True)
    summary = _read_json(endpoint_root / "in_sample/summary.json")
    metrics = _paired_metrics(summary)
    in_sample = pd.read_csv(endpoint_root / "in_sample/predictions.csv")
    loocv = pd.read_csv(endpoint_root / "resolver/loocv_predictions.csv")
    predictions = in_sample.merge(
        loocv[["subject_id", "outcome", "loocv_prediction"]],
        on=("subject_id", "outcome"),
        how="inner",
        validate="one_to_one",
    )
    if predictions.shape[0] != in_sample.shape[0] or predictions.shape[0] != loocv.shape[0]:
        raise ValueError(f"paired-fit subject closure differs: {endpoint_root}")
    missing = _figure_missing_paths(component, "in_sample_loocv_fit")
    if missing:
        figure = plot_in_sample_loocv_fit(
            predictions,
            metrics,
            output_paths=missing,
        )
        plt.close(figure)
    result = {
        "status": "complete",
        "scale_id": scale_id,
        "scale_display_name": scale_display_name,
        "model_role": role,
        "metrics": metrics,
        "sources": [
            "../../in_sample/predictions.csv",
            "../../resolver/loocv_predictions.csv",
            "../../in_sample/summary.json",
        ],
        "outputs": [
            "in_sample_loocv_fit.png",
            "in_sample_loocv_fit.pdf",
        ],
    }
    _write_json(component / "result.json", result)
    _write_complete(complete)
    return result


def _resolve_font() -> str:
    names = {value.name for value in font_manager.fontManager.ttflist}
    for candidate in ("Arial", "Helvetica", "DejaVu Sans"):
        if candidate in names:
            return candidate
    return "DejaVu Sans"


def _target_statistics_rows(
    *,
    target_ids: Sequence[str],
    target_labels: Sequence[str],
    stability: Sequence[Mapping[str, str]],
    bootstrap: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target_id, label, stable, boot in zip(
        target_ids,
        target_labels,
        stability,
        bootstrap,
        strict=True,
    ):
        rows.append(
            {
                "target_id": target_id,
                "target_label": label,
                "benefit_oriented_coefficient": _float(
                    stable["benefit_oriented_coefficient"]
                ),
                "fold_coefficient_percentile_2_5": _float(
                    stable["fold_coefficient_percentile_2_5"]
                ),
                "fold_coefficient_percentile_97_5": _float(
                    stable["fold_coefficient_percentile_97_5"]
                ),
                "fold_selection_frequency": _float(
                    stable["fold_selection_frequency"]
                ),
                "bootstrap_coefficient_percentile_2_5": _float(
                    boot["coefficient_percentile_2_5"]
                ),
                "bootstrap_coefficient_percentile_97_5": _float(
                    boot["coefficient_percentile_97_5"]
                ),
                "bootstrap_positive_sign_frequency": _float(
                    boot["positive_sign_frequency"]
                ),
                "full_coverage_subjects": _int(
                    stable["full_coverage_subjects"]
                ),
                "nominal_p": _float(stable["nominal_p"]),
                "fdr_q": _float(stable["fdr_q"]),
            }
        )
    return rows


def _plot_target_stability(
    rows: Sequence[Mapping[str, Any]],
    *,
    output_paths: Sequence[Path],
) -> None:
    font = _resolve_font()
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        font,
        "Arial",
        "Helvetica",
        "DejaVu Sans",
    ]
    layout = build_figure_layout(
        2,
        1,
        boxsize=(8.0 * len(rows), 25.0),
        panel_gap=(3.0, 5.0),
        margins=(12.0, 18.0, 5.0, 5.0),
        top_strip_mm=0.0,
        strip_pad_mm=0.0,
    )
    figure = plt.figure(
        figsize=layout.figure_size_inches,
        dpi=600,
        facecolor="white",
    )
    x = np.arange(len(rows), dtype=float)
    coefficients = np.asarray(
        [row["benefit_oriented_coefficient"] for row in rows],
        dtype=float,
    )
    fold_lower = np.asarray(
        [row["fold_coefficient_percentile_2_5"] for row in rows],
        dtype=float,
    )
    fold_upper = np.asarray(
        [row["fold_coefficient_percentile_97_5"] for row in rows],
        dtype=float,
    )
    boot_lower = np.asarray(
        [row["bootstrap_coefficient_percentile_2_5"] for row in rows],
        dtype=float,
    )
    boot_upper = np.asarray(
        [row["bootstrap_coefficient_percentile_97_5"] for row in rows],
        dtype=float,
    )
    colors = np.where(coefficients >= 0.0, "#F2000E", "#0E6AAF")
    upper = figure.add_axes(layout.panel_position(0, 0))
    finite_fold = (
        np.isfinite(coefficients)
        & np.isfinite(fold_lower)
        & np.isfinite(fold_upper)
    )
    finite_boot = (
        np.isfinite(coefficients)
        & np.isfinite(boot_lower)
        & np.isfinite(boot_upper)
    )
    upper.vlines(
        x[finite_fold],
        fold_lower[finite_fold],
        fold_upper[finite_fold],
        color="#999999",
        linewidth=2.0,
        label="LOOCV fold interval",
    )
    upper.vlines(
        x[finite_boot],
        boot_lower[finite_boot],
        boot_upper[finite_boot],
        color="#202020",
        linewidth=0.8,
        label="Bootstrap interval",
    )
    finite_coefficients = np.isfinite(coefficients)
    upper.scatter(
        x[finite_coefficients],
        coefficients[finite_coefficients],
        c=colors[finite_coefficients],
        s=16.0,
        zorder=3,
    )
    upper.axhline(0.0, color="#404040", linestyle=":", linewidth=1.0)
    upper.set_ylabel("Target coefficient", fontsize=7, fontfamily=font)
    upper.set_xticks(x, labels=[])
    upper.tick_params(labelsize=6, width=1.0, length=2.0)
    upper.legend(frameon=False, fontsize=6, loc="best")

    lower = figure.add_axes(layout.panel_position(1, 0))
    frequency = np.asarray(
        [row["fold_selection_frequency"] for row in rows],
        dtype=float,
    )
    lower.bar(x, frequency, color=colors, width=0.65)
    for index, row in enumerate(rows):
        q_value = float(row["fdr_q"])
        if np.isfinite(q_value) and q_value < 0.05:
            lower.text(
                index,
                min(1.0, frequency[index] + 0.04),
                "*",
                ha="center",
                va="bottom",
                fontsize=7,
                fontfamily=font,
            )
    lower.set_ylim(0.0, 1.08)
    lower.set_ylabel("LOOCV selection frequency", fontsize=7, fontfamily=font)
    lower.set_xticks(
        x,
        labels=[str(row["target_label"]) for row in rows],
        rotation=90,
        ha="center",
        fontsize=6,
        fontfamily=font,
    )
    lower.tick_params(axis="y", labelsize=6, width=1.0, length=2.0)
    for axis in (upper, lower):
        for spine in axis.spines.values():
            spine.set_linewidth(1.0)
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=600, bbox_inches="tight", transparent=False)
    plt.close(figure)


def _render_target_stability(
    *,
    endpoint_root: Path,
    scale_id: str,
    scale_display_name: str,
    role: str,
    target_ids: Sequence[str],
    target_labels: Sequence[str],
    stability: Sequence[Mapping[str, str]],
    bootstrap: Sequence[Mapping[str, str]],
    force: bool,
) -> dict[str, Any]:
    component = endpoint_root / "visualization/target_coefficient_stability"
    complete = component / "complete.json"
    if complete.is_file() and not force:
        return _read_json(component / "result.json")
    if force and component.exists():
        _trash(component)
    component.mkdir(parents=True, exist_ok=True)
    rows = _target_statistics_rows(
        target_ids=target_ids,
        target_labels=target_labels,
        stability=stability,
        bootstrap=bootstrap,
    )
    _write_csv(component / "target_statistics.csv", rows, tuple(rows[0]))
    missing = _figure_missing_paths(component, "target_coefficient_stability")
    if missing:
        _plot_target_stability(rows, output_paths=missing)
    result = {
        "status": "complete",
        "scale_id": scale_id,
        "scale_display_name": scale_display_name,
        "model_role": role,
        "target_count": len(rows),
        "fdr_marker_threshold": 0.05,
        "sources": [
            "../../resolver/target_stability.csv",
            "../../formal/bootstrap_summary.csv",
        ],
        "outputs": [
            "target_coefficient_stability.png",
            "target_coefficient_stability.pdf",
            "target_statistics.csv",
        ],
    }
    _write_json(component / "result.json", result)
    _write_complete(complete)
    return result


def _streamline_scores(
    membership: sparse.csr_matrix,
    coefficients: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    finite_targets = np.isfinite(coefficients)
    scores = np.full(membership.shape[0], np.nan, dtype=np.float64)
    if not np.any(finite_targets):
        return scores, np.zeros(membership.shape[0], dtype=np.int64)
    finite_membership = membership[:, finite_targets]
    hit_counts = np.asarray(
        finite_membership.sum(axis=1),
        dtype=np.int64,
    ).reshape(-1)
    weighted = np.asarray(
        finite_membership @ coefficients[finite_targets],
        dtype=np.float64,
    ).reshape(-1)
    scored = hit_counts > 0
    scores[scored] = weighted[scored] / hit_counts[scored]
    return scores, hit_counts


def _projection_image(
    projection: TargetConditionedProjection,
    seed: ResolvedMask,
) -> nib.Nifti1Image:
    source = nib.as_closest_canonical(nib.load(str(seed.source_path)))
    data = np.full(source.shape, np.nan, dtype=np.float32)
    data.reshape(-1, order="C")[projection.seed_voxel_indices] = (
        projection.target_conditioned_score.astype(np.float32)
    )
    header = source.header.copy()
    header.set_data_dtype(np.float32)
    return nib.Nifti1Image(data, source.affine, header=header)


def _target_score_rows(
    *,
    target_ids: Sequence[str],
    target_labels: Sequence[str],
    coefficients: np.ndarray,
    membership: sparse.csr_matrix,
) -> list[dict[str, Any]]:
    counts = np.asarray(membership.sum(axis=0), dtype=np.int64).reshape(-1)
    return [
        {
            "target_id": target_id,
            "target_label": target_label,
            "benefit_oriented_coefficient": (
                float(coefficients[index])
                if np.isfinite(coefficients[index])
                else ""
            ),
            "ppmi_fiber_count": int(counts[index]),
            "coefficient_finite": bool(np.isfinite(coefficients[index])),
        }
        for index, (target_id, target_label) in enumerate(
            zip(target_ids, target_labels, strict=True)
        )
    ]


def _render_spatial_2d(
    *,
    endpoint_root: Path,
    scale_id: str,
    scale_display_name: str,
    role: str,
    coefficients: np.ndarray,
    target_ids: Sequence[str],
    context: TargetProjectionContext,
    force: bool,
) -> dict[str, Any]:
    component = (
        endpoint_root
        / "visualization/spatial_2d/target_conditioned/all_coverage"
    )
    complete = component / "complete.json"
    if complete.is_file() and not force:
        return _read_json(component / "figures/result.json")
    if force and component.exists():
        _trash(component)
    component.mkdir(parents=True, exist_ok=True)
    role_projection = context.roles[role]
    target_projection = apply_target_scores_to_composition(
        composition=role_projection.voxel_patterns,
        target_scores=coefficients,
    )
    source_image = _projection_image(target_projection, context.seeds[role])
    display_path = component / "maps/display.nii.gz"
    display_path.parent.mkdir(parents=True, exist_ok=True)
    display_path, display_metadata = create_display_nifti(
        source_image,
        display_path,
        fwhm_mm=float(context.config["display_map"]["fwhm_mm"]),
        voxel_size_mm=float(context.config["display_map"]["voxel_size_mm"]),
        support_weight_threshold=float(
            context.config["display_map"]["support_weight_threshold"]
        ),
    )
    score_rows = _target_score_rows(
        target_ids=target_ids,
        target_labels=context.target_labels,
        coefficients=coefficients,
        membership=role_projection.target_membership,
    )
    _write_csv(
        component / "tables/target_scores.csv",
        score_rows,
        tuple(score_rows[0]),
    )
    streamline_scores, finite_hit_counts = _streamline_scores(
        role_projection.target_membership,
        coefficients,
    )
    _write_json(
        component / "target_score_qc.json",
        {
            "fiber_scope": "role_seed_connected_with_target_hit",
            "ppmi_fiber_count": int(role_projection.fiber_ids.size),
            "scored_ppmi_fiber_count": int(np.sum(np.isfinite(streamline_scores))),
            "excluded_ppmi_fiber_count": int(
                np.sum(~np.isfinite(streamline_scores))
            ),
            "finite_target_count": int(np.sum(np.isfinite(coefficients))),
            "multiple_finite_target_hit_count": int(
                np.sum(finite_hit_counts > 1)
            ),
            "streamline_target_score": "equal_mean_over_finite_target_scores",
        },
    )
    finite_voxel_scores = target_projection.target_conditioned_score[
        np.isfinite(target_projection.target_conditioned_score)
    ]
    finite_streamline_scores = streamline_scores[np.isfinite(streamline_scores)]
    if not finite_streamline_scores.size:
        raise ValueError(f"target projection has no scored PPMI fibers: {endpoint_root}")
    color_limit = float(np.max(np.abs(finite_streamline_scores)))
    if color_limit <= 0.0:
        raise ValueError(f"target projection PPMI scores are uniformly zero: {endpoint_root}")
    _write_json(
        component / "voxel_composition_qc.json",
        {
            "seed_voxel_count": int(
                target_projection.seed_voxel_indices.size
            ),
            "finite_score_voxel_count": int(finite_voxel_scores.size),
            "all_streamline_incidence_count": float(
                np.sum(target_projection.all_streamline_support_count)
            ),
            "target_scored_streamline_incidence_count": float(
                np.sum(target_projection.target_scored_streamline_count)
            ),
            "target_unscored_streamline_incidence_count": float(
                np.sum(target_projection.target_unscored_streamline_count)
            ),
            "per_fiber_per_voxel": "once",
        },
    )
    figures = component / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    missing = _figure_missing_paths(figures, "display")
    colorbar_label = str(
        context.config["fiber"]["labels"][
            "target_conditioned_colorbar_template"
        ]
    ).format(scale_display_name=scale_display_name)
    if missing:
        style = get_fiber_section_cfg(
            {
                "colorbar_label": colorbar_label,
                "mask_threshold": float(
                    context.config["outline"]["continuous_isovalue"]
                ),
            }
        )
        figure = plot_signed_voxel_sections(
            display_path,
            background_image=context.config["background"]["path"],
            mask_image=context.seeds[role].source_path,
            outline_image=context.config["fiber"]["seeds"][role].get(
                "outline_path"
            ),
            symmetric_color_limit=color_limit,
            style_config=style,
            output_paths=missing,
        )
        plt.close(figure)
    result = {
        "status": "complete",
        "scale_id": scale_id,
        "scale_display_name": scale_display_name,
        "model_role": role,
        "color_limits": [-color_limit, color_limit],
        "color_limit_scope": "scale_role",
        "colorbar_label": colorbar_label,
        "display_map": display_metadata,
        "sources": [
            "../../../../resolver/target_ids.npy",
            "../../../../resolver/full_weights.npy",
            str(
                Path("../../../../../../shared/target_projections")
                / context.connectome_id
                / role
            ),
        ],
        "outputs": [
            "maps/display.nii.gz",
            "figures/display.png",
            "figures/display.pdf",
            "tables/target_scores.csv",
            "target_score_qc.json",
            "voxel_composition_qc.json",
        ],
    }
    _write_json(figures / "result.json", result)
    _write_complete(complete)
    return result


def _geometry_by_role(
    context: TargetProjectionContext,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    selected = {
        role: np.zeros(context.connectome.metadata.n_fibers, dtype=np.bool_)
        for role in _ROLES
    }
    for role in _ROLES:
        selected[role][context.roles[role].fiber_ids - 1] = True
    point_parts: dict[str, list[np.ndarray]] = {role: [] for role in _ROLES}
    count_parts: dict[str, list[np.ndarray]] = {role: [] for role in _ROLES}
    id_parts: dict[str, list[np.ndarray]] = {role: [] for role in _ROLES}
    chunk_size = int(context.config["fiber"]["cache"]["fiber_chunk_size"])
    for chunk in context.connectome.iter_chunks(chunk_size):
        lengths = np.diff(chunk.point_offsets)
        for role in _ROLES:
            keep = selected[role][chunk.fiber_ids - 1]
            if not np.any(keep):
                continue
            point_keep = np.repeat(keep, lengths)
            point_parts[role].append(chunk.points[point_keep])
            count_parts[role].append(lengths[keep])
            id_parts[role].append(chunk.fiber_ids[keep])
    result: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for role in _ROLES:
        points = np.concatenate(point_parts[role], axis=0)
        counts = np.concatenate(count_parts[role]).astype(np.int64, copy=False)
        fiber_ids = np.concatenate(id_parts[role]).astype(np.int64, copy=False)
        if not np.array_equal(fiber_ids, context.roles[role].fiber_ids):
            raise ValueError(f"3-D geometry fiber order differs for {role}")
        result[role] = (points, counts, fiber_ids)
    return result


def _matlab_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def _partition(
    values: Sequence[dict[str, Any]],
    count: int,
) -> list[list[dict[str, Any]]]:
    groups = [[] for _ in range(min(count, len(values)))]
    for index, value in enumerate(values):
        groups[index % len(groups)].append(value)
    return groups


def _run_matlab_export(
    *,
    matlab: str,
    repository_root: Path,
    geometry_path: Path,
    task_path: Path,
) -> None:
    viz_root = Path(__file__).resolve().parent
    expression = (
        f"addpath('{_matlab_quote(repository_root)}');"
        f"addpath('{_matlab_quote(repository_root / 'helpers')}');"
        f"addpath(genpath('{_matlab_quote(viz_root)}'));"
        "mh_viz_export_individualized_target_fiber_pdfs("
        f"'{_matlab_quote(geometry_path)}','{_matlab_quote(task_path)}')"
    )
    subprocess.run(
        (matlab, "-nodisplay", "-batch", expression),
        check=True,
    )


def _render_spatial_3d(
    *,
    endpoints: Sequence[_Endpoint],
    context: TargetProjectionContext,
    force: bool,
) -> list[dict[str, Any]]:
    pending: dict[str, list[tuple[_Endpoint, np.ndarray, float]]] = {
        role: [] for role in _ROLES
    }
    results: list[dict[str, Any]] = []
    for endpoint in endpoints:
        component = endpoint.root / "visualization/spatial_3d/coefficient"
        complete = component / "complete.json"
        if complete.is_file() and not force:
            results.append(_read_json(component / "export_manifest.json"))
            continue
        if force and component.exists():
            _trash(component)
        scores, _ = _streamline_scores(
            context.roles[endpoint.role].target_membership,
            endpoint.coefficients,
        )
        finite = scores[np.isfinite(scores)]
        if not finite.size:
            raise ValueError(f"3-D target projection has no scored fibers: {endpoint.root}")
        color_limit = float(np.max(np.abs(finite)))
        if color_limit <= 0.0:
            raise ValueError(f"3-D target projection scores are uniformly zero: {endpoint.root}")
        pending[endpoint.role].append((endpoint, scores, color_limit))
    if not any(pending.values()):
        return results

    matlab = shutil.which("matlab")
    if matlab is None:
        raise ValueError("individualized 3-D export requires MATLAB")
    repository_root = Path(__file__).resolve().parents[4]
    geometry = _geometry_by_role(context)
    maximum_workers = max(1, (os.cpu_count() or 1) // 2)
    active_roles = [role for role in _ROLES if pending[role]]
    workers_per_role = max(1, maximum_workers // len(active_roles))
    with tempfile.TemporaryDirectory(
        prefix="individualized-target-3d-"
    ) as temporary_name:
        temporary_root = Path(temporary_name)
        jobs: list[tuple[Path, Path]] = []
        for role in active_roles:
            role_rows = pending[role]
            points, counts, fiber_ids = geometry[role]
            score_matrix = np.column_stack([row[1] for row in role_rows])
            geometry_path = temporary_root / f"{role}_geometry.mat"
            savemat(
                geometry_path,
                {
                    "fibers": points,
                    "idx": counts.reshape(1, -1),
                    "fiber_ids": fiber_ids.reshape(-1, 1),
                    "score_matrix": score_matrix,
                },
                do_compression=False,
            )
            task_rows: list[dict[str, Any]] = []
            for score_column, (endpoint, scores, color_limit) in enumerate(
                role_rows,
                start=1,
            ):
                figures = (
                    endpoint.root
                    / "visualization/spatial_3d/coefficient/figures"
                )
                figures.mkdir(parents=True, exist_ok=True)
                task_rows.append(
                    {
                        "scale_id": endpoint.scale_id,
                        "model_role": role,
                        "score_column": score_column,
                        "color_limit": color_limit,
                        "colorbar_label": str(
                            context.config["fiber"]["labels"][
                                "target_conditioned_colorbar_template"
                            ]
                        ).format(
                            scale_display_name=endpoint.scale_display_name
                        ),
                        "output_directory": str(figures),
                        "scored_fiber_count": int(np.sum(np.isfinite(scores))),
                    }
                )
            for group_index, group in enumerate(
                _partition(task_rows, workers_per_role)
            ):
                task_path = (
                    temporary_root / f"{role}_tasks_{group_index:02d}.json"
                )
                task_path.write_text(
                    json.dumps(group, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                jobs.append((geometry_path, task_path))
        with ThreadPoolExecutor(max_workers=min(maximum_workers, len(jobs))) as pool:
            futures = [
                pool.submit(
                    _run_matlab_export,
                    matlab=matlab,
                    repository_root=repository_root,
                    geometry_path=geometry_path,
                    task_path=task_path,
                )
                for geometry_path, task_path in jobs
            ]
            for future in futures:
                future.result()

    for role in active_roles:
        for endpoint, scores, color_limit in pending[role]:
            component = endpoint.root / "visualization/spatial_3d/coefficient"
            expected = (
                component
                / "figures"
                / (
                    f"{endpoint.scale_id}_fiber_coefficient_"
                    f"{role}_view01.pdf"
                )
            )
            if not expected.is_file():
                raise ValueError(f"MATLAB did not publish the expected 3-D PDF: {expected}")
            manifest = {
                "status": "complete",
                "scale_id": endpoint.scale_id,
                "scale_display_name": endpoint.scale_display_name,
                "model_role": role,
                "connectome_id": context.connectome_id,
                "fiber_scope": "role_seed_connected_with_target_hit",
                "scored_fiber_count": int(np.sum(np.isfinite(scores))),
                "excluded_fiber_count": int(np.sum(~np.isfinite(scores))),
                "color_limits": [-color_limit, color_limit],
                "color_limit_scope": "scale_role",
                "colormap": "vik",
                "surface_inward_sampling_depth_mm": float(
                    context.config["surface"]["inward_sampling_depth_mm"]
                ),
                "strict_headless": True,
                "font_family": "Arial",
                "outputs": [f"figures/{expected.name}"],
            }
            _write_json(component / "export_manifest.json", manifest)
            _write_complete(component / "complete.json")
            results.append(manifest)
    return results


def run_individualized_target_postprocess(
    *,
    publication_root: str | Path,
    spatial_config_path: str | Path,
    shared_root: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Publish all individualized endpoint visualizations in place."""

    publication = Path(publication_root).expanduser().resolve()
    manifest_path = publication / "model_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"individualized model manifest is missing: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "completed":
        raise ValueError("individualized model manifest is not complete")
    root_complete = publication / "complete.json"
    if root_complete.is_file() and not force:
        return {
            "status": "complete",
            "resume_status": "reused",
            "publication_root": str(publication),
        }
    scale_catalog = _scale_catalog(manifest)
    resolved_shared = (
        Path(shared_root).expanduser().resolve()
        if shared_root is not None
        else publication.parent / "shared"
    )
    context = prepare_target_projection_context(
        spatial_config_path=spatial_config_path,
        shared_root=resolved_shared,
    )
    target_ids = tuple(value.roi_id for value in context.targets)
    if len(target_ids) != _TARGET_COUNT:
        raise ValueError("individualized visualization requires 17 configured targets")

    if force and root_complete.exists():
        _trash(root_complete)
    endpoints: list[_Endpoint] = []
    component_results: list[dict[str, Any]] = []
    for scale_id, display_name in scale_catalog:
        scale_root = publication / scale_id
        scale_complete = scale_root / "complete.json"
        if force and scale_complete.exists():
            _trash(scale_complete)
        for role in _ROLES:
            endpoint_root = scale_root / role
            final_model = _read_json(endpoint_root / "final_model.json")
            if (
                final_model.get("model_family") != "individualized_seed_target"
                or final_model.get("role") != role
                or final_model.get("scale_id") != scale_id
                or final_model.get("selected_tau_v_per_m") is None
            ):
                raise ValueError(
                    f"individualized final model is not realized: {scale_id}/{role}"
                )
            coefficients, stability, bootstrap = _endpoint_target_data(
                endpoint_root,
                target_ids,
            )
            endpoint = _Endpoint(
                scale_id=scale_id,
                scale_display_name=display_name,
                role=role,
                root=endpoint_root,
                coefficients=coefficients,
                stability=tuple(stability),
                bootstrap=tuple(bootstrap),
            )
            endpoints.append(endpoint)
            component_results.append(
                _render_paired_fit(
                    endpoint_root=endpoint_root,
                    scale_id=scale_id,
                    scale_display_name=display_name,
                    role=role,
                    force=force,
                )
            )
            component_results.append(
                _render_target_stability(
                    endpoint_root=endpoint_root,
                    scale_id=scale_id,
                    scale_display_name=display_name,
                    role=role,
                    target_ids=target_ids,
                    target_labels=context.target_labels,
                    stability=stability,
                    bootstrap=bootstrap,
                    force=force,
                )
            )
            component_results.append(
                _render_spatial_2d(
                    endpoint_root=endpoint_root,
                    scale_id=scale_id,
                    scale_display_name=display_name,
                    role=role,
                    coefficients=coefficients,
                    target_ids=target_ids,
                    context=context,
                    force=force,
                )
            )
    component_results.extend(
        _render_spatial_3d(
            endpoints=endpoints,
            context=context,
            force=force,
        )
    )
    expected_markers = (
        "visualization/paired_fit/complete.json",
        "visualization/spatial_2d/target_conditioned/all_coverage/complete.json",
        "visualization/spatial_3d/coefficient/complete.json",
        "visualization/target_coefficient_stability/complete.json",
    )
    for scale_id, _ in scale_catalog:
        scale_root = publication / scale_id
        for role in _ROLES:
            missing = [
                relative
                for relative in expected_markers
                if not (scale_root / role / relative).is_file()
            ]
            if missing:
                raise ValueError(
                    f"individualized visualization is incomplete for "
                    f"{scale_id}/{role}: {missing}"
                )
        _write_complete(scale_root / "complete.json")
    _write_complete(root_complete)
    return {
        "status": "complete",
        "resume_status": "computed",
        "publication_root": str(publication),
        "shared_root": str(resolved_shared),
        "scale_count": len(scale_catalog),
        "endpoint_count": len(endpoints),
        "component_count": len(component_results),
        "matlab_worker_default": max(1, (os.cpu_count() or 1) // 2),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-root", required=True)
    parser.add_argument("--spatial-config", required=True)
    parser.add_argument("--shared-root")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_individualized_target_postprocess(
        publication_root=args.publication_root,
        spatial_config_path=args.spatial_config,
        shared_root=args.shared_root,
        force=args.force,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RoleTargetProjection",
    "TargetProjectionContext",
    "prepare_target_projection_context",
    "run_individualized_target_postprocess",
]
