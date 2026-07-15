"""Compile a deterministic, round-aware execution DAG from endpoint records."""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog import CatalogStatus, EndpointRecord
from ..config import ResolvedWorkflow
from ..contracts import TaskKey


PHASE_ORDER = {
    "observed": 0,
    "formal": 1,
    "sensitivity": 2,
    "report": 3,
}


class PlanningError(ValueError):
    """Raised when an endpoint catalog cannot form a closed execution DAG."""


@dataclass(frozen=True)
class GateRequirement:
    """Typed runtime fact required before a statically planned task executes."""

    fact: str
    false_status: str

    def __post_init__(self) -> None:
        if not self.fact.strip() or not self.false_status.strip():
            raise PlanningError("gate fact and false status must be nonempty")


@dataclass(frozen=True)
class TaskSpec:
    """One immutable service invocation in topological order."""

    key: TaskKey
    endpoint_id: str
    model_family: str
    connectome_role: str
    stage: str
    round_id: str
    phase: str
    service_id: str
    dependencies: tuple[str, ...]
    gates: tuple[GateRequirement, ...]
    output_record_type: str
    expensive_producer: bool = False
    cache_first_expensive: bool = False

    def __post_init__(self) -> None:
        if self.cache_first_expensive and not self.expensive_producer:
            raise PlanningError(
                "cache_first_expensive requires expensive_producer=True"
            )

    @property
    def task_id(self) -> str:
        return self.key.identifier


@dataclass(frozen=True)
class ExecutionPlan:
    """Topologically ordered tasks for one resolved configuration."""

    configuration_hash: str
    scientific_configuration_hash: str
    through: str
    tasks: tuple[TaskSpec, ...]

    def __post_init__(self) -> None:
        if self.through not in PHASE_ORDER:
            raise PlanningError(f"unsupported execution cutoff {self.through!r}")
        seen: set[str] = set()
        for task in self.tasks:
            if task.task_id in seen:
                raise PlanningError(f"duplicate task ID {task.task_id!r}")
            missing = tuple(item for item in task.dependencies if item not in seen)
            if missing:
                raise PlanningError(
                    f"task {task.task_id!r} has non-topological dependencies {missing}"
                )
            seen.add(task.task_id)

    def for_endpoint(self, endpoint_id: str) -> tuple[TaskSpec, ...]:
        return tuple(item for item in self.tasks if item.endpoint_id == endpoint_id)


class _TaskFactory:
    def __init__(self, configuration_hash: str, through: str) -> None:
        self.configuration_hash = configuration_hash
        self.through = through
        self.tasks: list[TaskSpec] = []
        self.stage_ids: dict[tuple[str, str], str] = {}

    def includes(self, phase: str) -> bool:
        return PHASE_ORDER[phase] <= PHASE_ORDER[self.through]

    def add(
        self,
        endpoint: EndpointRecord,
        *,
        stage: str,
        round_id: str,
        phase: str,
        service_id: str,
        dependencies: tuple[str | None, ...] = (),
        gates: tuple[GateRequirement, ...] = (),
        output_record_type: str,
        branch: str = "none",
        expensive_producer: bool = False,
        cache_first_expensive: bool = False,
    ) -> str | None:
        if not self.includes(phase):
            return None
        if any(item is None for item in dependencies):
            raise PlanningError(
                f"task {endpoint.endpoint_id}/{stage} depends on a task outside the execution cutoff"
            )
        dependency_ids = tuple(str(item) for item in dependencies)
        key = TaskKey(
            endpoint_id=endpoint.endpoint_id,
            stage=stage,
            branch=branch,
            parameter_identity=self.configuration_hash,
        )
        task = TaskSpec(
            key=key,
            endpoint_id=endpoint.endpoint_id,
            model_family=endpoint.key.model_family,
            connectome_role=endpoint.connectome_role,
            stage=stage,
            round_id=round_id,
            phase=phase,
            service_id=service_id,
            dependencies=dependency_ids,
            gates=gates,
            output_record_type=output_record_type,
            expensive_producer=expensive_producer,
            cache_first_expensive=cache_first_expensive,
        )
        self.tasks.append(task)
        self.stage_ids[(endpoint.endpoint_id, stage)] = task.task_id
        return task.task_id

    def stage(self, endpoint_id: str, stage: str) -> str:
        try:
            return self.stage_ids[(endpoint_id, stage)]
        except KeyError as exc:
            raise PlanningError(f"missing planned stage {endpoint_id}/{stage}") from exc


