"""Generic normative-connectome fiber backends."""

from .addon import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    AddonFiberBackend,
    AddonFiberBackendError,
    AddonFiberDesignError,
    AddonFiberExposure,
    prepare_addon_fiber_exposure,
)
from .coverage import (
    FiberCoverageError,
    candidate_mask,
    coverage_counts,
    heldout_fold_candidate_mask,
)
from .scoring import (
    FiberScoreError,
    FiberScoreResult,
    score_signed_fibers,
    score_support_fields,
)
from .reference import (
    FiberGridCellComputation,
    FiberGridCellMetrics,
    FiberSelectedArrays,
    ReferenceFiberBackend,
    ReferenceFiberBackendError,
)

__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "AddonFiberBackend",
    "AddonFiberBackendError",
    "AddonFiberDesignError",
    "AddonFiberExposure",
    "FiberCoverageError",
    "FiberGridCellComputation",
    "FiberGridCellMetrics",
    "FiberScoreError",
    "FiberScoreResult",
    "FiberSelectedArrays",
    "ReferenceFiberBackend",
    "ReferenceFiberBackendError",
    "candidate_mask",
    "coverage_counts",
    "heldout_fold_candidate_mask",
    "prepare_addon_fiber_exposure",
    "score_signed_fibers",
    "score_support_fields",
]
