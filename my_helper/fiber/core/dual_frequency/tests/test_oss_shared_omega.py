"""Omega-max-only OSS preparation, resume, and closure tests."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from dual_frequency.backends.activation import OSS_SCIENTIFIC_BACKEND_VERSION
from dual_frequency.cache import RunScopedArtifactPublisher
from dual_frequency.runtime.oss_shared_omega import (
    prepare_oss_omega_max_rows,
    shared_omega_group_uses_stable_scientific_cache,
)
from dual_frequency.tests import test_oss_axis_equivalence as axis_fixture
from dual_frequency.workflow import ServiceResult


class _TrackingProvider(axis_fixture._Provider):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.simulation_axes = []

    def activation_runtime_request(self, *args, **kwargs):
        self.simulation_axes.append(kwargs.get("simulation_feature_axis"))
        return super().activation_runtime_request(*args, **kwargs)


class OSSSharedOmegaTest(unittest.TestCase):
    def _arguments(self, root: Path):
        fixture = axis_fixture.OSSAxisEquivalenceTest(methodName="runTest")
        cache, final_ids, subject_axis, selection, descriptor = fixture._fixture(root)
        descriptor = {
            **descriptor,
            "preparation_version": descriptor["gate_version"],
        }
        del descriptor["gate_version"]
        descriptor["group_id"] = "oss-omega-group-test"
        endpoint_id = selection.endpoint.identifier
        toolchain = axis_fixture._Toolchain()
        return (
            {
                "descriptor": descriptor,
                "endpoint_inputs": {endpoint_id: object()},
                "prepared_exposures": {endpoint_id: object()},
                "final_selections": {endpoint_id: selection},
                "provider": axis_fixture._Provider(
                    final_ids,
                    subject_axis,
                    backend_version=OSS_SCIENTIFIC_BACKEND_VERSION,
                ),
                "cache": cache,
                "publisher": RunScopedArtifactPublisher(
                    root / "output",
                    "oss-shared-omega",
                    "1",
                ),
                "toolchain": toolchain,
                "workers": 14,
                "allow_expensive_producers": True,
            },
            toolchain,
        )

    def test_produces_only_omega_rows_and_resumes_without_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments, toolchain = self._arguments(root)
            first = prepare_oss_omega_max_rows(**arguments)

            self.assertEqual(first.preparation_status, "omega_max_ready")
            self.assertEqual(toolchain.calls, 2)
            self.assertEqual(len(first.omega_row_ids), 2)
            self.assertEqual(ServiceResult.from_record(first).decode_record(), first)
            self.assertTrue(
                shared_omega_group_uses_stable_scientific_cache(
                    first,
                    arguments["cache"],
                )
            )
            self.assertFalse(
                (
                    root
                    / "cache"
                    / "shared_exposure_v2"
                    / "oss_axis_equivalence"
                ).exists()
            )

            arguments["allow_expensive_producers"] = False
            arguments["toolchain"] = object()
            restored = prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(restored.omega_row_ids, first.omega_row_ids)
            self.assertEqual(toolchain.calls, 2)

            copied_root = root / "copied-cache"
            shutil.copytree(arguments["cache"].root, copied_root)
            arguments["cache"] = type(arguments["cache"])(copied_root)
            arguments["publisher"] = RunScopedArtifactPublisher(
                root / "copied-output",
                "oss-shared-omega-copy",
                "1",
            )
            copied = prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(copied.omega_row_ids, first.omega_row_ids)
            self.assertEqual(toolchain.calls, 2)

    def test_one_missing_row_produces_once_and_never_final_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments, toolchain = self._arguments(root)
            first = prepare_oss_omega_max_rows(**arguments)
            removed = (
                root
                / "cache"
                / "shared_exposure_v2"
                / "oss_rows"
                / first.omega_row_ids[0]
            )
            shutil.rmtree(removed)

            arguments["allow_expensive_producers"] = False
            arguments["toolchain"] = object()
            with self.assertRaisesRegex(
                RuntimeError,
                "cache misses require expensive producer authorization",
            ):
                prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(toolchain.calls, 2)

            arguments["allow_expensive_producers"] = True
            arguments["toolchain"] = toolchain
            repaired = prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(repaired.omega_row_ids, first.omega_row_ids)
            self.assertEqual(toolchain.calls, 3)
            for row_id in repaired.omega_row_ids:
                entry = arguments["cache"].resolve_identity("oss_rows", row_id)
                self.assertIsNotNone(entry)

    def test_corrupt_row_fails_closed_without_toolchain_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments, toolchain = self._arguments(root)
            first = prepare_oss_omega_max_rows(**arguments)
            entry = arguments["cache"].resolve_identity(
                "oss_rows",
                first.omega_row_ids[0],
            )
            assert entry is not None
            entry.file_path("probabilities.npy").write_bytes(b"corrupt")
            arguments["allow_expensive_producers"] = False
            arguments["toolchain"] = object()

            with self.assertRaises(RuntimeError):
                prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(toolchain.calls, 2)

    def test_final_axis_must_be_an_exact_omega_subset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments, toolchain = self._arguments(root)
            subject_axis = arguments["provider"].subject_axis
            arguments["provider"] = axis_fixture._Provider(
                np.asarray([2, 5], dtype=np.int64),
                subject_axis,
                backend_version=OSS_SCIENTIFIC_BACKEND_VERSION,
            )

            with self.assertRaisesRegex(RuntimeError, "exact ordered subset"):
                prepare_oss_omega_max_rows(**arguments)
            self.assertEqual(toolchain.calls, 0)

    def test_runtime_constructs_only_omega_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            arguments, toolchain = self._arguments(root)
            source = arguments["provider"]
            provider = _TrackingProvider(
                source.final_ids,
                source.subject_axis,
                backend_version=OSS_SCIENTIFIC_BACKEND_VERSION,
            )
            arguments["provider"] = provider

            result = prepare_oss_omega_max_rows(**arguments)

            self.assertEqual(len(provider.simulation_axes), 1)
            self.assertEqual(
                provider.simulation_axes[0],
                result.omega_feature_axis,
            )
            self.assertEqual(toolchain.calls, 2)


if __name__ == "__main__":
    unittest.main()
