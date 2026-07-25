"""Tests for immutable Task 17 performance benchmark preparation."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

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
    OSSAxisEquivalenceGroupRecord,
    TaskKey,
)
from dual_frequency.workflow import ExecutionPlan, ServiceResult, TaskSpec
from my_helper.fiber.pipelines import run_task17_performance_matrix as harness


class _Process:
    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


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
            toolchain = harness._AcceptedOSSInjectedToolchain(
                cache_root=cache.root,
                accepted_row_identities=(identity,),
            )
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
                harness.PerformanceMatrixHarnessError,
                "outside the accepted row closure",
            ):
                toolchain.produce_with_evidence(
                    SimpleNamespace(
                        scientific_identity="0" * 64,
                        row=row,
                    )
                )

    def test_accepted_oss_cache_closure_binds_only_gate_referenced_rows(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            final_axis = AxisRef("final-axis", 2, "1" * 64)
            omega_axis = AxisRef("omega-axis", 3, "2" * 64)
            _final_row, final_identity = self._publish_oss_row(
                root=root,
                cache=cache,
                name="final",
                axis=final_axis,
                ids=np.asarray([2, 3], dtype=np.int64),
                probabilities=np.asarray([0.3, 0.8], dtype=np.float32),
            )
            _omega_row, omega_identity = self._publish_oss_row(
                root=root,
                cache=cache,
                name="omega",
                axis=omega_axis,
                ids=np.asarray([1, 2, 3], dtype=np.int64),
                probabilities=np.asarray([0.1, 0.3, 0.8], dtype=np.float32),
            )
            decision_key = ScientificCacheKey(
                geometry_hash=final_identity,
                stimulation_hash=omega_identity,
                component_frequency_hash="3" * 64,
                transform_hash="4" * 64,
                connectome_feature_hash="5" * 64,
                backend_name="oss_axis_equivalence",
                backend_version="1",
                scientific_parameter_hashes=(
                    ("final_row", final_identity),
                    ("omega_row", omega_identity),
                ),
                kind="oss_axis_equivalence",
            )
            decision_path = root / "decision.json"
            decision_path.write_text(
                json.dumps(
                    {
                        "schema_version": (
                            "dual_frequency_oss_axis_decision_v1"
                        ),
                        "decision_id": decision_key.digest,
                        "group_id": "reference-group",
                        "status": "pass",
                        "final_row_identity": final_identity,
                        "omega_row_identity": omega_identity,
                        "state_mismatch_count": 0,
                        "activation_count_mismatch_count": 0,
                        "max_probability_difference": 0.0,
                        "probability_tolerance": 1e-7,
                    }
                ),
                encoding="utf-8",
            )
            cache.publish(
                decision_key,
                {"decision.json": decision_path},
            )
            record = OSSAxisEquivalenceGroupRecord(
                group_id="reference-group",
                model_family="reference_fiber",
                gate_status="accepted_omega_max",
                final_feature_axis=final_axis,
                omega_feature_axis=omega_axis,
                omega_cache_kind="fiber_exposures",
                omega_cache_semantic_sha256="6" * 64,
                endpoint_ids=("endpoint-a",),
                row_decision_ids=(decision_key.digest,),
            )
            closure = harness._accepted_oss_cache_closure(
                (("task_gate", record),),
                cache_root=cache.root,
            )
            self.assertEqual(
                [row["scientific_identity"] for row in closure["rows"]],
                sorted((final_identity, omega_identity)),
            )
            self.assertEqual(
                closure["groups"][0]["decision_ids"],
                [decision_key.digest],
            )
            descriptors = harness._accepted_oss_cache_entry_descriptors(
                closure
            )
            seed = harness._copy_verified_cache_entries(
                source_cache_root=cache.root,
                destination_cache_root=root / "row-cache",
                entries=descriptors,
            )
            self.assertEqual(len(seed["entries"]), 3)
            copied_cache = ContentAddressedCache(root / "row-cache")
            self.assertIsNotNone(
                copied_cache.resolve_identity(
                    "oss_axis_equivalence",
                    decision_key.digest,
                )
            )
            fixture = harness._prepare_injected_oss_fixture(
                accepted_closure=closure,
                destination_cache_root=root / "injected-fixture",
            )
            self.assertEqual(len(fixture["permitted_row_identities"]), 2)
            fixture_cache = ContentAddressedCache(
                root / "injected-fixture"
            )
            self.assertIsNone(
                fixture_cache.resolve_identity(
                    "oss_axis_equivalence",
                    decision_key.digest,
                )
            )
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "destination must be empty",
            ):
                harness._copy_verified_cache_entries(
                    source_cache_root=cache.root,
                    destination_cache_root=root / "row-cache",
                    entries=descriptors,
                )

    def test_accepted_oss_gate_records_require_both_fiber_families(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks_root = root / "tasks"
            tasks_root.mkdir()
            axis = AxisRef("fiber-axis", 2, "1" * 64)
            for family in ("reference_fiber", "addon_fiber"):
                record = OSSAxisEquivalenceGroupRecord(
                    group_id=f"{family}-group",
                    model_family=family,
                    gate_status="accepted_omega_max",
                    final_feature_axis=axis,
                    omega_feature_axis=axis,
                    omega_cache_kind="fiber_exposures",
                    omega_cache_semantic_sha256="2" * 64,
                    endpoint_ids=(f"{family}-endpoint",),
                    row_decision_ids=(f"{family}-decision",),
                )
                task_id = f"task_{family}"
                (tasks_root / f"{task_id}.json").write_text(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "endpoint_id": f"{family}-endpoint",
                            "service_id": "establish_oss_axis_equivalence",
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
            records = harness._accepted_oss_gate_records(root)
            self.assertEqual(
                {record.model_family for _, record in records},
                {"reference_fiber", "addon_fiber"},
            )
            (tasks_root / "task_addon_fiber.json").unlink()
            with self.assertRaisesRegex(
                harness.PerformanceMatrixHarnessError,
                "exact two fiber gate records",
            ):
                harness._accepted_oss_gate_records(root)

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
                "omega_max": {"axis_count": 90},
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
            service_id="establish_oss_axis_equivalence",
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
        record = OSSAxisEquivalenceGroupRecord(
            group_id="checkpoint-group",
            model_family="reference_fiber",
            gate_status="accepted_omega_max",
            final_feature_axis=axis,
            omega_feature_axis=axis,
            omega_cache_kind="fiber_exposures",
            omega_cache_semantic_sha256="2" * 64,
            endpoint_ids=("endpoint_a",),
            row_decision_ids=("decision-a",),
        )
        parent = _task(
            endpoint_id="endpoint_a",
            stage="parent",
            service_id="establish_oss_axis_equivalence",
            output_record_type="OSSAxisEquivalenceGroupRecord",
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
            parent_completed={parent.task_id},
            oss_completed=set(),
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
            (parent_root / "tasks" / f"{parent.task_id}.json").write_text(
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
        payload["tasks"][0]["unexpected"] = True
        with self.assertRaisesRegex(
            harness.PerformanceMatrixHarnessError,
            "task fields differ",
        ):
            harness._execution_plan_from_payload(payload)
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
                "maximum_task_tree_rss_bytes": 64 * 1024**3,
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

    def test_row_contract_is_immutable_and_attempts_are_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolved = {"maximum_task_tree_rss_bytes": 64 * 1024**3}
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
                "maximum_task_tree_rss_bytes": 64 * 1024**3,
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
                "maximum_task_tree_rss_bytes": 64 * 1024**3,
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
            marker = {
                "schema_version": harness._MARKER_SCHEMA,
                "plan_id": "prepared-plan",
                "request_sha256": harness._sha256_file(request_path),
                "resolved_plan_sha256": harness._canonical_sha256(resolved),
                "row_contracts": closure,
                "benchmark_root": str(root.resolve()),
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
            service_id="establish_oss_axis_equivalence",
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
            "establish_oss_axis_equivalence",
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
