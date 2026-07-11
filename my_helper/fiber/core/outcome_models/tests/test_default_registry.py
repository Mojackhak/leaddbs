"""Tests for the production configured service registry."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import nibabel as nib

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import (
    RunContext,
    TaskArtifact,
    TaskExecutionRecord,
    TaskResult,
    TaskStatus,
)
from outcome_models.planner import compile_execution_plan
from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    FinalArtifactRecord,
    HFSourceRecord,
    NuisancePlan,
    RecordError,
    ULFBranchRecord,
)
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.default_registry import _ConfiguredRuntime, build_default_service_registry
from outcome_models.tests.helpers import (
    clinical_rows_for_scale,
    write_clinical_rows,
    write_profile_bundle,
)


class DefaultRegistryTests(unittest.TestCase):
    def _fixture(self, root: Path):
        def mutate(profiles):
            profiles["workflow"]["execution"]["through"] = "report"
            profiles["study"]["paths"]["output_root"] = str(root / "outputs")

        workflow = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
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
        return RunContext(store=store, catalog=tuple(catalog), config=config), plan

    @staticmethod
    def _artifact_ref(
        context: RunContext,
        path: Path,
        kind: str,
        shape: tuple[int, ...] = (),
    ) -> ArtifactRef:
        return ArtifactRef(
            task_id="producer",
            kind=kind,
            relative_path=path.relative_to(context.store.run_root).as_posix(),
            sha256=sha256_file(path),
            shape=shape,
        )

    def _final(
        self,
        context: RunContext,
        task,
        *,
        branch: str = "hf_source",
        feature_ids_values: np.ndarray | None = None,
    ) -> FinalArtifactRecord:
        root = context.store.run_root / "models" / task.endpoint.identifier / "producer"
        root.mkdir(parents=True, exist_ok=True)
        subject_order = tuple(f"sub-{index:02d}" for index in range(1, 13))
        feature_ids = root / "feature_ids.npy"
        exposure = root / "exposure.npy"
        manifest = root / "manifest.json"
        scores = root / "scores.csv"
        values = (
            np.arange(20, dtype=np.int64)
            if feature_ids_values is None
            else np.asarray(feature_ids_values, dtype=np.int64)
        )
        np.save(feature_ids, values)
        np.save(exposure, np.ones((12, 20), dtype=np.float32))
        manifest.write_text("{}\n", encoding="utf-8")
        scores.write_text("subject_id,Y_post,Y_base\n", encoding="utf-8")
        nuisance = NuisancePlan.for_branch(branch, None)
        return FinalArtifactRecord.create(
            final_model_id=f"final-{task.endpoint.model_family}-{branch}",
            endpoint_model_id=task.endpoint.identifier,
            final_branch=branch,
            final_role="realized_final",
            selected_tau=200 if task.endpoint.model_family.endswith("voxel") else 800,
            selected_coverage=5,
            estimator="partial_spearman",
            scale_direction="lower",
            subject_order=subject_order,
            nuisance=nuisance,
            manifest=self._artifact_ref(context, manifest, "selected_manifest"),
            exposure=self._artifact_ref(context, exposure, "exposure_matrix", (12, 20)),
            scores=self._artifact_ref(context, scores, "selected_scores", (12,)),
            feature_axis=FeatureAxisRef(
                feature_ids,
                int(values.size),
                sha256_file(feature_ids),
                "candidate_flat_indices",
            ),
        )

    @staticmethod
    def _hf_source(
        task,
        final: FinalArtifactRecord,
        *,
        prediction_status: str = "error_predictive",
    ) -> HFSourceRecord:
        return HFSourceRecord.create(
            resolver_task_id=task.task_id,
            endpoint_model_id=task.endpoint.identifier,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status=prediction_status,
            threshold_source="pre_specified",
            selected_tau=final.selected_tau,
            selected_coverage=final.selected_coverage,
            subject_order=final.subject_order,
            feature_axis=final.feature_axis,
            artifacts=(final.manifest, final.exposure, final.scores),
        )

    def _delta_bundle(
        self,
        context: RunContext,
        *,
        tau: float,
        coverage: int,
        subject_order: tuple[str, ...],
    ) -> DeltaHFBundle:
        root = context.store.run_root / "delta_hf"
        root.mkdir(parents=True, exist_ok=True)
        full = root / "full.npy"
        folds = root / "folds.npy"
        support = root / "support.csv"
        np.save(full, np.arange(len(subject_order), dtype=np.float64))
        np.save(folds, np.ones((len(subject_order), len(subject_order)), dtype=np.float64))
        support.write_text("subject_id,out_support_fraction\n", encoding="utf-8")
        return DeltaHFBundle(
            input_status="valid",
            support_status="adequate",
            selected_hf_tau=tau,
            selected_hf_coverage=coverage,
            full_scores=self._artifact_ref(
                context,
                full,
                "delta_hf_full_scores",
                (len(subject_order),),
            ),
            fold_scores=self._artifact_ref(
                context,
                folds,
                "delta_hf_fold_scores",
                (len(subject_order), len(subject_order)),
            ),
            support_rows=self._artifact_ref(
                context,
                support,
                "delta_hf_support_rows",
                (len(subject_order),),
            ),
        )

    def test_every_planned_operation_resolves_without_a_default_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            registry = build_default_service_registry(context)

        unresolved = [
            (task.endpoint.model_family, task.key.execution_stage)
            for task in plan.tasks
            if registry.resolve(task) is None
        ]
        self.assertEqual(unresolved, [])
        self.assertIsNone(registry.default)

    def test_registry_construction_is_lazy_and_does_not_require_legacy_readiness_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, _ = self._fixture(Path(tmp))
            legacy_readiness = Path(tmp) / "summary" / "latest" / "component_availability.csv"
            self.assertFalse(legacy_readiness.exists())

            registry = build_default_service_registry(context)

        self.assertTrue(registry.by_operation)
        self.assertFalse(legacy_readiness.exists())

    def test_direct_flip_adapter_binds_repository_and_matlab_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, _ = self._fixture(Path(tmp))
            runtime = _ConfiguredRuntime(context)

            flipped, qc = runtime.flip_backend(
                repo_root=Path(tmp) / "ignored-repository-root",
                matlab_bin=Path(tmp) / "ignored-matlab-binary",
                side_paths={},
                preprocess_dir=Path(tmp) / "preprocess",
                force=False,
            )

        self.assertEqual(flipped, {})
        self.assertEqual(qc["status"], "SKIPPED")

    def test_ulf_sensitivity_rejects_hf_final_not_bound_by_exact_input_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            ulf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel"
                and task.key.execution_stage == "additional_sensitivities"
            )
            lock_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "input_hf_lock"
            )
            hf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_voxel"
                and task.endpoint.scale_id == ulf_task.endpoint.scale_id
                and task.key.execution_stage == "observed_source_resolver"
            )
            hf_final = self._final(context, hf_task)
            resolver_source = self._hf_source(hf_task, hf_final)
            locked_source = self._hf_source(
                hf_task,
                hf_final,
                prediction_status="error_nonpredictive",
            )
            context.results[lock_task.task_id] = TaskExecutionRecord(
                lock_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"hf_source_record": locked_source.as_dict()},
                ),
            )
            context.results[hf_task.task_id] = TaskExecutionRecord(
                hf_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={
                        "hf_source_record": resolver_source.as_dict(),
                        "final_model_record": hf_final.as_dict(),
                    },
                ),
            )

            with self.assertRaisesRegex(RecordError, "locked HF source"):
                _ConfiguredRuntime(context)._matched_hf_final(ulf_task, context)

    def test_no_delta_final_uses_valid_endpoint_delta_for_adjusted_sensitivity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            ulf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel"
                and task.key.execution_stage == "additional_sensitivities"
            )
            lock_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "input_hf_lock"
            )
            sidecar_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "preprocessing_sidecars"
            )
            branch_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "observed_branch_resolver"
                and task.key.branch == "no_delta_hf"
            )
            hf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_voxel"
                and task.endpoint.scale_id == ulf_task.endpoint.scale_id
                and task.key.execution_stage == "observed_source_resolver"
            )
            hf_final = self._final(context, hf_task)
            hf_source = self._hf_source(hf_task, hf_final)
            ulf_final = self._final(context, ulf_task, branch="no_delta_hf")
            delta = self._delta_bundle(
                context,
                tau=hf_final.selected_tau,
                coverage=hf_final.selected_coverage,
                subject_order=hf_final.subject_order,
            )
            branch = ULFBranchRecord.create(
                resolver_task_id=branch_task.task_id,
                endpoint_model_id=ulf_task.endpoint.identifier,
                branch="no_delta_hf",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_nonpredictive",
                threshold_source="pre_specified",
                selected_tau=ulf_final.selected_tau,
                selected_coverage=ulf_final.selected_coverage,
                adjacent_support=2,
                subject_order=ulf_final.subject_order,
                feature_axis=ulf_final.feature_axis,
                nuisance=ulf_final.nuisance,
                artifacts=(ulf_final.manifest, ulf_final.exposure, ulf_final.scores),
            )
            context.results[lock_task.task_id] = TaskExecutionRecord(
                lock_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"hf_source_record": hf_source.as_dict()},
                ),
            )
            context.results[hf_task.task_id] = TaskExecutionRecord(
                hf_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={
                        "hf_source_record": hf_source.as_dict(),
                        "final_model_record": hf_final.as_dict(),
                    },
                ),
            )
            context.results[sidecar_task.task_id] = TaskExecutionRecord(
                sidecar_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={
                        "delta_hf_bundle": delta.as_dict(),
                        "hf_source_record_hash": hf_source.record_hash,
                    },
                ),
            )
            context.results[branch_task.task_id] = TaskExecutionRecord(
                branch_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"ulf_branch_record": branch.as_dict()},
                ),
            )

            inputs = _ConfiguredRuntime(context).sensitivity_inputs(
                ulf_task,
                context,
                ulf_final,
            )

        self.assertIsNotNone(inputs.delta_hf)
        self.assertEqual(inputs.delta_hf.record_hash, delta.record_hash)

    def test_hf_direct_jitter_manifest_uses_exact_sidecar_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            jitter_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_voxel"
                and task.key.execution_stage == "spatial_jitter"
            )
            sidecar_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == jitter_task.endpoint.identifier
                and task.key.execution_stage == "preprocessing_sidecars"
            )
            final = self._final(context, jitter_task)
            cache_root = context.store.run_root / "hf_direct_cache"
            cache_root.mkdir(parents=True)
            candidate_xyz = cache_root / "candidate_xyz.npy"
            np.save(candidate_xyz, np.arange(60, dtype=np.float32).reshape(20, 3))
            sampling_rows = []
            for subject_id in final.subject_order:
                right = cache_root / f"{subject_id}_right.nii"
                left = cache_root / f"{subject_id}_left_to_right.nii"
                right.write_bytes(b"right")
                left.write_bytes(b"left")
                sampling_rows.append(
                    {
                        "subject_id": subject_id,
                        "right": [{"path": str(right)}],
                        "left_to_right": [{"path": str(left)}],
                    }
                )
            task_root = (
                context.store.run_root
                / "models"
                / sidecar_task.endpoint.identifier
                / "tasks"
                / sidecar_task.task_id
            )
            task_root.mkdir(parents=True, exist_ok=True)
            qc = task_root / "qc.json"
            sidecar_index = task_root / "sidecar_index.json"
            qc.write_text(json.dumps({"sampling_qc": sampling_rows}) + "\n", encoding="utf-8")
            sidecar_index.write_text(
                json.dumps({"cache_root": str(cache_root)}) + "\n",
                encoding="utf-8",
            )
            context.results[sidecar_task.task_id] = TaskExecutionRecord(
                sidecar_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    artifacts=(
                        TaskArtifact("qc", qc),
                        TaskArtifact("sidecar_index", sidecar_index),
                    ),
                ),
            )

            reference = _ConfiguredRuntime(context)._jitter_manifest(
                jitter_task,
                context,
                final,
                (final.exposure,),
            )
            payload = json.loads((context.store.run_root / reference.relative_path).read_text())
            candidate_xyz_sha = sha256_file(candidate_xyz)

        geometry = payload["geometry"]
        self.assertEqual(geometry["builder"], "direct_efield_resample_v1")
        self.assertEqual(geometry["final_candidate_xyz"]["sha256"], candidate_xyz_sha)
        self.assertEqual(
            [row["subject_id"] for row in geometry["hf_reference_sampling_qc"]],
            list(final.subject_order),
        )
        self.assertEqual(len(geometry["hf_reference_sampling_qc"][0]["right"][0]["sha256"]), 64)

    def test_hf_fiber_jitter_manifest_uses_configured_connectome_and_sidecar_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            jitter_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_fiber"
                and task.key.execution_stage == "spatial_jitter"
            )
            sidecar_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == jitter_task.endpoint.identifier
                and task.key.execution_stage == "sidecar_equivalence"
            )
            final = self._final(context, jitter_task)
            connectome = context.config.study.connectomes[jitter_task.endpoint.connectome].path
            connectome.parent.mkdir(parents=True, exist_ok=True)
            connectome.write_bytes(b"configured-connectome")
            cache_root = context.store.run_root / "hf_fiber_cache"
            flipped_root = cache_root / "flipped_left_to_right"
            flipped_root.mkdir(parents=True)
            side_fields = []
            for subject_id in final.subject_order:
                right = cache_root / f"{subject_id}_right.nii"
                left = cache_root / f"{subject_id}_left.nii"
                flipped = flipped_root / f"{subject_id}_hemi-L_src-01_to_R.nii"
                right.write_bytes(b"right")
                left.write_bytes(b"left")
                flipped.write_bytes(b"flipped")
                side_fields.extend(
                    [
                        {"subject_id": subject_id, "side": "R", "source_paths": [str(right)]},
                        {"subject_id": subject_id, "side": "L", "source_paths": [str(left)]},
                    ]
                )
            task_root = (
                context.store.run_root
                / "models"
                / sidecar_task.endpoint.identifier
                / "tasks"
                / sidecar_task.task_id
            )
            task_root.mkdir(parents=True, exist_ok=True)
            qc = task_root / "qc.json"
            sidecar_index = task_root / "sidecar_index.json"
            qc.write_text(
                json.dumps({"sampler_qc": {"side_fields": side_fields}}) + "\n",
                encoding="utf-8",
            )
            sidecar_index.write_text(
                json.dumps({"cache_root": str(cache_root)}) + "\n",
                encoding="utf-8",
            )
            context.results[sidecar_task.task_id] = TaskExecutionRecord(
                sidecar_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    artifacts=(
                        TaskArtifact("qc", qc),
                        TaskArtifact("sidecar_index", sidecar_index),
                    ),
                ),
            )

            reference = _ConfiguredRuntime(context)._jitter_manifest(
                jitter_task,
                context,
                final,
                (final.exposure,),
            )
            payload = json.loads((context.store.run_root / reference.relative_path).read_text())
            connectome_sha = sha256_file(connectome)

        geometry = payload["geometry"]
        self.assertEqual(geometry["builder"], "normative_fiber_efield_resample_v1")
        self.assertEqual(geometry["connectome_data_mat"]["sha256"], connectome_sha)
        self.assertEqual(
            [row["subject_id"] for row in geometry["hf_reference_sampling_qc"]],
            list(final.subject_order),
        )

    def test_ulf_direct_jitter_manifest_closes_finite_hf_overlap_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            ulf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_voxel"
                and task.key.execution_stage == "spatial_jitter"
            )
            ulf_branch_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "observed_branch_resolver"
                and task.key.branch == "no_delta_hf"
            )
            hf_resolver_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_voxel"
                and task.endpoint.scale_id == ulf_task.endpoint.scale_id
                and task.key.execution_stage == "observed_source_resolver"
            )
            hf_sidecar_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == hf_resolver_task.endpoint.identifier
                and task.key.execution_stage == "preprocessing_sidecars"
            )
            brainmask = Path(context.config.study.space["brainmask"])
            brainmask.parent.mkdir(parents=True, exist_ok=True)
            nib.save(
                nib.Nifti1Image(np.ones((2, 2, 10), dtype=np.uint8), np.eye(4)),
                str(brainmask),
            )
            matched_ids = np.arange(20, 40, dtype=np.int64)
            matched_hf = self._final(
                context,
                hf_resolver_task,
                feature_ids_values=matched_ids,
            )
            ulf_final = self._final(
                context,
                ulf_task,
                branch="no_delta_hf",
                feature_ids_values=matched_ids,
            )

            hf_cache = context.store.run_root / "matched_hf_cache"
            hf_cache.mkdir(parents=True)
            matched_xyz = np.column_stack(
                [np.ones(20), np.repeat(np.arange(2), 10), np.tile(np.arange(10), 2)]
            ).astype(np.float32)
            np.save(hf_cache / "candidate_xyz.npy", matched_xyz)
            hf_rows = []
            for subject_id in matched_hf.subject_order:
                right = hf_cache / f"{subject_id}_right.nii"
                left = hf_cache / f"{subject_id}_left.nii"
                right.write_bytes(b"right")
                left.write_bytes(b"left")
                hf_rows.append(
                    {
                        "subject_id": subject_id,
                        "right": [{"path": str(right)}],
                        "left_to_right": [{"path": str(left)}],
                    }
                )
            hf_task_root = (
                context.store.run_root
                / "models"
                / hf_sidecar_task.endpoint.identifier
                / "tasks"
                / hf_sidecar_task.task_id
            )
            hf_task_root.mkdir(parents=True, exist_ok=True)
            hf_qc = hf_task_root / "qc.json"
            hf_index = hf_task_root / "sidecar_index.json"
            hf_qc.write_text(json.dumps({"sampling_qc": hf_rows}) + "\n", encoding="utf-8")
            hf_index.write_text(
                json.dumps({"cache_root": str(hf_cache)}) + "\n",
                encoding="utf-8",
            )
            context.results[hf_sidecar_task.task_id] = TaskExecutionRecord(
                hf_sidecar_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    artifacts=(TaskArtifact("qc", hf_qc), TaskArtifact("sidecar_index", hf_index)),
                ),
            )
            context.results[hf_resolver_task.task_id] = TaskExecutionRecord(
                hf_resolver_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"final_model_record": matched_hf.as_dict()},
                ),
            )

            branch_root = context.store.run_root / "ulf_branch"
            branch_root.mkdir()
            ulf_candidate_xyz = branch_root / "candidate_xyz.npy"
            np.save(ulf_candidate_xyz, matched_xyz)
            hf_component_rows = []
            ulf_component_rows = []
            for subject_id in ulf_final.subject_order:
                hf_right = branch_root / f"{subject_id}_hf_right.nii"
                ulf_right = branch_root / f"{subject_id}_ulf_right.nii"
                hf_right.write_bytes(b"hf")
                ulf_right.write_bytes(b"ulf")
                hf_component_rows.append(
                    {
                        "subject_id": subject_id,
                        "right": [{"path": str(hf_right)}],
                        "left_to_right": [],
                    }
                )
                ulf_component_rows.append(
                    {
                        "subject_id": subject_id,
                        "right": [{"path": str(ulf_right)}],
                        "left_to_right": [],
                    }
                )
            source_manifest = branch_root / "source_scan_manifest.json"
            source_manifest.write_text(
                json.dumps(
                    {
                        "hf_component_qc": hf_component_rows,
                        "ulf_component_qc": ulf_component_rows,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            branch = ULFBranchRecord.create(
                resolver_task_id=ulf_branch_task.task_id,
                endpoint_model_id=ulf_task.endpoint.identifier,
                branch="no_delta_hf",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_nonpredictive",
                threshold_source="pre_specified",
                selected_tau=200,
                selected_coverage=5,
                adjacent_support=2,
                subject_order=ulf_final.subject_order,
                feature_axis=ulf_final.feature_axis,
                nuisance=ulf_final.nuisance,
                artifacts=(
                    self._artifact_ref(context, source_manifest, "source_scan_manifest"),
                    self._artifact_ref(context, ulf_candidate_xyz, "candidate_xyz", (20, 3)),
                    ulf_final.manifest,
                    ulf_final.exposure,
                    ulf_final.scores,
                ),
            )
            context.results[ulf_branch_task.task_id] = TaskExecutionRecord(
                ulf_branch_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"ulf_branch_record": branch.as_dict()},
                ),
            )

            reference = _ConfiguredRuntime(context)._jitter_manifest(
                ulf_task,
                context,
                ulf_final,
                (),
                matched_hf=matched_hf,
            )
            payload = json.loads((context.store.run_root / reference.relative_path).read_text())
            support_xyz = np.load(payload["geometry"]["hf_support_xyz"]["path"])
            mapped = np.load(
                payload["geometry"]["matched_hf_candidate_indices_in_support"]["path"]
            )
            np.save(
                matched_hf.feature_axis.ids_path,
                matched_ids.astype(np.int32),
            )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                _ConfiguredRuntime(context)._jitter_manifest(
                    ulf_task,
                    context,
                    ulf_final,
                    (),
                    matched_hf=matched_hf,
                )

        geometry = payload["geometry"]
        self.assertEqual(geometry["builder"], "direct_efield_resample_v1")
        self.assertEqual(support_xyz.shape, (20, 3))
        np.testing.assert_array_equal(mapped, np.arange(20, dtype=np.int64))
        self.assertEqual(
            [row["subject_id"] for row in geometry["ulf_component_sampling_qc"]],
            list(ulf_final.subject_order),
        )

    def test_ulf_fiber_jitter_manifest_combines_branch_components_and_matched_hf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, plan = self._fixture(Path(tmp))
            ulf_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "ulf_fiber"
                and task.key.execution_stage == "spatial_jitter"
            )
            ulf_branch_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == ulf_task.endpoint.identifier
                and task.key.execution_stage == "observed_branch_resolver"
                and task.key.branch == "no_delta_hf"
            )
            hf_resolver_task = next(
                task
                for task in plan.tasks
                if task.endpoint.model_family == "hf_fiber"
                and task.endpoint.scale_id == ulf_task.endpoint.scale_id
                and task.endpoint.connectome == ulf_task.endpoint.connectome
                and task.key.execution_stage == "observed_source_resolver"
            )
            hf_sidecar_task = next(
                task
                for task in plan.tasks
                if task.endpoint.identifier == hf_resolver_task.endpoint.identifier
                and task.key.execution_stage == "sidecar_equivalence"
            )
            connectome = context.config.study.connectomes[ulf_task.endpoint.connectome].path
            connectome.parent.mkdir(parents=True, exist_ok=True)
            connectome.write_bytes(b"configured-connectome")
            matched_hf = self._final(context, hf_resolver_task)
            ulf_final = self._final(context, ulf_task, branch="no_delta_hf")

            hf_cache = context.store.run_root / "matched_hf_fiber_cache"
            hf_flipped = hf_cache / "flipped_left_to_right"
            hf_flipped.mkdir(parents=True)
            hf_reference_fields = []
            for subject_id in matched_hf.subject_order:
                right = hf_cache / f"{subject_id}_right.nii"
                left = hf_cache / f"{subject_id}_left.nii"
                flipped = hf_flipped / f"{subject_id}_hemi-L_src-01_to_R.nii"
                right.write_bytes(b"right")
                left.write_bytes(b"left")
                flipped.write_bytes(b"flipped")
                hf_reference_fields.extend(
                    [
                        {"subject_id": subject_id, "side": "R", "source_paths": [str(right)]},
                        {"subject_id": subject_id, "side": "L", "source_paths": [str(left)]},
                    ]
                )
            hf_task_root = (
                context.store.run_root
                / "models"
                / hf_sidecar_task.endpoint.identifier
                / "tasks"
                / hf_sidecar_task.task_id
            )
            hf_task_root.mkdir(parents=True, exist_ok=True)
            hf_qc = hf_task_root / "qc.json"
            hf_index = hf_task_root / "sidecar_index.json"
            hf_qc.write_text(
                json.dumps({"sampler_qc": {"side_fields": hf_reference_fields}}) + "\n",
                encoding="utf-8",
            )
            hf_index.write_text(
                json.dumps({"cache_root": str(hf_cache)}) + "\n",
                encoding="utf-8",
            )
            context.results[hf_sidecar_task.task_id] = TaskExecutionRecord(
                hf_sidecar_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    artifacts=(TaskArtifact("qc", hf_qc), TaskArtifact("sidecar_index", hf_index)),
                ),
            )
            context.results[hf_resolver_task.task_id] = TaskExecutionRecord(
                hf_resolver_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"final_model_record": matched_hf.as_dict()},
                ),
            )

            preprocess = context.store.run_root / "ulf_fiber_preprocess"
            hf_component_flipped = preprocess / "hf_component" / "flipped_left_to_right"
            ulf_component_flipped = preprocess / "ulf_component" / "flipped_left_to_right"
            hf_component_flipped.mkdir(parents=True)
            ulf_component_flipped.mkdir(parents=True)
            component_qc = {"HF": {"side_paths": []}, "ULF": {"side_paths": []}}
            for subject_id in ulf_final.subject_order:
                for label, flipped_root in (
                    ("HF", hf_component_flipped),
                    ("ULF", ulf_component_flipped),
                ):
                    right = preprocess / f"{subject_id}_{label}_right.nii"
                    left = preprocess / f"{subject_id}_{label}_left.nii"
                    flipped = flipped_root / f"{subject_id}_hemi-L_src-01_to_R.nii"
                    right.write_bytes(label.encode("ascii"))
                    left.write_bytes(label.encode("ascii"))
                    flipped.write_bytes(label.encode("ascii"))
                    component_qc[label]["side_paths"].extend(
                        [
                            {"subject_id": subject_id, "side": "R", "source_paths": [str(right)]},
                            {"subject_id": subject_id, "side": "L", "source_paths": [str(left)]},
                        ]
                    )
            hf_component = preprocess / "X_HF_component.npy"
            ulf_component = preprocess / "X_ULF_component.npy"
            np.save(hf_component, np.ones((12, 20), dtype=np.float32))
            np.save(ulf_component, np.ones((12, 20), dtype=np.float32))
            selected_manifest = preprocess / "selected_manifest.json"
            selected_manifest.write_text(
                json.dumps({"component_sampler_qc": component_qc}) + "\n",
                encoding="utf-8",
            )
            branch = ULFBranchRecord.create(
                resolver_task_id=ulf_branch_task.task_id,
                endpoint_model_id=ulf_task.endpoint.identifier,
                branch="no_delta_hf",
                input_status="valid",
                source_status="pre_specified_accepted",
                prediction_status="error_nonpredictive",
                threshold_source="pre_specified",
                selected_tau=800,
                selected_coverage=5,
                adjacent_support=2,
                subject_order=ulf_final.subject_order,
                feature_axis=ulf_final.feature_axis,
                nuisance=ulf_final.nuisance,
                artifacts=(
                    self._artifact_ref(context, selected_manifest, "selected_manifest"),
                    self._artifact_ref(
                        context,
                        hf_component,
                        "hf_component_exposure",
                        (12, 20),
                    ),
                    self._artifact_ref(
                        context,
                        ulf_component,
                        "ulf_component_exposure",
                        (12, 20),
                    ),
                    ulf_final.exposure,
                    ulf_final.scores,
                ),
            )
            context.results[ulf_branch_task.task_id] = TaskExecutionRecord(
                ulf_branch_task,
                TaskResult(
                    TaskStatus.COMPLETED,
                    facts={"ulf_branch_record": branch.as_dict()},
                ),
            )

            reference = _ConfiguredRuntime(context)._jitter_manifest(
                ulf_task,
                context,
                ulf_final,
                (),
                matched_hf=matched_hf,
            )
            payload = json.loads((context.store.run_root / reference.relative_path).read_text())

        geometry = payload["geometry"]
        self.assertEqual(geometry["builder"], "normative_fiber_efield_resample_v1")
        self.assertEqual(
            [row["subject_id"] for row in geometry["hf_component_sampling_qc"]],
            list(ulf_final.subject_order),
        )
        self.assertEqual(
            [row["subject_id"] for row in geometry["hf_reference_sampling_qc"]],
            list(ulf_final.subject_order),
        )


if __name__ == "__main__":
    unittest.main()
