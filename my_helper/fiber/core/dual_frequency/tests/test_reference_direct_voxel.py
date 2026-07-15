"""Synthetic and bounded tests for the generic reference direct-voxel backend."""

from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.direct_voxel import kernel as direct_kernel
from dual_frequency.backends.direct_voxel import (
    ReferenceDirectVoxelBackend,
    ReferenceDirectVoxelBackendError,
    classify_prediction_status,
    evaluate_grid,
    evaluate_grid_cell,
    resolve_source,
)
from dual_frequency.backends.direct_voxel.kernel import continuous_mean_score
from dual_frequency.backends.direct_voxel.source_resolver import (
    resolve_source as resolve_direct_source,
)
from dual_frequency.backends.source_resolver import (
    GridCellMetric,
    resolve_source as resolve_shared_source,
)
from dual_frequency.backends.statistics import (
    average_rank,
    benefit_oriented_weights,
    linear_prediction,
    partial_spearman_weights,
    pearson_columns,
    rank_columns,
    residualize,
    safe_correlation,
    classify_prediction_status as shared_classify_prediction_status,
)
from dual_frequency.cache import (
    ArtifactPublicationError,
    ArtifactStore,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    HardComputabilityLimits,
    ObservedRequest,
    SourceGrid,
    canonical_hash,
)


