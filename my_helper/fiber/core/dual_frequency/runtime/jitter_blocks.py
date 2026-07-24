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

from ..backends.delta_reference import (
    build_compact_delta_reference_fiber,
    build_compact_delta_reference_voxel,
)
from ..backends.interaction.reference_overlap import prepare_reference_overlap
from ..backends.normative_fiber.addon import prepare_addon_fiber_exposure
from ..backends.protocols import ArtifactPublisher
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
    DeltaReferenceBundle,
    EndpointInputRecord,
    FinalModelRecord,
    FinalSelectionRecord,
    NormativeFiberScoreSettings,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SensitivityResult,
    SensitiveRecord,
    SourceRecord,
)
from ..contracts.identity import canonical_hash
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from ..instrumentation import increment_performance_event
from ..workflow.executor import ServiceResult, TaskExecutionRequest
from .input_provider import StudyRuntimeInputProvider


BLOCK_SCHEMA = "dual_frequency_jitter_physical_block_v1"
ADJUSTED_BLOCK_SCHEMA = "dual_frequency_jitter_physical_block_v2"
BLOCK_REFERENCE_SCHEMA = "dual_frequency_jitter_block_reference_v1"
BLOCK_REFERENCE_KIND = "jitter_physical_block_reference"
BLOCK_CACHE_KIND = "jitter_exposures"
BLOCK_PRODUCER_VERSION = "1"
ADJUSTED_BLOCK_PRODUCER_VERSION = "2"
ADJUSTED_SUPPORT_COUNT_VERSION = "complete_parent_inclusive_tau_counts_v1"
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


