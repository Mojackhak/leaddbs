"""Portable checkpoint validation and compact extension-plan tests."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from dual_frequency.application.sensitivity import (
    BASE_SCHEMA,
    CHECKPOINT_SCHEMA,
    SEED_SCHEMA,
    SensitivityCheckpointError,
    compile_sensitivity_extension_plan,
    load_sensitivity_checkpoint,
)
from dual_frequency.cache.identity import sha256_file
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    SourceRecord,
    TaskKey,
)
from dual_frequency.workflow import (
    ExecutionPlan,
    GateRequirement,
    ServiceResult,
    TaskOutcome,
    TaskSpec,
)


CONFIGURATION_HASH = "a" * 64
SCIENTIFIC_HASH = "b" * 64


def _artifact(path: Path, *, portable_name: str, sha256: str | None = None) -> ArtifactRef:
    axis = AxisRef("checkpoint-axis", 3, "c" * 64)
    return ArtifactRef(
        kind="checkpoint_array",
        schema_version="dual_frequency_array_v1",
        uri=f"base-run:///work/{portable_name}",
        sha256=sha256 if sha256 is not None else sha256_file(path),
        dtype="float64",
        shape=(3,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="synthetic",
        producer_id="checkpoint_test",
        producer_version="1",
    )


def _artifact_payload(artifact: ArtifactRef) -> dict[str, object]:
    return json.loads(json.dumps(asdict(artifact)))


def _seed_outcome(task_id: str, artifact: ArtifactRef) -> TaskOutcome:
    endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
    record = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="absent_no_stable_grid",
        prediction_status="not_applicable",
        threshold_source="none",
        selected_tau=None,
        selected_coverage=None,
        adjacent_support=0,
        feature_axis=None,
        artifacts=(artifact,),
    )
    return TaskOutcome(
        task_id=task_id,
        endpoint_id=endpoint.identifier,
        service_id="checkpoint_parent",
        status="completed",
        reason="none",
        result=ServiceResult.from_record(record),
    )


def _write_checkpoint(
    root: Path,
    *,
    final_artifacts: tuple[ArtifactRef, ...],
    seed_outcomes: tuple[TaskOutcome, ...],
) -> tuple[Path, Path, Path]:
    run_root = root / "run"
    cache_root = root / "cache"
    output_root = root / "output"
    base_root = run_root / "sensitivity_bases"
    endpoint_id = "endpoint-checkpoint"
    base_path = base_root / endpoint_id / "sensitivity_base.json"
    seed_path = base_root / "seed_task_states.json"
    for path in (run_root / "work", cache_root, output_root, base_path.parent):
        path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "dual_frequency_run_v1",
        "run_id": "parent-run",
        "study_id": "study",
        "final_status": "completed",
        "scientific_configuration_hash": SCIENTIFIC_HASH,
    }
    (run_root / "run_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    seed = {
        "schema_version": SEED_SCHEMA,
        "task_states": [
            {"task_id": outcome.task_id, **outcome.as_dict()}
            for outcome in seed_outcomes
        ],
    }
    seed_path.write_text(json.dumps(seed, sort_keys=True) + "\n", encoding="utf-8")
    base = {
        "schema_version": BASE_SCHEMA,
        "endpoint_id": endpoint_id,
        "shared_exposure_entries": [],
        "final_artifacts": [
            _artifact_payload(artifact) for artifact in final_artifacts
        ],
    }
    base_path.write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
    index = {
        "schema_version": CHECKPOINT_SCHEMA,
        "study_id": "study",
        "seed_task_states": {
            "relative_path": seed_path.relative_to(base_root).as_posix(),
            "sha256": sha256_file(seed_path),
        },
        "bases": [
            {
                "endpoint_id": endpoint_id,
                "relative_path": base_path.relative_to(base_root).as_posix(),
                "sha256": sha256_file(base_path),
            }
        ],
    }
    (base_root / "index.json").write_text(
        json.dumps(index, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_root, cache_root, output_root


def _task(
    endpoint: EndpointKey,
    stage: str,
    phase: str,
    dependencies: tuple[str, ...] = (),
    gates: tuple[GateRequirement, ...] = (),
) -> TaskSpec:
    return TaskSpec(
        key=TaskKey(endpoint.identifier, stage, parameter_identity=SCIENTIFIC_HASH),
        endpoint_id=endpoint.identifier,
        model_family=endpoint.model_family,
        connectome_role="none",
        stage=stage,
        round_id="checkpoint-test",
        phase=phase,
        service_id=f"service_{stage}",
        dependencies=dependencies,
        gates=gates,
        output_record_type="SourceRecord",
    )


class SensitivityCheckpointTest(unittest.TestCase):
    def test_loader_hashes_final_artifact_once_and_ignores_unselected_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            work = root / "run" / "work"
            work.mkdir(parents=True)
            final_path = work / "final.npy"
            unrelated_path = work / "unrelated.npy"
            np.save(final_path, np.arange(3, dtype=np.float64))
            np.save(unrelated_path, np.arange(3, dtype=np.float64))
            final_artifact = _artifact(final_path, portable_name="final.npy")
            unrelated_artifact = _artifact(
                unrelated_path,
                portable_name="unrelated.npy",
                sha256="f" * 64,
            )
            run_root, cache_root, output_root = _write_checkpoint(
                root,
                final_artifacts=(final_artifact, final_artifact),
                seed_outcomes=(
                    _seed_outcome("task-required", final_artifact),
                    _seed_outcome("task-unrelated", unrelated_artifact),
                ),
            )
            calls: list[Path] = []

            def counted(path: Path) -> str:
                calls.append(Path(path).resolve())
                return sha256_file(path)

            with patch(
                "dual_frequency.application.sensitivity.sha256_file",
                side_effect=counted,
            ):
                checkpoint = load_sensitivity_checkpoint(
                    run_root,
                    cache_root=cache_root,
                    output_root=output_root,
                )
                outcomes = checkpoint.seed_outcomes_for(("task-required",))

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].task_id, "task-required")
        self.assertEqual(calls.count(final_path.resolve()), 1)
        self.assertNotIn(unrelated_path.resolve(), calls)

    def test_loader_rejects_corrupted_final_artifact_before_rehydration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            work = root / "run" / "work"
            work.mkdir(parents=True)
            final_path = work / "final.npy"
            np.save(final_path, np.arange(3, dtype=np.float64))
            artifact = _artifact(final_path, portable_name="final.npy")
            run_root, cache_root, output_root = _write_checkpoint(
                root,
                final_artifacts=(artifact,),
                seed_outcomes=(_seed_outcome("task-required", artifact),),
            )
            final_path.write_bytes(final_path.read_bytes() + b"corruption")
            with self.assertRaisesRegex(
                SensitivityCheckpointError,
                "failed SHA-256",
            ):
                load_sensitivity_checkpoint(
                    run_root,
                    cache_root=cache_root,
                    output_root=output_root,
                )

    def test_extension_plan_stops_at_completed_direct_parent(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        ancestor = _task(endpoint, "input_readiness", "observed")
        parent = _task(
            endpoint,
            "final_realization",
            "observed",
            dependencies=(ancestor.task_id,),
        )
        formal = _task(
            endpoint,
            "formal_permutation",
            "formal",
            dependencies=(parent.task_id,),
        )
        target = _task(
            endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(parent.task_id, formal.task_id),
            gates=(GateRequirement("formal_complete", "not_run_formal_incomplete"),),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(ancestor, parent, formal, target),
        )
        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(endpoint.identifier,),
            analyses=("jitter",),
            seed_task_ids=(parent.task_id,),
        )

        self.assertEqual(
            tuple(task.task_id for task in extension.tasks),
            (parent.task_id, target.task_id),
        )
        self.assertTrue(extension.tasks[0].checkpoint_only)
        self.assertEqual(extension.tasks[0].dependencies, ())
        self.assertEqual(extension.tasks[0].gates, ())
        self.assertEqual(extension.tasks[1].dependencies, (parent.task_id,))
        self.assertEqual(extension.tasks[1].gates, ())

        with self.assertRaisesRegex(
            SensitivityCheckpointError,
            "lacks completed direct parent outcomes",
        ):
            compile_sensitivity_extension_plan(
                full_plan,
                endpoint_ids=(endpoint.identifier,),
                analyses=("jitter",),
                seed_task_ids=(),
            )


if __name__ == "__main__":
    unittest.main()
