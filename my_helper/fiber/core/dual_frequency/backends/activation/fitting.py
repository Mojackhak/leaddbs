"""Fixed-axis endpoint fitting for normative-fiber pPAM sensitivity."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ActivationArtifact,
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    canonical_hash,
)
from ...contracts.requests import ScientificInput
from ..normative_fiber.scoring import (
    FiberScoreResult,
    PrevalidatedFiberScoreWorkspace,
    score_support_fields,
)
from ..nuisance import (
    ADJUSTED_BRANCH,
    NuisancePlan,
    NuisancePlanError,
    build_addon_nuisance_plan,
)
from ..protocols import ArtifactPublisher
from ..statistics import (
    average_rank,
    benefit_oriented_weights,
    linear_prediction,
    rank_columns,
    residualize,
    safe_correlation,
)
from .canonical_mapping import activation_universe
from .ppam import binary_activation, validate_ten_sample_probabilities


class PPAMFittingError(RuntimeError):
    """Raised when a typed pPAM fitting request cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class _WeightOperator:
    train: np.ndarray
    nuisance_train: np.ndarray
    nuisance_test: np.ndarray | None
    ranked_nuisance_train: np.ndarray
    estimable: np.ndarray
    standardized_exposure_residual: np.ndarray


@dataclass(frozen=True, slots=True)
class _LOOCVResult:
    fold_weights: np.ndarray
    fold_scores: np.ndarray
    heldout_scores: np.ndarray
    predictions: np.ndarray
    baseline_predictions: np.ndarray
    fold_support: tuple[dict[str, object], ...]
    finite_weight_counts: np.ndarray
    score_nonconstant_all_folds: bool
    predictions_finite: bool
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class PPAMFitResult:
    """Observed, permutation, and support evidence for one activation fit."""

    status: str
    failure_reasons: tuple[str, ...]
    full_weights: np.ndarray
    fold_weights: np.ndarray
    full_scores: np.ndarray
    fold_scores: np.ndarray
    heldout_scores: np.ndarray
    predictions: np.ndarray
    baseline_predictions: np.ndarray
    full_support: dict[str, object]
    fold_support: tuple[dict[str, object], ...]
    finite_full_weights: int
    finite_fold_weights: np.ndarray
    performance: dict[str, float]
    peak_score_pearson_r: float
    permutation_null: np.ndarray
    permutation_p_plus_one_two_sided: float
    plain_activation_count: np.ndarray
    plain_activation_sum: np.ndarray
    plain_activation_top5: np.ndarray
    plain_model_comparisons: tuple[dict[str, object], ...]


def _finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise PPAMFittingError(f"{name} must be a finite subject vector")
    return array


def _design_valid(covariates: np.ndarray, rows: np.ndarray) -> bool:
    design = np.column_stack([np.ones(rows.size), covariates[rows]])
    return bool(
        rows.size > design.shape[1]
        and np.linalg.matrix_rank(design) == design.shape[1]
    )


def _nuisance_design_valid(nuisance_plan: NuisancePlan) -> bool:
    subjects = np.arange(nuisance_plan.full_covariates.shape[0])
    if not _design_valid(nuisance_plan.full_covariates, subjects):
        return False
    return all(
        _design_valid(
            nuisance_plan.fold_covariates[heldout],
            np.delete(subjects, heldout),
        )
        for heldout in subjects
    )


def _reference_nuisance_plan(baseline: np.ndarray) -> NuisancePlan:
    full = np.asarray(baseline, dtype=np.float64)[:, None]
    folds = np.broadcast_to(
        full,
        (full.shape[0], full.shape[0], 1),
    ).copy()
    plan = NuisancePlan(full_covariates=full, fold_covariates=folds)
    if not _nuisance_design_valid(plan):
        raise NuisancePlanError(
            "invalid_nuisance_design",
            "reference activation nuisance design is rank deficient",
        )
    return plan


def _build_nuisance_plan(
    request: ActivationRequest,
    baseline: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
) -> NuisancePlan:
    if request.final_model.endpoint.model_family.startswith("reference_"):
        if nuisance_inputs:
            raise NuisancePlanError(
                "invalid_nuisance_design",
                "reference activation cannot receive DeltaReferenceScore inputs",
            )
        return _reference_nuisance_plan(baseline)
    branch = request.final_model.final_key.final_branch
    if branch == ADJUSTED_BRANCH:
        return build_addon_nuisance_plan(
            baseline,
            branch,
            delta_full_scores=nuisance_inputs[0],
            delta_fold_scores=nuisance_inputs[1],
        )
    return build_addon_nuisance_plan(baseline, branch)


