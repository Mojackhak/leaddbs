"""Adversarial tests for scientific cache identity and artifact loading."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from dual_frequency.cache import (
    ArtifactStore,
    ArtifactValidationError,
    CacheCorruption,
    CacheIdentityError,
    CacheIdentityMismatch,
    CacheItem,
    ContentAddressedCache,
    ScientificCacheKey,
    sha256_file,
)
from dual_frequency.contracts import ArtifactRef, AxisRef


def _key(**changes: object) -> ScientificCacheKey:
    values: dict[str, object] = {
        "geometry_hash": "1" * 64,
        "stimulation_hash": "2" * 64,
        "component_frequency_hash": "3" * 64,
        "transform_hash": "4" * 64,
        "connectome_feature_hash": "5" * 64,
        "backend_name": "peak_efield",
        "backend_version": "2.1",
        "scientific_parameter_hashes": (("coverage", "6" * 64), ("tau", "7" * 64)),
    }
    values.update(changes)
    return ScientificCacheKey(**values)


class ScientificCacheIdentityTest(unittest.TestCase):
    def test_identity_is_immutable_deterministic_and_excludes_runtime_state(self) -> None:
        first = _key()
        second = _key(
            scientific_parameter_hashes=(("tau", "7" * 64), ("coverage", "6" * 64))
        )
        self.assertEqual(first, second)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(len(first.digest), 64)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first.backend_version = "changed"

        excluded_contexts = (
            {"scale": "mds_iii", "endpoint": "reference"},
            {"scale": "mds_iv", "endpoint": "addon"},
            {"run": "run-a", "workers": 1, "retries": 0, "task_order": (1, 2)},
            {"run": "run-b", "workers": 8, "retries": 9, "task_order": (2, 1)},
        )
        self.assertEqual({first.digest for _context in excluded_contexts}, {first.digest})
        self.assertTrue(
            {"scale", "endpoint", "run", "workers", "retries", "task_order"}.isdisjoint(
                first.as_dict()
            )
        )

    def test_every_scientific_category_changes_identity(self) -> None:
        base = _key()
        changes = (
            {"geometry_hash": "8" * 64},
            {"stimulation_hash": "8" * 64},
            {"component_frequency_hash": "8" * 64},
            {"transform_hash": "8" * 64},
            {"connectome_feature_hash": "8" * 64},
            {"backend_name": "oss_ppam"},
            {"backend_version": "2.2"},
            {"scientific_parameter_hashes": (("tau", "8" * 64),)},
        )
        self.assertEqual(len({base.digest, *(_key(**change).digest for change in changes)}), 9)

    def test_identity_rejects_bad_hashes_and_duplicate_parameter_names(self) -> None:
        with self.assertRaises(CacheIdentityError):
            _key(geometry_hash="short")
        with self.assertRaises(CacheIdentityError):
            _key(scientific_parameter_hashes=())
        with self.assertRaises(CacheIdentityError):
            _key(
                scientific_parameter_hashes=(("tau", "6" * 64), ("tau", "7" * 64))
            )


class ContentAddressedCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.cache = ContentAddressedCache(self.root / "cache")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _source(self, name: str, content: bytes) -> Path:
        path = self.sources / name
        path.write_bytes(content)
        return path

    def test_atomic_publish_manifest_and_exact_reuse(self) -> None:
        matrix = self._source("matrix.npy", b"matrix-content")
        axis = self._source("axis.json", b"axis-content")
        key = _key()
        items = (CacheItem("fiber-2", "b" * 64), CacheItem("fiber-1", "a" * 64))

        first = self.cache.publish(
            key,
            {"arrays/matrix.npy": matrix, "axes/axis.json": axis},
            items=items,
        )
        self.assertFalse(first.reused)
        self.assertEqual(first.path, self.cache.entry_path(key))
        self.assertTrue(first.manifest_path.is_file())
        manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["scientific_identity"], key.digest)
        self.assertEqual(ScientificCacheKey.from_dict(manifest["scientific_cache_key"]), key)
        self.assertEqual(
            {item["relative_path"] for item in manifest["files"]},
            {"arrays/matrix.npy", "axes/axis.json"},
        )
        self.assertEqual(
            {item["sha256"] for item in manifest["files"]},
            {sha256_file(matrix), sha256_file(axis)},
        )

        second = self.cache.publish(
            key,
            {"arrays/matrix.npy": matrix, "axes/axis.json": axis},
            items=items,
        )
        self.assertTrue(second.reused)
        self.assertEqual(first.files, second.files)
        self.assertEqual(first.items, second.items)
        self.assertFalse(tuple(first.path.parent.glob(f".{key.digest}.tmp-*")))

    def test_same_identity_with_different_content_is_rejected_without_overwrite(self) -> None:
        source = self._source("artifact.bin", b"original")
        key = _key()
        entry = self.cache.publish(key, {"artifact.bin": source})
        published_hash = sha256_file(entry.file_path("artifact.bin"))
        source.write_bytes(b"changed")
        with self.assertRaises(CacheIdentityMismatch):
            self.cache.publish(key, {"artifact.bin": source})
        self.assertEqual(sha256_file(entry.file_path("artifact.bin")), published_hash)

    def test_partial_failure_leaves_no_entry_or_staging_directory(self) -> None:
        source = self._source("artifact.bin", b"content")
        key = _key(geometry_hash="8" * 64)
        with mock.patch("dual_frequency.cache.store.shutil.copy2", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                self.cache.publish(key, {"artifact.bin": source})
        self.assertFalse(self.cache.entry_path(key).exists())
        self.assertFalse(tuple(self.cache.entry_path(key).parent.glob(f".{key.digest}.tmp-*")))

    def test_corruption_and_incomplete_manifest_are_rejected(self) -> None:
        source = self._source("artifact.bin", b"content")
        key = _key()
        entry = self.cache.publish(key, {"artifact.bin": source})
        entry.file_path("artifact.bin").write_bytes(b"corrupt")
        with self.assertRaises(CacheCorruption):
            self.cache.resolve(key)

        second_key = _key(geometry_hash="9" * 64)
        second = self.cache.publish(second_key, {"artifact.bin": source})
        (second.path / "undeclared.bin").write_bytes(b"extra")
        with self.assertRaises(CacheCorruption):
            self.cache.resolve(second_key)

    def test_manifest_scientific_identity_tampering_is_rejected(self) -> None:
        source = self._source("artifact.bin", b"content")
        key = _key()
        entry = self.cache.publish(key, {"artifact.bin": source})
        payload = json.loads(entry.manifest_path.read_text(encoding="utf-8"))
        payload["scientific_identity"] = "f" * 64
        entry.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(CacheIdentityMismatch):
            self.cache.resolve(key)

    def test_reindexed_view_requires_exact_unique_items_and_hashes(self) -> None:
        source = self._source("artifact.bin", b"content")
        key = _key()
        items = (
            CacheItem("a", "a" * 64),
            CacheItem("b", "b" * 64),
            CacheItem("c", "c" * 64),
        )
        self.cache.publish(key, {"artifact.bin": source}, items=items)
        view = self.cache.reindexed_view(key, (items[2], items[0], items[1]))
        self.assertEqual(view.source_indices, (2, 0, 1))
        self.assertEqual(view.as_manifest()["source_indices"], [2, 0, 1])
        self.assertEqual(view.as_manifest()["scientific_identity"], key.digest)

        cases = (
            (items[0], items[0], items[2]),
            (items[0], items[1]),
            (items[0], items[1], CacheItem("extra", "d" * 64)),
            (items[0], CacheItem("b", "e" * 64), items[2]),
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(CacheIdentityMismatch):
                self.cache.reindexed_view(key, case)

    def test_duplicate_source_items_are_rejected(self) -> None:
        source = self._source("artifact.bin", b"content")
        with self.assertRaises(CacheIdentityMismatch):
            self.cache.publish(
                _key(),
                {"artifact.bin": source},
                items=(CacheItem("same", "a" * 64), CacheItem("same", "a" * 64)),
            )


class ArtifactStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.allowed = self.root / "allowed"
        self.outside = self.root / "outside"
        self.allowed.mkdir()
        self.outside.mkdir()
        self.subjects = AxisRef("subjects", 2, "a" * 64)
        self.features = AxisRef("features", 3, "b" * 64)
        self.array = np.arange(6, dtype=np.float64).reshape(2, 3)
        self.path = self.allowed / "array.npy"
        np.save(self.path, self.array, allow_pickle=False)
        self.artifact = self._artifact(self.path)
        self.store = ArtifactStore((self.allowed,))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _artifact(
        self,
        path: Path,
        *,
        dtype: str = "float64",
        shape: tuple[int, ...] = (2, 3),
        axes: tuple[AxisRef, ...] | None = None,
        units: str | None = "V/m",
        space: str | None = "MNI152NLin2009bAsym",
    ) -> ArtifactRef:
        axes = axes or (self.subjects, self.features)
        return ArtifactRef(
            kind="exposure_matrix",
            schema_version="array_v1",
            uri=path.as_uri(),
            sha256=sha256_file(path),
            dtype=dtype,
            shape=shape,
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space=space,
            producer_id="cache_test",
            producer_version="1",
        )

    def _materialize(self, artifact: ArtifactRef | object | None = None, **changes: object):
        requirements: dict[str, object] = {
            "expected_dtype": "float64",
            "expected_shape": (2, 3),
            "expected_axes": (self.subjects, self.features),
            "expected_units": "V/m",
            "expected_space": "MNI152NLin2009bAsym",
        }
        requirements.update(changes)
        return self.store.materialize(
            self.artifact if artifact is None else artifact,
            **requirements,
        )

    def test_materializes_verified_array_as_read_only(self) -> None:
        output = self._materialize()
        np.testing.assert_array_equal(output, self.array)
        self.assertEqual(output.dtype, np.dtype("float64"))
        self.assertFalse(output.flags.writeable)

    def test_rejects_bare_paths_network_uris_and_out_of_root_files(self) -> None:
        with self.assertRaises(TypeError):
            self._materialize(self.path)
        with self.assertRaises(ArtifactValidationError):
            self._materialize(dataclasses.replace(self.artifact, uri=f"file://host{self.path}"))

        outside_path = self.outside / "array.npy"
        np.save(outside_path, self.array, allow_pickle=False)
        with self.assertRaises(ArtifactValidationError):
            self._materialize(self._artifact(outside_path))

        link = self.allowed / "outside.npy"
        link.symlink_to(outside_path)
        with self.assertRaises(ArtifactValidationError):
            self._materialize(self._artifact(link))

    def test_rejects_hash_corruption(self) -> None:
        corrupted_ref = dataclasses.replace(self.artifact, sha256="f" * 64)
        with self.assertRaises(ArtifactValidationError):
            self._materialize(corrupted_ref)

    def test_rejects_each_explicit_metadata_mismatch(self) -> None:
        other_subjects = AxisRef("other_subjects", 2, "c" * 64)
        cases = (
            {"expected_dtype": "float32"},
            {"expected_shape": (3, 2)},
            {"expected_axes": (other_subjects, self.features)},
            {"expected_axes": (self.features, self.subjects)},
            {"expected_units": "mV/mm"},
            {"expected_space": "native"},
        )
        for requirements in cases:
            with self.subTest(requirements=requirements), self.assertRaises(
                ArtifactValidationError
            ):
                self._materialize(**requirements)

    def test_rejects_file_array_that_disagrees_with_artifact_metadata(self) -> None:
        float32_path = self.allowed / "float32.npy"
        np.save(float32_path, self.array.astype(np.float32), allow_pickle=False)
        dishonest = ArtifactRef(
            kind=self.artifact.kind,
            schema_version=self.artifact.schema_version,
            uri=float32_path.as_uri(),
            sha256=sha256_file(float32_path),
            dtype=self.artifact.dtype,
            shape=self.artifact.shape,
            axis_refs=self.artifact.axis_refs,
            axis_hashes=self.artifact.axis_hashes,
            units=self.artifact.units,
            space=self.artifact.space,
            producer_id=self.artifact.producer_id,
            producer_version=self.artifact.producer_version,
        )
        with self.assertRaises(ArtifactValidationError):
            self._materialize(dishonest)


if __name__ == "__main__":
    unittest.main()
