"""Read-only orchestration services for validation, planning, and status."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from typing import Callable, Iterable

from .config import VtaModelConfig, load_vta_model
from .errors import RuntimeInputError
from .artifacts import (
    leaf_status,
    missing_artifacts,
    move_leaf_to_trash,
    trash_root_for,
)
from .matlab_bridge import MatlabBridge
from .paths import canonical_head_model_path, leaf_directory
from .planner import (
    Selection,
    SubjectPlan,
    TaskKind,
    VtaTask,
    build_plan,
)
from .records import StudyBase
from .study_base import load_study_base
from .subject_manifest import build_subject_manifest
from .telemetry import ProcessObservation


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
    recovered_complete: int = 0
    failed: int = 0
    skipped_dependency: int = 0
    subject_process_failed: int = 0

    def __add__(self, other: "RunSummary") -> "RunSummary":
        return RunSummary(
            generated=self.generated + other.generated,
            copied=self.copied + other.copied,
            skipped_existing=self.skipped_existing + other.skipped_existing,
            recovered_complete=(
                self.recovered_complete + other.recovered_complete
            ),
            failed=self.failed + other.failed,
            skipped_dependency=(
                self.skipped_dependency + other.skipped_dependency
            ),
            subject_process_failed=(
                self.subject_process_failed + other.subject_process_failed
            ),
        )


class RunService:
    """Execute subject DAGs sequentially with subject-level parallelism."""

    def __init__(
        self,
        bridge: MatlabBridge,
        *,
        run_id: str,
        diagnostic_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.bridge = bridge
        self.run_id = run_id
        self._diagnostic_sink = diagnostic_sink or _write_diagnostic

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
        try:
            build_subject_manifest(subject, self.run_id)
            if force:
                self._trash_selected_leaves_transactionally(subject)
        except Exception as error:
            self._report_subject_failure(subject, error)
            return RunSummary(
                failed=len(subject.tasks),
                subject_process_failed=1,
            )
        if all(self._task_is_complete(task) for task in subject.tasks):
            return RunSummary(skipped_existing=len(subject.tasks))
        observation: ProcessObservation | None = None
        try:
            observation = self.bridge.run_subject_manifest(subject, self.run_id)
            return self._summary_from_observation(subject, observation)
        except Exception as error:
            self._report_subject_failure(subject, error)
            partial = getattr(error, "partial_observation", observation)
            return self._reconcile_subject(subject, partial) + RunSummary(
                subject_process_failed=1
            )

    @staticmethod
    def _task_is_complete(task: VtaTask) -> bool:
        return all(
            leaf_status(
                leaf_directory(task, space), task.model.thresholds_v_per_m
            ).value
            == "complete"
            for space in task.model.spaces
        )

    def _summary_from_observation(
        self,
        subject: SubjectPlan,
        observation: ProcessObservation,
    ) -> RunSummary:
        task_by_id = {task.task_id: task for task in subject.tasks}
        summary = RunSummary()
        for outcome in observation.outcomes:
            task = task_by_id[outcome.task_id]
            if outcome.status in {
                "generated",
                "copied",
                "skipped_existing",
                "recovered_complete",
            } and not self._task_is_complete(task):
                raise RuntimeInputError(
                    f"MATLAB reported {outcome.status} for an incomplete task: "
                    f"{task.task_id}"
                )
            summary += RunSummary(**{outcome.status: 1})
        return summary

    def _reconcile_subject(
        self,
        subject: SubjectPlan,
        observation: ProcessObservation | None,
    ) -> RunSummary:
        parsed = {
            outcome.task_id: outcome
            for outcome in (() if observation is None else observation.outcomes)
        }
        summary = RunSummary()
        for task in subject.tasks:
            outcome = parsed.get(task.task_id)
            if outcome is not None:
                if outcome.status in {
                    "generated",
                    "copied",
                    "skipped_existing",
                    "recovered_complete",
                } and not self._task_is_complete(task):
                    summary += RunSummary(failed=1)
                else:
                    summary += RunSummary(**{outcome.status: 1})
            elif self._task_is_complete(task):
                summary += RunSummary(recovered_complete=1)
            elif self._task_has_missing_required_dependency(task, subject):
                summary += RunSummary(skipped_dependency=1)
            else:
                summary += RunSummary(failed=1)
        return summary

    def _report_subject_failure(
        self,
        subject: SubjectPlan,
        error: Exception,
    ) -> None:
        lines = [
            f"VTA subject process failed for {subject.subject_id}: "
            f"{type(error).__name__}: {error}\n"
        ]
        lines.extend(f"{note}\n" for note in getattr(error, "__notes__", ()))
        for line in lines:
            self._diagnostic_sink(line)

    @staticmethod
    def _task_has_missing_required_dependency(
        task: VtaTask,
        subject: SubjectPlan,
    ) -> bool:
        if task.kind is not TaskKind.ALTERNATING_GROUP_PEAK:
            return False
        native_leaf = leaf_directory(task, "native")
        native_peak = native_leaf / "efield.nii.gz"
        if native_peak.is_file():
            return False
        native_missing = missing_artifacts(
            native_leaf,
            task.model.thresholds_v_per_m,
        )
        mni_leaf = leaf_directory(task, "MNI152NLin2009bAsym")
        mni_efield_missing = not (mni_leaf / "efield.nii.gz").is_file()
        if not native_missing and not mni_efield_missing:
            return False
        tasks = {candidate.task_id: candidate for candidate in subject.tasks}
        return any(
            not (
                leaf_directory(tasks[dependency], "native") / "efield.nii.gz"
            ).is_file()
            for dependency in task.dependencies
        )

    @staticmethod
    def _trash_selected_leaves_transactionally(subject: SubjectPlan) -> None:
        leaves = sorted(
            {
                leaf_directory(task, space)
                for task in subject.tasks
                for space in task.model.spaces
            },
            key=str,
        )
        existing = tuple(leaf for leaf in leaves if leaf.exists())
        for root in {trash_root_for(leaf) for leaf in existing}:
            root.mkdir(parents=True, exist_ok=True)
            if not os.access(root, os.W_OK):
                raise RuntimeInputError(f"Trash is not writable: {root}")
        moved: list[tuple[Path, Path]] = []
        try:
            for leaf in existing:
                moved.append((leaf, move_leaf_to_trash(leaf)))
        except Exception as move_error:
            rollback_errors: list[Exception] = []
            for original, trashed in reversed(moved):
                try:
                    original.parent.mkdir(parents=True, exist_ok=True)
                    if original.exists():
                        raise RuntimeInputError(
                            f"Cannot restore occupied leaf: {original}"
                        )
                    os.replace(trashed, original)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            for rollback_error in rollback_errors:
                move_error.add_note(
                    "VTA force rollback also failed: "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                )
            raise


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
    _require_file(atlas / "atlas_index.mat", "atlas index")
    _require_file(atlas / "gm_mask.nii.gz", "template atlas GM mask")
    for subject in subjects:
        _require_native_anchor(subject.subject_dir)
        _require_subject_file(
            subject.subject_dir,
            "normalization/transformations/*from-anchorNative_to-MNI152NLin2009bAsym*.nii.gz",
            "native-to-MNI transform",
        )
        _require_subject_file(
            subject.subject_dir,
            f"atlases/{model.atlas_set}/gm_mask.nii*",
            "patient-space atlas GM mask",
        )


def plan_lines(prepared: PreparedPlan) -> Iterable[str]:
    for subject in prepared.subjects:
        for task in subject.tasks:
            head_model = canonical_head_model_path(task)
            row = {
                "control_mode": task.sources[0].control_mode,
                "dependencies": list(task.dependencies),
                "delivery_mode": task.delivery_mode,
                "electrode_id": task.electrode_id,
                "frequency_group_id": task.frequency_group_id,
                "head_model": {
                    "path": str(head_model),
                    "status": (
                        "reuse_existing"
                        if head_model.is_file()
                        else "build_required"
                    ),
                },
                "hemisphere": task.hemisphere,
                "kind": task.kind.value,
                "leaves": {
                    space: str(leaf_directory(task, space))
                    for space in task.model.spaces
                },
                "phase_id": task.phase_id,
                "program_id": task.program_id,
                "source_ids": [source.source_id for source in task.sources],
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


def _require_native_anchor(subject_dir: Path) -> Path:
    matches = sorted(
        path
        for path in subject_dir.glob(
            "coregistration/anat/*space-anchorNative*desc-preproc*T1w.nii*"
        )
        if path.is_file()
        and not path.name.startswith("._")
        and "_label-" not in path.name
    )
    if not matches:
        raise RuntimeInputError(f"Missing native T1w anchor under {subject_dir}")
    if len(matches) != 1:
        raise RuntimeInputError(f"Ambiguous native T1w anchor under {subject_dir}")
    return matches[0]


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise RuntimeInputError(f"Missing {label}: {path}")
    return path


def _write_diagnostic(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.flush()
