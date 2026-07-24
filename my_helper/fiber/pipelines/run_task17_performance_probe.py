#!/usr/bin/env python3
"""Record Task 17 descendant CPU-time and resource evidence for benchmarks."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence

if __package__:
    from .task17_performance_byte_ledger import (
        PerformanceByteLedgerError,
        aggregate_live_index,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task17_performance_byte_ledger import (
        PerformanceByteLedgerError,
        aggregate_live_index,
    )


_CSV_FIELDS = (
    "timestamp_utc",
    "elapsed_monotonic_seconds",
    "process_count",
    "tree_rss_bytes",
    "aggregate_cpu_seconds",
    "swap_used_bytes",
    "source_bytes",
    "scratch_bytes",
    "event",
)


class PerformanceProbeError(RuntimeError):
    """Raised when benchmark evidence cannot be sampled safely."""


@dataclass(frozen=True)
class ProcessSample:
    """One process identity and its cumulative resource counters."""

    pid: int
    create_time: float
    rss_bytes: int
    cpu_seconds: float

    @property
    def identity(self) -> tuple[int, float]:
        return self.pid, self.create_time


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _swap_used_bytes() -> int:
    try:
        result = subprocess.run(
            ("sysctl", "vm.swapusage"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PerformanceProbeError("cannot read macOS swap usage") from exc
    match = re.search(r"\bused\s*=\s*([0-9]+(?:\.[0-9]+)?)M\b", result.stdout)
    if match is None:
        raise PerformanceProbeError("macOS swap usage has an unsupported format")
    return int(round(float(match.group(1)) * 1024**2))


def _process_tree(root_pid: int) -> tuple[ProcessSample, ...]:
    try:
        import psutil
    except ImportError as exc:
        raise PerformanceProbeError("psutil is required for CPU-time evidence") from exc
    try:
        root = psutil.Process(root_pid)
        processes = (root, *root.children(recursive=True))
    except psutil.NoSuchProcess:
        return ()
    rows: list[ProcessSample] = []
    for process in processes:
        try:
            cpu = process.cpu_times()
            rows.append(
                ProcessSample(
                    pid=process.pid,
                    create_time=float(process.create_time()),
                    rss_bytes=int(process.memory_info().rss),
                    cpu_seconds=float(cpu.user + cpu.system),
                )
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return tuple(rows)


def _byte_counters(path: Path) -> tuple[int, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PerformanceProbeError(f"cannot read byte-counter document: {path}") from exc
    if not isinstance(payload, Mapping):
        raise PerformanceProbeError("byte-counter document must contain an object")
    if (
        payload.get("schema_version")
        == "dual_frequency_performance_byte_ledger_index_v1"
    ):
        try:
            aggregate = aggregate_live_index(path)
        except PerformanceByteLedgerError as exc:
            raise PerformanceProbeError(str(exc)) from exc
        return int(aggregate["source_bytes"]), int(aggregate["scratch_bytes"])
    if isinstance(payload.get("counters"), Mapping):
        payload = payload["counters"]
    values: list[int] = []
    for field in ("source_bytes", "scratch_bytes"):
        value = payload.get(field)
        if type(value) is not int or value < 0:
            raise PerformanceProbeError(
                f"byte-counter field must be a nonnegative integer: {field}"
            )
        values.append(value)
    return values[0], values[1]


def _validate_output_path(output: Path, guarded_roots: Sequence[Path]) -> Path:
    destination = output.expanduser().resolve()
    for raw_root in guarded_roots:
        root = raw_root.expanduser().resolve()
        if destination == root or root in destination.parents:
            raise PerformanceProbeError(
                "performance evidence must be stored outside guarded data roots"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _open_output(path: Path):
    if path.exists():
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle), None)
        except OSError as exc:
            raise PerformanceProbeError("cannot read existing probe evidence") from exc
        if tuple(header or ()) != _CSV_FIELDS:
            raise PerformanceProbeError("existing probe CSV header differs")
    handle = path.open("a", encoding="utf-8", newline="")
    if path.stat().st_size < 1:
        csv.writer(handle).writerow(_CSV_FIELDS)
        handle.flush()
        os.fsync(handle.fileno())
    return handle


def run_probe(
    *,
    runner_pid: int,
    output: Path,
    byte_counter_path: Path,
    guarded_roots: Sequence[Path],
    interval_seconds: float = 1.0,
    process_reader: Callable[[int], tuple[ProcessSample, ...]] = _process_tree,
    swap_reader: Callable[[], int] = _swap_used_bytes,
    byte_counter_reader: Callable[[Path], tuple[int, int]] = _byte_counters,
    monotonic_reader: Callable[[], float] = time.monotonic,
    timestamp_reader: Callable[[], str] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Sample until the runner exits while preserving retired-process CPU time."""

    if runner_pid < 2:
        raise PerformanceProbeError("runner PID must identify a non-system process")
    if not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise PerformanceProbeError("sample interval must be positive and finite")
    destination = _validate_output_path(output, guarded_roots)
    started = monotonic_reader()
    previous: dict[tuple[int, float], float] = {}
    retired_cpu_seconds = 0.0
    with _open_output(destination) as handle:
        writer = csv.writer(handle)
        while True:
            now = monotonic_reader()
            rows = process_reader(runner_pid)
            current = {row.identity: row.cpu_seconds for row in rows}
            for identity, cpu_seconds in previous.items():
                if identity not in current:
                    retired_cpu_seconds += cpu_seconds
            for row in rows:
                if (
                    row.pid < 1
                    or row.create_time < 0
                    or row.rss_bytes < 0
                    or not math.isfinite(row.cpu_seconds)
                    or row.cpu_seconds < 0
                ):
                    raise PerformanceProbeError("process sample is invalid")
                prior = previous.get(row.identity)
                if prior is not None and row.cpu_seconds < prior:
                    raise PerformanceProbeError(
                        "process cumulative CPU time decreased"
                    )
            source_bytes, scratch_bytes = byte_counter_reader(byte_counter_path)
            swap = swap_reader()
            if swap < 0:
                raise PerformanceProbeError("reported swap usage is negative")
            aggregate_cpu = retired_cpu_seconds + sum(current.values())
            event = "sample" if rows else "runner_exit"
            writer.writerow(
                (
                    timestamp_reader(),
                    max(0.0, now - started),
                    len(rows),
                    sum(row.rss_bytes for row in rows),
                    aggregate_cpu,
                    swap,
                    source_bytes,
                    scratch_bytes,
                    event,
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
            if not rows:
                return 0
            previous = current
            sleeper(interval_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--byte-counter", required=True, type=Path)
    parser.add_argument(
        "--guarded-root",
        action="append",
        required=True,
        type=Path,
    )
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return run_probe(
            runner_pid=arguments.runner_pid,
            output=arguments.output,
            byte_counter_path=arguments.byte_counter,
            guarded_roots=arguments.guarded_root,
            interval_seconds=arguments.interval_seconds,
        )
    except PerformanceProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
