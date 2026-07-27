"""Cache-first Omega-max-only OSS row preparation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..backends.activation.ossdbs import (
    OSS_SCIENTIFIC_BACKEND_VERSION,
    OSSRowMaterializer,
    build_oss_row_cache_key,
)
from ..cache import ContentAddressedCache, RunScopedArtifactPublisher
from ..contracts import (
    AxisRef,
    EndpointInputRecord,
    FinalSelectionRecord,
    OSSSharedOmegaGroupRecord,
    PreparedExposureRecord,
)
from ..contracts.identity import canonical_hash
from .activation_provider import OSSActivationProvider, OSSProducerRequest
from .oss_toolchain import OSSRowExecutionEvidence


OSS_SHARED_OMEGA_VERSION = "1"


class OSSSharedOmegaError(RuntimeError):
    """Raised when shared Omega-max row preparation cannot close exactly."""


def _axis(value: object, field: str) -> AxisRef:
    if not isinstance(value, Mapping) or set(value) != {
        "axis_id",
        "count",
        "sha256",
    }:
        raise OSSSharedOmegaError(
            f"{field} must contain one exact axis identity"
        )
    try:
        return AxisRef(
            axis_id=str(value["axis_id"]),
            count=int(value["count"]),
            sha256=str(value["sha256"]),
        )
    except (TypeError, ValueError) as exc:
        raise OSSSharedOmegaError(f"{field} is invalid") from exc


def _omega_ids(
    descriptor: Mapping[str, Any],
    cache: ContentAddressedCache,
) -> tuple[AxisRef, np.ndarray]:
    expected = {
        "cache_kind",
        "semantic_sha256",
        "feature_axis",
        "payload_relative_path",
        "payload_sha256",
    }
    if set(descriptor) != expected:
        raise OSSSharedOmegaError("Omega_max descriptor fields differ")
    entry = cache.resolve_identity(
        str(descriptor["cache_kind"]),
        str(descriptor["semantic_sha256"]),
    )
    if entry is None:
        raise OSSSharedOmegaError("Omega_max cache entry is missing")
    relative_path = str(descriptor["payload_relative_path"])
    matches = tuple(
        item for item in entry.files if item.relative_path == relative_path
    )
    if len(matches) != 1 or matches[0].sha256 != descriptor["payload_sha256"]:
        raise OSSSharedOmegaError("Omega_max cache payload identity changed")
    axis = _axis(descriptor["feature_axis"], "Omega_max feature axis")
    metadata = matches[0].metadata
    if (
        metadata.dtype != "int64"
        or metadata.shape != (axis.count,)
        or metadata.axes != (axis,)
        or metadata.units != "fiber_id"
    ):
        raise OSSSharedOmegaError(
            "Omega_max cache metadata differs from descriptor"
        )
    try:
        ids = np.asarray(
            np.load(entry.file_path(relative_path), allow_pickle=False)
        )
    except (OSError, ValueError) as exc:
        raise OSSSharedOmegaError("Omega_max fiber IDs are unreadable") from exc
    if (
        ids.dtype != np.dtype(np.int64)
        or ids.shape != (axis.count,)
        or np.any(ids < 1)
        or (ids.size > 1 and np.any(np.diff(ids) <= 0))
    ):
        raise OSSSharedOmegaError(
            "Omega_max fiber IDs are not ordered unique int64"
        )
    ids.flags.writeable = False
    return axis, ids


def _physical_row_key(request: OSSProducerRequest) -> str:
    return canonical_hash(
        {
            "subject_id": request.row.subject_id,
            "side": request.row.side,
            "frequency_group_id": request.frequency_group_id,
            "delivery_mode": request.delivery_mode,
            "source_ids": request.source_ids,
            "geometry_hash": request.row.geometry_hash,
            "stimulation_hash": request.row.stimulation_hash,
            "component_frequency_hash": request.row.component_frequency_hash,
            "transform_hash": request.row.transform_hash,
            "connectome_feature_hash": request.row.connectome_feature_hash,
            "settings": request.settings.parameter_hash,
        }
    )


def omega_ids_for_shared_group(
    record: OSSSharedOmegaGroupRecord,
    cache: ContentAddressedCache,
) -> np.ndarray:
    entry = cache.resolve_identity(
        record.omega_cache_kind,
        record.omega_cache_semantic_sha256,
    )
    if entry is None:
        raise OSSSharedOmegaError("shared Omega-max group lacks its axis cache")
    matches = tuple(
        item for item in entry.files if item.relative_path == "fiber_ids.npy"
    )
    if (
        len(matches) != 1
        or matches[0].metadata.axes != (record.omega_feature_axis,)
        or matches[0].metadata.dtype != "int64"
        or matches[0].metadata.shape != (record.omega_feature_axis.count,)
    ):
        raise OSSSharedOmegaError("shared Omega-max axis cache metadata changed")
    try:
        ids = np.asarray(
            np.load(entry.file_path("fiber_ids.npy"), allow_pickle=False)
        )
    except (OSError, ValueError) as exc:
        raise OSSSharedOmegaError("shared Omega-max fiber IDs are unreadable") from exc
    if (
        ids.dtype != np.dtype(np.int64)
        or ids.shape != (record.omega_feature_axis.count,)
        or np.any(ids < 1)
        or (ids.size > 1 and np.any(np.diff(ids) <= 0))
    ):
        raise OSSSharedOmegaError(
            "shared Omega-max fiber IDs are not ordered unique int64"
        )
    ids.flags.writeable = False
    return ids


def shared_omega_group_uses_stable_scientific_cache(
    record: OSSSharedOmegaGroupRecord,
    cache: ContentAddressedCache,
) -> bool:
    """Validate the exact terminal row closure for one shared Omega-max group."""

    if not isinstance(record, OSSSharedOmegaGroupRecord):
        raise TypeError("record must be an OSSSharedOmegaGroupRecord")
    if not isinstance(cache, ContentAddressedCache):
        raise TypeError("cache must be a ContentAddressedCache")
    if record.preparation_status != "omega_max_ready":
        raise OSSSharedOmegaError(
            "stable cache validation requires a ready shared Omega-max group"
        )
    omega_ids = omega_ids_for_shared_group(record, cache)
    for row_id in record.omega_row_ids:
        entry = cache.resolve_identity("oss_rows", row_id)
        if entry is None:
            raise OSSSharedOmegaError(
                "shared Omega-max group lacks a referenced row cache"
            )
        if entry.key.backend_version != OSS_SCIENTIFIC_BACKEND_VERSION:
            return False
        row_ids, _probabilities = OSSRowMaterializer._load_entry(entry.path)
        if not np.array_equal(row_ids, omega_ids):
            raise OSSSharedOmegaError(
                "shared Omega-max row cache differs from the declared axis"
            )
    return True


def prepare_oss_omega_max_rows(
    *,
    descriptor: Mapping[str, Any],
    endpoint_inputs: Mapping[str, EndpointInputRecord],
    prepared_exposures: Mapping[str, PreparedExposureRecord],
    final_selections: Mapping[str, FinalSelectionRecord],
    provider: object,
    cache: ContentAddressedCache,
    publisher: RunScopedArtifactPublisher,
    toolchain: object,
    workers: int,
    allow_expensive_producers: bool,
) -> OSSSharedOmegaGroupRecord:
    """Restore or produce exactly one Omega-max OSS row per physical condition."""

    expected = {
        "preparation_version",
        "model_family",
        "final_feature_axis",
        "omega_max",
        "group_id",
        "endpoint_ids",
    }
    if not isinstance(descriptor, Mapping) or set(descriptor) != expected:
        raise OSSSharedOmegaError("shared Omega-max group descriptor fields differ")
    if descriptor["preparation_version"] != OSS_SHARED_OMEGA_VERSION:
        raise OSSSharedOmegaError(
            "unsupported shared Omega-max preparation version"
        )
    group_id = str(descriptor["group_id"])
    model_family = str(descriptor["model_family"])
    endpoint_ids = tuple(sorted(str(value) for value in descriptor["endpoint_ids"]))
    if (
        not group_id
        or not model_family.endswith("fiber")
        or not endpoint_ids
        or len(set(endpoint_ids)) != len(endpoint_ids)
    ):
        raise OSSSharedOmegaError(
            "shared Omega-max group descriptor identity is invalid"
        )
    final_axis = _axis(descriptor["final_feature_axis"], "final feature axis")
    omega_descriptor = descriptor["omega_max"]
    if not isinstance(omega_descriptor, Mapping):
        raise OSSSharedOmegaError("Omega_max descriptor must be an object")
    omega_axis, omega_ids = _omega_ids(omega_descriptor, cache)
    if omega_axis.count < final_axis.count:
        raise OSSSharedOmegaError("Omega_max axis is smaller than the final axis")

    runtime_method = getattr(provider, "activation_runtime_request", None)
    if not callable(runtime_method):
        raise OSSSharedOmegaError(
            "shared Omega-max preparation requires runtime request capabilities"
        )
    requests_by_physical: dict[str, OSSProducerRequest] = {}
    activation_provider = OSSActivationProvider(cache, producer_toolchain=None)
    for endpoint_id in endpoint_ids:
        try:
            selection = final_selections[endpoint_id]
            endpoint_input = endpoint_inputs[endpoint_id]
            prepared = prepared_exposures[endpoint_id]
        except KeyError as exc:
            raise OSSSharedOmegaError(
                f"shared Omega-max group lacks checkpoint records for {endpoint_id!r}"
            ) from exc
        if selection.final_model is None:
            raise OSSSharedOmegaError(
                "shared Omega-max group contains an unrealized final"
            )
        if selection.final_model.valid_feature_axis.axis != final_axis:
            raise OSSSharedOmegaError(
                "shared Omega-max final models do not share the declared final axis"
            )
        omega_runtime = runtime_method(
            selection.final_model,
            endpoint_input,
            prepared,
            publisher,
            workers=workers,
            allow_expensive_producers=True,
            simulation_feature_axis=omega_axis,
            simulation_feature_ids=omega_ids,
        )
        for producer_request in activation_provider._producer_requests(omega_runtime):
            physical_key = _physical_row_key(producer_request)
            previous = requests_by_physical.get(physical_key)
            if (
                previous is not None
                and previous.scientific_identity
                != producer_request.scientific_identity
            ):
                raise OSSSharedOmegaError(
                    "shared physical OSS row resolves to different Omega identities"
                )
            requests_by_physical.setdefault(physical_key, producer_request)
    if not requests_by_physical:
        raise OSSSharedOmegaError(
            "shared Omega-max group contains no physical rows"
        )

    materializer = OSSRowMaterializer(cache, publisher, producer=None)
    row_ids: list[str] = []
    for physical_key in sorted(requests_by_physical):
        producer_request = requests_by_physical[physical_key]
        row_key = build_oss_row_cache_key(
            producer_request.row,
            producer_request.settings,
        )
        entry, _compatibility_sources = materializer.resolve_or_promote_historical(
            producer_request.row,
            row_key,
            producer_request.settings,
        )
        if entry is None:
            if not allow_expensive_producers:
                raise OSSSharedOmegaError(
                    "shared Omega-max cache misses require expensive producer "
                    "authorization"
                )
            produce_method = getattr(toolchain, "produce_with_evidence", None)
            if not callable(produce_method):
                raise OSSSharedOmegaError(
                    "shared Omega-max cache misses require exact "
                    "sample-evidence capabilities"
                )
            evidence = produce_method(producer_request)
            if not isinstance(evidence, OSSRowExecutionEvidence):
                raise OSSSharedOmegaError(
                    "OSS toolchain returned invalid sample-state evidence"
                )
            materializer.publish_product(
                producer_request.row,
                row_key,
                producer_request.settings,
                evidence.product,
            )
            entry, _sources = materializer.resolve_or_promote_historical(
                producer_request.row,
                row_key,
                producer_request.settings,
            )
        if entry is None:
            raise OSSSharedOmegaError(
                "shared Omega-max row remained unavailable after preparation"
            )
        row_ids.append(row_key.digest)

    ordered_row_ids = tuple(sorted(row_ids))
    summary = publisher.document(
        "omega_max_rows.json",
        {
            "schema_version": "dual_frequency_oss_shared_omega_group_v1",
            "group_id": group_id,
            "model_family": model_family,
            "preparation_status": "omega_max_ready",
            "endpoint_ids": list(endpoint_ids),
            "final_feature_axis": {
                "axis_id": final_axis.axis_id,
                "count": final_axis.count,
                "sha256": final_axis.sha256,
            },
            "omega_feature_axis": {
                "axis_id": omega_axis.axis_id,
                "count": omega_axis.count,
                "sha256": omega_axis.sha256,
            },
            "omega_row_ids": list(ordered_row_ids),
            "row_count": len(ordered_row_ids),
            "status": "completed",
        },
        kind="oss_shared_omega_group",
    )
    return OSSSharedOmegaGroupRecord(
        group_id=group_id,
        model_family=model_family,
        preparation_status="omega_max_ready",
        final_feature_axis=final_axis,
        omega_feature_axis=omega_axis,
        omega_cache_kind=str(omega_descriptor["cache_kind"]),
        omega_cache_semantic_sha256=str(omega_descriptor["semantic_sha256"]),
        endpoint_ids=endpoint_ids,
        omega_row_ids=ordered_row_ids,
        artifacts=(summary,),
    )


__all__ = [
    "OSS_SHARED_OMEGA_VERSION",
    "OSSSharedOmegaError",
    "omega_ids_for_shared_group",
    "prepare_oss_omega_max_rows",
    "shared_omega_group_uses_stable_scientific_cache",
]
