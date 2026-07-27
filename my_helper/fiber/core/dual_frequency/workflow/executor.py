"""Dependency-aware execution of generic dual-frequency workflow plans."""

from __future__ import annotations

import json
import multiprocessing
import os
import time
import uuid
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..contracts import ArtifactRef, AxisRef
from ..contracts.identity import canonical_hash
from ..instrumentation import (
    PerformanceInstrumentationError,
    aggregate_performance_fragments,
    performance_delta,
    performance_snapshot,
)
from .planner import ExecutionPlan, TaskSpec
from .registry import RegistryError, ServiceRegistry
from .run_store import RunStore


TERMINAL_STATUSES = frozenset({"completed", "skipped", "failed"})


class ExecutionError(RuntimeError):
    """Raised when a workflow cannot be executed under its declared contract."""


class ExpensiveProducerNotAuthorized(ExecutionError):
    """Raised before an unauthorized expensive producer can be invoked."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_record_codec() -> object:
    from ..runtime import record_codec

    return record_codec


@dataclass(frozen=True, order=True)
class RuntimeFact:
    """One named boolean fact emitted by a service."""

    name: str
    value: bool

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ExecutionError("runtime fact name must be nonempty")
        if type(self.value) is not bool:
            raise ExecutionError("runtime fact value must be boolean")


@dataclass(frozen=True)
class ServiceResult:
    """Persistable envelope whose scientific fields are derived by the codec."""

    output_record_type: str
    record_id: str
    payload_json: str
    artifacts: tuple[ArtifactRef, ...] = ()
    facts: tuple[RuntimeFact, ...] = ()

    def __post_init__(self) -> None:
        for field in ("output_record_type", "record_id"):
            if not str(getattr(self, field)).strip():
                raise ExecutionError(f"{field} must be nonempty")
        try:
            payload = json.loads(self.payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ExecutionError("service payload_json must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ExecutionError("service payload must be a JSON object")
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        object.__setattr__(self, "payload_json", canonical_payload)
        artifacts = tuple(self.artifacts)
        if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
            raise ExecutionError("service artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)
        facts = tuple(sorted(self.facts))
        if not all(isinstance(fact, RuntimeFact) for fact in facts):
            raise ExecutionError("service facts must contain only RuntimeFact values")
        if len({fact.name for fact in facts}) != len(facts):
            raise ExecutionError("service fact names must be unique")
        object.__setattr__(self, "facts", facts)

    @classmethod
    def from_record(
        cls,
        record: object,
        *,
        facts: Mapping[str, bool] | tuple[RuntimeFact, ...] = (),
    ) -> "ServiceResult":
        """Encode one allowlisted typed record without caller-supplied metadata."""
        codec = _load_record_codec()
        try:
            payload = codec.encode_record(record)
            record_id = codec.record_identifier(record)
            artifacts = tuple(codec.record_artifacts(record))
        except Exception as exc:
            raise ExecutionError(f"record codec rejected service output: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ExecutionError("record codec encode_record must return a mapping")
        output_record_type = type(record).__name__
        if isinstance(facts, Mapping):
            fact_values = tuple(RuntimeFact(name, value) for name, value in facts.items())
        else:
            fact_values = tuple(facts)
        result = cls(
            output_record_type=output_record_type,
            record_id=record_id,
            payload_json=json.dumps(payload, allow_nan=False),
            artifacts=artifacts,
            facts=fact_values,
        )
        result.decode_record()
        return result

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def fact_values(self) -> dict[str, bool]:
        return {fact.name: fact.value for fact in self.facts}

    def decode_record(self) -> object:
        """Decode and validate the complete persisted record envelope."""
        codec = _load_record_codec()
        try:
            record = codec.decode_record(
                self.output_record_type,
                self.payload,
                record_id=self.record_id,
                artifacts=self.artifacts,
            )
            record_id = codec.record_identifier(record)
            artifacts = tuple(codec.record_artifacts(record))
        except Exception as exc:
            raise ExecutionError(f"record codec rejected persisted service output: {exc}") from exc
        decoded_type = type(record).__name__
        if decoded_type != self.output_record_type:
            raise ExecutionError(
                f"service record type mismatch: envelope declares {self.output_record_type!r}, "
                f"codec decoded {decoded_type!r}"
            )
        if record_id != self.record_id:
            raise ExecutionError(
                f"service record identifier mismatch: envelope declares {self.record_id!r}, "
                f"codec computed {record_id!r}"
            )
        if artifacts != self.artifacts:
            raise ExecutionError("service record artifact closure does not match the codec")
        return record

    def as_dict(self) -> dict[str, Any]:
        codec = _load_record_codec()
        try:
            artifacts = [codec.encode_record(artifact) for artifact in self.artifacts]
        except Exception as exc:
            raise ExecutionError(f"record codec rejected service artifacts: {exc}") from exc
        return {
            "output_record_type": self.output_record_type,
            "record_id": self.record_id,
            "payload": self.payload,
            "artifacts": artifacts,
            "facts": self.fact_values,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ServiceResult":
        codec = _load_record_codec()
        try:
            artifacts: list[ArtifactRef] = []
            for encoded in payload.get("artifacts", ()):
                item = dict(encoded)
                item["axis_refs"] = tuple(
                    AxisRef(**axis) for axis in item.get("axis_refs", ())
                )
                item["axis_hashes"] = tuple(item.get("axis_hashes", ()))
                if item.get("shape") is not None:
                    item["shape"] = tuple(item["shape"])
                candidate = ArtifactRef(**item)
                artifact = codec.decode_record(
                    "ArtifactRef",
                    encoded,
                    record_id=codec.record_identifier(candidate),
                    artifacts=tuple(codec.record_artifacts(candidate)),
                )
                if not isinstance(artifact, ArtifactRef):
                    raise ExecutionError(
                        "persisted service artifact did not decode to ArtifactRef"
                    )
                artifacts.append(artifact)
        except Exception as exc:
            raise ExecutionError(f"record codec rejected persisted artifacts: {exc}") from exc
        fact_values = tuple(
            RuntimeFact(str(key), value) for key, value in payload.get("facts", {}).items()
        )
        result = cls(
            output_record_type=str(payload["output_record_type"]),
            record_id=str(payload["record_id"]),
            payload_json=json.dumps(payload.get("payload", {}), allow_nan=False),
            artifacts=tuple(artifacts),
            facts=fact_values,
        )
        result.decode_record()
        return result


@dataclass(frozen=True)
class TaskOutcome:
    """Terminal execution state for one planned task."""

    task_id: str
    endpoint_id: str
    service_id: str
    status: str
    reason: str
    result: ServiceResult | None
    started_at: str | None = None
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_STATUSES:
            raise ExecutionError(f"unsupported task outcome status {self.status!r}")
        if self.status == "completed" and self.result is None:
            raise ExecutionError("completed task outcomes require a service result")
        if self.status != "completed" and self.result is not None:
            raise ExecutionError("non-completed task outcomes cannot contain a service result")

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "service_id": self.service_id,
            "status": self.status,
            "reason": self.reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result.as_dict() if self.result is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskOutcome":
        result_payload = payload.get("result")
        return cls(
            task_id=str(payload["task_id"]),
            endpoint_id=str(payload["endpoint_id"]),
            service_id=str(payload["service_id"]),
            status=str(payload["status"]),
            reason=str(payload["reason"]),
            result=ServiceResult.from_dict(result_payload) if result_payload is not None else None,
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
        )


@dataclass(frozen=True)
class DependencyState:
    """Direct dependency state with its codec-restored typed record."""

    status: str
    reason: str
    record: object | None


@dataclass(frozen=True)
class TaskExecutionRequest:
    """Runtime request supplied to a registered service."""

    task: TaskSpec
    dependencies: Mapping[str, DependencyState]
    run_id: str
    output_dir: Path
    provider: object
    artifact_store: object | None
    scientific_cache: object | None
    allow_expensive_producers: bool
    workers: int


@dataclass(frozen=True)
class ExecutionContext:
    """Explicit execution dependencies and policy."""

    run_store: RunStore
    registry: ServiceRegistry
    provider: object
    endpoint_facts: Mapping[str, Mapping[str, bool]]
    allow_expensive_producers: bool
    continue_on_endpoint_failure: bool
    workers: int
    artifact_store: object | None = None
    scientific_cache: object | None = None
    resume: bool = False
    spawn_worker_spec: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_store, RunStore):
            raise ExecutionError("run_store must be a RunStore")
        if not isinstance(self.registry, ServiceRegistry):
            raise ExecutionError("registry must be a ServiceRegistry")
        if self.provider is None:
            raise ExecutionError("provider must be supplied explicitly")
        for field in ("allow_expensive_producers", "continue_on_endpoint_failure", "resume"):
            if type(getattr(self, field)) is not bool:
                raise ExecutionError(f"{field} must be boolean")
        if type(self.workers) is not int or self.workers < 1:
            raise ExecutionError("workers must be a positive integer")
        for endpoint_id, facts in self.endpoint_facts.items():
            if not str(endpoint_id).strip() or not isinstance(facts, Mapping):
                raise ExecutionError("endpoint_facts must map endpoint IDs to fact mappings")
            for name, value in facts.items():
                RuntimeFact(str(name), value)


@dataclass(frozen=True)
class _ResourceGrant:
    cpu: int
    memory_bytes: int
    connectome_io: int
    solver: int


class _ResourceLedger:
    """Parent-owned admission ledger beneath the public worker ceiling."""

    def __init__(self, workers: int) -> None:
        self.workers = workers
        self.cpu_used = 0
        self.io_used = 0
        self.solver_used = 0
        self.io_limit = max(1, min(2, workers))
        self.solver_limit = 1
        self.memory_used = 0
        self.peak_cpu_used = 0
        self.peak_memory_used = 0
        self.peak_io_used = 0
        self.peak_solver_used = 0
        self.total_memory, self.available_memory = self._memory_state()
        self.reserve = max(16 * 1024**3, int(0.20 * self.total_memory))
        self.managed = min(
            64 * 1024**3,
            max(0, self.available_memory - self.reserve),
        )
        self.minimum_managed = self.managed
        self.maximum_managed = self.managed

    @staticmethod
    def _memory_state() -> tuple[int, int]:
        try:
            import psutil

            memory = psutil.virtual_memory()
            return int(memory.total), int(memory.available)
        except ImportError:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            total = int(os.sysconf("SC_PHYS_PAGES")) * page_size
            available = int(os.sysconf("SC_AVPHYS_PAGES")) * page_size
            return total, available

    @staticmethod
    def request(
        task: TaskSpec,
        *,
        allow_expensive_producers: bool = True,
    ) -> _ResourceGrant:
        if task.cache_first_expensive and not allow_expensive_producers:
            return _ResourceGrant(1, 512 * 1024**2, 0, 0)
        if task.stage.startswith("jitter_block_"):
            if task.model_family.endswith("fiber"):
                return _ResourceGrant(1, 12 * 1024**3, 1, 0)
            return _ResourceGrant(1, 12 * 1024**3, 0, 0)
        if task.stage == "prepare_exposure":
            memory_bytes = (
                32 * 1024**3
                if task.model_family.endswith("fiber")
                else 16 * 1024**3
            )
            return _ResourceGrant(1, memory_bytes, 1, 0)
        if task.stage == "ppam_observed_workspace":
            return _ResourceGrant(1, 48 * 1024**3, 1, 1)
        if task.stage.startswith(
            ("oss_axis_equivalence_", "oss_omega_max_")
        ):
            return _ResourceGrant(1, 48 * 1024**3, 1, 1)
        if task.stage == "activation_sensitivity":
            if task.service_id == "aggregate_ppam_activation":
                return _ResourceGrant(1, 2 * 1024**3, 0, 0)
            return _ResourceGrant(1, 48 * 1024**3, 1, 1)
        if task.stage.startswith("formal_permutation_block_") or task.stage in {
            "formal_permutation_schedule",
            "formal_operator_workspace",
            "formal_permutation",
            "formal_bootstrap",
            "formal_in_sample",
            "spatial_jitter",
        }:
            return _ResourceGrant(1, 2 * 1024**3, 0, 0)
        if (
            task.stage.startswith("ppam_permutation_block_")
            or task.stage == "ppam_permutation_schedule"
        ):
            return _ResourceGrant(1, 2 * 1024**3, 0, 0)
        return _ResourceGrant(1, 512 * 1024**2, 0, 0)

    def can_acquire(self, grant: _ResourceGrant, running_count: int) -> bool:
        return not self.blocking_reasons(grant)

    def blocking_reasons(self, grant: _ResourceGrant) -> tuple[str, ...]:
        """Return every parent-ledger predicate preventing admission."""

        reasons: list[str] = []
        if self.cpu_used + grant.cpu > self.workers:
            reasons.append("cpu")
        if self.io_used + grant.connectome_io > self.io_limit:
            reasons.append("connectome_io")
        if self.solver_used + grant.solver > self.solver_limit:
            reasons.append("external_solver")
        projected = self.available_memory - self.memory_used - grant.memory_bytes
        cumulative_memory = self.memory_used + grant.memory_bytes
        if not cumulative_memory < self.managed:
            reasons.append("managed_memory")
        if not projected > self.reserve:
            reasons.append("memory_reserve")
        return tuple(reasons)

    def structural_blocking_reasons(
        self,
        grant: _ResourceGrant,
    ) -> tuple[str, ...]:
        """Return resource predicates that cannot recover without reconfiguration."""

        reasons: list[str] = []
        if grant.cpu > self.workers:
            reasons.append("cpu")
        if grant.connectome_io > self.io_limit:
            reasons.append("connectome_io")
        if grant.solver > self.solver_limit:
            reasons.append("external_solver")
        maximum_managed = min(
            64 * 1024**3,
            max(0, self.total_memory - self.reserve),
        )
        if not grant.memory_bytes < maximum_managed:
            reasons.append("managed_memory")
        return tuple(reasons)

    def acquire(self, grant: _ResourceGrant) -> None:
        self.cpu_used += grant.cpu
        self.memory_used += grant.memory_bytes
        self.io_used += grant.connectome_io
        self.solver_used += grant.solver
        self.peak_cpu_used = max(self.peak_cpu_used, self.cpu_used)
        self.peak_memory_used = max(self.peak_memory_used, self.memory_used)
        self.peak_io_used = max(self.peak_io_used, self.io_used)
        self.peak_solver_used = max(self.peak_solver_used, self.solver_used)

    def release(self, grant: _ResourceGrant) -> None:
        self.cpu_used -= grant.cpu
        self.memory_used -= grant.memory_bytes
        self.io_used -= grant.connectome_io
        self.solver_used -= grant.solver

    def reconcile_available(self, live_available_memory: int) -> None:
        """Refresh admission capacity without double-charging active grants."""

        live_available = max(0, int(live_available_memory))
        self.available_memory = live_available + self.memory_used
        self.managed = min(
            64 * 1024**3,
            max(0, self.available_memory - self.reserve),
        )
        self.minimum_managed = min(self.minimum_managed, self.managed)
        self.maximum_managed = max(self.maximum_managed, self.managed)

    def settings(self) -> dict[str, int]:
        """Return the effective non-scientific admission settings."""

        return {
            "workers": self.workers,
            "managed_memory_bytes": self.managed,
            "required_memory_reserve_bytes": self.reserve,
            "connectome_io_slots": self.io_limit,
            "external_solver_slots": self.solver_limit,
            "blas_threads_per_worker": 1,
        }

    def peak_reservations(self) -> dict[str, int]:
        """Return peak parent-ledger reservations for segment provenance."""

        return {
            "minimum_managed_memory_bytes": self.minimum_managed,
            "maximum_managed_memory_bytes": self.maximum_managed,
            "final_managed_memory_bytes": self.managed,
            "peak_reserved_cpu_slots": self.peak_cpu_used,
            "peak_reserved_memory_bytes": self.peak_memory_used,
            "peak_reserved_connectome_io_slots": self.peak_io_used,
            "peak_reserved_external_solver_slots": self.peak_solver_used,
        }


def _swap_used_bytes() -> int:
    try:
        import psutil

        return int(psutil.swap_memory().used)
    except ImportError:
        return 0


class _LiveResourceMonitor:
    """Sample production process-tree resources without changing task identity."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.baseline_swap_bytes = _swap_used_bytes()
        self.sample_count = 0
        self.peak_task_tree_rss_bytes = 0
        self.minimum_available_memory_bytes: int | None = None
        self.peak_swap_delta_bytes = 0
        self._next_sample_at = 0.0

    @staticmethod
    def _process_tree_rss_bytes() -> int:
        try:
            import psutil

            root = psutil.Process(os.getpid())
            processes = (root, *root.children(recursive=True))
            rss_by_pid: dict[int, int] = {}
            for process in processes:
                try:
                    rss_by_pid[process.pid] = int(process.memory_info().rss)
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            return sum(rss_by_pid.values())
        except ImportError:
            return 0

    @staticmethod
    def _available_memory_bytes(fallback: int) -> int:
        try:
            import psutil

            return int(psutil.virtual_memory().available)
        except ImportError:
            return max(0, int(fallback))

    def sample_if_due(
        self,
        ledger: _ResourceLedger,
        *,
        force: bool = False,
    ) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now < self._next_sample_at:
            return
        fallback = ledger.available_memory - ledger.memory_used
        available = self._available_memory_bytes(fallback)
        rss = self._process_tree_rss_bytes()
        swap = _swap_used_bytes()
        ledger.reconcile_available(available)
        self.sample_count += 1
        self.peak_task_tree_rss_bytes = max(
            self.peak_task_tree_rss_bytes,
            rss,
        )
        self.minimum_available_memory_bytes = (
            available
            if self.minimum_available_memory_bytes is None
            else min(self.minimum_available_memory_bytes, available)
        )
        self.peak_swap_delta_bytes = max(
            self.peak_swap_delta_bytes,
            max(0, swap - self.baseline_swap_bytes),
        )
        self._next_sample_at = now + 1.0

    def as_dict(self) -> dict[str, int]:
        return {
            "resource_sample_count": self.sample_count,
            "peak_task_tree_rss_bytes": self.peak_task_tree_rss_bytes,
            "minimum_available_memory_bytes": (
                0
                if self.minimum_available_memory_bytes is None
                else self.minimum_available_memory_bytes
            ),
            "peak_swap_delta_bytes": self.peak_swap_delta_bytes,
        }


