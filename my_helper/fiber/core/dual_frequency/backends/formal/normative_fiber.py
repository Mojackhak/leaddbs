"""Final-only normative-fiber permutation and subject-bootstrap backend."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...cache import ArtifactStore
from ...contracts import FormalRequest, FormalResult, NormativeFiberScoreSettings
from ..normative_fiber.coverage import (
    candidate_mask,
    coverage_counts,
    heldout_fold_candidate_mask,
)
from ..normative_fiber.scoring import (
    PrevalidatedFiberScoreWorkspace,
    score_signed_fibers,
)
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
    canonical_fiber_ids,
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
class _FiberFoldOperator:
    heldout: int
    train: np.ndarray
    nuisance_train: np.ndarray
    nuisance_test: np.ndarray
    ranked_nuisance_train: np.ndarray
    candidate_mask: np.ndarray
    estimable_indices: np.ndarray
    standardized_exposure_residual: np.ndarray


def _fold_candidate_masks(
    request: FormalRequest,
    exposure: np.ndarray,
) -> tuple[np.ndarray, ...]:
    tau = float(request.final_model.final_key.selected_tau)
    coverage = int(request.final_model.final_key.selected_coverage)
    minimum = request.hard_computability.fold_n_features_min
    if minimum is None:
        raise FormalBackendInputError("normative-fiber formal limits are incomplete")
    full_counts = coverage_counts(exposure, tau)
    masks: list[np.ndarray] = []
    for heldout in range(exposure.shape[0]):
        mask = heldout_fold_candidate_mask(
            exposure,
            full_counts,
            heldout,
            tau,
            coverage,
        )
        if int(np.count_nonzero(mask)) < minimum:
            raise FormalBackendInputError(
                f"locked normative-fiber final axis fails fold feature minimum at {heldout}"
            )
        masks.append(mask)
    return tuple(masks)


def _build_fold_operators(
    request: FormalRequest,
    exposure: np.ndarray,
    nuisance_plan: NuisancePlan,
    masks: tuple[np.ndarray, ...],
) -> tuple[_FiberFoldOperator, ...]:
    subjects = np.arange(exposure.shape[0], dtype=np.int64)
    operators: list[_FiberFoldOperator] = []
    for heldout, candidate in enumerate(masks):
        train = np.delete(subjects, heldout)
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
                f"locked normative-fiber final axis has no estimable fiber at fold {heldout}"
            )
        candidate_indices = np.flatnonzero(candidate)
        estimable_indices = candidate_indices[estimable]
        operators.append(
            _FiberFoldOperator(
                heldout=heldout,
                train=train,
                nuisance_train=nuisance_train,
                nuisance_test=nuisance[[heldout]],
                ranked_nuisance_train=ranked_nuisance,
                candidate_mask=candidate,
                estimable_indices=estimable_indices,
                standardized_exposure_residual=(
                    exposure_residual[:, estimable] / denominator[estimable]
                ),
            )
        )
    return tuple(operators)


def _optimized_weights(
    request: FormalRequest,
    outcome: np.ndarray,
    operator: _FiberFoldOperator,
) -> np.ndarray:
    weights = np.full(request.feature_axis.count, np.nan, dtype=np.float64)
    ranked_outcome = average_rank(outcome[operator.train])
    residual = residualize(ranked_outcome, operator.ranked_nuisance_train)
    denominator = float(np.sqrt(np.sum(residual**2)))
    if not np.isfinite(denominator) or denominator <= 0.0:
        return weights
    coefficients = operator.standardized_exposure_residual.T @ (
        residual / denominator
    )
    weights[operator.estimable_indices] = benefit_oriented_weights(
        coefficients,
        request.outcome_direction,
    )
    return weights


def _brute_force_weights(
    request: FormalRequest,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    operator: _FiberFoldOperator,
) -> np.ndarray:
    weights = np.full(request.feature_axis.count, np.nan, dtype=np.float64)
    coefficients = partial_spearman_weights(
        outcome[operator.train],
        exposure[operator.train][:, operator.candidate_mask],
        nuisance_plan.fold_covariates[operator.heldout, operator.train],
    )
    weights[operator.candidate_mask] = benefit_oriented_weights(
        coefficients,
        request.outcome_direction,
    )
    return weights


def _loocv(
    request: FormalRequest,
    exposure: np.ndarray,
    fiber_ids: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    operators: tuple[_FiberFoldOperator, ...],
    score_workspace: PrevalidatedFiberScoreWorkspace,
    *,
    optimized: bool,
) -> dict[str, float]:
    settings = request.fiber_score_settings
    if not isinstance(settings, NormativeFiberScoreSettings):
        raise FormalBackendInputError("normative-fiber score settings are missing")
    predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    baseline_predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    valid_counts: list[int] = []
    for operator in operators:
        weights = (
            _optimized_weights(request, outcome, operator)
            if optimized
            else _brute_force_weights(
                request,
                exposure,
                outcome,
                nuisance_plan,
                operator,
            )
        )
        valid_counts.append(int(np.count_nonzero(np.isfinite(weights))))
        score = score_workspace.score_state(
            weights,
            settings,
            candidate_mask=operator.candidate_mask,
        )
        train_score = score.net_score[operator.train]
        if (
            score.fiber_score_support_status == "absent_no_valid_signed_fibers"
            or not np.all(np.isfinite(train_score))
            or np.std(train_score) <= 0.0
        ):
            continue
        prediction, _ = linear_prediction(
            outcome[operator.train],
            train_score,
            operator.nuisance_train,
            score.net_score[[operator.heldout]],
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
                min(np.count_nonzero(operator.candidate_mask) for operator in operators)
            ),
            "fold_n_valid_features_min": float(min(valid_counts) if valid_counts else 0),
        }
    )
    return metrics


def _normative_fiber_permutation_block(
    request: FormalRequest,
    exposure: np.ndarray,
    fiber_ids: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    operators: tuple[_FiberFoldOperator, ...],
    score_workspace: PrevalidatedFiberScoreWorkspace,
    schedule: ResamplingSchedule,
    block: ReplicateBlock,
    *,
    optimized: bool,
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
        metrics = _loocv(
            request,
            exposure,
            fiber_ids,
            permuted_outcome,
            nuisance_plan,
            operators,
            score_workspace,
            optimized=optimized,
        )
        rho = float(metrics["loocv_spearman_rho"])
        if bool(metrics["all_predictions_finite"]) and np.isfinite(rho):
            null[local_index] = rho
    return PermutationBlockComputation(
        block=block,
        schedule_sha256=schedule.descriptor.schedule_sha256,
        null_statistics=null,
    )


def compute_normative_fiber_permutation_block(
    request: FormalRequest,
    exposure: np.ndarray,
    fiber_ids: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    schedule: ResamplingSchedule,
    block: ReplicateBlock,
    *,
    optimized: bool = True,
) -> PermutationBlockComputation:
    """Compute one fixed normative-fiber permutation interval."""

    if request.resampling_kind != "permutation":
        raise FormalBackendInputError(
            "fiber permutation requires resampling_kind='permutation'"
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
            "fiber permutation block does not match request resamples"
        )
    masks = _fold_candidate_masks(request, exposure)
    operators = _build_fold_operators(request, exposure, nuisance_plan, masks)
    score_workspace = PrevalidatedFiberScoreWorkspace(exposure, fiber_ids)
    return _normative_fiber_permutation_block(
        request,
        exposure,
        fiber_ids,
        outcome,
        nuisance_plan,
        operators,
        score_workspace,
        schedule,
        block,
        optimized=optimized,
    )


def compute_normative_fiber_permutation(
    request: FormalRequest,
    exposure: np.ndarray,
    fiber_ids: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    *,
    optimized: bool = True,
) -> PermutationComputation:
    """Compute a deterministic normative-fiber Freedman-Lane permutation test."""

    if request.resampling_kind != "permutation":
        raise FormalBackendInputError(
            "fiber permutation requires resampling_kind='permutation'"
        )
    masks = _fold_candidate_masks(request, exposure)
    operators = _build_fold_operators(request, exposure, nuisance_plan, masks)
    score_workspace = PrevalidatedFiberScoreWorkspace(exposure, fiber_ids)
    observed = _loocv(
        request,
        exposure,
        fiber_ids,
        outcome,
        nuisance_plan,
        operators,
        score_workspace,
        optimized=optimized,
    )
    if not bool(observed["all_predictions_finite"]) or not np.isfinite(
        observed["loocv_spearman_rho"]
    ):
        raise FormalBackendError(
            "observed final normative-fiber LOOCV statistic is not computable"
        )
    schedule = formal_resampling_schedule(
        "permutation",
        outcome.size,
        request.resamples,
        request.seed,
    )
    blocks = tuple(
        _normative_fiber_permutation_block(
            request,
            exposure,
            fiber_ids,
            outcome,
            nuisance_plan,
            operators,
            score_workspace,
            schedule,
            block,
            optimized=optimized,
        )
        for block in schedule.blocks()
    )
    return combine_permutation_blocks(
        observed,
        schedule,
        blocks,
    )


def compute_normative_fiber_bootstrap(
    request: FormalRequest,
    exposure: np.ndarray,
    fiber_ids: np.ndarray,
    outcome: np.ndarray,
    baseline: np.ndarray,
    provider: BootstrapNuisanceProvider | None,
    original_delta_full: np.ndarray | None = None,
    original_delta_folds: np.ndarray | None = None,
) -> BootstrapComputation:
    """Compute deterministic fiber weight, support, sign, and selection stability."""

    if request.resampling_kind != "bootstrap":
        raise FormalBackendInputError("fiber bootstrap requires resampling_kind='bootstrap'")
    settings = request.fiber_score_settings
    if not isinstance(settings, NormativeFiberScoreSettings):
        raise FormalBackendInputError("normative-fiber score settings are missing")
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
    samples = bootstrap_sample_indices(
        request.subject_axis.count,
        request.resamples,
        request.seed,
    )
    accumulator = StreamingBootstrapAccumulator(
        resamples=request.resamples,
        n_features=request.feature_axis.count,
        track_selection=True,
    )
    id_to_index = {int(fiber_id): index for index, fiber_id in enumerate(fiber_ids)}

    for replicate, sample in enumerate(samples):
        sampled_exposure = np.asarray(exposure[sample], dtype=np.float64)
        candidate = candidate_mask(coverage_counts(sampled_exposure, tau), coverage)
        replicate_weights = np.full(request.feature_axis.count, np.nan, dtype=np.float64)
        sweet_selected = np.zeros(request.feature_axis.count, dtype=bool)
        sour_selected = np.zeros(request.feature_axis.count, dtype=bool)
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
                sweet_selected=sweet_selected,
                sour_selected=sour_selected,
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
                sweet_selected=sweet_selected,
                sour_selected=sour_selected,
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
        score = score_signed_fibers(
            sampled_exposure,
            replicate_weights,
            fiber_ids,
            settings,
            candidate_mask=candidate,
        )
        support_code = 0
        if score.fiber_score_support_status == "absent_no_valid_signed_fibers":
            pass
        else:
            support_code = (
                2
                if score.fiber_score_support_status == "adequate_two_sign"
                and (
                    nuisance_evidence is None
                    or nuisance_evidence.support_status != "limited"
                )
                else 1
            )
            for fiber_id in score.sweet_fiber_ids:
                sweet_selected[id_to_index[int(fiber_id)]] = True
            for fiber_id in score.sour_fiber_ids:
                sour_selected[id_to_index[int(fiber_id)]] = True
        accumulator.update(
            replicate,
            weights=replicate_weights,
            candidate_mask=candidate,
            support_code=support_code,
            nuisance_evidence=nuisance_evidence,
            sweet_selected=sweet_selected,
            sour_selected=sour_selected,
        )
    return accumulator.finalize()


class NormativeFiberFormalBackend:
    """Publish formal evidence for exactly one realized formal-connectome final."""

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
        if not request.final_model.endpoint.model_family.endswith("fiber"):
            raise FormalBackendInputError("fiber backend requires a normative-fiber final")
        if request.connectome_role != "formal":
            raise FormalBackendInputError(
                "normative-fiber backend requires connectome_role='formal'"
            )
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
        assert request.feature_ids is not None
        fiber_ids = canonical_fiber_ids(
            materialize_array(
                request.feature_ids,
                name="feature_ids",
                expected_axes=(request.feature_axis,),
                expected_units=(request.feature_ids.units if hasattr(request.feature_ids, "units") else None),
                expected_space=(request.feature_ids.space if hasattr(request.feature_ids, "space") else None),
                artifact_store=self._artifact_store,
            ),
            request.feature_axis.count,
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
            result = compute_normative_fiber_permutation(
                request,
                exposure,
                fiber_ids,
                outcome,
                nuisance_plan,
            )
            return self._publish_permutation(request, result)

        result = compute_normative_fiber_bootstrap(
            request,
            exposure,
            fiber_ids,
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
        replicate_axis = resample_axis(request)
        feature_outputs = (
            ("formal_bootstrap_weight_mean.npy", "formal_bootstrap_weight_mean", result.weight_mean, "coefficient"),
            ("formal_bootstrap_weight_se.npy", "formal_bootstrap_weight_se", result.weight_se, "coefficient"),
            ("formal_bootstrap_finite_weight_count.npy", "formal_bootstrap_finite_weight_count", result.finite_weight_count, "count"),
            ("formal_bootstrap_candidate_selection_frequency.npy", "formal_bootstrap_candidate_selection_frequency", result.candidate_selection_frequency, "proportion"),
            ("formal_bootstrap_positive_sign_frequency.npy", "formal_bootstrap_positive_sign_frequency", result.positive_sign_frequency, "proportion"),
            ("formal_bootstrap_negative_sign_frequency.npy", "formal_bootstrap_negative_sign_frequency", result.negative_sign_frequency, "proportion"),
            ("formal_bootstrap_sweet_selection_frequency.npy", "formal_bootstrap_sweet_selection_frequency", result.sweet_selection_frequency, "proportion"),
            ("formal_bootstrap_sour_selection_frequency.npy", "formal_bootstrap_sour_selection_frequency", result.sour_selection_frequency, "proportion"),
        )
        artifacts = [
            self._publisher.array(
                filename,
                values,
                kind=kind,
                axes=(request.feature_axis,),
                units=units,
                space=request.exposure_space,
            )
            for filename, kind, values, units in feature_outputs
            if values is not None
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
    "FormalBackendError",
    "FormalBackendInputError",
    "NormativeFiberFormalBackend",
    "compute_normative_fiber_bootstrap",
    "compute_normative_fiber_permutation",
    "compute_normative_fiber_permutation_block",
]
