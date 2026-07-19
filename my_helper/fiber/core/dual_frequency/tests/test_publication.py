"""Canonical publication transaction and replay boundary tests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import dual_frequency.application.publication as publication_module
from dual_frequency.application.publication import (
    CanonicalPublisher,
    PublicationError,
    _PublicationWriter,
)
from dual_frequency.contracts import ArtifactRef, AxisRef


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> ArtifactRef:
    axis = AxisRef("axis-test", 3, "a" * 64)
    return ArtifactRef(
        kind="test_array",
        schema_version="dual_frequency_array_v1",
        uri=path.resolve().as_uri(),
        sha256=_sha256(path),
        dtype="float32",
        shape=(3,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="MNI152NLin2009bAsym",
        producer_id="task-test",
        producer_version="1",
    )


def test_writer_copies_verified_payload_without_persisting_run_uri(tmp_path: Path) -> None:
    source = tmp_path / ".runs" / "work" / "source.npy"
    source.parent.mkdir(parents=True)
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    reference = _artifact(source)
    context = {
        "scale_id": "scale_a",
        "model_family": "reference",
        "stage": "resolver",
    }

    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context=context,
    )
    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context=context,
    )
    writer.write_index()

    target = publication / "scale_a/reference/resolver/full_weights.npy"
    metadata_path = Path(f"{target}.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with (publication / "artifact_index.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert target.read_bytes() == source.read_bytes()
    assert "uri" not in metadata["source_artifact"]
    assert ".runs" not in metadata_path.read_text(encoding="utf-8")
    assert rows[0]["relative_path"] == "scale_a/reference/resolver/full_weights.npy"
    assert rows[0]["sha256"] == _sha256(target)
    assert int(rows[0]["size_bytes"]) == target.stat().st_size
    assert rows[0]["status"] == "completed"


def test_writer_rejects_immutable_collision(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    context = {"stage": "configuration"}
    writer.bytes(
        "resolved.yaml",
        b"first\n",
        artifact_kind="resolved_model_profile",
        context=context,
    )

    with pytest.raises(PublicationError, match="immutable publication collision"):
        writer.bytes(
            "resolved.yaml",
            b"second\n",
            artifact_kind="resolved_model_profile",
            context=context,
        )


def test_new_in_memory_payload_reuses_digest_without_fsync_or_reread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")

    def reject_fsync(_descriptor: int) -> None:
        raise AssertionError("publication must not issue a per-artifact fsync")

    def reject_reread(_path: Path) -> str:
        raise AssertionError("new in-memory payload must reuse its verified digest")

    monkeypatch.setattr(publication_module.os, "fsync", reject_fsync)
    monkeypatch.setattr(publication_module, "_sha256_file", reject_reread)
    writer.bytes(
        "resolved.yaml",
        b"payload\n",
        artifact_kind="resolved_model_profile",
        context={"stage": "configuration"},
    )

    expected = hashlib.sha256(b"payload\n").hexdigest()
    assert writer.rows["resolved.yaml"]["sha256"] == expected
    assert writer.rows["resolved.yaml"]["size_bytes"] == len(b"payload\n")


def test_copied_payload_hashes_temporary_once_and_reuses_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    original_sha256_file = publication_module._sha256_file
    checked_paths: list[Path] = []

    def track_sha256(path: Path) -> str:
        checked_paths.append(Path(path))
        return original_sha256_file(path)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context={"scale_id": "scale_a", "stage": "resolver"},
    )

    target = publication / "scale_a/reference/resolver/full_weights.npy"
    assert checked_paths[0] == source
    assert len(checked_paths) == 2
    assert checked_paths[1].parent == target.parent
    assert checked_paths[1] != target
    assert target not in checked_paths
    assert writer.rows[
        "scale_a/reference/resolver/full_weights.npy"
    ]["sha256"] == reference.sha256


def test_publisher_verifies_each_source_path_once_per_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publisher = CanonicalPublisher()
    original_sha256_file = publication_module._sha256_file
    original_artifact_location = publication_module._artifact_location
    checked_paths: list[Path] = []
    resolved_uris: list[str] = []

    def track_sha256(path: Path) -> str:
        checked_paths.append(Path(path))
        return original_sha256_file(path)

    def track_artifact_location(artifact: ArtifactRef) -> Path:
        resolved_uris.append(artifact.uri)
        return original_artifact_location(artifact)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    monkeypatch.setattr(
        publication_module, "_artifact_location", track_artifact_location
    )
    assert publisher._artifact_path(reference) == source.resolve()
    assert publisher._artifact_path(reference) == source.resolve()

    assert checked_paths == [source.resolve()]
    assert resolved_uris == [reference.uri]


def test_publisher_rejects_missing_source_payload(tmp_path: Path) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    source.unlink()

    with pytest.raises(PublicationError, match="source artifact is missing"):
        CanonicalPublisher()._artifact_path(reference)


def test_publisher_rejects_changed_digest_without_rereading_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publisher = CanonicalPublisher()
    original_sha256_file = publication_module._sha256_file
    checks = 0

    def track_sha256(path: Path) -> str:
        nonlocal checks
        checks += 1
        return original_sha256_file(path)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    publisher._artifact_path(reference)
    changed = ArtifactRef(
        kind=reference.kind,
        schema_version=reference.schema_version,
        uri=reference.uri,
        sha256="b" * 64,
        dtype=reference.dtype,
        shape=reference.shape,
        axis_refs=reference.axis_refs,
        axis_hashes=reference.axis_hashes,
        units=reference.units,
        space=reference.space,
        producer_id=reference.producer_id,
        producer_version=reference.producer_version,
    )

    with pytest.raises(PublicationError, match="SHA-256 mismatch"):
        publisher._artifact_path(changed)

    assert checks == 1


def test_writer_resolves_each_destination_parent_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    original_resolve = Path.resolve
    resolved_paths: list[Path] = []

    def track_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        resolved_paths.append(path)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", track_resolve)
    writer.bytes(
        "scale_a/reference/first.json",
        b"first\n",
        artifact_kind="first",
        context={"scale_id": "scale_a"},
    )
    writer.bytes(
        "scale_a/reference/second.json",
        b"second\n",
        artifact_kind="second",
        context={"scale_id": "scale_a"},
    )

    assert resolved_paths == [publication / "scale_a/reference"]


def test_writer_rejects_destination_parent_symlink_escape(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    outside = tmp_path / "outside"
    outside.mkdir()
    publication.mkdir()
    (publication / "escape").symlink_to(outside, target_is_directory=True)
    writer = _PublicationWriter(publication, domain="direct_voxel")

    with pytest.raises(PublicationError, match="escapes model root"):
        writer.bytes(
            "escape/payload.json",
            b"payload\n",
            artifact_kind="payload",
            context={"stage": "configuration"},
        )

    assert not (outside / "payload.json").exists()


def test_replay_rejects_noncompleted_manifest_without_writing(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    recovery_cache = run_root / "recovery-cache"
    recovery_cache.mkdir()
    checkpoint = recovery_cache / "checkpoint.bin"
    checkpoint.write_bytes(b"recoverable partial state")
    (run_root / "run_manifest.json").write_text(
        json.dumps({"final_status": "failed"}), encoding="utf-8"
    )

    with pytest.raises(PublicationError, match="completed run manifest"):
        CanonicalPublisher().publish(run_root)

    assert tuple(tmp_path.glob("**/model_manifest.json")) == ()
    assert checkpoint.read_bytes() == b"recoverable partial state"


def test_outcome_loader_rejects_failed_tasks_and_preserves_task_file(
    tmp_path: Path,
) -> None:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    task = tasks / "task_failed.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "task_failed",
                "endpoint_id": "endpoint_failed",
                "service_id": "service_failed",
                "status": "failed",
                "reason": "injected_failure",
                "started_at": None,
                "finished_at": None,
                "result": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublicationError, match="retains failed tasks"):
        CanonicalPublisher._outcomes(tmp_path)

    assert task.is_file()
    assert json.loads(task.read_text(encoding="utf-8"))["status"] == "failed"