CATALOG_AVAILABLE = GateRequirement("catalog_data_available", "not_run_catalog_unavailable")
ENDPOINT_INPUT_READY = GateRequirement(
    "endpoint_input_ready",
    "not_run_endpoint_input_not_ready",
)
REFERENCE_DEPENDENCY_READY = GateRequirement(
    "reference_dependency_ready",
    "not_run_reference_dependency_failure",
)
REFERENCE_SOURCE_ACCEPTED = GateRequirement(
    "reference_source_accepted",
    "not_run_reference_source_absent",
)
DELTA_INPUTS_VALID = GateRequirement("delta_inputs_valid", "not_run_delta_inputs_invalid")
FINAL_REALIZED = GateRequirement("final_model_realized", "not_run_no_final_model")
FORMAL_COMPLETE = GateRequirement("formal_complete", "not_run_formal_incomplete")
FORMAL_SOURCE_AVAILABLE = GateRequirement(
    "formal_source_available",
    "not_run_formal_source_unavailable",
)


def _plan_reference_voxel(factory: _TaskFactory, endpoint: EndpointRecord) -> None:
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_reference_voxel_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_reference_voxel_exposure",
        dependencies=(readiness,),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="PreparedExposureRecord",
    )
    observed = factory.add(
        endpoint,
        stage="observed_grid",
        round_id="round_2",
        phase="observed",
        service_id="run_reference_voxel_observed_grid",
        dependencies=(readiness, prepare),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="ObservedResult",
    )
    resolver = factory.add(
        endpoint,
        stage="source_resolver",
        round_id="round_2",
        phase="observed",
        service_id="resolve_reference_voxel_source",
        dependencies=(observed,),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="SourceRecord",
    )
    final = factory.add(
        endpoint,
        stage="final_realization",
        round_id="round_2",
        phase="observed",
        service_id="realize_reference_final",
        dependencies=(readiness, resolver),
        output_record_type="FinalSelectionRecord",
    )
    factory.add(
        endpoint,
        stage="formal_permutation",
        round_id="round_4",
        phase="formal",
        service_id="run_reference_voxel_formal_permutation",
        dependencies=(readiness, prepare, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    formal_bootstrap = factory.add(
        endpoint,
        stage="formal_bootstrap",
        round_id="round_5",
        phase="formal",
        service_id="run_reference_voxel_formal_bootstrap",
        dependencies=(readiness, prepare, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    factory.add(
        endpoint,
        stage="spatial_jitter",
        round_id="round_6",
        phase="sensitivity",
        service_id="run_reference_voxel_jitter",
        dependencies=(readiness, prepare, final, formal_bootstrap),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="selected_source_neighborhood",
        round_id="round_7",
        phase="sensitivity",
        service_id="run_reference_voxel_source_neighborhood",
        dependencies=(readiness, prepare, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )


def _plan_reference_fiber_formal(factory: _TaskFactory, endpoint: EndpointRecord) -> None:
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_reference_fiber_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_reference_fiber_sidecar",
        dependencies=(readiness,),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="PreparedExposureRecord",
    )
    observed = factory.add(
        endpoint,
        stage="observed_grid",
        round_id="round_2",
        phase="observed",
        service_id="run_reference_fiber_observed_grid",
        dependencies=(readiness, prepare),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="ObservedResult",
    )
    resolver = factory.add(
        endpoint,
        stage="source_resolver",
        round_id="round_5_5",
        phase="observed",
        service_id="resolve_reference_fiber_source",
        dependencies=(observed,),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="SourceRecord",
    )
    final = factory.add(
        endpoint,
        stage="final_realization",
        round_id="round_5_5",
        phase="observed",
        service_id="realize_reference_final",
        dependencies=(readiness, resolver),
        output_record_type="FinalSelectionRecord",
    )
    formal_permutation = factory.add(
        endpoint,
        stage="formal_permutation",
        round_id="round_6",
        phase="formal",
        service_id="run_reference_fiber_formal_permutation",
        dependencies=(readiness, prepare, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    formal_bootstrap = factory.add(
        endpoint,
        stage="formal_bootstrap",
        round_id="round_6",
        phase="formal",
        service_id="run_reference_fiber_formal_bootstrap",
        dependencies=(readiness, prepare, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    factory.add(
        endpoint,
        stage="plain_control",
        round_id="round_3",
        phase="sensitivity",
        service_id="run_reference_fiber_plain_control",
        dependencies=(readiness, prepare, observed),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="cheap_observed_sensitivity",
        round_id="round_5",
        phase="sensitivity",
        service_id="run_reference_fiber_cheap_sensitivity",
        dependencies=(readiness, prepare, observed),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="activation_sensitivity",
        round_id="round_7",
        phase="sensitivity",
        service_id="run_reference_fiber_activation",
        dependencies=(readiness, prepare, final, formal_permutation, formal_bootstrap),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="ActivationArtifact",
        expensive_producer=True,
        cache_first_expensive=True,
    )
    factory.add(
        endpoint,
        stage="spatial_jitter",
        round_id="round_8",
        phase="sensitivity",
        service_id="run_reference_fiber_jitter",
        dependencies=(
            readiness,
            prepare,
            final,
            formal_permutation,
            formal_bootstrap,
        ),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="SensitivityResult",
    )


def _plan_reference_fiber_sensitive(
    factory: _TaskFactory,
    endpoint: EndpointRecord,
    formal_endpoint: EndpointRecord,
) -> None:
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_reference_fiber_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_reference_fiber_sidecar",
        dependencies=(readiness,),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="PreparedExposureRecord",
    )
    observed = factory.add(
        endpoint,
        stage="observed_grid",
        round_id="round_2",
        phase="observed",
        service_id="run_reference_fiber_observed_grid",
        dependencies=(readiness, prepare),
        gates=(ENDPOINT_INPUT_READY,),
        output_record_type="ObservedResult",
    )
    formal_source = factory.stage(formal_endpoint.endpoint_id, "source_resolver")
    factory.add(
        endpoint,
        stage="formal_source_evaluation",
        round_id="round_5_5",
        phase="observed",
        service_id="evaluate_sensitive_connectome_at_formal_source",
        dependencies=(readiness, prepare, observed, formal_source),
        gates=(ENDPOINT_INPUT_READY, FORMAL_SOURCE_AVAILABLE),
        output_record_type="SensitiveRecord",
    )


def _plan_addon_voxel(
    factory: _TaskFactory,
    endpoint: EndpointRecord,
    reference_endpoint: EndpointRecord,
) -> None:
    reference_source = factory.stage(reference_endpoint.endpoint_id, "source_resolver")
    reference_readiness = factory.stage(
        reference_endpoint.endpoint_id,
        "input_readiness",
    )
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_addon_voxel_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    dependency = factory.add(
        endpoint,
        stage="reference_dependency",
        round_id="round_0",
        phase="observed",
        service_id="bind_reference_dependency",
        dependencies=(reference_source,),
        output_record_type="ReferenceDependencyRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_addon_voxel_exposure",
        dependencies=(readiness, dependency),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="PreparedExposureRecord",
    )
    delta = factory.add(
        endpoint,
        stage="delta_reference_input",
        round_id="round_1",
        phase="observed",
        service_id="build_voxel_delta_reference_input",
        dependencies=(
            readiness,
            reference_readiness,
            dependency,
            prepare,
            reference_source,
        ),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
        ),
        output_record_type="DeltaReferenceBundle",
    )
    no_delta = factory.add(
        endpoint,
        stage="branch_no_delta_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_addon_voxel_branch",
        dependencies=(readiness, dependency, prepare),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="BranchRecord",
        branch="no_delta_reference",
    )
    adjusted = factory.add(
        endpoint,
        stage="branch_delta_adjusted_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_addon_voxel_branch",
        dependencies=(readiness, dependency, prepare, delta),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
            DELTA_INPUTS_VALID,
        ),
        output_record_type="BranchRecord",
        branch="delta_reference_adjusted",
    )
    final = factory.add(
        endpoint,
        stage="final_realization",
        round_id="round_2",
        phase="observed",
        service_id="realize_addon_final",
        dependencies=(readiness, dependency, delta, no_delta, adjusted),
        output_record_type="FinalSelectionRecord",
    )
    factory.add(
        endpoint,
        stage="formal_permutation",
        round_id="round_4",
        phase="formal",
        service_id="run_addon_voxel_formal_permutation",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    formal_bootstrap = factory.add(
        endpoint,
        stage="formal_bootstrap",
        round_id="round_5",
        phase="formal",
        service_id="run_addon_voxel_formal_bootstrap",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    factory.add(
        endpoint,
        stage="spatial_jitter",
        round_id="round_6",
        phase="sensitivity",
        service_id="run_addon_voxel_jitter",
        dependencies=(
            readiness,
            reference_readiness,
            dependency,
            prepare,
            delta,
            final,
            formal_bootstrap,
        ),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="selected_source_neighborhood",
        round_id="round_7",
        phase="sensitivity",
        service_id="run_addon_voxel_source_neighborhood",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="additional_sensitivities",
        round_id="round_8",
        phase="sensitivity",
        service_id="run_addon_voxel_additional_sensitivities",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )


def _plan_addon_fiber_formal(
    factory: _TaskFactory,
    endpoint: EndpointRecord,
    reference_endpoint: EndpointRecord,
) -> None:
    reference_source = factory.stage(reference_endpoint.endpoint_id, "source_resolver")
    reference_readiness = factory.stage(
        reference_endpoint.endpoint_id,
        "input_readiness",
    )
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_addon_fiber_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    dependency = factory.add(
        endpoint,
        stage="reference_dependency",
        round_id="round_0",
        phase="observed",
        service_id="bind_reference_dependency",
        dependencies=(reference_source,),
        output_record_type="ReferenceDependencyRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_addon_fiber_sidecars",
        dependencies=(readiness, dependency),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="PreparedExposureRecord",
    )
    delta = factory.add(
        endpoint,
        stage="delta_reference_input",
        round_id="round_1",
        phase="observed",
        service_id="build_fiber_delta_reference_input",
        dependencies=(
            readiness,
            reference_readiness,
            dependency,
            prepare,
            reference_source,
        ),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
        ),
        output_record_type="DeltaReferenceBundle",
    )
    no_delta = factory.add(
        endpoint,
        stage="branch_no_delta_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_addon_fiber_branch",
        dependencies=(readiness, dependency, prepare),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="BranchRecord",
        branch="no_delta_reference",
    )
    adjusted = factory.add(
        endpoint,
        stage="branch_delta_adjusted_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_addon_fiber_branch",
        dependencies=(readiness, dependency, prepare, delta),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
            DELTA_INPUTS_VALID,
        ),
        output_record_type="BranchRecord",
        branch="delta_reference_adjusted",
    )
    final = factory.add(
        endpoint,
        stage="final_realization",
        round_id="round_2",
        phase="observed",
        service_id="realize_addon_final",
        dependencies=(readiness, dependency, delta, no_delta, adjusted),
        output_record_type="FinalSelectionRecord",
    )
    formal_permutation = factory.add(
        endpoint,
        stage="formal_permutation",
        round_id="round_7",
        phase="formal",
        service_id="run_addon_fiber_formal_permutation",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    formal_bootstrap = factory.add(
        endpoint,
        stage="formal_bootstrap",
        round_id="round_7",
        phase="formal",
        service_id="run_addon_fiber_formal_bootstrap",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="FormalResult",
    )
    factory.add(
        endpoint,
        stage="plain_burden_controls",
        round_id="round_3",
        phase="sensitivity",
        service_id="run_addon_fiber_plain_burden_controls",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="cheap_observed_sensitivity",
        round_id="round_5",
        phase="sensitivity",
        service_id="run_addon_fiber_cheap_sensitivity",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="selected_source_neighborhood",
        round_id="round_6",
        phase="sensitivity",
        service_id="run_addon_fiber_source_neighborhood",
        dependencies=(readiness, prepare, delta, final),
        gates=(FINAL_REALIZED,),
        output_record_type="SensitivityResult",
    )
    factory.add(
        endpoint,
        stage="activation_sensitivity",
        round_id="round_8",
        phase="sensitivity",
        service_id="run_addon_fiber_activation",
        dependencies=(
            readiness,
            prepare,
            delta,
            final,
            formal_permutation,
            formal_bootstrap,
        ),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="ActivationArtifact",
        expensive_producer=True,
        cache_first_expensive=True,
    )
    factory.add(
        endpoint,
        stage="spatial_jitter",
        round_id="round_9",
        phase="sensitivity",
        service_id="run_addon_fiber_jitter",
        dependencies=(
            readiness,
            reference_readiness,
            dependency,
            prepare,
            delta,
            final,
            formal_permutation,
            formal_bootstrap,
        ),
        gates=(FINAL_REALIZED, FORMAL_COMPLETE),
        output_record_type="SensitivityResult",
    )


def _plan_addon_fiber_sensitive(
    factory: _TaskFactory,
    endpoint: EndpointRecord,
    reference_endpoint: EndpointRecord,
    formal_addon_endpoint: EndpointRecord,
) -> None:
    reference_evaluation = factory.stage(reference_endpoint.endpoint_id, "formal_source_evaluation")
    reference_readiness = factory.stage(
        reference_endpoint.endpoint_id,
        "input_readiness",
    )
    formal_final = factory.stage(formal_addon_endpoint.endpoint_id, "final_realization")
    readiness = factory.add(
        endpoint,
        stage="input_readiness",
        round_id="round_0",
        phase="observed",
        service_id="validate_addon_fiber_input",
        gates=(CATALOG_AVAILABLE,),
        output_record_type="EndpointInputRecord",
    )
    dependency = factory.add(
        endpoint,
        stage="reference_dependency",
        round_id="round_0",
        phase="observed",
        service_id="bind_reference_dependency",
        dependencies=(reference_evaluation,),
        output_record_type="ReferenceDependencyRecord",
    )
    prepare = factory.add(
        endpoint,
        stage="prepare_exposure",
        round_id="round_1",
        phase="observed",
        service_id="prepare_addon_fiber_sidecars",
        dependencies=(readiness, dependency),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="PreparedExposureRecord",
    )
    delta = factory.add(
        endpoint,
        stage="delta_reference_input",
        round_id="round_1",
        phase="observed",
        service_id="build_fiber_delta_reference_input",
        dependencies=(
            readiness,
            reference_readiness,
            dependency,
            prepare,
            reference_evaluation,
        ),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
        ),
        output_record_type="DeltaReferenceBundle",
    )
    no_delta = factory.add(
        endpoint,
        stage="branch_no_delta_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_sensitive_addon_fiber_branch",
        dependencies=(readiness, dependency, prepare),
        gates=(ENDPOINT_INPUT_READY, REFERENCE_DEPENDENCY_READY),
        output_record_type="BranchRecord",
        branch="no_delta_reference",
    )
    adjusted = factory.add(
        endpoint,
        stage="branch_delta_adjusted_observed",
        round_id="round_2",
        phase="observed",
        service_id="run_sensitive_addon_fiber_branch",
        dependencies=(readiness, dependency, prepare, delta),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            REFERENCE_SOURCE_ACCEPTED,
            DELTA_INPUTS_VALID,
        ),
        output_record_type="BranchRecord",
        branch="delta_reference_adjusted",
    )
    factory.add(
        endpoint,
        stage="formal_source_evaluation",
        round_id="round_2",
        phase="observed",
        service_id="evaluate_sensitive_addon_at_formal_final",
        dependencies=(readiness, prepare, delta, no_delta, adjusted, formal_final),
        gates=(
            ENDPOINT_INPUT_READY,
            REFERENCE_DEPENDENCY_READY,
            FORMAL_SOURCE_AVAILABLE,
        ),
        output_record_type="SensitiveRecord",
    )


def _records_by_role(
    catalog: tuple[EndpointRecord, ...],
    family: str,
    role: str,
) -> tuple[EndpointRecord, ...]:
    return tuple(
        item
        for item in catalog
        if item.key.model_family == family and item.connectome_role == role
    )


def _endpoint_index(catalog: tuple[EndpointRecord, ...]) -> dict[str, EndpointRecord]:
    output = {item.endpoint_id: item for item in catalog}
    if len(output) != len(catalog):
        raise PlanningError("endpoint catalog contains duplicate endpoint IDs")
    return output


def _formal_by_scale(
    catalog: tuple[EndpointRecord, ...],
    family: str,
) -> dict[str, EndpointRecord]:
    output: dict[str, EndpointRecord] = {}
    for endpoint in _records_by_role(catalog, family, "formal"):
        if endpoint.key.scale_id in output:
            raise PlanningError(f"multiple formal endpoints for {family}/{endpoint.key.scale_id}")
        output[endpoint.key.scale_id] = endpoint
    return output


def compile_execution_plan(
    config: ResolvedWorkflow,
    catalog: tuple[EndpointRecord, ...],
) -> ExecutionPlan:
    """Compile all static tasks and runtime gates through the requested cutoff."""
    if not isinstance(config, ResolvedWorkflow):
        raise PlanningError("config must be a ResolvedWorkflow")
    catalog = tuple(catalog)
    endpoint_index = _endpoint_index(catalog)
    factory = _TaskFactory(
        config.scientific_configuration_hash,
        config.workflow.execution.through,
    )

    available = tuple(item for item in catalog if item.status == CatalogStatus.DATA_AVAILABLE)
    reference_voxel = tuple(item for item in available if item.key.model_family == "reference_voxel")
    reference_fiber_formal = _records_by_role(available, "reference_fiber", "formal")
    reference_fiber_sensitive = _records_by_role(available, "reference_fiber", "sensitive")
    addon_voxel = tuple(item for item in available if item.key.model_family == "addon_voxel")
    addon_fiber_formal = _records_by_role(available, "addon_fiber", "formal")
    addon_fiber_sensitive = _records_by_role(available, "addon_fiber", "sensitive")

    for endpoint in reference_voxel:
        _plan_reference_voxel(factory, endpoint)
    for endpoint in reference_fiber_formal:
        _plan_reference_fiber_formal(factory, endpoint)

    formal_reference_by_scale = _formal_by_scale(catalog, "reference_fiber")
    for endpoint in reference_fiber_sensitive:
        try:
            formal_endpoint = formal_reference_by_scale[endpoint.key.scale_id]
        except KeyError as exc:
            raise PlanningError(
                f"missing formal reference-fiber endpoint for {endpoint.key.scale_id!r}"
            ) from exc
        if formal_endpoint.status != CatalogStatus.DATA_AVAILABLE:
            continue
        _plan_reference_fiber_sensitive(factory, endpoint, formal_endpoint)

    for endpoint in addon_voxel:
        reference_id = endpoint.matched_reference_endpoint_id
        if reference_id is None or reference_id not in endpoint_index:
            raise PlanningError(f"missing reference endpoint for {endpoint.endpoint_id}")
        reference_endpoint = endpoint_index[reference_id]
        if reference_endpoint.status != CatalogStatus.DATA_AVAILABLE:
            continue
        _plan_addon_voxel(factory, endpoint, reference_endpoint)

    for endpoint in addon_fiber_formal:
        reference_id = endpoint.matched_reference_endpoint_id
        if reference_id is None or reference_id not in endpoint_index:
            raise PlanningError(f"missing reference endpoint for {endpoint.endpoint_id}")
        reference_endpoint = endpoint_index[reference_id]
        if reference_endpoint.status != CatalogStatus.DATA_AVAILABLE:
            continue
        _plan_addon_fiber_formal(factory, endpoint, reference_endpoint)

    formal_addon_by_scale = _formal_by_scale(catalog, "addon_fiber")
    for endpoint in addon_fiber_sensitive:
        reference_id = endpoint.matched_reference_endpoint_id
        if reference_id is None or reference_id not in endpoint_index:
            raise PlanningError(f"missing reference endpoint for {endpoint.endpoint_id}")
        reference_endpoint = endpoint_index[reference_id]
        try:
            formal_endpoint = formal_addon_by_scale[endpoint.key.scale_id]
        except KeyError:
            continue
        if formal_endpoint.status != CatalogStatus.DATA_AVAILABLE:
            continue
        if reference_endpoint.status != CatalogStatus.DATA_AVAILABLE:
            continue
        _plan_addon_fiber_sensitive(factory, endpoint, reference_endpoint, formal_endpoint)

    return ExecutionPlan(
        configuration_hash=config.configuration_hash,
        scientific_configuration_hash=config.scientific_configuration_hash,
        through=config.workflow.execution.through,
        tasks=tuple(factory.tasks),
    )
