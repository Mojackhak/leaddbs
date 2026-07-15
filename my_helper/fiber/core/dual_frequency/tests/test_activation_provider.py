"""Generic cache-first OSS activation-provider orchestration tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import unquote, urlsplit

import numpy as np

from dual_frequency.backends.activation import (
    MissingAcceptanceFixture,
    OSSRowProduct,
    OSSScientificSettings,
)
from dual_frequency.cache import ContentAddressedCache, RunScopedArtifactPublisher
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    SourceRecord,
)
from dual_frequency.runtime.activation_provider import (
    ActivationProviderError,
    CanonicalStimulationSource,
    OSSActivationProvider,
    OSSActivationRuntimeRequest,
    OSSProducerRequest,
)


def _digest(seed: int) -> str:
    return f"{seed:064x}"


def _array_artifact(axis: AxisRef) -> ArtifactRef:
    return ArtifactRef(
        kind="synthetic_final_feature_data",
        schema_version="synthetic_v1",
        uri="memory://activation-provider/final-feature-data",
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


def _geometry_artifact(seed: int, *, space: str = "right_canonical") -> ArtifactRef:
    return ArtifactRef(
        kind="canonical_stimulation_geometry",
        schema_version="synthetic_v1",
        uri=f"memory://activation-provider/geometry-{seed}",
        sha256=_digest(seed),
        dtype=None,
        shape=None,
        axis_refs=(),
        axis_hashes=(),
        units=None,
        space=space,
        producer_id="synthetic",
        producer_version="1",
    )


def _final(feature_axis: AxisRef, *, scale_id: str = "scale-a") -> FinalModelRecord:
    endpoint = EndpointKey(
        "synthetic-study",
        scale_id,
        "reference-binding",
        "reference_fiber",
        "formal-connectome",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=800.0,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "synthetic-final-axis"),
        artifacts=(_array_artifact(feature_axis),),
    )
    return FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            800.0,
            5,
            "continuous_dose_signed_peak",
        ),
        selected_source=source,
        selected_branch=None,
    )


def _artifact_array(artifact: ArtifactRef) -> np.ndarray:
    path = Path(unquote(urlsplit(artifact.uri).path))
    return np.load(path, allow_pickle=False)


class _FakeToolchain:
    def __init__(
        self,
        responses: dict[tuple[str, ...], np.ndarray],
    ) -> None:
        self._responses = responses
        self._calls: list[OSSProducerRequest] = []
        self._lock = threading.Lock()

    @property
    def calls(self) -> tuple[OSSProducerRequest, ...]:
        with self._lock:
            return tuple(self._calls)

    def produce(self, request: OSSProducerRequest) -> OSSRowProduct:
        if request.canonical_space != "right_canonical":
            raise AssertionError("producer request is not right-canonical")
        for source in request.sources:
            expected = "left_to_right" if source.side == "L" else "identity"
            if source.canonicalization != expected:
                raise AssertionError("producer received an invalid mapping recipe")
        with self._lock:
            self._calls.append(request)
        try:
            probabilities = self._responses[tuple(sorted(request.source_ids))]
        except KeyError as exc:
            raise AssertionError(
                f"unexpected producer source membership {request.source_ids!r}"
            ) from exc
        return OSSRowProduct(request.row.feature_ids, probabilities)


class OSSActivationProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.subject_ids = ("participant-a",)
        self.subject_axis = AxisRef("subjects", 1, "a" * 64)
        self.feature_axis = AxisRef("fibers", 3, "b" * 64)
        self.feature_ids = np.asarray([101, 205, 309], dtype=np.int64)
        self.settings = OSSScientificSettings(backend_version="2.2.0")

    def _source(
        self,
        source_id: str,
        *,
        side: str,
        group_id: str,
        delivery_mode: str,
        seed: int,
    ) -> CanonicalStimulationSource:
        return CanonicalStimulationSource(
            subject_id=self.subject_ids[0],
            side=side,
            frequency_group_id=group_id,
            delivery_mode=delivery_mode,
            source_id=source_id,
            geometry=_geometry_artifact(seed),
            canonicalization=("left_to_right" if side == "L" else "identity"),
            stimulation_hash=_digest(seed + 100),
            component_frequency_hash=_digest(seed + 200),
            transform_hash=_digest(seed + 300),
        )

    def _request(
        self,
        sources: tuple[CanonicalStimulationSource, ...],
        *,
        allow_expensive_producers: bool,
        final_model: FinalModelRecord | None = None,
        feature_axis: AxisRef | None = None,
    ) -> OSSActivationRuntimeRequest:
        selected_axis = feature_axis or self.feature_axis
        return OSSActivationRuntimeRequest(
            final_model=final_model or _final(self.feature_axis),
            connectome_role="formal",
            subject_axis=self.subject_axis,
            subject_ids=self.subject_ids,
            feature_axis=selected_axis,
            feature_ids=self.feature_ids,
            sources=sources,
            connectome_feature_hash="c" * 64,
            settings=self.settings,
            allow_expensive_producers=allow_expensive_producers,
            workers=2,
        )

    def _continuous_sources(self) -> tuple[CanonicalStimulationSource, ...]:
        return (
            self._source(
                "left-a",
                side="L",
                group_id="left-group",
                delivery_mode="continuous",
                seed=1,
            ),
            self._source(
                "left-b",
                side="L",
                group_id="left-group",
                delivery_mode="continuous",
                seed=2,
            ),
            self._source(
                "right-a",
                side="R",
                group_id="right-group",
                delivery_mode="continuous",
                seed=3,
            ),
            self._source(
                "right-b",
                side="R",
                group_id="right-group",
                delivery_mode="continuous",
                seed=4,
            ),
        )

    def _alternating_sources(self) -> tuple[CanonicalStimulationSource, ...]:
        return (
            self._source(
                "left-a",
                side="L",
                group_id="left-group",
                delivery_mode="alternating",
                seed=11,
            ),
            self._source(
                "left-b",
                side="L",
                group_id="left-group",
                delivery_mode="alternating",
                seed=12,
            ),
            self._source(
                "right-a",
                side="R",
                group_id="right-group",
                delivery_mode="alternating",
                seed=13,
            ),
            self._source(
                "right-b",
                side="R",
                group_id="right-group",
                delivery_mode="alternating",
                seed=14,
            ),
        )

    def test_exact_cache_hit_needs_no_toolchain_and_has_stable_row_identity(self) -> None:
        sources = self._continuous_sources()
        toolchain = _FakeToolchain(
            {
                ("left-a", "left-b"): np.asarray([0.1, 0.7, 0.5], dtype=np.float32),
                ("right-a", "right-b"): np.asarray([0.4, 0.2, 0.8], dtype=np.float32),
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache = ContentAddressedCache(root / "cache")
            first = OSSActivationProvider(
                cache,
                producer_toolchain=toolchain,
            ).materialize(
                self._request(sources, allow_expensive_producers=True),
                RunScopedArtifactPublisher(root / "run-a", "activation", "1"),
            )
            calls_after_production = toolchain.calls
            second_request = self._request(
                tuple(reversed(sources)),
                allow_expensive_producers=False,
                final_model=_final(self.feature_axis, scale_id="scale-b"),
            )
            second = OSSActivationProvider(cache).materialize(
                second_request,
                RunScopedArtifactPublisher(root / "run-b", "activation", "1"),
            )

            first_probability = _artifact_array(first.activation_probability)
            second_probability = _artifact_array(second.activation_probability)
            first_binary = _artifact_array(first.binary_exposure)
            second_binary = _artifact_array(second.binary_exposure)

        self.assertEqual(len(calls_after_production), 2)
        self.assertEqual(toolchain.calls, calls_after_production)
        self.assertEqual(
            {frozenset(call.source_ids) for call in calls_after_production},
            {frozenset(("left-a", "left-b")), frozenset(("right-a", "right-b"))},
        )
        self.assertEqual(
            len({call.scientific_identity for call in calls_after_production}),
            2,
        )
        np.testing.assert_array_equal(first_probability, second_probability)
        np.testing.assert_array_equal(first_binary, second_binary)
        np.testing.assert_array_equal(
            first_probability,
            np.asarray([[0.4, 0.7, 0.8]], dtype=np.float32),
        )

    def test_unauthorized_miss_fails_before_producer_invocation(self) -> None:
        toolchain = _FakeToolchain({})
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            provider = OSSActivationProvider(
                ContentAddressedCache(root / "cache"),
                producer_toolchain=toolchain,
            )
            with self.assertRaisesRegex(
                MissingAcceptanceFixture,
                "missing_acceptance_fixture",
            ):
                provider.materialize(
                    self._request(
                        self._continuous_sources(),
                        allow_expensive_producers=False,
                    ),
                    RunScopedArtifactPublisher(root / "run", "activation", "1"),
                )
        self.assertEqual(toolchain.calls, ())

    def test_continuous_group_is_one_joint_producer_row_per_side(self) -> None:
        toolchain = _FakeToolchain(
            {
                ("left-a", "left-b"): np.asarray([0.9, 0.1, 0.4], dtype=np.float32),
                ("right-a", "right-b"): np.asarray([0.2, 0.8, 0.5], dtype=np.float32),
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            artifact = OSSActivationProvider(
                ContentAddressedCache(root / "cache"),
                producer_toolchain=toolchain,
            ).materialize(
                self._request(
                    self._continuous_sources(),
                    allow_expensive_producers=True,
                ),
                RunScopedArtifactPublisher(root / "run", "activation", "1"),
            )
            probability = _artifact_array(artifact.activation_probability)
            binary = _artifact_array(artifact.binary_exposure)

        self.assertEqual(len(toolchain.calls), 2)
        self.assertTrue(all(call.delivery_mode == "continuous" for call in toolchain.calls))
        self.assertTrue(all(len(call.sources) == 2 for call in toolchain.calls))
        np.testing.assert_array_equal(
            probability,
            np.asarray([[0.9, 0.8, 0.5]], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            binary,
            np.asarray([[1.0, 1.0, 1.0]], dtype=np.float32),
        )

    def test_alternating_group_produces_independent_rows_then_max_merges(self) -> None:
        toolchain = _FakeToolchain(
            {
                ("left-a",): np.asarray([0.1, 0.9, 0.2], dtype=np.float32),
                ("left-b",): np.asarray([0.7, 0.2, 0.5], dtype=np.float32),
                ("right-a",): np.asarray([0.3, 0.4, 0.8], dtype=np.float32),
                ("right-b",): np.asarray([0.2, 0.6, 0.1], dtype=np.float32),
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            artifact = OSSActivationProvider(
                ContentAddressedCache(root / "cache"),
                producer_toolchain=toolchain,
            ).materialize(
                self._request(
                    self._alternating_sources(),
                    allow_expensive_producers=True,
                ),
                RunScopedArtifactPublisher(root / "run", "activation", "1"),
            )
            probability = _artifact_array(artifact.activation_probability)
            binary = _artifact_array(artifact.binary_exposure)

        self.assertEqual(len(toolchain.calls), 4)
        self.assertTrue(all(call.delivery_mode == "alternating" for call in toolchain.calls))
        self.assertTrue(all(len(call.sources) == 1 for call in toolchain.calls))
        np.testing.assert_array_equal(
            probability,
            np.asarray([[0.7, 0.9, 0.8]], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            binary,
            np.asarray([[1.0, 1.0, 1.0]], dtype=np.float32),
        )

    def test_nonfinal_feature_axis_is_rejected_before_materialization(self) -> None:
        wrong_axis = AxisRef("fibers", self.feature_axis.count, "d" * 64)
        with self.assertRaisesRegex(
            ActivationProviderError,
            "final.valid_feature_axis exactly",
        ):
            self._request(
                self._continuous_sources(),
                allow_expensive_producers=True,
                feature_axis=wrong_axis,
            )

    def test_left_geometry_recipe_is_content_bound_before_mapping_executes(self) -> None:
        source = CanonicalStimulationSource(
            subject_id=self.subject_ids[0],
            side="L",
            frequency_group_id="group",
            delivery_mode="continuous",
            source_id="left-native",
            geometry=_geometry_artifact(99, space="left_native"),
            canonicalization="left_to_right",
            stimulation_hash=_digest(199),
            component_frequency_hash=_digest(299),
            transform_hash=_digest(399),
        )
        changed_transform = CanonicalStimulationSource(
            subject_id=self.subject_ids[0],
            side="L",
            frequency_group_id="group",
            delivery_mode="continuous",
            source_id="left-native",
            geometry=_geometry_artifact(99, space="left_native"),
            canonicalization="left_to_right",
            stimulation_hash=_digest(199),
            component_frequency_hash=_digest(299),
            transform_hash=_digest(400),
        )
        self.assertNotEqual(source.geometry_hash, source.geometry.sha256)
        self.assertNotEqual(source.geometry_hash, changed_transform.geometry_hash)


if __name__ == "__main__":
    unittest.main()
