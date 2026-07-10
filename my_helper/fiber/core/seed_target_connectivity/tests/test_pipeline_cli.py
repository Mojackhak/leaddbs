"""Reusable API and four-command CLI integration tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from my_helper.fiber.core.seed_target_connectivity import compute_seed_target_statistics
from my_helper.fiber.core.seed_target_connectivity.config import resolve_config
from my_helper.fiber.core.seed_target_connectivity.pipeline import (
    ResolutionCache,
    inspect_run_status,
    list_run_artifacts,
    validate_inputs,
)
from my_helper.fiber.core.seed_target_connectivity import pipeline
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    RecordingAdapter,
    line,
    write_hdf5_connectome,
    write_mask,
)


class PipelineAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.atlas_root = self.root / "atlas"
        data_a = np.zeros((5, 4, 4), dtype=np.float32)
        data_a[1, 1, 1] = 1
        data_b = np.zeros((5, 4, 4), dtype=np.float32)
        data_b[3, 1, 1] = 1
        seed_data = np.zeros((5, 4, 4), dtype=np.float32)
        seed_data[1, 1, 1] = 1
        write_mask(self.atlas_root / "group" / "a.nii.gz", data_a)
        write_mask(self.atlas_root / "group" / "b.nii.gz", data_b)
        self.seed_path = write_mask(self.root / "seed.nii.gz", seed_data)
        self.streamlines = [
            line((0, 1, 1), (4, 1, 1)),
            line((0, 1, 1), (2, 1, 1)),
            line((2.5, 1, 1), (3.25, 1, 1)),
        ]
        self.config = resolve_config(
            {
                "schema_version": 1,
                "execution": {"fiber_chunk_size": 2, "cache_membership": True},
            }
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_validate_resolves_inputs_without_iterating_connectome(self) -> None:
        adapter = RecordingAdapter(self.streamlines)

        report = validate_inputs(
            target_atlas_root=self.atlas_root,
            seed_roi=self.seed_path,
            connectome=adapter,
            config=self.config,
        )

        self.assertEqual(report.n_targets, 2)
        self.assertEqual(report.n_valid_targets, 2)
        self.assertEqual(report.seed_voxel_count, 1)
        self.assertEqual(report.connectome_metadata.n_fibers, 3)
        self.assertEqual(adapter.iteration_count, 0)

    def test_public_api_computes_statistics_and_immutable_run(self) -> None:
        result = compute_seed_target_statistics(
            target_atlas_root=self.atlas_root,
            seed_roi=self.seed_path,
            connectome=RecordingAdapter(self.streamlines),
            config=self.config,
            output_root=self.root / "output",
            code_provenance={"git_commit": "1" * 40, "package_sha256": "2" * 64},
        )

        self.assertEqual([row.target_id for row in result.statistics], ["group/a", "group/b"])
        self.assertTrue(result.artifacts.run_dir.is_dir())
        self.assertEqual(inspect_run_status(result.artifacts.run_dir)["status"], "complete")
        self.assertEqual(len(list_run_artifacts(result.artifacts.run_dir)), 9)
        self.assertTrue((self.root / "output" / "membership_cache").is_dir())

    def test_resolution_cache_reuses_unchanged_atlas_across_public_calls(self) -> None:
        second_seed = self.root / "second_seed.nii.gz"
        second_seed.write_bytes(self.seed_path.read_bytes())
        cache = ResolutionCache()
        with patch.object(pipeline, "resolve_atlas", wraps=pipeline.resolve_atlas) as resolved:
            validate_inputs(
                target_atlas_root=self.atlas_root,
                seed_roi=self.seed_path,
                connectome=RecordingAdapter(self.streamlines),
                config=self.config,
                resolution_cache=cache,
            )
            validate_inputs(
                target_atlas_root=self.atlas_root,
                seed_roi=second_seed,
                connectome=RecordingAdapter(self.streamlines),
                config=self.config,
                resolution_cache=cache,
            )

        self.assertEqual(resolved.call_count, 1)


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repo_root = Path(__file__).resolve().parents[5]
        self.script = self.repo_root / "my_helper" / "fiber" / "pipelines" / "seed-target-connectivity"
        self.atlas_root = self.root / "atlas"
        target = np.zeros((5, 4, 4), dtype=np.float32)
        target[1, 1, 1] = 1
        seed = np.zeros((5, 4, 4), dtype=np.float32)
        seed[1, 1, 1] = 1
        write_mask(self.atlas_root / "group" / "target.nii.gz", target)
        self.seed_path = write_mask(self.root / "seed.nii.gz", seed)
        self.connectome_path = write_hdf5_connectome(
            self.root / "connectome" / "data.mat",
            [line((0, 1, 1), (2, 1, 1)), line((0, 3, 3), (1, 3, 3))],
        )
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            "schema_version: 1\nexecution:\n  fiber_chunk_size: 1\n  cache_membership: true\n",
            encoding="utf-8",
        )
        self.output_root = self.root / "output"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), *arguments],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def _scientific_arguments(self) -> list[str]:
        return [
            "--target-atlas-root",
            str(self.atlas_root),
            "--seed-roi",
            str(self.seed_path),
            "--connectome",
            str(self.connectome_path.parent),
            "--config",
            str(self.config_path),
        ]

    def test_validate_run_status_and_artifacts_commands(self) -> None:
        validated = self._run("validate", *self._scientific_arguments())
        self.assertEqual(validated.returncode, 0, validated.stderr)
        validation_payload = json.loads(validated.stdout)
        self.assertEqual(validation_payload["n_targets"], 1)
        self.assertFalse(self.output_root.exists())

        completed = self._run(
            "run",
            *self._scientific_arguments(),
            "--output-root",
            str(self.output_root),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        run_payload = json.loads(completed.stdout)
        run_dir = Path(run_payload["run_dir"])
        self.assertTrue(run_dir.is_dir())

        status = self._run("status", "--run-dir", str(run_dir))
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["status"], "complete")

        artifacts = self._run("artifacts", "--run-dir", str(run_dir))
        self.assertEqual(artifacts.returncode, 0, artifacts.stderr)
        self.assertEqual(len(json.loads(artifacts.stdout)["artifacts"]), 9)

    def test_validation_error_returns_exit_code_one_and_json_error(self) -> None:
        probabilistic = np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32)
        write_mask(self.atlas_root / "group" / "target.nii.gz", probabilistic)

        completed = self._run("validate", *self._scientific_arguments())

        self.assertEqual(completed.returncode, 1)
        error = json.loads(completed.stderr)
        self.assertEqual(error["status"], "error")
        self.assertIn("probability threshold", error["error"])

    def test_status_detects_artifact_tampering(self) -> None:
        completed = self._run(
            "run",
            *self._scientific_arguments(),
            "--output-root",
            str(self.output_root),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        run_dir = Path(json.loads(completed.stdout)["run_dir"])
        (run_dir / "target_connectivity.csv").write_text("tampered\n", encoding="utf-8")

        status = self._run("status", "--run-dir", str(run_dir))

        self.assertEqual(status.returncode, 1)
        self.assertIn("hash mismatch", json.loads(status.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
