from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import yaml

from my_helper.fiber.core.dwi.phase_encoding_qc import run


def _write_candidate(root: Path, label: str, offset: float) -> dict[str, str]:
    shape = (6, 7, 8)
    base = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + 1.0
    dwi = np.stack((base, base * 0.8, base * 1.1 + offset), axis=3)
    affine = np.eye(4)
    paths = {
        "dwi": root / f"{label}_dwi.nii.gz",
        "bval": root / f"{label}.bval",
        "mask": root / f"{label}_mask.nii.gz",
        "synthetic_b0": root / f"{label}_synthetic.nii.gz",
    }
    nib.save(nib.Nifti1Image(dwi, affine), paths["dwi"])
    np.savetxt(paths["bval"], np.array([[0.0, 1000.0, 0.0]]), fmt="%.1f")
    nib.save(nib.Nifti1Image(np.ones(shape, dtype=np.uint8), affine), paths["mask"])
    nib.save(nib.Nifti1Image(base * 1.1, affine), paths["synthetic_b0"])
    return {key: str(value) for key, value in paths.items()}


def test_phase_encoding_candidate_comparison(tmp_path: Path) -> None:
    candidates = []
    for label, offset in (("jplus", 0.0), ("jminus", 2.0)):
        record = {"label": label}
        record.update(_write_candidate(tmp_path, label, offset))
        candidates.append(record)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "output_root": str(tmp_path / "result"),
                "b0_threshold": 10,
                "candidates": candidates,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run(config_path)

    assert result["selected_b0_index_one_based"] == 3
    assert result["candidate_labels"] == ["jplus", "jminus"]
    assert result["candidate_to_candidate"]["pearson_r"] > 0.99
    assert (tmp_path / "result" / "phase_encoding_comparison.json").is_file()
    assert (tmp_path / "result" / "per_volume_comparison.csv").is_file()
    assert (tmp_path / "result" / "phase_encoding_comparison.png").is_file()
