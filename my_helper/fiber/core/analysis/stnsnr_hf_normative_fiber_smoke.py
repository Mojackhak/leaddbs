#!/usr/bin/env python3
"""HF normative connectome fiber observed smoke driver."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

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
    RAW_CLINICAL_FILE,
    STIM_FILE,
    detect_asset_root,
    infer_scale_direction,
    parse_endpoint_scale,
    repo_root_from_file,
)
from stnsnr_four_model_stats import (
    FiberNetScoreResult,
    benefit_oriented_weights,
    candidate_mask_from_coverage,
    coverage_from_suprathreshold,
    fiber_net_score,
    fit_linear_prediction,
    partial_spearman_matrix,
    pearson_corr_columns,
    regression_metrics,
    suprathreshold_matrix,
)
from stnsnr_four_model_resolver import classify_prediction_status, finite_float
from stnsnr_hf_direct_voxel_smoke import (
    STIM_SHEET,
    SubjectRecord,
    collect_side_field_paths,
    filter_hf_stn_rows,
    flip_left_fields_with_matlab,
    fit_baseline_only,
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

NORM_FIBER_TAU_GRID = [400, 600, 800, 1000, 1200, 1500, 2000]
NORM_FIBER_COVERAGE_GRID = [5, 6, 7, 8, 10, 12]
NORM_FIBER_PRIMARY_TAU = 800
NORM_FIBER_PRIMARY_COVERAGE = 5
NORM_FIBER_SENSITIVITY_TAU = 1500.0
NORM_FIBER_SENSITIVITY_COVERAGE = 5
NORM_FIBER_SENSITIVITY_SWEET_COUNT = 1500
NORM_FIBER_SENSITIVITY_SOUR_COUNT = 500
NORM_FIBER_WEIGHTED_PEAK_FRACTION = 0.05


@dataclass(frozen=True)
class ImageSampler:
    path: str
    data: np.ndarray
    inv_affine: np.ndarray
    shape: tuple[int, int, int]


@dataclass(frozen=True)
class HFNormativeFiberAnalysisConfig:
    """Explicit inputs for one primary or resolver HF normative-fiber run."""

    scale: str
    endpoint_protocol: str
    endpoint_phase: str
    scale_direction: str
    subject_order: tuple[str, ...]
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    repo_root: Path
    matlab_bin: Path
    connectome_id: str
    connectome_label: str
    connectome_path: Path
    connectome_identity_source: str
    output_dir: Path
    preprocess_dir: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    sweet_fraction: float = 0.01
    sour_fraction: float = 0.005
    weighted_peak_fraction: float = NORM_FIBER_WEIGHTED_PEAK_FRACTION
    sweet_selected_min_count: int = 200
    sour_selected_min_count: int = 100
    weighted_peak_min_count: int = 20
    sensitivity_high_tau: float = NORM_FIBER_SENSITIVITY_TAU
    sensitivity_coverage: int = NORM_FIBER_SENSITIVITY_COVERAGE
    sensitivity_sweet_count: int = NORM_FIBER_SENSITIVITY_SWEET_COUNT
    sensitivity_sour_count: int = NORM_FIBER_SENSITIVITY_SOUR_COUNT
    resolver_minimum_adjacent_passing_cells: int = 2
    max_fibers: int = 0
    fiber_chunk_size: int = 10000
    force_flip: bool = False
    force_rebuild: bool = False
    dynamic_names: bool = True

    def __post_init__(self) -> None:
        if self.scale_direction not in {"lower", "higher"}:
            raise ValueError("scale_direction must be 'lower' or 'higher'")
        if not self.tau_grid or any(float(value) <= 0 for value in self.tau_grid):
            raise ValueError("tau_grid must contain positive values")
        if not self.coverage_grid or any(int(value) < 1 for value in self.coverage_grid):
            raise ValueError("coverage_grid must contain positive values")
        if self.primary_tau not in self.tau_grid:
            raise ValueError("primary_tau must be present in tau_grid")
        if self.primary_coverage not in self.coverage_grid:
            raise ValueError("primary_coverage must be present in coverage_grid")
        if self.resolver_minimum_adjacent_passing_cells < 1:
            raise ValueError("resolver_minimum_adjacent_passing_cells must be positive")
        if not 0 < self.sweet_fraction <= 1 or not 0 < self.sour_fraction <= 1:
            raise ValueError("fiber score fractions must be in (0, 1]")
        if not 0 < self.weighted_peak_fraction <= 1:
            raise ValueError("weighted_peak_fraction must be in (0, 1]")
        if min(
            self.sweet_selected_min_count,
            self.sour_selected_min_count,
            self.weighted_peak_min_count,
        ) < 1:
            raise ValueError("fiber score minimum counts must be positive")
        if self.sensitivity_high_tau <= 0 or self.sensitivity_coverage < 1:
            raise ValueError("cheap sensitivity tau/Coverage must be positive")
        if self.sensitivity_sweet_count < 1 or self.sensitivity_sour_count < 1:
            raise ValueError("cheap sensitivity fixed counts must be positive")
        if self.max_fibers < 0:
            raise ValueError("max_fibers cannot be negative")


class SidecarValidationError(RuntimeError):
    """Raised when exposure sidecars are partial, stale, or inconsistent."""


def _numeric_token(value: float) -> str:
    return f"{float(value):g}"


def hf_fiber_primary_branch_name(tau: float, coverage: int, *, legacy: bool = False) -> str:
    """Return a branch name tied to its actual primary grid cell."""
    if legacy:
        return f"peak_efield_tau{_numeric_token(tau)}_primary"
    return f"peak_efield_tau{_numeric_token(tau)}_cov{int(coverage)}_primary"


def hf_fiber_artifact_names(tau: float, coverage: int, *, dynamic: bool) -> dict[str, str]:
    """Return primary and resolver artifact names for one grid identity."""
    if not dynamic:
        return {
            "coverage_npy": "coverage_tau800.npy",
            "rho_npy": "rho_HF_float32.npy",
            "weights_npy": "M_HF_float32.npy",
            "coverage_column": "coverage_tau800",
            "weights_csv": "normative_HF_fiber_weights.csv",
            "scores_csv": "normative_HF_fiber_scores.csv",
            "loocv_predictions_csv": "normative_HF_fiber_loocv_predictions.csv",
            "mapping_qc_json": "normative_HF_fiber_mapping_qc.json",
            "generation_manifest_json": "normative_HF_fiber_generation_manifest.json",
            "resolver_scan_csv": "normative_HF_fiber_tau_coverage_source_resolver_scan.csv",
            "resolver_manifest_json": "normative_HF_fiber_tau_coverage_source_resolver_manifest.json",
            "selected_source_json": "normative_HF_fiber_selected_source.json",
        }
    cell = f"tau{_numeric_token(tau)}_cov{int(coverage)}"
    prefix = f"normative_HF_fiber_{cell}"
    return {
        "coverage_npy": f"coverage_{cell}.npy",
        "rho_npy": f"rho_HF_{cell}_float32.npy",
        "weights_npy": f"M_HF_{cell}_float32.npy",
        "coverage_column": f"coverage_{cell}",
        "weights_csv": f"{prefix}_weights.csv",
        "scores_csv": f"{prefix}_scores.csv",
        "loocv_predictions_csv": f"{prefix}_loocv_predictions.csv",
        "mapping_qc_json": f"{prefix}_mapping_qc.json",
        "generation_manifest_json": f"{prefix}_generation_manifest.json",
        "resolver_scan_csv": f"{prefix}_tau_coverage_source_resolver_scan.csv",
        "resolver_manifest_json": f"{prefix}_tau_coverage_source_resolver_manifest.json",
        "selected_source_json": f"{prefix}_selected_source.json",
    }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_array(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    """Return a content identity suitable for sidecar provenance."""
    resolved = Path(path).expanduser().resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": sha256_file(resolved),
    }


def configured_sidecar_cache_key(
    *,
    clinical_table: Path,
    stimulation_table: Path,
    connectome_path: Path,
    scale: str,
    protocol: str,
    phase: str,
    subject_order: Sequence[str],
    max_fibers: int,
) -> str:
    """Return a stable cache key for request-level sidecar dependencies."""
    def cache_identity(path: Path) -> dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            return {"path": str(resolved), "status": "missing"}
        return file_identity(resolved)

    payload = {
        "clinical_table": cache_identity(clinical_table),
        "stimulation_table": cache_identity(stimulation_table),
        "connectome": cache_identity(connectome_path),
        "scale": str(scale),
        "protocol": str(protocol),
        "phase": str(phase),
        "subject_order": [str(value) for value in subject_order],
        "max_fibers": int(max_fibers),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def build_exposure_sidecar_contract(
    data_mat: Path,
    records: Sequence[Any],
    *,
    max_fibers: int,
    input_identities: Mapping[str, Any],
    connectome_identity_source: str = "data.mat:idx",
) -> dict[str, Any]:
    """Build the exact provenance contract required to reuse an exposure sidecar."""
    data_path = Path(data_mat).expanduser().resolve()
    lengths = load_idx_lengths(data_path, max_fibers=max_fibers)
    fiber_ids = np.arange(1, lengths.size + 1, dtype=np.int64)
    return {
        "contract_version": 1,
        "subject_order": [str(record.subject_id) for record in records],
        "connectome_path": str(data_path),
        "connectome_fingerprint": sha256_file(data_path),
        "connectome_identity_source": str(connectome_identity_source),
        "fiber_axis_hash": sha256_array(fiber_ids),
        "fiber_axis_count": int(fiber_ids.size),
        "shape": [len(records), int(fiber_ids.size)],
        "max_fibers": int(max_fibers),
        "development_cap": int(max_fibers) if max_fibers > 0 else 0,
        "input_identities": json.loads(json.dumps(input_identities, sort_keys=True)),
    }


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(data), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_sidecar_completion_manifest_atomic(
    completion_json: Path,
    *,
    contract: Mapping[str, Any],
    output_npy: Path,
    fiber_ids_npy: Path,
) -> dict[str, Any]:
    """Publish completion last, after both immutable array artifacts exist."""
    x = np.load(output_npy, mmap_mode="r")
    fiber_ids = np.load(fiber_ids_npy, mmap_mode="r")
    manifest = {
        **dict(contract),
        "status": "complete",
        "artifacts": {
            "exposure": {**file_identity(output_npy), "shape": list(x.shape), "dtype": str(x.dtype)},
            "fiber_ids": {
                **file_identity(fiber_ids_npy),
                "shape": list(fiber_ids.shape),
                "dtype": str(fiber_ids.dtype),
                "axis_hash": sha256_array(fiber_ids),
            },
        },
    }
    _atomic_write_json(completion_json, manifest)
    return manifest


def _validate_identity_tree_current(value: Any, path: str = "input_identities") -> None:
    if isinstance(value, dict) and {"path", "size_bytes", "mtime_ns", "sha256"}.issubset(value):
        try:
            current = file_identity(Path(str(value["path"])))
        except (FileNotFoundError, OSError) as exc:
            raise SidecarValidationError(f"{path} is no longer readable: {exc}") from exc
        if current != value:
            raise SidecarValidationError(f"{path} no longer matches its recorded identity")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_identity_tree_current(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_identity_tree_current(item, f"{path}[{index}]")


def validate_completed_exposure_sidecar(
    output_npy: Path,
    fiber_ids_npy: Path,
    completion_json: Path,
    *,
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate completion, provenance, array integrity, and feature ordering."""
    missing_arrays = [str(path) for path in (output_npy, fiber_ids_npy) if not Path(path).is_file()]
    if missing_arrays:
        raise SidecarValidationError(f"sidecar arrays are partial or missing: {','.join(missing_arrays)}")
    if not Path(completion_json).is_file():
        raise SidecarValidationError(f"sidecar completion manifest is missing: {completion_json}")
    try:
        manifest = json.loads(Path(completion_json).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SidecarValidationError(f"sidecar completion manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("status") != "complete":
        raise SidecarValidationError("sidecar completion manifest is not complete")

    for key, expected in expected_contract.items():
        if manifest.get(key) != expected:
            raise SidecarValidationError(f"sidecar {key} does not match the requested contract")
    _validate_identity_tree_current(manifest.get("input_identities", {}))

    x = np.load(output_npy, mmap_mode="r")
    fiber_ids = np.load(fiber_ids_npy, mmap_mode="r")
    if list(x.shape) != manifest.get("shape"):
        raise SidecarValidationError("sidecar exposure shape does not match completion manifest")
    if fiber_ids.ndim != 1 or int(fiber_ids.size) != int(manifest.get("fiber_axis_count", -1)):
        raise SidecarValidationError("sidecar fiber-axis shape does not match completion manifest")
    axis_hash = sha256_array(fiber_ids)
    if axis_hash != manifest.get("fiber_axis_hash"):
        raise SidecarValidationError("sidecar fiber-axis hash does not match completion manifest")

    artifacts = manifest.get("artifacts", {})
    exposure_artifact = artifacts.get("exposure", {})
    fiber_artifact = artifacts.get("fiber_ids", {})
    if sha256_file(output_npy) != exposure_artifact.get("sha256"):
        raise SidecarValidationError("sidecar exposure artifact hash does not match completion manifest")
    if sha256_file(fiber_ids_npy) != fiber_artifact.get("sha256"):
        raise SidecarValidationError("sidecar fiber-axis artifact hash does not match completion manifest")
    if axis_hash != fiber_artifact.get("axis_hash"):
        raise SidecarValidationError("sidecar fiber-axis artifact ordering does not match completion manifest")
    return manifest


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


def _read_table(path: Path, *, sheet_name: str | None = None) -> pd.DataFrame:
    table_path = Path(path).expanduser().resolve()
    if table_path.suffix.lower() == ".csv":
        return pd.read_csv(table_path)
    if table_path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(table_path, sheet_name=sheet_name or 0)
    raise ValueError(f"unsupported table format: {table_path}")


def load_subject_records_from_table(
    clinical_table: Path,
    *,
    scale: str,
    protocol: str,
    phase: str,
    subject_order: Sequence[str] = (),
) -> list[SubjectRecord]:
    """Load one explicit endpoint without parsing protocol or phase from its scale."""
    raw_df = _read_table(clinical_table)
    required = {"ID", "Scale", "Protocol", "Phase", "Value", "Baseline"}
    missing = sorted(required - set(raw_df.columns))
    if missing:
        raise RuntimeError(f"clinical table is missing columns: {','.join(missing)}")
    subset = raw_df[
        raw_df["Scale"].astype(str).eq(scale)
        & raw_df["Protocol"].astype(str).eq(protocol)
        & raw_df["Phase"].astype(str).eq(phase)
    ].copy()
    duplicate_ids = sorted(subset.loc[subset.duplicated("ID", keep=False), "ID"].astype(str).unique())
    if duplicate_ids:
        raise RuntimeError(f"duplicate clinical endpoint rows: {','.join(duplicate_ids)}")
    subset["Value"] = pd.to_numeric(subset["Value"], errors="coerce")
    subset["Baseline"] = pd.to_numeric(subset["Baseline"], errors="coerce")
    subset = subset[np.isfinite(subset["Value"]) & np.isfinite(subset["Baseline"])].copy()
    by_subject = {
        str(row["ID"]): SubjectRecord(str(row["ID"]), float(row["Value"]), float(row["Baseline"]))
        for _, row in subset.iterrows()
    }
    requested = tuple(str(value) for value in subject_order)
    if requested:
        missing_subjects = [subject_id for subject_id in requested if subject_id not in by_subject]
        unexpected_subjects = sorted(set(by_subject) - set(requested))
        if missing_subjects or unexpected_subjects:
            details = []
            if missing_subjects:
                details.append("missing=" + ",".join(missing_subjects))
            if unexpected_subjects:
                details.append("unexpected=" + ",".join(unexpected_subjects))
            raise RuntimeError("clinical subject order does not match configured endpoint: " + ";".join(details))
        records = [by_subject[subject_id] for subject_id in requested]
    else:
        records = [by_subject[subject_id] for subject_id in sorted(by_subject)]
    if len(records) < 12 and not requested:
        raise RuntimeError(f"scale {scale!r} has only {len(records)} valid subjects")
    return records


def load_stimulation_table(path: Path) -> pd.DataFrame:
    """Load the explicitly configured stimulation table."""
    return _read_table(path, sheet_name=STIM_SHEET)


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
    input_identities: Mapping[str, Any] | None = None,
    connectome_identity_source: str = "data.mat:idx",
    output_filename: str = "X_HF_fiber_float32_subject_major.npy",
    fiber_ids_filename: str = "fiber_ids.npy",
    completion_filename: str = "sidecar_completion.json",
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    output_npy = preprocess_dir / output_filename
    fiber_ids_npy = preprocess_dir / fiber_ids_filename
    completion_json = preprocess_dir / completion_filename
    contract = build_exposure_sidecar_contract(
        data_mat,
        records,
        max_fibers=max_fibers,
        input_identities=input_identities or {},
        connectome_identity_source=connectome_identity_source,
    )
    existing = [path.is_file() for path in (output_npy, fiber_ids_npy, completion_json)]
    if any(existing) and not force_rebuild:
        manifest = validate_completed_exposure_sidecar(
            output_npy,
            fiber_ids_npy,
            completion_json,
            expected_contract=contract,
        )
        x = np.load(output_npy, mmap_mode="r")
        fiber_ids = np.load(fiber_ids_npy)
        return x, fiber_ids, {
            "status": "reused_validated_sidecar",
            "output_npy": str(output_npy),
            "fiber_ids_npy": str(fiber_ids_npy),
            "completion_json": str(completion_json),
            "n_subjects": int(x.shape[0]),
            "n_fibers": int(x.shape[1]),
            "fiber_axis_hash": manifest["fiber_axis_hash"],
            "connectome_fingerprint": manifest["connectome_fingerprint"],
        }

    temporary_output = output_npy.with_name(f".{output_npy.stem}.{uuid4().hex}.tmp.npy")
    temporary_fiber_ids = fiber_ids_npy.with_name(f".{fiber_ids_npy.stem}.{uuid4().hex}.tmp.npy")
    try:
        sidecar_qc = build_fiber_exposure_sidecar(
            data_mat,
            records,
            samplers,
            temporary_output,
            temporary_fiber_ids,
            max_fibers=max_fibers,
            fiber_chunk_size=fiber_chunk_size,
        )
        os.replace(temporary_output, output_npy)
        os.replace(temporary_fiber_ids, fiber_ids_npy)
        manifest = write_sidecar_completion_manifest_atomic(
            completion_json,
            contract=contract,
            output_npy=output_npy,
            fiber_ids_npy=fiber_ids_npy,
        )
    finally:
        for temporary in (temporary_output, temporary_fiber_ids):
            if temporary.exists():
                temporary.unlink()
    sidecar_qc.update(
        {
            "status": "built_atomic_sidecar",
            "output_npy": str(output_npy),
            "fiber_ids_npy": str(fiber_ids_npy),
            "completion_json": str(completion_json),
            "fiber_axis_hash": manifest["fiber_axis_hash"],
            "connectome_fingerprint": manifest["connectome_fingerprint"],
        }
    )
    return np.load(output_npy, mmap_mode="r"), np.load(fiber_ids_npy), sidecar_qc


def normative_fiber_min_fold_candidate_threshold(connectome: str) -> int:
    """Return the model-specified minimum fold candidate fiber count."""
    return 1000 if connectome == "dtor" else 100


def _strict_boolean(value: Any) -> bool:
    return isinstance(value, bool) and value


def normative_fiber_hard_computability_passes(row: dict[str, Any]) -> bool:
    """Return whether one normative fiber grid cell passes source computability."""
    min_fold = normative_fiber_min_fold_candidate_threshold(str(row.get("connectome", "")))
    return (
        finite_float(row.get("n_subjects")) >= 12
        and finite_float(row.get("fold_n_candidate_fibers_min")) >= min_fold
        and _strict_boolean(row.get("selected_fiber_pools_computable"))
        and _strict_boolean(row.get("netfiberscore_nonconstant_all_folds"))
        and _strict_boolean(row.get("y_base_nuisance_design_valid"))
        and _strict_boolean(row.get("all_predictions_finite"))
    )


def resolve_normative_fiber_source(
    rows: list[dict[str, Any]],
    *,
    connectome: str,
    tau_grid: Sequence[float] = NORM_FIBER_TAU_GRID,
    coverage_grid: Sequence[int] = NORM_FIBER_COVERAGE_GRID,
    primary_tau: float = NORM_FIBER_PRIMARY_TAU,
    primary_coverage: int = NORM_FIBER_PRIMARY_COVERAGE,
    minimum_adjacent_passing_cells: int = 2,
) -> dict[str, Any]:
    """Resolve HF normative fiber source and prediction status from scan rows."""
    if minimum_adjacent_passing_cells < 1:
        raise ValueError("minimum_adjacent_passing_cells must be positive")
    tau_values = [float(value) for value in tau_grid]
    coverage_values = [int(value) for value in coverage_grid]
    prepared_rows: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        out.setdefault("connectome", connectome)
        out["n_voxels_full"] = out.get("n_candidate_fibers", 0)
        out["fold_n_voxels_min"] = out.get("fold_n_candidate_fibers_min", 0)
        out["hfscore_nonconstant_all_folds"] = out.get("netfiberscore_nonconstant_all_folds", False)
        prepared_rows.append(out)

    def passes(row: dict[str, Any]) -> bool:
        return normative_fiber_hard_computability_passes(row)

    def grid_position(row: dict[str, Any]) -> tuple[int, int] | None:
        tau = finite_float(row.get("tau"))
        coverage = finite_float(row.get("coverage"))
        if tau not in tau_values or coverage not in coverage_values:
            return None
        return tau_values.index(tau), coverage_values.index(int(coverage))

    def adjacent_count(selected: dict[str, Any]) -> int:
        selected_position = grid_position(selected)
        if selected_position is None:
            return 0
        count = 0
        for row in prepared_rows:
            row_position = grid_position(row)
            if row_position is None or not passes(row):
                continue
            delta_tau = abs(row_position[0] - selected_position[0])
            delta_coverage = abs(row_position[1] - selected_position[1])
            if delta_tau <= 1 and delta_coverage <= 1 and delta_tau + delta_coverage > 0:
                count += 1
        return count

    support = {
        id(row): adjacent_count(row)
        for row in prepared_rows
    }
    stable = [row for row in prepared_rows if passes(row) and support[id(row)] >= minimum_adjacent_passing_cells]
    primary = next(
        (
            row
            for row in stable
            if finite_float(row.get("tau")) == float(primary_tau)
            and finite_float(row.get("coverage")) == int(primary_coverage)
        ),
        None,
    )
    if primary is not None:
        selected = primary
        source_status = "pre_specified_accepted"
        threshold_source = "pre_specified"
    elif stable:
        def fallback_key(row: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
            tau_distance = abs(finite_float(row.get("tau")) - float(primary_tau))
            coverage_distance = abs(finite_float(row.get("coverage")) - int(primary_coverage))
            return (
                tau_distance + coverage_distance,
                tau_distance,
                coverage_distance,
                -float(support[id(row)]),
                -finite_float(row.get("fold_n_candidate_fibers_min")),
                -finite_float(row.get("tau")),
            )

        selected = sorted(stable, key=fallback_key)[0]
        source_status = "scan_fallback_accepted"
        threshold_source = "scan_fallback"
    else:
        selected = None
        source_status = "absent_no_stable_grid"
        threshold_source = "none"

    resolved = {
        "source_status": source_status,
        "prediction_status": classify_prediction_status(selected) if selected is not None else "not_applicable",
        "threshold_source": threshold_source,
        "selected_tau": finite_float(selected.get("tau")) if selected is not None else None,
        "selected_coverage": int(finite_float(selected.get("coverage"))) if selected is not None else None,
        "selected_adjacent_passing_grid_cells": support[id(selected)] if selected is not None else 0,
        "source_failure_reasons": "" if selected is not None else "no_grid_cell_passed_resolver_policy",
    }
    return {
        "hf_norm_fiber_source_status": resolved["source_status"],
        "hf_norm_fiber_prediction_status": resolved["prediction_status"],
        "hf_norm_fiber_threshold_source": resolved["threshold_source"],
        "hf_norm_fiber_selected_tau_v_per_m": resolved["selected_tau"],
        "hf_norm_fiber_selected_coverage": resolved["selected_coverage"],
        "hf_norm_fiber_selected_adjacent_passing_grid_cells": resolved[
            "selected_adjacent_passing_grid_cells"
        ],
        "hf_norm_fiber_source_failure_reasons": resolved["source_failure_reasons"],
    }


def baseline_nuisance_design_valid_all_folds(y_base: np.ndarray) -> bool:
    """Return whether intercept-plus-baseline is estimable globally and per LOOCV fold."""
    baseline = np.asarray(y_base, dtype=float)
    if baseline.ndim != 1 or baseline.size < 4 or not np.all(np.isfinite(baseline)):
        return False
    for indices in (np.arange(baseline.size), *(
        np.delete(np.arange(baseline.size), heldout) for heldout in range(baseline.size)
    )):
        fold = baseline[indices]
        design = np.column_stack([np.ones(fold.size), fold])
        if fold.size <= design.shape[1] or np.nanstd(fold) == 0:
            return False
        if np.linalg.matrix_rank(design) != design.shape[1]:
            return False
    return True


def _top_fraction_mean(values: np.ndarray, fraction: float) -> tuple[np.ndarray, int]:
    if values.shape[1] == 0:
        return np.zeros(values.shape[0], dtype=float), 0
    count = max(1, int(np.ceil(float(fraction) * values.shape[1])))
    return np.mean(np.sort(values, axis=1)[:, -count:], axis=1), count


def fixed_count_fiber_net_score(
    exposure: np.ndarray,
    weights: np.ndarray,
    candidate_mask: np.ndarray,
    *,
    fiber_ids: Iterable[int],
    sweet_count: int,
    sour_count: int,
    peak_fraction: float,
) -> FiberNetScoreResult:
    """Compute the documented fixed top-count sweet/sour sensitivity score."""
    x = np.asarray(exposure, dtype=float)
    w = np.asarray(weights, dtype=float)
    candidate = np.asarray(candidate_mask, dtype=bool) & np.isfinite(w)
    ids = np.asarray(list(fiber_ids), dtype=np.int64)
    if x.ndim != 2 or x.shape[1] != w.size or ids.size != w.size or candidate.size != w.size:
        raise ValueError("fixed-count score inputs must share one fiber axis")
    if sweet_count < 1 or sour_count < 1 or not 0 < peak_fraction <= 1:
        raise ValueError("fixed-count score parameters must be positive")

    positive_cols = np.flatnonzero(candidate & (w > 0))
    negative_cols = np.flatnonzero(candidate & (w < 0))
    sweet_order = np.lexsort((ids[positive_cols], -w[positive_cols]))
    sour_order = np.lexsort((ids[negative_cols], w[negative_cols]))
    sweet_cols = positive_cols[sweet_order[: min(sweet_count, positive_cols.size)]]
    sour_cols = negative_cols[sour_order[: min(sour_count, negative_cols.size)]]
    sweet_weighted = x[:, sweet_cols] * w[sweet_cols] if sweet_cols.size else np.empty((x.shape[0], 0))
    sour_weighted = x[:, sour_cols] * (-w[sour_cols]) if sour_cols.size else np.empty((x.shape[0], 0))
    sweet_peak, n_sweet_peak = _top_fraction_mean(sweet_weighted, peak_fraction)
    sour_peak, n_sour_peak = _top_fraction_mean(sour_weighted, peak_fraction)
    return FiberNetScoreResult(
        sweet_peak5=sweet_peak,
        sour_peak5=sour_peak,
        net_score=sweet_peak - sour_peak,
        sweet_fiber_ids=ids[sweet_cols],
        sour_fiber_ids=ids[sour_cols],
        n_sweet_peak_fibers=n_sweet_peak,
        n_sour_peak_fibers=n_sour_peak,
    )


def _fiber_score_for_selection(
    exposure: np.ndarray,
    weights: np.ndarray,
    candidate: np.ndarray,
    fiber_ids: np.ndarray,
    *,
    sweet_fraction: float,
    sour_fraction: float,
    peak_fraction: float,
    sweet_count: int | None,
    sour_count: int | None,
) -> FiberNetScoreResult:
    if sweet_count is None and sour_count is None:
        return fiber_net_score(
            exposure,
            weights,
            candidate,
            fiber_ids=fiber_ids,
            sweet_percent=sweet_fraction,
            sour_percent=sour_fraction,
            peak_percent=peak_fraction,
        )
    if sweet_count is None or sour_count is None:
        raise ValueError("sweet_count and sour_count must be configured together")
    return fixed_count_fiber_net_score(
        exposure,
        weights,
        candidate,
        fiber_ids=fiber_ids,
        sweet_count=sweet_count,
        sour_count=sour_count,
        peak_fraction=peak_fraction,
    )


def run_observed_loocv(
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    subject_ids: list[str],
    scale_direction: str,
    tau: float,
    min_coverage: int,
    *,
    sweet_fraction: float = 0.01,
    sour_fraction: float = 0.005,
    peak_fraction: float = NORM_FIBER_WEIGHTED_PEAK_FRACTION,
    sweet_count: int | None = None,
    sour_count: int | None = None,
    fold_weights_output: Path | None = None,
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
    full_net = _fiber_score_for_selection(
        np.asarray(x),
        weights,
        candidate,
        fiber_ids,
        sweet_fraction=sweet_fraction,
        sour_fraction=sour_fraction,
        peak_fraction=peak_fraction,
        sweet_count=sweet_count,
        sour_count=sour_count,
    )

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
    fold_candidate_counts: list[int] = []
    net_score_nonconstant_all_folds = True
    fold_weight_matrix = None
    if fold_weights_output is not None:
        fold_weights_output.parent.mkdir(parents=True, exist_ok=True)
        fold_weight_matrix = np.lib.format.open_memmap(
            fold_weights_output,
            mode="w+",
            dtype=np.float32,
            shape=(y_post.shape[0], x.shape[1]),
        )
    for heldout in range(y_post.shape[0]):
        train = np.array([idx for idx in range(y_post.shape[0]) if idx != heldout], dtype=int)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty candidate set for held-out {subject_ids[heldout]}")
        fold_candidate_counts.append(int(np.count_nonzero(candidate_fold)))
        rho_fold = partial_spearman_matrix(y_post[train], np.asarray(x[train][:, candidate_fold]), y_base[train])
        weights_fold = np.full(x.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        if fold_weight_matrix is not None:
            fold_weight_matrix[heldout] = weights_fold
        fold_net = _fiber_score_for_selection(
            np.asarray(x),
            weights_fold,
            candidate_fold,
            fiber_ids,
            sweet_fraction=sweet_fraction,
            sour_fraction=sour_fraction,
            peak_fraction=peak_fraction,
            sweet_count=sweet_count,
            sour_count=sour_count,
        )
        if np.nanstd(fold_net.net_score[train]) == 0:
            net_score_nonconstant_all_folds = False
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

    if fold_weight_matrix is not None:
        fold_weight_matrix.flush()
    metrics = regression_metrics(y_post, pred, pred_base)
    finite_predictions = bool(np.all(np.isfinite(pred)) and np.all(np.isfinite(pred_base)))
    y_base_nuisance_valid = baseline_nuisance_design_valid_all_folds(y_base)
    fold_count_array = np.asarray(fold_candidate_counts, dtype=float)
    qc = {
        "tau_v_per_m": tau,
        "min_coverage": min_coverage,
        "n_subjects": int(y_post.shape[0]),
        "n_fibers": int(x.shape[1]),
        "n_candidate_fibers": int(np.count_nonzero(candidate)),
        "fold_n_candidate_fibers_min": int(np.nanmin(fold_count_array)) if fold_count_array.size else 0,
        "fold_n_candidate_fibers_median": float(np.nanmedian(fold_count_array)) if fold_count_array.size else 0.0,
        "fold_n_candidate_fibers_max": int(np.nanmax(fold_count_array)) if fold_count_array.size else 0,
        "selected_fiber_pools_computable": bool(full_net.sweet_fiber_ids.size > 0 and full_net.sour_fiber_ids.size > 0),
        "netfiberscore_nonconstant_all_folds": net_score_nonconstant_all_folds,
        "y_base_nuisance_design_valid": y_base_nuisance_valid,
        "all_predictions_finite": finite_predictions,
        "coverage_min": int(np.min(coverage)) if coverage.size else 0,
        "coverage_max": int(np.max(coverage)) if coverage.size else 0,
        "coverage_mean": float(np.mean(coverage)) if coverage.size else 0.0,
        "n_sweet_selected_fibers": int(full_net.sweet_fiber_ids.size),
        "n_sour_selected_fibers": int(full_net.sour_fiber_ids.size),
        "score_selection": {
            "mode": "fixed_count" if sweet_count is not None else "fraction",
            "sweet_fraction": sweet_fraction if sweet_count is None else None,
            "sour_fraction": sour_fraction if sour_count is None else None,
            "sweet_count": sweet_count,
            "sour_count": sour_count,
            "weighted_peak_fraction": peak_fraction,
        },
        "loocv_metrics": metrics,
        "resampling_status": "not_run_smoke_observed_only",
    }
    return score_rows, fold_rows, qc, coverage, rho, weights


def _fit_heldout_ols(
    train_y: np.ndarray,
    train_predictors: np.ndarray,
    test_predictors: np.ndarray,
) -> tuple[float, np.ndarray, bool]:
    y = np.asarray(train_y, dtype=float)
    train = np.asarray(train_predictors, dtype=float)
    test = np.asarray(test_predictors, dtype=float)
    if train.ndim == 1:
        train = train[:, None]
    if test.ndim == 1:
        test = test[None, :]
    train_design = np.column_stack([np.ones(y.size), train])
    test_design = np.column_stack([np.ones(test.shape[0]), test])
    valid = (
        y.size > train_design.shape[1]
        and np.all(np.isfinite(y))
        and np.all(np.isfinite(train_design))
        and np.all(np.isfinite(test_design))
        and np.linalg.matrix_rank(train_design) == train_design.shape[1]
    )
    if not valid:
        return np.nan, np.full(train_design.shape[1], np.nan), False
    beta, *_ = np.linalg.lstsq(train_design, y, rcond=None)
    return float((test_design @ beta)[0]), beta, True


def _plain_exposure_summaries(
    x: np.ndarray,
    tau: float,
    peak_fraction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    exposure = np.asarray(x, dtype=float)
    touched = exposure > float(tau)
    touched_count = np.count_nonzero(touched, axis=1).astype(np.int64)
    exposure_sum = np.sum(exposure, axis=1)
    exposure_top5 = np.zeros(exposure.shape[0], dtype=float)
    for row_index in range(exposure.shape[0]):
        values = exposure[row_index, touched[row_index]]
        if values.size:
            count = max(1, int(np.ceil(float(peak_fraction) * values.size)))
            exposure_top5[row_index] = float(np.mean(np.sort(values)[-count:]))
    return touched_count, exposure_sum, exposure_top5


def compute_plain_connected_control(
    *,
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    subject_ids: list[str],
    scale_direction: str,
    tau: float,
    min_coverage: int,
    peak_fraction: float = NORM_FIBER_WEIGHTED_PEAK_FRACTION,
) -> dict[str, Any]:
    """Compute the documented outcome-independent exposure control and four LOOCV models."""
    exposure = np.asarray(x, dtype=np.float32)
    outcome = np.asarray(y_post, dtype=float)
    baseline = np.asarray(y_base, dtype=float)
    ids = np.asarray(fiber_ids, dtype=np.int64)
    touched_count, exposure_sum, exposure_top5 = _plain_exposure_summaries(
        exposure,
        tau,
        peak_fraction,
    )
    s_tau = suprathreshold_matrix(exposure, tau)
    coverage = coverage_from_suprathreshold(s_tau)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    if not np.any(candidate):
        raise RuntimeError("empty primary candidate set for plain connected control")

    rho = np.full(exposure.shape[1], np.nan, dtype=np.float32)
    rho[candidate] = partial_spearman_matrix(outcome, exposure[:, candidate], baseline).astype(np.float32)
    weights = benefit_oriented_weights(rho, scale_direction).astype(np.float32)
    full_net = fiber_net_score(exposure, weights, candidate, fiber_ids=ids)
    subject_rows = [
        {
            "subject_id": subject_id,
            "Y_post": float(outcome[index]),
            "Y_base": float(baseline[index]),
            "PlainTouchedCount": int(touched_count[index]),
            "PlainExposureSum": float(exposure_sum[index]),
            "PlainExposureTop5": float(exposure_top5[index]),
            "NetFiberScore": float(full_net.net_score[index]),
        }
        for index, subject_id in enumerate(subject_ids)
    ]

    model_names = (
        "baseline_only",
        "plain_plus_baseline",
        "net_plus_baseline",
        "joint_net_plain_baseline",
    )
    predictions = {name: np.full(outcome.size, np.nan, dtype=float) for name in model_names}
    coefficients: dict[str, list[np.ndarray]] = {name: [] for name in model_names}
    valid_folds = {name: True for name in model_names}
    fold_rows: list[dict[str, Any]] = []
    for heldout in range(outcome.size):
        train = np.delete(np.arange(outcome.size), heldout)
        coverage_fold = coverage - s_tau[heldout].astype(np.int32)
        candidate_fold = candidate_mask_from_coverage(coverage_fold, min_coverage)
        if not np.any(candidate_fold):
            raise RuntimeError(f"empty plain-control candidate set for held-out {subject_ids[heldout]}")
        rho_fold = partial_spearman_matrix(outcome[train], exposure[train][:, candidate_fold], baseline[train])
        weights_fold = np.full(exposure.shape[1], np.nan, dtype=np.float32)
        weights_fold[candidate_fold] = benefit_oriented_weights(rho_fold, scale_direction).astype(np.float32)
        fold_net = fiber_net_score(exposure, weights_fold, candidate_fold, fiber_ids=ids)
        predictor_sets = {
            "baseline_only": (baseline[train, None], baseline[[heldout], None]),
            "plain_plus_baseline": (
                np.column_stack([exposure_top5[train], baseline[train]]),
                np.column_stack([exposure_top5[[heldout]], baseline[[heldout]]]),
            ),
            "net_plus_baseline": (
                np.column_stack([fold_net.net_score[train], baseline[train]]),
                np.column_stack([fold_net.net_score[[heldout]], baseline[[heldout]]]),
            ),
            "joint_net_plain_baseline": (
                np.column_stack([fold_net.net_score[train], exposure_top5[train], baseline[train]]),
                np.column_stack(
                    [fold_net.net_score[[heldout]], exposure_top5[[heldout]], baseline[[heldout]]]
                ),
            ),
        }
        row = {"fold_id": heldout + 1, "heldout_subject_id": subject_ids[heldout]}
        for name, (train_predictors, test_predictors) in predictor_sets.items():
            prediction, beta, valid = _fit_heldout_ols(outcome[train], train_predictors, test_predictors)
            predictions[name][heldout] = prediction
            coefficients[name].append(beta)
            valid_folds[name] = valid_folds[name] and valid
            row[f"prediction_{name}"] = prediction
        fold_rows.append(row)

    baseline_prediction = predictions["baseline_only"]
    model_rows: list[dict[str, Any]] = []
    metrics_by_name: dict[str, dict[str, float]] = {}
    for name in model_names:
        metrics = regression_metrics(outcome, predictions[name], baseline_prediction)
        metrics_by_name[name] = metrics
        beta_matrix = np.asarray(coefficients[name], dtype=float)
        model_rows.append(
            {
                "model": name,
                **metrics,
                "all_folds_full_rank": bool(valid_folds[name]),
                "all_predictions_finite": bool(np.all(np.isfinite(predictions[name]))),
                "median_intercept": float(np.nanmedian(beta_matrix[:, 0])),
                "median_primary_beta": float(np.nanmedian(beta_matrix[:, 1])),
            }
        )

    corr = float(pearson_corr_columns(full_net.net_score, exposure_top5)[0])
    if not np.all(np.isfinite(exposure_top5)):
        branch_status = "failed_plain_exposure_not_computable"
    elif not valid_folds["plain_plus_baseline"]:
        branch_status = "failed_plain_model_singular"
    elif not valid_folds["joint_net_plain_baseline"]:
        branch_status = "failed_joint_model_singular"
    elif not np.isfinite(corr):
        branch_status = "failed_net_plain_correlation_not_computable"
    elif abs(corr) >= 0.95:
        branch_status = "complete_severe_collinearity_warning"
    elif abs(corr) >= 0.85:
        branch_status = "complete_high_collinearity_warning"
    else:
        branch_status = "complete"

    net_metrics = metrics_by_name["net_plus_baseline"]
    plain_metrics = metrics_by_name["plain_plus_baseline"]
    net_beta = model_rows[2]["median_primary_beta"]
    joint_net_beta = model_rows[3]["median_primary_beta"]
    expected_sign = -1.0 if scale_direction == "lower" else 1.0
    plain_similar_or_better = (
        finite_float(plain_metrics.get("mae")) <= finite_float(net_metrics.get("mae"))
        or finite_float(plain_metrics.get("rmse")) <= finite_float(net_metrics.get("rmse"))
    )
    net_loses_benefit_sign = bool(
        np.isfinite(net_beta)
        and np.isfinite(joint_net_beta)
        and net_beta * expected_sign > 0
        and joint_net_beta * expected_sign <= 0
    )
    burden_dominated = bool(plain_similar_or_better or net_loses_benefit_sign or abs(corr) >= 0.95)
    return {
        "branch": "plain_connected_streamline_control",
        "branch_status": branch_status,
        "source_classification_feedback": "none",
        "subject_rows": subject_rows,
        "fold_rows": fold_rows,
        "model_rows": model_rows,
        "corr_NetFiberScore_PlainExposureTop5": corr,
        "collinearity_band": "severe" if abs(corr) >= 0.95 else "high" if abs(corr) >= 0.85 else "ideal",
        "plain_similar_or_better_than_net": bool(plain_similar_or_better),
        "net_loses_benefit_sign_after_plain": net_loses_benefit_sign,
        "hf_norm_fiber_burden_dominated": burden_dominated,
        "tau_v_per_m": float(tau),
        "min_coverage": int(min_coverage),
    }


def _normative_scan_empty_row(
    *,
    connectome: str,
    tau: int,
    coverage: int,
    n_subjects: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "connectome": connectome,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": n_subjects,
        "n_candidate_fibers": 0,
        "fold_n_candidate_fibers_min": 0,
        "fold_n_candidate_fibers_median": 0,
        "fold_n_candidate_fibers_max": 0,
        "selected_fiber_pools_computable": False,
        "netfiberscore_nonconstant_all_folds": False,
        "y_base_nuisance_design_valid": False,
        "all_predictions_finite": False,
        "loocv_spearman_rho": np.nan,
        "loocv_pearson_r": np.nan,
        "q2": np.nan,
        "mae_model": np.nan,
        "mae_baseline": np.nan,
        "rmse_model": np.nan,
        "rmse_baseline": np.nan,
        "passes_all_hard_filters": False,
        "hf_norm_fiber_prediction_status": "not_applicable",
        "failure_reason": reason,
    }


def _baseline_error_metrics(fold_rows: list[dict[str, Any]]) -> dict[str, float]:
    y = np.array([row["Y_post"] for row in fold_rows], dtype=float)
    pred = np.array([row["prediction_NetFiberScore_model"] for row in fold_rows], dtype=float)
    pred_base = np.array([row["prediction_baseline_only"] for row in fold_rows], dtype=float)
    finite_model = np.isfinite(y) & np.isfinite(pred)
    finite_base = np.isfinite(y) & np.isfinite(pred_base)
    residual_model = y[finite_model] - pred[finite_model]
    residual_base = y[finite_base] - pred_base[finite_base]
    return {
        "mae_model": float(np.mean(np.abs(residual_model))) if residual_model.size else np.nan,
        "rmse_model": float(np.sqrt(np.mean(residual_model * residual_model))) if residual_model.size else np.nan,
        "mae_baseline": float(np.mean(np.abs(residual_base))) if residual_base.size else np.nan,
        "rmse_baseline": float(np.sqrt(np.mean(residual_base * residual_base))) if residual_base.size else np.nan,
    }


def evaluate_normative_fiber_grid_cell(
    *,
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    subject_ids: list[str],
    scale_direction: str,
    connectome: str,
    tau: int,
    coverage: int,
    sweet_fraction: float = 0.01,
    sour_fraction: float = 0.005,
    peak_fraction: float = NORM_FIBER_WEIGHTED_PEAK_FRACTION,
) -> dict[str, Any]:
    """Evaluate one HF normative fiber tau/Coverage resolver grid cell."""
    try:
        _, fold_rows, qc, _, _, _ = run_observed_loocv(
            x=x,
            fiber_ids=fiber_ids,
            y_post=y_post,
            y_base=y_base,
            subject_ids=subject_ids,
            scale_direction=scale_direction,
            tau=float(tau),
            min_coverage=int(coverage),
            sweet_fraction=sweet_fraction,
            sour_fraction=sour_fraction,
            peak_fraction=peak_fraction,
        )
    except Exception as exc:
        return _normative_scan_empty_row(
            connectome=connectome,
            tau=tau,
            coverage=coverage,
            n_subjects=int(y_post.shape[0]),
            reason=str(exc),
        )

    baseline_errors = _baseline_error_metrics(fold_rows)
    metrics = qc.get("loocv_metrics", {})
    row = {
        "connectome": connectome,
        "tau": tau,
        "coverage": coverage,
        "n_subjects": int(y_post.shape[0]),
        "n_candidate_fibers": int(qc.get("n_candidate_fibers", 0)),
        "fold_n_candidate_fibers_min": int(qc.get("fold_n_candidate_fibers_min", 0)),
        "fold_n_candidate_fibers_median": float(qc.get("fold_n_candidate_fibers_median", 0.0)),
        "fold_n_candidate_fibers_max": int(qc.get("fold_n_candidate_fibers_max", 0)),
        "selected_fiber_pools_computable": _strict_boolean(qc.get("selected_fiber_pools_computable", False)),
        "netfiberscore_nonconstant_all_folds": _strict_boolean(qc.get("netfiberscore_nonconstant_all_folds", False)),
        "y_base_nuisance_design_valid": _strict_boolean(qc.get("y_base_nuisance_design_valid", False)),
        "all_predictions_finite": _strict_boolean(qc.get("all_predictions_finite", False)),
        "loocv_spearman_rho": metrics.get("spearman_rho", np.nan),
        "loocv_pearson_r": metrics.get("pearson_r", np.nan),
        "q2": metrics.get("q2", np.nan),
        "mae_model": baseline_errors["mae_model"],
        "mae_baseline": baseline_errors["mae_baseline"],
        "rmse_model": baseline_errors["rmse_model"],
        "rmse_baseline": baseline_errors["rmse_baseline"],
        "failure_reason": "",
    }
    row["passes_all_hard_filters"] = normative_fiber_hard_computability_passes(row)
    row["hf_norm_fiber_prediction_status"] = (
        classify_prediction_status(
            {
                "mae_model": row["mae_model"],
                "mae_baseline": row["mae_baseline"],
                "rmse_model": row["rmse_model"],
                "rmse_baseline": row["rmse_baseline"],
            }
        )
        if row["passes_all_hard_filters"]
        else "not_applicable"
    )
    return row


def write_normative_fiber_source_scan_outputs(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]],
    resolved: dict[str, Any],
    manifest: dict[str, Any],
    artifact_names: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Write source resolver scan outputs for one HF normative fiber branch."""
    output_dir.mkdir(parents=True, exist_ok=True)
    names = artifact_names or hf_fiber_artifact_names(
        NORM_FIBER_PRIMARY_TAU,
        NORM_FIBER_PRIMARY_COVERAGE,
        dynamic=False,
    )
    scan_csv = output_dir / names["resolver_scan_csv"]
    summary_json = output_dir / names["resolver_manifest_json"]
    fieldnames = [
        "connectome",
        "tau",
        "coverage",
        "n_subjects",
        "n_candidate_fibers",
        "fold_n_candidate_fibers_min",
        "fold_n_candidate_fibers_median",
        "fold_n_candidate_fibers_max",
        "selected_fiber_pools_computable",
        "netfiberscore_nonconstant_all_folds",
        "y_base_nuisance_design_valid",
        "all_predictions_finite",
        "loocv_spearman_rho",
        "loocv_pearson_r",
        "q2",
        "mae_model",
        "mae_baseline",
        "rmse_model",
        "rmse_baseline",
        "passes_all_hard_filters",
        "hf_norm_fiber_prediction_status",
        "failure_reason",
    ]
    write_csv(scan_csv, rows, fieldnames)
    write_json(
        summary_json,
        {
            **manifest,
            **resolved,
            "n_grid_cells": len(rows),
            "n_passing_grid_cells": int(sum(_strict_boolean(row.get("passes_all_hard_filters")) for row in rows)),
            "outputs": {"scan_csv": str(scan_csv), "manifest_json": str(summary_json)},
        },
    )
    return {"scan_csv": str(scan_csv), "manifest_json": str(summary_json)}


def _load_configured_records(config: HFNormativeFiberAnalysisConfig) -> list[SubjectRecord]:
    return load_subject_records_from_table(
        config.clinical_table,
        scale=config.scale,
        protocol=config.endpoint_protocol,
        phase=config.endpoint_phase,
        subject_order=config.subject_order,
    )


def _base_sidecar_input_identities(config: HFNormativeFiberAnalysisConfig) -> dict[str, Any]:
    return {
        "clinical_table": file_identity(config.clinical_table),
        "stimulation_table": file_identity(config.stimulation_table),
    }


def _sampling_input_identities(
    config: HFNormativeFiberAnalysisConfig,
    samplers: Mapping[str, Mapping[str, Sequence[ImageSampler]]],
    sampler_qc: Mapping[str, Any],
) -> dict[str, Any]:
    identities = _base_sidecar_input_identities(config)
    paths: set[Path] = set()
    for subject_samplers in samplers.values():
        for side_samplers in subject_samplers.values():
            paths.update(Path(sampler.path).resolve() for sampler in side_samplers)
    for row in sampler_qc.get("side_fields", []):
        paths.update(Path(value).resolve() for value in row.get("source_paths", []))
    identities["efield_inputs"] = [file_identity(path) for path in sorted(paths)]
    return identities


def _load_completed_exposure_for_config(
    config: HFNormativeFiberAnalysisConfig,
    records: Sequence[SubjectRecord],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    output_npy = config.preprocess_dir / "X_HF_fiber_float32_subject_major.npy"
    fiber_ids_npy = config.preprocess_dir / "fiber_ids.npy"
    completion_json = config.preprocess_dir / "sidecar_completion.json"
    if not completion_json.is_file():
        raise SidecarValidationError(f"sidecar completion manifest is missing: {completion_json}")
    try:
        stored = json.loads(completion_json.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SidecarValidationError(f"sidecar completion manifest is unreadable: {exc}") from exc
    stored_inputs = stored.get("input_identities", {})
    current_base = _base_sidecar_input_identities(config)
    for key, identity in current_base.items():
        if stored_inputs.get(key) != identity:
            raise SidecarValidationError(f"sidecar input_identities.{key} does not match the configured input")
    contract = build_exposure_sidecar_contract(
        config.connectome_path,
        records,
        max_fibers=config.max_fibers,
        input_identities=stored_inputs,
        connectome_identity_source=config.connectome_identity_source,
    )
    manifest = validate_completed_exposure_sidecar(
        output_npy,
        fiber_ids_npy,
        completion_json,
        expected_contract=contract,
    )
    return np.load(output_npy, mmap_mode="r"), np.load(fiber_ids_npy), manifest


def _feature_axis_payload(
    config: HFNormativeFiberAnalysisConfig,
    fiber_ids: np.ndarray,
) -> dict[str, Any]:
    return {
        "ids_path": str(config.preprocess_dir / "fiber_ids.npy"),
        "count": int(fiber_ids.size),
        "sha256": sha256_array(fiber_ids),
        "identity_source": config.connectome_identity_source,
    }


def _prepare_configured_sidecar(
    config: HFNormativeFiberAnalysisConfig,
) -> tuple[list[SubjectRecord], np.ndarray, np.ndarray, dict[str, Any], dict[str, Any], dict[str, Any]]:
    config.preprocess_dir.mkdir(parents=True, exist_ok=True)
    if not config.connectome_path.is_file():
        raise RuntimeError(f"connectome data.mat missing: {config.connectome_path}")
    records = _load_configured_records(config)
    subject_ids = [record.subject_id for record in records]
    stim_rows = filter_hf_stn_rows(
        load_stimulation_table(config.stimulation_table),
        set(subject_ids),
        protocol=config.endpoint_protocol,
        phase=config.endpoint_phase,
    )
    samplers, sampler_qc = prepare_subject_samplers(
        records=records,
        stim_rows=stim_rows,
        derivatives_root=config.derivatives_root,
        repo_root=config.repo_root,
        matlab_bin=config.matlab_bin,
        preprocess_dir=config.preprocess_dir,
        force_flip=config.force_flip,
    )
    input_identities = _sampling_input_identities(config, samplers, sampler_qc)
    _, _, sidecar_qc = load_or_build_exposure(
        config.connectome_path,
        records,
        samplers,
        config.preprocess_dir,
        max_fibers=config.max_fibers,
        fiber_chunk_size=config.fiber_chunk_size,
        force_rebuild=config.force_rebuild,
        input_identities=input_identities,
        connectome_identity_source=config.connectome_identity_source,
    )
    x, fiber_ids, manifest = _load_completed_exposure_for_config(config, records)
    return records, x, fiber_ids, sampler_qc, sidecar_qc, manifest


def run_hf_normative_fiber_sidecar_configured(config: HFNormativeFiberAnalysisConfig) -> dict[str, Any]:
    """Build or strictly reuse the exposure cache and publish task-local equivalence artifacts."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    records, x, fiber_ids, sampler_qc, sidecar_qc, manifest = _prepare_configured_sidecar(config)
    all_finite = all(bool(np.all(np.isfinite(np.asarray(x[index])))) for index in range(x.shape[0]))
    all_nonnegative = all(bool(np.all(np.asarray(x[index]) >= 0)) for index in range(x.shape[0]))
    sequential_axis = bool(np.array_equal(fiber_ids, np.arange(1, fiber_ids.size + 1, dtype=np.int64)))
    if not all_finite or not all_nonnegative or not sequential_axis:
        raise SidecarValidationError(
            "sidecar equivalence failed: "
            f"all_finite={all_finite},all_nonnegative={all_nonnegative},sequential_axis={sequential_axis}"
        )

    sidecar_index = config.output_dir / "hf_fiber_sidecar_index.json"
    qc_path = config.output_dir / "hf_fiber_sidecar_equivalence_qc.json"
    _atomic_write_json(
        sidecar_index,
        {
            "status": "complete",
            "cache_root": str(config.preprocess_dir),
            "exposure_matrix": str(config.preprocess_dir / "X_HF_fiber_float32_subject_major.npy"),
            "fiber_ids": str(config.preprocess_dir / "fiber_ids.npy"),
            "completion_manifest": str(config.preprocess_dir / "sidecar_completion.json"),
            "subject_order": [record.subject_id for record in records],
            "feature_axis": _feature_axis_payload(config, fiber_ids),
            "shape": list(x.shape),
            "connectome_fingerprint": manifest["connectome_fingerprint"],
            "max_fibers": config.max_fibers,
        },
    )
    _atomic_write_json(
        qc_path,
        {
            "status": "PASS",
            "reuse_status": sidecar_qc["status"],
            "all_values_finite": all_finite,
            "all_values_nonnegative": all_nonnegative,
            "fiber_axis_sequential": sequential_axis,
            "subject_order_matches": [record.subject_id for record in records] == list(config.subject_order),
            "shape_matches_completion": list(x.shape) == manifest["shape"],
            "fiber_axis_hash_matches": sha256_array(fiber_ids) == manifest["fiber_axis_hash"],
            "sampler_qc": sampler_qc,
            "sidecar_qc": sidecar_qc,
        },
    )
    return {
        "artifacts": {
            "sidecar_index": str(sidecar_index),
            "qc": str(qc_path),
        }
    }


def run_hf_normative_fiber_primary_configured(config: HFNormativeFiberAnalysisConfig) -> dict[str, Any]:
    """Run the primary HF fiber cell from explicit configured identities."""
    started = time.time()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    records, x, fiber_ids, sampler_qc, sidecar_qc, _ = _prepare_configured_sidecar(config)
    subject_ids = [record.subject_id for record in records]
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    score_rows, fold_rows, qc, coverage, rho, weights = run_observed_loocv(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        y_base=y_base,
        subject_ids=subject_ids,
        scale_direction=config.scale_direction,
        tau=config.primary_tau,
        min_coverage=config.primary_coverage,
        sweet_fraction=config.sweet_fraction,
        sour_fraction=config.sour_fraction,
        peak_fraction=config.weighted_peak_fraction,
    )

    names = hf_fiber_artifact_names(config.primary_tau, config.primary_coverage, dynamic=config.dynamic_names)
    candidate = candidate_mask_from_coverage(coverage, config.primary_coverage)
    coverage_column = names["coverage_column"]
    weight_rows = [
        {
            "fiber_id": int(fiber_ids[col]),
            coverage_column: int(coverage[col]),
            "rho_HF": float(rho[col]) if np.isfinite(rho[col]) else "",
            "M_HF": float(weights[col]) if np.isfinite(weights[col]) else "",
            "is_candidate": True,
        }
        for col in np.where(candidate)[0]
    ]
    np.save(config.preprocess_dir / names["coverage_npy"], coverage.astype(np.int16))
    np.save(config.preprocess_dir / names["rho_npy"], rho.astype(np.float32))
    np.save(config.preprocess_dir / names["weights_npy"], weights.astype(np.float32))
    weights_csv = config.output_dir / names["weights_csv"]
    scores_csv = config.output_dir / names["scores_csv"]
    predictions_csv = config.output_dir / names["loocv_predictions_csv"]
    mapping_qc_json = config.output_dir / names["mapping_qc_json"]
    generation_manifest_json = config.output_dir / names["generation_manifest_json"]
    write_csv(weights_csv, weight_rows, ["fiber_id", coverage_column, "rho_HF", "M_HF", "is_candidate"])
    write_csv(
        scores_csv,
        score_rows,
        [
            "subject_id", "Y_post", "Y_base", "SweetPeak5", "SourPeak5", "NetFiberScore",
            "n_sweet_selected_fibers", "n_sour_selected_fibers", "n_sweet_peak_fibers",
            "n_sour_peak_fibers", "score_map_source", "is_primary_score",
        ],
    )
    write_csv(
        predictions_csv,
        fold_rows,
        [
            "fold_id", "heldout_subject_id", "Y_post", "Y_base", "SweetPeak5_LOOCV",
            "SourPeak5_LOOCV", "NetFiberScore_LOOCV", "prediction_NetFiberScore_model",
            "prediction_baseline_only", "residual_NetFiberScore_model", "residual_baseline_only",
            "n_train", "n_candidate_fibers", "n_sweet_selected_fibers", "n_sour_selected_fibers",
            "delta", "beta_Y_base", "baseline_beta_Y_base",
        ],
    )
    qc.update(
        {
            "scale": config.scale,
            "endpoint_protocol": config.endpoint_protocol,
            "endpoint_phase": config.endpoint_phase,
            "scale_direction": config.scale_direction,
            "scale_direction_source": "configured_endpoint",
            "connectome": config.connectome_label,
            "connectome_id": config.connectome_id,
            "connectome_identity_source": config.connectome_identity_source,
            "max_fibers": config.max_fibers,
            "sampler_qc": sampler_qc,
            "sidecar_qc": sidecar_qc,
        }
    )
    manifest = {
        "generated_at": iso_now(),
        "model": "HF normative connectome fiber",
        "branch": hf_fiber_primary_branch_name(
            config.primary_tau,
            config.primary_coverage,
            legacy=not config.dynamic_names,
        ),
        "status": "PASS",
        "repo_root": str(config.repo_root),
        "clinical_table": str(config.clinical_table),
        "stimulation_table": str(config.stimulation_table),
        "derivatives_root": str(config.derivatives_root),
        "connectome": config.connectome_label,
        "connectome_id": config.connectome_id,
        "data_mat": str(config.connectome_path),
        "output_root": str(config.output_dir),
        "parameters": {
            "scale": config.scale,
            "endpoint_protocol": config.endpoint_protocol,
            "endpoint_phase": config.endpoint_phase,
            "scale_direction": config.scale_direction,
            "tau_v_per_m": config.primary_tau,
            "min_coverage": config.primary_coverage,
            "tau_grid_v_per_m": list(config.tau_grid),
            "coverage_grid": list(config.coverage_grid),
            "max_fibers": config.max_fibers,
            "fiber_chunk_size": config.fiber_chunk_size,
            "random_seed": 42,
        },
        "outputs": {
            "preprocess_dir": str(config.preprocess_dir),
            "weights_csv": str(weights_csv),
            "scores_csv": str(scores_csv),
            "loocv_predictions_csv": str(predictions_csv),
            "mapping_qc_json": str(mapping_qc_json),
            "generation_manifest_json": str(generation_manifest_json),
        },
        "runtime_profile": {
            "total_s": time.time() - started,
            "n_fibers": int(x.shape[1]),
            "n_candidate_fibers": int(qc["n_candidate_fibers"]),
        },
    }
    write_json(mapping_qc_json, qc)
    write_json(generation_manifest_json, manifest)
    return {
        "source_status": "not_applicable",
        "prediction_status": "not_applicable",
        "threshold_source": "pre_specified",
        "selected_tau": config.primary_tau,
        "selected_coverage": config.primary_coverage,
        "adjacent_support": None,
        "subject_order": subject_ids,
        "feature_axis": _feature_axis_payload(config, fiber_ids),
        "artifacts": {
            "observed_metrics": str(mapping_qc_json),
            "loocv_predictions": str(predictions_csv),
        },
    }


def run_hf_normative_fiber_plain_connected_control_configured(
    config: HFNormativeFiberAnalysisConfig,
) -> dict[str, Any]:
    """Run the Round 3 outcome-independent connected-streamline burden control."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    records = _load_configured_records(config)
    subject_ids = [record.subject_id for record in records]
    x, fiber_ids, sidecar_manifest = _load_completed_exposure_for_config(config, records)
    touched_csv = config.output_dir / "normative_HF_plain_touched_summary.csv"
    comparison_csv = config.output_dir / "normative_HF_plain_connected_model_comparison.csv"
    folds_csv = config.output_dir / "normative_HF_plain_connected_loocv_predictions.csv"
    control_metrics = config.output_dir / "control_metrics.json"
    try:
        result = compute_plain_connected_control(
            x=x,
            fiber_ids=fiber_ids,
            y_post=np.array([record.y_post for record in records], dtype=float),
            y_base=np.array([record.y_base for record in records], dtype=float),
            subject_ids=subject_ids,
            scale_direction=config.scale_direction,
            tau=config.primary_tau,
            min_coverage=config.primary_coverage,
            peak_fraction=config.weighted_peak_fraction,
        )
    except Exception as exc:
        _atomic_write_json(
            control_metrics,
            {
                "branch": "plain_connected_streamline_control",
                "branch_status": "failed_control_readiness",
                "failure_reason": str(exc),
                "failure_type": type(exc).__name__,
                "source_classification_feedback": "none",
                "selected_source": "pre_specified_observed_source",
                "tau_v_per_m": config.primary_tau,
                "min_coverage": config.primary_coverage,
                "subject_order": subject_ids,
                "feature_axis": _feature_axis_payload(config, fiber_ids),
            },
        )
        return {"artifacts": {"control_metrics": str(control_metrics)}}

    write_csv(
        touched_csv,
        result["subject_rows"],
        [
            "subject_id",
            "Y_post",
            "Y_base",
            "PlainTouchedCount",
            "PlainExposureSum",
            "PlainExposureTop5",
            "NetFiberScore",
        ],
    )
    write_csv(
        comparison_csv,
        result["model_rows"],
        [
            "model",
            "spearman_rho",
            "pearson_r",
            "mae",
            "rmse",
            "q2",
            "all_folds_full_rank",
            "all_predictions_finite",
            "median_intercept",
            "median_primary_beta",
        ],
    )
    write_csv(
        folds_csv,
        result["fold_rows"],
        [
            "fold_id",
            "heldout_subject_id",
            "prediction_baseline_only",
            "prediction_plain_plus_baseline",
            "prediction_net_plus_baseline",
            "prediction_joint_net_plain_baseline",
        ],
    )
    _atomic_write_json(
        control_metrics,
        {
            **{key: value for key, value in result.items() if key not in {"subject_rows", "model_rows", "fold_rows"}},
            "selected_source": "pre_specified_observed_source",
            "subject_order": subject_ids,
            "feature_axis": _feature_axis_payload(config, fiber_ids),
            "sidecar_completion_status": sidecar_manifest["status"],
            "outputs": {
                "touched_summary_csv": str(touched_csv),
                "model_comparison_csv": str(comparison_csv),
                "loocv_predictions_csv": str(folds_csv),
            },
        },
    )
    return {"artifacts": {"control_metrics": str(control_metrics)}}


def _write_sensitivity_branch_outputs(
    *,
    branch_dir: Path,
    branch_name: str,
    fiber_ids: np.ndarray,
    score_rows: list[dict[str, Any]],
    fold_rows: list[dict[str, Any]],
    qc: dict[str, Any],
    coverage: np.ndarray,
    rho: np.ndarray,
    weights: np.ndarray,
    min_coverage: int,
) -> dict[str, str]:
    branch_dir.mkdir(parents=True, exist_ok=True)
    candidate = candidate_mask_from_coverage(coverage, min_coverage)
    weights_csv = branch_dir / "normative_HF_fiber_weights.csv"
    scores_csv = branch_dir / "normative_HF_fiber_scores.csv"
    predictions_csv = branch_dir / "normative_HF_fiber_loocv_predictions.csv"
    mapping_qc_json = branch_dir / "normative_HF_fiber_mapping_qc.json"
    write_csv(
        weights_csv,
        [
            {
                "fiber_id": int(fiber_ids[index]),
                "coverage": int(coverage[index]),
                "rho_HF": float(rho[index]) if np.isfinite(rho[index]) else "",
                "M_HF": float(weights[index]) if np.isfinite(weights[index]) else "",
                "is_candidate": True,
            }
            for index in np.where(candidate)[0]
        ],
        ["fiber_id", "coverage", "rho_HF", "M_HF", "is_candidate"],
    )
    write_csv(
        scores_csv,
        score_rows,
        [
            "subject_id", "Y_post", "Y_base", "SweetPeak5", "SourPeak5", "NetFiberScore",
            "n_sweet_selected_fibers", "n_sour_selected_fibers", "n_sweet_peak_fibers",
            "n_sour_peak_fibers", "score_map_source", "is_primary_score",
        ],
    )
    write_csv(
        predictions_csv,
        fold_rows,
        [
            "fold_id", "heldout_subject_id", "Y_post", "Y_base", "SweetPeak5_LOOCV",
            "SourPeak5_LOOCV", "NetFiberScore_LOOCV", "prediction_NetFiberScore_model",
            "prediction_baseline_only", "residual_NetFiberScore_model", "residual_baseline_only",
            "n_train", "n_candidate_fibers", "n_sweet_selected_fibers", "n_sour_selected_fibers",
            "delta", "beta_Y_base", "baseline_beta_Y_base",
        ],
    )
    _atomic_write_json(
        mapping_qc_json,
        {
            **qc,
            "branch": branch_name,
            "source_classification_feedback": "none",
            "resampling_status": "not_run_observed_sensitivity",
        },
    )
    return {
        "weights_csv": str(weights_csv),
        "scores_csv": str(scores_csv),
        "loocv_predictions_csv": str(predictions_csv),
        "mapping_qc_json": str(mapping_qc_json),
    }


def run_hf_normative_fiber_cheap_observed_sensitivity_configured(
    config: HFNormativeFiberAnalysisConfig,
) -> dict[str, Any]:
    """Run the fixed authoritative Round 5 high-tau and fixed top-count sensitivities."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    records = _load_configured_records(config)
    subject_ids = [record.subject_id for record in records]
    x, fiber_ids, sidecar_manifest = _load_completed_exposure_for_config(config, records)
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    specifications = [
        {
            "branch": f"peak_efield_tau{_numeric_token(config.sensitivity_high_tau)}_cov{config.sensitivity_coverage}_sensitivity",
            "tau": config.sensitivity_high_tau,
            "coverage": config.sensitivity_coverage,
            "sweet_count": None,
            "sour_count": None,
            "authoritative_spec": "fixed_tau1500_coverage5",
        },
        {
            "branch": f"top{config.sensitivity_sweet_count}_top{config.sensitivity_sour_count}_sensitivity",
            "tau": config.primary_tau,
            "coverage": config.primary_coverage,
            "sweet_count": config.sensitivity_sweet_count,
            "sour_count": config.sensitivity_sour_count,
            "authoritative_spec": "fixed_top1500_positive_top500_negative",
        },
    ]
    branch_rows: list[dict[str, Any]] = []
    for specification in specifications:
        branch_name = str(specification["branch"])
        tau = float(specification["tau"])
        coverage_min = int(specification["coverage"])
        try:
            score_rows, fold_rows, qc, coverage, rho, weights = run_observed_loocv(
                x=x,
                fiber_ids=fiber_ids,
                y_post=y_post,
                y_base=y_base,
                subject_ids=subject_ids,
                scale_direction=config.scale_direction,
                tau=tau,
                min_coverage=coverage_min,
                sweet_count=specification["sweet_count"],
                sour_count=specification["sour_count"],
                sweet_fraction=config.sweet_fraction,
                sour_fraction=config.sour_fraction,
                peak_fraction=config.weighted_peak_fraction,
            )
            if not _strict_boolean(qc["selected_fiber_pools_computable"]):
                branch_status = "selected_fiber_pool_empty"
            elif not _strict_boolean(qc["all_predictions_finite"]):
                branch_status = "nonfinite_predictions"
            else:
                branch_status = "complete"
            outputs = _write_sensitivity_branch_outputs(
                branch_dir=config.output_dir / branch_name,
                branch_name=branch_name,
                fiber_ids=fiber_ids,
                score_rows=score_rows,
                fold_rows=fold_rows,
                qc=qc,
                coverage=coverage,
                rho=rho,
                weights=weights,
                min_coverage=coverage_min,
            )
            branch_rows.append(
                {
                    **specification,
                    "branch_status": branch_status,
                    "failure_reason": "",
                    "source_classification_feedback": "none",
                    "n_candidate_fibers": int(qc["n_candidate_fibers"]),
                    "n_sweet_selected_fibers": int(qc["n_sweet_selected_fibers"]),
                    "n_sour_selected_fibers": int(qc["n_sour_selected_fibers"]),
                    "loocv_metrics": qc["loocv_metrics"],
                    "outputs": outputs,
                }
            )
        except Exception as exc:
            message = str(exc)
            branch_status = (
                "candidate_empty_or_threshold_too_strict"
                if "empty" in message.lower()
                else "failed_observed_sensitivity"
            )
            branch_rows.append(
                {
                    **specification,
                    "branch_status": branch_status,
                    "failure_reason": message,
                    "failure_type": type(exc).__name__,
                    "source_classification_feedback": "none",
                    "outputs": {},
                }
            )

    summary_csv = config.output_dir / "normative_HF_fiber_top_percentile_sweep_summary.csv"
    write_csv(
        summary_csv,
        branch_rows,
        [
            "branch", "tau", "coverage", "sweet_count", "sour_count", "authoritative_spec",
            "branch_status", "failure_reason", "n_candidate_fibers", "n_sweet_selected_fibers",
            "n_sour_selected_fibers",
        ],
    )
    sensitivity_results = config.output_dir / "sensitivity_results.json"
    all_complete = all(row["branch_status"] == "complete" for row in branch_rows)
    _atomic_write_json(
        sensitivity_results,
        {
            "overall_status": "complete" if all_complete else "complete_with_branch_failures",
            "source_classification_feedback": "none",
            "public_configured_spec": {
                "high_threshold_tau_v_per_m": config.sensitivity_high_tau,
                "high_threshold_coverage": config.sensitivity_coverage,
                "top_positive_fibers": config.sensitivity_sweet_count,
                "top_negative_fibers": config.sensitivity_sour_count,
                "sweet_fraction": config.sweet_fraction,
                "sour_fraction": config.sour_fraction,
                "weighted_peak_fraction": config.weighted_peak_fraction,
                "scale_branching": False,
            },
            "subject_order": subject_ids,
            "feature_axis": _feature_axis_payload(config, fiber_ids),
            "sidecar_completion_status": sidecar_manifest["status"],
            "branches": branch_rows,
            "outputs": {"branch_summary_csv": str(summary_csv)},
        },
    )
    return {"artifacts": {"sensitivity_results": str(sensitivity_results)}}


def _materialize_selected_source_artifacts(
    *,
    config: HFNormativeFiberAnalysisConfig,
    x: np.ndarray,
    fiber_ids: np.ndarray,
    y_post: np.ndarray,
    y_base: np.ndarray,
    subject_ids: list[str],
    selected_tau: float,
    selected_coverage: int,
    source_status: str,
    prediction_status: str,
) -> dict[str, str]:
    token = f"tau{_numeric_token(selected_tau)}_cov{int(selected_coverage)}"
    full_weights_path = config.output_dir / f"selected_{token}_full_weights.npy"
    fold_weights_path = config.output_dir / f"selected_{token}_fold_weights.npy"
    scores_path = config.output_dir / f"selected_{token}_scores.csv"
    fold_scores_path = config.output_dir / f"selected_{token}_fold_scores.csv"
    selected_manifest_path = config.output_dir / f"selected_{token}_manifest.json"
    temporary_full_weights = full_weights_path.with_name(f".{full_weights_path.stem}.{uuid4().hex}.tmp.npy")
    temporary_fold_weights = fold_weights_path.with_name(f".{fold_weights_path.stem}.{uuid4().hex}.tmp.npy")
    try:
        score_rows, fold_rows, qc, _, _, weights = run_observed_loocv(
            x=x,
            fiber_ids=fiber_ids,
            y_post=y_post,
            y_base=y_base,
            subject_ids=subject_ids,
            scale_direction=config.scale_direction,
            tau=selected_tau,
            min_coverage=selected_coverage,
            sweet_fraction=config.sweet_fraction,
            sour_fraction=config.sour_fraction,
            peak_fraction=config.weighted_peak_fraction,
            fold_weights_output=temporary_fold_weights,
        )
        np.save(temporary_full_weights, weights.astype(np.float32))
        os.replace(temporary_full_weights, full_weights_path)
        os.replace(temporary_fold_weights, fold_weights_path)
    finally:
        for temporary in (temporary_full_weights, temporary_fold_weights):
            if temporary.exists():
                temporary.unlink()

    write_csv(
        scores_path,
        score_rows,
        [
            "subject_id", "Y_post", "Y_base", "SweetPeak5", "SourPeak5", "NetFiberScore",
            "n_sweet_selected_fibers", "n_sour_selected_fibers", "n_sweet_peak_fibers",
            "n_sour_peak_fibers", "score_map_source", "is_primary_score",
        ],
    )
    write_csv(
        fold_scores_path,
        fold_rows,
        [
            "fold_id", "heldout_subject_id", "Y_post", "Y_base", "SweetPeak5_LOOCV",
            "SourPeak5_LOOCV", "NetFiberScore_LOOCV", "prediction_NetFiberScore_model",
            "prediction_baseline_only", "residual_NetFiberScore_model", "residual_baseline_only",
            "n_train", "n_candidate_fibers", "n_sweet_selected_fibers", "n_sour_selected_fibers",
            "delta", "beta_Y_base", "baseline_beta_Y_base",
        ],
    )
    exposure_path = config.preprocess_dir / "X_HF_fiber_float32_subject_major.npy"
    artifact_paths = {
        "exposure_matrix": str(exposure_path),
        "selected_scores": str(scores_path),
        "selected_full_weights": str(full_weights_path),
        "selected_fold_weights": str(fold_weights_path),
        "selected_fold_scores": str(fold_scores_path),
    }
    _atomic_write_json(
        selected_manifest_path,
        {
            "status": "complete",
            "source_status": source_status,
            "prediction_status": prediction_status,
            "selected_tau_v_per_m": selected_tau,
            "selected_coverage": selected_coverage,
            "scale_direction": config.scale_direction,
            "subject_order": subject_ids,
            "feature_axis": _feature_axis_payload(config, fiber_ids),
            "matrix_shape": list(x.shape),
            "fold_weights_shape": [len(subject_ids), int(fiber_ids.size)],
            "qc": qc,
            "artifacts": {
                kind: file_identity(Path(path))
                for kind, path in artifact_paths.items()
            },
        },
    )
    return {"selected_manifest": str(selected_manifest_path), **artifact_paths}


def run_hf_normative_fiber_resolver_configured(config: HFNormativeFiberAnalysisConfig) -> dict[str, Any]:
    """Run the configured tau/coverage resolver against a validated primary sidecar."""
    started = time.time()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    records = _load_configured_records(config)
    subject_ids = [record.subject_id for record in records]
    x, fiber_ids, sidecar_manifest = _load_completed_exposure_for_config(config, records)
    y_post = np.array([record.y_post for record in records], dtype=float)
    y_base = np.array([record.y_base for record in records], dtype=float)
    rows: list[dict[str, Any]] = []
    for tau in config.tau_grid:
        for coverage in config.coverage_grid:
            rows.append(
                evaluate_normative_fiber_grid_cell(
                    x=x,
                    fiber_ids=fiber_ids,
                    y_post=y_post,
                    y_base=y_base,
                    subject_ids=subject_ids,
                    scale_direction=config.scale_direction,
                    connectome=config.connectome_id,
                    tau=tau,
                    coverage=coverage,
                    sweet_fraction=config.sweet_fraction,
                    sour_fraction=config.sour_fraction,
                    peak_fraction=config.weighted_peak_fraction,
                )
            )
    resolved = resolve_normative_fiber_source(
        rows,
        connectome=config.connectome_id,
        tau_grid=config.tau_grid,
        coverage_grid=config.coverage_grid,
        primary_tau=config.primary_tau,
        primary_coverage=config.primary_coverage,
        minimum_adjacent_passing_cells=config.resolver_minimum_adjacent_passing_cells,
    )
    names = hf_fiber_artifact_names(config.primary_tau, config.primary_coverage, dynamic=config.dynamic_names)
    outputs = write_normative_fiber_source_scan_outputs(
        config.output_dir,
        rows=rows,
        resolved=resolved,
        artifact_names=names,
        manifest={
            "generated_at": iso_now(),
            "analysis": "hf_normative_fiber_tau_coverage_source_resolver_scan",
            "model": "HF normative connectome fiber",
            "connectome": config.connectome_label,
            "connectome_id": config.connectome_id,
            "connectome_identity_source": config.connectome_identity_source,
            "scale": config.scale,
            "endpoint_protocol": config.endpoint_protocol,
            "endpoint_phase": config.endpoint_phase,
            "scale_direction": config.scale_direction,
            "scale_direction_source": "configured_endpoint",
            "pre_specified_tau_v_per_m": config.primary_tau,
            "pre_specified_coverage": config.primary_coverage,
            "tau_grid_v_per_m": list(config.tau_grid),
            "coverage_grid": list(config.coverage_grid),
            "resolver_minimum_adjacent_passing_cells": config.resolver_minimum_adjacent_passing_cells,
            "primary_preprocess_dir": str(config.preprocess_dir),
            "sidecar_completion": sidecar_manifest,
            "runtime_s": time.time() - started,
        },
    )
    selected_source_json = config.output_dir / names["selected_source_json"]
    feature_axis = _feature_axis_payload(config, fiber_ids)
    source_status = resolved["hf_norm_fiber_source_status"]
    selected_artifacts: dict[str, str] = {}
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"}:
        selected_tau = resolved["hf_norm_fiber_selected_tau_v_per_m"]
        selected_coverage = resolved["hf_norm_fiber_selected_coverage"]
        if selected_tau in (None, "") or selected_coverage in (None, ""):
            raise RuntimeError("accepted HF fiber resolver did not select tau and coverage")
        selected_artifacts = _materialize_selected_source_artifacts(
            config=config,
            x=x,
            fiber_ids=fiber_ids,
            y_post=y_post,
            y_base=y_base,
            subject_ids=subject_ids,
            selected_tau=float(selected_tau),
            selected_coverage=int(selected_coverage),
            source_status=source_status,
            prediction_status=resolved["hf_norm_fiber_prediction_status"],
        )
    _atomic_write_json(
        selected_source_json,
        {
            **resolved,
            "subject_order": subject_ids,
            "feature_axis": feature_axis,
            "scan_csv": outputs["scan_csv"],
            "selected_artifacts": selected_artifacts,
        },
    )
    return {
        "source_status": resolved["hf_norm_fiber_source_status"],
        "prediction_status": resolved["hf_norm_fiber_prediction_status"],
        "threshold_source": resolved["hf_norm_fiber_threshold_source"],
        "selected_tau": resolved["hf_norm_fiber_selected_tau_v_per_m"],
        "selected_coverage": resolved["hf_norm_fiber_selected_coverage"],
        "adjacent_support": resolved["hf_norm_fiber_selected_adjacent_passing_grid_cells"],
        "subject_order": subject_ids,
        "feature_axis": feature_axis,
        "artifacts": {
            "source_status": outputs["manifest_json"],
            "selected_source": str(selected_source_json),
            **selected_artifacts,
        },
    }


def _legacy_analysis_config(
    args: argparse.Namespace,
    *,
    resolver: bool,
) -> HFNormativeFiberAnalysisConfig:
    """Translate the historical CLI namespace without changing its default layout."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    clinical_table_value = getattr(args, "clinical_table", "")
    stimulation_table_value = getattr(args, "stimulation_table", "")
    clinical_table = (
        Path(clinical_table_value).expanduser().resolve()
        if clinical_table_value
        else clinical_root / RAW_CLINICAL_FILE
    )
    stimulation_table = (
        Path(stimulation_table_value).expanduser().resolve()
        if stimulation_table_value
        else clinical_root / STIM_FILE
    )
    base_scale, parsed_protocol, parsed_phase = parse_endpoint_scale(args.scale)
    protocol = str(getattr(args, "endpoint_protocol", "") or parsed_protocol)
    phase = str(getattr(args, "endpoint_phase", "") or parsed_phase)
    inferred_direction, _ = infer_scale_direction(base_scale)
    scale_direction = str(getattr(args, "scale_direction", "") or inferred_direction)

    connectome_info = CONNECTOMES[args.connectome]
    explicit_connectome_path = getattr(args, "connectome_path", "")
    if explicit_connectome_path:
        data_mat = Path(explicit_connectome_path).expanduser().resolve()
    else:
        asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
        data_mat = asset_root / connectome_info["path"]
    connectome_label = str(getattr(args, "connectome_label", "") or connectome_info["label"])
    connectome_identity_source = str(getattr(args, "connectome_identity_source", "") or "data.mat:idx")

    tau_grid = tuple(float(value) for value in (getattr(args, "tau_grid", None) or NORM_FIBER_TAU_GRID))
    coverage_grid = tuple(int(value) for value in (getattr(args, "coverage_grid", None) or NORM_FIBER_COVERAGE_GRID))
    primary_tau = float(args.tau)
    primary_coverage = int(args.min_coverage)
    if primary_tau not in tau_grid:
        tau_grid = (*tau_grid, primary_tau)
    if primary_coverage not in coverage_grid:
        coverage_grid = (*coverage_grid, primary_coverage)

    output_root = Path(args.output_root).expanduser().resolve()
    scale_slug = slugify(args.scale)
    connectome_slug = connectome_info["slug"]
    primary_dir = (
        output_root
        / connectome_slug
        / scale_slug
        / hf_fiber_primary_branch_name(primary_tau, primary_coverage, legacy=True)
    )
    output_dir = (
        output_root / connectome_slug / scale_slug / "tau_coverage_source_resolver_scan"
        if resolver
        else primary_dir
    )
    return HFNormativeFiberAnalysisConfig(
        scale=base_scale,
        endpoint_protocol=protocol,
        endpoint_phase=phase,
        scale_direction=scale_direction,
        subject_order=(),
        clinical_table=clinical_table,
        stimulation_table=stimulation_table,
        derivatives_root=Path(args.leaddbs_derivatives).expanduser().resolve(),
        repo_root=repo_root,
        matlab_bin=Path(args.matlab_bin).expanduser().resolve(),
        connectome_id=args.connectome,
        connectome_label=connectome_label,
        connectome_path=data_mat,
        connectome_identity_source=connectome_identity_source,
        output_dir=output_dir,
        preprocess_dir=primary_dir / "preprocess",
        tau_grid=tau_grid,
        coverage_grid=coverage_grid,
        primary_tau=primary_tau,
        primary_coverage=primary_coverage,
        resolver_minimum_adjacent_passing_cells=int(
            getattr(args, "resolver_minimum_adjacent_passing_cells", 2)
        ),
        max_fibers=int(args.max_fibers),
        fiber_chunk_size=int(args.fiber_chunk_size),
        force_flip=bool(args.force_flip),
        force_rebuild=bool(args.force_rebuild),
        dynamic_names=False,
    )


def run_normative_fiber_source_resolver_scan(args: argparse.Namespace) -> int:
    """Run the declared HF normative fiber tau/Coverage source resolver scan."""
    config = _legacy_analysis_config(args, resolver=True)
    result = run_hf_normative_fiber_resolver_configured(config)
    print(f"HF normative fiber source resolver output: {config.output_dir}")
    print(json.dumps({key: result[key] for key in (
        "source_status", "prediction_status", "threshold_source", "selected_tau",
        "selected_coverage", "adjacent_support",
    )}, indent=2, sort_keys=True))
    print(f"Scan CSV: {result['artifacts']['source_status']}")
    return 0


def run_hf_normative_fiber_smoke(args: argparse.Namespace) -> int:
    config = _legacy_analysis_config(args, resolver=False)
    result = run_hf_normative_fiber_primary_configured(config)
    mapping_qc = json.loads(Path(result["artifacts"]["observed_metrics"]).read_text(encoding="utf-8"))
    print(f"HF normative fiber smoke output: {config.output_dir}")
    print(f"LOOCV Spearman rho: {mapping_qc['loocv_metrics']['spearman_rho']:.6g}")
    print(f"LOOCV Q2: {mapping_qc['loocv_metrics']['q2']:.6g}")
    print(f"Fibers: {result['feature_axis']['count']}; candidate fibers: {mapping_qc['n_candidate_fibers']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root.")
    parser.add_argument("--asset-root", default=str(DEFAULT_CANONICAL_ASSET_ROOT), help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--clinical-table", default="", help="Explicit clinical CSV/XLSX path; overrides --clinical-root.")
    parser.add_argument("--stimulation-table", default="", help="Explicit stimulation CSV/XLSX path; overrides --clinical-root.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_VAL_ROOT / "summary/normative_connectome_fiber/hf"), help="HF normative fiber output root.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--scale", default=HF_DEFAULT_SCALES[0], help="Raw clinical scale to run.")
    parser.add_argument("--endpoint-protocol", default="", help="Explicit endpoint protocol; otherwise parse the legacy scale label.")
    parser.add_argument("--endpoint-phase", default="", help="Explicit endpoint phase; otherwise parse the legacy scale label.")
    parser.add_argument("--scale-direction", choices=("lower", "higher"), default="", help="Explicit clinical benefit direction.")
    parser.add_argument("--connectome", choices=sorted(CONNECTOMES), default="ppmi", help="Public connectome to process.")
    parser.add_argument("--connectome-path", default="", help="Explicit connectome data.mat path.")
    parser.add_argument("--connectome-label", default="", help="Explicit connectome display label.")
    parser.add_argument("--connectome-identity-source", default="", help="Feature-axis identity source recorded in provenance.")
    parser.add_argument("--tau", type=float, default=800.0, help="Primary fiber inclusion threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=5, help="Minimum subject coverage.")
    parser.add_argument("--tau-grid", nargs="+", type=float, default=None, help="Resolver tau grid in V/m.")
    parser.add_argument("--coverage-grid", nargs="+", type=int, default=None, help="Resolver coverage grid.")
    parser.add_argument("--resolver-minimum-adjacent-passing-cells", type=int, default=2, help="Minimum passing neighbors required by the source resolver.")
    parser.add_argument("--source-resolver-scan", action="store_true", help="Run the tau/Coverage source resolver scan using the existing primary sidecar.")
    parser.add_argument("--fiber-chunk-size", type=int, default=10000, help="Number of fibers per sampling chunk.")
    parser.add_argument("--max-fibers", type=int, default=0, help="Development-only cap; 0 means full connectome.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    parser.add_argument("--force-rebuild", action="store_true", help="Regenerate exposure sidecar even if present.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.source_resolver_scan:
        return run_normative_fiber_source_resolver_scan(args)
    return run_hf_normative_fiber_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
