from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
import time

import pytest

from my_helper.fiber.core.vta_pipeline.config import load_vta_model
from my_helper.fiber.core.vta_pipeline.matlab_bridge import (
    MatlabBridge,
    TaskRunContext,
)
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.planner import (
    Selection,
    SubjectPlan,
    build_plan,
)
from my_helper.fiber.core.vta_pipeline.service import RunService
from my_helper.fiber.core.vta_pipeline.study_base import load_study_base


REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"
MODEL_PATH = REPO_ROOT / "my_helper" / "stnsnr" / "config" / "vta_model.yaml"


@pytest.fixture
def subject_plan(tmp_path: Path) -> SubjectPlan:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    subject_dir = tmp_path / "subject"
    reconstruction = (
        subject_dir / "reconstruction" / "sub-SNr003_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    path = tmp_path / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return build_plan(
        load_study_base(path),
        load_vta_model(MODEL_PATH),
        Selection(subject_ids=("SNr003",)),
    )[0]


def task_context(task) -> TaskRunContext:
    return TaskRunContext(
        run_id="20260713T120000Z",
        input_hash="input-hash",
        study_base_sha256="study-hash",
        vta_model_sha256="model-hash",
        code_commit=None,
        resume=False,
        force=False,
        output_leaves={
            space: leaf_directory(task, space) for space in task.model.spaces
        },
    )


def test_bridge_writes_canonical_json_and_invokes_one_entrypoint(
    subject_plan: SubjectPlan,
) -> None:
    captured: dict[str, object] = {}

    def runner(command, **kwargs):
        task_path = Path(command[-1].split("'")[1].replace("''", "'"))
        captured["command"] = command
        captured["payload"] = json.loads(task_path.read_text(encoding="utf-8"))

    task = subject_plan.tasks[0]
    bridge = MatlabBridge(repo_root=REPO_ROOT, runner=runner)

    bridge.run_task(task, task_context(task))

    payload = captured["payload"]
    assert payload["task_id"] == task.task_id
    assert "backend" not in payload
    assert "component_id" not in json.dumps(payload)
    assert "mh_vta_run_canonical_task" in captured["command"][-1]


class RecordingBridge:
    def __init__(self, *, fail_subject: str | None = None):
        self.fail_subject = fail_subject
        self._lock = threading.Lock()
        self._subject_inflight: dict[str, int] = {}
        self._subjects_inflight = 0
        self.maximum_inflight_per_subject = 0
        self.maximum_subjects_inflight = 0

    def run_task(self, task, context: TaskRunContext) -> None:
        with self._lock:
            self._subject_inflight[task.subject_id] = (
                self._subject_inflight.get(task.subject_id, 0) + 1
            )
            self._subjects_inflight += 1
            self.maximum_inflight_per_subject = max(
                self.maximum_inflight_per_subject,
                self._subject_inflight[task.subject_id],
            )
            self.maximum_subjects_inflight = max(
                self.maximum_subjects_inflight,
                self._subjects_inflight,
            )
        try:
            time.sleep(0.01)
            if task.subject_id == self.fail_subject:
                raise RuntimeError("synthetic MATLAB failure")
            for leaf in context.output_leaves.values():
                leaf.mkdir(parents=True, exist_ok=True)
                (leaf / "efield.nii.gz").write_bytes(task.task_id.encode("ascii"))
                for threshold in task.model.thresholds_v_per_m:
                    token = f"{threshold / 1000:.2f}".replace(".", "p")
                    (leaf / f"vta_threshold-{token}Vpermm.nii.gz").write_bytes(b"vta")
        finally:
            with self._lock:
                self._subject_inflight[task.subject_id] -= 1
                self._subjects_inflight -= 1


def second_subject_plan(first: SubjectPlan, root: Path) -> SubjectPlan:
    task_map = {task.task_id: f"second-{task.task_id}" for task in first.tasks}
    tasks = tuple(
        replace(
            task,
            task_id=task_map[task.task_id],
            subject_id="SNr004",
            subject_dir=root,
            dependencies=tuple(task_map[item] for item in task.dependencies),
        )
        for task in first.tasks
    )
    return SubjectPlan(
        subject_id="SNr004",
        subject_dir=root,
        headmodel_sides=first.headmodel_sides,
        tasks=tasks,
    )


def run_service(bridge: RecordingBridge) -> RunService:
    return RunService(
        bridge,
        run_id="20260713T120000Z",
        study_base_sha256="study-hash",
        vta_model_sha256="model-hash",
        implementation_sha256="implementation-hash",
        code_commit=None,
    )


def test_workers_never_overlap_tasks_from_same_subject(
    subject_plan: SubjectPlan,
    tmp_path: Path,
) -> None:
    bridge = RecordingBridge()
    plans = (subject_plan, second_subject_plan(subject_plan, tmp_path / "subject-2"))

    summary = run_service(bridge).run(
        plans,
        workers=3,
        resume=False,
        force=False,
    )

    assert summary.failed == 0
    assert summary.completed == 8
    assert bridge.maximum_inflight_per_subject == 1
    assert bridge.maximum_subjects_inflight == 2


def test_failed_subject_does_not_cancel_other_subject(
    subject_plan: SubjectPlan,
    tmp_path: Path,
) -> None:
    bridge = RecordingBridge(fail_subject="SNr003")
    plans = (subject_plan, second_subject_plan(subject_plan, tmp_path / "subject-2"))

    summary = run_service(bridge).run(
        plans,
        workers=2,
        resume=False,
        force=False,
    )

    assert summary.failed == 1
    assert summary.completed == 4
    assert summary.skipped_dependency == 3


def test_resume_skips_completed_tasks(subject_plan: SubjectPlan) -> None:
    first_bridge = RecordingBridge()
    service = run_service(first_bridge)
    first = service.run((subject_plan,), workers=1, resume=False, force=False)
    second = service.run((subject_plan,), workers=1, resume=True, force=False)

    assert first.completed == 4
    assert second.reused == 4
    assert second.completed == 0
