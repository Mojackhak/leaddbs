"""Tests for Task 17 live and terminal byte-ledger provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dual_frequency.instrumentation import _EVENTS, _KEYED_EVENTS
from my_helper.fiber.pipelines import build_task17_performance_byte_ledger
from my_helper.fiber.pipelines.task17_performance_byte_ledger import (
    PerformanceByteLedgerError,
    aggregate_live_index,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Task17PerformanceByteLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "run"
        self.segment_id = "segment_0001"
        self.fragment = (
            self.run
            / "work"
            / "task_one"
            / "attempt-one"
            / "performance_counter_fragment.json"
        )
        scalars = {
            event: 0 for event in sorted(_EVENTS - _KEYED_EVENTS)
        }
        scalars["source_bytes"] = 13
        scalars["scratch_bytes"] = 29
        _write(
            self.fragment,
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
            },
        )
        self.event = (
            self.run
            / "execution_segments"
            / f"performance_events_{self.segment_id}.json"
        )
        _write(
            self.event,
            {
                "schema_version": (
                    "dual_frequency_performance_event_report_v1"
                ),
                "segment_id": self.segment_id,
                "aggregation_status": "complete",
                "fragment_count": 1,
                "missing_fragment_count": 0,
                "fragments": [
                    {
                        "task_id": "task_one",
                        "process_identity": "process-one",
                        "path": str(self.fragment),
                        "sha256": _sha(self.fragment),
                    }
                ],
            },
        )
        self.segment = (
            self.run / "execution_segments" / f"{self.segment_id}.json"
        )
        _write(
            self.segment,
            {
                "segment_id": self.segment_id,
                "status": "finished",
                "performance_events_path": str(
                    self.event.relative_to(self.run)
                ),
                "performance_events_sha256": _sha(self.event),
            },
        )
        _write(
            self.run / "run_manifest.json",
            {"run_id": "benchmark-run", "final_status": "completed"},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_live_index_and_terminal_builder_match(self) -> None:
        index = self.root / "index.json"
        _write(
            index,
            {
                "schema_version": (
                    "dual_frequency_performance_byte_ledger_index_v1"
                ),
                "run_root": str(self.run),
            },
        )
        live = aggregate_live_index(index)
        output = self.root / "ledger.json"
        first = build_task17_performance_byte_ledger.build(
            run_root=self.run,
            segment_id=self.segment_id,
            output=output,
        )
        document = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(live["source_bytes"], document["source_bytes"])
        self.assertEqual(live["scratch_bytes"], document["scratch_bytes"])
        self.assertEqual(
            build_task17_performance_byte_ledger.build(
                run_root=self.run,
                segment_id=self.segment_id,
                output=output,
            ),
            output.resolve(),
        )

    def test_terminal_builder_rejects_fragment_sha_change(self) -> None:
        self.fragment.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            PerformanceByteLedgerError,
            "SHA differs",
        ):
            build_task17_performance_byte_ledger.build(
                run_root=self.run,
                segment_id=self.segment_id,
                output=self.root / "ledger.json",
            )


if __name__ == "__main__":
    unittest.main()
