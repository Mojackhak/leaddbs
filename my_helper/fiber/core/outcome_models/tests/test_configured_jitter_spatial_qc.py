"""Configured jitter spatial-robustness and DeltaHF support tests."""

from __future__ import annotations

import csv
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[2] / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))


DIRECT_JITTER = importlib.import_module("stnsnr_direct_voxel_formal_jitter")
FIBER_JITTER = importlib.import_module("stnsnr_normative_fiber_formal_jitter")
DIRECT_OBSERVED = importlib.import_module("stnsnr_ulf_direct_voxel_observed")
FIBER_OBSERVED = importlib.import_module("stnsnr_ulf_normative_fiber_observed")
SCORE_MODULE = importlib.import_module("stnsnr_normative_fiber_score")


class ConfiguredDeltaHFSupportTests(unittest.TestCase):
    @staticmethod
    def _target(root: Path) -> SimpleNamespace:
        scores_path = root / "scores.csv"
        with scores_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["subject_id", "Y_HF_ref"],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {"subject_id": "sub-01", "Y_HF_ref": 1.0},
                    {"subject_id": "sub-02", "Y_HF_ref": 2.0},
                ]
            )
        y_base_path = root / "y_base.npy"
        np.save(y_base_path, np.array([10.0, 11.0]))
        return SimpleNamespace(
            matched_hf_final=SimpleNamespace(
                selected_tau=10.0,
                selected_coverage=1,
            ),
            y_base_path=y_base_path,
            scores_path=scores_path,
            scale_direction="lower",
            subject_order=("sub-01", "sub-02"),
            score_config=SCORE_MODULE.NormativeFiberScoreConfig(
                sweet_fraction=0.2,
                sour_fraction=0.15,
                weighted_peak_fraction=0.25,
                sweet_selected_min_count=4,
                sour_selected_min_count=3,
                weighted_peak_min_count=2,
            ),
        )

    def test_each_fold_support_is_checked_against_every_subject(self) -> None:
        n_features = 21
        reprogrammed = np.zeros((2, n_features), dtype=np.float32)
        reprogrammed[0, 0] = 20.0
        reprogrammed[1, :] = 20.0
        all_features = np.ones(n_features, dtype=bool)
        first_feature_only = np.zeros(n_features, dtype=bool)
        first_feature_only[0] = True

        for name, jitter_module, observed_module in (
            ("direct", DIRECT_JITTER, DIRECT_OBSERVED),
            ("fiber", FIBER_JITTER, FIBER_OBSERVED),
        ):
            with self.subTest(model=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = self._target(root)
                geometry = {
                    "hf_reference": reprogrammed.copy(),
                    "hf_reprogrammed": reprogrammed.copy(),
                }
                if name == "direct":
                    geometry.update(
                        {
                            "hf_reprogrammed_support": reprogrammed.copy(),
                            "matched_hf_candidate_indices_in_support": np.arange(
                                n_features,
                                dtype=np.int64,
                            ),
                        }
                    )
                    full_result = {
                        "delta": np.zeros(2),
                        "valid_mask": all_features,
                        "s_tau": np.ones((2, n_features), dtype=bool),
                    }
                    fold_results = iter(
                        [
                            {"delta": np.zeros(2), "valid_mask": first_feature_only},
                            {"delta": np.zeros(2), "valid_mask": all_features},
                        ]
                    )
                else:
                    geometry["matched_fiber_ids"] = np.arange(
                        1,
                        n_features + 1,
                        dtype=np.int64,
                    )
                    full_result = {
                        "delta": np.zeros(2),
                        "candidate": all_features,
                        "weights": np.ones(n_features),
                        "s_tau": np.ones((2, n_features), dtype=bool),
                    }
                    fold_results = iter(
                        [
                            {
                                "delta": np.zeros(2),
                                "candidate": first_feature_only,
                                "weights": np.where(first_feature_only, 1.0, np.nan),
                            },
                            {
                                "delta": np.zeros(2),
                                "candidate": all_features,
                                "weights": np.ones(n_features),
                            },
                        ]
                    )

                with (
                    mock.patch.object(
                        observed_module,
                        "fit_hf_delta_full",
                        return_value=full_result,
                    ),
                    mock.patch.object(
                        observed_module,
                        "fit_hf_delta_fold",
                        side_effect=lambda *args, **kwargs: next(fold_results),
                    ),
                ):
                    result = jitter_module._default_configured_delta_builder(
                        target,
                        geometry,
                    )

                support = result["support"]
                self.assertEqual(result["status"], "invalid_extreme_out_of_support")
                self.assertEqual(support["fold_subject_fraction_shape"], [2, 2])
                self.assertEqual(support["n_fold_subject_pairs_evaluated"], 4)
                self.assertEqual(support["n_extreme_fold_subject_pairs"], 1)
                self.assertAlmostEqual(
                    support["maximum_out_support_fraction"],
                    20.0 / 21.0,
                )

    def test_exact_extreme_threshold_is_not_extreme(self) -> None:
        subject_values = np.zeros(2, dtype=float)
        self.assertEqual(
            DIRECT_JITTER._support_category(
                subject_values,
                np.array([[0.95, 0.0], [0.0, 0.0]]),
                False,
            ),
            "adequate",
        )
        self.assertEqual(
            DIRECT_JITTER._support_category(
                subject_values,
                np.array([[np.nextafter(0.95, 1.0), 0.0], [0.0, 0.0]]),
                False,
            ),
            "invalid_extreme_out_of_support",
        )


class ConfiguredJitterSpatialRobustnessTests(unittest.TestCase):
    @staticmethod
    def _target(root: Path, family: str) -> SimpleNamespace:
        valid_ids = root / "valid_feature_ids.npy"
        np.save(valid_ids, np.arange(3, dtype=np.int64))
        return SimpleNamespace(
            model_family=family,
            output_root=root,
            final_model_id=f"final-{family}",
            final_record_hash=f"hash-{family}",
            selected_tau=10.0,
            selected_coverage=1,
            final_branch="hf_source",
            hf_overlap_tau=None,
            valid_feature_ids_path=valid_ids,
            score_config=SCORE_MODULE.NormativeFiberScoreConfig(
                sweet_fraction=0.2,
                sour_fraction=0.15,
                weighted_peak_fraction=0.25,
                sweet_selected_min_count=4,
                sour_selected_min_count=3,
                weighted_peak_min_count=2,
            ),
        )

    def test_direct_and_fiber_jitter_report_bounded_spatial_qc(self) -> None:
        observed_weights = np.array([1.0, -2.0, np.nan, 4.0], dtype=np.float32)
        observed_valid = np.isfinite(observed_weights)
        jitter_maps = (
            np.array([1.0, -1.0, np.nan, 2.0], dtype=np.float32),
            np.array([-1.0, -2.0, 3.0, 4.0], dtype=np.float32),
        )
        expected_mean = np.array([0.0, -1.5, 3.0, 3.0], dtype=np.float32)
        expected_sd = np.array(
            [np.sqrt(2.0), np.sqrt(0.5), np.nan, np.sqrt(2.0)],
            dtype=np.float32,
        )

        for family, jitter_module, unit in (
            ("hf_voxel", DIRECT_JITTER, "voxel"),
            ("hf_fiber", FIBER_JITTER, "fiber"),
        ):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = self._target(root, family)
                branch_maps = iter(jitter_maps)

                def branch_fitter(target, geometry, delta):
                    weights = next(branch_maps)
                    return {
                        "status": "complete",
                        "q2": 0.25,
                        "_spatial_weights": weights,
                        "_spatial_valid": np.isfinite(weights),
                    }

                with mock.patch.object(
                    jitter_module,
                    "_configured_observed_weights",
                    create=True,
                    return_value=(observed_weights, observed_valid),
                ):
                    result = jitter_module.run_configured_jitter(
                        target,
                        n_jitters=2,
                        jitter_fwhm_mm=2.0,
                        seed=42,
                        geometry_builder=lambda target, rng, sigma: {},
                        branch_fitter=branch_fitter,
                    )

                spatial = result["spatial_robustness"]
                artifacts = spatial["map_variability_artifacts"]
                self.assertEqual(result["status"], "complete")
                self.assertTrue(result["selected_source_identity_fixed"])
                self.assertEqual(result["classification_feedback"], "none")
                if family == "hf_fiber":
                    self.assertEqual(
                        result["checkpoint"]["method_version"],
                        "normative_fiber_minimum_count_spatial_jitter_v3",
                    )
                    self.assertEqual(result["score"]["sweet_selected_min_count"], 4)
                self.assertEqual(spatial["status"], "complete")
                self.assertEqual(spatial["feature_unit"], unit)
                self.assertEqual(spatial["completed_replicates"], 2)
                self.assertEqual(spatial["streaming_memory_complexity"], "O(n_features)")
                self.assertAlmostEqual(
                    result["replicates"][1]["valid_support_jaccard"],
                    0.75,
                )
                self.assertAlmostEqual(
                    result["replicates"][1]["sign_consistency_fraction"],
                    2.0 / 3.0,
                )
                self.assertTrue(
                    np.isfinite(result["replicates"][0]["map_pearson_r"])
                )
                self.assertFalse(
                    any("weights" in key for row in result["replicates"] for key in row)
                )
                np.testing.assert_allclose(
                    np.load(artifacts["mean_npy"]),
                    expected_mean,
                    equal_nan=True,
                )
                np.testing.assert_allclose(
                    np.load(artifacts["sd_npy"]),
                    expected_sd,
                    rtol=1e-6,
                    equal_nan=True,
                )
                np.testing.assert_array_equal(
                    np.load(artifacts["finite_count_npy"]),
                    np.array([2, 2, 1, 2], dtype=np.uint32),
                )
                np.testing.assert_allclose(
                    np.load(spatial["observed_final_weights_npy"]),
                    observed_weights,
                    equal_nan=True,
                )

    def test_fiber_jitter_refits_weights_for_each_geometry_on_one_valid_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = self._target(root, "hf_fiber")
            parent_ids = root / "parent_feature_ids.npy"
            np.save(parent_ids, np.arange(5, dtype=np.int64))
            target.feature_ids_path = parent_ids
            scores_path = root / "scores.csv"
            with scores_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["subject_id", "Y_post", "Y_base"],
                )
                writer.writeheader()
                for index in range(12):
                    writer.writerow(
                        {
                            "subject_id": f"sub-{index + 1:02d}",
                            "Y_post": float(index + (index % 3)),
                            "Y_base": float((index * 5) % 7),
                        }
                    )
            target.scores_path = scores_path
            target.scale_direction = "higher"
            target.subject_order = tuple(f"sub-{index + 1:02d}" for index in range(12))
            base = np.arange(12, dtype=np.float32)
            first = np.column_stack((20.0 + base, 40.0 - base, 25.0 + (base % 4)))
            second = np.column_stack((40.0 - base, 20.0 + base, 25.0 + ((base + 2) % 4)))

            first_result = FIBER_JITTER._default_configured_branch_fitter(
                target,
                {"final_exposure": first},
                None,
            )
            second_result = FIBER_JITTER._default_configured_branch_fitter(
                target,
                {"final_exposure": second},
                None,
            )

        self.assertEqual(first_result["_spatial_weights"].shape, (3,))
        self.assertEqual(second_result["_spatial_weights"].shape, (3,))
        self.assertFalse(
            np.array_equal(
                np.sign(first_result["_spatial_weights"]),
                np.sign(second_result["_spatial_weights"]),
            )
        )

    def test_fiber_checkpoint_rejects_v2_identity_and_score_changes_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = self._target(root, "hf_fiber")
            v2_identity, v2_key = DIRECT_JITTER._configured_jitter_checkpoint_identity(
                target,
                n_jitters=2,
                jitter_fwhm_mm=2.0,
                seed=42,
            )
            v3_identity, v3_key = FIBER_JITTER._normative_fiber_checkpoint_identity(
                target,
                n_jitters=2,
                jitter_fwhm_mm=2.0,
                seed=42,
            )
            changed_target = self._target(root, "hf_fiber")
            changed_target.score_config = SCORE_MODULE.NormativeFiberScoreConfig(
                sweet_fraction=0.2,
                sour_fraction=0.15,
                weighted_peak_fraction=0.25,
                sweet_selected_min_count=5,
                sour_selected_min_count=3,
                weighted_peak_min_count=2,
            )
            changed_identity, changed_key = FIBER_JITTER._normative_fiber_checkpoint_identity(
                changed_target,
                n_jitters=2,
                jitter_fwhm_mm=2.0,
                seed=42,
            )
            state = DIRECT_JITTER._new_streaming_spatial_qc(
                np.ones(3, dtype=np.float32),
                np.ones(3, dtype=bool),
            )
            checkpoint = root / "legacy_v2_checkpoint.npz"
            DIRECT_JITTER._save_configured_jitter_checkpoint(
                checkpoint,
                identity=v2_identity,
                rows=[],
                spatial_state=state,
            )
            resumed = DIRECT_JITTER._load_configured_jitter_checkpoint(
                checkpoint,
                identity=v3_identity,
                spatial_state=state,
            )

        self.assertNotEqual(v2_key, v3_key)
        self.assertNotEqual(v3_key, changed_key)
        self.assertEqual(resumed, [])
        self.assertEqual(
            v3_identity["valid_feature_axis_file_sha256"],
            changed_identity["valid_feature_axis_file_sha256"],
        )

    def test_interrupted_jitter_resumes_only_remaining_replicates(self) -> None:
        observed_weights = np.array([1.0, -2.0, 3.0], dtype=np.float32)
        observed_valid = np.ones(3, dtype=bool)

        for family, jitter_module in (
            ("hf_voxel", DIRECT_JITTER),
            ("hf_fiber", FIBER_JITTER),
        ):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                target = self._target(Path(tmp), family)
                first_calls = 0

                def interrupting_geometry(target, rng, sigma):
                    nonlocal first_calls
                    first_calls += 1
                    if first_calls == 3:
                        raise KeyboardInterrupt
                    return {}

                def branch_fitter(target, geometry, delta):
                    return {
                        "status": "complete",
                        "q2": 0.1,
                        "_spatial_weights": observed_weights,
                        "_spatial_valid": observed_valid,
                    }

                with mock.patch.object(
                    jitter_module,
                    "_configured_observed_weights",
                    create=True,
                    return_value=(observed_weights, observed_valid),
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        jitter_module.run_configured_jitter(
                            target,
                            n_jitters=3,
                            jitter_fwhm_mm=2.0,
                            seed=42,
                            geometry_builder=interrupting_geometry,
                            branch_fitter=branch_fitter,
                        )

                checkpoints = list(
                    target.output_root.glob("configured_jitter_checkpoint_*.npz")
                )
                self.assertEqual(len(checkpoints), 1)
                resumed_calls = 0

                def resumed_geometry(target, rng, sigma):
                    nonlocal resumed_calls
                    resumed_calls += 1
                    return {}

                with mock.patch.object(
                    jitter_module,
                    "_configured_observed_weights",
                    create=True,
                    return_value=(observed_weights, observed_valid),
                ):
                    result = jitter_module.run_configured_jitter(
                        target,
                        n_jitters=3,
                        jitter_fwhm_mm=2.0,
                        seed=42,
                        geometry_builder=resumed_geometry,
                        branch_fitter=branch_fitter,
                    )

                self.assertEqual(resumed_calls, 1)
                self.assertEqual(result["checkpoint"]["resumed_replicates"], 2)
                self.assertEqual(result["checkpoint"]["checkpointed_replicates"], 3)


if __name__ == "__main__":
    unittest.main()
