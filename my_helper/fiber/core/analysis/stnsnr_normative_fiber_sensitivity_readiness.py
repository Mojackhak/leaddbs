#!/usr/bin/env python3
"""Readiness audit for dTOR normative-fiber OSS and jitter sensitivity layers."""

from __future__ import annotations

import argparse
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
            paths.extend(path for path in root.glob("*jitter*") if path.is_file())
    return paths


def assess_target_sensitivity_readiness(target: NormativeFiberTarget) -> dict[str, Any]:
    prefix = file_prefix_for_manifest(target.manifest_path)
    preprocess_dir = _preprocess_dir_from_manifest(target)
    oss_required = [
        preprocess_dir / "X_oss_float32_fiber_major.npy",
        preprocess_dir / "oss_parameter_manifest.json",
        preprocess_dir / "oss_activation_sidecar_metadata.json",
    ]
    missing_oss = _missing_paths(oss_required)
    oss_status = "ready_for_oss_sensitivity" if not missing_oss else "not_run_missing_oss_inputs"

    jitter_candidates = _jitter_candidate_paths(target, preprocess_dir)
    jitter_status = "ready_for_jitter_qc" if jitter_candidates else "not_run_missing_jitter_inputs"

    row = {
        "model_id": target.model_id,
        "manifest_path": str(target.manifest_path),
        "branch_dir": str(target.branch_dir),
        "preprocess_dir": str(preprocess_dir),
        "oss_sensitivity_status": oss_status,
        "oss_missing_inputs": ";".join(missing_oss),
        "oss_existing_inputs": ";".join(_existing_paths(oss_required)),
        "jitter_qc_status": jitter_status,
        "jitter_existing_inputs": ";".join(str(path) for path in jitter_candidates),
        "generated_at": iso_now(),
    }

    status_path = target.branch_dir / f"{prefix}_sensitivity_readiness_status.json"
    jitter_summary_path = target.branch_dir / f"{prefix}_jitter_summary.csv"
    write_json(
        status_path,
        {
            **row,
            "required_oss_inputs": [str(path) for path in oss_required],
            "jitter_input_search_roots": [str(target.branch_dir), str(preprocess_dir)],
        },
    )
    write_csv(
        jitter_summary_path,
        [
            {
                "model_id": target.model_id,
                "jitter_qc_status": jitter_status,
                "jitter_existing_inputs": row["jitter_existing_inputs"],
                "generated_at": row["generated_at"],
            }
        ],
        ["model_id", "jitter_qc_status", "jitter_existing_inputs", "generated_at"],
    )
    return row


def run_sensitivity_readiness(args: argparse.Namespace) -> int:
    readiness_csv = Path(args.readiness_csv).expanduser().resolve()
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
