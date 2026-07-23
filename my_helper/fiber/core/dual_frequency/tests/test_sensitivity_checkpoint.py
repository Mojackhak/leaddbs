"""Portable checkpoint validation and compact extension-plan tests."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from dual_frequency.application.sensitivity import (
    BASE_SCHEMA,
    CHECKPOINT_SCHEMA,
    SEED_SCHEMA,
    SensitivityCheckpointError,
    _physical_mapper,
    _portable_mapper,
    _remap_value,
    _scientific_array_payload,
    compile_sensitivity_extension_plan,
    load_sensitivity_checkpoint,
)
from dual_frequency.cache import RunScopedArtifactPublisher
from dual_frequency.cache.identity import sha256_file
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    IndexedArrayView,
    PreparedExposureRecord,
    SourceRecord,
    TaskKey,
)
from dual_frequency.runtime.record_codec import record_artifacts
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
    def test_indexed_view_base_payload_preserves_parent_and_selectors(self) -> None:
        rows = AxisRef("rows", 2, "1" * 64)
        parent_columns = AxisRef("parent-columns", 3, "2" * 64)
        selected_columns = AxisRef("selected-columns", 2, "3" * 64)

        def artifact(
            name: str,
            *,
            dtype: str,
            axes: tuple[AxisRef, ...],
            units: str | None,
            space: str | None,
            digest: str,
        ) -> ArtifactRef:
            return ArtifactRef(
                kind=name,
                schema_version="dual_frequency_array_v1",
                uri=f"cache:///{name}.npy",
                sha256=digest * 64,
                dtype=dtype,
                shape=tuple(axis.count for axis in axes),
                axis_refs=axes,
                axis_hashes=tuple(axis.sha256 for axis in axes),
                units=units,
                space=space,
                producer_id="checkpoint_test",
                producer_version="1",
            )

        parent = artifact(
            "shared_physical_exposure",
            dtype="float32",
            axes=(rows, parent_columns),
            units="V/m",
            space="synthetic",
            digest="4",
        )
        positions = artifact(
            "indexed_array_column_positions",
            dtype="int64",
            axes=(selected_columns,),
            units="index",
            space=None,
            digest="5",
        )
        view = IndexedArrayView(
            parent=parent,
            row_positions=None,
            column_positions=positions,
            axis_refs=(rows, selected_columns),
        )
        payload = _scientific_array_payload(view, lambda value: value)
        self.assertEqual(payload["kind"], "indexed_array_view")
        self.assertEqual(payload["identifier"], view.identifier)
        self.assertEqual(payload["parent"]["sha256"], parent.sha256)
        self.assertEqual(
            payload["column_positions"]["sha256"],
            positions.sha256,
        )
        self.assertEqual(payload["shape"], [2, 2])

    def test_portable_addon_preparation_replays_all_indexed_views_from_copy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "run"
            cache_root = root / "cache"
            output_root = root / "output"
            for path in (run_root, cache_root, output_root):
                path.mkdir(parents=True)
            publisher = RunScopedArtifactPublisher(
                cache_root / "prepared",
                "portable-addon",
                "1",
            )
            subjects = AxisRef("subjects", 2, "1" * 64)
            parent_features = AxisRef("parent-features", 3, "2" * 64)
            features = AxisRef("selected-features", 2, "3" * 64)
            selector = publisher.array(
                "column_positions.npy",
                np.asarray((2, 0), dtype=np.int64),
                kind="indexed_array_column_positions",
                axes=(features,),
                units="index",
                space=None,
            )

            def view(name: str, offset: float) -> IndexedArrayView:
                parent = publisher.array(
                    f"{name}.npy",
                    np.arange(6, dtype=np.float32).reshape(2, 3) + offset,
                    kind="shared_physical_exposure",
                    axes=(subjects, parent_features),
                    units="V/m",
                    space="synthetic",
                )
                return IndexedArrayView(
                    parent=parent,
                    row_positions=None,
                    column_positions=selector,
                    axis_refs=(subjects, features),
                )

            exposure = view("exposure", 0.0)
            reference_condition = view("reference_condition", 10.0)
            addon_reference = view("addon_reference", 20.0)
            total = view("total", 30.0)
            feature_ids = publisher.array(
                "feature_ids.npy",
                np.asarray((103, 101), dtype=np.int64),
                kind="canonical_feature_ids",
                axes=(features,),
                units=None,
                space="synthetic",
            )
            overlap = publisher.array(
                "overlap.npy",
                np.asarray(((True, False), (False, True)), dtype=bool),
                kind="reference_overlap_mask",
                axes=(subjects, features),
                units="binary",
                space="synthetic",
            )
            readiness = publisher.document(
                "readiness.json",
                {"schema_version": "portable_addon_readiness_v1"},
                kind="addon_auxiliary_readiness",
            )
            record = PreparedExposureRecord(
                endpoint=EndpointKey(
                    "study",
                    "scale",
                    "addon",
                    "addon_voxel",
                ),
                subject_axis=subjects,
                feature_axis=features,
                exposure=exposure,
                feature_ids=feature_ids,
                delta_reference_input_status="ready",
                delta_reference_reason_code="ready",
                auxiliary_readiness=readiness,
                reference_condition_exposure=reference_condition,
                addon_reference_component_exposure=addon_reference,
                reference_overlap_mask=overlap,
                total_exposure=total,
            )
            portable = _remap_value(
                record,
                _portable_mapper(run_root, cache_root, output_root),
            )
            self.assertIsInstance(portable, PreparedExposureRecord)
            encoded = ServiceResult.from_record(portable)
            self.assertEqual(encoded.decode_record(), portable)
            encoded_text = encoded.payload_json + json.dumps(
                [artifact.uri for artifact in encoded.artifacts],
                sort_keys=True,
            )
            self.assertNotIn(str(root.resolve()), encoded_text)
            self.assertNotIn(".runs", encoded_text)
            self.assertTrue(
                all(
                    artifact.uri.startswith("cache:///")
                    for artifact in record_artifacts(portable)
                )
            )

            copied_cache = root / "copied-cache"
            shutil.copytree(cache_root, copied_cache)
            physical_mapper = _physical_mapper(
                root / "copied-run",
                copied_cache,
                root / "copied-output",
            )
            restored = _remap_value(portable, physical_mapper)
            self.assertIsInstance(restored, PreparedExposureRecord)
            for artifact in record_artifacts(portable):
                resolved = physical_mapper.verify(artifact)
                self.assertTrue(
                    Path(resolved.uri.removeprefix("file://")).is_file()
                )
            self.assertEqual(
                tuple(artifact.sha256 for artifact in record_artifacts(restored)),
                tuple(artifact.sha256 for artifact in record_artifacts(record)),
            )

    def test_oss_extension_inserts_one_group_gate_before_observed_workspace(self) -> None:
        endpoints = tuple(
            EndpointKey(
                "study",
                f"scale-{index}",
                "reference",
                "reference_fiber",
                "formal-connectome",
            )
            for index in range(2)
        )
        tasks: list[TaskSpec] = []
        seed_ids: list[str] = []
        for endpoint in endpoints:
            readiness = _task(endpoint, "input_readiness", "observed")
            prepared = _task(
                endpoint,
                "prepare_exposure",
                "observed",
                dependencies=(readiness.task_id,),
            )
            final = _task(
                endpoint,
                "final_realization",
                "observed",
                dependencies=(readiness.task_id,),
            )
            observed = TaskSpec(
                key=TaskKey(
                    endpoint.identifier,
                    "ppam_observed_workspace",
                    parameter_identity=SCIENTIFIC_HASH,
                ),
                endpoint_id=endpoint.identifier,
                model_family=endpoint.model_family,
                connectome_role="formal",
                stage="ppam_observed_workspace",
                round_id="round_oss",
                phase="sensitivity",
                service_id="prepare_ppam_observed_workspace",
                dependencies=(readiness.task_id, prepared.task_id, final.task_id),
                gates=(),
                output_record_type="PPAMObservedWorkspaceRecord",
                expensive_producer=True,
                cache_first_expensive=True,
            )
            schedule = TaskSpec(
                key=TaskKey(
                    endpoint.identifier,
                    "ppam_permutation_schedule",
                    parameter_identity=SCIENTIFIC_HASH,
                ),
                endpoint_id=endpoint.identifier,
                model_family=endpoint.model_family,
                connectome_role="formal",
                stage="ppam_permutation_schedule",
                round_id="round_oss",
                phase="sensitivity",
                service_id="prepare_ppam_permutation_schedule",
                dependencies=(observed.task_id,),
                gates=(),
                output_record_type="ResamplingScheduleRecord",
            )
            block = TaskSpec(
                key=TaskKey(
                    endpoint.identifier,
                    "ppam_permutation_block_0000",
                    parameter_identity=SCIENTIFIC_HASH,
                ),
                endpoint_id=endpoint.identifier,
                model_family=endpoint.model_family,
                connectome_role="formal",
                stage="ppam_permutation_block_0000",
                round_id="round_oss",
                phase="sensitivity",
                service_id="run_ppam_permutation_block",
                dependencies=(observed.task_id, schedule.task_id),
                gates=(),
                output_record_type="PPAMPermutationBlockRecord",
            )
            aggregate = TaskSpec(
                key=TaskKey(
                    endpoint.identifier,
                    "activation_sensitivity",
                    parameter_identity=SCIENTIFIC_HASH,
                ),
                endpoint_id=endpoint.identifier,
                model_family=endpoint.model_family,
                connectome_role="formal",
                stage="activation_sensitivity",
                round_id="round_oss",
                phase="sensitivity",
                service_id="aggregate_ppam_activation",
                dependencies=(observed.task_id, schedule.task_id, block.task_id),
                gates=(),
                output_record_type="ActivationArtifact",
            )
            tasks.extend((readiness, prepared, final, observed, schedule, block, aggregate))
            seed_ids.extend((readiness.task_id, prepared.task_id, final.task_id))
        final_axis = {
            "axis_id": "final-axis",
            "count": 2,
            "sha256": "1" * 64,
        }
        omega = {
            "cache_kind": "fiber_exposures",
            "semantic_sha256": "2" * 64,
            "feature_axis": {
                "axis_id": "omega-axis",
                "count": 4,
                "sha256": "3" * 64,
            },
            "payload_relative_path": "fiber_ids.npy",
            "payload_sha256": "4" * 64,
        }
        plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=tuple(tasks),
        )
        extension = compile_sensitivity_extension_plan(
            plan,
            endpoint_ids=tuple(endpoint.identifier for endpoint in endpoints),
            analyses=("oss",),
            seed_task_ids=tuple(seed_ids),
            sensitivity_bases=tuple(
                {
                    "endpoint_id": endpoint.identifier,
                    "feature_axis": final_axis,
                    "omega_max": omega,
                }
                for endpoint in endpoints
            ),
        )

        gates = tuple(
            task
            for task in extension.tasks
            if task.service_id == "establish_oss_axis_equivalence"
        )
        observed_tasks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_ppam_observed_workspace"
        )
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0].output_record_type, "OSSAxisEquivalenceGroupRecord")
        self.assertTrue(gates[0].expensive_producer)
        self.assertTrue(gates[0].cache_first_expensive)
        self.assertEqual(len(observed_tasks), 2)
        self.assertTrue(
            all(gates[0].task_id in task.dependencies for task in observed_tasks)
        )

    def test_combined_extension_keeps_every_expensive_task_cache_first(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal-connectome",
        )
        readiness = _task(endpoint, "input_readiness", "observed")
        prepared = _task(
            endpoint,
            "prepare_exposure",
            "observed",
            dependencies=(readiness.task_id,),
        )
        final = _task(
            endpoint,
            "final_realization",
            "observed",
            dependencies=(readiness.task_id,),
        )
        jitter = _task(
            endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(final.task_id,),
        )
        observed = TaskSpec(
            key=TaskKey(
                endpoint.identifier,
                "ppam_observed_workspace",
                parameter_identity=SCIENTIFIC_HASH,
            ),
            endpoint_id=endpoint.identifier,
            model_family=endpoint.model_family,
            connectome_role="formal",
            stage="ppam_observed_workspace",
            round_id="round_oss",
            phase="sensitivity",
            service_id="prepare_ppam_observed_workspace",
            dependencies=(readiness.task_id, prepared.task_id, final.task_id),
            gates=(),
            output_record_type="PPAMObservedWorkspaceRecord",
            expensive_producer=True,
            cache_first_expensive=True,
        )
        schedule = TaskSpec(
            key=TaskKey(
                endpoint.identifier,
                "ppam_permutation_schedule",
                parameter_identity=SCIENTIFIC_HASH,
            ),
            endpoint_id=endpoint.identifier,
            model_family=endpoint.model_family,
            connectome_role="formal",
            stage="ppam_permutation_schedule",
            round_id="round_oss",
            phase="sensitivity",
            service_id="prepare_ppam_permutation_schedule",
            dependencies=(observed.task_id,),
            gates=(),
            output_record_type="ResamplingScheduleRecord",
        )
        block = TaskSpec(
            key=TaskKey(
                endpoint.identifier,
                "ppam_permutation_block_0000",
                parameter_identity=SCIENTIFIC_HASH,
            ),
            endpoint_id=endpoint.identifier,
            model_family=endpoint.model_family,
            connectome_role="formal",
            stage="ppam_permutation_block_0000",
            round_id="round_oss",
            phase="sensitivity",
            service_id="run_ppam_permutation_block",
            dependencies=(observed.task_id, schedule.task_id),
            gates=(),
            output_record_type="PPAMPermutationBlockRecord",
        )
        aggregate = TaskSpec(
            key=TaskKey(
                endpoint.identifier,
                "activation_sensitivity",
                parameter_identity=SCIENTIFIC_HASH,
            ),
            endpoint_id=endpoint.identifier,
            model_family=endpoint.model_family,
            connectome_role="formal",
            stage="activation_sensitivity",
            round_id="round_oss",
            phase="sensitivity",
            service_id="aggregate_ppam_activation",
            dependencies=(observed.task_id, schedule.task_id, block.task_id),
            gates=(),
            output_record_type="ActivationArtifact",
        )
        plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(
                readiness,
                prepared,
                final,
                jitter,
                observed,
                schedule,
                block,
                aggregate,
            ),
        )
        final_axis = {
            "axis_id": "final-axis",
            "count": 2,
            "sha256": "1" * 64,
        }
        omega = {
            "cache_kind": "fiber_exposures",
            "semantic_sha256": "2" * 64,
            "feature_axis": {
                "axis_id": "omega-axis",
                "count": 4,
                "sha256": "3" * 64,
            },
            "payload_relative_path": "fiber_ids.npy",
            "payload_sha256": "4" * 64,
        }
        rng = {
            "jitter_resamples": 50,
            "jitter_translation_fwhm_mm": 2.0,
            "seed": 42,
        }
        extension = compile_sensitivity_extension_plan(
            plan,
            endpoint_ids=(endpoint.identifier,),
            analyses=("jitter", "oss"),
            seed_task_ids=(readiness.task_id, prepared.task_id, final.task_id),
            jitter_bases=(
                {
                    "endpoint_id": endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": [
                        {
                            "kind": "fiber_exposures",
                            "semantic_sha256": "5" * 64,
                        }
                    ],
                },
            ),
            sensitivity_bases=(
                {
                    "endpoint_id": endpoint.identifier,
                    "feature_axis": final_axis,
                    "omega_max": omega,
                },
            ),
        )

        jitter_blocks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_jitter_exposure_block"
        )
        gates = tuple(
            task
            for task in extension.tasks
            if task.service_id == "establish_oss_axis_equivalence"
        )
        observed_tasks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_ppam_observed_workspace"
        )
        expensive = tuple(task for task in extension.tasks if task.expensive_producer)
        self.assertEqual(len(jitter_blocks), 2)
        self.assertEqual(len(gates), 1)
        self.assertEqual(len(observed_tasks), 1)
        self.assertTrue(
            all(task.cache_first_expensive for task in expensive)
        )
        self.assertIn(gates[0].task_id, observed_tasks[0].dependencies)
        jitter_target = next(
            task for task in extension.tasks if task.stage == "spatial_jitter"
        )
        self.assertTrue(
            {task.task_id for task in jitter_blocks}.issubset(
                set(jitter_target.dependencies)
            )
        )

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

    def test_final_in_sample_extension_inherits_exact_loocv_checkpoint(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        parent = _task(endpoint, "final_realization", "observed")
        formal = _task(
            endpoint,
            "formal_permutation",
            "formal",
            dependencies=(parent.task_id,),
        )
        target = _task(
            endpoint,
            "formal_in_sample",
            "formal",
            dependencies=(parent.task_id, formal.task_id),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="formal",
            tasks=(parent, formal, target),
        )
        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(endpoint.identifier,),
            analyses=("final_in_sample",),
            seed_task_ids=(parent.task_id, formal.task_id),
        )

        roots = tuple(task for task in extension.tasks if task.checkpoint_only)
        child = next(task for task in extension.tasks if task.stage == "formal_in_sample")
        self.assertEqual({task.task_id for task in roots}, {parent.task_id, formal.task_id})
        self.assertEqual(child.phase, "sensitivity")
        self.assertEqual(child.dependencies, (parent.task_id, formal.task_id))
        self.assertEqual(child.service_id, target.service_id)

        with self.assertRaisesRegex(
            SensitivityCheckpointError,
            "lacks completed direct parent outcomes",
        ):
            compile_sensitivity_extension_plan(
                full_plan,
                endpoint_ids=(endpoint.identifier,),
                analyses=("final_in_sample",),
                seed_task_ids=(parent.task_id,),
            )

    def test_jitter_extension_inserts_fixed_shared_physical_blocks(self) -> None:
        first_endpoint = EndpointKey(
            "study",
            "scale-one",
            "reference",
            "reference_voxel",
        )
        second_endpoint = EndpointKey(
            "study",
            "scale-two",
            "reference",
            "reference_voxel",
        )
        first_parent = _task(first_endpoint, "final_realization", "observed")
        second_parent = _task(second_endpoint, "final_realization", "observed")
        first_target = _task(
            first_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(first_parent.task_id,),
        )
        second_target = _task(
            second_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(second_parent.task_id,),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(first_parent, second_parent, first_target, second_target),
        )
        rng = {
            "jitter_resamples": 50,
            "jitter_translation_fwhm_mm": 2.0,
            "seed": 42,
        }
        shared = [
            {
                "kind": "voxel_exposures",
                "semantic_sha256": "d" * 64,
            }
        ]
        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(first_endpoint.identifier, second_endpoint.identifier),
            analyses=("jitter",),
            seed_task_ids=(first_parent.task_id, second_parent.task_id),
            jitter_bases=(
                {
                    "endpoint_id": first_endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": shared,
                },
                {
                    "endpoint_id": second_endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": shared,
                },
            ),
        )

        blocks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_jitter_exposure_block"
        )
        targets = tuple(
            task for task in extension.tasks if task.stage == "spatial_jitter"
        )
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(block.expensive_producer for block in blocks))
        self.assertTrue(all(block.cache_first_expensive for block in blocks))
        self.assertTrue(
            all(
                block.task_id
                == replace(
                    block,
                    expensive_producer=False,
                    cache_first_expensive=False,
                ).task_id
                for block in blocks
            )
        )
        self.assertEqual(
            tuple(
                (
                    block.execution_parameter("replicate_start"),
                    block.execution_parameter("replicate_stop"),
                )
                for block in blocks
            ),
            (("0", "25"), ("25", "50")),
        )
        self.assertEqual(
            {block.execution_parameter("group_id") for block in blocks},
            {targets[0].execution_parameter("jitter_block_group_id")},
        )
        self.assertEqual(
            {target.execution_parameter("jitter_block_group_id") for target in targets},
            {targets[0].execution_parameter("jitter_block_group_id")},
        )
        block_ids = {block.task_id for block in blocks}
        self.assertTrue(all(block_ids < set(target.dependencies) for target in targets))
        self.assertTrue(
            all(
                set(block.dependencies)
                == {first_parent.task_id, second_parent.task_id}
                for block in blocks
            )
        )
        self.assertTrue(all(task.checkpoint_only for task in extension.tasks[:2]))

    def test_adjusted_addon_uses_support_preserving_physical_blocks(self) -> None:
        reference_endpoint = EndpointKey(
            "study",
            "scale-one",
            "reference",
            "reference_voxel",
        )
        endpoint = EndpointKey(
            "study",
            "scale-one",
            "addon",
            "addon_voxel",
        )
        reference_input = _task(
            reference_endpoint,
            "input_readiness",
            "observed",
        )
        reference_prepared = _task(
            reference_endpoint,
            "prepare_exposure",
            "observed",
            dependencies=(reference_input.task_id,),
        )
        parent = _task(endpoint, "final_realization", "observed")
        target = _task(
            endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(parent.task_id, reference_input.task_id),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(reference_input, reference_prepared, parent, target),
        )

        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(endpoint.identifier,),
            analyses=("jitter",),
            seed_task_ids=(
                reference_input.task_id,
                reference_prepared.task_id,
                parent.task_id,
            ),
            jitter_bases=(
                {
                    "endpoint_id": endpoint.identifier,
                    "final_branch": "delta_reference_adjusted",
                    "rng_profile": {
                        "jitter_resamples": 50,
                        "jitter_translation_fwhm_mm": 2.0,
                        "seed": 42,
                    },
                    "shared_exposure_entries": [
                        {
                            "kind": "voxel_exposures",
                            "semantic_sha256": "d" * 64,
                        }
                    ],
                },
            ),
        )

        blocks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_jitter_exposure_block"
        )
        self.assertEqual(len(blocks), 2)
        descriptors = tuple(
            json.loads(block.execution_parameter("group_descriptor"))
            for block in blocks
        )
        self.assertEqual(
            {descriptor["producer_version"] for descriptor in descriptors},
            {"2"},
        )
        jitter = next(task for task in extension.tasks if task.stage == "spatial_jitter")
        block_ids = {block.task_id for block in blocks}
        self.assertTrue(block_ids < set(jitter.dependencies))
        self.assertIn(reference_prepared.task_id, jitter.dependencies)
        self.assertTrue(jitter.execution_parameter("jitter_block_group_id"))

    def test_jitter_endpoints_wait_for_every_physical_group(self) -> None:
        voxel_endpoint = EndpointKey(
            "study",
            "scale-one",
            "reference",
            "reference_voxel",
        )
        fiber_endpoint = EndpointKey(
            "study",
            "scale-two",
            "reference",
            "reference_fiber",
            "formal-connectome",
        )
        voxel_parent = _task(voxel_endpoint, "final_realization", "observed")
        fiber_parent = _task(fiber_endpoint, "final_realization", "observed")
        voxel_target = _task(
            voxel_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(voxel_parent.task_id,),
        )
        fiber_target = _task(
            fiber_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(fiber_parent.task_id,),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(voxel_parent, fiber_parent, voxel_target, fiber_target),
        )
        rng = {
            "jitter_resamples": 25,
            "jitter_translation_fwhm_mm": 2.0,
            "seed": 42,
        }
        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(voxel_endpoint.identifier, fiber_endpoint.identifier),
            analyses=("jitter",),
            seed_task_ids=(voxel_parent.task_id, fiber_parent.task_id),
            jitter_bases=(
                {
                    "endpoint_id": voxel_endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": [
                        {
                            "kind": "voxel_exposures",
                            "semantic_sha256": "d" * 64,
                        }
                    ],
                },
                {
                    "endpoint_id": fiber_endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": [
                        {
                            "kind": "fiber_exposures",
                            "semantic_sha256": "e" * 64,
                        }
                    ],
                },
            ),
        )

        blocks = tuple(
            task
            for task in extension.tasks
            if task.service_id == "prepare_jitter_exposure_block"
        )
        targets = tuple(
            task for task in extension.tasks if task.stage == "spatial_jitter"
        )
        self.assertEqual(len(blocks), 2)
        self.assertEqual(
            len(
                {
                    target.execution_parameter("jitter_block_group_id")
                    for target in targets
                }
            ),
            2,
        )
        block_ids = {block.task_id for block in blocks}
        self.assertTrue(all(block_ids < set(target.dependencies) for target in targets))

    def test_adjusted_addon_waits_for_reduced_physical_blocks(self) -> None:
        reference_endpoint = EndpointKey(
            "study",
            "scale-one",
            "reference",
            "reference_voxel",
        )
        addon_endpoint = EndpointKey(
            "study",
            "scale-two",
            "addon",
            "addon_voxel",
        )
        reference_input = _task(
            reference_endpoint,
            "input_readiness",
            "observed",
        )
        reference_prepared = _task(
            reference_endpoint,
            "prepare_exposure",
            "observed",
            dependencies=(reference_input.task_id,),
        )
        reference_parent = _task(
            reference_endpoint,
            "final_realization",
            "observed",
        )
        addon_parent = _task(addon_endpoint, "final_realization", "observed")
        reference_target = _task(
            reference_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(reference_parent.task_id,),
        )
        addon_target = _task(
            addon_endpoint,
            "spatial_jitter",
            "sensitivity",
            dependencies=(addon_parent.task_id, reference_input.task_id),
        )
        full_plan = ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="sensitivity",
            tasks=(
                reference_input,
                reference_prepared,
                reference_parent,
                addon_parent,
                reference_target,
                addon_target,
            ),
        )
        rng = {
            "jitter_resamples": 25,
            "jitter_translation_fwhm_mm": 2.0,
            "seed": 42,
        }
        shared = [
            {
                "kind": "voxel_exposures",
                "semantic_sha256": "d" * 64,
            }
        ]
        extension = compile_sensitivity_extension_plan(
            full_plan,
            endpoint_ids=(reference_endpoint.identifier, addon_endpoint.identifier),
            analyses=("jitter",),
            seed_task_ids=(
                reference_input.task_id,
                reference_prepared.task_id,
                reference_parent.task_id,
                addon_parent.task_id,
            ),
            jitter_bases=(
                {
                    "endpoint_id": reference_endpoint.identifier,
                    "rng_profile": rng,
                    "shared_exposure_entries": shared,
                },
                {
                    "endpoint_id": addon_endpoint.identifier,
                    "final_branch": "delta_reference_adjusted",
                    "rng_profile": rng,
                    "shared_exposure_entries": shared,
                },
            ),
        )

        adjusted_block = next(
            task
            for task in extension.tasks
            if task.service_id == "prepare_jitter_exposure_block"
            and json.loads(task.execution_parameter("group_descriptor"))[
                "producer_version"
            ]
            == "2"
        )
        adjusted = next(
            task
            for task in extension.tasks
            if task.endpoint_id == addon_endpoint.identifier
            and task.stage == "spatial_jitter"
        )
        self.assertIn(adjusted_block.task_id, adjusted.dependencies)
        self.assertIn(reference_prepared.task_id, adjusted.dependencies)
        self.assertTrue(adjusted.execution_parameter("jitter_block_group_id"))


if __name__ == "__main__":
    unittest.main()
