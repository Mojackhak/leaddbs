"""Synthetic end-to-end tests for the isolated Task 17 fault harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import textwrap
import unittest

from my_helper.fiber.pipelines import run_task17_fault_acceptance as harness


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Task17FaultAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.parent = self.root / "accepted-parent"
        self.publication = self.root / "publication"
        self.cache = self.root / "production-cache"
        self.working = self.root / "working"
        for directory in (
            self.parent,
            self.publication,
            self.cache,
            self.working,
        ):
            directory.mkdir()
        _write_json(
            self.parent / "run_manifest.json",
            {
                "run_id": "accepted-parent",
                "final_status": "completed",
            },
        )
        self.sources: dict[str, Path] = {}
        for name, content in {
            "payload.bin": b"payload",
            "shard.bin": b"shard",
            "axis.json": b'{"axis":"stable"}\n',
            "fail_input.bin": b"fail-input",
            "rebuild_parent.bin": b"parent",
            "protected.bin": b"protected",
        }.items():
            path = self.parent / name
            path.write_bytes(content)
            self.sources[name] = path
        (self.publication / "manifest.json").write_text(
            '{"status":"completed"}\n',
            encoding="utf-8",
        )
        (self.cache / "entry.bin").write_bytes(b"cache")
        self.one_shot = self.publication / "one-shot.txt"
        self.one_shot.write_text("same\n", encoding="utf-8")
        self.helper = self.working / "fault_fixture.py"
        self.helper.write_text(
            textwrap.dedent(
                """
                from __future__ import annotations
                import hashlib
                import json
                from pathlib import Path
                import sys

                mode = sys.argv[1]
                root = Path(sys.argv[2])
                if mode == "reject":
                    path = Path(sys.argv[3])
                    expected = sys.argv[4]
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    if actual != expected:
                        print("hash mismatch", file=sys.stderr)
                        raise SystemExit(7)
                    raise SystemExit(0)
                if mode == "first":
                    if not (root / "inputs" / "fail_input.bin").exists():
                        for name, status in (
                            ("failed.json", "failed"),
                            ("child-a.json", "skipped"),
                            ("child-b.json", "skipped"),
                        ):
                            path = root / "tasks" / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text(json.dumps({"status": status}))
                        print("missing input", file=sys.stderr)
                        raise SystemExit(8)
                    raise SystemExit(0)
                if mode == "resume":
                    for name in ("failed.json", "child-a.json", "child-b.json"):
                        path = root / "tasks" / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps({"status": "completed"}))
                    raise SystemExit(0)
                if mode == "plain":
                    if not (root / "inputs" / "rebuild_parent.bin").exists():
                        print("missing parent", file=sys.stderr)
                        raise SystemExit(9)
                    raise SystemExit(0)
                if mode == "rebuild":
                    rebuilt = root / "rebuilt"
                    rebuilt.mkdir(parents=True, exist_ok=True)
                    (rebuilt / "run_manifest.json").write_text(
                        json.dumps(
                            {
                                "run_id": "rebuilt-main",
                                "final_status": "completed",
                            }
                        )
                    )
                    (root / "rebuilt-output.txt").write_text("same\\n")
                    raise SystemExit(0)
                if mode == "extension":
                    raise SystemExit(0)
                if mode == "cache":
                    output = root / "cache-output.bin"
                    output.write_bytes(b"cache-output")
                    raise SystemExit(0)
                raise SystemExit(99)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.plan = self.root / "fault-plan.json"
        self.acceptance = self.root / "isolated"
        self._write_plan()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _command(self, *parts: str) -> list[str]:
        return [
            "python",
            str(self.helper),
            *parts,
        ]

    def _write_plan(self) -> None:
        readonly = [
            {"path": str(path), "sha256": _sha(path)}
            for path in (
                *self.sources.values(),
                self.parent / "run_manifest.json",
                self.publication / "manifest.json",
                self.one_shot,
                self.cache / "entry.bin",
            )
        ]
        copied = [
            {
                "source_path": str(path),
                "relative_path": name,
                "sha256": _sha(path),
            }
            for name, path in self.sources.items()
        ]
        corruption = []
        for kind, name in (
            ("payload", "payload.bin"),
            ("shard", "shard.bin"),
            ("axis", "axis.json"),
        ):
            corruption.append(
                {
                    "id": f"{kind}-corruption",
                    "kind": kind,
                    "relative_path": name,
                    "command": self._command(
                        "reject",
                        "{acceptance_root}",
                        f"{{acceptance_root}}/inputs/{name}",
                        _sha(self.sources[name]),
                    ),
                    "expected_exit_code": 7,
                    "expected_error_substring": "hash mismatch",
                }
            )
        cache_output_sha = hashlib.sha256(b"cache-output").hexdigest()
        _write_json(
            self.plan,
            {
                "schema_version": "dual_frequency_task17_fault_plan_v1",
                "plan_id": "synthetic-fault-plan",
                "accepted_parent_root": str(self.parent),
                "canonical_publication_roots": [str(self.publication)],
                "shared_production_cache_root": str(self.cache),
                "readonly_closure": readonly,
                "copied_artifacts": copied,
                "conda_environment": "leaddbs",
                "working_directory": str(self.working),
                "corruption_cases": corruption,
                "fail_once_case": {
                    "id": "fail-once",
                    "withheld_relative_path": "fail_input.bin",
                    "first_command": self._command(
                        "first",
                        "{acceptance_root}",
                    ),
                    "resume_command": self._command(
                        "resume",
                        "{acceptance_root}",
                    ),
                    "expected_exit_code": 8,
                    "expected_error_substring": "missing input",
                    "failed_task_state": "tasks/failed.json",
                    "descendant_task_states": [
                        "tasks/child-a.json",
                        "tasks/child-b.json",
                    ],
                    "protected_artifacts": [
                        {
                            "relative_path": "inputs/protected.bin",
                            "sha256": _sha(self.sources["protected.bin"]),
                        }
                    ],
                },
                "rebuild_case": {
                    "id": "deletion-rebuild",
                    "required_artifact_relative_path": "rebuild_parent.bin",
                    "plain_extension_command": self._command(
                        "plain",
                        "{acceptance_root}",
                    ),
                    "expected_exit_code": 9,
                    "expected_error_substring": "missing parent",
                    "rebuild_command": self._command(
                        "rebuild",
                        "{acceptance_root}",
                    ),
                    "rebuilt_run_relative_path": "rebuilt",
                    "rebuilt_run_id": "rebuilt-main",
                    "extension_command": self._command(
                        "extension",
                        "{acceptance_root}",
                    ),
                    "one_shot_comparisons": [
                        {
                            "rebuilt_relative_path": "rebuilt-output.txt",
                            "one_shot_path": str(self.one_shot),
                            "kind": "exact",
                            "atol": 0.0,
                            "rtol": 0.0,
                        }
                    ],
                },
                "cache_replay_case": {
                    "id": "copied-cache",
                    "command": self._command(
                        "cache",
                        "{acceptance_root}",
                    ),
                    "forbidden_argument": "--allow-expensive-producers",
                    "expected_outputs": [
                        {
                            "relative_path": "cache-output.bin",
                            "sha256": cache_output_sha,
                        }
                    ],
                },
            },
        )

    def test_complete_isolated_sequence_is_resumable_and_read_only(self) -> None:
        source_hashes = {
            path: _sha(path)
            for path in (
                *self.sources.values(),
                self.parent / "run_manifest.json",
                self.publication / "manifest.json",
                self.one_shot,
                self.cache / "entry.bin",
            )
        }
        marker = harness.initialize(self.plan, self.acceptance)
        report = harness.run(self.plan, self.acceptance)
        second = harness.run(self.plan, self.acceptance)
        validated = harness.validate_existing(self.plan, self.acceptance)
        self.assertEqual(marker["schema_version"], harness._MARKER_SCHEMA)
        self.assertEqual(report, second)
        self.assertEqual(report, validated)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(len(report["corruption_cases"]), 3)
        self.assertEqual(report["fail_once_case"]["status"], "validated")
        self.assertEqual(report["rebuild_case"]["rebuilt_run_id"], "rebuilt-main")
        self.assertEqual(report["cache_replay_case"]["status"], "validated")
        self.assertEqual(
            {path: _sha(path) for path in source_hashes},
            source_hashes,
        )
        for name, source in self.sources.items():
            self.assertEqual(
                _sha(self.acceptance / "inputs" / name),
                _sha(source),
            )

    def test_nonempty_unmarked_root_is_rejected(self) -> None:
        self.acceptance.mkdir()
        (self.acceptance / "foreign.txt").write_text("foreign", encoding="utf-8")
        with self.assertRaisesRegex(
            harness.FaultAcceptanceError,
            "lacks the harness marker",
        ):
            harness.initialize(self.plan, self.acceptance)

    def test_acceptance_root_inside_parent_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            harness.FaultAcceptanceError,
            "disjoint",
        ):
            harness.initialize(self.plan, self.parent / "unsafe")

    def test_completed_case_rejects_tampered_attempt_inventory(self) -> None:
        harness.initialize(self.plan, self.acceptance)
        harness.run(self.plan, self.acceptance)
        log = next(
            (self.acceptance / "cases" / "payload-corruption").glob(
                "attempt_*/*/*.stdout.txt"
            )
        )
        log.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(
            harness.FaultAcceptanceError,
            "attempt inventory differs",
        ):
            harness.validate_existing(self.plan, self.acceptance)

    def test_command_absolute_path_escape_is_rejected(self) -> None:
        document = json.loads(self.plan.read_text(encoding="utf-8"))
        document["corruption_cases"][0]["command"].append("/etc/passwd")
        _write_json(self.plan, document)
        harness.initialize(self.plan, self.acceptance)
        with self.assertRaisesRegex(
            harness.FaultAcceptanceError,
            "escapes allowed roots",
        ):
            harness.run(self.plan, self.acceptance)


if __name__ == "__main__":
    unittest.main()
