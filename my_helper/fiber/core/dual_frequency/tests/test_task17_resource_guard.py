from __future__ import annotations

import csv
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from my_helper.fiber.pipelines.run_task17_resource_guard import (
    MountIdentity,
    ProcessRow,
    ResourceGuardError,
    _pid_exists,
    _terminate_tree,
    run_guard,
)
from my_helper.fiber.pipelines.validate_task17_preinstrumentation_resources import (
    _guard_rows as validate_preinstrumentation_guard,
)
from my_helper.fiber.pipelines.validate_task17_resource_acceptance import (
    _validate_guard as validate_instrumented_guard,
)


class Task17ResourceGuardTest(unittest.TestCase):
    def _run(
        self,
        root: Path,
        snapshots: list[tuple[ProcessRow, ...]],
        swaps: list[int],
        mounts: list[bool | MountIdentity | None],
        *,
        max_rss_bytes: int = 1000,
    ) -> tuple[int, list[dict[str, str]], list[tuple[int, ...]]]:
        terminations: list[tuple[int, ...]] = []
        times = iter(
            (
                "2026-07-23T00:00:00+00:00",
                "2026-07-23T00:00:01+00:00",
                "2026-07-23T00:00:02+00:00",
            )
        )

        def process_reader() -> tuple[ProcessRow, ...]:
            return snapshots.pop(0)

        def swap_reader() -> int:
            return swaps.pop(0)

        stable_mount = MountIdentity(
            source_path="/dev/disk4s2",
            source_device=1,
            source_inode=2,
            source_rdev=3,
            source_mode=4,
            source_ctime_ns=5,
            mount_device=6,
            mount_inode=7,
            mount_ctime_ns=8,
        )

        def mount_identity_reader(_path: Path) -> MountIdentity | None:
            value = mounts.pop(0)
            if value is True:
                return stable_mount
            if value is False:
                return None
            return value

        def terminator(rows, runner_pid: int) -> None:
            terminations.append(
                tuple(sorted(row.pid for row in rows if row.pid == runner_pid))
            )

        output = root / "guard.csv"
        status = run_guard(
            runner_pid=100,
            output=output,
            mount_path=root / "VAL",
            max_rss_bytes=max_rss_bytes,
            interval_seconds=1.0,
            process_reader=process_reader,
            swap_reader=swap_reader,
            mount_identity_reader=mount_identity_reader,
            pid_reader=lambda _pid: False,
            terminator=terminator,
            sleeper=lambda _seconds: None,
            timestamp_reader=lambda: next(times),
        )
        with output.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return status, rows, terminations

    def test_samples_tree_then_records_clean_runner_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status, rows, terminations = self._run(
                root,
                [
                    (
                        ProcessRow(100, 1, 100, 5.0),
                        ProcessRow(101, 100, 200, 6.0),
                        ProcessRow(900, 1, 800, 90.0),
                    ),
                    (ProcessRow(900, 1, 800, 90.0),),
                ],
                [10, 10, 10],
                [True],
            )
        self.assertEqual(status, 0)
        self.assertEqual([row["event"] for row in rows], ["sample", "runner_exit"])
        self.assertEqual(rows[0]["tree_rss_bytes"], "300")
        self.assertEqual(rows[0]["tree_cpu_percent"], "11.0")
        self.assertEqual(rows[1]["peak_tree_rss_bytes"], "300")
        self.assertEqual(terminations, [])

    def test_unmount_records_stop_and_terminates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, rows, terminations = self._run(
                Path(temporary),
                [(ProcessRow(100, 1, 100, 1.0),)],
                [10, 10],
                [False],
            )
        self.assertEqual(status, 2)
        self.assertEqual(rows[-1]["event"], "val_unmounted_sigterm")
        self.assertEqual(terminations, [(100,)])

    def test_same_path_remount_records_stop_and_terminates(self) -> None:
        replacement_mount = MountIdentity(
            source_path="/dev/disk4s2",
            source_device=1,
            source_inode=20,
            source_rdev=3,
            source_mode=4,
            source_ctime_ns=50,
            mount_device=6,
            mount_inode=7,
            mount_ctime_ns=8,
        )
        with tempfile.TemporaryDirectory() as temporary:
            status, rows, terminations = self._run(
                Path(temporary),
                [
                    (ProcessRow(100, 1, 100, 1.0),),
                    (ProcessRow(100, 1, 100, 1.0),),
                ],
                [10, 10, 10],
                [True, replacement_mount],
            )
        self.assertEqual(status, 2)
        self.assertEqual(
            [row["event"] for row in rows],
            ["sample", "val_unmounted_sigterm"],
        )
        self.assertEqual(terminations, [(100,)])

    def test_clean_output_is_accepted_by_both_resource_validators(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status, _rows, _terminations = self._run(
                root,
                [
                    (ProcessRow(100, 1, 100, 1.0),),
                    (ProcessRow(900, 1, 100, 1.0),),
                ],
                [10, 10, 10],
                [True],
            )
            strict = validate_instrumented_guard(
                root / "guard.csv",
                max_rss_bytes=1000,
            )
            historical, _parsed = validate_preinstrumentation_guard(
                root / "guard.csv",
                max_rss_bytes=1000,
            )
        self.assertEqual(status, 0)
        self.assertEqual(strict["status"], "validated")
        self.assertEqual(historical["status"], "validated")

    def test_rss_boundary_records_stop_and_terminates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, rows, terminations = self._run(
                Path(temporary),
                [(ProcessRow(100, 1, 1000, 1.0),)],
                [10, 10],
                [True],
            )
        self.assertEqual(status, 2)
        self.assertEqual(rows[-1]["event"], "rss_limit_sigterm")
        self.assertEqual(terminations, [(100,)])

    def test_swap_growth_records_stop_and_terminates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, rows, terminations = self._run(
                Path(temporary),
                [(ProcessRow(100, 1, 100, 1.0),)],
                [10, 11],
                [True],
            )
        self.assertEqual(status, 2)
        self.assertEqual(rows[-1]["event"], "swap_growth_sigterm")
        self.assertEqual(terminations, [(100,)])

    def test_existing_header_must_match_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "guard.csv"
            output.write_text("wrong,header\n", encoding="utf-8")
            with self.assertRaisesRegex(ResourceGuardError, "header differs"):
                run_guard(
                    runner_pid=100,
                    output=output,
                    mount_path=root / "VAL",
                    process_reader=lambda: (),
                    swap_reader=lambda: 0,
                )

    def test_process_evidence_failure_terminates_the_declared_runner(self) -> None:
        terminations: list[tuple[int, ...]] = []

        def process_reader() -> tuple[ProcessRow, ...]:
            raise ResourceGuardError("process evidence failed")

        def terminator(rows, _runner_pid: int) -> None:
            terminations.append(tuple(row.pid for row in rows))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ResourceGuardError, "process evidence"):
                run_guard(
                    runner_pid=100,
                    output=root / "guard.csv",
                    mount_path=root / "VAL",
                    process_reader=process_reader,
                    swap_reader=lambda: 0,
                    terminator=terminator,
                )
        self.assertEqual(terminations, [(100,)])

    def test_live_runner_missing_from_snapshot_fails_closed(self) -> None:
        terminations: list[tuple[int, ...]] = []

        def terminator(rows, _runner_pid: int) -> None:
            terminations.append(tuple(row.pid for row in rows))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                ResourceGuardError,
                "live but absent",
            ):
                run_guard(
                    runner_pid=100,
                    output=root / "guard.csv",
                    mount_path=root / "VAL",
                    process_reader=lambda: (ProcessRow(900, 1, 1, 0.0),),
                    swap_reader=lambda: 0,
                    pid_reader=lambda _pid: True,
                    terminator=terminator,
                )
        self.assertEqual(terminations, [(100,)])

    def test_pid_probe_distinguishes_absence_from_permission_denial(self) -> None:
        with patch("os.kill", side_effect=ProcessLookupError):
            self.assertFalse(_pid_exists(100))
        with patch("os.kill", side_effect=PermissionError):
            self.assertTrue(_pid_exists(100))

    def test_guard_evidence_cannot_be_written_below_guarded_mount(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "VAL"
            with self.assertRaisesRegex(ResourceGuardError, "outside"):
                run_guard(
                    runner_pid=100,
                    output=mount / "guard.csv",
                    mount_path=mount,
                    process_reader=lambda: (),
                    swap_reader=lambda: 0,
                )

    def test_termination_is_limited_to_the_runner_tree(self) -> None:
        rows = (
            ProcessRow(100, 1, 1, 0.0),
            ProcessRow(101, 100, 1, 0.0),
            ProcessRow(102, 101, 1, 0.0),
            ProcessRow(900, 1, 1, 0.0),
        )
        with patch("os.kill") as kill:
            _terminate_tree(rows, 100)
        self.assertEqual(
            [call.args for call in kill.call_args_list],
            [(102, signal.SIGTERM), (101, signal.SIGTERM), (100, signal.SIGTERM)],
        )


if __name__ == "__main__":
    unittest.main()
