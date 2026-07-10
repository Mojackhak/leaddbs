"""Final-identity-locked reporting request contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..executor import RunContext
from ..planner import TaskSpec
from ..records import ArtifactRef, FinalArtifactRecord, RecordError


@dataclass(frozen=True)
class FinalLinkedArtifact:
    final_model_id: str
    final_record_hash: str
    artifact: ArtifactRef


@dataclass(frozen=True)
class ReportingRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    artifacts: tuple[FinalLinkedArtifact, ...]
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
        final: FinalArtifactRecord,
        *,
        artifacts: tuple[FinalLinkedArtifact, ...],
    ) -> "ReportingRequest":
        if context.config is None:
            raise RecordError("reporting service requires resolved workflow context")
        if task.workflow_phase != "report":
            raise RecordError("reporting request requires a report-phase task")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("report final artifact belongs to another endpoint")
        for item in artifacts:
            if item.final_model_id != final.final_model_id:
                raise RecordError("report artifact belongs to another final model")
            if item.final_record_hash != final.record_hash:
                raise RecordError("report artifact final-record hash mismatch")
        settings = context.config.model.reporting
        return cls(
            task=task,
            final=final,
            artifacts=tuple(artifacts),
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
