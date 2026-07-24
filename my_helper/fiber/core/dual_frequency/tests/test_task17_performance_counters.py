"""Tests for deterministic Task 17 performance-counter derivation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dual_frequency.instrumentation import _EVENTS, _KEYED_EVENTS
from my_helper.fiber.pipelines import build_task17_performance_counters as builder


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events() -> dict[str, object]:
    return {
        "process_identity": "process-one",
        "scalars": {
            event: 0 for event in sorted(_EVENTS - _KEYED_EVENTS)
        },
        "keyed": {event: {} for event in sorted(_KEYED_EVENTS)},
    }


class Task17PerformanceCounterBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "run"
        self.segment_id = "segment_0001"
        self.identity = "fiber_exposures:" + "a" * 64
        self._build_evidence()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build_evidence(self) -> None:
        _write(
            self.run / "run_manifest.json",
            {"run_id": "benchmark-run", "final_status": "completed"},
        )
        fragment_events = _events()
        fragment_events["scalars"]["memmap_flush"] = 2
        fragment_events["scalars"]["source_bytes"] = 11
        fragment_events["scalars"]["scratch_bytes"] = 22
        fragment_events["keyed"]["physical_cache_use"] = {self.identity: 1}
        fragment_events["keyed"]["physical_producer"] = {self.identity: 1}
        fragment_events["keyed"]["cache_resolve"] = {self.identity: 2}
        fragment_events["keyed"]["cache_full_verification"] = {
            self.identity: 1
        }
        fragment = self.run / "work" / "task_one" / "attempt-one"
        fragment_path = fragment / "performance_counter_fragment.json"
        _write(
            fragment_path,
            {
                "schema_version": (
                    "dual_frequency_performance_counter_fragment_v1"
                ),
                "process_identity": "process-one",
                "task_id": "task_one",
                "events": fragment_events,
            },
        )
        aggregate = {
            "scalars": dict(fragment_events["scalars"]),
            "keyed": {
                event: dict(values)
                for event, values in fragment_events["keyed"].items()
            },
        }
        parent = _events()
        parent["process_identity"] = "parent-process"
        event_path = (
            self.run
            / "execution_segments"
            / f"performance_events_{self.segment_id}.json"
        )
        _write(
            event_path,
            {
                "schema_version": (
                    "dual_frequency_performance_event_report_v1"
                ),
                "segment_id": self.segment_id,
                "aggregation_status": "complete",
                "scheduled_attempt_count": 1,
                "fragment_count": 1,
                "missing_fragment_count": 0,
                "fragments": [
                    {
                        "task_id": "task_one",
                        "process_identity": "process-one",
                        "path": str(fragment_path),
                        "sha256": _sha(fragment_path),
                    }
                ],
                "missing_fragments": [],
                "events": aggregate,
                "parent_events": parent,
            },
        )
        segment_path = (
            self.run / "execution_segments" / f"{self.segment_id}.json"
        )
        _write(
            segment_path,
            {
                "schema_version": "dual_frequency_execution_segment_v1",
                "segment_id": self.segment_id,
                "status": "finished",
                "task_timeout_count": 0,
                "transient_retry_count": 0,
                "performance_events_path": str(event_path.relative_to(self.run)),
                "performance_events_sha256": _sha(event_path),
            },
        )
        ledger = self.root / "byte-ledger.json"
        parity = self.root / "candidate-parity.json"
        audit = self.root / "artifact-audit.json"
        _write(
            ledger,
            {
                "schema_version": (
                    "dual_frequency_performance_byte_ledger_v1"
                ),
                "run_id": "benchmark-run",
                "segment_id": self.segment_id,
                "segment_path": str(segment_path.relative_to(self.run)),
                "segment_sha256": _sha(segment_path),
                "event_report_path": str(event_path.relative_to(self.run)),
                "event_report_sha256": _sha(event_path),
                "fragment_count": 1,
                "source_bytes": 11,
                "scratch_bytes": 22,
                "fragments": [
                    {
                        "task_id": "task_one",
                        "process_identity": "process-one",
                        "path": str(fragment_path.relative_to(self.run)),
                        "sha256": _sha(fragment_path),
                        "source_bytes": 11,
                        "scratch_bytes": 22,
                    }
                ],
            },
        )
        _write(
            parity,
            {
                "schema_version": "dual_frequency_candidate_parity_v1",
                "row_count": 1,
                "full_candidate_mismatch_count": 0,
                "fold_candidate_mismatch_count": 0,
                "candidate_false_negative_count": 0,
                "rows": [{"row_id": "configured-row"}],
            },
        )
        _write(
            audit,
            {
                "schema_version": (
                    "dual_frequency_artifact_static_audit_v1"
                ),
                "run_id": "benchmark-run",
                "segment_id": self.segment_id,
                "nested_executor_creation_sites": [],
                "retained_null_n_by_f_artifact_ids": [],
            },
        )
        self.inputs = self.root / "counter-inputs.json"
        _write(
            self.inputs,
            {
                "schema_version": (
                    "dual_frequency_performance_counter_inputs_v1"
                ),
                "run_root": str(self.run),
                "run_id": "benchmark-run",
                "segment_id": self.segment_id,
                "segment_sha256": _sha(segment_path),
                "event_report_path": str(event_path),
                "event_report_sha256": _sha(event_path),
                "byte_ledger_path": str(ledger),
                "byte_ledger_sha256": _sha(ledger),
                "candidate_parity_path": str(parity),
                "candidate_parity_sha256": _sha(parity),
                "artifact_static_audit_path": str(audit),
                "artifact_static_audit_sha256": _sha(audit),
                "benchmark_class": "normative_fiber",
                "cache_state": "cold",
            },
        )

    def test_builds_exact_counters_and_identical_replay(self) -> None:
        output = builder.build(self.inputs)
        first = output.read_bytes()
        self.assertEqual(builder.build(self.inputs), output)
        self.assertEqual(output.read_bytes(), first)
        document = json.loads(output.read_text(encoding="utf-8"))
        counters = document["counters"]
        self.assertEqual(counters["physical_producer_count_min"], 1)
        self.assertEqual(counters["physical_producer_count_max"], 1)
        self.assertEqual(counters["cache_full_verification_count_min"], 1)
        self.assertEqual(counters["cache_repeat_verification_count_max"], 0)
        self.assertEqual(counters["memmap_flush_count"], 2)
        self.assertEqual(counters["source_bytes"], 11)
        self.assertEqual(counters["scratch_bytes"], 22)

    def test_rejects_fragment_sha_change(self) -> None:
        inputs = json.loads(self.inputs.read_text(encoding="utf-8"))
        event = json.loads(
            Path(inputs["event_report_path"]).read_text(encoding="utf-8")
        )
        fragment = Path(event["fragments"][0]["path"])
        fragment.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(builder.PerformanceCounterBuildError):
            builder.build(self.inputs)

    def test_rejects_producer_outside_physical_use_closure(self) -> None:
        inputs = json.loads(self.inputs.read_text(encoding="utf-8"))
        event_path = Path(inputs["event_report_path"])
        event = json.loads(event_path.read_text(encoding="utf-8"))
        fragment_path = Path(event["fragments"][0]["path"])
        fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
        fragment["events"]["keyed"]["physical_producer"] = {
            "fiber_exposures:" + "b" * 64: 1
        }
        _write(fragment_path, fragment)
        event["fragments"][0]["sha256"] = _sha(fragment_path)
        event["events"]["keyed"]["physical_producer"] = dict(
            fragment["events"]["keyed"]["physical_producer"]
        )
        _write(event_path, event)
        segment_path = (
            self.run / "execution_segments" / f"{self.segment_id}.json"
        )
        segment = json.loads(segment_path.read_text(encoding="utf-8"))
        segment["performance_events_sha256"] = _sha(event_path)
        _write(segment_path, segment)
        inputs["segment_sha256"] = _sha(segment_path)
        inputs["event_report_sha256"] = _sha(event_path)
        ledger_path = Path(inputs["byte_ledger_path"])
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["segment_sha256"] = inputs["segment_sha256"]
        ledger["event_report_sha256"] = inputs["event_report_sha256"]
        _write(ledger_path, ledger)
        inputs["byte_ledger_sha256"] = _sha(ledger_path)
        _write(self.inputs, inputs)
        with self.assertRaises(builder.PerformanceCounterBuildError):
            builder.build(self.inputs)

    def test_rejects_external_event_report_with_matching_name_and_sha(self) -> None:
        inputs = json.loads(self.inputs.read_text(encoding="utf-8"))
        event_path = Path(inputs["event_report_path"])
        outside = self.root / "outside" / event_path.name
        outside.parent.mkdir()
        outside.write_bytes(event_path.read_bytes())
        inputs["event_report_path"] = str(outside)
        inputs["event_report_sha256"] = _sha(outside)
        _write(self.inputs, inputs)
        with self.assertRaisesRegex(
            builder.PerformanceCounterBuildError,
            "binding differs",
        ):
            builder.build(self.inputs)

    def test_rejects_external_same_byte_fragment_path(self) -> None:
        inputs = json.loads(self.inputs.read_text(encoding="utf-8"))
        event_path = Path(inputs["event_report_path"])
        event = json.loads(event_path.read_text(encoding="utf-8"))
        original = Path(event["fragments"][0]["path"])
        outside = self.root / "outside-fragment" / original.name
        outside.parent.mkdir()
        outside.write_bytes(original.read_bytes())
        event["fragments"][0]["path"] = str(outside)
        _write(event_path, event)
        segment_path = (
            self.run / "execution_segments" / f"{self.segment_id}.json"
        )
        segment = json.loads(segment_path.read_text(encoding="utf-8"))
        segment["performance_events_sha256"] = _sha(event_path)
        _write(segment_path, segment)
        inputs["segment_sha256"] = _sha(segment_path)
        inputs["event_report_sha256"] = _sha(event_path)
        ledger_path = Path(inputs["byte_ledger_path"])
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["segment_sha256"] = inputs["segment_sha256"]
        ledger["event_report_sha256"] = inputs["event_report_sha256"]
        _write(ledger_path, ledger)
        inputs["byte_ledger_sha256"] = _sha(ledger_path)
        _write(self.inputs, inputs)
        with self.assertRaisesRegex(
            builder.PerformanceCounterBuildError,
            "outside the run root",
        ):
            builder.build(self.inputs)

    def test_rejects_parent_owned_source_or_scratch_bytes(self) -> None:
        inputs = json.loads(self.inputs.read_text(encoding="utf-8"))
        event_path = Path(inputs["event_report_path"])
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["parent_events"]["scalars"]["source_bytes"] = 1
        _write(event_path, event)
        segment_path = (
            self.run / "execution_segments" / f"{self.segment_id}.json"
        )
        segment = json.loads(segment_path.read_text(encoding="utf-8"))
        segment["performance_events_sha256"] = _sha(event_path)
        _write(segment_path, segment)
        inputs["segment_sha256"] = _sha(segment_path)
        inputs["event_report_sha256"] = _sha(event_path)
        ledger_path = Path(inputs["byte_ledger_path"])
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["segment_sha256"] = inputs["segment_sha256"]
        ledger["event_report_sha256"] = inputs["event_report_sha256"]
        _write(ledger_path, ledger)
        inputs["byte_ledger_sha256"] = _sha(ledger_path)
        _write(self.inputs, inputs)
        with self.assertRaisesRegex(
            builder.PerformanceCounterBuildError,
            "outside the live fragment ledger",
        ):
            builder.build(self.inputs)


if __name__ == "__main__":
    unittest.main()
