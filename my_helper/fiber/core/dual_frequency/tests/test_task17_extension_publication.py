"""Tests for the complete Task 17 extension-v2 publication validator."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "pipelines"
    / "validate_task17_extension_publication.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_task17_extension_publication",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Task 17 extension publication validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class Task17ExtensionPublicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source-child"
        self.parent = self.root / "model-set"
        self.extension = self.parent / "extensions" / "extension-v2"
        self.source.mkdir()
        self.parent.mkdir()
        self.extension.mkdir(parents=True)
        self._build_valid_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build_valid_fixture(self) -> None:
        scientific_hash = "a" * 64
        parent_run_id = "parent-run"
        source_manifest = {
            "run_id": "source-child",
            "run_type": "sensitivity_extension",
            "final_status": "completed",
            "parent_run_id": parent_run_id,
            "scientific_configuration_hash": scientific_hash,
            "selected_sensitivity_analyses": ["jitter"],
        }
        _write_json(self.source / "run_manifest.json", source_manifest)
        _write_json(self.source / "complete.json", {})
        _write_json(
            self.source / "base_run_reference.json",
            {
                "base_run_id": parent_run_id,
                "scientific_configuration_hash": scientific_hash,
            },
        )
        parent_manifest = {
            "final_status": "completed",
            "source_run_id": parent_run_id,
            "model_set_id": "synthetic",
        }
        _write_json(self.parent / "model_manifest.json", parent_manifest)
        base = "adl/reference/sensitivity/spatial_jitter"
        _write_json(
            self.extension / base / "result.json",
            {
                "schema_version": "synthetic_result_v1",
                "status": "completed",
            },
        )
        _write_json(
            self.extension / base / "status.json",
            {
                "schema_version": "synthetic_status_v1",
                "status": "completed",
            },
        )
        result_row = {
            "endpoint_id": "endpoint",
            "scale_id": "adl",
            "model_family": "reference_voxel",
            "model_role": "reference",
            "analysis": "jitter",
            "final_model_id": "final",
            "selected_tau": 200,
            "selected_coverage": 5,
            "final_branch": "reference",
            "subject_count": 12,
            "result_relative_path": f"{base}/result.json",
            "status_relative_path": f"{base}/status.json",
        }
        _write_json(
            self.extension / "spatial_jitter_results.json",
            {
                "schema_version": "dual_frequency_spatial_jitter_results_v2",
                "source_extension_run_id": "source-child",
                "parent_run_id": parent_run_id,
                "result_count": 1,
                "results": [result_row],
            },
        )
        with (self.extension / "spatial_jitter_results.csv").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(result_row))
            writer.writeheader()
            writer.writerow(result_row)
        self._write_index()
        _write_json(
            self.extension / "extension_manifest.json",
            {
                "schema_version": "dual_frequency_extension_manifest_v2",
                "extension_id": self.extension.name,
                "source_extension_run_id": "source-child",
                "source_extension_manifest_sha256": validator._sha256_file(
                    self.source / "run_manifest.json"
                ),
                "parent_run_id": parent_run_id,
                "parent_publication_root": str(self.parent),
                "parent_publication_manifest_sha256": validator._sha256_file(
                    self.parent / "model_manifest.json"
                ),
                "parent_scientific_configuration_hash": scientific_hash,
                "analyses": ["jitter"],
                "result_count": 1,
                "publication_scope": "complete",
                "selected_scales": [],
                "status": "completed",
            },
        )

    def _write_index(self) -> None:
        paths = sorted(
            path
            for path in self.extension.rglob("*")
            if path.is_file()
            and path.name not in {"artifact_index.csv", "extension_manifest.json"}
        )
        with (self.extension / "artifact_index.csv").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            fields = (
                "relative_path",
                "sha256",
                "size_bytes",
                "status",
                "artifact_kind",
            )
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for path in paths:
                writer.writerow(
                    {
                        "relative_path": path.relative_to(self.extension).as_posix(),
                        "sha256": validator._sha256_file(path),
                        "size_bytes": path.stat().st_size,
                        "status": "completed",
                        "artifact_kind": path.stem,
                    }
                )

    def test_complete_extension_and_same_byte_report_pass(self) -> None:
        report = validator.validate(self.source, (self.extension,))
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["publications"][0]["artifact_count"], 4)
        output = self.root / "report.json"
        validator._write_report(output, report)
        validator._write_report(output, report)
        changed = dict(report)
        changed["status"] = "changed"
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "differs",
        ):
            validator._write_report(output, changed)

    def test_payload_corruption_fails(self) -> None:
        path = (
            self.extension
            / "adl/reference/sensitivity/spatial_jitter/result.json"
        )
        path.write_text("corrupt\n", encoding="utf-8")
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "byte count differs|SHA differs",
        ):
            validator.validate(self.source, (self.extension,))

    def test_unindexed_file_fails(self) -> None:
        (self.extension / "unexpected.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "exact file closure",
        ):
            validator.validate(self.source, (self.extension,))

    def test_parent_manifest_drift_fails(self) -> None:
        _write_json(
            self.parent / "model_manifest.json",
            {
                "final_status": "completed",
                "source_run_id": "parent-run",
                "model_set_id": "changed",
            },
        )
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "parent publication manifest SHA differs",
        ):
            validator.validate(self.source, (self.extension,))

    def test_source_child_drift_fails(self) -> None:
        manifest = json.loads(
            (self.source / "run_manifest.json").read_text(encoding="utf-8")
        )
        manifest["run_type"] = "changed"
        _write_json(self.source / "run_manifest.json", manifest)
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "extension and source child identities differ",
        ):
            validator.validate(self.source, (self.extension,))

    def test_missing_source_completion_marker_fails(self) -> None:
        (self.source / "complete.json").unlink()
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "source child completion marker is missing",
        ):
            validator.validate(self.source, (self.extension,))

    def test_forbidden_run_store_path_fails(self) -> None:
        path = (
            self.extension
            / "adl/reference/sensitivity/spatial_jitter/result.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["source"] = "file:///tmp/.runs/run/work/payload.npy"
        _write_json(path, payload)
        self._write_index()
        with self.assertRaisesRegex(
            validator.ExtensionPublicationError,
            "forbidden path text",
        ):
            validator.validate(self.source, (self.extension,))


if __name__ == "__main__":
    unittest.main()
