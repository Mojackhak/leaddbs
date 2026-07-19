"""Final-only formal inference contract and deterministic numerical tests."""

from __future__ import annotations

import csv
from concurrent.futures import ProcessPoolExecutor
import dataclasses
import hashlib
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote, urlsplit

import numpy as np

import dual_frequency.backends as public_backends
import dual_frequency.backends.normative_fiber.scoring as scoring_module
import dual_frequency.backends.protocols as backend_protocols
import dual_frequency.backends.statistics as statistics_module
import dual_frequency.contracts as public_contracts
import dual_frequency.contracts.requests as request_contracts
from dual_frequency.backends.formal import (
    DirectVoxelFormalBackend,
    FormalBackendError,
    FormalBackendInputError,
    NormativeFiberFormalBackend,
    compute_direct_voxel_bootstrap,
    compute_direct_voxel_bootstrap_block,
    compute_direct_voxel_permutation,
    compute_direct_voxel_permutation_block,
    compute_normative_fiber_bootstrap,
    compute_normative_fiber_bootstrap_block,
    compute_normative_fiber_permutation,
    compute_normative_fiber_permutation_block,
)
from dual_frequency.backends.formal.common import (
    BootstrapBlockComputation,
    BootstrapReplicateNotEstimableError,
    PermutationBlockComputation,
    PermutationComputation,
    ReplicateBlock,
    StreamingBootstrapAccumulator,
    build_bootstrap_nuisance_plan,
    build_fixed_nuisance_plan,
    combine_bootstrap_blocks,
    combine_permutation_blocks,
    fixed_replicate_blocks,
    formal_resampling_schedule,
)
from dual_frequency.backends.protocols import BootstrapNuisanceSampleNotEstimableError
from dual_frequency.backends.statistics import (
    partial_spearman_weights,
    partial_spearman_weights_complete,
)
from dual_frequency.backends.formal.direct_voxel import (
    _build_fold_operators as _build_direct_fold_operators,
    _optimized_loocv as _optimized_direct_loocv,
    open_direct_voxel_operator_scratch,
    _publish_direct_voxel_operator_scratch,
)
from dual_frequency.backends.formal.normative_fiber import (
    _build_fold_operators as _build_fiber_fold_operators,
    _fold_candidate_masks,
    _loocv as _fiber_loocv,
    open_normative_fiber_operator_scratch,
    _publish_normative_fiber_operator_scratch,
)
from dual_frequency.backends.formal.operator_scratch import (
    OperatorScratchError,
    cleanup_operator_scratch,
    close_operator_scratch,
)
from dual_frequency.backends.normative_fiber.coverage import coverage_counts
from dual_frequency.cache import (
    ArtifactStore,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BootstrapNuisanceEvidence,
    BootstrapRebuildProvenance,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointKey,
    EndpointInputRecord,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    FormalOperatorScratchRecord,
    FormalRequest,
    FormalResult,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    PreparedExposureRecord,
    RequestError,
    ResamplingBlockRecord,
    ResamplingScheduleRecord,
    SourceRecord,
    TaskKey,
)
from dual_frequency.runtime.formal_operator_workspace import (
    cleanup_formal_operator_scratch_record,
    formal_operator_input_identity,
    formal_operator_scratch_descriptor,
    formal_operator_scratch_record,
    validated_formal_operator_scratch_descriptor,
    validate_formal_operator_scratch_record,
)
from dual_frequency.runtime.formal_resampling import (
    FormalResamplingError,
    load_formal_resampling_schedule,
    publish_formal_resampling_schedule,
)
from dual_frequency.runtime.formal_bootstrap_blocks import (
    FormalBootstrapBlockError,
    load_formal_bootstrap_block,
    publish_formal_bootstrap_block,
)
from dual_frequency.runtime.service_adapters import build_default_service_registry
from dual_frequency.workflow.executor import DependencyState, TaskExecutionRequest
from dual_frequency.workflow.planner import TaskSpec


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


def _spawn_reopen_operator_scratch(descriptor: object) -> tuple[bool, int]:
    from dual_frequency.backends.formal.operator_scratch import (
        close_operator_scratch,
        open_operator_scratch,
    )

    arrays = open_operator_scratch(descriptor)
    try:
        valid = all(
            isinstance(value, np.memmap) and not value.flags.writeable
            for value in arrays.values()
        )
        return valid, len(arrays)
    finally:
        close_operator_scratch(arrays)


class ResamplingScheduleBlockTest(unittest.TestCase):
    def test_permutation_blocks_reassemble_historical_default_rng_bytes(self) -> None:
        generator = np.random.default_rng(42)
        expected = np.vstack(
            [generator.permutation(16) for _ in range(11)]
        ).astype(np.int32)
        schedule = formal_resampling_schedule("permutation", 16, 11, 42)
        blocks = schedule.blocks(block_size=4)
        self.assertEqual(
            tuple((block.start, block.stop) for block in blocks),
            ((0, 4), (4, 8), (8, 11)),
        )
        shuffled = (blocks[2], blocks[0], blocks[1])
        restored = np.concatenate(
            [schedule.block_view(block) for block in sorted(shuffled, key=lambda x: x.index)]
        )
        self.assertEqual(restored.tobytes(order="C"), expected.tobytes(order="C"))
        self.assertFalse(schedule.indices.flags.writeable)
        self.assertTrue(schedule.descriptor.bit_generator_class.endswith(".PCG64"))

    def test_bootstrap_blocks_reassemble_historical_single_integers_call(self) -> None:
        expected = np.random.default_rng(73).integers(
            0,
            12,
            size=(13, 12),
            dtype=np.int64,
        )
        schedule = formal_resampling_schedule("bootstrap", 12, 13, 73)
        blocks = fixed_replicate_blocks(13, block_size=5)
        restored = np.concatenate(
            [schedule.block_view(block) for block in blocks]
        )
        self.assertEqual(restored.tobytes(order="C"), expected.tobytes(order="C"))
        self.assertEqual(blocks[-1].count, 3)
        self.assertEqual(
            schedule.descriptor.schedule_sha256,
            formal_resampling_schedule("bootstrap", 12, 13, 73).descriptor.schedule_sha256,
        )


