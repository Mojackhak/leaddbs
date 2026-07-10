"""Immutable run artifact and provenance contract tests."""

from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

from my_helper.fiber.core.seed_target_connectivity.artifacts import (
    REQUIRED_ARTIFACTS,
    artifact_hashes,
    build_run_fingerprint,
    collect_code_provenance,
    verify_artifact_index,
    write_run_atomic,
)
from my_helper.fiber.core.seed_target_connectivity.config import resolve_config
from my_helper.fiber.core.seed_target_connectivity.engine import compute_memberships
from my_helper.fiber.core.seed_target_connectivity.errors import ArtifactError
from my_helper.fiber.core.seed_target_connectivity.statistics import compute_statistics
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    RecordingAdapter,
    line,
    resolved_atlas,
    resolved_mask,
)


class ArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_root = self.root / "output"
        self.config = resolve_config(
            {
                "schema_version": 1,
                "execution": {"fiber_chunk_size": 2, "cache_membership": False},
            }
        )
        self.seed = resolved_mask([(1, 1, 1)], roi_id="seed", role="seed")
        self.atlas = resolved_atlas(
            [
                resolved_mask([(1, 1, 1)], roi_id="group/a"),
                resolved_mask([(3, 1, 1)], roi_id="group/b"),
                resolved_mask([], roi_id="group/empty"),
            ]
        )
        self.adapter = RecordingAdapter(
            [
                line((0, 1, 1), (4, 1, 1)),
                line((0, 1, 1), (2, 1, 1)),
                line((2.5, 1, 1), (3.25, 1, 1)),
            ]
        )
        self.membership = compute_memberships(
            self.adapter,
            self.seed,
            self.atlas,
            self.config,
        )
        self.statistics = compute_statistics(
            self.membership,
            self.atlas,
            ranking_enabled=True,
        )
        self.code_provenance = {
            "git_commit": "1" * 40,
            "package_sha256": "2" * 64,
        }
        self.created_at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, *, now: datetime | None = None, config=None):
        return write_run_atomic(
            output_root=self.output_root,
            config=self.config if config is None else config,
            seed=self.seed,
            atlas=self.atlas,
            connectome_metadata=self.adapter.metadata,
            membership=self.membership,
            statistics=self.statistics,
            code_provenance=self.code_provenance,
            now=self.created_at if now is None else now,
        )

    def test_writes_exact_required_artifacts_and_valid_hash_index(self) -> None:
        run = self._write()

        self.assertEqual({path.name for path in run.run_dir.iterdir()}, set(REQUIRED_ARTIFACTS))
        indexed = verify_artifact_index(run.run_dir)
        self.assertEqual(indexed, artifact_hashes(run.run_dir))
        self.assertEqual(indexed, dict(run.artifact_hashes))
        self.assertEqual(set(indexed), set(REQUIRED_ARTIFACTS) - {"artifact_index.csv"})

    def test_serializes_required_connectivity_columns_and_no_nonfinite_tokens(self) -> None:
        run = self._write()
        connectivity_path = run.run_dir / "target_connectivity.csv"
        with connectivity_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), len(self.atlas.targets))
        required = {
            "target_id",
            "target_group",
            "relative_path",
            "source_value_type",
            "probability_threshold",
            "threshold_source",
            "target_status",
            "n_all_fibers",
            "n_seed_fibers",
            "n_target_fibers",
            "n_seed_target_fibers",
            "raw_fiber_count",
            "seed_normalized_fraction",
            "target_background_prevalence",
            "connectivity_lift",
            "connectivity_pmi",
            "rank",
        }
        self.assertTrue(required.issubset(rows[0]))
        serialized = connectivity_path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", serialized)
        self.assertNotIn("Infinity", serialized)
        self.assertNotIn("-inf", serialized.lower())

    def test_manifest_and_qc_record_complete_input_and_algorithm_provenance(self) -> None:
        run = self._write()
        manifest = json.loads((run.run_dir / "analysis_manifest.json").read_text(encoding="utf-8"))
        with (run.run_dir / "input_resolution_qc.csv").open(newline="", encoding="utf-8") as handle:
            qc_rows = list(csv.DictReader(handle))

        self.assertEqual(manifest["configuration_hash"], self.config.configuration_hash)
        self.assertEqual(manifest["connectome"]["geometry_hash"], self.adapter.metadata.geometry_hash)
        self.assertEqual(
            manifest["connectome"]["ordered_fiber_id_hash"],
            self.adapter.metadata.ordered_fiber_id_hash,
        )
        self.assertEqual(manifest["algorithm"]["fiber_chunk_size"], 2)
        self.assertEqual(manifest["seed"]["resolved_mask_hash"], self.seed.resolved_mask_hash)
        self.assertEqual(manifest["target_atlas"]["resolved_mask_hash"], self.atlas.atlas_hash)
        self.assertEqual(manifest["code_provenance"], self.code_provenance)
        self.assertEqual(manifest["created_at"], "2026-07-10T12:00:00Z")
        self.assertEqual(len(manifest["artifact_hashes"]), 7)
        self.assertEqual(len(qc_rows), 1 + len(self.atlas.targets))

    def test_artifact_index_repeats_complete_run_provenance(self) -> None:
        run = self._write()
        with (run.run_dir / "artifact_index.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        first = rows[0]
        self.assertEqual(first["configuration_hash"], self.config.configuration_hash)
        self.assertEqual(first["connectome_identity"], self.adapter.metadata.connectome_identity)
        self.assertEqual(first["ordered_fiber_id_hash"], self.adapter.metadata.ordered_fiber_id_hash)
        self.assertEqual(first["algorithm_version"], "1")
        self.assertEqual(first["fiber_chunk_size"], "2")
        self.assertEqual(first["created_at"], "2026-07-10T12:00:00Z")
        self.assertEqual(json.loads(first["code_provenance_json"]), self.code_provenance)
        source_hashes = json.loads(first["source_file_hashes_json"])
        self.assertEqual(source_hashes["seed"], self.seed.source_hash)
        self.assertEqual(set(source_hashes["targets"]), {target.roi_id for target in self.atlas.targets})
        resolved_hashes = json.loads(first["resolved_mask_hashes_json"])
        self.assertEqual(resolved_hashes["seed"], self.seed.resolved_mask_hash)
        self.assertEqual(resolved_hashes["target_atlas"], self.atlas.atlas_hash)

    def test_collected_code_provenance_uses_repository_git_commit(self) -> None:
        expected = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[5],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        provenance = collect_code_provenance()

        self.assertEqual(provenance["git_commit"], expected)
        self.assertEqual(len(provenance["package_sha256"]), 64)

    def test_membership_artifacts_preserve_canonical_ids_and_target_order(self) -> None:
        run = self._write()
        seed_ids = np.load(run.run_dir / "seed_connected_fiber_ids.npy", allow_pickle=False)
        with np.load(run.run_dir / "target_fiber_membership.npz", allow_pickle=False) as archive:
            target_ids = tuple(str(value) for value in archive["target_ids"].tolist())
            indptr = archive["indptr"]
            fiber_ids = archive["fiber_ids"]

        self.assertEqual(seed_ids.tolist(), self.membership.seed_fiber_ids.tolist())
        self.assertEqual(target_ids, self.membership.target_membership.target_ids)
        self.assertTrue(np.array_equal(indptr, self.membership.target_membership.indptr))
        self.assertTrue(np.array_equal(fiber_ids, self.membership.target_membership.fiber_ids))

    def test_resolved_config_and_ranking_are_deterministic(self) -> None:
        run = self._write()
        config = yaml.safe_load((run.run_dir / "config_resolved.yaml").read_text(encoding="utf-8"))
        with (run.run_dir / "target_ranking.csv").open(newline="", encoding="utf-8") as handle:
            ranking = list(csv.DictReader(handle))

        self.assertEqual(config["schema_version"], 1)
        self.assertEqual([row["target_id"] for row in ranking], ["group/a", "group/b"])
        self.assertEqual([row["rank"] for row in ranking], ["1", "2"])

    def test_unchanged_rerun_reuses_content_without_rewriting(self) -> None:
        first = self._write()
        hashes = artifact_hashes(first.run_dir)
        mtimes = {path.name: path.stat().st_mtime_ns for path in first.run_dir.iterdir()}

        second = self._write(now=self.created_at + timedelta(days=1))

        self.assertEqual(second.run_dir, first.run_dir)
        self.assertTrue(second.reused)
        self.assertEqual(artifact_hashes(second.run_dir), hashes)
        self.assertEqual(
            {path.name: path.stat().st_mtime_ns for path in second.run_dir.iterdir()},
            mtimes,
        )

    def test_stable_input_change_creates_a_different_run_fingerprint(self) -> None:
        first = self._write()
        changed_config = resolve_config(
            {
                "schema_version": 1,
                "execution": {"fiber_chunk_size": 3, "cache_membership": False},
            }
        )
        second = self._write(config=changed_config)

        self.assertNotEqual(first.run_fingerprint, second.run_fingerprint)
        self.assertNotEqual(first.run_dir, second.run_dir)

    def test_incomplete_existing_run_collision_is_rejected(self) -> None:
        fingerprint = build_run_fingerprint(
            config=self.config,
            seed=self.seed,
            atlas=self.atlas,
            connectome_metadata=self.adapter.metadata,
            code_provenance=self.code_provenance,
        )
        collision = self.output_root / "runs" / fingerprint
        collision.mkdir(parents=True)
        (collision / "partial.txt").write_text("partial", encoding="utf-8")

        with self.assertRaisesRegex(ArtifactError, "incomplete"):
            self._write()

    def test_artifact_index_provenance_tampering_is_rejected(self) -> None:
        run = self._write()
        index_path = run.run_dir / "artifact_index.csv"
        with index_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
            fieldnames = tuple(rows[0])
        rows[0]["configuration_hash"] = "0" * 64
        with index_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

        with self.assertRaisesRegex(ArtifactError, "provenance"):
            verify_artifact_index(run.run_dir)


if __name__ == "__main__":
    unittest.main()
