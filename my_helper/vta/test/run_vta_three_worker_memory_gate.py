#!/usr/bin/env python3
"""Run the isolated three-worker canonical VTA memory acceptance gate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Any

import psutil

from my_helper.fiber.core.vta_pipeline.artifacts import expected_artifacts
from my_helper.fiber.core.vta_pipeline.matlab_bridge import MatlabBridge
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.planner import Selection, TaskKind
from my_helper.fiber.core.vta_pipeline.process_monitor import (
    ProcessTreeMemoryMonitor,
)
from my_helper.fiber.core.vta_pipeline.service import RunService, prepare_plan


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / (
    "vta_performance_benchmark_v1.json"
)
DEFAULT_CASE_IDS = (
    "snr003_t2_p2_l_alternating",
    "snr006_t2_p2_l_alternating",
    "snr011_t2_p2_l_continuous",
)
EXPECTED_SUBJECT_COUNT = 3
EXPECTED_TASK_COUNT = 7
EXPECTED_FEM_SOLVE_COUNT = 5
WORKER_COUNT = 3
SAMPLE_INTERVAL_SECONDS = 0.1
ALLOWED_VALIDATION_ROOT = Path("/Volumes/VAL/STNSNr/validation")


class TrackingMemoryMonitor(ProcessTreeMemoryMonitor):
    """Add root-overlap and nested-MATLAB evidence to the shared RSS monitor."""

    def __init__(self) -> None:
        self._tracking_lock = threading.Lock()
        self._tracked_roots: dict[str, int] = {}
        self.max_active_subject_roots = 0
        self.max_sampled_live_subject_roots = 0
        self.max_nested_matlab_descendants = 0
        self.lifecycle: list[dict[str, Any]] = []
        self.sample_interval_seconds = SAMPLE_INTERVAL_SECONDS
        super().__init__(sample_interval_seconds=self.sample_interval_seconds)

    def register(self, subject_id: str, pid: int) -> None:
        super().register(subject_id, pid)
        with self._tracking_lock:
            self._tracked_roots[subject_id] = pid
            self.max_active_subject_roots = max(
                self.max_active_subject_roots,
                len(self._tracked_roots),
            )
            self.lifecycle.append(
                {
                    "event": "register",
                    "subject_id": subject_id,
                    "pid": pid,
                    "monotonic_seconds": time.monotonic(),
                    "active_roots": len(self._tracked_roots),
                }
            )

    def unregister(self, subject_id: str, pid: int) -> None:
        super().unregister(subject_id, pid)
        with self._tracking_lock:
            if self._tracked_roots.get(subject_id) == pid:
                del self._tracked_roots[subject_id]
            self.lifecycle.append(
                {
                    "event": "unregister",
                    "subject_id": subject_id,
                    "pid": pid,
                    "monotonic_seconds": time.monotonic(),
                    "active_roots": len(self._tracked_roots),
                }
            )

    def sample_once(self) -> None:
        with self._tracking_lock:
            roots = dict(self._tracked_roots)
        live_roots, nested = observe_matlab_processes(roots)
        with self._tracking_lock:
            self.max_sampled_live_subject_roots = max(
                self.max_sampled_live_subject_roots,
                live_roots,
            )
            self.max_nested_matlab_descendants = max(
                self.max_nested_matlab_descendants,
                nested,
            )
        super().sample_once()


class RecordingBridge:
    """Thread-safe observation recorder around the production MATLAB bridge."""

    def __init__(self, bridge: MatlabBridge) -> None:
        self._bridge = bridge
        self._lock = threading.Lock()
        self.observations = []

    def run_subject_manifest(self, subject, run_id):
        observation = self._bridge.run_subject_manifest(subject, run_id)
        with self._lock:
            self.observations.append(observation)
        return observation


def _is_matlab_process(process: psutil.Process) -> bool:
    try:
        name = process.name().lower()
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return False
    return name == "matlab" or name.startswith("matlab_")


def observe_matlab_processes(
    roots: Mapping[str, int],
    process_provider=psutil.Process,
) -> tuple[int, int]:
    """Return live MATLAB roots and nested MATLAB descendants for one sample."""

    live_roots = 0
    nested = 0
    for root_pid in roots.values():
        try:
            root = process_provider(root_pid)
            root_is_live = root.is_running() and root.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            continue
        if not root_is_live or not _is_matlab_process(root):
            continue
        live_roots += 1
        try:
            children = root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            children = []
        nested += sum(_is_matlab_process(child) for child in children)
    return live_roots, nested


def load_json_object(path: Path | str, label: str) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read {label}: {resolved}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def resolve_gate_cases(
    fixture: Mapping[str, Any], case_ids: Sequence[str]
) -> tuple[dict[str, Any], ...]:
    """Resolve three distinct-subject cases with one shared selector tuple."""

    if len(case_ids) != EXPECTED_SUBJECT_COUNT or len(set(case_ids)) != len(case_ids):
        raise ValueError("Three-worker gate requires three unique case IDs")
    cases = {
        str(case.get("case_id")): case
        for case in fixture.get("cases", ())
        if isinstance(case, Mapping)
    }
    selected = []
    for case_id in case_ids:
        case = cases.get(case_id)
        if case is None:
            raise ValueError(f"Unknown memory-gate case ID: {case_id}")
        selector = case.get("selector")
        if not isinstance(selector, Mapping):
            raise ValueError(f"Case has no selector object: {case_id}")
        selected.append(deepcopy(dict(case)))
    subject_ids = [case["selector"]["subject_id"] for case in selected]
    if len(set(subject_ids)) != EXPECTED_SUBJECT_COUNT:
        raise ValueError("Memory-gate cases must resolve to three distinct subjects")
    selector_keys = (
        "phase_id",
        "program_id",
        "electrode_id",
        "frequency_group_id",
    )
    shared = {
        tuple(case["selector"][key] for key in selector_keys)
        for case in selected
    }
    if len(shared) != 1:
        raise ValueError("Memory-gate cases must share one non-subject selector")
    return tuple(selected)


def prepare_isolated_inputs(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    fixture_path: Path | str,
    work_root: Path | str,
    case_ids: Sequence[str],
) -> tuple[Path, Path, Path, tuple[dict[str, Any], ...]]:
    """Copy selected subjects without outputs/head models into a unique root."""

    study_path = Path(study_base_path).expanduser().resolve()
    model_path = Path(vta_model_path).expanduser().resolve()
    fixture_resolved = Path(fixture_path).expanduser().resolve()
    for path, label in (
        (study_path, "study base"),
        (model_path, "VTA model"),
        (fixture_resolved, "benchmark fixture"),
    ):
        if not path.is_file():
            raise ValueError(f"Missing {label}: {path}")
    raw = load_json_object(study_path, "study base")
    fixture = load_json_object(fixture_resolved, "benchmark fixture")
    cases = resolve_gate_cases(fixture, case_ids)
    source_subjects = {
        str(subject["subject_id"]): subject
        for subject in raw.get("study", {}).get("subjects", ())
    }
    root = Path(work_root).expanduser().resolve()
    protected_paths = [study_path, model_path, fixture_resolved]
    protected_paths.extend(
        Path(subject["subject_sources"]["leaddbs_subject_dir"])
        .expanduser()
        .resolve()
        for subject in source_subjects.values()
    )
    _assert_safe_work_root(root, protected_paths)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_root = root / f"vta_three_worker_memory_gate_{stamp}"
    run_root.mkdir()
    manifest_path = run_root / "gate_manifest.json"
    manifest = {
        "schema_version": "vta_three_worker_memory_gate_v1",
        "status": "preparing",
        "source_study_base": str(study_path),
        "source_vta_model": str(model_path),
        "source_fixture": str(fixture_resolved),
        "case_ids": list(case_ids),
        "selectors": [case["selector"] for case in cases],
        "workers": WORKER_COUNT,
        "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
        "expected_subject_count": EXPECTED_SUBJECT_COUNT,
        "expected_task_count": EXPECTED_TASK_COUNT,
        "expected_fem_solve_count": EXPECTED_FEM_SOLVE_COUNT,
    }
    _write_new_json(manifest_path, manifest)

    try:
        copied_study_path, copied_model_path = _populate_isolated_inputs(
            raw,
            source_subjects,
            cases,
            model_path,
            run_root,
        )
    except BaseException as error:
        _mark_manifest_failed(run_root, error, "preparation")
        raise
    manifest["status"] = "prepared"
    _replace_json(manifest_path, manifest)
    return run_root, copied_study_path, copied_model_path, cases


def _populate_isolated_inputs(
    raw: Mapping[str, Any],
    source_subjects: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    model_path: Path,
    run_root: Path,
) -> tuple[Path, Path]:
    selected_subjects = []
    copied_dataset = run_root / "copied_dataset"
    copied_derivative = copied_dataset / "derivatives" / "leaddbs"
    copied_derivative.mkdir(parents=True)

    dataset_description_copied = False
    derivative_description_copied = False
    for case in cases:
        subject_id = str(case["selector"]["subject_id"])
        source_subject = deepcopy(source_subjects.get(subject_id))
        if source_subject is None:
            raise ValueError(f"Study base is missing subject: {subject_id}")
        source_dir = Path(
            source_subject["subject_sources"]["leaddbs_subject_dir"]
        ).expanduser().resolve()
        reconstruction = Path(
            source_subject["subject_sources"]["electrode_reconstruction"]["path"]
        ).expanduser().resolve()
        dataset_root, derivative_root = _dataset_roots(source_dir)
        relative_reconstruction = reconstruction.relative_to(source_dir)
        destination = copied_derivative / source_dir.name
        if not dataset_description_copied:
            shutil.copy2(
                _require_file(dataset_root / "dataset_description.json"),
                copied_dataset / "dataset_description.json",
            )
            dataset_description_copied = True
        derivative_description = derivative_root / "dataset_description.json"
        if derivative_description.is_file() and not derivative_description_copied:
            shutil.copy2(
                derivative_description,
                copied_derivative / "dataset_description.json",
            )
            derivative_description_copied = True
        shutil.copytree(
            source_dir,
            destination,
            copy_function=shutil.copy2,
            ignore=_cold_subject_ignore,
        )
        source_subject["subject_sources"]["leaddbs_subject_dir"] = str(destination)
        source_subject["subject_sources"]["electrode_reconstruction"]["path"] = str(
            destination / relative_reconstruction
        )
        selected_subjects.append(source_subject)

    copied_study = deepcopy(raw)
    copied_study["study"]["subjects"] = selected_subjects
    copied_study_path = run_root / "study_base.json"
    _write_new_json(copied_study_path, copied_study)
    copied_model_path = run_root / "vta_model.yaml"
    shutil.copy2(model_path, copied_model_path)
    return copied_study_path, copied_model_path


def run_gate(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    work_root: Path | str,
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    case_ids: Sequence[str] = DEFAULT_CASE_IDS,
) -> dict[str, Any]:
    run_root, copied_study, copied_model, cases = prepare_isolated_inputs(
        study_base_path,
        vta_model_path,
        fixture_path,
        work_root,
        case_ids,
    )
    selector = cases[0]["selector"]
    selection = Selection(
        subject_ids=tuple(case["selector"]["subject_id"] for case in cases),
        phase_ids=(selector["phase_id"],),
        program_ids=(int(selector["program_id"]),),
        electrode_ids=(selector["electrode_id"],),
        frequency_group_ids=(selector["frequency_group_id"],),
    )
    try:
        prepared = prepare_plan(copied_study, copied_model, selection)
        if len(prepared.subjects) != EXPECTED_SUBJECT_COUNT:
            raise ValueError("Prepared memory gate did not resolve three subjects")
        if prepared.task_count != EXPECTED_TASK_COUNT:
            raise ValueError(
                f"Prepared memory gate resolved {prepared.task_count} tasks, "
                f"expected {EXPECTED_TASK_COUNT}"
            )
        planned_fem = sum(
            task.kind is not TaskKind.ALTERNATING_GROUP_PEAK
            for subject in prepared.subjects
            for task in subject.tasks
        )
        if planned_fem != EXPECTED_FEM_SOLVE_COUNT:
            raise ValueError(
                f"Prepared memory gate resolved {planned_fem} FEM tasks, "
                f"expected {EXPECTED_FEM_SOLVE_COUNT}"
            )
    except BaseException as error:
        _mark_manifest_failed(run_root, error, "planning")
        raise

    diagnostics_path = run_root / "diagnostics.log"
    diagnostics_lock = threading.Lock()

    def diagnostic_sink(line: str) -> None:
        with diagnostics_lock:
            with diagnostics_path.open("a", encoding="utf-8") as stream:
                stream.write(line)

    monitor = TrackingMemoryMonitor()
    bridge = RecordingBridge(
        MatlabBridge(
            repo_root=REPO_ROOT,
            memory_monitor=monitor,
            diagnostic_sink=diagnostic_sink,
        )
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    service = RunService(bridge, run_id=run_id, diagnostic_sink=diagnostic_sink)
    started = time.perf_counter()
    execution_error: BaseException | None = None
    summary = None
    try:
        summary = service.run(
            prepared.subjects,
            workers=WORKER_COUNT,
            resume=False,
            force=False,
        )
    except BaseException as error:
        execution_error = error
    finally:
        wall_seconds = time.perf_counter() - started
        memory = monitor.finish()
    if execution_error is not None:
        failure = {
            "schema_version": "vta_three_worker_memory_gate_summary_v1",
            "status": "failed",
            "run_root": str(run_root),
            "run_id": run_id,
            "workers": WORKER_COUNT,
            "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
            "wall_seconds": wall_seconds,
            "memory_observation": asdict(memory),
            "error_type": type(execution_error).__name__,
            "error_message": str(execution_error),
            "pass": False,
        }
        _write_new_json(run_root / "acceptance_summary.json", failure)
        _mark_manifest_failed(run_root, execution_error, "execution")
        raise execution_error
    assert summary is not None

    observations = sorted(bridge.observations, key=lambda item: item.subject_id)
    fem_solve_count = sum(
        timing.stage == "fem_pcg_solve" and timing.stage_status == "executed"
        for observation in observations
        for timing in observation.timings
    )
    outcomes = [
        {
            "subject_id": observation.subject_id,
            **asdict(outcome),
        }
        for observation in observations
        for outcome in observation.outcomes
    ]
    artifact_inventory = _artifact_inventory(prepared.subjects)
    diagnostics = (
        diagnostics_path.read_text(encoding="utf-8")
        if diagnostics_path.is_file()
        else ""
    )
    no_failure_text = not any(
        token in diagnostics.lower()
        for token in ("out of memory", "oom", "killed by signal", "segmentation")
    )
    gates = evaluate_gates(
        observation_count=len(observations),
        outcome_statuses=tuple(outcome["status"] for outcome in outcomes),
        fem_solve_count=fem_solve_count,
        run_summary=summary,
        memory=memory,
        sampled_live_roots=monitor.max_sampled_live_subject_roots,
        nested_matlab_descendants=monitor.max_nested_matlab_descendants,
        sample_interval_seconds=monitor.sample_interval_seconds,
        artifacts_complete=all(row["present"] for row in artifact_inventory),
        no_failure_text=no_failure_text,
    )
    passed = all(gates.values())
    result = {
        "schema_version": "vta_three_worker_memory_gate_summary_v1",
        "status": "passed" if passed else "failed",
        "run_root": str(run_root),
        "run_id": run_id,
        "workers": WORKER_COUNT,
        "sample_interval_seconds": monitor.sample_interval_seconds,
        "wall_seconds": wall_seconds,
        "planned_subject_count": EXPECTED_SUBJECT_COUNT,
        "planned_task_count": EXPECTED_TASK_COUNT,
        "planned_fem_solve_count": EXPECTED_FEM_SOLVE_COUNT,
        "actual_fem_solve_count": fem_solve_count,
        "run_summary": asdict(summary),
        "memory_observation": asdict(memory),
        "aggregate_rss_fraction": (
            memory.aggregate_peak_rss_bytes / memory.physical_memory_bytes
        ),
        "maximum_subject_rss_fraction": (
            max(memory.subject_peak_rss_bytes.values(), default=0)
            / memory.physical_memory_bytes
        ),
        "max_active_subject_roots": monitor.max_active_subject_roots,
        "max_sampled_live_subject_roots": (
            monitor.max_sampled_live_subject_roots
        ),
        "max_nested_matlab_descendants": monitor.max_nested_matlab_descendants,
        "gates": gates,
        "pass": passed,
    }
    _write_new_json(run_root / "process_lifecycle.json", monitor.lifecycle)
    _write_new_json(run_root / "task_outcomes.json", outcomes)
    _write_new_json(run_root / "artifact_inventory.json", artifact_inventory)
    _write_new_json(run_root / "acceptance_summary.json", result)
    manifest = load_json_object(run_root / "gate_manifest.json", "gate manifest")
    manifest["status"] = result["status"]
    manifest["acceptance_summary"] = "acceptance_summary.json"
    _replace_json(run_root / "gate_manifest.json", manifest)
    if not passed:
        raise RuntimeError(f"Three-worker memory gate failed: {run_root}")
    return result


def evaluate_gates(
    *,
    observation_count: int,
    outcome_statuses: Sequence[str],
    fem_solve_count: int,
    run_summary,
    memory,
    sampled_live_roots: int,
    nested_matlab_descendants: int,
    sample_interval_seconds: float,
    artifacts_complete: bool,
    no_failure_text: bool,
) -> dict[str, bool]:
    """Evaluate the fixed three-worker acceptance contract."""

    aggregate_limit = 0.75 * memory.physical_memory_bytes
    subject_limit = 0.50 * memory.physical_memory_bytes
    return {
        "subject_count": observation_count == EXPECTED_SUBJECT_COUNT,
        "task_count": len(outcome_statuses) == EXPECTED_TASK_COUNT,
        "fem_solve_count": fem_solve_count == EXPECTED_FEM_SOLVE_COUNT,
        "all_tasks_generated": len(outcome_statuses) == EXPECTED_TASK_COUNT
        and all(status == "generated" for status in outcome_statuses),
        "run_summary_clean": run_summary.failed == 0
        and run_summary.skipped_dependency == 0
        and run_summary.subject_process_failed == 0,
        "three_live_roots_sampled": sampled_live_roots == WORKER_COUNT,
        "no_nested_matlab_roots": nested_matlab_descendants == 0,
        "aggregate_rss_within_limit": memory.aggregate_peak_rss_bytes
        <= aggregate_limit,
        "subject_rss_within_limit": bool(memory.subject_peak_rss_bytes)
        and max(memory.subject_peak_rss_bytes.values()) <= subject_limit,
        "sample_interval_is_100_ms": sample_interval_seconds
        == SAMPLE_INTERVAL_SECONDS,
        "memory_samples_present": memory.sample_count > 0,
        "artifacts_complete": artifacts_complete,
        "no_oom_or_signal_text": no_failure_text,
    }


def _artifact_inventory(subjects) -> list[dict[str, Any]]:
    rows = []
    for subject in subjects:
        for task in subject.tasks:
            for space in task.model.spaces:
                leaf = leaf_directory(task, space)
                for artifact in expected_artifacts(
                    leaf, task.model.thresholds_v_per_m
                ):
                    rows.append(
                        {
                            "subject_id": subject.subject_id,
                            "task_id": task.task_id,
                            "space": space,
                            "path": str(artifact),
                            "present": artifact.is_file(),
                        }
                    )
    return rows


def _cold_subject_ignore(path: str, names: list[str]) -> set[str]:
    del path
    return {name for name in names if name in {"headmodel", "stimulations"}}


def _dataset_roots(subject_dir: Path) -> tuple[Path, Path]:
    parts = subject_dir.parts
    marker = ("derivatives", "leaddbs")
    matches = [
        index
        for index in range(len(parts) - 1)
        if tuple(parts[index : index + 2]) == marker
    ]
    if len(matches) != 1:
        raise ValueError(f"Subject is not under derivatives/leaddbs: {subject_dir}")
    index = matches[0]
    dataset_root = Path(*parts[:index])
    return dataset_root, dataset_root / "derivatives" / "leaddbs"


def _assert_safe_work_root(root: Path, protected_paths: Sequence[Path]) -> None:
    allowed = ALLOWED_VALIDATION_ROOT.resolve()
    if root != allowed and allowed not in root.parents:
        raise ValueError(
            f"Memory gate work root must be inside {allowed}: {root}"
        )
    for protected in protected_paths:
        resolved = Path(protected).expanduser().resolve()
        if _paths_overlap(root, resolved):
            raise ValueError(
                f"Memory gate work root overlaps authoritative input: {resolved}"
            )


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first in second.parents
        or second in first.parents
    )


def _mark_manifest_failed(
    run_root: Path,
    error: BaseException,
    failure_phase: str,
) -> None:
    manifest_path = run_root / "gate_manifest.json"
    if not manifest_path.is_file():
        return
    manifest = load_json_object(manifest_path, "gate manifest")
    manifest.update(
        {
            "status": "failed",
            "failure_phase": failure_phase,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    )
    _replace_json(manifest_path, manifest)


def _require_file(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"Required file does not exist: {path}")
    return path


def _write_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite JSON output: {path}")
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _replace_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-base", required=True)
    parser.add_argument("--vta-model", required=True)
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--case", action="append", dest="case_ids")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_gate(
        args.study_base,
        args.vta_model,
        args.work_root,
        fixture_path=args.fixture,
        case_ids=tuple(args.case_ids or DEFAULT_CASE_IDS),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
