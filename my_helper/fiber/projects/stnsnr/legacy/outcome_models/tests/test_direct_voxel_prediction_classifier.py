"""Tests for direct-voxel prediction-error classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[5] / "core"
ANALYSIS_ROOT = CORE_ROOT / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from outcome_models.tests.fixtures.direct_voxel_synthetic import (  # noqa: E402
    baseline_values,
    exposure_matrix,
    nonpredictive_outcome,
    predictive_outcome,
)
from stnsnr_four_model_resolver import classify_prediction_status  # noqa: E402
from stnsnr_hf_direct_voxel_posthoc_threshold_scan import evaluate_grid_cell  # noqa: E402


class DirectVoxelPredictionClassifierTests(unittest.TestCase):
    def test_classifier_requires_both_strict_error_improvements(self) -> None:
        cases = (
            (0.8, 1.0, 1.0, 1.2, "error_predictive"),
            (1.0, 1.0, 1.0, 1.2, "error_nonpredictive"),
            (0.8, 1.0, 1.3, 1.2, "error_nonpredictive"),
        )
        for mae_model, mae_base, rmse_model, rmse_base, expected in cases:
            with self.subTest(expected=expected, mae_model=mae_model, rmse_model=rmse_model):
                row = {
                    "mae_model": mae_model,
                    "mae_baseline": mae_base,
                    "rmse_model": rmse_model,
                    "rmse_baseline": rmse_base,
                    "q2": -100.0,
                    "loocv_spearman_rho": -1.0,
                }
                self.assertEqual(classify_prediction_status(row), expected)

    def test_predictive_fixture_improves_both_loocv_errors(self) -> None:
        row = evaluate_grid_cell(
            exposure_matrix("pre_specified"),
            predictive_outcome(),
            baseline_values(),
            "lower",
            200,
            5,
        )
        self.assertTrue(row["passes_all_hard_filters"])
        self.assertLess(row["mae_model"], row["mae_baseline"])
        self.assertLess(row["rmse_model"], row["rmse_baseline"])
        self.assertEqual(row["hf_voxel_prediction_status"], "error_predictive")

    def test_nonpredictive_fixture_remains_computable(self) -> None:
        row = evaluate_grid_cell(
            exposure_matrix("pre_specified"),
            nonpredictive_outcome(),
            baseline_values(),
            "lower",
            200,
            5,
        )
        self.assertTrue(row["passes_all_hard_filters"])
        self.assertTrue(
            row["mae_model"] >= row["mae_baseline"]
            or row["rmse_model"] >= row["rmse_baseline"]
        )
        self.assertEqual(row["hf_voxel_prediction_status"], "error_nonpredictive")


if __name__ == "__main__":
    unittest.main()
