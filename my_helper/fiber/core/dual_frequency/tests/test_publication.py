"""Canonical publication transaction and replay boundary tests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

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
