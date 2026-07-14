"""Explicit configured requests for HF direct-voxel and normative-fiber runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable, Mapping

from ..catalog import CatalogStatus, EndpointRecord
from ..config import ConnectomeSpec
from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..records import FeatureAxisRef
from ..state import ACCEPTED_SOURCE_STATUSES
from .record_io import persist_hf_resolver_output


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
    score: Mapping[str, float | int]
    cheap_observed_sensitivity: Mapping[str, float | int]
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
            score=normative_fiber_score_settings(settings["score"]),
            cheap_observed_sensitivity={
                str(key): (int(value) if key in {"coverage", "sweet_top_count", "sour_top_count"} else float(value))
                for key, value in settings["cheap_observed_sensitivity"].items()
            },
            force=bool(context.config.workflow.execution.force),
        )


def normative_fiber_score_settings(
    values: Mapping[str, object],
) -> dict[str, float | int]:
    """Preserve the public float fractions and integer minimum counts."""
    integer_fields = {
        "sweet_selected_min_count",
        "sour_selected_min_count",
        "weighted_peak_min_count",
    }
    return {
        str(key): int(value) if key in integer_fields else float(value)
        for key, value in values.items()
    }


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
    input_status: str = "valid"

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
            input_status="not_applicable",
        )

    def task_result(self) -> TaskResult:
        accepted = (
            self.input_status == "valid"
            and self.source_status in ACCEPTED_SOURCE_STATUSES
        )
        return TaskResult(
            status=TaskStatus.COMPLETED,
            detail="observed_service_completed",
            facts={
                "source_accepted": accepted,
                "input_status": self.input_status,
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
DirectArtifactRunner = Callable[[HFDirectVoxelRequest], tuple[TaskArtifact, ...]]
FiberArtifactRunner = Callable[[HFNormativeFiberRequest], tuple[TaskArtifact, ...]]


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _readiness_result(
    endpoint: EndpointRecord,
    task: TaskSpec,
    context: RunContext,
) -> TaskResult:
    if task.endpoint.model_family == "hf_voxel":
        request = HFDirectVoxelRequest.from_context(endpoint, task, context)
        required = {
            "clinical_table": request.clinical_table,
            "stimulation_table": request.stimulation_table,
            "derivatives_root": request.derivatives_root,
            "brainmask": request.brainmask,
            "asset_root": request.asset_root,
        }
        output_root = request.output_root
    else:
        request = HFNormativeFiberRequest.from_context(endpoint, task, context)
        required = {
            "clinical_table": request.clinical_table,
            "stimulation_table": request.stimulation_table,
            "derivatives_root": request.derivatives_root,
            "asset_root": request.asset_root,
            "connectome": request.connectome.path,
        }
        output_root = request.output_root
    missing = sorted(name for name, path in required.items() if not Path(path).exists())
    if missing:
        return TaskResult(TaskStatus.INPUT_FAILURE, "missing_required_inputs:" + ",".join(missing))
    status_path = output_root / "readiness_status.json"
    _write_json_atomic(
        status_path,
        {
            "endpoint_model_id": endpoint.endpoint_model_id,
            "model_family": task.endpoint.model_family,
            "status": "ready",
            "inputs": {name: str(path) for name, path in sorted(required.items())},
        },
    )
    return TaskResult(
        TaskStatus.COMPLETED,
        "configured_inputs_ready",
        artifacts=(TaskArtifact("readiness_status", status_path),),
    )


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
        direct_sidecar_runner: DirectArtifactRunner | None = None,
        fiber_primary_runner: FiberRunner | None = None,
        fiber_resolver_runner: FiberRunner | None = None,
        fiber_sidecar_runner: FiberArtifactRunner | None = None,
        fiber_control_runner: FiberArtifactRunner | None = None,
        fiber_sensitivity_runner: FiberArtifactRunner | None = None,
    ) -> None:
        self.direct_runner = direct_runner
        self.direct_sidecar_runner = direct_sidecar_runner
        self.fiber_primary_runner = fiber_primary_runner
        self.fiber_resolver_runner = fiber_resolver_runner
        self.fiber_sidecar_runner = fiber_sidecar_runner
        self.fiber_control_runner = fiber_control_runner
        self.fiber_sensitivity_runner = fiber_sensitivity_runner

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        endpoint = context.catalog_record(task.endpoint.identifier)
        if endpoint.status != CatalogStatus.DATA_AVAILABLE:
            return TaskResult(TaskStatus.INPUT_FAILURE, ";".join(endpoint.failure_reasons))

        operation = task.key.execution_stage
        if operation in {"input_readiness", "version_input_freeze"}:
            return _readiness_result(endpoint, task, context)

        if task.endpoint.model_family == "hf_voxel" and operation == "preprocessing_sidecars":
            if self.direct_sidecar_runner is None:
                return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_direct_sidecar_runner_not_registered")
            artifacts = self.direct_sidecar_runner(HFDirectVoxelRequest.from_context(endpoint, task, context))
            return TaskResult(
                TaskStatus.COMPLETED,
                "hf_direct_sidecars_completed",
                artifacts=artifacts,
            )

        if task.endpoint.model_family == "hf_voxel" and operation == "observed_source_resolver":
            if self.direct_runner is None:
                return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_direct_runner_not_registered")
            output = self.direct_runner(HFDirectVoxelRequest.from_context(endpoint, task, context))
            return persist_hf_resolver_output(output, endpoint, task, context)

        if task.endpoint.model_family == "hf_fiber":
            request = HFNormativeFiberRequest.from_context(endpoint, task, context)
            if operation == "sidecar_equivalence":
                if self.fiber_sidecar_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_sidecar_runner_not_registered")
                return TaskResult(
                    TaskStatus.COMPLETED,
                    "hf_fiber_sidecars_completed",
                    artifacts=self.fiber_sidecar_runner(request),
                )
            if operation == "observed_primary":
                if self.fiber_primary_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_primary_runner_not_registered")
                return self.fiber_primary_runner(request).task_result()
            if operation == "plain_connected_control":
                if self.fiber_control_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_control_runner_not_registered")
                return TaskResult(
                    TaskStatus.COMPLETED,
                    "hf_fiber_plain_control_completed",
                    artifacts=self.fiber_control_runner(request),
                )
            if operation == "cheap_observed_sensitivity":
                if self.fiber_sensitivity_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_sensitivity_runner_not_registered")
                return TaskResult(
                    TaskStatus.COMPLETED,
                    "hf_fiber_cheap_sensitivity_completed",
                    artifacts=self.fiber_sensitivity_runner(request),
                )
            if operation == "observed_source_resolver":
                if self.fiber_resolver_runner is None:
                    return TaskResult(TaskStatus.EXECUTION_FAILURE, "hf_fiber_resolver_runner_not_registered")
                output = self.fiber_resolver_runner(request)
                return persist_hf_resolver_output(output, endpoint, task, context)

        return TaskResult(TaskStatus.EXECUTION_FAILURE, f"unsupported_hf_observed_operation:{operation}")
