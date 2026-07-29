"""Tests for immutable Task 17 performance benchmark preparation."""

from __future__ import annotations

from dataclasses import fields, replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from dual_frequency.backends.activation.ossdbs import (
    OSS_SCIENTIFIC_BACKEND_VERSION,
    OSSRowInput,
    OSSScientificSettings,
    build_oss_row_cache_key,
)
from dual_frequency.cache import (
    CacheFileMetadata,
    ContentAddressedCache,
    ScientificCacheKey,
)
from dual_frequency.contracts import (
    AxisRef,
    OSSSharedOmegaGroupRecord,
    TaskKey,
)
from dual_frequency.workflow import (
    BenchmarkOSSInjectedFixtureSpec,
    ExecutionPlan,
    ServiceResult,
    SpawnWorkerSpec,
    TaskSpec,
)
from dual_frequency.workflow.process_worker import (
    _BenchmarkOSSInjectedToolchain,
)
import dual_frequency.workflow.process_worker as process_worker
from my_helper.fiber.pipelines import run_task17_performance_matrix as harness


class _Process:
    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


class _TaskStore:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, object]] = {}

    def write_task_state(
        self,
        task_id: str,
        payload: dict[str, object],
    ) -> None:
        self.states[task_id] = {**payload, "task_id": task_id}

    def read_task_state(self, task_id: str) -> dict[str, object] | None:
        return self.states.get(task_id)


def _task(
    *,
    endpoint_id: str,
    stage: str,
    service_id: str,
    dependencies: tuple[str, ...] = (),
    output_record_type: str = "SyntheticRecord",
) -> TaskSpec:
    return TaskSpec(
        key=TaskKey(
            endpoint_id=endpoint_id,
            stage=stage,
            parameter_identity="a" * 64,
        ),
        endpoint_id=endpoint_id,
        model_family="reference_fiber",
        connectome_role="formal",
        stage=stage,
        round_id=f"round_{stage}",
        phase="formal",
        service_id=service_id,
        dependencies=dependencies,
        gates=(),
        output_record_type=output_record_type,
    )