@dataclass(frozen=True)
class RunResult:
    """Aggregate terminal state for one execution plan."""

    run_id: str
    outcomes: tuple[TaskOutcome, ...]
    exit_code: int

    @property
    def failed_task_ids(self) -> tuple[str, ...]:
        return tuple(outcome.task_id for outcome in self.outcomes if outcome.status == "failed")

    @property
    def failed_endpoint_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({outcome.endpoint_id for outcome in self.outcomes if outcome.status == "failed"})
        )


def plan_hash(plan: ExecutionPlan) -> str:
    """Return the exact plan hash retained as execution provenance."""
    return canonical_hash({"plan": asdict(plan)})


def _write_outcome(store: RunStore, outcome: TaskOutcome) -> None:
    store.write_task_state(outcome.task_id, outcome.as_dict())


def _restore_outcomes(
    plan: ExecutionPlan,
    context: ExecutionContext,
) -> tuple[dict[str, TaskOutcome], frozenset[str]]:
    if not context.resume:
        return {}, frozenset()
    output: dict[str, TaskOutcome] = {}
    invalid_completed: set[str] = set()
    cache_only_replays: set[str] = set()
    for task in plan.tasks:
        if any(dependency in invalid_completed for dependency in task.dependencies):
            invalid_completed.add(task.task_id)
            continue
        try:
            payload = context.run_store.read_task_state(task.task_id)
        except (OSError, TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping):
            continue
        result_payload = payload.get("result")
        if payload.get("status") != "completed":
            continue
        if not isinstance(result_payload, Mapping):
            invalid_completed.add(task.task_id)
            continue
        try:
            result = ServiceResult.from_dict(result_payload)
            record = result.decode_record()
            if type(record).__name__ == "FormalOperatorScratchRecord":
                from ..runtime.formal_operator_workspace import (
                    validate_formal_operator_scratch_record,
                )

                validate_formal_operator_scratch_record(
                    record,
                    context.run_store.root,
                )
            if type(record).__name__ == "PPAMObservedWorkspaceRecord":
                from ..runtime.ppam_observed_workspace import (
                    validate_ppam_observed_workspace_record,
                )

                selections = tuple(
                    dependency.result.decode_record()
                    for dependency_id in task.dependencies
                    for dependency in (output.get(dependency_id),)
                    if dependency is not None
                    and dependency.result is not None
                    and dependency.result.output_record_type
                    == "FinalSelectionRecord"
                )
                if (
                    len(selections) != 1
                    or getattr(selections[0], "final_model", None) is None
                ):
                    raise ExecutionError(
                        "restored pPAM workspace lacks its final selection"
                    )
                validate_ppam_observed_workspace_record(
                    record,
                    selections[0].final_model,
                    context.run_store.root,
                )
            if (
                type(record).__name__ == "OSSAxisEquivalenceGroupRecord"
                and getattr(record, "gate_status", None)
                == "accepted_omega_max"
                and context.scientific_cache is not None
            ):
                from ..runtime.oss_axis_equivalence import (
                    accepted_group_uses_stable_scientific_cache,
                )

                cache_only_replays.add(task.task_id)
                if not accepted_group_uses_stable_scientific_cache(
                    record,
                    context.scientific_cache,
                ):
                    invalid_completed.add(task.task_id)
                    continue
                cache_only_replays.discard(task.task_id)
            if (
                type(record).__name__ == "OSSSharedOmegaGroupRecord"
                and getattr(record, "preparation_status", None)
                == "omega_max_ready"
                and context.scientific_cache is not None
            ):
                from ..runtime.oss_shared_omega import (
                    shared_omega_group_uses_stable_scientific_cache,
                )

                cache_only_replays.add(task.task_id)
                if not shared_omega_group_uses_stable_scientific_cache(
                    record,
                    context.scientific_cache,
                ):
                    invalid_completed.add(task.task_id)
                    continue
                cache_only_replays.discard(task.task_id)
        except (OSError, RuntimeError, TypeError, ValueError):
            invalid_completed.add(task.task_id)
            continue
        output[task.task_id] = TaskOutcome(
            task_id=task.task_id,
            endpoint_id=task.endpoint_id,
            service_id=task.service_id,
            status="completed",
            reason="restored_completed_result",
            result=result,
            started_at=(
                str(payload["started_at"])
                if payload.get("started_at") is not None
                else None
            ),
            finished_at=(
                str(payload["finished_at"])
                if payload.get("finished_at") is not None
                else None
            ),
        )
    return output, frozenset(cache_only_replays)


