"""Generic runtime orchestration for cache-first OSS/pPAM activation rows.

The runtime receives stimulation sources with an exact canonicalization recipe.
It can derive a right-canonical scientific identity without executing the
mapping, expands delivery groups into producer rows, and delegates cache lookup,
miss authorization, pPAM validation, bilateral union, and artifact publication
to :class:`OSSRowMaterializer`. An expensive producer must materialize the
declared mapping before it invokes OSS.

Producer implementations are injected behind ``OSSProducerToolchain``. They
are invoked only for an authorized exact cache miss and are responsible for
resolving any private OSS-DBSv2 executable or environment dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from ..backends.activation.canonical_mapping import activation_universe
from ..backends.activation.ossdbs import (
    DEFAULT_ROW_WORKERS,
    OSSRowBatchArtifact,
    OSSRowBatchRequest,
    OSSRowInput,
    OSSRowMaterializer,
    OSSRowProduct,
    OSSScientificSettings,
    build_oss_row_cache_key,
)
from ..cache import ContentAddressedCache, RunScopedArtifactPublisher
from ..contracts import ArtifactRef, AxisRef, FinalModelRecord
from ..contracts.identity import canonical_hash


RIGHT_CANONICAL_SPACE = "right_canonical"


class ActivationProviderError(RuntimeError):
    """Raised when generic activation runtime inputs violate the contract."""


def _token(value: str, field_name: str) -> str:
    token = str(value).strip()
    if not token:
        raise ActivationProviderError(f"{field_name} must be nonempty")
    return token


def _sha256(value: str, field_name: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ActivationProviderError(
            f"{field_name} must be a full SHA-256 digest"
        )
    return digest


@dataclass(frozen=True, slots=True)
class CanonicalStimulationSource:
    """One source with an exact recipe for right-canonical OSS geometry."""

    subject_id: str
    side: str
    frequency_group_id: str
    delivery_mode: str
    source_id: str
    geometry: ArtifactRef
    canonicalization: str
    stimulation_hash: str
    component_frequency_hash: str
    transform_hash: str
    input_artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _token(self.subject_id, "subject_id"))
        side = str(self.side).strip().upper()
        if side not in {"L", "R"}:
            raise ActivationProviderError("side must be L or R")
        object.__setattr__(self, "side", side)
        object.__setattr__(
            self,
            "frequency_group_id",
            _token(self.frequency_group_id, "frequency_group_id"),
        )
        delivery_mode = str(self.delivery_mode).strip().lower()
        if delivery_mode not in {"continuous", "alternating"}:
            raise ActivationProviderError(
                "delivery_mode must be continuous or alternating"
            )
        object.__setattr__(self, "delivery_mode", delivery_mode)
        object.__setattr__(self, "source_id", _token(self.source_id, "source_id"))
        if not isinstance(self.geometry, ArtifactRef):
            raise ActivationProviderError("geometry must be an ArtifactRef")
        canonicalization = str(self.canonicalization).strip().lower()
        expected = "left_to_right" if side == "L" else "identity"
        if canonicalization != expected:
            raise ActivationProviderError(
                f"{side} geometry requires canonicalization={expected!r}"
            )
        object.__setattr__(self, "canonicalization", canonicalization)
        for field_name in (
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name),
            )
        artifacts = tuple(self.input_artifacts)
        if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
            raise ActivationProviderError(
                "input_artifacts must contain only ArtifactRef values"
            )
        object.__setattr__(self, "input_artifacts", artifacts)

    @property
    def geometry_hash(self) -> str:
        """Return the exact right-canonical geometry recipe identity."""

        return canonical_hash(
            {
                "contract": "dual_frequency_oss_canonical_geometry_v1",
                "input_geometry_sha256": self.geometry.sha256,
                "canonicalization": self.canonicalization,
                "transform_sha256": self.transform_hash,
            }
        )

    @property
    def artifacts(self) -> tuple[ArtifactRef, ...]:
        """Return all typed inputs needed by an injected producer."""

        return (self.geometry, *self.input_artifacts)


@dataclass(frozen=True, slots=True)
class OSSActivationRuntimeRequest:
    """Final-linked source groups and exact axes for OSS row materialization."""

    final_model: FinalModelRecord
    connectome_role: str
    subject_axis: AxisRef
    subject_ids: tuple[str, ...]
    feature_axis: AxisRef
    feature_ids: np.ndarray
    sources: tuple[CanonicalStimulationSource, ...]
    connectome_feature_hash: str
    settings: OSSScientificSettings
    allow_expensive_producers: bool
    simulation_feature_axis: AxisRef | None = None
    simulation_feature_ids: np.ndarray | None = None
    workers: int = DEFAULT_ROW_WORKERS

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise ActivationProviderError("final_model must be a FinalModelRecord")
        if self.final_model.final_status not in {
            "final_model_realized",
            "fallback_final_realized",
        }:
            raise ActivationProviderError(
                "activation runtime requires a realized final model"
            )
        if not self.final_model.endpoint.model_family.endswith("fiber"):
            raise ActivationProviderError(
                "activation runtime requires a normative-fiber final"
            )
        connectome_role = str(self.connectome_role).strip().lower()
        if connectome_role != "formal":
            raise ActivationProviderError(
                "activation runtime requires the formal connectome role"
            )
        object.__setattr__(self, "connectome_role", connectome_role)
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(
            self.feature_axis, AxisRef
        ):
            raise ActivationProviderError(
                "subject_axis and feature_axis must be AxisRef values"
            )
        if self.feature_axis != self.final_model.valid_feature_axis.axis:
            raise ActivationProviderError(
                "feature_axis must equal final.valid_feature_axis exactly"
            )
        subjects = tuple(_token(subject, "subject_id") for subject in self.subject_ids)
        if (
            not subjects
            or len(subjects) != self.subject_axis.count
            or len(set(subjects)) != len(subjects)
        ):
            raise ActivationProviderError(
                "subject_ids must be unique and match subject_axis"
            )
        object.__setattr__(self, "subject_ids", subjects)
        feature_ids = activation_universe(self.feature_ids)
        if feature_ids.size != self.feature_axis.count:
            raise ActivationProviderError(
                "feature_ids must match the exact final feature axis"
            )
        object.__setattr__(self, "feature_ids", feature_ids)
        simulation_axis = self.simulation_feature_axis or self.feature_axis
        if not isinstance(simulation_axis, AxisRef):
            raise ActivationProviderError(
                "simulation_feature_axis must be an AxisRef"
            )
        simulation_ids = activation_universe(
            feature_ids
            if self.simulation_feature_ids is None
            else self.simulation_feature_ids
        )
        if simulation_ids.size != simulation_axis.count:
            raise ActivationProviderError(
                "simulation_feature_ids must match simulation_feature_axis"
            )
        positions = np.searchsorted(simulation_ids, feature_ids)
        if (
            np.any(positions >= simulation_ids.size)
            or not np.array_equal(simulation_ids[positions], feature_ids)
        ):
            raise ActivationProviderError(
                "the final feature axis must be an exact ordered subset of the simulation axis"
            )
        object.__setattr__(self, "simulation_feature_axis", simulation_axis)
        object.__setattr__(self, "simulation_feature_ids", simulation_ids)
        sources = tuple(self.sources)
        if not sources or not all(
            isinstance(source, CanonicalStimulationSource) for source in sources
        ):
            raise ActivationProviderError(
                "sources must contain CanonicalStimulationSource values"
            )
        object.__setattr__(self, "sources", sources)
        object.__setattr__(
            self,
            "connectome_feature_hash",
            _sha256(self.connectome_feature_hash, "connectome_feature_hash"),
        )
        if not isinstance(self.settings, OSSScientificSettings):
            raise ActivationProviderError("settings must be OSSScientificSettings")
        if type(self.allow_expensive_producers) is not bool:
            raise ActivationProviderError(
                "allow_expensive_producers must be boolean"
            )
        if type(self.workers) is not int or self.workers < 1:
            raise ActivationProviderError("workers must be a positive integer")
        self._validate_source_groups(subjects, sources)

    @staticmethod
    def _validate_source_groups(
        subject_ids: tuple[str, ...],
        sources: tuple[CanonicalStimulationSource, ...],
    ) -> None:
        expected_subjects = set(subject_ids)
        identities: set[tuple[str, str, str, str]] = set()
        side_coverage: dict[str, set[str]] = defaultdict(set)
        grouped: dict[
            tuple[str, str, str], list[CanonicalStimulationSource]
        ] = defaultdict(list)
        for source in sources:
            if source.subject_id not in expected_subjects:
                raise ActivationProviderError(
                    "activation source subject is outside subject_ids"
                )
            identity = (
                source.subject_id,
                source.side,
                source.frequency_group_id,
                source.source_id,
            )
            if identity in identities:
                raise ActivationProviderError(
                    "duplicate subject/side/group/source activation input"
                )
            identities.add(identity)
            side_coverage[source.subject_id].add(source.side)
            grouped[
                (source.subject_id, source.side, source.frequency_group_id)
            ].append(source)
        if any(side_coverage[subject] != {"L", "R"} for subject in subject_ids):
            raise ActivationProviderError(
                "every subject requires exact left and right activation inputs"
            )
        for group_sources in grouped.values():
            modes = {source.delivery_mode for source in group_sources}
            if len(modes) != 1:
                raise ActivationProviderError(
                    "a frequency group cannot mix delivery modes"
                )


@dataclass(frozen=True, slots=True)
class OSSProducerRequest:
    """One cache-miss producer call on the exact final right-canonical axis."""

    scientific_identity: str
    row: OSSRowInput
    frequency_group_id: str
    delivery_mode: str
    sources: tuple[CanonicalStimulationSource, ...]
    settings: OSSScientificSettings
    canonical_space: str = RIGHT_CANONICAL_SPACE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scientific_identity",
            _sha256(self.scientific_identity, "scientific_identity"),
        )
        if not isinstance(self.row, OSSRowInput):
            raise ActivationProviderError("row must be an OSSRowInput")
        object.__setattr__(
            self,
            "frequency_group_id",
            _token(self.frequency_group_id, "frequency_group_id"),
        )
        delivery_mode = str(self.delivery_mode).strip().lower()
        if delivery_mode not in {"continuous", "alternating"}:
            raise ActivationProviderError(
                "producer delivery_mode must be continuous or alternating"
            )
        object.__setattr__(self, "delivery_mode", delivery_mode)
        sources = tuple(self.sources)
        if not sources or not all(
            isinstance(source, CanonicalStimulationSource) for source in sources
        ):
            raise ActivationProviderError(
                "producer sources must contain canonical stimulation sources"
            )
        if delivery_mode == "alternating" and len(sources) != 1:
            raise ActivationProviderError(
                "each alternating producer row must contain exactly one source"
            )
        if any(
            source.subject_id != self.row.subject_id
            or source.side != self.row.side
            or source.frequency_group_id != self.frequency_group_id
            or source.delivery_mode != delivery_mode
            for source in sources
        ):
            raise ActivationProviderError(
                "producer sources must match the row subject, side, group, and mode"
            )
        object.__setattr__(self, "sources", sources)
        if not isinstance(self.settings, OSSScientificSettings):
            raise ActivationProviderError(
                "producer settings must be OSSScientificSettings"
            )
        expected_hashes = {
            "geometry_hash": _aggregate_hash(
                "geometry",
                delivery_mode,
                sources,
                tuple(source.geometry_hash for source in sources),
            ),
            "stimulation_hash": _aggregate_hash(
                "stimulation",
                delivery_mode,
                sources,
                tuple(source.stimulation_hash for source in sources),
            ),
            "component_frequency_hash": _aggregate_hash(
                "component_frequency",
                delivery_mode,
                sources,
                tuple(source.component_frequency_hash for source in sources),
            ),
            "transform_hash": _aggregate_hash(
                "transform",
                delivery_mode,
                sources,
                tuple(source.transform_hash for source in sources),
            ),
        }
        if any(getattr(self.row, field) != expected for field, expected in expected_hashes.items()):
            raise ActivationProviderError(
                "producer row hashes differ from its exact source artifacts"
            )
        if build_oss_row_cache_key(self.row, self.settings).digest != self.scientific_identity:
            raise ActivationProviderError(
                "producer scientific_identity differs from the complete row cache key"
            )
        if self.canonical_space != RIGHT_CANONICAL_SPACE:
            raise ActivationProviderError(
                "OSS producer requests must use right_canonical space"
            )

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Return deterministic source membership for the producer row."""

        return tuple(source.source_id for source in self.sources)


