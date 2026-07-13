"""Schema version 2 batch configuration contract tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from my_helper.fiber.core.seed_target_connectivity import config as config_module
from my_helper.fiber.core.seed_target_connectivity.errors import ConfigurationError


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _document(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "inputs": {
                "target_atlas_root": "atlas",
                "seed_rois": {"rh": "seeds/right.nii.gz", "lh": "seeds/left.nii.gz"},
                "connectome": "connectome",
            },
            "output": {
                "output_root": "results",
                "run_name": "dTOR__HybraPD__STNSNrplus",
            },
            "seed": {"probability_threshold": None},
            "targets": {
                "probability_threshold": 0.25,
                "roi_thresholds": {"group/region": 0.5},
            },
            "execution": {"fiber_chunk_size": 17, "cache_membership": False},
            "ranking": {"enabled": False},
        }

    def _call_resolve(self, document: object):
        try:
            return config_module.resolve_config(document, base_dir=self.root)
        except TypeError as exc:
            if "base_dir" not in str(exc):
                raise
            return config_module.resolve_config(document)

    def _resolve(self, document: object):
        try:
            return self._call_resolve(document)
        except ConfigurationError as exc:
            self.fail(f"schema version 2 configuration should resolve: {exc}")

    def test_resolves_complete_batch_with_deterministic_seed_order(self) -> None:
        batch = self._resolve(self._document())

        self.assertEqual(batch.schema_version, 2)
        self.assertEqual(tuple(batch.inputs.seed_rois), ("lh", "rh"))
        self.assertEqual(batch.inputs.target_atlas_root, (self.root / "atlas").resolve())
        self.assertEqual(batch.inputs.connectome, (self.root / "connectome").resolve())
        self.assertEqual(batch.output.output_root, (self.root / "results").resolve())
        self.assertEqual(batch.output.cache_root, batch.output.output_root.parent / ".cache")
        self.assertEqual(batch.output.run_name, "dTOR__HybraPD__STNSNrplus")
        self.assertEqual(batch.targets.probability_threshold, 0.25)
        self.assertEqual(batch.execution.fiber_chunk_size, 17)
        self.assertFalse(batch.execution.cache_membership)
        self.assertFalse(batch.ranking.enabled)
        self.assertNotIn("intersection", batch.resolved_mapping)
        self.assertEqual(len(batch.batch_configuration_hash), 64)

    def test_load_config_resolves_paths_against_yaml_parent(self) -> None:
        path = self.root / "configs" / "batch.yaml"
        path.parent.mkdir()
        path.write_text(
            """schema_version: 2
inputs:
  target_atlas_root: ../atlas
  seed_rois:
    lh: ../seeds/left.nii.gz
    rh: ../seeds/right.nii.gz
  connectome: ../connectome
output:
  output_root: ../results
  run_name: bilateral
""",
            encoding="utf-8",
        )

        try:
            batch = config_module.load_config(path)
        except ConfigurationError as exc:
            self.fail(f"schema version 2 YAML should load: {exc}")

        self.assertEqual(batch.inputs.target_atlas_root, (self.root / "atlas").resolve())
        self.assertEqual(batch.inputs.seed_rois["lh"], (self.root / "seeds/left.nii.gz").resolve())
        self.assertEqual(batch.output.output_root, (self.root / "results").resolve())

    def test_effective_hash_excludes_sibling_seed_and_publication_paths(self) -> None:
        first_document = self._document()
        second_document = self._document()
        second_document["inputs"] = {
            **dict(second_document["inputs"]),
            "seed_rois": {"lh": "seeds/changed-left.nii.gz", "rh": "seeds/right.nii.gz"},
        }
        second_document["output"] = {
            "output_root": "other-results",
            "run_name": "other-name",
        }
        first = self._resolve(first_document)
        second = self._resolve(second_document)
        resolver = getattr(config_module, "effective_config", None)
        if resolver is None:
            self.fail("effective_config must resolve one named seed")

        first_right = resolver(first, "rh")
        second_right = resolver(second, "rh")

        self.assertNotEqual(first.batch_configuration_hash, second.batch_configuration_hash)
        self.assertEqual(
            first_right.effective_configuration_hash,
            second_right.effective_configuration_hash,
        )
        self.assertEqual(first_right.configuration_hash, first_right.effective_configuration_hash)
        self.assertEqual(first_right.seed_name, "rh")

    def test_rejects_version_one_intersection_unknown_and_missing_inputs(self) -> None:
        invalid_documents = (
            {"schema_version": 1},
            {**self._document(), "intersection": {"method": "segment_aware_voxel_traversal"}},
            {**self._document(), "unknown": True},
            {"schema_version": 2, "output": self._document()["output"]},
            {"schema_version": 2, "inputs": self._document()["inputs"]},
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ConfigurationError):
                    self._call_resolve(document)

    def test_rejects_empty_or_unsafe_seed_and_run_names(self) -> None:
        invalid_names = ("", ".", "..", "left/right", "left side")
        for name in invalid_names:
            with self.subTest(seed_name=name):
                document = self._document()
                document["inputs"] = {
                    **dict(document["inputs"]),
                    "seed_rois": {name: "seed.nii.gz"},
                }
                with self.assertRaises(ConfigurationError):
                    self._call_resolve(document)
            with self.subTest(run_name=name):
                document = self._document()
                document["output"] = {
                    "output_root": "results",
                    "run_name": name,
                }
                with self.assertRaises(ConfigurationError):
                    self._call_resolve(document)

    def test_rejects_invalid_threshold_chunk_and_empty_seed_mapping(self) -> None:
        invalid_documents = []
        for update in (
            {"seed": {"probability_threshold": 0.0}},
            {"targets": {"probability_threshold": 1.01}},
            {"execution": {"fiber_chunk_size": 0}},
        ):
            invalid_documents.append({**self._document(), **update})
        empty = self._document()
        empty["inputs"] = {**dict(empty["inputs"]), "seed_rois": {}}
        invalid_documents.append(empty)
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ConfigurationError):
                    self._call_resolve(document)

    def test_load_config_rejects_duplicate_yaml_keys(self) -> None:
        path = self.root / "config.yaml"
        path.write_text(
            """schema_version: 2
inputs:
  target_atlas_root: atlas
  seed_rois:
    lh: left.nii.gz
  connectome: connectome
output:
  output_root: results
  run_name: first
  run_name: second
""",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ConfigurationError, "duplicate key"):
            config_module.load_config(path)


if __name__ == "__main__":
    unittest.main()
