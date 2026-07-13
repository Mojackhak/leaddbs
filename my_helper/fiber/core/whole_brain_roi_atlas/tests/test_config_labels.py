from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np

from my_helper.fiber.core.whole_brain_roi_atlas.config import load_atlas_config
from my_helper.fiber.core.whole_brain_roi_atlas.errors import ConfigurationError, LabelError
from my_helper.fiber.core.whole_brain_roi_atlas.labels import (
    parse_label_table,
    resolve_labels,
)


class ConfigAndLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.nii.gz"
        self.reference = self.root / "reference.nii.gz"
        self.labels = self.root / "labels.txt"
        self.connectome = self.root / "data.mat"
        self.output = self.root / "atlas"
        data = np.zeros((3, 3, 3), dtype=np.uint16)
        data[0, 1, 1] = 1
        data[1, 1, 1] = 113
        data[0, 0, 0] = 217
        data[2, 0, 0] = 218
        affine = np.eye(4)
        affine[0, 3] = -1.0
        nib.save(nib.Nifti1Image(data, affine), self.source)
        nib.save(nib.Nifti1Image(np.zeros_like(data), affine), self.reference)
        self.labels.write_text(
            "1 Precentral_L\n"
            "113 Vermis_1_2\n"
            "217 Anterior_limb_of_internal_capsule_R\n"
            "218 Anterior_limb_of_internal_capsule_L\n",
            encoding="utf-8",
        )
        self.connectome.write_bytes(b"fixture")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_config(self, extra: str = "") -> Path:
        path = self.root / "config.yaml"
        path.write_text(
            f"""schema_version: 1
inputs:
  source_labeling: {self.source}
  source_labels: {self.labels}
  reference_image: {self.reference}
  connectome: {self.connectome}
output:
  atlas_root: {self.output}
labels:
  cortical_limbic: [1]
  cerebellar_hemisphere: []
  cerebellar_midline: [113]
  subcortical: []
  white_matter: [217, 218]
expected:
  label_count: 4
  fiber_count: 2
execution:
  fiber_chunk_size: 2
{extra}""",
            encoding="utf-8",
        )
        return path

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        path = self.write_config("execution:\n  fiber_chunk_size: 3\n")
        with self.assertRaisesRegex(ConfigurationError, "duplicate key"):
            load_atlas_config(path)

    def test_unknown_config_field_is_rejected(self) -> None:
        path = self.write_config("unexpected: true\n")
        with self.assertRaisesRegex(ConfigurationError, "unexpected"):
            load_atlas_config(path)

    def test_category_partition_must_cover_source_labels(self) -> None:
        path = self.write_config().read_text(encoding="utf-8").replace(
            "white_matter: [217, 218]", "white_matter: [217]"
        ).replace("label_count: 4", "label_count: 3")
        config_path = self.root / "invalid.yaml"
        config_path.write_text(path, encoding="utf-8")
        config = load_atlas_config(config_path)
        with self.assertRaisesRegex(LabelError, "partition"):
            resolve_labels(config, nib.load(self.source))

    def test_label_table_rejects_duplicate_ids(self) -> None:
        self.labels.write_text("1 First_L\n1 Second_L\n", encoding="utf-8")
        with self.assertRaisesRegex(LabelError, "duplicate label ID 1"):
            parse_label_table(self.labels)

    def test_white_matter_laterality_is_resolved_from_mni_centroid(self) -> None:
        config = load_atlas_config(self.write_config())
        resolved = {item.label_id: item for item in resolve_labels(config, nib.load(self.source))}

        self.assertEqual(resolved[1].hemisphere, "L")
        self.assertFalse(resolved[1].laterality_corrected)
        self.assertEqual(resolved[113].hemisphere, "M")
        self.assertEqual(resolved[217].hemisphere, "L")
        self.assertEqual(
            resolved[217].resolved_label_name,
            "Anterior_limb_of_internal_capsule_L",
        )
        self.assertTrue(resolved[217].laterality_corrected)
        self.assertEqual(resolved[218].hemisphere, "R")
        self.assertEqual(resolved[218].paired_filename, "Anterior_limb_of_internal_capsule.nii.gz")

    def test_repeated_white_matter_names_get_stable_pair_suffixes(self) -> None:
        data = np.zeros((2, 2, 2), dtype=np.uint16)
        data[0, 0, 0] = 235
        data[1, 0, 0] = 236
        data[0, 1, 0] = 237
        data[1, 1, 0] = 238
        affine = np.eye(4)
        affine[0, 3] = -0.5
        nib.save(nib.Nifti1Image(data, affine), self.source)
        self.labels.write_text(
            "235 Cingulum_R\n236 Cingulum_L\n237 Cingulum_R\n238 Cingulum_L\n",
            encoding="utf-8",
        )
        path = self.root / "repeated.yaml"
        path.write_text(
            f"""schema_version: 1
inputs:
  source_labeling: {self.source}
  source_labels: {self.labels}
  reference_image: {self.reference}
  connectome: {self.connectome}
output:
  atlas_root: {self.output}
labels:
  cortical_limbic: []
  cerebellar_hemisphere: []
  cerebellar_midline: []
  subcortical: []
  white_matter: [235, 236, 237, 238]
expected:
  label_count: 4
  fiber_count: 2
""",
            encoding="utf-8",
        )
        resolved = {item.label_id: item for item in resolve_labels(load_atlas_config(path), nib.load(self.source))}

        self.assertEqual(resolved[235].paired_filename, "Cingulum__pair-1.nii.gz")
        self.assertEqual(resolved[236].paired_filename, "Cingulum__pair-1.nii.gz")
        self.assertEqual(resolved[237].paired_filename, "Cingulum__pair-2.nii.gz")
        self.assertEqual(resolved[238].paired_filename, "Cingulum__pair-2.nii.gz")


if __name__ == "__main__":
    unittest.main()
