"""Observed-only and final-linked normative-fiber diagnostic controls."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...contracts import (
    NormativeFiberScoreSettings,
    ObservedRequest,
    ObservedResult,
    SensitivityResult,
)
from ..normative_fiber.coverage import candidate_mask, coverage_counts
from ..protocols import ArtifactPublisher
from ..statistics import safe_correlation
from .common import (
    FinalSensitivityTarget,
    ScientificArrayProvider,
    SensitivityStrategyError,
    evaluate_fixed_cell,
    evaluate_observed_fiber_cell,
    materialize_exposure,
    materialize_target_exposure,
    materialize_vector,
    publish_sensitivity_payload,
    selected_tau_coverage,
)


@dataclass(frozen=True, slots=True)
class ObservedFiberControlRequest:
    """Pre-resolver reference-fiber control inputs and diagnostic evidence."""

    observed_request: ObservedRequest
    observed_result: ObservedResult
    peak_fraction: float = 0.05
    high_threshold_tau: float | None = None
    high_threshold_coverage: int | None = None
    fixed_sweet_count: int | None = None
    fixed_sour_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observed_request, ObservedRequest):
            raise SensitivityStrategyError(
                "observed fiber control requires an ObservedRequest"
            )
        if self.observed_request.endpoint.model_family != "reference_fiber":
            raise SensitivityStrategyError(
                "observed fiber controls are defined for reference_fiber inputs"
            )
        if not isinstance(self.observed_result, ObservedResult):
            raise SensitivityStrategyError(
                "observed fiber control requires an ObservedResult"
            )
        if self.observed_result.source is not None:
            raise SensitivityStrategyError(
                "observed fiber controls cannot consume a resolved source"
            )
        _validate_peak_fraction(self.peak_fraction)
        high_values = (self.high_threshold_tau, self.high_threshold_coverage)
        if (high_values[0] is None) != (high_values[1] is None):
            raise SensitivityStrategyError(
                "high-threshold tau and coverage must be configured together"
            )
        if high_values[0] is not None and (
            not math.isfinite(float(high_values[0]))
            or float(high_values[0]) <= 0
            or type(high_values[1]) is not int
            or int(high_values[1]) < 1
        ):
            raise SensitivityStrategyError(
                "high-threshold tau and coverage must be positive"
            )
        fixed_values = (self.fixed_sweet_count, self.fixed_sour_count)
        if (fixed_values[0] is None) != (fixed_values[1] is None):
            raise SensitivityStrategyError(
                "fixed sweet and sour counts must be configured together"
            )
        if fixed_values[0] is not None and (
            type(fixed_values[0]) is not int
            or type(fixed_values[1]) is not int
            or int(fixed_values[0]) < 1
            or int(fixed_values[1]) < 1
        ):
            raise SensitivityStrategyError("fixed outer-library counts must be positive")


@dataclass(frozen=True, slots=True)
class FinalFiberControlRequest:
    """Diagnostic controls bound to one realized formal fiber final."""

    target: FinalSensitivityTarget
    peak_fraction: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.target, FinalSensitivityTarget):
            raise SensitivityStrategyError(
                "final fiber control target must be FinalSensitivityTarget"
            )
        if not self.target.final_model.endpoint.model_family.endswith("fiber"):
            raise SensitivityStrategyError(
                "final fiber controls require a normative-fiber final"
            )
        _validate_peak_fraction(self.peak_fraction)


def _validate_peak_fraction(value: float) -> float:
    fraction = float(value)
    if not math.isfinite(fraction) or not 0.0 < fraction <= 1.0:
        raise SensitivityStrategyError("peak_fraction must be finite and in (0, 1]")
    return fraction


def _plain_summaries(
    exposure: np.ndarray,
    *,
    tau: float,
    coverage: int,
    peak_fraction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    counts = coverage_counts(exposure, tau)
    candidate = candidate_mask(counts, coverage)
    if not np.any(candidate):
        raise SensitivityStrategyError("plain fiber control has an empty candidate set")
    selected = np.asarray(exposure[:, candidate], dtype=np.float64)
    touched = selected >= float(tau)
    touched_count = np.count_nonzero(touched, axis=1).astype(np.int64)
    exposure_sum = np.sum(selected, axis=1, dtype=np.float64)
    peak_count = max(1, int(np.ceil(peak_fraction * selected.shape[1])))
    peak = np.mean(
        np.partition(selected, selected.shape[1] - peak_count, axis=1)[
            :, -peak_count:
        ],
        axis=1,
    )
    return candidate, touched_count, exposure_sum, peak


def _fit_ols(outcome: np.ndarray, predictors: list[np.ndarray]) -> dict[str, object]:
    design = np.column_stack([np.ones(outcome.size), *predictors])
    if (
        outcome.size <= design.shape[1]
        or not np.all(np.isfinite(outcome))
        or not np.all(np.isfinite(design))
        or np.linalg.matrix_rank(design) != design.shape[1]
    ):
        return {"technical_status": "not_computable", "reason": "singular_design"}
    beta, *_ = np.linalg.lstsq(design, outcome, rcond=None)
    fitted = design @ beta
    residual = outcome - fitted
    sse = float(np.sum(residual**2))
    centered = outcome - np.mean(outcome)
    sst = float(np.sum(centered**2))
    r_squared = 1.0 - sse / sst if sst > 0 else math.nan
    return {
        "technical_status": "complete",
        "n_parameters": int(design.shape[1]),
        "r_squared": r_squared,
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "coefficients": beta.tolist(),
    }


def _full_nuisance_columns(
    target: FinalSensitivityTarget,
    array_provider: ScientificArrayProvider | None,
) -> list[np.ndarray]:
    request = target.observed_request
    columns = [
        materialize_vector(
            request.baseline,
            name="baseline",
            subject_axis=request.subject_axis,
            array_provider=array_provider,
        )
    ]
    if request.endpoint.model_family.startswith("addon_"):
        if request.branch == "delta_reference_adjusted":
            if len(request.nuisance_inputs) != 2:
                raise SensitivityStrategyError(
                    "adjusted final control requires full and fold DeltaReferenceScore"
                )
            columns.append(
                materialize_vector(
                    request.nuisance_inputs[0],
                    name="delta_reference_full",
                    subject_axis=request.subject_axis,
                    array_provider=array_provider,
                )
            )
        elif request.nuisance_inputs:
            raise SensitivityStrategyError(
                "no-delta final control cannot declare DeltaReferenceScore"
            )
    return columns


class ObservedFiberControlStrategy:
    """Publish outcome-independent controls without creating a final link."""

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

    def run(self, request: ObservedFiberControlRequest) -> SensitivityResult:
        if not isinstance(request, ObservedFiberControlRequest):
            raise TypeError("request must be an ObservedFiberControlRequest")
        observed = request.observed_request
        exposure = materialize_exposure(
            observed,
            array_provider=self.array_provider,
        )
        tau = float(observed.source_grid.pre_specified_tau)
        coverage = int(observed.source_grid.pre_specified_coverage)
        candidate, touched, exposure_sum, peak = _plain_summaries(
            exposure,
            tau=tau,
            coverage=coverage,
            peak_fraction=request.peak_fraction,
        )
        primary_cell = evaluate_observed_fiber_cell(
            observed,
            tau=tau,
            coverage=coverage,
            array_provider=self.array_provider,
        )
        high_threshold = None
        if request.high_threshold_tau is not None:
            high_threshold = evaluate_observed_fiber_cell(
                observed,
                tau=float(request.high_threshold_tau),
                coverage=int(request.high_threshold_coverage),
                array_provider=self.array_provider,
            ).as_payload()
        fixed_outer_library = None
        if request.fixed_sweet_count is not None:
            settings = observed.fiber_score_settings
            if settings is None:
                raise SensitivityStrategyError("fiber score settings are missing")
            fixed_settings = NormativeFiberScoreSettings(
                sweet_fraction=float(np.nextafter(0.0, 1.0)),
                sour_fraction=float(np.nextafter(0.0, 1.0)),
                weighted_peak_fraction=settings.weighted_peak_fraction,
                sweet_selected_min_count=int(request.fixed_sweet_count),
                sour_selected_min_count=int(request.fixed_sour_count),
                weighted_peak_min_count=settings.weighted_peak_min_count,
            )
            fixed_outer_library = evaluate_observed_fiber_cell(
                observed,
                tau=tau,
                coverage=coverage,
                array_provider=self.array_provider,
                score_settings=fixed_settings,
            ).as_payload()
        artifacts = (
            self.publisher.array(
                "observed_plain_touched_count.npy",
                touched,
                kind="observed_plain_fiber_touched_count",
                axes=(observed.subject_axis,),
                units="count",
                space=None,
            ),
            self.publisher.array(
                "observed_plain_exposure_sum.npy",
                exposure_sum,
                kind="observed_plain_fiber_exposure_sum",
                axes=(observed.subject_axis,),
                units="V/m",
                space=None,
            ),
            self.publisher.array(
                "observed_plain_peak_exposure.npy",
                peak,
                kind="observed_plain_fiber_peak_exposure",
                axes=(observed.subject_axis,),
                units="V/m",
                space=None,
            ),
        )
        payload = {
            "schema_version": "dual_frequency_observed_fiber_controls_v1",
            "target_id": observed.endpoint.identifier,
            "control_scope": "observed_pre_resolver",
            "tau": tau,
            "coverage": coverage,
            "peak_fraction": request.peak_fraction,
            "n_candidate_fibers": int(np.count_nonzero(candidate)),
            "touched_count_minimum": int(np.min(touched)),
            "touched_count_median": float(np.median(touched)),
            "touched_count_maximum": int(np.max(touched)),
            "primary_cell_diagnostic": primary_cell.as_payload(),
            "cheap_controls": {
                "high_threshold": (
                    high_threshold
                    if high_threshold is not None
                    else {
                        "technical_status": "not_applicable",
                        "reason": "not_configured",
                    }
                ),
                "fixed_outer_library": (
                    fixed_outer_library
                    if fixed_outer_library is not None
                    else {
                        "technical_status": "not_applicable",
                        "reason": "not_configured",
                    }
                ),
            },
            "input_diagnostic_artifact_ids": [
                artifact.identifier for artifact in request.observed_result.artifacts
            ],
        }
        return publish_sensitivity_payload(
            publisher=self.publisher,
            target_id=observed.endpoint.identifier,
            sensitivity_kind="observed_fiber_controls",
            filename="observed_fiber_controls.json",
            artifact_kind="observed_fiber_controls",
            payload=payload,
            extra_artifacts=artifacts,
        )


class FinalFiberControlStrategy:
    """Evaluate plain burden, signed increment, support, and collinearity QC."""

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

    def run(self, request: FinalFiberControlRequest) -> SensitivityResult:
        if not isinstance(request, FinalFiberControlRequest):
            raise TypeError("request must be a FinalFiberControlRequest")
        target = request.target
        observed = target.observed_request
        tau, coverage = selected_tau_coverage(target.final_model)
        exposure = materialize_target_exposure(
            target,
            array_provider=self.array_provider,
        )
        candidate, touched, exposure_sum, plain_peak = _plain_summaries(
            exposure,
            tau=tau,
            coverage=coverage,
            peak_fraction=request.peak_fraction,
        )
        evidence = evaluate_fixed_cell(
            target,
            tau=tau,
            coverage=coverage,
            array_provider=self.array_provider,
        )
        if evidence.full_scores is None:
            payload = {
                "schema_version": "dual_frequency_final_fiber_controls_v1",
                "target_id": target.final_model.identifier,
                "control_scope": "final_linked",
                "technical_status": "not_computable",
                "reason": evidence.reason,
                "selected_cell": evidence.as_payload(),
            }
            return publish_sensitivity_payload(
                publisher=self.publisher,
                target_id=target.final_model.identifier,
                sensitivity_kind="final_fiber_controls",
                filename="final_fiber_controls.json",
                artifact_kind="final_fiber_controls",
                payload=payload,
            )

        outcome = materialize_vector(
            observed.outcome,
            name="outcome",
            subject_axis=observed.subject_axis,
            array_provider=self.array_provider,
        )
        nuisance = _full_nuisance_columns(target, self.array_provider)
        models = {
            "nuisance_only": _fit_ols(outcome, nuisance),
            "plain_plus_nuisance": _fit_ols(outcome, [plain_peak, *nuisance]),
            "signed_plus_nuisance": _fit_ols(
                outcome,
                [evidence.full_scores, *nuisance],
            ),
            "joint": _fit_ols(
                outcome,
                [evidence.full_scores, plain_peak, *nuisance],
            ),
        }
        correlation, correlation_p = safe_correlation(
            evidence.full_scores,
            plain_peak,
            method="pearson",
        )
        nuisance_model = models["nuisance_only"]
        signed_model = models["signed_plus_nuisance"]
        plain_model = models["plain_plus_nuisance"]
        increments: dict[str, float | None] = {
            "signed_r_squared_increment": None,
            "plain_r_squared_increment": None,
        }
        if nuisance_model["technical_status"] == "complete":
            if signed_model["technical_status"] == "complete":
                increments["signed_r_squared_increment"] = float(
                    signed_model["r_squared"] - nuisance_model["r_squared"]
                )
            if plain_model["technical_status"] == "complete":
                increments["plain_r_squared_increment"] = float(
                    plain_model["r_squared"] - nuisance_model["r_squared"]
                )
        plain_similar_or_better = bool(
            signed_model["technical_status"] == "complete"
            and plain_model["technical_status"] == "complete"
            and (
                float(plain_model["mae"]) <= float(signed_model["mae"])
                or float(plain_model["rmse"]) <= float(signed_model["rmse"])
            )
        )
        payload = {
            "schema_version": "dual_frequency_final_fiber_controls_v1",
            "target_id": target.final_model.identifier,
            "control_scope": "final_linked",
            "technical_status": "complete",
            "tau": tau,
            "coverage": coverage,
            "peak_fraction": request.peak_fraction,
            "n_candidate_fibers": int(np.count_nonzero(candidate)),
            "touched_count_minimum": int(np.min(touched)),
            "touched_count_median": float(np.median(touched)),
            "touched_count_maximum": int(np.max(touched)),
            "plain_exposure_sum_mean": float(np.mean(exposure_sum)),
            "selected_cell_support": evidence.metrics,
            "models": models,
            "increments": increments,
            "selected_score_plain_peak_pearson_r": correlation,
            "selected_score_plain_peak_nominal_p": correlation_p,
            "collinearity_warning": (
                "not_computable"
                if not math.isfinite(correlation)
                else "acceptable"
                if abs(correlation) < 0.85
                else "high"
                if abs(correlation) < 0.95
                else "severe"
            ),
            "plain_similar_or_better_than_signed_score": plain_similar_or_better,
            "interpretation_burden_warning": bool(
                plain_similar_or_better
                or (math.isfinite(correlation) and abs(correlation) >= 0.95)
            ),
        }
        artifacts = (
            self.publisher.array(
                "final_plain_touched_count.npy",
                touched,
                kind="final_plain_fiber_touched_count",
                axes=(observed.subject_axis,),
                units="count",
                space=None,
            ),
            self.publisher.array(
                "final_plain_peak_exposure.npy",
                plain_peak,
                kind="final_plain_fiber_peak_exposure",
                axes=(observed.subject_axis,),
                units="V/m",
                space=None,
            ),
            self.publisher.array(
                "final_signed_scores.npy",
                evidence.full_scores,
                kind="final_fiber_control_signed_scores",
                axes=(observed.subject_axis,),
                units="V/m",
                space=None,
            ),
        )
        return publish_sensitivity_payload(
            publisher=self.publisher,
            target_id=target.final_model.identifier,
            sensitivity_kind="final_fiber_controls",
            filename="final_fiber_controls.json",
            artifact_kind="final_fiber_controls",
            payload=payload,
            extra_artifacts=artifacts,
        )


__all__ = [
    "FinalFiberControlRequest",
    "FinalFiberControlStrategy",
    "ObservedFiberControlRequest",
    "ObservedFiberControlStrategy",
]