def _weight_operator(
    binary_exposure: np.ndarray,
    nuisance_covariates: np.ndarray,
    train: np.ndarray,
    test: np.ndarray | None,
) -> _WeightOperator:
    nuisance_train = np.asarray(nuisance_covariates[train], dtype=np.float64)
    ranked_nuisance = rank_columns(nuisance_train)
    ranked_exposure = rank_columns(binary_exposure[train])
    residual = residualize(ranked_exposure, ranked_nuisance)
    denominator = np.sqrt(np.sum(residual * residual, axis=0))
    estimable = (
        np.isfinite(denominator)
        & (denominator > 0.0)
        & np.all(np.isfinite(residual), axis=0)
    )
    standardized = residual[:, estimable] / denominator[estimable]
    return _WeightOperator(
        train=np.asarray(train, dtype=np.int64),
        nuisance_train=nuisance_train,
        nuisance_test=(
            None
            if test is None
            else np.asarray(nuisance_covariates[test], dtype=np.float64)
        ),
        ranked_nuisance_train=ranked_nuisance,
        estimable=estimable,
        standardized_exposure_residual=standardized,
    )


def _weight_operators(
    binary_exposure: np.ndarray,
    nuisance_plan: NuisancePlan,
) -> tuple[_WeightOperator, tuple[_WeightOperator, ...]]:
    subjects = np.arange(binary_exposure.shape[0], dtype=np.int64)
    full = _weight_operator(
        binary_exposure,
        nuisance_plan.full_covariates,
        subjects,
        None,
    )
    folds = tuple(
        _weight_operator(
            binary_exposure,
            nuisance_plan.fold_covariates[heldout],
            np.delete(subjects, heldout),
            np.asarray([heldout], dtype=np.int64),
        )
        for heldout in subjects
    )
    return full, folds


def _weights_for_outcome(
    outcome: np.ndarray,
    operator: _WeightOperator,
    n_features: int,
    outcome_direction: str,
) -> np.ndarray:
    weights = np.full(n_features, np.nan, dtype=np.float32)
    if not np.any(operator.estimable):
        return weights
    ranked_outcome = average_rank(outcome[operator.train])
    residual = residualize(ranked_outcome, operator.ranked_nuisance_train)
    denominator = float(np.sqrt(np.sum(residual * residual)))
    if not np.isfinite(denominator) or denominator <= 0.0:
        return weights
    coefficients = operator.standardized_exposure_residual.T @ (
        residual / denominator
    )
    weights[operator.estimable] = benefit_oriented_weights(
        coefficients,
        outcome_direction,
    ).astype(np.float32)
    return weights


def _prediction_metrics(
    outcome: np.ndarray,
    predictions: np.ndarray,
    baseline_predictions: np.ndarray,
) -> dict[str, float]:
    finite_model = np.isfinite(outcome) & np.isfinite(predictions)
    finite_baseline = np.isfinite(outcome) & np.isfinite(baseline_predictions)
    if np.any(finite_model):
        error = outcome[finite_model] - predictions[finite_model]
        mae_model = float(np.mean(np.abs(error)))
        rmse_model = float(np.sqrt(np.mean(error**2)))
    else:
        mae_model = rmse_model = math.nan
    if np.any(finite_baseline):
        error = outcome[finite_baseline] - baseline_predictions[finite_baseline]
        mae_baseline = float(np.mean(np.abs(error)))
        rmse_baseline = float(np.sqrt(np.mean(error**2)))
    else:
        mae_baseline = rmse_baseline = math.nan
    joint = finite_model & finite_baseline
    q2 = math.nan
    if np.any(joint):
        sse_model = float(np.sum((outcome[joint] - predictions[joint]) ** 2))
        sse_baseline = float(
            np.sum((outcome[joint] - baseline_predictions[joint]) ** 2)
        )
        if sse_baseline > 0.0:
            q2 = 1.0 - sse_model / sse_baseline
    spearman_rho, spearman_p = safe_correlation(
        outcome,
        predictions,
        method="spearman",
    )
    pearson_r, pearson_p = safe_correlation(
        outcome,
        predictions,
        method="pearson",
    )
    return {
        "loocv_spearman_rho": spearman_rho,
        "loocv_spearman_nominal_p": spearman_p,
        "loocv_pearson_r": pearson_r,
        "loocv_pearson_nominal_p": pearson_p,
        "q2": q2,
        "mae_model": mae_model,
        "mae_baseline": mae_baseline,
        "rmse_model": rmse_model,
        "rmse_baseline": rmse_baseline,
    }


