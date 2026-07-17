"""Fixed physical jitter blocks and endpoint-local read-only views."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..backends.interaction.reference_overlap import prepare_reference_overlap
from ..backends.normative_fiber.addon import prepare_addon_fiber_exposure
from ..backends.sensitivity import (
    FinalSensitivityTarget,
    JitterReplicateEvidence,
    SpatialJitterSettings,
    jitter_rebuild_identity,
)
from ..cache import (
    ArtifactStore,
    CacheEntry,
    CacheFileMetadata,
    CachedFile,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    ScientificCacheKey,
)
from ..contracts import (
    ArtifactRef,
    AxisRef,
    EndpointInputRecord,
    FinalModelRecord,
    FinalSelectionRecord,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SensitivityResult,
    SensitiveRecord,
    SourceRecord,
)
from ..contracts.identity import canonical_hash
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from ..workflow.executor import ServiceResult, TaskExecutionRequest
from .input_provider import StudyRuntimeInputProvider


BLOCK_SCHEMA = "dual_frequency_jitter_physical_block_v1"
BLOCK_REFERENCE_SCHEMA = "dual_frequency_jitter_block_reference_v1"
BLOCK_REFERENCE_KIND = "jitter_physical_block_reference"
BLOCK_CACHE_KIND = "jitter_exposures"
BLOCK_PRODUCER_VERSION = "1"
BLOCK_SIZE = 25


class JitterBlockError(RuntimeError):
    """Raised when a fixed jitter block is incomplete or inconsistent."""


def _axis_payload(axis: AxisRef) -> dict[str, object]:
    return {
        "axis_id": axis.axis_id,
        "count": axis.count,
        "sha256": axis.sha256,
    }


def _artifact(record: SourceRecord | SensitiveRecord, kind: str) -> ArtifactRef:
    matches = tuple(item for item in record.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise JitterBlockError(
            f"jitter source requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _selected_source(final: FinalModelRecord) -> SourceRecord | SensitiveRecord:
    source = final.selected_source
    if source is None and final.selected_branch is not None:
        source = final.selected_branch.source
    if not isinstance(source, (SourceRecord, SensitiveRecord)):
        raise JitterBlockError("jitter final lacks a selected source record")
    return source


def _materialize_array(store: ArtifactStore, artifact: ArtifactRef) -> np.ndarray:
    if artifact.dtype is None or artifact.shape is None:
        raise JitterBlockError("jitter feature-key artifact is not an array")
    return store.materialize(
        artifact,
        expected_dtype=artifact.dtype,
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
        mmap_mode="r",
    )


def _feature_keys(
    store: ArtifactStore,
    final: FinalModelRecord,
) -> np.ndarray:
    source = _selected_source(final)
    kind = (
        "selected_feature_indices"
        if final.endpoint.model_family.endswith("voxel")
        else "normative_fiber_valid_union_ids"
    )
    values = np.asarray(_materialize_array(store, _artifact(source, kind)))
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.integer):
        raise JitterBlockError("jitter final feature keys must be an integer vector")
    output = np.asarray(values, dtype=np.int64)
    if output.size < 1 or output[0] < 0 or np.any(np.diff(output) <= 0):
        raise JitterBlockError(
            "jitter final feature keys must be nonempty, ordered, and unique"
        )
    return output


def _typed_records(
    request: TaskExecutionRequest,
    record_type: type,
) -> tuple[object, ...]:
    return tuple(
        state.record
        for state in request.dependencies.values()
        if isinstance(state.record, record_type)
    )


def _records_by_endpoint(
    request: TaskExecutionRequest,
    record_type: type,
    endpoint_ids: tuple[str, ...],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for record in _typed_records(request, record_type):
        endpoint = getattr(record, "endpoint", None)
        endpoint_id = getattr(endpoint, "identifier", None)
        if endpoint_id not in endpoint_ids:
            continue
        if endpoint_id in output:
            raise JitterBlockError(
                f"jitter block received duplicate {record_type.__name__} records"
            )
        output[str(endpoint_id)] = record
    missing = tuple(endpoint_id for endpoint_id in endpoint_ids if endpoint_id not in output)
    if missing:
        raise JitterBlockError(
            f"jitter block lacks {record_type.__name__} records for {missing!r}"
        )
    return output


def _finals_by_endpoint(
    request: TaskExecutionRequest,
    endpoint_ids: tuple[str, ...],
) -> dict[str, FinalModelRecord]:
    output: dict[str, FinalModelRecord] = {}
    for selection in _typed_records(request, FinalSelectionRecord):
        assert isinstance(selection, FinalSelectionRecord)
        endpoint_id = selection.endpoint.identifier
        if endpoint_id not in endpoint_ids:
            continue
        if selection.final_model is None:
            raise JitterBlockError("jitter block received an unrealized final")
        if endpoint_id in output:
            raise JitterBlockError("jitter block received duplicate final selections")
        output[endpoint_id] = selection.final_model
    missing = tuple(endpoint_id for endpoint_id in endpoint_ids if endpoint_id not in output)
    if missing:
        raise JitterBlockError(f"jitter block lacks realized finals for {missing!r}")
    return output


def _parse_task_parameters(
    request: TaskExecutionRequest,
) -> tuple[dict[str, Any], tuple[str, ...], str, int, int]:
    try:
        descriptor = json.loads(request.task.execution_parameter("group_descriptor"))
        raw_endpoint_ids = json.loads(
            request.task.execution_parameter("group_endpoint_ids")
        )
        group_id = request.task.execution_parameter("group_id")
        start = int(request.task.execution_parameter("replicate_start"))
        stop = int(request.task.execution_parameter("replicate_stop"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise JitterBlockError("jitter block task parameters are invalid") from exc
    if not isinstance(descriptor, dict):
        raise JitterBlockError("jitter block group descriptor must be an object")
    expected_fields = {
        "connectome_role",
        "final_branch_mode",
        "model_family",
        "producer_version",
        "replicates",
        "seed",
        "shared_exposure_entries",
        "translation_fwhm_mm",
    }
    if set(descriptor) != expected_fields:
        raise JitterBlockError("jitter block group descriptor fields are invalid")
    if not isinstance(raw_endpoint_ids, list):
        raise JitterBlockError("jitter block endpoint IDs must be an array")
    endpoint_ids = tuple(raw_endpoint_ids)
    if (
        not endpoint_ids
        or any(not isinstance(value, str) or not value for value in endpoint_ids)
        or len(set(endpoint_ids)) != len(endpoint_ids)
        or endpoint_ids != tuple(sorted(endpoint_ids))
    ):
        raise JitterBlockError("jitter block endpoint IDs are invalid")
    try:
        replicates = int(descriptor["replicates"])
        seed = int(descriptor["seed"])
        fwhm = float(descriptor["translation_fwhm_mm"])
    except (TypeError, ValueError) as exc:
        raise JitterBlockError("jitter block schedule is invalid") from exc
    if (
        replicates < 1
        or seed < 0
        or not math.isfinite(fwhm)
        or not fwhm > 0.0
        or start < 0
        or start >= replicates
        or stop != min(start + BLOCK_SIZE, replicates)
        or start % BLOCK_SIZE != 0
    ):
        raise JitterBlockError("jitter block replicate interval is invalid")
    if descriptor["producer_version"] != BLOCK_PRODUCER_VERSION:
        raise JitterBlockError("jitter block producer version is unsupported")
    expected_group_id = f"jitter_group_{canonical_hash(descriptor, length=20)}"
    if group_id != expected_group_id:
        raise JitterBlockError("jitter block group ID differs from its descriptor")
    return descriptor, endpoint_ids, group_id, start, stop


def _validate_group_records(
    *,
    provider: StudyRuntimeInputProvider,
    descriptor: Mapping[str, Any],
    endpoint_ids: tuple[str, ...],
    finals: Mapping[str, FinalModelRecord],
) -> None:
    family = str(descriptor["model_family"])
    role = str(descriptor["connectome_role"])
    branch = str(descriptor["final_branch_mode"])
    if family not in {
        "reference_voxel",
        "reference_fiber",
        "addon_voxel",
        "addon_fiber",
    }:
        raise JitterBlockError("jitter block model family is unsupported")
    if role not in {"none", "formal", "sensitive"}:
        raise JitterBlockError("jitter block connectome role is unsupported")
    if (family.endswith("voxel") and role != "none") or (
        family.endswith("fiber") and role == "none"
    ):
        raise JitterBlockError("jitter block model family and role are inconsistent")
    for endpoint_id in endpoint_ids:
        endpoint = provider.endpoint(endpoint_id)
        final = finals[endpoint_id]
        if (
            endpoint.key != final.endpoint
            or endpoint.key.model_family != family
            or endpoint.connectome_role != role
            or final.final_key is None
            or final.final_key.final_branch != branch
        ):
            raise JitterBlockError(
                "jitter block endpoint, final, and descriptor are inconsistent"
            )


def _physical_subject_ids(
    provider: StudyRuntimeInputProvider,
    inputs: Mapping[str, EndpointInputRecord],
) -> tuple[str, ...]:
    selected = {
        subject_id
        for record in inputs.values()
        for subject_id in record.included_subject_ids
    }
    subjects = tuple(
        subject.subject_id
        for subject in provider.study.subjects
        if subject.subject_id in selected
    )
    if selected != set(subjects):
        raise JitterBlockError("jitter endpoint subjects are outside the study axis")
    return subjects


def _block_axes(
    *,
    provider: StudyRuntimeInputProvider,
    group_id: str,
    parent_axis: AxisRef,
    subject_ids: tuple[str, ...],
    feature_keys: np.ndarray,
    indices: np.ndarray,
    seeds: np.ndarray,
) -> tuple[AxisRef, AxisRef, AxisRef]:
    replicate_axis = AxisRef(
        axis_id=f"{group_id}:replicates:{int(indices[0])}-{int(indices[-1]) + 1}",
        count=int(indices.size),
        sha256=canonical_hash(
            {
                "ordered_replicate_indices": indices.tolist(),
                "ordered_replicate_seeds": [int(value) for value in seeds],
            }
        ),
    )
    subject_axis = AxisRef(
        axis_id=f"{provider.study.study_id}:jitter-physical-subjects",
        count=len(subject_ids),
        sha256=canonical_hash({"ordered_subject_ids": subject_ids}),
    )
    feature_axis = AxisRef(
        axis_id=f"{parent_axis.axis_id}:jitter-union:{group_id}",
        count=int(feature_keys.size),
        sha256=canonical_hash(
            {
                "parent_axis_sha256": parent_axis.sha256,
                "ordered_feature_keys": feature_keys.tolist(),
            }
        ),
    )
    return replicate_axis, subject_axis, feature_axis


def _block_key(
    *,
    descriptor: Mapping[str, Any],
    group_id: str,
    subject_ids: tuple[str, ...],
    parent_axis: AxisRef,
    feature_axis: AxisRef,
    replicate_axis: AxisRef,
    components: tuple[str, ...],
) -> ScientificCacheKey:
    shared = descriptor.get("shared_exposure_entries")
    if not isinstance(shared, list) or not shared:
        raise JitterBlockError("jitter block lacks parent shared-exposure identities")
    family = str(descriptor.get("model_family", ""))
    physical_rule = (
        "canonical_grid_bilateral_mean_v1"
        if family.endswith("voxel")
        else "side_specific_fiber_peak_then_mean_v1"
    )
    return ScientificCacheKey(
        geometry_hash=canonical_hash(
            {
                "parent_axis_sha256": parent_axis.sha256,
                "feature_axis_sha256": feature_axis.sha256,
            }
        ),
        stimulation_hash=canonical_hash({"parent_shared_entries": shared}),
        component_frequency_hash=canonical_hash(
            {"model_family": family, "components": components}
        ),
        transform_hash=canonical_hash(
            {
                "seed": descriptor.get("seed"),
                "translation_fwhm_mm": descriptor.get("translation_fwhm_mm"),
            }
        ),
        connectome_feature_hash=feature_axis.sha256,
        backend_name="reduced_axis_physical_jitter_block",
        backend_version=BLOCK_PRODUCER_VERSION,
        scientific_parameter_hashes=(
            ("group", canonical_hash({"group_id": group_id})),
            ("subjects", canonical_hash({"subject_ids": subject_ids})),
            ("replicates", replicate_axis.sha256),
            ("physical_rule", canonical_hash({"rule": physical_rule})),
        ),
        kind=BLOCK_CACHE_KIND,
    )


class _HashingStream:
    def __init__(self, stream, digest: Any) -> None:
        self._stream = stream
        self._digest = digest

    def write(self, payload: bytes) -> int:
        self._digest.update(payload)
        return self._stream.write(payload)

    def flush(self) -> None:
        self._stream.flush()


def _write_npy(
    path: Path,
    value: np.ndarray,
    metadata: CacheFileMetadata,
) -> CachedFile:
    digest = hashlib.sha256()
    with path.open("xb") as stream:
        writer = _HashingStream(stream, digest)
        np.lib.format.write_array(
            writer,
            np.ascontiguousarray(value),
            allow_pickle=False,
        )
        writer.flush()
        os.fsync(stream.fileno())
    return CachedFile(
        relative_path=path.name,
        sha256=digest.hexdigest(),
        size_bytes=path.stat().st_size,
        metadata=metadata,
    )


def _write_document(path: Path, payload: Mapping[str, Any]) -> CachedFile:
    encoded = (
        json.dumps(
            dict(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return CachedFile(
        relative_path=path.name,
        sha256=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
    )


def prepare_jitter_exposure_block(request: TaskExecutionRequest) -> ServiceResult:
    """Produce or reuse one fixed physical block before endpoint statistics."""

    if not isinstance(request.provider, StudyRuntimeInputProvider):
        raise JitterBlockError(
            "physical jitter blocks require StudyRuntimeInputProvider"
        )
    if not isinstance(request.artifact_store, ArtifactStore):
        raise JitterBlockError("physical jitter blocks require ArtifactStore")
    if not isinstance(request.scientific_cache, ContentAddressedCache):
        raise JitterBlockError(
            "physical jitter blocks require ContentAddressedCache"
        )
    descriptor, endpoint_ids, group_id, start, stop = _parse_task_parameters(request)
    provider = request.provider
    store = request.artifact_store
    finals = _finals_by_endpoint(request, endpoint_ids)
    _validate_group_records(
        provider=provider,
        descriptor=descriptor,
        endpoint_ids=endpoint_ids,
        finals=finals,
    )
    inputs = _records_by_endpoint(
        request,
        EndpointInputRecord,
        endpoint_ids,
    )
    prepared = _records_by_endpoint(
        request,
        PreparedExposureRecord,
        endpoint_ids,
    )
    parent_axes = {
        record.feature_axis for record in prepared.values() if isinstance(record, PreparedExposureRecord)
    }
    if len(parent_axes) != 1:
        raise JitterBlockError(
            "one physical jitter group must share one parent feature axis"
        )
    parent_axis = next(iter(parent_axes))
    key_rows = tuple(_feature_keys(store, finals[endpoint_id]) for endpoint_id in endpoint_ids)
    feature_keys = np.unique(np.concatenate(key_rows)).astype(np.int64, copy=False)
    feature_keys.flags.writeable = False
    subject_ids = _physical_subject_ids(
        provider,
        {key: value for key, value in inputs.items() if isinstance(value, EndpointInputRecord)},
    )
    indices = np.arange(start, stop, dtype=np.int64)
    root_seed = int(descriptor["seed"])
    expected_seeds = np.asarray(
        [
            np.random.SeedSequence([root_seed, int(index)]).generate_state(
                1,
                dtype=np.uint64,
            )[0]
            for index in indices
        ],
        dtype=np.uint64,
    )
    replicate_axis, subject_axis, feature_axis = _block_axes(
        provider=provider,
        group_id=group_id,
        parent_axis=parent_axis,
        subject_ids=subject_ids,
        feature_keys=feature_keys,
        indices=indices,
        seeds=expected_seeds,
    )
    components = (
        ("primary_exposure",)
        if str(descriptor["model_family"]).startswith("reference_")
        else (
            "addon_reference_component_exposure",
            "primary_exposure",
            "reference_condition_exposure",
        )
    )
    key = _block_key(
        descriptor=descriptor,
        group_id=group_id,
        subject_ids=subject_ids,
        parent_axis=parent_axis,
        feature_axis=feature_axis,
        replicate_axis=replicate_axis,
        components=components,
    )
    cache = request.scientific_cache
    entry = cache.resolve(key)
    if entry is None:
        with cache.producer_lease(key) as producer:
            if producer:
                arrays, seeds = provider.build_jitter_physical_block(
                    endpoint_id=endpoint_ids[0],
                    subject_ids=subject_ids,
                    feature_keys=feature_keys,
                    replicate_start=start,
                    replicate_stop=stop,
                    root_seed=root_seed,
                    translation_fwhm_mm=float(descriptor["translation_fwhm_mm"]),
                )
                if tuple(sorted(arrays)) != components:
                    raise JitterBlockError(
                        "jitter producer returned an unexpected component set"
                    )
                if not np.array_equal(seeds, expected_seeds):
                    raise JitterBlockError("jitter producer changed the seed schedule")

                def generated(staging: Path) -> tuple[CachedFile, ...]:
                    records: list[CachedFile] = []
                    block_payload = {
                        "schema_version": BLOCK_SCHEMA,
                        "cache_kind": key.kind,
                        "semantic_sha256": key.digest,
                        "group_id": group_id,
                        "model_family": descriptor["model_family"],
                        "connectome_role": descriptor["connectome_role"],
                        "replicate_start": start,
                        "replicate_stop": stop,
                        "subject_ids": list(subject_ids),
                        "feature_key_kind": (
                            "parent_voxel_position"
                            if str(descriptor["model_family"]).endswith("voxel")
                            else "canonical_fiber_id"
                        ),
                        "components": list(components),
                        "replicate_axis": _axis_payload(replicate_axis),
                        "subject_axis": _axis_payload(subject_axis),
                        "feature_axis": _axis_payload(feature_axis),
                    }
                    records.append(_write_document(staging / "block.json", block_payload))
                    records.append(
                        _write_npy(
                            staging / "feature_keys.npy",
                            feature_keys,
                            CacheFileMetadata(
                                dtype="int64",
                                shape=(feature_axis.count,),
                                axes=(feature_axis,),
                                units=None,
                                space=provider.study.spatial.canonical_space,
                            ),
                        )
                    )
                    for component in components:
                        records.append(
                            _write_npy(
                                staging / f"{component}.npy",
                                arrays[component],
                                CacheFileMetadata(
                                    dtype="float32",
                                    shape=(
                                        replicate_axis.count,
                                        subject_axis.count,
                                        feature_axis.count,
                                    ),
                                    axes=(replicate_axis, subject_axis, feature_axis),
                                    units="V/m",
                                    space=provider.study.spatial.canonical_space,
                                ),
                            )
                        )
                    records.append(
                        _write_npy(
                            staging / "replicate_indices.npy",
                            indices,
                            CacheFileMetadata(
                                dtype="int64",
                                shape=(replicate_axis.count,),
                                axes=(replicate_axis,),
                            ),
                        )
                    )
                    records.append(
                        _write_npy(
                            staging / "replicate_seeds.npy",
                            expected_seeds,
                            CacheFileMetadata(
                                dtype="uint64",
                                shape=(replicate_axis.count,),
                                axes=(replicate_axis,),
                            ),
                        )
                    )
                    return tuple(sorted(records, key=lambda record: record.relative_path))

                entry = cache.publish_generated(key, generated)
            else:
                entry = cache.resolve(key)
                if entry is None:
                    raise JitterBlockError(
                        "jitter producer lease ended without a complete cache entry"
                    )
    publisher = RunScopedArtifactPublisher(
        request.output_dir,
        request.task.task_id,
        BLOCK_PRODUCER_VERSION,
    )
    reference = publisher.document(
        "jitter_block_reference.json",
        {
            "schema_version": BLOCK_REFERENCE_SCHEMA,
            "cache_kind": entry.key.kind,
            "semantic_sha256": entry.key.digest,
            "group_id": group_id,
            "replicate_start": start,
            "replicate_stop": stop,
            "reused": entry.reused,
        },
        kind=BLOCK_REFERENCE_KIND,
    )
    return ServiceResult.from_record(
        SensitivityResult(
            target_id=request.task.endpoint_id,
            sensitivity_kind="jitter_physical_block",
            artifacts=(reference,),
        )
    )


@dataclass(frozen=True)
class _MappedBlock:
    start: int
    stop: int
    subject_ids: tuple[str, ...]
    feature_keys: np.ndarray
    replicate_indices: np.ndarray
    replicate_seeds: np.ndarray
    components: Mapping[str, np.ndarray]


class _MemoryArena:
    """Task-local ephemeral artifact authority for one evaluated replicate."""

    def __init__(self) -> None:
        self._arrays: dict[str, tuple[ArtifactRef, np.ndarray]] = {}

    def clear(self) -> None:
        self._arrays.clear()

    @staticmethod
    def _digest(value: np.ndarray) -> str:
        digest = hashlib.sha256()

        class Sink:
            def write(self, payload: bytes) -> int:
                digest.update(payload)
                return len(payload)

        np.lib.format.write_array(
            Sink(),
            np.ascontiguousarray(value),
            allow_pickle=False,
        )
        return digest.hexdigest()

    def array(
        self,
        filename: str,
        value: np.ndarray,
        *,
        kind: str,
        axes: tuple[AxisRef, ...],
        units: str | None,
        space: str | None,
    ) -> ArtifactRef:
        array = np.asarray(value)
        if array.dtype == object or tuple(array.shape) != tuple(axis.count for axis in axes):
            raise JitterBlockError("ephemeral jitter array metadata is invalid")
        array = np.ascontiguousarray(array)
        array.flags.writeable = False
        digest = self._digest(array)
        uri = f"memory://jitter/{digest}/{str(filename).strip()}"
        artifact = ArtifactRef(
            kind=kind,
            schema_version="dual_frequency_array_v1",
            uri=uri,
            sha256=digest,
            dtype=array.dtype.name,
            shape=tuple(array.shape),
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space=space,
            producer_id="jitter_block_memory_view",
            producer_version=BLOCK_PRODUCER_VERSION,
        )
        self._arrays[uri] = (artifact, array)
        return artifact

    def materialize(
        self,
        artifact: ArtifactRef,
        *,
        expected_dtype: str | np.dtype,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None = None,
    ) -> np.ndarray:
        del mmap_mode
        try:
            registered, array = self._arrays[artifact.uri]
        except KeyError as exc:
            raise JitterBlockError("ephemeral jitter artifact is unavailable") from exc
        if registered != artifact:
            raise JitterBlockError("ephemeral jitter artifact identity changed")
        if (
            array.dtype != np.dtype(expected_dtype)
            or array.shape != expected_shape
            or artifact.axis_refs != expected_axes
            or artifact.units != expected_units
            or artifact.space != expected_space
        ):
            raise JitterBlockError("ephemeral jitter artifact metadata changed")
        return array


class JitterBlockArrayProvider:
    """Resolve ephemeral replicate views and durable checkpoint artifacts."""

    def __init__(self, arena: _MemoryArena, durable: ArtifactStore) -> None:
        self._arena = arena
        self._durable = durable

    def materialize(self, artifact: ArtifactRef, **requirements: object) -> np.ndarray:
        if artifact.uri.startswith("memory://jitter/"):
            return self._arena.materialize(artifact, **requirements)
        return self._durable.materialize(artifact, **requirements)


def _load_cache_array(entry: CacheEntry, name: str) -> np.ndarray:
    path = entry.file_path(name)
    try:
        array = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise JitterBlockError(f"jitter block array cannot be mapped: {name}") from exc
    if not isinstance(array, np.ndarray):
        raise JitterBlockError(f"jitter block payload is not an array: {name}")
    array.flags.writeable = False
    return array


def _load_blocks(
    *,
    request: TaskExecutionRequest,
    group_id: str,
    settings: SpatialJitterSettings,
) -> tuple[_MappedBlock, ...]:
    if not isinstance(request.artifact_store, ArtifactStore) or not isinstance(
        request.scientific_cache,
        ContentAddressedCache,
    ):
        raise JitterBlockError("jitter block consumer lacks cache or artifact store")
    references: list[dict[str, Any]] = []
    for result in _typed_records(request, SensitivityResult):
        assert isinstance(result, SensitivityResult)
        if result.sensitivity_kind != "jitter_physical_block":
            continue
        if len(result.artifacts) != 1:
            raise JitterBlockError("jitter block result must carry one reference")
        payload = request.artifact_store.materialize_document(
            result.artifacts[0],
            expected_kind=BLOCK_REFERENCE_KIND,
        )
        if payload.get("schema_version") != BLOCK_REFERENCE_SCHEMA:
            raise JitterBlockError("jitter block reference schema is invalid")
        if payload.get("group_id") == group_id:
            references.append(payload)
    references.sort(key=lambda payload: int(payload["replicate_start"]))
    blocks: list[_MappedBlock] = []
    expected_start = 0
    expected_subjects: tuple[str, ...] | None = None
    expected_features: np.ndarray | None = None
    for reference in references:
        start = int(reference["replicate_start"])
        stop = int(reference["replicate_stop"])
        if start != expected_start or stop <= start:
            raise JitterBlockError("jitter block ranges are missing or overlapping")
        entry = request.scientific_cache.resolve_identity(
            str(reference["cache_kind"]),
            str(reference["semantic_sha256"]),
        )
        if entry is None:
            raise JitterBlockError("referenced jitter block cache entry is missing")
        payload = json.loads(entry.file_path("block.json").read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != BLOCK_SCHEMA
            or payload.get("group_id") != group_id
            or int(payload.get("replicate_start", -1)) != start
            or int(payload.get("replicate_stop", -1)) != stop
        ):
            raise JitterBlockError("jitter block manifest differs from its reference")
        subjects = tuple(str(value) for value in payload.get("subject_ids", ()))
        features = np.asarray(_load_cache_array(entry, "feature_keys.npy"), dtype=np.int64)
        indices = np.asarray(_load_cache_array(entry, "replicate_indices.npy"), dtype=np.int64)
        seeds = np.asarray(_load_cache_array(entry, "replicate_seeds.npy"), dtype=np.uint64)
        if not np.array_equal(indices, np.arange(start, stop, dtype=np.int64)):
            raise JitterBlockError("jitter block replicate indices changed")
        expected_seed_values = np.asarray(
            [
                np.random.SeedSequence([settings.seed, int(index)]).generate_state(
                    1,
                    dtype=np.uint64,
                )[0]
                for index in indices
            ],
            dtype=np.uint64,
        )
        if not np.array_equal(seeds, expected_seed_values):
            raise JitterBlockError("jitter block seed schedule changed")
        if expected_subjects is None:
            expected_subjects = subjects
            expected_features = np.array(features, copy=True)
        elif subjects != expected_subjects or not np.array_equal(
            features,
            expected_features,
        ):
            raise JitterBlockError("jitter block physical axes changed across ranges")
        component_names = tuple(str(value) for value in payload.get("components", ()))
        components = {
            name: _load_cache_array(entry, f"{name}.npy") for name in component_names
        }
        blocks.append(
            _MappedBlock(
                start=start,
                stop=stop,
                subject_ids=subjects,
                feature_keys=features,
                replicate_indices=indices,
                replicate_seeds=seeds,
                components=components,
            )
        )
        expected_start = stop
    if expected_start != settings.replicates:
        raise JitterBlockError("jitter block set does not cover the requested schedule")
    return tuple(blocks)


class CachedJitterReplicateProvider:
    """Build endpoint requests as read-only views over verified physical blocks."""

    def __init__(
        self,
        *,
        request: TaskExecutionRequest,
        target: FinalSensitivityTarget,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        settings: SpatialJitterSettings,
        group_id: str,
    ) -> None:
        if not isinstance(request.artifact_store, ArtifactStore):
            raise JitterBlockError("cached jitter requires ArtifactStore")
        self.target = target
        self.endpoint_input = endpoint_input
        self.reference_dependency = reference_dependency
        self.settings = settings
        self.blocks = _load_blocks(request=request, group_id=group_id, settings=settings)
        self._arena = _MemoryArena()
        self.array_provider = JitterBlockArrayProvider(
            self._arena,
            request.artifact_store,
        )
        self._feature_keys = _feature_keys(
            request.artifact_store,
            target.final_model,
        )
        first = self.blocks[0]
        subject_positions = {value: index for index, value in enumerate(first.subject_ids)}
        try:
            self._subject_positions = np.asarray(
                [subject_positions[value] for value in endpoint_input.included_subject_ids],
                dtype=np.int64,
            )
        except KeyError as exc:
            raise JitterBlockError(
                "endpoint subject axis is outside the jitter physical block"
            ) from exc
        positions = np.searchsorted(first.feature_keys, self._feature_keys)
        if np.any(positions >= first.feature_keys.size) or not np.array_equal(
            first.feature_keys[positions],
            self._feature_keys,
        ):
            raise JitterBlockError("final features are outside the jitter union axis")
        self._feature_positions = np.asarray(positions, dtype=np.int64)
        self._reference_record = (
            None if reference_dependency is None else reference_dependency.reference_record
        )

    def _block(self, replicate_index: int) -> _MappedBlock:
        for block in self.blocks:
            if block.start <= replicate_index < block.stop:
                return block
        raise JitterBlockError("requested jitter replicate is outside the block set")

    def _component(
        self,
        block: _MappedBlock,
        replicate_index: int,
        name: str,
    ) -> np.ndarray:
        try:
            source = block.components[name][replicate_index - block.start]
        except KeyError as exc:
            raise JitterBlockError(f"jitter block lacks component {name!r}") from exc
        return np.asarray(
            source[np.ix_(self._subject_positions, self._feature_positions)],
            dtype=np.float32,
        )

    def build_replicate(
        self,
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence:
        if target != self.target:
            raise JitterBlockError("cached jitter target changed")
        block = self._block(replicate_index)
        local = replicate_index - block.start
        if int(block.replicate_seeds[local]) != replicate_seed:
            raise JitterBlockError("cached jitter replicate seed changed")
        self._arena.clear()
        axes = (
            target.observed_request.subject_axis,
            target.observed_request.feature_axis,
        )
        primary = self._component(block, replicate_index, "primary_exposure")
        support_status = "not_applicable"
        support_qc: tuple[tuple[str, float | int | str | bool], ...] = ()
        overlap_artifact: ArtifactRef | None = None
        if target.final_model.endpoint.model_family.startswith("addon_"):
            final_key = target.final_model.final_key
            if final_key is None or final_key.final_branch != "no_delta_reference":
                raise JitterBlockError(
                    "adjusted_jitter_requires_complete_parent_support"
                )
            reference_component = self._component(
                block,
                replicate_index,
                "addon_reference_component_exposure",
            )
            if target.final_model.endpoint.model_family.endswith("voxel"):
                if not isinstance(self._reference_record, SourceRecord) or (
                    self._reference_record.source_status
                    not in ACCEPTED_SOURCE_STATUSES
                    and self._reference_record.source_status
                    != "absent_no_stable_grid"
                ):
                    raise JitterBlockError(
                        "add-on voxel jitter lacks a valid matched reference source"
                    )
                overlap = prepare_reference_overlap(
                    primary,
                    reference_component,
                    self._reference_record,
                )
                exposure_value = np.asarray(
                    overlap.addon_exposure,
                    dtype=np.float32,
                )
                overlap_mask = overlap.overlap_mask
            else:
                if self.reference_dependency is None or not isinstance(
                    self._reference_record,
                    (SourceRecord, SensitiveRecord),
                ):
                    raise JitterBlockError(
                        "add-on fiber jitter lacks a typed matched reference source"
                    )
                overlap = prepare_addon_fiber_exposure(
                    primary,
                    reference_component,
                    self._reference_record,
                    matched_reference_endpoint_id=(
                        self.reference_dependency.matched_reference_endpoint_id
                    ),
                    matched_reference_connectome_id=(
                        target.final_model.endpoint.connectome_id
                    ),
                )
                exposure_value = np.asarray(overlap.exposure, dtype=np.float32)
                overlap_mask = overlap.reference_active
            overlap_artifact = self._arena.array(
                f"jitter_{replicate_index:04d}_selected_reference_overlap_mask.npy",
                overlap_mask,
                kind="jitter_selected_reference_overlap_mask",
                axes=axes,
                units="binary",
                space=target.observed_request.exposure_space,
            )
            support_qc = (
                ("translation_sigma_mm", self.settings.translation_sigma_mm),
                ("delta_input_status", "not_used_by_final_branch"),
            )
        else:
            exposure_value = primary
        exposure = self._arena.array(
            f"jitter_{replicate_index:04d}_selected_exposure.npy",
            exposure_value,
            kind="jitter_selected_exposure",
            axes=axes,
            units=target.observed_request.exposure_units,
            space=target.observed_request.exposure_space,
        )
        observed = replace(target.observed_request, exposure=exposure)
        rebuild_identity = jitter_rebuild_identity(
            target,
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            reference_overlap_mask=overlap_artifact,
            support_status=support_status,
            support_qc=support_qc,
        )
        return JitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=rebuild_identity,
            reference_overlap_mask=overlap_artifact,
            support_status=support_status,
            support_qc=support_qc,
            delta_rebuild_identity=None,
        )


__all__ = [
    "BLOCK_CACHE_KIND",
    "BLOCK_REFERENCE_KIND",
    "CachedJitterReplicateProvider",
    "JitterBlockArrayProvider",
    "JitterBlockError",
    "prepare_jitter_exposure_block",
]
