"""Exact final-versus-Omega_max OSS axis equivalence gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from ..backends.activation.ossdbs import (
    OSSRowMaterializer,
    build_oss_row_cache_key,
)
from ..cache import (
    CacheFileMetadata,
    CachedFile,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
)
from ..cache.identity import ScientificCacheKey
from ..contracts import (
    AxisRef,
    EndpointInputRecord,
    FinalSelectionRecord,
    OSSAxisEquivalenceGroupRecord,
    PreparedExposureRecord,
)
from ..contracts.identity import canonical_hash
from .activation_provider import OSSActivationProvider, OSSProducerRequest
from .oss_toolchain import OSSRowExecutionEvidence


OSS_AXIS_GATE_VERSION = "1"
OSS_AXIS_PROBABILITY_TOLERANCE = 1.0e-7


class OSSAxisEquivalenceError(RuntimeError):
    """Raised when the OSS axis gate cannot establish a closed decision."""


def _axis(value: object, field: str) -> AxisRef:
    if not isinstance(value, Mapping) or set(value) != {"axis_id", "count", "sha256"}:
        raise OSSAxisEquivalenceError(f"{field} must contain one exact axis identity")
    try:
        return AxisRef(
            axis_id=str(value["axis_id"]),
            count=int(value["count"]),
            sha256=str(value["sha256"]),
        )
    except (TypeError, ValueError) as exc:
        raise OSSAxisEquivalenceError(f"{field} is invalid") from exc


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
        raise OSSAxisEquivalenceError("Omega_max descriptor fields differ")
    entry = cache.resolve_identity(
        str(descriptor["cache_kind"]),
        str(descriptor["semantic_sha256"]),
    )
    if entry is None:
        raise OSSAxisEquivalenceError("Omega_max cache entry is missing")
    relative_path = str(descriptor["payload_relative_path"])
    matches = tuple(item for item in entry.files if item.relative_path == relative_path)
    if len(matches) != 1 or matches[0].sha256 != descriptor["payload_sha256"]:
        raise OSSAxisEquivalenceError("Omega_max cache payload identity changed")
    axis = _axis(descriptor["feature_axis"], "Omega_max feature axis")
    metadata = matches[0].metadata
    if (
        metadata.dtype != "int64"
        or metadata.shape != (axis.count,)
        or metadata.axes != (axis,)
        or metadata.units != "fiber_id"
    ):
        raise OSSAxisEquivalenceError("Omega_max cache metadata differs from descriptor")
    try:
        ids = np.asarray(np.load(entry.file_path(relative_path), allow_pickle=False))
    except (OSError, ValueError) as exc:
        raise OSSAxisEquivalenceError("Omega_max fiber IDs are unreadable") from exc
    if (
        ids.dtype != np.dtype(np.int64)
        or ids.shape != (axis.count,)
        or np.any(ids < 1)
        or (ids.size > 1 and np.any(np.diff(ids) <= 0))
    ):
        raise OSSAxisEquivalenceError("Omega_max fiber IDs are not ordered unique int64")
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


def _decision_key(
    group_id: str,
    final_request: OSSProducerRequest,
    omega_request: OSSProducerRequest,
) -> ScientificCacheKey:
    final_key = build_oss_row_cache_key(final_request.row, final_request.settings)
    omega_key = build_oss_row_cache_key(omega_request.row, omega_request.settings)
    return ScientificCacheKey(
        geometry_hash=final_key.digest,
        stimulation_hash=omega_key.digest,
        component_frequency_hash=canonical_hash(
            {"group_id": group_id, "physical_row": _physical_row_key(final_request)}
        ),
        transform_hash=final_request.row.transform_hash,
        connectome_feature_hash=final_request.row.connectome_feature_hash,
        backend_name="oss_axis_equivalence",
        backend_version=OSS_AXIS_GATE_VERSION,
        scientific_parameter_hashes=(
            ("final_row", final_key.digest),
            ("omega_row", omega_key.digest),
            (
                "state_comparison",
                canonical_hash(
                    {
                        "contract": "exact_ten_sample_state_subset_v1",
                        "probability_tolerance": OSS_AXIS_PROBABILITY_TOLERANCE,
                    }
                ),
            ),
        ),
        kind="oss_axis_equivalence",
    )


def _load_decision(
    cache: ContentAddressedCache,
    key: ScientificCacheKey,
    *,
    group_id: str,
    final_request: OSSProducerRequest,
    omega_request: OSSProducerRequest,
) -> dict[str, Any] | None:
    entry = cache.resolve(key)
    if entry is None:
        return None
    path = entry.file_path("decision.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSSAxisEquivalenceError("cached OSS axis decision is unreadable") from exc
    expected = {
        "schema_version",
        "decision_id",
        "group_id",
        "status",
        "final_row_identity",
        "omega_row_identity",
        "state_mismatch_count",
        "activation_count_mismatch_count",
        "max_probability_difference",
        "probability_tolerance",
    }
    final_key = build_oss_row_cache_key(final_request.row, final_request.settings)
    omega_key = build_oss_row_cache_key(omega_request.row, omega_request.settings)
    if (
        not isinstance(payload, dict)
        or set(payload) != expected
        or payload["schema_version"] != "dual_frequency_oss_axis_decision_v1"
        or payload["decision_id"] != key.digest
        or payload["group_id"] != group_id
        or payload["status"] not in {"pass", "fail"}
        or payload["final_row_identity"] != final_key.digest
        or payload["omega_row_identity"] != omega_key.digest
        or payload["probability_tolerance"] != OSS_AXIS_PROBABILITY_TOLERANCE
    ):
        raise OSSAxisEquivalenceError("cached OSS axis decision identity changed")
    for row_key in (final_key, omega_key):
        row_entry = cache.resolve(row_key)
        if row_entry is None:
            raise OSSAxisEquivalenceError(
                "cached OSS axis decision lacks its standard row cache"
            )
        OSSRowMaterializer._load_entry(row_entry.path)
    return payload


def _publish_decision(
    cache: ContentAddressedCache,
    key: ScientificCacheKey,
    payload: Mapping[str, Any],
) -> None:
    data = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    def producer(staging: Path) -> tuple[CachedFile, ...]:
        path = staging / "decision.json"
        path.write_bytes(data)
        return (
            CachedFile(
                relative_path="decision.json",
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                metadata=CacheFileMetadata(),
            ),
        )

    cache.publish_generated(key, producer, items=())


def establish_oss_axis_equivalence(
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
) -> OSSAxisEquivalenceGroupRecord:
    """Establish or restore all immutable row decisions for one fiber group."""

    expected = {
        "gate_version",
        "model_family",
        "final_feature_axis",
        "omega_max",
        "group_id",
        "endpoint_ids",
    }
    if not isinstance(descriptor, Mapping) or set(descriptor) != expected:
        raise OSSAxisEquivalenceError("OSS axis group descriptor fields differ")
    if descriptor["gate_version"] != OSS_AXIS_GATE_VERSION:
        raise OSSAxisEquivalenceError("unsupported OSS axis gate version")
    group_id = str(descriptor["group_id"])
    model_family = str(descriptor["model_family"])
    endpoint_ids = tuple(sorted(str(value) for value in descriptor["endpoint_ids"]))
    if (
        not group_id
        or not model_family.endswith("fiber")
        or not endpoint_ids
        or len(set(endpoint_ids)) != len(endpoint_ids)
    ):
        raise OSSAxisEquivalenceError("OSS axis group descriptor identity is invalid")
    final_axis = _axis(descriptor["final_feature_axis"], "final feature axis")
    omega_descriptor = descriptor["omega_max"]
    if not isinstance(omega_descriptor, Mapping):
        raise OSSAxisEquivalenceError("Omega_max descriptor must be an object")
    omega_axis, omega_ids = _omega_ids(omega_descriptor, cache)
    if omega_axis.count < final_axis.count:
        raise OSSAxisEquivalenceError("Omega_max axis is smaller than the final axis")
    runtime_method = getattr(provider, "activation_runtime_request", None)
    if not callable(runtime_method):
        raise OSSAxisEquivalenceError(
            "OSS axis gate requires runtime request capabilities"
        )
    paired: dict[str, tuple[OSSProducerRequest, OSSProducerRequest]] = {}
    activation_provider = OSSActivationProvider(cache, producer_toolchain=None)
    for endpoint_id in endpoint_ids:
        try:
            selection = final_selections[endpoint_id]
            endpoint_input = endpoint_inputs[endpoint_id]
            prepared = prepared_exposures[endpoint_id]
        except KeyError as exc:
            raise OSSAxisEquivalenceError(
                f"OSS axis group lacks checkpoint records for {endpoint_id!r}"
            ) from exc
        if selection.final_model is None:
            raise OSSAxisEquivalenceError("OSS axis group contains an unrealized final")
        if selection.final_model.valid_feature_axis.axis != final_axis:
            raise OSSAxisEquivalenceError(
                "OSS axis group final models do not share the declared final axis"
            )
        final_runtime = runtime_method(
            selection.final_model,
            endpoint_input,
            prepared,
            publisher,
            workers=workers,
            allow_expensive_producers=True,
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
        final_requests = activation_provider._producer_requests(final_runtime)
        omega_requests = activation_provider._producer_requests(omega_runtime)
        final_by_physical = {_physical_row_key(item): item for item in final_requests}
        omega_by_physical = {_physical_row_key(item): item for item in omega_requests}
        if set(final_by_physical) != set(omega_by_physical):
            raise OSSAxisEquivalenceError(
                "final and Omega_max runtime requests differ outside the feature axis"
            )
        for physical_key in sorted(final_by_physical):
            pair = (final_by_physical[physical_key], omega_by_physical[physical_key])
            previous = paired.get(physical_key)
            if previous is not None and (
                previous[0].scientific_identity != pair[0].scientific_identity
                or previous[1].scientific_identity != pair[1].scientific_identity
            ):
                raise OSSAxisEquivalenceError(
                    "shared physical OSS row resolves to different axis identities"
                )
            paired.setdefault(physical_key, pair)
    if not paired:
        raise OSSAxisEquivalenceError("OSS axis group contains no physical rows")

    materializer = OSSRowMaterializer(cache, publisher, producer=None)
    decisions: list[dict[str, Any]] = []
    for physical_key in sorted(paired):
        final_request, omega_request = paired[physical_key]
        decision_key = _decision_key(group_id, final_request, omega_request)
        decision = _load_decision(
            cache,
            decision_key,
            group_id=group_id,
            final_request=final_request,
            omega_request=omega_request,
        )
        if decision is None:
            if not allow_expensive_producers:
                raise OSSAxisEquivalenceError(
                    "OSS axis gate cache misses require expensive producer authorization"
                )
            toolchain_method = getattr(toolchain, "produce_with_evidence", None)
            if not callable(toolchain_method):
                raise OSSAxisEquivalenceError(
                    "OSS axis gate cache misses require exact sample-evidence capabilities"
                )
            final_evidence = toolchain_method(final_request)
            omega_evidence = toolchain_method(omega_request)
            if not isinstance(final_evidence, OSSRowExecutionEvidence) or not isinstance(
                omega_evidence,
                OSSRowExecutionEvidence,
            ):
                raise OSSAxisEquivalenceError(
                    "OSS toolchain returned invalid sample-state evidence"
                )
            positions = np.searchsorted(
                omega_evidence.product.feature_ids,
                final_evidence.product.feature_ids,
            )
            if (
                np.any(positions >= omega_evidence.product.feature_ids.size)
                or not np.array_equal(
                    omega_evidence.product.feature_ids[positions],
                    final_evidence.product.feature_ids,
                )
            ):
                raise OSSAxisEquivalenceError(
                    "final fiber IDs are not an exact subset of Omega_max"
                )
            omega_states = omega_evidence.sample_states[:, positions]
            state_mismatch_count = int(
                np.count_nonzero(final_evidence.sample_states != omega_states)
            )
            final_counts = np.count_nonzero(
                final_evidence.sample_states == 1,
                axis=0,
            )
            omega_counts = np.count_nonzero(omega_states == 1, axis=0)
            activation_count_mismatch_count = int(
                np.count_nonzero(final_counts != omega_counts)
            )
            max_probability_difference = float(
                np.max(
                    np.abs(
                        final_evidence.product.probabilities.astype(np.float64)
                        - omega_evidence.product.probabilities[positions].astype(
                            np.float64
                        )
                    )
                )
            )
            status = (
                "pass"
                if state_mismatch_count < 1
                and activation_count_mismatch_count < 1
                and max_probability_difference < OSS_AXIS_PROBABILITY_TOLERANCE
                else "fail"
            )
            final_row_key = build_oss_row_cache_key(
                final_request.row,
                final_request.settings,
            )
            omega_row_key = build_oss_row_cache_key(
                omega_request.row,
                omega_request.settings,
            )
            materializer.publish_product(
                final_request.row,
                final_row_key,
                final_request.settings,
                final_evidence.product,
            )
            materializer.publish_product(
                omega_request.row,
                omega_row_key,
                omega_request.settings,
                omega_evidence.product,
            )
            decision = {
                "schema_version": "dual_frequency_oss_axis_decision_v1",
                "decision_id": decision_key.digest,
                "group_id": group_id,
                "status": status,
                "final_row_identity": final_row_key.digest,
                "omega_row_identity": omega_row_key.digest,
                "state_mismatch_count": state_mismatch_count,
                "activation_count_mismatch_count": activation_count_mismatch_count,
                "max_probability_difference": max_probability_difference,
                "probability_tolerance": OSS_AXIS_PROBABILITY_TOLERANCE,
            }
            _publish_decision(cache, decision_key, decision)
        decisions.append(decision)

    accepted = all(item["status"] == "pass" for item in decisions)
    summary = publisher.document(
        "oss_axis_equivalence.json",
        {
            "schema_version": "dual_frequency_oss_axis_equivalence_v1",
            "group_id": group_id,
            "model_family": model_family,
            "gate_status": (
                "accepted_omega_max" if accepted else "rejected_final_axis"
            ),
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
            "row_decision_ids": sorted(
                str(item["decision_id"]) for item in decisions
            ),
            "row_count": len(decisions),
            "status": "completed",
        },
        kind="oss_axis_equivalence_group",
    )
    return OSSAxisEquivalenceGroupRecord(
        group_id=group_id,
        model_family=model_family,
        gate_status=("accepted_omega_max" if accepted else "rejected_final_axis"),
        final_feature_axis=final_axis,
        omega_feature_axis=omega_axis,
        omega_cache_kind=str(omega_descriptor["cache_kind"]),
        omega_cache_semantic_sha256=str(omega_descriptor["semantic_sha256"]),
        endpoint_ids=endpoint_ids,
        row_decision_ids=tuple(str(item["decision_id"]) for item in decisions),
        artifacts=(summary,),
    )


__all__ = [
    "OSS_AXIS_GATE_VERSION",
    "OSS_AXIS_PROBABILITY_TOLERANCE",
    "OSSAxisEquivalenceError",
    "establish_oss_axis_equivalence",
]
