"""Immutable HF-derived requests for ULF direct-voxel and fiber branches."""

from __future__ import annotations

import math
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..catalog import EndpointRecord
from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..identity import FinalModelKey
from ..planner import TaskSpec
from ..records import (
    DeltaHFBundle,
    FinalArtifactRecord,
    HFSourceRecord,
    NuisancePlan,
    RecordError,
    ULFBranchRecord,
)
from ..state import BranchResult, SourceResult, realize_ulf_final
from .record_io import artifact_ref_for_task, normative_fiber_final_provenance
from .observed import normative_fiber_score_settings


def validate_hf_source_for_ulf(
    source: HFSourceRecord,
    *,
    expected_subject_order: tuple[str, ...],
    expected_feature_sha: str,
) -> None:
    """Require exact subject and feature identity before reusing an accepted HF source."""
    if not source.accepted:
        return
    if source.subject_order != tuple(expected_subject_order):
        raise RecordError("matched HF source subject order does not match the ULF endpoint")
    if source.feature_axis is None or source.feature_axis.sha256 != expected_feature_sha:
        raise RecordError("matched HF source feature axis does not match the ULF model axis")


@dataclass(frozen=True)
class ULFObservedRequest:
    endpoint: EndpointRecord
    branch: str
    hf_source: HFSourceRecord
    delta_hf: DeltaHFBundle | None
    nuisance: NuisancePlan
    model_root: Path
    output_root: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    hf_overlap_tau: float
    hf_overlap_coverage: int | None
    score: Mapping[str, float | int] | None = None

    @classmethod
    def from_context(
        cls,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
        *,
        hf_source: HFSourceRecord,
        delta_hf: DeltaHFBundle | None,
    ) -> "ULFObservedRequest":
        if context.config is None:
            raise RecordError("configured ULF service requires resolved workflow context")
        branch = task.key.branch
        if branch not in {"no_delta_hf", "delta_hf_adjusted"}:
            raise RecordError(f"ULF branch request has unsupported branch {branch!r}")

        if branch == "delta_hf_adjusted":
            if not hf_source.accepted:
                raise RecordError("delta_hf_adjusted cannot run without an accepted matched HF source")
            if delta_hf is None or not delta_hf.valid:
                raise RecordError("delta_hf_adjusted requires a valid adequate-or-limited DeltaHF bundle")
            if (
                float(delta_hf.selected_hf_tau) != float(hf_source.selected_tau)
                or int(delta_hf.selected_hf_coverage) != int(hf_source.selected_coverage)
            ):
                raise RecordError("DeltaHF tau/Coverage must equal the immutable matched HF selected source")
        nuisance = NuisancePlan.for_branch(branch, delta_hf)

        if endpoint.key.model_family == "ulf_voxel":
            settings = context.config.model.direct_voxel
        elif endpoint.key.model_family == "ulf_fiber":
            settings = context.config.model.normative_fiber
        else:
            raise RecordError(f"unsupported ULF model family {endpoint.key.model_family!r}")

        model_root = context.store.run_root / "models" / endpoint.endpoint_model_id
        return cls(
            endpoint=endpoint,
            branch=branch,
            hf_source=hf_source,
            delta_hf=delta_hf,
            nuisance=nuisance,
            model_root=model_root,
            output_root=model_root / "tasks" / task.task_id,
            tau_grid=tuple(float(value) for value in settings["tau_grid_v_per_m"]),
            coverage_grid=tuple(int(value) for value in settings["coverage_grid"]),
            primary_tau=float(settings["pre_specified_tau_v_per_m"]),
            primary_coverage=int(settings["pre_specified_coverage"]),
            hf_overlap_tau=(float(hf_source.selected_tau) if hf_source.accepted else math.inf),
            hf_overlap_coverage=(int(hf_source.selected_coverage) if hf_source.accepted else None),
            score=(
                normative_fiber_score_settings(settings["score"])
                if endpoint.key.model_family == "ulf_fiber"
                else None
            ),
        )


@dataclass(frozen=True)
class DeltaBuilderOutput:
    bundle: DeltaHFBundle
    artifacts: tuple[TaskArtifact, ...] = ()


ULFRunner = Callable[[ULFObservedRequest], Any]
DeltaBuilder = Callable[[EndpointRecord, HFSourceRecord, TaskSpec, RunContext], DeltaBuilderOutput]


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _source_result(source: HFSourceRecord | ULFBranchRecord) -> SourceResult:
    return SourceResult(
        input_status=source.input_status,
        source_status=source.source_status,
        prediction_status=source.prediction_status,
        selected_tau=source.selected_tau,
        selected_coverage=source.selected_coverage,
        adjacent_support=(source.adjacent_support if isinstance(source, ULFBranchRecord) else None),
    )


