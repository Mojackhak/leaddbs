"""Immutable scientific records shared by every dual-frequency backend."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

import numpy as np

from .identity import EndpointKey, FinalModelKey, canonical_hash


ACCEPTED_SOURCE_STATUSES = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
PREDICTION_STATUSES = frozenset({"error_predictive", "error_nonpredictive"})
SOURCE_STATUSES = ACCEPTED_SOURCE_STATUSES | {"absent_no_stable_grid"}
SOURCE_INPUT_STATUSES = frozenset({"valid", "input_failure", "execution_failure"})
THRESHOLD_SOURCES = frozenset({"pre_specified", "scan_fallback", "none"})
DELTA_INPUT_STATUSES = frozenset({"valid", "invalid", "input_failure", "execution_failure"})
DELTA_SUPPORT_STATUSES = frozenset(
    {
        "adequate",
        "limited",
        "invalid_extreme_out_of_support",
        "invalid_no_reference_component_exposure",
        "invalid_no_reference_component_coverage",
        "not_applicable",
    }
)
DEPENDENCY_STATUSES = frozenset(
    {"ready", "not_configured", "input_failure", "design_failure", "execution_failure"}
)
BRANCH_ROLES = frozenset({"primary", "comparison", "fallback_eligible"})
BRANCH_INPUT_STATUSES = frozenset({"valid", "input_failure", "execution_failure", "not_attempted"})
NUISANCE_DESIGN_STATUSES = frozenset(
    {
        "valid",
        "design_failure",
        "invalid_delta_reference_scaling",
        "invalid_nuisance_design",
        "execution_failure",
        "not_attempted",
    }
)
SENSITIVE_CELL_COMPUTABILITY_STATUSES = frozenset({"computable", "not_computable"})
ENDPOINT_READINESS_STATUSES = frozenset(
    {"ready", "insufficient_subjects", "input_failure"}
)
DELTA_REFERENCE_INPUT_STATUSES = frozenset(
    {"ready", "input_failure", "not_applicable"}
)
FINAL_DECISION_STATUSES = frozenset(
    {
        "realized_primary",
        "realized_fallback",
        "no_final_model",
        "dependency_failure",
        "execution_failure",
    }
)
FINAL_SELECTION_STATUSES = frozenset(
    {
        "final_model_realized",
        "fallback_final_realized",
        "no_final_model",
        "dependency_failure",
        "execution_failure",
    }
)
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]*$")
RESAMPLING_REPLICATE_BLOCK_SIZE = 250


class RecordError(ValueError):
    """Raised when a scientific record is incomplete or inconsistent."""


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise RecordError(f"{field} must be nonempty")
    return token


def _sha256(value: str, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise RecordError(f"{field} must be a 64-character SHA-256 digest")
    return digest


@dataclass(frozen=True, order=True)
class AxisRef:
    """Identity and cardinality of one ordered array axis."""

    axis_id: str
    count: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis_id", _token(self.axis_id, "axis_id"))
        object.__setattr__(self, "count", int(self.count))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "axis sha256"))
        if self.count < 1:
            raise RecordError("axis count must be positive")


@dataclass(frozen=True, order=True)
class FeatureAxisRef:
    """Ordered feature axis plus the external identity authority."""

    axis: AxisRef
    identity_source: str

    def __post_init__(self) -> None:
        if not isinstance(self.axis, AxisRef):
            raise RecordError("feature axis must be an AxisRef")
        object.__setattr__(self, "identity_source", _token(self.identity_source, "identity_source"))


@dataclass(frozen=True)
class ArtifactRef:
    """Content-addressed external artifact with explicit array semantics."""

    kind: str
    schema_version: str
    uri: str
    sha256: str
    dtype: str | None
    shape: tuple[int, ...] | None
    axis_refs: tuple[AxisRef, ...]
    axis_hashes: tuple[str, ...]
    units: str | None
    space: str | None
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        for field in ("kind", "schema_version", "uri", "producer_id", "producer_version"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        parsed = urlparse(self.uri)
        if not parsed.scheme:
            raise RecordError("artifact uri must include an explicit URI scheme")
        object.__setattr__(self, "sha256", _sha256(self.sha256, "artifact sha256"))
        if self.dtype is not None:
            object.__setattr__(self, "dtype", _token(self.dtype, "dtype"))
        if self.units is not None:
            object.__setattr__(self, "units", _token(self.units, "units"))
        if self.space is not None:
            object.__setattr__(self, "space", _token(self.space, "space"))

        axis_refs = tuple(self.axis_refs)
        if not all(isinstance(item, AxisRef) for item in axis_refs):
            raise RecordError("axis_refs must contain only AxisRef values")
        axis_hashes = tuple(_sha256(value, "axis hash") for value in self.axis_hashes)
        object.__setattr__(self, "axis_refs", axis_refs)
        object.__setattr__(self, "axis_hashes", axis_hashes)
        if len(axis_refs) != len(axis_hashes):
            raise RecordError("axis_refs and axis_hashes must have the same length")
        if axis_hashes != tuple(item.sha256 for item in axis_refs):
            raise RecordError("axis_hashes must match ordered axis_refs")

        if self.shape is None:
            if axis_refs or self.dtype is not None:
                raise RecordError("non-array artifacts cannot declare dtype or axes without shape")
            return
        shape = tuple(int(value) for value in self.shape)
        if not shape or any(value < 1 for value in shape):
            raise RecordError("array artifact shape dimensions must be positive")
        if self.dtype is None:
            raise RecordError("array artifacts require dtype")
        if len(shape) != len(axis_refs):
            raise RecordError("array artifacts require one ordered AxisRef per dimension")
        for dimension, axis in zip(shape, axis_refs, strict=True):
            if dimension != axis.count:
                raise RecordError("artifact shape must match ordered axis cardinalities")
        object.__setattr__(self, "shape", shape)

    @property
    def identifier(self) -> str:
        return f"artifact_{canonical_hash(asdict(self), length=20)}"


def resampling_block_axis(
    replicate_axis: AxisRef,
    start: int,
    stop: int,
) -> AxisRef:
    """Return the canonical local axis for one fixed replicate interval."""

    if not isinstance(replicate_axis, AxisRef):
        raise RecordError("replicate_axis must be an AxisRef")
    if (
        type(start) is not int
        or type(stop) is not int
        or start < 0
        or stop <= start
        or stop > replicate_axis.count
    ):
        raise RecordError("resampling block interval is invalid")
    payload = {
        "replicate_axis": asdict(replicate_axis),
        "start": start,
        "stop": stop,
    }
    return AxisRef(
        f"{replicate_axis.axis_id}_block_{start:06d}_{stop:06d}",
        stop - start,
        canonical_hash(payload),
    )


@dataclass(frozen=True)
class ResamplingScheduleRecord:
    """Durable identity and payload for one complete historical RNG schedule."""

    target_id: str
    resampling_kind: str
    subject_axis: AxisRef
    replicate_axis: AxisRef
    seed: int
    replicate_count: int
    block_size: int
    schedule_schema: str
    generator_class: str
    bit_generator_class: str
    numpy_version: str
    environment_fingerprint: str
    schedule_sha256: str
    schedule: ArtifactRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _token(self.target_id, "target_id"))
        kind = _token(self.resampling_kind, "resampling_kind").lower()
        if kind not in {"permutation", "bootstrap"}:
            raise RecordError("resampling schedule kind is unsupported")
        object.__setattr__(self, "resampling_kind", kind)
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.replicate_axis,
            AxisRef,
        ):
            raise RecordError("resampling schedule axes must be AxisRef values")
        if type(self.seed) is not int:
            raise RecordError("resampling schedule seed must be an integer")
        if (
            type(self.replicate_count) is not int
            or self.replicate_count != self.replicate_axis.count
        ):
            raise RecordError(
                "resampling schedule count must match the replicate axis"
            )
        if self.block_size != RESAMPLING_REPLICATE_BLOCK_SIZE:
            raise RecordError("resampling schedule block size is not canonical")
        for field in (
            "schedule_schema",
            "generator_class",
            "bit_generator_class",
            "numpy_version",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(
            self,
            "environment_fingerprint",
            _sha256(self.environment_fingerprint, "environment_fingerprint"),
        )
        object.__setattr__(
            self,
            "schedule_sha256",
            _sha256(self.schedule_sha256, "schedule_sha256"),
        )
        if not isinstance(self.schedule, ArtifactRef):
            raise RecordError("resampling schedule payload must be an ArtifactRef")
        expected_dtype = "int32" if kind == "permutation" else "int64"
        if (
            self.schedule.kind != "formal_resampling_schedule"
            or self.schedule.dtype != expected_dtype
            or self.schedule.shape
            != (self.replicate_axis.count, self.subject_axis.count)
            or self.schedule.axis_refs != (self.replicate_axis, self.subject_axis)
            or self.schedule.units != "subject_index"
        ):
            raise RecordError(
                "resampling schedule artifact does not match its axes and kind"
            )

    @property
    def identifier(self) -> str:
        return f"resampling_schedule_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class ResamplingBlockRecord:
    """Durable output for one canonical formal-permutation replicate block."""

    target_id: str
    resampling_kind: str
    schedule_id: str
    replicate_axis: AxisRef
    block_axis: AxisRef
    block_index: int
    start: int
    stop: int
    total: int
    schedule_sha256: str
    technical_status: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _token(self.target_id, "target_id"))
        kind = _token(self.resampling_kind, "resampling_kind").lower()
        if kind != "permutation":
            raise RecordError(
                "resampling block v1 supports formal permutation only"
            )
        object.__setattr__(self, "resampling_kind", kind)
        object.__setattr__(self, "schedule_id", _token(self.schedule_id, "schedule_id"))
        if not isinstance(self.replicate_axis, AxisRef) or not isinstance(
            self.block_axis,
            AxisRef,
        ):
            raise RecordError("resampling block axes must be AxisRef values")
        if (
            type(self.block_index) is not int
            or type(self.start) is not int
            or type(self.stop) is not int
            or type(self.total) is not int
            or self.total != self.replicate_axis.count
            or self.start != self.block_index * RESAMPLING_REPLICATE_BLOCK_SIZE
            or self.stop
            != min(self.start + RESAMPLING_REPLICATE_BLOCK_SIZE, self.total)
        ):
            raise RecordError("resampling block interval is not canonical")
        if self.block_axis != resampling_block_axis(
            self.replicate_axis,
            self.start,
            self.stop,
        ):
            raise RecordError("resampling block axis does not match its interval")
        object.__setattr__(
            self,
            "schedule_sha256",
            _sha256(self.schedule_sha256, "schedule_sha256"),
        )
        status = _token(self.technical_status, "technical_status").lower()
        if status not in {"completed", "completed_with_nonfinite_replicates"}:
            raise RecordError("resampling block technical status is unsupported")
        object.__setattr__(self, "technical_status", status)
        artifacts = tuple(self.artifacts)
        if len(artifacts) != 1 or not isinstance(artifacts[0], ArtifactRef):
            raise RecordError(
                "formal permutation block requires one null-statistic artifact"
            )
        null = artifacts[0]
        if (
            null.kind != "formal_permutation_null_statistics_block"
            or null.dtype != "float64"
            or null.shape != (self.block_axis.count,)
            or null.axis_refs != (self.block_axis,)
            or null.units != "spearman_rho"
        ):
            raise RecordError(
                "formal permutation block artifact does not match the block axis"
            )
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"resampling_block_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class PPAMPermutationBlockRecord:
    """Durable pPAM null-statistic state for one canonical interval."""

    target_id: str
    schedule_id: str
    replicate_axis: AxisRef
    block_axis: AxisRef
    block_index: int
    start: int
    stop: int
    total: int
    schedule_sha256: str
    technical_status: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _token(self.target_id, "target_id"))
        object.__setattr__(
            self,
            "schedule_id",
            _token(self.schedule_id, "schedule_id"),
        )
        if not isinstance(self.replicate_axis, AxisRef) or not isinstance(
            self.block_axis,
            AxisRef,
        ):
            raise RecordError("pPAM permutation block axes must be AxisRef values")
        if (
            type(self.block_index) is not int
            or type(self.start) is not int
            or type(self.stop) is not int
            or type(self.total) is not int
            or self.total != self.replicate_axis.count
            or self.start != self.block_index * RESAMPLING_REPLICATE_BLOCK_SIZE
            or self.stop
            != min(self.start + RESAMPLING_REPLICATE_BLOCK_SIZE, self.total)
        ):
            raise RecordError("pPAM permutation block interval is not canonical")
        if self.block_axis != resampling_block_axis(
            self.replicate_axis,
            self.start,
            self.stop,
        ):
            raise RecordError("pPAM permutation block axis does not match its interval")
        object.__setattr__(
            self,
            "schedule_sha256",
            _sha256(self.schedule_sha256, "schedule_sha256"),
        )
        status = _token(self.technical_status, "technical_status").lower()
        if status not in {"completed", "completed_with_nonfinite_replicates"}:
            raise RecordError("pPAM permutation block technical status is unsupported")
        object.__setattr__(self, "technical_status", status)
        artifacts = tuple(self.artifacts)
        if len(artifacts) != 1 or not isinstance(artifacts[0], ArtifactRef):
            raise RecordError(
                "pPAM permutation block requires one null-statistic artifact"
            )
        null = artifacts[0]
        if (
            null.kind != "ppam_permutation_null_statistics_block"
            or null.dtype != "float64"
            or null.shape != (self.block_axis.count,)
            or null.axis_refs != (self.block_axis,)
            or null.units != "loocv_spearman_rho"
            or null.space is not None
        ):
            raise RecordError(
                "pPAM permutation block artifact does not match the block axis"
            )
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"ppam_permutation_block_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class BootstrapBlockRecord:
    """Durable mergeable state for one canonical bootstrap interval."""

    target_id: str
    schedule_id: str
    feature_axis: AxisRef
    feature_space: str
    replicate_axis: AxisRef
    block_axis: AxisRef
    block_index: int
    start: int
    stop: int
    total: int
    schedule_sha256: str
    selection_mode: str
    nuisance_evidence_mode: str
    technical_status: str
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _token(self.target_id, "target_id"))
        object.__setattr__(
            self,
            "schedule_id",
            _token(self.schedule_id, "schedule_id"),
        )
        if not isinstance(self.feature_axis, AxisRef) or not isinstance(
            self.replicate_axis,
            AxisRef,
        ) or not isinstance(self.block_axis, AxisRef):
            raise RecordError("bootstrap block axes must be AxisRef values")
        object.__setattr__(
            self,
            "feature_space",
            _token(self.feature_space, "feature_space"),
        )
        if (
            type(self.block_index) is not int
            or type(self.start) is not int
            or type(self.stop) is not int
            or type(self.total) is not int
            or self.total != self.replicate_axis.count
            or self.start != self.block_index * RESAMPLING_REPLICATE_BLOCK_SIZE
            or self.stop
            != min(self.start + RESAMPLING_REPLICATE_BLOCK_SIZE, self.total)
        ):
            raise RecordError("bootstrap block interval is not canonical")
        if self.block_axis != resampling_block_axis(
            self.replicate_axis,
            self.start,
            self.stop,
        ):
            raise RecordError("bootstrap block axis does not match its interval")
        object.__setattr__(
            self,
            "schedule_sha256",
            _sha256(self.schedule_sha256, "schedule_sha256"),
        )
        selection_mode = _token(self.selection_mode, "selection_mode").lower()
        if selection_mode not in {"none", "sweet_sour"}:
            raise RecordError("bootstrap block selection mode is unsupported")
        object.__setattr__(self, "selection_mode", selection_mode)
        nuisance_mode = _token(
            self.nuisance_evidence_mode,
            "nuisance_evidence_mode",
        ).lower()
        if nuisance_mode not in {"none", "complete_adjusted"}:
            raise RecordError("bootstrap block nuisance evidence mode is unsupported")
        object.__setattr__(self, "nuisance_evidence_mode", nuisance_mode)
        status = _token(self.technical_status, "technical_status").lower()
        if status not in {"completed", "completed_with_nonfinite_replicates"}:
            raise RecordError("bootstrap block technical status is unsupported")
        object.__setattr__(self, "technical_status", status)

        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RecordError("bootstrap block artifacts are invalid")
        by_kind = {item.kind: item for item in artifacts}
        if len(by_kind) != len(artifacts):
            raise RecordError("bootstrap block artifact kinds are duplicated")
        feature_specs = {
            "formal_bootstrap_weight_sum_block": ("float64", "coefficient_sum"),
            "formal_bootstrap_weight_square_sum_block": (
                "float64",
                "coefficient_squared_sum",
            ),
            "formal_bootstrap_finite_weight_count_block": ("int64", "count"),
            "formal_bootstrap_candidate_count_block": ("int64", "count"),
            "formal_bootstrap_positive_count_block": ("int64", "count"),
            "formal_bootstrap_negative_count_block": ("int64", "count"),
        }
        if selection_mode == "sweet_sour":
            feature_specs.update(
                {
                    "formal_bootstrap_sweet_count_block": ("int64", "count"),
                    "formal_bootstrap_sour_count_block": ("int64", "count"),
                }
            )
        replicate_specs = {
            "formal_bootstrap_replicate_candidate_count_block": (
                "int64",
                "count",
            ),
            "formal_bootstrap_replicate_valid_weight_count_block": (
                "int64",
                "count",
            ),
            "formal_bootstrap_replicate_support_code_block": (
                "int8",
                "ordinal_code",
            ),
        }
        expected_kinds = {
            *feature_specs,
            *replicate_specs,
            "formal_bootstrap_evidence_block",
        }
        if set(by_kind) != expected_kinds:
            raise RecordError("bootstrap block artifact closure is incomplete")
        for kind, (dtype, units) in feature_specs.items():
            artifact = by_kind[kind]
            if (
                artifact.dtype != dtype
                or artifact.shape != (self.feature_axis.count,)
                or artifact.axis_refs != (self.feature_axis,)
                or artifact.units != units
                or artifact.space != self.feature_space
            ):
                raise RecordError(
                    f"bootstrap block feature artifact {kind!r} is invalid"
                )
        for kind, (dtype, units) in replicate_specs.items():
            artifact = by_kind[kind]
            if (
                artifact.dtype != dtype
                or artifact.shape != (self.block_axis.count,)
                or artifact.axis_refs != (self.block_axis,)
                or artifact.units != units
                or artifact.space is not None
            ):
                raise RecordError(
                    f"bootstrap block replicate artifact {kind!r} is invalid"
                )
        evidence = by_kind["formal_bootstrap_evidence_block"]
        if (
            evidence.schema_version != "dual_frequency_document_v1"
            or evidence.dtype is not None
            or evidence.shape is not None
            or evidence.axis_refs
            or evidence.axis_hashes
            or evidence.units is not None
            or evidence.space is not None
        ):
            raise RecordError("bootstrap block evidence artifact is invalid")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"bootstrap_block_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class ScratchArrayRecord:
    """Persistable NPY header contract for one run-scoped scratch array."""

    name: str
    filename: str
    dtype: str
    shape: tuple[int, ...]
    fortran_order: bool
    nbytes: int

    def __post_init__(self) -> None:
        name = _token(self.name, "scratch array name").lower()
        if _REASON_CODE.fullmatch(name) is None:
            raise RecordError("scratch array name must be lower_snake_case")
        filename = _token(self.filename, "scratch array filename")
        path = PurePosixPath(filename)
        if path.is_absolute() or len(path.parts) != 1 or path.suffix != ".npy":
            raise RecordError("scratch array filename is unsafe")
        try:
            dtype = np.dtype(self.dtype)
        except (TypeError, ValueError) as error:
            raise RecordError("scratch array dtype is invalid") from error
        shape = tuple(self.shape)
        if not shape or any(type(value) is not int or value < 1 for value in shape):
            raise RecordError("scratch array shape is invalid")
        if type(self.fortran_order) is not bool:
            raise RecordError("scratch array order flag must be boolean")
        expected_nbytes = math.prod(shape) * dtype.itemsize
        if type(self.nbytes) is not int or self.nbytes != expected_nbytes:
            raise RecordError("scratch array byte count is inconsistent")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "dtype", dtype.name)
        object.__setattr__(self, "shape", shape)


@dataclass(frozen=True)
class FormalOperatorScratchRecord:
    """Non-artifact descriptor for one resumable formal-operator generation."""

    target_id: str
    model_family: str
    subject_axis: AxisRef
    feature_axis: AxisRef
    input_identity: str
    operator_schema: str
    technical_status: str
    generation_path: str
    arrays: tuple[ScratchArrayRecord, ...]
    total_nbytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _token(self.target_id, "target_id"))
        family = _token(self.model_family, "model_family").lower()
        if family not in {"direct_voxel", "normative_fiber"}:
            raise RecordError("formal operator scratch model family is unsupported")
        object.__setattr__(self, "model_family", family)
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.feature_axis,
            AxisRef,
        ):
            raise RecordError("formal operator scratch axes must be AxisRef values")
        object.__setattr__(
            self,
            "input_identity",
            _sha256(self.input_identity, "input_identity"),
        )
        schema = _token(self.operator_schema, "operator_schema")
        if schema != "dual_frequency_formal_operator_scratch_v1":
            raise RecordError("formal operator scratch schema is unsupported")
        object.__setattr__(self, "operator_schema", schema)
        status = _token(self.technical_status, "technical_status").lower()
        if status != "completed":
            raise RecordError("formal operator scratch status must be completed")
        object.__setattr__(self, "technical_status", status)
        generation = _token(self.generation_path, "generation_path")
        path = PurePosixPath(generation)
        historical_layout = (
            len(path.parts) == 3
            and path.parts[2].startswith("operator-generation-")
        )
        attempt_layout = (
            len(path.parts) == 4
            and path.parts[2].startswith("attempt-")
            and path.parts[3].startswith("operator-generation-")
        )
        if (
            path.is_absolute()
            or path.parts[0] != "work"
            or not path.parts[1].startswith("task_")
            or not (historical_layout or attempt_layout)
            or any(part in {".", ".."} for part in path.parts)
        ):
            raise RecordError(
                "formal operator scratch generation path is unsafe"
            )
        object.__setattr__(self, "generation_path", path.as_posix())
        arrays = tuple(self.arrays)
        if not arrays or not all(isinstance(item, ScratchArrayRecord) for item in arrays):
            raise RecordError("formal operator scratch arrays are invalid")
        if len({item.name for item in arrays}) != len(arrays):
            raise RecordError("formal operator scratch names are duplicated")
        if len({item.filename for item in arrays}) != len(arrays):
            raise RecordError("formal operator scratch filenames are duplicated")
        expected_nbytes = sum(item.nbytes for item in arrays)
        if type(self.total_nbytes) is not int or self.total_nbytes != expected_nbytes:
            raise RecordError("formal operator scratch total bytes are inconsistent")
        object.__setattr__(self, "arrays", arrays)

    @property
    def identifier(self) -> str:
        return f"formal_operator_scratch_{canonical_hash(asdict(self), length=20)}"


def _artifact_with_axes(
    value: ArtifactRef,
    field: str,
    expected_axes: tuple[AxisRef, ...],
) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise RecordError(f"{field} must be an ArtifactRef")
    if value.shape != tuple(axis.count for axis in expected_axes):
        raise RecordError(f"{field} must use the exact subject and feature axes")
    if value.axis_refs != expected_axes:
        raise RecordError(f"{field} must use the exact subject and feature axes")
    return value


@dataclass(frozen=True, order=True)
class SubjectExclusionRecord:
    """Generic reason-coded exclusion from one endpoint's fitted cohort."""

    subject_id: str
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _token(self.subject_id, "subject_id"))
        reason_code = _token(self.reason_code, "reason_code")
        if _REASON_CODE.fullmatch(reason_code) is None:
            raise RecordError("reason_code must be a generic lower_snake_case token")
        object.__setattr__(self, "reason_code", reason_code)


