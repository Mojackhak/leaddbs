"""Configured left-geometry to right-canonical OSS contract tests."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest


ANALYSIS_ROOT = Path(__file__).resolve().parents[2] / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

PREFLIGHT = importlib.import_module("stnsnr_normative_fiber_oss_parameter_preflight")
ACTIVATION = importlib.import_module("stnsnr_normative_fiber_oss_activation_rows")
WORKLIST = importlib.import_module("stnsnr_normative_fiber_oss_sidecar_worklist")


class OSSLeftToRightGeometryTests(unittest.TestCase):
    def test_left_preflight_flips_complete_mni_lead_geometry(self) -> None:
        script = PREFLIGHT._matlab_script(
            repo_root=Path("/repo"),
            source_mat=Path("/subject/stim.mat"),
            patient_dir=Path("/subject"),
            row_dir=Path("/run/left"),
            matlab_side_index=2,
            transform_left_to_right=True,
        )

        self.assertIn("options.native = 0;", script)
        self.assertIn("settings.contactLocation{requested_side_idx}", script)
        self.assertIn("settings.Implantation_coordinate(requested_side_idx,:)", script)
        self.assertIn("settings.Second_coordinate(requested_side_idx,:)", script)
        self.assertIn("settings.yMarkerMNI(requested_side_idx,:)", script)
        self.assertIn("settings.headMNI(requested_side_idx,:)", script)
        self.assertGreaterEqual(script.count("ea_flip_lr_nonlinear"), 5)
        self.assertIn("LEFT_TO_RIGHT_TRANSFORM=ea_flip_lr_nonlinear", script)
        self.assertIn("right_canonical_reconstruction.mat", script)
        self.assertIn(
            "reco.mni.coords_mm{1} = ea_flip_lr_nonlinear(reco.mni.coords_mm{requested_side_idx})",
            script,
        )
        self.assertIn("options.subj.recon.recon = canonical_recon_file", script)
        self.assertLess(
            script.index("options.subj.recon.recon = canonical_recon_file"),
            script.index("ea_prepare_fibers(options, S, settings, outputPaths)"),
        )

    def test_right_preflight_does_not_transform_geometry(self) -> None:
        script = PREFLIGHT._matlab_script(
            repo_root=Path("/repo"),
            source_mat=Path("/subject/stim.mat"),
            patient_dir=Path("/subject"),
            row_dir=Path("/run/right"),
            matlab_side_index=1,
            transform_left_to_right=False,
        )

        self.assertNotIn("LEFT_TO_RIGHT_TRANSFORM=ea_flip_lr_nonlinear", script)
        self.assertNotIn("settings.contactLocation{requested_side_idx} = ea_flip", script)
        self.assertNotIn("right_canonical_reconstruction.mat", script)

    def test_left_transformed_and_native_right_rows_use_right_connectome(self) -> None:
        self.assertEqual(
            ACTIVATION._right_canonical_connectome_side(
                {"side": "L", "canonicalization_mode": "left_geometry_to_right"}
            ),
            0,
        )
        self.assertEqual(
            ACTIVATION._right_canonical_connectome_side(
                {"side": "R", "canonicalization_mode": "native_right"}
            ),
            0,
        )
        with self.assertRaisesRegex(ValueError, "canonicalization"):
            ACTIVATION._right_canonical_connectome_side(
                {"side": "L", "canonicalization_mode": "native_left"}
            )

    def test_worklist_requires_exact_left_right_source_rows(self) -> None:
        rows = [
            {"subject_id": "sub-01", "side": "R"},
            {"subject_id": "sub-01", "side": "L"},
            {"subject_id": "sub-02", "side": "L"},
            {"subject_id": "sub-02", "side": "R"},
        ]

        ordered = WORKLIST._ordered_subject_side_rows(("sub-01", "sub-02"), rows)

        self.assertEqual(
            [(row["subject_id"], row["side"]) for row in ordered],
            [("sub-01", "L"), ("sub-01", "R"), ("sub-02", "L"), ("sub-02", "R")],
        )
        self.assertEqual(
            [row["canonicalization_mode"] for row in ordered],
            ["left_geometry_to_right", "native_right", "left_geometry_to_right", "native_right"],
        )
        with self.assertRaisesRegex(ValueError, "exact"):
            WORKLIST._ordered_subject_side_rows(("sub-01", "sub-02"), rows[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            WORKLIST._ordered_subject_side_rows(("sub-01", "sub-02"), rows + [rows[0]])


if __name__ == "__main__":
    unittest.main()