def _reference_feature_keys(
    store: ArtifactStore,
    record: SourceRecord | SensitiveRecord,
) -> np.ndarray:
    kind = (
        "selected_feature_indices"
        if record.endpoint.model_family.endswith("voxel")
        else "normative_fiber_valid_union_ids"
    )
    values = np.asarray(_materialize_array(store, _artifact(record, kind)))
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.integer):
        raise JitterBlockError(
            "adjusted jitter reference feature keys must be an integer vector"
        )
    output = np.asarray(values, dtype=np.int64)
    if output.size < 1 or output[0] < 0 or np.any(np.diff(output) <= 0):
        raise JitterBlockError(
            "adjusted jitter reference feature keys must be ordered and unique"
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


def _reference_dependencies_by_endpoint(
    request: TaskExecutionRequest,
    endpoint_ids: tuple[str, ...],
) -> dict[str, ReferenceDependencyRecord]:
    output: dict[str, ReferenceDependencyRecord] = {}
    for record in _typed_records(request, ReferenceDependencyRecord):
        assert isinstance(record, ReferenceDependencyRecord)
        endpoint_id = record.addon_endpoint.identifier
        if endpoint_id not in endpoint_ids:
            continue
        if endpoint_id in output:
            raise JitterBlockError(
                "adjusted jitter block received duplicate reference dependencies"
            )
        output[endpoint_id] = record
    missing = tuple(endpoint_id for endpoint_id in endpoint_ids if endpoint_id not in output)
    if missing:
        raise JitterBlockError(
            f"adjusted jitter block lacks reference dependencies for {missing!r}"
        )
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
    if descriptor["producer_version"] not in {
        BLOCK_PRODUCER_VERSION,
        ADJUSTED_BLOCK_PRODUCER_VERSION,
    }:
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
    producer_version = str(descriptor["producer_version"])
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
    if (branch == "delta_reference_adjusted") != (
        producer_version == ADJUSTED_BLOCK_PRODUCER_VERSION
    ):
        raise JitterBlockError(
            "jitter block branch and producer version are inconsistent"
        )
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
    reference_taus: np.ndarray | None,
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
    producer_version = str(descriptor["producer_version"])
    support_parameters: tuple[tuple[str, str], ...] = ()
    if producer_version == ADJUSTED_BLOCK_PRODUCER_VERSION:
        if reference_taus is None:
            raise JitterBlockError("adjusted jitter cache identity lacks reference taus")
        support_parameters = (
            (
                "reference_taus",
                canonical_hash(
                    {"ordered_reference_taus": reference_taus.tolist()}
                ),
            ),
            (
                "support_count_algorithm",
                canonical_hash({"version": ADJUSTED_SUPPORT_COUNT_VERSION}),
            ),
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
        backend_name=(
            "support_preserving_physical_jitter_block"
            if producer_version == ADJUSTED_BLOCK_PRODUCER_VERSION
            else "reduced_axis_physical_jitter_block"
        ),
        backend_version=producer_version,
        scientific_parameter_hashes=(
            ("group", canonical_hash({"group_id": group_id})),
            ("subjects", canonical_hash({"subject_ids": subject_ids})),
            ("replicates", replicate_axis.sha256),
            ("physical_rule", canonical_hash({"rule": physical_rule})),
        )
        + support_parameters,
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
    adjusted = str(descriptor["producer_version"]) == ADJUSTED_BLOCK_PRODUCER_VERSION
    reference_dependencies = (
        _reference_dependencies_by_endpoint(request, endpoint_ids)
        if adjusted
        else {}
    )
    reference_records = {
        endpoint_id: dependency.reference_record
        for endpoint_id, dependency in reference_dependencies.items()
    }
    key_rows = tuple(
        _feature_keys(store, finals[endpoint_id]) for endpoint_id in endpoint_ids
    )
    if adjusted:
        key_rows = (
            *key_rows,
            *(
                _reference_feature_keys(store, reference_records[endpoint_id])
                for endpoint_id in endpoint_ids
            ),
        )
    feature_keys = np.unique(np.concatenate(key_rows)).astype(np.int64, copy=False)
    feature_keys.flags.writeable = False
    reference_taus = None
    support_parent_feature_keys = None
    if adjusted:
        try:
            reference_taus = np.unique(
                np.asarray(
                    [
                        float(reference_records[endpoint_id].selected_tau)
                        for endpoint_id in endpoint_ids
                    ],
                    dtype=np.float64,
                )
            )
        except (TypeError, ValueError) as exc:
            raise JitterBlockError(
                "adjusted jitter reference records lack selected tau values"
            ) from exc
        if (
            reference_taus.size < 1
            or not np.all(np.isfinite(reference_taus))
            or np.any(reference_taus <= 0.0)
        ):
            raise JitterBlockError(
                "adjusted jitter reference tau vector is invalid"
            )
        reference_taus.flags.writeable = False
        if str(descriptor["model_family"]).endswith("fiber"):
            parent_key_rows = tuple(
                np.asarray(_materialize_array(store, record.feature_ids), dtype=np.int64)
                for record in prepared.values()
                if isinstance(record, PreparedExposureRecord)
            )
            if not parent_key_rows or any(
                not np.array_equal(parent_key_rows[0], row)
                for row in parent_key_rows[1:]
            ):
                raise JitterBlockError(
                    "adjusted fiber group does not share one support parent axis"
                )
            support_parent_feature_keys = parent_key_rows[0]
            support_parent_feature_keys.flags.writeable = False
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
        reference_taus=reference_taus,
    )
    cache = request.scientific_cache
    entry = cache.resolve(key)
    if entry is None:
        if not request.allow_expensive_producers:
            raise JitterBlockError(
                "jitter block cache misses require expensive producer authorization"
            )
        with cache.producer_lease(key) as producer:
            if producer:
                support_counts = None
                if adjusted:
                    assert reference_taus is not None
                    arrays, seeds, support_counts = (
                        provider.build_adjusted_jitter_physical_block(
                            endpoint_id=endpoint_ids[0],
                            subject_ids=subject_ids,
                            feature_keys=feature_keys,
                            support_parent_axis=parent_axis,
                            support_parent_feature_keys=support_parent_feature_keys,
                            reference_taus=reference_taus,
                            replicate_start=start,
                            replicate_stop=stop,
                            root_seed=root_seed,
                            translation_fwhm_mm=float(
                                descriptor["translation_fwhm_mm"]
                            ),
                        )
                    )
                else:
                    arrays, seeds = provider.build_jitter_physical_block(
                        endpoint_id=endpoint_ids[0],
                        subject_ids=subject_ids,
                        feature_keys=feature_keys,
                        replicate_start=start,
                        replicate_stop=stop,
                        root_seed=root_seed,
                        translation_fwhm_mm=float(
                            descriptor["translation_fwhm_mm"]
                        ),
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
                        "schema_version": (
                            ADJUSTED_BLOCK_SCHEMA if adjusted else BLOCK_SCHEMA
                        ),
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
                    if adjusted:
                        assert reference_taus is not None
                        block_payload.update(
                            {
                                "producer_version": ADJUSTED_BLOCK_PRODUCER_VERSION,
                                "support_parent_axis": _axis_payload(parent_axis),
                                "support_count_algorithm_version": (
                                    ADJUSTED_SUPPORT_COUNT_VERSION
                                ),
                                "reference_taus": reference_taus.tolist(),
                            }
                        )
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
                    if adjusted:
                        assert reference_taus is not None
                        assert support_counts is not None
                        tau_axis = AxisRef(
                            axis_id=f"{group_id}:reference-taus",
                            count=int(reference_taus.size),
                            sha256=canonical_hash(
                                {
                                    "ordered_reference_taus": (
                                        reference_taus.tolist()
                                    )
                                }
                            ),
                        )
                        records.append(
                            _write_npy(
                                staging / "reference_taus.npy",
                                reference_taus,
                                CacheFileMetadata(
                                    dtype="float64",
                                    shape=(tau_axis.count,),
                                    axes=(tau_axis,),
                                    units="V/m",
                                ),
                            )
                        )
                        records.append(
                            _write_npy(
                                staging / "parent_suprathreshold_counts.npy",
                                support_counts,
                                CacheFileMetadata(
                                    dtype="int64",
                                    shape=(
                                        replicate_axis.count,
                                        subject_axis.count,
                                        tau_axis.count,
                                    ),
                                    axes=(replicate_axis, subject_axis, tau_axis),
                                    units="count",
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
                if not entry.reused:
                    increment_performance_event(
                        "physical_producer",
                        key=f"{key.kind}:{key.digest}",
                    )
            else:
                entry = cache.resolve(key)
                if entry is None:
                    raise JitterBlockError(
                        "jitter producer lease ended without a complete cache entry"
                    )
    increment_performance_event(
        "physical_cache_use",
        key=f"{key.kind}:{key.digest}",
    )
    publisher = RunScopedArtifactPublisher(
        request.output_dir,
        request.task.task_id,
        str(descriptor["producer_version"]),
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
    support_parent_axis: AxisRef | None
    reference_taus: np.ndarray | None
    parent_suprathreshold_counts: np.ndarray | None


class _MemoryArena:
    """Task-local ephemeral artifact authority for one evaluated replicate."""

    def __init__(self) -> None:
        self._arrays: dict[str, tuple[ArtifactRef, np.ndarray]] = {}
        self._documents: dict[str, tuple[ArtifactRef, dict[str, Any]]] = {}

    def clear(self) -> None:
        self._arrays.clear()
        self._documents.clear()

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

    def document(
        self,
        filename: str,
        payload: Mapping[str, Any],
        *,
        kind: str,
    ) -> ArtifactRef:
        document = dict(payload)
        encoded = (
            json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        uri = f"memory://jitter/{digest}/{str(filename).strip()}"
        artifact = ArtifactRef(
            kind=kind,
            schema_version="dual_frequency_document_v1",
            uri=uri,
            sha256=digest,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id="jitter_block_memory_view",
            producer_version=ADJUSTED_BLOCK_PRODUCER_VERSION,
        )
        self._documents[uri] = (artifact, document)
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

    def materialize_document(
        self,
        artifact: ArtifactRef,
        *,
        expected_kind: str | None = None,
    ) -> dict[str, Any]:
        try:
            registered, payload = self._documents[artifact.uri]
        except KeyError as exc:
            raise JitterBlockError(
                "ephemeral jitter document is unavailable"
            ) from exc
        if registered != artifact or (
            expected_kind is not None and artifact.kind != expected_kind
        ):
            raise JitterBlockError("ephemeral jitter document identity changed")
        return dict(payload)


class _ArenaPublisher:
    """ArtifactPublisher adapter over one task-local replicate arena."""

    def __init__(self, arena: _MemoryArena, prefix: str) -> None:
        self._arena = arena
        self._prefix = str(prefix).strip()
        if not self._prefix:
            raise JitterBlockError("ephemeral jitter publisher prefix is empty")

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
        return self._arena.array(
            f"{self._prefix}_{filename}",
            value,
            kind=kind,
            axes=axes,
            units=units,
            space=space,
        )

    def document(
        self,
        filename: str,
        payload: Mapping[str, Any],
        *,
        kind: str,
    ) -> ArtifactRef:
        return self._arena.document(
            f"{self._prefix}_{filename}",
            payload,
            kind=kind,
        )


class JitterBlockArrayProvider:
    """Resolve ephemeral replicate views and durable checkpoint artifacts."""

    def __init__(self, arena: _MemoryArena, durable: ArtifactStore) -> None:
        self._arena = arena
        self._durable = durable

    def materialize(self, artifact: ArtifactRef, **requirements: object) -> np.ndarray:
        if artifact.uri.startswith("memory://jitter/"):
            return self._arena.materialize(artifact, **requirements)
        return self._durable.materialize(artifact, **requirements)

    def materialize_document(
        self,
        artifact: ArtifactRef,
        *,
        expected_kind: str | None = None,
    ) -> dict[str, Any]:
        if artifact.uri.startswith("memory://jitter/"):
            return self._arena.materialize_document(
                artifact,
                expected_kind=expected_kind,
            )
        return self._durable.materialize_document(
            artifact,
            expected_kind=expected_kind,
        )


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


def _axis_from_payload(value: object, field: str) -> AxisRef:
    if not isinstance(value, Mapping) or set(value) != {"axis_id", "count", "sha256"}:
        raise JitterBlockError(f"{field} axis descriptor is invalid")
    try:
        return AxisRef(
            axis_id=str(value["axis_id"]),
            count=int(value["count"]),
            sha256=str(value["sha256"]),
        )
    except (TypeError, ValueError) as exc:
        raise JitterBlockError(f"{field} axis descriptor is invalid") from exc


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
    expected_schema: str | None = None
    expected_support_axis: AxisRef | None = None
    expected_reference_taus: np.ndarray | None = None
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
        schema = str(payload.get("schema_version", ""))
        if (
            schema not in {BLOCK_SCHEMA, ADJUSTED_BLOCK_SCHEMA}
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
        support_axis = None
        reference_taus = None
        support_counts = None
        if schema == ADJUSTED_BLOCK_SCHEMA:
            if (
                payload.get("producer_version") != ADJUSTED_BLOCK_PRODUCER_VERSION
                or payload.get("support_count_algorithm_version")
                != ADJUSTED_SUPPORT_COUNT_VERSION
            ):
                raise JitterBlockError(
                    "adjusted jitter block support contract is invalid"
                )
            support_axis = _axis_from_payload(
                payload.get("support_parent_axis"),
                "support parent",
            )
            reference_taus = np.asarray(
                _load_cache_array(entry, "reference_taus.npy"),
                dtype=np.float64,
            )
            support_counts = np.asarray(
                _load_cache_array(entry, "parent_suprathreshold_counts.npy"),
                dtype=np.int64,
            )
            declared_taus = np.asarray(payload.get("reference_taus"), dtype=np.float64)
            if (
                reference_taus.ndim != 1
                or reference_taus.size < 1
                or not np.array_equal(reference_taus, declared_taus)
                or np.any(np.diff(reference_taus) <= 0.0)
                or support_counts.shape
                != (stop - start, len(subjects), reference_taus.size)
                or np.any(support_counts < 0)
                or np.any(support_counts > support_axis.count)
            ):
                raise JitterBlockError(
                    "adjusted jitter support arrays are inconsistent"
                )
        if expected_schema is None:
            expected_schema = schema
            expected_support_axis = support_axis
            expected_reference_taus = (
                None
                if reference_taus is None
                else np.array(reference_taus, copy=True)
            )
        elif (
            schema != expected_schema
            or support_axis != expected_support_axis
            or (
                reference_taus is None
                and expected_reference_taus is not None
            )
            or (
                reference_taus is not None
                and expected_reference_taus is None
            )
            or (
                reference_taus is not None
                and expected_reference_taus is not None
                and not np.array_equal(reference_taus, expected_reference_taus)
            )
        ):
            raise JitterBlockError(
                "jitter support contract changed across replicate ranges"
            )
        blocks.append(
            _MappedBlock(
                start=start,
                stop=stop,
                subject_ids=subjects,
                feature_keys=features,
                replicate_indices=indices,
                replicate_seeds=seeds,
                components=components,
                support_parent_axis=support_axis,
                reference_taus=reference_taus,
                parent_suprathreshold_counts=support_counts,
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
        if not isinstance(request.provider, StudyRuntimeInputProvider):
            raise JitterBlockError(
                "cached jitter requires StudyRuntimeInputProvider"
            )
        if target.final_model.final_key is None:
            raise JitterBlockError("cached jitter requires a realized final key")
        if target.final_model.endpoint != endpoint_input.endpoint:
            raise JitterBlockError(
                "cached jitter final and endpoint input identify different endpoints"
            )
        self.target = target
        self.endpoint_input = endpoint_input
        self.reference_dependency = reference_dependency
        self.settings = settings
        self._provider = request.provider
        self._store = request.artifact_store
        self._branch = target.final_model.final_key.final_branch
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
        self._feature_positions = self._positions_in_union(
            first.feature_keys,
            self._feature_keys,
            "final features",
        )
        self._reference_record = (
            None if reference_dependency is None else reference_dependency.reference_record
        )
        self._reference_input: EndpointInputRecord | None = None
        self._reference_prepared: PreparedExposureRecord | None = None
        self._reference_positions: np.ndarray | None = None
        self._support_tau_position: int | None = None
        self._fiber_score_settings: NormativeFiberScoreSettings | None = None

        adjusted = self._branch == "delta_reference_adjusted"
        if adjusted:
            if reference_dependency is None or not isinstance(
                self._reference_record,
                (SourceRecord, SensitiveRecord),
            ):
                raise JitterBlockError(
                    "adjusted cached jitter lacks a typed reference dependency"
                )
            reference_endpoint_id = (
                reference_dependency.matched_reference_endpoint_id
            )
            inputs = _records_by_endpoint(
                request,
                EndpointInputRecord,
                (reference_endpoint_id,),
            )
            prepared = _records_by_endpoint(
                request,
                PreparedExposureRecord,
                (
                    target.final_model.endpoint.identifier,
                    reference_endpoint_id,
                ),
            )
            reference_input = inputs[reference_endpoint_id]
            target_prepared = prepared[target.final_model.endpoint.identifier]
            reference_prepared = prepared[reference_endpoint_id]
            if (
                not isinstance(reference_input, EndpointInputRecord)
                or not isinstance(target_prepared, PreparedExposureRecord)
                or not isinstance(reference_prepared, PreparedExposureRecord)
                or reference_input.subject_axis is None
            ):
                raise JitterBlockError(
                    "adjusted cached jitter reference checkpoints are incomplete"
                )
            reference_keys = _reference_feature_keys(
                request.artifact_store,
                self._reference_record,
            )
            self._reference_positions = self._positions_in_union(
                first.feature_keys,
                reference_keys,
                "matched-reference features",
            )
            if (
                first.support_parent_axis is None
                or first.reference_taus is None
                or first.parent_suprathreshold_counts is None
                or first.support_parent_axis != target_prepared.feature_axis
            ):
                raise JitterBlockError(
                    "adjusted cached jitter lacks the complete-parent support contract"
                )
            selected_tau = (
                self._reference_record.selected_tau
                if isinstance(self._reference_record, SourceRecord)
                else self._reference_record.evaluated_tau
            )
            tau_positions = np.flatnonzero(
                first.reference_taus == float(selected_tau)
            )
            if tau_positions.size != 1:
                raise JitterBlockError(
                    "adjusted cached jitter lacks the locked reference tau"
                )
            if target.final_model.endpoint.model_family.endswith("voxel"):
                if (
                    not isinstance(self._reference_record, SourceRecord)
                    or first.support_parent_axis != reference_prepared.feature_axis
                ):
                    raise JitterBlockError(
                        "adjusted voxel jitter parent axes are inconsistent"
                    )
            else:
                score = request.provider.configuration.normative_fiber.score
                self._fiber_score_settings = NormativeFiberScoreSettings(
                    sweet_fraction=score.sweet_fraction,
                    sour_fraction=score.sour_fraction,
                    weighted_peak_fraction=score.weighted_peak_fraction,
                    sweet_selected_min_count=score.sweet_selected_min_count,
                    sour_selected_min_count=score.sour_selected_min_count,
                    weighted_peak_min_count=score.weighted_peak_min_count,
                )
            self._reference_input = reference_input
            self._reference_prepared = reference_prepared
            self._support_tau_position = int(tau_positions[0])
        elif first.support_parent_axis is not None:
            raise JitterBlockError(
                "non-adjusted cached jitter received an adjusted block contract"
            )

    @staticmethod
    def _positions_in_union(
        union: np.ndarray,
        requested: np.ndarray,
        label: str,
    ) -> np.ndarray:
        positions = np.searchsorted(union, requested)
        if np.any(positions >= union.size) or not np.array_equal(
            union[positions],
            requested,
        ):
            raise JitterBlockError(f"{label} are outside the jitter union axis")
        return np.asarray(positions, dtype=np.int64)

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
        *,
        feature_positions: np.ndarray | None = None,
    ) -> np.ndarray:
        try:
            source = block.components[name][replicate_index - block.start]
        except KeyError as exc:
            raise JitterBlockError(f"jitter block lacks component {name!r}") from exc
        positions = (
            self._feature_positions
            if feature_positions is None
            else feature_positions
        )
        return np.asarray(
            source[np.ix_(self._subject_positions, positions)],
            dtype=np.float32,
        )

    def _build_adjusted_delta(
        self,
        *,
        block: _MappedBlock,
        replicate_index: int,
        publisher: ArtifactPublisher,
    ) -> DeltaReferenceBundle:
        dependency = self.reference_dependency
        reference = self._reference_record
        reference_input = self._reference_input
        reference_prepared = self._reference_prepared
        if (
            dependency is None
            or not isinstance(reference, (SourceRecord, SensitiveRecord))
            or reference_input is None
            or reference_input.subject_axis is None
            or reference_prepared is None
            or self._reference_positions is None
            or self._support_tau_position is None
            or block.support_parent_axis is None
            or block.parent_suprathreshold_counts is None
        ):
            raise JitterBlockError(
                "adjusted cached jitter DeltaReference inputs are incomplete"
            )
        reference_exposure = self._component(
            block,
            replicate_index,
            "reference_condition_exposure",
            feature_positions=self._reference_positions,
        )
        addon_reference_exposure = self._component(
            block,
            replicate_index,
            "addon_reference_component_exposure",
            feature_positions=self._reference_positions,
        )
        local = replicate_index - block.start
        totals = np.asarray(
            block.parent_suprathreshold_counts[
                local,
                self._subject_positions,
                self._support_tau_position,
            ],
            dtype=np.int64,
        )
        subject_axis = self.target.observed_request.subject_axis
        if self.target.final_model.endpoint.model_family == "addon_voxel":
            if not isinstance(reference, SourceRecord):
                raise JitterBlockError(
                    "adjusted voxel jitter requires formal reference evidence"
                )
            return build_compact_delta_reference_voxel(
                matched_reference_endpoint_id=(
                    dependency.matched_reference_endpoint_id
                ),
                reference_source=reference,
                selected_feature_indices=_artifact(
                    reference,
                    "selected_feature_indices",
                ),
                full_weights=_artifact(
                    reference,
                    "benefit_oriented_feature_weights",
                ),
                fold_weights=_artifact(
                    reference,
                    "loocv_benefit_oriented_feature_weights",
                ),
                selected_reference_condition_exposure=reference_exposure,
                selected_addon_reference_component_exposure=(
                    addon_reference_exposure
                ),
                total_suprathreshold_count=totals,
                subject_axis=subject_axis,
                reference_subject_axis=reference_input.subject_axis,
                addon_subject_ids=self.endpoint_input.included_subject_ids,
                reference_subject_ids=reference_input.included_subject_ids,
                parent_feature_axis=reference_prepared.feature_axis,
                support_profile=(
                    self._provider.configuration.direct_voxel.delta_reference_support
                ),
                publisher=publisher,
                artifact_store=self._store,
            )
        if self.target.final_model.endpoint.model_family == "addon_fiber":
            if self._fiber_score_settings is None:
                raise JitterBlockError(
                    "adjusted fiber jitter lacks score settings"
                )
            return build_compact_delta_reference_fiber(
                matched_reference_endpoint_id=(
                    dependency.matched_reference_endpoint_id
                ),
                matched_reference_connectome_id=(
                    self.target.final_model.endpoint.connectome_id
                ),
                reference_record=reference,
                valid_fiber_ids=_artifact(
                    reference,
                    "normative_fiber_valid_union_ids",
                ),
                full_weights=_artifact(
                    reference,
                    "benefit_oriented_fiber_weights",
                ),
                fold_weights=_artifact(
                    reference,
                    "loocv_benefit_oriented_fiber_weights",
                ),
                fold_valid_masks=_artifact(
                    reference,
                    "loocv_valid_fiber_masks",
                ),
                selected_reference_condition_exposure=reference_exposure,
                selected_addon_reference_component_exposure=(
                    addon_reference_exposure
                ),
                total_suprathreshold_count=totals,
                subject_axis=subject_axis,
                reference_subject_axis=reference_input.subject_axis,
                addon_subject_ids=self.endpoint_input.included_subject_ids,
                reference_subject_ids=reference_input.included_subject_ids,
                support_parent_fiber_axis=block.support_parent_axis,
                reference_parent_fiber_axis=reference_prepared.feature_axis,
                fiber_score_settings=self._fiber_score_settings,
                support_profile=(
                    self._provider.configuration.normative_fiber.delta_reference_support
                ),
                publisher=publisher,
                artifact_store=self._store,
            )
        raise JitterBlockError("adjusted cached jitter model family is unsupported")

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
        delta: DeltaReferenceBundle | None = None
        if target.final_model.endpoint.model_family.startswith("addon_"):
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
            if self._branch == "delta_reference_adjusted":
                delta = self._build_adjusted_delta(
                    block=block,
                    replicate_index=replicate_index,
                    publisher=_ArenaPublisher(
                        self._arena,
                        f"jitter_{replicate_index:04d}",
                    ),
                )
                support_status = delta.support_status
                support_qc = (
                    ("translation_sigma_mm", self.settings.translation_sigma_mm),
                    ("delta_input_status", delta.input_status),
                    ("delta_bundle_id", delta.identifier),
                )
            else:
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
        parent_observed = target.observed_request
        if (
            self._branch == "delta_reference_adjusted"
            and delta is not None
            and delta.valid
        ):
            assert delta.full_scores is not None and delta.fold_scores is not None
            parent_observed = replace(
                parent_observed,
                nuisance_inputs=(delta.full_scores, delta.fold_scores),
            )
        observed = replace(parent_observed, exposure=exposure)
        rebuild_identity = jitter_rebuild_identity(
            target,
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            reference_overlap_mask=overlap_artifact,
            support_status=support_status,
            support_qc=support_qc,
        )
        delta_identity = None
        if (
            self._branch == "delta_reference_adjusted"
            and delta is not None
            and delta.valid
        ):
            delta_identity = jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap_artifact,
                support_status=support_status,
                support_qc=support_qc,
                component="delta_reference",
            )
        return JitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=rebuild_identity,
            reference_overlap_mask=overlap_artifact,
            support_status=support_status,
            support_qc=support_qc,
            delta_rebuild_identity=delta_identity,
        )


__all__ = [
    "BLOCK_CACHE_KIND",
    "BLOCK_REFERENCE_KIND",
    "CachedJitterReplicateProvider",
    "JitterBlockArrayProvider",
    "JitterBlockError",
    "prepare_jitter_exposure_block",
]
