"""Injected-replicate spatial-jitter sensitivity on a realized final cell."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Protocol, runtime_checkable

import numpy as np

from ...contracts import ArtifactRef, ObservedRequest, SensitivityResult
from ..protocols import ArtifactPublisher
from .common import (
    FinalSensitivityTarget,
    ScientificArrayProvider,
    SensitivityStrategyError,
    evaluate_fixed_cell,
    publish_sensitivity_payload,
    selected_tau_coverage,
    validate_observed_identity,
)


_VALID_ADDON_SUPPORT_STATUSES = frozenset(
    {
        "adequate",
        "limited",
        "invalid_extreme_out_of_support",
        "invalid_no_reference_component_exposure",
        "invalid_no_reference_component_coverage",
    }
)
_COMPUTABLE_ADDON_SUPPORT_STATUSES = frozenset({"adequate", "limited"})


@dataclass(frozen=True, slots=True)
class SpatialJitterSettings:
    """Deterministic replicate count and root seed."""

    replicates: int
    seed: int

    def __post_init__(self) -> None:
        if type(self.replicates) is not int or self.replicates < 1:
            raise SensitivityStrategyError("jitter replicates must be positive")
        if type(self.seed) is not int or self.seed < 0:
            raise SensitivityStrategyError("jitter seed must be a nonnegative integer")


def jitter_rebuild_identity(
    target: FinalSensitivityTarget,
    *,
    observed_request: ObservedRequest,
    replicate_index: int,
    replicate_seed: int,
    reference_overlap_mask: ArtifactRef | None = None,
    support_status: str = "not_applicable",
    support_qc: tuple[tuple[str, float | int | str | bool], ...] = (),
    component: str = "replicate",
) -> str:
    """Bind one rebuild token to all perturbed scientific artifact identities."""

    if not isinstance(target, FinalSensitivityTarget):
        raise SensitivityStrategyError(
            "jitter rebuild identity requires a FinalSensitivityTarget"
        )
    if type(replicate_index) is not int or replicate_index < 0:
        raise SensitivityStrategyError("replicate_index must be nonnegative")
    if type(replicate_seed) is not int or replicate_seed < 0:
        raise SensitivityStrategyError("replicate_seed must be nonnegative")
    token = str(component).strip()
    if token not in {"replicate", "delta_reference"}:
        raise SensitivityStrategyError("unsupported jitter rebuild component")
    validate_observed_identity(target.observed_request, observed_request)
    if not isinstance(observed_request.exposure, ArtifactRef):
        raise SensitivityStrategyError(
            "jitter rebuild exposure must be an immutable ArtifactRef"
        )
    if reference_overlap_mask is not None and not isinstance(
        reference_overlap_mask,
        ArtifactRef,
    ):
        raise SensitivityStrategyError(
            "jitter rebuild overlap mask must be an immutable ArtifactRef"
        )
    normalized_qc = _normalize_support_qc(support_qc)
    nuisance_artifacts: list[str] = []
    if observed_request.branch == "delta_reference_adjusted":
        if len(observed_request.nuisance_inputs) != 2 or not all(
            isinstance(value, ArtifactRef)
            for value in observed_request.nuisance_inputs
        ):
            raise SensitivityStrategyError(
                "adjusted jitter rebuild requires full/fold DeltaReferenceScore artifacts"
            )
        nuisance_artifacts = [
            value.identifier
            for value in observed_request.nuisance_inputs
            if isinstance(value, ArtifactRef)
        ]
    payload = json.dumps(
        {
            "component": token,
            "delta_artifacts": nuisance_artifacts,
            "exposure_artifact": observed_request.exposure.identifier,
            "final_model_id": target.final_model.identifier,
            "overlap_artifact": (
                None
                if reference_overlap_mask is None
                else reference_overlap_mask.identifier
            ),
            "replicate_index": replicate_index,
            "replicate_seed": replicate_seed,
            "support_qc": normalized_qc,
            "support_status": str(support_status).strip(),
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"jitter_{token}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _normalize_support_qc(
    rows: tuple[tuple[str, float | int | str | bool], ...],
) -> tuple[tuple[str, float | int | str | bool], ...]:
    normalized: list[tuple[str, float | int | str | bool]] = []
    seen: set[str] = set()
    for row in tuple(rows):
        if len(row) != 2:
            raise SensitivityStrategyError(
                "jitter support_qc must contain key-value pairs"
            )
        key = str(row[0]).strip()
        if not key:
            raise SensitivityStrategyError(
                "jitter support_qc keys must be nonempty"
            )
        if key in seen:
            raise SensitivityStrategyError("jitter support_qc keys must be unique")
        seen.add(key)
        value = row[1]
        if type(value) not in {bool, int, float, str}:
            raise SensitivityStrategyError(
                "jitter support_qc values must be JSON scalar values"
            )
        if type(value) is float and not math.isfinite(value):
            raise SensitivityStrategyError(
                "jitter support_qc numeric values must be finite"
            )
        normalized.append((key, value))
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class JitterReplicateEvidence:
    """Complete perturbed inputs and rebuild evidence for one jitter replicate."""

    observed_request: ObservedRequest
    replicate_index: int
    replicate_seed: int
    rebuild_identity: str
    reference_overlap_mask: ArtifactRef | None = None
    support_status: str = "not_applicable"
    support_qc: tuple[tuple[str, float | int | str | bool], ...] = ()
    delta_rebuild_identity: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observed_request, ObservedRequest):
            raise SensitivityStrategyError(
                "jitter evidence requires a complete ObservedRequest"
            )
        if type(self.replicate_index) is not int or self.replicate_index < 0:
            raise SensitivityStrategyError(
                "jitter evidence replicate_index must be nonnegative"
            )
        if type(self.replicate_seed) is not int or self.replicate_seed < 0:
            raise SensitivityStrategyError(
                "jitter evidence replicate_seed must be nonnegative"
            )
        rebuild_identity = str(self.rebuild_identity).strip()
        if not rebuild_identity:
            raise SensitivityStrategyError(
                "jitter evidence rebuild_identity must be nonempty"
            )
        object.__setattr__(self, "rebuild_identity", rebuild_identity)
        if self.reference_overlap_mask is not None and not isinstance(
            self.reference_overlap_mask,
            ArtifactRef,
        ):
            raise SensitivityStrategyError(
                "jitter reference_overlap_mask must be an immutable ArtifactRef"
            )
        support_status = str(self.support_status).strip()
        if not support_status:
            raise SensitivityStrategyError(
                "jitter evidence support_status must be nonempty"
            )
        object.__setattr__(self, "support_status", support_status)
        support_qc = _normalize_support_qc(self.support_qc)
        object.__setattr__(self, "support_qc", support_qc)
        if self.delta_rebuild_identity is not None:
            delta_identity = str(self.delta_rebuild_identity).strip()
            if not delta_identity:
                raise SensitivityStrategyError(
                    "delta_rebuild_identity must be nonempty when declared"
                )
            object.__setattr__(self, "delta_rebuild_identity", delta_identity)


@runtime_checkable
class JitterReplicateProvider(Protocol):
    """Build a complete perturbed request without path or geometry discovery."""

    def build_replicate(
        self,
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence: ...


@dataclass(frozen=True, slots=True)
class SpatialJitterRequest:
    target: FinalSensitivityTarget
    settings: SpatialJitterSettings
    replicate_provider: JitterReplicateProvider

    def __post_init__(self) -> None:
        if not isinstance(self.target, FinalSensitivityTarget):
            raise SensitivityStrategyError(
                "spatial-jitter target must be a FinalSensitivityTarget"
            )
        if not isinstance(self.settings, SpatialJitterSettings):
            raise SensitivityStrategyError(
                "spatial-jitter settings must be SpatialJitterSettings"
            )
        if not isinstance(self.replicate_provider, JitterReplicateProvider):
            raise SensitivityStrategyError(
                "replicate_provider must implement JitterReplicateProvider"
            )


def _replicate_seed(seed: int, index: int) -> int:
    sequence = np.random.SeedSequence([int(seed), int(index)])
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


def _numeric_aggregate(rows: list[dict[str, object]]) -> dict[str, dict[str, float | int]]:
    keys = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, (bool, np.bool_))
        }
    )
    output: dict[str, dict[str, float | int]] = {}
    for key in keys:
        values = np.asarray(
            [
                float(row[key])
                for row in rows
                if key in row and math.isfinite(float(row[key]))
            ],
            dtype=np.float64,
        )
        if not values.size:
            continue
        output[key] = {
            "finite_count": int(values.size),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }
    return output


def _same_scientific_identity(
    first: ArtifactRef,
    second: ArtifactRef,
) -> bool:
    return first == second or (
        first.sha256 == second.sha256
        and first.shape == second.shape
        and first.axis_refs == second.axis_refs
    )


def _validate_locked_observed_fields(
    original: ObservedRequest,
    rebuilt: ObservedRequest,
) -> None:
    locked_fields = (
        "endpoint",
        "branch",
        "subject_axis",
        "feature_axis",
        "source_grid",
        "exposure_units",
        "exposure_space",
        "outcome_direction",
        "hard_computability",
        "connectome_role",
        "feature_ids",
        "fiber_score_settings",
    )
    for field in locked_fields:
        if getattr(rebuilt, field) != getattr(original, field):
            raise SensitivityStrategyError(
                f"jitter cannot change locked observed field {field!r}"
            )
    if rebuilt.outcome != original.outcome:
        raise SensitivityStrategyError(
            "jitter cannot change the clinical outcome artifact"
        )
    if rebuilt.baseline != original.baseline:
        raise SensitivityStrategyError(
            "jitter cannot change the clinical baseline artifact"
        )


def _validate_replicate_evidence(
    target: FinalSensitivityTarget,
    evidence: JitterReplicateEvidence,
    *,
    replicate_index: int,
    replicate_seed: int,
) -> None:
    if not isinstance(evidence, JitterReplicateEvidence):
        raise SensitivityStrategyError(
            "jitter provider must return JitterReplicateEvidence"
        )
    if (
        evidence.replicate_index != replicate_index
        or evidence.replicate_seed != replicate_seed
    ):
        raise SensitivityStrategyError(
            "jitter evidence index and seed must equal the requested replicate"
        )
    validate_observed_identity(
        target.observed_request,
        evidence.observed_request,
    )
    observed = evidence.observed_request
    original = target.observed_request
    _validate_locked_observed_fields(original, observed)
    if not isinstance(original.exposure, ArtifactRef) or not isinstance(
        observed.exposure,
        ArtifactRef,
    ):
        raise SensitivityStrategyError(
            "jitter exposure inputs must be immutable ArtifactRef values"
        )
    if _same_scientific_identity(original.exposure, observed.exposure):
        raise SensitivityStrategyError(
            "jitter cannot reuse the original exposure artifact identity"
        )

    expected_identity = jitter_rebuild_identity(
        target,
        observed_request=observed,
        replicate_index=replicate_index,
        replicate_seed=replicate_seed,
        reference_overlap_mask=evidence.reference_overlap_mask,
        support_status=evidence.support_status,
        support_qc=evidence.support_qc,
    )
    if evidence.rebuild_identity != expected_identity:
        raise SensitivityStrategyError(
            "jitter rebuild identity does not match the perturbed artifact evidence"
        )

    is_addon = target.final_model.endpoint.model_family.startswith("addon_")
    if not is_addon:
        if observed.nuisance_inputs != original.nuisance_inputs:
            raise SensitivityStrategyError(
                "reference jitter cannot change nuisance artifacts"
            )
        if evidence.reference_overlap_mask is not None:
            raise SensitivityStrategyError(
                "reference jitter cannot declare a reference-overlap mask"
            )
        if evidence.support_status != "not_applicable" or evidence.support_qc:
            raise SensitivityStrategyError(
                "reference jitter support evidence must be not_applicable"
            )
        if evidence.delta_rebuild_identity is not None:
            raise SensitivityStrategyError(
                "reference jitter cannot declare DeltaReferenceScore evidence"
            )
        return

    if evidence.reference_overlap_mask is None:
        raise SensitivityStrategyError(
            "add-on jitter requires a rebuilt reference-overlap mask"
        )
    if not isinstance(target.reference_overlap_mask, ArtifactRef):
        raise SensitivityStrategyError(
            "add-on jitter target requires an original reference-overlap artifact"
        )
    if _same_scientific_identity(
        target.reference_overlap_mask,
        evidence.reference_overlap_mask,
    ):
        raise SensitivityStrategyError(
            "add-on jitter cannot reuse the original reference-overlap mask"
        )
    if evidence.support_status not in _VALID_ADDON_SUPPORT_STATUSES:
        raise SensitivityStrategyError(
            "add-on jitter requires a recognized rebuilt support status"
        )
    if not evidence.support_qc:
        raise SensitivityStrategyError(
            "add-on jitter requires nonempty rebuilt support QC"
        )

    if observed.branch == "delta_reference_adjusted":
        if (
            len(original.nuisance_inputs) != 2
            or len(observed.nuisance_inputs) != 2
        ):
            raise SensitivityStrategyError(
                "adjusted add-on jitter requires original and rebuilt full/fold "
                "DeltaReferenceScore inputs"
            )
        expected_delta_identity = jitter_rebuild_identity(
            target,
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            reference_overlap_mask=evidence.reference_overlap_mask,
            support_status=evidence.support_status,
            support_qc=evidence.support_qc,
            component="delta_reference",
        )
        if evidence.delta_rebuild_identity != expected_delta_identity:
            raise SensitivityStrategyError(
                "adjusted add-on jitter requires DeltaReferenceScore rebuild evidence"
            )
        for original_value, rebuilt_value in zip(
            original.nuisance_inputs,
            observed.nuisance_inputs,
            strict=True,
        ):
            if not isinstance(original_value, ArtifactRef) or not isinstance(
                rebuilt_value,
                ArtifactRef,
            ):
                raise SensitivityStrategyError(
                    "adjusted add-on jitter requires immutable DeltaReferenceScore artifacts"
                )
            if _same_scientific_identity(original_value, rebuilt_value):
                raise SensitivityStrategyError(
                    "adjusted add-on jitter cannot reuse original DeltaReferenceScore inputs"
                )
    elif observed.branch == "no_delta_reference":
        if (
            observed.nuisance_inputs != original.nuisance_inputs
            or observed.nuisance_inputs
            or evidence.delta_rebuild_identity is not None
        ):
            raise SensitivityStrategyError(
                "no-delta add-on jitter cannot declare DeltaReferenceScore evidence"
            )
    else:
        raise SensitivityStrategyError("unsupported add-on jitter branch")


class SpatialJitterStrategy:
    """Aggregate deterministic typed jitter replicates without file discovery."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        array_provider: ScientificArrayProvider | None = None,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        self.publisher = publisher
        self.array_provider = array_provider

    def run(self, request: SpatialJitterRequest) -> SensitivityResult:
        if not isinstance(request, SpatialJitterRequest):
            raise TypeError("request must be a SpatialJitterRequest")
        tau, coverage = selected_tau_coverage(request.target.final_model)
        replicate_rows: list[dict[str, object]] = []
        completed_metrics: list[dict[str, object]] = []
        for index in range(request.settings.replicates):
            seed = _replicate_seed(request.settings.seed, index)
            try:
                replicate = request.replicate_provider.build_replicate(
                    request.target,
                    replicate_index=index,
                    replicate_seed=seed,
                )
            except SensitivityStrategyError:
                raise
            except Exception as exc:  # Provider execution is replicate-local.
                replicate_rows.append(
                    {
                        "replicate_index": index,
                        "replicate_seed": seed,
                        "technical_status": "failed",
                        "reason": f"provider_failure:{type(exc).__name__}:{exc}",
                    }
                )
                continue
            # Contract violations are global input failures, not noisy replicates.
            _validate_replicate_evidence(
                request.target,
                replicate,
                replicate_index=index,
                replicate_seed=seed,
            )
            replicate_target = FinalSensitivityTarget(
                final_model=request.target.final_model,
                observed_request=replicate.observed_request,
                reference_overlap_mask=replicate.reference_overlap_mask,
            )
            support_qc = {
                str(key): value for key, value in replicate.support_qc
            }
            if (
                replicate.support_status
                not in _COMPUTABLE_ADDON_SUPPORT_STATUSES
                and replicate.support_status != "not_applicable"
            ):
                replicate_rows.append(
                    {
                        "replicate_index": index,
                        "replicate_seed": seed,
                        "rebuild_identity": replicate.rebuild_identity,
                        "delta_rebuild_identity": replicate.delta_rebuild_identity,
                        "support_status": replicate.support_status,
                        "support_qc": support_qc,
                        "technical_status": "not_computable",
                        "reason": "rebuilt_support_is_invalid",
                    }
                )
                continue
            evidence = evaluate_fixed_cell(
                replicate_target,
                tau=tau,
                coverage=coverage,
                array_provider=self.array_provider,
            )
            row = {
                "replicate_index": index,
                "replicate_seed": seed,
                "rebuild_identity": replicate.rebuild_identity,
                "delta_rebuild_identity": replicate.delta_rebuild_identity,
                "support_status": replicate.support_status,
                "support_qc": support_qc,
                **evidence.as_payload(),
            }
            replicate_rows.append(row)
            if evidence.technical_status == "complete":
                completed_metrics.append(dict(evidence.metrics))

        payload = {
            "schema_version": "dual_frequency_spatial_jitter_v1",
            "target_id": request.target.final_model.identifier,
            "selected_tau": tau,
            "selected_coverage": coverage,
            "root_seed": request.settings.seed,
            "requested_replicates": request.settings.replicates,
            "completed_replicates": len(completed_metrics),
            "replicates": replicate_rows,
            "numeric_aggregate": _numeric_aggregate(completed_metrics),
        }
        return publish_sensitivity_payload(
            publisher=self.publisher,
            target_id=request.target.final_model.identifier,
            sensitivity_kind="spatial_jitter",
            filename="spatial_jitter_metrics.json",
            artifact_kind="spatial_jitter_metrics",
            payload=payload,
        )


__all__ = [
    "JitterReplicateEvidence",
    "JitterReplicateProvider",
    "SpatialJitterRequest",
    "SpatialJitterSettings",
    "SpatialJitterStrategy",
    "jitter_rebuild_identity",
]
