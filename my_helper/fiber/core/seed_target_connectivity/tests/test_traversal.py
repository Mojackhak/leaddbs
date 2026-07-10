"""Reference and optimized segment-aware traversal tests."""

from __future__ import annotations

import unittest

import numpy as np

from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    fiber_chunk,
    line,
    resolved_mask,
)
from my_helper.fiber.core.seed_target_connectivity.traversal import (
    build_sparse_lookup,
    optimized_membership,
    reference_membership,
)


class SegmentTraversalTests(unittest.TestCase):
    def test_detects_crossing_when_both_vertices_are_outside(self) -> None:
        mask = resolved_mask([(1, 1, 1)])
        streamline = line((-1, 1, 1), (3, 1, 1))

        reference = reference_membership([streamline], [mask])
        optimized = optimized_membership(fiber_chunk([streamline]), build_sparse_lookup([mask]))

        self.assertEqual(reference.tolist(), [[True]])
        self.assertTrue(np.array_equal(reference, optimized))

    def test_rejects_segment_that_approaches_without_crossing(self) -> None:
        mask = resolved_mask([(1, 1, 1)])
        streamline = line((-1, 1.51, 1), (3, 1.51, 1))

        reference = reference_membership([streamline], [mask])
        optimized = optimized_membership(fiber_chunk([streamline]), build_sparse_lookup([mask]))

        self.assertEqual(reference.tolist(), [[False]])
        self.assertTrue(np.array_equal(reference, optimized))

    def test_assigns_overlapping_targets_independently(self) -> None:
        first = resolved_mask([(1, 1, 1)], roi_id="first")
        second = resolved_mask([(1, 1, 1), (2, 1, 1)], roi_id="second")
        streamline = line((-1, 1, 1), (3, 1, 1))

        result = optimized_membership(
            fiber_chunk([streamline]),
            build_sparse_lookup([first, second]),
        )

        self.assertEqual(result.tolist(), [[True, True]])

    def test_empty_targets_remain_false_without_affecting_peers(self) -> None:
        empty = resolved_mask([], roi_id="empty")
        valid = resolved_mask([(1, 1, 1)], roi_id="valid")
        streamline = line((0, 1, 1), (2, 1, 1))

        result = optimized_membership(
            fiber_chunk([streamline]),
            build_sparse_lookup([empty, valid]),
        )

        self.assertEqual(result.tolist(), [[False, True]])

    def test_supports_different_valid_grid_geometries(self) -> None:
        identity_mask = resolved_mask([(1, 1, 1)], roi_id="identity")
        translated_affine = np.eye(4, dtype=np.float64)
        translated_affine[0, 3] = 10.0
        translated_mask = resolved_mask(
            [(0, 1, 1)],
            affine=translated_affine,
            roi_id="translated",
        )
        streamlines = [
            line((0, 1, 1), (2, 1, 1)),
            line((9, 1, 1), (11, 1, 1)),
        ]

        reference = reference_membership(streamlines, [identity_mask, translated_mask])
        optimized = optimized_membership(
            fiber_chunk(streamlines),
            build_sparse_lookup([identity_mask, translated_mask]),
        )

        self.assertEqual(reference.tolist(), [[True, False], [False, True]])
        self.assertTrue(np.array_equal(reference, optimized))

    def test_half_open_boundaries_and_zero_length_segments_are_deterministic(self) -> None:
        lower = resolved_mask([(1, 1, 1)], roi_id="lower")
        upper = resolved_mask([(2, 1, 1)], roi_id="upper")
        streamlines = [
            line((0.5, 1, 1), (0.5, 1, 1)),
            line((1.5, 1, 1), (1.5, 1, 1)),
            line((1.5, 1, 1), (2.25, 1, 1)),
        ]

        reference = reference_membership(streamlines, [lower, upper])
        optimized = optimized_membership(
            fiber_chunk(streamlines),
            build_sparse_lookup([lower, upper]),
        )

        self.assertEqual(reference.tolist(), [[True, False], [False, True], [False, True]])
        self.assertTrue(np.array_equal(reference, optimized))

    def test_multiple_segments_and_fibers_preserve_row_order(self) -> None:
        masks = [
            resolved_mask([(1, 1, 1)], roi_id="one"),
            resolved_mask([(2, 2, 2)], roi_id="two"),
        ]
        streamlines = [
            line((0, 1, 1), (1, 1, 1), (3, 1, 1)),
            line((0, 0, 0), (0.4, 0.4, 0.4)),
            line((1, 2, 2), (3, 2, 2)),
        ]

        reference = reference_membership(streamlines, masks)
        optimized = optimized_membership(fiber_chunk(streamlines, first_id=20), build_sparse_lookup(masks))

        self.assertEqual(reference.tolist(), [[True, False], [False, False], [False, True]])
        self.assertTrue(np.array_equal(reference, optimized))

    def test_randomized_reference_and_optimized_kernels_agree(self) -> None:
        generator = np.random.default_rng(20260710)
        masks = [
            resolved_mask([(0, 0, 0), (1, 1, 1), (2, 1, 3)], roi_id="a"),
            resolved_mask([(1, 1, 1), (3, 3, 3)], roi_id="b"),
        ]
        streamlines = [
            np.asarray(generator.uniform(-1.2, 4.2, size=(3, 3)), dtype=np.float32)
            for _ in range(100)
        ]

        reference = reference_membership(streamlines, masks)
        optimized = optimized_membership(fiber_chunk(streamlines), build_sparse_lookup(masks))

        self.assertTrue(np.array_equal(reference, optimized))

    def test_target_bitsets_span_multiple_uint64_words(self) -> None:
        masks = [
            resolved_mask([(1, 1, 1)], roi_id=f"target_{index:03d}")
            for index in range(70)
        ]
        streamline = line((0, 1, 1), (2, 1, 1))

        result = optimized_membership(
            fiber_chunk([streamline]),
            build_sparse_lookup(masks),
        )

        self.assertEqual(result.shape, (1, 70))
        self.assertTrue(np.all(result))


if __name__ == "__main__":
    unittest.main()
