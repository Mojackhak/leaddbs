"""YAML-only command line interface for target-profile QC."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .errors import TargetProfileQcError
from .pipeline import run_qc, status_qc, validate_qc


def build_parser() -> argparse.ArgumentParser:
    """Build the exact three-command public parser."""

    parser = argparse.ArgumentParser(prog="mrtrix-target-profile-qc")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate", "Validate exact tracking identities without writes."),
        ("run", "Run or reuse the configured target-profile QC."),
        ("status", "Verify the current QC output without mutation."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--config", type=Path, required=True)
    return parser


def _emit(value: Any, stream) -> None:
    stream.write(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one CLI command and return a process exit code."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            payload = validate_qc(args.config).as_mapping()
        elif args.command == "run":
            payload = run_qc(args.config)
        else:
            payload = status_qc(args.config)
    except (TargetProfileQcError, OSError, ValueError) as exc:
        _emit(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            sys.stderr,
        )
        return 1
    _emit(payload, sys.stdout)
    return 0 if payload.get("status") in {"valid", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

