"""Tests for final-linked ULF normative-fiber plain and burden controls."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[2] / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from stnsnr_ulf_normative_fiber_sensitivity_observed import (  # noqa: E402
    run_configured_plain_burden_controls,
)


class ULFPlainBurdenControlTests(unittest.TestCase):
    def _target(
        self,
        root: Path,
        *,
        branch: str = "delta_hf_adjusted",
        include_delta: bool = True,
        include_matched_hf: bool = True,
    ) -> SimpleNamespace:
        subject_order = tuple(f"sub-{index:02d}" for index in range(1, 9))
        plain_peaks = np.array([20, 25, 21, 30, 24, 28, 23, 35], dtype=np.float32)
        ulf_only = np.zeros((8, 10), dtype=np.float32)
        ulf_only[:, 0] = plain_peaks
        ulf_only[:, 1] = np.array([15, 14, 16, 13, 17, 12, 18, 11], dtype=np.float32)
        ulf_only[:4, 2] = np.array([11, 12, 13, 14], dtype=np.float32)
        ulf_only[0, 9] = 1000.0

        ulf_total = ulf_only + 2.0
        hf_component = np.zeros_like(ulf_only)
        hf_component[:, 0] = np.linspace(6.0, 6.7, 8)
        hf_component[:, 2] = np.arange(50.0, 58.0)
        hf_component[0, 9] = 100.0

        exposure_path = root / "ulf_only.npy"
        ulf_total_path = root / "ulf_total.npy"
        hf_component_path = root / "hf_component.npy"
        feature_ids_path = root / "ulf_feature_ids.npy"
        np.save(exposure_path, ulf_only)
        np.save(ulf_total_path, ulf_total)
        np.save(hf_component_path, hf_component)
        np.save(feature_ids_path, np.arange(10, dtype=np.int64))

        y_post = np.array([18, 21, 17, 25, 19, 24, 16, 23], dtype=float)
        y_hf_ref = np.array([30, 28, 35, 27, 33, 31, 26, 34], dtype=float)
        net_score = np.array([1, 4, 2, 8, 5, 7, 3, 6], dtype=float)
        scores_path = root / "scores.csv"
        with scores_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["subject_id", "Y_post", "Y_HF_ref", "NetULFFiberScore"],
            )
            writer.writeheader()
            for values in zip(subject_order, y_post, y_hf_ref, net_score, strict=True):
                writer.writerow(dict(zip(writer.fieldnames, values, strict=True)))

        delta_full_path = None
        delta_fold_path = None
        if include_delta:
            delta = np.array([2, 5, 1, 4, 8, 3, 7, 6], dtype=float)
            delta_full_path = root / "delta_full.npy"
            delta_fold_path = root / "delta_folds.npy"
            np.save(delta_full_path, delta)
            np.save(delta_fold_path, np.tile(delta, (8, 1)))

        matched_hf_final = None
        matched_hf_paths: dict[str, Path] = {}
        if include_matched_hf:
            hf_reference = np.zeros_like(ulf_only)
            hf_reference[:, 0] = 6.0
            hf_reference[:, 1] = 7.0
            hf_reference[:2, 2] = 8.0
            hf_reference_path = root / "hf_reference.npy"
            hf_feature_ids_path = root / "hf_feature_ids.npy"
            np.save(hf_reference_path, hf_reference)
            np.save(hf_feature_ids_path, np.arange(10, dtype=np.int64))
            matched_hf_final = SimpleNamespace(
                final_model_id="matched-hf-final",
                selected_tau=5.0,
                selected_coverage=3,
            )
            matched_hf_paths = {
                "exposure": hf_reference_path,
                "feature_ids": hf_feature_ids_path,
            }

        return SimpleNamespace(
            final_model_id="realized-ulf-final",
            final_record_hash="f" * 64,
            final_branch=branch,
            selected_tau=10.0,
            selected_coverage=3,
            subject_order=subject_order,
            output_root=root / "controls",
            exposure_path=exposure_path,
            scores_path=scores_path,
            feature_ids_path=feature_ids_path,
            component_paths={
                "ulf_component_exposure": ulf_total_path,
                "hf_component_exposure": hf_component_path,
            },
            delta_full_path=delta_full_path,
            delta_fold_path=delta_fold_path,
            matched_hf_final=matched_hf_final,
            matched_hf_paths=matched_hf_paths,
            hf_overlap_tau=5.0,
        )

    def _run(self, target: SimpleNamespace) -> dict[str, object]:
        return run_configured_plain_burden_controls(target, enabled_analyses=())

    def test_plain_top5_uses_touched_selected_candidate_fibers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = self._target(Path(tmp))
            result = self._run(target)
            with Path(result["control_table"]).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        plain = result["analyses"]["plain_ulf_only_exposure"]
        self.assertEqual(result["status"], "complete")
        self.assertEqual(plain["status"], "complete")
        self.assertEqual(plain["candidate_fiber_count"], 3)
        self.assertEqual(float(rows[0]["PlainULFOnlyExposureTop5"]), 20.0)
        self.assertEqual(int(rows[0]["PlainULFOnlyTouchedCount"]), 3)
        self.assertNotEqual(float(rows[0]["PlainULFOnlyExposureTop5"]), 1000.0)

    def test_adjusted_comparisons_use_realized_branch_nuisance_and_keep_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = self._target(Path(tmp))
            result = self._run(target)

        comparisons = result["analyses"]["branch_nuisance_model_comparisons"]
        self.assertEqual(comparisons["status"], "complete")
        self.assertEqual(comparisons["realized_final_branch"], "delta_hf_adjusted")
        self.assertEqual(comparisons["nuisance_columns"], ["Y_HF_ref", "DeltaHFScore"])
        self.assertEqual(
            comparisons["models"]["joint"]["predictor_names"],
            ["NetULFFiberScore", "PlainULFOnlyExposureTop5", "Y_HF_ref", "DeltaHFScore"],
        )
        self.assertEqual(result["final_model_id"], target.final_model_id)
        self.assertEqual(result["final_record_hash"], target.final_record_hash)
        self.assertEqual(result["classification_feedback"], "none")
        self.assertNotIn("classification_changes", json.dumps(result, sort_keys=True))

    def test_no_delta_final_uses_y_hf_ref_only_nuisance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = self._target(
                Path(tmp),
                branch="no_delta_hf",
                include_delta=False,
            )
            result = self._run(target)

        comparisons = result["analyses"]["branch_nuisance_model_comparisons"]
        self.assertEqual(comparisons["status"], "complete")
        self.assertEqual(comparisons["nuisance_columns"], ["Y_HF_ref"])
        self.assertEqual(
            comparisons["models"]["joint"]["predictor_names"],
            ["NetULFFiberScore", "PlainULFOnlyExposureTop5", "Y_HF_ref"],
        )

    def test_hf_out_of_support_uses_matched_hf_candidate_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = self._target(Path(tmp))
            result = self._run(target)
            with Path(result["control_table"]).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        burden = result["analyses"]["hf_out_of_support_burden"]
        self.assertEqual(burden["status"], "complete")
        self.assertEqual(burden["matched_hf_final_model_id"], "matched-hf-final")
        self.assertEqual(burden["hf_candidate_fiber_count"], 2)
        self.assertEqual(float(rows[0]["PlainHFOutSupportTop5"]), 100.0)
        self.assertEqual(float(rows[1]["PlainHFOutSupportTop5"]), 51.0)

    def test_missing_inputs_mark_only_affected_controls_not_computable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = self._target(
                Path(tmp),
                include_delta=False,
                include_matched_hf=False,
            )
            result = self._run(target)

        analyses = result["analyses"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(analyses["plain_ulf_only_exposure"]["status"], "complete")
        self.assertEqual(
            analyses["branch_nuisance_model_comparisons"],
            {
                "status": "not_computable",
                "reason": "missing_final_branch_delta_hf",
                "realized_final_branch": "delta_hf_adjusted",
                "nuisance_columns": ["Y_HF_ref", "DeltaHFScore"],
            },
        )
        self.assertEqual(analyses["hf_out_of_support_burden"]["status"], "not_computable")
        self.assertEqual(
            analyses["hf_out_of_support_burden"]["reason"],
            "missing_matched_hf_final",
        )


if __name__ == "__main__":
    unittest.main()
