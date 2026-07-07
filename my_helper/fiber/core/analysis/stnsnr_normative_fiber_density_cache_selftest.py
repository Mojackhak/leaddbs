#!/usr/bin/env python3
"""Self-tests for STN/SNr normative-fiber basic density-cache generation."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np

from stnsnr_normative_fiber_density_cache import build_density_cache_for_branch


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_weights(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"fiber_id": "1", "M_HF": "2.0", "is_candidate": "True"},
        {"fiber_id": "3", "M_HF": "-3.0", "is_candidate": "True"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fiber_id", "M_HF", "is_candidate"])
        writer.writeheader()
        writer.writerows(rows)


def write_tiny_connectome(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Three fibers with lengths [2, 1, 2]. The second fiber is not selected.
    coords = np.array(
        [
            [1, 1, 2, 3, 3],
            [1, 2, 2, 3, 4],
            [1, 1, 2, 3, 3],
            [0, 0, 0, 0, 0],
        ],
        dtype=np.float32,
    )
    with h5py.File(path, "w") as handle:
        handle.create_dataset("fibers", data=coords)
        handle.create_dataset("idx", data=np.array([[2, 1, 2]], dtype=np.float64))


def test_density_cache_writes_voxel_and_weighted_maps() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        branch_dir = root / "branch"
        weights_csv = branch_dir / "normative_HF_fiber_weights.csv"
        data_mat = root / "data.mat"
        template_path = root / "brainmask.nii.gz"
        write_weights(weights_csv)
        write_tiny_connectome(data_mat)
        template_img = nib.Nifti1Image(np.ones((5, 5, 5), dtype=np.uint8), np.eye(4))
        nib.save(template_img, str(template_path))

        outputs = build_density_cache_for_branch(
            model_id="B_DTOR",
            branch_dir=branch_dir,
            weights_csv=weights_csv,
            data_mat=data_mat,
            template_path=template_path,
            output_prefix="normative_HF",
        )

        density = np.asarray(nib.load(outputs["density_map"]).dataobj)
        weighted = np.asarray(nib.load(outputs["weighted_density_map"]).dataobj)
        positive = np.asarray(nib.load(outputs["positive_weighted_density_map"]).dataobj)
        negative = np.asarray(nib.load(outputs["negative_weighted_density_map"]).dataobj)
        assert_equal(float(density[1, 1, 1]), 1.0, "first selected fiber first voxel count")
        assert_equal(float(density[1, 2, 1]), 1.0, "first selected fiber second voxel count")
        assert_equal(float(density[3, 3, 3]), 1.0, "negative selected fiber first voxel count")
        assert_equal(float(density[3, 4, 3]), 1.0, "negative selected fiber second voxel count")
        assert_equal(float(weighted[1, 1, 1]), 2.0, "positive fiber weighted density")
        assert_equal(float(positive[1, 1, 1]), 2.0, "positive density")
        assert_equal(float(weighted[3, 3, 3]), -3.0, "negative fiber weighted density")
        assert_equal(float(negative[3, 3, 3]), -3.0, "negative density")
        assert_true(Path(outputs["density_cache_npz"]).is_file(), "density cache npz should exist")
        manifest = json.loads(Path(outputs["manifest_json"]).read_text(encoding="utf-8"))
        assert_equal(manifest["n_selected_fibers"], 2, "manifest selected fiber count")
        assert_equal(manifest["n_density_voxels_nonzero"], 4, "manifest density voxel count")


def main() -> int:
    test_density_cache_writes_voxel_and_weighted_maps()
    print("stnsnr_normative_fiber_density_cache_selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
