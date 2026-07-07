#!/usr/bin/env python3
"""Self-tests for direct-voxel formal jitter QC."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from stnsnr_direct_voxel_formal_jitter import run_target_jitter
from stnsnr_direct_voxel_formal_permutation import DirectVoxelTarget


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _write_tiny_nifti(path: Path, offset: float) -> None:
    data = np.arange(27, dtype=np.float32).reshape(3, 3, 3) + float(offset)
    img = nib.Nifti1Image(data, np.eye(4))
    nib.save(img, str(path))


def test_run_target_jitter_writes_summary_tables_and_se_nifti() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        preprocess_dir = branch_dir / "preprocess"
        preprocess_dir.mkdir()
        right_path = preprocess_dir / "right.nii.gz"
        left_path = preprocess_dir / "left_to_right.nii.gz"
        _write_tiny_nifti(right_path, 0.0)
        _write_tiny_nifti(left_path, 1.0)
        np.save(preprocess_dir / "candidate_xyz.npy", np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]], dtype=np.float32))
        np.save(preprocess_dir / "candidate_flat_indices.npy", np.array([0, 13, 26], dtype=np.int64))
        np.save(
            preprocess_dir / "X_HF_float32_subject_major.npy",
            np.array(
                [
                    [1.0, 2.0, 3.0],
                    [1.5, 1.0, 4.0],
                    [2.0, 3.0, 1.0],
                    [3.0, 2.5, 5.0],
                    [4.0, 3.0, 2.0],
                    [5.0, 4.0, 1.5],
                ],
                dtype=np.float32,
            ),
        )
        (preprocess_dir / "subjects.csv").write_text(
            "subject_id,y_post,y_base\n"
            "s1,10,0.0\n"
            "s2,9,0.1\n"
            "s3,8,0.0\n"
            "s4,6,0.2\n"
            "s5,5,0.1\n"
            "s6,4,0.2\n",
            encoding="utf-8",
        )
        qc = {
            "sampling_qc": [
                {"subject_id": f"s{i}", "right": [{"path": str(right_path)}], "left_to_right": [{"path": str(left_path)}]}
                for i in range(1, 7)
            ],
            "scale_direction": "lower",
        }
        (preprocess_dir / "direct_voxel_HF_preprocess_qc.json").write_text(json.dumps(qc), encoding="utf-8")
        coef_img = nib.Nifti1Image(np.zeros((3, 3, 3), dtype=np.float32), affine=np.eye(4))
        nib.save(coef_img, branch_dir / "direct_voxel_HF_coef.nii.gz")
        target = DirectVoxelTarget(
            model_id="A",
            manifest_path=branch_dir / "direct_voxel_HF_generation_manifest.json",
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X_HF_float32_subject_major.npy",
            subjects_csv=preprocess_dir / "subjects.csv",
            outcome_column="y_post",
            nuisance_columns=("y_base",),
            scale_direction="lower",
            tau=0.5,
            min_coverage=2,
        )

        row = run_target_jitter(target, n_jitters=5, jitter_fwhm_mm=0.1, seed=42)

        assert_equal(row["B"], 5, "jitter count")
        assert_equal(row["jitter_status"], "complete", "jitter status")
        assert_true((branch_dir / "direct_voxel_HF_jitter_summary.csv").is_file(), "summary exists")
        assert_true((branch_dir / "direct_voxel_HF_jitter_model_similarity.csv").is_file(), "similarity exists")
        assert_true((branch_dir / "direct_voxel_HF_jitter_selected_overlap.csv").is_file(), "overlap exists")
        assert_true((branch_dir / "direct_voxel_HF_jitter_se.nii.gz").is_file(), "SE NIfTI exists")


def main() -> int:
    test_run_target_jitter_writes_summary_tables_and_se_nifti()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
