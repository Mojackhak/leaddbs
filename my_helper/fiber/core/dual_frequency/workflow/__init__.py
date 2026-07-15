"""Pure planning and final-realization APIs for dual-frequency workflows.

The workflow state layer consumes immutable contract records and performs no
filesystem access or numerical computation. Its public API is exported here so
callers do not need to depend on the implementation module layout.
"""

from .state import (
    ACCEPTED,
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    BranchPlan,
    FinalDecision,
    StateError,
    derive_branch_plan,
    realize_final,
)

__all__ = [
    "ACCEPTED",
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "BranchPlan",
    "FinalDecision",
    "StateError",
    "derive_branch_plan",
    "realize_final",
]
