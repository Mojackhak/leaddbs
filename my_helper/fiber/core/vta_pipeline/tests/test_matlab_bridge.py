from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import signal
import subprocess
import threading
import time

import pytest

from my_helper.fiber.core.vta_pipeline.artifacts import expected_artifacts
from my_helper.fiber.core.vta_pipeline.config import load_vta_model
from my_helper.fiber.core.vta_pipeline.matlab_bridge import (
    MatlabBridge,
    TaskRunContext,
)
from my_helper.fiber.core.vta_pipeline.errors import (
    EventProtocolError,
    MatlabProcessError,
)
from my_helper.fiber.core.vta_pipeline.telemetry import EVENT_PREFIX
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.planner import (
    Selection,
    SubjectPlan,
    TaskKind,
    build_plan,
)
from my_helper.fiber.core.vta_pipeline.service import RunService
from my_helper.fiber.core.vta_pipeline.study_base import load_study_base


REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"
MODEL_PATH = REPO_ROOT / "my_helper" / "stnsnr" / "config" / "vta_model.yaml"


def write_runtime_inputs(raw: dict, root: Path) -> Path:
    subject_dir = root / "subject"
    reconstruction = (
        subject_dir / "reconstruction" / "sub-fixture_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    raw["study"]["subjects"][0]["subject_sources"]["electrode_reconstruction"][
        "path"
    ] = str(reconstruction)
    raw["study"]["subjects"][0]["subject_sources"]["leaddbs_subject_dir"] = str(
        subject_dir
    )
    path = root / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def subject_plan(tmp_path: Path) -> SubjectPlan:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    path = write_runtime_inputs(raw, tmp_path)
    return build_plan(
        load_study_base(path),
        load_vta_model(MODEL_PATH),
        Selection(subject_ids=("SNr003",)),
    )[0]


def task_context(task) -> TaskRunContext:
    output_leaves = {
        space: leaf_directory(task, space) for space in task.model.spaces
    }
    return TaskRunContext(
        run_id="20260713T120000Z",
        output_leaves=output_leaves,
        missing_artifacts={
            space: tuple(path.name for path in expected_artifacts(
                leaf, task.model.thresholds_v_per_m
            ))
            for space, leaf in output_leaves.items()
        },
    )


def telemetry_event(
    payload: dict[str, object],
    sequence: int,
    event_type: str,
    **fields: object,
) -> str:
    event = {
        "schema_version": "vta_event_v1",
        "event_type": event_type,
        "sequence": sequence,
        "run_id": payload["run_id"],
        "subject_id": payload["subject_id"],
        **fields,
    }
    return EVENT_PREFIX + json.dumps(event, separators=(",", ":")) + "\n"


def complete_event_lines(payload: dict[str, object]) -> list[str]:
    task_id = str(payload["task_id"])
    return [
        telemetry_event(payload, 1, "subject_ready"),
        telemetry_event(payload, 2, "task_started", task_id=task_id),
        telemetry_event(
            payload,
            3,
            "task_outcome",
            task_id=task_id,
            status="generated",
            copied_artifact_count=0,
            generated_artifact_count=1,
        ),
        telemetry_event(
            payload,
            4,
            "subject_summary",
            generated=1,
            copied=0,
            skipped_existing=0,
            recovered_complete=0,
            failed=0,
            skipped_dependency=0,
            process_success=True,
        ),
    ]


class FakePopen:
    def __init__(
        self,
        command: list[str],
        lines: list[str],
        *,
        returncode: int = 0,
        timeout_once: bool = False,
        lifecycle: list[str] | None = None,
    ) -> None:
        self.command = command
        self.pid = 1234
        self.lifecycle = lifecycle if lifecycle is not None else []
        self.stdout = RecordingStdout("".join(lines), self.lifecycle)
        self.returncode = returncode
        self.timeout_once = timeout_once
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.lifecycle.append("wait")
        self.wait_calls += 1
        if timeout is not None and self.timeout_once:
            self.timeout_once = False
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.returncode

    def poll(self) -> int | None:
        if self.terminated or self.killed or self.wait_calls:
            return self.returncode
        return None

    def terminate(self) -> None:
        self.lifecycle.append("terminate")
        self.terminated = True

    def kill(self) -> None:
        self.lifecycle.append("kill")
        self.killed = True


class RecordingStdout(io.StringIO):
    def __init__(self, value: str, lifecycle: list[str]) -> None:
        super().__init__(value)
        self._lifecycle = lifecycle

    def __iter__(self):
        self._lifecycle.append("stdout")
        return super().__iter__()


