from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np

from my_helper.fiber.core.whole_brain_roi_atlas.cli import main
from my_helper.fiber.core.whole_brain_roi_atlas.config import load_atlas_config
from my_helper.fiber.core.whole_brain_roi_atlas.errors import PublicationError
from my_helper.fiber.core.whole_brain_roi_atlas.pipeline import (
    build_whole_brain_roi_atlas,
    inspect_atlas_status,
)


class PipelineAndCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.nii.gz"
        self.reference = self.root / "reference.nii.gz"
        self.labels = self.root / "labels.txt"
        self.connectome = self.root / "data.mat"
        self.atlas_root = self.root / "atlas"
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
        points = np.asarray(
            [
                [0, 1, 1, 1],
                [1, 1, 1, 1],
                [-1, 0, 0, 2],
                [1, 0, 0, 2],
            ],
            dtype=np.float32,
        )
        with h5py.File(self.connectome, "w") as handle:
            handle.create_dataset("idx", data=np.asarray([[2, 2]], dtype=np.float64))
            handle.create_dataset("fibers", data=points.T)
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            f"""schema_version: 1
inputs:
  source_labeling: {self.source}
  source_labels: {self.labels}
  reference_image: {self.reference}
  connectome: {self.connectome}
output:
  atlas_root: {self.atlas_root}
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
  fiber_chunk_size: 1
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_build_publishes_complete_deterministic_atlas(self) -> None:
        config = load_atlas_config(self.config_path)
        first = build_whole_brain_roi_atlas(config)
        second = build_whole_brain_roi_atlas(config)

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.build_fingerprint, second.build_fingerprint)
        self.assertEqual(first.label_count, 4)
        self.assertEqual(first.main_roi_count, 2)
        self.assertEqual(first.white_matter_roi_count, 2)
        required = {
            "labels.nii.gz",
            "labels.txt",
            "labels_source.txt",
            "region_manifest.csv",
            "region_manifest.json",
            "dtor_endpoint_qc.csv",
            "build_manifest.json",
            "artifact_index.csv",
            "config_resolved.yaml",
            "README.md",
        }
        self.assertTrue(required.issubset({path.name for path in self.atlas_root.iterdir()}))
        readme = (self.atlas_root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# HybraPD Whole-Brain ROI Atlas\n"))
        for name in (
            "Precentral_L",
            "Vermis_1_2",
            "Anterior_limb_of_internal_capsule_L",
            "Anterior_limb_of_internal_capsule_R",
        ):
            self.assertIn(name, readme)
        self.assertEqual(inspect_atlas_status(self.atlas_root)["status"], "complete")

    def test_mismatched_existing_output_is_not_overwritten(self) -> None:
        config = load_atlas_config(self.config_path)
        build_whole_brain_roi_atlas(config)
        original = (self.atlas_root / "build_manifest.json").read_bytes()
        self.labels.write_text(self.labels.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        with self.assertRaisesRegex(PublicationError, "different build fingerprint"):
            build_whole_brain_roi_atlas(config)
        self.assertEqual((self.atlas_root / "build_manifest.json").read_bytes(), original)

    def test_cli_validate_build_and_status_emit_json(self) -> None:
        for arguments in (
            ["validate", "--config", str(self.config_path)],
            ["build", "--config", str(self.config_path)],
            ["status", "--atlas-root", str(self.atlas_root)],
        ):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(arguments)
            self.assertEqual(code, 0)
            payload = json.loads(stream.getvalue())
            self.assertIn(payload["status"], ("valid", "complete"))


if __name__ == "__main__":
    unittest.main()