@runtime_checkable
class OSSProducerToolchain(Protocol):
    """Injected expensive producer with private toolchain resolution."""

    def produce(self, request: OSSProducerRequest) -> OSSRowProduct: ...


def _aggregate_hash(
    label: str,
    delivery_mode: str,
    sources: tuple[CanonicalStimulationSource, ...],
    values: tuple[str, ...],
) -> str:
    if len(sources) != len(values):
        raise ActivationProviderError("aggregate source identities are misaligned")
    if len(values) == 1:
        return values[0]
    return canonical_hash(
        {
            "contract": "dual_frequency_oss_joint_source_v1",
            "field": label,
            "delivery_mode": delivery_mode,
            "ordered_sources": [{"sha256": value} for value in values],
        }
    )


def _logical_row_id(
    sources: tuple[CanonicalStimulationSource, ...],
) -> str:
    first = sources[0]
    return "oss-row-" + canonical_hash(
        {
            "subject_id": first.subject_id,
            "side": first.side,
            "frequency_group_id": first.frequency_group_id,
            "delivery_mode": first.delivery_mode,
            "source_ids": [source.source_id for source in sources],
        },
        length=24,
    )


class OSSActivationProvider:
    """Expand frequency groups and materialize exact cache-backed OSS rows."""

    def __init__(
        self,
        cache: ContentAddressedCache,
        *,
        producer_toolchain: OSSProducerToolchain | None = None,
    ) -> None:
        if not isinstance(cache, ContentAddressedCache):
            raise TypeError("cache must be a ContentAddressedCache")
        if producer_toolchain is not None and not isinstance(
            producer_toolchain, OSSProducerToolchain
        ):
            raise TypeError(
                "producer_toolchain must implement OSSProducerToolchain or be None"
            )
        self.cache = cache
        self.producer_toolchain = producer_toolchain

    def materialize(
        self,
        request: OSSActivationRuntimeRequest,
        publisher: RunScopedArtifactPublisher,
    ) -> OSSRowBatchArtifact:
        """Resolve exact caches and invoke the injected producer only for allowed misses."""

        if not isinstance(request, OSSActivationRuntimeRequest):
            raise TypeError("request must be an OSSActivationRuntimeRequest")
        if not isinstance(publisher, RunScopedArtifactPublisher):
            raise TypeError("publisher must be a RunScopedArtifactPublisher")
        producer_requests = self._producer_requests(request)
        by_identity: dict[str, OSSProducerRequest] = {}
        for producer_request in producer_requests:
            by_identity.setdefault(
                producer_request.scientific_identity,
                producer_request,
            )

        def produce(row: OSSRowInput) -> OSSRowProduct:
            if self.producer_toolchain is None:
                raise ActivationProviderError(
                    "authorized cache misses require an injected OSS producer toolchain"
                )
            identity = build_oss_row_cache_key(row, request.settings).digest
            try:
                producer_request = by_identity[identity]
            except KeyError as exc:
                raise ActivationProviderError(
                    "materializer requested an unplanned OSS producer row"
                ) from exc
            return self.producer_toolchain.produce(producer_request)

        materializer = OSSRowMaterializer(
            self.cache,
            publisher,
            producer=(produce if self.producer_toolchain is not None else None),
        )
        return materializer.materialize(
            OSSRowBatchRequest(
                final_model=request.final_model,
                connectome_role=request.connectome_role,
                subject_axis=request.subject_axis,
                subject_ids=request.subject_ids,
                feature_axis=request.feature_axis,
                feature_ids=request.feature_ids,
                rows=tuple(item.row for item in producer_requests),
                settings=request.settings,
                allow_expensive_producers=request.allow_expensive_producers,
                simulation_feature_axis=request.simulation_feature_axis,
                simulation_feature_ids=request.simulation_feature_ids,
                workers=request.workers,
            )
        )

    @staticmethod
    def _producer_requests(
        request: OSSActivationRuntimeRequest,
    ) -> tuple[OSSProducerRequest, ...]:
        subject_index = {
            subject_id: index for index, subject_id in enumerate(request.subject_ids)
        }
        side_index = {"L": 0, "R": 1}
        grouped: dict[
            tuple[str, str, str], list[CanonicalStimulationSource]
        ] = defaultdict(list)
        for source in request.sources:
            grouped[
                (source.subject_id, source.side, source.frequency_group_id)
            ].append(source)

        output: list[OSSProducerRequest] = []
        for group_key in sorted(
            grouped,
            key=lambda key: (
                subject_index[key[0]],
                side_index[key[1]],
                key[2],
            ),
        ):
            group_sources = tuple(
                sorted(
                    grouped[group_key],
                    key=lambda source: (
                        source.geometry_hash,
                        source.stimulation_hash,
                        source.component_frequency_hash,
                        source.transform_hash,
                        source.source_id,
                    ),
                )
            )
            delivery_mode = group_sources[0].delivery_mode
            batches = (
                (group_sources,)
                if delivery_mode == "continuous"
                else tuple((source,) for source in group_sources)
            )
            for source_batch in batches:
                geometry_hash = _aggregate_hash(
                    "geometry",
                    delivery_mode,
                    source_batch,
                    tuple(source.geometry_hash for source in source_batch),
                )
                stimulation_hash = _aggregate_hash(
                    "stimulation",
                    delivery_mode,
                    source_batch,
                    tuple(source.stimulation_hash for source in source_batch),
                )
                component_frequency_hash = _aggregate_hash(
                    "component_frequency",
                    delivery_mode,
                    source_batch,
                    tuple(source.component_frequency_hash for source in source_batch),
                )
                transform_hash = _aggregate_hash(
                    "transform",
                    delivery_mode,
                    source_batch,
                    tuple(source.transform_hash for source in source_batch),
                )
                row = OSSRowInput(
                    subject_id=source_batch[0].subject_id,
                    side=source_batch[0].side,
                    source_id=_logical_row_id(source_batch),
                    feature_axis=request.simulation_feature_axis,
                    feature_ids=request.simulation_feature_ids,
                    geometry_hash=geometry_hash,
                    stimulation_hash=stimulation_hash,
                    component_frequency_hash=component_frequency_hash,
                    transform_hash=transform_hash,
                    connectome_feature_hash=request.connectome_feature_hash,
                    input_artifacts=tuple(
                        artifact
                        for source in source_batch
                        for artifact in source.artifacts
                    ),
                )
                identity = build_oss_row_cache_key(row, request.settings).digest
                output.append(
                    OSSProducerRequest(
                        scientific_identity=identity,
                        row=row,
                        frequency_group_id=source_batch[0].frequency_group_id,
                        delivery_mode=delivery_mode,
                        sources=source_batch,
                        settings=request.settings,
                    )
                )
        return tuple(output)


__all__ = [
    "ActivationProviderError",
    "CanonicalStimulationSource",
    "OSSActivationProvider",
    "OSSActivationRuntimeRequest",
    "OSSProducerRequest",
    "OSSProducerToolchain",
    "RIGHT_CANONICAL_SPACE",
]