class DurableBootstrapBlockTest(unittest.TestCase):
    @staticmethod
    def _assert_block_equal(
        expected: BootstrapBlockComputation,
        actual: BootstrapBlockComputation,
    ) -> None:
        for field in dataclasses.fields(expected):
            left = getattr(expected, field.name)
            right = getattr(actual, field.name)
            if isinstance(left, np.ndarray):
                np.testing.assert_array_equal(right, left)
            else:
                if right != left:
                    raise AssertionError(f"bootstrap block field differs: {field.name}")

    def _compute_block(
        self,
        request: FormalRequest,
        schedule: object,
    ) -> BootstrapBlockComputation:
        exposure = _artifact_value(request.exposure)
        outcome = _artifact_value(request.outcome)
        baseline = _artifact_value(request.baseline)
        block = schedule.blocks()[0]
        if request.final_model.endpoint.model_family.endswith("fiber"):
            return compute_normative_fiber_bootstrap_block(
                request,
                exposure,
                _artifact_value(request.feature_ids),
                outcome,
                baseline,
                None,
                schedule,
                block,
            )
        return compute_direct_voxel_bootstrap_block(
            request,
            exposure,
            outcome,
            baseline,
            None,
            schedule,
            block,
        )

    def test_direct_and_fiber_blocks_publish_reopen_and_preserve_exact_state(self) -> None:
        for model_family, expected_selection, expected_count in (
            ("reference_voxel", "none", 10),
            ("reference_fiber", "sweet_sour", 12),
        ):
            with (
                self.subTest(model_family=model_family),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                request = _formal_request(
                    model_family,
                    "bootstrap",
                    resamples=3,
                    seed=97,
                )
                schedule_record = publish_formal_resampling_schedule(
                    request,
                    RunScopedArtifactPublisher(root, "schedule", "1"),
                )
                store = ArtifactStore((root,))
                schedule = load_formal_resampling_schedule(
                    schedule_record,
                    request,
                    store,
                )
                computed = self._compute_block(request, schedule)
                record = publish_formal_bootstrap_block(
                    computed,
                    schedule_record,
                    request.feature_axis,
                    request.exposure.space,
                    RunScopedArtifactPublisher(root, "block", "1"),
                )
                self.assertEqual(record.selection_mode, expected_selection)
                self.assertEqual(len(record.artifacts), expected_count)
                self.assertNotIn(
                    (request.resamples, request.feature_axis.count),
                    tuple(
                        artifact.shape
                        for artifact in record.artifacts
                        if artifact.shape is not None
                    ),
                )
                restored = load_formal_bootstrap_block(
                    record,
                    schedule_record,
                    request.feature_axis,
                    request.exposure.space,
                    store,
                )
                self._assert_block_equal(computed, restored)

                changed_schedule = dataclasses.replace(
                    schedule_record,
                    schedule_sha256="0" * 64,
                )
                with self.assertRaisesRegex(
                    FormalBootstrapBlockError,
                    "parent schedule",
                ):
                    load_formal_bootstrap_block(
                        record,
                        changed_schedule,
                        request.feature_axis,
                        request.exposure.space,
                        store,
                    )
                with self.assertRaisesRegex(
                    FormalBootstrapBlockError,
                    "feature axis",
                ):
                    load_formal_bootstrap_block(
                        record,
                        schedule_record,
                        dataclasses.replace(
                            request.feature_axis,
                            axis_id="wrong_features",
                        ),
                        request.exposure.space,
                        store,
                    )
                first_artifact = record.artifacts[0]
                with self.assertRaisesRegex(
                    public_contracts.RecordError,
                    "closure",
                ):
                    dataclasses.replace(
                        record,
                        artifacts=(
                            dataclasses.replace(first_artifact, kind="wrong_kind"),
                            *record.artifacts[1:],
                        ),
                    )
                with self.assertRaisesRegex(
                    public_contracts.RecordError,
                    "artifact shape",
                ):
                    dataclasses.replace(
                        record,
                        artifacts=(
                            dataclasses.replace(
                                first_artifact,
                                shape=(request.feature_axis.count + 1,),
                            ),
                            *record.artifacts[1:],
                        ),
                    )
                _artifact_path(first_artifact).write_bytes(
                    _artifact_path(first_artifact).read_bytes() + b"corrupt"
                )
                with self.assertRaises(FormalBootstrapBlockError):
                    load_formal_bootstrap_block(
                        record,
                        schedule_record,
                        request.feature_axis,
                        request.exposure.space,
                        store,
                    )

    def test_adjusted_evidence_mode_round_trips_complete_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = _formal_request(
                "reference_voxel",
                "bootstrap",
                resamples=3,
                seed=101,
            )
            schedule_record = publish_formal_resampling_schedule(
                request,
                RunScopedArtifactPublisher(root, "schedule", "1"),
            )
            store = ArtifactStore((root,))
            schedule = load_formal_resampling_schedule(
                schedule_record,
                request,
                store,
            )
            computed = self._compute_block(request, schedule)
            adjusted = dataclasses.replace(
                computed,
                require_complete_nuisance_evidence=True,
                nuisance_evidence=tuple(
                    {
                        "replicate": replicate,
                        "support_status": "adequate",
                    }
                    for replicate in range(computed.block.start, computed.block.stop)
                ),
            )
            with self.assertRaisesRegex(
                FormalBackendError,
                "does not cover",
            ):
                dataclasses.replace(
                    adjusted,
                    nuisance_evidence=adjusted.nuisance_evidence[:-1],
                )
            record = publish_formal_bootstrap_block(
                adjusted,
                schedule_record,
                request.feature_axis,
                request.exposure.space,
                RunScopedArtifactPublisher(root, "adjusted_block", "1"),
            )
            self.assertEqual(record.nuisance_evidence_mode, "complete_adjusted")
            restored = load_formal_bootstrap_block(
                record,
                schedule_record,
                request.feature_axis,
                request.exposure.space,
                store,
            )
            self._assert_block_equal(adjusted, restored)


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


class _FormalServiceArrayStore:
    def __init__(self, run_root: Path) -> None:
        self._published = ArtifactStore((run_root,))

    def materialize(self, artifact: ArtifactRef, **requirements: object) -> np.ndarray:
        if artifact.identifier in _SCIENTIFIC_ARRAYS:
            return _ScientificArrayStore().materialize(artifact, **requirements)
        return self._published.materialize(artifact, **requirements)


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


class _FormalServiceProvider:
    def __init__(self, request: FormalRequest) -> None:
        self.request = request
        self.calls: list[str] = []

    def formal_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        publisher: object,
        *,
        resampling_kind: str,
        delta_reference: object | None,
    ) -> FormalRequest:
        del publisher
        if final_model != self.request.final_model:
            raise AssertionError("formal service passed a different final model")
        if endpoint_input.endpoint != final_model.endpoint:
            raise AssertionError("formal service passed a different endpoint input")
        if prepared.endpoint != final_model.endpoint:
            raise AssertionError("formal service passed a different prepared exposure")
        adjusted = self.request.delta_reference_full is not None
        if (
            resampling_kind != "permutation"
            or (delta_reference is not None) != adjusted
        ):
            raise AssertionError("formal predecessor requested the wrong resampling input")
        self.calls.append(resampling_kind)
        return self.request


