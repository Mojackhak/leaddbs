"""Synthetic acceptance tests for the retained Task 17 parity verifier."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from dual_frequency.cache import (
    CacheFileMetadata,
    ContentAddressedCache,
    ScientificCacheKey,
    sha256_file,
)
from dual_frequency.contracts import AxisRef
from dual_frequency.contracts.identity import canonical_hash


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
VALIDATOR_PATH = (
    REPOSITORY_ROOT
    / "my_helper/fiber/pipelines/validate_task17_connectome_parity_fixture.py"
)
SPEC = importlib.util.spec_from_file_location("task17_parity_validator", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


CONNECTOMES = (
    "ppmi_85_ewert_2017",
    "mgh_usc_hcp_32_horn_2017",
    "dtor_985_full_elias_2024",
)
ROLES = ("reference", "addon_primary", "addon_reference_condition")
FAMILIES = ("reference_fiber", "addon_fiber")


class Task17ParityFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache_root = self.root / "cache"
        self.parent = self.root / "authority-run"
        (self.parent / "tasks").mkdir(parents=True)
        (self.parent / "run_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": self.parent.name,
                    "final_status": "completed",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _digest(label: str) -> str:
        return canonical_hash({"label": label})

    def _physical_rows(self) -> list[dict[str, object]]:
        cache = ContentAddressedCache(self.cache_root)
        rows: list[dict[str, object]] = []
        for connectome_index, connectome in enumerate(CONNECTOMES):
            for role_index, role in enumerate(ROLES):
                source = self.root / f"{connectome}-{role}.npy"
                values = np.full(
                    (2, 3),
                    connectome_index * 10 + role_index,
                    dtype=np.float32,
                )
                np.save(source, values)
                key = ScientificCacheKey(
                    geometry_hash=self._digest(f"geometry-{connectome}"),
                    stimulation_hash=self._digest(f"stimulation-{role}"),
                    component_frequency_hash=self._digest(f"component-{role}"),
                    transform_hash=self._digest("transform"),
                    connectome_feature_hash=self._digest(f"axis-{connectome}"),
                    backend_name="shared_fiber_physical_exposure",
                    backend_version="2",
                    scientific_parameter_hashes=(
                        ("role", self._digest(role)),
                    ),
                    kind="fiber_exposures",
                )
                row_axis = AxisRef("subjects", 2, self._digest("subjects"))
                feature_axis = AxisRef(
                    f"features-{connectome}",
                    3,
                    self._digest(f"features-{connectome}"),
                )
                entry = cache.publish(
                    key,
                    {"exposure.npy": source},
                    metadata={
                        "exposure.npy": CacheFileMetadata(
                            dtype="float32",
                            shape=(2, 3),
                            axes=(row_axis, feature_axis),
                            units="V/m",
                            space="synthetic",
                        )
                    },
                )
                rows.append(
                    {
                        "connectome_id": connectome,
                        "frequency_role": role,
                        "semantic_sha256": key.digest,
                        "payload_sha256": entry.files[0].sha256,
                        "shape": [2, 3],
                    }
                )
        return rows

    def _prepared_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        task_index = 0
        for family in FAMILIES:
            for connectome in CONNECTOMES:
                task_id = f"task_{task_index:020d}"
                work = self.parent / "work" / task_id
                work.mkdir(parents=True)
                exposure_path = work / "exposure.npy"
                ids_path = work / "feature_ids.npy"
                np.save(exposure_path, np.arange(6, dtype=np.float32).reshape(2, 3))
                np.save(ids_path, np.arange(1, 4, dtype=np.int64))
                exposure_sha = sha256_file(exposure_path)
                ids_sha = sha256_file(ids_path)
                axis_sha = self._digest(f"prepared-axis-{family}-{connectome}")
                exposure = {
                    "dtype": "float32",
                    "sha256": exposure_sha,
                    "shape": [2, 3],
                    "uri": exposure_path.resolve().as_uri(),
                }
                feature_ids = {
                    "dtype": "int64",
                    "sha256": ids_sha,
                    "shape": [3],
                    "uri": ids_path.resolve().as_uri(),
                }
                task = {
                    "status": "completed",
                    "result": {
                        "output_record_type": "PreparedExposureRecord",
                        "payload": {
                            "endpoint": {
                                "model_family": family,
                                "connectome_id": connectome,
                            },
                            "exposure": exposure,
                            "feature_ids": feature_ids,
                            "feature_axis": {"sha256": axis_sha},
                        },
                    }
                }
                (self.parent / "tasks" / f"{task_id}.json").write_text(
                    json.dumps(task),
                    encoding="utf-8",
                )
                rows.append(
                    {
                        "model_family": family,
                        "connectome_id": connectome,
                        "exposure_sha256": exposure_sha,
                        "feature_ids_sha256": ids_sha,
                        "feature_axis_sha256": axis_sha,
                        "shape": [2, 3],
                    }
                )
                task_index += 1
        return rows

    def _fixture(self) -> Path:
        fixture = {
            "schema_version": "dual_frequency_task17_connectome_parity_fixture_v1",
            "authority_run_id": self.parent.name,
            "authority_cache_root": str(self.cache_root),
            "physical_fiber_exposures": self._physical_rows(),
            "prepared_omega_max_exposures": self._prepared_rows(),
        }
        path = self.root / "fixture.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        return path

    def test_complete_fixture_validates_and_writes_immutable_report(self) -> None:
        fixture = self._fixture()
        report = VALIDATOR.validate(fixture, self.parent)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(len(report["physical_fiber_exposures"]), 9)
        self.assertEqual(len(report["prepared_omega_max_exposures"]), 6)
        output = self.root / "report.json"
        VALIDATOR._write_report(output, report)
        before = output.stat().st_mtime_ns
        VALIDATOR._write_report(output, report)
        self.assertEqual(output.stat().st_mtime_ns, before)

    def test_duplicate_physical_role_is_rejected(self) -> None:
        fixture = self._fixture()
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["physical_fiber_exposures"][1] = dict(
            payload["physical_fiber_exposures"][0]
        )
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(VALIDATOR.ParityFixtureError):
            VALIDATOR.validate(fixture, self.parent)

    def test_incomplete_parent_manifest_is_rejected(self) -> None:
        fixture = self._fixture()
        (self.parent / "run_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": self.parent.name,
                    "final_status": "running",
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(VALIDATOR.ParityFixtureError):
            VALIDATOR.validate(fixture, self.parent)


if __name__ == "__main__":
    unittest.main()
