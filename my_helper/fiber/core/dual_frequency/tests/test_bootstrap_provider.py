from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

import numpy as np

from ..cache import ArtifactStore, sha256_file
from ..contracts import ArtifactRef, AxisRef, IndexedArrayView
from ..runtime.bootstrap_provider import (
    StudyBootstrapNuisanceProviderError,
    _aligned_selected_fiber_exposures,
    _materialize_columns,
)


class BootstrapProviderFiberAlignmentTests(unittest.TestCase):
    def test_materializes_only_selected_columns_from_indexed_view(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = AxisRef("rows", 2, "1" * 64)
            parent_columns = AxisRef("parent-columns", 4, "2" * 64)
            logical_columns = AxisRef("logical-columns", 3, "3" * 64)
            values = np.arange(8, dtype=np.float32).reshape(2, 4)
            parent_path = root / "parent.npy"
            positions_path = root / "positions.npy"
            np.save(parent_path, values, allow_pickle=False)
            np.save(
                positions_path,
                np.asarray([3, 1, 0], dtype=np.int64),
                allow_pickle=False,
            )

            def artifact(
                path: Path,
                *,
                dtype: str,
                axes: tuple[AxisRef, ...],
                units: str | None,
                space: str | None,
            ) -> ArtifactRef:
                return ArtifactRef(
                    kind=path.stem,
                    schema_version="dual_frequency_array_v1",
                    uri=path.as_uri(),
                    sha256=sha256_file(path),
                    dtype=dtype,
                    shape=tuple(axis.count for axis in axes),
                    axis_refs=axes,
                    axis_hashes=tuple(axis.sha256 for axis in axes),
                    units=units,
                    space=space,
                    producer_id="bootstrap_test",
                    producer_version="1",
                )

            parent = artifact(
                parent_path,
                dtype="float32",
                axes=(rows, parent_columns),
                units="V/m",
                space="synthetic",
            )
            selector = artifact(
                positions_path,
                dtype="int64",
                axes=(logical_columns,),
                units="index",
                space=None,
            )
            view = IndexedArrayView(
                parent=parent,
                row_positions=None,
                column_positions=selector,
                axis_refs=(rows, logical_columns),
            )
            output = _materialize_columns(
                ArtifactStore((root,)),
                view,
                np.asarray([2, 0], dtype=np.int64),
            )
            np.testing.assert_array_equal(output, values[:, [0, 3]])

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
