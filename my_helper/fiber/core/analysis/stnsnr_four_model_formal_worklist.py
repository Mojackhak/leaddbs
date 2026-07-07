#!/usr/bin/env python3
"""Build a final-model formal target worklist for the STN/SNr four-model plan."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_io import MANIFEST_AUDIT_FIELDS, iso_now, manifest_audit_fields, read_csv, write_csv, write_json

READY_FINAL_STATUSES = {"final_model_error_predictive", "final_model_error_nonpredictive"}
FORMAL_TARGET_MODEL_IDS = {"A", "B_DTOR", "C", "D_DTOR"}
OBSERVED_ROBUSTNESS_MODEL_IDS = {"B_PPMI", "B_MGH", "D_PPMI"}


def final_model_kind(row: dict[str, str]) -> str:
    model_id = row.get("model_id", "")
    if model_id in {"A", "B_PPMI", "B_MGH", "B_DTOR"}:
        return "hf"
    if model_id in {"C", "D_PPMI", "D_DTOR"}:
        return "ulf"
    return "unknown"


def formal_target_row(row: dict[str, str]) -> dict[str, str]:
    kind = final_model_kind(row)
    if kind == "hf":
        final_status = row.get("hf_final_model_status", "")
        final_branch_or_source = row.get("hf_final_model_source", "")
        final_role = row.get("hf_final_model_role", "")
        selection_reason = row.get("hf_final_model_selection_reason", "")
    elif kind == "ulf":
        final_status = row.get("ulf_final_model_status", "")
        final_branch_or_source = row.get("ulf_final_model_branch", "")
        final_role = row.get("ulf_final_model_role", "")
        selection_reason = row.get("ulf_final_model_selection_reason", "")
    else:
        final_status = ""
        final_branch_or_source = ""
        final_role = ""
        selection_reason = "unknown_model_id"

    if final_status in READY_FINAL_STATUSES and row.get("model_id", "") in FORMAL_TARGET_MODEL_IDS:
        target_status = "READY_FOR_FORMAL_RESAMPLING"
        reason = "accepted_final_model"
    elif final_status in READY_FINAL_STATUSES and row.get("model_id", "") in OBSERVED_ROBUSTNESS_MODEL_IDS:
        target_status = "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING"
        reason = "connectome_observed_robustness_only"
    elif final_status:
        target_status = "NO_FINAL_MODEL"
        reason = final_status
    else:
        target_status = "WAITING_FOR_FINAL_MODEL_CLASSIFICATION"
        reason = "missing_final_model_status"

    return {
        "model_id": row.get("model_id", ""),
        "model": row.get("model", ""),
        "model_family": kind,
        "observed_branch": row.get("branch", ""),
        "final_branch_or_source": final_branch_or_source,
        "final_model_role": final_role,
        "final_model_status": final_status,
        "final_model_selection_reason": selection_reason,
        "formal_target_status": target_status,
        "formal_target_reason": reason,
        "formal_resampling_status": row.get("formal_resampling_status", ""),
        "latest_manifest": row.get("latest_manifest", ""),
        **manifest_audit_fields(row),
    }


def build_worklist(status_csv: Path) -> list[dict[str, str]]:
    return [formal_target_row(row) for row in read_csv(status_csv)]


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# STN/SNr Final-Model Formal Target Worklist",
        "",
        "| Model | Family | Final branch/source | Final role | Final status | Formal target |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {model_family} | {final_branch_or_source} | "
            "{final_model_role} | {final_model_status} | {formal_target_status} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_worklist(args: argparse.Namespace) -> int:
    status_csv = Path(args.status_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    rows = build_worklist(status_csv)
    csv_path = output_dir / "four_model_formal_target_worklist.csv"
    md_path = output_dir / "four_model_formal_target_worklist.md"
    manifest_path = output_dir / "four_model_formal_target_worklist_manifest.json"
    fieldnames = [
        "model_id",
        "model",
        "model_family",
        "observed_branch",
        "final_branch_or_source",
        "final_model_role",
        "final_model_status",
        "final_model_selection_reason",
        "formal_target_status",
        "formal_target_reason",
        "formal_resampling_status",
        "latest_manifest",
        *MANIFEST_AUDIT_FIELDS,
    ]
    write_csv(csv_path, rows, fieldnames)
    write_markdown(md_path, rows)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "status_csv": str(status_csv),
            "n_rows": len(rows),
            "target_counts": count_by(rows, "formal_target_status"),
            "outputs": {"csv": str(csv_path), "markdown": str(md_path), "manifest": str(manifest_path)},
        },
        add_code_provenance=True,
    )
    print(f"Formal target worklist output: {csv_path}")
    for row in rows:
        print(f"{row['model_id']} {row['formal_target_status']}: {row['final_branch_or_source']}")
    return 0


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-csv",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/status/four_model_execution_status.csv"),
        help="Consolidated four-model execution status CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/formal_worklist"),
        help="Formal target worklist output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_worklist(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
