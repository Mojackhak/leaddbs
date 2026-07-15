"""Independent add-on exposure, endpoint, support, and collinearity analyses."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...contracts import ArtifactRef, AxisRef, ObservedRequest, SensitivityResult
from ..nuisance import ADJUSTED_BRANCH, NO_DELTA_BRANCH
from ..protocols import ArtifactPublisher
from .common import (
    FinalSensitivityTarget,
    ScientificArrayProvider,
    SensitivityStrategyError,
    evaluate_fixed_cell,
    materialize_vector,
    publish_sensitivity_payload,
    selected_tau_coverage,
    target_for_alternative_request,
    validate_observed_against_final,
    validate_observed_identity,
)


ANALYSIS_NAMES = (
    "nonfinal_branch",
    "gain",
    "total_exposure",
    "support",
    "collinearity",
)
GAIN_OUTCOME_ARTIFACT_KIND = "direction_normalized_addon_gain"
TOTAL_EXPOSURE_ARTIFACT_KIND = "raw_addon_component_exposure"


def _require_subject_artifact(
    value: object,
    *,
    name: str,
    subject_axis: AxisRef,
) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise SensitivityStrategyError(
            f"{name} must be an immutable ArtifactRef"
        )
    if value.axis_refs != (subject_axis,) or value.shape != (subject_axis.count,):
        raise SensitivityStrategyError(
            f"{name} artifact must bind the exact subject axis"
        )
    return value


@dataclass(frozen=True, slots=True)
class SupportDiagnosticInput:
    """Subject and fold-maximum out-of-support fractions."""

    subject_axis: AxisRef
    subject_out_support_fraction: ArtifactRef
    fold_maximum_out_support_fraction: ArtifactRef

    def __post_init__(self) -> None:
        if not isinstance(self.subject_axis, AxisRef):
            raise SensitivityStrategyError("support subject_axis must be an AxisRef")
        for name in (
            "subject_out_support_fraction",
            "fold_maximum_out_support_fraction",
        ):
            _require_subject_artifact(
                getattr(self, name),
                name=name,
                subject_axis=self.subject_axis,
            )


@dataclass(frozen=True, slots=True)
class CollinearityInput:
    """Additional subject vectors evaluated with the selected final score."""

    subject_axis: AxisRef
    column_names: tuple[str, ...]
    columns: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.subject_axis, AxisRef):
            raise SensitivityStrategyError("collinearity subject_axis must be an AxisRef")
        names = tuple(str(name).strip() for name in self.column_names)
        columns = tuple(self.columns)
        if not names or any(not name for name in names):
            raise SensitivityStrategyError("collinearity column names must be nonempty")
        if len(names) != len(columns) or len(set(names)) != len(names):
            raise SensitivityStrategyError(
                "collinearity names and columns must be unique and aligned"
            )
        for index, value in enumerate(columns):
            _require_subject_artifact(
                value,
                name=f"collinearity columns[{index}]",
                subject_axis=self.subject_axis,
            )
        object.__setattr__(self, "column_names", names)
        object.__setattr__(self, "columns", columns)


@dataclass(frozen=True, slots=True)
class AddonExposureSensitivityRequest:
    """Five independent add-on analyses bound to one realized final axis."""

    target: FinalSensitivityTarget
    nonfinal_request: ObservedRequest | None = None
    gain_request: ObservedRequest | None = None
    total_exposure_request: ObservedRequest | None = None
    support_input: SupportDiagnosticInput | None = None
    collinearity_input: CollinearityInput | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, FinalSensitivityTarget):
            raise SensitivityStrategyError("add-on target must be FinalSensitivityTarget")
        if not self.target.final_model.endpoint.model_family.startswith("addon_"):
            raise SensitivityStrategyError("add-on sensitivity requires an add-on final")
        target_request = self.target.observed_request
        for field in ("nonfinal_request", "gain_request", "total_exposure_request"):
            observed = getattr(self, field)
            if observed is not None:
                validate_observed_against_final(
                    self.target.final_model,
                    observed,
                    require_final_branch=field != "nonfinal_request",
                )
                validate_observed_identity(
                    target_request,
                    observed,
                )
                if (
                    field != "total_exposure_request"
                    and observed.exposure != target_request.exposure
                ):
                    raise SensitivityStrategyError(
                        f"{field} must reuse the realized final exposure artifact"
                    )
                if field == "total_exposure_request":
                    total_exposure = observed.exposure
                    if not isinstance(total_exposure, ArtifactRef):
                        raise SensitivityStrategyError(
                            "total_exposure_request must use an immutable exposure artifact"
                        )
                    if total_exposure.kind != TOTAL_EXPOSURE_ARTIFACT_KIND:
                        raise SensitivityStrategyError(
                            "total_exposure_request.exposure must use artifact kind "
                            f"{TOTAL_EXPOSURE_ARTIFACT_KIND!r}"
                        )
                if observed.baseline != target_request.baseline:
                    raise SensitivityStrategyError(
                        f"{field} must reuse the realized final baseline artifact"
                    )
                locked_fields = (
                    "source_grid",
                    "exposure_units",
                    "exposure_space",
                    "hard_computability",
                    "connectome_role",
                    "feature_ids",
                    "fiber_score_settings",
                )
                for locked_field in locked_fields:
                    if getattr(observed, locked_field) != getattr(
                        target_request,
                        locked_field,
                    ):
                        raise SensitivityStrategyError(
                            f"{field} cannot change {locked_field}"
                        )
                if field != "gain_request":
                    if observed.outcome != target_request.outcome:
                        raise SensitivityStrategyError(
                            f"{field} must reuse the realized final outcome artifact"
                        )
                    if observed.outcome_direction != target_request.outcome_direction:
                        raise SensitivityStrategyError(
                            f"{field} must retain the realized final outcome direction"
                        )
                if field in {"gain_request", "total_exposure_request"} and (
                    observed.nuisance_inputs != target_request.nuisance_inputs
                ):
                    raise SensitivityStrategyError(
                        f"{field} must reuse the realized final nuisance artifacts"
                    )
        if self.nonfinal_request is not None:
            final_key = self.target.final_model.final_key
            if final_key is None:
                raise SensitivityStrategyError("realized add-on final has no final key")
            opposite_branch = {
                NO_DELTA_BRANCH: ADJUSTED_BRANCH,
                ADJUSTED_BRANCH: NO_DELTA_BRANCH,
            }.get(final_key.final_branch)
            if opposite_branch is None or self.nonfinal_request.branch != opposite_branch:
                raise SensitivityStrategyError(
                    "nonfinal_request must identify the canonical opposite branch"
                )
        if self.gain_request is not None:
            gain_outcome = _require_subject_artifact(
                self.gain_request.outcome,
                name="gain_request.outcome",
                subject_axis=target_request.subject_axis,
            )
            if gain_outcome.kind != GAIN_OUTCOME_ARTIFACT_KIND:
                raise SensitivityStrategyError(
                    "gain_request.outcome must use artifact kind "
                    f"{GAIN_OUTCOME_ARTIFACT_KIND!r}"
                )
            if self.gain_request.outcome_direction != "higher":
                raise SensitivityStrategyError(
                    "direction-normalized gain requires outcome_direction='higher'"
                )
        if self.support_input is not None:
            if not isinstance(self.support_input, SupportDiagnosticInput):
                raise SensitivityStrategyError(
                    "support_input must be SupportDiagnosticInput"
                )
            if self.support_input.subject_axis != self.target.observed_request.subject_axis:
                raise SensitivityStrategyError("support subject axis must match the target")
        if self.collinearity_input is not None:
            if not isinstance(self.collinearity_input, CollinearityInput):
                raise SensitivityStrategyError(
                    "collinearity_input must be CollinearityInput"
                )
            if self.collinearity_input.subject_axis != self.target.observed_request.subject_axis:
                raise SensitivityStrategyError(
                    "collinearity subject axis must match the target"
                )


class AddonExposureSensitivityStrategy:
    """Run every configured add-on analysis to its own terminal status."""

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

    def _cell_analysis(
        self,
        final_target: FinalSensitivityTarget,
        observed: ObservedRequest | None,
        *,
        analysis_scope: str,
        tau: float,
        coverage: int,
    ) -> dict[str, object]:
        if observed is None:
            return {"technical_status": "not_applicable", "reason": "not_configured"}
        try:
            evidence = evaluate_fixed_cell(
                target_for_alternative_request(
                    final_target,
                    observed,
                    analysis_scope=analysis_scope,
                ),
                tau=tau,
                coverage=coverage,
                array_provider=self.array_provider,
            )
        except Exception as exc:
            return {
                "technical_status": "not_computable",
                "reason": f"{type(exc).__name__}:{exc}",
            }
        return evidence.as_payload()

    def _support(self, value: SupportDiagnosticInput | None) -> dict[str, object]:
        if value is None:
            return {"technical_status": "not_applicable", "reason": "not_configured"}
        try:
            subject = materialize_vector(
                value.subject_out_support_fraction,
                name="subject_out_support_fraction",
                subject_axis=value.subject_axis,
                array_provider=self.array_provider,
            )
            folds = materialize_vector(
                value.fold_maximum_out_support_fraction,
                name="fold_maximum_out_support_fraction",
                subject_axis=value.subject_axis,
                array_provider=self.array_provider,
            )
        except Exception as exc:
            return {
                "technical_status": "not_computable",
                "reason": f"{type(exc).__name__}:{exc}",
            }
        if np.any((subject < 0.0) | (subject > 1.0)) or np.any(
            (folds < 0.0) | (folds > 1.0)
        ):
            return {
                "technical_status": "not_computable",
                "reason": "support_fractions_outside_unit_interval",
            }
        maximum = float(max(np.max(subject), np.max(folds)))
        median = float(np.median(subject))
        fraction_over_0p50 = float(np.mean(subject > 0.50))
        fraction_over_0p80 = float(np.mean(subject > 0.80))
        if median > 0.50 or fraction_over_0p80 > 0.25 or maximum > 0.95:
            category = "invalid_extreme_out_of_support"
        elif median <= 0.20 and fraction_over_0p50 <= 0.25:
            category = "adequate"
        else:
            category = "limited"
        return {
            "technical_status": "complete",
            "support_category": category,
            "median_out_support_fraction": median,
            "fraction_over_0p50": fraction_over_0p50,
            "fraction_over_0p80": fraction_over_0p80,
            "maximum_out_support_fraction": maximum,
            "individual_extreme_threshold": 0.95,
        }

    def _collinearity(
        self,
        request: AddonExposureSensitivityRequest,
        *,
        tau: float,
        coverage: int,
    ) -> dict[str, object]:
        value = request.collinearity_input
        if value is None:
            return {"technical_status": "not_applicable", "reason": "not_configured"}
        try:
            selected = evaluate_fixed_cell(
                request.target,
                tau=tau,
                coverage=coverage,
                array_provider=self.array_provider,
            )
            if selected.full_scores is None:
                raise SensitivityStrategyError("selected final score is not computable")
            columns = [selected.full_scores]
            for index, scientific_input in enumerate(value.columns):
                columns.append(
                    materialize_vector(
                        scientific_input,
                        name=f"collinearity_columns[{index}]",
                        subject_axis=value.subject_axis,
                        array_provider=self.array_provider,
                    )
                )
            design = np.column_stack(columns)
            centered = design - np.mean(design, axis=0, keepdims=True)
            scales = np.std(centered, axis=0, ddof=1)
            if not np.all(np.isfinite(design)) or np.any(scales <= 0.0):
                raise SensitivityStrategyError(
                    "collinearity design must be finite and nonconstant"
                )
            standardized = centered / scales
            correlations = np.corrcoef(standardized, rowvar=False)
            off_diagonal = np.abs(
                correlations[np.triu_indices_from(correlations, k=1)]
            )
            maximum = float(np.max(off_diagonal)) if off_diagonal.size else 0.0
            warning = (
                "acceptable" if maximum < 0.85 else "high" if maximum < 0.95 else "severe"
            )
            return {
                "technical_status": "complete",
                "columns": ["selected_final_score", *value.column_names],
                "correlation_matrix": correlations.tolist(),
                "maximum_absolute_pairwise_correlation": maximum,
                "collinearity_warning": warning,
                "condition_number": float(np.linalg.cond(standardized)),
            }
        except Exception as exc:
            return {
                "technical_status": "not_computable",
                "reason": f"{type(exc).__name__}:{exc}",
            }

    def run(self, request: AddonExposureSensitivityRequest) -> SensitivityResult:
        if not isinstance(request, AddonExposureSensitivityRequest):
            raise TypeError("request must be an AddonExposureSensitivityRequest")
        tau, coverage = selected_tau_coverage(request.target.final_model)
        analyses = {
            "nonfinal_branch": self._cell_analysis(
                request.target,
                request.nonfinal_request,
                analysis_scope="nonfinal_branch",
                tau=tau,
                coverage=coverage,
            ),
            "gain": self._cell_analysis(
                request.target,
                request.gain_request,
                analysis_scope="gain",
                tau=tau,
                coverage=coverage,
            ),
            "total_exposure": self._cell_analysis(
                request.target,
                request.total_exposure_request,
                analysis_scope="total_exposure",
                tau=tau,
                coverage=coverage,
            ),
            "support": self._support(request.support_input),
            "collinearity": self._collinearity(
                request,
                tau=tau,
                coverage=coverage,
            ),
        }
        if tuple(analyses) != ANALYSIS_NAMES:
            raise AssertionError("add-on analysis order changed")
        payload = {
            "schema_version": "dual_frequency_addon_sensitivity_v1",
            "target_id": request.target.final_model.identifier,
            "selected_tau": tau,
            "selected_coverage": coverage,
            "analyses": analyses,
        }
        return publish_sensitivity_payload(
            publisher=self.publisher,
            target_id=request.target.final_model.identifier,
            sensitivity_kind="addon_exposure",
            filename="addon_exposure_sensitivity.json",
            artifact_kind="addon_exposure_sensitivity",
            payload=payload,
        )


__all__ = [
    "ANALYSIS_NAMES",
    "AddonExposureSensitivityRequest",
    "AddonExposureSensitivityStrategy",
    "CollinearityInput",
    "SupportDiagnosticInput",
]
