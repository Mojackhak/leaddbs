"""Immutable scientific records shared by every dual-frequency backend."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from .identity import EndpointKey, FinalModelKey, canonical_hash


ACCEPTED_SOURCE_STATUSES = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
PREDICTION_STATUSES = frozenset({"error_predictive", "error_nonpredictive"})
SOURCE_STATUSES = ACCEPTED_SOURCE_STATUSES | {"absent_no_stable_grid"}


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
        if self.source_status not in SOURCE_STATUSES:
            raise RecordError(f"unsupported source_status {self.source_status!r}")
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
    failure_stage: str = "none"
    failure_detail: str = "none"

    def __post_init__(self) -> None:
        for field in ("input_status", "support_status", "failure_stage", "failure_detail"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
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
        for field in ("full_scores", "fold_scores", "support_rows"):
            value = getattr(self, field)
            if value is not None and not isinstance(value, ArtifactRef):
                raise RecordError(f"{field} must be an ArtifactRef or None")
        if self.input_status == "valid" and self.support_status in {"adequate", "limited"}:
            if not self._valid_payload():
                raise RecordError("valid DeltaReferenceScore input requires aligned full/fold/support artifacts")

    def _valid_payload(self) -> bool:
        if self.selected_reference_tau is None or self.selected_reference_coverage is None:
            return False
        if self.full_scores is None or self.fold_scores is None or self.support_rows is None:
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


@dataclass(frozen=True)
class ReferenceDependencyRecord:
    """Explicit add-on dependency on one matched reference endpoint."""

    addon_endpoint: EndpointKey
    matched_reference_endpoint_id: str
    dependency_status: str
    reference_source: SourceRecord | None
    delta_reference: DeltaReferenceBundle | None

    def __post_init__(self) -> None:
        if not isinstance(self.addon_endpoint, EndpointKey) or not self.addon_endpoint.model_family.startswith(
            "addon_"
        ):
            raise RecordError("addon_endpoint must identify an add-on model")
        object.__setattr__(
            self,
            "matched_reference_endpoint_id",
            _token(self.matched_reference_endpoint_id, "matched_reference_endpoint_id"),
        )
        object.__setattr__(self, "dependency_status", _token(self.dependency_status, "dependency_status"))
        if self.reference_source is not None and not isinstance(self.reference_source, SourceRecord):
            raise RecordError("reference_source must be a SourceRecord or None")
        if self.delta_reference is not None and not isinstance(self.delta_reference, DeltaReferenceBundle):
            raise RecordError("delta_reference must be a DeltaReferenceBundle or None")
        if self.reference_source is not None:
            reference_endpoint = self.reference_source.endpoint
            expected_family = self.addon_endpoint.model_family.replace("addon_", "reference_", 1)
            if reference_endpoint.identifier != self.matched_reference_endpoint_id:
                raise RecordError("reference source does not match the declared endpoint dependency")
            if reference_endpoint.scale_id != self.addon_endpoint.scale_id:
                raise RecordError("reference and add-on dependency scale IDs must match")
            if reference_endpoint.model_family != expected_family:
                raise RecordError("reference and add-on dependency model families must match")
            if reference_endpoint.connectome_id != self.addon_endpoint.connectome_id:
                raise RecordError("reference and add-on dependency connectomes must match")

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

    @property
    def identifier(self) -> str:
        return f"final_record_{canonical_hash(asdict(self), length=20)}"


@dataclass(frozen=True)
class SensitiveRecord:
    """Observed cross-connectome evidence that can never realize a final model."""

    endpoint: EndpointKey
    formal_endpoint_id: str
    evaluated_tau: float
    evaluated_coverage: int
    input_status: str
    source_status: str
    prediction_status: str
    artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey) or not self.endpoint.model_family.endswith("fiber"):
            raise RecordError("sensitivity evidence requires a normative-fiber endpoint")
        object.__setattr__(self, "formal_endpoint_id", _token(self.formal_endpoint_id, "formal_endpoint_id"))
        object.__setattr__(self, "input_status", _token(self.input_status, "input_status"))
        object.__setattr__(self, "source_status", _token(self.source_status, "source_status"))
        object.__setattr__(self, "prediction_status", _token(self.prediction_status, "prediction_status"))
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
