"""Read-only orchestration services for validation, planning, and status."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Iterable

from .config import VtaModelConfig, load_vta_model
from .errors import RuntimeInputError
from .artifacts import (
    atomic_copy_missing,
    expected_artifacts,
    leaf_status,
    missing_artifacts,
    move_leaf_to_trash,
)
from .matlab_bridge import MatlabBridge, TaskRunContext
from .paths import leaf_directory
from .planner import (
    Selection,
    SubjectPlan,
    VtaTask,
    build_plan,
    equivalent_task_key,
)
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


@dataclass(frozen=True)
class RunSummary:
    generated: int = 0
    copied: int = 0
    skipped_existing: int = 0
    failed: int = 0
    skipped_dependency: int = 0

    def __add__(self, other: "RunSummary") -> "RunSummary":
        return RunSummary(
            generated=self.generated + other.generated,
            copied=self.copied + other.copied,
            skipped_existing=self.skipped_existing + other.skipped_existing,
            failed=self.failed + other.failed,
            skipped_dependency=(
                self.skipped_dependency + other.skipped_dependency
            ),
        )


class RunService:
    """Execute subject DAGs sequentially with subject-level parallelism."""

    def __init__(
        self,
        bridge: MatlabBridge,
        *,
        run_id: str,
    ) -> None:
        self.bridge = bridge
        self.run_id = run_id

    def run(
        self,
        subjects: tuple[SubjectPlan, ...],
        *,
        workers: int,
        resume: bool,
        force: bool,
    ) -> RunSummary:
        if workers <= 0:
            raise ValueError("workers must be positive")
        if resume and force:
            raise ValueError("resume and force are mutually exclusive")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self._run_subject,
                    subject,
                    force=force,
                )
                for subject in subjects
            ]
            summary = RunSummary()
            for future in futures:
                summary += future.result()
            return summary

    def _run_subject(
        self,
        subject: SubjectPlan,
        *,
        force: bool,
    ) -> RunSummary:
        summary = RunSummary()
        blocked: set[str] = set()
        if force:
            self._trash_selected_leaves(subject)
        for task in subject.tasks:
            if any(dependency in blocked for dependency in task.dependencies):
                blocked.add(task.task_id)
                summary += RunSummary(skipped_dependency=1)
                continue
            try:
                result = self._run_task(task, subject)
            except Exception:
                blocked.add(task.task_id)
                summary += RunSummary(failed=1)
                continue
            summary += RunSummary(**{result: 1})
        return summary

    def _run_task(
        self,
        task: VtaTask,
        subject: SubjectPlan,
    ) -> str:
        leaves = {
            space: leaf_directory(task, space) for space in task.model.spaces
        }
        if all(
            leaf_status(leaf, task.model.thresholds_v_per_m).value == "complete"
            for leaf in leaves.values()
        ):
            return "skipped_existing"
        copied = self._copy_from_equivalent_groups(task, subject, leaves)
        missing = {
            space: tuple(
                path.name
                for path in missing_artifacts(
                    leaf,
                    task.model.thresholds_v_per_m,
                )
            )
            for space, leaf in leaves.items()
        }
        missing = {space: names for space, names in missing.items() if names}
        if not missing:
            return "copied" if copied else "skipped_existing"
        context = TaskRunContext(
            run_id=self.run_id,
            output_leaves=leaves,
            missing_artifacts=missing,
        )
        self.bridge.run_task(task, context)
        for leaf in leaves.values():
            _validate_leaf_artifacts(task, leaf)
        return "generated"

    def _copy_from_equivalent_groups(
        self,
        task: VtaTask,
        subject: SubjectPlan,
        leaves: dict[str, Path],
    ) -> bool:
        copied = False
        candidates = subject.reuse_candidates or subject.tasks
        task_key = equivalent_task_key(task)
        donors = tuple(
            candidate
            for candidate in candidates
            if candidate.subject_id == task.subject_id
            and candidate.task_id != task.task_id
            and equivalent_task_key(candidate) == task_key
        )
        for space, leaf in leaves.items():
            for destination in expected_artifacts(
                leaf, task.model.thresholds_v_per_m
            ):
                if destination.is_file():
                    continue
                for donor in donors:
                    source = leaf_directory(donor, space) / destination.name
                    if not source.is_file():
                        continue
                    copied = (
                        atomic_copy_missing(source, destination) == "copied"
                        or copied
                    )
                    break
        return copied

    @staticmethod
    def _trash_selected_leaves(subject: SubjectPlan) -> None:
        leaves = {
            leaf_directory(task, space)
            for task in subject.tasks
            for space in task.model.spaces
        }
        for leaf in sorted(leaves, key=str):
            if leaf.exists():
                move_leaf_to_trash(leaf)


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
                    "status": leaf_status(
                        leaf, task.model.thresholds_v_per_m
                    ).value,
                    "subject_id": subject.subject_id,
                    "task_id": task.task_id,
                }
                yield json.dumps(row, sort_keys=True, separators=(",", ":"))


def _require_subject_file(subject_dir: Path, pattern: str, label: str) -> Path:
    matches = sorted(
        path
        for path in subject_dir.glob(pattern)
        if path.is_file() and not path.name.startswith("._")
    )
    if not matches:
        raise RuntimeInputError(f"Missing {label} under {subject_dir}")
    return matches[0]


def _validate_leaf_artifacts(task: VtaTask, leaf: Path) -> None:
    required = expected_artifacts(leaf, task.model.thresholds_v_per_m)
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeInputError(f"MATLAB did not create artifact: {missing[0]}")
