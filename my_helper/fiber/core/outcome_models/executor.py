"""Dependency-aware execution for configured outcome-model task plans."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .catalog import CatalogStatus, EndpointRecord
from .planner import (
    DependencyRequirement,
    ExecutionPlan,
    GatePredicate,
    TaskSpec,
)
from .run_store import ConfiguredRunStore, sha256_file


class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIGURATION_ERROR = 2
    PLANNED_INPUT_FAILURE = 3
    EXECUTION_OR_NO_FINAL_FAILURE = 4
    RUN_LOOKUP_ERROR = 5


class TaskStatus(str, Enum):
    COMPLETED = "completed"
    INPUT_FAILURE = "input_failure"
    EXECUTION_FAILURE = "execution_failure"
    NO_FINAL_MODEL = "no_final_model"
    SKIPPED_DEPENDENCY = "skipped_dependency"
    SKIPPED_GATE = "skipped_gate"


@dataclass(frozen=True)
class TaskArtifact:
    kind: str
    path: Path


@dataclass(frozen=True)
class TaskResult:
    status: TaskStatus
    detail: str = ""
    facts: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[TaskArtifact, ...] = ()


class ModelService(Protocol):
    def execute(self, task: TaskSpec, context: "RunContext") -> TaskResult: ...


@dataclass(frozen=True)
class ServiceRegistry:
    by_operation: Mapping[tuple[str, str], ModelService] = field(default_factory=dict)
    by_model_family: Mapping[str, ModelService] = field(default_factory=dict)
    default: ModelService | None = None

    def resolve(self, task: TaskSpec) -> ModelService | None:
        return self.by_operation.get(
            (task.endpoint.model_family, task.key.execution_stage),
            self.by_model_family.get(task.endpoint.model_family, self.default),
        )


@dataclass
class RunContext:
    store: ConfiguredRunStore
    catalog: tuple[EndpointRecord, ...]
    config: Any | None = None
    resume: bool = False
    results: dict[str, "TaskExecutionRecord"] = field(default_factory=dict)

    def catalog_record(self, endpoint_model_id: str) -> EndpointRecord:
        matches = [row for row in self.catalog if row.endpoint_model_id == endpoint_model_id]
        if len(matches) != 1:
            raise RuntimeError(f"expected one catalog row for {endpoint_model_id}; found {len(matches)}")
        return matches[0]

    def dependency_facts(self, task: TaskSpec, execution_stage: str) -> Mapping[str, Any]:
        matches = [
            self.results[item.task_id].result.facts
            for item in task.dependencies
            if item.task_id in self.results
            and self.results[item.task_id].task.key.execution_stage == execution_stage
        ]
        if len(matches) != 1:
            return {}
        return matches[0]

    def matched_hf_source_accepted(self, task: TaskSpec) -> bool:
        expected_family = "hf_voxel" if task.endpoint.model_family == "ulf_voxel" else "hf_fiber"
        for record in self.results.values():
            if (
                record.task.endpoint.study_id == task.endpoint.study_id
                and record.task.endpoint.scale_id == task.endpoint.scale_id
                and record.task.endpoint.model_family == expected_family
                and record.task.endpoint.connectome == task.endpoint.connectome
                and record.task.key.execution_stage == "observed_source_resolver"
            ):
                return bool(record.result.facts.get("source_accepted", False))
        return False

    def final_model_realized(self, task: TaskSpec) -> bool:
        for record in self.results.values():
            if record.task.endpoint.identifier != task.endpoint.identifier:
                continue
            if record.task.key.execution_stage == "final_model_realization":
                return bool(record.result.facts.get("final_model_realized", False))
            if record.task.key.execution_stage == "observed_source_resolver" and task.endpoint.model_family.startswith("hf_"):
                return bool(record.result.facts.get("source_accepted", False))
        return False


@dataclass(frozen=True)
class TaskExecutionRecord:
    task: TaskSpec
    result: TaskResult
    reused: bool = False
    started_at: str = ""
    finished_at: str = ""

    def status_row(self) -> dict[str, str]:
        final_model_id = str(self.result.facts.get("final_model_id", ""))
        return {
            "task_id": self.task.task_id,
            "endpoint_model_id": self.task.endpoint.identifier,
            "status": self.result.status.value,
            "detail": self.result.detail,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dependency_ids": json.dumps([item.task_id for item in self.task.dependencies], separators=(",", ":")),
            "final_model_id": final_model_id,
        }


@dataclass(frozen=True)
class RunResult:
    exit_code: ExitCode
    tasks: tuple[TaskExecutionRecord, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dependency_satisfied(requirement: DependencyRequirement, result: TaskResult) -> bool:
    if requirement == DependencyRequirement.TERMINAL:
        return True
    if requirement == DependencyRequirement.SUCCESS:
        return result.status == TaskStatus.COMPLETED
    if requirement == DependencyRequirement.ACCEPTED_FINAL:
        return result.status == TaskStatus.COMPLETED and bool(
            result.facts.get("source_accepted") or result.facts.get("final_model_realized")
        )
    if requirement == DependencyRequirement.FORMAL_COMPLETE:
        return result.status == TaskStatus.COMPLETED and bool(result.facts.get("formal_complete", False))
    raise RuntimeError(f"unsupported dependency requirement {requirement}")


def _gate_open(task: TaskSpec, context: RunContext) -> bool:
    predicate = task.gate.predicate
    if predicate == GatePredicate.ALWAYS:
        return True
    if predicate == GatePredicate.ENDPOINT_DATA_AVAILABLE:
        return context.catalog_record(task.endpoint.identifier).status == CatalogStatus.DATA_AVAILABLE
    if predicate == GatePredicate.BRANCH_INTENDED_OR_COMPARISON:
        return context.catalog_record(task.endpoint.identifier).status == CatalogStatus.DATA_AVAILABLE
    if predicate == GatePredicate.DELTA_HFSCORE_INPUTS_VALID:
        facts = context.dependency_facts(task, "preprocessing_sidecars")
        return context.matched_hf_source_accepted(task) and bool(facts.get("delta_hfscore_inputs_valid", False))
    if predicate == GatePredicate.FINAL_MODEL_REALIZED:
        return context.final_model_realized(task)
    raise RuntimeError(f"unsupported gate predicate {predicate}")


def _resume_artifacts(task: TaskSpec, context: RunContext) -> tuple[TaskArtifact, ...] | None:
    rows = [
        row
        for row in context.store.load_artifact_index()
        if row["task_id"] == task.task_id and row["kind"] != "task_manifest"
    ]
    by_kind: dict[str, TaskArtifact] = {}
    for row in rows:
        kind = str(row["kind"])
        if kind in by_kind:
            return None
        path = (context.store.run_root / row["relative_path"]).resolve()
        try:
            path.relative_to(context.store.run_root)
        except ValueError:
            return None
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            return None
        by_kind[kind] = TaskArtifact(kind, path)
    expected = tuple(
        kind for kind in task.expected_artifact_kinds if kind != "task_manifest"
    )
    if any(kind not in by_kind for kind in expected):
        return None
    ordered = [by_kind.pop(kind) for kind in expected]
    ordered.extend(by_kind[kind] for kind in sorted(by_kind))
    return tuple(ordered)


def _resume_record(task: TaskSpec, context: RunContext) -> TaskExecutionRecord | None:
    if not context.resume:
        return None
    manifest = context.store.load_task_manifest(task.task_id)
    if manifest is None or manifest.get("status") != TaskStatus.COMPLETED.value:
        return None
    artifacts = _resume_artifacts(task, context)
    if artifacts is None:
        return None
    result = TaskResult(
        status=TaskStatus.COMPLETED,
        detail=str(manifest.get("detail", "")),
        facts=dict(manifest.get("facts", {})),
        artifacts=artifacts,
    )
    return TaskExecutionRecord(
        task=task,
        result=result,
        reused=True,
        started_at=str(manifest.get("started_at", "")),
        finished_at=str(manifest.get("finished_at", "")),
    )


def _persist_record(record: TaskExecutionRecord, context: RunContext) -> None:
    manifest_path = context.store.write_task_manifest(
        task_id=record.task.task_id,
        manifest={
            "task": record.task.as_dict(),
            "status": record.result.status.value,
            "detail": record.result.detail,
            "facts": dict(record.result.facts),
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "reused": record.reused,
        },
    )
    context.store.record_artifact(task_id=record.task.task_id, kind="task_manifest", path=manifest_path)
    for artifact in record.result.artifacts:
        context.store.record_artifact(task_id=record.task.task_id, kind=artifact.kind, path=artifact.path)


def _exit_code(records: Sequence[TaskExecutionRecord]) -> ExitCode:
    statuses = {record.result.status for record in records}
    if statuses & {TaskStatus.EXECUTION_FAILURE, TaskStatus.NO_FINAL_MODEL}:
        return ExitCode.EXECUTION_OR_NO_FINAL_FAILURE
    if TaskStatus.INPUT_FAILURE in statuses:
        return ExitCode.PLANNED_INPUT_FAILURE
    return ExitCode.SUCCESS


def _validate_service_result(task: TaskSpec, result: TaskResult, context: RunContext) -> TaskResult:
    if result.status != TaskStatus.COMPLETED:
        return result
    expected = set(task.expected_artifact_kinds) - {"task_manifest"}
    by_kind = {artifact.kind: artifact for artifact in result.artifacts}
    missing = sorted(expected - set(by_kind))
    invalid: list[str] = []
    for kind, artifact in by_kind.items():
        path = Path(artifact.path).expanduser().resolve()
        try:
            path.relative_to(context.store.run_root)
        except ValueError:
            invalid.append(f"{kind}:outside_run_root")
            continue
        if not path.is_file():
            invalid.append(f"{kind}:missing_file")
    if not missing and not invalid:
        return result
    details = []
    if missing:
        details.append("missing_expected_artifacts:" + ",".join(missing))
    if invalid:
        details.append("invalid_artifacts:" + ",".join(sorted(invalid)))
    return TaskResult(TaskStatus.EXECUTION_FAILURE, ";".join(details))


def execute_plan(
    plan: ExecutionPlan,
    context: RunContext,
    services: ServiceRegistry,
) -> RunResult:
    """Execute every planned task to one terminal state without cross-endpoint cancellation."""
    if context.resume:
        context.store.recover_interrupted_tasks()
    records: list[TaskExecutionRecord] = []
    for task in plan.tasks:
        reused = _resume_record(task, context)
        if reused is not None:
            record = reused
        else:
            started_at = _utc_now()
            unsatisfied = [
                dependency
                for dependency in task.dependencies
                if dependency.task_id not in context.results
                or not _dependency_satisfied(
                    dependency.requirement,
                    context.results[dependency.task_id].result,
                )
            ]
            if unsatisfied:
                detail = "unsatisfied_dependencies:" + ",".join(item.task_id for item in unsatisfied)
                result = TaskResult(TaskStatus.SKIPPED_DEPENDENCY, detail)
            elif not _gate_open(task, context):
                result = TaskResult(TaskStatus.SKIPPED_GATE, f"gate_closed:{task.gate.predicate.value}")
            else:
                service = services.resolve(task)
                if service is None:
                    result = TaskResult(TaskStatus.EXECUTION_FAILURE, "no_registered_model_service")
                else:
                    try:
                        result = service.execute(task, context)
                    except Exception as exc:
                        result = TaskResult(TaskStatus.EXECUTION_FAILURE, f"service_exception:{exc}")
                    if not isinstance(result, TaskResult):
                        result = TaskResult(TaskStatus.EXECUTION_FAILURE, "service_returned_invalid_result")
                    else:
                        result = _validate_service_result(task, result, context)
            record = TaskExecutionRecord(
                task=task,
                result=result,
                started_at=started_at,
                finished_at=_utc_now(),
            )
            _persist_record(record, context)
        context.results[task.task_id] = record
        records.append(record)
        context.store.write_task_statuses([item.status_row() for item in records])

    exit_code = _exit_code(records)
    context.store.update_run_manifest(
        {
            "status": "completed" if exit_code == ExitCode.SUCCESS else "completed_with_failures",
            "exit_code": int(exit_code),
            "finished_at": _utc_now(),
            "task_count": len(records),
        }
    )
    return RunResult(exit_code=exit_code, tasks=tuple(records))
