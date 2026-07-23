"""Cache-first OSS row materialization and bounded fixture tests."""

from __future__ import annotations

import dataclasses
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
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
    OSSBackendError,
    OSSRowBatchRequest,
    OSSRowInput,
    OSSRowMaterializer,
    OSSRowProduct,
    OSSScientificSettings,
    PPAMActivationBackend,
    cleanup_ppam_operator_scratch,
    close_ppam_operator_scratch,
    binary_activation,
    build_oss_row_cache_key,
    compute_ppam_permutation_block,
    subset_probability_axis,
)
from dual_frequency.backends.formal.common import (
    FormalBackendError,
    ReplicateBlock,
    combine_permutation_blocks,
    formal_resampling_schedule,
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
    PPAMPermutationBlockRecord,
    PPAMObservedWorkspaceRecord,
    RecordError,
    ResamplingScheduleRecord,
    SourceRecord,
)
from dual_frequency.runtime.ppam_permutation_blocks import (
    PPAMPermutationBlockError,
    load_ppam_permutation_block,
    publish_ppam_permutation_block,
)
from dual_frequency.runtime.ppam_observed_workspace import (
    PPAMObservedWorkspaceError,
    cleanup_ppam_observed_workspace_record,
    load_ppam_observed_state,
    ppam_observed_workspace_record,
    publish_ppam_operator_scratch,
    reopen_ppam_workspace_from_record,
    validated_ppam_operator_scratch_descriptor,
)


def _materialize_artifact(
    store: ArtifactStore,
    artifact: ArtifactRef,
) -> np.ndarray:
    return store.materialize(
        artifact,
        expected_dtype=np.dtype(artifact.dtype),
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
        mmap_mode="r",
    )


