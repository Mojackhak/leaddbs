#!/usr/bin/env python3
"""Self-tests for observed ULF direct-voxel sensitivity branches."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from stnsnr_ulf_direct_voxel_sensitivity_observed import (
    SensitivityInputs,
    build_sensitivity_branches,
)


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_build_sensitivity_branches_writes_gain_and_total_ulf_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        ref_img = nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), affine=np.eye(4))
        ref_path = root / "ref.nii.gz"
        nib.save(ref_img, ref_path)
        n_subjects = 12
        latent = np.linspace(0.0, 1.0, n_subjects)
        x_ulf_only = np.column_stack(
            [
                250.0 * latent + 10.0,
                210.0 * latent[::-1] + 15.0,
                180.0 + 30.0 * latent,
                40.0 * latent,
                260.0 * latent + 5.0,
                150.0 + 80.0 * latent[::-1],
                95.0 * latent,
                310.0 * latent + 3.0,
            ]
        ).astype(np.float32)
        x_ulf_total = (x_ulf_only + 15.0).astype(np.float32)
        y_hf_ref = 40.0 - 8.0 * latent
        y_post = 35.0 - 9.0 * latent
        gain = y_hf_ref - y_post
        delta_hf = np.linspace(-0.2, 0.3, n_subjects)
        subject_ids = [f"SNr{idx:03d}" for idx in range(n_subjects)]
        inputs = SensitivityInputs(
            subject_ids=subject_ids,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            gain=gain,
            delta_hfscore=delta_hf,
            x_ulf_only=x_ulf_only,
            x_ulf_total=x_ulf_total,
            candidate_flat=np.arange(8, dtype=np.int64),
            ref_img_path=ref_path,
            scale_direction="lower",
            tau=100.0,
            min_coverage=3,
            output_root=root / "out",
            post_scale="MDS-UPDRS III score (STN+SNr, 3 m)",
            hf_reference_scale="MDS-UPDRS III score (STN, 3 m)",
        )

        rows = build_sensitivity_branches(inputs)

        assert_equal({row["branch"] for row in rows}, {"partial_spearman_gain_endpoint", "partial_spearman_total_ulf_exposure"}, "branches")
        for row in rows:
            branch_dir = Path(row["branch_dir"])
            assert_true((branch_dir / "direct_voxel_ULF_only_generation_manifest.json").is_file(), "manifest exists")
            assert_true((branch_dir / "direct_voxel_ULF_only_scores.csv").is_file(), "scores exists")
            assert_true((branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv").is_file(), "predictions exists")
            assert_true((branch_dir / "direct_voxel_ULF_only_coef.nii.gz").is_file(), "coef nifti exists")
            manifest = json.loads((branch_dir / "direct_voxel_ULF_only_generation_manifest.json").read_text(encoding="utf-8"))
            assert_equal(manifest["resampling_status"], "not_run_observed_only", "resampling status")
            assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_build_sensitivity_branches_writes_gain_and_total_ulf_outputs()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
