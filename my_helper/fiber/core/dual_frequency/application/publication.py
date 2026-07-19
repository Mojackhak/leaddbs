"""Canonical publication replay for completed dual-frequency run stores."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlparse

import numpy as np
import yaml

from ..contracts import (
    ArtifactRef,
    BranchRecord,
    EndpointInputRecord,
    FinalSelectionRecord,
    FormalResult,
    ObservedResult,
    PreparedExposureRecord,
    SensitiveRecord,
    SourceRecord,
)
from ..workflow import TaskOutcome


class PublicationError(RuntimeError):
    """Raised when a completed run cannot be projected safely."""


@dataclass(frozen=True)
class PublicationResult:
    """Stable summary of one publication-only replay."""

    run_id: str
    direct_voxel_root: Path
    normative_fiber_root: Path
    direct_voxel_artifact_count: int
    normative_fiber_artifact_count: int
    scale_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "direct_voxel_root": str(self.direct_voxel_root),
            "normative_fiber_root": str(self.normative_fiber_root),
            "direct_voxel_artifact_count": self.direct_voxel_artifact_count,
            "normative_fiber_artifact_count": self.normative_fiber_artifact_count,
            "scale_count": self.scale_count,
        }


@dataclass(frozen=True)
class ExtensionPublicationResult:
    """Stable summary of one final-linked extension replay."""

    source_run_id: str
    extension_id: str
    direct_voxel_root: Path
    normative_fiber_root: Path
    direct_voxel_result_count: int
    normative_fiber_result_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "source_run_id": self.source_run_id,
            "extension_id": self.extension_id,
            "direct_voxel_root": str(self.direct_voxel_root),
            "normative_fiber_root": str(self.normative_fiber_root),
            "direct_voxel_result_count": self.direct_voxel_result_count,
            "normative_fiber_result_count": self.normative_fiber_result_count,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_path(artifact: ArtifactRef) -> Path:
    parsed = urlparse(artifact.uri)
    if parsed.scheme != "file":
        raise PublicationError("canonical publication accepts file artifacts only")
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_file():
        raise PublicationError(f"source artifact is missing: {path}")
    if _sha256_file(path) != artifact.sha256:
        raise PublicationError(f"source artifact SHA-256 mismatch: {path}")
    return path


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: Iterable[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=tuple(fields), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return stream.getvalue().encode("utf-8")


def _plain(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


class _PublicationWriter:
    """Publish immutable files while retaining partial state after a failure."""

    def __init__(self, root: Path, *, domain: str) -> None:
        self.root = Path(root).resolve()
        self.domain = domain
        self.root.mkdir(parents=True, exist_ok=True)
        self.rows: dict[str, dict[str, object]] = {}

    def _target(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PublicationError(f"publication path must be relative: {relative}")
        target = (self.root / candidate).resolve()
        if self.root not in target.parents:
            raise PublicationError(f"publication path escapes model root: {relative}")
        return target

    @staticmethod
    def _install_bytes(target: Path, payload: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = hashlib.sha256(payload).hexdigest()
        if target.is_file():
            if _sha256_file(target) != expected:
                raise PublicationError(f"immutable publication collision: {target}")
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                if _sha256_file(target) != expected:
                    raise PublicationError(f"concurrent publication collision: {target}")
            else:
                os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _install_file(target: Path, source: Path, sha256: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            if _sha256_file(target) != sha256:
                raise PublicationError(f"immutable publication collision: {target}")
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            with temporary.open("rb+") as handle:
                os.fsync(handle.fileno())
            if _sha256_file(temporary) != sha256:
                raise PublicationError(f"copied artifact SHA-256 mismatch: {source}")
            if target.exists():
                if _sha256_file(target) != sha256:
                    raise PublicationError(f"concurrent publication collision: {target}")
            else:
                os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _record(
        self,
        relative: str,
        *,
        artifact_kind: str,
        context: Mapping[str, object],
        status: str = "completed",
    ) -> None:
        target = self._target(relative)
        row: dict[str, object] = {
            "scale_id": context.get("scale_id", ""),
            "model_family": context.get("model_family", ""),
            "branch_id": context.get("branch_id", ""),
            "stage": context.get("stage", ""),
            "artifact_kind": artifact_kind,
            "relative_path": Path(relative).as_posix(),
            "sha256": _sha256_file(target),
            "size_bytes": target.stat().st_size,
            "status": status,
        }
        if self.domain == "normative_fiber":
            row["connectome_id"] = context.get("connectome_id", "")
            row["connectome_role"] = context.get("connectome_role", "")
        previous = self.rows.get(row["relative_path"])
        if previous is not None and previous != row:
            raise PublicationError(f"artifact index collision: {relative}")
        self.rows[str(row["relative_path"])] = row

    def bytes(
        self,
        relative: str,
        payload: bytes,
        *,
        artifact_kind: str,
        context: Mapping[str, object],
    ) -> None:
        target = self._target(relative)
        self._install_bytes(target, payload)
        self._record(relative, artifact_kind=artifact_kind, context=context)

    def json(
        self,
        relative: str,
        payload: Mapping[str, Any],
        *,
        artifact_kind: str,
        context: Mapping[str, object],
    ) -> None:
        self.bytes(
            relative,
            _json_bytes(payload),
            artifact_kind=artifact_kind,
            context=context,
        )

    def csv(
        self,
        relative: str,
        rows: Iterable[Mapping[str, Any]],
        fields: Iterable[str],
        *,
        artifact_kind: str,
        context: Mapping[str, object],
    ) -> None:
        self.bytes(
            relative,
            _csv_bytes(rows, fields),
            artifact_kind=artifact_kind,
            context=context,
        )

    def artifact(
        self,
        relative: str,
        artifact: ArtifactRef,
        *,
        artifact_kind: str,
        context: Mapping[str, object],
    ) -> None:
        source = _artifact_path(artifact)
        target = self._target(relative)
        self._install_file(target, source, artifact.sha256)
        metadata = {
            "schema_version": "dual_frequency_published_artifact_metadata_v1",
            "artifact_kind": artifact_kind,
            "source_artifact": {
                "kind": artifact.kind,
                "schema_version": artifact.schema_version,
                "sha256": artifact.sha256,
                "dtype": artifact.dtype,
                "shape": _plain(artifact.shape),
                "axis_refs": _plain(artifact.axis_refs),
                "axis_hashes": _plain(artifact.axis_hashes),
                "units": artifact.units,
                "space": artifact.space,
                "producer_id": artifact.producer_id,
                "producer_version": artifact.producer_version,
            },
            "published_relative_path": Path(relative).as_posix(),
            "payload_sha256": artifact.sha256,
            "size_bytes": target.stat().st_size,
        }
        self._install_bytes(
            self._target(f"{relative}.metadata.json"),
            _json_bytes(metadata),
        )
        self._record(relative, artifact_kind=artifact_kind, context=context)

    def generated_file(
        self,
        relative: str,
        source: Path,
        *,
        artifact_kind: str,
        context: Mapping[str, object],
        provenance: Mapping[str, object],
    ) -> None:
        source = Path(source).resolve()
        digest = _sha256_file(source)
        target = self._target(relative)
        self._install_file(target, source, digest)
        metadata = {
            "schema_version": "dual_frequency_derived_artifact_metadata_v1",
            "artifact_kind": artifact_kind,
            "published_relative_path": Path(relative).as_posix(),
            "payload_sha256": digest,
            "size_bytes": target.stat().st_size,
            "provenance": dict(provenance),
        }
        self._install_bytes(
            self._target(f"{relative}.metadata.json"),
            _json_bytes(metadata),
        )
        self._record(relative, artifact_kind=artifact_kind, context=context)

    def write_index(self) -> None:
        if self.domain == "direct_voxel":
            fields = (
                "scale_id",
                "model_family",
                "branch_id",
                "stage",
                "artifact_kind",
                "relative_path",
                "sha256",
                "size_bytes",
                "status",
            )
        else:
            fields = (
                "scale_id",
                "model_family",
                "branch_id",
                "connectome_id",
                "connectome_role",
                "stage",
                "artifact_kind",
                "relative_path",
                "sha256",
                "size_bytes",
                "status",
            )
        payload = _csv_bytes(
            (self.rows[key] for key in sorted(self.rows)),
            fields,
        )
        self._install_bytes(self.root / "artifact_index.csv", payload)


def _one_artifact(record: object, kind: str, *, required: bool = True) -> ArtifactRef | None:
    artifacts = tuple(getattr(record, "artifacts", ()))
    matches = tuple(item for item in artifacts if item.kind == kind)
    if len(matches) > 1 or (required and not matches):
        raise PublicationError(
            f"record {type(record).__name__} requires one artifact kind {kind!r}"
        )
    return matches[0] if matches else None


def _source_from_selection(selection: FinalSelectionRecord) -> SourceRecord | None:
    if selection.final_model is None:
        return None
    if selection.final_model.selected_source is not None:
        return selection.final_model.selected_source
    branch = selection.final_model.selected_branch
    return None if branch is None else branch.source


def _stage_status(
    *,
    domain: str,
    endpoint: object,
    branch: str | None,
    stage: str,
    status: str,
    reason: str,
    started: str | None,
    finished: str | None,
    artifacts: Iterable[str],
    connectome_role: str | None = None,
) -> dict[str, object]:
    schema = (
        "direct_voxel_stage_status_v1"
        if domain == "direct_voxel"
        else "normative_fiber_stage_status_v1"
    )
    payload: dict[str, object] = {
        "schema_version": schema,
        "scale_id": endpoint.scale_id,
        "model_family": (
            "reference" if endpoint.model_family.startswith("reference_") else "addon"
        ),
        "branch_id": branch,
        "stage": stage,
        "status": status,
        "reason": reason,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "artifact_relative_paths": sorted(artifacts),
    }
    if domain == "normative_fiber":
        payload["connectome_id"] = endpoint.connectome_id
        payload["connectome_role"] = connectome_role
    return payload


class CanonicalPublisher:
    """Replay one completed parent run into both stable model-set trees."""

    def __init__(self) -> None:
        self._fiber_voxel_cache: dict[tuple[str, str], dict[int, np.ndarray]] = {}
        self._fiber_offset_cache: dict[str, tuple[np.ndarray, np.ndarray, bool]] = {}
        self._file_sha_cache: dict[str, str] = {}

    def _cached_sha256(self, path: Path) -> str:
        resolved = str(Path(path).resolve())
        digest = self._file_sha_cache.get(resolved)
        if digest is None:
            digest = _sha256_file(Path(resolved))
            self._file_sha_cache[resolved] = digest
        return digest

    def publish(
        self,
        run_root: Path,
        *,
        output_root_override: Path | None = None,
    ) -> PublicationResult:
        root = Path(run_root).expanduser().resolve()
        manifest = self._manifest(root)
        resolved = self._yaml(root / "configuration_resolved.yaml")
        study_document = self._json(root / "inputs" / "study_base.json")
        outcomes = self._outcomes(root)
        records = {
            outcome.task_id: outcome.result.decode_record()
            for outcome in outcomes
            if outcome.status == "completed" and outcome.result is not None
        }
        endpoint_keys = self._endpoint_keys(outcomes, records)
        scale_definitions = {
            str(item["scale_id"]): dict(item)
            for item in study_document["study"]["scale_definitions"]
        }
        output_root = (
            Path(output_root_override).expanduser().resolve()
            if output_root_override is not None
            else Path(resolved["direct_voxel"]["output"]["root"]).resolve()
        )
        direct_root = (
            output_root
            / "direct_voxel"
            / str(resolved["direct_voxel"]["model_set_id"])
        )
        fiber_root = (
            output_root
            / "normative_fiber"
            / str(resolved["normative_fiber"]["model_set_id"])
        )
        direct_writer = _PublicationWriter(direct_root, domain="direct_voxel")
        fiber_writer = _PublicationWriter(fiber_root, domain="normative_fiber")

        times = self._run_times(outcomes)
        self._publish_profile(
            direct_writer,
            "resolved_direct_voxel_model.yaml",
            resolved["direct_voxel"],
        )
        self._publish_profile(
            fiber_writer,
            "resolved_normative_fiber_model.yaml",
            resolved["normative_fiber"],
        )
        study_bytes = (root / "inputs" / "study_base.json").read_bytes()
        for writer in (direct_writer, fiber_writer):
            writer.bytes(
                "study_base.json",
                study_bytes,
                artifact_kind="study_base_snapshot",
                context={"stage": "configuration"},
            )

        by_endpoint: dict[str, list[tuple[TaskOutcome, object]]] = defaultdict(list)
        for outcome in outcomes:
            if outcome.task_id in records:
                by_endpoint[outcome.endpoint_id].append((outcome, records[outcome.task_id]))

        direct_scale_rows = self._publish_direct(
            direct_writer,
            resolved,
            study_document,
            scale_definitions,
            endpoint_keys,
            by_endpoint,
            times,
        )
        fiber_scale_rows = self._publish_fiber(
            fiber_writer,
            resolved,
            study_document,
            scale_definitions,
            endpoint_keys,
            by_endpoint,
            times,
        )
        self._publish_scale_status(direct_writer, direct_scale_rows, domain="direct_voxel")
        self._publish_scale_status(fiber_writer, fiber_scale_rows, domain="normative_fiber")
        direct_writer.write_index()
        fiber_writer.write_index()
        self._publish_manifest(
            direct_writer,
            manifest,
            resolved,
            study_document,
            times,
            domain="direct_voxel",
        )
        self._publish_manifest(
            fiber_writer,
            manifest,
            resolved,
            study_document,
            times,
            domain="normative_fiber",
        )
        return PublicationResult(
            run_id=str(manifest["run_id"]),
            direct_voxel_root=direct_root,
            normative_fiber_root=fiber_root,
            direct_voxel_artifact_count=len(direct_writer.rows),
            normative_fiber_artifact_count=len(fiber_writer.rows),
            scale_count=len(resolved["study"]["selected_scales"]),
        )

    def publish_extension(
        self,
        run_root: Path,
        *,
        extension_id: str | None = None,
        output_root_override: Path | None = None,
        selected_scales: tuple[str, ...] = (),
    ) -> ExtensionPublicationResult:
        """Replay one completed final-in-sample child into stable extensions."""

        root = Path(run_root).expanduser().resolve()
        manifest = self._manifest(root)
        resolved = self._yaml(root / "configuration_resolved.yaml")
        aggregate = self._json(
            root / "sensitivity_results" / "final_in_sample_results.json"
        )
        selected_endpoint_ids = {
            str(row["endpoint_id"])
            for row in aggregate["results"]
            if not selected_scales or str(row["scale_id"]) in selected_scales
        }
        outcomes = self._outcomes(root, endpoint_ids=selected_endpoint_ids)
        records = {
            outcome.task_id: outcome.result.decode_record()
            for outcome in outcomes
            if outcome.status == "completed" and outcome.result is not None
        }
        endpoint_keys = self._endpoint_keys(outcomes, records)
        selected_extension_id = str(extension_id or manifest["run_id"]).strip()
        if (
            not selected_extension_id
            or "/" in selected_extension_id
            or "\\" in selected_extension_id
        ):
            raise PublicationError("extension_id must be a nonempty path-safe token")
        base_reference = self._json(root / "base_run_reference.json")
        parent_run_id = str(base_reference["base_run_id"])
        aggregate_rows = {
            str(row["endpoint_id"]): dict(row) for row in aggregate["results"]
        }
        output_root = (
            Path(output_root_override).expanduser().resolve()
            if output_root_override is not None
            else Path(resolved["direct_voxel"]["output"]["root"]).resolve()
        )
        domains = {
            "direct_voxel": (
                output_root
                / "direct_voxel"
                / str(resolved["direct_voxel"]["model_set_id"])
            ),
            "normative_fiber": (
                output_root
                / "normative_fiber"
                / str(resolved["normative_fiber"]["model_set_id"])
            ),
        }
        writers: dict[str, _PublicationWriter] = {}
        for domain, main_root in domains.items():
            self._validate_parent_publication(main_root, parent_run_id)
            writers[domain] = _PublicationWriter(
                main_root / "extensions" / selected_extension_id,
                domain=domain,
            )

        by_endpoint: dict[str, list[tuple[TaskOutcome, object]]] = defaultdict(list)
        for outcome in outcomes:
            if outcome.task_id in records:
                by_endpoint[outcome.endpoint_id].append((outcome, records[outcome.task_id]))
        domain_rows: dict[str, list[dict[str, Any]]] = {
            "direct_voxel": [],
            "normative_fiber": [],
        }
        times = self._run_times(outcomes)
        for endpoint_id, key in endpoint_keys.items():
            if selected_scales and key.scale_id not in selected_scales:
                continue
            endpoint_records = by_endpoint[endpoint_id]
            in_sample = next(
                (
                    record
                    for _, record in endpoint_records
                    if isinstance(record, FormalResult)
                    and record.resampling_kind == "in_sample_permutation"
                ),
                None,
            )
            if in_sample is None:
                continue
            summary = aggregate_rows.get(endpoint_id)
            if summary is None:
                raise PublicationError(
                    f"in-sample aggregate lacks endpoint {endpoint_id}"
                )
            selection = next(
                (
                    record
                    for _, record in endpoint_records
                    if isinstance(record, FinalSelectionRecord)
                ),
                None,
            )
            endpoint_input = next(
                (
                    record
                    for _, record in endpoint_records
                    if isinstance(record, EndpointInputRecord)
                ),
                None,
            )
            if selection is None or selection.final_model is None or endpoint_input is None:
                raise PublicationError(
                    f"in-sample endpoint lacks immutable parent records: {endpoint_id}"
                )
            if in_sample.final_model_id != selection.final_model.identifier:
                raise PublicationError(
                    f"in-sample final-model identity mismatch: {endpoint_id}"
                )
            domain = (
                "direct_voxel"
                if key.model_family.endswith("voxel")
                else "normative_fiber"
            )
            writer = writers[domain]
            role = (
                "reference" if key.model_family.startswith("reference_") else "addon"
            )
            branch = (
                "reference"
                if role == "reference"
                else selection.final_model.selected_branch.branch
            )
            base = f"{key.scale_id}/{role}/sensitivity/final_in_sample"
            context: dict[str, object] = {
                "scale_id": key.scale_id,
                "model_family": role,
                "branch_id": None if role == "reference" else branch,
                "stage": "final_in_sample",
            }
            if domain == "normative_fiber":
                context["connectome_id"] = key.connectome_id
                context["connectome_role"] = "formal"
            artifact_names = {
                "in_sample_candidate_feature_ids": "candidate_feature_ids.npy",
                "in_sample_candidate_parent_indices": "candidate_parent_indices.npy",
                "in_sample_observed_benefit_oriented_weights": "observed_weights.npy",
                "in_sample_observed_spatial_scores": "observed_scores.npy",
                "in_sample_model_predictions": "model_predictions.npy",
                "in_sample_baseline_predictions": "baseline_predictions.npy",
                "formal_permutation_schedule": "permutation_schedule.npy",
                "in_sample_permutation_null_statistics": "permutation_null_statistics.npy",
                "formal_in_sample_summary": "technical_summary.json",
            }
            artifact_paths: list[str] = []
            artifacts = {item.kind: item for item in in_sample.artifacts}
            for kind, name in artifact_names.items():
                artifact = artifacts[kind]
                relative = f"{base}/{name}"
                writer.artifact(
                    relative,
                    artifact,
                    artifact_kind=kind,
                    context=context,
                )
                artifact_paths.append(relative)
            summary_path = f"{base}/summary.json"
            writer.json(
                summary_path,
                {
                    "schema_version": "dual_frequency_final_in_sample_endpoint_v1",
                    **summary,
                    "source_extension_run_id": manifest["run_id"],
                    "parent_run_id": parent_run_id,
                },
                artifact_kind="final_in_sample_summary",
                context=context,
            )
            artifact_paths.append(summary_path)
            predictions_path = self._publish_extension_predictions(
                writer,
                source=_source_from_selection(selection),
                endpoint_input=endpoint_input,
                in_sample=in_sample,
                base=base,
                context=context,
            )
            artifact_paths.append(predictions_path)
            status_path = f"{base}/status.json"
            writer.json(
                status_path,
                _stage_status(
                    domain=domain,
                    endpoint=key,
                    branch=None if role == "reference" else branch,
                    stage="final_in_sample",
                    status="completed",
                    reason="completed",
                    started=times[0],
                    finished=times[1],
                    artifacts=artifact_paths,
                    connectome_role=(
                        None if domain == "direct_voxel" else "formal"
                    ),
                ),
                artifact_kind="stage_status",
                context=context,
            )
            domain_rows[domain].append(summary)

        for domain, writer in writers.items():
            rows = sorted(
                domain_rows[domain],
                key=lambda row: (str(row["scale_id"]), str(row["model_family"])),
            )
            if not rows:
                raise PublicationError(f"extension has no {domain} final-in-sample results")
            writer.json(
                "final_in_sample_results.json",
                {
                    **{key: value for key, value in aggregate.items() if key != "results"},
                    "result_count": len(rows),
                    "results": rows,
                },
                artifact_kind="final_in_sample_results",
                context={"stage": "final_in_sample"},
            )
            writer.csv(
                "final_in_sample_results.csv",
                rows,
                tuple(rows[0]),
                artifact_kind="final_in_sample_results",
                context={"stage": "final_in_sample"},
            )
            writer.write_index()
            parent_manifest_path = domains[domain] / "model_manifest.json"
            extension_manifest = {
                "schema_version": "dual_frequency_extension_manifest_v2",
                "extension_id": selected_extension_id,
                "source_extension_run_id": manifest["run_id"],
                "parent_run_id": parent_run_id,
                "parent_publication_root": str(domains[domain]),
                "parent_publication_manifest_sha256": _sha256_file(
                    parent_manifest_path
                ),
                "parent_scientific_configuration_hash": manifest[
                    "scientific_configuration_hash"
                ],
                "analyses": ["final_in_sample"],
                "result_count": len(rows),
                "started_at_utc": times[0],
                "finished_at_utc": times[1],
                "status": "completed",
            }
            _PublicationWriter._install_bytes(
                writer.root / "extension_manifest.json",
                _json_bytes(extension_manifest),
            )
        return ExtensionPublicationResult(
            source_run_id=str(manifest["run_id"]),
            extension_id=selected_extension_id,
            direct_voxel_root=writers["direct_voxel"].root,
            normative_fiber_root=writers["normative_fiber"].root,
            direct_voxel_result_count=len(domain_rows["direct_voxel"]),
            normative_fiber_result_count=len(domain_rows["normative_fiber"]),
        )

    @staticmethod
    def _validate_parent_publication(root: Path, parent_run_id: str) -> None:
        manifest_path = Path(root) / "model_manifest.json"
        payload = CanonicalPublisher._json(manifest_path)
        if payload.get("final_status") != "completed":
            raise PublicationError(f"parent publication is not complete: {root}")
        if payload.get("source_run_id") != parent_run_id:
            raise PublicationError(
                f"parent publication run identity mismatch: {root}"
            )
        index = Path(root) / "artifact_index.csv"
        if not index.is_file():
            raise PublicationError(f"parent publication index is missing: {root}")

    def _publish_extension_predictions(
        self,
        writer: _PublicationWriter,
        *,
        source: SourceRecord,
        endpoint_input: EndpointInputRecord,
        in_sample: FormalResult,
        base: str,
        context: Mapping[str, object],
    ) -> str:
        in_sample_artifacts = {item.kind: item for item in in_sample.artifacts}
        source_artifacts = {item.kind: item for item in source.artifacts}
        in_sample_predictions = np.asarray(
            np.load(
                _artifact_path(in_sample_artifacts["in_sample_model_predictions"]),
                allow_pickle=False,
            )
        )
        in_sample_baseline = np.asarray(
            np.load(
                _artifact_path(in_sample_artifacts["in_sample_baseline_predictions"]),
                allow_pickle=False,
            )
        )
        loocv_kind = (
            "loocv_model_predictions"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_loocv_model_predictions"
        )
        loocv_baseline_kind = (
            "loocv_baseline_predictions"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_loocv_baseline_predictions"
        )
        loocv_predictions = np.asarray(
            np.load(_artifact_path(source_artifacts[loocv_kind]), allow_pickle=False)
        )
        loocv_baseline = np.asarray(
            np.load(
                _artifact_path(source_artifacts[loocv_baseline_kind]),
                allow_pickle=False,
            )
        )
        outcome = np.asarray(
            np.load(_artifact_path(endpoint_input.outcome), allow_pickle=False)
        )
        rows = [
            {
                "subject_id": subject_id,
                "outcome": float(outcome[index]),
                "in_sample_prediction": float(in_sample_predictions[index]),
                "loocv_prediction": float(loocv_predictions[index]),
                "in_sample_baseline_prediction": float(in_sample_baseline[index]),
                "loocv_baseline_prediction": float(loocv_baseline[index]),
            }
            for index, subject_id in enumerate(endpoint_input.included_subject_ids)
        ]
        relative = f"{base}/predictions.csv"
        writer.csv(
            relative,
            rows,
            tuple(rows[0]),
            artifact_kind="paired_predictions",
            context=context,
        )
        return relative

    @staticmethod
    def _manifest(root: Path) -> dict[str, Any]:
        payload = CanonicalPublisher._json(root / "run_manifest.json")
        if payload.get("final_status") != "completed":
            raise PublicationError("canonical replay requires a completed run manifest")
        return payload

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicationError(f"cannot read required JSON: {path}") from exc
        if not isinstance(value, dict):
            raise PublicationError(f"required JSON must contain an object: {path}")
        return value

    @staticmethod
    def _yaml(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PublicationError(f"cannot read required YAML: {path}") from exc
        if not isinstance(value, dict):
            raise PublicationError(f"required YAML must contain an object: {path}")
        return value

    @staticmethod
    def _outcomes(
        root: Path,
        *,
        endpoint_ids: set[str] | None = None,
    ) -> tuple[TaskOutcome, ...]:
        outcomes: list[TaskOutcome] = []
        selected_task_ids: set[str] | None = None
        status_path = root / "task_status.csv"
        if status_path.is_file():
            try:
                with status_path.open("r", encoding="utf-8", newline="") as handle:
                    rows = tuple(csv.DictReader(handle))
            except OSError as exc:
                raise PublicationError(f"cannot read task status: {status_path}") from exc
            failed = tuple(
                row["task_id"] for row in rows if row.get("status") == "failed"
            )
            if failed:
                raise PublicationError(
                    f"completed publication input retains failed tasks: {len(failed)}"
                )
            selected_task_ids = {
                str(row["task_id"])
                for row in rows
                if endpoint_ids is None
                or str(row.get("endpoint_id", "")) in endpoint_ids
            }
        paths = (
            sorted((root / "tasks").glob("task_*.json"))
            if selected_task_ids is None
            else [
                root / "tasks" / f"{task_id}.json"
                for task_id in sorted(selected_task_ids)
            ]
        )
        if not paths:
            raise PublicationError("completed run has no persisted task states")

        def load(path: Path) -> TaskOutcome:
            payload = CanonicalPublisher._json(path)
            try:
                return TaskOutcome.from_dict(payload)
            except Exception as exc:
                raise PublicationError(f"invalid persisted task state: {path}") from exc
        with ThreadPoolExecutor(max_workers=min(16, len(paths))) as executor:
            outcomes.extend(executor.map(load, paths))
        failed = tuple(item.task_id for item in outcomes if item.status == "failed")
        if failed:
            raise PublicationError(
                f"completed publication input retains failed tasks: {len(failed)}"
            )
        return tuple(outcomes)

    @staticmethod
    def _endpoint_keys(
        outcomes: Iterable[TaskOutcome], records: Mapping[str, object]
    ) -> dict[str, object]:
        keys: dict[str, object] = {}
        for outcome in outcomes:
            record = records.get(outcome.task_id)
            endpoint = getattr(record, "endpoint", None)
            if endpoint is None and isinstance(record, ObservedResult) and record.source is not None:
                endpoint = record.source.endpoint
            if endpoint is not None:
                previous = keys.get(outcome.endpoint_id)
                if previous is not None and previous != endpoint:
                    raise PublicationError("endpoint identity changed across task records")
                keys[outcome.endpoint_id] = endpoint
        return keys

    @staticmethod
    def _run_times(outcomes: Iterable[TaskOutcome]) -> tuple[str | None, str | None]:
        starts = sorted(item.started_at for item in outcomes if item.started_at)
        finishes = sorted(item.finished_at for item in outcomes if item.finished_at)
        return (starts[0] if starts else None, finishes[-1] if finishes else None)

    @staticmethod
    def _publish_profile(
        writer: _PublicationWriter,
        name: str,
        profile: Mapping[str, Any],
    ) -> None:
        payload = yaml.safe_dump(dict(profile), sort_keys=True, allow_unicode=False).encode(
            "utf-8"
        )
        writer.bytes(
            name,
            payload,
            artifact_kind="resolved_model_profile",
            context={"stage": "configuration"},
        )

    @staticmethod
    def _publish_scale_status(
        writer: _PublicationWriter,
        rows: list[dict[str, object]],
        *,
        domain: str,
    ) -> None:
        fields = tuple(rows[0]) if rows else ("scale_id",)
        writer.csv(
            "scale_status.csv",
            rows,
            fields,
            artifact_kind="scale_status",
            context={"stage": "status"},
        )
        for row in rows:
            writer.json(
                f"{row['scale_id']}/scale_status.json",
                {"schema_version": f"{domain}_scale_status_v1", **row},
                artifact_kind="scale_status",
                context={"scale_id": row["scale_id"], "stage": "status"},
            )

    def _publish_direct(
        self,
        writer: _PublicationWriter,
        resolved: Mapping[str, Any],
        study: Mapping[str, Any],
        scale_definitions: Mapping[str, Mapping[str, Any]],
        endpoint_keys: Mapping[str, object],
        by_endpoint: Mapping[str, list[tuple[TaskOutcome, object]]],
        times: tuple[str | None, str | None],
    ) -> list[dict[str, object]]:
        scale_rows: list[dict[str, object]] = []
        for scale_id in resolved["direct_voxel"]["scales"]:
            endpoints = [
                (endpoint_id, key)
                for endpoint_id, key in endpoint_keys.items()
                if key.scale_id == scale_id and key.model_family.endswith("voxel")
            ]
            selections: dict[str, FinalSelectionRecord] = {}
            for endpoint_id, key in endpoints:
                records = by_endpoint[endpoint_id]
                selection = next(
                    (
                        record
                        for _, record in records
                        if isinstance(record, FinalSelectionRecord)
                    ),
                    None,
                )
                if selection is None:
                    raise PublicationError(
                        f"direct endpoint lacks FinalSelectionRecord: {endpoint_id}"
                    )
                selections[key.model_family] = selection
                self._publish_direct_endpoint(
                    writer,
                    selection,
                    records,
                    scale_definitions[scale_id],
                    study,
                    times,
                )
            reference = selections["reference_voxel"]
            addon = selections["addon_voxel"]
            reference_source = _source_from_selection(reference)
            addon_source = _source_from_selection(addon)
            addon_branch = (
                None
                if addon.final_model is None or addon.final_model.selected_branch is None
                else addon.final_model.selected_branch.branch
            )
            scale_rows.append(
                {
                    "scale_id": scale_id,
                    "scale_direction": scale_definitions[scale_id]["direction"],
                    "reference_input_status": (
                        "valid" if reference_source is not None else "input_failure"
                    ),
                    "reference_source_status": (
                        reference_source.source_status if reference_source else "none"
                    ),
                    "reference_prediction_status": (
                        reference_source.prediction_status if reference_source else "not_applicable"
                    ),
                    "reference_final_status": reference.selection_status,
                    "addon_intended_primary_branch": "delta_reference_adjusted",
                    "addon_final_branch": addon_branch or "",
                    "addon_final_role": (
                        addon.final_model.realization_role if addon.final_model else "no_final_model"
                    ),
                    "addon_final_status": addon.selection_status,
                    "overall_status": "completed",
                    "failure_reason": "",
                }
            )
        return scale_rows

    def _publish_direct_endpoint(
        self,
        writer: _PublicationWriter,
        selection: FinalSelectionRecord,
        records: list[tuple[TaskOutcome, object]],
        scale_definition: Mapping[str, Any],
        study: Mapping[str, Any],
        times: tuple[str | None, str | None],
    ) -> None:
        endpoint = selection.endpoint
        role = "reference" if endpoint.model_family.startswith("reference_") else "addon"
        source = _source_from_selection(selection)
        branch = "reference"
        if selection.final_model is not None and selection.final_model.selected_branch is not None:
            branch = selection.final_model.selected_branch.branch
        base = f"{endpoint.scale_id}/{role}"
        resolver = f"{base}/resolver" if role == "reference" else f"{base}/branches/{branch}/resolver"
        observed = f"{base}/observed" if role == "reference" else f"{base}/branches/{branch}/observed"
        context = {
            "scale_id": endpoint.scale_id,
            "model_family": role,
            "branch_id": None if role == "reference" else branch,
        }
        final_document: dict[str, object]
        if source is None or selection.final_model is None:
            final_document = {
                "schema_version": "direct_voxel_final_model_v1",
                "final_model_id": None,
                "scale_id": endpoint.scale_id,
                "model_family": role,
                "intended_primary_branch": (
                    "reference" if role == "reference" else "delta_reference_adjusted"
                ),
                "realized_final_branch": None,
                "final_role": "no_final_model",
                "final_status": selection.selection_status,
                "source_status": "none",
                "prediction_status": "not_applicable",
                "selected_tau_v_per_m": None,
                "selected_coverage_subjects_min": None,
                "selected_adjacent_passing_cells": None,
                "source_record_relative_path": None,
                "artifact_relative_paths": [],
                "failure_reasons": list(selection.reason_codes),
            }
            writer.json(
                f"{base}/final_model.json",
                final_document,
                artifact_kind="final_model",
                context={**context, "stage": "final"},
            )
            return

        if role == "addon":
            endpoint_input = next(
                record for _, record in records if isinstance(record, EndpointInputRecord)
            )
            prepared = next(
                record for _, record in records if isinstance(record, PreparedExposureRecord)
            )
            for branch_record in (
                record for _, record in records if isinstance(record, BranchRecord)
            ):
                if branch_record.branch == branch or branch_record.source is None:
                    continue
                self._publish_direct_nonfinal_branch(
                    writer,
                    branch_record,
                    endpoint_input,
                    prepared,
                    scale_definition,
                    study,
                    times,
                )

        artifacts_by_kind = {item.kind: item for item in source.artifacts}
        grid_kind = (
            "direct_voxel_grid_metrics"
            if role == "reference"
            else "addon_direct_voxel_grid_metrics"
        )
        grid_artifact = artifacts_by_kind[grid_kind]
        grid = self._json(_artifact_path(grid_artifact))
        cells = list(grid["cells"])
        scan_fields = tuple(sorted({key for row in cells for key in row}))
        writer.csv(
            f"{observed}/source_scan.csv",
            cells,
            scan_fields,
            artifact_kind="source_scan",
            context={**context, "stage": "observed"},
        )
        writer.json(
            f"{observed}/source_scan_qc.json",
            {
                "schema_version": "direct_voxel_source_scan_qc_v1",
                "cell_count": len(cells),
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
            },
            artifact_kind="source_scan_qc",
            context={**context, "stage": "observed"},
        )
        observed_artifacts = [
            f"{observed}/source_scan.csv",
            f"{observed}/source_scan_qc.json",
        ]
        writer.json(
            f"{observed}/status.json",
            _stage_status(
                domain="direct_voxel",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="observed",
                status="completed",
                reason="completed",
                started=times[0],
                finished=times[1],
                artifacts=observed_artifacts,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "observed"},
        )

        copy_map = {
            "selected_feature_indices": "valid_voxel_indices.npy",
            "benefit_oriented_feature_weights": "full_weights.npy",
            "loocv_benefit_oriented_feature_weights": "fold_weights.npy",
            "loocv_valid_feature_masks": "fold_valid_masks.npy",
        }
        resolver_paths: list[str] = []
        for kind, name in copy_map.items():
            artifact = artifacts_by_kind[kind]
            relative = f"{resolver}/{name}"
            writer.artifact(
                relative,
                artifact,
                artifact_kind=kind,
                context={**context, "stage": "resolver"},
            )
            resolver_paths.append(relative)

        endpoint_input = next(
            record for _, record in records if isinstance(record, EndpointInputRecord)
        )
        prepared = next(
            record for _, record in records if isinstance(record, PreparedExposureRecord)
        )
        scores_path, predictions_path, subject_order_path = self._publish_score_tables(
            writer,
            source,
            endpoint_input,
            resolver,
            context,
        )
        resolver_paths.extend((scores_path, predictions_path, subject_order_path))
        nifti_paths = self._publish_direct_nifti(
            writer,
            source,
            prepared,
            endpoint,
            scale_definition,
            study,
            resolver,
            base,
            context,
        )
        resolver_paths.extend(
            path for path in nifti_paths if path.startswith(f"{resolver}/")
        )
        report_paths = [
            path for path in nifti_paths if path.startswith(f"{base}/report/")
        ]
        report_summary_path = f"{base}/report/summary.json"
        writer.json(
            report_summary_path,
            {
                "schema_version": "direct_voxel_report_summary_v1",
                "scale_id": endpoint.scale_id,
                "model_family": role,
                "final_model_id": selection.final_model.identifier,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "display_artifact_relative_paths": sorted(report_paths),
                "display_only": True,
            },
            artifact_kind="report_summary",
            context={**context, "stage": "report"},
        )
        report_paths.append(report_summary_path)
        writer.json(
            f"{base}/report/status.json",
            _stage_status(
                domain="direct_voxel",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="report",
                status="completed",
                reason="display_derivatives_completed",
                started=times[0],
                finished=times[1],
                artifacts=report_paths,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "report"},
        )
        selected_source_path = f"{resolver}/selected_source.json"
        selected_source = {
            "schema_version": "direct_voxel_selected_source_v1",
            "source_record_id": source.identifier,
            "selected_tau_v_per_m": source.selected_tau,
            "selected_coverage_subjects_min": source.selected_coverage,
            "threshold_source": source.threshold_source,
            "selected_adjacent_passing_cells": source.adjacent_support,
            "scale_direction": scale_definition["direction"],
            "subject_axis_sha256": endpoint_input.subject_axis.sha256,
            "voxel_axis_sha256": source.feature_axis.axis.sha256,
            "artifact_relative_paths": sorted(resolver_paths),
        }
        writer.json(
            selected_source_path,
            selected_source,
            artifact_kind="selected_source",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(selected_source_path)
        writer.json(
            f"{resolver}/source_status.json",
            {
                "input_status": source.input_status,
                "source_status": source.source_status,
                "prediction_status": source.prediction_status,
                "threshold_source": source.threshold_source,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "selected_adjacent_passing_cells": source.adjacent_support,
                "source_failure_reasons": [],
            },
            artifact_kind="source_status",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(f"{resolver}/source_status.json")
        writer.json(
            f"{resolver}/status.json",
            _stage_status(
                domain="direct_voxel",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="resolver",
                status="completed",
                reason="completed",
                started=times[0],
                finished=times[1],
                artifacts=resolver_paths,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "resolver"},
        )
        final_document = {
            "schema_version": "direct_voxel_final_model_v1",
            "final_model_id": selection.final_model.identifier,
            "scale_id": endpoint.scale_id,
            "model_family": role,
            "intended_primary_branch": (
                "reference" if role == "reference" else "delta_reference_adjusted"
            ),
            "realized_final_branch": branch,
            "final_role": selection.final_model.realization_role,
            "final_status": selection.selection_status,
            "source_status": source.source_status,
            "prediction_status": source.prediction_status,
            "selected_tau_v_per_m": source.selected_tau,
            "selected_coverage_subjects_min": source.selected_coverage,
            "selected_adjacent_passing_cells": source.adjacent_support,
            "source_record_relative_path": selected_source_path,
            "artifact_relative_paths": sorted(resolver_paths),
            "failure_reasons": [],
        }
        writer.json(
            f"{base}/final_model.json",
            final_document,
            artifact_kind="final_model",
            context={**context, "stage": "final"},
        )
        self._publish_formal(
            writer,
            selection,
            records,
            base,
            context,
            domain="direct_voxel",
            direct_nifti=(prepared, endpoint, study),
            times=times,
        )
        self._publish_sensitivity_base(writer, selection, base, context)

    def _publish_direct_nonfinal_branch(
        self,
        writer: _PublicationWriter,
        branch_record: BranchRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        scale_definition: Mapping[str, Any],
        study: Mapping[str, Any],
        times: tuple[str | None, str | None],
    ) -> None:
        source = branch_record.source
        if source is None:
            return
        endpoint = branch_record.endpoint
        base = f"{endpoint.scale_id}/addon"
        observed = f"{base}/branches/{branch_record.branch}/observed"
        resolver = f"{base}/branches/{branch_record.branch}/resolver"
        context = {
            "scale_id": endpoint.scale_id,
            "model_family": "addon",
            "branch_id": branch_record.branch,
        }
        artifacts = {item.kind: item for item in source.artifacts}
        grid = self._json(_artifact_path(artifacts["addon_direct_voxel_grid_metrics"]))
        cells = list(grid["cells"])
        scan_fields = tuple(sorted({key for row in cells for key in row}))
        writer.csv(
            f"{observed}/source_scan.csv",
            cells,
            scan_fields,
            artifact_kind="source_scan",
            context={**context, "stage": "observed"},
        )
        writer.json(
            f"{observed}/source_scan_qc.json",
            {
                "schema_version": "direct_voxel_source_scan_qc_v1",
                "cell_count": len(cells),
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
            },
            artifact_kind="source_scan_qc",
            context={**context, "stage": "observed"},
        )
        observed_paths = [
            f"{observed}/source_scan.csv",
            f"{observed}/source_scan_qc.json",
        ]
        writer.json(
            f"{observed}/status.json",
            _stage_status(
                domain="direct_voxel",
                endpoint=endpoint,
                branch=branch_record.branch,
                stage="observed",
                status="completed",
                reason="completed_nonfinal_branch",
                started=times[0],
                finished=times[1],
                artifacts=observed_paths,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "observed"},
        )
        resolver_paths: list[str] = []
        for kind, name in (
            ("selected_feature_indices", "valid_voxel_indices.npy"),
            ("benefit_oriented_feature_weights", "full_weights.npy"),
            ("loocv_benefit_oriented_feature_weights", "fold_weights.npy"),
            ("loocv_valid_feature_masks", "fold_valid_masks.npy"),
        ):
            relative = f"{resolver}/{name}"
            writer.artifact(
                relative,
                artifacts[kind],
                artifact_kind=kind,
                context={**context, "stage": "resolver"},
            )
            resolver_paths.append(relative)
        resolver_paths.extend(
            self._publish_score_tables(
                writer,
                source,
                endpoint_input,
                resolver,
                context,
            )
        )
        resolver_paths.extend(
            path
            for path in self._publish_direct_nifti(
                writer,
                source,
                prepared,
                endpoint,
                scale_definition,
                study,
                resolver,
                base,
                context,
                publish_report_display=False,
            )
            if path.startswith(f"{resolver}/")
        )
        selected_source_path = f"{resolver}/selected_source.json"
        writer.json(
            selected_source_path,
            {
                "schema_version": "direct_voxel_selected_source_v1",
                "source_record_id": source.identifier,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "threshold_source": source.threshold_source,
                "selected_adjacent_passing_cells": source.adjacent_support,
                "scale_direction": scale_definition["direction"],
                "subject_axis_sha256": endpoint_input.subject_axis.sha256,
                "voxel_axis_sha256": source.feature_axis.axis.sha256,
                "artifact_relative_paths": sorted(resolver_paths),
            },
            artifact_kind="selected_source",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(selected_source_path)
        source_status_path = f"{resolver}/source_status.json"
        writer.json(
            source_status_path,
            {
                "input_status": source.input_status,
                "source_status": source.source_status,
                "prediction_status": source.prediction_status,
                "threshold_source": source.threshold_source,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "selected_adjacent_passing_cells": source.adjacent_support,
                "source_failure_reasons": [],
                "final_branch_selected": False,
            },
            artifact_kind="source_status",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(source_status_path)
        writer.json(
            f"{resolver}/status.json",
            _stage_status(
                domain="direct_voxel",
                endpoint=endpoint,
                branch=branch_record.branch,
                stage="resolver",
                status="completed",
                reason="completed_nonfinal_branch",
                started=times[0],
                finished=times[1],
                artifacts=resolver_paths,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "resolver"},
        )

    def _publish_score_tables(
        self,
        writer: _PublicationWriter,
        source: SourceRecord,
        endpoint_input: EndpointInputRecord,
        resolver: str,
        context: Mapping[str, object],
    ) -> tuple[str, str, str]:
        role = str(context["model_family"])
        artifacts = {item.kind: item for item in source.artifacts}
        score_kind = (
            "continuous_weighted_mean_scores"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_full_scores"
        )
        heldout_kind = (
            "loocv_heldout_scores"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_loocv_heldout_scores"
        )
        model_kind = (
            "loocv_model_predictions"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_loocv_model_predictions"
        )
        baseline_kind = (
            "loocv_baseline_predictions"
            if source.endpoint.model_family.endswith("voxel")
            else "normative_fiber_loocv_baseline_predictions"
        )
        scores = np.asarray(np.load(_artifact_path(artifacts[score_kind]), allow_pickle=False))
        heldout = np.asarray(np.load(_artifact_path(artifacts[heldout_kind]), allow_pickle=False))
        model = np.asarray(np.load(_artifact_path(artifacts[model_kind]), allow_pickle=False))
        baseline_predictions = np.asarray(
            np.load(_artifact_path(artifacts[baseline_kind]), allow_pickle=False)
        )
        outcome = np.asarray(
            np.load(_artifact_path(endpoint_input.outcome), allow_pickle=False)
        )
        baseline = np.asarray(
            np.load(_artifact_path(endpoint_input.baseline), allow_pickle=False)
        )
        subject_ids = endpoint_input.included_subject_ids
        score_name = "reference_score" if role == "reference" else "addon_score"
        score_rows = [
            {
                "subject_id": subject_id,
                "observed_outcome": float(outcome[index]),
                "baseline_outcome": float(baseline[index]),
                score_name: float(scores[index]),
                "source_status": source.source_status,
                "prediction_status": source.prediction_status,
            }
            for index, subject_id in enumerate(subject_ids)
        ]
        scores_path = f"{resolver}/scores.csv"
        writer.csv(
            scores_path,
            score_rows,
            tuple(score_rows[0]),
            artifact_kind="scores",
            context={**context, "stage": "resolver"},
        )
        prediction_rows = [
            {
                "fold_index": index,
                "subject_id": subject_id,
                "observed_outcome": float(outcome[index]),
                f"{score_name}_loocv": float(heldout[index]),
                "prediction_model": float(model[index]),
                "prediction_baseline": float(baseline_predictions[index]),
                "residual_model": float(outcome[index] - model[index]),
                "residual_baseline": float(outcome[index] - baseline_predictions[index]),
            }
            for index, subject_id in enumerate(subject_ids)
        ]
        predictions_path = f"{resolver}/loocv_predictions.csv"
        writer.csv(
            predictions_path,
            prediction_rows,
            tuple(prediction_rows[0]),
            artifact_kind="loocv_predictions",
            context={**context, "stage": "resolver"},
        )
        subject_order_path = f"{resolver}/subject_order.csv"
        writer.csv(
            subject_order_path,
            (
                {"fold_index": index, "subject_id": subject_id}
                for index, subject_id in enumerate(subject_ids)
            ),
            ("fold_index", "subject_id"),
            artifact_kind="subject_order",
            context={**context, "stage": "resolver"},
        )
        return scores_path, predictions_path, subject_order_path

    def _publish_direct_nifti(
        self,
        writer: _PublicationWriter,
        source: SourceRecord,
        prepared: PreparedExposureRecord,
        endpoint: object,
        scale_definition: Mapping[str, Any],
        study: Mapping[str, Any],
        resolver: str,
        base: str,
        context: Mapping[str, object],
        *,
        publish_report_display: bool = True,
    ) -> list[str]:
        try:
            import nibabel as nib
            from scipy.ndimage import gaussian_filter
        except ImportError as exc:
            raise PublicationError("direct-voxel publication requires nibabel and scipy") from exc
        artifacts = {item.kind: item for item in source.artifacts}
        selected = np.asarray(
            np.load(_artifact_path(artifacts["selected_feature_indices"]), allow_pickle=False),
            dtype=np.int64,
        )
        parent_voxel_ids = np.asarray(
            np.load(_artifact_path(prepared.feature_ids), allow_pickle=False), dtype=np.int64
        )
        voxel_ids = parent_voxel_ids[selected]
        benefit = np.asarray(
            np.load(
                _artifact_path(artifacts["benefit_oriented_feature_weights"]),
                allow_pickle=False,
            ),
            dtype=np.float32,
        )
        fold_weights = np.asarray(
            np.load(
                _artifact_path(artifacts["loocv_benefit_oriented_feature_weights"]),
                allow_pickle=False,
            ),
            dtype=np.float64,
        )
        exposure = np.load(_artifact_path(prepared.exposure), allow_pickle=False, mmap_mode="r")
        coverage_values = np.count_nonzero(
            np.asarray(exposure[:, selected]) >= float(source.selected_tau), axis=0
        ).astype(np.int16)
        direction = str(scale_definition["direction"])
        coefficient = benefit if direction == "higher" else -benefit
        stability = np.full(benefit.shape, np.nan, dtype=np.float32)
        finite_full = np.isfinite(benefit) & (benefit != 0.0)
        for index in np.flatnonzero(finite_full):
            finite = np.isfinite(fold_weights[:, index])
            if np.any(finite):
                stability[index] = np.mean(
                    np.sign(fold_weights[finite, index]) == np.sign(benefit[index])
                )

        brainmask_path = Path(
            study["study"]["spot_model_sources"]["brainmask"]["path"]
        ).resolve()
        reference_image = nib.load(str(brainmask_path))
        temporary_root = Path(tempfile.mkdtemp(prefix="dual-frequency-nifti-"))
        outputs: list[str] = []
        try:
            values = {
                "coverage.nii.gz": coverage_values,
                "coefficient.nii.gz": coefficient.astype(np.float32, copy=False),
                "benefit_map.nii.gz": benefit,
                "stability.nii.gz": stability,
            }
            for name, vector in values.items():
                fill = 0 if name == "coverage.nii.gz" else np.nan
                dtype = np.int16 if name == "coverage.nii.gz" else np.float32
                volume = np.full(reference_image.shape, fill, dtype=dtype)
                flat = volume.reshape(-1)
                finite = np.isfinite(vector) if np.issubdtype(dtype, np.floating) else np.ones(
                    vector.shape, dtype=bool
                )
                flat[voxel_ids[finite]] = vector[finite]
                image = nib.Nifti1Image(volume, reference_image.affine, reference_image.header)
                image.set_data_dtype(dtype)
                temporary = temporary_root / name
                nib.save(image, temporary)
                relative = f"{resolver}/{name}"
                writer.generated_file(
                    relative,
                    temporary,
                    artifact_kind=name.removesuffix(".nii.gz"),
                    context={**context, "stage": "resolver"},
                    provenance={
                        "source_record_id": source.identifier,
                        "brainmask_path": str(brainmask_path),
                        "brainmask_sha256": _sha256_file(brainmask_path),
                        "selected_feature_indices_sha256": artifacts[
                            "selected_feature_indices"
                        ].sha256,
                    },
                )
                outputs.append(relative)
                del image, volume, flat

            finite_positions = np.flatnonzero(np.isfinite(benefit))
            if publish_report_display and finite_positions.size:
                coordinates = np.column_stack(
                    np.unravel_index(voxel_ids[finite_positions], reference_image.shape)
                )
                lower = coordinates.min(axis=0)
                upper = coordinates.max(axis=0) + 1
                zooms = np.asarray(reference_image.header.get_zooms()[:3], dtype=float)
                for fwhm in (1.0, 2.0):
                    sigma = fwhm / 2.354820045 / zooms
                    pad = np.ceil(4.0 * sigma).astype(int)
                    crop_lower = np.maximum(lower - pad, 0)
                    crop_upper = np.minimum(upper + pad, reference_image.shape)
                    crop_shape = tuple((crop_upper - crop_lower).tolist())
                    local_values = np.zeros(crop_shape, dtype=np.float32)
                    local_mask = np.zeros(crop_shape, dtype=np.float32)
                    selected_coordinates = coordinates - crop_lower
                    local_values[tuple(selected_coordinates.T)] = benefit[finite_positions]
                    local_mask[tuple(selected_coordinates.T)] = 1.0
                    numerator = gaussian_filter(local_values, sigma=sigma, mode="constant")
                    denominator = gaussian_filter(local_mask, sigma=sigma, mode="constant")
                    local_smoothed = np.full(crop_shape, np.nan, dtype=np.float32)
                    supported = denominator > 0.0
                    local_smoothed[supported] = numerator[supported] / denominator[supported]
                    volume = np.full(reference_image.shape, np.nan, dtype=np.float32)
                    slices = tuple(
                        slice(int(crop_lower[axis]), int(crop_upper[axis]))
                        for axis in range(3)
                    )
                    volume[slices] = local_smoothed
                    image = nib.Nifti1Image(
                        volume, reference_image.affine, reference_image.header
                    )
                    image.set_data_dtype(np.float32)
                    name = f"benefit_map_smooth_fwhm{int(fwhm)}mm.nii.gz"
                    temporary = temporary_root / name
                    nib.save(image, temporary)
                    relative = f"{base}/report/display/{name}"
                    writer.generated_file(
                        relative,
                        temporary,
                        artifact_kind="benefit_map_smooth",
                        context={**context, "stage": "report"},
                        provenance={
                            "source_record_id": source.identifier,
                            "input_relative_path": f"{resolver}/benefit_map.nii.gz",
                            "fwhm_mm": fwhm,
                            "algorithm": "masked_normalized_gaussian_v1",
                        },
                    )
                    outputs.append(relative)
                    del image, volume
            if publish_report_display:
                relative = f"{base}/report/display/benefit_map_bilateral.nii.gz"
                self._publish_direct_bilateral(
                    writer,
                    relative,
                    f"{resolver}/benefit_map.nii.gz",
                    benefit,
                    voxel_ids,
                    reference_image,
                    study,
                    source,
                    context,
                    temporary_root,
                )
                outputs.append(relative)
            writer.json(
                f"{resolver}/mapping_qc.json",
                {
                    "schema_version": "direct_voxel_mapping_qc_v1",
                    "brainmask_path": str(brainmask_path),
                    "brainmask_sha256": _sha256_file(brainmask_path),
                    "nifti_shape": list(reference_image.shape),
                    "affine": np.asarray(reference_image.affine).tolist(),
                    "selected_voxel_count": int(selected.size),
                    "finite_benefit_voxel_count": int(np.isfinite(benefit).sum()),
                },
                artifact_kind="mapping_qc",
                context={**context, "stage": "resolver"},
            )
            outputs.append(f"{resolver}/mapping_qc.json")
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
        return outputs

    def _publish_direct_bilateral(
        self,
        writer: _PublicationWriter,
        relative: str,
        input_relative: str,
        benefit: np.ndarray,
        voxel_ids: np.ndarray,
        reference_image: object,
        study: Mapping[str, Any],
        source: SourceRecord,
        context: Mapping[str, object],
        temporary_root: Path,
    ) -> None:
        try:
            import nibabel as nib
            from nibabel.processing import resample_from_to
        except ImportError as exc:
            raise PublicationError("bilateral voxel publication requires nibabel") from exc
        repository_root = Path(__file__).resolve().parents[5]
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin" and machine in {"arm64", "aarch64"}:
            executable = repository_root / "ext_libs/ANTs/antsApplyTransforms.maca64"
        elif system == "darwin":
            executable = repository_root / "ext_libs/ANTs/antsApplyTransforms.maci64"
        elif system == "linux":
            executable = repository_root / "ext_libs/ANTs/antsApplyTransforms.glnxa64"
        elif system == "windows":
            executable = repository_root / "ext_libs/ANTs/antsApplyTransforms.exe"
        else:
            raise PublicationError(f"unsupported ANTs publication platform: {system}")
        if not executable.is_file():
            raise PublicationError(f"Lead-DBS ANTs executable is missing: {executable}")
        transform_path = Path(
            study["study"]["spot_model_sources"]["hemisphere_mapping"]
            ["left_to_right_transform"]["path"]
        ).resolve()
        if not transform_path.is_file():
            raise PublicationError(
                f"configured nonlinear left-right transform is missing: {transform_path}"
            )

        flipped_affine = np.asarray(reference_image.affine, dtype=float).copy()
        flipped_affine[0, :] *= -1.0
        finite = np.isfinite(benefit)
        values_volume = np.zeros(reference_image.shape, dtype=np.float32)
        values_volume.reshape(-1)[voxel_ids[finite]] = benefit[finite]
        values_input = temporary_root / "bilateral_values_input.nii.gz"
        values_image = nib.Nifti1Image(
            values_volume,
            flipped_affine,
            reference_image.header,
        )
        values_image.set_data_dtype(np.float32)
        nib.save(values_image, values_input)
        del values_volume, values_image
        mask_volume = np.zeros(reference_image.shape, dtype=np.float32)
        mask_volume.reshape(-1)[voxel_ids[finite]] = 1.0
        mask_input = temporary_root / "bilateral_mask_input.nii.gz"
        mask_image = nib.Nifti1Image(
            mask_volume,
            flipped_affine,
            reference_image.header,
        )
        mask_image.set_data_dtype(np.float32)
        nib.save(mask_image, mask_input)
        del mask_volume, mask_image

        values_warped = temporary_root / "bilateral_values_warped.nii.gz"
        mask_warped = temporary_root / "bilateral_mask_warped.nii.gz"
        transform_arg = f"[{transform_path},0]"
        for input_path, output_path in (
            (values_input, values_warped),
            (mask_input, mask_warped),
        ):
            command = (
                str(executable),
                "--dimensionality",
                "3",
                "--input-image-type",
                "0",
                "--float",
                "1",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--reference-image",
                str(input_path),
                "--transform",
                transform_arg,
                "--interpolation",
                "Linear",
                "--default-value",
                "0",
            )
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise PublicationError(
                    "configured nonlinear bilateral transform failed to execute"
                ) from exc
            if completed.returncode != 0 or not output_path.is_file():
                detail = (completed.stderr or completed.stdout).strip()
                raise PublicationError(
                    "configured nonlinear bilateral transform failed: "
                    f"{detail[-1000:]}"
                )

        target = (reference_image.shape, reference_image.affine)
        values_resampled = resample_from_to(
            nib.load(str(values_warped)), target, order=1
        )
        left = np.asarray(values_resampled.dataobj, dtype=np.float32)
        mask_resampled = resample_from_to(
            nib.load(str(mask_warped)), target, order=1
        )
        mask = np.asarray(mask_resampled.dataobj, dtype=np.float32)
        supported = np.isfinite(mask) & (mask > 1e-6)
        left[~supported] = np.nan
        left[supported] /= mask[supported]
        right = np.full(reference_image.shape, np.nan, dtype=np.float32)
        right.reshape(-1)[voxel_ids[finite]] = benefit[finite]
        right_finite = np.isfinite(right)
        left_finite = np.isfinite(left)
        overlap = right_finite & left_finite
        bilateral = left
        bilateral[right_finite & ~left_finite] = right[right_finite & ~left_finite]
        bilateral[overlap] = (right[overlap] + left[overlap]) / 2.0
        output = temporary_root / "benefit_map_bilateral.nii.gz"
        image = nib.Nifti1Image(
            bilateral,
            reference_image.affine,
            reference_image.header,
        )
        image.set_data_dtype(np.float32)
        nib.save(image, output)
        writer.generated_file(
            relative,
            output,
            artifact_kind="benefit_map_bilateral",
            context={**context, "stage": "report"},
            provenance={
                "source_record_id": source.identifier,
                "input_relative_path": input_relative,
                "transform_path": str(transform_path),
                "transform_sha256": self._cached_sha256(transform_path),
                "ants_executable": str(executable),
                "algorithm": (
                    "ea_flip_lr_header_configured_ants_masked_linear_v1"
                ),
                "right_finite_voxel_count": int(np.count_nonzero(right_finite)),
                "left_finite_voxel_count": int(np.count_nonzero(left_finite)),
                "overlap_voxel_count": int(np.count_nonzero(overlap)),
            },
        )

    def _publish_fiber(
        self,
        writer: _PublicationWriter,
        resolved: Mapping[str, Any],
        study: Mapping[str, Any],
        scale_definitions: Mapping[str, Mapping[str, Any]],
        endpoint_keys: Mapping[str, object],
        by_endpoint: Mapping[str, list[tuple[TaskOutcome, object]]],
        times: tuple[str | None, str | None],
    ) -> list[dict[str, object]]:
        profile = resolved["normative_fiber"]
        connectome_roles = {
            str(item["connectome_id"]): str(item["role"])
            for item in profile["connectomes"]
        }
        formal_connectome = next(
            key for key, role in connectome_roles.items() if role == "formal"
        )
        rows: list[dict[str, object]] = []
        for scale_id in profile["scales"]:
            selections: dict[str, FinalSelectionRecord] = {}
            for endpoint_id, key in endpoint_keys.items():
                if (
                    key.scale_id != scale_id
                    or not key.model_family.endswith("fiber")
                    or key.connectome_id != formal_connectome
                ):
                    continue
                records = by_endpoint[endpoint_id]
                selection = next(
                    (
                        record
                        for _, record in records
                        if isinstance(record, FinalSelectionRecord)
                    ),
                    None,
                )
                if selection is None:
                    raise PublicationError(
                        f"formal fiber endpoint lacks FinalSelectionRecord: {endpoint_id}"
                    )
                selections[key.model_family] = selection
                self._publish_fiber_endpoint(
                    writer,
                    selection,
                    records,
                    connectome_roles,
                    str(resolved["scientific_configuration_hash"]),
                    study,
                    times,
                )
            sensitive_statuses: list[str] = []
            for endpoint_id, key in endpoint_keys.items():
                if (
                    key.scale_id != scale_id
                    or not key.model_family.endswith("fiber")
                    or connectome_roles.get(key.connectome_id) != "sensitive"
                ):
                    continue
                records = by_endpoint[endpoint_id]
                sensitive = next(
                    (
                        record
                        for _, record in records
                        if isinstance(record, SensitiveRecord)
                    ),
                    None,
                )
                if sensitive is None:
                    raise PublicationError(
                        f"sensitive fiber endpoint lacks SensitiveRecord: {endpoint_id}"
                    )
                self._publish_sensitive_observed_grids(records, writer, times)
                self._publish_sensitive_fiber_evaluation(
                    writer,
                    sensitive,
                    records,
                    selections[key.model_family],
                    times,
                )
                sensitive_statuses.append(sensitive.cell_computability_status)
            reference = selections["reference_fiber"]
            addon = selections["addon_fiber"]
            reference_source = _source_from_selection(reference)
            addon_source = _source_from_selection(addon)
            addon_branch = addon.final_model.selected_branch.branch
            rows.append(
                {
                    "scale_id": scale_id,
                    "scale_direction": scale_definitions[scale_id]["direction"],
                    "formal_connectome_id": formal_connectome,
                    "reference_input_status": reference_source.input_status,
                    "reference_source_status": reference_source.source_status,
                    "reference_prediction_status": reference_source.prediction_status,
                    "reference_final_status": reference.selection_status,
                    "addon_intended_primary_branch": "delta_reference_adjusted",
                    "addon_final_branch": addon_branch,
                    "addon_final_role": addon.final_model.realization_role,
                    "addon_final_status": addon.selection_status,
                    "sensitive_connectome_status": (
                        "completed"
                        if len(sensitive_statuses)
                        == 2 * sum(role == "sensitive" for role in connectome_roles.values())
                        else "incomplete"
                    ),
                    "overall_status": "completed",
                    "failure_reason": "",
                }
            )
        return rows

    def _publish_fiber_endpoint(
        self,
        writer: _PublicationWriter,
        selection: FinalSelectionRecord,
        records: list[tuple[TaskOutcome, object]],
        connectome_roles: Mapping[str, str],
        scientific_configuration_hash: str,
        study: Mapping[str, Any],
        times: tuple[str | None, str | None],
    ) -> None:
        endpoint = selection.endpoint
        role = "reference" if endpoint.model_family.startswith("reference_") else "addon"
        branch = "reference"
        if selection.final_model.selected_branch is not None:
            branch = selection.final_model.selected_branch.branch
        base = f"{endpoint.scale_id}/{role}"
        connectome_base = (
            f"{base}/connectomes/{endpoint.connectome_id}"
            if role == "reference"
            else f"{base}/branches/{branch}/connectomes/{endpoint.connectome_id}"
        )
        observed = f"{connectome_base}/observed"
        resolver = f"{connectome_base}/resolver"
        context = {
            "scale_id": endpoint.scale_id,
            "model_family": role,
            "branch_id": None if role == "reference" else branch,
            "connectome_id": endpoint.connectome_id,
            "connectome_role": connectome_roles[endpoint.connectome_id],
        }
        source = _source_from_selection(selection)
        artifacts = {item.kind: item for item in source.artifacts}
        if role == "addon":
            endpoint_input = next(
                record for _, record in records if isinstance(record, EndpointInputRecord)
            )
            for branch_record in (
                record for _, record in records if isinstance(record, BranchRecord)
            ):
                if branch_record.branch == branch or branch_record.source is None:
                    continue
                self._publish_fiber_nonfinal_branch(
                    writer,
                    branch_record,
                    endpoint_input,
                    connectome_roles[endpoint.connectome_id],
                    times,
                )
        grid = self._json(_artifact_path(artifacts["normative_fiber_grid_metrics"]))
        cells = list(grid["cells"])
        scan_fields = tuple(sorted({key for row in cells for key in row}))
        writer.csv(
            f"{observed}/source_scan.csv",
            cells,
            scan_fields,
            artifact_kind="source_scan",
            context={**context, "stage": "observed"},
        )
        writer.json(
            f"{observed}/status.json",
            _stage_status(
                domain="normative_fiber",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="observed",
                status="completed",
                reason="completed",
                started=times[0],
                finished=times[1],
                artifacts=[f"{observed}/source_scan.csv"],
                connectome_role=connectome_roles[endpoint.connectome_id],
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "observed"},
        )
        mapping = {
            "normative_fiber_candidate_ids": "candidate_fiber_ids.npy",
            "normative_fiber_valid_union_ids": "valid_fiber_ids.npy",
            "benefit_oriented_fiber_weights": "full_weights.npy",
            "loocv_benefit_oriented_fiber_weights": "fold_weights.npy",
            "loocv_valid_fiber_masks": "fold_valid_masks.npy",
            "normative_fiber_sweet_selected_ids": "selected_sweet_fiber_ids.npy",
            "normative_fiber_sour_selected_ids": "selected_sour_fiber_ids.npy",
        }
        resolver_paths: list[str] = []
        for kind, name in mapping.items():
            artifact = artifacts.get(kind)
            if artifact is None:
                continue
            relative = f"{resolver}/{name}"
            writer.artifact(
                relative,
                artifact,
                artifact_kind=kind,
                context={**context, "stage": "resolver"},
            )
            resolver_paths.append(relative)
        endpoint_input = next(
            record for _, record in records if isinstance(record, EndpointInputRecord)
        )
        score_paths = self._publish_score_tables(
            writer, source, endpoint_input, resolver, context
        )
        resolver_paths.extend(score_paths)
        resolver_paths.append(
            self._publish_fiber_score_support(
                writer,
                artifacts["normative_fiber_score_support"],
                resolver,
                context,
            )
        )
        source_selection_path = f"{resolver}/source_selection.json"
        writer.json(
            source_selection_path,
            {
                "schema_version": "normative_fiber_source_selection_v1",
                "source_status": source.source_status,
                "prediction_status": source.prediction_status,
                "threshold_source": source.threshold_source,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "selected_adjacent_passing_cells": source.adjacent_support,
                "selected_grid_distance": None,
                "final_valid_feature_axis_relative_path": f"{resolver}/valid_fiber_ids.npy",
                "artifact_relative_paths": sorted(resolver_paths),
            },
            artifact_kind="source_selection",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(source_selection_path)
        writer.json(
            f"{resolver}/status.json",
            _stage_status(
                domain="normative_fiber",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="resolver",
                status="completed",
                reason="completed",
                started=times[0],
                finished=times[1],
                artifacts=resolver_paths,
                connectome_role=connectome_roles[endpoint.connectome_id],
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "resolver"},
        )
        report_paths = self._publish_fiber_density(
            writer,
            source,
            endpoint.connectome_id,
            study,
            base,
            context,
        )
        report_summary_path = f"{base}/report/summary.json"
        writer.json(
            report_summary_path,
            {
                "schema_version": "normative_fiber_report_summary_v1",
                "scale_id": endpoint.scale_id,
                "model_family": role,
                "final_model_id": selection.final_model.identifier,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "display_artifact_relative_paths": sorted(report_paths),
                "density_scope": "selected_signed_fiber_libraries",
                "display_only": True,
            },
            artifact_kind="report_summary",
            context={**context, "stage": "report"},
        )
        report_paths.append(report_summary_path)
        writer.json(
            f"{base}/report/status.json",
            _stage_status(
                domain="normative_fiber",
                endpoint=endpoint,
                branch=None if role == "reference" else branch,
                stage="report",
                status="completed",
                reason="display_derivatives_completed",
                started=times[0],
                finished=times[1],
                artifacts=report_paths,
                connectome_role=connectome_roles[endpoint.connectome_id],
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "report"},
        )
        final_document = {
            "schema_version": "normative_fiber_final_model_v1",
            "scale_id": endpoint.scale_id,
            "model_family": role,
            "formal_connectome_id": endpoint.connectome_id,
            "final_branch": branch,
            "final_role": selection.final_model.realization_role,
            "final_status": selection.selection_status,
            "source_status": source.source_status,
            "prediction_status": source.prediction_status,
            "selected_tau_v_per_m": source.selected_tau,
            "selected_coverage_subjects_min": source.selected_coverage,
            "resolver_relative_path": source_selection_path,
            "valid_feature_axis_relative_path": f"{resolver}/valid_fiber_ids.npy",
            "scientific_config_sha256": scientific_configuration_hash,
            "final_record_sha256": selection.final_model.identifier,
        }
        writer.json(
            f"{base}/final_model.json",
            final_document,
            artifact_kind="final_model",
            context={**context, "stage": "final"},
        )
        self._publish_formal(
            writer,
            selection,
            records,
            base,
            context,
            domain="normative_fiber",
            direct_nifti=None,
            times=times,
        )
        self._publish_sensitivity_base(writer, selection, base, context)

    def _publish_fiber_nonfinal_branch(
        self,
        writer: _PublicationWriter,
        branch_record: BranchRecord,
        endpoint_input: EndpointInputRecord,
        connectome_role: str,
        times: tuple[str | None, str | None],
    ) -> None:
        source = branch_record.source
        if source is None:
            return
        endpoint = branch_record.endpoint
        base = f"{endpoint.scale_id}/addon/branches/{branch_record.branch}"
        connectome_base = f"{base}/connectomes/{endpoint.connectome_id}"
        observed = f"{connectome_base}/observed"
        resolver = f"{connectome_base}/resolver"
        context = {
            "scale_id": endpoint.scale_id,
            "model_family": "addon",
            "branch_id": branch_record.branch,
            "connectome_id": endpoint.connectome_id,
            "connectome_role": connectome_role,
        }
        artifacts = {item.kind: item for item in source.artifacts}
        grid = self._json(_artifact_path(artifacts["normative_fiber_grid_metrics"]))
        cells = list(grid["cells"])
        scan_fields = tuple(sorted({key for row in cells for key in row}))
        scan_path = f"{observed}/source_scan.csv"
        writer.csv(
            scan_path,
            cells,
            scan_fields,
            artifact_kind="source_scan",
            context={**context, "stage": "observed"},
        )
        writer.json(
            f"{observed}/status.json",
            _stage_status(
                domain="normative_fiber",
                endpoint=endpoint,
                branch=branch_record.branch,
                stage="observed",
                status="completed",
                reason="completed_nonfinal_branch",
                started=times[0],
                finished=times[1],
                artifacts=[scan_path],
                connectome_role=connectome_role,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "observed"},
        )
        resolver_paths: list[str] = []
        for kind, name in (
            ("normative_fiber_candidate_ids", "candidate_fiber_ids.npy"),
            ("normative_fiber_valid_union_ids", "valid_fiber_ids.npy"),
            ("benefit_oriented_fiber_weights", "full_weights.npy"),
            ("loocv_benefit_oriented_fiber_weights", "fold_weights.npy"),
            ("loocv_valid_fiber_masks", "fold_valid_masks.npy"),
            ("normative_fiber_sweet_selected_ids", "selected_sweet_fiber_ids.npy"),
            ("normative_fiber_sour_selected_ids", "selected_sour_fiber_ids.npy"),
        ):
            artifact = artifacts.get(kind)
            if artifact is None:
                continue
            relative = f"{resolver}/{name}"
            writer.artifact(
                relative,
                artifact,
                artifact_kind=kind,
                context={**context, "stage": "resolver"},
            )
            resolver_paths.append(relative)
        resolver_paths.extend(
            self._publish_score_tables(
                writer,
                source,
                endpoint_input,
                resolver,
                context,
            )
        )
        resolver_paths.append(
            self._publish_fiber_score_support(
                writer,
                artifacts["normative_fiber_score_support"],
                resolver,
                context,
            )
        )
        source_selection_path = f"{resolver}/source_selection.json"
        writer.json(
            source_selection_path,
            {
                "schema_version": "normative_fiber_source_selection_v1",
                "source_status": source.source_status,
                "prediction_status": source.prediction_status,
                "threshold_source": source.threshold_source,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "selected_adjacent_passing_cells": source.adjacent_support,
                "selected_grid_distance": None,
                "final_valid_feature_axis_relative_path": (
                    f"{resolver}/valid_fiber_ids.npy"
                ),
                "final_branch_selected": False,
                "artifact_relative_paths": sorted(resolver_paths),
            },
            artifact_kind="source_selection",
            context={**context, "stage": "resolver"},
        )
        resolver_paths.append(source_selection_path)
        writer.json(
            f"{resolver}/status.json",
            _stage_status(
                domain="normative_fiber",
                endpoint=endpoint,
                branch=branch_record.branch,
                stage="resolver",
                status="completed",
                reason="completed_nonfinal_branch",
                started=times[0],
                finished=times[1],
                artifacts=resolver_paths,
                connectome_role=connectome_role,
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "resolver"},
        )

    def _publish_fiber_score_support(
        self,
        writer: _PublicationWriter,
        artifact: ArtifactRef,
        resolver: str,
        context: Mapping[str, object],
    ) -> str:
        support = self._json(_artifact_path(artifact))
        rows = [
            {"scope": "full_sample", "heldout_index": "", **support["full_sample"]},
            *({"scope": "loocv_fold", **row} for row in support["folds"]),
        ]
        fields = tuple(sorted({key for row in rows for key in row}))
        relative = f"{resolver}/fiber_score_support.csv"
        writer.csv(
            relative,
            rows,
            fields,
            artifact_kind="normative_fiber_score_support",
            context={**context, "stage": "resolver"},
        )
        return relative

    def _publish_sensitive_observed_grids(
        self,
        records: list[tuple[TaskOutcome, object]],
        writer: _PublicationWriter,
        times: tuple[str | None, str | None],
    ) -> None:
        candidates: list[tuple[object, str, ArtifactRef]] = []
        for _, record in records:
            if isinstance(record, ObservedResult):
                grid = next(
                    (
                        artifact
                        for artifact in record.artifacts
                        if artifact.kind == "normative_fiber_grid_metrics"
                    ),
                    None,
                )
                if grid is not None:
                    endpoint = next(
                        item.endpoint
                        for _, item in records
                        if isinstance(item, SensitiveRecord)
                    )
                    candidates.append((endpoint, "reference", grid))
            elif isinstance(record, BranchRecord):
                grid = next(
                    (
                        artifact
                        for artifact in record.artifacts
                        if artifact.kind == "normative_fiber_grid_metrics"
                    ),
                    None,
                )
                if grid is not None:
                    candidates.append((record.endpoint, record.branch, grid))
        if not candidates:
            raise PublicationError("sensitive fiber endpoint lacks observed grid evidence")
        for endpoint, branch, artifact in candidates:
            role = (
                "reference"
                if endpoint.model_family.startswith("reference_")
                else "addon"
            )
            if role == "reference":
                observed = (
                    f"{endpoint.scale_id}/reference/connectomes/"
                    f"{endpoint.connectome_id}/observed"
                )
                branch_id: str | None = None
            else:
                observed = (
                    f"{endpoint.scale_id}/addon/branches/{branch}/connectomes/"
                    f"{endpoint.connectome_id}/observed"
                )
                branch_id = branch
            context = {
                "scale_id": endpoint.scale_id,
                "model_family": role,
                "branch_id": branch_id,
                "connectome_id": endpoint.connectome_id,
                "connectome_role": "sensitive",
            }
            grid = self._json(_artifact_path(artifact))
            cells = list(grid["cells"])
            fields = tuple(sorted({key for row in cells for key in row}))
            scan_path = f"{observed}/source_scan.csv"
            writer.csv(
                scan_path,
                cells,
                fields,
                artifact_kind="source_scan",
                context={**context, "stage": "observed"},
            )
            writer.json(
                f"{observed}/status.json",
                _stage_status(
                    domain="normative_fiber",
                    endpoint=endpoint,
                    branch=branch_id,
                    stage="observed",
                    status="completed",
                    reason="completed_sensitive_grid",
                    started=times[0],
                    finished=times[1],
                    artifacts=[scan_path],
                    connectome_role="sensitive",
                ),
                artifact_kind="stage_status",
                context={**context, "stage": "observed"},
            )

    def _publish_sensitive_fiber_evaluation(
        self,
        writer: _PublicationWriter,
        sensitive: SensitiveRecord,
        records: list[tuple[TaskOutcome, object]],
        formal_selection: FinalSelectionRecord,
        times: tuple[str | None, str | None],
    ) -> None:
        endpoint = sensitive.endpoint
        role = "reference" if endpoint.model_family.startswith("reference_") else "addon"
        branch = "reference"
        if formal_selection.final_model.selected_branch is not None:
            branch = formal_selection.final_model.selected_branch.branch
        base = f"{endpoint.scale_id}/{role}"
        if role == "reference":
            evaluation = (
                f"{base}/connectomes/{endpoint.connectome_id}/formal_source_evaluation"
            )
        else:
            evaluation = (
                f"{base}/branches/{branch}/connectomes/{endpoint.connectome_id}"
                "/formal_source_evaluation"
            )
        context = {
            "scale_id": endpoint.scale_id,
            "model_family": role,
            "branch_id": None if role == "reference" else branch,
            "connectome_id": endpoint.connectome_id,
            "connectome_role": "sensitive",
        }
        artifacts = {item.kind: item for item in sensitive.artifacts}
        evidence = artifacts.get("normative_fiber_sensitive_cell_evidence")
        if evidence is None:
            evidence = artifacts.get("normative_fiber_sensitive_cell_status")
        if evidence is None:
            raise PublicationError("sensitive fiber evidence lacks its cell document")
        paths: list[str] = []
        relative = f"{evaluation}/formal_source_cell.json"
        writer.artifact(
            relative,
            evidence,
            artifact_kind=evidence.kind,
            context={**context, "stage": "formal_source_evaluation"},
        )
        paths.append(relative)

        if sensitive.cell_computability_status == "computable":
            mapping = {
                "normative_fiber_candidate_ids": "candidate_fiber_ids.npy",
                "normative_fiber_valid_union_ids": "valid_fiber_ids.npy",
                "benefit_oriented_fiber_weights": "full_weights.npy",
                "loocv_benefit_oriented_fiber_weights": "fold_weights.npy",
                "loocv_valid_fiber_masks": "fold_valid_masks.npy",
            }
            for kind, name in mapping.items():
                artifact = artifacts.get(kind)
                if artifact is None:
                    raise PublicationError(
                        f"computable sensitive fiber evidence lacks {kind}"
                    )
                relative = f"{evaluation}/{name}"
                writer.artifact(
                    relative,
                    artifact,
                    artifact_kind=kind,
                    context={**context, "stage": "formal_source_evaluation"},
                )
                paths.append(relative)

            endpoint_input = next(
                record for _, record in records if isinstance(record, EndpointInputRecord)
            )
            score_name = "reference_score" if role == "reference" else "addon_score"
            full_scores = np.asarray(
                np.load(
                    _artifact_path(artifacts["normative_fiber_full_scores"]),
                    allow_pickle=False,
                ),
                dtype=np.float64,
            )
            heldout_scores = np.asarray(
                np.load(
                    _artifact_path(artifacts["normative_fiber_loocv_heldout_scores"]),
                    allow_pickle=False,
                ),
                dtype=np.float64,
            )
            predictions = np.asarray(
                np.load(
                    _artifact_path(artifacts["normative_fiber_loocv_model_predictions"]),
                    allow_pickle=False,
                ),
                dtype=np.float64,
            )
            baseline_predictions = np.asarray(
                np.load(
                    _artifact_path(artifacts["normative_fiber_loocv_baseline_predictions"]),
                    allow_pickle=False,
                ),
                dtype=np.float64,
            )
            outcome = np.asarray(
                np.load(_artifact_path(endpoint_input.outcome), allow_pickle=False),
                dtype=np.float64,
            )
            baseline = np.asarray(
                np.load(_artifact_path(endpoint_input.baseline), allow_pickle=False),
                dtype=np.float64,
            )
            subject_ids = endpoint_input.included_subject_ids
            expected = (len(subject_ids),)
            if any(
                values.shape != expected
                for values in (
                    full_scores,
                    heldout_scores,
                    predictions,
                    baseline_predictions,
                    outcome,
                    baseline,
                )
            ):
                raise PublicationError("sensitive fiber score arrays do not share subject axis")
            score_rows = [
                {
                    "subject_id": subject_id,
                    "observed_outcome": float(outcome[index]),
                    "baseline_outcome": float(baseline[index]),
                    score_name: float(full_scores[index]),
                    "input_status": sensitive.input_status,
                    "cell_computability_status": sensitive.cell_computability_status,
                    "prediction_status": sensitive.prediction_status,
                }
                for index, subject_id in enumerate(subject_ids)
            ]
            relative = f"{evaluation}/scores.csv"
            writer.csv(
                relative,
                score_rows,
                tuple(score_rows[0]),
                artifact_kind="sensitive_scores",
                context={**context, "stage": "formal_source_evaluation"},
            )
            paths.append(relative)
            prediction_rows = [
                {
                    "fold_index": index,
                    "subject_id": subject_id,
                    "observed_outcome": float(outcome[index]),
                    f"{score_name}_loocv": float(heldout_scores[index]),
                    "prediction_model": float(predictions[index]),
                    "prediction_baseline": float(baseline_predictions[index]),
                    "residual_model": float(outcome[index] - predictions[index]),
                    "residual_baseline": float(
                        outcome[index] - baseline_predictions[index]
                    ),
                }
                for index, subject_id in enumerate(subject_ids)
            ]
            relative = f"{evaluation}/loocv_predictions.csv"
            writer.csv(
                relative,
                prediction_rows,
                tuple(prediction_rows[0]),
                artifact_kind="sensitive_loocv_predictions",
                context={**context, "stage": "formal_source_evaluation"},
            )
            paths.append(relative)
            support = self._json(
                _artifact_path(artifacts["normative_fiber_score_support"])
            )
            support_rows = [
                {"scope": "full_sample", "heldout_index": "", **support["full_sample"]},
                *(
                    {"scope": "loocv_fold", **row}
                    for row in support["folds"]
                ),
            ]
            support_fields = tuple(
                sorted({key for row in support_rows for key in row})
            )
            relative = f"{evaluation}/fiber_score_support.csv"
            writer.csv(
                relative,
                support_rows,
                support_fields,
                artifact_kind="sensitive_fiber_score_support",
                context={**context, "stage": "formal_source_evaluation"},
            )
            paths.append(relative)

        status = _stage_status(
            domain="normative_fiber",
            endpoint=endpoint,
            branch=None if role == "reference" else branch,
            stage="formal_source_evaluation",
            status="completed",
            reason=sensitive.cell_computability_status,
            started=times[0],
            finished=times[1],
            artifacts=paths,
            connectome_role="sensitive",
        )
        status.update(
            {
                "formal_endpoint_id": sensitive.formal_endpoint_id,
                "evaluated_tau_v_per_m": sensitive.evaluated_tau,
                "evaluated_coverage_subjects_min": sensitive.evaluated_coverage,
                "input_status": sensitive.input_status,
                "cell_computability_status": sensitive.cell_computability_status,
                "prediction_status": sensitive.prediction_status,
            }
        )
        writer.json(
            f"{evaluation}/status.json",
            status,
            artifact_kind="stage_status",
            context={**context, "stage": "formal_source_evaluation"},
        )

    def _publish_fiber_density(
        self,
        writer: _PublicationWriter,
        source: SourceRecord,
        connectome_id: str,
        study: Mapping[str, Any],
        base: str,
        context: Mapping[str, object],
    ) -> list[str]:
        try:
            import h5py
            import nibabel as nib
        except ImportError as exc:
            raise PublicationError(
                "normative-fiber publication requires h5py and nibabel"
            ) from exc

        artifacts = {item.kind: item for item in source.artifacts}
        required = (
            "normative_fiber_valid_union_ids",
            "benefit_oriented_fiber_weights",
            "normative_fiber_sweet_selected_ids",
            "normative_fiber_sour_selected_ids",
        )
        missing = [kind for kind in required if kind not in artifacts]
        if missing:
            raise PublicationError(
                f"normative-fiber report lacks selected density inputs: {missing}"
            )
        valid_ids = np.asarray(
            np.load(
                _artifact_path(artifacts["normative_fiber_valid_union_ids"]),
                allow_pickle=False,
            ),
            dtype=np.int64,
        ).reshape(-1)
        weights = np.asarray(
            np.load(
                _artifact_path(artifacts["benefit_oriented_fiber_weights"]),
                allow_pickle=False,
            ),
            dtype=np.float64,
        ).reshape(-1)
        sweet_ids = np.asarray(
            np.load(
                _artifact_path(artifacts["normative_fiber_sweet_selected_ids"]),
                allow_pickle=False,
            ),
            dtype=np.int64,
        ).reshape(-1)
        sour_ids = np.asarray(
            np.load(
                _artifact_path(artifacts["normative_fiber_sour_selected_ids"]),
                allow_pickle=False,
            ),
            dtype=np.int64,
        ).reshape(-1)
        if valid_ids.shape != weights.shape or valid_ids.size < 1:
            raise PublicationError("published fiber IDs and weights have mismatched axes")
        if np.any(np.diff(valid_ids) <= 0):
            raise PublicationError("published valid fiber IDs must be ordered and unique")
        if np.intersect1d(sweet_ids, sour_ids).size:
            raise PublicationError("published sweet and sour fiber IDs overlap")
        display_ids = np.unique(np.concatenate((sweet_ids, sour_ids))).astype(np.int64)
        if display_ids.size < 1:
            raise PublicationError("normative-fiber report has no selected display fibers")
        positions = np.searchsorted(valid_ids, display_ids)
        if np.any(positions >= valid_ids.size) or not np.array_equal(
            valid_ids[positions], display_ids
        ):
            raise PublicationError("selected display fiber lies outside the valid axis")
        display_weights = weights[positions]
        if not np.all(np.isfinite(display_weights)):
            raise PublicationError("selected display fiber has a non-finite weight")
        sweet_positions = np.searchsorted(display_ids, sweet_ids)
        sour_positions = np.searchsorted(display_ids, sour_ids)
        if sweet_ids.size and np.any(display_weights[sweet_positions] <= 0.0):
            raise PublicationError("selected sweet fiber does not have positive weight")
        if sour_ids.size and np.any(display_weights[sour_positions] >= 0.0):
            raise PublicationError("selected sour fiber does not have negative weight")

        connectomes = study["study"]["spot_model_sources"]["connectomes"]
        matches = [
            item for item in connectomes if str(item["connectome_id"]) == connectome_id
        ]
        if len(matches) != 1:
            raise PublicationError(
                f"expected one study connectome for density projection: {connectome_id}"
            )
        connectome_entry = matches[0]["streamlines"]
        connectome_path = Path(str(connectome_entry["path"])).expanduser().resolve()
        if not connectome_path.is_file():
            raise PublicationError(f"connectome geometry is missing: {connectome_path}")
        brainmask_entry = study["study"]["spot_model_sources"]["brainmask"]
        brainmask_path = Path(str(brainmask_entry["path"])).expanduser().resolve()
        reference_image = nib.load(str(brainmask_path))
        shape = tuple(int(item) for item in reference_image.shape)
        cache_key = (str(connectome_path), _sha256_file(brainmask_path))
        geometry = self._fiber_voxel_cache.setdefault(cache_key, {})
        missing_ids = [int(item) for item in display_ids if int(item) not in geometry]
        if missing_ids:
            cache_path = str(connectome_path)
            indexed = self._fiber_offset_cache.get(cache_path)
            if indexed is None:
                try:
                    with h5py.File(connectome_path, "r") as handle:
                        if "fibers" not in handle or "idx" not in handle:
                            raise PublicationError("connectome lacks fibers or idx")
                        raw_lengths = np.asarray(handle["idx"][...], dtype=np.float64).reshape(-1)
                        lengths = np.rint(raw_lengths).astype(np.int64)
                        fibers = handle["fibers"]
                        if fibers.ndim != 2:
                            raise PublicationError("connectome fibers must be two-dimensional")
                        if fibers.shape[0] in {4, 5}:
                            row_major = True
                            total_points = int(fibers.shape[1])
                        elif fibers.shape[1] in {4, 5}:
                            row_major = False
                            total_points = int(fibers.shape[0])
                        else:
                            raise PublicationError(
                                "connectome fibers lack coordinate rows"
                            )
                    if (
                        raw_lengths.size < 1
                        or not np.all(np.isfinite(raw_lengths))
                        or not np.array_equal(raw_lengths, lengths.astype(np.float64))
                        or np.any(lengths < 2)
                        or int(np.sum(lengths, dtype=np.int64)) != total_points
                    ):
                        raise PublicationError("connectome idx is structurally invalid")
                    offsets = np.empty(lengths.size + 1, dtype=np.int64)
                    offsets[0] = 0
                    np.cumsum(lengths, dtype=np.int64, out=offsets[1:])
                    indexed = (lengths, offsets, row_major)
                    self._fiber_offset_cache[cache_path] = indexed
                except OSError as exc:
                    raise PublicationError(
                        f"cannot read connectome geometry: {connectome_path}"
                    ) from exc
            lengths, offsets, row_major = indexed
            missing_array = np.asarray(missing_ids, dtype=np.int64)
            if np.any(missing_array < 1) or np.any(missing_array > lengths.size):
                raise PublicationError("selected fiber ID lies outside the connectome")
            inverse = np.linalg.inv(reference_image.affine)
            voxel_sizes = nib.affines.voxel_sizes(reference_image.affine)
            sample_step = max(float(np.min(voxel_sizes)) * 0.5, 0.1)
            try:
                with h5py.File(connectome_path, "r") as handle:
                    fibers = handle["fibers"]
                    for fiber_id in missing_ids:
                        start = int(offsets[fiber_id - 1])
                        stop = int(offsets[fiber_id])
                        if row_major:
                            streamline = np.asarray(
                                fibers[:3, start:stop], dtype=np.float32
                            ).T
                        else:
                            streamline = np.asarray(
                                fibers[start:stop, :3], dtype=np.float32
                            )
                        sampled_parts: list[np.ndarray] = [streamline[:1]]
                        for start_point, end_point in zip(
                            streamline[:-1], streamline[1:], strict=True
                        ):
                            length = float(np.linalg.norm(end_point - start_point))
                            steps = max(1, int(np.ceil(length / sample_step)))
                            fractions = np.linspace(
                                0.0, 1.0, steps + 1, endpoint=True
                            )[1:]
                            sampled_parts.append(
                                start_point[None, :]
                                + fractions[:, None]
                                * (end_point - start_point)[None, :]
                            )
                        points = np.concatenate(sampled_parts, axis=0)
                        voxels = np.rint(
                            nib.affines.apply_affine(inverse, points)
                        ).astype(np.int64)
                        inside = np.all(
                            (voxels >= 0) & (voxels < np.asarray(shape)), axis=1
                        )
                        if np.any(inside):
                            flat = np.ravel_multi_index(
                                np.unique(voxels[inside], axis=0).T, shape
                            ).astype(np.int64)
                        else:
                            flat = np.empty(0, dtype=np.int64)
                        geometry[fiber_id] = flat
            except OSError as exc:
                raise PublicationError(
                    f"cannot read connectome geometry: {connectome_path}"
                ) from exc

        voxel_count = int(np.prod(shape))
        support_chunks = [geometry[int(item)] for item in display_ids]
        support = (
            np.unique(np.concatenate(support_chunks))
            if any(chunk.size for chunk in support_chunks)
            else np.empty(0, dtype=np.int64)
        )
        if support.size < 1:
            raise PublicationError("selected fibers do not intersect the reference grid")
        signed = np.full(voxel_count, np.nan, dtype=np.float32)
        positive = np.full(voxel_count, np.nan, dtype=np.float32)
        negative = np.full(voxel_count, np.nan, dtype=np.float32)
        signed[support] = 0.0
        positive[support] = 0.0
        negative[support] = 0.0
        for fiber_id, weight in zip(
            display_ids.tolist(), display_weights.tolist(), strict=True
        ):
            flat = geometry[int(fiber_id)]
            signed[flat] += float(weight)
            if weight > 0.0:
                positive[flat] += float(weight)
            elif weight < 0.0:
                negative[flat] += float(weight)

        temporary_root = Path(tempfile.mkdtemp(prefix="dual-frequency-fiber-density-"))
        outputs: list[str] = []
        provenance = {
            "source_record_id": source.identifier,
            "connectome_id": connectome_id,
            "connectome_path": str(connectome_path),
            "connectome_sha256": str(connectome_entry.get("sha256", "")),
            "brainmask_sha256": cache_key[1],
            "sweet_selected_ids_sha256": artifacts[
                "normative_fiber_sweet_selected_ids"
            ].sha256,
            "sour_selected_ids_sha256": artifacts[
                "normative_fiber_sour_selected_ids"
            ].sha256,
            "full_weights_sha256": artifacts[
                "benefit_oriented_fiber_weights"
            ].sha256,
            "density_scope": "selected_signed_fiber_libraries",
            "density_algorithm": "signed_weight_once_per_fiber_per_voxel_v1",
            "selected_fiber_count": int(display_ids.size),
            "support_voxel_count": int(support.size),
        }
        try:
            for name, values, kind in (
                (
                    "unthresholded_weighted_density.nii.gz",
                    signed,
                    "unthresholded_weighted_density",
                ),
                (
                    "positive_weighted_density.nii.gz",
                    positive,
                    "positive_weighted_density",
                ),
                (
                    "negative_weighted_density.nii.gz",
                    negative,
                    "negative_weighted_density",
                ),
            ):
                image = nib.Nifti1Image(
                    values.reshape(shape),
                    reference_image.affine,
                    reference_image.header,
                )
                image.set_data_dtype(np.float32)
                temporary = temporary_root / name
                nib.save(image, temporary)
                relative = f"{base}/report/{name}"
                writer.generated_file(
                    relative,
                    temporary,
                    artifact_kind=kind,
                    context={**context, "stage": "report"},
                    provenance=provenance,
                )
                outputs.append(relative)
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
        return outputs

    def _publish_formal(
        self,
        writer: _PublicationWriter,
        selection: FinalSelectionRecord,
        records: list[tuple[TaskOutcome, object]],
        base: str,
        context: Mapping[str, object],
        *,
        domain: str,
        direct_nifti: tuple[PreparedExposureRecord, object, Mapping[str, Any]] | None,
        times: tuple[str | None, str | None],
    ) -> None:
        formal_records = [
            record
            for _, record in records
            if isinstance(record, FormalResult)
            and record.final_model_id == selection.final_model.identifier
        ]
        if not formal_records:
            return
        formal_base = f"{base}/formal"
        paths: list[str] = []
        for record in formal_records:
            artifacts = {item.kind: item for item in record.artifacts}
            if record.resampling_kind == "permutation":
                null = artifacts["formal_permutation_null_statistics"]
                relative = (
                    f"{formal_base}/permutation_null_statistics.npy"
                    if domain == "direct_voxel"
                    else f"{formal_base}/permutation_null.npy"
                )
                writer.artifact(
                    relative,
                    null,
                    artifact_kind=null.kind,
                    context={**context, "stage": "formal"},
                )
                paths.append(relative)
                summary_artifact = artifacts["formal_permutation_summary"]
                summary = self._json(_artifact_path(summary_artifact))
                relative = f"{formal_base}/permutation_summary.csv"
                writer.csv(
                    relative,
                    [summary],
                    tuple(summary),
                    artifact_kind="formal_permutation_summary",
                    context={**context, "stage": "formal"},
                )
                paths.append(relative)
            elif record.resampling_kind == "bootstrap":
                summary_artifact = artifacts["formal_bootstrap_summary"]
                summary = self._json(_artifact_path(summary_artifact))
                relative = f"{formal_base}/bootstrap_summary.csv"
                writer.csv(
                    relative,
                    [summary],
                    tuple(summary),
                    artifact_kind="formal_bootstrap_summary",
                    context={**context, "stage": "formal"},
                )
                paths.append(relative)
                if domain == "normative_fiber":
                    for kind, name in (
                        (
                            "formal_bootstrap_candidate_selection_frequency",
                            "bootstrap_selection_frequency.npy",
                        ),
                        ("formal_bootstrap_positive_sign_frequency", "bootstrap_sign_stability.npy"),
                    ):
                        artifact = artifacts[kind]
                        relative = f"{formal_base}/{name}"
                        writer.artifact(
                            relative,
                            artifact,
                            artifact_kind=kind,
                            context={**context, "stage": "formal"},
                        )
                        paths.append(relative)
                elif direct_nifti is not None:
                    se = artifacts["formal_bootstrap_weight_se"]
                    prepared, endpoint, study = direct_nifti
                    relative = f"{formal_base}/bootstrap_standard_error.nii.gz"
                    self._publish_direct_formal_nifti(
                        writer,
                        relative,
                        se,
                        _source_from_selection(selection),
                        prepared,
                        study,
                        context,
                    )
                    paths.append(relative)
        writer.json(
            f"{formal_base}/status.json",
            _stage_status(
                domain=domain,
                endpoint=selection.endpoint,
                branch=(
                    None
                    if selection.endpoint.model_family.startswith("reference_")
                    else selection.final_model.selected_branch.branch
                ),
                stage="formal",
                status="completed",
                reason="completed",
                started=times[0],
                finished=times[1],
                artifacts=paths,
                connectome_role=(
                    None if domain == "direct_voxel" else "formal"
                ),
            ),
            artifact_kind="stage_status",
            context={**context, "stage": "formal"},
        )

    @staticmethod
    def _publish_direct_formal_nifti(
        writer: _PublicationWriter,
        relative: str,
        artifact: ArtifactRef,
        source: SourceRecord,
        prepared: PreparedExposureRecord,
        study: Mapping[str, Any],
        context: Mapping[str, object],
    ) -> None:
        try:
            import nibabel as nib
        except ImportError as exc:
            raise PublicationError("direct-voxel publication requires nibabel") from exc
        source_artifacts = {item.kind: item for item in source.artifacts}
        selected = np.asarray(
            np.load(
                _artifact_path(source_artifacts["selected_feature_indices"]),
                allow_pickle=False,
            ),
            dtype=np.int64,
        )
        parent_voxel_ids = np.asarray(
            np.load(_artifact_path(prepared.feature_ids), allow_pickle=False),
            dtype=np.int64,
        )
        values = np.asarray(
            np.load(_artifact_path(artifact), allow_pickle=False),
            dtype=np.float32,
        ).reshape(-1)
        if values.shape != selected.shape:
            raise PublicationError(
                "direct bootstrap standard-error axis does not match selected voxels"
            )
        voxel_ids = parent_voxel_ids[selected]
        brainmask_path = Path(
            study["study"]["spot_model_sources"]["brainmask"]["path"]
        ).resolve()
        reference_image = nib.load(str(brainmask_path))
        volume = np.full(reference_image.shape, np.nan, dtype=np.float32)
        finite = np.isfinite(values)
        volume.reshape(-1)[voxel_ids[finite]] = values[finite]
        temporary_root = Path(tempfile.mkdtemp(prefix="dual-frequency-formal-nifti-"))
        try:
            temporary = temporary_root / "bootstrap_standard_error.nii.gz"
            image = nib.Nifti1Image(
                volume,
                reference_image.affine,
                reference_image.header,
            )
            image.set_data_dtype(np.float32)
            nib.save(image, temporary)
            writer.generated_file(
                relative,
                temporary,
                artifact_kind=artifact.kind,
                context={**context, "stage": "formal"},
                provenance={
                    "source_artifact_sha256": artifact.sha256,
                    "selected_feature_indices_sha256": source_artifacts[
                        "selected_feature_indices"
                    ].sha256,
                    "brainmask_sha256": _sha256_file(brainmask_path),
                },
            )
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

    @staticmethod
    def _publish_sensitivity_base(
        writer: _PublicationWriter,
        selection: FinalSelectionRecord,
        base: str,
        context: Mapping[str, object],
    ) -> None:
        source = _source_from_selection(selection)
        writer.json(
            f"{base}/sensitivity_base.json",
            {
                "schema_version": "dual_frequency_public_sensitivity_base_v1",
                "endpoint_id": selection.endpoint.identifier,
                "final_model_id": selection.final_model.identifier,
                "source_record_id": source.identifier,
                "selected_tau_v_per_m": source.selected_tau,
                "selected_coverage_subjects_min": source.selected_coverage,
                "valid_feature_axis": _plain(source.feature_axis),
                "artifact_sha256": {
                    item.kind: item.sha256 for item in source.artifacts
                },
            },
            artifact_kind="sensitivity_base",
            context={**context, "stage": "sensitivity_base"},
        )

    def _publish_manifest(
        self,
        writer: _PublicationWriter,
        run_manifest: Mapping[str, Any],
        resolved: Mapping[str, Any],
        study: Mapping[str, Any],
        times: tuple[str | None, str | None],
        *,
        domain: str,
    ) -> None:
        profile = resolved[domain]
        payload: dict[str, object] = {
            "schema_version": f"{domain}_model_manifest_v1",
            "model_set_id": profile["model_set_id"],
            "profile_type": domain,
            "study_id": run_manifest["study_id"],
            "study_base_path": str(writer.root / "study_base.json"),
            "study_base_sha256": run_manifest["study_base_sha256"],
            "resolved_model_path": (
                "resolved_direct_voxel_model.yaml"
                if domain == "direct_voxel"
                else "resolved_normative_fiber_model.yaml"
            ),
            "resolved_model_sha256": _sha256_file(
                writer.root
                / (
                    "resolved_direct_voxel_model.yaml"
                    if domain == "direct_voxel"
                    else "resolved_normative_fiber_model.yaml"
                )
            ),
            "scientific_config_sha256": run_manifest[
                "scientific_configuration_hash"
            ],
            "output_root": str(writer.root.parent.parent),
            "scale_ids": list(profile["scales"]),
            "scale_count": len(profile["scales"]),
            "code_provenance": {
                "git_available": False,
                "git_commit": None,
                "git_dirty": None,
                "run_code_identity": run_manifest.get("code_identity"),
            },
            "source_run_id": run_manifest["run_id"],
            "started_at_utc": times[0],
            "finished_at_utc": times[1],
            "final_status": "completed",
        }
        if domain == "normative_fiber":
            payload["connectomes"] = profile["connectomes"]
            payload["formal_connectome_id"] = next(
                item["connectome_id"]
                for item in profile["connectomes"]
                if item["role"] == "formal"
            )
        _PublicationWriter._install_bytes(
            writer.root / "model_manifest.json", _json_bytes(payload)
        )


__all__ = [
    "CanonicalPublisher",
    "ExtensionPublicationResult",
    "PublicationError",
    "PublicationResult",
]
