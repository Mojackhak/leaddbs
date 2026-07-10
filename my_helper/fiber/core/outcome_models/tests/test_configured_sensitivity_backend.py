"""Configured final-linked sensitivity backend tests."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import importlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from outcome_models.identity import EndpointModelKey, TaskKey
from outcome_models.planner import GatePredicate, TaskGate, TaskSpec, compile_execution_plan
from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.run_store import ConfiguredRunStore
from outcome_models.services.legacy_sensitivity import (
    SUPPORTED_SENSITIVITY_OPERATIONS,
    build_configured_sensitivity_target,
    run_configured_sensitivity,
)
from outcome_models.services.sensitivity import (
    SensitivityRequest,
    SensitivityRuntimeInputs,
    SensitivityService,
    SensitivityServiceOutput,
)
from outcome_models.tests.helpers import (
    clinical_rows_for_scale,
    write_clinical_rows,
    write_profile_bundle,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


class ConfiguredSensitivityBackendTests(unittest.TestCase):
    def _task(self, family: str, stage: str) -> TaskSpec:
        endpoint = EndpointModelKey(
            study_id="study",
            scale_id="scale",
            model_family=family,
            endpoint_phase="chronic",
            connectome="dtor" if family.endswith("fiber") else "none",
        )
        key = TaskKey(
            endpoint_model_id=endpoint.identifier,
            execution_stage=stage,
            branch="realized_final" if family.startswith("ulf_") else "none",
            source_reference="final_model_record",
        )
        return TaskSpec(
            task_id=key.identifier,
            key=key,
            endpoint=endpoint,
            round_name="Round 3" if stage == "plain_burden_controls" else "Round 7",
            workflow_phase="observed" if stage == "plain_burden_controls" else "sensitivity",
            dependencies=(),
            gate=TaskGate(GatePredicate.FINAL_MODEL_REALIZED),
            expected_artifact_kinds=(
                "task_manifest",
                (
                    "jitter_results"
                    if stage == "spatial_jitter"
                    else "control_metrics"
                    if stage == "plain_burden_controls"
                    else "sensitivity_results"
                ),
            ),
        )

    def _artifact(
        self,
        root: Path,
        path: Path,
        kind: str,
        shape: tuple[int, ...] = (),
    ) -> ArtifactRef:
        return ArtifactRef(
            task_id="producer",
            kind=kind,
            relative_path=path.relative_to(root).as_posix(),
            sha256=_sha256(path),
            shape=shape,
        )

    def _final(self, root: Path, task: TaskSpec, *, branch: str = "no_delta_hf") -> FinalArtifactRecord:
        producer = root / "models" / task.endpoint.identifier / "producer"
        producer.mkdir(parents=True, exist_ok=True)
        subject_order = tuple(f"sub-{index:02d}" for index in range(1, 13))
        exposure = producer / "exposure.npy"
        subject_gradient = np.arange(12, dtype=np.float32)[:, None] * 4.0
        feature_gradient = np.arange(20, dtype=np.float32)[None, :] * 1.5
        base_exposure = 900.0 if task.endpoint.model_family.endswith("fiber") else 260.0
        np.save(exposure, base_exposure + subject_gradient + feature_gradient)
        scores = producer / "scores.csv"
        with scores.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["subject_id", "Y_post", "Y_HF_ref", "Y_base"],
            )
            writer.writeheader()
            for index, subject_id in enumerate(subject_order):
                writer.writerow(
                    {
                        "subject_id": subject_id,
                        "Y_post": 30 - index + (index % 3),
                        "Y_HF_ref": 25 + ((index * 5) % 7),
                        "Y_base": 18 + ((index * 3) % 5),
                    }
                )
        ids = producer / "feature_ids.npy"
        feature_ids = np.arange(20, dtype=np.int64)
        np.save(ids, feature_ids)
        manifest = producer / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "subject_order": list(subject_order),
                    "scale_direction": "lower",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        nuisance = NuisancePlan.for_branch("no_delta_hf", None)
        if branch == "hf_source":
            nuisance = NuisancePlan.for_branch("hf_source", None)
        fiber_kwargs = {}
        estimator = "partial_spearman"
        if task.endpoint.model_family.endswith("fiber"):
            estimator = "peak_efield_partial_spearman"
            full_weights_path = producer / "selected_full_weights.npy"
            valid_ids_path = producer / "selected_valid_fiber_ids.npy"
            full_weights = np.concatenate(
                [np.linspace(1.0, -1.0, 10), np.full(10, np.nan)]
            ).astype(np.float32)
            valid_ids = feature_ids[:10]
            np.save(full_weights_path, full_weights)
            np.save(valid_ids_path, valid_ids)
            fiber_kwargs = {
                "full_weights": self._artifact(
                    root,
                    full_weights_path,
                    "selected_full_weights",
                    (20,),
                ),
                "valid_feature_axis": FeatureAxisRef(
                    valid_ids_path,
                    valid_ids.size,
                    _array_sha256(valid_ids),
                    "data.mat:idx",
                ),
            }
        return FinalArtifactRecord.create(
            final_model_id=f"final-{family_token(task.endpoint.model_family)}-{branch}",
            endpoint_model_id=task.endpoint.identifier,
            final_branch=branch,
            final_role="realized_final",
            selected_tau=250 if task.endpoint.model_family.endswith("voxel") else 800,
            selected_coverage=5,
            estimator=estimator,
            scale_direction="lower",
            subject_order=subject_order,
            nuisance=nuisance,
            manifest=self._artifact(root, manifest, "selected_manifest"),
            exposure=self._artifact(root, exposure, "exposure_matrix", (12, 20)),
            scores=self._artifact(root, scores, "selected_scores", (12,)),
            feature_axis=FeatureAxisRef(
                ids,
                20,
                (
                    _array_sha256(feature_ids)
                    if task.endpoint.model_family.endswith("fiber")
                    else _sha256(ids)
                ),
                (
                    "data.mat:idx"
                    if task.endpoint.model_family.endswith("fiber")
                    else "candidate_flat_indices"
                ),
            ),
            **fiber_kwargs,
        )

    def _request(
        self,
        root: Path,
        task: TaskSpec,
        final: FinalArtifactRecord,
        *,
        delta: DeltaHFBundle | None = None,
        jitter: bool = False,
    ) -> SensitivityRequest:
        raw_dir = root / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[ArtifactRef] = []
        fiber_model = task.endpoint.model_family.endswith("fiber")
        for kind, value in (
            ("hf_component_exposure", 700.0 if fiber_model else 180.0),
            ("ulf_component_exposure", 900.0 if fiber_model else 280.0),
        ):
            path = raw_dir / f"{kind}.npy"
            values = (
                value
                + np.arange(12, dtype=np.float32)[:, None] * 3.0
                + np.arange(20, dtype=np.float32)[None, :]
            )
            np.save(path, values)
            artifacts.append(self._artifact(root, path, kind, (12, 20)))
        y_base_path = raw_dir / "y_base.npy"
        np.save(y_base_path, np.linspace(10, 21, 12))
        jitter_ref = None
        if jitter:
            manifest_path = raw_dir / "jitter_inputs.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "stnsnr_sensitivity_jitter_v1",
                        "endpoint_model_id": final.endpoint_model_id,
                        "final_model_id": final.final_model_id,
                        "final_record_hash": final.record_hash,
                        "model_family": task.endpoint.model_family,
                        "subject_order": list(final.subject_order),
                        "feature_axis_sha256": final.feature_axis.sha256,
                        "geometry": {"status": "synthetic_test_fixture"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            jitter_ref = self._artifact(root, manifest_path, "jitter_input_manifest")
        return SensitivityRequest(
            task=task,
            final=final,
            delta_hf=delta,
            output_root=root / "models" / task.endpoint.identifier / "tasks" / task.task_id,
            selected_tau_multipliers=(0.9, 1.1),
            jitter_resamples=3,
            seed=42,
            enabled_ulf_analyses=("nonfinal_branch", "gain", "total_exposure", "support", "collinearity"),
            component_exposures=tuple(artifacts),
            jitter_input_manifest=jitter_ref,
            matched_hf_final=None,
            y_base=self._artifact(root, y_base_path, "y_base", (12,)),
            hf_overlap_tau=800.0 if fiber_model else 200.0,
            rebuild_geometry=jitter,
            rebuild_delta_hf=False,
            rebuild_support_qc=False,
            rebuild_nuisance=jitter,
            jitter_fwhm_mm=2.0,
            oss_model="OSS-DBSv2",
            oss_activation_threshold=0.5,
            score=(
                {
                    "sweet_fraction": 0.2,
                    "sour_fraction": 0.15,
                    "weighted_peak_fraction": 0.25,
                    "sweet_selected_min_count": 4,
                    "sour_selected_min_count": 3,
                    "weighted_peak_min_count": 2,
                }
                if fiber_model
                else None
            ),
        )

    def _valid_delta(self, root: Path) -> DeltaHFBundle:
        delta_root = root / "delta"
        delta_root.mkdir(parents=True, exist_ok=True)
        full_path = delta_root / "delta_full.npy"
        fold_path = delta_root / "delta_folds.npy"
        support_path = delta_root / "delta_support.csv"
        np.save(full_path, np.linspace(-1.0, 1.0, 12, dtype=np.float64))
        np.save(
            fold_path,
            np.tile(np.linspace(-1.0, 1.0, 12, dtype=np.float64), (12, 1)),
        )
        support_path.write_text(
            "subject_id,support_status\n"
            + "".join(f"sub-{index:02d},adequate\n" for index in range(1, 13)),
            encoding="utf-8",
        )
        return DeltaHFBundle(
            input_status="valid",
            support_status="adequate",
            selected_hf_tau=800,
            selected_hf_coverage=5,
            full_scores=self._artifact(root, full_path, "delta_hf_full_scores", (12,)),
            fold_scores=self._artifact(root, fold_path, "delta_hf_fold_scores", (12, 12)),
            support_rows=self._artifact(root, support_path, "delta_hf_support_rows", (12,)),
        )

    def test_target_rejects_artifact_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_voxel", "selected_source_neighborhood")
            final = self._final(root, task)
            request = self._request(root, task, final)
            raw = root / request.component_exposures[1].relative_path
            raw.write_bytes(b"changed")
            with self.assertRaisesRegex(RecordError, "SHA-256 mismatch"):
                build_configured_sensitivity_target(request)

    def test_normative_fiber_axis_uses_logical_array_identity_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "selected_source_neighborhood")
            final = self._final(root, task)
            axis_path = Path(final.feature_axis.ids_path)

            self.assertNotEqual(final.feature_axis.sha256, _sha256(axis_path))
            target = build_configured_sensitivity_target(
                self._request(root, task, final)
            )

        self.assertEqual(target.subject_order, final.subject_order)
        self.assertEqual(
            target.valid_feature_ids_path,
            Path(final.valid_feature_axis.ids_path).resolve(),
        )
        self.assertEqual(target.score_config.sweet_selected_min_count, 4)
        self.assertEqual(target.score_config.sour_selected_min_count, 3)
        self.assertEqual(target.score_config.weighted_peak_min_count, 2)

    def test_ulf_fiber_sensitivity_applies_configured_minima_in_full_and_folds(self) -> None:
        analysis_root = Path(__file__).resolve().parents[2] / "analysis"
        if str(analysis_root) not in sys.path:
            sys.path.insert(0, str(analysis_root))
        module = importlib.import_module(
            "stnsnr_ulf_normative_fiber_sensitivity_observed"
        )
        score_module = importlib.import_module("stnsnr_normative_fiber_score")
        exposure = (
            900.0
            + np.arange(12, dtype=np.float32)[:, None] * 2.0
            + np.arange(10, dtype=np.float32)[None, :]
        )
        score_config = score_module.NormativeFiberScoreConfig(
            sweet_fraction=0.2,
            sour_fraction=0.15,
            weighted_peak_fraction=0.25,
            sweet_selected_min_count=4,
            sour_selected_min_count=3,
            weighted_peak_min_count=2,
        )

        with mock.patch.object(
            module,
            "partial_spearman_matrix",
            side_effect=lambda _y, x, _cov: np.concatenate(
                [np.linspace(1.0, 0.1, 6), -np.linspace(0.1, 1.0, x.shape[1] - 6)]
            ),
        ), mock.patch.object(
            module,
            "fit_linear_prediction",
            return_value=(np.array([1.0]), np.zeros(3)),
        ), mock.patch.object(
            module,
            "fit_baseline_prediction",
            return_value=(np.array([1.0]), np.zeros(2)),
        ):
            branch = module.compute_observed_fiber_sensitivity_branch(
                branch_name="configured",
                exposure=exposure,
                outcome=np.linspace(10.0, 21.0, 12),
                covariates=np.linspace(20.0, 31.0, 12),
                covariate_names=["Y_HF_ref"],
                scale_direction="higher",
                tau=800.0,
                min_coverage=5,
                subject_ids=[f"sub-{index:02d}" for index in range(12)],
                fiber_ids=np.arange(10, dtype=np.int64),
                score_config=score_config,
            )

        self.assertEqual(branch["score_support"]["sweet_actual_selected_count"], 4)
        self.assertEqual(branch["score_support"]["sour_actual_selected_count"], 3)
        self.assertEqual(branch["score_support"]["sweet_actual_peak_count"], 2)
        self.assertEqual(branch["fold_rows"][0]["sour_actual_peak_count"], 2)

    def test_ulf_nonfinal_branch_refits_on_the_realized_final_valid_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "cheap_observed_sensitivity")
            final = self._final(root, task)
            delta = self._valid_delta(root)
            target = build_configured_sensitivity_target(
                self._request(root, task, final, delta=delta)
            )
            analysis_root = Path(__file__).resolve().parents[2] / "analysis"
            if str(analysis_root) not in sys.path:
                sys.path.insert(0, str(analysis_root))
            module = importlib.import_module(
                "stnsnr_ulf_normative_fiber_sensitivity_observed"
            )
            calls: list[dict[str, object]] = []

            def fitted_branch(**kwargs):
                calls.append(kwargs)
                branch = {
                    "score_rows": [
                        {"NetULFFiberSensitivityScore": float(index)}
                        for index in range(12)
                    ]
                }
                return (
                    {
                        "status": "complete",
                        "branch": kwargs["name"],
                        "loocv_metrics": {},
                        "n_candidate_fibers": int(kwargs["exposure"].shape[1]),
                        "all_predictions_finite": True,
                    },
                    branch,
                )

            with mock.patch.object(
                module,
                "_configured_fiber_branch_result",
                side_effect=fitted_branch,
            ):
                module.run_configured_additional_sensitivities(
                    target,
                    enabled_analyses=("nonfinal_branch",),
                )

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [call["name"] for call in calls],
            ["selected_no_delta_hf", "delta_hf_adjusted"],
        )
        self.assertEqual(
            [call["covariate_names"] for call in calls],
            [["Y_HF_ref"], ["Y_HF_ref", "DeltaHFScore"]],
        )
        for call in calls:
            self.assertEqual(call["exposure"].shape, (12, 10))
            np.testing.assert_array_equal(
                call["fiber_ids"],
                np.arange(10, dtype=np.int64),
            )

    def test_normative_fiber_axis_identity_rejects_feature_order_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "selected_source_neighborhood")
            final = self._final(root, task)
            axis_path = Path(final.feature_axis.ids_path)
            np.save(axis_path, np.arange(19, -1, -1, dtype=np.int64))

            with self.assertRaisesRegex(RecordError, "feature-axis SHA-256 mismatch"):
                build_configured_sensitivity_target(self._request(root, task, final))

    def test_normative_fiber_axis_validation_keeps_score_subject_order_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "selected_source_neighborhood")
            final = self._final(root, task)
            scores_path = root / final.scores.relative_path
            with scores_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fieldnames = list(reader.fieldnames or ())
            rows[0], rows[1] = rows[1], rows[0]
            with scores_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            mismatched_final = replace(
                final,
                scores=self._artifact(root, scores_path, "selected_scores", (12,)),
            )

            with self.assertRaisesRegex(RecordError, "score subject order"):
                build_configured_sensitivity_target(
                    self._request(root, task, mismatched_final)
                )

    def test_direct_support_diagnostic_reads_full_and_fold_maximum_fractions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            support_path = Path(tmp) / "direct_support.csv"
            with support_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "subject_id",
                        "full_out_support_fraction",
                        "fold_out_support_fraction_max",
                    ],
                )
                writer.writeheader()
                for index, fold_maximum in enumerate((0.20, 0.30, 0.40, 0.96)):
                    writer.writerow(
                        {
                            "subject_id": f"sub-{index + 1:02d}",
                            "full_out_support_fraction": 0.10,
                            "fold_out_support_fraction_max": fold_maximum,
                        }
                    )
            analysis_root = Path(__file__).resolve().parents[2] / "analysis"
            if str(analysis_root) not in sys.path:
                sys.path.insert(0, str(analysis_root))
            module = importlib.import_module(
                "stnsnr_ulf_direct_voxel_sensitivity_observed"
            )

            diagnostic = module._support_diagnostic(
                SimpleNamespace(
                    model_family="ulf_voxel",
                    delta_support_path=support_path,
                )
            )

        self.assertEqual(
            diagnostic["observed_support_category"],
            "invalid_extreme_out_of_support",
        )
        self.assertEqual(diagnostic["median_out_support_fraction"], 0.10)
        self.assertEqual(diagnostic["maximum_out_support_fraction"], 0.96)

    def test_fiber_support_diagnostic_reads_subject_and_fold_maximum_fractions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            support_path = Path(tmp) / "fiber_support.csv"
            with support_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "subject_id",
                        "subject_out_candidate_fraction",
                        "maximum_fold_out_candidate_fraction",
                    ],
                )
                writer.writeheader()
                for index, fold_maximum in enumerate((0.25, 0.50, 0.60, 0.75)):
                    writer.writerow(
                        {
                            "subject_id": f"sub-{index + 1:02d}",
                            "subject_out_candidate_fraction": 0.10,
                            "maximum_fold_out_candidate_fraction": fold_maximum,
                        }
                    )
            analysis_root = Path(__file__).resolve().parents[2] / "analysis"
            if str(analysis_root) not in sys.path:
                sys.path.insert(0, str(analysis_root))
            module = importlib.import_module(
                "stnsnr_ulf_direct_voxel_sensitivity_observed"
            )

            diagnostic = module._support_diagnostic(
                SimpleNamespace(
                    model_family="ulf_fiber",
                    delta_support_path=support_path,
                )
            )

        self.assertEqual(diagnostic["observed_support_category"], "adequate")
        self.assertEqual(diagnostic["median_out_support_fraction"], 0.10)
        self.assertEqual(diagnostic["maximum_out_support_fraction"], 0.75)

    def test_ulf_neighborhood_passes_raw_components_and_selected_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_voxel", "selected_source_neighborhood")
            final = self._final(root, task)
            request = self._request(root, task, final)
            calls = []

            def runner(target, *, tau_multipliers):
                calls.append((target.component_paths, target.hf_overlap_tau, tau_multipliers))
                return {"status": "complete", "cells": [225.0, 275.0]}

            output = run_configured_sensitivity(request, direct_neighborhood_runner=runner)
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual([artifact.kind for artifact in output.artifacts], ["sensitivity_results"])
        self.assertIn("ulf_component_exposure", calls[0][0])
        self.assertEqual(calls[0][1], 200.0)
        self.assertEqual(calls[0][2], (0.9, 1.1))
        self.assertEqual(payload["final_model_id"], final.final_model_id)
        self.assertEqual(payload["final_record_hash"], final.record_hash)
        self.assertNotIn("source_status", payload)

    def test_total_exposure_runs_when_delta_dependent_sensitivities_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "cheap_observed_sensitivity")
            final = self._final(root, task)
            invalid_delta = DeltaHFBundle(
                input_status="invalid",
                support_status="invalid_extreme_out_of_support",
                selected_hf_tau=800,
                selected_hf_coverage=5,
                full_scores=None,
                fold_scores=None,
                support_rows=None,
                failure_stage="support",
            )
            request = self._request(root, task, final, delta=invalid_delta)

            def runner(target, *, enabled_analyses, tau_multipliers):
                self.assertEqual(enabled_analyses[-1], "collinearity")
                return {
                    "additional_sensitivities": {
                        "analyses": {
                            "total_exposure": {"status": "complete"},
                            "support": {"status": "not_computable", "reason": "invalid_delta_hf"},
                        }
                    },
                    "tau_multipliers": list(tau_multipliers),
                }

            output = run_configured_sensitivity(request, ulf_fiber_cheap_runner=runner)
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        analyses = payload["results"]["additional_sensitivities"]["analyses"]
        self.assertEqual(analyses["total_exposure"]["status"], "complete")
        self.assertEqual(analyses["support"]["status"], "not_computable")
        self.assertEqual(payload["score"]["sweet_selected_min_count"], 4)
        self.assertEqual(payload["score"]["sour_selected_min_count"], 3)
        self.assertEqual(payload["score"]["weighted_peak_min_count"], 2)

    def test_plain_burden_control_is_the_only_observed_phase_sensitivity_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "plain_burden_controls")
            final = self._final(root, task)
            template = self._request(root, task, final)
            context = SimpleNamespace(
                config=SimpleNamespace(
                    model=SimpleNamespace(
                        sensitivity={
                            "selected_tau_multipliers": [0.9, 1.1],
                            "ulf_nonfinal_branch": True,
                            "ulf_gain": True,
                            "ulf_total_exposure": True,
                            "ulf_support": True,
                            "ulf_collinearity": True,
                        },
                        formal={"jitter_resamples": 1000, "seed": 42},
                        oss={"model": "OSS-DBSv2", "deterministic_activation_threshold": 0.5},
                        normative_fiber={
                            "score": {
                                "sweet_fraction": 0.2,
                                "sour_fraction": 0.15,
                                "weighted_peak_fraction": 0.25,
                                "sweet_selected_min_count": 4,
                                "sour_selected_min_count": 3,
                                "weighted_peak_min_count": 2,
                            }
                        },
                    )
                ),
                store=SimpleNamespace(run_root=root),
            )
            request = SensitivityRequest.from_context(
                task,
                context,
                final,
                delta_hf=None,
                component_exposures=template.component_exposures,
                y_base=template.y_base,
                hf_overlap_tau=200.0,
            )
            invalid_task = TaskSpec(
                task_id=TaskKey(
                    endpoint_model_id=task.endpoint.identifier,
                    execution_stage="selected_source_neighborhood",
                    branch="realized_final",
                    source_reference="final_model_record",
                ).identifier,
                key=TaskKey(
                    endpoint_model_id=task.endpoint.identifier,
                    execution_stage="selected_source_neighborhood",
                    branch="realized_final",
                    source_reference="final_model_record",
                ),
                endpoint=task.endpoint,
                round_name="Round 7",
                workflow_phase="observed",
                dependencies=(),
                gate=task.gate,
                expected_artifact_kinds=("task_manifest", "sensitivity_results"),
            )
            with self.assertRaisesRegex(RecordError, "sensitivity-phase"):
                SensitivityRequest.from_context(
                    invalid_task,
                    context,
                    final,
                    delta_hf=None,
                )

            calls = []

            def runner(target, *, enabled_analyses):
                calls.append((target.operation, enabled_analyses))
                return {"status": "complete", "plain_total_exposure_mean": 1.0}

            output = run_configured_sensitivity(
                request,
                ulf_fiber_plain_control_runner=runner,
            )

        self.assertEqual(calls[0][0], "plain_burden_controls")
        self.assertEqual([artifact.kind for artifact in output.artifacts], ["control_metrics"])

    def test_supported_matrix_covers_every_planned_sensitivity_and_control_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def mutate(profiles):
                profiles["workflow"]["selection"]["models"] = [
                    "hf-voxel",
                    "hf-fiber",
                    "ulf-voxel",
                    "ulf-fiber",
                ]
                profiles["workflow"]["selection"]["connectomes"] = ["dtor"]
                profiles["workflow"]["execution"]["through"] = "report"
                profiles["study"]["paths"]["output_root"] = str(root / "outputs")

            workflow = write_profile_bundle(root, mutate=mutate)
            write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
            config = load_resolved_workflow(workflow, WorkflowOverrides())
            catalog = build_endpoint_catalog(config)
            plan = compile_execution_plan(config, catalog)
            planned = {
                (task.endpoint.model_family, task.key.execution_stage): (
                    set(task.expected_artifact_kinds) - {"task_manifest"}
                ).pop()
                for task in plan.tasks
                if task.workflow_phase == "sensitivity"
                and task.key.execution_stage != "oss_sensitivity"
            }
            planned.update(
                {
                    (task.endpoint.model_family, task.key.execution_stage): (
                        set(task.expected_artifact_kinds) - {"task_manifest"}
                    ).pop()
                    for task in plan.tasks
                    if task.endpoint.model_family == "ulf_fiber"
                    and task.key.execution_stage == "plain_burden_controls"
                }
            )

        self.assertEqual(planned, dict(SUPPORTED_SENSITIVITY_OPERATIONS))

    def test_jitter_dispatch_keeps_final_identity_and_fixed_method(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("hf_voxel", "spatial_jitter")
            final = self._final(root, task, branch="hf_source")
            request = self._request(root, task, final, jitter=True)
            calls = []

            def runner(target, *, n_jitters, jitter_fwhm_mm, seed):
                calls.append((n_jitters, jitter_fwhm_mm, seed, target.final_record_hash))
                return {"status": "complete", "replicates": n_jitters}

            output = run_configured_sensitivity(request, direct_jitter_runner=runner)
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual(calls, [(3, 2.0, 42, final.record_hash)])
        self.assertEqual(output.artifacts[0].kind, "jitter_results")
        self.assertEqual(payload["classification_feedback"], "prohibited")

    def test_ulf_jitter_rebuilds_geometry_delta_support_and_nuisance_per_replicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_voxel", "spatial_jitter")
            final = self._final(root, task)
            request = self._request(root, task, final, jitter=True)
            calls = {"geometry": 0, "delta": 0, "branch": 0}
            analysis_root = Path(__file__).resolve().parents[2] / "analysis"
            if str(analysis_root) not in sys.path:
                sys.path.insert(0, str(analysis_root))
            module = importlib.import_module("stnsnr_direct_voxel_formal_jitter")

            def geometry_builder(target, rng, sigma_mm):
                calls["geometry"] += 1
                self.assertEqual(sigma_mm, 2.0 / 2.3548200450309493)
                return {
                    "ulf_component": np.full((12, 20), 300.0, dtype=np.float32),
                    "hf_component": np.full((12, 20), 100.0, dtype=np.float32),
                    "hf_reference": np.full((12, 20), 260.0, dtype=np.float32),
                    "hf_reprogrammed": np.full((12, 20), 270.0, dtype=np.float32),
                }

            def delta_builder(target, geometry):
                calls["delta"] += 1
                return {
                    "status": "adequate",
                    "full_scores": np.linspace(0.0, 1.0, 12),
                    "fold_scores": np.tile(np.linspace(0.0, 1.0, 12), (12, 1)),
                    "support": {"maximum_out_support_fraction": 0.1},
                }

            def branch_fitter(target, geometry, delta):
                calls["branch"] += 1
                self.assertEqual(target.final_branch, "no_delta_hf")
                self.assertEqual(target.selected_tau, 250.0)
                self.assertEqual(delta["status"], "adequate")
                return {"status": "complete", "q2": 0.1}

            def runner(target, *, n_jitters, jitter_fwhm_mm, seed):
                return module.run_configured_jitter(
                    target,
                    n_jitters=n_jitters,
                    jitter_fwhm_mm=jitter_fwhm_mm,
                    seed=seed,
                    geometry_builder=geometry_builder,
                    delta_builder=delta_builder,
                    branch_fitter=branch_fitter,
                )

            output = run_configured_sensitivity(request, direct_jitter_runner=runner)
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual(calls, {"geometry": 3, "delta": 3, "branch": 3})
        self.assertEqual(payload["results"]["completed_replicates"], 3)
        self.assertTrue(payload["results"]["selected_source_identity_fixed"])

    def test_ulf_fiber_jitter_uses_the_same_per_replicate_rebuild_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("ulf_fiber", "spatial_jitter")
            final = self._final(root, task)
            request = self._request(root, task, final, jitter=True)
            calls = {"geometry": 0, "delta": 0, "branch": 0}
            analysis_root = Path(__file__).resolve().parents[2] / "analysis"
            if str(analysis_root) not in sys.path:
                sys.path.insert(0, str(analysis_root))
            module = importlib.import_module("stnsnr_normative_fiber_formal_jitter")

            def geometry_builder(target, rng, sigma_mm):
                calls["geometry"] += 1
                return {"fiber_ids": np.arange(20), "ulf_component": np.ones((12, 20))}

            def delta_builder(target, geometry):
                calls["delta"] += 1
                return {
                    "status": "limited",
                    "full_scores": np.zeros(12),
                    "fold_scores": np.zeros((12, 12)),
                }

            def branch_fitter(target, geometry, delta):
                calls["branch"] += 1
                return {"status": "complete"}

            def runner(target, *, n_jitters, jitter_fwhm_mm, seed):
                return module.run_configured_jitter(
                    target,
                    n_jitters=n_jitters,
                    jitter_fwhm_mm=jitter_fwhm_mm,
                    seed=seed,
                    geometry_builder=geometry_builder,
                    delta_builder=delta_builder,
                    branch_fitter=branch_fitter,
                )

            output = run_configured_sensitivity(request, fiber_jitter_runner=runner)
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual(calls, {"geometry": 3, "delta": 3, "branch": 3})
        self.assertEqual(payload["results"]["completed_replicates"], 3)

    def test_default_jitter_fails_explicitly_when_geometry_contract_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("hf_voxel", "spatial_jitter")
            final = self._final(root, task, branch="hf_source")
            request = self._request(root, task, final, jitter=True)
            with self.assertRaisesRegex(
                RuntimeError,
                "builder='direct_efield_resample_v1'",
            ):
                run_configured_sensitivity(request)

    def test_default_direct_and_fiber_neighborhood_runners_are_executable(self) -> None:
        for family in ("hf_voxel", "ulf_fiber"):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                task = self._task(family, "selected_source_neighborhood")
                final = self._final(
                    root,
                    task,
                    branch="hf_source" if family.startswith("hf_") else "no_delta_hf",
                )
                request = self._request(root, task, final)
                output = run_configured_sensitivity(request)
                payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))
                cells = payload["results"]["cells"]
                self.assertEqual([cell["tau_multiplier"] for cell in cells], [0.9, 1.1])
                self.assertTrue(all(cell["selected_coverage"] == 5 for cell in cells))

    def test_default_ulf_additional_runners_keep_total_exposure_delta_independent(self) -> None:
        for family in ("ulf_voxel", "ulf_fiber"):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage = (
                    "additional_sensitivities"
                    if family == "ulf_voxel"
                    else "cheap_observed_sensitivity"
                )
                task = self._task(family, stage)
                final = self._final(root, task)
                invalid_delta = DeltaHFBundle(
                    input_status="invalid",
                    support_status="invalid_extreme_out_of_support",
                    selected_hf_tau=200 if family.endswith("voxel") else 800,
                    selected_hf_coverage=5,
                    full_scores=None,
                    fold_scores=None,
                    support_rows=None,
                    failure_stage="support",
                )
                request = self._request(root, task, final, delta=invalid_delta)
                output = run_configured_sensitivity(request)
                payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))
                results = payload["results"]
                analyses = (
                    results["analyses"]
                    if family == "ulf_voxel"
                    else results["additional_sensitivities"]["analyses"]
                )
                self.assertEqual(
                    analyses["total_exposure"]["status"],
                    "complete",
                    msg=str(analyses["total_exposure"]),
                )
                self.assertEqual(analyses["support"]["status"], "not_computable")
                self.assertEqual(analyses["nonfinal_branch"]["status"], "not_computable")

    def test_sensitivity_service_returns_endpoint_local_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("hf_voxel", "selected_source_neighborhood")
            final = self._final(root, task, branch="hf_source")
            store = ConfiguredRunStore.create(
                output_root=root,
                study_id="study",
                provenance={"configuration_hash": "hash", "input_hashes": {}, "code_provenance": {}},
            )
            context = RunContext(store=store, catalog=(), config=object())

            def inputs_loader(_task, _context, _final):
                return SensitivityRuntimeInputs()

            service = SensitivityService(
                runner=lambda _request: (_ for _ in ()).throw(RecordError("missing lower-level input")),
                final_loader=lambda _task, _context: final,
                inputs_loader=inputs_loader,
                request_factory=lambda **_: self._request(root, task, final),
            )
            result = service.execute(task, context)

        self.assertEqual(result.status, TaskStatus.EXECUTION_FAILURE)
        self.assertIn("missing lower-level input", result.detail)

    def test_sensitivity_service_reports_only_final_linked_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task("hf_voxel", "selected_source_neighborhood")
            final = self._final(root, task, branch="hf_source")
            result_path = root / "sensitivity.json"
            result_path.write_text("{}\n", encoding="utf-8")
            store = ConfiguredRunStore.create(
                output_root=root,
                study_id="study",
                provenance={"configuration_hash": "hash", "input_hashes": {}, "code_provenance": {}},
            )
            context = RunContext(store=store, catalog=(), config=object())
            service = SensitivityService(
                runner=lambda _request: SensitivityServiceOutput(
                    (TaskArtifact("sensitivity_results", result_path),)
                ),
                final_loader=lambda _task, _context: final,
                inputs_loader=lambda _task, _context, _final: SensitivityRuntimeInputs(),
                request_factory=lambda **_: self._request(root, task, final),
            )
            result = service.execute(task, context)

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.facts["final_model_id"], final.final_model_id)
        self.assertEqual(result.facts["final_artifact_record_hash"], final.record_hash)
        self.assertNotIn("source_status", result.facts)
        self.assertNotIn("prediction_status", result.facts)


def family_token(value: str) -> str:
    return value.replace("_", "-")


if __name__ == "__main__":
    unittest.main()