def _synthetic_fixture(
    *,
    signal_center: float = 260.0,
    signal_slope: float = 20.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_subjects = 16
    n_signal = 24
    z = np.linspace(-1.5, 1.5, n_subjects)
    loadings = np.linspace(0.8, 1.2, n_signal)
    subject = np.arange(n_subjects, dtype=float)[:, None]
    feature = np.arange(n_signal, dtype=float)[None, :]
    signal = (
        signal_center
        + signal_slope * z[:, None] * loadings[None, :]
        + 0.25 * np.sin((subject + 1.0) * (feature + 1.0))
    )
    background_feature = np.arange(8, dtype=float)[None, :]
    background = 40.0 + 2.0 * np.cos((subject + 1.0) * (background_feature + 1.0))
    exposure = np.column_stack([signal, background]).astype(np.float64)
    baseline = 45.0 + 3.0 * np.cos(np.arange(n_subjects) * 1.7)
    fixed_error = 0.2 * np.sin(np.arange(n_subjects) * 2.3)
    outcome = 40.0 - 8.0 * z + 0.3 * baseline + fixed_error
    return exposure, outcome, baseline


def _grid() -> SourceGrid:
    return SourceGrid(
        pre_specified_tau=200,
        pre_specified_coverage=5,
        tau_values=(180, 200, 220),
        coverage_values=(5, 6),
        minimum_adjacent_passing_cells=2,
    )


def _limits(**changes: int) -> HardComputabilityLimits:
    values = {
        "n_subjects_min": 12,
        "n_features_full_min": 20,
        "fold_n_features_min": 10,
    }
    values.update(changes)
    return HardComputabilityLimits(**values)


def _axes() -> tuple[AxisRef, AxisRef]:
    subjects = tuple(f"subject-{index:02d}" for index in range(16))
    features = tuple(f"voxel-{index:02d}" for index in range(32))
    return (
        AxisRef("synthetic_subjects", len(subjects), canonical_hash({"items": subjects})),
        AxisRef("synthetic_voxels", len(features), canonical_hash({"items": features})),
    )


def _request(
    exposure: np.ndarray | ArtifactRef,
    outcome: np.ndarray | ArtifactRef,
    baseline: np.ndarray | ArtifactRef,
    *,
    subjects: AxisRef | None = None,
    features: AxisRef | None = None,
) -> ObservedRequest:
    subject_axis, feature_axis = _axes()
    return ObservedRequest(
        endpoint=EndpointKey(
            "synthetic_study",
            "synthetic_scale",
            "reference_pair",
            "reference_voxel",
        ),
        branch="reference",
        exposure=exposure,
        outcome=outcome,
        baseline=baseline,
        nuisance_inputs=(),
        subject_axis=subjects or subject_axis,
        feature_axis=features or feature_axis,
        source_grid=_grid(),
        exposure_units=(exposure.units if isinstance(exposure, ArtifactRef) else "V/m"),
        exposure_space=(
            exposure.space if isinstance(exposure, ArtifactRef) else "synthetic"
        ),
        outcome_direction="lower",
        hard_computability=_limits(),
        connectome_role="none",
        feature_ids=None,
        fiber_score_settings=None,
    )


def _publisher(root: Path) -> RunScopedArtifactPublisher:
    return RunScopedArtifactPublisher(
        root,
        producer_id="reference_direct_voxel_backend",
        producer_version="1",
    )


@dataclasses.dataclass(frozen=True)
class _SyntheticFiberMetric:
    """Fiber-like metric that satisfies the shared resolver protocol structurally."""

    tau: float
    coverage: int
    fold_n_features_min: int
    passes_hard_computability: bool
    prediction_status: str
    mae_model: float
    mae_baseline: float
    rmse_model: float
    rmse_baseline: float


def _synthetic_fiber_cells(
    grid: SourceGrid,
    passing_fold_minima: dict[tuple[float, int], int],
) -> tuple[_SyntheticFiberMetric, ...]:
    cells = []
    for tau in grid.tau_values:
        for coverage in grid.coverage_values:
            key = (float(tau), int(coverage))
            passes = key in passing_fold_minima
            cells.append(
                _SyntheticFiberMetric(
                    tau=float(tau),
                    coverage=int(coverage),
                    fold_n_features_min=passing_fold_minima.get(key, 0),
                    passes_hard_computability=passes,
                    prediction_status=(
                        "error_predictive" if passes else "not_applicable"
                    ),
                    mae_model=1.0,
                    mae_baseline=2.0,
                    rmse_model=1.5,
                    rmse_baseline=2.5,
                )
            )
    return tuple(cells)


class SharedStatisticsTest(unittest.TestCase):
    def test_model_statistics_are_direct_reexports_with_identical_numerics(self) -> None:
        self.assertIs(
            direct_kernel.partial_spearman_weights,
            partial_spearman_weights,
        )
        self.assertIs(
            direct_kernel.benefit_oriented_weights,
            benefit_oriented_weights,
        )
        self.assertIs(
            direct_kernel.classify_prediction_status,
            shared_classify_prediction_status,
        )

        outcome = np.arange(1.0, 7.0)
        exposure = np.column_stack([outcome, outcome[::-1]])
        nuisance = np.array([[0.0], [1.0], [0.0], [1.0], [0.0], [1.0]])
        coefficients = partial_spearman_weights(outcome, exposure, nuisance)
        np.testing.assert_allclose(coefficients, np.array([1.0, -1.0]))
        np.testing.assert_allclose(
            benefit_oriented_weights(coefficients, "lower"),
            np.array([-1.0, 1.0]),
        )
        np.testing.assert_allclose(
            benefit_oriented_weights(coefficients, "higher"),
            np.array([1.0, -1.0]),
        )
        self.assertEqual(
            shared_classify_prediction_status(0.8, 1.0, 1.0, 1.2),
            "error_predictive",
        )
        self.assertEqual(
            shared_classify_prediction_status(0.8, 1.0, 1.3, 1.2),
            "error_nonpredictive",
        )

    def test_rank_residual_and_column_correlation_numerics(self) -> None:
        np.testing.assert_allclose(
            average_rank(np.array([3.0, np.nan, 1.0, 3.0])),
            np.array([2.5, np.nan, 1.0, 2.5]),
            equal_nan=True,
        )
        np.testing.assert_allclose(
            rank_columns(
                np.array(
                    [
                        [2.0, 10.0],
                        [1.0, 20.0],
                        [2.0, 20.0],
                    ]
                )
            ),
            np.array(
                [
                    [2.5, 1.0],
                    [1.0, 2.5],
                    [2.5, 2.5],
                ]
            ),
        )
        np.testing.assert_allclose(
            residualize(
                np.array([1.0, 3.0, 2.0, 5.0]),
                np.array([[0.0], [1.0], [2.0], [3.0]]),
            ),
            np.array([-0.1, 0.8, -1.3, 0.6]),
            atol=1e-12,
        )
        correlations = pearson_columns(
            np.array([1.0, 2.0, 3.0, 4.0]),
            np.column_stack(
                [
                    np.array([1.0, 2.0, 3.0, 4.0]),
                    np.array([4.0, 3.0, 2.0, 1.0]),
                    np.ones(4),
                ]
            ),
        )
        np.testing.assert_allclose(correlations[:2], np.array([1.0, -1.0]))
        self.assertTrue(np.isnan(correlations[2]))

    def test_safe_correlation_and_linear_prediction_numerics(self) -> None:
        first = np.array([1.0, 2.0, 3.0, 4.0])
        second = np.array([1.0, 4.0, 2.0, 3.0])
        pearson = safe_correlation(first, second, method="pearson")
        spearman = safe_correlation(first, second, method="spearman")
        self.assertAlmostEqual(pearson[0], 0.4)
        self.assertAlmostEqual(spearman[0], 0.4)
        self.assertTrue(all(np.isfinite(value) for value in (*pearson, *spearman)))

        prediction, coefficients = linear_prediction(
            np.array([1.0, 3.0, 4.0, 6.0]),
            np.array([0.0, 1.0, 0.0, 1.0]),
            np.array([[0.0], [0.0], [1.0], [1.0]]),
            np.array([2.0]),
            np.array([[2.0]]),
        )
        np.testing.assert_allclose(prediction, np.array([11.0]), atol=1e-12)
        np.testing.assert_allclose(
            coefficients,
            np.array([1.0, 2.0, 3.0]),
            atol=1e-12,
        )


class SharedSourceResolverTest(unittest.TestCase):
    def test_direct_resolver_path_is_a_compatibility_reexport(self) -> None:
        self.assertIs(resolve_source, resolve_shared_source)
        self.assertIs(resolve_direct_source, resolve_shared_source)

    def test_structural_fiber_metrics_preserve_fallback_priority(self) -> None:
        grid = SourceGrid(200, 6, (180, 200, 220), (5, 6, 7), 0)
        cases = (
            (
                "grid_index_manhattan_distance",
                {(200.0, 5): 10, (180.0, 5): 10},
                (200.0, 5),
            ),
            (
                "adjacent_support",
                {(180.0, 6): 10, (200.0, 5): 10, (180.0, 7): 10},
                (180.0, 6),
            ),
            (
                "fold_minimum",
                {(180.0, 6): 20, (200.0, 5): 30},
                (200.0, 5),
            ),
            (
                "stricter_coverage",
                {(200.0, 5): 10, (200.0, 7): 10},
                (200.0, 7),
            ),
            (
                "higher_tau",
                {(180.0, 6): 10, (220.0, 6): 10},
                (220.0, 6),
            ),
        )
        for name, passing, expected in cases:
            with self.subTest(priority=name):
                cells = _synthetic_fiber_cells(grid, passing)
                self.assertTrue(isinstance(cells[0], GridCellMetric))
                resolution = resolve_shared_source(cells, grid)
                self.assertEqual(resolution.source_status, "scan_fallback_accepted")
                self.assertIsInstance(resolution.selected, _SyntheticFiberMetric)
                self.assertEqual(
                    (resolution.selected.tau, resolution.selected.coverage),
                    expected,
                )


class DirectVoxelKernelTest(unittest.TestCase):
    def test_grid_metrics_reject_contradictory_status_fields(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        metrics = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
        ).metrics
        with self.assertRaisesRegex(ValueError, "hard-computability"):
            dataclasses.replace(metrics, passes_hard_computability=False)
        with self.assertRaisesRegex(ValueError, "error-prediction status"):
            dataclasses.replace(metrics, prediction_status="not_applicable")
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            dataclasses.replace(
                metrics,
                n_valid_full_features=metrics.n_features_full + 1,
            )
        with self.assertRaisesRegex(ValueError, "minimum, median, and maximum"):
            dataclasses.replace(
                metrics,
                fold_n_features_median=metrics.fold_n_features_max + 1,
            )

    def test_pre_specified_source_is_accepted_and_predictive(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        cells = evaluate_grid(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            _grid().tau_values,
            _grid().coverage_values,
            _limits(),
        )
        resolution = resolve_source(cells, _grid())
        self.assertEqual(resolution.source_status, "pre_specified_accepted")
        self.assertEqual(resolution.prediction_status, "error_predictive")
        self.assertEqual(resolution.selected.tau, 200)
        self.assertEqual(resolution.selected.coverage, 5)
        self.assertGreaterEqual(resolution.adjacent_support, 2)

    def test_scan_fallback_uses_stability_order_not_outcome_metrics(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture(
            signal_center=190.0,
            signal_slope=4.0,
        )
        grid = SourceGrid(200, 5, (150, 180, 200), (5, 6), 2)
        cells = evaluate_grid(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            grid.tau_values,
            grid.coverage_values,
            _limits(),
        )
        resolution = resolve_source(cells, grid)
        self.assertEqual(resolution.source_status, "scan_fallback_accepted")
        self.assertEqual((resolution.selected.tau, resolution.selected.coverage), (180, 5))

        altered = tuple(
            dataclasses.replace(cell, q2=-5.0, loocv_spearman_rho=-0.9)
            if cell.passes_hard_computability
            else cell
            for cell in cells
        )
        altered_resolution = resolve_source(altered, grid)
        self.assertEqual(
            (altered_resolution.selected.tau, altered_resolution.selected.coverage),
            (180, 5),
        )

    def test_equal_grid_distance_prefers_adjacent_support_before_axis_direction(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        grid = SourceGrid(200, 6, (180, 200, 220), (5, 6, 7), 1)
        cells = evaluate_grid(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            grid.tau_values,
            grid.coverage_values,
            _limits(),
        )
        passing = {(180.0, 6), (200.0, 5), (180.0, 7)}

        def force_failure(cell):
            if (cell.tau, cell.coverage) in passing:
                return cell
            return dataclasses.replace(
                cell,
                passes_n_features_full=False,
                passes_hard_computability=False,
                prediction_status="not_applicable",
                failure_reasons=("forced_test_failure",),
            )

        resolution = resolve_source(tuple(force_failure(cell) for cell in cells), grid)
        self.assertEqual(
            (resolution.selected.tau, resolution.selected.coverage),
            (180, 6),
        )
        self.assertEqual(resolution.adjacent_support, 2)

    def test_absent_grid_has_no_prediction_classification(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture(
            signal_center=70.0,
            signal_slope=2.0,
        )
        cells = evaluate_grid(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            _grid().tau_values,
            _grid().coverage_values,
            _limits(),
        )
        resolution = resolve_source(cells, _grid())
        self.assertEqual(resolution.source_status, "absent_no_stable_grid")
        self.assertEqual(resolution.prediction_status, "not_applicable")
        self.assertIsNone(resolution.selected)

    def test_hard_computability_uses_configured_limits_only(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        computation = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(n_features_full_min=25),
        )
        self.assertEqual(computation.metrics.n_features_full, 24)
        self.assertFalse(computation.metrics.passes_n_features_full)
        self.assertFalse(computation.metrics.passes_hard_computability)
        self.assertEqual(computation.metrics.prediction_status, "not_applicable")

        with self.assertRaisesRegex(ValueError, "feature minima"):
            evaluate_grid_cell(
                exposure,
                outcome,
                baseline,
                (),
                "lower",
                200,
                5,
                HardComputabilityLimits(12, None, None),
            )

    def test_nonfinite_heldout_predictions_fail_computability(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        exposure[0, 0] = np.nan
        computation = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
        )
        self.assertFalse(computation.metrics.all_predictions_finite)
        self.assertFalse(computation.metrics.passes_predictions_finite)
        self.assertFalse(computation.metrics.passes_hard_computability)
        self.assertEqual(computation.metrics.prediction_status, "not_applicable")

    def test_heldout_subject_never_changes_its_training_fold_operator(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        original = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
            retain_arrays=True,
        )
        changed_exposure = exposure.copy()
        changed_exposure[0, :24] += np.linspace(100.0, 300.0, 24)
        changed = evaluate_grid_cell(
            changed_exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
            retain_arrays=True,
        )
        np.testing.assert_array_equal(
            original.arrays.fold_valid_masks[0],
            changed.arrays.fold_valid_masks[0],
        )
        np.testing.assert_allclose(
            original.arrays.fold_weights[0],
            changed.arrays.fold_weights[0],
            equal_nan=True,
        )
        self.assertNotEqual(
            original.arrays.heldout_scores[0],
            changed.arrays.heldout_scores[0],
        )

    def test_tau_defines_support_but_score_uses_continuous_dose(self) -> None:
        exposure = np.array([[250.0, 100.0], [210.0, 50.0]])
        weights = np.array([0.5, 2.0])
        score = continuous_mean_score(exposure, weights, np.array([True, True]))
        np.testing.assert_allclose(score, np.array([162.5, 102.5]))

    def test_prediction_classifier_requires_both_error_metrics(self) -> None:
        self.assertEqual(
            classify_prediction_status(0.8, 1.0, 1.0, 1.2),
            "error_predictive",
        )
        self.assertEqual(
            classify_prediction_status(1.0, 1.0, 1.0, 1.2),
            "error_nonpredictive",
        )
        self.assertEqual(
            classify_prediction_status(0.8, 1.0, 1.3, 1.2),
            "error_nonpredictive",
        )

    def test_higher_better_direction_reorients_weights_without_changing_predictions(self) -> None:
        exposure, outcome, baseline = _synthetic_fixture()
        lower = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
            retain_arrays=True,
        )
        higher = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "higher",
            200,
            5,
            _limits(),
            retain_arrays=True,
        )
        np.testing.assert_allclose(
            higher.arrays.full_weights,
            -lower.arrays.full_weights,
            equal_nan=True,
        )
        np.testing.assert_allclose(
            higher.arrays.heldout_predictions,
            lower.arrays.heldout_predictions,
            rtol=0,
            atol=1e-10,
        )


class ReferenceDirectVoxelBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.exposure, self.outcome, self.baseline = _synthetic_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_backend_publishes_axis_bound_artifacts_without_overwrite(self) -> None:
        backend = ReferenceDirectVoxelBackend(_publisher(self.root / "output"))
        request = _request(self.exposure, self.outcome, self.baseline)
        result = backend.run(request)
        self.assertEqual(result.source.source_status, "pre_specified_accepted")
        self.assertEqual(result.source.prediction_status, "error_predictive")
        self.assertEqual(result.source.feature_axis.axis.count, 24)
        self.assertTrue(all(Path(item.uri.removeprefix("file://")).is_file() for item in result.artifacts))
        self.assertTrue(
            all(
                Path(f"{item.uri.removeprefix('file://')}.artifact.json").is_file()
                for item in result.artifacts
            )
        )
        fold_weights = next(
            item
            for item in result.artifacts
            if item.kind == "loocv_benefit_oriented_feature_weights"
        )
        self.assertEqual(
            fold_weights.axis_refs,
            (request.subject_axis, result.source.feature_axis.axis),
        )
        self.assertEqual(
            fold_weights.shape,
            (request.subject_axis.count, result.source.feature_axis.axis.count),
        )

        repeated = backend.run(request)
        self.assertEqual(
            tuple(item.sha256 for item in repeated.artifacts),
            tuple(item.sha256 for item in result.artifacts),
        )
        changed = dataclasses.replace(request, outcome=self.outcome[::-1].copy())
        with self.assertRaisesRegex(ArtifactPublicationError, "overwrite"):
            backend.run(changed)

    def test_backend_rejects_extra_nuisance_and_non_v_per_m_exposure(self) -> None:
        backend = ReferenceDirectVoxelBackend(_publisher(self.root / "output"))
        request = _request(self.exposure, self.outcome, self.baseline)
        with self.assertRaisesRegex(ReferenceDirectVoxelBackendError, "only nuisance"):
            backend.run(
                dataclasses.replace(
                    request,
                    nuisance_inputs=(np.linspace(0.0, 1.0, 16),),
                )
            )
        with self.assertRaisesRegex(ReferenceDirectVoxelBackendError, "V/m"):
            backend.run(dataclasses.replace(request, exposure_units="V/mm"))

    def test_artifact_inputs_require_and_use_the_injected_store(self) -> None:
        subject_axis, feature_axis = _axes()
        input_root = self.root / "inputs"
        input_root.mkdir()

        def artifact(
            name: str,
            array: np.ndarray,
            axes: tuple[AxisRef, ...],
            units: str,
        ) -> ArtifactRef:
            path = input_root / f"{name}.npy"
            np.save(path, array, allow_pickle=False)
            return ArtifactRef(
                kind=name,
                schema_version="synthetic_v1",
                uri=path.as_uri(),
                sha256=sha256_file(path),
                dtype=array.dtype.name,
                shape=array.shape,
                axis_refs=axes,
                axis_hashes=tuple(axis.sha256 for axis in axes),
                units=units,
                space="MNI152NLin2009bAsym" if array.ndim == 2 else None,
                producer_id="synthetic_fixture",
                producer_version="1",
            )

        exposure_ref = artifact(
            "exposure",
            self.exposure,
            (subject_axis, feature_axis),
            "V/m",
        )
        outcome_ref = artifact("outcome", self.outcome, (subject_axis,), "score")
        baseline_ref = artifact("baseline", self.baseline, (subject_axis,), "score")
        request = _request(
            exposure_ref,
            outcome_ref,
            baseline_ref,
            subjects=subject_axis,
            features=feature_axis,
        )
        with self.assertRaisesRegex(ReferenceDirectVoxelBackendError, "ArtifactStore"):
            ReferenceDirectVoxelBackend(_publisher(self.root / "missing_store")).run(request)

        store = ArtifactStore((self.root,))
        result = ReferenceDirectVoxelBackend(
            _publisher(self.root / "artifact_output"),
            artifact_store=store,
        ).run(request)
        self.assertEqual(result.source.source_status, "pre_specified_accepted")


class CompletedFixtureParityTest(unittest.TestCase):
    frozen_manifest = (
        Path(__file__).resolve().parents[3]
        / "projects/stnsnr/acceptance/frozen/20260711T034644Z_d318f177f7f2ac7d"
        / "bounded_fixture_manifest.json"
    )
    task_id = "task_7a3ba9216fb910e53750"

    @unittest.skipUnless(
        frozen_manifest.is_file(),
        "completed bounded reference-direct fixture is unavailable",
    )
    def test_frozen_completed_reference_task_matches_source_and_arrays(self) -> None:
        frozen = json.loads(self.frozen_manifest.read_text(encoding="utf-8"))
        self.assertEqual(frozen["source_run_id"], "20260711T034644Z_d318f177f7f2ac7d")
        task = next(
            item for item in frozen["eligible_tasks"] if item["task_id"] == self.task_id
        )
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["scope_id"], "reference_direct_voxel")
        self.assertEqual(task["execution_stage"], "observed_source_resolver")
        self.assertEqual(task["parent_scale_id"], "mds_updrs_iii_score")

        artifacts = {item["kind"]: item for item in task["artifacts"]}
        for item in (*task["artifacts"], task["task_manifest"]):
            path = Path(item["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256_file(path), item["sha256"], path)

        def artifact_path(kind: str) -> Path:
            return Path(artifacts[kind]["path"])

        exposure = np.load(artifact_path("exposure_matrix"), allow_pickle=False)
        candidate_indices = np.load(
            artifact_path("candidate_flat_indices"),
            allow_pickle=False,
        )
        with artifact_path("subjects_table").open(newline="") as stream:
            subjects = list(csv.DictReader(stream))
        outcome = np.array([float(row["y_post"]) for row in subjects])
        baseline = np.array([float(row["y_base"]) for row in subjects])
        with artifact_path("threshold_scan_results").open(newline="") as stream:
            expected = next(
                row
                for row in csv.DictReader(stream)
                if float(row["tau"]) == 200 and int(row["coverage"]) == 5
            )

        grid = SourceGrid(
            200,
            5,
            (100, 150, 180, 200, 220, 250, 300, 350, 400, 500),
            (5, 6, 7, 8, 10, 12),
            2,
        )
        cells = evaluate_grid(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            grid.tau_values,
            grid.coverage_values,
            _limits(),
        )
        resolution = resolve_source(cells, grid)
        source_status = json.loads(
            artifact_path("source_status").read_text(encoding="utf-8")
        )
        selected_source = json.loads(
            artifact_path("selected_source").read_text(encoding="utf-8")
        )
        self.assertEqual(source_status["endpoint_model_id"], task["endpoint_model_id"])
        self.assertEqual(resolution.source_status, source_status["source_status"])
        self.assertEqual(resolution.prediction_status, source_status["prediction_status"])
        self.assertEqual(resolution.threshold_source, source_status["threshold_source"])
        self.assertEqual(resolution.selected.tau, selected_source["selected_tau"])
        self.assertEqual(resolution.selected.coverage, selected_source["selected_coverage"])
        self.assertEqual(resolution.adjacent_support, selected_source["adjacent_support"])
        self.assertEqual(selected_source["feature_axis"]["count"], candidate_indices.size)
        self.assertEqual(
            selected_source["feature_axis"]["sha256"],
            artifacts["candidate_flat_indices"]["sha256"],
        )

        computation = evaluate_grid_cell(
            exposure,
            outcome,
            baseline,
            (),
            "lower",
            200,
            5,
            _limits(),
            retain_arrays=True,
        )
        metrics = computation.metrics
        self.assertEqual(metrics.n_features_full, int(expected["n_voxels_full"]))
        self.assertEqual(
            metrics.n_valid_full_features,
            int(expected["n_valid_full_score_voxels"]),
        )
        self.assertEqual(metrics.fold_n_features_min, int(expected["fold_n_voxels_min"]))
        self.assertAlmostEqual(
            metrics.loocv_spearman_rho,
            float(expected["loocv_spearman_rho"]),
            places=12,
        )
        self.assertAlmostEqual(metrics.q2, float(expected["q2"]), places=8)
        self.assertAlmostEqual(metrics.mae_model, float(expected["mae_model"]), places=7)
        self.assertAlmostEqual(metrics.rmse_model, float(expected["rmse_model"]), places=7)
        self.assertTrue(metrics.passes_hard_computability)
        self.assertEqual(metrics.prediction_status, "error_nonpredictive")

        expected_full_weights = np.load(
            artifact_path("selected_full_weights"),
            allow_pickle=False,
        )
        expected_fold_weights = np.load(
            artifact_path("selected_fold_weights"),
            allow_pickle=False,
        )
        expected_fold_scores = np.load(
            artifact_path("selected_fold_scores"),
            allow_pickle=False,
        )
        np.testing.assert_allclose(
            computation.arrays.full_weights,
            expected_full_weights,
            rtol=2e-7,
            atol=5e-8,
            equal_nan=True,
        )
        np.testing.assert_allclose(
            computation.arrays.fold_weights,
            expected_fold_weights,
            rtol=2e-7,
            atol=5e-8,
            equal_nan=True,
        )
        np.testing.assert_allclose(
            computation.arrays.fold_scores,
            expected_fold_scores,
            rtol=0,
            atol=1e-5,
            equal_nan=True,
        )
        np.testing.assert_array_equal(
            computation.arrays.full_valid_mask,
            np.isfinite(expected_full_weights),
        )
        np.testing.assert_array_equal(
            computation.arrays.fold_valid_masks,
            np.isfinite(expected_fold_weights),
        )

        with artifact_path("selected_scores").open(newline="") as stream:
            score_rows = list(csv.DictReader(stream))
        with artifact_path("selected_loocv_predictions").open(newline="") as stream:
            prediction_rows = list(csv.DictReader(stream))
        np.testing.assert_allclose(
            computation.arrays.full_scores,
            np.array([float(row["HFScore_mean_main"]) for row in score_rows]),
            rtol=0,
            atol=2e-6,
        )
        np.testing.assert_allclose(
            computation.arrays.heldout_scores,
            np.array([float(row["HFScore_mean_main_LOOCV"]) for row in prediction_rows]),
            rtol=0,
            atol=2e-6,
        )
        np.testing.assert_allclose(
            computation.arrays.heldout_predictions,
            np.array([float(row["prediction_HFScore_model"]) for row in prediction_rows]),
            rtol=0,
            atol=2e-6,
        )
        np.testing.assert_allclose(
            computation.arrays.baseline_predictions,
            np.array([float(row["prediction_baseline_only"]) for row in prediction_rows]),
            rtol=0,
            atol=1e-12,
        )


if __name__ == "__main__":
    unittest.main()
