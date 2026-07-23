"""Conditional final in-sample inference and paired-report regression tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.formal import FinalInSampleBackend
from dual_frequency.backends.formal.common import residual_permutation_schedule
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.contracts import (
    AxisRef,
    FormalResult,
    HardComputabilityLimits,
    InSampleRequest,
    IndexedArrayView,
)
from dual_frequency.reporting import (
    build_formal_in_sample_results,
    formal_in_sample_results_csv,
)

from .test_formal import _final_model, _score_settings, _synthetic_arrays


def _document(
    *,
    endpoint_id: str,
    scale_id: str,
    model_family: str,
    final_model_id: str,
    in_sample_p: float,
    loocv_p: float,
) -> dict[str, object]:
    return {
        "schema_version": "formal_in_sample_summary_v1",
        "endpoint_id": endpoint_id,
        "scale_id": scale_id,
        "model_family": model_family,
        "final_model_id": final_model_id,
        "selected_tau": 200.0,
        "selected_coverage": 5,
        "final_branch": "reference",
        "conditioning_label": "conditional_on_selected_tau_coverage_branch_and_candidate_axis",
        "candidate_axis_id": "candidate",
        "candidate_axis_sha256": "c" * 64,
        "candidate_feature_count": 32,
        "subject_axis_id": "subjects",
        "subject_axis_sha256": "s" * 64,
        "schedule_pairing_status": "independent_deterministic_schedule",
        "subject_mask_match": True,
        "technical_status": "completed",
        "in_sample": {
            "in_sample_spearman_rho": 0.5,
            "in_sample_permutation_p_plus_one_two_sided": in_sample_p,
        },
        "loocv": {
            "loocv_spearman_rho": 0.25,
            "loocv_permutation_p_plus_one_two_sided": loocv_p,
        },
        "optimism_gaps": {"spearman_optimism_gap": 0.25},
    }


class FinalInSampleBackendTest(unittest.TestCase):
    def test_explicit_schedule_preserves_historical_default_rng_order(self) -> None:
        generator = np.random.default_rng(42)
        expected = np.vstack([generator.permutation(16) for _ in range(10)])
        actual = residual_permutation_schedule(16, 10, 42)
        np.testing.assert_array_equal(actual, expected)

    def test_direct_and_fiber_use_full_parent_axis_and_publish_paired_metrics(self) -> None:
        for model_family in ("reference_voxel", "reference_fiber"):
            with self.subTest(model_family=model_family), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                publisher = RunScopedArtifactPublisher(root, "in_sample_test", "1")
                subject_count = 16
                parent_count = 32
                final_count = 12
                subject_axis = AxisRef("subjects", subject_count, "a" * 64)
                parent_axis = AxisRef("parent_features", parent_count, "b" * 64)
                final_axis = AxisRef("selected_features", final_count, "c" * 64)
                exposure, outcome, baseline, _ = _synthetic_arrays(
                    n_subjects=subject_count,
                    n_features=parent_count,
                )
                final_model = _final_model(
                    model_family,
                    final_axis,
                    tau=200.0,
                    coverage=5,
                )
                exposure_ref = publisher.array(
                    "parent_exposure.npy",
                    exposure,
                    kind="prepared_exposure",
                    axes=(subject_axis, parent_axis),
                    units="V/m",
                    space="right_canonical",
                )
                outcome_ref = publisher.array(
                    "outcome.npy",
                    outcome,
                    kind="outcome",
                    axes=(subject_axis,),
                    units="score",
                    space="clinical",
                )
                baseline_ref = publisher.array(
                    "baseline.npy",
                    baseline,
                    kind="baseline",
                    axes=(subject_axis,),
                    units="score",
                    space="clinical",
                )
                feature_ids_ref = publisher.array(
                    "parent_feature_ids.npy",
                    np.arange(parent_count, dtype=np.int64),
                    kind="parent_feature_ids",
                    axes=(parent_axis,),
                    units=None,
                    space="right_canonical",
                )
                loocv_predictions = publisher.array(
                    "loocv_predictions.npy",
                    outcome + np.linspace(-0.5, 0.5, subject_count),
                    kind="loocv_model_predictions",
                    axes=(subject_axis,),
                    units="score",
                    space=None,
                )
                loocv_baseline = publisher.array(
                    "loocv_baseline.npy",
                    np.full(subject_count, np.mean(outcome)),
                    kind="loocv_baseline_predictions",
                    axes=(subject_axis,),
                    units="score",
                    space=None,
                )
                loocv_summary = publisher.document(
                    "loocv_summary.json",
                    {
                        "schema_version": "formal_permutation_summary_v1",
                        "p_plus_one_two_sided": 0.25,
                        "resamples_requested": 5,
                        "finite_replicate_count": 5,
                        "observed": {
                            "loocv_spearman_rho": 0.8,
                            "loocv_spearman_nominal_p": 0.001,
                            "loocv_pearson_r": 0.8,
                            "loocv_pearson_nominal_p": 0.001,
                            "q2": 0.4,
                            "rmse_model": 1.0,
                            "mae_model": 0.8,
                            "rmse_baseline": 2.0,
                            "mae_baseline": 1.5,
                        },
                    },
                    kind="formal_permutation_summary",
                )
                request = InSampleRequest(
                    final_model=final_model,
                    exposure=exposure_ref,
                    outcome=outcome_ref,
                    baseline=baseline_ref,
                    delta_reference_full=None,
                    subject_axis=subject_axis,
                    feature_axis=parent_axis,
                    feature_ids=feature_ids_ref,
                    loocv_predictions=loocv_predictions,
                    loocv_baseline_predictions=loocv_baseline,
                    loocv_permutation_summary=loocv_summary,
                    exposure_units="V/m",
                    exposure_space="right_canonical",
                    outcome_direction="lower",
                    hard_computability=(
                        HardComputabilityLimits(12, None, 1)
                        if model_family.endswith("fiber")
                        else HardComputabilityLimits(12, 20, 1)
                    ),
                    connectome_role=(
                        "formal" if model_family.endswith("fiber") else "none"
                    ),
                    fiber_score_settings=(
                        _score_settings() if model_family.endswith("fiber") else None
                    ),
                    resamples=5,
                    seed=42,
                )
                result = FinalInSampleBackend(
                    publisher,
                    artifact_store=ArtifactStore((root,)),
                ).run(request)
                self.assertEqual(result.resampling_kind, "in_sample_permutation")
                summary_ref = next(
                    item for item in result.artifacts if item.kind == "formal_in_sample_summary"
                )
                summary = json.loads(Path(summary_ref.uri.removeprefix("file://")).read_text())
                self.assertEqual(summary["candidate_feature_count"], parent_count)
                self.assertNotIn("in_sample_adjusted_r2", summary["in_sample"])
                self.assertIn("in_sample_r2", summary["in_sample"])
                self.assertIn("in_sample_relative_r2", summary["in_sample"])
                self.assertIn("loocv_r2", summary["loocv"])
                self.assertIn("spearman_optimism_gap", summary["optimism_gaps"])
                self.assertEqual(
                    summary["schedule_pairing_status"],
                    "independent_deterministic_schedule",
                )
                view_publisher = RunScopedArtifactPublisher(
                    root / "view",
                    "in_sample_view_test",
                    "1",
                )
                view_request = dataclasses.replace(
                    request,
                    exposure=IndexedArrayView(
                        parent=exposure_ref,
                        row_positions=None,
                        column_positions=None,
                        axis_refs=(subject_axis, parent_axis),
                    ),
                )
                view_result = FinalInSampleBackend(
                    view_publisher,
                    artifact_store=ArtifactStore((root,)),
                ).run(view_request)
                view_summary_ref = next(
                    item
                    for item in view_result.artifacts
                    if item.kind == "formal_in_sample_summary"
                )
                view_summary = json.loads(
                    Path(
                        view_summary_ref.uri.removeprefix("file://")
                    ).read_text()
                )
                self.assertEqual(view_summary["in_sample"], summary["in_sample"])
                self.assertEqual(
                    view_summary["candidate_feature_count"],
                    summary["candidate_feature_count"],
                )


class FormalInSampleReportingTest(unittest.TestCase):
    def test_complete_112_endpoint_family_and_global_bh_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records: dict[str, object] = {}
            families = (
                "reference_voxel",
                "addon_voxel",
                "reference_fiber",
                "addon_fiber",
            )
            for family_index, family in enumerate(families):
                for scale_index in range(28):
                    task_id = f"task_{family_index:02d}_{scale_index:02d}"
                    final_model_id = f"final_{family_index:02d}_{scale_index:02d}"
                    publisher = RunScopedArtifactPublisher(root, task_id, "1")
                    artifact = publisher.document(
                        f"{task_id}_in_sample_summary.json",
                        _document(
                            endpoint_id=f"endpoint_{family_index:02d}_{scale_index:02d}",
                            scale_id=f"scale_{scale_index:02d}",
                            model_family=family,
                            final_model_id=final_model_id,
                            in_sample_p=(scale_index + 1) / 1000.0,
                            loocv_p=(scale_index + 2) / 1000.0,
                        ),
                        kind="formal_in_sample_summary",
                    )
                    records[task_id] = FormalResult(
                        final_model_id=final_model_id,
                        resampling_kind="in_sample_permutation",
                        technical_status="completed",
                        artifacts=(artifact,),
                    )
            document = build_formal_in_sample_results(
                records,
                ArtifactStore((root,)),
            )
            self.assertEqual(document["result_count"], 112)
            for row in document["results"]:
                self.assertIsNotNone(row["in_sample_permutation_q_bh_model_family"])
                self.assertIsNotNone(row["loocv_permutation_q_bh_model_family"])
                self.assertIsNotNone(row["in_sample_permutation_q_bh_all_endpoints"])
                self.assertIsNotNone(row["loocv_permutation_q_bh_all_endpoints"])
            csv_text = formal_in_sample_results_csv(document)
            self.assertEqual(len(csv_text.splitlines()), 113)


if __name__ == "__main__":
    unittest.main()
