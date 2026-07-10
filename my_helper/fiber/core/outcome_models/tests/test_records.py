"""Tests for immutable source, DeltaHF, nuisance, and final-artifact records."""

from __future__ import annotations

import unittest
from pathlib import Path

from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    FinalArtifactRecord,
    HFSourceRecord,
    NuisancePlan,
    RecordError,
    ULFBranchRecord,
)


class ImmutableRecordTests(unittest.TestCase):
    def _artifact(self, kind: str, name: str, shape=()) -> ArtifactRef:
        return ArtifactRef(
            task_id="task_source",
            kind=kind,
            relative_path=f"tasks/task_source/{name}",
            sha256="a" * 64,
            shape=shape,
        )

    def test_hf_source_hash_covers_selected_source_and_feature_axis(self) -> None:
        axis = FeatureAxisRef(Path("fiber_ids.npy"), 3, "b" * 64, "data.mat:idx")
        source = HFSourceRecord.create(
            resolver_task_id="task_resolver",
            endpoint_model_id="endpoint_hf",
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=800,
            selected_coverage=5,
            subject_order=("sub-01", "sub-02"),
            feature_axis=axis,
            artifacts=(self._artifact("source_manifest", "source.json"),),
        )
        changed = HFSourceRecord.create(
            resolver_task_id="task_resolver",
            endpoint_model_id="endpoint_hf",
            input_status="valid",
            source_status="scan_fallback_accepted",
            prediction_status="error_predictive",
            threshold_source="scan_fallback",
            selected_tau=1000,
            selected_coverage=5,
            subject_order=("sub-01", "sub-02"),
            feature_axis=axis,
            artifacts=(self._artifact("source_manifest", "source.json"),),
        )

        self.assertTrue(source.accepted)
        self.assertNotEqual(source.record_hash, changed.record_hash)
        self.assertEqual(len(source.record_hash), 64)
        self.assertEqual(HFSourceRecord.from_dict(source.as_dict()), source)
        tampered = source.as_dict()
        tampered["selected_tau"] = 1200
        with self.assertRaises(RecordError):
            HFSourceRecord.from_dict(tampered)

    def test_accepted_hf_source_requires_selected_cell_axis_and_artifacts(self) -> None:
        with self.assertRaises(RecordError):
            HFSourceRecord.create(
                resolver_task_id="task_resolver",
                endpoint_model_id="endpoint_hf",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=None,
                selected_coverage=None,
                subject_order=("sub-01",),
                feature_axis=None,
                artifacts=(),
            )

    def test_delta_bundle_accepts_adequate_and_limited_but_rejects_extreme_support(self) -> None:
        full = self._artifact("delta_hf_full_scores", "full.npy", (2,))
        folds = self._artifact("delta_hf_fold_scores", "folds.npy", (2, 2))
        support = self._artifact("delta_hf_support_rows", "support.csv", (2,))
        adequate = DeltaHFBundle(
            input_status="valid",
            support_status="adequate",
            selected_hf_tau=800,
            selected_hf_coverage=5,
            full_scores=full,
            fold_scores=folds,
            support_rows=support,
        )
        limited = DeltaHFBundle(
            input_status="valid",
            support_status="limited",
            selected_hf_tau=800,
            selected_hf_coverage=5,
            full_scores=full,
            fold_scores=folds,
            support_rows=support,
        )
        invalid = DeltaHFBundle(
            input_status="invalid",
            support_status="invalid_extreme_out_of_support",
            selected_hf_tau=800,
            selected_hf_coverage=5,
            full_scores=None,
            fold_scores=None,
            support_rows=support,
            failure_stage="support_qc",
            failure_detail="extreme out of support",
        )

        self.assertTrue(adequate.valid)
        self.assertTrue(limited.valid)
        self.assertFalse(invalid.valid)
        self.assertEqual(DeltaHFBundle.from_dict(limited.as_dict()), limited)

    def test_adjusted_nuisance_requires_valid_full_and_fold_delta_artifacts(self) -> None:
        no_delta = NuisancePlan.for_branch("no_delta_hf", None)
        self.assertEqual(no_delta.columns, ("Y_HF_ref",))
        with self.assertRaises(RecordError):
            NuisancePlan.for_branch("delta_hf_adjusted", None)

        bundle = DeltaHFBundle(
            input_status="valid",
            support_status="limited",
            selected_hf_tau=200,
            selected_hf_coverage=5,
            full_scores=self._artifact("delta_hf_full_scores", "full.npy", (2,)),
            fold_scores=self._artifact("delta_hf_fold_scores", "folds.npy", (2, 2)),
            support_rows=self._artifact("delta_hf_support_rows", "support.csv", (2,)),
        )
        adjusted = NuisancePlan.for_branch("delta_hf_adjusted", bundle)
        self.assertEqual(adjusted.columns, ("Y_HF_ref", "DeltaHFScore"))
        self.assertEqual(adjusted.delta_hf_record_hash, bundle.record_hash)
        self.assertEqual(adjusted.delta_hf_full_scores, bundle.full_scores)
        self.assertEqual(adjusted.delta_hf_fold_scores, bundle.fold_scores)
        self.assertEqual(adjusted.delta_hf_support_rows, bundle.support_rows)

    def test_final_artifact_record_binds_branch_source_nuisance_and_files(self) -> None:
        nuisance = NuisancePlan.for_branch("no_delta_hf", None)
        final = FinalArtifactRecord.create(
            final_model_id="final_one",
            endpoint_model_id="endpoint_ulf",
            final_branch="no_delta_hf",
            final_role="fallback_final",
            selected_tau=250,
            selected_coverage=6,
            estimator="partial_spearman",
            scale_direction="lower",
            subject_order=("sub-01", "sub-02"),
            nuisance=nuisance,
            manifest=self._artifact("final_manifest", "manifest.json"),
            exposure=self._artifact("exposure", "x.npy", (2, 3)),
            scores=self._artifact("scores", "scores.csv", (2,)),
            feature_axis=FeatureAxisRef(Path("voxels.npy"), 3, "c" * 64, "candidate_flat_indices"),
            spatial_reference=self._artifact("spatial_reference", "brainmask.nii.gz"),
        )

        self.assertEqual(final.nuisance.columns, ("Y_HF_ref",))
        self.assertEqual(final.scale_direction, "lower")
        self.assertEqual(final.subject_order, ("sub-01", "sub-02"))
        self.assertIsNotNone(final.spatial_reference)
        self.assertEqual(len(final.record_hash), 64)
        self.assertEqual(FinalArtifactRecord.from_dict(final.as_dict()), final)

    def test_ulf_branch_record_binds_branch_nuisance_source_and_artifacts(self) -> None:
        record = ULFBranchRecord.create(
            resolver_task_id="task_branch",
            endpoint_model_id="endpoint_ulf",
            branch="no_delta_hf",
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_nonpredictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            adjacent_support=2,
            subject_order=("sub-01", "sub-02"),
            feature_axis=FeatureAxisRef(Path("voxels.npy"), 3, "c" * 64, "candidate_flat_indices"),
            nuisance=NuisancePlan.for_branch("no_delta_hf", None),
            artifacts=(self._artifact("selected_manifest", "manifest.json"),),
        )
        self.assertTrue(record.accepted)
        self.assertEqual(ULFBranchRecord.from_dict(record.as_dict()), record)
        self.assertEqual(record.nuisance.columns, ("Y_HF_ref",))


if __name__ == "__main__":
    unittest.main()