def _formal_service_dependencies(
    request: FormalRequest,
) -> tuple[_FormalServiceProvider, dict[str, DependencyState]]:
    subject_ids = tuple(
        f"subject-{index:02d}" for index in range(request.subject_axis.count)
    )
    endpoint_input = EndpointInputRecord(
        endpoint=request.final_model.endpoint,
        readiness_status="ready",
        candidate_subject_ids=subject_ids,
        included_subject_ids=subject_ids,
        exclusions=(),
        minimum_subjects=request.hard_computability.n_subjects_min,
        subject_axis=request.subject_axis,
        baseline=request.baseline,
        outcome=request.outcome,
    )
    feature_ids = request.feature_ids
    if feature_ids is None:
        feature_ids = _scientific_artifact(
            "canonical_brainmask_voxel_ids",
            np.arange(request.feature_axis.count, dtype=np.int64),
            (request.feature_axis,),
            units="voxel_id",
            space=request.exposure_space,
        )
    is_reference = request.final_model.endpoint.model_family.startswith("reference_")
    auxiliary_readiness = None
    if not is_reference:
        auxiliary_readiness = ArtifactRef(
            kind="synthetic_auxiliary_readiness",
            schema_version="synthetic_v1",
            uri="memory://formal-fixture/auxiliary-readiness.json",
            sha256="8" * 64,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id="formal_fixture",
            producer_version="1",
        )
    prepared = PreparedExposureRecord(
        endpoint=request.final_model.endpoint,
        subject_axis=request.subject_axis,
        feature_axis=request.feature_axis,
        exposure=request.exposure,
        feature_ids=feature_ids,
        delta_reference_input_status=("not_applicable" if is_reference else "ready"),
        delta_reference_reason_code=("not_applicable" if is_reference else "ready"),
        auxiliary_readiness=auxiliary_readiness,
        reference_condition_exposure=(None if is_reference else request.exposure),
        addon_reference_component_exposure=(
            None if is_reference else request.exposure
        ),
        reference_overlap_mask=None,
        total_exposure=None,
    )
    selection = FinalSelectionRecord(
        endpoint=request.final_model.endpoint,
        selection_status=request.final_model.final_status,
        final_model=request.final_model,
        reason_codes=("primary_model_realized",),
        causal_task_ids=("task_fixture",),
    )
    dependencies = {
        "endpoint_input": DependencyState("completed", "none", endpoint_input),
        "prepared_exposure": DependencyState("completed", "none", prepared),
        "final_selection": DependencyState("completed", "none", selection),
    }
    if request.delta_reference_full is not None:
        assert request.delta_reference_folds is not None
        support_axis = _axis("delta_support_columns", 4, "d")
        support_rows = _scientific_artifact(
            "delta_reference_support_rows",
            np.ones((request.subject_axis.count, support_axis.count)),
            (request.subject_axis, support_axis),
            units="support",
            space="clinical",
        )
        support_qc = ArtifactRef(
            kind="delta_reference_support_qc",
            schema_version="synthetic_v1",
            uri="memory://formal-fixture/delta-support-qc.json",
            sha256="9" * 64,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id="formal_fixture",
            producer_version="1",
        )
        dependencies["delta_reference"] = DependencyState(
            "completed",
            "none",
            DeltaReferenceBundle(
                input_status="valid",
                support_status="adequate",
                selected_reference_tau=200.0,
                selected_reference_coverage=5,
                full_scores=request.delta_reference_full,
                fold_scores=request.delta_reference_folds,
                support_rows=support_rows,
                support_qc=support_qc,
            ),
        )
    return _FormalServiceProvider(request), dependencies


def _formal_service_task(
    request: FormalRequest,
    *,
    service_id: str,
    output_record_type: str,
    execution_parameters: tuple[tuple[str, str], ...] = (),
    dependency_ids: tuple[str, ...] = (
        "endpoint_input",
        "prepared_exposure",
        "final_selection",
    ),
) -> TaskSpec:
    parameter_identity = hashlib.sha256(
        repr((service_id, execution_parameters)).encode("utf-8")
    ).hexdigest()
    return TaskSpec(
        key=TaskKey(
            request.final_model.endpoint.identifier,
            service_id,
            "none",
            parameter_identity,
        ),
        endpoint_id=request.final_model.endpoint.identifier,
        model_family=request.final_model.endpoint.model_family,
        connectome_role=request.connectome_role,
        stage=service_id,
        round_id="formal_predecessor_test",
        phase="formal",
        service_id=service_id,
        dependencies=dependency_ids,
        gates=(),
        output_record_type=output_record_type,
        execution_parameters=execution_parameters,
    )


def _formal_service_execution_request(
    request: FormalRequest,
    *,
    service_id: str,
    output_record_type: str,
    run_root: Path,
    execution_parameters: tuple[tuple[str, str], ...] = (),
    additional_dependencies: dict[str, DependencyState] | None = None,
) -> tuple[TaskExecutionRequest, _FormalServiceProvider]:
    provider, dependencies = _formal_service_dependencies(request)
    dependencies.update(additional_dependencies or {})
    task = _formal_service_task(
        request,
        service_id=service_id,
        output_record_type=output_record_type,
        execution_parameters=execution_parameters,
        dependency_ids=tuple(dependencies),
    )
    return (
        TaskExecutionRequest(
            task=task,
            dependencies=dependencies,
            run_id="formal-predecessor-test",
            output_dir=run_root / "work" / task.task_id,
            provider=provider,
            artifact_store=_FormalServiceArrayStore(run_root),
            scientific_cache=None,
            allow_expensive_producers=False,
            workers=2,
        ),
        provider,
    )


def _artifact_path(artifact: ArtifactRef) -> Path:
    parsed = urlsplit(artifact.uri)
    if parsed.scheme != "file":
        raise AssertionError("test publisher did not return a local file artifact")
    return Path(unquote(parsed.path))


