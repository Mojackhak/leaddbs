"""Portable final-model checkpoints and sensitivity extension plans."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlparse

from ..cache import CacheError, ContentAddressedCache, ScientificCacheKey
from ..cache.identity import sha256_file
from ..contracts import (
    AxisRef,
    ArtifactRef,
    FinalSelectionRecord,
    IndexedArrayView,
    PreparedExposureRecord,
)
from ..contracts.identity import canonical_hash
from ..reporting.artifact_index import record_artifact_closure
from ..workflow import ExecutionPlan, ServiceResult, TaskOutcome, TaskSpec
from ..contracts import TaskKey


class SensitivityCheckpointError(RuntimeError):
    """Raised when a sensitivity checkpoint is incomplete or unsafe."""


CHECKPOINT_SCHEMA = "dual_frequency_sensitivity_checkpoint_v1"
BASE_SCHEMA = "dual_frequency_sensitivity_base_v1"
SEED_SCHEMA = "dual_frequency_sensitivity_seed_tasks_v1"
JITTER_BLOCK_SIZE = 25
JITTER_BLOCK_PRODUCER_VERSION = "1"
JITTER_ADJUSTED_BLOCK_PRODUCER_VERSION = "2"
OSS_SHARED_OMEGA_VERSION = "1"


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _axis_payload(axis: object) -> dict[str, object]:
    return {
        "axis_id": str(getattr(axis, "axis_id")),
        "count": int(getattr(axis, "count")),
        "sha256": str(getattr(axis, "sha256")),
    }


def _omega_max_descriptor(
    *,
    model_family: str,
    shared_exposure_semantic_sha256: str,
    shared_entries: Sequence[Mapping[str, str]],
    cache: ContentAddressedCache,
) -> dict[str, object] | None:
    """Recover one portable Omega_max descriptor from validated cache entries."""

    if not str(model_family).endswith("fiber"):
        return None
    if not shared_entries:
        return None
    candidates = []
    for shared in shared_entries:
        try:
            entry = cache.resolve_identity(
                str(shared["kind"]),
                str(shared["semantic_sha256"]),
            )
        except (KeyError, CacheError) as exc:
            raise SensitivityCheckpointError(
                "Omega_max shared cache identity failed validation"
            ) from exc
        if entry is None:
            raise SensitivityCheckpointError("Omega_max shared cache entry is missing")
        if (
            entry.key.backend_name == "normative_fiber_omega_max"
            and entry.key.stimulation_hash == shared_exposure_semantic_sha256
        ):
            candidates.append(entry)
    if len(candidates) != 1:
        raise SensitivityCheckpointError(
            "fiber sensitivity base must resolve one exact Omega_max cache entry"
        )
    entry = candidates[0]
    payloads = tuple(item for item in entry.files if item.relative_path == "fiber_ids.npy")
    if len(payloads) != 1:
        raise SensitivityCheckpointError("Omega_max cache lacks one fiber_ids payload")
    payload = payloads[0]
    metadata = payload.metadata
    if (
        metadata.dtype != "int64"
        or metadata.shape is None
        or len(metadata.shape) != 1
        or len(metadata.axes) != 1
        or metadata.shape[0] != metadata.axes[0].count
        or metadata.units != "fiber_id"
    ):
        raise SensitivityCheckpointError("Omega_max cache axis metadata is invalid")
    return {
        "cache_kind": entry.key.kind,
        "semantic_sha256": entry.key.digest,
        "feature_axis": _axis_payload(metadata.axes[0]),
        "payload_relative_path": payload.relative_path,
        "payload_sha256": payload.sha256,
    }


def _historical_omega_max_descriptor(
    *,
    model_family: str,
    shared_exposure_semantic_sha256: str,
    shared_entries: Sequence[Mapping[str, str]],
    cache_root: Path,
) -> dict[str, object] | None:
    """Derive a missing descriptor from cache manifests without reading payloads."""

    if not str(model_family).endswith("fiber") or not shared_entries:
        return None
    root = Path(cache_root).expanduser().resolve()
    candidates: list[tuple[str, str, Mapping[str, Any]]] = []
    for shared in shared_entries:
        kind = str(shared.get("kind", "")).strip()
        if kind != "fiber_exposures":
            continue
        digest = str(shared.get("semantic_sha256", "")).strip().lower()
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            continue
        manifest_path = (
            root
            / "shared_exposure_v2"
            / kind
            / digest
            / "manifest.json"
        )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            key = ScientificCacheKey.from_dict(manifest["scientific_cache_key"])
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            continue
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("schema_version") != "scientific_cache_entry_v2"
            or manifest.get("completed") is not True
            or key.kind != kind
            or key.digest != digest
        ):
            continue
        if (
            key.backend_name == "normative_fiber_omega_max"
            and key.stimulation_hash == shared_exposure_semantic_sha256
        ):
            candidates.append((kind, digest, manifest))
    if len(candidates) != 1:
        raise SensitivityCheckpointError(
            "fiber sensitivity base must resolve one exact Omega_max cache manifest"
        )
    kind, digest, manifest = candidates[0]
    files = manifest.get("files")
    if not isinstance(files, list):
        raise SensitivityCheckpointError(
            "Omega_max shared cache manifest files are invalid"
        )
    payloads = [
        item
        for item in files
        if isinstance(item, Mapping)
        and item.get("relative_path") == "fiber_ids.npy"
    ]
    if len(payloads) != 1:
        raise SensitivityCheckpointError(
            "Omega_max cache manifest lacks one fiber_ids payload"
        )
    payload = payloads[0]
    shape = payload.get("shape")
    axes = payload.get("axes")
    axis = axes[0] if isinstance(axes, list) and len(axes) == 1 else None
    axis_id = axis.get("axis_id") if isinstance(axis, Mapping) else None
    axis_count = axis.get("count") if isinstance(axis, Mapping) else None
    axis_sha = axis.get("sha256") if isinstance(axis, Mapping) else None
    if (
        payload.get("dtype") != "int64"
        or not isinstance(shape, list)
        or len(shape) != 1
        or type(shape[0]) is not int
        or shape[0] < 1
        or not isinstance(axes, list)
        or len(axes) != 1
        or not isinstance(axis_id, str)
        or not axis_id.strip()
        or type(axis_count) is not int
        or axis_count != shape[0]
        or not isinstance(axis_sha, str)
        or len(axis_sha) != 64
        or any(
            character not in "0123456789abcdef"
            for character in axis_sha.lower()
        )
        or payload.get("units") != "fiber_id"
    ):
        raise SensitivityCheckpointError(
            "Omega_max cache manifest axis metadata is invalid"
        )
    payload_sha = str(payload.get("sha256", "")).strip().lower()
    if (
        len(payload_sha) != 64
        or any(character not in "0123456789abcdef" for character in payload_sha)
    ):
        raise SensitivityCheckpointError(
            "Omega_max cache manifest payload identity is invalid"
        )
    return {
        "cache_kind": kind,
        "semantic_sha256": digest,
        "feature_axis": {
            "axis_id": axis_id,
            "count": axis_count,
            "sha256": axis_sha.lower(),
        },
        "payload_relative_path": "fiber_ids.npy",
        "payload_sha256": payload_sha,
    }


def _artifact_payload(artifact: ArtifactRef) -> dict[str, object]:
    payload = asdict(artifact)
    payload["shape"] = None if artifact.shape is None else list(artifact.shape)
    payload["axis_refs"] = [_axis_payload(axis) for axis in artifact.axis_refs]
    payload["axis_hashes"] = list(artifact.axis_hashes)
    return payload


def _scientific_array_payload(
    value: ArtifactRef | IndexedArrayView,
    mapper: Callable[[ArtifactRef], ArtifactRef],
) -> dict[str, object]:
    if isinstance(value, ArtifactRef):
        return _artifact_payload(mapper(value))
    return {
        "kind": "indexed_array_view",
        "schema_version": value.schema_version,
        "identifier": value.identifier,
        "parent": _artifact_payload(mapper(value.parent)),
        "row_positions": (
            None
            if value.row_positions is None
            else _artifact_payload(mapper(value.row_positions))
        ),
        "column_positions": (
            None
            if value.column_positions is None
            else _artifact_payload(mapper(value.column_positions))
        ),
        "axis_refs": [_axis_payload(axis) for axis in value.axis_refs],
        "axis_hashes": list(value.axis_hashes),
        "dtype": value.dtype,
        "shape": list(value.shape),
        "units": value.units,
        "space": value.space,
    }


def _remap_value(value: object, mapper: Callable[[ArtifactRef], ArtifactRef]) -> object:
    if isinstance(value, ArtifactRef):
        return mapper(value)
    if is_dataclass(value) and not isinstance(value, type):
        return replace(
            value,
            **{
                field.name: _remap_value(getattr(value, field.name), mapper)
                for field in fields(value)
            },
        )
    if isinstance(value, tuple):
        return tuple(_remap_value(item, mapper) for item in value)
    if isinstance(value, list):
        return [_remap_value(item, mapper) for item in value]
    if isinstance(value, dict):
        return {key: _remap_value(item, mapper) for key, item in value.items()}
    return value


def _portable_mapper(
    run_root: Path,
    cache_root: Path,
    output_root: Path,
) -> Callable[[ArtifactRef], ArtifactRef]:
    roots = (
        ("base-run", run_root.resolve()),
        ("cache", cache_root.resolve()),
        ("output", output_root.resolve()),
    )

    def mapper(artifact: ArtifactRef) -> ArtifactRef:
        parsed = urlparse(artifact.uri)
        if parsed.scheme != "file" or parsed.netloc:
            raise SensitivityCheckpointError("checkpoint artifacts must start as local files")
        path = Path(unquote(parsed.path)).resolve()
        for scheme, root in roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if scheme == "base-run" and (
                relative.parts[:1] == ("runtime_work",)
                or "prepared-memmaps" in relative.parts
            ):
                raise SensitivityCheckpointError(
                    f"sensitivity checkpoint rejects scratch artifact {path}"
                )
            return replace(artifact, uri=f"{scheme}:///{relative.as_posix()}")
        raise SensitivityCheckpointError(
            f"sensitivity artifact is outside durable run, cache, and output roots: {path}"
        )

    return mapper


class _PhysicalArtifactMapper:
    """Resolve a path-safe portable artifact URI without reading its payload."""

    def __init__(self, run_root: Path, cache_root: Path, output_root: Path) -> None:
        self._roots = {
            "base-run": run_root.resolve(),
            "cache": cache_root.resolve(),
            "output": output_root.resolve(),
        }

    def __call__(self, artifact: ArtifactRef) -> ArtifactRef:
        if not isinstance(artifact, ArtifactRef):
            raise SensitivityCheckpointError("checkpoint artifact must be an ArtifactRef")
        parsed = urlparse(artifact.uri)
        root = self._roots.get(parsed.scheme)
        if (
            root is None
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
        ):
            raise SensitivityCheckpointError(
                f"unsupported portable artifact URI {artifact.uri!r}"
            )
        relative = Path(unquote(parsed.path.lstrip("/")))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise SensitivityCheckpointError(
                f"unsafe portable artifact URI {artifact.uri!r}"
            )
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SensitivityCheckpointError(
                f"portable artifact escapes its declared root: {artifact.uri!r}"
            ) from exc
        return replace(artifact, uri=path.as_uri())


def _physical_mapper(
    run_root: Path,
    cache_root: Path,
    output_root: Path,
) -> _PhysicalArtifactMapper:
    return _PhysicalArtifactMapper(run_root, cache_root, output_root)


def _artifact_from_payload(payload: object) -> ArtifactRef:
    if not isinstance(payload, Mapping):
        raise SensitivityCheckpointError("checkpoint artifact payload is invalid")
    expected = {field.name for field in fields(ArtifactRef)}
    if set(payload) != expected:
        raise SensitivityCheckpointError("checkpoint artifact fields are invalid")
    item = dict(payload)
    axes = item.get("axis_refs")
    hashes = item.get("axis_hashes")
    if not isinstance(axes, list) or not isinstance(hashes, list):
        raise SensitivityCheckpointError("checkpoint artifact axes are invalid")
    try:
        item["axis_refs"] = tuple(AxisRef(**dict(axis)) for axis in axes)
        item["axis_hashes"] = tuple(hashes)
        if item.get("shape") is not None:
            if not isinstance(item["shape"], list):
                raise TypeError("artifact shape must be a list")
            item["shape"] = tuple(item["shape"])
        return ArtifactRef(**item)
    except (TypeError, ValueError) as exc:
        raise SensitivityCheckpointError(
            "checkpoint artifact metadata is invalid"
        ) from exc


def _portable_outcome(
    outcome: TaskOutcome,
    mapper: Callable[[ArtifactRef], ArtifactRef],
) -> TaskOutcome:
    if outcome.result is None:
        raise SensitivityCheckpointError("only completed outcomes may seed an extension")
    record = outcome.result.decode_record()
    portable_record = _remap_value(record, mapper)
    result = ServiceResult.from_record(portable_record, facts=outcome.result.facts)
    return replace(outcome, result=result)


def _physical_outcome(
    payload: Mapping[str, Any],
    mapper: Callable[[ArtifactRef], ArtifactRef],
) -> TaskOutcome:
    portable = TaskOutcome.from_dict(payload)
    if portable.status != "completed" or portable.result is None:
        raise SensitivityCheckpointError("seed bundle contains a non-completed outcome")
    record = portable.result.decode_record()
    physical_record = _remap_value(record, mapper)
    result = ServiceResult.from_record(physical_record, facts=portable.result.facts)
    return replace(portable, result=result)


def _input_provenance(
    run_root: Path,
    task_id: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = run_root / "work" / task_id / "input_hash_manifest.json"
    if not path.is_file():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SensitivityCheckpointError(f"input hash manifest is unreadable: {path}") from exc
    if payload.get("schema_version") not in {
        "dual_frequency_prepared_input_hashes_v1",
        "dual_frequency_prepared_input_hashes_v2",
    }:
        raise SensitivityCheckpointError(f"input hash manifest schema is invalid: {path}")
    files_value = payload.get("files")
    if not isinstance(files_value, list):
        raise SensitivityCheckpointError(f"input hash manifest files are invalid: {path}")
    files: list[dict[str, str]] = []
    for item in files_value:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise SensitivityCheckpointError(f"input hash row is invalid: {path}")
        files.append({"path": str(item["path"]), "sha256": str(item["sha256"])})
    shared_value = payload.get("shared_exposures", [])
    if not isinstance(shared_value, list):
        raise SensitivityCheckpointError(
            f"input hash manifest shared exposures are invalid: {path}"
        )
    shared: list[dict[str, str]] = []
    for item in shared_value:
        if not isinstance(item, dict) or set(item) != {"kind", "semantic_sha256"}:
            raise SensitivityCheckpointError(f"shared exposure row is invalid: {path}")
        shared.append(
            {"kind": str(item["kind"]), "semantic_sha256": str(item["semantic_sha256"])}
        )
    return files, shared


def publish_sensitivity_checkpoints(
    *,
    run_root: Path,
    plan: ExecutionPlan,
    outcomes: Sequence[TaskOutcome],
    typed_records: Mapping[str, object],
    run_id: str,
    study_id: str,
    model_set_ids: Mapping[str, str],
    cache_root: Path,
    output_root: Path,
    source_identities: Sequence[Mapping[str, str]],
    rng_profiles: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Publish one portable base per realized final plus one shared seed bundle."""

    root = Path(run_root).resolve()
    target = root / "sensitivity_bases"
    target.mkdir(parents=True, exist_ok=True)
    task_by_id = {task.task_id: task for task in plan.tasks}
    outcome_by_id = {outcome.task_id: outcome for outcome in outcomes}
    mapper = _portable_mapper(root, cache_root, output_root)
    scientific_cache = ContentAddressedCache(cache_root)

    seed_outcomes: list[TaskOutcome] = []
    for task in plan.tasks:
        outcome = outcome_by_id.get(task.task_id)
        if outcome is None:
            continue
        if task.phase == "sensitivity" or outcome.status != "completed":
            continue
        seed_outcomes.append(_portable_outcome(outcome, mapper))
    seed_payload = {
        "schema_version": SEED_SCHEMA,
        "task_states": [
            {"task_id": outcome.task_id, **outcome.as_dict()}
            for outcome in seed_outcomes
        ],
    }
    seed_path = target / "seed_task_states.json"
    _atomic_json(seed_path, seed_payload)
    seed_sha = sha256_file(seed_path)

    bases: list[dict[str, str]] = []
    for task in plan.tasks:
        if task.stage != "final_realization":
            continue
        record = typed_records.get(task.task_id)
        if not isinstance(record, FinalSelectionRecord) or record.final_model is None:
            continue
        final = record.final_model
        endpoint_id = final.endpoint.identifier
        prepare_tasks = tuple(
            candidate
            for candidate in plan.tasks
            if candidate.endpoint_id == endpoint_id and candidate.stage == "prepare_exposure"
        )
        if len(prepare_tasks) != 1:
            raise SensitivityCheckpointError(
                f"realized final {endpoint_id!r} does not have one preparation task"
            )
        prepared = typed_records.get(prepare_tasks[0].task_id)
        if not isinstance(prepared, PreparedExposureRecord):
            raise SensitivityCheckpointError(
                f"realized final {endpoint_id!r} lacks a prepared exposure checkpoint"
            )
        readiness = next(
            (
                typed_records[candidate.task_id]
                for candidate in plan.tasks
                if candidate.endpoint_id == endpoint_id
                and candidate.stage == "input_readiness"
                and candidate.task_id in typed_records
            ),
            None,
        )
        subject_axis = getattr(readiness, "subject_axis", None)
        if subject_axis is None:
            raise SensitivityCheckpointError(
                f"realized final {endpoint_id!r} lacks a subject axis"
            )
        family = final.endpoint.model_family
        profile_key = "direct_voxel" if family.endswith("voxel") else "normative_fiber"
        rng_profile = dict(rng_profiles[profile_key])
        final_artifacts = tuple(record_artifact_closure(final))
        portable_artifacts = tuple(mapper(artifact) for artifact in final_artifacts)
        producers = sorted(
            {
                (artifact.producer_id, artifact.producer_version, artifact.schema_version)
                for artifact in record_artifact_closure(record)
            }
        )
        selected_source = final.selected_source
        if selected_source is None and final.selected_branch is not None:
            selected_source = final.selected_branch.source
        source_files, shared_exposures = _input_provenance(
            root,
            prepare_tasks[0].task_id,
        )
        shared_exposure_semantic_sha256 = (
            (
                prepared.exposure.sha256
                if isinstance(prepared.exposure, ArtifactRef)
                else prepared.exposure.parent.sha256
            )
            if not shared_exposures
            else shared_exposures[0]["semantic_sha256"]
        )
        omega_max = _omega_max_descriptor(
            model_family=family,
            shared_exposure_semantic_sha256=shared_exposure_semantic_sha256,
            shared_entries=shared_exposures,
            cache=scientific_cache,
        )
        base = {
            "schema_version": BASE_SCHEMA,
            "base_run_id": run_id,
            "study_id": study_id,
            "model_set_id": model_set_ids[profile_key],
            "endpoint_id": endpoint_id,
            "scale_id": final.endpoint.scale_id,
            "model_family": family,
            "model_role": "reference" if family.startswith("reference_") else "addon",
            "final_task_id": task.task_id,
            "final_model_record_id": final.identifier,
            "final_model_id": final.final_key.identifier,
            "final_status": final.final_status,
            "realization_role": final.realization_role,
            "final_branch": final.final_key.final_branch,
            "selected_source_record_id": (
                None if selected_source is None else selected_source.identifier
            ),
            "selected_tau": final.final_key.selected_tau,
            "selected_coverage": final.final_key.selected_coverage,
            "subject_axis": _axis_payload(subject_axis),
            "feature_axis": _axis_payload(final.valid_feature_axis.axis),
            "feature_identity_source": final.valid_feature_axis.identity_source,
            "shared_exposure_semantic_sha256": shared_exposure_semantic_sha256,
            "shared_exposure_entries": shared_exposures,
            "shared_exposure_artifact": _scientific_array_payload(
                prepared.exposure,
                mapper,
            ),
            "final_artifacts": [_artifact_payload(item) for item in portable_artifacts],
            "source_content_identities": source_files,
            "configuration_source_identities": [dict(item) for item in source_identities],
            "omega_max": omega_max,
            "oss_axis_gate": {
                "status": "historical_final_axis",
                "reason": "omega_max_equivalence_not_yet_accepted",
            },
            "producer_versions": [
                {
                    "producer_id": producer_id,
                    "producer_version": producer_version,
                    "artifact_schema": schema,
                }
                for producer_id, producer_version, schema in producers
            ],
            "rng_profile": rng_profile,
            "rng_schedule_identity": canonical_hash(
                {"endpoint_id": endpoint_id, "rng_profile": rng_profile}
            ),
            "seed_task_bundle": {
                "path": "../seed_task_states.json",
                "sha256": seed_sha,
            },
        }
        base_path = target / endpoint_id / "sensitivity_base.json"
        _atomic_json(base_path, base)
        bases.append(
            {
                "endpoint_id": endpoint_id,
                "relative_path": base_path.relative_to(target).as_posix(),
                "sha256": sha256_file(base_path),
            }
        )
    index = {
        "schema_version": CHECKPOINT_SCHEMA,
        "study_id": study_id,
        "seed_task_states": {
            "relative_path": seed_path.relative_to(target).as_posix(),
            "sha256": seed_sha,
        },
        "bases": sorted(bases, key=lambda item: item["endpoint_id"]),
    }
    _atomic_json(target / "index.json", index)
    return index


