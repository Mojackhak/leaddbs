"""Deterministic round-aware planning for configured four-model workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import heapq
from typing import Any, Iterable, Mapping, Sequence

from .catalog import CatalogStatus, EndpointRecord
from .config import ResolvedWorkflow
from .identity import EndpointModelKey, TaskKey


class PlanError(ValueError):
    """Raised when an execution plan is incomplete or cyclic."""


class DependencyRequirement(str, Enum):
    TERMINAL = "terminal"
    SUCCESS = "success"
    ACCEPTED_FINAL = "accepted_final"
    FORMAL_COMPLETE = "formal_complete"


class GatePredicate(str, Enum):
    ALWAYS = "always"
    ENDPOINT_DATA_AVAILABLE = "endpoint_data_available"
    BRANCH_INTENDED_OR_COMPARISON = "branch_intended_or_comparison"
    DELTA_HFSCORE_INPUTS_VALID = "delta_hfscore_inputs_valid"
    FINAL_MODEL_REALIZED = "final_model_realized"


@dataclass(frozen=True, order=True)
class DependencySpec:
    task_id: str
    requirement: DependencyRequirement

    def __post_init__(self) -> None:
        if not str(self.task_id).strip():
            raise PlanError("dependency task_id must be nonempty")

    def as_dict(self) -> dict[str, str]:
        return {"task_id": self.task_id, "requirement": self.requirement.value}


@dataclass(frozen=True)
class TaskGate:
    predicate: GatePredicate

    def as_dict(self) -> dict[str, str]:
        return {"predicate": self.predicate.value}


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    key: TaskKey
    endpoint: EndpointModelKey
    round_name: str
    workflow_phase: str
    dependencies: tuple[DependencySpec, ...]
    gate: TaskGate
    expected_artifact_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.task_id != self.key.identifier:
            raise PlanError("task_id must equal the canonical TaskKey identifier")
        if self.key.endpoint_model_id != self.endpoint.identifier:
            raise PlanError("TaskKey endpoint_model_id must match the embedded endpoint identity")
        if self.workflow_phase not in _PHASE_ORDER:
            raise PlanError(f"unknown workflow phase {self.workflow_phase!r}")
        if not self.round_name.startswith("Round "):
            raise PlanError("round_name must preserve model-document Round provenance")
        if not self.expected_artifact_kinds:
            raise PlanError("expected_artifact_kinds must be nonempty")
        if len({item.task_id for item in self.dependencies}) != len(self.dependencies):
            raise PlanError(f"task {self.task_id} has duplicate dependencies")

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            **self.key.as_dict(),
            "endpoint": self.endpoint.as_dict(),
            "round_name": self.round_name,
            "workflow_phase": self.workflow_phase,
            "dependencies": [item.as_dict() for item in self.dependencies],
            "gate": self.gate.as_dict(),
            "expected_artifact_kinds": list(self.expected_artifact_kinds),
        }


@dataclass(frozen=True)
class ExecutionPlan:
    through: str
    tasks: tuple[TaskSpec, ...]

    @classmethod
    def from_tasks(cls, tasks: Sequence[TaskSpec], *, through: str) -> "ExecutionPlan":
        if through not in _PHASE_ORDER:
            raise PlanError(f"unknown through phase {through!r}")
        out_of_scope = [task.task_id for task in tasks if _PHASE_ORDER[task.workflow_phase] > _PHASE_ORDER[through]]
        if out_of_scope:
            raise PlanError(f"tasks exceed through phase {through}: {','.join(sorted(out_of_scope))}")
        return cls(through=through, tasks=_topological_order(tuple(tasks)))

    def as_dict(self) -> dict[str, Any]:
        return {"through": self.through, "tasks": [task.as_dict() for task in self.tasks]}


_PHASE_ORDER = {"observed": 0, "formal": 1, "sensitivity": 2, "report": 3}
_MODEL_ORDER = {"hf_voxel": 0, "hf_fiber": 1, "ulf_voxel": 2, "ulf_fiber": 3}

_ARTIFACTS = {
    "readiness": ("task_manifest", "readiness_status"),
    "sidecars": ("task_manifest", "sidecar_index", "qc"),
    "observed": ("task_manifest", "observed_metrics", "loocv_predictions"),
    "resolver": ("task_manifest", "source_status", "selected_source"),
    "final": ("task_manifest", "final_model_status"),
    "control": ("task_manifest", "control_metrics"),
    "qualification": ("task_manifest", "qualification_status"),
    "permutation": ("task_manifest", "permutation_results"),
    "bootstrap": ("task_manifest", "bootstrap_results"),
    "formal": ("task_manifest", "permutation_results", "bootstrap_results"),
    "jitter": ("task_manifest", "jitter_results"),
    "sensitivity": ("task_manifest", "sensitivity_results"),
    "oss_sidecar": (
        "task_manifest",
        "oss_activation_probabilities",
        "oss_fiber_ids",
        "oss_parameter_manifest",
        "oss_activation_metadata",
    ),
    "oss": ("task_manifest", "oss_activation_results"),
    "summary": ("task_manifest", "endpoint_summary"),
    "report": ("task_manifest", "endpoint_report", "artifact_index"),
}


def _task_sort_key(task: TaskSpec) -> tuple[Any, ...]:
    return (
        task.endpoint.study_id,
        task.endpoint.scale_id,
        _MODEL_ORDER.get(task.endpoint.model_family, 99),
        task.endpoint.endpoint_phase,
        task.endpoint.connectome,
        _PHASE_ORDER[task.workflow_phase],
        _round_number(task.round_name),
        task.key.execution_stage,
        task.key.branch,
        task.task_id,
    )


def _round_number(round_name: str) -> float:
    token = round_name.split(maxsplit=1)[1]
    if token == "2b":
        return 2.1
    return float(token)


def _topological_order(tasks: tuple[TaskSpec, ...]) -> tuple[TaskSpec, ...]:
    by_id: dict[str, TaskSpec] = {}
    for task in tasks:
        if task.task_id in by_id:
            raise PlanError(f"duplicate task_id {task.task_id}")
        by_id[task.task_id] = task
    for task in tasks:
        missing = [item.task_id for item in task.dependencies if item.task_id not in by_id]
        if missing:
            raise PlanError(f"task {task.task_id} has missing dependencies: {','.join(sorted(missing))}")

    indegree = {task.task_id: len(task.dependencies) for task in tasks}
    children: dict[str, list[str]] = {task.task_id: [] for task in tasks}
    for task in tasks:
        for dependency in task.dependencies:
            children[dependency.task_id].append(task.task_id)
    ready = [(_task_sort_key(task), task.task_id) for task in tasks if indegree[task.task_id] == 0]
    heapq.heapify(ready)
    ordered: list[TaskSpec] = []
    while ready:
        _, task_id = heapq.heappop(ready)
        task = by_id[task_id]
        ordered.append(task)
        for child_id in sorted(children[task_id]):
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                child = by_id[child_id]
                heapq.heappush(ready, (_task_sort_key(child), child_id))
    if len(ordered) != len(tasks):
        cyclic = sorted(task_id for task_id, degree in indegree.items() if degree > 0)
        raise PlanError(f"execution plan contains a cycle: {','.join(cyclic)}")
    return tuple(ordered)


class _EndpointBuilder:
    def __init__(self, record: EndpointRecord) -> None:
        self.record = record
        self.tasks: list[TaskSpec] = []

    def add(
        self,
        operation: str,
        round_name: str,
        workflow_phase: str,
        artifact_group: str,
        *,
        dependencies: Iterable[tuple[TaskSpec, DependencyRequirement]] = (),
        gate: GatePredicate = GatePredicate.ENDPOINT_DATA_AVAILABLE,
        branch: str = "none",
        source_reference: str = "none",
    ) -> TaskSpec:
        key = TaskKey(
            endpoint_model_id=self.record.endpoint_model_id,
            execution_stage=operation,
            branch=branch,
            source_reference=source_reference,
        )
        dependency_specs = tuple(DependencySpec(task.task_id, requirement) for task, requirement in dependencies)
        task = TaskSpec(
            task_id=key.identifier,
            key=key,
            endpoint=self.record.key,
            round_name=round_name,
            workflow_phase=workflow_phase,
            dependencies=dependency_specs,
            gate=TaskGate(gate),
            expected_artifact_kinds=_ARTIFACTS[artifact_group],
        )
        self.tasks.append(task)
        return task

    def report(self, operation: str, round_name: str, dependencies: Sequence[TaskSpec], artifact_group: str) -> TaskSpec:
        return self.add(
            operation,
            round_name,
            "report",
            artifact_group,
            dependencies=((task, DependencyRequirement.TERMINAL) for task in dependencies),
            gate=GatePredicate.ALWAYS,
        )


def _hf_voxel_tasks(record: EndpointRecord) -> tuple[list[TaskSpec], TaskSpec]:
    builder = _EndpointBuilder(record)
    readiness = builder.add("input_readiness", "Round 0", "observed", "readiness", gate=GatePredicate.ALWAYS)
    sidecars = builder.add(
        "preprocessing_sidecars",
        "Round 1",
        "observed",
        "sidecars",
        dependencies=((readiness, DependencyRequirement.SUCCESS),),
    )
    resolver = builder.add(
        "observed_source_resolver",
        "Round 2",
        "observed",
        "resolver",
        dependencies=((sidecars, DependencyRequirement.SUCCESS),),
        source_reference="candidate_grid",
    )
    smoke = builder.add(
        "equivalence_smoke",
        "Round 3",
        "formal",
        "qualification",
        dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        source_reference="final_model_record",
    )
    permutation = builder.add(
        "formal_permutation",
        "Round 4",
        "formal",
        "permutation",
        dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        source_reference="final_model_record",
    )
    bootstrap = builder.add(
        "formal_bootstrap",
        "Round 5",
        "formal",
        "bootstrap",
        dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        source_reference="final_model_record",
    )
    builder.add(
        "spatial_jitter",
        "Round 6",
        "sensitivity",
        "jitter",
        dependencies=(
            (permutation, DependencyRequirement.FORMAL_COMPLETE),
            (bootstrap, DependencyRequirement.FORMAL_COMPLETE),
        ),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        source_reference="final_model_record",
    )
    builder.add(
        "selected_source_neighborhood",
        "Round 7",
        "sensitivity",
        "sensitivity",
        dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        source_reference="final_model_record",
    )
    builder.report("endpoint_report", "Round 8", tuple(builder.tasks), "report")
    return builder.tasks, resolver


def _hf_fiber_tasks(record: EndpointRecord, *, formal_connectome: bool) -> tuple[list[TaskSpec], TaskSpec]:
    builder = _EndpointBuilder(record)
    readiness = builder.add("version_input_freeze", "Round 0", "observed", "readiness", gate=GatePredicate.ALWAYS)
    sidecars = builder.add(
        "sidecar_equivalence",
        "Round 1",
        "observed",
        "sidecars",
        dependencies=((readiness, DependencyRequirement.SUCCESS),),
    )
    observed = builder.add(
        "observed_primary",
        "Round 2",
        "observed",
        "observed",
        dependencies=((sidecars, DependencyRequirement.SUCCESS),),
        source_reference="pre_specified_cell",
    )
    control = builder.add(
        "plain_connected_control",
        "Round 3",
        "observed",
        "control",
        dependencies=((observed, DependencyRequirement.SUCCESS),),
    )
    cheap = builder.add(
        "cheap_observed_sensitivity",
        "Round 5",
        "observed",
        "sensitivity",
        dependencies=((observed, DependencyRequirement.SUCCESS),),
    )
    resolver = builder.add(
        "observed_source_resolver",
        "Round 5.5",
        "observed",
        "resolver",
        dependencies=((control, DependencyRequirement.TERMINAL), (cheap, DependencyRequirement.SUCCESS)),
        source_reference="candidate_grid",
    )
    if formal_connectome:
        smoke = builder.add(
            "candidate_source_smoke",
            "Round 4",
            "formal",
            "qualification",
            dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            source_reference="final_model_record",
        )
        formal = builder.add(
            "formal_permutation_bootstrap",
            "Round 6",
            "formal",
            "formal",
            dependencies=((resolver, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            source_reference="final_model_record",
        )
        oss_sidecars = builder.add(
            "oss_sidecar_preparation",
            "Round 7",
            "sensitivity",
            "oss_sidecar",
            dependencies=((formal, DependencyRequirement.FORMAL_COMPLETE),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            source_reference="final_model_record",
        )
        builder.add(
            "oss_sensitivity",
            "Round 7",
            "sensitivity",
            "oss",
            dependencies=((oss_sidecars, DependencyRequirement.SUCCESS),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            source_reference="final_model_record",
        )
        builder.add(
            "spatial_jitter",
            "Round 8",
            "sensitivity",
            "jitter",
            dependencies=((formal, DependencyRequirement.FORMAL_COMPLETE),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            source_reference="final_model_record",
        )
    builder.report("endpoint_report", "Round 9", tuple(builder.tasks), "report")
    return builder.tasks, resolver


def _ulf_common(
    record: EndpointRecord,
    matched_hf_resolver: TaskSpec,
) -> tuple[_EndpointBuilder, TaskSpec, TaskSpec, TaskSpec]:
    builder = _EndpointBuilder(record)
    hf_lock = builder.add(
        "input_hf_lock",
        "Round 0",
        "observed",
        "readiness",
        dependencies=((matched_hf_resolver, DependencyRequirement.TERMINAL),),
        gate=GatePredicate.ALWAYS,
    )
    sidecars = builder.add(
        "preprocessing_sidecars",
        "Round 1",
        "observed",
        "sidecars",
        dependencies=((hf_lock, DependencyRequirement.SUCCESS),),
    )
    observed_round = "Round 2b" if record.key.endpoint_phase == "immediate" else "Round 2"
    branch_dependencies = (
        (sidecars, DependencyRequirement.SUCCESS),
        (matched_hf_resolver, DependencyRequirement.TERMINAL),
    )
    no_delta = builder.add(
        "observed_branch_resolver",
        observed_round,
        "observed",
        "resolver",
        dependencies=branch_dependencies,
        gate=GatePredicate.BRANCH_INTENDED_OR_COMPARISON,
        branch="no_delta_hf",
        source_reference="candidate_grid",
    )
    adjusted = builder.add(
        "observed_branch_resolver",
        observed_round,
        "observed",
        "resolver",
        dependencies=branch_dependencies,
        gate=GatePredicate.DELTA_HFSCORE_INPUTS_VALID,
        branch="delta_hf_adjusted",
        source_reference="candidate_grid",
    )
    final = builder.add(
        "final_model_realization",
        observed_round,
        "observed",
        "final",
        dependencies=(
            (no_delta, DependencyRequirement.TERMINAL),
            (adjusted, DependencyRequirement.TERMINAL),
        ),
        branch="resolver",
        source_reference="branch_source_records",
    )
    return builder, no_delta, adjusted, final


def _ulf_voxel_tasks(record: EndpointRecord, matched_hf_resolver: TaskSpec) -> list[TaskSpec]:
    builder, _, _, final = _ulf_common(record, matched_hf_resolver)
    smoke = builder.add(
        "equivalence_smoke",
        "Round 3",
        "formal",
        "qualification",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    permutation = builder.add(
        "formal_permutation",
        "Round 4",
        "formal",
        "permutation",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    bootstrap = builder.add(
        "formal_bootstrap",
        "Round 5",
        "formal",
        "bootstrap",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    builder.add(
        "spatial_jitter",
        "Round 6",
        "sensitivity",
        "jitter",
        dependencies=(
            (permutation, DependencyRequirement.FORMAL_COMPLETE),
            (bootstrap, DependencyRequirement.FORMAL_COMPLETE),
        ),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    builder.add(
        "selected_source_neighborhood",
        "Round 7",
        "sensitivity",
        "sensitivity",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    builder.add(
        "additional_sensitivities",
        "Round 8",
        "sensitivity",
        "sensitivity",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    summary = builder.report("endpoint_summary", "Round 8", tuple(builder.tasks), "summary")
    builder.report("endpoint_report", "Round 9", (summary,), "report")
    return builder.tasks


def _ulf_fiber_tasks(
    record: EndpointRecord,
    matched_hf_resolver: TaskSpec,
    *,
    formal_connectome: bool,
) -> list[TaskSpec]:
    builder, _, _, final = _ulf_common(record, matched_hf_resolver)
    builder.add(
        "plain_burden_controls",
        "Round 3",
        "observed",
        "control",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    builder.add(
        "cheap_observed_sensitivity",
        "Round 5",
        "sensitivity",
        "sensitivity",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    builder.add(
        "selected_source_neighborhood",
        "Round 6",
        "sensitivity",
        "sensitivity",
        dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
        gate=GatePredicate.FINAL_MODEL_REALIZED,
        branch="realized_final",
        source_reference="final_model_record",
    )
    if formal_connectome:
        smoke = builder.add(
            "candidate_source_smoke",
            "Round 4",
            "formal",
            "qualification",
            dependencies=((final, DependencyRequirement.ACCEPTED_FINAL),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            branch="realized_final",
            source_reference="final_model_record",
        )
        formal = builder.add(
            "formal_permutation_bootstrap",
            "Round 7",
            "formal",
            "formal",
            dependencies=((final, DependencyRequirement.ACCEPTED_FINAL), (smoke, DependencyRequirement.SUCCESS)),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            branch="realized_final",
            source_reference="final_model_record",
        )
        oss_sidecars = builder.add(
            "oss_sidecar_preparation",
            "Round 8",
            "sensitivity",
            "oss_sidecar",
            dependencies=((formal, DependencyRequirement.FORMAL_COMPLETE),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            branch="realized_final",
            source_reference="final_model_record",
        )
        builder.add(
            "oss_sensitivity",
            "Round 8",
            "sensitivity",
            "oss",
            dependencies=((oss_sidecars, DependencyRequirement.SUCCESS),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            branch="realized_final",
            source_reference="final_model_record",
        )
        builder.add(
            "spatial_jitter",
            "Round 9",
            "sensitivity",
            "jitter",
            dependencies=((formal, DependencyRequirement.FORMAL_COMPLETE),),
            gate=GatePredicate.FINAL_MODEL_REALIZED,
            branch="realized_final",
            source_reference="final_model_record",
        )
    builder.report("endpoint_report", "Round 10", tuple(builder.tasks), "report")
    return builder.tasks


def _matched_hf_record(record: EndpointRecord, catalog: Sequence[EndpointRecord]) -> EndpointRecord:
    expected_family = "hf_voxel" if record.key.model_family == "ulf_voxel" else "hf_fiber"
    candidates = [
        item
        for item in catalog
        if item.key.study_id == record.key.study_id
        and item.key.scale_id == record.key.scale_id
        and item.key.model_family == expected_family
        and item.key.endpoint_phase == "reference"
        and item.key.connectome == record.key.connectome
        and item.outcome_protocol == record.hf_reference_protocol
        and item.outcome_phase == record.hf_reference_phase
    ]
    if len(candidates) != 1:
        raise PlanError(
            f"endpoint {record.endpoint_model_id} requires exactly one matched {expected_family} dependency; "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _is_formal_connectome(config: ResolvedWorkflow, record: EndpointRecord) -> bool:
    roles: Mapping[str, str] = config.model.normative_fiber["connectome_roles"]
    return roles.get(record.key.connectome) == "formal"


def compile_execution_plan(
    config: ResolvedWorkflow,
    catalog: Sequence[EndpointRecord],
) -> ExecutionPlan:
    """Compile a deterministic, dependency-complete plan through the requested phase."""
    executable_records = [record for record in catalog if record.status != CatalogStatus.NOT_CONFIGURED]
    all_tasks: list[TaskSpec] = []
    hf_resolvers: dict[str, TaskSpec] = {}

    for record in executable_records:
        if record.key.model_family == "hf_voxel":
            tasks, resolver = _hf_voxel_tasks(record)
        elif record.key.model_family == "hf_fiber":
            tasks, resolver = _hf_fiber_tasks(record, formal_connectome=_is_formal_connectome(config, record))
        else:
            continue
        all_tasks.extend(tasks)
        hf_resolvers[record.endpoint_model_id] = resolver

    for record in executable_records:
        if not record.key.model_family.startswith("ulf_"):
            continue
        matched_record = _matched_hf_record(record, executable_records)
        try:
            matched_resolver = hf_resolvers[matched_record.endpoint_model_id]
        except KeyError as exc:
            raise PlanError(f"matched HF resolver is missing for endpoint {record.endpoint_model_id}") from exc
        if record.key.model_family == "ulf_voxel":
            all_tasks.extend(_ulf_voxel_tasks(record, matched_resolver))
        else:
            all_tasks.extend(
                _ulf_fiber_tasks(
                    record,
                    matched_resolver,
                    formal_connectome=_is_formal_connectome(config, record),
                )
            )

    through = config.workflow.execution.through
    selected_tasks = tuple(
        task for task in all_tasks if _PHASE_ORDER[task.workflow_phase] <= _PHASE_ORDER[through]
    )
    return ExecutionPlan.from_tasks(selected_tasks, through=through)
