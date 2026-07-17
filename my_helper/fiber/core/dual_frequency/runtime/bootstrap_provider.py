"""Task-scoped matched-reference refits for adjusted subject bootstrap."""

from __future__ import annotations

import numpy as np

from ..backends.normative_fiber.scoring import FiberScoreError, score_signed_fibers
from ..backends.protocols import BootstrapNuisanceSampleNotEstimableError
from ..backends.statistics import (
    StatisticsError,
    benefit_oriented_weights,
    partial_spearman_weights_complete,
)
from ..cache import ArtifactStore
from ..catalog import EndpointRecord
from ..config.models import DeltaReferenceSupportProfile
from ..contracts import (
    ArtifactRef,
    BootstrapNuisanceEvidence,
    BootstrapRebuildProvenance,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FormalRequest,
    NormativeFiberScoreSettings,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SourceRecord,
)
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from .input_provider import StudyRuntimeInputProvider


PROVIDER_ID = "study_matched_reference_bootstrap"
PROVIDER_VERSION = "1"


class StudyBootstrapNuisanceProviderError(RuntimeError):
    """Raised when static production inputs cannot define a safe refit provider."""


def _artifact(record: SourceRecord, kind: str) -> ArtifactRef:
    matches = tuple(item for item in record.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise StudyBootstrapNuisanceProviderError(
            f"accepted reference source requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _materialize(store: ArtifactStore, artifact: ArtifactRef) -> np.ndarray:
    if artifact.dtype is None or artifact.shape is None:
        raise StudyBootstrapNuisanceProviderError(
            f"artifact {artifact.kind!r} must contain an array"
        )
    return store.materialize(
        artifact,
        expected_dtype=artifact.dtype,
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
        mmap_mode="r",
    )


def _finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise StudyBootstrapNuisanceProviderError(
            f"{name} must be a finite reference-subject vector"
        )
    return array


def _selected_parent_positions(
    parent_ids: np.ndarray,
    selected_ids: np.ndarray,
) -> np.ndarray:
    parent = np.asarray(parent_ids)
    selected = np.asarray(selected_ids)
    if (
        parent.ndim != 1
        or selected.ndim != 1
        or parent.dtype == object
        or selected.dtype == object
        or not np.issubdtype(parent.dtype, np.integer)
        or not np.issubdtype(selected.dtype, np.integer)
    ):
        raise StudyBootstrapNuisanceProviderError(
            "fiber IDs must be one-dimensional integer arrays"
        )
    parent = np.asarray(parent, dtype=np.int64)
    selected = np.asarray(selected, dtype=np.int64)
    if np.unique(parent).size != parent.size or np.unique(selected).size != selected.size:
        raise StudyBootstrapNuisanceProviderError("fiber IDs must be unique")
    order = np.argsort(parent, kind="stable")
    sorted_parent = parent[order]
    insertion = np.searchsorted(sorted_parent, selected)
    inside = insertion < sorted_parent.size
    matched = np.zeros(selected.size, dtype=bool)
    matched[inside] = sorted_parent[insertion[inside]] == selected[inside]
    if not np.all(matched):
        raise StudyBootstrapNuisanceProviderError(
            "locked valid-union fiber IDs are absent from the parent axis"
        )
    positions = np.asarray(order[insertion], dtype=np.int64)
    if positions.size and np.any(np.diff(positions) <= 0):
        raise StudyBootstrapNuisanceProviderError(
            "locked valid-union fiber IDs do not preserve parent order"
        )
    return positions


def _sample_not_estimable(detail: str) -> BootstrapNuisanceSampleNotEstimableError:
    return BootstrapNuisanceSampleNotEstimableError(detail)


def _fit_reference_operators(
    exposure: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    *,
    tau: float,
    coverage: int,
    outcome_direction: str,
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(exposure, dtype=np.float64)
    y = np.asarray(outcome, dtype=np.float64)
    nuisance = np.asarray(baseline, dtype=np.float64)[:, None]
    if (
        x.ndim != 2
        or y.shape != (x.shape[0],)
        or nuisance.shape != (x.shape[0], 1)
        or not np.all(np.isfinite(x))
        or not np.all(np.isfinite(y))
        or not np.all(np.isfinite(nuisance))
    ):
        raise StudyBootstrapNuisanceProviderError(
            "sampled matched-reference inputs must be finite and axis aligned"
        )
    n_subjects, n_features = x.shape
    all_rows = np.arange(n_subjects, dtype=np.int64)
    active = x >= float(tau)
    counts = np.sum(active, axis=0, dtype=np.int64)

    full_candidate = counts >= int(coverage)
    if not np.any(full_candidate):
        raise _sample_not_estimable(
            "sampled matched reference has no full-sample tau/Coverage support"
        )
    try:
        full_coefficients = partial_spearman_weights_complete(
            y,
            x[:, full_candidate],
            nuisance,
        )
    except StatisticsError as error:
        raise _sample_not_estimable(
            f"sampled matched-reference full fit is not estimable: {error}"
        ) from error
    full_weights = np.full(n_features, np.nan, dtype=np.float64)
    full_weights[full_candidate] = benefit_oriented_weights(
        full_coefficients,
        outcome_direction,
    )
    if not np.any(np.isfinite(full_weights)):
        raise _sample_not_estimable(
            "sampled matched-reference full fit has no finite operator"
        )

    fold_weights = np.full((n_subjects, n_features), np.nan, dtype=np.float64)
    for heldout in range(n_subjects):
        train = np.delete(all_rows, heldout)
        fold_candidate = (counts - active[heldout].astype(np.int64)) >= int(coverage)
        if not np.any(fold_candidate):
            raise _sample_not_estimable(
                f"sampled matched reference has no tau/Coverage support in fold {heldout}"
            )
        try:
            coefficients = partial_spearman_weights_complete(
                y[train],
                x[train][:, fold_candidate],
                nuisance[train],
            )
        except StatisticsError as error:
            raise _sample_not_estimable(
                f"sampled matched-reference fold {heldout} is not estimable: {error}"
            ) from error
        fold_weights[heldout, fold_candidate] = benefit_oriented_weights(
            coefficients,
            outcome_direction,
        )
        if not np.any(np.isfinite(fold_weights[heldout])):
            raise _sample_not_estimable(
                f"sampled matched-reference fold {heldout} has no finite operator"
            )
    return full_weights, fold_weights


def _support_evidence(
    addon_reference_exposure: np.ndarray,
    total_suprathreshold: np.ndarray,
    full_valid: np.ndarray,
    fold_valid: np.ndarray,
    *,
    tau: float,
    coverage: int,
    profile: DeltaReferenceSupportProfile,
    model_family: str,
) -> tuple[str, tuple[tuple[str, float | int | str | bool], ...]]:
    exposure = np.asarray(addon_reference_exposure, dtype=np.float64)
    total = np.asarray(total_suprathreshold, dtype=np.int64)
    if exposure.ndim != 2 or total.shape != (exposure.shape[0],):
        raise StudyBootstrapNuisanceProviderError(
            "sampled support inputs do not share the subject axis"
        )
    if np.any(total <= 0):
        raise _sample_not_estimable(
            "sampled add-on reference component has no suprathreshold support"
        )
    active = exposure >= float(tau)
    full_in = np.sum(active[:, full_valid], axis=1, dtype=np.int64)
    fold_in = np.empty((exposure.shape[0], exposure.shape[0]), dtype=np.int64)
    for heldout in range(exposure.shape[0]):
        fold_in[heldout] = np.sum(
            active[:, fold_valid[heldout]],
            axis=1,
            dtype=np.int64,
        )
    full_out = 1.0 - (full_in / total)
    fold_out = 1.0 - (fold_in / total[None, :])
    all_required = np.concatenate((full_out, fold_out.ravel()))
    if not np.all(np.isfinite(all_required)):
        raise _sample_not_estimable(
            "sampled DeltaReferenceScore support fractions are not finite"
        )

    median_out = float(np.median(full_out))
    invalid_subject_fraction = float(
        np.mean(full_out > profile.invalid.subject_out_support_threshold)
    )
    invalid = bool(
        median_out > profile.invalid.cohort_median_out_support_min_exclusive
        or invalid_subject_fraction
        > profile.invalid.subject_fraction_min_exclusive
        or np.any(
            all_required
            > profile.invalid.individual_out_support_min_exclusive
        )
    )
    if invalid:
        raise _sample_not_estimable(
            "sampled DeltaReferenceScore has invalid extreme out-of-support exposure"
        )
    adequate_subject_fraction = float(
        np.mean(full_out > profile.adequate.subject_out_support_threshold)
    )
    support_status = (
        "adequate"
        if (
            median_out < profile.adequate.cohort_median_out_support_max
            and adequate_subject_fraction < profile.adequate.subject_fraction_max
        )
        else "limited"
    )
    qc: tuple[tuple[str, float | int | str | bool], ...] = (
        ("model_family", model_family),
        ("selected_reference_tau", float(tau)),
        ("selected_reference_coverage", int(coverage)),
        ("full_finite_operator_count", int(np.count_nonzero(full_valid))),
        (
            "fold_finite_operator_count_min",
            int(np.min(np.sum(fold_valid, axis=1))),
        ),
        ("cohort_median_out_support_fraction", median_out),
        ("subject_fraction_over_0p50", float(np.mean(full_out > 0.50))),
        ("subject_fraction_over_0p80", float(np.mean(full_out > 0.80))),
        ("maximum_required_out_support_fraction", float(np.max(all_required))),
    )
    return support_status, qc


class StudyBootstrapNuisanceProvider:
    """Rebuild adjusted DeltaReferenceScore on one locked production task closure."""

    def __init__(
        self,
        runtime_provider: StudyRuntimeInputProvider,
        artifact_store: ArtifactStore,
        request: FormalRequest,
        addon_input: EndpointInputRecord,
        addon_prepared: PreparedExposureRecord,
        reference_input: EndpointInputRecord,
        reference_prepared: PreparedExposureRecord,
        dependency: ReferenceDependencyRecord,
        delta_reference: DeltaReferenceBundle,
    ) -> None:
        if not isinstance(runtime_provider, StudyRuntimeInputProvider):
            raise TypeError("runtime_provider must be a StudyRuntimeInputProvider")
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore")
        if not isinstance(request, FormalRequest):
            raise TypeError("request must be a FormalRequest")
        if request.resampling_kind != "bootstrap":
            raise StudyBootstrapNuisanceProviderError(
                "matched-reference provider requires a bootstrap request"
            )
        final_key = request.final_model.final_key
        if final_key is None or final_key.final_branch != "delta_reference_adjusted":
            raise StudyBootstrapNuisanceProviderError(
                "matched-reference provider requires an adjusted final model"
            )
        if addon_input.endpoint != request.final_model.endpoint:
            raise StudyBootstrapNuisanceProviderError(
                "add-on endpoint input does not match the formal final"
            )
        if (
            addon_input.readiness_status != "ready"
            or addon_input.subject_axis != request.subject_axis
            or addon_prepared.endpoint != addon_input.endpoint
            or addon_prepared.subject_axis != request.subject_axis
        ):
            raise StudyBootstrapNuisanceProviderError(
                "add-on provider inputs are not ready on the formal subject axis"
            )
        if dependency.addon_endpoint != addon_input.endpoint:
            raise StudyBootstrapNuisanceProviderError(
                "reference dependency targets a different add-on endpoint"
            )
        if dependency.dependency_status != "ready":
            raise StudyBootstrapNuisanceProviderError(
                "reference dependency is not ready"
            )
        reference_source = dependency.reference_record
        if not isinstance(reference_source, SourceRecord):
            raise StudyBootstrapNuisanceProviderError(
                "formal adjusted bootstrap requires an accepted reference SourceRecord"
            )
        if reference_source.source_status not in ACCEPTED_SOURCE_STATUSES:
            raise StudyBootstrapNuisanceProviderError(
                "matched reference source is not accepted"
            )
        if (
            reference_source.endpoint.identifier
            != dependency.matched_reference_endpoint_id
            or reference_input.endpoint != reference_source.endpoint
            or reference_prepared.endpoint != reference_source.endpoint
        ):
            raise StudyBootstrapNuisanceProviderError(
                "matched reference records do not share one endpoint identity"
            )
        if (
            reference_input.readiness_status != "ready"
            or reference_input.subject_axis is None
            or reference_input.baseline is None
            or reference_input.outcome is None
            or reference_prepared.subject_axis != reference_input.subject_axis
        ):
            raise StudyBootstrapNuisanceProviderError(
                "matched reference inputs are not scientifically ready"
            )
        expected_reference_family = addon_input.endpoint.model_family.replace(
            "addon_",
            "reference_",
            1,
        )
        if reference_source.endpoint.model_family != expected_reference_family:
            raise StudyBootstrapNuisanceProviderError(
                "matched reference model family differs from the add-on model"
            )
        if (
            reference_source.endpoint.scale_id != addon_input.endpoint.scale_id
            or reference_source.endpoint.connectome_id
            != addon_input.endpoint.connectome_id
        ):
            raise StudyBootstrapNuisanceProviderError(
                "matched reference scale or connectome differs from the add-on endpoint"
            )
        if (
            reference_source.selected_tau is None
            or reference_source.selected_coverage is None
            or reference_source.feature_axis is None
        ):
            raise StudyBootstrapNuisanceProviderError(
                "accepted reference source lacks locked source fields"
            )
        if (
            not delta_reference.valid
            or delta_reference.selected_reference_tau != reference_source.selected_tau
            or delta_reference.selected_reference_coverage
            != reference_source.selected_coverage
            or delta_reference.support_rows is None
        ):
            raise StudyBootstrapNuisanceProviderError(
                "observed DeltaReferenceScore does not match the locked reference source"
            )
        if (
            addon_prepared.reference_condition_exposure is None
            or addon_prepared.addon_reference_component_exposure is None
        ):
            raise StudyBootstrapNuisanceProviderError(
                "adjusted bootstrap requires both reference-component exposures"
            )
        if reference_prepared.feature_axis != addon_prepared.feature_axis:
            raise StudyBootstrapNuisanceProviderError(
                "reference and add-on parent feature axes differ"
            )
        if reference_prepared.feature_ids.sha256 != addon_prepared.feature_ids.sha256:
            raise StudyBootstrapNuisanceProviderError(
                "reference and add-on parent feature IDs differ"
            )

        reference_endpoint = runtime_provider.endpoint(
            dependency.matched_reference_endpoint_id
        )
        if not isinstance(reference_endpoint, EndpointRecord):
            raise StudyBootstrapNuisanceProviderError(
                "runtime provider returned an invalid reference endpoint"
            )
        self._model_family = addon_input.endpoint.model_family
        self._tau = float(reference_source.selected_tau)
        self._coverage = int(reference_source.selected_coverage)
        self._outcome_direction = reference_endpoint.scale_direction
        self._request = request
        self._subject_count = request.subject_axis.count
        self._addon_subject_ids = tuple(addon_input.included_subject_ids)
        reference_positions_by_id = {
            subject_id: index
            for index, subject_id in enumerate(reference_input.included_subject_ids)
        }
        if any(
            subject_id not in reference_positions_by_id
            for subject_id in self._addon_subject_ids
        ):
            raise StudyBootstrapNuisanceProviderError(
                "every add-on subject must occur in the matched reference cohort"
            )
        self._reference_positions = np.asarray(
            [
                reference_positions_by_id[subject_id]
                for subject_id in self._addon_subject_ids
            ],
            dtype=np.int64,
        )

        selected_axis = reference_source.feature_axis.axis
        if self._model_family.endswith("voxel"):
            selected_indices = np.asarray(
                _materialize(
                    artifact_store,
                    _artifact(reference_source, "selected_feature_indices"),
                )
            )
            if (
                selected_indices.shape != (selected_axis.count,)
                or not np.issubdtype(selected_indices.dtype, np.integer)
            ):
                raise StudyBootstrapNuisanceProviderError(
                    "selected voxel indices do not match the locked reference axis"
                )
            positions = np.asarray(selected_indices, dtype=np.int64)
            if positions.size and (
                positions[0] < 0
                or positions[-1] >= reference_prepared.feature_axis.count
                or np.any(np.diff(positions) <= 0)
            ):
                raise StudyBootstrapNuisanceProviderError(
                    "selected voxel indices are outside deterministic parent order"
                )
            self._fiber_ids: np.ndarray | None = None
            self._fiber_settings: NormativeFiberScoreSettings | None = None
            self._support_profile = (
                runtime_provider.configuration.direct_voxel.delta_reference_support
            )
        else:
            selected_ids = np.asarray(
                _materialize(
                    artifact_store,
                    _artifact(reference_source, "normative_fiber_valid_union_ids"),
                )
            )
            if selected_ids.shape != (selected_axis.count,):
                raise StudyBootstrapNuisanceProviderError(
                    "selected fiber IDs do not match the locked reference axis"
                )
            parent_ids = _materialize(artifact_store, reference_prepared.feature_ids)
            positions = _selected_parent_positions(parent_ids, selected_ids)
            self._fiber_ids = np.asarray(selected_ids, dtype=np.int64)
            if not isinstance(request.fiber_score_settings, NormativeFiberScoreSettings):
                raise StudyBootstrapNuisanceProviderError(
                    "normative-fiber adjusted bootstrap lacks score settings"
                )
            self._fiber_settings = request.fiber_score_settings
            self._support_profile = (
                runtime_provider.configuration.normative_fiber.delta_reference_support
            )

        reference_exposure = _materialize(artifact_store, reference_prepared.exposure)
        reference_condition = _materialize(
            artifact_store,
            addon_prepared.reference_condition_exposure,
        )
        addon_reference_component = _materialize(
            artifact_store,
            addon_prepared.addon_reference_component_exposure,
        )
        self._reference_exposure = np.asarray(
            reference_exposure[:, positions],
            dtype=np.float64,
        )
        self._reference_condition_exposure = np.asarray(
            reference_condition[:, positions],
            dtype=np.float64,
        )
        self._addon_reference_component_exposure = np.asarray(
            addon_reference_component[:, positions],
            dtype=np.float64,
        )
        if not (
            np.all(np.isfinite(self._reference_exposure))
            and np.all(np.isfinite(self._reference_condition_exposure))
            and np.all(np.isfinite(self._addon_reference_component_exposure))
        ):
            raise StudyBootstrapNuisanceProviderError(
                "locked selected reference exposures must be finite"
            )

        reference_count = reference_input.subject_axis.count
        self._reference_outcome = _finite_vector(
            _materialize(artifact_store, reference_input.outcome),
            "reference outcome",
            reference_count,
        )
        self._reference_baseline = _finite_vector(
            _materialize(artifact_store, reference_input.baseline),
            "reference baseline",
            reference_count,
        )
        support_rows = np.asarray(
            _materialize(artifact_store, delta_reference.support_rows),
            dtype=np.float64,
        )
        if (
            support_rows.ndim != 2
            or support_rows.shape[0] != self._subject_count
            or support_rows.shape[1] < 1
            or not np.all(np.isfinite(support_rows[:, 0]))
            or np.any(support_rows[:, 0] < 0)
            or not np.all(support_rows[:, 0] == np.floor(support_rows[:, 0]))
        ):
            raise StudyBootstrapNuisanceProviderError(
                "observed support rows lack exact total suprathreshold counts"
            )
        self._total_suprathreshold = np.asarray(
            support_rows[:, 0],
            dtype=np.int64,
        )

    def _delta_scores(
        self,
        reference_condition: np.ndarray,
        addon_reference_component: np.ndarray,
        full_weights: np.ndarray,
        fold_weights: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        full_valid = np.isfinite(full_weights)
        fold_valid = np.isfinite(fold_weights)
        if self._model_family.endswith("voxel"):
            delta = addon_reference_component - reference_condition
            full_scores = np.mean(
                delta[:, full_valid] * full_weights[full_valid][None, :],
                axis=1,
            )
            fold_scores = np.empty(
                (self._subject_count, self._subject_count),
                dtype=np.float64,
            )
            for heldout in range(self._subject_count):
                valid = fold_valid[heldout]
                fold_scores[heldout] = np.mean(
                    delta[:, valid] * fold_weights[heldout, valid][None, :],
                    axis=1,
                )
            return full_scores, fold_scores

        assert self._fiber_ids is not None and self._fiber_settings is not None
        try:
            addon_full = score_signed_fibers(
                addon_reference_component,
                full_weights,
                self._fiber_ids,
                self._fiber_settings,
                candidate_mask=full_valid,
            )
            reference_full = score_signed_fibers(
                reference_condition,
                full_weights,
                self._fiber_ids,
                self._fiber_settings,
                candidate_mask=full_valid,
            )
        except FiberScoreError as error:
            raise _sample_not_estimable(
                f"sampled matched-reference full fiber operator is invalid: {error}"
            ) from error
        if (
            addon_full.fiber_score_support_status
            == "absent_no_valid_signed_fibers"
            or reference_full.fiber_score_support_status
            == "absent_no_valid_signed_fibers"
        ):
            raise _sample_not_estimable(
                "sampled matched-reference full fiber operator has no signed support"
            )
        full_scores = np.asarray(
            addon_full.net_score - reference_full.net_score,
            dtype=np.float64,
        )
        fold_scores = np.empty(
            (self._subject_count, self._subject_count),
            dtype=np.float64,
        )
        for heldout in range(self._subject_count):
            valid = fold_valid[heldout]
            try:
                addon_fold = score_signed_fibers(
                    addon_reference_component,
                    fold_weights[heldout],
                    self._fiber_ids,
                    self._fiber_settings,
                    candidate_mask=valid,
                )
                reference_fold = score_signed_fibers(
                    reference_condition,
                    fold_weights[heldout],
                    self._fiber_ids,
                    self._fiber_settings,
                    candidate_mask=valid,
                )
            except FiberScoreError as error:
                raise _sample_not_estimable(
                    f"sampled matched-reference fiber fold {heldout} is invalid: {error}"
                ) from error
            if (
                addon_fold.fiber_score_support_status
                == "absent_no_valid_signed_fibers"
                or reference_fold.fiber_score_support_status
                == "absent_no_valid_signed_fibers"
            ):
                raise _sample_not_estimable(
                    f"sampled matched-reference fiber fold {heldout} has no signed support"
                )
            fold_scores[heldout] = addon_fold.net_score - reference_fold.net_score
        return full_scores, fold_scores

    def build_bootstrap_nuisance(
        self,
        request: FormalRequest,
        sample_indices: np.ndarray,
    ) -> BootstrapNuisanceEvidence:
        if request != self._request:
            raise StudyBootstrapNuisanceProviderError(
                "bootstrap provider received a different formal request"
            )
        sample = np.asarray(sample_indices)
        if (
            sample.shape != (self._subject_count,)
            or sample.dtype == object
            or not np.issubdtype(sample.dtype, np.integer)
        ):
            raise StudyBootstrapNuisanceProviderError(
                "bootstrap sample must match the formal subject axis"
            )
        sample = np.asarray(sample, dtype=np.int64)
        if np.any((sample < 0) | (sample >= self._subject_count)):
            raise StudyBootstrapNuisanceProviderError(
                "bootstrap sample indices are outside the formal subject axis"
            )
        reference_rows = self._reference_positions[sample]
        sampled_reference_exposure = self._reference_exposure[reference_rows]
        sampled_reference_outcome = self._reference_outcome[reference_rows]
        sampled_reference_baseline = self._reference_baseline[reference_rows]
        full_weights, fold_weights = _fit_reference_operators(
            sampled_reference_exposure,
            sampled_reference_outcome,
            sampled_reference_baseline,
            tau=self._tau,
            coverage=self._coverage,
            outcome_direction=self._outcome_direction,
        )
        reference_condition = self._reference_condition_exposure[sample]
        addon_reference_component = self._addon_reference_component_exposure[sample]
        full_scores, fold_scores = self._delta_scores(
            reference_condition,
            addon_reference_component,
            full_weights,
            fold_weights,
        )
        if not np.all(np.isfinite(full_scores)) or not np.all(np.isfinite(fold_scores)):
            raise _sample_not_estimable(
                "sampled matched-reference DeltaReferenceScore is not finite"
            )
        full_valid = np.isfinite(full_weights)
        fold_valid = np.isfinite(fold_weights)
        support_status, support_qc = _support_evidence(
            addon_reference_component,
            self._total_suprathreshold[sample],
            full_valid,
            fold_valid,
            tau=self._tau,
            coverage=self._coverage,
            profile=self._support_profile,
            model_family=self._model_family,
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
            support_status=support_status,
            support_qc=support_qc,
            rebuild_provenance=provenance,
        )


__all__ = [
    "StudyBootstrapNuisanceProvider",
    "StudyBootstrapNuisanceProviderError",
]
