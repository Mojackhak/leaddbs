"""Deterministic integration tests for the direct-voxel source resolver."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np


CORE_ROOT = Path(__file__).resolve().parents[5] / "core"
ANALYSIS_ROOT = CORE_ROOT / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from outcome_models.tests.fixtures.direct_voxel_synthetic import (  # noqa: E402
    COVERAGE_GRID,
    TAU_GRID,
    evaluate_full_grid,
    synthetic_nifti_data,
)
from stnsnr_four_model_resolver import resolve_hf_source  # noqa: E402
from stnsnr_hf_direct_voxel_posthoc_threshold_scan import evaluate_grid_cell  # noqa: E402
from stnsnr_hf_direct_voxel_smoke import sample_image_at_xyz  # noqa: E402


def resolve(rows: list[dict[str, object]]) -> dict[str, object]:
    return resolve_hf_source(
        rows,
        primary_tau=200,
        primary_coverage=5,
        tau_grid=list(TAU_GRID),
        coverage_grid=list(COVERAGE_GRID),
        minimum_adjacent_passing_cells=2,
    )


def passing_row(tau: int, coverage: int) -> dict[str, object]:
    return {
        "tau": tau,
        "coverage": coverage,
        "n_subjects": 16,
        "n_voxels_full": 24,
        "fold_n_voxels_min": 24,
        "hfscore_nonconstant_all_folds": True,
        "all_predictions_finite": True,
        "mae_model": 0.8,
        "mae_baseline": 1.0,
        "rmse_model": 1.0,
        "rmse_baseline": 1.2,
        "q2": -10.0,
        "loocv_spearman_rho": -1.0,
    }


class DirectVoxelSourceResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pre_rows = evaluate_full_grid(
            evaluate_grid_cell,
            exposure_kind="pre_specified",
        )
        cls.fallback_rows = evaluate_full_grid(
            evaluate_grid_cell,
            exposure_kind="scan_fallback",
        )
        cls.absent_rows = evaluate_full_grid(
            evaluate_grid_cell,
            exposure_kind="absent",
        )

    def test_pre_specified_source_is_accepted_with_local_support(self) -> None:
        result = resolve(self.pre_rows)
        self.assertEqual(result["source_status"], "pre_specified_accepted")
        self.assertEqual((result["selected_tau"], result["selected_coverage"]), (200, 5))
        self.assertGreaterEqual(result["selected_adjacent_passing_grid_cells"], 2)

    def test_scan_fallback_selects_tau180_coverage5(self) -> None:
        result = resolve(self.fallback_rows)
        self.assertEqual(result["source_status"], "scan_fallback_accepted")
        self.assertEqual(result["threshold_source"], "scan_fallback")
        self.assertEqual((result["selected_tau"], result["selected_coverage"]), (180, 5))
        self.assertGreaterEqual(result["selected_adjacent_passing_grid_cells"], 2)

    def test_absent_fixture_has_no_selected_source(self) -> None:
        result = resolve(self.absent_rows)
        self.assertEqual(result["source_status"], "absent_no_stable_grid")
        self.assertEqual(result["prediction_status"], "not_applicable")
        self.assertEqual(result["threshold_source"], "none")

    def test_isolated_passing_cell_is_not_a_scan_fallback(self) -> None:
        result = resolve([passing_row(180, 5)])
        self.assertEqual(result["source_status"], "absent_no_stable_grid")
        self.assertEqual(result["source_failure_reasons"], "no_grid_cell_met_adjacent_support")

    def test_source_selection_does_not_use_outcome_performance_metrics(self) -> None:
        altered = copy.deepcopy(self.fallback_rows)
        for index, row in enumerate(altered):
            row["mae_model"] = 1000.0 - index
            row["mae_baseline"] = -1000.0
            row["rmse_model"] = 1000.0 + index
            row["rmse_baseline"] = -1000.0
            row["q2"] = float(index)
            row["loocv_spearman_rho"] = float(-index)
        expected = resolve(self.fallback_rows)
        observed = resolve(altered)
        self.assertEqual(observed["source_status"], expected["source_status"])
        self.assertEqual(observed["selected_tau"], expected["selected_tau"])
        self.assertEqual(observed["selected_coverage"], expected["selected_coverage"])

    def test_small_nifti_adapter_preserves_voxel_values_and_shape(self) -> None:
        data = synthetic_nifti_data()
        coordinates = np.array([[0, 0, 0], [3, 3, 1], [1, 2, 0]], dtype=float)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_efield.nii.gz"
            nib.save(nib.Nifti1Image(data, np.eye(4)), path)
            values, qc = sample_image_at_xyz(path, coordinates)
        expected = np.array([data[0, 0, 0], data[3, 3, 1], data[1, 2, 0]])
        np.testing.assert_allclose(values, expected)
        self.assertEqual(qc["shape"], [4, 4, 2])
        self.assertEqual(qc["inside_voxels"], 3)


if __name__ == "__main__":
    unittest.main()
