"""Final-record-locked OSS/pPAM sensitivity service contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..records import ArtifactRef, FinalArtifactRecord, RecordError
from .record_io import load_final_record
from .observed import normative_fiber_score_settings


_OSS_SMOKE_PERMUTATIONS = 1000
_OSS_SMOKE_SEED = 42


class OSSSidecarsUnavailable(RecordError):
    """Raised when no complete final-linked OSS sidecar bundle is available."""


@dataclass(frozen=True)
class OSSSidecarBundle:
    """Hash-locked OSS inputs for one immutable final normative-fiber model."""

    final_model_id: str
    final_record_hash: str
    compatibility_hash: str
    activation_probabilities: ArtifactRef
    fiber_ids: ArtifactRef
    parameter_manifest: ArtifactRef
    activation_metadata: ArtifactRef

    def __post_init__(self) -> None:
        if not str(self.final_model_id).strip() or not str(self.final_record_hash).strip():
            raise RecordError("OSS sidecar final identity must be nonempty")
        if len(str(self.compatibility_hash)) != 64:
            raise RecordError("OSS sidecar compatibility hash must be a full SHA-256 digest")
        expected_kinds = {
            "activation_probabilities": "oss_activation_probabilities",
            "fiber_ids": "oss_fiber_ids",
            "parameter_manifest": "oss_parameter_manifest",
            "activation_metadata": "oss_activation_metadata",
        }
        for field, expected in expected_kinds.items():
            artifact = getattr(self, field)
            if artifact.kind != expected:
                raise RecordError(f"OSS {field} artifact kind must be {expected!r}")

    def as_dict(self) -> dict[str, object]:
        return {
            "final_model_id": self.final_model_id,
            "final_record_hash": self.final_record_hash,
            "compatibility_hash": self.compatibility_hash,
            "activation_probabilities": self.activation_probabilities.as_dict(),
            "fiber_ids": self.fiber_ids.as_dict(),
            "parameter_manifest": self.parameter_manifest.as_dict(),
            "activation_metadata": self.activation_metadata.as_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "OSSSidecarBundle":
        def artifact(name: str) -> ArtifactRef:
            payload = value.get(name)
            if not isinstance(payload, dict):
                raise RecordError(f"OSS sidecar bundle is missing {name}")
            return ArtifactRef.from_dict(dict(payload))

        return cls(
            final_model_id=str(value.get("final_model_id", "")),
            final_record_hash=str(value.get("final_record_hash", "")),
            compatibility_hash=str(value.get("compatibility_hash", "")),
            activation_probabilities=artifact("activation_probabilities"),
            fiber_ids=artifact("fiber_ids"),
            parameter_manifest=artifact("parameter_manifest"),
            activation_metadata=artifact("activation_metadata"),
        )


@dataclass(frozen=True)
class OSSRequest:
    """One final dTOR normative-fiber OSS sensitivity request."""

    task: TaskSpec
    final: FinalArtifactRecord
    sidecars: OSSSidecarBundle
    output_root: Path
    oss_model: str
    activation_model: str
    activation_threshold: float
    canonical_hemisphere: str
    hemisphere_merge_rule: str
    expected_component: str
    smoke_permutations: int
    seed: int
    score: Mapping[str, float | int]

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        *,
        sidecars: OSSSidecarBundle,
    ) -> "OSSRequest":
        if context.config is None:
            raise RecordError("OSS service requires resolved workflow context")
        if task.workflow_phase != "sensitivity" or task.key.execution_stage != "oss_sensitivity":
            raise RecordError("OSS request requires an oss_sensitivity task")
        if task.key.source_reference != "final_model_record":
            raise RecordError("OSS task must reference an immutable final-model record")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("OSS final artifact belongs to another endpoint")
        if task.endpoint.model_family not in {"hf_fiber", "ulf_fiber"}:
            raise RecordError("OSS sensitivity is defined only for normative-fiber models")
        if str(task.endpoint.connectome).lower() != "dtor":
            raise RecordError("OSS sensitivity is restricted to final dTOR branches")
        if sidecars.final_model_id != final.final_model_id:
            raise RecordError("OSS sidecar belongs to another final model")
        if sidecars.final_record_hash != final.record_hash:
            raise RecordError("OSS sidecar final-record hash mismatch")

        settings = context.config.model.oss
        oss_model = str(settings["model"])
        threshold = float(settings["deterministic_activation_threshold"])
        merge_rule = str(settings["hemisphere_merge_rule"])
        hemisphere = str(settings["canonical_hemisphere"]).lower()
        if oss_model != "OSS-DBSv2":
            raise RecordError("configured OSS model must be OSS-DBSv2")
        if threshold != 0.5:
            raise RecordError("configured deterministic pPAM fitting threshold must equal 0.5")
        if merge_rule != "max_probability_union":
            raise RecordError("configured OSS hemisphere merge must be max_probability_union")
        if hemisphere != "right":
            raise RecordError("configured OSS feature space must be right-canonical")
        if not bool(settings["final_dtor_only"]):
            raise RecordError("configured OSS sensitivity must remain final-dTOR-only")
        try:
            score = normative_fiber_score_settings(
                context.config.model.normative_fiber["score"]
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise RecordError(
                "configured OSS sensitivity requires all six fiber score values"
            ) from exc

        return cls(
            task=task,
            final=final,
            sidecars=sidecars,
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            oss_model=oss_model,
            activation_model="pPAM",
            activation_threshold=threshold,
            canonical_hemisphere=hemisphere,
            hemisphere_merge_rule=merge_rule,
            expected_component=(
                "HF_only_reference"
                if task.endpoint.model_family == "hf_fiber"
                else "ULF_addon_component"
            ),
            smoke_permutations=_OSS_SMOKE_PERMUTATIONS,
            seed=_OSS_SMOKE_SEED,
            score=score,
        )


@dataclass(frozen=True)
class OSSServiceOutput:
    artifacts: tuple[TaskArtifact, ...]
    detail: str = "configured_oss_sensitivity_completed"


OSSRunner = Callable[[OSSRequest], OSSServiceOutput]
FinalLoader = Callable[[TaskSpec, RunContext], FinalArtifactRecord]
SidecarLoader = Callable[[TaskSpec, RunContext, FinalArtifactRecord], OSSSidecarBundle]


def load_oss_sidecar_bundle(
    task: TaskSpec,
    context: RunContext,
    final: FinalArtifactRecord,
) -> OSSSidecarBundle:
    """Load the bundle only from the typed endpoint-local producer edge."""
    facts = context.dependency_facts(task, "oss_sidecar_preparation")
    payload = facts.get("oss_sidecar_bundle")
    if not isinstance(payload, dict):
        raise OSSSidecarsUnavailable(
            "the oss_sidecar_preparation dependency did not publish a bundle"
        )
    bundle = OSSSidecarBundle.from_dict(payload)
    if bundle.final_model_id != final.final_model_id:
        raise OSSSidecarsUnavailable("OSS sidecar belongs to another final model")
    if bundle.final_record_hash != final.record_hash:
        raise OSSSidecarsUnavailable("OSS sidecar final-record hash mismatch")
    return bundle


class OSSService:
    """Run OSS sensitivity without modifying source or final-model classification."""

    def __init__(
        self,
        *,
        runner: OSSRunner,
        final_loader: FinalLoader = load_final_record,
        sidecar_loader: SidecarLoader = load_oss_sidecar_bundle,
    ) -> None:
        self.runner = runner
        self.final_loader = final_loader
        self.sidecar_loader = sidecar_loader

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        final: FinalArtifactRecord | None = None
        try:
            final = self.final_loader(task, context)
            sidecars = self.sidecar_loader(task, context, final)
            request = OSSRequest.from_context(
                task,
                context,
                final,
                sidecars=sidecars,
            )
            output = self.runner(request)
        except OSSSidecarsUnavailable as exc:
            facts = {}
            if final is not None:
                facts = {
                    "final_model_id": final.final_model_id,
                    "final_record_hash": final.record_hash,
                    "oss_sensitivity_complete": False,
                }
            return TaskResult(
                TaskStatus.INPUT_FAILURE,
                f"missing_oss_sidecars:{exc}",
                facts=facts,
            )
        except (OSError, RecordError, RuntimeError, ValueError) as exc:
            facts = {}
            if final is not None:
                facts = {
                    "final_model_id": final.final_model_id,
                    "final_record_hash": final.record_hash,
                    "oss_sensitivity_complete": False,
                }
            return TaskResult(
                TaskStatus.EXECUTION_FAILURE,
                f"oss_service_failure:{exc}",
                facts=facts,
            )
        return TaskResult(
            TaskStatus.COMPLETED,
            output.detail,
            facts={
                "oss_sensitivity_complete": True,
                "final_model_id": final.final_model_id,
                "final_record_hash": final.record_hash,
                "oss_model": request.oss_model,
                "activation_model": request.activation_model,
                "activation_threshold": request.activation_threshold,
            },
            artifacts=output.artifacts,
        )


__all__ = [
    "OSSRequest",
    "OSSService",
    "OSSServiceOutput",
    "OSSSidecarBundle",
    "OSSSidecarsUnavailable",
    "load_oss_sidecar_bundle",
]
