"""Synthetic tests for add-on direct-voxel branch computation and realization."""

from __future__ import annotations

import dataclasses
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.direct_voxel import (
    AddonDirectVoxelBackend,
    AddonDirectVoxelDesignError,
    build_addon_nuisance_plan,
    evaluate_grid_cell_with_nuisance_plan,
)
from dual_frequency.backends.interaction import (
    branch_failure_record,
    branch_intended_role,
    branch_record_from_observed,
)
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.contracts import (
    AxisRef,
    EndpointKey,
    HardComputabilityLimits,
    ObservedRequest,
    SourceGrid,
    canonical_hash,
)
from dual_frequency.workflow.state import BranchPlan, realize_final


NO_DELTA = "no_delta_reference"
ADJUSTED = "delta_reference_adjusted"


def _fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n_subjects = 16
    z = np.linspace(-1.5, 1.5, n_subjects)
    loadings = np.linspace(0.8, 1.2, 24)
    subject = np.arange(n_subjects, dtype=float)[:, None]
    feature = np.arange(24, dtype=float)[None, :]
    signal = (
        260.0
        + 20.0 * z[:, None] * loadings[None, :]
        + 0.25 * np.sin((subject + 1.0) * (feature + 1.0))
    )
    background = 40.0 + 2.0 * np.cos(
        (subject + 1.0) * (np.arange(8, dtype=float)[None, :] + 1.0)
    )
    exposure = np.column_stack([signal, background])
    reference = 45.0 + 2.5 * np.cos(np.arange(n_subjects) * 1.3)
    delta = np.sin(np.arange(n_subjects) * 0.9) + 0.3 * z
    fixed_error = 0.15 * np.cos(np.arange(n_subjects) * 2.1)
    outcome = 55.0 - 7.0 * z + 0.4 * reference + 2.0 * delta + fixed_error
    fold_delta = np.tile(delta, (n_subjects, 1))
    return exposure, outcome, reference, delta, fold_delta


def _axes() -> tuple[AxisRef, AxisRef]:
    subjects = tuple(f"subject-{index:02d}" for index in range(16))
    features = tuple(f"voxel-{index:02d}" for index in range(32))
    return (
        AxisRef("addon_subjects", 16, canonical_hash({"items": subjects})),
        AxisRef("addon_voxels", 32, canonical_hash({"items": features})),
    )


def _request(branch: str) -> ObservedRequest:
    exposure, outcome, reference, delta, fold_delta = _fixture()
    subjects, features = _axes()
    nuisance = () if branch == NO_DELTA else (delta, fold_delta)
    return ObservedRequest(
        endpoint=EndpointKey(
            "synthetic_study",
            "synthetic_scale",
            "configured_pair",
            "addon_voxel",
        ),
        branch=branch,
        exposure=exposure,
        outcome=outcome,
        baseline=reference,
        nuisance_inputs=nuisance,
        subject_axis=subjects,
        feature_axis=features,
        source_grid=SourceGrid(200, 5, (180, 200, 220), (5, 6), 2),
        exposure_units="V/m",
        exposure_space="synthetic_right_canonical",
        outcome_direction="lower",
        hard_computability=HardComputabilityLimits(12, 20, 10),
        connectome_role="none",
        feature_ids=None,
        fiber_score_settings=None,
    )


def _publisher(root: Path, branch: str) -> RunScopedArtifactPublisher:
    return RunScopedArtifactPublisher(
        root,
        producer_id=f"addon_direct_voxel_{branch}",
        producer_version="1",
    )


