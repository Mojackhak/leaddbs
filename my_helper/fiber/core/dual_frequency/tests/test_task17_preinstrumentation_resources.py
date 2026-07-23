"""Tests for pre-instrumentation Task 17 resource acceptance."""

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
    / "validate_task17_preinstrumentation_resources.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_task17_preinstrumentation_resources",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load pre-instrumentation resource validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task_id(key: dict[str, str]) -> str:
    payload = json.dumps(
        key,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"task_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


class Task17PreinstrumentationResourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "resource-run"
        self.cache = base / "cache"
        self.guard = base / "guard.csv"
        self.windows = base / "windows.json"
        self.segment = self.root / "execution_segments" / "segment_0010.json"
        self._build_valid_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _cache_entry(
        self,
        kind: str,
        identity: str,
        payloads: dict[str, bytes],
    ) -> None:
        root = self.cache / "shared_exposure_v2" / kind / identity
        root.mkdir(parents=True)
        files = []
        for relative, data in sorted(payloads.items()):
            path = root / relative
            path.write_bytes(data)
            files.append(
                {
                    "relative_path": relative,
                    "sha256": _sha256(path),
                    "size_bytes": len(data),
                    "metadata": {},
                }
            )
        _write_json(
            root / "manifest.json",
            {
                "schema_version": "scientific_cache_entry_v2",
                "completed": True,
                "scientific_identity": identity,
                "scientific_cache_key": {
                    "kind": kind,
                },
                "files": files,
                "items": [],
            },
        )

    def _row(self, identity: str, n_fibers: int) -> None:
        metadata = (
            json.dumps(
                {
                    "schema_version": "dual_frequency_oss_row_v2",
                    "scientific_identity": identity,
                    "n_fibers": n_fibers,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        self._cache_entry(
            "oss_rows",
            identity,
            {
                "fiber_ids.npy": b"ids",
                "probabilities.npy": b"probabilities",
                "row_metadata.json": metadata,
            },
        )

    def _decision(
        self,
        identity: str,
        group_id: str,
        final_row: str,
        omega_row: str,
    ) -> None:
        payload = (
            json.dumps(
                {
                    "schema_version": "dual_frequency_oss_axis_decision_v1",
                    "decision_id": identity,
                    "group_id": group_id,
                    "status": "pass",
                    "final_row_identity": final_row,
                    "omega_row_identity": omega_row,
                    "state_mismatch_count": 0,
                    "activation_count_mismatch_count": 0,
                    "max_probability_difference": 0.0,
                    "probability_tolerance": 0.0,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        self._cache_entry(
            "oss_axis_equivalence",
            identity,
            {"decision.json": payload},
        )

    def _build_valid_fixture(self) -> None:
        _write_json(
            self.root / "run_manifest.json",
            {
                "run_id": self.root.name,
                "final_status": "completed",
            },
        )
        _write_json(
            self.segment,
            {
                "schema_version": "dual_frequency_execution_segment_v1",
                "segment_id": "segment_0010",
                "status": "finished",
                "pool_mode": "spawn_process",
                "workers": 14,
                "started_at": "2026-07-22T00:00:00+00:00",
                "finished_at": "2026-07-22T00:00:10+00:00",
            },
        )
        groups = ("oss_axis_group_reference", "oss_axis_group_addon")
        decisions = ("1" * 64, "2" * 64)
        rows = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
        tasks = []
        for index, (group, decision) in enumerate(zip(groups, decisions, strict=True)):
            key = {
                "endpoint_id": f"endpoint_gate_{index}",
                "stage": f"oss_axis_equivalence_{index}",
                "branch": "none",
                "parameter_identity": str(index + 1) * 64,
            }
            task_id = _task_id(key)
            tasks.append(
                {
                    "key": key,
                    "service_id": "establish_oss_axis_equivalence",
                }
            )
            _write_json(
                self.root / "tasks" / f"{task_id}.json",
                {
                    "task_id": task_id,
                    "status": "completed",
                    "reason": "none",
                    "result": {
                        "output_record_type": "OSSAxisEquivalenceGroupRecord",
                        "payload": {
                            "group_id": group,
                            "gate_status": "accepted_omega_max",
                            "row_decision_ids": [decision],
                        },
                    },
                },
            )
        _write_json(
            self.root / "sensitivity_plan.json",
            {"plan": {"tasks": tasks}},
        )
        for row, count in zip(rows, (5, 10, 6, 9), strict=True):
            self._row(row, count)
        self._decision(decisions[0], groups[0], rows[0], rows[1])
        self._decision(decisions[1], groups[1], rows[2], rows[3])
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
            writer.writerows(
                [
                    {
                        "timestamp_utc": "2026-07-22T00:00:02+00:00",
                        "tree_rss_bytes": 10,
                        "peak_tree_rss_bytes": 10,
                        "tree_cpu_percent": 50,
                        "swap_used_bytes": 100,
                        "swap_baseline_bytes": 100,
                        "event": "sample",
                    },
                    {
                        "timestamp_utc": "2026-07-22T00:00:03+00:00",
                        "tree_rss_bytes": 20,
                        "peak_tree_rss_bytes": 20,
                        "tree_cpu_percent": 70,
                        "swap_used_bytes": 99,
                        "swap_baseline_bytes": 100,
                        "event": "sample",
                    },
                    {
                        "timestamp_utc": "2026-07-22T00:00:05+00:00",
                        "tree_rss_bytes": 5,
                        "peak_tree_rss_bytes": 5,
                        "tree_cpu_percent": 10,
                        "swap_used_bytes": 200,
                        "swap_baseline_bytes": 200,
                        "event": "sample",
                    },
                ]
            )
        _write_json(
            self.windows,
            {
                "schema_version": (
                    "dual_frequency_task17_preinstrumentation_windows_v1"
                ),
                "run_id": self.root.name,
                "windows": [
                    {
                        "decision_id": decisions[0],
                        "row_identity": rows[1],
                        "start_utc": "2026-07-22T00:00:02+00:00",
                        "finish_utc": "2026-07-22T00:00:03+00:00",
                        "guard_epoch_swap_baseline_bytes": 100,
                        "peak_task_tree_rss_bytes": 20,
                    }
                ],
            },
        )

    def _validate(self) -> dict[str, object]:
        return validator.validate(
            self.root,
            "segment_0010",
            self.cache,
            self.guard,
            self.windows,
            workers=14,
            max_rss_bytes=64 * 1024**3,
        )

    def test_valid_terminal_closure_and_window_pass(self) -> None:
        report = self._validate()
        self.assertEqual(report["status"], "validated")
        self.assertFalse(report["continuous_full_span_monitoring"])
        self.assertEqual(report["oss_closure"]["maximum_n_fibers"], 10)
        self.assertEqual(len(report["uncovered_elapsed_intervals"]), 2)
        output = Path(self.temporary.name) / "report.json"
        validator._write_report(output, report)
        validator._write_report(output, report)

    def test_nonmaximum_row_window_fails(self) -> None:
        document = json.loads(self.windows.read_text(encoding="utf-8"))
        document["windows"][0]["row_identity"] = "a" * 64
        _write_json(self.windows, document)
        with self.assertRaisesRegex(
            validator.PreinstrumentationResourceError,
            "terminal maximum row",
        ):
            self._validate()

    def test_window_peak_mismatch_fails(self) -> None:
        document = json.loads(self.windows.read_text(encoding="utf-8"))
        document["windows"][0]["peak_task_tree_rss_bytes"] = 19
        _write_json(self.windows, document)
        with self.assertRaisesRegex(
            validator.PreinstrumentationResourceError,
            "RSS peak differs",
        ):
            self._validate()

    def test_failed_gate_decision_fails(self) -> None:
        path = (
            self.cache
            / "shared_exposure_v2"
            / "oss_axis_equivalence"
            / ("1" * 64)
            / "decision.json"
        )
        path.write_bytes(path.read_bytes().replace(b'"pass"', b'"fail"'))
        with self.assertRaisesRegex(
            validator.PreinstrumentationResourceError,
            "payload SHA-256 differs",
        ):
            self._validate()

    def test_derived_task_identity_mismatch_fails(self) -> None:
        plan_path = self.root / "sensitivity_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        key = plan["plan"]["tasks"][0]["key"]
        task_id = _task_id(key)
        task_path = self.root / "tasks" / f"{task_id}.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["task_id"] = "task_wrong"
        _write_json(task_path, task)
        with self.assertRaisesRegex(
            validator.PreinstrumentationResourceError,
            "task identity differs",
        ):
            self._validate()

    def test_instrumented_segment_is_rejected(self) -> None:
        segment = json.loads(self.segment.read_text(encoding="utf-8"))
        segment["resource_sample_count"] = 1
        _write_json(self.segment, segment)
        with self.assertRaisesRegex(
            validator.PreinstrumentationResourceError,
            "strict resource validator",
        ):
            self._validate()


if __name__ == "__main__":
    unittest.main()
