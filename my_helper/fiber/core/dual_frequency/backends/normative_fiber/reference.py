"""Reference normative-fiber observed backend with role-aware publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import math
from pathlib import Path
import tempfile
from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ArtifactRef,
    AxisRef,
    FeatureAxisRef,
    ObservedRequest,
    ObservedResult,
    SensitiveRecord,
    SourceRecord,
    canonical_hash,
)
from ...contracts.requests import ScientificInput
from ..nuisance import NuisancePlan
from ..protocols import ArtifactPublisher
from ..source_resolver import SourceResolution, resolve_source
from ..statistics import (
    benefit_oriented_weights,
    classify_prediction_status,
    linear_prediction,
    partial_spearman_weights,
    safe_correlation,
)
from .coverage import candidate_mask, coverage_counts, heldout_fold_candidate_mask
from .scoring import (
    FiberScoreResult,
    PrevalidatedFiberScoreWorkspace,
    score_support_fields,
)


SUPPORT_STATUSES = frozenset(
    {
        "adequate_two_sign",
        "limited_two_sign",
        "limited_positive_only",
        "limited_negative_only",
        "absent_no_valid_signed_fibers",
    }
)


class ReferenceFiberBackendError(RuntimeError):
    """Raised when a reference normative-fiber request cannot complete safely."""


@dataclass(frozen=True)
class FiberGridCellMetrics:
    """Observed and LOOCV evidence for one normative-fiber grid cell."""

    tau: float
    coverage: int
    n_subjects: int
    n_features_full: int
    n_candidate_full: int
    n_valid_full_features: int
    fold_n_features_min: int
    fold_n_features_median: float
    fold_n_features_max: int
    fold_n_valid_features_min: int
    fold_n_valid_features_median: float
    fold_n_valid_features_max: int
    full_support_status: str
    fold_support_statuses: tuple[str, ...]
    baseline_nuisance_design_valid: bool
    score_nonconstant_all_folds: bool
    all_predictions_finite: bool
    loocv_spearman_rho: float
    loocv_spearman_nominal_p: float
    loocv_pearson_r: float
    loocv_pearson_nominal_p: float
    q2: float
    mae_model: float
    mae_baseline: float
    rmse_model: float
    rmse_baseline: float
    full_score_baseline_pearson_r: float
    full_score_baseline_spearman_rho: float
    passes_n_subjects: bool
    passes_fold_n_features_min: bool
    passes_baseline_nuisance_design: bool
    passes_signed_support: bool
    passes_score_nonconstant: bool
    passes_predictions_finite: bool
    passes_hard_computability: bool
    prediction_status: str
    failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.tau)) or self.tau <= 0:
            raise ReferenceFiberBackendError("grid-cell tau must be finite and positive")
        if type(self.coverage) is not int or self.coverage < 1:
            raise ReferenceFiberBackendError("grid-cell coverage must be a positive integer")
        for field in (
            "n_subjects",
            "n_features_full",
            "n_candidate_full",
            "n_valid_full_features",
            "fold_n_features_min",
            "fold_n_features_max",
            "fold_n_valid_features_min",
            "fold_n_valid_features_max",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ReferenceFiberBackendError(f"{field} must be a nonnegative integer")
        for low, middle, high, label in (
            (
                self.fold_n_features_min,
                self.fold_n_features_median,
                self.fold_n_features_max,
                "candidate",
            ),
            (
                self.fold_n_valid_features_min,
                self.fold_n_valid_features_median,
                self.fold_n_valid_features_max,
                "valid",
            ),
        ):
            if not math.isfinite(float(middle)) or not low <= middle <= high:
                raise ReferenceFiberBackendError(
                    f"fold {label} minimum, median, and maximum are inconsistent"
                )
        statuses = tuple(self.fold_support_statuses)
        if self.full_support_status not in SUPPORT_STATUSES or any(
            status not in SUPPORT_STATUSES for status in statuses
        ):
            raise ReferenceFiberBackendError("unsupported fiber support status")
        if len(statuses) != self.n_subjects:
            raise ReferenceFiberBackendError("fold support statuses must match subjects")
        object.__setattr__(self, "fold_support_statuses", statuses)
        expected_signed = self.full_support_status != "absent_no_valid_signed_fibers" and all(
            status != "absent_no_valid_signed_fibers" for status in statuses
        )
        if self.passes_signed_support != expected_signed:
            raise ReferenceFiberBackendError("signed-support flags are contradictory")
        expected_hard = bool(
            self.passes_n_subjects
            and self.passes_fold_n_features_min
            and self.passes_baseline_nuisance_design
            and self.passes_signed_support
            and self.passes_score_nonconstant
            and self.passes_predictions_finite
        )
        if self.passes_hard_computability != expected_hard:
            raise ReferenceFiberBackendError("hard-computability flags are contradictory")
        if expected_hard:
            if self.prediction_status not in {"error_predictive", "error_nonpredictive"}:
                raise ReferenceFiberBackendError(
                    "computable grid cells require an error-prediction status"
                )
            if not all(
                math.isfinite(value)
                for value in (
                    self.mae_model,
                    self.mae_baseline,
                    self.rmse_model,
                    self.rmse_baseline,
                )
            ):
                raise ReferenceFiberBackendError(
                    "computable grid cells require finite prediction errors"
                )
        elif self.prediction_status != "not_applicable":
            raise ReferenceFiberBackendError(
                "noncomputable grid cells require prediction_status='not_applicable'"
            )
        reasons = tuple(str(reason).strip() for reason in self.failure_reasons)
        if any(not reason for reason in reasons):
            raise ReferenceFiberBackendError("failure reasons must be nonempty strings")
        object.__setattr__(self, "failure_reasons", reasons)

    def as_json_dict(self) -> dict[str, Any]:
        """Return strict JSON with undefined report metrics represented as null."""

        return _json_safe(asdict(self))


@dataclass(frozen=True)
class FiberSelectedArrays:
    """Selected-cell arrays projected onto the full/fold-valid union axis."""

    candidate_indices: np.ndarray
    union_indices: np.ndarray
    full_weights: np.ndarray
    fold_weights: np.ndarray
    fold_valid_masks: np.ndarray
    full_scores: np.ndarray
    fold_scores: np.ndarray
    heldout_scores: np.ndarray
    heldout_predictions: np.ndarray
    baseline_predictions: np.ndarray
    full_sweet_fiber_ids: np.ndarray
    full_sour_fiber_ids: np.ndarray
    full_support: dict[str, object]
    fold_support: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, np.ndarray):
                value.flags.writeable = False


@dataclass(frozen=True)
class FiberGridCellComputation:
    """One grid-cell metric with optional selected arrays."""

    metrics: FiberGridCellMetrics
    arrays: FiberSelectedArrays | None


@dataclass
class _WeightCache:
    full_weights: np.memmap
    fold_weights: np.memmap
    minimum_tau: float
    minimum_counts: np.ndarray

    def flush(self) -> None:
        self.full_weights.flush()
        self.fold_weights.flush()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


def _materialize(
    value: ScientificInput,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    expected_space: str | None,
    artifact_store: ArtifactStore | None,
    memory_map: bool,
) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asanyarray(value)
    if artifact_store is None:
        raise ReferenceFiberBackendError(
            f"{name} is artifact-backed but no ArtifactStore was provided"
        )
    if value.dtype is None or value.shape is None:
        raise ReferenceFiberBackendError(f"{name} must reference an array artifact")
    return artifact_store.materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=value.shape,
        expected_axes=expected_axes,
        expected_units=expected_units,
        expected_space=expected_space,
        mmap_mode="r" if memory_map else None,
    )


def _finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.ndim != 1
        or array.size != count
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.number)
        or np.iscomplexobj(array)
    ):
        raise ReferenceFiberBackendError(f"{name} must be a real subject vector")
    output = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(output)):
        raise ReferenceFiberBackendError(f"{name} must contain only finite values")
    return output


def _fiber_ids(value: np.ndarray, count: int) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.ndim != 1
        or array.size != count
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.integer)
    ):
        raise ReferenceFiberBackendError(
            "feature_ids must be a matching one-dimensional integer array"
        )
    if np.issubdtype(array.dtype, np.unsignedinteger) and np.any(
        array > np.iinfo(np.int64).max
    ):
        raise ReferenceFiberBackendError("feature_ids exceed the canonical int64 range")
    output = np.asarray(array, dtype=np.int64)
    if np.unique(output).size != output.size:
        raise ReferenceFiberBackendError("canonical feature_ids must be unique")
    output.flags.writeable = False
    return output


def _nuisance_design_valid_all_folds(nuisance_plan: NuisancePlan) -> bool:
    n_subjects = nuisance_plan.full_covariates.shape[0]
    for heldout in range(-1, n_subjects):
        indices = (
            np.arange(n_subjects)
            if heldout < 0
            else np.delete(np.arange(n_subjects), heldout)
        )
        covariates = (
            nuisance_plan.full_covariates
            if heldout < 0
            else nuisance_plan.fold_covariates[heldout]
        )
        design = np.column_stack([np.ones(indices.size), covariates[indices]])
        if indices.size <= design.shape[1] or np.linalg.matrix_rank(design) != design.shape[1]:
            return False
    return True


def _write_weight_row(
    destination: np.ndarray,
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_covariates: np.ndarray,
    subject_indices: np.ndarray,
    eligible: np.ndarray,
    outcome_direction: str,
    *,
    chunk_size: int,
) -> None:
    destination[:] = np.nan
    for start in range(0, exposure.shape[1], chunk_size):
        stop = min(start + chunk_size, exposure.shape[1])
        local = eligible[start:stop]
        if not np.any(local):
            continue
        block = np.asarray(exposure[:, start:stop], dtype=np.float64)[subject_indices]
        coefficients = partial_spearman_weights(
            outcome[subject_indices],
            block[:, local],
            nuisance_covariates[subject_indices],
        )
        positions = start + np.flatnonzero(local)
        destination[positions] = benefit_oriented_weights(
            coefficients,
            outcome_direction,
        ).astype(np.float32)


def _build_weight_cache(
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    request: ObservedRequest,
    work_root: Path,
    *,
    chunk_size: int,
) -> _WeightCache:
    minimum_tau = min(request.source_grid.tau_values)
    minimum_coverage = min(request.source_grid.coverage_values)
    counts = coverage_counts(exposure, minimum_tau, chunk_size=chunk_size)
    full_eligible = candidate_mask(counts, minimum_coverage)
    full = np.lib.format.open_memmap(
        work_root / "full_weights.npy",
        mode="w+",
        dtype=np.float32,
        shape=(exposure.shape[1],),
    )
    folds = np.lib.format.open_memmap(
        work_root / "fold_weights.npy",
        mode="w+",
        dtype=np.float32,
        shape=(exposure.shape[0], exposure.shape[1]),
    )
    all_subjects = np.arange(exposure.shape[0])
    _write_weight_row(
        full,
        exposure,
        outcome,
        nuisance_plan.full_covariates,
        all_subjects,
        full_eligible,
        request.outcome_direction,
        chunk_size=chunk_size,
    )
    for heldout in range(exposure.shape[0]):
        train = np.delete(all_subjects, heldout)
        fold_eligible = heldout_fold_candidate_mask(
            exposure,
            counts,
            heldout,
            minimum_tau,
            minimum_coverage,
            chunk_size=chunk_size,
        )
        _write_weight_row(
            folds[heldout],
            exposure,
            outcome,
            nuisance_plan.fold_covariates[heldout],
            train,
            fold_eligible,
            request.outcome_direction,
            chunk_size=chunk_size,
        )
    cache = _WeightCache(full, folds, float(minimum_tau), counts)
    cache.flush()
    return cache


def _baseline_loocv_predictions(
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
) -> np.ndarray:
    predictions = np.full(outcome.size, np.nan, dtype=np.float64)
    all_subjects = np.arange(outcome.size)
    for heldout in range(outcome.size):
        train = np.delete(all_subjects, heldout)
        prediction, _ = linear_prediction(
            outcome[train],
            None,
            nuisance_plan.fold_covariates[heldout, train],
            None,
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        predictions[heldout] = prediction[0]
    predictions.flags.writeable = False
    return predictions


def _prediction_metrics(
    outcome: np.ndarray,
    model_predictions: np.ndarray,
    baseline_predictions: np.ndarray,
) -> dict[str, float]:
    model_finite = np.isfinite(outcome) & np.isfinite(model_predictions)
    baseline_finite = np.isfinite(outcome) & np.isfinite(baseline_predictions)
    if np.any(model_finite):
        model_error = outcome[model_finite] - model_predictions[model_finite]
        mae_model = float(np.mean(np.abs(model_error)))
        rmse_model = float(np.sqrt(np.mean(model_error**2)))
    else:
        mae_model = rmse_model = math.nan
    if np.any(baseline_finite):
        baseline_error = outcome[baseline_finite] - baseline_predictions[baseline_finite]
        mae_baseline = float(np.mean(np.abs(baseline_error)))
        rmse_baseline = float(np.sqrt(np.mean(baseline_error**2)))
    else:
        mae_baseline = rmse_baseline = math.nan
    joint = model_finite & baseline_finite
    q2 = math.nan
    if np.any(joint):
        sse_model = float(np.sum((outcome[joint] - model_predictions[joint]) ** 2))
        sse_baseline = float(np.sum((outcome[joint] - baseline_predictions[joint]) ** 2))
        if sse_baseline > 0:
            q2 = 1.0 - sse_model / sse_baseline
    spearman_rho, spearman_p = safe_correlation(
        outcome,
        model_predictions,
        method="spearman",
    )
    pearson_r, pearson_p = safe_correlation(
        outcome,
        model_predictions,
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


def _evaluate_cell(
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    request: ObservedRequest,
    cache: _WeightCache,
    score_workspace: PrevalidatedFiberScoreWorkspace,
    baseline_predictions: np.ndarray,
    counts: np.ndarray,
    tau: float,
    coverage: int,
    *,
    chunk_size: int,
    retain_arrays: bool,
) -> FiberGridCellComputation:
    settings = request.fiber_score_settings
    if settings is None:
        raise ReferenceFiberBackendError("normative-fiber score settings are missing")
    full_candidate = candidate_mask(counts, coverage)
    full_weights = cache.full_weights
    full_score = score_workspace.score(
        full_weights,
        settings,
        candidate_mask=full_candidate,
    )
    full_valid = full_candidate & np.isfinite(full_weights)
    valid_union = full_valid.copy()
    full_support = score_support_fields(full_score, settings)

    n_subjects = outcome.size
    fold_scores = np.empty((n_subjects, n_subjects), dtype=np.float64)
    heldout_scores = np.empty(n_subjects, dtype=np.float64)
    predictions = np.full(n_subjects, np.nan, dtype=np.float64)
    baseline_predictions = np.asarray(
        baseline_predictions,
        dtype=np.float64,
    ).copy()
    if baseline_predictions.shape != (n_subjects,):
        raise ReferenceFiberBackendError(
            "cached baseline predictions do not match the subject axis"
        )
    fold_candidate_counts: list[int] = []
    fold_valid_counts: list[int] = []
    fold_support: list[dict[str, object]] = []
    fold_support_statuses: list[str] = []
    score_nonconstant = True
    all_subjects = np.arange(n_subjects)
    for heldout in range(n_subjects):
        train = np.delete(all_subjects, heldout)
        fold_candidate = heldout_fold_candidate_mask(
            exposure,
            counts,
            heldout,
            tau,
            coverage,
            chunk_size=chunk_size,
        )
        fold_weights = cache.fold_weights[heldout]
        fold_score = score_workspace.score(
            fold_weights,
            settings,
            candidate_mask=fold_candidate,
        )
        fold_valid = fold_candidate & np.isfinite(fold_weights)
        valid_union |= fold_valid
        fold_scores[heldout] = fold_score.net_score
        heldout_scores[heldout] = fold_score.net_score[heldout]
        fold_candidate_counts.append(int(np.count_nonzero(fold_candidate)))
        fold_valid_counts.append(int(np.count_nonzero(fold_valid)))
        support = score_support_fields(fold_score, settings)
        fold_support.append(support)
        fold_support_statuses.append(fold_score.fiber_score_support_status)
        train_score = fold_score.net_score[train]
        if not np.all(np.isfinite(train_score)) or np.std(train_score) == 0:
            score_nonconstant = False
        model_prediction, _ = linear_prediction(
            outcome[train],
            train_score,
            nuisance_plan.fold_covariates[heldout, train],
            fold_score.net_score[[heldout]],
            nuisance_plan.fold_covariates[heldout, [heldout]],
        )
        predictions[heldout] = model_prediction[0]

    fold_candidates = np.asarray(fold_candidate_counts, dtype=np.int64)
    fold_valid = np.asarray(fold_valid_counts, dtype=np.int64)
    baseline_design_valid = _nuisance_design_valid_all_folds(nuisance_plan)
    all_predictions_finite = bool(
        np.all(np.isfinite(predictions)) and np.all(np.isfinite(baseline_predictions))
    )
    passes_subjects = n_subjects >= request.hard_computability.n_subjects_min
    fold_minimum = request.hard_computability.fold_n_features_min
    if fold_minimum is None:
        raise ReferenceFiberBackendError("fold candidate minimum is missing")
    passes_fold_minimum = bool(fold_candidates.size and np.min(fold_candidates) >= fold_minimum)
    passes_signed = (
        full_score.fiber_score_support_status != "absent_no_valid_signed_fibers"
        and all(
            status != "absent_no_valid_signed_fibers"
            for status in fold_support_statuses
        )
    )
    passes_hard = bool(
        passes_subjects
        and passes_fold_minimum
        and baseline_design_valid
        and passes_signed
        and score_nonconstant
        and all_predictions_finite
    )
    performance = _prediction_metrics(outcome, predictions, baseline_predictions)
    prediction_status = (
        classify_prediction_status(
            performance["mae_model"],
            performance["mae_baseline"],
            performance["rmse_model"],
            performance["rmse_baseline"],
        )
        if passes_hard
        else "not_applicable"
    )
    failure_reasons: list[str] = []
    if not passes_subjects:
        failure_reasons.append("insufficient_subjects")
    if not passes_fold_minimum:
        failure_reasons.append("insufficient_fold_candidate_fibers")
    if not baseline_design_valid:
        failure_reasons.append("invalid_baseline_nuisance_design")
    if not passes_signed:
        failure_reasons.append("absent_valid_signed_fibers")
    if not score_nonconstant:
        failure_reasons.append("fold_score_constant_or_nonfinite")
    if not all_predictions_finite:
        failure_reasons.append("nonfinite_predictions")
    full_score_baseline_pearson, _ = safe_correlation(
        full_score.net_score,
        nuisance_plan.full_covariates[:, 0],
        method="pearson",
    )
    full_score_baseline_spearman, _ = safe_correlation(
        full_score.net_score,
        nuisance_plan.full_covariates[:, 0],
        method="spearman",
    )
    metrics = FiberGridCellMetrics(
        tau=float(tau),
        coverage=int(coverage),
        n_subjects=n_subjects,
        n_features_full=exposure.shape[1],
        n_candidate_full=int(np.count_nonzero(full_candidate)),
        n_valid_full_features=int(np.count_nonzero(full_valid)),
        fold_n_features_min=int(np.min(fold_candidates)),
        fold_n_features_median=float(np.median(fold_candidates)),
        fold_n_features_max=int(np.max(fold_candidates)),
        fold_n_valid_features_min=int(np.min(fold_valid)),
        fold_n_valid_features_median=float(np.median(fold_valid)),
        fold_n_valid_features_max=int(np.max(fold_valid)),
        full_support_status=full_score.fiber_score_support_status,
        fold_support_statuses=tuple(fold_support_statuses),
        baseline_nuisance_design_valid=baseline_design_valid,
        score_nonconstant_all_folds=score_nonconstant,
        all_predictions_finite=all_predictions_finite,
        full_score_baseline_pearson_r=full_score_baseline_pearson,
        full_score_baseline_spearman_rho=full_score_baseline_spearman,
        passes_n_subjects=passes_subjects,
        passes_fold_n_features_min=passes_fold_minimum,
        passes_baseline_nuisance_design=baseline_design_valid,
        passes_signed_support=passes_signed,
        passes_score_nonconstant=score_nonconstant,
        passes_predictions_finite=all_predictions_finite,
        passes_hard_computability=passes_hard,
        prediction_status=prediction_status,
        failure_reasons=tuple(failure_reasons),
        **performance,
    )

    arrays: FiberSelectedArrays | None = None
    if retain_arrays:
        union_indices = np.flatnonzero(valid_union).astype(np.int64)
        candidate_indices = np.flatnonzero(full_candidate).astype(np.int64)
        if union_indices.size == 0:
            raise ReferenceFiberBackendError("retained cell has no valid fiber union")
        selected_full_weights = np.asarray(full_weights[union_indices], dtype=np.float32).copy()
        selected_full_weights[~full_valid[union_indices]] = np.nan
        selected_fold_weights = np.empty(
            (n_subjects, union_indices.size),
            dtype=np.float32,
        )
        selected_fold_valid = np.empty(
            (n_subjects, union_indices.size),
            dtype=bool,
        )
        for heldout in range(n_subjects):
            fold_candidate = heldout_fold_candidate_mask(
                exposure,
                counts,
                heldout,
                tau,
                coverage,
                chunk_size=chunk_size,
            )
            valid = fold_candidate[union_indices] & np.isfinite(
                cache.fold_weights[heldout, union_indices]
            )
            selected_fold_valid[heldout] = valid
            selected_fold_weights[heldout] = cache.fold_weights[heldout, union_indices]
            selected_fold_weights[heldout, ~valid] = np.nan
        arrays = FiberSelectedArrays(
            candidate_indices=candidate_indices,
            union_indices=union_indices,
            full_weights=selected_full_weights,
            fold_weights=selected_fold_weights,
            fold_valid_masks=selected_fold_valid,
            full_scores=np.asarray(full_score.net_score, dtype=np.float64),
            fold_scores=fold_scores,
            heldout_scores=heldout_scores,
            heldout_predictions=predictions,
            baseline_predictions=baseline_predictions,
            full_sweet_fiber_ids=full_score.sweet_fiber_ids,
            full_sour_fiber_ids=full_score.sour_fiber_ids,
            full_support=full_support,
            fold_support=tuple(fold_support),
        )
    return FiberGridCellComputation(metrics=metrics, arrays=arrays)


class _FiberWorkspace:
    def __init__(
        self,
        exposure: np.ndarray,
        outcome: np.ndarray,
        nuisance_plan: NuisancePlan,
        fiber_ids: np.ndarray,
        request: ObservedRequest,
        *,
        chunk_size: int,
    ) -> None:
        self.exposure = exposure
        self.outcome = outcome
        self.nuisance_plan = nuisance_plan
        self.fiber_ids = fiber_ids
        self.request = request
        self.chunk_size = chunk_size
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.cache: _WeightCache | None = None
        self.score_workspace: PrevalidatedFiberScoreWorkspace | None = None
        self._coverage_counts: dict[float, np.ndarray] = {}
        self._baseline_predictions: np.ndarray | None = None

    def __enter__(self) -> "_FiberWorkspace":
        self._temporary = tempfile.TemporaryDirectory(prefix="dual-frequency-fiber-")
        self.cache = _build_weight_cache(
            self.exposure,
            self.outcome,
            self.nuisance_plan,
            self.request,
            Path(self._temporary.name),
            chunk_size=self.chunk_size,
        )
        self.score_workspace = PrevalidatedFiberScoreWorkspace(
            self.exposure,
            self.fiber_ids,
            chunk_size=self.chunk_size,
        )
        self._coverage_counts[self.cache.minimum_tau] = self.cache.minimum_counts
        return self

    def __exit__(self, *_: object) -> None:
        if self.cache is not None:
            self.cache.flush()
        self.cache = None
        self.score_workspace = None
        self._coverage_counts.clear()
        self._baseline_predictions = None
        if self._temporary is not None:
            self._temporary.cleanup()
        self._temporary = None

    def _counts(self, tau: float) -> np.ndarray:
        key = float(tau)
        counts = self._coverage_counts.get(key)
        if counts is None:
            counts = coverage_counts(
                self.exposure,
                key,
                chunk_size=self.chunk_size,
            )
            self._coverage_counts[key] = counts
        return counts

    def _baseline(self) -> np.ndarray:
        if self._baseline_predictions is None:
            self._baseline_predictions = _baseline_loocv_predictions(
                self.outcome,
                self.nuisance_plan,
            )
        return self._baseline_predictions

    def evaluate_grid(self) -> tuple[FiberGridCellMetrics, ...]:
        if self.cache is None or self.score_workspace is None:
            raise ReferenceFiberBackendError("fiber workspace is not open")
        metrics: list[FiberGridCellMetrics] = []
        for tau in self.request.source_grid.tau_values:
            counts = self._counts(tau)
            for coverage in self.request.source_grid.coverage_values:
                metrics.append(
                    _evaluate_cell(
                        self.exposure,
                        self.outcome,
                        self.nuisance_plan,
                        self.request,
                        self.cache,
                        self.score_workspace,
                        self._baseline(),
                        counts,
                        tau,
                        coverage,
                        chunk_size=self.chunk_size,
                        retain_arrays=False,
                    ).metrics
                )
        return tuple(metrics)

    def evaluate_cell(
        self,
        tau: float,
        coverage: int,
        *,
        retain_arrays: bool,
    ) -> FiberGridCellComputation:
        if self.cache is None or self.score_workspace is None:
            raise ReferenceFiberBackendError("fiber workspace is not open")
        counts = self._counts(tau)
        return _evaluate_cell(
            self.exposure,
            self.outcome,
            self.nuisance_plan,
            self.request,
            self.cache,
            self.score_workspace,
            self._baseline(),
            counts,
            tau,
            coverage,
            chunk_size=self.chunk_size,
            retain_arrays=retain_arrays,
        )


class ReferenceFiberBackend:
    """Run one reference normative-fiber endpoint with formal/sensitive roles."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore | None = None,
        feature_chunk_size: int = 65_536,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore or None")
        if type(feature_chunk_size) is not int or feature_chunk_size < 1:
            raise ValueError("feature_chunk_size must be a positive integer")
        self.publisher = publisher
        self.artifact_store = artifact_store
        self.feature_chunk_size = feature_chunk_size

    def _inputs(
        self,
        request: ObservedRequest,
    ) -> tuple[np.ndarray, np.ndarray, NuisancePlan, np.ndarray]:
        if request.endpoint.model_family != "reference_fiber":
            raise ReferenceFiberBackendError(
                "ReferenceFiberBackend requires a reference_fiber endpoint"
            )
        if request.branch != "reference":
            raise ReferenceFiberBackendError("reference fiber branch must be 'reference'")
        if request.nuisance_inputs:
            raise ReferenceFiberBackendError(
                "reference fiber accepts baseline as its only nuisance covariate"
            )
        if request.feature_ids is None:
            raise ReferenceFiberBackendError("reference fiber requires feature_ids")
        exposure = _materialize(
            request.exposure,
            name="exposure",
            expected_axes=(request.subject_axis, request.feature_axis),
            expected_units=request.exposure_units,
            expected_space=request.exposure_space,
            artifact_store=self.artifact_store,
            memory_map=True,
        )
        outcome = _materialize(
            request.outcome,
            name="outcome",
            expected_axes=(request.subject_axis,),
            expected_units=(
                request.outcome.units if isinstance(request.outcome, ArtifactRef) else None
            ),
            expected_space=(
                request.outcome.space if isinstance(request.outcome, ArtifactRef) else None
            ),
            artifact_store=self.artifact_store,
            memory_map=False,
        )
        baseline = _materialize(
            request.baseline,
            name="baseline",
            expected_axes=(request.subject_axis,),
            expected_units=(
                request.baseline.units
                if isinstance(request.baseline, ArtifactRef)
                else None
            ),
            expected_space=(
                request.baseline.space
                if isinstance(request.baseline, ArtifactRef)
                else None
            ),
            artifact_store=self.artifact_store,
            memory_map=False,
        )
        feature_ids = _materialize(
            request.feature_ids,
            name="feature_ids",
            expected_axes=(request.feature_axis,),
            expected_units=(
                request.feature_ids.units
                if isinstance(request.feature_ids, ArtifactRef)
                else None
            ),
            expected_space=(
                request.feature_ids.space
                if isinstance(request.feature_ids, ArtifactRef)
                else None
            ),
            artifact_store=self.artifact_store,
            memory_map=True,
        )
        if exposure.ndim != 2 or exposure.shape != (
            request.subject_axis.count,
            request.feature_axis.count,
        ):
            raise ReferenceFiberBackendError("exposure shape changed after validation")
        outcome_vector = _finite_vector(outcome, "outcome", request.subject_axis.count)
        baseline_vector = _finite_vector(
            baseline,
            "baseline",
            request.subject_axis.count,
        )
        full_covariates = baseline_vector[:, None]
        nuisance_plan = NuisancePlan(
            full_covariates=full_covariates,
            fold_covariates=np.broadcast_to(
                full_covariates,
                (
                    request.subject_axis.count,
                    request.subject_axis.count,
                    1,
                ),
            ),
        )
        return (
            exposure,
            outcome_vector,
            nuisance_plan,
            _fiber_ids(feature_ids, request.feature_axis.count),
        )

    def run(self, request: ObservedRequest) -> ObservedResult:
        """Evaluate the full observed grid and resolve only a formal connectome."""

        if not isinstance(request, ObservedRequest):
            raise TypeError("request must be an ObservedRequest")
        exposure, outcome, nuisance_plan, fiber_ids = self._inputs(request)
        with _FiberWorkspace(
            exposure,
            outcome,
            nuisance_plan,
            fiber_ids,
            request,
            chunk_size=self.feature_chunk_size,
        ) as workspace:
            grid_metrics = workspace.evaluate_grid()
            grid_artifact = self.publisher.document(
                "grid_metrics.json",
                {
                    "endpoint_id": request.endpoint.identifier,
                    "branch": request.branch,
                    "connectome_role": request.connectome_role,
                    "cells": [cell.as_json_dict() for cell in grid_metrics],
                },
                kind="normative_fiber_grid_metrics",
            )
            if request.connectome_role == "sensitive":
                return ObservedResult(source=None, artifacts=(grid_artifact,))

            resolution = resolve_source(grid_metrics, request.source_grid)
            artifacts: list[ArtifactRef] = [grid_artifact]
            selected_axis: FeatureAxisRef | None = None
            selected_metrics: dict[str, Any] | None = None
            if resolution.selected is not None:
                selected = workspace.evaluate_cell(
                    resolution.selected.tau,
                    resolution.selected.coverage,
                    retain_arrays=True,
                )
                if selected.metrics.as_json_dict() != resolution.selected.as_json_dict():
                    raise ReferenceFiberBackendError(
                        "selected source recomputation differed from its scan result"
                    )
                if selected.arrays is None:
                    raise AssertionError("selected fiber arrays are missing")
                selected_axis, selected_artifacts = self._publish_selected(
                    request,
                    fiber_ids,
                    selected,
                )
                artifacts.extend(selected_artifacts)
                selected_metrics = selected.metrics.as_json_dict()
            resolution_artifact = self.publisher.document(
                "source_resolution.json",
                {
                    "source_status": resolution.source_status,
                    "prediction_status": resolution.prediction_status,
                    "threshold_source": resolution.threshold_source,
                    "selected_tau": (
                        resolution.selected.tau if resolution.selected is not None else None
                    ),
                    "selected_coverage": (
                        resolution.selected.coverage
                        if resolution.selected is not None
                        else None
                    ),
                    "adjacent_support": resolution.adjacent_support,
                    "failure_reason": resolution.failure_reason,
                    "selected_metrics": selected_metrics,
                },
                kind="normative_fiber_source_resolution",
            )
            artifacts.append(resolution_artifact)
            source = SourceRecord(
                endpoint=request.endpoint,
                input_status="valid",
                source_status=resolution.source_status,
                prediction_status=resolution.prediction_status,
                threshold_source=resolution.threshold_source,
                selected_tau=(
                    resolution.selected.tau if resolution.selected is not None else None
                ),
                selected_coverage=(
                    resolution.selected.coverage if resolution.selected is not None else None
                ),
                adjacent_support=resolution.adjacent_support,
                feature_axis=selected_axis,
                artifacts=tuple(artifacts),
            )
            return ObservedResult(source=source, artifacts=tuple(artifacts))

    def evaluate_sensitive_at_formal_source(
        self,
        request: ObservedRequest,
        formal_source: SourceRecord,
    ) -> SensitiveRecord:
        """Evaluate one sensitive connectome at the matching formal numeric source."""

        if not isinstance(request, ObservedRequest) or request.connectome_role != "sensitive":
            raise ReferenceFiberBackendError("sensitive evaluation requires a sensitive request")
        if not isinstance(formal_source, SourceRecord):
            raise TypeError("formal_source must be a SourceRecord")
        if formal_source.source_status not in {
            "pre_specified_accepted",
            "scan_fallback_accepted",
        }:
            raise ReferenceFiberBackendError(
                "sensitive evaluation requires an accepted formal source"
            )
        if formal_source.selected_tau is None or formal_source.selected_coverage is None:
            raise ReferenceFiberBackendError("formal source has no numeric tau/Coverage")
        if (
            request.endpoint.study_id != formal_source.endpoint.study_id
            or request.endpoint.scale_id != formal_source.endpoint.scale_id
            or request.endpoint.endpoint_binding_id
            != formal_source.endpoint.endpoint_binding_id
            or request.endpoint.model_family != formal_source.endpoint.model_family
        ):
            raise ReferenceFiberBackendError(
                "sensitive request does not match the formal endpoint identity"
            )
        if (
            formal_source.selected_tau not in request.source_grid.tau_values
            or formal_source.selected_coverage not in request.source_grid.coverage_values
        ):
            raise ReferenceFiberBackendError(
                "formal numeric tau/Coverage is outside the sensitive declared grid"
            )

        exposure, outcome, nuisance_plan, fiber_ids = self._inputs(request)
        with _FiberWorkspace(
            exposure,
            outcome,
            nuisance_plan,
            fiber_ids,
            request,
            chunk_size=self.feature_chunk_size,
        ) as workspace:
            computation = workspace.evaluate_cell(
                formal_source.selected_tau,
                formal_source.selected_coverage,
                retain_arrays=False,
            )
            metric_artifact = self.publisher.document(
                "formal_source_cell.json",
                {
                    "formal_endpoint_id": formal_source.endpoint.identifier,
                    "metrics": computation.metrics.as_json_dict(),
                },
                kind="normative_fiber_sensitive_cell_evidence",
            )
            artifacts: list[ArtifactRef] = [metric_artifact]
            feature_axis: FeatureAxisRef | None = None
            if computation.metrics.passes_hard_computability:
                retained = workspace.evaluate_cell(
                    formal_source.selected_tau,
                    formal_source.selected_coverage,
                    retain_arrays=True,
                )
                if retained.metrics.as_json_dict() != computation.metrics.as_json_dict():
                    raise ReferenceFiberBackendError(
                        "sensitive retained-cell recomputation changed its metrics"
                    )
                feature_axis, selected_artifacts = self._publish_selected(
                    request,
                    fiber_ids,
                    retained,
                    prefix="formal_source_",
                )
                artifacts.extend(selected_artifacts)
            return SensitiveRecord(
                endpoint=request.endpoint,
                formal_endpoint_id=formal_source.endpoint.identifier,
                evaluated_tau=formal_source.selected_tau,
                evaluated_coverage=formal_source.selected_coverage,
                input_status="valid",
                cell_computability_status=(
                    "computable"
                    if computation.metrics.passes_hard_computability
                    else "not_computable"
                ),
                prediction_status=computation.metrics.prediction_status,
                feature_axis=feature_axis,
                artifacts=tuple(artifacts),
            )

    def _publish_selected(
        self,
        request: ObservedRequest,
        parent_fiber_ids: np.ndarray,
        computation: FiberGridCellComputation,
        *,
        prefix: str = "selected_",
    ) -> tuple[FeatureAxisRef, tuple[ArtifactRef, ...]]:
        arrays = computation.arrays
        if arrays is None:
            raise ReferenceFiberBackendError("selected computation has no retained arrays")
        selected_ids = parent_fiber_ids[arrays.union_indices]
        selected_id_digest = hashlib.sha256(
            np.ascontiguousarray(selected_ids).tobytes(order="C")
        ).hexdigest()
        selected_axis_ref = AxisRef(
            axis_id=(
                f"{request.feature_axis.axis_id}:valid-union:"
                f"tau-{computation.metrics.tau:g}:coverage-{computation.metrics.coverage}"
            ),
            count=int(selected_ids.size),
            sha256=canonical_hash(
                {
                    "parent_axis_sha256": request.feature_axis.sha256,
                    "selected_fiber_ids_sha256": selected_id_digest,
                    "tau": computation.metrics.tau,
                    "coverage": computation.metrics.coverage,
                }
            ),
        )
        selected_axis = FeatureAxisRef(
            selected_axis_ref,
            "selected_normative_fiber_full_fold_valid_union",
        )
        candidate_ids = parent_fiber_ids[arrays.candidate_indices]
        candidate_axis = AxisRef(
            axis_id=(
                f"{request.feature_axis.axis_id}:candidate-full:"
                f"tau-{computation.metrics.tau:g}:coverage-{computation.metrics.coverage}"
            ),
            count=int(candidate_ids.size),
            sha256=canonical_hash(
                {
                    "parent_axis_sha256": request.feature_axis.sha256,
                    "candidate_fiber_ids_sha256": hashlib.sha256(
                        np.ascontiguousarray(candidate_ids).tobytes(order="C")
                    ).hexdigest(),
                    "tau": computation.metrics.tau,
                    "coverage": computation.metrics.coverage,
                }
            ),
        )
        artifacts: list[ArtifactRef] = [
            self.publisher.array(
                f"{prefix}candidate_fiber_ids.npy",
                candidate_ids,
                kind="normative_fiber_candidate_ids",
                axes=(candidate_axis,),
                units=None,
                space=request.exposure_space,
            ),
            self.publisher.array(
                f"{prefix}valid_fiber_ids.npy",
                selected_ids,
                kind="normative_fiber_valid_union_ids",
                axes=(selected_axis_ref,),
                units=None,
                space=request.exposure_space,
            ),
            self.publisher.array(
                f"{prefix}full_weights.npy",
                arrays.full_weights,
                kind="benefit_oriented_fiber_weights",
                axes=(selected_axis_ref,),
                units="coefficient",
                space=request.exposure_space,
            ),
            self.publisher.array(
                f"{prefix}fold_weights.npy",
                arrays.fold_weights,
                kind="loocv_benefit_oriented_fiber_weights",
                axes=(request.subject_axis, selected_axis_ref),
                units="coefficient",
                space=request.exposure_space,
            ),
            self.publisher.array(
                f"{prefix}fold_valid_masks.npy",
                arrays.fold_valid_masks,
                kind="loocv_valid_fiber_masks",
                axes=(request.subject_axis, selected_axis_ref),
                units=None,
                space=request.exposure_space,
            ),
            self.publisher.array(
                f"{prefix}full_scores.npy",
                arrays.full_scores,
                kind="normative_fiber_full_scores",
                axes=(request.subject_axis,),
                units="V/m",
                space=None,
            ),
            self.publisher.array(
                f"{prefix}fold_scores.npy",
                arrays.fold_scores,
                kind="normative_fiber_loocv_fold_scores",
                axes=(request.subject_axis, request.subject_axis),
                units="V/m",
                space=None,
            ),
            self.publisher.array(
                f"{prefix}heldout_scores.npy",
                arrays.heldout_scores,
                kind="normative_fiber_loocv_heldout_scores",
                axes=(request.subject_axis,),
                units="V/m",
                space=None,
            ),
            self.publisher.array(
                f"{prefix}heldout_predictions.npy",
                arrays.heldout_predictions,
                kind="normative_fiber_loocv_model_predictions",
                axes=(request.subject_axis,),
                units=(request.outcome.units if isinstance(request.outcome, ArtifactRef) else None),
                space=None,
            ),
            self.publisher.array(
                f"{prefix}baseline_predictions.npy",
                arrays.baseline_predictions,
                kind="normative_fiber_loocv_baseline_predictions",
                axes=(request.subject_axis,),
                units=(request.outcome.units if isinstance(request.outcome, ArtifactRef) else None),
                space=None,
            ),
            self.publisher.document(
                f"{prefix}fiber_score_support.json",
                {
                    "full_sample": arrays.full_support,
                    "folds": [
                        {"heldout_index": index, **support}
                        for index, support in enumerate(arrays.fold_support)
                    ],
                },
                kind="normative_fiber_score_support",
            ),
        ]
        for side, values in (
            ("sweet", arrays.full_sweet_fiber_ids),
            ("sour", arrays.full_sour_fiber_ids),
        ):
            if values.size == 0:
                continue
            side_axis = AxisRef(
                axis_id=f"{selected_axis_ref.axis_id}:{side}-selected",
                count=int(values.size),
                sha256=canonical_hash(
                    {
                        "selected_axis_sha256": selected_axis_ref.sha256,
                        "side": side,
                        "fiber_ids": values.tolist(),
                    }
                ),
            )
            artifacts.append(
                self.publisher.array(
                    f"{prefix}{side}_fiber_ids.npy",
                    values,
                    kind=f"normative_fiber_{side}_selected_ids",
                    axes=(side_axis,),
                    units=None,
                    space=request.exposure_space,
                )
            )
        return selected_axis, tuple(artifacts)


__all__ = [
    "FiberGridCellComputation",
    "FiberGridCellMetrics",
    "FiberSelectedArrays",
    "ReferenceFiberBackend",
    "ReferenceFiberBackendError",
]
