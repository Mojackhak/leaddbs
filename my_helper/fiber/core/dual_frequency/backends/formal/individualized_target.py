"""Final-only individualized target permutation and bootstrap backend."""

from __future__ import annotations

import numpy as np

from ...cache import ArtifactStore
from ...contracts import FormalRequest, FormalResult
from ..individualized_target import evaluate_target_cell
from ..protocols import ArtifactPublisher, BootstrapNuisanceProvider
from ..statistics import (
    benefit_oriented_weights,
    partial_spearman_coefficients_and_pvalues,
)
from .common import (
    BootstrapBlockComputation,
    BootstrapReplicateNotEstimableError,
    FormalBackendError,
    FormalBackendInputError,
    PermutationBlockComputation,
    ReplicateBlock,
    ResamplingSchedule,
    StreamingBootstrapAccumulator,
    build_bootstrap_nuisance_plan,
    build_fixed_nuisance_plan,
    combine_bootstrap_blocks,
    combine_permutation_blocks,
    finite_vector,
    freedman_lane_outcomes,
    materialize_array,
    validate_resampling_schedule,
)
from .direct_voxel import DirectVoxelFormalBackend


class IndividualizedTargetFormalBackend:
    """Compute formal evidence for one locked individualized target model."""

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

    def _arrays(
        self,
        request: FormalRequest,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if not request.final_model.endpoint.model_family.endswith(
            "individualized"
        ):
            raise FormalBackendInputError(
                "target formal backend requires an individualized final"
            )
        if request.target_support is None:
            raise FormalBackendInputError(
                "target formal request lacks target support"
            )
        exposure = np.asarray(
            materialize_array(
                request.exposure,
                name="target_exposure",
                expected_axes=(
                    request.subject_axis,
                    request.feature_axis,
                ),
                expected_units="V/m",
                expected_space="individualized_target",
                artifact_store=self._artifact_store,
            ),
            dtype=np.float64,
        )
        support = np.asarray(
            materialize_array(
                request.target_support,
                name="target_support",
                expected_axes=(
                    request.subject_axis,
                    request.feature_axis,
                ),
                expected_units="binary",
                expected_space="individualized_target",
                artifact_store=self._artifact_store,
            ),
            dtype=bool,
        )
        outcome = finite_vector(
            materialize_array(
                request.outcome,
                name="outcome",
                expected_axes=(request.subject_axis,),
                expected_units=request.outcome.units,
                expected_space=request.outcome.space,
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
                expected_units=request.baseline.units,
                expected_space=request.baseline.space,
                artifact_store=self._artifact_store,
            ),
            "baseline",
            request.subject_axis.count,
        )
        if exposure.shape != support.shape:
            raise FormalBackendInputError(
                "target exposure and support shapes differ"
            )
        return exposure, support, outcome, baseline

    def _optional_delta(
        self,
        request: FormalRequest,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        full = (
            None
            if request.delta_reference_full is None
            else finite_vector(
                materialize_array(
                    request.delta_reference_full,
                    name="delta_reference_full",
                    expected_axes=(request.subject_axis,),
                    expected_units=request.delta_reference_full.units,
                    expected_space=request.delta_reference_full.space,
                    artifact_store=self._artifact_store,
                ),
                "delta_reference_full",
                request.subject_axis.count,
            )
        )
        folds = None
        if request.delta_reference_folds is not None:
            folds = np.asarray(
                materialize_array(
                    request.delta_reference_folds,
                    name="delta_reference_folds",
                    expected_axes=(
                        request.subject_axis,
                        request.subject_axis,
                    ),
                    expected_units=request.delta_reference_folds.units,
                    expected_space=request.delta_reference_folds.space,
                    artifact_store=self._artifact_store,
                ),
                dtype=np.float64,
            )
            if (
                folds.shape
                != (
                    request.subject_axis.count,
                    request.subject_axis.count,
                )
                or not np.all(np.isfinite(folds))
            ):
                raise FormalBackendInputError(
                    "delta_reference_folds must be finite and fold-by-subject"
                )
        return full, folds

    @staticmethod
    def _metrics(computation) -> dict[str, float]:
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
            "all_predictions_finite": float(
                metrics.all_predictions_finite
            ),
            "fold_n_candidate_features_min": float(
                metrics.fold_n_features_min
            ),
            "fold_n_valid_features_min": float(
                metrics.fold_n_features_min
            ),
        }

    def _permutation_workspace(
        self,
        request: FormalRequest,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        object,
    ]:
        exposure, support, outcome, baseline = self._arrays(request)
        delta_full, delta_folds = self._optional_delta(request)
        nuisance_plan = build_fixed_nuisance_plan(
            request,
            baseline,
            delta_full,
            delta_folds,
        )
        return exposure, support, outcome, nuisance_plan

    def _statistic(
        self,
        request: FormalRequest,
        exposure: np.ndarray,
        support: np.ndarray,
        nuisance_plan,
        outcome: np.ndarray,
    ) -> dict[str, float]:
        computation = evaluate_target_cell(
            exposure,
            support,
            outcome,
            nuisance_plan,
            request.outcome_direction,
            float(request.final_model.final_key.selected_tau),
            int(request.final_model.final_key.selected_coverage),
            request.hard_computability,
            retain_arrays=False,
        )
        return self._metrics(computation)

    def run_permutation_block(
        self,
        request: FormalRequest,
        schedule: ResamplingSchedule,
        block: ReplicateBlock,
    ) -> PermutationBlockComputation:
        exposure, support, outcome, nuisance_plan = (
            self._permutation_workspace(request)
        )
        validate_resampling_schedule(
            schedule,
            schedule_kind="permutation",
            subject_count=outcome.size,
            replicate_count=request.resamples,
            seed=request.seed,
        )
        permuted = freedman_lane_outcomes(
            outcome,
            nuisance_plan.full_covariates,
            block.count,
            request.seed,
            schedule=schedule.block_view(block),
        )
        null = np.full(block.count, np.nan, dtype=np.float64)
        for index, permuted_outcome in enumerate(permuted):
            metrics = self._statistic(
                request,
                exposure,
                support,
                nuisance_plan,
                permuted_outcome,
            )
            rho = float(metrics["loocv_spearman_rho"])
            if bool(metrics["all_predictions_finite"]) and np.isfinite(rho):
                null[index] = rho
        return PermutationBlockComputation(
            block=block,
            schedule_sha256=schedule.descriptor.schedule_sha256,
            null_statistics=null,
        )

    def aggregate_permutation(
        self,
        request: FormalRequest,
        schedule: ResamplingSchedule,
        blocks: tuple[PermutationBlockComputation, ...],
        schedule_artifact,
    ) -> FormalResult:
        exposure, support, outcome, nuisance_plan = (
            self._permutation_workspace(request)
        )
        observed = self._statistic(
            request,
            exposure,
            support,
            nuisance_plan,
            outcome,
        )
        if (
            not bool(observed["all_predictions_finite"])
            or not np.isfinite(observed["loocv_spearman_rho"])
        ):
            raise FormalBackendError(
                "observed individualized target statistic is not computable"
            )
        result = combine_permutation_blocks(observed, schedule, blocks)
        return DirectVoxelFormalBackend(
            self._publisher,
            artifact_store=self._artifact_store,
        )._publish_permutation(
            request,
            result,
            schedule_artifact=schedule_artifact,
        )

    def run_bootstrap_block(
        self,
        request: FormalRequest,
        schedule: ResamplingSchedule,
        block: ReplicateBlock,
    ) -> BootstrapBlockComputation:
        exposure, support, outcome, baseline = self._arrays(request)
        delta_full, delta_folds = self._optional_delta(request)
        build_fixed_nuisance_plan(
            request,
            baseline,
            delta_full,
            delta_folds,
        )
        validate_resampling_schedule(
            schedule,
            schedule_kind="bootstrap",
            subject_count=request.subject_axis.count,
            replicate_count=request.resamples,
            seed=request.seed,
        )
        coverage = int(request.final_model.final_key.selected_coverage)
        full_minimum = request.hard_computability.n_features_full_min
        if full_minimum is None:
            raise FormalBackendInputError(
                "target bootstrap requires a full target minimum"
            )
        adjusted = (
            request.final_model.final_key.final_branch
            == "delta_reference_adjusted"
        )
        accumulator = StreamingBootstrapAccumulator(
            resamples=request.resamples,
            n_features=request.feature_axis.count,
            track_selection=False,
            retain_replicate_weights=True,
        )
        for replicate, sample in zip(
            range(block.start, block.stop),
            schedule.block_view(block),
            strict=True,
        ):
            sampled_support = support[sample]
            candidate = (
                np.count_nonzero(sampled_support, axis=0) >= coverage
            )
            replicate_weights = np.full(
                request.feature_axis.count,
                np.nan,
                dtype=np.float64,
            )
            try:
                nuisance_plan, nuisance_evidence = (
                    build_bootstrap_nuisance_plan(
                        request,
                        baseline,
                        sample,
                        self._bootstrap_nuisance_provider,
                        original_delta_full=delta_full,
                        original_delta_folds=delta_folds,
                    )
                )
            except BootstrapReplicateNotEstimableError as exc:
                accumulator.update(
                    replicate,
                    weights=replicate_weights,
                    candidate_mask=candidate,
                    support_code=0,
                    nuisance_evidence=None,
                    nuisance_nonestimability=exc.detail,
                )
                continue
            if np.any(candidate):
                coefficients, _ = partial_spearman_coefficients_and_pvalues(
                    outcome[sample],
                    exposure[sample][:, candidate],
                    nuisance_plan.full_covariates,
                )
                replicate_weights[candidate] = benefit_oriented_weights(
                    coefficients,
                    request.outcome_direction,
                )
            valid_count = int(
                np.count_nonzero(np.isfinite(replicate_weights))
            )
            support_code = (
                2
                if valid_count > 0
                and int(np.count_nonzero(candidate)) >= full_minimum
                and (
                    nuisance_evidence is None
                    or nuisance_evidence.support_status != "limited"
                )
                else 1
                if valid_count > 0
                else 0
            )
            accumulator.update(
                replicate,
                weights=replicate_weights,
                candidate_mask=candidate,
                support_code=support_code,
                nuisance_evidence=nuisance_evidence,
            )
        return accumulator.block_result(
            block,
            schedule.descriptor.schedule_sha256,
            require_complete_nuisance_evidence=adjusted,
        )

    def aggregate_bootstrap(
        self,
        request: FormalRequest,
        schedule: ResamplingSchedule,
        blocks: tuple[BootstrapBlockComputation, ...],
    ) -> FormalResult:
        result = combine_bootstrap_blocks(schedule, blocks)
        return DirectVoxelFormalBackend(
            self._publisher,
            artifact_store=self._artifact_store,
        )._publish_bootstrap(request, result)


__all__ = ["IndividualizedTargetFormalBackend"]