def _spawn_reopen_ppam_workspace(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
    run_root: Path,
    schedule: object,
    block: ReplicateBlock,
) -> tuple[bool, np.ndarray]:
    """Reopen one durable pPAM workspace in a fresh spawned interpreter."""

    store = ArtifactStore((run_root,))
    binary = _materialize_artifact(store, binary_exposure)
    outcome = _materialize_artifact(store, request.outcome)
    fiber_ids = _materialize_artifact(store, request.feature_ids)
    workspace, arrays = reopen_ppam_workspace_from_record(
        record,
        request,
        binary_exposure,
        binary,
        outcome,
        fiber_ids,
        run_root,
    )
    try:
        readonly = all(
            isinstance(value, np.memmap) and not value.flags.writeable
            for value in arrays.values()
        )
        computed = ppam_fitting.compute_ppam_permutation_block_from_workspace(
            workspace,
            schedule,
            block,
        )
        return readonly, computed.null_statistics
    finally:
        close_ppam_operator_scratch(arrays)


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
    def test_v1_settings_reject_mutable_scientific_defaults(self) -> None:
        invalid_settings = (
            {"conductivity_model": "Constant"},
            {"conductivity_mode": "anisotropic"},
            {"patient_dti_enabled": True},
            {"axon_model": "MRG2002"},
            {"axon_length_mm": 20.0},
            {"waveform": "sine"},
            {"relative_phase": "variable"},
        )
        for changes in invalid_settings:
            with self.subTest(changes=changes), self.assertRaises(OSSBackendError):
                OSSScientificSettings(backend_version="2.2.0", **changes)

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

    def test_omega_simulation_rows_are_cropped_to_the_locked_final_axis(self) -> None:
        final_axis = AxisRef("final-fibers", 2, "1" * 64)
        final_ids = np.asarray([102, 104], dtype=np.int64)
        simulation_axis = AxisRef("omega-fibers", 5, "2" * 64)
        simulation_ids = np.arange(101, 106, dtype=np.int64)
        rows = _rows(self.subjects, simulation_axis, simulation_ids)

        def producer(row: OSSRowInput) -> OSSRowProduct:
            return OSSRowProduct(row.feature_ids, self._values(row))

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            batch = OSSRowMaterializer(
                ContentAddressedCache(root / "cache"),
                RunScopedArtifactPublisher(root / "run", "oss_test", "1"),
                producer=producer,
            ).materialize(
                OSSRowBatchRequest(
                    final_model=_final("scale-omega", final_axis),
                    connectome_role="formal",
                    subject_axis=self.subject_axis,
                    subject_ids=self.subjects,
                    feature_axis=final_axis,
                    feature_ids=final_ids,
                    rows=rows,
                    settings=OSSScientificSettings(backend_version="2.2.0"),
                    allow_expensive_producers=True,
                    simulation_feature_axis=simulation_axis,
                    simulation_feature_ids=simulation_ids,
                    workers=3,
                )
            )
            observed = _artifact_array(batch.activation_probability)
            observed_ids = _artifact_array(batch.feature_ids)
        full = np.stack(
            [
                np.maximum(
                    self._values(
                        next(
                            row
                            for row in rows
                            if row.subject_id == subject and row.side == "L"
                        )
                    ),
                    self._values(
                        next(
                            row
                            for row in rows
                            if row.subject_id == subject and row.side == "R"
                        )
                    ),
                )
                for subject in self.subjects
            ]
        )
        np.testing.assert_array_equal(observed, full[:, [1, 3]])
        np.testing.assert_array_equal(observed_ids, final_ids)

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
        self.assertEqual(max_active, 1)
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

    def _published_request(
        self,
        root: Path,
        request: ActivationRequest,
        binary: np.ndarray,
    ) -> tuple[ActivationRequest, ArtifactRef]:
        publisher = RunScopedArtifactPublisher(root, "ppam_inputs", "1")
        probability = publisher.array(
            "activation_probability.npy",
            np.asarray(request.activation_probability, dtype=np.float32),
            kind="activation_probability",
            axes=(self.subject_axis, self.feature_axis),
            units="probability",
            space="right_canonical",
        )
        binary_ref = publisher.array(
            "binary_exposure.npy",
            np.asarray(binary, dtype=np.float32),
            kind="binary_exposure",
            axes=(self.subject_axis, self.feature_axis),
            units="binary",
            space="right_canonical",
        )
        outcome = publisher.array(
            "outcome.npy",
            np.asarray(request.outcome, dtype=np.float64),
            kind="endpoint_outcome",
            axes=(self.subject_axis,),
            units="score",
            space=None,
        )
        baseline = publisher.array(
            "baseline.npy",
            np.asarray(request.baseline, dtype=np.float64),
            kind="endpoint_baseline",
            axes=(self.subject_axis,),
            units="score",
            space=None,
        )
        peak = publisher.array(
            "peak_final_score.npy",
            np.asarray(request.peak_final_score, dtype=np.float64),
            kind="oss_peak_final_score",
            axes=(self.subject_axis,),
            units="score",
            space=None,
        )
        feature_ids = publisher.array(
            "feature_ids.npy",
            np.asarray(request.feature_ids, dtype=np.int64),
            kind="oss_final_feature_ids",
            axes=(self.feature_axis,),
            units="fiber_id",
            space="right_canonical",
        )
        activation_feature_ids = publisher.array(
            "activation_feature_ids.npy",
            np.asarray(request.activation_feature_ids, dtype=np.int64),
            kind="oss_activation_feature_ids",
            axes=(self.feature_axis,),
            units="fiber_id",
            space="right_canonical",
        )
        return (
            dataclasses.replace(
                request,
                activation_probability=probability,
                outcome=outcome,
                baseline=baseline,
                peak_final_score=peak,
                feature_ids=feature_ids,
                activation_feature_ids=activation_feature_ids,
            ),
            binary_ref,
        )

    def _observed_artifacts(self) -> tuple[ArtifactRef, ...]:
        axes_by_kind = {
            "oss_fiber_ids": (self.feature_axis,),
            "oss_benefit_oriented_fiber_weights": (self.feature_axis,),
            "oss_loocv_benefit_oriented_fiber_weights": (
                self.subject_axis,
                self.feature_axis,
            ),
            "oss_full_net_fiber_scores": (self.subject_axis,),
            "oss_loocv_fold_net_fiber_scores": (
                self.subject_axis,
                self.subject_axis,
            ),
            "oss_loocv_heldout_net_fiber_scores": (self.subject_axis,),
            "oss_loocv_model_predictions": (self.subject_axis,),
            "oss_loocv_baseline_predictions": (self.subject_axis,),
            "oss_plain_activation_count": (self.subject_axis,),
            "oss_plain_activation_sum": (self.subject_axis,),
            "oss_plain_activation_top5": (self.subject_axis,),
        }
        arrays = tuple(
            ArtifactRef(
                kind=kind,
                schema_version="dual_frequency_array_v1",
                uri=f"memory://ppam/{kind}",
                sha256=f"{index:x}" * 64,
                dtype="float64",
                shape=tuple(axis.count for axis in axes),
                axis_refs=axes,
                axis_hashes=tuple(axis.sha256 for axis in axes),
                units="score",
                space=None,
                producer_id="ppam_observed_test",
                producer_version="1",
            )
            for index, (kind, axes) in enumerate(axes_by_kind.items(), start=1)
        )
        documents = tuple(
            ArtifactRef(
                kind=kind,
                schema_version="dual_frequency_document_v1",
                uri=f"memory://ppam/{kind}",
                sha256=digest * 64,
                dtype=None,
                shape=None,
                axis_refs=(),
                axis_hashes=(),
                units=None,
                space=None,
                producer_id="ppam_observed_test",
                producer_version="1",
            )
            for kind, digest in (
                ("oss_fiber_score_support", "c"),
                ("oss_plain_activation_model_comparison", "d"),
                ("ppam_observed_state", "e"),
            )
        )
        return (*arrays, *documents)

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
            (probabilities > 0.5).astype(np.float32),
        )
        self.assertEqual(first_binary[0, 0], 0.0)
        expected_weights = benefit_oriented_weights(
            partial_spearman_weights(
                self.outcome,
                first_binary,
                self.baseline[:, None],
            ),
            "lower",
        ).astype(np.float32)
        np.testing.assert_allclose(full_weights, expected_weights, rtol=1e-6, atol=1e-6)

    def test_permutation_blocks_match_single_interval_in_reverse_order(self) -> None:
        request = dataclasses.replace(
            self._request(),
            permutation_resamples=251,
            seed=67,
        )
        schedule = formal_resampling_schedule(
            "permutation",
            self.n_subjects,
            request.permutation_resamples,
            request.seed,
        )
        with patch.object(
            ppam_fitting,
            "_weight_operators",
            wraps=ppam_fitting._weight_operators,
        ) as build_operators:
            workspace = ppam_fitting.prepare_ppam_fit_workspace(
                request,
                self.probabilities,
                np.zeros_like(self.probabilities, dtype=bool),
                self.outcome,
                self.baseline,
                self.peak_score,
                self.fiber_ids,
                (),
            )
            serial = ppam_fitting.compute_ppam_permutation_block_from_workspace(
                workspace.permutation,
                schedule,
                ReplicateBlock(
                    0,
                    0,
                    request.permutation_resamples,
                    request.permutation_resamples,
                ),
            )
            canonical_blocks = tuple(
                ppam_fitting.compute_ppam_permutation_block_from_workspace(
                    workspace.permutation,
                    schedule,
                    block,
                )
                for block in schedule.blocks()
            )
            explicit = ppam_fitting.aggregate_ppam_fit_workspace(
                workspace,
                schedule,
                tuple(reversed(canonical_blocks)),
            )
            self.assertEqual(build_operators.call_count, 1)
        self.assertEqual(
            tuple(block.block.count for block in canonical_blocks),
            (250, 1),
        )
        combined = combine_permutation_blocks(
            {"loocv_spearman_rho": 0.25},
            schedule,
            tuple(reversed(canonical_blocks)),
        )
        np.testing.assert_array_equal(combined.null_statistics, serial.null_statistics)
        with self.assertRaisesRegex(
            FormalBackendError,
            "full schedule",
        ):
            combine_permutation_blocks(
                {"loocv_spearman_rho": 0.25},
                schedule,
                canonical_blocks[:-1],
            )
        changed_digest = dataclasses.replace(
            canonical_blocks[0],
            schedule_sha256="0" * 64,
        )
        with self.assertRaisesRegex(
            FormalBackendError,
            "parent schedule",
        ):
            combine_permutation_blocks(
                {"loocv_spearman_rho": 0.25},
                schedule,
                (changed_digest, *canonical_blocks[1:]),
            )

        delegated = ppam_fitting.fit_ppam_activation(
            request,
            self.probabilities,
            np.zeros_like(self.probabilities, dtype=bool),
            self.outcome,
            self.baseline,
            self.peak_score,
            self.fiber_ids,
            (),
        )
        for field in dataclasses.fields(explicit):
            actual = getattr(explicit, field.name)
            expected = getattr(delegated, field.name)
            if isinstance(actual, np.ndarray):
                np.testing.assert_array_equal(actual, expected)
            else:
                self.assertEqual(actual, expected, field.name)

    def test_ppam_operator_scratch_reopens_in_spawn_without_rebuilding(self) -> None:
        request = dataclasses.replace(
            self._request(),
            permutation_resamples=3,
            seed=73,
        )
        binary = binary_activation(self.probabilities)
        workspace = ppam_fitting.prepare_ppam_permutation_workspace(
            request,
            binary,
            self.outcome,
            self.baseline,
            self.fiber_ids,
            (),
        )
        schedule = formal_resampling_schedule(
            "permutation",
            self.n_subjects,
            request.permutation_resamples,
            request.seed,
        )
        block = schedule.blocks()[0]
        expected = ppam_fitting.compute_ppam_permutation_block_from_workspace(
            workspace,
            schedule,
            block,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory)
            descriptor = publish_ppam_operator_scratch(
                run_root
                / "work"
                / "task_ppam_workspace"
                / "attempt-0000000000000001",
                workspace,
            )
            persisted_request, binary_ref = self._published_request(
                run_root / "work" / "task_ppam_inputs",
                request,
                binary,
            )
            record = ppam_observed_workspace_record(
                persisted_request,
                binary_ref,
                self._observed_artifacts(),
                "permutation_ready",
                run_root,
                descriptor,
            )
            self.assertEqual(
                validated_ppam_operator_scratch_descriptor(
                    record,
                    persisted_request,
                    binary_ref,
                    run_root,
                ),
                descriptor,
            )
            store = ArtifactStore((run_root,))
            with patch.object(
                ppam_fitting,
                "_weight_operators",
                side_effect=AssertionError("operators must not be rebuilt"),
            ):
                reopened, arrays = reopen_ppam_workspace_from_record(
                    record,
                    persisted_request,
                    binary_ref,
                    _materialize_artifact(store, binary_ref),
                    _materialize_artifact(store, persisted_request.outcome),
                    _materialize_artifact(
                        store,
                        persisted_request.feature_ids,
                    ),
                    run_root,
                )
                try:
                    self.assertTrue(
                        all(
                            isinstance(value, np.memmap)
                            and not value.flags.writeable
                            for value in arrays.values()
                        )
                    )
                    restored = (
                        ppam_fitting.compute_ppam_permutation_block_from_workspace(
                            reopened,
                            schedule,
                            block,
                        )
                    )
                finally:
                    close_ppam_operator_scratch(arrays)
            np.testing.assert_array_equal(
                restored.null_statistics,
                expected.null_statistics,
            )

            with ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            ) as executor:
                readonly, spawned_null = executor.submit(
                    _spawn_reopen_ppam_workspace,
                    record,
                    persisted_request,
                    binary_ref,
                    run_root,
                    schedule,
                    block,
                ).result(timeout=60)
            self.assertTrue(readonly)
            np.testing.assert_array_equal(
                spawned_null,
                expected.null_statistics,
            )

            with self.assertRaisesRegex(
                PPAMObservedWorkspaceError,
                "does not match",
            ):
                validated_ppam_operator_scratch_descriptor(
                    record,
                    dataclasses.replace(persisted_request, seed=74),
                    binary_ref,
                    run_root,
                )
            unexpected = descriptor.root / "unexpected.txt"
            unexpected.write_text("untracked\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "cleanup"):
                cleanup_ppam_operator_scratch(descriptor)
            unexpected.unlink()
            descriptor_path = descriptor.root / descriptor.arrays[0].filename
            descriptor_path.unlink()
            with self.assertRaisesRegex(RuntimeError, "cannot be reopened"):
                validated_ppam_operator_scratch_descriptor(
                    record,
                    persisted_request,
                    binary_ref,
                    run_root,
                )
            cleanup_ppam_observed_workspace_record(record, run_root)
            self.assertFalse(descriptor.root.exists())

    def test_ppam_operator_scratch_preserves_zero_width_logical_state(self) -> None:
        request = self._request()
        binary = np.zeros_like(self.probabilities, dtype=np.float32)
        workspace = ppam_fitting.prepare_ppam_permutation_workspace(
            request,
            binary,
            self.outcome,
            self.baseline,
            self.fiber_ids,
            (),
        )
        workspace = dataclasses.replace(
            workspace,
            full_operator=dataclasses.replace(
                workspace.full_operator,
                estimable=np.zeros(self.n_fibers, dtype=bool),
                standardized_exposure_residual=np.empty(
                    (self.n_subjects, 0),
                    dtype=np.float64,
                ),
            ),
            fold_operators=tuple(
                dataclasses.replace(
                    operator,
                    estimable=np.zeros(self.n_fibers, dtype=bool),
                    standardized_exposure_residual=np.empty(
                        (self.n_subjects - 1, 0),
                        dtype=np.float64,
                    ),
                )
                for operator in workspace.fold_operators
            ),
        )
        packed = ppam_fitting.ppam_operator_scratch_arrays(workspace)
        self.assertEqual(
            packed["full_standardized_exposure_residual"].shape[1],
            1,
        )
        self.assertEqual(
            packed["fold_standardized_exposure_residual"].shape[2],
            1,
        )
        self.assertFalse(np.any(packed["full_standardized_exposure_residual"]))
        self.assertFalse(np.any(packed["fold_standardized_exposure_residual"]))
        restored = ppam_fitting.restore_ppam_permutation_workspace(
            request,
            binary,
            self.outcome,
            self.fiber_ids,
            packed,
        )
        self.assertEqual(
            restored.full_operator.standardized_exposure_residual.shape[1],
            0,
        )
        self.assertTrue(
            all(
                item.standardized_exposure_residual.shape[1] == 0
                for item in restored.fold_operators
            )
        )

    def test_ppam_observed_document_rejects_missing_or_nonnumeric_state(self) -> None:
        request = self._request()
        binary = binary_activation(self.probabilities)
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory)
            workspace = ppam_fitting.prepare_ppam_permutation_workspace(
                request,
                binary,
                self.outcome,
                self.baseline,
                self.fiber_ids,
                (),
            )
            descriptor = publish_ppam_operator_scratch(
                run_root
                / "work"
                / "task_ppam_workspace"
                / "attempt-0000000000000001",
                workspace,
            )
            persisted_request, binary_ref = self._published_request(
                run_root / "work" / "task_ppam_inputs",
                request,
                binary,
            )
            record = ppam_observed_workspace_record(
                persisted_request,
                binary_ref,
                self._observed_artifacts(),
                "permutation_ready",
                run_root,
                descriptor,
            )
            base_payload = {
                "schema_version": "dual_frequency_ppam_observed_state_v1",
                "final_model_id": request.final_model.identifier,
                "technical_status": "permutation_ready",
                "failure_reasons": [],
                "finite_fold_weights": [0] * self.n_subjects,
                "performance": {"loocv_spearman_rho": None},
                "full_support": {},
                "fold_support": [{} for _index in range(self.n_subjects)],
                "plain_model_comparisons": [],
                "peak_score_pearson_r": None,
            }

            class DocumentStore:
                def __init__(self, payload: dict[str, object]) -> None:
                    self.payload = payload

                def materialize_document(
                    self,
                    artifact: ArtifactRef,
                    *,
                    expected_kind: str,
                ) -> dict[str, object]:
                    del artifact, expected_kind
                    return self.payload

            malformed_payloads = (
                base_payload,
                {
                    **base_payload,
                    "finite_full_weights": 0,
                    "performance": {"loocv_spearman_rho": "not-a-number"},
                },
                {
                    **base_payload,
                    "finite_full_weights": self.n_fibers + 1,
                },
            )
            for payload in malformed_payloads:
                with self.subTest(payload=payload), self.assertRaises(
                    PPAMObservedWorkspaceError
                ):
                    load_ppam_observed_state(
                        record,
                        persisted_request,
                        DocumentStore(payload),
                    )

    def test_permutation_block_record_publishes_reopens_and_fails_closed(self) -> None:
        request = dataclasses.replace(
            self._request(),
            permutation_resamples=3,
            seed=71,
        )
        binary = binary_activation(self.probabilities)
        schedule = formal_resampling_schedule(
            "permutation",
            self.n_subjects,
            request.permutation_resamples,
            request.seed,
        )
        computed = compute_ppam_permutation_block(
            request,
            binary,
            self.outcome,
            self.baseline,
            self.fiber_ids,
            (),
            schedule,
            schedule.blocks()[0],
        )
        replicate_axis = AxisRef(
            "ppam_permutation_replicates",
            request.permutation_resamples,
            "9" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schedule_publisher = RunScopedArtifactPublisher(
                root,
                "ppam_schedule",
                "1",
            )
            schedule_artifact = schedule_publisher.array(
                "formal_resampling_schedule.npy",
                schedule.indices,
                kind="formal_resampling_schedule",
                axes=(replicate_axis, self.subject_axis),
                units="subject_index",
                space=None,
            )
            descriptor = schedule.descriptor
            schedule_record = ResamplingScheduleRecord(
                target_id=request.final_model.identifier,
                resampling_kind="permutation",
                subject_axis=self.subject_axis,
                replicate_axis=replicate_axis,
                seed=request.seed,
                replicate_count=request.permutation_resamples,
                block_size=250,
                schedule_schema=descriptor.schema_version,
                generator_class=descriptor.generator_class,
                bit_generator_class=descriptor.bit_generator_class,
                numpy_version=descriptor.numpy_version,
                environment_fingerprint=descriptor.environment_fingerprint,
                schedule_sha256=descriptor.schedule_sha256,
                schedule=schedule_artifact,
            )
            record = publish_ppam_permutation_block(
                computed,
                schedule_record,
                RunScopedArtifactPublisher(root, "ppam_block", "1"),
            )
            self.assertIsInstance(record, PPAMPermutationBlockRecord)
            restored = load_ppam_permutation_block(
                record,
                schedule_record,
                ArtifactStore((root,)),
            )
            np.testing.assert_array_equal(
                restored.null_statistics,
                computed.null_statistics,
            )
            self.assertEqual(restored.block, computed.block)
            self.assertEqual(
                restored.schedule_sha256,
                computed.schedule_sha256,
            )

            with self.assertRaisesRegex(RecordError, "artifact"):
                dataclasses.replace(
                    record,
                    artifacts=(
                        dataclasses.replace(
                            record.artifacts[0],
                            kind="formal_permutation_null_statistics_block",
                        ),
                    ),
                )
            changed_schedule = dataclasses.replace(
                schedule_record,
                schedule_sha256="0" * 64,
            )
            with self.assertRaisesRegex(
                PPAMPermutationBlockError,
                "parent schedule",
            ):
                load_ppam_permutation_block(
                    record,
                    changed_schedule,
                    ArtifactStore((root,)),
                )
            block_path = Path(unquote(urlsplit(record.artifacts[0].uri).path))
            block_path.write_bytes(block_path.read_bytes() + b"corrupt")
            with self.assertRaises(PPAMPermutationBlockError):
                load_ppam_permutation_block(
                    record,
                    schedule_record,
                    ArtifactStore((root,)),
                )

    def test_observed_state_enforces_permutation_readiness(self) -> None:
        request = dataclasses.replace(
            self._request(),
            permutation_resamples=3,
            seed=79,
        )
        workspace = ppam_fitting.prepare_ppam_fit_workspace(
            request,
            self.probabilities,
            np.zeros_like(self.probabilities, dtype=bool),
            self.outcome,
            self.baseline,
            self.peak_score,
            self.fiber_ids,
            (),
        )
        observed = ppam_fitting.ppam_observed_state(workspace)
        with self.assertRaisesRegex(
            ppam_fitting.PPAMFittingError,
            "requires its parent schedule",
        ):
            ppam_fitting.aggregate_ppam_observed_state(observed, None, ())

        degenerate = dataclasses.replace(
            observed,
            failure_reasons=("activation_all_zero",),
        )
        result = ppam_fitting.aggregate_ppam_observed_state(
            degenerate,
            None,
            (),
        )
        self.assertEqual(result.status, "failed_activation_degenerate")
        self.assertEqual(result.failure_reasons, ("activation_all_zero",))
        self.assertTrue(np.all(np.isnan(result.permutation_null)))
        schedule = formal_resampling_schedule(
            "permutation",
            self.n_subjects,
            request.permutation_resamples,
            request.seed,
        )
        with self.assertRaisesRegex(
            ppam_fitting.PPAMFittingError,
            "cannot receive null state",
        ):
            ppam_fitting.aggregate_ppam_observed_state(
                degenerate,
                schedule,
                (),
            )

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
        expected_binary = (self.probabilities > 0.5).astype(np.float32)
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
        expected_binary = (self.probabilities > 0.5).astype(np.float32)
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
            (expected > 0.5).astype(np.float32),
        )


if __name__ == "__main__":
    unittest.main()
