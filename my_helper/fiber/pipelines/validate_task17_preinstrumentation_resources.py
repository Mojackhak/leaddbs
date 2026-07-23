#!/usr/bin/env python3
"""Validate terminal Task 17 resources for a pre-instrumentation OSS segment."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
import uuid


_ALLOWED_GUARD_EVENTS = frozenset({"sample", "runner_exited", "completed"})
_WINDOW_SCHEMA = "dual_frequency_task17_preinstrumentation_windows_v1"


class PreinstrumentationResourceError(RuntimeError):
    """Raised when pre-instrumentation resource evidence is incomplete."""


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreinstrumentationResourceError(
            f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise PreinstrumentationResourceError(
            f"{label} must contain an object: {path}"
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise PreinstrumentationResourceError(
            f"{label} must be an integer not below {minimum}"
        )
    return int(value)


def _number(value: object, label: str, *, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PreinstrumentationResourceError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or result < minimum:
        raise PreinstrumentationResourceError(
            f"{label} must be finite and not below {minimum}"
        )
    return result


def _timestamp(value: object, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreinstrumentationResourceError(f"{label} is invalid") from exc
    if result.tzinfo is None:
        raise PreinstrumentationResourceError(f"{label} must include a timezone")
    return result


def _task_closure(run_root: Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    plan_path = run_root / "sensitivity_plan.json"
    plan_document = _read_json(plan_path, "sensitivity plan")
    plan = plan_document.get("plan")
    if not isinstance(plan, Mapping) or not isinstance(plan.get("tasks"), list):
        raise PreinstrumentationResourceError(
            "sensitivity plan task closure is invalid"
        )
    plan_tasks: list[dict[str, Any]] = []
    task_digests: list[tuple[str, str]] = []
    status_counts: dict[str, int] = {}
    for item in plan["tasks"]:
        if not isinstance(item, Mapping):
            raise PreinstrumentationResourceError(
                "sensitivity plan task must be an object"
            )
        task_id = str(item.get("task_id", "")).strip()
        if not task_id or any(task["task_id"] == task_id for task in plan_tasks):
            raise PreinstrumentationResourceError(
                "sensitivity plan task IDs must be nonempty and unique"
            )
        task_path = run_root / "tasks" / f"{task_id}.json"
        task = _read_json(task_path, f"task {task_id}")
        if str(task.get("task_id", task_id)) != task_id:
            raise PreinstrumentationResourceError(
                f"task identity differs: {task_id}"
            )
        status = str(task.get("status", "")).strip()
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "completed":
            raise PreinstrumentationResourceError(
                f"terminal plan task is not completed: {task_id}:{status}"
            )
        reason = str(task.get("reason", "")).strip()
        if reason not in {"none", "restored_completed_result"}:
            raise PreinstrumentationResourceError(
                f"completed task retains an unsupported reason: {task_id}:{reason}"
            )
        plan_tasks.append({**dict(item), "task_id": task_id, "outcome": task})
        task_digests.append((task_id, _sha256_file(task_path)))
    if not plan_tasks:
        raise PreinstrumentationResourceError("sensitivity plan contains no tasks")
    digest = hashlib.sha256()
    for task_id, task_sha in task_digests:
        digest.update(task_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(task_sha.encode("ascii"))
        digest.update(b"\n")
    return (
        {
            "plan_sha256": _sha256_file(plan_path),
            "task_count": len(plan_tasks),
            "task_status_counts": status_counts,
            "task_closure_sha256": digest.hexdigest(),
        },
        tuple(plan_tasks),
    )


def _cache_entry(
    cache_root: Path,
    kind: str,
    identity: str,
    required_files: frozenset[str],
) -> tuple[dict[str, Any], Path]:
    if (
        len(identity) != 64
        or any(character not in "0123456789abcdef" for character in identity)
    ):
        raise PreinstrumentationResourceError(
            f"{kind} identity is not a lowercase SHA-256 digest"
        )
    root = cache_root / "shared_exposure_v2" / kind / identity
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path, f"{kind} cache manifest")
    key = manifest.get("scientific_cache_key")
    if (
        not isinstance(key, Mapping)
        or key.get("kind") != kind
        or manifest.get("schema_version") != "scientific_cache_entry_v2"
        or manifest.get("completed") is not True
        or manifest.get("scientific_identity") != identity
    ):
        raise PreinstrumentationResourceError(
            f"{kind} cache manifest identity differs"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PreinstrumentationResourceError(
            f"{kind} cache manifest files are invalid"
        )
    names: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping):
            raise PreinstrumentationResourceError(
                f"{kind} cache file record is invalid"
            )
        relative = str(item.get("relative_path", "")).strip()
        if (
            not relative
            or relative in names
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise PreinstrumentationResourceError(
                f"{kind} cache file path is invalid"
            )
        path = root / relative
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PreinstrumentationResourceError(
                f"{kind} cache payload is unavailable: {relative}"
            ) from exc
        if size != _integer(item.get("size_bytes"), f"{kind} cache size"):
            raise PreinstrumentationResourceError(
                f"{kind} cache payload size differs: {relative}"
            )
        if _sha256_file(path) != item.get("sha256"):
            raise PreinstrumentationResourceError(
                f"{kind} cache payload SHA-256 differs: {relative}"
            )
        names.add(relative)
    if names != required_files:
        raise PreinstrumentationResourceError(
            f"{kind} cache payload closure differs"
        )
    return manifest, root


def _gate_closure(
    tasks: Sequence[Mapping[str, Any]],
    cache_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    gates: list[dict[str, Any]] = []
    decision_groups: dict[str, str] = {}
    for item in tasks:
        outcome = item["outcome"]
        result = outcome.get("result")
        service_id = str(item.get("service_id", "")).strip()
        if service_id != "establish_oss_axis_equivalence":
            continue
        if (
            not isinstance(result, Mapping)
            or result.get("output_record_type") != "OSSAxisEquivalenceGroupRecord"
            or not isinstance(result.get("payload"), Mapping)
        ):
            raise PreinstrumentationResourceError(
                "completed OSS gate lacks its typed result"
            )
        payload = dict(result["payload"])
        group_id = str(payload.get("group_id", "")).strip()
        decision_ids = payload.get("row_decision_ids")
        if (
            not group_id
            or payload.get("gate_status") != "accepted_omega_max"
            or not isinstance(decision_ids, list)
            or not decision_ids
            or len(set(decision_ids)) != len(decision_ids)
        ):
            raise PreinstrumentationResourceError(
                f"OSS gate result is not accepted and closed: {group_id}"
            )
        for decision_id in decision_ids:
            decision = str(decision_id)
            if decision in decision_groups:
                raise PreinstrumentationResourceError(
                    "OSS decisions must belong to one gate only"
                )
            decision_groups[decision] = group_id
        gates.append(
            {
                "task_id": item["task_id"],
                "group_id": group_id,
                "row_decision_ids": sorted(str(value) for value in decision_ids),
            }
        )
    if len(gates) != 2:
        raise PreinstrumentationResourceError(
            "pre-instrumentation OSS acceptance requires two completed gates"
        )
    rows: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for decision_id, group_id in sorted(decision_groups.items()):
        _, decision_root = _cache_entry(
            cache_root,
            "oss_axis_equivalence",
            decision_id,
            frozenset({"decision.json"}),
        )
        decision = _read_json(
            decision_root / "decision.json",
            f"OSS decision {decision_id}",
        )
        if (
            decision.get("schema_version") != "dual_frequency_oss_axis_decision_v1"
            or decision.get("decision_id") != decision_id
            or decision.get("group_id") != group_id
            or decision.get("status") != "pass"
            or _integer(
                decision.get("state_mismatch_count"),
                "state mismatch count",
            )
            != 0
            or _integer(
                decision.get("activation_count_mismatch_count"),
                "activation mismatch count",
            )
            != 0
            or _number(
                decision.get("max_probability_difference"),
                "maximum probability difference",
            )
            != 0.0
        ):
            raise PreinstrumentationResourceError(
                f"OSS decision is not an exact pass: {decision_id}"
            )
        row_ids = (
            str(decision.get("final_row_identity", "")),
            str(decision.get("omega_row_identity", "")),
        )
        if row_ids[0] == row_ids[1]:
            raise PreinstrumentationResourceError(
                f"OSS decision rows are not distinct: {decision_id}"
            )
        for row_id in row_ids:
            _, row_root = _cache_entry(
                cache_root,
                "oss_rows",
                row_id,
                frozenset(
                    {
                        "fiber_ids.npy",
                        "probabilities.npy",
                        "row_metadata.json",
                    }
                ),
            )
            metadata = _read_json(
                row_root / "row_metadata.json",
                f"OSS row metadata {row_id}",
            )
            n_fibers = _integer(
                metadata.get("n_fibers"),
                f"OSS row fiber count {row_id}",
                minimum=1,
            )
            if (
                metadata.get("schema_version") != "dual_frequency_oss_row_v2"
                or metadata.get("scientific_identity") != row_id
            ):
                raise PreinstrumentationResourceError(
                    f"OSS row metadata identity differs: {row_id}"
                )
            existing = rows.get(row_id)
            row = {
                "row_identity": row_id,
                "n_fibers": n_fibers,
                "row_metadata_sha256": _sha256_file(
                    row_root / "row_metadata.json"
                ),
            }
            if existing is not None and existing != row:
                raise PreinstrumentationResourceError(
                    f"OSS row metadata is inconsistent: {row_id}"
                )
            rows[row_id] = row
        decisions[decision_id] = {
            "decision_id": decision_id,
            "group_id": group_id,
            "final_row_identity": row_ids[0],
            "omega_row_identity": row_ids[1],
            "decision_sha256": _sha256_file(decision_root / "decision.json"),
        }
    maximum = max(row["n_fibers"] for row in rows.values())
    maximum_rows = sorted(
        row_id for row_id, row in rows.items() if row["n_fibers"] == maximum
    )
    return (
        {
            "gate_count": len(gates),
            "decision_count": len(decisions),
            "unique_row_count": len(rows),
            "maximum_n_fibers": maximum,
            "maximum_row_identities": maximum_rows,
            "gates": sorted(gates, key=lambda item: item["group_id"]),
            "rows": [rows[row_id] for row_id in sorted(rows)],
        },
        decisions,
    )


def _guard_rows(
    path: Path,
    *,
    max_rss_bytes: int,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    fields = {
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
            if set(reader.fieldnames or ()) != fields:
                raise PreinstrumentationResourceError("guard CSV fields differ")
            raw_rows = [dict(row) for row in reader]
    except OSError as exc:
        raise PreinstrumentationResourceError(
            f"cannot read guard CSV: {path}"
        ) from exc
    if not raw_rows:
        raise PreinstrumentationResourceError("guard CSV contains no samples")
    parsed: list[dict[str, Any]] = []
    epochs: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    previous_peak: int | None = None
    current: dict[str, Any] | None = None
    maximum_gap = 0.0
    for line, row in enumerate(raw_rows, start=2):
        timestamp = _timestamp(row.get("timestamp_utc"), f"guard line {line} time")
        if previous_time is not None:
            gap = (timestamp - previous_time).total_seconds()
            if gap <= 0:
                raise PreinstrumentationResourceError(
                    "guard timestamps are not strictly increasing"
                )
            maximum_gap = max(maximum_gap, gap)
        try:
            tree_rss = int(row.get("tree_rss_bytes", ""))
            peak_rss = int(row.get("peak_tree_rss_bytes", ""))
            swap_used = int(row.get("swap_used_bytes", ""))
            baseline = int(row.get("swap_baseline_bytes", ""))
        except ValueError as exc:
            raise PreinstrumentationResourceError(
                f"guard integer is invalid on line {line}"
            ) from exc
        if min(tree_rss, peak_rss, swap_used, baseline) < 0:
            raise PreinstrumentationResourceError(
                f"guard integer is negative on line {line}"
            )
        _number(row.get("tree_cpu_percent"), "guard tree CPU")
        event = str(row.get("event", "")).strip()
        if event not in _ALLOWED_GUARD_EVENTS:
            raise PreinstrumentationResourceError(
                f"guard contains a stop or unsupported event: {event}"
            )
        if tree_rss >= max_rss_bytes or peak_rss >= max_rss_bytes:
            raise PreinstrumentationResourceError("guard RSS reached its ceiling")
        if max(0, swap_used - baseline) >= 1:
            raise PreinstrumentationResourceError(
                "guard swap growth is not below one byte"
            )
        new_epoch = (
            current is None
            or baseline != current["swap_baseline_bytes"]
            or (previous_peak is not None and peak_rss < previous_peak)
        )
        if new_epoch:
            current = {
                "epoch_index": len(epochs),
                "start_utc": timestamp.isoformat(),
                "finish_utc": timestamp.isoformat(),
                "sample_count": 0,
                "swap_baseline_bytes": baseline,
                "peak_task_tree_rss_bytes": 0,
            }
            epochs.append(current)
            previous_peak = None
        if peak_rss < tree_rss or (
            previous_peak is not None and peak_rss < previous_peak
        ):
            raise PreinstrumentationResourceError(
                "guard running RSS peak is inconsistent"
            )
        assert current is not None
        current["finish_utc"] = timestamp.isoformat()
        current["sample_count"] += 1
        current["peak_task_tree_rss_bytes"] = max(
            current["peak_task_tree_rss_bytes"],
            peak_rss,
        )
        parsed.append(
            {
                "timestamp": timestamp,
                "epoch_index": current["epoch_index"],
                "tree_rss_bytes": tree_rss,
                "peak_tree_rss_bytes": peak_rss,
                "swap_baseline_bytes": baseline,
            }
        )
        previous_time = timestamp
        previous_peak = peak_rss
    return (
        {
            "guard_sha256": _sha256_file(path),
            "sample_count": len(parsed),
            "epoch_count": len(epochs),
            "start_utc": parsed[0]["timestamp"].isoformat(),
            "finish_utc": parsed[-1]["timestamp"].isoformat(),
            "maximum_sample_gap_seconds": maximum_gap,
            "peak_task_tree_rss_bytes": max(
                row["peak_tree_rss_bytes"] for row in parsed
            ),
            "epochs": epochs,
            "status": "validated",
        },
        tuple(parsed),
    )


def _measurement_windows(
    path: Path,
    *,
    run_id: str,
    rows: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]],
    guard_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    document = _read_json(path, "measurement windows")
    windows = document.get("windows")
    if (
        document.get("schema_version") != _WINDOW_SCHEMA
        or document.get("run_id") != run_id
        or not isinstance(windows, list)
        or not windows
    ):
        raise PreinstrumentationResourceError(
            "measurement-window document identity differs"
        )
    maximum_rows = set(rows["maximum_row_identities"])
    accepted: list[dict[str, Any]] = []
    covered_rows: set[str] = set()
    for index, item in enumerate(windows):
        if not isinstance(item, Mapping):
            raise PreinstrumentationResourceError(
                f"measurement window {index} must be an object"
            )
        decision_id = str(item.get("decision_id", "")).strip()
        row_id = str(item.get("row_identity", "")).strip()
        decision = decisions.get(decision_id)
        if (
            decision is None
            or row_id not in {
                decision["final_row_identity"],
                decision["omega_row_identity"],
            }
            or row_id not in maximum_rows
        ):
            raise PreinstrumentationResourceError(
                f"measurement window {index} is not tied to a terminal maximum row"
            )
        start = _timestamp(item.get("start_utc"), f"window {index} start")
        finish = _timestamp(item.get("finish_utc"), f"window {index} finish")
        if finish < start:
            raise PreinstrumentationResourceError(
                f"measurement window {index} has reversed bounds"
            )
        samples = [
            row
            for row in guard_rows
            if start <= row["timestamp"] <= finish
        ]
        if not samples or len({row["epoch_index"] for row in samples}) != 1:
            raise PreinstrumentationResourceError(
                f"measurement window {index} does not select one guard epoch"
            )
        baseline = _integer(
            item.get("guard_epoch_swap_baseline_bytes"),
            f"window {index} swap baseline",
        )
        if any(row["swap_baseline_bytes"] != baseline for row in samples):
            raise PreinstrumentationResourceError(
                f"measurement window {index} guard baseline differs"
            )
        observed_peak = max(row["peak_tree_rss_bytes"] for row in samples)
        declared_peak = _integer(
            item.get("peak_task_tree_rss_bytes"),
            f"window {index} RSS peak",
            minimum=1,
        )
        if declared_peak != observed_peak:
            raise PreinstrumentationResourceError(
                f"measurement window {index} RSS peak differs"
            )
        accepted.append(
            {
                "decision_id": decision_id,
                "row_identity": row_id,
                "start_utc": start.isoformat(),
                "finish_utc": finish.isoformat(),
                "guard_epoch_index": samples[0]["epoch_index"],
                "guard_epoch_swap_baseline_bytes": baseline,
                "sample_count": len(samples),
                "peak_task_tree_rss_bytes": observed_peak,
            }
        )
        covered_rows.add(row_id)
    if not covered_rows:
        raise PreinstrumentationResourceError(
            "no terminal maximum row has a measured guard window"
        )
    return {
        "measurement_windows_sha256": _sha256_file(path),
        "window_count": len(accepted),
        "covered_maximum_row_identities": sorted(covered_rows),
        "windows": accepted,
        "status": "validated",
    }


def _uncovered_intervals(
    segment: Mapping[str, Any],
    guard: Mapping[str, Any],
) -> list[dict[str, str]]:
    started = _timestamp(segment.get("started_at"), "segment start")
    finished = _timestamp(segment.get("finished_at"), "segment finish")
    if finished < started:
        raise PreinstrumentationResourceError("segment bounds are reversed")
    guard_start = _timestamp(guard["start_utc"], "guard start")
    guard_finish = _timestamp(guard["finish_utc"], "guard finish")
    intervals: list[dict[str, str]] = []
    if guard_start > started:
        intervals.append(
            {
                "start_utc": started.isoformat(),
                "finish_utc": min(guard_start, finished).isoformat(),
                "reason": "before_external_guard",
            }
        )
    if guard_finish < finished:
        intervals.append(
            {
                "start_utc": max(guard_finish, started).isoformat(),
                "finish_utc": finished.isoformat(),
                "reason": "after_external_guard",
            }
        )
    return intervals


def validate(
    run_root: Path,
    segment_id: str,
    cache_root: Path,
    guard_csv: Path,
    measurement_windows: Path,
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
        raise PreinstrumentationResourceError(
            "run manifest is not terminal-completed"
        )
    expected_workers = _integer(workers, "expected workers", minimum=1)
    ceiling = _integer(max_rss_bytes, "RSS ceiling", minimum=1)
    segment_path = root / "execution_segments" / f"{segment_id}.json"
    segment = _read_json(segment_path, "execution segment")
    if (
        segment.get("schema_version") != "dual_frequency_execution_segment_v1"
        or segment.get("segment_id") != segment_id
        or segment.get("status") != "finished"
        or segment.get("pool_mode") != "spawn_process"
        or _integer(segment.get("workers"), "segment workers", minimum=1)
        != expected_workers
    ):
        raise PreinstrumentationResourceError(
            "selected pre-instrumentation segment identity differs"
        )
    if "resource_sample_count" in segment:
        raise PreinstrumentationResourceError(
            "instrumented segments must use the strict resource validator"
        )
    tasks, task_documents = _task_closure(root)
    rows, decisions = _gate_closure(
        task_documents,
        cache_root.expanduser().resolve(),
    )
    guard, parsed_guard = _guard_rows(
        guard_csv.expanduser().resolve(),
        max_rss_bytes=ceiling,
    )
    windows = _measurement_windows(
        measurement_windows.expanduser().resolve(),
        run_id=str(manifest["run_id"]),
        rows=rows,
        decisions=decisions,
        guard_rows=parsed_guard,
    )
    return {
        "schema_version": (
            "dual_frequency_task17_preinstrumentation_resource_acceptance_v1"
        ),
        "run_id": manifest["run_id"],
        "run_manifest_sha256": _sha256_file(manifest_path),
        "segment_id": segment_id,
        "segment_sha256": _sha256_file(segment_path),
        "workers": expected_workers,
        "max_rss_bytes": ceiling,
        "evidence_mode": "external_guard_with_maximum_row_windows",
        "continuous_full_span_monitoring": False,
        "tasks": tasks,
        "oss_closure": rows,
        "guard": guard,
        "measurement_windows": windows,
        "uncovered_elapsed_intervals": _uncovered_intervals(segment, guard),
        "scientific_completion_status": "validated",
        "resource_acceptance_status": "validated_preinstrumentation",
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
            raise PreinstrumentationResourceError(
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
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--guard-csv", required=True, type=Path)
    parser.add_argument("--measurement-windows", required=True, type=Path)
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
            arguments.cache_root,
            arguments.guard_csv,
            arguments.measurement_windows,
            workers=arguments.workers,
            max_rss_bytes=arguments.max_rss_bytes,
        )
        if arguments.output is not None:
            _write_report(arguments.output, report)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except PreinstrumentationResourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
