#!/usr/bin/env python3
"""Guard one Task 17 runner tree against mount, RSS, and swap violations."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence


_CSV_FIELDS = (
    "timestamp_utc",
    "tree_rss_bytes",
    "peak_tree_rss_bytes",
    "tree_cpu_percent",
    "swap_used_bytes",
    "swap_baseline_bytes",
    "event",
)
_DEFAULT_RSS_LIMIT_BYTES = 64 * 1024**3


class ResourceGuardError(RuntimeError):
    """Raised when the resource guard cannot produce trustworthy evidence."""


@dataclass(frozen=True)
class ProcessRow:
    """One process snapshot row."""

    pid: int
    parent_pid: int
    rss_bytes: int
    cpu_percent: float


def _process_rows() -> tuple[ProcessRow, ...]:
    try:
        result = subprocess.run(
            ("ps", "-axo", "pid=,ppid=,rss=,%cpu="),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResourceGuardError("cannot read the process table") from exc
    rows: list[ProcessRow] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if len(fields) != 4:
            continue
        try:
            pid = int(fields[0])
            parent_pid = int(fields[1])
            rss_bytes = int(fields[2]) * 1024
            cpu_percent = float(fields[3])
        except ValueError:
            continue
        if pid > 0 and parent_pid >= 0 and rss_bytes >= 0 and cpu_percent >= 0:
            rows.append(ProcessRow(pid, parent_pid, rss_bytes, cpu_percent))
    if not rows:
        raise ResourceGuardError("the process table contains no valid rows")
    return tuple(rows)


def _tree_rows(
    rows: Sequence[ProcessRow],
    root_pid: int,
) -> tuple[ProcessRow, ...]:
    children: dict[int, list[int]] = {}
    by_pid = {row.pid: row for row in rows}
    for row in rows:
        children.setdefault(row.parent_pid, []).append(row.pid)
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        pending.extend(children.get(pid, ()))
    return tuple(by_pid[pid] for pid in seen if pid in by_pid)


def _swap_used_bytes() -> int:
    try:
        result = subprocess.run(
            ("sysctl", "vm.swapusage"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResourceGuardError("cannot read macOS swap usage") from exc
    match = re.search(r"\bused\s*=\s*([0-9]+(?:\.[0-9]+)?)M\b", result.stdout)
    if match is None:
        raise ResourceGuardError("macOS swap usage has an unsupported format")
    return int(round(float(match.group(1)) * 1024**2))


def _mount_is_present(mount_path: Path) -> bool:
    try:
        result = subprocess.run(
            ("mount",),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResourceGuardError("cannot read mounted filesystems") from exc
    return f" on {mount_path} " in result.stdout


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tree_depths(
    rows: Sequence[ProcessRow],
    root_pid: int,
) -> dict[int, int]:
    children: dict[int, list[int]] = {}
    known = {row.pid for row in rows}
    for row in rows:
        children.setdefault(row.parent_pid, []).append(row.pid)
    depths: dict[int, int] = {}
    pending = [(root_pid, 0)]
    while pending:
        pid, depth = pending.pop()
        if pid in depths or pid not in known:
            continue
        depths[pid] = depth
        pending.extend((child, depth + 1) for child in children.get(pid, ()))
    return depths


def _terminate_tree(rows: Sequence[ProcessRow], root_pid: int) -> None:
    depths = _tree_depths(rows, root_pid)
    for pid in sorted(depths, key=lambda value: (depths[value], value), reverse=True):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise ResourceGuardError(
                f"cannot terminate guarded process {pid}"
            ) from exc


def _validate_output_path(output: Path, mount_path: Path) -> Path:
    destination = output.expanduser().resolve()
    guarded = mount_path.expanduser().resolve()
    if destination == guarded or guarded in destination.parents:
        raise ResourceGuardError(
            "guard evidence must be stored outside the guarded mount"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _open_output(path: Path):
    new_file = not path.exists() or path.stat().st_size < 1
    if not new_file:
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle), None)
        except OSError as exc:
            raise ResourceGuardError("cannot read existing guard evidence") from exc
        if tuple(header or ()) != _CSV_FIELDS:
            raise ResourceGuardError("existing guard CSV header differs")
    try:
        handle = path.open("a", encoding="utf-8", newline="")
    except OSError as exc:
        raise ResourceGuardError("cannot append guard evidence") from exc
    if new_file:
        writer = csv.writer(handle)
        writer.writerow(_CSV_FIELDS)
        handle.flush()
    return handle


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_row(writer: object, handle: object, row: Sequence[object]) -> None:
    try:
        writer.writerow(row)
        handle.flush()
    except OSError as exc:
        raise ResourceGuardError("cannot append guard evidence") from exc


def _fail_closed(
    rows: Sequence[ProcessRow],
    runner_pid: int,
    terminator: Callable[[Sequence[ProcessRow], int], None],
) -> None:
    tree = _tree_rows(rows, runner_pid)
    evidence = (
        rows
        if any(row.pid == runner_pid for row in tree)
        else (ProcessRow(runner_pid, 0, 0, 0.0),)
    )
    terminator(evidence, runner_pid)


def run_guard(
    *,
    runner_pid: int,
    output: Path,
    mount_path: Path,
    max_rss_bytes: int = _DEFAULT_RSS_LIMIT_BYTES,
    interval_seconds: float = 1.0,
    process_reader: Callable[[], tuple[ProcessRow, ...]] = _process_rows,
    swap_reader: Callable[[], int] = _swap_used_bytes,
    mount_reader: Callable[[Path], bool] = _mount_is_present,
    pid_reader: Callable[[int], bool] = _pid_exists,
    terminator: Callable[[Sequence[ProcessRow], int], None] = _terminate_tree,
    sleeper: Callable[[float], None] = time.sleep,
    timestamp_reader: Callable[[], str] = _utc_now,
) -> int:
    """Run until the runner exits or a resource contract triggers a stop."""

    if runner_pid < 2:
        raise ResourceGuardError("runner PID must identify a non-system process")
    if max_rss_bytes < 1:
        raise ResourceGuardError("RSS ceiling must be positive")
    if interval_seconds <= 0:
        raise ResourceGuardError("sample interval must be positive")
    destination = _validate_output_path(output, mount_path)
    baseline_swap = swap_reader()
    if baseline_swap < 0:
        raise ResourceGuardError("swap baseline is negative")
    peak_rss = 0
    with _open_output(destination) as handle:
        writer = csv.writer(handle)
        last_rows: tuple[ProcessRow, ...] = ()
        while True:
            runner_present: bool | None = None
            try:
                timestamp = timestamp_reader()
                rows = process_reader()
                last_rows = rows
                tree = _tree_rows(rows, runner_pid)
                runner_present = any(row.pid == runner_pid for row in tree)
                if not runner_present:
                    if pid_reader(runner_pid):
                        runner_present = True
                        raise ResourceGuardError(
                            "runner PID is live but absent from process snapshot"
                        )
                    _write_row(
                        writer,
                        handle,
                        (
                            timestamp,
                            0,
                            peak_rss,
                            0.0,
                            swap_reader(),
                            baseline_swap,
                            "runner_exit",
                        ),
                    )
                    return 0
                rss_bytes = sum(row.rss_bytes for row in tree)
                cpu_percent = sum(row.cpu_percent for row in tree)
                used_swap = swap_reader()
                if used_swap < 0:
                    raise ResourceGuardError("reported swap usage is negative")
                peak_rss = max(peak_rss, rss_bytes)
                event = "sample"
                if not mount_reader(mount_path):
                    event = "val_unmounted_sigterm"
                elif rss_bytes >= max_rss_bytes:
                    event = "rss_limit_sigterm"
                elif used_swap > baseline_swap:
                    event = "swap_growth_sigterm"
                _write_row(
                    writer,
                    handle,
                    (
                        timestamp,
                        rss_bytes,
                        peak_rss,
                        cpu_percent,
                        used_swap,
                        baseline_swap,
                        event,
                    ),
                )
                if event != "sample":
                    terminator(rows, runner_pid)
                    return 2
                sleeper(interval_seconds)
            except ResourceGuardError:
                if runner_present is not False:
                    _fail_closed(last_rows, runner_pid, terminator)
                raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mount", required=True, type=Path)
    parser.add_argument(
        "--max-rss-bytes",
        type=int,
        default=_DEFAULT_RSS_LIMIT_BYTES,
    )
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return run_guard(
            runner_pid=arguments.runner_pid,
            output=arguments.output,
            mount_path=arguments.mount,
            max_rss_bytes=arguments.max_rss_bytes,
            interval_seconds=arguments.interval_seconds,
        )
    except ResourceGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
