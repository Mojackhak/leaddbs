#!/usr/bin/env python3
"""Install the ZhangMing legacy-contact compatibility warp candidate."""

from pathlib import Path
import sys


LEAD_ROOT = Path("/Users/mojackhu/Github/leaddbs")
if str(LEAD_ROOT) not in sys.path:
    sys.path.insert(0, str(LEAD_ROOT))

from my_helper.warpslicer.legacy_contact_compat import (  # noqa: E402
    InstallParams,
    InstallPaths,
    install_legacy_contact_compat,
)


SUBJECT_DIR = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr030")
TRANSFORM_DIR = SUBJECT_DIR / "normalization" / "transformations"
OUTPUT_DIR = SUBJECT_DIR / "warpdrive" / "legacy_contact_compat"


def main() -> None:
    paths = InstallPaths(
        lead_root=LEAD_ROOT,
        reconstruction_mat=SUBJECT_DIR
        / "reconstruction"
        / "sub-SNr030_desc-reconstruction.mat",
        cohort_pkl=Path("/Volumes/VAL/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl"),
        current_forward=TRANSFORM_DIR
        / "sub-SNr030_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz",
        current_inverse=TRANSFORM_DIR
        / "sub-SNr030_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz",
        candidate_forward=OUTPUT_DIR
        / "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompat_ants.nii.gz",
        candidate_inverse_point_exact=OUTPUT_DIR
        / "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompatPointExact_ants.nii.gz",
        validation_summary=OUTPUT_DIR / "validation_summary.json",
        output_dir=OUTPUT_DIR,
        subject_label="Sub-ZhangMing",
    )
    params = InstallParams(
        precision_decimals=7,
        max_point_exact_grid_error_mm=1e-6,
        abort_if_backup_exists=True,
    )
    record = install_legacy_contact_compat(paths, params)
    print("Installed forward:", record["targets"]["forward"])
    print("Installed inverse:", record["targets"]["inverse"])
    print("Updated reconstruction:", record["targets"]["reconstruction"])
    print("Backups:", record["backups"])
    print("Install record:", record["install_record"])
    print("Post-install validation:", record["post_install_validation"])


if __name__ == "__main__":
    main()
