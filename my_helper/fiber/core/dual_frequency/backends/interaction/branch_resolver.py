"""Convert add-on observed outcomes into branch-local immutable records."""

from __future__ import annotations

from ...contracts import BranchRecord, EndpointKey, ObservedResult


NO_DELTA_BRANCH = "no_delta_reference"
ADJUSTED_BRANCH = "delta_reference_adjusted"
BRANCHES = frozenset({NO_DELTA_BRANCH, ADJUSTED_BRANCH})


class BranchResolverError(ValueError):
    """Raised when branch role or result inputs contradict the workflow state."""


def branch_intended_role(
    branch: str,
    *,
    intended_branch: str,
    fallback_eligible: bool,
) -> str:
    """Return primary, fallback-eligible, or comparison without using outcomes."""

    if branch not in BRANCHES or intended_branch not in BRANCHES:
        raise BranchResolverError("branch and intended_branch must be canonical add-on branches")
    if branch == intended_branch:
        return "primary"
    if (
        branch == NO_DELTA_BRANCH
        and intended_branch == ADJUSTED_BRANCH
        and fallback_eligible
    ):
        return "fallback_eligible"
    return "comparison"


def branch_record_from_observed(
    endpoint: EndpointKey,
    branch: str,
    result: ObservedResult,
    *,
    intended_branch: str,
    fallback_eligible: bool,
) -> BranchRecord:
    """Wrap one completed branch without assigning a final-model role."""

    if not isinstance(result, ObservedResult) or result.source is None:
        raise BranchResolverError("completed add-on observation requires a source record")
    if result.source.endpoint != endpoint:
        raise BranchResolverError("observed source endpoint does not match the branch endpoint")
    return BranchRecord(
        endpoint=endpoint,
        branch=branch,
        intended_role=branch_intended_role(
            branch,
            intended_branch=intended_branch,
            fallback_eligible=fallback_eligible,
        ),
        input_status="valid",
        nuisance_design_status="valid",
        source=result.source,
        artifacts=result.artifacts,
    )


def branch_failure_record(
    endpoint: EndpointKey,
    branch: str,
    *,
    intended_branch: str,
    fallback_eligible: bool,
    input_status: str,
    nuisance_design_status: str,
    failure_stage: str,
    failure_detail: str,
) -> BranchRecord:
    """Record an expected branch-local input or design failure explicitly."""

    return BranchRecord(
        endpoint=endpoint,
        branch=branch,
        intended_role=branch_intended_role(
            branch,
            intended_branch=intended_branch,
            fallback_eligible=fallback_eligible,
        ),
        input_status=input_status,
        nuisance_design_status=nuisance_design_status,
        source=None,
        failure_stage=failure_stage,
        failure_detail=failure_detail,
    )


__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "BranchResolverError",
    "branch_failure_record",
    "branch_intended_role",
    "branch_record_from_observed",
]
