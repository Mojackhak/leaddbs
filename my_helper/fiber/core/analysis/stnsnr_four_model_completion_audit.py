#!/usr/bin/env python3
"""Build a completion/blocker audit for the STN/SNr four-model program."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stnsnr_four_model_final_reporting import FORMAL_ROOT, count_by, index_by_model_id
from stnsnr_io import MANIFEST_AUDIT_FIELDS, iso_now, read_csv, write_csv, write_json


COMPLETION_FIELDS = [
    "model_id",
    "model",
    "analysis_family",
    "final_model_status",
    "formal_target_status",
    "formal_readiness_status",
    "formal_resampling_status",
    "figure_output_status",
    "completion_status",
    "blocking_status",
    "blocker_categories",
    "blocker_detail",
    "schema_status",
    "missing_recommended_fields",
    "latest_manifest",
    *MANIFEST_AUDIT_FIELDS,
]


def index_schema_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("manifest_path", ""): row for row in rows if row.get("manifest_path")}


def has_missing_status(*values: str) -> bool:
    return any("missing" in str(value).lower() for value in values if value)


def add_blocker(blockers: list[str], details: list[str], category: str, detail: str = "") -> None:
    if category not in blockers:
        blockers.append(category)
    if detail:
        details.append(f"{category}: {detail}")


def classify_completion(
    final_row: dict[str, str],
    figure_row: dict[str, str] | None,
) -> dict[str, str]:
    final_status = final_row.get("final_model_status", "")
    formal_target = final_row.get("formal_target_status", "")
    formal_readiness = final_row.get("formal_readiness_status", "")
    formal_status = final_row.get("formal_resampling_status", "")
    figure_status = final_row.get("figure_output_status", "")
    blockers: list[str] = []
    details: list[str] = []

    if final_status.startswith("no_final_model") or final_status.startswith("absent"):
        add_blocker(blockers, details, "final_model_absent", final_status)

    if formal_target == "READY_FOR_FORMAL_RESAMPLING" and formal_readiness != "READY_FOR_FORMAL_DRIVER":
        add_blocker(blockers, details, "formal_driver_inputs", formal_readiness)

    if has_missing_status(final_row.get("oss_sensitivity_status", ""), final_row.get("oss_missing_inputs", "")):
        add_blocker(blockers, details, "oss_inputs", final_row.get("oss_missing_inputs", ""))

    if has_missing_status(final_row.get("fiber_jitter_qc_status", ""), final_row.get("jitter_missing_inputs", "")):
        add_blocker(blockers, details, "jitter_inputs", final_row.get("jitter_missing_inputs", ""))

    figure_density_status = figure_row.get("fiber_density_label_cache_status", "") if figure_row else ""
    if figure_status == "not_run_missing_density_label_cache" or figure_density_status == "not_run_missing_density_label_cache":
        add_blocker(blockers, details, "density_label_cache", figure_density_status or figure_status)

    if formal_target == "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING":
        return {
            "completion_status": "observed_robustness_no_formal_target",
            "blocking_status": "not_blocked_observed_only",
            "blocker_categories": ";".join(blockers),
            "blocker_detail": "; ".join(details),
        }

    if blockers:
        if any(category in blockers for category in ["oss_inputs", "jitter_inputs", "density_label_cache"]):
            completion_status = "blocked_missing_fiber_inputs"
        else:
            completion_status = "blocked_missing_required_inputs"
        return {
            "completion_status": completion_status,
            "blocking_status": "blocked",
            "blocker_categories": ";".join(blockers),
            "blocker_detail": "; ".join(details),
        }

    if formal_target == "READY_FOR_FORMAL_RESAMPLING" and formal_status:
        return {
            "completion_status": "complete_to_current_spec",
            "blocking_status": "not_blocked",
            "blocker_categories": "",
            "blocker_detail": "",
        }

    return {
        "completion_status": "not_classified",
        "blocking_status": "needs_review",
        "blocker_categories": "",
        "blocker_detail": "",
    }


def build_audit_rows(
    *,
    final_rows: list[dict[str, str]],
    figure_rows: list[dict[str, str]],
    schema_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    figure_by_id = index_by_model_id(figure_rows)
    schema_by_path = index_schema_rows(schema_rows)
    rows: list[dict[str, str]] = []
    for final_row in final_rows:
        manifest_path = final_row.get("latest_manifest", "")
        schema_row = schema_by_path.get(manifest_path, {})
        classification = classify_completion(final_row, figure_by_id.get(final_row.get("model_id", "")))
        rows.append(
            {
                "model_id": final_row.get("model_id", ""),
                "model": final_row.get("model", ""),
                "analysis_family": final_row.get("analysis_family", ""),
                "final_model_status": final_row.get("final_model_status", ""),
                "formal_target_status": final_row.get("formal_target_status", ""),
                "formal_readiness_status": final_row.get("formal_readiness_status", ""),
                "formal_resampling_status": final_row.get("formal_resampling_status", ""),
                "figure_output_status": final_row.get("figure_output_status", ""),
                **classification,
                "schema_status": schema_row.get("schema_status", ""),
                "missing_recommended_fields": schema_row.get("missing_recommended_fields", ""),
                "latest_manifest": manifest_path,
                "latest_manifest_provenance_status": final_row.get("latest_manifest_provenance_status", ""),
                "latest_manifest_stale_status": final_row.get("latest_manifest_stale_status", ""),
            }
        )
    return rows


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# STN/SNr Four-Model Completion Audit",
        "",
        "This audit summarizes the current final-model checkpoint. It does not run models or create missing inputs.",
        "",
        "| Model | Completion status | Blocking status | Blockers |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {completion_status} | {blocking_status} | {blocker_categories} |".format(
                **row
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_completion_audit(
    *,
    final_report_csv: Path,
    figure_readiness_csv: Path,
    all_endpoint_missing_work_csv: Path,
    manifest_schema_audit_csv: Path,
    output_dir: Path,
) -> dict[str, str]:
    final_rows = read_csv(Path(final_report_csv))
    if not final_rows:
        raise RuntimeError(f"no final report rows found in {final_report_csv}")
    figure_rows = read_csv(Path(figure_readiness_csv))
    all_endpoint_missing_work_rows = read_csv(Path(all_endpoint_missing_work_csv))
    schema_rows = read_csv(Path(manifest_schema_audit_csv))
    audit_rows = build_audit_rows(final_rows=final_rows, figure_rows=figure_rows, schema_rows=schema_rows)

    output_dir = Path(output_dir)
    audit_csv = output_dir / "four_model_completion_audit.csv"
    audit_md = output_dir / "four_model_completion_audit.md"
    manifest_json = output_dir / "four_model_completion_audit_manifest.json"
    write_csv(audit_csv, audit_rows, COMPLETION_FIELDS)
    write_markdown(audit_md, audit_rows)
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "inputs": {
                "final_report_csv": str(final_report_csv),
                "figure_readiness_csv": str(figure_readiness_csv),
                "all_endpoint_missing_work_csv": str(all_endpoint_missing_work_csv),
                "manifest_schema_audit_csv": str(manifest_schema_audit_csv),
            },
            "n_rows": len(audit_rows),
            "completion_status_counts": count_by(audit_rows, "completion_status"),
            "blocking_status_counts": count_by(audit_rows, "blocking_status"),
            "all_endpoint_missing_work_counts": count_by(all_endpoint_missing_work_rows, "work_status"),
            "schema_status_counts": count_by(schema_rows, "schema_status"),
            "outputs": {
                "completion_audit_csv": str(audit_csv),
                "completion_audit_md": str(audit_md),
                "manifest_json": str(manifest_json),
            },
        },
        add_code_provenance=True,
    )
    return {
        "completion_audit_csv": str(audit_csv),
        "completion_audit_md": str(audit_md),
        "manifest_json": str(manifest_json),
    }


def run_completion_audit(args: argparse.Namespace) -> int:
    outputs = build_completion_audit(
        final_report_csv=Path(args.final_report_csv).expanduser().resolve(),
        figure_readiness_csv=Path(args.figure_readiness_csv).expanduser().resolve(),
        all_endpoint_missing_work_csv=Path(args.all_endpoint_missing_work_csv).expanduser().resolve(),
        manifest_schema_audit_csv=Path(args.manifest_schema_audit_csv).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
    )
    print(f"Completion audit: {outputs['completion_audit_csv']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-report-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_final_report.csv"),
        help="Final report CSV.",
    )
    parser.add_argument(
        "--figure-readiness-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_figure_output_readiness.csv"),
        help="Figure-output readiness CSV.",
    )
    parser.add_argument(
        "--all-endpoint-missing-work-csv",
        default=str(FORMAL_ROOT / "all_endpoint_reporting/four_model_all_endpoint_missing_work.csv"),
        help="All-endpoint missing-work audit CSV.",
    )
    parser.add_argument(
        "--manifest-schema-audit-csv",
        default=str(FORMAL_ROOT / "manifest_schema_audit/four_model_manifest_schema_audit.csv"),
        help="Manifest schema audit CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "completion_audit"),
        help="Completion audit output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_completion_audit(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
