"""Explicit configured requests for HF direct-voxel and normative-fiber runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..catalog import CatalogStatus, EndpointRecord
from ..config import ConnectomeSpec
from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..state import ACCEPTED_SOURCE_STATUSES


@dataclass(frozen=True)
class FeatureAxisRef:
    ids_path: Path
    count: int
    sha256: str
    identity_source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "ids_path": str(self.ids_path),
            "count": int(self.count),
            "sha256": self.sha256,
            "identity_source": self.identity_source,
        }


@dataclass(frozen=True)
class HFDirectVoxelRequest:
    endpoint: EndpointRecord
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    brainmask: Path
    asset_root: Path
    model_root: Path
    output_root: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    candidate_threshold: float
    force: bool

    @classmethod
    def from_context(
        cls,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> "HFDirectVoxelRequest":
        if context.config is None:
            raise RuntimeError("configured HF direct-voxel service requires resolved workflow context")
        settings = context.config.model.direct_voxel
        model_root = context.store.run_root / "models" / endpoint.endpoint_model_id
        return cls(
            endpoint=endpoint,
            clinical_table=context.config.study.paths.clinical_table,
            stimulation_table=context.config.study.paths.stimulation_table,
            derivatives_root=context.config.study.paths.leaddbs_derivatives,
            brainmask=Path(context.config.study.space["brainmask"]),
            asset_root=context.config.study.paths.asset_root,
            model_root=model_root,
            output_root=model_root / "tasks" / task.task_id,
            tau_grid=tuple(float(value) for value in settings["tau_grid_v_per_m"]),
            coverage_grid=tuple(int(value) for value in settings["coverage_grid"]),
            primary_tau=float(settings["pre_specified_tau_v_per_m"]),
            primary_coverage=int(settings["pre_specified_coverage"]),
            candidate_threshold=float(context.config.model.direct_candidate_threshold_v_per_m),
            force=bool(context.config.workflow.execution.force),
        )


@dataclass(frozen=True)
class HFNormativeFiberRequest:
    endpoint: EndpointRecord
    connectome: ConnectomeSpec
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    asset_root: Path
    model_root: Path
    output_root: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    force: bool

    @classmethod
    def from_context(
        cls,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> "HFNormativeFiberRequest":
        if context.config is None:
            raise RuntimeError("configured HF normative-fiber service requires resolved workflow context")
        try:
            connectome = context.config.study.connectomes[endpoint.key.connectome]
        except KeyError as exc:
            raise RuntimeError(f"unknown configured connectome {endpoint.key.connectome!r}") from exc
        settings = context.config.model.normative_fiber
        model_root = context.store.run_root / "models" / endpoint.endpoint_model_id
        return cls(
            endpoint=endpoint,
            connectome=connectome,
            clinical_table=context.config.study.paths.clinical_table,
            stimulation_table=context.config.study.paths.stimulation_table,
            derivatives_root=context.config.study.paths.leaddbs_derivatives,
            asset_root=context.config.study.paths.asset_root,
            model_root=model_root,
            output_root=model_root / "tasks" / task.task_id,
            tau_grid=tuple(float(value) for value in settings["tau_grid_v_per_m"]),
            coverage_grid=tuple(int(value) for value in settings["coverage_grid"]),
            primary_tau=float(settings["pre_specified_tau_v_per_m"]),
            primary_coverage=int(settings["pre_specified_coverage"]),
            force=bool(context.config.workflow.execution.force),
        )


@dataclass(frozen=True)
class ObservedServiceOutput:
    source_status: str
    prediction_status: str
    threshold_source: str
    selected_tau: float | None
    selected_coverage: int | None
    adjacent_support: int | None
    subject_order: tuple[str, ...]
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[TaskArtifact, ...] = ()

    @classmethod
    def empty(cls) -> "ObservedServiceOutput":
        return cls(
            source_status="not_applicable",
            prediction_status="not_applicable",
            threshold_source="not_applicable",
            selected_tau=None,
            selected_coverage=None,
            adjacent_support=None,
            subject_order=(),
            feature_axis=None,
        )

    def task_result(self) -> TaskResult:
        accepted = self.source_status in ACCEPTED_SOURCE_STATUSES
        return TaskResult(
            status=TaskStatus.COMPLETED,
            detail="observed_service_completed",
            facts={
                "source_accepted": accepted,
                "source_status": self.source_status,
                "prediction_status": self.prediction_status,
                "threshold_source": self.threshold_source,
                "selected_tau": self.selected_tau,
                "selected_coverage": self.selected_coverage,
                "adjacent_support": self.adjacent_support,
                "subject_order": list(self.subject_order),
                "feature_axis": self.feature_axis.as_dict() if self.feature_axis is not None else None,
            },
            artifacts=self.artifacts,
        )


DirectRunner = Callable[[HFDirectVoxelRequest], ObservedServiceOutput]
FiberRunner = Callable[[HFNormativeFiberRequest], ObservedServiceOutput]


def direct_source_branch_name(request: HFDirectVoxelRequest, tau: float, coverage: int) -> str:
    del request
    return f"tau{float(tau):g}_cov{int(coverage)}"


def fiber_primary_branch_name(request: HFNormativeFiberRequest) -> str:
    return f"peak_efield_tau{request.primary_tau:g}_cov{request.primary_coverage}_primary"


class HFObservedService:
    """Dispatch configured HF observed tasks without consulting legacy defaults."""

    def __init__(
        self,
        *,
        direct_runner: DirectRunner | None = None,
        fiber_primary_runner: FiberRunner | None = None,
        fiber_resolver_runner: FiberRunner | None = None,
    ) -> None:
        self.direct_runner = direct_runner
        self.fiber_primary_runner = fiber_primary_runner
        self.fiber_resolver_runner = fiber_resolver_runner

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        endpoint = context.catalog_record(task.endpoint.identifier)
        if endpoint.status != CatalogStatus.DATA_AVAILABLE:
            return TaskResult(TaskStatus.INPUT_FAILURE, ";".join(endpoint.failure_reasons))

        operation = task.key.execution_stage
        if task.endpoint.model_family == "hf_voxel" and operation == "observed_source_resolver":
            if self.direct_runner is None:
                return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_direct_runner_not_registered")
            return self.direct_runner(HFDirectVoxelRequest.from_context(endpoint, task, context)).task_result()

        if task.endpoint.model_family == "hf_fiber":
            request = HFNormativeFiberRequest.from_context(endpoint, task, context)
            if operation == "observed_primary":
                if self.fiber_primary_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_primary_runner_not_registered")
                return self.fiber_primary_runner(request).task_result()
            if operation == "observed_source_resolver":
                if self.fiber_resolver_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_resolver_runner_not_registered")
                return self.fiber_resolver_runner(request).task_result()

        if operation in {
            "input_readiness",
            "version_input_freeze",
            "preprocessing_sidecars",
            "sidecar_equivalence",
            "plain_connected_control",
            "cheap_observed_sensitivity",
        }:
            return TaskResult(TaskStatus.COMPLETED, "configured_inputs_ready")
        return TaskResult(TaskStatus.EXECUTION_FAILURE, f"unsupported_hf_observed_operation:{operation}")
