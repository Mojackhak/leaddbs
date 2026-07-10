"""Final-artifact-driven formal inference service contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

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
    score: Mapping[str, float | int] | None = None

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
        score = None
        if task.endpoint.model_family in {"hf_fiber", "ulf_fiber"}:
            try:
                values = context.config.model.normative_fiber["score"]
                score = {
                    "sweet_fraction": float(values["sweet_fraction"]),
                    "sour_fraction": float(values["sour_fraction"]),
                    "weighted_peak_fraction": float(values["weighted_peak_fraction"]),
                    "sweet_selected_min_count": int(values["sweet_selected_min_count"]),
                    "sour_selected_min_count": int(values["sour_selected_min_count"]),
                    "weighted_peak_min_count": int(values["weighted_peak_min_count"]),
                }
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise RecordError(
                    "configured normative-fiber formal request requires all six score values"
                ) from exc
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
            score=score,
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
