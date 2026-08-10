"""Spatial-jitter sensitivity for a locked individualized target model."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

import numpy as np

from ...contracts import (
    ArtifactRef,
    AxisRef,
    FinalModelRecord,
    SensitivityResult,
    TargetObservedRequest,
    canonical_hash,
)
from ..individualized_target import (
    build_target_nuisance_plan,
    evaluate_target_cell,
)
from ..protocols import ArtifactPublisher
from .common import ScientificArrayProvider
from .spatial_jitter import SpatialJitterSettings


class IndividualizedTargetJitterError(RuntimeError):
    """Raised when target spatial jitter cannot evaluate the locked final."""


@dataclass(frozen=True, slots=True)
class TargetJitterReplicateEvidence:
    """One deterministic translated target request."""

    observed_request: TargetObservedRequest | None
    replicate_index: int
    replicate_seed: int
    technical_status: str = "complete"
    reason: str | None = None

    def __post_init__(self) -> None:
        status = str(self.technical_status).strip()
        if status not in {"complete", "not_computable"}:
            raise IndividualizedTargetJitterError(
                "target jitter replicate has an unsupported technical status"
            )
        object.__setattr__(self, "technical_status", status)
        if status == "complete" and not isinstance(
            self.observed_request,
            TargetObservedRequest,
        ):
            raise IndividualizedTargetJitterError(
                "complete target jitter replicate requires TargetObservedRequest"
            )
        if status == "not_computable":
            if self.observed_request is not None:
                raise IndividualizedTargetJitterError(
                    "non-computable target jitter replicate cannot carry a request"
                )
            reason = str(self.reason or "").strip()
            if not reason:
                raise IndividualizedTargetJitterError(
                    "non-computable target jitter replicate requires a reason"
                )
            object.__setattr__(self, "reason", reason)
        if type(self.replicate_index) is not int or self.replicate_index < 0:
            raise IndividualizedTargetJitterError(
                "target jitter replicate_index must be nonnegative"
            )
        if type(self.replicate_seed) is not int or self.replicate_seed < 0:
            raise IndividualizedTargetJitterError(
                "target jitter replicate_seed must be nonnegative"
            )


@runtime_checkable
class TargetJitterReplicateProvider(Protocol):
    """Build one translated target request on the locked scientific axes."""

    def replicate_indices(self) -> tuple[int, ...]: ...

    def build_replicate(
        self,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> TargetJitterReplicateEvidence: ...


@dataclass(frozen=True, slots=True)
class IndividualizedTargetJitterRequest:
    """A locked target final and its deterministic perturbation provider."""

    final_model: FinalModelRecord
    observed_request: TargetObservedRequest
    settings: SpatialJitterSettings
    replicate_provider: TargetJitterReplicateProvider

    def __post_init__(self) -> None:
        if (
            not isinstance(self.final_model, FinalModelRecord)
            or self.final_model.final_key is None
            or not self.final_model.endpoint.model_family.endswith(
                "individualized"
            )
        ):
            raise IndividualizedTargetJitterError(
                "target jitter requires a realized individualized final"
            )
        if (
            not isinstance(self.observed_request, TargetObservedRequest)
            or self.observed_request.endpoint != self.final_model.endpoint
        ):
            raise IndividualizedTargetJitterError(
                "target jitter observed request does not match the final"
            )
        if not isinstance(self.settings, SpatialJitterSettings):
            raise IndividualizedTargetJitterError(
                "target jitter settings are invalid"
            )
        if not isinstance(
            self.replicate_provider,
            TargetJitterReplicateProvider,
        ):
            raise IndividualizedTargetJitterError(
                "target jitter replicate provider is invalid"
            )


def _replicate_seed(seed: int, index: int) -> int:
    sequence = np.random.SeedSequence([int(seed), int(index)])
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


class IndividualizedTargetSpatialJitterBackend:
    """Recompute the fixed final target cell after translated E-field sampling."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ScientificArrayProvider,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        if not isinstance(artifact_store, ScientificArrayProvider):
            raise TypeError(
                "artifact_store must implement ScientificArrayProvider"
            )
        self.publisher = publisher
        self.artifact_store = artifact_store

    def _materialize(self, artifact: ArtifactRef) -> np.ndarray:
        return np.asarray(
            self.artifact_store.materialize(
                artifact,
                expected_dtype=artifact.dtype,
                expected_shape=artifact.shape,
                expected_axes=artifact.axis_refs,
                expected_units=artifact.units,
                expected_space=artifact.space,
            )
        )

    @staticmethod
    def _validate_locked_request(
        original: TargetObservedRequest,
        rebuilt: TargetObservedRequest,
    ) -> None:
        for field in (
            "endpoint",
            "branch",
            "subject_axis",
            "target_axis",
            "tau_axis",
            "source_grid",
            "outcome_direction",
            "hard_computability",
            "score_settings",
        ):
            if getattr(rebuilt, field) != getattr(original, field):
                raise IndividualizedTargetJitterError(
                    f"target jitter cannot change locked field {field!r}"
                )
        if rebuilt.outcome != original.outcome or rebuilt.baseline != original.baseline:
            raise IndividualizedTargetJitterError(
                "target jitter cannot change clinical inputs"
            )
        if original.branch != "delta_reference_adjusted":
            if rebuilt.nuisance_inputs != original.nuisance_inputs:
                raise IndividualizedTargetJitterError(
                    "target jitter cannot add nuisance inputs"
                )
        elif len(rebuilt.nuisance_inputs) != 2:
            raise IndividualizedTargetJitterError(
                "adjusted target jitter requires rebuilt full and fold "
                "DeltaReferenceScore inputs"
            )

    def _evaluate(
        self,
        request: TargetObservedRequest,
        *,
        tau: float,
        coverage: int,
    ) -> dict[str, object]:
        try:
            tau_index = request.source_grid.tau_values.index(float(tau))
        except ValueError as exc:
            raise IndividualizedTargetJitterError(
                "selected target tau is outside the jitter request grid"
            ) from exc
        burdens = np.asarray(
            self._materialize(request.patient_burdens),
            dtype=np.float64,
        )[tau_index]
        support = np.asarray(
            self._materialize(request.patient_support),
            dtype=bool,
        )[tau_index]
        outcome = np.asarray(
            self._materialize(request.outcome),
            dtype=np.float64,
        )
        baseline = np.asarray(
            self._materialize(request.baseline),
            dtype=np.float64,
        )
        nuisance = build_target_nuisance_plan(
            request,
            baseline,
            self.artifact_store,
        )
        return evaluate_target_cell(
            burdens,
            support,
            outcome,
            nuisance,
            request.outcome_direction,
            tau,
            coverage,
            request.hard_computability,
            retain_arrays=False,
        ).metrics.as_json_dict()

    def run(
        self,
        request: IndividualizedTargetJitterRequest,
    ) -> SensitivityResult:
        if not isinstance(request, IndividualizedTargetJitterRequest):
            raise TypeError(
                "request must be IndividualizedTargetJitterRequest"
            )
        final_key = request.final_model.final_key
        assert final_key is not None
        tau = float(final_key.selected_tau)
        coverage = int(final_key.selected_coverage)
        observed = self._evaluate(
            request.observed_request,
            tau=tau,
            coverage=coverage,
        )
        null = np.full(
            request.settings.replicates,
            np.nan,
            dtype=np.float64,
        )
        rows: list[dict[str, object] | None] = [
            None
        ] * request.settings.replicates
        order = request.replicate_provider.replicate_indices()
        if (
            len(order) != request.settings.replicates
            or set(order) != set(range(request.settings.replicates))
        ):
            raise IndividualizedTargetJitterError(
                "target jitter provider returned an invalid replicate order"
            )
        for index in order:
            seed = _replicate_seed(request.settings.seed, index)
            evidence = request.replicate_provider.build_replicate(
                replicate_index=index,
                replicate_seed=seed,
            )
            if (
                evidence.replicate_index != index
                or evidence.replicate_seed != seed
            ):
                raise IndividualizedTargetJitterError(
                    "target jitter provider returned the wrong replicate"
                )
            if evidence.technical_status == "not_computable":
                rows[index] = {
                    "replicate_index": index,
                    "replicate_seed": seed,
                    "technical_status": "not_computable",
                    "reason": evidence.reason,
                }
                continue
            assert evidence.observed_request is not None
            self._validate_locked_request(
                request.observed_request,
                evidence.observed_request,
            )
            metrics = self._evaluate(
                evidence.observed_request,
                tau=tau,
                coverage=coverage,
            )
            rho = metrics.get("loocv_spearman_rho")
            if isinstance(rho, (int, float)) and math.isfinite(float(rho)):
                null[index] = float(rho)
            rows[index] = {
                "replicate_index": index,
                "replicate_seed": seed,
                "technical_status": "complete",
                "metrics": metrics,
            }
        replicate_axis = AxisRef(
            axis_id=(
                f"{request.final_model.endpoint.identifier}:"
                "individualized-target-jitter"
            ),
            count=request.settings.replicates,
            sha256=canonical_hash(
                {
                    "final_model_id": request.final_model.identifier,
                    "replicates": request.settings.replicates,
                    "seed": request.settings.seed,
                    "translation_fwhm_mm": (
                        request.settings.translation_fwhm_mm
                    ),
                }
            ),
        )
        observed_artifact = self.publisher.document(
            "observed_statistic.json",
            {
                "selected_tau": tau,
                "selected_coverage": coverage,
                "metrics": observed,
            },
            kind="individualized_target_jitter_observed_statistic",
        )
        null_artifact = self.publisher.array(
            "null_statistics.npy",
            null,
            kind="individualized_target_jitter_statistics",
            axes=(replicate_axis,),
            units="spearman_rho",
            space=None,
        )
        finite = null[np.isfinite(null)]
        summary_artifact = self.publisher.document(
            "summary.json",
            {
                "target_id": request.final_model.identifier,
                "selected_tau": tau,
                "selected_coverage": coverage,
                "root_seed": request.settings.seed,
                "translation_fwhm_mm": (
                    request.settings.translation_fwhm_mm
                ),
                "translation_sigma_mm": (
                    request.settings.translation_sigma_mm
                ),
                "requested_replicates": request.settings.replicates,
                "finite_replicates": int(finite.size),
                "rho_mean": (
                    float(np.mean(finite)) if finite.size else None
                ),
                "rho_median": (
                    float(np.median(finite)) if finite.size else None
                ),
                "rho_percentile_2_5": (
                    float(np.percentile(finite, 2.5))
                    if finite.size
                    else None
                ),
                "rho_percentile_97_5": (
                    float(np.percentile(finite, 97.5))
                    if finite.size
                    else None
                ),
                "replicates": [
                    row for row in rows if row is not None
                ],
            },
            kind="individualized_target_jitter_summary",
        )
        return SensitivityResult(
            target_id=request.final_model.identifier,
            sensitivity_kind="spatial_jitter",
            artifacts=(
                observed_artifact,
                null_artifact,
                summary_artifact,
            ),
        )


__all__ = [
    "IndividualizedTargetJitterError",
    "IndividualizedTargetJitterRequest",
    "IndividualizedTargetSpatialJitterBackend",
    "TargetJitterReplicateEvidence",
    "TargetJitterReplicateProvider",
]
