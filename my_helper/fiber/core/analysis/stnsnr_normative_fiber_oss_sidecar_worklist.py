#!/usr/bin/env python3
"""Build a read-only OSS/pPAM sidecar input audit and worklist."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    NormativeFiberTarget,
    _load_json,
    discover_targets,
    iso_now,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


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
    if not subjects:
        for row in rows:
            subject = str(row.get("subject_id", "")).strip()
            if subject and subject not in subjects:
                subjects.append(subject)
    return subjects


def _read_fiber_id_count(path: Path) -> tuple[int, str]:
    if not path.is_file():
        return 0, "missing"
    arr = np.load(path, mmap_mode="r")
    if arr.ndim != 1:
        return int(arr.shape[0]), "invalid_ndim"
    return int(arr.shape[0]), "ok"


def _sidecar_preprocess_dir(target: NormativeFiberTarget, manifest: dict[str, Any]) -> Path:
    outputs = manifest.get("outputs", {})
    if outputs.get("preprocess_dir"):
        return Path(outputs["preprocess_dir"]).expanduser().resolve()
    if target.model_id == "D_DTOR":
        return target.x_path.parent
    return target.branch_dir / "preprocess"


def _sidecar_required_paths(preprocess_dir: Path) -> list[Path]:
    return [
        preprocess_dir / "X_oss_float32_fiber_major.npy",
        preprocess_dir / "oss_parameter_manifest.json",
        preprocess_dir / "oss_activation_sidecar_metadata.json",
    ]


def _hf_source_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    qc_path = Path(manifest["outputs"]["mapping_qc_json"]).expanduser().resolve()
    qc = _load_json(qc_path)
    return list(qc.get("sampler_qc", {}).get("side_fields", []))


def _ulf_source_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    component_qc = manifest.get("component_sampler_qc", {})
    ulf_qc = component_qc.get("ULF", {}) if isinstance(component_qc, dict) else {}
    return list(ulf_qc.get("side_paths", []))


def _source_rows_for_target(target: NormativeFiberTarget, manifest: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if target.model_id == "B_DTOR":
        return "HF_only_reference", "HF", _hf_source_rows(manifest)
    if target.model_id == "D_DTOR":
        return "ULF_addon_component", "ULF", _ulf_source_rows(manifest)
    raise ValueError(f"unsupported model_id: {target.model_id}")


def _source_status(source_paths: list[str]) -> str:
    if not source_paths:
        return "missing_source_paths"
    missing = [path for path in source_paths if not Path(path).is_file()]
    if missing:
        return "missing_source_files"
    return "ready_source_files"


def _derivatives_root(manifest: dict[str, Any]) -> Path:
    value = manifest.get("derivatives_root")
    if value:
        return Path(str(value)).expanduser().resolve()
    return DEFAULT_VAL_ROOT / "derivatives/leaddbs"


def _recover_ulf_source_paths(row: dict[str, Any], derivatives_root: Path) -> tuple[list[str], str]:
    subject = str(row.get("subject_id", "")).strip()
    side = str(row.get("side", "")).strip()
    if not subject or side not in {"L", "R"}:
        return [], ""
    patterns = [
        f"sub-*/stimulations/MNI152NLin2009bAsym/stnsnr_vta_{subject}_3m_STNplusSNr_alt_{side}_SNr_*/*_sim-efield_model-simbio_hemi-{side}.nii",
        f"sub-*/stimulations/MNI152NLin2009bAsym/stnsnr_target_component_{subject}_3m_STNplusSNr_{side}_SNr/*_sim-efield_model-simbio_hemi-{side}.nii",
    ]
    for mode, pattern in zip(
        ["recovered_derivatives_ulf_alt_snr", "recovered_derivatives_ulf_target_component_snr"],
        patterns,
        strict=True,
    ):
        matches = sorted(str(path) for path in derivatives_root.glob(pattern) if path.is_file() and not path.name.startswith("._"))
        if matches:
            return matches, mode
    return [], ""


def _row_subjects(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("subject_id", "")).strip() for row in rows if str(row.get("subject_id", "")).strip()}


def _target_audit_status(
    *,
    candidate_input_missing: list[str],
    missing_subjects: list[str],
    worklist_rows: list[dict[str, Any]],
    required_sidecars: list[Path],
) -> str:
    if candidate_input_missing:
        return "blocked_missing_candidate_inputs"
    if missing_subjects:
        return "blocked_missing_subject_source_rows"
    if any(row["side_input_status"] != "ready_source_files" for row in worklist_rows):
        return "blocked_missing_source_paths_or_files"
    if all(path.is_file() for path in required_sidecars):
        return "sidecar_files_already_present"
    return "ready_for_true_oss_sidecar_generation"


def audit_target(target: NormativeFiberTarget) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _load_json(target.manifest_path)
    subject_order = _subject_order_from_scores(target.scores_csv)
    source_component, frequency_class, source_rows = _source_rows_for_target(target, manifest)
    source_subjects = _row_subjects(source_rows)
    missing_subjects = [subject for subject in subject_order if subject not in source_subjects]
    sidecar_preprocess_dir = _sidecar_preprocess_dir(target, manifest)
    required_sidecars = _sidecar_required_paths(sidecar_preprocess_dir)
    sidecar_existing = [str(path) for path in required_sidecars if path.is_file()]
    sidecar_missing = [str(path) for path in required_sidecars if not path.is_file()]

    candidate_input_paths = [target.x_path, target.fiber_ids_path, target.scores_csv]
    candidate_input_missing = [str(path) for path in candidate_input_paths if not path.is_file()]
    n_fibers, fiber_id_status = _read_fiber_id_count(target.fiber_ids_path)

    worklist_rows: list[dict[str, Any]] = []
    derivatives_root = _derivatives_root(manifest)
    for row in source_rows:
        subject = str(row.get("subject_id", "")).strip()
        side = str(row.get("side", "")).strip()
        source_paths = [str(path) for path in row.get("source_paths", [])]
        recovered_mode = ""
        if target.model_id == "D_DTOR" and not source_paths:
            source_paths, recovered_mode = _recover_ulf_source_paths(row, derivatives_root)
        missing_source_files = [path for path in source_paths if not Path(path).is_file()]
        path_mode = row.get("path_mode", [])
        if isinstance(path_mode, str):
            path_mode_text = path_mode
        else:
            path_mode_text = ";".join(str(item) for item in path_mode)
        if recovered_mode:
            path_mode_text = recovered_mode if not path_mode_text else f"{path_mode_text};{recovered_mode}"
        worklist_rows.append(
            {
                "model_id": target.model_id,
                "source_component": source_component,
                "frequency_class": frequency_class,
                "subject_id": subject,
                "side": side,
                "path_mode": path_mode_text,
                "n_source_paths": len(source_paths),
                "source_paths": ";".join(source_paths),
                "missing_source_files": ";".join(missing_source_files),
                "side_input_status": _source_status(source_paths),
                "required_output_preprocess_dir": str(sidecar_preprocess_dir),
                "required_x_oss_path": str(required_sidecars[0]),
                "required_oss_parameter_manifest": str(required_sidecars[1]),
                "required_oss_activation_metadata": str(required_sidecars[2]),
            }
        )

    audit_status = _target_audit_status(
        candidate_input_missing=candidate_input_missing,
        missing_subjects=missing_subjects,
        worklist_rows=worklist_rows,
        required_sidecars=required_sidecars,
    )
    n_ready_sides = sum(1 for row in worklist_rows if row["side_input_status"] == "ready_source_files")
    audit_row = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "branch_dir": str(target.branch_dir),
        "source_component": source_component,
        "frequency_class": frequency_class,
        "scores_csv": str(target.scores_csv),
        "n_subjects": len(subject_order),
        "subject_order": ";".join(subject_order),
        "n_subjects_with_source_rows": len(source_subjects),
        "missing_subject_source_rows": ";".join(missing_subjects),
        "n_side_rows": len(worklist_rows),
        "n_ready_side_rows": n_ready_sides,
        "n_missing_source_path_side_rows": sum(1 for row in worklist_rows if row["side_input_status"] == "missing_source_paths"),
        "n_missing_source_file_side_rows": sum(1 for row in worklist_rows if row["side_input_status"] == "missing_source_files"),
        "n_recovered_source_path_side_rows": sum(1 for row in worklist_rows if "recovered_derivatives_" in row["path_mode"]),
        "candidate_x_path": str(target.x_path),
        "candidate_fiber_ids_path": str(target.fiber_ids_path),
        "candidate_n_fibers": n_fibers,
        "candidate_fiber_id_status": fiber_id_status,
        "candidate_input_missing": ";".join(candidate_input_missing),
        "required_output_preprocess_dir": str(sidecar_preprocess_dir),
        "required_sidecar_files": ";".join(str(path) for path in required_sidecars),
        "existing_sidecar_files": ";".join(sidecar_existing),
        "missing_sidecar_files": ";".join(sidecar_missing),
        "oss_sidecar_input_audit_status": audit_status,
        "generated_at": iso_now(),
    }
    return audit_row, worklist_rows


def run_oss_sidecar_worklist(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no dTOR normative-fiber OSS sidecar worklist targets found")

    audit_rows: list[dict[str, Any]] = []
    worklist_rows: list[dict[str, Any]] = []
    for target in targets:
        print(f"Auditing OSS sidecar inputs for {target.model_id}")
        audit_row, target_worklist = audit_target(target)
        audit_rows.append(audit_row)
        worklist_rows.extend(target_worklist)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "normative_fiber_oss_sidecar_input_audit.csv"
    worklist_path = output_dir / "normative_fiber_oss_sidecar_worklist.csv"
    manifest_path = output_dir / "normative_fiber_oss_sidecar_worklist_manifest.json"

    write_csv(audit_path, audit_rows, list(audit_rows[0].keys()))
    write_csv(worklist_path, worklist_rows, list(worklist_rows[0].keys()) if worklist_rows else [])
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(audit_rows),
            "n_worklist_rows": len(worklist_rows),
            "code_provenance": git_provenance(),
            "side_effects": "read_only_audit_no_oss_sidecars_created",
            "outputs": {
                "audit_csv": str(audit_path),
                "worklist_csv": str(worklist_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    print(f"OSS sidecar input audit: {audit_path}")
    print(f"OSS sidecar worklist: {worklist_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_oss_sidecar_worklist"),
        help="Cross-target OSS sidecar input audit/worklist directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_oss_sidecar_worklist(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