class PopenFactory:
    def __init__(
        self,
        line_factory=complete_event_lines,
        *,
        returncode: int = 0,
        timeout_once: bool = False,
    ) -> None:
        self.line_factory = line_factory
        self.returncode = returncode
        self.timeout_once = timeout_once
        self.process: FakePopen | None = None
        self.payload: dict[str, object] | None = None
        self.task_path: Path | None = None
        self.kwargs: dict[str, object] | None = None
        self.lifecycle: list[str] = []

    def __call__(self, command: list[str], **kwargs: object) -> FakePopen:
        task_path = Path(command[-1].split("'")[1].replace("''", "'"))
        payload = json.loads(task_path.read_text(encoding="utf-8"))
        self.task_path = task_path
        self.payload = payload
        self.kwargs = kwargs
        self.process = FakePopen(
            command,
            self.line_factory(payload),
            returncode=self.returncode,
            timeout_once=self.timeout_once,
            lifecycle=self.lifecycle,
        )
        return self.process


def test_bridge_payload_contains_missing_paths_but_no_hash_or_provenance(
    subject_plan: SubjectPlan,
) -> None:
    factory = PopenFactory()
    task = subject_plan.tasks[0]
    result = MatlabBridge(repo_root=REPO_ROOT, popen_factory=factory).run_task(
        task,
        task_context(task),
    )

    assert result.outcomes[0].status == "generated"
    assert factory.payload is not None
    payload = factory.payload
    assert payload["task_id"] == task.task_id
    assert payload["missing_artifacts"]
    assert "input_hash" not in payload
    assert "implementation_sha256" not in payload
    assert "study_base_sha256" not in payload
    assert "provenance" not in json.dumps(payload).lower()
    assert factory.process is not None
    assert "mh_vta_run_canonical_task" in factory.process.command[-1]
    assert factory.kwargs == {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
        "start_new_session": True,
    }
    assert factory.task_path is not None
    assert not factory.task_path.exists()


def test_bridge_forwards_only_unframed_diagnostics(
    subject_plan: SubjectPlan,
) -> None:
    def lines(payload: dict[str, object]) -> list[str]:
        framed = complete_event_lines(payload)
        return ["diagnostic before\n", *framed, "diagnostic after\n"]

    diagnostics: list[str] = []
    task = subject_plan.tasks[0]
    MatlabBridge(
        repo_root=REPO_ROOT,
        popen_factory=PopenFactory(lines),
        diagnostic_sink=diagnostics.append,
    ).run_task(task, task_context(task))

    assert diagnostics == ["diagnostic before\n", "diagnostic after\n"]


class RecordingMonitor:
    def __init__(self, lifecycle: list[str] | None = None) -> None:
        self.events: list[tuple[str, str, int]] = []
        self.lifecycle = lifecycle if lifecycle is not None else []

    def register(self, subject_id: str, pid: int) -> None:
        self.lifecycle.append("register")
        self.events.append(("register", subject_id, pid))

    def unregister(self, subject_id: str, pid: int) -> None:
        self.lifecycle.append("unregister")
        self.events.append(("unregister", subject_id, pid))


def test_bridge_registers_monitor_and_unregisters_after_reaping(
    subject_plan: SubjectPlan,
) -> None:
    factory = PopenFactory()
    monitor = RecordingMonitor(factory.lifecycle)
    task = subject_plan.tasks[0]

    MatlabBridge(
        repo_root=REPO_ROOT,
        popen_factory=factory,
        memory_monitor=monitor,
    ).run_task(task, task_context(task))

    assert monitor.events == [
        ("register", task.subject_id, 1234),
        ("unregister", task.subject_id, 1234),
    ]
    assert factory.process is not None
    assert factory.process.wait_calls == 1
    assert factory.lifecycle == ["register", "stdout", "wait", "unregister"]


def test_bridge_terminates_reaps_and_unregisters_on_protocol_failure(
    subject_plan: SubjectPlan,
) -> None:
    factory = PopenFactory(
        lambda payload: [EVENT_PREFIX + "{malformed}\n"],
        timeout_once=True,
    )
    monitor = RecordingMonitor(factory.lifecycle)
    group_signals: list[int] = []
    task = subject_plan.tasks[0]

    with pytest.raises(EventProtocolError):
        MatlabBridge(
            repo_root=REPO_ROOT,
            popen_factory=factory,
            memory_monitor=monitor,
            process_group_signaler=lambda pid, requested: group_signals.append(
                requested
            ),
        ).run_task(task, task_context(task))

    assert factory.process is not None
    assert factory.process.wait_calls == 2
    assert group_signals == [signal.SIGTERM, signal.SIGKILL]
    assert factory.lifecycle == [
        "register",
        "stdout",
        "wait",
        "wait",
        "unregister",
    ]
    assert monitor.events[-1][0] == "unregister"


