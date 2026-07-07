#!/usr/bin/env python3
"""Audit final-model formal targets before expensive STN/SNr formal drivers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_io import iso_now, read_csv, write_csv, write_json

READY_FORMAL_TARGET = "READY_FOR_FORMAL_RESAMPLING"

REQUIRED_FILES_BY_MANIFEST: dict[str, list[str]] = {
    "direct_voxel_HF_generation_manifest.json": [
        "direct_voxel_HF_mapping_qc.json",
        "direct_voxel_HF_scores.csv",
        "direct_voxel_HF_loocv_predictions.csv",
    ],
    "normative_HF_fiber_generation_manifest.json": [
        "normative_HF_fiber_mapping_qc.json",
        "normative_HF_fiber_scores.csv",
        "normative_HF_fiber_loocv_predictions.csv",
    ],
    "direct_voxel_ULF_only_generation_manifest.json": [
        "direct_voxel_ULF_only_mapping_qc.json",
        "direct_voxel_ULF_only_scores.csv",
        "direct_voxel_ULF_only_loocv_predictions.csv",
    ],
    "normative_ULF_fiber_generation_manifest.json": [
        "normative_ULF_fiber_mapping_qc.json",
        "normative_ULF_fiber_scores.csv",
        "normative_ULF_fiber_loocv_predictions.csv",
    ],
}


def manifest_required_files(manifest_path: Path) -> list[str]:
    return list(REQUIRED_FILES_BY_MANIFEST.get(manifest_path.name, []))


def formal_readiness_row(worklist_row: dict[str, str]) -> dict[str, Any]:
    formal_target_status = worklist_row.get("formal_target_status", "")
    base = {
        "model_id": worklist_row.get("model_id", ""),
        "model": worklist_row.get("model", ""),
        "model_family": worklist_row.get("model_family", ""),
        "observed_branch": worklist_row.get("observed_branch", ""),
        "final_branch_or_source": worklist_row.get("final_branch_or_source", ""),
        "final_model_role": worklist_row.get("final_model_role", ""),
        "final_model_status": worklist_row.get("final_model_status", ""),
        "formal_target_status": formal_target_status,
        "latest_manifest": worklist_row.get("latest_manifest", ""),
    }

    if formal_target_status != READY_FORMAL_TARGET:
        return {
            **base,
            "formal_readiness_status": "NOT_READY_NO_FORMAL_TARGET",
            "formal_readiness_reason": formal_target_status or "missing_formal_target_status",
            "required_file_count": 0,
            "existing_required_file_count": 0,
            "missing_required_files": "",
        }

    manifest = Path(str(worklist_row.get("latest_manifest", "")))
    if not str(manifest):
        return {
            **base,
            "formal_readiness_status": "NOT_READY_MISSING_MANIFEST",
            "formal_readiness_reason": "latest_manifest_field_empty",
            "required_file_count": 1,
            "existing_required_file_count": 0,
            "missing_required_files": "",
        }
    if not manifest.is_file():
        return {
            **base,
            "formal_readiness_status": "NOT_READY_MISSING_MANIFEST",
            "formal_readiness_reason": "latest_manifest_missing",
            "required_file_count": 1,
            "existing_required_file_count": 0,
            "missing_required_files": str(manifest),
        }

    companion_files = manifest_required_files(manifest)
    if not companion_files:
        return {
            **base,
            "formal_readiness_status": "NOT_READY_UNKNOWN_MANIFEST_TYPE",
            "formal_readiness_reason": manifest.name,
            "required_file_count": 1,
            "existing_required_file_count": 1,
            "missing_required_files": "",
        }

    required_paths = [manifest] + [manifest.parent / name for name in companion_files]
    missing = [path for path in required_paths if not path.is_file()]
    if missing:
        status = "NOT_READY_MISSING_REQUIRED_FILES"
        reason = "missing_required_branch_files"
    else:
        status = "READY_FOR_FORMAL_DRIVER"
        reason = "all_required_branch_files_present"
    return {
        **base,
        "formal_readiness_status": status,
        "formal_readiness_reason": reason,
        "required_file_count": len(required_paths),
        "existing_required_file_count": len(required_paths) - len(missing),
        "missing_required_files": ";".join(str(path) for path in missing),
    }


def build_readiness(worklist_csv: Path) -> list[dict[str, Any]]:
    return [formal_readiness_row(row) for row in read_csv(worklist_csv)]


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# STN/SNr Final-Model Formal Readiness",
        "",
        "| Model | Final branch/source | Target status | Readiness | Existing/required files |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {final_branch_or_source} | {formal_target_status} | "
            "{formal_readiness_status} | {existing_required_file_count}/{required_file_count} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_readiness(args: argparse.Namespace) -> int:
    worklist_csv = Path(args.worklist_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    rows = build_readiness(worklist_csv)
    csv_path = output_dir / "four_model_formal_readiness.csv"
    md_path = output_dir / "four_model_formal_readiness.md"
    manifest_path = output_dir / "four_model_formal_readiness_manifest.json"
    fieldnames = [
        "model_id",
        "model",
        "model_family",
        "observed_branch",
        "final_branch_or_source",
        "final_model_role",
        "final_model_status",
        "formal_target_status",
        "formal_readiness_status",
        "formal_readiness_reason",
        "required_file_count",
        "existing_required_file_count",
        "missing_required_files",
        "latest_manifest",
    ]
    write_csv(csv_path, rows, fieldnames)
    write_markdown(md_path, rows)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "worklist_csv": str(worklist_csv),
            "n_rows": len(rows),
            "readiness_counts": count_by(rows, "formal_readiness_status"),
            "outputs": {"csv": str(csv_path), "markdown": str(md_path), "manifest": str(manifest_path)},
        },
        add_code_provenance=True,
    )
    print(f"Formal readiness output: {csv_path}")
    for row in rows:
        print(f"{row['model_id']} {row['formal_readiness_status']}: {row['final_branch_or_source']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--worklist-csv",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_worklist/four_model_formal_target_worklist.csv"),
        help="Final-model formal target worklist CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_readiness"),
        help="Formal readiness output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_readiness(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
