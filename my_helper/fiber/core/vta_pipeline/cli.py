"""Public `vta-model` command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .errors import VtaPipelineError
from .matlab_bridge import MatlabBridge
from .planner import Selection
from .service import RunService, plan_lines, prepare_plan, status_lines


_REPO_ROOT = Path(__file__).resolve().parents[4]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except SystemExit as exc:
        return int(exc.code)
    except VtaPipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vta-model")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("validate", _handle_validate),
        ("plan", _handle_plan),
        ("run", _handle_run),
        ("status", _handle_status),
    ):
        command = commands.add_parser(name)
        _add_common_arguments(command)
        if name == "run":
            command.add_argument("--workers", type=_positive_int, default=1)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--resume", action="store_true")
            mode.add_argument("--force", action="store_true")
        command.set_defaults(handler=handler)
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--study-base", required=True)
    parser.add_argument("--vta-model", required=True)
    subjects = parser.add_mutually_exclusive_group(required=True)
    subjects.add_argument("--subject", action="append", dest="subjects")
    subjects.add_argument("--all-subjects", action="store_true")
    parser.add_argument("--phase", action="append", dest="phases")
    parser.add_argument("--program", action="append", type=int, dest="programs")
    parser.add_argument("--electrode", action="append", dest="electrodes")
    parser.add_argument(
        "--frequency-group",
        action="append",
        dest="frequency_groups",
    )


def _selection(args: argparse.Namespace) -> Selection:
    return Selection(
        subject_ids=tuple(args.subjects or ()),
        all_subjects=bool(args.all_subjects),
        phase_ids=tuple(args.phases or ()),
        program_ids=tuple(args.programs or ()),
        electrode_ids=tuple(args.electrodes or ()),
        frequency_group_ids=tuple(args.frequency_groups or ()),
    )


def _prepared(args: argparse.Namespace):
    return prepare_plan(args.study_base, args.vta_model, _selection(args))


def _handle_validate(args: argparse.Namespace) -> int:
    prepared = _prepared(args)
    print(f"valid subjects={len(prepared.subjects)} tasks={prepared.task_count}")
    return 0


def _handle_plan(args: argparse.Namespace) -> int:
    for line in plan_lines(_prepared(args)):
        print(line)
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    for line in status_lines(_prepared(args)):
        print(line)
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    prepared = _prepared(args)
    service = RunService(
        MatlabBridge(repo_root=_REPO_ROOT),
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    summary = service.run(
        prepared.subjects,
        workers=args.workers,
        resume=bool(args.resume),
        force=bool(args.force),
    )
    print(json.dumps(asdict(summary), sort_keys=True))
    return 1 if summary.failed else 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("workers must be positive")
    return parsed
