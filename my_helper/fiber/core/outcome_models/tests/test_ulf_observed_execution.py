"""Integration tests for ULF lock, branch, and final-model execution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskArtifact, TaskExecutionRecord, TaskResult, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.records import ArtifactRef, DeltaHFBundle, FeatureAxisRef, HFSourceRecord
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.observed import ObservedServiceOutput
from outcome_models.services.record_io import _logical_array_sha256
from outcome_models.services.ulf_observed import DeltaBuilderOutput, ULFObservedService
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class ULFObservedExecutionTests(unittest.TestCase):
    def _fixture(self, root: Path, model: str = "ulf-voxel"):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = [model]

        workflow = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        store = ConfiguredRunStore.create(
            output_root=root / "outputs",
            study_id=config.study.study_id,
            provenance={"configuration_hash": config.configuration_hash, "input_hashes": {}, "code_provenance": {}},
        )
        store.initialize(resolved_workflow={}, endpoint_catalog=[], execution_plan=plan.as_dict())
        context = RunContext(store=store, catalog=tuple(catalog), config=config)
        ulf_family = "ulf_fiber" if model == "ulf-fiber" else "ulf_voxel"
        hf_family = "hf_fiber" if model == "ulf-fiber" else "hf_voxel"
        tasks = {
            task.key.execution_stage + ":" + task.key.branch: task
            for task in plan.tasks
            if task.endpoint.model_family == ulf_family
        }
        hf_task = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == hf_family
            and task.key.execution_stage == "observed_source_resolver"
        )
        endpoint = context.catalog_record(tasks["input_hf_lock:none"].endpoint.identifier)
        source_artifact = ArtifactRef(
            hf_task.task_id,
            "selected_manifest",
            "models/hf/selected.json",
            "a" * 64,
        )
        hf_axis_path = store.run_root / "hf_source_axis.npy"
        hf_axis_values = np.arange(4, dtype=np.int64)
        np.save(hf_axis_path, hf_axis_values)
        hf_source = HFSourceRecord.create(
            resolver_task_id=hf_task.task_id,
            endpoint_model_id=hf_task.endpoint.identifier,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            subject_order=endpoint.subject_ids,
            feature_axis=FeatureAxisRef(
                hf_axis_path,
                4,
                (
                    _logical_array_sha256(hf_axis_values)
                    if model == "ulf-fiber"
                    else sha256_file(hf_axis_path)
                ),
                "data.mat:idx" if model == "ulf-fiber" else "candidate_flat_indices",
            ),
            artifacts=(source_artifact,),
        )
        context.results[hf_task.task_id] = TaskExecutionRecord(
            hf_task,
            TaskResult(
                TaskStatus.COMPLETED,
                facts={
                    "source_accepted": True,
                    "hf_source_record": hf_source.as_dict(),
                },
            ),
        )
        return context, tasks, endpoint

    @staticmethod
    def _record(context, task, result):
        context.results[task.task_id] = TaskExecutionRecord(task, result)

    def test_predictive_hf_realizes_adjusted_primary_from_two_branch_records(self) -> None:
        def delta_builder(endpoint, source, task, context):
            root = context.store.run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            root.mkdir(parents=True, exist_ok=True)
            full = root / "delta_full.npy"
            folds = root / "delta_folds.npy"
            support = root / "support.csv"
            np.save(full, np.linspace(0.0, 1.0, endpoint.n_subjects))
            np.save(folds, np.tile(np.linspace(0.0, 1.0, endpoint.n_subjects), (endpoint.n_subjects, 1)))
            support.write_text(
                "subject_id,out_support_fraction\n"
                + "".join(f"{subject},0.1\n" for subject in endpoint.subject_ids),
                encoding="utf-8",
            )

            def ref(kind, path, shape):
                return ArtifactRef(
                    task.task_id,
                    kind,
                    path.relative_to(context.store.run_root).as_posix(),
                    sha256_file(path),
                    shape,
                )

            bundle = DeltaHFBundle(
                "valid",
                "adequate",
                source.selected_tau,
                source.selected_coverage,
                ref("delta_hf_full_scores", full, (endpoint.n_subjects,)),
                ref("delta_hf_fold_scores", folds, (endpoint.n_subjects, endpoint.n_subjects)),
                ref("delta_hf_support_rows", support, (endpoint.n_subjects,)),
            )
            return DeltaBuilderOutput(
                bundle,
                (
                    TaskArtifact("delta_hf_full_scores", full),
                    TaskArtifact("delta_hf_fold_scores", folds),
                    TaskArtifact("delta_hf_support_rows", support),
                ),
            )

        def branch_runner(request):
            root = request.output_root
            root.mkdir(parents=True, exist_ok=True)
            axis = request.model_root / "cache" / request.branch / "fiber_ids.npy"
            axis.parent.mkdir(parents=True, exist_ok=True)
            axis_values = np.arange(4, dtype=np.int64)
            np.save(axis, axis_values)
            exposure = root / "exposure.npy"
            np.save(exposure, np.full((request.endpoint.n_subjects, 4), 1000.0, dtype=np.float32))
            paths = {}
            for kind, name in (
                ("source_status", "source.json"),
                ("selected_source", "selected.json"),
                ("selected_manifest", "manifest.json"),
                ("selected_scores", "scores.csv"),
                ("coefficient_nifti", "coef.nii.gz"),
            ):
                path = root / name
                path.write_text("{}\n", encoding="utf-8")
                paths[kind] = path
            paths["exposure_matrix"] = exposure
            valid_mask = (
                np.array([True, False, True, True])
                if request.branch == "delta_hf_adjusted"
                else np.array([False, True, True, True])
            )
            full_weights = root / "selected_full_weights.npy"
            valid_ids = root / "selected_valid_fiber_ids.npy"
            np.save(full_weights, np.where(valid_mask, 1.0, np.nan).astype(np.float32))
            np.save(valid_ids, axis_values[valid_mask])
            paths["selected_full_weights"] = full_weights
            paths["selected_valid_fiber_ids"] = valid_ids
            return ObservedServiceOutput(
                "pre_specified_accepted",
                "error_predictive" if request.branch == "delta_hf_adjusted" else "error_nonpredictive",
                "pre_specified",
                200,
                5,
                2,
                request.endpoint.subject_ids,
                FeatureAxisRef(axis, 4, _logical_array_sha256(axis_values), "data.mat:idx"),
                tuple(TaskArtifact(kind, path) for kind, path in paths.items()),
            )

        with tempfile.TemporaryDirectory() as tmp:
            context, tasks, _ = self._fixture(Path(tmp), "ulf-fiber")
            service = ULFObservedService(fiber_runner=branch_runner, delta_builder=delta_builder)
            for key in (
                "input_hf_lock:none",
                "preprocessing_sidecars:none",
                "observed_branch_resolver:no_delta_hf",
                "observed_branch_resolver:delta_hf_adjusted",
                "final_model_realization:resolver",
            ):
                task = tasks[key]
                result = service.execute(task, context)
                self._record(context, task, result)

            final = context.results[tasks["final_model_realization:resolver"].task_id].result
            final_record = final.facts["final_model_record"]
            valid_axis_path = Path(final_record["valid_feature_axis"]["ids_path"])
            realized_valid_ids = np.load(valid_axis_path)

        self.assertEqual(final.status, TaskStatus.COMPLETED)
        self.assertTrue(final.facts["final_model_realized"])
        self.assertEqual(final.facts["intended_primary_branch"], "delta_hf_adjusted")
        self.assertEqual(final.facts["final_branch"], "delta_hf_adjusted")
        self.assertEqual(final.facts["final_role"], "primary")
        self.assertEqual(
            final.facts["final_model_record"]["nuisance"]["columns"],
            ["Y_HF_ref", "DeltaHFScore"],
        )
        np.testing.assert_array_equal(realized_valid_ids, np.array([0, 2, 3]))
        self.assertEqual(
            final_record["full_weights"]["task_id"],
            tasks["observed_branch_resolver:delta_hf_adjusted"].task_id,
        )


if __name__ == "__main__":
    unittest.main()