def _dependency_layers(
    task: TaskSpec,
    tasks: Mapping[str, TaskSpec],
) -> tuple[tuple[str, ...], ...]:
    """Return unique dependency IDs grouped by distance from the task."""

    seen: set[str] = set()
    frontier = tuple(task.dependencies)
    layers: list[tuple[str, ...]] = []
    while frontier:
        layer = tuple(dict.fromkeys(task_id for task_id in frontier if task_id not in seen))
        if not layer:
            break
        layers.append(layer)
        seen.update(layer)
        frontier = tuple(
            dependency
            for task_id in layer
            for dependency in tasks[task_id].dependencies
        )
    return tuple(layers)


def _resolve_fact(
    task: TaskSpec,
    fact_name: str,
    tasks: Mapping[str, TaskSpec],
    outcomes: Mapping[str, TaskOutcome],
    endpoint_facts: Mapping[str, Mapping[str, bool]],
) -> bool:
    static = endpoint_facts.get(task.endpoint_id, {})
    if fact_name in static:
        return static[fact_name]
    for layer in _dependency_layers(task, tasks):
        values = {
            outcome.result.fact_values[fact_name]
            for task_id in layer
            for outcome in (outcomes.get(task_id),)
            if outcome is not None
            and outcome.result is not None
            and fact_name in outcome.result.fact_values
        }
        if not values:
            continue
        if len(values) != 1:
            raise ExecutionError(
                f"runtime fact {fact_name!r} is contradictory for {task.task_id}"
            )
        return next(iter(values))
    raise ExecutionError(f"runtime fact {fact_name!r} is unavailable for {task.task_id}")


