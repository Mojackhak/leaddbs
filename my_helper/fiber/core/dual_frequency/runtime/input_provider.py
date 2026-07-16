"""Validated study inputs and canonical exposure preparation for the runtime."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterator, Protocol, runtime_checkable

import fcntl

import nibabel as nib
import numpy as np
from scipy.ndimage import map_coordinates

from seed_target_connectivity.connectome import LeadDBSHDF5Connectome, open_connectome
from ..backends.activation.ossdbs import OSSRowBatchArtifact, OSSScientificSettings
from ..backends.interaction.reference_overlap import prepare_reference_overlap
from ..backends.normative_fiber.addon import prepare_addon_fiber_exposure
from ..backends.protocols import ArtifactPublisher
from ..cache import ArtifactStore, CacheFileMetadata, ContentAddressedCache
from ..cache.identity import ScientificCacheKey, sha256_file
from ..catalog import EndpointRecord
from ..config import (
    DirectVoxelModelProfile,
    NormativeFiberModelProfile,
    ResolvedWorkflow,
)
from ..config.models import EndpointBinding
from ..contracts import (
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FormalRequest,
    HardComputabilityLimits,
    NormativeFiberScoreSettings,
    ObservedRequest,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SourceGrid,
    SourceRecord,
    StudyBaseRecord,
    SubjectExclusionRecord,
)
from ..contracts.identity import canonical_hash
from ..contracts.records import ACCEPTED_SOURCE_STATUSES, FinalModelRecord
from ..contracts.study_base import ProgramRecord, SubjectRecord
from .activation_provider import (
    CanonicalStimulationSource,
    OSSActivationRuntimeRequest,
)
from .oss_toolchain import LeadDBSOSSProducerToolchain, oss_backend_version


_ACTIVE_INPUT_HASHES: ContextVar[dict[str, str] | None] = ContextVar(
    "dual_frequency_active_input_hashes",
    default=None,
)
_ACTIVE_SHARED_EXPOSURES: ContextVar[list[dict[str, str]] | None] = ContextVar(
    "dual_frequency_active_shared_exposures",
    default=None,
)


class RuntimeInputProviderError(RuntimeError):
    """Raised when validated runtime inputs cannot form an exact scientific input."""


@runtime_checkable
class LeftToCanonicalTransformer(Protocol):
    """Transform one left-hemisphere canonical-space image to the canonical side."""

    def transform(
        self,
        source: Path,
        destination: Path,
        configured_transform: Path,
    ) -> Path: ...


class MatlabLeftToCanonicalTransformer:
    """Run the Lead-DBS nonlinear left-to-right helper with explicit paths."""

    def __init__(
        self,
        *,
        matlab_command: str = "matlab",
        repository_root: Path | None = None,
    ) -> None:
        command = str(matlab_command).strip()
        if not command:
            raise RuntimeInputProviderError("matlab_command must be nonempty")
        self._command = command
        self._repository_root = (
            Path(repository_root).expanduser().resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[5]
        )

    @staticmethod
    def _matlab_string(value: Path) -> str:
        return str(value).replace("'", "''")

    def transform(
        self,
        source: Path,
        destination: Path,
        configured_transform: Path,
    ) -> Path:
        source = Path(source).resolve()
        destination = Path(destination).resolve()
        configured_transform = Path(configured_transform).resolve()
        if not source.is_file():
            raise RuntimeInputProviderError(f"left E-field is missing: {source}")
        if not configured_transform.is_file():
            raise RuntimeInputProviderError(
                f"configured left-to-canonical transform is missing: {configured_transform}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reproduce ea_flip_lr_nonlinear while binding the exact configured
        # transform instead of allowing Lead-DBS to rediscover one by space.
        script = (
            f"addpath(genpath('{self._matlab_string(self._repository_root)}'));"
            f"src='{self._matlab_string(source)}';"
            f"dst='{self._matlab_string(destination)}';"
            f"xfm='{self._matlab_string(configured_transform)}';"
            "ea_flip_lr(src,dst);"
            "ea_ants_apply_transforms(struct(),{dst},{dst},0,dst,xfm,4);"
        )
        executable = shutil.which(self._command) or self._command
        result = subprocess.run(
            (executable, "-batch", script),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not destination.is_file():
            detail = (result.stderr or result.stdout or "unknown MATLAB failure").strip()
            raise RuntimeInputProviderError(
                f"left-to-canonical transform failed for {source.name}: {detail}"
            )
        return destination


@dataclass(frozen=True)
class FrequencyGroupArtifact:
    """One exact group-level E-field leaf selected only by frequency class."""

    subject_id: str
    phase_id: str
    program_id: int
    electrode_id: str
    hemisphere: str
    frequency_group_id: str
    delivery_mode: str
    frequency_class: str
    efield_path: Path


@dataclass(frozen=True)
class GroupResolution:
    """Exact group-level artifacts for one subject, binding, and frequency class."""

    groups: tuple[FrequencyGroupArtifact, ...]
    reason_code: str | None

    @property
    def ready(self) -> bool:
        return self.reason_code is None

    @property
    def hemispheres(self) -> frozenset[str]:
        return frozenset(item.hemisphere for item in self.groups)


@dataclass(frozen=True)
class JitterTranslationContext:
    """Deterministic isotropic translations for one spatial-jitter replicate."""

    replicate_index: int
    replicate_seed: int
    translation_sigma_mm: float

    def __post_init__(self) -> None:
        if type(self.replicate_index) is not int or self.replicate_index < 0:
            raise RuntimeInputProviderError("jitter replicate_index must be nonnegative")
        if type(self.replicate_seed) is not int or self.replicate_seed < 0:
            raise RuntimeInputProviderError("jitter replicate_seed must be nonnegative")
        sigma = float(self.translation_sigma_mm)
        if not math.isfinite(sigma) or sigma <= 0.0:
            raise RuntimeInputProviderError(
                "jitter translation_sigma_mm must be finite and positive"
            )
        object.__setattr__(self, "translation_sigma_mm", sigma)

    def vector(
        self,
        *,
        binding_id: str,
        frequency_class: str,
        subject_id: str,
        hemisphere: str,
    ) -> np.ndarray:
        payload = canonical_hash(
            {
                "binding_id": str(binding_id),
                "frequency_class": str(frequency_class),
                "hemisphere": str(hemisphere),
                "replicate_index": self.replicate_index,
                "replicate_seed": self.replicate_seed,
                "subject_id": str(subject_id),
            }
        )
        entropy = int(payload[:16], 16)
        generator = np.random.default_rng(np.random.SeedSequence([self.replicate_seed, entropy]))
        vector = generator.normal(0.0, self.translation_sigma_mm, size=3)
        return np.asarray(vector, dtype=np.float64)


@dataclass(frozen=True)
class _FeatureSpace:
    axis: AxisRef
    ids: np.ndarray
    coordinates: np.ndarray | None
    connectome: LeadDBSHDF5Connectome | None
    source_path: Path


@dataclass(frozen=True)
class _FileDigest:
    signature: tuple[int, int, int]
    sha256: str


@dataclass(frozen=True)
class _TemporaryMatrix:
    array: np.memmap
    path: Path
    delete_on_release: bool = True


class _NiftiSampler:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        try:
            image = nib.load(str(self.path))
            data = np.asarray(image.dataobj, dtype=np.float32)
        except Exception as exc:
            raise RuntimeInputProviderError(f"failed to load E-field {self.path}: {exc}") from exc
        if data.ndim != 3 or not np.all(np.isfinite(data)):
            raise RuntimeInputProviderError(
                f"E-field must be a finite three-dimensional image: {self.path}"
            )
        self._data = data
        self._inverse_affine = np.linalg.inv(image.affine)

    def sample(
        self,
        coordinates_mm: np.ndarray,
        *,
        translation_mm: np.ndarray | None = None,
    ) -> np.ndarray:
        coordinates = np.asarray(coordinates_mm, dtype=np.float64)
        if coordinates.ndim != 2 or coordinates.shape[1] != 3:
            raise RuntimeInputProviderError("sampling coordinates must have shape (n, 3)")
        if translation_mm is not None:
            translation = np.asarray(translation_mm, dtype=np.float64)
            if translation.shape != (3,) or not np.all(np.isfinite(translation)):
                raise RuntimeInputProviderError(
                    "jitter translation must contain three finite millimeter values"
                )
            coordinates = coordinates - translation[None, :]
        voxels = nib.affines.apply_affine(self._inverse_affine, coordinates)
        inside = np.ones(coordinates.shape[0], dtype=bool)
        for axis, size in enumerate(self._data.shape):
            inside &= (voxels[:, axis] >= 0.0) & (voxels[:, axis] <= size - 1)
        values = np.zeros(coordinates.shape[0], dtype=np.float32)
        if np.any(inside):
            values[inside] = map_coordinates(
                self._data,
                [voxels[inside, 0], voxels[inside, 1], voxels[inside, 2]],
                order=1,
                mode="constant",
                cval=0.0,
                prefilter=False,
            ).astype(np.float32)
        if not np.all(np.isfinite(values)):
            raise RuntimeInputProviderError(f"sampled E-field is nonfinite: {self.path}")
        np.maximum(values, 0.0, out=values)
        return values


@runtime_checkable
class RuntimeInputProvider(Protocol):
    """Endpoint-scoped provider used by production and synthetic registries."""

    def endpoint(self, endpoint_id: str) -> EndpointRecord: ...

    def publish_endpoint_input(
        self,
        endpoint_id: str,
        publisher: ArtifactPublisher,
    ) -> EndpointInputRecord: ...

    def publish_prepared_exposure(
        self,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        publisher: ArtifactPublisher,
    ) -> PreparedExposureRecord: ...

    def observed_request(
        self,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        *,
        branch: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> ObservedRequest: ...


class StudyRuntimeInputProvider:
    """Resolve typed endpoint inputs directly from validated study/config records."""

    def __init__(
        self,
        study: StudyBaseRecord,
        configuration: ResolvedWorkflow,
        catalog: tuple[EndpointRecord, ...],
        *,
        work_root: Path,
        artifact_store: ArtifactStore | None = None,
        scientific_cache: ContentAddressedCache | None = None,
        left_transformer: LeftToCanonicalTransformer | None = None,
        fiber_chunk_size: int = 65_536,
    ) -> None:
        if not isinstance(study, StudyBaseRecord):
            raise TypeError("study must be a StudyBaseRecord")
        if not isinstance(configuration, ResolvedWorkflow):
            raise TypeError("configuration must be a ResolvedWorkflow")
        if not catalog or not all(isinstance(item, EndpointRecord) for item in catalog):
            raise RuntimeInputProviderError("catalog must contain EndpointRecord values")
        if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore or None")
        if scientific_cache is not None and not isinstance(
            scientific_cache,
            ContentAddressedCache,
        ):
            raise TypeError("scientific_cache must be a ContentAddressedCache or None")
        if type(fiber_chunk_size) is not int or fiber_chunk_size < 1:
            raise RuntimeInputProviderError("fiber_chunk_size must be a positive integer")
        endpoints = {item.endpoint_id: item for item in catalog}
        if len(endpoints) != len(catalog):
            raise RuntimeInputProviderError("catalog endpoint IDs must be unique")
        subjects = {item.subject_id: item for item in study.subjects}
        if len(subjects) != len(study.subjects):
            raise RuntimeInputProviderError("study subject IDs must be unique")

        self.study = study
        self.configuration = configuration
        self.catalog = tuple(catalog)
        self._endpoints = endpoints
        self._subjects = subjects
        self._artifact_store = artifact_store
        self._scientific_cache = scientific_cache
        self._work_root = Path(work_root).expanduser().resolve()
        self._work_root.mkdir(parents=True, exist_ok=True)
        self._left_transformer = left_transformer or MatlabLeftToCanonicalTransformer()
        self._fiber_chunk_size = fiber_chunk_size
        self._lock = RLock()
        self._samplers: dict[Path, tuple[_FileDigest, _NiftiSampler]] = {}
        self._hashes: dict[Path, _FileDigest] = {}
        self._feature_spaces: dict[tuple[str, str], _FeatureSpace] = {}
        self._shared_preparation_locks: dict[str, RLock] = {}

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int, int]:
        try:
            stat = Path(path).stat()
        except OSError as exc:
            raise RuntimeInputProviderError(f"required input file is unavailable: {path}") from exc
        if not Path(path).is_file():
            raise RuntimeInputProviderError(f"required input is not a file: {path}")
        return (int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))

    @contextmanager
    def _capture_input_hashes(self) -> Iterator[dict[str, str]]:
        captured: dict[str, str] = {}
        token = _ACTIVE_INPUT_HASHES.set(captured)
        shared_token = _ACTIVE_SHARED_EXPOSURES.set([])
        try:
            yield captured
        finally:
            _ACTIVE_INPUT_HASHES.reset(token)
            _ACTIVE_SHARED_EXPOSURES.reset(shared_token)

    def _path_hash(
        self,
        path: Path,
        *,
        force: bool = False,
        record: bool = True,
    ) -> str:
        resolved = Path(path).expanduser().resolve()
        signature_before = self._file_signature(resolved)
        with self._lock:
            cached = self._hashes.get(resolved)
        if force or cached is None or cached.signature != signature_before:
            digest = sha256_file(resolved)
            signature_after = self._file_signature(resolved)
            if signature_after != signature_before:
                raise RuntimeInputProviderError(
                    f"input changed while it was being hashed: {resolved}"
                )
            cached = _FileDigest(signature_after, digest)
            with self._lock:
                self._hashes[resolved] = cached
        captured = _ACTIVE_INPUT_HASHES.get()
        if record and captured is not None:
            captured[str(resolved)] = cached.sha256
        return cached.sha256

    def _temporary_matrix(
        self,
        label: str,
        shape: tuple[int, int],
        dtype: np.dtype | type[np.generic],
    ) -> _TemporaryMatrix:
        root = self._work_root / "prepared-memmaps"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f".{label}.{uuid.uuid4().hex}.npy"
        try:
            value = np.lib.format.open_memmap(
                path,
                mode="w+",
                dtype=np.dtype(dtype),
                shape=shape,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeInputProviderError(
                f"failed to allocate bounded preparation matrix {label!r}"
            ) from exc
        return _TemporaryMatrix(value, path)

    @staticmethod
    def _release_temporary_matrix(value: _TemporaryMatrix) -> None:
        try:
            value.array.flush()
            mapping = getattr(value.array, "_mmap", None)
            if mapping is not None:
                mapping.close()
        finally:
            if value.delete_on_release:
                value.path.unlink(missing_ok=True)

    @staticmethod
    def _validate_nifti(path: Path) -> None:
        try:
            image = nib.load(str(path))
        except Exception as exc:
            raise RuntimeInputProviderError(
                f"cached transformed E-field is unreadable: {path}"
            ) from exc
        if len(image.shape) != 3 or any(int(value) < 1 for value in image.shape):
            raise RuntimeInputProviderError(
                f"cached transformed E-field must be finite and three-dimensional: {path}"
            )
        try:
            for index in range(int(image.shape[2])):
                plane = np.asarray(image.dataobj[:, :, index])
                if not np.all(np.isfinite(plane)):
                    raise RuntimeInputProviderError(
                        f"cached transformed E-field is nonfinite: {path}"
                    )
        except RuntimeInputProviderError:
            raise
        except Exception as exc:
            raise RuntimeInputProviderError(
                f"cached transformed E-field cannot be read: {path}"
            ) from exc

    def endpoint(self, endpoint_id: str) -> EndpointRecord:
        try:
            return self._endpoints[str(endpoint_id)]
        except KeyError as exc:
            raise RuntimeInputProviderError(f"unknown endpoint ID {endpoint_id!r}") from exc

    def _profile(
        self,
        endpoint: EndpointRecord,
    ) -> DirectVoxelModelProfile | NormativeFiberModelProfile:
        return (
            self.configuration.direct_voxel
            if endpoint.key.model_family.endswith("voxel")
            else self.configuration.normative_fiber
        )

    def _bindings(
        self,
        endpoint: EndpointRecord,
    ) -> tuple[EndpointBinding, EndpointBinding]:
        pair = self._profile(endpoint).endpoint_pair
        if endpoint.key.model_family.startswith("reference_"):
            return pair.baseline, pair.reference
        return pair.reference, pair.addon

    @staticmethod
    def _program(subject: SubjectRecord, binding: EndpointBinding) -> ProgramRecord | None:
        matches = tuple(
            item
            for item in subject.programs
            if item.phase_id == binding.phase_id and item.program_id == binding.program_id
        )
        if len(matches) > 1:
            raise RuntimeInputProviderError(
                f"duplicate program binding for {subject.subject_id}/{binding.identifier}"
            )
        return matches[0] if matches else None

    @staticmethod
    def _clinical_value(program: ProgramRecord | None, scale_id: str) -> float | None:
        if program is None:
            return None
        matches = tuple(item for item in program.observations if item.scale_id == scale_id)
        if len(matches) != 1:
            raise RuntimeInputProviderError(
                f"program {program.identifier!r} does not contain one {scale_id!r} observation"
            )
        observation = matches[0]
        if observation.status != "observed" or observation.value is None:
            return None
        value = float(observation.value)
        return value if math.isfinite(value) else None

    def _group_leaf(
        self,
        subject: SubjectRecord,
        source: object,
        delivery_mode: str,
    ) -> Path:
        phase_id = str(getattr(source, "phase_id"))
        program_id = int(getattr(source, "program_id"))
        electrode_id = str(getattr(source, "electrode_id"))
        group_id = str(getattr(source, "frequency_group_id"))
        root = (
            subject.leaddbs_subject_dir
            / "stimulations"
            / self.study.spatial.canonical_space
            / f"phase-{phase_id}"
            / f"program-{program_id}"
            / f"electrode-{electrode_id}"
            / f"frequency-group-{group_id}"
        )
        if delivery_mode == "continuous":
            return root / "delivery-continuous" / "joint" / "efield.nii.gz"
        if delivery_mode == "alternating":
            return (
                root
                / "delivery-alternating"
                / "derived"
                / "group-peak"
                / "efield.nii.gz"
            )
        raise RuntimeInputProviderError(f"unsupported delivery mode {delivery_mode!r}")

    def _resolve_groups(
        self,
        endpoint: EndpointRecord,
        subject: SubjectRecord,
        binding: EndpointBinding,
        frequency_class: str,
        *,
        require_bilateral: bool,
    ) -> GroupResolution:
        program = self._program(subject, binding)
        if program is None:
            return GroupResolution((), "missing_bound_program")
        profile = self._profile(endpoint)
        electrode_sides = {item.electrode_id: item.hemisphere for item in subject.electrodes}
        grouped: dict[tuple[str, str], list[object]] = {}
        for source in program.stimulation_sources:
            grouped.setdefault(
                (source.electrode_id, source.frequency_group_id),
                [],
            ).append(source)
        selected: list[FrequencyGroupArtifact] = []
        for (electrode_id, group_id), sources in sorted(grouped.items()):
            frequencies = {float(getattr(item, "frequency_hz")) for item in sources}
            modes = {str(getattr(item, "delivery_mode")) for item in sources}
            if len(frequencies) != 1 or len(modes) != 1:
                raise RuntimeInputProviderError(
                    f"frequency group {subject.subject_id}/{binding.identifier}/"
                    f"{electrode_id}/{group_id} is internally inconsistent"
                )
            resolved_class = profile.frequency_classes.classify(next(iter(frequencies)))
            if resolved_class != frequency_class:
                continue
            try:
                hemisphere = electrode_sides[electrode_id]
            except KeyError as exc:
                raise RuntimeInputProviderError(
                    f"frequency group references unknown electrode {electrode_id!r}"
                ) from exc
            if hemisphere not in {"L", "R"}:
                raise RuntimeInputProviderError(
                    f"unsupported electrode hemisphere {hemisphere!r}"
                )
            delivery_mode = next(iter(modes))
            path = self._group_leaf(subject, sources[0], delivery_mode)
            selected.append(
                FrequencyGroupArtifact(
                    subject_id=subject.subject_id,
                    phase_id=binding.phase_id,
                    program_id=binding.program_id,
                    electrode_id=electrode_id,
                    hemisphere=hemisphere,
                    frequency_group_id=group_id,
                    delivery_mode=delivery_mode,
                    frequency_class=frequency_class,
                    efield_path=path,
                )
            )
        if not selected:
            return GroupResolution((), f"no_{frequency_class}_frequency_group")
        if any(not item.efield_path.is_file() for item in selected):
            return GroupResolution(tuple(selected), "missing_efield_artifact")
        hemispheres = {item.hemisphere for item in selected}
        if require_bilateral and hemispheres != {"L", "R"}:
            return GroupResolution(tuple(selected), "missing_required_hemisphere")
        return GroupResolution(tuple(selected), None)

    def _oss_backend_version(self) -> str:
        repository_root = Path(__file__).resolve().parents[5]
        return oss_backend_version(
            repository_root,
            file_hasher=self._path_hash,
        )

    def oss_producer_toolchain(self) -> LeadDBSOSSProducerToolchain:
        """Return the project-neutral producer used only for authorized OSS misses."""

        if self._artifact_store is None:
            raise RuntimeInputProviderError(
                "artifact_store is required to construct the OSS producer toolchain"
            )
        repository_root = Path(__file__).resolve().parents[5]
        formal = self.configuration.normative_fiber.formal_connectome
        return LeadDBSOSSProducerToolchain(
            artifact_store=self._artifact_store,
            connectome_path=formal.path,
            connectome_label=formal.label,
            work_root=self._work_root / "oss-producer",
            repository_root=repository_root,
            environment_file=(
                repository_root
                / "classes"
                / "conda_utils"
                / "environments"
                / "OSS-DBSv2.yml"
            ),
            subject_roots={
                subject.subject_id: subject.leaddbs_subject_dir
                for subject in self.study.subjects
            },
        )

    @staticmethod
    def _side_local_contact(
        subject: SubjectRecord,
        electrode_id: str,
        contact: int | str,
    ) -> int | str:
        if isinstance(contact, str):
            if contact.strip().lower() != "case":
                raise RuntimeInputProviderError(
                    "stimulation contact must be a global integer or case"
                )
            return "case"
        if isinstance(contact, bool):
            raise RuntimeInputProviderError("stimulation contact cannot be boolean")
        electrode_by_id = {item.electrode_id: item for item in subject.electrodes}
        offset = 0
        for candidate_id in subject.electrode_order:
            try:
                candidate = electrode_by_id[candidate_id]
            except KeyError as exc:
                raise RuntimeInputProviderError(
                    "subject electrode order differs from its electrode definitions"
                ) from exc
            if candidate_id == electrode_id:
                local_zero_based = int(contact) - offset
                if not 0 <= local_zero_based < candidate.contact_count:
                    raise RuntimeInputProviderError(
                        "global stimulation contact is outside its declared electrode"
                    )
                return local_zero_based + 1
            offset += candidate.contact_count
        raise RuntimeInputProviderError(
            f"electrode {electrode_id!r} is absent from subject electrode order"
        )

    @staticmethod
    def _oss_coordinate_transform_path(forward_image_transform: Path) -> Path:
        """Resolve the explicit Lead-DBS inverse field used for point coordinates."""

        forward = Path(forward_image_transform).expanduser().resolve()
        if forward.name != "Composite.nii.gz":
            raise RuntimeInputProviderError(
                "OSS coordinate mapping requires a Lead-DBS Composite.nii.gz "
                "image transform"
            )
        inverse = forward.with_name("InverseComposite.nii.gz")
        if not inverse.is_file():
            raise RuntimeInputProviderError(
                "OSS coordinate mapping requires the sibling "
                f"InverseComposite.nii.gz: {inverse}"
            )
        return inverse.resolve()

    def _activation_sources(
        self,
        endpoint: EndpointRecord,
        endpoint_input: EndpointInputRecord,
        publisher: ArtifactPublisher,
    ) -> tuple[CanonicalStimulationSource, ...]:
        if endpoint_input.readiness_status != "ready":
            raise RuntimeInputProviderError(
                "activation sources require a ready endpoint input"
            )
        _baseline_binding, outcome_binding = self._bindings(endpoint)
        frequency_class = (
            "reference"
            if endpoint.key.model_family.startswith("reference_")
            else "addon"
        )
        profile = self._profile(endpoint)
        repository_root = Path(__file__).resolve().parents[5]
        template_segmask = (
            repository_root
            / "templates"
            / "space"
            / self.study.spatial.canonical_space
            / "segmask.nii"
        ).resolve()
        template_segmask_hash = self._path_hash(template_segmask)
        coordinate_transform_path = self._oss_coordinate_transform_path(
            self.study.spatial.left_to_right_transform
        )
        coordinate_transform_hash = self._path_hash(coordinate_transform_path)
        identity_transform_hash = canonical_hash(
            {"contract": "dual_frequency_oss_identity_transform_v1"}
        )
        output: list[CanonicalStimulationSource] = []

        for subject_id in endpoint_input.included_subject_ids:
            subject = self._subjects[subject_id]
            program = self._program(subject, outcome_binding)
            if program is None:
                raise RuntimeInputProviderError(
                    "activation endpoint lost its validated bound program"
                )
            electrode_by_id = {item.electrode_id: item for item in subject.electrodes}
            grouped: dict[tuple[str, str], list[object]] = {}
            for source in program.stimulation_sources:
                grouped.setdefault(
                    (source.electrode_id, source.frequency_group_id),
                    [],
                ).append(source)

            selected_sides: set[str] = set()
            for (electrode_id, group_id), group_sources in sorted(grouped.items()):
                frequencies = {float(item.frequency_hz) for item in group_sources}
                delivery_modes = {str(item.delivery_mode) for item in group_sources}
                if len(frequencies) != 1 or len(delivery_modes) != 1:
                    raise RuntimeInputProviderError(
                        "activation frequency group is internally inconsistent"
                    )
                if profile.frequency_classes.classify(next(iter(frequencies))) != frequency_class:
                    continue
                try:
                    electrode = electrode_by_id[electrode_id]
                except KeyError as exc:
                    raise RuntimeInputProviderError(
                        f"activation group references unknown electrode {electrode_id!r}"
                    ) from exc
                side = str(electrode.hemisphere).upper()
                if side not in {"L", "R"}:
                    raise RuntimeInputProviderError(
                        f"activation group has unsupported hemisphere {side!r}"
                    )
                selected_sides.add(side)
                reconstruction_hash = self._path_hash(subject.electrode_reconstruction)
                canonicalization = "left_to_right" if side == "L" else "identity"
                source_transform_hash = (
                    coordinate_transform_hash if side == "L" else identity_transform_hash
                )

                for source in sorted(group_sources, key=lambda item: str(item.source_id)):
                    source_identity = canonical_hash(
                        {
                            "subject_id": subject_id,
                            "binding_id": outcome_binding.identifier,
                            "electrode_id": electrode_id,
                            "frequency_group_id": group_id,
                            "source_id": source.source_id,
                        },
                        length=24,
                    )
                    geometry = publisher.document(
                        f"oss_geometry_{source_identity}.json",
                        {
                            "schema_version": "dual_frequency_oss_geometry_recipe_v1",
                            "electrode_model": electrode.electrode_model,
                            "reconstruction_lead_id": electrode.reconstruction_lead_id,
                            "contact_count": electrode.contact_count,
                            "reconstruction_sha256": reconstruction_hash,
                            "template_segmask_uri": template_segmask.as_uri(),
                            "template_segmask_sha256": template_segmask_hash,
                        },
                        kind="oss_stimulation_geometry_recipe",
                    )
                    source_parameters = publisher.document(
                        f"oss_source_parameters_{source_identity}.json",
                        {
                            "schema_version": "dual_frequency_oss_source_parameters_v1",
                            "source_id": source.source_id,
                            "control_mode": source.control_mode,
                            "amplitude": float(source.amplitude),
                            "pulse_width_us": float(source.pulse_width_us),
                            "frequency_hz": float(source.frequency_hz),
                            "contacts": [
                                {
                                    "contact": self._side_local_contact(
                                        subject,
                                        electrode_id,
                                        contact.contact,
                                    ),
                                    "polarity": contact.polarity,
                                    "fraction": float(contact.fraction),
                                }
                                for contact in source.contacts
                            ],
                        },
                        kind="oss_stimulation_source_parameters",
                    )
                    locator = publisher.document(
                        f"oss_source_locator_{source_identity}.json",
                        {
                            "schema_version": "dual_frequency_oss_source_locator_v1",
                            "subject_id": subject_id,
                            "phase_id": outcome_binding.phase_id,
                            "program_id": outcome_binding.program_id,
                            "electrode_id": electrode_id,
                            "frequency_group_id": group_id,
                            "source_id": source.source_id,
                            "subject_dir_uri": subject.leaddbs_subject_dir.as_uri(),
                            "reconstruction_uri": subject.electrode_reconstruction.as_uri(),
                            "reconstruction_sha256": reconstruction_hash,
                            "transform_uri": (
                                coordinate_transform_path.as_uri()
                                if side == "L"
                                else None
                            ),
                            "transform_sha256": source_transform_hash,
                            "canonicalization": canonicalization,
                        },
                        kind="oss_stimulation_source_locator",
                    )
                    output.append(
                        CanonicalStimulationSource(
                            subject_id=subject_id,
                            side=side,
                            frequency_group_id=group_id,
                            delivery_mode=next(iter(delivery_modes)),
                            source_id=str(source.source_id),
                            geometry=geometry,
                            canonicalization=canonicalization,
                            stimulation_hash=source_parameters.sha256,
                            component_frequency_hash=canonical_hash(
                                {"frequency_hz": float(source.frequency_hz)}
                            ),
                            transform_hash=source_transform_hash,
                            input_artifacts=(source_parameters, locator),
                        )
                    )
            if selected_sides != {"L", "R"}:
                raise RuntimeInputProviderError(
                    "activation requires exact left and right frequency-class groups"
                )
        return tuple(output)

    def publish_endpoint_input(
        self,
        endpoint_id: str,
        publisher: ArtifactPublisher,
    ) -> EndpointInputRecord:
        endpoint = self.endpoint(endpoint_id)
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        baseline_binding, outcome_binding = self._bindings(endpoint)
        primary_class = (
            "reference"
            if endpoint.key.model_family.startswith("reference_")
            else "addon"
        )
        included: list[str] = []
        exclusions: list[SubjectExclusionRecord] = []
        baseline_values: list[float] = []
        outcome_values: list[float] = []
        for subject_id in endpoint.subject_ids:
            subject = self._subjects[subject_id]
            baseline = self._clinical_value(
                self._program(subject, baseline_binding),
                endpoint.key.scale_id,
            )
            outcome = self._clinical_value(
                self._program(subject, outcome_binding),
                endpoint.key.scale_id,
            )
            reason: str | None = None
            if baseline is None:
                reason = "missing_baseline_observation"
            elif outcome is None:
                reason = "missing_outcome_observation"
            else:
                primary = self._resolve_groups(
                    endpoint,
                    subject,
                    outcome_binding,
                    primary_class,
                    require_bilateral=True,
                )
                reason = primary.reason_code
            if reason is not None:
                exclusions.append(SubjectExclusionRecord(subject_id, reason))
                continue
            included.append(subject_id)
            baseline_values.append(float(baseline))
            outcome_values.append(float(outcome))

        readiness = (
            "ready"
            if len(included) >= endpoint.minimum_subjects
            else "insufficient_subjects"
        )
        subject_axis: AxisRef | None = None
        baseline_artifact: ArtifactRef | None = None
        outcome_artifact: ArtifactRef | None = None
        if included:
            subject_axis = AxisRef(
                axis_id=f"{endpoint.endpoint_id}:subjects",
                count=len(included),
                sha256=canonical_hash({"ordered_subject_ids": included}),
            )
            scale = next(item for item in self.study.scales if item.scale_id == endpoint.key.scale_id)
            baseline_artifact = publisher.array(
                "baseline.npy",
                np.asarray(baseline_values, dtype=np.float64),
                kind="endpoint_baseline",
                axes=(subject_axis,),
                units=scale.unit,
                space=None,
            )
            outcome_artifact = publisher.array(
                "outcome.npy",
                np.asarray(outcome_values, dtype=np.float64),
                kind="endpoint_outcome",
                axes=(subject_axis,),
                units=scale.unit,
                space=None,
            )
        return EndpointInputRecord(
            endpoint=endpoint.key,
            readiness_status=readiness,
            candidate_subject_ids=endpoint.subject_ids,
            included_subject_ids=tuple(included),
            exclusions=tuple(exclusions),
            minimum_subjects=endpoint.minimum_subjects,
            subject_axis=subject_axis,
            baseline=baseline_artifact,
            outcome=outcome_artifact,
        )

    def _canonical_left_path(self, source: Path) -> Path:
        source = Path(source).resolve()
        transform = Path(self.study.spatial.left_to_right_transform).resolve()
        source_hash = self._path_hash(source)
        transform_hash = self._path_hash(transform)
        identity = canonical_hash(
            {
                "source_sha256": source_hash,
                "transform_sha256": transform_hash,
                "interpolation": 4,
            }
        )
        destination = self._work_root / "left_to_canonical" / f"{identity}.nii.gz"
        metadata_path = destination.with_name(f"{destination.name}.cache.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock_path = destination.with_name(f".{destination.name}.lock")
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise RuntimeInputProviderError(
                f"cannot open transformed E-field cache lock: {lock_path}"
            ) from exc
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.tmp.nii.gz"
        )
        metadata_temporary = metadata_path.with_name(
            f".{metadata_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if destination.is_file():
                self._validate_nifti(destination)
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeInputProviderError(
                        f"transformed E-field cache metadata is missing or invalid: {metadata_path}"
                    ) from exc
                output_hash = self._path_hash(destination)
                expected_metadata = {
                    "schema_version": "dual_frequency_left_transform_cache_v1",
                    "source_sha256": source_hash,
                    "transform_sha256": transform_hash,
                    "interpolation": 4,
                    "output_sha256": output_hash,
                }
                if metadata != expected_metadata:
                    raise RuntimeInputProviderError(
                        f"transformed E-field cache metadata does not match its inputs: {destination}"
                    )
                return destination
            transformed = self._left_transformer.transform(source, temporary, transform)
            transformed = Path(transformed).resolve()
            if transformed != temporary.resolve():
                raise RuntimeInputProviderError(
                    "left-to-canonical transformer returned an unexpected destination"
                )
            self._validate_nifti(temporary)
            if self._path_hash(source, force=True) != source_hash:
                raise RuntimeInputProviderError(
                    f"left E-field changed during transformation: {source}"
                )
            if self._path_hash(transform, force=True) != transform_hash:
                raise RuntimeInputProviderError(
                    f"configured transform changed during transformation: {transform}"
                )
            output_hash = self._path_hash(temporary, force=True, record=False)
            metadata_temporary.write_text(
                json.dumps(
                    {
                        "schema_version": "dual_frequency_left_transform_cache_v1",
                        "source_sha256": source_hash,
                        "transform_sha256": transform_hash,
                        "interpolation": 4,
                        "output_sha256": output_hash,
                    },
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
            os.replace(metadata_temporary, metadata_path)
            if self._path_hash(destination, force=True) != output_hash:
                raise RuntimeInputProviderError(
                    f"transformed E-field changed during atomic publication: {destination}"
                )
            return destination
        finally:
            temporary.unlink(missing_ok=True)
            metadata_temporary.unlink(missing_ok=True)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _sampler(self, path: Path) -> _NiftiSampler:
        resolved = Path(path).resolve()
        digest = self._path_hash(resolved)
        signature = self._file_signature(resolved)
        with self._lock:
            cached = self._samplers.get(resolved)
            if cached is not None and cached[0] == _FileDigest(signature, digest):
                return cached[1]
        sampler = _NiftiSampler(resolved)
        if self._file_signature(resolved) != signature:
            raise RuntimeInputProviderError(
                f"E-field changed while it was being loaded: {resolved}"
            )
        if self._path_hash(resolved, force=True) != digest:
            raise RuntimeInputProviderError(
                f"E-field content changed while it was being loaded: {resolved}"
            )
        with self._lock:
            self._samplers[resolved] = (_FileDigest(signature, digest), sampler)
        return sampler

    def _sample_group_resolution(
        self,
        resolution: GroupResolution,
        coordinates: np.ndarray,
        *,
        allow_absent: bool,
        translation_by_side: dict[str, np.ndarray] | None = None,
    ) -> tuple[np.ndarray, str | None]:
        count = int(coordinates.shape[0])
        if not resolution.groups:
            if allow_absent:
                return np.zeros(count, dtype=np.float32), resolution.reason_code
            raise RuntimeInputProviderError(
                f"required frequency group is unavailable: {resolution.reason_code}"
            )
        if resolution.reason_code == "missing_efield_artifact":
            if allow_absent:
                return np.zeros(count, dtype=np.float32), resolution.reason_code
            raise RuntimeInputProviderError("declared frequency-group E-field is missing")
        side_values: dict[str, np.ndarray] = {}
        for side in ("L", "R"):
            paths = tuple(item.efield_path for item in resolution.groups if item.hemisphere == side)
            if not paths:
                if allow_absent:
                    side_values[side] = np.zeros(count, dtype=np.float32)
                    continue
                raise RuntimeInputProviderError(f"required {side} hemisphere exposure is missing")
            values = []
            for path in paths:
                sample_path = self._canonical_left_path(path) if side == "L" else path
                values.append(
                    self._sampler(sample_path).sample(
                        coordinates,
                        translation_mm=(
                            None
                            if translation_by_side is None
                            else translation_by_side[side]
                        ),
                    )
                )
            side_values[side] = np.maximum.reduce(values)
        bilateral = (side_values["L"] + side_values["R"]) / np.float32(2.0)
        if not np.all(np.isfinite(bilateral)) or np.any(bilateral < 0.0):
            raise RuntimeInputProviderError("bilateral exposure is not finite and nonnegative")
        return bilateral.astype(np.float32, copy=False), resolution.reason_code

    def _sample_fiber_group_resolution(
        self,
        resolution: GroupResolution,
        points: np.ndarray,
        point_offsets: np.ndarray,
        *,
        allow_absent: bool,
        translation_by_side: dict[str, np.ndarray] | None = None,
    ) -> tuple[np.ndarray, str | None]:
        offsets = np.asarray(point_offsets)
        if offsets.ndim != 1 or offsets.size < 2:
            raise RuntimeInputProviderError("fiber point offsets must be one-dimensional")
        if not np.issubdtype(offsets.dtype, np.integer):
            raise RuntimeInputProviderError("fiber point offsets must contain integers")
        offsets = np.asarray(offsets, dtype=np.int64)
        point_count = int(np.asarray(points).shape[0])
        if offsets[0] != 0 or offsets[-1] != point_count or np.any(np.diff(offsets) <= 0):
            raise RuntimeInputProviderError(
                "fiber point offsets must partition the complete point array"
            )
        fiber_count = int(offsets.size - 1)
        if not resolution.groups:
            if allow_absent:
                return np.zeros(fiber_count, dtype=np.float32), resolution.reason_code
            raise RuntimeInputProviderError(
                f"required frequency group is unavailable: {resolution.reason_code}"
            )
        if resolution.reason_code == "missing_efield_artifact":
            if allow_absent:
                return np.zeros(fiber_count, dtype=np.float32), resolution.reason_code
            raise RuntimeInputProviderError("declared frequency-group E-field is missing")

        side_peaks: dict[str, np.ndarray] = {}
        for side in ("L", "R"):
            paths = tuple(
                item.efield_path
                for item in resolution.groups
                if item.hemisphere == side
            )
            if not paths:
                if allow_absent:
                    side_peaks[side] = np.zeros(fiber_count, dtype=np.float32)
                    continue
                raise RuntimeInputProviderError(
                    f"required {side} hemisphere exposure is missing"
                )
            group_peaks: list[np.ndarray] = []
            for path in paths:
                sample_path = self._canonical_left_path(path) if side == "L" else path
                point_values = self._sampler(sample_path).sample(
                    points,
                    translation_mm=(
                        None
                        if translation_by_side is None
                        else translation_by_side[side]
                    ),
                )
                group_peaks.append(
                    np.maximum.reduceat(point_values, offsets[:-1]).astype(
                        np.float32,
                        copy=False,
                    )
                )
            side_peaks[side] = np.maximum.reduce(group_peaks)
        bilateral = (side_peaks["L"] + side_peaks["R"]) / np.float32(2.0)
        if not np.all(np.isfinite(bilateral)) or np.any(bilateral < 0.0):
            raise RuntimeInputProviderError(
                "bilateral fiber exposure is not finite and nonnegative"
            )
        return bilateral.astype(np.float32, copy=False), resolution.reason_code

    def _direct_feature_space(self) -> _FeatureSpace:
        key = ("voxel", self.study.spatial.brainmask_id)
        brainmask_hash = self._path_hash(self.study.spatial.brainmask_path)
        with self._lock:
            cached = self._feature_spaces.get(key)
            if cached is not None:
                return cached
            image = nib.load(str(self.study.spatial.brainmask_path))
            mask = np.asarray(image.dataobj) > 0
            indices = np.argwhere(mask)
            coordinates = nib.affines.apply_affine(image.affine, indices)
            canonical = self.study.spatial.canonical_hemisphere
            if canonical == "R":
                keep = coordinates[:, 0] > 0.0
            elif canonical == "L":
                keep = coordinates[:, 0] < 0.0
            else:
                raise RuntimeInputProviderError(
                    f"unsupported canonical hemisphere {canonical!r}"
                )
            indices = indices[keep]
            coordinates = np.asarray(coordinates[keep], dtype=np.float32)
            if not indices.size:
                raise RuntimeInputProviderError("canonical brainmask hemisphere is empty")
            ids = np.ravel_multi_index(
                (indices[:, 0], indices[:, 1], indices[:, 2]),
                image.shape,
            ).astype(np.int64)
            id_hash = hashlib.sha256(np.ascontiguousarray(ids, dtype="<i8").tobytes()).hexdigest()
            axis = AxisRef(
                axis_id=(
                    f"{self.study.study_id}:brainmask-{self.study.spatial.brainmask_id}:"
                    f"hemisphere-{canonical}"
                ),
                count=int(ids.size),
                sha256=canonical_hash(
                    {
                        "brainmask_sha256": brainmask_hash,
                        "canonical_hemisphere": canonical,
                        "ordered_voxel_ids_sha256": id_hash,
                    }
                ),
            )
            ids.flags.writeable = False
            coordinates.flags.writeable = False
            if self._path_hash(self.study.spatial.brainmask_path, force=True) != brainmask_hash:
                raise RuntimeInputProviderError(
                    "brainmask changed while its canonical feature axis was built"
                )
            value = _FeatureSpace(
                axis,
                ids,
                coordinates,
                None,
                Path(self.study.spatial.brainmask_path).resolve(),
            )
            self._feature_spaces[key] = value
            return value

    def _fiber_feature_space(self, connectome_id: str) -> _FeatureSpace:
        key = ("fiber", connectome_id)
        definitions = {
            item.connectome_id: item for item in self.study.spatial.connectomes
        }
        try:
            definition = definitions[connectome_id]
        except KeyError as exc:
            raise RuntimeInputProviderError(
                f"study does not define connectome {connectome_id!r}"
            ) from exc
        connectome_sha256 = self._path_hash(definition.streamlines_path)
        with self._lock:
            cached = self._feature_spaces.get(key)
            if cached is not None:
                return cached
            connectome = open_connectome(definition.streamlines_path)
            ids = np.arange(1, connectome.metadata.n_fibers + 1, dtype=np.int64)
            axis = AxisRef(
                axis_id=f"{self.study.study_id}:connectome-{connectome_id}:fibers",
                count=int(ids.size),
                sha256=canonical_hash(
                    {
                        "connectome_identity": connectome.metadata.connectome_identity,
                        "connectome_sha256": connectome_sha256,
                        "ordered_fiber_id_hash": connectome.metadata.ordered_fiber_id_hash,
                    }
                ),
            )
            ids.flags.writeable = False
            value = _FeatureSpace(
                axis,
                ids,
                None,
                connectome,
                Path(definition.streamlines_path).resolve(),
            )
            self._feature_spaces[key] = value
            return value

    def _matrix_for_binding(
        self,
        endpoint: EndpointRecord,
        subject_ids: tuple[str, ...],
        binding: EndpointBinding,
        frequency_class: str,
        feature_space: _FeatureSpace,
        *,
        allow_absent: bool,
        jitter_context: JitterTranslationContext | None = None,
    ) -> tuple[_TemporaryMatrix, tuple[str, ...]]:
        physical_subject_ids = tuple(subject.subject_id for subject in self.study.subjects)
        resolutions = tuple(
            self._resolve_groups(
                endpoint,
                self._subjects[subject_id],
                binding,
                frequency_class,
                require_bilateral=True,
            )
            for subject_id in physical_subject_ids
        )
        resolution_by_subject = dict(zip(physical_subject_ids, resolutions, strict=True))
        missing = tuple(
            subject_id
            for subject_id in subject_ids
            for resolution in (resolution_by_subject[subject_id],)
            if resolution.reason_code is not None
        )
        if missing and not allow_absent:
            raise RuntimeInputProviderError(
                "required endpoint exposure is missing for included subjects: "
                + ", ".join(missing)
            )
        key = self._shared_exposure_key(
            subject_ids=physical_subject_ids,
            binding=binding,
            frequency_class=frequency_class,
            feature_space=feature_space,
            resolutions=resolutions,
            jitter_context=jitter_context,
        )
        shared_entries = _ACTIVE_SHARED_EXPOSURES.get()
        if shared_entries is not None:
            value = {"kind": key.kind, "semantic_sha256": key.digest}
            if value not in shared_entries:
                shared_entries.append(value)
        if self._scientific_cache is None:
            physical = self._compute_binding_matrix(
                endpoint=endpoint,
                subject_ids=physical_subject_ids,
                binding=binding,
                frequency_class=frequency_class,
                feature_space=feature_space,
                resolutions=resolutions,
                allow_absent=True,
                jitter_context=jitter_context,
            )
            return (
                self._select_subject_rows(
                    physical,
                    physical_subject_ids,
                    subject_ids,
                    f"{endpoint.endpoint_id}-{binding.identifier}-{frequency_class}-subjects",
                ),
                missing,
            )

        with self._lock:
            preparation_lock = self._shared_preparation_locks.setdefault(
                key.digest,
                RLock(),
            )
        with preparation_lock:
            entry = self._scientific_cache.resolve(key)
            if entry is not None:
                physical = self._open_shared_exposure(entry.file_path("exposure.npy"))
                return (
                    self._select_subject_rows(
                        physical,
                        physical_subject_ids,
                        subject_ids,
                        f"{endpoint.endpoint_id}-{binding.identifier}-{frequency_class}-subjects",
                    ),
                    missing,
                )
            with self._scientific_cache.producer_lease(key) as producer:
                if not producer:
                    entry = self._scientific_cache.resolve(key)
                    if entry is None:
                        raise RuntimeInputProviderError(
                            "shared exposure producer lease ended without a cache entry"
                        )
                else:
                    temporary = self._compute_binding_matrix(
                        endpoint=endpoint,
                        subject_ids=physical_subject_ids,
                        binding=binding,
                        frequency_class=frequency_class,
                        feature_space=feature_space,
                        resolutions=resolutions,
                        allow_absent=True,
                        jitter_context=jitter_context,
                    )
                    subject_axis = AxisRef(
                        axis_id=(
                            f"{self.study.study_id}:physical-subjects:"
                            f"{canonical_hash(physical_subject_ids, length=12)}"
                        ),
                        count=len(physical_subject_ids),
                        sha256=canonical_hash(
                            {"ordered_subject_ids": physical_subject_ids}
                        ),
                    )
                    try:
                        entry = self._scientific_cache.publish(
                            key,
                            {"exposure.npy": temporary.path},
                            metadata={
                                "exposure.npy": CacheFileMetadata(
                                    dtype="float32",
                                    shape=(
                                        len(physical_subject_ids),
                                        feature_space.axis.count,
                                    ),
                                    axes=(subject_axis, feature_space.axis),
                                    units="V/m",
                                    space=self.study.spatial.canonical_space,
                                )
                            },
                        )
                    finally:
                        self._release_temporary_matrix(temporary)
            physical = self._open_shared_exposure(entry.file_path("exposure.npy"))
            return (
                self._select_subject_rows(
                    physical,
                    physical_subject_ids,
                    subject_ids,
                    f"{endpoint.endpoint_id}-{binding.identifier}-{frequency_class}-subjects",
                ),
                missing,
            )

    def _shared_exposure_key(
        self,
        *,
        subject_ids: tuple[str, ...],
        binding: EndpointBinding,
        frequency_class: str,
        feature_space: _FeatureSpace,
        resolutions: tuple[GroupResolution, ...],
        jitter_context: JitterTranslationContext | None,
    ) -> ScientificCacheKey:
        source_rows: list[dict[str, object]] = []
        for subject_id, resolution in zip(subject_ids, resolutions, strict=True):
            groups: list[dict[str, object]] = []
            for group in resolution.groups:
                if group.efield_path.is_file():
                    content_sha = self._path_hash(group.efield_path)
                else:
                    content_sha = canonical_hash(
                        {
                            "missing": True,
                            "subject_id": group.subject_id,
                            "electrode_id": group.electrode_id,
                            "frequency_group_id": group.frequency_group_id,
                        }
                    )
                groups.append(
                    {
                        "hemisphere": group.hemisphere,
                        "electrode_id": group.electrode_id,
                        "frequency_group_id": group.frequency_group_id,
                        "delivery_mode": group.delivery_mode,
                        "content_sha256": content_sha,
                    }
                )
            source_rows.append(
                {
                    "subject_id": subject_id,
                    "reason_code": resolution.reason_code,
                    "groups": groups,
                }
            )
        geometry_hash = self._path_hash(feature_space.source_path)
        transform_hash = self._path_hash(self.study.spatial.left_to_right_transform)
        jitter_identity = canonical_hash(
            {
                "replicate_index": (
                    None if jitter_context is None else jitter_context.replicate_index
                ),
                "replicate_seed": (
                    None if jitter_context is None else jitter_context.replicate_seed
                ),
                "translation_sigma_mm": (
                    None if jitter_context is None else jitter_context.translation_sigma_mm
                ),
            }
        )
        domain = "voxel" if feature_space.coordinates is not None else "fiber"
        kind = (
            "jitter_exposures"
            if jitter_context is not None
            else ("voxel_exposures" if domain == "voxel" else "fiber_exposures")
        )
        return ScientificCacheKey(
            geometry_hash=geometry_hash,
            stimulation_hash=canonical_hash({"physical_rows": source_rows}),
            component_frequency_hash=canonical_hash(
                {
                    "binding_id": binding.identifier,
                    "frequency_class": frequency_class,
                }
            ),
            transform_hash=transform_hash,
            connectome_feature_hash=feature_space.axis.sha256,
            backend_name=f"shared_{domain}_physical_exposure",
            backend_version="2",
            scientific_parameter_hashes=(
                ("jitter_schedule", jitter_identity),
                ("ordered_subjects", canonical_hash({"subject_ids": subject_ids})),
                (
                    "physical_rule",
                    canonical_hash(
                        {
                            "rule": (
                                "canonical_grid_bilateral_mean_v1"
                                if domain == "voxel"
                                else "side_specific_fiber_peak_then_mean_v1"
                            )
                        }
                    ),
                ),
            ),
            kind=kind,
        )

    def _select_subject_rows(
        self,
        source: _TemporaryMatrix,
        source_subject_ids: tuple[str, ...],
        requested_subject_ids: tuple[str, ...],
        label: str,
    ) -> _TemporaryMatrix:
        """Return the exact endpoint row subset while retaining one physical cache axis."""

        if requested_subject_ids == source_subject_ids:
            return source
        position_by_id = {
            subject_id: index for index, subject_id in enumerate(source_subject_ids)
        }
        try:
            positions = np.asarray(
                [position_by_id[subject_id] for subject_id in requested_subject_ids],
                dtype=np.int64,
            )
        except KeyError as exc:
            self._release_temporary_matrix(source)
            raise RuntimeInputProviderError(
                "endpoint subject axis is not a subset of the physical subject axis"
            ) from exc
        output = self._temporary_matrix(
            label,
            (len(requested_subject_ids), source.array.shape[1]),
            source.array.dtype,
        )
        completed = False
        try:
            for start in range(0, source.array.shape[1], self._fiber_chunk_size):
                stop = min(start + self._fiber_chunk_size, source.array.shape[1])
                output.array[:, start:stop] = source.array[positions, start:stop]
            output.array.flush()
            completed = True
            return output
        finally:
            self._release_temporary_matrix(source)
            if not completed:
                self._release_temporary_matrix(output)

    @staticmethod
    def _open_shared_exposure(path: Path) -> _TemporaryMatrix:
        try:
            array = np.load(path, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError) as exc:
            raise RuntimeInputProviderError(
                f"shared exposure cache cannot be mapped: {path}"
            ) from exc
        if not isinstance(array, np.memmap) or array.dtype != np.dtype(np.float32):
            raise RuntimeInputProviderError("shared exposure cache has an invalid array")
        return _TemporaryMatrix(array, path, delete_on_release=False)

    def _compute_binding_matrix(
        self,
        *,
        endpoint: EndpointRecord,
        subject_ids: tuple[str, ...],
        binding: EndpointBinding,
        frequency_class: str,
        feature_space: _FeatureSpace,
        resolutions: tuple[GroupResolution, ...],
        allow_absent: bool,
        jitter_context: JitterTranslationContext | None,
    ) -> _TemporaryMatrix:
        temporary = self._temporary_matrix(
            f"{endpoint.endpoint_id}-{binding.identifier}-{frequency_class}",
            (len(subject_ids), feature_space.axis.count),
            np.float32,
        )
        matrix = temporary.array
        completed = False
        try:
            if feature_space.coordinates is not None:
                for index, (subject_id, resolution) in enumerate(
                    zip(subject_ids, resolutions, strict=True)
                ):
                    translations = (
                        None
                        if jitter_context is None
                        else {
                            side: jitter_context.vector(
                                binding_id=binding.identifier,
                                frequency_class=frequency_class,
                                subject_id=subject_id,
                                hemisphere=side,
                            )
                            for side in ("L", "R")
                        }
                    )
                    matrix[index], _reason = self._sample_group_resolution(
                        resolution,
                        feature_space.coordinates,
                        allow_absent=allow_absent,
                        translation_by_side=translations,
                    )
                matrix.flush()
                completed = True
                return temporary

            connectome = feature_space.connectome
            if connectome is None:
                raise AssertionError("fiber feature space has no connectome")
            connectome_signature = self._file_signature(feature_space.source_path)
            expected_start = 0
            for chunk in connectome.iter_chunks(self._fiber_chunk_size):
                chunk_ids = np.asarray(chunk.fiber_ids)
                if chunk_ids.dtype != np.dtype(np.int64) or chunk_ids.ndim != 1:
                    raise RuntimeInputProviderError(
                        "connectome chunk fiber IDs must be one-dimensional int64"
                    )
                start = int(chunk_ids[0]) - 1
                stop = int(chunk_ids[-1])
                if start != expected_start or not np.array_equal(
                    chunk_ids,
                    np.arange(start + 1, stop + 1, dtype=np.int64),
                ):
                    raise RuntimeInputProviderError(
                        "connectome chunks must preserve contiguous canonical fiber IDs"
                    )
                for subject_index, resolution in enumerate(resolutions):
                    subject_id = subject_ids[subject_index]
                    translations = (
                        None
                        if jitter_context is None
                        else {
                            side: jitter_context.vector(
                                binding_id=binding.identifier,
                                frequency_class=frequency_class,
                                subject_id=subject_id,
                                hemisphere=side,
                            )
                            for side in ("L", "R")
                        }
                    )
                    fiber_values, _reason = self._sample_fiber_group_resolution(
                        resolution,
                        chunk.points,
                        chunk.point_offsets,
                        allow_absent=allow_absent,
                        translation_by_side=translations,
                    )
                    if fiber_values.shape != (stop - start,):
                        raise RuntimeInputProviderError(
                            "connectome chunk fiber IDs and point offsets disagree"
                        )
                    matrix[subject_index, start:stop] = fiber_values
                expected_start = stop
            if expected_start != feature_space.axis.count:
                raise RuntimeInputProviderError(
                    "connectome chunks do not cover the complete canonical fiber axis"
                )
            if self._file_signature(feature_space.source_path) != connectome_signature:
                raise RuntimeInputProviderError(
                    "connectome changed while fiber exposure was being prepared"
                )
            matrix.flush()
            completed = True
            return temporary
        finally:
            if not completed:
                self._release_temporary_matrix(temporary)

    def _omega_max_feature_space(
        self,
        parent: _FeatureSpace,
        exposure: np.ndarray,
        subject_ids: tuple[str, ...],
        profile: DirectVoxelModelProfile | NormativeFiberModelProfile,
    ) -> tuple[_FeatureSpace, np.ndarray | None]:
        if not isinstance(profile, NormativeFiberModelProfile):
            return parent, None
        minimum_tau = min(profile.source.tau_values)
        minimum_coverage = min(profile.source.coverage_values)
        matrix = np.asanyarray(exposure)
        counts = np.count_nonzero(matrix > minimum_tau, axis=0)
        positions = np.flatnonzero(counts > minimum_coverage).astype(np.int64)
        if positions.size == 0:
            return parent, None
        ids = np.asarray(parent.ids[positions], dtype=np.int64)
        ids.flags.writeable = False
        position_hash = hashlib.sha256(
            np.ascontiguousarray(positions, dtype="<i8").tobytes()
        ).hexdigest()
        axis = AxisRef(
            axis_id=f"{parent.axis.axis_id}:omega-max",
            count=int(ids.size),
            sha256=canonical_hash(
                {
                    "parent_axis_sha256": parent.axis.sha256,
                    "ordered_subject_ids": subject_ids,
                    "tau_values": profile.source.tau_values,
                    "coverage_values": profile.source.coverage_values,
                    "threshold_policy": "strict_threshold_v1",
                    "ordered_parent_positions_sha256": position_hash,
                }
            ),
        )
        self._publish_omega_max_cache(
            parent=parent,
            axis=axis,
            ids=ids,
            subject_ids=subject_ids,
            profile=profile,
        )
        return (
            _FeatureSpace(
                axis=axis,
                ids=ids,
                coordinates=None,
                connectome=parent.connectome,
                source_path=parent.source_path,
            ),
            None if positions.size == parent.axis.count else positions,
        )

    def _publish_omega_max_cache(
        self,
        *,
        parent: _FeatureSpace,
        axis: AxisRef,
        ids: np.ndarray,
        subject_ids: tuple[str, ...],
        profile: NormativeFiberModelProfile,
    ) -> None:
        if self._scientific_cache is None:
            return
        shared_entries = _ACTIVE_SHARED_EXPOSURES.get()
        physical_identity = (
            parent.axis.sha256
            if not shared_entries
            else shared_entries[0]["semantic_sha256"]
        )
        key = ScientificCacheKey(
            geometry_hash=self._path_hash(parent.source_path),
            stimulation_hash=physical_identity,
            component_frequency_hash=canonical_hash({"artifact": "omega_max"}),
            transform_hash=self._path_hash(self.study.spatial.left_to_right_transform),
            connectome_feature_hash=parent.axis.sha256,
            backend_name="normative_fiber_omega_max",
            backend_version="2",
            scientific_parameter_hashes=(
                ("eligible_cohort", canonical_hash({"subject_ids": subject_ids})),
                (
                    "threshold_grid",
                    canonical_hash(
                        {
                            "tau_values": profile.source.tau_values,
                            "coverage_values": profile.source.coverage_values,
                        }
                    ),
                ),
                ("threshold_policy", canonical_hash({"policy": "strict_threshold_v1"})),
            ),
            kind="fiber_exposures",
        )
        entry = self._scientific_cache.resolve(key)
        if entry is None:
            root = self._work_root / "omega-max-staging"
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"{key.digest}.npy"
            np.save(path, ids, allow_pickle=False)
            try:
                entry = self._scientific_cache.publish(
                    key,
                    {"fiber_ids.npy": path},
                    metadata={
                        "fiber_ids.npy": CacheFileMetadata(
                            dtype="int64",
                            shape=(axis.count,),
                            axes=(axis,),
                            units="fiber_id",
                            space=self.study.spatial.canonical_space,
                        )
                    },
                )
            finally:
                path.unlink(missing_ok=True)
        cached_ids = np.load(entry.file_path("fiber_ids.npy"), allow_pickle=False)
        if not np.array_equal(cached_ids, ids):
            raise RuntimeInputProviderError("Omega_max cache differs from the exact candidate union")
        if shared_entries is not None:
            value = {"kind": key.kind, "semantic_sha256": key.digest}
            if value not in shared_entries:
                shared_entries.append(value)

    def _subset_matrix(
        self,
        source: _TemporaryMatrix,
        positions: np.ndarray,
        label: str,
    ) -> _TemporaryMatrix:
        indices = np.asarray(positions, dtype=np.int64)
        if (
            indices.ndim != 1
            or indices.size < 1
            or indices[0] < 0
            or indices[-1] >= source.array.shape[1]
            or np.any(np.diff(indices) < 1)
        ):
            raise RuntimeInputProviderError("Omega_max positions must be ordered and unique")
        output = self._temporary_matrix(
            label,
            (source.array.shape[0], int(indices.size)),
            source.array.dtype,
        )
        completed = False
        try:
            for start in range(0, indices.size, self._fiber_chunk_size):
                stop = min(start + self._fiber_chunk_size, indices.size)
                output.array[:, start:stop] = source.array[:, indices[start:stop]]
            output.array.flush()
            completed = True
            return output
        finally:
            if not completed:
                self._release_temporary_matrix(output)

    @staticmethod
    def _publish_input_hash_manifest(
        publisher: ArtifactPublisher,
        endpoint: EndpointRecord,
        input_hashes: dict[str, str],
    ) -> ArtifactRef:
        return publisher.document(
            "input_hash_manifest.json",
            {
                "schema_version": "dual_frequency_prepared_input_hashes_v2",
                "endpoint_id": endpoint.endpoint_id,
                "files": [
                    {"path": path, "sha256": digest}
                    for path, digest in sorted(input_hashes.items())
                ],
                "shared_exposures": list(_ACTIVE_SHARED_EXPOSURES.get() or ()),
            },
            kind="prepared_input_hash_manifest",
        )

    @staticmethod
    def _validate_reference_dependency(
        endpoint: EndpointRecord,
        dependency: ReferenceDependencyRecord,
    ) -> SourceRecord | SensitiveRecord:
        if not isinstance(dependency, ReferenceDependencyRecord):
            raise TypeError("reference_dependency must be a ReferenceDependencyRecord")
        if dependency.addon_endpoint != endpoint.key:
            raise RuntimeInputProviderError(
                "reference dependency belongs to a different add-on endpoint"
            )
        expected_reference = endpoint.matched_reference_endpoint_id
        if expected_reference is None:
            raise RuntimeInputProviderError(
                "add-on endpoint has no configured matched reference endpoint"
            )
        if dependency.matched_reference_endpoint_id != expected_reference:
            raise RuntimeInputProviderError(
                "reference dependency does not match the catalog reference endpoint"
            )
        if dependency.dependency_status != "ready":
            raise RuntimeInputProviderError(
                "add-on exposure requires a ready reference dependency"
            )
        record = dependency.reference_record
        if not isinstance(record, (SourceRecord, SensitiveRecord)):
            raise RuntimeInputProviderError(
                "ready reference dependency has no typed reference record"
            )
        if record.endpoint.identifier != expected_reference:
            raise RuntimeInputProviderError(
                "reference record identity differs from the catalog dependency"
            )
        if record.endpoint.connectome_id != endpoint.key.connectome_id:
            raise RuntimeInputProviderError(
                "reference dependency connectome differs from the add-on endpoint"
            )
        return record

    def publish_prepared_exposure(
        self,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        publisher: ArtifactPublisher,
    ) -> PreparedExposureRecord:
        with self._capture_input_hashes() as input_hashes:
            return self._publish_prepared_exposure_impl(
                endpoint_input,
                reference_dependency,
                publisher,
                input_hashes,
                jitter_context=None,
            )

    def publish_jitter_prepared_exposure(
        self,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        publisher: ArtifactPublisher,
        jitter_context: JitterTranslationContext,
    ) -> PreparedExposureRecord:
        """Rebuild one endpoint exposure after deterministic spatial translation."""

        if not isinstance(jitter_context, JitterTranslationContext):
            raise TypeError("jitter_context must be a JitterTranslationContext")
        with self._capture_input_hashes() as input_hashes:
            return self._publish_prepared_exposure_impl(
                endpoint_input,
                reference_dependency,
                publisher,
                input_hashes,
                jitter_context=jitter_context,
            )

    def _publish_prepared_exposure_impl(
        self,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        publisher: ArtifactPublisher,
        input_hashes: dict[str, str],
        *,
        jitter_context: JitterTranslationContext | None,
    ) -> PreparedExposureRecord:
        if not isinstance(endpoint_input, EndpointInputRecord):
            raise TypeError("endpoint_input must be an EndpointInputRecord")
        if endpoint_input.readiness_status != "ready" or endpoint_input.subject_axis is None:
            raise RuntimeInputProviderError("prepared exposure requires ready endpoint input")
        endpoint = self.endpoint(endpoint_input.endpoint.identifier)
        if endpoint.key != endpoint_input.endpoint:
            raise RuntimeInputProviderError("endpoint input key differs from catalog endpoint")
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        subject_ids = endpoint_input.included_subject_ids
        profile = self._profile(endpoint)
        pair = profile.endpoint_pair
        sampling_feature_space = (
            self._direct_feature_space()
            if endpoint.key.model_family.endswith("voxel")
            else self._fiber_feature_space(endpoint.key.connectome_id)
        )
        is_reference = endpoint.key.model_family.startswith("reference_")
        primary_binding = pair.reference if is_reference else pair.addon
        primary_class = "reference" if is_reference else "addon"
        raw_primary, _missing_primary = self._matrix_for_binding(
            endpoint,
            subject_ids,
            primary_binding,
            primary_class,
            sampling_feature_space,
            allow_absent=False,
            jitter_context=jitter_context,
        )
        temporaries = [raw_primary]
        feature_space = sampling_feature_space
        omega_positions: np.ndarray | None = None
        if endpoint.key.model_family.endswith("fiber"):
            feature_space, omega_positions = self._omega_max_feature_space(
                sampling_feature_space,
                raw_primary.array,
                subject_ids,
                profile,
            )
            if omega_positions is not None:
                raw_primary = self._subset_matrix(
                    raw_primary,
                    omega_positions,
                    f"{endpoint.endpoint_id}-primary-omega-max",
                )
                temporaries.append(raw_primary)
        feature_ids = publisher.array(
            "feature_ids.npy",
            np.asarray(feature_space.ids, dtype=np.int64),
            kind=(
                "canonical_brainmask_voxel_ids"
                if endpoint.key.model_family.endswith("voxel")
                else "canonical_connectome_omega_max_fiber_ids"
            ),
            axes=(feature_space.axis,),
            units=None,
            space=self.study.spatial.canonical_space,
        )
        axes = (endpoint_input.subject_axis, feature_space.axis)
        try:
            if is_reference:
                exposure = publisher.array(
                    "exposure.npy",
                    raw_primary.array,
                    kind="prepared_reference_exposure",
                    axes=axes,
                    units="V/m",
                    space=self.study.spatial.canonical_space,
                )
                self._publish_input_hash_manifest(publisher, endpoint, input_hashes)
                return PreparedExposureRecord(
                    endpoint=endpoint.key,
                    subject_axis=endpoint_input.subject_axis,
                    feature_axis=feature_space.axis,
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

            if reference_dependency is None:
                raise RuntimeInputProviderError(
                    "add-on exposure requires reference dependency"
                )
            reference_record = self._validate_reference_dependency(
                endpoint,
                reference_dependency,
            )
            reference_condition, missing_reference_condition = self._matrix_for_binding(
                endpoint,
                subject_ids,
                pair.reference,
                "reference",
                sampling_feature_space,
                allow_absent=True,
                jitter_context=jitter_context,
            )
            temporaries.append(reference_condition)
            if omega_positions is not None:
                reference_condition = self._subset_matrix(
                    reference_condition,
                    omega_positions,
                    f"{endpoint.endpoint_id}-reference-condition-omega-max",
                )
                temporaries.append(reference_condition)
            addon_reference_component, missing_addon_reference = self._matrix_for_binding(
                endpoint,
                subject_ids,
                pair.addon,
                "reference",
                sampling_feature_space,
                allow_absent=True,
                jitter_context=jitter_context,
            )
            temporaries.append(addon_reference_component)
            if omega_positions is not None:
                addon_reference_component = self._subset_matrix(
                    addon_reference_component,
                    omega_positions,
                    f"{endpoint.endpoint_id}-addon-reference-omega-max",
                )
                temporaries.append(addon_reference_component)
            reference_accepted = (
                isinstance(reference_record, SourceRecord)
                and reference_record.source_status in ACCEPTED_SOURCE_STATUSES
            ) or (
                isinstance(reference_record, SensitiveRecord)
                and reference_record.cell_computability_status == "computable"
            )
            if not reference_accepted:
                delta_status = "not_applicable"
                delta_reason = "reference_source_absent"
            elif missing_reference_condition:
                delta_status = "input_failure"
                delta_reason = "missing_reference_condition_exposure"
            elif missing_addon_reference:
                delta_status = "input_failure"
                delta_reason = "missing_addon_reference_component_exposure"
            else:
                delta_status = "ready"
                delta_reason = "ready"

            if endpoint.key.model_family.endswith("voxel"):
                if not isinstance(reference_record, SourceRecord):
                    raise RuntimeInputProviderError(
                        "add-on voxel dependency requires SourceRecord"
                    )
                overlap = prepare_reference_overlap(
                    raw_primary.array,
                    addon_reference_component.array,
                    reference_record,
                )
                prepared: np.ndarray = np.asarray(
                    overlap.addon_exposure,
                    dtype=np.float32,
                )
                overlap_mask: np.ndarray = np.asarray(
                    overlap.overlap_mask,
                    dtype=bool,
                )
            else:
                overlap_temporary = self._temporary_matrix(
                    f"{endpoint.endpoint_id}-reference-overlap",
                    raw_primary.array.shape,
                    np.bool_,
                )
                temporaries.append(overlap_temporary)
                if isinstance(reference_record, SensitiveRecord) and (
                    reference_record.cell_computability_status != "computable"
                ):
                    overlap_temporary.array[:] = False
                    overlap_temporary.array.flush()
                    prepared = raw_primary.array
                    overlap_mask = overlap_temporary.array
                else:
                    prepared_temporary = self._temporary_matrix(
                        f"{endpoint.endpoint_id}-addon-only",
                        raw_primary.array.shape,
                        np.float32,
                    )
                    temporaries.append(prepared_temporary)
                    overlap = prepare_addon_fiber_exposure(
                        raw_primary.array,
                        addon_reference_component.array,
                        reference_record,
                        matched_reference_endpoint_id=(
                            reference_dependency.matched_reference_endpoint_id
                        ),
                        matched_reference_connectome_id=endpoint.key.connectome_id,
                        destination=prepared_temporary.array,
                        reference_active_destination=overlap_temporary.array,
                        feature_chunk_size=self._fiber_chunk_size,
                    )
                    prepared = overlap.exposure
                    overlap_mask = overlap.reference_active

            exposure = publisher.array(
                "exposure.npy",
                prepared,
                kind="prepared_addon_only_exposure",
                axes=axes,
                units="V/m",
                space=self.study.spatial.canonical_space,
            )
            reference_condition_artifact = publisher.array(
                "reference_condition_exposure.npy",
                reference_condition.array,
                kind="reference_condition_exposure",
                axes=axes,
                units="V/m",
                space=self.study.spatial.canonical_space,
            )
            addon_reference_artifact = publisher.array(
                "addon_reference_component_exposure.npy",
                addon_reference_component.array,
                kind="addon_reference_component_exposure",
                axes=axes,
                units="V/m",
                space=self.study.spatial.canonical_space,
            )
            overlap_artifact = publisher.array(
                "reference_overlap_mask.npy",
                overlap_mask,
                kind="reference_overlap_mask",
                axes=axes,
                units="binary",
                space=self.study.spatial.canonical_space,
            )
            total_artifact = publisher.array(
                "total_exposure.npy",
                raw_primary.array,
                kind="raw_addon_component_exposure",
                axes=axes,
                units="V/m",
                space=self.study.spatial.canonical_space,
            )
            input_hash_manifest = self._publish_input_hash_manifest(
                publisher,
                endpoint,
                input_hashes,
            )
            auxiliary_readiness = publisher.document(
                "auxiliary_readiness.json",
                {
                    "schema_version": "dual_frequency_auxiliary_readiness_v1",
                    "delta_reference_input_status": delta_status,
                    "delta_reference_reason_code": delta_reason,
                    "missing_reference_condition_subject_ids": list(
                        missing_reference_condition
                    ),
                    "missing_addon_reference_component_subject_ids": list(
                        missing_addon_reference
                    ),
                    "input_hash_manifest": {
                        "artifact_id": input_hash_manifest.identifier,
                        "sha256": input_hash_manifest.sha256,
                        "uri": input_hash_manifest.uri,
                    },
                },
                kind="addon_auxiliary_readiness",
            )
            return PreparedExposureRecord(
                endpoint=endpoint.key,
                subject_axis=endpoint_input.subject_axis,
                feature_axis=feature_space.axis,
                exposure=exposure,
                feature_ids=feature_ids,
                delta_reference_input_status=delta_status,
                delta_reference_reason_code=delta_reason,
                auxiliary_readiness=auxiliary_readiness,
                reference_condition_exposure=reference_condition_artifact,
                addon_reference_component_exposure=addon_reference_artifact,
                reference_overlap_mask=overlap_artifact,
                total_exposure=total_artifact,
            )
        finally:
            for temporary in reversed(temporaries):
                self._release_temporary_matrix(temporary)

    def _source_grid(self, endpoint: EndpointRecord) -> SourceGrid:
        profile = self._profile(endpoint)
        source = profile.source
        return SourceGrid(
            pre_specified_tau=source.pre_specified.tau,
            pre_specified_coverage=source.pre_specified.coverage,
            tau_values=source.tau_values,
            coverage_values=source.coverage_values,
            minimum_adjacent_passing_cells=source.minimum_adjacent_passing_cells,
        )

    def _hard_limits(self, endpoint: EndpointRecord) -> HardComputabilityLimits:
        if endpoint.key.model_family.endswith("voxel"):
            profile = self.configuration.direct_voxel.hard_computability
            return HardComputabilityLimits(
                profile.n_subjects_min,
                profile.n_features_full_min,
                profile.fold_n_features_min,
            )
        profile = self.configuration.normative_fiber
        connectome = next(
            item for item in profile.connectomes if item.connectome_id == endpoint.key.connectome_id
        )
        return HardComputabilityLimits(
            profile.hard_computability.n_subjects_min,
            None,
            connectome.fold_candidate_fibers_min,
        )

    def _fiber_score_settings(
        self,
        endpoint: EndpointRecord,
    ) -> NormativeFiberScoreSettings | None:
        if endpoint.key.model_family.endswith("voxel"):
            return None
        score = self.configuration.normative_fiber.score
        return NormativeFiberScoreSettings(
            sweet_fraction=score.sweet_fraction,
            sour_fraction=score.sour_fraction,
            weighted_peak_fraction=score.weighted_peak_fraction,
            sweet_selected_min_count=score.sweet_selected_min_count,
            sour_selected_min_count=score.sour_selected_min_count,
            weighted_peak_min_count=score.weighted_peak_min_count,
        )

    def observed_request(
        self,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        *,
        branch: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> ObservedRequest:
        endpoint = self.endpoint(endpoint_input.endpoint.identifier)
        if endpoint_input.readiness_status != "ready":
            raise RuntimeInputProviderError("observed request requires ready endpoint input")
        if endpoint_input.subject_axis is None or endpoint_input.baseline is None or endpoint_input.outcome is None:
            raise RuntimeInputProviderError("ready endpoint input is incomplete")
        if prepared.endpoint != endpoint.key or prepared.subject_axis != endpoint_input.subject_axis:
            raise RuntimeInputProviderError("prepared exposure does not match endpoint input")
        allowed_branches = (
            {"reference"}
            if endpoint.key.model_family.startswith("reference_")
            else {"no_delta_reference", "delta_reference_adjusted"}
        )
        if branch not in allowed_branches:
            raise RuntimeInputProviderError(
                f"branch {branch!r} is invalid for {endpoint.key.model_family}"
            )
        nuisance: tuple[ArtifactRef, ...] = ()
        if branch == "delta_reference_adjusted":
            if prepared.delta_reference_input_status != "ready":
                raise RuntimeInputProviderError(
                    "adjusted branch requires prepared DeltaReferenceScore inputs"
                )
            if delta_reference is None or not delta_reference.valid:
                raise RuntimeInputProviderError("adjusted branch requires valid DeltaReferenceScore")
            self._validate_delta_reference_axes(
                delta_reference,
                endpoint_input.subject_axis,
            )
            assert delta_reference.full_scores is not None
            assert delta_reference.fold_scores is not None
            nuisance = (delta_reference.full_scores, delta_reference.fold_scores)
        return ObservedRequest(
            endpoint=endpoint.key,
            branch=branch,
            exposure=prepared.exposure,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            nuisance_inputs=nuisance,
            subject_axis=endpoint_input.subject_axis,
            feature_axis=prepared.feature_axis,
            source_grid=self._source_grid(endpoint),
            exposure_units="V/m",
            exposure_space=self.study.spatial.canonical_space,
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            feature_ids=(
                prepared.feature_ids
                if endpoint.key.model_family.endswith("fiber")
                else None
            ),
            fiber_score_settings=self._fiber_score_settings(endpoint),
        )

    @staticmethod
    def _validate_delta_reference_axes(
        delta_reference: DeltaReferenceBundle,
        subject_axis: AxisRef,
    ) -> None:
        if not delta_reference.valid:
            raise RuntimeInputProviderError("DeltaReferenceScore bundle is not valid")
        full = delta_reference.full_scores
        folds = delta_reference.fold_scores
        if full is None or folds is None:
            raise RuntimeInputProviderError("valid DeltaReferenceScore bundle is incomplete")
        if full.axis_refs != (subject_axis,) or folds.axis_refs != (
            subject_axis,
            subject_axis,
        ):
            raise RuntimeInputProviderError(
                "DeltaReferenceScore axes differ from the endpoint subject axis"
            )

    def _materialize(self, artifact: ArtifactRef) -> np.ndarray:
        if self._artifact_store is None:
            raise RuntimeInputProviderError("artifact_store is required to slice final inputs")
        return self._artifact_store.materialize(
            artifact,
            expected_dtype=artifact.dtype,
            expected_shape=artifact.shape,
            expected_axes=artifact.axis_refs,
            expected_units=artifact.units,
            expected_space=artifact.space,
            mmap_mode="r",
        )

    @staticmethod
    def _selected_source(final_model: FinalModelRecord) -> SourceRecord:
        source = final_model.selected_source
        if source is None and final_model.selected_branch is not None:
            source = final_model.selected_branch.source
        if source is None:
            raise RuntimeInputProviderError("realized final has no selected source")
        return source

    def selected_exposure(
        self,
        final_model: FinalModelRecord,
        prepared: PreparedExposureRecord,
        publisher: ArtifactPublisher,
    ) -> tuple[ArtifactRef, ArtifactRef | None]:
        if not isinstance(final_model, FinalModelRecord):
            raise TypeError("final_model must be a FinalModelRecord")
        if not isinstance(prepared, PreparedExposureRecord):
            raise TypeError("prepared must be a PreparedExposureRecord")
        if final_model.endpoint != prepared.endpoint:
            raise RuntimeInputProviderError(
                "final model and prepared exposure identify different endpoints"
            )
        if final_model.final_key is None:
            raise RuntimeInputProviderError("realized final model has no final key")
        source = self._selected_source(final_model)
        if source.endpoint != final_model.endpoint:
            raise RuntimeInputProviderError(
                "selected source endpoint differs from the final endpoint"
            )
        parent_exposure = self._materialize(prepared.exposure)
        parent_ids = self._materialize(prepared.feature_ids)
        if parent_ids.dtype != np.dtype(np.int64) or parent_ids.ndim != 1:
            raise RuntimeInputProviderError(
                "canonical parent feature IDs must be one-dimensional int64"
            )
        if parent_ids.shape != (prepared.feature_axis.count,):
            raise RuntimeInputProviderError(
                "canonical parent feature IDs differ from the parent feature axis"
            )
        if parent_ids.size and np.any(np.diff(parent_ids) <= 0):
            raise RuntimeInputProviderError(
                "canonical parent feature IDs must be unique and strictly increasing"
            )
        selected_axis = final_model.valid_feature_axis.axis
        if source.feature_axis is None or source.feature_axis.axis != selected_axis:
            raise RuntimeInputProviderError(
                "selected source does not carry the final selected axis"
            )
        tau = source.selected_tau
        coverage = source.selected_coverage
        if tau is None or coverage is None:
            raise RuntimeInputProviderError("realized final source lacks tau or Coverage")
        if final_model.endpoint.model_family.endswith("voxel"):
            matches = tuple(item for item in source.artifacts if item.kind == "selected_feature_indices")
            if len(matches) != 1:
                raise RuntimeInputProviderError("direct final requires one selected_feature_indices artifact")
            if matches[0].axis_refs != (selected_axis,):
                raise RuntimeInputProviderError(
                    "selected feature-index artifact does not bind the final axis"
                )
            indices = self._materialize(matches[0])
            if indices.dtype != np.dtype(np.int64) or indices.ndim != 1:
                raise RuntimeInputProviderError(
                    "selected feature indices must be one-dimensional int64"
                )
            if indices.size and (
                indices[0] < 0
                or indices[-1] >= parent_ids.size
                or np.any(np.diff(indices) <= 0)
            ):
                raise RuntimeInputProviderError(
                    "selected feature indices must be ordered, unique, and in bounds"
                )
            selected_ids = parent_ids[indices]
            if final_model.endpoint.model_family.startswith("reference_"):
                expected_payload = {
                    "parent_axis_sha256": prepared.feature_axis.sha256,
                    "selected_indices": indices.tolist(),
                    "tau": tau,
                    "coverage": coverage,
                }
                expected_identity_source = "selected_direct_voxel_feature_union"
            else:
                expected_payload = {
                    "parent_axis_sha256": prepared.feature_axis.sha256,
                    "branch": final_model.final_key.final_branch,
                    "selected_indices": indices.tolist(),
                    "tau": tau,
                    "coverage": coverage,
                }
                expected_identity_source = "selected_addon_direct_voxel_feature_union"
            expected_hash = canonical_hash(expected_payload)
            if final_model.valid_feature_axis.identity_source != expected_identity_source:
                raise RuntimeInputProviderError(
                    "direct final uses an unexpected selected-axis identity authority"
                )
            selected_feature_ids: ArtifactRef | None = None
        else:
            matches = tuple(
                item for item in source.artifacts if item.kind == "normative_fiber_valid_union_ids"
            )
            if len(matches) != 1:
                raise RuntimeInputProviderError("fiber final requires one valid-union ID artifact")
            if matches[0].axis_refs != (selected_axis,):
                raise RuntimeInputProviderError(
                    "valid-union fiber-ID artifact does not bind the final axis"
                )
            source_ids = self._materialize(matches[0])
            if source_ids.dtype != np.dtype(np.int64) or source_ids.ndim != 1:
                raise RuntimeInputProviderError(
                    "selected fiber IDs must be one-dimensional int64"
                )
            if source_ids.size and np.any(np.diff(source_ids) <= 0):
                raise RuntimeInputProviderError(
                    "selected fiber IDs must be unique and preserve parent order"
                )
            indices = np.searchsorted(parent_ids, source_ids)
            if np.any(indices >= parent_ids.size) or not np.array_equal(parent_ids[indices], source_ids):
                raise RuntimeInputProviderError("selected fiber IDs are outside the parent axis")
            selected_ids = source_ids
            selected_id_digest = hashlib.sha256(
                np.ascontiguousarray(selected_ids, dtype=np.int64).tobytes(order="C")
            ).hexdigest()
            expected_hash = canonical_hash(
                {
                    "parent_axis_sha256": prepared.feature_axis.sha256,
                    "selected_fiber_ids_sha256": selected_id_digest,
                    "tau": tau,
                    "coverage": coverage,
                }
            )
            if final_model.valid_feature_axis.identity_source != (
                "selected_normative_fiber_full_fold_valid_union"
            ):
                raise RuntimeInputProviderError(
                    "fiber final uses an unexpected selected-axis identity authority"
                )
            selected_feature_ids = matches[0]
        if selected_ids.size != selected_axis.count:
            raise RuntimeInputProviderError("selected feature count differs from final axis")
        if selected_axis.sha256 != expected_hash:
            raise RuntimeInputProviderError(
                "selected features do not reproduce the locked final-axis identity"
            )
        branch = final_model.final_key.final_branch
        if final_model.endpoint.model_family.startswith("reference_"):
            expected_branch = "reference"
        else:
            if final_model.selected_branch is None:
                raise RuntimeInputProviderError(
                    "add-on final has no selected branch"
                )
            expected_branch = final_model.selected_branch.branch
        if branch != expected_branch:
            raise RuntimeInputProviderError(
                "final branch differs from the selected source or branch"
            )
        selected_temporary = self._temporary_matrix(
            f"{final_model.endpoint.identifier}-selected-exposure",
            (prepared.subject_axis.count, selected_axis.count),
            np.float32,
        )
        try:
            for start in range(0, selected_axis.count, self._fiber_chunk_size):
                stop = min(start + self._fiber_chunk_size, selected_axis.count)
                selected_temporary.array[:, start:stop] = parent_exposure[
                    :,
                    indices[start:stop],
                ]
            selected_temporary.array.flush()
            selected_exposure = publisher.array(
                "selected_exposure.npy",
                selected_temporary.array,
                kind="final_selected_exposure",
                axes=(prepared.subject_axis, selected_axis),
                units=prepared.exposure.units,
                space=prepared.exposure.space,
            )
        finally:
            self._release_temporary_matrix(selected_temporary)
        return selected_exposure, selected_feature_ids

    def activation_runtime_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        publisher: ArtifactPublisher,
        *,
        workers: int,
        allow_expensive_producers: bool,
    ) -> OSSActivationRuntimeRequest:
        """Build exact cache-first OSS rows for one realized fiber final."""

        endpoint = self.endpoint(final_model.endpoint.identifier)
        if not endpoint.key.model_family.endswith("fiber"):
            raise RuntimeInputProviderError(
                "activation runtime is defined only for normative-fiber endpoints"
            )
        if (
            endpoint.key != final_model.endpoint
            or endpoint_input.endpoint != final_model.endpoint
            or prepared.endpoint != final_model.endpoint
        ):
            raise RuntimeInputProviderError(
                "activation final, endpoint input, prepared exposure, and catalog must match"
            )
        if (
            endpoint_input.readiness_status != "ready"
            or endpoint_input.subject_axis is None
            or prepared.subject_axis != endpoint_input.subject_axis
        ):
            raise RuntimeInputProviderError(
                "activation runtime requires one ready, aligned subject axis"
            )
        if endpoint.connectome_role != "formal":
            raise RuntimeInputProviderError(
                "activation runtime requires the configured formal connectome"
            )
        source = self._selected_source(final_model)
        id_artifacts = tuple(
            artifact
            for artifact in source.artifacts
            if artifact.kind == "normative_fiber_valid_union_ids"
        )
        if len(id_artifacts) != 1:
            raise RuntimeInputProviderError(
                "activation final requires one selected normative-fiber ID artifact"
            )
        feature_ids = np.asarray(self._materialize(id_artifacts[0]))
        if (
            feature_ids.dtype != np.dtype(np.int64)
            or feature_ids.shape != (final_model.valid_feature_axis.axis.count,)
            or (feature_ids.size and np.any(np.diff(feature_ids) <= 0))
        ):
            raise RuntimeInputProviderError(
                "activation final fiber IDs must be ordered, unique int64 values"
            )
        connectomes = tuple(
            item
            for item in self.configuration.normative_fiber.connectomes
            if item.connectome_id == endpoint.key.connectome_id
        )
        if len(connectomes) != 1 or connectomes[0].role != "formal":
            raise RuntimeInputProviderError(
                "activation endpoint does not resolve to one formal connectome"
            )
        oss = self.configuration.normative_fiber.oss
        settings = OSSScientificSettings(
            backend_version=self._oss_backend_version(),
            model=oss.model,
            activation_model=oss.activation_model,
            diameter_min_um=oss.fiber_diameter_um.minimum,
            diameter_max_um=oss.fiber_diameter_um.maximum,
            diameter_samples=oss.fiber_diameter_um.samples,
            sampling=oss.fiber_diameter_um.sampling,
            fitting_probability_threshold=oss.fitting_probability_threshold,
        )
        return OSSActivationRuntimeRequest(
            final_model=final_model,
            connectome_role=endpoint.connectome_role,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=endpoint_input.included_subject_ids,
            feature_axis=final_model.valid_feature_axis.axis,
            feature_ids=feature_ids,
            sources=self._activation_sources(endpoint, endpoint_input, publisher),
            connectome_feature_hash=self._path_hash(connectomes[0].path),
            settings=settings,
            allow_expensive_producers=allow_expensive_producers,
            workers=workers,
        )

    def activation_fitting_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        materialized_rows: OSSRowBatchArtifact,
        reference_overlap_mask: ArtifactRef | None,
        publisher: ArtifactPublisher,
        *,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> ActivationRequest:
        """Bind materialized OSS rows to the endpoint's immutable fitting inputs."""

        endpoint = self.endpoint(final_model.endpoint.identifier)
        if (
            endpoint.key != final_model.endpoint
            or endpoint_input.endpoint != final_model.endpoint
            or prepared.endpoint != final_model.endpoint
        ):
            raise RuntimeInputProviderError(
                "activation fitting inputs identify different endpoints"
            )
        if (
            endpoint_input.readiness_status != "ready"
            or endpoint_input.subject_axis is None
            or endpoint_input.baseline is None
            or endpoint_input.outcome is None
            or prepared.subject_axis != endpoint_input.subject_axis
        ):
            raise RuntimeInputProviderError(
                "activation fitting requires complete, aligned endpoint inputs"
            )
        if (
            materialized_rows.final_model_id != final_model.identifier
            or materialized_rows.feature_axis != final_model.valid_feature_axis.axis
        ):
            raise RuntimeInputProviderError(
                "materialized OSS rows differ from the realized final"
            )
        source = self._selected_source(final_model)
        id_artifacts = tuple(
            artifact
            for artifact in source.artifacts
            if artifact.kind == "normative_fiber_valid_union_ids"
        )
        score_artifacts = tuple(
            artifact
            for artifact in source.artifacts
            if artifact.kind == "normative_fiber_full_scores"
        )
        if len(id_artifacts) != 1 or len(score_artifacts) != 1:
            raise RuntimeInputProviderError(
                "activation final lacks one fiber-ID or full-score authority"
            )
        feature_ids = np.asarray(self._materialize(id_artifacts[0]))
        if feature_ids.dtype != np.dtype(np.int64):
            raise RuntimeInputProviderError("activation final fiber IDs must be int64")
        feature_id_artifact = publisher.array(
            "oss_final_feature_ids.npy",
            feature_ids,
            kind="oss_final_feature_ids",
            axes=(final_model.valid_feature_axis.axis,),
            units="fiber_id",
            space="right_canonical",
        )

        is_reference = final_model.endpoint.model_family.startswith("reference_")
        overlap: ArtifactRef | None = None
        if is_reference:
            if reference_overlap_mask is not None:
                raise RuntimeInputProviderError(
                    "reference activation cannot receive an overlap mask"
                )
        else:
            if reference_overlap_mask is None:
                raise RuntimeInputProviderError(
                    "add-on activation requires the selected reference-overlap mask"
                )
            overlap_values = np.asarray(
                self._materialize(reference_overlap_mask),
                dtype=bool,
            )
            overlap = publisher.array(
                "oss_reference_overlap_mask.npy",
                overlap_values,
                kind="oss_reference_overlap_mask",
                axes=(
                    endpoint_input.subject_axis,
                    final_model.valid_feature_axis.axis,
                ),
                units="binary",
                space="right_canonical",
            )

        nuisance: tuple[ArtifactRef, ...] = ()
        branch = final_model.final_key.final_branch if final_model.final_key else None
        if branch == "delta_reference_adjusted":
            if prepared.delta_reference_input_status != "ready":
                raise RuntimeInputProviderError(
                    "adjusted activation requires prepared DeltaReferenceScore inputs"
                )
            if delta_reference is None or not delta_reference.valid:
                raise RuntimeInputProviderError(
                    "adjusted activation requires valid DeltaReferenceScore"
                )
            self._validate_delta_reference_axes(
                delta_reference,
                endpoint_input.subject_axis,
            )
            assert delta_reference.full_scores is not None
            assert delta_reference.fold_scores is not None
            nuisance = (delta_reference.full_scores, delta_reference.fold_scores)
        elif branch not in {"reference", "no_delta_reference"}:
            raise RuntimeInputProviderError(
                f"unsupported activation final branch {branch!r}"
            )

        profile = self.configuration.normative_fiber
        return ActivationRequest(
            final_model=final_model,
            activation_probability=materialized_rows.activation_probability,
            reference_overlap_mask=overlap,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            peak_final_score=score_artifacts[0],
            nuisance_inputs=nuisance,
            subject_axis=endpoint_input.subject_axis,
            feature_axis=final_model.valid_feature_axis.axis,
            feature_ids=feature_id_artifact,
            activation_feature_ids=materialized_rows.feature_ids,
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            fiber_score_settings=self._fiber_score_settings(endpoint),
            fitting_probability_threshold=profile.oss.fitting_probability_threshold,
            permutation_resamples=profile.oss.permutation_resamples,
            seed=profile.formal_resampling.seed,
        )

    def formal_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        publisher: ArtifactPublisher,
        *,
        resampling_kind: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> FormalRequest:
        if resampling_kind not in {"permutation", "bootstrap"}:
            raise RuntimeInputProviderError(
                "resampling_kind must be 'permutation' or 'bootstrap'"
            )
        endpoint = self.endpoint(final_model.endpoint.identifier)
        if (
            final_model.endpoint != endpoint_input.endpoint
            or final_model.endpoint != prepared.endpoint
            or endpoint.key != final_model.endpoint
        ):
            raise RuntimeInputProviderError(
                "formal final, endpoint input, prepared exposure, and catalog must match"
            )
        if endpoint_input.readiness_status != "ready":
            raise RuntimeInputProviderError("formal request requires ready endpoint input")
        if endpoint_input.subject_axis is None or endpoint_input.baseline is None or endpoint_input.outcome is None:
            raise RuntimeInputProviderError("formal request requires complete endpoint input")
        if prepared.subject_axis != endpoint_input.subject_axis:
            raise RuntimeInputProviderError(
                "formal prepared exposure uses a different subject axis"
            )
        adjusted = (
            final_model.final_key is not None
            and final_model.final_key.final_branch == "delta_reference_adjusted"
        )
        if adjusted:
            if prepared.delta_reference_input_status != "ready":
                raise RuntimeInputProviderError(
                    "adjusted formal request requires prepared DeltaReferenceScore inputs"
                )
            if delta_reference is None or not delta_reference.valid:
                raise RuntimeInputProviderError(
                    "adjusted formal request requires valid DeltaReferenceScore"
                )
            self._validate_delta_reference_axes(
                delta_reference,
                endpoint_input.subject_axis,
            )
        exposure, feature_ids = self.selected_exposure(final_model, prepared, publisher)
        profile = self._profile(endpoint).formal_resampling
        resamples = (
            profile.permutation_resamples
            if resampling_kind == "permutation"
            else profile.bootstrap_resamples
        )
        return FormalRequest(
            final_model=final_model,
            resampling_kind=resampling_kind,
            exposure=exposure,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            delta_reference_full=(
                delta_reference.full_scores if adjusted and delta_reference is not None else None
            ),
            delta_reference_folds=(
                delta_reference.fold_scores if adjusted and delta_reference is not None else None
            ),
            subject_axis=endpoint_input.subject_axis,
            feature_axis=final_model.valid_feature_axis.axis,
            exposure_units="V/m",
            exposure_space=self.study.spatial.canonical_space,
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            feature_ids=feature_ids,
            fiber_score_settings=self._fiber_score_settings(endpoint),
            resamples=resamples,
            seed=profile.seed,
        )


__all__ = [
    "FrequencyGroupArtifact",
    "GroupResolution",
    "JitterTranslationContext",
    "LeftToCanonicalTransformer",
    "MatlabLeftToCanonicalTransformer",
    "RuntimeInputProvider",
    "RuntimeInputProviderError",
    "StudyRuntimeInputProvider",
]