class AddonNuisancePlanTest(unittest.TestCase):
    def test_no_delta_and_adjusted_designs_are_explicit(self) -> None:
        _, _, reference, delta, folds = _fixture()
        no_delta = build_addon_nuisance_plan(reference, NO_DELTA)
        self.assertEqual(no_delta.full_covariates.shape, (16, 1))
        self.assertEqual(no_delta.fold_covariates.shape, (16, 16, 1))

        adjusted = build_addon_nuisance_plan(
            reference,
            ADJUSTED,
            delta_full_scores=delta,
            delta_fold_scores=folds,
        )
        self.assertEqual(adjusted.full_covariates.shape, (16, 2))
        for heldout in range(16):
            training = np.delete(np.arange(16), heldout)
            self.assertAlmostEqual(
                float(np.mean(adjusted.fold_covariates[heldout, training, 1])),
                0.0,
                places=12,
            )
            self.assertAlmostEqual(
                float(np.std(adjusted.fold_covariates[heldout, training, 1], ddof=0)),
                1.0,
                places=12,
            )

    def test_adjusted_scaling_and_design_failures_are_branch_local(self) -> None:
        _, _, reference, delta, folds = _fixture()
        with self.assertRaises(AddonDirectVoxelDesignError) as caught:
            build_addon_nuisance_plan(
                reference,
                ADJUSTED,
                delta_full_scores=np.ones(16),
                delta_fold_scores=np.ones((16, 16)),
            )
        self.assertEqual(caught.exception.status, "invalid_delta_reference_scaling")

        collinear = 2.0 * reference + 3.0
        with self.assertRaises(AddonDirectVoxelDesignError) as caught:
            build_addon_nuisance_plan(
                reference,
                ADJUSTED,
                delta_full_scores=collinear,
                delta_fold_scores=np.tile(collinear, (16, 1)),
            )
        self.assertEqual(caught.exception.status, "invalid_nuisance_design")

        no_delta = build_addon_nuisance_plan(reference, NO_DELTA)
        self.assertEqual(no_delta.full_covariates.shape, (16, 1))
        self.assertTrue(np.all(np.isfinite(delta)))
        self.assertTrue(np.all(np.isfinite(folds)))

    def test_heldout_delta_value_does_not_change_fold_weights(self) -> None:
        exposure, outcome, reference, delta, folds = _fixture()
        heldout = 4
        altered_folds = folds.copy()
        altered_folds[heldout, heldout] += 1000.0
        first = build_addon_nuisance_plan(
            reference,
            ADJUSTED,
            delta_full_scores=delta,
            delta_fold_scores=folds,
        )
        second = build_addon_nuisance_plan(
            reference,
            ADJUSTED,
            delta_full_scores=delta,
            delta_fold_scores=altered_folds,
        )
        request = _request(ADJUSTED)
        first_result = evaluate_grid_cell_with_nuisance_plan(
            exposure,
            outcome,
            first,
            "lower",
            200,
            5,
            request.hard_computability,
            retain_arrays=True,
        )
        second_result = evaluate_grid_cell_with_nuisance_plan(
            exposure,
            outcome,
            second,
            "lower",
            200,
            5,
            request.hard_computability,
            retain_arrays=True,
        )
        np.testing.assert_allclose(
            first_result.arrays.fold_weights[heldout],
            second_result.arrays.fold_weights[heldout],
            equal_nan=True,
        )
        self.assertNotEqual(
            first_result.arrays.heldout_predictions[heldout],
            second_result.arrays.heldout_predictions[heldout],
        )


