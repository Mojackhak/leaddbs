"""Tests for reviewed, bounded predecessor fixture manifests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from projects.stnsnr.acceptance.build_bounded_fixture_manifest import (
    FixtureManifestError,
    build_fixture_manifest,
)
from projects.stnsnr.acceptance.compare_bounded_fixtures import compare_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BoundedFixtureManifestTests(unittest.TestCase):
    def _write_run(self, root: Path) -> tuple[Path, Path]:
        run_root = root / "frozen_run"
        run_root.mkdir()
        (run_root / "run_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "frozen_run",
                    "configuration_hash": "c" * 64,
                    "provenance_hash": "e" * 64,
                    "status": "initialized",
                    "code_provenance": {"commit": "d" * 40, "dirty": False},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        task_specs = []
        statuses = {
            "task_science": "completed",
            "task_completed_but_not_allowed": "completed",
            "task_failure_report": "completed",
            "task_failed": "execution_failure",
            "task_missing": "completed",
        }
        artifact_rows: list[dict[str, str]] = []
        for task_id, status in statuses.items():
            stage = "endpoint_report" if task_id == "task_failure_report" else "observed_source_resolver"
            expected = ["task_manifest", "endpoint_report"] if stage == "endpoint_report" else [
                "task_manifest",
                "scientific_array",
            ]
            spec = {
                "task_id": task_id,
                "endpoint_model_id": "endpoint_a",
                "execution_stage": stage,
                "workflow_phase": "report" if stage == "endpoint_report" else "observed",
                "branch": "none",
                "replicate": "none",
                "source_reference": "none",
                "round_name": "Round 1",
                "dependencies": [],
                "gate": {"predicate": "always"},
                "expected_artifact_kinds": expected,
                "endpoint": {
                    "study_id": "study",
                    "scale_id": "scale",
                    "endpoint_phase": "reference",
                    "model_family": "hf_voxel",
                    "connectome": "none",
                },
            }
            task_specs.append(spec)
            task_root = run_root / "tasks" / task_id
            task_root.mkdir(parents=True)
            task_manifest = task_root / "task_manifest.json"
            task_manifest.write_text(
                json.dumps({"task_id": task_id, "status": status, "task": spec}) + "\n",
                encoding="utf-8",
            )
            artifact_rows.append(
                {
                    "task_id": task_id,
                    "kind": "task_manifest",
                    "relative_path": task_manifest.relative_to(run_root).as_posix(),
                    "sha256": _sha256(task_manifest),
                    "size_bytes": str(task_manifest.stat().st_size),
                }
            )
            if task_id == "task_missing":
                artifact_rows.append(
                    {
                        "task_id": task_id,
                        "kind": "scientific_array",
                        "relative_path": f"models/{task_id}/missing.npy",
                        "sha256": "f" * 64,
                        "size_bytes": "128",
                    }
                )
            elif stage == "endpoint_report":
                report = task_root / "endpoint_report.csv"
                report.write_text("status\nfailed\n", encoding="utf-8")
                artifact_rows.append(
                    {
                        "task_id": task_id,
                        "kind": "endpoint_report",
                        "relative_path": report.relative_to(run_root).as_posix(),
                        "sha256": _sha256(report),
                        "size_bytes": str(report.stat().st_size),
                    }
                )
            else:
                array = task_root / "weights.npy"
                np.save(array, np.array([1.0, 2.0], dtype=np.float64))
                artifact_rows.append(
                    {
                        "task_id": task_id,
                        "kind": "scientific_array",
                        "relative_path": array.relative_to(run_root).as_posix(),
                        "sha256": _sha256(array),
                        "size_bytes": str(array.stat().st_size),
                    }
                )
        task_specs.append(
            {
                "task_id": "task_unstarted",
                "endpoint_model_id": "endpoint_a",
                "execution_stage": "formal_permutation",
                "workflow_phase": "formal",
                "branch": "none",
                "replicate": "none",
                "source_reference": "final_model_record",
                "round_name": "Round 2",
                "dependencies": [],
                "gate": {"predicate": "final_model_realized"},
                "expected_artifact_kinds": ["task_manifest", "formal_results"],
                "endpoint": {
                    "study_id": "study",
                    "scale_id": "scale",
                    "endpoint_phase": "reference",
                    "model_family": "hf_voxel",
                    "connectome": "none",
                },
            }
        )
        (run_root / "execution_plan.json").write_text(
            json.dumps({"tasks": task_specs}) + "\n", encoding="utf-8"
        )
        with (run_root / "task_status.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "task_id",
                    "endpoint_model_id",
                    "status",
                    "detail",
                    "started_at",
                    "finished_at",
                    "dependency_ids",
                    "final_model_id",
                ),
            )
            writer.writeheader()
            for task_id, status in statuses.items():
                writer.writerow(
                    {
                        "task_id": task_id,
                        "endpoint_model_id": "endpoint_a",
                        "status": status,
                        "detail": status,
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "dependency_ids": "[]",
                        "final_model_id": "",
                    }
                )
        with (run_root / "artifact_index.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=artifact_rows[0].keys())
            writer.writeheader()
            writer.writerows(artifact_rows)
        allowlist_path = root / "allowlist.json"
        allowlist_path.write_text(
            json.dumps(
                {
                    "schema_version": "dual_frequency_approved_task_allowlist_v1",
                    "source_run": {
                        "run_id": "frozen_run",
                        "commit": "d" * 40,
                        "configuration_hash": "c" * 64,
                        "provenance_hash": "e" * 64,
                        "status": "initialized",
                        "dirty": False,
                    },
                    "scopes": [
                        {
                            "scope_id": "reference_direct_voxel",
                            "source_endpoints": [
                                {
                                    "source_endpoint_model_id": "endpoint_a",
                                    "connectome_id": "none",
                                }
                            ],
                            "parent_scale_id": "scale",
                            "model_family": "hf_voxel",
                            "source_binding_role": "reference",
                            "source_connectome_role": "not_applicable",
                            "target_connectome_roles": [],
                            "tasks": [
                                {
                                    "task_id": "task_science",
                                    "execution_stage": "observed_source_resolver",
                                    "branch": "none",
                                    "expected_status": "completed",
                                    "plan_expected_artifact_kinds": [
                                        "task_manifest",
                                        "scientific_array",
                                    ],
                                    "reviewed_artifact_kinds": ["scientific_array"],
                                    "artifact_kind_conversions": {},
                                }
                            ],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return run_root, allowlist_path

    def test_explicit_allowlist_prevents_status_based_auto_enrollment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root, allowlist_path = self._write_run(root)
            manifest = build_fixture_manifest(run_root, allowlist_path, root / "fixture")
            payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual([row["task_id"] for row in payload["eligible_tasks"]], ["task_science"])
        self.assertEqual(payload["source_run_id"], "frozen_run")
        self.assertEqual(payload["eligible_tasks"][0]["scope_id"], "reference_direct_voxel")
        self.assertEqual(payload["eligible_tasks"][0]["source_binding_role"], "reference")
        self.assertEqual(payload["eligible_tasks"][0]["artifact_kind_conversions"], {})
        self.assertIn("task_completed_but_not_allowed", payload["excluded_tasks"])
        self.assertIn("task_missing", payload["excluded_tasks"])
        self.assertIn("task_unstarted", payload["excluded_tasks"])

    def test_unknown_duplicate_and_hash_invalid_allowlist_entries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root, allowlist_path = self._write_run(root)
            payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
            payload["scopes"][0]["tasks"].append(dict(payload["scopes"][0]["tasks"][0]))
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "duplicate"):
                build_fixture_manifest(run_root, allowlist_path, root / "duplicate")

            task = payload["scopes"][0]["tasks"][0]
            payload["scopes"][0]["tasks"] = [{**task, "task_id": "task_unknown"}]
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "unknown"):
                build_fixture_manifest(run_root, allowlist_path, root / "unknown")

            payload["scopes"][0]["tasks"] = [{**task, "task_id": "task_science"}]
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            array = run_root / "tasks" / "task_science" / "weights.npy"
            array.write_bytes(b"tampered")
            with self.assertRaisesRegex(FixtureManifestError, "SHA-256"):
                build_fixture_manifest(run_root, allowlist_path, root / "tampered")

    def test_allowlisted_artifact_path_cannot_escape_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root, allowlist_path = self._write_run(root)
            with (run_root / "artifact_index.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                if row["task_id"] == "task_science" and row["kind"] == "scientific_array":
                    row["relative_path"] = "../outside.npy"
            with (run_root / "artifact_index.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(FixtureManifestError, "outside"):
                build_fixture_manifest(run_root, allowlist_path, root / "escaped")

    def test_paused_source_status_dirty_state_and_provenance_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root, allowlist_path = self._write_run(root)
            payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
            payload["source_run"]["status"] = "completed"
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "status"):
                build_fixture_manifest(run_root, allowlist_path, root / "wrong-status")

            payload["source_run"]["status"] = "initialized"
            payload["source_run"]["dirty"] = True
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "dirty"):
                build_fixture_manifest(run_root, allowlist_path, root / "dirty")

            payload["source_run"]["dirty"] = False
            payload["source_run"]["provenance_hash"] = "0" * 64
            allowlist_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "provenance_hash"):
                build_fixture_manifest(run_root, allowlist_path, root / "provenance")

    def test_manifest_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root, allowlist_path = self._write_run(root)
            first = build_fixture_manifest(run_root, allowlist_path, root / "first")
            second = build_fixture_manifest(run_root, allowlist_path, root / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_comparison_uses_tolerance_for_float_arrays_and_exact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected_array = root / "expected.npy"
            observed_array = root / "observed.npy"
            np.save(expected_array, np.array([1.0, 2.0], dtype=np.float64))
            np.save(observed_array, np.array([1.0 + 1e-11, 2.0], dtype=np.float64))
            expected = root / "expected.json"
            observed = root / "observed.json"
            base = {
                "schema_version": "dual_frequency_bounded_fixture_v1",
                "eligible_tasks": [
                    {
                        "task_id": "task_science",
                        "artifacts": [
                            {
                                "kind": "weights",
                                "path": str(expected_array),
                                "comparison": "floating",
                            }
                        ],
                    }
                ],
            }
            expected.write_text(json.dumps(base) + "\n", encoding="utf-8")
            changed = json.loads(json.dumps(base))
            changed["eligible_tasks"][0]["artifacts"][0]["path"] = str(observed_array)
            observed.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            result = compare_fixture(expected, observed)
            self.assertTrue(result.passed)

            changed["eligible_tasks"][0]["task_id"] = "different"
            observed.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            self.assertFalse(compare_fixture(expected, observed).passed)

    def test_comparison_keeps_integer_masks_exact_and_compares_mixed_csv_by_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected_mask = root / "expected_mask.npy"
            observed_mask = root / "observed_mask.npy"
            np.save(expected_mask, np.array([1, 0, 1], dtype=np.uint8))
            np.save(observed_mask, np.array([1, 1, 1], dtype=np.uint8))
            expected_csv = root / "expected.csv"
            observed_csv = root / "observed.csv"
            pd.DataFrame({"ID": ["a", "b"], "score": [1.0, 2.0], "note": [None, "ok"]}).to_csv(expected_csv, index=False)
            pd.DataFrame({"ID": ["a", "b"], "score": [1.0 + 1e-11, 2.0], "note": [None, "ok"]}).to_csv(
                observed_csv, index=False
            )
            expected = root / "expected.json"
            observed = root / "observed.json"
            expected.write_text(
                json.dumps(
                    {
                        "eligible_tasks": [
                            {
                                "task_id": "task_science",
                                "artifacts": [
                                    {"kind": "mask", "path": str(expected_mask)},
                                    {"kind": "scores", "path": str(expected_csv)},
                                ],
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            observed.write_text(
                json.dumps(
                    {
                        "eligible_tasks": [
                            {
                                "task_id": "task_science",
                                "artifacts": [
                                    {"kind": "mask", "path": str(observed_mask)},
                                    {"kind": "scores", "path": str(observed_csv)},
                                ],
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = compare_fixture(expected, observed)

        self.assertFalse(result.passed)
        self.assertTrue(any("mask" in difference for difference in result.differences))
        self.assertFalse(any(":scores:score" in difference for difference in result.differences))
        self.assertFalse(any(":scores:note" in difference for difference in result.differences))

    def test_comparison_uses_oss_probability_tolerance_and_exact_json_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected_probability = root / "expected_probability.npy"
            observed_probability = root / "observed_probability.npy"
            np.save(expected_probability, np.array([0.1, 0.9], dtype=np.float32))
            np.save(observed_probability, np.array([0.1 + 5e-8, 0.9], dtype=np.float32))
            expected_meta = root / "expected_meta.json"
            observed_meta = root / "observed_meta.json"
            expected_meta.write_text(json.dumps({"fiber_id": "f1", "metric": 1.0}) + "\n")
            observed_meta.write_text(json.dumps({"fiber_id": "f2", "metric": 1.0 + 1e-11}) + "\n")
            expected = root / "expected.json"
            observed = root / "observed.json"
            tasks = lambda probability, metadata: {
                "eligible_tasks": [
                    {
                        "task_id": "task_science",
                        "artifacts": [
                            {
                                "kind": "oss_activation_probabilities",
                                "path": str(probability),
                            },
                            {"kind": "metadata", "path": str(metadata)},
                        ],
                    }
                ]
            }
            expected.write_text(json.dumps(tasks(expected_probability, expected_meta)) + "\n")
            observed.write_text(json.dumps(tasks(observed_probability, observed_meta)) + "\n")
            result = compare_fixture(expected, observed)

        self.assertFalse(result.passed)
        self.assertFalse(any("oss_activation_probabilities" in item for item in result.differences))
        self.assertTrue(any("metadata" in item for item in result.differences))


if __name__ == "__main__":
    unittest.main()
