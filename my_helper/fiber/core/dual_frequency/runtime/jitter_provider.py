"""Task-scoped spatial-jitter reconstruction for the production runtime."""

from __future__ import annotations

from dataclasses import replace
import re

import numpy as np

from ..backends.delta_reference import (
    build_delta_reference_fiber,
    build_delta_reference_voxel,
)
from ..backends.protocols import ArtifactPublisher
from ..backends.sensitivity import (
    FinalSensitivityTarget,
    JitterReplicateEvidence,
    SpatialJitterSettings,
    jitter_rebuild_identity,
)
from ..cache import ArtifactStore
from ..contracts import (
    ArtifactRef,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FinalModelRecord,
    NormativeFiberScoreSettings,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SourceRecord,
)
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from .input_provider import JitterTranslationContext, StudyRuntimeInputProvider


_SAFE_PREFIX = re.compile(r"^[a-z0-9_]+$")


class StudyJitterProviderError(RuntimeError):
    """Raised when one production jitter replicate cannot be reconstructed."""


class _PrefixedPublisher:
    """Give every replicate an immutable filename namespace in one task root."""

    def __init__(self, publisher: ArtifactPublisher, prefix: str) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        token = str(prefix).strip()
        if _SAFE_PREFIX.fullmatch(token) is None:
            raise StudyJitterProviderError("jitter artifact prefix is unsafe")
        self._publisher = publisher
        self._prefix = token

    def array(self, filename: str, value: np.ndarray, **metadata: object) -> ArtifactRef:
        return self._publisher.array(
            f"{self._prefix}_{filename}",
            value,
            **metadata,
        )

    def document(self, filename: str, payload: dict[str, object], **metadata: object) -> ArtifactRef:
        return self._publisher.document(
            f"{self._prefix}_{filename}",
            payload,
            **metadata,
        )


