"""Deterministic normative-fiber coverage and signed-score tests."""

from __future__ import annotations

import dataclasses
import unittest

import numpy as np

from dual_frequency.backends.normative_fiber import (
    FiberCoverageError,
    FiberScoreError,
    candidate_mask,
    coverage_counts,
    heldout_fold_candidate_mask,
    score_signed_fibers,
    score_support_fields,
)
from dual_frequency.contracts import NormativeFiberScoreSettings


SETTINGS = NormativeFiberScoreSettings(0.01, 0.005, 0.05, 200, 100, 20)


class FiberCoverageTest(unittest.TestCase):
    def test_threshold_equality_is_included_and_fold_removes_heldout_subject(self) -> None:
        exposure = np.array(
            [
                [100.0, 200.0, 201.0],
                [100.0, 199.0, 250.0],
                [90.0, 200.0, 50.0],
            ]
        )
        counts = coverage_counts(exposure, 200, chunk_size=2)
        np.testing.assert_array_equal(counts, [0, 2, 2])
        np.testing.assert_array_equal(candidate_mask(counts, 2), [False, True, True])
        np.testing.assert_array_equal(
            heldout_fold_candidate_mask(exposure, counts, 0, 200, 2, chunk_size=2),
            [False, False, False],
        )
        np.testing.assert_array_equal(
            heldout_fold_candidate_mask(exposure, counts, 1, 200, 2, chunk_size=2),
            [False, True, False],
        )

    def test_coverage_rejects_nonfinite_or_inconsistent_inputs(self) -> None:
        exposure = np.ones((3, 4))
        exposure[1, 2] = np.nan
        with self.assertRaisesRegex(FiberCoverageError, "finite"):
            coverage_counts(exposure, 200)
        with self.assertRaisesRegex(FiberCoverageError, "subject axis"):
            heldout_fold_candidate_mask(
                np.ones((3, 4)),
                np.array([4, 0, 0, 0]),
                0,
                200,
                2,
            )


class FiberScoreTest(unittest.TestCase):
    @staticmethod
    def _library() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        subject = np.arange(5, dtype=float)[:, None]
        fiber = np.arange(400, dtype=float)[None, :]
        exposure = 20.0 + subject + (fiber % 11) / 10.0
        weights = np.zeros(400, dtype=float)
        weights[:250] = 2.0
        weights[250:370] = -3.0
        fiber_ids = np.arange(10_000, 10_400, dtype=np.int64)[::-1]
        return exposure, weights, fiber_ids

    def test_applies_200_100_20_policy_and_deterministic_id_ties(self) -> None:
        exposure, weights, fiber_ids = self._library()
        result = score_signed_fibers(
            exposure,
            weights,
            fiber_ids,
            SETTINGS,
            chunk_size=17,
        )
        self.assertEqual(result.n_positive_valid_fibers, 250)
        self.assertEqual(result.n_negative_valid_fibers, 120)
        self.assertEqual(result.sweet_actual_selected_count, 200)
        self.assertEqual(result.sour_actual_selected_count, 100)
        self.assertEqual(result.sweet_actual_peak_count, 20)
        self.assertEqual(result.sour_actual_peak_count, 20)
        self.assertEqual(result.fiber_score_support_status, "adequate_two_sign")
        np.testing.assert_array_equal(
            result.sweet_fiber_ids,
            np.sort(fiber_ids[:250])[:200],
        )
        np.testing.assert_array_equal(
            result.sour_fiber_ids,
            np.sort(fiber_ids[250:370])[:100],
        )
        self.assertTrue(np.all(np.isfinite(result.net_score)))
        self.assertFalse(result.net_score.flags.writeable)

    def test_intersects_candidate_mask_with_finite_weights(self) -> None:
        exposure, weights, fiber_ids = self._library()
        candidate = np.zeros(400, dtype=bool)
        candidate[:12] = True
        candidate[250:257] = True
        weights[0] = np.nan
        result = score_signed_fibers(
            exposure,
            weights,
            fiber_ids,
            SETTINGS,
            candidate_mask=candidate,
        )
        self.assertEqual(result.n_positive_valid_fibers, 11)
        self.assertEqual(result.n_negative_valid_fibers, 7)
        self.assertEqual(result.fiber_score_support_status, "limited_two_sign")
        self.assertNotIn(fiber_ids[0], result.sweet_fiber_ids)

    def test_one_sided_and_absent_scores_remain_explicit(self) -> None:
        exposure = np.arange(24, dtype=float).reshape(4, 6)
        ids = np.arange(6, dtype=np.int64)
        positive = score_signed_fibers(
            exposure,
            np.ones(6),
            ids,
            SETTINGS,
        )
        self.assertEqual(positive.fiber_score_support_status, "limited_positive_only")
        np.testing.assert_array_equal(positive.sour_peak, np.zeros(4))
        absent = score_signed_fibers(
            exposure,
            np.zeros(6),
            ids,
            SETTINGS,
        )
        self.assertEqual(
            absent.fiber_score_support_status,
            "absent_no_valid_signed_fibers",
        )
        np.testing.assert_array_equal(absent.net_score, np.zeros(4))

    def test_column_reordering_preserves_score_and_selected_id_hashes(self) -> None:
        exposure, weights, fiber_ids = self._library()
        first = score_signed_fibers(exposure, weights, fiber_ids, SETTINGS, chunk_size=13)
        order = np.arange(fiber_ids.size)[::-1]
        second = score_signed_fibers(
            exposure[:, order],
            weights[order],
            fiber_ids[order],
            SETTINGS,
            chunk_size=29,
        )
        np.testing.assert_allclose(first.net_score, second.net_score)
        self.assertEqual(
            first.sweet_selected_fiber_id_hash,
            second.sweet_selected_fiber_id_hash,
        )
        self.assertEqual(
            first.sour_selected_fiber_id_hash,
            second.sour_selected_fiber_id_hash,
        )

    def test_continuous_values_below_tau_remain_in_a_precomputed_candidate(self) -> None:
        exposure = np.array([[50.0, 10.0], [100.0, 20.0]])
        result = score_signed_fibers(
            exposure,
            np.array([1.0, -1.0]),
            np.array([1, 2], dtype=np.int64),
            dataclasses.replace(
                SETTINGS,
                sweet_selected_min_count=1,
                sour_selected_min_count=1,
                weighted_peak_min_count=1,
            ),
            candidate_mask=np.array([True, True]),
        )
        np.testing.assert_array_equal(result.net_score, [40.0, 80.0])

    def test_support_fields_and_invalid_ids_are_explicit(self) -> None:
        exposure = np.ones((3, 2))
        result = score_signed_fibers(
            exposure,
            np.array([1.0, -1.0]),
            np.array([1, 2], dtype=np.int64),
            SETTINGS,
        )
        fields = score_support_fields(result, SETTINGS)
        self.assertEqual(fields["sweet_selected_k_min"], 200)
        self.assertEqual(fields["weighted_peak_k_min"], 20)
        with self.assertRaisesRegex(FiberScoreError, "unique"):
            score_signed_fibers(
                exposure,
                np.array([1.0, -1.0]),
                np.array([1, 1], dtype=np.int64),
                SETTINGS,
            )


if __name__ == "__main__":
    unittest.main()
