"""Final-linked sensitivity request contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..executor import RunContext
from ..planner import TaskSpec
from ..records import DeltaHFBundle, FinalArtifactRecord, RecordError


@dataclass(frozen=True)
class SensitivityRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    delta_hf: DeltaHFBundle | None
    output_root: Path
    selected_tau_multipliers: tuple[float, float]
    rebuild_geometry: bool
    rebuild_delta_hf: bool
    rebuild_support_qc: bool
    rebuild_nuisance: bool
    oss_model: str
    oss_activation_threshold: float

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        *,
        delta_hf: DeltaHFBundle | None,
    ) -> "SensitivityRequest":
        if context.config is None:
            raise RecordError("sensitivity service requires resolved workflow context")
        if task.workflow_phase != "sensitivity":
            raise RecordError("sensitivity request requires a sensitivity-phase task")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("sensitivity final artifact belongs to another endpoint")
        adjusted = final.final_branch == "delta_hf_adjusted"
        if adjusted:
            if delta_hf is None or not delta_hf.valid:
                raise RecordError("adjusted sensitivity requires a valid DeltaHF bundle")
            if final.nuisance.delta_hf_record_hash != delta_hf.record_hash:
                raise RecordError("sensitivity DeltaHF bundle does not match the final nuisance plan")
        elif delta_hf is not None and final.nuisance.delta_hf_record_hash is not None:
            raise RecordError("no-delta sensitivity cannot reference DeltaHF nuisance")

        operation = task.key.execution_stage
        is_jitter = operation == "spatial_jitter"
        multipliers = tuple(float(value) for value in context.config.model.sensitivity["selected_tau_multipliers"])
        if len(multipliers) != 2:
            raise RecordError("selected tau sensitivity requires exactly two multipliers")
        return cls(
            task=task,
            final=final,
            delta_hf=delta_hf,
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            selected_tau_multipliers=(multipliers[0], multipliers[1]),
            rebuild_geometry=is_jitter,
            rebuild_delta_hf=is_jitter and adjusted,
            rebuild_support_qc=is_jitter and adjusted,
            rebuild_nuisance=is_jitter,
            oss_model=str(context.config.model.oss["model"]),
            oss_activation_threshold=float(context.config.model.oss["deterministic_activation_threshold"]),
        )
