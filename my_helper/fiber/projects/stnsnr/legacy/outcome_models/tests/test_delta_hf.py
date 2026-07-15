"""Tests for shared DeltaHFScore support classification."""

from __future__ import annotations

import unittest

from outcome_models.services.delta_hf import classify_delta_hf_support


class DeltaHFSupportTests(unittest.TestCase):
    def test_adequate_and_limited_are_valid_support_classes(self) -> None:
        adequate = classify_delta_hf_support(
            subject_out_fractions=(0.10, 0.20, 0.50, 0.05),
            fold_out_fractions=(0.10, 0.20, 0.50, 0.05),
            any_zero_total=False,
            zero_status="invalid_no_hfcomponent_coverage",
        )
        limited = classify_delta_hf_support(
            subject_out_fractions=(0.10, 0.30, 0.40, 0.20),
            fold_out_fractions=(0.10, 0.30, 0.40, 0.20),
            any_zero_total=False,
            zero_status="invalid_no_hfcomponent_coverage",
        )
        self.assertEqual(adequate.status, "adequate")
        self.assertEqual(limited.status, "limited")
        self.assertTrue(adequate.valid)
        self.assertTrue(limited.valid)

    def test_extreme_thresholds_are_strict_and_include_any_fold_over_point_95(self) -> None:
        exact = classify_delta_hf_support(
            subject_out_fractions=(0.50, 0.80, 0.20, 0.20),
            fold_out_fractions=(0.95, 0.20, 0.20, 0.20),
            any_zero_total=False,
            zero_status="invalid_no_hfcomponent_exposure",
        )
        fold_extreme = classify_delta_hf_support(
            subject_out_fractions=(0.10, 0.10, 0.10, 0.10),
            fold_out_fractions=(0.9500001, 0.10, 0.10, 0.10),
            any_zero_total=False,
            zero_status="invalid_no_hfcomponent_exposure",
        )
        subject_fraction_extreme = classify_delta_hf_support(
            subject_out_fractions=(0.81, 0.81, 0.10, 0.10),
            fold_out_fractions=(0.10, 0.10, 0.10, 0.10),
            any_zero_total=False,
            zero_status="invalid_no_hfcomponent_exposure",
        )
        self.assertEqual(exact.status, "limited")
        self.assertEqual(fold_extreme.status, "invalid_extreme_out_of_support")
        self.assertEqual(subject_fraction_extreme.status, "invalid_extreme_out_of_support")

    def test_zero_total_precedes_fraction_classification(self) -> None:
        result = classify_delta_hf_support(
            subject_out_fractions=(0.0, 0.0),
            fold_out_fractions=(0.0, 0.0),
            any_zero_total=True,
            zero_status="invalid_no_hfcomponent_coverage",
        )
        self.assertEqual(result.status, "invalid_no_hfcomponent_coverage")
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()
