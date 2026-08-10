"""Focused tests for individualized target-burden kernels."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
from types import MethodType, SimpleNamespace
import unittest

import numpy as np

from dual_frequency.backends.formal import (
    FinalInSampleBackend,
    IndividualizedTargetFormalBackend,
)
from dual_frequency.backends.formal.common import formal_resampling_schedule
from dual_frequency.backends.individualized_target import (
    IndividualizedTargetBackend,
    evaluate_target_cell,
)
from dual_frequency.backends.nuisance import NuisancePlan
from dual_frequency.backends.sensitivity import (
    IndividualizedTargetJitterRequest,
    IndividualizedTargetSpatialJitterBackend,
    SpatialJitterSettings,
    TargetJitterReplicateEvidence,
)
from dual_frequency.application.publication import (
    CanonicalPublisher,
    _CompleteMarkerWriter,
)
from dual_frequency.application.sensitivity import publish_sensitivity_checkpoints
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.contracts import (
    AxisRef,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FormalRequest,
    FormalResult,
    HardComputabilityLimits,
    InSampleRequest,
    PreparedTargetExposureRecord,
    FinalSelectionRecord,
    SensitivityResult,
    SourceGrid,
    SourceRecord,
    TaskKey,
    TargetObservedRequest,
    TargetScoreSettings,
)
from dual_frequency.runtime.formal_resampling import (
    publish_formal_resampling_schedule,
)
from dual_frequency.runtime.input_provider import StudyRuntimeInputProvider
from dual_frequency.runtime.service_adapters import (
    _prepared_target_exposure_record,
)
from dual_frequency.runtime.target_jitter_provider import (
    StudyTargetJitterReplicateProvider,
)
from dual_frequency.workflow import ExecutionPlan, TaskSpec


def _target_fixture(
    root: Path,
    *,
    subjects: int = 14,
    targets: int = 3,
) -> tuple[
    RunScopedArtifactPublisher,
    ArtifactStore,
    FinalModelRecord,
    AxisRef,
    AxisRef,
    AxisRef,
    object,
    object,
    object,
    object,
    object,
]:
    publisher = RunScopedArtifactPublisher(root, "target_test", "unversioned")
    subject_axis = AxisRef("target-subjects", subjects, "a" * 64)
    target_axis = AxisRef("selected-targets", targets, "b" * 64)
    tau_axis = AxisRef("target-tau", 1, "c" * 64)
    target_ids = np.asarray(
        ("GPe", "GPi", "posterior_putamen")[:targets],
        dtype="<U17",
    )
    target_ids_ref = publisher.array(
        "target_ids.npy",
        target_ids,
        kind="individualized_target_ids",
        axes=(target_axis,),
        units="target_id",
        space=None,
    )
    endpoint = EndpointKey(
        study_id="target_fixture",
        scale_id="synthetic_scale",
        endpoint_binding_id="reference",
        model_family="reference_individualized",
        connectome_id="none",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_predictive",
        threshold_source="pre_specified",
        selected_tau=400.0,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(
            target_axis,
            "selected_individualized_target_union",
        ),
        artifacts=(target_ids_ref,),
    )
    final = FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            400.0,
            5,
            "target_activation_burden",
        ),
        selected_source=source,
        selected_branch=None,
    )
    z = np.linspace(-1.5, 1.5, subjects, dtype=np.float64)
    exposure = np.column_stack(
        (
            160.0 + 35.0 * z,
            110.0 - 18.0 * z + np.sin(np.arange(subjects)),
            90.0 + 8.0 * np.cos(np.arange(subjects)),
        )
    )[:, :targets]
    outcome = 50.0 - 9.0 * z + np.sin(np.arange(subjects)) * 0.2
    baseline = 20.0 + np.cos(np.arange(subjects)) * 0.5
    support = np.ones(exposure.shape, dtype=bool)
    exposure_ref = publisher.array(
        "exposure.npy",
        exposure,
        kind="final_selected_exposure",
        axes=(subject_axis, target_axis),
        units="V/m",
        space="individualized_target",
    )
    support_ref = publisher.array(
        "support.npy",
        support,
        kind="individualized_final_target_support",
        axes=(subject_axis, target_axis),
        units="binary",
        space="individualized_target",
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
    return (
        publisher,
        ArtifactStore((root,)),
        final,
        subject_axis,
        target_axis,
        tau_axis,
        target_ids_ref,
        exposure_ref,
        support_ref,
        outcome_ref,
        baseline_ref,
    )


def _target_formal_request(
    final: FinalModelRecord,
    subject_axis: AxisRef,
    target_axis: AxisRef,
    target_ids_ref,
    exposure_ref,
    support_ref,
    outcome_ref,
    baseline_ref,
    *,
    kind: str,
    resamples: int,
) -> FormalRequest:
    return FormalRequest(
        final_model=final,
        resampling_kind=kind,
        exposure=exposure_ref,
        outcome=outcome_ref,
        baseline=baseline_ref,
        delta_reference_full=None,
        delta_reference_folds=None,
        subject_axis=subject_axis,
        feature_axis=target_axis,
        exposure_units="V/m",
        exposure_space="individualized_target",
        outcome_direction="lower",
        hard_computability=HardComputabilityLimits(12, 1, 1),
        connectome_role="none",
        feature_ids=None,
        fiber_score_settings=None,
        resamples=resamples,
        seed=42,
        target_support=support_ref,
        target_ids=target_ids_ref,
        target_score_settings=TargetScoreSettings(
            exposure_scaling="training_fold_zscore",
            normalization="sum_absolute_target_weights",
        ),
    )


class IndividualizedTargetKernelTest(unittest.TestCase):
    def test_target_tck_path_includes_configured_tractogram_space(self) -> None:
        provider = object.__new__(StudyRuntimeInputProvider)
        provider.configuration = SimpleNamespace(
            individualized_seed_target=SimpleNamespace(
                tractography=SimpleNamespace(
                    subject_root_pattern="/tractography/sub-{subject_id}",
                    space="configuredTargetSpace",
                    seed_id="STNSNrplus",
                )
            )
        )
        self.assertEqual(
            provider._target_tck_path("SNr017", "lh", "GPe"),
            Path(
                "/tractography/sub-SNr017/tractograms/"
                "configuredTargetSpace/lh/STNSNrplus/targets/lh/GPe.tck"
            ),
        )

    def test_prepared_target_exposure_is_selected_by_endpoint(self) -> None:
        reference_endpoint = EndpointKey(
            study_id="target_fixture",
            scale_id="scale_a",
            endpoint_binding_id="reference",
            model_family="reference_individualized",
            connectome_id="none",
        )
        other_endpoint = EndpointKey(
            study_id="target_fixture",
            scale_id="scale_b",
            endpoint_binding_id="reference",
            model_family="reference_individualized",
            connectome_id="none",
        )
        selected = object.__new__(PreparedTargetExposureRecord)
        object.__setattr__(selected, "endpoint", reference_endpoint)
        other = object.__new__(PreparedTargetExposureRecord)
        object.__setattr__(other, "endpoint", other_endpoint)
        request = SimpleNamespace(
            task=SimpleNamespace(task_id="target_jitter"),
            dependencies={
                "other": SimpleNamespace(record=other),
                "selected": SimpleNamespace(record=selected),
            },
        )

        self.assertIs(
            _prepared_target_exposure_record(
                request,
                reference_endpoint.identifier,
            ),
            selected,
        )

    def test_sensitivity_checkpoint_accepts_target_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary) / "run"
            (
                publisher,
                _store,
                final,
                subject_axis,
                target_axis,
                tau_axis,
                target_ids,
                _exposure,
                _support,
                _outcome,
                _baseline,
            ) = _target_fixture(run_root, subjects=14, targets=3)
            endpoint = final.endpoint
            side_axis = AxisRef("target-sides", 2, "d" * 64)
            totals = np.full((14, 2, 3), 100, dtype=np.int64)
            side_shape = (1, 14, 2, 3)
            patient_shape = (1, 14, 3)
            prepared = PreparedTargetExposureRecord(
                endpoint=endpoint,
                subject_axis=subject_axis,
                target_axis=target_axis,
                side_axis=side_axis,
                tau_axis=tau_axis,
                target_ids=target_ids,
                side_total_counts=publisher.array(
                    "checkpoint_side_total_counts.npy",
                    totals,
                    kind="individualized_side_total_fiber_counts",
                    axes=(subject_axis, side_axis, target_axis),
                    units="count",
                    space=None,
                ),
                side_burdens=publisher.array(
                    "checkpoint_side_burdens.npy",
                    np.full(side_shape, 125.0, dtype=np.float32),
                    kind="individualized_side_target_burdens",
                    axes=(tau_axis, subject_axis, side_axis, target_axis),
                    units="V/m",
                    space=None,
                ),
                side_activated_counts=publisher.array(
                    "checkpoint_side_activated_counts.npy",
                    np.full(side_shape, 25, dtype=np.int64),
                    kind="individualized_side_activated_fiber_counts",
                    axes=(tau_axis, subject_axis, side_axis, target_axis),
                    units="count",
                    space=None,
                ),
                side_activated_fractions=publisher.array(
                    "checkpoint_side_activated_fractions.npy",
                    np.full(side_shape, 0.25, dtype=np.float32),
                    kind="individualized_side_activated_fiber_fractions",
                    axes=(tau_axis, subject_axis, side_axis, target_axis),
                    units="fraction",
                    space=None,
                ),
                patient_burdens=publisher.array(
                    "checkpoint_patient_burdens.npy",
                    np.full(patient_shape, 125.0, dtype=np.float32),
                    kind="individualized_patient_target_burdens",
                    axes=(tau_axis, subject_axis, target_axis),
                    units="V/m",
                    space=None,
                ),
                patient_support=publisher.array(
                    "checkpoint_patient_support.npy",
                    np.ones(patient_shape, dtype=bool),
                    kind="individualized_patient_target_support",
                    axes=(tau_axis, subject_axis, target_axis),
                    units="binary",
                    space=None,
                ),
                delta_reference_input_status="not_applicable",
                delta_reference_reason_code="reference_model",
                auxiliary_readiness=None,
                reference_condition_patient_burdens=None,
                reference_condition_patient_support=None,
                addon_reference_component_patient_burdens=None,
                addon_reference_component_patient_support=None,
            )
            selection = FinalSelectionRecord(
                endpoint=endpoint,
                selection_status="final_model_realized",
                final_model=final,
                reason_codes=("primary_realized",),
                causal_task_ids=("task_source",),
            )

            def task(
                stage: str,
                output_record_type: str,
                dependencies: tuple[str, ...] = (),
            ) -> TaskSpec:
                return TaskSpec(
                    key=TaskKey(
                        endpoint.identifier,
                        stage,
                        parameter_identity="e" * 64,
                    ),
                    endpoint_id=endpoint.identifier,
                    model_family=endpoint.model_family,
                    connectome_role="none",
                    stage=stage,
                    round_id="round_test",
                    phase="observed",
                    service_id=f"test_{stage}",
                    dependencies=dependencies,
                    gates=(),
                    output_record_type=output_record_type,
                )

            input_task = task("input_readiness", "EndpointInputRecord")
            prepare_task = task(
                "prepare_exposure",
                "PreparedTargetExposureRecord",
                (input_task.task_id,),
            )
            final_task = task(
                "final_realization",
                "FinalSelectionRecord",
                (prepare_task.task_id,),
            )
            plan = ExecutionPlan(
                configuration_hash="a" * 64,
                scientific_configuration_hash="b" * 64,
                through="report",
                tasks=(input_task, prepare_task, final_task),
            )
            cache_root = Path(temporary) / "cache"
            output_root = Path(temporary) / "output"
            cache_root.mkdir()
            output_root.mkdir()
            index = publish_sensitivity_checkpoints(
                run_root=run_root,
                plan=plan,
                outcomes=(),
                typed_records={
                    input_task.task_id: SimpleNamespace(subject_axis=subject_axis),
                    prepare_task.task_id: prepared,
                    final_task.task_id: selection,
                },
                run_id="individualized-checkpoint-test",
                study_id=endpoint.study_id,
                cache_root=cache_root,
                output_root=output_root,
                source_identities=(),
                rng_profiles={"individualized_seed_target": {"seed": 42}},
            )
            self.assertEqual(len(index["bases"]), 1)
            base_path = (
                run_root
                / "sensitivity_bases"
                / index["bases"][0]["relative_path"]
            )
            base = json.loads(base_path.read_text(encoding="utf-8"))
            self.assertEqual(
                base["shared_exposure_artifact"]["sha256"],
                prepared.patient_burdens.sha256,
            )

    def test_runtime_provider_reads_locked_reference_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                _publisher,
                _store,
                final,
                _subject_axis,
                _target_axis,
                _tau_axis,
                _target_ids,
                _exposure,
                _support,
                _outcome,
                _baseline,
            ) = _target_fixture(Path(temporary), subjects=14, targets=3)
            source = final.selected_source
            assert source is not None
            self.assertEqual(
                StudyRuntimeInputProvider._selected_tau_coverage(source),
                (400.0, 5),
            )

    def test_target_burden_uses_any_side_support_and_bilateral_mean(self) -> None:
        provider = object.__new__(StudyRuntimeInputProvider)
        provider.configuration = SimpleNamespace(
            individualized_seed_target=SimpleNamespace(
                source=SimpleNamespace(tau_values=(400.0,)),
                target_exposure=SimpleNamespace(
                    activated_fiber_count_min=20,
                    activated_fiber_fraction_min=0.05,
                ),
                tractography=SimpleNamespace(target_ids=("target_a",)),
            )
        )
        peaks = [
            [
                [np.concatenate((np.full(20, 400.0), np.full(80, 200.0)))],
                [np.concatenate((np.full(10, 500.0), np.full(90, 100.0)))],
            ]
        ]

        arrays = provider._target_burden_arrays(
            primary_peaks=peaks,
            reference_component_peaks=None,
            reference_tau=None,
        )

        self.assertEqual(arrays.side_activated_counts[0, 0, :, 0].tolist(), [20, 10])
        self.assertTrue(arrays.patient_support[0, 0, 0])
        self.assertAlmostEqual(float(arrays.side_burdens[0, 0, 0, 0]), 80.0)
        self.assertAlmostEqual(float(arrays.side_burdens[0, 0, 1, 0]), 50.0)
        self.assertAlmostEqual(float(arrays.patient_burdens[0, 0, 0]), 65.0)

    def test_target_jitter_cache_path_includes_support_thresholds(self) -> None:
        def shared_root(fraction: float) -> Path:
            jitter = object.__new__(StudyTargetJitterReplicateProvider)
            jitter.provider = SimpleNamespace(
                configuration=SimpleNamespace(
                    workflow=SimpleNamespace(
                        output=SimpleNamespace(root=Path("/tmp/output")),
                    ),
                    individualized_seed_target=SimpleNamespace(
                        target_exposure=SimpleNamespace(
                            activated_fiber_count_min=20,
                            activated_fiber_fraction_min=fraction,
                        ),
                    ),
                ),
            )
            jitter.final_model = SimpleNamespace(
                endpoint=SimpleNamespace(model_family="reference_individualized"),
            )
            jitter.reference_dependency = None
            jitter.endpoint_input = SimpleNamespace(
                included_subject_ids=("001", "002"),
            )
            jitter.settings = SimpleNamespace(
                translation_fwhm_mm=2.0,
                seed=42,
            )
            return jitter._shared_root()

        old_root = shared_root(0.05)
        new_root = shared_root(0.01)

        self.assertNotEqual(old_root, new_root)
        self.assertIn("support_count_20", new_root.parts)
        self.assertIn("support_fraction_0p01", new_root.parts)

    def test_addon_target_burden_excludes_inclusive_reference_overlap(self) -> None:
        provider = object.__new__(StudyRuntimeInputProvider)
        provider.configuration = SimpleNamespace(
            individualized_seed_target=SimpleNamespace(
                source=SimpleNamespace(tau_values=(400.0,)),
                target_exposure=SimpleNamespace(
                    activated_fiber_count_min=1,
                    activated_fiber_fraction_min=0.01,
                ),
                tractography=SimpleNamespace(target_ids=("target_a",)),
            )
        )
        primary = np.concatenate((np.full(20, 400.0), np.full(80, 200.0)))
        reference = np.concatenate(
            (np.full(5, 400.0), np.full(15, 399.0), np.full(80, 0.0))
        )
        primary_peaks = [[[primary], [primary]]]
        reference_peaks = [[[reference], [reference]]]

        arrays = provider._target_burden_arrays(
            primary_peaks=primary_peaks,
            reference_component_peaks=reference_peaks,
            reference_tau=400.0,
        )

        self.assertEqual(arrays.side_activated_counts[0, 0, :, 0].tolist(), [15, 15])
        self.assertAlmostEqual(float(arrays.side_activated_fractions[0, 0, 0, 0]), 0.15)
        self.assertAlmostEqual(float(arrays.side_burdens[0, 0, 0, 0]), 60.0)

    def test_fold_scaling_uses_only_training_rows(self) -> None:
        subjects = 14
        primary = np.linspace(20.0, 180.0, subjects)
        exposure = np.column_stack(
            (
                primary,
                np.square(np.linspace(-1.0, 1.0, subjects)) * 40.0,
                np.sin(np.arange(subjects)) * 10.0 + 50.0,
            )
        )
        support = np.ones_like(exposure, dtype=bool)
        outcome = primary + np.cos(np.arange(subjects)) * 2.0
        baseline = np.linspace(-0.5, 0.5, subjects)
        full = baseline[:, None]
        nuisance = NuisancePlan(
            full_covariates=full,
            fold_covariates=np.broadcast_to(
                full,
                (subjects, subjects, 1),
            ),
        )

        computation = evaluate_target_cell(
            exposure,
            support,
            outcome,
            nuisance,
            "higher",
            400.0,
            5,
            HardComputabilityLimits(12, 1, 1),
            retain_arrays=True,
        )

        self.assertTrue(computation.metrics.passes_hard_computability)
        self.assertIsNotNone(computation.arrays)
        assert computation.arrays is not None
        expected_center = float(np.mean(exposure[1:, 0]))
        expected_scale = float(np.std(exposure[1:, 0]))
        self.assertAlmostEqual(
            computation.arrays.fold_centers[0, 0],
            expected_center,
        )
        self.assertAlmostEqual(
            computation.arrays.fold_scales[0, 0],
            expected_scale,
        )
        self.assertNotAlmostEqual(
            computation.arrays.fold_centers[0, 0],
            float(np.mean(exposure[:, 0])),
        )
        self.assertTrue(
            np.all(
                np.isfinite(
                    computation.arrays.full_nominal_p[
                        computation.arrays.full_valid_mask
                    ]
                )
            )
        )
        self.assertTrue(
            np.all(
                computation.arrays.full_fdr_q[
                    computation.arrays.full_valid_mask
                ]
                >= computation.arrays.full_nominal_p[
                    computation.arrays.full_valid_mask
                ]
            )
        )

    def test_coverage_is_inclusive(self) -> None:
        subjects = 12
        exposure = np.column_stack(
            (
                np.arange(subjects, dtype=np.float64),
                np.linspace(10.0, 30.0, subjects),
            )
        )
        support = np.zeros_like(exposure, dtype=bool)
        support[:6, 0] = True
        support[:, 1] = True
        outcome = np.arange(subjects, dtype=np.float64) + 0.1
        baseline = np.sin(np.arange(subjects, dtype=np.float64))
        full = baseline[:, None]
        nuisance = NuisancePlan(
            full_covariates=full,
            fold_covariates=np.broadcast_to(
                full,
                (subjects, subjects, 1),
            ),
        )

        computation = evaluate_target_cell(
            exposure,
            support,
            outcome,
            nuisance,
            "higher",
            400.0,
            6,
            HardComputabilityLimits(12, 1, 1),
            retain_arrays=True,
        )

        self.assertIsNotNone(computation.arrays)
        assert computation.arrays is not None
        self.assertTrue(computation.arrays.full_support_mask[0])
        self.assertEqual(computation.metrics.n_features_full, 2)

    def test_jitter_block_streams_each_target_once_for_all_replicates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                _publisher,
                _store,
                final,
                subject_axis,
                _target_axis,
                _tau_axis,
                _target_ids,
                _exposure,
                _support,
                outcome,
                baseline,
            ) = _target_fixture(Path(temporary), subjects=14, targets=3)
            subject_ids = tuple(
                f"subject-{index:02d}" for index in range(14)
            )
            endpoint_input = EndpointInputRecord(
                endpoint=final.endpoint,
                readiness_status="ready",
                candidate_subject_ids=subject_ids,
                included_subject_ids=subject_ids,
                exclusions=(),
                minimum_subjects=12,
                subject_axis=subject_axis,
                baseline=baseline,
                outcome=outcome,
            )
            provider = object.__new__(StudyRuntimeInputProvider)
            provider.configuration = SimpleNamespace(
                individualized_seed_target=SimpleNamespace(
                    endpoint_pair=SimpleNamespace(
                        reference=SimpleNamespace(identifier="reference"),
                        addon=SimpleNamespace(identifier="addon"),
                    ),
                    source=SimpleNamespace(
                        tau_values=(200.0, 400.0, 600.0),
                    ),
                    target_exposure=SimpleNamespace(
                        activated_fiber_count_min=1,
                        activated_fiber_fraction_min=0.25,
                    ),
                    tractography=SimpleNamespace(
                        sides=("lh", "rh"),
                        target_ids=("target_a", "target_b", "target_c"),
                    ),
                )
            )
            provider._endpoints = {
                final.endpoint.identifier: SimpleNamespace(
                    key=final.endpoint,
                )
            }
            provider._subjects = {
                subject_id: object() for subject_id in subject_ids
            }
            provider._condition_samplers = MethodType(
                lambda self, *args, **kwargs: (
                    {"lh": (object(),), "rh": (object(),)},
                    None,
                ),
                provider,
            )
            provider._target_tck_path = MethodType(
                lambda self, subject_id, side, target_id: Path(
                    f"/{subject_id}/{side}/{target_id}.tck"
                ),
                provider,
            )
            sample_calls: list[Path] = []

            def sample_block(
                self,
                path,
                samplers,
                translations_mm,
            ):
                del self, samplers
                sample_calls.append(path)
                base = np.asarray(
                    [300.0, 450.0, 500.0, 700.0],
                    dtype=np.float32,
                )
                return np.stack(
                    [
                        base + replicate_offset * 10.0
                        for replicate_offset in range(len(translations_mm))
                    ]
                )

            provider._sample_target_tck_block = MethodType(
                sample_block,
                provider,
            )
            block = provider.build_target_jitter_burden_block(
                endpoint_input=endpoint_input,
                reference_dependency=None,
                replicate_start=0,
                replicate_stop=2,
                root_seed=42,
                translation_fwhm_mm=2.0,
            )
            self.assertEqual(
                len(sample_calls),
                len(subject_ids) * 2 * 3,
            )
            self.assertEqual(
                block.patient_burdens.shape,
                (2, 3, 14, 3),
            )
            self.assertAlmostEqual(
                float(block.patient_burdens[0, 1, 0, 0]),
                412.5,
            )
            self.assertTrue(block.patient_support[0, 1, 0, 0])

    def test_observed_backend_publishes_full_reporting_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publisher = RunScopedArtifactPublisher(
                root,
                "target_observed_test",
                "unversioned",
            )
            subjects = 14
            targets = 17
            subject_axis = AxisRef("observed-subjects", subjects, "7" * 64)
            target_axis = AxisRef("observed-targets", targets, "8" * 64)
            tau_axis = AxisRef("observed-tau", 1, "9" * 64)
            target_ids = np.asarray(
                [f"target_{index:02d}" for index in range(targets)],
                dtype="<U17",
            )
            x = np.linspace(-1.0, 1.0, subjects)
            burdens = np.column_stack(
                [
                    100.0 + (index + 1) * x + np.sin(np.arange(subjects) + index)
                    for index in range(targets)
                ]
            )
            support = np.ones_like(burdens, dtype=bool)
            outcome = 20.0 + 4.0 * x + np.cos(np.arange(subjects))
            baseline = 10.0 + np.sin(np.arange(subjects))
            request = TargetObservedRequest(
                endpoint=EndpointKey(
                    study_id="target_observed",
                    scale_id="scale_a",
                    endpoint_binding_id="reference",
                    model_family="reference_individualized",
                    connectome_id="none",
                ),
                branch="reference",
                patient_burdens=publisher.array(
                    "burdens.npy",
                    burdens[None],
                    kind="individualized_patient_burdens",
                    axes=(tau_axis, subject_axis, target_axis),
                    units="V/m",
                    space="individualized_target",
                ),
                patient_support=publisher.array(
                    "support.npy",
                    support[None],
                    kind="individualized_patient_support",
                    axes=(tau_axis, subject_axis, target_axis),
                    units="binary",
                    space="individualized_target",
                ),
                outcome=publisher.array(
                    "outcome.npy",
                    outcome,
                    kind="outcome",
                    axes=(subject_axis,),
                    units="score",
                    space=None,
                ),
                baseline=publisher.array(
                    "baseline.npy",
                    baseline,
                    kind="baseline",
                    axes=(subject_axis,),
                    units="score",
                    space=None,
                ),
                nuisance_inputs=(),
                subject_axis=subject_axis,
                target_axis=target_axis,
                tau_axis=tau_axis,
                target_ids=publisher.array(
                    "input_target_ids.npy",
                    target_ids,
                    kind="individualized_target_ids",
                    axes=(target_axis,),
                    units="target_id",
                    space=None,
                ),
                source_grid=SourceGrid(
                    pre_specified_tau=400.0,
                    pre_specified_coverage=5,
                    tau_values=(400.0,),
                    coverage_values=(5,),
                    minimum_adjacent_passing_cells=0,
                ),
                outcome_direction="higher",
                hard_computability=HardComputabilityLimits(12, 1, 1),
                score_settings=TargetScoreSettings(
                    exposure_scaling="training_fold_zscore",
                    normalization="sum_absolute_target_weights",
                ),
            )
            result = IndividualizedTargetBackend(
                publisher,
                artifact_store=ArtifactStore((root,)),
            ).run(request)
            artifacts = {artifact.kind: artifact for artifact in result.artifacts}
            for kind in (
                "individualized_all_target_ids",
                "individualized_all_full_target_weights",
                "individualized_all_full_target_nominal_p",
                "individualized_all_full_target_fdr_q",
                "individualized_all_fold_target_weights",
                "individualized_all_fold_target_valid_masks",
            ):
                self.assertIn(kind, artifacts)
            self.assertEqual(
                artifacts["individualized_all_target_ids"].shape,
                (17,),
            )


class IndividualizedTargetFormalTest(unittest.TestCase):
    def test_permutation_and_bootstrap_execute_on_target_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                publisher,
                artifact_store,
                final,
                subject_axis,
                target_axis,
                _,
                target_ids,
                exposure,
                support,
                outcome,
                baseline,
            ) = _target_fixture(root)
            backend = IndividualizedTargetFormalBackend(
                publisher,
                artifact_store=artifact_store,
            )
            permutation_request = _target_formal_request(
                final,
                subject_axis,
                target_axis,
                target_ids,
                exposure,
                support,
                outcome,
                baseline,
                kind="permutation",
                resamples=3,
            )
            permutation_schedule = formal_resampling_schedule(
                "permutation",
                subject_axis.count,
                3,
                42,
            )
            permutation_block = backend.run_permutation_block(
                permutation_request,
                permutation_schedule,
                permutation_schedule.blocks(block_size=3)[0],
            )
            schedule_artifact = publish_formal_resampling_schedule(
                permutation_request,
                publisher,
            ).schedule
            permutation_result = backend.aggregate_permutation(
                permutation_request,
                permutation_schedule,
                (permutation_block,),
                schedule_artifact,
            )
            self.assertEqual(
                permutation_result.resampling_kind,
                "permutation",
            )
            self.assertIn(
                "formal_permutation_summary",
                {artifact.kind for artifact in permutation_result.artifacts},
            )

            bootstrap_request = _target_formal_request(
                final,
                subject_axis,
                target_axis,
                target_ids,
                exposure,
                support,
                outcome,
                baseline,
                kind="bootstrap",
                resamples=3,
            )
            bootstrap_schedule = formal_resampling_schedule(
                "bootstrap",
                subject_axis.count,
                3,
                42,
            )
            bootstrap_block = backend.run_bootstrap_block(
                bootstrap_request,
                bootstrap_schedule,
                bootstrap_schedule.blocks(block_size=3)[0],
            )
            bootstrap_result = backend.aggregate_bootstrap(
                bootstrap_request,
                bootstrap_schedule,
                (bootstrap_block,),
            )
            self.assertEqual(
                bootstrap_result.resampling_kind,
                "bootstrap",
            )
            self.assertIn(
                "formal_bootstrap_summary",
                {artifact.kind for artifact in bootstrap_result.artifacts},
            )
            replicate_weights = next(
                artifact
                for artifact in bootstrap_result.artifacts
                if artifact.kind == "formal_bootstrap_replicate_weights"
            )
            self.assertEqual(
                replicate_weights.shape,
                (3, target_axis.count),
            )

    def test_in_sample_publishes_paired_target_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                publisher,
                artifact_store,
                final,
                subject_axis,
                target_axis,
                _,
                target_ids,
                exposure,
                support,
                outcome,
                baseline,
            ) = _target_fixture(root)
            outcome_values = np.asarray(
                artifact_store.materialize(
                    outcome,
                    expected_dtype=outcome.dtype,
                    expected_shape=outcome.shape,
                    expected_axes=outcome.axis_refs,
                    expected_units=outcome.units,
                    expected_space=outcome.space,
                ),
                dtype=np.float64,
            )
            loocv_predictions = publisher.array(
                "loocv_predictions.npy",
                outcome_values + np.linspace(-0.5, 0.5, subject_axis.count),
                kind="loocv_model_predictions",
                axes=(subject_axis,),
                units="score",
                space=None,
            )
            loocv_baseline = publisher.array(
                "loocv_baseline.npy",
                np.full(subject_axis.count, np.mean(outcome_values)),
                kind="loocv_baseline_predictions",
                axes=(subject_axis,),
                units="score",
                space=None,
            )
            loocv_summary = publisher.document(
                "loocv_summary.json",
                {
                    "p_plus_one_two_sided": 0.25,
                    "resamples_requested": 3,
                    "finite_replicate_count": 3,
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
                final_model=final,
                exposure=exposure,
                outcome=outcome,
                baseline=baseline,
                delta_reference_full=None,
                subject_axis=subject_axis,
                feature_axis=target_axis,
                feature_ids=None,
                loocv_predictions=loocv_predictions,
                loocv_baseline_predictions=loocv_baseline,
                loocv_permutation_summary=loocv_summary,
                exposure_units="V/m",
                exposure_space="individualized_target",
                outcome_direction="lower",
                hard_computability=HardComputabilityLimits(12, 1, 1),
                connectome_role="none",
                fiber_score_settings=None,
                resamples=3,
                seed=42,
                target_support=support,
                target_ids=target_ids,
                target_score_settings=TargetScoreSettings(
                    exposure_scaling="training_fold_zscore",
                    normalization="sum_absolute_target_weights",
                ),
            )
            result = FinalInSampleBackend(
                publisher,
                artifact_store=artifact_store,
            ).run(request)
            summary_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_in_sample_summary"
            )
            summary = json.loads(
                Path(summary_ref.uri.removeprefix("file://")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["candidate_feature_count"], target_axis.count)
            self.assertIn("in_sample_spearman_rho", summary["in_sample"])
            self.assertIn("loocv_spearman_rho", summary["loocv"])
            self.assertIn(
                "spearman_optimism_gap",
                summary["optimism_gaps"],
            )

    def test_formal_only_publication_retains_full_target_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "work"
            output = root / "published"
            publisher = RunScopedArtifactPublisher(
                work,
                "target_publication_test",
                "unversioned",
            )
            subjects = 14
            target_names = (
                "GPe",
                "GPi",
                "caudate",
                "posterior_putamen",
                "VLP_thalamus",
                "VLA_thalamus",
                "RN",
                "VA_thalamus",
                "VM_thalamus",
                "PPN",
                "SMA",
                "M1",
                "sPf_thalamus",
                "premotor",
                "CM_thalamus",
                "DLPFC",
                "Pf_thalamus",
            )
            subject_axis = AxisRef("publication-subjects", subjects, "1" * 64)
            target_axis = AxisRef("publication-targets", 17, "2" * 64)
            selected_axis = AxisRef("publication-selected-targets", 3, "3" * 64)
            side_axis = AxisRef("publication-sides", 2, "4" * 64)
            tau_axis = AxisRef("publication-tau", 1, "5" * 64)
            replicate_axis = AxisRef("publication-replicates", 4, "6" * 64)
            endpoint = EndpointKey(
                study_id="target_publication",
                scale_id="scale_a",
                endpoint_binding_id="reference",
                model_family="reference_individualized",
                connectome_id="none",
            )
            target_values = np.asarray(target_names, dtype="<U17")
            selected_indices = np.asarray([0, 1, 2], dtype=np.int64)
            weights = np.full(17, np.nan, dtype=np.float64)
            weights[:3] = np.asarray([0.8, -0.4, 0.2])
            nominal_p = np.full(17, np.nan, dtype=np.float64)
            nominal_p[:3] = np.asarray([0.001, 0.02, 0.2])
            fdr_q = np.full(17, np.nan, dtype=np.float64)
            fdr_q[:3] = np.asarray([0.003, 0.03, 0.2])
            valid = np.isfinite(weights)
            folds = np.broadcast_to(weights, (subjects, 17)).copy()
            fold_valid = np.broadcast_to(valid, (subjects, 17)).copy()
            centers = np.arange(17, dtype=np.float64) + 100.0
            scales = np.arange(17, dtype=np.float64) + 10.0
            z = np.linspace(-1.0, 1.0, subjects)
            outcome_values = 50.0 - 5.0 * z
            baseline_values = 20.0 + z
            score_values = 2.0 * z
            prediction_values = outcome_values + 0.1
            baseline_prediction_values = np.full(
                subjects,
                np.mean(outcome_values),
            )

            def array(
                name: str,
                values: np.ndarray,
                kind: str,
                axes: tuple[AxisRef, ...],
                units: str | None,
                space: str | None = None,
            ):
                return publisher.array(
                    name,
                    values,
                    kind=kind,
                    axes=axes,
                    units=units,
                    space=space,
                )

            all_target_ids = array(
                "all_target_ids.npy",
                target_values,
                "individualized_all_target_ids",
                (target_axis,),
                "target_id",
            )
            selected_index_artifact = array(
                "selected_indices.npy",
                selected_indices,
                "individualized_selected_target_indices",
                (selected_axis,),
                "index",
            )
            source_artifacts = (
                all_target_ids,
                selected_index_artifact,
                array(
                    "selected_target_ids.npy",
                    target_values[selected_indices],
                    "individualized_target_ids",
                    (selected_axis,),
                    "target_id",
                ),
                array(
                    "all_weights.npy",
                    weights,
                    "individualized_all_full_target_weights",
                    (target_axis,),
                    "coefficient",
                ),
                array(
                    "all_nominal_p.npy",
                    nominal_p,
                    "individualized_all_full_target_nominal_p",
                    (target_axis,),
                    "probability",
                ),
                array(
                    "all_fdr_q.npy",
                    fdr_q,
                    "individualized_all_full_target_fdr_q",
                    (target_axis,),
                    "probability",
                ),
                array(
                    "all_support.npy",
                    valid,
                    "individualized_all_full_target_support_mask",
                    (target_axis,),
                    "binary",
                ),
                array(
                    "all_valid.npy",
                    valid,
                    "individualized_all_full_target_valid_mask",
                    (target_axis,),
                    "binary",
                ),
                array(
                    "all_centers.npy",
                    centers,
                    "individualized_all_full_target_centers",
                    (target_axis,),
                    "V/m",
                ),
                array(
                    "all_scales.npy",
                    scales,
                    "individualized_all_full_target_scales",
                    (target_axis,),
                    "V/m",
                ),
                array(
                    "all_fold_weights.npy",
                    folds,
                    "individualized_all_fold_target_weights",
                    (subject_axis, target_axis),
                    "coefficient",
                ),
                array(
                    "all_fold_centers.npy",
                    np.broadcast_to(centers, (subjects, 17)),
                    "individualized_all_fold_target_centers",
                    (subject_axis, target_axis),
                    "V/m",
                ),
                array(
                    "all_fold_scales.npy",
                    np.broadcast_to(scales, (subjects, 17)),
                    "individualized_all_fold_target_scales",
                    (subject_axis, target_axis),
                    "V/m",
                ),
                array(
                    "all_fold_support.npy",
                    fold_valid,
                    "individualized_all_fold_target_support_masks",
                    (subject_axis, target_axis),
                    "binary",
                ),
                array(
                    "all_fold_valid.npy",
                    fold_valid,
                    "individualized_all_fold_target_valid_masks",
                    (subject_axis, target_axis),
                    "binary",
                ),
                array(
                    "full_scores.npy",
                    score_values,
                    "individualized_full_target_scores",
                    (subject_axis,),
                    "score",
                ),
                array(
                    "heldout_scores.npy",
                    score_values,
                    "individualized_loocv_heldout_scores",
                    (subject_axis,),
                    "score",
                ),
                array(
                    "heldout_predictions.npy",
                    prediction_values,
                    "loocv_model_predictions",
                    (subject_axis,),
                    "score",
                ),
                array(
                    "baseline_predictions.npy",
                    baseline_prediction_values,
                    "loocv_baseline_predictions",
                    (subject_axis,),
                    "score",
                ),
                publisher.document(
                    "source_resolution.json",
                    {
                        "source_status": "scan_fallback_accepted",
                        "prediction_status": "error_predictive",
                        "threshold_source": "scan_fallback",
                        "selected_tau": 400.0,
                        "selected_coverage": 5,
                        "adjacent_support": 2,
                        "failure_reason": None,
                        "selected_metrics": {"n_features_full": 3},
                    },
                    kind="individualized_target_source_resolution",
                ),
            )
            source = SourceRecord(
                endpoint=endpoint,
                input_status="valid",
                source_status="scan_fallback_accepted",
                prediction_status="error_predictive",
                threshold_source="scan_fallback",
                selected_tau=400.0,
                selected_coverage=5,
                adjacent_support=2,
                feature_axis=FeatureAxisRef(
                    selected_axis,
                    "selected_individualized_target_union",
                ),
                artifacts=source_artifacts,
            )
            final = FinalModelRecord(
                endpoint=endpoint,
                final_status="final_model_realized",
                realization_role="primary",
                final_key=FinalModelKey(
                    endpoint.identifier,
                    "reference",
                    400.0,
                    5,
                    "target_activation_burden",
                ),
                selected_source=source,
                selected_branch=None,
            )
            selection = FinalSelectionRecord(
                endpoint=endpoint,
                selection_status="final_model_realized",
                final_model=final,
                reason_codes=("primary_realized",),
                causal_task_ids=("task_source",),
            )
            outcome = array(
                "outcome.npy",
                outcome_values,
                "outcome",
                (subject_axis,),
                "score",
            )
            baseline = array(
                "baseline.npy",
                baseline_values,
                "baseline",
                (subject_axis,),
                "score",
            )
            endpoint_input = EndpointInputRecord(
                endpoint=endpoint,
                readiness_status="ready",
                candidate_subject_ids=tuple(
                    f"subject-{index:02d}" for index in range(subjects)
                ),
                included_subject_ids=tuple(
                    f"subject-{index:02d}" for index in range(subjects)
                ),
                exclusions=(),
                minimum_subjects=12,
                subject_axis=subject_axis,
                baseline=baseline,
                outcome=outcome,
            )
            total_counts = np.full((subjects, 2, 17), 100, dtype=np.int64)
            activated_counts = np.full(
                (1, subjects, 2, 17),
                25,
                dtype=np.int64,
            )
            fractions = activated_counts.astype(np.float64) / total_counts[None]
            side_burdens = np.full(
                (1, subjects, 2, 17),
                125.0,
                dtype=np.float64,
            )
            patient_burdens = np.mean(side_burdens, axis=2)
            patient_support = np.ones((1, subjects, 17), dtype=bool)
            prepared = PreparedTargetExposureRecord(
                endpoint=endpoint,
                subject_axis=subject_axis,
                target_axis=target_axis,
                side_axis=side_axis,
                tau_axis=tau_axis,
                target_ids=array(
                    "prepared_target_ids.npy",
                    target_values,
                    "prepared_target_ids",
                    (target_axis,),
                    "target_id",
                ),
                side_total_counts=array(
                    "side_total_counts.npy",
                    total_counts,
                    "side_total_counts",
                    (subject_axis, side_axis, target_axis),
                    "count",
                ),
                side_burdens=array(
                    "side_burdens.npy",
                    side_burdens,
                    "side_burdens",
                    (tau_axis, subject_axis, side_axis, target_axis),
                    "V/m",
                ),
                side_activated_counts=array(
                    "side_activated_counts.npy",
                    activated_counts,
                    "side_activated_counts",
                    (tau_axis, subject_axis, side_axis, target_axis),
                    "count",
                ),
                side_activated_fractions=array(
                    "side_activated_fractions.npy",
                    fractions,
                    "side_activated_fractions",
                    (tau_axis, subject_axis, side_axis, target_axis),
                    "fraction",
                ),
                patient_burdens=array(
                    "patient_burdens.npy",
                    patient_burdens,
                    "patient_burdens",
                    (tau_axis, subject_axis, target_axis),
                    "V/m",
                ),
                patient_support=array(
                    "patient_support.npy",
                    patient_support,
                    "patient_support",
                    (tau_axis, subject_axis, target_axis),
                    "binary",
                ),
                delta_reference_input_status="not_applicable",
                delta_reference_reason_code="not_applicable",
                auxiliary_readiness=None,
                reference_condition_patient_burdens=None,
                reference_condition_patient_support=None,
                addon_reference_component_patient_burdens=None,
                addon_reference_component_patient_support=None,
            )
            permutation = FormalResult(
                final_model_id=final.identifier,
                resampling_kind="permutation",
                technical_status="completed",
                artifacts=(
                    array(
                        "permutation_null.npy",
                        np.asarray([0.1, -0.1, 0.2, -0.2]),
                        "formal_permutation_null_statistics",
                        (replicate_axis,),
                        "spearman_rho",
                    ),
                    publisher.document(
                        "permutation_summary.json",
                        {
                            "resamples_requested": 4,
                            "finite_replicate_count": 4,
                            "seed": 42,
                            "p_plus_one_two_sided": 0.2,
                            "technical_status": "completed",
                            "observed": {
                                "loocv_spearman_rho": 0.5,
                                "loocv_spearman_nominal_p": 0.05,
                                "loocv_pearson_r": 0.5,
                                "loocv_pearson_nominal_p": 0.05,
                                "q2": 0.2,
                                "rmse_model": 1.0,
                                "mae_model": 0.8,
                                "rmse_baseline": 2.0,
                                "mae_baseline": 1.5,
                            },
                        },
                        kind="formal_permutation_summary",
                    ),
                ),
            )
            bootstrap = FormalResult(
                final_model_id=final.identifier,
                resampling_kind="bootstrap",
                technical_status="completed",
                artifacts=(
                    array(
                        "bootstrap_weights.npy",
                        np.asarray(
                            [
                                [0.8, -0.4, 0.2],
                                [0.7, -0.5, 0.1],
                                [0.9, -0.3, 0.3],
                                [0.8, -0.4, 0.2],
                            ]
                        ),
                        "formal_bootstrap_replicate_weights",
                        (replicate_axis, selected_axis),
                        "coefficient",
                    ),
                    publisher.document(
                        "bootstrap_summary.json",
                        {
                            "resamples_requested": 4,
                            "finite_replicate_count": 4,
                            "seed": 42,
                            "technical_status": "completed",
                        },
                        kind="formal_bootstrap_summary",
                    ),
                ),
            )
            in_sample_summary = {
                "scale_id": "scale_a",
                "model_family": "reference_individualized",
                "selected_tau": 400.0,
                "selected_coverage": 5,
                "final_branch": "reference",
                "technical_status": "completed",
                "in_sample": {
                    "in_sample_n_subjects_finite": subjects,
                    "in_sample_permutations_finite": 4,
                    "in_sample_spearman_rho": 0.7,
                    "in_sample_spearman_nominal_p": 0.01,
                    "in_sample_permutation_p_plus_one_two_sided": 0.2,
                    "in_sample_pearson_r": 0.7,
                    "in_sample_pearson_nominal_p": 0.01,
                    "in_sample_r2": 0.5,
                    "in_sample_relative_r2": 0.4,
                    "in_sample_rmse": 0.8,
                    "in_sample_mae": 0.6,
                    "in_sample_rmse_baseline": 2.0,
                    "in_sample_mae_baseline": 1.5,
                },
                "loocv": {
                    "loocv_n_subjects_finite": subjects,
                    "loocv_permutations_finite": 4,
                    "loocv_spearman_rho": 0.5,
                    "loocv_spearman_nominal_p": 0.05,
                    "loocv_permutation_p_plus_one_two_sided": 0.2,
                    "loocv_pearson_r": 0.5,
                    "loocv_pearson_nominal_p": 0.05,
                    "loocv_q2": 0.2,
                    "loocv_rmse_model": 1.0,
                    "loocv_mae_model": 0.8,
                    "loocv_rmse_baseline": 2.0,
                    "loocv_mae_baseline": 1.5,
                },
                "optimism_gaps": {
                    "spearman_optimism_gap": 0.2,
                    "pearson_optimism_gap": 0.2,
                    "r2_q2_gap": 0.2,
                    "rmse_optimism_gap": 0.2,
                    "mae_optimism_gap": 0.2,
                },
            }
            in_sample = FormalResult(
                final_model_id=final.identifier,
                resampling_kind="in_sample_permutation",
                technical_status="completed",
                artifacts=(
                    array(
                        "in_sample_model.npy",
                        prediction_values,
                        "in_sample_model_predictions",
                        (subject_axis,),
                        "score",
                    ),
                    array(
                        "in_sample_baseline.npy",
                        baseline_prediction_values,
                        "in_sample_baseline_predictions",
                        (subject_axis,),
                        "score",
                    ),
                    publisher.document(
                        "in_sample_summary.json",
                        in_sample_summary,
                        kind="formal_in_sample_summary",
                    ),
                ),
            )
            records = [
                (None, endpoint_input),
                (None, prepared),
                (None, selection),
                (None, permutation),
                (None, bootstrap),
                (None, in_sample),
            ]
            resolved = {
                "study": {"selected_scales": ["scale_a"]},
                "selection": {"models": ["reference_individualized"]},
                "individualized_seed_target": {
                    "source": {"tau_values": [400.0]},
                    "target_exposure": {
                        "activated_fiber_count_min": 20,
                        "activated_fiber_fraction_min": 0.05,
                    },
                    "tractography": {
                        "sides": ["lh", "rh"],
                        "target_ids": list(target_names),
                    },
                },
            }
            publication_writer = _CompleteMarkerWriter(
                output / "individualized_seed_target"
            )
            CanonicalPublisher()._publish_individualized(
                publication_writer,
                resolved,
                {"scale_a": {"label": "Scale A"}},
                {"endpoint": endpoint},
                {"endpoint": records},
                ("2026-07-30T00:00:00Z", "2026-07-30T01:00:00Z"),
            )

            published_root = output / "individualized_seed_target"
            self.assertFalse((published_root / "complete.json").exists())
            self.assertFalse((published_root / "scale_a/complete.json").exists())
            self.assertFalse((published_root / "artifact_index.csv").exists())
            with (published_root / "final_model_selection.csv").open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                selection_rows = list(csv.DictReader(handle))
            self.assertEqual(selection_rows[0]["fallback_used"], "True")
            published_targets = np.load(
                published_root
                / "scale_a/reference/resolver/target_ids.npy",
                allow_pickle=False,
            )
            self.assertEqual(tuple(published_targets.tolist()), target_names)
            report_summary = json.loads(
                (
                    published_root
                    / "scale_a/reference/report/summary.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(report_summary["sensitivity_extensions"], [])
            self.assertFalse(
                (published_root / "scale_a/reference/sensitivity").exists()
            )
            first_count = publication_writer.written_count
            resumed_writer = _CompleteMarkerWriter(published_root)
            CanonicalPublisher()._publish_individualized(
                resumed_writer,
                resolved,
                {"scale_a": {"label": "Scale A"}},
                {"endpoint": endpoint},
                {"endpoint": records},
                ("2026-07-30T00:00:00Z", "2026-07-30T01:00:00Z"),
            )
            self.assertGreater(first_count, 0)
            self.assertEqual(resumed_writer.written_count, 0)

    def test_addon_publication_also_closes_its_reference_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "individualized_seed_target"
            writer = _CompleteMarkerWriter(root)
            publisher = CanonicalPublisher()
            published_roles: list[str] = []

            def publish_endpoint(
                _self: CanonicalPublisher,
                _writer: _CompleteMarkerWriter,
                records: list[tuple[object, object]],
                _profile: object,
            ) -> tuple[dict[str, object], dict[str, object]]:
                role = str(records[0][1])
                published_roles.append(role)
                row = {
                    "scale_id": "scale_a",
                    "model_family": "individualized_seed_target",
                    "role": role,
                }
                return row, row

            publisher._publish_individualized_endpoint = MethodType(
                publish_endpoint,
                publisher,
            )
            publisher._publish_individualized(
                writer,
                {
                    "study": {"selected_scales": ["scale_a"]},
                    "selection": {"models": ["addon_individualized"]},
                    "individualized_seed_target": {},
                },
                {"scale_a": {"label": "Scale A"}},
                {
                    "reference": SimpleNamespace(
                        scale_id="scale_a",
                        model_family="reference_individualized",
                    ),
                    "addon": SimpleNamespace(
                        scale_id="scale_a",
                        model_family="addon_individualized",
                    ),
                },
                {
                    "reference": [(None, "reference")],
                    "addon": [(None, "addon")],
                },
                ("2026-08-05T00:00:00Z", "2026-08-05T01:00:00Z"),
            )

            self.assertEqual(published_roles, ["reference", "addon"])
            manifest = json.loads(
                (root / "model_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["roles"], ["reference", "addon"])

    def test_jitter_keeps_the_final_cell_and_records_noncomputable_replicates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                publisher,
                artifact_store,
                final,
                subject_axis,
                target_axis,
                tau_axis,
                target_ids,
                exposure,
                support,
                outcome,
                baseline,
            ) = _target_fixture(root)
            exposure_values = np.asarray(
                artifact_store.materialize(
                    exposure,
                    expected_dtype=exposure.dtype,
                    expected_shape=exposure.shape,
                    expected_axes=exposure.axis_refs,
                    expected_units=exposure.units,
                    expected_space=exposure.space,
                )
            )
            support_values = np.asarray(
                artifact_store.materialize(
                    support,
                    expected_dtype=support.dtype,
                    expected_shape=support.shape,
                    expected_axes=support.axis_refs,
                    expected_units=support.units,
                    expected_space=support.space,
                )
            )
            burdens = publisher.array(
                "tau_burdens.npy",
                exposure_values[None, :, :],
                kind="individualized_patient_burdens",
                axes=(tau_axis, subject_axis, target_axis),
                units="V/m",
                space="individualized_target",
            )
            target_support = publisher.array(
                "tau_support.npy",
                support_values[None, :, :],
                kind="individualized_patient_support",
                axes=(tau_axis, subject_axis, target_axis),
                units="binary",
                space="individualized_target",
            )
            observed_request = TargetObservedRequest(
                endpoint=final.endpoint,
                branch="reference",
                patient_burdens=burdens,
                patient_support=target_support,
                outcome=outcome,
                baseline=baseline,
                nuisance_inputs=(),
                subject_axis=subject_axis,
                target_axis=target_axis,
                tau_axis=tau_axis,
                target_ids=target_ids,
                source_grid=SourceGrid(
                    pre_specified_tau=400.0,
                    pre_specified_coverage=5,
                    tau_values=(400.0,),
                    coverage_values=(5,),
                    minimum_adjacent_passing_cells=0,
                ),
                outcome_direction="lower",
                hard_computability=HardComputabilityLimits(12, 1, 1),
                score_settings=TargetScoreSettings(
                    exposure_scaling="training_fold_zscore",
                    normalization="sum_absolute_target_weights",
                ),
            )

            class ReplicateProvider:
                @staticmethod
                def replicate_indices() -> tuple[int, ...]:
                    return (1, 0)

                def build_replicate(
                    self,
                    *,
                    replicate_index: int,
                    replicate_seed: int,
                ) -> TargetJitterReplicateEvidence:
                    if replicate_index == 1:
                        return TargetJitterReplicateEvidence(
                            observed_request=None,
                            replicate_index=replicate_index,
                            replicate_seed=replicate_seed,
                            technical_status="not_computable",
                            reason="synthetic_missing_support",
                        )
                    return TargetJitterReplicateEvidence(
                        observed_request=observed_request,
                        replicate_index=replicate_index,
                        replicate_seed=replicate_seed,
                    )

            result = IndividualizedTargetSpatialJitterBackend(
                publisher,
                artifact_store=artifact_store,
            ).run(
                IndividualizedTargetJitterRequest(
                    final_model=final,
                    observed_request=observed_request,
                    settings=SpatialJitterSettings(
                        replicates=2,
                        seed=42,
                        translation_fwhm_mm=2.0,
                    ),
                    replicate_provider=ReplicateProvider(),
                )
            )
            null_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "individualized_target_jitter_statistics"
            )
            null = np.asarray(
                artifact_store.materialize(
                    null_ref,
                    expected_dtype=null_ref.dtype,
                    expected_shape=null_ref.shape,
                    expected_axes=null_ref.axis_refs,
                    expected_units=null_ref.units,
                    expected_space=null_ref.space,
                )
            )
            self.assertTrue(np.isfinite(null[0]))
            self.assertTrue(np.isnan(null[1]))


if __name__ == "__main__":
    unittest.main()
