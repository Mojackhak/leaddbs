"""Tests for deterministic normative-fiber score construction."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[5] / "core" / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from stnsnr_normative_fiber_score import (  # noqa: E402
    NormativeFiberScoreConfig,
    fiber_net_score,
    score_support_fields,
)


class NormativeFiberScoreTests(unittest.TestCase):
    def test_applies_outer_and_peak_minimum_counts(self) -> None:
        n_positive = 250
        n_negative = 150
        weights = np.concatenate(
            [
                np.linspace(1.0, 0.1, n_positive),
                np.linspace(-1.0, -0.1, n_negative),
            ]
        )
        exposure = np.vstack([np.ones(weights.size), np.full(weights.size, 2.0)])
        result = fiber_net_score(
            exposure,
            weights,
            np.ones(weights.size, dtype=bool),
            fiber_ids=np.arange(1000, 1000 + weights.size),
        )

        self.assertEqual(result.sweet_percentage_count, math.ceil(0.01 * n_positive))
        self.assertEqual(result.sour_percentage_count, math.ceil(0.005 * n_negative))
        self.assertEqual(result.sweet_actual_selected_count, 200)
        self.assertEqual(result.sour_actual_selected_count, 100)
        self.assertEqual(result.sweet_actual_peak_count, 20)
        self.assertEqual(result.sour_actual_peak_count, 20)
        self.assertTrue(result.sweet_minimum_count_dominated)
        self.assertTrue(result.sour_minimum_count_dominated)
        self.assertTrue(result.sweet_peak_minimum_count_dominated)
        self.assertTrue(result.sour_peak_minimum_count_dominated)
        self.assertEqual(result.fiber_score_support_status, "adequate_two_sign")

    def test_caps_minimum_counts_at_available_signed_fibers(self) -> None:
        weights = np.concatenate([np.linspace(1.0, 0.1, 50), np.linspace(-1.0, -0.1, 40)])
        exposure = np.ones((3, weights.size), dtype=float)
        result = fiber_net_score(
            exposure,
            weights,
            np.ones(weights.size, dtype=bool),
            fiber_ids=np.arange(weights.size),
        )

        self.assertEqual(result.sweet_actual_selected_count, 50)
        self.assertEqual(result.sour_actual_selected_count, 40)
        self.assertEqual(result.sweet_actual_peak_count, 20)
        self.assertEqual(result.sour_actual_peak_count, 20)
        self.assertTrue(result.sweet_minimum_count_dominated)
        self.assertTrue(result.sour_minimum_count_dominated)
        self.assertEqual(result.fiber_score_support_status, "limited_two_sign")

    def test_intersects_coverage_with_finite_nonzero_weights(self) -> None:
        exposure = np.asarray([[2.0, 4.0, 8.0, 16.0], [1.0, 3.0, 7.0, 15.0]])
        weights = np.asarray([0.5, np.nan, 0.0, -0.25])
        coverage = np.asarray([True, True, True, False])
        result = fiber_net_score(
            exposure,
            weights,
            coverage,
            fiber_ids=np.asarray([11, 13, 17, 19]),
        )

        self.assertEqual(result.n_positive_valid_fibers, 1)
        self.assertEqual(result.n_negative_valid_fibers, 0)
        self.assertEqual(result.sweet_fiber_ids.tolist(), [11])
        self.assertEqual(result.sour_fiber_ids.tolist(), [])
        np.testing.assert_array_equal(result.sour_peak5, np.zeros(2))
        np.testing.assert_allclose(result.net_score, exposure[:, 0] * 0.5)
        self.assertEqual(result.fiber_score_support_status, "limited_positive_only")

    def test_uses_canonical_id_to_break_equal_weight_ties(self) -> None:
        config = NormativeFiberScoreConfig(
            sweet_fraction=0.01,
            sour_fraction=0.005,
            weighted_peak_fraction=0.05,
            sweet_selected_min_count=2,
            sour_selected_min_count=1,
            weighted_peak_min_count=1,
        )
        result = fiber_net_score(
            np.ones((2, 3)),
            np.ones(3),
            np.ones(3, dtype=bool),
            fiber_ids=np.asarray([30, 10, 20]),
            score_config=config,
        )

        self.assertEqual(result.sweet_fiber_ids.tolist(), [10, 20])

    def test_rejects_duplicate_canonical_fiber_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            fiber_net_score(
                np.ones((2, 3)),
                np.asarray([0.3, 0.2, -0.1]),
                np.ones(3, dtype=bool),
                fiber_ids=np.asarray([10, 10, 20]),
            )

    def test_rejects_duplicate_ids_outside_valid_support(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            fiber_net_score(
                np.ones((2, 3)),
                np.asarray([0.3, np.nan, -0.1]),
                np.asarray([True, False, True]),
                fiber_ids=np.asarray([10, 10, 20]),
            )

    def test_rejects_nonfinite_exposure_before_scoring(self) -> None:
        exposure = np.asarray([[1.0, np.nan], [2.0, 3.0]])
        with self.assertRaisesRegex(ValueError, "finite"):
            fiber_net_score(
                exposure,
                np.asarray([0.4, -0.2]),
                np.ones(2, dtype=bool),
                fiber_ids=np.asarray([1, 2]),
            )

    def test_marks_absent_support_without_minimum_domination(self) -> None:
        result = fiber_net_score(
            np.ones((2, 3)),
            np.asarray([0.0, np.nan, 0.0]),
            np.ones(3, dtype=bool),
            fiber_ids=np.asarray([1, 2, 3]),
        )

        self.assertEqual(result.fiber_score_support_status, "absent_no_valid_signed_fibers")
        self.assertFalse(result.sweet_minimum_count_dominated)
        self.assertFalse(result.sour_minimum_count_dominated)
        self.assertFalse(result.sweet_peak_minimum_count_dominated)
        self.assertFalse(result.sour_peak_minimum_count_dominated)
        np.testing.assert_array_equal(result.net_score, np.zeros(2))

    def test_selected_id_hashes_are_deterministic_and_nonempty(self) -> None:
        kwargs = {
            "exposure": np.ones((2, 4)),
            "weights": np.asarray([0.8, 0.4, -0.6, -0.2]),
            "candidate_mask": np.ones(4, dtype=bool),
            "fiber_ids": np.asarray([101, 103, 107, 109]),
        }
        first = fiber_net_score(**kwargs)
        second = fiber_net_score(**kwargs)
        empty = fiber_net_score(
            np.ones((2, 2)),
            np.zeros(2),
            np.ones(2, dtype=bool),
            fiber_ids=np.asarray([1, 2]),
        )

        self.assertEqual(first.sweet_selected_fiber_id_hash, second.sweet_selected_fiber_id_hash)
        self.assertEqual(first.sour_selected_fiber_id_hash, second.sour_selected_fiber_id_hash)
        self.assertEqual(len(first.sweet_selected_fiber_id_hash), 64)
        self.assertEqual(len(empty.sweet_selected_fiber_id_hash), 64)
        self.assertNotEqual(empty.sweet_selected_fiber_id_hash, "")
        self.assertEqual(
            empty.sweet_selected_fiber_id_hash,
            empty.sour_selected_fiber_id_hash,
        )

        reordered = fiber_net_score(
            np.ones((2, 4)),
            np.asarray([0.4, 0.8, -0.6, -0.2]),
            np.ones(4, dtype=bool),
            fiber_ids=np.asarray([101, 103, 107, 109]),
        )
        self.assertNotEqual(
            first.sweet_selected_fiber_id_hash,
            reordered.sweet_selected_fiber_id_hash,
        )

    def test_negative_only_uses_canonical_id_for_sour_ties(self) -> None:
        config = NormativeFiberScoreConfig(
            sweet_selected_min_count=1,
            sour_selected_min_count=2,
            weighted_peak_min_count=1,
        )
        result = fiber_net_score(
            np.ones((2, 3)),
            -np.ones(3),
            np.ones(3, dtype=bool),
            fiber_ids=np.asarray([30, 10, 20]),
            score_config=config,
        )

        self.assertEqual(result.sour_fiber_ids.tolist(), [10, 20])
        self.assertEqual(result.fiber_score_support_status, "limited_negative_only")

    def test_exact_percentage_boundaries_do_not_mark_outer_minimum_dominated(self) -> None:
        n_per_sign = 20_000
        result = fiber_net_score(
            np.ones((1, n_per_sign * 2), dtype=np.float32),
            np.concatenate([np.ones(n_per_sign), -np.ones(n_per_sign)]),
            np.ones(n_per_sign * 2, dtype=bool),
            fiber_ids=np.arange(n_per_sign * 2),
        )

        self.assertEqual(result.sweet_percentage_count, 200)
        self.assertEqual(result.sour_percentage_count, 100)
        self.assertFalse(result.sweet_minimum_count_dominated)
        self.assertFalse(result.sour_minimum_count_dominated)

    def test_percentage_counts_can_exceed_outer_minima(self) -> None:
        n_per_sign = 20_001
        result = fiber_net_score(
            np.ones((1, n_per_sign * 2), dtype=np.float32),
            np.concatenate([np.ones(n_per_sign), -np.ones(n_per_sign)]),
            np.ones(n_per_sign * 2, dtype=bool),
            fiber_ids=np.arange(n_per_sign * 2),
        )

        self.assertEqual(result.sweet_actual_selected_count, 201)
        self.assertEqual(result.sour_actual_selected_count, 101)

    def test_weighted_peak_percentage_can_exceed_minimum(self) -> None:
        config = NormativeFiberScoreConfig(
            sweet_fraction=1.0,
            sweet_selected_min_count=200,
            weighted_peak_min_count=20,
        )
        result = fiber_net_score(
            np.ones((1, 401)),
            np.ones(401),
            np.ones(401, dtype=bool),
            fiber_ids=np.arange(401),
            score_config=config,
        )

        self.assertEqual(result.sweet_actual_peak_count, 21)
        self.assertFalse(result.sweet_peak_minimum_count_dominated)

    def test_support_fields_emit_the_complete_contract(self) -> None:
        config = NormativeFiberScoreConfig()
        result = fiber_net_score(
            np.ones((2, 2)),
            np.asarray([0.4, -0.2]),
            np.ones(2, dtype=bool),
            fiber_ids=np.asarray([5, 7]),
            score_config=config,
        )
        fields = score_support_fields(result, config)

        expected = {
            "n_positive_valid_fibers",
            "n_negative_valid_fibers",
            "sweet_fraction_requested",
            "sour_fraction_requested",
            "weighted_peak_fraction_requested",
            "sweet_selected_k_min",
            "sour_selected_k_min",
            "weighted_peak_k_min",
            "sweet_percentage_count",
            "sour_percentage_count",
            "sweet_actual_selected_count",
            "sour_actual_selected_count",
            "sweet_actual_peak_count",
            "sour_actual_peak_count",
            "sweet_minimum_count_dominated",
            "sour_minimum_count_dominated",
            "sweet_peak_minimum_count_dominated",
            "sour_peak_minimum_count_dominated",
            "fiber_score_support_status",
            "sweet_selected_fiber_id_hash",
            "sour_selected_fiber_id_hash",
        }
        self.assertEqual(set(fields), expected)
        self.assertEqual(fields["sweet_selected_k_min"], 200)
        self.assertEqual(fields["sour_selected_k_min"], 100)
        self.assertEqual(fields["weighted_peak_k_min"], 20)

    def test_rejects_invalid_score_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "sweet_fraction"):
            NormativeFiberScoreConfig(sweet_fraction=0.0)
        with self.assertRaisesRegex(ValueError, "weighted_peak_min_count"):
            NormativeFiberScoreConfig(weighted_peak_min_count=0)

    def test_mapping_rejects_fractional_minimum_counts(self) -> None:
        values = {
            "sweet_fraction": 0.01,
            "sour_fraction": 0.005,
            "weighted_peak_fraction": 0.05,
            "sweet_selected_min_count": 200.9,
            "sour_selected_min_count": 100,
            "weighted_peak_min_count": 20,
        }
        with self.assertRaisesRegex(ValueError, "sweet_selected_min_count"):
            NormativeFiberScoreConfig.from_mapping(values)


if __name__ == "__main__":
    unittest.main()
