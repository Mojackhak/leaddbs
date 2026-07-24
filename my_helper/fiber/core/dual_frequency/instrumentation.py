"""Process-local performance events and immutable task delta fragments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
import time
from typing import Mapping, Sequence


_EVENTS = frozenset(
    {
        "physical_producer",
        "hot_loop_metadata_work",
        "cache_full_verification",
        "endpoint_payload_copy",
        "executor_creation",
        "retained_null_n_by_f_output",
        "left_transform_resolve",
        "nifti_open",
        "sampler_build",
        "sampler_rebuild",
        "sampler_eviction",
        "connectome_row4_audit_pass",
        "direct_copy_verification",
        "filtered_connectome_build",
        "memmap_flush",
        "artifact_index_snapshot",
        "payload_read_bytes",
        "payload_write_bytes",
        "payload_hash_bytes",
        "source_bytes",
        "scratch_bytes",
        "cancellation",
        "timeout",
        "retry",
    }
)
_KEYED_EVENTS = frozenset(
    {
        "physical_producer",
        "hot_loop_metadata_work",
        "cache_full_verification",
        "endpoint_payload_copy",
        "executor_creation",
        "retained_null_n_by_f_output",
        "left_transform_resolve",
        "nifti_open",
        "sampler_build",
        "sampler_rebuild",
        "sampler_eviction",
        "connectome_row4_audit_pass",
        "direct_copy_verification",
        "filtered_connectome_build",
    }
)
_PROCESS_IDENTITY = f"{os.getpid()}-{time.time_ns()}"
_LOCK = RLock()
_SCALARS = {event: 0 for event in _EVENTS - _KEYED_EVENTS}
_KEYED = {event: {} for event in _KEYED_EVENTS}


class PerformanceInstrumentationError(RuntimeError):
    """Raised when a performance event or fragment is invalid."""


def process_identity() -> str:
    """Return the stable identity of this imported process instance."""

    return _PROCESS_IDENTITY


def increment_performance_event(
    event: str,
    *,
    amount: int = 1,
    key: str | None = None,
) -> None:
    """Increment one declared process-local event without filesystem I/O."""

    if event not in _EVENTS:
        raise PerformanceInstrumentationError(f"unknown performance event: {event}")
    if type(amount) is not int or amount < 0:
        raise PerformanceInstrumentationError(
            "performance event amount must be a nonnegative integer"
        )
    if event in _KEYED_EVENTS:
        token = "" if key is None else str(key).strip()
        if not token:
            raise PerformanceInstrumentationError(
                f"keyed performance event requires an identity: {event}"
            )
        with _LOCK:
            values = _KEYED[event]
            values[token] = values.get(token, 0) + amount
        return
    if key is not None:
        raise PerformanceInstrumentationError(
            f"scalar performance event cannot carry an identity: {event}"
        )
    with _LOCK:
        _SCALARS[event] += amount


def performance_snapshot() -> dict[str, object]:
    """Return one immutable copy of current process-local event totals."""

    with _LOCK:
        return {
            "process_identity": _PROCESS_IDENTITY,
            "scalars": dict(_SCALARS),
            "keyed": {
                event: dict(values)
                for event, values in _KEYED.items()
            },
        }


def performance_delta(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> dict[str, object]:
    """Calculate a nonnegative delta between snapshots from one process."""

    if (
        before.get("process_identity") != _PROCESS_IDENTITY
        or after.get("process_identity") != _PROCESS_IDENTITY
    ):
        raise PerformanceInstrumentationError(
            "performance snapshots belong to another process"
        )
    before_scalars = before.get("scalars")
    after_scalars = after.get("scalars")
    before_keyed = before.get("keyed")
    after_keyed = after.get("keyed")
    if not all(
        isinstance(value, Mapping)
        for value in (before_scalars, after_scalars, before_keyed, after_keyed)
    ):
        raise PerformanceInstrumentationError("performance snapshot fields differ")
    scalar_delta: dict[str, int] = {}
    for event in sorted(_EVENTS - _KEYED_EVENTS):
        previous = before_scalars.get(event)
        current = after_scalars.get(event)
        if type(previous) is not int or type(current) is not int or current < previous:
            raise PerformanceInstrumentationError(
                f"performance scalar decreased or is invalid: {event}"
            )
        scalar_delta[event] = current - previous
    keyed_delta: dict[str, dict[str, int]] = {}
    for event in sorted(_KEYED_EVENTS):
        previous_values = before_keyed.get(event)
        current_values = after_keyed.get(event)
        if not isinstance(previous_values, Mapping) or not isinstance(
            current_values,
            Mapping,
        ):
            raise PerformanceInstrumentationError(
                f"performance keyed event differs: {event}"
            )
        identities = set(previous_values) | set(current_values)
        event_delta: dict[str, int] = {}
        for identity in sorted(identities):
            previous = previous_values.get(identity, 0)
            current = current_values.get(identity, 0)
            if (
                type(previous) is not int
                or type(current) is not int
                or current < previous
            ):
                raise PerformanceInstrumentationError(
                    f"performance keyed counter decreased: {event}:{identity}"
                )
            if current > previous:
                event_delta[str(identity)] = current - previous
        keyed_delta[event] = event_delta
    return {
        "process_identity": _PROCESS_IDENTITY,
        "scalars": scalar_delta,
        "keyed": keyed_delta,
    }


def write_performance_fragment(
    output_dir: Path,
    *,
    task_id: str,
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> Path:
    """Atomically publish one immutable task delta fragment."""

    task_token = str(task_id).strip()
    if not task_token:
        raise PerformanceInstrumentationError("task ID must be nonempty")
    destination = Path(output_dir) / "performance_counter_fragment.json"
    payload = {
        "schema_version": "dual_frequency_performance_counter_fragment_v1",
        "process_identity": _PROCESS_IDENTITY,
        "task_id": task_token,
        "events": performance_delta(before, after),
    }
    text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_text(encoding="utf-8") != text:
            raise PerformanceInstrumentationError(
                "task performance fragment differs from existing publication"
            )
        return destination
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def aggregate_performance_fragments(
    attempts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate immutable worker fragments without inventing missing evidence."""

    scalar_totals = {event: 0 for event in sorted(_EVENTS - _KEYED_EVENTS)}
    keyed_totals: dict[str, dict[str, int]] = {
        event: {} for event in sorted(_KEYED_EVENTS)
    }
    fragments: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for attempt in attempts:
        task_id = str(attempt.get("task_id", "")).strip()
        output_dir = str(attempt.get("output_dir", "")).strip()
        if not task_id or not output_dir:
            raise PerformanceInstrumentationError(
                "performance attempt requires task_id and output_dir"
            )
        attempt_dir = Path(output_dir)
        path = attempt_dir / "performance_counter_fragment.json"
        if not path.is_file():
            missing.append(
                {
                    "task_id": task_id,
                    "attempt_dir": str(attempt_dir),
                }
            )
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if (
                document.get("schema_version")
                != "dual_frequency_performance_counter_fragment_v1"
                or document.get("task_id") != task_id
            ):
                raise PerformanceInstrumentationError(
                    "performance fragment identity differs"
                )
            events = document["events"]
            process = str(document["process_identity"]).strip()
            if events.get("process_identity") != process:
                raise PerformanceInstrumentationError(
                    "performance fragment process identity differs"
                )
            scalars = events["scalars"]
            keyed = events["keyed"]
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise PerformanceInstrumentationError(
                f"performance fragment is unreadable: {path}"
            ) from exc
        if not process or not isinstance(scalars, Mapping) or not isinstance(
            keyed,
            Mapping,
        ):
            raise PerformanceInstrumentationError(
                f"performance fragment structure differs: {path}"
            )
        for event in scalar_totals:
            value = scalars.get(event)
            if type(value) is not int or value < 0:
                raise PerformanceInstrumentationError(
                    f"performance scalar is invalid: {path}:{event}"
                )
            scalar_totals[event] += value
        for event in keyed_totals:
            values = keyed.get(event)
            if not isinstance(values, Mapping):
                raise PerformanceInstrumentationError(
                    f"performance keyed event is invalid: {path}:{event}"
                )
            for identity, value in values.items():
                token = str(identity).strip()
                if not token or type(value) is not int or value < 0:
                    raise PerformanceInstrumentationError(
                        f"performance keyed value is invalid: {path}:{event}"
                    )
                totals = keyed_totals[event]
                totals[token] = totals.get(token, 0) + value
        fragments.append(
            {
                "task_id": task_id,
                "process_identity": process,
                "path": str(path),
            }
        )
    return {
        "schema_version": "dual_frequency_performance_event_report_v1",
        "scheduled_attempt_count": len(attempts),
        "fragment_count": len(fragments),
        "missing_fragment_count": len(missing),
        "aggregation_status": "complete" if not missing else "incomplete",
        "fragments": fragments,
        "missing_fragments": missing,
        "events": {
            "scalars": scalar_totals,
            "keyed": keyed_totals,
        },
    }


__all__ = [
    "PerformanceInstrumentationError",
    "aggregate_performance_fragments",
    "increment_performance_event",
    "performance_delta",
    "performance_snapshot",
    "process_identity",
    "write_performance_fragment",
]
