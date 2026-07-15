"""Contract tests for fixed-axis configured OSS numerical scoring.

The numerical backend receives pPAM probabilities on the immutable realized
fiber axis. It must threshold probabilities at ``>= 0.5`` before any fit,
keep that axis fixed, re-estimate fold-local weights and signed score support,
and apply the explicit six-field normative-fiber score policy through the
shared score kernel. OSS support is reporting-only and cannot feed source,
prediction, branch-role, or final-model classification.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import stnsnr_normative_fiber_oss_sensitivity as module
from stnsnr_normative_fiber_score import (
    NormativeFiberScoreConfig,
    score_support_fields,
)


SUPPORT_FIELDS = {
    "n_positive_valid_fibers",
    "n_negative_valid_fibers",
    "sweet_fraction_requested",
    "sour_fraction_requested",
    "weighted_peak_fraction_requested",
    "sweet_selected_k_min",
    "sour_selected_k_min",
    "weighted_peak_k_min",
    "sweet_percentage_count",
    "sour_percentage_count",
    "sweet_actual_selected_count",
    "sour_actual_selected_count",
    "sweet_actual_peak_count",
    "sour_actual_peak_count",
    "sweet_minimum_count_dominated",
    "sour_minimum_count_dominated",
    "sweet_peak_minimum_count_dominated",
    "sour_peak_minimum_count_dominated",
    "fiber_score_support_status",
    "sweet_selected_fiber_id_hash",
    "sour_selected_fiber_id_hash",
}


class ConfiguredOSSScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ppam = np.asarray(
            [
                [0.49, 0.50, 0.90, 0.10, 0.75, 0.90],
                [0.60, 0.20, 0.85, 0.55, 0.10, 0.90],
                [0.10, 0.70, 0.30, 0.80, 0.65, 0.90],
                [0.80, 0.10, 0.60, 0.20, 0.90, 0.90],
                [0.25, 0.95, 0.40, 0.65, 0.20, 0.90],
                [0.90, 0.35, 0.10, 0.75, 0.55, 0.90],
                [0.45, 0.80, 0.70, 0.30, 0.15, 0.90],
                [0.70, 0.40, 0.20, 0.90, 0.60, 0.90],
            ],
            dtype=np.float32,
        )
        self.fiber_ids = np.asarray([101, 103, 107, 109, 113, 127], dtype=np.int64)
        self.y_post = np.asarray([31, 19, 28, 16, 25, 13, 22, 10], dtype=float)
        self.nuisance = np.asarray([40, 43, 39, 45, 41, 47, 42, 46], dtype=float)
        self.score_config = NormativeFiberScoreConfig(
            sweet_fraction=0.50,
            sour_fraction=0.50,
            weighted_peak_fraction=0.50,
            sweet_selected_min_count=2,
            sour_selected_min_count=2,
            weighted_peak_min_count=1,
        )

    def test_thresholds_ppam_at_greater_than_or_equal_to_point_five(self) -> None:
        binary = module._threshold_ppam(
            np.asarray([[0.49, 0.50, 0.90]], dtype=np.float32)
        )

        np.testing.assert_array_equal(binary, [[0.0, 1.0, 1.0]])
        self.assertEqual(binary.dtype, np.float32)

    def test_full_sample_uses_fixed_axis_shared_kernel_and_explicit_policy(self) -> None:
        with patch.object(
            module,
            "fiber_net_score",
            wraps=module.fiber_net_score,
        ) as score_kernel:
            weights, scores = module._full_sample_weights_scores(
                x=self.ppam,
                fiber_ids=self.fiber_ids,
                y_post=self.y_post,
                nuisance=self.nuisance,
                scale_direction="lower",
                score_config=self.score_config,
            )

        score_kernel.assert_called_once()
        exposure, observed_weights, candidate_mask = score_kernel.call_args.args
        np.testing.assert_array_equal(exposure[0], [0.0, 1.0, 1.0, 0.0, 1.0, 1.0])
        np.testing.assert_array_equal(candidate_mask, np.ones(self.fiber_ids.size, dtype=bool))
        np.testing.assert_array_equal(observed_weights, weights)
        self.assertEqual(score_kernel.call_args.kwargs["score_config"], self.score_config)
        self.assertTrue(np.isnan(weights[-1]))
        self.assertEqual(set(score_support_fields(scores, self.score_config)), SUPPORT_FIELDS)

    def test_loocv_reestimates_fold_weights_and_emits_complete_support(self) -> None:
        with patch.object(
            module,
            "fiber_net_score",
            wraps=module.fiber_net_score,
        ) as score_kernel:
            observed, fold_rows = module._loocv_oss(
                x=self.ppam,
                fiber_ids=self.fiber_ids,
                y_post=self.y_post,
                nuisance=self.nuisance,
                scale_direction="lower",
                score_config=self.score_config,
            )

        self.assertEqual(len(fold_rows), self.ppam.shape[0])
        self.assertEqual(score_kernel.call_count, self.ppam.shape[0])
        fold_weights = []
        fold_support_identities = set()
        for call, row in zip(score_kernel.call_args_list, fold_rows, strict=True):
            exposure, weights, candidate_mask = call.args
            np.testing.assert_array_equal(exposure, module._threshold_ppam(self.ppam))
            np.testing.assert_array_equal(
                candidate_mask,
                np.ones(self.fiber_ids.size, dtype=bool),
            )
            self.assertEqual(call.kwargs["score_config"], self.score_config)
            self.assertEqual(row["n_fixed_axis_fibers"], self.fiber_ids.size)
            self.assertTrue(SUPPORT_FIELDS.issubset(row))
            fold_weights.append(np.nan_to_num(weights, nan=99.0))
            fold_support_identities.add(
                (
                    row["sweet_selected_fiber_id_hash"],
                    row["sour_selected_fiber_id_hash"],
                )
            )

        self.assertGreater(
            len({tuple(values.tolist()) for values in fold_weights}),
            1,
        )
        self.assertGreater(len(fold_support_identities), 1)
        self.assertTrue(observed["all_predictions_finite"])
        self.assertEqual(observed["n_fixed_axis_fibers"], self.fiber_ids.size)
        prohibited_tokens = (
            "source_status",
            "prediction_status",
            "threshold_source",
            "branch_role",
            "final_role",
        )
        for row in [observed, *fold_rows]:
            self.assertFalse(any(token in row for token in prohibited_tokens))

    def test_configured_role_precedes_legacy_model_id_fallback(self) -> None:
        configured_ulf = SimpleNamespace(
            model_family="ulf_fiber",
            final_branch="delta_hf_adjusted",
            model_id="B_DTOR",
        )
        branch_only = SimpleNamespace(final_branch="hf_source", model_id="D_DTOR")

        self.assertEqual(module._target_model_family(configured_ulf), "ulf_fiber")
        self.assertEqual(module._target_model_family(branch_only), "hf_fiber")
        self.assertEqual(
            module._target_model_family(SimpleNamespace(model_id="B_DTOR")),
            "hf_fiber",
        )
        self.assertEqual(
            module._target_model_family(SimpleNamespace(model_id="D_DTOR")),
            "ulf_fiber",
        )


if __name__ == "__main__":
    unittest.main()
