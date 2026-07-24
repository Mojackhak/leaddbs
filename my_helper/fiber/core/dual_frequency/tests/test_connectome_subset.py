"""Deterministic tests for exact connectome subsetting and pPAM aggregation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from scipy.io import savemat

from dual_frequency.backends.activation.canonical_mapping import CanonicalMappingError
from dual_frequency.instrumentation import performance_delta, performance_snapshot
from dual_frequency.runtime.connectome_subset import (
    ConnectomeSubsetError,
    aggregate_activation_probabilities,
    load_local_activation_status,
    write_filtered_connectome,
)


_PARENT_LENGTHS = np.asarray([2, 1, 3], dtype=np.int64)
_PARENT_FIBERS = np.asarray(
    [
        [10.0, 11.0, 20.0, 30.0, 31.0, 32.0],
        [110.0, 111.0, 120.0, 130.0, 131.0, 132.0],
        [210.0, 211.0, 220.0, 230.0, 231.0, 232.0],
        [1.0, 1.0, 2.0, 3.0, 3.0, 3.0],
    ],
    dtype=np.float64,
)


def _write_hdf5_connectome(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset("fibers", data=_PARENT_FIBERS)
        handle.create_dataset("idx", data=_PARENT_LENGTHS.reshape(1, -1))


def _write_transposed_hdf5_connectome(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset("fibers", data=_PARENT_FIBERS.T)
        handle.create_dataset("idx", data=_PARENT_LENGTHS.reshape(-1, 1))


def _write_axon_state(
    path: Path,
    *,
    local_ids: list[int] | list[float],
    statuses: list[int],
) -> Path:
    if len(local_ids) != len(statuses):
        raise AssertionError("Axon_state fixture IDs and statuses must have equal length")
    fibers = np.zeros((len(local_ids), 5), dtype=np.float64)
    fibers[:, 0] = np.arange(len(local_ids), dtype=np.float64)
    fibers[:, 3] = np.asarray(local_ids, dtype=np.float64)
    fibers[:, 4] = np.asarray(statuses, dtype=np.float64)
    savemat(path, {"fibers": fibers})
    return path


class ConnectomeSubsetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_hdf5_subset_preserves_requested_order_and_assigns_local_ids(self) -> None:
        source = self.root / "parent.mat"
        target = self.root / "subset.mat"
        _write_hdf5_connectome(source)

        before = performance_snapshot()
        result = write_filtered_connectome(
            source,
            target,
            np.asarray([3, 1], dtype=np.int64),
        )
        events = performance_delta(before, performance_snapshot())

        self.assertEqual(result.path, target.resolve())
        np.testing.assert_array_equal(result.feature_ids, [3, 1])
        np.testing.assert_array_equal(result.local_fiber_ids, [1, 2])
        np.testing.assert_array_equal(result.point_counts, [3, 2])
        self.assertEqual(result.parent_fiber_count, 3)
        self.assertEqual(
            sum(events["keyed"]["connectome_row4_audit_pass"].values()),
            1,
        )
        self.assertEqual(
            sum(events["keyed"]["filtered_connectome_build"].values()),
            1,
        )

        with h5py.File(target, "r") as handle:
            fibers = handle["fibers"][:]
            np.testing.assert_array_equal(
                fibers[:3],
                _PARENT_FIBERS[:3, [3, 4, 5, 0, 1]],
            )
            np.testing.assert_array_equal(fibers[3], [1, 1, 1, 2, 2])
            np.testing.assert_array_equal(handle["idx"][:], [[3.0, 2.0]])
            np.testing.assert_array_equal(handle["origNum"][:], [[2.0]])

    def test_classic_mat_subset_accepts_transposed_fibers(self) -> None:
        source = self.root / "classic-parent.mat"
        target = self.root / "classic-subset.mat"
        savemat(
            source,
            {
                "fibers": _PARENT_FIBERS.T,
                "idx": _PARENT_LENGTHS.reshape(-1, 1),
            },
        )
        self.assertFalse(h5py.is_hdf5(source))

        result = write_filtered_connectome(
            source,
            target,
            np.asarray([2, 3], dtype=np.int64),
        )

        np.testing.assert_array_equal(result.feature_ids, [2, 3])
        np.testing.assert_array_equal(result.point_counts, [1, 3])
        with h5py.File(target, "r") as handle:
            fibers = handle["fibers"][:]
            np.testing.assert_array_equal(
                fibers[:3],
                _PARENT_FIBERS[:3, [2, 3, 4, 5]],
            )
            np.testing.assert_array_equal(fibers[3], [1, 2, 2, 2])
            np.testing.assert_array_equal(handle["idx"][:], [[1.0, 3.0]])
            np.testing.assert_array_equal(handle["origNum"][:], [[2.0]])

    def test_hdf5_subset_accepts_transposed_fibers(self) -> None:
        source = self.root / "transposed-parent.mat"
        target = self.root / "transposed-subset.mat"
        _write_transposed_hdf5_connectome(source)

        result = write_filtered_connectome(
            source,
            target,
            np.asarray([2, 1], dtype=np.int64),
        )

        np.testing.assert_array_equal(result.feature_ids, [2, 1])
        np.testing.assert_array_equal(result.point_counts, [1, 2])
        with h5py.File(target, "r") as handle:
            fibers = handle["fibers"][:]
            np.testing.assert_array_equal(
                fibers[:3],
                _PARENT_FIBERS[:3, [2, 0, 1]],
            )
            np.testing.assert_array_equal(fibers[3], [1, 2, 2])
            np.testing.assert_array_equal(handle["idx"][:], [[1.0, 2.0]])
            np.testing.assert_array_equal(handle["origNum"][:], [[2.0]])

    def test_rejects_malformed_and_out_of_range_feature_ids(self) -> None:
        source = self.root / "parent.mat"
        _write_hdf5_connectome(source)

        malformed_cases = (
            (
                "wrong-dtype",
                np.asarray([1], dtype=np.int32),
                "exact int64 dtype",
            ),
            (
                "duplicate",
                np.asarray([1, 1], dtype=np.int64),
                "unique fiber IDs",
            ),
        )
        for label, feature_ids, message in malformed_cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(CanonicalMappingError, message):
                    write_filtered_connectome(
                        source,
                        self.root / f"malformed-{label}.mat",
                        feature_ids,
                    )

        for label, feature_ids in (
            ("zero", np.asarray([0], dtype=np.int64)),
            ("above-parent", np.asarray([4], dtype=np.int64)),
        ):
            with self.subTest(case=label):
                with self.assertRaisesRegex(
                    ConnectomeSubsetError,
                    "final fiber ID is outside the formal connectome",
                ):
                    write_filtered_connectome(
                        source,
                        self.root / f"out-of-range-{label}.mat",
                        feature_ids,
                    )

    def test_refuses_to_overwrite_an_existing_filtered_target(self) -> None:
        source = self.root / "parent.mat"
        target = self.root / "existing-target.mat"
        _write_hdf5_connectome(source)
        target.write_bytes(b"existing artifact\n")

        with self.assertRaisesRegex(
            ConnectomeSubsetError,
            "refusing to overwrite filtered connectome",
        ):
            write_filtered_connectome(
                source,
                target,
                np.asarray([1], dtype=np.int64),
            )

        self.assertEqual(target.read_bytes(), b"existing artifact\n")

    def test_ten_axon_state_mat_files_produce_activation_count_over_ten(self) -> None:
        paths = []
        for sample_index in range(10):
            paths.append(
                _write_axon_state(
                    self.root / f"Axon_state_{sample_index + 1}.mat",
                    local_ids=[1, 2, 3, 4],
                    statuses=[
                        0,
                        int(sample_index < 3),
                        int(sample_index < 7),
                        1,
                    ],
                )
            )

        probabilities = aggregate_activation_probabilities(
            paths,
            np.asarray([900, 100, 700, 300], dtype=np.int64),
        )

        np.testing.assert_array_equal(
            probabilities,
            np.asarray([0.0, 0.3, 0.7, 1.0], dtype=np.float32),
        )
        self.assertEqual(probabilities.dtype, np.dtype(np.float32))
        self.assertFalse(probabilities.flags.writeable)

    def test_aggregation_rejects_local_axis_mismatch(self) -> None:
        paths = []
        for sample_index in range(10):
            local_ids = [1, 2, 4] if sample_index == 0 else [1, 2, 3]
            paths.append(
                _write_axon_state(
                    self.root / f"axis-{sample_index + 1}.mat",
                    local_ids=local_ids,
                    statuses=[1, 0, 1],
                )
            )

        with self.assertRaisesRegex(
            ConnectomeSubsetError,
            r"sample 1 local axis mismatch: missing=\[3\], extra=\[4\]",
        ):
            aggregate_activation_probabilities(
                paths,
                np.asarray([10, 20, 30], dtype=np.int64),
            )

    def test_axon_state_rejects_inconsistent_status_for_one_local_fiber(self) -> None:
        path = _write_axon_state(
            self.root / "inconsistent.mat",
            local_ids=[1, 1, 2],
            statuses=[0, 1, 0],
        )

        with self.assertRaisesRegex(
            ConnectomeSubsetError,
            "inconsistent status for local fiber 1",
        ):
            load_local_activation_status(path)

    def test_axon_state_rejects_unknown_status_code(self) -> None:
        path = _write_axon_state(
            self.root / "unknown-status.mat",
            local_ids=[1, 2],
            statuses=[1, 9],
        )

        with self.assertRaisesRegex(
            ConnectomeSubsetError,
            "activated, inactive, CSF, or electrode-intersection codes",
        ):
            load_local_activation_status(path)


if __name__ == "__main__":
    unittest.main()
