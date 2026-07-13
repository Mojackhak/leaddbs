"""Read-only orchestration services for validation, planning, and status."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .config import VtaModelConfig, load_vta_model
from .errors import ExecutionUnavailableError, RuntimeInputError
from .paths import leaf_directory
from .planner import Selection, SubjectPlan, build_plan
from .provenance import read_leaf_status
from .records import StudyBase
from .study_base import load_study_base


_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class PreparedPlan:
    study: StudyBase
    model: VtaModelConfig
    subjects: tuple[SubjectPlan, ...]

    @property
    def task_count(self) -> int:
        return sum(len(subject.tasks) for subject in self.subjects)


def prepare_plan(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    selection: Selection,
) -> PreparedPlan:
    study = load_study_base(study_base_path)
    model = load_vta_model(vta_model_path)
    subjects = build_plan(study, model, selection)
    validate_runtime_inputs(subjects, model)
    return PreparedPlan(study=study, model=model, subjects=subjects)


def validate_runtime_inputs(
    subjects: tuple[SubjectPlan, ...],
    model: VtaModelConfig,
) -> None:
    atlas = (
        _REPO_ROOT
        / "templates"
        / "space"
        / "MNI152NLin2009bAsym"
        / "atlases"
        / model.atlas_set
    )
    if not atlas.is_dir():
        raise RuntimeInputError(f"Atlas does not exist: {atlas}")
    for subject in subjects:
        _require_subject_file(
            subject.subject_dir,
            "coregistration/anat/*space-anchorNative*desc-preproc*T1w.nii*",
            "native T1w anchor",
        )
        _require_subject_file(
            subject.subject_dir,
            "normalization/transformations/*from-anchorNative_to-MNI152NLin2009bAsym*.nii.gz",
            "native-to-MNI transform",
        )


def plan_lines(prepared: PreparedPlan) -> Iterable[str]:
    for subject in prepared.subjects:
        for task in subject.tasks:
            row = {
                "dependencies": list(task.dependencies),
                "kind": task.kind.value,
                "leaves": {
                    space: str(leaf_directory(task, space))
                    for space in task.model.spaces
                },
                "subject_id": subject.subject_id,
                "task_id": task.task_id,
            }
            yield json.dumps(row, sort_keys=True, separators=(",", ":"))


def status_lines(prepared: PreparedPlan) -> Iterable[str]:
    for subject in prepared.subjects:
        for task in subject.tasks:
            for space in task.model.spaces:
                leaf = leaf_directory(task, space)
                row = {
                    "leaf": str(leaf),
                    "space": space,
                    "status": read_leaf_status(leaf).value,
                    "subject_id": subject.subject_id,
                    "task_id": task.task_id,
                }
                yield json.dumps(row, sort_keys=True, separators=(",", ":"))


def run_unavailable() -> None:
    raise ExecutionUnavailableError("execution backend is not installed")


def _require_subject_file(subject_dir: Path, pattern: str, label: str) -> Path:
    matches = sorted(
        path
        for path in subject_dir.glob(pattern)
        if path.is_file() and not path.name.startswith("._")
    )
    if not matches:
        raise RuntimeInputError(f"Missing {label} under {subject_dir}")
    return matches[0]
