"""Semantic batch artifact, provenance, replacement, and rollback tests."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from my_helper.fiber.core.seed_target_connectivity import artifacts
from my_helper.fiber.core.seed_target_connectivity.config import effective_config, resolve_config
from my_helper.fiber.core.seed_target_connectivity.engine import compute_memberships
from my_helper.fiber.core.seed_target_connectivity.errors import ArtifactError
from my_helper.fiber.core.seed_target_connectivity.statistics import compute_statistics
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    RecordingAdapter,
    line,
    resolved_atlas,
    resolved_mask,
)


CURRENT_ARTIFACTS = {
    "config_resolved.yaml",
    "target_catalog.csv",
    "target_connectivity.csv",
    "target_ranking.csv",
    "seed_connected_fiber_ids.npy",
    "target_fiber_membership.npz",
    "input_resolution_qc.csv",
    "provenance.json",
    "artifact_index.csv",
}


class BatchArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_root = self.root / "results"
        self.batch = self._batch()
        self.atlas = resolved_atlas(
            [
                resolved_mask([(1, 1, 1)], roi_id="group/a"),
                resolved_mask([(3, 1, 1)], roi_id="group/b"),
            ]
        )
        self.seeds = {
            "lh": resolved_mask([(1, 1, 1)], roi_id="lh", role="seed"),
            "rh": resolved_mask([(3, 1, 1)], roi_id="rh", role="seed"),
        }
        self.adapter = RecordingAdapter(
            [
                line((0, 1, 1), (4, 1, 1)),
                line((0, 1, 1), (2, 1, 1)),
                line((2.5, 1, 1), (3.25, 1, 1)),
            ]
        )
        self.code_provenance = {
            "git_commit": "1" * 40,
            "package_sha256": "2" * 64,
        }
        self.created_at = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _batch(self, *, right_seed: str = "right.nii.gz", chunk_size: int = 2):
        return resolve_config(
            {
                "schema_version": 2,
                "inputs": {
                    "target_atlas_root": str(self.root / "atlas"),
                    "seed_rois": {
                        "lh": str(self.root / "left.nii.gz"),
                        "rh": str(self.root / right_seed),
                    },
                    "connectome": str(self.root / "connectome"),
                },
                "output": {
                    "output_root": str(self.output_root),
                    "run_name": "dTOR__HybraPD__STNSNrplus",
                    "cache_root": str(self.root / ".cache"),
                },
                "execution": {"fiber_chunk_size": chunk_size, "cache_membership": False},
            }
        )

    def _stage(self, seed_name: str, *, batch=None, code_provenance=None):
        stage = getattr(artifacts, "stage_run_artifacts", None)
        if stage is None:
            self.fail("stage_run_artifacts must create semantic version-2 artifacts")
        selected_batch = self.batch if batch is None else batch
        effective = effective_config(selected_batch, seed_name)
        membership = compute_memberships(
            self.adapter,
            self.seeds[seed_name],
            self.atlas,
            effective,
        )
        statistics = compute_statistics(membership, self.atlas, ranking_enabled=True)
        return stage(
            batch=selected_batch,
            config=effective,
            seed=self.seeds[seed_name],
            atlas=self.atlas,
            connectome_metadata=self.adapter.metadata,
            membership=membership,
            statistics=statistics,
            code_provenance=self.code_provenance if code_provenance is None else code_provenance,
            now=self.created_at,
        )

    def _publish(self, staged, *, trash=None, replace=os.replace):
        publish = getattr(artifacts, "publish_staged_batch", None)
        if publish is None:
            self.fail("publish_staged_batch must publish all staged seeds transactionally")
        return publish(
            staged,
            trash=(lambda path: None) if trash is None else trash,
            replace=replace,
        )

    def test_stage_writes_provenance_and_human_readable_final_path(self) -> None:
        staged = self._stage("lh")

        self.assertFalse(staged.reused)
        self.assertEqual(
            staged.final_dir,
            self.batch.output.output_root / "lh" / "dTOR__HybraPD__STNSNrplus",
        )
        self.assertIsNotNone(staged.staging_dir)
        self.assertEqual({path.name for path in staged.staging_dir.iterdir()}, CURRENT_ARTIFACTS)
        self.assertFalse((staged.staging_dir / "analysis_manifest.json").exists())
        provenance = json.loads((staged.staging_dir / "provenance.json").read_text(encoding="utf-8"))
        effective = effective_config(self.batch, "lh")
        self.assertEqual(provenance["batch_configuration_hash"], self.batch.batch_configuration_hash)
        self.assertEqual(provenance["effective_configuration_hash"], effective.configuration_hash)
        self.assertEqual(provenance["run_fingerprint"], staged.run_fingerprint)
        self.assertEqual(provenance["seed_name"], "lh")
        self.assertEqual(artifacts.verify_artifact_index(staged.staging_dir), dict(staged.artifact_hashes))

    def test_stage_ignores_exfat_appledouble_sidecars(self) -> None:
        original = artifacts._write_primary_artifacts

        def write_with_sidecar(staging, **kwargs):
            hashes = original(staging, **kwargs)
            (staging / "._config_resolved.yaml").write_bytes(b"filesystem metadata")
            return hashes

        with patch.object(artifacts, "_write_primary_artifacts", side_effect=write_with_sidecar):
            staged = self._stage("lh")

        self.assertTrue((staged.staging_dir / "._config_resolved.yaml").is_file())
        self.assertNotIn("._config_resolved.yaml", staged.artifact_hashes)
        self.assertEqual(
            artifacts.verify_artifact_index(staged.staging_dir),
            dict(staged.artifact_hashes),
        )

    def test_matching_result_is_reused_without_rewriting(self) -> None:
        first = self._stage("lh")
        published = self._publish({"lh": first})["lh"]
        mtimes = {path.name: path.stat().st_mtime_ns for path in published.run_dir.iterdir()}

        second = self._stage("lh")
        reused = self._publish({"lh": second})["lh"]

        self.assertTrue(second.reused)
        self.assertTrue(reused.reused)
        self.assertIsNone(second.staging_dir)
        self.assertEqual(
            {path.name: path.stat().st_mtime_ns for path in reused.run_dir.iterdir()},
            mtimes,
        )

    def test_sibling_seed_change_refreshes_batch_provenance_without_changing_fingerprint(self) -> None:
        first = self._stage("lh")
        self._publish({"lh": first})
        changed_batch = self._batch(right_seed="changed-right.nii.gz")

        refreshed = self._stage("lh", batch=changed_batch)

        self.assertFalse(refreshed.reused)
        self.assertEqual(refreshed.run_fingerprint, first.run_fingerprint)
        provenance = json.loads((refreshed.staging_dir / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["batch_configuration_hash"], changed_batch.batch_configuration_hash)

    def test_unrelated_existing_directory_is_not_replaced(self) -> None:
        final = self.output_root / "lh" / "dTOR__HybraPD__STNSNrplus"
        final.mkdir(parents=True)
        (final / "user.txt").write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(ArtifactError, "tool-owned"):
            self._stage("lh")

        self.assertEqual((final / "user.txt").read_text(encoding="utf-8"), "keep")

    def test_replacement_moves_prior_result_to_trash_after_success(self) -> None:
        first = self._stage("lh")
        self._publish({"lh": first})
        changed = self._stage("lh", code_provenance={**self.code_provenance, "git_commit": "3" * 40})
        trashed: list[Path] = []

        def trash(path: Path) -> None:
            trashed.append(path)
            destination = self.root / "trash" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))

        published = self._publish({"lh": changed}, trash=trash)["lh"]

        self.assertEqual(len(trashed), 1)
        self.assertTrue(published.run_dir.is_dir())
        self.assertEqual(
            json.loads((published.run_dir / "provenance.json").read_text())["run_fingerprint"],
            changed.run_fingerprint,
        )

    def test_second_side_publication_failure_restores_both_prior_results(self) -> None:
        initial = {name: self._stage(name) for name in ("lh", "rh")}
        initial_published = self._publish(initial)
        old_fingerprints = {
            name: result.run_fingerprint for name, result in initial_published.items()
        }
        changed_code = {**self.code_provenance, "git_commit": "4" * 40}
        changed = {
            name: self._stage(name, code_provenance=changed_code)
            for name in ("lh", "rh")
        }
        right_final = changed["rh"].final_dir

        def failing_replace(source, destination) -> None:
            source_path = Path(source)
            destination_path = Path(destination)
            if ".staging" in source_path.name and destination_path == right_final:
                raise OSError("injected second-side publication failure")
            os.replace(source, destination)

        with self.assertRaisesRegex(ArtifactError, "injected second-side"):
            self._publish(changed, replace=failing_replace)

        for name in ("lh", "rh"):
            final = self.output_root / name / "dTOR__HybraPD__STNSNrplus"
            self.assertTrue(final.is_dir())
            provenance = json.loads((final / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["run_fingerprint"], old_fingerprints[name])


if __name__ == "__main__":
    unittest.main()
