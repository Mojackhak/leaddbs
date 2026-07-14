#!/usr/bin/env python3
"""Prepare and run the frozen canonical VTA performance baseline."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import threading
import time
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from my_helper.fiber.core.vta_pipeline.artifacts import (  # noqa: E402
    atomic_copy_missing,
    expected_artifacts,
    leaf_status,
    missing_artifacts,
    move_leaf_to_trash,
    threshold_filename,
)
from my_helper.fiber.core.vta_pipeline.config import load_vta_model  # noqa: E402
from my_helper.fiber.core.vta_pipeline.matlab_bridge import (  # noqa: E402
    MatlabBridge,
    TaskRunContext,
)
from my_helper.fiber.core.vta_pipeline.paths import (  # noqa: E402
    canonical_head_model_path,
    leaf_directory,
)
from my_helper.fiber.core.vta_pipeline.planner import (  # noqa: E402
    Selection,
    SubjectPlan,
    TaskKind,
    VtaTask,
    build_plan,
    equivalent_task_key,
)
from my_helper.fiber.core.vta_pipeline.process_monitor import (  # noqa: E402
    ProcessTreeMemoryMonitor,
)
from my_helper.fiber.core.vta_pipeline.service import (  # noqa: E402
    RunSummary,
    RunService,
    prepare_plan,
)
from my_helper.fiber.core.vta_pipeline.study_base import (  # noqa: E402
    load_study_base,
)


SCHEMA_VERSION = "vta_performance_benchmark_v1"
FIXTURE_PATH = Path(__file__).with_name("fixtures") / f"{SCHEMA_VERSION}.json"
AUTHORITATIVE_LEADDBS_ROOT = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs")
WORKER_COUNT = 3
COUNT_KEYS = (
    "matlab_process_count",
    "fem_solve_count",
    "derived_task_count",
    "copy_count",
    "skip_count",
)
EXPECTED_PAIR_ORDER = (
    ("baseline", "candidate"),
    ("candidate", "baseline"),
    ("baseline", "candidate"),
    ("candidate", "baseline"),
    ("baseline", "candidate"),
)
REPRESENTATIVE_CASE_ID = "snr003_t2_p2_l_alternating"
REPRESENTATIVE_PAIR_ORDER = (
    ("compatibility_per_task", "persistent_subject"),
    ("persistent_subject", "compatibility_per_task"),
    ("compatibility_per_task", "persistent_subject"),
)
EXECUTION_PATHS = ("compatibility_per_task", "persistent_subject")
REPRESENTATIVE_FEM_LIMIT = 16
CURRENT_PAYLOAD = {
    "case_id": "R_single_cathode_case_return",
    "hemisphere": "R",
    "design": "single_cathode_case_return",
    "control_mode": "current",
    "unit": "mA",
    "amplitude_mA": 4.7761121690289734,
    "pulse_width_us": 90,
    "frequency_hz": 130,
    "contacts": [
        {"contact": 4, "polarity": "cathode", "fraction": 1.0},
        {"contact": "case", "polarity": "anode", "fraction": 1.0},
    ],
}


CommandRunner = Callable[[Sequence[str]], Any]
ArtifactComparator = Callable[
    [Path, Path, Mapping[str, Any], Sequence[str]], Mapping[str, Any]
]


class _BenchmarkAttemptFailure(RuntimeError):
    """Carry a persisted failed attempt record back to the paired state machine."""

    def __init__(self, record: Mapping[str, Any], cause: BaseException) -> None:
        super().__init__(str(cause))
        self.record = dict(record)
        self.cause = cause


def load_fixture(path: Path | str = FIXTURE_PATH) -> dict[str, Any]:
    """Load and structurally validate the frozen benchmark fixture."""

    fixture_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read benchmark fixture: {fixture_path}") from exc
    validate_fixture_document(raw)
    return raw


def validate_fixture_document(fixture: Mapping[str, Any]) -> None:
    """Validate fields whose values define the frozen benchmark contract."""

    if fixture.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Fixture schema_version must be {SCHEMA_VERSION}")
    if fixture.get("spaces") != ["native", "MNI152NLin2009bAsym"]:
        raise ValueError("Fixture spaces must contain canonical native and MNI")
    if fixture.get("thresholds_v_per_m") != [180, 200, 220]:
        raise ValueError("Fixture thresholds must be exactly 180, 200, and 220 V/m")
    if fixture.get("workers") != WORKER_COUNT:
        raise ValueError("Fixture worker count must be exactly three")
    if fixture.get("warmup_runs_per_path") != 1:
        raise ValueError("Fixture must define one warm-up per execution path")
    if paired_order_schedule(fixture) != EXPECTED_PAIR_ORDER:
        raise ValueError("Fixture measured pair order does not match the frozen order")

    payloads = _mapping(fixture.get("payloads"), "payloads")
    if payloads.get("current_single_cathode_case_return") != CURRENT_PAYLOAD:
        raise ValueError("Current-control payload does not match the frozen case")
    _validate_synthetic_payload(
        _mapping(
            payloads.get("synthetic_continuous_multi_source"),
            "synthetic_continuous_multi_source payload",
        )
    )

    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Fixture cases must be a non-empty list")
    case_ids: set[str] = set()
    for case in cases:
        case_map = _mapping(case, "benchmark case")
        case_id = _nonempty_string(case_map.get("case_id"), "case_id")
        if case_id in case_ids:
            raise ValueError(f"Duplicate benchmark case_id: {case_id}")
        case_ids.add(case_id)
        selector = _mapping(case_map.get("selector"), f"selector for {case_id}")
        _validate_selector(selector, case_id)
        tasks = case_map.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"Case {case_id} must define at least one task selector")
        task_keys: set[tuple[str, tuple[str, ...]]] = set()
        for task in tasks:
            task_map = _mapping(task, f"task selector for {case_id}")
            kind = _nonempty_string(task_map.get("task_kind"), "task_kind")
            if kind not in {item.value for item in TaskKind}:
                raise ValueError(f"Unsupported task_kind in case {case_id}: {kind}")
            source_ids = task_map.get("source_ids")
            if (
                not isinstance(source_ids, list)
                or not source_ids
                or any(not isinstance(item, str) or not item for item in source_ids)
            ):
                raise ValueError(f"Invalid source_ids in case {case_id}")
            task_key = (kind, tuple(source_ids))
            if task_key in task_keys:
                raise ValueError(f"Duplicate task selector in case {case_id}")
            task_keys.add(task_key)

        if case_map.get("headmodel_state") not in {"cold", "warm"}:
            raise ValueError(f"Invalid headmodel_state in case {case_id}")
        if case_map.get("initial_artifacts") not in {
            "missing",
            "threshold_repair",
            "complete",
        }:
            raise ValueError(f"Invalid initial_artifacts in case {case_id}")
        payload_id = case_map.get("payload_id")
        if payload_id is not None and payload_id not in payloads:
            raise ValueError(f"Unknown payload_id in case {case_id}: {payload_id}")
        expected = _mapping(
            case_map.get("expected_counts"), f"expected_counts for {case_id}"
        )
        for path_name in ("baseline", "candidate"):
            assert_expected_counts(
                _mapping(expected.get(path_name), f"{path_name} counts for {case_id}"),
                _mapping(expected.get(path_name), f"{path_name} counts for {case_id}"),
            )


def validate_benchmark_inputs(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    *,
    fixture_path: Path | str = FIXTURE_PATH,
) -> dict[str, Any]:
    """Validate inputs and prove every semantic task selector is unique."""

    fixture = load_fixture(fixture_path)
    study_path = Path(study_base_path).expanduser().resolve()
    model_path = Path(vta_model_path).expanduser().resolve()
    load_study_base(study_path)
    model = load_vta_model(model_path)
    if list(model.spaces) != fixture["spaces"]:
        raise ValueError("VTA model spaces do not match the benchmark fixture")
    if list(model.thresholds_v_per_m) != fixture["thresholds_v_per_m"]:
        raise ValueError("VTA model thresholds do not match the benchmark fixture")

    raw = _read_json_object(study_path, "study base")
    materialized = deepcopy(raw)
    _materialize_payloads(materialized, fixture)
    inventory = _semantic_task_inventory(materialized)
    resolved: dict[str, list[dict[str, Any]]] = {}
    for case in fixture["cases"]:
        case_matches: list[dict[str, Any]] = []
        for task_selector in case["tasks"]:
            matches = [
                task
                for task in inventory
                if _semantic_task_matches(task, case["selector"], task_selector)
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Case {case['case_id']} task selector must resolve exactly once; "
                    f"resolved {len(matches)} times"
                )
            case_matches.append(matches[0])
        resolved[case["case_id"]] = case_matches
    return {"fixture": fixture, "semantic_tasks": resolved}


def paired_order_schedule(
    fixture: Mapping[str, Any] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return the reusable five-pair baseline/candidate order."""

    if fixture is None:
        return EXPECTED_PAIR_ORDER
    raw = fixture.get("measured_pair_order")
    if not isinstance(raw, list):
        raise ValueError("measured_pair_order must be a list")
    try:
        return tuple((str(pair[0]), str(pair[1])) for pair in raw)
    except (IndexError, TypeError) as exc:
        raise ValueError("Each measured pair must contain two paths") from exc


