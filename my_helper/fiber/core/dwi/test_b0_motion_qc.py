"""Synthetic tests for last-b0 selection and read-only motion QC."""

from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import yaml

from my_helper.fiber.core.dwi.b0_motion_qc import run


def test_last_b0_is_selected_and_motion_is_recovered(tmp_path: Path) -> None:
    shape = (24, 22, 20)
    grid = np.indices(shape, dtype=np.float32)
    reference = np.exp(
        -(
            (grid[0] - 12.0) ** 2 / 30.0
            + (grid[1] - 10.0) ** 2 / 24.0
            + (grid[2] - 9.0) ** 2 / 18.0
        )
    ).astype(np.float32)
    moving = np.roll(reference, shift=2, axis=0)
    diffusion = reference * 0.7
    data = np.stack([moving, reference, diffusion], axis=3)
    dwi = tmp_path / "dwi.nii.gz"
    bval = tmp_path / "dwi.bval"
    nib.save(nib.Nifti1Image(data, np.eye(4)), dwi)
    np.savetxt(bval, np.array([[0.0, 0.0, 1000.0]]), fmt="%.1f")
    output = tmp_path / "qc"
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "output_root": str(output),
                "reference": {"strategy": "last", "b0_threshold": 10},
                "subjects": [{"id": "sub-test", "dwi": str(dwi), "bval": str(bval)}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run(config)
    manifest = json.loads((output / "sub-test" / "b0_motion_qc.json").read_text())
    comparison = manifest["comparisons"][0]

    assert result["status"] == "complete"
    assert manifest["selected_reference_index_one_based"] == 2
    assert comparison["metrics_after"]["pearson_r"] > comparison["metrics_before"]["pearson_r"]
    assert (output / "sub-test" / comparison["artifacts"]["montage"]).is_file()
