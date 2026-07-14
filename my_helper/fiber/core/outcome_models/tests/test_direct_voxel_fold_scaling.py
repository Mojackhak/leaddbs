"""Tests for leakage-free DeltaReferenceScore fold scaling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


CORE_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = CORE_ROOT / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from outcome_models.tests.fixtures.direct_voxel_synthetic import (  # noqa: E402
    addon_outcome,
    baseline_values,
    delta_reference_scores,
    exposure_matrix,
    subject_ids,
)
from stnsnr_four_model_resolver import (  # noqa: E402
    DeltaReferenceScalingError,
    branch_nuisance_design_status,
    zscore_from_training_rows,
)
from stnsnr_four_model_stats import (  # noqa: E402
    coverage_from_suprathreshold,
    suprathreshold_matrix,
)
from stnsnr_ulf_direct_voxel_observed import compute_branch  # noqa: E402


class DirectVoxelFoldScalingTests(unittest.TestCase):
    def test_training_rows_define_center_and_population_scale(self) -> None:
        values = delta_reference_scores()
        heldout = 0
        train = np.delete(np.arange(values.size, dtype=int), heldout)
        standardized = zscore_from_training_rows(values, train)
        self.assertAlmostEqual(float(np.mean(standardized[train])), 0.0, places=14)
        self.assertAlmostEqual(float(np.std(standardized[train], ddof=0)), 1.0, places=14)

    def test_heldout_value_cannot_change_training_standardization(self) -> None:
        values = delta_reference_scores()
        heldout = 0
        train = np.delete(np.arange(values.size, dtype=int), heldout)
        original = zscore_from_training_rows(values, train)
        changed = values.copy()
        changed[heldout] += 1000.0
        modified = zscore_from_training_rows(changed, train)
        np.testing.assert_allclose(modified[train], original[train], rtol=0.0, atol=0.0)
        self.assertNotEqual(modified[heldout], original[heldout])

    def test_full_nonconstant_but_fold_constant_delta_is_invalid_scaling(self) -> None:
        delta = np.ones(16, dtype=np.float64)
        delta[-1] = 2.0
        self.assertEqual(
            branch_nuisance_design_status(
                y_hf_ref=baseline_values(),
                delta_hfscore=delta,
            ),
            "invalid_delta_reference_scaling",
        )

    def test_constant_training_values_raise_specific_scaling_error(self) -> None:
        values = np.ones(16, dtype=np.float64)
        with self.assertRaisesRegex(
            DeltaReferenceScalingError,
            "invalid_delta_reference_scaling",
        ):
            zscore_from_training_rows(values, np.arange(values.size, dtype=int))

    def test_adjusted_compute_branch_records_full_and_fold_standardized_values(self) -> None:
        exposure = exposure_matrix("pre_specified")
        suprathreshold = suprathreshold_matrix(exposure, 200)
        coverage = coverage_from_suprathreshold(suprathreshold)
        delta = delta_reference_scores()
        result = compute_branch(
            branch_name="synthetic_delta_hf_adjusted",
            x_ulf_only=exposure,
            coverage=coverage,
            s_tau_ulf_only=suprathreshold,
            y_post=addon_outcome(),
            y_hf_ref=baseline_values(),
            nuisance_full=delta,
            nuisance_fold_provider=lambda _heldout: delta,
            scale_direction="lower",
            min_coverage=5,
            subject_ids=list(subject_ids()),
        )
        full_expected = zscore_from_training_rows(
            delta,
            np.arange(delta.size, dtype=int),
        )
        np.testing.assert_allclose(
            [row["DeltaHFScore_z"] for row in result["score_rows"]],
            full_expected,
        )
        for heldout, row in enumerate(result["fold_rows"]):
            train = np.delete(np.arange(delta.size, dtype=int), heldout)
            fold_expected = zscore_from_training_rows(delta, train)
            self.assertAlmostEqual(
                row["DeltaHFScore_z_LOOCV"],
                fold_expected[heldout],
                places=14,
            )


if __name__ == "__main__":
    unittest.main()