def resolve_case_tasks(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    case: Mapping[str, Any],
) -> tuple[VtaTask, ...]:
    """Resolve absolute-path-dependent task IDs for one semantic case."""

    plan = _resolve_case_subject_plan(study_base_path, vta_model_path, case)
    candidates = plan.tasks
    resolved: list[VtaTask] = []
    for task_selector in case["tasks"]:
        matches = [
            task
            for task in candidates
            if task.kind.value == task_selector["task_kind"]
            and [source.source_id for source in task.sources]
            == task_selector["source_ids"]
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Case {case['case_id']} task selector must resolve exactly once; "
                f"resolved {len(matches)} times"
            )
        resolved.append(matches[0])
    return tuple(resolved)


def _resolve_case_subject_plan(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    case: Mapping[str, Any],
) -> SubjectPlan:
    selector = case["selector"]
    study = load_study_base(study_base_path)
    model = load_vta_model(vta_model_path)
    plans = build_plan(
        study,
        model,
        Selection(
            subject_ids=(selector["subject_id"],),
            phase_ids=(selector["phase_id"],),
            program_ids=(selector["program_id"],),
            electrode_ids=(selector["electrode_id"],),
            frequency_group_ids=(selector["frequency_group_id"],),
        ),
    )
    if len(plans) != 1:
        raise ValueError(
            f"Case {case['case_id']} must resolve exactly one subject plan"
        )
    return plans[0]


def prepare_benchmark(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    work_root: Path | str,
    *,
    fixture_path: Path | str = FIXTURE_PATH,
    now: Callable[[], datetime] | None = None,
    trash_root: Path | str | None = None,
) -> Path:
    """Create isolated frozen snapshots and return the benchmark root."""

    validated = validate_benchmark_inputs(
        study_base_path, vta_model_path, fixture_path=fixture_path
    )
    fixture = validated["fixture"]
    study_path = Path(study_base_path).expanduser().resolve()
    model_path = Path(vta_model_path).expanduser().resolve()
    raw = _read_json_object(study_path, "study base")
    validation_root = Path(work_root).expanduser().resolve()
    _reject_unsafe_work_root(validation_root, raw, study_path.parent)

    clock = now or (lambda: datetime.now(timezone.utc))
    stamp = clock().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    benchmark_root = validation_root / f"vta_performance_benchmark_{stamp}"
    _move_conflict_to_trash(benchmark_root, trash_root=trash_root)
    for directory in (
        benchmark_root / "frozen_input",
        benchmark_root / "working" / "baseline",
        benchmark_root / "working" / "candidate",
        benchmark_root / "runs",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    resolved_cases: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        manifest = _prepare_case_snapshot(
            raw,
            study_path,
            model_path,
            fixture,
            case,
            benchmark_root / "frozen_input" / case["case_id"],
        )
        resolved_case = deepcopy(case)
        resolved_case["resolved_task_ids"] = manifest["resolved_task_ids"]
        resolved_case["snapshot"] = str(
            Path("frozen_input") / case["case_id"]
        )
        resolved_cases.append(resolved_case)

    resolved_fixture = deepcopy(fixture)
    resolved_fixture["source_fixture"] = str(Path(fixture_path).expanduser().resolve())
    resolved_fixture["source_study_base"] = str(study_path)
    resolved_fixture["source_vta_model"] = str(model_path)
    resolved_fixture["protected_roots"] = [
        str(path)
        for path in sorted(
            _authoritative_roots(raw, study_path.parent),
            key=str,
        )
    ]
    resolved_fixture["cases"] = resolved_cases
    _publish_json(
        benchmark_root / "fixture.json",
        resolved_fixture,
        trash_root=trash_root,
    )
    _publish_json(
        benchmark_root / "benchmark_summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": "prepared",
            "candidate_binding": "deferred",
            "benchmark_root": str(benchmark_root),
        },
        trash_root=trash_root,
    )
    return benchmark_root


def restore_snapshot(
    frozen_snapshot: Path | str,
    destination: Path | str,
    *,
    trash_root: Path | str | None = None,
    protected_roots: Sequence[Path | str] = (),
) -> Path:
    """Replace a working case with an exact copy of its frozen snapshot."""

    source = Path(frozen_snapshot).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Frozen snapshot does not exist: {source}")
    if (
        source == target
        or _is_within(source, target)
        or _is_within(target, source)
    ):
        raise ValueError("Frozen snapshot and restore destination must be disjoint")
    _reject_protected_path(
        target,
        (AUTHORITATIVE_LEADDBS_ROOT, *protected_roots),
    )
    _move_conflict_to_trash(target, trash_root=trash_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, copy_function=_clone_or_copy)
    _verify_restored_artifact_state(target)
    return target


def build_baseline_command(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    selector: Mapping[str, Any],
    *,
    python_executable: str = sys.executable,
) -> tuple[str, ...]:
    """Build one compatibility-path command with the frozen worker count."""

    command = [
        python_executable,
        "-c",
        (
            "from my_helper.vta.test.run_vta_performance_benchmark "
            "import _case_runner_main; raise SystemExit(_case_runner_main())"
        ),
        "--study-base",
        str(Path(study_base_path).resolve()),
        "--vta-model",
        str(Path(vta_model_path).resolve()),
        "--subject",
        str(selector["subject_id"]),
        "--phase",
        str(selector["phase_id"]),
        "--program",
        str(selector["program_id"]),
        "--electrode",
        str(selector["electrode_id"]),
        "--frequency-group",
        str(selector["frequency_group_id"]),
        "--workers",
        str(WORKER_COUNT),
    ]
    return tuple(command)


def build_case_command(
    study_base_path: Path | str,
    vta_model_path: Path | str,
    selector: Mapping[str, Any],
    *,
    execution_path: str,
    python_executable: str = sys.executable,
) -> tuple[str, ...]:
    """Build one isolated benchmark case command for an explicit path."""

    if execution_path not in EXECUTION_PATHS:
        raise ValueError(f"Unsupported benchmark execution path: {execution_path}")
    command = list(
        build_baseline_command(
            study_base_path,
            vta_model_path,
            selector,
            python_executable=python_executable,
        )
    )
    command.extend(("--execution-path", execution_path))
    return tuple(command)


