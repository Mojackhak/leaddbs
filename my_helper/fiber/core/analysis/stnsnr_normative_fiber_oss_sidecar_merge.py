#!/usr/bin/env python3
"""Merge row-level OSS activation states into branch-level normative-fiber sidecars."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    discover_targets,
    iso_now,
    read_csv,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


DEFAULT_WORKLIST_CSV = (
    DEFAULT_VAL_ROOT
    / "summary/four_model_execution/normative_fiber_oss_sidecar_worklist/"
    / "normative_fiber_oss_sidecar_worklist.csv"
)
DEFAULT_ACTIVATION_SUMMARY_CSV = (
    DEFAULT_VAL_ROOT
    / "summary/four_model_execution/normative_fiber_oss_activation_rows/"
    / "normative_fiber_oss_activation_row_summary.csv"
)
DEFAULT_READINESS_CSV = DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_readiness/four_model_formal_readiness.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_oss_sidecar_merge"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _subject_order_from_scores(path: Path) -> list[str]:
    rows = _read_csv_rows(path)
    subjects: list[str] = []
    for row in rows:
        if str(row.get("is_primary_score", "")).strip().lower() not in {"true", "1", "yes"}:
            continue
        subject = str(row.get("subject_id", "")).strip()
        if subject and subject not in subjects:
            subjects.append(subject)
    if subjects:
        return subjects
    for row in rows:
        subject = str(row.get("subject_id", "")).strip()
        if subject and subject not in subjects:
            subjects.append(subject)
    return subjects


def _array_sha256(values: np.ndarray) -> str:
    arr = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(arr.dtype).encode("utf-8"))
    digest.update(str(arr.shape).encode("utf-8"))
    digest.update(arr.view(np.uint8))
    return digest.hexdigest()


def _file_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(block_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _index_by_key(rows: list[dict[str, str]], fields: tuple[str, ...]) -> dict[tuple[str, ...], dict[str, str]]:
    indexed: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(str(row.get(field, "")).strip() for field in fields)
        if key in indexed:
            raise RuntimeError(f"duplicate row for key {key}")
        indexed[key] = row
    return indexed


def _load_activation_status_by_local_fiber(result_dir: Path) -> tuple[dict[int, int], dict[str, int]]:
    mat_path = result_dir / "Axon_state_default_1.mat"
    csv_path = result_dir / "Axon_state_default_1.csv"
    if mat_path.is_file():
        mat = loadmat(mat_path)
        if "fibers" not in mat:
            raise RuntimeError(f"missing fibers variable in {mat_path}")
        fibers = np.asarray(mat["fibers"], dtype=float)
    elif csv_path.is_file():
        fibers = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    else:
        raise RuntimeError(f"missing Axon_state_default_1.mat/csv in {result_dir}")
    if fibers.ndim != 2 or fibers.shape[1] < 5:
        raise RuntimeError(f"invalid Axon_state shape in {result_dir}: {fibers.shape}")

    local_ids = np.asarray(np.rint(fibers[:, 3]), dtype=np.int64)
    statuses = np.asarray(np.rint(fibers[:, 4]), dtype=np.int64)
    status_by_local: dict[int, int] = {}
    inconsistent = 0
    for local_id in np.unique(local_ids):
        if local_id <= 0:
            continue
        local_statuses = np.unique(statuses[local_ids == local_id])
        if local_statuses.size != 1:
            inconsistent += 1
            status_by_local[int(local_id)] = int(np.max(local_statuses))
        else:
            status_by_local[int(local_id)] = int(local_statuses[0])
    qc = {
        "n_state_points": int(fibers.shape[0]),
        "n_state_local_fibers": int(len(status_by_local)),
        "n_state_inconsistent_local_fibers": int(inconsistent),
        "n_state_activated_local_fibers": int(sum(1 for status in status_by_local.values() if status == 1)),
        "n_state_unactivated_local_fibers": int(sum(1 for status in status_by_local.values() if status == 0)),
        "n_state_negative_status_local_fibers": int(sum(1 for status in status_by_local.values() if status < 0)),
    }
    return status_by_local, qc


def _load_mapping_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_csv_rows(path)
    required = {"filtered_local_fiber_id", "candidate_column_index", "selected_candidate_fiber_id"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise RuntimeError(f"mapping file {path} missing columns: {sorted(missing)}")
    return rows


def _target_paths_from_worklist(rows: list[dict[str, str]], model_id: str) -> dict[str, Path]:
    model_rows = [row for row in rows if row.get("model_id") == model_id]
    if not model_rows:
        raise RuntimeError(f"no worklist rows for {model_id}")
    keys = [
        "required_output_preprocess_dir",
        "required_x_oss_path",
        "required_oss_parameter_manifest",
        "required_oss_activation_metadata",
        "oss_fiber_ids_path",
    ]
    out: dict[str, Path] = {}
    for key in keys:
        values = {str(row.get(key, "")).strip() for row in model_rows}
        if len(values) != 1:
            raise RuntimeError(f"worklist field {key} is not unique for {model_id}: {sorted(values)}")
        out[key] = Path(next(iter(values))).expanduser().resolve()
    return out


def _merge_model(
    *,
    model_id: str,
    subject_order: list[str],
    worklist_rows: list[dict[str, str]],
    activation_by_key: dict[tuple[str, str, str], dict[str, str]],
    output_dir: Path,
) -> dict[str, Any]:
    provenance = git_provenance()
    target_paths = _target_paths_from_worklist(worklist_rows, model_id)
    fiber_ids = np.asarray(np.load(target_paths["oss_fiber_ids_path"]), dtype=np.int64)
    if fiber_ids.ndim != 1:
        raise RuntimeError(f"oss_fiber_ids must be 1D for {model_id}: {target_paths['oss_fiber_ids_path']}")
    n_subjects = len(subject_order)
    n_fibers = int(fiber_ids.size)
    if n_subjects == 0 or n_fibers == 0:
        raise RuntimeError(f"empty merge dimensions for {model_id}: subjects={n_subjects}, fibers={n_fibers}")

    subject_to_row = {subject: idx for idx, subject in enumerate(subject_order)}
    x = np.zeros((n_subjects, n_fibers), dtype=np.float32)
    qc_rows: list[dict[str, Any]] = []
    source_rows = [row for row in worklist_rows if row.get("model_id") == model_id]
    missing_subjects = sorted({row.get("subject_id", "") for row in source_rows} - set(subject_order))
    if missing_subjects:
        raise RuntimeError(f"{model_id} worklist has subjects absent from score order: {missing_subjects}")

    total_mapping_rows = 0
    total_missing_state_ids = 0
    total_negative_status = 0
    total_inconsistent_state_ids = 0
    for work_row in source_rows:
        subject_id = str(work_row.get("subject_id", "")).strip()
        side = str(work_row.get("side", "")).strip()
        subject_idx = subject_to_row[subject_id]
        activation_row = activation_by_key.get((model_id, subject_id, side))
        if activation_row is None:
            raise RuntimeError(f"missing activation row for {(model_id, subject_id, side)}")
        if activation_row.get("row_status") != "pathway_activation_complete":
            raise RuntimeError(f"activation row is not complete for {(model_id, subject_id, side)}: {activation_row.get('row_status')}")
        mapping_path = Path(activation_row.get("local_to_candidate_mapping_path", "")).expanduser().resolve()
        if not mapping_path.is_file():
            raise RuntimeError(f"missing local-to-candidate mapping for {(model_id, subject_id, side)}: {mapping_path}")
        if int(float(activation_row.get("local_to_candidate_mapping_invalid_candidate_column_count", "0") or 0)) != 0:
            raise RuntimeError(f"invalid candidate-column mapping count for {(model_id, subject_id, side)}")

        result_dir = Path(activation_row.get("output_path", "")).expanduser().resolve()
        status_by_local, state_qc = _load_activation_status_by_local_fiber(result_dir)
        mapping_rows = _load_mapping_rows(mapping_path)
        row_missing_state_ids = 0
        row_negative_status = 0
        row_activated_assignments = 0
        row_touched_columns: set[int] = set()
        for mapping in mapping_rows:
            local_id = int(float(mapping["filtered_local_fiber_id"]))
            col = int(float(mapping["candidate_column_index"]))
            if col < 0 or col >= n_fibers:
                raise RuntimeError(f"candidate column out of range in {mapping_path}: {col}")
            status = status_by_local.get(local_id)
            if status is None:
                row_missing_state_ids += 1
                continue
            p_activation = 1.0 if status == 1 else 0.0
            if status < 0:
                row_negative_status += 1
            if p_activation > 0:
                row_activated_assignments += 1
            x[subject_idx, col] = max(float(x[subject_idx, col]), p_activation)
            row_touched_columns.add(col)

        total_mapping_rows += len(mapping_rows)
        total_missing_state_ids += row_missing_state_ids
        total_negative_status += row_negative_status
        total_inconsistent_state_ids += state_qc["n_state_inconsistent_local_fibers"]
        qc_rows.append(
            {
                "model_id": model_id,
                "subject_id": subject_id,
                "side": side,
                "row_index": activation_row.get("row_index", ""),
                "n_mapping_rows": len(mapping_rows),
                "n_touched_candidate_columns": len(row_touched_columns),
                "n_activated_assignments": row_activated_assignments,
                "n_missing_state_ids": row_missing_state_ids,
                "n_negative_status_assignments": row_negative_status,
                **state_qc,
                "mapping_path": str(mapping_path),
                "result_dir": str(result_dir),
            }
        )

    if not np.all(np.isfinite(x)):
        raise RuntimeError(f"{model_id} OSS sidecar contains non-finite values")
    if float(np.min(x)) < 0.0 or float(np.max(x)) > 1.0:
        raise RuntimeError(f"{model_id} OSS sidecar outside [0, 1]")
    if np.count_nonzero(x) == 0:
        raise RuntimeError(f"{model_id} OSS sidecar is all zero")

    preprocess_dir = target_paths["required_output_preprocess_dir"]
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    x_path = target_paths["required_x_oss_path"]
    fiber_ids_out = preprocess_dir / "oss_fiber_ids.npy"
    np.save(x_path, x)
    np.save(fiber_ids_out, fiber_ids)

    subject_order_hash = hashlib.sha256(";".join(subject_order).encode("utf-8")).hexdigest()
    fiber_ids_hash = _array_sha256(fiber_ids)
    x_hash = _array_sha256(x)
    summary = {
        "model_id": model_id,
        "merge_status": "complete",
        "n_subjects": n_subjects,
        "n_fibers": n_fibers,
        "x_oss_path": str(x_path),
        "oss_fiber_ids_path": str(fiber_ids_out),
        "x_oss_shape": f"{x.shape[0]}x{x.shape[1]}",
        "x_oss_dtype": str(x.dtype),
        "x_oss_min": float(np.min(x)),
        "x_oss_max": float(np.max(x)),
        "x_oss_nonzero_count": int(np.count_nonzero(x)),
        "x_oss_nonzero_fraction": float(np.count_nonzero(x) / x.size),
        "activation_value_type": "pPAM_activation_probability",
        "current_activation_value_subtype": "deterministic_binary_0_1",
        "status_source": "Axon_state_default_1.mat",
        "hemisphere_source_merge_rule": "max_probability_union",
        "n_source_rows": len(source_rows),
        "n_qc_rows": len(qc_rows),
        "total_mapping_rows": total_mapping_rows,
        "total_missing_state_ids": total_missing_state_ids,
        "total_negative_status_assignments": total_negative_status,
        "total_inconsistent_state_local_fibers": total_inconsistent_state_ids,
        "subject_order": ";".join(subject_order),
        "subject_order_hash": subject_order_hash,
        "fiber_ids_hash": fiber_ids_hash,
        "x_oss_hash": x_hash,
        "generated_at": iso_now(),
        "code_provenance": provenance,
    }

    parameter_manifest = {
        **summary,
        "worklist_oss_fiber_ids_path": str(target_paths["oss_fiber_ids_path"]),
        "worklist_oss_fiber_ids_hash": _file_sha256(target_paths["oss_fiber_ids_path"]),
        "status_mapping": {
            "Axon_state status == 1": "p(A)=1.0",
            "Axon_state status == 0": "p(A)=0.0",
            "Axon_state status < 0": "p(A)=0.0 and counted as damaged/CSF/out-of-domain QC",
        },
        "required_inputs": {
            "worklist_rows": len(source_rows),
            "activation_summary": "normative_fiber_oss_activation_row_summary.csv",
        },
    }
    activation_metadata = {
        **summary,
        "matrix_path": str(x_path),
        "matrix_shape": list(x.shape),
        "matrix_dtype": str(x.dtype),
        "matrix_range": [float(np.min(x)), float(np.max(x))],
        "subject_axis": "rows",
        "fiber_axis": "columns",
        "column_order": "selected-source candidate fiber id order",
        "row_order": "primary score table subject order",
        "oss_fiber_ids_path": str(fiber_ids_out),
        "qc_csv": str(preprocess_dir / "oss_activation_sidecar_qc.csv"),
        "row_qc": qc_rows,
    }
    write_json(target_paths["required_oss_parameter_manifest"], parameter_manifest)
    write_json(target_paths["required_oss_activation_metadata"], activation_metadata)
    write_csv(preprocess_dir / "oss_activation_sidecar_qc.csv", qc_rows, list(qc_rows[0].keys()))
    write_json(output_dir / f"{model_id}_oss_sidecar_merge_status.json", activation_metadata)
    return summary


def run_oss_sidecar_merge(args: argparse.Namespace) -> int:
    worklist_csv = Path(args.worklist_csv).expanduser().resolve()
    activation_summary_csv = Path(args.activation_summary_csv).expanduser().resolve()
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    requested = set(args.model_id) if args.model_id else None

    targets = discover_targets(readiness_csv, requested)
    targets = [target for target in targets if target.model_id in DTOR_NORMATIVE_TARGET_IDS]
    if not targets:
        raise RuntimeError("no dTOR normative-fiber targets found for OSS sidecar merge")
    worklist_rows = read_csv(worklist_csv)
    activation_rows = read_csv(activation_summary_csv)
    activation_by_key = _index_by_key(activation_rows, ("model_id", "subject_id", "side"))

    summaries: list[dict[str, Any]] = []
    for target in targets:
        print(f"Merging normative-fiber OSS sidecar for {target.model_id}")
        summaries.append(
            _merge_model(
                model_id=target.model_id,
                subject_order=_subject_order_from_scores(target.scores_csv),
                worklist_rows=worklist_rows,
                activation_by_key=activation_by_key,
                output_dir=output_dir,
            )
        )

    summary_path = output_dir / "normative_fiber_oss_sidecar_merge_summary.csv"
    write_csv(summary_path, summaries, list(summaries[0].keys()))
    write_json(
        output_dir / "normative_fiber_oss_sidecar_merge_manifest.json",
        {
            "generated_at": iso_now(),
            "worklist_csv": str(worklist_csv),
            "activation_summary_csv": str(activation_summary_csv),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(summaries),
            "code_provenance": git_provenance(),
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"OSS sidecar merge summary: {summary_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worklist-csv", default=str(DEFAULT_WORKLIST_CSV), help="OSS sidecar worklist CSV.")
    parser.add_argument("--activation-summary-csv", default=str(DEFAULT_ACTIVATION_SUMMARY_CSV), help="Row-level activation summary CSV.")
    parser.add_argument("--readiness-csv", default=str(DEFAULT_READINESS_CSV), help="Formal readiness CSV.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Cross-target sidecar merge summary directory.")
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_oss_sidecar_merge(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
