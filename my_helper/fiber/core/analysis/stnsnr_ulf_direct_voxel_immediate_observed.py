#!/usr/bin/env python3
"""Observed-only C direct-voxel same-day immediate endpoint-family driver."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from stnsnr_four_model_readiness import DEFAULT_CLINICAL_ROOT, RAW_CLINICAL_FILE
from stnsnr_hf_direct_voxel_smoke import slugify
from stnsnr_run_provenance import git_provenance
from stnsnr_ulf_direct_voxel_observed import (
    DEFAULT_GATE_STATUS,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_READINESS_ROOT,
    ULF_DIRECT_CANDIDATE_THRESHOLD,
    build_arg_parser as build_observed_arg_parser,
    main as observed_main,
)


@dataclass(frozen=True)
class ImmediateEndpointRow:
    scale: str
    post_scale: str
    hf_reference_scale: str
    n_subjects: int


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def discover_immediate_endpoint_rows(clinical_root: Path, min_subjects: int) -> list[ImmediateEndpointRow]:
    raw_path = Path(clinical_root) / RAW_CLINICAL_FILE
    raw_df = pd.read_excel(raw_path)
    immediate = raw_df[
        raw_df["Protocol"].astype(str).eq("STN+SNr")
        & raw_df["Phase"].astype(str).eq("immediate")
        & raw_df["Value"].notna()
    ].copy()
    endpoints: list[ImmediateEndpointRow] = []
    for scale, post_rows in immediate.groupby("Scale", sort=True):
        hf_rows = raw_df[
            raw_df["Scale"].astype(str).eq(str(scale))
            & raw_df["Protocol"].astype(str).eq("STN")
            & raw_df["Phase"].astype(str).eq("3m")
            & raw_df["Value"].notna()
        ].copy()
        paired_subjects = set(post_rows["ID"].astype(str)) & set(hf_rows["ID"].astype(str))
        if len(paired_subjects) < int(min_subjects):
            continue
        endpoints.append(
            ImmediateEndpointRow(
                scale=str(scale),
                post_scale=f"{scale} (STN+SNr, immediate)",
                hf_reference_scale=f"{scale} (STN, 3 m)",
                n_subjects=len(paired_subjects),
            )
        )
    return endpoints


def observed_driver_argv(args: argparse.Namespace, post_scale: str, source_resolver_scan: bool) -> list[str]:
    argv = [
        "--repo-root",
        str(args.repo_root),
        "--asset-root",
        str(args.asset_root),
        "--clinical-root",
        str(args.clinical_root),
        "--leaddbs-derivatives",
        str(args.leaddbs_derivatives),
        "--readiness-root",
        str(args.readiness_root),
        "--gate-status",
        str(args.gate_status),
        "--output-root",
        str(args.output_root),
        "--matlab-bin",
        str(args.matlab_bin),
        "--post-scale",
        post_scale,
        "--tau",
        str(args.tau),
        "--candidate-threshold",
        str(args.candidate_threshold),
        "--min-coverage",
        str(args.min_coverage),
        "--hf-tau",
        str(args.hf_tau),
        "--hf-min-coverage",
        str(args.hf_min_coverage),
    ]
    if args.readiness_csv:
        argv.extend(["--readiness-csv", str(args.readiness_csv)])
    if args.force_flip:
        argv.append("--force-flip")
    if source_resolver_scan:
        argv.append("--source-resolver-scan")
    return argv


def run_immediate_observed(args: argparse.Namespace) -> int:
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    endpoints = discover_immediate_endpoint_rows(clinical_root, args.min_subjects)
    if not endpoints:
        raise RuntimeError("no same-day immediate endpoint rows meet the minimum subject requirement")
    summary_rows: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if args.endpoint and endpoint.post_scale != args.endpoint:
            continue
        observed_rc = observed_main(observed_driver_argv(args, endpoint.post_scale, source_resolver_scan=False))
        if observed_rc != 0:
            raise RuntimeError(f"observed immediate run failed for {endpoint.post_scale}")
        scan_rc = observed_main(observed_driver_argv(args, endpoint.post_scale, source_resolver_scan=True))
        if scan_rc != 0:
            raise RuntimeError(f"source-resolver scan failed for {endpoint.post_scale}")
        scale_slug = slugify(endpoint.post_scale)
        summary_rows.append(
            {
                **asdict(endpoint),
                "scale_slug": scale_slug,
                "observed_root": str(output_root / scale_slug / f"tau{int(args.tau)}"),
                "source_resolver_root": str(output_root / scale_slug / "tau_coverage_source_resolver_scan"),
                "status": "observed_and_source_resolver_complete",
            }
        )
    if not summary_rows:
        raise RuntimeError(f"requested endpoint was not available: {args.endpoint}")
    summary_dir = output_root / "immediate_endpoint_family"
    summary_csv = summary_dir / "direct_voxel_ULF_only_immediate_endpoint_summary.csv"
    manifest_json = summary_dir / "direct_voxel_ULF_only_immediate_endpoint_manifest.json"
    write_csv(
        summary_csv,
        summary_rows,
        [
            "scale",
            "post_scale",
            "hf_reference_scale",
            "n_subjects",
            "scale_slug",
            "observed_root",
            "source_resolver_root",
            "status",
        ],
    )
    write_json(
        manifest_json,
        {
            "generated_at": iso_now(),
            "model": "ULF direct voxel same-day immediate endpoint family",
            "n_endpoint_rows": len(summary_rows),
            "min_subjects": int(args.min_subjects),
            "resampling_status": "not_run_observed_only",
            "code_provenance": git_provenance(),
            "outputs": {"summary_csv": str(summary_csv), "manifest_json": str(manifest_json)},
        },
    )
    print(f"ULF direct voxel immediate endpoint summary: {summary_csv}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    observed_defaults = build_observed_arg_parser().parse_args([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=observed_defaults.repo_root, help="Code repo root.")
    parser.add_argument("--asset-root", default=observed_defaults.asset_root, help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=observed_defaults.leaddbs_derivatives, help="Lead-DBS derivatives directory.")
    parser.add_argument("--readiness-root", default=str(DEFAULT_READINESS_ROOT), help="ULF component readiness run root.")
    parser.add_argument("--readiness-csv", default="", help="Explicit ULF component e-field availability CSV.")
    parser.add_argument("--gate-status", default=str(DEFAULT_GATE_STATUS), help="A/B gate status CSV.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="ULF direct voxel output root.")
    parser.add_argument("--matlab-bin", default=observed_defaults.matlab_bin, help="MATLAB executable.")
    parser.add_argument("--tau", type=float, default=observed_defaults.tau, help="ULF activity and coverage threshold in V/m.")
    parser.add_argument("--candidate-threshold", type=float, default=ULF_DIRECT_CANDIDATE_THRESHOLD, help="Sparse ULF candidate threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=observed_defaults.min_coverage, help="Minimum ULF-only subject coverage.")
    parser.add_argument("--hf-tau", type=float, default=observed_defaults.hf_tau, help="Matched HF map threshold in V/m for DeltaHFScore.")
    parser.add_argument("--hf-min-coverage", type=int, default=observed_defaults.hf_min_coverage, help="Matched HF map minimum coverage for DeltaHFScore.")
    parser.add_argument("--min-subjects", type=int, default=12, help="Minimum paired subjects for an immediate endpoint row.")
    parser.add_argument("--endpoint", default="", help="Optional exact immediate post-scale to run.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_immediate_observed(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
