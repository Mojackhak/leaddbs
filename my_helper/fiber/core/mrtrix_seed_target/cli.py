"""YAML-only command-line interface for seed-wide MRtrix tractography."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
from typing import Any, Sequence

from .errors import MrtrixSeedTargetError
from .pipeline import run_batch, status_batch, validate_batch
from .tools import request_stop


class _SignalInterruption(KeyboardInterrupt):
    """Carry the terminating POSIX signal through normal Python cleanup."""

    def __init__(self, signal_number: int) -> None:
        super().__init__(f"received signal {signal_number}")
        self.signal_number = int(signal_number)


def _handle_stop_signal(signal_number: int, _frame: Any) -> None:
    request_stop()
    raise _SignalInterruption(signal_number)


def build_parser() -> argparse.ArgumentParser:
    """Build the exact three-command public CLI."""

    parser = argparse.ArgumentParser(prog="mrtrix-seed-target")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate", "Resolve and validate the complete YAML batch without writes."),
        ("run", "Run or automatically resume the configured batch."),
        ("status", "Verify current subject-local results without execution."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--config", type=Path, required=True)
    return parser


def _emit(value: Any, stream) -> None:
    stream.write(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one CLI command and return its process exit code."""

    args = build_parser().parse_args(argv)
    prior_handlers: dict[int, Any] = {}
    if args.command == "run":
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            prior_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, _handle_stop_signal)
    try:
        if args.command == "validate":
            payload = validate_batch(args.config).as_mapping()
        elif args.command == "run":
            payload = run_batch(args.config)
        else:
            payload = status_batch(args.config)
    except (MrtrixSeedTargetError, OSError, ValueError) as exc:
        _emit(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            sys.stderr,
        )
        return 1
    except KeyboardInterrupt as exc:
        request_stop()
        signal_number = (
            exc.signal_number if isinstance(exc, _SignalInterruption) else signal.SIGINT
        )
        _emit(
            {
                "status": "interrupted",
                "signal": signal.Signals(signal_number).name,
            },
            sys.stderr,
        )
        return 128 + int(signal_number)
    finally:
        for signal_number, handler in prior_handlers.items():
            signal.signal(signal_number, handler)
    _emit(payload, sys.stdout)
    return 0 if payload.get("status") in {"valid", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
