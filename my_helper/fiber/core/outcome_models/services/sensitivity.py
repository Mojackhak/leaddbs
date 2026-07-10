"""Final-linked sensitivity request contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..records import ArtifactRef, DeltaHFBundle, FinalArtifactRecord, RecordError
from ..run_store import sha256_file


_ULF_SENSITIVITY_KEYS = (
    ("ulf_nonfinal_branch", "nonfinal_branch"),
    ("ulf_gain", "gain"),
    ("ulf_total_exposure", "total_exposure"),
    ("ulf_support", "support"),
    ("ulf_collinearity", "collinearity"),
)


@dataclass(frozen=True)
class SensitivityRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    delta_hf: DeltaHFBundle | None
    output_root: Path
    selected_tau_multipliers: tuple[float, float]
    jitter_resamples: int
    seed: int
    enabled_ulf_analyses: tuple[str, ...]
    component_exposures: tuple[ArtifactRef, ...]
    jitter_input_manifest: ArtifactRef | None
    matched_hf_final: FinalArtifactRecord | None
    y_base: ArtifactRef | None
    hf_overlap_tau: float | None
    rebuild_geometry: bool
    rebuild_delta_hf: bool
    rebuild_support_qc: bool
    rebuild_nuisance: bool
    jitter_fwhm_mm: float
    oss_model: str
    oss_activation_threshold: float

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        *,
        delta_hf: DeltaHFBundle | None,
        component_exposures: tuple[ArtifactRef, ...] = (),
        jitter_input_manifest: ArtifactRef | None = None,
        matched_hf_final: FinalArtifactRecord | None = None,
        y_base: ArtifactRef | None = None,
        hf_overlap_tau: float | None = None,
    ) -> "SensitivityRequest":
        if context.config is None:
            raise RecordError("sensitivity service requires resolved workflow context")
        operation = task.key.execution_stage
        plain_burden_control = (
            operation == "plain_burden_controls"
            and task.endpoint.model_family == "ulf_fiber"
            and task.workflow_phase == "observed"
        )
        if task.workflow_phase != "sensitivity" and not plain_burden_control:
            raise RecordError("sensitivity request requires a sensitivity-phase task")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("sensitivity final artifact belongs to another endpoint")
        adjusted = final.final_branch == "delta_hf_adjusted"
        if adjusted:
            if delta_hf is None or not delta_hf.valid:
                raise RecordError("adjusted sensitivity requires a valid DeltaHF bundle")
            if final.nuisance.delta_hf_record_hash != delta_hf.record_hash:
                raise RecordError("sensitivity DeltaHF bundle does not match the final nuisance plan")
        elif delta_hf is not None and final.nuisance.delta_hf_record_hash is not None:
            raise RecordError("no-delta sensitivity cannot reference DeltaHF nuisance")

        is_jitter = operation == "spatial_jitter"
        is_ulf = task.endpoint.model_family in {"ulf_voxel", "ulf_fiber"}
        multipliers = tuple(float(value) for value in context.config.model.sensitivity["selected_tau_multipliers"])
        if len(multipliers) != 2:
            raise RecordError("selected tau sensitivity requires exactly two multipliers")
        exposures = tuple(component_exposures)
        expected_subjects = len(final.subject_order)
        expected_shape = (expected_subjects, final.feature_axis.count)
        kinds = {artifact.kind for artifact in exposures}
        for artifact in exposures:
            if artifact.shape != expected_shape:
                raise RecordError(
                    "component exposure artifact must match final subject and feature order"
                )
        needs_ulf_components = is_ulf and operation in {
            "plain_burden_controls",
            "cheap_observed_sensitivity",
            "selected_source_neighborhood",
            "additional_sensitivities",
            "spatial_jitter",
        }
        if needs_ulf_components:
            if "ulf_component_exposure" not in kinds:
                raise RecordError(
                    f"{operation} requires a raw ULF component exposure artifact"
                )
            if hf_overlap_tau is None:
                raise RecordError(f"{operation} requires an explicit HF-overlap tau")
            if hf_overlap_tau != float("inf") and "hf_component_exposure" not in kinds:
                raise RecordError(
                    f"finite HF-overlap {operation} requires a raw HF component exposure artifact"
                )
        if is_jitter:
            if not exposures:
                raise RecordError("spatial jitter requires explicit component exposure artifacts")
            if jitter_input_manifest is None:
                raise RecordError("spatial jitter requires a hashed jitter input manifest")
            if is_ulf:
                if y_base is None or y_base.shape != (expected_subjects,):
                    raise RecordError("ULF jitter requires a branch-specific Y_base artifact")
                if adjusted and matched_hf_final is None:
                    raise RecordError("adjusted ULF jitter requires the matched HF final record")
        sensitivity_settings = context.config.model.sensitivity
        enabled_ulf = tuple(
            label for key, label in _ULF_SENSITIVITY_KEYS if bool(sensitivity_settings[key])
        )
        if (
            is_ulf
            and operation in {"cheap_observed_sensitivity", "additional_sensitivities"}
            and "collinearity" in enabled_ulf
            and (y_base is None or y_base.shape != (expected_subjects,))
        ):
            raise RecordError(
                f"{operation} collinearity sensitivity requires a branch-specific Y_base artifact"
            )
        formal_settings = context.config.model.formal
        return cls(
            task=task,
            final=final,
            delta_hf=delta_hf,
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            selected_tau_multipliers=(multipliers[0], multipliers[1]),
            jitter_resamples=int(formal_settings["jitter_resamples"]),
            seed=int(formal_settings["seed"]),
            enabled_ulf_analyses=enabled_ulf,
            component_exposures=exposures,
            jitter_input_manifest=jitter_input_manifest,
            matched_hf_final=matched_hf_final,
            y_base=y_base,
            hf_overlap_tau=(float(hf_overlap_tau) if hf_overlap_tau is not None else None),
            rebuild_geometry=is_jitter,
            rebuild_delta_hf=is_jitter and adjusted,
            rebuild_support_qc=is_jitter and adjusted,
            rebuild_nuisance=is_jitter,
            jitter_fwhm_mm=2.0,
            oss_model=str(context.config.model.oss["model"]),
            oss_activation_threshold=float(context.config.model.oss["deterministic_activation_threshold"]),
        )


@dataclass(frozen=True)
class SensitivityRuntimeInputs:
    """Immutable runtime artifacts needed beyond the selected final record."""

    delta_hf: DeltaHFBundle | None = None
    component_exposures: tuple[ArtifactRef, ...] = ()
    jitter_input_manifest: ArtifactRef | None = None
    matched_hf_final: FinalArtifactRecord | None = None
    y_base: ArtifactRef | None = None
    hf_overlap_tau: float | None = None


@dataclass(frozen=True)
class SensitivityServiceOutput:
    artifacts: tuple[TaskArtifact, ...]
    detail: str = "configured_sensitivity_completed"


SensitivityRunner = Callable[[SensitivityRequest], SensitivityServiceOutput]
SensitivityFinalLoader = Callable[[TaskSpec, RunContext], FinalArtifactRecord]
SensitivityInputsLoader = Callable[
    [TaskSpec, RunContext, FinalArtifactRecord], SensitivityRuntimeInputs
]
SensitivityRequestFactory = Callable[..., SensitivityRequest]


class SensitivityService:
    """Execute one sensitivity task bound to exactly one immutable final model."""

    def __init__(
        self,
        *,
        runner: SensitivityRunner,
        final_loader: SensitivityFinalLoader,
        inputs_loader: SensitivityInputsLoader,
        request_factory: SensitivityRequestFactory = SensitivityRequest.from_context,
    ) -> None:
        self.runner = runner
        self.final_loader = final_loader
        self.inputs_loader = inputs_loader
        self.request_factory = request_factory

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        try:
            final = self.final_loader(task, context)
            inputs = self.inputs_loader(task, context, final)
            request = self.request_factory(
                task=task,
                context=context,
                final=final,
                delta_hf=inputs.delta_hf,
                component_exposures=inputs.component_exposures,
                jitter_input_manifest=inputs.jitter_input_manifest,
                matched_hf_final=inputs.matched_hf_final,
                y_base=inputs.y_base,
                hf_overlap_tau=inputs.hf_overlap_tau,
            )
            output = self.runner(request)
            artifacts = list(output.artifacts)
            if inputs.jitter_input_manifest is not None:
                manifest_path = (
                    context.store.run_root / inputs.jitter_input_manifest.relative_path
                ).resolve()
                if (
                    not manifest_path.is_relative_to(context.store.run_root)
                    or not manifest_path.is_file()
                    or sha256_file(manifest_path) != inputs.jitter_input_manifest.sha256
                ):
                    raise RecordError("jitter input manifest provenance is invalid")
                if not any(item.kind == "jitter_input_manifest" for item in artifacts):
                    artifacts.append(TaskArtifact("jitter_input_manifest", manifest_path))
        except (OSError, RecordError, RuntimeError, ValueError) as exc:
            return TaskResult(
                TaskStatus.EXECUTION_FAILURE,
                f"sensitivity_service_failure:{exc}",
            )
        completion_fact = (
            "control_complete"
            if task.key.execution_stage == "plain_burden_controls"
            else "sensitivity_complete"
        )
        return TaskResult(
            TaskStatus.COMPLETED,
            output.detail,
            facts={
                completion_fact: True,
                "final_model_id": final.final_model_id,
                "final_artifact_record_hash": final.record_hash,
            },
            artifacts=tuple(artifacts),
        )


__all__ = [
    "SensitivityRequest",
    "SensitivityRuntimeInputs",
    "SensitivityService",
    "SensitivityServiceOutput",
]
