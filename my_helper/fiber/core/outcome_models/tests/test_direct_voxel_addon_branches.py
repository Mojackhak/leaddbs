"""Tests for direct-voxel add-on nuisance and branch realization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


CORE_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = CORE_ROOT / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from outcome_models.state import (  # noqa: E402
    BranchResult,
    SourceResult,
    realize_ulf_final,
)
from outcome_models.tests.fixtures.direct_voxel_synthetic import (  # noqa: E402
    addon_outcome,
    baseline_values,
    delta_reference_scores,
    exposure_matrix,
    subject_ids,
)
from stnsnr_four_model_resolver import branch_nuisance_design_status  # noqa: E402
from stnsnr_four_model_stats import (  # noqa: E402
    coverage_from_suprathreshold,
    suprathreshold_matrix,
)
from stnsnr_ulf_direct_voxel_observed import (  # noqa: E402
    evaluate_ulf_direct_grid_cell,
    resolve_ulf_direct_branch,
    ulf_endpoint_status_for_primary,
)


def source(status: str, prediction: str, *, tau: float | None = 200.0) -> SourceResult:
    return SourceResult(
        input_status="valid",
        source_status=status,
        prediction_status=prediction,
        selected_tau=tau,
        selected_coverage=5 if tau is not None else None,
        adjacent_support=2 if tau is not None else None,
    )


class DirectVoxelAddonBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.exposure = exposure_matrix("pre_specified")
        cls.suprathreshold = suprathreshold_matrix(cls.exposure, 200)
        cls.coverage = coverage_from_suprathreshold(cls.suprathreshold)
        cls.y_reference = baseline_values()
        cls.delta = delta_reference_scores()
        cls.y_addon = addon_outcome()

    def test_valid_no_delta_and_adjusted_designs_run_the_same_grid_cell(self) -> None:
        rows = {}
        for branch, delta, provider in (
            ("no_delta_hf", None, None),
            ("delta_hf_adjusted", self.delta, lambda _heldout: self.delta),
        ):
            rows[branch] = evaluate_ulf_direct_grid_cell(
                branch=branch,
                branch_role="primary",
                x_ulf_only=self.exposure,
                coverage_array=self.coverage,
                s_tau_ulf_only=self.suprathreshold,
                y_post=self.y_addon,
                y_hf_ref=self.y_reference,
                nuisance_full=delta,
                nuisance_fold_provider=provider,
                scale_direction="lower",
                subject_ids=list(subject_ids()),
                tau=200,
                coverage=5,
            )
        for branch, row in rows.items():
            with self.subTest(branch=branch):
                self.assertEqual(row["branch_nuisance_design_status"], "valid")
                self.assertTrue(row["passes_all_hard_filters"])
                self.assertEqual(row["n_voxels_full"], 24)
                self.assertEqual(row["fold_n_voxels_min"], 24)
                self.assertTrue(row["all_predictions_finite"])

    def test_constant_delta_fails_only_adjusted_design(self) -> None:
        constant = np.ones_like(self.delta)
        self.assertEqual(
            branch_nuisance_design_status(
                y_hf_ref=self.y_reference,
                delta_hfscore=constant,
            ),
            "invalid_delta_reference_scaling",
        )
        self.assertEqual(
            branch_nuisance_design_status(
                y_hf_ref=self.y_reference,
                delta_hfscore=None,
            ),
            "valid",
        )

        adjusted_row = evaluate_ulf_direct_grid_cell(
            branch="delta_hf_adjusted",
            branch_role="primary",
            x_ulf_only=self.exposure,
            coverage_array=self.coverage,
            s_tau_ulf_only=self.suprathreshold,
            y_post=self.y_addon,
            y_hf_ref=self.y_reference,
            nuisance_full=constant,
            nuisance_fold_provider=lambda _heldout: constant,
            scale_direction="lower",
            subject_ids=list(subject_ids()),
            tau=200,
            coverage=5,
        )
        resolution = resolve_ulf_direct_branch(
            [adjusted_row],
            primary_tau=200,
            primary_coverage=5,
            tau_grid=[200],
            coverage_grid=[5],
        )
        self.assertEqual(
            resolution["ulf_branch_input_status"],
            "invalid_delta_reference_scaling",
        )
        self.assertEqual(
            ulf_endpoint_status_for_primary(resolution),
            "primary_branch_input_failure",
        )

    def test_collinear_delta_is_invalid_nuisance_design(self) -> None:
        collinear = 2.0 * self.y_reference + 3.0
        self.assertEqual(
            branch_nuisance_design_status(
                y_hf_ref=self.y_reference,
                delta_hfscore=collinear,
            ),
            "invalid_nuisance_design",
        )

    def test_adjusted_scaling_failure_realizes_accepted_no_delta_fallback(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        final = realize_ulf_final(
            hf,
            {
                "delta_hf_adjusted": BranchResult(
                    branch="delta_hf_adjusted",
                    input_status="invalid_delta_reference_scaling",
                    source=None,
                ),
                "no_delta_hf": BranchResult(
                    branch="no_delta_hf",
                    input_status="valid",
                    source=source("pre_specified_accepted", "error_nonpredictive"),
                ),
            },
        )
        self.assertEqual(final.intended_primary_branch, "delta_hf_adjusted")
        self.assertEqual(final.final_branch, "no_delta_hf")
        self.assertEqual(final.final_role, "fallback_final")


if __name__ == "__main__":
    unittest.main()
