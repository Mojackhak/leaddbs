"""Configured ULF direct-voxel backend contract tests."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pandas as pd

from outcome_models.catalog import CatalogStatus, EndpointRecord
from outcome_models.identity import EndpointModelKey
from outcome_models.identity import TaskKey
from outcome_models.planner import GatePredicate, TaskGate, TaskSpec
from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    HFSourceRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.services.legacy_ulf_direct import (
    ConfiguredULFDirectDeltaBuilder,
    ConfiguredULFDirectPaths,
    assess_delta_hf_voxel_support,
    run_configured_ulf_direct,
    score_delta_hf_locked_support,
)
from outcome_models.services.ulf_observed import ULFObservedRequest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class ULFDirectConfiguredBackendTests(unittest.TestCase):
    def _endpoint(self) -> EndpointRecord:
        key = EndpointModelKey("study", "scale", "chronic", "ulf_voxel")
        return EndpointRecord(
            key=key,
            endpoint_model_id=key.identifier,
            scale_label="Configured Scale",
            direction="lower",
            outcome_protocol="STN+SNr",
            outcome_phase="3m",
            hf_reference_protocol="STN",
            hf_reference_phase="3m",
            n_subjects=3,
            subject_ids=("sub-01", "sub-02", "sub-03"),
            status=CatalogStatus.DATA_AVAILABLE,
            failure_reasons=(),
        )

    def _paths(self, root: Path) -> ConfiguredULFDirectPaths:
        files = root / "inputs"
        files.mkdir(parents=True, exist_ok=True)
        values = {}
        for name in (
            "clinical.xlsx",
            "stimulation.xlsx",
            "brainmask.nii.gz",
            "readiness.csv",
        ):
            path = files / name
            path.write_bytes(name.encode("ascii"))
            values[name] = path
        return ConfiguredULFDirectPaths(
            run_root=root,
            clinical_table=values["clinical.xlsx"],
            stimulation_table=values["stimulation.xlsx"],
            derivatives_root=files / "derivatives",
            brainmask=values["brainmask.nii.gz"],
            asset_root=files / "assets",
            readiness_csv=values["readiness.csv"],
            matlab_bin=Path("/usr/bin/false"),
        )

    def _artifact(self, root: Path, task_id: str, kind: str, name: str, array) -> ArtifactRef:
        path = root / "tasks" / task_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".npy"):
            np.save(path, np.asarray(array, dtype=float))
            shape = tuple(np.asarray(array).shape)
        else:
            pd.DataFrame(array).to_csv(path, index=False)
            shape = (len(array),)
        return ArtifactRef(task_id, kind, str(path.relative_to(root)), _sha256(path), shape)

    def _source(self, root: Path, *, accepted: bool) -> HFSourceRecord:
        if not accepted:
            return HFSourceRecord.create(
                resolver_task_id="hf_resolver",
                endpoint_model_id="hf_endpoint",
                input_status="valid",
                source_status="absent_no_stable_grid",
                prediction_status="not_applicable",
                threshold_source="none",
                selected_tau=None,
                selected_coverage=None,
                subject_order=(),
                feature_axis=None,
                artifacts=(),
            )
        ids = root / "hf_candidate_ids.npy"
        np.save(ids, np.array([11, 17, 23], dtype=np.int64))
        source_manifest = root / "hf_source.json"
        source_manifest.write_text("{}\n", encoding="utf-8")
        return HFSourceRecord.create(
            resolver_task_id="hf_resolver",
            endpoint_model_id="hf_endpoint",
            input_status="valid",
            source_status="scan_fallback_accepted",
            prediction_status="error_predictive",
            threshold_source="scan_fallback",
            selected_tau=250,
            selected_coverage=6,
            subject_order=self._endpoint().subject_ids,
            feature_axis=FeatureAxisRef(ids, 3, _sha256(ids), "candidate_flat_indices"),
            artifacts=(
                ArtifactRef(
                    "hf_resolver",
                    "source_manifest",
                    str(source_manifest.relative_to(root)),
                    _sha256(source_manifest),
                    (),
                ),
            ),
        )

    def _delta(self, root: Path, *, valid: bool = True) -> DeltaHFBundle:
        if not valid:
            return DeltaHFBundle(
                input_status="invalid",
                support_status="invalid_extreme_out_of_support",
                selected_hf_tau=250,
                selected_hf_coverage=6,
                full_scores=None,
                fold_scores=None,
                support_rows=self._artifact(
                    root,
                    "delta_task",
                    "delta_hf_support_rows",
                    "support.csv",
                    [{"subject_id": subject, "status": "invalid"} for subject in self._endpoint().subject_ids],
                ),
                failure_stage="support_qc",
                failure_detail="extreme out of support",
            )
        return DeltaHFBundle(
            input_status="valid",
            support_status="limited",
            selected_hf_tau=250,
            selected_hf_coverage=6,
            full_scores=self._artifact(
                root,
                "delta_task",
                "delta_hf_full_scores",
                "full.npy",
                [0.1, 0.2, 0.3],
            ),
            fold_scores=self._artifact(
                root,
                "delta_task",
                "delta_hf_fold_scores",
                "folds.npy",
                [[0.11, 0.12, 0.13], [0.21, 0.22, 0.23], [0.31, 0.32, 0.33]],
            ),
            support_rows=self._artifact(
                root,
                "delta_task",
                "delta_hf_support_rows",
                "support.csv",
                [{"subject_id": subject, "status": "limited"} for subject in self._endpoint().subject_ids],
            ),
        )

    def _request(
        self,
        root: Path,
        *,
        branch: str,
        source: HFSourceRecord,
        delta: DeltaHFBundle | None,
    ) -> ULFObservedRequest:
        return ULFObservedRequest(
            endpoint=self._endpoint(),
            branch=branch,
            hf_source=source,
            delta_hf=delta,
            nuisance=NuisancePlan.for_branch(branch, delta),
            model_root=root / "models" / self._endpoint().endpoint_model_id,
            output_root=root / "models" / self._endpoint().endpoint_model_id / "tasks" / f"ulf_{branch}",
            tau_grid=(100.0, 200.0, 300.0),
            coverage_grid=(5, 6, 8),
            primary_tau=200.0,
            primary_coverage=5,
            hf_overlap_tau=float(source.selected_tau) if source.accepted else math.inf,
            hf_overlap_coverage=int(source.selected_coverage) if source.accepted else None,
        )

    @staticmethod
    def _fake_analysis(captured: dict):
        def run(config, *, flip_backend=None):
            captured["config"] = config
            captured["flip_backend"] = flip_backend
            config.output_root.mkdir(parents=True, exist_ok=True)
            feature_ids = config.output_root / f"{config.branch_name}_candidate_flat_indices.npy"
            np.save(feature_ids, np.array([2, 4, 8], dtype=np.int64))
            metrics = config.output_root / f"{config.branch_name}_observed_metrics.json"
            metrics.write_text(json.dumps({"branch": config.branch}), encoding="utf-8")
            predictions = config.output_root / f"{config.branch_name}_loocv_predictions.csv"
            predictions.write_text("subject_id,prediction\nsub-01,1\n", encoding="utf-8")
            return {
                "branch": config.branch,
                "branch_name": config.branch_name,
                "source_resolution": {
                    "source_status": "pre_specified_accepted",
                    "prediction_status": "error_nonpredictive",
                    "threshold_source": "pre_specified",
                    "selected_tau": config.primary_tau,
                    "selected_coverage": config.primary_coverage,
                    "selected_adjacent_passing_grid_cells": 2,
                },
                "subject_ids": list(config.subject_order),
                "feature_ids_path": str(feature_ids),
                "feature_count": 3,
                "artifact_paths": {
                    "observed_metrics": str(metrics),
                    "loocv_predictions": str(predictions),
                },
            }

        return run

    def test_absent_hf_runs_no_delta_with_infinite_overlap_and_no_delta_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=False)
            request = self._request(root, branch="no_delta_hf", source=source, delta=None)
            captured = {}
            output = run_configured_ulf_direct(
                request,
                paths=self._paths(root),
                analysis_runner=self._fake_analysis(captured),
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )

            self.assertTrue(math.isinf(captured["config"].hf_overlap_tau))
            self.assertEqual(captured["config"].nuisance_columns, ("Y_HF_ref",))
            self.assertIsNone(captured["config"].delta_full_scores)
            self.assertFalse(any(artifact.kind.startswith("delta_hf_") for artifact in output.artifacts))

    def test_adjusted_uses_selected_hf_tau_for_overlap_delta_and_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=True)
            delta = self._delta(root)
            request = self._request(root, branch="delta_hf_adjusted", source=source, delta=delta)
            captured = {}
            output = run_configured_ulf_direct(
                request,
                paths=self._paths(root),
                analysis_runner=self._fake_analysis(captured),
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )

            config = captured["config"]
            self.assertEqual(config.hf_overlap_tau, 250)
            self.assertEqual(config.delta_hf_tau, 250)
            self.assertEqual(config.delta_hf_coverage, 6)
            self.assertEqual(config.nuisance_columns, ("Y_HF_ref", "DeltaHFScore"))
            self.assertEqual(np.load(config.delta_full_scores).shape, (3,))
            self.assertEqual(np.load(config.delta_fold_scores).shape, (3, 3))
            kinds = {artifact.kind for artifact in output.artifacts}
            self.assertTrue(
                {"delta_hf_full_scores", "delta_hf_fold_scores", "delta_hf_support_rows"}.issubset(kinds)
            )
            for artifact in output.artifacts:
                self.assertTrue(artifact.path.resolve().is_relative_to(request.output_root.resolve()))

    def test_delta_failure_rejects_adjusted_without_blocking_no_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=True)
            invalid = self._delta(root, valid=False)
            no_delta = self._request(root, branch="no_delta_hf", source=source, delta=None)
            output = run_configured_ulf_direct(
                no_delta,
                paths=self._paths(root),
                analysis_runner=self._fake_analysis({}),
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )
            adjusted = ULFObservedRequest(
                **{
                    **no_delta.__dict__,
                    "branch": "delta_hf_adjusted",
                    "delta_hf": invalid,
                    "output_root": no_delta.model_root / "tasks" / "ulf_delta_hf_adjusted",
                }
            )
            with self.assertRaises(RecordError):
                run_configured_ulf_direct(
                    adjusted,
                    paths=self._paths(root),
                    analysis_runner=self._fake_analysis({}),
                    flip_backend=lambda *args, **kwargs: ({}, {}),
                )

            self.assertEqual(output.source_status, "pre_specified_accepted")
            self.assertFalse((adjusted.output_root / "source_status.json").exists())

    def test_adjusted_never_runs_when_hf_source_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=False)
            no_delta = self._request(root, branch="no_delta_hf", source=source, delta=None)
            adjusted = ULFObservedRequest(
                **{
                    **no_delta.__dict__,
                    "branch": "delta_hf_adjusted",
                    "nuisance": NuisancePlan.for_branch("no_delta_hf", None),
                }
            )
            with self.assertRaises(RecordError):
                run_configured_ulf_direct(
                    adjusted,
                    paths=self._paths(root),
                    analysis_runner=self._fake_analysis({}),
                    flip_backend=lambda *args, **kwargs: ({}, {}),
                )

            self.assertFalse(adjusted.output_root.exists())

    def test_no_delta_uses_selected_hf_overlap_and_ignores_invalid_delta_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=True)
            invalid = self._delta(root, valid=False)
            request = self._request(root, branch="no_delta_hf", source=source, delta=invalid)
            captured = {}
            run_configured_ulf_direct(
                request,
                paths=self._paths(root),
                analysis_runner=self._fake_analysis(captured),
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )
            self.assertEqual(captured["config"].hf_overlap_tau, 250)
            self.assertIsNone(captured["config"].delta_hf_tau)
            self.assertIsNone(captured["config"].delta_full_scores)

            inconsistent = ULFObservedRequest(
                **{
                    **request.__dict__,
                    "output_root": request.model_root / "tasks" / "inconsistent_overlap",
                    "hf_overlap_tau": 200.0,
                }
            )
            with self.assertRaises(RecordError):
                run_configured_ulf_direct(
                    inconsistent,
                    paths=self._paths(root),
                    analysis_runner=self._fake_analysis({}),
                    flip_backend=lambda *args, **kwargs: ({}, {}),
                )

    def test_dynamic_branch_name_and_task_root_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, accepted=True)
            request = self._request(root, branch="no_delta_hf", source=source, delta=None)
            captured = {}
            run_configured_ulf_direct(
                request,
                paths=self._paths(root),
                analysis_runner=self._fake_analysis(captured),
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )

            config = captured["config"]
            self.assertEqual(config.branch_name, "tau200_cov5_no_delta_hf")
            self.assertEqual(config.outcome_phase, "3m")
            self.assertEqual(config.output_root, request.output_root.resolve())
            self.assertTrue(
                config.model_cache_root.resolve().is_relative_to((request.model_root / "cache").resolve())
            )

    def test_real_configured_entrypoint_runs_one_no_delta_branch_without_hf_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._paths(root)
            subjects = tuple(f"sub-{index:02d}" for index in range(1, 13))
            endpoint = self._endpoint()
            endpoint = EndpointRecord(
                **{
                    **endpoint.__dict__,
                    "n_subjects": len(subjects),
                    "subject_ids": subjects,
                }
            )
            source = self._source(root, accepted=False)
            model_root = root / "models" / endpoint.endpoint_model_id
            request = ULFObservedRequest(
                endpoint=endpoint,
                branch="no_delta_hf",
                hf_source=source,
                delta_hf=None,
                nuisance=NuisancePlan.for_branch("no_delta_hf", None),
                model_root=model_root,
                output_root=model_root / "tasks" / "real_no_delta",
                tau_grid=(100.0, 200.0),
                coverage_grid=(5, 6),
                primary_tau=100.0,
                primary_coverage=5,
                hf_overlap_tau=math.inf,
                hf_overlap_coverage=None,
            )

            clinical_rows = []
            readiness_rows = []
            rng = np.random.default_rng(20260709)
            affine = np.eye(4)
            nib.save(
                nib.Nifti1Image(np.ones((4, 4, 4), dtype=np.uint8), affine),
                str(paths.brainmask),
            )
            for index, subject in enumerate(subjects):
                clinical_rows.extend(
                    [
                        {
                            "ID": subject,
                            "Scale": endpoint.scale_label,
                            "Protocol": endpoint.outcome_protocol,
                            "Phase": endpoint.outcome_phase,
                            "Value": float(20 + index + (index % 3)),
                            "Baseline": float(35 + (index % 5)),
                        },
                        {
                            "ID": subject,
                            "Scale": endpoint.scale_label,
                            "Protocol": endpoint.hf_reference_protocol,
                            "Phase": endpoint.hf_reference_phase,
                            "Value": float(18 + (index * 2) % 7),
                            "Baseline": float(35 + (index % 5)),
                        },
                    ]
                )
                efield = root / "inputs" / f"{subject}_ulf.nii.gz"
                nib.save(
                    nib.Nifti1Image(rng.uniform(110, 260, size=(4, 4, 4)).astype(np.float32), affine),
                    str(efield),
                )
                hf_efield = root / "inputs" / f"{subject}_hf.nii.gz"
                nib.save(
                    nib.Nifti1Image(rng.uniform(0, 100, size=(4, 4, 4)).astype(np.float32), affine),
                    str(hf_efield),
                )
                readiness_rows.append(
                    {
                        "subject_id": subject,
                        "side": "R",
                        "frequency_class": "ULF",
                        "efield_exists": True,
                        "efield_path": str(efield),
                        "status": "available",
                        "protocol": endpoint.outcome_protocol,
                        "phase": endpoint.outcome_phase,
                    }
                )
                readiness_rows.append(
                    {
                        "subject_id": subject,
                        "side": "R",
                        "frequency_class": "HF",
                        "efield_exists": True,
                        "efield_path": str(hf_efield),
                        "status": "available",
                        "protocol": endpoint.outcome_protocol,
                        "phase": endpoint.outcome_phase,
                    }
                )
            pd.DataFrame(clinical_rows).to_excel(paths.clinical_table, index=False)
            pd.DataFrame(readiness_rows).to_csv(paths.readiness_csv, index=False)

            output = run_configured_ulf_direct(
                request,
                paths=paths,
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )

            self.assertEqual(output.subject_order, subjects)
            self.assertEqual(output.feature_axis.count, 48)
            self.assertIn(output.source_status, {"pre_specified_accepted", "scan_fallback_accepted"})
            self.assertFalse(any(artifact.kind.startswith("delta_hf_") for artifact in output.artifacts))
            artifacts = {artifact.kind: artifact.path for artifact in output.artifacts}
            self.assertTrue(
                {"ulf_component_exposure", "hf_component_exposure", "y_base"}.issubset(artifacts)
            )
            self.assertEqual(np.load(artifacts["ulf_component_exposure"]).shape, (12, 48))
            self.assertEqual(np.load(artifacts["hf_component_exposure"]).shape, (12, 48))
            self.assertEqual(np.load(artifacts["y_base"]).shape, (12,))

            hf_ids = root / "hf_real_candidate_ids.npy"
            np.save(hf_ids, np.arange(48, dtype=np.int64))
            hf_manifest = root / "hf_real_source.json"
            hf_manifest.write_text("{}\n", encoding="utf-8")
            accepted_source = HFSourceRecord.create(
                resolver_task_id="hf_real_resolver",
                endpoint_model_id="hf_real_endpoint",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=250,
                selected_coverage=6,
                subject_order=subjects,
                feature_axis=FeatureAxisRef(hf_ids, 48, _sha256(hf_ids), "candidate_flat_indices"),
                artifacts=(
                    ArtifactRef(
                        "hf_real_resolver",
                        "source_manifest",
                        str(hf_manifest.relative_to(root)),
                        _sha256(hf_manifest),
                        (),
                    ),
                ),
            )
            delta = DeltaHFBundle(
                input_status="valid",
                support_status="adequate",
                selected_hf_tau=250,
                selected_hf_coverage=6,
                full_scores=self._artifact(
                    root,
                    "delta_real",
                    "delta_hf_full_scores",
                    "full.npy",
                    np.linspace(-0.5, 0.5, len(subjects)),
                ),
                fold_scores=self._artifact(
                    root,
                    "delta_real",
                    "delta_hf_fold_scores",
                    "folds.npy",
                    np.vstack(
                        [np.linspace(-0.5, 0.5, len(subjects)) + fold * 0.001 for fold in range(len(subjects))]
                    ),
                ),
                support_rows=self._artifact(
                    root,
                    "delta_real",
                    "delta_hf_support_rows",
                    "support.csv",
                    [{"subject_id": subject, "support_status": "adequate"} for subject in subjects],
                ),
            )
            adjusted = ULFObservedRequest(
                **{
                    **request.__dict__,
                    "branch": "delta_hf_adjusted",
                    "hf_source": accepted_source,
                    "delta_hf": delta,
                    "nuisance": NuisancePlan.for_branch("delta_hf_adjusted", delta),
                    "output_root": model_root / "tasks" / "real_adjusted",
                    "hf_overlap_tau": 250.0,
                    "hf_overlap_coverage": 6,
                }
            )
            adjusted_output = run_configured_ulf_direct(
                adjusted,
                paths=paths,
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )
            adjusted_kinds = {artifact.kind for artifact in adjusted_output.artifacts}
            self.assertTrue(
                {"delta_hf_full_scores", "delta_hf_fold_scores", "delta_hf_support_rows"}.issubset(
                    adjusted_kinds
                )
            )


class ULFDirectDeltaBuilderTests(unittest.TestCase):
    @staticmethod
    def _support_weights(n_features: int, n_supported: int) -> np.ndarray:
        weights = np.full(n_features, np.nan, dtype=float)
        weights[:n_supported] = 1.0
        return weights

    def test_support_qc_adequate_and_limited_use_suprathreshold_voxel_counts(self) -> None:
        component = np.full((4, 100), 150.0)
        adequate = assess_delta_hf_voxel_support(
            component_exposure=component,
            full_weights=self._support_weights(100, 80),
            fold_weights=np.tile(self._support_weights(100, 80), (4, 1)),
            selected_tau=100.0,
            subject_order=("s1", "s2", "s3", "s4"),
        )
        limited = assess_delta_hf_voxel_support(
            component_exposure=component,
            full_weights=self._support_weights(100, 70),
            fold_weights=np.tile(self._support_weights(100, 70), (4, 1)),
            selected_tau=100.0,
            subject_order=("s1", "s2", "s3", "s4"),
        )

        self.assertEqual(adequate.assessment.status, "adequate")
        self.assertAlmostEqual(adequate.assessment.cohort_median, 0.20)
        self.assertEqual(limited.assessment.status, "limited")
        self.assertAlmostEqual(limited.assessment.cohort_median, 0.30)
        self.assertTrue(all(row["total_suprathreshold_voxels"] == 100 for row in adequate.rows))

    def test_support_qc_zero_coverage_is_invalid(self) -> None:
        component = np.full((3, 20), 150.0)
        component[1] = 99.0
        result = assess_delta_hf_voxel_support(
            component_exposure=component,
            full_weights=self._support_weights(20, 20),
            fold_weights=np.tile(self._support_weights(20, 20), (3, 1)),
            selected_tau=100.0,
            subject_order=("s1", "s2", "s3"),
        )

        self.assertEqual(result.assessment.status, "invalid_no_hfcomponent_coverage")
        self.assertEqual(result.rows[1]["total_suprathreshold_voxels"], 0)

    def test_support_qc_fold_fraction_must_be_strictly_greater_than_point_95(self) -> None:
        component = np.full((2, 100), 150.0)
        full = self._support_weights(100, 100)
        exact_boundary = assess_delta_hf_voxel_support(
            component_exposure=component,
            full_weights=full,
            fold_weights=np.tile(self._support_weights(100, 5), (2, 1)),
            selected_tau=100.0,
            subject_order=("s1", "s2"),
        )
        beyond_boundary = assess_delta_hf_voxel_support(
            component_exposure=component,
            full_weights=full,
            fold_weights=np.tile(self._support_weights(100, 4), (2, 1)),
            selected_tau=100.0,
            subject_order=("s1", "s2"),
        )

        self.assertEqual(exact_boundary.assessment.status, "adequate")
        self.assertAlmostEqual(exact_boundary.assessment.maximum_required_fraction, 0.95)
        self.assertEqual(beyond_boundary.assessment.status, "invalid_extreme_out_of_support")
        self.assertAlmostEqual(beyond_boundary.assessment.maximum_required_fraction, 0.96)

    def test_scoring_remains_continuous_inside_locked_weight_support(self) -> None:
        reference = np.array([[80.0, 40.0], [20.0, 10.0]])
        component = np.array([[60.0, 20.0], [10.0, 5.0]])
        full_weights = np.array([1.0, 2.0])
        fold_weights = np.array([[1.0, 2.0], [2.0, 1.0]])

        full, folds = score_delta_hf_locked_support(
            reference_exposure=reference,
            component_exposure=component,
            full_weights=full_weights,
            fold_weights=fold_weights,
        )

        np.testing.assert_allclose(full, [-30.0, -10.0])
        np.testing.assert_allclose(folds[0], [-30.0, -10.0])
        np.testing.assert_allclose(folds[1], [-30.0, -12.5])

    @staticmethod
    def _write_artifact(
        run_root: Path,
        task_id: str,
        kind: str,
        name: str,
        values: np.ndarray,
    ) -> ArtifactRef:
        path = run_root / "models" / "hf" / "tasks" / task_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, values)
        return ArtifactRef(
            task_id,
            kind,
            str(path.relative_to(run_root)),
            _sha256(path),
            tuple(int(value) for value in values.shape),
        )

    def test_real_delta_builder_writes_atomic_bundle_artifacts_under_sidecar_task_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp).resolve()
            subjects = ("sub-01", "sub-02", "sub-03")
            endpoint_key = EndpointModelKey("study", "scale", "chronic", "ulf_voxel")
            endpoint = EndpointRecord(
                key=endpoint_key,
                endpoint_model_id=endpoint_key.identifier,
                scale_label="Configured Scale",
                direction="lower",
                outcome_protocol="STN+SNr",
                outcome_phase="3m",
                hf_reference_protocol="STN",
                hf_reference_phase="3m",
                n_subjects=len(subjects),
                subject_ids=subjects,
                status=CatalogStatus.DATA_AVAILABLE,
                failure_reasons=(),
            )
            task_key = TaskKey(endpoint.endpoint_model_id, "preprocessing_sidecars", "sidecars")
            task = TaskSpec(
                task_id=task_key.identifier,
                key=task_key,
                endpoint=endpoint.key,
                round_name="Round 1",
                workflow_phase="observed",
                dependencies=(),
                gate=TaskGate(GatePredicate.ALWAYS),
                expected_artifact_kinds=("task_manifest", "sidecar_index", "qc"),
            )
            context = SimpleNamespace(store=SimpleNamespace(run_root=run_root))

            input_root = run_root / "inputs"
            input_root.mkdir()
            brainmask = input_root / "brainmask.nii.gz"
            nib.save(
                nib.Nifti1Image(np.ones((11, 1, 1), dtype=np.uint8), np.eye(4)),
                str(brainmask),
            )
            readiness_rows = []
            for subject in subjects:
                efield = input_root / f"{subject}_hf_component.nii.gz"
                values = np.zeros((11, 1, 1), dtype=np.float32)
                values[1:, 0, 0] = 300.0
                nib.save(nib.Nifti1Image(values, np.eye(4)), str(efield))
                readiness_rows.append(
                    {
                        "subject_id": subject,
                        "side": "R",
                        "frequency_class": "HF",
                        "efield_exists": True,
                        "efield_path": str(efield),
                        "status": "available",
                        "protocol": endpoint.outcome_protocol,
                        "phase": endpoint.outcome_phase,
                    }
                )
            readiness = input_root / "readiness.csv"
            pd.DataFrame(readiness_rows).to_csv(readiness, index=False)
            for name in ("clinical.xlsx", "stimulation.xlsx"):
                (input_root / name).write_bytes(b"configured")

            hf_task_id = "hf_resolver"
            candidates = np.arange(1, 11, dtype=np.int64)
            full_weights = self._support_weights(10, 8).astype(np.float32)
            fold_weights = np.tile(full_weights, (len(subjects), 1)).astype(np.float32)
            reference = np.full((len(subjects), 10), 100.0, dtype=np.float32)
            candidate_ref = self._write_artifact(
                run_root, hf_task_id, "candidate_flat_indices", "candidate.npy", candidates
            )
            full_ref = self._write_artifact(
                run_root, hf_task_id, "selected_full_weights", "full_weights.npy", full_weights
            )
            fold_ref = self._write_artifact(
                run_root, hf_task_id, "selected_fold_weights", "fold_weights.npy", fold_weights
            )
            exposure_ref = self._write_artifact(
                run_root, hf_task_id, "exposure_matrix", "reference.npy", reference
            )
            candidate_path = run_root / candidate_ref.relative_path
            source = HFSourceRecord.create(
                resolver_task_id=hf_task_id,
                endpoint_model_id="hf_endpoint",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=100.0,
                selected_coverage=2,
                subject_order=subjects,
                feature_axis=FeatureAxisRef(
                    candidate_path,
                    10,
                    candidate_ref.sha256,
                    "candidate_flat_indices",
                ),
                artifacts=(candidate_ref, full_ref, fold_ref, exposure_ref),
            )
            paths = ConfiguredULFDirectPaths(
                run_root=run_root,
                clinical_table=input_root / "clinical.xlsx",
                stimulation_table=input_root / "stimulation.xlsx",
                derivatives_root=input_root / "derivatives",
                brainmask=brainmask,
                asset_root=input_root / "assets",
                readiness_csv=readiness,
                matlab_bin=Path("/usr/bin/false"),
            )
            builder = ConfiguredULFDirectDeltaBuilder(
                paths=paths,
                flip_backend=lambda *args, **kwargs: ({}, {}),
            )

            result = builder(endpoint, source, task, context)

            self.assertTrue(result.bundle.valid)
            self.assertEqual(result.bundle.support_status, "adequate")
            self.assertEqual(result.bundle.full_scores.shape, (3,))
            self.assertEqual(result.bundle.fold_scores.shape, (3, 3))
            task_root = run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            for artifact_ref in (
                result.bundle.full_scores,
                result.bundle.fold_scores,
                result.bundle.support_rows,
            ):
                artifact_path = run_root / artifact_ref.relative_path
                self.assertEqual(artifact_ref.task_id, task.task_id)
                self.assertEqual(artifact_ref.sha256, _sha256(artifact_path))
                self.assertTrue(artifact_path.resolve().is_relative_to(task_root))
            np.testing.assert_allclose(np.load(task_root / "full.npy"), [50.0, 50.0, 50.0])
            np.testing.assert_allclose(np.load(task_root / "folds.npy"), np.full((3, 3), 50.0))
            support = pd.read_csv(task_root / "support.csv")
            self.assertEqual(tuple(support["subject_id"]), subjects)
            self.assertTrue((task_root / "support_qc.json").is_file())
            self.assertTrue(all(artifact.path.resolve().is_relative_to(task_root) for artifact in result.artifacts))
            self.assertFalse(any(path.name.startswith(".") and ".tmp-" in path.name for path in task_root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
