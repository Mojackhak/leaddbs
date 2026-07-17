"""Deterministic DeltaReferenceScore and reference-overlap tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.delta_reference import (
    DeltaReferenceDirectVoxelError,
    build_delta_reference_voxel,
)
from dual_frequency.backends.interaction import prepare_reference_overlap
from dual_frequency.backends.interaction import ReferenceOverlapError
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.config.models import (
    AdequateSupportProfile,
    DeltaReferenceSupportProfile,
    InvalidSupportProfile,
)
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    FeatureAxisRef,
    SourceRecord,
    canonical_hash,
)


def _support_profile() -> DeltaReferenceSupportProfile:
    return DeltaReferenceSupportProfile(
        adequate=AdequateSupportProfile(0.20, 0.50, 0.25),
        invalid=InvalidSupportProfile(0.50, 0.80, 0.25, 0.95),
    )


def _axes(
    selected_indices: np.ndarray,
    *,
    n_subjects: int = 4,
    n_features: int = 10,
    tau: float = 200.0,
    coverage: int = 2,
) -> tuple[AxisRef, AxisRef, AxisRef]:
    subjects = AxisRef("subjects", n_subjects, "a" * 64)
    parent = AxisRef("voxels", n_features, "b" * 64)
    selected = AxisRef(
        f"voxels:selected:tau-{tau:g}:coverage-{coverage}",
        int(selected_indices.size),
        canonical_hash(
            {
                "parent_axis_sha256": parent.sha256,
                "selected_indices": selected_indices.tolist(),
                "tau": tau,
                "coverage": coverage,
            }
        ),
    )
    return subjects, parent, selected


def _synthetic_artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="selected_feature_indices",
        schema_version="dual_frequency_array_v1",
        uri="file:///synthetic/selected_feature_indices.npy",
        sha256="c" * 64,
        dtype="int64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=None,
        space="synthetic",
        producer_id="synthetic_fixture",
        producer_version="1",
    )


def _subject_ids(axis: AxisRef) -> tuple[str, ...]:
    return tuple(f"subject-{index:02d}" for index in range(axis.count))


def _source(selected_axis: AxisRef, *, accepted: bool = True) -> SourceRecord:
    endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
    if accepted:
        return SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_nonpredictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=2,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(
                selected_axis,
                "selected_direct_voxel_feature_union",
            ),
            artifacts=(_synthetic_artifact(selected_axis),),
        )
    return SourceRecord(
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


class DeltaReferenceDirectVoxelTest(unittest.TestCase):
    def _build(
        self,
        root: Path,
        *,
        selected_indices: np.ndarray,
        full_weights: np.ndarray,
        fold_weights: np.ndarray,
        addon_reference_exposure: np.ndarray,
        reference_exposure: np.ndarray | None = None,
    ):
        subjects, parent, selected = _axes(
            selected_indices,
            n_features=addon_reference_exposure.shape[1],
        )
        if reference_exposure is None:
            reference_exposure = np.full((subjects.count, parent.count), 100.0)
        source = _source(selected)
        return build_delta_reference_voxel(
            matched_reference_endpoint_id=source.endpoint.identifier,
            reference_source=source,
            selected_feature_indices=selected_indices,
            full_weights=full_weights,
            fold_weights=fold_weights,
            reference_condition_exposure=reference_exposure,
            addon_reference_component_exposure=addon_reference_exposure,
            subject_axis=subjects,
            reference_subject_axis=subjects,
            addon_subject_ids=_subject_ids(subjects),
            reference_subject_ids=_subject_ids(subjects),
            parent_feature_axis=parent,
            support_profile=_support_profile(),
            publisher=RunScopedArtifactPublisher(root, "delta_test", "1"),
        )

    def test_adequate_support_publishes_locked_full_and_fold_scores(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        full_weights = np.linspace(0.5, 1.2, indices.size)
        fold_weights = np.tile(full_weights, (4, 1))
        addon_reference = np.full((4, 10), 150.0)
        addon_reference[:, :8] = 250.0
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._build(
                root,
                selected_indices=indices,
                full_weights=full_weights,
                fold_weights=fold_weights,
                addon_reference_exposure=addon_reference,
            )
            self.assertTrue(bundle.valid)
            self.assertEqual(bundle.support_status, "adequate")
            self.assertEqual(bundle.selected_reference_tau, 200)
            self.assertEqual(bundle.selected_reference_coverage, 2)
            self.assertIsNotNone(bundle.support_qc)
            store = ArtifactStore([root])
            full = store.materialize(
                bundle.full_scores,
                expected_dtype="float64",
                expected_shape=(4,),
                expected_axes=bundle.full_scores.axis_refs,
                expected_units="V/m",
                expected_space=None,
            )
            expected = np.mean((250.0 - 100.0) * full_weights)
            np.testing.assert_allclose(full, expected)

    def test_limited_support_remains_valid(self) -> None:
        indices = np.arange(6, dtype=np.int64)
        weights = np.ones(indices.size)
        addon_reference = np.full((4, 10), 250.0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._build(
                Path(temporary),
                selected_indices=indices,
                full_weights=weights,
                fold_weights=np.tile(weights, (4, 1)),
                addon_reference_exposure=addon_reference,
            )
        self.assertTrue(bundle.valid)
        self.assertEqual(bundle.support_status, "limited")

    def test_exact_tau_reference_component_coverage_is_valid(self) -> None:
        indices = np.arange(10, dtype=np.int64)
        weights = np.ones(indices.size)
        addon_reference = np.full((4, 10), 200.0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._build(
                Path(temporary),
                selected_indices=indices,
                full_weights=weights,
                fold_weights=np.tile(weights, (4, 1)),
                addon_reference_exposure=addon_reference,
            )
        self.assertTrue(bundle.valid)
        self.assertEqual(bundle.support_status, "adequate")
        self.assertIsNotNone(bundle.full_scores)
        self.assertIsNotNone(bundle.fold_scores)
        self.assertIsNotNone(bundle.support_qc)

    def test_below_tau_reference_component_coverage_is_invalid(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        weights = np.ones(indices.size)
        addon_reference = np.full((4, 10), 199.0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._build(
                Path(temporary),
                selected_indices=indices,
                full_weights=weights,
                fold_weights=np.tile(weights, (4, 1)),
                addon_reference_exposure=addon_reference,
            )
        self.assertFalse(bundle.valid)
        self.assertEqual(
            bundle.support_status,
            "invalid_no_reference_component_coverage",
        )
        self.assertIsNone(bundle.full_scores)
        self.assertIsNone(bundle.fold_scores)
        self.assertIsNotNone(bundle.support_qc)

    def test_extreme_out_of_support_is_invalid(self) -> None:
        indices = np.arange(4, dtype=np.int64)
        weights = np.ones(indices.size)
        addon_reference = np.full((4, 10), 250.0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._build(
                Path(temporary),
                selected_indices=indices,
                full_weights=weights,
                fold_weights=np.tile(weights, (4, 1)),
                addon_reference_exposure=addon_reference,
            )
        self.assertFalse(bundle.valid)
        self.assertEqual(bundle.support_status, "invalid_extreme_out_of_support")

    def test_individual_extreme_boundary_is_strictly_greater_than_0p95(self) -> None:
        indices = np.arange(100, dtype=np.int64)
        addon_reference = np.full((4, 100), 250.0)
        full_weights = np.ones(100)
        at_boundary = np.ones((4, 100))
        at_boundary[0, 5:] = np.nan
        beyond_boundary = at_boundary.copy()
        beyond_boundary[0, 4] = np.nan
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = self._build(
                root / "at_boundary",
                selected_indices=indices,
                full_weights=full_weights,
                fold_weights=at_boundary,
                addon_reference_exposure=addon_reference,
            )
            rejected = self._build(
                root / "beyond_boundary",
                selected_indices=indices,
                full_weights=full_weights,
                fold_weights=beyond_boundary,
                addon_reference_exposure=addon_reference,
            )
        self.assertEqual(accepted.support_status, "adequate")
        self.assertEqual(rejected.support_status, "invalid_extreme_out_of_support")

    def test_fold_scores_never_substitute_full_sample_weights(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        addon_reference = np.full((4, 10), 150.0)
        addon_reference[:, :8] = 250.0 + np.arange(4)[:, None]
        fold_weights = np.vstack(
            (
                np.linspace(0.2, 0.9, 8),
                np.linspace(0.3, 1.0, 8),
                np.linspace(0.4, 1.1, 8),
                np.linspace(0.5, 1.2, 8),
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._build(
                root / "first",
                selected_indices=indices,
                full_weights=np.ones(8),
                fold_weights=fold_weights,
                addon_reference_exposure=addon_reference,
            )
            second = self._build(
                root / "second",
                selected_indices=indices,
                full_weights=np.linspace(10.0, 80.0, 8),
                fold_weights=fold_weights,
                addon_reference_exposure=addon_reference,
            )
            store = ArtifactStore([root])
            first_fold = store.materialize(
                first.fold_scores,
                expected_dtype="float64",
                expected_shape=(4, 4),
                expected_axes=first.fold_scores.axis_refs,
                expected_units="V/m",
                expected_space=None,
            )
            second_fold = store.materialize(
                second.fold_scores,
                expected_dtype="float64",
                expected_shape=(4, 4),
                expected_axes=second.fold_scores.axis_refs,
                expected_units="V/m",
                expected_space=None,
            )
            np.testing.assert_array_equal(first_fold, second_fold)

    def test_addon_subset_selects_reference_folds_by_subject_identity(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        addon_axis, parent, selected = _axes(indices, n_subjects=3)
        reference_axis = AxisRef("reference-subjects", 5, "d" * 64)
        addon_ids = ("subject-a", "subject-c", "subject-e")
        reference_ids = (
            "subject-a",
            "subject-b",
            "subject-c",
            "subject-d",
            "subject-e",
        )
        fold_weights = np.vstack(
            [np.full(indices.size, factor) for factor in (1.0, 2.0, 3.0, 4.0, 5.0)]
        )
        reference_exposure = np.full((3, 10), 100.0)
        addon_reference = np.full((3, 10), 150.0)
        addon_reference[:, :8] = 250.0
        source = _source(selected)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = build_delta_reference_voxel(
                matched_reference_endpoint_id=source.endpoint.identifier,
                reference_source=source,
                selected_feature_indices=indices,
                full_weights=np.ones(indices.size),
                fold_weights=fold_weights,
                reference_condition_exposure=reference_exposure,
                addon_reference_component_exposure=addon_reference,
                subject_axis=addon_axis,
                reference_subject_axis=reference_axis,
                addon_subject_ids=addon_ids,
                reference_subject_ids=reference_ids,
                parent_feature_axis=parent,
                support_profile=_support_profile(),
                publisher=RunScopedArtifactPublisher(root, "delta_subset", "1"),
            )
            self.assertTrue(bundle.valid)
            assert bundle.fold_scores is not None
            folds = ArtifactStore([root]).materialize(
                bundle.fold_scores,
                expected_dtype="float64",
                expected_shape=(3, 3),
                expected_axes=(addon_axis, addon_axis),
                expected_units="V/m",
                expected_space=None,
            )
            np.testing.assert_allclose(
                folds,
                np.asarray(
                    (
                        (150.0, 150.0, 150.0),
                        (450.0, 450.0, 450.0),
                        (750.0, 750.0, 750.0),
                    )
                ),
            )

    def test_missing_addon_subject_rejects_adjusted_cohort(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        addon_axis, parent, selected = _axes(indices, n_subjects=3)
        reference_axis = AxisRef("reference-subjects", 4, "d" * 64)
        source = _source(selected)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                DeltaReferenceDirectVoxelError,
                "every add-on subject",
            ):
                build_delta_reference_voxel(
                    matched_reference_endpoint_id=source.endpoint.identifier,
                    reference_source=source,
                    selected_feature_indices=indices,
                    full_weights=np.ones(indices.size),
                    fold_weights=np.ones((4, indices.size)),
                    reference_condition_exposure=np.full((3, 10), 100.0),
                    addon_reference_component_exposure=np.full((3, 10), 250.0),
                    subject_axis=addon_axis,
                    reference_subject_axis=reference_axis,
                    addon_subject_ids=("subject-a", "subject-c", "subject-missing"),
                    reference_subject_ids=(
                        "subject-a",
                        "subject-b",
                        "subject-c",
                        "subject-d",
                    ),
                    parent_feature_axis=parent,
                    support_profile=_support_profile(),
                    publisher=RunScopedArtifactPublisher(
                        Path(temporary),
                        "delta_missing",
                        "1",
                    ),
                )

    def test_selected_parent_axis_identity_is_validated(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        subjects, parent, selected = _axes(indices)
        source = _source(selected)
        wrong_indices = indices.copy()
        wrong_indices[-1] = 9
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                DeltaReferenceDirectVoxelError,
                "feature-axis hash",
            ):
                build_delta_reference_voxel(
                    matched_reference_endpoint_id=source.endpoint.identifier,
                    reference_source=source,
                    selected_feature_indices=wrong_indices,
                    full_weights=np.ones(8),
                    fold_weights=np.ones((4, 8)),
                    reference_condition_exposure=np.full((4, 10), 100.0),
                    addon_reference_component_exposure=np.full((4, 10), 250.0),
                    subject_axis=subjects,
                    reference_subject_axis=subjects,
                    addon_subject_ids=_subject_ids(subjects),
                    reference_subject_ids=_subject_ids(subjects),
                    parent_feature_axis=parent,
                    support_profile=_support_profile(),
                    publisher=RunScopedArtifactPublisher(
                        Path(temporary),
                        "delta_test",
                        "1",
                    ),
                )

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                DeltaReferenceDirectVoxelError,
                "matched_reference_endpoint_id",
            ):
                build_delta_reference_voxel(
                    matched_reference_endpoint_id="endpoint_wrong",
                    reference_source=source,
                    selected_feature_indices=indices,
                    full_weights=np.ones(8),
                    fold_weights=np.ones((4, 8)),
                    reference_condition_exposure=np.full((4, 10), 100.0),
                    addon_reference_component_exposure=np.full((4, 10), 250.0),
                    subject_axis=subjects,
                    reference_subject_axis=subjects,
                    addon_subject_ids=_subject_ids(subjects),
                    reference_subject_ids=_subject_ids(subjects),
                    parent_feature_axis=parent,
                    support_profile=_support_profile(),
                    publisher=RunScopedArtifactPublisher(
                        Path(temporary),
                        "delta_test",
                        "1",
                    ),
                )

    def test_artifact_backed_inputs_use_declared_axes(self) -> None:
        indices = np.arange(8, dtype=np.int64)
        subjects, parent, selected = _axes(indices)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_publisher = RunScopedArtifactPublisher(root / "inputs", "reference", "1")
            index_ref = input_publisher.array(
                "indices.npy",
                indices,
                kind="selected_feature_indices",
                axes=(selected,),
                units=None,
                space="synthetic",
            )
            full_ref = input_publisher.array(
                "full_weights.npy",
                np.ones(8),
                kind="benefit_oriented_feature_weights",
                axes=(selected,),
                units="coefficient",
                space="synthetic",
            )
            fold_ref = input_publisher.array(
                "fold_weights.npy",
                np.ones((4, 8)),
                kind="loocv_benefit_oriented_feature_weights",
                axes=(subjects, selected),
                units="coefficient",
                space="synthetic",
            )
            reference_ref = input_publisher.array(
                "reference.npy",
                np.full((4, 10), 100.0),
                kind="reference_condition_exposure",
                axes=(subjects, parent),
                units="V/m",
                space="synthetic",
            )
            addon_ref = input_publisher.array(
                "addon_reference.npy",
                np.column_stack(
                    (np.full((4, 8), 250.0), np.full((4, 2), 150.0))
                ),
                kind="addon_reference_component_exposure",
                axes=(subjects, parent),
                units="V/m",
                space="synthetic",
            )
            source = replace(
                _source(selected),
                artifacts=(index_ref, full_ref, fold_ref),
            )
            bundle = build_delta_reference_voxel(
                matched_reference_endpoint_id=source.endpoint.identifier,
                reference_source=source,
                selected_feature_indices=index_ref,
                full_weights=full_ref,
                fold_weights=fold_ref,
                reference_condition_exposure=reference_ref,
                addon_reference_component_exposure=addon_ref,
                subject_axis=subjects,
                reference_subject_axis=subjects,
                addon_subject_ids=_subject_ids(subjects),
                reference_subject_ids=_subject_ids(subjects),
                parent_feature_axis=parent,
                support_profile=_support_profile(),
                publisher=RunScopedArtifactPublisher(root / "output", "delta_test", "1"),
                artifact_store=ArtifactStore([root]),
            )
            self.assertTrue(bundle.valid)

    def test_absent_and_accepted_reference_overlap_rules(self) -> None:
        indices = np.arange(3, dtype=np.int64)
        _, _, selected = _axes(indices, n_features=3)
        addon = np.array([[5.0, 6.0, 7.0]])
        reference = np.array([[199.0, 200.0, 201.0]])

        accepted = prepare_reference_overlap(addon, reference, _source(selected))
        self.assertEqual(accepted.reference_threshold, 200.0)
        np.testing.assert_array_equal(
            accepted.overlap_mask,
            np.array([[False, True, True]]),
        )
        np.testing.assert_array_equal(
            accepted.addon_exposure,
            np.array([[5.0, 0.0, 0.0]]),
        )

        absent = prepare_reference_overlap(addon, reference, _source(selected, accepted=False))
        self.assertTrue(np.isposinf(absent.reference_threshold))
        self.assertFalse(np.any(absent.overlap_mask))
        np.testing.assert_array_equal(absent.addon_exposure, addon)

        failed_dependency = replace(
            _source(selected, accepted=False),
            input_status="input_failure",
        )
        with self.assertRaisesRegex(ReferenceOverlapError, "valid matched reference"):
            prepare_reference_overlap(addon, reference, failed_dependency)

        wrong_family = replace(
            _source(selected),
            endpoint=EndpointKey(
                "study",
                "scale",
                "reference",
                "reference_fiber",
                "synthetic_connectome",
            ),
        )
        with self.assertRaisesRegex(ReferenceOverlapError, "reference_voxel"):
            prepare_reference_overlap(addon, reference, wrong_family)


if __name__ == "__main__":
    unittest.main()