@dataclass(frozen=True)
class EndpointInputRecord:
    """Endpoint-local clinical candidates and exact scientific-ready inputs."""

    endpoint: EndpointKey
    readiness_status: str
    candidate_subject_ids: tuple[str, ...]
    included_subject_ids: tuple[str, ...]
    exclusions: tuple[SubjectExclusionRecord, ...]
    minimum_subjects: int
    subject_axis: AxisRef | None
    baseline: ArtifactRef | None
    outcome: ArtifactRef | None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        readiness = _token(self.readiness_status, "readiness_status")
        if readiness not in ENDPOINT_READINESS_STATUSES:
            raise RecordError(f"unsupported readiness_status {readiness!r}")
        object.__setattr__(self, "readiness_status", readiness)

        candidates = tuple(
            _token(value, "candidate subject ID")
            for value in self.candidate_subject_ids
        )
        included = tuple(
            _token(value, "included subject ID")
            for value in self.included_subject_ids
        )
        if not candidates:
            raise RecordError("candidate_subject_ids must be nonempty")
        if len(set(candidates)) != len(candidates):
            raise RecordError("candidate subject IDs must be unique")
        if len(set(included)) != len(included):
            raise RecordError("included subject IDs must be unique")
        included_set = set(included)
        if tuple(value for value in candidates if value in included_set) != included:
            raise RecordError("included subjects must preserve candidate order")
        object.__setattr__(self, "candidate_subject_ids", candidates)
        object.__setattr__(self, "included_subject_ids", included)

        exclusions = tuple(self.exclusions)
        if not all(isinstance(value, SubjectExclusionRecord) for value in exclusions):
            raise RecordError("exclusions must contain only SubjectExclusionRecord values")
        excluded_ids = tuple(value.subject_id for value in exclusions)
        expected_excluded_ids = tuple(
            value for value in candidates if value not in included_set
        )
        if excluded_ids != expected_excluded_ids:
            raise RecordError(
                "excluded subjects must exactly cover non-included candidates in candidate order"
            )
        object.__setattr__(self, "exclusions", exclusions)

        if type(self.minimum_subjects) is not int or self.minimum_subjects < 1:
            raise RecordError("minimum_subjects must be a positive integer")
        if readiness == "ready" and len(included) < self.minimum_subjects:
            raise RecordError(
                "ready endpoint inputs require included count to meet minimum_subjects"
            )
        if (
            readiness == "insufficient_subjects"
            and len(included) >= self.minimum_subjects
        ):
            raise RecordError(
                "insufficient_subjects requires included count below minimum_subjects"
            )
        if readiness == "input_failure" and included:
            raise RecordError("input_failure endpoint inputs cannot include fitted subjects")

        aligned_values = (self.subject_axis, self.baseline, self.outcome)
        if not included:
            if any(value is not None for value in aligned_values):
                raise RecordError(
                    "endpoint inputs without included subjects cannot declare aligned artifacts"
                )
            return
        if not isinstance(self.subject_axis, AxisRef):
            raise RecordError("included endpoint inputs require a subject_axis")
        if self.subject_axis.count != len(included):
            raise RecordError("subject_axis count must match included_subject_ids")
        if self.baseline is None or self.outcome is None:
            raise RecordError(
                "included endpoint inputs require baseline and outcome artifacts"
            )
        _artifact_with_axes(self.baseline, "baseline", (self.subject_axis,))
        _artifact_with_axes(self.outcome, "outcome", (self.subject_axis,))

    @property
    def identifier(self) -> str:
        return f"endpoint_input_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class PreparedExposureRecord:
    """Prepared endpoint exposure and its complete resume-safe auxiliaries."""

    endpoint: EndpointKey
    subject_axis: AxisRef
    feature_axis: AxisRef
    exposure: ArtifactRef
    feature_ids: ArtifactRef
    delta_reference_input_status: str
    delta_reference_reason_code: str
    auxiliary_readiness: ArtifactRef | None
    reference_condition_exposure: ArtifactRef | None
    addon_reference_component_exposure: ArtifactRef | None
    reference_overlap_mask: ArtifactRef | None
    total_exposure: ArtifactRef | None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.feature_axis,
            AxisRef,
        ):
            raise RecordError("subject_axis and feature_axis must be AxisRef values")
        axes = (self.subject_axis, self.feature_axis)
        _artifact_with_axes(self.exposure, "exposure", axes)
        _artifact_with_axes(self.feature_ids, "feature_ids", (self.feature_axis,))
        if self.feature_ids.dtype != "int64":
            raise RecordError("canonical feature_ids must use int64 dtype")

        delta_status = _token(
            self.delta_reference_input_status,
            "delta_reference_input_status",
        )
        if delta_status not in DELTA_REFERENCE_INPUT_STATUSES:
            raise RecordError(
                f"unsupported delta_reference_input_status {delta_status!r}"
            )
        object.__setattr__(self, "delta_reference_input_status", delta_status)
        reason_code = _token(
            self.delta_reference_reason_code,
            "delta_reference_reason_code",
        )
        if _REASON_CODE.fullmatch(reason_code) is None:
            raise RecordError(
                "delta_reference_reason_code must be a lower_snake_case token"
            )
        object.__setattr__(self, "delta_reference_reason_code", reason_code)
        if self.auxiliary_readiness is not None:
            if not isinstance(self.auxiliary_readiness, ArtifactRef):
                raise RecordError("auxiliary_readiness must be an ArtifactRef or None")
            if self.auxiliary_readiness.shape is not None:
                raise RecordError("auxiliary_readiness must be a document artifact")

        auxiliary_fields = (
            "reference_condition_exposure",
            "addon_reference_component_exposure",
            "reference_overlap_mask",
            "total_exposure",
        )
        delta_reference_fields = (
            "reference_condition_exposure",
            "addon_reference_component_exposure",
        )
        if self.endpoint.model_family.startswith("reference_"):
            if delta_status != "not_applicable":
                raise RecordError(
                    "reference exposure requires delta_reference_input_status='not_applicable'"
                )
            if self.auxiliary_readiness is not None:
                raise RecordError("reference exposure cannot declare auxiliary_readiness")
            if any(getattr(self, field) is not None for field in auxiliary_fields):
                raise RecordError("reference exposure cannot declare add-on auxiliaries")
        else:
            if self.auxiliary_readiness is None:
                raise RecordError("add-on exposure requires auxiliary_readiness evidence")
            missing = tuple(
                field
                for field in delta_reference_fields
                if getattr(self, field) is None
            )
            if delta_status == "ready" and missing:
                raise RecordError(
                    "Delta-ready add-on exposure requires both Delta input artifacts"
                )
            for field in auxiliary_fields:
                value = getattr(self, field)
                if value is not None:
                    _artifact_with_axes(value, field, axes)
            if self.reference_overlap_mask is not None:
                if self.reference_overlap_mask.dtype != "bool":
                    raise RecordError("reference_overlap_mask must use bool dtype")
                if self.reference_overlap_mask.units != "binary":
                    raise RecordError("reference_overlap_mask must use binary units")

    @property
    def primary_exposure(self) -> ArtifactRef:
        """Return the prepared primary exposure used by observed and formal fits."""
        return self.exposure

    @property
    def identifier(self) -> str:
        return f"prepared_exposure_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class SourceRecord:
    """Endpoint-specific source resolver and prediction classification."""

    endpoint: EndpointKey
    input_status: str
    source_status: str
    prediction_status: str
    threshold_source: str
    selected_tau: float | None
    selected_coverage: int | None
    adjacent_support: int | None
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        for field in ("input_status", "source_status", "prediction_status", "threshold_source"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if self.input_status not in SOURCE_INPUT_STATUSES:
            raise RecordError(f"unsupported source input_status {self.input_status!r}")
        if self.source_status not in SOURCE_STATUSES:
            raise RecordError(f"unsupported source_status {self.source_status!r}")
        if self.threshold_source not in THRESHOLD_SOURCES:
            raise RecordError(f"unsupported threshold_source {self.threshold_source!r}")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RecordError("artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

        if self.selected_tau is not None:
            selected_tau = float(self.selected_tau)
            if not math.isfinite(selected_tau) or selected_tau <= 0:
                raise RecordError("selected_tau must be finite and positive")
            object.__setattr__(self, "selected_tau", selected_tau)
        if self.selected_coverage is not None:
            selected_coverage = int(self.selected_coverage)
            if selected_coverage < 1:
                raise RecordError("selected_coverage must be positive")
            object.__setattr__(self, "selected_coverage", selected_coverage)
        if self.adjacent_support is not None:
            adjacent_support = int(self.adjacent_support)
            if adjacent_support < 0:
                raise RecordError("adjacent_support must be nonnegative")
            object.__setattr__(self, "adjacent_support", adjacent_support)
        if self.feature_axis is not None and not isinstance(self.feature_axis, FeatureAxisRef):
            raise RecordError("feature_axis must be a FeatureAxisRef or None")

        if self.source_status in ACCEPTED_SOURCE_STATUSES:
            if self.input_status != "valid":
                raise RecordError("accepted source requires valid input")
            if self.prediction_status not in PREDICTION_STATUSES:
                raise RecordError("accepted source requires an error-prediction classification")
            if self.selected_tau is None or self.selected_coverage is None:
                raise RecordError("accepted source requires selected tau and coverage")
            if self.adjacent_support is None or self.feature_axis is None:
                raise RecordError("accepted source requires adjacent support and a feature axis")
            if not artifacts:
                raise RecordError("accepted source requires scientific artifacts")
            if not any(self.feature_axis.axis.sha256 in artifact.axis_hashes for artifact in artifacts):
                raise RecordError("accepted source artifacts must bind the selected feature axis")
        else:
            if self.prediction_status != "not_applicable":
                raise RecordError("absent source requires prediction_status='not_applicable'")
            if any(value is not None for value in (self.selected_tau, self.selected_coverage, self.feature_axis)):
                raise RecordError("absent source cannot select tau, coverage, or a feature axis")

    @property
    def identifier(self) -> str:
        return f"source_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class DeltaReferenceBundle:
    """Leakage-safe reference-score input for an add-on endpoint."""

    input_status: str
    support_status: str
    selected_reference_tau: float | None
    selected_reference_coverage: int | None
    full_scores: ArtifactRef | None
    fold_scores: ArtifactRef | None
    support_rows: ArtifactRef | None
    support_qc: ArtifactRef | None = None
    failure_stage: str = "none"
    failure_detail: str = "none"

    def __post_init__(self) -> None:
        for field in ("input_status", "support_status", "failure_stage", "failure_detail"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if self.input_status not in DELTA_INPUT_STATUSES:
            raise RecordError(f"unsupported DeltaReferenceScore input_status {self.input_status!r}")
        if self.support_status not in DELTA_SUPPORT_STATUSES:
            raise RecordError(f"unsupported DeltaReferenceScore support_status {self.support_status!r}")
        if self.selected_reference_tau is not None:
            tau = float(self.selected_reference_tau)
            if not math.isfinite(tau) or tau <= 0:
                raise RecordError("selected_reference_tau must be finite and positive")
            object.__setattr__(self, "selected_reference_tau", tau)
        if self.selected_reference_coverage is not None:
            coverage = int(self.selected_reference_coverage)
            if coverage < 1:
                raise RecordError("selected_reference_coverage must be positive")
            object.__setattr__(self, "selected_reference_coverage", coverage)
        for field in ("full_scores", "fold_scores", "support_rows", "support_qc"):
            value = getattr(self, field)
            if value is not None and not isinstance(value, ArtifactRef):
                raise RecordError(f"{field} must be an ArtifactRef or None")
        if self.input_status == "valid" and self.support_status in {"adequate", "limited"}:
            if not self._valid_payload():
                raise RecordError("valid DeltaReferenceScore input requires aligned full/fold/support artifacts")
        elif self.input_status == "valid":
            raise RecordError("valid DeltaReferenceScore input requires adequate or limited support")
        elif self.support_status.startswith("invalid_") and (
            self.support_rows is None or self.support_qc is None
        ):
            raise RecordError(
                "support-invalid DeltaReferenceScore input requires support rows and QC"
            )

    def _valid_payload(self) -> bool:
        if self.selected_reference_tau is None or self.selected_reference_coverage is None:
            return False
        if (
            self.full_scores is None
            or self.fold_scores is None
            or self.support_rows is None
            or self.support_qc is None
        ):
            return False
        if self.full_scores.shape is None or self.fold_scores.shape is None or self.support_rows.shape is None:
            return False
        if len(self.full_scores.shape) != 1:
            return False
        n_subjects = self.full_scores.shape[0]
        if self.fold_scores.shape != (n_subjects, n_subjects):
            return False
        subject_hash = self.full_scores.axis_hashes[0]
        if self.fold_scores.axis_hashes != (subject_hash, subject_hash):
            return False
        return bool(self.support_rows.axis_hashes) and self.support_rows.axis_hashes[0] == subject_hash

    @property
    def valid(self) -> bool:
        if self.input_status != "valid" or self.support_status not in {"adequate", "limited"}:
            return False
        return self._valid_payload()

    @property
    def identifier(self) -> str:
        return f"delta_reference_{canonical_hash(asdict(self), length=20)}"


_REFERENCE_SOURCE_UNSET = object()


@dataclass(frozen=True, init=False)
class ReferenceDependencyRecord:
    """Explicit add-on dependency on one matched reference endpoint."""

    addon_endpoint: EndpointKey
    matched_reference_endpoint_id: str
    dependency_status: str
    reference_record: SourceRecord | SensitiveRecord | None
    delta_reference: DeltaReferenceBundle | None

    def __init__(
        self,
        addon_endpoint: EndpointKey,
        matched_reference_endpoint_id: str,
        dependency_status: str,
        reference_record: SourceRecord | SensitiveRecord | None = None,
        delta_reference: DeltaReferenceBundle | None = None,
        *,
        reference_source: SourceRecord | None | object = _REFERENCE_SOURCE_UNSET,
    ) -> None:
        if reference_source is not _REFERENCE_SOURCE_UNSET:
            if reference_source is not None and not isinstance(
                reference_source,
                SourceRecord,
            ):
                raise RecordError(
                    "legacy reference_source must be a SourceRecord or None"
                )
            if reference_record is not None:
                raise RecordError(
                    "reference_record and legacy reference_source cannot both be supplied"
                )
            reference_record = reference_source
        object.__setattr__(self, "addon_endpoint", addon_endpoint)
        object.__setattr__(
            self,
            "matched_reference_endpoint_id",
            matched_reference_endpoint_id,
        )
        object.__setattr__(self, "dependency_status", dependency_status)
        object.__setattr__(self, "reference_record", reference_record)
        object.__setattr__(self, "delta_reference", delta_reference)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(
            self.addon_endpoint,
            EndpointKey,
        ) or not self.addon_endpoint.model_family.startswith("addon_"):
            raise RecordError("addon_endpoint must identify an add-on model")
        object.__setattr__(
            self,
            "matched_reference_endpoint_id",
            _token(
                self.matched_reference_endpoint_id,
                "matched_reference_endpoint_id",
            ),
        )
        object.__setattr__(
            self,
            "dependency_status",
            _token(self.dependency_status, "dependency_status"),
        )
        if self.dependency_status not in DEPENDENCY_STATUSES:
            raise RecordError(f"unsupported dependency_status {self.dependency_status!r}")
        if self.reference_record is not None and not isinstance(
            self.reference_record,
            (SourceRecord, SensitiveRecord),
        ):
            raise RecordError(
                "reference_record must be a SourceRecord, SensitiveRecord, or None"
            )
        if self.delta_reference is not None and not isinstance(
            self.delta_reference,
            DeltaReferenceBundle,
        ):
            raise RecordError("delta_reference must be a DeltaReferenceBundle or None")
        if self.reference_record is not None:
            reference_endpoint = self.reference_record.endpoint
            expected_family = self.addon_endpoint.model_family.replace(
                "addon_",
                "reference_",
                1,
            )
            if reference_endpoint.identifier != self.matched_reference_endpoint_id:
                raise RecordError(
                    "reference record does not match the declared endpoint dependency"
                )
            if reference_endpoint.scale_id != self.addon_endpoint.scale_id:
                raise RecordError("reference and add-on dependency scale IDs must match")
            if reference_endpoint.model_family != expected_family:
                raise RecordError("reference and add-on dependency model families must match")
            if reference_endpoint.connectome_id != self.addon_endpoint.connectome_id:
                raise RecordError("reference and add-on dependency connectomes must match")
            if isinstance(
                self.reference_record,
                SensitiveRecord,
            ) and not expected_family.endswith("fiber"):
                raise RecordError(
                    "SensitiveRecord dependencies are valid only for normative-fiber endpoints"
                )

    @property
    def reference_source(self) -> SourceRecord | SensitiveRecord | None:
        """Return the former dependency attribute for transitional callers."""
        return self.reference_record

    @property
    def identifier(self) -> str:
        return f"dependency_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class BranchRecord:
    """Independent source and design result for one add-on branch."""

    endpoint: EndpointKey
    branch: str
    intended_role: str
    input_status: str
    nuisance_design_status: str
    source: SourceRecord | None
    artifacts: tuple[ArtifactRef, ...] = ()
    failure_stage: str = "none"
    failure_detail: str = "none"

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey) or not self.endpoint.model_family.startswith("addon_"):
            raise RecordError("branch endpoint must identify an add-on model")
        for field in (
            "branch",
            "intended_role",
            "input_status",
            "nuisance_design_status",
            "failure_stage",
            "failure_detail",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if self.branch not in {"no_delta_reference", "delta_reference_adjusted"}:
            raise RecordError(f"unsupported add-on branch {self.branch!r}")
        if self.intended_role not in BRANCH_ROLES:
            raise RecordError(f"unsupported intended_role {self.intended_role!r}")
        if self.input_status not in BRANCH_INPUT_STATUSES:
            raise RecordError(f"unsupported branch input_status {self.input_status!r}")
        if self.nuisance_design_status not in NUISANCE_DESIGN_STATUSES:
            raise RecordError(
                f"unsupported nuisance_design_status {self.nuisance_design_status!r}"
            )
        if self.source is not None and self.source.endpoint != self.endpoint:
            raise RecordError("branch source endpoint does not match branch endpoint")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RecordError("branch artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"branch_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class FinalModelRecord:
    """Unique primary or one-way fallback realization for an endpoint."""

    endpoint: EndpointKey
    final_status: str
    realization_role: str
    final_key: FinalModelKey | None
    selected_source: SourceRecord | None
    selected_branch: BranchRecord | None
    artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        object.__setattr__(self, "final_status", _token(self.final_status, "final_status"))
        object.__setattr__(self, "realization_role", _token(self.realization_role, "realization_role"))
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RecordError("final artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)
        expected_roles = {
            "final_model_realized": "primary",
            "fallback_final_realized": "fallback_final",
        }
        if self.final_status not in expected_roles:
            raise RecordError("FinalModelRecord requires a realized primary or fallback status")
        if self.realization_role != expected_roles[self.final_status]:
            raise RecordError("final realization role does not match final status")
        if self.final_key is None:
            raise RecordError("realized final requires a final key")
        if self.final_key.endpoint_id != self.endpoint.identifier:
            raise RecordError("final key endpoint does not match final record endpoint")
        if self.endpoint.model_family.startswith("reference_"):
            if self.final_status != "final_model_realized":
                raise RecordError("reference models cannot be fallback finals")
            if self.selected_source is None or self.selected_branch is not None:
                raise RecordError("reference final requires only a selected source")
            if self.selected_source.endpoint != self.endpoint:
                raise RecordError("selected source endpoint does not match final record endpoint")
            if self.selected_source.source_status not in ACCEPTED_SOURCE_STATUSES:
                raise RecordError("reference final requires an accepted source")
            self._validate_final_key(
                branch="reference",
                source=self.selected_source,
            )
        else:
            if self.selected_branch is None or self.selected_source is not None:
                raise RecordError("add-on final requires only a selected branch")
            if self.selected_branch.endpoint != self.endpoint:
                raise RecordError("selected branch endpoint does not match final record endpoint")
            if (
                self.selected_branch.source is None
                or self.selected_branch.source.source_status not in ACCEPTED_SOURCE_STATUSES
            ):
                raise RecordError("add-on final requires an accepted branch source")
            self._validate_final_key(
                branch=self.selected_branch.branch,
                source=self.selected_branch.source,
            )

    def _validate_final_key(self, *, branch: str, source: SourceRecord) -> None:
        if self.final_key is None:
            raise RecordError("realized final requires a final key")
        if self.final_key.final_branch != branch:
            raise RecordError("final key branch does not match the selected source or branch")
        if self.final_key.selected_tau != source.selected_tau:
            raise RecordError("final key tau does not match the selected source")
        if self.final_key.selected_coverage != source.selected_coverage:
            raise RecordError("final key coverage does not match the selected source")

    @property
    def valid_feature_axis(self) -> FeatureAxisRef:
        """Return the locked valid axis inherited by all final-linked tasks."""
        source = self.selected_source
        if source is None and self.selected_branch is not None:
            source = self.selected_branch.source
        if source is None or source.feature_axis is None:
            raise RecordError("realized final model has no selected feature axis")
        return source.feature_axis

    @property
    def feature_axis(self) -> FeatureAxisRef:
        """Backward-compatible alias for the locked valid feature axis."""
        return self.valid_feature_axis

    @property
    def identifier(self) -> str:
        return f"final_record_{canonical_hash(asdict(self), length=20)}"


def _reason_codes(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    output = tuple(_token(value, field) for value in values)
    if not output:
        raise RecordError(f"{field} must be nonempty")
    if any(_REASON_CODE.fullmatch(value) is None for value in output):
        raise RecordError(f"{field} must contain lower_snake_case tokens")
    if len(set(output)) != len(output):
        raise RecordError(f"{field} must be unique")
    return tuple(sorted(output))


def _causal_task_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    output = tuple(_token(value, "causal task ID") for value in values)
    if len(set(output)) != len(output):
        raise RecordError("causal_task_ids must be unique")
    return tuple(sorted(output))


@dataclass(frozen=True)
class FinalSelectionRecord:
    """Scientific final-selection output, including valid no-model states."""

    endpoint: EndpointKey
    selection_status: str
    final_model: FinalModelRecord | None
    reason_codes: tuple[str, ...]
    causal_task_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        status = _token(self.selection_status, "selection_status")
        if status not in FINAL_SELECTION_STATUSES:
            raise RecordError(f"unsupported selection_status {status!r}")
        object.__setattr__(self, "selection_status", status)
        object.__setattr__(
            self,
            "reason_codes",
            _reason_codes(tuple(self.reason_codes), "reason_codes"),
        )
        object.__setattr__(
            self,
            "causal_task_ids",
            _causal_task_ids(tuple(self.causal_task_ids)),
        )

        realized_statuses = {
            "final_model_realized": "final_model_realized",
            "fallback_final_realized": "fallback_final_realized",
        }
        if status in realized_statuses:
            if not isinstance(self.final_model, FinalModelRecord):
                raise RecordError(f"{status} requires a final_model")
            if self.final_model.endpoint != self.endpoint:
                raise RecordError("final selection endpoint must match final_model endpoint")
            if self.final_model.final_status != realized_statuses[status]:
                raise RecordError(
                    "final selection status must agree with final_model final_status"
                )
        elif self.final_model is not None:
            raise RecordError(f"{status} forbids a final_model")

    @property
    def identifier(self) -> str:
        return f"final_selection_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class FinalDecisionRecord:
    """Aggregate-only terminal authority for one requested endpoint."""

    endpoint: EndpointKey
    decision_status: str
    final_model: FinalModelRecord | None
    reason_code: str
    causal_task_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey):
            raise RecordError("endpoint must be an EndpointKey")
        status = _token(self.decision_status, "decision_status")
        if status not in FINAL_DECISION_STATUSES:
            raise RecordError(f"unsupported decision_status {status!r}")
        object.__setattr__(self, "decision_status", status)
        reason_code = _token(self.reason_code, "reason_code")
        if _REASON_CODE.fullmatch(reason_code) is None:
            raise RecordError("reason_code must be a lower_snake_case token")
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(
            self,
            "causal_task_ids",
            _causal_task_ids(tuple(self.causal_task_ids)),
        )

        realized_statuses = {
            "realized_primary": "final_model_realized",
            "realized_fallback": "fallback_final_realized",
        }
        if status in realized_statuses:
            if not isinstance(self.final_model, FinalModelRecord):
                raise RecordError(f"{status} requires a final_model")
            if self.final_model.endpoint != self.endpoint:
                raise RecordError("final decision endpoint must match final_model endpoint")
            if self.final_model.final_status != realized_statuses[status]:
                raise RecordError(
                    "final decision status must agree with final_model final_status"
                )
        elif self.final_model is not None:
            raise RecordError(f"{status} decisions forbid a final_model")

    @property
    def identifier(self) -> str:
        return f"final_decision_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class SensitiveRecord:
    """Evidence at the formal source cell for a sensitive connectome."""

    endpoint: EndpointKey
    formal_endpoint_id: str
    evaluated_tau: float
    evaluated_coverage: int
    input_status: str
    cell_computability_status: str
    prediction_status: str
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey) or not self.endpoint.model_family.endswith("fiber"):
            raise RecordError("sensitivity evidence requires a normative-fiber endpoint")
        object.__setattr__(self, "formal_endpoint_id", _token(self.formal_endpoint_id, "formal_endpoint_id"))
        object.__setattr__(self, "input_status", _token(self.input_status, "input_status"))
        object.__setattr__(
            self,
            "cell_computability_status",
            _token(self.cell_computability_status, "cell_computability_status"),
        )
        object.__setattr__(self, "prediction_status", _token(self.prediction_status, "prediction_status"))
        if self.input_status not in SOURCE_INPUT_STATUSES:
            raise RecordError(f"unsupported sensitive input_status {self.input_status!r}")
        if self.cell_computability_status not in SENSITIVE_CELL_COMPUTABILITY_STATUSES:
            raise RecordError(
                "cell_computability_status must be 'computable' or 'not_computable'"
            )
        if self.cell_computability_status == "computable":
            if self.input_status != "valid":
                raise RecordError("computable sensitive evidence requires valid input")
            if self.prediction_status not in PREDICTION_STATUSES:
                raise RecordError(
                    "computable sensitive evidence requires an error-prediction classification"
                )
            if not isinstance(self.feature_axis, FeatureAxisRef):
                raise RecordError("computable sensitive evidence requires a feature axis")
        elif self.prediction_status != "not_applicable":
            raise RecordError(
                "noncomputable sensitive evidence requires prediction_status='not_applicable'"
            )
        if self.feature_axis is not None and not isinstance(self.feature_axis, FeatureAxisRef):
            raise RecordError("feature_axis must be a FeatureAxisRef or None")
        if self.input_status != "valid" and self.feature_axis is not None:
            raise RecordError("invalid sensitive input cannot declare a feature axis")
        tau = float(self.evaluated_tau)
        coverage = int(self.evaluated_coverage)
        if not math.isfinite(tau) or tau <= 0 or coverage < 1:
            raise RecordError("sensitivity evidence requires positive tau and coverage")
        object.__setattr__(self, "evaluated_tau", tau)
        object.__setattr__(self, "evaluated_coverage", coverage)
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactRef) for item in artifacts):
            raise RecordError("sensitivity artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)

    @property
    def identifier(self) -> str:
        return f"sensitive_{canonical_hash(asdict(self), length=20)}"
