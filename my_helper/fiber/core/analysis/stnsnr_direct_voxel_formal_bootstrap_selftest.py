#!/usr/bin/env python3
"""Self-tests for direct-voxel final-model formal bootstrap."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from stnsnr_direct_voxel_formal_bootstrap import run_target_bootstrap
from stnsnr_direct_voxel_formal_permutation import DirectVoxelTarget


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_run_target_bootstrap_writes_summary_and_se_nifti() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        preprocess_dir = branch_dir / "preprocess"
        preprocess_dir.mkdir()
        x = np.array(
            [
                [0.0, 2.0, 4.0, 0.0, 3.0, 1.0],
                [1.0, 3.0, 5.0, 0.0, 0.0, 2.0],
                [2.0, 4.0, 6.0, 1.0, 0.0, 3.0],
                [3.0, 5.0, 7.0, 1.0, 2.0, 4.0],
                [4.0, 6.0, 8.0, 2.0, 2.0, 5.0],
                [5.0, 7.0, 9.0, 2.0, 4.0, 6.0],
            ],
            dtype=np.float32,
        )
        np.save(preprocess_dir / "X_HF_float32_subject_major.npy", x)
        np.save(preprocess_dir / "candidate_flat_indices.npy", np.arange(x.shape[1], dtype=np.int64))
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
        coef_img = nib.Nifti1Image(np.zeros((1, 1, x.shape[1]), dtype=np.float32), affine=np.eye(4))
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

        row = run_target_bootstrap(target, n_bootstraps=9, seed=42)

        assert_equal(row["B"], 9, "bootstrap count")
        assert_equal(row["bootstrap_status"], "complete", "bootstrap status")
        assert_true((branch_dir / "direct_voxel_HF_bootstrap_summary.csv").is_file(), "summary exists")
        assert_true((branch_dir / "direct_voxel_HF_bootstrap_se.nii.gz").is_file(), "SE NIfTI exists")
        assert_true(np.isfinite(nib.load(branch_dir / "direct_voxel_HF_bootstrap_se.nii.gz").get_fdata()).any(), "finite SE")
        manifest = json.loads((branch_dir / "direct_voxel_HF_formal_bootstrap_manifest.json").read_text(encoding="utf-8"))
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_run_target_bootstrap_writes_summary_and_se_nifti()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
