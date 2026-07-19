"""Final-only direct-voxel permutation and subject-bootstrap backend."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ...cache import ArtifactStore
from ...contracts import FormalRequest, FormalResult
from ..direct_voxel.kernel import evaluate_grid_cell_with_nuisance_plan
from ..nuisance import ADJUSTED_BRANCH, NuisancePlan
from ..protocols import ArtifactPublisher, BootstrapNuisanceProvider
from ..statistics import (
    average_rank,
    benefit_oriented_weights,
    linear_prediction,
    partial_spearman_weights,
    rank_columns,
    residualize,
)
from .common import (
    BootstrapComputation,
    BootstrapReplicateNotEstimableError,
    FormalBackendError,
    FormalBackendInputError,
    PermutationBlockComputation,
    PermutationComputation,
    ReplicateBlock,
    ResamplingSchedule,
    StreamingBootstrapAccumulator,
    bootstrap_sample_indices,
    build_bootstrap_nuisance_plan,
    build_fixed_nuisance_plan,
    combine_permutation_blocks,
    finite_exposure,
    finite_vector,
    formal_resampling_schedule,
    freedman_lane_outcomes,
    json_safe,
    materialize_array,
    prediction_metrics,
    resample_axis,
    validate_resampling_schedule,
)


@dataclass(frozen=True, slots=True)
class _FoldOperator:
    heldout: int
    train: np.ndarray
    nuisance_train: np.ndarray
    nuisance_test: np.ndarray
    ranked_nuisance_train: np.ndarray
    score_operator: np.ndarray
    candidate_count: int
    valid_feature_count: int


def _build_fold_operators(
    request: FormalRequest,
    exposure: np.ndarray,
    nuisance_plan: NuisancePlan,
) -> tuple[_FoldOperator, ...]:
    tau = float(request.final_model.final_key.selected_tau)
    coverage = int(request.final_model.final_key.selected_coverage)
    limits = request.hard_computability
    full_minimum = limits.n_features_full_min
    fold_minimum = limits.fold_n_features_min
    if full_minimum is None or fold_minimum is None:
        raise FormalBackendInputError("direct-voxel formal limits are incomplete")
    suprathreshold = np.asarray(exposure >= tau, dtype=bool)
    full_counts = np.count_nonzero(suprathreshold, axis=0).astype(np.int32)
    if int(np.count_nonzero(full_counts >= coverage)) < full_minimum:
        raise FormalBackendInputError(
            "locked direct-voxel final axis fails its full-sample feature minimum"
        )

    direction = -1.0 if request.outcome_direction == "lower" else 1.0
    subjects = np.arange(exposure.shape[0], dtype=np.int64)
    operators: list[_FoldOperator] = []
    for heldout in subjects:
        train = np.delete(subjects, heldout)
        fold_counts = full_counts - suprathreshold[heldout].astype(np.int32)
        candidate = fold_counts >= coverage
        candidate_count = int(np.count_nonzero(candidate))
        if candidate_count < fold_minimum:
            raise FormalBackendInputError(
                f"locked direct-voxel final axis fails fold feature minimum at {heldout}"
            )
        nuisance = nuisance_plan.fold_covariates[heldout]
        nuisance_train = nuisance[train]
        ranked_nuisance = rank_columns(nuisance_train)
        ranked_exposure = rank_columns(exposure[train][:, candidate])
        exposure_residual = residualize(ranked_exposure, ranked_nuisance)
        denominator = np.sqrt(np.sum(exposure_residual**2, axis=0))
        estimable = (
            np.isfinite(denominator)
            & (denominator > 0.0)
            & np.all(np.isfinite(exposure_residual), axis=0)
        )
        if not np.any(estimable):
            raise FormalBackendInputError(
                f"locked direct-voxel final axis has no estimable feature at fold {heldout}"
            )
        candidate_indices = np.flatnonzero(candidate)
        valid_indices = candidate_indices[estimable]
        standardized = exposure_residual[:, estimable] / denominator[estimable]
        score_operator = (
            direction
            * (np.asarray(exposure[:, valid_indices], dtype=np.float64) @ standardized.T)
            / float(valid_indices.size)
        )
        operators.append(
            _FoldOperator(
                heldout=int(heldout),
                train=train,
                nuisance_train=nuisance_train,
                nuisance_test=nuisance[[heldout]],
                ranked_nuisance_train=ranked_nuisance,
                score_operator=score_operator,
                candidate_count=candidate_count,
                valid_feature_count=int(valid_indices.size),
            )
        )
    return tuple(operators)


def _optimized_loocv(
    outcome: np.ndarray,
    operators: tuple[_FoldOperator, ...],
) -> dict[str, float]:
    predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    baseline_predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    for operator in operators:
        ranked_outcome = average_rank(outcome[operator.train])
        residual = residualize(ranked_outcome, operator.ranked_nuisance_train)
        denominator = float(np.sqrt(np.sum(residual**2)))
        if not np.isfinite(denominator) or denominator <= 0.0:
            continue
        scores = operator.score_operator @ (residual / denominator)
        train_scores = scores[operator.train]
        if not np.all(np.isfinite(train_scores)) or np.std(train_scores) <= 0.0:
            continue
        prediction, _ = linear_prediction(
            outcome[operator.train],
            train_scores,
            operator.nuisance_train,
            scores[[operator.heldout]],
            operator.nuisance_test,
        )
        baseline, _ = linear_prediction(
            outcome[operator.train],
            None,
            operator.nuisance_train,
            None,
            operator.nuisance_test,
        )
        predictions[operator.heldout] = prediction[0]
        baseline_predictions[operator.heldout] = baseline[0]
    metrics = prediction_metrics(outcome, predictions, baseline_predictions)
    metrics.update(
        {
            "all_predictions_finite": float(
                np.all(np.isfinite(predictions))
                and np.all(np.isfinite(baseline_predictions))
            ),
            "fold_n_candidate_features_min": float(
                min(operator.candidate_count for operator in operators)
            ),
            "fold_n_valid_features_min": float(
                min(operator.valid_feature_count for operator in operators)
            ),
        }
    )
    return metrics


def _brute_force_loocv(
    request: FormalRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
) -> dict[str, float]:
    computation = evaluate_grid_cell_with_nuisance_plan(
        exposure,
        outcome,
        nuisance_plan,
        request.outcome_direction,
        float(request.final_model.final_key.selected_tau),
        int(request.final_model.final_key.selected_coverage),
        request.hard_computability,
        retain_arrays=False,
    )
    metrics = computation.metrics
    return {
        "loocv_spearman_rho": metrics.loocv_spearman_rho,
        "loocv_spearman_nominal_p": metrics.loocv_spearman_nominal_p,
        "loocv_pearson_r": metrics.loocv_pearson_r,
        "loocv_pearson_nominal_p": metrics.loocv_pearson_nominal_p,
        "mae_model": metrics.mae_model,
        "mae_baseline": metrics.mae_baseline,
        "rmse_model": metrics.rmse_model,
        "rmse_baseline": metrics.rmse_baseline,
        "q2": metrics.q2,
        "all_predictions_finite": float(metrics.all_predictions_finite),
        "fold_n_candidate_features_min": float(metrics.fold_n_features_min),
        "fold_n_valid_features_min": float(metrics.fold_n_features_min),
    }


def _direct_voxel_permutation_block(
    statistic: Callable[[np.ndarray], dict[str, float]],
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    schedule: ResamplingSchedule,
    block: ReplicateBlock,
) -> PermutationBlockComputation:
    permuted = freedman_lane_outcomes(
        outcome,
        nuisance_plan.full_covariates,
        block.count,
        schedule.descriptor.seed,
        schedule=schedule.block_view(block),
    )
    null = np.full(block.count, np.nan, dtype=np.float64)
    for local_index, permuted_outcome in enumerate(permuted):
        metrics = statistic(permuted_outcome)
        rho = float(metrics["loocv_spearman_rho"])
        if bool(metrics["all_predictions_finite"]) and np.isfinite(rho):
            null[local_index] = rho
    return PermutationBlockComputation(
        block=block,
        schedule_sha256=schedule.descriptor.schedule_sha256,
        null_statistics=null,
    )


def compute_direct_voxel_permutation_block(
    request: FormalRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    schedule: ResamplingSchedule,
    block: ReplicateBlock,
    *,
    optimized: bool = True,
) -> PermutationBlockComputation:
    """Compute one fixed direct-voxel permutation interval."""

    if request.resampling_kind != "permutation":
        raise FormalBackendInputError(
            "direct permutation requires resampling_kind='permutation'"
        )
    validate_resampling_schedule(
        schedule,
        schedule_kind="permutation",
        subject_count=outcome.size,
        replicate_count=request.resamples,
        seed=request.seed,
    )
    if block.total != request.resamples:
        raise FormalBackendInputError(
            "direct permutation block does not match request resamples"
        )
    operators = (
        _build_fold_operators(request, exposure, nuisance_plan)
        if optimized
        else None
    )
    statistic = (
        (lambda values: _optimized_loocv(values, operators))
        if operators is not None
        else (
            lambda values: _brute_force_loocv(
                request,
                exposure,
                values,
                nuisance_plan,
            )
        )
    )
    return _direct_voxel_permutation_block(
        statistic,
        outcome,
        nuisance_plan,
        schedule,
        block,
    )


def compute_direct_voxel_permutation(
    request: FormalRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    *,
    optimized: bool = True,
) -> PermutationComputation:
    """Compute a deterministic direct-voxel Freedman-Lane permutation test."""

    if request.resampling_kind != "permutation":
        raise FormalBackendInputError(
            "direct permutation requires resampling_kind='permutation'"
        )
    operators = (
        _build_fold_operators(request, exposure, nuisance_plan)
        if optimized
        else None
    )
    statistic = (
        (lambda values: _optimized_loocv(values, operators))
        if operators is not None
        else (
            lambda values: _brute_force_loocv(
                request,
                exposure,
                values,
                nuisance_plan,
            )
        )
    )
    observed = statistic(outcome)
    if not bool(observed["all_predictions_finite"]) or not np.isfinite(
        observed["loocv_spearman_rho"]
    ):
        raise FormalBackendError(
            "observed final direct-voxel LOOCV statistic is not computable"
        )
    schedule = formal_resampling_schedule(
        "permutation",
        outcome.size,
        request.resamples,
        request.seed,
    )
    blocks = tuple(
        _direct_voxel_permutation_block(
            statistic,
            outcome,
            nuisance_plan,
            schedule,
            block,
        )
        for block in schedule.blocks()
    )
    return combine_permutation_blocks(
        observed,
        schedule,
        blocks,
    )


def compute_direct_voxel_bootstrap(
    request: FormalRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    provider: BootstrapNuisanceProvider | None,
    original_delta_full: np.ndarray | None = None,
    original_delta_folds: np.ndarray | None = None,
) -> BootstrapComputation:
    """Compute deterministic subject-bootstrap weight and support stability."""

    if request.resampling_kind != "bootstrap":
        raise FormalBackendInputError("direct bootstrap requires resampling_kind='bootstrap'")
    adjusted = request.final_model.final_key.final_branch == ADJUSTED_BRANCH
    if adjusted and provider is None:
        raise FormalBackendInputError(
            "adjusted bootstrap requires an injected BootstrapNuisanceProvider"
        )
    build_fixed_nuisance_plan(
        request,
        baseline,
        original_delta_full,
        original_delta_folds,
    )
    tau = float(request.final_model.final_key.selected_tau)
    coverage = int(request.final_model.final_key.selected_coverage)
    full_minimum = request.hard_computability.n_features_full_min
    if full_minimum is None:
        raise FormalBackendInputError("direct bootstrap requires n_features_full_min")

    samples = bootstrap_sample_indices(
        request.subject_axis.count,
        request.resamples,
        request.seed,
    )
    accumulator = StreamingBootstrapAccumulator(
        resamples=request.resamples,
        n_features=request.feature_axis.count,
        track_selection=False,
    )
    for replicate, sample in enumerate(samples):
        sampled_exposure = np.asarray(exposure[sample], dtype=np.float64)
        candidate = np.count_nonzero(sampled_exposure >= tau, axis=0) >= coverage
        replicate_weights = np.full(request.feature_axis.count, np.nan, dtype=np.float64)
        try:
            nuisance_plan, nuisance_evidence = build_bootstrap_nuisance_plan(
                request,
                baseline,
                sample,
                provider,
                original_delta_full=original_delta_full,
                original_delta_folds=original_delta_folds,
            )
        except BootstrapReplicateNotEstimableError as error:
            accumulator.update(
                replicate,
                weights=replicate_weights,
                candidate_mask=candidate,
                support_code=0,
                nuisance_evidence=None,
                nuisance_nonestimability=error.detail,
            )
            continue
        sampled_outcome = outcome[sample]
        if not np.any(candidate):
            accumulator.update(
                replicate,
                weights=replicate_weights,
                candidate_mask=candidate,
                support_code=0,
                nuisance_evidence=nuisance_evidence,
            )
            continue
        coefficients = partial_spearman_weights(
            sampled_outcome,
            sampled_exposure[:, candidate],
            nuisance_plan.full_covariates,
        )
        local_weights = benefit_oriented_weights(
            coefficients,
            request.outcome_direction,
        )
        replicate_weights[candidate] = local_weights
        valid_count = int(np.count_nonzero(np.isfinite(local_weights)))
        support_code = 0
        if valid_count > 0:
            support_code = (
                2
                if int(np.count_nonzero(candidate)) >= full_minimum
                and (
                    nuisance_evidence is None
                    or nuisance_evidence.support_status != "limited"
                )
                else 1
            )
        accumulator.update(
            replicate,
            weights=replicate_weights,
            candidate_mask=candidate,
            support_code=support_code,
            nuisance_evidence=nuisance_evidence,
        )
    return accumulator.finalize()


class DirectVoxelFormalBackend:
    """Publish formal evidence for exactly one realized direct-voxel final."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore | None = None,
        bootstrap_nuisance_provider: BootstrapNuisanceProvider | None = None,
    ) -> None:
        self._publisher = publisher
        self._artifact_store = artifact_store
        self._bootstrap_nuisance_provider = bootstrap_nuisance_provider

    def run_formal(self, request: FormalRequest) -> FormalResult:
        if not isinstance(request, FormalRequest):
            raise FormalBackendInputError("request must be FormalRequest")
        if not request.final_model.endpoint.model_family.endswith("voxel"):
            raise FormalBackendInputError("direct backend requires a direct-voxel final")
        if request.connectome_role != "none":
            raise FormalBackendInputError("direct backend requires connectome_role='none'")
        if (
            request.resampling_kind == "bootstrap"
            and request.final_model.final_key.final_branch == ADJUSTED_BRANCH
            and self._bootstrap_nuisance_provider is None
        ):
            raise FormalBackendInputError(
                "adjusted bootstrap requires an injected BootstrapNuisanceProvider"
            )

        exposure = finite_exposure(
            materialize_array(
                request.exposure,
                name="exposure",
                expected_axes=(request.subject_axis, request.feature_axis),
                expected_units=request.exposure_units,
                expected_space=request.exposure_space,
                artifact_store=self._artifact_store,
                memory_map=True,
            ),
            request,
        )
        outcome = finite_vector(
            materialize_array(
                request.outcome,
                name="outcome",
                expected_axes=(request.subject_axis,),
                expected_units=(request.outcome.units if hasattr(request.outcome, "units") else None),
                expected_space=(request.outcome.space if hasattr(request.outcome, "space") else None),
                artifact_store=self._artifact_store,
            ),
            "outcome",
            request.subject_axis.count,
        )
        baseline = finite_vector(
            materialize_array(
                request.baseline,
                name="baseline",
                expected_axes=(request.subject_axis,),
                expected_units=(request.baseline.units if hasattr(request.baseline, "units") else None),
                expected_space=(request.baseline.space if hasattr(request.baseline, "space") else None),
                artifact_store=self._artifact_store,
            ),
            "baseline",
            request.subject_axis.count,
        )

        delta_full = self._optional_delta_vector(request.delta_reference_full, request)
        delta_folds = self._optional_delta_folds(request.delta_reference_folds, request)
        if request.resampling_kind == "permutation":
            nuisance_plan = build_fixed_nuisance_plan(
                request,
                baseline,
                delta_full,
                delta_folds,
            )
            result = compute_direct_voxel_permutation(
                request,
                exposure,
                outcome,
                nuisance_plan,
            )
            return self._publish_permutation(request, result)

        result = compute_direct_voxel_bootstrap(
            request,
            exposure,
            outcome,
            baseline,
            self._bootstrap_nuisance_provider,
            delta_full,
            delta_folds,
        )
        return self._publish_bootstrap(request, result)

    def _optional_delta_vector(
        self,
        value: object,
        request: FormalRequest,
    ) -> np.ndarray | None:
        if value is None:
            return None
        array = materialize_array(
            value,
            name="delta_reference_full",
            expected_axes=(request.subject_axis,),
            expected_units=(value.units if hasattr(value, "units") else None),
            expected_space=(value.space if hasattr(value, "space") else None),
            artifact_store=self._artifact_store,
        )
        return finite_vector(array, "delta_reference_full", request.subject_axis.count)

    def _optional_delta_folds(
        self,
        value: object,
        request: FormalRequest,
    ) -> np.ndarray | None:
        if value is None:
            return None
        array = materialize_array(
            value,
            name="delta_reference_folds",
            expected_axes=(request.subject_axis, request.subject_axis),
            expected_units=(value.units if hasattr(value, "units") else None),
            expected_space=(value.space if hasattr(value, "space") else None),
            artifact_store=self._artifact_store,
        )
        output = np.asarray(array, dtype=np.float64)
        expected = (request.subject_axis.count, request.subject_axis.count)
        if output.shape != expected or not np.all(np.isfinite(output)):
            raise FormalBackendInputError(
                "delta_reference_folds must be a finite fold-by-subject matrix"
            )
        return output

    def _publish_permutation(
        self,
        request: FormalRequest,
        result: PermutationComputation,
    ) -> FormalResult:
        replicate_axis = resample_axis(request)
        null_artifact = self._publisher.array(
            "formal_permutation_null_statistics.npy",
            result.null_statistics,
            kind="formal_permutation_null_statistics",
            axes=(replicate_axis,),
            units="spearman_rho",
            space=None,
        )
        finite_count = int(np.count_nonzero(np.isfinite(result.null_statistics)))
        status = (
            "completed"
            if finite_count == request.resamples
            else "completed_with_nonfinite_replicates"
        )
        artifacts = [null_artifact]
        schedule_artifact = None
        if result.permutation_schedule is not None:
            schedule_artifact = self._publisher.array(
                "formal_permutation_schedule.npy",
                result.permutation_schedule,
                kind="formal_permutation_schedule",
                axes=(replicate_axis, request.subject_axis),
                units="subject_index",
                space=None,
            )
            artifacts.append(schedule_artifact)
        summary = {
            "schema_version": "formal_permutation_summary_v2",
            "final_model_id": request.final_model.identifier,
            "resampling_kind": "permutation",
            "resamples_requested": request.resamples,
            "finite_replicate_count": finite_count,
            "seed": request.seed,
            "p_plus_one_two_sided": result.p_plus_one_two_sided,
            "observed": result.observed_metrics,
            "permutation_schedule_id": (
                schedule_artifact.identifier if schedule_artifact is not None else None
            ),
            "permutation_schedule_sha256": (
                schedule_artifact.sha256 if schedule_artifact is not None else None
            ),
            "rng_algorithm": "numpy_pcg64",
            "rng_contract_version": 1,
            "technical_status": status,
        }
        summary_artifact = self._publisher.document(
            "formal_permutation_summary.json",
            json_safe(summary),
            kind="formal_permutation_summary",
        )
        return FormalResult(
            final_model_id=request.final_model.identifier,
            resampling_kind="permutation",
            technical_status=status,
            artifacts=tuple((*artifacts, summary_artifact)),
        )

    def _publish_bootstrap(
        self,
        request: FormalRequest,
        result: BootstrapComputation,
    ) -> FormalResult:
        feature_axis = request.feature_axis
        replicate_axis = resample_axis(request)
        feature_outputs = (
            ("formal_bootstrap_weight_mean.npy", "formal_bootstrap_weight_mean", result.weight_mean, "coefficient"),
            ("formal_bootstrap_weight_se.npy", "formal_bootstrap_weight_se", result.weight_se, "coefficient"),
            ("formal_bootstrap_finite_weight_count.npy", "formal_bootstrap_finite_weight_count", result.finite_weight_count, "count"),
            ("formal_bootstrap_candidate_selection_frequency.npy", "formal_bootstrap_candidate_selection_frequency", result.candidate_selection_frequency, "proportion"),
            ("formal_bootstrap_positive_sign_frequency.npy", "formal_bootstrap_positive_sign_frequency", result.positive_sign_frequency, "proportion"),
            ("formal_bootstrap_negative_sign_frequency.npy", "formal_bootstrap_negative_sign_frequency", result.negative_sign_frequency, "proportion"),
        )
        artifacts = [
            self._publisher.array(
                filename,
                values,
                kind=kind,
                axes=(feature_axis,),
                units=units,
                space=request.exposure_space,
            )
            for filename, kind, values, units in feature_outputs
        ]
        replicate_outputs = (
            ("formal_bootstrap_candidate_count.npy", "formal_bootstrap_candidate_count", result.replicate_candidate_count, "count"),
            ("formal_bootstrap_valid_weight_count.npy", "formal_bootstrap_valid_weight_count", result.replicate_valid_weight_count, "count"),
            ("formal_bootstrap_support_code.npy", "formal_bootstrap_support_code", result.replicate_support_code, "ordinal_code"),
        )
        artifacts.extend(
            self._publisher.array(
                filename,
                values,
                kind=kind,
                axes=(replicate_axis,),
                units=units,
                space=None,
            )
            for filename, kind, values, units in replicate_outputs
        )
        if result.nuisance_evidence or result.nonestimable_replicates:
            artifacts.append(
                self._publisher.document(
                    "formal_bootstrap_nuisance_qc.json",
                    {
                        "schema_version": "formal_bootstrap_nuisance_qc_v2",
                        "final_model_id": request.final_model.identifier,
                        "replicates": list(result.nuisance_evidence),
                        "nonestimable_replicates": list(
                            result.nonestimable_replicates
                        ),
                    },
                    kind="formal_bootstrap_nuisance_qc",
                )
            )
        status = (
            "completed"
            if result.finite_replicate_count == request.resamples
            else "completed_with_nonfinite_replicates"
        )
        summary = {
            "schema_version": "formal_bootstrap_summary_v2",
            "final_model_id": request.final_model.identifier,
            "resampling_kind": "bootstrap",
            "resamples_requested": request.resamples,
            "finite_replicate_count": result.finite_replicate_count,
            "nonestimable_nuisance_replicate_count": len(
                result.nonestimable_replicates
            ),
            "seed": request.seed,
            "support_code_legend": {"0": "absent", "1": "limited", "2": "adequate"},
            "technical_status": status,
        }
        artifacts.append(
            self._publisher.document(
                "formal_bootstrap_summary.json",
                json_safe(summary),
                kind="formal_bootstrap_summary",
            )
        )
        return FormalResult(
            final_model_id=request.final_model.identifier,
            resampling_kind="bootstrap",
            technical_status=status,
            artifacts=tuple(artifacts),
        )


__all__ = [
    "DirectVoxelFormalBackend",
    "FormalBackendError",
    "FormalBackendInputError",
    "compute_direct_voxel_bootstrap",
    "compute_direct_voxel_permutation",
    "compute_direct_voxel_permutation_block",
]