def _matched_hf_family(task: TaskSpec) -> str:
    return "hf_voxel" if task.endpoint.model_family == "ulf_voxel" else "hf_fiber"


def _matched_hf_execution_record(task: TaskSpec, context: RunContext):
    matches = [
        record
        for record in context.results.values()
        if record.task.endpoint.study_id == task.endpoint.study_id
        and record.task.endpoint.scale_id == task.endpoint.scale_id
        and record.task.endpoint.model_family == _matched_hf_family(task)
        and record.task.endpoint.connectome == task.endpoint.connectome
        and record.task.key.execution_stage == "observed_source_resolver"
    ]
    if len(matches) != 1:
        raise RecordError(f"expected one matched HF resolver result; found {len(matches)}")
    return matches[0]


def matched_hf_source(task: TaskSpec, context: RunContext) -> HFSourceRecord:
    """Load the exact same-scale/connectome HF source or represent its failure."""
    record = _matched_hf_execution_record(task, context)
    payload = record.result.facts.get("hf_source_record")
    if isinstance(payload, dict):
        return HFSourceRecord.from_dict(dict(payload))
    return HFSourceRecord.create(
        resolver_task_id=record.task.task_id,
        endpoint_model_id=record.task.endpoint.identifier,
        input_status=record.result.status.value,
        source_status="absent_hf_resolver_failure",
        prediction_status="not_applicable",
        threshold_source="none",
        selected_tau=None,
        selected_coverage=None,
        subject_order=(),
        feature_axis=None,
        artifacts=(),
    )


def _delta_bundle(task: TaskSpec, context: RunContext) -> DeltaHFBundle | None:
    facts = context.dependency_facts(task, "preprocessing_sidecars")
    payload = facts.get("delta_hf_bundle")
    return DeltaHFBundle.from_dict(dict(payload)) if isinstance(payload, dict) else None


def _branch_record_from_execution(record: Any) -> ULFBranchRecord | None:
    payload = record.result.facts.get("ulf_branch_record")
    return ULFBranchRecord.from_dict(dict(payload)) if isinstance(payload, dict) else None


