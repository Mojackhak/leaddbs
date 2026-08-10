"""Shared typed inputs and deterministic resampling utilities for formal backends."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import platform
from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ArtifactRef,
    AxisRef,
    BootstrapNuisanceEvidence,
    FormalRequest,
    RESAMPLING_REPLICATE_BLOCK_SIZE,
    canonical_hash,
)
from ...contracts.requests import ScientificInput
from ..nuisance import (
    ADJUSTED_BRANCH,
    NuisancePlan,
    NuisancePlanError,
    build_addon_nuisance_plan,
)
from ..protocols import (
    BootstrapNuisanceProvider,
    BootstrapNuisanceSampleNotEstimableError,
)
from ..statistics import safe_correlation


class FormalBackendError(RuntimeError):
    """Raised when formal inference cannot complete without violating its contract."""


class FormalBackendInputError(FormalBackendError):
    """Raised before publication when a formal input is missing or inconsistent."""


class BootstrapReplicateNotEstimableError(FormalBackendInputError):
    """Raised when one valid bootstrap draw has a non-estimable nuisance design."""

    def __init__(self, detail: str) -> None:
        normalized = str(detail).strip()
        if not normalized:
            normalized = "sample-specific nuisance design is not estimable"
        self.detail = normalized
        super().__init__(normalized)


FORMAL_REPLICATE_BLOCK_SIZE = RESAMPLING_REPLICATE_BLOCK_SIZE
RNG_SCHEDULE_SCHEMA = "dual_frequency_resampling_schedule_v1"


@dataclass(frozen=True, slots=True)
class ReplicateBlock:
    """One immutable half-open interval over a complete replicate schedule."""

    index: int
    start: int
    stop: int
    total: int

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise FormalBackendInputError("replicate block index must be nonnegative")
        if (
            type(self.start) is not int
            or type(self.stop) is not int
            or type(self.total) is not int
            or self.start < 0
            or self.stop <= self.start
            or self.stop > self.total
        ):
            raise FormalBackendInputError("replicate block interval is invalid")

    @property
    def count(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True, slots=True)
class RngScheduleDescriptor:
    """Portable identity and environment evidence for one full RNG schedule."""

    schema_version: str
    schedule_kind: str
    seed: int
    subject_count: int
    replicate_count: int
    dtype: str
    generator_class: str
    bit_generator_class: str
    numpy_version: str
    environment_fingerprint: str
    schedule_sha256: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": self.schema_version,
            "schedule_kind": self.schedule_kind,
            "seed": self.seed,
            "subject_count": self.subject_count,
            "replicate_count": self.replicate_count,
            "dtype": self.dtype,
            "generator_class": self.generator_class,
            "bit_generator_class": self.bit_generator_class,
            "numpy_version": self.numpy_version,
            "environment_fingerprint": self.environment_fingerprint,
            "schedule_sha256": self.schedule_sha256,
        }


@dataclass(frozen=True, slots=True)
class ResamplingSchedule:
    """One complete historical schedule with immutable block views."""

    descriptor: RngScheduleDescriptor
    indices: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, RngScheduleDescriptor):
            raise FormalBackendInputError(
                "resampling schedule descriptor is invalid"
            )
        indices = np.array(self.indices, copy=True)
        expected_shape = (
            self.descriptor.replicate_count,
            self.descriptor.subject_count,
        )
        if indices.shape != expected_shape or indices.dtype.name != self.descriptor.dtype:
            raise FormalBackendInputError(
                "resampling schedule payload does not match its descriptor"
            )
        if _schedule_sha256(indices) != self.descriptor.schedule_sha256:
            raise FormalBackendInputError(
                "resampling schedule payload digest does not match its descriptor"
            )
        if self.descriptor.schedule_kind == "permutation":
            expected = np.arange(self.descriptor.subject_count, dtype=indices.dtype)
            if np.any(np.sort(indices, axis=1) != expected):
                raise FormalBackendInputError(
                    "permutation schedule rows must contain every subject once"
                )
        elif self.descriptor.schedule_kind == "bootstrap":
            if np.any(indices < 0) or np.any(indices >= self.descriptor.subject_count):
                raise FormalBackendInputError(
                    "bootstrap schedule indices are outside the subject axis"
                )
        else:
            raise FormalBackendInputError("resampling schedule kind is unsupported")
        indices.flags.writeable = False
        object.__setattr__(self, "indices", indices)

    def blocks(
        self,
        block_size: int = FORMAL_REPLICATE_BLOCK_SIZE,
    ) -> tuple[ReplicateBlock, ...]:
        return fixed_replicate_blocks(
            self.descriptor.replicate_count,
            block_size=block_size,
        )

    def block_view(self, block: ReplicateBlock) -> np.ndarray:
        if not isinstance(block, ReplicateBlock) or block.total != self.indices.shape[0]:
            raise FormalBackendInputError(
                "replicate block does not match the full schedule"
            )
        view = self.indices[block.start : block.stop]
        view.flags.writeable = False
        return view


@dataclass(frozen=True, slots=True)
class PermutationBlockComputation:
    """One schedule-bound null-statistic interval from an independent worker."""

    block: ReplicateBlock
    schedule_sha256: str
    null_statistics: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.block, ReplicateBlock):
            raise FormalBackendError("permutation block descriptor is invalid")
        digest = str(self.schedule_sha256).strip().lower()
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise FormalBackendError("permutation block schedule digest is invalid")
        null = np.array(self.null_statistics, dtype=np.float64, copy=True)
        if null.shape != (self.block.count,):
            raise FormalBackendError(
                "permutation block null length does not match its interval"
            )
        null.flags.writeable = False
        object.__setattr__(self, "schedule_sha256", digest)
        object.__setattr__(self, "null_statistics", null)


def _schedule_sha256(indices: np.ndarray) -> str:
    array = np.ascontiguousarray(indices)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(
        json.dumps(list(array.shape), separators=(",", ":")).encode("ascii")
    )
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def fixed_replicate_blocks(
    replicate_count: int,
    *,
    block_size: int = FORMAL_REPLICATE_BLOCK_SIZE,
) -> tuple[ReplicateBlock, ...]:
    """Partition a replicate axis independently of worker assignment."""

    if type(replicate_count) is not int or replicate_count < 1:
        raise FormalBackendInputError("replicate_count must be a positive integer")
    if type(block_size) is not int or block_size < 1:
        raise FormalBackendInputError("block_size must be a positive integer")
    return tuple(
        ReplicateBlock(
            index=index,
            start=start,
            stop=min(start + block_size, replicate_count),
            total=replicate_count,
        )
        for index, start in enumerate(range(0, replicate_count, block_size))
    )


def formal_resampling_schedule(
    schedule_kind: str,
    subject_count: int,
    replicate_count: int,
    seed: int,
) -> ResamplingSchedule:
    """Generate one complete schedule with the historical RNG call pattern."""

    kind = str(schedule_kind).strip().lower()
    if kind not in {"permutation", "bootstrap"}:
        raise FormalBackendInputError(
            "schedule_kind must be 'permutation' or 'bootstrap'"
        )
    if type(subject_count) is not int or subject_count < 1:
        raise FormalBackendInputError("subject_count must be a positive integer")
    if type(replicate_count) is not int or replicate_count < 1:
        raise FormalBackendInputError("replicate_count must be a positive integer")
    if type(seed) is not int:
        raise FormalBackendInputError("resampling seed must be an integer")
    generator = np.random.default_rng(seed)
    if kind == "permutation":
        indices = np.empty((replicate_count, subject_count), dtype=np.int32)
        for index in range(replicate_count):
            indices[index] = generator.permutation(subject_count)
    else:
        indices = generator.integers(
            0,
            subject_count,
            size=(replicate_count, subject_count),
            dtype=np.int64,
        )
    generator_class = f"{type(generator).__module__}.{type(generator).__name__}"
    bit_generator = generator.bit_generator
    bit_generator_class = (
        f"{type(bit_generator).__module__}.{type(bit_generator).__name__}"
    )
    environment_fingerprint = canonical_hash(
        {
            "numpy_version": np.__version__,
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "generator_class": generator_class,
            "bit_generator_class": bit_generator_class,
        }
    )
    descriptor = RngScheduleDescriptor(
        schema_version=RNG_SCHEDULE_SCHEMA,
        schedule_kind=kind,
        seed=seed,
        subject_count=subject_count,
        replicate_count=replicate_count,
        dtype=indices.dtype.name,
        generator_class=generator_class,
        bit_generator_class=bit_generator_class,
        numpy_version=np.__version__,
        environment_fingerprint=environment_fingerprint,
        schedule_sha256=_schedule_sha256(indices),
    )
    return ResamplingSchedule(descriptor=descriptor, indices=indices)


def validate_resampling_schedule(
    schedule: ResamplingSchedule,
    *,
    schedule_kind: str,
    subject_count: int,
    replicate_count: int,
    seed: int,
) -> None:
    """Require exact request identity for one parent-generated schedule."""

    if not isinstance(schedule, ResamplingSchedule):
        raise FormalBackendInputError("resampling schedule is invalid")
    descriptor = schedule.descriptor
    if (
        descriptor.schedule_kind != schedule_kind
        or descriptor.subject_count != subject_count
        or descriptor.replicate_count != replicate_count
        or descriptor.seed != seed
    ):
        raise FormalBackendInputError(
            "resampling schedule does not match the formal request"
        )


@dataclass(frozen=True, slots=True)
class PermutationComputation:
    """Observed prediction metrics and a deterministic permutation null."""

    observed_metrics: dict[str, float]
    null_statistics: np.ndarray
    p_plus_one_two_sided: float | None
    permutation_schedule: np.ndarray | None = None

    def __post_init__(self) -> None:
        null = np.array(self.null_statistics, dtype=np.float64, copy=True)
        if null.ndim != 1:
            raise FormalBackendError("permutation null statistics must be one-dimensional")
        if np.all(np.isfinite(null)):
            if (
                self.p_plus_one_two_sided is None
                or not math.isfinite(float(self.p_plus_one_two_sided))
                or not 0.0 < float(self.p_plus_one_two_sided) <= 1.0
            ):
                raise FormalBackendError(
                    "a complete finite permutation null requires a valid p value"
                )
        elif self.p_plus_one_two_sided is not None:
            raise FormalBackendError(
                "a permutation null with attrition cannot carry an inferential p value"
            )
        schedule = self.permutation_schedule
        if schedule is not None:
            schedule = np.array(schedule, dtype=np.int32, copy=True)
            if schedule.ndim != 2 or schedule.shape[0] != null.size:
                raise FormalBackendError(
                    "permutation schedule must be replicate-by-subject"
                )
            expected = np.arange(schedule.shape[1], dtype=np.int32)
            if np.any(np.sort(schedule, axis=1) != expected):
                raise FormalBackendError(
                    "every permutation schedule row must contain every subject once"
                )
            schedule.flags.writeable = False
            object.__setattr__(self, "permutation_schedule", schedule)
        null.flags.writeable = False
        object.__setattr__(self, "null_statistics", null)


@dataclass(frozen=True, slots=True)
class BootstrapComputation:
    """Aligned bootstrap weight, support, sign, and optional selection evidence."""

    weight_mean: np.ndarray
    weight_se: np.ndarray
    finite_weight_count: np.ndarray
    candidate_selection_frequency: np.ndarray
    positive_sign_frequency: np.ndarray
    negative_sign_frequency: np.ndarray
    replicate_candidate_count: np.ndarray
    replicate_valid_weight_count: np.ndarray
    replicate_support_code: np.ndarray
    finite_replicate_count: int
    replicate_weights: np.ndarray | None = None
    nonestimable_replicates: tuple[dict[str, Any], ...] = ()
    nuisance_evidence: tuple[dict[str, Any], ...] = ()
    sweet_selection_frequency: np.ndarray | None = None
    sour_selection_frequency: np.ndarray | None = None

    def __post_init__(self) -> None:
        arrays = (
            "weight_mean",
            "weight_se",
            "finite_weight_count",
            "candidate_selection_frequency",
            "positive_sign_frequency",
            "negative_sign_frequency",
            "replicate_candidate_count",
            "replicate_valid_weight_count",
            "replicate_support_code",
            "sweet_selection_frequency",
            "sour_selection_frequency",
        )
        feature_lengths: set[int] = set()
        replicate_lengths: set[int] = set()
        for field in arrays:
            value = getattr(self, field)
            if value is None:
                continue
            array = np.array(value, copy=True)
            if array.ndim != 1 or array.dtype == object:
                raise FormalBackendError(f"{field} must be a one-dimensional numeric array")
            array.flags.writeable = False
            object.__setattr__(self, field, array)
            if field.startswith("replicate_"):
                replicate_lengths.add(array.size)
            else:
                feature_lengths.add(array.size)
        if len(feature_lengths) != 1 or len(replicate_lengths) != 1:
            raise FormalBackendError(
                "bootstrap outputs must have exact and consistent feature/resample shapes"
            )
        replicate_count = next(iter(replicate_lengths))
        replicate_weights = self.replicate_weights
        if replicate_weights is not None:
            replicate_weights = np.array(
                replicate_weights,
                dtype=np.float64,
                copy=True,
            )
            if (
                replicate_weights.shape
                != (replicate_count, next(iter(feature_lengths)))
                or np.any(np.isinf(replicate_weights))
            ):
                raise FormalBackendError(
                    "bootstrap replicate_weights must be replicate-by-feature "
                    "without infinite values"
                )
            replicate_weights.flags.writeable = False
            object.__setattr__(
                self,
                "replicate_weights",
                replicate_weights,
            )
        evidence: list[dict[str, Any]] = []
        evidence_replicates: set[int] = set()
        for item in self.nuisance_evidence:
            row = dict(item)
            replicate = row.get("replicate")
            if (
                type(replicate) is not int
                or not 0 <= replicate < replicate_count
                or replicate in evidence_replicates
            ):
                raise FormalBackendError(
                    "bootstrap nuisance evidence has an invalid replicate index"
                )
            evidence_replicates.add(replicate)
            evidence.append(row)
        object.__setattr__(self, "nuisance_evidence", tuple(evidence))
        nonestimable: list[dict[str, Any]] = []
        seen_replicates: set[int] = set()
        for item in self.nonestimable_replicates:
            row = dict(item)
            replicate = row.get("replicate")
            reason_code = str(row.get("reason_code", "")).strip()
            detail = str(row.get("detail", "")).strip()
            if (
                type(replicate) is not int
                or not 0 <= replicate < replicate_count
                or replicate in seen_replicates
            ):
                raise FormalBackendError(
                    "bootstrap non-estimable evidence has an invalid replicate index"
                )
            if reason_code != "nonestimable_nuisance_design" or not detail:
                raise FormalBackendError(
                    "bootstrap non-estimable evidence has an invalid reason"
                )
            seen_replicates.add(replicate)
            nonestimable.append(
                {
                    "replicate": replicate,
                    "reason_code": reason_code,
                    "detail": detail,
                }
            )
        if evidence_replicates:
            if evidence_replicates & seen_replicates:
                raise FormalBackendError(
                    "bootstrap nuisance and non-estimable evidence overlap"
                )
            if evidence_replicates | seen_replicates != set(range(replicate_count)):
                raise FormalBackendError(
                    "adjusted bootstrap evidence does not cover every replicate"
                )
        object.__setattr__(self, "nonestimable_replicates", tuple(nonestimable))
        if type(self.finite_replicate_count) is not int or self.finite_replicate_count < 0:
            raise FormalBackendError("finite_replicate_count must be nonnegative")


@dataclass(frozen=True, slots=True)
class BootstrapBlockComputation:
    """Mergeable bootstrap accumulator state for one schedule interval."""

    block: ReplicateBlock
    schedule_sha256: str
    weight_sum: np.ndarray
    weight_square_sum: np.ndarray
    finite_weight_count: np.ndarray
    candidate_count: np.ndarray
    positive_count: np.ndarray
    negative_count: np.ndarray
    replicate_candidate_count: np.ndarray
    replicate_valid_weight_count: np.ndarray
    replicate_support_code: np.ndarray
    replicate_weights: np.ndarray | None = None
    require_complete_nuisance_evidence: bool = False
    nuisance_evidence: tuple[dict[str, Any], ...] = ()
    nonestimable_replicates: tuple[dict[str, Any], ...] = ()
    sweet_count: np.ndarray | None = None
    sour_count: np.ndarray | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.block, ReplicateBlock):
            raise FormalBackendError("bootstrap block descriptor is invalid")
        if type(self.require_complete_nuisance_evidence) is not bool:
            raise FormalBackendError(
                "bootstrap block nuisance evidence mode must be boolean"
            )
        digest = str(self.schedule_sha256).strip().lower()
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise FormalBackendError("bootstrap block schedule digest is invalid")
        object.__setattr__(self, "schedule_sha256", digest)

        feature_count: int | None = None
        for field in (
            "weight_sum",
            "weight_square_sum",
            "finite_weight_count",
            "candidate_count",
            "positive_count",
            "negative_count",
            "sweet_count",
            "sour_count",
        ):
            value = getattr(self, field)
            if value is None:
                continue
            dtype = np.float64 if field.startswith("weight_") else np.int64
            array = np.array(value, dtype=dtype, copy=True)
            if array.ndim != 1:
                raise FormalBackendError(
                    f"bootstrap block {field} must be one-dimensional"
                )
            if feature_count is None:
                feature_count = array.size
            elif array.size != feature_count:
                raise FormalBackendError(
                    "bootstrap block feature arrays have inconsistent lengths"
                )
            if field.startswith("weight_"):
                if not np.all(np.isfinite(array)):
                    raise FormalBackendError(
                        f"bootstrap block {field} must be finite"
                    )
            elif np.any(array < 0):
                raise FormalBackendError(
                    f"bootstrap block {field} cannot contain negative counts"
                )
            array.flags.writeable = False
            object.__setattr__(self, field, array)
        if feature_count is None or feature_count < 1:
            raise FormalBackendError("bootstrap block feature axis is empty")
        if (self.sweet_count is None) != (self.sour_count is None):
            raise FormalBackendError(
                "bootstrap block selection counts must be both present or absent"
            )
        if np.any(self.weight_square_sum < 0.0):
            raise FormalBackendError(
                "bootstrap block squared-weight sums cannot be negative"
            )
        if np.any(self.finite_weight_count > self.candidate_count):
            raise FormalBackendError(
                "bootstrap block finite counts exceed candidate counts"
            )
        if np.any(self.positive_count + self.negative_count > self.finite_weight_count):
            raise FormalBackendError(
                "bootstrap block sign counts exceed finite counts"
            )

        for field, dtype in (
            ("replicate_candidate_count", np.int64),
            ("replicate_valid_weight_count", np.int64),
            ("replicate_support_code", np.int8),
        ):
            array = np.array(getattr(self, field), dtype=dtype, copy=True)
            if array.shape != (self.block.count,):
                raise FormalBackendError(
                    f"bootstrap block {field} does not match its interval"
                )
            array.flags.writeable = False
            object.__setattr__(self, field, array)
        if np.any(self.replicate_candidate_count < 0) or np.any(
            self.replicate_valid_weight_count < 0
        ):
            raise FormalBackendError(
                "bootstrap block replicate counts cannot be negative"
            )
        if np.any(
            self.replicate_valid_weight_count > self.replicate_candidate_count
        ):
            raise FormalBackendError(
                "bootstrap block valid replicate counts exceed candidate counts"
            )
        if np.any(~np.isin(self.replicate_support_code, (0, 1, 2))):
            raise FormalBackendError("bootstrap block support codes are invalid")
        replicate_weights = self.replicate_weights
        if replicate_weights is not None:
            replicate_weights = np.array(
                replicate_weights,
                dtype=np.float64,
                copy=True,
            )
            if (
                replicate_weights.shape != (self.block.count, feature_count)
                or np.any(np.isinf(replicate_weights))
            ):
                raise FormalBackendError(
                    "bootstrap block replicate_weights must be "
                    "block-by-feature without infinite values"
                )
            replicate_weights.flags.writeable = False
            object.__setattr__(
                self,
                "replicate_weights",
                replicate_weights,
            )

        evidence_indices: set[int] = set()
        evidence: list[dict[str, Any]] = []
        for item in self.nuisance_evidence:
            row = dict(item)
            replicate = row.get("replicate")
            if (
                type(replicate) is not int
                or not self.block.start <= replicate < self.block.stop
                or replicate in evidence_indices
            ):
                raise FormalBackendError(
                    "bootstrap block nuisance evidence index is invalid"
                )
            evidence_indices.add(replicate)
            evidence.append(row)
        object.__setattr__(self, "nuisance_evidence", tuple(evidence))

        nonestimable_indices: set[int] = set()
        nonestimable: list[dict[str, Any]] = []
        for item in self.nonestimable_replicates:
            row = dict(item)
            replicate = row.get("replicate")
            if (
                type(replicate) is not int
                or not self.block.start <= replicate < self.block.stop
                or replicate in nonestimable_indices
                or replicate in evidence_indices
                or row.get("reason_code") != "nonestimable_nuisance_design"
                or not str(row.get("detail", "")).strip()
            ):
                raise FormalBackendError(
                    "bootstrap block non-estimable evidence is invalid"
                )
            nonestimable_indices.add(replicate)
            nonestimable.append(row)
        object.__setattr__(
            self,
            "nonestimable_replicates",
            tuple(nonestimable),
        )
        covered = evidence_indices | nonestimable_indices
        if self.require_complete_nuisance_evidence and covered != set(
            range(self.block.start, self.block.stop)
        ):
            raise FormalBackendError(
                "bootstrap block adjusted evidence does not cover its interval"
            )
        if not self.require_complete_nuisance_evidence and evidence_indices:
            raise FormalBackendError(
                "bootstrap block nuisance evidence is unexpected for this branch"
            )


def materialize_array(
    value: ScientificInput,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    expected_space: str | None,
    artifact_store: ArtifactStore | None,
    memory_map: bool = False,
) -> np.ndarray:
    """Materialize an already validated array input without discovering files."""

    if isinstance(value, np.ndarray):
        return np.asanyarray(value)
    if not isinstance(value, ArtifactRef):
        raise FormalBackendInputError(f"{name} must be an array or ArtifactRef")
    if artifact_store is None:
        raise FormalBackendInputError(
            f"{name} is artifact-backed but no ArtifactStore was injected"
        )
    if value.dtype is None or value.shape is None:
        raise FormalBackendInputError(f"{name} must reference an array artifact")
    return artifact_store.materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=value.shape,
        expected_axes=expected_axes,
        expected_units=expected_units,
        expected_space=expected_space,
        mmap_mode="r" if memory_map else None,
    )


def finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    """Return one finite float64 subject vector."""

    array = np.asarray(value)
    if (
        array.shape != (count,)
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.number)
        or np.iscomplexobj(array)
    ):
        raise FormalBackendInputError(f"{name} must be a real subject vector")
    output = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(output)):
        raise FormalBackendInputError(f"{name} must contain only finite values")
    return output


def finite_exposure(value: np.ndarray, request: FormalRequest) -> np.ndarray:
    """Return finite subject-by-feature exposure on the exact locked final axis."""

    array = np.asanyarray(value)
    expected = (request.subject_axis.count, request.feature_axis.count)
    if (
        array.shape != expected
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.number)
        or np.iscomplexobj(array)
    ):
        raise FormalBackendInputError(
            f"exposure must be a real array with exact final-axis shape {expected}"
        )
    for start in range(0, array.shape[1], 262_144):
        if not np.all(np.isfinite(np.asarray(array[:, start : start + 262_144]))):
            raise FormalBackendInputError("exposure must contain only finite values")
    return array


def canonical_fiber_ids(value: np.ndarray, count: int) -> np.ndarray:
    """Validate the exact ordered int64 IDs for a locked normative-fiber axis."""

    ids = np.asarray(value)
    if ids.shape != (count,) or ids.dtype != np.dtype(np.int64):
        raise FormalBackendInputError(
            "feature_ids must be an exact one-dimensional canonical int64 axis"
        )
    if np.unique(ids).size != ids.size:
        raise FormalBackendInputError("canonical feature_ids must be unique")
    output = np.array(ids, dtype=np.int64, copy=True)
    output.flags.writeable = False
    return output


def _design_valid(covariates: np.ndarray, rows: np.ndarray) -> bool:
    design = np.column_stack([np.ones(rows.size), covariates[rows]])
    return bool(
        rows.size > design.shape[1]
        and np.all(np.isfinite(design))
        and np.linalg.matrix_rank(design) == design.shape[1]
    )


def validate_nuisance_plan(plan: NuisancePlan) -> None:
    """Require an estimable nuisance-only model in full data and every LOOCV fold."""

    count = plan.full_covariates.shape[0]
    rows = np.arange(count, dtype=np.int64)
    if not _design_valid(plan.full_covariates, rows):
        raise FormalBackendInputError("full nuisance-only design is not estimable")
    for heldout in range(count):
        training = np.delete(rows, heldout)
        if not _design_valid(plan.fold_covariates[heldout], training):
            raise FormalBackendInputError(
                f"fold nuisance-only design is not estimable for held-out index {heldout}"
            )


def _reference_nuisance_plan(baseline: np.ndarray) -> NuisancePlan:
    full = np.asarray(baseline, dtype=np.float64)[:, None]
    folds = np.broadcast_to(full, (full.shape[0], *full.shape)).copy()
    plan = NuisancePlan(full_covariates=full, fold_covariates=folds)
    validate_nuisance_plan(plan)
    return plan


def build_fixed_nuisance_plan(
    request: FormalRequest,
    baseline: np.ndarray,
    delta_full: np.ndarray | None,
    delta_folds: np.ndarray | None,
) -> NuisancePlan:
    """Build the fixed full/fold nuisance plan used by observed and permutation fits."""

    branch = request.final_model.final_key.final_branch
    try:
        if request.final_model.endpoint.model_family.startswith("reference_"):
            plan = _reference_nuisance_plan(baseline)
        elif branch == ADJUSTED_BRANCH:
            plan = build_addon_nuisance_plan(
                baseline,
                branch,
                delta_full_scores=delta_full,
                delta_fold_scores=delta_folds,
            )
        else:
            plan = build_addon_nuisance_plan(baseline, branch)
    except NuisancePlanError as error:
        raise FormalBackendInputError(error.detail) from error
    validate_nuisance_plan(plan)
    return plan


def build_bootstrap_nuisance_plan(
    request: FormalRequest,
    baseline: np.ndarray,
    sample_indices: np.ndarray,
    provider: BootstrapNuisanceProvider | None,
    *,
    original_delta_full: np.ndarray | None = None,
    original_delta_folds: np.ndarray | None = None,
) -> tuple[NuisancePlan, BootstrapNuisanceEvidence | None]:
    """Build one sample-specific plan without resampling fixed adjusted scores."""

    sample = np.asarray(sample_indices, dtype=np.int64)
    if sample.shape != (request.subject_axis.count,) or np.any(
        (sample < 0) | (sample >= request.subject_axis.count)
    ):
        raise FormalBackendInputError("bootstrap sample indices are outside the subject axis")
    sampled_baseline = baseline[sample]
    branch = request.final_model.final_key.final_branch
    if branch != ADJUSTED_BRANCH:
        try:
            if request.final_model.endpoint.model_family.startswith("reference_"):
                plan = _reference_nuisance_plan(sampled_baseline)
            else:
                plan = build_addon_nuisance_plan(sampled_baseline, branch)
                validate_nuisance_plan(plan)
        except (FormalBackendInputError, NuisancePlanError) as error:
            detail = error.detail if isinstance(error, NuisancePlanError) else str(error)
            raise BootstrapReplicateNotEstimableError(detail) from error
        return plan, None

    if provider is None:
        raise FormalBackendInputError(
            "adjusted bootstrap requires an injected BootstrapNuisanceProvider"
        )
    if original_delta_full is None or original_delta_folds is None:
        raise FormalBackendInputError(
            "adjusted bootstrap requires materialized original DeltaReferenceScore inputs"
        )
    original_full = np.asarray(original_delta_full, dtype=np.float64)
    original_folds = np.asarray(original_delta_folds, dtype=np.float64)
    expected_count = request.subject_axis.count
    if original_full.shape != (expected_count,) or not np.all(np.isfinite(original_full)):
        raise FormalBackendInputError(
            "original full DeltaReferenceScore must be a finite subject vector"
        )
    if original_folds.shape != (expected_count, expected_count) or not np.all(
        np.isfinite(original_folds)
    ):
        raise FormalBackendInputError(
            "original fold DeltaReferenceScore must be a finite fold-by-subject matrix"
        )
    try:
        rebuilt = provider.build_bootstrap_nuisance(request, sample.copy())
    except BootstrapNuisanceSampleNotEstimableError as error:
        raise BootstrapReplicateNotEstimableError(error.detail) from error
    if not isinstance(rebuilt, BootstrapNuisanceEvidence):
        raise FormalBackendInputError(
            "BootstrapNuisanceProvider must return BootstrapNuisanceEvidence"
        )
    if not np.array_equal(rebuilt.sample_indices, sample):
        raise FormalBackendInputError(
            "BootstrapNuisanceProvider returned a different ordered sample-index vector"
        )
    provenance = rebuilt.rebuild_provenance
    if provenance.final_model_id != request.final_model.identifier:
        raise FormalBackendInputError(
            "bootstrap rebuild provenance targets a different final model"
        )
    if provenance.subject_axis != request.subject_axis:
        raise FormalBackendInputError(
            "bootstrap rebuild provenance targets a different subject axis"
        )
    identity_sample = np.arange(request.subject_axis.count, dtype=np.int64)
    if not np.array_equal(sample, identity_sample):
        stale_full_candidates = (original_full, original_full[sample])
        if any(
            np.array_equal(rebuilt.delta_reference_full_scores, candidate)
            for candidate in stale_full_candidates
        ):
            raise FormalBackendInputError(
                "bootstrap provider returned stale full DeltaReferenceScore "
                "without a matched-reference refit"
            )
        stale_fold_candidates = (
            original_folds,
            original_folds[np.ix_(sample, sample)],
            original_folds[sample, :],
            original_folds[:, sample],
        )
        if any(
            np.array_equal(rebuilt.delta_reference_fold_scores, candidate)
            for candidate in stale_fold_candidates
        ):
            raise FormalBackendInputError(
                "bootstrap provider returned stale fold DeltaReferenceScore "
                "without a matched-reference refit"
            )
    try:
        plan = build_addon_nuisance_plan(
            sampled_baseline,
            branch,
            delta_full_scores=rebuilt.delta_reference_full_scores,
            delta_fold_scores=rebuilt.delta_reference_fold_scores,
        )
        validate_nuisance_plan(plan)
    except (FormalBackendInputError, NuisancePlanError) as error:
        detail = error.detail if isinstance(error, NuisancePlanError) else str(error)
        raise BootstrapReplicateNotEstimableError(detail) from error
    return plan, rebuilt


def residual_permutation_schedule(
    subject_count: int,
    count: int,
    seed: int,
) -> np.ndarray:
    """Return the explicit PCG64 residual-permutation schedule contract."""

    return formal_resampling_schedule(
        "permutation",
        subject_count,
        count,
        seed,
    ).indices


def freedman_lane_outcomes(
    outcome: np.ndarray,
    nuisance: np.ndarray,
    count: int,
    seed: int,
    *,
    schedule: np.ndarray | None = None,
) -> np.ndarray:
    """Generate fixed-nuisance Freedman-Lane outcomes in deterministic order."""

    design = np.column_stack([np.ones(outcome.size), nuisance])
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise FormalBackendInputError("Freedman-Lane nuisance design is rank deficient")
    beta, *_ = np.linalg.lstsq(design, outcome, rcond=None)
    fitted = design @ beta
    residual = outcome - fitted
    indices = (
        residual_permutation_schedule(outcome.size, count, seed)
        if schedule is None
        else np.asarray(schedule, dtype=np.int32)
    )
    if indices.shape != (count, outcome.size):
        raise FormalBackendInputError(
            "Freedman-Lane schedule does not match count and subject axis"
        )
    expected = np.arange(outcome.size, dtype=np.int32)
    if np.any(np.sort(indices, axis=1) != expected):
        raise FormalBackendInputError("Freedman-Lane schedule rows are invalid")
    output = np.empty((count, outcome.size), dtype=np.float64)
    for index in range(count):
        output[index] = fitted + residual[indices[index]]
    return output


def plus_one_two_sided(observed: float, null: np.ndarray) -> float | None:
    """Return a p value only when the complete requested null is finite."""

    if not math.isfinite(float(observed)):
        raise FormalBackendError("observed LOOCV Spearman rho is not finite")
    values = np.asarray(null, dtype=np.float64)
    if values.ndim != 1:
        raise FormalBackendError("permutation null statistics must be one-dimensional")
    if not np.all(np.isfinite(values)):
        return None
    extreme = int(np.count_nonzero(np.abs(values) >= abs(float(observed))))
    return float((extreme + 1) / (values.size + 1))


def combine_permutation_blocks(
    observed_metrics: dict[str, float],
    schedule: ResamplingSchedule,
    blocks: tuple[PermutationBlockComputation, ...],
) -> PermutationComputation:
    """Reassemble complete schedule-bound blocks in historical replicate order."""

    if not isinstance(schedule, ResamplingSchedule):
        raise FormalBackendError("permutation aggregation requires a schedule")
    if schedule.descriptor.schedule_kind != "permutation":
        raise FormalBackendError("permutation aggregation received a non-permutation schedule")
    candidates = tuple(blocks)
    if not candidates:
        raise FormalBackendError("permutation aggregation requires at least one block")
    if not all(
        isinstance(result, PermutationBlockComputation) for result in candidates
    ):
        raise FormalBackendError(
            "permutation aggregation received an invalid block"
        )
    ordered = tuple(sorted(candidates, key=lambda item: item.block.start))
    total = schedule.descriptor.replicate_count
    digest = schedule.descriptor.schedule_sha256
    null = np.empty(total, dtype=np.float64)
    expected_start = 0
    seen_indices: set[int] = set()
    for result in ordered:
        block = result.block
        if block.index != len(seen_indices):
            raise FormalBackendError(
                "permutation aggregation received a nonsequential block index"
            )
        if block.index in seen_indices:
            raise FormalBackendError("permutation aggregation received a duplicate block index")
        seen_indices.add(block.index)
        if result.schedule_sha256 != digest or block.total != total:
            raise FormalBackendError(
                "permutation block does not match the parent schedule"
            )
        if block.start != expected_start:
            raise FormalBackendError(
                "permutation blocks are missing, overlapping, or noncontiguous"
            )
        null[block.start : block.stop] = result.null_statistics
        expected_start = block.stop
    if expected_start != total:
        raise FormalBackendError("permutation blocks do not cover the full schedule")
    try:
        observed = float(observed_metrics["loocv_spearman_rho"])
    except (KeyError, TypeError, ValueError) as error:
        raise FormalBackendError(
            "permutation aggregation lacks an observed Spearman statistic"
        ) from error
    return PermutationComputation(
        observed_metrics=dict(observed_metrics),
        null_statistics=null,
        p_plus_one_two_sided=plus_one_two_sided(observed, null),
        permutation_schedule=schedule.indices,
    )


def prediction_metrics(
    outcome: np.ndarray,
    predictions: np.ndarray,
    baseline_predictions: np.ndarray,
) -> dict[str, float]:
    """Return report-only held-out metrics without changing classification."""

    finite_model = np.isfinite(outcome) & np.isfinite(predictions)
    finite_baseline = np.isfinite(outcome) & np.isfinite(baseline_predictions)
    model_error = outcome[finite_model] - predictions[finite_model]
    baseline_error = outcome[finite_baseline] - baseline_predictions[finite_baseline]
    mae_model = float(np.mean(np.abs(model_error))) if model_error.size else math.nan
    rmse_model = (
        float(np.sqrt(np.mean(model_error**2))) if model_error.size else math.nan
    )
    mae_baseline = (
        float(np.mean(np.abs(baseline_error))) if baseline_error.size else math.nan
    )
    rmse_baseline = (
        float(np.sqrt(np.mean(baseline_error**2)))
        if baseline_error.size
        else math.nan
    )
    joint = finite_model & finite_baseline
    q2 = math.nan
    if np.any(joint):
        model_sse = float(np.sum((outcome[joint] - predictions[joint]) ** 2))
        baseline_sse = float(
            np.sum((outcome[joint] - baseline_predictions[joint]) ** 2)
        )
        if baseline_sse > 0.0:
            q2 = 1.0 - model_sse / baseline_sse
    spearman, spearman_p = safe_correlation(outcome, predictions, method="spearman")
    pearson, pearson_p = safe_correlation(outcome, predictions, method="pearson")
    return {
        "loocv_spearman_rho": spearman,
        "loocv_spearman_nominal_p": spearman_p,
        "loocv_pearson_r": pearson,
        "loocv_pearson_nominal_p": pearson_p,
        "mae_model": mae_model,
        "mae_baseline": mae_baseline,
        "rmse_model": rmse_model,
        "rmse_baseline": rmse_baseline,
        "q2": q2,
    }


def bootstrap_sample_indices(count: int, resamples: int, seed: int) -> np.ndarray:
    """Return deterministic ordered subject-index vectors."""

    return formal_resampling_schedule(
        "bootstrap",
        count,
        resamples,
        seed,
    ).indices


class StreamingBootstrapAccumulator:
    """Accumulate B-by-F bootstrap evidence using O(B + F) memory."""

    def __init__(
        self,
        *,
        resamples: int,
        n_features: int,
        track_selection: bool,
        retain_replicate_weights: bool = False,
    ) -> None:
        if type(resamples) is not int or resamples < 1:
            raise FormalBackendInputError("resamples must be a positive integer")
        if type(n_features) is not int or n_features < 1:
            raise FormalBackendInputError("n_features must be a positive integer")
        self.resamples = resamples
        self.n_features = n_features
        self._track_selection = bool(track_selection)
        self._replicate_weights = (
            np.full((resamples, n_features), np.nan, dtype=np.float64)
            if retain_replicate_weights
            else None
        )
        self._seen = np.zeros(resamples, dtype=bool)
        self._weight_sum = np.zeros(n_features, dtype=np.float64)
        self._weight_square_sum = np.zeros(n_features, dtype=np.float64)
        self._finite_count = np.zeros(n_features, dtype=np.int64)
        self._candidate_count = np.zeros(n_features, dtype=np.int64)
        self._positive_count = np.zeros(n_features, dtype=np.int64)
        self._negative_count = np.zeros(n_features, dtype=np.int64)
        self._sweet_count = np.zeros(n_features, dtype=np.int64)
        self._sour_count = np.zeros(n_features, dtype=np.int64)
        self._replicate_candidate_count = np.zeros(resamples, dtype=np.int64)
        self._replicate_valid_count = np.zeros(resamples, dtype=np.int64)
        self._replicate_support_code = np.zeros(resamples, dtype=np.int8)
        self._nuisance_evidence: list[dict[str, Any] | None] = [None] * resamples
        self._nonestimable_evidence: list[dict[str, Any] | None] = [None] * resamples

    def update(
        self,
        replicate: int,
        *,
        weights: np.ndarray,
        candidate_mask: np.ndarray,
        support_code: int,
        nuisance_evidence: BootstrapNuisanceEvidence | None,
        sweet_selected: np.ndarray | None = None,
        sour_selected: np.ndarray | None = None,
        nuisance_nonestimability: str | None = None,
    ) -> None:
        """Consume exactly one feature-aligned replicate."""

        if type(replicate) is not int or not 0 <= replicate < self.resamples:
            raise FormalBackendInputError("bootstrap replicate index is outside B")
        if self._seen[replicate]:
            raise FormalBackendInputError("bootstrap replicate was accumulated twice")
        values = np.asarray(weights)
        candidate = np.asarray(candidate_mask)
        expected = (self.n_features,)
        if (
            values.shape != expected
            or values.dtype == object
            or not np.issubdtype(values.dtype, np.number)
            or np.iscomplexobj(values)
        ):
            raise FormalBackendInputError("bootstrap weights must have exact shape F")
        if candidate.shape != expected or candidate.dtype != np.dtype(bool):
            raise FormalBackendInputError(
                "bootstrap candidate mask must be boolean with exact shape F"
            )
        values = np.asarray(values, dtype=np.float64)
        finite = np.isfinite(values)
        if np.any(finite & ~candidate):
            raise FormalBackendInputError(
                "bootstrap weights cannot be finite outside the candidate mask"
            )
        if type(support_code) is not int or support_code not in {0, 1, 2}:
            raise FormalBackendInputError("bootstrap support_code must be 0, 1, or 2")
        nonestimability = (
            str(nuisance_nonestimability).strip()
            if nuisance_nonestimability is not None
            else ""
        )
        if nonestimability and (np.any(finite) or support_code != 0):
            raise FormalBackendInputError(
                "a non-estimable bootstrap replicate cannot publish weights or support"
            )

        selection_values: list[np.ndarray] = []
        for name, selected in (
            ("sweet_selected", sweet_selected),
            ("sour_selected", sour_selected),
        ):
            if self._track_selection:
                if selected is None:
                    raise FormalBackendInputError(
                        f"{name} is required when selection stability is enabled"
                    )
                array = np.asarray(selected)
                if array.shape != expected or array.dtype != np.dtype(bool):
                    raise FormalBackendInputError(f"{name} must have exact boolean shape F")
                if np.any(array & ~finite):
                    raise FormalBackendInputError(
                        f"{name} cannot select a nonfinite-weight feature"
                    )
                selection_values.append(array)
            elif selected is not None:
                raise FormalBackendInputError(
                    "selection masks are not allowed for this bootstrap accumulator"
                )

        self._seen[replicate] = True
        self._candidate_count += candidate
        self._finite_count += finite
        self._weight_sum[finite] += values[finite]
        self._weight_square_sum[finite] += values[finite] ** 2
        self._positive_count += finite & (values > 0.0)
        self._negative_count += finite & (values < 0.0)
        if self._track_selection:
            self._sweet_count += selection_values[0]
            self._sour_count += selection_values[1]
        self._replicate_candidate_count[replicate] = int(np.count_nonzero(candidate))
        self._replicate_valid_count[replicate] = int(np.count_nonzero(finite))
        self._replicate_support_code[replicate] = support_code
        if self._replicate_weights is not None:
            self._replicate_weights[replicate] = values
        if nuisance_evidence is not None:
            provenance = nuisance_evidence.rebuild_provenance
            self._nuisance_evidence[replicate] = {
                "replicate": replicate,
                "support_status": nuisance_evidence.support_status,
                "support_qc": dict(nuisance_evidence.support_qc),
                "rebuild_provenance": {
                    "provider_id": provenance.provider_id,
                    "provider_version": provenance.provider_version,
                    "rebuild_method": provenance.rebuild_method,
                    "final_model_id": provenance.final_model_id,
                    "subject_axis_id": provenance.subject_axis.axis_id,
                    "subject_axis_sha256": provenance.subject_axis.sha256,
                    "sample_indices_sha256": provenance.sample_indices_sha256,
                    "delta_reference_sha256": provenance.delta_reference_sha256,
                },
            }
        if nonestimability:
            self._nonestimable_evidence[replicate] = {
                "replicate": replicate,
                "reason_code": "nonestimable_nuisance_design",
                "detail": nonestimability,
            }

    def block_result(
        self,
        block: ReplicateBlock,
        schedule_sha256: str,
        *,
        require_complete_nuisance_evidence: bool = False,
    ) -> BootstrapBlockComputation:
        """Freeze partial state after consuming exactly one block interval."""

        if not isinstance(block, ReplicateBlock) or block.total != self.resamples:
            raise FormalBackendInputError(
                "bootstrap block does not match the accumulator"
            )
        expected = np.zeros(self.resamples, dtype=bool)
        expected[block.start : block.stop] = True
        if not np.array_equal(self._seen, expected):
            raise FormalBackendInputError(
                "bootstrap accumulator does not contain exactly one block"
            )
        return BootstrapBlockComputation(
            block=block,
            schedule_sha256=schedule_sha256,
            weight_sum=self._weight_sum,
            weight_square_sum=self._weight_square_sum,
            finite_weight_count=self._finite_count,
            candidate_count=self._candidate_count,
            positive_count=self._positive_count,
            negative_count=self._negative_count,
            sweet_count=(self._sweet_count if self._track_selection else None),
            sour_count=(self._sour_count if self._track_selection else None),
            replicate_candidate_count=self._replicate_candidate_count[
                block.start : block.stop
            ],
            replicate_valid_weight_count=self._replicate_valid_count[
                block.start : block.stop
            ],
            replicate_support_code=self._replicate_support_code[
                block.start : block.stop
            ],
            replicate_weights=(
                None
                if self._replicate_weights is None
                else self._replicate_weights[block.start : block.stop]
            ),
            require_complete_nuisance_evidence=(
                require_complete_nuisance_evidence
            ),
            nuisance_evidence=tuple(
                item
                for item in self._nuisance_evidence[block.start : block.stop]
                if item is not None
            ),
            nonestimable_replicates=tuple(
                item
                for item in self._nonestimable_evidence[block.start : block.stop]
                if item is not None
            ),
        )

    def finalize(self) -> BootstrapComputation:
        """Validate all B replicates and emit exact F/B-shaped summaries."""

        if not np.all(self._seen):
            missing = np.flatnonzero(~self._seen)
            raise FormalBackendInputError(
                f"bootstrap accumulator is missing replicates {missing.tolist()}"
            )
        finite_replicates = int(np.count_nonzero(self._replicate_valid_count > 0))
        if finite_replicates == 0:
            raise FormalBackendError("bootstrap produced no finite replicate")
        weight_mean = np.full(self.n_features, np.nan, dtype=np.float64)
        weight_se = np.full(self.n_features, np.nan, dtype=np.float64)
        nonzero = self._finite_count > 0
        repeated = self._finite_count > 1
        weight_mean[nonzero] = self._weight_sum[nonzero] / self._finite_count[nonzero]
        numerator = self._weight_square_sum[repeated] - (
            self._weight_sum[repeated] ** 2 / self._finite_count[repeated]
        )
        weight_se[repeated] = np.sqrt(
            np.maximum(numerator, 0.0) / (self._finite_count[repeated] - 1)
        )
        positive_frequency = np.zeros(self.n_features, dtype=np.float64)
        negative_frequency = np.zeros(self.n_features, dtype=np.float64)
        positive_frequency[nonzero] = (
            self._positive_count[nonzero] / self._finite_count[nonzero]
        )
        negative_frequency[nonzero] = (
            self._negative_count[nonzero] / self._finite_count[nonzero]
        )
        evidence = tuple(
            item
            for item in self._nuisance_evidence
            if item is not None
        )
        nonestimable = tuple(
            item
            for item in self._nonestimable_evidence
            if item is not None
        )
        return BootstrapComputation(
            weight_mean=weight_mean,
            weight_se=weight_se,
            finite_weight_count=self._finite_count,
            candidate_selection_frequency=self._candidate_count / self.resamples,
            positive_sign_frequency=positive_frequency,
            negative_sign_frequency=negative_frequency,
            replicate_candidate_count=self._replicate_candidate_count,
            replicate_valid_weight_count=self._replicate_valid_count,
            replicate_support_code=self._replicate_support_code,
            finite_replicate_count=finite_replicates,
            replicate_weights=self._replicate_weights,
            nonestimable_replicates=nonestimable,
            nuisance_evidence=evidence,
            sweet_selection_frequency=(
                self._sweet_count / finite_replicates
                if self._track_selection
                else None
            ),
            sour_selection_frequency=(
                self._sour_count / finite_replicates
                if self._track_selection
                else None
            ),
        )


def combine_bootstrap_blocks(
    schedule: ResamplingSchedule,
    blocks: tuple[BootstrapBlockComputation, ...],
) -> BootstrapComputation:
    """Strictly combine complete bootstrap block state in replicate order."""

    validate_resampling_schedule(
        schedule,
        schedule_kind="bootstrap",
        subject_count=schedule.descriptor.subject_count,
        replicate_count=schedule.descriptor.replicate_count,
        seed=schedule.descriptor.seed,
    )
    candidates = tuple(blocks)
    if not candidates or not all(
        isinstance(item, BootstrapBlockComputation) for item in candidates
    ):
        raise FormalBackendInputError(
            "bootstrap aggregation requires valid block state"
        )
    ordered = tuple(sorted(candidates, key=lambda item: item.block.start))
    expected_start = 0
    for block_index, item in enumerate(ordered):
        if (
            item.block.index != block_index
            or item.block.start != expected_start
            or item.block.total != schedule.descriptor.replicate_count
            or item.schedule_sha256 != schedule.descriptor.schedule_sha256
        ):
            raise FormalBackendInputError(
                "bootstrap blocks do not match the complete schedule"
            )
        expected_start = item.block.stop
    if expected_start != schedule.descriptor.replicate_count:
        raise FormalBackendInputError(
            "bootstrap blocks do not cover the complete schedule"
        )
    feature_counts = {item.weight_sum.size for item in ordered}
    selection_modes = {
        item.sweet_count is not None and item.sour_count is not None
        for item in ordered
    }
    nuisance_evidence_modes = {
        item.require_complete_nuisance_evidence for item in ordered
    }
    replicate_weight_modes = {
        item.replicate_weights is not None for item in ordered
    }
    if (
        len(feature_counts) != 1
        or len(selection_modes) != 1
        or len(nuisance_evidence_modes) != 1
        or len(replicate_weight_modes) != 1
    ):
        raise FormalBackendInputError(
            "bootstrap blocks have inconsistent feature or selection state"
        )
    n_features = next(iter(feature_counts))
    track_selection = next(iter(selection_modes))
    retain_replicate_weights = next(iter(replicate_weight_modes))
    merged = StreamingBootstrapAccumulator(
        resamples=schedule.descriptor.replicate_count,
        n_features=n_features,
        track_selection=track_selection,
        retain_replicate_weights=retain_replicate_weights,
    )
    merged._seen[:] = True
    for item in ordered:
        merged._weight_sum += item.weight_sum
        merged._weight_square_sum += item.weight_square_sum
        merged._finite_count += item.finite_weight_count
        merged._candidate_count += item.candidate_count
        merged._positive_count += item.positive_count
        merged._negative_count += item.negative_count
        if track_selection:
            assert item.sweet_count is not None and item.sour_count is not None
            merged._sweet_count += item.sweet_count
            merged._sour_count += item.sour_count
        interval = slice(item.block.start, item.block.stop)
        merged._replicate_candidate_count[interval] = (
            item.replicate_candidate_count
        )
        merged._replicate_valid_count[interval] = (
            item.replicate_valid_weight_count
        )
        merged._replicate_support_code[interval] = item.replicate_support_code
        if retain_replicate_weights:
            assert (
                merged._replicate_weights is not None
                and item.replicate_weights is not None
            )
            merged._replicate_weights[interval] = item.replicate_weights
        for evidence in item.nuisance_evidence:
            merged._nuisance_evidence[int(evidence["replicate"])] = evidence
        for evidence in item.nonestimable_replicates:
            merged._nonestimable_evidence[int(evidence["replicate"])] = evidence
    return merged.finalize()


def resample_axis(request: FormalRequest) -> AxisRef:
    """Build the deterministic generated axis for this exact formal task."""

    payload = {
        "final_model_id": request.final_model.identifier,
        "resampling_kind": request.resampling_kind,
        "resamples": request.resamples,
        "seed": request.seed,
    }
    return AxisRef(
        f"formal_{request.resampling_kind}_replicates",
        request.resamples,
        canonical_hash(payload),
    )


def json_safe(value: Any) -> Any:
    """Convert finite numerical output to strict JSON scalars."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


__all__ = [
    "BootstrapBlockComputation",
    "BootstrapComputation",
    "BootstrapReplicateNotEstimableError",
    "FORMAL_REPLICATE_BLOCK_SIZE",
    "FormalBackendError",
    "FormalBackendInputError",
    "PermutationComputation",
    "PermutationBlockComputation",
    "ReplicateBlock",
    "ResamplingSchedule",
    "RngScheduleDescriptor",
    "StreamingBootstrapAccumulator",
    "bootstrap_sample_indices",
    "build_bootstrap_nuisance_plan",
    "build_fixed_nuisance_plan",
    "combine_bootstrap_blocks",
    "canonical_fiber_ids",
    "combine_permutation_blocks",
    "finite_exposure",
    "finite_vector",
    "fixed_replicate_blocks",
    "formal_resampling_schedule",
    "freedman_lane_outcomes",
    "json_safe",
    "materialize_array",
    "plus_one_two_sided",
    "prediction_metrics",
    "residual_permutation_schedule",
    "resample_axis",
    "validate_resampling_schedule",
    "validate_nuisance_plan",
]
