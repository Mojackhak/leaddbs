"""Immutable record and array-or-artifact request tests."""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

import numpy as np

from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    ObservedRequest,
    RecordError,
    RequestError,
    SourceGrid,
    SourceRecord,
)


class RecordTest(unittest.TestCase):
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
        )
        self.assertEqual(request.exposure.shape, (2, 3))

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
        bundle = DeltaReferenceBundle(
            input_status="valid",
            support_status="limited",
            selected_reference_tau=200,
            selected_reference_coverage=5,
            full_scores=full,
            fold_scores=fold,
            support_rows=support,
        )
        self.assertTrue(bundle.valid)
        mismatched_fold = artifact("fold", (2, 2), (subjects, other_subjects))
        with self.assertRaises(RecordError):
            dataclasses.replace(bundle, fold_scores=mismatched_fold)


if __name__ == "__main__":
    unittest.main()
