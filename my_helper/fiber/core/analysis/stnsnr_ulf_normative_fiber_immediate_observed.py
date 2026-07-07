#!/usr/bin/env python3
"""Observed-only D normative-fiber same-day immediate endpoint-family driver."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from stnsnr_four_model_readiness import DEFAULT_CLINICAL_ROOT
from stnsnr_hf_direct_voxel_smoke import slugify
from stnsnr_io import iso_now, write_csv, write_json
from stnsnr_ulf_direct_voxel_immediate_observed import discover_immediate_endpoint_rows
from stnsnr_ulf_normative_fiber_observed import (
    CONNECTOMES,
    ULF_NORM_FIBER_PRIMARY_COVERAGE,
    ULF_NORM_FIBER_PRIMARY_TAU,
    build_arg_parser as build_observed_arg_parser,
    main as observed_main,
)


DEFAULT_CONNECTOMES = ["ppmi", "dtor"]


def parse_connectomes(value: str) -> list[str]:
    connectomes = [item.strip() for item in str(value).split(",") if item.strip()]
    if not connectomes:
        raise ValueError("--connectomes must include at least one connectome key")
    return connectomes


def connectome_slug_for_key(connectome: str) -> str:
    if connectome not in CONNECTOMES:
        raise ValueError(f"unsupported connectome {connectome!r}; expected one of {sorted(CONNECTOMES)}")
    return str(CONNECTOMES[connectome]["slug"])


def observed_root_for_row(output_root: Path, *, connectome: str, scale_slug: str, tau: float) -> Path:
    return (
        Path(output_root)
        / connectome_slug_for_key(connectome)
        / scale_slug
        / f"peak_efield_tau{int(tau)}_observed"
    )


def immediate_outputs_exist(output_root: Path, *, connectome: str, scale_slug: str, tau: float) -> bool:
    observed_root = observed_root_for_row(output_root, connectome=connectome, scale_slug=scale_slug, tau=tau)
    required = [
        observed_root / f"ulf_peak_efield_tau{int(tau)}_no_delta_hf" / "normative_ULF_fiber_generation_manifest.json",
        observed_root
        / f"ulf_peak_efield_tau{int(tau)}_delta_hf_adjusted"
        / "normative_ULF_fiber_generation_manifest.json",
        observed_root
        / "tau_coverage_source_resolver_scan"
        / "normative_ULF_fiber_tau_coverage_source_resolver_manifest.json",
    ]
    return all(path.is_file() for path in required)


def observed_driver_argv(
    args: argparse.Namespace,
    *,
    post_scale: str,
    connectome: str,
    source_resolver_scan: bool,
) -> list[str]:
    argv = [
        "--repo-root",
        str(args.repo_root),
        "--asset-root",
        str(args.asset_root),
        "--clinical-root",
        str(args.clinical_root),
        "--readiness-root",
        str(args.readiness_root),
        "--gate-status",
        str(args.gate_status),
        "--output-root",
        str(args.output_root),
        "--hf-output-root",
        str(args.hf_output_root),
        "--matlab-bin",
        str(args.matlab_bin),
        "--post-scale",
        post_scale,
        "--connectome",
        connectome,
        "--tau",
        str(args.tau),
        "--min-coverage",
        str(args.min_coverage),
        "--fiber-chunk-size",
        str(args.fiber_chunk_size),
        "--max-fibers",
        str(args.max_fibers),
    ]
    if args.readiness_csv:
        argv.extend(["--readiness-csv", str(args.readiness_csv)])
    if args.force_flip:
        argv.append("--force-flip")
    if args.force_rebuild:
        argv.append("--force-rebuild")
    if source_resolver_scan:
        argv.append("--source-resolver-scan")
    return argv


def run_immediate_observed(args: argparse.Namespace) -> int:
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    connectomes = parse_connectomes(args.connectomes)
    endpoints = discover_immediate_endpoint_rows(clinical_root, args.min_subjects)
    if not endpoints:
        raise RuntimeError("no same-day immediate endpoint rows meet the minimum subject requirement")

    summary_rows: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if args.endpoint and endpoint.post_scale != args.endpoint:
            continue
        for connectome in connectomes:
            connectome_slug = connectome_slug_for_key(connectome)
            scale_slug = slugify(endpoint.post_scale)
            if immediate_outputs_exist(output_root, connectome=connectome, scale_slug=scale_slug, tau=args.tau):
                row_status = "existing_observed_and_source_resolver_detected"
            else:
                observed_rc = observed_main(
                    observed_driver_argv(
                        args,
                        post_scale=endpoint.post_scale,
                        connectome=connectome,
                        source_resolver_scan=False,
                    )
                )
                if observed_rc != 0:
                    raise RuntimeError(f"observed immediate run failed for {endpoint.post_scale} / {connectome}")
                scan_rc = observed_main(
                    observed_driver_argv(
                        args,
                        post_scale=endpoint.post_scale,
                        connectome=connectome,
                        source_resolver_scan=True,
                    )
                )
                if scan_rc != 0:
                    raise RuntimeError(f"source-resolver scan failed for {endpoint.post_scale} / {connectome}")
                row_status = "observed_and_source_resolver_complete"
            observed_root = observed_root_for_row(output_root, connectome=connectome, scale_slug=scale_slug, tau=args.tau)
            summary_rows.append(
                {
                    **asdict(endpoint),
                    "connectome": connectome,
                    "connectome_slug": connectome_slug,
                    "scale_slug": scale_slug,
                    "observed_root": str(observed_root),
                    "source_resolver_root": str(observed_root / "tau_coverage_source_resolver_scan"),
                    "status": row_status,
                }
            )
    if not summary_rows:
        raise RuntimeError(f"requested endpoint was not available: {args.endpoint}")

    summary_dir = output_root / "immediate_endpoint_family"
    summary_csv = summary_dir / "normative_ULF_fiber_immediate_endpoint_summary.csv"
    manifest_json = summary_dir / "normative_ULF_fiber_immediate_endpoint_manifest.json"
    write_csv(
        summary_csv,
        summary_rows,
        [
            "scale",
            "post_scale",
            "hf_reference_scale",
            "n_subjects",
            "connectome",
            "connectome_slug",
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
            "model": "ULF normative fiber same-day immediate endpoint family",
            "connectomes": connectomes,
            "n_endpoint_connectome_rows": len(summary_rows),
            "min_subjects": int(args.min_subjects),
            "resampling_status": "not_run_observed_only",
            "outputs": {"summary_csv": str(summary_csv), "manifest_json": str(manifest_json)},
        },
        add_code_provenance=True,
    )
    print(f"ULF normative fiber immediate endpoint summary: {summary_csv}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    observed_defaults = build_observed_arg_parser().parse_args([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=observed_defaults.repo_root, help="Code repo root.")
    parser.add_argument("--asset-root", default=observed_defaults.asset_root, help="Lead-DBS asset root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--readiness-root", default=observed_defaults.readiness_root, help="ULF component readiness run root.")
    parser.add_argument("--readiness-csv", default="", help="Explicit ULF component e-field availability CSV.")
    parser.add_argument("--gate-status", default=observed_defaults.gate_status, help="A/B gate status CSV.")
    parser.add_argument("--output-root", default=observed_defaults.output_root, help="ULF normative fiber output root.")
    parser.add_argument("--hf-output-root", default=observed_defaults.hf_output_root, help="Matched HF normative fiber output root.")
    parser.add_argument("--matlab-bin", default=observed_defaults.matlab_bin, help="MATLAB executable.")
    parser.add_argument("--connectomes", default=",".join(DEFAULT_CONNECTOMES), help="Comma-separated connectome keys to process.")
    parser.add_argument("--tau", type=float, default=ULF_NORM_FIBER_PRIMARY_TAU, help="Fiber inclusion threshold in V/m.")
    parser.add_argument("--min-coverage", type=int, default=ULF_NORM_FIBER_PRIMARY_COVERAGE, help="Minimum subject coverage.")
    parser.add_argument("--fiber-chunk-size", type=int, default=observed_defaults.fiber_chunk_size, help="Number of fibers per sampling chunk.")
    parser.add_argument("--max-fibers", type=int, default=observed_defaults.max_fibers, help="Development-only cap; 0 means full connectome.")
    parser.add_argument("--min-subjects", type=int, default=12, help="Minimum paired subjects for an immediate endpoint row.")
    parser.add_argument("--endpoint", default="", help="Optional exact immediate post-scale to run.")
    parser.add_argument("--force-flip", action="store_true", help="Regenerate left-to-right flipped fields.")
    parser.add_argument("--force-rebuild", action="store_true", help="Regenerate component exposure sidecars.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_immediate_observed(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