def _dependency_states(
    task: TaskSpec,
    outcomes: Mapping[str, TaskOutcome],
) -> dict[str, DependencyState]:
    return {
        dependency_id: DependencyState(
            status=outcomes[dependency_id].status,
            reason=outcomes[dependency_id].reason,
            record=(
                outcomes[dependency_id].result.decode_record()
                if outcomes[dependency_id].result is not None
                else None
            ),
        )
        for dependency_id in task.dependencies
    }


def _record_endpoint_id(record: object) -> str | None:
    endpoint = getattr(record, "endpoint", None)
    if type(record).__name__ == "ReferenceDependencyRecord":
        endpoint = getattr(record, "addon_endpoint", None)
    if endpoint is None and type(record).__name__ == "ObservedResult":
        source = getattr(record, "source", None)
        endpoint = getattr(source, "endpoint", None)
    if endpoint is None:
        return None
    endpoint_id = getattr(endpoint, "identifier", None)
    if not isinstance(endpoint_id, str) or not endpoint_id.strip():
        raise ExecutionError("service record endpoint has no valid identifier")
    return endpoint_id


def _validate_service_result(task: TaskSpec, result: object) -> ServiceResult:
    if not isinstance(result, ServiceResult):
        raise ExecutionError(f"service {task.service_id!r} did not return ServiceResult")
    record = result.decode_record()
    if result.output_record_type != task.output_record_type:
        raise ExecutionError(
            f"service {task.service_id!r} returned {result.output_record_type!r}; "
            f"expected {task.output_record_type!r}"
        )
    record_endpoint_id = _record_endpoint_id(record)
    if record_endpoint_id is not None and record_endpoint_id != task.endpoint_id:
        raise ExecutionError(
            f"service {task.service_id!r} returned endpoint {record_endpoint_id!r}; "
            f"expected {task.endpoint_id!r}"
        )
    return result


def _begin_task(task: TaskSpec, context: ExecutionContext) -> tuple[str, Path]:
    started = _utc_now()
    output_dir = _new_task_attempt_dir(context.run_store.root, task)
    context.run_store.write_task_state(
        task.task_id,
        {
            "endpoint_id": task.endpoint_id,
            "service_id": task.service_id,
            "status": "running",
            "reason": "none",
            "started_at": started,
            "finished_at": None,
            "result": None,
        },
    )
    return started, output_dir


