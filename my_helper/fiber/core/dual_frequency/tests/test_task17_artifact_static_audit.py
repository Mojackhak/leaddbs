"""Tests for Task 17 artifact and nested-executor auditing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from my_helper.fiber.pipelines import run_task17_artifact_static_audit as auditor


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Task17ArtifactStaticAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "run"
        self.source = self.root / "dual_frequency"
        for name in ("runtime", "backends", "cache"):
            path = self.source / name / "module.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 1\n", encoding="utf-8")
        self.payload = self.run / "work" / "task_one" / "value.npy"
        self.payload.parent.mkdir(parents=True, exist_ok=True)
        self.payload.write_bytes(b"artifact")
        self.artifact = {
            "axis_hashes": [],
            "axis_refs": [],
            "dtype": "float32",
            "kind": "prepared_reference_exposure",
            "producer_id": "task_one",
            "producer_version": "1",
            "schema_version": "dual_frequency_array_v1",
            "sha256": _sha(self.payload),
            "shape": [2],
            "space": None,
            "units": "V/m",
            "uri": self.payload.resolve().as_uri(),
        }
        _write(
            self.run / "run_manifest.json",
            {"run_id": "run-one", "final_status": "completed"},
        )
        _write(
            self.run / "artifact_index.json",
            {
                "schema_version": "dual_frequency_artifact_index_v1",
                "artifacts": [
                    {
                        "artifact_id": "artifact-one",
                        "kind": self.artifact["kind"],
                        "uri": self.artifact["uri"],
                        "sha256": self.artifact["sha256"],
                    }
                ],
            },
        )
        _write(
            self.run / "tasks" / "task_one.json",
            {
                "task_id": "task_one",
                "status": "completed",
                "result": {"artifacts": [self.artifact]},
            },
        )
        self.event = (
            self.run
            / "execution_segments"
            / "performance_events_segment_0001.json"
        )
        _write(
            self.event,
            {
                "schema_version": (
                    "dual_frequency_performance_event_report_v1"
                ),
                "segment_id": "segment_0001",
                "aggregation_status": "complete",
                "fragments": [{"task_id": "task_one"}],
            },
        )
        self.segment = (
            self.run / "execution_segments" / "segment_0001.json"
        )
        _write(
            self.segment,
            {
                "schema_version": "dual_frequency_execution_segment_v1",
                "segment_id": "segment_0001",
                "status": "finished",
                "performance_events_path": str(
                    self.event.relative_to(self.run)
                ),
                "performance_events_sha256": _sha(self.event),
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_audits_artifacts_sources_and_identical_replay(self) -> None:
        output = auditor.audit(
            run_root=self.run,
            segment_id="segment_0001",
            source_root=self.source,
        )
        first = output.read_bytes()
        self.assertEqual(
            auditor.audit(
                run_root=self.run,
                segment_id="segment_0001",
                source_root=self.source,
            ),
            output,
        )
        self.assertEqual(output.read_bytes(), first)
        document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(document["task_ids"], ["task_one"])
        self.assertEqual(document["inspected_artifact_ids"], ["artifact-one"])
        self.assertEqual(document["retained_null_n_by_f_artifact_ids"], [])
        self.assertEqual(document["nested_executor_creation_sites"], [])
        self.assertEqual(len(document["scientific_source_files"]), 3)

    def test_reports_nested_scientific_executor_site(self) -> None:
        (self.source / "runtime" / "module.py").write_text(
            "ThreadPoolExecutor(max_workers=2)\n",
            encoding="utf-8",
        )
        output = auditor.audit(
            run_root=self.run,
            segment_id="segment_0001",
            source_root=self.source,
        )
        document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            document["nested_executor_creation_sites"],
            [
                {
                    "constructor": "ThreadPoolExecutor",
                    "line": 1,
                    "path": "runtime/module.py",
                }
            ],
        )

    def test_rejects_task_artifact_missing_from_index(self) -> None:
        _write(
            self.run / "artifact_index.json",
            {
                "schema_version": "dual_frequency_artifact_index_v1",
                "artifacts": [],
            },
        )
        with self.assertRaises(auditor.ArtifactStaticAuditError):
            auditor.audit(
                run_root=self.run,
                segment_id="segment_0001",
                source_root=self.source,
            )


if __name__ == "__main__":
    unittest.main()
