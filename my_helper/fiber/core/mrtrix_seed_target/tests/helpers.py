"""Synthetic fixtures for seed-wide MRtrix package tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from scipy.io import savemat


def minimal_document(tmp_path: Path, *, subject_count: int = 1) -> dict[str, Any]:
    """Return one schema-valid in-memory configuration."""

    atlas = tmp_path / "atlas"
    subject_root = tmp_path / "subjects"
    return {
        "schema_version": 1,
        "atlas": {
            "name": "atlas",
            "space": "MNI152NLin2009bAsym",
            "root": str(atlas),
            "seeds": [
                {
                    "id": "Seed",
                    "side": "lh",
                    "path": str(atlas / "lh" / "Seed.nii.gz"),
                    "targets": [
                        {
                            "id": "Target",
                            "side": "lh",
                            "path": str(atlas / "lh" / "Target.nii.gz"),
                        }
                    ],
                }
            ],
        },
        "subjects": [
            {
                "id": f"sub-{index + 1:03d}",
                "subject_dir": str(subject_root / f"sub-{index + 1:03d}"),
            }
            for index in range(subject_count)
        ],
        "tracking": {
            "minimum_streamlines_per_target": 300,
            "fod_cutoff": 0.06,
            "min_length_mm": 10,
            "max_length_mm": 250,
            "random_seed": 1,
        },
        "execution": {
            "subject_workers": 2,
            "preparation_threads_per_subject": 4,
            "seedwide_workers_per_subject": 2,
            "mrtrix_threads_per_seedwide_job": 1,
            "cpu_budget": 16,
            "memory_budget_gb": 48,
            "memory_dispatch_fraction": 0.8,
            "preparation_memory_reservation_gb": 8,
            "seedwide_memory_reservation_gb": 2,
            "generation_chunk_streamlines": 50000,
            "maximum_seedwide_streamlines": 100000000,
            "matlab_executable": "/bin/true",
            "mrtrix_path_prefix": "/usr/local/bin",
        },
        "visualization": {
            "target_fiber_display_budget": 3000,
            "target_colormap": "hsv",
            "seed_wireframe_color": "#D9D9D9",
        },
    }


def write_nifti(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray | None = None,
) -> Path:
    """Write one small NIfTI test image."""

    path.parent.mkdir(parents=True, exist_ok=True)
    image = nib.Nifti1Image(
        np.asarray(data),
        np.eye(4, dtype=np.float64) if affine is None else affine,
    )
    nib.save(image, path)
    return path


def make_subject_tree(
    root: Path,
    subject_id: str,
    *,
    method: str = "SPM (Friston 2007)",
    method_token: str = "spm",
    approved: int = 1,
    normalization_method: str = "EasyReg (Iglesias 2023)",
    normalization_approval: float = 1,
    target_space: str = "MNI152NLin2009bAsym",
) -> Path:
    """Create the exact minimal Lead-DBS paths used by discovery."""

    subject = root / subject_id
    dwi_dir = subject / "preprocessing" / "dwi"
    affine = np.diag([1.5, 1.5, 2.0, 1.0])
    write_nifti(
        dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi.nii",
        np.ones((4, 5, 6, 2), dtype=np.float32),
        affine,
    )
    write_nifti(
        dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi_b0.nii",
        np.ones((4, 5, 6), dtype=np.float32),
        affine,
    )
    write_nifti(dwi_dir / "brainmask.nii", np.ones((4, 5, 6), dtype=np.uint8), affine)
    write_nifti(
        dwi_dir / "trackingmask.nii", np.ones((4, 5, 6), dtype=np.uint8), affine
    )
    (dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi.bvec").write_text(
        "1 0\n0 1\n0 0\n", encoding="utf-8"
    )
    (dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi.bval").write_text(
        "0 1000\n", encoding="utf-8"
    )
    write_nifti(
        subject
        / "coregistration"
        / "anat"
        / f"{subject_id}_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w.nii",
        np.ones((8, 8, 8), dtype=np.float32),
        np.diag([0.7, 0.7, 0.7, 1.0]),
    )
    target_to_anchor = (
        subject
        / "normalization"
        / "transformations"
        / f"{subject_id}_from-{target_space}_to-anchorNative_desc-ants.nii.gz"
    )
    anchor_to_target = (
        subject
        / "normalization"
        / "transformations"
        / f"{subject_id}_from-anchorNative_to-{target_space}_desc-ants.nii.gz"
    )
    write_nifti(target_to_anchor, np.zeros((8, 8, 8, 1, 3), dtype=np.float32))
    write_nifti(anchor_to_target, np.zeros((2, 2, 2, 1, 3), dtype=np.float32))
    log_path = (
        subject / "coregistration" / "log" / f"{subject_id}_desc-coregmethod.json"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"method":{"B0":"%s"},"approval":{"B0":%d}}\n'
        % (method, approved),
        encoding="utf-8",
    )
    normalization_log = (
        subject / "normalization" / "log" / f"{subject_id}_desc-normmethod.json"
    )
    normalization_log.parent.mkdir(parents=True, exist_ok=True)
    normalization_log.write_text(
        '{"method":"%s","approval":%s}\n'
        % (normalization_method, normalization_approval),
        encoding="utf-8",
    )
    transform_root = subject / "coregistration" / "transformations"
    anchor_to_b0 = (
        transform_root
        / f"{subject_id}_from-anchorNative_to-b0_desc-{method_token}44.mat"
    )
    b0_to_anchor = (
        transform_root
        / f"{subject_id}_from-b0_to-anchorNative_desc-{method_token}44.mat"
    )
    anchor_to_b0.parent.mkdir(parents=True, exist_ok=True)
    savemat(anchor_to_b0, {"tmat": np.eye(4, dtype=np.float64)})
    savemat(b0_to_anchor, {"tmat": np.eye(4, dtype=np.float64)})
    return subject
