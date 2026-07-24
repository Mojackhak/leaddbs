#!/usr/bin/env python3
"""Derive one SHA-bound Task 17 performance-counter sidecar."""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.instrumentation import _EVENTS, _KEYED_EVENTS


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
_INPUT_FIELDS = frozenset(
    {
        "schema_version",
        "run_root",
        "run_id",
        "segment_id",
        "segment_sha256",
        "event_report_path",
        "event_report_sha256",
        "byte_ledger_path",
        "byte_ledger_sha256",
        "candidate_parity_path",
        "candidate_parity_sha256",
        "artifact_static_audit_path",
        "artifact_static_audit_sha256",
        "benchmark_class",
        "cache_state",
    }
)


class PerformanceCounterBuildError(RuntimeError):
    """Raised when bound counter evidence is incomplete or contradictory."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise PerformanceCounterBuildError(f"{field} must be a SHA-256 digest")
    return digest


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PerformanceCounterBuildError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise PerformanceCounterBuildError(f"{label} must contain an object")
    return value


def _bound_document(
    *,
    raw_path: object,
    raw_sha256: object,
    base: Path,
    label: str,
) -> tuple[Path, dict[str, object], str]:
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    expected = _digest(raw_sha256, f"{label} SHA")
    if not path.is_file() or _sha256_file(path) != expected:
        raise PerformanceCounterBuildError(f"{label} SHA differs")
    return path, _read_json(path, label), expected


def _nonnegative(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise PerformanceCounterBuildError(
            f"{field} must be a nonnegative integer"
        )
    return value


def _normalize_events(
    raw: object,
    *,
    label: str,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    if not isinstance(raw, Mapping):
        raise PerformanceCounterBuildError(f"{label} must contain an object")
    if set(raw) not in ({"scalars", "keyed"}, {"process_identity", "scalars", "keyed"}):
        raise PerformanceCounterBuildError(f"{label} fields differ")
    scalars = raw.get("scalars")
    keyed = raw.get("keyed")
    if not isinstance(scalars, Mapping) or set(scalars) != (_EVENTS - _KEYED_EVENTS):
        raise PerformanceCounterBuildError(f"{label} scalar fields differ")
    if not isinstance(keyed, Mapping) or set(keyed) != _KEYED_EVENTS:
        raise PerformanceCounterBuildError(f"{label} keyed fields differ")
    normalized_scalars = {
        event: _nonnegative(scalars[event], f"{label} scalar {event}")
        for event in sorted(_EVENTS - _KEYED_EVENTS)
    }
    normalized_keyed: dict[str, dict[str, int]] = {}
    for event in sorted(_KEYED_EVENTS):
        values = keyed[event]
        if not isinstance(values, Mapping):
            raise PerformanceCounterBuildError(
                f"{label} keyed event differs: {event}"
            )
        normalized_keyed[event] = {
            str(identity): _nonnegative(
                value,
                f"{label} keyed event {event}:{identity}",
            )
            for identity, value in values.items()
            if str(identity).strip()
        }
        if len(normalized_keyed[event]) != len(values):
            raise PerformanceCounterBuildError(
                f"{label} contains an empty event identity"
            )
    return normalized_scalars, normalized_keyed


def _add_events(
    scalar_totals: dict[str, int],
    keyed_totals: dict[str, dict[str, int]],
    scalars: Mapping[str, int],
    keyed: Mapping[str, Mapping[str, int]],
) -> None:
    for event, value in scalars.items():
        scalar_totals[event] += value
    for event, values in keyed.items():
        totals = keyed_totals[event]
        for identity, value in values.items():
            totals[identity] = totals.get(identity, 0) + value


def _fragment_events(
    report: Mapping[str, object],
) -> tuple[
    dict[str, int],
    dict[str, dict[str, int]],
    dict[tuple[str, str], dict[str, int]],
]:
    if (
        report.get("schema_version")
        != "dual_frequency_performance_event_report_v1"
        or report.get("aggregation_status") != "complete"
        or report.get("missing_fragment_count") != 0
    ):
        raise PerformanceCounterBuildError("performance event report is incomplete")
    fragments = report.get("fragments")
    if not isinstance(fragments, list):
        raise PerformanceCounterBuildError("performance fragment closure differs")
    if report.get("fragment_count") != len(fragments):
        raise PerformanceCounterBuildError("performance fragment count differs")
    scalar_totals = {event: 0 for event in _EVENTS - _KEYED_EVENTS}
    keyed_totals = {event: {} for event in _KEYED_EVENTS}
    process_cache: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"resolve": 0, "verify": 0}
    )
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(fragments):
        if not isinstance(item, Mapping) or set(item) != {
            "task_id",
            "process_identity",
            "path",
            "sha256",
        }:
            raise PerformanceCounterBuildError(
                f"performance fragment reference differs: {index}"
            )
        path = Path(str(item["path"])).expanduser().resolve()
        expected_sha = _digest(item["sha256"], "performance fragment SHA")
        if not path.is_file() or _sha256_file(path) != expected_sha:
            raise PerformanceCounterBuildError(
                f"performance fragment SHA differs: {path}"
            )
        document = _read_json(path, "performance fragment")
        process = str(item["process_identity"]).strip()
        task_id = str(item["task_id"]).strip()
        identity = (process, task_id)
        if not process or not task_id or identity in seen:
            raise PerformanceCounterBuildError(
                "performance fragment identity is empty or duplicated"
            )
        seen.add(identity)
        if (
            document.get("schema_version")
            != "dual_frequency_performance_counter_fragment_v1"
            or document.get("process_identity") != process
            or document.get("task_id") != task_id
        ):
            raise PerformanceCounterBuildError(
                "performance fragment identity differs"
            )
        scalars, keyed = _normalize_events(
            document.get("events"),
            label=f"fragment {index} events",
        )
        _add_events(scalar_totals, keyed_totals, scalars, keyed)
        cache_identities = set(keyed["cache_resolve"]) | set(
            keyed["cache_full_verification"]
        )
        for cache_identity in cache_identities:
            pair = process_cache[(process, cache_identity)]
            pair["resolve"] += keyed["cache_resolve"].get(cache_identity, 0)
            pair["verify"] += keyed["cache_full_verification"].get(
                cache_identity,
                0,
            )
    parent_scalars, parent_keyed = _normalize_events(
        report.get("parent_events"),
        label="parent events",
    )
    _add_events(
        scalar_totals,
        keyed_totals,
        parent_scalars,
        parent_keyed,
    )
    aggregate_scalars, aggregate_keyed = _normalize_events(
        report.get("events"),
        label="reported aggregate events",
    )
    if aggregate_scalars != {
        event: scalar_totals[event] - parent_scalars[event]
        for event in scalar_totals
    }:
        raise PerformanceCounterBuildError(
            "reported scalar aggregate differs from worker fragments"
        )
    expected_worker_keyed = {
        event: {
            identity: value - parent_keyed[event].get(identity, 0)
            for identity, value in keyed_totals[event].items()
            if value - parent_keyed[event].get(identity, 0) > 0
        }
        for event in keyed_totals
    }
    if aggregate_keyed != expected_worker_keyed:
        raise PerformanceCounterBuildError(
            "reported keyed aggregate differs from worker fragments"
        )
    return scalar_totals, keyed_totals, process_cache


def _sum_keyed(values: Mapping[str, int]) -> int:
    return sum(values.values())


def _atomic_publish(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(
        dict(payload),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise PerformanceCounterBuildError(
                "performance counter sidecar differs from existing publication"
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(input_path: Path) -> Path:
    """Validate bound evidence and publish one deterministic counter sidecar."""

    input_path = input_path.expanduser().resolve()
    inputs = _read_json(input_path, "performance counter inputs")
    if set(inputs) != _INPUT_FIELDS:
        raise PerformanceCounterBuildError("performance counter input fields differ")
    if (
        inputs.get("schema_version")
        != "dual_frequency_performance_counter_inputs_v1"
    ):
        raise PerformanceCounterBuildError("performance counter input schema differs")
    run_root = Path(str(inputs["run_root"])).expanduser().resolve()
    if not run_root.is_dir():
        raise PerformanceCounterBuildError("performance run root is missing")
    manifest = _read_json(run_root / "run_manifest.json", "run manifest")
    run_id = str(inputs["run_id"])
    segment_id = str(inputs["segment_id"])
    if (
        manifest.get("run_id") != run_id
        or manifest.get("final_status") != "completed"
    ):
        raise PerformanceCounterBuildError("performance run is not terminal completed")
    segment_path = run_root / "execution_segments" / f"{segment_id}.json"
    segment_sha = _digest(inputs["segment_sha256"], "segment SHA")
    if not segment_path.is_file() or _sha256_file(segment_path) != segment_sha:
        raise PerformanceCounterBuildError("execution segment SHA differs")
    segment = _read_json(segment_path, "execution segment")
    if segment.get("segment_id") != segment_id or segment.get("status") != "finished":
        raise PerformanceCounterBuildError("execution segment is not terminal")
    if inputs["cache_state"] not in {"cold", "warm"}:
        raise PerformanceCounterBuildError("cache state must be cold or warm")
    base = input_path.parent
    event_path, event_report, event_sha = _bound_document(
        raw_path=inputs["event_report_path"],
        raw_sha256=inputs["event_report_sha256"],
        base=base,
        label="performance event report",
    )
    if (
        event_report.get("segment_id") != segment_id
        or Path(str(segment["performance_events_path"])).name != event_path.name
        or segment.get("performance_events_sha256") != event_sha
    ):
        raise PerformanceCounterBuildError(
            "segment performance event binding differs"
        )
    ledger_path, ledger, ledger_sha = _bound_document(
        raw_path=inputs["byte_ledger_path"],
        raw_sha256=inputs["byte_ledger_sha256"],
        base=base,
        label="performance byte ledger",
    )
    if ledger.get("schema_version") != "dual_frequency_performance_byte_ledger_v1":
        raise PerformanceCounterBuildError("performance byte ledger schema differs")
    parity_path, parity, parity_sha = _bound_document(
        raw_path=inputs["candidate_parity_path"],
        raw_sha256=inputs["candidate_parity_sha256"],
        base=base,
        label="candidate parity report",
    )
    if parity.get("schema_version") != "dual_frequency_candidate_parity_v1":
        raise PerformanceCounterBuildError("candidate parity schema differs")
    audit_path, audit, audit_sha = _bound_document(
        raw_path=inputs["artifact_static_audit_path"],
        raw_sha256=inputs["artifact_static_audit_sha256"],
        base=base,
        label="artifact/static audit",
    )
    if (
        audit.get("schema_version")
        != "dual_frequency_artifact_static_audit_v1"
        or audit.get("run_id") != run_id
        or audit.get("segment_id") != segment_id
    ):
        raise PerformanceCounterBuildError("artifact/static audit identity differs")
    nested_sites = audit.get("nested_executor_creation_sites")
    retained_ids = audit.get("retained_null_n_by_f_artifact_ids")
    if not isinstance(nested_sites, list) or not isinstance(retained_ids, list):
        raise PerformanceCounterBuildError("artifact/static audit closure differs")

    scalars, keyed, process_cache = _fragment_events(event_report)
    physical_closure = set(keyed["physical_cache_use"])
    producer_identities = set(keyed["physical_producer"])
    if not physical_closure:
        raise PerformanceCounterBuildError("physical cache identity closure is empty")
    if producer_identities - physical_closure:
        raise PerformanceCounterBuildError(
            "physical producer identity escapes the use closure"
        )
    producer_counts = [
        keyed["physical_producer"].get(identity, 0)
        for identity in sorted(physical_closure)
    ]
    verification_pairs = {
        pair: counts
        for pair, counts in process_cache.items()
        if counts["resolve"] > 0
    }
    if not verification_pairs:
        raise PerformanceCounterBuildError("cache verification closure is empty")
    if any(
        counts["verify"] > 0 and counts["resolve"] < 1
        for counts in process_cache.values()
    ):
        raise PerformanceCounterBuildError(
            "cache verification escapes the resolve closure"
        )
    verification_counts = [
        counts["verify"] for counts in verification_pairs.values()
    ]
    counters = {
        "candidate_false_negative_count": _nonnegative(
            parity.get("candidate_false_negative_count"),
            "candidate false-negative count",
        ),
        "physical_producer_count_min": min(producer_counts),
        "physical_producer_count_max": max(producer_counts),
        "hot_loop_metadata_work_count": _sum_keyed(
            keyed["hot_loop_metadata_work"]
        ),
        "cache_full_verification_count_min": min(verification_counts),
        "cache_full_verification_count_max": max(verification_counts),
        "cache_repeat_verification_count_max": max(
            max(0, value - 1) for value in verification_counts
        ),
        "endpoint_payload_copy_count": _sum_keyed(
            keyed["endpoint_payload_copy"]
        ),
        "nested_executor_creation_count": max(
            _sum_keyed(keyed["executor_creation"]),
            len(nested_sites),
        ),
        "retained_null_n_by_f_output_count": max(
            _sum_keyed(keyed["retained_null_n_by_f_output"]),
            len(retained_ids),
        ),
        "left_transform_resolve_count": _sum_keyed(
            keyed["left_transform_resolve"]
        ),
        "nifti_open_count": _sum_keyed(keyed["nifti_open"]),
        "sampler_build_count": _sum_keyed(keyed["sampler_build"]),
        "sampler_rebuild_count": _sum_keyed(keyed["sampler_rebuild"]),
        "sampler_eviction_count": _sum_keyed(keyed["sampler_eviction"]),
        "connectome_row4_audit_pass_count": _sum_keyed(
            keyed["connectome_row4_audit_pass"]
        ),
        "direct_copy_verification_count": _sum_keyed(
            keyed["direct_copy_verification"]
        ),
        "filtered_connectome_build_count": _sum_keyed(
            keyed["filtered_connectome_build"]
        ),
        "memmap_flush_count": scalars["memmap_flush"],
        "artifact_index_snapshot_count": scalars["artifact_index_snapshot"],
        "payload_read_bytes": scalars["payload_read_bytes"],
        "payload_write_bytes": scalars["payload_write_bytes"],
        "payload_hash_bytes": scalars["payload_hash_bytes"],
        "source_bytes": _nonnegative(ledger.get("source_bytes"), "source bytes"),
        "scratch_bytes": _nonnegative(
            ledger.get("scratch_bytes"),
            "scratch bytes",
        ),
        "cancellation_count": scalars["cancellation"],
        "timeout_count": _nonnegative(
            segment.get("task_timeout_count"),
            "task timeout count",
        ),
        "retry_count": _nonnegative(
            segment.get("transient_retry_count"),
            "transient retry count",
        ),
    }
    if set(counters) != _COUNTERS:
        raise AssertionError("derived performance counter schema differs")
    source_evidence = {
        "inputs_path": str(input_path),
        "inputs_sha256": _sha256_file(input_path),
        "segment_path": str(segment_path),
        "segment_sha256": segment_sha,
        "event_report_path": str(event_path),
        "event_report_sha256": event_sha,
        "byte_ledger_path": str(ledger_path),
        "byte_ledger_sha256": ledger_sha,
        "candidate_parity_path": str(parity_path),
        "candidate_parity_sha256": parity_sha,
        "artifact_static_audit_path": str(audit_path),
        "artifact_static_audit_sha256": audit_sha,
        "benchmark_class": str(inputs["benchmark_class"]),
        "cache_state": str(inputs["cache_state"]),
    }
    output = (
        run_root
        / "execution_segments"
        / f"performance_counters_{segment_id}.json"
    )
    _atomic_publish(
        output,
        {
            "schema_version": "dual_frequency_performance_counters_v1",
            "segment_id": segment_id,
            "source_evidence": source_evidence,
            "counters": counters,
        },
    )
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    output = build(arguments.inputs)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
