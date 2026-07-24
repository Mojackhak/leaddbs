"""Endpoint-local input and canonical exposure provider tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import nibabel as nib
import h5py
import numpy as np

from seed_target_connectivity.connectome import LeadDBSHDF5Connectome

from dual_frequency.backends.activation import OSS_SCIENTIFIC_BACKEND_VERSION
from dual_frequency.cache import (
    ArtifactStore,
    CacheCorruption,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
    sha256_file,
)
from dual_frequency.catalog import build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides, load_workflow
from dual_frequency.contracts import (
    AxisRef,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FormalResult,
    IndexedArrayView,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SourceRecord,
    SubjectRecord,
)
from dual_frequency.contracts.identity import canonical_hash
from dual_frequency.contracts.study_base import (
    ClinicalObservation,
    ComponentDefinition,
    ConnectomeDefinition,
    ContactRecord,
    ElectrodeDefinition,
    ProgramRecord,
    ScaleDefinition,
    SpatialDefinition,
    StimulationSource,
    StudyBaseRecord,
    SubscaleDefinition,
)
from dual_frequency.runtime.input_provider import (
    JitterTranslationContext,
    MatlabLeftToCanonicalTransformer,
    RuntimeInputProviderError,
    StudyRuntimeInputProvider,
    _FeatureSpace,
    _NiftiSampler,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
WORKFLOW_PATH = (
    REPOSITORY_ROOT
    / "my_helper"
    / "stnsnr"
    / "config"
    / "four_model_v1"
    / "workflow.yaml"
)
SCALE_ID = "mds_updrs_iii_score"
SECOND_SCALE_ID = "mds_updrs_iv"
FORMAL_CONNECTOME_ID = "synthetic-formal-connectome"


class _CopyTransformer:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = float(delay_seconds)
        self.calls = 0
        self._lock = threading.Lock()

    def transform(
        self,
        source: Path,
        destination: Path,
        configured_transform: Path,
    ) -> Path:
        self.assert_inputs(source, configured_transform)
        with self._lock:
            self.calls += 1
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    @staticmethod
    def assert_inputs(source: Path, configured_transform: Path) -> None:
        if not source.is_file() or not configured_transform.is_file():
            raise AssertionError("test transformer received a missing input")


def _observation(subject_id: str, phase_id: str, program_id: int, value: int) -> ClinicalObservation:
    return ClinicalObservation(
        observation_id=f"obs:{subject_id}:{phase_id}:{program_id}:{SCALE_ID}",
        subject_id=subject_id,
        phase_id=phase_id,
        program_id=program_id,
        scale_id=SCALE_ID,
        subscale_id="total",
        value=value,
        status="observed",
    )


def _source(
    subject_id: str,
    phase_id: str,
    program_id: int,
    electrode_id: str,
    group_id: str,
    delivery_mode: str,
    frequency_hz: float,
) -> StimulationSource:
    first_global_contact = 0 if electrode_id == "lead-L" else 4
    return StimulationSource(
        subject_id=subject_id,
        phase_id=phase_id,
        program_id=program_id,
        electrode_id=electrode_id,
        frequency_group_id=group_id,
        delivery_mode=delivery_mode,
        source_id=f"{group_id}-source",
        source_label="Component",
        component_id="component",
        frequency_hz=frequency_hz,
        control_mode="voltage",
        amplitude=2.0,
        pulse_width_us=60.0,
        contacts=(
            ContactRecord("case", "anode", 1.0),
            ContactRecord(first_global_contact, "cathode", 1.0),
        ),
    )


def _leaf(
    subject_dir: Path,
    phase_id: str,
    program_id: int,
    electrode_id: str,
    group_id: str,
    delivery_mode: str,
) -> Path:
    root = (
        subject_dir
        / "stimulations"
        / "MNI152NLin2009bAsym"
        / f"phase-{phase_id}"
        / f"program-{program_id}"
        / f"electrode-{electrode_id}"
        / f"frequency-group-{group_id}"
    )
    if delivery_mode == "continuous":
        return root / "delivery-continuous" / "joint" / "efield.nii.gz"
    return root / "delivery-alternating" / "derived" / "group-peak" / "efield.nii.gz"


def _write_field(path: Path, value: float, affine: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(np.full((4, 4, 2), value, dtype=np.float32), affine),
        str(path),
    )


def _write_field_array(path: Path, value: np.ndarray, affine: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(np.asarray(value, dtype=np.float32), affine),
        str(path),
    )


@dataclasses.dataclass(frozen=True)
class _FiberChunk:
    fiber_ids: np.ndarray
    points: np.ndarray
    point_offsets: np.ndarray


class _FakeConnectome:
    def __init__(self, chunk: _FiberChunk | tuple[_FiberChunk, ...]) -> None:
        self._chunks = chunk if isinstance(chunk, tuple) else (chunk,)
        self.iteration_count = 0

    def iter_chunks(self, _chunk_size: int):
        self.iteration_count += 1
        yield from self._chunks


def _materialize(store: ArtifactStore, artifact) -> np.ndarray:
    if isinstance(artifact, IndexedArrayView):
        return store.materialize_indexed_array_view(
            artifact,
            max_bytes=16 * 1024**3,
        )
    return store.materialize(
        artifact,
        expected_dtype=artifact.dtype,
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
    )


def uuid_for_array(value: np.ndarray) -> str:
    array = np.asarray(value)
    return canonical_hash(
        {"dtype": array.dtype.name, "values": array.tolist()},
        length=12,
    )


def _program(
    subject_id: str,
    phase_id: str,
    program_id: int,
    sources: tuple[StimulationSource, ...],
    value: int,
) -> ProgramRecord:
    return ProgramRecord(
        subject_id=subject_id,
        phase_id=phase_id,
        phase_label=phase_id,
        program_id=program_id,
        program_label=f"Program {program_id}",
        condition_role="configured",
        stimulation_state="active" if sources else "none",
        assessment_order=program_id,
        duration_label="configured",
        stimulation_start_date=None,
        assessment_date=None,
        exposure_days=None,
        observations=(_observation(subject_id, phase_id, program_id, value),),
        stimulation_sources=sources,
    )


class InputProviderTest(unittest.TestCase):
    def test_jitter_translation_is_deterministic_and_keyed_by_side(self) -> None:
        context = JitterTranslationContext(
            replicate_index=2,
            replicate_seed=12345,
            translation_sigma_mm=0.75,
        )
        arguments = {
            "binding_id": "phase-a_program-1",
            "frequency_class": "reference",
            "subject_id": "subject-a",
            "hemisphere": "R",
        }
        first = context.vector(**arguments)
        second = context.vector(**arguments)
        left = context.vector(**{**arguments, "hemisphere": "L"})
        np.testing.assert_array_equal(first, second)
        self.assertFalse(np.array_equal(first, left))

    def test_shared_connectome_geometry_is_single_write_and_read_only(self) -> None:
        path = self.root / "geometry-connectome" / "data.mat"
        path.parent.mkdir(parents=True)
        lengths = np.asarray([2, 3, 2], dtype=np.float64)
        point_ids = np.repeat(np.arange(1, 4, dtype=np.float32), lengths.astype(int))
        coordinates = np.vstack(
            (
                np.arange(point_ids.size, dtype=np.float32),
                np.ones(point_ids.size, dtype=np.float32),
                np.full(point_ids.size, 2.0, dtype=np.float32),
            )
        )
        with h5py.File(path, "w") as handle:
            handle.create_dataset("idx", data=lengths.reshape(1, -1))
            handle.create_dataset(
                "fibers",
                data=np.vstack((coordinates, point_ids)),
                chunks=(4, 4),
                compression="gzip",
            )
        connectome = LeadDBSHDF5Connectome(path)
        study = self._study(missing_addon_for_last_subject=False)
        provider, _catalog, _store, _root = self._provider(study, shared_cache=True)

        with mock.patch.object(
            provider,
            "_produce_connectome_geometry",
            wraps=provider._produce_connectome_geometry,
        ) as produce:
            with ThreadPoolExecutor(max_workers=4) as executor:
                geometries = tuple(
                    executor.map(
                        lambda _index: provider._shared_connectome_geometry(connectome),
                        range(4),
                    )
                )

        self.assertEqual(produce.call_count, 1)
        self.assertEqual(len({item.cache_identity for item in geometries}), 1)
        geometry = geometries[0]
        self.assertIsInstance(geometry.points, np.memmap)
        self.assertIsInstance(geometry.point_offsets, np.memmap)
        self.assertFalse(geometry.points.flags.writeable)
        self.assertFalse(geometry.point_offsets.flags.writeable)
        np.testing.assert_array_equal(geometry.points, coordinates.T)
        np.testing.assert_array_equal(geometry.point_offsets, [0, 2, 5, 7])
        audit = json.loads(geometry.audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["logical_point_coverage_count"], 7)
        self.assertEqual(audit["n_fibers"], 3)

        key = provider._connectome_geometry_key(connectome)
        source_entry = provider._scientific_cache.entry_path(key)
        copied_root = self.root / "copied-scientific-cache"
        copied_cache = ContentAddressedCache(copied_root)
        copied_entry = copied_cache.entry_path(key)
        copied_entry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_entry, copied_entry)
        copied_provider, _catalog, _store, _root = self._provider(
            study,
            shared_cache=True,
            scientific_cache_root=copied_root,
        )
        with mock.patch.object(
            copied_provider,
            "_produce_connectome_geometry",
            side_effect=AssertionError("copied geometry must not be reproduced"),
        ):
            copied = copied_provider._shared_connectome_geometry(connectome)
        np.testing.assert_array_equal(copied.points, coordinates.T)
        np.testing.assert_array_equal(copied.point_offsets, [0, 2, 5, 7])

        copied_points = copied_entry / "points.npy"
        with copied_points.open("r+b") as stream:
            stream.seek(-1, 2)
            original = stream.read(1)
            stream.seek(-1, 2)
            stream.write(bytes((original[0] ^ 1,)))
        corrupted_provider, _catalog, _store, _root = self._provider(
            study,
            shared_cache=True,
            scientific_cache_root=copied_root,
        )
        with self.assertRaises(CacheCorruption):
            corrupted_provider._shared_connectome_geometry(connectome)

    def test_shared_geometry_matches_uncached_point_balanced_adapter(self) -> None:
        path = self.root / "parity-connectome" / "data.mat"
        path.parent.mkdir(parents=True)
        lengths = np.asarray([2, 2, 2], dtype=np.float64)
        point_ids = np.repeat(np.arange(1, 4, dtype=np.float32), 2)
        coordinates = np.asarray(
            (
                (1.0, 0.0, 0.0),
                (2.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (3.0, 1.0, 0.0),
                (1.0, 1.0, 1.0),
                (2.0, 1.0, 1.0),
            ),
            dtype=np.float32,
        )
        with h5py.File(path, "w") as handle:
            handle.create_dataset("idx", data=lengths.reshape(1, -1))
            handle.create_dataset(
                "fibers",
                data=np.vstack((coordinates.T, point_ids)),
                chunks=(4, 3),
                compression="gzip",
            )
        study = self._study(missing_addon_for_last_subject=False)
        uncached_provider, uncached_catalog, _store, _root = self._provider(
            study,
            fiber_point_byte_budget=1024,
        )
        cached_provider, cached_catalog, _store, _root = self._provider(
            study,
            shared_cache=True,
            fiber_point_byte_budget=24,
        )
        streamed_provider, streamed_catalog, _store, _root = self._provider(
            study,
            shared_cache=True,
            scientific_cache_root=self.root / "streaming-scientific-cache",
            fiber_point_byte_budget=24,
            fiber_geometry_shared_budget=1,
        )
        ids = np.arange(1, 4, dtype=np.int64)
        axis = AxisRef("parity-fiber-axis", 3, "e" * 64)
        uncached_feature_space = _FeatureSpace(
            axis,
            ids,
            None,
            LeadDBSHDF5Connectome(path),
            path,
        )
        cached_feature_space = _FeatureSpace(
            axis,
            ids,
            None,
            LeadDBSHDF5Connectome(path),
            path,
        )
        streamed_feature_space = _FeatureSpace(
            axis,
            ids,
            None,
            LeadDBSHDF5Connectome(path),
            path,
        )
        subject_ids = tuple(subject.subject_id for subject in study.subjects[:2])
        uncached_endpoint = self._endpoint(uncached_catalog, "reference_voxel")
        cached_endpoint = self._endpoint(cached_catalog, "reference_voxel")
        streamed_endpoint = self._endpoint(streamed_catalog, "reference_voxel")
        binding = self.configuration.direct_voxel.endpoint_pair.reference
        uncached, uncached_missing = uncached_provider._matrix_for_binding(
            uncached_endpoint,
            subject_ids,
            binding,
            "reference",
            uncached_feature_space,
            allow_absent=False,
        )
        cached, cached_missing = cached_provider._matrix_for_binding(
            cached_endpoint,
            subject_ids,
            binding,
            "reference",
            cached_feature_space,
            allow_absent=False,
        )
        with mock.patch.object(
            streamed_provider,
            "_shared_connectome_geometry",
            side_effect=AssertionError("oversize geometry must stream from HDF5"),
        ):
            streamed, streamed_missing = streamed_provider._matrix_for_binding(
                streamed_endpoint,
                subject_ids,
                binding,
                "reference",
                streamed_feature_space,
                allow_absent=False,
            )
        try:
            self.assertEqual(uncached_missing, cached_missing)
            self.assertEqual(cached_missing, streamed_missing)
            np.testing.assert_array_equal(
                uncached.materialize(),
                cached.materialize(),
            )
            np.testing.assert_array_equal(
                cached.materialize(),
                streamed.materialize(),
            )
        finally:
            uncached_provider._release_temporary_matrix(uncached)
            cached_provider._release_temporary_matrix(cached)
            streamed_provider._release_temporary_matrix(streamed)

    def test_jitter_sampler_translates_field_with_linear_zero_padded_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gradient.nii.gz"
            data = np.indices((5, 4, 3), dtype=np.float32)[0]
            nib.save(nib.Nifti1Image(data, np.eye(4)), path)
            sampler = _NiftiSampler(path)
            coordinates = np.asarray(((2.0, 1.0, 1.0), (0.0, 1.0, 1.0)))
            unshifted = sampler.sample(coordinates)
            shifted = sampler.sample(
                coordinates,
                translation_mm=np.asarray((1.0, 0.0, 0.0)),
            )
            np.testing.assert_allclose(unshifted, np.asarray((2.0, 0.0)))
            np.testing.assert_allclose(shifted, np.asarray((1.0, 0.0)))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.affine = np.eye(4, dtype=np.float64)
        self.brainmask = self.root / "brainmask.nii.gz"
        nib.save(
            nib.Nifti1Image(np.ones((4, 4, 2), dtype=np.uint8), self.affine),
            str(self.brainmask),
        )
        self.transform = self.root / "Composite.nii.gz"
        self.transform.write_bytes(b"synthetic-transform")
        self.inverse_transform = self.root / "InverseComposite.nii.gz"
        self.inverse_transform.write_bytes(b"synthetic-inverse-transform")
        self.configuration = load_workflow(
            WORKFLOW_PATH,
            WorkflowOverrides(
                scales=(SCALE_ID,),
                models=("reference_voxel", "addon_voxel"),
                through="observed",
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _study(
        self,
        *,
        missing_addon_for_last_subject: bool,
        missing_addon_reference_for_last_subject: bool = False,
    ) -> StudyBaseRecord:
        subjects: list[SubjectRecord] = []
        for index in range(12):
            subject_id = f"participant-{index + 1:02d}"
            subject_dir = self.root / subject_id
            electrodes = (
                ElectrodeDefinition("lead-L", "L", "Synthetic", 4, 2),
                ElectrodeDefinition("lead-R", "R", "Synthetic", 4, 1),
            )
            reference_sources: list[StimulationSource] = []
            addon_sources: list[StimulationSource] = []
            for electrode_id in ("lead-L", "lead-R"):
                reference_source = _source(
                    subject_id,
                    "T2",
                    1,
                    electrode_id,
                    "reference-group",
                    "continuous",
                    130.0,
                )
                reference_sources.append(reference_source)
                _write_field(
                    _leaf(subject_dir, "T2", 1, electrode_id, "reference-group", "continuous"),
                    250.0,
                    self.affine,
                )
                addon_reference = _source(
                    subject_id,
                    "T3",
                    2,
                    electrode_id,
                    "reference-group",
                    "continuous",
                    130.0,
                )
                if not (missing_addon_reference_for_last_subject and index == 11):
                    addon_sources.append(addon_reference)
                    _write_field(
                        _leaf(
                            subject_dir,
                            "T3",
                            2,
                            electrode_id,
                            "reference-group",
                            "continuous",
                        ),
                        250.0,
                        self.affine,
                    )
                if not (missing_addon_for_last_subject and index == 11):
                    delivery = "alternating" if index == 0 else "continuous"
                    addon_source = _source(
                        subject_id,
                        "T3",
                        2,
                        electrode_id,
                        "addon-group",
                        delivery,
                        30.0,
                    )
                    addon_sources.append(addon_source)
                    _write_field(
                        _leaf(subject_dir, "T3", 2, electrode_id, "addon-group", delivery),
                        80.0,
                        self.affine,
                    )
            subjects.append(
                SubjectRecord(
                    subject_id=subject_id,
                    subject_label=subject_id,
                    leaddbs_subject_dir=subject_dir,
                    electrode_reconstruction=subject_dir / "reconstruction.mat",
                    electrodes=electrodes,
                    programs=(
                        _program(subject_id, "T0", 0, (), 40),
                        _program(subject_id, "T2", 1, tuple(reference_sources), 30),
                        _program(subject_id, "T3", 2, tuple(addon_sources), 20),
                    ),
                    electrode_order=("lead-L", "lead-R"),
                )
            )
        return StudyBaseRecord(
            schema_version="dual_frequency_study_v1",
            study_id="synthetic-study",
            study_label="Synthetic Study",
            data_version="1",
            components=(ComponentDefinition("component", "Component"),),
            scales=(
                ScaleDefinition(
                    SCALE_ID,
                    "Motor score",
                    "integer",
                    "score",
                    "lower",
                    (SubscaleDefinition("total", "Total"),),
                ),
            ),
            spatial=SpatialDefinition(
                canonical_space="MNI152NLin2009bAsym",
                canonical_hemisphere="R",
                left_to_right_transform=self.transform,
                brainmask_id="synthetic-mask",
                brainmask_path=self.brainmask,
                connectomes=(),
            ),
            subjects=tuple(subjects),
            source_path=self.root / "study_base.json",
            source_sha256="a" * 64,
        )

    def _activation_study(self) -> StudyBaseRecord:
        """Build a target-neutral, dynamically grouped OSS input fixture."""

        study = self._study(missing_addon_for_last_subject=False)
        connectome_path = self.root / "synthetic-formal-connectome.mat"
        connectome_path.write_bytes(b"synthetic-connectome")
        subjects: list[SubjectRecord] = []
        for subject_index, subject in enumerate(study.subjects):
            subject.electrode_reconstruction.parent.mkdir(parents=True, exist_ok=True)
            subject.electrode_reconstruction.write_bytes(
                f"synthetic-reconstruction:{subject.subject_id}".encode("ascii")
            )
            programs: list[ProgramRecord] = []
            for program in subject.programs:
                second_scale = ClinicalObservation(
                    observation_id=(
                        f"obs:{subject.subject_id}:{program.phase_id}:"
                        f"{program.program_id}:{SECOND_SCALE_ID}"
                    ),
                    subject_id=subject.subject_id,
                    phase_id=program.phase_id,
                    program_id=program.program_id,
                    scale_id=SECOND_SCALE_ID,
                    subscale_id="total",
                    value=int(program.observations[0].value) + 5,
                    status="observed",
                )
                sources = program.stimulation_sources
                if program.phase_id == "T2" and program.program_id == 1:
                    if subject_index == 0:
                        sources = tuple(
                            dataclasses.replace(
                                source,
                                source_label="Low-frequency decoy",
                                component_id="target_stn",
                                frequency_hz=30.0,
                            )
                            for source in sources
                        )
                    else:
                        expanded: list[StimulationSource] = []
                        for source in sources:
                            second_global_contact = (
                                1 if source.electrode_id == "lead-L" else 5
                            )
                            expanded.extend(
                                (
                                    dataclasses.replace(
                                        source,
                                        source_label="High frequency on SNr component",
                                        component_id="target_snr",
                                    ),
                                    dataclasses.replace(
                                        source,
                                        source_id="reference-continuous-source-b",
                                        source_label="High frequency on STN component",
                                        component_id="target_stn",
                                        contacts=(
                                            ContactRecord("case", "anode", 1.0),
                                            ContactRecord(
                                                second_global_contact,
                                                "cathode",
                                                1.0,
                                            ),
                                        ),
                                    ),
                                    dataclasses.replace(
                                        source,
                                        frequency_group_id="reference-alternating",
                                        delivery_mode="alternating",
                                        source_id="reference-alternating-source-a",
                                        source_label="Alternating high frequency on SNr",
                                        component_id="target_snr",
                                    ),
                                    dataclasses.replace(
                                        source,
                                        frequency_group_id="reference-alternating",
                                        delivery_mode="alternating",
                                        source_id="reference-alternating-source-b",
                                        source_label="Alternating high frequency on STN",
                                        component_id="target_stn",
                                        contacts=(
                                            ContactRecord("case", "anode", 1.0),
                                            ContactRecord(
                                                second_global_contact,
                                                "cathode",
                                                1.0,
                                            ),
                                        ),
                                    ),
                                    dataclasses.replace(
                                        source,
                                        frequency_group_id="low-frequency-decoy",
                                        source_id="low-frequency-decoy-source",
                                        source_label="Low frequency on STN component",
                                        component_id="target_stn",
                                        frequency_hz=30.0,
                                    ),
                                )
                            )
                            _write_field(
                                _leaf(
                                    subject.leaddbs_subject_dir,
                                    "T2",
                                    1,
                                    source.electrode_id,
                                    "reference-alternating",
                                    "alternating",
                                ),
                                240.0,
                                self.affine,
                            )
                        sources = tuple(expanded)
                programs.append(
                    dataclasses.replace(
                        program,
                        observations=(*program.observations, second_scale),
                        stimulation_sources=sources,
                    )
                )
            subjects.append(dataclasses.replace(subject, programs=tuple(programs)))

        return dataclasses.replace(
            study,
            components=(
                ComponentDefinition("target_stn", "STN"),
                ComponentDefinition("target_snr", "SNr"),
            ),
            scales=(
                *study.scales,
                ScaleDefinition(
                    SECOND_SCALE_ID,
                    "MDS-UPDRS IV",
                    "integer",
                    "score",
                    "lower",
                    (SubscaleDefinition("total", "Total"),),
                ),
            ),
            spatial=dataclasses.replace(
                study.spatial,
                connectomes=(
                    ConnectomeDefinition(
                        FORMAL_CONNECTOME_ID,
                        "Synthetic formal connectome",
                        "MNI152NLin2009bAsym",
                        connectome_path,
                        None,
                    ),
                ),
            ),
            subjects=tuple(subjects),
        )

    def _activation_configuration(self, scales: tuple[str, ...]):
        formal = dataclasses.replace(
            self.configuration.normative_fiber.formal_connectome,
            connectome_id=FORMAL_CONNECTOME_ID,
            label="Synthetic formal connectome",
            path=self.root / "synthetic-formal-connectome.mat",
        )
        return dataclasses.replace(
            self.configuration,
            direct_voxel=dataclasses.replace(
                self.configuration.direct_voxel,
                scales=scales,
                hard_computability=dataclasses.replace(
                    self.configuration.direct_voxel.hard_computability,
                    n_subjects_min=2,
                ),
            ),
            normative_fiber=dataclasses.replace(
                self.configuration.normative_fiber,
                scales=scales,
                connectomes=(formal,),
                hard_computability=dataclasses.replace(
                    self.configuration.normative_fiber.hard_computability,
                    n_subjects_min=2,
                ),
            ),
            selected_scales=scales,
            selected_models=("reference_fiber",),
            selected_connectomes=(FORMAL_CONNECTOME_ID,),
        )

    def _provider(
        self,
        study: StudyBaseRecord,
        *,
        transformer: _CopyTransformer | None = None,
        configuration=None,
        shared_cache: bool = False,
        scientific_cache_root: Path | None = None,
        fiber_point_byte_budget: int = 256 * 1024**2,
        fiber_geometry_shared_budget: int = 16 * 1024**3,
        sampler_cache_bytes: int = 2 * 1024**3,
    ):
        selected_configuration = configuration or self.configuration
        catalog = build_endpoint_catalog(selected_configuration, study)
        artifact_root = self.root / "artifacts"
        artifact_root.mkdir(parents=True, exist_ok=True)
        cache_root = scientific_cache_root or self.root / "scientific-cache"
        if shared_cache:
            cache_root.mkdir(parents=True, exist_ok=True)
        artifact_store = ArtifactStore(
            (artifact_root, cache_root) if shared_cache else (artifact_root,)
        )
        selected_transformer = transformer or _CopyTransformer()
        provider = StudyRuntimeInputProvider(
            study,
            selected_configuration,
            catalog,
            work_root=self.root / "provider-work",
            artifact_store=artifact_store,
            scientific_cache=(
                ContentAddressedCache(
                    cache_root
                )
                if shared_cache
                else None
            ),
            left_transformer=selected_transformer,
            fiber_point_byte_budget=fiber_point_byte_budget,
            fiber_geometry_shared_budget=fiber_geometry_shared_budget,
            sampler_cache_bytes=sampler_cache_bytes,
        )
        return provider, catalog, artifact_store, artifact_root

    @staticmethod
    def _endpoint(catalog, family: str):
        return next(item for item in catalog if item.key.model_family == family)

    @staticmethod
    def _endpoint_for_scale(catalog, family: str, scale_id: str):
        return next(
            item
            for item in catalog
            if item.key.model_family == family and item.key.scale_id == scale_id
        )

    @staticmethod
    def _accepted_source(endpoint, publisher) -> SourceRecord:
        selected_axis = AxisRef("selected-overlap", 1, "b" * 64)
        evidence = publisher.array(
            "weights.npy",
            np.ones(1, dtype=np.float64),
            kind="benefit_oriented_feature_weights",
            axes=(selected_axis,),
            units="coefficient",
            space=None,
        )
        return SourceRecord(
            endpoint=endpoint.key if hasattr(endpoint, "key") else endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200.0,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(selected_axis, "synthetic-selected-feature"),
            artifacts=(evidence,),
        )

    def _dependency(self, reference_endpoint, addon_endpoint, artifact_root):
        source = self._accepted_source(
            reference_endpoint,
            RunScopedArtifactPublisher(
                artifact_root / f"source-{addon_endpoint.endpoint_id}",
                f"source-{addon_endpoint.endpoint_id}",
                "1",
            ),
        )
        return ReferenceDependencyRecord(
            addon_endpoint=addon_endpoint.key,
            matched_reference_endpoint_id=reference_endpoint.endpoint_id,
            dependency_status="ready",
            reference_record=source,
            delta_reference=None,
        )

    @staticmethod
    def _valid_delta(subject_axis: AxisRef, artifact_root: Path) -> DeltaReferenceBundle:
        publisher = RunScopedArtifactPublisher(
            artifact_root / "delta-reference",
            "delta-reference",
            "1",
        )
        full = publisher.array(
            "full.npy",
            np.linspace(-1.0, 1.0, subject_axis.count, dtype=np.float64),
            kind="delta_reference_full_scores",
            axes=(subject_axis,),
            units="z_score",
            space=None,
        )
        folds = publisher.array(
            "folds.npy",
            np.tile(
                np.linspace(-1.0, 1.0, subject_axis.count, dtype=np.float64),
                (subject_axis.count, 1),
            ),
            kind="delta_reference_fold_scores",
            axes=(subject_axis, subject_axis),
            units="z_score",
            space=None,
        )
        support_rows = publisher.array(
            "support.npy",
            np.ones(subject_axis.count, dtype=np.float64),
            kind="delta_reference_support_rows",
            axes=(subject_axis,),
            units="fraction",
            space=None,
        )
        support_qc = publisher.document(
            "support_qc.json",
            {"schema_version": "synthetic_delta_support_v1"},
            kind="delta_reference_support_qc",
        )
        return DeltaReferenceBundle(
            input_status="valid",
            support_status="adequate",
            selected_reference_tau=200.0,
            selected_reference_coverage=5,
            full_scores=full,
            fold_scores=folds,
            support_rows=support_rows,
            support_qc=support_qc,
        )

    @staticmethod
    def _direct_final(
        endpoint,
        prepared: PreparedExposureRecord,
        artifact_root: Path,
        indices: np.ndarray,
        *,
        axis_hash: str | None = None,
        branch: str = "reference",
    ) -> FinalModelRecord:
        index_array = np.asarray(indices)
        identity_payload = {
            "parent_axis_sha256": prepared.feature_axis.sha256,
            "selected_indices": index_array.astype(np.int64).tolist(),
            "tau": 200.0,
            "coverage": 5,
        }
        identity_source = "selected_direct_voxel_feature_union"
        if endpoint.key.model_family.startswith("addon_"):
            identity_payload["branch"] = branch
            identity_source = "selected_addon_direct_voxel_feature_union"
        expected_hash = canonical_hash(identity_payload)
        selected_axis = AxisRef(
            "selected-direct",
            int(index_array.size),
            axis_hash or expected_hash,
        )
        index_artifact = RunScopedArtifactPublisher(
            artifact_root
            / (
                f"selected-{uuid_for_array(index_array)}-"
                f"{(axis_hash or expected_hash)[:8]}"
            ),
            "selected-direct",
            "1",
        ).array(
            "selected_feature_indices.npy",
            index_array,
            kind="selected_feature_indices",
            axes=(selected_axis,),
            units="index",
            space=None,
        )
        source = SourceRecord(
            endpoint=endpoint.key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200.0,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(
                selected_axis,
                identity_source,
            ),
            artifacts=(index_artifact,),
        )
        selected_branch = None
        selected_source = source
        if endpoint.key.model_family.startswith("addon_"):
            selected_branch = BranchRecord(
                endpoint=endpoint.key,
                branch=branch,
                intended_role="primary",
                input_status="valid",
                nuisance_design_status="valid",
                source=source,
            )
            selected_source = None
        return FinalModelRecord(
            endpoint=endpoint.key,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                endpoint.endpoint_id,
                branch,
                200.0,
                5,
                "loocv_linear",
            ),
            selected_source=selected_source,
            selected_branch=selected_branch,
        )

    @staticmethod
    def _activation_final_inputs(endpoint, endpoint_input, artifact_root: Path):
        if endpoint_input.subject_axis is None:
            raise AssertionError("activation fixture requires a ready subject axis")
        parent_ids = np.asarray((101, 205, 309, 407, 503, 601), dtype=np.int64)
        selected_ids = np.asarray((205, 407, 601), dtype=np.int64)
        parent_axis = AxisRef(
            "synthetic-formal-connectome:all-fibers",
            parent_ids.size,
            canonical_hash({"ordered_fiber_ids": parent_ids.tolist()}),
        )
        selected_id_digest = hashlib.sha256(
            np.ascontiguousarray(selected_ids).tobytes(order="C")
        ).hexdigest()
        selected_axis = AxisRef(
            "synthetic-formal-connectome:selected-fibers",
            selected_ids.size,
            canonical_hash(
                {
                    "parent_axis_sha256": parent_axis.sha256,
                    "selected_fiber_ids_sha256": selected_id_digest,
                    "tau": 800.0,
                    "coverage": 5,
                }
            ),
        )
        prepared_publisher = RunScopedArtifactPublisher(
            artifact_root / f"prepared-{endpoint.key.scale_id}",
            f"prepared-{endpoint.key.scale_id}",
            "1",
        )
        prepared = PreparedExposureRecord(
            endpoint=endpoint.key,
            subject_axis=endpoint_input.subject_axis,
            feature_axis=parent_axis,
            exposure=prepared_publisher.array(
                "exposure.npy",
                np.zeros(
                    (endpoint_input.subject_axis.count, parent_axis.count),
                    dtype=np.float32,
                ),
                kind="prepared_reference_fiber_exposure",
                axes=(endpoint_input.subject_axis, parent_axis),
                units="V/m",
                space="MNI152NLin2009bAsym",
            ),
            feature_ids=prepared_publisher.array(
                "feature_ids.npy",
                parent_ids,
                kind="canonical_connectome_fiber_ids",
                axes=(parent_axis,),
                units="fiber_id",
                space="MNI152NLin2009bAsym",
            ),
            delta_reference_input_status="not_applicable",
            delta_reference_reason_code="not_applicable",
            auxiliary_readiness=None,
            reference_condition_exposure=None,
            addon_reference_component_exposure=None,
            reference_overlap_mask=None,
            total_exposure=None,
        )
        selected_artifact = RunScopedArtifactPublisher(
            artifact_root / f"selected-{endpoint.key.scale_id}",
            f"selected-{endpoint.key.scale_id}",
            "1",
        ).array(
            "valid_union_ids.npy",
            selected_ids,
            kind="normative_fiber_valid_union_ids",
            axes=(selected_axis,),
            units="fiber_id",
            space=None,
        )
        source = SourceRecord(
            endpoint=endpoint.key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=800.0,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(
                selected_axis,
                "selected_normative_fiber_full_fold_valid_union",
            ),
            artifacts=(selected_artifact,),
        )
        final_model = FinalModelRecord(
            endpoint=endpoint.key,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                endpoint.endpoint_id,
                "reference",
                800.0,
                5,
                "loocv_linear",
            ),
            selected_source=source,
            selected_branch=None,
        )
        return prepared, final_model, parent_ids, selected_ids

    @staticmethod
    def _activation_source_signature(request) -> tuple[tuple[object, ...], ...]:
        return tuple(
            sorted(
                (
                    source.subject_id,
                    source.side,
                    source.frequency_group_id,
                    source.delivery_mode,
                    source.source_id,
                    source.geometry_hash,
                    source.stimulation_hash,
                    source.component_frequency_hash,
                    source.transform_hash,
                )
                for source in request.sources
            )
        )

    def _activation_request_for_scale(
        self,
        provider,
        catalog,
        artifact_root: Path,
        scale_id: str,
        label: str,
    ):
        endpoint = self._endpoint_for_scale(catalog, "reference_fiber", scale_id)
        endpoint_input = provider.publish_endpoint_input(
            endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / f"{label}-input",
                f"{label}-input",
                "1",
            ),
        )
        prepared, final_model, parent_ids, selected_ids = self._activation_final_inputs(
            endpoint,
            endpoint_input,
            artifact_root / label,
        )
        request = provider.activation_runtime_request(
            final_model,
            endpoint_input,
            prepared,
            RunScopedArtifactPublisher(
                artifact_root / f"{label}-activation",
                f"{label}-activation",
                "1",
            ),
            workers=3,
            allow_expensive_producers=False,
        )
        return endpoint, endpoint_input, final_model, parent_ids, selected_ids, request

    def test_activation_runtime_subjects_equal_endpoint_included_subjects(self) -> None:
        study = self._activation_study()
        configuration = self._activation_configuration((SCALE_ID,))
        provider, catalog, _store, artifact_root = self._provider(
            study,
            configuration=configuration,
        )
        (
            endpoint,
            endpoint_input,
            _final_model,
            _parent_ids,
            _selected_ids,
            request,
        ) = self._activation_request_for_scale(
            provider,
            catalog,
            artifact_root,
            SCALE_ID,
            "endpoint-cohort",
        )

        self.assertEqual(len(endpoint.subject_ids), 12)
        self.assertEqual(endpoint_input.readiness_status, "ready")
        self.assertEqual(len(endpoint_input.included_subject_ids), 11)
        self.assertEqual(
            request.subject_ids,
            endpoint_input.included_subject_ids,
        )
        self.assertEqual(
            {source.subject_id for source in request.sources},
            set(endpoint_input.included_subject_ids),
        )
        self.assertTrue(
            all(subject_id.startswith("participant-") for subject_id in request.subject_ids)
        )
        self.assertEqual(
            tuple(exclusion.reason_code for exclusion in endpoint_input.exclusions),
            ("no_reference_frequency_group",),
        )

    def test_activation_sources_use_frequency_and_expand_dynamic_groups(self) -> None:
        study = self._activation_study()
        configuration = self._activation_configuration((SCALE_ID,))
        provider, catalog, artifact_store, artifact_root = self._provider(
            study,
            configuration=configuration,
        )
        (
            _endpoint,
            endpoint_input,
            _final_model,
            _parent_ids,
            _selected_ids,
            request,
        ) = self._activation_request_for_scale(
            provider,
            catalog,
            artifact_root,
            SCALE_ID,
            "dynamic-groups",
        )

        group_counts = Counter(
            (
                source.subject_id,
                source.side,
                source.frequency_group_id,
                source.delivery_mode,
            )
            for source in request.sources
        )
        for subject_id in endpoint_input.included_subject_ids:
            for side in ("L", "R"):
                self.assertEqual(
                    group_counts[(subject_id, side, "reference-group", "continuous")],
                    2,
                )
                self.assertEqual(
                    group_counts[
                        (subject_id, side, "reference-alternating", "alternating")
                    ],
                    2,
                )
        self.assertEqual(len(request.sources), len(endpoint_input.included_subject_ids) * 8)
        self.assertFalse(
            any(
                source.frequency_group_id == "low-frequency-decoy"
                for source in request.sources
            )
        )

        sample_subject = provider._subjects[endpoint_input.included_subject_ids[0]]
        sample_program = next(
            program
            for program in sample_subject.programs
            if program.phase_id == "T2" and program.program_id == 1
        )
        selected_source_ids = {source.source_id for source in request.sources}
        selected_components = {
            source.component_id
            for source in sample_program.stimulation_sources
            if source.source_id in selected_source_ids
            and configuration.normative_fiber.frequency_classes.classify(
                source.frequency_hz
            )
            == "reference"
        }
        self.assertEqual(selected_components, {"target_stn", "target_snr"})

        primary_sources = tuple(
            source
            for source in request.sources
            if source.subject_id == endpoint_input.included_subject_ids[0]
            and source.frequency_group_id == "reference-group"
            and source.source_id == "reference-group-source"
        )
        self.assertEqual({source.side for source in primary_sources}, {"L", "R"})
        for canonical_source in primary_sources:
            geometry = artifact_store.materialize_document(
                canonical_source.geometry,
                expected_kind="oss_stimulation_geometry_recipe",
            )
            parameters_ref = next(
                artifact
                for artifact in canonical_source.input_artifacts
                if artifact.kind == "oss_stimulation_source_parameters"
            )
            locator_ref = next(
                artifact
                for artifact in canonical_source.input_artifacts
                if artifact.kind == "oss_stimulation_source_locator"
            )
            parameters = artifact_store.materialize_document(
                parameters_ref,
                expected_kind="oss_stimulation_source_parameters",
            )
            locator = artifact_store.materialize_document(
                locator_ref,
                expected_kind="oss_stimulation_source_locator",
            )
            self.assertEqual(geometry["contact_count"], 4)
            self.assertEqual(
                geometry["reconstruction_lead_id"],
                2 if canonical_source.side == "L" else 1,
            )
            self.assertEqual(
                geometry["template_segmask_uri"],
                (
                    REPOSITORY_ROOT
                    / "templates"
                    / "space"
                    / "MNI152NLin2009bAsym"
                    / "segmask.nii"
                ).as_uri(),
            )
            self.assertEqual(parameters["source_id"], canonical_source.source_id)
            self.assertEqual(
                parameters["contacts"],
                [
                    {"contact": "case", "polarity": "anode", "fraction": 1.0},
                    {"contact": 1, "polarity": "cathode", "fraction": 1.0},
                ],
            )
            self.assertEqual(
                locator["subject_dir_uri"],
                provider._subjects[canonical_source.subject_id].leaddbs_subject_dir.as_uri(),
            )
            if canonical_source.side == "L":
                self.assertEqual(
                    locator["transform_uri"],
                    self.inverse_transform.resolve().as_uri(),
                )
                self.assertEqual(
                    locator["transform_sha256"],
                    sha256_file(self.inverse_transform),
                )
                self.assertEqual(
                    canonical_source.transform_hash,
                    sha256_file(self.inverse_transform),
                )
            else:
                self.assertIsNone(locator["transform_uri"])
            self.assertNotIn("component_id", parameters)
            self.assertNotIn("source_label", parameters)

        relabeled_subjects = tuple(
            dataclasses.replace(
                subject,
                programs=tuple(
                    dataclasses.replace(
                        program,
                        stimulation_sources=tuple(
                            dataclasses.replace(
                                source,
                                component_id=(
                                    "target_stn"
                                    if source.component_id == "target_snr"
                                    else "target_snr"
                                ),
                                source_label=f"Relabeled {source.source_id}",
                            )
                            for source in program.stimulation_sources
                        ),
                    )
                    for program in subject.programs
                ),
            )
            for subject in study.subjects
        )
        relabeled_study = dataclasses.replace(study, subjects=relabeled_subjects)
        relabeled_provider, relabeled_catalog, _store, relabeled_artifact_root = self._provider(
            relabeled_study,
            configuration=configuration,
        )
        relabeled_request = self._activation_request_for_scale(
            relabeled_provider,
            relabeled_catalog,
            relabeled_artifact_root,
            SCALE_ID,
            "relabeled-components",
        )[-1]
        self.assertEqual(
            self._activation_source_signature(request),
            self._activation_source_signature(relabeled_request),
        )

    def test_activation_requires_explicit_inverse_coordinate_transform(self) -> None:
        self.inverse_transform.unlink()
        study = self._activation_study()
        configuration = self._activation_configuration((SCALE_ID,))
        provider, catalog, _artifact_store, artifact_root = self._provider(
            study,
            configuration=configuration,
        )

        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "requires the sibling InverseComposite.nii.gz",
        ):
            self._activation_request_for_scale(
                provider,
                catalog,
                artifact_root,
                SCALE_ID,
                "missing-inverse-transform",
            )

    def test_activation_identity_is_scale_neutral_and_final_axis_locked(self) -> None:
        study = self._activation_study()
        configuration = self._activation_configuration((SCALE_ID, SECOND_SCALE_ID))
        provider, catalog, _store, artifact_root = self._provider(
            study,
            configuration=configuration,
        )
        first = self._activation_request_for_scale(
            provider,
            catalog,
            artifact_root,
            SCALE_ID,
            "first-scale",
        )
        second = self._activation_request_for_scale(
            provider,
            catalog,
            artifact_root,
            SECOND_SCALE_ID,
            "second-scale",
        )
        first_endpoint, _, first_final, first_parent, first_selected, first_request = first
        second_endpoint, _, second_final, second_parent, second_selected, second_request = second

        self.assertNotEqual(first_endpoint.scale_label, second_endpoint.scale_label)
        self.assertNotEqual(first_final.endpoint.scale_id, second_final.endpoint.scale_id)
        np.testing.assert_array_equal(first_parent, second_parent)
        np.testing.assert_array_equal(first_selected, second_selected)
        self.assertLess(first_request.feature_ids.size, first_parent.size)
        self.assertEqual(first_request.feature_axis, first_final.valid_feature_axis.axis)
        self.assertEqual(second_request.feature_axis, second_final.valid_feature_axis.axis)
        self.assertEqual(first_request.feature_axis, second_request.feature_axis)
        np.testing.assert_array_equal(first_request.feature_ids, first_selected)
        np.testing.assert_array_equal(second_request.feature_ids, second_selected)
        self.assertEqual(
            self._activation_source_signature(first_request),
            self._activation_source_signature(second_request),
        )
        self.assertEqual(
            first_request.connectome_feature_hash,
            second_request.connectome_feature_hash,
        )
        self.assertEqual(first_request.settings, second_request.settings)
        self.assertEqual(
            first_request.settings.backend_version,
            OSS_SCIENTIFIC_BACKEND_VERSION,
        )

    def test_missing_addon_frequency_excludes_only_that_addon_endpoint(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=True)
        )
        reference_publisher = RunScopedArtifactPublisher(
            artifact_root / "reference-input",
            "reference-input-test",
            "1",
        )
        addon_publisher = RunScopedArtifactPublisher(
            artifact_root / "addon-input",
            "addon-input-test",
            "1",
        )
        reference = provider.publish_endpoint_input(
            self._endpoint(catalog, "reference_voxel").endpoint_id,
            reference_publisher,
        )
        addon = provider.publish_endpoint_input(
            self._endpoint(catalog, "addon_voxel").endpoint_id,
            addon_publisher,
        )
        self.assertEqual(reference.readiness_status, "ready")
        self.assertEqual(len(reference.included_subject_ids), 12)
        self.assertEqual(addon.readiness_status, "insufficient_subjects")
        self.assertEqual(len(addon.included_subject_ids), 11)
        self.assertEqual(
            tuple(item.reason_code for item in addon.exclusions),
            ("no_addon_frequency_group",),
        )

    def test_physical_exposure_is_prepared_once_and_reused_from_v2_cache(self) -> None:
        provider, catalog, artifact_store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            shared_cache=True,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        endpoint_input = provider.publish_endpoint_input(
            endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "shared-input",
                "shared-input",
                "1",
            ),
        )
        with mock.patch.object(
            provider,
            "_compute_binding_matrix",
            wraps=provider._compute_binding_matrix,
        ) as producer:
            first = provider.publish_prepared_exposure(
                endpoint_input,
                None,
                RunScopedArtifactPublisher(
                    artifact_root / "shared-first",
                    "shared-first",
                    "1",
                ),
            )
            second = provider.publish_prepared_exposure(
                endpoint_input,
                None,
                RunScopedArtifactPublisher(
                    artifact_root / "shared-second",
                    "shared-second",
                    "1",
                ),
            )
        self.assertEqual(producer.call_count, 1)
        self.assertIsInstance(first.exposure, IndexedArrayView)
        self.assertEqual(first.exposure, second.exposure)
        assert isinstance(first.exposure, IndexedArrayView)
        self.assertIn(
            "/shared_exposure_v2/voxel_exposures/",
            first.exposure.parent.uri,
        )
        self.assertIsNotNone(first.exposure.row_positions)
        assert first.exposure.row_positions is not None
        self.assertIn(
            "/shared_exposure_v2/prepared_artifacts/",
            first.exposure.row_positions.uri,
        )
        np.testing.assert_array_equal(
            _materialize(artifact_store, first.exposure),
            _materialize(artifact_store, second.exposure),
        )
        selected_indices = np.asarray(
            (0, first.feature_axis.count - 1),
            dtype=np.int64,
        )
        expected_selected = _materialize(
            artifact_store,
            first.exposure,
        )[:, selected_indices]
        final_model = self._direct_final(
            endpoint,
            first,
            artifact_root,
            selected_indices,
        )
        with mock.patch.object(
            artifact_store,
            "materialize_indexed_array_view",
            side_effect=AssertionError(
                "selected exposure must not materialize the complete view"
            ),
        ):
            selected_exposure, _selected_ids = provider.selected_exposure(
                final_model,
                first,
                RunScopedArtifactPublisher(
                    artifact_root / "shared-selected",
                    "shared-selected",
                    "1",
                ),
            )
        np.testing.assert_array_equal(
            _materialize(artifact_store, selected_exposure),
            expected_selected,
        )
        self.assertFalse(tuple((artifact_root / "shared-first").glob("*.npy")))
        self.assertFalse(tuple((artifact_root / "shared-second").glob("*.npy")))
        cache_entries = tuple(
            (self.root / "scientific-cache" / "shared_exposure_v2" / "voxel_exposures").glob(
                "*"
            )
        )
        self.assertEqual(len(cache_entries), 1)
        prepared_entries = tuple(
            (
                self.root
                / "scientific-cache"
                / "shared_exposure_v2"
                / "prepared_artifacts"
            ).glob("*")
        )
        self.assertEqual(len(prepared_entries), 2)

    def test_prepared_artifact_cache_reuses_identity_and_separates_axes(self) -> None:
        provider, _catalog, artifact_store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            shared_cache=True,
        )
        subject_axis = AxisRef("prepared-subjects", 2, canonical_hash(["s1", "s2"]))
        alias_subject_axis = AxisRef(
            "different-endpoint-subjects",
            subject_axis.count,
            subject_axis.sha256,
        )
        feature_axis = AxisRef("prepared-features", 3, canonical_hash([1, 2, 3]))
        changed_axis = AxisRef("prepared-features", 3, canonical_hash([1, 3, 2]))
        values = np.arange(6, dtype=np.float32).reshape(2, 3)
        arguments = {
            "domain": "direct_voxel",
            "filename": "exposure.npy",
            "value": values,
            "kind": "prepared_reference_exposure",
            "units": "V/m",
            "space": "right_canonical",
            "dependencies": (("primary_matrix", canonical_hash("primary")),),
        }
        first = provider._publish_prepared_array(
            publisher=RunScopedArtifactPublisher(
                artifact_root / "prepared-cache-first",
                "prepared-cache-first",
                "1",
            ),
            axes=(subject_axis, feature_axis),
            **arguments,
        )
        second = provider._publish_prepared_array(
            publisher=RunScopedArtifactPublisher(
                artifact_root / "prepared-cache-second",
                "prepared-cache-second",
                "1",
            ),
            axes=(subject_axis, feature_axis),
            **arguments,
        )
        endpoint_alias = provider._publish_prepared_array(
            publisher=RunScopedArtifactPublisher(
                artifact_root / "prepared-cache-endpoint-alias",
                "prepared-cache-endpoint-alias",
                "1",
            ),
            axes=(alias_subject_axis, feature_axis),
            **arguments,
        )
        separated = provider._publish_prepared_array(
            publisher=RunScopedArtifactPublisher(
                artifact_root / "prepared-cache-separated",
                "prepared-cache-separated",
                "1",
            ),
            axes=(subject_axis, changed_axis),
            **arguments,
        )
        cross_domain = provider._publish_prepared_array(
            publisher=RunScopedArtifactPublisher(
                artifact_root / "prepared-cache-cross-domain",
                "prepared-cache-cross-domain",
                "1",
            ),
            axes=(subject_axis, feature_axis),
            **{**arguments, "domain": "normative_fiber"},
        )
        self.assertEqual(first.uri, second.uri)
        self.assertEqual(first.uri, endpoint_alias.uri)
        self.assertEqual(
            endpoint_alias.axis_refs,
            (alias_subject_axis, feature_axis),
        )
        self.assertNotEqual(first.uri, separated.uri)
        self.assertNotEqual(first.uri, cross_domain.uri)
        np.testing.assert_array_equal(_materialize(artifact_store, first), values)
        parent = provider._temporary_matrix(
            "prepared-cache-hit-view",
            (3, 3),
            np.float32,
        )
        parent.array[:] = np.vstack(
            (values[0], np.full(3, -1.0, dtype=np.float32), values[1])
        )
        parent.array.flush()
        cache_hit_view = dataclasses.replace(
            parent,
            row_positions=np.asarray([0, 2], dtype=np.int64),
        )
        try:
            with mock.patch.object(
                type(cache_hit_view),
                "read_column_block",
                side_effect=AssertionError("cache hit must not read view payloads"),
            ):
                cache_hit = provider._publish_prepared_array(
                    publisher=RunScopedArtifactPublisher(
                        artifact_root / "prepared-cache-hit-view",
                        "prepared-cache-hit-view",
                        "1",
                    ),
                    axes=(subject_axis, feature_axis),
                    **{**arguments, "value": cache_hit_view},
                )
            self.assertEqual(first.uri, cache_hit.uri)
        finally:
            provider._release_temporary_matrix(cache_hit_view)
        for task_root in (
            "prepared-cache-first",
            "prepared-cache-second",
            "prepared-cache-endpoint-alias",
            "prepared-cache-separated",
            "prepared-cache-cross-domain",
            "prepared-cache-hit-view",
        ):
            self.assertFalse(tuple((artifact_root / task_root).glob("*.npy")))

        cached_path = Path(first.uri.removeprefix("file://"))
        np.save(cached_path, values + 1.0, allow_pickle=False)
        provider._scientific_cache = ContentAddressedCache(
            self.root / "scientific-cache"
        )
        with self.assertRaises(CacheCorruption):
            provider._publish_prepared_array(
                publisher=RunScopedArtifactPublisher(
                    artifact_root / "prepared-cache-corrupt",
                    "prepared-cache-corrupt",
                    "1",
                ),
                axes=(subject_axis, feature_axis),
                **arguments,
            )

    def test_different_endpoint_subject_subsets_reuse_one_physical_matrix(self) -> None:
        study = self._study(missing_addon_for_last_subject=False)
        provider, catalog, _artifact_store, _artifact_root = self._provider(
            study,
            shared_cache=True,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        feature_space = provider._direct_feature_space()
        binding = provider.configuration.direct_voxel.endpoint_pair.reference
        first_subjects = tuple(endpoint.subject_ids[:8])
        second_subjects = tuple(endpoint.subject_ids[2:11])
        with mock.patch.object(
            provider,
            "_compute_binding_matrix",
            wraps=provider._compute_binding_matrix,
        ) as producer, mock.patch.object(
            provider,
            "_bilateral_sampling_plan",
            wraps=provider._bilateral_sampling_plan,
        ) as sampling_plan, mock.patch.object(
            provider,
            "_sample_voxel_plan",
            wraps=provider._sample_voxel_plan,
        ) as sample_plan:
            first, first_missing = provider._matrix_for_binding(
                endpoint,
                first_subjects,
                binding,
                "reference",
                feature_space,
                allow_absent=False,
            )
            second, second_missing = provider._matrix_for_binding(
                endpoint,
                second_subjects,
                binding,
                "reference",
                feature_space,
                allow_absent=False,
            )
        try:
            self.assertEqual(producer.call_count, 1)
            self.assertEqual(sampling_plan.call_count, len(study.subjects))
            self.assertEqual(sample_plan.call_count, len(study.subjects))
            self.assertEqual(first_missing, ())
            self.assertEqual(second_missing, ())
            self.assertEqual(first.shape[0], len(first_subjects))
            self.assertEqual(second.shape[0], len(second_subjects))
            np.testing.assert_array_equal(
                first.materialize()[2:],
                second.materialize()[:6],
            )
        finally:
            provider._release_temporary_matrix(first)
            provider._release_temporary_matrix(second)

    def test_cache_backed_subject_and_feature_subsets_allocate_no_memmap(self) -> None:
        study = self._study(missing_addon_for_last_subject=False)
        provider, catalog, _artifact_store, _artifact_root = self._provider(
            study,
            shared_cache=True,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        feature_space = provider._direct_feature_space()
        binding = provider.configuration.direct_voxel.endpoint_pair.reference
        initial, _missing = provider._matrix_for_binding(
            endpoint,
            tuple(endpoint.subject_ids[:8]),
            binding,
            "reference",
            feature_space,
            allow_absent=False,
        )
        provider._release_temporary_matrix(initial)

        with mock.patch.object(
            provider,
            "_temporary_matrix",
            wraps=provider._temporary_matrix,
        ) as allocator:
            subject_view, _missing = provider._matrix_for_binding(
                endpoint,
                tuple(endpoint.subject_ids[2:11]),
                binding,
                "reference",
                feature_space,
                allow_absent=False,
            )
            feature_view = provider._subset_matrix(
                subject_view,
                np.asarray([0, 2], dtype=np.int64),
                "must-remain-logical",
            )
        try:
            self.assertEqual(allocator.call_count, 0)
            self.assertIsNotNone(feature_view.row_positions)
            self.assertIsNotNone(feature_view.column_positions)
            self.assertEqual(feature_view.shape, (9, 2))
            np.testing.assert_array_equal(
                feature_view.materialize(),
                subject_view.materialize()[:, [0, 2]],
            )
        finally:
            provider._release_temporary_matrix(feature_view)

    def test_fiber_overlap_views_preserve_inclusive_threshold(self) -> None:
        provider, _catalog, _artifact_store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            shared_cache=True,
        )
        reference_key = EndpointKey(
            "synthetic-study",
            SCALE_ID,
            "reference-binding",
            "reference_fiber",
            FORMAL_CONNECTOME_ID,
        )
        addon_key = EndpointKey(
            "synthetic-study",
            SCALE_ID,
            "addon-binding",
            "addon_fiber",
            FORMAL_CONNECTOME_ID,
        )
        selected_axis = AxisRef("selected-fibers", 1, canonical_hash([1]))
        source_artifact = RunScopedArtifactPublisher(
            artifact_root / "fiber-overlap-source",
            "fiber-overlap-source",
            "1",
        ).array(
            "weights.npy",
            np.ones(1, dtype=np.float64),
            kind="benefit_oriented_feature_weights",
            axes=(selected_axis,),
            units="coefficient",
            space=None,
        )
        source = SourceRecord(
            endpoint=reference_key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200.0,
            selected_coverage=1,
            adjacent_support=1,
            feature_axis=FeatureAxisRef(
                selected_axis,
                "selected_normative_fiber_full_fold_valid_union",
            ),
            artifacts=(source_artifact,),
        )
        dependency = ReferenceDependencyRecord(
            addon_endpoint=addon_key,
            matched_reference_endpoint_id=reference_key.identifier,
            dependency_status="ready",
            reference_record=source,
            delta_reference=None,
        )
        endpoint = mock.Mock(
            endpoint_id=addon_key.identifier,
            key=addon_key,
        )
        addon = provider._temporary_matrix("fiber-addon-view", (2, 4), np.float32)
        reference = provider._temporary_matrix(
            "fiber-reference-view",
            (2, 4),
            np.float32,
        )
        addon.array[:] = 80.0
        reference.array[:] = np.asarray(
            ([199.0, 200.0, 201.0, 0.0], [200.0, 199.0, 0.0, 250.0]),
            dtype=np.float32,
        )
        addon.array.flush()
        reference.array.flush()
        prepared, overlap = provider._prepare_fiber_overlap_views(
            endpoint=endpoint,
            addon=addon,
            reference=reference,
            reference_record=source,
            reference_dependency=dependency,
        )
        try:
            expected_overlap = reference.materialize() >= 200.0
            np.testing.assert_array_equal(overlap.materialize(), expected_overlap)
            np.testing.assert_array_equal(
                prepared.materialize(),
                np.where(expected_overlap, 0.0, 80.0).astype(np.float32),
            )
        finally:
            for matrix in (prepared, overlap, addon, reference):
                provider._release_temporary_matrix(matrix)

    def test_omega_max_is_the_exact_inclusive_minimum_grid_candidate_union(self) -> None:
        provider, _catalog, _artifact_store, _artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        source = dataclasses.replace(
            provider.configuration.normative_fiber.source,
            tau_values=(100.0, 200.0),
            coverage_values=(1, 2),
        )
        profile = dataclasses.replace(
            provider.configuration.normative_fiber,
            source=source,
        )
        parent = _FeatureSpace(
            AxisRef("parent-fibers", 5, "d" * 64),
            np.arange(1, 6, dtype=np.int64),
            None,
            None,
            self.root / "synthetic-parent.mat",
        )
        exposure = np.array(
            [
                [101.0, 101.0, 100.0, 250.0, 201.0],
                [101.0, 0.0, 100.0, 250.0, 101.0],
                [0.0, 0.0, 100.0, 250.0, 0.0],
                [0.0, 0.0, 100.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        omega, positions = provider._omega_max_feature_space(
            parent,
            exposure,
            ("s1", "s2", "s3", "s4"),
            profile,
        )
        self.assertIsNone(positions)
        resolved_positions = (
            np.arange(parent.axis.count, dtype=np.int64)
            if positions is None
            else positions
        )
        np.testing.assert_array_equal(resolved_positions, np.arange(5))
        np.testing.assert_array_equal(omega.ids, np.arange(1, 6))
        for tau in source.tau_values:
            for coverage in source.coverage_values:
                candidates = set(
                    np.flatnonzero(np.count_nonzero(exposure >= tau, axis=0) >= coverage)
                )
                self.assertTrue(
                    candidates.issubset(set(resolved_positions.tolist()))
                )

    def test_addon_fiber_axis_includes_locked_reference_valid_union(self) -> None:
        parent = _FeatureSpace(
            AxisRef("parent-fibers", 5, "d" * 64),
            np.arange(1, 6, dtype=np.int64),
            None,
            None,
            self.root / "synthetic-parent.mat",
        )
        primary = _FeatureSpace(
            AxisRef("primary-omega", 2, "e" * 64),
            np.array([1, 4], dtype=np.int64),
            None,
            None,
            parent.source_path,
        )
        reference_axis = AxisRef("reference-valid-union", 3, "f" * 64)
        augmented, positions = (
            StudyRuntimeInputProvider._augment_addon_fiber_feature_space(
                parent,
                primary,
                np.array([0, 3], dtype=np.int64),
                np.array([3, 4, 5], dtype=np.int64),
                reference_axis,
            )
        )
        assert positions is not None
        np.testing.assert_array_equal(positions, np.array([0, 2, 3, 4]))
        np.testing.assert_array_equal(augmented.ids, np.array([1, 3, 4, 5]))
        self.assertNotEqual(augmented.axis.sha256, primary.axis.sha256)

        second_reference_axis = AxisRef("second-reference-valid-union", 3, "a" * 64)
        rebound, _ = StudyRuntimeInputProvider._augment_addon_fiber_feature_space(
            parent,
            primary,
            np.array([0, 3], dtype=np.int64),
            np.array([3, 4, 5], dtype=np.int64),
            second_reference_axis,
        )
        self.assertNotEqual(rebound.axis.sha256, augmented.axis.sha256)

        with self.assertRaisesRegex(RuntimeInputProviderError, "outside the parent"):
            StudyRuntimeInputProvider._augment_addon_fiber_feature_space(
                parent,
                primary,
                np.array([0, 3], dtype=np.int64),
                np.array([3, 6], dtype=np.int64),
                AxisRef("invalid-reference-valid-union", 2, "b" * 64),
            )

    def test_reference_valid_union_ids_are_materialized_from_locked_artifact(self) -> None:
        provider, _catalog, _artifact_store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        selected_axis = AxisRef("reference-valid-union", 3, "c" * 64)
        selected_ids = np.array([2, 4, 5], dtype=np.int64)
        artifact = RunScopedArtifactPublisher(
            artifact_root / "reference-valid-union",
            "reference-valid-union",
            "1",
        ).array(
            "valid_union_ids.npy",
            selected_ids,
            kind="normative_fiber_valid_union_ids",
            axes=(selected_axis,),
            units=None,
            space="MNI152NLin2009bAsym",
        )
        reference_record = SourceRecord(
            endpoint=EndpointKey(
                "synthetic",
                SCALE_ID,
                "reference",
                "reference_fiber",
                FORMAL_CONNECTOME_ID,
            ),
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=100.0,
            selected_coverage=1,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(
                selected_axis,
                "selected_normative_fiber_full_fold_valid_union",
            ),
            artifacts=(artifact,),
        )
        locked = provider._reference_valid_union_ids(reference_record)
        assert locked is not None
        materialized_ids, materialized_axis = locked
        np.testing.assert_array_equal(materialized_ids, selected_ids)
        self.assertEqual(materialized_axis, selected_axis)

    def test_missing_reference_component_preserves_no_delta_cohort(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(
                missing_addon_for_last_subject=False,
                missing_addon_reference_for_last_subject=True,
            )
        )
        reference_endpoint = self._endpoint(catalog, "reference_voxel")
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        addon_input = provider.publish_endpoint_input(
            addon_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "missing-aux-input",
                "missing-aux-input",
                "1",
            ),
        )
        self.assertEqual(addon_input.readiness_status, "ready")
        self.assertEqual(len(addon_input.included_subject_ids), 12)
        prepared = provider.publish_prepared_exposure(
            addon_input,
            self._dependency(reference_endpoint, addon_endpoint, artifact_root),
            RunScopedArtifactPublisher(
                artifact_root / "missing-aux-exposure",
                "missing-aux-exposure",
                "1",
            ),
        )
        self.assertEqual(prepared.delta_reference_input_status, "input_failure")
        self.assertEqual(
            prepared.delta_reference_reason_code,
            "missing_addon_reference_component_exposure",
        )
        request = provider.observed_request(
            addon_input,
            prepared,
            branch="no_delta_reference",
        )
        self.assertEqual(request.subject_axis.count, 12)
        delta = self._valid_delta(addon_input.subject_axis, artifact_root)
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "prepared DeltaReferenceScore inputs",
        ):
            provider.observed_request(
                addon_input,
                prepared,
                branch="delta_reference_adjusted",
                delta_reference=delta,
            )

    def test_reference_dependency_must_match_exact_addon_endpoint(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        addon_input = provider.publish_endpoint_input(
            addon_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "dependency-input",
                "dependency-input",
                "1",
            ),
        )
        other_reference = EndpointKey(
            addon_endpoint.key.study_id,
            addon_endpoint.key.scale_id,
            "other-reference-binding",
            "reference_voxel",
        )
        other_addon = EndpointKey(
            addon_endpoint.key.study_id,
            addon_endpoint.key.scale_id,
            "other-addon-binding",
            "addon_voxel",
        )
        other_source = self._accepted_source(
            other_reference,
            RunScopedArtifactPublisher(
                artifact_root / "other-reference-source",
                "other-reference-source",
                "1",
            ),
        )
        dependency = ReferenceDependencyRecord(
            addon_endpoint=other_addon,
            matched_reference_endpoint_id=other_reference.identifier,
            dependency_status="ready",
            reference_record=other_source,
            delta_reference=None,
        )
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "different add-on endpoint",
        ):
            provider.publish_prepared_exposure(
                addon_input,
                dependency,
                RunScopedArtifactPublisher(
                    artifact_root / "dependency-exposure",
                    "dependency-exposure",
                    "1",
                ),
            )

    def test_fiber_peaks_are_reduced_per_hemisphere_before_average(self) -> None:
        study = self._study(missing_addon_for_last_subject=False)
        provider, catalog, _store, _artifact_root = self._provider(study)
        endpoint = self._endpoint(catalog, "reference_voxel")
        subject_id = endpoint.subject_ids[0]
        subject = next(item for item in study.subjects if item.subject_id == subject_id)
        left = _leaf(
            subject.leaddbs_subject_dir,
            "T2",
            1,
            "lead-L",
            "reference-group",
            "continuous",
        )
        right = _leaf(
            subject.leaddbs_subject_dir,
            "T2",
            1,
            "lead-R",
            "reference-group",
            "continuous",
        )
        left_data = np.zeros((4, 4, 2), dtype=np.float32)
        right_data = np.zeros((4, 4, 2), dtype=np.float32)
        left_data[2, 0, 0] = 10.0
        right_data[1, 0, 0] = 10.0
        _write_field_array(left, left_data, self.affine)
        _write_field_array(right, right_data, self.affine)
        connectome_path = self.root / "synthetic-connectome.h5"
        connectome_path.write_bytes(b"bounded-connectome-fixture")
        chunks = (
            _FiberChunk(
                fiber_ids=np.array([1], dtype=np.int64),
                points=np.array(
                    [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                    dtype=np.float32,
                ),
                point_offsets=np.array([0, 2], dtype=np.int64),
            ),
            _FiberChunk(
                fiber_ids=np.array([2], dtype=np.int64),
                points=np.array(
                    [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                    dtype=np.float32,
                ),
                point_offsets=np.array([0, 2], dtype=np.int64),
            ),
        )
        fake_connectome = _FakeConnectome(chunks)
        feature_space = _FeatureSpace(
            AxisRef("synthetic-fiber-axis", 2, "c" * 64),
            np.array([1, 2], dtype=np.int64),
            None,
            fake_connectome,
            connectome_path,
        )
        physical_subjects = tuple(endpoint.subject_ids[:2])
        with mock.patch.object(
            provider,
            "_fiber_sampling_plan",
            wraps=provider._fiber_sampling_plan,
        ) as sampling_plan, mock.patch.object(
            provider,
            "_sample_fiber_plan",
            wraps=provider._sample_fiber_plan,
        ) as sample_plan:
            temporary, missing = provider._matrix_for_binding(
                endpoint,
                physical_subjects,
                provider.configuration.direct_voxel.endpoint_pair.reference,
                "reference",
                feature_space,
                allow_absent=False,
            )
        try:
            self.assertIsInstance(temporary.array, np.memmap)
            self.assertEqual(missing, ())
            self.assertEqual(temporary.array.shape, (2, 2))
            np.testing.assert_allclose(temporary.array[0], 10.0)
            np.testing.assert_allclose(temporary.array[1], 250.0)
            self.assertEqual(fake_connectome.iteration_count, 1)
            self.assertEqual(sampling_plan.call_count, len(study.subjects))
            self.assertEqual(sample_plan.call_count, 2 * len(study.subjects))
        finally:
            provider._release_temporary_matrix(temporary)

    def test_explicit_transform_path_is_used_by_matlab_backend(self) -> None:
        self.assertEqual(MatlabLeftToCanonicalTransformer.TIMEOUT_SECONDS, 1800.0)
        source = self.root / "left-source.nii.gz"
        destination = self.root / "left-canonical.nii.gz"
        configured = self.root / "configured-forward-transform.nii.gz"
        _write_field(source, 1.0, self.affine)
        configured.write_bytes(b"configured-transform")
        process = mock.Mock()
        process.returncode = 0

        def communicate(*, timeout):
            self.assertEqual(timeout, MatlabLeftToCanonicalTransformer.TIMEOUT_SECONDS)
            shutil.copyfile(source, destination)
            return "", ""

        process.communicate.side_effect = communicate

        transformer = MatlabLeftToCanonicalTransformer(
            repository_root=REPOSITORY_ROOT,
        )
        with mock.patch(
            "dual_frequency.runtime.input_provider.subprocess.Popen",
            return_value=process,
        ) as popen:
            transformed = transformer.transform(source, destination, configured)
        self.assertEqual(transformed, destination.resolve())
        self.assertEqual(popen.call_count, 1)
        script = popen.call_args.args[0][2]
        self.assertIn(str(configured.resolve()), script)
        self.assertIn("ea_ants_apply_transforms", script)
        self.assertNotIn("ea_flip_lr_nonlinear", script)

    def test_matlab_transform_timeout_terminates_its_process_group(self) -> None:
        source = self.root / "timeout-left-source.nii.gz"
        destination = self.root / "timeout-left-canonical.nii.gz"
        configured = self.root / "timeout-transform.nii.gz"
        _write_field(source, 1.0, self.affine)
        configured.write_bytes(b"configured-transform")
        process = mock.Mock()
        process.pid = 12345
        process.communicate.side_effect = (
            subprocess.TimeoutExpired("matlab", 300.0),
            ("", ""),
        )
        transformer = MatlabLeftToCanonicalTransformer(
            repository_root=REPOSITORY_ROOT,
        )
        with mock.patch(
            "dual_frequency.runtime.input_provider.subprocess.Popen",
            return_value=process,
        ), mock.patch(
            "dual_frequency.runtime.input_provider.os.killpg"
        ) as killpg:
            with self.assertRaisesRegex(RuntimeInputProviderError, "timed out"):
                transformer.transform(source, destination, configured)
        killpg.assert_called_once_with(12345, signal.SIGTERM)

    def test_left_transform_cache_is_atomic_under_concurrent_reuse(self) -> None:
        transformer = _CopyTransformer(delay_seconds=0.05)
        provider, catalog, _store, _artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            transformer=transformer,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        subject = provider._subjects[endpoint.subject_ids[0]]
        source = _leaf(
            subject.leaddbs_subject_dir,
            "T2",
            1,
            "lead-L",
            "reference-group",
            "continuous",
        )
        with ThreadPoolExecutor(max_workers=4) as executor:
            paths = tuple(executor.map(lambda _value: provider._canonical_left_path(source), range(8)))
        self.assertEqual(transformer.calls, 1)
        self.assertEqual(len(set(paths)), 1)
        self.assertTrue(paths[0].is_file())
        _write_field(paths[0], 999.0, self.affine)
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "cache metadata does not match",
        ):
            provider._canonical_left_path(source)

    def test_sampler_cache_evicts_decoded_fields_by_bytes(self) -> None:
        provider, _catalog, _store, _artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            sampler_cache_bytes=128,
        )
        first = self.root / "sampler-first.nii.gz"
        second = self.root / "sampler-second.nii.gz"
        _write_field(first, 1.0, self.affine)
        _write_field(second, 2.0, self.affine)
        provider._sampler(first)
        provider._sampler(second)
        self.assertEqual(tuple(provider._samplers), (second.resolve(),))
        self.assertLessEqual(provider._sampler_bytes, 128)

    def test_shared_transformed_nifti_is_structurally_validated_once_per_process(self) -> None:
        provider, catalog, _store, _artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            transformer=_CopyTransformer(),
            shared_cache=True,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        subject = provider._subjects[endpoint.subject_ids[0]]
        source = _leaf(
            subject.leaddbs_subject_dir,
            "T2",
            1,
            "lead-L",
            "reference-group",
            "continuous",
        )
        with mock.patch.object(
            provider,
            "_validate_nifti",
            wraps=provider._validate_nifti,
        ) as validate:
            first = provider._canonical_left_path(source)
            calls_after_first_lookup = validate.call_count
            second = provider._canonical_left_path(source)
        self.assertEqual(first, second)
        self.assertGreater(calls_after_first_lookup, 0)
        self.assertEqual(validate.call_count, calls_after_first_lookup)

    def test_left_transform_is_shared_across_provider_process_roots(self) -> None:
        study = self._study(missing_addon_for_last_subject=False)
        first_transformer = _CopyTransformer()
        provider, catalog, artifact_store, _artifact_root = self._provider(
            study,
            transformer=first_transformer,
            shared_cache=True,
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        subject = provider._subjects[endpoint.subject_ids[0]]
        source = _leaf(
            subject.leaddbs_subject_dir,
            "T2",
            1,
            "lead-L",
            "reference-group",
            "continuous",
        )
        first = provider._canonical_left_path(source)
        second_transformer = _CopyTransformer()
        second_provider = StudyRuntimeInputProvider(
            study,
            provider.configuration,
            catalog,
            work_root=self.root / "second-provider-work",
            artifact_store=artifact_store,
            scientific_cache=ContentAddressedCache(self.root / "scientific-cache"),
            left_transformer=second_transformer,
        )
        second = second_provider._canonical_left_path(source)
        self.assertEqual(first_transformer.calls, 1)
        self.assertEqual(second_transformer.calls, 0)
        self.assertEqual(first, second)
        self.assertIn("shared_exposure_v2/transformed_efields", first.as_posix())

    def test_formal_request_requires_exact_endpoint_and_selected_axis(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        reference_endpoint = self._endpoint(catalog, "reference_voxel")
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        endpoint_input = provider.publish_endpoint_input(
            reference_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "formal-input",
                "formal-input",
                "1",
            ),
        )
        prepared = provider.publish_prepared_exposure(
            endpoint_input,
            None,
            RunScopedArtifactPublisher(
                artifact_root / "formal-prepared",
                "formal-prepared",
                "1",
            ),
        )
        final_model = self._direct_final(
            reference_endpoint,
            prepared,
            artifact_root,
            np.array([0, 1], dtype=np.int64),
        )
        request = provider.formal_request(
            final_model,
            endpoint_input,
            prepared,
            RunScopedArtifactPublisher(
                artifact_root / "formal-request",
                "formal-request",
                "1",
            ),
            resampling_kind="permutation",
        )
        self.assertEqual(request.final_model, final_model)
        self.assertEqual(request.feature_axis, final_model.valid_feature_axis.axis)

        source = final_model.selected_source
        assert source is not None
        in_sample_publisher = RunScopedArtifactPublisher(
            artifact_root / "in-sample-request",
            "in-sample-request",
            "1",
        )
        count = endpoint_input.subject_axis.count
        source_with_predictions = dataclasses.replace(
            source,
            artifacts=(
                *source.artifacts,
                in_sample_publisher.array(
                    "loocv_predictions.npy",
                    np.arange(count, dtype=np.float64),
                    kind="loocv_model_predictions",
                    axes=(endpoint_input.subject_axis,),
                    units="score",
                    space=None,
                ),
                in_sample_publisher.array(
                    "loocv_baseline_predictions.npy",
                    np.zeros(count, dtype=np.float64),
                    kind="loocv_baseline_predictions",
                    axes=(endpoint_input.subject_axis,),
                    units="score",
                    space=None,
                ),
            ),
        )
        in_sample_final = dataclasses.replace(
            final_model,
            selected_source=source_with_predictions,
        )
        loocv_summary = in_sample_publisher.document(
            "formal_permutation_summary.json",
            {
                "schema_version": "formal_permutation_summary_v1",
                "observed": {},
            },
            kind="formal_permutation_summary",
        )
        in_sample_request = provider.in_sample_request(
            in_sample_final,
            endpoint_input,
            prepared,
            FormalResult(
                final_model_id=in_sample_final.identifier,
                resampling_kind="permutation",
                technical_status="completed",
                artifacts=(loocv_summary,),
            ),
        )
        self.assertEqual(in_sample_request.feature_axis, prepared.feature_axis)
        self.assertEqual(in_sample_request.final_model, in_sample_final)

        mismatched_input = dataclasses.replace(
            endpoint_input,
            endpoint=addon_endpoint.key,
        )
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "must match",
        ):
            provider.formal_request(
                final_model,
                mismatched_input,
                prepared,
                RunScopedArtifactPublisher(
                    artifact_root / "formal-mismatch",
                    "formal-mismatch",
                    "1",
                ),
                resampling_kind="permutation",
            )

        wrong_axis_final = self._direct_final(
            reference_endpoint,
            prepared,
            artifact_root,
            np.array([0, 1], dtype=np.int64),
            axis_hash="d" * 64,
        )
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "locked final-axis identity",
        ):
            provider.selected_exposure(
                wrong_axis_final,
                prepared,
                RunScopedArtifactPublisher(
                    artifact_root / "wrong-axis",
                    "wrong-axis",
                    "1",
                ),
            )

    def test_selected_direct_indices_reject_noninteger_duplicate_and_out_of_bounds(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        endpoint = self._endpoint(catalog, "reference_voxel")
        endpoint_input = provider.publish_endpoint_input(
            endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "selected-input",
                "selected-input",
                "1",
            ),
        )
        prepared = provider.publish_prepared_exposure(
            endpoint_input,
            None,
            RunScopedArtifactPublisher(
                artifact_root / "selected-prepared",
                "selected-prepared",
                "1",
            ),
        )
        cases = (
            (np.array([0.0, 1.0], dtype=np.float64), "one-dimensional int64"),
            (np.array([0, 0], dtype=np.int64), "ordered, unique, and in bounds"),
            (
                np.array([prepared.feature_axis.count], dtype=np.int64),
                "ordered, unique, and in bounds",
            ),
        )
        for case_index, (indices, message) in enumerate(cases):
            with self.subTest(indices=indices):
                final_model = self._direct_final(
                    endpoint,
                    prepared,
                    artifact_root,
                    indices,
                )
                with self.assertRaisesRegex(RuntimeInputProviderError, message):
                    provider.selected_exposure(
                        final_model,
                        prepared,
                        RunScopedArtifactPublisher(
                            artifact_root / f"invalid-selected-{case_index}",
                            f"invalid-selected-{case_index}",
                            "1",
                        ),
                    )

    def test_adjusted_formal_cannot_override_prepared_delta_failure(self) -> None:
        provider, catalog, _store, artifact_root = self._provider(
            self._study(
                missing_addon_for_last_subject=False,
                missing_addon_reference_for_last_subject=True,
            )
        )
        reference_endpoint = self._endpoint(catalog, "reference_voxel")
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        endpoint_input = provider.publish_endpoint_input(
            addon_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "adjusted-formal-input",
                "adjusted-formal-input",
                "1",
            ),
        )
        prepared = provider.publish_prepared_exposure(
            endpoint_input,
            self._dependency(reference_endpoint, addon_endpoint, artifact_root),
            RunScopedArtifactPublisher(
                artifact_root / "adjusted-formal-prepared",
                "adjusted-formal-prepared",
                "1",
            ),
        )
        final_model = self._direct_final(
            addon_endpoint,
            prepared,
            artifact_root,
            np.array([0, 1], dtype=np.int64),
            branch="delta_reference_adjusted",
        )
        delta = self._valid_delta(endpoint_input.subject_axis, artifact_root)
        with self.assertRaisesRegex(
            RuntimeInputProviderError,
            "prepared DeltaReferenceScore inputs",
        ):
            provider.formal_request(
                final_model,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(
                    artifact_root / "adjusted-formal-request",
                    "adjusted-formal-request",
                    "1",
                ),
                resampling_kind="bootstrap",
                delta_reference=delta,
            )

    def test_selected_fiber_ids_require_int64_unique_parent_order(self) -> None:
        provider, _catalog, _store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False)
        )
        endpoint = EndpointKey(
            "synthetic-study",
            SCALE_ID,
            "synthetic-fiber-binding",
            "reference_fiber",
            "synthetic-connectome",
        )
        subject_axis = AxisRef("fiber-subjects", 2, "1" * 64)
        parent_axis = AxisRef("fiber-parent", 3, "2" * 64)
        prepared_publisher = RunScopedArtifactPublisher(
            artifact_root / "fiber-prepared",
            "fiber-prepared",
            "1",
        )
        exposure = prepared_publisher.array(
            "exposure.npy",
            np.ones((2, 3), dtype=np.float32),
            kind="prepared_reference_exposure",
            axes=(subject_axis, parent_axis),
            units="V/m",
            space="MNI152NLin2009bAsym",
        )
        feature_ids = prepared_publisher.array(
            "feature_ids.npy",
            np.array([1, 2, 3], dtype=np.int64),
            kind="canonical_connectome_fiber_ids",
            axes=(parent_axis,),
            units=None,
            space="MNI152NLin2009bAsym",
        )
        prepared = PreparedExposureRecord(
            endpoint=endpoint,
            subject_axis=subject_axis,
            feature_axis=parent_axis,
            exposure=exposure,
            feature_ids=feature_ids,
            delta_reference_input_status="not_applicable",
            delta_reference_reason_code="not_applicable",
            auxiliary_readiness=None,
            reference_condition_exposure=None,
            addon_reference_component_exposure=None,
            reference_overlap_mask=None,
            total_exposure=None,
        )
        cases = (
            (np.array([1.0, 2.0], dtype=np.float64), "one-dimensional int64"),
            (np.array([1, 1], dtype=np.int64), "unique and preserve parent order"),
        )
        for case_index, (selected_ids, message) in enumerate(cases):
            with self.subTest(selected_ids=selected_ids):
                selected_axis = AxisRef(
                    f"fiber-selected-{case_index}",
                    2,
                    str(case_index + 3) * 64,
                )
                selected_artifact = RunScopedArtifactPublisher(
                    artifact_root / f"fiber-source-{case_index}",
                    f"fiber-source-{case_index}",
                    "1",
                ).array(
                    "valid_union_ids.npy",
                    selected_ids,
                    kind="normative_fiber_valid_union_ids",
                    axes=(selected_axis,),
                    units="fiber_id",
                    space=None,
                )
                source = SourceRecord(
                    endpoint=endpoint,
                    input_status="valid",
                    source_status="pre_specified_accepted",
                    prediction_status="error_predictive",
                    threshold_source="pre_specified",
                    selected_tau=800.0,
                    selected_coverage=5,
                    adjacent_support=2,
                    feature_axis=FeatureAxisRef(
                        selected_axis,
                        "selected_normative_fiber_full_fold_valid_union",
                    ),
                    artifacts=(selected_artifact,),
                )
                final_model = FinalModelRecord(
                    endpoint=endpoint,
                    final_status="final_model_realized",
                    realization_role="primary",
                    final_key=FinalModelKey(
                        endpoint.identifier,
                        "reference",
                        800.0,
                        5,
                        "loocv_linear",
                    ),
                    selected_source=source,
                    selected_branch=None,
                )
                with self.assertRaisesRegex(RuntimeInputProviderError, message):
                    provider.selected_exposure(
                        final_model,
                        prepared,
                        RunScopedArtifactPublisher(
                            artifact_root / f"fiber-selected-output-{case_index}",
                            f"fiber-selected-output-{case_index}",
                            "1",
                        ),
                    )

    def test_continuous_and_alternating_paths_feed_locked_overlap_preparation(self) -> None:
        provider, catalog, artifact_store, artifact_root = self._provider(
            self._study(missing_addon_for_last_subject=False),
            shared_cache=True,
        )
        reference_endpoint = self._endpoint(catalog, "reference_voxel")
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        reference_publisher = RunScopedArtifactPublisher(
            artifact_root / "reference-input",
            "reference-input",
            "1",
        )
        reference_input = provider.publish_endpoint_input(
            reference_endpoint.endpoint_id,
            reference_publisher,
        )
        reference_prepared = provider.publish_prepared_exposure(
            reference_input,
            None,
            RunScopedArtifactPublisher(
                artifact_root / "reference-exposure",
                "reference-exposure",
                "1",
            ),
        )
        selected_axis = AxisRef("selected", 1, "b" * 64)
        selected_artifact = RunScopedArtifactPublisher(
            artifact_root / "reference-source",
            "reference-source",
            "1",
        ).array(
            "weights.npy",
            np.ones(1, dtype=np.float64),
            kind="benefit_oriented_feature_weights",
            axes=(selected_axis,),
            units="coefficient",
            space=None,
        )
        source = SourceRecord(
            endpoint=reference_endpoint.key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200.0,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(selected_axis, "synthetic-selected-feature"),
            artifacts=(selected_artifact,),
        )
        dependency = ReferenceDependencyRecord(
            addon_endpoint=addon_endpoint.key,
            matched_reference_endpoint_id=reference_endpoint.endpoint_id,
            dependency_status="ready",
            reference_record=source,
            delta_reference=None,
        )
        addon_input = provider.publish_endpoint_input(
            addon_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "addon-input",
                "addon-input",
                "1",
            ),
        )
        addon_prepared = provider.publish_prepared_exposure(
            addon_input,
            dependency,
            RunScopedArtifactPublisher(
                artifact_root / "addon-exposure",
                "addon-exposure",
                "1",
            ),
        )
        self.assertEqual(reference_prepared.feature_axis, addon_prepared.feature_axis)
        self.assertEqual(addon_prepared.delta_reference_input_status, "ready")
        self.assertIsInstance(addon_prepared.total_exposure, IndexedArrayView)
        self.assertIsInstance(
            addon_prepared.reference_condition_exposure,
            IndexedArrayView,
        )
        self.assertIsInstance(
            addon_prepared.addon_reference_component_exposure,
            IndexedArrayView,
        )
        exposure = _materialize(artifact_store, addon_prepared.exposure)
        raw_addon = _materialize(artifact_store, addon_prepared.total_exposure)
        overlap = _materialize(artifact_store, addon_prepared.reference_overlap_mask)
        self.assertTrue(np.allclose(exposure, 0.0))
        self.assertTrue(np.allclose(raw_addon, 80.0))
        self.assertTrue(np.all(overlap))
        self.assertFalse(tuple((artifact_root / "addon-exposure").glob("*.npy")))
        addon_final = self._direct_final(
            addon_endpoint,
            addon_prepared,
            artifact_root,
            np.array([0, 1], dtype=np.int64),
            branch="no_delta_reference",
        )
        selected_exposure, _selected_ids = provider.selected_exposure(
            addon_final,
            addon_prepared,
            RunScopedArtifactPublisher(
                artifact_root / "addon-selected-exposure",
                "addon-selected-exposure",
                "1",
            ),
        )
        self.assertEqual(selected_exposure.axis_refs[1], addon_final.valid_feature_axis.axis)
        manifest = json.loads(
            (artifact_root / "addon-exposure" / "input_hash_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        consumed_paths = {item["path"] for item in manifest["files"]}
        first_subject = provider._subjects[addon_input.included_subject_ids[0]]
        expected_right = _leaf(
            first_subject.leaddbs_subject_dir,
            "T3",
            2,
            "lead-R",
            "addon-group",
            "alternating",
        ).resolve()
        self.assertIn(str(expected_right), consumed_paths)
        self.assertIn(
            str(Path(provider.study.spatial.left_to_right_transform).resolve()),
            consumed_paths,
        )


if __name__ == "__main__":
    unittest.main()
