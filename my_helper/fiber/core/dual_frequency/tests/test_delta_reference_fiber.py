"""Deterministic normative-fiber DeltaReferenceScore tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.delta_reference.normative_fiber import (
    DeltaReferenceFiberError,
    build_delta_reference_fiber,
)
from dual_frequency.backends.normative_fiber.scoring import score_signed_fibers
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
    NormativeFiberScoreSettings,
    SensitiveRecord,
    SourceRecord,
    canonical_hash,
)


def _support_profile() -> DeltaReferenceSupportProfile:
    return DeltaReferenceSupportProfile(
        adequate=AdequateSupportProfile(0.20, 0.50, 0.25),
        invalid=InvalidSupportProfile(0.50, 0.80, 0.25, 0.95),
    )


def _score_settings() -> NormativeFiberScoreSettings:
    return NormativeFiberScoreSettings(
        sweet_fraction=0.01,
        sour_fraction=0.005,
        weighted_peak_fraction=0.05,
        sweet_selected_min_count=200,
        sour_selected_min_count=100,
        weighted_peak_min_count=20,
    )


def _axes(
    parent_fiber_ids: np.ndarray,
    valid_fiber_ids: np.ndarray,
    *,
    connectome_id: str,
    n_subjects: int = 4,
    tau: float = 200.0,
    coverage: int = 2,
) -> tuple[AxisRef, AxisRef, AxisRef]:
    subject_axis = AxisRef(
        "subjects",
        n_subjects,
        canonical_hash({"subject_ids": list(range(n_subjects))}),
    )
    parent_axis = AxisRef(
        f"fibers:{connectome_id}",
        int(parent_fiber_ids.size),
        canonical_hash(
            {
                "connectome_id": connectome_id,
                "fiber_ids": parent_fiber_ids.tolist(),
            }
        ),
    )
    selected_digest = hashlib.sha256(
        np.ascontiguousarray(valid_fiber_ids, dtype=np.int64).tobytes(order="C")
    ).hexdigest()
    selected_axis = AxisRef(
        f"{parent_axis.axis_id}:valid-union:tau-{tau:g}:coverage-{coverage}",
        int(valid_fiber_ids.size),
        canonical_hash(
            {
                "parent_axis_sha256": parent_axis.sha256,
                "selected_fiber_ids_sha256": selected_digest,
                "tau": tau,
                "coverage": coverage,
            }
        ),
    )
    return subject_axis, parent_axis, selected_axis


def _placeholder_artifact(axis: AxisRef, connectome_id: str) -> ArtifactRef:
    return ArtifactRef(
        kind="normative_fiber_valid_union_ids",
        schema_version="dual_frequency_array_v1",
        uri=f"memory://{connectome_id}/valid_fiber_ids.npy",
        sha256="c" * 64,
        dtype="int64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=None,
        space=f"space:{connectome_id}",
        producer_id="synthetic_reference",
        producer_version="1",
    )


def _reference_record(
    selected_axis: AxisRef,
    *,
    connectome_id: str,
    sensitive: bool = False,
    artifacts: tuple[ArtifactRef, ...] | None = None,
) -> SourceRecord | SensitiveRecord:
    endpoint = EndpointKey(
        "study",
        "scale",
        "reference_binding",
        "reference_fiber",
        connectome_id,
    )
    carried = artifacts or (_placeholder_artifact(selected_axis, connectome_id),)
    feature_axis = FeatureAxisRef(
        selected_axis,
        "selected_normative_fiber_full_fold_valid_union",
    )
    if sensitive:
        formal_endpoint = EndpointKey(
            "study",
            "scale",
            "reference_binding",
            "reference_fiber",
            "formal_connectome",
        )
        return SensitiveRecord(
            endpoint=endpoint,
            formal_endpoint_id=formal_endpoint.identifier,
            evaluated_tau=200,
            evaluated_coverage=2,
            input_status="valid",
            cell_computability_status="computable",
            prediction_status="error_nonpredictive",
            feature_axis=feature_axis,
            artifacts=carried,
        )
    return SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=200,
        selected_coverage=2,
        adjacent_support=2,
        feature_axis=feature_axis,
        artifacts=carried,
    )


def _materialize(artifact: ArtifactRef, root: Path) -> np.ndarray:
    return ArtifactStore([root]).materialize(
        artifact,
        expected_dtype=artifact.dtype,
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
    )


def _subject_ids(axis: AxisRef) -> tuple[str, ...]:
    return tuple(f"subject-{index:02d}" for index in range(axis.count))


class DeltaReferenceFiberTest(unittest.TestCase):
    def _build(
        self,
        root: Path,
        *,
        parent_fiber_ids: np.ndarray,
        valid_fiber_ids: np.ndarray,
        full_weights: np.ndarray | ArtifactRef,
        fold_weights: np.ndarray | ArtifactRef,
        fold_valid_masks: np.ndarray | ArtifactRef,
        reference_exposure: np.ndarray | ArtifactRef,
        addon_reference_exposure: np.ndarray | ArtifactRef,
        connectome_id: str = "formal_connectome",
        reference_record: SourceRecord | SensitiveRecord | None = None,
        subject_axis: AxisRef | None = None,
        parent_axis: AxisRef | None = None,
        reference_parent_axis: AxisRef | None = None,
        selected_axis: AxisRef | None = None,
        parent_fiber_input: np.ndarray | ArtifactRef | None = None,
        valid_fiber_input: np.ndarray | ArtifactRef | None = None,
        artifact_store: ArtifactStore | None = None,
    ):
        if subject_axis is None or parent_axis is None or selected_axis is None:
            subject_axis, parent_axis, selected_axis = _axes(
                parent_fiber_ids,
                valid_fiber_ids,
                connectome_id=connectome_id,
            )
        evidence = reference_record or _reference_record(
            selected_axis,
            connectome_id=connectome_id,
        )
        return build_delta_reference_fiber(
            matched_reference_endpoint_id=evidence.endpoint.identifier,
            matched_reference_connectome_id=connectome_id,
            reference_record=evidence,
            parent_fiber_ids=(
                parent_fiber_ids if parent_fiber_input is None else parent_fiber_input
            ),
            valid_fiber_ids=(
                valid_fiber_ids if valid_fiber_input is None else valid_fiber_input
            ),
            full_weights=full_weights,
            fold_weights=fold_weights,
            fold_valid_masks=fold_valid_masks,
            reference_condition_exposure=reference_exposure,
            addon_reference_component_exposure=addon_reference_exposure,
            subject_axis=subject_axis,
            reference_subject_axis=subject_axis,
            addon_subject_ids=_subject_ids(subject_axis),
            reference_subject_ids=_subject_ids(subject_axis),
            parent_fiber_axis=parent_axis,
            fiber_score_settings=_score_settings(),
            support_profile=_support_profile(),
            publisher=RunScopedArtifactPublisher(root, "delta_fiber_test", "1"),
            artifact_store=artifact_store,
            reference_parent_fiber_axis=reference_parent_axis,
        )

    def test_formal_record_uses_continuous_signed_200_100_20_operator(self) -> None:
        parent_ids = np.arange(10_000, 10_320, dtype=np.int64)
        valid_ids = parent_ids[:300]
        full_weights = np.concatenate((np.ones(200), -np.ones(100)))
        fold_weights = np.tile(full_weights, (4, 1))
        fold_masks = np.ones_like(fold_weights, dtype=bool)
        subject = np.arange(4, dtype=np.float64)[:, None]
        reference = np.zeros((4, 320), dtype=np.float64)
        addon = np.zeros((4, 320), dtype=np.float64)
        reference[:, :200] = 125.0 + 10.0 * subject
        reference[:, 200:300] = 75.0 + 5.0 * subject
        addon[:, :200] = 450.0 + 20.0 * subject
        addon[:, 200:300] = 225.0 + 10.0 * subject

        addon_operator = score_signed_fibers(
            addon[:, :300],
            full_weights,
            valid_ids,
            _score_settings(),
            candidate_mask=np.ones(300, dtype=bool),
        )
        reference_operator = score_signed_fibers(
            reference[:, :300],
            full_weights,
            valid_ids,
            _score_settings(),
            candidate_mask=np.ones(300, dtype=bool),
        )
        self.assertEqual(addon_operator.sweet_actual_selected_count, 200)
        self.assertEqual(addon_operator.sour_actual_selected_count, 100)
        self.assertEqual(addon_operator.sweet_actual_peak_count, 20)
        self.assertEqual(addon_operator.sour_actual_peak_count, 20)
        expected = addon_operator.net_score - reference_operator.net_score

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._build(
                root,
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_weights,
                fold_weights=fold_weights,
                fold_valid_masks=fold_masks,
                reference_exposure=reference,
                addon_reference_exposure=addon,
            )
            self.assertTrue(bundle.valid)
            self.assertEqual(bundle.support_status, "adequate")
            assert bundle.full_scores is not None and bundle.fold_scores is not None
            np.testing.assert_allclose(_materialize(bundle.full_scores, root), expected)
            np.testing.assert_allclose(
                _materialize(bundle.fold_scores, root),
                np.tile(expected, (4, 1)),
            )

    def test_locked_selected_axis_uses_reference_parent_not_augmented_addon_parent(
        self,
    ) -> None:
        valid_ids = np.arange(10_000, 10_300, dtype=np.int64)
        reference_parent_ids = valid_ids.copy()
        addon_parent_ids = np.concatenate(
            (valid_ids, np.arange(20_000, 20_020, dtype=np.int64))
        )
        subjects, reference_parent_axis, selected_axis = _axes(
            reference_parent_ids,
            valid_ids,
            connectome_id="formal_connectome",
        )
        _, addon_parent_axis, _ = _axes(
            addon_parent_ids,
            valid_ids,
            connectome_id="formal_connectome",
        )
        full_weights = np.concatenate((np.ones(200), -np.ones(100)))
        fold_weights = np.tile(full_weights, (subjects.count, 1))
        fold_masks = np.ones_like(fold_weights, dtype=bool)
        reference = np.zeros(
            (subjects.count, addon_parent_ids.size),
            dtype=np.float64,
        )
        addon = np.zeros_like(reference)
        subject = np.arange(subjects.count, dtype=np.float64)[:, None]
        reference[:, :300] = 250.0 + subject
        addon[:, :300] = 300.0 + subject

        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._build(
                Path(temporary),
                parent_fiber_ids=addon_parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_weights,
                fold_weights=fold_weights,
                fold_valid_masks=fold_masks,
                reference_exposure=reference,
                addon_reference_exposure=addon,
                subject_axis=subjects,
                parent_axis=addon_parent_axis,
                reference_parent_axis=reference_parent_axis,
                selected_axis=selected_axis,
            )
        self.assertTrue(bundle.valid)

    def test_fold_operator_can_use_fibers_outside_full_finite_support(self) -> None:
        parent_ids = np.arange(20_000, 20_400, dtype=np.int64)
        valid_ids = parent_ids.copy()
        full_weights = np.full(400, np.nan)
        full_weights[:200] = 1.0
        full_weights[200:300] = -1.0
        fold_weights = np.tile(full_weights, (4, 1))
        fold_weights[0] = np.nan
        fold_weights[0, 100:200] = -1.0
        fold_weights[0, 200:400] = 1.0
        fold_masks = np.isfinite(fold_weights)
        reference = np.full((4, 400), 100.0, dtype=np.float64)
        addon = np.empty((4, 400), dtype=np.float64)
        addon[:, :100] = 300.0
        addon[:, 100:200] = 400.0
        addon[:, 200:300] = 500.0
        addon[:, 300:400] = 900.0
        expected_fold_zero = (
            score_signed_fibers(
                addon,
                fold_weights[0],
                valid_ids,
                _score_settings(),
                candidate_mask=fold_masks[0],
            ).net_score
            - score_signed_fibers(
                reference,
                fold_weights[0],
                valid_ids,
                _score_settings(),
                candidate_mask=fold_masks[0],
            ).net_score
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._build(
                root,
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_weights,
                fold_weights=fold_weights,
                fold_valid_masks=fold_masks,
                reference_exposure=reference,
                addon_reference_exposure=addon,
            )
            self.assertTrue(bundle.valid)
            self.assertEqual(bundle.support_status, "limited")
            assert bundle.fold_scores is not None
            fold_scores = _materialize(bundle.fold_scores, root)
            np.testing.assert_allclose(fold_scores[0], expected_fold_zero)
            np.testing.assert_allclose(fold_scores[0], 500.0)

    def test_addon_subset_selects_fiber_reference_folds_by_subject_identity(self) -> None:
        parent_ids = np.arange(25_000, 25_320, dtype=np.int64)
        valid_ids = parent_ids[:300]
        addon_axis, parent_axis, selected_axis = _axes(
            parent_ids,
            valid_ids,
            connectome_id="formal_connectome",
            n_subjects=3,
        )
        reference_axis = AxisRef(
            "reference-subjects",
            5,
            canonical_hash({"subject_ids": ["a", "b", "c", "d", "e"]}),
        )
        base_weights = np.concatenate((np.ones(200), -np.ones(100)))
        fold_weights = np.vstack(
            [base_weights * factor for factor in (1.0, 2.0, 3.0, 4.0, 5.0)]
        )
        fold_masks = np.isfinite(fold_weights)
        reference = np.zeros((3, 320), dtype=np.float64)
        addon = np.zeros((3, 320), dtype=np.float64)
        reference[:, :200] = 100.0
        reference[:, 200:300] = 50.0
        addon[:, :200] = 400.0
        addon[:, 200:300] = 200.0
        evidence = _reference_record(selected_axis, connectome_id="formal_connectome")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = build_delta_reference_fiber(
                matched_reference_endpoint_id=evidence.endpoint.identifier,
                matched_reference_connectome_id="formal_connectome",
                reference_record=evidence,
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=base_weights,
                fold_weights=fold_weights,
                fold_valid_masks=fold_masks,
                reference_condition_exposure=reference,
                addon_reference_component_exposure=addon,
                subject_axis=addon_axis,
                reference_subject_axis=reference_axis,
                addon_subject_ids=("subject-a", "subject-c", "subject-e"),
                reference_subject_ids=(
                    "subject-a",
                    "subject-b",
                    "subject-c",
                    "subject-d",
                    "subject-e",
                ),
                parent_fiber_axis=parent_axis,
                fiber_score_settings=_score_settings(),
                support_profile=_support_profile(),
                publisher=RunScopedArtifactPublisher(root, "delta_subset", "1"),
            )
            self.assertTrue(bundle.valid)
            assert bundle.fold_scores is not None
            folds = _materialize(bundle.fold_scores, root)
            expected_rows = []
            for index in (0, 2, 4):
                weights = fold_weights[index]
                expected_rows.append(
                    score_signed_fibers(
                        addon[:, :300],
                        weights,
                        valid_ids,
                        _score_settings(),
                        candidate_mask=np.ones(300, dtype=bool),
                    ).net_score
                    - score_signed_fibers(
                        reference[:, :300],
                        weights,
                        valid_ids,
                        _score_settings(),
                        candidate_mask=np.ones(300, dtype=bool),
                    ).net_score
                )
            np.testing.assert_allclose(folds, np.vstack(expected_rows))

    def test_sensitive_record_requires_local_endpoint_connectome_and_parent_axis(self) -> None:
        connectome_id = "sensitive_connectome"
        parent_ids = np.arange(30_000, 30_200, dtype=np.int64)
        valid_ids = parent_ids.copy()
        subjects, parent_axis, selected_axis = _axes(
            parent_ids,
            valid_ids,
            connectome_id=connectome_id,
        )
        evidence = _reference_record(
            selected_axis,
            connectome_id=connectome_id,
            sensitive=True,
        )
        weights = np.ones(200)
        folds = np.tile(weights, (4, 1))
        masks = np.ones_like(folds, dtype=bool)
        reference = np.full((4, 200), 100.0)
        addon = np.full((4, 200), 201.0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._build(
                root / "valid",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=weights,
                fold_weights=folds,
                fold_valid_masks=masks,
                reference_exposure=reference,
                addon_reference_exposure=addon,
                connectome_id=connectome_id,
                reference_record=evidence,
                subject_axis=subjects,
                parent_axis=parent_axis,
                selected_axis=selected_axis,
            )
            self.assertTrue(bundle.valid)
            self.assertEqual(bundle.support_status, "adequate")

            with self.assertRaisesRegex(DeltaReferenceFiberError, "connectome"):
                build_delta_reference_fiber(
                    matched_reference_endpoint_id=evidence.endpoint.identifier,
                    matched_reference_connectome_id="formal_connectome",
                    reference_record=evidence,
                    parent_fiber_ids=parent_ids,
                    valid_fiber_ids=valid_ids,
                    full_weights=weights,
                    fold_weights=folds,
                    fold_valid_masks=masks,
                    reference_condition_exposure=reference,
                    addon_reference_component_exposure=addon,
                    subject_axis=subjects,
                    reference_subject_axis=subjects,
                    addon_subject_ids=_subject_ids(subjects),
                    reference_subject_ids=_subject_ids(subjects),
                    parent_fiber_axis=parent_axis,
                    fiber_score_settings=_score_settings(),
                    support_profile=_support_profile(),
                    publisher=RunScopedArtifactPublisher(
                        root / "wrong_connectome",
                        "delta_fiber_test",
                        "1",
                    ),
                )

            with self.assertRaisesRegex(DeltaReferenceFiberError, "parent fiber axis"):
                self._build(
                    root / "borrowed_parent",
                    parent_fiber_ids=parent_ids,
                    valid_fiber_ids=valid_ids,
                    full_weights=weights,
                    fold_weights=folds,
                    fold_valid_masks=masks,
                    reference_exposure=reference,
                    addon_reference_exposure=addon,
                    connectome_id=connectome_id,
                    reference_record=evidence,
                    subject_axis=subjects,
                    parent_axis=replace(parent_axis, sha256="f" * 64),
                    selected_axis=selected_axis,
                )

    def test_strict_individual_extreme_boundary_accepts_0p95_only(self) -> None:
        parent_ids = np.arange(40_000, 40_100, dtype=np.int64)
        valid_ids = parent_ids.copy()
        full_weights = np.ones(100)
        accepted_folds = np.ones((4, 100))
        accepted_folds[0, 5:] = np.nan
        rejected_folds = accepted_folds.copy()
        rejected_folds[0, 4] = np.nan
        reference = np.full((4, 100), 100.0)
        addon = np.full((4, 100), 250.0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = self._build(
                root / "accepted",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_weights,
                fold_weights=accepted_folds,
                fold_valid_masks=np.isfinite(accepted_folds),
                reference_exposure=reference,
                addon_reference_exposure=addon,
            )
            rejected = self._build(
                root / "rejected",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_weights,
                fold_weights=rejected_folds,
                fold_valid_masks=np.isfinite(rejected_folds),
                reference_exposure=reference,
                addon_reference_exposure=addon,
            )
            self.assertEqual(accepted.support_status, "adequate")
            self.assertTrue(accepted.valid)
            assert accepted.support_rows is not None
            support_rows = _materialize(accepted.support_rows, root)
            self.assertEqual(support_rows[0, 3], 0.95)
            self.assertEqual(rejected.support_status, "invalid_extreme_out_of_support")
            self.assertFalse(rejected.valid)
            self.assertIsNone(rejected.full_scores)
            self.assertIsNone(rejected.fold_scores)
            self.assertIsNotNone(rejected.support_rows)
            self.assertIsNotNone(rejected.support_qc)
            self.assertFalse(
                (root / "rejected" / "delta_reference_full_scores.npy").exists()
            )
            self.assertFalse(
                (root / "rejected" / "delta_reference_fold_scores.npy").exists()
            )

    def test_strict_tau_and_adequate_support_boundaries(self) -> None:
        parent_ids = np.arange(50_000, 50_100, dtype=np.int64)
        valid_ids = parent_ids.copy()
        weights = np.ones(100)
        weights[81:] = np.nan
        folds = np.tile(weights, (4, 1))
        masks = np.isfinite(folds)
        reference = np.full((4, 100), 100.0)
        addon = np.full((4, 100), 201.0)
        addon[:, 81:] = 10_000.0

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            strict = self._build(
                root / "strict",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=weights,
                fold_weights=folds,
                fold_valid_masks=masks,
                reference_exposure=reference,
                addon_reference_exposure=addon,
            )
            self.assertTrue(strict.valid)
            self.assertEqual(strict.support_status, "adequate")
            assert strict.full_scores is not None and strict.support_rows is not None
            np.testing.assert_allclose(_materialize(strict.full_scores, root), 101.0)
            rows = _materialize(strict.support_rows, root)
            np.testing.assert_array_equal(rows[:, 0], 100.0)
            np.testing.assert_array_equal(rows[:, 1], 81.0)
            np.testing.assert_allclose(rows[:, 2], 0.19)

            equality = np.full_like(addon, 200.0)
            excluded = self._build(
                root / "equality",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=weights,
                fold_weights=folds,
                fold_valid_masks=masks,
                reference_exposure=reference,
                addon_reference_exposure=equality,
            )
            self.assertEqual(
                excluded.support_status,
                "invalid_no_reference_component_exposure",
            )
            self.assertFalse(excluded.valid)

            zero_exposure = addon.copy()
            zero_exposure[0] = 200.0
            invalid = self._build(
                root / "zero",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=weights,
                fold_weights=folds,
                fold_valid_masks=masks,
                reference_exposure=reference,
                addon_reference_exposure=zero_exposure,
            )
            self.assertEqual(
                invalid.support_status,
                "invalid_no_reference_component_exposure",
            )
            self.assertFalse(invalid.valid)
            self.assertIsNone(invalid.full_scores)
            self.assertIsNone(invalid.fold_scores)
            self.assertIsNotNone(invalid.support_rows)
            self.assertIsNotNone(invalid.support_qc)
            self.assertFalse(
                (root / "zero" / "delta_reference_full_scores.npy").exists()
            )
            self.assertFalse(
                (root / "zero" / "delta_reference_fold_scores.npy").exists()
            )

    def test_artifact_inputs_require_exact_axes_and_local_record_membership(self) -> None:
        parent_ids = np.arange(60_000, 60_200, dtype=np.int64)
        valid_ids = parent_ids.copy()
        subjects, parent_axis, selected_axis = _axes(
            parent_ids,
            valid_ids,
            connectome_id="formal_connectome",
        )
        weights = np.ones(200)
        folds = np.tile(weights, (4, 1))
        masks = np.ones_like(folds, dtype=bool)
        reference = np.full((4, 200), 100.0)
        addon = np.full((4, 200), 250.0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = RunScopedArtifactPublisher(root / "inputs", "reference", "1")
            parent_ref = inputs.array(
                "parent_ids.npy",
                parent_ids,
                kind="normative_fiber_parent_ids",
                axes=(parent_axis,),
                units=None,
                space="space:formal_connectome",
            )
            valid_ref = inputs.array(
                "valid_ids.npy",
                valid_ids,
                kind="normative_fiber_valid_union_ids",
                axes=(selected_axis,),
                units=None,
                space="space:formal_connectome",
            )
            full_ref = inputs.array(
                "full_weights.npy",
                weights,
                kind="benefit_oriented_fiber_weights",
                axes=(selected_axis,),
                units="coefficient",
                space="space:formal_connectome",
            )
            fold_ref = inputs.array(
                "fold_weights.npy",
                folds,
                kind="loocv_benefit_oriented_fiber_weights",
                axes=(subjects, selected_axis),
                units="coefficient",
                space="space:formal_connectome",
            )
            mask_ref = inputs.array(
                "fold_masks.npy",
                masks,
                kind="loocv_valid_fiber_masks",
                axes=(subjects, selected_axis),
                units=None,
                space="space:formal_connectome",
            )
            reference_ref = inputs.array(
                "reference.npy",
                reference,
                kind="reference_condition_exposure",
                axes=(subjects, parent_axis),
                units="V/m",
                space="space:formal_connectome",
            )
            addon_ref = inputs.array(
                "addon_reference.npy",
                addon,
                kind="addon_reference_component_exposure",
                axes=(subjects, parent_axis),
                units="V/m",
                space="space:formal_connectome",
            )
            evidence = _reference_record(
                selected_axis,
                connectome_id="formal_connectome",
                artifacts=(valid_ref, full_ref, fold_ref, mask_ref),
            )
            store = ArtifactStore([root])
            bundle = self._build(
                root / "output",
                parent_fiber_ids=parent_ids,
                valid_fiber_ids=valid_ids,
                full_weights=full_ref,
                fold_weights=fold_ref,
                fold_valid_masks=mask_ref,
                reference_exposure=reference_ref,
                addon_reference_exposure=addon_ref,
                reference_record=evidence,
                subject_axis=subjects,
                parent_axis=parent_axis,
                selected_axis=selected_axis,
                parent_fiber_input=parent_ref,
                valid_fiber_input=valid_ref,
                artifact_store=store,
            )
            self.assertTrue(bundle.valid)

            rogue = RunScopedArtifactPublisher(root / "rogue", "reference", "1").array(
                "full_weights.npy",
                weights,
                kind="benefit_oriented_fiber_weights",
                axes=(selected_axis,),
                units="coefficient",
                space="space:formal_connectome",
            )
            with self.assertRaisesRegex(DeltaReferenceFiberError, "local reference record"):
                self._build(
                    root / "rejected",
                    parent_fiber_ids=parent_ids,
                    valid_fiber_ids=valid_ids,
                    full_weights=rogue,
                    fold_weights=fold_ref,
                    fold_valid_masks=mask_ref,
                    reference_exposure=reference_ref,
                    addon_reference_exposure=addon_ref,
                    reference_record=evidence,
                    subject_axis=subjects,
                    parent_axis=parent_axis,
                    selected_axis=selected_axis,
                    parent_fiber_input=parent_ref,
                    valid_fiber_input=valid_ref,
                    artifact_store=store,
                )


if __name__ == "__main__":
    unittest.main()
