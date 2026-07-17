"""Contract and numerical tests for generic sensitivity strategies."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlparse

import numpy as np

from dual_frequency.backends.sensitivity import (
    AddonExposureSensitivityRequest,
    AddonExposureSensitivityStrategy,
    ClassificationFeedbackError,
    CollinearityInput,
    FinalFiberControlRequest,
    FinalFiberControlStrategy,
    FinalSensitivityTarget,
    JitterReplicateEvidence,
    ObservedFiberControlRequest,
    ObservedFiberControlStrategy,
    SensitivityStrategyError,
    SpatialJitterRequest,
    SpatialJitterSettings,
    SpatialJitterStrategy,
    SupportDiagnosticInput,
    TauNeighborhoodRequest,
    TauNeighborhoodStrategy,
    evaluate_fixed_cell,
    jitter_rebuild_identity,
    validate_no_classification_feedback,
)
from dual_frequency.backends.nuisance import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    build_gain_nuisance_plan,
)
from dual_frequency.backends.sensitivity.common import materialize_target_exposure
from dual_frequency.backends.sensitivity.fiber_controls import _plain_summaries
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BranchRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    ObservedRequest,
    ObservedResult,
    RequestError,
    SensitiveRecord,
    SourceGrid,
    SourceRecord,
)


def _document_artifact(kind: str = "diagnostic") -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        schema_version="1",
        uri=f"memory://fixture/{kind}.json",
        sha256="d" * 64,
        dtype=None,
        shape=None,
        axis_refs=(),
        axis_hashes=(),
        units=None,
        space=None,
        producer_id="sensitivity_test",
        producer_version="1",
    )


def _axis_artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="selected_feature_axis_fixture",
        schema_version="1",
        uri="memory://fixture/selected_feature_axis.npy",
        sha256="e" * 64,
        dtype="float64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="synthetic",
        producer_id="sensitivity_test",
        producer_version="1",
    )


_FIXTURE_ARRAYS: dict[str, np.ndarray] = {}


def _array_artifact(
    kind: str,
    values: np.ndarray,
    axes: tuple[AxisRef, ...],
    *,
    units: str | None = None,
    space: str | None = None,
) -> ArtifactRef:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    sha256 = digest.hexdigest()
    artifact = ArtifactRef(
        kind=kind,
        schema_version="1",
        uri=f"memory://fixture/{kind}_{sha256}.npy",
        sha256=sha256,
        dtype=array.dtype.name,
        shape=array.shape,
        axis_refs=axes,
        axis_hashes=tuple(axis.sha256 for axis in axes),
        units=units,
        space=space,
        producer_id="sensitivity_test",
        producer_version="1",
    )
    frozen = np.array(array, copy=True)
    frozen.flags.writeable = False
    _FIXTURE_ARRAYS[artifact.identifier] = frozen
    return artifact


def _fixture_array(artifact: ArtifactRef) -> np.ndarray:
    return _FIXTURE_ARRAYS[artifact.identifier]


def _feature_ids(axis: AxisRef) -> np.ndarray:
    return np.arange(10_000, 10_000 + axis.count, dtype=np.int64)


def _feature_ids_artifact(
    axis: AxisRef,
    values: np.ndarray | None = None,
) -> ArtifactRef:
    identifiers = np.ascontiguousarray(
        _feature_ids(axis) if values is None else values,
        dtype=np.int64,
    )
    digest = hashlib.sha256(identifiers.tobytes(order="C")).hexdigest()
    artifact = ArtifactRef(
        kind="normative_fiber_valid_union_ids",
        schema_version="1",
        uri=f"memory://fixture/fiber_ids_{digest}.npy",
        sha256=digest,
        dtype="int64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="fiber_id",
        space=None,
        producer_id="sensitivity_test",
        producer_version="1",
    )
    frozen = np.array(identifiers, copy=True)
    frozen.flags.writeable = False
    _FIXTURE_ARRAYS[artifact.identifier] = frozen
    return artifact


class FixtureArrayProvider:
    def materialize(
        self,
        artifact: ArtifactRef,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None = None,
    ) -> np.ndarray:
        self.assert_expected(
            artifact,
            expected_dtype=expected_dtype,
            expected_shape=expected_shape,
            expected_axes=expected_axes,
            expected_units=expected_units,
            expected_space=expected_space,
            mmap_mode=mmap_mode,
        )
        try:
            return _FIXTURE_ARRAYS[artifact.identifier]
        except KeyError as exc:
            raise AssertionError("fixture artifact was not registered") from exc

    @staticmethod
    def assert_expected(
        artifact: ArtifactRef,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
        expected_axes: tuple[AxisRef, ...],
        expected_units: str | None,
        expected_space: str | None,
        mmap_mode: str | None,
    ) -> None:
        if artifact.dtype != expected_dtype:
            raise AssertionError("fixture dtype mismatch")
        if artifact.shape != expected_shape or artifact.axis_refs != expected_axes:
            raise AssertionError("fixture shape or axis mismatch")
        if artifact.units != expected_units or artifact.space != expected_space:
            raise AssertionError("fixture unit or space mismatch")
        if mmap_mode != "r":
            raise AssertionError("fixture arrays must be materialized read-only")


_ARRAY_PROVIDER = FixtureArrayProvider()


def _arrays(n_subjects: int, n_features: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    latent = np.linspace(-1.5, 1.5, n_subjects)
    baseline = 18.0 + np.sin(np.arange(n_subjects) * 1.7)
    loading = np.linspace(0.8, 1.2, n_features)
    subject = np.arange(n_subjects, dtype=np.float64)[:, None]
    feature = np.arange(n_features, dtype=np.float64)[None, :]
    exposure = (
        230.0
        + 28.0 * latent[:, None] * loading[None, :]
        + 0.25 * np.sin((subject + 1.0) * (feature + 1.0))
    )
    # Every feature remains in cohort support, but this subject is below tau.
    exposure[0] = 100.0 + np.arange(n_features, dtype=np.float64)
    outcome = 42.0 - 8.0 * latent + 0.3 * baseline
    return exposure, outcome, baseline


def _endpoint(family: str) -> EndpointKey:
    return EndpointKey(
        "synthetic_study",
        "scale_a",
        "pair_a",
        family,
        "connectome_formal" if family.endswith("fiber") else "none",
    )


def _source(endpoint: EndpointKey, axis: AxisRef, *, tau: float = 200.0) -> SourceRecord:
    artifacts = [_axis_artifact(axis)]
    if endpoint.model_family.endswith("fiber"):
        artifacts.append(_feature_ids_artifact(axis))
    return SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=tau,
        selected_coverage=3,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(axis, "synthetic_exact_final_axis"),
        artifacts=tuple(artifacts),
    )


def _final(
    endpoint: EndpointKey,
    axis: AxisRef,
    *,
    branch: str = "reference",
) -> FinalModelRecord:
    source = _source(endpoint, axis)
    final_key = FinalModelKey(
        endpoint.identifier,
        branch,
        200.0,
        3,
        "partial_spearman",
    )
    if endpoint.model_family.startswith("reference_"):
        return FinalModelRecord(
            endpoint=endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=final_key,
            selected_source=source,
            selected_branch=None,
            artifacts=(_axis_artifact(axis),),
        )
    branch_record = BranchRecord(
        endpoint=endpoint,
        branch=branch,
        intended_role="primary",
        input_status="valid",
        nuisance_design_status="valid",
        source=source,
        artifacts=(_axis_artifact(axis),),
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=final_key,
        selected_source=None,
        selected_branch=branch_record,
        artifacts=(_axis_artifact(axis),),
    )


def _observed(
    family: str,
    *,
    branch: str = "reference",
    axis: AxisRef | None = None,
    nuisance_inputs: tuple[np.ndarray | ArtifactRef, ...] = (),
    exposure: np.ndarray | None = None,
    outcome: np.ndarray | None = None,
    baseline: np.ndarray | None = None,
    outcome_kind: str = "clinical_outcome",
) -> ObservedRequest:
    if exposure is None or outcome is None or baseline is None:
        default_exposure, default_outcome, default_baseline = _arrays(12, 8)
        exposure = default_exposure if exposure is None else exposure
        outcome = default_outcome if outcome is None else outcome
        baseline = default_baseline if baseline is None else baseline
    subjects = AxisRef("subjects", exposure.shape[0], "a" * 64)
    features = axis or AxisRef(
        f"features:{family}",
        exposure.shape[1],
        "b" * 64,
    )
    fiber = family.endswith("fiber")
    exposure_artifact = _array_artifact(
        "observed_exposure",
        np.asarray(exposure, dtype=np.float64),
        (subjects, features),
        units="V/m",
        space="synthetic",
    )
    outcome_artifact = _array_artifact(
        outcome_kind,
        np.asarray(outcome, dtype=np.float64),
        (subjects,),
        units="score",
    )
    baseline_artifact = _array_artifact(
        "clinical_baseline",
        np.asarray(baseline, dtype=np.float64),
        (subjects,),
        units="score",
    )
    nuisance_artifacts: list[ArtifactRef] = []
    for index, value in enumerate(nuisance_inputs):
        if isinstance(value, ArtifactRef):
            nuisance_artifacts.append(value)
            continue
        array = np.asarray(value, dtype=np.float64)
        nuisance_artifacts.append(
            _array_artifact(
                f"nuisance_{index}",
                array,
                (subjects,) * array.ndim,
                units="score",
            )
        )
    return ObservedRequest(
        endpoint=_endpoint(family),
        branch=branch,
        exposure=exposure_artifact,
        outcome=outcome_artifact,
        baseline=baseline_artifact,
        nuisance_inputs=tuple(nuisance_artifacts),
        subject_axis=subjects,
        feature_axis=features,
        source_grid=SourceGrid(
            200.0,
            3,
            (180.0, 200.0, 220.0),
            (3, 4),
            1,
        ),
        exposure_units="V/m",
        exposure_space="synthetic",
        outcome_direction="lower",
        hard_computability=HardComputabilityLimits(
            8,
            None if fiber else 1,
            1,
        ),
        connectome_role="formal" if fiber else "none",
        feature_ids=_feature_ids_artifact(features) if fiber else None,
        fiber_score_settings=(
            NormativeFiberScoreSettings(
                sweet_fraction=0.25,
                sour_fraction=0.25,
                weighted_peak_fraction=0.25,
                sweet_selected_min_count=2,
                sour_selected_min_count=1,
                weighted_peak_min_count=1,
            )
            if fiber
            else None
        ),
    )


def _target(
    family: str,
    *,
    branch: str = "reference",
    nuisance_inputs: tuple[np.ndarray | ArtifactRef, ...] = (),
) -> FinalSensitivityTarget:
    observed = _observed(
        family,
        branch=branch,
        nuisance_inputs=nuisance_inputs,
    )
    return FinalSensitivityTarget(
        final_model=_final(observed.endpoint, observed.feature_axis, branch=branch),
        observed_request=observed,
    )


def _gain_request(observed: ObservedRequest) -> ObservedRequest:
    return replace(
        observed,
        outcome=_array_artifact(
            "direction_normalized_addon_gain",
            _fixture_array(observed.outcome),
            (observed.subject_axis,),
            units="score",
        ),
        outcome_direction="higher",
    )


def _total_exposure_request(observed: ObservedRequest) -> ObservedRequest:
    return replace(
        observed,
        exposure=_array_artifact(
            "raw_addon_component_exposure",
            _fixture_array(observed.exposure),
            (observed.subject_axis, observed.feature_axis),
            units=observed.exposure.units,
            space=observed.exposure.space,
        ),
    )


def _json_artifact(result) -> ArtifactRef:
    matches = [artifact for artifact in result.artifacts if artifact.shape is None]
    if len(matches) != 1:
        raise AssertionError("expected exactly one JSON artifact")
    return matches[0]


def _read_json(artifact: ArtifactRef) -> dict[str, object]:
    path = Path(unquote(urlparse(artifact.uri).path))
    return json.loads(path.read_text(encoding="utf-8"))


class FinalOnlyContractTest(unittest.TestCase):
    def test_final_linked_inputs_reject_mutable_arrays(self) -> None:
        observed = _observed("reference_voxel")
        final = _final(observed.endpoint, observed.feature_axis)
        mutable_values = {
            "exposure": _fixture_array(observed.exposure).copy(),
            "outcome": _fixture_array(observed.outcome).copy(),
            "baseline": _fixture_array(observed.baseline).copy(),
        }
        for field, value in mutable_values.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    SensitivityStrategyError,
                    "immutable ArtifactRef",
                ):
                    FinalSensitivityTarget(final, replace(observed, **{field: value}))

        delta = np.linspace(-1.0, 1.0, observed.subject_axis.count)
        adjusted = _observed(
            "addon_voxel",
            branch="delta_reference_adjusted",
            nuisance_inputs=(delta, np.tile(delta, (delta.size, 1))),
        )
        adjusted_final = _final(
            adjusted.endpoint,
            adjusted.feature_axis,
            branch="delta_reference_adjusted",
        )
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "nuisance_inputs.*ArtifactRef",
        ):
            FinalSensitivityTarget(
                adjusted_final,
                replace(
                    adjusted,
                    nuisance_inputs=(
                        delta,
                        adjusted.nuisance_inputs[1],
                    ),
                ),
            )

        addon = _target("addon_voxel", branch="no_delta_reference")
        overlap = np.zeros(
            (
                addon.observed_request.subject_axis.count,
                addon.observed_request.feature_axis.count,
            ),
            dtype=bool,
        )
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "reference_overlap_mask.*ArtifactRef",
        ):
            FinalSensitivityTarget(
                addon.final_model,
                addon.observed_request,
                reference_overlap_mask=overlap,
            )

    def test_rejects_nonfinal_sensitive_and_mismatched_axis(self) -> None:
        observed = _observed("reference_voxel")
        source = _source(observed.endpoint, observed.feature_axis)
        with self.assertRaisesRegex(SensitivityStrategyError, "FinalModelRecord"):
            FinalSensitivityTarget(source, observed)  # type: ignore[arg-type]

        sensitive_endpoint = EndpointKey(
            "synthetic_study",
            "scale_a",
            "pair_a",
            "reference_fiber",
            "connectome_sensitive",
        )
        sensitive_axis = AxisRef("sensitive", 8, "c" * 64)
        sensitive = SensitiveRecord(
            endpoint=sensitive_endpoint,
            formal_endpoint_id="endpoint_formal",
            evaluated_tau=200.0,
            evaluated_coverage=3,
            input_status="valid",
            cell_computability_status="computable",
            prediction_status="error_nonpredictive",
            feature_axis=FeatureAxisRef(sensitive_axis, "sensitive_fixture"),
            artifacts=(_axis_artifact(sensitive_axis),),
        )
        with self.assertRaisesRegex(SensitivityStrategyError, "FinalModelRecord"):
            FinalSensitivityTarget(sensitive, observed)  # type: ignore[arg-type]

        final = _final(observed.endpoint, observed.feature_axis)
        wrong_axis = AxisRef("wrong", observed.feature_axis.count, "f" * 64)
        mismatched = _observed("reference_voxel", axis=wrong_axis)
        with self.assertRaisesRegex(SensitivityStrategyError, "valid_feature_axis"):
            FinalSensitivityTarget(final, mismatched)

    def test_rejects_nonrealized_and_missing_final_axis(self) -> None:
        target = _target("reference_voxel")
        nonrealized = object.__new__(FinalModelRecord)
        nonrealized.__dict__.update(target.final_model.__dict__)
        object.__setattr__(nonrealized, "final_status", "no_final_model")
        with self.assertRaisesRegex(SensitivityStrategyError, "realized"):
            FinalSensitivityTarget(nonrealized, target.observed_request)

        source = target.final_model.selected_source
        self.assertIsNotNone(source)
        broken_source = object.__new__(SourceRecord)
        broken_source.__dict__.update(source.__dict__)  # type: ignore[union-attr]
        object.__setattr__(broken_source, "feature_axis", None)
        broken = object.__new__(FinalModelRecord)
        broken.__dict__.update(target.final_model.__dict__)
        object.__setattr__(broken, "selected_source", broken_source)
        with self.assertRaisesRegex(SensitivityStrategyError, "exact valid feature axis"):
            FinalSensitivityTarget(broken, target.observed_request)

    def test_rejects_sensitive_connectome_role(self) -> None:
        observed = _observed("reference_fiber")
        sensitive_request = replace(observed, connectome_role="sensitive")
        final = _final(observed.endpoint, observed.feature_axis)
        with self.assertRaisesRegex(SensitivityStrategyError, "formal connectome"):
            FinalSensitivityTarget(final, sensitive_request)

    def test_fiber_target_requires_exact_selected_source_id_artifact(self) -> None:
        observed = _observed("reference_fiber")
        final = _final(observed.endpoint, observed.feature_axis)
        reordered = _feature_ids_artifact(
            observed.feature_axis,
            _feature_ids(observed.feature_axis)[::-1],
        )
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "selected final source ID artifact",
        ):
            FinalSensitivityTarget(final, replace(observed, feature_ids=reordered))

        source = final.selected_source
        self.assertIsNotNone(source)
        missing_ids = replace(source, artifacts=(_axis_artifact(observed.feature_axis),))
        final_without_ids = replace(final, selected_source=missing_ids)
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "exactly one normative_fiber_valid_union_ids",
        ):
            FinalSensitivityTarget(final_without_ids, observed)


class ContinuousDoseTest(unittest.TestCase):
    def test_direct_and_fiber_scores_keep_below_tau_values(self) -> None:
        for family in ("reference_voxel", "reference_fiber"):
            with self.subTest(family=family):
                target = _target(family)
                exposure = _fixture_array(target.observed_request.exposure)
                self.assertTrue(np.all(exposure[0] < 200.0))
                evidence = evaluate_fixed_cell(
                    target,
                    tau=200.0,
                    coverage=3,
                    array_provider=_ARRAY_PROVIDER,
                )
                self.assertEqual(evidence.technical_status, "complete")
                self.assertIsNotNone(evidence.full_scores)
                self.assertGreater(abs(float(evidence.full_scores[0])), 1e-8)

    def test_direct_support_includes_exact_tau(self) -> None:
        exposure = np.zeros((12, 2), dtype=np.float64)
        exposure[:3, 0] = 200.0
        exposure[:, 1] = np.linspace(220.0, 260.0, 12)
        baseline = 20.0 + np.sin(np.arange(12))
        outcome = 40.0 - np.linspace(-3.0, 3.0, 12) + 0.2 * baseline
        observed = _observed(
            "reference_voxel",
            exposure=exposure,
            outcome=outcome,
            baseline=baseline,
        )
        target = FinalSensitivityTarget(
            _final(observed.endpoint, observed.feature_axis),
            observed,
        )
        evidence = evaluate_fixed_cell(
            target,
            tau=200.0,
            coverage=3,
            array_provider=_ARRAY_PROVIDER,
        )
        self.assertEqual(evidence.metrics["n_features_full"], 2)

    def test_fiber_support_includes_exact_tau(self) -> None:
        exposure = np.zeros((12, 2), dtype=np.float64)
        exposure[:3, 0] = 200.0
        exposure[:, 1] = np.linspace(220.0, 260.0, 12)
        baseline = 20.0 + np.sin(np.arange(12))
        outcome = 40.0 - np.linspace(-3.0, 3.0, 12) + 0.2 * baseline
        observed = _observed(
            "reference_fiber",
            exposure=exposure,
            outcome=outcome,
            baseline=baseline,
        )
        target = FinalSensitivityTarget(
            _final(observed.endpoint, observed.feature_axis),
            observed,
        )
        evidence = evaluate_fixed_cell(
            target,
            tau=200.0,
            coverage=3,
            array_provider=_ARRAY_PROVIDER,
        )
        self.assertEqual(evidence.metrics["n_candidate_full"], 2)

    def test_tau_neighborhood_uses_absolute_0p9_and_1p1_values(self) -> None:
        target = _target("reference_voxel")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = TauNeighborhoodStrategy(
                RunScopedArtifactPublisher(root, "tau_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            ).run(TauNeighborhoodRequest(target))
            payload = _read_json(_json_artifact(result))
            self.assertEqual(payload["tau_multipliers"], [0.9, 1.1])
            self.assertEqual(
                [cell["tau"] for cell in payload["cells"]],
                [180.0, 220.00000000000003],
            )
            score_refs = [artifact for artifact in result.artifacts if artifact.shape]
            self.assertEqual(len(score_refs), 2)
            store = ArtifactStore([root])
            lower = store.materialize(
                score_refs[0],
                expected_dtype=score_refs[0].dtype,
                expected_shape=score_refs[0].shape,
                expected_axes=score_refs[0].axis_refs,
                expected_units="V/m",
                expected_space=None,
            )
            self.assertGreater(abs(float(lower[0])), 1e-8)


class DeterministicProvider:
    def __init__(self) -> None:
        self.seeds: list[int] = []

    def build_replicate(
        self,
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence:
        self.seeds.append(replicate_seed)
        rng = np.random.default_rng(replicate_seed)
        exposure = _fixture_array(target.observed_request.exposure)
        perturbed = exposure + rng.normal(0.0, 0.01, size=exposure.shape)
        observed = replace(
            target.observed_request,
            exposure=_array_artifact(
                "jittered_exposure",
                perturbed,
                (
                    target.observed_request.subject_axis,
                    target.observed_request.feature_axis,
                ),
                units="V/m",
                space="synthetic",
            ),
        )
        return JitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
            ),
        )


class SpatialJitterTest(unittest.TestCase):
    def test_settings_convert_fwhm_to_gaussian_sigma(self) -> None:
        settings = SpatialJitterSettings(2, 7, 2.354820045)
        self.assertAlmostEqual(settings.translation_sigma_mm, 1.0)

    def test_injected_provider_and_aggregation_are_deterministic(self) -> None:
        target = _target("reference_voxel")
        payloads = []
        seed_sequences = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label in ("first", "second"):
                provider = DeterministicProvider()
                result = SpatialJitterStrategy(
                    RunScopedArtifactPublisher(root / label, "jitter_test", "1"),
                    array_provider=_ARRAY_PROVIDER,
                ).run(
                    SpatialJitterRequest(
                        target,
                        SpatialJitterSettings(
                            replicates=5,
                            seed=20260715,
                            translation_fwhm_mm=2.0,
                        ),
                        provider,
                    )
                )
                payloads.append(_read_json(_json_artifact(result)))
                seed_sequences.append(provider.seeds)
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(seed_sequences[0], seed_sequences[1])
        self.assertEqual(len(set(seed_sequences[0])), 5)
        self.assertEqual(payloads[0]["requested_replicates"], 5)

    def test_provider_axis_contract_violation_is_rejected(self) -> None:
        class WrongAxisProvider(DeterministicProvider):
            def build_replicate(self, target, *, replicate_index, replicate_seed):
                evidence = super().build_replicate(
                    target,
                    replicate_index=replicate_index,
                    replicate_seed=replicate_seed,
                )
                observed = evidence.observed_request
                axis = AxisRef(
                    "wrong-jitter-axis",
                    observed.feature_axis.count,
                    "9" * 64,
                )
                return replace(
                    evidence,
                    observed_request=_observed(
                        "reference_voxel",
                        axis=axis,
                        exposure=_fixture_array(observed.exposure),
                        outcome=_fixture_array(observed.outcome),
                        baseline=_fixture_array(observed.baseline),
                    ),
                )

        target = _target("reference_voxel")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(SensitivityStrategyError, "feature axis"):
                SpatialJitterStrategy(
                    RunScopedArtifactPublisher(Path(temporary), "jitter_test", "1"),
                    array_provider=_ARRAY_PROVIDER,
                ).run(
                    SpatialJitterRequest(
                        target,
                        SpatialJitterSettings(1, 1, 2.0),
                        WrongAxisProvider(),
                    )
                )

    def test_fiber_jitter_rejects_changed_ordered_id_identity(self) -> None:
        class ReorderedFiberProvider(DeterministicProvider):
            def build_replicate(self, target, *, replicate_index, replicate_seed):
                evidence = super().build_replicate(
                    target,
                    replicate_index=replicate_index,
                    replicate_seed=replicate_seed,
                )
                axis = evidence.observed_request.feature_axis
                reordered = _feature_ids_artifact(axis, _feature_ids(axis)[::-1])
                return replace(
                    evidence,
                    observed_request=replace(
                        evidence.observed_request,
                        feature_ids=reordered,
                    ),
                )

        target = _target("reference_fiber")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                SensitivityStrategyError,
                "ordered feature-ID identity",
            ):
                SpatialJitterStrategy(
                    RunScopedArtifactPublisher(Path(temporary), "jitter_test", "1"),
                    array_provider=_ARRAY_PROVIDER,
                ).run(
                    SpatialJitterRequest(
                        target,
                        SpatialJitterSettings(1, 3, 2.0),
                        ReorderedFiberProvider(),
                    )
                )


class AddonSpatialJitterEvidenceTest(unittest.TestCase):
    @staticmethod
    def _adjusted_target() -> FinalSensitivityTarget:
        exposure, outcome, baseline = _arrays(12, 8)
        delta_full = np.linspace(-1.0, 1.0, 12)
        delta_folds = np.vstack(
            [delta_full + 0.01 * heldout for heldout in range(12)]
        )
        observed = _observed(
            "addon_voxel",
            branch="delta_reference_adjusted",
            nuisance_inputs=(delta_full, delta_folds),
            exposure=exposure,
            outcome=outcome,
            baseline=baseline,
        )
        overlap = _array_artifact(
            "reference_overlap_mask",
            np.zeros_like(exposure, dtype=bool),
            (observed.subject_axis, observed.feature_axis),
            units="mask",
            space="synthetic",
        )
        return FinalSensitivityTarget(
            _final(
                observed.endpoint,
                observed.feature_axis,
                branch="delta_reference_adjusted",
            ),
            observed,
            reference_overlap_mask=overlap,
        )

    @staticmethod
    def _valid_evidence(
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence:
        original = target.observed_request
        exposure = _array_artifact(
            "jittered_exposure",
            _fixture_array(original.exposure) + 0.1,
            (original.subject_axis, original.feature_axis),
            units="V/m",
            space="synthetic",
        )
        overlap_values = np.array(
            _fixture_array(target.reference_overlap_mask),
            copy=True,
        )
        overlap_values[0, 0] = ~overlap_values[0, 0]
        overlap = _array_artifact(
            "jittered_reference_overlap_mask",
            overlap_values,
            (original.subject_axis, original.feature_axis),
            units="mask",
            space="synthetic",
        )
        delta_full, delta_folds = original.nuisance_inputs
        rebuilt_delta = (
            _array_artifact(
                "jittered_delta_reference_full",
                _fixture_array(delta_full) + 0.01,
                (original.subject_axis,),
                units="score",
            ),
            _array_artifact(
                "jittered_delta_reference_folds",
                _fixture_array(delta_folds) + 0.01,
                (original.subject_axis, original.subject_axis),
                units="score",
            ),
        )
        observed = replace(
            original,
            exposure=exposure,
            nuisance_inputs=rebuilt_delta,
        )
        support_qc = (("median_out_support_fraction", 0.1),)
        return JitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap,
                support_status="adequate",
                support_qc=support_qc,
            ),
            reference_overlap_mask=overlap,
            support_status="adequate",
            support_qc=support_qc,
            delta_rebuild_identity=jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap,
                support_status="adequate",
                support_qc=support_qc,
                component="delta_reference",
            ),
        )

    @staticmethod
    def _rebind_evidence(
        target: FinalSensitivityTarget,
        evidence: JitterReplicateEvidence,
    ) -> JitterReplicateEvidence:
        rebuild = jitter_rebuild_identity(
            target,
            observed_request=evidence.observed_request,
            replicate_index=evidence.replicate_index,
            replicate_seed=evidence.replicate_seed,
            reference_overlap_mask=evidence.reference_overlap_mask,
            support_status=evidence.support_status,
            support_qc=evidence.support_qc,
        )
        delta = jitter_rebuild_identity(
            target,
            observed_request=evidence.observed_request,
            replicate_index=evidence.replicate_index,
            replicate_seed=evidence.replicate_seed,
            reference_overlap_mask=evidence.reference_overlap_mask,
            support_status=evidence.support_status,
            support_qc=evidence.support_qc,
            component="delta_reference",
        )
        return replace(
            evidence,
            rebuild_identity=rebuild,
            delta_rebuild_identity=delta,
        )

    def _assert_provider_rejected(self, evidence, pattern: str) -> None:
        class Provider:
            def build_replicate(self, target, *, replicate_index, replicate_seed):
                return evidence(target, replicate_index, replicate_seed)

        target = self._adjusted_target()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(SensitivityStrategyError, pattern):
                SpatialJitterStrategy(
                    RunScopedArtifactPublisher(Path(temporary), "jitter_test", "1"),
                    array_provider=_ARRAY_PROVIDER,
                ).run(
                    SpatialJitterRequest(
                        target,
                        SpatialJitterSettings(1, 4, 2.0),
                        Provider(),
                    )
                )

    def test_adjusted_jitter_accepts_fully_rebuilt_artifacts(self) -> None:
        class Provider:
            def build_replicate(inner_self, target, *, replicate_index, replicate_seed):
                return self._valid_evidence(
                    target,
                    replicate_index=replicate_index,
                    replicate_seed=replicate_seed,
                )

        target = self._adjusted_target()
        with tempfile.TemporaryDirectory() as temporary:
            result = SpatialJitterStrategy(
                RunScopedArtifactPublisher(Path(temporary), "jitter_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            ).run(
                SpatialJitterRequest(
                    target,
                    SpatialJitterSettings(1, 4, 2.0),
                    Provider(),
                )
            )
        self.assertEqual(result.sensitivity_kind, "spatial_jitter")

    def test_rejects_reused_exposure_overlap_and_delta_artifacts(self) -> None:
        mutations = {
            "exposure": (
                lambda target, evidence: replace(
                    evidence,
                    observed_request=replace(
                        evidence.observed_request,
                        exposure=target.observed_request.exposure,
                    ),
                ),
                "original exposure artifact",
            ),
            "overlap": (
                lambda target, evidence: replace(
                    evidence,
                    reference_overlap_mask=target.reference_overlap_mask,
                ),
                "original reference-overlap mask",
            ),
            "delta_full": (
                lambda target, evidence: replace(
                    evidence,
                    observed_request=replace(
                        evidence.observed_request,
                        nuisance_inputs=(
                            target.observed_request.nuisance_inputs[0],
                            evidence.observed_request.nuisance_inputs[1],
                        ),
                    ),
                ),
                "original DeltaReferenceScore",
            ),
            "delta_folds": (
                lambda target, evidence: replace(
                    evidence,
                    observed_request=replace(
                        evidence.observed_request,
                        nuisance_inputs=(
                            evidence.observed_request.nuisance_inputs[0],
                            target.observed_request.nuisance_inputs[1],
                        ),
                    ),
                ),
                "original DeltaReferenceScore",
            ),
        }
        for label, (mutate, pattern) in mutations.items():
            with self.subTest(label=label):
                def evidence(target, index, seed, mutate=mutate):
                    valid = self._valid_evidence(
                        target,
                        replicate_index=index,
                        replicate_seed=seed,
                    )
                    return self._rebind_evidence(target, mutate(target, valid))

                self._assert_provider_rejected(evidence, pattern)

    def test_rejects_same_content_stale_artifacts_under_new_uris(self) -> None:
        def copied(artifact: ArtifactRef, label: str) -> ArtifactRef:
            duplicate = replace(
                artifact,
                uri=f"memory://fixture/copied_stale_{label}.npy",
            )
            _FIXTURE_ARRAYS[duplicate.identifier] = _fixture_array(artifact)
            return duplicate

        mutations = {
            "exposure": (
                lambda target, valid: replace(
                    valid,
                    observed_request=replace(
                        valid.observed_request,
                        exposure=copied(
                            target.observed_request.exposure,
                            "exposure",
                        ),
                    ),
                ),
                "original exposure artifact",
            ),
            "overlap": (
                lambda target, valid: replace(
                    valid,
                    reference_overlap_mask=copied(
                        target.reference_overlap_mask,
                        "overlap",
                    ),
                ),
                "original reference-overlap mask",
            ),
            "delta_full": (
                lambda target, valid: replace(
                    valid,
                    observed_request=replace(
                        valid.observed_request,
                        nuisance_inputs=(
                            copied(
                                target.observed_request.nuisance_inputs[0],
                                "delta_full",
                            ),
                            valid.observed_request.nuisance_inputs[1],
                        ),
                    ),
                ),
                "original DeltaReferenceScore",
            ),
            "delta_folds": (
                lambda target, valid: replace(
                    valid,
                    observed_request=replace(
                        valid.observed_request,
                        nuisance_inputs=(
                            valid.observed_request.nuisance_inputs[0],
                            copied(
                                target.observed_request.nuisance_inputs[1],
                                "delta_folds",
                            ),
                        ),
                    ),
                ),
                "original DeltaReferenceScore",
            ),
        }
        for label, (mutate, pattern) in mutations.items():
            with self.subTest(label=label):
                def evidence(target, index, seed, mutate=mutate):
                    valid = self._valid_evidence(
                        target,
                        replicate_index=index,
                        replicate_seed=seed,
                    )
                    return self._rebind_evidence(target, mutate(target, valid))

                self._assert_provider_rejected(evidence, pattern)

    def test_rejects_changed_clinical_and_configuration_fields(self) -> None:
        mutations = {
            "outcome": lambda target, observed: replace(
                observed,
                outcome=_array_artifact(
                    "clinical_outcome",
                    _fixture_array(observed.outcome) + 1.0,
                    (observed.subject_axis,),
                    units="score",
                ),
            ),
            "baseline": lambda target, observed: replace(
                observed,
                baseline=_array_artifact(
                    "clinical_baseline",
                    _fixture_array(observed.baseline) + 1.0,
                    (observed.subject_axis,),
                    units="score",
                ),
            ),
            "config": lambda target, observed: replace(
                observed,
                outcome_direction="higher",
            ),
            "source_grid": lambda target, observed: replace(
                observed,
                source_grid=SourceGrid(
                    180.0,
                    3,
                    (180.0, 200.0, 220.0),
                    (3, 4),
                    1,
                ),
            ),
            "hard_computability": lambda target, observed: replace(
                observed,
                hard_computability=HardComputabilityLimits(9, 1, 1),
            ),
            "endpoint": lambda target, observed: replace(
                observed,
                endpoint=EndpointKey(
                    "synthetic_study",
                    "scale_b",
                    "pair_a",
                    "addon_voxel",
                    "none",
                ),
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                def evidence(target, index, seed, mutate=mutate):
                    valid = self._valid_evidence(
                        target,
                        replicate_index=index,
                        replicate_seed=seed,
                    )
                    changed = replace(
                        valid,
                        observed_request=mutate(target, valid.observed_request),
                    )
                    return self._rebind_evidence(target, changed)

                self._assert_provider_rejected(evidence, "jitter cannot change")

    def test_support_qc_rejects_nonfinite_and_non_json_scalars(self) -> None:
        target = self._adjusted_target()
        valid = self._valid_evidence(
            target,
            replicate_index=0,
            replicate_seed=1,
        )
        for value in (math.nan, math.inf, [0.1]):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    SensitivityStrategyError,
                    "support_qc",
                ):
                    replace(valid, support_qc=(("invalid", value),))

    def test_provider_subject_axis_contract_violation_is_rejected(self) -> None:
        class WrongSubjectProvider(DeterministicProvider):
            def build_replicate(self, target, *, replicate_index, replicate_seed):
                evidence = super().build_replicate(
                    target,
                    replicate_index=replicate_index,
                    replicate_seed=replicate_seed,
                )
                wrong_subjects = AxisRef(
                    "wrong-subject-order",
                    evidence.observed_request.subject_axis.count,
                    "8" * 64,
                )
                malformed = object.__new__(ObservedRequest)
                malformed.__dict__.update(evidence.observed_request.__dict__)
                object.__setattr__(malformed, "subject_axis", wrong_subjects)
                return replace(
                    evidence,
                    observed_request=malformed,
                )

        target = _target("reference_voxel")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(SensitivityStrategyError, "subject axis"):
                SpatialJitterStrategy(
                    RunScopedArtifactPublisher(Path(temporary), "jitter_test", "1"),
                    array_provider=_ARRAY_PROVIDER,
                ).run(
                    SpatialJitterRequest(
                        target,
                        SpatialJitterSettings(1, 2, 2.0),
                        WrongSubjectProvider(),
                    )
                )


class AddonIndependenceTest(unittest.TestCase):
    def test_gain_nuisance_is_intercept_only_or_delta_only(self) -> None:
        no_delta = build_gain_nuisance_plan(12, NO_DELTA_BRANCH)
        self.assertEqual(no_delta.full_covariates.shape, (12, 0))
        self.assertEqual(no_delta.fold_covariates.shape, (12, 12, 0))

        delta_full = np.linspace(-2.0, 2.0, 12)
        delta_folds = np.vstack(
            [delta_full + 0.05 * heldout for heldout in range(12)]
        )
        adjusted = build_gain_nuisance_plan(
            12,
            ADJUSTED_BRANCH,
            delta_full_scores=delta_full,
            delta_fold_scores=delta_folds,
        )
        self.assertEqual(adjusted.full_covariates.shape, (12, 1))
        self.assertEqual(adjusted.fold_covariates.shape, (12, 12, 1))
        for heldout in range(12):
            training = np.delete(np.arange(12), heldout)
            self.assertAlmostEqual(
                float(np.mean(adjusted.fold_covariates[heldout, training, 0])),
                0.0,
                places=12,
            )
            self.assertAlmostEqual(
                float(np.std(adjusted.fold_covariates[heldout, training, 0])),
                1.0,
                places=12,
            )

    def test_nonfinal_and_gain_apply_overlap_but_total_exposure_does_not(self) -> None:
        exposure, outcome, baseline = _arrays(12, 2)
        exposure[:, 0] = 250.0 + np.linspace(-5.0, 5.0, 12)
        exposure[:, 1] = 240.0 + np.linspace(5.0, -5.0, 12)
        observed = _observed(
            "addon_voxel",
            branch="no_delta_reference",
            exposure=exposure,
            outcome=outcome,
            baseline=baseline,
        )
        overlap_values = np.zeros_like(exposure, dtype=bool)
        overlap_values[:, 0] = True
        overlap = _array_artifact(
            "reference_overlap_mask",
            overlap_values,
            (observed.subject_axis, observed.feature_axis),
            units="mask",
            space="synthetic",
        )
        target = FinalSensitivityTarget(
            _final(
                observed.endpoint,
                observed.feature_axis,
                branch="no_delta_reference",
            ),
            observed,
            reference_overlap_mask=overlap,
        )
        delta_full = np.linspace(-1.0, 1.0, 12)
        delta_folds = np.vstack(
            [delta_full + 0.01 * heldout for heldout in range(12)]
        )
        nonfinal = replace(
            observed,
            branch="delta_reference_adjusted",
            nuisance_inputs=(
                _array_artifact(
                    "delta_reference_full",
                    delta_full,
                    (observed.subject_axis,),
                    units="score",
                ),
                _array_artifact(
                    "delta_reference_folds",
                    delta_folds,
                    (observed.subject_axis, observed.subject_axis),
                    units="score",
                ),
            ),
        )
        request = AddonExposureSensitivityRequest(
            target=target,
            nonfinal_request=nonfinal,
            gain_request=_gain_request(observed),
            total_exposure_request=_total_exposure_request(observed),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = AddonExposureSensitivityStrategy(
                RunScopedArtifactPublisher(Path(temporary), "addon_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            ).run(request)
            payload = _read_json(_json_artifact(result))
        analyses = payload["analyses"]
        self.assertEqual(
            analyses["nonfinal_branch"]["metrics"]["n_features_full"],
            1,
        )
        self.assertEqual(analyses["gain"]["metrics"]["n_features_full"], 1)
        self.assertEqual(
            analyses["total_exposure"]["metrics"]["n_features_full"],
            2,
        )

    def test_all_alternative_requests_reject_raw_scientific_inputs(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        observed = target.observed_request
        delta = np.linspace(-1.0, 1.0, observed.subject_axis.count)
        nonfinal = replace(
            observed,
            branch="delta_reference_adjusted",
            exposure=_fixture_array(observed.exposure).copy(),
            nuisance_inputs=(
                _array_artifact(
                    "delta_reference_full",
                    delta,
                    (observed.subject_axis,),
                    units="score",
                ),
                _array_artifact(
                    "delta_reference_folds",
                    np.tile(delta, (delta.size, 1)),
                    (observed.subject_axis, observed.subject_axis),
                    units="score",
                ),
            ),
        )
        gain = replace(
            _gain_request(observed),
            outcome=_fixture_array(observed.outcome).copy(),
        )
        total = replace(
            observed,
            baseline=_fixture_array(observed.baseline).copy(),
        )
        requests = (
            {"nonfinal_request": nonfinal},
            {"gain_request": gain},
            {"total_exposure_request": total},
        )
        for fields in requests:
            with self.subTest(field=next(iter(fields))):
                with self.assertRaisesRegex(
                    SensitivityStrategyError,
                    "immutable ArtifactRef",
                ):
                    AddonExposureSensitivityRequest(target=target, **fields)

    def test_alternative_request_rejects_subject_axis_drift(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        wrong_subjects = AxisRef(
            "wrong-addon-subject-order",
            target.observed_request.subject_axis.count,
            "7" * 64,
        )
        malformed = object.__new__(ObservedRequest)
        malformed.__dict__.update(_gain_request(target.observed_request).__dict__)
        object.__setattr__(malformed, "subject_axis", wrong_subjects)
        with self.assertRaisesRegex(SensitivityStrategyError, "artifact axes"):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=malformed,
            )

    def test_fiber_alternative_rejects_changed_ordered_id_identity(self) -> None:
        target = _target("addon_fiber", branch="no_delta_reference")
        axis = target.observed_request.feature_axis
        reordered = _feature_ids_artifact(axis, _feature_ids(axis)[::-1])
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "selected final source ID artifact",
        ):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=replace(
                    _gain_request(target.observed_request),
                    feature_ids=reordered,
                ),
            )

    def test_gain_requires_direction_normalized_gain_artifact_kind(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "direction_normalized_addon_gain",
        ):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=target.observed_request,
            )

        wrong_axis = AxisRef(
            "wrong-gain-axis",
            target.observed_request.subject_axis.count,
            "1" * 64,
        )
        malformed = object.__new__(ObservedRequest)
        malformed.__dict__.update(_gain_request(target.observed_request).__dict__)
        wrong_gain = _array_artifact(
            "direction_normalized_addon_gain",
            _fixture_array(target.observed_request.outcome),
            (wrong_axis,),
            units="score",
        )
        object.__setattr__(malformed, "outcome", wrong_gain)
        with self.assertRaisesRegex(SensitivityStrategyError, "outcome artifact axes"):
            AddonExposureSensitivityRequest(target=target, gain_request=malformed)

        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "outcome_direction='higher'",
        ):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=replace(
                    _gain_request(target.observed_request),
                    outcome_direction="lower",
                ),
            )

    def test_gain_and_total_exposure_are_locked_to_realized_final_inputs(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        observed = target.observed_request
        delta = np.linspace(-1.0, 1.0, observed.subject_axis.count)
        adjusted_nuisance = (
            _array_artifact(
                "delta_reference_full",
                delta,
                (observed.subject_axis,),
                units="score",
            ),
            _array_artifact(
                "delta_reference_folds",
                np.tile(delta, (delta.size, 1)),
                (observed.subject_axis, observed.subject_axis),
                units="score",
            ),
        )
        opposite_branch = replace(
            _gain_request(observed),
            branch="delta_reference_adjusted",
            nuisance_inputs=adjusted_nuisance,
        )
        with self.assertRaisesRegex(SensitivityStrategyError, "realized final branch"):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=opposite_branch,
            )

        with self.assertRaisesRegex(SensitivityStrategyError, "realized final branch"):
            AddonExposureSensitivityRequest(
                target=target,
                total_exposure_request=replace(
                    _total_exposure_request(observed),
                    branch="delta_reference_adjusted",
                    nuisance_inputs=adjusted_nuisance,
                ),
            )

        substituted_exposure = _array_artifact(
            "substituted_exposure",
            _fixture_array(observed.exposure),
            (observed.subject_axis, observed.feature_axis),
            units=observed.exposure.units,
            space=observed.exposure.space,
        )
        with self.assertRaisesRegex(SensitivityStrategyError, "final exposure artifact"):
            AddonExposureSensitivityRequest(
                target=target,
                gain_request=replace(
                    _gain_request(observed),
                    exposure=substituted_exposure,
                ),
            )
        with self.assertRaisesRegex(
            SensitivityStrategyError,
            "raw_addon_component_exposure",
        ):
            AddonExposureSensitivityRequest(
                target=target,
                total_exposure_request=replace(
                    observed,
                    exposure=substituted_exposure,
                ),
            )

        substituted_outcome = _array_artifact(
            "substituted_outcome",
            _fixture_array(observed.outcome),
            (observed.subject_axis,),
            units=observed.outcome.units,
            space=observed.outcome.space,
        )
        with self.assertRaisesRegex(SensitivityStrategyError, "final outcome artifact"):
            AddonExposureSensitivityRequest(
                target=target,
                total_exposure_request=replace(
                    _total_exposure_request(observed),
                    outcome=substituted_outcome,
                ),
            )

        substituted_baseline = _array_artifact(
            "substituted_baseline",
            _fixture_array(observed.baseline),
            (observed.subject_axis,),
            units=observed.baseline.units,
            space=observed.baseline.space,
        )
        for field, alternative in (
            (
                "gain_request",
                replace(_gain_request(observed), baseline=substituted_baseline),
            ),
            (
                "total_exposure_request",
                replace(
                    _total_exposure_request(observed),
                    baseline=substituted_baseline,
                ),
            ),
        ):
            with self.subTest(substituted_field=field):
                with self.assertRaisesRegex(
                    SensitivityStrategyError,
                    "final baseline artifact",
                ):
                    AddonExposureSensitivityRequest(
                        target=target,
                        **{field: alternative},
                    )

        adjusted_target = _target(
            "addon_voxel",
            branch="delta_reference_adjusted",
            nuisance_inputs=adjusted_nuisance,
        )
        adjusted_observed = adjusted_target.observed_request
        substituted_nuisance = tuple(
            _array_artifact(
                f"substituted_nuisance_{index}",
                _fixture_array(artifact),
                artifact.axis_refs,
                units=artifact.units,
                space=artifact.space,
            )
            for index, artifact in enumerate(adjusted_observed.nuisance_inputs)
        )
        for field, alternative in (
            (
                "gain_request",
                replace(
                    _gain_request(adjusted_observed),
                    nuisance_inputs=substituted_nuisance,
                ),
            ),
            (
                "total_exposure_request",
                replace(
                    _total_exposure_request(adjusted_observed),
                    nuisance_inputs=substituted_nuisance,
                ),
            ),
        ):
            with self.subTest(substituted_field=field):
                with self.assertRaisesRegex(
                    SensitivityStrategyError,
                    "final nuisance artifacts",
                ):
                    AddonExposureSensitivityRequest(
                        target=adjusted_target,
                        **{field: alternative},
                    )

    def test_nonfinal_request_rejects_an_arbitrary_third_branch(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        with self.assertRaisesRegex(RequestError, "invalid for 'addon_voxel'"):
            replace(target.observed_request, branch="invalid_branch")

    def test_support_and_collinearity_require_exact_axis_artifacts(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        axis = target.observed_request.subject_axis
        values = np.linspace(0.0, 0.5, axis.count)
        support = SupportDiagnosticInput(
            axis,
            _array_artifact(
                "subject_out_support_fraction",
                values,
                (axis,),
                units="fraction",
            ),
            _array_artifact(
                "fold_maximum_out_support_fraction",
                values[::-1],
                (axis,),
                units="fraction",
            ),
        )
        collinearity = CollinearityInput(
            axis,
            ("charge",),
            (
                _array_artifact(
                    "charge",
                    np.linspace(1.0, 2.0, axis.count),
                    (axis,),
                    units="a.u.",
                ),
            ),
        )
        request = AddonExposureSensitivityRequest(
            target=target,
            support_input=support,
            collinearity_input=collinearity,
        )
        self.assertIs(request.support_input, support)
        self.assertIs(request.collinearity_input, collinearity)

        with self.assertRaisesRegex(SensitivityStrategyError, "ArtifactRef"):
            SupportDiagnosticInput(
                axis,
                values,  # type: ignore[arg-type]
                support.fold_maximum_out_support_fraction,
            )
        with self.assertRaisesRegex(SensitivityStrategyError, "ArtifactRef"):
            CollinearityInput(axis, ("charge",), (values,))  # type: ignore[arg-type]

    def test_total_exposure_completes_when_delta_dependent_analysis_fails(self) -> None:
        target = _target("addon_voxel", branch="no_delta_reference")
        observed = target.observed_request
        constant_delta = np.ones(observed.subject_axis.count, dtype=np.float64)
        nonfinal = replace(
            observed,
            branch="delta_reference_adjusted",
            nuisance_inputs=(
                _array_artifact(
                    "constant_delta_reference_full",
                    constant_delta,
                    (observed.subject_axis,),
                    units="score",
                ),
                _array_artifact(
                    "constant_delta_reference_folds",
                    np.tile(constant_delta, (constant_delta.size, 1)),
                    (observed.subject_axis, observed.subject_axis),
                    units="score",
                ),
            ),
        )
        request = AddonExposureSensitivityRequest(
            target=target,
            nonfinal_request=nonfinal,
            total_exposure_request=_total_exposure_request(observed),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = AddonExposureSensitivityStrategy(
                RunScopedArtifactPublisher(Path(temporary), "addon_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            ).run(request)
            payload = _read_json(_json_artifact(result))
        analyses = payload["analyses"]
        self.assertEqual(
            analyses["nonfinal_branch"]["technical_status"],
            "not_computable",
        )
        self.assertEqual(analyses["total_exposure"]["technical_status"], "complete")
        self.assertEqual(analyses["gain"]["technical_status"], "not_applicable")


class FiberControlBoundaryTest(unittest.TestCase):
    def test_plain_peak_uses_all_continuous_candidate_exposure(self) -> None:
        exposure = np.array(
            [
                [10.0, 20.0],
                [210.0, 220.0],
                [230.0, 240.0],
                [250.0, 260.0],
            ],
            dtype=np.float64,
        )
        candidate, touched, exposure_sum, peak = _plain_summaries(
            exposure,
            tau=200.0,
            coverage=2,
            peak_fraction=0.5,
        )
        np.testing.assert_array_equal(candidate, np.array([True, True]))
        self.assertEqual(int(touched[0]), 0)
        self.assertEqual(float(exposure_sum[0]), 30.0)
        self.assertEqual(float(peak[0]), 20.0)

    def test_final_plain_control_uses_overlap_excluded_exposure(self) -> None:
        base = _target("addon_fiber", branch="no_delta_reference")
        raw = _fixture_array(base.observed_request.exposure)
        overlap_values = np.zeros_like(raw, dtype=bool)
        overlap_values[:, 0] = True
        overlap = _array_artifact(
            "reference_overlap_mask",
            overlap_values,
            (
                base.observed_request.subject_axis,
                base.observed_request.feature_axis,
            ),
            units="mask",
            space="synthetic",
        )
        target = FinalSensitivityTarget(
            base.final_model,
            base.observed_request,
            reference_overlap_mask=overlap,
        )
        filtered = materialize_target_exposure(
            target,
            array_provider=_ARRAY_PROVIDER,
        )
        self.assertTrue(np.all(filtered[:, 0] == 0.0))
        _, _, _, expected_peak = _plain_summaries(
            filtered,
            tau=200.0,
            coverage=3,
            peak_fraction=0.05,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = FinalFiberControlStrategy(
                RunScopedArtifactPublisher(root, "control_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            ).run(FinalFiberControlRequest(target))
            peak_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "final_plain_fiber_peak_exposure"
            )
            actual_peak = ArtifactStore([root]).materialize(
                peak_ref,
                expected_dtype=peak_ref.dtype,
                expected_shape=peak_ref.shape,
                expected_axes=peak_ref.axis_refs,
                expected_units="V/m",
                expected_space=None,
            )
        np.testing.assert_allclose(actual_peak, expected_peak, rtol=0.0, atol=0.0)

    def test_observed_and_final_control_types_cannot_be_interchanged(self) -> None:
        target = _target("reference_fiber")
        diagnostic = ObservedResult(source=None, artifacts=(_document_artifact(),))
        observed_request = ObservedFiberControlRequest(
            target.observed_request,
            diagnostic,
            high_threshold_tau=220.0,
            high_threshold_coverage=3,
            fixed_sweet_count=3,
            fixed_sour_count=2,
        )
        final_request = FinalFiberControlRequest(target)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            observed_strategy = ObservedFiberControlStrategy(
                RunScopedArtifactPublisher(root / "observed", "control_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            )
            final_strategy = FinalFiberControlStrategy(
                RunScopedArtifactPublisher(root / "final", "control_test", "1"),
                array_provider=_ARRAY_PROVIDER,
            )
            observed_result = observed_strategy.run(observed_request)
            final_result = final_strategy.run(final_request)
            self.assertEqual(observed_result.sensitivity_kind, "observed_fiber_controls")
            self.assertEqual(final_result.sensitivity_kind, "final_fiber_controls")
            observed_payload = _read_json(_json_artifact(observed_result))
            self.assertIn(
                observed_payload["cheap_controls"]["high_threshold"]["technical_status"],
                {"complete", "not_computable"},
            )
            self.assertIn(
                observed_payload["cheap_controls"]["fixed_outer_library"]["technical_status"],
                {"complete", "not_computable"},
            )
            with self.assertRaises(TypeError):
                observed_strategy.run(final_request)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                final_strategy.run(observed_request)  # type: ignore[arg-type]

        resolved = ObservedResult(
            source=target.final_model.selected_source,
            artifacts=(_document_artifact("resolved"),),
        )
        with self.assertRaisesRegex(SensitivityStrategyError, "resolved source"):
            ObservedFiberControlRequest(target.observed_request, resolved)


class ClassificationFeedbackTest(unittest.TestCase):
    def test_classification_keys_and_values_are_rejected_recursively(self) -> None:
        for payload in (
            {"prediction_status": "error_predictive"},
            {"nested": {"final_model_status": "final_model_realized"}},
            {"innocent_key": "scan_fallback_accepted"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ClassificationFeedbackError):
                    validate_no_classification_feedback(payload)


class FrozenReferenceJitterEvidenceTest(unittest.TestCase):
    TASK_IDS = {
        "task_5b71860d5cf5d6eee91b",
        "task_074a9c54f455d5c87e9d",
    }
    REQUIRED_REPLICATE_FIELDS = {
        "jitter_index",
        "status",
        "spatial_qc_status",
        "loocv_spearman_rho",
        "loocv_pearson_r",
        "q2",
        "mae",
        "rmse",
        "map_pearson_r",
        "valid_support_jaccard",
    }

    def test_allowlisted_hashes_and_first_five_replicates(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "projects/stnsnr/acceptance/frozen"
            / "20260711T034644Z_d318f177f7f2ac7d"
            / "bounded_fixture_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tasks = {
            task["task_id"]: task
            for task in manifest["eligible_tasks"]
            if task["task_id"] in self.TASK_IDS
        }
        self.assertEqual(set(tasks), self.TASK_IDS)
        for task_id, task in tasks.items():
            with self.subTest(task_id=task_id):
                self.assertEqual(task["source_binding_role"], "reference")
                self.assertEqual(task["execution_stage"], "spatial_jitter")
                artifact = next(
                    item for item in task["artifacts"] if item["kind"] == "jitter_results"
                )
                path = Path(artifact["path"])
                if not path.is_file():
                    self.skipTest(f"mounted frozen artifact is unavailable: {path}")
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    artifact["sha256"],
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                replicates = payload["results"]["replicates"][:5]
                self.assertEqual(len(replicates), 5)
                for index, replicate in enumerate(replicates, start=1):
                    self.assertTrue(
                        self.REQUIRED_REPLICATE_FIELDS.issubset(replicate)
                    )
                    self.assertEqual(replicate["jitter_index"], index)
                    self.assertIn(
                        replicate["status"],
                        {"complete", "failed", "not_computable"},
                    )
                    self.assertIsInstance(replicate["spatial_qc_status"], str)
                    for field in (
                        "loocv_spearman_rho",
                        "loocv_pearson_r",
                        "q2",
                        "mae",
                        "rmse",
                        "map_pearson_r",
                        "valid_support_jaccard",
                    ):
                        self.assertTrue(np.isfinite(float(replicate[field])))


if __name__ == "__main__":
    unittest.main()
