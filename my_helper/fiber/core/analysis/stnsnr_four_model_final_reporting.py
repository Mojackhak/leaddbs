#!/usr/bin/env python3
"""Build final reporting and figure-output readiness summaries for STN/SNr."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_io import MANIFEST_AUDIT_FIELDS, iso_now, manifest_audit_fields, read_csv, write_csv, write_json


FORMAL_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution"
DIRECT_DISPLAY_FILES_BY_MANIFEST = {
    "direct_voxel_HF_generation_manifest.json": [
        "direct_voxel_HF_coef.nii.gz",
        "direct_voxel_HF_sweet_sour.nii.gz",
        "direct_voxel_HF_stability.nii.gz",
        "direct_voxel_HF_bootstrap_se.nii.gz",
        "direct_voxel_HF_jitter_se.nii.gz",
    ],
    "direct_voxel_ULF_only_generation_manifest.json": [
        "direct_voxel_ULF_only_coef.nii.gz",
        "direct_voxel_ULF_only_sweet_sour.nii.gz",
        "direct_voxel_ULF_only_stability.nii.gz",
        "direct_voxel_ULF_only_bootstrap_se.nii.gz",
        "direct_voxel_ULF_only_jitter_se.nii.gz",
    ],
}
FIBER_BASIC_DENSITY_CACHE_PATTERNS = [
    "*density*lookup*",
    "*streamline*voxel*density*",
]
FIBER_LABEL_CACHE_PATTERNS = [
    "*endpoint*label*cache*",
    "*fiber*label*cache*",
]
FIBER_FDR_CACHE_PATTERNS = [
    "*fdr*",
    "*q_value*",
    "*q-value*",
]
FIBER_ENRICHMENT_CACHE_PATTERNS = [
    "*enrichment*",
]


def index_by_model_id(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("model_id", "")): row for row in rows if row.get("model_id")}


def model_family(model_id: str, model: str, worklist_row: dict[str, str] | None = None) -> str:
    if worklist_row and worklist_row.get("model_family"):
        return worklist_row["model_family"]
    if model_id in {"A", "B_PPMI", "B_MGH", "B_DTOR"}:
        return "hf"
    if model_id in {"C", "D_PPMI", "D_DTOR"}:
        return "ulf"
    text = model.lower()
    if "ulf" in text:
        return "ulf"
    if "hf" in text:
        return "hf"
    return "unknown"


def analysis_family(model_id: str, manifest_path: str) -> str:
    manifest_name = Path(manifest_path).name if manifest_path else ""
    if "direct_voxel" in manifest_name or model_id in {"A", "C"}:
        return "direct_voxel"
    if "fiber" in manifest_name or model_id.startswith(("B_", "D_")):
        return "normative_fiber"
    return "unknown"


def final_branch_or_source(status_row: dict[str, str], worklist_row: dict[str, str] | None) -> str:
    if worklist_row and worklist_row.get("final_branch_or_source"):
        return worklist_row["final_branch_or_source"]
    return (
        status_row.get("hf_final_model_source")
        or status_row.get("ulf_final_model_branch")
        or status_row.get("branch")
        or ""
    )


def final_model_role(status_row: dict[str, str], worklist_row: dict[str, str] | None) -> str:
    if worklist_row and worklist_row.get("final_model_role"):
        return worklist_row["final_model_role"]
    return status_row.get("hf_final_model_role") or status_row.get("ulf_final_model_role") or ""


def final_model_status(status_row: dict[str, str], worklist_row: dict[str, str] | None) -> str:
    if worklist_row and worklist_row.get("final_model_status"):
        return worklist_row["final_model_status"]
    return status_row.get("hf_final_model_status") or status_row.get("ulf_final_model_status") or ""


def first_value(*values: str | None) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def direct_display_readiness(manifest_path: str) -> dict[str, str]:
    if not manifest_path:
        return {
            "direct_voxel_display_status": "not_applicable_not_direct_voxel",
            "direct_voxel_missing_display_maps": "",
        }
    manifest = Path(manifest_path)
    required_files = DIRECT_DISPLAY_FILES_BY_MANIFEST.get(manifest.name)
    if not required_files:
        return {
            "direct_voxel_display_status": "not_applicable_not_direct_voxel",
            "direct_voxel_missing_display_maps": "",
        }
    branch_dir = manifest.parent
    missing = [str(branch_dir / filename) for filename in required_files if not (branch_dir / filename).is_file()]
    if missing:
        return {
            "direct_voxel_display_status": "not_run_missing_display_source_maps",
            "direct_voxel_missing_display_maps": ";".join(missing),
        }
    return {
        "direct_voxel_display_status": "ready_from_existing_maps",
        "direct_voxel_missing_display_maps": "",
    }


def candidate_density_cache_roots(manifest_path: str, extra_roots: list[Path]) -> list[Path]:
    roots: list[Path] = []
    if manifest_path:
        branch_dir = Path(manifest_path).parent
        roots.extend([branch_dir, branch_dir / "preprocess"])
    roots.extend(extra_roots)
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_cache_paths(manifest_path: str, density_cache_roots: list[Path], patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for root in candidate_density_cache_roots(manifest_path, density_cache_roots):
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                if path.is_file() and not path.name.startswith("._"):
                    paths.append(path)
    return sorted(set(paths))


def fiber_density_readiness(manifest_path: str, density_cache_roots: list[Path]) -> dict[str, str]:
    manifest_name = Path(manifest_path).name if manifest_path else ""
    if "fiber" not in manifest_name:
        return {
            "fiber_density_label_cache_status": "not_applicable_not_normative_fiber",
            "fiber_density_label_cache_paths": "",
        }
    density_caches = find_cache_paths(manifest_path, density_cache_roots, FIBER_BASIC_DENSITY_CACHE_PATTERNS)
    label_caches = find_cache_paths(manifest_path, density_cache_roots, FIBER_LABEL_CACHE_PATTERNS)
    fdr_caches = find_cache_paths(manifest_path, density_cache_roots, FIBER_FDR_CACHE_PATTERNS)
    enrichment_caches = find_cache_paths(manifest_path, density_cache_roots, FIBER_ENRICHMENT_CACHE_PATTERNS)
    all_caches = sorted(set(density_caches + label_caches + fdr_caches + enrichment_caches))
    if not all_caches:
        return {
            "fiber_density_label_cache_status": "not_run_missing_density_label_cache",
            "fiber_density_label_cache_paths": "",
        }
    if density_caches and not label_caches:
        return {
            "fiber_density_label_cache_status": "ready_from_existing_basic_density_cache",
            "fiber_density_label_cache_paths": ";".join(str(path) for path in density_caches),
        }
    if density_caches and label_caches and (not fdr_caches or not enrichment_caches):
        return {
            "fiber_density_label_cache_status": "ready_from_existing_density_label_cache_missing_fdr_enrichment",
            "fiber_density_label_cache_paths": ";".join(
                str(path) for path in sorted(set(density_caches + label_caches + fdr_caches + enrichment_caches))
            ),
        }
    return {
        "fiber_density_label_cache_status": "ready_from_existing_density_label_fdr_enrichment_cache",
        "fiber_density_label_cache_paths": ";".join(str(path) for path in all_caches),
    }


def figure_output_status(
    *,
    family: str,
    direct_status: str,
    fiber_status: str,
    final_status: str,
) -> str:
    if final_status.startswith("no_final_model"):
        return "not_applicable_no_final_model"
    if family == "direct_voxel":
        if direct_status == "ready_from_existing_maps":
            return "ready_from_existing_direct_voxel_maps"
        return direct_status
    if family == "normative_fiber":
        if fiber_status == "ready_from_existing_basic_density_cache":
            return "ready_for_basic_fiber_density_outputs"
        if fiber_status == "ready_from_existing_density_label_cache_missing_fdr_enrichment":
            return "ready_for_density_label_outputs"
        if fiber_status == "ready_from_existing_density_label_fdr_enrichment_cache":
            return "ready_for_full_fiber_figure_outputs"
        return "not_run_missing_density_label_cache"
    return "not_applicable_unknown_analysis_family"


def build_report_row(
    *,
    status_row: dict[str, str],
    worklist_row: dict[str, str] | None,
    readiness_row: dict[str, str] | None,
    direct_permutation_row: dict[str, str] | None,
    direct_bootstrap_row: dict[str, str] | None,
    direct_jitter_row: dict[str, str] | None,
    fiber_permutation_row: dict[str, str] | None,
    fiber_bootstrap_row: dict[str, str] | None,
    fiber_sensitivity_row: dict[str, str] | None,
    density_cache_roots: list[Path],
    cohort_n: int,
) -> tuple[dict[str, str], dict[str, str]]:
    model_id = status_row.get("model_id", "")
    manifest_path = first_value(
        status_row.get("latest_manifest"),
        worklist_row.get("latest_manifest") if worklist_row else "",
    )
    family = analysis_family(model_id, manifest_path)
    direct_readiness = direct_display_readiness(manifest_path)
    density_readiness = fiber_density_readiness(manifest_path, density_cache_roots)
    model_status = final_model_status(status_row, worklist_row)
    output_status = figure_output_status(
        family=family,
        direct_status=direct_readiness["direct_voxel_display_status"],
        fiber_status=density_readiness["fiber_density_label_cache_status"],
        final_status=model_status,
    )
    permutation_row = fiber_permutation_row if family == "normative_fiber" else direct_permutation_row
    bootstrap_row = fiber_bootstrap_row if family == "normative_fiber" else direct_bootstrap_row
    row = {
        "model_id": model_id,
        "model": status_row.get("model", ""),
        "model_family": model_family(model_id, status_row.get("model", ""), worklist_row),
        "analysis_family": family,
        "observed_branch": status_row.get("branch", ""),
        "final_branch_or_source": final_branch_or_source(status_row, worklist_row),
        "final_model_role": final_model_role(status_row, worklist_row),
        "final_model_status": model_status,
        "formal_target_status": worklist_row.get("formal_target_status", "") if worklist_row else "",
        "formal_readiness_status": readiness_row.get("formal_readiness_status", "") if readiness_row else "",
        "formal_resampling_status": status_row.get("formal_resampling_status", ""),
        "formal_p_plus_one_two_sided": permutation_row.get("p_plus_one_two_sided", "") if permutation_row else "",
        "permutation_status": permutation_row.get("permutation_status", "") if permutation_row else "",
        "bootstrap_status": bootstrap_row.get("bootstrap_status", "") if bootstrap_row else "",
        "finite_bootstrap_count": bootstrap_row.get("finite_bootstrap_count", "") if bootstrap_row else "",
        "jitter_status": direct_jitter_row.get("jitter_status", "") if direct_jitter_row else "",
        "finite_jitter_count": direct_jitter_row.get("finite_jitter_count", "") if direct_jitter_row else "",
        "oss_sensitivity_status": fiber_sensitivity_row.get("oss_sensitivity_status", "") if fiber_sensitivity_row else "",
        "oss_missing_inputs": fiber_sensitivity_row.get("oss_missing_inputs", "") if fiber_sensitivity_row else "",
        "fiber_jitter_qc_status": fiber_sensitivity_row.get("jitter_qc_status", "") if fiber_sensitivity_row else "",
        "jitter_missing_inputs": fiber_sensitivity_row.get("jitter_missing_inputs", "") if fiber_sensitivity_row else "",
        "jitter_input_search_roots": fiber_sensitivity_row.get("jitter_input_search_roots", "") if fiber_sensitivity_row else "",
        "figure_output_status": output_status,
        "n_subjects": str(cohort_n),
        "hypothesis_generating": "true",
        "interpretation": f"hypothesis_generating_n{cohort_n}",
        "latest_manifest": manifest_path,
        **manifest_audit_fields(status_row),
    }
    readiness = {
        "model_id": model_id,
        "analysis_family": family,
        "final_branch_or_source": row["final_branch_or_source"],
        "final_model_status": model_status,
        **direct_readiness,
        **density_readiness,
        "oss_sensitivity_status": row["oss_sensitivity_status"],
        "oss_missing_inputs": row["oss_missing_inputs"],
        "fiber_jitter_qc_status": row["fiber_jitter_qc_status"],
        "jitter_missing_inputs": row["jitter_missing_inputs"],
        "jitter_input_search_roots": row["jitter_input_search_roots"],
        "formal_resampling_status": row["formal_resampling_status"],
        "figure_output_status": output_status,
        "latest_manifest": manifest_path,
        **manifest_audit_fields(row),
    }
    return row, readiness


def write_markdown(path: Path, rows: list[dict[str, str]], cohort_n: int) -> None:
    lines = [
        "# STN/SNr Four-Model Final Report",
        "",
        f"Current formal interpretation is hypothesis-generating because the cohort size is n={cohort_n}.",
        "This report summarizes automatically selected final models and output readiness; it does not create new model fits.",
        "",
        "| Model | Final branch/source | Final status | Formal status | Figure-output status |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {final_branch_or_source} | {final_model_status} | "
            "{formal_resampling_status} | {figure_output_status} |".format(**row)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_density_cache_roots() -> list[Path]:
    return []


def build_final_reporting(
    *,
    status_csv: Path,
    worklist_csv: Path,
    readiness_csv: Path,
    direct_permutation_csv: Path,
    direct_bootstrap_csv: Path,
    direct_jitter_csv: Path,
    fiber_permutation_csv: Path,
    fiber_bootstrap_csv: Path,
    fiber_sensitivity_csv: Path,
    output_dir: Path,
    cohort_n: int = 16,
    density_cache_roots: list[Path] | None = None,
) -> dict[str, str]:
    status_rows = read_csv(Path(status_csv))
    if not status_rows:
        raise RuntimeError(f"no status rows found in {status_csv}")
    worklist_by_id = index_by_model_id(read_csv(Path(worklist_csv)))
    readiness_by_id = index_by_model_id(read_csv(Path(readiness_csv)))
    direct_permutation_by_id = index_by_model_id(read_csv(Path(direct_permutation_csv)))
    direct_bootstrap_by_id = index_by_model_id(read_csv(Path(direct_bootstrap_csv)))
    direct_jitter_by_id = index_by_model_id(read_csv(Path(direct_jitter_csv)))
    fiber_permutation_by_id = index_by_model_id(read_csv(Path(fiber_permutation_csv)))
    fiber_bootstrap_by_id = index_by_model_id(read_csv(Path(fiber_bootstrap_csv)))
    fiber_sensitivity_by_id = index_by_model_id(read_csv(Path(fiber_sensitivity_csv)))
    cache_roots = density_cache_roots if density_cache_roots is not None else default_density_cache_roots()

    report_rows: list[dict[str, str]] = []
    readiness_rows: list[dict[str, str]] = []
    for status_row in status_rows:
        model_id = status_row.get("model_id", "")
        report_row, readiness_row = build_report_row(
            status_row=status_row,
            worklist_row=worklist_by_id.get(model_id),
            readiness_row=readiness_by_id.get(model_id),
            direct_permutation_row=direct_permutation_by_id.get(model_id),
            direct_bootstrap_row=direct_bootstrap_by_id.get(model_id),
            direct_jitter_row=direct_jitter_by_id.get(model_id),
            fiber_permutation_row=fiber_permutation_by_id.get(model_id),
            fiber_bootstrap_row=fiber_bootstrap_by_id.get(model_id),
            fiber_sensitivity_row=fiber_sensitivity_by_id.get(model_id),
            density_cache_roots=cache_roots,
            cohort_n=cohort_n,
        )
        report_rows.append(report_row)
        readiness_rows.append(readiness_row)

    output_dir = Path(output_dir)
    final_report_csv = output_dir / "four_model_final_report.csv"
    final_report_md = output_dir / "four_model_final_report.md"
    figure_readiness_csv = output_dir / "four_model_figure_output_readiness.csv"
    manifest_json = output_dir / "four_model_final_reporting_manifest.json"
    report_fields = [
        "model_id",
        "model",
        "model_family",
        "analysis_family",
        "observed_branch",
        "final_branch_or_source",
        "final_model_role",
        "final_model_status",
        "formal_target_status",
        "formal_readiness_status",
        "formal_resampling_status",
        "formal_p_plus_one_two_sided",
        "permutation_status",
        "bootstrap_status",
        "finite_bootstrap_count",
        "jitter_status",
        "finite_jitter_count",
        "oss_sensitivity_status",
        "oss_missing_inputs",
        "fiber_jitter_qc_status",
        "jitter_missing_inputs",
        "jitter_input_search_roots",
        "figure_output_status",
        "n_subjects",
        "hypothesis_generating",
        "interpretation",
        "latest_manifest",
        *MANIFEST_AUDIT_FIELDS,
    ]
    readiness_fields = [
        "model_id",
        "analysis_family",
        "final_branch_or_source",
        "final_model_status",
        "direct_voxel_display_status",
        "direct_voxel_missing_display_maps",
        "fiber_density_label_cache_status",
        "fiber_density_label_cache_paths",
        "oss_sensitivity_status",
        "oss_missing_inputs",
        "fiber_jitter_qc_status",
        "jitter_missing_inputs",
        "jitter_input_search_roots",
        "formal_resampling_status",
        "figure_output_status",
        "latest_manifest",
        *MANIFEST_AUDIT_FIELDS,
    ]
    write_csv(final_report_csv, report_rows, report_fields)
    write_csv(figure_readiness_csv, readiness_rows, readiness_fields)
    write_markdown(final_report_md, report_rows, cohort_n)
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "cohort_n": cohort_n,
            "interpretation": "hypothesis_generating",
            "inputs": {
                "status_csv": str(status_csv),
                "worklist_csv": str(worklist_csv),
                "readiness_csv": str(readiness_csv),
                "direct_permutation_csv": str(direct_permutation_csv),
                "direct_bootstrap_csv": str(direct_bootstrap_csv),
                "direct_jitter_csv": str(direct_jitter_csv),
                "fiber_permutation_csv": str(fiber_permutation_csv),
                "fiber_bootstrap_csv": str(fiber_bootstrap_csv),
                "fiber_sensitivity_csv": str(fiber_sensitivity_csv),
                "density_cache_roots": [str(path) for path in cache_roots],
            },
            "n_rows": len(report_rows),
            "figure_output_counts": count_by(report_rows, "figure_output_status"),
            "outputs": {
                "final_report_csv": str(final_report_csv),
                "final_report_md": str(final_report_md),
                "figure_readiness_csv": str(figure_readiness_csv),
                "manifest_json": str(manifest_json),
            },
        },
        add_code_provenance=True,
    )
    return {
        "final_report_csv": str(final_report_csv),
        "final_report_md": str(final_report_md),
        "figure_readiness_csv": str(figure_readiness_csv),
        "manifest_json": str(manifest_json),
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def run_final_reporting(args: argparse.Namespace) -> int:
    outputs = build_final_reporting(
        status_csv=Path(args.status_csv).expanduser().resolve(),
        worklist_csv=Path(args.worklist_csv).expanduser().resolve(),
        readiness_csv=Path(args.readiness_csv).expanduser().resolve(),
        direct_permutation_csv=Path(args.direct_permutation_csv).expanduser().resolve(),
        direct_bootstrap_csv=Path(args.direct_bootstrap_csv).expanduser().resolve(),
        direct_jitter_csv=Path(args.direct_jitter_csv).expanduser().resolve(),
        fiber_permutation_csv=Path(args.fiber_permutation_csv).expanduser().resolve(),
        fiber_bootstrap_csv=Path(args.fiber_bootstrap_csv).expanduser().resolve(),
        fiber_sensitivity_csv=Path(args.fiber_sensitivity_csv).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
        cohort_n=args.cohort_n,
        density_cache_roots=[Path(path).expanduser().resolve() for path in args.density_cache_root],
    )
    print(f"Final report: {outputs['final_report_csv']}")
    print(f"Figure-output readiness: {outputs['figure_readiness_csv']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-csv",
        default=str(FORMAL_ROOT / "status/four_model_execution_status.csv"),
        help="Consolidated four-model execution status CSV.",
    )
    parser.add_argument(
        "--worklist-csv",
        default=str(FORMAL_ROOT / "formal_worklist/four_model_formal_target_worklist.csv"),
        help="Final-model formal target worklist CSV.",
    )
    parser.add_argument(
        "--readiness-csv",
        default=str(FORMAL_ROOT / "formal_readiness/four_model_formal_readiness.csv"),
        help="Final-model formal readiness CSV.",
    )
    parser.add_argument(
        "--direct-permutation-csv",
        default=str(FORMAL_ROOT / "direct_voxel_formal_permutation/direct_voxel_formal_permutation_summary.csv"),
        help="Direct-voxel formal permutation summary CSV.",
    )
    parser.add_argument(
        "--direct-bootstrap-csv",
        default=str(FORMAL_ROOT / "direct_voxel_formal_bootstrap/direct_voxel_formal_bootstrap_summary.csv"),
        help="Direct-voxel formal bootstrap summary CSV.",
    )
    parser.add_argument(
        "--direct-jitter-csv",
        default=str(FORMAL_ROOT / "direct_voxel_formal_jitter/direct_voxel_formal_jitter_summary.csv"),
        help="Direct-voxel formal jitter summary CSV.",
    )
    parser.add_argument(
        "--fiber-permutation-csv",
        default=str(FORMAL_ROOT / "normative_fiber_formal_permutation/normative_fiber_formal_permutation_summary.csv"),
        help="dTOR normative-fiber formal permutation summary CSV.",
    )
    parser.add_argument(
        "--fiber-bootstrap-csv",
        default=str(FORMAL_ROOT / "normative_fiber_formal_bootstrap/normative_fiber_formal_bootstrap_summary.csv"),
        help="dTOR normative-fiber formal bootstrap summary CSV.",
    )
    parser.add_argument(
        "--fiber-sensitivity-csv",
        default=str(FORMAL_ROOT / "normative_fiber_sensitivity_readiness/normative_fiber_sensitivity_readiness_summary.csv"),
        help="dTOR normative-fiber OSS/jitter sensitivity readiness summary CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FORMAL_ROOT / "final_reporting"),
        help="Final reporting output directory.",
    )
    parser.add_argument("--cohort-n", type=int, default=16, help="Cohort size to record in final report.")
    parser.add_argument(
        "--density-cache-root",
        action="append",
        default=[str(path) for path in default_density_cache_roots()],
        help="Root to search for existing fiber density/label caches.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_final_reporting(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
