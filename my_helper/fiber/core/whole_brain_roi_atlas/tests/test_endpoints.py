from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np

from my_helper.fiber.core.whole_brain_roi_atlas.endpoints import compute_endpoint_census
from my_helper.fiber.core.whole_brain_roi_atlas.errors import EndpointCensusError
from my_helper.fiber.core.whole_brain_roi_atlas.models import ResolvedLabel


def resolved(label_id: int, name: str) -> ResolvedLabel:
    return ResolvedLabel(
        label_id=label_id,
        source_label_name=name,
        resolved_label_name=name,
        base_name=name[:-2],
        category="cortical_limbic",
        tissue_type="gray_matter",
        hemisphere=name[-1],
        laterality_corrected=False,
        include_in_region_ranking=True,
        paired_filename=f"{name[:-2]}.nii.gz",
        source_voxel_count=1,
        centroid_x=0.0,
        centroid_y=0.0,
        centroid_z=0.0,
        contralateral_voxel_fraction=0.0,
    )


class EndpointCensusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        data = np.zeros((3, 1, 1), dtype=np.uint16)
        data[0, 0, 0] = 1
        data[1, 0, 0] = 2
        self.image = nib.Nifti1Image(data, np.eye(4))
        self.labels = (resolved(1, "First_L"), resolved(2, "Second_R"))
        self.connectome = self.root / "data.mat"
        lengths = np.asarray([2, 3, 2], dtype=np.float64)
        points = np.asarray(
            [
                [0, 0, 0, 1],
                [1, 0, 0, 1],
                [0, 0, 0, 2],
                [0.25, 0, 0, 2],
                [0, 0, 0, 2],
                [2, 0, 0, 3],
                [10, 0, 0, 3],
            ],
            dtype=np.float32,
        )
        with h5py.File(self.connectome, "w") as handle:
            handle.create_dataset("idx", data=lengths.reshape(1, -1))
            handle.create_dataset("fibers", data=points.T)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_strict_endpoint_counts_and_unique_fiber_counts(self) -> None:
        result = compute_endpoint_census(
            self.connectome,
            self.image,
            self.labels,
            chunk_size=2,
        )

        rows = {item.label_id: item for item in result.labels}
        self.assertEqual(result.n_fibers, 3)
        self.assertEqual(result.n_endpoints, 6)
        self.assertEqual(rows[1].endpoint_count, 3)
        self.assertEqual(rows[1].fiber_count, 2)
        self.assertEqual(rows[2].endpoint_count, 1)
        self.assertEqual(rows[2].fiber_count, 1)
        self.assertEqual(result.unassigned_endpoint_count, 2)
        self.assertEqual(result.unassigned_fiber_count, 1)
        self.assertEqual(
            sum(item.endpoint_count for item in result.labels)
            + result.unassigned_endpoint_count,
            result.n_endpoints,
        )

    def test_malformed_idx_is_reported_as_endpoint_error(self) -> None:
        with h5py.File(self.connectome, "a") as handle:
            del handle["idx"]
            handle.create_dataset("idx", data=np.asarray([[1, 6]], dtype=np.float64))
        with self.assertRaisesRegex(EndpointCensusError, "at least two points"):
            compute_endpoint_census(
                self.connectome,
                self.image,
                self.labels,
                chunk_size=2,
            )


if __name__ == "__main__":
    unittest.main()
