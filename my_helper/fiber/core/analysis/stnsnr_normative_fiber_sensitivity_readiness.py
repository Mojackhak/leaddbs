#!/usr/bin/env python3
"""Readiness audit for dTOR normative-fiber OSS and jitter sensitivity layers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_normative_fiber_smoke_permutation import (
    DTOR_NORMATIVE_TARGET_IDS,
    NormativeFiberTarget,
    _load_json,
    discover_targets,
    file_prefix_for_manifest,
    iso_now,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


def _preprocess_dir_from_manifest(target: NormativeFiberTarget) -> Path:
    manifest = _load_json(target.manifest_path)
    outputs = manifest.get("outputs", {})
    if outputs.get("preprocess_dir"):
        return Path(outputs["preprocess_dir"]).expanduser().resolve()
    return target.branch_dir / "preprocess"


def _existing_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if path.exists()]


def _missing_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if not path.exists()]


def _jitter_candidate_paths(target: NormativeFiberTarget, preprocess_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for root in (target.branch_dir, preprocess_dir):
        if root.exists():
            for path in root.glob("*jitter*"):
                name = path.name
                if not path.is_file() or name.startswith("._"):
                    continue
                if any(token in name for token in ("summary", "status", "manifest")):
                    continue
                paths.append(path)
    return paths


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _complete_jitter_outputs(target: NormativeFiberTarget) -> tuple[str, str, list[str], list[str]]:
    prefix = file_prefix_for_manifest(target.manifest_path)
    summary_path = target.branch_dir / f"{prefix}_jitter_summary.csv"
    manifest_path = target.branch_dir / f"{prefix}_formal_jitter_manifest.json"
    expected = [summary_path, manifest_path]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        return "not_run_missing_jitter_inputs", "no_complete_jitter_qc_outputs_found", [], [str(path) for path in expected]
    rows = _read_csv_rows(summary_path)
    if not rows or str(rows[0].get("jitter_status", "")).strip().lower() != "complete":
        return "not_run_missing_jitter_inputs", "no_complete_jitter_qc_outputs_found", [], [str(path) for path in expected]
    try:
        n_jitters = int(float(rows[0].get("B", "0")))
    except (TypeError, ValueError):
        n_jitters = 0
    if n_jitters < 1000:
        return "not_run_missing_jitter_inputs", "no_formal_jitter_qc_outputs_found", [], [str(path) for path in expected]
    return "complete", "", [str(path) for path in expected], [str(path) for path in expected]


def assess_target_sensitivity_readiness(target: NormativeFiberTarget) -> dict[str, Any]:
    provenance = git_provenance()
    prefix = file_prefix_for_manifest(target.manifest_path)
    preprocess_dir = _preprocess_dir_from_manifest(target)
    oss_required = [
        preprocess_dir / "X_oss_float32_fiber_major.npy",
        preprocess_dir / "oss_parameter_manifest.json",
        preprocess_dir / "oss_activation_sidecar_metadata.json",
    ]
    missing_oss = _missing_paths(oss_required)
    oss_status = "ready_for_oss_sensitivity" if not missing_oss else "not_run_missing_oss_inputs"

    legacy_jitter_candidates = _jitter_candidate_paths(target, preprocess_dir)
    jitter_status, jitter_missing_reason, jitter_existing_outputs, jitter_expected_outputs = _complete_jitter_outputs(target)
    jitter_search_roots = [str(target.branch_dir), str(preprocess_dir)]

    row = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "branch_dir": str(target.branch_dir),
        "preprocess_dir": str(preprocess_dir),
        "oss_sensitivity_status": oss_status,
        "oss_missing_inputs": ";".join(missing_oss),
        "oss_existing_inputs": ";".join(_existing_paths(oss_required)),
        "jitter_qc_status": jitter_status,
        "jitter_missing_inputs": jitter_missing_reason,
        "jitter_existing_inputs": ";".join(jitter_existing_outputs),
        "jitter_expected_outputs": ";".join(jitter_expected_outputs),
        "legacy_jitter_candidate_inputs": ";".join(str(path) for path in legacy_jitter_candidates),
        "jitter_input_search_roots": ";".join(jitter_search_roots),
        "generated_at": iso_now(),
        "code_provenance": provenance,
    }

    status_path = target.branch_dir / f"{prefix}_sensitivity_readiness_status.json"
    readiness_jitter_status_path = target.branch_dir / f"{prefix}_sensitivity_readiness_jitter_status.csv"
    write_json(
        status_path,
        {
            **row,
            "required_oss_inputs": [str(path) for path in oss_required],
            "expected_jitter_outputs": jitter_expected_outputs,
            "jitter_input_search_roots": jitter_search_roots,
        },
    )
    write_csv(
        readiness_jitter_status_path,
        [
            {
                "model_id": target.model_id,
                "jitter_qc_status": jitter_status,
                "jitter_existing_inputs": row["jitter_existing_inputs"],
                "jitter_expected_outputs": row["jitter_expected_outputs"],
                "generated_at": row["generated_at"],
                "code_provenance": provenance,
            }
        ],
        ["model_id", "jitter_qc_status", "jitter_existing_inputs", "jitter_expected_outputs", "generated_at", "code_provenance"],
    )
    return row


def run_sensitivity_readiness(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
    provenance = git_provenance()
    requested = set(args.model_id) if args.model_id else None
    targets = discover_targets(readiness_csv, requested)
    if not targets:
        raise RuntimeError("no dTOR normative-fiber sensitivity readiness targets found")
    rows = []
    for target in targets:
        print(f"Auditing dTOR normative-fiber sensitivity readiness for {target.model_id}")
        rows.append(assess_target_sensitivity_readiness(target))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "normative_fiber_sensitivity_readiness_summary.csv"
    write_csv(summary_path, rows, list(rows[0].keys()))
    write_json(
        output_dir / "normative_fiber_sensitivity_readiness_manifest.json",
        {
            "generated_at": iso_now(),
            "readiness_csv": str(readiness_csv),
            "n_targets": len(rows),
            "code_provenance": provenance,
            "outputs": {"summary_csv": str(summary_path)},
        },
    )
    print(f"dTOR normative-fiber sensitivity readiness summary: {summary_path}")
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
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_sensitivity_readiness"),
        help="Cross-target sensitivity readiness summary directory.",
    )
    parser.add_argument("--model-id", action="append", choices=sorted(DTOR_NORMATIVE_TARGET_IDS), help="Optional model ID filter.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_sensitivity_readiness(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
