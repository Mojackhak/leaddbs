"""Tests for configured-data Task 17 candidate parity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from my_helper.fiber.pipelines import run_task17_candidate_parity as parity


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Task17CandidateParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.parent_exposure = np.asarray(
            [
                [2.0, 0.0, 3.0, 0.0],
                [2.0, 2.0, 0.0, 0.0],
                [0.0, 2.0, 3.0, 0.0],
            ],
            dtype=np.float32,
        )
        self.parent_ids = np.asarray([10, 20, 30, 40], dtype=np.int64)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _artifact(self, name: str, value: np.ndarray, axis: str) -> dict[str, object]:
        path = self.root / name
        np.save(path, value, allow_pickle=False)
        return {
            "path": str(path),
            "sha256": _sha(path),
            "dtype": value.dtype.name,
            "shape": list(value.shape),
            "feature_axis_sha256": hashlib.sha256(
                axis.encode("utf-8")
            ).hexdigest(),
        }

    def _plan(self, optimized_positions: list[int]) -> Path:
        optimized_ids = self.parent_ids[optimized_positions]
        optimized_exposure = self.parent_exposure[:, optimized_positions]
        parent_axis = "parent-axis"
        optimized_axis = "optimized-axis"
        document = {
            "schema_version": "dual_frequency_candidate_parity_plan_v1",
            "rows": [
                {
                    "row_id": "configured-fiber",
                    "model_family": "reference_fiber",
                    "tau": 2.0,
                    "coverage": 2,
                    "parent_exposure": self._artifact(
                        "parent_exposure.npy",
                        self.parent_exposure,
                        parent_axis,
                    ),
                    "parent_feature_ids": self._artifact(
                        "parent_ids.npy",
                        self.parent_ids,
                        parent_axis,
                    ),
                    "optimized_exposure": self._artifact(
                        "optimized_exposure.npy",
                        optimized_exposure,
                        optimized_axis,
                    ),
                    "optimized_feature_ids": self._artifact(
                        "optimized_ids.npy",
                        optimized_ids,
                        optimized_axis,
                    ),
                }
            ],
        }
        path = self.root / "plan.json"
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def test_full_and_every_fold_have_zero_false_negatives(self) -> None:
        plan = self._plan([0, 1, 2])
        output = parity.run(plan)
        first = output.read_bytes()
        self.assertEqual(parity.run(plan), output)
        self.assertEqual(output.read_bytes(), first)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["full_candidate_mismatch_count"], 0)
        self.assertEqual(report["fold_candidate_mismatch_count"], 0)
        self.assertEqual(report["candidate_false_negative_count"], 0)
        self.assertEqual(len(report["rows"][0]["folds"]), 3)

    def test_reports_parent_candidate_missing_from_optimized_axis(self) -> None:
        report = json.loads(
            parity.run(self._plan([0, 1])).read_text(encoding="utf-8")
        )
        self.assertGreater(report["candidate_false_negative_count"], 0)

    def test_rejects_optimized_values_that_differ_from_parent(self) -> None:
        plan = self._plan([0, 1, 2])
        document = json.loads(plan.read_text(encoding="utf-8"))
        optimized = Path(
            document["rows"][0]["optimized_exposure"]["path"]
        )
        changed = np.load(optimized, allow_pickle=False)
        changed[0, 0] += 1.0
        np.save(optimized, changed, allow_pickle=False)
        document["rows"][0]["optimized_exposure"]["sha256"] = _sha(optimized)
        plan.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(parity.CandidateParityError):
            parity.run(plan)


if __name__ == "__main__":
    unittest.main()
