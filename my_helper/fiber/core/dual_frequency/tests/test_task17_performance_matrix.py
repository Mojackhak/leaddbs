"""Tests for immutable Task 17 performance benchmark preparation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dual_frequency.contracts import TaskKey
from dual_frequency.workflow import ExecutionPlan, TaskSpec
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
        output_record_type="SyntheticRecord",
    )


class Task17PerformanceMatrixTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
