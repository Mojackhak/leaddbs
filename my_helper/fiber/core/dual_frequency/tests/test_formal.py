"""Final-only formal inference contract and deterministic numerical tests."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote, urlsplit

import numpy as np

import dual_frequency.backends as public_backends
import dual_frequency.backends.protocols as backend_protocols
import dual_frequency.contracts as public_contracts
import dual_frequency.contracts.requests as request_contracts
from dual_frequency.backends.formal import (
    DirectVoxelFormalBackend,
    FormalBackendError,
    FormalBackendInputError,
    NormativeFiberFormalBackend,
    compute_direct_voxel_bootstrap,
    compute_direct_voxel_permutation,
    compute_normative_fiber_bootstrap,
    compute_normative_fiber_permutation,
)
from dual_frequency.backends.formal.common import (
    PermutationComputation,
    StreamingBootstrapAccumulator,
    build_bootstrap_nuisance_plan,
    build_fixed_nuisance_plan,
)
from dual_frequency.backends.formal.direct_voxel import (
    _build_fold_operators as _build_direct_fold_operators,
)
from dual_frequency.backends.formal.normative_fiber import _fold_candidate_masks
from dual_frequency.backends.normative_fiber.coverage import coverage_counts
from dual_frequency.cache import RunScopedArtifactPublisher, sha256_file
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BootstrapNuisanceEvidence,
    BootstrapRebuildProvenance,
    BranchRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FormalRequest,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    RequestError,
    SourceRecord,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
ALLOWLIST_PATH = (
    REPOSITORY_ROOT
    / "my_helper/fiber/projects/stnsnr/acceptance/approved_task_allowlist.json"
)
FROZEN_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "my_helper/fiber/projects/stnsnr/acceptance/frozen"
    / "20260711T034644Z_d318f177f7f2ac7d/bounded_fixture_manifest.json"
)
FORMAL_TASK_IDS = {
    "task_8a8aae8bccdbe7051226",
    "task_105bd4ea4fed6a70fd81",
    "task_49604ac969f9c1a045c2",
    "task_4c0176441302daf11384",
}


_SCIENTIFIC_ARRAYS: dict[str, np.ndarray] = {}


def _axis(axis_id: str, count: int, character: str) -> AxisRef:
    return AxisRef(axis_id, count, character * 64)


def _scientific_artifact(
    kind: str,
    value: np.ndarray,
    axes: tuple[AxisRef, ...],
    *,
    units: str,
    space: str,
) -> ArtifactRef:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    sha256 = digest.hexdigest()
    artifact = ArtifactRef(
        kind=kind,
        schema_version="array_v1",
        uri=f"memory://formal-fixture/{kind}-{sha256[:16]}.npy",
        sha256=sha256,
        dtype=array.dtype.name,
        shape=array.shape,
        axis_refs=axes,
        axis_hashes=tuple(axis.sha256 for axis in axes),
        units=units,
        space=space,
        producer_id="formal_fixture",
        producer_version="1",
    )
    stored = np.array(array, copy=True)
    stored.flags.writeable = False
    _SCIENTIFIC_ARRAYS[artifact.identifier] = stored
    return artifact


class _ScientificArrayStore:
    def materialize(
        self,
        artifact: ArtifactRef,
        *,
        expected_dtype: str | np.dtype,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None = None,
    ) -> np.ndarray:
        del mmap_mode
        if artifact.identifier not in _SCIENTIFIC_ARRAYS:
            raise AssertionError(f"unexpected fixture artifact: {artifact.kind}")
        value = _SCIENTIFIC_ARRAYS[artifact.identifier]
        if np.dtype(expected_dtype) != value.dtype:
            raise AssertionError("fixture dtype requirement changed")
        if expected_shape != value.shape:
            raise AssertionError("fixture shape requirement changed")
        if expected_axes != artifact.axis_refs:
            raise AssertionError("fixture axis requirement changed")
        if expected_units != artifact.units or expected_space != artifact.space:
            raise AssertionError("fixture scientific metadata requirement changed")
        output = np.array(value, copy=True)
        output.flags.writeable = False
        return output


def _artifact_value(value: ArtifactRef) -> np.ndarray:
    return _ScientificArrayStore().materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=value.shape,
        expected_axes=value.axis_refs,
        expected_units=value.units,
        expected_space=value.space,
    )


def _source_artifact(axis: AxisRef, model_family: str) -> ArtifactRef:
    return ArtifactRef(
        kind="selected_weights",
        schema_version="array_v1",
        uri=f"memory://formal-fixture/{model_family}-weights.npy",
        sha256="f" * 64,
        dtype="float64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="right_canonical",
        producer_id="formal_fixture",
        producer_version="1",
    )


def _fiber_id_artifact(axis: AxisRef) -> ArtifactRef:
    return _scientific_artifact(
        "normative_fiber_valid_union_ids",
        np.arange(10_000, 10_000 + axis.count, dtype=np.int64),
        (axis,),
        units="fiber_id",
        space="right_canonical",
    )


def _final_model(
    model_family: str,
    feature_axis: AxisRef,
    *,
    branch: str = "reference",
    tau: float = 200.0,
    coverage: int = 5,
) -> FinalModelRecord:
    is_fiber = model_family.endswith("fiber")
    is_reference = model_family.startswith("reference_")
    endpoint = EndpointKey(
        study_id="formal_fixture",
        scale_id="synthetic_scale",
        endpoint_binding_id="reference" if is_reference else "addon",
        model_family=model_family,
        connectome_id="dtor" if is_fiber else "none",
    )
    source_artifacts = [_source_artifact(feature_axis, model_family)]
    if is_fiber:
        source_artifacts.append(_fiber_id_artifact(feature_axis))
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_predictive",
        threshold_source="pre_specified",
        selected_tau=tau,
        selected_coverage=coverage,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(
            feature_axis,
            "canonical_fiber_ids" if is_fiber else "canonical_brainmask",
        ),
        artifacts=tuple(source_artifacts),
    )
    final_key = FinalModelKey(
        endpoint.identifier,
        branch,
        tau,
        coverage,
        "continuous_dose_signed_peak" if is_fiber else "continuous_dose_mean",
    )
    if is_reference:
        return FinalModelRecord(
            endpoint=endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=final_key,
            selected_source=source,
            selected_branch=None,
        )
    selected_branch = BranchRecord(
        endpoint=endpoint,
        branch=branch,
        intended_role="primary",
        input_status="valid",
        nuisance_design_status="valid",
        source=source,
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=final_key,
        selected_source=None,
        selected_branch=selected_branch,
    )


def _synthetic_arrays(*, n_subjects: int = 16, n_features: int = 32) -> tuple[np.ndarray, ...]:
    z = np.linspace(-1.5, 1.5, n_subjects, dtype=np.float64)
    loadings = np.linspace(0.8, 1.2, n_features, dtype=np.float64)
    loadings[n_features // 2 :] *= -1.0
    subject_index = np.arange(1, n_subjects + 1, dtype=np.float64)[:, None]
    feature_index = np.arange(1, n_features + 1, dtype=np.float64)[None, :]
    exposure = (
        260.0
        + 20.0 * z[:, None] * loadings[None, :]
        + 0.25 * np.sin(subject_index * feature_index)
    )
    baseline = 25.0 + 2.0 * np.sin(np.arange(n_subjects, dtype=np.float64) + 0.3)
    outcome = 40.0 - 8.0 * z + 0.3 * baseline + 0.1 * np.cos(subject_index[:, 0])
    return exposure, outcome, baseline, z


def _score_settings() -> NormativeFiberScoreSettings:
    return NormativeFiberScoreSettings(
        sweet_fraction=0.25,
        sour_fraction=0.25,
        weighted_peak_fraction=0.25,
        sweet_selected_min_count=2,
        sour_selected_min_count=2,
        weighted_peak_min_count=1,
    )


def _formal_request(
    model_family: str,
    resampling_kind: str,
    *,
    branch: str = "reference",
    resamples: int = 10,
    seed: int = 42,
    exposure: np.ndarray | None = None,
) -> FormalRequest:
    if exposure is None:
        exposure, outcome, baseline, z = _synthetic_arrays()
    else:
        _, outcome, baseline, z = _synthetic_arrays(
            n_subjects=exposure.shape[0],
            n_features=exposure.shape[1],
        )
    n_subjects, n_features = exposure.shape
    subject_axis = _axis("formal_subjects", n_subjects, "a")
    feature_axis = _axis(
        "formal_fibers" if model_family.endswith("fiber") else "formal_voxels",
        n_features,
        "b",
    )
    adjusted = branch == "delta_reference_adjusted"
    delta_full = 0.7 * z + 0.05 * np.sin(np.arange(n_subjects, dtype=np.float64))
    delta_folds = np.broadcast_to(delta_full, (n_subjects, n_subjects)).copy()
    final_model = _final_model(model_family, feature_axis, branch=branch)
    selected_source = final_model.selected_source
    if selected_source is None and final_model.selected_branch is not None:
        selected_source = final_model.selected_branch.source
    feature_ids = None
    if model_family.endswith("fiber"):
        assert selected_source is not None
        feature_ids = next(
            artifact
            for artifact in selected_source.artifacts
            if artifact.kind == "normative_fiber_valid_union_ids"
        )
    return FormalRequest(
        final_model=final_model,
        resampling_kind=resampling_kind,
        exposure=_scientific_artifact(
            f"{model_family}_formal_exposure",
            np.asarray(exposure, dtype=np.float64),
            (subject_axis, feature_axis),
            units="V/m",
            space="right_canonical",
        ),
        outcome=_scientific_artifact(
            f"{model_family}_formal_outcome",
            outcome,
            (subject_axis,),
            units="score",
            space="clinical",
        ),
        baseline=_scientific_artifact(
            f"{model_family}_formal_baseline",
            baseline,
            (subject_axis,),
            units="score",
            space="clinical",
        ),
        delta_reference_full=(
            _scientific_artifact(
                f"{model_family}_delta_reference_full",
                delta_full,
                (subject_axis,),
                units="score",
                space="clinical",
            )
            if adjusted
            else None
        ),
        delta_reference_folds=(
            _scientific_artifact(
                f"{model_family}_delta_reference_folds",
                delta_folds,
                (subject_axis, subject_axis),
                units="score",
                space="clinical",
            )
            if adjusted
            else None
        ),
        subject_axis=subject_axis,
        feature_axis=feature_axis,
        exposure_units="V/m",
        exposure_space="right_canonical",
        outcome_direction="lower",
        hard_computability=(
            HardComputabilityLimits(12, None, 10)
            if model_family.endswith("fiber")
            else HardComputabilityLimits(12, 20, 10)
        ),
        connectome_role="formal" if model_family.endswith("fiber") else "none",
        feature_ids=feature_ids,
        fiber_score_settings=_score_settings() if model_family.endswith("fiber") else None,
        resamples=resamples,
        seed=seed,
    )


def _fiber_id_values(request: FormalRequest) -> np.ndarray:
    if request.feature_ids is None:
        raise AssertionError("fixture request has no fiber ID artifact")
    return _artifact_value(request.feature_ids)


def _original_delta_values(request: FormalRequest) -> tuple[np.ndarray, np.ndarray]:
    if request.delta_reference_full is None or request.delta_reference_folds is None:
        raise AssertionError("fixture request has no DeltaReferenceScore artifacts")
    return (
        _artifact_value(request.delta_reference_full),
        _artifact_value(request.delta_reference_folds),
    )


def _artifact_path(artifact: ArtifactRef) -> Path:
    parsed = urlsplit(artifact.uri)
    if parsed.scheme != "file":
        raise AssertionError("test publisher did not return a local file artifact")
    return Path(unquote(parsed.path))


class _SyntheticBootstrapNuisanceProvider:
    def __init__(self, baseline: np.ndarray) -> None:
        self.baseline = np.asarray(baseline, dtype=np.float64)
        self.calls: list[np.ndarray] = []

    def build_bootstrap_nuisance(
        self,
        request: FormalRequest,
        sample_indices: np.ndarray,
    ) -> BootstrapNuisanceEvidence:
        sample = np.asarray(sample_indices, dtype=np.int64)
        replicate = len(self.calls)
        self.calls.append(sample.copy())
        n_subjects = sample.size
        raw_delta = np.arange(n_subjects, dtype=np.float64) + 0.05 * np.sin(
            np.arange(n_subjects, dtype=np.float64) + replicate
        )
        folds = np.empty((n_subjects, n_subjects), dtype=np.float64)
        for heldout in range(n_subjects):
            folds[heldout] = raw_delta + 0.01 * np.cos(
                (heldout + 1) * (np.arange(n_subjects, dtype=np.float64) + 1)
                + replicate
            )
        provenance = BootstrapRebuildProvenance.from_rebuild(
            provider_id="synthetic_bootstrap_nuisance_provider",
            provider_version="1",
            final_model_id=request.final_model.identifier,
            subject_axis=request.subject_axis,
            sample_indices=sample,
            delta_reference_full_scores=raw_delta,
            delta_reference_fold_scores=folds,
        )
        return BootstrapNuisanceEvidence(
            sample_indices=sample,
            delta_reference_full_scores=raw_delta,
            delta_reference_fold_scores=folds,
            support_status="limited" if replicate % 2 else "adequate",
            support_qc=(
                ("replicate_token", replicate),
                ("median_out_support_fraction", 0.1 + 0.01 * replicate),
            ),
            rebuild_provenance=provenance,
        )


class FormalRequestContractTest(unittest.TestCase):
    def test_request_is_final_only_axis_locked_and_role_specific(self) -> None:
        direct = _formal_request("reference_voxel", "permutation")
        with self.assertRaisesRegex(RequestError, "FinalModelRecord"):
            dataclasses.replace(direct, final_model=object())
        with self.assertRaisesRegex(RequestError, "resampling_kind"):
            dataclasses.replace(direct, resampling_kind="permutation_and_bootstrap")
        with self.assertRaisesRegex(RequestError, "ArtifactRef"):
            dataclasses.replace(direct, exposure=Path("exposure.npy"))
        for field in ("exposure", "outcome", "baseline"):
            with self.subTest(field=field), self.assertRaisesRegex(
                RequestError,
                "ArtifactRef",
            ):
                dataclasses.replace(
                    direct,
                    **{field: np.asarray(_artifact_value(getattr(direct, field)))},
                )
        reordered_subject_axis = _axis(
            "reordered_formal_subjects",
            direct.subject_axis.count,
            "e",
        )
        reordered_outcome = _scientific_artifact(
            "reordered_outcome",
            _artifact_value(direct.outcome)[::-1],
            (reordered_subject_axis,),
            units="score",
            space="clinical",
        )
        with self.assertRaisesRegex(RequestError, "artifact axes"):
            dataclasses.replace(direct, outcome=reordered_outcome)
        with self.assertRaisesRegex(RequestError, "final.valid_feature_axis"):
            dataclasses.replace(
                direct,
                feature_axis=_axis("other_voxels", direct.feature_axis.count, "c"),
            )
        with self.assertRaisesRegex(RequestError, "connectome_role='none'"):
            dataclasses.replace(direct, connectome_role="formal")

        fiber = _formal_request("reference_fiber", "permutation")
        with self.assertRaisesRegex(RequestError, "connectome_role='formal'"):
            dataclasses.replace(fiber, connectome_role="sensitive")
        with self.assertRaisesRegex(RequestError, "fiber IDs"):
            dataclasses.replace(fiber, feature_ids=None)
        with self.assertRaisesRegex(RequestError, "exact immutable ID artifact"):
            dataclasses.replace(
                fiber,
                feature_ids=_fiber_id_values(fiber)[::-1].copy(),
            )
        assert fiber.feature_ids is not None
        reordered_artifact = dataclasses.replace(
            fiber.feature_ids,
            uri="memory://formal-fixture/reordered-valid-fiber-ids.npy",
            sha256="e" * 64,
        )
        with self.assertRaisesRegex(RequestError, "exactly equal"):
            dataclasses.replace(fiber, feature_ids=reordered_artifact)

    def test_fiber_request_rejects_nonunique_selected_source_id_artifact(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        source = request.final_model.selected_source
        assert source is not None
        duplicate = dataclasses.replace(
            request.feature_ids,
            uri="memory://formal-fixture/duplicate-valid-fiber-ids.npy",
        )
        ambiguous_source = dataclasses.replace(
            source,
            artifacts=source.artifacts + (duplicate,),
        )
        ambiguous_final = dataclasses.replace(
            request.final_model,
            selected_source=ambiguous_source,
        )
        with self.assertRaisesRegex(RequestError, "exactly one"):
            dataclasses.replace(request, final_model=ambiguous_final)

    def test_branch_specific_delta_inputs_are_explicit(self) -> None:
        adjusted = _formal_request(
            "addon_voxel",
            "permutation",
            branch="delta_reference_adjusted",
        )
        with self.assertRaisesRegex(RequestError, "full and fold"):
            dataclasses.replace(adjusted, delta_reference_folds=None)
        assert adjusted.delta_reference_full is not None
        assert adjusted.delta_reference_folds is not None
        for field in ("delta_reference_full", "delta_reference_folds"):
            with self.subTest(field=field), self.assertRaisesRegex(
                RequestError,
                "ArtifactRef",
            ):
                dataclasses.replace(
                    adjusted,
                    **{field: np.asarray(_artifact_value(getattr(adjusted, field)))},
                )
        no_delta = _formal_request(
            "addon_voxel",
            "permutation",
            branch="no_delta_reference",
        )
        with self.assertRaisesRegex(RequestError, "cannot receive"):
            dataclasses.replace(
                no_delta,
                delta_reference_full=np.arange(no_delta.subject_axis.count),
            )


class FormalPermutationTest(unittest.TestCase):
    def test_direct_optimized_matches_brute_force_for_ten_permutations(self) -> None:
        request = _formal_request("reference_voxel", "permutation")
        exposure = _artifact_value(request.exposure)
        outcome = _artifact_value(request.outcome)
        baseline = _artifact_value(request.baseline)
        nuisance = build_fixed_nuisance_plan(request, baseline, None, None)
        optimized = compute_direct_voxel_permutation(
            request,
            exposure,
            outcome,
            nuisance,
            optimized=True,
        )
        brute = compute_direct_voxel_permutation(
            request,
            exposure,
            outcome,
            nuisance,
            optimized=False,
        )
        np.testing.assert_allclose(
            optimized.null_statistics,
            brute.null_statistics,
            rtol=0.0,
            atol=1e-12,
            equal_nan=True,
        )
        self.assertAlmostEqual(
            optimized.observed_metrics["loocv_spearman_rho"],
            brute.observed_metrics["loocv_spearman_rho"],
            places=12,
        )
        self.assertEqual(optimized.p_plus_one_two_sided, brute.p_plus_one_two_sided)

    def test_fiber_optimized_matches_brute_force_for_ten_permutations(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        exposure = _artifact_value(request.exposure)
        outcome = _artifact_value(request.outcome)
        baseline = _artifact_value(request.baseline)
        fiber_ids = _fiber_id_values(request)
        nuisance = build_fixed_nuisance_plan(request, baseline, None, None)
        optimized = compute_normative_fiber_permutation(
            request,
            exposure,
            fiber_ids,
            outcome,
            nuisance,
            optimized=True,
        )
        brute = compute_normative_fiber_permutation(
            request,
            exposure,
            fiber_ids,
            outcome,
            nuisance,
            optimized=False,
        )
        np.testing.assert_allclose(
            optimized.null_statistics,
            brute.null_statistics,
            rtol=0.0,
            atol=1e-12,
            equal_nan=True,
        )
        self.assertAlmostEqual(
            optimized.observed_metrics["loocv_spearman_rho"],
            brute.observed_metrics["loocv_spearman_rho"],
            places=12,
        )
        self.assertEqual(optimized.p_plus_one_two_sided, brute.p_plus_one_two_sided)

    def test_direct_null_rejects_partial_finite_prediction_vector(self) -> None:
        request = _formal_request("reference_voxel", "permutation", resamples=2)
        nuisance = build_fixed_nuisance_plan(
            request,
            _artifact_value(request.baseline),
            None,
            None,
        )
        observed = {
            "all_predictions_finite": 1.0,
            "loocv_spearman_rho": 0.5,
        }
        partial = {
            "all_predictions_finite": 0.0,
            "loocv_spearman_rho": 0.9,
        }
        complete = {
            "all_predictions_finite": 1.0,
            "loocv_spearman_rho": -0.25,
        }
        with mock.patch(
            "dual_frequency.backends.formal.direct_voxel._optimized_loocv",
            side_effect=(observed, partial, complete),
        ):
            result = compute_direct_voxel_permutation(
                request,
                _artifact_value(request.exposure),
                _artifact_value(request.outcome),
                nuisance,
            )
        self.assertTrue(np.isnan(result.null_statistics[0]))
        self.assertEqual(result.null_statistics[1], -0.25)
        self.assertIsNone(result.p_plus_one_two_sided)

    def test_fiber_null_rejects_partial_finite_prediction_vector(self) -> None:
        request = _formal_request("reference_fiber", "permutation", resamples=2)
        nuisance = build_fixed_nuisance_plan(
            request,
            _artifact_value(request.baseline),
            None,
            None,
        )
        observed = {
            "all_predictions_finite": 1.0,
            "loocv_spearman_rho": 0.5,
        }
        partial = {
            "all_predictions_finite": 0.0,
            "loocv_spearman_rho": 0.9,
        }
        complete = {
            "all_predictions_finite": 1.0,
            "loocv_spearman_rho": -0.25,
        }
        with mock.patch(
            "dual_frequency.backends.formal.normative_fiber._loocv",
            side_effect=(observed, partial, complete),
        ):
            result = compute_normative_fiber_permutation(
                request,
                _artifact_value(request.exposure),
                _fiber_id_values(request),
                _artifact_value(request.outcome),
                nuisance,
            )
        self.assertTrue(np.isnan(result.null_statistics[0]))
        self.assertEqual(result.null_statistics[1], -0.25)
        self.assertIsNone(result.p_plus_one_two_sided)

    def test_partial_null_publication_has_no_p_value_and_reports_attrition(self) -> None:
        request = _formal_request("reference_voxel", "permutation", resamples=2)
        computation = PermutationComputation(
            observed_metrics={"loocv_spearman_rho": 0.5},
            null_statistics=np.array([np.nan, -0.25], dtype=np.float64),
            p_plus_one_two_sided=None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            backend = DirectVoxelFormalBackend(
                RunScopedArtifactPublisher(Path(temporary), "formal_test", "1")
            )
            result = backend._publish_permutation(request, computation)
            self.assertEqual(
                result.technical_status,
                "completed_with_nonfinite_replicates",
            )
            summary_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_permutation_summary"
            )
            payload = json.loads(
                _artifact_path(summary_ref).read_text(encoding="utf-8")
            )
            self.assertIsNone(payload["p_plus_one_two_sided"])
            self.assertEqual(payload["finite_replicate_count"], 1)

        with self.assertRaisesRegex(FormalBackendError, "cannot carry"):
            PermutationComputation(
                observed_metrics={"loocv_spearman_rho": 0.5},
                null_statistics=np.array([np.nan, -0.25], dtype=np.float64),
                p_plus_one_two_sided=0.5,
            )

    def test_obsolete_generic_sensitivity_api_is_not_public(self) -> None:
        self.assertFalse(hasattr(public_contracts, "SensitivityRequest"))
        self.assertFalse(hasattr(request_contracts, "SensitivityRequest"))
        self.assertFalse(hasattr(public_backends, "SensitivityBackend"))
        self.assertFalse(hasattr(backend_protocols, "SensitivityBackend"))

    def test_direct_voxel_coverage_excludes_values_equal_to_tau(self) -> None:
        request = _formal_request("reference_voxel", "permutation")
        exposure = _artifact_value(request.exposure).copy()
        tau = float(request.final_model.final_key.selected_tau)
        exposure[:, 0] = tau
        nuisance = build_fixed_nuisance_plan(
            request,
            _artifact_value(request.baseline),
            None,
            None,
        )
        operators = _build_direct_fold_operators(request, exposure, nuisance)
        self.assertTrue(
            all(
                operator.candidate_count == request.feature_axis.count - 1
                for operator in operators
            )
        )

    def test_normative_fiber_coverage_excludes_values_equal_to_tau(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        exposure = _artifact_value(request.exposure).copy()
        tau = float(request.final_model.final_key.selected_tau)
        exposure[:, 0] = tau
        self.assertEqual(int(coverage_counts(exposure, tau)[0]), 0)
        masks = _fold_candidate_masks(request, exposure)
        self.assertTrue(all(not bool(mask[0]) for mask in masks))


class FormalBootstrapTest(unittest.TestCase):
    @staticmethod
    def _assert_bootstrap_equal(first: object, second: object) -> None:
        for field in dataclasses.fields(first):
            left = getattr(first, field.name)
            right = getattr(second, field.name)
            if isinstance(left, np.ndarray):
                np.testing.assert_array_equal(left, right)
            else:
                if left != right:
                    raise AssertionError(f"bootstrap field differs: {field.name}")

    def test_streaming_accumulator_enforces_exact_feature_and_resample_shapes(self) -> None:
        accumulator = StreamingBootstrapAccumulator(
            resamples=2,
            n_features=3,
            track_selection=False,
        )
        with self.assertRaisesRegex(FormalBackendInputError, "exact shape F"):
            accumulator.update(
                0,
                weights=np.ones(2),
                candidate_mask=np.ones(3, dtype=bool),
                support_code=2,
                nuisance_evidence=None,
            )
        accumulator.update(
            0,
            weights=np.ones(3),
            candidate_mask=np.ones(3, dtype=bool),
            support_code=2,
            nuisance_evidence=None,
        )
        with self.assertRaisesRegex(FormalBackendInputError, "missing replicates"):
            accumulator.finalize()
        with self.assertRaisesRegex(FormalBackendInputError, "accumulated twice"):
            accumulator.update(
                0,
                weights=np.ones(3),
                candidate_mask=np.ones(3, dtype=bool),
                support_code=2,
                nuisance_evidence=None,
            )

    def test_direct_and_fiber_bootstrap_prefixes_are_deterministic(self) -> None:
        direct = _formal_request("reference_voxel", "bootstrap")
        direct_first = compute_direct_voxel_bootstrap(
            direct,
            _artifact_value(direct.exposure),
            _artifact_value(direct.outcome),
            _artifact_value(direct.baseline),
            None,
        )
        direct_second = compute_direct_voxel_bootstrap(
            direct,
            _artifact_value(direct.exposure),
            _artifact_value(direct.outcome),
            _artifact_value(direct.baseline),
            None,
        )
        self._assert_bootstrap_equal(direct_first, direct_second)
        self.assertEqual(direct_first.replicate_candidate_count.shape, (10,))
        self.assertEqual(direct_first.weight_mean.shape, (direct.feature_axis.count,))

        fiber = _formal_request("reference_fiber", "bootstrap")
        fiber_first = compute_normative_fiber_bootstrap(
            fiber,
            _artifact_value(fiber.exposure),
            _fiber_id_values(fiber),
            _artifact_value(fiber.outcome),
            _artifact_value(fiber.baseline),
            None,
        )
        fiber_second = compute_normative_fiber_bootstrap(
            fiber,
            _artifact_value(fiber.exposure),
            _fiber_id_values(fiber),
            _artifact_value(fiber.outcome),
            _artifact_value(fiber.baseline),
            None,
        )
        self._assert_bootstrap_equal(fiber_first, fiber_second)
        self.assertEqual(fiber_first.sweet_selection_frequency.shape, (fiber.feature_axis.count,))
        self.assertEqual(fiber_first.sour_selection_frequency.shape, (fiber.feature_axis.count,))

    def test_bootstrap_evidence_rejects_stale_score_payload_identity(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)
        evidence = _SyntheticBootstrapNuisanceProvider(
            _artifact_value(request.baseline)
        ).build_bootstrap_nuisance(request, sample)
        with self.assertRaisesRegex(RequestError, "rebuilt DeltaReferenceScore"):
            dataclasses.replace(
                evidence,
                delta_reference_full_scores=(
                    evidence.delta_reference_full_scores + 1.0
                ),
            )

    def test_bootstrap_provenance_binds_order_not_only_multiplicity(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        count = request.subject_axis.count
        first_sample = np.arange(count, dtype=np.int64)
        reordered_sample = np.roll(first_sample, 1)
        full, folds = _original_delta_values(request)
        first = BootstrapRebuildProvenance.from_rebuild(
            provider_id="ordered_sample_test",
            provider_version="1",
            final_model_id=request.final_model.identifier,
            subject_axis=request.subject_axis,
            sample_indices=first_sample,
            delta_reference_full_scores=full,
            delta_reference_fold_scores=folds,
        )
        reordered = BootstrapRebuildProvenance.from_rebuild(
            provider_id="ordered_sample_test",
            provider_version="1",
            final_model_id=request.final_model.identifier,
            subject_axis=request.subject_axis,
            sample_indices=reordered_sample,
            delta_reference_full_scores=full,
            delta_reference_fold_scores=folds,
        )
        self.assertNotEqual(first.sample_indices_sha256, reordered.sample_indices_sha256)

    def test_nonidentity_bootstrap_rejects_unchanged_original_delta_values(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        original_full, original_folds = _original_delta_values(request)
        sample = np.roll(
            np.arange(request.subject_axis.count, dtype=np.int64),
            1,
        )

        class StaleProvider:
            def __init__(self, *, stale_full: bool) -> None:
                self.stale_full = stale_full

            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                full = (
                    original_full.copy()
                    if self.stale_full
                    else original_full
                    + np.linspace(0.01, 0.16, original_full.size)
                )
                folds = original_folds.copy()
                provenance = BootstrapRebuildProvenance.from_rebuild(
                    provider_id="stale_provider",
                    provider_version="1",
                    final_model_id=formal_request.final_model.identifier,
                    subject_axis=formal_request.subject_axis,
                    sample_indices=sample_indices,
                    delta_reference_full_scores=full,
                    delta_reference_fold_scores=folds,
                )
                return BootstrapNuisanceEvidence(
                    sample_indices=sample_indices,
                    delta_reference_full_scores=full,
                    delta_reference_fold_scores=folds,
                    support_status="adequate",
                    support_qc=(("test", True),),
                    rebuild_provenance=provenance,
                )

        with self.assertRaisesRegex(FormalBackendInputError, "stale full"):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                StaleProvider(stale_full=True),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )
        with self.assertRaisesRegex(FormalBackendInputError, "stale fold"):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                StaleProvider(stale_full=False),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )

    def test_nonidentity_bootstrap_rejects_reindexed_original_delta_values(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        original_full, original_folds = _original_delta_values(request)
        sample = np.roll(
            np.arange(request.subject_axis.count, dtype=np.int64),
            1,
        )

        class ReindexedProvider:
            def __init__(self, *, stale_full: bool) -> None:
                self.stale_full = stale_full

            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                full = original_full[sample_indices]
                if not self.stale_full:
                    full = full + np.linspace(0.01, 0.16, full.size)
                folds = original_folds[np.ix_(sample_indices, sample_indices)]
                provenance = BootstrapRebuildProvenance.from_rebuild(
                    provider_id="reindexed_provider",
                    provider_version="1",
                    final_model_id=formal_request.final_model.identifier,
                    subject_axis=formal_request.subject_axis,
                    sample_indices=sample_indices,
                    delta_reference_full_scores=full,
                    delta_reference_fold_scores=folds,
                )
                return BootstrapNuisanceEvidence(
                    sample_indices=sample_indices,
                    delta_reference_full_scores=full,
                    delta_reference_fold_scores=folds,
                    support_status="adequate",
                    support_qc=(("test", True),),
                    rebuild_provenance=provenance,
                )

        with self.assertRaisesRegex(FormalBackendInputError, "stale full"):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                ReindexedProvider(stale_full=True),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )
        with self.assertRaisesRegex(FormalBackendInputError, "stale fold"):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                ReindexedProvider(stale_full=False),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )

    def test_bootstrap_support_qc_rejects_classification_feedback(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)
        evidence = _SyntheticBootstrapNuisanceProvider(
            _artifact_value(request.baseline)
        ).build_bootstrap_nuisance(request, sample)

        with self.assertRaisesRegex(RequestError, "classification mutation key"):
            dataclasses.replace(
                evidence,
                support_qc=(("prediction_status", "error_predictive"),),
            )
        with self.assertRaisesRegex(RequestError, "classification value"):
            dataclasses.replace(
                evidence,
                support_qc=(("technical_note", "error_predictive"),),
            )

    def test_bootstrap_evidence_rejects_wrong_final_identity(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)
        evidence = _SyntheticBootstrapNuisanceProvider(
            _artifact_value(request.baseline)
        ).build_bootstrap_nuisance(request, sample)
        wrong_identity = dataclasses.replace(
            evidence,
            rebuild_provenance=dataclasses.replace(
                evidence.rebuild_provenance,
                final_model_id="different_final_model",
            ),
        )

        class WrongIdentityProvider:
            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                return wrong_identity

        with self.assertRaisesRegex(FormalBackendInputError, "different final model"):
            original_full, original_folds = _original_delta_values(request)
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                WrongIdentityProvider(),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )

    def test_bootstrap_backend_constructs_nuisance_from_raw_rebuilt_scores(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)
        provider = _SyntheticBootstrapNuisanceProvider(_artifact_value(request.baseline))
        original_full, original_folds = _original_delta_values(request)
        plan, evidence = build_bootstrap_nuisance_plan(
            request,
            _artifact_value(request.baseline),
            sample,
            provider,
            original_delta_full=original_full,
            original_delta_folds=original_folds,
        )
        assert evidence is not None
        self.assertEqual(plan.full_covariates.shape, (sample.size, 2))
        np.testing.assert_array_equal(
            plan.full_covariates[:, 0],
            _artifact_value(request.baseline)[sample],
        )
        self.assertAlmostEqual(float(np.mean(plan.full_covariates[:, 1])), 0.0)
        self.assertAlmostEqual(float(np.std(plan.full_covariates[:, 1])), 1.0)

    def test_adjusted_bootstrap_requires_provider_before_publication(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backend = DirectVoxelFormalBackend(
                RunScopedArtifactPublisher(root, "formal_test", "1")
            )
            with self.assertRaisesRegex(FormalBackendInputError, "injected"):
                backend.run_formal(request)
            self.assertEqual(list(root.iterdir()), [])

    def test_adjusted_bootstrap_publishes_support_qc_for_every_replicate(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        provider = _SyntheticBootstrapNuisanceProvider(_artifact_value(request.baseline))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backend = DirectVoxelFormalBackend(
                RunScopedArtifactPublisher(root, "formal_test", "1"),
                artifact_store=_ScientificArrayStore(),
                bootstrap_nuisance_provider=provider,
            )
            result = backend.run_formal(request)
            self.assertEqual(len(provider.calls), 10)
            self.assertFalse(hasattr(result, "source_status"))
            evidence_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_bootstrap_nuisance_qc"
            )
            payload = json.loads(_artifact_path(evidence_ref).read_text(encoding="utf-8"))
            rows = payload["replicates"]
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[0]["support_status"], "adequate")
            self.assertEqual(rows[1]["support_status"], "limited")
            self.assertEqual(rows[0]["support_qc"]["replicate_token"], 0)
            self.assertAlmostEqual(
                rows[9]["support_qc"]["median_out_support_fraction"],
                0.19,
            )
            self.assertEqual(
                rows[0]["rebuild_provenance"]["rebuild_method"],
                "matched_reference_bootstrap_rebuild",
            )
            self.assertEqual(
                rows[0]["rebuild_provenance"]["final_model_id"],
                request.final_model.identifier,
            )
            self.assertEqual(
                len(rows[0]["rebuild_provenance"]["sample_indices_sha256"]),
                64,
            )

    def test_formal_publication_is_immutable_and_has_no_classification_feedback(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publisher = RunScopedArtifactPublisher(root, "formal_test", "1")
            backend = NormativeFiberFormalBackend(
                publisher,
                artifact_store=_ScientificArrayStore(),
            )
            first = backend.run_formal(request)
            second = backend.run_formal(request)
            self.assertEqual(
                tuple(artifact.sha256 for artifact in first.artifacts),
                tuple(artifact.sha256 for artifact in second.artifacts),
            )
            summary_ref = next(
                artifact
                for artifact in first.artifacts
                if artifact.kind == "formal_permutation_summary"
            )
            payload = json.loads(_artifact_path(summary_ref).read_text(encoding="utf-8"))
            forbidden = {
                "source_status",
                "prediction_status",
                "branch_role",
                "endpoint_status",
                "final_status",
            }
            self.assertTrue(forbidden.isdisjoint(payload))


class FrozenFormalSummaryTest(unittest.TestCase):
    def test_only_allowlisted_frozen_ten_thousand_resample_summaries_are_hashed(self) -> None:
        allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        formal_allowlist: dict[str, set[str]] = {}
        for scope in allowlist["scopes"]:
            for task in scope["tasks"]:
                if str(task["execution_stage"]).startswith("formal_"):
                    formal_allowlist[task["task_id"]] = set(task["reviewed_artifact_kinds"])
        self.assertEqual(set(formal_allowlist), FORMAL_TASK_IDS)
        self.assertTrue(
            all(
                kinds <= {"permutation_results", "bootstrap_results"}
                for kinds in formal_allowlist.values()
            )
        )

        manifest = json.loads(FROZEN_MANIFEST_PATH.read_text(encoding="utf-8"))
        frozen = {
            task["task_id"]: task
            for task in manifest["eligible_tasks"]
            if task["task_id"] in formal_allowlist
        }
        self.assertEqual(set(frozen), FORMAL_TASK_IDS)
        consumed: list[tuple[str, str]] = []
        for task_id in sorted(FORMAL_TASK_IDS):
            task = frozen[task_id]
            self.assertEqual(task["status"], "completed")
            artifacts = {
                artifact["kind"]: artifact
                for artifact in task["artifacts"]
                if artifact["kind"] in formal_allowlist[task_id]
            }
            self.assertEqual(set(artifacts), formal_allowlist[task_id])
            for kind in sorted(artifacts):
                artifact = artifacts[kind]
                path = Path(artifact["path"])
                if not path.is_file():
                    self.skipTest(f"frozen allowlisted summary is not mounted: {path}")
                self.assertEqual(sha256_file(path), artifact["sha256"])
                with path.open("r", encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 1)
                self.assertEqual(int(rows[0]["B"]), 10_000)
                consumed.append((task_id, kind))
        expected = sum(len(kinds) for kinds in formal_allowlist.values())
        self.assertEqual(len(consumed), expected)


if __name__ == "__main__":
    unittest.main()
