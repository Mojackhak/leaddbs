"""Read-only orchestration services for validation, planning, and status."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Iterable

from .config import VtaModelConfig, load_vta_model
from .errors import RuntimeInputError
from .paths import leaf_directory
from .matlab_bridge import MatlabBridge, TaskRunContext
from .planner import Selection, SubjectPlan, VtaTask, build_plan
from .provenance import (
    LeafStore,
    ProvenanceContext,
    compute_input_hash,
    read_leaf_status,
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
    completed: int = 0
    reused: int = 0
    failed: int = 0
    skipped_dependency: int = 0

    def __add__(self, other: "RunSummary") -> "RunSummary":
        return RunSummary(
            completed=self.completed + other.completed,
            reused=self.reused + other.reused,
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
        study_base_sha256: str,
        vta_model_sha256: str,
        implementation_sha256: str,
        code_commit: str | None,
    ) -> None:
        self.bridge = bridge
        self.run_id = run_id
        self.study_base_sha256 = study_base_sha256
        self.vta_model_sha256 = vta_model_sha256
        self.implementation_sha256 = implementation_sha256
        self.code_commit = code_commit

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
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self._run_subject,
                    subject,
                    resume=resume,
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
        resume: bool,
        force: bool,
    ) -> RunSummary:
        summary = RunSummary()
        for index, task in enumerate(subject.tasks):
            try:
                result = self._run_task(task, resume=resume, force=force)
            except Exception:
                return summary + RunSummary(
                    failed=1,
                    skipped_dependency=len(subject.tasks) - index - 1,
                )
            if result == "reuse":
                summary += RunSummary(reused=1)
            else:
                summary += RunSummary(completed=1)
        return summary

    def _run_task(
        self,
        task: VtaTask,
        *,
        resume: bool,
        force: bool,
    ) -> str:
        input_hash = compute_input_hash(
            task.to_payload(),
            study_base_sha256=self.study_base_sha256,
            vta_model_sha256=self.vta_model_sha256,
            implementation_sha256=self.implementation_sha256,
            code_commit=self.code_commit,
        )
        provenance = ProvenanceContext(
            run_id=self.run_id,
            input_hash=input_hash,
            study_base_sha256=self.study_base_sha256,
            vta_model_sha256=self.vta_model_sha256,
            code_commit=self.code_commit,
        )
        leaves = {
            space: leaf_directory(task, space) for space in task.model.spaces
        }
        stores = {space: LeafStore(path) for space, path in leaves.items()}
        preparation = {
            space: store.prepare(provenance, force=force, resume=resume)
            for space, store in stores.items()
        }
        if all(value == "reuse" for value in preparation.values()):
            return "reuse"
        context = TaskRunContext(
            run_id=self.run_id,
            input_hash=input_hash,
            study_base_sha256=self.study_base_sha256,
            vta_model_sha256=self.vta_model_sha256,
            implementation_sha256=self.implementation_sha256,
            code_commit=self.code_commit,
            resume=resume,
            force=force,
            output_leaves=leaves,
        )
        run_spaces = [
            space for space, value in preparation.items() if value == "run"
        ]
        try:
            self.bridge.run_task(task, context)
            for space in run_spaces:
                _validate_leaf_artifacts(task, leaves[space])
                stores[space].complete(provenance, leaves[space] / "efield.nii.gz")
        except Exception:
            for space in run_spaces:
                stores[space].fail(provenance)
            raise
        return "completed"


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
    required = [leaf / "efield.nii.gz"]
    for threshold in task.model.thresholds_v_per_m:
        token = f"{threshold / 1000:.2f}".replace(".", "p")
        required.append(leaf / f"vta_threshold-{token}Vpermm.nii.gz")
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeInputError(f"MATLAB did not create artifact: {missing[0]}")
