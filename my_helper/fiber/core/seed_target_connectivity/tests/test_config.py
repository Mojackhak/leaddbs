"""Configuration contract tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from my_helper.fiber.core.seed_target_connectivity.config import load_config, resolve_config
from my_helper.fiber.core.seed_target_connectivity.errors import ConfigurationError


class ConfigTests(unittest.TestCase):
    def test_minimal_config_uses_only_algorithmic_defaults(self) -> None:
        config = resolve_config({"schema_version": 1})

        self.assertEqual(config.schema_version, 1)
        self.assertIsNone(config.seed.probability_threshold)
        self.assertIsNone(config.targets.probability_threshold)
        self.assertEqual(dict(config.targets.roi_thresholds), {})
        self.assertEqual(config.intersection.method, "segment_aware_voxel_traversal")
        self.assertEqual(config.execution.fiber_chunk_size, 100_000)
        self.assertTrue(config.execution.cache_membership)
        self.assertTrue(config.ranking.enabled)

    def test_resolves_explicit_thresholds_and_execution_settings(self) -> None:
        config = resolve_config(
            {
                "schema_version": 1,
                "seed": {"probability_threshold": 0.25},
                "targets": {
                    "probability_threshold": 0.3,
                    "roi_thresholds": {"group/region": 0.7},
                },
                "intersection": {"method": "segment_aware_voxel_traversal"},
                "execution": {"fiber_chunk_size": 17, "cache_membership": False},
                "ranking": {"enabled": False},
            }
        )

        self.assertEqual(config.seed.probability_threshold, 0.25)
        self.assertEqual(config.targets.probability_threshold, 0.3)
        self.assertEqual(config.targets.roi_thresholds["group/region"], 0.7)
        self.assertEqual(config.execution.fiber_chunk_size, 17)
        self.assertFalse(config.execution.cache_membership)
        self.assertFalse(config.ranking.enabled)

    def test_rejects_unknown_fields_at_every_level(self) -> None:
        for document in (
            {"schema_version": 1, "unknown": True},
            {"schema_version": 1, "seed": {"unknown": True}},
            {"schema_version": 1, "targets": {"unknown": True}},
            {"schema_version": 1, "execution": {"unknown": True}},
        ):
            with self.subTest(document=document):
                with self.assertRaisesRegex(ConfigurationError, "Additional properties"):
                    resolve_config(document)

    def test_rejects_invalid_schema_version_thresholds_and_chunk_size(self) -> None:
        invalid_documents = (
            {"schema_version": 2},
            {"schema_version": 1, "seed": {"probability_threshold": 0.0}},
            {"schema_version": 1, "seed": {"probability_threshold": 1.01}},
            {"schema_version": 1, "targets": {"probability_threshold": -0.1}},
            {
                "schema_version": 1,
                "targets": {"roi_thresholds": {"group/region": 0.0}},
            },
            {"schema_version": 1, "execution": {"fiber_chunk_size": 0}},
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ConfigurationError):
                    resolve_config(document)

    def test_rejects_non_mapping_documents(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "YAML object"):
            resolve_config(["not", "a", "mapping"])

    def test_load_config_rejects_duplicate_yaml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                "schema_version: 1\nexecution:\n  fiber_chunk_size: 10\n  fiber_chunk_size: 20\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "duplicate key"):
                load_config(path)

    def test_load_config_records_stable_resolved_mapping_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text("schema_version: 1\n", encoding="utf-8")

            first = load_config(path)
            second = load_config(path)

        self.assertEqual(first.resolved_mapping, second.resolved_mapping)
        self.assertEqual(first.configuration_hash, second.configuration_hash)
        self.assertEqual(len(first.configuration_hash), 64)


if __name__ == "__main__":
    unittest.main()
