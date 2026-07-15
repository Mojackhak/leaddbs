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
        expected_exposure_shape = (self.subject_axis.count, self.feature_axis.count)
        if _shape(self.exposure, "exposure") != expected_exposure_shape:
            raise RequestError(f"exposure shape must be {expected_exposure_shape}")
        expected_outcome_shape = (self.subject_axis.count,)
        if _shape(self.outcome, "outcome") != expected_outcome_shape:
            raise RequestError(f"outcome shape must be {expected_outcome_shape}")
        if _shape(self.baseline, "baseline") != expected_outcome_shape:
            raise RequestError(f"baseline shape must be {expected_outcome_shape}")
        for index, value in enumerate(self.nuisance_inputs):
            shape = _shape(value, f"nuisance_inputs[{index}]")
            if not shape or shape[0] != self.subject_axis.count or len(shape) > 2:
                raise RequestError("each nuisance input must be subject-major and one- or two-dimensional")


@dataclass(frozen=True)
class ObservedResult:
    """Observed backend result and immutable source classification."""

    source: SourceRecord
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceRecord):
            raise RequestError("source must be a SourceRecord")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("observed artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class FormalRequest:
    """Permutation/bootstrap request bound to one realized final model."""

    final_model: FinalModelRecord
    outcome: ScientificInput
    baseline: ScientificInput
    nuisance_inputs: tuple[ScientificInput, ...]
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
    final_model: FinalModelRecord | None = None
    sensitive_record: SensitiveRecord | None = None

    def __post_init__(self) -> None:
        if not str(self.sensitivity_kind).strip():
            raise RequestError("sensitivity_kind must be nonempty")
        _scientific_input(self.exposure, "exposure")
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
        if not isinstance(self.feature_axis, AxisRef):
            raise RequestError("feature_axis must be an AxisRef")
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
