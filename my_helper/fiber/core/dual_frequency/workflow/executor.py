"""Dependency-aware execution of generic dual-frequency workflow plans."""

from __future__ import annotations

import json
import multiprocessing
import os
import uuid
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..contracts import ArtifactRef, AxisRef
from ..contracts.identity import canonical_hash
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
        self.total_memory, self.available_memory = self._memory_state()
        self.reserve = max(16 * 1024**3, int(0.20 * self.total_memory))
        self.managed = min(
            64 * 1024**3,
            max(0, self.available_memory - self.reserve),
        )

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
    def request(task: TaskSpec) -> _ResourceGrant:
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
        if task.stage.startswith("oss_axis_equivalence_"):
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
        if self.cpu_used + grant.cpu > self.workers:
            return False
        if self.io_used + grant.connectome_io > self.io_limit:
            return False
        if self.solver_used + grant.solver > self.solver_limit:
            return False
        projected = self.available_memory - self.memory_used - grant.memory_bytes
        cumulative_memory = self.memory_used + grant.memory_bytes
        normal = (
            not cumulative_memory > self.managed
            and projected > self.reserve
        )
        return normal

    def acquire(self, grant: _ResourceGrant) -> None:
        self.cpu_used += grant.cpu
        self.memory_used += grant.memory_bytes
        self.io_used += grant.connectome_io
        self.solver_used += grant.solver

    def release(self, grant: _ResourceGrant) -> None:
        self.cpu_used -= grant.cpu
        self.memory_used -= grant.memory_bytes
        self.io_used -= grant.connectome_io
        self.solver_used -= grant.solver

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


def _swap_used_bytes() -> int:
    try:
        import psutil

        return int(psutil.swap_memory().used)
    except ImportError:
        return 0


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


def _restore_outcomes(plan: ExecutionPlan, context: ExecutionContext) -> dict[str, TaskOutcome]:
    if not context.resume:
        return {}
    output: dict[str, TaskOutcome] = {}
    invalid_completed: set[str] = set()
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
    return output


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
) -> ServiceResult:
    service = context.registry.resolve(task.service_id)
    request = TaskExecutionRequest(
        task=task,
        dependencies=dependencies,
        run_id=context.run_store.run_id,
        output_dir=output_dir,
        provider=context.provider,
        artifact_store=context.artifact_store,
        scientific_cache=context.scientific_cache,
        allow_expensive_producers=context.allow_expensive_producers,
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


def execute_plan(plan: ExecutionPlan, context: ExecutionContext) -> RunResult:
    """Execute a plan with local failure isolation and exact resume semantics."""
    if not isinstance(plan, ExecutionPlan):
        raise ExecutionError("plan must be an ExecutionPlan")
    try:
        context.registry.require(task.service_id for task in plan.tasks)
    except RegistryError as exc:
        raise ExecutionError(str(exc)) from exc

    task_index = {task.task_id: task for task in plan.tasks}
    outcomes = _restore_outcomes(plan, context)
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
    process_mode = context.spawn_worker_spec is not None
    initial_swap = _swap_used_bytes()
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

        pool = ProcessPoolExecutor(
            max_workers=context.workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=initialize_worker,
            initargs=(context.spawn_worker_spec,),
        )
    else:
        pool = ThreadPoolExecutor(max_workers=context.workers)
    running: dict[object, tuple[TaskSpec, str, _ResourceGrant]] = {}
    try:
        while pending or running:
            progressed = False
            ready = [
                task
                for task in plan.tasks
                if task.task_id in pending
                and all(dependency in outcomes for dependency in task.dependencies)
            ]
            for task in ready:
                if abort:
                    pending.pop(task.task_id)
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
                    and not context.allow_expensive_producers
                ):
                    pending.pop(task.task_id)
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
                if len(running) >= context.workers:
                    break
                grant = ledger.request(task)
                if not ledger.can_acquire(grant, len(running)):
                    continue
                pending.pop(task.task_id)
                started, output_dir = _begin_task(task, context)
                dependencies = _dependency_states(task, outcomes)
                if process_mode:
                    command = WorkerCommand(
                        task=task,
                        dependencies=dependencies,
                        run_id=context.run_store.run_id,
                        output_dir=output_dir,
                        allow_expensive_producers=context.allow_expensive_producers,
                    )
                    future = pool.submit(execute_worker_command, command)
                else:
                    future = pool.submit(
                        _invoke_local_service,
                        task,
                        context,
                        dependencies,
                        output_dir,
                    )
                ledger.acquire(grant)
                running[future] = (task, started, grant)
                progressed = True

            if progressed and len(running) < context.workers:
                continue
            if running:
                completed, _pending_futures = wait(
                    tuple(running),
                    return_when=FIRST_COMPLETED,
                )
                for future in completed:
                    task, started, grant = running.pop(future)
                    ledger.release(grant)
                    outcome = _finish_future(task, started, future, context)
                    outcomes[outcome.task_id] = outcome
                    if outcome.status == "failed" and not context.continue_on_endpoint_failure:
                        abort = True
                continue
            if pending:
                raise ExecutionError(
                    "executor reached a dependency or resource-admission deadlock"
                )
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        context.run_store.finish_execution_segment(
            segment_id,
            {
                "finished_at": _utc_now(),
                "swap_delta_bytes": max(0, _swap_used_bytes() - initial_swap),
            },
        )

    ordered = tuple(outcomes[task.task_id] for task in plan.tasks)
    exit_code = 1 if any(outcome.status == "failed" for outcome in ordered) else 0
    return RunResult(context.run_store.run_id, ordered, exit_code)
