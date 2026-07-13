"""Atlas discovery and ROI resolution contract tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from my_helper.fiber.core.seed_target_connectivity.atlas import discover_targets
from my_helper.fiber.core.seed_target_connectivity.errors import ROIResolutionError
from my_helper.fiber.core.seed_target_connectivity.roi import resolve_atlas, resolve_seed
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import effective_test_config, write_mask


class AtlasDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_discovers_only_visible_nonroot_niftis_in_stable_order(self) -> None:
        data = np.ones((2, 2, 2), dtype=np.float32)
        write_mask(self.root / "root_helper.nii.gz", data)
        write_mask(self.root / "group_b" / "region.nii", data)
        write_mask(self.root / "group_a" / "region.nii.gz", data)
        write_mask(self.root / "group_a" / "nested" / "deep.nii.gz", data)
        write_mask(self.root / ".hidden" / "secret.nii.gz", data)
        (self.root / "group_a" / "._copy.nii.gz").write_bytes(b"AppleDouble")
        (self.root / "group_a" / "notes.txt").write_text("ignored", encoding="utf-8")
        try:
            os.symlink(self.root, self.root / "group_a" / "cycle")
        except OSError:
            pass

        targets = discover_targets(self.root)

        self.assertEqual(
            [target.target_id for target in targets],
            ["group_a/nested/deep", "group_a/region", "group_b/region"],
        )
        self.assertEqual(
            [target.relative_path for target in targets],
            ["group_a/nested/deep.nii.gz", "group_a/region.nii.gz", "group_b/region.nii"],
        )
        self.assertEqual([target.target_group for target in targets], ["group_a/nested", "group_a", "group_b"])

    def test_requires_existing_directory_and_at_least_one_target(self) -> None:
        with self.assertRaisesRegex(ROIResolutionError, "atlas root"):
            discover_targets(self.root / "missing")
        with self.assertRaisesRegex(ROIResolutionError, "no target NIfTI"):
            discover_targets(self.root)


class ROIResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_binary_seed_uses_positive_voxels_and_records_geometry(self) -> None:
        data = np.zeros((2, 2, 2), dtype=np.float32)
        data[0, 0, 0] = 1.0
        data[1, 1, 1] = 1.0 + 5e-7
        affine = np.diag([2.0, 3.0, 4.0, 1.0])
        path = write_mask(self.root / "seed.nii.gz", data, affine)

        resolved = resolve_seed(path, effective_test_config())

        self.assertEqual(resolved.source_value_type, "binary")
        self.assertIsNone(resolved.probability_threshold)
        self.assertEqual(resolved.threshold_source, "not_applicable")
        self.assertEqual(resolved.voxel_count, 2)
        self.assertAlmostEqual(resolved.physical_volume_mm3, 48.0)
        self.assertEqual(resolved.flat_voxel_indices.tolist(), [0, 7])
        self.assertEqual(len(resolved.source_hash), 64)
        self.assertEqual(len(resolved.resolved_mask_hash), 64)

    def test_probabilistic_seed_requires_explicit_threshold(self) -> None:
        path = write_mask(self.root / "seed.nii.gz", np.array([[[0.0, 0.4, 0.8]]]))

        with self.assertRaisesRegex(ROIResolutionError, "probability threshold"):
            resolve_seed(path, effective_test_config())

        resolved = resolve_seed(
            path,
            effective_test_config(seed={"probability_threshold": 0.5}),
        )
        self.assertEqual(resolved.source_value_type, "probabilistic")
        self.assertEqual(resolved.probability_threshold, 0.5)
        self.assertEqual(resolved.threshold_source, "seed.probability_threshold")
        self.assertEqual(resolved.flat_voxel_indices.tolist(), [2])

    def test_target_override_precedes_default_threshold(self) -> None:
        data = np.array([[[0.2, 0.6, 0.9]]])
        write_mask(self.root / "group" / "override.nii.gz", data)
        write_mask(self.root / "group" / "default.nii.gz", data)
        config = effective_test_config(
                targets={
                    "probability_threshold": 0.5,
                    "roi_thresholds": {"group/override": 0.8},
                }
        )

        atlas = resolve_atlas(self.root, config)
        by_id = {target.roi_id: target for target in atlas.targets}

        self.assertEqual(by_id["group/override"].voxel_count, 1)
        self.assertEqual(by_id["group/override"].threshold_source, "targets.roi_thresholds[group/override]")
        self.assertEqual(by_id["group/default"].voxel_count, 2)
        self.assertEqual(by_id["group/default"].threshold_source, "targets.probability_threshold")

    def test_empty_target_is_recorded_without_aborting_peer_targets(self) -> None:
        write_mask(self.root / "group" / "empty.nii.gz", np.array([[[0.1, 0.2]]]))
        write_mask(self.root / "group" / "valid.nii.gz", np.array([[[0.1, 0.9]]]))
        config = effective_test_config(targets={"probability_threshold": 0.5})

        atlas = resolve_atlas(self.root, config)
        by_id = {target.roi_id: target for target in atlas.targets}

        self.assertEqual(by_id["group/empty"].status, "empty_after_threshold")
        self.assertEqual(by_id["group/empty"].voxel_count, 0)
        self.assertEqual(by_id["group/valid"].status, "valid")
        self.assertEqual(by_id["group/valid"].voxel_count, 1)

    def test_probabilistic_target_without_threshold_fails_validation(self) -> None:
        write_mask(self.root / "group" / "region.nii.gz", np.array([[[0.1, 0.9]]]))
        with self.assertRaisesRegex(ROIResolutionError, "group/region"):
            resolve_atlas(self.root, effective_test_config())

    def test_empty_seed_and_invalid_value_ranges_are_rejected(self) -> None:
        cases = {
            "empty": np.zeros((2, 2, 2)),
            "negative": np.array([[[-0.1, 1.0]]]),
            "above_one": np.array([[[0.0, 1.1]]]),
            "nonfinite": np.array([[[0.0, np.nan]]]),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                path = write_mask(self.root / f"{name}.nii.gz", data)
                with self.assertRaises(ROIResolutionError):
                    resolve_seed(path, effective_test_config())

    def test_resolution_hashes_are_deterministic_and_threshold_sensitive(self) -> None:
        path = write_mask(self.root / "seed.nii.gz", np.array([[[0.1, 0.5, 0.9]]]))
        low_config = effective_test_config(seed={"probability_threshold": 0.4})
        high_config = effective_test_config(seed={"probability_threshold": 0.8})

        first = resolve_seed(path, low_config)
        repeated = resolve_seed(path, low_config)
        changed = resolve_seed(path, high_config)

        self.assertEqual(first.resolved_mask_hash, repeated.resolved_mask_hash)
        self.assertNotEqual(first.resolved_mask_hash, changed.resolved_mask_hash)


if __name__ == "__main__":
    unittest.main()
