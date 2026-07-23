"""Tests for terminal Task 17 resource acceptance validation."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "pipelines"
    / "validate_task17_resource_acceptance.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_task17_resource_acceptance",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Task 17 resource acceptance validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _task_id(key: dict[str, str]) -> str:
    payload = json.dumps(
        key,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"task_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


class Task17ResourceAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "resource-run"
        self.task_keys = tuple(
            {
                "endpoint_id": f"endpoint_{index}",
                "stage": f"stage_{index}",
                "branch": "none",
                "parameter_identity": str(index + 1) * 64,
            }
            for index in range(2)
        )
        self.tasks = tuple(_task_id(key) for key in self.task_keys)
        self.guard = Path(self.temporary.name) / "guard.csv"
        self.segment_path = (
            self.root / "execution_segments" / "segment_0002.json"
        )
        self._build_valid_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build_valid_fixture(self) -> None:
        _write_json(
            self.root / "run_manifest.json",
            {
                "run_id": self.root.name,
                "final_status": "completed",
                "plan_hash": "a" * 64,
            },
        )
        _write_json(
            self.root / "sensitivity_plan.json",
            {
                "plan": {
                    "tasks": [
                        {"key": key}
                        for key in self.task_keys
                    ]
                }
            },
        )
        for task_id in self.tasks:
            _write_json(
                self.root / "tasks" / f"{task_id}.json",
                {
                    "task_id": task_id,
                    "status": "completed",
                    "reason": "none",
                },
            )
        _write_json(
            self.segment_path,
            {
                "schema_version": "dual_frequency_execution_segment_v1",
                "segment_id": "segment_0002",
                "status": "finished",
                "pool_mode": "spawn_process",
                "workers": 14,
                "blas_threads_per_worker": 1,
                "external_solver_slots": 1,
                "pool_generation_count": 1,
                "resource_sample_count": 100,
                "peak_task_tree_rss_bytes": 48 * 1024**3,
                "peak_swap_delta_bytes": 0,
                "swap_delta_bytes": 0,
                "peak_reserved_cpu_slots": 14,
                "peak_reserved_external_solver_slots": 1,
                "task_timeout_count": 0,
                "broken_pool_count": 0,
                "transient_retry_count": 0,
                "restored_task_count": 1,
                "scheduled_task_count": 1,
                "terminal_task_count": 2,
            },
        )
        self._write_guard(
            [
                {
                    "timestamp_utc": "2026-07-22T00:00:00+00:00",
                    "tree_rss_bytes": 10,
                    "peak_tree_rss_bytes": 10,
                    "tree_cpu_percent": 50.0,
                    "swap_used_bytes": 100,
                    "swap_baseline_bytes": 100,
                    "event": "sample",
                },
                {
                    "timestamp_utc": "2026-07-22T00:00:01+00:00",
                    "tree_rss_bytes": 20,
                    "peak_tree_rss_bytes": 20,
                    "tree_cpu_percent": 75.0,
                    "swap_used_bytes": 99,
                    "swap_baseline_bytes": 100,
                    "event": "sample",
                },
                {
                    "timestamp_utc": "2026-07-22T00:00:03+00:00",
                    "tree_rss_bytes": 5,
                    "peak_tree_rss_bytes": 5,
                    "tree_cpu_percent": 10.0,
                    "swap_used_bytes": 200,
                    "swap_baseline_bytes": 200,
                    "event": "runner_exited",
                },
            ]
        )

    def _write_guard(self, rows: list[dict[str, object]]) -> None:
        fields = (
            "timestamp_utc",
            "tree_rss_bytes",
            "peak_tree_rss_bytes",
            "tree_cpu_percent",
            "swap_used_bytes",
            "swap_baseline_bytes",
            "event",
        )
        with self.guard.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _validate(self) -> dict[str, object]:
        return validator.validate(
            self.root,
            "segment_0002",
            self.guard,
            workers=14,
            max_rss_bytes=64 * 1024**3,
        )

    def test_valid_multi_epoch_guard_and_same_byte_report_pass(self) -> None:
        report = self._validate()
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["guard"]["epoch_count"], 2)
        self.assertEqual(report["tasks"]["task_count"], 2)
        output = Path(self.temporary.name) / "report.json"
        validator._write_report(output, report)
        validator._write_report(output, report)

    def test_segment_rss_ceiling_fails(self) -> None:
        segment = json.loads(self.segment_path.read_text(encoding="utf-8"))
        segment["peak_task_tree_rss_bytes"] = 64 * 1024**3
        _write_json(self.segment_path, segment)
        with self.assertRaisesRegex(
            validator.ResourceAcceptanceError,
            "RSS reached",
        ):
            self._validate()

    def test_guard_swap_growth_fails(self) -> None:
        with self.guard.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["swap_used_bytes"] = "101"
        self._write_guard(rows)
        with self.assertRaisesRegex(
            validator.ResourceAcceptanceError,
            "swap growth",
        ):
            self._validate()

    def test_terminal_task_mismatch_fails(self) -> None:
        path = self.root / "tasks" / f"{self.tasks[1]}.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        task["status"] = "skipped"
        task["reason"] = "dependency_failed"
        _write_json(path, task)
        with self.assertRaisesRegex(
            validator.ResourceAcceptanceError,
            "not completed",
        ):
            self._validate()

    def test_guard_stop_event_fails(self) -> None:
        with self.guard.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[-1]["event"] = "stop_swap_growth"
        self._write_guard(rows)
        with self.assertRaisesRegex(
            validator.ResourceAcceptanceError,
            "stop or unsupported",
        ):
            self._validate()

    def test_derived_task_identity_mismatch_fails(self) -> None:
        path = self.root / "tasks" / f"{self.tasks[1]}.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        task["task_id"] = "task_wrong"
        _write_json(path, task)
        with self.assertRaisesRegex(
            validator.ResourceAcceptanceError,
            "task identity differs",
        ):
            self._validate()


if __name__ == "__main__":
    unittest.main()
