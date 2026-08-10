"""Matched-reference target refits for adjusted subject bootstrap."""

from __future__ import annotations

import math

import numpy as np

from ..backends.delta_reference import target_delta_support_evidence
from ..backends.individualized_target import (
    apply_target_operator,
    evaluate_target_cell,
)
from ..backends.nuisance import NuisancePlan
from ..backends.protocols import (
    BootstrapNuisanceSampleNotEstimableError,
)
from ..cache import ArtifactStore
from ..contracts import (
    BootstrapNuisanceEvidence,
    BootstrapRebuildProvenance,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FormalRequest,
    PreparedTargetExposureRecord,
    ReferenceDependencyRecord,
    SourceRecord,
)
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from .input_provider import StudyRuntimeInputProvider


PROVIDER_ID = "study_matched_reference_target_bootstrap"
PROVIDER_VERSION = "unversioned"


class StudyTargetBootstrapNuisanceProviderError(RuntimeError):
    """Raised when locked target inputs cannot define bootstrap refits."""


def _artifact(source: SourceRecord, kind: str):
    matches = tuple(item for item in source.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise StudyTargetBootstrapNuisanceProviderError(
            f"reference target source requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _materialize(store: ArtifactStore, artifact) -> np.ndarray:
    return np.asarray(
        store.materialize(
            artifact,
            expected_dtype=artifact.dtype,
            expected_shape=artifact.shape,
            expected_axes=artifact.axis_refs,
            expected_units=artifact.units,
            expected_space=artifact.space,
        )
    )


def _sample_not_estimable(
    detail: str,
) -> BootstrapNuisanceSampleNotEstimableError:
    return BootstrapNuisanceSampleNotEstimableError(detail)


class StudyTargetBootstrapNuisanceProvider:
    """Rebuild target DeltaReferenceScore inside each bootstrap sample."""

    def __init__(
        self,
        runtime_provider: StudyRuntimeInputProvider,
        artifact_store: ArtifactStore,
        request: FormalRequest,
        addon_input: EndpointInputRecord,
        addon_prepared: PreparedTargetExposureRecord,
        reference_input: EndpointInputRecord,
        reference_prepared: PreparedTargetExposureRecord,
        dependency: ReferenceDependencyRecord,
        delta_reference: DeltaReferenceBundle,
    ) -> None:
        if not isinstance(runtime_provider, StudyRuntimeInputProvider):
            raise TypeError("runtime_provider must be StudyRuntimeInputProvider")
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be ArtifactStore")
        if (
            not isinstance(request, FormalRequest)
            or request.resampling_kind != "bootstrap"
            or request.final_model.final_key is None
            or request.final_model.final_key.final_branch
            != "delta_reference_adjusted"
            or request.final_model.endpoint.model_family
            != "addon_individualized"
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap provider requires an adjusted individualized "
                "bootstrap request"
            )
        reference_source = dependency.reference_record
        if (
            not isinstance(reference_source, SourceRecord)
            or reference_source.source_status not in ACCEPTED_SOURCE_STATUSES
            or reference_source.feature_axis is None
            or reference_source.selected_tau is None
            or reference_source.selected_coverage is None
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap requires an accepted reference source"
            )
        if (
            addon_input.endpoint != request.final_model.endpoint
            or addon_prepared.endpoint != addon_input.endpoint
            or addon_input.subject_axis != request.subject_axis
            or addon_prepared.subject_axis != request.subject_axis
            or reference_input.endpoint != reference_source.endpoint
            or reference_prepared.endpoint != reference_source.endpoint
            or reference_input.subject_axis is None
            or reference_input.outcome is None
            or reference_input.baseline is None
            or reference_prepared.subject_axis != reference_input.subject_axis
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap inputs do not share the required endpoint axes"
            )
        if (
            not delta_reference.valid
            or delta_reference.selected_reference_tau
            != reference_source.selected_tau
            or delta_reference.selected_reference_coverage
            != reference_source.selected_coverage
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "observed target DeltaReferenceScore differs from the "
                "locked reference source"
            )
        if (
            addon_prepared.reference_condition_patient_burdens is None
            or addon_prepared.addon_reference_component_patient_burdens is None
            or addon_prepared.addon_reference_component_patient_support is None
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap lacks add-on reference-component inputs"
            )
        selected_axis = reference_source.feature_axis.axis
        indices = np.asarray(
            _materialize(
                artifact_store,
                _artifact(
                    reference_source,
                    "individualized_selected_target_indices",
                ),
            ),
            dtype=np.int64,
        )
        if (
            indices.shape != (selected_axis.count,)
            or (
                indices.size
                and (
                    indices[0] < 0
                    or indices[-1] >= reference_prepared.target_axis.count
                    or np.any(np.diff(indices) <= 0)
                )
            )
            or reference_prepared.target_axis != addon_prepared.target_axis
            or reference_prepared.tau_axis != addon_prepared.tau_axis
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "selected target axis is outside the prepared parent axis"
            )
        tau_values = (
            runtime_provider.configuration.individualized_seed_target.source.tau_values
        )
        try:
            tau_index = tau_values.index(
                float(reference_source.selected_tau)
            )
        except ValueError as exc:
            raise StudyTargetBootstrapNuisanceProviderError(
                "reference tau is outside the prepared target grid"
            ) from exc
        reference_positions = {
            subject_id: index
            for index, subject_id in enumerate(
                reference_input.included_subject_ids
            )
        }
        addon_subject_ids = tuple(addon_input.included_subject_ids)
        if any(
            subject_id not in reference_positions
            for subject_id in addon_subject_ids
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "every add-on subject must occur in the reference cohort"
            )
        self._reference_positions = np.asarray(
            [reference_positions[value] for value in addon_subject_ids],
            dtype=np.int64,
        )
        self._request = request
        self._subject_count = request.subject_axis.count
        self._tau = float(reference_source.selected_tau)
        self._coverage = int(reference_source.selected_coverage)
        self._outcome_direction = runtime_provider.endpoint(
            dependency.matched_reference_endpoint_id
        ).scale_direction
        self._support_profile = (
            runtime_provider.configuration.individualized_seed_target
            .delta_reference_support
        )
        self._reference_burdens = np.asarray(
            _materialize(
                artifact_store,
                reference_prepared.patient_burdens,
            ),
            dtype=np.float64,
        )[tau_index][:, indices]
        self._reference_support = np.asarray(
            _materialize(
                artifact_store,
                reference_prepared.patient_support,
            ),
            dtype=bool,
        )[tau_index][:, indices]
        self._reference_outcome = np.asarray(
            _materialize(artifact_store, reference_input.outcome),
            dtype=np.float64,
        )
        self._reference_baseline = np.asarray(
            _materialize(artifact_store, reference_input.baseline),
            dtype=np.float64,
        )
        self._reference_condition = np.asarray(
            _materialize(
                artifact_store,
                addon_prepared.reference_condition_patient_burdens,
            ),
            dtype=np.float64,
        )[tau_index][:, indices]
        self._addon_component = np.asarray(
            _materialize(
                artifact_store,
                addon_prepared.addon_reference_component_patient_burdens,
            ),
            dtype=np.float64,
        )[tau_index][:, indices]
        component_support_all = np.asarray(
            _materialize(
                artifact_store,
                addon_prepared.addon_reference_component_patient_support,
            ),
            dtype=bool,
        )[tau_index]
        self._component_support_all = component_support_all
        self._component_support_selected = component_support_all[:, indices]

    def build_bootstrap_nuisance(
        self,
        request: FormalRequest,
        sample_indices: np.ndarray,
    ) -> BootstrapNuisanceEvidence:
        if request != self._request:
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap provider received a different request"
            )
        sample = np.asarray(sample_indices)
        if (
            sample.shape != (self._subject_count,)
            or sample.dtype == object
            or not np.issubdtype(sample.dtype, np.integer)
        ):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap sample does not match the subject axis"
            )
        sample = np.asarray(sample, dtype=np.int64)
        if np.any((sample < 0) | (sample >= self._subject_count)):
            raise StudyTargetBootstrapNuisanceProviderError(
                "target bootstrap sample is outside the subject axis"
            )
        reference_rows = self._reference_positions[sample]
        reference_burdens = self._reference_burdens[reference_rows]
        reference_support = self._reference_support[reference_rows]
        reference_outcome = self._reference_outcome[reference_rows]
        reference_baseline = self._reference_baseline[reference_rows]
        nuisance = NuisancePlan(
            full_covariates=reference_baseline[:, None],
            fold_covariates=np.broadcast_to(
                reference_baseline[:, None],
                (
                    self._subject_count,
                    self._subject_count,
                    1,
                ),
            ),
        )
        computation = evaluate_target_cell(
            reference_burdens,
            reference_support,
            reference_outcome,
            nuisance,
            self._outcome_direction,
            self._tau,
            self._coverage,
            request.hard_computability,
            retain_arrays=True,
        )
        arrays = computation.arrays
        if (
            arrays is None
            or not computation.metrics.passes_hard_computability
        ):
            raise _sample_not_estimable(
                "sampled reference target model is not computable"
            )
        reference_condition = self._reference_condition[sample]
        addon_component = self._addon_component[sample]
        full_scores = apply_target_operator(
            addon_component,
            arrays.full_weights,
            arrays.full_centers,
            arrays.full_scales,
            arrays.full_valid_mask,
        ) - apply_target_operator(
            reference_condition,
            arrays.full_weights,
            arrays.full_centers,
            arrays.full_scales,
            arrays.full_valid_mask,
        )
        fold_scores = np.empty(
            (self._subject_count, self._subject_count),
            dtype=np.float64,
        )
        for heldout in range(self._subject_count):
            fold_scores[heldout] = apply_target_operator(
                addon_component,
                arrays.fold_weights[heldout],
                arrays.fold_centers[heldout],
                arrays.fold_scales[heldout],
                arrays.fold_valid_masks[heldout],
            ) - apply_target_operator(
                reference_condition,
                arrays.fold_weights[heldout],
                arrays.fold_centers[heldout],
                arrays.fold_scales[heldout],
                arrays.fold_valid_masks[heldout],
            )
        if (
            not np.all(np.isfinite(full_scores))
            or not np.all(np.isfinite(fold_scores))
        ):
            raise _sample_not_estimable(
                "sampled target DeltaReferenceScore is not finite"
            )
        status, _rows, _labels, support_values = (
            target_delta_support_evidence(
                self._component_support_all[sample],
                self._component_support_selected[sample],
                arrays.full_valid_mask,
                arrays.fold_valid_masks,
                self._support_profile,
            )
        )
        if status not in {"adequate", "limited"}:
            raise _sample_not_estimable(
                f"sampled target DeltaReferenceScore support is {status}"
            )
        support_qc: list[tuple[str, float | int | str | bool]] = [
            ("model_family", "addon_individualized"),
            ("selected_reference_tau", self._tau),
            ("selected_reference_coverage", self._coverage),
        ]
        support_qc.extend(
            (key, value)
            for key, value in support_values.items()
            if value is not None and key not in {"model_family", "support_status"}
        )
        if not all(
            type(value) in {bool, int, float, str}
            and not (
                type(value) is float and not math.isfinite(value)
            )
            for _key, value in support_qc
        ):
            raise _sample_not_estimable(
                "sampled target support evidence is incomplete"
            )
        provenance = BootstrapRebuildProvenance.from_rebuild(
            provider_id=PROVIDER_ID,
            provider_version=PROVIDER_VERSION,
            final_model_id=request.final_model.identifier,
            subject_axis=request.subject_axis,
            sample_indices=sample,
            delta_reference_full_scores=full_scores,
            delta_reference_fold_scores=fold_scores,
        )
        return BootstrapNuisanceEvidence(
            sample_indices=sample,
            delta_reference_full_scores=full_scores,
            delta_reference_fold_scores=fold_scores,
            support_status=status,
            support_qc=tuple(support_qc),
            rebuild_provenance=provenance,
        )


__all__ = [
    "StudyTargetBootstrapNuisanceProvider",
    "StudyTargetBootstrapNuisanceProviderError",
]
