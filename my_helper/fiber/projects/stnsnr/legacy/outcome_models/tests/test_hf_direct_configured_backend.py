"""Contract tests for the configured legacy HF direct-voxel backend."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import nibabel as nib

CORE_ROOT = Path(__file__).resolve().parents[5] / "core"
ANALYSIS_ROOT = CORE_ROOT / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from outcome_models.catalog import CatalogStatus, EndpointRecord
from outcome_models.identity import EndpointModelKey
from outcome_models.services.legacy_hf_direct import (
    run_configured_hf_direct,
    run_configured_hf_direct_sidecars,
)
from outcome_models.services.observed import HFDirectVoxelRequest
from stnsnr_hf_direct_voxel_posthoc_threshold_scan import (
    ConfiguredHFDirectVoxelRun,
    cache_completion_metadata,
    configured_cache_manifest_name,
    configured_manifest_name,
    configured_scan_directory,
    materialize_configured_hf_direct_source,
    validate_preprocess_cache,
    write_atomic_json,
)
from stnsnr_hf_direct_voxel_smoke import primary_branch_name


def _endpoint() -> EndpointRecord:
    key = EndpointModelKey(
        study_id="configured-study",
        scale_id="motor_score",
        endpoint_phase="chronic",
        model_family="hf_voxel",
    )
    return EndpointRecord(
        key=key,
        endpoint_model_id=key.identifier,
        scale_label="Motor score",
        direction="lower",
        outcome_protocol="STN",
        outcome_phase="3m",
        hf_reference_protocol="STN",
        hf_reference_phase="3m",
        n_subjects=3,
        subject_ids=("sub-01", "sub-02", "sub-03"),
        status=CatalogStatus.DATA_AVAILABLE,
        failure_reasons=(),
    )


def _request(root: Path) -> HFDirectVoxelRequest:
    endpoint = _endpoint()
    return HFDirectVoxelRequest(
        endpoint=endpoint,
        clinical_table=root / "inputs" / "clinical.csv",
        stimulation_table=root / "inputs" / "stimulation.xlsx",
        derivatives_root=root / "inputs" / "derivatives",
        brainmask=root / "inputs" / "configured_brainmask.nii.gz",
        asset_root=root / "assets",
        model_root=root / "models" / endpoint.endpoint_model_id,
        output_root=root / "models" / endpoint.endpoint_model_id / "tasks" / "resolver-task",
        tau_grid=(125.0, 175.0, 275.0),
        coverage_grid=(4, 7, 9),
        primary_tau=175.0,
        primary_coverage=7,
        candidate_threshold=125.0,
        force=False,
    )


class ConfiguredHFDirectBackendTests(unittest.TestCase):
    def test_selected_source_materializes_full_and_fold_specific_artifacts(self) -> None:
        rng = np.random.default_rng(42)
        x = rng.uniform(0.0, 2.0, size=(12, 30)).astype(np.float32)
        y_base = np.linspace(10.0, 21.0, 12)
        y_post = 0.5 * y_base + rng.normal(0.0, 1.0, size=12)
        subject_ids = tuple(f"sub-{index:02d}" for index in range(1, 13))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brainmask = root / "brainmask.nii.gz"
            nib.save(
                nib.Nifti1Image(np.ones((4, 4, 4), dtype=np.uint8), np.eye(4)),
                brainmask,
            )
            artifacts = materialize_configured_hf_direct_source(
                output_dir=root / "selected",
                x=x,
                y_post=y_post,
                y_base=y_base,
                subject_ids=subject_ids,
                candidate_flat=np.arange(30, dtype=np.int64),
                brainmask=brainmask,
                scale_direction="lower",
                tau=0.5,
                coverage=5,
            )
            self.assertEqual(np.load(artifacts["full_weights"]).shape, (30,))
            self.assertEqual(np.load(artifacts["fold_weights"]).shape, (12, 30))
            self.assertEqual(np.load(artifacts["fold_scores"]).shape, (12, 12))
            self.assertTrue(artifacts["scores"].is_file())
            self.assertTrue(artifacts["loocv_predictions"].is_file())
            self.assertTrue(artifacts["coefficient_nifti"].is_file())
            self.assertTrue(artifacts["manifest"].is_file())

    def test_sidecar_runner_builds_hash_keyed_shared_cache_and_standard_artifacts(self) -> None:
        captured = []

        def preprocess_runner(config, *, flip_backend):
            captured.append((config, flip_backend))
            config.cache_root.mkdir(parents=True, exist_ok=True)
            completion = config.cache_root / "cache_complete.json"
            qc = config.cache_root / "preprocess_qc.json"
            completion.write_text("{}\n", encoding="utf-8")
            qc.write_text("{}\n", encoding="utf-8")
            return {
                "preprocess_dir": config.cache_root,
                "preprocess_status": "built",
                "preprocess_cache_validation": "cache_rebuilt",
                "preprocess_qc_path": qc,
                "completion_manifest_path": completion,
                "subject_ids": config.subject_order,
            }

        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            marker = object()
            artifacts = run_configured_hf_direct_sidecars(
                request,
                flip_backend=marker,
                preprocess_runner=preprocess_runner,
            )
            by_kind = {artifact.kind: artifact.path for artifact in artifacts}
            self.assertEqual(set(by_kind), {"sidecar_index", "qc"})
            self.assertTrue(by_kind["sidecar_index"].is_file())
            self.assertTrue(by_kind["qc"].is_file())

        config, observed_flip = captured[0]
        self.assertIs(observed_flip, marker)
        self.assertEqual(config.cache_root.parent, request.model_root / "cache")
        self.assertIn(request.endpoint.endpoint_model_id, config.cache_root.name)
        self.assertIn("candidate_tau125", config.cache_root.name)

    def test_configured_runner_forwards_explicit_inputs_and_converts_output(self) -> None:
        captured: list[tuple[ConfiguredHFDirectVoxelRun, object]] = []

        def flip_backend(*args, **kwargs):
            raise AssertionError("the injected analysis double must not call the flip backend")

        def analysis_runner(config, *, flip_backend):
            captured.append((config, flip_backend))
            config.output_root.mkdir(parents=True, exist_ok=True)
            feature_ids = config.output_root / "candidate_flat_indices.npy"
            np.save(feature_ids, np.array([11, 17, 23], dtype=np.int64))
            manifest = config.output_root / configured_manifest_name(config)
            manifest.write_text("{}\n", encoding="utf-8")
            return {
                "source_resolution": {
                    "source_status": "scan_fallback_accepted",
                    "prediction_status": "error_predictive",
                    "threshold_source": "scan_fallback",
                    "selected_tau": 275,
                    "selected_coverage": 9,
                    "selected_adjacent_passing_grid_cells": 2,
                },
                "subject_ids": ["sub-01", "sub-02", "sub-03"],
                "feature_ids_path": feature_ids,
                "feature_count": 3,
                "manifest_path": manifest,
                "artifact_paths": {"scan_manifest": manifest},
            }

        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            output = run_configured_hf_direct(
                request,
                flip_backend=flip_backend,
                analysis_runner=analysis_runner,
            )
            artifact_paths = {artifact.kind: artifact.path for artifact in output.artifacts}
            self.assertTrue(artifact_paths["source_status"].is_file())
            self.assertTrue(artifact_paths["selected_source"].is_file())
            source_status_payload = json.loads(
                artifact_paths["source_status"].read_text(encoding="utf-8")
            )

        config, observed_flip_backend = captured[0]
        self.assertEqual(config.endpoint_id, request.endpoint.endpoint_model_id)
        self.assertEqual(config.scale_label, request.endpoint.scale_label)
        self.assertEqual(config.direction, "lower")
        self.assertEqual((config.protocol, config.phase), ("STN", "3m"))
        self.assertEqual(config.subject_order, request.endpoint.subject_ids)
        self.assertEqual(config.clinical_table, request.clinical_table)
        self.assertEqual(config.stimulation_table, request.stimulation_table)
        self.assertEqual(config.brainmask, request.brainmask)
        self.assertEqual(config.derivatives_root, request.derivatives_root)
        self.assertEqual(config.tau_grid, request.tau_grid)
        self.assertEqual(config.coverage_grid, request.coverage_grid)
        self.assertEqual((config.primary_tau, config.primary_coverage), (175.0, 7))
        self.assertEqual(config.candidate_threshold, min(config.tau_grid))
        self.assertIs(observed_flip_backend, flip_backend)
        self.assertEqual(output.source_status, "scan_fallback_accepted")
        self.assertEqual((output.selected_tau, output.selected_coverage), (275.0, 9))
        self.assertEqual(output.subject_order, ("sub-01", "sub-02", "sub-03"))
        self.assertEqual(output.feature_axis.count, 3)
        self.assertEqual(output.feature_axis.identity_source, "candidate_flat_indices")
        self.assertIn("scan_manifest", artifact_paths)
        self.assertIn("source_status", artifact_paths)
        self.assertIn("selected_source", artifact_paths)
        self.assertEqual(source_status_payload["source_status"], "scan_fallback_accepted")

    def test_candidate_threshold_must_equal_minimum_configured_tau(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = replace(_request(Path(tmp)), candidate_threshold=124.0)
            with self.assertRaisesRegex(ValueError, "candidate_threshold.*minimum tau"):
                run_configured_hf_direct(
                    request,
                    flip_backend=lambda *args, **kwargs: None,
                    analysis_runner=lambda config, **kwargs: {},
                )

    def test_configured_runner_rejects_backend_subject_order_drift(self) -> None:
        def analysis_runner(config, *, flip_backend):
            del flip_backend
            config.output_root.mkdir(parents=True, exist_ok=True)
            feature_ids = config.output_root / "candidate_flat_indices.npy"
            np.save(feature_ids, np.array([11], dtype=np.int64))
            return {
                "source_resolution": {
                    "source_status": "absent_no_stable_grid",
                    "prediction_status": "not_applicable",
                    "threshold_source": "none",
                    "selected_tau": "",
                    "selected_coverage": "",
                    "selected_adjacent_passing_grid_cells": 0,
                },
                "subject_ids": ["sub-02", "sub-01", "sub-03"],
                "feature_ids_path": feature_ids,
                "feature_count": 1,
                "artifact_paths": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "subject order"):
                run_configured_hf_direct(
                    _request(Path(tmp)),
                    flip_backend=lambda *args, **kwargs: None,
                    analysis_runner=analysis_runner,
                )

    def test_configured_names_include_endpoint_and_actual_threshold_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            config = ConfiguredHFDirectVoxelRun.from_request_values(
                endpoint_id=request.endpoint.endpoint_model_id,
                scale_label=request.endpoint.scale_label,
                direction=request.endpoint.direction,
                protocol=request.endpoint.hf_reference_protocol,
                phase=request.endpoint.hf_reference_phase,
                clinical_table=request.clinical_table,
                stimulation_table=request.stimulation_table,
                derivatives_root=request.derivatives_root,
                brainmask=request.brainmask,
                asset_root=request.asset_root,
                output_root=request.output_root,
                tau_grid=request.tau_grid,
                coverage_grid=request.coverage_grid,
                primary_tau=request.primary_tau,
                primary_coverage=request.primary_coverage,
                candidate_threshold=request.candidate_threshold,
                force=request.force,
                subject_order=request.endpoint.subject_ids,
            )

        scan_dir = configured_scan_directory(config)
        manifest_name = configured_manifest_name(config)
        cache_manifest_name = configured_cache_manifest_name(config)
        self.assertIn(request.endpoint.endpoint_model_id, scan_dir.parts)
        self.assertIn("candidate_tau125", str(scan_dir))
        self.assertIn("taus_125-175-275", str(scan_dir))
        self.assertIn("coverages_4-7-9", str(scan_dir))
        self.assertIn("primary_tau175_cov7", str(scan_dir))
        self.assertIn(request.endpoint.endpoint_model_id, manifest_name)
        self.assertIn("primary_tau175_cov7", manifest_name)
        self.assertIn(request.endpoint.endpoint_model_id, cache_manifest_name)
        self.assertIn("candidate_tau125", cache_manifest_name)
        self.assertEqual(primary_branch_name(175, 7), "tau175_cov7/partial_spearman")

    def test_cache_reuse_requires_complete_matching_metadata_and_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            x_path = cache_dir / "X_HF_float32_subject_major.npy"
            flat_path = cache_dir / "candidate_flat_indices.npy"
            np.save(x_path, np.ones((3, 4), dtype=np.float32))
            np.save(flat_path, np.array([1, 2, 3, 4], dtype=np.int64))
            expected = cache_completion_metadata(
                endpoint_id="endpoint-real",
                subject_order=("sub-01", "sub-02", "sub-03"),
                candidate_threshold=125.0,
                brainmask_identity={"path": "/brainmask.nii.gz", "size": 21, "mtime_ns": 7},
                input_identities=(
                    {"path": "/clinical.csv", "size": 31, "mtime_ns": 8},
                    {"path": "/stimulation.xlsx", "size": 41, "mtime_ns": 9},
                ),
                protocol="STN",
                phase="3m",
                matrix_shape=(3, 4),
                candidate_shape=(4,),
            )
            manifest_path = cache_dir / "cache_complete.json"

            valid, reason = validate_preprocess_cache(
                manifest_path=manifest_path,
                expected=expected,
                x_path=x_path,
                candidate_flat_path=flat_path,
            )
            self.assertFalse(valid)
            self.assertEqual(reason, "completion_manifest_missing")

            write_atomic_json(manifest_path, expected)
            valid, reason = validate_preprocess_cache(
                manifest_path=manifest_path,
                expected=expected,
                x_path=x_path,
                candidate_flat_path=flat_path,
            )
            self.assertEqual((valid, reason), (True, "cache_valid"))

            mutations = {
                "status": "building",
                "endpoint_id": "endpoint-stale",
                "subject_order": ["sub-02", "sub-01", "sub-03"],
                "candidate_threshold_v_per_m": 124.0,
                "brainmask_identity": {"path": "/other.nii.gz", "size": 21, "mtime_ns": 7},
                "input_identities": [{"path": "/different.csv", "size": 31, "mtime_ns": 8}],
                "protocol": "STN+SNr",
                "phase": "immediate",
                "matrix_shape": [3, 5],
            }
            for field, stale_value in mutations.items():
                with self.subTest(field=field):
                    stale = json.loads(json.dumps(expected))
                    stale[field] = stale_value
                    write_atomic_json(manifest_path, stale)
                    valid, reason = validate_preprocess_cache(
                        manifest_path=manifest_path,
                        expected=expected,
                        x_path=x_path,
                        candidate_flat_path=flat_path,
                    )
                    self.assertFalse(valid)
                    self.assertIn(field, reason)

            write_atomic_json(manifest_path, expected)
            np.save(x_path, np.ones((3, 5), dtype=np.float32))
            valid, reason = validate_preprocess_cache(
                manifest_path=manifest_path,
                expected=expected,
                x_path=x_path,
                candidate_flat_path=flat_path,
            )
            self.assertEqual((valid, reason), (False, "matrix_shape_file_mismatch"))


if __name__ == "__main__":
    unittest.main()