class ULFObservedService:
    """Execute ULF lock, Delta readiness, branch resolvers, and unique final realization."""

    def __init__(
        self,
        *,
        direct_runner: ULFRunner | None = None,
        fiber_runner: ULFRunner | None = None,
        delta_builder: DeltaBuilder | None = None,
    ) -> None:
        self.direct_runner = direct_runner
        self.fiber_runner = fiber_runner
        self.delta_builder = delta_builder

    def _input_hf_lock(
        self,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> TaskResult:
        source = matched_hf_source(task, context)
        path = (
            context.store.run_root
            / "models"
            / endpoint.endpoint_model_id
            / "tasks"
            / task.task_id
            / "readiness_status.json"
        )
        _write_json_atomic(
            path,
            {
                "status": "ready",
                "endpoint_model_id": endpoint.endpoint_model_id,
                "matched_hf_source": source.as_dict(),
            },
        )
        return TaskResult(
            TaskStatus.COMPLETED,
            "matched_hf_source_locked",
            facts={"hf_source_record": source.as_dict(), "hf_source_accepted": source.accepted},
            artifacts=(TaskArtifact("readiness_status", path),),
        )

    def _sidecars(
        self,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> TaskResult:
        source = matched_hf_source(task, context)
        if source.accepted and self.delta_builder is not None:
            built = self.delta_builder(endpoint, source, task, context)
        elif source.accepted:
            built = DeltaBuilderOutput(
                DeltaHFBundle(
                    input_status="implementation_unavailable",
                    support_status="invalid_delta_builder_unavailable",
                    selected_hf_tau=source.selected_tau,
                    selected_hf_coverage=source.selected_coverage,
                    full_scores=None,
                    fold_scores=None,
                    support_rows=None,
                    failure_stage="delta_builder",
                    failure_detail="configured DeltaHF builder is not registered",
                )
            )
        else:
            built = DeltaBuilderOutput(
                DeltaHFBundle(
                    input_status="not_applicable",
                    support_status="not_applicable_no_stable_hf_source",
                    selected_hf_tau=None,
                    selected_hf_coverage=None,
                    full_scores=None,
                    fold_scores=None,
                    support_rows=None,
                    failure_stage="hf_source",
                    failure_detail="matched HF source is unavailable",
                )
            )
        task_root = (
            context.store.run_root
            / "models"
            / endpoint.endpoint_model_id
            / "tasks"
            / task.task_id
        )
        bundle_path = task_root / "delta_hf_bundle.json"
        sidecar_index = task_root / "sidecar_index.json"
        qc_path = task_root / "qc.json"
        _write_json_atomic(bundle_path, built.bundle.as_dict())
        _write_json_atomic(
            sidecar_index,
            {
                "endpoint_model_id": endpoint.endpoint_model_id,
                "hf_source_record_hash": source.record_hash,
                "delta_hf_bundle": str(bundle_path),
                "artifacts": [
                    {"kind": artifact.kind, "path": str(artifact.path)} for artifact in built.artifacts
                ],
            },
        )
        _write_json_atomic(
            qc_path,
            {
                "delta_hfscore_inputs_valid": built.bundle.valid,
                "input_status": built.bundle.input_status,
                "support_status": built.bundle.support_status,
                "failure_stage": built.bundle.failure_stage,
                "failure_detail": built.bundle.failure_detail,
            },
        )
        return TaskResult(
            TaskStatus.COMPLETED,
            "ulf_preprocessing_sidecars_completed",
            facts={
                "delta_hfscore_inputs_valid": built.bundle.valid,
                "delta_hf_bundle": built.bundle.as_dict(),
                "hf_source_record_hash": source.record_hash,
            },
            artifacts=(
                TaskArtifact("sidecar_index", sidecar_index),
                TaskArtifact("qc", qc_path),
                TaskArtifact("delta_hf_bundle", bundle_path),
                *built.artifacts,
            ),
        )

    def _branch(
        self,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> TaskResult:
        source = matched_hf_source(task, context)
        bundle = _delta_bundle(task, context)
        request = ULFObservedRequest.from_context(
            endpoint,
            task,
            context,
            hf_source=source,
            delta_hf=(bundle if task.key.branch == "delta_hf_adjusted" else None),
        )
        runner = self.direct_runner if task.endpoint.model_family == "ulf_voxel" else self.fiber_runner
        if runner is None:
            return TaskResult(TaskStatus.EXECUTION_FAILURE, "ulf_branch_runner_not_registered")
        output = runner(request)
        refs = tuple(artifact_ref_for_task(artifact, task=task, context=context) for artifact in output.artifacts)
        branch = ULFBranchRecord.create(
            resolver_task_id=task.task_id,
            endpoint_model_id=endpoint.endpoint_model_id,
            branch=task.key.branch,
            input_status="valid",
            source_status=str(output.source_status),
            prediction_status=str(output.prediction_status),
            threshold_source=str(output.threshold_source),
            selected_tau=output.selected_tau,
            selected_coverage=output.selected_coverage,
            adjacent_support=output.adjacent_support,
            subject_order=tuple(output.subject_order),
            feature_axis=output.feature_axis,
            nuisance=request.nuisance,
            artifacts=refs,
        )
        path = request.output_root / "ulf_branch_record.json"
        _write_json_atomic(path, branch.as_dict())
        return TaskResult(
            TaskStatus.COMPLETED,
            "ulf_branch_resolver_completed",
            facts={
                "source_accepted": branch.accepted,
                "source_status": branch.source_status,
                "prediction_status": branch.prediction_status,
                "selected_tau": branch.selected_tau,
                "selected_coverage": branch.selected_coverage,
                "ulf_branch_record": branch.as_dict(),
                "ulf_branch_record_hash": branch.record_hash,
            },
            artifacts=(*output.artifacts, TaskArtifact("ulf_branch_record", path)),
        )

    def _final(
        self,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> TaskResult:
        hf = matched_hf_source(task, context)
        execution_by_branch = {
            context.results[dependency.task_id].task.key.branch: context.results[dependency.task_id]
            for dependency in task.dependencies
            if dependency.task_id in context.results
        }
        state_inputs: dict[str, BranchResult] = {}
        records: dict[str, ULFBranchRecord] = {}
        for branch_name in ("no_delta_hf", "delta_hf_adjusted"):
            execution = execution_by_branch.get(branch_name)
            record = _branch_record_from_execution(execution) if execution is not None else None
            if record is not None:
                records[branch_name] = record
                state_inputs[branch_name] = BranchResult(branch_name, "valid", _source_result(record))
            else:
                input_status = (
                    execution.result.detail
                    if execution is not None and execution.result.detail
                    else "missing_branch_result"
                )
                state_inputs[branch_name] = BranchResult(branch_name, input_status, None)
        decision = realize_ulf_final(_source_result(hf), state_inputs)
        task_root = (
            context.store.run_root
            / "models"
            / endpoint.endpoint_model_id
            / "tasks"
            / task.task_id
        )
        status_path = task_root / "final_model_status.json"
        status_payload: dict[str, object] = {
            "endpoint_model_id": endpoint.endpoint_model_id,
            "intended_primary_branch": decision.intended_primary_branch,
            "final_branch": decision.final_branch,
            "final_role": decision.final_role,
            "final_status": decision.final_status,
            "failure_reasons": list(decision.failure_reasons),
        }
        if decision.final_branch is None:
            _write_json_atomic(status_path, status_payload)
            return TaskResult(
                TaskStatus.NO_FINAL_MODEL,
                decision.final_status,
                facts={"final_model_realized": False, **status_payload},
                artifacts=(TaskArtifact("final_model_status", status_path),),
            )

        branch = records[decision.final_branch]
        refs = {artifact.kind: artifact for artifact in branch.artifacts}
        required = {"selected_manifest", "exposure_matrix", "selected_scores"}
        missing = sorted(required - set(refs))
        if missing:
            return TaskResult(
                TaskStatus.EXECUTION_FAILURE,
                "realized_branch_missing_final_artifacts:" + ",".join(missing),
            )
        if branch.feature_axis is None or branch.selected_tau is None or branch.selected_coverage is None:
            return TaskResult(TaskStatus.EXECUTION_FAILURE, "realized_branch_missing_identity")
        estimator = (
            str(context.config.model.direct_voxel["estimator"])
            if task.endpoint.model_family == "ulf_voxel"
            else f"{context.config.model.normative_fiber['exposure']}_partial_spearman"
        )
        full_weights = None
        valid_feature_axis = None
        if estimator == "peak_efield_partial_spearman":
            full_weights, valid_feature_axis = normative_fiber_final_provenance(
                refs_by_kind=refs,
                parent_axis=branch.feature_axis,
                selected_tau=branch.selected_tau,
                selected_coverage=branch.selected_coverage,
                context=context,
            )
        key = FinalModelKey(
            endpoint_model_id=endpoint.endpoint_model_id,
            final_branch=decision.final_branch,
            selected_tau=branch.selected_tau,
            selected_coverage=branch.selected_coverage,
            estimator=estimator,
        )
        final = FinalArtifactRecord.create(
            final_model_id=key.identifier,
            endpoint_model_id=endpoint.endpoint_model_id,
            final_branch=decision.final_branch,
            final_role=decision.final_role,
            selected_tau=branch.selected_tau,
            selected_coverage=branch.selected_coverage,
            estimator=estimator,
            scale_direction=endpoint.direction,
            subject_order=branch.subject_order,
            nuisance=branch.nuisance,
            manifest=refs["selected_manifest"],
            exposure=refs["exposure_matrix"],
            scores=refs["selected_scores"],
            feature_axis=branch.feature_axis,
            full_weights=full_weights,
            valid_feature_axis=valid_feature_axis,
            spatial_reference=refs.get("coefficient_nifti"),
        )
        final_path = task_root / "final_model_record.json"
        _write_json_atomic(final_path, final.as_dict())
        status_payload.update(
            {
                "final_model_id": final.final_model_id,
                "final_record_hash": final.record_hash,
            }
        )
        _write_json_atomic(status_path, status_payload)
        return TaskResult(
            TaskStatus.COMPLETED,
            "ulf_final_model_realized",
            facts={
                "final_model_realized": True,
                "final_model_id": final.final_model_id,
                "final_record_hash": final.record_hash,
                "final_model_record": final.as_dict(),
                **status_payload,
            },
            artifacts=(
                TaskArtifact("final_model_status", status_path),
                TaskArtifact("final_model_record", final_path),
            ),
        )

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        endpoint = context.catalog_record(task.endpoint.identifier)
        operation = task.key.execution_stage
        if operation == "input_hf_lock":
            return self._input_hf_lock(endpoint, task, context)
        if operation == "preprocessing_sidecars":
            return self._sidecars(endpoint, task, context)
        if operation == "observed_branch_resolver":
            return self._branch(endpoint, task, context)
        if operation == "final_model_realization":
            return self._final(endpoint, task, context)
        return TaskResult(TaskStatus.EXECUTION_FAILURE, f"unsupported_ulf_observed_operation:{operation}")


__all__ = [
    "DeltaBuilderOutput",
    "ULFObservedRequest",
    "ULFObservedService",
    "matched_hf_source",
    "validate_hf_source_for_ulf",
]
