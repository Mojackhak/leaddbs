"""Argument parsing for the public dual-frequency workflow CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ..config import WorkflowOverrides
from ..workflow import ExecutionError, RunStoreError
from .publication import CanonicalPublisher, PublicationError
from .service import (
    ApplicationError,
    SensitivityExtensionRequest,
    WorkflowRequest,
    WorkflowService,
)


def _workflow_arguments(parser: argparse.ArgumentParser, *, run: bool) -> None:
    parser.add_argument("--study-base", type=Path, required=True)
    parser.add_argument("--direct-voxel-model", type=Path, required=True)
    parser.add_argument("--normative-fiber-model", type=Path, required=True)
    parser.add_argument("--workflow-profile", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--scale", action="append", default=[])
    selection.add_argument("--all-available", action="store_true")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        choices=("reference_voxel", "reference_fiber", "addon_voxel", "addon_fiber"),
    )
    parser.add_argument("--connectome", action="append", default=[])
    parser.add_argument(
        "--through",
        choices=("observed", "formal", "sensitivity", "report"),
    )
    parser.add_argument("--workers", type=int)
    parser.add_argument(
        "--allow-expensive-producers",
        action="store_true",
        default=None,
    )
    if run:
        parser.add_argument("--run-id")
        parser.add_argument("--resume", action="store_true", default=None)
        parser.add_argument("--force", action="store_true", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_dual_frequency_models",
        description="Validate, plan, and execute generic dual-frequency outcome models.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _workflow_arguments(subparsers.add_parser("validate"), run=False)
    _workflow_arguments(subparsers.add_parser("plan"), run=False)
    _workflow_arguments(subparsers.add_parser("run"), run=True)
    sensitivity = subparsers.add_parser("sensitivity")
    sensitivity.add_argument("--base-run", type=Path, required=True)
    sensitivity.add_argument("--analyses", required=True)
    sensitivity.add_argument("--run-id", required=True)
    sensitivity.add_argument("--workers", type=int, default=3)
    sensitivity.add_argument(
        "--allow-expensive-producers",
        action="store_true",
        default=False,
    )
    sensitivity_existing = sensitivity.add_mutually_exclusive_group()
    sensitivity_existing.add_argument(
        "--resume",
        action="store_true",
        default=False,
    )
    sensitivity_existing.add_argument(
        "--force",
        action="store_true",
        default=False,
    )
    sensitivity.add_argument("--rebuild", action="store_true", default=False)
    sensitivity.add_argument("--rebuild-run-id")
    sensitivity.add_argument("--study-base", type=Path)
    sensitivity.add_argument("--direct-voxel-model", type=Path)
    sensitivity.add_argument("--normative-fiber-model", type=Path)
    sensitivity.add_argument("--workflow-profile", type=Path)
    sensitivity_selection = sensitivity.add_mutually_exclusive_group()
    sensitivity_selection.add_argument("--scale", action="append", default=[])
    sensitivity_selection.add_argument("--all-available", action="store_true")
    sensitivity.add_argument(
        "--model",
        action="append",
        default=[],
        choices=("reference_voxel", "reference_fiber", "addon_voxel", "addon_fiber"),
    )
    sensitivity.add_argument("--connectome", action="append", default=[])
    for command in ("status", "artifacts"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--run-root", type=Path, required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--run-root", type=Path, required=True)
    publish.add_argument("--output-root", type=Path)
    publish_extension = subparsers.add_parser("publish-extension")
    publish_extension.add_argument("--run-root", type=Path, required=True)
    publish_extension.add_argument("--extension-id")
    publish_extension.add_argument("--output-root", type=Path)
    publish_extension.add_argument("--scale", action="append", default=[])
    return parser


def _request(arguments: argparse.Namespace) -> WorkflowRequest:
    overrides = WorkflowOverrides(
        scales=tuple(arguments.scale),
        all_available=arguments.all_available,
        models=tuple(arguments.model),
        connectomes=tuple(arguments.connectome),
        through=arguments.through,
        resume=getattr(arguments, "resume", None),
        force=getattr(arguments, "force", None),
        allow_expensive_producers=arguments.allow_expensive_producers,
        workers=arguments.workers,
    )
    return WorkflowRequest(
        study_base=arguments.study_base,
        direct_voxel_model=arguments.direct_voxel_model,
        normative_fiber_model=arguments.normative_fiber_model,
        workflow_profile=arguments.workflow_profile,
        overrides=overrides,
    )


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    service: WorkflowService | None = None,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    workflow_service = service or WorkflowService()
    try:
        if arguments.command == "validate":
            _print_json(workflow_service.validate(_request(arguments)).as_dict())
            return 0
        if arguments.command == "plan":
            _print_json(workflow_service.plan(_request(arguments)).as_dict())
            return 0
        if arguments.command == "run":
            result = workflow_service.run(_request(arguments), run_id=arguments.run_id)
            _print_json(
                {
                    "run_id": result.run_id,
                    "exit_code": result.exit_code,
                    "failed_task_ids": list(result.failed_task_ids),
                    "failed_endpoint_ids": list(result.failed_endpoint_ids),
                }
            )
            return result.exit_code
        if arguments.command == "sensitivity":
            analyses = tuple(
                item.strip()
                for item in str(arguments.analyses).split(",")
                if item.strip()
            )
            rebuild_request = None
            if arguments.rebuild:
                rebuild_paths = (
                    arguments.study_base,
                    arguments.direct_voxel_model,
                    arguments.normative_fiber_model,
                    arguments.workflow_profile,
                )
                if any(path is None for path in rebuild_paths):
                    raise ApplicationError(
                        "rebuild requires study-base and all three workflow profiles; "
                        "run the project converter first if study_base.json was deleted"
                    )
                if not Path(arguments.study_base).expanduser().is_file():
                    raise ApplicationError(
                        "study_base.json is missing; run the explicit project-owned "
                        "upstream converter before generic rebuild"
                    )
                if not arguments.all_available and not arguments.scale:
                    raise ApplicationError("rebuild requires --scale or --all-available")
                rebuild_request = WorkflowRequest(
                    study_base=arguments.study_base,
                    direct_voxel_model=arguments.direct_voxel_model,
                    normative_fiber_model=arguments.normative_fiber_model,
                    workflow_profile=arguments.workflow_profile,
                    overrides=WorkflowOverrides(
                        scales=tuple(arguments.scale),
                        all_available=arguments.all_available,
                        models=tuple(arguments.model),
                        connectomes=tuple(arguments.connectome),
                        through="observed",
                        workers=arguments.workers,
                    ),
                )
            result = workflow_service.sensitivity(
                SensitivityExtensionRequest(
                    base_run=arguments.base_run,
                    analyses=analyses,
                    run_id=arguments.run_id,
                    workers=arguments.workers,
                    allow_expensive_producers=arguments.allow_expensive_producers,
                    resume=arguments.resume,
                    force=arguments.force,
                    rebuild_request=rebuild_request,
                    rebuild_run_id=arguments.rebuild_run_id,
                )
            )
            _print_json(
                {
                    "run_id": result.run_id,
                    "exit_code": result.exit_code,
                    "failed_task_ids": list(result.failed_task_ids),
                    "failed_endpoint_ids": list(result.failed_endpoint_ids),
                }
            )
            return result.exit_code
        if arguments.command == "status":
            _print_json(workflow_service.status(arguments.run_root))
            return 0
        if arguments.command == "artifacts":
            _print_json(workflow_service.artifacts(arguments.run_root))
            return 0
        if arguments.command == "publish":
            _print_json(
                CanonicalPublisher()
                .publish(
                    arguments.run_root,
                    output_root_override=arguments.output_root,
                )
                .as_dict()
            )
            return 0
        if arguments.command == "publish-extension":
            _print_json(
                CanonicalPublisher()
                .publish_extension(
                    arguments.run_root,
                    extension_id=arguments.extension_id,
                    output_root_override=arguments.output_root,
                    selected_scales=tuple(arguments.scale),
                )
                .as_dict()
            )
            return 0
        raise ApplicationError(f"unsupported command {arguments.command!r}")
    except (ApplicationError, ExecutionError, PublicationError, RunStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
