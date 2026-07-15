"""Pure right-canonical OSS sidecar merge contract tests."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[5] / "core" / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

MERGE = importlib.import_module("stnsnr_normative_fiber_oss_sidecar_merge")


class OSSSidecarMergeContractTests(unittest.TestCase):
    def test_exact_left_right_rows_use_max_probability_union(self) -> None:
        subjects = ("sub-01", "sub-02")
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)
        rows = {
            ("sub-01", "L"): (fiber_ids, np.asarray([0.2, 0.8, 0.3])),
            ("sub-01", "R"): (fiber_ids, np.asarray([0.7, 0.1, 0.4])),
            ("sub-02", "L"): (fiber_ids, np.asarray([0.9, 0.2, 0.1])),
            ("sub-02", "R"): (fiber_ids, np.asarray([0.3, 0.6, 0.5])),
        }

        merged = MERGE.merge_right_canonical_probabilities(
            subject_order=subjects,
            valid_fiber_ids=fiber_ids,
            side_probabilities=rows,
        )

        np.testing.assert_allclose(
            merged,
            np.asarray([[0.7, 0.8, 0.4], [0.9, 0.6, 0.5]], dtype=np.float32),
        )
        self.assertEqual(merged.dtype, np.float32)

    def test_missing_side_or_reordered_axis_is_rejected(self) -> None:
        fiber_ids = np.asarray([101, 107, 109], dtype=np.int64)
        complete = {
            ("sub-01", "L"): (fiber_ids, np.asarray([0.2, 0.8, 0.3])),
            ("sub-01", "R"): (fiber_ids, np.asarray([0.7, 0.1, 0.4])),
        }
        with self.assertRaisesRegex(ValueError, "exact"):
            MERGE.merge_right_canonical_probabilities(
                subject_order=("sub-01",),
                valid_fiber_ids=fiber_ids,
                side_probabilities={key: value for key, value in complete.items() if key[1] == "R"},
            )
        drifted = dict(complete)
        drifted[("sub-01", "L")] = (
            fiber_ids[::-1],
            np.asarray([0.3, 0.8, 0.2]),
        )
        with self.assertRaisesRegex(ValueError, "axis"):
            MERGE.merge_right_canonical_probabilities(
                subject_order=("sub-01",),
                valid_fiber_ids=fiber_ids,
                side_probabilities=drifted,
            )


if __name__ == "__main__":
    unittest.main()
