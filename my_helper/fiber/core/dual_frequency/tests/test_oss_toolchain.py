"""Deterministic validation tests for the injected Lead-DBS OSS toolchain.

The suite uses only temporary local artifacts and a fake row executor. It
documents the producer boundary without launching MATLAB or OSS-DBSv2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from typing import Any, Callable

import numpy as np

from dual_frequency.backends.activation import (
    OSSRowInput,
    OSSRowProduct,
    OSSScientificSettings,
    build_oss_row_cache_key,
)
from dual_frequency.cache import (
    ArtifactStore,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.contracts import AxisRef
from dual_frequency.contracts.identity import canonical_hash
from dual_frequency.runtime.activation_provider import (
    ActivationProviderError,
    CanonicalStimulationSource,
    OSSProducerRequest,
)
from dual_frequency.runtime.oss_toolchain import (
    LeadDBSOSSProducerToolchain,
    OSSExecutableSet,
    OSS_MAX_FIBERS_PER_EXECUTION,
    OSS_PRODUCER_IMPLEMENTATION_PATHS,
    OSSProducerExecutionError,
    PreparedOSSRow,
    SubprocessOSSRowExecutor,
    OSSRowExecutionEvidence,
    _hash_oss_source_tree,
    _terminate_process_group,
    oss_backend_version,
)
from dual_frequency.runtime.connectome_subset import FilteredConnectome


def _digest(seed: int) -> str:
    return f"{seed:064x}"


def _case_return_contacts(active_contact: int) -> list[dict[str, object]]:
    return [
        {"contact": active_contact, "polarity": "cathode", "fraction": 1.0},
        {"contact": "case", "polarity": "anode", "fraction": 1.0},
    ]


def _electrode_return_contacts(
    active_contact: int,
    return_contact: int,
) -> list[dict[str, object]]:
    return [
        {"contact": active_contact, "polarity": "cathode", "fraction": 1.0},
        {"contact": return_contact, "polarity": "anode", "fraction": 1.0},
    ]


def _aggregate_source_hash(
    label: str,
    delivery_mode: str,
    sources: tuple[CanonicalStimulationSource, ...],
    values: tuple[str, ...],
) -> str:
    if len(values) == 1:
        return values[0]
    return canonical_hash(
        {
            "contract": "dual_frequency_oss_joint_source_v1",
            "field": label,
            "delivery_mode": delivery_mode,
            "ordered_sources": [{"sha256": value} for value in values],
        }
    )


class _FakeOSSRowExecutor:
    """Record prepared rows and return deterministic pPAM products."""

    def __init__(
        self,
        returned_feature_ids: np.ndarray | None = None,
        mutation: Callable[[], None] | None = None,
    ) -> None:
        self.rows: list[PreparedOSSRow] = []
        self.returned_feature_ids = (
            None
            if returned_feature_ids is None
            else np.array(returned_feature_ids, dtype=np.int64, copy=True)
        )
        self.mutation = mutation

    def execute(self, row: PreparedOSSRow) -> OSSRowProduct:
        self.rows.append(row)
        if self.mutation is not None:
            self.mutation()
        feature_ids = (
            row.feature_ids
            if self.returned_feature_ids is None
            else self.returned_feature_ids
        )
        probabilities = np.zeros(feature_ids.size, dtype=np.float32)
        return OSSRowProduct(feature_ids, probabilities)


class LeadDBSOSSProducerToolchainTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        self.subject_dir = self.root / "subject-input"
        self.subject_dir.mkdir()
        self.reconstruction_path = self.subject_dir / "reconstruction.mat"
        self.reconstruction_path.write_bytes(b"synthetic reconstruction\n")
        self.connectome_path = self.root / "formal-connectome.mat"
        self.connectome_path.write_bytes(b"tiny connectome placeholder\n")

        self.repository_root = self.root / "leaddbs"
        self.repository_root.mkdir()
        repository_assets = self.repository_root / "templates" / "synthetic-space"
        repository_assets.mkdir(parents=True)
        self.transform_path = repository_assets / "left-to-right.mat"
        self.transform_path.write_bytes(b"synthetic transform\n")
        self.template_segmask_path = repository_assets / "segmask.nii"
        self.template_segmask_path.write_bytes(b"synthetic segmask\n")
        self.environment_file = (
            self.repository_root
            / "classes"
            / "conda_utils"
            / "environments"
            / "OSS-DBSv2.yml"
        )
        self.environment_file.parent.mkdir(parents=True)
        self.environment_file.write_text("name: fake-oss\n", encoding="utf-8")

        self.publisher = RunScopedArtifactPublisher(
            self.root / "artifacts",
            "oss-toolchain-test",
            "1",
        )
        self.artifact_store = ArtifactStore((self.publisher.root,))
        self.feature_ids = np.asarray([407, 11, 9001], dtype=np.int64)
        ordered_axis_hash = hashlib.sha256(
            np.asarray(self.feature_ids, dtype="<i8").tobytes(order="C")
        ).hexdigest()
        self.feature_axis = AxisRef(
            "final-valid-fibers",
            self.feature_ids.size,
            ordered_axis_hash,
        )
        self._publication_index = 0
        self._request_index = 0
        self.subject_roots: dict[str, Path] = {}

    def _toolchain(
        self,
        executor: _FakeOSSRowExecutor,
        *,
        backend_version_resolver: Callable[[Path], str] | None = None,
    ) -> LeadDBSOSSProducerToolchain:
        return LeadDBSOSSProducerToolchain(
            artifact_store=self.artifact_store,
            connectome_path=self.connectome_path,
            connectome_label="tiny-formal-connectome",
            work_root=self.root / "work",
            repository_root=self.repository_root,
            environment_file=self.environment_file,
            subject_roots=self.subject_roots,
            executor=executor,
            backend_version_resolver=(
                backend_version_resolver
                or (lambda _root: "synthetic-toolchain-v1")
            ),
        )

    def _publish_source(
        self,
        source_id: str,
        *,
        subject_id: str,
        side: str = "R",
        frequency_group_id: str = "generic-frequency-group",
        delivery_mode: str = "continuous",
        control_mode: str = "voltage",
        contacts: list[dict[str, object]] | None = None,
        parameter_source_id: str | None = None,
        locator_source_id: str | None = None,
        declared_reconstruction_hash: str | None = None,
        geometry_overrides: Mapping[str, object] | None = None,
    ) -> CanonicalStimulationSource:
        self.subject_roots[subject_id] = self.subject_dir
        self._publication_index += 1
        publication_id = self._publication_index
        normalized_side = side.upper()
        reconstruction_hash = (
            declared_reconstruction_hash or sha256_file(self.reconstruction_path)
        )
        if normalized_side == "L":
            transform_uri: str | None = self.transform_path.as_uri()
            transform_hash = sha256_file(self.transform_path)
            canonicalization = "left_to_right"
            reconstruction_lead_id = 2
        else:
            transform_uri = None
            transform_hash = _digest(700)
            canonicalization = "identity"
            reconstruction_lead_id = 1

        geometry_payload: dict[str, Any] = {
            "schema_version": "dual_frequency_oss_geometry_recipe_v1",
            "electrode_model": "Synthetic Eight Contact Lead",
            "reconstruction_lead_id": reconstruction_lead_id,
            "contact_count": 8,
            "reconstruction_sha256": reconstruction_hash,
            "template_segmask_uri": self.template_segmask_path.as_uri(),
            "template_segmask_sha256": sha256_file(
                self.template_segmask_path
            ),
        }
        geometry_payload.update(geometry_overrides or {})
        geometry = self.publisher.document(
            f"geometry-{publication_id}.json",
            geometry_payload,
            kind="oss_stimulation_geometry_recipe",
        )

        parameter_payload: dict[str, Any] = {
            "schema_version": "dual_frequency_oss_source_parameters_v1",
            "source_id": parameter_source_id or source_id,
            "control_mode": control_mode,
            "amplitude": 2.5,
            "pulse_width_us": 60.0,
            "frequency_hz": 130.0,
            "contacts": contacts or _case_return_contacts(publication_id),
        }
        parameters = self.publisher.document(
            f"parameters-{publication_id}.json",
            parameter_payload,
            kind="oss_stimulation_source_parameters",
        )

        locator_payload: dict[str, Any] = {
            "schema_version": "dual_frequency_oss_source_locator_v1",
            "subject_id": subject_id,
            "phase_id": "generic-phase",
            "program_id": "generic-program",
            "electrode_id": f"generic-electrode-{normalized_side.lower()}",
            "frequency_group_id": frequency_group_id,
            "source_id": locator_source_id or source_id,
            "subject_dir_uri": self.subject_dir.as_uri(),
            "reconstruction_uri": self.reconstruction_path.as_uri(),
            "reconstruction_sha256": reconstruction_hash,
            "transform_uri": transform_uri,
            "transform_sha256": transform_hash,
            "canonicalization": canonicalization,
        }
        locator = self.publisher.document(
            f"locator-{publication_id}.json",
            locator_payload,
            kind="oss_stimulation_source_locator",
        )

        return CanonicalStimulationSource(
            subject_id=subject_id,
            side=normalized_side,
            frequency_group_id=frequency_group_id,
            delivery_mode=delivery_mode,
            source_id=source_id,
            geometry=geometry,
            canonicalization=canonicalization,
            stimulation_hash=parameters.sha256,
            component_frequency_hash=canonical_hash({"frequency_hz": 130.0}),
            transform_hash=transform_hash,
            input_artifacts=(parameters, locator),
        )

    def _request(
        self,
        sources: tuple[CanonicalStimulationSource, ...],
        *,
        delivery_mode: str,
    ) -> OSSProducerRequest:
        self._request_index += 1
        first = sources[0]
        connectome_hash = sha256_file(self.connectome_path)
        settings = OSSScientificSettings(backend_version="synthetic-toolchain-v1")
        row = OSSRowInput(
            subject_id=first.subject_id,
            side=first.side,
            source_id="+".join(source.source_id for source in sources),
            feature_axis=self.feature_axis,
            feature_ids=self.feature_ids,
            geometry_hash=_aggregate_source_hash(
                "geometry",
                delivery_mode,
                sources,
                tuple(source.geometry_hash for source in sources),
            ),
            stimulation_hash=_aggregate_source_hash(
                "stimulation",
                delivery_mode,
                sources,
                tuple(source.stimulation_hash for source in sources),
            ),
            component_frequency_hash=_aggregate_source_hash(
                "component_frequency",
                delivery_mode,
                sources,
                tuple(source.component_frequency_hash for source in sources),
            ),
            transform_hash=_aggregate_source_hash(
                "transform",
                delivery_mode,
                sources,
                tuple(source.transform_hash for source in sources),
            ),
            connectome_feature_hash=connectome_hash,
            input_artifacts=tuple(
                artifact
                for source in sources
                for artifact in source.artifacts
            ),
        )
        self.assertEqual(
            row.connectome_feature_hash,
            sha256_file(self.connectome_path),
        )
        return OSSProducerRequest(
            scientific_identity=build_oss_row_cache_key(row, settings).digest,
            row=row,
            frequency_group_id=first.frequency_group_id,
            delivery_mode=delivery_mode,
            sources=sources,
            settings=settings,
        )

    def test_accepts_arbitrary_generic_subject_ids_without_an_allowlist(self) -> None:
        executor = _FakeOSSRowExecutor()
        subject_ids = (
            "generic-subject-zeta-47",
            "external_cohort_subject_Q9",
        )
        sources = tuple(
            self._publish_source(
                f"source-{index}",
                subject_id=subject_id,
                delivery_mode="alternating",
            )
            for index, subject_id in enumerate(subject_ids, start=1)
        )
        toolchain = self._toolchain(executor)

        for subject_id, source in zip(subject_ids, sources, strict=True):
            with self.subTest(subject_id=subject_id):
                product = toolchain.produce(
                    self._request((source,), delivery_mode="alternating")
                )
                self.assertEqual(executor.rows[-1].subject_id, subject_id)
                np.testing.assert_array_equal(product.feature_ids, self.feature_ids)

        self.assertEqual(
            tuple(row.subject_id for row in executor.rows),
            subject_ids,
        )

    def test_accepts_continuous_sources_with_one_shared_boundary(self) -> None:
        executor = _FakeOSSRowExecutor()
        subject_id = "generic-continuous-subject"
        source_a = self._publish_source(
            "source-a",
            subject_id=subject_id,
            contacts=_case_return_contacts(1),
        )
        source_b = self._publish_source(
            "source-b",
            subject_id=subject_id,
            contacts=_case_return_contacts(2),
        )
        toolchain = self._toolchain(executor)

        product = toolchain.produce(
            self._request((source_a, source_b), delivery_mode="continuous")
        )

        self.assertEqual(len(executor.rows), 1)
        prepared = executor.rows[0]
        self.assertEqual(prepared.delivery_mode, "continuous")
        self.assertEqual(
            tuple(source.source_id for source in prepared.sources),
            ("source-a", "source-b"),
        )
        self.assertEqual(
            tuple(source.return_topology for source in prepared.sources),
            ("case", "case"),
        )
        np.testing.assert_array_equal(prepared.feature_ids, self.feature_ids)
        np.testing.assert_array_equal(product.feature_ids, self.feature_ids)

    def test_accepts_multipolar_voltage_contacts_with_unit_fractions(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "multipolar-voltage-source",
            subject_id="generic-multipolar-subject",
            contacts=[
                {"contact": 1, "polarity": "cathode", "fraction": 1.0},
                {"contact": 2, "polarity": "cathode", "fraction": 1.0},
                {"contact": "case", "polarity": "anode", "fraction": 1.0},
            ],
        )

        self._toolchain(executor).produce(
            self._request((source,), delivery_mode="continuous")
        )

        self.assertEqual(len(executor.rows), 1)
        self.assertEqual(len(executor.rows[0].sources[0].contacts), 3)

    def test_rejects_fractional_voltage_contacts(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "fractional-voltage-source",
            subject_id="generic-fractional-voltage-subject",
            contacts=[
                {"contact": 1, "polarity": "cathode", "fraction": 0.5},
                {"contact": 2, "polarity": "cathode", "fraction": 0.5},
                {"contact": "case", "polarity": "anode", "fraction": 1.0},
            ],
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "every active voltage contact must have fraction 1.0",
        ):
            self._toolchain(executor).produce(
                self._request((source,), delivery_mode="continuous")
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_cathodic_case_for_current_control(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "cathodic-current-case-source",
            subject_id="generic-current-case-subject",
            control_mode="current",
            contacts=[
                {"contact": "case", "polarity": "cathode", "fraction": 1.0},
                {"contact": 1, "polarity": "anode", "fraction": 1.0},
            ],
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "case must be the sole anode",
        ):
            self._toolchain(executor).produce(
                self._request((source,), delivery_mode="continuous")
            )

        self.assertEqual(executor.rows, [])

    def test_accepts_one_alternating_left_source(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "left-source",
            subject_id="generic-left-subject",
            side="L",
            delivery_mode="alternating",
            contacts=_case_return_contacts(3),
        )

        self._toolchain(executor).produce(
            self._request((source,), delivery_mode="alternating")
        )

        self.assertEqual(len(executor.rows), 1)
        prepared = executor.rows[0]
        self.assertEqual(prepared.delivery_mode, "alternating")
        self.assertEqual(len(prepared.sources), 1)
        self.assertEqual(prepared.transform_path, self.transform_path.resolve())

    def test_rejects_an_executor_that_changes_the_exact_feature_axis(self) -> None:
        returned_axis = self.feature_ids[[1, 0, 2]]
        executor = _FakeOSSRowExecutor(returned_axis)
        source = self._publish_source(
            "single-source",
            subject_id="generic-axis-subject",
            delivery_mode="alternating",
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "changed the exact final fiber axis",
        ):
            self._toolchain(executor).produce(
                self._request((source,), delivery_mode="alternating")
            )

        self.assertEqual(len(executor.rows), 1)
        np.testing.assert_array_equal(executor.rows[0].feature_ids, self.feature_ids)

    def test_rejects_a_source_hash_not_bound_to_its_parameter_artifact(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "tampered-hash-source",
            subject_id="generic-tampered-hash-subject",
            delivery_mode="alternating",
        )
        tampered = replace(source, stimulation_hash=_digest(123_456))

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "source parameter artifact differs from stimulation_hash",
        ):
            self._toolchain(executor).produce(
                self._request((tampered,), delivery_mode="alternating")
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_a_scientific_identity_not_derived_from_the_row(self) -> None:
        source = self._publish_source(
            "identity-source",
            subject_id="generic-identity-subject",
            delivery_mode="alternating",
        )
        request = self._request((source,), delivery_mode="alternating")

        with self.assertRaisesRegex(
            ActivationProviderError,
            "scientific_identity differs from the complete row cache key",
        ):
            replace(request, scientific_identity=_digest(654_321))

    def test_rejects_nested_template_path_outside_the_repository_root(self) -> None:
        outside = self.root / "outside-segmask.nii"
        outside.write_bytes(b"outside segmentation\n")
        source = self._publish_source(
            "outside-template-source",
            subject_id="generic-outside-template-subject",
            delivery_mode="alternating",
            geometry_overrides={
                "template_segmask_uri": outside.as_uri(),
                "template_segmask_sha256": sha256_file(outside),
            },
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "template_segmask is outside its configured roots",
        ):
            self._toolchain(_FakeOSSRowExecutor()).produce(
                self._request((source,), delivery_mode="alternating")
            )

    def test_rejects_input_mutation_before_result_publication(self) -> None:
        source = self._publish_source(
            "mutable-input-source",
            subject_id="generic-mutable-input-subject",
            delivery_mode="alternating",
        )
        executor = _FakeOSSRowExecutor(
            mutation=lambda: self.reconstruction_path.write_bytes(
                b"mutated reconstruction with a different size\n"
            )
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "reconstruction changed during OSS row production",
        ):
            self._toolchain(executor).produce(
                self._request((source,), delivery_mode="alternating")
            )

        self.assertEqual(len(executor.rows), 1)

    def test_rejects_source_and_document_identity_mismatches(self) -> None:
        cases = (
            (
                {"parameter_source_id": "different-parameter-source"},
                "source parameter ID differs from typed source",
            ),
            (
                {"locator_source_id": "different-locator-source"},
                "source locator differs from typed producer row",
            ),
        )

        for kwargs, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                executor = _FakeOSSRowExecutor()
                source = self._publish_source(
                    "typed-source",
                    subject_id="generic-mismatch-subject",
                    delivery_mode="alternating",
                    **kwargs,
                )
                with self.assertRaisesRegex(
                    OSSProducerExecutionError,
                    expected_message,
                ):
                    self._toolchain(executor).produce(
                        self._request((source,), delivery_mode="alternating")
                    )
                self.assertEqual(executor.rows, [])

    def test_rejects_a_wrong_reconstruction_content_hash(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "wrong-hash-source",
            subject_id="generic-hash-subject",
            delivery_mode="alternating",
            declared_reconstruction_hash=_digest(999_999),
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "reconstruction content differs from its declared hash",
        ):
            self._toolchain(executor).produce(
                self._request((source,), delivery_mode="alternating")
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_continuous_sources_with_different_geometry(self) -> None:
        executor = _FakeOSSRowExecutor()
        subject_id = "generic-geometry-subject"
        source_a = self._publish_source(
            "geometry-source-a",
            subject_id=subject_id,
            contacts=_case_return_contacts(1),
        )
        source_b = self._publish_source(
            "geometry-source-b",
            subject_id=subject_id,
            contacts=_case_return_contacts(2),
            geometry_overrides={"electrode_model": "Different Synthetic Lead"},
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "continuous sources do not share exact geometry",
        ):
            self._toolchain(executor).produce(
                self._request((source_a, source_b), delivery_mode="continuous")
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_contact_overlap_across_continuous_sources(self) -> None:
        executor = _FakeOSSRowExecutor()
        subject_id = "generic-overlap-subject"
        source_a = self._publish_source(
            "overlap-source-a",
            subject_id=subject_id,
            contacts=_case_return_contacts(1),
        )
        source_b = self._publish_source(
            "overlap-source-b",
            subject_id=subject_id,
            contacts=_case_return_contacts(1),
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "continuous sources reuse contacts: \\[1\\]",
        ):
            self._toolchain(executor).produce(
                self._request((source_a, source_b), delivery_mode="continuous")
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_mixed_voltage_return_topology(self) -> None:
        executor = _FakeOSSRowExecutor()
        subject_id = "generic-return-topology-subject"
        case_return = self._publish_source(
            "case-return-source",
            subject_id=subject_id,
            contacts=_case_return_contacts(1),
        )
        electrode_return = self._publish_source(
            "electrode-return-source",
            subject_id=subject_id,
            contacts=_electrode_return_contacts(2, 3),
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "continuous voltage sources cannot mix return topologies",
        ):
            self._toolchain(executor).produce(
                self._request(
                    (case_return, electrode_return),
                    delivery_mode="continuous",
                )
            )

        self.assertEqual(executor.rows, [])

    def test_rejects_backend_attestation_mismatch_before_execution(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "attestation-mismatch-source",
            subject_id="generic-attestation-subject",
            delivery_mode="alternating",
        )
        toolchain = self._toolchain(
            executor,
            backend_version_resolver=lambda _root: "different-toolchain-version",
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "implementation differs from the row cache backend version",
        ):
            toolchain.produce(
                self._request((source,), delivery_mode="alternating")
            )
        self.assertEqual(executor.rows, [])

    def test_backend_attestation_is_cached_once_across_rows(self) -> None:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            "attestation-change-source",
            subject_id="generic-attestation-change-subject",
            delivery_mode="alternating",
        )
        calls = 0

        def resolver(_root: Path) -> str:
            nonlocal calls
            calls += 1
            return (
                "synthetic-toolchain-v1"
                if calls == 1
                else "changed-toolchain-version"
            )

        toolchain = self._toolchain(
            executor,
            backend_version_resolver=resolver,
        )
        request = self._request((source,), delivery_mode="alternating")
        toolchain.produce(request)
        toolchain.produce(request)
        self.assertEqual(calls, 1)
        self.assertEqual(len(executor.rows), 2)

    def test_backend_attestation_covers_all_core_python_modules(self) -> None:
        repository = self.root / "attestation-repository"
        for relative in OSS_PRODUCER_IMPLEMENTATION_PATHS:
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixed:{relative}\n", encoding="utf-8")
        dynamic = (
            repository
            / "my_helper"
            / "fiber"
            / "core"
            / "dual_frequency"
            / "workflow"
            / "planner.py"
        )
        dynamic.parent.mkdir(parents=True, exist_ok=True)
        dynamic.write_text("VALUE = 1\n", encoding="utf-8")
        first = oss_backend_version(repository)
        dynamic.write_text("VALUE = 2\n", encoding="utf-8")
        second = oss_backend_version(repository)
        self.assertNotEqual(first, second)

    def test_installed_source_hash_covers_non_generated_package_resources(self) -> None:
        site_packages = self.root / "site-packages"
        for package in ("ossdbs", "leaddbsinterface"):
            package_root = site_packages / package
            package_root.mkdir(parents=True)
            (package_root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        resource = site_packages / "ossdbs" / "axon.hoc"
        resource.write_text("proc stimulate() {}\n", encoding="utf-8")
        first = _hash_oss_source_tree(site_packages)
        resource.write_text("proc stimulate() { stoprun = 1 }\n", encoding="utf-8")
        second = _hash_oss_source_tree(site_packages)
        self.assertNotEqual(first, second)
        generated = site_packages / "ossdbs" / "__pycache__" / "module.pyc"
        generated.parent.mkdir()
        generated.write_bytes(b"generated")
        self.assertEqual(second, _hash_oss_source_tree(site_packages))

    def test_rejects_subject_locator_bound_to_another_subject_root(self) -> None:
        source = self._publish_source(
            "cross-subject-root-source",
            subject_id="generic-subject-root-a",
            delivery_mode="alternating",
        )
        other_root = self.root / "different-subject-root"
        other_root.mkdir()
        self.subject_roots[source.subject_id] = other_root

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "subject_dir is outside its configured roots",
        ):
            self._toolchain(_FakeOSSRowExecutor()).produce(
                self._request((source,), delivery_mode="alternating")
            )

    def test_external_stage_streams_logs_without_buffering(self) -> None:
        log_prefix = self.root / "external-stage" / "successful"
        SubprocessOSSRowExecutor._run(
            (
                sys.executable,
                "-c",
                "import sys; print('stdout-line'); print('stderr-line', file=sys.stderr)",
            ),
            cwd=self.root,
            log_prefix=log_prefix,
            timeout_seconds=5.0,
        )
        self.assertEqual(
            log_prefix.with_suffix(".stdout.log").read_text(encoding="utf-8"),
            "stdout-line\n",
        )
        self.assertEqual(
            log_prefix.with_suffix(".stderr.log").read_text(encoding="utf-8"),
            "stderr-line\n",
        )

    @unittest.skipUnless(os.name == "posix", "executable scripts require POSIX")
    def test_external_stage_prepends_environment_bin_to_path(self) -> None:
        environment_bin = self.root / "locked-environment" / "bin"
        environment_bin.mkdir(parents=True)
        python = environment_bin / "python"
        nested_executable = environment_bin / "nrnivmodl"
        python.write_text("#!/bin/sh\nnrnivmodl\n", encoding="utf-8")
        nested_executable.write_text(
            "#!/bin/sh\nprintf 'nested-path-ok\\n'\n",
            encoding="utf-8",
        )
        python.chmod(0o755)
        nested_executable.chmod(0o755)
        log_prefix = self.root / "external-stage" / "nested-path"

        SubprocessOSSRowExecutor._run(
            (str(python),),
            cwd=self.root,
            log_prefix=log_prefix,
            timeout_seconds=5.0,
        )

        self.assertEqual(
            log_prefix.with_suffix(".stdout.log").read_text(encoding="utf-8"),
            "nested-path-ok\n",
        )
        self.assertEqual(
            log_prefix.with_suffix(".stderr.log").read_text(encoding="utf-8"),
            "",
        )

    def test_external_stage_timeout_terminates_the_process_group(self) -> None:
        marker = self.root / "escaped-child.txt"
        child = (
            "import pathlib,time; time.sleep(1.0); "
            f"pathlib.Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
            "time.sleep(60.0)"
        )

        with self.assertRaisesRegex(
            OSSProducerExecutionError,
            "external OSS command timed out",
        ):
            SubprocessOSSRowExecutor._run(
                (sys.executable, "-c", parent),
                cwd=self.root,
                log_prefix=self.root / "external-stage" / "timeout",
                timeout_seconds=0.1,
            )
        time.sleep(1.2)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "posix", "process groups require POSIX")
    def test_sigterm_cascades_to_the_active_external_process_group(self) -> None:
        external_pid_path = self.root / "external-parent.pid"
        descendant_pid_path = self.root / "external-descendant.pid"
        descendant = (
            "import os,pathlib,time; "
            f"pathlib.Path({str(descendant_pid_path)!r}).write_text("
            "str(os.getpid()), encoding='utf-8'); "
            "time.sleep(60.0)"
        )
        external = (
            "import os,pathlib,subprocess,sys,time; "
            f"pathlib.Path({str(external_pid_path)!r}).write_text("
            "str(os.getpid()), encoding='utf-8'); "
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}]); "
            "time.sleep(60.0)"
        )
        package_root = Path(__file__).resolve().parents[2]
        wrapper = (
            "import pathlib,sys; "
            f"sys.path.insert(0, {str(package_root)!r}); "
            "from dual_frequency.runtime.oss_toolchain import "
            "SubprocessOSSRowExecutor; "
            "SubprocessOSSRowExecutor._run("
            f"({sys.executable!r}, '-c', {external!r}), "
            f"cwd=pathlib.Path({str(self.root)!r}), "
            f"log_prefix=pathlib.Path({str(self.root / 'cascade')!r}), "
            "timeout_seconds=60.0)"
        )
        process = subprocess.Popen(
            (sys.executable, "-c", wrapper),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        def cleanup() -> None:
            if process.poll() is None:
                process.kill()
            if external_pid_path.exists():
                try:
                    os.killpg(
                        int(external_pid_path.read_text(encoding="utf-8")),
                        signal.SIGKILL,
                    )
                except (ProcessLookupError, ValueError):
                    pass

        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5.0
        while (
            not external_pid_path.exists() or not descendant_pid_path.exists()
        ) and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.01)
        if not external_pid_path.exists() or not descendant_pid_path.exists():
            stdout, stderr = process.communicate(timeout=5.0)
            self.fail(f"external process group did not start: {stdout!r} {stderr!r}")

        process.terminate()
        process.wait(timeout=5.0)
        process.communicate()
        self.assertNotEqual(process.returncode, 0)
        pids = (
            int(external_pid_path.read_text(encoding="utf-8")),
            int(descendant_pid_path.read_text(encoding="utf-8")),
        )
        deadline = time.monotonic() + 2.0
        live = set(pids)
        while live and time.monotonic() < deadline:
            for pid in tuple(live):
                status = subprocess.run(
                    ("ps", "-o", "stat=", "-p", str(pid)),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                state = status.stdout.strip()
                if status.returncode != 0 or not state or state.startswith("Z"):
                    live.discard(pid)
            if live:
                time.sleep(0.01)
        self.assertFalse(live)

    def test_large_row_execution_preserves_axis_and_exact_sample_states(self) -> None:
        row = replace(
            self._prepared_row_for_converter(control_mode="voltage"),
            scientific_identity=_digest(9876),
            feature_ids=np.arange(1, 7003, dtype=np.int64),
        )
        executor = SubprocessOSSRowExecutor(
            work_root=self.root / "chunked-executor",
            repository_root=self.repository_root,
            environment_file=self.environment_file,
        )
        observed_chunks: list[PreparedOSSRow] = []

        def execute_chunk(
            chunk: PreparedOSSRow,
            *,
            include_evidence: bool,
        ) -> OSSRowExecutionEvidence:
            self.assertTrue(include_evidence)
            observed_chunks.append(chunk)
            counts = np.remainder(chunk.feature_ids, 11).astype(np.int64)
            states = np.zeros((10, chunk.feature_ids.size), dtype=np.int8)
            for column, count in enumerate(counts.tolist()):
                states[:count, column] = 1
            probabilities = (counts.astype(np.float64) / 10.0).astype(np.float32)
            return OSSRowExecutionEvidence(
                OSSRowProduct(chunk.feature_ids, probabilities),
                states,
            )

        with mock.patch.object(
            executor,
            "_execute_single",
            side_effect=execute_chunk,
        ):
            result = executor.execute_with_evidence(row)

        self.assertEqual(
            [chunk.feature_ids.size for chunk in observed_chunks],
            [OSS_MAX_FIBERS_PER_EXECUTION, OSS_MAX_FIBERS_PER_EXECUTION, 2],
        )
        self.assertEqual(len({chunk.scientific_identity for chunk in observed_chunks}), 3)
        np.testing.assert_array_equal(result.product.feature_ids, row.feature_ids)
        expected_counts = np.remainder(row.feature_ids, 11).astype(np.int64)
        np.testing.assert_array_equal(
            result.product.probabilities,
            (expected_counts.astype(np.float64) / 10.0).astype(np.float32),
        )
        for column, count in enumerate(expected_counts.tolist()):
            np.testing.assert_array_equal(
                result.sample_states[:, column],
                np.concatenate(
                    (
                        np.ones(count, dtype=np.int8),
                        np.zeros(10 - count, dtype=np.int8),
                    )
                ),
            )

    @unittest.skipUnless(os.name == "posix", "process groups require POSIX")
    def test_termination_kills_a_sigterm_resistant_descendant(self) -> None:
        pid_path = self.root / "resistant-child.pid"
        child = (
            "import os,pathlib,signal,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(pid_path)!r}).write_text(str(os.getpid()), encoding='utf-8'); "
            "time.sleep(60.0)"
        )
        parent = (
            "import pathlib,subprocess,sys,time\n"
            f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
            f"pid_path=pathlib.Path({str(pid_path)!r})\n"
            "deadline=time.monotonic()+5.0\n"
            "while not pid_path.exists() and time.monotonic()<deadline:\n"
            "    time.sleep(0.01)\n"
            "if not pid_path.exists():\n"
            "    raise RuntimeError('child did not become ready')\n"
        )
        process = subprocess.Popen(
            (sys.executable, "-c", parent),
            start_new_session=True,
        )
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5.0
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(pid_path.exists())
        child_pid = int(pid_path.read_text(encoding="utf-8"))
        process_group_id = process.pid
        process.wait(timeout=5.0)
        _terminate_process_group(
            process,
            process_group_id=process_group_id,
            grace_seconds=0.1,
        )
        deadline = time.monotonic() + 2.0
        live = True
        while live and time.monotonic() < deadline:
            status = subprocess.run(
                ("ps", "-o", "stat=", "-p", str(child_pid)),
                capture_output=True,
                text=True,
                check=False,
            )
            state = status.stdout.strip()
            live = status.returncode == 0 and bool(state) and not state.startswith("Z")
            if live:
                time.sleep(0.01)
        self.assertFalse(live)

    def test_external_executor_revalidates_environment_before_and_after_row(self) -> None:
        row = self._prepared_row_for_converter(control_mode="voltage")
        executor = SubprocessOSSRowExecutor(
            work_root=self.root / "external-executor",
            repository_root=self.repository_root,
            environment_file=self.environment_file,
        )
        command = self.root / "command"
        command.write_text("command\n", encoding="utf-8")
        commands = OSSExecutableSet(
            matlab=command,
            environment_root=self.root,
            python=command,
            prepareaxonmodel=command,
            leaddbs2ossdbs=command,
            ossdbs=command,
            run_pathway_activation=command,
        )
        filtered_path = self.root / "filtered-connectome.mat"
        filtered_path.write_bytes(b"filtered\n")
        filtered = FilteredConnectome(
            path=filtered_path,
            feature_ids=row.feature_ids,
            local_fiber_ids=np.arange(1, row.feature_ids.size + 1, dtype=np.int64),
            point_counts=np.ones(row.feature_ids.size, dtype=np.int64),
            parent_fiber_count=row.feature_ids.size,
        )
        matlab_manifest = {
            "parameter_files": (),
            "active_contact_locations_mm": [],
            "segmask_path": str(row.template_segmask_path),
        }
        with (
            mock.patch.object(
                executor,
                "_resolve_commands",
                side_effect=(commands, commands),
            ) as resolve,
            mock.patch(
                "dual_frequency.runtime.oss_toolchain.write_filtered_connectome",
                return_value=filtered,
            ),
            mock.patch.object(
                executor,
                "_prepare_matlab_row",
                return_value=matlab_manifest,
            ),
            mock.patch.object(executor, "_run_samples", return_value=()),
            mock.patch(
                "dual_frequency.runtime.oss_toolchain.aggregate_activation_probabilities",
                return_value=np.zeros(row.feature_ids.size, dtype=np.float32),
            ),
        ):
            product = executor.execute(row)
        self.assertEqual(resolve.call_count, 2)
        np.testing.assert_array_equal(product.feature_ids, row.feature_ids)

    def test_entrypoints_are_bound_to_the_validated_environment_python(self) -> None:
        environment = self.root / "validated-environment"
        python = environment / "bin" / "python"
        entrypoint = environment / "bin" / "ossdbs"
        python.parent.mkdir(parents=True)
        python.write_text("python\n", encoding="utf-8")
        entrypoint.write_text("#!/different/python\n", encoding="utf-8")
        commands = OSSExecutableSet(
            matlab=self.root / "matlab",
            environment_root=environment,
            python=python,
            prepareaxonmodel=environment / "bin" / "prepareaxonmodel",
            leaddbs2ossdbs=environment / "bin" / "leaddbs2ossdbs",
            ossdbs=entrypoint,
            run_pathway_activation=environment / "bin" / "run_pathway_activation",
        )
        self.assertEqual(
            commands.entrypoint_command(entrypoint, "parameters.json"),
            (str(python), str(entrypoint), "parameters.json"),
        )

    def _prepared_row_for_converter(self, *, control_mode: str) -> PreparedOSSRow:
        executor = _FakeOSSRowExecutor()
        source = self._publish_source(
            f"converter-{control_mode}-source",
            subject_id=f"generic-converter-{control_mode}-subject",
            delivery_mode="alternating",
            control_mode=control_mode,
        )
        self._toolchain(executor).produce(
            self._request((source,), delivery_mode="alternating")
        )
        return executor.rows[0]

    def _converter_contract_fixture(
        self,
        row: PreparedOSSRow,
    ) -> tuple[dict[str, object], Path, Path, Path, Path]:
        sample = Path(
            tempfile.mkdtemp(prefix=f"converter-{row.control_mode}-", dir=self.root)
        )
        segmask = sample / "segmask.nii"
        segmask.write_bytes(row.template_segmask_path.read_bytes())
        pathway_h5 = sample / "Allocated_axons.h5"
        pathway_h5.write_bytes(b"synthetic allocated axons\n")
        pathway_json = sample / "Allocated_axons_parameters.json"
        pathway_json.write_text("{}\n", encoding="utf-8")
        output_path = sample / "Results"
        output_path.mkdir()
        converter: dict[str, object] = {
            "MaterialDistribution": {
                "MRIPath": str(segmask),
                "MRIMapping": {
                    "Unknown": 0,
                    "CSF": 3,
                    "White matter": 2,
                    "Gray matter": 1,
                    "Blood": 4,
                },
                "DiffusionTensorActive": False,
                "DTIPath": "",
            },
            "DielectricModel": {
                "Type": "ColeCole4",
                "CustomParameters": None,
            },
            "StimulationSignal": {
                "Type": "Rectangle",
                "CurrentControlled": row.control_mode == "current",
                "Frequency[Hz]": row.frequency_hz,
                "PulseWidth[us]": row.pulse_width_us,
                "PulseTopWidth[us]": 0.0,
                "CounterPulseWidth[us]": 0.0,
                "InterPulseWidth[us]": 0.0,
            },
            "CalcAxonActivation": True,
            "PointModel": {
                "Pathway": {
                    "Active": True,
                    "FileName": str(pathway_h5),
                }
            },
            "PathwayFile": str(pathway_json),
            "OutputPath": str(output_path),
            "ModelSide": 0,
        }
        return converter, segmask, pathway_h5, pathway_json, output_path

    def test_converter_contract_accepts_fixed_voltage_and_current_settings(self) -> None:
        for control_mode in ("voltage", "current"):
            with self.subTest(control_mode=control_mode):
                row = self._prepared_row_for_converter(control_mode=control_mode)
                converter, segmask, pathway_h5, pathway_json, output_path = (
                    self._converter_contract_fixture(row)
                )
                SubprocessOSSRowExecutor._validate_converter_contract(
                    converter,
                    row=row,
                    segmask_path=segmask,
                    pathway_h5=pathway_h5,
                    pathway_json=pathway_json,
                    output_path=output_path,
                )

    def test_converter_contract_rejects_dti_and_control_mode_drift(self) -> None:
        cases = (
            ("DiffusionTensorActive", True, "fixed isotropic tissue contract"),
            ("CurrentControlled", True, "fixed stimulation waveform"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                row = self._prepared_row_for_converter(control_mode="voltage")
                converter, segmask, pathway_h5, pathway_json, output_path = (
                    self._converter_contract_fixture(row)
                )
                section = (
                    converter["MaterialDistribution"]
                    if field == "DiffusionTensorActive"
                    else converter["StimulationSignal"]
                )
                if not isinstance(section, dict):
                    raise AssertionError("converter fixture section must be a dictionary")
                section[field] = value
                with self.assertRaisesRegex(OSSProducerExecutionError, message):
                    SubprocessOSSRowExecutor._validate_converter_contract(
                        converter,
                        row=row,
                        segmask_path=segmask,
                        pathway_h5=pathway_h5,
                        pathway_json=pathway_json,
                        output_path=output_path,
                    )


if __name__ == "__main__":
    unittest.main()