def _loocv(
    outcome: np.ndarray,
    binary_exposure: np.ndarray,
    nuisance_plan: NuisancePlan,
    fold_operators: tuple[_WeightOperator, ...],
    request: ActivationRequest,
    score_workspace: PrevalidatedFiberScoreWorkspace,
    *,
    retain_score_metadata: bool,
) -> _LOOCVResult:
    n_subjects, n_features = binary_exposure.shape
    fold_weights = np.full((n_subjects, n_features), np.nan, dtype=np.float32)
    fold_scores = np.zeros((n_subjects, n_subjects), dtype=np.float64)
    heldout_scores = np.zeros(n_subjects, dtype=np.float64)
    predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    baseline_predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    finite_counts = np.zeros(n_subjects, dtype=np.int64)
    support: list[dict[str, object]] = []
    score_nonconstant = True
    candidate = np.ones(n_features, dtype=bool)
    for heldout, operator in enumerate(fold_operators):
        weights = _weights_for_outcome(
            outcome,
            operator,
            n_features,
            request.outcome_direction,
        )
        fold_weights[heldout] = weights
        finite_counts[heldout] = int(np.count_nonzero(np.isfinite(weights)))
        score = (
            score_workspace.score(
                weights,
                request.fiber_score_settings,
                candidate_mask=candidate,
            )
            if retain_score_metadata
            else score_workspace.score_state(
                weights,
                request.fiber_score_settings,
                candidate_mask=candidate,
            )
        )
        fold_scores[heldout] = score.net_score
        heldout_scores[heldout] = score.net_score[heldout]
        support.append(
            score_support_fields(score, request.fiber_score_settings)
            if isinstance(score, FiberScoreResult)
            else {
                "n_positive_valid_fibers": score.n_positive_valid_fibers,
                "n_negative_valid_fibers": score.n_negative_valid_fibers,
                "fiber_score_support_status": score.fiber_score_support_status,
            }
        )
        train_score = score.net_score[operator.train]
        usable_score = bool(
            score.fiber_score_support_status
            != "absent_no_valid_signed_fibers"
            and np.all(np.isfinite(train_score))
            and np.std(train_score) > 0.0
        )
        if not usable_score:
            score_nonconstant = False
        else:
            prediction, _ = linear_prediction(
                outcome[operator.train],
                train_score,
                operator.nuisance_train,
                score.net_score[[heldout]],
                operator.nuisance_test,
            )
            predictions[heldout] = prediction[0]
        baseline_prediction, _ = linear_prediction(
            outcome[operator.train],
            None,
            operator.nuisance_train,
            None,
            operator.nuisance_test,
        )
        baseline_predictions[heldout] = baseline_prediction[0]
    predictions_finite = bool(
        np.all(np.isfinite(predictions))
        and np.all(np.isfinite(baseline_predictions))
    )
    return _LOOCVResult(
        fold_weights=fold_weights,
        fold_scores=fold_scores,
        heldout_scores=heldout_scores,
        predictions=predictions,
        baseline_predictions=baseline_predictions,
        fold_support=tuple(support),
        finite_weight_counts=finite_counts,
        score_nonconstant_all_folds=score_nonconstant,
        predictions_finite=predictions_finite,
        metrics=_prediction_metrics(outcome, predictions, baseline_predictions),
    )


def _freedman_lane_outcomes(
    outcome: np.ndarray,
    nuisance: np.ndarray,
    count: int,
    seed: int,
) -> np.ndarray:
    design = np.column_stack([np.ones(outcome.size), nuisance])
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise PPAMFittingError("Freedman-Lane nuisance design is rank deficient")
    beta, *_ = np.linalg.lstsq(design, outcome, rcond=None)
    fitted = design @ beta
    residuals = outcome - fitted
    generator = np.random.default_rng(seed)
    permutations = np.empty((count, outcome.size), dtype=np.float64)
    for index in range(count):
        permutations[index] = fitted + residuals[generator.permutation(outcome.size)]
    return permutations


