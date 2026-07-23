"""Adversarial tests for scientific cache identity and artifact loading."""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np
import dual_frequency.cache.store as cache_store

from dual_frequency.cache import (
    ArtifactPublicationError,
    ArtifactStore,
    ArtifactValidationError,
    CacheCorruption,
    CacheFileMetadata,
    CacheIdentityError,
    CacheIdentityMismatch,
    CacheItem,
    CacheShardInterval,
    CachedFile,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    ScientificCacheKey,
    sha256_file,
)
from dual_frequency.contracts import ArtifactRef, AxisRef, IndexedArrayView


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

    def _array_source(self, name: str, value: np.ndarray) -> Path:
        path = self.sources / name
        np.save(path, value, allow_pickle=False)
        return path

    def test_atomic_publish_manifest_and_exact_reuse(self) -> None:
        matrix_value = np.arange(6, dtype=np.float32).reshape(2, 3)
        matrix = self._array_source("matrix.npy", matrix_value)
        axis = self._source("axis.json", b"axis-content")
        key = _key()
        items = (CacheItem("fiber-2", "b" * 64), CacheItem("fiber-1", "a" * 64))
        rows = AxisRef("rows", 2, "c" * 64)
        columns = AxisRef("columns", 3, "d" * 64)

        first = self.cache.publish(
            key,
            {"arrays/matrix.npy": matrix, "axes/axis.json": axis},
            items=items,
            metadata={
                "arrays/matrix.npy": CacheFileMetadata(
                    dtype="float32",
                    shape=(2, 3),
                    axes=(rows, columns),
                    units="V/m",
                    space="canonical_grid",
                )
            },
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
            metadata={
                "arrays/matrix.npy": CacheFileMetadata(
                    dtype="float32",
                    shape=(2, 3),
                    axes=(rows, columns),
                    units="V/m",
                    space="canonical_grid",
                )
            },
        )
        self.assertTrue(second.reused)
        self.assertEqual(first.files, second.files)
        self.assertEqual(first.items, second.items)
        self.assertFalse(tuple(first.path.parent.glob(f".{key.digest}.tmp-*")))

    def test_generated_publish_writes_once_without_copy_or_post_write_hash(self) -> None:
        key = _key(backend_name="generated_jitter_block")
        rows = AxisRef("replicates", 2, "c" * 64)
        columns = AxisRef("features", 3, "d" * 64)
        value = np.arange(6, dtype=np.float32).reshape(2, 3)
        producer_calls = 0

        def producer(staging: Path) -> tuple[CachedFile, ...]:
            nonlocal producer_calls
            producer_calls += 1
            path = staging / "block.npy"
            digest = hashlib.sha256()

            class HashingStream:
                def __init__(self, stream):
                    self.stream = stream

                def write(self, payload: bytes) -> int:
                    digest.update(payload)
                    return self.stream.write(payload)

                def flush(self) -> None:
                    self.stream.flush()

            with path.open("xb") as stream:
                writer = HashingStream(stream)
                np.lib.format.write_array(writer, value, allow_pickle=False)
                writer.flush()
                os.fsync(stream.fileno())
            return (
                CachedFile(
                    relative_path="block.npy",
                    sha256=digest.hexdigest(),
                    size_bytes=path.stat().st_size,
                    metadata=CacheFileMetadata(
                        dtype="float32",
                        shape=(2, 3),
                        axes=(rows, columns),
                        units="V/m",
                        space="synthetic",
                    ),
                ),
            )

        with mock.patch.object(
            ContentAddressedCache,
            "_copy_and_hash",
            side_effect=AssertionError("generated publication cannot copy payloads"),
        ):
            first = self.cache.publish_generated(key, producer)
            second = self.cache.publish_generated(
                key,
                lambda _staging: (_ for _ in ()).throw(
                    AssertionError("cache hit cannot invoke the producer")
                ),
            )

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(producer_calls, 1)
        np.testing.assert_array_equal(
            np.load(first.file_path("block.npy"), allow_pickle=False),
            value,
        )

    def test_generated_publish_failure_removes_staging_generation(self) -> None:
        key = _key(backend_name="failed_generated_jitter_block")

        def producer(staging: Path) -> tuple[CachedFile, ...]:
            (staging / "partial.bin").write_bytes(b"partial")
            raise OSError("producer failed")

        with self.assertRaisesRegex(OSError, "producer failed"):
            self.cache.publish_generated(key, producer)
        self.assertFalse(self.cache.entry_path(key).exists())
        self.assertFalse(
            tuple(
                self.cache.entry_path(key).parent.glob(
                    f".{key.digest}.tmp-*"
                )
            )
        )

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
        with mock.patch.object(
            ContentAddressedCache,
            "_copy_and_hash",
            side_effect=OSError("boom"),
        ):
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
            ContentAddressedCache(self.root / "cache").resolve(key)

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

    def test_direct_copy_is_verified_once_per_process_instance(self) -> None:
        source = self._source("artifact.bin", b"portable-content")
        key = _key(kind="fiber_exposures")
        source_cache = ContentAddressedCache(self.root / "source-cache")
        source_entry = source_cache.publish(key, {"artifact.bin": source})

        copied_cache = ContentAddressedCache(self.root / "copied-cache")
        destination = copied_cache.entry_path(key)
        destination.parent.mkdir(parents=True)
        shutil.copytree(source_entry.path, destination)
        (destination / "._artifact.bin").write_bytes(b"appledouble-metadata")
        (destination / "._manifest.json").write_bytes(b"appledouble-metadata")
        with mock.patch(
            "dual_frequency.cache.store.sha256_file",
            wraps=sha256_file,
        ) as checksum:
            first = copied_cache.resolve(key)
            second = copied_cache.resolve(key)
            portable = copied_cache.resolve_identity(key.kind, key.digest)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNotNone(portable)
        self.assertEqual(portable.key, key)
        self.assertEqual(checksum.call_count, 1)

        with mock.patch(
            "dual_frequency.cache.store.sha256_file",
            wraps=sha256_file,
        ) as checksum:
            ContentAddressedCache(self.root / "copied-cache").resolve(key)
        self.assertEqual(checksum.call_count, 1)

    def test_partial_direct_copy_fails_closed_without_mutation(self) -> None:
        source = self._source("artifact.bin", b"portable-content")
        key = _key(kind="voxel_exposures")
        source_entry = ContentAddressedCache(self.root / "source-cache").publish(
            key,
            {"artifact.bin": source},
        )
        copied_cache = ContentAddressedCache(self.root / "copied-cache")
        destination = copied_cache.entry_path(key)
        destination.mkdir(parents=True)
        shutil.copy2(source_entry.manifest_path, destination / "manifest.json")
        with self.assertRaises(CacheCorruption):
            copied_cache.resolve(key)
        self.assertTrue(destination.is_dir())
        self.assertTrue((destination / "manifest.json").is_file())

    def test_array_structure_and_complete_shard_intervals_are_verified(self) -> None:
        key = _key(kind="jitter_exposures")
        logical_axis = AxisRef("replicates", 4, "e" * 64)
        first = self._array_source("part-000.npy", np.array([1.0, 2.0]))
        second = self._array_source("part-001.npy", np.array([3.0, 4.0]))
        metadata = {
            "parts/part-000.npy": CacheFileMetadata(
                dtype="float64",
                shape=(2,),
                axes=(logical_axis,),
                units="V/m",
                space="canonical_grid",
                shard_interval=CacheShardInterval("exposure", "replicates", 0, 2),
            ),
            "parts/part-001.npy": CacheFileMetadata(
                dtype="float64",
                shape=(2,),
                axes=(logical_axis,),
                units="V/m",
                space="canonical_grid",
                shard_interval=CacheShardInterval("exposure", "replicates", 2, 4),
            ),
        }
        entry = self.cache.publish(
            key,
            {"parts/part-000.npy": first, "parts/part-001.npy": second},
            metadata=metadata,
        )
        self.assertEqual(entry.path, self.cache.entry_path(key))

        payload = json.loads(entry.manifest_path.read_text(encoding="utf-8"))
        payload["files"][1]["shard_interval"]["start"] = 3
        entry.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(CacheCorruption):
            ContentAddressedCache(self.root / "cache").resolve(key)

    def test_numpy_payload_requires_exact_declared_header(self) -> None:
        array = self._array_source("values.npy", np.array([1.0, 2.0]))
        axis = AxisRef("values", 2, "f" * 64)
        with self.assertRaises(CacheIdentityMismatch):
            self.cache.publish(_key(), {"values.npy": array})
        with self.assertRaises(CacheCorruption):
            self.cache.publish(
                _key(),
                {"values.npy": array},
                metadata={
                    "values.npy": CacheFileMetadata(
                        dtype="float32",
                        shape=(2,),
                        axes=(axis,),
                    )
                },
            )

    def test_cross_instance_producer_lease_serializes_one_publication(self) -> None:
        source = self._source("artifact.bin", b"content")
        key = _key(kind="voxel_exposures")
        produced: list[int] = []

        def publish(index: int) -> bool:
            cache = ContentAddressedCache(self.root / "lease-cache")
            with cache.producer_lease(key, timeout_seconds=2.0) as owner:
                if owner:
                    produced.append(index)
                    cache.publish(key, {"artifact.bin": source})
                return owner

        with ThreadPoolExecutor(max_workers=2) as pool:
            owners = tuple(pool.map(publish, (1, 2)))
        self.assertEqual(sum(owners), 1)
        self.assertEqual(len(produced), 1)
        self.assertIsNotNone(ContentAddressedCache(self.root / "lease-cache").resolve(key))

    def test_stale_producer_lock_is_quarantined_before_recovery(self) -> None:
        cache = ContentAddressedCache(self.root / "stale-cache")
        key = _key(kind="fiber_exposures")
        destination = cache.entry_path(key)
        destination.parent.mkdir(parents=True)
        lock = destination.parent / f".{key.digest}.produce.lock"
        lock.write_text("pid=999999999\n", encoding="ascii")
        orphan = destination.parent / f".{key.digest}.tmp-interrupted"
        orphan.mkdir()
        (orphan / "partial.bin").write_bytes(b"partial")
        other_key = _key(kind="voxel_exposures")
        other_orphan = destination.parent / f".{other_key.digest}.tmp-unrelated"
        other_orphan.mkdir()
        with cache.producer_lease(key, timeout_seconds=1.0) as owner:
            self.assertTrue(owner)
        self.assertFalse(lock.exists())
        self.assertEqual(len(tuple(destination.parent.glob(f"{lock.name}.stale-*"))), 1)
        quarantines = tuple(
            destination.parent.glob(f".{key.digest}.orphan-*")
        )
        self.assertEqual(len(quarantines), 1)
        self.assertEqual(
            (quarantines[0] / "payload" / "partial.bin").read_bytes(),
            b"partial",
        )
        self.assertFalse(orphan.exists())
        self.assertTrue(other_orphan.is_dir())

    def test_live_producer_refreshes_wait_deadline_until_publication(self) -> None:
        cache = ContentAddressedCache(self.root / "live-cache")
        source = self._source("live-artifact.bin", b"content")
        key = _key(kind="voxel_exposures")
        destination = cache.entry_path(key)
        destination.parent.mkdir(parents=True)
        lock = destination.parent / f".{key.digest}.produce.lock"
        lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")
        active_staging = destination.parent / f".{key.digest}.tmp-active"
        active_staging.mkdir()

        def delayed_publish() -> None:
            time.sleep(0.05)
            ContentAddressedCache(self.root / "live-cache").publish(
                key,
                {"artifact.bin": source},
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(delayed_publish)
            with cache.producer_lease(key, timeout_seconds=0.01) as owner:
                self.assertFalse(owner)
            future.result()
        self.assertTrue(active_staging.is_dir())
        self.assertFalse(
            tuple(destination.parent.glob(f".{key.digest}.orphan-*"))
        )

    def test_stale_recovery_serializes_two_contenders(self) -> None:
        root = self.root / "contended-stale-cache"
        cache = ContentAddressedCache(root)
        source = self._source("contended-artifact.bin", b"content")
        key = _key(kind="fiber_exposures")
        destination = cache.entry_path(key)
        destination.parent.mkdir(parents=True)
        lock = destination.parent / f".{key.digest}.produce.lock"
        lock.write_text("pid=999999999\n", encoding="ascii")
        orphan = destination.parent / f".{key.digest}.tmp-interrupted"
        orphan.mkdir()
        entered = threading.Event()
        release = threading.Event()
        recovery_calls: list[Path] = []
        original = ContentAddressedCache._quarantine_orphan_staging

        def delayed_recovery(path: Path) -> None:
            recovery_calls.append(path)
            entered.set()
            self.assertTrue(release.wait(timeout=2.0))
            original(path)

        def publish() -> bool:
            contender = ContentAddressedCache(root)
            with contender.producer_lease(key, timeout_seconds=2.0) as owner:
                if owner:
                    contender.publish(key, {"artifact.bin": source})
                return owner

        with mock.patch.object(
            ContentAddressedCache,
            "_quarantine_orphan_staging",
            side_effect=delayed_recovery,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(publish)
                self.assertTrue(entered.wait(timeout=2.0))
                second = pool.submit(publish)
                time.sleep(0.05)
                release.set()
                owners = (first.result(), second.result())
        self.assertEqual(sum(owners), 1)
        self.assertEqual(recovery_calls, [lock])
        self.assertIsNotNone(ContentAddressedCache(root).resolve(key))

    def test_stale_recovery_rejects_replaced_lock_inode(self) -> None:
        cache = ContentAddressedCache(self.root / "replaced-lock-cache")
        key = _key(kind="fiber_exposures")
        destination = cache.entry_path(key)
        destination.parent.mkdir(parents=True)
        lock = destination.parent / f".{key.digest}.produce.lock"
        lock.write_text("pid=999999999\n", encoding="ascii")
        orphan = destination.parent / f".{key.digest}.tmp-active"
        orphan.mkdir()
        replaced = lock.with_name(f"{lock.name}.replaced")
        changed = False

        def replace_before_validation(descriptor: int, operation: int) -> None:
            nonlocal changed
            if operation == fcntl.LOCK_EX | fcntl.LOCK_NB and not changed:
                changed = True
                os.replace(lock, replaced)
                lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")

        with mock.patch.object(
            cache_store.fcntl,
            "flock",
            side_effect=replace_before_validation,
        ):
            self.assertFalse(cache._quarantine_stale_lock(lock))
        self.assertTrue(lock.is_file())
        self.assertTrue(orphan.is_dir())
        self.assertFalse(
            tuple(destination.parent.glob(f".{key.digest}.orphan-*"))
        )

    def test_duplicate_source_items_are_rejected(self) -> None:
        source = self._source("artifact.bin", b"content")
        with self.assertRaises(CacheIdentityMismatch):
            self.cache.publish(
                _key(),
                {"artifact.bin": source},
                items=(CacheItem("same", "a" * 64), CacheItem("same", "a" * 64)),
            )


class RunScopedArtifactPublisherTest(unittest.TestCase):
    def test_exact_reuse_and_symlink_targets_are_handled_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publisher = RunScopedArtifactPublisher(root / "output", "test", "1")
            axis = AxisRef("items", 2, "a" * 64)
            array = np.array([1.0, 2.0])
            first = publisher.array(
                "values.npy",
                array,
                kind="values",
                axes=(axis,),
                units=None,
                space=None,
            )
            second = publisher.array(
                "values.npy",
                array.copy(),
                kind="values",
                axes=(axis,),
                units=None,
                space=None,
            )
            self.assertEqual(first.sha256, second.sha256)
            metadata_path = publisher.root / "values.npy.artifact.json"
            self.assertTrue(metadata_path.is_file())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["payload_sha256"], first.sha256)
            self.assertEqual(metadata["artifact"]["axes"][0]["sha256"], axis.sha256)

            semantic_changes = (
                {
                    "kind": "different_semantics",
                    "axes": (axis,),
                    "units": None,
                    "space": None,
                },
                {
                    "kind": "values",
                    "axes": (AxisRef("other_items", 2, "b" * 64),),
                    "units": None,
                    "space": None,
                },
                {
                    "kind": "values",
                    "axes": (axis,),
                    "units": "score",
                    "space": None,
                },
            )
            for changes in semantic_changes:
                with self.subTest(changes=changes), self.assertRaisesRegex(
                    ArtifactPublicationError,
                    "overwrite",
                ):
                    publisher.array("values.npy", array, **changes)

            outside = root / "outside.npy"
            np.save(outside, array, allow_pickle=False)
            target = publisher.root / "linked.npy"
            target.symlink_to(outside)
            with self.assertRaisesRegex(ArtifactPublicationError, "overwrite"):
                publisher.array(
                    "linked.npy",
                    array,
                    kind="values",
                    axes=(axis,),
                    units=None,
                    space=None,
                )
            np.testing.assert_array_equal(np.load(outside), array)

    def test_existing_payload_without_metadata_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            publisher = RunScopedArtifactPublisher(Path(temporary), "test", "1")
            axis = AxisRef("items", 2, "a" * 64)
            array = np.array([1.0, 2.0])
            publisher.array(
                "values.npy",
                array,
                kind="values",
                axes=(axis,),
                units="score",
                space="synthetic",
            )
            (publisher.root / "values.npy.artifact.json").unlink()
            with self.assertRaisesRegex(ArtifactPublicationError, "incomplete"):
                publisher.array(
                    "values.npy",
                    array,
                    kind="values",
                    axes=(axis,),
                    units="score",
                    space="synthetic",
                )

    def test_orphaned_publication_lock_is_not_removed_or_bypassed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            publisher = RunScopedArtifactPublisher(Path(temporary), "test", "1")
            lock = publisher.root / ".record.json.publish.lock"
            lock.write_text("pid=stale\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactPublicationError, "lock already exists"):
                publisher.document("record.json", {"status": "complete"}, kind="record")
            self.assertTrue(lock.is_file())
            self.assertFalse((publisher.root / "record.json").exists())


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
        self.document_payload = {
            "nested": {"enabled": True, "value": None},
            "sequence": [3, 1, 2],
            "status": "complete",
        }
        self.document_path = self.allowed / "document.json"
        self.document_path.write_text(
            json.dumps(self.document_payload, sort_keys=True),
            encoding="utf-8",
        )
        self.document_artifact = self._document_artifact(self.document_path)
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

    def _document_artifact(
        self,
        path: Path,
        *,
        kind: str = "run_record",
        schema_version: str = "dual_frequency_document_v1",
        dtype: str | None = None,
        shape: tuple[int, ...] | None = None,
        axes: tuple[AxisRef, ...] = (),
        units: str | None = None,
        space: str | None = None,
    ) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            schema_version=schema_version,
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

    def test_indexed_array_view_uses_verified_bounded_blocks(self) -> None:
        selected_subjects = AxisRef("selected_subjects", 2, "c" * 64)
        selected_features = AxisRef("selected_features", 2, "d" * 64)
        row_path = self.allowed / "row_positions.npy"
        column_path = self.allowed / "column_positions.npy"
        np.save(row_path, np.asarray([1, 0], dtype=np.int64), allow_pickle=False)
        np.save(column_path, np.asarray([2, 0], dtype=np.int64), allow_pickle=False)
        row_positions = self._artifact(
            row_path,
            dtype="int64",
            shape=(2,),
            axes=(selected_subjects,),
            units="index",
            space=None,
        )
        column_positions = self._artifact(
            column_path,
            dtype="int64",
            shape=(2,),
            axes=(selected_features,),
            units="index",
            space=None,
        )
        view = IndexedArrayView(
            parent=self.artifact,
            row_positions=row_positions,
            column_positions=column_positions,
            axis_refs=(selected_subjects, selected_features),
        )

        blocks = list(
            self.store.iter_indexed_array_view_blocks(
                view,
                block_columns=1,
            )
        )
        self.assertEqual([(start, stop) for start, stop, _ in blocks], [(0, 1), (1, 2)])
        self.assertTrue(all(block.shape == (2, 1) for _, _, block in blocks))
        self.assertTrue(all(not block.flags.writeable for _, _, block in blocks))

        expected = self.array[np.ix_([1, 0], [2, 0])]
        output = self.store.materialize_indexed_array_view(
            view,
            max_bytes=expected.nbytes,
            block_columns=1,
        )
        np.testing.assert_array_equal(output, expected)
        self.assertFalse(output.flags.writeable)
        with self.store.open_indexed_array_view(
            view,
            max_block_bytes=expected.nbytes,
        ) as reader:
            self.assertEqual(reader.shape, (2, 2))
            self.assertEqual(reader.ndim, 2)
            np.testing.assert_array_equal(reader[:, 0:1], expected[:, 0:1])
            np.testing.assert_array_equal(reader[1, :], expected[1, :])
            np.testing.assert_array_equal(
                reader[[1, 0], [1, 0]],
                expected[np.ix_([1, 0], [1, 0])],
            )
            with self.assertRaisesRegex(ArtifactValidationError, "implicit"):
                np.asarray(reader)
            with self.assertRaisesRegex(ArtifactValidationError, "selector"):
                reader[np.asarray([True, False]), :]
        with self.assertRaisesRegex(ArtifactValidationError, "closed"):
            reader[:, :]
        with self.store.open_indexed_array_view(
            view,
            max_block_bytes=np.dtype("float64").itemsize,
        ) as reader:
            with self.assertRaisesRegex(ArtifactValidationError, "block byte budget"):
                reader[:, 0:1]
        with self.assertRaisesRegex(ArtifactValidationError, "budget"):
            self.store.materialize_indexed_array_view(
                view,
                max_bytes=expected.nbytes - 1,
            )

    def test_indexed_array_view_rejects_duplicate_and_out_of_range_positions(self) -> None:
        selected_subjects = AxisRef("selected_subjects", 2, "c" * 64)
        for filename, values, message in (
            ("duplicate.npy", [1, 1], "duplicate"),
            ("outside.npy", [0, 2], "parent axis"),
        ):
            with self.subTest(filename=filename):
                path = self.allowed / filename
                np.save(path, np.asarray(values, dtype=np.int64), allow_pickle=False)
                positions = self._artifact(
                    path,
                    dtype="int64",
                    shape=(2,),
                    axes=(selected_subjects,),
                    units="index",
                    space=None,
                )
                view = IndexedArrayView(
                    parent=self.artifact,
                    row_positions=positions,
                    column_positions=None,
                    axis_refs=(selected_subjects, self.features),
                )
                with self.assertRaisesRegex(ArtifactValidationError, message):
                    list(
                        self.store.iter_indexed_array_view_blocks(
                            view,
                            block_columns=2,
                        )
                    )

    def test_materializes_verified_array_as_read_only_memory_map(self) -> None:
        output = self._materialize(mmap_mode="r")
        self.assertIsInstance(output, np.memmap)
        np.testing.assert_array_equal(output, self.array)
        self.assertFalse(output.flags.writeable)
        with self.assertRaisesRegex(ArtifactValidationError, "read-only"):
            self._materialize(mmap_mode="r+")

    def test_reuses_process_local_sha_only_while_file_signature_is_unchanged(self) -> None:
        with mock.patch.object(
            cache_store,
            "sha256_stream",
            wraps=cache_store.sha256_stream,
        ) as digest:
            np.testing.assert_array_equal(self._materialize(), self.array)
            np.testing.assert_array_equal(self._materialize(), self.array)
            self.assertEqual(digest.call_count, 1)

            np.save(self.path, self.array + 1.0, allow_pickle=False)
            with self.assertRaisesRegex(ArtifactValidationError, "SHA-256"):
                self._materialize()
            self.assertEqual(digest.call_count, 2)

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

    def test_materializes_verified_json_document_without_mutation(self) -> None:
        original_bytes = self.document_path.read_bytes()

        output = self.store.materialize_document(
            self.document_artifact,
            expected_kind="run_record",
        )

        self.assertEqual(output, self.document_payload)
        self.assertIsInstance(output, dict)
        self.assertEqual(self.document_path.read_bytes(), original_bytes)

    def test_document_reuses_process_local_sha_verification(self) -> None:
        with mock.patch.object(
            cache_store,
            "sha256_stream",
            wraps=cache_store.sha256_stream,
        ) as digest:
            first = self.store.materialize_document(
                self.document_artifact,
                expected_kind="run_record",
            )
            second = self.store.materialize_document(
                self.document_artifact,
                expected_kind="run_record",
            )
        self.assertEqual(first, second)
        self.assertEqual(digest.call_count, 1)

    def test_document_rejects_non_artifact_and_wrong_schema(self) -> None:
        with self.assertRaises(TypeError):
            self.store.materialize_document(
                self.document_path,
                expected_kind="run_record",
            )

        wrong_schema = dataclasses.replace(
            self.document_artifact,
            schema_version="dual_frequency_document_v2",
        )
        with self.assertRaises(ArtifactValidationError):
            self.store.materialize_document(wrong_schema, expected_kind="run_record")

    def test_document_rejects_wrong_kind(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            self.store.materialize_document(
                self.document_artifact,
                expected_kind="different_record",
            )

    def test_document_rejects_forbidden_metadata(self) -> None:
        item_axis = AxisRef("items", 1, "c" * 64)
        cases = (
            dataclasses.replace(
                self.document_artifact,
                dtype="float64",
                shape=(1,),
                axis_refs=(item_axis,),
                axis_hashes=(item_axis.sha256,),
            ),
            dataclasses.replace(self.document_artifact, units="score"),
            dataclasses.replace(self.document_artifact, space="native"),
        )
        for artifact in cases:
            with self.subTest(artifact=artifact), self.assertRaises(
                ArtifactValidationError
            ):
                self.store.materialize_document(artifact, expected_kind="run_record")

    def test_document_rejects_hash_corruption(self) -> None:
        corrupted_ref = dataclasses.replace(self.document_artifact, sha256="f" * 64)
        with self.assertRaises(ArtifactValidationError):
            self.store.materialize_document(corrupted_ref, expected_kind="run_record")

    def test_document_rejects_out_of_root_file(self) -> None:
        outside_path = self.outside / "document.json"
        outside_path.write_text('{"status":"complete"}', encoding="utf-8")
        outside_artifact = self._document_artifact(outside_path)

        with self.assertRaises(ArtifactValidationError):
            self.store.materialize_document(outside_artifact, expected_kind="run_record")

    def test_document_rejects_non_object_json(self) -> None:
        path = self.allowed / "array.json"
        path.write_text('["not", "an", "object"]', encoding="utf-8")
        artifact = self._document_artifact(path)

        with self.assertRaises(ArtifactValidationError):
            self.store.materialize_document(artifact, expected_kind="run_record")

    def test_document_rejects_invalid_utf8_and_json(self) -> None:
        cases = {
            "invalid-utf8.json": b'{"value":"\xff"}',
            "invalid-json.json": b'{"status":',
        }
        for filename, content in cases.items():
            with self.subTest(filename=filename):
                path = self.allowed / filename
                path.write_bytes(content)
                artifact = self._document_artifact(path)
                with self.assertRaises(ArtifactValidationError):
                    self.store.materialize_document(artifact, expected_kind="run_record")


if __name__ == "__main__":
    unittest.main()
