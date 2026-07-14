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
    normalization = (
        subject
        / "normalization"
        / "transformations"
        / f"{subject_id}_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz"
    )
    write_nifti(normalization, np.ones((2, 2, 2), dtype=np.uint8))
    log_path = (
        subject / "coregistration" / "log" / f"{subject_id}_desc-coregmethod.json"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"method":{"B0":"%s"},"approval":{"B0":%d}}\n'
        % (method, approved),
        encoding="utf-8",
    )
    transform = (
        subject
        / "coregistration"
        / "transformations"
        / f"{subject_id}_from-anchorNative_to-b0_desc-{method_token}44.mat"
    )
    transform.parent.mkdir(parents=True, exist_ok=True)
    savemat(transform, {"tmat": np.eye(4, dtype=np.float64)})
    return subject