def _plain_activation(binary_exposure: np.ndarray) -> tuple[np.ndarray, ...]:
    activated = binary_exposure > 0.0
    count = np.sum(activated, axis=1, dtype=np.int64).astype(np.float64)
    total = np.sum(binary_exposure, axis=1, dtype=np.float64)
    top5 = np.zeros(binary_exposure.shape[0], dtype=np.float64)
    for row in range(binary_exposure.shape[0]):
        values = np.asarray(binary_exposure[row, activated[row]], dtype=np.float64)
        if values.size:
            selected = max(1, int(np.ceil(0.05 * values.size)))
            top5[row] = float(np.mean(np.sort(values)[-selected:]))
    return count, total, top5


def _in_sample_comparison(
    name: str,
    outcome: np.ndarray,
    nuisance: np.ndarray,
    scores: tuple[tuple[str, np.ndarray], ...],
) -> dict[str, object]:
    columns = [np.ones(outcome.size)]
    columns.extend(np.asarray(values, dtype=np.float64) for _label, values in scores)
    columns.extend(nuisance[:, index] for index in range(nuisance.shape[1]))
    design = np.column_stack(columns)
    design_valid = bool(
        outcome.size > design.shape[1]
        and np.all(np.isfinite(design))
        and np.linalg.matrix_rank(design) == design.shape[1]
    )
    payload: dict[str, object] = {
        "model": name,
        "design_valid": design_valid,
    }
    if not design_valid:
        payload["failure_reason"] = "rank_deficient_or_nonfinite_design"
        return payload
    beta, *_ = np.linalg.lstsq(design, outcome, rcond=None)
    prediction = design @ beta
    residual = outcome - prediction
    spearman, _ = safe_correlation(outcome, prediction, method="spearman")
    pearson, _ = safe_correlation(outcome, prediction, method="pearson")
    payload.update(
        {
            "in_sample_spearman_rho": _json_number(spearman),
            "in_sample_pearson_r": _json_number(pearson),
            "in_sample_mae": float(np.mean(np.abs(residual))),
            "in_sample_rmse": float(np.sqrt(np.mean(residual**2))),
            "score_coefficients": {
                label: float(beta[index + 1])
                for index, (label, _values) in enumerate(scores)
            },
        }
    )
    return payload


def _plain_model_comparisons(
    outcome: np.ndarray,
    nuisance: np.ndarray,
    net_score: np.ndarray,
    plain_top5: np.ndarray,
) -> tuple[dict[str, object], ...]:
    return (
        _in_sample_comparison("nuisance_only", outcome, nuisance, ()),
        _in_sample_comparison(
            "plain_oss_activation_top5",
            outcome,
            nuisance,
            (("plain_activation_top5", plain_top5),),
        ),
        _in_sample_comparison(
            "oss_net_score",
            outcome,
            nuisance,
            (("oss_net_score", net_score),),
        ),
        _in_sample_comparison(
            "oss_net_score_plus_plain_top5",
            outcome,
            nuisance,
            (
                ("oss_net_score", net_score),
                ("plain_activation_top5", plain_top5),
            ),
        ),
    )


