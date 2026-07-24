#!/usr/bin/env python3
"""Validate terminal Task 17 scheduler and resource-guard evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
import uuid


_ALLOWED_GUARD_EVENTS = frozenset(
    {"sample", "runner_exit", "runner_exited", "completed"}
)
_TERMINAL_GUARD_EVENTS = frozenset(
    {"runner_exit", "runner_exited", "completed"}
)
_ADMISSION_REASONS = frozenset(
    {
        "worker_slots",
        "cpu",
        "managed_memory",
        "memory_reserve",
        "connectome_io",
        "external_solver",
    }
)
_SCHEDULER_ROW_FIELDS = frozenset(
    {
        "start_utc",
        "finish_utc",
        "elapsed_seconds",
        "ready_task_count",
        "running_task_count",
        "runnable_cpu_slots",
        "reserved_cpu_slots",
        "reserved_memory_bytes",
        "reserved_connectome_io_slots",
        "reserved_external_solver_slots",
        "admission_blocked_task_count_by_reason",
        "storage_limited",
    }
)


class ResourceAcceptanceError(RuntimeError):
    """Raised when terminal Task 17 resource evidence is incomplete."""


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(block_size):
                digest.update(block)
    except OSError as exc:
        raise ResourceAcceptanceError(f"cannot hash evidence file: {path}") from exc
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResourceAcceptanceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ResourceAcceptanceError(f"{label} must contain an object: {path}")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise ResourceAcceptanceError(
            f"{label} must be an integer not below {minimum}"
        )
    return int(value)


def _number(value: object, label: str, *, minimum: float = 0.0) -> float:
    if type(value) is bool:
        raise ResourceAcceptanceError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResourceAcceptanceError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or result < minimum:
        raise ResourceAcceptanceError(
            f"{label} must be finite and not below {minimum}"
        )
    return result


def _task_id(item: Mapping[str, Any]) -> str:
    key = item.get("key")
    if (
        not isinstance(key, Mapping)
        or set(key)
        != {"endpoint_id", "stage", "branch", "parameter_identity"}
        or any(not str(key[field]).strip() for field in key)
    ):
        raise ResourceAcceptanceError("sensitivity plan task key is invalid")
    payload = json.dumps(
        dict(key),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"task_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _validate_tasks(
    run_root: Path,
    segment: Mapping[str, Any],
) -> dict[str, Any]:
    plan_path = run_root / "sensitivity_plan.json"
    plan_document = _read_json(plan_path, "sensitivity plan")
    plan = plan_document.get("plan")
    if not isinstance(plan, Mapping) or not isinstance(plan.get("tasks"), list):
        raise ResourceAcceptanceError("sensitivity plan task closure is invalid")
    task_ids: list[str] = []
    for task in plan["tasks"]:
        if not isinstance(task, Mapping):
            raise ResourceAcceptanceError("sensitivity plan task must be an object")
        task_id = _task_id(task)
        if task_id in task_ids:
            raise ResourceAcceptanceError(
                "sensitivity plan task IDs must be nonempty and unique"
            )
        task_ids.append(task_id)
    if not task_ids:
        raise ResourceAcceptanceError("sensitivity plan contains no tasks")
    status_counts: dict[str, int] = {}
    task_digests: list[str] = []
    for task_id in task_ids:
        path = run_root / "tasks" / f"{task_id}.json"
        task = _read_json(path, f"task {task_id}")
        if str(task.get("task_id", task_id)) != task_id:
            raise ResourceAcceptanceError(f"task identity differs: {task_id}")
        status = str(task.get("status", "")).strip()
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "completed":
            raise ResourceAcceptanceError(
                f"terminal plan task is not completed: {task_id}:{status}"
            )
        reason = str(task.get("reason", "")).strip()
        if reason not in {"none", "restored_completed_result"}:
            raise ResourceAcceptanceError(
                f"completed task retains an unsupported reason: {task_id}:{reason}"
            )
        task_digests.append(_sha256_file(path))
    terminal_count = _integer(
        segment.get("terminal_task_count"),
        "segment terminal task count",
        minimum=1,
    )
    if terminal_count != len(task_ids):
        raise ResourceAcceptanceError(
            "segment terminal task count differs from the plan"
        )
    restored = _integer(
        segment.get("restored_task_count"),
        "segment restored task count",
    )
    scheduled = _integer(
        segment.get("scheduled_task_count"),
        "segment scheduled task count",
    )
    retries = _integer(
        segment.get("transient_retry_count"),
        "segment transient retry count",
    )
    if restored > terminal_count or scheduled < terminal_count - restored:
        raise ResourceAcceptanceError(
            "segment restored and scheduled task counts do not cover the plan"
        )
    if scheduled > terminal_count - restored + retries:
        raise ResourceAcceptanceError(
            "segment scheduled task count exceeds its retry closure"
        )
    digest = hashlib.sha256()
    for task_id, task_sha in zip(task_ids, task_digests, strict=True):
        digest.update(task_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(task_sha.encode("ascii"))
        digest.update(b"\n")
    return {
        "plan_sha256": _sha256_file(plan_path),
        "task_count": len(task_ids),
        "task_status_counts": status_counts,
        "task_closure_sha256": digest.hexdigest(),
    }


def _reason_counts(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != _ADMISSION_REASONS:
        raise ResourceAcceptanceError(f"{label} reason closure differs")
    return {
        reason: _integer(value[reason], f"{label} {reason}")
        for reason in sorted(_ADMISSION_REASONS)
    }


def _reason_waits(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != _ADMISSION_REASONS:
        raise ResourceAcceptanceError(f"{label} reason closure differs")
    return {
        reason: _number(value[reason], f"{label} {reason}")
        for reason in sorted(_ADMISSION_REASONS)
    }


def _utc_timestamp(value: object, label: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ResourceAcceptanceError(f"{label} is invalid") from exc
    if (
        timestamp.utcoffset() is None
        or timestamp.utcoffset().total_seconds() != 0
    ):
        raise ResourceAcceptanceError(f"{label} is not UTC")
    return timestamp


def _validate_scheduler_windows(
    run_root: Path,
    segment: Mapping[str, Any],
    *,
    workers: int,
    managed_memory_bytes: int,
    connectome_io_slots: int,
    external_solver_slots: int,
) -> dict[str, Any]:
    relative = segment.get("scheduler_windows_path")
    if not isinstance(relative, str) or not relative:
        raise ResourceAcceptanceError("segment lacks scheduler-window path")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ResourceAcceptanceError("scheduler-window path must be relative")
    path = (run_root / relative_path).resolve()
    if run_root.resolve() not in path.parents:
        raise ResourceAcceptanceError("scheduler-window path escapes run root")
    expected_sha = str(segment.get("scheduler_windows_sha256", "")).strip().lower()
    if (
        len(expected_sha) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha)
        or _sha256_file(path) != expected_sha
    ):
        raise ResourceAcceptanceError("scheduler-window SHA differs")
    document = _read_json(path, "scheduler windows")
    rows = document.get("rows")
    declared_count = _integer(
        segment.get("scheduler_window_count"),
        "scheduler-window count",
        minimum=1,
    )
    if (
        set(document) != {"schema_version", "segment_id", "rows"}
        or document.get("schema_version")
        != "dual_frequency_scheduler_windows_v1"
        or document.get("segment_id") != segment.get("segment_id")
        or not isinstance(rows, list)
        or len(rows) != declared_count
    ):
        raise ResourceAcceptanceError("scheduler-window closure differs")
    prior_finish: datetime | None = None
    peak_cpu = 0
    peak_memory = 0
    peak_io = 0
    peak_solver = 0
    peak_admission_counts = {
        reason: 0
        for reason in sorted(_ADMISSION_REASONS)
    }
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != _SCHEDULER_ROW_FIELDS:
            raise ResourceAcceptanceError(
                f"scheduler window {index} fields differ"
            )
        start = _utc_timestamp(
            row["start_utc"],
            f"scheduler window {index} start",
        )
        finish = _utc_timestamp(
            row["finish_utc"],
            f"scheduler window {index} finish",
        )
        if finish <= start or (prior_finish is not None and start != prior_finish):
            raise ResourceAcceptanceError(
                "scheduler-window time closure differs"
            )
        elapsed = _number(
            row["elapsed_seconds"],
            f"scheduler window {index} elapsed",
        )
        if elapsed <= 0:
            raise ResourceAcceptanceError(
                "scheduler-window elapsed time must be positive"
            )
        scheduler_counts = {
            field: _integer(row[field], f"scheduler window {index} {field}")
            for field in (
                "ready_task_count",
                "running_task_count",
                "runnable_cpu_slots",
            )
        }
        running = scheduler_counts["running_task_count"]
        runnable = scheduler_counts["runnable_cpu_slots"]
        cpu = _integer(
            row["reserved_cpu_slots"],
            f"scheduler window {index} reserved CPU",
        )
        memory = _integer(
            row["reserved_memory_bytes"],
            f"scheduler window {index} reserved memory",
        )
        connectome_io = _integer(
            row["reserved_connectome_io_slots"],
            f"scheduler window {index} reserved connectome I/O",
        )
        solver = _integer(
            row["reserved_external_solver_slots"],
            f"scheduler window {index} reserved solver",
        )
        if (
            running > workers
            or runnable > workers
            or cpu > workers
            or memory > managed_memory_bytes
            or connectome_io > connectome_io_slots
            or solver > external_solver_slots
        ):
            raise ResourceAcceptanceError(
                "scheduler-window reservation exceeds its ceiling"
            )
        reasons = _reason_counts(
            row["admission_blocked_task_count_by_reason"],
            f"scheduler window {index} admission",
        )
        for reason, count in reasons.items():
            peak_admission_counts[reason] = max(
                peak_admission_counts[reason],
                count,
            )
        if (
            type(row["storage_limited"]) is not bool
            or row["storage_limited"] != (reasons["connectome_io"] > 0)
        ):
            raise ResourceAcceptanceError(
                "scheduler-window storage classification differs"
            )
        peak_cpu = max(peak_cpu, cpu)
        peak_memory = max(peak_memory, memory)
        peak_io = max(peak_io, connectome_io)
        peak_solver = max(peak_solver, solver)
        prior_finish = finish
    return {
        "path": str(path),
        "sha256": expected_sha,
        "window_count": len(rows),
        "peak_reserved_cpu_slots": peak_cpu,
        "peak_reserved_memory_bytes": peak_memory,
        "peak_reserved_connectome_io_slots": peak_io,
        "peak_reserved_external_solver_slots": peak_solver,
        "peak_admission_blocked_task_count_by_reason": peak_admission_counts,
        "status": "validated",
    }


def _validate_segment(
    run_root: Path,
    segment_id: str,
    *,
    workers: int,
    max_rss_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if re.fullmatch(r"segment_[0-9]+", segment_id) is None:
        raise ResourceAcceptanceError("selected segment identity is invalid")
    path = run_root / "execution_segments" / f"{segment_id}.json"
    segment = _read_json(path, "execution segment")
    if (
        segment.get("schema_version") != "dual_frequency_execution_segment_v1"
        or segment.get("segment_id") != segment_id
        or segment.get("status") != "finished"
        or segment.get("pool_mode") != "spawn_process"
    ):
        raise ResourceAcceptanceError(
            "selected execution segment is not a finished spawn segment"
        )
    if _integer(segment.get("workers"), "segment workers", minimum=1) != workers:
        raise ResourceAcceptanceError("segment worker ceiling differs")
    managed_memory = _integer(
        segment.get("managed_memory_bytes"),
        "managed-memory ceiling",
        minimum=1,
    )
    if managed_memory > max_rss_bytes:
        raise ResourceAcceptanceError("managed-memory ceiling exceeds RSS ceiling")
    memory_reserve = _integer(
        segment.get("required_memory_reserve_bytes"),
        "required memory reserve",
        minimum=1,
    )
    expected_io_slots = max(1, min(2, workers))
    connectome_io_slots = _integer(
        segment.get("connectome_io_slots"),
        "connectome I/O slots",
        minimum=1,
    )
    if connectome_io_slots != expected_io_slots:
        raise ResourceAcceptanceError("connectome I/O slot boundary differs")
    if _integer(
        segment.get("blas_threads_per_worker"),
        "BLAS threads per worker",
        minimum=1,
    ) != 1:
        raise ResourceAcceptanceError("segment BLAS thread boundary differs")
    external_solver_slots = _integer(
        segment.get("external_solver_slots"),
        "external solver slots",
        minimum=1,
    )
    if external_solver_slots != 1:
        raise ResourceAcceptanceError("segment must expose one solver slot")
    peak_rss = _integer(
        segment.get("peak_task_tree_rss_bytes"),
        "segment peak task-tree RSS",
        minimum=1,
    )
    if peak_rss >= max_rss_bytes:
        raise ResourceAcceptanceError("segment task-tree RSS reached its ceiling")
    if _integer(
        segment.get("peak_swap_delta_bytes"),
        "segment peak swap growth",
    ) >= 1:
        raise ResourceAcceptanceError("segment peak swap growth is not below one byte")
    if _integer(
        segment.get("swap_delta_bytes"),
        "segment final swap growth",
    ) >= 1:
        raise ResourceAcceptanceError("segment final swap growth is not below one byte")
    samples = _integer(
        segment.get("resource_sample_count"),
        "segment resource sample count",
        minimum=1,
    )
    cpu_peak = _integer(
        segment.get("peak_reserved_cpu_slots"),
        "segment reserved CPU peak",
    )
    if cpu_peak >= workers + 1:
        raise ResourceAcceptanceError(
            "segment reserved CPU peak exceeds the worker contract"
        )
    memory_peak = _integer(
        segment.get("peak_reserved_memory_bytes"),
        "segment reserved memory peak",
    )
    if memory_peak > managed_memory:
        raise ResourceAcceptanceError(
            "segment reserved memory peak exceeds its ceiling"
        )
    connectome_io_peak = _integer(
        segment.get("peak_reserved_connectome_io_slots"),
        "segment reserved connectome I/O peak",
    )
    if connectome_io_peak > connectome_io_slots:
        raise ResourceAcceptanceError(
            "segment reserved connectome I/O peak exceeds its ceiling"
        )
    solver_peak = _integer(
        segment.get("peak_reserved_external_solver_slots"),
        "segment reserved solver peak",
    )
    if solver_peak >= 2:
        raise ResourceAcceptanceError(
            "segment reserved solver peak exceeds one token"
        )
    running_peak = _integer(
        segment.get("peak_running_task_count"),
        "segment running-task peak",
    )
    if running_peak > workers:
        raise ResourceAcceptanceError(
            "segment running-task peak exceeds the worker ceiling"
        )
    ready_peak = _integer(
        segment.get("max_ready_queue_depth"),
        "segment ready-queue peak",
    )
    admission_counts = _reason_counts(
        segment.get("admission_blocked_task_count_by_reason"),
        "segment admission count",
    )
    admission_waits = _reason_waits(
        segment.get("admission_wait_seconds_by_reason"),
        "segment admission wait",
    )
    maximum_admission_wait = _number(
        segment.get("max_task_admission_wait_seconds"),
        "segment maximum admission wait",
    )
    generations = _integer(
        segment.get("pool_generation_count"),
        "segment pool generation count",
        minimum=1,
    )
    recoveries = sum(
        _integer(segment.get(field), f"segment {field}")
        for field in ("task_timeout_count", "broken_pool_count")
    )
    if generations > 1 and recoveries < 1:
        raise ResourceAcceptanceError(
            "multiple pool generations lack a recorded recovery event"
        )
    for field in (
        "transient_retry_count",
        "quarantined_attempt_count",
    ):
        _integer(segment.get(field), f"segment {field}")
    scheduler = _validate_scheduler_windows(
        run_root,
        segment,
        workers=workers,
        managed_memory_bytes=managed_memory,
        connectome_io_slots=connectome_io_slots,
        external_solver_slots=external_solver_slots,
    )
    if (
        scheduler["peak_reserved_cpu_slots"] > cpu_peak
        or scheduler["peak_reserved_memory_bytes"] > memory_peak
        or scheduler["peak_reserved_connectome_io_slots"] > connectome_io_peak
        or scheduler["peak_reserved_external_solver_slots"] > solver_peak
        or any(
            scheduler["peak_admission_blocked_task_count_by_reason"][reason]
            > admission_counts[reason]
            for reason in _ADMISSION_REASONS
        )
    ):
        raise ResourceAcceptanceError(
            "scheduler-window peak exceeds the segment aggregate"
        )
    tasks = _validate_tasks(run_root, segment)
    return (
        {
            "segment_id": segment_id,
            "segment_sha256": _sha256_file(path),
            "workers": workers,
            "managed_memory_bytes": managed_memory,
            "required_memory_reserve_bytes": memory_reserve,
            "connectome_io_slots": connectome_io_slots,
            "external_solver_slots": external_solver_slots,
            "blas_threads_per_worker": 1,
            "pool_generation_count": generations,
            "resource_sample_count": samples,
            "peak_task_tree_rss_bytes": peak_rss,
            "peak_swap_delta_bytes": segment["peak_swap_delta_bytes"],
            "swap_delta_bytes": segment["swap_delta_bytes"],
            "peak_reserved_cpu_slots": cpu_peak,
            "peak_reserved_memory_bytes": memory_peak,
            "peak_reserved_connectome_io_slots": connectome_io_peak,
            "peak_reserved_external_solver_slots": solver_peak,
            "peak_running_task_count": running_peak,
            "max_ready_queue_depth": ready_peak,
            "admission_blocked_task_count_by_reason": admission_counts,
            "admission_wait_seconds_by_reason": admission_waits,
            "max_task_admission_wait_seconds": maximum_admission_wait,
            "status": "validated",
        },
        tasks,
        scheduler,
    )


def _guard_integer(row: Mapping[str, str], field: str, line: int) -> int:
    try:
        value = int(row.get(field, ""))
    except ValueError as exc:
        raise ResourceAcceptanceError(
            f"guard {field} is invalid on line {line}"
        ) from exc
    if value < 0:
        raise ResourceAcceptanceError(
            f"guard {field} is negative on line {line}"
        )
    return value


def _validate_guard(path: Path, *, max_rss_bytes: int) -> dict[str, Any]:
    required = {
        "timestamp_utc",
        "tree_rss_bytes",
        "peak_tree_rss_bytes",
        "tree_cpu_percent",
        "swap_used_bytes",
        "swap_baseline_bytes",
        "event",
    }
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if set(reader.fieldnames or ()) != required:
                raise ResourceAcceptanceError("guard CSV fields differ")
            rows = [dict(row) for row in reader]
    except OSError as exc:
        raise ResourceAcceptanceError(f"cannot read guard CSV: {path}") from exc
    if not rows:
        raise ResourceAcceptanceError("guard CSV contains no samples")
    epochs: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    previous_peak: int | None = None
    current: dict[str, Any] | None = None
    maximum_gap = 0.0
    global_peak = 0
    for index, row in enumerate(rows, start=2):
        timestamp = _utc_timestamp(
            row["timestamp_utc"],
            f"guard timestamp on line {index}",
        )
        if previous_time is not None:
            gap = (timestamp - previous_time).total_seconds()
            if gap <= 0:
                raise ResourceAcceptanceError(
                    "guard timestamps are not strictly increasing"
                )
            maximum_gap = max(maximum_gap, gap)
        tree_rss = _guard_integer(row, "tree_rss_bytes", index)
        declared_peak = _guard_integer(row, "peak_tree_rss_bytes", index)
        swap_used = _guard_integer(row, "swap_used_bytes", index)
        baseline = _guard_integer(row, "swap_baseline_bytes", index)
        _number(row.get("tree_cpu_percent"), "guard tree CPU")
        event = str(row.get("event", "")).strip()
        if event not in _ALLOWED_GUARD_EVENTS:
            raise ResourceAcceptanceError(
                f"guard contains a stop or unsupported event: {event}"
            )
        is_last = index == len(rows) + 1
        if (
            (event in _TERMINAL_GUARD_EVENTS) != is_last
            or (is_last and tree_rss != 0)
        ):
            raise ResourceAcceptanceError(
                "guard terminal-event boundary differs"
            )
        if tree_rss >= max_rss_bytes or declared_peak >= max_rss_bytes:
            raise ResourceAcceptanceError("guard RSS reached its ceiling")
        if max(0, swap_used - baseline) >= 1:
            raise ResourceAcceptanceError(
                "guard swap growth is not below one byte"
            )
        new_epoch = (
            current is None
            or baseline != current["swap_baseline_bytes"]
            or (previous_peak is not None and declared_peak < previous_peak)
        )
        if new_epoch:
            current = {
                "start_utc": timestamp.isoformat(),
                "finish_utc": timestamp.isoformat(),
                "sample_count": 0,
                "swap_baseline_bytes": baseline,
                "peak_tree_rss_bytes": 0,
            }
            epochs.append(current)
            previous_peak = None
        if declared_peak < tree_rss or (
            previous_peak is not None and declared_peak < previous_peak
        ):
            raise ResourceAcceptanceError(
                "guard running RSS peak is inconsistent"
            )
        current["finish_utc"] = timestamp.isoformat()
        current["sample_count"] += 1
        current["peak_tree_rss_bytes"] = max(
            current["peak_tree_rss_bytes"],
            declared_peak,
        )
        previous_time = timestamp
        previous_peak = declared_peak
        global_peak = max(global_peak, declared_peak)
    return {
        "guard_sha256": _sha256_file(path),
        "sample_count": len(rows),
        "epoch_count": len(epochs),
        "start_utc": epochs[0]["start_utc"],
        "finish_utc": epochs[-1]["finish_utc"],
        "maximum_sample_gap_seconds": maximum_gap,
        "peak_task_tree_rss_bytes": global_peak,
        "epochs": epochs,
        "status": "validated",
    }


def validate(
    run_root: Path,
    segment_id: str,
    guard_csv: Path,
    *,
    workers: int,
    max_rss_bytes: int,
) -> dict[str, Any]:
    root = run_root.expanduser().resolve()
    manifest_path = root / "run_manifest.json"
    manifest = _read_json(manifest_path, "run manifest")
    if (
        manifest.get("final_status") != "completed"
        or manifest.get("run_id") != root.name
    ):
        raise ResourceAcceptanceError("run manifest is not terminal-completed")
    workers = _integer(workers, "expected workers", minimum=1)
    max_rss_bytes = _integer(
        max_rss_bytes,
        "RSS ceiling",
        minimum=1,
    )
    segment, tasks, scheduler = _validate_segment(
        root,
        segment_id,
        workers=workers,
        max_rss_bytes=max_rss_bytes,
    )
    if segment["segment_id"] != segment_id:
        raise ResourceAcceptanceError("selected segment identity differs")
    guard = _validate_guard(
        guard_csv.expanduser().resolve(),
        max_rss_bytes=max_rss_bytes,
    )
    return {
        "schema_version": "dual_frequency_task17_resource_acceptance_v1",
        "run_id": manifest["run_id"],
        "run_manifest_sha256": _sha256_file(manifest_path),
        "max_rss_bytes": max_rss_bytes,
        "segment": segment,
        "scheduler_windows": scheduler,
        "tasks": tasks,
        "guard": guard,
        "status": "validated",
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    serialized = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_text(encoding="utf-8") != serialized:
            raise ResourceAcceptanceError(
                f"existing resource report differs: {destination}"
            )
        return
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument("--guard-csv", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    parser.add_argument(
        "--max-rss-bytes",
        type=int,
        default=64 * 1024**3,
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(
            arguments.run_root,
            arguments.segment_id,
            arguments.guard_csv,
            workers=arguments.workers,
            max_rss_bytes=arguments.max_rss_bytes,
        )
        if arguments.output is not None:
            _write_report(arguments.output, report)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except ResourceAcceptanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
