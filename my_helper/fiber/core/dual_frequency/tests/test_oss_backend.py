"""Cache-first OSS row materialization and bounded fixture tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import unquote, urlsplit

import numpy as np

from dual_frequency.backends.activation import (
    MissingAcceptanceFixture,
    OSSRowBatchRequest,
    OSSRowInput,
    OSSRowMaterializer,
    OSSRowProduct,
    OSSScientificSettings,
    binary_activation,
    build_oss_row_cache_key,
    subset_probability_axis,
)
from dual_frequency.cache import (
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    SourceRecord,
)


def _artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="synthetic_fiber_weights",
        schema_version="synthetic_v1",
        uri="memory://synthetic/weights",
        sha256="f" * 64,
        dtype="float32",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units=None,
        space="right_canonical",
        producer_id="synthetic",
        producer_version="1",
    )


def _final(scale_id: str, feature_axis: AxisRef) -> FinalModelRecord:
    endpoint = EndpointKey(
        "synthetic",
        scale_id,
        "reference_binding",
        "reference_fiber",
        "formal-connectome",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=800,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "synthetic_fiber_ids"),
        artifacts=(_artifact(feature_axis),),
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            800,
            5,
            "weighted_peak",
        ),
        selected_source=source,
        selected_branch=None,
    )


def _rows(
    subjects: tuple[str, ...],
    feature_axis: AxisRef,
    fiber_ids: np.ndarray,
) -> tuple[OSSRowInput, ...]:
    rows = []
    for subject_index, subject_id in enumerate(subjects):
        for side_index, side in enumerate(("L", "R")):
            seed = subject_index * 2 + side_index + 1
            rows.append(
                OSSRowInput(
                    subject_id=subject_id,
                    side=side,
                    source_id=f"source-{seed}",
                    feature_axis=feature_axis,
                    feature_ids=fiber_ids,
                    geometry_hash=f"{seed:064x}",
                    stimulation_hash=f"{seed + 100:064x}",
                    component_frequency_hash=f"{seed + 200:064x}",
                    transform_hash=f"{seed + 300:064x}",
                    connectome_feature_hash=feature_axis.sha256,
                )
            )
    return tuple(reversed(rows))


def _request(
    *,
    scale_id: str,
    allow_expensive: bool,
    subjects: tuple[str, ...],
    subject_axis: AxisRef,
    feature_axis: AxisRef,
    fiber_ids: np.ndarray,
    rows: tuple[OSSRowInput, ...],
    workers: int = 3,
) -> OSSRowBatchRequest:
    return OSSRowBatchRequest(
        final_model=_final(scale_id, feature_axis),
        connectome_role="formal",
        subject_axis=subject_axis,
        subject_ids=subjects,
        feature_axis=feature_axis,
        feature_ids=fiber_ids,
        rows=rows,
        settings=OSSScientificSettings(backend_version="2.2.0"),
        allow_expensive_producers=allow_expensive,
        workers=workers,
    )


def _artifact_array(artifact: ArtifactRef) -> np.ndarray:
    return np.load(Path(unquote(urlsplit(artifact.uri).path)), allow_pickle=False)


class OSSRowIdentityTest(unittest.TestCase):
    def test_key_excludes_endpoint_and_execution_identity_by_construction(self) -> None:
        fibers = AxisRef("fibers", 3, "a" * 64)
        row = _rows(("sub-01",), fibers, np.arange(3, dtype=np.int64))[0]
        settings = OSSScientificSettings(backend_version="2.2.0")
        first = build_oss_row_cache_key(row, settings)
        second = build_oss_row_cache_key(row, settings)
        self.assertEqual(first, second)
        self.assertNotIn("scale", json.dumps(first.as_dict()))
        self.assertNotIn("endpoint", json.dumps(first.as_dict()))
        self.assertNotIn("final", json.dumps(first.as_dict()))
        self.assertNotIn("worker", json.dumps(first.as_dict()))

    def test_key_changes_for_every_scientific_identity_dimension(self) -> None:
        fibers = AxisRef("fibers", 3, "a" * 64)
        row = _rows(("sub-01",), fibers, np.arange(3, dtype=np.int64))[0]
        settings = OSSScientificSettings(backend_version="2.2.0")
        baseline = build_oss_row_cache_key(row, settings).digest
        for field_name in (
            "geometry_hash",
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
            "connectome_feature_hash",
        ):
            changed = dataclasses.replace(row, **{field_name: "e" * 64})
            with self.subTest(field_name=field_name):
                self.assertNotEqual(
                    build_oss_row_cache_key(changed, settings).digest,
                    baseline,
                )
        self.assertNotEqual(
            build_oss_row_cache_key(
                row,
                OSSScientificSettings(backend_version="2.3.0"),
            ).digest,
            baseline,
        )


class OSSRowMaterializerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.subjects = ("sub-01", "sub-02", "sub-03")
        self.subject_axis = AxisRef("subjects", 3, "b" * 64)
        self.feature_axis = AxisRef("fibers", 5, "c" * 64)
        self.fiber_ids = np.arange(101, 106, dtype=np.int64)
        self.rows = _rows(self.subjects, self.feature_axis, self.fiber_ids)

    @staticmethod
    def _values(row: OSSRowInput) -> np.ndarray:
        subject = int(row.subject_id.rsplit("-", 1)[1])
        side = 0.2 if row.side == "L" else 0.35
        return np.clip(
            side + subject * 0.05 + np.arange(row.feature_ids.size) * 0.12,
            0.0,
            1.0,
        ).astype(np.float32)

    def test_blocked_miss_invokes_no_producer(self) -> None:
        calls: list[str] = []

        def producer(row: OSSRowInput) -> OSSRowProduct:
            calls.append(row.source_id)
            return OSSRowProduct(row.feature_ids, self._values(row))

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            materializer = OSSRowMaterializer(
                ContentAddressedCache(root / "cache"),
                RunScopedArtifactPublisher(root / "run", "oss_test", "1"),
                producer=producer,
            )
            with self.assertRaisesRegex(
                MissingAcceptanceFixture,
                "missing_acceptance_fixture",
            ):
                materializer.materialize(
                    _request(
                        scale_id="scale-a",
                        allow_expensive=False,
                        subjects=self.subjects,
                        subject_axis=self.subject_axis,
                        feature_axis=self.feature_axis,
                        fiber_ids=self.fiber_ids,
                        rows=self.rows,
                    )
                )
        self.assertEqual(calls, [])

    def test_three_worker_production_is_deterministic_and_cache_reusable(self) -> None:
        lock = threading.Lock()
        active = 0
        max_active = 0
        calls: list[str] = []

        def producer(row: OSSRowInput) -> OSSRowProduct:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                calls.append(row.source_id)
            time.sleep(0.01 * (1 + int(row.source_id.rsplit("-", 1)[1]) % 3))
            product = OSSRowProduct(row.feature_ids, self._values(row))
            with lock:
                active -= 1
            return product

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache = ContentAddressedCache(root / "cache")
            first = OSSRowMaterializer(
                cache,
                RunScopedArtifactPublisher(root / "run-a", "oss_test", "1"),
                producer=producer,
            ).materialize(
                _request(
                    scale_id="scale-a",
                    allow_expensive=True,
                    subjects=self.subjects,
                    subject_axis=self.subject_axis,
                    feature_axis=self.feature_axis,
                    fiber_ids=self.fiber_ids,
                    rows=self.rows,
                )
            )
            first_probability = _artifact_array(first.activation_probability)
            first_binary = _artifact_array(first.binary_exposure)
            calls_after_first = len(calls)

            def forbidden(_row: OSSRowInput) -> OSSRowProduct:
                raise AssertionError("exact cache hit must not invoke producer")

            second = OSSRowMaterializer(
                cache,
                RunScopedArtifactPublisher(root / "run-b", "oss_test", "1"),
                producer=forbidden,
            ).materialize(
                _request(
                    scale_id="scale-b",
                    allow_expensive=False,
                    subjects=self.subjects,
                    subject_axis=self.subject_axis,
                    feature_axis=self.feature_axis,
                    fiber_ids=self.fiber_ids,
                    rows=tuple(reversed(self.rows)),
                )
            )
            second_probability = _artifact_array(second.activation_probability)
            second_binary = _artifact_array(second.binary_exposure)

        self.assertEqual(calls_after_first, len(self.rows))
        self.assertEqual(len(calls), calls_after_first)
        self.assertGreaterEqual(max_active, 2)
        self.assertLessEqual(max_active, 3)
        np.testing.assert_array_equal(first_probability, second_probability)
        np.testing.assert_array_equal(first_binary, second_binary)
        np.testing.assert_array_equal(first_binary, binary_activation(first_probability))
        expected = np.stack(
            [
                np.maximum(
                    self._values(next(row for row in self.rows if row.subject_id == subject and row.side == "L")),
                    self._values(next(row for row in self.rows if row.subject_id == subject and row.side == "R")),
                )
                for subject in self.subjects
            ]
        )
        np.testing.assert_array_equal(first_probability, expected)


class CompletedOSSFixtureContractTest(unittest.TestCase):
    frozen_manifest = (
        Path(__file__).resolve().parents[3]
        / "projects/stnsnr/acceptance/frozen/20260711T034644Z_d318f177f7f2ac7d"
        / "bounded_fixture_manifest.json"
    )

    @unittest.skipUnless(
        frozen_manifest.is_file(),
        "completed bounded OSS fixtures are unavailable",
    )
    def test_allowlisted_matrix_supports_bounded_subset_and_threshold_replay(self) -> None:
        frozen = json.loads(self.frozen_manifest.read_text(encoding="utf-8"))
        tasks = {task["task_id"]: task for task in frozen["eligible_tasks"]}
        sidecar = tasks["task_07369f7915997b203e03"]
        sensitivity = tasks["task_5f8a7058c24e684281c9"]
        self.assertEqual(sidecar["status"], "completed")
        self.assertEqual(sensitivity["status"], "completed")
        artifacts = {artifact["kind"]: artifact for artifact in sidecar["artifacts"]}
        sensitivity_artifacts = {
            artifact["kind"]: artifact for artifact in sensitivity["artifacts"]
        }
        consumed = (
            sidecar["task_manifest"],
            artifacts["oss_activation_metadata"],
            artifacts["oss_activation_probabilities"],
            artifacts["oss_fiber_ids"],
            artifacts["oss_parameter_manifest"],
            sensitivity["task_manifest"],
            sensitivity_artifacts["oss_activation_results"],
        )
        for artifact in consumed:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256_file(path), artifact["sha256"], path)

        matrix = np.load(
            artifacts["oss_activation_probabilities"]["path"],
            allow_pickle=False,
            mmap_mode="r",
        )
        fiber_ids = np.load(
            artifacts["oss_fiber_ids"]["path"],
            allow_pickle=False,
            mmap_mode="r",
        )
        metadata = json.loads(
            Path(artifacts["oss_activation_metadata"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(matrix.shape, (16, 3990))
        self.assertEqual(matrix.dtype, np.dtype(np.float32))
        self.assertEqual(fiber_ids.shape, (3990,))
        self.assertEqual(fiber_ids.dtype, np.dtype(np.int64))
        self.assertEqual(metadata["hemisphere_source_merge_rule"], "max_probability_union")
        self.assertEqual(metadata["canonical_hemisphere"], "right")
        self.assertEqual(metadata["ppam_sample_count"], 10)

        subject_indices = np.asarray([0, 7, 15], dtype=np.int64)
        fiber_indices = np.linspace(0, fiber_ids.size - 1, 48, dtype=np.int64)
        requested_ids = np.asarray(fiber_ids[fiber_indices], dtype=np.int64)
        observed = subset_probability_axis(
            np.asarray(matrix[subject_indices]),
            source_fiber_ids=np.asarray(fiber_ids),
            requested_fiber_ids=requested_ids,
        )
        expected = np.asarray(matrix[np.ix_(subject_indices, fiber_indices)])
        np.testing.assert_array_equal(observed, expected)
        np.testing.assert_array_equal(
            binary_activation(observed),
            (expected >= 0.5).astype(np.float32),
        )


if __name__ == "__main__":
    unittest.main()
