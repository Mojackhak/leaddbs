"""Cache-first OSS/pPAM row materialization on a locked final fiber axis."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from ...cache import CacheItem, ContentAddressedCache, RunScopedArtifactPublisher
from ...cache.identity import ScientificCacheKey
from ...contracts import ArtifactRef, AxisRef, FinalModelRecord
from ...contracts.identity import canonical_hash
from .canonical_mapping import (
    activation_universe,
    merge_right_canonical_probabilities,
)
from .ppam import (
    binary_activation,
    max_probability_union,
    validate_ten_sample_probabilities,
)


DEFAULT_ROW_WORKERS = 3


class OSSBackendError(RuntimeError):
    """Raised when an OSS row request or cached result is invalid."""


class MissingAcceptanceFixture(OSSBackendError):
    """Raised before production when an exact OSS cache row is unavailable."""


def _token(value: str, field_name: str) -> str:
    token = str(value).strip()
    if not token:
        raise OSSBackendError(f"{field_name} must be nonempty")
    return token


def _sha256(value: str, field_name: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise OSSBackendError(f"{field_name} must be a full SHA-256 digest")
    return digest


@dataclass(frozen=True, slots=True)
class OSSScientificSettings:
    """Fixed v1 OSS/pPAM settings plus the explicit toolchain version."""

    backend_version: str
    model: str = "OSS-DBSv2"
    activation_model: str = "pPAM"
    diameter_min_um: float = 1.0
    diameter_max_um: float = 4.0
    diameter_samples: int = 10
    sampling: str = "equidistant"
    fitting_probability_threshold: float = 0.5
    tissue_space: str = "MNI152NLin2009bAsym"
    conductivity_model: str = "ColeCole4"
    conductivity_mode: str = "isotropic"
    patient_dti_enabled: bool = False
    axon_model: str = "McNeal1976"
    axon_length_mm: float = 10.0
    waveform: str = "rectangular"
    relative_phase: str = "zero"
    producer_contract: str = "dual_frequency_oss_producer_v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_version", _token(self.backend_version, "backend_version"))
        if (
            self.model != "OSS-DBSv2"
            or self.activation_model != "pPAM"
            or float(self.diameter_min_um) != 1.0
            or float(self.diameter_max_um) != 4.0
            or type(self.diameter_samples) is not int
            or self.diameter_samples != 10
            or self.sampling != "equidistant"
            or float(self.fitting_probability_threshold) != 0.5
            or self.tissue_space != "MNI152NLin2009bAsym"
            or self.conductivity_model != "ColeCole4"
            or self.conductivity_mode != "isotropic"
            or type(self.patient_dti_enabled) is not bool
            or self.patient_dti_enabled
            or self.axon_model != "McNeal1976"
            or float(self.axon_length_mm) != 10.0
            or self.waveform != "rectangular"
            or self.relative_phase != "zero"
            or self.producer_contract != "dual_frequency_oss_producer_v1"
        ):
            raise OSSBackendError(
                "v1 OSS settings require OSS-DBSv2 pPAM, 1-4 um, "
                "10 equidistant samples, threshold 0.5, template ColeCole4 "
                "isotropic tissue, disabled patient DTI, McNeal1976 10 mm "
                "axons, and a zero-phase rectangular waveform"
            )

    @property
    def parameter_hash(self) -> str:
        return canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class OSSRowInput:
    """One right-canonical subject/side/source producer request."""

    subject_id: str
    side: str
    source_id: str
    feature_axis: AxisRef
    feature_ids: np.ndarray
    geometry_hash: str
    stimulation_hash: str
    component_frequency_hash: str
    transform_hash: str
    connectome_feature_hash: str
    input_artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _token(self.subject_id, "subject_id"))
        side = str(self.side).strip().upper()
        if side not in {"L", "R"}:
            raise OSSBackendError("side must be L or R")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "source_id", _token(self.source_id, "source_id"))
        if not isinstance(self.feature_axis, AxisRef):
            raise OSSBackendError("feature_axis must be an AxisRef")
        fiber_ids = activation_universe(self.feature_ids)
        if fiber_ids.size != self.feature_axis.count:
            raise OSSBackendError("feature_ids must match feature_axis cardinality")
        object.__setattr__(self, "feature_ids", fiber_ids)
        for field_name in (
            "geometry_hash",
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
            "connectome_feature_hash",
        ):
            object.__setattr__(self, field_name, _sha256(getattr(self, field_name), field_name))
        artifacts = tuple(self.input_artifacts)
        if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
            raise OSSBackendError("input_artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "input_artifacts", artifacts)


def build_oss_row_cache_key(
    row: OSSRowInput,
    settings: OSSScientificSettings,
) -> ScientificCacheKey:
    """Build a scale/final/run-independent exact scientific row identity."""

    if not isinstance(row, OSSRowInput) or not isinstance(settings, OSSScientificSettings):
        raise TypeError("row and settings must be typed OSS values")
    ordered_ids = np.asarray(row.feature_ids, dtype="<i8", order="C")
    ordered_axis_hash = hashlib.sha256(ordered_ids.tobytes(order="C")).hexdigest()
    return ScientificCacheKey(
        geometry_hash=row.geometry_hash,
        stimulation_hash=row.stimulation_hash,
        component_frequency_hash=row.component_frequency_hash,
        transform_hash=row.transform_hash,
        connectome_feature_hash=row.connectome_feature_hash,
        backend_name="OSS-DBSv2-pPAM",
        backend_version=settings.backend_version,
        scientific_parameter_hashes=(
            ("ordered_feature_axis", ordered_axis_hash),
            ("oss_ppam_v1", settings.parameter_hash),
        ),
    )


@dataclass(frozen=True, slots=True)
class OSSRowProduct:
    """One producer result before immutable cache publication."""

    feature_ids: np.ndarray
    probabilities: np.ndarray

    def __post_init__(self) -> None:
        ids = activation_universe(self.feature_ids)
        probabilities = validate_ten_sample_probabilities(self.probabilities)
        if probabilities.ndim != 1 or probabilities.shape != (ids.size,):
            raise OSSBackendError("row probabilities must be one-dimensional on feature_ids")
        object.__setattr__(self, "feature_ids", ids)
        object.__setattr__(self, "probabilities", probabilities)


OSSRowProducer = Callable[[OSSRowInput], OSSRowProduct]


@dataclass(frozen=True, slots=True)
class OSSRowBatchArtifact:
    """Materialized continuous/binary rows before endpoint-model fitting."""

    final_model_id: str
    feature_axis: AxisRef
    feature_ids: ArtifactRef
    activation_probability: ArtifactRef
    binary_exposure: ArtifactRef
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "final_model_id", _token(self.final_model_id, "final_model_id"))
        if not isinstance(self.feature_axis, AxisRef):
            raise OSSBackendError("feature_axis must be an AxisRef")
        if (
            not isinstance(self.feature_ids, ArtifactRef)
            or self.feature_ids.axis_refs != (self.feature_axis,)
            or np.dtype(self.feature_ids.dtype) != np.dtype(np.int64)
            or self.feature_ids.units != "fiber_id"
            or self.feature_ids.space != "right_canonical"
        ):
            raise OSSBackendError(
                "row batch feature_ids must be ordered int64 right-canonical fiber IDs"
            )
        for artifact in (self.activation_probability, self.binary_exposure):
            if not isinstance(artifact, ArtifactRef) or not artifact.axis_refs:
                raise OSSBackendError("row batch outputs require array ArtifactRef values")
            if artifact.axis_refs[-1] != self.feature_axis:
                raise OSSBackendError("row batch outputs must use the final feature axis")
        if self.activation_probability.axis_refs != self.binary_exposure.axis_refs:
            raise OSSBackendError("continuous and binary row-batch axes must match")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
            raise OSSBackendError("row batch artifacts must contain only ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True, slots=True)
class OSSRowBatchRequest:
    """Final-linked row materialization request with cache-miss authorization."""

    final_model: FinalModelRecord
    connectome_role: str
    subject_axis: AxisRef
    subject_ids: tuple[str, ...]
    feature_axis: AxisRef
    feature_ids: np.ndarray
    rows: tuple[OSSRowInput, ...]
    settings: OSSScientificSettings
    allow_expensive_producers: bool
    workers: int = DEFAULT_ROW_WORKERS

    def __post_init__(self) -> None:
        if not isinstance(self.final_model, FinalModelRecord):
            raise OSSBackendError("final_model must be a FinalModelRecord")
        if not self.final_model.endpoint.model_family.endswith("fiber"):
            raise OSSBackendError("OSS is defined only for normative-fiber finals")
        if str(self.connectome_role).strip().lower() != "formal":
            raise OSSBackendError("OSS requires the configured formal connectome role")
        object.__setattr__(self, "connectome_role", "formal")
        if not isinstance(self.subject_axis, AxisRef) or not isinstance(self.feature_axis, AxisRef):
            raise OSSBackendError("subject_axis and feature_axis must be AxisRef values")
        if self.feature_axis != self.final_model.valid_feature_axis.axis:
            raise OSSBackendError("OSS feature axis must equal final.valid_feature_axis")
        subjects = tuple(_token(value, "subject_id") for value in self.subject_ids)
        if len(subjects) != self.subject_axis.count or len(set(subjects)) != len(subjects):
            raise OSSBackendError("subject_ids must be unique and match subject_axis")
        object.__setattr__(self, "subject_ids", subjects)
        ids = activation_universe(self.feature_ids)
        if ids.size != self.feature_axis.count:
            raise OSSBackendError("feature_ids must match feature_axis")
        object.__setattr__(self, "feature_ids", ids)
        rows = tuple(self.rows)
        if not rows or not all(isinstance(row, OSSRowInput) for row in rows):
            raise OSSBackendError("rows must contain typed OSSRowInput values")
        object.__setattr__(self, "rows", rows)
        if not isinstance(self.settings, OSSScientificSettings):
            raise OSSBackendError("settings must be OSSScientificSettings")
        if type(self.allow_expensive_producers) is not bool:
            raise OSSBackendError("allow_expensive_producers must be boolean")
        if type(self.workers) is not int or self.workers < 1:
            raise OSSBackendError("workers must be a positive integer")
        expected_subjects = set(subjects)
        observed_keys: set[tuple[str, str, str]] = set()
        side_coverage: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if row.subject_id not in expected_subjects:
                raise OSSBackendError("row subject is outside the declared subject axis")
            if row.feature_axis != self.feature_axis or not np.array_equal(row.feature_ids, ids):
                raise OSSBackendError("every OSS row must use final.valid_feature_axis exactly")
            identity = (row.subject_id, row.side, row.source_id)
            if identity in observed_keys:
                raise OSSBackendError("duplicate subject/side/source OSS row")
            observed_keys.add(identity)
            side_coverage[row.subject_id].add(row.side)
        if any(side_coverage[subject] != {"L", "R"} for subject in subjects):
            raise OSSBackendError("every subject requires at least one exact L and R OSS row")


class OSSRowMaterializer:
    """Resolve exact row caches, optionally produce misses, and publish a final matrix."""

    def __init__(
        self,
        cache: ContentAddressedCache,
        publisher: RunScopedArtifactPublisher,
        *,
        producer: OSSRowProducer | None,
    ) -> None:
        if not isinstance(cache, ContentAddressedCache):
            raise TypeError("cache must be a ContentAddressedCache")
        if not isinstance(publisher, RunScopedArtifactPublisher):
            raise TypeError("publisher must be a RunScopedArtifactPublisher")
        if producer is not None and not callable(producer):
            raise TypeError("producer must be callable or None")
        self.cache = cache
        self.publisher = publisher
        self.producer = producer

    def materialize(self, request: OSSRowBatchRequest) -> OSSRowBatchArtifact:
        if not isinstance(request, OSSRowBatchRequest):
            raise TypeError("request must be an OSSRowBatchRequest")
        ordered_rows = self._ordered_rows(request)
        keyed_rows = tuple(
            (row, build_oss_row_cache_key(row, request.settings)) for row in ordered_rows
        )
        entries = {key.digest: self.cache.resolve(key) for _row, key in keyed_rows}
        missing_by_digest: dict[str, tuple[OSSRowInput, ScientificCacheKey]] = {}
        for row, key in keyed_rows:
            if entries[key.digest] is None:
                missing_by_digest.setdefault(key.digest, (row, key))
        if missing_by_digest and not request.allow_expensive_producers:
            missing = ",".join(sorted(missing_by_digest))
            raise MissingAcceptanceFixture(
                f"missing_acceptance_fixture:{missing}"
            )
        if missing_by_digest:
            if self.producer is None:
                raise OSSBackendError("authorized cache misses require an OSS row producer")
            self._produce_missing(tuple(missing_by_digest.values()), request.workers)
            for _row, key in missing_by_digest.values():
                entries[key.digest] = self.cache.resolve(key)
        if any(entry is None for entry in entries.values()):
            raise OSSBackendError("an OSS cache entry remained unavailable after production")

        side_values: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
        for row, key in keyed_rows:
            entry = entries[key.digest]
            assert entry is not None
            ids, probabilities = self._load_entry(entry.path)
            if not np.array_equal(ids, request.feature_ids):
                raise OSSBackendError("cached OSS row feature axis differs from final axis")
            side_values[(row.subject_id, row.side)].append(probabilities)
        side_rows: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        for key, values in side_values.items():
            merged = values[0]
            for value in values[1:]:
                merged = max_probability_union(merged, value)
            side_rows[key] = (request.feature_ids, merged)
        probabilities = merge_right_canonical_probabilities(
            subject_order=request.subject_ids,
            valid_fiber_ids=request.feature_ids,
            side_probabilities=side_rows,
        )
        binary = binary_activation(probabilities)
        probability_ref = self.publisher.array(
            "activation_probability.npy",
            probabilities,
            kind="oss_activation_probability",
            axes=(request.subject_axis, request.feature_axis),
            units="probability",
            space="right_canonical",
        )
        binary_ref = self.publisher.array(
            "binary_activation.npy",
            binary,
            kind="oss_binary_activation",
            axes=(request.subject_axis, request.feature_axis),
            units="binary",
            space="right_canonical",
        )
        fiber_ids_ref = self.publisher.array(
            "fiber_ids.npy",
            request.feature_ids,
            kind="oss_fiber_ids",
            axes=(request.feature_axis,),
            units="fiber_id",
            space="right_canonical",
        )
        status_ref = self.publisher.document(
            "activation_materialization.json",
            {
                "schema_version": "dual_frequency_oss_materialization_v1",
                "final_model_id": request.final_model.identifier,
                "connectome_role": request.connectome_role,
                "row_workers": request.workers,
                "requested_rows": len(ordered_rows),
                "unique_row_cache_keys": len(entries),
                "produced_cache_keys": len(missing_by_digest),
                "cache_keys": sorted(entries),
                "merge_rule": "max_probability_union",
                "fitting_probability_threshold": 0.5,
                "status": "completed",
            },
            kind="oss_activation_materialization_status",
        )
        return OSSRowBatchArtifact(
            final_model_id=request.final_model.identifier,
            feature_axis=request.feature_axis,
            feature_ids=fiber_ids_ref,
            activation_probability=probability_ref,
            binary_exposure=binary_ref,
            artifacts=(fiber_ids_ref, status_ref),
        )

    @staticmethod
    def _ordered_rows(request: OSSRowBatchRequest) -> tuple[OSSRowInput, ...]:
        subject_index = {subject: index for index, subject in enumerate(request.subject_ids)}
        side_index = {"L": 0, "R": 1}
        return tuple(
            sorted(
                request.rows,
                key=lambda row: (
                    subject_index[row.subject_id],
                    side_index[row.side],
                    row.source_id,
                    build_oss_row_cache_key(row, request.settings).digest,
                ),
            )
        )

    def _produce_missing(
        self,
        missing: tuple[tuple[OSSRowInput, ScientificCacheKey], ...],
        workers: int,
    ) -> None:
        assert self.producer is not None
        with ThreadPoolExecutor(max_workers=min(workers, len(missing))) as pool:
            futures = {
                pool.submit(self._produce_one, row, key): key.digest
                for row, key in missing
            }
            for future in as_completed(futures):
                future.result()

    def _produce_one(self, row: OSSRowInput, key: ScientificCacheKey) -> None:
        assert self.producer is not None
        product = self.producer(row)
        if not isinstance(product, OSSRowProduct):
            raise OSSBackendError("OSS row producer must return OSSRowProduct")
        if not np.array_equal(product.feature_ids, row.feature_ids):
            raise OSSBackendError("OSS row producer returned a different feature axis")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ids_path = root / "fiber_ids.npy"
            probability_path = root / "probabilities.npy"
            metadata_path = root / "row_metadata.json"
            np.save(ids_path, product.feature_ids, allow_pickle=False)
            np.save(probability_path, product.probabilities, allow_pickle=False)
            metadata_path.write_text(
                json.dumps(
                    {
                        "schema_version": "dual_frequency_oss_row_v1",
                        "scientific_identity": key.digest,
                        "feature_axis_sha256": row.feature_axis.sha256,
                        "n_fibers": row.feature_axis.count,
                        "backend_name": key.backend_name,
                        "backend_version": key.backend_version,
                    },
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            items = tuple(
                CacheItem(str(int(fiber_id)), canonical_hash({"fiber_id": int(fiber_id)}))
                for fiber_id in product.feature_ids
            )
            self.cache.publish(
                key,
                {
                    "fiber_ids.npy": ids_path,
                    "probabilities.npy": probability_path,
                    "row_metadata.json": metadata_path,
                },
                items=items,
            )

    @staticmethod
    def _load_entry(path: Path) -> tuple[np.ndarray, np.ndarray]:
        ids_path = path / "fiber_ids.npy"
        probabilities_path = path / "probabilities.npy"
        if not ids_path.is_file() or not probabilities_path.is_file():
            raise OSSBackendError("validated OSS cache entry lacks required row arrays")
        try:
            ids = activation_universe(np.load(ids_path, allow_pickle=False))
            probabilities = validate_ten_sample_probabilities(
                np.load(probabilities_path, allow_pickle=False)
            )
        except (OSError, ValueError) as exc:
            raise OSSBackendError("OSS cache row arrays cannot be loaded") from exc
        if probabilities.ndim != 1 or probabilities.shape != (ids.size,):
            raise OSSBackendError("OSS cache probability row shape is invalid")
        return ids, probabilities


__all__ = [
    "DEFAULT_ROW_WORKERS",
    "MissingAcceptanceFixture",
    "OSSBackendError",
    "OSSRowBatchRequest",
    "OSSRowBatchArtifact",
    "OSSRowInput",
    "OSSRowMaterializer",
    "OSSRowProduct",
    "OSSScientificSettings",
    "build_oss_row_cache_key",
]
