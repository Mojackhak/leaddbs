"""Thread-safe prospective CPU and observed-memory resource accounting."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Any, Iterator


@dataclass(frozen=True)
class ResourceSnapshot:
    """One instantaneous resource-pool state."""

    used_cpu: int
    used_memory_gb: float
    cpu_budget: int
    memory_capacity_gb: float


@dataclass
class _Allocation:
    """Mutable accounting record for one admitted task."""

    label: str
    cpu: int
    reserved_memory_gb: float
    observed_memory_gb: float = 0.0
    peak_memory_gb: float = 0.0

    @property
    def charged_memory_gb(self) -> float:
        """Return the greater of reserved and currently observed memory."""

        return max(self.reserved_memory_gb, self.observed_memory_gb)


class ResourceLease:
    """One admitted task lease that accepts process-tree RSS observations."""

    def __init__(self, pool: "ResourcePool", token: int) -> None:
        self._pool = pool
        self._token = token

    def observe_memory_gb(self, memory_gb: float) -> None:
        """Update the task's current and peak observed process-tree memory."""

        self._pool._observe(self._token, memory_gb)

    @property
    def snapshot(self) -> ResourceSnapshot:
        """Return the current global accounting snapshot."""

        return self._pool.snapshot()


class ResourcePool:
    """Admit tasks under CPU and prospective/observed memory constraints."""

    def __init__(self, cpu_budget: int, memory_capacity_gb: float) -> None:
        self.cpu_budget = int(cpu_budget)
        self.memory_capacity_gb = float(memory_capacity_gb)
        if self.cpu_budget <= 0 or self.memory_capacity_gb <= 0:
            raise ValueError("resource budgets must be positive")
        self._allocations: dict[int, _Allocation] = {}
        self._next_token = 0
        self._over_reservations: list[dict[str, Any]] = []
        self._condition = threading.Condition()

    @contextmanager
    def reserve(
        self,
        cpu: int,
        memory_gb: float,
        *,
        label: str,
    ) -> Iterator[ResourceLease]:
        """Reserve resources for one complete external task lifecycle."""

        cpu = int(cpu)
        memory_gb = float(memory_gb)
        if cpu <= 0 or memory_gb <= 0:
            raise ValueError("task CPU and memory reservations must be positive")
        if cpu > self.cpu_budget or memory_gb > self.memory_capacity_gb:
            raise ValueError("one task reservation cannot fit the resource budget")
        with self._condition:
            self._condition.wait_for(
                lambda: (
                    self._used_cpu_locked() + cpu <= self.cpu_budget
                    and self._used_memory_locked() + memory_gb
                    <= self.memory_capacity_gb + 1e-9
                )
            )
            token = self._next_token
            self._next_token += 1
            self._allocations[token] = _Allocation(
                label=str(label),
                cpu=cpu,
                reserved_memory_gb=memory_gb,
            )
            lease = ResourceLease(self, token)
        try:
            yield lease
        finally:
            with self._condition:
                allocation = self._allocations.pop(token)
                if allocation.peak_memory_gb > allocation.reserved_memory_gb:
                    self._over_reservations.append(
                        {
                            "label": allocation.label,
                            "reserved_memory_gb": allocation.reserved_memory_gb,
                            "peak_process_tree_rss_gb": allocation.peak_memory_gb,
                        }
                    )
                self._condition.notify_all()

    def _used_cpu_locked(self) -> int:
        return sum(allocation.cpu for allocation in self._allocations.values())

    def _used_memory_locked(self) -> float:
        return sum(
            allocation.charged_memory_gb
            for allocation in self._allocations.values()
        )

    def _observe(self, token: int, memory_gb: float) -> None:
        observed = max(0.0, float(memory_gb))
        with self._condition:
            allocation = self._allocations.get(token)
            if allocation is None:
                return
            allocation.observed_memory_gb = observed
            allocation.peak_memory_gb = max(allocation.peak_memory_gb, observed)
            self._condition.notify_all()

    def snapshot(self) -> ResourceSnapshot:
        """Return the current admitted reservation totals."""

        with self._condition:
            return ResourceSnapshot(
                used_cpu=self._used_cpu_locked(),
                used_memory_gb=self._used_memory_locked(),
                cpu_budget=self.cpu_budget,
                memory_capacity_gb=self.memory_capacity_gb,
            )

    def report(self) -> dict[str, Any]:
        """Return final resource accounting and over-reservation events."""

        with self._condition:
            return {
                "cpu_budget": self.cpu_budget,
                "memory_dispatch_capacity_gb": self.memory_capacity_gb,
                "active_tasks": len(self._allocations),
                "over_reservations": list(self._over_reservations),
            }
