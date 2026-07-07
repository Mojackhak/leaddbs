#!/usr/bin/env python3
"""Self-tests for shared STN/SNr IO helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stnsnr_io import manifest_audit_fields, manifest_stale_status, read_csv, write_csv, write_json


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


def test_reporting_modules_use_shared_json_writer() -> None:
    analysis_dir = Path(__file__).resolve().parent
    for module_name in [
        "stnsnr_four_model_gate_status.py",
        "stnsnr_four_model_execution_status.py",
        "stnsnr_four_model_formal_worklist.py",
        "stnsnr_four_model_final_reporting.py",
        "stnsnr_four_model_all_endpoint_reporting.py",
    ]:
        source = (analysis_dir / module_name).read_text(encoding="utf-8")
        assert_true("from stnsnr_io import" in source and "write_json" in source, f"{module_name} imports shared IO")
        assert_true("def write_json(" not in source, f"{module_name} does not define local write_json")


def test_manifest_stale_status() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        current = "abc123"
        missing_provenance = root / "missing_provenance.json"
        missing_provenance.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        current_manifest = root / "current.json"
        current_manifest.write_text(
            json.dumps({"code_provenance": {"git_commit": current}}),
            encoding="utf-8",
        )
        legacy_manifest = root / "legacy.json"
        legacy_manifest.write_text(
            json.dumps({"git_provenance": {"head_commit": current}}),
            encoding="utf-8",
        )
        stale_manifest = root / "stale.json"
        stale_manifest.write_text(
            json.dumps({"code_provenance": {"git_commit": "def456"}}),
            encoding="utf-8",
        )

        assert_equal(manifest_stale_status("", current), "not_applicable_no_manifest", "empty manifest path")
        assert_equal(manifest_stale_status(str(root / "missing.json"), current), "missing_manifest", "missing manifest")
        assert_equal(
            manifest_stale_status(str(missing_provenance), current),
            "missing_code_provenance",
            "missing code provenance",
        )
        assert_equal(manifest_stale_status(str(current_manifest), current), "current_head", "current manifest")
        assert_equal(manifest_stale_status(str(legacy_manifest), current), "current_head", "legacy current manifest")
        assert_equal(manifest_stale_status(str(stale_manifest), current), "different_commit", "stale manifest")


def test_manifest_audit_fields() -> None:
    row = {
        "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
        "latest_manifest_stale_status": "missing_code_provenance",
        "other": "ignored",
    }
    assert_equal(
        manifest_audit_fields(row),
        {
            "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
            "latest_manifest_stale_status": "missing_code_provenance",
        },
        "manifest audit field copy",
    )


def main() -> int:
    test_csv_and_json_helpers()
    test_reporting_modules_use_shared_json_writer()
    test_manifest_stale_status()
    test_manifest_audit_fields()
    print("STN/SNr IO self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
