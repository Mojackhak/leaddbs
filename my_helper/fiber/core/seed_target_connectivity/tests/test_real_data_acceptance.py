"""Synthetic and opt-in dTOR acceptance tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

from my_helper.fiber.core.seed_target_connectivity.acceptance import (
    load_acceptance_fixture,
    run_acceptance_fixture,
)
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    line,
    write_hdf5_connectome,
    write_mask,
)


class SyntheticAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        atlas = self.root / "atlas"
        target_a = np.zeros((5, 4, 4), dtype=np.float32)
        target_a[1, 1, 1] = 1
        target_b = np.zeros((5, 4, 4), dtype=np.float32)
        target_b[3, 1, 1] = 1
        seed_a = np.zeros((5, 4, 4), dtype=np.float32)
        seed_a[1, 1, 1] = 1
        seed_b = np.zeros((5, 4, 4), dtype=np.float32)
        seed_b[3, 1, 1] = 1
        write_mask(atlas / "group" / "a.nii.gz", target_a)
        write_mask(atlas / "group" / "b.nii.gz", target_b)
        write_mask(self.root / "seed_a.nii.gz", seed_a)
        write_mask(self.root / "seed_b.nii.gz", seed_b)
        write_hdf5_connectome(
            self.root / "connectome" / "data.mat",
            [
                line((0, 1, 1), (2, 1, 1)),
                line((2.5, 1, 1), (4, 1, 1)),
                line((0, 1, 1), (4, 1, 1)),
                line((0, 3, 3), (1, 3, 3)),
            ],
        )
        self.fixture_path = self.root / "fixture.yaml"
        self.fixture_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "target_atlas_root": "atlas",
                    "seeds": [
                        {"fixture_id": "first", "path": "seed_a.nii.gz"},
                        {"fixture_id": "second", "path": "seed_b.nii.gz"},
                    ],
                    "connectome": "connectome/data.mat",
                    "config": {
                        "schema_version": 1,
                        "execution": {"fiber_chunk_size": 2, "cache_membership": True},
                        "ranking": {"enabled": True},
                    },
                    "sampling": {"seed_connected_per_run": 1, "background_fibers": 1},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_fixture_runs_two_independent_public_api_acceptance_runs(self) -> None:
        fixture = load_acceptance_fixture(self.fixture_path, self.root)

        report = run_acceptance_fixture(fixture, self.root / "output")

        self.assertEqual(report.target_count, 2)
        self.assertEqual([run.fixture_id for run in report.runs], ["first", "second"])
        self.assertTrue(all(run.n_seed_fibers > 0 for run in report.runs))
        self.assertFalse(report.runs[0].target_cache_hit)
        self.assertTrue(report.runs[1].target_cache_hit)
        self.assertGreaterEqual(report.sampled_fiber_count, 2)
        self.assertTrue(report.sampled_kernel_equivalence)
        self.assertTrue(report.identical_rerun_hashes)
        self.assertTrue(report.deterministic_ranks)
        self.assertTrue(report.finite_valid_metrics)
        self.assertTrue(report.source_state_unchanged)
        self.assertTrue((self.root / "output" / "acceptance_report.json").is_file())

    def test_fixture_rejects_unknown_fields(self) -> None:
        document = yaml.safe_load(self.fixture_path.read_text(encoding="utf-8"))
        document["unknown"] = True
        self.fixture_path.write_text(yaml.safe_dump(document), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unknown"):
            load_acceptance_fixture(self.fixture_path, self.root)


@unittest.skipUnless(os.environ.get("RUN_DTOR_ACCEPTANCE") == "1", "full dTOR acceptance is opt-in")
class DTORAcceptanceTests(unittest.TestCase):
    def test_repository_dtor_fixture(self) -> None:
        repo_root = Path(__file__).resolve().parents[5]
        fixture_path = (
            repo_root
            / "my_helper/fiber/core/seed_target_connectivity/tests/fixtures/dtor_stnsnr_acceptance.yaml"
        )
        output_root = Path(
            os.environ.get(
                "DTOR_ACCEPTANCE_OUTPUT_ROOT",
                "/tmp/seed-target-connectivity-dtor-acceptance",
            )
        )
        fixture = load_acceptance_fixture(fixture_path, repo_root)

        report = run_acceptance_fixture(fixture, output_root)

        self.assertEqual(report.target_count, 106)
        self.assertEqual(len(report.runs), 2)
        self.assertTrue(all(run.n_seed_fibers > 0 for run in report.runs))
        self.assertTrue(report.sampled_kernel_equivalence)
        self.assertTrue(report.identical_rerun_hashes)
        self.assertTrue(report.deterministic_ranks)
        self.assertTrue(report.finite_valid_metrics)
        self.assertTrue(report.source_state_unchanged)


if __name__ == "__main__":
    unittest.main()
