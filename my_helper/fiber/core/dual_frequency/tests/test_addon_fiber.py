"""Add-on normative-fiber preparation, nuisance, and resolver tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.interaction import branch_record_from_observed
from dual_frequency.backends.normative_fiber import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    AddonFiberBackend,
    AddonFiberBackendError,
    AddonFiberDesignError,
    prepare_addon_fiber_exposure,
)
from dual_frequency.cache import RunScopedArtifactPublisher, sha256_file
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    FeatureAxisRef,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    ObservedRequest,
    SensitiveRecord,
    SourceGrid,
    SourceRecord,
)


def _inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    latent = np.linspace(-1.5, 1.5, 12)
    reference_outcome = 18.0 + np.sin(np.arange(12) * 1.7)
    loading = np.linspace(0.8, 1.2, 48)
    subject = np.arange(12, dtype=float)[:, None]
    fiber = np.arange(48, dtype=float)[None, :]
    exposure = (
        260.0
        + 22.0 * latent[:, None] * loading[None, :]
        + 0.25 * np.sin((subject + 1.0) * (fiber + 1.0))
    )
    outcome = 42.0 - 8.0 * latent + 0.3 * reference_outcome
    fiber_ids = np.arange(80_000, 80_048, dtype=np.int64)
    return exposure, outcome, reference_outcome, fiber_ids


def _request(
    role: str,
    branch: str,
    exposure: np.ndarray,
    outcome: np.ndarray,
    reference_outcome: np.ndarray,
    fiber_ids: np.ndarray,
    *,
    connectome_id: str,
    nuisance_inputs: tuple[np.ndarray, ...] = (),
) -> ObservedRequest:
    subjects = AxisRef("subjects", exposure.shape[0], "a" * 64)
    fibers = AxisRef(f"fibers:{connectome_id}", exposure.shape[1], "b" * 64)
    return ObservedRequest(
        endpoint=EndpointKey(
            "synthetic",
            "scale_a",
            "reference_addon_pair",
            "addon_fiber",
            connectome_id,
        ),
        branch=branch,
        exposure=exposure,
        outcome=outcome,
        baseline=reference_outcome,
        nuisance_inputs=nuisance_inputs,
        subject_axis=subjects,
        feature_axis=fibers,
        source_grid=SourceGrid(200, 3, (100, 200, 300), (3, 4), 2),
        exposure_units="V/m",
        exposure_space="synthetic_space",
        outcome_direction="lower",
        hard_computability=HardComputabilityLimits(12, None, 20),
        connectome_role=role,
        feature_ids=fiber_ids,
        fiber_score_settings=NormativeFiberScoreSettings(
            sweet_fraction=0.25,
            sour_fraction=0.25,
            weighted_peak_fraction=0.25,
            sweet_selected_min_count=4,
            sour_selected_min_count=3,
            weighted_peak_min_count=2,
        ),
    )


def _dummy_artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="dummy_selected_axis",
        schema_version="1",
        uri="file:///tmp/dummy-selected-axis.npy",
        sha256="c" * 64,
        dtype="float32",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=None,
        space="synthetic_space",
        producer_id="test",
        producer_version="1",
    )


def _reference_source(*, accepted: bool = True) -> SourceRecord:
    endpoint = EndpointKey(
        "synthetic",
        "scale_a",
        "reference_addon_pair",
        "reference_fiber",
        "connectome_formal",
    )
    if not accepted:
        return SourceRecord(
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
    axis = AxisRef("selected-reference-fibers", 1, "d" * 64)
    artifact = _dummy_artifact(axis)
    return SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_predictive",
        threshold_source="pre_specified",
        selected_tau=200,
        selected_coverage=3,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(axis, "test"),
        artifacts=(artifact,),
    )


def _prepare(
    addon: np.ndarray,
    reference: np.ndarray,
    reference_model: SourceRecord | SensitiveRecord,
    **kwargs: object,
):
    return prepare_addon_fiber_exposure(
        addon,
        reference,
        reference_model,
        matched_reference_endpoint_id=reference_model.endpoint.identifier,
        matched_reference_connectome_id=reference_model.endpoint.connectome_id,
        **kwargs,
    )


class AddonFiberPreparationTest(unittest.TestCase):
    def test_overlap_includes_equality_and_precedes_candidate_coverage(self) -> None:
        addon = np.full((3, 4), 250.0, dtype=np.float32)
        reference = np.array(
            [[199.0, 200.0, 201.0, 0.0]] * 3,
            dtype=np.float32,
        )
        prepared = _prepare(
            addon,
            reference,
            _reference_source(),
        )
        np.testing.assert_array_equal(
            prepared.reference_active[0],
            np.array([False, True, True, False]),
        )
        np.testing.assert_array_equal(
            prepared.exposure[0],
            np.array([250.0, 0.0, 0.0, 250.0], dtype=np.float32),
        )
        coverage = np.sum(prepared.exposure >= 200.0, axis=0)
        np.testing.assert_array_equal(coverage, np.array([3, 0, 0, 3]))

    def test_absent_reference_source_leaves_continuous_addon_exposure_unchanged(self) -> None:
        addon = np.arange(12, dtype=np.float32).reshape(3, 4)
        reference = np.full_like(addon, 1_000.0)
        prepared = _prepare(
            addon,
            reference,
            _reference_source(accepted=False),
        )
        np.testing.assert_array_equal(prepared.exposure, addon)
        self.assertFalse(np.any(prepared.reference_active))
        self.assertIsNone(prepared.selected_reference_tau)

    def test_sensitive_reference_evidence_uses_its_evaluated_tau(self) -> None:
        source = _reference_source()
        evidence = SensitiveRecord(
            endpoint=dataclasses.replace(
                source.endpoint,
                connectome_id="connectome_sensitive",
            ),
            formal_endpoint_id=source.endpoint.identifier,
            evaluated_tau=300,
            evaluated_coverage=3,
            input_status="valid",
            cell_computability_status="computable",
            prediction_status="error_nonpredictive",
            feature_axis=source.feature_axis,
            artifacts=source.artifacts,
        )
        addon = np.full((2, 2), 250.0, dtype=np.float32)
        reference = np.array([[299.0, 300.0], [301.0, 0.0]], dtype=np.float32)
        prepared = _prepare(addon, reference, evidence)
        np.testing.assert_array_equal(
            prepared.exposure,
            np.array([[250.0, 250.0], [0.0, 250.0]], dtype=np.float32),
        )

    def test_overlap_preparation_writes_caller_owned_chunked_destinations(self) -> None:
        addon = np.arange(30, dtype=np.float32).reshape(3, 10) + 200.0
        reference = np.tile(
            np.arange(10, dtype=np.float32) * 50.0,
            (3, 1),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = np.lib.format.open_memmap(
                root / "prepared.npy",
                mode="w+",
                dtype=np.float32,
                shape=addon.shape,
            )
            active_destination = np.lib.format.open_memmap(
                root / "active.npy",
                mode="w+",
                dtype=bool,
                shape=addon.shape,
            )
            prepared = _prepare(
                addon,
                reference,
                _reference_source(),
                destination=destination,
                reference_active_destination=active_destination,
                feature_chunk_size=3,
            )
            expected_active = reference >= 200.0
            np.testing.assert_array_equal(prepared.reference_active, expected_active)
            np.testing.assert_array_equal(
                prepared.exposure,
                np.where(expected_active, 0.0, addon),
            )

    def test_overlap_rejects_a_borrowed_reference_identity(self) -> None:
        source = _reference_source()
        addon = np.full((2, 2), 250.0, dtype=np.float32)
        reference = np.full_like(addon, 200.0)
        with self.assertRaisesRegex(AddonFiberBackendError, "endpoint"):
            prepare_addon_fiber_exposure(
                addon,
                reference,
                source,
                matched_reference_endpoint_id="endpoint_wrong",
                matched_reference_connectome_id=source.endpoint.connectome_id,
            )
        with self.assertRaisesRegex(AddonFiberBackendError, "connectome"):
            prepare_addon_fiber_exposure(
                addon,
                reference,
                source,
                matched_reference_endpoint_id=source.endpoint.identifier,
                matched_reference_connectome_id="connectome_wrong",
            )


class AddonFiberBackendTest(unittest.TestCase):
    def test_formal_no_delta_branch_resolves_without_assigning_final_role(self) -> None:
        exposure, outcome, reference, fiber_ids = _inputs()
        request = _request(
            "formal",
            NO_DELTA_BRANCH,
            exposure,
            outcome,
            reference,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = AddonFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "addon_fiber_test", "1"),
                feature_chunk_size=11,
            ).run(request)
        self.assertIsNotNone(result.source)
        assert result.source is not None
        self.assertEqual(result.source.source_status, "pre_specified_accepted")
        self.assertFalse(hasattr(result.source, "final_role"))

    def test_adjusted_branch_uses_fold_specific_delta_inputs(self) -> None:
        exposure, outcome, reference, fiber_ids = _inputs()
        delta = np.cos(np.arange(exposure.shape[0]) * 1.13)
        fold_delta = np.broadcast_to(delta, (exposure.shape[0], exposure.shape[0])).copy()
        request = _request(
            "formal",
            ADJUSTED_BRANCH,
            exposure,
            outcome,
            reference,
            fiber_ids,
            connectome_id="connectome_formal",
            nuisance_inputs=(delta, fold_delta),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = AddonFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "addon_fiber_test", "1"),
                feature_chunk_size=9,
            ).run(request)
        self.assertIsNotNone(result.source)
        assert result.source is not None
        self.assertIn(
            result.source.prediction_status,
            {"error_predictive", "error_nonpredictive"},
        )

    def test_adjusted_failure_does_not_block_no_delta_branch(self) -> None:
        exposure, outcome, reference, fiber_ids = _inputs()
        adjusted = _request(
            "formal",
            ADJUSTED_BRANCH,
            exposure,
            outcome,
            reference,
            fiber_ids,
            connectome_id="connectome_formal",
            nuisance_inputs=(
                np.ones(exposure.shape[0]),
                np.ones((exposure.shape[0], exposure.shape[0])),
            ),
        )
        no_delta = dataclasses.replace(
            adjusted,
            branch=NO_DELTA_BRANCH,
            nuisance_inputs=(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(AddonFiberDesignError) as caught:
                AddonFiberBackend(
                    RunScopedArtifactPublisher(root / "adjusted", "addon_fiber_test", "1")
                ).run(adjusted)
            self.assertEqual(caught.exception.status, "invalid_delta_reference_scaling")
            result = AddonFiberBackend(
                RunScopedArtifactPublisher(root / "no_delta", "addon_fiber_test", "1")
            ).run(no_delta)
        self.assertIsNotNone(result.source)

    def test_sensitive_branch_has_grid_only_and_cannot_cross_formal_branch(self) -> None:
        exposure, outcome, reference, fiber_ids = _inputs()
        formal_request = _request(
            "formal",
            NO_DELTA_BRANCH,
            exposure,
            outcome,
            reference,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        sensitive_request = _request(
            "sensitive",
            NO_DELTA_BRANCH,
            exposure * 0.98,
            outcome,
            reference,
            fiber_ids + 1_000,
            connectome_id="connectome_sensitive",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            formal_result = AddonFiberBackend(
                RunScopedArtifactPublisher(root / "formal", "addon_fiber_test", "1")
            ).run(formal_request)
            assert formal_result.source is not None
            formal_branch = branch_record_from_observed(
                formal_request.endpoint,
                NO_DELTA_BRANCH,
                formal_result,
                intended_branch=NO_DELTA_BRANCH,
                fallback_eligible=False,
            )
            sensitive_backend = AddonFiberBackend(
                RunScopedArtifactPublisher(root / "sensitive", "addon_fiber_test", "1")
            )
            observed = sensitive_backend.run(sensitive_request)
            self.assertIsNone(observed.source)
            evidence = sensitive_backend.evaluate_sensitive_at_formal_branch(
                sensitive_request,
                formal_branch,
            )
            self.assertEqual(evidence.cell_computability_status, "computable")
            wrong_branch = dataclasses.replace(
                formal_branch,
                branch=ADJUSTED_BRANCH,
            )
            with self.assertRaisesRegex(
                Exception,
                "does not match",
            ):
                sensitive_backend.evaluate_sensitive_at_formal_branch(
                    sensitive_request,
                    wrong_branch,
                )


class CompletedAddonFiberFixtureContractTest(unittest.TestCase):
    frozen_manifest = (
        Path(__file__).resolve().parents[3]
        / "projects/stnsnr/acceptance/frozen/20260711T034644Z_d318f177f7f2ac7d"
        / "bounded_fixture_manifest.json"
    )
    task_ids = {
        "delta": "task_49c57915a31c57add0ee",
        "observed": "task_294db6b85fcc19c9ff25",
        "final": "task_f2761adf6686800a83da",
        "controls": "task_05fb8da14057db04bcd0",
        "formal": "task_4c0176441302daf11384",
        "cheap": "task_737a02e8a551e383ceb5",
        "neighborhood": "task_3791e85acf027faa4e68",
    }

    @unittest.skipUnless(
        frozen_manifest.is_file(),
        "completed bounded add-on fiber fixture manifest is unavailable",
    )
    def test_allowlisted_terminal_scope_and_scalar_contract(self) -> None:
        frozen = json.loads(self.frozen_manifest.read_text(encoding="utf-8"))
        self.assertEqual(frozen["source_run_id"], "20260711T034644Z_d318f177f7f2ac7d")
        tasks = {task["task_id"]: task for task in frozen["eligible_tasks"]}
        self.assertTrue(set(self.task_ids.values()) <= set(tasks))

        for label, task_id in self.task_ids.items():
            with self.subTest(task=label):
                task = tasks[task_id]
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["connectome_id"], "dtor")
                self.assertEqual(task["parent_scale_id"], "mds_updrs_iii_score")
                self.assertEqual(
                    task["endpoint_model_id"],
                    "endpoint_0e489d4dae7d51a3fa0c",
                )
                manifest = Path(task["task_manifest"]["path"])
                self.assertTrue(manifest.is_file(), manifest)
                self.assertEqual(
                    sha256_file(manifest),
                    task["task_manifest"]["sha256"],
                )

        delta_artifacts = {
            item["kind"]: item for item in tasks[self.task_ids["delta"]]["artifacts"]
        }
        observed_artifacts = {
            item["kind"]: item
            for item in tasks[self.task_ids["observed"]]["artifacts"]
        }
        final_artifacts = {
            item["kind"]: item for item in tasks[self.task_ids["final"]]["artifacts"]
        }
        consumed = (
            delta_artifacts["delta_hf_bundle"],
            delta_artifacts["delta_hf_support_qc"],
            observed_artifacts["selected_source"],
            observed_artifacts["source_status"],
            observed_artifacts["ulf_branch_record"],
            final_artifacts["final_model_record"],
            final_artifacts["final_model_status"],
        )
        for artifact in consumed:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256_file(path), artifact["sha256"], path)

        support = json.loads(
            Path(delta_artifacts["delta_hf_support_qc"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(support["support_status"], "invalid_extreme_out_of_support")
        self.assertEqual(support["selected_hf_tau_v_per_m"], 800.0)
        self.assertEqual(support["selected_hf_coverage"], 5)
        self.assertGreater(support["cohort_median_subject_out_candidate_fraction"], 0.50)
        self.assertGreater(support["maximum_required_out_candidate_fraction"], 0.95)
        self.assertEqual(support["out_candidate_fraction_definition"], "suprathreshold_touched_fiber_count")

        selected = json.loads(
            Path(observed_artifacts["selected_source"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(selected["branch"], "no_delta_hf")
        self.assertEqual(selected["ulf_norm_fiber_source_status"], "scan_fallback_accepted")
        self.assertEqual(selected["ulf_norm_fiber_prediction_status"], "error_predictive")
        self.assertEqual(selected["ulf_norm_fiber_selected_tau_v_per_m"], 400)
        self.assertEqual(selected["ulf_norm_fiber_selected_coverage"], 5)

        final = json.loads(
            Path(final_artifacts["final_model_status"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(final["final_branch"], "no_delta_hf")
        self.assertEqual(final["final_role"], "primary")
        self.assertEqual(final["final_status"], "final_model_error_predictive")


if __name__ == "__main__":
    unittest.main()
