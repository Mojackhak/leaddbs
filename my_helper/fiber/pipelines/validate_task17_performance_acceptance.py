#!/usr/bin/env python3
"""Validate the complete Task 17 cold/warm performance matrix."""

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
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

import yaml


_WORKERS = (1, 3, 6, 12)
_NON_PPAM_CLASSES = (
    "direct_voxel",
    "formal_permutation",
    "bootstrap",
    "spatial_jitter",
)
_COUNTERS = frozenset(
    {
        "candidate_false_negative_count",
        "physical_producer_count_min",
        "physical_producer_count_max",
        "hot_loop_metadata_work_count",
        "cache_full_verification_count_min",
        "cache_full_verification_count_max",
        "cache_repeat_verification_count_max",
        "endpoint_payload_copy_count",
        "nested_executor_creation_count",
        "retained_null_n_by_f_output_count",
        "left_transform_resolve_count",
        "nifti_open_count",
        "sampler_build_count",
        "sampler_rebuild_count",
        "sampler_eviction_count",
        "connectome_row4_audit_pass_count",
        "direct_copy_verification_count",
        "filtered_connectome_build_count",
        "memmap_flush_count",
        "artifact_index_snapshot_count",
        "payload_read_bytes",
        "payload_write_bytes",
        "payload_hash_bytes",
        "source_bytes",
        "scratch_bytes",
        "cancellation_count",
        "timeout_count",
        "retry_count",
    }
)
_NON_WORKER_ADMISSION_REASONS = frozenset(
    {
        "cpu",
        "managed_memory",
        "memory_reserve",
        "connectome_io",
        "external_solver",
    }
)


