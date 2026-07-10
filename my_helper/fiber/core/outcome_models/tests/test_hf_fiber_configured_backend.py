"""Executable contract for the configured legacy HF normative-fiber backend."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import h5py
import numpy as np

from outcome_models.catalog import CatalogStatus, EndpointRecord
from outcome_models.config import ConnectomeSpec
from outcome_models.identity import EndpointModelKey
from outcome_models.services import legacy_hf_fiber
from outcome_models.services.legacy_hf_fiber import (
    HFNormativeFiberResolverPolicy,
    build_legacy_hf_fiber_config,
    run_configured_hf_fiber_control,
    run_configured_hf_fiber_primary,
    run_configured_hf_fiber_resolver,
    run_configured_hf_fiber_sensitivity,
    run_configured_hf_fiber_sidecar,
)
from outcome_models.services.observed import FeatureAxisRef, HFNormativeFiberRequest, ObservedServiceOutput
import stnsnr_hf_normative_fiber_smoke as hf_fiber_analysis
from stnsnr_hf_normative_fiber_smoke import (
    HFNormativeFiberAnalysisConfig,
    SidecarValidationError,
    baseline_nuisance_design_valid_all_folds,
    build_arg_parser as build_legacy_arg_parser,
    build_exposure_sidecar_contract,
    file_identity,
    fixed_count_fiber_net_score,
    hf_fiber_artifact_names,
    hf_fiber_primary_branch_name,
    compute_plain_connected_control,
    normative_fiber_hard_computability_passes,
    resolve_normative_fiber_source,
    run_hf_normative_fiber_cheap_observed_sensitivity_configured,
    validate_completed_exposure_sidecar,
    write_sidecar_completion_manifest_atomic,
)


def _request(root: Path) -> HFNormativeFiberRequest:
    endpoint = EndpointRecord(
        key=EndpointModelKey("study", "scale", "chronic", "hf_fiber", "custom"),
        endpoint_model_id="endpoint_model",
        scale_label="Configured Scale",
        direction="higher",
        outcome_protocol="CUSTOM_PROTOCOL",
        outcome_phase="9m",
        hf_reference_protocol="CUSTOM_PROTOCOL",
        hf_reference_phase="9m",
        n_subjects=3,
        subject_ids=("sub-03", "sub-01", "sub-02"),
        status=CatalogStatus.DATA_AVAILABLE,
        failure_reasons=(),
    )
    return HFNormativeFiberRequest(
        endpoint=endpoint,
        connectome=ConnectomeSpec(
            connectome_id="custom",
            label="Custom Connectome",
            path=root / "connectome.mat",
            fiber_identity_source="data.mat:idx",
        ),
        clinical_table=root / "clinical.csv",
        stimulation_table=root / "stimulation.csv",
        derivatives_root=root / "derivatives",
        asset_root=root / "assets",
        model_root=root / "model",
        output_root=root / "model" / "tasks" / "task-primary",
        tau_grid=(125.0, 275.0, 425.0),
        coverage_grid=(2, 3),
        primary_tau=275.0,
        primary_coverage=3,
        score={
            "sweet_fraction": 0.01,
            "sour_fraction": 0.005,
            "weighted_peak_fraction": 0.05,
            "sweet_selected_min_count": 200,
            "sour_selected_min_count": 100,
            "weighted_peak_min_count": 20,
        },
        cheap_observed_sensitivity={
            "high_tau_v_per_m": 425.0,
            "coverage": 3,
            "sweet_top_count": 7,
            "sour_top_count": 5,
        },
        force=False,
    )


class ConfiguredRequestTests(unittest.TestCase):
    def test_config_maps_every_scientific_identity_without_legacy_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            policy = HFNormativeFiberResolverPolicy(minimum_adjacent_passing_cells=4)
            config = build_legacy_hf_fiber_config(request, resolver_policy=policy, max_fibers=17)

        self.assertEqual(config.endpoint_protocol, "CUSTOM_PROTOCOL")
        self.assertEqual(config.endpoint_phase, "9m")
        self.assertEqual(config.scale_direction, "higher")
        self.assertEqual(config.subject_order, ("sub-03", "sub-01", "sub-02"))
        self.assertEqual(config.clinical_table, request.clinical_table)
        self.assertEqual(config.stimulation_table, request.stimulation_table)
        self.assertEqual(config.connectome_path, request.connectome.path)
        self.assertEqual(config.connectome_identity_source, "data.mat:idx")
        self.assertEqual(config.tau_grid, request.tau_grid)
        self.assertEqual(config.coverage_grid, request.coverage_grid)
        self.assertEqual(config.primary_tau, 275.0)
        self.assertEqual(config.primary_coverage, 3)
        self.assertEqual(config.sweet_selected_min_count, 200)
        self.assertEqual(config.sour_selected_min_count, 100)
        self.assertEqual(config.weighted_peak_min_count, 20)
        self.assertEqual(config.resolver_minimum_adjacent_passing_cells, 4)
        self.assertEqual(config.max_fibers, 17)
        self.assertEqual(config.output_dir, request.output_root)
        self.assertIn(request.model_root / "cache", config.preprocess_dir.parents)
        self.assertTrue(config.dynamic_names)

    def test_dynamic_names_include_actual_tau_and_coverage(self) -> None:
        self.assertEqual(hf_fiber_primary_branch_name(275.0, 3), "peak_efield_tau275_cov3_primary")
        names = hf_fiber_artifact_names(275.0, 3, dynamic=True)
        self.assertIn("tau275_cov3", names["weights_csv"])
        self.assertIn("tau275_cov3", names["coverage_npy"])
        self.assertIn("tau275_cov3", names["resolver_scan_csv"])

    def test_legacy_wrapper_defaults_and_artifact_names_are_preserved(self) -> None:
        args = build_legacy_arg_parser().parse_args([])
        self.assertEqual((args.connectome, args.tau, args.min_coverage), ("ppmi", 800.0, 5))
        self.assertEqual(hf_fiber_primary_branch_name(args.tau, args.min_coverage, legacy=True), "peak_efield_tau800_primary")
        names = hf_fiber_artifact_names(args.tau, args.min_coverage, dynamic=False)
        self.assertEqual(names["weights_csv"], "normative_HF_fiber_weights.csv")
        self.assertEqual(names["coverage_column"], "coverage_tau800")

    def test_primary_and_resolver_runners_return_typed_outputs_with_feature_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            ids_path = request.model_root / "cache" / "fiber_ids.npy"
            primary_metrics = request.output_root / "primary_metrics.json"
            predictions = request.output_root / "predictions.csv"
            resolver_paths = {
                kind: request.output_root / f"{kind}.artifact"
                for kind in (
                    "source_status",
                    "selected_source",
                    "selected_manifest",
                    "selected_scores",
                    "selected_full_weights",
                    "selected_fold_weights",
                    "selected_fold_scores",
                )
            }
            resolver_paths["exposure_matrix"] = request.model_root / "cache" / "exposure.npy"
            for path in (ids_path, primary_metrics, predictions, *resolver_paths.values()):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test\n", encoding="utf-8")
            feature_axis = {
                "ids_path": str(ids_path),
                "count": 13,
                "sha256": "a" * 64,
                "identity_source": "data.mat:idx",
            }
            fake_analysis = SimpleNamespace(
                run_hf_normative_fiber_primary_configured=lambda config: {
                    "source_status": "not_applicable",
                    "prediction_status": "not_applicable",
                    "threshold_source": "pre_specified",
                    "selected_tau": config.primary_tau,
                    "selected_coverage": config.primary_coverage,
                    "adjacent_support": None,
                    "subject_order": list(config.subject_order),
                    "feature_axis": feature_axis,
                    "artifacts": {
                        "observed_metrics": str(primary_metrics),
                        "loocv_predictions": str(predictions),
                    },
                },
                run_hf_normative_fiber_resolver_configured=lambda config: {
                    "source_status": "scan_fallback_accepted",
                    "prediction_status": "error_predictive",
                    "threshold_source": "scan_fallback",
                    "selected_tau": 425.0,
                    "selected_coverage": 2,
                    "adjacent_support": 5,
                    "subject_order": list(config.subject_order),
                    "feature_axis": feature_axis,
                    "artifacts": {kind: str(path) for kind, path in resolver_paths.items()},
                },
            )
            with patch.object(legacy_hf_fiber, "_load_legacy_analysis", return_value=fake_analysis):
                primary = run_configured_hf_fiber_primary(request)
                resolver = run_configured_hf_fiber_resolver(request)

        self.assertIsInstance(primary, ObservedServiceOutput)
        self.assertIsInstance(primary.feature_axis, FeatureAxisRef)
        self.assertEqual(primary.feature_axis.count, 13)
        self.assertEqual({artifact.kind for artifact in primary.artifacts}, {"observed_metrics", "loocv_predictions"})
        self.assertIsInstance(resolver, ObservedServiceOutput)
        self.assertEqual(resolver.source_status, "scan_fallback_accepted")
        self.assertEqual(resolver.adjacent_support, 5)
        self.assertEqual(
            {artifact.kind for artifact in resolver.artifacts},
            {
                "source_status",
                "selected_source",
                "selected_manifest",
                "exposure_matrix",
                "selected_scores",
                "selected_full_weights",
                "selected_fold_weights",
                "selected_fold_scores",
            },
        )

    def test_runner_rejects_backend_subject_order_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            ids_path = request.model_root / "cache" / "fiber_ids.npy"
            ids_path.parent.mkdir(parents=True, exist_ok=True)
            ids_path.write_text("test\n", encoding="utf-8")
            fake_analysis = SimpleNamespace(
                run_hf_normative_fiber_primary_configured=lambda config: {
                    "source_status": "not_applicable",
                    "prediction_status": "not_applicable",
                    "threshold_source": "pre_specified",
                    "selected_tau": config.primary_tau,
                    "selected_coverage": config.primary_coverage,
                    "adjacent_support": None,
                    "subject_order": ["sub-01", "sub-03", "sub-02"],
                    "feature_axis": {
                        "ids_path": str(ids_path),
                        "count": 1,
                        "sha256": "a" * 64,
                        "identity_source": "data.mat:idx",
                    },
                    "artifacts": {},
                }
            )
            with patch.object(legacy_hf_fiber, "_load_legacy_analysis", return_value=fake_analysis):
                with self.assertRaisesRegex(RuntimeError, "subject order"):
                    run_configured_hf_fiber_primary(request)

    def test_all_observed_stage_artifact_runners_return_exact_planner_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            artifacts = {
                "sidecar_index": request.output_root / "sidecar_index.json",
                "qc": request.output_root / "qc.json",
                "control_metrics": request.output_root / "control_metrics.json",
                "sensitivity_results": request.output_root / "sensitivity_results.json",
            }
            for path in artifacts.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            fake_analysis = SimpleNamespace(
                run_hf_normative_fiber_sidecar_configured=lambda config: {
                    "artifacts": {
                        "sidecar_index": str(artifacts["sidecar_index"]),
                        "qc": str(artifacts["qc"]),
                    }
                },
                run_hf_normative_fiber_plain_connected_control_configured=lambda config: {
                    "artifacts": {"control_metrics": str(artifacts["control_metrics"])}
                },
                run_hf_normative_fiber_cheap_observed_sensitivity_configured=lambda config: {
                    "artifacts": {"sensitivity_results": str(artifacts["sensitivity_results"])}
                },
            )
            with patch.object(legacy_hf_fiber, "_load_legacy_analysis", return_value=fake_analysis):
                sidecar = run_configured_hf_fiber_sidecar(request)
                control = run_configured_hf_fiber_control(request)
                sensitivity = run_configured_hf_fiber_sensitivity(request)
                artifacts_exist = all(
                    artifact.path.is_file() for artifact in (*sidecar, *control, *sensitivity)
                )

        self.assertEqual([artifact.kind for artifact in sidecar], ["qc", "sidecar_index"])
        self.assertEqual([artifact.kind for artifact in control], ["control_metrics"])
        self.assertEqual([artifact.kind for artifact in sensitivity], ["sensitivity_results"])
        self.assertTrue(artifacts_exist)


class ObservedStageKernelTests(unittest.TestCase):
    def test_plain_control_computes_documented_exposures_and_four_loocv_models(self) -> None:
        rng = np.random.default_rng(42)
        x = rng.uniform(0.0, 4.0, size=(12, 80)).astype(np.float32)
        y_base = np.linspace(3.0, 20.0, 12)
        y_post = 0.4 * y_base - 1.5 * x[:, 0] + rng.normal(0.0, 0.2, size=12)
        result = compute_plain_connected_control(
            x=x,
            fiber_ids=np.arange(1, 81, dtype=np.int64),
            y_post=y_post,
            y_base=y_base,
            subject_ids=[f"sub-{index:02d}" for index in range(12)],
            scale_direction="lower",
            tau=1.0,
            min_coverage=3,
        )

        expected_touched = x[0] > 1.0
        first = result["subject_rows"][0]
        self.assertEqual(first["PlainTouchedCount"], int(np.count_nonzero(expected_touched)))
        self.assertAlmostEqual(first["PlainExposureSum"], float(np.sum(x[0].astype(float))))
        expected_top_count = max(1, int(np.ceil(0.05 * np.count_nonzero(expected_touched))))
        expected_top5 = float(np.mean(np.sort(x[0, expected_touched].astype(float))[-expected_top_count:]))
        self.assertAlmostEqual(first["PlainExposureTop5"], expected_top5)
        self.assertEqual(
            {row["model"] for row in result["model_rows"]},
            {"baseline_only", "plain_plus_baseline", "net_plus_baseline", "joint_net_plain_baseline"},
        )
        self.assertEqual(result["source_classification_feedback"], "none")

    def test_top_count_sensitivity_uses_fixed_1500_positive_and_500_negative_fibers(self) -> None:
        exposure = np.ones((3, 2500), dtype=np.float32)
        weights = np.concatenate(
            [np.linspace(2.0, 0.1, 1800), -np.linspace(0.1, 2.0, 700)]
        )
        score = fixed_count_fiber_net_score(
            exposure,
            weights,
            np.ones(2500, dtype=bool),
            fiber_ids=np.arange(1, 2501, dtype=np.int64),
            sweet_count=1500,
            sour_count=500,
            peak_fraction=0.05,
        )
        self.assertEqual(score.sweet_fiber_ids.size, 1500)
        self.assertEqual(score.sour_fiber_ids.size, 500)
        self.assertEqual(score.n_sweet_peak_fibers, 75)
        self.assertEqual(score.n_sour_peak_fibers, 25)

    def test_sensitivity_failures_are_recorded_per_branch_without_source_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = HFNormativeFiberAnalysisConfig(
                scale="Scale",
                endpoint_protocol="STN",
                endpoint_phase="3m",
                scale_direction="lower",
                subject_order=tuple(f"sub-{index:02d}" for index in range(6)),
                clinical_table=root / "clinical.csv",
                stimulation_table=root / "stimulation.csv",
                derivatives_root=root / "derivatives",
                repo_root=root,
                matlab_bin=root / "matlab",
                connectome_id="custom",
                connectome_label="Custom",
                connectome_path=root / "data.mat",
                connectome_identity_source="data.mat:idx",
                output_dir=root / "task",
                preprocess_dir=root / "cache",
                tau_grid=(400.0, 800.0, 1500.0),
                coverage_grid=(5,),
                primary_tau=800.0,
                primary_coverage=5,
            )
            records = [
                SimpleNamespace(subject_id=subject_id, y_post=float(index + 2), y_base=float(index + 1))
                for index, subject_id in enumerate(config.subject_order)
            ]
            x = np.zeros((6, 20), dtype=np.float32)
            fiber_ids = np.arange(1, 21, dtype=np.int64)
            with patch.object(hf_fiber_analysis, "_load_configured_records", return_value=records), patch.object(
                hf_fiber_analysis,
                "_load_completed_exposure_for_config",
                return_value=(x, fiber_ids, {"status": "complete"}),
            ):
                result = run_hf_normative_fiber_cheap_observed_sensitivity_configured(config)
            payload = json.loads(Path(result["artifacts"]["sensitivity_results"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["source_classification_feedback"], "none")
        self.assertEqual(payload["overall_status"], "complete_with_branch_failures")
        self.assertEqual(
            {row["branch_status"] for row in payload["branches"]},
            {"candidate_empty_or_threshold_too_strict"},
        )
        self.assertEqual(payload["public_configured_spec"]["high_threshold_tau_v_per_m"], 1500.0)
        self.assertEqual(payload["public_configured_spec"]["top_positive_fibers"], 1500)
        self.assertEqual(payload["public_configured_spec"]["top_negative_fibers"], 500)

    def test_scan_fallback_materializes_immutable_selected_source_arrays_and_scores(self) -> None:
        rng = np.random.default_rng(7)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = HFNormativeFiberAnalysisConfig(
                scale="Scale",
                endpoint_protocol="STN",
                endpoint_phase="3m",
                scale_direction="lower",
                subject_order=tuple(f"sub-{index:02d}" for index in range(12)),
                clinical_table=root / "clinical.csv",
                stimulation_table=root / "stimulation.csv",
                derivatives_root=root / "derivatives",
                repo_root=root,
                matlab_bin=root / "matlab",
                connectome_id="custom",
                connectome_label="Custom",
                connectome_path=root / "data.mat",
                connectome_identity_source="data.mat:idx",
                output_dir=root / "task",
                preprocess_dir=root / "cache",
                tau_grid=(1.0, 1.5, 2.0),
                coverage_grid=(3, 4),
                primary_tau=1.0,
                primary_coverage=3,
            )
            config.output_dir.mkdir(parents=True)
            config.preprocess_dir.mkdir(parents=True)
            x = rng.uniform(0.0, 4.0, size=(12, 90)).astype(np.float32)
            np.save(config.preprocess_dir / "X_HF_fiber_float32_subject_major.npy", x)
            fiber_ids = np.arange(1, 91, dtype=np.int64)
            y_base = np.linspace(2.0, 15.0, 12)
            y_post = 0.5 * y_base - 1.2 * x[:, 0] + rng.normal(0.0, 0.3, size=12)
            artifacts = hf_fiber_analysis._materialize_selected_source_artifacts(
                config=config,
                x=x,
                fiber_ids=fiber_ids,
                y_post=y_post,
                y_base=y_base,
                subject_ids=list(config.subject_order),
                selected_tau=1.5,
                selected_coverage=4,
                source_status="scan_fallback_accepted",
                prediction_status="error_predictive",
            )
            manifest = json.loads(Path(artifacts["selected_manifest"]).read_text(encoding="utf-8"))
            full_weights = np.load(artifacts["selected_full_weights"])
            fold_weights = np.load(artifacts["selected_fold_weights"])

        self.assertEqual(manifest["source_status"], "scan_fallback_accepted")
        self.assertEqual((manifest["selected_tau_v_per_m"], manifest["selected_coverage"]), (1.5, 4))
        self.assertEqual(full_weights.shape, (90,))
        self.assertEqual(fold_weights.shape, (12, 90))
        self.assertEqual(
            set(artifacts),
            {
                "selected_manifest",
                "exposure_matrix",
                "selected_scores",
                "selected_full_weights",
                "selected_fold_weights",
                "selected_fold_scores",
            },
        )


class ResolverValidityTests(unittest.TestCase):
    @staticmethod
    def _passing_row(tau: float, coverage: int) -> dict[str, object]:
        return {
            "connectome": "ppmi",
            "tau": tau,
            "coverage": coverage,
            "n_subjects": 16,
            "fold_n_candidate_fibers_min": 200,
            "selected_fiber_pools_computable": True,
            "netfiberscore_nonconstant_all_folds": True,
            "y_base_nuisance_design_valid": True,
            "all_predictions_finite": True,
            "mae_model": 8.0,
            "mae_baseline": 10.0,
            "rmse_model": 9.0,
            "rmse_baseline": 11.0,
        }

    def test_string_booleans_never_pass_hard_computability(self) -> None:
        row = self._passing_row(275.0, 3)
        row["all_predictions_finite"] = "False"
        self.assertFalse(normative_fiber_hard_computability_passes(row))
        row["all_predictions_finite"] = "True"
        self.assertFalse(normative_fiber_hard_computability_passes(row))

    def test_nuisance_design_must_be_valid_in_every_training_fold(self) -> None:
        self.assertFalse(baseline_nuisance_design_valid_all_folds(np.array([0.0, 0.0, 0.0, 1.0])))
        self.assertTrue(baseline_nuisance_design_valid_all_folds(np.array([0.0, 1.0, 2.0, 3.0])))

    def test_resolver_uses_configured_grid_primary_cell_and_adjacency_policy(self) -> None:
        rows = [self._passing_row(275.0, 3), self._passing_row(425.0, 3)]
        accepted = resolve_normative_fiber_source(
            rows,
            connectome="ppmi",
            tau_grid=(125.0, 275.0, 425.0),
            coverage_grid=(2, 3),
            primary_tau=275.0,
            primary_coverage=3,
            minimum_adjacent_passing_cells=1,
        )
        rejected = resolve_normative_fiber_source(
            rows,
            connectome="ppmi",
            tau_grid=(125.0, 275.0, 425.0),
            coverage_grid=(2, 3),
            primary_tau=275.0,
            primary_coverage=3,
            minimum_adjacent_passing_cells=2,
        )
        self.assertEqual(accepted["hf_norm_fiber_source_status"], "pre_specified_accepted")
        self.assertEqual(rejected["hf_norm_fiber_source_status"], "absent_no_stable_grid")

    def test_resolver_preserves_noninteger_tau_grid_identity(self) -> None:
        rows = [self._passing_row(275.5, 3), self._passing_row(425.25, 3)]
        resolved = resolve_normative_fiber_source(
            rows,
            connectome="ppmi",
            tau_grid=(125.75, 275.5, 425.25),
            coverage_grid=(2, 3),
            primary_tau=275.5,
            primary_coverage=3,
            minimum_adjacent_passing_cells=1,
        )
        self.assertEqual(resolved["hf_norm_fiber_source_status"], "pre_specified_accepted")
        self.assertEqual(resolved["hf_norm_fiber_selected_tau_v_per_m"], 275.5)


class SidecarCompletionTests(unittest.TestCase):
    def _fixture(self, root: Path):
        data_mat = root / "data.mat"
        with h5py.File(data_mat, "w") as handle:
            handle.create_dataset("idx", data=np.array([[2, 3, 1]], dtype=np.int64))
        clinical = root / "clinical.csv"
        clinical.write_text("ID,Value\nsub-01,1\n", encoding="utf-8")
        records = [SimpleNamespace(subject_id="sub-01"), SimpleNamespace(subject_id="sub-02")]
        input_identities = {"clinical_table": file_identity(clinical)}
        contract = build_exposure_sidecar_contract(
            data_mat,
            records,
            max_fibers=2,
            input_identities=input_identities,
        )
        output_npy = root / "X.npy"
        fiber_ids_npy = root / "fiber_ids.npy"
        completion_json = root / "sidecar_completion.json"
        np.save(output_npy, np.arange(4, dtype=np.float32).reshape(2, 2))
        np.save(fiber_ids_npy, np.array([1, 2], dtype=np.int64))
        write_sidecar_completion_manifest_atomic(
            completion_json,
            contract=contract,
            output_npy=output_npy,
            fiber_ids_npy=fiber_ids_npy,
        )
        return data_mat, records, input_identities, contract, output_npy, fiber_ids_npy, completion_json

    def test_complete_matching_sidecar_is_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, _, contract, output_npy, fiber_ids_npy, completion_json = self._fixture(root)
            manifest = validate_completed_exposure_sidecar(
                output_npy,
                fiber_ids_npy,
                completion_json,
                expected_contract=contract,
            )

        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["shape"], [2, 2])
        self.assertEqual(manifest["subject_order"], ["sub-01", "sub-02"])

    def test_subject_order_mismatch_and_partial_sidecars_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_mat, records, inputs, contract, output_npy, fiber_ids_npy, completion_json = self._fixture(root)
            reversed_contract = build_exposure_sidecar_contract(
                data_mat,
                list(reversed(records)),
                max_fibers=2,
                input_identities=inputs,
            )
            with self.assertRaisesRegex(SidecarValidationError, "subject_order"):
                validate_completed_exposure_sidecar(
                    output_npy,
                    fiber_ids_npy,
                    completion_json,
                    expected_contract=reversed_contract,
                )
            completion_json.unlink()
            with self.assertRaisesRegex(SidecarValidationError, "completion manifest"):
                validate_completed_exposure_sidecar(
                    output_npy,
                    fiber_ids_npy,
                    completion_json,
                    expected_contract=contract,
                )

    def test_mutated_fiber_axis_and_input_identity_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, _, contract, output_npy, fiber_ids_npy, completion_json = self._fixture(root)
            np.save(fiber_ids_npy, np.array([2, 1], dtype=np.int64))
            with self.assertRaisesRegex(SidecarValidationError, "fiber-axis"):
                validate_completed_exposure_sidecar(
                    output_npy,
                    fiber_ids_npy,
                    completion_json,
                    expected_contract=contract,
                )

            manifest = json.loads(completion_json.read_text(encoding="utf-8"))
            manifest["input_identities"]["clinical_table"]["sha256"] = "0" * 64
            completion_json.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(SidecarValidationError, "input_identities"):
                validate_completed_exposure_sidecar(
                    output_npy,
                    fiber_ids_npy,
                    completion_json,
                    expected_contract=contract,
                )


if __name__ == "__main__":
    unittest.main()