class AddonDirectVoxelBackendTest(unittest.TestCase):
    def test_adjusted_branch_accepts_axis_validated_artifact_inputs(self) -> None:
        request = _request(ADJUSTED)
        exposure, outcome, reference, delta, fold_delta = _fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = RunScopedArtifactPublisher(root / "inputs", "fixture", "1")
            exposure_ref = inputs.array(
                "exposure.npy",
                exposure,
                kind="addon_overlap_excluded_exposure",
                axes=(request.subject_axis, request.feature_axis),
                units="V/m",
                space=request.exposure_space,
            )
            outcome_ref = inputs.array(
                "outcome.npy",
                outcome,
                kind="addon_outcome",
                axes=(request.subject_axis,),
                units="score",
                space="clinical",
            )
            reference_ref = inputs.array(
                "reference.npy",
                reference,
                kind="reference_outcome",
                axes=(request.subject_axis,),
                units="score",
                space="clinical",
            )
            delta_ref = inputs.array(
                "delta.npy",
                delta,
                kind="delta_reference_full_scores",
                axes=(request.subject_axis,),
                units="V/m",
                space=None,
            )
            fold_delta_ref = inputs.array(
                "fold_delta.npy",
                fold_delta,
                kind="delta_reference_fold_scores",
                axes=(request.subject_axis, request.subject_axis),
                units="V/m",
                space=None,
            )
            artifact_request = dataclasses.replace(
                request,
                exposure=exposure_ref,
                outcome=outcome_ref,
                baseline=reference_ref,
                nuisance_inputs=(delta_ref, fold_delta_ref),
            )
            result = AddonDirectVoxelBackend(
                _publisher(root / "output", ADJUSTED),
                artifact_store=ArtifactStore([root]),
            ).run(artifact_request)
            self.assertIsNotNone(result.source)
            self.assertIn(
                result.source.source_status,
                {"pre_specified_accepted", "scan_fallback_accepted"},
            )

    def test_both_executable_branches_resolve_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = {}
            for branch in (NO_DELTA, ADJUSTED):
                backend = AddonDirectVoxelBackend(
                    _publisher(root / branch, branch)
                )
                results[branch] = backend.run(_request(branch))
                source = results[branch].source
                self.assertIsNotNone(source)
                self.assertIn(
                    source.source_status,
                    {"pre_specified_accepted", "scan_fallback_accepted"},
                )
                self.assertIsNotNone(source.feature_axis)
                self.assertTrue(results[branch].artifacts)
            self.assertNotEqual(
                results[NO_DELTA].source.identifier,
                results[ADJUSTED].source.identifier,
            )

    def test_adjusted_request_rejects_constant_delta_without_affecting_no_delta(self) -> None:
        request = _request(ADJUSTED)
        invalid = dataclasses.replace(
            request,
            nuisance_inputs=(np.ones(16), np.ones((16, 16))),
        )
        with tempfile.TemporaryDirectory() as temporary:
            backend = AddonDirectVoxelBackend(
                _publisher(Path(temporary) / "adjusted", ADJUSTED)
            )
            with self.assertRaises(AddonDirectVoxelDesignError) as caught:
                backend.run(invalid)
            self.assertEqual(caught.exception.status, "invalid_delta_reference_scaling")

            no_delta = AddonDirectVoxelBackend(
                _publisher(Path(temporary) / "no_delta", NO_DELTA)
            ).run(_request(NO_DELTA))
            self.assertIsNotNone(no_delta.source)

    def test_branch_records_preserve_one_way_fallback(self) -> None:
        request = _request(NO_DELTA)
        with tempfile.TemporaryDirectory() as temporary:
            observed = AddonDirectVoxelBackend(
                _publisher(Path(temporary), NO_DELTA)
            ).run(request)
        no_delta = branch_record_from_observed(
            request.endpoint,
            NO_DELTA,
            observed,
            intended_branch=ADJUSTED,
            fallback_eligible=True,
        )
        adjusted_failure = branch_failure_record(
            request.endpoint,
            ADJUSTED,
            intended_branch=ADJUSTED,
            fallback_eligible=True,
            input_status="valid",
            nuisance_design_status="invalid_delta_reference_scaling",
            failure_stage="nuisance_design",
            failure_detail="constant DeltaReferenceScore",
        )
        plan = BranchPlan(
            endpoint=request.endpoint,
            status="ready",
            intended_branch=ADJUSTED,
            attempted_branches=(NO_DELTA, ADJUSTED),
            intended_status="pending",
            fallback_eligible=True,
        )
        decision = realize_final(
            plan,
            {NO_DELTA: no_delta, ADJUSTED: adjusted_failure},
        )
        self.assertEqual(decision.final_branch, NO_DELTA)
        self.assertEqual(decision.final_role, "fallback_final")

        self.assertEqual(
            branch_intended_role(
                ADJUSTED,
                intended_branch=NO_DELTA,
                fallback_eligible=False,
            ),
            "comparison",
        )
        accepted_adjusted_source = dataclasses.replace(
            observed.source,
            endpoint=request.endpoint,
        )
        accepted_adjusted = dataclasses.replace(
            no_delta,
            branch=ADJUSTED,
            intended_role="comparison",
            source=accepted_adjusted_source,
        )
        no_delta_failure = branch_failure_record(
            request.endpoint,
            NO_DELTA,
            intended_branch=NO_DELTA,
            fallback_eligible=False,
            input_status="valid",
            nuisance_design_status="valid",
            failure_stage="source",
            failure_detail="absent_no_stable_grid",
        )
        no_delta_primary = BranchPlan(
            endpoint=request.endpoint,
            status="ready",
            intended_branch=NO_DELTA,
            attempted_branches=(NO_DELTA, ADJUSTED),
            intended_status="pending",
            fallback_eligible=False,
        )
        no_final = realize_final(
            no_delta_primary,
            {NO_DELTA: no_delta_failure, ADJUSTED: accepted_adjusted},
        )
        self.assertIsNone(no_final.final_branch)
        self.assertEqual(no_final.final_role, "no_final_model")


if __name__ == "__main__":
    unittest.main()