def assert_expected_counts(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    """Require exact process, solve, derived, copy, and skip counts."""

    if set(actual) != set(COUNT_KEYS) or set(expected) != set(COUNT_KEYS):
        raise ValueError(f"Execution counts must contain exactly {COUNT_KEYS}")
    for key in COUNT_KEYS:
        actual_value = actual[key]
        expected_value = expected[key]
        if (
            not isinstance(actual_value, int)
            or isinstance(actual_value, bool)
            or actual_value < 0
            or not isinstance(expected_value, int)
            or isinstance(expected_value, bool)
            or expected_value < 0
        ):
            raise ValueError(f"Execution count {key} must be a nonnegative integer")
        if actual_value != expected_value:
            raise ValueError(
                f"Execution count mismatch for {key}: "
                f"expected {expected_value}, observed {actual_value}"
            )


def run_baseline(
    benchmark_root: Path | str,
    *,
    command_runner: CommandRunner | None = None,
    trash_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run one warm-up and five measured compatibility-path repetitions."""

    root = Path(benchmark_root).expanduser().resolve()
    fixture = _read_json_object(root / "fixture.json", "resolved fixture")
    if fixture.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Resolved benchmark fixture has an invalid schema")
    protected_roots = tuple(
        Path(path).expanduser().resolve()
        for path in fixture.get("protected_roots", ())
    )
    _reject_protected_path(root, (AUTHORITATIVE_LEADDBS_ROOT, *protected_roots))
    runner = command_runner or _run_subprocess
    records: list[dict[str, Any]] = []

    warmup = _run_suite(
        root,
        fixture,
        run_label="warmup-baseline",
        repetition_index=None,
        command_runner=runner,
        trash_root=trash_root,
    )
    records.extend(warmup["cases"])

    measured_suites: list[dict[str, Any]] = []
    for repetition_index in range(1, len(paired_order_schedule(fixture)) + 1):
        suite = _run_suite(
            root,
            fixture,
            run_label=f"repetition-{repetition_index:02d}-baseline",
            repetition_index=repetition_index,
            command_runner=runner,
            trash_root=trash_root,
        )
        measured_suites.append(suite)
        records.extend(suite["cases"])

    measured_wall_times = [suite["wall_seconds"] for suite in measured_suites]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "baseline_complete",
        "candidate_binding": "deferred",
        "workers_requested": WORKER_COUNT,
        "concurrency_measurement": "not_measured_single_subject_cases",
        "future_paired_order_status": "not_executed_candidate_deferred",
        "future_paired_order": [
            list(pair) for pair in paired_order_schedule(fixture)
        ],
        "warmup": warmup,
        "measured": measured_suites,
        "baseline_median_wall_seconds": statistics.median(measured_wall_times),
        "case_run_count": len(records),
    }
    _publish_json(
        root / "benchmark_summary.json",
        summary,
        trash_root=trash_root,
    )
    return summary


def run_paired(
    benchmark_root: Path | str,
    case_id: str,
    *,
    command_runner: CommandRunner | None = None,
    artifact_comparator: ArtifactComparator | None = None,
    trash_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run the bounded representative compatibility/candidate comparison."""

    root = Path(benchmark_root).expanduser().resolve()
    fixture = _read_json_object(root / "fixture.json", "resolved fixture")
    if fixture.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Resolved benchmark fixture has an invalid schema")
    if case_id != REPRESENTATIVE_CASE_ID:
        raise ValueError(
            "The paired real-FEM gate only permits the documented "
            f"representative case: {REPRESENTATIVE_CASE_ID}"
        )
    matches = [
        case
        for case in fixture.get("cases", ())
        if case.get("case_id") == case_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Representative case must resolve exactly once: {case_id}")
    case = matches[0]
    protected_roots = tuple(
        Path(path).expanduser().resolve()
        for path in fixture.get("protected_roots", ())
    )
    _reject_protected_path(root, (AUTHORITATIVE_LEADDBS_ROOT, *protected_roots))
    _claim_paired_root(root)
    runner = command_runner or _run_subprocess
    comparator = artifact_comparator or compare_case_outputs
    records: list[dict[str, Any]] = []
    fem_count = 0
    warmups: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    _publish_paired_state(
        root,
        status="paired_in_progress",
        case_id=case_id,
        records=records,
        fem_count=fem_count,
        trash_root=trash_root,
    )
    try:
        for execution_path in EXECUTION_PATHS:
            record = _run_paired_path(
                root,
                fixture,
                case,
                execution_path=execution_path,
                run_label=f"warmup-{execution_path}",
                repetition_index=None,
                command_runner=runner,
                trash_root=trash_root,
            )
            warmups.append(record)
            records.append(record)
            fem_count += record["counts"]["fem_solve_count"]
            _assert_representative_fem_bound(fem_count)
            _publish_paired_state(
                root,
                status="paired_in_progress",
                case_id=case_id,
                records=records,
                fem_count=fem_count,
                trash_root=trash_root,
            )

        for repetition_index, order in enumerate(
            REPRESENTATIVE_PAIR_ORDER, start=1
        ):
            by_path: dict[str, dict[str, Any]] = {}
            for order_index, execution_path in enumerate(order, start=1):
                record = _run_paired_path(
                    root,
                    fixture,
                    case,
                    execution_path=execution_path,
                    run_label=(
                        f"pair-{repetition_index:02d}-order-{order_index}-"
                        f"{execution_path}"
                    ),
                    repetition_index=repetition_index,
                    command_runner=runner,
                    trash_root=trash_root,
                )
                by_path[execution_path] = record
                records.append(record)
                fem_count += record["counts"]["fem_solve_count"]
                _assert_representative_fem_bound(fem_count)
                _publish_paired_state(
                    root,
                    status="paired_in_progress",
                    case_id=case_id,
                    records=records,
                    fem_count=fem_count,
                    trash_root=trash_root,
                )
            try:
                comparison = dict(
                    comparator(
                        Path(
                            by_path["compatibility_per_task"]["working_root"]
                        ),
                        Path(by_path["persistent_subject"]["working_root"]),
                        case,
                        tuple(fixture["spaces"]),
                    )
                )
                if comparison.get("pass") is not True:
                    raise ValueError(
                        "Numerical artifact comparison failed for pair "
                        f"{repetition_index}"
                    )
                pair = {
                    "status": "completed",
                    "repetition_index": repetition_index,
                    "order": list(order),
                    "runs": by_path,
                    "artifact_comparison": comparison,
                }
            except BaseException as error:
                pair = {
                    "status": "failed",
                    "repetition_index": repetition_index,
                    "order": list(order),
                    "runs": by_path,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                _publish_json(
                    root
                    / "runs"
                    / f"pair-{repetition_index:02d}-comparison.json",
                    pair,
                    trash_root=trash_root,
                )
                raise
            _publish_json(
                root / "runs" / f"pair-{repetition_index:02d}-comparison.json",
                pair,
                trash_root=trash_root,
            )
            pairs.append(pair)
    except _BenchmarkAttemptFailure as failure:
        failed_record = failure.record
        records.append(failed_record)
        fem_count += _failed_attempt_fem_charge(failed_record, case)
        _publish_paired_state(
            root,
            status="paired_failed",
            case_id=case_id,
            records=records,
            fem_count=fem_count,
            trash_root=trash_root,
            error=failure.cause,
        )
        _assert_representative_fem_bound(fem_count)
        raise failure.cause
    except BaseException as error:
        _publish_paired_state(
            root,
            status="paired_failed",
            case_id=case_id,
            records=records,
            fem_count=fem_count,
            trash_root=trash_root,
            error=error,
        )
        raise

    medians = {
        execution_path: statistics.median(
            record["wall_seconds"]
            for record in records
            if record["repetition_index"] is not None
            and record["path"] == execution_path
        )
        for execution_path in EXECUTION_PATHS
    }
    ratio = medians["persistent_subject"] / medians["compatibility_per_task"]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "paired_complete",
        "candidate_binding": "persistent_subject",
        "case_id": case_id,
        "warmups": warmups,
        "measured_pairs": pairs,
        "completed_fem_solve_count": fem_count,
        "completed_fem_solve_limit": REPRESENTATIVE_FEM_LIMIT,
        "median_wall_seconds": medians,
        "persistent_to_compatibility_ratio": ratio,
        "representative_25_percent_target_pass": ratio <= 0.75,
        "numerical_gate_pass": True,
        "three_worker_memory_gate": "not_measured",
    }
    _publish_json(root / "benchmark_summary.json", summary, trash_root=trash_root)
    return summary


def _claim_paired_root(root: Path) -> None:
    prior_summary = _read_json_object(
        root / "benchmark_summary.json", "benchmark summary"
    )
    if prior_summary.get("status") != "prepared":
        raise ValueError(
            "A paired benchmark root is single-use and must be in prepared state"
        )
    claim = root / ".paired_gate_claim"
    try:
        claim.mkdir()
    except FileExistsError as error:
        raise ValueError("The paired benchmark root is already claimed") from error
    current_summary = _read_json_object(
        root / "benchmark_summary.json", "benchmark summary"
    )
    if current_summary.get("status") != "prepared":
        raise ValueError("The paired benchmark root changed while being claimed")
    _write_new_json(
        claim / "claim.json",
        {
            "schema_version": SCHEMA_VERSION,
            "pid": os.getpid(),
            "claimed_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def _failed_attempt_fem_charge(
    record: dict[str, Any], case: Mapping[str, Any]
) -> int:
    counts = record.get("counts")
    if isinstance(counts, Mapping):
        value = counts.get("fem_solve_count")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            record["fem_count_accounting"] = "observed"
            return value
    expected_key = (
        "baseline"
        if record.get("path") == "compatibility_per_task"
        else "candidate"
    )
    expected = _mapping(
        _mapping(case.get("expected_counts"), "expected counts").get(expected_key),
        f"{expected_key} expected counts",
    )
    value = expected.get("fem_solve_count")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Representative expected FEM count is invalid")
    record["fem_count_accounting"] = (
        "conservative_expected_due_to_missing_or_malformed_observed_count"
    )
    return value


def _publish_paired_state(
    root: Path,
    *,
    status: str,
    case_id: str,
    records: Sequence[Mapping[str, Any]],
    fem_count: int,
    trash_root: Path | str | None,
    error: BaseException | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "candidate_binding": "persistent_subject",
        "case_id": case_id,
        "completed_fem_solve_count": fem_count,
        "completed_fem_solve_limit": REPRESENTATIVE_FEM_LIMIT,
        "execution_records": list(records),
        "three_worker_memory_gate": "not_measured",
    }
    if error is not None:
        payload.update(
            {"error_type": type(error).__name__, "error": str(error)}
        )
    _publish_json(root / "benchmark_summary.json", payload, trash_root=trash_root)


def _run_paired_path(
    root: Path,
    fixture: Mapping[str, Any],
    case: Mapping[str, Any],
    *,
    execution_path: str,
    run_label: str,
    repetition_index: int | None,
    command_runner: CommandRunner,
    trash_root: Path | str | None,
) -> dict[str, Any]:
    run_directory = root / "runs" / run_label
    _move_conflict_to_trash(run_directory, trash_root=trash_root)
    run_directory.mkdir(parents=True)
    working = root / "working" / run_label / execution_path / str(case["case_id"])
    record: dict[str, Any] = {
        "case_id": case["case_id"],
        "path": execution_path,
        "run_label": run_label,
        "repetition_index": repetition_index,
        "working_root": str(working),
        "status": "in_progress",
    }
    record_path = run_directory / f"{case['case_id']}.json"
    _publish_json(record_path, record, trash_root=trash_root)
    started = time.perf_counter()
    try:
        working = restore_snapshot(
            root / str(case["snapshot"]),
            working,
            trash_root=trash_root,
            protected_roots=fixture.get("protected_roots", ()),
        )
        command = build_case_command(
            working / "study_base.json",
            working / "vta_model.yaml",
            _mapping(case.get("selector"), "representative selector"),
            execution_path=execution_path,
        )
        record["command"] = list(command)
        _publish_json(record_path, record, trash_root=trash_root)
        result = command_runner(command)
        returncode, stdout, stderr, supplied_counts = _command_result(result)
        record.update(
            {
                "returncode": returncode,
                "stderr": stderr,
                "stdout": stdout,
            }
        )
        run_summary: Mapping[str, Any] | None = None
        try:
            run_summary = _parse_run_summary(stdout)
        except ValueError:
            if returncode == 0:
                raise
        if run_summary is not None:
            reported_counts = run_summary.get("benchmark_counts")
            if supplied_counts is not None:
                counts = supplied_counts
            elif isinstance(reported_counts, Mapping):
                counts = dict(reported_counts)
            else:
                counts = None
            record.update(
                {
                    "run_summary": dict(run_summary),
                    "process_observations": run_summary.get(
                        "process_observations", []
                    ),
                    "memory_observation": run_summary.get(
                        "memory_observation"
                    ),
                    "artifact_inventory": run_summary.get(
                        "artifact_inventory", []
                    ),
                }
            )
            if counts is not None:
                record["counts"] = counts
        if returncode != 0:
            raise RuntimeError(
                f"{execution_path} failed for {case['case_id']} with return code "
                f"{returncode}: {stderr.strip()}"
            )
        if run_summary is None:
            raise ValueError(f"{execution_path} emitted no JSON run summary")
        if run_summary.get("failed", 0) or run_summary.get(
            "skipped_dependency", 0
        ):
            raise RuntimeError(f"{execution_path} reported a task failure")
        counts = record.get("counts")
        if not isinstance(counts, Mapping):
            raise ValueError(
                f"{execution_path} emitted no observed execution counts"
            )
        expected_key = (
            "baseline"
            if execution_path == "compatibility_per_task"
            else "candidate"
        )
        assert_expected_counts(counts, case["expected_counts"][expected_key])
        record.update(
            {
                "status": "completed",
            }
        )
    except BaseException as error:
        record.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        record["wall_seconds"] = time.perf_counter() - started
        _publish_json(record_path, record, trash_root=trash_root)
        raise _BenchmarkAttemptFailure(record, error) from error
    record["wall_seconds"] = time.perf_counter() - started
    _publish_json(
        record_path,
        record,
        trash_root=trash_root,
    )
    return record


def _assert_representative_fem_bound(completed_count: int) -> None:
    if completed_count > REPRESENTATIVE_FEM_LIMIT:
        raise ValueError(
            "Representative benchmark exceeded the approved completed FEM "
            f"limit: {completed_count} > {REPRESENTATIVE_FEM_LIMIT}"
        )


def _run_suite(
    root: Path,
    fixture: Mapping[str, Any],
    *,
    run_label: str,
    repetition_index: int | None,
    command_runner: CommandRunner,
    trash_root: Path | str | None,
) -> dict[str, Any]:
    suite_started = time.perf_counter()
    case_records: list[dict[str, Any]] = []
    run_directory = root / "runs" / run_label
    _move_conflict_to_trash(run_directory, trash_root=trash_root)
    run_directory.mkdir(parents=True)
    for case in fixture["cases"]:
        case_id = case["case_id"]
        working = restore_snapshot(
            root / case["snapshot"],
            root / "working" / "baseline" / case_id,
            trash_root=trash_root,
            protected_roots=fixture.get("protected_roots", ()),
        )
        command = build_baseline_command(
            working / "study_base.json",
            working / "vta_model.yaml",
            case["selector"],
        )
        started = time.perf_counter()
        result = command_runner(command)
        wall_seconds = time.perf_counter() - started
        returncode, stdout, stderr, supplied_counts = _command_result(result)
        if returncode != 0:
            raise RuntimeError(
                f"Baseline command failed for {case_id} with return code "
                f"{returncode}: {stderr.strip()}"
            )
        run_summary = _parse_run_summary(stdout)
        if run_summary.get("failed", 0) or run_summary.get("skipped_dependency", 0):
            raise RuntimeError(f"Baseline task failure reported for case {case_id}")
        reported_counts = run_summary.get("benchmark_counts")
        if supplied_counts is not None:
            actual_counts = supplied_counts
        elif isinstance(reported_counts, Mapping):
            actual_counts = dict(reported_counts)
        else:
            raise ValueError(
                f"Baseline command emitted no observed execution counts for {case_id}"
            )
        assert_expected_counts(
            actual_counts,
            case["expected_counts"]["baseline"],
        )
        record = {
            "case_id": case_id,
            "path": "baseline",
            "run_label": run_label,
            "repetition_index": repetition_index,
            "wall_seconds": wall_seconds,
            "command": list(command),
            "counts": actual_counts,
            "run_summary": run_summary,
            "process_observations": run_summary.get("process_observations", []),
            "memory_observation": run_summary.get("memory_observation"),
            "artifact_inventory": run_summary.get("artifact_inventory", []),
        }
        _publish_json(
            run_directory / f"{case_id}.json",
            record,
            trash_root=trash_root,
        )
        case_records.append(record)
    return {
        "run_label": run_label,
        "repetition_index": repetition_index,
        "wall_seconds": time.perf_counter() - suite_started,
        "cases": case_records,
    }


def _prepare_case_snapshot(
    source_raw: Mapping[str, Any],
    source_study_path: Path,
    source_model_path: Path,
    fixture: Mapping[str, Any],
    case: Mapping[str, Any],
    snapshot: Path,
) -> dict[str, Any]:
    selector = case["selector"]
    source_subject = _find_subject(source_raw, selector["subject_id"])
    source_subject_dir = _resolve_input_path(
        source_subject["subject_sources"]["leaddbs_subject_dir"],
        source_study_path.parent,
    )
    source_reconstruction = _resolve_input_path(
        source_subject["subject_sources"]["electrode_reconstruction"]["path"],
        source_study_path.parent,
    )
    try:
        reconstruction_relative = source_reconstruction.relative_to(source_subject_dir)
    except ValueError as exc:
        raise ValueError("Reconstruction must be inside the Lead-DBS subject tree") from exc
    dataset_root = _dataset_root_for_subject(source_subject_dir)
    dataset_description = dataset_root / "dataset_description.json"
    if not dataset_description.is_file():
        raise ValueError(f"BIDS dataset description does not exist: {dataset_description}")

    destination_dataset = snapshot / "copied_dataset"
    destination_subject = (
        destination_dataset
        / "derivatives"
        / "leaddbs"
        / source_subject_dir.name
    )
    destination_subject.parent.mkdir(parents=True)
    _clone_or_copy(dataset_description, destination_dataset / "dataset_description.json")

    def ignore(path: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        if Path(path).resolve() == source_subject_dir:
            if "stimulations" in names:
                ignored.add("stimulations")
            if case["headmodel_state"] == "cold" and "headmodel" in names:
                ignored.add("headmodel")
        return ignored

    shutil.copytree(
        source_subject_dir,
        destination_subject,
        copy_function=_clone_or_copy,
        ignore=ignore,
    )

    snapshot_raw = deepcopy(source_raw)
    _materialize_payloads(snapshot_raw, fixture)
    selected = deepcopy(_find_subject(snapshot_raw, selector["subject_id"]))
    selected["subject_sources"]["leaddbs_subject_dir"] = str(
        destination_subject.relative_to(snapshot)
    )
    selected["subject_sources"]["electrode_reconstruction"]["path"] = str(
        (destination_subject / reconstruction_relative).relative_to(snapshot)
    )
    snapshot_raw["study"]["subjects"] = [selected]
    _write_new_json(snapshot / "study_base.json", snapshot_raw)
    _clone_or_copy(source_model_path, snapshot / "vta_model.yaml")

    copied_study = snapshot / "study_base.json"
    copied_model = snapshot / "vta_model.yaml"
    plan = _resolve_case_subject_plan(copied_study, copied_model, case)
    resolved = resolve_case_tasks(copied_study, copied_model, case)
    _assert_headmodel_state(resolved, case["headmodel_state"])
    if case["initial_artifacts"] != "missing":
        source_tasks = resolve_case_tasks(source_study_path, source_model_path, case)
        _copy_initial_artifacts(
            source_tasks,
            resolved,
            spaces=tuple(fixture["spaces"]),
            mode=case["initial_artifacts"],
        )

    donors = _equivalent_donor_tasks(plan, resolved)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case["case_id"],
        "semantic_selector": case["selector"],
        "resolved_task_ids": [task.task_id for task in resolved],
        "headmodel_state": case["headmodel_state"],
        "initial_artifacts": case["initial_artifacts"],
        "selected_artifacts": _frozen_artifact_state(snapshot, resolved),
        "donor_artifacts": _frozen_artifact_state(snapshot, donors),
    }
    _write_new_json(snapshot / "snapshot_manifest.json", manifest)
    return manifest


def _equivalent_donor_tasks(
    plan: SubjectPlan,
    selected_tasks: tuple[VtaTask, ...],
) -> tuple[VtaTask, ...]:
    selected_ids = {task.task_id for task in selected_tasks}
    selected_keys = {equivalent_task_key(task) for task in selected_tasks}
    donors = {
        task.task_id: task
        for task in plan.reuse_candidates
        if task.task_id not in selected_ids
        and equivalent_task_key(task) in selected_keys
    }
    return tuple(donors[task_id] for task_id in sorted(donors))


def _frozen_artifact_state(
    snapshot_root: Path,
    tasks: tuple[VtaTask, ...],
) -> list[dict[str, Any]]:
    state: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for task in tasks:
        for space in task.model.spaces:
            leaf = leaf_directory(task, space)
            for artifact in expected_artifacts(
                leaf,
                task.model.thresholds_v_per_m,
            ):
                if artifact in seen:
                    continue
                seen.add(artifact)
                try:
                    relative = artifact.relative_to(snapshot_root)
                except ValueError as exc:
                    raise ValueError(
                        f"Frozen artifact escaped snapshot root: {artifact}"
                    ) from exc
                state.append(
                    {
                        "task_id": task.task_id,
                        "space": space,
                        "path": str(relative),
                        "present": artifact.is_file(),
                    }
                )
    return sorted(state, key=lambda item: (item["path"], item["task_id"]))


def _verify_restored_artifact_state(snapshot_root: Path) -> None:
    manifest_path = snapshot_root / "snapshot_manifest.json"
    if not manifest_path.is_file():
        return
    manifest = _read_json_object(manifest_path, "snapshot manifest")
    for field in ("selected_artifacts", "donor_artifacts"):
        entries = manifest.get(field)
        if not isinstance(entries, list):
            raise ValueError(f"Snapshot manifest is missing {field}")
        for entry in entries:
            item = _mapping(entry, field)
            path = (
                snapshot_root
                / _nonempty_string(item.get("path"), "artifact path")
            ).resolve()
            if not _is_within(path, snapshot_root.resolve()):
                raise ValueError(f"Snapshot artifact escaped restore root: {path}")
            expected_present = item.get("present")
            if not isinstance(expected_present, bool):
                raise ValueError("Snapshot artifact present state must be boolean")
            if path.is_file() != expected_present:
                raise ValueError(
                    f"Restored artifact state mismatch for {path}: "
                    f"expected present={expected_present}"
                )


def _copy_initial_artifacts(
    source_tasks: tuple[VtaTask, ...],
    destination_tasks: tuple[VtaTask, ...],
    *,
    spaces: tuple[str, ...],
    mode: str,
) -> None:
    if len(source_tasks) != len(destination_tasks):
        raise ValueError("Source and copied task counts differ")
    for source_task, destination_task in zip(source_tasks, destination_tasks, strict=True):
        for space in spaces:
            source_leaf = leaf_directory(source_task, space)
            destination_leaf = leaf_directory(destination_task, space)
            source_artifacts = expected_artifacts(
                source_leaf, source_task.model.thresholds_v_per_m
            )
            selected = source_artifacts[:1] if mode == "threshold_repair" else source_artifacts
            for source in selected:
                if not source.is_file():
                    raise ValueError(f"Frozen source artifact does not exist: {source}")
                destination = destination_leaf / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                _clone_or_copy(source, destination)
            if mode == "threshold_repair":
                masks = expected_artifacts(
                    destination_leaf, destination_task.model.thresholds_v_per_m
                )[1:]
                if any(mask.exists() for mask in masks):
                    raise ValueError("Threshold-repair snapshot contains a threshold mask")


def _assert_headmodel_state(tasks: tuple[VtaTask, ...], expected: str) -> None:
    paths = {canonical_head_model_path(task) for task in tasks}
    if expected == "cold" and any(path.exists() for path in paths):
        raise ValueError("Cold-headmodel snapshot contains a selected head model")
    if expected == "warm" and any(not path.is_file() for path in paths):
        missing = next(path for path in paths if not path.is_file())
        raise ValueError(f"Warm-headmodel snapshot is missing: {missing}")


def _command_result(result: Any) -> tuple[int, str, str, dict[str, int] | None]:
    if isinstance(result, Mapping):
        returncode = int(result.get("returncode", 0))
        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        counts = result.get("benchmark_counts")
    else:
        returncode = int(getattr(result, "returncode"))
        stdout = str(getattr(result, "stdout", ""))
        stderr = str(getattr(result, "stderr", ""))
        counts = getattr(result, "benchmark_counts", None)
    return returncode, stdout, stderr, dict(counts) if counts is not None else None


def _parse_run_summary(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "generated" in payload:
            return payload
    raise ValueError("Baseline command did not emit a JSON run summary")


def _run_subprocess(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class _RecordingBridge:
    """Thread-safe observation collector around either MATLAB bridge API."""

    def __init__(self, delegate: MatlabBridge) -> None:
        self._delegate = delegate
        self._observations = []
        self._bridge_call_count = 0
        self._lock = threading.Lock()

    @property
    def observations(self) -> tuple[Any, ...]:
        with self._lock:
            return tuple(self._observations)

    @property
    def bridge_call_count(self) -> int:
        with self._lock:
            return self._bridge_call_count

    def run_task(self, task: VtaTask, context: TaskRunContext) -> Any:
        with self._lock:
            self._bridge_call_count += 1
        try:
            observation = self._delegate.run_task(task, context)
        except Exception as error:
            self._record_partial(error)
            raise
        self._record(observation)
        return observation

    def run_subject_manifest(self, subject: SubjectPlan, run_id: str) -> Any:
        with self._lock:
            self._bridge_call_count += 1
        try:
            observation = self._delegate.run_subject_manifest(subject, run_id)
        except Exception as error:
            self._record_partial(error)
            raise
        self._record(observation)
        return observation

    def _record_partial(self, error: Exception) -> None:
        partial = getattr(error, "partial_observation", None)
        if partial is not None:
            self._record(partial)

    def _record(self, observation: Any) -> None:
        with self._lock:
            self._observations.append(observation)


class _CompatibilityPerTaskService:
    """Preserve the pre-persistent per-task execution path for benchmarking."""

    def __init__(self, bridge: _RecordingBridge, *, run_id: str) -> None:
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
        if workers != WORKER_COUNT:
            raise ValueError(f"Benchmark workers must be exactly {WORKER_COUNT}")
        if resume or force:
            raise ValueError("Compatibility benchmark requires a restored snapshot")
        if len(subjects) != 1:
            raise ValueError(
                "Compatibility representative benchmark requires one subject"
            )
        summary = RunSummary()
        for subject in subjects:
            summary += self._run_subject(subject)
        return summary

    def _run_subject(self, subject: SubjectPlan) -> RunSummary:
        summary = RunSummary()
        blocked: set[str] = set()
        reuse_owners: dict[tuple[object, ...], str] = {}
        for task in subject.tasks:
            owner_id = reuse_owners.setdefault(
                equivalent_task_key(task), task.task_id
            )
            if any(dependency in blocked for dependency in task.dependencies):
                blocked.add(task.task_id)
                summary += RunSummary(skipped_dependency=1)
                continue
            if owner_id in blocked and not self._task_is_complete(task):
                blocked.add(task.task_id)
                summary += RunSummary(skipped_dependency=1)
                continue
            try:
                outcome = self._run_task(task, subject)
            except Exception:
                blocked.add(task.task_id)
                summary += RunSummary(failed=1)
                continue
            summary += RunSummary(**{outcome: 1})
        return summary

    @staticmethod
    def _task_is_complete(task: VtaTask) -> bool:
        return all(
            leaf_status(
                leaf_directory(task, space), task.model.thresholds_v_per_m
            ).value
            == "complete"
            for space in task.model.spaces
        )

    def _run_task(self, task: VtaTask, subject: SubjectPlan) -> str:
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
                    leaf, task.model.thresholds_v_per_m
                )
            )
            for space, leaf in leaves.items()
        }
        missing = {space: names for space, names in missing.items() if names}
        if not missing:
            return "copied" if copied else "skipped_existing"
        self.bridge.run_task(
            task,
            TaskRunContext(
                run_id=self.run_id,
                output_leaves=leaves,
                missing_artifacts=missing,
            ),
        )
        for leaf in leaves.values():
            absent = [
                path
                for path in expected_artifacts(
                    leaf, task.model.thresholds_v_per_m
                )
                if not path.is_file()
            ]
            if absent:
                raise RuntimeError(
                    f"Compatibility task left missing artifacts: {absent[0]}"
                )
        return "generated"

    @staticmethod
    def _copy_from_equivalent_groups(
        task: VtaTask,
        subject: SubjectPlan,
        leaves: Mapping[str, Path],
    ) -> bool:
        copied = False
        task_key = equivalent_task_key(task)
        donors = tuple(
            candidate
            for candidate in (subject.reuse_candidates or subject.tasks)
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
                    if source.is_file():
                        copied = (
                            atomic_copy_missing(source, destination) == "copied"
                            or copied
                        )
                        break
        return copied


def _execute_case(
    study_base_path: Path,
    vta_model_path: Path,
    selector: Mapping[str, Any],
    *,
    workers: int,
    execution_path: str = "compatibility_per_task",
) -> dict[str, Any]:
    if workers != WORKER_COUNT:
        raise ValueError(f"Benchmark workers must be exactly {WORKER_COUNT}")
    selection = Selection(
        subject_ids=(str(selector["subject_id"]),),
        phase_ids=(str(selector["phase_id"]),),
        program_ids=(int(selector["program_id"]),),
        electrode_ids=(str(selector["electrode_id"]),),
        frequency_group_ids=(str(selector["frequency_group_id"]),),
    )
    prepared = prepare_plan(study_base_path, vta_model_path, selection)
    tasks = tuple(task for subject in prepared.subjects for task in subject.tasks)
    task_kind_by_id = {task.task_id: task.kind for task in tasks}
    monitor = ProcessTreeMemoryMonitor()
    bridge = _RecordingBridge(
        MatlabBridge(repo_root=_REPO_ROOT, memory_monitor=monitor)
    )
    if execution_path == "compatibility_per_task":
        service: Any = _CompatibilityPerTaskService(
            bridge,
            run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        )
    elif execution_path == "persistent_subject":
        service = RunService(
            bridge,
            run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        )
    else:
        raise ValueError(f"Unsupported benchmark execution path: {execution_path}")
    started = time.perf_counter()
    try:
        summary = service.run(
            prepared.subjects,
            workers=workers,
            resume=False,
            force=False,
        )
    finally:
        memory = monitor.finish()
    wall_seconds = time.perf_counter() - started
    observations = bridge.observations
    executed_solve_count = sum(
        timing.stage == "fem_pcg_solve" and timing.stage_status == "executed"
        for observation in observations
        for timing in observation.timings
    )
    derived_task_count = sum(
        task_kind_by_id.get(outcome.task_id) is TaskKind.ALTERNATING_GROUP_PEAK
        and outcome.status == "generated"
        for observation in observations
        for outcome in observation.outcomes
    )
    counts = {
        "matlab_process_count": len(observations),
        "fem_solve_count": int(executed_solve_count),
        "derived_task_count": int(derived_task_count),
        "copy_count": summary.copied,
        "skip_count": summary.skipped_existing,
    }
    return {
        **asdict(summary),
        "benchmark_counts": counts,
        "wall_seconds": wall_seconds,
        "process_observations": [asdict(item) for item in observations],
        "memory_observation": asdict(memory),
        "artifact_inventory": _artifact_inventory(tasks),
        "execution_path": execution_path,
        "bridge_call_count": bridge.bridge_call_count,
    }


def _artifact_inventory(tasks: tuple[VtaTask, ...]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for task in tasks:
        for space in task.model.spaces:
            leaf = leaf_directory(task, space)
            for path in expected_artifacts(leaf, task.model.thresholds_v_per_m):
                inventory.append(
                    {
                        "task_id": task.task_id,
                        "space": space,
                        "path": str(path),
                        "present": path.is_file(),
                        "size_bytes": path.stat().st_size if path.is_file() else None,
                    }
                )
    return inventory


def compare_case_outputs(
    compatibility_root: Path,
    persistent_root: Path,
    case: Mapping[str, Any],
    spaces: Sequence[str],
) -> dict[str, Any]:
    """Compare paired canonical outputs on semantically corresponding tasks."""

    import nibabel as nib
    import numpy as np

    reference_tasks = resolve_case_tasks(
        compatibility_root / "study_base.json",
        compatibility_root / "vta_model.yaml",
        case,
    )
    candidate_tasks = resolve_case_tasks(
        persistent_root / "study_base.json",
        persistent_root / "vta_model.yaml",
        case,
    )
    if len(reference_tasks) != len(candidate_tasks):
        raise ValueError("Paired benchmark task counts differ")
    rows: list[dict[str, Any]] = []
    for task_index, (reference_task, candidate_task) in enumerate(
        zip(reference_tasks, candidate_tasks, strict=True), start=1
    ):
        if (
            reference_task.kind is not candidate_task.kind
            or tuple(source.source_id for source in reference_task.sources)
            != tuple(source.source_id for source in candidate_task.sources)
        ):
            raise ValueError("Paired benchmark semantic task identities differ")
        exact = reference_task.kind is TaskKind.ALTERNATING_GROUP_PEAK
        for space in spaces:
            reference_leaf = leaf_directory(reference_task, space)
            candidate_leaf = leaf_directory(candidate_task, space)
            reference_image = nib.load(str(reference_leaf / "efield.nii.gz"))
            candidate_image = nib.load(str(candidate_leaf / "efield.nii.gz"))
            reference = np.asarray(reference_image.dataobj, dtype=np.float64)
            candidate = np.asarray(candidate_image.dataobj, dtype=np.float64)
            row = _compare_efield_arrays(
                reference,
                candidate,
                np.asarray(reference_image.affine, dtype=np.float64),
                np.asarray(candidate_image.affine, dtype=np.float64),
                exact=exact,
            )
            row.update(
                {
                    "task_index": task_index,
                    "task_kind": reference_task.kind.value,
                    "source_ids": [
                        source.source_id for source in reference_task.sources
                    ],
                    "space": space,
                    "thresholds": [],
                }
            )
            for threshold in reference_task.model.thresholds_v_per_m:
                reference_vta_image = nib.load(
                    str(reference_leaf / threshold_filename(threshold))
                )
                candidate_vta_image = nib.load(
                    str(candidate_leaf / threshold_filename(threshold))
                )
                reference_vta = np.asarray(reference_vta_image.dataobj) != 0
                candidate_vta = np.asarray(candidate_vta_image.dataobj) != 0
                expected_reference = np.isfinite(reference) & (reference >= threshold)
                expected_candidate = np.isfinite(candidate) & (candidate >= threshold)
                if not np.array_equal(reference_vta, expected_reference):
                    raise ValueError(
                        "Compatibility VTA does not equal thresholded E-field"
                    )
                if not np.array_equal(candidate_vta, expected_candidate):
                    raise ValueError(
                        "Persistent VTA does not equal thresholded E-field"
                    )
                if not np.array_equal(
                    reference_vta_image.affine, reference_image.affine
                ):
                    raise ValueError("Compatibility VTA affine differs from E-field")
                if not np.array_equal(
                    candidate_vta_image.affine, candidate_image.affine
                ):
                    raise ValueError("Persistent VTA affine differs from E-field")
                threshold_row = _compare_vta_masks(
                    reference_vta,
                    candidate_vta,
                    reference,
                    candidate,
                    float(threshold),
                    exact=exact,
                )
                row["thresholds"].append(threshold_row)
            rows.append(row)
    return {"pass": True, "rows": rows}


def _compare_efield_arrays(
    reference: Any,
    candidate: Any,
    reference_affine: Any,
    candidate_affine: Any,
    *,
    exact: bool,
) -> dict[str, Any]:
    import numpy as np

    if reference.shape != candidate.shape:
        raise ValueError("Paired E-field dimensions differ")
    reference_finite = np.isfinite(reference)
    candidate_finite = np.isfinite(candidate)
    if not np.array_equal(reference_finite, candidate_finite):
        raise ValueError("Paired E-field finite masks differ")
    values = reference[reference_finite]
    candidates = candidate[candidate_finite]
    if values.size == 0 or max(float(np.max(np.abs(values))), 0.0) == 0:
        raise ValueError("Paired E-fields contain no finite nonzero signal")
    affine_max_abs = float(np.max(np.abs(candidate_affine - reference_affine)))
    difference = candidates - values
    value_max_abs = float(np.max(np.abs(difference))) if difference.size else 0.0
    denominator = float(np.linalg.norm(values))
    relative_l2 = float(np.linalg.norm(difference) / denominator)
    if np.array_equal(values, candidates):
        correlation = 1.0
    else:
        correlation = float(np.corrcoef(values, candidates)[0, 1])
    exact_values = bool(np.array_equal(reference, candidate, equal_nan=True))
    if affine_max_abs > 1e-12:
        raise ValueError("Paired E-field affine difference exceeds 1e-12")
    if value_max_abs > 1e-3:
        raise ValueError("Paired E-field value difference exceeds 1e-3 V/m")
    if relative_l2 > 1e-5:
        raise ValueError("Paired E-field relative L2 exceeds 1e-5")
    if not np.isfinite(correlation) or correlation < 0.999999:
        raise ValueError("Paired E-field correlation is below 0.999999")
    if exact and not exact_values:
        raise ValueError("Derived group-peak E-field is not exactly repeatable")
    return {
        "shape": list(reference.shape),
        "finite_voxel_count": int(values.size),
        "affine_max_abs": affine_max_abs,
        "value_max_abs_v_per_m": value_max_abs,
        "relative_l2": relative_l2,
        "correlation": correlation,
        "exact_values": exact_values,
    }


def _compare_vta_masks(
    reference_mask: Any,
    candidate_mask: Any,
    reference_efield: Any,
    candidate_efield: Any,
    threshold: float,
    *,
    exact: bool,
) -> dict[str, Any]:
    import numpy as np

    discordant = np.logical_xor(reference_mask, candidate_mask)
    reference_count = int(np.count_nonzero(reference_mask))
    candidate_count = int(np.count_nonzero(candidate_mask))
    total = reference_count + candidate_count
    intersection = int(np.count_nonzero(reference_mask & candidate_mask))
    dice = 1.0 if total == 0 else 2.0 * intersection / total
    volume_denominator = max(reference_count, 1)
    relative_volume_difference = (
        abs(candidate_count - reference_count) / volume_denominator
    )
    if np.any(discordant):
        near_reference = np.abs(reference_efield[discordant] - threshold) <= 1e-3
        near_candidate = np.abs(candidate_efield[discordant] - threshold) <= 1e-3
        discordant_near_threshold = bool(np.all(near_reference & near_candidate))
    else:
        discordant_near_threshold = True
    exact_masks = bool(np.array_equal(reference_mask, candidate_mask))
    if dice < 0.999:
        raise ValueError(f"VTA Dice is below 0.999 at {threshold:g} V/m")
    if relative_volume_difference > 0.001:
        raise ValueError(
            f"VTA relative volume difference exceeds 0.1% at {threshold:g} V/m"
        )
    if not discordant_near_threshold:
        raise ValueError(
            f"VTA discordance is not threshold-local at {threshold:g} V/m"
        )
    if exact and not exact_masks:
        raise ValueError("Derived group-peak VTA is not exactly repeatable")
    return {
        "threshold_v_per_m": threshold,
        "reference_voxel_count": reference_count,
        "candidate_voxel_count": candidate_count,
        "discordant_voxel_count": int(np.count_nonzero(discordant)),
        "dice": dice,
        "relative_volume_difference": relative_volume_difference,
        "discordant_near_threshold": discordant_near_threshold,
        "exact_masks": exact_masks,
    }


def _case_runner_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--study-base", type=Path, required=True)
    parser.add_argument("--vta-model", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--program", type=int, required=True)
    parser.add_argument("--electrode", required=True)
    parser.add_argument("--frequency-group", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument(
        "--execution-path",
        choices=EXECUTION_PATHS,
        default="compatibility_per_task",
    )
    args = parser.parse_args(argv)
    result = _execute_case(
        args.study_base,
        args.vta_model,
        {
            "subject_id": args.subject,
            "phase_id": args.phase,
            "program_id": args.program,
            "electrode_id": args.electrode,
            "frequency_group_id": args.frequency_group,
        },
        workers=args.workers,
        execution_path=args.execution_path,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return (
        1
        if result["failed"]
        or result["skipped_dependency"]
        or result.get("subject_process_failed", 0)
        else 0
    )


def _validate_synthetic_payload(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("delivery_mode") != "continuous"
        or payload.get("control_mode") != "voltage"
        or payload.get("unit") != "V"
    ):
        raise ValueError("Synthetic payload must be continuous voltage control")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 2:
        raise ValueError("Synthetic payload must define exactly two sources")
    for index, source in enumerate(sources, start=1):
        if (
            source.get("source_id") != f"source-{index}"
            or source.get("frequency_hz") != 130
            or source.get("amplitude_v") != 2.0
            or source.get("pulse_width_us") != 60
            or source.get("contacts")
            != [
                {"contact": index, "polarity": "cathode", "fraction": 1.0},
                {"contact": "case", "polarity": "anode", "fraction": 1.0},
            ]
        ):
            raise ValueError("Synthetic multi-source payload is not frozen correctly")


def _validate_selector(selector: Mapping[str, Any], case_id: str) -> None:
    for key in (
        "subject_id",
        "phase_id",
        "electrode_id",
        "frequency_group_id",
    ):
        _nonempty_string(selector.get(key), f"{key} for {case_id}")
    program_id = selector.get("program_id")
    if not isinstance(program_id, int) or isinstance(program_id, bool):
        raise ValueError(f"program_id for {case_id} must be an integer")


def _materialize_payloads(raw: dict[str, Any], fixture: Mapping[str, Any]) -> None:
    payload_cases = [case for case in fixture["cases"] if "payload_id" in case]
    for case in payload_cases:
        subject = _find_subject(raw, case["selector"]["subject_id"])
        phase_id = case["selector"]["phase_id"]
        phase = next(
            (item for item in subject["phases"] if item.get("phase_id") == phase_id),
            None,
        )
        if phase is None:
            phase = {
                "phase_id": phase_id,
                "phase_label": "Frozen performance benchmark",
                "programs": [],
            }
            subject["phases"].append(phase)
        program_id = case["selector"]["program_id"]
        if any(item.get("program_id") == program_id for item in phase["programs"]):
            raise ValueError(
                f"Benchmark program {phase_id}/{program_id} already exists"
            )
        payload = fixture["payloads"][case["payload_id"]]
        group = _payload_frequency_group(subject, case, payload)
        phase["programs"].append(
            {
                "program_id": program_id,
                "program_label": case["case_id"],
                "condition_role": "benchmark_only",
                "stimulation_state": "active",
                "electrode_programs": [
                    {
                        "electrode_id": case["selector"]["electrode_id"],
                        "frequency_groups": [group],
                    }
                ],
            }
        )


def _payload_frequency_group(
    subject: Mapping[str, Any],
    case: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    electrode_id = case["selector"]["electrode_id"]
    if case["payload_id"] == "synthetic_continuous_multi_source":
        sources = [
            {
                "source_id": source["source_id"],
                "source_label": "Synthetic benchmark source",
                "component_id": "benchmark_synthetic",
                "frequency_hz": source["frequency_hz"],
                "control_mode": "voltage",
                "amplitude": source["amplitude_v"],
                "pulse_width_us": source["pulse_width_us"],
                "contacts": _global_contacts(
                    subject, electrode_id, source["contacts"]
                ),
            }
            for source in payload["sources"]
        ]
    else:
        sources = [
            {
                "source_id": "current-source-1",
                "source_label": "Current benchmark source",
                "component_id": "benchmark_current",
                "frequency_hz": payload["frequency_hz"],
                "control_mode": "current",
                "amplitude": payload["amplitude_mA"],
                "pulse_width_us": payload["pulse_width_us"],
                "contacts": _global_contacts(
                    subject, electrode_id, payload["contacts"]
                ),
            }
        ]
    return {
        "frequency_group_id": case["selector"]["frequency_group_id"],
        "delivery_mode": "continuous",
        "sources": sources,
    }


def _global_contacts(
    subject: Mapping[str, Any],
    electrode_id: str,
    contacts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    definitions = {
        item["electrode_id"]: item for item in subject["electrodes"]
    }
    order = subject["contact_numbering"]["electrode_order"]
    if electrode_id not in definitions or electrode_id not in order:
        raise ValueError(f"Unknown benchmark electrode: {electrode_id}")
    offset = sum(definitions[item]["contact_count"] for item in order[: order.index(electrode_id)])
    contact_count = definitions[electrode_id]["contact_count"]
    result: list[dict[str, Any]] = []
    for contact in contacts:
        raw_contact = contact["contact"]
        if raw_contact == "case":
            global_contact: int | str = "case"
        elif (
            isinstance(raw_contact, int)
            and not isinstance(raw_contact, bool)
            and 1 <= raw_contact <= contact_count
        ):
            global_contact = offset + raw_contact - 1
        else:
            raise ValueError(f"Invalid one-based local benchmark contact: {raw_contact}")
        result.append({**contact, "contact": global_contact})
    return result


def _semantic_task_inventory(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for subject in raw["study"]["subjects"]:
        for phase in subject["phases"]:
            for program in phase["programs"]:
                for electrode in program.get("electrode_programs", []):
                    for group in electrode.get("frequency_groups", []):
                        source_ids = [source["source_id"] for source in group["sources"]]
                        common = {
                            "subject_id": subject["subject_id"],
                            "phase_id": phase["phase_id"],
                            "program_id": program["program_id"],
                            "electrode_id": electrode["electrode_id"],
                            "frequency_group_id": group["frequency_group_id"],
                        }
                        if group["delivery_mode"] == "continuous":
                            inventory.append(
                                {
                                    **common,
                                    "task_kind": "continuous_joint",
                                    "source_ids": source_ids,
                                }
                            )
                        else:
                            inventory.extend(
                                {
                                    **common,
                                    "task_kind": "alternating_source",
                                    "source_ids": [source_id],
                                }
                                for source_id in source_ids
                            )
                            inventory.append(
                                {
                                    **common,
                                    "task_kind": "alternating_group_peak",
                                    "source_ids": source_ids,
                                }
                            )
    return inventory


def _semantic_task_matches(
    task: Mapping[str, Any],
    selector: Mapping[str, Any],
    task_selector: Mapping[str, Any],
) -> bool:
    return all(task.get(key) == value for key, value in selector.items()) and all(
        task.get(key) == value for key, value in task_selector.items()
    )


def _reject_unsafe_work_root(
    work_root: Path,
    raw: Mapping[str, Any],
    study_base_directory: Path,
) -> None:
    _reject_protected_path(
        work_root,
        _authoritative_roots(raw, study_base_directory),
    )


def _authoritative_roots(
    raw: Mapping[str, Any],
    study_base_directory: Path,
) -> set[Path]:
    authoritative_roots = {AUTHORITATIVE_LEADDBS_ROOT.resolve()}
    for subject in raw["study"]["subjects"]:
        subject_dir = _resolve_input_path(
            subject["subject_sources"]["leaddbs_subject_dir"],
            study_base_directory,
        )
        if subject_dir.parent.name == "leaddbs" and subject_dir.name.startswith("sub-"):
            authoritative_roots.add(subject_dir.parent.resolve())
    return authoritative_roots


def _reject_protected_path(
    path: Path,
    protected_roots: Sequence[Path | str],
) -> None:
    resolved = path.expanduser().resolve()
    for raw_root in protected_roots:
        root = Path(raw_root).expanduser().resolve()
        if _is_within(resolved, root) or _is_within(root, resolved):
            raise ValueError(
                "Benchmark paths must be separate from authoritative "
                f"derivatives: {root}"
            )


def _move_conflict_to_trash(
    path: Path,
    *,
    trash_root: Path | str | None,
) -> Path | None:
    if not path.exists():
        return None
    return move_leaf_to_trash(path, trash_root=trash_root)


def _clone_or_copy(source: Path | str, destination: Path | str) -> str:
    """Use an APFS clone when available, preserving a portable copy fallback."""

    source_path = Path(source)
    destination_path = Path(destination)
    clonefile = getattr(os, "clonefile", None)
    if clonefile is not None:
        try:
            clonefile(source_path, destination_path)
            shutil.copystat(source_path, destination_path)
            return str(destination_path)
        except OSError:
            destination_path.unlink(missing_ok=True)
    return str(shutil.copy2(source_path, destination_path))


def _publish_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    trash_root: Path | str | None,
) -> None:
    _move_conflict_to_trash(path, trash_root=trash_root)
    _write_new_json(path, payload)


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite untracked file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read {label}: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return raw


def _find_subject(raw: Mapping[str, Any], subject_id: str) -> dict[str, Any]:
    matches = [
        subject
        for subject in raw["study"]["subjects"]
        if subject.get("subject_id") == subject_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Subject selector must resolve exactly once: {subject_id}")
    return matches[0]


def _dataset_root_for_subject(subject_dir: Path) -> Path:
    leaddbs_root = subject_dir.parent
    derivatives_root = leaddbs_root.parent
    if leaddbs_root.name != "leaddbs" or derivatives_root.name != "derivatives":
        raise ValueError(
            "Lead-DBS subject directory must use "
            "<dataset>/derivatives/leaddbs/sub-* layout"
        )
    return derivatives_root.parent


def _resolve_input_path(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, prepare, or run the frozen VTA baseline benchmark."
    )
    commands = parser.add_subparsers(dest="mode", required=True)
    for mode in ("validate", "prepare", "run-baseline"):
        command = commands.add_parser(mode)
        command.add_argument("--study-base", type=Path, required=True)
        command.add_argument("--vta-model", type=Path, required=True)
        command.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
        if mode != "validate":
            command.add_argument("--work-root", type=Path, required=True)
    paired = commands.add_parser("run-paired")
    paired.add_argument("--benchmark-root", type=Path, required=True)
    paired.add_argument("--case", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.mode == "run-paired":
            run_paired(args.benchmark_root, args.case)
            print(args.benchmark_root / "benchmark_summary.json")
            return 0
        if args.mode == "validate":
            result = validate_benchmark_inputs(
                args.study_base,
                args.vta_model,
                fixture_path=args.fixture,
            )
            task_count = sum(len(items) for items in result["semantic_tasks"].values())
            print(
                f"valid cases={len(result['semantic_tasks'])} "
                f"semantic_tasks={task_count}"
            )
            return 0
        root = prepare_benchmark(
            args.study_base,
            args.vta_model,
            args.work_root,
            fixture_path=args.fixture,
        )
        if args.mode == "prepare":
            print(root)
            return 0
        run_baseline(root)
        print(root / "benchmark_summary.json")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
