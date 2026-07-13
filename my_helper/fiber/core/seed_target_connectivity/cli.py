"""Command-line interface for generic seed-target connectivity statistics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .errors import SeedTargetConnectivityError
from . import pipeline as pipeline_module
from .pipeline import (
    inspect_run_status,
    list_run_artifacts,
    validate_batch,
)


def _add_batch_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the four-command public argument parser."""
    parser = argparse.ArgumentParser(prog="seed-target-connectivity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Resolve inputs without full connectome traversal.")
    _add_batch_config(validate_parser)

    run_parser = subparsers.add_parser("run", help="Compute statistics and publish an immutable run.")
    _add_batch_config(run_parser)

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
            report = validate_batch(args.config)
            payload = report.as_serializable_mapping()
        elif args.command == "run":
            result = pipeline_module.compute_seed_target_batch(args.config)
            payload = result.as_serializable_mapping()
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
