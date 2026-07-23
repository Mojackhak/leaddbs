"""Exact OSS final/Omega axis gate and resume tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.activation import OSSRowProduct, OSSScientificSettings
from dual_frequency.cache import (
    CacheCorruption,
    CacheFileMetadata,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
)
from dual_frequency.cache.identity import ScientificCacheKey
from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    SourceRecord,
)
from dual_frequency.runtime.activation_provider import (
    CanonicalStimulationSource,
    OSSActivationRuntimeRequest,
)
from dual_frequency.runtime.oss_axis_equivalence import (
    establish_oss_axis_equivalence,
)
from dual_frequency.runtime.oss_toolchain import OSSRowExecutionEvidence
from dual_frequency.workflow import ServiceResult


def _artifact(label: str, axis: AxisRef | None = None) -> ArtifactRef:
    return ArtifactRef(
        kind="synthetic_oss_input",
        schema_version="synthetic_v1",
        uri=f"memory://synthetic/{label}",
        sha256=(label[0] * 64),
        dtype=(None if axis is None else "float32"),
        shape=(None if axis is None else (axis.count,)),
        axis_refs=(() if axis is None else (axis,)),
        axis_hashes=(() if axis is None else (axis.sha256,)),
        units=None,
        space=None,
        producer_id="synthetic",
        producer_version="1",
    )


def _selection(axis: AxisRef) -> FinalSelectionRecord:
    endpoint = EndpointKey(
        "study",
        "scale",
        "reference",
        "reference_fiber",
        "formal-connectome",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=400.0,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(axis, "synthetic_final_fiber_ids"),
        artifacts=(_artifact("f-final", axis),),
    )
    final = FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            400.0,
            5,
            "weighted_peak",
        ),
        selected_source=source,
        selected_branch=None,
    )
    return FinalSelectionRecord(
        endpoint=endpoint,
        selection_status="final_model_realized",
        final_model=final,
        reason_codes=("primary_realized",),
        causal_task_ids=("task-final",),
    )


class _Provider:
    def __init__(self, final_ids: np.ndarray, subject_axis: AxisRef) -> None:
        self.final_ids = final_ids
        self.subject_axis = subject_axis

    def activation_runtime_request(
        self,
        final_model,
        _endpoint_input,
        _prepared,
        _publisher,
        *,
        workers,
        allow_expensive_producers,
        simulation_feature_axis=None,
        simulation_feature_ids=None,
    ) -> OSSActivationRuntimeRequest:
        sources = tuple(
            CanonicalStimulationSource(
                subject_id="sub-01",
                side=side,
                frequency_group_id="group-01",
                delivery_mode="alternating",
                source_id=f"source-{side}",
                geometry=_artifact(f"{label}-geometry"),
                canonicalization=("left_to_right" if side == "L" else "identity"),
                stimulation_hash=label * 64,
                component_frequency_hash=("c" if side == "L" else "d") * 64,
                transform_hash=("e" if side == "L" else "f") * 64,
            )
            for side, label in (("L", "a"), ("R", "b"))
        )
        return OSSActivationRuntimeRequest(
            final_model=final_model,
            connectome_role="formal",
            subject_axis=self.subject_axis,
            subject_ids=("sub-01",),
            feature_axis=final_model.valid_feature_axis.axis,
            feature_ids=self.final_ids,
            sources=sources,
            connectome_feature_hash="9" * 64,
            settings=OSSScientificSettings(backend_version="synthetic-oss-v1"),
            allow_expensive_producers=allow_expensive_producers,
            simulation_feature_axis=simulation_feature_axis,
            simulation_feature_ids=simulation_feature_ids,
            workers=workers,
        )


class _Toolchain:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def produce_with_evidence(self, request) -> OSSRowExecutionEvidence:
        self.calls += 1
        ids = request.row.feature_ids
        states = np.zeros((10, ids.size), dtype=np.int8)
        states[:5, ids % 2 == 0] = 1
        if self.fail and ids.size == 2:
            states[0, 0] = 1 - states[0, 0]
        probabilities = (
            np.count_nonzero(states == 1, axis=0).astype(np.float64) / 10.0
        ).astype(np.float32)
        return OSSRowExecutionEvidence(
            OSSRowProduct(ids, probabilities),
            states,
        )


class OSSAxisEquivalenceTest(unittest.TestCase):
    def _fixture(self, root: Path):
        cache = ContentAddressedCache(root / "cache")
        final_axis = AxisRef("final-axis", 2, "1" * 64)
        omega_axis = AxisRef("omega-axis", 4, "2" * 64)
        final_ids = np.asarray([2, 4], dtype=np.int64)
        omega_ids = np.asarray([1, 2, 3, 4], dtype=np.int64)
        physical_identity = "3" * 64
        key = ScientificCacheKey(
            geometry_hash="4" * 64,
            stimulation_hash=physical_identity,
            component_frequency_hash="5" * 64,
            transform_hash="6" * 64,
            connectome_feature_hash="7" * 64,
            backend_name="normative_fiber_omega_max",
            backend_version="2",
            scientific_parameter_hashes=(("grid", "8" * 64),),
            kind="fiber_exposures",
        )
        path = root / "omega.npy"
        np.save(path, omega_ids, allow_pickle=False)
        entry = cache.publish(
            key,
            {"fiber_ids.npy": path},
            metadata={
                "fiber_ids.npy": CacheFileMetadata(
                    dtype="int64",
                    shape=(omega_axis.count,),
                    axes=(omega_axis,),
                    units="fiber_id",
                    space="right_canonical",
                )
            },
        )
        payload = next(item for item in entry.files if item.relative_path == "fiber_ids.npy")
        selection = _selection(final_axis)
        endpoint_id = selection.endpoint.identifier
        descriptor = {
            "gate_version": "1",
            "model_family": "reference_fiber",
            "final_feature_axis": {
                "axis_id": final_axis.axis_id,
                "count": final_axis.count,
                "sha256": final_axis.sha256,
            },
            "omega_max": {
                "cache_kind": key.kind,
                "semantic_sha256": key.digest,
                "feature_axis": {
                    "axis_id": omega_axis.axis_id,
                    "count": omega_axis.count,
                    "sha256": omega_axis.sha256,
                },
                "payload_relative_path": payload.relative_path,
                "payload_sha256": payload.sha256,
            },
            "group_id": "oss-axis-group-test",
            "endpoint_ids": [endpoint_id],
        }
        return (
            cache,
            final_ids,
            AxisRef("subjects", 1, "a" * 64),
            selection,
            descriptor,
        )

    def test_pass_publishes_constant_size_row_caches_and_resumes_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            toolchain = _Toolchain()
            arguments = {
                "descriptor": descriptor,
                "endpoint_inputs": {endpoint_id: object()},
                "prepared_exposures": {endpoint_id: object()},
                "final_selections": {endpoint_id: selection},
                "provider": _Provider(final_ids, subject_axis),
                "cache": cache,
                "publisher": RunScopedArtifactPublisher(
                    root / "output",
                    "oss-axis-gate",
                    "1",
                ),
                "toolchain": toolchain,
                "workers": 14,
                "allow_expensive_producers": True,
            }
            first = establish_oss_axis_equivalence(**arguments)
            arguments["allow_expensive_producers"] = False
            restored = establish_oss_axis_equivalence(**arguments)

            self.assertEqual(first.gate_status, "accepted_omega_max")
            self.assertEqual(restored.gate_status, "accepted_omega_max")
            self.assertEqual(toolchain.calls, 4)
            self.assertEqual(len(first.row_decision_ids), 2)
            self.assertEqual(ServiceResult.from_record(first).decode_record(), first)
            decision_files = tuple(
                (root / "cache" / "shared_exposure_v2" / "oss_axis_equivalence").glob(
                    "*/decision.json"
                )
            )
            self.assertEqual(len(decision_files), 2)
            shutil.rmtree(decision_files[0].parent)
            with self.assertRaisesRegex(
                RuntimeError,
                "cache misses require expensive producer authorization",
            ):
                establish_oss_axis_equivalence(**arguments)
            self.assertEqual(toolchain.calls, 4)
            arguments["allow_expensive_producers"] = True
            repaired = establish_oss_axis_equivalence(**arguments)
            self.assertEqual(repaired.gate_status, "accepted_omega_max")
            self.assertEqual(toolchain.calls, 6)
            row_manifests = tuple(
                (root / "cache" / "shared_exposure_v2" / "oss_rows").glob(
                    "*/manifest.json"
                )
            )
            self.assertEqual(len(row_manifests), 4)
            for manifest in row_manifests:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(payload["items"], [])
                self.assertEqual(len(payload["files"]), 3)

    def test_cache_miss_without_authorization_stops_before_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            toolchain = _Toolchain()

            with self.assertRaisesRegex(
                RuntimeError,
                "cache misses require expensive producer authorization",
            ):
                establish_oss_axis_equivalence(
                    descriptor=descriptor,
                    endpoint_inputs={endpoint_id: object()},
                    prepared_exposures={endpoint_id: object()},
                    final_selections={endpoint_id: selection},
                    provider=_Provider(final_ids, subject_axis),
                    cache=cache,
                    publisher=RunScopedArtifactPublisher(
                        root / "output",
                        "oss-axis-gate",
                        "1",
                    ),
                    toolchain=toolchain,
                    workers=14,
                    allow_expensive_producers=False,
                )

            self.assertEqual(toolchain.calls, 0)

    def test_complete_gate_survives_direct_cache_copy_without_toolchain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            initial_toolchain = _Toolchain()
            arguments = {
                "descriptor": descriptor,
                "endpoint_inputs": {endpoint_id: object()},
                "prepared_exposures": {endpoint_id: object()},
                "final_selections": {endpoint_id: selection},
                "provider": _Provider(final_ids, subject_axis),
                "cache": cache,
                "publisher": RunScopedArtifactPublisher(
                    root / "output",
                    "oss-axis-gate",
                    "1",
                ),
                "toolchain": initial_toolchain,
                "workers": 14,
                "allow_expensive_producers": True,
            }
            expected = establish_oss_axis_equivalence(**arguments)
            self.assertEqual(initial_toolchain.calls, 4)

            copied_root = root / "copied-cache"
            shutil.copytree(cache.root, copied_root)
            copied_toolchain = _Toolchain()
            arguments.update(
                {
                    "cache": ContentAddressedCache(copied_root),
                    "publisher": RunScopedArtifactPublisher(
                        root / "copied-output",
                        "oss-axis-gate-copy",
                        "1",
                    ),
                    "toolchain": copied_toolchain,
                    "allow_expensive_producers": False,
                }
            )
            restored = establish_oss_axis_equivalence(**arguments)

            self.assertEqual(restored.gate_status, "accepted_omega_max")
            self.assertEqual(restored.row_decision_ids, expected.row_decision_ids)
            self.assertEqual(copied_toolchain.calls, 0)

    def test_cached_decision_requires_both_standard_row_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            toolchain = _Toolchain()
            arguments = {
                "descriptor": descriptor,
                "endpoint_inputs": {endpoint_id: object()},
                "prepared_exposures": {endpoint_id: object()},
                "final_selections": {endpoint_id: selection},
                "provider": _Provider(final_ids, subject_axis),
                "cache": cache,
                "publisher": RunScopedArtifactPublisher(
                    root / "output",
                    "oss-axis-gate",
                    "1",
                ),
                "toolchain": toolchain,
                "workers": 14,
                "allow_expensive_producers": True,
            }
            establish_oss_axis_equivalence(**arguments)
            self.assertEqual(toolchain.calls, 4)

            decision_path = next(
                (
                    root
                    / "cache"
                    / "shared_exposure_v2"
                    / "oss_axis_equivalence"
                ).glob("*/decision.json")
            )
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            missing_row = (
                root
                / "cache"
                / "shared_exposure_v2"
                / "oss_rows"
                / decision["final_row_identity"]
            )
            shutil.rmtree(missing_row)
            arguments["allow_expensive_producers"] = False

            with self.assertRaisesRegex(
                RuntimeError,
                "cached OSS axis decision lacks its standard row cache",
            ):
                establish_oss_axis_equivalence(**arguments)
            self.assertEqual(toolchain.calls, 4)

    def test_new_process_rejects_corrupt_row_referenced_by_cached_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            toolchain = _Toolchain()
            arguments = {
                "descriptor": descriptor,
                "endpoint_inputs": {endpoint_id: object()},
                "prepared_exposures": {endpoint_id: object()},
                "final_selections": {endpoint_id: selection},
                "provider": _Provider(final_ids, subject_axis),
                "cache": cache,
                "publisher": RunScopedArtifactPublisher(
                    root / "output",
                    "oss-axis-gate",
                    "1",
                ),
                "toolchain": toolchain,
                "workers": 14,
                "allow_expensive_producers": True,
            }
            establish_oss_axis_equivalence(**arguments)
            self.assertEqual(toolchain.calls, 4)

            decision_path = next(
                (
                    root
                    / "cache"
                    / "shared_exposure_v2"
                    / "oss_axis_equivalence"
                ).glob("*/decision.json")
            )
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            probabilities = (
                root
                / "cache"
                / "shared_exposure_v2"
                / "oss_rows"
                / decision["final_row_identity"]
                / "probabilities.npy"
            )
            with probabilities.open("r+b") as stream:
                stream.seek(-1, 2)
                final_byte = stream.read(1)
                stream.seek(-1, 2)
                stream.write(bytes([final_byte[0] ^ 1]))

            arguments["cache"] = ContentAddressedCache(root / "cache")
            arguments["allow_expensive_producers"] = False
            with self.assertRaises(CacheCorruption):
                establish_oss_axis_equivalence(**arguments)
            self.assertEqual(toolchain.calls, 4)

    def test_any_state_mismatch_rejects_omega_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache, final_ids, subject_axis, selection, descriptor = self._fixture(root)
            endpoint_id = selection.endpoint.identifier
            result = establish_oss_axis_equivalence(
                descriptor=descriptor,
                endpoint_inputs={endpoint_id: object()},
                prepared_exposures={endpoint_id: object()},
                final_selections={endpoint_id: selection},
                provider=_Provider(final_ids, subject_axis),
                cache=cache,
                publisher=RunScopedArtifactPublisher(
                    root / "output",
                    "oss-axis-gate",
                    "1",
                ),
                toolchain=_Toolchain(fail=True),
                workers=14,
                allow_expensive_producers=True,
            )
            self.assertEqual(result.gate_status, "rejected_final_axis")


if __name__ == "__main__":
    unittest.main()
