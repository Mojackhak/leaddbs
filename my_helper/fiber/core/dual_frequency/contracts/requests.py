"""Typed array-or-artifact requests for scientific backends."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import numpy as np

from .identity import EndpointKey
from .records import (
    ArtifactRef,
    AxisRef,
    FinalModelRecord,
    SensitiveRecord,
    SourceRecord,
)


ScientificInput: TypeAlias = np.ndarray | ArtifactRef


class RequestError(ValueError):
    """Raised when a backend request contains an unresolved or unsafe input."""


def _scientific_input(value: object, field: str) -> ScientificInput:
    if isinstance(value, (str, Path)):
        raise RequestError(f"{field} cannot be a raw path or filename")
    if not isinstance(value, (np.ndarray, ArtifactRef)):
        raise RequestError(f"{field} must be a NumPy array or ArtifactRef")
    if isinstance(value, np.ndarray) and value.dtype == object:
        raise RequestError(f"{field} cannot use object dtype")
    return value


def _inputs(values: tuple[ScientificInput, ...], field: str) -> tuple[ScientificInput, ...]:
    output = tuple(values)
    for index, value in enumerate(output):
        _scientific_input(value, f"{field}[{index}]")
    return output


def _shape(value: ScientificInput, field: str) -> tuple[int, ...]:
    shape = value.shape if isinstance(value, np.ndarray) else value.shape
    if shape is None:
        raise RequestError(f"{field} must reference an array artifact")
    return tuple(int(dimension) for dimension in shape)


def _require_artifact_axes(
    value: ScientificInput,
    field: str,
    expected_axes: tuple[AxisRef, ...],
) -> None:
    if isinstance(value, ArtifactRef) and value.axis_refs != expected_axes:
        raise RequestError(f"{field} artifact axes do not match the declared request axes")


def _validate_vector(value: ScientificInput, field: str, subject_axis: AxisRef) -> None:
    expected_shape = (subject_axis.count,)
    if _shape(value, field) != expected_shape:
        raise RequestError(f"{field} shape must be {expected_shape}")
    _require_artifact_axes(value, field, (subject_axis,))


def _validate_exposure(
    value: ScientificInput,
    field: str,
    subject_axis: AxisRef,
    feature_axis: AxisRef,
) -> None:
    expected_shape = (subject_axis.count, feature_axis.count)
    if _shape(value, field) != expected_shape:
        raise RequestError(f"{field} shape must be {expected_shape}")
    _require_artifact_axes(value, field, (subject_axis, feature_axis))


def _validate_nuisance(value: ScientificInput, field: str, subject_axis: AxisRef) -> None:
    shape = _shape(value, field)
    if not shape or shape[0] != subject_axis.count or len(shape) > 2:
        raise RequestError(f"{field} must be subject-major and one- or two-dimensional")
    if isinstance(value, ArtifactRef) and value.axis_refs[0] != subject_axis:
        raise RequestError(f"{field} artifact subject axis does not match the declared request axis")


@dataclass(frozen=True)
class SourceGrid:
    """Observed tau/Coverage resolver grid."""

    pre_specified_tau: float
    pre_specified_coverage: int
    tau_values: tuple[float, ...]
    coverage_values: tuple[int, ...]
    minimum_adjacent_passing_cells: int

    def __post_init__(self) -> None:
        tau_values = tuple(float(value) for value in self.tau_values)
        coverage_values = tuple(int(value) for value in self.coverage_values)
        if not tau_values or any(not math.isfinite(value) or value <= 0 for value in tau_values):
            raise RequestError("tau_values must contain finite positive values")
        if tuple(sorted(set(tau_values))) != tau_values:
            raise RequestError("tau_values must be unique and increasing")
        if not coverage_values or any(value < 1 for value in coverage_values):
            raise RequestError("coverage_values must contain positive values")
        if tuple(sorted(set(coverage_values))) != coverage_values:
            raise RequestError("coverage_values must be unique and increasing")
        object.__setattr__(self, "pre_specified_tau", float(self.pre_specified_tau))
        object.__setattr__(self, "pre_specified_coverage", int(self.pre_specified_coverage))
        object.__setattr__(self, "tau_values", tau_values)
        object.__setattr__(self, "coverage_values", coverage_values)
        object.__setattr__(self, "minimum_adjacent_passing_cells", int(self.minimum_adjacent_passing_cells))
        if self.pre_specified_tau not in tau_values:
            raise RequestError("pre_specified_tau must be present in tau_values")
        if self.pre_specified_coverage not in coverage_values:
            raise RequestError("pre_specified_coverage must be present in coverage_values")
        if self.minimum_adjacent_passing_cells < 0:
            raise RequestError("minimum_adjacent_passing_cells must be nonnegative")


@dataclass(frozen=True)
class HardComputabilityLimits:
    """Configured observed-model computability limits."""

    n_subjects_min: int
    n_features_full_min: int | None
    fold_n_features_min: int | None

    def __post_init__(self) -> None:
        if type(self.n_subjects_min) is not int or self.n_subjects_min < 1:
            raise RequestError("n_subjects_min must be a positive integer")
        for field in ("n_features_full_min", "fold_n_features_min"):
            value = getattr(self, field)
            if value is not None and (type(value) is not int or value < 1):
                raise RequestError(f"{field} must be null or a positive integer")


@dataclass(frozen=True)
class NormativeFiberScoreSettings:
    """Explicit signed-library and weighted-peak score parameters."""

    sweet_fraction: float
    sour_fraction: float
    weighted_peak_fraction: float
    sweet_selected_min_count: int
    sour_selected_min_count: int
    weighted_peak_min_count: int

    def __post_init__(self) -> None:
        for field in ("sweet_fraction", "sour_fraction", "weighted_peak_fraction"):
            value = float(getattr(self, field))
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise RequestError(f"{field} must be finite and in (0, 1]")
            object.__setattr__(self, field, value)
        for field in (
            "sweet_selected_min_count",
            "sour_selected_min_count",
            "weighted_peak_min_count",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise RequestError(f"{field} must be a positive integer")


@dataclass(frozen=True)
class ObservedRequest:
    """Observed LOOCV request for one endpoint and candidate branch."""

    endpoint: EndpointKey
    branch: str
    exposure: ScientificInput
    outcome: ScientificInput
    baseline: ScientificInput
    nuisance_inputs: tuple[ScientificInput, ...]
    subject_axis: AxisRef
    feature_axis: AxisRef
    source_grid: SourceGrid
    exposure_units: str
    exposure_space: str
    outcome_direction: str
    hard_computability: HardComputabilityLimits
    connectome_role: str
    feature_ids: ScientificInput | None
    fiber_score_settings: NormativeFiberScoreSettings | None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RequestError("endpoint must be an EndpointKey")
        if not str(self.branch).strip():
            raise RequestError("branch must be nonempty")
        _scientific_input(self.exposure, "exposure")
        _scientific_input(self.outcome, "outcome")
        _scientific_input(self.baseline, "baseline")
        object.__setattr__(self, "nuisance_inputs", _inputs(self.nuisance_inputs, "nuisance_inputs"))
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(self.feature_axis, AxisRef):
            raise RequestError("subject_axis and feature_axis must be AxisRef values")
        if not isinstance(self.source_grid, SourceGrid):
            raise RequestError("source_grid must be a SourceGrid")
        exposure_units = str(self.exposure_units).strip()
        exposure_space = str(self.exposure_space).strip()
        if not exposure_units or not exposure_space:
            raise RequestError("exposure_units and exposure_space must be nonempty")
        object.__setattr__(self, "exposure_units", exposure_units)
        object.__setattr__(self, "exposure_space", exposure_space)
        direction = str(self.outcome_direction).strip().lower()
        if direction not in {"lower", "higher"}:
            raise RequestError("outcome_direction must be 'lower' or 'higher'")
        object.__setattr__(self, "outcome_direction", direction)
        if not isinstance(self.hard_computability, HardComputabilityLimits):
            raise RequestError("hard_computability must be HardComputabilityLimits")
        role = str(self.connectome_role).strip().lower()
        if role not in {"none", "formal", "sensitive"}:
            raise RequestError("connectome_role must be 'none', 'formal', or 'sensitive'")
        object.__setattr__(self, "connectome_role", role)
        _validate_exposure(self.exposure, "exposure", self.subject_axis, self.feature_axis)
        if isinstance(self.exposure, ArtifactRef):
            if self.exposure.units != self.exposure_units:
                raise RequestError("exposure artifact units do not match exposure_units")
            if self.exposure.space != self.exposure_space:
                raise RequestError("exposure artifact space does not match exposure_space")
        _validate_vector(self.outcome, "outcome", self.subject_axis)
        _validate_vector(self.baseline, "baseline", self.subject_axis)
        for index, value in enumerate(self.nuisance_inputs):
            _validate_nuisance(value, f"nuisance_inputs[{index}]", self.subject_axis)

        if self.endpoint.model_family.endswith("voxel"):
            if role != "none":
                raise RequestError("direct-voxel requests require connectome_role='none'")
            if self.feature_ids is not None or self.fiber_score_settings is not None:
                raise RequestError(
                    "direct-voxel requests cannot declare fiber IDs or score settings"
                )
            if (
                self.hard_computability.n_features_full_min is None
                or self.hard_computability.fold_n_features_min is None
            ):
                raise RequestError(
                    "direct-voxel requests require full and fold feature minima"
                )
            return

        if role not in {"formal", "sensitive"}:
            raise RequestError("normative-fiber requests require a connectome role")
        if self.exposure_units != "V/m":
            raise RequestError("normative-fiber exposure_units must be 'V/m'")
        if self.feature_ids is None:
            raise RequestError("normative-fiber requests require canonical feature_ids")
        _scientific_input(self.feature_ids, "feature_ids")
        expected_feature_shape = (self.feature_axis.count,)
        if _shape(self.feature_ids, "feature_ids") != expected_feature_shape:
            raise RequestError(f"feature_ids shape must be {expected_feature_shape}")
        _require_artifact_axes(self.feature_ids, "feature_ids", (self.feature_axis,))
        if not isinstance(self.fiber_score_settings, NormativeFiberScoreSettings):
            raise RequestError(
                "normative-fiber requests require NormativeFiberScoreSettings"
            )
        if self.hard_computability.n_features_full_min is not None:
            raise RequestError(
                "normative-fiber requests cannot add a full-sample fiber-count gate"
            )
        if self.hard_computability.fold_n_features_min is None:
            raise RequestError(
                "normative-fiber requests require a fold candidate-fiber minimum"
            )


@dataclass(frozen=True)
class ObservedResult:
    """Observed artifacts plus an optional formal source classification."""

    source: SourceRecord | None
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if self.source is not None and not isinstance(self.source, SourceRecord):
            raise RequestError("source must be a SourceRecord or None")
        artifacts = tuple(self.artifacts)
        if not artifacts or not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("observed artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class FormalRequest:
    """Permutation/bootstrap request bound to one realized final model."""

    final_model: FinalModelRecord
    outcome: ScientificInput
    baseline: ScientificInput
    nuisance_inputs: tuple[ScientificInput, ...]
    subject_axis: AxisRef
    permutation_resamples: int
    bootstrap_resamples: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise RequestError("final_model must be a FinalModelRecord")
        if self.final_model.final_status not in {"final_model_realized", "fallback_final_realized"}:
            raise RequestError("formal inference requires a realized final model")
        _scientific_input(self.outcome, "outcome")
        _scientific_input(self.baseline, "baseline")
        object.__setattr__(self, "nuisance_inputs", _inputs(self.nuisance_inputs, "nuisance_inputs"))
        if not isinstance(self.subject_axis, AxisRef):
            raise RequestError("subject_axis must be an AxisRef")
        _validate_vector(self.outcome, "outcome", self.subject_axis)
        _validate_vector(self.baseline, "baseline", self.subject_axis)
        for index, value in enumerate(self.nuisance_inputs):
            _validate_nuisance(value, f"nuisance_inputs[{index}]", self.subject_axis)
        for field in ("permutation_resamples", "bootstrap_resamples"):
            value = int(getattr(self, field))
            if value < 1:
                raise RequestError(f"{field} must be positive")
            object.__setattr__(self, field, value)
        object.__setattr__(self, "seed", int(self.seed))


@dataclass(frozen=True)
class FormalResult:
    """Formal inference artifacts for one final model."""

    final_model_id: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not str(self.final_model_id).strip():
            raise RequestError("final_model_id must be nonempty")
        artifacts = tuple(self.artifacts)
        if not artifacts or not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("formal result requires ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class SensitivityRequest:
    """Final-linked or sensitive-connectome evaluation request."""

    sensitivity_kind: str
    exposure: ScientificInput
    parameter_values: tuple[float, ...]
    subject_axis: AxisRef
    feature_axis: AxisRef
    final_model: FinalModelRecord | None = None
    sensitive_record: SensitiveRecord | None = None

    def __post_init__(self) -> None:
        if not str(self.sensitivity_kind).strip():
            raise RequestError("sensitivity_kind must be nonempty")
        _scientific_input(self.exposure, "exposure")
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(self.feature_axis, AxisRef):
            raise RequestError("subject_axis and feature_axis must be AxisRef values")
        _validate_exposure(self.exposure, "exposure", self.subject_axis, self.feature_axis)
        values = tuple(float(value) for value in self.parameter_values)
        if any(not math.isfinite(value) for value in values):
            raise RequestError("parameter_values must be finite")
        object.__setattr__(self, "parameter_values", values)
        if (self.final_model is None) == (self.sensitive_record is None):
            raise RequestError("sensitivity request requires exactly one model or sensitive record")
        if self.final_model is not None and self.final_model.final_status not in {
            "final_model_realized",
            "fallback_final_realized",
        }:
            raise RequestError("final-linked sensitivity requires a realized final model")
        if self.final_model is not None and self.feature_axis != self.final_model.feature_axis.axis:
            raise RequestError("final-linked sensitivity must inherit the final model feature axis")


@dataclass(frozen=True)
class SensitivityResult:
    """Sensitivity artifacts that cannot alter final-model classification."""

    target_id: str
    sensitivity_kind: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not str(self.target_id).strip() or not str(self.sensitivity_kind).strip():
            raise RequestError("target_id and sensitivity_kind must be nonempty")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("sensitivity artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class ActivationRequest:
    """OSS/pPAM request bound to a normative-fiber final feature axis."""

    final_model: FinalModelRecord
    activation_probability: ScientificInput
    subject_axis: AxisRef
    feature_axis: AxisRef
    fitting_probability_threshold: float
    permutation_resamples: int

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise RequestError("final_model must be a FinalModelRecord")
        if not self.final_model.endpoint.model_family.endswith("fiber"):
            raise RequestError("activation sensitivity requires a normative-fiber final model")
        if self.final_model.final_status not in {"final_model_realized", "fallback_final_realized"}:
            raise RequestError("activation sensitivity requires a realized final model")
        _scientific_input(self.activation_probability, "activation_probability")
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(self.feature_axis, AxisRef):
            raise RequestError("subject_axis and feature_axis must be AxisRef values")
        if self.feature_axis != self.final_model.feature_axis.axis:
            raise RequestError("activation sensitivity must inherit the final model feature axis")
        _validate_exposure(
            self.activation_probability,
            "activation_probability",
            self.subject_axis,
            self.feature_axis,
        )
        threshold = float(self.fitting_probability_threshold)
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise RequestError("fitting_probability_threshold must be in [0, 1]")
        object.__setattr__(self, "fitting_probability_threshold", threshold)
        object.__setattr__(self, "permutation_resamples", int(self.permutation_resamples))
        if self.permutation_resamples < 1:
            raise RequestError("permutation_resamples must be positive")


@dataclass(frozen=True)
class ActivationArtifact:
    """Activation sensitivity artifacts on the inherited final feature axis."""

    final_model_id: str
    feature_axis: AxisRef
    binary_exposure: ArtifactRef
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not str(self.final_model_id).strip():
            raise RequestError("final_model_id must be nonempty")
        if not isinstance(self.feature_axis, AxisRef) or not isinstance(self.binary_exposure, ArtifactRef):
            raise RequestError("activation output requires an axis and binary ArtifactRef")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("activation artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)