def test_bridge_preserves_protocol_error_when_cleanup_fails(
    subject_plan: SubjectPlan,
) -> None:
    factory = PopenFactory(lambda payload: [EVENT_PREFIX + "{malformed}\n"])
    monitor = RecordingMonitor(factory.lifecycle)
    task = subject_plan.tasks[0]

    def fail_signal(pid: int, requested: int) -> None:
        raise PermissionError(f"cannot signal {pid} with {requested}")

    with pytest.raises(EventProtocolError) as captured:
        MatlabBridge(
            repo_root=REPO_ROOT,
            popen_factory=factory,
            memory_monitor=monitor,
            process_group_signaler=fail_signal,
        ).run_task(task, task_context(task))

    assert "process reaping also failed" in "\n".join(captured.value.__notes__)
    assert factory.lifecycle == ["register", "stdout"]
    assert monitor.events == [("register", task.subject_id, 1234)]


def test_bridge_rejects_nonzero_matlab_exit(subject_plan: SubjectPlan) -> None:
    factory = PopenFactory(returncode=7)
    task = subject_plan.tasks[0]

    with pytest.raises(MatlabProcessError, match="7"):
        MatlabBridge(
            repo_root=REPO_ROOT,
            popen_factory=factory,
        ).run_task(task, task_context(task))


class RecordingBridge:
    def __init__(self, *, fail_task_id: str | None = None):
        self.fail_task_id = fail_task_id
        self.calls: list[str] = []
        self.contexts: list[TaskRunContext] = []
        self._lock = threading.Lock()
        self._subject_inflight: dict[str, int] = {}
        self._subjects_inflight = 0
        self.maximum_inflight_per_subject = 0
        self.maximum_subjects_inflight = 0

    def run_task(self, task, context: TaskRunContext) -> None:
        with self._lock:
            self.calls.append(task.task_id)
            self.contexts.append(context)
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
            time.sleep(0.005)
            if task.task_id == self.fail_task_id:
                raise RuntimeError("synthetic MATLAB failure")
            for space, names in context.missing_artifacts.items():
                leaf = context.output_leaves[space]
                leaf.mkdir(parents=True, exist_ok=True)
                for name in names:
                    (leaf / name).write_bytes(f"{task.task_id}:{name}".encode("ascii"))
        finally:
            with self._lock:
                self._subject_inflight[task.subject_id] -= 1
                self._subjects_inflight -= 1


def clone_subject_plan(first: SubjectPlan, root: Path) -> SubjectPlan:
    task_map = {task.task_id: f"second-{task.task_id}" for task in first.tasks}

    def clone(task):
        return replace(
            task,
            task_id=task_map.get(task.task_id, f"candidate-{task.task_id}"),
            subject_id="different-subject",
            subject_dir=root,
            reconstruction_path=root / "reconstruction.mat",
            dependencies=tuple(task_map[item] for item in task.dependencies),
        )

    tasks = tuple(clone(task) for task in first.tasks)
    return SubjectPlan(
        subject_id="different-subject",
        subject_dir=root,
        headmodel_sides=first.headmodel_sides,
        tasks=tasks,
        reuse_candidates=tasks,
    )


def test_workers_never_overlap_tasks_from_same_subject(
    subject_plan: SubjectPlan,
    tmp_path: Path,
) -> None:
    bridge = RecordingBridge()
    plans = (subject_plan, clone_subject_plan(subject_plan, tmp_path / "subject-2"))

    summary = RunService(bridge, run_id="run").run(
        plans,
        workers=3,
        resume=False,
        force=False,
    )

    assert summary.failed == 0
    assert summary.generated == 8
    assert bridge.maximum_inflight_per_subject == 1
    assert bridge.maximum_subjects_inflight == 2


def test_failure_skips_only_dependency_descendants(
    subject_plan: SubjectPlan,
) -> None:
    failed_source = next(
        task
        for task in subject_plan.tasks
        if task.kind is TaskKind.ALTERNATING_SOURCE
    )
    bridge = RecordingBridge(fail_task_id=failed_source.task_id)

    summary = RunService(bridge, run_id="run").run(
        (subject_plan,), workers=1, resume=False, force=False
    )

    assert summary.failed == 1
    assert summary.generated == 2
    assert summary.skipped_dependency == 1
    assert len(bridge.calls) == 3