class PerformanceAcceptanceError(RuntimeError):
    """Raised when performance evidence is incomplete or fails a gate."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PerformanceAcceptanceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise PerformanceAcceptanceError(f"{label} must contain an object")
    return value


def _sha(value: object, label: str) -> str:
    token = str(value).strip().lower()
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise PerformanceAcceptanceError(f"{label} must be a SHA-256 digest")
    return token


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PerformanceAcceptanceError(f"{label} must be a nonnegative integer")
    return int(value)


def _number(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PerformanceAcceptanceError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or result < 0:
        raise PerformanceAcceptanceError(f"{label} must be finite and nonnegative")
    return result


def _required_keys(
    value: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise PerformanceAcceptanceError(f"{label} fields differ from the schema")


def _row_key(row: Mapping[str, object]) -> tuple[str, str | None, str, str, int]:
    connectome = row["connectome_id"]
    if connectome is not None and (not isinstance(connectome, str) or not connectome):
        raise PerformanceAcceptanceError("connectome_id must be null or nonempty")
    workers = row["workers"]
    if type(workers) is not int or workers not in _WORKERS:
        raise PerformanceAcceptanceError("workers must be one of 1, 3, 6, or 12")
    return (
        str(row["benchmark_class"]),
        connectome,
        str(row["cache_state"]),
        str(row["solver_mode"]),
        workers,
    )


def _expected_keys(connectomes: Sequence[str]) -> set[tuple[str, str | None, str, str, int]]:
    expected: set[tuple[str, str | None, str, str, int]] = set()
    classes = tuple((name, None) for name in _NON_PPAM_CLASSES) + tuple(
        ("fiber_connectome", connectome) for connectome in connectomes
    )
    for benchmark_class, connectome in classes:
        for cache_state in ("cold", "warm"):
            for workers in _WORKERS:
                expected.add(
                    (benchmark_class, connectome, cache_state, "none", workers)
                )
    for cache_state in ("cold", "warm"):
        for workers in _WORKERS:
            expected.add(("ppam", None, cache_state, "injected", workers))
    for workers in _WORKERS:
        expected.add(("ppam", None, "warm", "real_cache_hit", workers))
        expected.add(("ppam", None, "cold", "real_solver", workers))
    return expected


def _read_probe(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    expected = {
        "timestamp_utc",
        "elapsed_monotonic_seconds",
        "process_count",
        "tree_rss_bytes",
        "aggregate_cpu_seconds",
        "swap_used_bytes",
        "source_bytes",
        "scratch_bytes",
        "event",
    }
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if set(reader.fieldnames or ()) != expected:
                raise PerformanceAcceptanceError("probe CSV fields differ")
            raw_rows = list(reader)
    except OSError as exc:
        raise PerformanceAcceptanceError(f"cannot read probe CSV: {path}") from exc
    if len(raw_rows) < 2 or raw_rows[-1]["event"] != "runner_exit":
        raise PerformanceAcceptanceError("probe must contain samples and runner_exit")
    rows: list[dict[str, object]] = []
    previous_elapsed = -1.0
    previous_cpu = -1.0
    previous_source_bytes = -1
    previous_scratch_bytes = -1
    previous_timestamp: datetime | None = None
    for line, raw in enumerate(raw_rows, start=2):
        try:
            timestamp = datetime.fromisoformat(raw["timestamp_utc"])
        except ValueError as exc:
            raise PerformanceAcceptanceError(
                f"probe timestamp is invalid on line {line}"
            ) from exc
        if (
            timestamp.utcoffset() is None
            or timestamp.utcoffset().total_seconds() != 0
            or (
                previous_timestamp is not None
                and timestamp <= previous_timestamp
            )
        ):
            raise PerformanceAcceptanceError(
                "probe timestamps must be strictly increasing UTC values"
            )
        elapsed = _number(raw["elapsed_monotonic_seconds"], "probe elapsed")
        cpu = _number(raw["aggregate_cpu_seconds"], "probe CPU")
        try:
            process_count = int(raw["process_count"])
            rss = int(raw["tree_rss_bytes"])
            swap = int(raw["swap_used_bytes"])
            source_bytes = int(raw["source_bytes"])
            scratch_bytes = int(raw["scratch_bytes"])
        except ValueError as exc:
            raise PerformanceAcceptanceError(
                f"probe integer field is invalid on line {line}"
            ) from exc
        if (
            elapsed <= previous_elapsed
            or cpu < previous_cpu
            or source_bytes < previous_source_bytes
            or scratch_bytes < previous_scratch_bytes
        ):
            raise PerformanceAcceptanceError("probe counters are not monotonic")
        is_last = line == len(raw_rows) + 1
        expected_event = "runner_exit" if is_last else "sample"
        if (
            raw["event"] != expected_event
            or (is_last and (process_count != 0 or rss != 0))
            or (not is_last and process_count < 1)
        ):
            raise PerformanceAcceptanceError(
                "probe sample and runner-exit boundary differs"
            )
        row = {
            "timestamp": timestamp,
            "elapsed": elapsed,
            "cpu": cpu,
            "process_count": process_count,
            "rss": rss,
            "swap": swap,
            "source_bytes": source_bytes,
            "scratch_bytes": scratch_bytes,
            "event": raw["event"],
        }
        if min(
            row["process_count"],
            row["rss"],
            row["swap"],
            row["source_bytes"],
            row["scratch_bytes"],
        ) < 0:
            raise PerformanceAcceptanceError("probe byte counter is negative")
        rows.append(row)
        previous_elapsed = elapsed
        previous_cpu = cpu
        previous_source_bytes = source_bytes
        previous_scratch_bytes = scratch_bytes
        previous_timestamp = timestamp
    wall = float(rows[-1]["elapsed"]) - float(rows[0]["elapsed"])
    cpu = float(rows[-1]["cpu"]) - float(rows[0]["cpu"])
    if wall <= 0:
        raise PerformanceAcceptanceError("probe wall time must be positive")
    return rows, {
        "sha256": _sha256_file(path),
        "sample_count": len(rows),
        "wall_seconds": wall,
        "aggregate_cpu_seconds": cpu,
        "effective_cores": cpu / wall,
        "peak_rss_bytes": max(int(row["rss"]) for row in rows),
        "swap_delta_bytes": max(int(row["swap"]) for row in rows)
        - int(rows[0]["swap"]),
        "source_bytes": int(rows[-1]["source_bytes"]),
        "scratch_bytes": int(rows[-1]["scratch_bytes"]),
    }


def _cpu_at(rows: Sequence[Mapping[str, object]], timestamp: datetime) -> float:
    for left, right in zip(rows, rows[1:], strict=False):
        left_time = left["timestamp"]
        right_time = right["timestamp"]
        if not isinstance(left_time, datetime) or not isinstance(right_time, datetime):
            raise PerformanceAcceptanceError("probe timestamp type differs")
        if left_time <= timestamp <= right_time:
            span = (right_time - left_time).total_seconds()
            if span <= 0:
                raise PerformanceAcceptanceError("probe timestamp span is invalid")
            fraction = (timestamp - left_time).total_seconds() / span
            return float(left["cpu"]) + fraction * (
                float(right["cpu"]) - float(left["cpu"])
            )
    raise PerformanceAcceptanceError("scheduler window escapes probe envelope")


def _scheduler_windows(
    run_root: Path,
    segment: Mapping[str, object],
    probe: Sequence[Mapping[str, object]],
    workers: int,
) -> dict[str, object]:
    relative = segment.get("scheduler_windows_path")
    if not isinstance(relative, str) or not relative:
        raise PerformanceAcceptanceError("segment lacks scheduler-window path")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise PerformanceAcceptanceError(
            "scheduler-window path must be relative"
        )
    path = (run_root / relative_path).resolve()
    if run_root.resolve() not in path.parents:
        raise PerformanceAcceptanceError("scheduler-window path escapes run root")
    expected_sha = _sha(
        segment.get("scheduler_windows_sha256"),
        "scheduler-window SHA",
    )
    if _sha256_file(path) != expected_sha:
        raise PerformanceAcceptanceError("scheduler-window SHA differs")
    document = _read_json(path, "scheduler windows")
    rows = document.get("rows")
    if (
        document.get("schema_version") != "dual_frequency_scheduler_windows_v1"
        or document.get("segment_id") != segment.get("segment_id")
        or not isinstance(rows, list)
        or len(rows) != segment.get("scheduler_window_count")
        or not rows
    ):
        raise PerformanceAcceptanceError("scheduler-window closure differs")
    eligible = 0
    above_six = 0
    windows: list[dict[str, object]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise PerformanceAcceptanceError("scheduler window must be an object")
        try:
            start = datetime.fromisoformat(str(raw["start_utc"]))
            finish = datetime.fromisoformat(str(raw["finish_utc"]))
        except (KeyError, ValueError) as exc:
            raise PerformanceAcceptanceError("scheduler window timestamp differs") from exc
        elapsed = (finish - start).total_seconds()
        if elapsed <= 0:
            raise PerformanceAcceptanceError("scheduler window is not positive")
        reasons = raw.get("admission_blocked_task_count_by_reason")
        if not isinstance(reasons, Mapping):
            raise PerformanceAcceptanceError("scheduler admission reasons differ")
        non_worker_block = any(
            _integer(reasons.get(reason), f"scheduler reason {reason}") > 0
            for reason in _NON_WORKER_ADMISSION_REASONS
        )
        is_eligible = (
            workers == 12
            and _integer(raw.get("runnable_cpu_slots"), "runnable CPU slots") > 5
            and not non_worker_block
            and raw.get("storage_limited") is False
        )
        effective = (_cpu_at(probe, finish) - _cpu_at(probe, start)) / elapsed
        if effective < 0:
            raise PerformanceAcceptanceError("window effective cores are negative")
        eligible += int(is_eligible)
        above_six += int(is_eligible and effective > 6)
        windows.append(
            {
                "index": index,
                "effective_cores": effective,
                "eligible": is_eligible,
            }
        )
    return {
        "path": str(path),
        "sha256": expected_sha,
        "window_count": len(windows),
        "eligible_window_count": eligible,
        "eligible_above_six_count": above_six,
        "eligible_above_six_fraction": (
            None if eligible < 1 else above_six / eligible
        ),
        "windows": windows,
    }


def _validate_counters(raw: object, *, cache_state: str) -> dict[str, int]:
    if not isinstance(raw, Mapping) or set(raw) != _COUNTERS:
        raise PerformanceAcceptanceError("performance counters differ from the schema")
    counters = {field: _integer(raw[field], f"counter {field}") for field in _COUNTERS}
    if counters["candidate_false_negative_count"] > 0:
        raise PerformanceAcceptanceError("candidate false negatives are present")
    expected_producers = 1 if cache_state == "cold" else 0
    if counters["physical_producer_count_min"] != expected_producers:
        raise PerformanceAcceptanceError("physical producer minimum differs")
    if counters["physical_producer_count_max"] != expected_producers:
        raise PerformanceAcceptanceError("physical producer maximum differs")
    if not 0 < counters["cache_full_verification_count_min"] < 2:
        raise PerformanceAcceptanceError("full cache verification minimum differs")
    if not 0 < counters["cache_full_verification_count_max"] < 2:
        raise PerformanceAcceptanceError("full cache verification maximum differs")
    for field in (
        "hot_loop_metadata_work_count",
        "cache_repeat_verification_count_max",
        "endpoint_payload_copy_count",
        "nested_executor_creation_count",
        "retained_null_n_by_f_output_count",
        "sampler_rebuild_count",
        "sampler_eviction_count",
        "cancellation_count",
        "timeout_count",
        "retry_count",
    ):
        if counters[field] > 0:
            raise PerformanceAcceptanceError(f"counter gate failed: {field}")
    return counters


def _validate_executed_row(
    row: Mapping[str, object],
    *,
    max_rss_bytes: int,
) -> dict[str, object]:
    run_root = Path(str(row["run_root"])).expanduser().resolve()
    manifest = _read_json(run_root / "run_manifest.json", "run manifest")
    if manifest.get("final_status") != "completed":
        raise PerformanceAcceptanceError("benchmark run is not completed")
    segment_id = str(row["segment_id"]).strip()
    if re.fullmatch(r"segment_[0-9]+", segment_id) is None:
        raise PerformanceAcceptanceError(
            "benchmark segment ID is invalid"
        )
    segment_path = run_root / "execution_segments" / f"{segment_id}.json"
    segment = _read_json(segment_path, "execution segment")
    workers = int(row["workers"])
    if (
        segment.get("status") != "finished"
        or segment.get("pool_mode") != "spawn_process"
        or segment.get("workers") != workers
        or segment.get("pool_generation_count") != 1
    ):
        raise PerformanceAcceptanceError("execution segment boundary differs")
    configuration = run_root / "configuration_resolved.yaml"
    if _sha256_file(configuration) != _sha(
        row["configuration_sha256"],
        "configuration SHA",
    ):
        raise PerformanceAcceptanceError("resolved configuration SHA differs")
    try:
        configuration_document = yaml.safe_load(
            configuration.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PerformanceAcceptanceError(
            "cannot read resolved benchmark configuration"
        ) from exc
    if (
        not isinstance(configuration_document, Mapping)
        or not isinstance(configuration_document.get("execution"), Mapping)
        or configuration_document["execution"].get("workers") != workers
    ):
        raise PerformanceAcceptanceError(
            "resolved configuration worker ceiling differs"
        )
    probe_path = Path(str(row["probe_csv"])).expanduser().resolve()
    probe_rows, probe_summary = _read_probe(probe_path)
    if probe_summary["peak_rss_bytes"] >= max_rss_bytes:
        raise PerformanceAcceptanceError("benchmark RSS reached its ceiling")
    if probe_summary["swap_delta_bytes"] > 0:
        raise PerformanceAcceptanceError("benchmark swap increased")
    scheduler = _scheduler_windows(run_root, segment, probe_rows, workers)
    counter_path = Path(str(row["counter_path"])).expanduser().resolve()
    if counter_path != run_root and run_root not in counter_path.parents:
        raise PerformanceAcceptanceError("counter sidecar escapes benchmark run")
    expected_counter_sha = _sha(row["counter_sha256"], "counter sidecar SHA")
    if _sha256_file(counter_path) != expected_counter_sha:
        raise PerformanceAcceptanceError("counter sidecar SHA differs")
    counter_document = _read_json(counter_path, "performance counter sidecar")
    if (
        counter_document.get("schema_version")
        != "dual_frequency_performance_counters_v1"
        or counter_document.get("segment_id") != segment_id
        or set(counter_document)
        != {"schema_version", "segment_id", "source_evidence", "counters"}
    ):
        raise PerformanceAcceptanceError("performance counter sidecar differs")
    source_evidence = counter_document["source_evidence"]
    if (
        not isinstance(source_evidence, Mapping)
        or source_evidence.get("segment_sha256") != _sha256_file(segment_path)
        or source_evidence.get("event_report_sha256")
        != segment.get("performance_events_sha256")
    ):
        raise PerformanceAcceptanceError(
            "performance counter source evidence differs"
        )
    counters = _validate_counters(
        counter_document["counters"],
        cache_state=str(row["cache_state"]),
    )
    if (
        counters["source_bytes"] != probe_summary["source_bytes"]
        or counters["scratch_bytes"] != probe_summary["scratch_bytes"]
    ):
        raise PerformanceAcceptanceError("probe and terminal byte counters differ")
    if (
        workers == 12
        and row["io_classification"] == "compute_bound"
        and (
            scheduler["eligible_window_count"] < 1
            or float(scheduler["eligible_above_six_fraction"]) <= 0.80
        )
    ):
        raise PerformanceAcceptanceError("12-worker utilization gate failed")
    return {
        "status": "validated",
        "run_manifest_sha256": _sha256_file(run_root / "run_manifest.json"),
        "segment_sha256": _sha256_file(segment_path),
        "configuration_sha256": row["configuration_sha256"],
        "numerical_identity_sha256": _sha(
            row["numerical_identity_sha256"],
            "numerical identity",
        ),
        "probe": probe_summary,
        "scheduler": scheduler,
        "counters": counters,
        "counter_sidecar_sha256": expected_counter_sha,
        "io_classification": row["io_classification"],
    }


_ROW_FIELDS = {
    "benchmark_class",
    "connectome_id",
    "cache_state",
    "solver_mode",
    "workers",
    "status",
    "not_run_reason",
    "preflight_path",
    "preflight_sha256",
    "run_root",
    "segment_id",
    "probe_csv",
    "configuration_sha256",
    "numerical_identity_sha256",
    "io_classification",
    "counter_path",
    "counter_sha256",
}


def validate(manifest_path: Path) -> dict[str, object]:
    """Validate exact matrix closure and every executed row."""

    manifest_path = manifest_path.expanduser().resolve()
    document = _read_json(manifest_path, "performance matrix")
    _required_keys(
        document,
        {
            "schema_version",
            "configured_connectomes",
            "chosen_default_workers",
            "max_rss_bytes",
            "rows",
        },
        "performance matrix",
    )
    if document["schema_version"] != "dual_frequency_task17_performance_matrix_v1":
        raise PerformanceAcceptanceError("performance matrix schema differs")
    connectomes = document["configured_connectomes"]
    if (
        not isinstance(connectomes, list)
        or not connectomes
        or len(set(connectomes)) != len(connectomes)
        or any(not isinstance(item, str) or not item for item in connectomes)
    ):
        raise PerformanceAcceptanceError("configured connectome closure differs")
    chosen = document["chosen_default_workers"]
    if type(chosen) is not int or chosen not in _WORKERS:
        raise PerformanceAcceptanceError("chosen default workers differs")
    max_rss = _integer(document["max_rss_bytes"], "maximum RSS")
    rows = document["rows"]
    if not isinstance(rows, list):
        raise PerformanceAcceptanceError("performance rows must be an array")
    indexed: dict[tuple[str, str | None, str, str, int], Mapping[str, object]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise PerformanceAcceptanceError("performance row must be an object")
        _required_keys(raw, _ROW_FIELDS, f"performance row {index}")
        key = _row_key(raw)
        if key in indexed:
            raise PerformanceAcceptanceError(f"duplicate performance row: {key}")
        indexed[key] = raw
    expected = _expected_keys(connectomes)
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed), key=str)
        extra = sorted(set(indexed) - expected, key=str)
        raise PerformanceAcceptanceError(
            f"performance matrix closure differs; missing={missing}; extra={extra}"
        )
    results: list[dict[str, object]] = []
    identities: dict[tuple[str, str | None, str], str] = {}
    for key in sorted(indexed, key=str):
        row = indexed[key]
        status = row["status"]
        if status == "not_run":
            if key[0:4] != ("ppam", None, "cold", "real_solver"):
                raise PerformanceAcceptanceError("only real cold solver may be not_run")
            if row["not_run_reason"] != "real_cold_solver_not_authorized":
                raise PerformanceAcceptanceError("real cold not_run reason differs")
            preflight = Path(str(row["preflight_path"])).expanduser().resolve()
            if _sha256_file(preflight) != _sha(
                row["preflight_sha256"],
                "preflight SHA",
            ):
                raise PerformanceAcceptanceError("not_run preflight SHA differs")
            preflight_document = _read_json(preflight, "not_run preflight")
            if preflight_document.get("authorized") is not False:
                raise PerformanceAcceptanceError(
                    "not_run preflight does not prove missing authorization"
                )
            evidence: dict[str, object] = {
                "status": "not_run",
                "preflight_sha256": row["preflight_sha256"],
            }
        elif status == "executed":
            if row["not_run_reason"] is not None:
                raise PerformanceAcceptanceError("executed row has not_run reason")
            evidence = _validate_executed_row(row, max_rss_bytes=max_rss)
            identity_key = (key[0], key[1], key[3])
            identity = str(evidence["numerical_identity_sha256"])
            prior = identities.setdefault(identity_key, identity)
            if prior != identity:
                raise PerformanceAcceptanceError(
                    f"worker/cache numerical identity differs: {identity_key}"
                )
        else:
            raise PerformanceAcceptanceError("performance row status differs")
        results.append(
            {
                "key": {
                    "benchmark_class": key[0],
                    "connectome_id": key[1],
                    "cache_state": key[2],
                    "solver_mode": key[3],
                    "workers": key[4],
                },
                "evidence": evidence,
            }
        )
    if chosen != 3:
        result_index = {
            (
                item["key"]["benchmark_class"],
                item["key"]["connectome_id"],
                item["key"]["cache_state"],
                item["key"]["solver_mode"],
                item["key"]["workers"],
            ): item["evidence"]
            for item in results
        }
        compared = 0
        for key, chosen_evidence in result_index.items():
            if key[4] != chosen or chosen_evidence["status"] != "validated":
                continue
            baseline_key = (*key[:4], 3)
            baseline = result_index.get(baseline_key)
            if (
                baseline is None
                or baseline["status"] != "validated"
                or chosen_evidence.get("io_classification") != "compute_bound"
            ):
                continue
            compared += 1
            if (
                chosen_evidence["probe"]["wall_seconds"]
                >= baseline["probe"]["wall_seconds"]
            ):
                raise PerformanceAcceptanceError(
                    "chosen non-default worker count is not faster than workers 3"
                )
        if compared < 1:
            raise PerformanceAcceptanceError(
                "chosen non-default worker count lacks compute-bound comparisons"
            )
    return {
        "schema_version": "dual_frequency_task17_performance_acceptance_v1",
        "status": "validated",
        "input_manifest_sha256": _sha256_file(manifest_path),
        "configured_connectomes": list(connectomes),
        "chosen_default_workers": chosen,
        "row_count": len(results),
        "rows": results,
    }


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        dict(report),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    if destination.exists() and destination.read_text(encoding="utf-8") == text:
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(arguments.manifest)
        _write_report(arguments.output, report)
    except PerformanceAcceptanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
