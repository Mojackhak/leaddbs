from __future__ import annotations

import unittest
from pathlib import Path

import nibabel as nib

from my_helper.fiber.core.whole_brain_roi_atlas.config import load_atlas_config
from my_helper.fiber.core.whole_brain_roi_atlas.labels import resolve_labels


REPO_ROOT = Path(__file__).resolve().parents[5]
CONFIG = REPO_ROOT / "my_helper" / "fiber" / "configs" / "dtor_hybrapd_whole_brain.yaml"


class RepositoryConfigTests(unittest.TestCase):
    def test_hybrapd_categories_and_main_roi_sides_are_complete(self) -> None:
        config = load_atlas_config(CONFIG)
        labels = resolve_labels(config, nib.load(config.source_labeling))

        self.assertEqual(config.atlas_root.name, "HybraPD Whole Brain (Yu 2021)")
        self.assertEqual(len(labels), 198)
        self.assertEqual(len(config.categories.cortical_limbic), 90)
        self.assertEqual(len(config.categories.cerebellar_hemisphere), 18)
        self.assertEqual(len(config.categories.cerebellar_midline), 8)
        self.assertEqual(len(config.categories.subcortical), 34)
        self.assertEqual(len(config.categories.white_matter), 48)
        main = [item for item in labels if item.include_in_region_ranking]
        self.assertEqual(sum(item.hemisphere == "L" for item in main), 71)
        self.assertEqual(sum(item.hemisphere == "R" for item in main), 71)
        self.assertEqual(sum(item.hemisphere == "M" for item in main), 8)
        self.assertEqual(sum(item.laterality_corrected for item in labels), 42)


if __name__ == "__main__":
    unittest.main()
