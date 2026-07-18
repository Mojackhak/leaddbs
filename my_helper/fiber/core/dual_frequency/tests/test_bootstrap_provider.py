from __future__ import annotations

import unittest

import numpy as np

from ..runtime.bootstrap_provider import (
    StudyBootstrapNuisanceProviderError,
    _aligned_selected_fiber_exposures,
)


class BootstrapProviderFiberAlignmentTests(unittest.TestCase):
    def test_aligns_locked_ids_independently_across_two_parent_axes(self) -> None:
        reference_parent_ids = np.asarray([10, 20, 30, 40, 50], dtype=np.int64)
        addon_parent_ids = np.asarray([20, 30, 40, 60], dtype=np.int64)
        selected_ids = np.asarray([20, 40], dtype=np.int64)
        reference_exposure = np.asarray(
            [[10.0, 20.0, 30.0, 40.0, 50.0]],
            dtype=np.float64,
        )
        reference_condition = np.asarray(
            [[200.0, 300.0, 400.0, 600.0]],
            dtype=np.float64,
        )
        addon_reference_component = np.asarray(
            [[1200.0, 1300.0, 1400.0, 1600.0]],
            dtype=np.float64,
        )

        aligned = _aligned_selected_fiber_exposures(
            reference_parent_ids,
            addon_parent_ids,
            selected_ids,
            reference_exposure,
            reference_condition,
            addon_reference_component,
        )

        np.testing.assert_array_equal(aligned[0], [[20.0, 40.0]])
        np.testing.assert_array_equal(aligned[1], [[200.0, 400.0]])
        np.testing.assert_array_equal(aligned[2], [[1200.0, 1400.0]])

    def test_rejects_locked_id_missing_from_addon_parent(self) -> None:
        with self.assertRaisesRegex(
            StudyBootstrapNuisanceProviderError,
            "absent from the parent axis",
        ):
            _aligned_selected_fiber_exposures(
                np.asarray([10, 20, 30], dtype=np.int64),
                np.asarray([10, 30], dtype=np.int64),
                np.asarray([10, 20], dtype=np.int64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 2), dtype=np.float64),
                np.ones((2, 2), dtype=np.float64),
            )

    def test_rejects_duplicate_parent_fiber_ids(self) -> None:
        with self.assertRaisesRegex(
            StudyBootstrapNuisanceProviderError,
            "fiber IDs must be unique",
        ):
            _aligned_selected_fiber_exposures(
                np.asarray([10, 20, 30], dtype=np.int64),
                np.asarray([10, 20, 20], dtype=np.int64),
                np.asarray([10, 20], dtype=np.int64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
            )

    def test_rejects_selected_order_not_preserved_by_addon_parent(self) -> None:
        with self.assertRaisesRegex(
            StudyBootstrapNuisanceProviderError,
            "do not preserve parent order",
        ):
            _aligned_selected_fiber_exposures(
                np.asarray([10, 20, 30], dtype=np.int64),
                np.asarray([20, 10, 30], dtype=np.int64),
                np.asarray([10, 20], dtype=np.int64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
            )

    def test_rejects_exposure_width_outside_declared_parent(self) -> None:
        with self.assertRaisesRegex(
            StudyBootstrapNuisanceProviderError,
            "does not match its parent fiber IDs",
        ):
            _aligned_selected_fiber_exposures(
                np.asarray([10, 20, 30], dtype=np.int64),
                np.asarray([10, 20, 30], dtype=np.int64),
                np.asarray([10, 20], dtype=np.int64),
                np.ones((2, 2), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
                np.ones((2, 3), dtype=np.float64),
            )


if __name__ == "__main__":
    unittest.main()
