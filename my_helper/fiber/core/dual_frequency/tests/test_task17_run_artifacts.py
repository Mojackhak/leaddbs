"""Tests for complete Task 17 run-artifact payload validation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "pipelines"
    / "validate_task17_run_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_task17_run_artifacts",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Task 17 run-artifact validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact(path: Path, kind: str, producer: str) -> dict[str, object]:
    return {
        "kind": kind,
        "producer_id": producer,
        "producer_version": "1",
        "schema_version": "dual_frequency_document_v1",
        "sha256": validator._sha256_file(path),
        "uri": path.resolve().as_uri(),
    }


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    work = root / "work"
    work.mkdir(parents=True)
    shared_path = work / "shared.json"
    unique_path = work / "unique.json"
    _write_json(shared_path, {"value": "shared"})
    _write_json(unique_path, {"value": "unique"})
    shared = _artifact(shared_path, "shared", "task_a")
    unique = _artifact(unique_path, "unique", "task_a")
    tasks = {
        "task_a": (shared, unique),
        "task_b": (shared,),
    }
    for task_id, artifacts in tasks.items():
        _write_json(
            root / "tasks" / f"{task_id}.json",
            {
                "endpoint_id": f"endpoint_{task_id}",
                "finished_at": "2026-07-26T00:00:01Z",
                "reason": "none",
                "result": {
                    "artifacts": list(artifacts),
                    "facts": {},
                    "output_record_type": "SyntheticRecord",
                    "payload": {},
                    "record_id": f"record_{task_id}",
                },
                "service_id": "synthetic",
                "started_at": "2026-07-26T00:00:00Z",
                "status": "completed",
                "task_id": task_id,
            },
        )
    _write_json(
        root / "run_manifest.json",
        {
            "final_status": "completed",
            "run_id": "run",
            "scientific_configuration_hash": "a" * 64,
            "study_base_sha256": "b" * 64,
            "study_id": "study",
        },
    )
    rows = []
    for index, artifact in enumerate((shared, unique), start=1):
        task_ids = [
            task_id
            for task_id, artifacts in tasks.items()
            if artifact in artifacts
        ]
        rows.append(
            {
                "artifact_id": f"artifact_{index}",
                **artifact,
                "task_references": [
                    {
                        "endpoint_id": f"endpoint_{task_id}",
                        "output_record_type": "SyntheticRecord",
                        "record_id": f"record_{task_id}",
                        "service_id": "synthetic",
                        "task_id": task_id,
                    }
                    for task_id in task_ids
                ],
            }
        )
    _write_json(
        root / "artifact_index.json",
        {
            "artifacts": rows,
            "run_id": "run",
            "schema_version": "dual_frequency_artifact_index_v2",
        },
    )
    return root


def test_complete_run_and_same_byte_report_pass(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    report = validator.validate(root)

    assert report["status"] == "validated"
    assert report["task_count"] == 2
    assert report["artifact_count"] == 2
    assert report["task_artifact_reference_count"] == 3
    assert report["artifact_bytes"] > 0

    output = tmp_path / "validation.json"
    validator._write_report(output, report)
    first_stat = output.stat()
    validator._write_report(output, report)
    assert output.stat().st_mtime_ns == first_stat.st_mtime_ns
    changed = dict(report)
    changed["status"] = "changed"
    with pytest.raises(
        validator.RunArtifactValidationError,
        match="differs",
    ):
        validator._write_report(output, changed)


def test_payload_corruption_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    _write_json(root / "work/shared.json", {"value": "corrupt"})

    with pytest.raises(
        validator.RunArtifactValidationError,
        match="payload SHA differs",
    ):
        validator.validate(root)


def test_missing_index_identity_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    index_path = root / "artifact_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["artifacts"] = index["artifacts"][:1]
    _write_json(index_path, index)

    with pytest.raises(
        validator.RunArtifactValidationError,
        match="identity closures differ",
    ):
        validator.validate(root)


def test_task_reference_closure_mismatch_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    index_path = root / "artifact_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["artifacts"][0]["task_references"] = index["artifacts"][0][
        "task_references"
    ][:1]
    _write_json(index_path, index)

    with pytest.raises(
        validator.RunArtifactValidationError,
        match="task-reference closure differs",
    ):
        validator.validate(root)


def test_artifact_outside_run_root_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    outside = tmp_path / "outside.json"
    _write_json(outside, {"value": "outside"})
    index_path = root / "artifact_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    old = index["artifacts"][1]
    new_artifact = _artifact(outside, str(old["kind"]), "task_a")
    index["artifacts"][1].update(new_artifact)
    task_path = root / "tasks/task_a.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["result"]["artifacts"][1].update(new_artifact)
    _write_json(task_path, task)
    _write_json(index_path, index)

    with pytest.raises(
        validator.RunArtifactValidationError,
        match="outside the run root",
    ):
        validator.validate(root)
