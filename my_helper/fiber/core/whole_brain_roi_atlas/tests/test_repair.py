from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from my_helper.fiber.core.seed_target_connectivity.models import TargetFiberMembership
from my_helper.fiber.core.whole_brain_roi_atlas.repair import (
    parse_itksnap_label_file,
    remap_target_membership,
)


class HybraPDRepairTests(unittest.TestCase):
    def test_parse_itksnap_table_accepts_unicode_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.label"
            lines = ["# header", '0 0 0 0 0 0 0 "Clear Label"']
            lines.extend(
                f"{label_id} 1 2 3 1 1 1 “Region {label_id}”"
                for label_id in range(1, 199)
            )
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records = parse_itksnap_label_file(path)
        self.assertEqual(len(records), 199)
        self.assertEqual(records[198], "Region 198")

    def test_membership_is_reordered_by_label_id_without_changing_sets(self) -> None:
        old = TargetFiberMembership(
            target_ids=("lh/OldA", "lh/OldB"),
            indptr=np.asarray([0, 2, 5], dtype=np.int64),
            fiber_ids=np.asarray([1, 4, 2, 3, 9], dtype=np.int64),
        )
        migrated = remap_target_membership(
            old,
            {"lh/OldA": 10, "lh/OldB": 20},
            {"lh/NewA": 10, "lh/NewB": 20},
            ("lh/NewB", "lh/NewA"),
        )
        self.assertEqual(migrated.target_ids, ("lh/NewB", "lh/NewA"))
        np.testing.assert_array_equal(migrated.ids_for("lh/NewB"), [2, 3, 9])
        np.testing.assert_array_equal(migrated.ids_for("lh/NewA"), [1, 4])


if __name__ == "__main__":
    unittest.main()
