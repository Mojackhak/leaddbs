"""Typed array-or-artifact requests for scientific backends."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeAlias

import numpy as np

from .identity import EndpointKey, canonical_hash
from .records import (
    ArtifactRef,
    AxisRef,
    FinalModelRecord,
    SourceRecord,
)
from .validation import classification_feedback_violation


ScientificInput: TypeAlias = np.ndarray | ArtifactRef


BOOTSTRAP_REBUILD_METHOD = "matched_reference_bootstrap_rebuild"


class RequestError(ValueError):
    """Raised when a backend request contains an unresolved or unsafe input."""


def _request_token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise RequestError(f"{field} must be nonempty")
    return token


def _request_sha256(value: str, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise RequestError(f"{field} must be a 64-character SHA-256 digest")
    return digest


def _bootstrap_sample_indices_sha256(
    sample_indices: np.ndarray,
    subject_count: int,
) -> str:
    sample = np.asarray(sample_indices)
    if (
        sample.shape != (subject_count,)
        or sample.dtype == object
        or not np.issubdtype(sample.dtype, np.integer)
        or np.any((sample < 0) | (sample >= subject_count))
    ):
        raise RequestError(
            "bootstrap sample_indices must be an in-range ordered subject vector"
        )
    ordered_sample = np.ascontiguousarray(sample, dtype="<i8")
    digest = hashlib.sha256()
    digest.update(b"bootstrap_ordered_sample_indices_v1\0")
    digest.update(np.asarray([subject_count], dtype="<i8").tobytes())
    digest.update(ordered_sample.tobytes(order="C"))
    return digest.hexdigest()


def _bootstrap_delta_reference_sha256(
    full_scores: np.ndarray,
    fold_scores: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    digest.update(b"bootstrap_delta_reference_scores_v1\0")
    for name, value in ((b"full\0", full_scores), (b"folds\0", fold_scores)):
        array = np.ascontiguousarray(value, dtype="<f8")
        digest.update(name)
        digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _scientific_input(value: object, field: str) -> ScientificInput:
    if isinstance(value, (str, Path)):
        raise RequestError(f"{field} cannot be a raw path or filename")
    if not isinstance(value, (np.ndarray, ArtifactRef)):
        raise RequestError(f"{field} must be a NumPy array or ArtifactRef")
    if isinstance(value, np.ndarray) and value.dtype == object:
        raise RequestError(f"{field} cannot use object dtype")
    return value


def _artifact_input(value: object, field: str) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise RequestError(f"{field} must be an ArtifactRef")
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
        branch = str(self.branch).strip()
        if not branch:
            raise RequestError("branch must be nonempty")
        if self.endpoint.model_family.startswith("reference_"):
            allowed_branches = {"reference"}
        else:
            allowed_branches = {"no_delta_reference", "delta_reference_adjusted"}
        if branch not in allowed_branches:
            raise RequestError(
                f"branch {branch!r} is invalid for {self.endpoint.model_family!r}"
            )
        object.__setattr__(self, "branch", branch)
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

    @property
    def identifier(self) -> str:
        return f"observed_result_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class BootstrapRebuildProvenance:
    """Identity-bound provenance for one rebuilt bootstrap DeltaReferenceScore."""

    provider_id: str
    provider_version: str
    rebuild_method: str
    final_model_id: str
    subject_axis: AxisRef
    sample_indices_sha256: str
    delta_reference_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "provider_id",
            "provider_version",
            "rebuild_method",
            "final_model_id",
        ):
            object.__setattr__(
                self,
                field,
                _request_token(getattr(self, field), field),
            )
        if self.rebuild_method != BOOTSTRAP_REBUILD_METHOD:
            raise RequestError(
                f"rebuild_method must be {BOOTSTRAP_REBUILD_METHOD!r}"
            )
        if not isinstance(self.subject_axis, AxisRef):
            raise RequestError("bootstrap rebuild subject_axis must be an AxisRef")
        object.__setattr__(
            self,
            "sample_indices_sha256",
            _request_sha256(
                self.sample_indices_sha256,
                "sample_indices_sha256",
            ),
        )
        object.__setattr__(
            self,
            "delta_reference_sha256",
            _request_sha256(
                self.delta_reference_sha256,
                "delta_reference_sha256",
            ),
        )

    @classmethod
    def from_rebuild(
        cls,
        *,
        provider_id: str,
        provider_version: str,
        final_model_id: str,
        subject_axis: AxisRef,
        sample_indices: np.ndarray,
        delta_reference_full_scores: np.ndarray,
        delta_reference_fold_scores: np.ndarray,
    ) -> "BootstrapRebuildProvenance":
        """Create deterministic provenance from the exact rebuilt score payload."""

        return cls(
            provider_id=provider_id,
            provider_version=provider_version,
            rebuild_method=BOOTSTRAP_REBUILD_METHOD,
            final_model_id=final_model_id,
            subject_axis=subject_axis,
            sample_indices_sha256=_bootstrap_sample_indices_sha256(
                sample_indices,
                subject_axis.count,
            ),
            delta_reference_sha256=_bootstrap_delta_reference_sha256(
                delta_reference_full_scores,
                delta_reference_fold_scores,
            ),
        )


@dataclass(frozen=True)
class BootstrapNuisanceEvidence:
    """Raw rebuilt DeltaReferenceScore values and support QC for one sample."""

    sample_indices: np.ndarray
    delta_reference_full_scores: np.ndarray
    delta_reference_fold_scores: np.ndarray
    support_status: str
    support_qc: tuple[tuple[str, float | int | str | bool], ...]
    rebuild_provenance: BootstrapRebuildProvenance

    def __post_init__(self) -> None:
        indices = np.array(self.sample_indices, copy=True)
        if (
            indices.ndim != 1
            or indices.size < 1
            or indices.dtype == object
            or not np.issubdtype(indices.dtype, np.integer)
        ):
            raise RequestError("bootstrap sample_indices must be a nonempty integer vector")
        indices = np.asarray(indices, dtype=np.int64)
        if np.any((indices < 0) | (indices >= indices.size)):
            raise RequestError("bootstrap sample_indices are outside the subject axis")

        full = np.array(
            self.delta_reference_full_scores,
            dtype=np.float64,
            copy=True,
        )
        folds = np.array(
            self.delta_reference_fold_scores,
            dtype=np.float64,
            copy=True,
        )
        expected_full = (indices.size,)
        expected_folds = (indices.size, indices.size)
        if full.shape != expected_full or folds.shape != expected_folds:
            raise RequestError(
                "rebuilt DeltaReferenceScore arrays must be subject and fold-by-subject"
            )
        if not np.all(np.isfinite(full)) or not np.all(np.isfinite(folds)):
            raise RequestError("rebuilt DeltaReferenceScore arrays must be finite")

        provenance = self.rebuild_provenance
        if not isinstance(provenance, BootstrapRebuildProvenance):
            raise RequestError(
                "bootstrap evidence requires BootstrapRebuildProvenance"
            )
        expected_sample_indices_sha256 = _bootstrap_sample_indices_sha256(
            indices,
            indices.size,
        )
        if provenance.sample_indices_sha256 != expected_sample_indices_sha256:
            raise RequestError(
                "bootstrap rebuild provenance does not match ordered sample indices"
            )
        expected_delta_sha256 = _bootstrap_delta_reference_sha256(full, folds)
        if provenance.delta_reference_sha256 != expected_delta_sha256:
            raise RequestError(
                "bootstrap rebuild provenance does not match rebuilt DeltaReferenceScore"
            )

        status = str(self.support_status).strip().lower()
        if status not in {"adequate", "limited"}:
            raise RequestError(
                "adjusted bootstrap support_status must be 'adequate' or 'limited'"
            )
        qc = tuple(self.support_qc)
        if not qc:
            raise RequestError("adjusted bootstrap nuisance plan requires support QC")
        normalized_qc: list[tuple[str, float | int | str | bool]] = []
        seen: set[str] = set()
        for item in qc:
            if not isinstance(item, tuple) or len(item) != 2:
                raise RequestError("support_qc entries must be key-value pairs")
            key = str(item[0]).strip()
            value = item[1]
            if not key or key in seen:
                raise RequestError("support_qc keys must be nonempty and unique")
            if not isinstance(value, (float, int, str, bool)) or (
                isinstance(value, float) and not math.isfinite(value)
            ):
                raise RequestError("support_qc values must be finite JSON scalars")
            seen.add(key)
            normalized_qc.append((key, value))
        feedback_violation = classification_feedback_violation(
            dict(normalized_qc),
            location="support_qc",
        )
        if feedback_violation is not None:
            raise RequestError(feedback_violation)

        indices.flags.writeable = False
        full.flags.writeable = False
        folds.flags.writeable = False
        object.__setattr__(self, "sample_indices", indices)
        object.__setattr__(self, "delta_reference_full_scores", full)
        object.__setattr__(self, "delta_reference_fold_scores", folds)
        object.__setattr__(self, "support_status", status)
        object.__setattr__(self, "support_qc", tuple(normalized_qc))
        object.__setattr__(self, "rebuild_provenance", provenance)


@dataclass(frozen=True)
class FormalRequest:
    """One resampling family bound to one realized final and its locked axis."""

    final_model: FinalModelRecord
    resampling_kind: str
    exposure: ArtifactRef
    outcome: ArtifactRef
    baseline: ArtifactRef
    delta_reference_full: ArtifactRef | None
    delta_reference_folds: ArtifactRef | None
    subject_axis: AxisRef
    feature_axis: AxisRef
    exposure_units: str
    exposure_space: str
    outcome_direction: str
    hard_computability: HardComputabilityLimits
    connectome_role: str
    feature_ids: ArtifactRef | None
    fiber_score_settings: NormativeFiberScoreSettings | None
    resamples: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise RequestError("final_model must be a FinalModelRecord")
        if self.final_model.final_status not in {
            "final_model_realized",
            "fallback_final_realized",
        }:
            raise RequestError("formal inference requires a realized final model")
        kind = str(self.resampling_kind).strip().lower()
        if kind not in {"permutation", "bootstrap"}:
            raise RequestError("resampling_kind must be 'permutation' or 'bootstrap'")
        object.__setattr__(self, "resampling_kind", kind)

        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.feature_axis, AxisRef
        ):
            raise RequestError("subject_axis and feature_axis must be AxisRef values")
        if self.feature_axis != self.final_model.valid_feature_axis.axis:
            raise RequestError("formal feature_axis must inherit final.valid_feature_axis")

        _artifact_input(self.exposure, "exposure")
        _artifact_input(self.outcome, "outcome")
        _artifact_input(self.baseline, "baseline")
        _validate_exposure(
            self.exposure,
            "exposure",
            self.subject_axis,
            self.feature_axis,
        )
        _validate_vector(self.outcome, "outcome", self.subject_axis)
        _validate_vector(self.baseline, "baseline", self.subject_axis)

        units = str(self.exposure_units).strip()
        space = str(self.exposure_space).strip()
        if not units or not space:
            raise RequestError("exposure_units and exposure_space must be nonempty")
        object.__setattr__(self, "exposure_units", units)
        object.__setattr__(self, "exposure_space", space)
        if self.exposure.units != units:
            raise RequestError("exposure artifact units do not match exposure_units")
        if self.exposure.space != space:
            raise RequestError("exposure artifact space does not match exposure_space")

        direction = str(self.outcome_direction).strip().lower()
        if direction not in {"lower", "higher"}:
            raise RequestError("outcome_direction must be 'lower' or 'higher'")
        object.__setattr__(self, "outcome_direction", direction)
        if not isinstance(self.hard_computability, HardComputabilityLimits):
            raise RequestError("hard_computability must be HardComputabilityLimits")
        if self.subject_axis.count < self.hard_computability.n_subjects_min:
            raise RequestError("formal subject axis does not meet n_subjects_min")

        role = str(self.connectome_role).strip().lower()
        if role not in {"none", "formal", "sensitive"}:
            raise RequestError("connectome_role must be 'none', 'formal', or 'sensitive'")
        object.__setattr__(self, "connectome_role", role)

        final_key = self.final_model.final_key
        if final_key is None:
            raise RequestError("formal inference requires a realized final key")
        adjusted = final_key.final_branch == "delta_reference_adjusted"
        delta_values = (self.delta_reference_full, self.delta_reference_folds)
        if adjusted:
            if any(value is None for value in delta_values):
                raise RequestError(
                    "adjusted formal requests require full and fold DeltaReferenceScore"
                )
            assert self.delta_reference_full is not None
            assert self.delta_reference_folds is not None
            _artifact_input(self.delta_reference_full, "delta_reference_full")
            _artifact_input(self.delta_reference_folds, "delta_reference_folds")
            _validate_vector(
                self.delta_reference_full,
                "delta_reference_full",
                self.subject_axis,
            )
            expected_shape = (self.subject_axis.count, self.subject_axis.count)
            if _shape(self.delta_reference_folds, "delta_reference_folds") != expected_shape:
                raise RequestError(f"delta_reference_folds shape must be {expected_shape}")
            _require_artifact_axes(
                self.delta_reference_folds,
                "delta_reference_folds",
                (self.subject_axis, self.subject_axis),
            )
        elif any(value is not None for value in delta_values):
            raise RequestError(
                "reference and no-delta formal requests cannot receive DeltaReferenceScore"
            )

        if self.final_model.endpoint.model_family.endswith("voxel"):
            if role != "none":
                raise RequestError("direct-voxel formal requests require connectome_role='none'")
            if self.feature_ids is not None or self.fiber_score_settings is not None:
                raise RequestError(
                    "direct-voxel formal requests cannot declare fiber IDs or score settings"
                )
            if (
                self.hard_computability.n_features_full_min is None
                or self.hard_computability.fold_n_features_min is None
            ):
                raise RequestError(
                    "direct-voxel formal requests require full and fold feature minima"
                )
        else:
            if role != "formal":
                raise RequestError(
                    "normative-fiber formal requests require connectome_role='formal'"
                )
            if units != "V/m":
                raise RequestError("normative-fiber formal exposure_units must be 'V/m'")
            if self.feature_ids is None:
                raise RequestError("normative-fiber formal requests require fiber IDs")
            if not isinstance(self.feature_ids, ArtifactRef):
                raise RequestError(
                    "normative-fiber feature_ids must be the selected source's exact "
                    "immutable ID artifact"
                )
            selected_source = self.final_model.selected_source
            if selected_source is None and self.final_model.selected_branch is not None:
                selected_source = self.final_model.selected_branch.source
            if selected_source is None:
                raise RequestError("normative-fiber final has no selected source")
            source_id_artifacts = tuple(
                artifact
                for artifact in selected_source.artifacts
                if artifact.kind == "normative_fiber_valid_union_ids"
            )
            if len(source_id_artifacts) != 1:
                raise RequestError(
                    "selected normative-fiber source must carry exactly one "
                    "normative_fiber_valid_union_ids artifact"
                )
            source_id_artifact = source_id_artifacts[0]
            if source_id_artifact.axis_refs != (self.feature_axis,):
                raise RequestError(
                    "selected source fiber ID artifact must use final.valid_feature_axis"
                )
            if self.feature_ids != source_id_artifact:
                raise RequestError(
                    "feature_ids must exactly equal the selected source "
                    "normative_fiber_valid_union_ids artifact"
                )
            if _shape(self.feature_ids, "feature_ids") != (self.feature_axis.count,):
                raise RequestError("feature_ids must match final.valid_feature_axis")
            _require_artifact_axes(
                self.feature_ids,
                "feature_ids",
                (self.feature_axis,),
            )
            if self.feature_ids.dtype != "int64":
                raise RequestError("feature_ids artifact dtype must be int64")
            if not isinstance(self.fiber_score_settings, NormativeFiberScoreSettings):
                raise RequestError(
                    "normative-fiber formal requests require score settings"
                )
            if self.hard_computability.n_features_full_min is not None:
                raise RequestError(
                    "normative-fiber formal requests cannot add a full-sample fiber gate"
                )
            if self.hard_computability.fold_n_features_min is None:
                raise RequestError(
                    "normative-fiber formal requests require a fold feature minimum"
                )

        if type(self.resamples) is not int or self.resamples < 1:
            raise RequestError("resamples must be a positive integer")
        if type(self.seed) is not int:
            raise RequestError("seed must be an integer")


@dataclass(frozen=True)
class InSampleRequest:
    """Full-parent-axis request for conditional final in-sample inference."""

    final_model: FinalModelRecord
    exposure: ArtifactRef
    outcome: ArtifactRef
    baseline: ArtifactRef
    delta_reference_full: ArtifactRef | None
    subject_axis: AxisRef
    feature_axis: AxisRef
    feature_ids: ArtifactRef
    loocv_predictions: ArtifactRef
    loocv_baseline_predictions: ArtifactRef
    loocv_permutation_summary: ArtifactRef
    exposure_units: str
    exposure_space: str
    outcome_direction: str
    hard_computability: HardComputabilityLimits
    connectome_role: str
    fiber_score_settings: NormativeFiberScoreSettings | None
    resamples: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise RequestError("in-sample inference requires a FinalModelRecord")
        if self.final_model.final_key is None:
            raise RequestError("in-sample inference requires a realized final key")
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.feature_axis,
            AxisRef,
        ):
            raise RequestError("in-sample axes must be AxisRef values")

        for value, field in (
            (self.exposure, "exposure"),
            (self.outcome, "outcome"),
            (self.baseline, "baseline"),
            (self.feature_ids, "feature_ids"),
            (self.loocv_predictions, "loocv_predictions"),
            (self.loocv_baseline_predictions, "loocv_baseline_predictions"),
            (self.loocv_permutation_summary, "loocv_permutation_summary"),
        ):
            _artifact_input(value, field)
        _validate_exposure(
            self.exposure,
            "exposure",
            self.subject_axis,
            self.feature_axis,
        )
        _validate_vector(self.outcome, "outcome", self.subject_axis)
        _validate_vector(self.baseline, "baseline", self.subject_axis)
        _validate_vector(
            self.loocv_predictions,
            "loocv_predictions",
            self.subject_axis,
        )
        _validate_vector(
            self.loocv_baseline_predictions,
            "loocv_baseline_predictions",
            self.subject_axis,
        )
        if self.feature_ids.dtype != "int64":
            raise RequestError("in-sample feature_ids must use int64")
        if _shape(self.feature_ids, "feature_ids") != (self.feature_axis.count,):
            raise RequestError("in-sample feature_ids must match the parent feature axis")
        _require_artifact_axes(
            self.feature_ids,
            "feature_ids",
            (self.feature_axis,),
        )
        if self.loocv_permutation_summary.shape is not None:
            raise RequestError("LOOCV permutation summary must be a document artifact")

        units = _request_token(self.exposure_units, "exposure_units")
        space = _request_token(self.exposure_space, "exposure_space")
        object.__setattr__(self, "exposure_units", units)
        object.__setattr__(self, "exposure_space", space)
        if self.exposure.units != units or self.exposure.space != space:
            raise RequestError("in-sample exposure metadata does not match the request")

        direction = str(self.outcome_direction).strip().lower()
        if direction not in {"lower", "higher"}:
            raise RequestError("in-sample outcome_direction must be lower or higher")
        object.__setattr__(self, "outcome_direction", direction)
        if not isinstance(self.hard_computability, HardComputabilityLimits):
            raise RequestError("in-sample hard_computability is invalid")
        if self.subject_axis.count < self.hard_computability.n_subjects_min:
            raise RequestError("in-sample subject axis does not meet n_subjects_min")

        role = str(self.connectome_role).strip().lower()
        if role not in {"none", "formal"}:
            raise RequestError("in-sample connectome_role must be none or formal")
        object.__setattr__(self, "connectome_role", role)
        is_fiber = self.final_model.endpoint.model_family.endswith("fiber")
        if is_fiber:
            if role != "formal" or not isinstance(
                self.fiber_score_settings,
                NormativeFiberScoreSettings,
            ):
                raise RequestError(
                    "normative-fiber in-sample requests require formal role and score settings"
                )
        elif role != "none" or self.fiber_score_settings is not None:
            raise RequestError(
                "direct-voxel in-sample requests require no connectome role or fiber settings"
            )

        adjusted = (
            self.final_model.final_key.final_branch == "delta_reference_adjusted"
        )
        if adjusted:
            if self.delta_reference_full is None:
                raise RequestError(
                    "adjusted in-sample inference requires full DeltaReferenceScore"
                )
            _artifact_input(self.delta_reference_full, "delta_reference_full")
            _validate_vector(
                self.delta_reference_full,
                "delta_reference_full",
                self.subject_axis,
            )
        elif self.delta_reference_full is not None:
            raise RequestError(
                "reference and no-delta in-sample requests cannot receive DeltaReferenceScore"
            )

        if type(self.resamples) is not int or self.resamples < 1:
            raise RequestError("in-sample resamples must be a positive integer")
        if type(self.seed) is not int:
            raise RequestError("in-sample seed must be an integer")


@dataclass(frozen=True)
class FormalResult:
    """Technical formal evidence with no classification feedback fields."""

    final_model_id: str
    resampling_kind: str
    technical_status: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "final_model_id",
            _request_token(self.final_model_id, "final_model_id"),
        )
        kind = str(self.resampling_kind).strip().lower()
        if kind not in {"permutation", "bootstrap", "in_sample_permutation"}:
            raise RequestError("formal result has an unsupported resampling_kind")
        status = str(self.technical_status).strip().lower()
        if status not in {"completed", "completed_with_nonfinite_replicates"}:
            raise RequestError("formal result has an unsupported technical_status")
        object.__setattr__(self, "resampling_kind", kind)
        object.__setattr__(self, "technical_status", status)
        artifacts = tuple(self.artifacts)
        if not artifacts or not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("formal result requires ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"formal_result_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class SensitivityResult:
    """Sensitivity artifacts that cannot alter final-model classification."""

    target_id: str
    sensitivity_kind: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id",
            _request_token(self.target_id, "target_id"),
        )
        object.__setattr__(
            self,
            "sensitivity_kind",
            _request_token(self.sensitivity_kind, "sensitivity_kind"),
        )
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("sensitivity artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"sensitivity_result_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class ActivationRequest:
    """OSS/pPAM request bound to a normative-fiber final feature axis."""

    final_model: FinalModelRecord
    activation_probability: ScientificInput
    reference_overlap_mask: ScientificInput | None
    outcome: ScientificInput
    baseline: ScientificInput
    peak_final_score: ScientificInput
    nuisance_inputs: tuple[ScientificInput, ...]
    subject_axis: AxisRef
    feature_axis: AxisRef
    feature_ids: ScientificInput
    activation_feature_ids: ScientificInput
    outcome_direction: str
    hard_computability: HardComputabilityLimits
    connectome_role: str
    fiber_score_settings: NormativeFiberScoreSettings
    fitting_probability_threshold: float
    permutation_resamples: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise RequestError("final_model must be a FinalModelRecord")
        if not self.final_model.endpoint.model_family.endswith("fiber"):
            raise RequestError("activation sensitivity requires a normative-fiber final model")
        if self.final_model.final_status not in {"final_model_realized", "fallback_final_realized"}:
            raise RequestError("activation sensitivity requires a realized final model")
        _scientific_input(self.activation_probability, "activation_probability")
        _scientific_input(self.outcome, "outcome")
        _scientific_input(self.baseline, "baseline")
        _scientific_input(self.peak_final_score, "peak_final_score")
        object.__setattr__(
            self,
            "nuisance_inputs",
            _inputs(self.nuisance_inputs, "nuisance_inputs"),
        )
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(self.feature_axis, AxisRef):
            raise RequestError("subject_axis and feature_axis must be AxisRef values")
        if self.feature_axis != self.final_model.valid_feature_axis.axis:
            raise RequestError("activation sensitivity must inherit the final model feature axis")
        _validate_exposure(
            self.activation_probability,
            "activation_probability",
            self.subject_axis,
            self.feature_axis,
        )
        is_reference = self.final_model.endpoint.model_family.startswith("reference_")
        if is_reference:
            if self.reference_overlap_mask is not None:
                raise RequestError(
                    "reference activation cannot receive a reference_overlap_mask"
                )
        else:
            if self.reference_overlap_mask is None:
                raise RequestError(
                    "add-on activation requires a reference_overlap_mask"
                )
            _scientific_input(self.reference_overlap_mask, "reference_overlap_mask")
            _validate_exposure(
                self.reference_overlap_mask,
                "reference_overlap_mask",
                self.subject_axis,
                self.feature_axis,
            )
            if isinstance(self.reference_overlap_mask, np.ndarray):
                if self.reference_overlap_mask.dtype != np.dtype(bool):
                    raise RequestError("reference_overlap_mask must use boolean dtype")
            elif (
                np.dtype(self.reference_overlap_mask.dtype) != np.dtype(bool)
                or self.reference_overlap_mask.units != "binary"
                or self.reference_overlap_mask.space != "right_canonical"
            ):
                raise RequestError(
                    "reference_overlap_mask artifact must be boolean binary data "
                    "in right_canonical space"
                )
        _validate_vector(self.outcome, "outcome", self.subject_axis)
        _validate_vector(self.baseline, "baseline", self.subject_axis)
        _validate_vector(self.peak_final_score, "peak_final_score", self.subject_axis)
        if isinstance(self.activation_probability, ArtifactRef) and (
            self.activation_probability.units != "probability"
            or self.activation_probability.space != "right_canonical"
        ):
            raise RequestError(
                "activation_probability artifact must use probability units in right_canonical space"
            )
        for index, value in enumerate(self.nuisance_inputs):
            _validate_nuisance(value, f"nuisance_inputs[{index}]", self.subject_axis)
        _scientific_input(self.feature_ids, "feature_ids")
        if _shape(self.feature_ids, "feature_ids") != (self.feature_axis.count,):
            raise RequestError("feature_ids must match the final feature axis")
        _require_artifact_axes(self.feature_ids, "feature_ids", (self.feature_axis,))
        if isinstance(self.feature_ids, ArtifactRef) and (
            np.dtype(self.feature_ids.dtype) != np.dtype(np.int64)
            or self.feature_ids.units != "fiber_id"
            or self.feature_ids.space != "right_canonical"
        ):
            raise RequestError(
                "feature_ids artifact must be int64 fiber_id data in right_canonical space"
            )
        _scientific_input(self.activation_feature_ids, "activation_feature_ids")
        if _shape(self.activation_feature_ids, "activation_feature_ids") != (
            self.feature_axis.count,
        ):
            raise RequestError("activation_feature_ids must match the final feature axis")
        _require_artifact_axes(
            self.activation_feature_ids,
            "activation_feature_ids",
            (self.feature_axis,),
        )
        if isinstance(self.activation_feature_ids, ArtifactRef) and (
            np.dtype(self.activation_feature_ids.dtype) != np.dtype(np.int64)
            or self.activation_feature_ids.units != "fiber_id"
            or self.activation_feature_ids.space != "right_canonical"
        ):
            raise RequestError(
                "activation_feature_ids artifact must be int64 fiber_id data in right_canonical space"
            )
        direction = str(self.outcome_direction).strip().lower()
        if direction not in {"lower", "higher"}:
            raise RequestError("outcome_direction must be 'lower' or 'higher'")
        object.__setattr__(self, "outcome_direction", direction)
        if not isinstance(self.hard_computability, HardComputabilityLimits):
            raise RequestError("hard_computability must be HardComputabilityLimits")
        if (
            self.hard_computability.n_features_full_min is not None
            or self.hard_computability.fold_n_features_min is None
        ):
            raise RequestError(
                "activation sensitivity requires normative-fiber hard limits"
            )
        if str(self.connectome_role).strip().lower() != "formal":
            raise RequestError("activation sensitivity requires connectome_role='formal'")
        object.__setattr__(self, "connectome_role", "formal")
        if not isinstance(self.fiber_score_settings, NormativeFiberScoreSettings):
            raise RequestError(
                "activation sensitivity requires NormativeFiberScoreSettings"
            )
        branch = self.final_model.final_key.final_branch
        if is_reference:
            if self.nuisance_inputs:
                raise RequestError("reference activation cannot receive nuisance_inputs")
        elif branch == "no_delta_reference":
            if self.nuisance_inputs:
                raise RequestError("no-delta activation cannot receive nuisance_inputs")
        elif branch == "delta_reference_adjusted":
            if len(self.nuisance_inputs) != 2:
                raise RequestError(
                    "adjusted activation requires full and fold DeltaReferenceScore inputs"
                )
            if _shape(self.nuisance_inputs[0], "nuisance_inputs[0]") != (
                self.subject_axis.count,
            ):
                raise RequestError(
                    "adjusted activation full DeltaReferenceScore must be a subject vector"
                )
            if _shape(self.nuisance_inputs[1], "nuisance_inputs[1]") != (
                self.subject_axis.count,
                self.subject_axis.count,
            ):
                raise RequestError(
                    "adjusted activation fold DeltaReferenceScore must be fold-by-subject"
                )
            _require_artifact_axes(
                self.nuisance_inputs[0],
                "nuisance_inputs[0]",
                (self.subject_axis,),
            )
            _require_artifact_axes(
                self.nuisance_inputs[1],
                "nuisance_inputs[1]",
                (self.subject_axis, self.subject_axis),
            )
        else:
            raise RequestError(f"unsupported activation final branch {branch!r}")
        threshold = float(self.fitting_probability_threshold)
        if threshold != 0.5:
            raise RequestError("v1 fitting_probability_threshold must equal 0.5")
        object.__setattr__(self, "fitting_probability_threshold", threshold)
        object.__setattr__(self, "permutation_resamples", int(self.permutation_resamples))
        if self.permutation_resamples < 1:
            raise RequestError("permutation_resamples must be positive")
        if type(self.seed) is not int or self.seed < 0:
            raise RequestError("seed must be a nonnegative integer")


@dataclass(frozen=True)
class ActivationArtifact:
    """Activation sensitivity artifacts on the inherited final feature axis."""

    final_model_id: str
    feature_axis: AxisRef
    activation_probability: ArtifactRef
    binary_exposure: ArtifactRef
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "final_model_id",
            _request_token(self.final_model_id, "final_model_id"),
        )
        if (
            not isinstance(self.feature_axis, AxisRef)
            or not isinstance(self.activation_probability, ArtifactRef)
            or not isinstance(self.binary_exposure, ArtifactRef)
        ):
            raise RequestError(
                "activation output requires an axis, probability, and binary ArtifactRef"
            )
        for artifact in (self.activation_probability, self.binary_exposure):
            if not artifact.axis_refs or artifact.axis_refs[-1] != self.feature_axis:
                raise RequestError("activation output artifacts must use the final feature axis")
        if self.activation_probability.axis_refs != self.binary_exposure.axis_refs:
            raise RequestError("probability and binary activation axes must match")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RequestError("activation artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"activation_artifact_{canonical_hash(asdict(self), length=20)}"
