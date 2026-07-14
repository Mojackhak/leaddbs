"""Resource accounting and external-process lifecycle tests."""

from __future__ import annotations

from pathlib import Path
import sys
import threading
import time

import psutil
import pytest

from ..errors import ExecutionInterrupted
from ..resources import ResourcePool
from ..tools import request_stop, reset_stop_request, run_command


def test_observed_rss_controls_admission_and_reports_over_reservation() -> None:
    pool = ResourcePool(cpu_budget=2, memory_capacity_gb=4.0)
    admitted = threading.Event()

    def reserve_second() -> None:
        with pool.reserve(cpu=1, memory_gb=1.0, label="second"):
            admitted.set()

    with pool.reserve(cpu=1, memory_gb=1.0, label="first") as lease:
        assert lease.snapshot.used_memory_gb == 1.0
        lease.observe_memory_gb(3.5)
        assert lease.snapshot.used_memory_gb == 3.5
        worker = threading.Thread(target=reserve_second)
        worker.start()
        assert not admitted.wait(timeout=0.1)
        lease.observe_memory_gb(0.25)
        assert admitted.wait(timeout=1.0)
        worker.join(timeout=1.0)
        assert not worker.is_alive()

    report = pool.report()
    assert report["active_tasks"] == 0
    assert report["over_reservations"] == [
        {
            "label": "first",
            "reserved_memory_gb": 1.0,
            "peak_process_tree_rss_gb": 3.5,
        }
    ]


def test_stop_request_terminates_external_process_group(tmp_path: Path) -> None:
    reset_stop_request()
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(60)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(60)"
    )
    timer = threading.Timer(0.5, request_stop)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ExecutionInterrupted):
            run_command(
                [sys.executable, "-c", script],
                log_path=tmp_path / "producer.log",
                sample_interval_seconds=0.05,
            )
    finally:
        timer.cancel()
        reset_stop_request()
    assert time.monotonic() - started < 10.0
    assert "[interrupted: ExecutionInterrupted:" in (
        tmp_path / "producer.log"
    ).read_text(encoding="utf-8")
    assert child_pid_path.is_file()
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(50):
        if not psutil.pid_exists(child_pid):
            break
        try:
            if psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.Error:
            break
        time.sleep(0.02)
    else:
        pytest.fail(f"child process {child_pid} survived process-group interruption")