def fit_ppam_activation(
    request: ActivationRequest,
    probabilities: np.ndarray,
    reference_overlap_mask: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    peak_final_score: np.ndarray,
    fiber_ids: np.ndarray,
    nuisance_inputs: tuple[np.ndarray, ...],
) -> PPAMFitResult:
    """Fit one report-only pPAM sensitivity on a locked final fiber axis."""

    probability = validate_ten_sample_probabilities(probabilities)
    unmasked_binary = binary_activation(probability)
    overlap = np.asarray(reference_overlap_mask)
    if overlap.shape != unmasked_binary.shape or overlap.dtype != np.dtype(bool):
        raise PPAMFittingError(
            "reference_overlap_mask must be boolean on the activation subject-feature axes"
        )
    binary = np.where(overlap, 0.0, unmasked_binary).astype(np.float32, copy=False)
    binary.flags.writeable = False
    n_subjects, n_features = binary.shape
    y = _finite_vector(outcome, "outcome", n_subjects)
    baseline_values = _finite_vector(baseline, "baseline", n_subjects)
    peak = np.asarray(peak_final_score, dtype=np.float64)
    if peak.shape != (n_subjects,):
        raise PPAMFittingError("peak_final_score must be a subject vector")
    ids = activation_universe(fiber_ids)
    if ids.size != n_features:
        raise PPAMFittingError("fiber_ids do not match activation feature axis")
    plan = _build_nuisance_plan(request, baseline_values, nuisance_inputs)
    score_workspace = PrevalidatedFiberScoreWorkspace(binary, ids)
    full_operator, fold_operators = _weight_operators(binary, plan)
    full_weights = _weights_for_outcome(
        y,
        full_operator,
        n_features,
        request.outcome_direction,
    )
    full_score = score_workspace.score(
        full_weights,
        request.fiber_score_settings,
        candidate_mask=np.ones(n_features, dtype=bool),
    )
    observed = _loocv(
        y,
        binary,
        plan,
        fold_operators,
        request,
        score_workspace,
        retain_score_metadata=True,
    )
    finite_full = int(np.count_nonzero(np.isfinite(full_weights)))
    minimum = request.hard_computability.fold_n_features_min
    if minimum is None:
        raise PPAMFittingError("activation fold feature minimum is missing")
    passes_subjects = n_subjects >= request.hard_computability.n_subjects_min
    passes_features = bool(
        observed.finite_weight_counts.size
        and int(np.min(observed.finite_weight_counts)) >= minimum
    )
    signed_support = bool(
        full_score.fiber_score_support_status
        != "absent_no_valid_signed_fibers"
        and all(
            item["fiber_score_support_status"]
            != "absent_no_valid_signed_fibers"
            for item in observed.fold_support
        )
    )
    failures: list[str] = []
    if not np.any(binary):
        failures.append("activation_all_zero")
    if not passes_subjects:
        failures.append("insufficient_subjects")
    if not passes_features:
        failures.append("insufficient_fold_finite_weights")
    if not signed_support:
        failures.append("absent_valid_signed_fibers")
    if (
        not np.all(np.isfinite(full_score.net_score))
        or np.std(full_score.net_score) == 0.0
    ):
        failures.append("full_score_constant_or_nonfinite")
    if not observed.score_nonconstant_all_folds:
        failures.append("fold_score_constant_or_nonfinite")
    if not observed.predictions_finite:
        failures.append("nonfinite_predictions")

    peak_is_valid = bool(np.all(np.isfinite(peak)) and np.std(peak) > 0.0)
    if not peak_is_valid:
        failures.append("peak_final_score_constant_or_nonfinite")

    peak_correlation, _ = safe_correlation(
        full_score.net_score,
        peak,
        method="pearson",
    )
    if peak_is_valid and not np.isfinite(peak_correlation):
        failures.append("nonfinite_peak_score_correlation")
    null = np.full(request.permutation_resamples, np.nan, dtype=np.float64)
    activation_failures = {
        "activation_all_zero",
        "insufficient_fold_finite_weights",
        "absent_valid_signed_fibers",
        "full_score_constant_or_nonfinite",
        "fold_score_constant_or_nonfinite",
    }
    can_permute = not failures
    if can_permute:
        permuted_outcomes = _freedman_lane_outcomes(
            y,
            plan.full_covariates,
            request.permutation_resamples,
            request.seed,
        )
        for index, permuted in enumerate(permuted_outcomes):
            permuted_fit = _loocv(
                permuted,
                binary,
                plan,
                fold_operators,
                request,
                score_workspace,
                retain_score_metadata=False,
            )
            null[index] = permuted_fit.metrics["loocv_spearman_rho"]
        if not np.all(np.isfinite(null)):
            failures.append("permutation_incomplete")

    observed_statistic = observed.metrics["loocv_spearman_rho"]
    if np.isfinite(observed_statistic) and np.all(np.isfinite(null)):
        permutation_p = float(
            (1 + np.sum(np.abs(null) >= abs(observed_statistic)))
            / (null.size + 1)
        )
    else:
        permutation_p = math.nan

    if any(reason in activation_failures for reason in failures):
        status = "failed_activation_degenerate"
    elif failures:
        status = "failed_oss_design_or_prediction"
    elif np.isfinite(peak_correlation) and peak_correlation > 0.0:
        status = "passed_activation_consistent"
    else:
        status = "passed_activation_model_dependent"
    plain_count, plain_sum, plain_top5 = _plain_activation(binary)
    comparisons = _plain_model_comparisons(
        y,
        plan.full_covariates,
        full_score.net_score,
        plain_top5,
    )
    return PPAMFitResult(
        status=status,
        failure_reasons=tuple(failures),
        full_weights=full_weights,
        fold_weights=observed.fold_weights,
        full_scores=np.asarray(full_score.net_score, dtype=np.float64),
        fold_scores=observed.fold_scores,
        heldout_scores=observed.heldout_scores,
        predictions=observed.predictions,
        baseline_predictions=observed.baseline_predictions,
        full_support=score_support_fields(
            full_score,
            request.fiber_score_settings,
        ),
        fold_support=observed.fold_support,
        finite_full_weights=finite_full,
        finite_fold_weights=observed.finite_weight_counts,
        performance=observed.metrics,
        peak_score_pearson_r=peak_correlation,
        permutation_null=null,
        permutation_p_plus_one_two_sided=permutation_p,
        plain_activation_count=plain_count,
        plain_activation_sum=plain_sum,
        plain_activation_top5=plain_top5,
        plain_model_comparisons=comparisons,
    )


