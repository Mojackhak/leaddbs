"""Tests for the complete Task 17 performance-matrix validator."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from my_helper.fiber.pipelines import validate_task17_performance_acceptance as validator


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Task17PerformanceAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.preflight = self.root / "real-cold-preflight.json"
        _write_json(self.preflight, {"authorized": False})
        self.manifest = self.root / "matrix.json"
        self.rows: list[dict[str, object]] = []
        self._build_runs()
        self._build_rows()
        self._write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _digest(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    @staticmethod
    def _counters(cache_state: str) -> dict[str, int]:
        counters = {field: 0 for field in validator._COUNTERS}
        producer_count = 1 if cache_state == "cold" else 0
        counters.update(
            {
                "physical_producer_count_min": producer_count,
                "physical_producer_count_max": producer_count,
                "cache_full_verification_count_min": 1,
                "cache_full_verification_count_max": 1,
                "source_bytes": 10,
                "scratch_bytes": 20,
            }
        )
        return counters

    def _build_runs(self) -> None:
        self.runs: dict[int, dict[str, object]] = {}
        for workers in validator._WORKERS:
            root = self.root / f"run-w{workers}"
            _write_json(
                root / "run_manifest.json",
                {"run_id": root.name, "final_status": "completed"},
            )
            configuration = root / "configuration_resolved.yaml"
            configuration.write_text(f"execution:\n  workers: {workers}\n", encoding="utf-8")
            probe = self.root / f"probe-w{workers}.csv"
            cpu_step = 40 if workers == 12 else 5
            with probe.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "timestamp_utc",
                        "elapsed_monotonic_seconds",
                        "process_count",
                        "tree_rss_bytes",
                        "aggregate_cpu_seconds",
                        "swap_used_bytes",
                        "source_bytes",
                        "scratch_bytes",
                        "event",
                    ),
                )
                writer.writeheader()
                for index, event in enumerate(("sample", "sample", "runner_exit")):
                    writer.writerow(
                        {
                            "timestamp_utc": f"2026-07-24T00:00:{index * 5:02d}+00:00",
                            "elapsed_monotonic_seconds": index * 5,
                            "process_count": 1 if index < 2 else 0,
                            "tree_rss_bytes": 100 if index < 2 else 0,
                            "aggregate_cpu_seconds": index * cpu_step,
                            "swap_used_bytes": 10,
                            "source_bytes": 10,
                            "scratch_bytes": 20,
                            "event": event,
                        }
                    )
            segment_id = "segment_0001"
            scheduler = (
                root
                / "execution_segments"
                / f"scheduler_windows_{segment_id}.json"
            )
            zero_reasons = {
                reason: 0
                for reason in (
                    "worker_slots",
                    "cpu",
                    "connectome_io",
                    "external_solver",
                )
            }
            _write_json(
                scheduler,
                {
                    "schema_version": "dual_frequency_scheduler_windows_v1",
                    "segment_id": segment_id,
                    "rows": [
                        {
                            "start_utc": "2026-07-24T00:00:00+00:00",
                            "finish_utc": "2026-07-24T00:00:05+00:00",
                            "elapsed_seconds": 5,
                            "ready_task_count": workers,
                            "running_task_count": 0,
                            "runnable_cpu_slots": workers,
                            "reserved_cpu_slots": workers,
                            "reserved_connectome_io_slots": 0,
                            "reserved_external_solver_slots": 0,
                            "admission_blocked_task_count_by_reason": zero_reasons,
                            "storage_limited": False,
                        },
                        {
                            "start_utc": "2026-07-24T00:00:05+00:00",
                            "finish_utc": "2026-07-24T00:00:10+00:00",
                            "elapsed_seconds": 5,
                            "ready_task_count": workers,
                            "running_task_count": 0,
                            "runnable_cpu_slots": workers,
                            "reserved_cpu_slots": workers,
                            "reserved_connectome_io_slots": 0,
                            "reserved_external_solver_slots": 0,
                            "admission_blocked_task_count_by_reason": zero_reasons,
                            "storage_limited": False,
                        },
                    ],
                },
            )
            _write_json(
                root / "execution_segments" / f"{segment_id}.json",
                {
                    "schema_version": "dual_frequency_execution_segment_v1",
                    "segment_id": segment_id,
                    "status": "finished",
                    "pool_mode": "spawn_process",
                    "workers": workers,
                    "connectome_io_slots": max(1, min(2, workers)),
                    "external_solver_slots": 1,
                    "blas_threads_per_worker": 1,
                    "pool_generation_count": 1,
                    "scheduler_windows_path": str(scheduler.relative_to(root)),
                    "scheduler_windows_sha256": _sha(scheduler),
                    "scheduler_window_count": 2,
                    "performance_events_path": (
                        f"execution_segments/performance_events_{segment_id}.json"
                    ),
                    "performance_events_sha256": self._digest(
                        f"events:{workers}"
                    ),
                },
            )
            segment = root / "execution_segments" / f"{segment_id}.json"
            self.runs[workers] = {
                "root": root,
                "configuration_sha256": _sha(configuration),
                "probe": probe,
                "segment_sha256": _sha(segment),
                "event_sha256": self._digest(f"events:{workers}"),
            }

    def _executed_row(
        self,
        key: tuple[str, str | None, str, str, int],
    ) -> dict[str, object]:
        benchmark_class, connectome, cache_state, solver_mode, workers = key
        run = self.runs[workers]
        counter = (
            Path(str(run["root"]))
            / "execution_segments"
            / (
                "performance_counters_"
                + self._digest(str(key))[:16]
                + ".json"
            )
        )
        _write_json(
            counter,
            {
                "schema_version": "dual_frequency_performance_counters_v1",
                "segment_id": "segment_0001",
                "source_evidence": {
                    "segment_sha256": run["segment_sha256"],
                    "event_report_sha256": run["event_sha256"],
                },
                "counters": self._counters(cache_state),
            },
        )
        return {
            "benchmark_class": benchmark_class,
            "connectome_id": connectome,
            "cache_state": cache_state,
            "solver_mode": solver_mode,
            "workers": workers,
            "status": "executed",
            "not_run_reason": None,
            "preflight_path": None,
            "preflight_sha256": None,
            "run_root": str(run["root"]),
            "segment_id": "segment_0001",
            "probe_csv": str(run["probe"]),
            "probe_sha256": _sha(Path(str(run["probe"]))),
            "configuration_sha256": run["configuration_sha256"],
            "numerical_identity_sha256": self._digest(
                f"{benchmark_class}:{connectome}:{solver_mode}"
            ),
            "io_classification": "compute_bound",
            "counter_path": str(counter),
            "counter_sha256": _sha(counter),
        }

    def _not_run_row(
        self,
        key: tuple[str, str | None, str, str, int],
    ) -> dict[str, object]:
        row = self._executed_row(key)
        row.update(
            {
                "status": "not_run",
                "not_run_reason": "real_cold_solver_not_authorized",
                "preflight_path": str(self.preflight),
                "preflight_sha256": _sha(self.preflight),
                "run_root": None,
                "segment_id": None,
                "probe_csv": None,
                "probe_sha256": None,
                "configuration_sha256": None,
                "numerical_identity_sha256": None,
                "io_classification": None,
                "counter_path": None,
                "counter_sha256": None,
            }
        )
        return row

    def _build_rows(self) -> None:
        for key in sorted(
            validator._expected_keys(("ppmi", "mgh", "dtor")),
            key=str,
        ):
            if key[0:4] == ("ppam", None, "cold", "real_solver"):
                self.rows.append(self._not_run_row(key))
            else:
                self.rows.append(self._executed_row(key))

    def _write_manifest(self) -> None:
        _write_json(
            self.manifest,
            {
                "schema_version": "dual_frequency_task17_performance_matrix_v1",
                "configured_connectomes": ["ppmi", "mgh", "dtor"],
                "chosen_default_workers": 3,
                "rows": self.rows,
            },
        )

    def _refresh_probe_sha(self, workers: int) -> None:
        probe = Path(str(self.runs[workers]["probe"]))
        digest = _sha(probe)
        for row in self.rows:
            if row["status"] == "executed" and row["workers"] == workers:
                row["probe_sha256"] = digest
        self._write_manifest()

    def _scheduler_fixture(
        self,
        workers: int = 3,
    ) -> tuple[Path, dict[str, object], Path, list[dict[str, object]]]:
        root = Path(str(self.runs[workers]["root"]))
        segment_path = root / "execution_segments" / "segment_0001.json"
        segment = json.loads(segment_path.read_text(encoding="utf-8"))
        scheduler = root / str(segment["scheduler_windows_path"])
        probe, _ = validator._read_probe(
            Path(str(self.runs[workers]["probe"]))
        )
        return root, segment, scheduler, probe

    def _validate_scheduler_fixture(
        self,
        root: Path,
        segment: dict[str, object],
        scheduler: Path,
        probe: list[dict[str, object]],
        *,
        workers: int = 3,
    ) -> dict[str, object]:
        segment["scheduler_windows_sha256"] = _sha(scheduler)
        return validator._scheduler_windows(
            root,
            segment,
            probe,
            workers,
        )

    def test_complete_matrix_passes_and_report_is_identical(self) -> None:
        report = validator.validate(self.manifest)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["row_count"], 72)
        self.assertEqual(
            report["chosen_default_decision"]["basis"],
            "prespecified_safe_default",
        )
        output = self.root / "acceptance.json"
        validator._write_report(output, report)
        first = output.read_bytes()
        validator._write_report(output, report)
        self.assertEqual(output.read_bytes(), first)

    def test_missing_row_fails_matrix_closure(self) -> None:
        self.rows.pop()
        self._write_manifest()
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "matrix closure differs",
        ):
            validator.validate(self.manifest)

    def test_low_12_worker_cpu_fails_utilization_gate(self) -> None:
        probe = self.runs[12]["probe"]
        with Path(str(probe)).open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for index, row in enumerate(rows):
            row["aggregate_cpu_seconds"] = str(index * 5)
        with Path(str(probe)).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_probe_sha(12)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "utilization gate failed",
        ):
            validator.validate(self.manifest)

    def test_decreasing_probe_byte_counter_is_rejected(self) -> None:
        probe = Path(str(self.runs[3]["probe"]))
        with probe.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["source_bytes"] = "11"
        rows[1]["source_bytes"] = "10"
        with probe.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_probe_sha(3)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "not monotonic",
        ):
            validator.validate(self.manifest)

    def test_probe_sha_mismatch_is_rejected(self) -> None:
        executed = next(row for row in self.rows if row["status"] == "executed")
        executed["probe_sha256"] = self._digest("different-probe")
        self._write_manifest()
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "performance probe SHA differs",
        ):
            validator.validate(self.manifest)

    def test_unknown_io_classification_is_rejected(self) -> None:
        executed = next(row for row in self.rows if row["status"] == "executed")
        executed["io_classification"] = "unknown"
        self._write_manifest()
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "I/O classification differs",
        ):
            validator.validate(self.manifest)

    def test_nondefault_workers_require_shorter_compute_bound_rows(self) -> None:
        _write_json(
            self.manifest,
            {
                "schema_version": "dual_frequency_task17_performance_matrix_v1",
                "configured_connectomes": ["ppmi", "mgh", "dtor"],
                "chosen_default_workers": 6,
                "rows": self.rows,
            },
        )
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "not faster than workers 3",
        ):
            validator.validate(self.manifest)

    def test_faster_nondefault_workers_record_comparisons(self) -> None:
        probe = Path(str(self.runs[6]["probe"]))
        with probe.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[-1]["elapsed_monotonic_seconds"] = "9"
        with probe.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_probe_sha(6)
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        document["chosen_default_workers"] = 6
        _write_json(self.manifest, document)
        report = validator.validate(self.manifest)
        decision = report["chosen_default_decision"]
        self.assertEqual(
            decision["basis"],
            "all_matched_compute_bound_rows_faster_than_workers_3",
        )
        self.assertGreater(len(decision["compute_bound_comparisons"]), 0)

    def test_early_runner_exit_is_rejected(self) -> None:
        probe = Path(str(self.runs[3]["probe"]))
        with probe.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["event"] = "runner_exit"
        rows[1]["process_count"] = "0"
        rows[1]["tree_rss_bytes"] = "0"
        with probe.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_probe_sha(3)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "boundary differs",
        ):
            validator.validate(self.manifest)

    def test_non_utc_or_nonincreasing_timestamp_is_rejected(self) -> None:
        probe = Path(str(self.runs[3]["probe"]))
        with probe.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["timestamp_utc"] = rows[0]["timestamp_utc"]
        with probe.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_probe_sha(3)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "strictly increasing UTC",
        ):
            validator.validate(self.manifest)

    def test_path_traversal_segment_id_is_rejected(self) -> None:
        executed = next(row for row in self.rows if row["status"] == "executed")
        executed["segment_id"] = "../segment_0001"
        self._write_manifest()
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "segment ID is invalid",
        ):
            validator.validate(self.manifest)

    def test_segment_schema_mismatch_is_rejected(self) -> None:
        root = Path(str(self.runs[3]["root"]))
        path = root / "execution_segments" / "segment_0001.json"
        segment = json.loads(path.read_text(encoding="utf-8"))
        segment["schema_version"] = "unexpected"
        _write_json(path, segment)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "execution segment boundary differs",
        ):
            validator.validate(self.manifest)

    def test_scheduler_extra_field_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][0]["unexpected"] = 1
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "fields differ",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_scheduler_noncontiguous_utc_window_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][1]["start_utc"] = "2026-07-24T00:00:06+00:00"
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "time closure differs",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_scheduler_boolean_elapsed_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][0]["elapsed_seconds"] = True
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "field types differ",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_scheduler_solver_reservation_above_ceiling_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][0]["reserved_external_solver_slots"] = 2
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "reservation exceeds",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_scheduler_runnable_derivation_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][0]["runnable_cpu_slots"] = 2
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "reservation exceeds",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_scheduler_storage_classification_is_rejected(self) -> None:
        root, segment, scheduler, probe = self._scheduler_fixture()
        document = json.loads(scheduler.read_text(encoding="utf-8"))
        document["rows"][0]["storage_limited"] = True
        _write_json(scheduler, document)
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "storage classification differs",
        ):
            self._validate_scheduler_fixture(
                root,
                segment,
                scheduler,
                probe,
            )

    def test_absolute_scheduler_path_is_rejected(self) -> None:
        root = Path(str(self.runs[3]["root"]))
        scheduler = (
            root
            / "execution_segments"
            / "scheduler_windows_segment_0001.json"
        )
        with self.assertRaisesRegex(
            validator.PerformanceAcceptanceError,
            "must be relative",
        ):
            validator._scheduler_windows(
                root,
                {
                    "segment_id": "segment_0001",
                    "scheduler_windows_path": str(scheduler.resolve()),
                },
                (),
                3,
            )


if __name__ == "__main__":
    unittest.main()
