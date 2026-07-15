"""Pure branch-planning and one-way final-model state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..contracts.identity import EndpointKey
from ..contracts.records import BranchRecord, ReferenceDependencyRecord


NO_DELTA_BRANCH = "no_delta_reference"
ADJUSTED_BRANCH = "delta_reference_adjusted"
ACCEPTED = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})

_BRANCH_ORDER = (NO_DELTA_BRANCH, ADJUSTED_BRANCH)
_FALLBACK_FAILURES = frozenset({"input_failure", "design_failure", "absent_no_stable_grid"})
_EXECUTION_STAGES = frozenset({"execution", "execution_failure"})


class StateError(ValueError):
    """Raised when state-machine inputs violate the typed workflow contract."""


@dataclass(frozen=True)
class BranchPlan:
    """Immutable branch intent derived only from the reference dependency."""

    endpoint: EndpointKey
    status: str
    intended_branch: str | None
    attempted_branches: tuple[str, ...]
    intended_status: str
    fallback_eligible: bool
    failure_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, EndpointKey) or not self.endpoint.model_family.startswith("addon_"):
            raise StateError("branch plan endpoint must identify an add-on model")
        attempted = tuple(self.attempted_branches)
        reasons = tuple(str(reason) for reason in self.failure_reasons)
        object.__setattr__(self, "attempted_branches", attempted)
        object.__setattr__(self, "failure_reasons", reasons)
        if attempted != tuple(branch for branch in _BRANCH_ORDER if branch in attempted):
            raise StateError("attempted_branches must use unique canonical branch order")
        if self.status == "dependency_failure":
            if (
                self.intended_branch is not None
                or attempted
                or self.intended_status != "dependency_failure"
                or self.fallback_eligible
            ):
                raise StateError("dependency-failure plans cannot contain branch work")
            return
        if self.status != "ready":
            raise StateError(f"unsupported branch plan status {self.status!r}")
        if self.intended_branch not in _BRANCH_ORDER:
            raise StateError("ready branch plans require an intended branch")
        if self.intended_status not in {"pending", "input_failure"}:
            raise StateError(f"unsupported intended branch status {self.intended_status!r}")
        if self.intended_status == "pending" and self.intended_branch not in attempted:
            raise StateError("a pending intended branch must be attempted")
        if self.intended_status == "input_failure" and self.intended_branch in attempted:
            raise StateError("an input-failed intended branch cannot be attempted")
        if self.fallback_eligible != (self.intended_branch == ADJUSTED_BRANCH):
            raise StateError("only an adjusted intended branch can be fallback-eligible")


@dataclass(frozen=True)
class FinalDecision:
    """Unique realized branch or an explicit terminal no-final decision."""

    final_branch: str | None
    final_role: str
    final_status: str
    intended_branch: str | None
    selected_branch: BranchRecord | None
    failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        reasons = tuple(str(reason) for reason in self.failure_reasons)
        object.__setattr__(self, "failure_reasons", reasons)
        if self.final_branch is None:
            if self.final_role != "no_final_model" or self.selected_branch is not None:
                raise StateError("no-final decisions cannot select a branch")
            if self.final_status not in {"dependency_failure", "execution_failure", "no_final_model"}:
                raise StateError(f"unsupported no-final status {self.final_status!r}")
            if not reasons:
                raise StateError("no-final decisions require a failure reason")
            return
        if self.final_branch not in _BRANCH_ORDER:
            raise StateError(f"unsupported final branch {self.final_branch!r}")
        if self.final_role not in {"primary", "fallback_final"}:
            raise StateError(f"unsupported realized final role {self.final_role!r}")
        expected_status = "final_model_realized" if self.final_role == "primary" else "fallback_final_realized"
        if self.final_status != expected_status:
            raise StateError("realized final status does not match its role")
        if self.selected_branch is None or self.selected_branch.branch != self.final_branch:
            raise StateError("realized final must contain its selected BranchRecord")
        if self.final_role == "primary" and reasons:
            raise StateError("primary final decisions cannot contain failure reasons")

    @property
    def realization_role(self) -> str:
        """Return the role name used by ``FinalModelRecord``."""
        return self.final_role


@dataclass(frozen=True)
class _BranchAssessment:
    status: str
    reason: str | None
    record: BranchRecord | None


def _dependency_failure(reference: ReferenceDependencyRecord, reason: str) -> BranchPlan:
    return BranchPlan(
        endpoint=reference.addon_endpoint,
        status="dependency_failure",
        intended_branch=None,
        attempted_branches=(),
        intended_status="dependency_failure",
        fallback_eligible=False,
        failure_reasons=(reason,),
    )


def derive_branch_plan(reference: ReferenceDependencyRecord, delta_status: str) -> BranchPlan:
    """Derive deterministic add-on branch intent without consulting branch outcomes."""
    if not isinstance(reference, ReferenceDependencyRecord):
        raise StateError("reference must be a ReferenceDependencyRecord")
    if reference.dependency_status != "ready":
        return _dependency_failure(
            reference,
            f"reference_dependency:{reference.dependency_status}",
        )
    if reference.reference_source is None:
        return _dependency_failure(reference, "reference_dependency:missing_reference_source")

    source = reference.reference_source
    if source.source_status == "absent_no_stable_grid":
        return BranchPlan(
            endpoint=reference.addon_endpoint,
            status="ready",
            intended_branch=NO_DELTA_BRANCH,
            attempted_branches=(NO_DELTA_BRANCH,),
            intended_status="pending",
            fallback_eligible=False,
        )
    if source.source_status not in ACCEPTED:
        raise StateError(f"ready reference has unsupported source_status {source.source_status!r}")

    normalized_delta_status = str(delta_status).strip()
    if not normalized_delta_status:
        raise StateError("delta_status must be nonempty")
    delta_valid = normalized_delta_status == "valid"
    if source.prediction_status == "error_predictive":
        if delta_valid:
            return BranchPlan(
                endpoint=reference.addon_endpoint,
                status="ready",
                intended_branch=ADJUSTED_BRANCH,
                attempted_branches=_BRANCH_ORDER,
                intended_status="pending",
                fallback_eligible=True,
            )
        return BranchPlan(
            endpoint=reference.addon_endpoint,
            status="ready",
            intended_branch=ADJUSTED_BRANCH,
            attempted_branches=(NO_DELTA_BRANCH,),
            intended_status="input_failure",
            fallback_eligible=True,
            failure_reasons=(f"{ADJUSTED_BRANCH}:delta_status={normalized_delta_status}",),
        )
    if source.prediction_status == "error_nonpredictive":
        attempted = _BRANCH_ORDER if delta_valid else (NO_DELTA_BRANCH,)
        return BranchPlan(
            endpoint=reference.addon_endpoint,
            status="ready",
            intended_branch=NO_DELTA_BRANCH,
            attempted_branches=attempted,
            intended_status="pending",
            fallback_eligible=False,
        )
    raise StateError(
        "accepted reference source requires error_predictive or error_nonpredictive prediction_status"
    )


def _execution_reason(branch: str, record: BranchRecord) -> str | None:
    if record.input_status == "execution_failure":
        return f"{branch}:input_status=execution_failure"
    if record.nuisance_design_status == "execution_failure":
        return f"{branch}:nuisance_design_status=execution_failure"
    if record.source is not None and record.source.input_status == "execution_failure":
        return f"{branch}:source_input_status=execution_failure"
    if record.failure_stage in _EXECUTION_STAGES:
        return f"{branch}:failure_stage={record.failure_stage}"
    return None


def _assess_branch(branch: str, record: BranchRecord | None) -> _BranchAssessment:
    if record is None:
        return _BranchAssessment("input_failure", f"{branch}:missing_branch_record", None)
    execution_reason = _execution_reason(branch, record)
    if execution_reason is not None:
        return _BranchAssessment("execution_failure", execution_reason, record)
    if record.input_status != "valid":
        return _BranchAssessment("input_failure", f"{branch}:input_status={record.input_status}", record)
    if record.nuisance_design_status != "valid":
        return _BranchAssessment(
            "design_failure",
            f"{branch}:nuisance_design_status={record.nuisance_design_status}",
            record,
        )
    if record.source is None:
        return _BranchAssessment("input_failure", f"{branch}:missing_source_record", record)
    if record.source.input_status != "valid":
        return _BranchAssessment(
            "input_failure",
            f"{branch}:source_input_status={record.source.input_status}",
            record,
        )
    if record.source.source_status == "absent_no_stable_grid":
        return _BranchAssessment(
            "absent_no_stable_grid",
            f"{branch}:source_status=absent_no_stable_grid",
            record,
        )
    if record.source.source_status in ACCEPTED:
        return _BranchAssessment("accepted", None, record)
    raise StateError(f"branch {branch!r} has unsupported source_status {record.source.source_status!r}")


def _validate_branches(branch_plan: BranchPlan, branches: Mapping[str, BranchRecord]) -> None:
    for key, record in branches.items():
        if key not in _BRANCH_ORDER:
            raise StateError(f"unsupported branch mapping key {key!r}")
        if not isinstance(record, BranchRecord):
            raise StateError(f"branch mapping value for {key!r} must be a BranchRecord")
        if record.branch != key:
            raise StateError(f"branch mapping key {key!r} does not match record branch {record.branch!r}")
        if record.endpoint != branch_plan.endpoint:
            raise StateError(f"branch {key!r} endpoint does not match the branch plan endpoint")


def _no_final(
    branch_plan: BranchPlan,
    final_status: str,
    reasons: tuple[str, ...],
) -> FinalDecision:
    return FinalDecision(
        final_branch=None,
        final_role="no_final_model",
        final_status=final_status,
        intended_branch=branch_plan.intended_branch,
        selected_branch=None,
        failure_reasons=reasons,
    )


def realize_final(
    branch_plan: BranchPlan,
    branches: Mapping[str, BranchRecord],
) -> FinalDecision:
    """Realize the intended branch or the sole permitted no-delta fallback."""
    if not isinstance(branch_plan, BranchPlan):
        raise StateError("branch_plan must be a BranchPlan")
    if not isinstance(branches, Mapping):
        raise StateError("branches must be a mapping")
    _validate_branches(branch_plan, branches)

    if branch_plan.status == "dependency_failure":
        return _no_final(branch_plan, "dependency_failure", branch_plan.failure_reasons)

    intended_name = branch_plan.intended_branch
    if intended_name is None:
        raise StateError("ready branch plan has no intended branch")
    if branch_plan.intended_status == "input_failure":
        intended = _BranchAssessment(
            "input_failure",
            branch_plan.failure_reasons[0],
            None,
        )
    else:
        intended = _assess_branch(intended_name, branches.get(intended_name))

    if intended.status == "execution_failure":
        assert intended.reason is not None
        return _no_final(branch_plan, "execution_failure", (intended.reason,))
    if intended.status == "accepted":
        assert intended.record is not None
        return FinalDecision(
            final_branch=intended_name,
            final_role="primary",
            final_status="final_model_realized",
            intended_branch=intended_name,
            selected_branch=intended.record,
            failure_reasons=(),
        )

    if (
        branch_plan.intended_branch == ADJUSTED_BRANCH
        and branch_plan.fallback_eligible
        and intended.status in _FALLBACK_FAILURES
    ):
        alternate = _assess_branch(NO_DELTA_BRANCH, branches.get(NO_DELTA_BRANCH))
        if alternate.status == "execution_failure":
            assert intended.reason is not None and alternate.reason is not None
            return _no_final(
                branch_plan,
                "execution_failure",
                (intended.reason, alternate.reason),
            )
        if (
            alternate.status == "accepted"
            and alternate.record is not None
            and alternate.record.source is not None
            and alternate.record.source.source_status in ACCEPTED
        ):
            assert intended.reason is not None
            return FinalDecision(
                final_branch=NO_DELTA_BRANCH,
                final_role="fallback_final",
                final_status="fallback_final_realized",
                intended_branch=ADJUSTED_BRANCH,
                selected_branch=alternate.record,
                failure_reasons=(intended.reason,),
            )
        assert intended.reason is not None and alternate.reason is not None
        return _no_final(
            branch_plan,
            "no_final_model",
            (intended.reason, alternate.reason),
        )

    assert intended.reason is not None
    return _no_final(branch_plan, "no_final_model", (intended.reason,))
