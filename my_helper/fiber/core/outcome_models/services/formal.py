"""Final-artifact-driven formal inference service contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..records import FinalArtifactRecord, RecordError


@dataclass(frozen=True)
class FormalRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    output_root: Path
    permutations: int
    bootstraps: int
    seed: int

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
    ) -> "FormalRequest":
        if context.config is None:
            raise RecordError("formal service requires resolved workflow context")
        if task.workflow_phase != "formal":
            raise RecordError("formal request requires a formal-phase task")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("formal final artifact belongs to a different endpoint")
        if task.key.source_reference != "final_model_record":
            raise RecordError("formal task must reference an immutable final-model record")
        settings = context.config.model.formal
        return cls(
            task=task,
            final=final,
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            permutations=int(settings["permutations"]),
            bootstraps=int(settings["bootstraps"]),
            seed=int(settings["seed"]),
        )


@dataclass(frozen=True)
class FormalServiceOutput:
    artifacts: tuple[TaskArtifact, ...]
    detail: str = "formal_inference_completed"


FormalRunner = Callable[[FormalRequest], FormalServiceOutput]
FinalLoader = Callable[[TaskSpec, RunContext], FinalArtifactRecord]


class FormalService:
    """Run formal inference for exactly one immutable final model."""

    def __init__(self, *, runner: FormalRunner, final_loader: FinalLoader) -> None:
        self.runner = runner
        self.final_loader = final_loader

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        try:
            final = self.final_loader(task, context)
            request = FormalRequest.from_context(task, context, final)
            output = self.runner(request)
        except (OSError, RecordError, RuntimeError, ValueError) as exc:
            return TaskResult(TaskStatus.EXECUTION_FAILURE, f"formal_service_failure:{exc}")
        return TaskResult(
            status=TaskStatus.COMPLETED,
            detail=output.detail,
            facts={
                "formal_complete": True,
                "final_model_id": final.final_model_id,
                "final_artifact_record_hash": final.record_hash,
                "nuisance_columns": list(final.nuisance.columns),
            },
            artifacts=output.artifacts,
        )