def _new_task_attempt_dir(run_root: Path, task: TaskSpec) -> Path:
    """Create an immutable output directory for one task invocation."""

    task_root = Path(run_root) / "work" / task.task_id
    task_root.mkdir(parents=True, exist_ok=True)
    output_dir = task_root / f"attempt-{uuid.uuid4().hex}"
    output_dir.mkdir(exist_ok=False)
    return output_dir


def _invoke_local_service(
    task: TaskSpec,
    context: ExecutionContext,
    dependencies: Mapping[str, DependencyState],
    output_dir: Path,
    *,
    allow_expensive_producers: bool | None = None,
) -> ServiceResult:
    service = context.registry.resolve(task.service_id)
    allowed = (
        context.allow_expensive_producers
        if allow_expensive_producers is None
        else allow_expensive_producers
    )
    request = TaskExecutionRequest(
        task=task,
        dependencies=dependencies,
        run_id=context.run_store.run_id,
        output_dir=output_dir,
        provider=context.provider,
        artifact_store=context.artifact_store,
        scientific_cache=context.scientific_cache,
        allow_expensive_producers=allowed,
        workers=1,
    )
    return _validate_service_result(task, service(request))


def _finish_future(
    task: TaskSpec,
    started: str,
    future: object,
    context: ExecutionContext,
) -> TaskOutcome:
    try:
        result = _validate_service_result(task, future.result())
        context.run_store.record_artifacts(result.artifacts)
        outcome = TaskOutcome(
            task_id=task.task_id,
            endpoint_id=task.endpoint_id,
            service_id=task.service_id,
            status="completed",
            reason="none",
            result=result,
            started_at=started,
            finished_at=_utc_now(),
        )
    except Exception as exc:
        outcome = TaskOutcome(
            task_id=task.task_id,
            endpoint_id=task.endpoint_id,
            service_id=task.service_id,
            status="failed",
            reason=f"{type(exc).__name__}: {exc}",
            result=None,
            started_at=started,
            finished_at=_utc_now(),
        )
    _write_outcome(context.run_store, outcome)
    return outcome


def _run_task(task: TaskSpec, context: ExecutionContext, outcomes: Mapping[str, TaskOutcome]) -> TaskOutcome:
    started = _utc_now()
    output_dir = _new_task_attempt_dir(context.run_store.root, task)
    context.run_store.write_task_state(
        task.task_id,
        {
            "endpoint_id": task.endpoint_id,
            "service_id": task.service_id,
            "status": "running",
            "reason": "none",
            "started_at": started,
            "finished_at": None,
            "result": None,
        },
    )
    try:
        service = context.registry.resolve(task.service_id)
        request = TaskExecutionRequest(
            task=task,
            dependencies=_dependency_states(task, outcomes),
            run_id=context.run_store.run_id,
            output_dir=output_dir,
            provider=context.provider,
            artifact_store=context.artifact_store,
            scientific_cache=context.scientific_cache,
            allow_expensive_producers=context.allow_expensive_producers,
            workers=context.workers,
        )
        result = _validate_service_result(task, service(request))
        context.run_store.record_artifacts(result.artifacts)
        outcome = TaskOutcome(
            task_id=task.task_id,
            endpoint_id=task.endpoint_id,
            service_id=task.service_id,
            status="completed",
            reason="none",
            result=result,
            started_at=started,
            finished_at=_utc_now(),
        )
    except Exception as exc:
        outcome = TaskOutcome(
            task_id=task.task_id,
            endpoint_id=task.endpoint_id,
            service_id=task.service_id,
            status="failed",
            reason=f"{type(exc).__name__}: {exc}",
            result=None,
            started_at=started,
            finished_at=_utc_now(),
        )
    _write_outcome(context.run_store, outcome)
    return outcome


def _skipped(task: TaskSpec, reason: str, store: RunStore) -> TaskOutcome:
    now = _utc_now()
    outcome = TaskOutcome(
        task_id=task.task_id,
        endpoint_id=task.endpoint_id,
        service_id=task.service_id,
        status="skipped",
        reason=reason,
        result=None,
        started_at=now,
        finished_at=now,
    )
    _write_outcome(store, outcome)
    return outcome


def _failed(task: TaskSpec, reason: str, store: RunStore) -> TaskOutcome:
    now = _utc_now()
    outcome = TaskOutcome(
        task_id=task.task_id,
        endpoint_id=task.endpoint_id,
        service_id=task.service_id,
        status="failed",
        reason=reason,
        result=None,
        started_at=now,
        finished_at=now,
    )
    _write_outcome(store, outcome)
    return outcome


_ADMISSION_REASONS = (
    "worker_slots",
    "cpu",
    "managed_memory",
    "memory_reserve",
    "connectome_io",
    "external_solver",
)


