"""Affine-aware ROI resampling and target-cleaning tests."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.io import savemat

from ..roi import clean_target_mask, resample_anchor_mask_to_b0
from .helpers import write_nifti


def test_world_tmat_and_headers_define_nearest_neighbor_resampling(tmp_path: Path) -> None:
    anchor_data = np.zeros((5, 5, 5), dtype=np.uint8)
    anchor_data[1, 1, 1] = 1
    anchor = write_nifti(tmp_path / "anchor.nii.gz", anchor_data, np.eye(4))
    b0 = write_nifti(
        tmp_path / "b0.nii.gz", np.zeros((6, 5, 5), dtype=np.float32), np.eye(4)
    )
    tmat = np.eye(4)
    tmat[0, 3] = 1.0
    transform = tmp_path / "transform44.mat"
    savemat(transform, {"tmat": tmat})
    output = tmp_path / "dwi.nii.gz"
    count = resample_anchor_mask_to_b0(anchor, b0, transform, output)
    image = nib.load(output)
    data = np.asanyarray(image.dataobj)
    assert count == 1
    assert data[2, 1, 1] == 1
    assert set(np.unique(data)) == {0, 1}
    assert image.shape == nib.load(b0).shape
    assert np.array_equal(image.affine, nib.load(b0).affine)


def test_clean_target_removes_seed_overlap_on_final_grid(tmp_path: Path) -> None:
    seed_data = np.zeros((4, 4, 4), dtype=np.uint8)
    target_data = np.zeros_like(seed_data)
    seed_data[1, 1, 1] = 1
    target_data[1, 1, 1] = 1
    target_data[2, 2, 2] = 1
    seed = write_nifti(tmp_path / "seed.nii.gz", seed_data)
    target = write_nifti(tmp_path / "target.nii.gz", target_data)
    output = tmp_path / "clean.nii.gz"
    count, overlap = clean_target_mask(target, seed, output)
    cleaned = np.asanyarray(nib.load(output).dataobj) > 0
    assert count == 1
    assert overlap == 1
    assert not np.any(cleaned & (seed_data > 0))
    assert cleaned[2, 2, 2]
