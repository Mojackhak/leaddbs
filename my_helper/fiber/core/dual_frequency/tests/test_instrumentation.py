"""Tests for process-local performance instrumentation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dual_frequency.instrumentation import (
    PerformanceInstrumentationError,
    aggregate_performance_fragments,
    increment_performance_event,
    performance_delta,
    performance_snapshot,
    write_performance_fragment,
)
from dual_frequency.runtime.input_provider import StudyRuntimeInputProvider


class PerformanceInstrumentationTests(unittest.TestCase):
    """Verify event deltas, immutable fragments, and parent aggregation."""

    def test_scalar_and_keyed_deltas_are_exact(self) -> None:
        before = performance_snapshot()
        increment_performance_event("payload_read_bytes", amount=17)
        increment_performance_event(
            "cache_full_verification",
            key="fiber_exposures:abc",
        )
        delta = performance_delta(before, performance_snapshot())
        self.assertEqual(delta["scalars"]["payload_read_bytes"], 17)
        self.assertEqual(
            delta["keyed"]["cache_full_verification"],
            {"fiber_exposures:abc": 1},
        )

    def test_invalid_event_and_cross_process_snapshot_fail(self) -> None:
        with self.assertRaises(PerformanceInstrumentationError):
            increment_performance_event("not_declared")
        before = performance_snapshot()
        after = performance_snapshot()
        after["process_identity"] = "another-process"
        with self.assertRaises(PerformanceInstrumentationError):
            performance_delta(before, after)

    def test_fragment_is_immutable_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory) / "attempt"
            before = performance_snapshot()
            increment_performance_event("payload_write_bytes", amount=23)
            after = performance_snapshot()
            path = write_performance_fragment(
                attempt,
                task_id="task_one",
                before=before,
                after=after,
            )
            self.assertEqual(
                write_performance_fragment(
                    attempt,
                    task_id="task_one",
                    before=before,
                    after=after,
                ),
                path,
            )
            report = aggregate_performance_fragments(
                [{"task_id": "task_one", "output_dir": str(attempt)}]
            )
            self.assertEqual(report["aggregation_status"], "complete")
            self.assertEqual(report["fragment_count"], 1)
            self.assertEqual(
                report["events"]["scalars"]["payload_write_bytes"],
                23,
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            document["task_id"] = "changed"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(PerformanceInstrumentationError):
                aggregate_performance_fragments(
                    [{"task_id": "task_one", "output_dir": str(attempt)}]
                )

    def test_missing_fragment_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = aggregate_performance_fragments(
                [{"task_id": "task_missing", "output_dir": directory}]
            )
        self.assertEqual(report["aggregation_status"], "incomplete")
        self.assertEqual(report["missing_fragment_count"], 1)
        self.assertEqual(report["events"]["scalars"]["payload_hash_bytes"], 0)

    def test_hot_loop_guard_records_metadata_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(b"payload")
            before = performance_snapshot()
            with StudyRuntimeInputProvider._hot_loop_guard():
                StudyRuntimeInputProvider._file_signature(path)
            delta = performance_delta(before, performance_snapshot())
        self.assertEqual(
            sum(delta["keyed"]["hot_loop_metadata_work"].values()),
            1,
        )


if __name__ == "__main__":
    unittest.main()
