"""Public CLI for configured endpoint-aware outcome-model workflows."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .catalog import CatalogStatus, build_endpoint_catalog
from .config import ConfigurationError, ResolvedWorkflow, WorkflowOverrides, load_resolved_workflow
from .executor import ExitCode, RunContext, ServiceRegistry, execute_plan
from .planner import compile_execution_plan
from .run_store import ConfiguredRunStore, RunIdentityMismatch, RunStoreError, sha256_file


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def resolved_workflow_payload(config: ResolvedWorkflow) -> dict[str, Any]:
    return {
        "study": _plain(config.study),
        "scales": _plain(config.scales),
        "model": _plain(config.model),
        "workflow": _plain(config.workflow),
        "configuration_hash": config.configuration_hash,
        "source_paths": [str(path) for path in config.source_paths],
    }


def _split_values(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    output: list[str] = []
    for value in values:
        output.extend(item.strip() for item in value.split(",") if item.strip())
    return tuple(output)


def _overrides(args: argparse.Namespace) -> WorkflowOverrides:
    return WorkflowOverrides(
        scales=tuple(args.scale or ()),
        all_available=bool(args.all_available),
        models=_split_values(args.models),
        phases=_split_values(args.phases),
        connectomes=_split_values(args.connectomes),
        through=args.through,
        # Resume and force control run lineage; they do not change model identity.
        resume=None,
        force=None,
    )


def _add_configured_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--scale", action="append")
    selection.add_argument("--all-available", action="store_true")
    parser.add_argument("--models", action="append")
    parser.add_argument("--phases", action="append")
    parser.add_argument("--connectomes", action="append")
    parser.add_argument("--through", choices=("observed", "formal", "sensitivity", "report"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_configured_outcome_models.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "plan"):
        _add_configured_arguments(subparsers.add_parser(name))
    run = subparsers.add_parser("run")
    _add_configured_arguments(run)
    run.add_argument("--dry-run", action="store_true")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--force", action="store_true")
    run.add_argument("--run-id")
    for name in ("status", "artifacts"):
        lookup = subparsers.add_parser(name)
        lookup.add_argument("--output-root", type=Path, required=True)
        lookup.add_argument("--run-id", required=True)
    return parser


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _find_run_root(output_root: Path, run_id: str) -> Path:
    base = Path(output_root).expanduser().resolve() / "configured_model_runs"
    matches = [path for path in base.glob(f"*/{run_id}") if path.is_dir()]
    if len(matches) != 1:
        raise RunStoreError(f"expected exactly one run {run_id!r} under {base}; found {len(matches)}")
    return matches[0]


def _file_hash(path: Path) -> str:
    return sha256_file(path) if path.is_file() else "missing"


def _code_provenance(workspace: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=workspace,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
        dirty = True
    return {
        "commit": commit,
        "dirty": dirty,
        "environment": os.environ.get("CONDA_DEFAULT_ENV", "unknown"),
        "python": os.sys.version.split()[0],
    }


def _provenance(config: ResolvedWorkflow) -> dict[str, Any]:
    workspace = Path(__file__).resolve().parents[4]
    input_hashes = {
        "clinical_table": _file_hash(config.study.paths.clinical_table),
        "stimulation_table": _file_hash(config.study.paths.stimulation_table),
        "reference_image": _file_hash(Path(config.study.space["reference_image"])),
        "brainmask": _file_hash(Path(config.study.space["brainmask"])),
    }
    input_hashes.update(
        {f"profile_{index}": _file_hash(path) for index, path in enumerate(config.source_paths)}
    )
    input_hashes.update(
        {f"connectome_{key}": _file_hash(value.path) for key, value in config.study.connectomes.items()}
    )
    return {
        "configuration_hash": config.configuration_hash,
        "input_hashes": input_hashes,
        "code_provenance": _code_provenance(workspace),
    }


def _load_plan(args: argparse.Namespace):
    config = load_resolved_workflow(args.config, _overrides(args))
    catalog = build_endpoint_catalog(config)
    plan = compile_execution_plan(config, catalog)
    return config, catalog, plan


def _planned_exit(catalog) -> ExitCode:
    return (
        ExitCode.PLANNED_INPUT_FAILURE
        if any(row.status == CatalogStatus.INPUT_FAILURE for row in catalog)
        else ExitCode.SUCCESS
    )


def _run_lookup(args: argparse.Namespace) -> ExitCode:
    run_root = _find_run_root(args.output_root, args.run_id)
    if args.command == "status":
        payload = {
            "run_id": args.run_id,
            "run_root": str(run_root),
            "manifest": json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8")),
            "tasks": _read_csv(run_root / "task_status.csv"),
        }
    else:
        payload = {
            "run_id": args.run_id,
            "run_root": str(run_root),
            "artifacts": _read_csv(run_root / "artifact_index.csv"),
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return ExitCode.SUCCESS


def main(
    argv: Sequence[str] | None = None,
    *,
    service_registry: ServiceRegistry | None = None,
    now: datetime | None = None,
) -> ExitCode:
    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
        if args.command in {"status", "artifacts"}:
            return _run_lookup(args)
        if args.command == "run" and args.resume and not args.run_id:
            parser.error("run --resume requires --run-id")
        if args.command == "run" and args.run_id and not (args.resume or args.force):
            parser.error("run --run-id requires --resume or --force")

        config, catalog, plan = _load_plan(args)
        if args.command == "validate":
            payload = {
                "configuration_hash": config.configuration_hash,
                "endpoint_count": len(catalog),
                "input_failures": sum(row.status == CatalogStatus.INPUT_FAILURE for row in catalog),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return _planned_exit(catalog)
        if args.command == "plan" or args.dry_run:
            print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
            return _planned_exit(catalog)

        provenance = _provenance(config)
        output_root = config.study.paths.output_root
        if args.resume:
            store = ConfiguredRunStore.resume(
                output_root=output_root,
                study_id=config.study.study_id,
                run_id=args.run_id,
                expected_provenance=provenance,
            )
            resume = True
        else:
            store = ConfiguredRunStore.create(
                output_root=output_root,
                study_id=config.study.study_id,
                provenance=provenance,
                started_at=now or datetime.now(timezone.utc),
                supersedes_run_id=args.run_id if args.force else None,
            )
            store.initialize(
                resolved_workflow=resolved_workflow_payload(config),
                endpoint_catalog=[row.as_dict() for row in catalog],
                execution_plan=plan.as_dict(),
            )
            resume = False
        context = RunContext(store=store, catalog=tuple(catalog), config=config, resume=resume)
        if service_registry is None:
            from .services.default_registry import build_default_service_registry

            service_registry = build_default_service_registry(context)
        result = execute_plan(plan, context, service_registry)
        print(
            json.dumps(
                {
                    "run_id": store.run_id,
                    "run_root": str(store.run_root),
                    "exit_code": int(result.exit_code),
                    "task_count": len(result.tasks),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return result.exit_code
    except SystemExit as exc:
        return ExitCode.SUCCESS if int(exc.code or 0) == 0 else ExitCode.CONFIGURATION_ERROR
    except ConfigurationError as exc:
        parser._print_message(f"configuration error: {exc}\n", os.sys.stderr)
        return ExitCode.CONFIGURATION_ERROR
    except (RunIdentityMismatch, RunStoreError, FileNotFoundError, json.JSONDecodeError) as exc:
        parser._print_message(f"run lookup error: {exc}\n", os.sys.stderr)
        return ExitCode.RUN_LOOKUP_ERROR


if __name__ == "__main__":
    raise SystemExit(int(main()))
