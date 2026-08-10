"""Lead-DBS subject discovery and 44.mat selection tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ..discovery import discover_subject
from ..errors import DiscoveryError, ValidationError
from ..models import SubjectSpec
from .helpers import make_subject_tree, write_nifti


@pytest.mark.parametrize(
    ("method", "token"),
    [
        ("SPM (Friston 2007)", "spm"),
        ("BRAINSFit (Johnson 2007)", "brainsfit"),
    ],
)
def test_method_log_selects_exact_matching_44_mat(
    tmp_path: Path, method: str, token: str
) -> None:
    subject_id = "sub-001"
    subject_dir = make_subject_tree(
        tmp_path, subject_id, method=method, method_token=token
    )
    resolved = discover_subject(
        SubjectSpec(subject_id, subject_dir), "MNI152NLin2009bAsym"
    )
    assert resolved.coregistration_method_token == token
    assert resolved.anchor_to_b0_transform.name.endswith(f"desc-{token}44.mat")
    assert resolved.b0_to_anchor_transform.name.endswith(f"desc-{token}44.mat")
    assert resolved.b0.name.endswith("desc-preproc_dwi_b0.nii")


def test_unapproved_b0_is_rejected(tmp_path: Path) -> None:
    subject_dir = make_subject_tree(tmp_path, "sub-001", approved=0)
    with pytest.raises(DiscoveryError, match="not approved"):
        discover_subject(SubjectSpec("sub-001", subject_dir), "MNI152NLin2009bAsym")


def test_anatomical_anchor_ambiguity_is_rejected(tmp_path: Path) -> None:
    subject_id = "sub-001"
    subject_dir = make_subject_tree(tmp_path, subject_id)
    write_nifti(
        subject_dir
        / "coregistration"
        / "anat"
        / f"{subject_id}_ses-preop_space-anchorNative_desc-preproc_acq-ax_T1w.nii",
        __import__("numpy").ones((2, 2, 2), dtype="float32"),
    )
    with pytest.raises(DiscoveryError, match="exactly one anatomical"):
        discover_subject(
            SubjectSpec(subject_id, subject_dir), "MNI152NLin2009bAsym"
        )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (np.zeros((4, 5, 6), dtype=np.uint8), "tracking mask is empty"),
        (np.full((4, 5, 6), 2, dtype=np.uint8), "tracking mask must be binary"),
    ],
)
def test_invalid_tracking_mask_is_rejected_before_preparation(
    tmp_path: Path, data: np.ndarray, message: str
) -> None:
    subject_id = "sub-001"
    subject_dir = make_subject_tree(tmp_path, subject_id)
    write_nifti(
        subject_dir / "preprocessing" / "dwi" / "trackingmask.nii",
        data,
        np.diag([1.5, 1.5, 2.0, 1.0]),
    )
    with pytest.raises(ValidationError, match=message):
        discover_subject(
            SubjectSpec(subject_id, subject_dir), "MNI152NLin2009bAsym"
        )
