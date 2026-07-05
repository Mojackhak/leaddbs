#!/usr/bin/env python3
"""Create a worklist for missing ULF component-specific e-field inputs."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_four_model_execution_status import latest_run_dir


DEFAULT_READINESS_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution/ulf_component_readiness"
DEFAULT_OUTPUT_DIR = DEFAULT_VAL_ROOT / "summary/four_model_execution/ulf_component_efield_worklist"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def build_missing_worklist_rows(readiness_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows requiring component-specific e-field generation."""
    worklist: list[dict[str, Any]] = []
    for row in readiness_rows:
        if as_bool(row.get("efield_exists")):
            continue
        path_mode = str(row.get("path_mode", "")).strip()
        generation_status = generation_status_for_path_mode(path_mode)
        if generation_status == "not_actionable_unknown_path_mode":
            continue
        out = {
            "worklist_index": len(worklist) + 1,
            "subject_id": row.get("subject_id", ""),
            "name_en": row.get("name_en", ""),
            "phase": row.get("phase", ""),
            "protocol": row.get("protocol", ""),
            "side": row.get("side", ""),
            "target": row.get("target", ""),
            "contact": row.get("contact", ""),
            "frequency_hz": row.get("frequency_hz", ""),
            "frequency_class": row.get("frequency_class", ""),
            "stimulation_pattern": row.get("stimulation_pattern", ""),
            "path_mode": path_mode,
            "folder_path": row.get("folder_path", ""),
            "efield_path": row.get("efield_path", ""),
            "generation_status": generation_status,
            "recommended_generator": recommended_generator_for_path_mode(path_mode),
        }
        worklist.append(out)
    return worklist


def generation_status_for_path_mode(path_mode: str) -> str:
    if path_mode == "counterfactual_target_component_continuous_mixed":
        return "needs_counterfactual_target_component_efield"
    if path_mode == "observed_alternating_subprogram":
        return "needs_observed_alternating_subprogram_efield"
    if path_mode == "observed_single_target_continuous_condition":
        return "needs_observed_continuous_condition_efield"
    return "not_actionable_unknown_path_mode"


def recommended_generator_for_path_mode(path_mode: str) -> str:
    if path_mode == "counterfactual_target_component_continuous_mixed":
        return "run_stnsnr_target_component_vta_distribution"
    if path_mode in {"observed_alternating_subprogram", "observed_single_target_continuous_condition"}:
        return "run_stnsnr_vta_coverage"
    return ""


def summarize_worklist(worklist: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_frequency_class: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    for row in worklist:
        status = str(row.get("generation_status", ""))
        frequency_class = str(row.get("frequency_class", ""))
        subject_id = str(row.get("subject_id", ""))
        by_status[status] = by_status.get(status, 0) + 1
        by_frequency_class[frequency_class] = by_frequency_class.get(frequency_class, 0) + 1
        by_subject[subject_id] = by_subject.get(subject_id, 0) + 1
    return {
        "n_missing": len(worklist),
        "by_status": by_status,
        "by_frequency_class": by_frequency_class,
        "by_subject": by_subject,
    }


def resolve_readiness_csv(readiness_root: Path, explicit_csv: str | None) -> Path:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    run_dir = latest_run_dir(readiness_root)
    if run_dir is None:
        return Path("")
    return run_dir / "ulf_component_efield_availability.csv"


def run_worklist(args: argparse.Namespace) -> int:
    readiness_root = Path(args.readiness_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    readiness_csv = resolve_readiness_csv(readiness_root, args.readiness_csv)
    if not readiness_csv.is_file():
        raise FileNotFoundError(f"Missing ULF readiness e-field CSV: {readiness_csv}")
    readiness_rows = read_csv_rows(readiness_csv)
    worklist = build_missing_worklist_rows(readiness_rows)
    csv_path = output_dir / "ulf_component_efield_worklist.csv"
    manifest_path = output_dir / "ulf_component_efield_worklist_manifest.json"
    fieldnames = [
        "worklist_index",
        "subject_id",
        "name_en",
        "phase",
        "protocol",
        "side",
        "target",
        "contact",
        "frequency_hz",
        "frequency_class",
        "stimulation_pattern",
        "path_mode",
        "folder_path",
        "efield_path",
        "generation_status",
        "recommended_generator",
    ]
    write_csv(csv_path, worklist, fieldnames)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "summary": summarize_worklist(worklist),
            "outputs": {"csv": str(csv_path), "manifest": str(manifest_path)},
            "interpretation": "This worklist is report-only and does not run MATLAB or generate e-fields.",
        },
    )
    print(f"ULF component e-field worklist output: {csv_path}")
    print(f"Missing component e-fields: {len(worklist)}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-root", default=str(DEFAULT_READINESS_ROOT), help="ULF readiness run root.")
    parser.add_argument("--readiness-csv", default="", help="Explicit ULF component e-field availability CSV.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Worklist output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_worklist(args)


if __name__ == "__main__":
    raise SystemExit(main())
