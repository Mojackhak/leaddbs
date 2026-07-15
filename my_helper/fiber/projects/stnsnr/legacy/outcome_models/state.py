"""Pure source, branch-role, and final-model state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


ACCEPTED_SOURCE_STATUSES = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
PREDICTION_STATUSES = frozenset({"error_predictive", "error_nonpredictive"})


@dataclass(frozen=True)
class SourceResult:
    input_status: str
    source_status: str
    prediction_status: str
    selected_tau: float | None
    selected_coverage: int | None
    adjacent_support: int | None

    @property
    def accepted(self) -> bool:
        return self.input_status == "valid" and self.source_status in ACCEPTED_SOURCE_STATUSES

    @property
    def unavailable(self) -> bool:
        return not self.accepted


@dataclass(frozen=True)
class BranchResult:
    branch: str
    input_status: str
    source: SourceResult | None

    @property
    def input_valid(self) -> bool:
        return self.input_status == "valid" and self.source is not None and self.source.input_status == "valid"


@dataclass(frozen=True)
class IntendedBranches:
    intended_primary_branch: str
    executable_branches: tuple[str, ...]
    delta_hfscore_role: str


@dataclass(frozen=True)
class FinalModelDecision:
    intended_primary_branch: str
    final_branch: str | None
    final_role: str
    final_status: str
    failure_reasons: tuple[str, ...]


def intended_ulf_branches(hf: SourceResult, *, delta_hf_input_valid: bool) -> IntendedBranches:
    """Resolve HF-derived ULF branch roles without consulting ULF outcomes."""
    if hf.input_status != "valid":
        return IntendedBranches(
            intended_primary_branch="none",
            executable_branches=(),
            delta_hfscore_role="not_run_reference_dependency_failure",
        )

    if hf.source_status == "absent_no_stable_grid":
        return IntendedBranches(
            intended_primary_branch="no_delta_hf",
            executable_branches=("no_delta_hf",),
            delta_hfscore_role="not_run_no_stable_hf_source",
        )

    if not hf.accepted:
        raise ValueError("a valid HF input requires an accepted source or absent_no_stable_grid")

    if hf.prediction_status == "error_predictive":
        executable = ("no_delta_hf", "delta_hf_adjusted") if delta_hf_input_valid else ("no_delta_hf",)
        role = "primary_error_predictive_hf_adjustment" if delta_hf_input_valid else "primary_input_failure"
        return IntendedBranches("delta_hf_adjusted", executable, role)

    if hf.prediction_status == "error_nonpredictive":
        executable = ("no_delta_hf", "delta_hf_adjusted") if delta_hf_input_valid else ("no_delta_hf",)
        role = (
            "stable_error_nonpredictive_hf_adjustment_sensitivity"
            if delta_hf_input_valid
            else "not_run_invalid_delta_hfscore"
        )
        return IntendedBranches("no_delta_hf", executable, role)

    raise ValueError("an accepted HF source requires error_predictive or error_nonpredictive status")


def _prediction_final_status(prediction_status: str) -> str:
    if prediction_status == "error_predictive":
        return "final_model_error_predictive"
    if prediction_status == "error_nonpredictive":
        return "final_model_error_nonpredictive"
    raise ValueError(f"accepted source has invalid prediction status: {prediction_status!r}")


def _branch_input_failure(result: BranchResult | None) -> bool:
    return result is None or not result.input_valid


def _branch_execution_failure(result: BranchResult | None) -> bool:
    return bool(
        result is not None
        and (
            result.input_status == "execution_failure"
            or (result.source is not None and result.source.input_status == "execution_failure")
        )
    )


def _branch_source_absent(result: BranchResult | None) -> bool:
    return bool(
        result is not None
        and result.input_valid
        and result.source is not None
        and result.source.source_status == "absent_no_stable_grid"
    )


def _failure_reason(result: BranchResult | None, branch: str) -> str:
    if result is None:
        return f"{branch}:missing_branch_result"
    if result.input_status != "valid":
        return f"{branch}:{result.input_status}"
    if result.source is None:
        return f"{branch}:missing_source_result"
    if result.source.input_status != "valid":
        return f"{branch}:{result.source.input_status}"
    return f"{branch}:source_not_accepted"


def realize_ulf_final(
    hf: SourceResult,
    branches: Mapping[str, BranchResult],
) -> FinalModelDecision:
    """Realize one ULF final model or an explicit no-final terminal state."""
    adjusted = branches.get("delta_hf_adjusted")
    delta_input_valid = adjusted is not None and adjusted.input_valid
    intended = intended_ulf_branches(hf, delta_hf_input_valid=delta_input_valid)
    primary_name = intended.intended_primary_branch
    if primary_name == "none":
        return FinalModelDecision(
            intended_primary_branch="none",
            final_branch=None,
            final_role="no_final_model",
            final_status="dependency_failure",
            failure_reasons=(f"hf_source:{hf.input_status}",),
        )
    primary = branches.get(primary_name)

    if _branch_execution_failure(primary):
        return FinalModelDecision(
            intended_primary_branch=primary_name,
            final_branch=None,
            final_role="no_final_model",
            final_status="execution_failure",
            failure_reasons=(_failure_reason(primary, primary_name),),
        )

    if not _branch_input_failure(primary) and primary is not None and primary.source is not None:
        if primary.source.accepted:
            return FinalModelDecision(
                intended_primary_branch=primary_name,
                final_branch=primary_name,
                final_role="primary",
                final_status=_prediction_final_status(primary.source.prediction_status),
                failure_reasons=(),
            )

    if primary_name == "delta_hf_adjusted" and (
        _branch_input_failure(primary) or _branch_source_absent(primary)
    ):
        fallback = branches.get("no_delta_hf")
        if _branch_execution_failure(fallback):
            return FinalModelDecision(
                intended_primary_branch=primary_name,
                final_branch=None,
                final_role="no_final_model",
                final_status="execution_failure",
                failure_reasons=(_failure_reason(primary, primary_name), _failure_reason(fallback, "no_delta_hf")),
            )
        if fallback is not None and fallback.input_valid and fallback.source is not None and fallback.source.accepted:
            return FinalModelDecision(
                intended_primary_branch=primary_name,
                final_branch="no_delta_hf",
                final_role="fallback_final",
                final_status=_prediction_final_status(fallback.source.prediction_status),
                failure_reasons=(_failure_reason(primary, primary_name),),
            )
        reasons = [_failure_reason(primary, primary_name), _failure_reason(fallback, "no_delta_hf")]
        fallback_absent = (
            _branch_source_absent(fallback)
        )
        return FinalModelDecision(
            intended_primary_branch=primary_name,
            final_branch=None,
            final_role="no_final_model",
            final_status=(
                "no_final_model_absent_no_stable_grid" if fallback_absent else "no_final_model_input_failure"
            ),
            failure_reasons=tuple(reasons),
        )

    if _branch_source_absent(primary):
        return FinalModelDecision(
            intended_primary_branch=primary_name,
            final_branch=None,
            final_role="no_final_model",
            final_status="no_final_model_absent_no_stable_grid",
            failure_reasons=(f"{primary_name}:absent_no_stable_grid",),
        )

    return FinalModelDecision(
        intended_primary_branch=primary_name,
        final_branch=None,
        final_role="no_final_model",
        final_status="no_final_model_input_failure",
        failure_reasons=(_failure_reason(primary, primary_name),),
    )
