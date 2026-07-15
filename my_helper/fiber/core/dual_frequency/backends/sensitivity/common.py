"""Shared contracts and fixed-cell numerics for final-linked sensitivity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any, Protocol, runtime_checkable

import numpy as np

from ...contracts import (
    ArtifactRef,
    AxisRef,
    FinalModelRecord,
    NormativeFiberScoreSettings,
    ObservedRequest,
    SensitivityResult,
)
from ...contracts.requests import ScientificInput
from ...contracts.validation import classification_feedback_violation
from ..direct_voxel.kernel import evaluate_grid_cell_with_nuisance_plan
from ..normative_fiber.coverage import (
    candidate_mask,
    coverage_counts,
    heldout_fold_candidate_mask,
)
from ..normative_fiber.scoring import score_signed_fibers, score_support_fields
from ..nuisance import (
    NuisancePlan,
    NuisancePlanError,
    build_addon_nuisance_plan,
    build_gain_nuisance_plan,
)
from ..protocols import ArtifactPublisher
from ..statistics import (
    benefit_oriented_weights,
    linear_prediction,
    partial_spearman_weights,
    safe_correlation,
)


REALIZED_FINAL_STATUSES = frozenset(
    {"final_model_realized", "fallback_final_realized"}
)
NORMATIVE_FIBER_ID_ARTIFACT_KIND = "normative_fiber_valid_union_ids"
BRANCH_SENSITIVITY_SCOPES = frozenset(
    {"nonfinal_branch", "gain", "total_exposure"}
)

class SensitivityStrategyError(RuntimeError):
    """Raised when a sensitivity request violates its numerical contract."""


class ClassificationFeedbackError(SensitivityStrategyError):
    """Raised when a sensitivity payload attempts to mutate classification."""


@runtime_checkable
class ScientificArrayProvider(Protocol):
    """Materialize an immutable ArtifactRef without exposing a raw path."""

    def materialize(
        self,
        artifact: ArtifactRef,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None = None,
    ) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class FinalSensitivityTarget:
    """One realized final plus exact-axis observed inputs for sensitivity."""

    final_model: FinalModelRecord
    observed_request: ObservedRequest
    reference_overlap_mask: ScientificInput | None = None

    def __post_init__(self) -> None:
        _validate_final_model(self.final_model)
        validate_observed_against_final(
            self.final_model,
            self.observed_request,
            require_final_branch=True,
        )
        if self.reference_overlap_mask is not None:
            if not self.final_model.endpoint.model_family.startswith("addon_"):
                raise SensitivityStrategyError(
                    "reference_overlap_mask is defined only for add-on finals"
                )
            _require_artifact_input(
                self.reference_overlap_mask,
                "reference_overlap_mask",
                expected_axes=(
                    self.observed_request.subject_axis,
                    self.observed_request.feature_axis,
                ),
            )
            expected_shape = (
                self.observed_request.subject_axis.count,
                self.observed_request.feature_axis.count,
            )
            if (
                _input_shape(self.reference_overlap_mask, "reference_overlap_mask")
                != expected_shape
            ):
                raise SensitivityStrategyError(
                    f"reference_overlap_mask shape must be {expected_shape}"
                )
            try:
                is_boolean = (
                    np.dtype(self.reference_overlap_mask.dtype) == np.dtype(bool)
                )
            except TypeError:
                is_boolean = False
            if not is_boolean:
                raise SensitivityStrategyError(
                    "reference_overlap_mask artifact must declare bool dtype"
                )


@dataclass(frozen=True, slots=True)
class BranchSensitivityTarget:
    """Validated alternative analysis bound to one final target identity."""

    final_target: FinalSensitivityTarget
    observed_request: ObservedRequest
    analysis_scope: str

    def __post_init__(self) -> None:
        if not isinstance(self.final_target, FinalSensitivityTarget):
            raise SensitivityStrategyError(
                "branch sensitivity requires a FinalSensitivityTarget"
            )
        if not self.final_target.final_model.endpoint.model_family.startswith(
            "addon_"
        ):
            raise SensitivityStrategyError(
                "branch sensitivity is defined only for add-on finals"
            )
        scope = str(self.analysis_scope).strip()
        if scope not in BRANCH_SENSITIVITY_SCOPES:
            raise SensitivityStrategyError(
                f"unsupported branch sensitivity scope {scope!r}"
            )
        object.__setattr__(self, "analysis_scope", scope)
        validate_observed_against_final(
            self.final_target.final_model,
            self.observed_request,
            require_final_branch=False,
        )
        validate_observed_identity(
            self.final_target.observed_request,
            self.observed_request,
        )
        if scope == "nonfinal_branch":
            final_key = self.final_target.final_model.final_key
            if final_key is None or self.observed_request.branch == final_key.final_branch:
                raise SensitivityStrategyError(
                    "nonfinal branch sensitivity must identify the non-realized branch"
                )

    @property
    def final_model(self) -> FinalModelRecord:
        return self.final_target.final_model

    @property
    def reference_overlap_mask(self) -> ScientificInput | None:
        if self.analysis_scope == "total_exposure":
            return None
        return self.final_target.reference_overlap_mask


SensitivityTarget = FinalSensitivityTarget | BranchSensitivityTarget


@dataclass(frozen=True, slots=True)
class FixedCellEvidence:
    """Classification-free fixed-cell metrics and optional full-sample scores."""

    technical_status: str
    tau: float
    coverage: int
    metrics: Mapping[str, Any]
    full_scores: np.ndarray | None
    reason: str | None = None

    def __post_init__(self) -> None:
        status = str(self.technical_status).strip()
        if status not in {"complete", "not_computable"}:
            raise SensitivityStrategyError("unsupported fixed-cell technical status")
        object.__setattr__(self, "technical_status", status)
        tau = float(self.tau)
        if not math.isfinite(tau) or tau <= 0:
            raise SensitivityStrategyError("fixed-cell tau must be finite and positive")
        object.__setattr__(self, "tau", tau)
        if type(self.coverage) is not int or self.coverage < 1:
            raise SensitivityStrategyError("fixed-cell coverage must be positive")
        metrics = dict(self.metrics)
        validate_no_classification_feedback(metrics)
        object.__setattr__(self, "metrics", metrics)
        if self.full_scores is not None:
            scores = np.asarray(self.full_scores, dtype=np.float64)
            if scores.ndim != 1 or not np.all(np.isfinite(scores)):
                raise SensitivityStrategyError(
                    "fixed-cell scores must be a finite subject vector"
                )
            scores = np.array(scores, copy=True)
            scores.flags.writeable = False
            object.__setattr__(self, "full_scores", scores)
        if self.reason is not None:
            reason = str(self.reason).strip()
            if not reason:
                raise SensitivityStrategyError("fixed-cell reason must be nonempty")
            object.__setattr__(self, "reason", reason)

    def as_payload(self) -> dict[str, Any]:
        return {
            "technical_status": self.technical_status,
            "tau": self.tau,
            "coverage": self.coverage,
            "metrics": _json_safe(self.metrics),
            "reason": self.reason,
        }


def _validate_scientific_input(value: object, name: str) -> None:
    if not isinstance(value, (np.ndarray, ArtifactRef)):
        raise SensitivityStrategyError(
            f"{name} must be a NumPy array or ArtifactRef; paths are not accepted"
        )
    if isinstance(value, np.ndarray) and value.dtype == object:
        raise SensitivityStrategyError(f"{name} cannot use object dtype")


def _require_artifact_input(
    value: object,
    name: str,
    *,
    expected_axes: tuple[AxisRef, ...],
) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise SensitivityStrategyError(
            f"final-linked {name} must be an immutable ArtifactRef"
        )
    if value.axis_refs != expected_axes:
        raise SensitivityStrategyError(
            f"final-linked {name} artifact axes must exactly match the request"
        )
    expected_shape = tuple(axis.count for axis in expected_axes)
    if value.shape != expected_shape:
        raise SensitivityStrategyError(
            f"final-linked {name} shape must be {expected_shape}"
        )
    return value


def _validate_final_linked_scientific_inputs(
    observed_request: ObservedRequest,
) -> None:
    subject_axis = observed_request.subject_axis
    feature_axis = observed_request.feature_axis
    _require_artifact_input(
        observed_request.exposure,
        "exposure",
        expected_axes=(subject_axis, feature_axis),
    )
    _require_artifact_input(
        observed_request.outcome,
        "outcome",
        expected_axes=(subject_axis,),
    )
    _require_artifact_input(
        observed_request.baseline,
        "baseline",
        expected_axes=(subject_axis,),
    )
    for index, value in enumerate(observed_request.nuisance_inputs):
        if not isinstance(value, ArtifactRef):
            raise SensitivityStrategyError(
                "final-linked nuisance_inputs "
                f"must contain only immutable ArtifactRef values; index {index} is invalid"
            )
        if value.shape is None or len(value.shape) not in {1, 2}:
            raise SensitivityStrategyError(
                f"final-linked nuisance_inputs[{index}] must be one- or two-dimensional"
            )
        expected_axes = (subject_axis,) * len(value.shape)
        _require_artifact_input(
            value,
            f"nuisance_inputs[{index}]",
            expected_axes=expected_axes,
        )


def _input_shape(value: ScientificInput, name: str) -> tuple[int, ...]:
    shape = value.shape
    if shape is None:
        raise SensitivityStrategyError(f"{name} must reference an array artifact")
    return tuple(int(dimension) for dimension in shape)


def _validate_final_model(final_model: object) -> FinalModelRecord:
    if not isinstance(final_model, FinalModelRecord):
        raise SensitivityStrategyError(
            "final-linked sensitivity requires a FinalModelRecord"
        )
    if final_model.final_status not in REALIZED_FINAL_STATUSES:
        raise SensitivityStrategyError(
            "final-linked sensitivity requires a realized final model"
        )
    try:
        axis = final_model.valid_feature_axis.axis
    except (AttributeError, ValueError) as exc:
        raise SensitivityStrategyError(
            "final-linked sensitivity requires an exact valid feature axis"
        ) from exc
    if not isinstance(axis, AxisRef):
        raise SensitivityStrategyError(
            "final-linked sensitivity requires an exact valid feature axis"
        )
    return final_model


def _selected_final_source(final_model: FinalModelRecord):
    source = final_model.selected_source
    if source is None and final_model.selected_branch is not None:
        source = final_model.selected_branch.source
    if source is None:
        raise SensitivityStrategyError("realized final has no selected source")
    return source


def _final_fiber_id_artifact(final_model: FinalModelRecord) -> ArtifactRef:
    source = _selected_final_source(final_model)
    matches = tuple(
        artifact
        for artifact in source.artifacts
        if artifact.kind == NORMATIVE_FIBER_ID_ARTIFACT_KIND
    )
    if len(matches) != 1:
        raise SensitivityStrategyError(
            "normative-fiber final source must contain exactly one "
            f"{NORMATIVE_FIBER_ID_ARTIFACT_KIND} artifact"
        )
    artifact = matches[0]
    expected_axis = final_model.valid_feature_axis.axis
    if artifact.axis_refs != (expected_axis,) or artifact.shape != (
        expected_axis.count,
    ):
        raise SensitivityStrategyError(
            "normative-fiber final ID artifact must bind the locked feature axis"
        )
    return artifact


def _validate_final_fiber_id_identity(
    final_model: FinalModelRecord,
    observed_request: ObservedRequest,
) -> None:
    if not final_model.endpoint.model_family.endswith("fiber"):
        return
    expected = _final_fiber_id_artifact(final_model)
    if not isinstance(observed_request.feature_ids, ArtifactRef):
        raise SensitivityStrategyError(
            "final-linked normative-fiber feature_ids must be an ArtifactRef"
        )
    if observed_request.feature_ids != expected:
        raise SensitivityStrategyError(
            "normative-fiber feature_ids must equal the selected final source ID artifact"
        )


def validate_observed_identity(
    reference: ObservedRequest,
    candidate: ObservedRequest,
) -> None:
    """Require exact ordered subject, feature, and fiber-ID scientific identity."""

    if candidate.subject_axis != reference.subject_axis:
        raise SensitivityStrategyError(
            "sensitivity subject axis must equal the final target subject axis"
        )
    if candidate.feature_axis != reference.feature_axis:
        raise SensitivityStrategyError(
            "sensitivity feature axis must equal the final target feature axis"
        )
    _validate_final_linked_scientific_inputs(candidate)
    if reference.endpoint.model_family.endswith("fiber"):
        if not isinstance(reference.feature_ids, ArtifactRef) or not isinstance(
            candidate.feature_ids,
            ArtifactRef,
        ):
            raise SensitivityStrategyError(
                "normative-fiber identity requires immutable feature-ID artifacts"
            )
        if candidate.feature_ids != reference.feature_ids:
            raise SensitivityStrategyError(
                "normative-fiber ordered feature-ID identity must remain unchanged"
            )


def validate_observed_against_final(
    final_model: FinalModelRecord,
    observed_request: ObservedRequest,
    *,
    require_final_branch: bool,
) -> None:
    """Validate endpoint, role, and exact axes without invoking a resolver."""

    _validate_final_model(final_model)
    if not isinstance(observed_request, ObservedRequest):
        raise SensitivityStrategyError("observed_request must be an ObservedRequest")
    _validate_final_linked_scientific_inputs(observed_request)
    if observed_request.endpoint != final_model.endpoint:
        raise SensitivityStrategyError(
            "sensitivity observed endpoint must equal the final endpoint"
        )
    if observed_request.feature_axis != final_model.valid_feature_axis.axis:
        raise SensitivityStrategyError(
            "sensitivity feature axis must equal final.valid_feature_axis"
        )
    family = final_model.endpoint.model_family
    if family.endswith("fiber"):
        if observed_request.connectome_role != "formal":
            raise SensitivityStrategyError(
                "final-linked normative-fiber sensitivity requires the formal connectome"
            )
    elif observed_request.connectome_role != "none":
        raise SensitivityStrategyError(
            "final-linked direct-voxel sensitivity cannot declare a connectome"
        )
    if require_final_branch:
        final_key = final_model.final_key
        if final_key is None or observed_request.branch != final_key.final_branch:
            raise SensitivityStrategyError(
                "sensitivity observed branch must equal the realized final branch"
            )
    _validate_final_fiber_id_identity(final_model, observed_request)


def _materialize(
    value: ScientificInput,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    expected_space: str | None,
    array_provider: ScientificArrayProvider | None,
) -> np.ndarray:
    _validate_scientific_input(value, name)
    expected_shape = tuple(axis.count for axis in expected_axes)
    if _input_shape(value, name) != expected_shape:
        raise SensitivityStrategyError(f"{name} shape must be {expected_shape}")
    if isinstance(value, np.ndarray):
        return np.asanyarray(value)
    if value.axis_refs != expected_axes:
        raise SensitivityStrategyError(f"{name} artifact axes do not match the request")
    if value.dtype is None:
        raise SensitivityStrategyError(f"{name} artifact must declare a dtype")
    if value.units != expected_units or value.space != expected_space:
        raise SensitivityStrategyError(
            f"{name} artifact units or space do not match the request"
        )
    if array_provider is None or not isinstance(array_provider, ScientificArrayProvider):
        raise SensitivityStrategyError(
            f"{name} is artifact-backed but no ScientificArrayProvider was injected"
        )
    return np.asanyarray(
        array_provider.materialize(
            value,
            expected_dtype=value.dtype,
            expected_shape=expected_shape,
            expected_axes=expected_axes,
            expected_units=expected_units,
            expected_space=expected_space,
            mmap_mode="r",
        )
    )


def materialize_vector(
    value: ScientificInput,
    *,
    name: str,
    subject_axis: AxisRef,
    array_provider: ScientificArrayProvider | None,
) -> np.ndarray:
    units = value.units if isinstance(value, ArtifactRef) else None
    space = value.space if isinstance(value, ArtifactRef) else None
    array = _materialize(
        value,
        name=name,
        expected_axes=(subject_axis,),
        expected_units=units,
        expected_space=space,
        array_provider=array_provider,
    )
    output = np.asarray(array, dtype=np.float64)
    if output.shape != (subject_axis.count,) or not np.all(np.isfinite(output)):
        raise SensitivityStrategyError(f"{name} must be a finite subject vector")
    return output


def materialize_exposure(
    request: ObservedRequest,
    *,
    value: ScientificInput | None = None,
    name: str = "exposure",
    array_provider: ScientificArrayProvider | None,
) -> np.ndarray:
    scientific_input = request.exposure if value is None else value
    array = _materialize(
        scientific_input,
        name=name,
        expected_axes=(request.subject_axis, request.feature_axis),
        expected_units=request.exposure_units,
        expected_space=request.exposure_space,
        array_provider=array_provider,
    )
    output = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(output)):
        raise SensitivityStrategyError(f"{name} must contain only finite values")
    return output


def _materialize_nuisance_inputs(
    request: ObservedRequest,
    array_provider: ScientificArrayProvider | None,
) -> tuple[np.ndarray, ...]:
    output: list[np.ndarray] = []
    for index, value in enumerate(request.nuisance_inputs):
        if isinstance(value, np.ndarray):
            array = np.asarray(value, dtype=np.float64)
            if (
                array.ndim not in {1, 2}
                or array.shape[0] != request.subject_axis.count
                or not np.all(np.isfinite(array))
            ):
                raise SensitivityStrategyError(
                    f"nuisance_inputs[{index}] must be finite and subject-major"
                )
            output.append(array)
            continue
        axes = value.axis_refs
        units = value.units if isinstance(value, ArtifactRef) else None
        space = value.space if isinstance(value, ArtifactRef) else None
        array = _materialize(
            value,
            name=f"nuisance_inputs[{index}]",
            expected_axes=axes,
            expected_units=units,
            expected_space=space,
            array_provider=array_provider,
        )
        output.append(np.asarray(array, dtype=np.float64))
    return tuple(output)


def _reference_nuisance_plan(
    baseline: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
) -> NuisancePlan:
    columns: list[np.ndarray] = [baseline[:, None]]
    for index, value in enumerate(nuisance_inputs):
        array = np.asarray(value, dtype=np.float64)
        if array.ndim == 1:
            array = array[:, None]
        if array.ndim != 2 or array.shape[0] != baseline.size:
            raise SensitivityStrategyError(
                f"nuisance_inputs[{index}] must be subject-major"
            )
        columns.append(array)
    full = np.column_stack(columns)
    if not np.all(np.isfinite(full)):
        raise SensitivityStrategyError("nuisance design must be finite")
    folds = np.broadcast_to(full, (baseline.size, *full.shape)).copy()
    return NuisancePlan(full_covariates=full, fold_covariates=folds)


def _nuisance_plan(
    request: ObservedRequest,
    array_provider: ScientificArrayProvider | None,
    *,
    analysis_scope: str,
) -> tuple[np.ndarray, NuisancePlan]:
    outcome = materialize_vector(
        request.outcome,
        name="outcome",
        subject_axis=request.subject_axis,
        array_provider=array_provider,
    )
    nuisance_inputs = _materialize_nuisance_inputs(request, array_provider)
    if request.endpoint.model_family.startswith("addon_"):
        delta_full = delta_folds = None
        if request.branch == "delta_reference_adjusted":
            if len(nuisance_inputs) != 2:
                raise SensitivityStrategyError(
                    "adjusted sensitivity requires full and fold DeltaReferenceScore inputs"
                )
            delta_full, delta_folds = nuisance_inputs
        elif request.branch == "no_delta_reference":
            if nuisance_inputs:
                raise SensitivityStrategyError(
                    "no-delta sensitivity cannot declare DeltaReferenceScore inputs"
                )
        else:
            raise SensitivityStrategyError("unsupported add-on sensitivity branch")
        try:
            if analysis_scope == "gain":
                plan = build_gain_nuisance_plan(
                    request.subject_axis.count,
                    request.branch,
                    delta_full_scores=delta_full,
                    delta_fold_scores=delta_folds,
                )
            else:
                baseline = materialize_vector(
                    request.baseline,
                    name="baseline",
                    subject_axis=request.subject_axis,
                    array_provider=array_provider,
                )
                plan = build_addon_nuisance_plan(
                    baseline,
                    request.branch,
                    delta_full_scores=delta_full,
                    delta_fold_scores=delta_folds,
                )
        except NuisancePlanError as exc:
            raise SensitivityStrategyError(f"{exc.status}:{exc.detail}") from exc
        return outcome, plan
    baseline = materialize_vector(
        request.baseline,
        name="baseline",
        subject_axis=request.subject_axis,
        array_provider=array_provider,
    )
    return outcome, _reference_nuisance_plan(baseline, nuisance_inputs)


def _apply_reference_overlap(
    exposure: np.ndarray,
    target: SensitivityTarget,
    array_provider: ScientificArrayProvider | None,
) -> np.ndarray:
    if target.reference_overlap_mask is None:
        return exposure
    mask_input = target.reference_overlap_mask
    mask = _materialize(
        mask_input,
        name="reference_overlap_mask",
        expected_axes=(
            target.observed_request.subject_axis,
            target.observed_request.feature_axis,
        ),
        expected_units=(mask_input.units if isinstance(mask_input, ArtifactRef) else None),
        expected_space=(mask_input.space if isinstance(mask_input, ArtifactRef) else None),
        array_provider=array_provider,
    )
    if np.asarray(mask).dtype != np.dtype(bool):
        raise SensitivityStrategyError("reference_overlap_mask must be boolean")
    return np.where(np.asarray(mask, dtype=bool), 0.0, exposure)


def materialize_target_exposure(
    target: SensitivityTarget,
    *,
    array_provider: ScientificArrayProvider | None = None,
) -> np.ndarray:
    """Materialize a target exposure and apply its declared overlap exclusion."""

    if not isinstance(target, (FinalSensitivityTarget, BranchSensitivityTarget)):
        raise SensitivityStrategyError("target must be a validated sensitivity target")
    exposure = materialize_exposure(
        target.observed_request,
        array_provider=array_provider,
    )
    return _apply_reference_overlap(exposure, target, array_provider)


def _direct_cell(
    target: SensitivityTarget,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    tau: float,
    coverage: int,
) -> FixedCellEvidence:
    request = target.observed_request
    computation = evaluate_grid_cell_with_nuisance_plan(
        exposure,
        outcome,
        nuisance_plan,
        request.outcome_direction,
        float(tau),
        coverage,
        request.hard_computability,
        retain_arrays=True,
    )
    metrics = computation.metrics.as_json_dict()
    metrics["tau"] = float(tau)
    metrics.pop("prediction_status", None)
    if computation.arrays is None:
        reasons = metrics.get("failure_reasons") or ["fixed_cell_not_computable"]
        return FixedCellEvidence(
            technical_status="not_computable",
            tau=tau,
            coverage=coverage,
            metrics=metrics,
            full_scores=None,
            reason=";".join(str(value) for value in reasons),
        )
    return FixedCellEvidence(
        technical_status="complete",
        tau=tau,
        coverage=coverage,
        metrics=metrics,
        full_scores=computation.arrays.full_scores,
    )


def _finite_feature_weights(
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance: np.ndarray,
    rows: np.ndarray,
    eligible: np.ndarray,
    outcome_direction: str,
) -> np.ndarray:
    weights = np.full(exposure.shape[1], np.nan, dtype=np.float64)
    if not np.any(eligible):
        return weights
    coefficients = partial_spearman_weights(
        outcome[rows],
        exposure[rows][:, eligible],
        nuisance[rows],
    )
    weights[eligible] = benefit_oriented_weights(coefficients, outcome_direction)
    return weights


def _prediction_metrics(
    outcome: np.ndarray,
    predictions: np.ndarray,
    baseline_predictions: np.ndarray,
) -> dict[str, float | None]:
    finite_model = np.isfinite(predictions)
    finite_baseline = np.isfinite(baseline_predictions)
    model_error = outcome[finite_model] - predictions[finite_model]
    baseline_error = outcome[finite_baseline] - baseline_predictions[finite_baseline]
    mae_model = float(np.mean(np.abs(model_error))) if model_error.size else math.nan
    rmse_model = float(np.sqrt(np.mean(model_error**2))) if model_error.size else math.nan
    mae_baseline = (
        float(np.mean(np.abs(baseline_error))) if baseline_error.size else math.nan
    )
    rmse_baseline = (
        float(np.sqrt(np.mean(baseline_error**2))) if baseline_error.size else math.nan
    )
    joint = finite_model & finite_baseline
    q2 = math.nan
    if np.any(joint):
        sse_model = float(np.sum((outcome[joint] - predictions[joint]) ** 2))
        sse_baseline = float(
            np.sum((outcome[joint] - baseline_predictions[joint]) ** 2)
        )
        if sse_baseline > 0:
            q2 = 1.0 - sse_model / sse_baseline
    spearman, spearman_p = safe_correlation(outcome, predictions, method="spearman")
    pearson, pearson_p = safe_correlation(outcome, predictions, method="pearson")
    return {
        "loocv_spearman_rho": spearman,
        "loocv_spearman_nominal_p": spearman_p,
        "loocv_pearson_r": pearson,
        "loocv_pearson_nominal_p": pearson_p,
        "q2": q2,
        "mae_model": mae_model,
        "mae_baseline": mae_baseline,
        "rmse_model": rmse_model,
        "rmse_baseline": rmse_baseline,
    }


def _fiber_cell(
    request: ObservedRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    tau: float,
    coverage: int,
    array_provider: ScientificArrayProvider | None,
    *,
    score_settings: NormativeFiberScoreSettings | None = None,
) -> FixedCellEvidence:
    settings = request.fiber_score_settings if score_settings is None else score_settings
    feature_ids_input = request.feature_ids
    if settings is None or feature_ids_input is None:
        raise SensitivityStrategyError(
            "normative-fiber sensitivity requires score settings and feature IDs"
        )
    feature_ids = _materialize(
        feature_ids_input,
        name="feature_ids",
        expected_axes=(request.feature_axis,),
        expected_units=(
            feature_ids_input.units if isinstance(feature_ids_input, ArtifactRef) else None
        ),
        expected_space=(
            feature_ids_input.space if isinstance(feature_ids_input, ArtifactRef) else None
        ),
        array_provider=array_provider,
    )
    feature_ids = np.asarray(feature_ids, dtype=np.int64)
    counts = coverage_counts(exposure, tau)
    full_candidate = candidate_mask(counts, coverage)
    if not np.any(full_candidate):
        return FixedCellEvidence(
            technical_status="not_computable",
            tau=tau,
            coverage=coverage,
            metrics={"n_candidate_full": 0},
            full_scores=None,
            reason="empty_full_sample_candidate_set",
        )

    n_subjects = outcome.size
    subjects = np.arange(n_subjects, dtype=np.int64)
    full_weights = _finite_feature_weights(
        exposure,
        outcome,
        nuisance_plan.full_covariates,
        subjects,
        full_candidate,
        request.outcome_direction,
    )
    full_score = score_signed_fibers(
        exposure,
        full_weights,
        feature_ids,
        settings,
        candidate_mask=full_candidate,
    )
    if full_score.fiber_score_support_status == "absent_no_valid_signed_fibers":
        return FixedCellEvidence(
            technical_status="not_computable",
            tau=tau,
            coverage=coverage,
            metrics={
                "n_candidate_full": int(np.count_nonzero(full_candidate)),
                **score_support_fields(full_score, settings),
            },
            full_scores=None,
            reason="absent_valid_signed_fibers",
        )

    predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    baseline_predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    fold_candidate_counts: list[int] = []
    fold_valid_counts: list[int] = []
    fold_support_statuses: list[str] = []
    score_nonconstant = True
    for heldout in range(n_subjects):
        train = np.delete(subjects, heldout)
        fold_candidate = heldout_fold_candidate_mask(
            exposure,
            counts,
            heldout,
            tau,
            coverage,
        )
        fold_candidate_counts.append(int(np.count_nonzero(fold_candidate)))
        fold_weights = _finite_feature_weights(
            exposure,
            outcome,
            nuisance_plan.fold_covariates[heldout],
            train,
            fold_candidate,
            request.outcome_direction,
        )
        fold_valid_counts.append(
            int(np.count_nonzero(fold_candidate & np.isfinite(fold_weights)))
        )
        fold_score = score_signed_fibers(
            exposure,
            fold_weights,
            feature_ids,
            settings,
            candidate_mask=fold_candidate,
        )
        fold_support_statuses.append(fold_score.fiber_score_support_status)
        if fold_score.fiber_score_support_status == "absent_no_valid_signed_fibers":
            score_nonconstant = False
            continue
        training_score = fold_score.net_score[train]
        if not np.all(np.isfinite(training_score)) or np.std(training_score) == 0:
            score_nonconstant = False
            continue
        prediction, _ = linear_prediction(
            outcome[train],
            training_score,
            nuisance_plan.fold_covariates[heldout, train],
            fold_score.net_score[[heldout]],
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        baseline_prediction, _ = linear_prediction(
            outcome[train],
            None,
            nuisance_plan.fold_covariates[heldout, train],
            None,
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        predictions[heldout] = prediction[0]
        baseline_predictions[heldout] = baseline_prediction[0]

    fold_candidates = np.asarray(fold_candidate_counts, dtype=np.int64)
    fold_valid = np.asarray(fold_valid_counts, dtype=np.int64)
    all_predictions_finite = bool(
        np.all(np.isfinite(predictions))
        and np.all(np.isfinite(baseline_predictions))
    )
    fold_minimum = request.hard_computability.fold_n_features_min
    if fold_minimum is None:
        raise SensitivityStrategyError(
            "normative-fiber sensitivity requires a fold candidate minimum"
        )
    passes_signed_support = all(
        status != "absent_no_valid_signed_fibers"
        for status in fold_support_statuses
    )
    metrics: dict[str, Any] = {
        "n_subjects": n_subjects,
        "n_candidate_full": int(np.count_nonzero(full_candidate)),
        "n_valid_full_features": int(
            np.count_nonzero(full_candidate & np.isfinite(full_weights))
        ),
        "fold_n_candidate_features_min": int(np.min(fold_candidates)),
        "fold_n_candidate_features_median": float(np.median(fold_candidates)),
        "fold_n_candidate_features_max": int(np.max(fold_candidates)),
        "fold_n_valid_features_min": int(np.min(fold_valid)),
        "fold_n_valid_features_median": float(np.median(fold_valid)),
        "fold_n_valid_features_max": int(np.max(fold_valid)),
        "score_nonconstant_all_folds": score_nonconstant,
        "all_predictions_finite": all_predictions_finite,
        "passes_n_subjects": n_subjects
        >= request.hard_computability.n_subjects_min,
        "passes_fold_n_features_min": int(np.min(fold_candidates)) >= fold_minimum,
        "passes_signed_support": passes_signed_support,
        **score_support_fields(full_score, settings),
        **_prediction_metrics(outcome, predictions, baseline_predictions),
    }
    metrics["passes_hard_computability"] = bool(
        metrics["passes_n_subjects"]
        and metrics["passes_fold_n_features_min"]
        and passes_signed_support
        and score_nonconstant
        and all_predictions_finite
    )
    return FixedCellEvidence(
        technical_status="complete",
        tau=tau,
        coverage=coverage,
        metrics=metrics,
        full_scores=full_score.net_score,
    )


def evaluate_fixed_cell(
    target: SensitivityTarget,
    *,
    tau: float,
    coverage: int,
    array_provider: ScientificArrayProvider | None = None,
) -> FixedCellEvidence:
    """Evaluate one exact-axis cell without source resolution or dose thresholding."""

    if not isinstance(target, (FinalSensitivityTarget, BranchSensitivityTarget)):
        raise SensitivityStrategyError("target must be a validated sensitivity target")
    request = target.observed_request
    exposure = materialize_target_exposure(
        target,
        array_provider=array_provider,
    )
    analysis_scope = (
        target.analysis_scope
        if isinstance(target, BranchSensitivityTarget)
        else "final"
    )
    outcome, nuisance_plan = _nuisance_plan(
        request,
        array_provider,
        analysis_scope=analysis_scope,
    )
    if request.endpoint.model_family.endswith("voxel"):
        return _direct_cell(target, exposure, outcome, nuisance_plan, tau, coverage)
    return _fiber_cell(
        request,
        exposure,
        outcome,
        nuisance_plan,
        tau,
        coverage,
        array_provider,
    )


def evaluate_observed_fiber_cell(
    observed_request: ObservedRequest,
    *,
    tau: float,
    coverage: int,
    array_provider: ScientificArrayProvider | None = None,
    score_settings: NormativeFiberScoreSettings | None = None,
) -> FixedCellEvidence:
    """Evaluate one pre-resolver fiber cell without creating a final link."""

    if not isinstance(observed_request, ObservedRequest):
        raise SensitivityStrategyError("observed_request must be an ObservedRequest")
    if not observed_request.endpoint.model_family.endswith("fiber"):
        raise SensitivityStrategyError(
            "observed fiber controls require a normative-fiber request"
        )
    if observed_request.connectome_role not in {"formal", "sensitive"}:
        raise SensitivityStrategyError(
            "observed fiber controls require a configured connectome role"
        )
    exposure = materialize_exposure(
        observed_request,
        array_provider=array_provider,
    )
    outcome, nuisance_plan = _nuisance_plan(
        observed_request,
        array_provider,
        analysis_scope="observed",
    )
    return _fiber_cell(
        observed_request,
        exposure,
        outcome,
        nuisance_plan,
        tau,
        coverage,
        array_provider,
        score_settings=score_settings,
    )


def target_for_alternative_request(
    final_target: FinalSensitivityTarget,
    observed_request: ObservedRequest,
    *,
    analysis_scope: str,
) -> BranchSensitivityTarget:
    """Bind an alternative add-on analysis to a final axis without branch promotion."""

    return BranchSensitivityTarget(
        final_target=final_target,
        observed_request=observed_request,
        analysis_scope=analysis_scope,
    )


def selected_tau_coverage(final_model: FinalModelRecord) -> tuple[float, int]:
    _validate_final_model(final_model)
    if final_model.final_key is None:
        raise SensitivityStrategyError("realized final has no FinalModelKey")
    return (
        float(final_model.final_key.selected_tau),
        int(final_model.final_key.selected_coverage),
    )


def validate_no_classification_feedback(value: object, *, location: str = "payload") -> None:
    """Recursively reject classification keys and values from sensitivity output."""

    violation = classification_feedback_violation(value, location=location)
    if violation is not None:
        raise ClassificationFeedbackError(violation)


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


def publish_sensitivity_payload(
    *,
    publisher: ArtifactPublisher,
    target_id: str,
    sensitivity_kind: str,
    filename: str,
    artifact_kind: str,
    payload: Mapping[str, Any],
    extra_artifacts: tuple[ArtifactRef, ...] = (),
) -> SensitivityResult:
    """Validate and publish classification-free sensitivity evidence."""

    if not isinstance(publisher, ArtifactPublisher):
        raise TypeError("publisher must implement ArtifactPublisher")
    clean_payload = _json_safe(payload)
    validate_no_classification_feedback(clean_payload)
    document = publisher.document(
        filename,
        clean_payload,
        kind=artifact_kind,
    )
    artifacts = tuple(extra_artifacts) + (document,)
    if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
        raise SensitivityStrategyError("published sensitivity artifacts are invalid")
    return SensitivityResult(
        target_id=str(target_id),
        sensitivity_kind=str(sensitivity_kind),
        artifacts=artifacts,
    )


__all__ = [
    "BRANCH_SENSITIVITY_SCOPES",
    "BranchSensitivityTarget",
    "ClassificationFeedbackError",
    "FinalSensitivityTarget",
    "FixedCellEvidence",
    "ScientificArrayProvider",
    "SensitivityStrategyError",
    "evaluate_fixed_cell",
    "evaluate_observed_fiber_cell",
    "materialize_exposure",
    "materialize_target_exposure",
    "materialize_vector",
    "publish_sensitivity_payload",
    "selected_tau_coverage",
    "target_for_alternative_request",
    "validate_no_classification_feedback",
    "validate_observed_against_final",
    "validate_observed_identity",
]