def test_failed_reuse_owner_skips_still_dependent_recipient(
    tmp_path: Path,
) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    duplicate_phase(raw)
    path = write_runtime_inputs(raw, tmp_path)
    full = build_plan(
        load_study_base(path),
        load_vta_model(MODEL_PATH),
        Selection(subject_ids=("SNr003",)),
    )[0]
    equivalent = tuple(
        task
        for task in full.tasks
        if task.kind is TaskKind.CONTINUOUS_JOINT
    )
    assert len(equivalent) == 2
    plan = replace(full, tasks=equivalent, reuse_candidates=equivalent)
    bridge = RecordingBridge(fail_task_id=equivalent[0].task_id)

    summary = RunService(bridge, run_id="run").run(
        (plan,), workers=1, resume=False, force=False
    )

    assert summary.failed == 1
    assert summary.skipped_dependency == 1
    assert summary.generated == 0
    assert bridge.calls == [equivalent[0].task_id]


def test_existing_paths_are_skipped_without_hash_checks(
    subject_plan: SubjectPlan,
) -> None:
    bridge = RecordingBridge()
    service = RunService(bridge, run_id="run")
    first = service.run((subject_plan,), workers=1, resume=False, force=False)
    second = service.run((subject_plan,), workers=1, resume=True, force=False)

    assert first.generated == 4
    assert second.skipped_existing == 4
    assert len(bridge.calls) == 4


def test_partial_leaf_sends_only_missing_artifact_to_bridge(
    subject_plan: SubjectPlan,
) -> None:
    bridge = RecordingBridge()
    service = RunService(bridge, run_id="run")
    first = service.run((subject_plan,), workers=1, resume=False, force=False)
    task = subject_plan.tasks[0]
    missing_path = expected_artifacts(
        leaf_directory(task, "native"), task.model.thresholds_v_per_m
    )[-1]
    missing_path.unlink()

    second = service.run((subject_plan,), workers=1, resume=False, force=False)

    assert first.generated == 4
    assert second.generated == 1
    assert second.skipped_existing == 3
    assert bridge.contexts[-1].missing_artifacts == {
        "native": (missing_path.name,)
    }


def duplicate_phase(raw: dict) -> None:
    subject = raw["study"]["subjects"][0]
    phase = deepcopy(subject["phases"][0])
    phase["phase_id"] = "arbitrary-followup"
    phase["programs"][0]["program_id"] = 77
    for electrode in phase["programs"][0]["electrode_programs"]:
        for group_index, group in enumerate(electrode["frequency_groups"]):
            group["frequency_group_id"] = f"renamed-group-{group_index}"
            for source_index, source in enumerate(group["sources"]):
                source["source_id"] = f"renamed-source-{source_index}"
    subject["phases"].append(phase)


def test_selected_group_reuses_unselected_same_subject_group(
    tmp_path: Path,
) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    duplicate_phase(raw)
    path = write_runtime_inputs(raw, tmp_path)
    model = load_vta_model(MODEL_PATH)
    study = load_study_base(path)
    all_tasks = build_plan(
        study, model, Selection(subject_ids=("SNr003",))
    )[0]
    donor_tasks = tuple(
        task for task in all_tasks.tasks if task.phase_id == "T1"
    )
    for task in donor_tasks:
        for space in task.model.spaces:
            for artifact in expected_artifacts(
                leaf_directory(task, space), task.model.thresholds_v_per_m
            ):
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(b"donor")
    selected = build_plan(
        study,
        model,
        Selection(subject_ids=("SNr003",), phase_ids=("arbitrary-followup",)),
    )[0]
    bridge = RecordingBridge()

    summary = RunService(bridge, run_id="run").run(
        (selected,), workers=1, resume=False, force=False
    )

    assert summary.copied == 4
    assert summary.generated == 0
    assert bridge.calls == []
    for task in selected.tasks:
        for space in task.model.spaces:
            assert all(
                path.read_bytes() == b"donor"
                for path in expected_artifacts(
                    leaf_directory(task, space), task.model.thresholds_v_per_m
                )
            )


def test_equal_group_in_different_subject_is_not_a_donor(
    subject_plan: SubjectPlan,
    tmp_path: Path,
) -> None:
    for task in subject_plan.tasks:
        for space in task.model.spaces:
            for artifact in expected_artifacts(
                leaf_directory(task, space), task.model.thresholds_v_per_m
            ):
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(b"first-subject")
    second = clone_subject_plan(subject_plan, tmp_path / "different-subject")
    bridge = RecordingBridge()

    summary = RunService(bridge, run_id="run").run(
        (second,), workers=1, resume=False, force=False
    )

    assert summary.generated == 4
    assert summary.copied == 0
    assert len(bridge.calls) == 4
