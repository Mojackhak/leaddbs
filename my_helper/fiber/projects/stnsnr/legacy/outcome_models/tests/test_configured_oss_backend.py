"""Tests for final-record-locked configured OSS/pPAM sensitivity."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import (
    RunContext,
    TaskExecutionRecord,
    TaskResult,
    TaskStatus,
)
from outcome_models.planner import compile_execution_plan
from outcome_models.records import (
    ArtifactRef,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.legacy_oss import run_configured_oss
from outcome_models.services.oss import (
    OSSRequest,
    OSSService,
    OSSSidecarBundle,
    OSSSidecarsUnavailable,
    load_oss_sidecar_bundle,
)
from outcome_models.tests.helpers import (
    clinical_rows_for_scale,
    write_clinical_rows,
    write_profile_bundle,
)


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


class ConfiguredOSSBackendTests(unittest.TestCase):
    def _fixture(self, root: Path, model: str) -> tuple[RunContext, object, object]:
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = [model]
            profiles["workflow"]["execution"]["through"] = "sensitivity"
            profiles["study"]["paths"]["output_root"] = str(root / "outputs")

        workflow = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        family = "ulf_fiber" if model == "ulf-fiber" else "hf_fiber"
        task = next(
            item
            for item in plan.tasks
            if item.endpoint.model_family == family
            and item.key.execution_stage == "oss_sensitivity"
        )
        store = ConfiguredRunStore.create(
            output_root=root / "outputs",
            study_id=config.study.study_id,
            provenance={
                "configuration_hash": config.configuration_hash,
                "input_hashes": {},
                "code_provenance": {},
            },
        )
        store.initialize(
            resolved_workflow={},
            endpoint_catalog=[row.as_dict() for row in catalog],
            execution_plan=plan.as_dict(),
        )
        return RunContext(store=store, catalog=tuple(catalog), config=config), task, plan

    @staticmethod
    def _artifact(
        run_root: Path,
        path: Path,
        kind: str,
        shape: tuple[int, ...] = (),
    ) -> ArtifactRef:
        return ArtifactRef(
            task_id="fixture-task",
            kind=kind,
            relative_path=path.relative_to(run_root).as_posix(),
            sha256=sha256_file(path),
            shape=shape,
        )

    def _final(self, context: RunContext, task, *, branch: str) -> FinalArtifactRecord:
        root = context.store.run_root
        artifact_root = root / "fixture" / "final"
        artifact_root.mkdir(parents=True, exist_ok=True)
        subject_order = tuple(f"sub-{index:02d}" for index in range(1, 13))
        feature_ids = np.asarray([101, 103, 107, 109, 113, 127], dtype=np.int64)
        feature_path = artifact_root / "fiber_ids.npy"
        exposure_path = artifact_root / "peak_exposure.npy"
        scores_path = artifact_root / "scores.csv"
        manifest_path = artifact_root / "manifest.json"
        np.save(feature_path, feature_ids)
        np.save(
            exposure_path,
            np.arange(len(subject_order) * feature_ids.size, dtype=np.float32).reshape(
                len(subject_order), feature_ids.size
            ),
        )
        nuisance_column = "Y_base" if branch == "hf_source" else "Y_HF_ref"
        score_column = "NetFiberScore" if branch == "hf_source" else "NetULFFiberScore"
        y_values = [34, 28, 31, 24, 29, 20, 26, 18, 22, 15, 19, 12]
        with scores_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["subject_id", "Y_post", nuisance_column, score_column],
            )
            writer.writeheader()
            for index, subject_id in enumerate(subject_order):
                writer.writerow(
                    {
                        "subject_id": subject_id,
                        "Y_post": y_values[index],
                        nuisance_column: 40 + ((index * 7) % 11),
                        score_column: ((index * 5) % 13) - 6,
                    }
                )
        manifest_path.write_text(
            json.dumps(
                {
                    "scale_direction": "lower",
                    "subject_order": list(subject_order),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        full_weights_path = artifact_root / "selected_full_weights.npy"
        full_weights = np.asarray([1.0, np.nan, -0.5, 0.25, np.nan, np.nan], dtype=np.float32)
        np.save(full_weights_path, full_weights)
        valid_feature_ids = feature_ids[np.isfinite(full_weights)]
        valid_feature_path = artifact_root / "valid_fiber_ids.npy"
        np.save(valid_feature_path, valid_feature_ids)
        feature_axis = FeatureAxisRef(
            ids_path=feature_path,
            count=feature_ids.size,
            sha256=_array_sha256(feature_ids),
            identity_source="data.mat:idx",
        )
        nuisance = NuisancePlan.for_branch(branch, None)
        return FinalArtifactRecord.create(
            final_model_id=f"configured-{task.endpoint.model_family}-final",
            endpoint_model_id=task.endpoint.identifier,
            final_branch=branch,
            final_role="primary",
            selected_tau=800,
            selected_coverage=5,
            estimator="peak_efield_partial_spearman",
            scale_direction="lower",
            subject_order=subject_order,
            nuisance=nuisance,
            manifest=self._artifact(root, manifest_path, "selected_manifest"),
            exposure=self._artifact(
                root,
                exposure_path,
                "exposure_matrix",
                (len(subject_order), feature_ids.size),
            ),
            scores=self._artifact(root, scores_path, "selected_scores", (len(subject_order),)),
            feature_axis=feature_axis,
            full_weights=self._artifact(
                root,
                full_weights_path,
                "selected_full_weights",
                (feature_ids.size,),
            ),
            valid_feature_axis=FeatureAxisRef(
                ids_path=valid_feature_path,
                count=valid_feature_ids.size,
                sha256=_array_sha256(valid_feature_ids),
                identity_source="data.mat:idx",
            ),
        )

    def _sidecars(
        self,
        context: RunContext,
        final: FinalArtifactRecord,
        *,
        component: str,
        frequency_hz: float,
        hf_overlap_exclusion_applied: bool | None = None,
        hf_overlap_definition: str = "matched_hf_peak_efield_selected_tau",
        swap_fiber_order: bool = False,
        modeled_frequency_hz: float | None = None,
        first_probability: float | None = None,
        parameter_overrides: dict[str, object] | None = None,
        metadata_overrides: dict[str, object] | None = None,
    ) -> OSSSidecarBundle:
        root = context.store.run_root
        sidecar_root = root / "fixture" / "oss"
        sidecar_root.mkdir(parents=True, exist_ok=True)
        fiber_ids = np.load(final.valid_feature_axis.ids_path)
        if swap_fiber_order:
            fiber_ids = fiber_ids[::-1]
        fiber_path = sidecar_root / "oss_fiber_ids.npy"
        matrix_path = sidecar_root / "X_oss_float32_fiber_major.npy"
        parameter_path = sidecar_root / "oss_parameter_manifest.json"
        metadata_path = sidecar_root / "oss_activation_sidecar_metadata.json"
        np.save(fiber_path, fiber_ids)
        base = np.asarray(
            [
                [0.40, 0.50, 0.90],
                [0.60, 0.20, 0.50],
                [0.10, 0.70, 0.80],
                [0.80, 0.10, 0.20],
            ],
            dtype=np.float32,
        )
        if first_probability is not None:
            base[0, 0] = first_probability
        probabilities = np.vstack([base for _ in range(3)])
        np.save(matrix_path, probabilities)
        compatibility_hash = "f" * 64
        parameter = {
            "schema_version": "four_model_v1_oss_parameter_manifest",
            "oss_model": "OSS-DBSv2",
            "activation_model": "pPAM",
            "ppam_sample_count": 10,
            "final_model_id": final.final_model_id,
            "final_record_hash": final.record_hash,
            "endpoint_id": final.endpoint_model_id,
            "connectome": "dtor",
            "oss_exposure_component": component,
            "requested_frequency_hz": frequency_hz,
            "oss_parameter_frequency_hz": (
                frequency_hz if modeled_frequency_hz is None else modeled_frequency_hz
            ),
            "frequency_source": "Lead-DBS stimulation protocol",
            "frequency_validation_status": "verified_exact_match",
            "canonical_hemisphere": "right",
            "left_to_right_mapping_method": "ea_flip_lr_nonlinear",
            "left_to_right_mapping_identity": {
                "method": "ea_flip_lr_nonlinear",
                "code_sha256": "d" * 64,
                "transform_sha256": "e" * 64,
            },
            "hemisphere_source_merge_rule": "max_probability_union",
            "subject_order": list(final.subject_order),
            "selected_source_feature_axis_sha256": final.feature_axis.sha256,
            "valid_feature_axis_sha256": final.valid_feature_axis.sha256,
            "oss_fiber_ids_sha256": sha256_file(fiber_path),
            "selected_tau": final.selected_tau,
            "selected_coverage": final.selected_coverage,
            "missing_subjects": [],
            "failed_subjects": [],
            "compatibility_hash": compatibility_hash,
        }
        if hf_overlap_exclusion_applied is not None:
            parameter["hf_overlap_exclusion_applied"] = hf_overlap_exclusion_applied
            parameter["hf_overlap_definition"] = hf_overlap_definition
        if parameter_overrides is not None:
            parameter.update(parameter_overrides)
        parameter_path.write_text(json.dumps(parameter) + "\n", encoding="utf-8")
        metadata = {
            "schema_version": "four_model_v1_oss_activation_metadata",
            "final_model_id": final.final_model_id,
            "final_record_hash": final.record_hash,
            "matrix_shape": list(probabilities.shape),
            "matrix_dtype": "float32",
            "matrix_range": [float(probabilities.min()), float(probabilities.max())],
            "finite_check_status": "passed",
            "activation_value_type": "pPAM_activation_probability",
            "ppam_sample_count": 10,
            "canonical_hemisphere": "right",
            "left_to_right_mapping_method": "ea_flip_lr_nonlinear",
            "left_to_right_mapping_identity": {
                "method": "ea_flip_lr_nonlinear",
                "code_sha256": "d" * 64,
                "transform_sha256": "e" * 64,
            },
            "hemisphere_source_merge_rule": "max_probability_union",
            "subject_order": list(final.subject_order),
            "valid_feature_axis_sha256": final.valid_feature_axis.sha256,
            "oss_fiber_ids_sha256": sha256_file(fiber_path),
            "compatibility_hash": compatibility_hash,
        }
        if metadata_overrides is not None:
            metadata.update(metadata_overrides)
        metadata_path.write_text(
            json.dumps(metadata) + "\n",
            encoding="utf-8",
        )
        return OSSSidecarBundle(
            final_model_id=final.final_model_id,
            final_record_hash=final.record_hash,
            compatibility_hash=compatibility_hash,
            activation_probabilities=self._artifact(
                root,
                matrix_path,
                "oss_activation_probabilities",
                probabilities.shape,
            ),
            fiber_ids=self._artifact(
                root,
                fiber_path,
                "oss_fiber_ids",
                (fiber_ids.size,),
            ),
            parameter_manifest=self._artifact(
                root,
                parameter_path,
                "oss_parameter_manifest",
            ),
            activation_metadata=self._artifact(
                root,
                metadata_path,
                "oss_activation_metadata",
            ),
        )

    def test_backend_thresholds_ppam_at_point_five_and_writes_exact_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)
            captured: dict[str, object] = {}

            def numerical_runner(target):
                fit = np.load(target.fit_activation_path)
                captured["fit"] = fit
                captured["target"] = target
                return {
                    "oss_result_status": "complete",
                    "observed_loocv_spearman_rho": 0.2,
                }

            output = run_configured_oss(request, numerical_runner=numerical_runner)

            self.assertEqual([item.kind for item in output.artifacts], ["oss_activation_results"])
            fit = captured["fit"]
            self.assertEqual(fit.dtype, np.float32)
            self.assertEqual(set(np.unique(fit)), {0.0, 1.0})
            self.assertEqual(fit.shape, (12, 3))
            self.assertEqual(fit[0].tolist(), [0.0, 1.0, 1.0])
            np.testing.assert_array_equal(
                np.load(captured["target"].fiber_ids_path),
                np.asarray([101, 107, 109], dtype=np.int64),
            )
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))
            self.assertEqual(payload["final_model_id"], final.final_model_id)
            self.assertEqual(payload["final_record_hash"], final.record_hash)
            self.assertEqual(payload["fit_activation_definition"], "pPAM_probability_ge_0.5")
            self.assertEqual(payload["hemisphere_merge_rule"], "max_probability_union")
            self.assertNotIn("source_status", payload)
            self.assertNotIn("prediction_status", payload)

    def test_default_numerical_backend_runs_on_binary_ppam(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
            )
            request = replace(
                OSSRequest.from_context(task, context, final, sidecars=sidecars),
                smoke_permutations=3,
            )

            output = run_configured_oss(request)

            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))
            self.assertEqual(payload["numerical_results"]["permutation_status"], "complete")
            self.assertEqual(payload["numerical_results"]["B"], 3)
            self.assertTrue(Path(payload["outputs"]["loocv_predictions_csv"]).is_file())
            self.assertTrue(Path(payload["outputs"]["weights_npy"]).is_file())

    def test_rejects_fiber_axis_order_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
                swap_fiber_order=True,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            with self.assertRaisesRegex(RecordError, "fiber order"):
                run_configured_oss(request, numerical_runner=lambda target: {})

    def test_rejects_frequency_drift_before_fitting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=110.0,
                modeled_frequency_hz=130.0,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            with self.assertRaisesRegex(RecordError, "frequency"):
                run_configured_oss(request, numerical_runner=lambda target: {})

    def test_accepts_verified_subject_side_frequency_maps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            frequencies = {
                f"{subject_id}:{side}": (110.0 if index < 6 else 130.0)
                for index, subject_id in enumerate(final.subject_order)
                for side in ("L", "R")
            }
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=110.0,
                parameter_overrides={
                    "frequency_scope": "subject_side_specific",
                    "requested_frequency_hz": None,
                    "oss_parameter_frequency_hz": None,
                    "frequency_validation_status": (
                        "verified_exact_match_per_subject_side"
                    ),
                    "requested_frequencies_hz": frequencies,
                    "modeled_frequencies_hz": frequencies,
                },
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            output = run_configured_oss(request, numerical_runner=lambda target: {})
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))

        self.assertEqual(payload["frequency_scope"], "subject_side_specific")
        self.assertIsNone(payload["requested_frequency_hz"])
        self.assertEqual(payload["requested_frequencies_hz"], frequencies)

    def test_rejects_unexpected_manifest_schema_versions(self) -> None:
        cases = (
            (
                "parameter manifest",
                {"parameter_overrides": {"schema_version": "four_model_v0"}},
            ),
            (
                "activation metadata",
                {"metadata_overrides": {"schema_version": "four_model_v0"}},
            ),
        )
        for label, overrides in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                context, task, _ = self._fixture(Path(tmp), "hf-fiber")
                final = self._final(context, task, branch="hf_source")
                sidecars = self._sidecars(
                    context,
                    final,
                    component="HF_only_reference",
                    frequency_hz=130.0,
                    **overrides,
                )
                request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

                with self.assertRaisesRegex(RecordError, f"{label} schema version"):
                    run_configured_oss(request, numerical_runner=lambda target: {})

    def test_rejects_manifest_ppam_sample_count_other_than_ten(self) -> None:
        cases = (
            ("parameter manifest", {"parameter_overrides": {"ppam_sample_count": 9}}),
            ("activation metadata", {"metadata_overrides": {"ppam_sample_count": 9}}),
        )
        for label, overrides in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                context, task, _ = self._fixture(Path(tmp), "hf-fiber")
                final = self._final(context, task, branch="hf_source")
                sidecars = self._sidecars(
                    context,
                    final,
                    component="HF_only_reference",
                    frequency_hz=130.0,
                    **overrides,
                )
                request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

                with self.assertRaisesRegex(RecordError, f"{label} pPAM sample count"):
                    run_configured_oss(request, numerical_runner=lambda target: {})

    def test_rejects_activation_probabilities_off_activated_count_lattice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
                first_probability=0.49,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            with self.assertRaisesRegex(RecordError, "activated_count/10"):
                run_configured_oss(request, numerical_runner=lambda target: {})

    def test_ulf_requires_addon_component_and_hf_overlap_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "ulf-fiber")
            final = self._final(context, task, branch="no_delta_hf")
            invalid = self._sidecars(
                context,
                final,
                component="ULF_addon_component",
                frequency_hz=10.0,
                hf_overlap_exclusion_applied=False,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=invalid)
            with self.assertRaisesRegex(RecordError, "HF-overlap"):
                run_configured_oss(request, numerical_runner=lambda target: {})

            valid = self._sidecars(
                context,
                final,
                component="ULF_addon_component",
                frequency_hz=10.0,
                hf_overlap_exclusion_applied=True,
            )
            valid_request = OSSRequest.from_context(task, context, final, sidecars=valid)
            output = run_configured_oss(valid_request, numerical_runner=lambda target: {})
            self.assertEqual(output.artifacts[0].kind, "oss_activation_results")

    def test_ulf_allows_explicit_hf_source_absent_overlap_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "ulf-fiber")
            final = self._final(context, task, branch="no_delta_hf")
            sidecars = self._sidecars(
                context,
                final,
                component="ULF_addon_component",
                frequency_hz=10.0,
                hf_overlap_exclusion_applied=True,
                hf_overlap_definition="hf_source_absent_all_false",
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            output = run_configured_oss(request, numerical_runner=lambda target: {})

            self.assertEqual(output.artifacts[0].kind, "oss_activation_results")
            payload = json.loads(output.artifacts[0].path.read_text(encoding="utf-8"))
            self.assertEqual(payload["hf_overlap_definition"], "hf_source_absent_all_false")

    def test_service_reports_missing_sidecars_as_explicit_input_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")

            def missing_loader(*_args):
                raise OSSSidecarsUnavailable("no final-linked OSS sidecar bundle")

            service = OSSService(
                final_loader=lambda _task, _context: final,
                sidecar_loader=missing_loader,
                runner=run_configured_oss,
            )
            result = service.execute(task, context)

            self.assertEqual(result.status, TaskStatus.INPUT_FAILURE)
            self.assertIn("missing_oss_sidecars", result.detail)
            self.assertEqual(result.facts["final_model_id"], final.final_model_id)
            self.assertNotIn("source_status", result.facts)
            self.assertNotIn("prediction_status", result.facts)

    def test_sidecar_loader_reads_only_the_typed_preparation_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, plan = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
            )
            producer = next(
                item
                for item in plan.tasks
                if item.endpoint.identifier == task.endpoint.identifier
                and item.key.execution_stage == "oss_sidecar_preparation"
            )
            context.results[producer.task_id] = TaskExecutionRecord(
                task=producer,
                result=TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"oss_sidecar_bundle": sidecars.as_dict()},
                ),
            )
            unrelated = next(
                item
                for item in plan.tasks
                if item.endpoint.identifier == task.endpoint.identifier
                and item.key.execution_stage == "candidate_source_smoke"
            )
            context.results[unrelated.task_id] = TaskExecutionRecord(
                task=unrelated,
                result=TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"oss_sidecar_bundle": sidecars.as_dict()},
                ),
            )

            loaded = load_oss_sidecar_bundle(task, context, final)

        self.assertEqual(loaded, sidecars)

    def test_service_success_has_no_classification_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
            )
            service = OSSService(
                final_loader=lambda _task, _context: final,
                sidecar_loader=lambda _task, _context, _final: sidecars,
                runner=lambda request: run_configured_oss(
                    request,
                    numerical_runner=lambda target: {"oss_result_status": "complete"},
                ),
            )

            result = service.execute(task, context)

            self.assertEqual(result.status, TaskStatus.COMPLETED)
            self.assertEqual(result.facts["final_model_id"], final.final_model_id)
            self.assertEqual(result.facts["final_record_hash"], final.record_hash)
            self.assertTrue(result.facts["oss_sensitivity_complete"])
            self.assertNotIn("source_status", result.facts)
            self.assertNotIn("prediction_status", result.facts)
            self.assertEqual([item.kind for item in result.artifacts], ["oss_activation_results"])

    def test_backend_rejects_namespaced_classification_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, _ = self._fixture(Path(tmp), "hf-fiber")
            final = self._final(context, task, branch="hf_source")
            sidecars = self._sidecars(
                context,
                final,
                component="HF_only_reference",
                frequency_hz=130.0,
            )
            request = OSSRequest.from_context(task, context, final, sidecars=sidecars)

            with self.assertRaisesRegex(RecordError, "classification"):
                run_configured_oss(
                    request,
                    numerical_runner=lambda target: {
                        "hf_norm_fiber_source_status": "scan_fallback_accepted"
                    },
                )


if __name__ == "__main__":
    unittest.main()
