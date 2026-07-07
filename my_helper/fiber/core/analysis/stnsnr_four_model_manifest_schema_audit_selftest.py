#!/usr/bin/env python3
"""Self-tests for STN/SNr four-model manifest schema audit."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from stnsnr_four_model_manifest_schema_audit import build_manifest_schema_audit


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_schema_audit_deduplicates_and_classifies_manifests() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        complete_manifest = root / "complete_manifest.json"
        complete_manifest.write_text(
            json.dumps(
                {
                    "generated_at": "2026-07-07T00:00:00",
                    "outputs": {"csv": "out.csv"},
                    "code_provenance": {"git_commit": "abc123"},
                }
            ),
            encoding="utf-8",
        )
        legacy_manifest = root / "legacy_manifest.json"
        legacy_manifest.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        invalid_manifest = root / "invalid_manifest.json"
        invalid_manifest.write_text("{not json\n", encoding="utf-8")
        missing_manifest = root / "missing_manifest.json"

        status_csv = root / "status.csv"
        write_csv(
            status_csv,
            [
                {"model_id": "A", "latest_manifest": str(complete_manifest)},
                {"model_id": "B_DTOR", "latest_manifest": str(missing_manifest)},
            ],
        )
        final_report_csv = root / "final_report.csv"
        write_csv(
            final_report_csv,
            [
                {"model_id": "A", "latest_manifest": str(complete_manifest)},
                {"model_id": "D_DTOR", "latest_manifest": str(legacy_manifest)},
            ],
        )
        all_endpoint_csv = root / "all_endpoint.csv"
        write_csv(
            all_endpoint_csv,
            [
                {
                    "source_table": "discovered_branch_manifest",
                    "model_id": "C",
                    "manifest_path": str(legacy_manifest),
                },
                {
                    "source_table": "discovered_branch_manifest",
                    "model_id": "D_DTOR",
                    "manifest_path": str(invalid_manifest),
                },
            ],
        )

        result = build_manifest_schema_audit(
            status_csv=status_csv,
            final_report_csv=final_report_csv,
            all_endpoint_report_csv=all_endpoint_csv,
            output_dir=root / "manifest_schema_audit",
            current_commit="abc123",
        )

        rows = read_csv(Path(result["schema_audit_csv"]))
        rows_by_path = {row["manifest_path"]: row for row in rows}
        assert_equal(len(rows_by_path), 4, "deduplicated manifest rows")
        assert_equal(rows_by_path[str(complete_manifest)]["schema_status"], "schema_complete", "complete schema")
        assert_equal(
            rows_by_path[str(complete_manifest)]["latest_manifest_stale_status"],
            "current_head",
            "complete manifest current",
        )
        assert_equal(
            rows_by_path[str(legacy_manifest)]["schema_status"],
            "schema_missing_recommended_fields",
            "legacy schema",
        )
        assert_equal(
            rows_by_path[str(legacy_manifest)]["missing_recommended_fields"],
            "code_provenance;generated_at;outputs",
            "legacy missing fields",
        )
        assert_true("final_report:D_DTOR" in rows_by_path[str(legacy_manifest)]["source_refs"], "legacy final ref")
        assert_true("all_endpoint:C" in rows_by_path[str(legacy_manifest)]["source_refs"], "legacy all-endpoint ref")
        assert_equal(rows_by_path[str(invalid_manifest)]["schema_status"], "invalid_json", "invalid schema")
        assert_equal(rows_by_path[str(missing_manifest)]["schema_status"], "missing_manifest", "missing schema")

        manifest = json.loads(Path(result["manifest_json"]).read_text(encoding="utf-8"))
        assert_equal(manifest["schema_status_counts"]["schema_complete"], 1, "manifest complete count")
        assert_equal(
            manifest["schema_status_counts"]["schema_missing_recommended_fields"],
            1,
            "manifest legacy count",
        )
        assert_equal(manifest["schema_status_counts"]["invalid_json"], 1, "manifest invalid count")
        assert_equal(manifest["schema_status_counts"]["missing_manifest"], 1, "manifest missing count")
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_manifest_schema_audit_deduplicates_and_classifies_manifests()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
