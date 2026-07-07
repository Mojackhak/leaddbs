#!/usr/bin/env python3
"""Audit manifest schema completeness for STN/SNr four-model outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_io import (
    iso_now,
    manifest_provenance_status,
    manifest_stale_status,
    read_csv,
    write_csv,
    write_json,
)
from stnsnr_run_provenance import git_provenance


FORMAL_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution"
RECOMMENDED_MANIFEST_FIELDS = ["code_provenance", "generated_at", "outputs"]


def add_manifest_ref(refs_by_path: dict[str, set[str]], path_text: str, source_ref: str) -> None:
    if not path_text:
        return
    refs_by_path.setdefault(str(path_text), set()).add(source_ref)


def collect_manifest_refs(
    *,
    status_csv: Path,
    final_report_csv: Path,
    all_endpoint_report_csv: Path,
) -> dict[str, set[str]]:
    refs_by_path: dict[str, set[str]] = {}
    for row in read_csv(status_csv):
        add_manifest_ref(refs_by_path, row.get("latest_manifest", ""), f"status:{row.get('model_id', '')}")
    for row in read_csv(final_report_csv):
        add_manifest_ref(refs_by_path, row.get("latest_manifest", ""), f"final_report:{row.get('model_id', '')}")
    for row in read_csv(all_endpoint_report_csv):
        add_manifest_ref(refs_by_path, row.get("manifest_path", ""), f"all_endpoint:{row.get('model_id', '')}")
    return refs_by_path


def load_manifest_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except json.JSONDecodeError as exc:
        return {}, f"{exc.__class__.__name__}: {exc}"


def schema_audit_row(manifest_path: str, source_refs: set[str], current_commit: str) -> dict[str, str]:
    path = Path(manifest_path)
    base = {
        "manifest_path": manifest_path,
        "manifest_name": path.name,
        "source_refs": ";".join(sorted(source_refs)),
    }
    if not path.is_file():
        return {
            **base,
            "manifest_exists_status": "missing_manifest",
            "json_parse_status": "not_applicable_missing_manifest",
            "schema_status": "missing_manifest",
            "missing_recommended_fields": "",
            "has_code_provenance": "false",
            "has_generated_at": "false",
            "has_outputs": "false",
            "latest_manifest_provenance_status": "missing_manifest",
            "latest_manifest_stale_status": "missing_manifest",
        }
    data, parse_error = load_manifest_json(path)
    if parse_error:
        return {
            **base,
            "manifest_exists_status": "manifest_exists",
            "json_parse_status": "invalid_json",
            "schema_status": "invalid_json",
            "missing_recommended_fields": "",
            "has_code_provenance": "false",
            "has_generated_at": "false",
            "has_outputs": "false",
            "latest_manifest_provenance_status": "invalid_json",
            "latest_manifest_stale_status": "invalid_json",
        }
    missing = [field for field in RECOMMENDED_MANIFEST_FIELDS if field not in data]
    return {
        **base,
        "manifest_exists_status": "manifest_exists",
        "json_parse_status": "valid_json",
        "schema_status": "schema_complete" if not missing else "schema_missing_recommended_fields",
        "missing_recommended_fields": ";".join(missing),
        "has_code_provenance": str("code_provenance" in data).lower(),
        "has_generated_at": str("generated_at" in data).lower(),
        "has_outputs": str("outputs" in data).lower(),
        "latest_manifest_provenance_status": manifest_provenance_status(manifest_path),
        "latest_manifest_stale_status": manifest_stale_status(manifest_path, current_commit),
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# STN/SNr Four-Model Manifest Schema Audit",
        "",
        "This audit scans existing manifest references. It does not fit models or change model status.",
        "",
        "## Schema Counts",
        "",
    ]
    for key, value in sorted(count_by(rows, "schema_status").items()):
        lines.append(f"- {key}: {value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manifest_schema_audit(
    *,
    status_csv: Path,
    final_report_csv: Path,
    all_endpoint_report_csv: Path,
    output_dir: Path,
    current_commit: str = "",
) -> dict[str, str]:
    commit = current_commit or str(git_provenance().get("git_commit", "") or "")
    refs_by_path = collect_manifest_refs(
        status_csv=Path(status_csv),
        final_report_csv=Path(final_report_csv),
        all_endpoint_report_csv=Path(all_endpoint_report_csv),
    )
    rows = [
        schema_audit_row(manifest_path, refs_by_path[manifest_path], commit)
        for manifest_path in sorted(refs_by_path)
    ]
    output_dir = Path(output_dir)
    csv_path = output_dir / "four_model_manifest_schema_audit.csv"
    md_path = output_dir / "four_model_manifest_schema_audit.md"
    manifest_path = output_dir / "four_model_manifest_schema_audit_manifest.json"
    fields = [
        "manifest_path",
        "manifest_name",
        "source_refs",
        "manifest_exists_status",
        "json_parse_status",
        "schema_status",
        "missing_recommended_fields",
        "has_code_provenance",
        "has_generated_at",
        "has_outputs",
        "latest_manifest_provenance_status",
        "latest_manifest_stale_status",
    ]
    write_csv(csv_path, rows, fields)
    write_markdown(md_path, rows)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "inputs": {
                "status_csv": str(status_csv),
                "final_report_csv": str(final_report_csv),
                "all_endpoint_report_csv": str(all_endpoint_report_csv),
            },
            "n_manifest_rows": len(rows),
            "schema_status_counts": count_by(rows, "schema_status"),
            "manifest_provenance_counts": count_by(rows, "latest_manifest_provenance_status"),
            "manifest_stale_counts": count_by(rows, "latest_manifest_stale_status"),
            "outputs": {
                "schema_audit_csv": str(csv_path),
                "schema_audit_md": str(md_path),
                "manifest_json": str(manifest_path),
            },
        },
        add_code_provenance=True,
    )
    return {
        "schema_audit_csv": str(csv_path),
        "schema_audit_md": str(md_path),
        "manifest_json": str(manifest_path),
    }


def run_manifest_schema_audit(args: argparse.Namespace) -> int:
    outputs = build_manifest_schema_audit(
        status_csv=Path(args.status_csv).expanduser().resolve(),
        final_report_csv=Path(args.final_report_csv).expanduser().resolve(),
        all_endpoint_report_csv=Path(args.all_endpoint_report_csv).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
    )
    print(f"Manifest schema audit: {outputs['schema_audit_csv']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-csv",
        default=str(FORMAL_ROOT / "status/four_model_execution_status.csv"),
        help="Consolidated execution status CSV.",
    )
    parser.add_argument(
        "--final-report-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_final_report.csv"),
        help="Final report CSV.",
    )
    parser.add_argument(
        "--all-endpoint-report-csv",
        default=str(FORMAL_ROOT / "all_endpoint_reporting/four_model_all_endpoint_report.csv"),
        help="All-endpoint report CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "manifest_schema_audit"),
        help="Manifest schema audit output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_manifest_schema_audit(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
