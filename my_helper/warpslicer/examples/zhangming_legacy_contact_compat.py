#!/usr/bin/env python3
"""Build a ZhangMing legacy-contact compatibility warp candidate."""

from pathlib import Path
import sys


LEAD_ROOT = Path("/Users/mojackhu/Github/leaddbs")
if str(LEAD_ROOT) not in sys.path:
    sys.path.insert(0, str(LEAD_ROOT))

from my_helper.warpslicer.legacy_contact_compat import (  # noqa: E402
    CompatParams,
    CompatPaths,
    build_legacy_contact_compat,
)


SUBJECT_DIR = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-ZhangMing")
TRANSFORM_DIR = SUBJECT_DIR / "normalization" / "transformations"
OUTPUT_DIR = SUBJECT_DIR / "warpdrive" / "legacy_contact_compat"


def main() -> None:
    paths = CompatPaths(
        lead_root=LEAD_ROOT,
        reconstruction_mat=SUBJECT_DIR
        / "reconstruction"
        / "sub-ZhangMing_desc-reconstruction.mat",
        cohort_pkl=Path("/Volumes/VAL/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl"),
        template_reference=LEAD_ROOT
        / "templates"
        / "space"
        / "MNI152NLin2009bAsym"
        / "t1.nii",
        native_reference=SUBJECT_DIR
        / "coregistration"
        / "anat"
        / "sub-ZhangMing_ses-preop_space-anchorNative_desc-preproc_acq-ax_T1w.nii",
        current_forward=TRANSFORM_DIR
        / "sub-ZhangMing_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz",
        current_inverse=TRANSFORM_DIR
        / "sub-ZhangMing_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz",
        output_dir=OUTPUT_DIR,
        subject_label="Sub-ZhangMing",
        legacy_target_override_csv=None,
    )
    params = CompatParams(
        rbf_radius_mm=15.0,
        stiffness=0.0,
        precision_decimals=7,
        overwrite_existing_outputs=True,
    )
    summary = build_legacy_contact_compat(paths, params)
    print("Candidate forward:", summary["candidate_forward"])
    print("Candidate inverse:", summary["candidate_inverse"])
    print("Point-exact candidate inverse:", summary["candidate_inverse_point_exact"])
    print("Candidate inverse validation:", summary["validation"]["candidate_inverse_point"])
    print("Point-exact grid validation:", summary["validation"]["candidate_inverse_point_exact_grid"])
    print("Point-exact ANTs validation:", summary["validation"]["candidate_inverse_point_exact_ants"])


if __name__ == "__main__":
    main()
