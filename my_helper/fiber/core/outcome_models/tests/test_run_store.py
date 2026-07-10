"""Tests for immutable configured-run storage and provenance."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

from outcome_models.run_store import (
    REQUIRED_RUN_ARTIFACTS,
    ConfiguredRunStore,
    RunIdentityMismatch,
    RunStoreError,
    sha256_file,
)


class ConfiguredRunStoreTests(unittest.TestCase):
    def _provenance(self) -> dict[str, object]:
        return {
            "configuration_hash": "config-sha256",
            "input_hashes": {
                "clinical_table": "clinical-sha256",
                "stimulation_table": "stimulation-sha256",
            },
            "code_provenance": {
                "commit": "abc123",
                "dirty": False,
                "environment": "leaddbs",
            },
        }

    def _create(self, output_root: Path, **kwargs) -> ConfiguredRunStore:
        return ConfiguredRunStore.create(
            output_root=output_root,
            study_id="synthetic_study",
            provenance=self._provenance(),
            started_at=datetime(2026, 7, 9, 12, 34, 56, tzinfo=timezone.utc),
            **kwargs,
        )

    def test_run_id_has_utc_prefix_and_reproducible_input_hash_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self._create(Path(tmp) / "one")
            second = self._create(Path(tmp) / "two")

        self.assertRegex(first.run_id, r"^20260709T123456Z_[0-9a-f]{16}$")
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.run_fingerprint, second.run_fingerprint)

    def test_initialize_writes_six_required_run_artifacts_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._create(Path(tmp))
            store.initialize(
                resolved_workflow={"schema_version": "four_model_v1", "selection": {"scales": ["scale_one"]}},
                endpoint_catalog=[{"endpoint_model_id": "endpoint_one", "status": "data_available"}],
                execution_plan={"tasks": [{"task_id": "task_one"}]},
            )
            names = {path.name for path in store.run_root.iterdir() if path.is_file()}
            workflow = yaml.safe_load((store.run_root / "workflow_resolved.yaml").read_text(encoding="utf-8"))
            plan = json.loads((store.run_root / "execution_plan.json").read_text(encoding="utf-8"))
            temporary_files = list(store.run_root.glob(".*.tmp"))

        self.assertEqual(names, set(REQUIRED_RUN_ARTIFACTS))
        self.assertEqual(workflow["selection"]["scales"], ["scale_one"])
        self.assertEqual(plan["tasks"][0]["task_id"], "task_one")
        self.assertEqual(temporary_files, [])

    def test_hash_helper_and_artifact_index_record_content_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._create(Path(tmp))
            store.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            artifact = store.run_root / "tasks" / "task_one" / "predictions.csv"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("subject,prediction\nsub-01,1.25\n", encoding="utf-8")
            store.record_artifact(task_id="task_one", kind="predictions", path=artifact)
            with (store.run_root / "artifact_index.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            actual_hash = sha256_file(artifact)

        expected = hashlib.sha256(b"subject,prediction\nsub-01,1.25\n").hexdigest()
        self.assertEqual(actual_hash, expected)
        self.assertEqual(rows[0]["sha256"], expected)
        self.assertEqual(rows[0]["relative_path"], "tasks/task_one/predictions.csv")

    def test_task_manifest_preserves_subject_and_feature_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._create(Path(tmp))
            store.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            path = store.write_task_manifest(
                task_id="task_one",
                manifest={
                    "dependency_ids": ["task_zero"],
                    "subject_order": ["sub-02", "sub-01"],
                    "feature_order": [17, 3, 11],
                    "terminal_status": "completed",
                },
            )
            manifest = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["subject_order"], ["sub-02", "sub-01"])
        self.assertEqual(manifest["feature_order"], [17, 3, 11])
        self.assertEqual(manifest["configuration_hash"], "config-sha256")

    def test_running_tasks_are_recovered_as_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._create(Path(tmp))
            store.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            store.write_task_statuses(
                [
                    {"task_id": "task_running", "status": "running", "detail": ""},
                    {"task_id": "task_done", "status": "completed", "detail": "ok"},
                ]
            )
            changed = store.recover_interrupted_tasks()
            with (store.run_root / "task_status.csv").open(encoding="utf-8") as handle:
                rows = {row["task_id"]: row for row in csv.DictReader(handle)}

        self.assertEqual(changed, ("task_running",))
        self.assertEqual(rows["task_running"]["status"], "interrupted")
        self.assertEqual(rows["task_done"]["status"], "completed")

    def test_resume_requires_exact_identity_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            created = self._create(output_root)
            created.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            resumed = ConfiguredRunStore.resume(
                output_root=output_root,
                study_id="synthetic_study",
                run_id=created.run_id,
                expected_provenance=self._provenance(),
            )
            incompatible = self._provenance()
            incompatible["configuration_hash"] = "different"
            with self.assertRaises(RunIdentityMismatch):
                ConfiguredRunStore.resume(
                    output_root=output_root,
                    study_id="synthetic_study",
                    run_id=created.run_id,
                    expected_provenance=incompatible,
                )

        self.assertEqual(resumed.run_root, created.run_root)

    def test_force_creates_new_run_and_records_superseded_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            original = self._create(output_root)
            original.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            forced = ConfiguredRunStore.create(
                output_root=output_root,
                study_id="synthetic_study",
                provenance=self._provenance(),
                started_at=datetime(2026, 7, 9, 12, 35, 1, tzinfo=timezone.utc),
                supersedes_run_id=original.run_id,
            )
            forced.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            manifest = json.loads((forced.run_root / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertNotEqual(forced.run_id, original.run_id)
        self.assertEqual(manifest["supersedes_run_id"], original.run_id)

    def test_artifact_outside_run_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self._create(root / "outputs")
            store.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan={"tasks": []})
            external = root / "external.csv"
            external.write_text("value\n1\n", encoding="utf-8")
            with self.assertRaises(RunStoreError):
                store.record_artifact(task_id="task_one", kind="external", path=external)

    def test_run_root_cannot_be_created_inside_legacy_output_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy_root = Path(tmp) / "summary"
            legacy_root.mkdir()
            with self.assertRaises(RunStoreError):
                ConfiguredRunStore.create(
                    output_root=legacy_root,
                    study_id="synthetic_study",
                    provenance=self._provenance(),
                    legacy_roots=(legacy_root,),
                )


if __name__ == "__main__":
    unittest.main()