@dataclass(frozen=True)
class LoadedSensitivityCheckpoint:
    base_run: Path
    parent_manifest: dict[str, Any]
    bases: tuple[dict[str, Any], ...]
    _seed_states: tuple[dict[str, Any], ...]
    _artifact_mapper: _PhysicalArtifactMapper

    @property
    def endpoint_ids(self) -> tuple[str, ...]:
        return tuple(str(base["endpoint_id"]) for base in self.bases)

    @property
    def seed_task_ids(self) -> tuple[str, ...]:
        return tuple(str(state["task_id"]) for state in self._seed_states)

    def seed_outcomes_for(self, task_ids: Sequence[str]) -> tuple[TaskOutcome, ...]:
        """Rehydrate only the immutable direct roots selected for one extension."""

        requested = tuple(dict.fromkeys(str(task_id) for task_id in task_ids))
        requested_set = set(requested)
        available = set(self.seed_task_ids)
        missing = tuple(task_id for task_id in requested if task_id not in available)
        if missing:
            raise SensitivityCheckpointError(
                "sensitivity checkpoint lacks completed direct parent outcomes: "
                + ",".join(missing)
            )
        return tuple(
            _physical_outcome(state, self._artifact_mapper)
            for state in self._seed_states
            if str(state["task_id"]) in requested_set
        )


