"""Immutable record and array-or-artifact request tests."""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

import numpy as np

from dual_frequency.contracts import (
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FormalRequest,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    ObservedRequest,
    RecordError,
    RequestError,
    SensitiveRecord,
    SourceGrid,
    SourceRecord,
)


class RecordTest(unittest.TestCase):
    def test_hard_computability_limits_allow_domain_specific_feature_rules(self) -> None:
        limits = HardComputabilityLimits(12, None, None)
        self.assertIsNone(limits.n_features_full_min)
        self.assertIsNone(limits.fold_n_features_min)
        with self.assertRaises(RequestError):
            HardComputabilityLimits(12, 0, None)
        with self.assertRaises(RequestError):
            HardComputabilityLimits(12, None, 0)

    @staticmethod
    def _feature_artifact(axis: AxisRef) -> ArtifactRef:
        return ArtifactRef(
            kind="feature_weights",
            schema_version="array_v1",
            uri="file:///tmp/weights.npy",
            sha256="e" * 64,
            dtype="float64",
            shape=(axis.count,),
            axis_refs=(axis,),
            axis_hashes=(axis.sha256,),
            units="coefficient",
            space="MNI152NLin2009bAsym",
            producer_id="synthetic_fixture",
            producer_version="1",
        )

    @staticmethod
    def _array_artifact(
        kind: str,
        axes: tuple[AxisRef, ...],
        *,
        units: str = "score",
        dtype: str = "float64",
        space: str = "synthetic",
    ) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            schema_version="array_v1",
            uri=f"file:///tmp/{kind}.npy",
            sha256=(kind[0].encode("ascii").hex()[0] if kind else "a") * 64,
            dtype=dtype,
            shape=tuple(axis.count for axis in axes),
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space=space,
            producer_id="synthetic_fixture",
            producer_version="1",
        )

    def test_endpoint_identity_is_deterministic_and_immutable(self) -> None:
        key = EndpointKey(
            study_id="synthetic",
            scale_id="scale_a",
            endpoint_binding_id="subscale_b",
            model_family="addon_fiber",
            connectome_id="connectome_x",
        )
        self.assertEqual(key.identifier, EndpointKey(**dataclasses.asdict(key)).identifier)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            key.scale_id = "changed"
        with self.assertRaises(ValueError):
            EndpointKey(
                study_id="synthetic",
                scale_id="scale_a",
                endpoint_binding_id="reference",
                model_family="frequency_1_reference",
            )

    def test_artifact_requires_complete_ordered_array_identity(self) -> None:
        subjects = AxisRef("subjects", 2, "a" * 64)
        features = AxisRef("features", 3, "b" * 64)
        artifact = ArtifactRef(
            kind="exposure_matrix",
            schema_version="array_v1",
            uri="file:///tmp/exposure.npy",
            sha256="c" * 64,
            dtype="float64",
            shape=(2, 3),
            axis_refs=(subjects, features),
            axis_hashes=(subjects.sha256, features.sha256),
            units="V/m",
            space="MNI152NLin2009bAsym",
            producer_id="synthetic_fixture",
            producer_version="1",
        )
        self.assertTrue(artifact.identifier.startswith("artifact_"))
        with self.assertRaises(RecordError):
            dataclasses.replace(artifact, uri="/tmp/exposure.npy")
        with self.assertRaises(RecordError):
            dataclasses.replace(artifact, shape=(3, 2))
        with self.assertRaises(RecordError):
            dataclasses.replace(artifact, axis_hashes=(features.sha256, subjects.sha256))

    def test_source_record_enforces_absent_and_accepted_states(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        axis = AxisRef("voxels", 20, "d" * 64)
        feature = FeatureAxisRef(axis, "canonical_brainmask")
        accepted = SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_nonpredictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=feature,
            artifacts=(self._feature_artifact(axis),),
        )
        self.assertTrue(accepted.identifier.startswith("source_"))
        absent = SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="absent_no_stable_grid",
            prediction_status="not_applicable",
            threshold_source="none",
            selected_tau=None,
            selected_coverage=None,
            adjacent_support=0,
            feature_axis=None,
        )
        self.assertEqual(absent.source_status, "absent_no_stable_grid")
        with self.assertRaises(RecordError):
            dataclasses.replace(absent, prediction_status="error_predictive")

    def test_scientific_request_rejects_paths_and_accepts_arrays(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        subject_axis = AxisRef("subjects", 2, "a" * 64)
        feature_axis = AxisRef("voxels", 3, "b" * 64)
        grid = SourceGrid(200, 5, (180, 200, 220), (5, 6), 2)
        limits = HardComputabilityLimits(12, 20, 10)
        with self.assertRaises(RequestError):
            ObservedRequest(
                endpoint=endpoint,
                branch="reference",
                exposure=Path("exposure.npy"),
                outcome=np.ones(2),
                baseline=np.arange(2),
                nuisance_inputs=(),
                subject_axis=subject_axis,
                feature_axis=feature_axis,
                source_grid=grid,
                exposure_units="V/m",
                exposure_space="MNI152NLin2009bAsym",
                outcome_direction="lower",
                hard_computability=limits,
                connectome_role="none",
                feature_ids=None,
                fiber_score_settings=None,
            )
        request = ObservedRequest(
            endpoint=endpoint,
            branch="reference",
            exposure=np.ones((2, 3)),
            outcome=np.ones(2),
            baseline=np.arange(2),
            nuisance_inputs=(),
            subject_axis=subject_axis,
            feature_axis=feature_axis,
            source_grid=grid,
            exposure_units="V/m",
            exposure_space="MNI152NLin2009bAsym",
            outcome_direction="lower",
            hard_computability=limits,
            connectome_role="none",
            feature_ids=None,
            fiber_score_settings=None,
        )
        self.assertEqual(request.exposure.shape, (2, 3))

    def test_artifact_backed_request_requires_exact_axis_identity(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        subjects = AxisRef("subjects", 2, "a" * 64)
        other_subjects = AxisRef("other_subjects", 2, "c" * 64)
        features = AxisRef("voxels", 3, "b" * 64)
        grid = SourceGrid(200, 5, (180, 200, 220), (5, 6), 2)
        limits = HardComputabilityLimits(12, 20, 10)
        with self.assertRaisesRegex(RequestError, "artifact axes"):
            ObservedRequest(
                endpoint=endpoint,
                branch="reference",
                exposure=self._array_artifact(
                    "exposure",
                    (other_subjects, features),
                    units="V/m",
                ),
                outcome=self._array_artifact("outcome", (subjects,)),
                baseline=self._array_artifact("baseline", (subjects,)),
                nuisance_inputs=(),
                subject_axis=subjects,
                feature_axis=features,
                source_grid=grid,
                exposure_units="V/m",
                exposure_space="synthetic",
                outcome_direction="lower",
                hard_computability=limits,
                connectome_role="none",
                feature_ids=None,
                fiber_score_settings=None,
            )

    def test_observed_request_binds_exposure_units_and_space(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        subjects = AxisRef("subjects", 2, "a" * 64)
        features = AxisRef("voxels", 3, "b" * 64)
        grid = SourceGrid(200, 5, (180, 200, 220), (5, 6), 2)
        limits = HardComputabilityLimits(12, 20, 10)
        exposure = self._array_artifact(
            "exposure",
            (subjects, features),
            units="V/m",
        )
        common = {
            "endpoint": endpoint,
            "branch": "reference",
            "outcome": self._array_artifact("outcome", (subjects,)),
            "baseline": self._array_artifact("baseline", (subjects,)),
            "nuisance_inputs": (),
            "subject_axis": subjects,
            "feature_axis": features,
            "source_grid": grid,
            "exposure_units": "V/m",
            "exposure_space": "synthetic",
            "outcome_direction": "lower",
            "hard_computability": limits,
            "connectome_role": "none",
            "feature_ids": None,
            "fiber_score_settings": None,
        }
        ObservedRequest(exposure=exposure, **common)
        with self.assertRaisesRegex(RequestError, "units"):
            ObservedRequest(
                exposure=dataclasses.replace(exposure, units="V/mm"),
                **common,
            )
        with self.assertRaisesRegex(RequestError, "space"):
            ObservedRequest(
                exposure=dataclasses.replace(exposure, space="other_space"),
                **common,
            )

    def test_normative_fiber_request_requires_role_ids_and_score_settings(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "connectome_formal",
        )
        subjects = AxisRef("subjects", 12, "a" * 64)
        fibers = AxisRef("fibers", 24, "b" * 64)
        settings = NormativeFiberScoreSettings(0.01, 0.005, 0.05, 200, 100, 20)
        common = {
            "endpoint": endpoint,
            "branch": "reference",
            "exposure": np.ones((12, 24)),
            "outcome": np.arange(12, dtype=float),
            "baseline": np.linspace(0.0, 1.0, 12),
            "nuisance_inputs": (),
            "subject_axis": subjects,
            "feature_axis": fibers,
            "source_grid": SourceGrid(800, 5, (400, 800, 1200), (5, 6), 2),
            "exposure_units": "V/m",
            "exposure_space": "MNI152NLin2009bAsym",
            "outcome_direction": "lower",
            "hard_computability": HardComputabilityLimits(12, None, 1000),
            "connectome_role": "formal",
            "feature_ids": np.arange(24, dtype=np.int64),
            "fiber_score_settings": settings,
        }
        request = ObservedRequest(**common)
        self.assertEqual(request.connectome_role, "formal")
        with self.assertRaisesRegex(RequestError, "connectome role"):
            ObservedRequest(**{**common, "connectome_role": "none"})
        with self.assertRaisesRegex(RequestError, "canonical feature_ids"):
            ObservedRequest(**{**common, "feature_ids": None})
        with self.assertRaisesRegex(RequestError, "full-sample fiber-count"):
            ObservedRequest(
                **{
                    **common,
                    "hard_computability": HardComputabilityLimits(12, 20, 1000),
                }
            )

    def test_sensitive_record_describes_formal_cell_without_source_status(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "connectome_sensitive",
        )
        fibers = AxisRef("fibers", 24, "b" * 64)
        feature_axis = FeatureAxisRef(fibers, "canonical_connectome_fiber_ids")
        evidence = SensitiveRecord(
            endpoint=endpoint,
            formal_endpoint_id="endpoint_formal",
            evaluated_tau=800,
            evaluated_coverage=5,
            input_status="valid",
            cell_computability_status="computable",
            prediction_status="error_nonpredictive",
            feature_axis=feature_axis,
        )
        self.assertEqual(evidence.cell_computability_status, "computable")
        self.assertFalse(hasattr(evidence, "source_status"))
        with self.assertRaisesRegex(RecordError, "error-prediction"):
            dataclasses.replace(evidence, prediction_status="not_applicable")
        noncomputable = dataclasses.replace(
            evidence,
            cell_computability_status="not_computable",
            prediction_status="not_applicable",
            feature_axis=None,
        )
        self.assertEqual(noncomputable.prediction_status, "not_applicable")

    def test_final_record_supports_reference_source_and_addon_branch(self) -> None:
        axis = AxisRef("voxels", 20, "d" * 64)
        artifact = self._feature_artifact(axis)
        reference_endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        reference_source = SourceRecord(
            endpoint=reference_endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(axis, "canonical_brainmask"),
            artifacts=(artifact,),
        )
        reference_final = FinalModelRecord(
            endpoint=reference_endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                reference_endpoint.identifier,
                "reference",
                200,
                5,
                "loocv_weighted_map",
            ),
            selected_source=reference_source,
            selected_branch=None,
        )
        self.assertEqual(reference_final.selected_source, reference_source)

        addon_endpoint = EndpointKey("study", "scale", "addon", "addon_voxel")
        addon_source = dataclasses.replace(reference_source, endpoint=addon_endpoint)
        branch = BranchRecord(
            endpoint=addon_endpoint,
            branch="no_delta_reference",
            intended_role="primary",
            input_status="valid",
            nuisance_design_status="valid",
            source=addon_source,
        )
        addon_final = FinalModelRecord(
            endpoint=addon_endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                addon_endpoint.identifier,
                branch.branch,
                200,
                5,
                "loocv_weighted_map",
            ),
            selected_source=None,
            selected_branch=branch,
        )
        self.assertEqual(addon_final.selected_branch, branch)
        with self.assertRaises(RecordError):
            dataclasses.replace(addon_final, final_status="fallback_final_realized")
        with self.assertRaisesRegex(RecordError, "tau"):
            dataclasses.replace(
                reference_final,
                final_key=dataclasses.replace(reference_final.final_key, selected_tau=999),
            )
        with self.assertRaisesRegex(RecordError, "branch"):
            dataclasses.replace(
                addon_final,
                final_key=dataclasses.replace(addon_final.final_key, final_branch="delta_reference_adjusted"),
            )
        self.assertEqual(reference_final.feature_axis.axis, axis)

    def test_formal_and_activation_requests_bind_declared_axes(self) -> None:
        subjects = AxisRef("subjects", 2, "a" * 64)
        other_subjects = AxisRef("other_subjects", 2, "c" * 64)
        fibers = AxisRef("fibers", 3, "b" * 64)
        endpoint = EndpointKey("study", "scale", "reference", "reference_fiber", "formal_connectome")
        feature_ids = self._array_artifact(
            "normative_fiber_valid_union_ids",
            (fibers,),
            units="fiber_id",
            dtype="int64",
            space="right_canonical",
        )
        source = SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=800,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(fibers, "connectome_fiber_ids"),
            artifacts=(self._feature_artifact(fibers), feature_ids),
        )
        final = FinalModelRecord(
            endpoint=endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(endpoint.identifier, "reference", 800, 5, "weighted_peak"),
            selected_source=source,
            selected_branch=None,
        )
        outcome = self._array_artifact("outcome", (subjects,))
        baseline = self._array_artifact("baseline", (subjects,))
        exposure = self._array_artifact(
            "fiber_exposure",
            (subjects, fibers),
            units="V/m",
            space="right_canonical",
        )
        formal = FormalRequest(
            final_model=final,
            resampling_kind="permutation",
            exposure=exposure,
            outcome=outcome,
            baseline=baseline,
            delta_reference_full=None,
            delta_reference_folds=None,
            subject_axis=subjects,
            feature_axis=fibers,
            exposure_units="V/m",
            exposure_space="right_canonical",
            outcome_direction="lower",
            hard_computability=HardComputabilityLimits(2, None, 1),
            connectome_role="formal",
            feature_ids=feature_ids,
            fiber_score_settings=NormativeFiberScoreSettings(
                sweet_fraction=0.1,
                sour_fraction=0.1,
                weighted_peak_fraction=0.1,
                sweet_selected_min_count=2,
                sour_selected_min_count=2,
                weighted_peak_min_count=1,
            ),
            resamples=10,
            seed=1,
        )
        self.assertEqual(formal.subject_axis, subjects)
        with self.assertRaisesRegex(RequestError, "ArtifactRef"):
            dataclasses.replace(formal, outcome=np.ones(subjects.count))
        with self.assertRaisesRegex(RequestError, "artifact axes"):
            dataclasses.replace(formal, subject_axis=other_subjects)

        activation_ids = self._array_artifact(
            "fiber_ids",
            (fibers,),
            units="fiber_id",
            dtype="int64",
            space="right_canonical",
        )
        activation = ActivationRequest(
            final_model=final,
            activation_probability=self._array_artifact(
                "activation",
                (subjects, fibers),
                units="probability",
                space="right_canonical",
            ),
            reference_overlap_mask=None,
            outcome=outcome,
            baseline=baseline,
            peak_final_score=self._array_artifact("peak_score", (subjects,)),
            nuisance_inputs=(),
            subject_axis=subjects,
            feature_axis=fibers,
            feature_ids=activation_ids,
            activation_feature_ids=activation_ids,
            outcome_direction="lower",
            hard_computability=HardComputabilityLimits(12, None, 20),
            connectome_role="formal",
            fiber_score_settings=NormativeFiberScoreSettings(
                sweet_fraction=0.1,
                sour_fraction=0.1,
                weighted_peak_fraction=0.1,
                sweet_selected_min_count=2,
                sour_selected_min_count=2,
                weighted_peak_min_count=1,
            ),
            fitting_probability_threshold=0.5,
            permutation_resamples=10,
            seed=1,
        )
        self.assertEqual(final.valid_feature_axis, final.feature_axis)
        self.assertEqual(activation.feature_axis, fibers)
        wrong_fibers = AxisRef("other_fibers", 3, "d" * 64)
        with self.assertRaisesRegex(RequestError, "inherit"):
            dataclasses.replace(
                activation,
                feature_axis=wrong_fibers,
                activation_probability=self._array_artifact(
                    "other_activation",
                    (subjects, wrong_fibers),
                    units="probability",
                    space="right_canonical",
                ),
            )

    def test_status_tokens_reject_unknown_values(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        absent = SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="absent_no_stable_grid",
            prediction_status="not_applicable",
            threshold_source="none",
            selected_tau=None,
            selected_coverage=None,
            adjacent_support=None,
            feature_axis=None,
        )
        with self.assertRaisesRegex(RecordError, "input_status"):
            dataclasses.replace(absent, input_status="typo")
        with self.assertRaisesRegex(RecordError, "threshold_source"):
            dataclasses.replace(absent, threshold_source="typo")

    def test_delta_reference_bundle_requires_identical_subject_axes(self) -> None:
        subjects = AxisRef("subjects", 2, "a" * 64)
        other_subjects = AxisRef("other_subjects", 2, "f" * 64)

        def artifact(kind: str, shape: tuple[int, ...], axes: tuple[AxisRef, ...]) -> ArtifactRef:
            return ArtifactRef(
                kind=kind,
                schema_version="array_v1",
                uri=f"file:///tmp/{kind}.npy",
                sha256=("1" if kind == "full" else "2" if kind == "fold" else "3") * 64,
                dtype="float64",
                shape=shape,
                axis_refs=axes,
                axis_hashes=tuple(axis.sha256 for axis in axes),
                units="score",
                space="clinical",
                producer_id="synthetic_fixture",
                producer_version="1",
            )

        full = artifact("full", (2,), (subjects,))
        fold = artifact("fold", (2, 2), (subjects, subjects))
        support = artifact("support", (2,), (subjects,))
        support_qc = ArtifactRef(
            kind="support_qc",
            schema_version="document_v1",
            uri="file:///tmp/support_qc.json",
            sha256="4" * 64,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id="synthetic_fixture",
            producer_version="1",
        )
        bundle = DeltaReferenceBundle(
            input_status="valid",
            support_status="limited",
            selected_reference_tau=200,
            selected_reference_coverage=5,
            full_scores=full,
            fold_scores=fold,
            support_rows=support,
            support_qc=support_qc,
        )
        self.assertTrue(bundle.valid)
        mismatched_fold = artifact("fold", (2, 2), (subjects, other_subjects))
        with self.assertRaises(RecordError):
            dataclasses.replace(bundle, fold_scores=mismatched_fold)


if __name__ == "__main__":
    unittest.main()