class _ExecutionMetrics:
    """Accumulate non-scientific scheduler provenance for one segment."""

    def __init__(self, restored_task_count: int) -> None:
        self.restored_task_count = int(restored_task_count)
        self.scheduled_task_count = 0
        self.max_ready_queue_depth = 0
        self.peak_running_task_count = 0
        self._active: dict[str, dict[str, float]] = {}
        self._first_blocked: dict[str, float] = {}
        self._blocked_tasks: dict[str, set[str]] = {
            reason: set() for reason in _ADMISSION_REASONS
        }
        self._wait_seconds: dict[str, float] = {
            reason: 0.0 for reason in _ADMISSION_REASONS
        }
        self.max_task_admission_wait_seconds = 0.0
        self._scheduler_windows: list[dict[str, object]] = []
        self._window_started_monotonic: float | None = None
        self._window_started_utc: str | None = None
        self._next_window_at = 0.0

    def observe_ready_queue(self, depth: int) -> None:
        self.max_ready_queue_depth = max(self.max_ready_queue_depth, int(depth))

    def observe_running(self, count: int) -> None:
        self.peak_running_task_count = max(
            self.peak_running_task_count,
            int(count),
        )

    def observe_blocked(
        self,
        task_id: str,
        reasons: tuple[str, ...],
        now: float,
    ) -> None:
        unknown = set(reasons) - set(_ADMISSION_REASONS)
        if unknown:
            raise ExecutionError(
                "scheduler reported unsupported admission reasons: "
                + ",".join(sorted(unknown))
            )
        active = self._active.setdefault(task_id, {})
        for reason in tuple(active):
            if reason not in reasons:
                self._wait_seconds[reason] += max(0.0, now - active.pop(reason))
        for reason in reasons:
            if reason not in active:
                active[reason] = now
            self._blocked_tasks[reason].add(task_id)
        self._first_blocked.setdefault(task_id, now)

    def close_task(self, task_id: str, now: float) -> None:
        active = self._active.pop(task_id, {})
        for reason, started in active.items():
            self._wait_seconds[reason] += max(0.0, now - started)
        first = self._first_blocked.pop(task_id, None)
        if first is not None:
            self.max_task_admission_wait_seconds = max(
                self.max_task_admission_wait_seconds,
                max(0.0, now - first),
            )

    def scheduled(self, task_id: str, running_count: int, now: float) -> None:
        self.close_task(task_id, now)
        self.scheduled_task_count += 1
        self.observe_running(running_count)

    def sample_scheduler_window(
        self,
        *,
        ready_task_count: int,
        running_task_count: int,
        ledger: _ResourceLedger,
        now_monotonic: float,
        now_utc: str,
        force: bool = False,
    ) -> None:
        """Retain one five-second scheduler window without filesystem I/O."""

        if self._window_started_monotonic is None:
            self._window_started_monotonic = now_monotonic
            self._window_started_utc = now_utc
            self._next_window_at = now_monotonic + 5.0
            if not force:
                return
        if not force and now_monotonic < self._next_window_at:
            return
        started = self._window_started_monotonic
        started_utc = self._window_started_utc
        if started is None or started_utc is None:
            raise ExecutionError("scheduler window lacks a start boundary")
        elapsed = max(0.0, now_monotonic - started)
        if elapsed > 0:
            active_reasons = {
                reason: sum(
                    1
                    for reasons in self._active.values()
                    if reason in reasons
                )
                for reason in _ADMISSION_REASONS
            }
            self._scheduler_windows.append(
                {
                    "start_utc": started_utc,
                    "finish_utc": now_utc,
                    "elapsed_seconds": elapsed,
                    "ready_task_count": int(ready_task_count),
                    "running_task_count": int(running_task_count),
                    "runnable_cpu_slots": min(
                        ledger.workers,
                        int(ready_task_count) + int(running_task_count),
                    ),
                    "reserved_cpu_slots": ledger.cpu_used,
                    "managed_memory_bytes": ledger.managed,
                    "reserved_memory_bytes": ledger.memory_used,
                    "reserved_connectome_io_slots": ledger.io_used,
                    "reserved_external_solver_slots": ledger.solver_used,
                    "admission_blocked_task_count_by_reason": active_reasons,
                    "storage_limited": active_reasons["connectome_io"] > 0,
                }
            )
        self._window_started_monotonic = now_monotonic
        self._window_started_utc = now_utc
        self._next_window_at = now_monotonic + 5.0

    @property
    def scheduler_windows(self) -> tuple[dict[str, object], ...]:
        """Return immutable terminal scheduler-window evidence."""

        return tuple(dict(row) for row in self._scheduler_windows)

    def as_dict(
        self,
        *,
        terminal_task_count: int,
        ledger: _ResourceLedger,
        now: float,
    ) -> dict[str, object]:
        for task_id in tuple(self._active):
            self.close_task(task_id, now)
        return {
            "restored_task_count": self.restored_task_count,
            "scheduled_task_count": self.scheduled_task_count,
            "terminal_task_count": int(terminal_task_count),
            "peak_running_task_count": self.peak_running_task_count,
            "max_ready_queue_depth": self.max_ready_queue_depth,
            "admission_blocked_task_count_by_reason": {
                reason: len(self._blocked_tasks[reason])
                for reason in _ADMISSION_REASONS
            },
            "admission_wait_seconds_by_reason": {
                reason: self._wait_seconds[reason]
                for reason in _ADMISSION_REASONS
            },
            "max_task_admission_wait_seconds": (
                self.max_task_admission_wait_seconds
            ),
            **ledger.peak_reservations(),
        }


@dataclass(frozen=True)
class _RunningInvocation:
    """Parent-owned state for one submitted immutable task attempt."""

    task: TaskSpec
    started_at: str
    started_monotonic: float
    grant: _ResourceGrant
    output_dir: Path


def _terminate_process_pool(pool: object) -> None:
    """Terminate one spawn generation and every worker-owned process group."""

    processes = tuple(getattr(pool, "_processes", {}).values())
    for process in processes:
        pid = getattr(process, "pid", None)
        terminated_group = False
        if isinstance(pid, int) and pid > 0 and hasattr(os, "killpg"):
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, 15)
                    terminated_group = True
            except (OSError, ProcessLookupError):
                pass
        if not terminated_group:
            try:
                process.terminate()
            except (AttributeError, OSError, ProcessLookupError):
                continue
    deadline = time.monotonic() + 5.0
    for process in processes:
        try:
            process.join(timeout=max(0.0, deadline - time.monotonic()))
        except (AttributeError, OSError):
            continue
    for process in processes:
        try:
            alive = process.is_alive()
        except (AttributeError, OSError):
            alive = False
        if not alive:
            continue
        pid = getattr(process, "pid", None)
        killed_group = False
        if isinstance(pid, int) and pid > 0 and hasattr(os, "killpg"):
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, 9)
                    killed_group = True
            except (OSError, ProcessLookupError):
                pass
        if not killed_group:
            try:
                process.kill()
            except (AttributeError, OSError, ProcessLookupError):
                continue
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except (AttributeError, BrokenProcessPool):
        pass


def _quarantine_attempt(output_dir: Path, reason: str) -> bool:
    """Move one terminated attempt aside before any retry starts."""

    source = Path(output_dir)
    if not source.exists():
        return False
    token = "".join(character if character.isalnum() else "-" for character in reason)
    destination = source.with_name(
        f"{source.name}.quarantined-{token[:48]}-{uuid.uuid4().hex}"
    )
    os.replace(source, destination)
    return True


def _write_retrying(
    store: RunStore,
    invocation: _RunningInvocation,
    reason: str,
) -> None:
    """Persist a nonterminal attempt boundary that resume will rerun."""

    store.write_task_state(
        invocation.task.task_id,
        {
            "endpoint_id": invocation.task.endpoint_id,
            "service_id": invocation.task.service_id,
            "status": "retrying",
            "reason": reason,
            "started_at": invocation.started_at,
            "finished_at": _utc_now(),
            "result": None,
        },
    )


