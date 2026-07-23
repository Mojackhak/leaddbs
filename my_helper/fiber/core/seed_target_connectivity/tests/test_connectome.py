"""Stable-ID connectome adapter contract tests."""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

import h5py
import numpy as np

from my_helper.fiber.core.seed_target_connectivity.connectome import (
    LeadDBSHDF5Connectome,
    open_connectome,
)
from my_helper.fiber.core.seed_target_connectivity.errors import ConnectomeError
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    line,
    mutate_fourth_row,
    write_hdf5_connectome,
)


class LeadDBSHDF5ConnectomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_preserves_canonical_ids_and_geometry_across_chunks(self) -> None:
        streamlines = [
            line((0, 0, 0), (1, 0, 0)),
            line((0, 1, 0), (1, 1, 0), (2, 1, 0)),
            line((0, 2, 0), (1, 2, 0)),
        ]
        path = write_hdf5_connectome(self.root / "connectome" / "data.mat", streamlines)
        adapter = LeadDBSHDF5Connectome(path)

        chunks = list(adapter.iter_chunks(2))

        self.assertEqual([chunk.fiber_ids.tolist() for chunk in chunks], [[1, 2], [3]])
        self.assertEqual(chunks[0].point_offsets.tolist(), [0, 2, 5])
        self.assertTrue(np.array_equal(chunks[0].streamline(0), streamlines[0]))
        self.assertTrue(np.array_equal(chunks[0].streamline(1), streamlines[1]))
        self.assertTrue(np.array_equal(chunks[1].streamline(0), streamlines[2]))
        self.assertEqual(adapter.metadata.n_fibers, 3)
        self.assertEqual(adapter.metadata.n_points, 7)
        self.assertEqual(adapter.metadata.connectome_id, "connectome")
        self.assertEqual(len(adapter.metadata.source_hash), 64)
        self.assertEqual(len(adapter.metadata.geometry_hash), 64)
        self.assertEqual(len(adapter.metadata.ordered_fiber_id_hash), 64)

    def test_point_balanced_ranges_preserve_all_fibers_and_bound_points(self) -> None:
        streamlines = [
            line(*((float(i), 0.0, 0.0) for i in range(length)))
            for length in (2, 8, 2, 8, 2)
        ]
        path = write_hdf5_connectome(self.root / "balanced" / "data.mat", streamlines)
        adapter = LeadDBSHDF5Connectome(path)

        ranges = adapter.point_balanced_ranges(
            10,
            coordinate_bytes_per_point=1,
        )
        chunks = list(
            adapter.iter_point_balanced_chunks(
                10,
                coordinate_bytes_per_point=1,
            )
        )

        self.assertEqual(ranges[0][0], 0)
        self.assertEqual(ranges[-1][1], len(streamlines))
        self.assertTrue(
            all(first[1] == second[0] for first, second in zip(ranges, ranges[1:]))
        )
        self.assertEqual(
            np.concatenate([chunk.fiber_ids for chunk in chunks]).tolist(),
            [1, 2, 3, 4, 5],
        )
        self.assertTrue(all(chunk.points.shape[0] <= 10 for chunk in chunks))
        self.assertEqual(sum(chunk.points.shape[0] for chunk in chunks), 22)
        self.assertTrue(
            all(
                chunk.point_offsets[-1] == chunk.points.shape[0]
                for chunk in chunks
            )
        )

    def test_point_id_validation_allocates_no_point_sized_expected_vector(self) -> None:
        path = write_hdf5_connectome(
            self.root / "no-repeat" / "data.mat",
            [
                line((0, 0, 0), (1, 0, 0)),
                line((0, 1, 0), (1, 1, 0), (2, 1, 0)),
            ],
        )
        adapter = LeadDBSHDF5Connectome(path)

        with mock.patch(
            "my_helper.fiber.core.seed_target_connectivity.connectome.np.repeat",
            side_effect=AssertionError("point-sized expected IDs are forbidden"),
            create=True,
        ):
            chunks = list(adapter.iter_chunks(2))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].fiber_ids.tolist(), [1, 2])

    def test_point_balanced_range_validation_rejects_invalid_budgets(self) -> None:
        path = write_hdf5_connectome(
            self.root / "invalid-budget" / "data.mat",
            [line((0, 0, 0), (1, 0, 0))],
        )
        adapter = LeadDBSHDF5Connectome(path)

        for budget in (0, False):
            with self.subTest(budget=budget), self.assertRaises(ConnectomeError):
                adapter.point_balanced_ranges(budget)
        with self.assertRaises(ConnectomeError):
            adapter.point_balanced_ranges(12, coordinate_bytes_per_point=0)

    def test_open_connectome_accepts_directory_or_data_file(self) -> None:
        path = write_hdf5_connectome(
            self.root / "named-connectome" / "data.mat",
            [line((0, 0, 0), (1, 0, 0))],
        )
        from_file = open_connectome(path)
        from_directory = open_connectome(path.parent)

        self.assertEqual(from_file.metadata.geometry_hash, from_directory.metadata.geometry_hash)
        self.assertEqual(from_directory.metadata.connectome_id, "named-connectome")

    def test_rejects_mismatched_point_level_canonical_ids(self) -> None:
        path = write_hdf5_connectome(
            self.root / "data.mat",
            [line((0, 0, 0), (1, 0, 0)), line((0, 1, 0), (1, 1, 0))],
        )
        mutate_fourth_row(path, value=99, point_index=1)

        with self.assertRaisesRegex(ConnectomeError, "canonical fiber ID"):
            list(LeadDBSHDF5Connectome(path).iter_chunks(2))

    def test_rejects_nonfinite_coordinates_and_short_fibers(self) -> None:
        invalid_sets = (
            [line((0, 0, 0), (np.nan, 0, 0))],
            [line((0, 0, 0))],
        )
        for index, streamlines in enumerate(invalid_sets):
            with self.subTest(index=index):
                path = write_hdf5_connectome(self.root / str(index) / "data.mat", streamlines)
                with self.assertRaises(ConnectomeError):
                    adapter = LeadDBSHDF5Connectome(path)
                    list(adapter.iter_chunks(1))

    def test_rejects_idx_point_count_mismatch_and_noninteger_lengths(self) -> None:
        for index, replacement in enumerate((3.0, 2.5)):
            with self.subTest(replacement=replacement):
                path = write_hdf5_connectome(
                    self.root / str(index) / "data.mat",
                    [line((0, 0, 0), (1, 0, 0))],
                )
                with h5py.File(path, "r+") as handle:
                    handle["idx"][0, 0] = replacement
                with self.assertRaises(ConnectomeError):
                    LeadDBSHDF5Connectome(path)

    def test_rejects_missing_datasets_and_invalid_chunk_size(self) -> None:
        path = self.root / "data.mat"
        with h5py.File(path, "w") as handle:
            handle.create_dataset("idx", data=np.array([[2.0]]))
        with self.assertRaisesRegex(ConnectomeError, "fibers"):
            LeadDBSHDF5Connectome(path)

        valid_path = write_hdf5_connectome(
            self.root / "valid" / "data.mat",
            [line((0, 0, 0), (1, 0, 0))],
        )
        with self.assertRaisesRegex(ConnectomeError, "chunk size"):
            list(LeadDBSHDF5Connectome(valid_path).iter_chunks(0))

    def test_metadata_is_deterministic_for_unchanged_source(self) -> None:
        path = write_hdf5_connectome(
            self.root / "data.mat",
            [line((0, 0, 0), (1, 0, 0)), line((0, 1, 0), (1, 1, 0))],
        )
        first = LeadDBSHDF5Connectome(path).metadata
        repeated = LeadDBSHDF5Connectome(path).metadata

        self.assertEqual(first, repeated)

    def test_load_streamlines_by_canonical_id_preserves_requested_order(self) -> None:
        streamlines = [
            line((0, 0, 0), (1, 0, 0)),
            line((0, 1, 0), (1, 1, 0), (2, 1, 0)),
            line((0, 2, 0), (1, 2, 0)),
        ]
        path = write_hdf5_connectome(self.root / "data.mat", streamlines)
        adapter = LeadDBSHDF5Connectome(path)

        loaded = adapter.load_streamlines([3, 1])

        self.assertTrue(np.array_equal(loaded[0], streamlines[2]))
        self.assertTrue(np.array_equal(loaded[1], streamlines[0]))
        with self.assertRaises(ConnectomeError):
            adapter.load_streamlines([1, 1])
        with self.assertRaises(ConnectomeError):
            adapter.load_streamlines([0])


if __name__ == "__main__":
    unittest.main()
