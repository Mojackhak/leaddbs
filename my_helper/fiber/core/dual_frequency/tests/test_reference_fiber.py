"""Reference normative-fiber backend and connectome-role tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote, urlsplit

import numpy as np

import dual_frequency.backends.normative_fiber.reference as reference_module
from dual_frequency.backends.normative_fiber import ReferenceFiberBackend
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher, sha256_file
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    ObservedRequest,
    SourceGrid,
)


def _synthetic_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    latent = np.linspace(-1.5, 1.5, 12)
    baseline = 18.0 + np.sin(np.arange(12) * 1.7)
    loading = np.linspace(0.8, 1.2, 48)
    subject = np.arange(12, dtype=float)[:, None]
    fiber = np.arange(48, dtype=float)[None, :]
    exposure = (
        260.0
        + 22.0 * latent[:, None] * loading[None, :]
        + 0.25 * np.sin((subject + 1.0) * (fiber + 1.0))
    )
    outcome = 42.0 - 8.0 * latent + 0.3 * baseline + 0.05 * np.cos(np.arange(12))
    fiber_ids = np.arange(50_000, 50_048, dtype=np.int64)
    return exposure, outcome, baseline, fiber_ids


def _request(
    role: str,
    exposure: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    fiber_ids: np.ndarray,
    *,
    connectome_id: str,
) -> ObservedRequest:
    subjects = AxisRef("subjects", exposure.shape[0], "a" * 64)
    fibers = AxisRef(f"fibers:{connectome_id}", exposure.shape[1], "b" * 64)
    return ObservedRequest(
        endpoint=EndpointKey(
            "synthetic",
            "scale_a",
            "reference_pair",
            "reference_fiber",
            connectome_id,
        ),
        branch="reference",
        exposure=exposure,
        outcome=outcome,
        baseline=baseline,
        nuisance_inputs=(),
        subject_axis=subjects,
        feature_axis=fibers,
        source_grid=SourceGrid(
            pre_specified_tau=200,
            pre_specified_coverage=3,
            tau_values=(100, 200, 300),
            coverage_values=(3, 4),
            minimum_adjacent_passing_cells=2,
        ),
        exposure_units="V/m",
        exposure_space="synthetic_space",
        outcome_direction="lower",
        hard_computability=HardComputabilityLimits(
            n_subjects_min=12,
            n_features_full_min=None,
            fold_n_features_min=20,
        ),
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


def _artifact_array(result: object, kind: str) -> np.ndarray:
    artifacts = getattr(result, "artifacts")
    artifact = next(item for item in artifacts if item.kind == kind)
    path = Path(unquote(urlsplit(artifact.uri).path))
    return np.load(path, allow_pickle=False)


class ReferenceFiberBackendTest(unittest.TestCase):
    def test_formal_role_resolves_source_and_publishes_union_axis(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        with tempfile.TemporaryDirectory() as temporary:
            backend = ReferenceFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "fiber_test", "1"),
                feature_chunk_size=11,
            )
            result = backend.run(request)
            self.assertIsNotNone(result.source)
            assert result.source is not None
            self.assertEqual(result.source.source_status, "pre_specified_accepted")
            self.assertEqual(result.source.selected_tau, 200)
            self.assertEqual(result.source.selected_coverage, 3)
            self.assertIn(
                result.source.prediction_status,
                {"error_predictive", "error_nonpredictive"},
            )
            self.assertIsNotNone(result.source.feature_axis)
            selected_ids = _artifact_array(result, "normative_fiber_valid_union_ids")
            fold_weights = _artifact_array(
                result,
                "loocv_benefit_oriented_fiber_weights",
            )
            fold_masks = _artifact_array(result, "loocv_valid_fiber_masks")
            self.assertEqual(selected_ids.shape, (result.source.feature_axis.axis.count,))
            self.assertEqual(fold_weights.shape, (12, selected_ids.size))
            self.assertEqual(fold_masks.shape, fold_weights.shape)
            self.assertTrue(np.all(np.isnan(fold_weights[~fold_masks])))
            self.assertTrue(
                {"normative_fiber_grid_metrics", "normative_fiber_source_resolution"}
                <= {artifact.kind for artifact in result.artifacts}
            )

    def test_grid_and_selected_cell_scan_coverage_once_per_tau(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        with tempfile.TemporaryDirectory() as temporary:
            backend = ReferenceFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "fiber_test", "1"),
                feature_chunk_size=11,
            )
            with mock.patch.object(
                reference_module,
                "coverage_counts",
                wraps=reference_module.coverage_counts,
            ) as count_coverage:
                result = backend.run(request)

        self.assertIsNotNone(result.source)
        self.assertEqual(
            count_coverage.call_count,
            len(set(request.source_grid.tau_values)),
        )
        self.assertEqual(
            [float(call.args[1]) for call in count_coverage.call_args_list],
            list(request.source_grid.tau_values),
        )

    def test_sensitive_role_emits_grid_only_then_formal_cell_evidence(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        formal_request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        sensitive_request = _request(
            "sensitive",
            exposure * 0.98,
            outcome,
            baseline,
            fiber_ids + 1_000,
            connectome_id="connectome_sensitive",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            formal = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "formal", "fiber_test", "1"),
                feature_chunk_size=13,
            ).run(formal_request)
            assert formal.source is not None
            sensitive_backend = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "sensitive", "fiber_test", "1"),
                feature_chunk_size=13,
            )
            observed = sensitive_backend.run(sensitive_request)
            self.assertIsNone(observed.source)
            self.assertEqual(
                {artifact.kind for artifact in observed.artifacts},
                {"normative_fiber_grid_metrics"},
            )
            evidence = sensitive_backend.evaluate_sensitive_at_formal_source(
                sensitive_request,
                formal.source,
            )
            self.assertEqual(evidence.cell_computability_status, "computable")
            self.assertEqual(evidence.evaluated_tau, formal.source.selected_tau)
            self.assertEqual(evidence.evaluated_coverage, formal.source.selected_coverage)
            self.assertFalse(hasattr(evidence, "source_status"))
            self.assertIsNotNone(evidence.feature_axis)

    def test_absent_grid_returns_no_selected_feature_axis(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        request = _request(
            "formal",
            np.full_like(exposure, 50.0),
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = ReferenceFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "fiber_test", "1"),
                feature_chunk_size=9,
            ).run(request)
            assert result.source is not None
            self.assertEqual(result.source.source_status, "absent_no_stable_grid")
            self.assertEqual(result.source.prediction_status, "not_applicable")
            self.assertIsNone(result.source.feature_axis)

    def test_formal_role_selects_nearest_stable_scan_fallback(self) -> None:
        _, outcome, baseline, fiber_ids = _synthetic_inputs()
        latent = np.linspace(-1.5, 1.5, 12)
        loading = np.linspace(0.8, 1.2, 48)
        subject = np.arange(12, dtype=float)[:, None]
        fiber = np.arange(48, dtype=float)[None, :]
        exposure = (
            190.0
            + 4.0 * latent[:, None] * loading[None, :]
            + 0.1 * np.sin((subject + 1.0) * (fiber + 1.0))
        )
        request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        request = dataclasses.replace(
            request,
            source_grid=SourceGrid(200, 3, (150, 180, 200), (3, 4), 2),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = ReferenceFiberBackend(
                RunScopedArtifactPublisher(Path(temporary), "fiber_test", "1"),
                feature_chunk_size=9,
            ).run(request)
            assert result.source is not None
            self.assertEqual(result.source.source_status, "scan_fallback_accepted")
            self.assertEqual(result.source.threshold_source, "scan_fallback")
            self.assertEqual(result.source.selected_tau, 180)
            self.assertEqual(result.source.selected_coverage, 3)

    def test_sensitive_formal_cell_can_be_noncomputable_without_becoming_a_source(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        formal_request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        sensitive_request = _request(
            "sensitive",
            np.full_like(exposure, 50.0),
            outcome,
            baseline,
            fiber_ids + 2_000,
            connectome_id="connectome_sensitive",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            formal = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "formal", "fiber_test", "1"),
                feature_chunk_size=13,
            ).run(formal_request)
            assert formal.source is not None
            sensitive_backend = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "sensitive", "fiber_test", "1"),
                feature_chunk_size=13,
            )
            evidence = sensitive_backend.evaluate_sensitive_at_formal_source(
                sensitive_request,
                formal.source,
            )
            self.assertEqual(evidence.cell_computability_status, "not_computable")
            self.assertEqual(evidence.prediction_status, "not_applicable")
            self.assertIsNone(evidence.feature_axis)
            self.assertEqual(
                {artifact.kind for artifact in evidence.artifacts},
                {"normative_fiber_sensitive_cell_evidence"},
            )

    def test_heldout_outcome_does_not_change_its_fold_operator_or_prediction(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        changed_outcome = outcome.copy()
        changed_outcome[0] += 1000.0
        first_request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        second_request = dataclasses.replace(first_request, outcome=changed_outcome)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "first", "fiber_test", "1"),
                feature_chunk_size=7,
            ).run(first_request)
            second = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "second", "fiber_test", "1"),
                feature_chunk_size=7,
            ).run(second_request)
            first_ids = _artifact_array(first, "normative_fiber_valid_union_ids")
            second_ids = _artifact_array(second, "normative_fiber_valid_union_ids")
            np.testing.assert_array_equal(first_ids, second_ids)
            first_fold_weights = _artifact_array(
                first,
                "loocv_benefit_oriented_fiber_weights",
            )
            second_fold_weights = _artifact_array(
                second,
                "loocv_benefit_oriented_fiber_weights",
            )
            np.testing.assert_allclose(
                first_fold_weights[0],
                second_fold_weights[0],
                equal_nan=True,
            )
            first_predictions = _artifact_array(
                first,
                "normative_fiber_loocv_model_predictions",
            )
            second_predictions = _artifact_array(
                second,
                "normative_fiber_loocv_model_predictions",
            )
            self.assertEqual(first_predictions[0], second_predictions[0])

    def test_artifact_backed_large_axes_use_read_only_memory_mapping(self) -> None:
        exposure, outcome, baseline, fiber_ids = _synthetic_inputs()
        array_request = _request(
            "formal",
            exposure,
            outcome,
            baseline,
            fiber_ids,
            connectome_id="connectome_formal",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()

            def artifact(
                name: str,
                array: np.ndarray,
                axes: tuple[AxisRef, ...],
                *,
                units: str | None,
                space: str | None,
            ) -> ArtifactRef:
                path = inputs / f"{name}.npy"
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
                    space=space,
                    producer_id="fiber_test",
                    producer_version="1",
                )

            exposure_ref = artifact(
                "exposure",
                exposure,
                (array_request.subject_axis, array_request.feature_axis),
                units="V/m",
                space="synthetic_space",
            )
            outcome_ref = artifact(
                "outcome",
                outcome,
                (array_request.subject_axis,),
                units="score",
                space=None,
            )
            baseline_ref = artifact(
                "baseline",
                baseline,
                (array_request.subject_axis,),
                units="score",
                space=None,
            )
            ids_ref = artifact(
                "feature_ids",
                fiber_ids,
                (array_request.feature_axis,),
                units=None,
                space="synthetic_space",
            )

            class SpyStore(ArtifactStore):
                def __init__(self, allowed_roots: tuple[Path, ...]) -> None:
                    super().__init__(allowed_roots)
                    self.calls: list[tuple[str, str | None]] = []

                def materialize(self, value: ArtifactRef, **requirements: object) -> np.ndarray:
                    self.calls.append((value.kind, requirements.get("mmap_mode")))
                    return super().materialize(value, **requirements)

            store = SpyStore((inputs,))
            request = dataclasses.replace(
                array_request,
                exposure=exposure_ref,
                outcome=outcome_ref,
                baseline=baseline_ref,
                feature_ids=ids_ref,
            )
            result = ReferenceFiberBackend(
                RunScopedArtifactPublisher(root / "output", "fiber_test", "1"),
                artifact_store=store,
                feature_chunk_size=9,
            ).run(request)
            self.assertIsNotNone(result.source)
            self.assertEqual(
                store.calls,
                [
                    ("exposure", "r"),
                    ("outcome", None),
                    ("baseline", None),
                    ("feature_ids", "r"),
                ],
            )


class CompletedFiberFixtureContractTest(unittest.TestCase):
    frozen_manifest = (
        Path(__file__).resolve().parents[3]
        / "projects/stnsnr/acceptance/frozen/20260711T034644Z_d318f177f7f2ac7d"
        / "bounded_fixture_manifest.json"
    )
    task_pairs = {
        "dtor": ("task_075e4d68a6dabf3a18c7", "task_51c47d4ff4d99bac88de"),
        "mgh": ("task_76866eb0c55bb0ad884e", "task_7c6a215126b9dc8235e4"),
        "ppmi": ("task_8b9b8c4b0f6df58f27a6", "task_83e88470fbb15079e217"),
    }

    @unittest.skipUnless(
        frozen_manifest.is_file(),
        "completed bounded reference-fiber fixtures are unavailable",
    )
    def test_frozen_tasks_support_bounded_scalar_and_artifact_contract(self) -> None:
        frozen = json.loads(self.frozen_manifest.read_text(encoding="utf-8"))
        self.assertEqual(frozen["source_run_id"], "20260711T034644Z_d318f177f7f2ac7d")
        tasks = {task["task_id"]: task for task in frozen["eligible_tasks"]}
        formal_selection: tuple[float, int] | None = None
        for connectome, (observed_id, resolver_id) in self.task_pairs.items():
            with self.subTest(connectome=connectome):
                observed = tasks[observed_id]
                resolver = tasks[resolver_id]
                self.assertEqual(observed["status"], "completed")
                self.assertEqual(resolver["status"], "completed")
                self.assertEqual(observed["connectome_id"], connectome)
                self.assertEqual(resolver["connectome_id"], connectome)
                self.assertEqual(observed["parent_scale_id"], "mds_updrs_iii_score")
                self.assertEqual(observed["endpoint_model_id"], resolver["endpoint_model_id"])

                observed_artifacts = {item["kind"]: item for item in observed["artifacts"]}
                resolver_artifacts = {item["kind"]: item for item in resolver["artifacts"]}
                consumed = (
                    observed["task_manifest"],
                    resolver["task_manifest"],
                    observed_artifacts["loocv_predictions"],
                    observed_artifacts["observed_metrics"],
                    resolver_artifacts["selected_fold_scores"],
                    resolver_artifacts["selected_manifest"],
                    resolver_artifacts["selected_scores"],
                    resolver_artifacts["selected_source"],
                    resolver_artifacts["selected_valid_fiber_ids"],
                    resolver_artifacts["source_status"],
                )
                for artifact in consumed:
                    path = Path(artifact["path"])
                    self.assertTrue(path.is_file(), path)
                    self.assertEqual(sha256_file(path), artifact["sha256"], path)
                self.assertEqual(
                    observed_artifacts["loocv_predictions"]["sha256"],
                    resolver_artifacts["selected_fold_scores"]["sha256"],
                )

                selected_source = json.loads(
                    Path(resolver_artifacts["selected_source"]["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                source_status = json.loads(
                    Path(resolver_artifacts["source_status"]["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                selected_manifest = json.loads(
                    Path(resolver_artifacts["selected_manifest"]["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    selected_source["hf_norm_fiber_source_status"],
                    "pre_specified_accepted",
                )
                self.assertEqual(
                    selected_source["hf_norm_fiber_prediction_status"],
                    "error_nonpredictive",
                )
                self.assertEqual(
                    selected_source["hf_norm_fiber_threshold_source"],
                    "pre_specified",
                )
                selection = (
                    float(selected_source["hf_norm_fiber_selected_tau_v_per_m"]),
                    int(selected_source["hf_norm_fiber_selected_coverage"]),
                )
                self.assertEqual(selection, (800.0, 5))
                self.assertEqual(
                    source_status["hf_norm_fiber_source_status"],
                    selected_source["hf_norm_fiber_source_status"],
                )
                if connectome == "dtor":
                    formal_selection = selection
                else:
                    self.assertEqual(selection, formal_selection)

                valid_ids = np.load(
                    resolver_artifacts["selected_valid_fiber_ids"]["path"],
                    allow_pickle=False,
                    mmap_mode="r",
                )
                self.assertEqual(valid_ids.dtype, np.dtype("int64"))
                self.assertEqual(np.unique(valid_ids).size, valid_ids.size)
                qc = selected_manifest["qc"]
                self.assertEqual(
                    valid_ids.size,
                    qc["n_positive_valid_fibers"] + qc["n_negative_valid_fibers"],
                )
                self.assertEqual(qc["sweet_selected_k_min"], 200)
                self.assertEqual(qc["sour_selected_k_min"], 100)
                self.assertEqual(qc["weighted_peak_k_min"], 20)
                self.assertTrue(qc["all_predictions_finite"])

        self.assertEqual(formal_selection, (800.0, 5))


if __name__ == "__main__":
    unittest.main()
