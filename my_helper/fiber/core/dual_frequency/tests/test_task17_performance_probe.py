"""Tests for Task 17 cumulative CPU-time benchmark evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from dual_frequency.instrumentation import _EVENTS, _KEYED_EVENTS
from my_helper.fiber.pipelines.run_task17_performance_probe import (
    PerformanceProbeError,
    ProcessSample,
    _byte_counters,
    run_probe,
)


class Task17PerformanceProbeTest(unittest.TestCase):
    def test_live_index_derives_atomic_fragment_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            fragment = (
                run
                / "work"
                / "task_one"
                / "attempt-one"
                / "performance_counter_fragment.json"
            )
            fragment.parent.mkdir(parents=True)
            scalars = {
                event: 0 for event in sorted(_EVENTS - _KEYED_EVENTS)
            }
            scalars["source_bytes"] = 31
            scalars["scratch_bytes"] = 47
            fragment.write_text(
                json.dumps(
                    {
                        "schema_version": (
                            "dual_frequency_performance_counter_fragment_v1"
                        ),
                        "process_identity": "process-one",
                        "task_id": "task_one",
                        "events": {
                            "process_identity": "process-one",
                            "scalars": scalars,
                            "keyed": {
                                event: {} for event in sorted(_KEYED_EVENTS)
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            index = root / "byte-index.json"
            index.write_text(
                json.dumps(
                    {
                        "schema_version": (
                            "dual_frequency_performance_byte_ledger_index_v1"
                        ),
                        "run_root": str(run),
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(_byte_counters(index), (31, 47))

    def test_retired_process_cpu_remains_in_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counter = root / "counters.json"
            counter.write_text(
                json.dumps({"source_bytes": 10, "scratch_bytes": 20}),
                encoding="utf-8",
            )
            snapshots = [
                (
                    ProcessSample(100, 1.0, 100, 1.0),
                    ProcessSample(101, 2.0, 200, 2.0),
                ),
                (ProcessSample(100, 1.0, 120, 1.5),),
                (),
            ]
            monotonic = iter((10.0, 10.0, 11.0, 12.0))
            status = run_probe(
                runner_pid=100,
                output=root / "probe.csv",
                byte_counter_path=counter,
                guarded_roots=(root / "VAL",),
                process_reader=lambda _pid: snapshots.pop(0),
                swap_reader=lambda: 7,
                monotonic_reader=lambda: next(monotonic),
                timestamp_reader=lambda: "2026-07-24T00:00:00+00:00",
                sleeper=lambda _seconds: None,
            )
            with (root / "probe.csv").open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(status, 0)
        self.assertEqual(
            [float(row["aggregate_cpu_seconds"]) for row in rows],
            [3.0, 3.5, 3.5],
        )
        self.assertEqual(rows[-1]["event"], "runner_exit")
        self.assertEqual(rows[0]["source_bytes"], "10")
        self.assertEqual(rows[0]["scratch_bytes"], "20")

    def test_output_inside_guarded_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counter = root / "counters.json"
            counter.write_text(
                json.dumps({"source_bytes": 0, "scratch_bytes": 0}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PerformanceProbeError,
                "outside guarded",
            ):
                run_probe(
                    runner_pid=100,
                    output=root / "VAL" / "probe.csv",
                    byte_counter_path=counter,
                    guarded_roots=(root / "VAL",),
                    process_reader=lambda _pid: (),
                    swap_reader=lambda: 0,
                )

    def test_decreasing_cpu_counter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counter = root / "counters.json"
            counter.write_text(
                json.dumps({"source_bytes": 0, "scratch_bytes": 0}),
                encoding="utf-8",
            )
            snapshots = [
                (ProcessSample(100, 1.0, 100, 2.0),),
                (ProcessSample(100, 1.0, 100, 1.0),),
            ]
            with self.assertRaisesRegex(
                PerformanceProbeError,
                "CPU time decreased",
            ):
                run_probe(
                    runner_pid=100,
                    output=root / "probe.csv",
                    byte_counter_path=counter,
                    guarded_roots=(root / "VAL",),
                    process_reader=lambda _pid: snapshots.pop(0),
                    swap_reader=lambda: 0,
                    sleeper=lambda _seconds: None,
                )


if __name__ == "__main__":
    unittest.main()
