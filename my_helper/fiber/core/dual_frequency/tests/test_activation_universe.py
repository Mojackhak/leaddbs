"""Deterministic contract tests for the pure activation primitives."""

from __future__ import annotations

import unittest

import numpy as np

from dual_frequency.backends.activation import (
    CanonicalMappingError,
    PPAMError,
    activation_universe,
    binary_activation,
    max_probability_union,
    merge_right_canonical_probabilities,
    subset_probability_axis,
)


class ActivationUniverseTests(unittest.TestCase):
    def test_activation_universe_is_the_exact_ordered_final_axis(self) -> None:
        final_valid_ids = np.asarray([503, 101, 907, 211], dtype=np.int64)

        actual = activation_universe(final_valid_ids)

        np.testing.assert_array_equal(actual, final_valid_ids)
        self.assertEqual(actual.dtype, np.dtype(np.int64))
        self.assertFalse(actual.flags.writeable)

    def test_activation_universe_requires_unique_nonempty_int64_ids(self) -> None:
        invalid = (
            (np.asarray([1, 2], dtype=np.int32), "int64"),
            (np.asarray([1.0, 2.0], dtype=np.float64), "int64"),
            (np.asarray([1, 1], dtype=np.int64), "unique"),
            (np.asarray([[1, 2]], dtype=np.int64), "one-dimensional"),
            (np.asarray([], dtype=np.int64), "nonempty"),
        )
        for fiber_ids, message in invalid:
            with self.subTest(dtype=fiber_ids.dtype, shape=fiber_ids.shape):
                with self.assertRaisesRegex(CanonicalMappingError, message):
                    activation_universe(fiber_ids)

    def test_exact_axis_subsetting_uses_requested_id_order(self) -> None:
        source_ids = np.asarray([503, 101, 907, 211], dtype=np.int64)
        requested_ids = np.asarray([907, 503, 211], dtype=np.int64)
        probabilities = np.asarray(
            [[0.1, 0.2, 0.3, 0.4], [0.8, 0.7, 0.6, 0.5]],
            dtype=np.float64,
        )

        subset = subset_probability_axis(
            probabilities,
            source_fiber_ids=source_ids,
            requested_fiber_ids=requested_ids,
        )

        np.testing.assert_array_equal(
            subset,
            np.asarray([[0.3, 0.1, 0.4], [0.6, 0.8, 0.5]], dtype=np.float32),
        )
        self.assertEqual(subset.dtype, np.dtype(np.float32))
        self.assertFalse(subset.flags.writeable)

    def test_exact_axis_subsetting_rejects_missing_or_invalid_identity(self) -> None:
        probabilities = np.asarray([[0.1, 0.2]], dtype=np.float32)
        source_ids = np.asarray([100, 102], dtype=np.int64)

        with self.assertRaisesRegex(CanonicalMappingError, "exact requested fiber IDs"):
            subset_probability_axis(
                probabilities,
                source_fiber_ids=source_ids,
                requested_fiber_ids=np.asarray([101], dtype=np.int64),
            )
        with self.assertRaisesRegex(CanonicalMappingError, "unique"):
            subset_probability_axis(
                probabilities,
                source_fiber_ids=np.asarray([100, 100], dtype=np.int64),
                requested_fiber_ids=np.asarray([100], dtype=np.int64),
            )

    def test_exact_axis_subsetting_validates_shape_and_probability_domain(self) -> None:
        source_ids = np.asarray([10, 20], dtype=np.int64)
        requested_ids = np.asarray([20], dtype=np.int64)

        with self.assertRaisesRegex(CanonicalMappingError, "fiber-axis length"):
            subset_probability_axis(
                np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32),
                source_fiber_ids=source_ids,
                requested_fiber_ids=requested_ids,
            )
        with self.assertRaisesRegex(PPAMError, "finite"):
            subset_probability_axis(
                np.asarray([[0.1, np.nan]], dtype=np.float32),
                source_fiber_ids=source_ids,
                requested_fiber_ids=requested_ids,
            )


