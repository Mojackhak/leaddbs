"""Tests for persisted immutable source and final-model records."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.executor import RunContext, TaskArtifact, TaskStatus
from outcome_models.planner import compile_execution_plan
from outcome_models.records import FeatureAxisRef, FinalArtifactRecord, HFSourceRecord, RecordError
from outcome_models.run_store import ConfiguredRunStore, sha256_file
from outcome_models.services.observed import ObservedServiceOutput
from outcome_models.services.record_io import persist_hf_resolver_output
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


class RecordIOTests(unittest.TestCase):
    @staticmethod
    def _array_sha256(values: np.ndarray) -> str:
        array = np.ascontiguousarray(values)
        digest = hashlib.sha256()
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(array.tobytes(order="C"))
        return digest.hexdigest()

    def _fixture(self, root: Path, model_family: str = "hf_voxel"):
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = [
                "hf-fiber" if model_family == "hf_fiber" else "hf-voxel"
            ]

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
        task = next(
            item
            for item in plan.tasks
            if item.endpoint.model_family == model_family
            and item.key.execution_stage == "observed_source_resolver"
        )
        endpoint = context.catalog_record(task.endpoint.identifier)
        return context, task, endpoint

    def test_accepted_source_writes_source_and_unique_final_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, endpoint = self._fixture(Path(tmp))
            task_root = context.store.run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            task_root.mkdir(parents=True, exist_ok=True)
            axis_path = task_root / "candidate_flat_indices.npy"
            exposure = task_root / "exposure.npy"
            np.save(axis_path, np.arange(3, dtype=np.int64))
            np.save(exposure, np.ones((12, 3), dtype=np.float32))
            paths = {}
            for kind, name in (
                ("source_status", "source_status.json"),
                ("selected_source", "selected_source.json"),
                ("selected_manifest", "selected_manifest.json"),
                ("selected_scores", "selected_scores.csv"),
            ):
                path = task_root / name
                path.write_text("{}\n", encoding="utf-8")
                paths[kind] = path
            paths["exposure_matrix"] = exposure
            output = ObservedServiceOutput(
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=200,
                selected_coverage=5,
                adjacent_support=3,
                subject_order=endpoint.subject_ids,
                feature_axis=FeatureAxisRef(
                    axis_path,
                    3,
                    sha256_file(axis_path),
                    "candidate_flat_indices",
                ),
                artifacts=tuple(TaskArtifact(kind, path) for kind, path in paths.items()),
            )
            result = persist_hf_resolver_output(output, endpoint, task, context)
            by_kind = {artifact.kind: artifact.path for artifact in result.artifacts}
            source = HFSourceRecord.from_dict(
                __import__("json").loads(by_kind["hf_source_record"].read_text(encoding="utf-8"))
            )
            final = FinalArtifactRecord.from_dict(
                __import__("json").loads(by_kind["final_model_record"].read_text(encoding="utf-8"))
            )

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.facts["source_accepted"])
        self.assertTrue(result.facts["final_model_realized"])
        self.assertEqual(source.record_hash, result.facts["hf_source_record_hash"])
        self.assertEqual(final.final_model_id, result.facts["final_model_id"])
        self.assertEqual(final.final_branch, "hf_source")
        self.assertEqual(final.selected_tau, 200)
        self.assertEqual(final.nuisance.columns, ("Y_base",))

    def test_absent_source_writes_source_record_without_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, endpoint = self._fixture(Path(tmp))
            task_root = context.store.run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            task_root.mkdir(parents=True, exist_ok=True)
            source_status = task_root / "source_status.json"
            selected_source = task_root / "selected_source.json"
            source_status.write_text("{}\n", encoding="utf-8")
            selected_source.write_text("{}\n", encoding="utf-8")
            output = ObservedServiceOutput(
                source_status="absent_no_stable_grid",
                prediction_status="not_applicable",
                threshold_source="none",
                selected_tau=None,
                selected_coverage=None,
                adjacent_support=0,
                subject_order=endpoint.subject_ids,
                feature_axis=None,
                artifacts=(
                    TaskArtifact("source_status", source_status),
                    TaskArtifact("selected_source", selected_source),
                ),
            )
            result = persist_hf_resolver_output(output, endpoint, task, context)

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertFalse(result.facts["source_accepted"])
        self.assertFalse(result.facts["final_model_realized"])
        self.assertNotIn("final_model_id", result.facts)
        self.assertEqual(
            {artifact.kind for artifact in result.artifacts},
            {"source_status", "selected_source", "hf_source_record"},
        )

    def test_hf_fiber_final_binds_and_verifies_realized_valid_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context, task, endpoint = self._fixture(Path(tmp), "hf_fiber")
            task_root = context.store.run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            task_root.mkdir(parents=True, exist_ok=True)
            parent_ids = np.array([10, 11, 12, 13, 14], dtype=np.int64)
            axis_path = task_root / "fiber_ids.npy"
            exposure_path = task_root / "exposure.npy"
            weights_path = task_root / "selected_full_weights.npy"
            valid_ids_path = task_root / "selected_valid_fiber_ids.npy"
            np.save(axis_path, parent_ids)
            exposure = np.full((len(endpoint.subject_ids), parent_ids.size), 0.5, dtype=np.float32)
            exposure[:, [0, 1, 2, 3]] = 2.0
            np.save(exposure_path, exposure)
            weights = np.array([1.0, -1.0, np.nan, 0.5, -0.25], dtype=np.float32)
            np.save(weights_path, weights)
            np.save(valid_ids_path, np.array([10, 11, 13], dtype=np.int64))
            paths = {
                "exposure_matrix": exposure_path,
                "selected_full_weights": weights_path,
                "selected_valid_fiber_ids": valid_ids_path,
            }
            for kind in ("source_status", "selected_source", "selected_manifest", "selected_scores"):
                path = task_root / f"{kind}.json"
                path.write_text("{}\n", encoding="utf-8")
                paths[kind] = path
            output = ObservedServiceOutput(
                source_status="pre_specified_accepted",
                prediction_status="error_predictive",
                threshold_source="pre_specified",
                selected_tau=1.0,
                selected_coverage=5,
                adjacent_support=3,
                subject_order=endpoint.subject_ids,
                feature_axis=FeatureAxisRef(
                    axis_path,
                    parent_ids.size,
                    self._array_sha256(parent_ids),
                    "data.mat:idx",
                ),
                artifacts=tuple(TaskArtifact(kind, path) for kind, path in paths.items()),
            )
            result = persist_hf_resolver_output(output, endpoint, task, context)
            final = FinalArtifactRecord.from_dict(dict(result.facts["final_model_record"]))

            self.assertEqual(final.full_weights.kind, "selected_full_weights")
            self.assertEqual(final.valid_feature_axis.count, 3)
            self.assertEqual(final.valid_feature_axis.identity_source, "data.mat:idx")
            self.assertEqual(final.valid_feature_axis.sha256, self._array_sha256(np.array([10, 11, 13])))

            np.save(valid_ids_path, np.array([11, 10, 13], dtype=np.int64))
            with self.assertRaisesRegex(RecordError, "valid fiber"):
                persist_hf_resolver_output(output, endpoint, task, context)


if __name__ == "__main__":
    unittest.main()
