from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

import psutil
import pytest

from my_helper.fiber.core.vta_pipeline.process_monitor import (
    ProcessTreeMemoryMonitor,
)


@dataclass(frozen=True)
class Tree:
    pid: int
    rss: int
    children: tuple[int, ...] = ()
    running: bool = True
    vanish_on_memory_info: bool = False


def tree(
    pid: int,
    *,
    rss: int,
    children: tuple[int, ...] = (),
    running: bool = True,
    vanish_on_memory_info: bool = False,
) -> Tree:
    return Tree(
        pid=pid,
        rss=rss,
        children=children,
        running=running,
        vanish_on_memory_info=vanish_on_memory_info,
    )


class FakeProcess:
    def __init__(self, provider: "FakeProvider", pid: int) -> None:
        self._provider = provider
        self.pid = pid

    def children(self, *, recursive: bool) -> list["FakeProcess"]:
        assert recursive
        descendants: list[FakeProcess] = []
        pending = list(self._provider.trees[self.pid].children)
        visited: set[int] = set()
        while pending:
            pid = pending.pop(0)
            if pid in visited:
                continue
            visited.add(pid)
            descendants.append(FakeProcess(self._provider, pid))
            pending.extend(self._provider.trees[pid].children)
        return descendants

    def is_running(self) -> bool:
        return self._provider.trees[self.pid].running

    def memory_info(self) -> SimpleNamespace:
        item = self._provider.trees[self.pid]
        if item.vanish_on_memory_info:
            raise psutil.NoSuchProcess(self.pid)
        return SimpleNamespace(rss=item.rss)


class FakeProvider:
    def __init__(self, trees: dict[int, Tree]) -> None:
        self.trees = trees

    def process(self, pid: int) -> FakeProcess:
        if pid not in self.trees:
            raise psutil.NoSuchProcess(pid)
        return FakeProcess(self, pid)


def memory(*, total: int, available: int) -> SimpleNamespace:
    return SimpleNamespace(total=total, available=available)


def swap(*, used: int) -> SimpleNamespace:
    return SimpleNamespace(used=used)


def sequence_provider(values: list[SimpleNamespace]) -> Callable[[], SimpleNamespace]:
    iterator = iter(values)
    return lambda: next(iterator)


def test_sample_sums_unique_live_pids_once() -> None:
    provider = FakeProvider(
        {
            10: tree(10, rss=100, children=(11,)),
            20: tree(20, rss=200, children=(11, 21)),
            11: tree(11, rss=50),
            21: tree(21, rss=25),
        }
    )
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=10),
        start_thread=False,
    )
    monitor.register("SNr003", 10)
    monitor.register("SNr006", 20)

    monitor.sample_once()

    result = monitor.finish()
    assert result.aggregate_peak_rss_bytes == 375
    assert result.subject_peak_rss_bytes == {"SNr003": 150, "SNr006": 275}
    assert result.sample_count == 2


def test_vanished_and_stopped_processes_are_ignored() -> None:
    provider = FakeProvider(
        {
            10: tree(10, rss=100, children=(11, 12, 13)),
            11: tree(11, rss=50),
            12: tree(12, rss=25, vanish_on_memory_info=True),
            13: tree(13, rss=75, running=False),
        }
    )
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=0),
        start_thread=False,
    )
    monitor.register("live", 10)
    monitor.register("missing", 999)

    monitor.sample_once()

    result = monitor.finish()
    assert result.aggregate_peak_rss_bytes == 150
    assert result.subject_peak_rss_bytes == {"live": 150, "missing": 0}


def test_unregister_stops_future_sampling_but_preserves_peak() -> None:
    provider = FakeProvider({10: tree(10, rss=100)})
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=0),
        start_thread=False,
    )
    monitor.register("SNr003", 10)
    monitor.sample_once()

    monitor.unregister("SNr003", 10)
    provider.trees[10] = tree(10, rss=500)
    monitor.sample_once()

    result = monitor.finish()
    assert result.aggregate_peak_rss_bytes == 100
    assert result.subject_peak_rss_bytes == {"SNr003": 100}
    assert result.sample_count == 3


def test_unregister_takes_final_sample_for_short_lived_process() -> None:
    provider = FakeProvider({10: tree(10, rss=125)})
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=0),
        start_thread=False,
    )
    monitor.register("SNr003", 10)

    monitor.unregister("SNr003", 10)

    result = monitor.finish()
    assert result.aggregate_peak_rss_bytes == 125
    assert result.subject_peak_rss_bytes == {"SNr003": 125}
    assert result.sample_count == 1


def test_finish_without_samples_returns_zero_process_peaks() -> None:
    monitor = ProcessTreeMemoryMonitor(
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=10),
        start_thread=False,
    )

    result = monitor.finish()

    assert result.aggregate_peak_rss_bytes == 0
    assert result.subject_peak_rss_bytes == {}
    assert result.physical_memory_bytes == 1000
    assert result.minimum_available_memory_bytes == 400
    assert result.swap_used_start_bytes == 10
    assert result.swap_used_end_bytes == 10
    assert result.swap_used_peak_bytes == 10
    assert result.sample_count == 0


def test_system_memory_tracks_minimum_available_and_swap_peak() -> None:
    virtual_memory_provider = sequence_provider(
        [
            memory(total=1000, available=500),
            memory(total=1000, available=400),
            memory(total=1000, available=300),
        ]
    )
    swap_memory_provider = sequence_provider(
        [swap(used=10), swap(used=25), swap(used=20), swap(used=15)]
    )
    monitor = ProcessTreeMemoryMonitor(
        virtual_memory_provider=virtual_memory_provider,
        swap_memory_provider=swap_memory_provider,
        start_thread=False,
    )

    monitor.sample_once()
    monitor.sample_once()

    result = monitor.finish()
    assert result.physical_memory_bytes == 1000
    assert result.minimum_available_memory_bytes == 300
    assert result.swap_used_start_bytes == 10
    assert result.swap_used_end_bytes == 15
    assert result.swap_used_peak_bytes == 25
    assert result.sample_count == 2


def test_finish_is_idempotent() -> None:
    monitor = ProcessTreeMemoryMonitor(
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=10),
        start_thread=False,
    )

    first = monitor.finish()
    second = monitor.finish()

    assert second is first


def test_finish_takes_final_sample_for_registered_process() -> None:
    provider = FakeProvider({10: tree(10, rss=125)})
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=0),
        start_thread=False,
    )
    monitor.register("SNr003", 10)

    result = monitor.finish()

    assert result.aggregate_peak_rss_bytes == 125
    assert result.subject_peak_rss_bytes == {"SNr003": 125}
    assert result.sample_count == 1


@pytest.mark.parametrize("interval", (0, -0.1, float("inf"), float("nan")))
def test_rejects_invalid_sample_interval(interval: float) -> None:
    with pytest.raises(ValueError, match="sample_interval_seconds"):
        ProcessTreeMemoryMonitor(
            sample_interval_seconds=interval,
            start_thread=False,
        )


def test_rejects_duplicate_subject_registration_and_registration_after_finish() -> None:
    monitor = ProcessTreeMemoryMonitor(start_thread=False)
    monitor.register("SNr003", 10)

    with pytest.raises(ValueError, match="already registered"):
        monitor.register("SNr003", 20)

    monitor.finish()
    with pytest.raises(RuntimeError, match="finish"):
        monitor.register("SNr006", 20)
