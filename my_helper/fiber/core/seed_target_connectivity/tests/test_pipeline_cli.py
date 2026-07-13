"""Single-seed primitives and schema-v2 batch CLI integration tests."""

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
from my_helper.fiber.core.seed_target_connectivity.config import effective_config, resolve_config
from my_helper.fiber.core.seed_target_connectivity.errors import MembershipError
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
        left_seed_data = np.zeros((5, 4, 4), dtype=np.float32)
        left_seed_data[1, 1, 1] = 1
        right_seed_data = np.zeros((5, 4, 4), dtype=np.float32)
        right_seed_data[3, 1, 1] = 1
        write_mask(self.atlas_root / "group" / "a.nii.gz", data_a)
        write_mask(self.atlas_root / "group" / "b.nii.gz", data_b)
        self.left_seed_path = write_mask(self.root / "left_seed.nii.gz", left_seed_data)
        self.right_seed_path = write_mask(self.root / "right_seed.nii.gz", right_seed_data)
        self.streamlines = [
            line((0, 1, 1), (4, 1, 1)),
            line((0, 1, 1), (2, 1, 1)),
            line((2.5, 1, 1), (3.25, 1, 1)),
        ]
        self.batch = resolve_config(
            {
                "schema_version": 2,
                "inputs": {
                    "target_atlas_root": str(self.atlas_root),
                    "seed_rois": {
                        "lh": str(self.left_seed_path),
                        "rh": str(self.right_seed_path),
                    },
                    "connectome": str(self.root / "connectome"),
                },
                "output": {
                    "output_root": str(self.root / "results"),
                    "run_name": "bilateral",
                    "cache_root": str(self.root / ".cache"),
                },
                "execution": {"fiber_chunk_size": 2, "cache_membership": True},
            }
        )
        self.left_config = effective_config(self.batch, "lh")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_validate_resolves_inputs_without_iterating_connectome(self) -> None:
        adapter = RecordingAdapter(self.streamlines)

        report = validate_inputs(
            target_atlas_root=self.atlas_root,
            seed_roi=self.left_seed_path,
            connectome=adapter,
            config=self.left_config,
        )

        self.assertEqual(report.n_targets, 2)
        self.assertEqual(report.n_valid_targets, 2)
        self.assertEqual(report.seed_voxel_count, 1)
        self.assertEqual(report.connectome_metadata.n_fibers, 3)
        self.assertEqual(adapter.iteration_count, 0)

    def test_validate_batch_resolves_both_seeds_without_iteration(self) -> None:
        adapter = RecordingAdapter(self.streamlines)
        validator = getattr(pipeline, "validate_batch", None)
        if validator is None:
            self.fail("validate_batch must validate every named seed")

        report = validator(self.batch, connectome_override=adapter)

        self.assertEqual(tuple(report.seeds), ("lh", "rh"))
        self.assertEqual(report.seeds["lh"].n_targets, 2)
        self.assertEqual(report.seeds["rh"].n_targets, 2)
        self.assertEqual(
            report.seeds["lh"].connectome_metadata.connectome_identity,
            report.seeds["rh"].connectome_metadata.connectome_identity,
        )
        self.assertEqual(adapter.iteration_count, 0)

    def test_single_seed_primitive_computes_legacy_inspectable_run(self) -> None:
        result = compute_seed_target_statistics(
            target_atlas_root=self.atlas_root,
            seed_roi=self.left_seed_path,
            connectome=RecordingAdapter(self.streamlines),
            config=self.left_config,
            output_root=self.root / "legacy-output",
            code_provenance={"git_commit": "1" * 40, "package_sha256": "2" * 64},
        )

        self.assertEqual([row.target_id for row in result.statistics], ["group/a", "group/b"])
        self.assertTrue(result.artifacts.run_dir.is_dir())
        self.assertEqual(inspect_run_status(result.artifacts.run_dir)["status"], "complete")
        self.assertEqual(len(list_run_artifacts(result.artifacts.run_dir)), 9)

    def test_resolution_cache_reuses_unchanged_atlas_across_effective_configs(self) -> None:
        cache = ResolutionCache()
        with patch.object(pipeline, "resolve_atlas", wraps=pipeline.resolve_atlas) as resolved:
            validate_inputs(
                target_atlas_root=self.atlas_root,
                seed_roi=self.left_seed_path,
                connectome=RecordingAdapter(self.streamlines),
                config=self.left_config,
                resolution_cache=cache,
            )
            validate_inputs(
                target_atlas_root=self.atlas_root,
                seed_roi=self.right_seed_path,
                connectome=RecordingAdapter(self.streamlines),
                config=effective_config(self.batch, "rh"),
                resolution_cache=cache,
            )

        self.assertEqual(resolved.call_count, 1)

    def test_compute_batch_publishes_both_sides_and_reuses_target_cache(self) -> None:
        runner = getattr(pipeline, "compute_seed_target_batch", None)
        if runner is None:
            self.fail("compute_seed_target_batch must run every named seed")
        adapter = RecordingAdapter(self.streamlines)
        provenance = {"git_commit": "1" * 40, "package_sha256": "2" * 64}

        first = runner(
            self.batch,
            connectome_override=adapter,
            code_provenance=provenance,
            trash=lambda path: None,
        )

        self.assertEqual(tuple(first.results), ("lh", "rh"))
        self.assertEqual(first.results["lh"].artifacts.run_dir, self.batch.output.output_root / "lh" / "bilateral")
        self.assertEqual(first.results["rh"].artifacts.run_dir, self.batch.output.output_root / "rh" / "bilateral")
        self.assertTrue(first.results["rh"].membership.target_cache_hit)
        self.assertEqual(adapter.iteration_count, 2)

        second_adapter = RecordingAdapter(self.streamlines)
        second = runner(
            self.batch,
            connectome_override=second_adapter,
            code_provenance=provenance,
            trash=lambda path: None,
        )

        self.assertTrue(all(result.artifacts.reused for result in second.results.values()))
        self.assertEqual(second_adapter.iteration_count, 0)

    def test_second_seed_computation_failure_publishes_neither_side(self) -> None:
        runner = getattr(pipeline, "compute_seed_target_batch", None)
        if runner is None:
            self.fail("compute_seed_target_batch must run every named seed")
        original = pipeline.compute_memberships
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MembershipError("injected second-seed failure")
            return original(*args, **kwargs)

        with patch.object(pipeline, "compute_memberships", side_effect=fail_second):
            with self.assertRaisesRegex(MembershipError, "second-seed"):
                runner(
                    self.batch,
                    connectome_override=RecordingAdapter(self.streamlines),
                    code_provenance={"git_commit": "1" * 40, "package_sha256": "2" * 64},
                    trash=lambda path: None,
                )

        self.assertFalse((self.batch.output.output_root / "lh" / "bilateral").exists())
        self.assertFalse((self.batch.output.output_root / "rh" / "bilateral").exists())


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repo_root = Path(__file__).resolve().parents[5]
        self.script = self.repo_root / "my_helper" / "fiber" / "pipelines" / "seed-target-connectivity"
        self.atlas_root = self.root / "atlas"
        target = np.zeros((5, 4, 4), dtype=np.float32)
        target[1, 1, 1] = 1
        left_seed = np.zeros((5, 4, 4), dtype=np.float32)
        left_seed[1, 1, 1] = 1
        right_seed = np.zeros((5, 4, 4), dtype=np.float32)
        right_seed[3, 1, 1] = 1
        write_mask(self.atlas_root / "group" / "target.nii.gz", target)
        self.left_seed_path = write_mask(self.root / "left_seed.nii.gz", left_seed)
        self.right_seed_path = write_mask(self.root / "right_seed.nii.gz", right_seed)
        self.connectome_path = write_hdf5_connectome(
            self.root / "connectome" / "data.mat",
            [line((0, 1, 1), (4, 1, 1)), line((0, 3, 3), (1, 3, 3))],
        )
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            f"""schema_version: 2
inputs:
  target_atlas_root: {self.atlas_root}
  seed_rois:
    lh: {self.left_seed_path}
    rh: {self.right_seed_path}
  connectome: {self.connectome_path.parent}
output:
  output_root: {self.root / 'results'}
  run_name: bilateral
  cache_root: {self.root / '.cache'}
execution:
  fiber_chunk_size: 1
  cache_membership: true
ranking:
  enabled: true
""",
            encoding="utf-8",
        )

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

    def test_validate_accepts_only_yaml_and_returns_named_seed_reports(self) -> None:
        validated = self._run("validate", "--config", str(self.config_path))

        self.assertEqual(validated.returncode, 0, validated.stderr)
        payload = json.loads(validated.stdout)
        self.assertEqual(tuple(payload["seeds"]), ("lh", "rh"))
        self.assertEqual(payload["seeds"]["lh"]["n_targets"], 1)
        self.assertEqual(payload["seeds"]["rh"]["n_targets"], 1)

    def test_removed_path_flags_are_rejected_by_argparse(self) -> None:
        completed = self._run(
            "validate",
            "--config",
            str(self.config_path),
            "--seed-roi",
            str(self.left_seed_path),
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("unrecognized arguments", completed.stderr)

    def test_run_help_does_not_offer_resume_or_force(self) -> None:
        completed = self._run("run", "--help")

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("--resume", completed.stdout)
        self.assertNotIn("--force", completed.stdout)

    def test_run_publishes_and_reuses_named_semantic_results(self) -> None:
        first = self._run("run", "--config", str(self.config_path))

        self.assertEqual(first.returncode, 0, first.stderr)
        first_payload = json.loads(first.stdout)
        self.assertEqual(tuple(first_payload["results"]), ("lh", "rh"))
        for name in ("lh", "rh"):
            result = first_payload["results"][name]
            self.assertEqual(Path(result["run_dir"]).name, "bilateral")
            self.assertEqual(Path(result["run_dir"]).parent.name, name)
            self.assertFalse(result["reused"])

        second = self._run("run", "--config", str(self.config_path))

        self.assertEqual(second.returncode, 0, second.stderr)
        second_payload = json.loads(second.stdout)
        self.assertTrue(all(row["reused"] for row in second_payload["results"].values()))

    def test_status_and_artifacts_remain_run_directory_inspection_commands(self) -> None:
        batch = resolve_config(json.loads(json.dumps({
            "schema_version": 2,
            "inputs": {
                "target_atlas_root": str(self.atlas_root),
                "seed_rois": {"lh": str(self.left_seed_path)},
                "connectome": str(self.connectome_path.parent),
            },
            "output": {"output_root": str(self.root / "unused"), "run_name": "legacy"},
            "execution": {"fiber_chunk_size": 1, "cache_membership": True},
        })))
        result = compute_seed_target_statistics(
            target_atlas_root=self.atlas_root,
            seed_roi=self.left_seed_path,
            connectome=self.connectome_path.parent,
            config=effective_config(batch, "lh"),
            output_root=self.root / "legacy-output",
            code_provenance={"git_commit": "1" * 40, "package_sha256": "2" * 64},
        )

        status = self._run("status", "--run-dir", str(result.artifacts.run_dir))
        artifacts = self._run("artifacts", "--run-dir", str(result.artifacts.run_dir))

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["status"], "complete")
        self.assertEqual(artifacts.returncode, 0, artifacts.stderr)
        self.assertEqual(len(json.loads(artifacts.stdout)["artifacts"]), 9)


if __name__ == "__main__":
    unittest.main()
