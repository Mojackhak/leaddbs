"""Cross-component exposure preparation functions."""

from .branch_resolver import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    BranchResolverError,
    branch_failure_record,
    branch_intended_role,
    branch_record_from_observed,
)
from .reference_overlap import (
    ReferenceOverlapError,
    ReferenceOverlapResult,
    prepare_reference_overlap,
)

__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "BranchResolverError",
    "ReferenceOverlapError",
    "ReferenceOverlapResult",
    "branch_failure_record",
    "branch_intended_role",
    "branch_record_from_observed",
    "prepare_reference_overlap",
]
