"""Shared full-sample and fold-specific nuisance-design construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


NO_DELTA_BRANCH = "no_delta_reference"
ADJUSTED_BRANCH = "delta_reference_adjusted"


class NuisancePlanError(ValueError):
    """Expected branch-local nuisance input or design failure."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = str(status)
        self.detail = str(detail)


@dataclass(frozen=True)
class NuisancePlan:
    """Full-sample and fold-specific nuisance covariates for one endpoint."""

    full_covariates: np.ndarray
    fold_covariates: np.ndarray

    def __post_init__(self) -> None:
        full = np.array(self.full_covariates, dtype=np.float64, copy=True)
        folds = np.array(self.fold_covariates, dtype=np.float64, copy=True)
        if full.ndim != 2 or not all(dimension > 0 for dimension in full.shape):
            raise NuisancePlanError(
                "invalid_nuisance_design",
                "full nuisance covariates must be a nonempty subject-by-covariate matrix",
            )
        expected = (full.shape[0], full.shape[0], full.shape[1])
        if folds.shape != expected:
            raise NuisancePlanError(
                "invalid_nuisance_design",
                "fold nuisance covariates must have shape fold-by-subject-by-covariate",
            )
        if not np.all(np.isfinite(full)) or not np.all(np.isfinite(folds)):
            raise NuisancePlanError(
                "invalid_nuisance_design",
                "nuisance covariates must contain only finite values",
            )
        full.flags.writeable = False
        folds.flags.writeable = False
        object.__setattr__(self, "full_covariates", full)
        object.__setattr__(self, "fold_covariates", folds)


def _finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise NuisancePlanError(
            "invalid_nuisance_design",
            f"{name} must be a finite subject vector",
        )
    return array


def _design_is_valid(covariates: np.ndarray, rows: np.ndarray) -> bool:
    design = np.column_stack([np.ones(rows.size), covariates[rows]])
    return bool(
        rows.size > design.shape[1]
        and np.linalg.matrix_rank(design) == design.shape[1]
    )


def _standardize(value: np.ndarray, training_rows: np.ndarray) -> np.ndarray:
    training = value[training_rows]
    center = float(np.mean(training))
    scale = float(np.std(training, ddof=0))
    if not np.isfinite(center) or not np.isfinite(scale) or scale <= 0:
        raise NuisancePlanError(
            "invalid_delta_reference_scaling",
            "DeltaReferenceScore is constant or nonfinite in a required training set",
        )
    standardized = (value - center) / scale
    if not np.all(np.isfinite(standardized)):
        raise NuisancePlanError(
            "invalid_delta_reference_scaling",
            "DeltaReferenceScore standardization produced nonfinite values",
        )
    return standardized


def build_addon_nuisance_plan(
    reference_outcome: np.ndarray,
    branch: str,
    *,
    delta_full_scores: np.ndarray | None = None,
    delta_fold_scores: np.ndarray | None = None,
) -> NuisancePlan:
    """Build one validated add-on nuisance design for every required fold."""

    reference = np.asarray(reference_outcome, dtype=np.float64)
    if reference.ndim != 1 or not np.all(np.isfinite(reference)):
        raise NuisancePlanError(
            "invalid_nuisance_design",
            "reference outcome must be a finite subject vector",
        )
    n_subjects = reference.size
    if n_subjects < 3:
        raise NuisancePlanError(
            "invalid_nuisance_design",
            "nuisance design requires at least three subjects",
        )
    all_rows = np.arange(n_subjects)

    if branch == NO_DELTA_BRANCH:
        if delta_full_scores is not None or delta_fold_scores is not None:
            raise NuisancePlanError(
                "invalid_nuisance_design",
                "no-delta branch cannot receive DeltaReferenceScore inputs",
            )
        full = reference[:, None]
        folds = np.broadcast_to(full, (n_subjects, n_subjects, 1)).copy()
    elif branch == ADJUSTED_BRANCH:
        if delta_full_scores is None or delta_fold_scores is None:
            raise NuisancePlanError(
                "invalid_delta_reference_scaling",
                "adjusted branch requires full and fold DeltaReferenceScore inputs",
            )
        delta_full = _finite_vector(delta_full_scores, "delta_full_scores", n_subjects)
        delta_folds = np.asarray(delta_fold_scores, dtype=np.float64)
        if delta_folds.shape != (n_subjects, n_subjects) or not np.all(
            np.isfinite(delta_folds)
        ):
            raise NuisancePlanError(
                "invalid_delta_reference_scaling",
                "delta_fold_scores must be a finite fold-by-subject matrix",
            )
        full = np.column_stack([reference, _standardize(delta_full, all_rows)])
        folds = np.empty((n_subjects, n_subjects, 2), dtype=np.float64)
        for heldout in range(n_subjects):
            training = np.delete(all_rows, heldout)
            folds[heldout, :, 0] = reference
            folds[heldout, :, 1] = _standardize(delta_folds[heldout], training)
    else:
        raise NuisancePlanError(
            "invalid_nuisance_design",
            f"unsupported add-on branch {branch!r}",
        )

    if not _design_is_valid(full, all_rows):
        raise NuisancePlanError(
            "invalid_nuisance_design",
            "full-sample branch nuisance design is rank deficient",
        )
    for heldout in range(n_subjects):
        training = np.delete(all_rows, heldout)
        if not _design_is_valid(folds[heldout], training):
            raise NuisancePlanError(
                "invalid_nuisance_design",
                f"branch nuisance design is rank deficient for held-out index {heldout}",
            )
    return NuisancePlan(full_covariates=full, fold_covariates=folds)


__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "NuisancePlan",
    "NuisancePlanError",
    "build_addon_nuisance_plan",
]
