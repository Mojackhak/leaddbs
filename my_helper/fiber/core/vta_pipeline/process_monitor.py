"""Synchronized process-tree memory sampling for VTA subject workers."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Callable, Protocol

import psutil


class _MemoryInfo(Protocol):
    rss: int


class _Process(Protocol):
    pid: int

    def children(self, *, recursive: bool) -> list["_Process"]: ...

    def is_running(self) -> bool: ...

    def memory_info(self) -> _MemoryInfo: ...


class _VirtualMemory(Protocol):
    total: int
    available: int


class _SwapMemory(Protocol):
    used: int


@dataclass(frozen=True)
class MemoryObservation:
    """Peak process RSS and host-memory measurements for one monitored run."""

    aggregate_peak_rss_bytes: int
    subject_peak_rss_bytes: dict[str, int]
    physical_memory_bytes: int
    minimum_available_memory_bytes: int
    swap_used_start_bytes: int
    swap_used_end_bytes: int
    swap_used_peak_bytes: int
    sample_count: int


_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.ZombieProcess,
    psutil.AccessDenied,
)


class ProcessTreeMemoryMonitor:
    """Sample every registered process tree on one shared clock."""

    def __init__(
        self,
        sample_interval_seconds: float = 0.1,
        *,
        process_provider: Callable[[int], _Process] = psutil.Process,
        virtual_memory_provider: Callable[[], _VirtualMemory] = psutil.virtual_memory,
        swap_memory_provider: Callable[[], _SwapMemory] = psutil.swap_memory,
        start_thread: bool = True,
    ) -> None:
        if (
            not isinstance(sample_interval_seconds, (int, float))
            or isinstance(sample_interval_seconds, bool)
            or not math.isfinite(sample_interval_seconds)
            or sample_interval_seconds <= 0
        ):
            raise ValueError(
                "sample_interval_seconds must be a finite positive number"
            )
        self._sample_interval_seconds = sample_interval_seconds
        self._process_provider = process_provider
        self._virtual_memory_provider = virtual_memory_provider
        self._swap_memory_provider = swap_memory_provider

        initial_memory = virtual_memory_provider()
        initial_swap = swap_memory_provider()
        self._physical_memory_bytes = int(initial_memory.total)
        self._minimum_available_memory_bytes = int(initial_memory.available)
        self._swap_used_start_bytes = int(initial_swap.used)
        self._swap_used_peak_bytes = int(initial_swap.used)

        self._roots: dict[str, int] = {}
        self._subject_peak_rss_bytes: dict[str, int] = {}
        self._aggregate_peak_rss_bytes = 0
        self._sample_count = 0
        self._finished: MemoryObservation | None = None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        if start_thread:
            self._thread = threading.Thread(
                target=self._sample_loop,
                name="vta-process-memory-monitor",
                daemon=True,
            )
            self._thread.start()

    def register(self, subject_id: str, pid: int) -> None:
        """Register the root PID for a subject process tree."""
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError("subject_id must be a non-empty string")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise ValueError("pid must be a positive integer")
        with self._lock:
            if self._finished is not None:
                raise RuntimeError("cannot register after monitor finish")
            if subject_id in self._roots:
                raise ValueError(
                    f"subject {subject_id!r} is already registered"
                )
            self._roots[subject_id] = pid
            self._subject_peak_rss_bytes.setdefault(subject_id, 0)

    def unregister(self, subject_id: str, pid: int) -> None:
        """Stop sampling a subject root while retaining its observed peak."""
        self.sample_once()
        with self._lock:
            if self._roots.get(subject_id) == pid:
                del self._roots[subject_id]

    def sample_once(self) -> None:
        """Take one synchronized sample across all registered process trees."""
        with self._lock:
            if self._finished is not None:
                return
            roots = dict(self._roots)

        unique_processes: dict[int, _Process] = {}
        subject_pids: dict[str, set[int]] = {
            subject_id: set() for subject_id in roots
        }
        for subject_id, root_pid in roots.items():
            try:
                root = self._process_provider(root_pid)
            except _PROCESS_ERRORS:
                continue

            processes = [root]
            try:
                processes.extend(root.children(recursive=True))
            except _PROCESS_ERRORS:
                pass

            for process in processes:
                subject_pids[subject_id].add(process.pid)
                unique_processes[process.pid] = process

        rss_by_pid: dict[int, int] = {}
        for pid, process in unique_processes.items():
            try:
                if process.is_running():
                    rss_by_pid[pid] = int(process.memory_info().rss)
            except _PROCESS_ERRORS:
                continue

        aggregate_rss = sum(rss_by_pid.values())
        subject_rss = {
            subject_id: sum(rss_by_pid.get(pid, 0) for pid in pids)
            for subject_id, pids in subject_pids.items()
        }
        memory = self._virtual_memory_provider()
        swap = self._swap_memory_provider()

        with self._lock:
            if self._finished is not None:
                return
            self._aggregate_peak_rss_bytes = max(
                self._aggregate_peak_rss_bytes,
                aggregate_rss,
            )
            for subject_id, rss in subject_rss.items():
                self._subject_peak_rss_bytes[subject_id] = max(
                    self._subject_peak_rss_bytes.get(subject_id, 0),
                    rss,
                )
            self._minimum_available_memory_bytes = min(
                self._minimum_available_memory_bytes,
                int(memory.available),
            )
            self._swap_used_peak_bytes = max(
                self._swap_used_peak_bytes,
                int(swap.used),
            )
            self._sample_count += 1

    def finish(self) -> MemoryObservation:
        """Stop sampling and return an idempotent final observation."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()

        with self._lock:
            should_sample = self._finished is None and bool(self._roots)
        if should_sample:
            self.sample_once()

        with self._lock:
            if self._finished is None:
                swap_used_end_bytes = int(self._swap_memory_provider().used)
                self._swap_used_peak_bytes = max(
                    self._swap_used_peak_bytes,
                    swap_used_end_bytes,
                )
                self._finished = MemoryObservation(
                    aggregate_peak_rss_bytes=self._aggregate_peak_rss_bytes,
                    subject_peak_rss_bytes=dict(self._subject_peak_rss_bytes),
                    physical_memory_bytes=self._physical_memory_bytes,
                    minimum_available_memory_bytes=(
                        self._minimum_available_memory_bytes
                    ),
                    swap_used_start_bytes=self._swap_used_start_bytes,
                    swap_used_end_bytes=swap_used_end_bytes,
                    swap_used_peak_bytes=self._swap_used_peak_bytes,
                    sample_count=self._sample_count,
                )
            return self._finished

    def _sample_loop(self) -> None:
        while not self._stop_event.wait(self._sample_interval_seconds):
            self.sample_once()