def load_sensitivity_checkpoint(
    base_run: Path,
    *,
    cache_root: Path,
    output_root: Path,
    require_omega_max: bool = False,
) -> LoadedSensitivityCheckpoint:
    """Load the structural parent contract needed to compile a sensitivity child."""

    root = Path(base_run).expanduser().resolve()
    manifest_path = root / "run_manifest.json"
    index_path = root / "sensitivity_bases" / "index.json"
    if not manifest_path.is_file() or not index_path.is_file():
        raise SensitivityCheckpointError("base run lacks a complete sensitivity checkpoint")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SensitivityCheckpointError(
            "base run manifest or sensitivity index is unreadable"
        ) from exc
    if manifest.get("schema_version") != "dual_frequency_run_v1":
        raise SensitivityCheckpointError("unsupported base-run manifest schema")
    if manifest.get("final_status") != "completed":
        raise SensitivityCheckpointError("base run is not completed")
    if index.get("schema_version") != CHECKPOINT_SCHEMA:
        raise SensitivityCheckpointError("unsupported sensitivity checkpoint schema")
    bases: list[dict[str, Any]] = []
    mapper = _physical_mapper(root, cache_root, output_root)
    endpoint_ids: set[str] = set()
    for item in index.get("bases", []):
        if not isinstance(item, dict) or set(item) != {
            "endpoint_id",
            "relative_path",
            "sha256",
        }:
            raise SensitivityCheckpointError("sensitivity base index row is invalid")
        relative = Path(str(item["relative_path"]))
        path = (index_path.parent / relative).resolve()
        if index_path.parent not in path.parents or not path.is_file():
            raise SensitivityCheckpointError("sensitivity base path is unsafe or missing")
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SensitivityCheckpointError("sensitivity base is unreadable") from exc
        if base.get("schema_version") != BASE_SCHEMA:
            raise SensitivityCheckpointError("unsupported sensitivity base schema")
        endpoint_id = str(base.get("endpoint_id", ""))
        if endpoint_id != str(item["endpoint_id"]) or not endpoint_id:
            raise SensitivityCheckpointError("sensitivity base endpoint identity changed")
        if endpoint_id in endpoint_ids:
            raise SensitivityCheckpointError("sensitivity base endpoint is duplicated")
        endpoint_ids.add(endpoint_id)
        shared_entries = base.get("shared_exposure_entries", [])
        if not isinstance(shared_entries, list):
            raise SensitivityCheckpointError("shared exposure entries are invalid")
        for shared in shared_entries:
            if not isinstance(shared, dict) or set(shared) != {
                "kind",
                "semantic_sha256",
            }:
                raise SensitivityCheckpointError("shared exposure identity is invalid")
        model_family = str(base.get("model_family", ""))
        if require_omega_max and model_family.endswith("fiber") and shared_entries:
            descriptor = base.get("omega_max")
            if descriptor is None:
                descriptor = _historical_omega_max_descriptor(
                    model_family=model_family,
                    shared_exposure_semantic_sha256=str(
                        base.get("shared_exposure_semantic_sha256", "")
                    ),
                    shared_entries=shared_entries,
                    cache_root=cache_root,
                )
                base = dict(base)
                base["omega_max"] = descriptor
            required_descriptor_fields = {
                "cache_kind",
                "semantic_sha256",
                "feature_axis",
                "payload_relative_path",
                "payload_sha256",
            }
            if (
                not isinstance(descriptor, Mapping)
                or not required_descriptor_fields.issubset(descriptor)
            ):
                raise SensitivityCheckpointError(
                    "fiber sensitivity base lacks a complete Omega_max descriptor"
                )
            feature_axis = descriptor.get("feature_axis")
            if (
                not isinstance(feature_axis, Mapping)
                or not {"axis_id", "count", "sha256"}.issubset(feature_axis)
            ):
                raise SensitivityCheckpointError(
                    "fiber sensitivity base has an invalid Omega_max feature axis"
                )
        final_artifacts = base.get("final_artifacts")
        if not isinstance(final_artifacts, list):
            raise SensitivityCheckpointError("final-model artifact set is invalid")
        for artifact_payload in final_artifacts:
            mapper(_artifact_from_payload(artifact_payload))
        bases.append(base)
    if not bases:
        raise SensitivityCheckpointError("base run contains no realized final checkpoint")
    seed_ref = index.get("seed_task_states")
    if not isinstance(seed_ref, dict):
        raise SensitivityCheckpointError("sensitivity seed-task reference is missing")
    seed_path = (index_path.parent / str(seed_ref["relative_path"])).resolve()
    if index_path.parent not in seed_path.parents or not seed_path.is_file():
        raise SensitivityCheckpointError("sensitivity seed-task bundle is unsafe or missing")
    try:
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SensitivityCheckpointError(
            "sensitivity seed-task bundle is unreadable"
        ) from exc
    if seed.get("schema_version") != SEED_SCHEMA:
        raise SensitivityCheckpointError("unsupported sensitivity seed-task schema")
    states = seed.get("task_states")
    if not isinstance(states, list):
        raise SensitivityCheckpointError("sensitivity seed-task states are invalid")
    normalized_states: list[dict[str, Any]] = []
    task_ids: set[str] = set()
    expected_state_fields = {
        "task_id",
        "endpoint_id",
        "service_id",
        "status",
        "reason",
        "started_at",
        "finished_at",
        "result",
    }
    expected_result_fields = {
        "output_record_type",
        "record_id",
        "payload",
        "artifacts",
        "facts",
    }
    for state in states:
        if not isinstance(state, dict) or set(state) != expected_state_fields:
            raise SensitivityCheckpointError("sensitivity seed-task state is invalid")
        task_id = str(state["task_id"])
        result = state.get("result")
        if (
            not task_id
            or task_id in task_ids
            or state.get("status") != "completed"
            or not isinstance(result, dict)
            or set(result) != expected_result_fields
            or not isinstance(result.get("payload"), dict)
            or not isinstance(result.get("artifacts"), list)
            or not isinstance(result.get("facts"), dict)
        ):
            raise SensitivityCheckpointError(
                "sensitivity seed bundle contains an invalid completed outcome"
            )
        task_ids.add(task_id)
        normalized_states.append(dict(state))
    return LoadedSensitivityCheckpoint(
        root,
        manifest,
        tuple(bases),
        tuple(normalized_states),
        mapper,
    )