def _artifact(record: SourceRecord | SensitiveRecord, kind: str) -> ArtifactRef:
    matches = tuple(item for item in record.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise StudyJitterProviderError(
            f"reference evidence requires exactly one {kind!r} artifact"
        )
    return matches[0]


class StudyJitterReplicateProvider:
    """Rebuild translated exposure, overlap, support, and Delta inputs per replicate."""

    def __init__(
        self,
        *,
        provider: StudyRuntimeInputProvider,
        endpoint_input: EndpointInputRecord,
        reference_input: EndpointInputRecord | None,
        reference_dependency: ReferenceDependencyRecord | None,
        final_model: FinalModelRecord,
        original_delta: DeltaReferenceBundle | None,
        publisher: ArtifactPublisher,
        artifact_store: ArtifactStore,
        settings: SpatialJitterSettings,
    ) -> None:
        if not isinstance(provider, StudyRuntimeInputProvider):
            raise TypeError("provider must be a StudyRuntimeInputProvider")
        if not isinstance(endpoint_input, EndpointInputRecord):
            raise TypeError("endpoint_input must be an EndpointInputRecord")
        if not isinstance(final_model, FinalModelRecord):
            raise TypeError("final_model must be a FinalModelRecord")
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore")
        if not isinstance(settings, SpatialJitterSettings):
            raise TypeError("settings must be SpatialJitterSettings")
        if final_model.endpoint != endpoint_input.endpoint:
            raise StudyJitterProviderError(
                "jitter final and endpoint input identify different endpoints"
            )
        if final_model.final_key is None:
            raise StudyJitterProviderError("jitter requires a realized final key")
        if (
            final_model.final_key.final_branch == "delta_reference_adjusted"
            and (original_delta is None or not original_delta.valid)
        ):
            raise StudyJitterProviderError(
                "adjusted jitter requires the valid original DeltaReferenceScore bundle"
            )
        is_addon = final_model.endpoint.model_family.startswith("addon_")
        if is_addon:
            if not isinstance(reference_input, EndpointInputRecord):
                raise StudyJitterProviderError(
                    "add-on jitter requires matched reference endpoint input"
                )
            if not isinstance(reference_dependency, ReferenceDependencyRecord):
                raise StudyJitterProviderError(
                    "add-on jitter requires a typed reference dependency"
                )
        elif reference_input is not None or reference_dependency is not None:
            raise StudyJitterProviderError(
                "reference jitter cannot receive add-on reference dependencies"
            )
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")

        self.provider = provider
        self.endpoint_input = endpoint_input
        self.reference_input = reference_input
        self.reference_dependency = reference_dependency
        self.final_model = final_model
        self.original_delta = original_delta
        self.publisher = publisher
        self.artifact_store = artifact_store
        self.settings = settings

    def _fiber_score_settings(self) -> NormativeFiberScoreSettings:
        score = self.provider.configuration.normative_fiber.score
        return NormativeFiberScoreSettings(
            sweet_fraction=score.sweet_fraction,
            sour_fraction=score.sour_fraction,
            weighted_peak_fraction=score.weighted_peak_fraction,
            sweet_selected_min_count=score.sweet_selected_min_count,
            sour_selected_min_count=score.sour_selected_min_count,
            weighted_peak_min_count=score.weighted_peak_min_count,
        )

    def _build_delta(
        self,
        prepared: PreparedExposureRecord,
        publisher: ArtifactPublisher,
    ) -> DeltaReferenceBundle | None:
        dependency = self.reference_dependency
        reference_input = self.reference_input
        if dependency is None or reference_input is None:
            return None
        reference = dependency.reference_record
        accepted = (
            isinstance(reference, SourceRecord)
            and reference.source_status in ACCEPTED_SOURCE_STATUSES
        ) or (
            isinstance(reference, SensitiveRecord)
            and reference.cell_computability_status == "computable"
        )
        if not accepted or prepared.delta_reference_input_status != "ready":
            return None
        if (
            self.endpoint_input.subject_axis is None
            or reference_input.subject_axis is None
            or prepared.reference_condition_exposure is None
            or prepared.addon_reference_component_exposure is None
        ):
            raise StudyJitterProviderError(
                "jitter DeltaReferenceScore inputs are incomplete"
            )

        configuration = self.provider.configuration
        if self.final_model.endpoint.model_family == "addon_voxel":
            if not isinstance(reference, SourceRecord):
                raise StudyJitterProviderError(
                    "direct-voxel jitter requires SourceRecord reference evidence"
                )
            return build_delta_reference_voxel(
                matched_reference_endpoint_id=dependency.matched_reference_endpoint_id,
                reference_source=reference,
                selected_feature_indices=_artifact(reference, "selected_feature_indices"),
                full_weights=_artifact(reference, "benefit_oriented_feature_weights"),
                fold_weights=_artifact(
                    reference,
                    "loocv_benefit_oriented_feature_weights",
                ),
                reference_condition_exposure=prepared.reference_condition_exposure,
                addon_reference_component_exposure=(
                    prepared.addon_reference_component_exposure
                ),
                subject_axis=self.endpoint_input.subject_axis,
                reference_subject_axis=reference_input.subject_axis,
                addon_subject_ids=self.endpoint_input.included_subject_ids,
                reference_subject_ids=reference_input.included_subject_ids,
                parent_feature_axis=prepared.feature_axis,
                support_profile=configuration.direct_voxel.delta_reference_support,
                publisher=publisher,
                artifact_store=self.artifact_store,
            )
        if self.final_model.endpoint.model_family == "addon_fiber":
            assert isinstance(reference, (SourceRecord, SensitiveRecord))
            return build_delta_reference_fiber(
                matched_reference_endpoint_id=dependency.matched_reference_endpoint_id,
                matched_reference_connectome_id=prepared.endpoint.connectome_id,
                reference_record=reference,
                parent_fiber_ids=prepared.feature_ids,
                valid_fiber_ids=_artifact(
                    reference,
                    "normative_fiber_valid_union_ids",
                ),
                full_weights=_artifact(reference, "benefit_oriented_fiber_weights"),
                fold_weights=_artifact(
                    reference,
                    "loocv_benefit_oriented_fiber_weights",
                ),
                fold_valid_masks=_artifact(reference, "loocv_valid_fiber_masks"),
                reference_condition_exposure=prepared.reference_condition_exposure,
                addon_reference_component_exposure=(
                    prepared.addon_reference_component_exposure
                ),
                subject_axis=self.endpoint_input.subject_axis,
                reference_subject_axis=reference_input.subject_axis,
                addon_subject_ids=self.endpoint_input.included_subject_ids,
                reference_subject_ids=reference_input.included_subject_ids,
                parent_fiber_axis=prepared.feature_axis,
                fiber_score_settings=self._fiber_score_settings(),
                support_profile=configuration.normative_fiber.delta_reference_support,
                publisher=publisher,
                artifact_store=self.artifact_store,
            )
        raise StudyJitterProviderError("unsupported add-on jitter model family")

    def _selected_indices(self, prepared: PreparedExposureRecord) -> np.ndarray:
        source = self.final_model.selected_source
        if source is None and self.final_model.selected_branch is not None:
            source = self.final_model.selected_branch.source
        if source is None:
            raise StudyJitterProviderError("jitter final lacks a selected source")
        if self.final_model.endpoint.model_family.endswith("voxel"):
            return np.asarray(
                self.provider._materialize(_artifact(source, "selected_feature_indices")),
                dtype=np.int64,
            )
        parent_ids = np.asarray(
            self.provider._materialize(prepared.feature_ids),
            dtype=np.int64,
        )
        selected_ids = np.asarray(
            self.provider._materialize(
                _artifact(source, "normative_fiber_valid_union_ids")
            ),
            dtype=np.int64,
        )
        indices = np.searchsorted(parent_ids, selected_ids)
        if np.any(indices >= parent_ids.size) or not np.array_equal(
            parent_ids[indices],
            selected_ids,
        ):
            raise StudyJitterProviderError(
                "jitter selected fiber IDs are outside the parent feature axis"
            )
        return np.asarray(indices, dtype=np.int64)

    def _selected_overlap(
        self,
        prepared: PreparedExposureRecord,
        publisher: ArtifactPublisher,
    ) -> ArtifactRef:
        if prepared.reference_overlap_mask is None:
            raise StudyJitterProviderError("add-on jitter lacks rebuilt overlap input")
        indices = self._selected_indices(prepared)
        selected_axis = self.final_model.valid_feature_axis.axis
        if indices.shape != (selected_axis.count,):
            raise StudyJitterProviderError(
                "jitter selected overlap indices differ from the final axis"
            )
        parent = np.asarray(
            self.provider._materialize(prepared.reference_overlap_mask),
            dtype=bool,
        )
        return publisher.array(
            "selected_reference_overlap_mask.npy",
            parent[:, indices],
            kind="jitter_selected_reference_overlap_mask",
            axes=(prepared.subject_axis, selected_axis),
            units="binary",
            space=prepared.reference_overlap_mask.space,
        )

    def build_replicate(
        self,
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence:
        if not isinstance(target, FinalSensitivityTarget):
            raise TypeError("target must be a FinalSensitivityTarget")
        if target.final_model != self.final_model:
            raise StudyJitterProviderError("jitter target differs from the bound final")
        prefix = f"jitter_{replicate_index:04d}"
        publisher = _PrefixedPublisher(self.publisher, prefix)
        context = JitterTranslationContext(
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            translation_sigma_mm=self.settings.translation_sigma_mm,
        )
        prepared = self.provider.publish_jitter_prepared_exposure(
            self.endpoint_input,
            self.reference_dependency,
            publisher,
            context,
        )
        branch = self.final_model.final_key.final_branch
        delta = self._build_delta(prepared, publisher)
        support_status = "not_applicable"
        support_qc: tuple[tuple[str, float | int | str | bool], ...] = ()
        if self.final_model.endpoint.model_family.startswith("addon_"):
            if delta is not None:
                support_status = delta.support_status
                support_qc = (
                    ("translation_sigma_mm", self.settings.translation_sigma_mm),
                    ("delta_input_status", delta.input_status),
                    ("delta_bundle_id", delta.identifier),
                )
            else:
                support_qc = (
                    ("translation_sigma_mm", self.settings.translation_sigma_mm),
                    ("delta_input_status", prepared.delta_reference_input_status),
                    ("delta_reason_code", prepared.delta_reference_reason_code),
                )

        if branch == "delta_reference_adjusted" and (delta is None or not delta.valid):
            parent_observed = target.observed_request
        else:
            parent_observed = self.provider.observed_request(
                self.endpoint_input,
                prepared,
                branch=branch,
                delta_reference=delta,
            )
        selected_exposure, selected_feature_ids = self.provider.selected_exposure(
            self.final_model,
            prepared,
            publisher,
        )
        observed = replace(
            parent_observed,
            exposure=selected_exposure,
            feature_axis=self.final_model.valid_feature_axis.axis,
            feature_ids=selected_feature_ids,
        )
        overlap = (
            self._selected_overlap(prepared, publisher)
            if self.final_model.endpoint.model_family.startswith("addon_")
            else None
        )
        delta_identity = None
        if branch == "delta_reference_adjusted" and delta is not None and delta.valid:
            delta_identity = jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap,
                support_status=support_status,
                support_qc=support_qc,
                component="delta_reference",
            )
        return JitterReplicateEvidence(
            observed_request=observed,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=jitter_rebuild_identity(
                target,
                observed_request=observed,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap,
                support_status=support_status,
                support_qc=support_qc,
            ),
            reference_overlap_mask=overlap,
            support_status=support_status,
            support_qc=support_qc,
            delta_rebuild_identity=delta_identity,
        )


__all__ = ["StudyJitterProviderError", "StudyJitterReplicateProvider"]
