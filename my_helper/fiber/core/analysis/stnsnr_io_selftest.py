#!/usr/bin/env python3
"""Self-tests for shared STN/SNr IO helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stnsnr_io import read_csv, write_csv, write_json


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_csv_and_json_helpers() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        csv_path = root / "nested" / "table.csv"
        write_csv(csv_path, [{"a": 1, "b": "two"}], ["a", "b"])
        rows = read_csv(csv_path)
        assert_equal(rows, [{"a": "1", "b": "two"}], "CSV round trip")

        json_path = root / "nested" / "manifest.json"
        write_json(json_path, {"status": "PASS"}, add_code_provenance=True)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert_equal(data["status"], "PASS", "JSON payload")
        assert_true(bool(data["code_provenance"].get("git_commit")), "code provenance added")


def main() -> int:
    test_csv_and_json_helpers()
    print("STN/SNr IO self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