def compile_sensitivity_extension_plan(
    full_plan: ExecutionPlan,
    *,
    endpoint_ids: Sequence[str],
    analyses: Sequence[str],
    seed_task_ids: Sequence[str],
    jitter_bases: Sequence[Mapping[str, Any]] | None = None,
    sensitivity_bases: Sequence[Mapping[str, Any]] | None = None,
) -> ExecutionPlan:
    """Return sensitivity targets bounded by completed direct checkpoint roots."""

    requested = tuple(dict.fromkeys(str(value).strip().lower() for value in analyses))
    allowed = {"jitter", "oss", "final_in_sample"}
    if not requested or any(value not in allowed for value in requested):
        raise SensitivityCheckpointError(
            "analyses must select jitter, oss, final_in_sample, or a combination"
        )
    stages = {
        "jitter": "spatial_jitter",
        "oss": "activation_sensitivity",
        "final_in_sample": "formal_in_sample",
    }
    endpoint_set = set(endpoint_ids)
    source_tasks = {task.task_id: task for task in full_plan.tasks}
    targets = [
        task
        for task in full_plan.tasks
        if task.endpoint_id in endpoint_set
        and any(task.stage == stages[analysis] for analysis in requested)
    ]
    for analysis in requested:
        if not any(task.stage == stages[analysis] for task in targets):
            raise SensitivityCheckpointError(
                f"no realized final supports requested analysis {analysis!r}"
            )
    selected_target_ids = {task.task_id for task in targets}
    if "oss" in requested:
        ppam_services = {
            "prepare_ppam_observed_workspace",
            "prepare_ppam_permutation_schedule",
            "run_ppam_permutation_block",
            "aggregate_ppam_activation",
        }
        frontier = [
            task
            for task in targets
            if task.service_id == "aggregate_ppam_activation"
        ]
        while frontier:
            child = frontier.pop()
            for dependency in child.dependencies:
                parent = source_tasks[dependency]
                if (
                    parent.service_id not in ppam_services
                    or parent.task_id in selected_target_ids
                ):
                    continue
                selected_target_ids.add(parent.task_id)
                frontier.append(parent)
        targets = [
            task for task in full_plan.tasks if task.task_id in selected_target_ids
        ]
    extension_targets: dict[str, TaskSpec] = {}
    for task in targets:
        dependencies = (
            task.dependencies
            if task.stage == "formal_in_sample"
            else tuple(
                dependency
                for dependency in task.dependencies
                if source_tasks[dependency].phase != "formal"
            )
        )
        extension_targets[task.task_id] = replace(
            task,
            phase="sensitivity",
            dependencies=dependencies,
            gates=tuple(
                gate for gate in task.gates if gate.fact != "formal_complete"
            ),
        )
    block_tasks: list[TaskSpec] = []
    oss_gate_tasks: list[TaskSpec] = []
    if "jitter" in requested and jitter_bases is not None:
        bases_by_endpoint = {
            str(base.get("endpoint_id", "")): dict(base) for base in jitter_bases
        }
        jitter_targets = tuple(
            task for task in extension_targets.values() if task.stage == "spatial_jitter"
        )
        missing_bases = tuple(
            sorted(
                task.endpoint_id
                for task in jitter_targets
                if task.endpoint_id not in bases_by_endpoint
            )
        )
        if missing_bases:
            raise SensitivityCheckpointError(
                "jitter extension lacks sensitivity bases for endpoints: "
                + ",".join(missing_bases)
            )

        grouped: dict[str, list[TaskSpec]] = {}
        descriptors: dict[str, dict[str, Any]] = {}
        for task in jitter_targets:
            base = bases_by_endpoint[task.endpoint_id]
            rng = base.get("rng_profile")
            shared = base.get("shared_exposure_entries")
            if not isinstance(rng, Mapping) or not isinstance(shared, list):
                raise SensitivityCheckpointError(
                    "jitter sensitivity base lacks RNG or shared-exposure identity"
                )
            try:
                replicates = int(rng["jitter_resamples"])
                seed = int(rng["seed"])
                fwhm = float(rng["jitter_translation_fwhm_mm"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SensitivityCheckpointError(
                    "jitter sensitivity base has an invalid RNG profile"
                ) from exc
            if replicates < 1 or seed < 0 or not fwhm > 0.0:
                raise SensitivityCheckpointError(
                    "jitter sensitivity base has an invalid RNG schedule"
                )
            final_branch = str(base.get("final_branch", "")).strip()
            adjusted = (
                task.model_family.startswith("addon_")
                and final_branch == "delta_reference_adjusted"
            )
            if task.model_family.startswith("addon_") and final_branch not in {
                "no_delta_reference",
                "delta_reference_adjusted",
            }:
                raise SensitivityCheckpointError(
                    "add-on jitter base has an unsupported final branch"
                )
            normalized_shared: list[dict[str, str]] = []
            for entry in shared:
                if not isinstance(entry, Mapping) or set(entry) != {
                    "kind",
                    "semantic_sha256",
                }:
                    raise SensitivityCheckpointError(
                        "jitter sensitivity base has an invalid shared-exposure entry"
                    )
                normalized_shared.append(
                    {
                        "kind": str(entry["kind"]),
                        "semantic_sha256": str(entry["semantic_sha256"]),
                    }
                )
            descriptor = {
                "model_family": task.model_family,
                "connectome_role": task.connectome_role,
                "final_branch_mode": final_branch,
                "shared_exposure_entries": sorted(
                    normalized_shared,
                    key=lambda item: (item["kind"], item["semantic_sha256"]),
                ),
                "replicates": replicates,
                "seed": seed,
                "translation_fwhm_mm": fwhm,
                "producer_version": (
                    JITTER_ADJUSTED_BLOCK_PRODUCER_VERSION
                    if adjusted
                    else JITTER_BLOCK_PRODUCER_VERSION
                ),
            }
            group_id = f"jitter_group_{canonical_hash(descriptor, length=20)}"
            grouped.setdefault(group_id, []).append(task)
            descriptors[group_id] = descriptor

        adjusted_reference_prepared_by_target: dict[str, str] = {}
        for group_id in sorted(grouped):
            members = tuple(sorted(grouped[group_id], key=lambda item: item.endpoint_id))
            representative = members[0]
            descriptor = descriptors[group_id]
            endpoint_ids_json = json.dumps(
                [task.endpoint_id for task in members],
                separators=(",", ":"),
                sort_keys=True,
            )
            descriptor_json = json.dumps(
                descriptor,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
            dependency_set = {
                dependency for task in members for dependency in task.dependencies
            }
            if descriptor["final_branch_mode"] == "delta_reference_adjusted":
                reference_family = (
                    "reference_voxel"
                    if representative.model_family.endswith("voxel")
                    else "reference_fiber"
                )
                for member in members:
                    reference_inputs = tuple(
                        source_tasks[dependency]
                        for dependency in member.dependencies
                        if source_tasks[dependency].stage == "input_readiness"
                        and source_tasks[dependency].model_family == reference_family
                    )
                    if len(reference_inputs) != 1:
                        raise SensitivityCheckpointError(
                            "adjusted jitter target lacks one matched-reference input"
                        )
                    reference_prepared = tuple(
                        candidate
                        for candidate in full_plan.tasks
                        if candidate.endpoint_id == reference_inputs[0].endpoint_id
                        and candidate.stage == "prepare_exposure"
                    )
                    if len(reference_prepared) != 1:
                        raise SensitivityCheckpointError(
                            "adjusted jitter target lacks one matched-reference preparation"
                        )
                    reference_prepared_id = reference_prepared[0].task_id
                    dependency_set.add(reference_prepared_id)
                    adjusted_reference_prepared_by_target[
                        member.task_id
                    ] = reference_prepared_id
            ordered_dependencies = tuple(
                task.task_id
                for task in full_plan.tasks
                if task.task_id in dependency_set
            )
            for start in range(0, int(descriptor["replicates"]), JITTER_BLOCK_SIZE):
                stop = min(
                    start + JITTER_BLOCK_SIZE,
                    int(descriptor["replicates"]),
                )
                stage = f"jitter_block_{group_id.removeprefix('jitter_group_')}_{start:04d}_{stop:04d}"
                parameters = (
                    ("group_descriptor", descriptor_json),
                    ("group_endpoint_ids", endpoint_ids_json),
                    ("group_id", group_id),
                    ("replicate_start", str(start)),
                    ("replicate_stop", str(stop)),
                )
                key = TaskKey(
                    endpoint_id=representative.endpoint_id,
                    stage=stage,
                    parameter_identity=canonical_hash(
                        {
                            "scientific_configuration_hash": (
                                full_plan.scientific_configuration_hash
                            ),
                            "execution_parameters": parameters,
                        }
                    ),
                )
                block = TaskSpec(
                    key=key,
                    endpoint_id=representative.endpoint_id,
                    model_family=representative.model_family,
                    connectome_role=representative.connectome_role,
                    stage=stage,
                    round_id="round_jitter_blocks",
                    phase="sensitivity",
                    service_id="prepare_jitter_exposure_block",
                    dependencies=ordered_dependencies,
                    gates=(),
                    output_record_type="SensitivityResult",
                    execution_parameters=parameters,
                    expensive_producer=True,
                    cache_first_expensive=True,
                )
                block_tasks.append(block)

        for group_id, members in grouped.items():
            for member in members:
                current = extension_targets[member.task_id]
                dependencies = current.dependencies
                reference_prepared_id = adjusted_reference_prepared_by_target.get(
                    member.task_id
                )
                if (
                    reference_prepared_id is not None
                    and reference_prepared_id not in dependencies
                ):
                    dependencies = (*dependencies, reference_prepared_id)
                extension_targets[member.task_id] = replace(
                    current,
                    dependencies=dependencies,
                    execution_parameters=(
                        *current.execution_parameters,
                        ("jitter_block_group_id", group_id),
                    ),
                )

        physical_block_ids = tuple(task.task_id for task in block_tasks)
        for target in jitter_targets:
            current = extension_targets[target.task_id]
            extension_targets[target.task_id] = replace(
                current,
                dependencies=(*current.dependencies, *physical_block_ids),
            )

    if "oss" in requested:
        bases_by_endpoint = (
            {}
            if sensitivity_bases is None
            else {
                str(base.get("endpoint_id", "")): dict(base)
                for base in sensitivity_bases
            }
        )
        observed_targets = tuple(
            task
            for task in extension_targets.values()
            if task.service_id == "prepare_ppam_observed_workspace"
        )
        grouped_oss: dict[str, list[TaskSpec]] = {}
        oss_descriptors: dict[str, dict[str, Any]] = {}
        for task in observed_targets if sensitivity_bases is not None else ():
            base = bases_by_endpoint.get(task.endpoint_id)
            if base is None:
                raise SensitivityCheckpointError(
                    f"OSS sensitivity base is missing for {task.endpoint_id!r}"
                )
            if not task.model_family.endswith("fiber"):
                raise SensitivityCheckpointError(
                    "OSS sensitivity target must be a normative-fiber endpoint"
                )
            final_axis = base.get("feature_axis")
            omega_max = base.get("omega_max")
            if not isinstance(final_axis, Mapping) or not isinstance(omega_max, Mapping):
                raise SensitivityCheckpointError(
                    "OSS sensitivity base lacks final or Omega_max axis identity"
                )
            descriptor = {
                "preparation_version": OSS_SHARED_OMEGA_VERSION,
                "model_family": task.model_family,
                "final_feature_axis": dict(final_axis),
                "omega_max": dict(omega_max),
            }
            group_id = f"oss_omega_group_{canonical_hash(descriptor, length=20)}"
            grouped_oss.setdefault(group_id, []).append(task)
            oss_descriptors[group_id] = descriptor

        for group_id in sorted(grouped_oss):
            members = tuple(
                sorted(grouped_oss[group_id], key=lambda item: item.endpoint_id)
            )
            representative = members[0]
            descriptor = {
                **oss_descriptors[group_id],
                "group_id": group_id,
                "endpoint_ids": [member.endpoint_id for member in members],
            }
            descriptor_json = json.dumps(
                descriptor,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
            dependency_set = {
                dependency for member in members for dependency in member.dependencies
            }
            ordered_dependencies = tuple(
                task.task_id
                for task in full_plan.tasks
                if task.task_id in dependency_set
            )
            stage = f"oss_omega_max_{group_id.removeprefix('oss_omega_group_')}"
            parameters = (("group_descriptor", descriptor_json),)
            gate_key = TaskKey(
                endpoint_id=representative.endpoint_id,
                stage=stage,
                parameter_identity=canonical_hash(
                    {
                        "scientific_configuration_hash": (
                            full_plan.scientific_configuration_hash
                        ),
                        "execution_parameters": parameters,
                    }
                ),
            )
            gate = TaskSpec(
                key=gate_key,
                endpoint_id=representative.endpoint_id,
                model_family=representative.model_family,
                connectome_role=representative.connectome_role,
                stage=stage,
                round_id="round_oss_omega_max",
                phase="sensitivity",
                service_id="prepare_oss_omega_max_rows",
                dependencies=ordered_dependencies,
                gates=(),
                output_record_type="OSSSharedOmegaGroupRecord",
                execution_parameters=parameters,
                expensive_producer=True,
                cache_first_expensive=True,
            )
            oss_gate_tasks.append(gate)
            for member in members:
                current = extension_targets[member.task_id]
                extension_targets[member.task_id] = replace(
                    current,
                    dependencies=(*current.dependencies, gate.task_id),
                )

    internal_task_ids = {
        *extension_targets,
        *(task.task_id for task in block_tasks),
        *(task.task_id for task in oss_gate_tasks),
    }
    direct_parent_ids = {
        dependency
        for task in (*extension_targets.values(), *block_tasks, *oss_gate_tasks)
        for dependency in task.dependencies
        if dependency not in internal_task_ids
    }
    missing = tuple(sorted(direct_parent_ids - set(seed_task_ids)))
    if missing:
        raise SensitivityCheckpointError(
            "sensitivity checkpoint lacks completed direct parent outcomes: "
            + ",".join(missing)
        )
    checkpoint_roots = {
        task_id: replace(
            source_tasks[task_id],
            dependencies=(),
            gates=(),
            checkpoint_only=True,
        )
        for task_id in direct_parent_ids
    }

    selected_roots = tuple(
        checkpoint_roots[task.task_id]
        for task in full_plan.tasks
        if task.task_id in checkpoint_roots
    )
    selected_targets = tuple(
        extension_targets[task.task_id]
        for task in full_plan.tasks
        if task.task_id in extension_targets
    )
    selected = (*selected_roots, *block_tasks, *oss_gate_tasks, *selected_targets)
    if any(task.phase == "formal" and not task.checkpoint_only for task in selected):
        raise SensitivityCheckpointError(
            "sensitivity extension closure cannot contain formal tasks"
        )
    return ExecutionPlan(
        configuration_hash=full_plan.configuration_hash,
        scientific_configuration_hash=full_plan.scientific_configuration_hash,
        through="sensitivity",
        tasks=selected,
    )


def write_csv_snapshots(
    run_root: Path,
    outcomes: Sequence[TaskOutcome],
    artifact_document: Mapping[str, Any],
) -> None:
    """Write simple interoperable task and artifact CSV snapshots."""

    root = Path(run_root).resolve()
    task_path = root / "task_status.csv"
    with task_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("task_id", "endpoint_id", "service_id", "status", "reason"),
        )
        writer.writeheader()
        for outcome in outcomes:
            writer.writerow(
                {
                    "task_id": outcome.task_id,
                    "endpoint_id": outcome.endpoint_id,
                    "service_id": outcome.service_id,
                    "status": outcome.status,
                    "reason": outcome.reason,
                }
            )
    artifact_path = root / "artifact_index.csv"
    with artifact_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("artifact_id", "kind", "uri", "sha256"),
        )
        writer.writeheader()
        for item in artifact_document.get("artifacts", []):
            writer.writerow({field: item.get(field) for field in writer.fieldnames})


def parent_manifest_sha256(base_run: Path) -> str:
    return sha256_file(Path(base_run).resolve() / "run_manifest.json")


__all__ = [
    "LoadedSensitivityCheckpoint",
    "SensitivityCheckpointError",
    "compile_sensitivity_extension_plan",
    "load_sensitivity_checkpoint",
    "parent_manifest_sha256",
    "publish_sensitivity_checkpoints",
    "write_csv_snapshots",
]