def _json_number(value: float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


class PPAMActivationBackend:
    """Materialize, fit, and publish one generic pPAM activation sensitivity."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore or None")
        self.publisher = publisher
        self.artifact_store = artifact_store

    def _array(
        self,
        value: ScientificInput,
        *,
        shape: tuple[int, ...],
        axes: tuple[AxisRef, ...],
        dtype: np.dtype | None = None,
        units: str | None = None,
        space: str | None = None,
    ) -> np.ndarray:
        if isinstance(value, np.ndarray):
            array = np.asarray(value)
        else:
            if self.artifact_store is None:
                raise PPAMFittingError(
                    "ArtifactRef inputs require a configured ArtifactStore"
                )
            array = self.artifact_store.materialize(
                value,
                expected_dtype=(np.dtype(value.dtype) if dtype is None else dtype),
                expected_shape=shape,
                expected_axes=axes,
                expected_units=(value.units if units is None else units),
                expected_space=(value.space if space is None else space),
                mmap_mode="r",
            )
        if array.shape != shape:
            raise PPAMFittingError("materialized activation input shape is invalid")
        return np.asarray(array)

    def _publish_probability(
        self,
        request: ActivationRequest,
        probability: np.ndarray,
    ) -> ArtifactRef:
        if isinstance(request.activation_probability, ArtifactRef):
            return request.activation_probability
        return self.publisher.array(
            "oss_activation_probability.npy",
            probability,
            kind="oss_activation_probability",
            axes=(request.subject_axis, request.feature_axis),
            units="probability",
            space="right_canonical",
        )

    def _failure(
        self,
        request: ActivationRequest,
        probability_ref: ArtifactRef,
        binary_ref: ArtifactRef,
        reason: str,
        detail: str,
    ) -> ActivationArtifact:
        status_ref = self.publisher.document(
            "oss_status.json",
            {
                "schema_version": "dual_frequency_ppam_fit_status_v1",
                "final_model_id": request.final_model.identifier,
                "oss_sensitivity_status": "failed_oss_design_or_prediction",
                "failure_reasons": [reason],
                "detail": detail,
                "reference_overlap_applied": request.reference_overlap_mask is not None,
                "classification_feedback": False,
                "status": "completed_with_technical_failure",
            },
            kind="oss_sensitivity_status",
        )
        return ActivationArtifact(
            final_model_id=request.final_model.identifier,
            feature_axis=request.feature_axis,
            activation_probability=probability_ref,
            binary_exposure=binary_ref,
            artifacts=(status_ref,),
        )

    def run_activation(self, request: ActivationRequest) -> ActivationArtifact:
        if not isinstance(request, ActivationRequest):
            raise TypeError("request must be an ActivationRequest")
        shape = (request.subject_axis.count, request.feature_axis.count)
        probability = validate_ten_sample_probabilities(
            self._array(
                request.activation_probability,
                shape=shape,
                axes=(request.subject_axis, request.feature_axis),
                dtype=np.dtype(np.float32),
                units="probability",
                space="right_canonical",
            )
        )
        outcome = self._array(
            request.outcome,
            shape=(request.subject_axis.count,),
            axes=(request.subject_axis,),
        )
        baseline = self._array(
            request.baseline,
            shape=(request.subject_axis.count,),
            axes=(request.subject_axis,),
        )
        peak_score = self._array(
            request.peak_final_score,
            shape=(request.subject_axis.count,),
            axes=(request.subject_axis,),
        )
        fiber_ids = activation_universe(
            self._array(
                request.feature_ids,
                shape=(request.feature_axis.count,),
                axes=(request.feature_axis,),
                dtype=np.dtype(np.int64),
                units="fiber_id",
                space="right_canonical",
            )
        )
        activation_feature_ids = activation_universe(
            self._array(
                request.activation_feature_ids,
                shape=(request.feature_axis.count,),
                axes=(request.feature_axis,),
                dtype=np.dtype(np.int64),
                units="fiber_id",
                space="right_canonical",
            )
        )
        if not np.array_equal(fiber_ids, activation_feature_ids):
            raise PPAMFittingError(
                "activation matrix feature IDs differ from final.valid_feature_axis IDs"
            )
        if request.reference_overlap_mask is None:
            reference_overlap_mask = np.zeros(shape, dtype=bool)
        else:
            reference_overlap_mask = self._array(
                request.reference_overlap_mask,
                shape=shape,
                axes=(request.subject_axis, request.feature_axis),
                dtype=np.dtype(bool),
                units="binary",
                space="right_canonical",
            )
            if reference_overlap_mask.dtype != np.dtype(bool):
                raise PPAMFittingError(
                    "reference_overlap_mask must materialize as boolean data"
                )
        nuisance_inputs = tuple(
            self._array(
                value,
                shape=(
                    (request.subject_axis.count,)
                    if index == 0
                    else (request.subject_axis.count, request.subject_axis.count)
                ),
                axes=(
                    (request.subject_axis,)
                    if index == 0
                    else (request.subject_axis, request.subject_axis)
                ),
            )
            for index, value in enumerate(request.nuisance_inputs)
        )
        try:
            result = fit_ppam_activation(
                request,
                probability,
                reference_overlap_mask,
                outcome,
                baseline,
                peak_score,
                fiber_ids,
                nuisance_inputs,
            )
        except NuisancePlanError as exc:
            binary = np.where(
                reference_overlap_mask,
                0.0,
                binary_activation(probability),
            ).astype(np.float32, copy=False)
            probability_ref = self._publish_probability(request, probability)
            binary_ref = self.publisher.array(
                "oss_binary_exposure.npy",
                binary,
                kind="oss_binary_activation",
                axes=(request.subject_axis, request.feature_axis),
                units="binary",
                space="right_canonical",
            )
            return self._failure(
                request,
                probability_ref,
                binary_ref,
                exc.status,
                exc.detail,
            )

        binary = np.where(
            reference_overlap_mask,
            0.0,
            binary_activation(probability),
        ).astype(np.float32, copy=False)
        probability_ref = self._publish_probability(request, probability)
        binary_ref = self.publisher.array(
            "oss_binary_exposure.npy",
            binary,
            kind="oss_binary_activation",
            axes=(request.subject_axis, request.feature_axis),
            units="binary",
            space="right_canonical",
        )

        outcome_units = (
            request.outcome.units
            if isinstance(request.outcome, ArtifactRef)
            else None
        )
        artifacts = [
            self.publisher.array(
                "oss_fiber_ids.npy",
                fiber_ids,
                kind="oss_fiber_ids",
                axes=(request.feature_axis,),
                units="fiber_id",
                space="right_canonical",
            ),
            self.publisher.array(
                "oss_full_weights.npy",
                result.full_weights,
                kind="oss_benefit_oriented_fiber_weights",
                axes=(request.feature_axis,),
                units="coefficient",
                space="right_canonical",
            ),
            self.publisher.array(
                "oss_fold_weights.npy",
                result.fold_weights,
                kind="oss_loocv_benefit_oriented_fiber_weights",
                axes=(request.subject_axis, request.feature_axis),
                units="coefficient",
                space="right_canonical",
            ),
            self.publisher.array(
                "oss_full_scores.npy",
                result.full_scores,
                kind="oss_full_net_fiber_scores",
                axes=(request.subject_axis,),
                units="weighted_binary_activation",
                space=None,
            ),
            self.publisher.array(
                "oss_fold_scores.npy",
                result.fold_scores,
                kind="oss_loocv_fold_net_fiber_scores",
                axes=(request.subject_axis, request.subject_axis),
                units="weighted_binary_activation",
                space=None,
            ),
            self.publisher.array(
                "oss_heldout_scores.npy",
                result.heldout_scores,
                kind="oss_loocv_heldout_net_fiber_scores",
                axes=(request.subject_axis,),
                units="weighted_binary_activation",
                space=None,
            ),
            self.publisher.array(
                "oss_loocv_predictions.npy",
                result.predictions,
                kind="oss_loocv_model_predictions",
                axes=(request.subject_axis,),
                units=outcome_units,
                space=None,
            ),
            self.publisher.array(
                "oss_baseline_predictions.npy",
                result.baseline_predictions,
                kind="oss_loocv_baseline_predictions",
                axes=(request.subject_axis,),
                units=outcome_units,
                space=None,
            ),
            self.publisher.array(
                "oss_plain_activation_count.npy",
                result.plain_activation_count,
                kind="oss_plain_activation_count",
                axes=(request.subject_axis,),
                units="fiber_count",
                space=None,
            ),
            self.publisher.array(
                "oss_plain_activation_sum.npy",
                result.plain_activation_sum,
                kind="oss_plain_activation_sum",
                axes=(request.subject_axis,),
                units="binary_activation_sum",
                space=None,
            ),
            self.publisher.array(
                "oss_plain_activation_top5.npy",
                result.plain_activation_top5,
                kind="oss_plain_activation_top5",
                axes=(request.subject_axis,),
                units="binary_activation",
                space=None,
            ),
        ]
        permutation_axis = AxisRef(
            axis_id=f"{request.subject_axis.axis_id}:oss-permutation",
            count=request.permutation_resamples,
            sha256=canonical_hash(
                {
                    "final_model_id": request.final_model.identifier,
                    "count": request.permutation_resamples,
                    "seed": request.seed,
                }
            ),
        )
        artifacts.append(
            self.publisher.array(
                "oss_permutation_null.npy",
                result.permutation_null,
                kind="oss_permutation_null_statistics",
                axes=(permutation_axis,),
                units="loocv_spearman_rho",
                space=None,
            )
        )
        artifacts.append(
            self.publisher.document(
                "oss_fiber_score_support.json",
                {
                    "schema_version": "dual_frequency_ppam_support_v1",
                    "full_sample": result.full_support,
                    "folds": list(result.fold_support),
                },
                kind="oss_fiber_score_support",
            )
        )
        artifacts.append(
            self.publisher.document(
                "oss_permutation_summary.json",
                {
                    "schema_version": "dual_frequency_ppam_permutation_v1",
                    "B": request.permutation_resamples,
                    "seed": request.seed,
                    "observed_loocv_spearman_rho": _json_number(
                        result.performance["loocv_spearman_rho"]
                    ),
                    "p_plus_one_two_sided": _json_number(
                        result.permutation_p_plus_one_two_sided
                    ),
                    "null_finite_count": int(
                        np.count_nonzero(np.isfinite(result.permutation_null))
                    ),
                    "status": (
                        "complete"
                        if np.all(np.isfinite(result.permutation_null))
                        else "not_complete"
                    ),
                },
                kind="oss_permutation_summary",
            )
        )
        artifacts.append(
            self.publisher.document(
                "oss_plain_activation_model_comparison.json",
                {
                    "schema_version": "dual_frequency_ppam_plain_control_v1",
                    "models": list(result.plain_model_comparisons),
                    "interpretation": "burden_or_placement_qc_only",
                    "classification_feedback": False,
                },
                kind="oss_plain_activation_model_comparison",
            )
        )
        status_payload = {
            "schema_version": "dual_frequency_ppam_fit_status_v1",
            "final_model_id": request.final_model.identifier,
            "oss_sensitivity_status": result.status,
            "failure_reasons": list(result.failure_reasons),
            "n_subjects": request.subject_axis.count,
            "n_fixed_axis_fibers": request.feature_axis.count,
            "n_finite_full_sample_weights": result.finite_full_weights,
            "fold_n_finite_weight_fibers_min": int(
                np.min(result.finite_fold_weights)
            ),
            "fold_n_finite_weight_fibers_median": float(
                np.median(result.finite_fold_weights)
            ),
            "fold_n_finite_weight_fibers_max": int(
                np.max(result.finite_fold_weights)
            ),
            "corr_net_score_oss_vs_peak": _json_number(
                result.peak_score_pearson_r
            ),
            "performance": {
                key: _json_number(value)
                for key, value in result.performance.items()
            },
            "permutation_p_plus_one_two_sided": _json_number(
                result.permutation_p_plus_one_two_sided
            ),
            "candidate_axis_rule": "final.valid_feature_axis",
            "candidate_axis_rescanned": False,
            "reference_overlap_applied": request.reference_overlap_mask is not None,
            "classification_feedback": False,
            "status": "completed",
        }
        artifacts.append(
            self.publisher.document(
                "oss_status.json",
                status_payload,
                kind="oss_sensitivity_status",
            )
        )
        return ActivationArtifact(
            final_model_id=request.final_model.identifier,
            feature_axis=request.feature_axis,
            activation_probability=probability_ref,
            binary_exposure=binary_ref,
            artifacts=tuple(artifacts),
        )


__all__ = [
    "PPAMActivationBackend",
    "PPAMFitResult",
    "PPAMFittingError",
    "fit_ppam_activation",
]
