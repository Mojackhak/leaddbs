#!/usr/bin/env python3
"""Build and install a HuangDan legacy-contact compatibility warp candidate."""

from pathlib import Path
import sys

import numpy as np


LEAD_ROOT = Path("/Users/mojackhu/Github/leaddbs")
if str(LEAD_ROOT) not in sys.path:
    sys.path.insert(0, str(LEAD_ROOT))

from my_helper.warpslicer.legacy_contact_compat import (  # noqa: E402
    CompatParams,
    CompatPaths,
    InstallParams,
    InstallPaths,
    build_legacy_contact_compat,
    extract_contact_landmarks,
    install_legacy_contact_compat,
)


SUBJECT_LABEL = "Sub-HuangDan"
SUBJECT_DIR = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-HuangDan")
TRANSFORM_DIR = SUBJECT_DIR / "normalization" / "transformations"
OUTPUT_DIR = SUBJECT_DIR / "warpdrive" / "legacy_contact_compat"
COHORT_PKL = Path("/Volumes/VAL/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl")
PRECISION_DECIMALS = 7
MAX_POINT_EXACT_GRID_ERROR_MM = 1e-6


def main() -> None:
    compat_paths = CompatPaths(
        lead_root=LEAD_ROOT,
        reconstruction_mat=SUBJECT_DIR / "reconstruction" / "sub-HuangDan_desc-reconstruction.mat",
        cohort_pkl=COHORT_PKL,
        template_reference=LEAD_ROOT / "templates" / "space" / "MNI152NLin2009bAsym" / "t1.nii",
        native_reference=SUBJECT_DIR
        / "coregistration"
        / "anat"
        / "sub-HuangDan_ses-preop_space-anchorNative_desc-preproc_acq-ax_T1w.nii",
        current_forward=TRANSFORM_DIR
        / "sub-HuangDan_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz",
        current_inverse=TRANSFORM_DIR
        / "sub-HuangDan_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz",
        output_dir=OUTPUT_DIR,
        subject_label=SUBJECT_LABEL,
        legacy_target_override_csv=None,
    )
    build_params = CompatParams(
        rbf_radius_mm=15.0,
        stiffness=0.0,
        precision_decimals=PRECISION_DECIMALS,
        overwrite_existing_outputs=True,
    )

    print_delta_table("Pre-install MNI delta", extract_contact_landmarks(compat_paths))
    summary = build_legacy_contact_compat(compat_paths, build_params)
    point_exact_grid = summary["validation"]["candidate_inverse_point_exact_grid"]
    if not point_exact_grid["rounded_exact"]:
        raise RuntimeError("PointExact grid validation is not rounded-exact")
    if float(point_exact_grid["max_error_mm"]) > MAX_POINT_EXACT_GRID_ERROR_MM:
        raise RuntimeError(
            "PointExact grid max error exceeds threshold: "
            f"{point_exact_grid['max_error_mm']} > {MAX_POINT_EXACT_GRID_ERROR_MM}"
        )

    install_paths = InstallPaths(
        lead_root=LEAD_ROOT,
        reconstruction_mat=compat_paths.reconstruction_mat,
        cohort_pkl=COHORT_PKL,
        current_forward=compat_paths.current_forward,
        current_inverse=compat_paths.current_inverse,
        candidate_forward=OUTPUT_DIR
        / "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompat_ants.nii.gz",
        candidate_inverse_point_exact=OUTPUT_DIR
        / "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompatPointExact_ants.nii.gz",
        validation_summary=OUTPUT_DIR / "validation_summary.json",
        output_dir=OUTPUT_DIR,
        subject_label=SUBJECT_LABEL,
    )
    install_params = InstallParams(
        precision_decimals=PRECISION_DECIMALS,
        max_point_exact_grid_error_mm=MAX_POINT_EXACT_GRID_ERROR_MM,
        abort_if_backup_exists=True,
    )
    record = install_legacy_contact_compat(install_paths, install_params)

    print("Candidate forward:", summary["candidate_forward"])
    print("Candidate inverse:", summary["candidate_inverse"])
    print("Point-exact candidate inverse:", summary["candidate_inverse_point_exact"])
    print("Point-exact grid validation:", point_exact_grid)
    print("Installed forward:", record["targets"]["forward"])
    print("Installed inverse:", record["targets"]["inverse"])
    print("Updated reconstruction:", record["targets"]["reconstruction"])
    print("Backup directory:", record["backup_dir"])
    print("Install record:", record["install_record"])
    print("Post-install validation:", record["post_install_validation"])
    print_delta_table("Post-install MNI delta", extract_contact_landmarks(compat_paths))


def print_delta_table(label: str, landmarks: dict) -> None:
    current_mni = np.asarray(landmarks["current_mni"], dtype=float)
    legacy_mni = np.asarray(landmarks["legacy_mni"], dtype=float)
    delta = current_mni - legacy_mni
    distances = np.linalg.norm(delta, axis=1)
    print(label)
    print(
        "mean_error_mm={:.9f} max_error_mm={:.9f} rms_error_mm={:.9f} max_abs_axis_delta_mm={:.9f}".format(
            float(distances.mean()),
            float(distances.max()),
            float(np.sqrt(np.mean(distances**2))),
            float(np.max(np.abs(delta))),
        )
    )
    print("Contact Side dx_mm dy_mm dz_mm distance_mm")
    for meta, point_delta, distance in zip(landmarks["contact_rows"], delta, distances):
        print(
            "{:>7} {:>5} {:+.9f} {:+.9f} {:+.9f} {:.9f}".format(
                int(meta["Contact"]),
                str(meta["Side"]),
                float(point_delta[0]),
                float(point_delta[1]),
                float(point_delta[2]),
                float(distance),
            )
        )


if __name__ == "__main__":
    main()
