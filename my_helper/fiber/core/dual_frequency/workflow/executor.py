"""Dependency-aware execution of generic dual-frequency workflow plans."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
ARTIFACT_REQUIRED_OUTPUTS = frozenset(
    {
        "ArtifactRef",
        "ObservedResult",
        "FormalResult",
        "SensitivityResult",
        "ActivationArtifact",
        "ReportArtifact",
    }
)


class ExecutionError(RuntimeError):
    """Raised when a workflow cannot be executed under its declared contract."""


class ExpensiveProducerNotAuthorized(ExecutionError):
    """Raised before an unauthorized expensive producer can be invoked."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    """Persistable service output envelope."""

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
    def create(
        cls,
        output_record_type: str,
        record_id: str,
        payload: Mapping[str, Any],
        *,
        artifacts: tuple[ArtifactRef, ...] = (),
        facts: Mapping[str, bool] | tuple[RuntimeFact, ...] = (),
    ) -> "ServiceResult":
        if isinstance(facts, Mapping):
            fact_values = tuple(RuntimeFact(name, value) for name, value in facts.items())
        else:
            fact_values = tuple(facts)
        return cls(
            output_record_type=output_record_type,
            record_id=record_id,
            payload_json=json.dumps(dict(payload), allow_nan=False),
            artifacts=tuple(artifacts),
            facts=fact_values,
        )

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def fact_values(self) -> dict[str, bool]:
        return {fact.name: fact.value for fact in self.facts}

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_record_type": self.output_record_type,
            "record_id": self.record_id,
            "payload": self.payload,
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
            "facts": self.fact_values,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ServiceResult":
        artifacts: list[ArtifactRef] = []
        for item in payload.get("artifacts", []):
            item = dict(item)
            item["axis_refs"] = tuple(AxisRef(**axis) for axis in item.get("axis_refs", []))
            item["axis_hashes"] = tuple(item.get("axis_hashes", []))
            if item.get("shape") is not None:
                item["shape"] = tuple(item["shape"])
            artifacts.append(ArtifactRef(**item))
        return cls.create(
            str(payload["output_record_type"]),
            str(payload["record_id"]),
            payload.get("payload", {}),
            artifacts=tuple(artifacts),
            facts={str(key): value for key, value in payload.get("facts", {}).items()},
        )


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
    """Direct dependency state supplied to a service."""

    status: str
    reason: str
    result: ServiceResult | None


@dataclass(frozen=True)
class TaskExecutionRequest:
    """Runtime request supplied to a registered service."""

    task: TaskSpec
    dependencies: Mapping[str, DependencyState]
    run_id: str
    output_dir: Path
    artifact_store: object | None
    scientific_cache: object | None
    allow_expensive_producers: bool
    workers: int


@dataclass(frozen=True)
class ExecutionContext:
    """Explicit execution dependencies and policy."""

    run_store: RunStore
    registry: ServiceRegistry
    endpoint_facts: Mapping[str, Mapping[str, bool]]
    allow_expensive_producers: bool
    continue_on_endpoint_failure: bool
    workers: int
    artifact_store: object | None = None
    scientific_cache: object | None = None
    resume: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.run_store, RunStore):
            raise ExecutionError("run_store must be a RunStore")
        if not isinstance(self.registry, ServiceRegistry):
            raise ExecutionError("registry must be a ServiceRegistry")
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
    """Return the exact hash used by run-store resume validation."""
    return canonical_hash({"plan": asdict(plan)})


def _write_outcome(store: RunStore, outcome: TaskOutcome) -> None:
    store.write_task_state(outcome.task_id, outcome.as_dict())


def _restore_outcomes(plan: ExecutionPlan, context: ExecutionContext) -> dict[str, TaskOutcome]:
    if not context.resume:
        return {}
    output: dict[str, TaskOutcome] = {}
    for task in plan.tasks:
        payload = context.run_store.read_task_state(task.task_id)
        if payload is None:
            continue
        outcome = TaskOutcome.from_dict(payload)
        if outcome.endpoint_id != task.endpoint_id or outcome.service_id != task.service_id:
            raise ExecutionError(f"resume task identity mismatch for {task.task_id}")
        if outcome.status in {"completed", "skipped"}:
            output[task.task_id] = outcome
    return output


def _ancestor_ids(task: TaskSpec, tasks: Mapping[str, TaskSpec]) -> tuple[str, ...]:
    seen: set[str] = set()
    pending = list(task.dependencies)
    while pending:
        task_id = pending.pop()
        if task_id in seen:
            continue
        seen.add(task_id)
        pending.extend(tasks[task_id].dependencies)
    return tuple(sorted(seen))


def _resolve_fact(
    task: TaskSpec,
    fact_name: str,
    tasks: Mapping[str, TaskSpec],
    outcomes: Mapping[str, TaskOutcome],
    endpoint_facts: Mapping[str, Mapping[str, bool]],
) -> bool:
    values: set[bool] = set()
    static = endpoint_facts.get(task.endpoint_id, {})
    if fact_name in static:
        values.add(static[fact_name])
    for ancestor_id in _ancestor_ids(task, tasks):
        outcome = outcomes.get(ancestor_id)
        if outcome is None or outcome.result is None:
            continue
        fact_values = outcome.result.fact_values
        if fact_name in fact_values:
            values.add(fact_values[fact_name])
    if not values:
        raise ExecutionError(f"runtime fact {fact_name!r} is unavailable for {task.task_id}")
    if len(values) != 1:
        raise ExecutionError(f"runtime fact {fact_name!r} is contradictory for {task.task_id}")
    return next(iter(values))


def _dependency_states(
    task: TaskSpec,
    outcomes: Mapping[str, TaskOutcome],
) -> dict[str, DependencyState]:
    return {
        dependency_id: DependencyState(
            status=outcomes[dependency_id].status,
            reason=outcomes[dependency_id].reason,
            result=outcomes[dependency_id].result,
        )
        for dependency_id in task.dependencies
    }


def _validate_service_result(task: TaskSpec, result: object) -> ServiceResult:
    if not isinstance(result, ServiceResult):
        raise ExecutionError(f"service {task.service_id!r} did not return ServiceResult")
    if result.output_record_type != task.output_record_type:
        raise ExecutionError(
            f"service {task.service_id!r} returned {result.output_record_type!r}; "
            f"expected {task.output_record_type!r}"
        )
    if task.output_record_type in ARTIFACT_REQUIRED_OUTPUTS and not result.artifacts:
        raise ExecutionError(
            f"task {task.task_id} requires at least one declared artifact"
        )
    return result


def _run_task(task: TaskSpec, context: ExecutionContext, outcomes: Mapping[str, TaskOutcome]) -> TaskOutcome:
    started = _utc_now()
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
    output_dir = context.run_store.root / "work" / task.task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        service = context.registry.resolve(task.service_id)
        request = TaskExecutionRequest(
            task=task,
            dependencies=_dependency_states(task, outcomes),
            run_id=context.run_store.run_id,
            output_dir=output_dir,
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
    if context.run_store.identity.configuration_hash != plan.configuration_hash:
        raise ExecutionError("run store configuration hash does not match plan")
    if context.run_store.identity.scientific_configuration_hash != plan.scientific_configuration_hash:
        raise ExecutionError("run store scientific configuration hash does not match plan")
    if context.run_store.identity.plan_hash != plan_hash(plan):
        raise ExecutionError("run store plan hash does not match plan")
    try:
        context.registry.require(task.service_id for task in plan.tasks)
    except RegistryError as exc:
        raise ExecutionError(str(exc)) from exc

    task_index = {task.task_id: task for task in plan.tasks}
    outcomes = _restore_outcomes(plan, context)
    pending = {task.task_id: task for task in plan.tasks if task.task_id not in outcomes}
    abort = False

    while pending:
        ready = [
            task
            for task in plan.tasks
            if task.task_id in pending and all(dependency in outcomes for dependency in task.dependencies)
        ]
        if not ready:
            raise ExecutionError("executor reached a dependency deadlock")

        runnable: list[TaskSpec] = []
        for task in ready:
            pending.pop(task.task_id)
            if abort:
                outcomes[task.task_id] = _skipped(task, "not_run_batch_aborted", context.run_store)
                continue
            dependency_outcomes = tuple(outcomes[item] for item in task.dependencies)
            blocking = tuple(
                outcome
                for outcome in dependency_outcomes
                if outcome.status == "failed"
                or (outcome.status == "skipped" and outcome.reason.startswith("dependency_failure"))
            )
            if blocking:
                outcomes[task.task_id] = _skipped(
                    task,
                    "dependency_failure:" + ",".join(item.task_id for item in blocking),
                    context.run_store,
                )
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
                outcomes[task.task_id] = _failed(task, str(exc), context.run_store)
                if not context.continue_on_endpoint_failure:
                    abort = True
                continue
            if failed_gate is not None:
                outcomes[task.task_id] = _skipped(
                    task,
                    failed_gate.false_status,
                    context.run_store,
                )
                continue
            if (
                task.expensive_producer
                and not task.cache_first_expensive
                and not context.allow_expensive_producers
            ):
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
                continue
            runnable.append(task)

        if runnable:
            snapshot = dict(outcomes)
            with ThreadPoolExecutor(max_workers=context.workers) as pool:
                futures = {
                    pool.submit(_run_task, task, context, snapshot): task
                    for task in runnable
                }
                for future in as_completed(futures):
                    outcome = future.result()
                    outcomes[outcome.task_id] = outcome
                    if outcome.status == "failed" and not context.continue_on_endpoint_failure:
                        abort = True

    ordered = tuple(outcomes[task.task_id] for task in plan.tasks)
    exit_code = 1 if any(outcome.status == "failed" for outcome in ordered) else 0
    context.run_store.finalize("failed" if exit_code else "completed")
    return RunResult(context.run_store.run_id, ordered, exit_code)
