"""Production spatial-jitter provider for individualized target models."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import uuid

import fcntl
import numpy as np

from ..backends.delta_reference import (
    build_delta_reference_individualized_target,
)
from ..backends.sensitivity import (
    SpatialJitterSettings,
    TargetJitterReplicateEvidence,
)
from ..cache import ArtifactStore
from ..contracts import (
    ArtifactRef,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FinalModelRecord,
    ReferenceDependencyRecord,
    SourceRecord,
    TargetObservedRequest,
    canonical_hash,
)
from .input_provider import (
    StudyRuntimeInputProvider,
    TargetJitterBurdenBlock,
)
from .jitter_blocks import (
    JitterBlockArrayProvider,
    _ArenaPublisher,
    _MemoryArena,
)


class StudyTargetJitterProviderError(RuntimeError):
    """Raised when a translated target exposure cannot be prepared."""


TARGET_JITTER_BLOCK_SIZE = 25


def _token(value: float) -> str:
    return f"{float(value):g}".replace(".", "p")


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_npy(path: Path, value: np.ndarray) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class StudyTargetJitterReplicateProvider:
    """Reuse shared translated target burdens and rebuild endpoint statistics."""

    def __init__(
        self,
        *,
        provider: StudyRuntimeInputProvider,
        endpoint_input: EndpointInputRecord,
        reference_input: EndpointInputRecord | None,
        reference_dependency: ReferenceDependencyRecord | None,
        final_model: FinalModelRecord,
        original_request: TargetObservedRequest,
        artifact_store: ArtifactStore,
        settings: SpatialJitterSettings,
    ) -> None:
        if not isinstance(provider, StudyRuntimeInputProvider):
            raise TypeError("provider must be a StudyRuntimeInputProvider")
        if not isinstance(endpoint_input, EndpointInputRecord):
            raise TypeError("endpoint_input must be an EndpointInputRecord")
        if not isinstance(final_model, FinalModelRecord):
            raise TypeError("final_model must be a FinalModelRecord")
        if not isinstance(original_request, TargetObservedRequest):
            raise TypeError("original_request must be TargetObservedRequest")
        if final_model.endpoint != endpoint_input.endpoint:
            raise StudyTargetJitterProviderError(
                "target jitter final and endpoint input do not match"
            )
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore")
        if not isinstance(settings, SpatialJitterSettings):
            raise TypeError("settings must be SpatialJitterSettings")
        is_addon = final_model.endpoint.model_family.startswith("addon_")
        if is_addon and (
            not isinstance(reference_input, EndpointInputRecord)
            or not isinstance(reference_dependency, ReferenceDependencyRecord)
        ):
            raise StudyTargetJitterProviderError(
                "add-on target jitter requires its matched reference inputs"
            )
        if not is_addon and (
            reference_input is not None or reference_dependency is not None
        ):
            raise StudyTargetJitterProviderError(
                "reference target jitter cannot receive add-on dependencies"
            )
        self.provider = provider
        self.endpoint_input = endpoint_input
        self.reference_input = reference_input
        self.reference_dependency = reference_dependency
        self.final_model = final_model
        self.original_request = original_request
        self.artifact_store = artifact_store
        self.settings = settings
        self._arena = _MemoryArena()
        self.array_provider = JitterBlockArrayProvider(
            self._arena,
            artifact_store,
        )
        self._loaded_leaf: Path | None = None
        self._loaded_block: TargetJitterBurdenBlock | None = None

    def replicate_indices(self) -> tuple[int, ...]:
        """Return a block-rotated order with fixed replicate identities."""

        replicates = self.settings.replicates
        block_count = (
            replicates + TARGET_JITTER_BLOCK_SIZE - 1
        ) // TARGET_JITTER_BLOCK_SIZE
        start_block = int(
            canonical_hash(
                {"endpoint_id": self.final_model.endpoint.identifier},
                length=8,
            ),
            16,
        ) % block_count
        ordered_blocks = (
            *range(start_block, block_count),
            *range(0, start_block),
        )
        return tuple(
            index
            for block_index in ordered_blocks
            for index in range(
                block_index * TARGET_JITTER_BLOCK_SIZE,
                min(
                    (block_index + 1) * TARGET_JITTER_BLOCK_SIZE,
                    replicates,
                ),
            )
        )

    def _shared_root(self) -> Path:
        profile = self.provider.configuration.individualized_seed_target
        role = (
            "addon"
            if self.final_model.endpoint.model_family.startswith("addon_")
            else "reference"
        )
        reference_tau = "not_applicable"
        if role == "addon":
            dependency = self.reference_dependency
            assert dependency is not None
            reference = dependency.reference_record
            if not isinstance(reference, SourceRecord) or reference.selected_tau is None:
                raise StudyTargetJitterProviderError(
                    "add-on target jitter reference has no selected tau"
                )
            reference_tau = _token(reference.selected_tau)
        subjects = self.endpoint_input.included_subject_ids
        chunks = tuple(
            "--".join(subjects[start : start + 8])
            for start in range(0, len(subjects), 8)
        )
        root = (
            self.provider.configuration.workflow.output.root
            / "shared"
            / "jitter_exposures"
            / "individualized_seed_target"
            / role
            / f"reference_tau_{reference_tau}"
            / f"fwhm_{_token(self.settings.translation_fwhm_mm)}mm"
            / f"seed_{self.settings.seed}"
            / (
                "support_count_"
                f"{profile.target_exposure.activated_fiber_count_min}"
            )
            / (
                "support_fraction_"
                f"{_token(profile.target_exposure.activated_fiber_fraction_min)}"
            )
            / "cohort"
        )
        for chunk in chunks:
            root /= chunk
        return root

    def _shared_leaf(self, replicate_index: int) -> Path:
        start = (
            replicate_index // TARGET_JITTER_BLOCK_SIZE
        ) * TARGET_JITTER_BLOCK_SIZE
        stop = min(
            start + TARGET_JITTER_BLOCK_SIZE,
            self.settings.replicates,
        )
        return self._shared_root() / f"block_{start:04d}_{stop:04d}"

    def _expected_block(
        self,
        leaf: Path,
    ) -> tuple[int, int, np.ndarray, np.ndarray]:
        try:
            start_text, stop_text = leaf.name.removeprefix("block_").split(
                "_",
                maxsplit=1,
            )
            start = int(start_text)
            stop = int(stop_text)
        except (TypeError, ValueError) as exc:
            raise StudyTargetJitterProviderError(
                f"target jitter block path is invalid: {leaf}"
            ) from exc
        indices = np.arange(start, stop, dtype=np.int64)
        seeds = np.asarray(
            [
                np.random.SeedSequence(
                    [self.settings.seed, int(index)]
                ).generate_state(1, dtype=np.uint64)[0]
                for index in indices
            ],
            dtype=np.uint64,
        )
        return start, stop, indices, seeds

    def _load_array(
        self,
        leaf: Path,
        filename: str,
        *,
        shape: tuple[int, ...],
        dtype: np.dtype,
    ) -> np.ndarray:
        try:
            value = np.load(
                leaf / filename,
                allow_pickle=False,
                mmap_mode="r",
            )
        except (OSError, ValueError) as exc:
            raise StudyTargetJitterProviderError(
                f"target jitter block array cannot be read: {leaf / filename}"
            ) from exc
        if value.shape != shape or value.dtype != dtype:
            raise StudyTargetJitterProviderError(
                f"target jitter block array metadata is invalid: "
                f"{leaf / filename}"
            )
        value.flags.writeable = False
        return value

    def _load_shared(self, leaf: Path) -> TargetJitterBurdenBlock:
        start, stop, expected_indices, expected_seeds = self._expected_block(
            leaf
        )
        replicate_count = stop - start
        tau_count = self.original_request.tau_axis.count
        subject_count = self.original_request.subject_axis.count
        target_count = self.original_request.target_axis.count
        patient_shape = (
            replicate_count,
            tau_count,
            subject_count,
            target_count,
        )
        indices = self._load_array(
            leaf,
            "replicate_indices.npy",
            shape=(replicate_count,),
            dtype=np.dtype(np.int64),
        )
        seeds = self._load_array(
            leaf,
            "replicate_seeds.npy",
            shape=(replicate_count,),
            dtype=np.dtype(np.uint64),
        )
        if not np.array_equal(indices, expected_indices) or not np.array_equal(
            seeds,
            expected_seeds,
        ):
            raise StudyTargetJitterProviderError(
                f"shared target jitter schedule differs from the request: {leaf}"
            )
        burdens = self._load_array(
            leaf,
            "patient_burdens.npy",
            shape=patient_shape,
            dtype=np.dtype(np.float32),
        )
        support = self._load_array(
            leaf,
            "patient_support.npy",
            shape=patient_shape,
            dtype=np.dtype(np.bool_),
        )
        reference_burdens = None
        component_burdens = None
        component_support = None
        if self.final_model.endpoint.model_family.startswith("addon_"):
            reference_burdens = self._load_array(
                leaf,
                "reference_condition_patient_burdens.npy",
                shape=patient_shape,
                dtype=np.dtype(np.float32),
            )
            component_burdens = self._load_array(
                leaf,
                "addon_reference_component_patient_burdens.npy",
                shape=patient_shape,
                dtype=np.dtype(np.float32),
            )
            component_support = self._load_array(
                leaf,
                "addon_reference_component_patient_support.npy",
                shape=patient_shape,
                dtype=np.dtype(np.bool_),
            )
        return TargetJitterBurdenBlock(
            replicate_indices=indices,
            replicate_seeds=seeds,
            patient_burdens=burdens,
            patient_support=support,
            reference_condition_patient_burdens=reference_burdens,
            addon_reference_component_patient_burdens=component_burdens,
            addon_reference_component_patient_support=component_support,
        )

    def _publish_shared(self, leaf: Path) -> TargetJitterBurdenBlock:
        start, stop, _indices, _seeds = self._expected_block(leaf)
        block = self.provider.build_target_jitter_burden_block(
            endpoint_input=self.endpoint_input,
            reference_dependency=self.reference_dependency,
            replicate_start=start,
            replicate_stop=stop,
            root_seed=self.settings.seed,
            translation_fwhm_mm=self.settings.translation_fwhm_mm,
        )
        leaf.mkdir(parents=True, exist_ok=True)
        arrays = {
            "replicate_indices.npy": block.replicate_indices,
            "replicate_seeds.npy": block.replicate_seeds,
            "patient_burdens.npy": block.patient_burdens,
            "patient_support.npy": block.patient_support,
        }
        optional = {
            "reference_condition_patient_burdens.npy": (
                block.reference_condition_patient_burdens
            ),
            "addon_reference_component_patient_burdens.npy": (
                block.addon_reference_component_patient_burdens
            ),
            "addon_reference_component_patient_support.npy": (
                block.addon_reference_component_patient_support
            ),
        }
        arrays.update(
            {
                filename: value
                for filename, value in optional.items()
                if value is not None
            }
        )
        for filename, value in arrays.items():
            _atomic_npy(leaf / filename, value)
        _atomic_json(
            leaf / "metadata.json",
            {
                "kind": "individualized_target_jitter_block",
                "replicate_start": start,
                "replicate_stop": stop,
                "subject_ids": list(
                    self.endpoint_input.included_subject_ids
                ),
                "seed": self.settings.seed,
                "translation_fwhm_mm": (
                    self.settings.translation_fwhm_mm
                ),
            },
        )
        _atomic_json(leaf / "complete.json", {"status": "complete"})
        return self._load_shared(leaf)

    def _shared_block(
        self,
        *,
        replicate_index: int,
    ) -> TargetJitterBurdenBlock:
        leaf = self._shared_leaf(replicate_index)
        if self._loaded_leaf == leaf and self._loaded_block is not None:
            return self._loaded_block
        if (leaf / "complete.json").is_file():
            block = self._load_shared(leaf)
            self._loaded_leaf = leaf
            self._loaded_block = block
            return block
        lock_root = leaf.parent / ".locks"
        lock_root.mkdir(parents=True, exist_ok=True)
        lock_path = lock_root / f"{leaf.name}.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if (leaf / "complete.json").is_file():
                block = self._load_shared(leaf)
            else:
                block = self._publish_shared(leaf)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        self._loaded_leaf = leaf
        self._loaded_block = block
        return block

    def _delta(
        self,
        *,
        reference_condition_burdens: ArtifactRef,
        addon_reference_component_burdens: ArtifactRef,
        addon_reference_component_support: ArtifactRef,
        replicate_index: int,
    ) -> DeltaReferenceBundle | None:
        dependency = self.reference_dependency
        reference_input = self.reference_input
        if dependency is None or reference_input is None:
            return None
        reference = dependency.reference_record
        if not isinstance(reference, SourceRecord):
            raise StudyTargetJitterProviderError(
                "target jitter reference dependency is not a SourceRecord"
            )
        if (
            self.endpoint_input.subject_axis is None
            or reference_input.subject_axis is None
        ):
            raise StudyTargetJitterProviderError(
                "target jitter DeltaReferenceScore inputs are incomplete"
            )
        profile = self.provider.configuration.individualized_seed_target
        return build_delta_reference_individualized_target(
            matched_reference_endpoint_id=(
                dependency.matched_reference_endpoint_id
            ),
            reference_source=reference,
            reference_condition_burdens=reference_condition_burdens,
            addon_reference_component_burdens=(
                addon_reference_component_burdens
            ),
            addon_reference_component_support=(
                addon_reference_component_support
            ),
            subject_axis=self.endpoint_input.subject_axis,
            reference_subject_axis=reference_input.subject_axis,
            target_axis=self.original_request.target_axis,
            tau_axis=self.original_request.tau_axis,
            tau_values=profile.source.tau_values,
            addon_subject_ids=self.endpoint_input.included_subject_ids,
            reference_subject_ids=reference_input.included_subject_ids,
            support_profile=profile.delta_reference_support,
            publisher=_ArenaPublisher(
                self._arena,
                f"target_jitter_{replicate_index:04d}",
            ),
            artifact_store=self.array_provider,
        )

    def _patient_view(
        self,
        filename: str,
        value: np.ndarray,
        *,
        kind: str,
        units: str,
    ) -> ArtifactRef:
        return self._arena.array(
            filename,
            value,
            kind=kind,
            axes=(
                self.original_request.tau_axis,
                self.original_request.subject_axis,
                self.original_request.target_axis,
            ),
            units=units,
            space=None,
        )

    def build_replicate(
        self,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> TargetJitterReplicateEvidence:
        block = self._shared_block(
            replicate_index=replicate_index,
        )
        local = replicate_index - int(block.replicate_indices[0])
        if (
            local < 0
            or local >= block.replicate_indices.size
            or int(block.replicate_indices[local]) != replicate_index
            or int(block.replicate_seeds[local]) != replicate_seed
        ):
            raise StudyTargetJitterProviderError(
                "target jitter block returned the wrong replicate"
            )
        self._arena.clear()
        patient_burdens = self._patient_view(
            f"replicate_{replicate_index:04d}_patient_burdens.npy",
            block.patient_burdens[local],
            kind="individualized_patient_target_burdens",
            units="V/m",
        )
        patient_support = self._patient_view(
            f"replicate_{replicate_index:04d}_patient_support.npy",
            block.patient_support[local],
            kind="individualized_patient_target_support",
            units="binary",
        )
        delta = None
        branch = self.final_model.final_key.final_branch
        if branch == "delta_reference_adjusted":
            if (
                block.reference_condition_patient_burdens is None
                or block.addon_reference_component_patient_burdens is None
                or block.addon_reference_component_patient_support is None
            ):
                raise StudyTargetJitterProviderError(
                    "adjusted target jitter block lacks DeltaReferenceScore arrays"
                )
            delta = self._delta(
                reference_condition_burdens=self._patient_view(
                    (
                        f"replicate_{replicate_index:04d}_"
                        "reference_condition_patient_burdens.npy"
                    ),
                    block.reference_condition_patient_burdens[local],
                    kind="individualized_reference_condition_patient_burdens",
                    units="V/m",
                ),
                addon_reference_component_burdens=self._patient_view(
                    (
                        f"replicate_{replicate_index:04d}_"
                        "addon_reference_component_patient_burdens.npy"
                    ),
                    block.addon_reference_component_patient_burdens[local],
                    kind=(
                        "individualized_addon_reference_component_patient_burdens"
                    ),
                    units="V/m",
                ),
                addon_reference_component_support=self._patient_view(
                    (
                        f"replicate_{replicate_index:04d}_"
                        "addon_reference_component_patient_support.npy"
                    ),
                    block.addon_reference_component_patient_support[local],
                    kind=(
                        "individualized_addon_reference_component_patient_support"
                    ),
                    units="binary",
                ),
                replicate_index=replicate_index,
            )
        if (
            branch == "delta_reference_adjusted"
            and (delta is None or not delta.valid)
        ):
            return TargetJitterReplicateEvidence(
                observed_request=None,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                technical_status="not_computable",
                reason="translated_delta_reference_support_is_invalid",
            )
        nuisance_inputs = self.original_request.nuisance_inputs
        if delta is not None:
            assert delta.full_scores is not None and delta.fold_scores is not None
            nuisance_inputs = (delta.full_scores, delta.fold_scores)
        observed = replace(
            self.original_request,
            patient_burdens=patient_burdens,
            patient_support=patient_support,
            nuisance_inputs=nuisance_inputs,
        )
        return TargetJitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
        )


__all__ = [
    "StudyTargetJitterProviderError",
    "StudyTargetJitterReplicateProvider",
    "TARGET_JITTER_BLOCK_SIZE",
]
