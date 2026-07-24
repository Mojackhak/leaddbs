"""Focused tests for repository-owned source and scratch byte events."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
import tempfile
import unittest

import numpy as np

from dual_frequency.cache import (
    ArtifactStore,
    CacheFileMetadata,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    ScientificCacheKey,
)
from dual_frequency.contracts import AxisRef
from dual_frequency.instrumentation import performance_delta, performance_snapshot
from dual_frequency.runtime.input_provider import StudyRuntimeInputProvider


def _cache_key() -> ScientificCacheKey:
    return ScientificCacheKey(
        geometry_hash="1" * 64,
        stimulation_hash="2" * 64,
        component_frequency_hash="3" * 64,
        transform_hash="4" * 64,
        connectome_feature_hash="5" * 64,
        backend_name="test",
        backend_version="1",
        scientific_parameter_hashes=(("tau", "6" * 64),),
    )


class Task17ByteInstrumentationTest(unittest.TestCase):
    def test_cache_and_artifact_staging_increment_scratch_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.npy"
            np.save(source, np.arange(3, dtype=np.float32), allow_pickle=False)
            source_size = source.stat().st_size
            cache = ContentAddressedCache(root / "cache")
            axis = AxisRef("items", 3, "a" * 64)
            before = performance_snapshot()
            cache.publish(
                _cache_key(),
                {"values.npy": source},
                metadata={
                    "values.npy": CacheFileMetadata(
                        dtype="float32",
                        shape=(3,),
                        axes=(axis,),
                    )
                },
            )
            publisher = RunScopedArtifactPublisher(
                root / "run" / "work" / "task_one" / "attempt-one",
                "task_one",
                "1",
            )
            publisher.array(
                "result.npy",
                np.arange(3, dtype=np.float32),
                kind="result",
                axes=(axis,),
                units=None,
                space=None,
            )
            delta = performance_delta(before, performance_snapshot())
        self.assertGreater(
            delta["scalars"]["scratch_bytes"],
            source_size,
        )

    def test_original_hash_and_temporary_matrix_are_accounted_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "run" / "work"
            work.mkdir(parents=True)
            allowed = root / "run"
            source_root = root / "configured-inputs"
            source_root.mkdir()
            source = source_root / "input.bin"
            source.write_bytes(b"configured-scientific-input")
            provider = object.__new__(StudyRuntimeInputProvider)
            provider._work_root = work
            provider._artifact_store = ArtifactStore((allowed,))
            provider._scientific_cache = ContentAddressedCache(root / "cache")
            provider._lock = RLock()
            provider._hashes = {}
            before = performance_snapshot()
            provider._path_hash(source)
            matrix = provider._temporary_matrix(
                "test",
                (2, 3),
                np.float32,
            )
            matrix_size = matrix.path.stat().st_size
            provider._release_temporary_matrix(matrix)
            delta = performance_delta(before, performance_snapshot())
        self.assertEqual(
            delta["scalars"]["source_bytes"],
            len(b"configured-scientific-input"),
        )
        self.assertEqual(delta["scalars"]["scratch_bytes"], matrix_size)


if __name__ == "__main__":
    unittest.main()
