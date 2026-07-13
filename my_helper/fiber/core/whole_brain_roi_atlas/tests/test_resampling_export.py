from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np

from my_helper.fiber.core.whole_brain_roi_atlas.config import load_atlas_config
from my_helper.fiber.core.whole_brain_roi_atlas.export import export_binary_rois
from my_helper.fiber.core.whole_brain_roi_atlas.labels import resolve_labels
from my_helper.fiber.core.whole_brain_roi_atlas.resampling import resample_integer_labels


class ResamplingAndExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source_path = self.root / "source.nii.gz"
        self.reference_path = self.root / "reference.nii.gz"
        self.labels_path = self.root / "labels.txt"
        self.connectome_path = self.root / "data.mat"
        data = np.zeros((3, 3, 3), dtype=np.uint16)
        data[0, 1, 1] = 1
        data[1, 1, 1] = 113
        data[0, 0, 0] = 217
        data[2, 0, 0] = 218
        affine = np.eye(4)
        affine[0, 3] = -1.0
        source = nib.Nifti1Image(data, affine)
        source.set_qform(affine, code=1)
        source.set_sform(affine, code=1)
        nib.save(source, self.source_path)
        reference = nib.Nifti1Image(np.zeros_like(data), affine)
        reference.set_qform(affine, code=2)
        reference.set_sform(affine, code=3)
        nib.save(reference, self.reference_path)
        self.labels_path.write_text(
            "1 Precentral_L\n"
            "113 Vermis_1_2\n"
            "217 Anterior_limb_of_internal_capsule_R\n"
            "218 Anterior_limb_of_internal_capsule_L\n",
            encoding="utf-8",
        )
        self.connectome_path.write_bytes(b"fixture")
        config_path = self.root / "config.yaml"
        config_path.write_text(
            f"""schema_version: 1
inputs:
  source_labeling: {self.source_path}
  source_labels: {self.labels_path}
  reference_image: {self.reference_path}
  connectome: {self.connectome_path}
output:
  atlas_root: {self.root / 'atlas'}
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
""",
            encoding="utf-8",
        )
        self.config = load_atlas_config(config_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_resampling_preserves_integer_labels_and_reference_grid(self) -> None:
        source = nib.load(self.source_path)
        reference = nib.load(self.reference_path)
        result = resample_integer_labels(source, reference)

        self.assertEqual(result.shape, reference.shape)
        np.testing.assert_allclose(result.affine, reference.affine)
        np.testing.assert_allclose(result.get_qform(), reference.get_qform())
        np.testing.assert_allclose(result.get_sform(), reference.get_sform())
        self.assertEqual(result.get_qform(coded=True)[1], 2)
        self.assertEqual(result.get_sform(coded=True)[1], 3)
        self.assertEqual(set(np.unique(np.asanyarray(result.dataobj))), {0, 1, 113, 217, 218})

    def test_export_writes_main_and_hidden_white_matter_rois(self) -> None:
        image = nib.load(self.source_path)
        labels = resolve_labels(self.config, image)
        artifacts = export_binary_rois(image, labels, self.root / "staging")

        paths = {item.label_id: item.relative_path for item in artifacts}
        self.assertEqual(paths[1], "lh/Precentral.nii.gz")
        self.assertEqual(paths[113], "midline/Vermis_1_2.nii.gz")
        self.assertEqual(
            paths[217],
            ".qc/white_matter/lh/Anterior_limb_of_internal_capsule.nii.gz",
        )
        self.assertEqual(
            paths[218],
            ".qc/white_matter/rh/Anterior_limb_of_internal_capsule.nii.gz",
        )
        self.assertTrue((self.root / "staging" / "mixed").is_dir())

    def test_exported_masks_are_disjoint_and_reconstruct_labels(self) -> None:
        image = nib.load(self.source_path)
        labels = resolve_labels(self.config, image)
        artifacts = export_binary_rois(image, labels, self.root / "staging")
        reconstructed = np.zeros(image.shape, dtype=np.uint16)
        occupied = np.zeros(image.shape, dtype=bool)
        for item in artifacts:
            mask_image = nib.load(self.root / "staging" / item.relative_path)
            mask = np.asanyarray(mask_image.dataobj).astype(bool)
            self.assertFalse(np.any(occupied & mask))
            occupied |= mask
            reconstructed[mask] = item.label_id
            np.testing.assert_allclose(mask_image.affine, image.affine)
            np.testing.assert_allclose(mask_image.get_qform(), image.get_qform())
            np.testing.assert_allclose(mask_image.get_sform(), image.get_sform())
        np.testing.assert_array_equal(reconstructed, np.asanyarray(image.dataobj))


if __name__ == "__main__":
    unittest.main()