class FormalPredecessorServiceTest(unittest.TestCase):
    def test_schedule_and_operator_services_preserve_typed_boundaries(self) -> None:
        registry = build_default_service_registry()
        backend_types = {
            "reference_voxel": (
                DirectVoxelFormalBackend,
                "reference",
                "dual_frequency.backends.formal.direct_voxel._build_fold_operators",
            ),
            "reference_fiber": (
                NormativeFiberFormalBackend,
                "reference",
                "dual_frequency.backends.formal.normative_fiber._build_fold_operators",
            ),
            "addon_voxel": (
                DirectVoxelFormalBackend,
                "delta_reference_adjusted",
                "dual_frequency.backends.formal.direct_voxel._build_fold_operators",
            ),
            "addon_fiber": (
                NormativeFiberFormalBackend,
                "delta_reference_adjusted",
                "dual_frequency.backends.formal.normative_fiber._build_fold_operators",
            ),
        }
        for model_family, (backend_type, branch, builder_target) in backend_types.items():
            with (
                self.subTest(model_family=model_family),
                tempfile.TemporaryDirectory() as temporary,
            ):
                run_root = Path(temporary)
                formal_request = _formal_request(
                    model_family,
                    "permutation",
                    branch=branch,
                    resamples=11,
                    seed=73,
                )
                if branch == "delta_reference_adjusted":
                    subject_index = np.arange(
                        formal_request.subject_axis.count,
                        dtype=np.float64,
                    )
                    delta_full = (
                        np.sin(1.7 * subject_index)
                        + 0.2 * np.cos(0.6 * subject_index)
                    )
                    delta_folds = np.broadcast_to(
                        delta_full,
                        (
                            formal_request.subject_axis.count,
                            formal_request.subject_axis.count,
                        ),
                    ).copy()
                    formal_request = dataclasses.replace(
                        formal_request,
                        delta_reference_full=_scientific_artifact(
                            f"{model_family}_service_delta_full",
                            delta_full,
                            (formal_request.subject_axis,),
                            units="score",
                            space="clinical",
                        ),
                        delta_reference_folds=_scientific_artifact(
                            f"{model_family}_service_delta_folds",
                            delta_folds,
                            (
                                formal_request.subject_axis,
                                formal_request.subject_axis,
                            ),
                            units="score",
                            space="clinical",
                        ),
                    )
                schedule_request, schedule_provider = (
                    _formal_service_execution_request(
                        formal_request,
                        service_id="prepare_formal_permutation_schedule",
                        output_record_type="ResamplingScheduleRecord",
                        run_root=run_root,
                    )
                )
                schedule_result = registry.resolve(
                    "prepare_formal_permutation_schedule"
                )(schedule_request)
                schedule_record = schedule_result.decode_record()
                self.assertIsInstance(schedule_record, ResamplingScheduleRecord)
                self.assertNotIsInstance(schedule_record, FormalResult)
                self.assertEqual(schedule_provider.calls, ["permutation"])
                restored = load_formal_resampling_schedule(
                    schedule_record,
                    formal_request,
                    ArtifactStore((run_root,)),
                )
                expected = formal_resampling_schedule(
                    "permutation",
                    formal_request.subject_axis.count,
                    formal_request.resamples,
                    formal_request.seed,
                )
                self.assertEqual(
                    restored.indices.tobytes(order="C"),
                    expected.indices.tobytes(order="C"),
                )
                altered_digest = (
                    "f" * 64
                    if schedule_record.schedule_sha256 != "f" * 64
                    else "e" * 64
                )
                with self.assertRaises(FormalResamplingError):
                    load_formal_resampling_schedule(
                        dataclasses.replace(
                            schedule_record,
                            schedule_sha256=altered_digest,
                        ),
                        formal_request,
                        ArtifactStore((run_root,)),
                    )

                workspace_request, workspace_provider = (
                    _formal_service_execution_request(
                        formal_request,
                        service_id="prepare_formal_operator_workspace",
                        output_record_type="FormalOperatorScratchRecord",
                        run_root=run_root,
                    )
                )
                with mock.patch.object(
                    backend_type,
                    "run_formal",
                    side_effect=AssertionError("formal fit must not run"),
                ) as formal_fit:
                    workspace_result = registry.resolve(
                        "prepare_formal_operator_workspace"
                    )(workspace_request)
                formal_fit.assert_not_called()
                workspace_record = workspace_result.decode_record()
                self.assertIsInstance(
                    workspace_record,
                    FormalOperatorScratchRecord,
                )
                self.assertNotIsInstance(workspace_record, FormalResult)
                self.assertEqual(workspace_provider.calls, ["permutation"])
                validate_formal_operator_scratch_record(
                    workspace_record,
                    run_root,
                )

                predecessor_dependencies = {
                    "schedule": DependencyState(
                        "completed",
                        "none",
                        schedule_record,
                    ),
                    "scratch": DependencyState(
                        "completed",
                        "none",
                        workspace_record,
                    ),
                }
                block_request, block_provider = _formal_service_execution_request(
                    formal_request,
                    service_id="run_formal_permutation_block",
                    output_record_type="ResamplingBlockRecord",
                    run_root=run_root,
                    execution_parameters=(("block_index", "0"),),
                    additional_dependencies=predecessor_dependencies,
                )
                with mock.patch(
                    builder_target,
                    side_effect=AssertionError("fold operators must not rebuild"),
                ) as operator_builder:
                    block_result = registry.resolve(
                        "run_formal_permutation_block"
                    )(block_request)
                operator_builder.assert_not_called()
                block_record = block_result.decode_record()
                self.assertIsInstance(block_record, ResamplingBlockRecord)
                self.assertEqual(block_provider.calls, ["permutation"])

                aggregate_request, aggregate_provider = (
                    _formal_service_execution_request(
                        formal_request,
                        service_id="aggregate_formal_permutation",
                        output_record_type="FormalResult",
                        run_root=run_root,
                        additional_dependencies={
                            **predecessor_dependencies,
                            "block_000": DependencyState(
                                "completed",
                                "none",
                                block_record,
                            ),
                        },
                    )
                )
                with mock.patch(
                    builder_target,
                    side_effect=AssertionError("fold operators must not rebuild"),
                ) as operator_builder:
                    aggregate_result = registry.resolve(
                        "aggregate_formal_permutation"
                    )(aggregate_request)
                operator_builder.assert_not_called()
                final_result = aggregate_result.decode_record()
                self.assertIsInstance(final_result, FormalResult)
                self.assertTrue(aggregate_result.fact_values["formal_complete"])
                self.assertEqual(aggregate_provider.calls, ["permutation"])
                artifact_kinds = {artifact.kind for artifact in final_result.artifacts}
                self.assertIn("formal_resampling_schedule", artifact_kinds)
                self.assertNotIn("formal_permutation_schedule", artifact_kinds)
                self.assertTrue(
                    formal_operator_scratch_descriptor(
                        workspace_record,
                        run_root,
                    ).root.is_dir()
                )
                cleanup_formal_operator_scratch_record(workspace_record, run_root)

    def test_two_block_services_match_serial_and_reject_missing_interval(self) -> None:
        registry = build_default_service_registry()
        cases = {
            "reference_voxel": (
                DirectVoxelFormalBackend,
                "dual_frequency.backends.formal.direct_voxel._build_fold_operators",
            ),
            "reference_fiber": (
                NormativeFiberFormalBackend,
                "dual_frequency.backends.formal.normative_fiber._build_fold_operators",
            ),
        }
        exposure = _synthetic_arrays(n_subjects=12, n_features=20)[0]
        for model_family, (backend_type, builder_target) in cases.items():
            with (
                self.subTest(model_family=model_family),
                tempfile.TemporaryDirectory() as temporary,
            ):
                run_root = Path(temporary)
                formal_request = _formal_request(
                    model_family,
                    "permutation",
                    resamples=251,
                    seed=91,
                    exposure=exposure,
                )
                serial = backend_type(
                    RunScopedArtifactPublisher(
                        run_root / "serial",
                        "serial_formal",
                        "1",
                    ),
                    artifact_store=_ScientificArrayStore(),
                ).run_formal(formal_request)

                schedule_request, _provider = _formal_service_execution_request(
                    formal_request,
                    service_id="prepare_formal_permutation_schedule",
                    output_record_type="ResamplingScheduleRecord",
                    run_root=run_root,
                )
                schedule_record = registry.resolve(
                    "prepare_formal_permutation_schedule"
                )(schedule_request).decode_record()
                self.assertIsInstance(schedule_record, ResamplingScheduleRecord)
                workspace_request, _provider = _formal_service_execution_request(
                    formal_request,
                    service_id="prepare_formal_operator_workspace",
                    output_record_type="FormalOperatorScratchRecord",
                    run_root=run_root,
                )
                workspace_record = registry.resolve(
                    "prepare_formal_operator_workspace"
                )(workspace_request).decode_record()
                self.assertIsInstance(
                    workspace_record,
                    FormalOperatorScratchRecord,
                )
                predecessors = {
                    "schedule": DependencyState(
                        "completed",
                        "none",
                        schedule_record,
                    ),
                    "scratch": DependencyState(
                        "completed",
                        "none",
                        workspace_record,
                    ),
                }
                block_records: list[ResamplingBlockRecord] = []
                with mock.patch(
                    builder_target,
                    side_effect=AssertionError("fold operators must not rebuild"),
                ) as operator_builder:
                    for block_index in range(2):
                        block_request, _provider = (
                            _formal_service_execution_request(
                                formal_request,
                                service_id="run_formal_permutation_block",
                                output_record_type="ResamplingBlockRecord",
                                run_root=run_root,
                                execution_parameters=(
                                    ("block_index", str(block_index)),
                                ),
                                additional_dependencies=predecessors,
                            )
                        )
                        block_record = registry.resolve(
                            "run_formal_permutation_block"
                        )(block_request).decode_record()
                        self.assertIsInstance(
                            block_record,
                            ResamplingBlockRecord,
                        )
                        block_records.append(block_record)
                operator_builder.assert_not_called()

                missing_request, _provider = _formal_service_execution_request(
                    formal_request,
                    service_id="aggregate_formal_permutation",
                    output_record_type="FormalResult",
                    run_root=run_root,
                    additional_dependencies={
                        **predecessors,
                        "block_000": DependencyState(
                            "completed",
                            "none",
                            block_records[0],
                        ),
                    },
                )
                with self.assertRaises(FormalBackendError):
                    registry.resolve("aggregate_formal_permutation")(
                        missing_request
                    )

                mismatched_request, _provider = (
                    _formal_service_execution_request(
                        formal_request,
                        service_id="aggregate_formal_permutation",
                        output_record_type="FormalResult",
                        run_root=run_root,
                        additional_dependencies={
                            **predecessors,
                            "block_000": DependencyState(
                                "completed",
                                "none",
                                dataclasses.replace(
                                    block_records[0],
                                    schedule_id="different_schedule",
                                ),
                            ),
                            "block_001": DependencyState(
                                "completed",
                                "none",
                                block_records[1],
                            ),
                        },
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "parent schedule"):
                    registry.resolve("aggregate_formal_permutation")(
                        mismatched_request
                    )

                aggregate_request, _provider = _formal_service_execution_request(
                    formal_request,
                    service_id="aggregate_formal_permutation",
                    output_record_type="FormalResult",
                    run_root=run_root,
                    additional_dependencies={
                        **predecessors,
                        "block_001": DependencyState(
                            "completed",
                            "none",
                            block_records[1],
                        ),
                        "block_000": DependencyState(
                            "completed",
                            "none",
                            block_records[0],
                        ),
                    },
                )
                with mock.patch(
                    builder_target,
                    side_effect=AssertionError("fold operators must not rebuild"),
                ) as operator_builder:
                    aggregate = registry.resolve(
                        "aggregate_formal_permutation"
                    )(aggregate_request).decode_record()
                operator_builder.assert_not_called()
                self.assertIsInstance(aggregate, FormalResult)

                serial_artifacts = {
                    artifact.kind: artifact for artifact in serial.artifacts
                }
                aggregate_artifacts = {
                    artifact.kind: artifact for artifact in aggregate.artifacts
                }
                np.testing.assert_array_equal(
                    np.load(
                        _artifact_path(
                            aggregate_artifacts[
                                "formal_permutation_null_statistics"
                            ]
                        ),
                        allow_pickle=False,
                    ),
                    np.load(
                        _artifact_path(
                            serial_artifacts[
                                "formal_permutation_null_statistics"
                            ]
                        ),
                        allow_pickle=False,
                    ),
                )
                aggregate_summary = json.loads(
                    _artifact_path(
                        aggregate_artifacts["formal_permutation_summary"]
                    ).read_text(encoding="utf-8")
                )
                serial_summary = json.loads(
                    _artifact_path(
                        serial_artifacts["formal_permutation_summary"]
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    aggregate_summary["observed"],
                    serial_summary["observed"],
                )
                self.assertEqual(
                    aggregate_summary["p_plus_one_two_sided"],
                    serial_summary["p_plus_one_two_sided"],
                )
                cleanup_formal_operator_scratch_record(workspace_record, run_root)

    def test_workspace_service_retains_generation_after_record_failure(self) -> None:
        formal_request = _formal_request(
            "reference_voxel",
            "permutation",
            resamples=3,
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            execution_request, _provider = _formal_service_execution_request(
                formal_request,
                service_id="prepare_formal_operator_workspace",
                output_record_type="FormalOperatorScratchRecord",
                run_root=run_root,
            )
            with mock.patch(
                "dual_frequency.runtime.service_adapters."
                "formal_operator_scratch_record",
                side_effect=RuntimeError("synthetic record failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic record failure"):
                    build_default_service_registry().resolve(
                        "prepare_formal_operator_workspace"
                    )(execution_request)
            generations = tuple(
                execution_request.output_dir.glob("operator-generation-*")
            )
            self.assertEqual(len(generations), 1)
            self.assertTrue(tuple(generations[0].glob("*.npy")))


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


class FormalOperatorScratchTest(unittest.TestCase):
    @staticmethod
    def _assert_metrics_equal(
        expected: dict[str, float],
        actual: dict[str, float],
    ) -> None:
        if set(expected) != set(actual):
            raise AssertionError("operator scratch changed metric fields")
        for key in expected:
            np.testing.assert_allclose(
                actual[key],
                expected[key],
                rtol=0.0,
                atol=0.0,
                equal_nan=True,
                err_msg=key,
            )

    def test_operator_identity_ignores_task_path_but_not_content(self) -> None:
        request = _formal_request("reference_voxel", "permutation")
        republished = dataclasses.replace(
            request.exposure,
            uri="memory://different-task/selected-exposure.npy",
            producer_id="different_task",
            producer_version="99",
        )
        self.assertEqual(
            formal_operator_input_identity(request),
            formal_operator_input_identity(
                dataclasses.replace(request, exposure=republished)
            ),
        )
        changed = dataclasses.replace(republished, sha256="1" * 64)
        self.assertNotEqual(
            formal_operator_input_identity(request),
            formal_operator_input_identity(
                dataclasses.replace(request, exposure=changed)
            ),
        )

    def test_direct_operator_generation_reopens_read_only_with_exact_metrics(self) -> None:
        request = _formal_request("reference_voxel", "permutation")
        exposure = _artifact_value(request.exposure)
        outcome = _artifact_value(request.outcome)
        baseline = _artifact_value(request.baseline)
        nuisance = build_fixed_nuisance_plan(request, baseline, None, None)
        operators = _build_direct_fold_operators(request, exposure, nuisance)
        expected = _optimized_direct_loocv(outcome, operators)

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory)
            descriptor = _publish_direct_voxel_operator_scratch(
                run_root / "work" / "task_fixture",
                operators,
            )
            record = formal_operator_scratch_record(
                descriptor,
                request,
                run_root,
            )
            validate_formal_operator_scratch_record(record, run_root)
            self.assertEqual(
                validated_formal_operator_scratch_descriptor(
                    record,
                    request,
                    run_root,
                ),
                descriptor,
            )
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                validated_formal_operator_scratch_descriptor(
                    dataclasses.replace(record, input_identity="0" * 64),
                    request,
                    run_root,
                )
            self.assertEqual(
                formal_operator_scratch_descriptor(record, run_root),
                descriptor,
            )
            reopened, arrays = open_direct_voxel_operator_scratch(descriptor)
            try:
                self.assertTrue(
                    all(
                        isinstance(value, np.memmap) and not value.flags.writeable
                        for value in arrays.values()
                    )
                )
                self._assert_metrics_equal(
                    expected,
                    _optimized_direct_loocv(outcome, reopened),
                )
            finally:
                close_operator_scratch(arrays)

            with ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            ) as executor:
                reopened_in_spawn, array_count = executor.submit(
                    _spawn_reopen_operator_scratch,
                    descriptor,
                ).result(timeout=30)
            self.assertTrue(reopened_in_spawn)
            self.assertEqual(array_count, len(descriptor.arrays))

            untracked = descriptor.root / "untracked.txt"
            untracked.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(OperatorScratchError, "untracked"):
                cleanup_operator_scratch(descriptor)
            self.assertTrue(untracked.is_file())
            untracked.unlink()
            cleanup_operator_scratch(descriptor)
            self.assertFalse(descriptor.root.exists())

    def test_fiber_operator_generation_reopens_read_only_with_exact_metrics(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        exposure = _artifact_value(request.exposure)
        fiber_ids = _fiber_id_values(request)
        outcome = _artifact_value(request.outcome)
        baseline = _artifact_value(request.baseline)
        nuisance = build_fixed_nuisance_plan(request, baseline, None, None)
        masks = _fold_candidate_masks(request, exposure)
        operators = _build_fiber_fold_operators(
            request,
            exposure,
            nuisance,
            masks,
        )
        expected = _fiber_loocv(
            request,
            exposure,
            fiber_ids,
            outcome,
            nuisance,
            operators,
            scoring_module.PrevalidatedFiberScoreWorkspace(exposure, fiber_ids),
            optimized=True,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            descriptor = _publish_normative_fiber_operator_scratch(
                Path(temporary_directory),
                operators,
            )
            reopened, arrays = open_normative_fiber_operator_scratch(descriptor)
            try:
                self.assertTrue(
                    all(
                        isinstance(value, np.memmap) and not value.flags.writeable
                        for value in arrays.values()
                    )
                )
                actual = _fiber_loocv(
                    request,
                    exposure,
                    fiber_ids,
                    outcome,
                    nuisance,
                    reopened,
                    scoring_module.PrevalidatedFiberScoreWorkspace(
                        exposure,
                        fiber_ids,
                    ),
                    optimized=True,
                )
                self._assert_metrics_equal(expected, actual)
            finally:
                close_operator_scratch(arrays)
            cleanup_operator_scratch(descriptor)
            self.assertFalse(descriptor.root.exists())


class FormalPermutationTest(unittest.TestCase):
    def test_multi_block_permutations_match_unsplit_results_and_worker_order(self) -> None:
        for model_family in ("reference_voxel", "reference_fiber"):
            with self.subTest(model_family=model_family):
                request = _formal_request(model_family, "permutation")
                exposure = _artifact_value(request.exposure)
                outcome = _artifact_value(request.outcome)
                baseline = _artifact_value(request.baseline)
                nuisance = build_fixed_nuisance_plan(request, baseline, None, None)
                schedule = formal_resampling_schedule(
                    "permutation",
                    outcome.size,
                    request.resamples,
                    request.seed,
                )
                blocks = schedule.blocks(block_size=3)
                if model_family.endswith("voxel"):
                    full = compute_direct_voxel_permutation(
                        request,
                        exposure,
                        outcome,
                        nuisance,
                    )
                    results = tuple(
                        compute_direct_voxel_permutation_block(
                            request,
                            exposure,
                            outcome,
                            nuisance,
                            schedule,
                            block,
                        )
                        for block in blocks
                    )
                else:
                    fiber_ids = _fiber_id_values(request)
                    full = compute_normative_fiber_permutation(
                        request,
                        exposure,
                        fiber_ids,
                        outcome,
                        nuisance,
                    )
                    results = tuple(
                        compute_normative_fiber_permutation_block(
                            request,
                            exposure,
                            fiber_ids,
                            outcome,
                            nuisance,
                            schedule,
                            block,
                        )
                        for block in blocks
                    )
                combined = combine_permutation_blocks(
                    full.observed_metrics,
                    schedule,
                    tuple(reversed(results)),
                )
                np.testing.assert_allclose(
                    combined.null_statistics,
                    full.null_statistics,
                    rtol=0.0,
                    atol=0.0,
                    equal_nan=True,
                )
                self.assertEqual(
                    combined.p_plus_one_two_sided,
                    full.p_plus_one_two_sided,
                )

    def test_permutation_aggregator_rejects_missing_overlap_and_digest_change(self) -> None:
        schedule = formal_resampling_schedule("permutation", 4, 6, 19)
        blocks = schedule.blocks(block_size=2)
        results = tuple(
            PermutationBlockComputation(
                block=block,
                schedule_sha256=schedule.descriptor.schedule_sha256,
                null_statistics=np.arange(block.start, block.stop, dtype=np.float64),
            )
            for block in blocks
        )
        observed = {"loocv_spearman_rho": 0.5}
        with self.assertRaisesRegex(FormalBackendError, "invalid block"):
            combine_permutation_blocks(observed, schedule, (object(),))
        with self.assertRaisesRegex(FormalBackendError, "full schedule"):
            combine_permutation_blocks(observed, schedule, results[:-1])
        changed = dataclasses.replace(results[0], schedule_sha256="0" * 64)
        with self.assertRaisesRegex(FormalBackendError, "parent schedule"):
            combine_permutation_blocks(observed, schedule, (changed, *results[1:]))
        overlapping = PermutationBlockComputation(
            block=ReplicateBlock(index=1, start=1, stop=3, total=6),
            schedule_sha256=schedule.descriptor.schedule_sha256,
            null_statistics=np.array([1.0, 2.0]),
        )
        with self.assertRaisesRegex(FormalBackendError, "noncontiguous"):
            combine_permutation_blocks(
                observed,
                schedule,
                (results[0], overlapping, results[2]),
            )

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
        with mock.patch.object(
            scoring_module,
            "_validate_exposure",
            wraps=scoring_module._validate_exposure,
        ) as validate_exposure:
            optimized = compute_normative_fiber_permutation(
                request,
                exposure,
                fiber_ids,
                outcome,
                nuisance,
                optimized=True,
            )
        self.assertEqual(validate_exposure.call_count, 1)
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

    def test_direct_voxel_coverage_includes_values_equal_to_tau(self) -> None:
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
                operator.candidate_count == request.feature_axis.count
                for operator in operators
            )
        )

    def test_normative_fiber_coverage_includes_values_equal_to_tau(self) -> None:
        request = _formal_request("reference_fiber", "permutation")
        exposure = _artifact_value(request.exposure).copy()
        tau = float(request.final_model.final_key.selected_tau)
        exposure[:, 0] = tau
        self.assertEqual(int(coverage_counts(exposure, tau)[0]), exposure.shape[0])
        masks = _fold_candidate_masks(request, exposure)
        self.assertTrue(all(bool(mask[0]) for mask in masks))


class FormalBootstrapTest(unittest.TestCase):
    def test_complete_partial_spearman_matches_general_kernel(self) -> None:
        outcome = np.asarray([2, 4, 4, 7, 9, 10, 10, 13], dtype=np.float64)
        nuisance = np.asarray(
            [
                [1, 8],
                [1, 7],
                [2, 6],
                [3, 5],
                [3, 4],
                [5, 3],
                [8, 2],
                [13, 1],
            ],
            dtype=np.float64,
        )
        exposure = np.column_stack(
            (
                np.asarray([0, 0, 1, 1, 2, 3, 3, 5], dtype=np.float64),
                np.asarray([8, 7, 6, 5, 4, 3, 2, 1], dtype=np.float64),
                np.asarray([1, 3, 2, 5, 4, 8, 7, 6], dtype=np.float64),
            )
        )
        expected = statistics_module._partial_spearman_weights_scalar(
            outcome,
            exposure,
            nuisance,
        )
        complete = partial_spearman_weights_complete(outcome, exposure, nuisance)
        dispatched = partial_spearman_weights(outcome, exposure, nuisance)
        np.testing.assert_allclose(complete, expected, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(dispatched, expected, rtol=1e-12, atol=1e-12)

    def test_complete_partial_spearman_dispatch_uses_two_linear_solves(self) -> None:
        outcome = np.asarray([8, 2, 7, 3, 6, 4, 5, 1], dtype=np.float64)
        nuisance = np.arange(8, dtype=np.float64)[:, None]
        exposure = np.column_stack(
            tuple(
                np.roll(np.arange(8, dtype=np.float64), shift)
                for shift in range(5)
            )
        )
        original = np.linalg.lstsq
        with mock.patch.object(np.linalg, "lstsq", wraps=original) as solve:
            actual = partial_spearman_weights(outcome, exposure, nuisance)

        self.assertEqual(solve.call_count, 2)
        self.assertEqual(solve.call_args_list[0].args[1].shape, (8,))
        self.assertEqual(solve.call_args_list[1].args[1].shape, (8, 5))
        self.assertEqual(actual.shape, (5,))

    def test_partial_spearman_dispatch_preserves_scalar_fallbacks(self) -> None:
        outcome = np.asarray([1, 2, 2, 4, 5, 7, 7, 9], dtype=np.float64)
        base_exposure = np.column_stack(
            (
                np.asarray([3, 1, 4, 1, 5, 9, 2, 6], dtype=np.float64),
                np.ones(8, dtype=np.float64),
                np.asarray([8, 6, 7, 5, 3, 0, 9, 2], dtype=np.float64),
            )
        )
        finite_nuisance = np.arange(8, dtype=np.float64)[:, None]
        nonfinite_exposure = base_exposure.copy()
        nonfinite_exposure[3, 2] = np.nan
        rank_deficient_nuisance = np.column_stack(
            (finite_nuisance[:, 0], finite_nuisance[:, 0])
        )

        for exposure, nuisance in (
            (nonfinite_exposure, finite_nuisance),
            (base_exposure, rank_deficient_nuisance),
        ):
            with self.subTest(
                nonfinite=bool(np.any(~np.isfinite(exposure))),
                nuisance_columns=nuisance.shape[1],
            ):
                expected = statistics_module._partial_spearman_weights_scalar(
                    outcome,
                    exposure,
                    nuisance,
                )
                actual = partial_spearman_weights(outcome, exposure, nuisance)
                np.testing.assert_allclose(
                    actual,
                    expected,
                    rtol=1e-12,
                    atol=1e-12,
                    equal_nan=True,
                )

    def test_adjusted_provider_sample_failure_is_replicate_attrition(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)

        class NonEstimableProvider:
            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                del formal_request, sample_indices
                raise BootstrapNuisanceSampleNotEstimableError(
                    "sampled matched reference has no finite fold operator"
                )

        original_full, original_folds = _original_delta_values(request)
        with self.assertRaisesRegex(
            BootstrapReplicateNotEstimableError,
            "no finite fold operator",
        ):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                NonEstimableProvider(),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )

    def test_adjusted_bootstrap_accepts_mixed_rebuild_and_attrition_qc(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        delegate = _SyntheticBootstrapNuisanceProvider(
            _artifact_value(request.baseline)
        )

        class PartiallyNonEstimableProvider:
            def __init__(self) -> None:
                self.calls = 0

            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                self.calls += 1
                if self.calls == 1:
                    raise BootstrapNuisanceSampleNotEstimableError(
                        "sampled DeltaReferenceScore support is invalid"
                    )
                return delegate.build_bootstrap_nuisance(
                    formal_request,
                    sample_indices,
                )

        provider = PartiallyNonEstimableProvider()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backend = DirectVoxelFormalBackend(
                RunScopedArtifactPublisher(root, "formal_test", "1"),
                artifact_store=_ScientificArrayStore(),
                bootstrap_nuisance_provider=provider,
            )
            result = backend.run_formal(request)
            summary_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_bootstrap_summary"
            )
            summary = json.loads(
                _artifact_path(summary_ref).read_text(encoding="utf-8")
            )
            self.assertEqual(summary["finite_replicate_count"], 9)
            self.assertEqual(summary["nonestimable_nuisance_replicate_count"], 1)
            qc_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_bootstrap_nuisance_qc"
            )
            qc = json.loads(_artifact_path(qc_ref).read_text(encoding="utf-8"))
            self.assertEqual(len(qc["replicates"]), 9)
            self.assertEqual(len(qc["nonestimable_replicates"]), 1)
            self.assertEqual(qc["nonestimable_replicates"][0]["replicate"], 0)

    def test_adjusted_rebuilt_scaling_failure_is_replicate_attrition(self) -> None:
        request = _formal_request(
            "addon_voxel",
            "bootstrap",
            branch="delta_reference_adjusted",
        )
        sample = np.arange(request.subject_axis.count, dtype=np.int64)

        class ConstantScoreProvider:
            def build_bootstrap_nuisance(
                self,
                formal_request: FormalRequest,
                sample_indices: np.ndarray,
            ) -> BootstrapNuisanceEvidence:
                count = sample_indices.size
                full = np.full(count, 17.0, dtype=np.float64)
                folds = np.full((count, count), 17.0, dtype=np.float64)
                provenance = BootstrapRebuildProvenance.from_rebuild(
                    provider_id="constant_score_provider",
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

        original_full, original_folds = _original_delta_values(request)
        with self.assertRaisesRegex(
            BootstrapReplicateNotEstimableError,
            "constant or nonfinite",
        ):
            build_bootstrap_nuisance_plan(
                request,
                _artifact_value(request.baseline),
                sample,
                ConstantScoreProvider(),
                original_delta_full=original_full,
                original_delta_folds=original_folds,
            )

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

    def test_bootstrap_blocks_match_single_interval_in_reverse_order(self) -> None:
        for model_family in ("reference_voxel", "reference_fiber"):
            with self.subTest(model_family=model_family):
                request = _formal_request(
                    model_family,
                    "bootstrap",
                    resamples=251,
                    seed=83,
                )
                exposure = _artifact_value(request.exposure)
                outcome = _artifact_value(request.outcome)
                baseline = _artifact_value(request.baseline)
                schedule = formal_resampling_schedule(
                    "bootstrap",
                    request.subject_axis.count,
                    request.resamples,
                    request.seed,
                )
                if model_family.endswith("fiber"):
                    fiber_ids = _artifact_value(request.feature_ids)

                    def compute(block):
                        return compute_normative_fiber_bootstrap_block(
                            request,
                            exposure,
                            fiber_ids,
                            outcome,
                            baseline,
                            None,
                            schedule,
                            block,
                        )

                else:

                    def compute(block):
                        return compute_direct_voxel_bootstrap_block(
                            request,
                            exposure,
                            outcome,
                            baseline,
                            None,
                            schedule,
                            block,
                        )

                serial = combine_bootstrap_blocks(
                    schedule,
                    (compute(ReplicateBlock(0, 0, request.resamples, request.resamples)),),
                )
                canonical_blocks = tuple(compute(block) for block in schedule.blocks())
                self.assertEqual(
                    tuple(block.block.count for block in canonical_blocks),
                    (250, 1),
                )
                self.assertTrue(
                    all(
                        array.ndim == 1
                        for block in canonical_blocks
                        for array in (
                            block.weight_sum,
                            block.weight_square_sum,
                            block.replicate_candidate_count,
                        )
                    )
                )
                combined = combine_bootstrap_blocks(
                    schedule,
                    tuple(reversed(canonical_blocks)),
                )
                for field in dataclasses.fields(serial):
                    expected = getattr(serial, field.name)
                    actual = getattr(combined, field.name)
                    if isinstance(expected, np.ndarray):
                        if np.issubdtype(expected.dtype, np.floating):
                            np.testing.assert_allclose(
                                actual,
                                expected,
                                rtol=1e-13,
                                atol=1e-13,
                                equal_nan=True,
                            )
                        else:
                            np.testing.assert_array_equal(actual, expected)
                    else:
                        self.assertEqual(actual, expected)
                with self.assertRaisesRegex(
                    FormalBackendInputError,
                    "complete schedule",
                ):
                    combine_bootstrap_blocks(schedule, canonical_blocks[:-1])
                changed_digest = dataclasses.replace(
                    canonical_blocks[0],
                    schedule_sha256="0" * 64,
                )
                with self.assertRaisesRegex(
                    FormalBackendInputError,
                    "complete schedule",
                ):
                    combine_bootstrap_blocks(
                        schedule,
                        (changed_digest, *canonical_blocks[1:]),
                    )
                with self.assertRaisesRegex(
                    FormalBackendInputError,
                    "valid block state",
                ):
                    combine_bootstrap_blocks(schedule, (object(),))

    @staticmethod
    def _request_with_sample_specific_nuisance_attrition(
        model_family: str,
    ) -> FormalRequest:
        request = _formal_request(model_family, "bootstrap", resamples=6)
        baseline = np.array(
            [
                0.0,
                7.0,
                0.0,
                0.0,
                0.0,
                9.0,
                0.0,
                2.0,
                10.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ],
            dtype=np.float64,
        )
        return dataclasses.replace(
            request,
            baseline=_scientific_artifact(
                f"{model_family}_attrition_baseline",
                baseline,
                (request.subject_axis,),
                units="score",
                space="clinical",
            ),
        )

    def test_reference_bootstrap_records_sample_specific_nuisance_attrition(self) -> None:
        for model_family in ("reference_voxel", "reference_fiber"):
            with self.subTest(model_family=model_family):
                request = self._request_with_sample_specific_nuisance_attrition(
                    model_family
                )
                if model_family.endswith("fiber"):
                    result = compute_normative_fiber_bootstrap(
                        request,
                        _artifact_value(request.exposure),
                        _fiber_id_values(request),
                        _artifact_value(request.outcome),
                        _artifact_value(request.baseline),
                        None,
                    )
                else:
                    result = compute_direct_voxel_bootstrap(
                        request,
                        _artifact_value(request.exposure),
                        _artifact_value(request.outcome),
                        _artifact_value(request.baseline),
                        None,
                    )
                self.assertEqual(result.finite_replicate_count, 5)
                self.assertEqual(
                    result.nonestimable_replicates,
                    (
                        {
                            "replicate": 5,
                            "reason_code": "nonestimable_nuisance_design",
                            "detail": (
                                "fold nuisance-only design is not estimable "
                                "for held-out index 6"
                            ),
                        },
                    ),
                )
                self.assertGreater(int(result.replicate_candidate_count[5]), 0)
                self.assertEqual(int(result.replicate_valid_weight_count[5]), 0)
                self.assertEqual(int(result.replicate_support_code[5]), 0)

    def test_bootstrap_publication_reports_nonestimable_nuisance_draws(self) -> None:
        request = self._request_with_sample_specific_nuisance_attrition(
            "reference_voxel"
        )
        computation = compute_direct_voxel_bootstrap(
            request,
            _artifact_value(request.exposure),
            _artifact_value(request.outcome),
            _artifact_value(request.baseline),
            None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            backend = DirectVoxelFormalBackend(
                RunScopedArtifactPublisher(Path(temporary), "formal_test", "1")
            )
            result = backend._publish_bootstrap(request, computation)
            self.assertEqual(
                result.technical_status,
                "completed_with_nonfinite_replicates",
            )
            summary_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_bootstrap_summary"
            )
            summary = json.loads(
                _artifact_path(summary_ref).read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary["schema_version"],
                "formal_bootstrap_summary_v2",
            )
            self.assertEqual(summary["finite_replicate_count"], 5)
            self.assertEqual(summary["nonestimable_nuisance_replicate_count"], 1)
            qc_ref = next(
                artifact
                for artifact in result.artifacts
                if artifact.kind == "formal_bootstrap_nuisance_qc"
            )
            qc = json.loads(_artifact_path(qc_ref).read_text(encoding="utf-8"))
            self.assertEqual(
                qc["schema_version"],
                "formal_bootstrap_nuisance_qc_v2",
            )
            self.assertEqual(
                qc["nonestimable_replicates"],
                list(computation.nonestimable_replicates),
            )

    def test_bootstrap_rejects_nonestimable_original_nuisance_design(self) -> None:
        for model_family in ("reference_voxel", "reference_fiber"):
            with self.subTest(model_family=model_family):
                request = _formal_request(model_family, "bootstrap", resamples=2)
                request = dataclasses.replace(
                    request,
                    baseline=_scientific_artifact(
                        f"{model_family}_constant_baseline",
                        np.zeros(request.subject_axis.count, dtype=np.float64),
                        (request.subject_axis,),
                        units="score",
                        space="clinical",
                    ),
                )
                arguments = (
                    request,
                    _artifact_value(request.exposure),
                    _artifact_value(request.outcome),
                    _artifact_value(request.baseline),
                    None,
                )
                with self.assertRaisesRegex(
                    FormalBackendInputError,
                    "full nuisance-only design is not estimable",
                ):
                    if model_family.endswith("fiber"):
                        compute_normative_fiber_bootstrap(
                            request,
                            _artifact_value(request.exposure),
                            _fiber_id_values(request),
                            _artifact_value(request.outcome),
                            _artifact_value(request.baseline),
                            None,
                        )
                    else:
                        compute_direct_voxel_bootstrap(*arguments)

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