class CanonicalRowMergeTests(unittest.TestCase):
    @staticmethod
    def _rows() -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)
        return {
            ("sub-01", "R"): (fiber_ids, np.asarray([0.7, 0.1, 0.4])),
            ("sub-02", "L"): (fiber_ids, np.asarray([0.9, 0.2, 0.1])),
            ("sub-01", "L"): (fiber_ids, np.asarray([0.2, 0.8, 0.3])),
            ("sub-02", "R"): (fiber_ids, np.asarray([0.3, 0.6, 0.5])),
        }

    def test_exact_left_right_rows_merge_in_declared_subject_order(self) -> None:
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)

        merged = merge_right_canonical_probabilities(
            subject_order=("sub-02", "sub-01"),
            valid_fiber_ids=fiber_ids,
            side_probabilities=self._rows(),
        )

        np.testing.assert_array_equal(
            merged,
            np.asarray([[0.9, 0.6, 0.5], [0.7, 0.8, 0.4]], dtype=np.float32),
        )
        self.assertEqual(merged.dtype, np.dtype(np.float32))
        self.assertFalse(merged.flags.writeable)

    def test_merge_requires_exact_left_right_rows_for_every_subject(self) -> None:
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)
        rows = self._rows()
        del rows[("sub-01", "L")]
        with self.assertRaisesRegex(CanonicalMappingError, "exact L/R rows"):
            merge_right_canonical_probabilities(
                subject_order=("sub-01", "sub-02"),
                valid_fiber_ids=fiber_ids,
                side_probabilities=rows,
            )

        rows = self._rows()
        rows[("sub-extra", "R")] = rows[("sub-01", "R")]
        with self.assertRaisesRegex(CanonicalMappingError, "exact L/R rows"):
            merge_right_canonical_probabilities(
                subject_order=("sub-01", "sub-02"),
                valid_fiber_ids=fiber_ids,
                side_probabilities=rows,
            )

    def test_merge_rejects_reordered_row_axis_and_duplicate_subjects(self) -> None:
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)
        rows = self._rows()
        rows[("sub-01", "L")] = (
            fiber_ids[::-1].copy(),
            np.asarray([0.3, 0.8, 0.2]),
        )
        with self.assertRaisesRegex(CanonicalMappingError, "exact final feature axis"):
            merge_right_canonical_probabilities(
                subject_order=("sub-01", "sub-02"),
                valid_fiber_ids=fiber_ids,
                side_probabilities=rows,
            )

        with self.assertRaisesRegex(CanonicalMappingError, "unique"):
            merge_right_canonical_probabilities(
                subject_order=("sub-01", "sub-01"),
                valid_fiber_ids=fiber_ids,
                side_probabilities=self._rows(),
            )


class PPAMTests(unittest.TestCase):
    def test_max_probability_union_is_elementwise_and_float32(self) -> None:
        right = np.asarray([[0.1, 0.8], [0.5, 0.2]], dtype=np.float64)
        left_to_right = np.asarray([[0.7, 0.3], [0.5, 1.0]], dtype=np.float64)

        merged = max_probability_union(right, left_to_right)

        np.testing.assert_array_equal(
            merged,
            np.asarray([[0.7, 0.8], [0.5, 1.0]], dtype=np.float32),
        )
        self.assertEqual(merged.dtype, np.dtype(np.float32))
        self.assertFalse(merged.flags.writeable)

    def test_max_probability_union_validates_shape_and_probability_domain(self) -> None:
        valid = np.asarray([0.2, 0.8], dtype=np.float32)
        with self.assertRaisesRegex(PPAMError, "same shape"):
            max_probability_union(valid, np.asarray([[0.2, 0.8]], dtype=np.float32))

        invalid = (
            (np.asarray([np.nan, 0.2]), "finite"),
            (np.asarray([-0.01, 0.2]), r"\[0, 1\]"),
            (np.asarray([0.2, 1.01]), r"\[0, 1\]"),
        )
        for probabilities, message in invalid:
            with self.subTest(probabilities=probabilities):
                with self.assertRaisesRegex(PPAMError, message):
                    max_probability_union(valid, probabilities)

    def test_binary_activation_uses_strict_half_threshold(self) -> None:
        probabilities = np.asarray(
            [[0.0, 0.49999997, 0.5, 0.50000006, 1.0]],
            dtype=np.float32,
        )

        binary = binary_activation(probabilities)

        np.testing.assert_array_equal(
            binary,
            np.asarray([[0.0, 0.0, 0.0, 1.0, 1.0]], dtype=np.float32),
        )
        self.assertEqual(binary.dtype, np.dtype(np.float32))
        self.assertFalse(binary.flags.writeable)

    def test_binary_activation_rejects_nonfinite_and_out_of_range_values(self) -> None:
        for probabilities, message in (
            (np.asarray([0.2, np.inf]), "finite"),
            (np.asarray([0.2, -np.finfo(np.float64).eps]), r"\[0, 1\]"),
            (np.asarray([0.2, 1.0 + np.finfo(np.float64).eps]), r"\[0, 1\]"),
        ):
            with self.subTest(probabilities=probabilities):
                with self.assertRaisesRegex(PPAMError, message):
                    binary_activation(probabilities)


if __name__ == "__main__":
    unittest.main()
