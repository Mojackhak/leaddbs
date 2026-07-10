"""Command-line interface for generic seed-target connectivity statistics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .errors import SeedTargetConnectivityError
from .pipeline import (
    compute_seed_target_statistics,
    inspect_run_status,
    list_run_artifacts,
    validate_inputs,
)


def _add_scientific_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-atlas-root", type=Path, required=True)
    parser.add_argument("--seed-roi", type=Path, required=True)
    parser.add_argument("--connectome", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the four-command public argument parser."""
    parser = argparse.ArgumentParser(prog="seed-target-connectivity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Resolve inputs without full connectome traversal.")
    _add_scientific_inputs(validate_parser)

    run_parser = subparsers.add_parser("run", help="Compute statistics and publish an immutable run.")
    _add_scientific_inputs(run_parser)
    run_parser.add_argument("--output-root", type=Path, required=True)
    run_parser.add_argument("--cache-root", type=Path)

    status_parser = subparsers.add_parser("status", help="Verify one immutable run.")
    status_parser.add_argument("--run-dir", type=Path, required=True)

    artifacts_parser = subparsers.add_parser("artifacts", help="List verified run artifacts.")
    artifacts_parser.add_argument("--run-dir", type=Path, required=True)
    return parser


def _emit(value: Any, stream) -> None:
    stream.write(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            report = validate_inputs(
                target_atlas_root=args.target_atlas_root,
                seed_roi=args.seed_roi,
                connectome=args.connectome,
                config=args.config,
            )
            payload = report.as_serializable_mapping()
        elif args.command == "run":
            result = compute_seed_target_statistics(
                target_atlas_root=args.target_atlas_root,
                seed_roi=args.seed_roi,
                connectome=args.connectome,
                config=args.config,
                output_root=args.output_root,
                cache_root=args.cache_root,
            )
            payload = {
                "status": "complete",
                "run_dir": str(result.artifacts.run_dir),
                "run_fingerprint": result.artifacts.run_fingerprint,
                "reused": result.artifacts.reused,
                "n_targets": len(result.statistics),
                "n_seed_fibers": int(result.membership.seed_fiber_ids.size),
            }
        elif args.command == "status":
            payload = inspect_run_status(args.run_dir)
        else:
            payload = {"status": "complete", "artifacts": list(list_run_artifacts(args.run_dir))}
    except (SeedTargetConnectivityError, OSError) as exc:
        _emit(
            {"status": "error", "error_type": type(exc).__name__, "error": str(exc)},
            sys.stderr,
        )
        return 1
    _emit(payload, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