class Task17PerformanceMatrixTest(unittest.TestCase):
    @staticmethod
    def _publish_oss_row(
        *,
        root: Path,
        cache: ContentAddressedCache,
        name: str,
        axis: AxisRef,
        ids: np.ndarray,
        probabilities: np.ndarray,
    ) -> tuple[OSSRowInput, str]:
        row = OSSRowInput(
            subject_id="sub-01",
            side="L",
            source_id="left",
            feature_axis=axis,
            feature_ids=ids,
            geometry_hash="b" * 64,
            stimulation_hash="c" * 64,
            component_frequency_hash="d" * 64,
            transform_hash="e" * 64,
            connectome_feature_hash="f" * 64,
        )
        key = build_oss_row_cache_key(
            row,
            OSSScientificSettings(
                backend_version=OSS_SCIENTIFIC_BACKEND_VERSION
            ),
        )
        ids_path = root / f"{name}-ids.npy"
        probabilities_path = root / f"{name}-probabilities.npy"
        np.save(ids_path, ids, allow_pickle=False)
        np.save(probabilities_path, probabilities, allow_pickle=False)
        cache.publish(
            key,
            {
                "fiber_ids.npy": ids_path,
                "probabilities.npy": probabilities_path,
            },
            metadata={
                "fiber_ids.npy": CacheFileMetadata(
                    dtype="int64",
                    shape=(axis.count,),
                    axes=(axis,),
                    units="fiber_id",
                    space="right_canonical",
                ),
                "probabilities.npy": CacheFileMetadata(
                    dtype="float32",
                    shape=(axis.count,),
                    axes=(axis,),
                    units="probability",
                    space="right_canonical",
                ),
            },
        )
        return row, key.digest

    def test_injected_oss_toolchain_reconstructs_exact_ten_sample_counts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            axis = AxisRef("fiber-axis", 3, "a" * 64)
            ids = np.asarray([1, 2, 3], dtype=np.int64)
            probabilities = np.asarray([0.0, 0.3, 1.0], dtype=np.float32)
            row, identity = self._publish_oss_row(
                root=root,
                cache=cache,
                name="injected",
                axis=axis,
                ids=ids,
                probabilities=probabilities,
            )
            spec = BenchmarkOSSInjectedFixtureSpec(
                schema_version=(
                    "dual_frequency_task17_injected_oss_fixture_v1"
                ),
                cache_root=cache.root,
                accepted_closure_sha256="1" * 64,
                permitted_row_identities=(identity,),
            )
            toolchain = _BenchmarkOSSInjectedToolchain(spec)
            evidence = toolchain.produce_with_evidence(
                SimpleNamespace(
                    scientific_identity=identity,
                    row=row,
                )
            )
            self.assertEqual(
                np.count_nonzero(evidence.sample_states == 1, axis=0).tolist(),
                [0, 3, 10],
            )
            with self.assertRaisesRegex(
                ValueError,
                "outside the benchmark fixture",
            ):
                toolchain.produce_with_evidence(
                    SimpleNamespace(
                        scientific_identity="0" * 64,
                        row=row,
                    )
                )

    def test_spawn_worker_fixture_default_and_descriptor_validation(
        self,
    ) -> None:
        fixture_field = next(
            field
            for field in fields(SpawnWorkerSpec)
            if field.name == "benchmark_oss_fixture"
        )
        self.assertIsNone(fixture_field.default)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            valid = BenchmarkOSSInjectedFixtureSpec(
                schema_version=(
                    "dual_frequency_task17_injected_oss_fixture_v1"
                ),
                cache_root=root,
                accepted_closure_sha256="1" * 64,
                permitted_row_identities=("2" * 64,),
            )
            valid.validate()
            with self.assertRaisesRegex(
                ValueError,
                "descriptor differs",
            ):
                replace(
                    valid,
                    permitted_row_identities=("3" * 64, "2" * 64),
                ).validate()
            with self.assertRaisesRegex(
                ValueError,
                "SHA-256",
            ):
                replace(
                    valid,
                    accepted_closure_sha256="invalid",
                ).validate()

    def test_worker_initialization_overrides_only_injected_oss_toolchain(
        self,
    ) -> None:
        class _Provider:
            def __init__(self, *_args, **_kwargs) -> None:
                self.marker = "ordinary-provider"

            def oss_producer_toolchain(self) -> str:
                return "production-toolchain"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture_cache = ContentAddressedCache(root / "fixture-cache")
            axis = AxisRef("fiber-axis", 2, "a" * 64)
            row, identity = self._publish_oss_row(
                root=root,
                cache=fixture_cache,
                name="worker-injected",
                axis=axis,
                ids=np.asarray([1, 2], dtype=np.int64),
                probabilities=np.asarray([0.2, 0.7], dtype=np.float32),
            )
            fixture = BenchmarkOSSInjectedFixtureSpec(
                schema_version=(
                    "dual_frequency_task17_injected_oss_fixture_v1"
                ),
                cache_root=fixture_cache.root,
                accepted_closure_sha256="1" * 64,
                permitted_row_identities=(identity,),
            )
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            scientific_cache = root / "scientific-cache"
            scientific_cache.mkdir()
            spec = SpawnWorkerSpec(
                study=object(),
                configuration=object(),
                catalog=(),
                work_root=root / "work",
                artifact_roots=(artifact_root, scientific_cache),
                cache_root=scientific_cache,
                benchmark_oss_fixture=fixture,
            )
            with (
                patch.object(process_worker.os, "setsid"),
                patch(
                    "dual_frequency.runtime.input_provider."
                    "StudyRuntimeInputProvider",
                    _Provider,
                ),
                patch(
                    "dual_frequency.workflow.registry.build_default_registry",
                    return_value="registry",
                ),
            ):
                process_worker.initialize_worker(spec)
            self.assertIsInstance(process_worker._PROVIDER, _Provider)
            self.assertEqual(
                process_worker._PROVIDER.marker,
                "ordinary-provider",
            )
            injected = (
                process_worker._PROVIDER.oss_producer_toolchain()
            )
            self.assertIsInstance(
                injected,
                _BenchmarkOSSInjectedToolchain,
            )
            evidence = injected.produce_with_evidence(
                SimpleNamespace(
                    scientific_identity=identity,
                    row=row,
                )
            )
            self.assertEqual(
                np.count_nonzero(
                    evidence.sample_states == 1,
                    axis=0,
                ).tolist(),
                [2, 7],
            )

    def test_worker_initialization_without_fixture_uses_production_provider(
        self,
    ) -> None:
        class _Provider:
            def __init__(self, *_args, **_kwargs) -> None:
                self.marker = "ordinary-provider"

            def oss_producer_toolchain(self) -> str:
                return "production-toolchain"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            scientific_cache = root / "scientific-cache"
            scientific_cache.mkdir()
            spec = SpawnWorkerSpec(
                study=object(),
                configuration=object(),
                catalog=(),
                work_root=root / "work",
                artifact_roots=(artifact_root, scientific_cache),
                cache_root=scientific_cache,
            )
            with (
                patch.object(process_worker.os, "setsid"),
                patch(
                    "dual_frequency.runtime.input_provider."
                    "StudyRuntimeInputProvider",
                    _Provider,
                ),
                patch(
                    "dual_frequency.workflow.registry.build_default_registry",
                    return_value="registry",
                ),
            ):
                process_worker.initialize_worker(spec)
            self.assertIs(type(process_worker._PROVIDER), _Provider)
            self.assertEqual(
                process_worker._PROVIDER.marker,
                "ordinary-provider",
            )
            self.assertEqual(
                process_worker._PROVIDER.oss_producer_toolchain(),
                "production-toolchain",
            )

    def test_accepted_oss_cache_closure_drives_row_cache_states(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            final_axis = AxisRef("final-axis", 2, "1" * 64)
            omega_axis = AxisRef("omega-axis", 3, "2" * 64)
            omega_ids = np.asarray([1, 2, 3], dtype=np.int64)
            _omega_row, omega_identity = self._publish_oss_row(
                root=root,
                cache=cache,
                name="omega",
                axis=omega_axis,
                ids=omega_ids,
                probabilities=np.asarray([0.1, 0.3, 0.8], dtype=np.float32),
            )
            axis_key = ScientificCacheKey(
                geometry_hash="1" * 64,
                stimulation_hash="2" * 64,
                component_frequency_hash="3" * 64,
                transform_hash="4" * 64,
                connectome_feature_hash="5" * 64,
                backend_name="normative_fiber_omega_max",
                backend_version="2",
                scientific_parameter_hashes=(("grid", "6" * 64),),
                kind="fiber_exposures",
            )
            axis_path = root / "omega-axis.npy"
            np.save(axis_path, omega_ids, allow_pickle=False)
            cache.publish(
                axis_key,
                {"fiber_ids.npy": axis_path},
                metadata={
                    "fiber_ids.npy": CacheFileMetadata(
                        dtype="int64",
                        shape=(omega_axis.count,),
                        axes=(omega_axis,),
                        units="fiber_id",
                        space="right_canonical",
                    )
                },
            )
            record = OSSSharedOmegaGroupRecord(
                group_id="reference-group",
                model_family="reference_fiber",
                preparation_status="omega_max_ready",
                final_feature_axis=final_axis,
                omega_feature_axis=omega_axis,
                omega_cache_kind=axis_key.kind,
                omega_cache_semantic_sha256=axis_key.digest,
                endpoint_ids=("endpoint-a",),
                omega_row_ids=(omega_identity,),
            )
            closure = harness._accepted_oss_cache_closure(
                (("task_omega", record),),
                cache_root=cache.root,
            )
            self.assertEqual(
                [row["scientific_identity"] for row in closure["rows"]],
                [omega_identity],
            )
            self.assertEqual(
                closure["groups"][0]["omega_row_ids"],
                [omega_identity],
            )
            descriptors = harness._accepted_oss_cache_entry_descriptors(
                closure
            )
            seed = harness._copy_verified_cache_entries(
                source_cache_root=cache.root,
                destination_cache_root=root / "row-cache",
                entries=descriptors,
            )
            self.assertEqual(len(seed["entries"]), 1)
            copied_cache = ContentAddressedCache(root / "row-cache")
            self.assertIsNotNone(
                copied_cache.resolve_identity(
                    "oss_rows",
                    omega_identity,
                )
            )
            fixture = harness._prepare_injected_oss_fixture(
                accepted_closure=closure,
                destination_cache_root=root / "injected-fixture",
            )
            self.assertEqual(len(fixture["permitted_row_identities"]), 1)
            spawn_fixture = harness._benchmark_oss_fixture_spec(fixture)
            self.assertIsInstance(
                spawn_fixture,
                BenchmarkOSSInjectedFixtureSpec,
            )
            self.assertEqual(
                spawn_fixture.permitted_row_identities,
                tuple(fixture["permitted_row_identities"]),
            )
            fixture_cache = ContentAddressedCache(
                root / "injected-fixture"
            )
            self.assertIsNotNone(
                fixture_cache.resolve_identity(
                    "oss_rows",
                    omega_identity,
                )
            )
            empty_proof = harness._empty_cache_proof(
                root / "empty-row-cache"
            )
            self.assertEqual(empty_proof["entry_count"], 0)
            shared_cache = cache.root / "shared_exposure_v2"
            (shared_cache / "._fiber_exposures").write_bytes(
                b"AppleDouble metadata"
            )
            (
                shared_cache
                / "fiber_exposures"
                / f"._{axis_key.digest}"
            ).write_bytes(b"AppleDouble metadata")
            warm_manifest_path = root / "warm-seed.json"
            warm_manifest = harness._publish_warm_seed_manifest(
                warm_manifest_path,
                cache_root=cache.root,
                slice_id="slice-a",
            )
            self.assertEqual(len(warm_manifest["entries"]), 2)
            copied_warm = harness._copy_warm_seed(
                warm_manifest_path,
                destination_cache_root=root / "warm-row-cache",
                expected_slice_id="slice-a",
            )
            self.assertEqual(len(copied_warm["entries"]), 2)
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "identity differs",
            ):
                harness._copy_warm_seed(
                    warm_manifest_path,
                    destination_cache_root=root / "wrong-slice-cache",
                    expected_slice_id="slice-b",
                )
            resolved = {"accepted_oss_cache": closure}
            injected_state = harness._prepare_row_cache_state(
                resolved=resolved,
                row={
                    "cache_state": "cold",
                    "solver_mode": "injected",
                    "slice_id": "slice-a",
                },
                benchmark_root=root,
                attempt_root=root / "attempt-injected",
            )
            self.assertEqual(injected_state["cache_source"], "empty")
            self.assertIsNotNone(injected_state["injected_fixture"])
            real_cache_hit_state = harness._prepare_row_cache_state(
                resolved=resolved,
                row={
                    "cache_state": "warm",
                    "solver_mode": "real_cache_hit",
                    "slice_id": "slice-a",
                },
                benchmark_root=root,
                attempt_root=root / "attempt-real-cache-hit",
            )
            self.assertEqual(
                real_cache_hit_state["cache_source"],
                "accepted_independent_oss",
            )
            expected_warm_manifest = (
                root / "warm_seeds" / "slice-a" / "warm_seed.json"
            )
            harness._publish_warm_seed_manifest(
                expected_warm_manifest,
                cache_root=cache.root,
                slice_id="slice-a",
            )
            ordinary_warm_state = harness._prepare_row_cache_state(
                resolved=resolved,
                row={
                    "cache_state": "warm",
                    "solver_mode": "none",
                    "slice_id": "slice-a",
                },
                benchmark_root=root,
                attempt_root=root / "attempt-ordinary-warm",
            )
            self.assertEqual(
                ordinary_warm_state["cache_source"],
                "unmeasured_warm_seed",
            )
            resumed_root = root / "resumed-benchmark"
            resumed_slice_id = "a" * 64
            resumed_attempt = (
                resumed_root
                / "warm_seeds"
                / resumed_slice_id
                / "attempts"
                / "attempt_0001"
            )
            resumed_cache = resumed_attempt / "scientific_cache"
            harness._copy_verified_cache_entries(
                source_cache_root=cache.root,
                destination_cache_root=resumed_cache,
                entries=harness._isolated_cache_entry_descriptors(
                    cache.root
                ),
            )
            harness._atomic_json(
                resumed_attempt / "run" / "complete.json",
                {"status": "completed"},
            )
            harness._atomic_json(
                resumed_attempt / "seed_attempt_result.json",
                {
                    "schema_version": (
                        "dual_frequency_task17_warm_seed_result_v1"
                    ),
                    "slice_id": resumed_slice_id,
                    "run_root": str(
                        (resumed_attempt / "run").resolve()
                    ),
                },
            )
            resumed = harness._execute_unmeasured_warm_seed(
                resolved={},
                row={
                    "cache_state": "warm",
                    "solver_mode": "none",
                    "slice_id": resumed_slice_id,
                },
                benchmark_root=resumed_root,
            )
            self.assertEqual(resumed["slice_id"], resumed_slice_id)
            self.assertEqual(len(resumed["entries"]), 2)
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "destination must be empty",
            ):
                harness._copy_verified_cache_entries(
                    source_cache_root=cache.root,
                    destination_cache_root=root / "row-cache",
                    entries=descriptors,
                )

    def test_shared_omega_cache_closure_contains_rows_without_decisions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            final_axis = AxisRef("final-axis", 2, "1" * 64)
            omega_axis = AxisRef("omega-axis", 3, "2" * 64)
            omega_ids = np.asarray([1, 2, 3], dtype=np.int64)
            _row, row_id = self._publish_oss_row(
                root=root,
                cache=cache,
                name="omega-only",
                axis=omega_axis,
                ids=omega_ids,
                probabilities=np.asarray([0.1, 0.3, 0.8], dtype=np.float32),
            )
            axis_key = ScientificCacheKey(
                geometry_hash="1" * 64,
                stimulation_hash="2" * 64,
                component_frequency_hash="3" * 64,
                transform_hash="4" * 64,
                connectome_feature_hash="5" * 64,
                backend_name="normative_fiber_omega_max",
                backend_version="2",
                scientific_parameter_hashes=(("grid", "6" * 64),),
                kind="fiber_exposures",
            )
            axis_path = root / "omega-axis.npy"
            np.save(axis_path, omega_ids, allow_pickle=False)
            cache.publish(
                axis_key,
                {"fiber_ids.npy": axis_path},
                metadata={
                    "fiber_ids.npy": CacheFileMetadata(
                        dtype="int64",
                        shape=(omega_axis.count,),
                        axes=(omega_axis,),
                        units="fiber_id",
                        space="right_canonical",
                    )
                },
            )
            record = OSSSharedOmegaGroupRecord(
                group_id="reference-group",
                model_family="reference_fiber",
                preparation_status="omega_max_ready",
                final_feature_axis=final_axis,
                omega_feature_axis=omega_axis,
                omega_cache_kind=axis_key.kind,
                omega_cache_semantic_sha256=axis_key.digest,
                endpoint_ids=("endpoint-a",),
                omega_row_ids=(row_id,),
            )

            closure = harness._accepted_oss_cache_closure(
                (("task_omega", record),),
                cache_root=cache.root,
            )
            self.assertEqual(
                [row["scientific_identity"] for row in closure["rows"]],
                [row_id],
            )
            self.assertNotIn("decisions", closure["groups"][0])
            descriptors = harness._accepted_oss_cache_entry_descriptors(
                closure
            )
            self.assertEqual(
                descriptors,
                (
                    {
                        "kind": "oss_rows",
                        "scientific_identity": row_id,
                        "manifest_sha256": closure["rows"][0][
                            "manifest_sha256"
                        ],
                    },
                ),
            )

    def test_accepted_oss_groups_require_both_fiber_families(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks_root = root / "tasks"
            tasks_root.mkdir()
            axis = AxisRef("fiber-axis", 2, "1" * 64)
            for index, family in enumerate(
                ("reference_fiber", "addon_fiber"),
                start=2,
            ):
                record = OSSSharedOmegaGroupRecord(
                    group_id=f"{family}-group",
                    model_family=family,
                    preparation_status="omega_max_ready",
                    final_feature_axis=axis,
                    omega_feature_axis=axis,
                    omega_cache_kind="fiber_exposures",
                    omega_cache_semantic_sha256=f"{index:064x}",
                    endpoint_ids=(f"{family}-endpoint",),
                    omega_row_ids=(f"{index + 2:064x}",),
                )
                task_id = f"task_{family}"
                (tasks_root / f"{task_id}.json").write_text(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "endpoint_id": f"{family}-endpoint",
                            "service_id": "prepare_oss_omega_max_rows",
                            "status": "completed",
                            "reason": "completed",
                            "started_at": None,
                            "finished_at": None,
                            "result": ServiceResult.from_record(
                                record
                            ).as_dict(),
                        }
                    ),
                    encoding="utf-8",
                )
            records = harness._accepted_oss_group_records(root)
            self.assertEqual(
                {record.model_family for _, record in records},
                {"reference_fiber", "addon_fiber"},
            )
            (tasks_root / "task_addon_fiber.json").unlink()
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "exact two Omega-only groups",
            ):
                harness._accepted_oss_group_records(root)

    def test_accepted_oss_records_decode_shared_omega_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks_root = root / "tasks"
            tasks_root.mkdir()
            axis = AxisRef("fiber-axis", 2, "1" * 64)
            for index, family in enumerate(
                ("reference_fiber", "addon_fiber"),
                start=2,
            ):
                record = OSSSharedOmegaGroupRecord(
                    group_id=f"{family}-group",
                    model_family=family,
                    preparation_status="omega_max_ready",
                    final_feature_axis=axis,
                    omega_feature_axis=axis,
                    omega_cache_kind="fiber_exposures",
                    omega_cache_semantic_sha256=f"{index:064x}",
                    endpoint_ids=(f"{family}-endpoint",),
                    omega_row_ids=(f"{index + 2:064x}",),
                )
                task_id = f"task_{family}"
                (tasks_root / f"{task_id}.json").write_text(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "service_id": "prepare_oss_omega_max_rows",
                            "status": "completed",
                            "result": ServiceResult.from_record(record).as_dict(),
                        }
                    ),
                    encoding="utf-8",
                )
            records = harness._accepted_oss_group_records(root)
            self.assertTrue(
                all(
                    isinstance(record, OSSSharedOmegaGroupRecord)
                    for _task_id, record in records
                )
            )

    def test_terminal_run_requires_the_root_completion_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "dual_frequency_run_v1",
                        "run_id": "completed-run",
                        "final_status": "completed",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "is not a completed run",
            ):
                harness._terminal_run(root, "accepted run")
            (root / "complete.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                harness._terminal_run(root, "accepted run")["run_id"],
                "completed-run",
            )

    def test_completed_task_import_requires_the_task_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks = root / "tasks"
            tasks.mkdir()
            task_id = "task_marker_contract"
            (tasks / f"{task_id}.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "result": {"output_record_type": "SyntheticRecord"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(harness._completed_task_ids(root), set())
            marker = tasks / task_id / "complete.json"
            marker.parent.mkdir()
            marker.write_text("{}\n", encoding="utf-8")
            self.assertEqual(harness._completed_task_ids(root), {task_id})

    def test_exact_three_connectome_key_closure_has_72_rows(self) -> None:
        rows = harness._row_keys(("ppmi", "mgh", "dtor"))
        self.assertEqual(len(rows), 72)
        keys = {
            (
                row["benchmark_class"],
                row["connectome_id"],
                row["cache_state"],
                row["solver_mode"],
                row["workers"],
            )
            for row in rows
        }
        self.assertEqual(len(keys), 72)
        self.assertEqual(
            sum(row["benchmark_class"] == "fiber_connectome" for row in rows),
            24,
        )
        self.assertEqual(
            sum(row["solver_mode"] == "real_solver" for row in rows),
            4,
        )

    def test_maximum_burden_uses_each_model_domains_replicates(self) -> None:
        bases = (
            {
                "endpoint_id": "endpoint_voxel",
                "model_family": "reference_voxel",
                "subject_axis": {"count": 20},
                "feature_axis": {"count": 100},
                "omega_max": None,
            },
            {
                "endpoint_id": "endpoint_fiber",
                "model_family": "reference_fiber",
                "subject_axis": {"count": 20},
                "feature_axis": {"count": 90},
                "omega_max": {"feature_axis": {"count": 90}},
            },
        )
        selected, evidence = harness._maximum_base(
            bases,
            kind="formal_permutation",
            replicates_by_domain={
                "direct_voxel": 100,
                "normative_fiber": 200,
            },
        )
        self.assertEqual(selected["endpoint_id"], "endpoint_fiber")
        self.assertEqual(evidence["selected"]["burden"], 360000)
        self.assertEqual(evidence["selected"]["replicates"], 200)

    def test_maximum_burden_uses_endpoint_id_as_final_tie_break(self) -> None:
        bases = (
            {
                "endpoint_id": "endpoint_b",
                "model_family": "reference_voxel",
                "subject_axis": {"count": 20},
                "feature_axis": {"count": 100},
            },
            {
                "endpoint_id": "endpoint_a",
                "model_family": "addon_voxel",
                "subject_axis": {"count": 20},
                "feature_axis": {"count": 100},
            },
        )
        selected, _evidence = harness._maximum_base(
            bases,
            kind="bootstrap",
            replicates_by_domain={"direct_voxel": 100},
        )
        self.assertEqual(selected["endpoint_id"], "endpoint_a")

    def test_slice_separates_parent_and_oss_imports(self) -> None:
        parent = _task(
            endpoint_id="endpoint_a",
            stage="parent",
            service_id="realize_reference_final",
        )
        gate = _task(
            endpoint_id="endpoint_a",
            stage="gate",
            service_id="prepare_oss_omega_max_rows",
            dependencies=(parent.task_id,),
        )
        measured = _task(
            endpoint_id="endpoint_a",
            stage="measured",
            service_id="prepare_ppam_observed_workspace",
            dependencies=(parent.task_id, gate.task_id),
        )
        plan = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="formal",
            tasks=(parent, gate, measured),
        )
        descriptor = harness._slice_descriptor(
            plan,
            (measured,),
            parent_completed={parent.task_id},
            oss_completed={gate.task_id},
            label="ppam",
        )
        self.assertEqual(
            descriptor["imported_parent_task_ids"],
            [parent.task_id],
        )
        self.assertEqual(
            descriptor["imported_oss_task_ids"],
            [gate.task_id],
        )
        self.assertEqual(
            descriptor["selected_task_ids"],
            [measured.task_id],
        )

    def test_slice_rejects_missing_imported_dependency(self) -> None:
        parent = _task(
            endpoint_id="endpoint_a",
            stage="parent",
            service_id="realize_reference_final",
        )
        measured = _task(
            endpoint_id="endpoint_a",
            stage="measured",
            service_id="prepare_formal_operator_workspace",
            dependencies=(parent.task_id,),
        )
        plan = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="formal",
            tasks=(parent, measured),
        )
        with self.assertRaisesRegex(
            harness.PerformanceMatrixHarnessError,
            "lacks completed imported dependency",
        ):
            harness._slice_descriptor(
                plan,
                (measured,),
                parent_completed=set(),
                oss_completed=set(),
                label="formal_permutation",
            )

    def test_imported_checkpoint_states_decode_the_exact_slice_roots(
        self,
    ) -> None:
        axis = AxisRef("fiber-axis", 2, "1" * 64)
        record = OSSSharedOmegaGroupRecord(
            group_id="checkpoint-group",
            model_family="reference_fiber",
            preparation_status="omega_max_ready",
            final_feature_axis=axis,
            omega_feature_axis=axis,
            omega_cache_kind="fiber_exposures",
            omega_cache_semantic_sha256="2" * 64,
            endpoint_ids=("endpoint_a",),
            omega_row_ids=("3" * 64,),
        )
        parent = _task(
            endpoint_id="endpoint_a",
            stage="parent",
            service_id="prepare_oss_omega_max_rows",
            output_record_type="OSSSharedOmegaGroupRecord",
        )
        selected = _task(
            endpoint_id="endpoint_a",
            stage="selected",
            service_id="prepare_ppam_observed_workspace",
            dependencies=(parent.task_id,),
        )
        full = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="sensitivity",
            tasks=(parent, selected),
        )
        sliced = harness._execution_slice_plan(full, (selected,))
        descriptor = harness._slice_descriptor(
            sliced,
            (selected,),
            parent_completed=set(),
            oss_completed={parent.task_id},
            label="ppam",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent_root = root / "parent"
            oss_root = root / "oss"
            (parent_root / "tasks").mkdir(parents=True)
            (oss_root / "tasks").mkdir(parents=True)
            state = {
                "task_id": parent.task_id,
                "endpoint_id": parent.endpoint_id,
                "service_id": parent.service_id,
                "status": "completed",
                "reason": "completed",
                "started_at": None,
                "finished_at": None,
                "result": ServiceResult.from_record(record).as_dict(),
            }
            (oss_root / "tasks" / f"{parent.task_id}.json").write_text(
                json.dumps(state),
                encoding="utf-8",
            )
            states, closure = harness._imported_checkpoint_states(
                descriptor,
                parent_root=parent_root,
                oss_root=oss_root,
            )
            self.assertEqual(states, (state,))
            self.assertEqual(
                closure["entries"][0]["task_id"],
                parent.task_id,
            )
            store = _TaskStore()
            self.assertEqual(
                harness._install_imported_checkpoint_states(store, states),
                (parent.task_id,),
            )
            self.assertEqual(store.states[parent.task_id], state)
            row = {
                "row_id": "row_checkpoint_attempt",
                "benchmark_class": "formal_permutation",
                "connectome_id": None,
                "cache_state": "cold",
                "solver_mode": "none",
                "workers": 1,
                "slice_id": descriptor["slice_id"],
                "planned_status": "planned",
            }
            resolved = {
                "rows": [row],
                "slices": [descriptor],
                "accepted_parent": {"root": str(parent_root)},
                "accepted_independent_oss": {"root": str(oss_root)},
                "accepted_oss_cache": {
                    "cache_root": str(root / "unused-cache"),
                    "groups": [],
                    "rows": [],
                    "closure_sha256": "a" * 64,
                },
            }
            attempt, attempt_plan = harness._prepare_row_attempt(
                resolved=resolved,
                row=row,
                benchmark_root=root / "benchmark",
            )
            self.assertEqual(attempt.name, "attempt_0001")
            self.assertTrue((attempt / "attempt_plan.json").is_file())
            self.assertEqual(
                attempt_plan["selected_task_ids"],
                [selected.task_id],
            )
            (
                reopened_attempt_plan,
                reopened_states,
                reopened_cache_state,
                reopened_descriptor,
                reopened_execution_plan,
            ) = harness._open_row_attempt_inputs(
                resolved=resolved,
                row=row,
                benchmark_root=root / "benchmark",
                attempt_root=attempt,
            )
            self.assertEqual(reopened_attempt_plan, attempt_plan)
            self.assertEqual(reopened_states, states)
            self.assertEqual(reopened_cache_state["cache_source"], "empty")
            self.assertEqual(reopened_descriptor, descriptor)
            self.assertEqual(reopened_execution_plan, sliced)

    def test_execution_slice_replaces_only_direct_parents_with_checkpoints(
        self,
    ) -> None:
        parent = _task(
            endpoint_id="endpoint_a",
            stage="parent",
            service_id="realize_reference_final",
        )
        first = _task(
            endpoint_id="endpoint_a",
            stage="first",
            service_id="prepare_formal_operator_workspace",
            dependencies=(parent.task_id,),
        )
        second = _task(
            endpoint_id="endpoint_a",
            stage="second",
            service_id="run_formal_permutation_block",
            dependencies=(first.task_id,),
        )
        source = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="formal",
            tasks=(parent, first, second),
        )
        sliced = harness._execution_slice_plan(source, (first, second))
        self.assertEqual(len(sliced.tasks), 3)
        self.assertTrue(sliced.tasks[0].checkpoint_only)
        self.assertEqual(sliced.tasks[0].task_id, parent.task_id)
        self.assertFalse(sliced.tasks[1].checkpoint_only)
        self.assertEqual(sliced.tasks[2].dependencies, (first.task_id,))
        payload = harness._plain(sliced)
        self.assertEqual(
            harness._execution_plan_from_payload(payload),
            sliced,
        )
        payload["unexpected_plan_field"] = "ignored"
        payload["tasks"][0]["unexpected"] = True
        payload["tasks"][0]["key"]["unexpected"] = "ignored"
        self.assertEqual(
            harness._execution_plan_from_payload(payload),
            sliced,
        )
        descriptor = harness._slice_descriptor(
            sliced,
            (first, second),
            parent_completed={parent.task_id},
            oss_completed=set(),
            label="formal_permutation",
        )
        resolved = {
            "slices": [descriptor],
            "rows": [
                {
                    "row_id": "row-formal",
                    "slice_id": descriptor["slice_id"],
                }
            ],
        }
        row = harness._resolved_row(resolved, "row-formal")
        reopened_descriptor, reopened_plan = harness._resolved_slice(
            resolved,
            row,
        )
        self.assertEqual(reopened_descriptor, descriptor)
        self.assertEqual(reopened_plan, sliced)
        with self.assertRaisesRegex(
            harness.PerformanceMatrixHarnessError,
            "resolve exactly once",
        ):
            harness._resolved_row(
                {
                    **resolved,
                    "rows": [resolved["rows"][0], resolved["rows"][0]],
                },
                "row-formal",
            )

    def test_request_rejects_an_operator_authored_row_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in (
                "parent",
                "oss",
                "work",
            ):
                (root / name).mkdir()
            for name in (
                "study.json",
                "direct.yaml",
                "fiber.yaml",
                "workflow.yaml",
            ):
                (root / name).write_text("{}\n", encoding="utf-8")
            request = {
                "schema_version": harness._REQUEST_SCHEMA,
                "plan_id": "plan",
                "accepted_parent_root": str(root / "parent"),
                "accepted_independent_oss_root": str(root / "oss"),
                "study_base": str(root / "study.json"),
                "direct_voxel_model": str(root / "direct.yaml"),
                "normative_fiber_model": str(root / "fiber.yaml"),
                "workflow_profile": str(root / "workflow.yaml"),
                "conda_environment": "leaddbs",
                "working_directory": str(root / "work"),
                "real_cold_solver_authorization": None,
                "benchmark_class": "direct_voxel",
            }
            path = root / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "fields differ",
            ):
                harness._load_request(path)
            request.pop("benchmark_class")
            request["conda_environment"] = "bad/name"
            path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "path-safe",
            ):
                harness._load_request(path)

    def test_request_identity_uses_parsed_semantic_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("parent", "oss", "work"):
                (root / name).mkdir()
            for name in (
                "study.json",
                "direct.yaml",
                "fiber.yaml",
                "workflow.yaml",
            ):
                (root / name).write_text("{}\n", encoding="utf-8")
            request = {
                "schema_version": harness._REQUEST_SCHEMA,
                "plan_id": "plan",
                "accepted_parent_root": str(root / "parent"),
                "accepted_independent_oss_root": str(root / "oss"),
                "study_base": str(root / "study.json"),
                "direct_voxel_model": str(root / "direct.yaml"),
                "normative_fiber_model": str(root / "fiber.yaml"),
                "workflow_profile": str(root / "workflow.yaml"),
                "conda_environment": "leaddbs",
                "working_directory": str(root / "work"),
                "real_cold_solver_authorization": None,
            }
            path = root / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            first_request, first_identity = harness._load_request(path)
            equivalent = dict(reversed(tuple(request.items())))
            equivalent["plan_id"] = " plan "
            equivalent["accepted_parent_root"] = (
                f"{root}/work/../parent"
            )
            equivalent["study_base"] = f"{root}/./study.json"
            equivalent["working_directory"] = f"{root}/work/."
            path.write_text(
                json.dumps(
                    equivalent,
                    indent=4,
                )
                + "\n",
                encoding="utf-8",
            )
            second_request, second_identity = harness._load_request(path)
            self.assertEqual(first_request, second_request)
            self.assertEqual(first_identity, second_identity)

    def test_parent_input_bundle_uses_bound_paths_not_source_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            inputs = parent / "inputs"
            inputs.mkdir()
            roles = {
                "study_base": "study.json",
                "direct_voxel_model": "direct.yaml",
                "normative_fiber_model": "fiber.yaml",
                "workflow_profile": "workflow.yaml",
            }
            request: dict[str, object] = {}
            files: dict[str, dict[str, str]] = {}
            for role, name in roles.items():
                path = inputs / name
                path.write_text("{}\n", encoding="utf-8")
                request[role] = str(path)
                files[role] = {
                    "relative_path": str(path.relative_to(parent)),
                }
            (inputs / "input_bundle.json").write_text(
                json.dumps(
                    {
                        "schema_version": "dual_frequency_input_bundle_v1",
                        "files": files,
                    }
                ),
                encoding="utf-8",
            )
            first = harness._validate_input_bundle(parent, request)
            (inputs / "workflow.yaml").write_text(
                "{ }\n",
                encoding="utf-8",
            )
            second = harness._validate_input_bundle(parent, request)
            expected = {
                role: {"path": str(Path(str(path)).resolve())}
                for role, path in request.items()
            }
            self.assertEqual(first, expected)
            self.assertEqual(second, expected)

    def test_benchmark_root_rejects_a_protected_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            protected = root / "production" / "cache"
            protected.mkdir(parents=True)
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "overlaps",
            ):
                harness._benchmark_root(
                    root / "production",
                    protected=(protected,),
                )

    def test_runner_readiness_binds_row_pid_plan_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "run"
            run_root.mkdir()
            ready = root / "runner_ready.json"
            ready.write_text(
                json.dumps(
                    {
                        "schema_version": harness._RUNNER_READY_SCHEMA,
                        "row_id": "row_a",
                        "runner_pid": 123,
                        "run_root": str(run_root),
                        "segment_plan_sha256": "a" * 64,
                        "imported_parent_task_ids": ["task_parent"],
                        "imported_oss_task_ids": ["task_gate"],
                    }
                ),
                encoding="utf-8",
            )
            document = harness._runner_ready(
                _Process(),
                ready,
                row_id="row_a",
                timeout_seconds=1,
            )
            self.assertEqual(document["runner_pid"], 123)

    def test_runner_exit_before_readiness_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "exited before",
            ):
                harness._runner_ready(
                    _Process(2),
                    Path(temporary) / "missing.json",
                    row_id="row_a",
                    timeout_seconds=1,
                )

    def test_measurement_start_round_trip_binds_byte_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "byte-ledger.json"
            ledger.write_text('{"schema_version":"ledger"}\n', encoding="utf-8")
            token = root / "measurement_start.json"
            published = harness._measurement_start(
                token,
                row_id="row_a",
                runner_pid=123,
                byte_ledger_index=ledger,
            )
            reopened = harness._wait_for_measurement_start(
                token,
                row_id="row_a",
                runner_pid=123,
                timeout_seconds=1,
            )
            self.assertEqual(reopened, published)

    def test_measurement_start_rejects_a_changed_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "byte-ledger.json"
            ledger.write_text('{"schema_version":"ledger"}\n', encoding="utf-8")
            token = root / "measurement_start.json"
            harness._measurement_start(
                token,
                row_id="row_a",
                runner_pid=123,
                byte_ledger_index=ledger,
            )
            ledger.write_text('{"schema_version":"changed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "byte-ledger identity differs",
            ):
                harness._wait_for_measurement_start(
                    token,
                    row_id="row_a",
                    runner_pid=123,
                    timeout_seconds=1,
                )

    def test_terminal_probe_summary_requires_one_complete_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "probe.csv"
            path.write_text(
                "\n".join(
                    (
                        "timestamp_utc,elapsed_monotonic_seconds,process_count,"
                        "tree_rss_bytes,aggregate_cpu_seconds,swap_used_bytes,"
                        "source_bytes,scratch_bytes,event",
                        "2026-07-25T00:00:00+00:00,0.1,2,100,0.2,10,3,4,sample",
                        "2026-07-25T00:00:01+00:00,1.1,1,120,0.8,10,5,7,sample",
                        "2026-07-25T00:00:02+00:00,2.1,0,0,0.8,10,5,7,runner_exit",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            summary = harness._terminal_probe_summary(path)
            self.assertEqual(summary["row_count"], 3)
            self.assertEqual(summary["peak_rss_bytes"], 120)
            self.assertEqual(summary["source_bytes"], 5)
            self.assertEqual(summary["scratch_bytes"], 7)

    def test_terminal_probe_summary_rejects_nonterminal_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "probe.csv"
            path.write_text(
                "\n".join(
                    (
                        "timestamp_utc,elapsed_monotonic_seconds,process_count,"
                        "tree_rss_bytes,aggregate_cpu_seconds,swap_used_bytes,"
                        "source_bytes,scratch_bytes,event",
                        "2026-07-25T00:00:00+00:00,0.1,1,100,0.2,10,3,4,sample",
                        "2026-07-25T00:00:01+00:00,1.1,0,0,0.2,10,3,4,sample",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "terminal event differs",
            ):
                harness._terminal_probe_summary(path)

    def test_numerical_payload_removes_only_run_local_locations(self) -> None:
        normalized = harness._numerical_payload(
            {
                "record": {
                    "uri": "file:///row-a/value.npy",
                    "generation_path": "work/task_a/attempt-1/generation",
                    "sha256": "a" * 64,
                    "path_semantics": "scientific-token",
                }
            }
        )
        self.assertEqual(
            normalized,
            {
                "record": {
                    "sha256": "a" * 64,
                    "path_semantics": "scientific-token",
                }
            },
        )

    def test_io_classification_comes_from_run_scheduler_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "execution_segments" / "scheduler.json"
            path.parent.mkdir()
            document = {
                "schema_version": "dual_frequency_scheduler_windows_v1",
                "segment_id": "segment_0001",
                "rows": [{"storage_limited": False}],
            }
            path.write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            segment = {
                "segment_id": "segment_0001",
                "scheduler_windows_path": str(path.relative_to(root)),
                "scheduler_windows_sha256": harness._sha256_file(path),
                "scheduler_window_count": 1,
            }
            self.assertEqual(
                harness._row_io_classification(root, segment),
                "compute_bound",
            )
            document["rows"][0]["storage_limited"] = True
            path.write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            segment["scheduler_windows_sha256"] = harness._sha256_file(path)
            self.assertEqual(
                harness._row_io_classification(root, segment),
                "storage_limited",
            )

    def test_terminal_matrix_validation_is_read_only_and_complete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertIsNone(harness._validate_terminal_matrix(root))
            matrix = root / "performance_matrix.json"
            matrix.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "publication is partial",
            ):
                harness._validate_terminal_matrix(root)
            expected = {
                "schema_version": (
                    "dual_frequency_task17_performance_acceptance_v1"
                ),
                "status": "validated",
                "row_count": 72,
            }
            acceptance = root / "performance_acceptance.json"
            acceptance.write_text(
                json.dumps(expected),
                encoding="utf-8",
            )
            with patch(
                "my_helper.fiber.pipelines."
                "validate_task17_performance_acceptance.validate",
                return_value=expected,
            ):
                result = harness._validate_terminal_matrix(root)
            self.assertEqual(result["row_count"], 72)
            acceptance.write_text(
                json.dumps({**expected, "row_count": 71}),
                encoding="utf-8",
            )
            with (
                patch(
                    "my_helper.fiber.pipelines."
                    "validate_task17_performance_acceptance.validate",
                    return_value=expected,
                ),
                self.assertRaisesRegex(
                    harness.PerformanceMatrixHarnessError,
                    "report differs",
                ),
            ):
                harness._validate_terminal_matrix(root)

    def test_public_parser_exposes_resumable_matrix_run(self) -> None:
        arguments = harness._parser().parse_args(
            (
                "run",
                "--request",
                "request.json",
                "--benchmark-root",
                "benchmark",
            )
        )
        self.assertEqual(arguments.operation, "run")

    def test_public_main_dispatches_resumable_matrix_run(self) -> None:
        expected = {
            "status": "completed",
            "matrix_path": "/benchmark/performance_matrix.json",
        }
        with (
            patch.object(
                harness,
                "_run_matrix",
                return_value=expected,
            ) as run_matrix,
            patch("builtins.print") as output,
        ):
            exit_code = harness.main(
                (
                    "run",
                    "--request",
                    "request.json",
                    "--benchmark-root",
                    "benchmark",
                )
            )

        self.assertEqual(exit_code, 0)
        run_matrix.assert_called_once_with(
            Path("request.json"),
            Path("benchmark"),
        )
        self.assertEqual(json.loads(output.call_args.args[0]), expected)

    def test_finished_execution_segment_requires_exactly_one_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "execution_segments").mkdir()
            (root / "run_manifest.json").write_text(
                json.dumps({"final_status": "completed"}),
                encoding="utf-8",
            )
            segment = root / "execution_segments" / "segment_0001.json"
            segment.write_text(
                json.dumps(
                    {
                        "segment_id": "segment_0001",
                        "status": "finished",
                    }
                ),
                encoding="utf-8",
            )
            segment_id, segment_path, document = (
                harness._finished_execution_segment(root)
            )
            self.assertEqual(segment_id, "segment_0001")
            self.assertEqual(segment_path, segment.resolve())
            self.assertEqual(document["status"], "finished")
            (root / "execution_segments" / "segment_0002.json").write_text(
                json.dumps(
                    {
                        "segment_id": "segment_0002",
                        "status": "finished",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "exactly one",
            ):
                harness._finished_execution_segment(root)

    def test_child_execution_environment_is_plan_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            resolved = {
                "execution_environment": {
                    "conda_environment": "leaddbs",
                    "working_directory": str(root),
                }
            }
            self.assertEqual(
                harness._validate_child_execution_environment(
                    resolved,
                    working_directory=root,
                    environment={"CONDA_DEFAULT_ENV": "leaddbs"},
                ),
                {
                    "conda_environment": "leaddbs",
                    "working_directory": str(root),
                },
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "differs",
            ):
                harness._validate_child_execution_environment(
                    resolved,
                    working_directory=root,
                    environment={"CONDA_DEFAULT_ENV": "base"},
                )

    def test_candidate_selected_ids_are_immutable_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "selected.npy"
            values = np.asarray([2, 5, 9], dtype=np.int64)
            self.assertEqual(
                harness._atomic_selected_ids(path, values),
                path.resolve(),
            )
            self.assertTrue(
                np.array_equal(
                    np.load(path, allow_pickle=False),
                    values,
                )
            )
            self.assertEqual(
                harness._atomic_selected_ids(path, values.copy()),
                path.resolve(),
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "differs",
            ):
                harness._atomic_selected_ids(
                    path,
                    np.asarray([2, 6, 9], dtype=np.int64),
                )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "invalid",
            ):
                harness._atomic_selected_ids(
                    Path(temporary) / "unordered.npy",
                    np.asarray([2, 2, 9], dtype=np.int64),
                )

    def test_row_ids_are_stable_and_key_specific(self) -> None:
        first = {
            "benchmark_class": "direct_voxel",
            "connectome_id": None,
            "cache_state": "cold",
            "solver_mode": "none",
            "workers": 1,
        }
        second = {**first, "workers": 3}
        self.assertEqual(
            harness._row_id("a" * 64, first),
            harness._row_id("a" * 64, dict(first)),
        )
        self.assertNotEqual(
            harness._row_id("a" * 64, first),
            harness._row_id("a" * 64, second),
        )

    def test_warm_seed_rows_cover_seven_ordinary_and_one_injected_slice(
        self,
    ) -> None:
        rows = harness._row_keys(("ppmi", "mgh", "dtor"))
        slice_tokens: dict[tuple[str, object, str], str] = {}
        for index, row in enumerate(rows):
            key = (
                str(row["benchmark_class"]),
                row["connectome_id"],
                str(row["solver_mode"]),
            )
            token = slice_tokens.setdefault(
                key,
                f"{len(slice_tokens) + 1:064x}",
            )
            row["slice_id"] = token
            row["row_id"] = f"row_{index:04d}"
            row["planned_status"] = (
                "not_run"
                if row["solver_mode"] == "real_solver"
                else "planned"
            )
        selected = harness._warm_seed_rows({"rows": rows})
        self.assertEqual(len(selected), 8)
        self.assertEqual(
            sum(row["solver_mode"] == "injected" for row in selected),
            1,
        )
        self.assertEqual(
            {int(row["workers"]) for row in selected},
            {1},
        )
        self.assertNotIn(
            "real_cache_hit",
            {row["solver_mode"] for row in selected},
        )

    def test_row_contract_is_immutable_and_attempts_are_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolved = {}
            row = {
                "row_id": "row_123",
                "benchmark_class": "direct_voxel",
                "connectome_id": None,
                "cache_state": "cold",
                "solver_mode": "none",
                "workers": 1,
                "slice_id": "a" * 64,
                "planned_status": "planned",
            }
            contract = harness._row_contract(resolved, row)
            _path, first_sha = harness._ensure_row_contract(root, contract)
            _path, second_sha = harness._ensure_row_contract(root, contract)
            self.assertEqual(first_sha, second_sha)
            first, first_index = harness._next_attempt(root)
            second, second_index = harness._next_attempt(root)
            self.assertEqual(first.name, "attempt_0001")
            self.assertEqual(first_index, 1)
            self.assertEqual(second.name, "attempt_0002")
            self.assertEqual(second_index, 2)
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "immutable benchmark document changed",
            ):
                harness._ensure_row_contract(
                    root,
                    {**contract, "slice_id": "b" * 64},
                )

    def test_terminal_row_rejects_changed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "attempts" / "attempt_0001" / "probe.csv"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("probe\n", encoding="utf-8")
            reference = harness._relative_evidence(
                evidence,
                row_root=root,
            )
            contract_sha = "a" * 64
            (root / "row_result.json").write_text(
                json.dumps(
                    {
                        "schema_version": harness._ROW_RESULT_SCHEMA,
                        "row_id": "row_a",
                        "contract_sha256": contract_sha,
                        "status": "executed",
                        "attempt": 1,
                        "evidence": [reference],
                        "not_run_reason": None,
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNotNone(
                harness._validate_row_result(root, contract_sha)
            )
            evidence.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "evidence SHA differs",
            ):
                harness._validate_row_result(root, contract_sha)

    def test_prepare_publishes_and_validates_all_row_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_identity = "a" * 64
            rows = harness._row_keys(("ppmi", "mgh", "dtor"))
            for row in rows:
                row["slice_id"] = "b" * 64
                row["planned_status"] = (
                    "not_run"
                    if row["solver_mode"] == "real_solver"
                    else "planned"
                )
                row["row_id"] = harness._row_id(plan_identity, row)
            resolved = {
                "schema_version": harness._RESOLVED_SCHEMA,
                "rows": rows,
            }
            closure = harness._row_contract_closure(resolved)
            self.assertEqual(len(closure), 72)
            harness._publish_row_contracts(root, resolved, closure)
            harness._validate_row_contracts(root, resolved, closure)
            authority = root / "authority"
            for name in ("parent", "oss", "work"):
                (authority / name).mkdir(parents=True)
            request = {
                "schema_version": harness._REQUEST_SCHEMA,
                "plan_id": "prepared-plan",
                "accepted_parent_root": str(authority / "parent"),
                "accepted_independent_oss_root": str(authority / "oss"),
                "study_base": str(authority / "study.json"),
                "direct_voxel_model": str(authority / "direct.yaml"),
                "normative_fiber_model": str(authority / "fiber.yaml"),
                "workflow_profile": str(authority / "workflow.yaml"),
                "conda_environment": "leaddbs",
                "working_directory": str(authority / "work"),
                "real_cold_solver_authorization": None,
            }
            for field in (
                "study_base",
                "direct_voxel_model",
                "normative_fiber_model",
                "workflow_profile",
            ):
                Path(request[field]).write_text("{}\n", encoding="utf-8")
            request_path = authority / "request.json"
            request_path.write_text(
                json.dumps(request),
                encoding="utf-8",
            )
            _normalized_request, request_identity = harness._load_request(
                request_path
            )
            parity_root = root / "candidate_parity"
            parity_rows = [
                {"row_id": f"endpoint_{index:04d}"}
                for index in range(224)
            ]
            parity_plan_path = parity_root / "plan.json"
            harness._atomic_json(
                parity_plan_path,
                {
                    "schema_version": (
                        "dual_frequency_candidate_parity_plan_v2"
                    ),
                    "rows": parity_rows,
                },
            )
            parity_report_path = parity_root / "report.json"
            harness._atomic_json(
                parity_report_path,
                {
                    "schema_version": "dual_frequency_candidate_parity_v1",
                    "plan_path": str(parity_plan_path.resolve()),
                    "plan_sha256": harness._sha256_file(parity_plan_path),
                    "row_count": 224,
                    "full_candidate_mismatch_count": 0,
                    "fold_candidate_mismatch_count": 0,
                    "candidate_false_negative_count": 0,
                    "rows": parity_rows,
                },
            )
            marker = {
                "schema_version": harness._MARKER_SCHEMA,
                "plan_id": "prepared-plan",
                "request_sha256": request_identity,
                "resolved_plan_sha256": harness._canonical_sha256(resolved),
                "row_contracts": closure,
                "benchmark_root": str(root.resolve()),
                "candidate_parity": harness._candidate_parity_binding(root),
            }
            harness._atomic_json(
                root / "benchmark_plan_resolved.json",
                resolved,
            )
            harness._atomic_json(root / "benchmark_root.json", marker)
            reopened, reopened_marker = harness._open_prepared_benchmark(
                request_path,
                root,
            )
            self.assertEqual(reopened, resolved)
            self.assertEqual(reopened_marker, marker)
            missing = root / closure[0]["relative_path"]
            missing.unlink()
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "contract differs",
            ):
                harness._validate_row_contracts(root, resolved, closure)

    def test_only_unauthorized_real_cold_solver_can_be_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            row = {
                "row_id": "row_cold_solver",
                "benchmark_class": "ppam",
                "connectome_id": None,
                "cache_state": "cold",
                "solver_mode": "real_solver",
                "workers": 1,
                "planned_status": "not_run",
            }
            authorization = {
                "authorized": False,
                "path": None,
                "sha256": None,
            }
            result = harness._publish_not_run_row(
                root,
                contract_sha256="a" * 64,
                row=row,
                authorization=authorization,
            )
            repeated = harness._publish_not_run_row(
                root,
                contract_sha256="a" * 64,
                row=row,
                authorization=authorization,
            )
            self.assertEqual(result, repeated)
            preflight = json.loads(
                (root / "real_cold_solver_preflight.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIs(preflight["authorized"], False)
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "only an unauthorized",
            ):
                harness._publish_not_run_row(
                    root / "other",
                    contract_sha256="a" * 64,
                    row={**row, "solver_mode": "injected"},
                    authorization=authorization,
                )

    def test_extension_slice_includes_the_base_physical_producer(self) -> None:
        readiness = _task(
            endpoint_id="endpoint_a",
            stage="readiness",
            service_id="validate_reference_fiber_input",
        )
        base = _task(
            endpoint_id="endpoint_a",
            stage="prepare",
            service_id="prepare_reference_fiber_sidecar",
            dependencies=(readiness.task_id,),
        )
        full = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="formal",
            tasks=(readiness, base),
        )
        gate = _task(
            endpoint_id="endpoint_a",
            stage="gate",
            service_id="prepare_oss_omega_max_rows",
        )
        block = _task(
            endpoint_id="endpoint_a",
            stage="block",
            service_id="run_ppam_permutation_block",
            dependencies=(base.task_id,),
        )
        aggregate = _task(
            endpoint_id="endpoint_a",
            stage="aggregate",
            service_id="aggregate_ppam_activation",
            dependencies=(block.task_id, gate.task_id),
        )
        extension = ExecutionPlan(
            configuration_hash="b" * 64,
            scientific_configuration_hash="c" * 64,
            through="sensitivity",
            tasks=(
                replace(
                    base,
                    dependencies=(),
                    gates=(),
                    checkpoint_only=True,
                ),
                gate,
                block,
                aggregate,
            ),
        )
        plan, selected = harness._combined_extension_slice_plan(
            full,
            extension,
            endpoint_id="endpoint_a",
            extension_services={
                "run_ppam_permutation_block",
                "aggregate_ppam_activation",
            },
        )
        self.assertEqual(
            [task.service_id for task in selected],
            [
                "prepare_reference_fiber_sidecar",
                "run_ppam_permutation_block",
                "aggregate_ppam_activation",
            ],
        )
        descriptor = harness._slice_descriptor(
            plan,
            selected,
            parent_completed={readiness.task_id},
            oss_completed={gate.task_id},
            label="ppam",
        )
        self.assertEqual(
            descriptor["imported_parent_task_ids"],
            [readiness.task_id],
        )
        self.assertEqual(
            descriptor["imported_oss_task_ids"],
            [gate.task_id],
        )
        self.assertEqual(
            len(descriptor["execution_plan"]["tasks"]),
            len(plan.tasks),
        )
        measured_gate_plan, measured_gate_tasks = (
            harness._combined_extension_slice_plan(
                full,
                extension,
                endpoint_id="endpoint_a",
                extension_services=harness._PPAM_SERVICES,
            )
        )
        self.assertIn(
            "prepare_oss_omega_max_rows",
            {task.service_id for task in measured_gate_tasks},
        )
        measured_gate_descriptor = harness._slice_descriptor(
            measured_gate_plan,
            measured_gate_tasks,
            parent_completed={readiness.task_id},
            oss_completed=set(),
            label="ppam:injected",
        )
        self.assertEqual(
            measured_gate_descriptor["imported_oss_task_ids"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
