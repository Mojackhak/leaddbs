"""Final-identity-locked reporting request contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from ..executor import (
    RunContext,
    TaskArtifact,
    TaskResult,
    TaskStatus,
)
from ..planner import DependencyRequirement, TaskSpec
from ..records import ArtifactRef, FinalArtifactRecord, RecordError
from ..run_store import sha256_file


@dataclass(frozen=True)
class FinalLinkedArtifact:
    final_model_id: str | None
    final_record_hash: str | None
    artifact: ArtifactRef


@dataclass(frozen=True)
class TerminalDependencyState:
    task_id: str
    execution_stage: str
    status: str
    detail: str


@dataclass(frozen=True)
class ReportingRequest:
    task: TaskSpec
    final: FinalArtifactRecord | None
    artifacts: tuple[FinalLinkedArtifact, ...]
    endpoint_terminal_status: str
    endpoint_terminal_detail: str
    terminal_dependencies: tuple[TerminalDependencyState, ...]
    output_root: Path
    fdr: bool
    density: bool
    labels: bool
    numeric_first: bool

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord | None,
        *,
        artifacts: tuple[FinalLinkedArtifact, ...],
        endpoint_terminal_status: str | None = None,
        endpoint_terminal_detail: str = "",
        terminal_dependencies: tuple[TerminalDependencyState, ...] = (),
    ) -> "ReportingRequest":
        if context.config is None:
            raise RecordError("reporting service requires resolved workflow context")
        if task.workflow_phase != "report":
            raise RecordError("reporting request requires a report-phase task")
        terminal_status = endpoint_terminal_status
        if final is not None:
            if final.endpoint_model_id != task.endpoint.identifier:
                raise RecordError("report final artifact belongs to another endpoint")
            if terminal_status not in {None, "final_model_realized"}:
                raise RecordError("realized final record conflicts with endpoint terminal status")
            terminal_status = "final_model_realized"
            for item in artifacts:
                if item.final_model_id != final.final_model_id:
                    raise RecordError("report artifact belongs to another final model")
                if item.final_record_hash != final.record_hash:
                    raise RecordError("report artifact final-record hash mismatch")
        else:
            if terminal_status not in {"no_final_model", "input_failure"}:
                raise RecordError("report without a final record requires an explicit terminal state")
            for item in artifacts:
                if item.final_model_id not in {None, ""} or item.final_record_hash not in {None, ""}:
                    raise RecordError("no-final report artifact must not fabricate final identity")
        settings = context.config.model.reporting
        return cls(
            task=task,
            final=final,
            artifacts=tuple(artifacts),
            endpoint_terminal_status=str(terminal_status),
            endpoint_terminal_detail=str(endpoint_terminal_detail),
            terminal_dependencies=tuple(terminal_dependencies),
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            fdr=bool(settings["fdr"]),
            density=bool(settings["density"]),
            labels=bool(settings["labels"]),
            numeric_first=bool(settings["numeric_first"]),
        )


class ReportingRunnerOutput(Protocol):
    artifacts: tuple[TaskArtifact, ...]
    facts: Mapping[str, Any]
    detail: str


ReportingRunner = Callable[[ReportingRequest], ReportingRunnerOutput]


def _report_dependency_records(task: TaskSpec, context: RunContext):
    records = []
    for dependency in task.dependencies:
        if dependency.requirement != DependencyRequirement.TERMINAL:
            continue
        record = context.results.get(dependency.task_id)
        if record is None:
            raise RecordError(f"reporting terminal dependency is missing: {dependency.task_id}")
        if record.task.endpoint.identifier != task.endpoint.identifier:
            raise RecordError("reporting dependency belongs to another endpoint")
        records.append(record)
    return tuple(records)


def _dependency_closure(task: TaskSpec, context: RunContext):
    records = []
    pending = [dependency.task_id for dependency in task.dependencies]
    seen: set[str] = set()
    while pending:
        task_id = pending.pop()
        if task_id in seen:
            continue
        seen.add(task_id)
        record = context.results.get(task_id)
        if record is None:
            raise RecordError(f"reporting dependency closure is missing: {task_id}")
        records.append(record)
        pending.extend(dependency.task_id for dependency in record.task.dependencies)
    return tuple(records)


def _load_exact_final(task: TaskSpec, context: RunContext) -> FinalArtifactRecord | None:
    finals: dict[str, FinalArtifactRecord] = {}
    for record in _dependency_closure(task, context):
        payload = record.result.facts.get("final_model_record")
        if not isinstance(payload, dict):
            continue
        final = FinalArtifactRecord.from_dict(dict(payload))
        if final.endpoint_model_id != task.endpoint.identifier:
            continue
        finals[final.record_hash] = final
    if len(finals) > 1:
        raise RecordError("reporting dependency closure contains multiple final records")
    return next(iter(finals.values()), None)


def _terminal_states(records) -> tuple[TerminalDependencyState, ...]:
    return tuple(
        TerminalDependencyState(
            task_id=record.task.task_id,
            execution_stage=record.task.key.execution_stage,
            status=record.result.status.value,
            detail=record.result.detail,
        )
        for record in records
    )


def _no_final_status(records) -> tuple[str, str]:
    propagated = [
        (
            str(record.result.facts.get("endpoint_terminal_status", "")),
            str(record.result.facts.get("endpoint_terminal_detail", "")),
        )
        for record in records
    ]
    input_failures = [
        record
        for record in records
        if record.result.status == TaskStatus.INPUT_FAILURE
        or record.result.facts.get("endpoint_terminal_status") == "input_failure"
    ]
    if input_failures:
        details = [record.result.detail for record in input_failures if record.result.detail]
        details.extend(detail for status, detail in propagated if status == "input_failure" and detail)
        return "input_failure", ";".join(dict.fromkeys(details))
    no_finals = [
        record
        for record in records
        if record.result.status == TaskStatus.NO_FINAL_MODEL
        or record.result.facts.get("endpoint_terminal_status") == "no_final_model"
        or record.result.facts.get("final_model_realized") is False
    ]
    if no_finals:
        details = [record.result.detail for record in no_finals if record.result.detail]
        details.extend(detail for status, detail in propagated if status == "no_final_model" and detail)
        return "no_final_model", ";".join(dict.fromkeys(details))
    raise RecordError("missing final record without explicit no-final or input-failure state")


def _indexed_artifact_ref(
    artifact: TaskArtifact,
    *,
    source_task: TaskSpec,
    context: RunContext,
) -> ArtifactRef:
    path = Path(artifact.path).expanduser().resolve()
    try:
        relative_path = path.relative_to(context.store.run_root).as_posix()
    except ValueError as exc:
        raise RecordError("reporting dependency artifact is outside the configured run root") from exc
    if not path.is_file():
        raise RecordError(f"reporting dependency artifact is missing: {path}")
    matches = [
        row
        for row in context.store.load_artifact_index()
        if row.get("task_id") == source_task.task_id
        and row.get("kind") == artifact.kind
        and row.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise RecordError(
            "reporting dependency artifact requires exactly one run-store artifact-index row"
        )
    digest = sha256_file(path)
    if matches[0].get("sha256") != digest:
        raise RecordError(f"artifact index SHA-256 mismatch: {relative_path}")
    return ArtifactRef(
        task_id=source_task.task_id,
        kind=artifact.kind,
        relative_path=relative_path,
        sha256=digest,
    )


class ReportingService:
    """Execute one report from immutable final identity and explicit DAG artifacts."""

    def __init__(self, *, runner: ReportingRunner) -> None:
        self.runner = runner

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        try:
            dependency_records = _report_dependency_records(task, context)
            final = _load_exact_final(task, context)
            terminal_states = _terminal_states(dependency_records)
            if final is None:
                terminal_status, terminal_detail = _no_final_status(dependency_records)
            else:
                terminal_status, terminal_detail = "final_model_realized", ""
            linked_artifacts = tuple(
                FinalLinkedArtifact(
                    final_model_id=final.final_model_id if final is not None else None,
                    final_record_hash=final.record_hash if final is not None else None,
                    artifact=_indexed_artifact_ref(
                        artifact,
                        source_task=record.task,
                        context=context,
                    ),
                )
                for record in dependency_records
                for artifact in record.result.artifacts
            )
            request = ReportingRequest.from_context(
                task,
                context,
                final,
                artifacts=linked_artifacts,
                endpoint_terminal_status=terminal_status,
                endpoint_terminal_detail=terminal_detail,
                terminal_dependencies=terminal_states,
            )
            output = self.runner(request)
        except (OSError, RecordError, RuntimeError, ValueError) as exc:
            return TaskResult(TaskStatus.EXECUTION_FAILURE, f"reporting_service_failure:{exc}")

        facts = {
            **dict(output.facts),
            "reporting_complete": True,
            "endpoint_terminal_status": request.endpoint_terminal_status,
            "endpoint_terminal_detail": request.endpoint_terminal_detail,
            "final_model_id": final.final_model_id if final is not None else "",
            "final_record_hash": final.record_hash if final is not None else "",
        }
        if final is not None:
            facts["final_model_record"] = final.as_dict()
        for forbidden in ("source_status", "prediction_status", "source_accepted"):
            facts.pop(forbidden, None)
        return TaskResult(
            status=TaskStatus.COMPLETED,
            detail=output.detail,
            facts=facts,
            artifacts=output.artifacts,
        )


__all__ = [
    "FinalLinkedArtifact",
    "ReportingRequest",
    "ReportingRunner",
    "ReportingService",
    "TerminalDependencyState",
]
