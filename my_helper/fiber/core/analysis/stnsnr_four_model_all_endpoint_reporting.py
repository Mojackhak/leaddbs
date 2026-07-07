#!/usr/bin/env python3
"""Build all-endpoint reporting and missing-work audits for STN/SNr."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_run_provenance import git_provenance


FORMAL_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution"
SUMMARY_ROOT = DEFAULT_VAL_ROOT / "summary"
MANIFEST_COMPANIONS = {
    "direct_voxel_HF_generation_manifest.json": {
        "model_id": "A",
        "model": "HF direct voxel",
        "prefix": "direct_voxel_HF",
    },
    "direct_voxel_ULF_only_generation_manifest.json": {
        "model_id": "C",
        "model": "ULF direct voxel",
        "prefix": "direct_voxel_ULF_only",
    },
    "normative_HF_fiber_generation_manifest.json": {
        "model_id": "B",
        "model": "HF normative fiber",
        "prefix": "normative_HF_fiber",
    },
    "normative_ULF_fiber_generation_manifest.json": {
        "model_id": "D",
        "model": "ULF normative fiber",
        "prefix": "normative_ULF_fiber",
    },
}
MISSING_WORK_ITEMS = [
    {
        "work_item_id": "C_chronic_gain_endpoint_sensitivity",
        "model_id": "C",
        "work_type": "gain_endpoint_sensitivity",
        "search_tokens": ("gain",),
    },
    {
        "work_item_id": "C_same_day_immediate_endpoint_family",
        "model_id": "C",
        "work_type": "same_day_immediate_endpoint_family",
        "search_tokens": ("immediate",),
    },
    {
        "work_item_id": "C_total_ulf_exposure_sensitivity",
        "model_id": "C",
        "work_type": "total_ulf_exposure_sensitivity",
        "search_tokens": ("total_ulf", "total-ulf", "totalulf"),
    },
    {
        "work_item_id": "D_chronic_gain_endpoint_sensitivity",
        "model_id": "D",
        "work_type": "gain_endpoint_sensitivity",
        "search_tokens": ("gain",),
    },
    {
        "work_item_id": "D_same_day_immediate_endpoint_family",
        "model_id": "D",
        "work_type": "same_day_immediate_endpoint_family",
        "search_tokens": ("immediate",),
    },
    {
        "work_item_id": "D_total_ulf_exposure_sensitivity",
        "model_id": "D",
        "work_type": "total_ulf_exposure_sensitivity",
        "search_tokens": ("total_ulf", "total-ulf", "totalulf"),
    },
]


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def branch_companion_status(manifest_path: Path, prefix: str) -> tuple[str, str, dict[str, str]]:
    required = {
        "manifest": manifest_path,
        "qc": manifest_path.parent / f"{prefix}_mapping_qc.json",
        "scores": manifest_path.parent / f"{prefix}_scores.csv",
        "predictions": manifest_path.parent / f"{prefix}_loocv_predictions.csv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    status = "complete_branch_outputs" if not missing else "missing_companion_outputs"
    return status, ";".join(missing), {key: str(path) for key, path in required.items()}


def endpoint_slug_from_manifest(manifest_path: Path) -> str:
    parts = manifest_path.parts
    for part in parts:
        if "_stn" in part or "_snr" in part:
            return part
    return manifest_path.parent.name


def connectome_label_from_path(path: Path) -> str:
    lowered = str(path).lower()
    if "ppmi" in lowered:
        return "PPMI"
    if "mgh" in lowered:
        return "MGH"
    if "dtor" in lowered:
        return "DTOR"
    return ""


def branch_role_from_path(path: Path) -> str:
    lowered = str(path).lower()
    if "delta_hf_adjusted" in lowered:
        return "delta_hf_adjusted"
    if "no_delta_hf" in lowered:
        return "no_delta_hf"
    return ""


def rows_from_hf_direct_scan(scan_summary_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_csv(scan_summary_csv):
        rows.append(
            {
                "source_table": "hf_direct_voxel_all_endpoint_scan",
                "model_id": "A",
                "model": "HF direct voxel",
                "endpoint_family": row.get("endpoint_family", ""),
                "scale": row.get("scale", ""),
                "scale_slug": row.get("scale_slug", ""),
                "connectome": "",
                "branch": "tau_coverage_source_resolver_scan",
                "branch_role": "source_resolver",
                "output_status": "source_resolver_scanned",
                "source_status": row.get("hf_voxel_source_status", ""),
                "prediction_status": row.get("hf_voxel_prediction_status", ""),
                "threshold_source": row.get("hf_voxel_threshold_source", ""),
                "selected_tau": row.get("hf_voxel_selected_tau_v_per_m") or row.get("selected_tau", ""),
                "selected_coverage": row.get("hf_voxel_selected_coverage") or row.get("selected_coverage", ""),
                "n_subjects": row.get("n_subjects", ""),
                "loocv_spearman_rho": row.get("selected_loocv_spearman_rho", ""),
                "q2": row.get("selected_q2", ""),
                "manifest_path": str(scan_summary_csv.with_name("all_scales_posthoc_threshold_scan_manifest.json")),
                "qc_path": "",
                "scores_path": "",
                "predictions_path": "",
                "missing_outputs": "",
            }
        )
    return rows


def rows_from_observed_summary(observed_branch_summary_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_csv(observed_branch_summary_csv):
        rows.append(
            {
                "source_table": "four_model_observed_branch_summary",
                "model_id": row.get("model_id", ""),
                "model": row.get("model", ""),
                "endpoint_family": "",
                "scale": "",
                "scale_slug": row.get("scale_slug", ""),
                "connectome": connectome_label_from_path(Path(row.get("manifest_path", ""))),
                "branch": row.get("branch", ""),
                "branch_role": "observed_branch",
                "output_status": "complete_branch_outputs" if row.get("output_exists") == "True" else "missing_outputs",
                "source_status": "",
                "prediction_status": "",
                "threshold_source": "",
                "selected_tau": "",
                "selected_coverage": "",
                "n_subjects": "",
                "loocv_spearman_rho": row.get("spearman_rho", ""),
                "q2": row.get("q2", ""),
                "manifest_path": row.get("manifest_path", ""),
                "qc_path": row.get("qc_path", ""),
                "scores_path": "",
                "predictions_path": row.get("predictions_path", ""),
                "missing_outputs": "",
            }
        )
    return rows


def rows_from_final_report(final_report_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_csv(final_report_csv):
        rows.append(
            {
                "source_table": "four_model_final_report",
                "model_id": row.get("model_id", ""),
                "model": row.get("model", ""),
                "endpoint_family": "",
                "scale": "",
                "scale_slug": "",
                "connectome": connectome_label_from_path(Path(row.get("latest_manifest", ""))),
                "branch": row.get("final_branch_or_source", ""),
                "branch_role": row.get("final_model_role", ""),
                "output_status": row.get("figure_output_status", ""),
                "source_status": "",
                "prediction_status": row.get("final_model_status", ""),
                "threshold_source": "",
                "selected_tau": "",
                "selected_coverage": "",
                "n_subjects": row.get("n_subjects", ""),
                "loocv_spearman_rho": "",
                "q2": "",
                "manifest_path": row.get("latest_manifest", ""),
                "qc_path": "",
                "scores_path": "",
                "predictions_path": "",
                "missing_outputs": "",
            }
        )
    return rows


def discover_generation_manifests(roots: list[Path]) -> list[Path]:
    manifests: list[Path] = []
    names = set(MANIFEST_COMPANIONS)
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*generation_manifest.json"):
            if path.name.startswith("._") or path.name not in names:
                continue
            manifests.append(path)
    return sorted(set(manifests))


def rows_from_discovered_manifests(manifest_roots: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for manifest_path in discover_generation_manifests(manifest_roots):
        spec = MANIFEST_COMPANIONS[manifest_path.name]
        output_status, missing, companion_paths = branch_companion_status(manifest_path, spec["prefix"])
        connectome = connectome_label_from_path(manifest_path)
        model_id = spec["model_id"]
        if model_id in {"B", "D"} and connectome:
            model_id = f"{model_id}_{connectome}"
        rows.append(
            {
                "source_table": "discovered_branch_manifest",
                "model_id": model_id,
                "model": spec["model"],
                "endpoint_family": "",
                "scale": "",
                "scale_slug": endpoint_slug_from_manifest(manifest_path),
                "connectome": connectome,
                "branch": manifest_path.parent.name,
                "branch_role": branch_role_from_path(manifest_path),
                "output_status": output_status,
                "source_status": "",
                "prediction_status": "",
                "threshold_source": "",
                "selected_tau": "",
                "selected_coverage": "",
                "n_subjects": "",
                "loocv_spearman_rho": "",
                "q2": "",
                "manifest_path": companion_paths["manifest"],
                "qc_path": companion_paths["qc"],
                "scores_path": companion_paths["scores"],
                "predictions_path": companion_paths["predictions"],
                "missing_outputs": missing,
            }
        )
    return rows


def search_paths_for_tokens(roots: list[Path], tokens: tuple[str, ...], model_id: str) -> list[Path]:
    matches: list[Path] = []
    model_hint = "direct_voxel/ulf" if model_id == "C" else "normative_connectome_fiber/ulf"
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.name.startswith("._"):
                continue
            lowered = str(path).lower().replace("\\", "/")
            if model_hint not in lowered:
                continue
            if any(token in lowered for token in tokens):
                matches.append(path)
    return sorted(set(matches))


def build_missing_work_rows(search_roots: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in MISSING_WORK_ITEMS:
        matches = search_paths_for_tokens(search_roots, item["search_tokens"], item["model_id"])
        rows.append(
            {
                "work_item_id": item["work_item_id"],
                "model_id": item["model_id"],
                "work_type": item["work_type"],
                "work_status": "observed_outputs_detected" if matches else "not_run_missing_observed_outputs",
                "matched_paths": ";".join(str(path) for path in matches[:20]),
                "note": "reporting audit only; this row does not execute the model driver",
            }
        )
    return rows


def write_markdown(path: Path, report_rows: list[dict[str, str]], missing_rows: list[dict[str, str]]) -> None:
    counts = count_by(report_rows, "source_table")
    missing_counts = count_by(missing_rows, "work_status")
    lines = [
        "# STN/SNr Four-Model All-Endpoint Report",
        "",
        "This report aggregates existing endpoint-level outputs and records missing sensitivity work. It does not fit models.",
        "",
        "## Row Counts",
        "",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Missing Work Counts", ""])
    for key, value in sorted(missing_counts.items()):
        lines.append(f"- {key}: {value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def default_manifest_roots() -> list[Path]:
    return [SUMMARY_ROOT / "direct_voxel", SUMMARY_ROOT / "normative_connectome_fiber"]


def build_all_endpoint_reporting(
    *,
    hf_direct_scan_summary_csv: Path,
    observed_branch_summary_csv: Path,
    final_report_csv: Path,
    manifest_roots: list[Path],
    missing_work_search_roots: list[Path],
    output_dir: Path,
) -> dict[str, str]:
    report_rows = []
    report_rows.extend(rows_from_hf_direct_scan(Path(hf_direct_scan_summary_csv)))
    report_rows.extend(rows_from_observed_summary(Path(observed_branch_summary_csv)))
    report_rows.extend(rows_from_final_report(Path(final_report_csv)))
    report_rows.extend(rows_from_discovered_manifests(manifest_roots))
    missing_rows = build_missing_work_rows(missing_work_search_roots)

    output_dir = Path(output_dir)
    report_csv = output_dir / "four_model_all_endpoint_report.csv"
    missing_csv = output_dir / "four_model_all_endpoint_missing_work.csv"
    report_md = output_dir / "four_model_all_endpoint_report.md"
    manifest_json = output_dir / "four_model_all_endpoint_reporting_manifest.json"
    report_fields = [
        "source_table",
        "model_id",
        "model",
        "endpoint_family",
        "scale",
        "scale_slug",
        "connectome",
        "branch",
        "branch_role",
        "output_status",
        "source_status",
        "prediction_status",
        "threshold_source",
        "selected_tau",
        "selected_coverage",
        "n_subjects",
        "loocv_spearman_rho",
        "q2",
        "manifest_path",
        "qc_path",
        "scores_path",
        "predictions_path",
        "missing_outputs",
    ]
    missing_fields = ["work_item_id", "model_id", "work_type", "work_status", "matched_paths", "note"]
    write_csv(report_csv, report_rows, report_fields)
    write_csv(missing_csv, missing_rows, missing_fields)
    write_markdown(report_md, report_rows, missing_rows)
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "inputs": {
                "hf_direct_scan_summary_csv": str(hf_direct_scan_summary_csv),
                "observed_branch_summary_csv": str(observed_branch_summary_csv),
                "final_report_csv": str(final_report_csv),
                "manifest_roots": [str(path) for path in manifest_roots],
                "missing_work_search_roots": [str(path) for path in missing_work_search_roots],
            },
            "n_report_rows": len(report_rows),
            "n_missing_work_rows": len(missing_rows),
            "source_table_counts": count_by(report_rows, "source_table"),
            "missing_work_counts": count_by(missing_rows, "work_status"),
            "code_provenance": git_provenance(),
            "outputs": {
                "all_endpoint_report_csv": str(report_csv),
                "all_endpoint_report_md": str(report_md),
                "missing_work_csv": str(missing_csv),
                "manifest_json": str(manifest_json),
            },
        },
    )
    return {
        "all_endpoint_report_csv": str(report_csv),
        "all_endpoint_report_md": str(report_md),
        "missing_work_csv": str(missing_csv),
        "manifest_json": str(manifest_json),
    }


def run_all_endpoint_reporting(args: argparse.Namespace) -> int:
    roots = [Path(path).expanduser().resolve() for path in args.manifest_root]
    search_roots = [Path(path).expanduser().resolve() for path in args.missing_work_search_root]
    outputs = build_all_endpoint_reporting(
        hf_direct_scan_summary_csv=Path(args.hf_direct_scan_summary_csv).expanduser().resolve(),
        observed_branch_summary_csv=Path(args.observed_branch_summary_csv).expanduser().resolve(),
        final_report_csv=Path(args.final_report_csv).expanduser().resolve(),
        manifest_roots=roots,
        missing_work_search_roots=search_roots,
        output_dir=Path(args.output_dir).expanduser().resolve(),
    )
    print(f"All-endpoint report: {outputs['all_endpoint_report_csv']}")
    print(f"Missing-work audit: {outputs['missing_work_csv']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hf-direct-scan-summary-csv",
        default=str(SUMMARY_ROOT / "direct_voxel/hf/posthoc_threshold_scan_all_scales/all_scales_posthoc_threshold_scan_summary.csv"),
        help="A-model all-endpoint HF direct voxel source-resolver scan summary.",
    )
    parser.add_argument(
        "--observed-branch-summary-csv",
        default=str(FORMAL_ROOT / "status/four_model_observed_branch_summary.csv"),
        help="Consolidated observed branch summary CSV.",
    )
    parser.add_argument(
        "--final-report-csv",
        default=str(FORMAL_ROOT / "final_reporting/four_model_final_report.csv"),
        help="Final reporting CSV.",
    )
    parser.add_argument(
        "--manifest-root",
        action="append",
        default=[str(path) for path in default_manifest_roots()],
        help="Root to search for existing generation manifests.",
    )
    parser.add_argument(
        "--missing-work-search-root",
        action="append",
        default=[str(path) for path in default_manifest_roots()],
        help="Root to search for gain/immediate/total-ULF outputs.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "all_endpoint_reporting"),
        help="All-endpoint reporting output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_all_endpoint_reporting(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
