"""Canonical artifact paths for VTA tasks."""

from __future__ import annotations

from pathlib import Path

from .errors import PlanningError
from .planner import TaskKind, VtaTask


def canonical_head_model_path(task: VtaTask) -> Path:
    """Return the canonical native head-model path for a task hemisphere."""

    side_index = 1 if task.hemisphere == "R" else 2
    return (
        task.subject_dir
        / "headmodel"
        / "native"
        / f"sub-{task.subject_id}_desc-headmodel{side_index}.mat"
    )


def leaf_directory(task: VtaTask, space: str) -> Path:
    """Return the canonical output leaf for one task and output space."""

    if space not in task.model.spaces:
        raise PlanningError(f"Unknown output space: {space}")
    root = (
        task.subject_dir
        / "stimulations"
        / space
        / f"phase-{task.phase_id}"
        / f"program-{task.program_id}"
        / f"electrode-{task.electrode_id}"
        / f"frequency-group-{task.frequency_group_id}"
    )
    if task.kind is TaskKind.CONTINUOUS_JOINT:
        return root / "delivery-continuous" / "joint"
    if task.kind is TaskKind.ALTERNATING_SOURCE:
        if len(task.sources) != 1:
            raise PlanningError("Alternating source task must contain one source")
        return (
            root
            / "delivery-alternating"
            / "sources"
            / f"source-{task.sources[0].source_id}"
        )
    return root / "delivery-alternating" / "derived" / "group-peak"