def execute_plan(plan: ExecutionPlan, context: ExecutionContext) -> RunResult:
    """Execute a plan with local failure isolation and exact resume semantics."""
    if not isinstance(plan, ExecutionPlan):
        raise ExecutionError("plan must be an ExecutionPlan")
    try:
        context.registry.require(task.service_id for task in plan.tasks)
    except RegistryError as exc:
        raise ExecutionError(str(exc)) from exc

    task_index = {task.task_id: task for task in plan.tasks}
    outcomes, cache_only_replays = _restore_outcomes(plan, context)
    missing_checkpoint_roots = tuple(
        task.task_id
        for task in plan.tasks
        if task.checkpoint_only and task.task_id not in outcomes
    )
    if missing_checkpoint_roots:
        raise ExecutionError(
            "extension checkpoint roots are missing completed outcomes: "
            + ",".join(missing_checkpoint_roots)
        )
    pending = {task.task_id: task for task in plan.tasks if task.task_id not in outcomes}
    abort = False
    ledger = _ResourceLedger(context.workers)
    metrics = _ExecutionMetrics(len(outcomes))
    process_mode = context.spawn_worker_spec is not None
    resource_monitor = _LiveResourceMonitor(process_mode)
    resource_monitor.sample_if_due(ledger, force=True)
    initial_swap = _swap_used_bytes()
    parent_performance_before = performance_snapshot()
    segment_id = context.run_store.begin_execution_segment(
        {
            "started_at": _utc_now(),
            "code_identity": context.run_store.identity.code_identity,
            "plan_hash": context.run_store.identity.plan_hash,
            "pool_mode": "spawn_process" if process_mode else "in_process_test",
            "pool_generation_count": 1,
            **ledger.settings(),
        }
    )
    if process_mode:
        from .process_worker import (
            WorkerCommand,
            execute_worker_command,
            initialize_worker,
        )

        def create_pool():
            return ProcessPoolExecutor(
                max_workers=context.workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=initialize_worker,
                initargs=(context.spawn_worker_spec,),
            )

    else:
        def create_pool():
            return ThreadPoolExecutor(max_workers=context.workers)

    pool = create_pool()
    pool_generation_count = 1
    task_timeout_count = 0
    broken_pool_count = 0
    transient_retry_count = 0
    quarantined_attempt_count = 0
    attempts: dict[str, int] = {}
    scheduled_attempts: list[dict[str, str]] = []
    running: dict[object, _RunningInvocation] = {}

    def recover_generation(reason: str) -> None:
        nonlocal pool
        nonlocal pool_generation_count
        nonlocal transient_retry_count
        nonlocal quarantined_attempt_count
        nonlocal abort

        if not process_mode:
            raise ExecutionError("pool generation recovery requires spawn execution")
        if pool is None:
            raise ExecutionError("pool generation recovery lacks an active pool")
        _terminate_process_pool(pool)
        pool = None
        invocations = tuple(running.values())
        running.clear()
        for invocation in invocations:
            ledger.release(invocation.grant)
            if _quarantine_attempt(invocation.output_dir, reason):
                quarantined_attempt_count += 1
            task = invocation.task
            consumed_retries = max(0, attempts.get(task.task_id, 1) - 1)
            if (
                task.transient_safe
                and consumed_retries < task.max_transient_retries
            ):
                pending[task.task_id] = task
                transient_retry_count += 1
                _write_retrying(
                    context.run_store,
                    invocation,
                    f"{reason}:retry_{consumed_retries + 1}",
                )
                continue
            outcomes[task.task_id] = _failed(
                task,
                f"PoolGenerationFailure: {reason}",
                context.run_store,
            )
            if not context.continue_on_endpoint_failure:
                abort = True
        if pending and not abort:
            pool = create_pool()
            pool_generation_count += 1

    try:
        while pending or running:
            resource_monitor.sample_if_due(ledger)
            now_monotonic = time.monotonic()
            expired = tuple(
                invocation
                for invocation in running.values()
                if invocation.task.timeout_seconds is not None
                and now_monotonic - invocation.started_monotonic
                > invocation.task.timeout_seconds
            )
            if expired:
                task_timeout_count += len(expired)
                recover_generation(
                    "task_timeout:" + ",".join(
                        sorted(item.task.task_id for item in expired)
                    )
                )
                continue
            progressed = False
            resource_blocked_ready = False
            ready = [
                task
                for task in plan.tasks
                if task.task_id in pending
                and all(dependency in outcomes for dependency in task.dependencies)
            ]
            metrics.observe_ready_queue(len(ready))
            metrics.sample_scheduler_window(
                ready_task_count=len(ready),
                running_task_count=len(running),
                ledger=ledger,
                now_monotonic=now_monotonic,
                now_utc=_utc_now(),
            )
            for task in ready:
                admission_time = time.monotonic()
                task_allows_expensive = (
                    context.allow_expensive_producers
                    and task.task_id not in cache_only_replays
                )
                if abort:
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    outcomes[task.task_id] = _skipped(
                        task,
                        "not_run_batch_aborted",
                        context.run_store,
                    )
                    progressed = True
                    continue
                dependency_outcomes = tuple(outcomes[item] for item in task.dependencies)
                blocking = tuple(
                    outcome
                    for outcome in dependency_outcomes
                    if outcome.status == "failed"
                    or (
                        outcome.status == "skipped"
                        and outcome.reason.startswith("dependency_failure")
                    )
                )
                if blocking:
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    outcomes[task.task_id] = _skipped(
                        task,
                        "dependency_failure:" + ",".join(
                            item.task_id for item in blocking
                        ),
                        context.run_store,
                    )
                    progressed = True
                    continue
                try:
                    failed_gate = next(
                        (
                            gate
                            for gate in task.gates
                            if not _resolve_fact(
                                task,
                                gate.fact,
                                task_index,
                                outcomes,
                                context.endpoint_facts,
                            )
                        ),
                        None,
                    )
                except ExecutionError as exc:
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    outcomes[task.task_id] = _failed(
                        task,
                        str(exc),
                        context.run_store,
                    )
                    if not context.continue_on_endpoint_failure:
                        abort = True
                    progressed = True
                    continue
                if failed_gate is not None:
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    outcomes[task.task_id] = _skipped(
                        task,
                        failed_gate.false_status,
                        context.run_store,
                    )
                    progressed = True
                    continue
                if (
                    task.expensive_producer
                    and not task.cache_first_expensive
                    and not task_allows_expensive
                ):
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    error = ExpensiveProducerNotAuthorized(
                        f"expensive producer {task.service_id!r} is not authorized"
                    )
                    outcomes[task.task_id] = _failed(
                        task,
                        f"{type(error).__name__}: {error}",
                        context.run_store,
                    )
                    if not context.continue_on_endpoint_failure:
                        abort = True
                    progressed = True
                    continue
                if task.timeout_seconds is not None and not process_mode:
                    pending.pop(task.task_id)
                    metrics.close_task(task.task_id, admission_time)
                    outcomes[task.task_id] = _failed(
                        task,
                        "ExecutionError: task timeout requires spawn execution",
                        context.run_store,
                    )
                    if not context.continue_on_endpoint_failure:
                        abort = True
                    progressed = True
                    continue
                if len(running) >= context.workers:
                    metrics.observe_blocked(
                        task.task_id,
                        ("worker_slots",),
                        admission_time,
                    )
                    continue
                grant = ledger.request(
                    task,
                    allow_expensive_producers=task_allows_expensive,
                )
                blocking_reasons = ledger.blocking_reasons(grant)
                if blocking_reasons:
                    resource_blocked_ready = True
                    metrics.observe_blocked(
                        task.task_id,
                        blocking_reasons,
                        admission_time,
                    )
                    continue
                pending.pop(task.task_id)
                started, output_dir = _begin_task(task, context)
                dependencies = _dependency_states(task, outcomes)
                ledger.acquire(grant)
                invocation = _RunningInvocation(
                    task=task,
                    started_at=started,
                    started_monotonic=time.monotonic(),
                    grant=grant,
                    output_dir=output_dir,
                )
                attempts[task.task_id] = attempts.get(task.task_id, 0) + 1
                if process_mode:
                    scheduled_attempts.append(
                        {
                            "task_id": task.task_id,
                            "output_dir": str(output_dir),
                        }
                    )
                    command = WorkerCommand(
                        task=task,
                        dependencies=dependencies,
                        run_id=context.run_store.run_id,
                        output_dir=output_dir,
                        allow_expensive_producers=task_allows_expensive,
                    )
                    try:
                        future = pool.submit(execute_worker_command, command)
                    except BrokenProcessPool:
                        running[object()] = invocation
                        metrics.scheduled(
                            task.task_id,
                            len(running),
                            admission_time,
                        )
                        broken_pool_count += 1
                        recover_generation("broken_process_pool_during_submit")
                        progressed = True
                        break
                else:
                    future = pool.submit(
                        _invoke_local_service,
                        task,
                        context,
                        dependencies,
                        output_dir,
                        allow_expensive_producers=task_allows_expensive,
                    )
                running[future] = invocation
                metrics.scheduled(
                    task.task_id,
                    len(running),
                    admission_time,
                )
                progressed = True

            if progressed and len(running) < context.workers:
                continue
            if running:
                wait_timeout = 1.0
                current_time = time.monotonic()
                for invocation in running.values():
                    timeout = invocation.task.timeout_seconds
                    if timeout is not None:
                        wait_timeout = min(
                            wait_timeout,
                            max(
                                0.0,
                                invocation.started_monotonic
                                + timeout
                                - current_time,
                            ),
                        )
                completed, _pending_futures = wait(
                    tuple(running),
                    timeout=wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                broken = False
                for future in completed:
                    try:
                        exception = future.exception()
                    except Exception as exc:
                        exception = exc
                    if isinstance(exception, BrokenProcessPool):
                        broken = True
                        break
                if broken:
                    broken_pool_count += 1
                    recover_generation("broken_process_pool")
                    continue
                for future in completed:
                    invocation = running.pop(future)
                    ledger.release(invocation.grant)
                    outcome = _finish_future(
                        invocation.task,
                        invocation.started_at,
                        future,
                        context,
                    )
                    outcomes[outcome.task_id] = outcome
                    if outcome.status == "failed" and not context.continue_on_endpoint_failure:
                        abort = True
                continue
            if pending:
                if process_mode and ready and resource_blocked_ready:
                    impossible: list[str] = []
                    for task in ready:
                        task_allows_expensive = (
                            context.allow_expensive_producers
                            and task.task_id not in cache_only_replays
                        )
                        grant = ledger.request(
                            task,
                            allow_expensive_producers=task_allows_expensive,
                        )
                        reasons = ledger.structural_blocking_reasons(grant)
                        if reasons:
                            impossible.append(
                                f"{task.task_id}:{','.join(reasons)}"
                            )
                    if impossible:
                        raise ExecutionError(
                            "executor found structurally inadmissible tasks: "
                            + ";".join(impossible)
                        )
                    time.sleep(1.0)
                    resource_monitor.sample_if_due(ledger, force=True)
                    continue
                raise ExecutionError(
                    "executor reached a dependency or resource-admission deadlock"
                )
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        resource_monitor.sample_if_due(ledger, force=True)
        terminal_now = time.monotonic()
        metrics.sample_scheduler_window(
            ready_task_count=0,
            running_task_count=0,
            ledger=ledger,
            now_monotonic=terminal_now,
            now_utc=_utc_now(),
            force=True,
        )
        scheduler_evidence = (
            context.run_store.write_execution_segment_scheduler_windows(
                segment_id,
                metrics.scheduler_windows,
            )
            if metrics.scheduler_windows
            else {
                "scheduler_windows_path": None,
                "scheduler_windows_sha256": None,
                "scheduler_window_count": 0,
            }
        )
        if process_mode:
            try:
                performance_payload = aggregate_performance_fragments(
                    scheduled_attempts
                )
                performance_payload["parent_events"] = performance_delta(
                    parent_performance_before,
                    performance_snapshot(),
                )
            except PerformanceInstrumentationError as exc:
                performance_payload = {
                    "schema_version": (
                        "dual_frequency_performance_event_report_v1"
                    ),
                    "aggregation_status": "failed",
                    "aggregation_error": f"{type(exc).__name__}: {exc}",
                    "scheduled_attempt_count": len(scheduled_attempts),
                    "fragment_count": 0,
                    "missing_fragment_count": len(scheduled_attempts),
                    "fragments": [],
                    "missing_fragments": list(scheduled_attempts),
                    "events": None,
                }
            performance_evidence = (
                context.run_store.write_execution_segment_performance_events(
                    segment_id,
                    performance_payload,
                )
            )
        else:
            performance_evidence = {
                "performance_events_path": None,
                "performance_events_sha256": None,
                "performance_fragment_count": 0,
                "performance_missing_fragment_count": 0,
            }
        context.run_store.finish_execution_segment(
            segment_id,
            {
                "finished_at": _utc_now(),
                "swap_delta_bytes": max(0, _swap_used_bytes() - initial_swap),
                "pool_generation_count": pool_generation_count,
                "task_timeout_count": task_timeout_count,
                "broken_pool_count": broken_pool_count,
                "transient_retry_count": transient_retry_count,
                "quarantined_attempt_count": quarantined_attempt_count,
                **metrics.as_dict(
                    terminal_task_count=len(outcomes),
                    ledger=ledger,
                    now=time.monotonic(),
                ),
                **resource_monitor.as_dict(),
                **scheduler_evidence,
                **performance_evidence,
            },
        )

    ordered = tuple(outcomes[task.task_id] for task in plan.tasks)
    exit_code = 1 if any(outcome.status == "failed" for outcome in ordered) else 0
    return RunResult(context.run_store.run_id, ordered, exit_code)
