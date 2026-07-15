"""Cache-first OSS row materialization and bounded fixture tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import numpy as np

import dual_frequency.backends.activation.fitting as ppam_fitting
from dual_frequency.backends.activation import (
    MissingAcceptanceFixture,
    OSSRowBatchRequest,
    OSSRowInput,
    OSSRowMaterializer,
    OSSRowProduct,
    OSSScientificSettings,
    PPAMActivationBackend,
    binary_activation,
    build_oss_row_cache_key,
    subset_probability_axis,
)
from dual_frequency.backends.statistics import (
    benefit_oriented_weights,
    partial_spearman_weights,
)
from dual_frequency.cache import (
    ArtifactStore,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.contracts import (
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    BranchRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    SourceRecord,
)


def _artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="synthetic_fiber_weights",
        schema_version="synthetic_v1",
        uri="memory://synthetic/weights",
        sha256="f" * 64,
        dtype="float32",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=None,
        space="right_canonical",
        producer_id="synthetic",
        producer_version="1",
    )


def _final(scale_id: str, feature_axis: AxisRef) -> FinalModelRecord:
    endpoint = EndpointKey(
        "synthetic",
        scale_id,
        "reference_binding",
        "reference_fiber",
        "formal-connectome",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=800,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "synthetic_fiber_ids"),
        artifacts=(_artifact(feature_axis),),
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            800,
            5,
            "weighted_peak",
        ),
        selected_source=source,
        selected_branch=None,
    )


def _rows(
    subjects: tuple[str, ...],
    feature_axis: AxisRef,
    fiber_ids: np.ndarray,
) -> tuple[OSSRowInput, ...]:
    rows = []
    for subject_index, subject_id in enumerate(subjects):
        for side_index, side in enumerate(("L", "R")):
            seed = subject_index * 2 + side_index + 1
            rows.append(
                OSSRowInput(
                    subject_id=subject_id,
                    side=side,
                    source_id=f"source-{seed}",
                    feature_axis=feature_axis,
                    feature_ids=fiber_ids,
                    geometry_hash=f"{seed:064x}",
                    stimulation_hash=f"{seed + 100:064x}",
                    component_frequency_hash=f"{seed + 200:064x}",
                    transform_hash=f"{seed + 300:064x}",
                    connectome_feature_hash=feature_axis.sha256,
                )
            )
    return tuple(reversed(rows))


def _request(
    *,
    scale_id: str,
    allow_expensive: bool,
    subjects: tuple[str, ...],
    subject_axis: AxisRef,
    feature_axis: AxisRef,
    fiber_ids: np.ndarray,
    rows: tuple[OSSRowInput, ...],
    workers: int = 3,
) -> OSSRowBatchRequest:
    return OSSRowBatchRequest(
        final_model=_final(scale_id, feature_axis),
        connectome_role="formal",
        subject_axis=subject_axis,
        subject_ids=subjects,
        feature_axis=feature_axis,
        feature_ids=fiber_ids,
        rows=rows,
        settings=OSSScientificSettings(backend_version="2.2.0"),
        allow_expensive_producers=allow_expensive,
        workers=workers,
    )


def _artifact_array(artifact: ArtifactRef) -> np.ndarray:
    return np.load(Path(unquote(urlsplit(artifact.uri).path)), allow_pickle=False)


def _document_payload(artifact: ArtifactRef) -> dict[str, object]:
    return json.loads(
        Path(unquote(urlsplit(artifact.uri).path)).read_text(encoding="utf-8")
    )


def _addon_final(
    branch_name: str,
    feature_axis: AxisRef,
) -> FinalModelRecord:
    endpoint = EndpointKey(
        "synthetic",
        "scale",
        "addon_binding",
        "addon_fiber",
        "formal-connectome",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=800,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "synthetic_fiber_ids"),
        artifacts=(_artifact(feature_axis),),
    )
    branch = BranchRecord(
        endpoint=endpoint,
        branch=branch_name,
        intended_role="primary",
        input_status="valid",
        nuisance_design_status="valid",
        source=source,
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            branch_name,
            800,
            5,
            "weighted_peak",
        ),
        selected_source=None,
        selected_branch=branch,
    )


class OSSRowIdentityTest(unittest.TestCase):
    def test_key_excludes_endpoint_and_execution_identity_by_construction(self) -> None:
        fibers = AxisRef("fibers", 3, "a" * 64)
        row = _rows(("sub-01",), fibers, np.arange(3, dtype=np.int64))[0]
        settings = OSSScientificSettings(backend_version="2.2.0")
        first = build_oss_row_cache_key(row, settings)
        second = build_oss_row_cache_key(row, settings)
        self.assertEqual(first, second)
        self.assertNotIn("scale", json.dumps(first.as_dict()))
        self.assertNotIn("endpoint", json.dumps(first.as_dict()))
        self.assertNotIn("final", json.dumps(first.as_dict()))
        self.assertNotIn("worker", json.dumps(first.as_dict()))

    def test_key_changes_for_every_scientific_identity_dimension(self) -> None:
        fibers = AxisRef("fibers", 3, "a" * 64)
        row = _rows(("sub-01",), fibers, np.arange(3, dtype=np.int64))[0]
        settings = OSSScientificSettings(backend_version="2.2.0")
        baseline = build_oss_row_cache_key(row, settings).digest
        for field_name in (
            "geometry_hash",
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
            "connectome_feature_hash",
        ):
            changed = dataclasses.replace(row, **{field_name: "e" * 64})
            with self.subTest(field_name=field_name):
                self.assertNotEqual(
                    build_oss_row_cache_key(changed, settings).digest,
                    baseline,
                )
        self.assertNotEqual(
            build_oss_row_cache_key(
                row,
                OSSScientificSettings(backend_version="2.3.0"),
            ).digest,
            baseline,
        )

    def test_key_binds_actual_ordered_feature_ids(self) -> None:
        fibers = AxisRef("fibers", 3, "a" * 64)
        row = _rows(("sub-01",), fibers, np.arange(3, dtype=np.int64))[0]
        reordered = dataclasses.replace(
            row,
            feature_ids=np.asarray([1, 0, 2], dtype=np.int64),
        )
        settings = OSSScientificSettings(backend_version="2.2.0")
        self.assertNotEqual(
            build_oss_row_cache_key(row, settings).digest,
            build_oss_row_cache_key(reordered, settings).digest,
        )


class OSSRowMaterializerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.subjects = ("sub-01", "sub-02", "sub-03")
        self.subject_axis = AxisRef("subjects", 3, "b" * 64)
        self.feature_axis = AxisRef("fibers", 5, "c" * 64)
        self.fiber_ids = np.arange(101, 106, dtype=np.int64)
        self.rows = _rows(self.subjects, self.feature_axis, self.fiber_ids)

    @staticmethod
    def _values(row: OSSRowInput) -> np.ndarray:
        subject = int(row.subject_id.rsplit("-", 1)[1])
        side = 0.2 if row.side == "L" else 0.35
        values = np.clip(
            side + subject * 0.05 + np.arange(row.feature_ids.size) * 0.12,
            0.0,
            1.0,
        )
        return (np.rint(values * 10.0) / 10.0).astype(np.float32)

    def test_blocked_miss_invokes_no_producer(self) -> None:
        calls: list[str] = []

        def producer(row: OSSRowInput) -> OSSRowProduct:
            calls.append(row.source_id)
            return OSSRowProduct(row.feature_ids, self._values(row))

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            materializer = OSSRowMaterializer(
                ContentAddressedCache(root / "cache"),
                RunScopedArtifactPublisher(root / "run", "oss_test", "1"),
                producer=producer,
            )
            with self.assertRaisesRegex(
                MissingAcceptanceFixture,
                "missing_acceptance_fixture",
            ):
                materializer.materialize(
                    _request(
                        scale_id="scale-a",
                        allow_expensive=False,
                        subjects=self.subjects,
                        subject_axis=self.subject_axis,
                        feature_axis=self.feature_axis,
                        fiber_ids=self.fiber_ids,
                        rows=self.rows,
                    )
                )
        self.assertEqual(calls, [])

    def test_row_product_requires_the_ten_sample_probability_lattice(self) -> None:
        with self.assertRaisesRegex(ValueError, "activation count divided by 10"):
            OSSRowProduct(
                self.fiber_ids,
                np.asarray([0.0, 0.1, 0.37, 0.9, 1.0], dtype=np.float32),
            )

    def test_three_worker_production_is_deterministic_and_cache_reusable(self) -> None:
        lock = threading.Lock()
        active = 0
        max_active = 0
        calls: list[str] = []

        def producer(row: OSSRowInput) -> OSSRowProduct:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                calls.append(row.source_id)
            time.sleep(0.01 * (1 + int(row.source_id.rsplit("-", 1)[1]) % 3))
            product = OSSRowProduct(row.feature_ids, self._values(row))
            with lock:
                active -= 1
            return product

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache = ContentAddressedCache(root / "cache")
            first = OSSRowMaterializer(
                cache,
                RunScopedArtifactPublisher(root / "run-a", "oss_test", "1"),
                producer=producer,
            ).materialize(
                _request(
                    scale_id="scale-a",
                    allow_expensive=True,
                    subjects=self.subjects,
                    subject_axis=self.subject_axis,
                    feature_axis=self.feature_axis,
                    fiber_ids=self.fiber_ids,
                    rows=self.rows,
                )
            )
            first_probability = _artifact_array(first.activation_probability)
            first_binary = _artifact_array(first.binary_exposure)
            first_ids = _artifact_array(first.feature_ids)
            calls_after_first = len(calls)

            def forbidden(_row: OSSRowInput) -> OSSRowProduct:
                raise AssertionError("exact cache hit must not invoke producer")

            second = OSSRowMaterializer(
                cache,
                RunScopedArtifactPublisher(root / "run-b", "oss_test", "1"),
                producer=forbidden,
            ).materialize(
                _request(
                    scale_id="scale-b",
                    allow_expensive=False,
                    subjects=self.subjects,
                    subject_axis=self.subject_axis,
                    feature_axis=self.feature_axis,
                    fiber_ids=self.fiber_ids,
                    rows=tuple(reversed(self.rows)),
                )
            )
            second_probability = _artifact_array(second.activation_probability)
            second_binary = _artifact_array(second.binary_exposure)
            second_ids = _artifact_array(second.feature_ids)

        self.assertEqual(calls_after_first, len(self.rows))
        self.assertEqual(len(calls), calls_after_first)
        self.assertGreaterEqual(max_active, 2)
        self.assertLessEqual(max_active, 3)
        np.testing.assert_array_equal(first_probability, second_probability)
        np.testing.assert_array_equal(first_binary, second_binary)
        np.testing.assert_array_equal(first_ids, self.fiber_ids)
        np.testing.assert_array_equal(second_ids, self.fiber_ids)
        np.testing.assert_array_equal(first_binary, binary_activation(first_probability))
        expected = np.stack(
            [
                np.maximum(
                    self._values(next(row for row in self.rows if row.subject_id == subject and row.side == "L")),
                    self._values(next(row for row in self.rows if row.subject_id == subject and row.side == "R")),
                )
                for subject in self.subjects
            ]
        )
        np.testing.assert_array_equal(first_probability, expected)


class PPAMActivationBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.n_subjects = 12
        self.n_fibers = 60
        self.subject_axis = AxisRef("subjects", self.n_subjects, "7" * 64)
        self.feature_axis = AxisRef("fibers", self.n_fibers, "8" * 64)
        self.fiber_ids = np.arange(1_000, 1_000 + self.n_fibers, dtype=np.int64)
        self.latent = np.linspace(-1.5, 1.5, self.n_subjects)
        subject = np.arange(self.n_subjects, dtype=np.float64)[:, None]
        fiber = np.arange(self.n_fibers, dtype=np.float64)[None, :]
        sign = np.where((np.arange(self.n_fibers) % 2) == 0, 1.0, -1.0)
        threshold = ((np.arange(self.n_fibers) % 9) - 4) * 0.11
        activation_latent = (
            self.latent[:, None] * sign[None, :]
            + 0.45 * np.sin((subject + 1.0) * (fiber + 1.0))
        )
        self.probabilities = np.where(
            activation_latent > threshold[None, :],
            0.8,
            0.2,
        ).astype(np.float32)
        self.baseline = 30.0 + np.sin(np.arange(self.n_subjects))
        self.outcome = (
            50.0
            - 8.0 * self.latent
            + 0.3 * self.baseline
            + 0.15 * np.cos(np.arange(self.n_subjects))
        )
        self.peak_score = self.latent.copy()
        self.settings = NormativeFiberScoreSettings(
            sweet_fraction=0.01,
            sour_fraction=0.005,
            weighted_peak_fraction=0.05,
            sweet_selected_min_count=10,
            sour_selected_min_count=5,
            weighted_peak_min_count=2,
        )

    def _request(
        self,
        *,
        final: FinalModelRecord | None = None,
        nuisance_inputs: tuple[np.ndarray, ...] = (),
        outcome_direction: str = "lower",
    ) -> ActivationRequest:
        resolved_final = final or _final("scale", self.feature_axis)
        overlap_mask = (
            None
            if resolved_final.endpoint.model_family.startswith("reference_")
            else np.zeros_like(self.probabilities, dtype=bool)
        )
        return ActivationRequest(
            final_model=resolved_final,
            activation_probability=self.probabilities,
            reference_overlap_mask=overlap_mask,
            outcome=self.outcome,
            baseline=self.baseline,
            peak_final_score=self.peak_score,
            nuisance_inputs=nuisance_inputs,
            subject_axis=self.subject_axis,
            feature_axis=self.feature_axis,
            feature_ids=self.fiber_ids,
            activation_feature_ids=self.fiber_ids,
            outcome_direction=outcome_direction,
            hard_computability=HardComputabilityLimits(12, None, 20),
            connectome_role="formal",
            fiber_score_settings=self.settings,
            fitting_probability_threshold=0.5,
            permutation_resamples=5,
            seed=42,
        )

    @staticmethod
    def _status(result) -> dict[str, object]:
        status = next(
            artifact
            for artifact in result.artifacts
            if artifact.kind == "oss_sensitivity_status"
        )
        return _document_payload(status)

    def test_reference_fit_is_fixed_axis_fold_local_and_reproducible(self) -> None:
        probabilities = self.probabilities.copy()
        probabilities[0, 0] = 0.5
        request = dataclasses.replace(
            self._request(),
            activation_probability=probabilities,
        )
        original_final = request.final_model
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "first", "oss_fit", "1")
            ).run_activation(request)
            second = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "second", "oss_fit", "1")
            ).run_activation(request)
            first_status = self._status(first)
            second_status = self._status(second)
            first_null = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_permutation_null_statistics"
                )
            )
            second_null = _artifact_array(
                next(
                    artifact
                    for artifact in second.artifacts
                    if artifact.kind == "oss_permutation_null_statistics"
                )
            )
            fold_weights = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_loocv_benefit_oriented_fiber_weights"
                )
            )
            full_weights = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_benefit_oriented_fiber_weights"
                )
            )
            first_binary = _artifact_array(first.binary_exposure)
            comparison = _document_payload(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_plain_activation_model_comparison"
                )
            )
        self.assertEqual(first_status["oss_sensitivity_status"], "passed_activation_consistent")
        self.assertFalse(first_status["candidate_axis_rescanned"])
        self.assertFalse(first_status["classification_feedback"])
        self.assertEqual(first_status, second_status)
        self.assertEqual(request.final_model, original_final)
        self.assertEqual(fold_weights.shape, (self.n_subjects, self.n_fibers))
        self.assertGreaterEqual(int(np.min(np.sum(np.isfinite(fold_weights), axis=1))), 20)
        self.assertEqual(len(comparison["models"]), 4)
        self.assertFalse(comparison["classification_feedback"])
        np.testing.assert_array_equal(first_null, second_null)
        np.testing.assert_array_equal(
            first_binary,
            (probabilities >= 0.5).astype(np.float32),
        )
        self.assertEqual(first_binary[0, 0], 1.0)
        expected_weights = benefit_oriented_weights(
            partial_spearman_weights(
                self.outcome,
                first_binary,
                self.baseline[:, None],
            ),
            "lower",
        ).astype(np.float32)
        np.testing.assert_allclose(full_weights, expected_weights, rtol=1e-6, atol=1e-6)

    def test_heldout_outcome_does_not_change_its_fold_fit(self) -> None:
        request = self._request()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "first", "oss_fit", "1")
            ).run_activation(request)
            changed_outcome = self.outcome.copy()
            changed_outcome[0] += 100.0
            changed = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "changed", "oss_fit", "1")
            ).run_activation(
                dataclasses.replace(request, outcome=changed_outcome)
            )
            first_weights = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_loocv_benefit_oriented_fiber_weights"
                )
            )
            changed_weights = _artifact_array(
                next(
                    artifact
                    for artifact in changed.artifacts
                    if artifact.kind == "oss_loocv_benefit_oriented_fiber_weights"
                )
            )
            first_scores = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_loocv_fold_net_fiber_scores"
                )
            )
            changed_scores = _artifact_array(
                next(
                    artifact
                    for artifact in changed.artifacts
                    if artifact.kind == "oss_loocv_fold_net_fiber_scores"
                )
            )
            first_predictions = _artifact_array(
                next(
                    artifact
                    for artifact in first.artifacts
                    if artifact.kind == "oss_loocv_model_predictions"
                )
            )
            changed_predictions = _artifact_array(
                next(
                    artifact
                    for artifact in changed.artifacts
                    if artifact.kind == "oss_loocv_model_predictions"
                )
            )
        np.testing.assert_array_equal(first_weights[0], changed_weights[0])
        np.testing.assert_array_equal(first_scores[0], changed_scores[0])
        self.assertEqual(first_predictions[0], changed_predictions[0])

    def test_adjusted_branch_uses_fold_delta_and_reports_invalid_design(self) -> None:
        delta_full = self.latent + 0.2 * np.sin(np.arange(self.n_subjects))
        subject_index = np.arange(self.n_subjects, dtype=np.float64)
        delta_folds = np.stack(
            [
                delta_full[
                    np.roll(
                        np.arange(self.n_subjects),
                        (heldout + 1) * 3,
                    )
                ]
                + 0.05 * np.sin((heldout + 1.3) * (subject_index + 1.0))
                for heldout in range(self.n_subjects)
            ]
        )
        adjusted = _addon_final("delta_reference_adjusted", self.feature_axis)
        request = self._request(
            final=adjusted,
            nuisance_inputs=(delta_full, delta_folds),
        )
        with self.assertRaisesRegex(ValueError, "subject vector"):
            dataclasses.replace(
                request,
                nuisance_inputs=(delta_full[:, None], delta_folds),
            )
        with self.assertRaisesRegex(ValueError, "fold-by-subject"):
            dataclasses.replace(
                request,
                nuisance_inputs=(delta_full, delta_folds[:, :-1]),
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "valid", "oss_fit", "1")
            ).run_activation(request)
            repeated_full = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "repeated", "oss_fit", "1")
            ).run_activation(
                dataclasses.replace(
                    request,
                    nuisance_inputs=(
                        delta_full,
                        np.broadcast_to(
                            delta_full,
                            (self.n_subjects, self.n_subjects),
                        ).copy(),
                    ),
                )
            )
            invalid = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "invalid", "oss_fit", "1")
            ).run_activation(
                dataclasses.replace(
                    request,
                    nuisance_inputs=(
                        np.ones(self.n_subjects),
                        np.ones((self.n_subjects, self.n_subjects)),
                    ),
                )
            )
            collinear_delta = 2.0 * self.baseline + 3.0
            collinear = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "collinear", "oss_fit", "1")
            ).run_activation(
                dataclasses.replace(
                    request,
                    nuisance_inputs=(
                        collinear_delta,
                        np.broadcast_to(
                            collinear_delta,
                            (self.n_subjects, self.n_subjects),
                        ).copy(),
                    ),
                )
            )
            valid_status = self._status(valid)
            invalid_status = self._status(invalid)
            collinear_status = self._status(collinear)
            valid_fold_weights = _artifact_array(
                next(
                    artifact
                    for artifact in valid.artifacts
                    if artifact.kind == "oss_loocv_benefit_oriented_fiber_weights"
                )
            )
            repeated_fold_weights = _artifact_array(
                next(
                    artifact
                    for artifact in repeated_full.artifacts
                    if artifact.kind == "oss_loocv_benefit_oriented_fiber_weights"
                )
            )
        self.assertIn(
            valid_status["oss_sensitivity_status"],
            {"passed_activation_consistent", "passed_activation_model_dependent"},
        )
        self.assertEqual(
            invalid_status["oss_sensitivity_status"],
            "failed_oss_design_or_prediction",
        )
        self.assertEqual(invalid_status["failure_reasons"], ["invalid_delta_reference_scaling"])
        self.assertEqual(
            collinear_status["oss_sensitivity_status"],
            "failed_oss_design_or_prediction",
        )
        self.assertEqual(
            collinear_status["failure_reasons"],
            ["invalid_nuisance_design"],
        )
        finite = np.isfinite(valid_fold_weights[0]) & np.isfinite(
            repeated_fold_weights[0]
        )
        self.assertTrue(np.any(finite))
        self.assertGreater(
            float(
                np.max(
                    np.abs(
                        valid_fold_weights[0, finite]
                        - repeated_fold_weights[0, finite]
                    )
                )
            ),
            1e-6,
        )

    def test_no_delta_addon_is_executable_without_delta_inputs(self) -> None:
        request = self._request(
            final=_addon_final("no_delta_reference", self.feature_axis)
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            ).run_activation(request)
            status = self._status(result)
        self.assertIn(
            status["oss_sensitivity_status"],
            {"passed_activation_consistent", "passed_activation_model_dependent"},
        )

    def test_addon_overlap_mask_is_required_and_applied_before_all_scoring(self) -> None:
        final = _addon_final("no_delta_reference", self.feature_axis)
        overlap = np.zeros_like(self.probabilities, dtype=bool)
        overlap[:, 0] = True
        overlap[0, 1] = True
        request = dataclasses.replace(
            self._request(final=final),
            reference_overlap_mask=overlap,
        )
        with self.assertRaisesRegex(ValueError, "requires a reference_overlap_mask"):
            dataclasses.replace(request, reference_overlap_mask=None)
        with self.assertRaisesRegex(ValueError, "reference activation cannot receive"):
            dataclasses.replace(
                self._request(),
                reference_overlap_mask=overlap,
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            ).run_activation(request)
            status = self._status(result)
            observed_binary = _artifact_array(result.binary_exposure)
            plain_count = _artifact_array(
                next(
                    artifact
                    for artifact in result.artifacts
                    if artifact.kind == "oss_plain_activation_count"
                )
            )
        expected_binary = (self.probabilities >= 0.5).astype(np.float32)
        expected_binary[overlap] = 0.0
        np.testing.assert_array_equal(observed_binary, expected_binary)
        np.testing.assert_array_equal(plain_count, np.sum(expected_binary, axis=1))
        self.assertTrue(status["reference_overlap_applied"])

    def test_addon_overlap_artifact_is_axis_validated_and_materialized(self) -> None:
        overlap = np.zeros_like(self.probabilities, dtype=bool)
        overlap[:, :2] = True
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            overlap_ref = RunScopedArtifactPublisher(
                root / "inputs",
                "synthetic_overlap",
                "1",
            ).array(
                "reference_overlap.npy",
                overlap,
                kind="reference_active_overlap",
                axes=(self.subject_axis, self.feature_axis),
                units="binary",
                space="right_canonical",
            )
            request = dataclasses.replace(
                self._request(
                    final=_addon_final("no_delta_reference", self.feature_axis)
                ),
                reference_overlap_mask=overlap_ref,
            )
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "fit", "oss_fit", "1"),
                artifact_store=ArtifactStore((root,)),
            ).run_activation(request)
            observed_binary = _artifact_array(result.binary_exposure)
        expected_binary = (self.probabilities >= 0.5).astype(np.float32)
        expected_binary[overlap] = 0.0
        np.testing.assert_array_equal(observed_binary, expected_binary)

    def test_constant_peak_score_is_a_design_failure_not_a_pass(self) -> None:
        request = dataclasses.replace(
            self._request(),
            peak_final_score=np.ones(self.n_subjects),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            ).run_activation(request)
            status = self._status(result)
        self.assertEqual(
            status["oss_sensitivity_status"],
            "failed_oss_design_or_prediction",
        )
        self.assertIn(
            "peak_final_score_constant_or_nonfinite",
            status["failure_reasons"],
        )
        self.assertIsNone(status["corr_net_score_oss_vs_peak"])

    def test_incomplete_permutation_has_no_p_value(self) -> None:
        request = dataclasses.replace(self._request(), permutation_resamples=2)
        permuted = np.stack([self.outcome, np.ones(self.n_subjects)])
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(
                ppam_fitting,
                "_freedman_lane_outcomes",
                return_value=permuted,
            ):
                result = PPAMActivationBackend(
                    RunScopedArtifactPublisher(
                        Path(temporary_directory),
                        "oss_fit",
                        "1",
                    )
                ).run_activation(request)
            status = self._status(result)
            permutation = _document_payload(
                next(
                    artifact
                    for artifact in result.artifacts
                    if artifact.kind == "oss_permutation_summary"
                )
            )
        self.assertEqual(
            status["oss_sensitivity_status"],
            "failed_oss_design_or_prediction",
        )
        self.assertIn("permutation_incomplete", status["failure_reasons"])
        self.assertEqual(permutation["status"], "not_complete")
        self.assertEqual(permutation["null_finite_count"], 1)
        self.assertIsNone(permutation["p_plus_one_two_sided"])

    def test_outcome_direction_flips_benefit_oriented_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            lower = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "lower", "oss_fit", "1")
            ).run_activation(self._request(outcome_direction="lower"))
            higher = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "higher", "oss_fit", "1")
            ).run_activation(self._request(outcome_direction="higher"))
            lower_weights = _artifact_array(
                next(
                    artifact
                    for artifact in lower.artifacts
                    if artifact.kind == "oss_benefit_oriented_fiber_weights"
                )
            )
            higher_weights = _artifact_array(
                next(
                    artifact
                    for artifact in higher.artifacts
                    if artifact.kind == "oss_benefit_oriented_fiber_weights"
                )
            )
        np.testing.assert_allclose(lower_weights, -higher_weights, rtol=0, atol=0)

    def test_one_sided_score_remains_executable_and_explicit(self) -> None:
        thresholds = np.linspace(-1.2, 1.2, self.n_fibers)
        probabilities = np.where(
            self.latent[:, None] >= thresholds[None, :],
            0.8,
            0.2,
        ).astype(np.float32)
        request = dataclasses.replace(
            self._request(),
            activation_probability=probabilities,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            ).run_activation(request)
            status = self._status(result)
            support = _document_payload(
                next(
                    artifact
                    for artifact in result.artifacts
                    if artifact.kind == "oss_fiber_score_support"
                )
            )
        self.assertEqual(
            support["full_sample"]["fiber_score_support_status"],
            "limited_positive_only",
        )
        self.assertIn(
            status["oss_sensitivity_status"],
            {"passed_activation_consistent", "passed_activation_model_dependent"},
        )

    def test_all_zero_activation_is_report_only_technical_failure(self) -> None:
        request = dataclasses.replace(
            self._request(),
            activation_probability=np.zeros_like(self.probabilities),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            ).run_activation(request)
            status = self._status(result)
        self.assertEqual(
            status["oss_sensitivity_status"],
            "failed_activation_degenerate",
        )
        self.assertFalse(status["classification_feedback"])

    def test_nonlattice_probability_is_rejected_before_publication(self) -> None:
        probabilities = self.probabilities.copy()
        probabilities[0, 0] = 0.37
        request = dataclasses.replace(
            self._request(),
            activation_probability=probabilities,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            backend = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            )
            with self.assertRaisesRegex(ValueError, "activation count divided by 10"):
                backend.run_activation(request)
            self.assertEqual(tuple(Path(temporary_directory).iterdir()), ())

    def test_activation_feature_id_value_or_order_mismatch_is_rejected(self) -> None:
        mismatched = self.fiber_ids.copy()
        mismatched[[0, 1]] = mismatched[[1, 0]]
        request = dataclasses.replace(
            self._request(),
            activation_feature_ids=mismatched,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            backend = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    Path(temporary_directory),
                    "oss_fit",
                    "1",
                )
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "feature IDs differ",
            ):
                backend.run_activation(request)
            self.assertEqual(tuple(Path(temporary_directory).iterdir()), ())

    def test_row_batch_artifacts_feed_fitter_without_path_discovery(self) -> None:
        subjects = tuple(f"sub-{index:02d}" for index in range(self.n_subjects))
        rows = _rows(subjects, self.feature_axis, self.fiber_ids)

        def producer(row: OSSRowInput) -> OSSRowProduct:
            index = subjects.index(row.subject_id)
            return OSSRowProduct(self.fiber_ids, self.probabilities[index])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            final = _final("scale", self.feature_axis)
            batch = OSSRowMaterializer(
                ContentAddressedCache(root / "cache"),
                RunScopedArtifactPublisher(root / "rows", "oss_rows", "1"),
                producer=producer,
            ).materialize(
                OSSRowBatchRequest(
                    final_model=final,
                    connectome_role="formal",
                    subject_axis=self.subject_axis,
                    subject_ids=subjects,
                    feature_axis=self.feature_axis,
                    feature_ids=self.fiber_ids,
                    rows=rows,
                    settings=OSSScientificSettings(backend_version="2.2.0"),
                    allow_expensive_producers=True,
                    workers=3,
                )
            )
            request = dataclasses.replace(
                self._request(final=final),
                activation_probability=batch.activation_probability,
                feature_ids=batch.feature_ids,
                activation_feature_ids=batch.feature_ids,
            )
            result = PPAMActivationBackend(
                RunScopedArtifactPublisher(root / "fit", "oss_fit", "1"),
                artifact_store=ArtifactStore((root,)),
            ).run_activation(request)
            status = self._status(result)
        self.assertIn(
            status["oss_sensitivity_status"],
            {"passed_activation_consistent", "passed_activation_model_dependent"},
        )


class CompletedOSSFixtureContractTest(unittest.TestCase):
    frozen_manifest = (
        Path(__file__).resolve().parents[3]
        / "projects/stnsnr/acceptance/frozen/20260711T034644Z_d318f177f7f2ac7d"
        / "bounded_fixture_manifest.json"
    )

    @unittest.skipUnless(
        frozen_manifest.is_file(),
        "completed bounded OSS fixtures are unavailable",
    )
    def test_allowlisted_matrix_supports_bounded_subset_and_threshold_replay(self) -> None:
        frozen = json.loads(self.frozen_manifest.read_text(encoding="utf-8"))
        tasks = {task["task_id"]: task for task in frozen["eligible_tasks"]}
        sidecar = tasks["task_07369f7915997b203e03"]
        sensitivity = tasks["task_5f8a7058c24e684281c9"]
        self.assertEqual(sidecar["status"], "completed")
        self.assertEqual(sensitivity["status"], "completed")
        artifacts = {artifact["kind"]: artifact for artifact in sidecar["artifacts"]}
        sensitivity_artifacts = {
            artifact["kind"]: artifact for artifact in sensitivity["artifacts"]
        }
        consumed = (
            sidecar["task_manifest"],
            artifacts["oss_activation_metadata"],
            artifacts["oss_activation_probabilities"],
            artifacts["oss_fiber_ids"],
            artifacts["oss_parameter_manifest"],
            sensitivity["task_manifest"],
            sensitivity_artifacts["oss_activation_results"],
        )
        missing = [
            Path(artifact["path"])
            for artifact in consumed
            if not Path(artifact["path"]).is_file()
        ]
        if missing:
            self.skipTest(
                "completed bounded OSS fixture files are unavailable: "
                + ", ".join(str(path) for path in missing)
            )
        for artifact in consumed:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256_file(path), artifact["sha256"], path)

        matrix = np.load(
            artifacts["oss_activation_probabilities"]["path"],
            allow_pickle=False,
            mmap_mode="r",
        )
        fiber_ids = np.load(
            artifacts["oss_fiber_ids"]["path"],
            allow_pickle=False,
            mmap_mode="r",
        )
        metadata = json.loads(
            Path(artifacts["oss_activation_metadata"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(matrix.shape, (16, 3990))
        self.assertEqual(matrix.dtype, np.dtype(np.float32))
        self.assertEqual(fiber_ids.shape, (3990,))
        self.assertEqual(fiber_ids.dtype, np.dtype(np.int64))
        self.assertEqual(metadata["hemisphere_source_merge_rule"], "max_probability_union")
        self.assertEqual(metadata["canonical_hemisphere"], "right")
        self.assertEqual(metadata["ppam_sample_count"], 10)

        subject_indices = np.asarray([0, 7, 15], dtype=np.int64)
        fiber_indices = np.linspace(0, fiber_ids.size - 1, 48, dtype=np.int64)
        requested_ids = np.asarray(fiber_ids[fiber_indices], dtype=np.int64)
        observed = subset_probability_axis(
            np.asarray(matrix[subject_indices]),
            source_fiber_ids=np.asarray(fiber_ids),
            requested_fiber_ids=requested_ids,
        )
        expected = np.asarray(matrix[np.ix_(subject_indices, fiber_indices)])
        np.testing.assert_array_equal(observed, expected)
        np.testing.assert_array_equal(
            binary_activation(observed),
            (expected >= 0.5).astype(np.float32),
        )


if __name__ == "__main__":
    unittest.main()
