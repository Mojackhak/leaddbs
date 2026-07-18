"""Conditional final in-sample inference on the full prepared parent axis."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    AxisRef,
    FormalResult,
    InSampleRequest,
    NormativeFiberScoreSettings,
    canonical_hash,
)
from ..direct_voxel.kernel import continuous_mean_score
from ..normative_fiber.coverage import candidate_mask, coverage_counts
from ..normative_fiber.scoring import (
    _score_signed_fibers_prevalidated,
    score_support_fields,
)
from ..nuisance import ADJUSTED_BRANCH
from ..protocols import ArtifactPublisher
from ..statistics import (
    average_rank,
    benefit_oriented_weights,
    linear_prediction,
    rank_columns,
    safe_correlation,
)
from .common import (
    FormalBackendError,
    FormalBackendInputError,
    canonical_fiber_ids,
    finite_exposure,
    finite_vector,
    json_safe,
    materialize_array,
    plus_one_two_sided,
    residual_permutation_schedule,
)


CONDITIONING_LABEL = (
    "conditional_on_selected_tau_coverage_branch_and_candidate_axis"
)
RNG_ALGORITHM = "numpy_pcg64"
RNG_CONTRACT_VERSION = 1


@dataclass(frozen=True, slots=True)
class _WeightOperator:
    """Outcome-independent full-sample partial-Spearman operator."""

    nuisance: np.ndarray
    ranked_nuisance_design: np.ndarray
    standardized_exposure_residual: np.ndarray
    estimable_features: np.ndarray


@dataclass(frozen=True, slots=True)
class _Fit:
    predictions: np.ndarray
    baseline_predictions: np.ndarray
    scores: np.ndarray
    weights: np.ndarray
    support: dict[str, object]


def _weight_operator(exposure: np.ndarray, nuisance: np.ndarray) -> _WeightOperator:
    ranked_nuisance = rank_columns(nuisance)
    design = np.column_stack([np.ones(exposure.shape[0]), ranked_nuisance])
    if (
        exposure.shape[0] <= design.shape[1]
        or np.linalg.matrix_rank(design) != design.shape[1]
    ):
        raise FormalBackendInputError(
            "in-sample ranked nuisance design is not estimable"
        )
    ranked_exposure = rank_columns(exposure)
    coefficients, *_ = np.linalg.lstsq(design, ranked_exposure, rcond=None)
    residual = ranked_exposure - design @ coefficients
    residual -= np.mean(residual, axis=0)
    denominator = np.sqrt(np.sum(residual**2, axis=0))
    estimable = np.isfinite(denominator) & (denominator > 0.0)
    if not np.any(estimable):
        raise FormalBackendInputError(
            "in-sample candidate exposure has no estimable features"
        )
    standardized = np.zeros(residual.shape, dtype=np.float64)
    standardized[:, estimable] = residual[:, estimable] / denominator[estimable]
    return _WeightOperator(
        nuisance=np.asarray(nuisance, dtype=np.float64),
        ranked_nuisance_design=design,
        standardized_exposure_residual=standardized,
        estimable_features=estimable,
    )


def _weights(operator: _WeightOperator, outcome: np.ndarray, direction: str) -> np.ndarray:
    ranked = average_rank(outcome)
    coefficients, *_ = np.linalg.lstsq(
        operator.ranked_nuisance_design,
        ranked,
        rcond=None,
    )
    residual = ranked - operator.ranked_nuisance_design @ coefficients
    residual -= np.mean(residual)
    denominator = float(np.sqrt(np.sum(residual**2)))
    weights = np.full(
        operator.estimable_features.shape,
        np.nan,
        dtype=np.float64,
    )
    if not math.isfinite(denominator) or denominator <= 0.0:
        return weights
    normalized = residual / denominator
    weights[operator.estimable_features] = (
        operator.standardized_exposure_residual[:, operator.estimable_features].T
        @ normalized
    )
    return benefit_oriented_weights(weights, direction)


def _nuisance(
    request: InSampleRequest,
    baseline: np.ndarray,
    delta_full: np.ndarray | None,
) -> np.ndarray:
    columns = [np.asarray(baseline, dtype=np.float64)]
    if request.final_model.final_key.final_branch == ADJUSTED_BRANCH:
        if delta_full is None:
            raise FormalBackendInputError(
                "adjusted in-sample inference lacks DeltaReferenceScore"
            )
        center = float(np.mean(delta_full))
        scale = float(np.std(delta_full, ddof=0))
        if not math.isfinite(center) or not math.isfinite(scale) or scale <= 0.0:
            raise FormalBackendInputError(
                "in-sample DeltaReferenceScore cannot be standardized"
            )
        columns.append((delta_full - center) / scale)
    nuisance = np.column_stack(columns)
    design = np.column_stack([np.ones(nuisance.shape[0]), nuisance])
    if (
        nuisance.shape[0] <= design.shape[1]
        or np.linalg.matrix_rank(design) != design.shape[1]
    ):
        raise FormalBackendInputError(
            "in-sample nuisance-only design is not estimable"
        )
    return nuisance


def _candidate(
    request: InSampleRequest,
    exposure: np.ndarray,
    feature_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    final_key = request.final_model.final_key
    tau = float(final_key.selected_tau)
    coverage = int(final_key.selected_coverage)
    mask = candidate_mask(coverage_counts(exposure, tau), coverage)
    indices = np.flatnonzero(mask).astype(np.int64)
    if indices.size == 0:
        raise FormalBackendInputError(
            "final in-sample source has no full-sample candidate features"
        )
    if request.final_model.endpoint.model_family.endswith("voxel"):
        minimum = request.hard_computability.n_features_full_min
        if minimum is None or indices.size < minimum:
            raise FormalBackendInputError(
                "final in-sample voxel source fails its full-sample feature minimum"
            )
    return indices, np.asarray(exposure[:, indices]), feature_ids[indices]


def _fit(
    request: InSampleRequest,
    outcome: np.ndarray,
    candidate_exposure: np.ndarray,
    candidate_ids: np.ndarray,
    operator: _WeightOperator,
) -> _Fit:
    weights = _weights(operator, outcome, request.outcome_direction)
    valid = np.isfinite(weights)
    support: dict[str, object]
    if request.final_model.endpoint.model_family.endswith("fiber"):
        settings = request.fiber_score_settings
        if not isinstance(settings, NormativeFiberScoreSettings):
            raise FormalBackendInputError(
                "normative-fiber in-sample score settings are missing"
            )
        score = _score_signed_fibers_prevalidated(
            candidate_exposure,
            weights,
            candidate_ids,
            settings,
            candidate_mask=np.ones(candidate_ids.size, dtype=bool),
            chunk_size=8_192,
        )
        scores = np.asarray(score.net_score, dtype=np.float64)
        support = score_support_fields(score, settings)
        usable = score.fiber_score_support_status != "absent_no_valid_signed_fibers"
    else:
        usable = bool(np.any(valid))
        scores = (
            continuous_mean_score(candidate_exposure, weights, valid)
            if usable
            else np.full(outcome.shape, np.nan, dtype=np.float64)
        )
        support = {
            "candidate_feature_count": int(candidate_ids.size),
            "valid_weight_count": int(np.count_nonzero(valid)),
        }
    if (
        not usable
        or not np.all(np.isfinite(scores))
        or float(np.std(scores)) <= 0.0
    ):
        empty = np.full(outcome.shape, np.nan, dtype=np.float64)
        return _Fit(empty, empty.copy(), scores, weights, support)
    predictions, _ = linear_prediction(
        outcome,
        scores,
        operator.nuisance,
        scores,
        operator.nuisance,
    )
    baseline_predictions, _ = linear_prediction(
        outcome,
        None,
        operator.nuisance,
        None,
        operator.nuisance,
    )
    return _Fit(
        np.asarray(predictions, dtype=np.float64),
        np.asarray(baseline_predictions, dtype=np.float64),
        scores,
        weights,
        support,
    )


def _metrics(
    outcome: np.ndarray,
    predictions: np.ndarray,
    baseline_predictions: np.ndarray,
) -> tuple[dict[str, object], np.ndarray]:
    finite = (
        np.isfinite(outcome)
        & np.isfinite(predictions)
        & np.isfinite(baseline_predictions)
    )
    count = int(np.count_nonzero(finite))
    spearman, spearman_p = safe_correlation(
        outcome,
        predictions,
        method="spearman",
    )
    pearson, pearson_p = safe_correlation(
        outcome,
        predictions,
        method="pearson",
    )
    values: dict[str, object] = {
        "in_sample_n_subjects_total": int(outcome.size),
        "in_sample_n_subjects_finite": count,
        "in_sample_predictions_all_finite": bool(count == outcome.size),
        "in_sample_spearman_rho": spearman,
        "in_sample_spearman_nominal_p": spearman_p,
        "in_sample_pearson_r": pearson,
        "in_sample_pearson_nominal_p": pearson_p,
        "in_sample_r2": math.nan,
        "in_sample_relative_r2": math.nan,
        "in_sample_rmse": math.nan,
        "in_sample_mae": math.nan,
        "in_sample_rmse_baseline": math.nan,
        "in_sample_mae_baseline": math.nan,
    }
    if count:
        y = outcome[finite]
        model_error = y - predictions[finite]
        baseline_error = y - baseline_predictions[finite]
        model_sse = float(np.sum(model_error**2))
        baseline_sse = float(np.sum(baseline_error**2))
        total_sse = float(np.sum((y - np.mean(y)) ** 2))
        values.update(
            {
                "in_sample_r2": (
                    1.0 - model_sse / total_sse if total_sse > 0.0 else math.nan
                ),
                "in_sample_relative_r2": (
                    1.0 - model_sse / baseline_sse
                    if baseline_sse > 0.0
                    else math.nan
                ),
                "in_sample_rmse": float(np.sqrt(np.mean(model_error**2))),
                "in_sample_mae": float(np.mean(np.abs(model_error))),
                "in_sample_rmse_baseline": float(
                    np.sqrt(np.mean(baseline_error**2))
                ),
                "in_sample_mae_baseline": float(np.mean(np.abs(baseline_error))),
            }
        )
    return values, finite


def _loocv_metrics(
    request: InSampleRequest,
    artifact_store: ArtifactStore,
    outcome: np.ndarray,
) -> tuple[dict[str, object], np.ndarray, dict[str, Any]]:
    predictions = np.asarray(
        materialize_array(
            request.loocv_predictions,
            name="loocv_predictions",
            expected_axes=(request.subject_axis,),
            expected_units=request.loocv_predictions.units,
            expected_space=request.loocv_predictions.space,
            artifact_store=artifact_store,
        ),
        dtype=np.float64,
    )
    baseline = np.asarray(
        materialize_array(
            request.loocv_baseline_predictions,
            name="loocv_baseline_predictions",
            expected_axes=(request.subject_axis,),
            expected_units=request.loocv_baseline_predictions.units,
            expected_space=request.loocv_baseline_predictions.space,
            artifact_store=artifact_store,
        ),
        dtype=np.float64,
    )
    summary = artifact_store.materialize_document(
        request.loocv_permutation_summary,
        expected_kind="formal_permutation_summary",
    )
    observed = summary.get("observed")
    if not isinstance(observed, dict):
        raise FormalBackendInputError("LOOCV permutation summary lacks observed metrics")
    finite = np.isfinite(outcome) & np.isfinite(predictions) & np.isfinite(baseline)
    finite_count = int(np.count_nonzero(finite))
    if finite_count:
        model_error = outcome[finite] - predictions[finite]
        total_sse = float(
            np.sum((outcome[finite] - np.mean(outcome[finite])) ** 2)
        )
        model_sse = float(np.sum(model_error**2))
        loocv_r2 = 1.0 - model_sse / total_sse if total_sse > 0.0 else math.nan
    else:
        loocv_r2 = math.nan
    values: dict[str, object] = {
        "loocv_n_subjects_total": int(outcome.size),
        "loocv_n_subjects_finite": finite_count,
        "loocv_predictions_all_finite": bool(np.all(finite)),
        "loocv_spearman_rho": observed.get("loocv_spearman_rho"),
        "loocv_spearman_nominal_p": observed.get("loocv_spearman_nominal_p"),
        "loocv_pearson_r": observed.get("loocv_pearson_r"),
        "loocv_pearson_nominal_p": observed.get("loocv_pearson_nominal_p"),
        "loocv_r2": loocv_r2,
        "loocv_q2": observed.get("q2"),
        "loocv_rmse_model": observed.get("rmse_model"),
        "loocv_mae_model": observed.get("mae_model"),
        "loocv_rmse_baseline": observed.get("rmse_baseline"),
        "loocv_mae_baseline": observed.get("mae_baseline"),
        "loocv_permutation_p_plus_one_two_sided": summary.get(
            "p_plus_one_two_sided"
        ),
        "loocv_permutations_requested": summary.get("resamples_requested"),
        "loocv_permutations_finite": summary.get("finite_replicate_count"),
    }
    return values, finite, summary


def _optimism(
    in_sample: dict[str, object],
    loocv: dict[str, object],
    mask_match: bool,
) -> dict[str, float | None]:
    pairs = {
        "spearman_optimism_gap": (
            "in_sample_spearman_rho",
            "loocv_spearman_rho",
            1.0,
        ),
        "pearson_optimism_gap": (
            "in_sample_pearson_r",
            "loocv_pearson_r",
            1.0,
        ),
        "r2_optimism_gap": ("in_sample_r2", "loocv_r2", 1.0),
        "relative_r2_q2_gap": (
            "in_sample_relative_r2",
            "loocv_q2",
            1.0,
        ),
        "rmse_optimism_gap": ("in_sample_rmse", "loocv_rmse_model", -1.0),
        "mae_optimism_gap": ("in_sample_mae", "loocv_mae_model", -1.0),
    }
    output: dict[str, float | None] = {}
    for name, (in_name, cv_name, direction) in pairs.items():
        first = in_sample.get(in_name)
        second = loocv.get(cv_name)
        if (
            not mask_match
            or not isinstance(first, (int, float))
            or not isinstance(second, (int, float))
            or not math.isfinite(float(first))
            or not math.isfinite(float(second))
        ):
            output[name] = None
        elif direction > 0.0:
            output[name] = float(first) - float(second)
        else:
            output[name] = float(second) - float(first)
    return output


class FinalInSampleBackend:
    """Compute and publish one conditional final in-sample permutation result."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore,
    ) -> None:
        self.publisher = publisher
        self.artifact_store = artifact_store

    def run(self, request: InSampleRequest) -> FormalResult:
        if not isinstance(request, InSampleRequest):
            raise FormalBackendInputError("request must be InSampleRequest")
        exposure = finite_exposure(
            materialize_array(
                request.exposure,
                name="exposure",
                expected_axes=(request.subject_axis, request.feature_axis),
                expected_units=request.exposure_units,
                expected_space=request.exposure_space,
                artifact_store=self.artifact_store,
                memory_map=True,
            ),
            request,
        )
        outcome = finite_vector(
            materialize_array(
                request.outcome,
                name="outcome",
                expected_axes=(request.subject_axis,),
                expected_units=request.outcome.units,
                expected_space=request.outcome.space,
                artifact_store=self.artifact_store,
            ),
            "outcome",
            request.subject_axis.count,
        )
        baseline = finite_vector(
            materialize_array(
                request.baseline,
                name="baseline",
                expected_axes=(request.subject_axis,),
                expected_units=request.baseline.units,
                expected_space=request.baseline.space,
                artifact_store=self.artifact_store,
            ),
            "baseline",
            request.subject_axis.count,
        )
        feature_ids = canonical_fiber_ids(
            materialize_array(
                request.feature_ids,
                name="feature_ids",
                expected_axes=(request.feature_axis,),
                expected_units=request.feature_ids.units,
                expected_space=request.feature_ids.space,
                artifact_store=self.artifact_store,
            ),
            request.feature_axis.count,
        )
        delta_full = (
            None
            if request.delta_reference_full is None
            else finite_vector(
                materialize_array(
                    request.delta_reference_full,
                    name="delta_reference_full",
                    expected_axes=(request.subject_axis,),
                    expected_units=request.delta_reference_full.units,
                    expected_space=request.delta_reference_full.space,
                    artifact_store=self.artifact_store,
                ),
                "delta_reference_full",
                request.subject_axis.count,
            )
        )
        nuisance = _nuisance(request, baseline, delta_full)
        candidate_indices, candidate_exposure, candidate_ids = _candidate(
            request,
            exposure,
            feature_ids,
        )
        operator = _weight_operator(candidate_exposure, nuisance)
        observed = _fit(
            request,
            outcome,
            candidate_exposure,
            candidate_ids,
            operator,
        )
        in_sample_metrics, in_sample_mask = _metrics(
            outcome,
            observed.predictions,
            observed.baseline_predictions,
        )
        observed_rho = float(in_sample_metrics["in_sample_spearman_rho"])
        if not math.isfinite(observed_rho):
            raise FormalBackendError(
                "observed final in-sample Spearman rho is not computable"
            )

        schedule = residual_permutation_schedule(
            outcome.size,
            request.resamples,
            request.seed,
        )
        design = np.column_stack([np.ones(outcome.size), nuisance])
        nuisance_beta, *_ = np.linalg.lstsq(design, outcome, rcond=None)
        fitted = design @ nuisance_beta
        residual = outcome - fitted
        null = np.full(request.resamples, np.nan, dtype=np.float64)
        for index in range(request.resamples):
            pseudo_outcome = fitted + residual[schedule[index]]
            pseudo = _fit(
                request,
                pseudo_outcome,
                candidate_exposure,
                candidate_ids,
                operator,
            )
            rho, _ = safe_correlation(
                pseudo_outcome,
                pseudo.predictions,
                method="spearman",
            )
            if math.isfinite(rho):
                null[index] = rho
        p_value = plus_one_two_sided(observed_rho, null)

        loocv, loocv_mask, loocv_summary = _loocv_metrics(
            request,
            self.artifact_store,
            outcome,
        )
        mask_match = bool(np.array_equal(in_sample_mask, loocv_mask))
        gaps = _optimism(in_sample_metrics, loocv, mask_match)

        final_key = request.final_model.final_key
        candidate_id_digest = hashlib.sha256(
            np.ascontiguousarray(candidate_ids, dtype=np.int64).tobytes(order="C")
        ).hexdigest()
        candidate_axis = AxisRef(
            axis_id=(
                f"{request.feature_axis.axis_id}:in-sample-candidate:"
                f"tau-{final_key.selected_tau:g}:coverage-{final_key.selected_coverage}"
            ),
            count=int(candidate_ids.size),
            sha256=canonical_hash(
                {
                    "parent_axis_sha256": request.feature_axis.sha256,
                    "candidate_feature_ids_sha256": candidate_id_digest,
                    "tau": final_key.selected_tau,
                    "coverage": final_key.selected_coverage,
                    "branch": final_key.final_branch,
                }
            ),
        )
        replicate_axis = AxisRef(
            axis_id="formal_in_sample_permutation_replicates",
            count=request.resamples,
            sha256=canonical_hash(
                {
                    "final_model_id": request.final_model.identifier,
                    "resamples": request.resamples,
                    "seed": request.seed,
                    "rng_contract_version": RNG_CONTRACT_VERSION,
                }
            ),
        )
        candidate_artifact = self.publisher.array(
            "in_sample_candidate_feature_ids.npy",
            candidate_ids,
            kind="in_sample_candidate_feature_ids",
            axes=(candidate_axis,),
            units=None,
            space=request.exposure_space,
        )
        candidate_index_artifact = self.publisher.array(
            "in_sample_candidate_parent_indices.npy",
            candidate_indices,
            kind="in_sample_candidate_parent_indices",
            axes=(candidate_axis,),
            units="parent_index",
            space=None,
        )
        weights_artifact = self.publisher.array(
            "in_sample_observed_weights.npy",
            observed.weights,
            kind="in_sample_observed_benefit_oriented_weights",
            axes=(candidate_axis,),
            units="coefficient",
            space=request.exposure_space,
        )
        score_artifact = self.publisher.array(
            "in_sample_observed_scores.npy",
            observed.scores,
            kind="in_sample_observed_spatial_scores",
            axes=(request.subject_axis,),
            units="V/m",
            space=None,
        )
        prediction_artifact = self.publisher.array(
            "in_sample_predictions.npy",
            observed.predictions,
            kind="in_sample_model_predictions",
            axes=(request.subject_axis,),
            units=request.outcome.units,
            space=None,
        )
        baseline_artifact = self.publisher.array(
            "in_sample_baseline_predictions.npy",
            observed.baseline_predictions,
            kind="in_sample_baseline_predictions",
            axes=(request.subject_axis,),
            units=request.outcome.units,
            space=None,
        )
        schedule_artifact = self.publisher.array(
            "in_sample_permutation_schedule.npy",
            schedule,
            kind="formal_permutation_schedule",
            axes=(replicate_axis, request.subject_axis),
            units="subject_index",
            space=None,
        )
        null_artifact = self.publisher.array(
            "in_sample_permutation_null_statistics.npy",
            null,
            kind="in_sample_permutation_null_statistics",
            axes=(replicate_axis,),
            units="spearman_rho",
            space=None,
        )
        parent_schedule_sha = loocv_summary.get("permutation_schedule_sha256")
        schedule_pairing_status = (
            "shared_explicit_schedule"
            if isinstance(parent_schedule_sha, str)
            and parent_schedule_sha == schedule_artifact.sha256
            else "independent_deterministic_schedule"
        )
        finite_permutations = int(np.count_nonzero(np.isfinite(null)))
        in_sample_metrics.update(
            {
                "in_sample_permutation_p_plus_one_two_sided": p_value,
                "in_sample_permutations_requested": request.resamples,
                "in_sample_permutations_finite": finite_permutations,
            }
        )
        status = (
            "completed"
            if finite_permutations == request.resamples
            else "completed_with_nonfinite_replicates"
        )
        summary = {
            "schema_version": "formal_in_sample_summary_v1",
            "endpoint_id": request.final_model.endpoint.identifier,
            "scale_id": request.final_model.endpoint.scale_id,
            "model_family": request.final_model.endpoint.model_family,
            "final_model_id": request.final_model.identifier,
            "selected_tau": final_key.selected_tau,
            "selected_coverage": final_key.selected_coverage,
            "final_branch": final_key.final_branch,
            "conditioning_label": CONDITIONING_LABEL,
            "candidate_axis_id": candidate_axis.axis_id,
            "candidate_axis_sha256": candidate_axis.sha256,
            "candidate_feature_count": candidate_axis.count,
            "candidate_feature_artifact_id": candidate_artifact.identifier,
            "subject_axis_id": request.subject_axis.axis_id,
            "subject_axis_sha256": request.subject_axis.sha256,
            "permutation_schedule_id": schedule_artifact.identifier,
            "permutation_schedule_sha256": schedule_artifact.sha256,
            "schedule_pairing_status": schedule_pairing_status,
            "seed": request.seed,
            "resamples_requested": request.resamples,
            "rng_algorithm": RNG_ALGORITHM,
            "rng_contract_version": RNG_CONTRACT_VERSION,
            "in_sample": in_sample_metrics,
            "loocv": loocv,
            "optimism_gaps": gaps,
            "subject_mask_match": mask_match,
            "support": observed.support,
            "technical_status": status,
        }
        summary_artifact = self.publisher.document(
            "in_sample_summary.json",
            json_safe(summary),
            kind="formal_in_sample_summary",
        )
        return FormalResult(
            final_model_id=request.final_model.identifier,
            resampling_kind="in_sample_permutation",
            technical_status=status,
            artifacts=(
                candidate_artifact,
                candidate_index_artifact,
                weights_artifact,
                score_artifact,
                prediction_artifact,
                baseline_artifact,
                schedule_artifact,
                null_artifact,
                summary_artifact,
            ),
        )


__all__ = [
    "CONDITIONING_LABEL",
    "FinalInSampleBackend",
    "RNG_ALGORITHM",
    "RNG_CONTRACT_VERSION",
]
