"""Tests for the pure HF-to-ULF branch and final-model state machine."""

from __future__ import annotations

import unittest

from outcome_models.state import (
    BranchResult,
    SourceResult,
    intended_ulf_branches,
    realize_ulf_final,
)


def source(
    source_status: str,
    prediction_status: str,
    *,
    input_status: str = "valid",
    tau: float | None = 200.0,
) -> SourceResult:
    return SourceResult(
        input_status=input_status,
        source_status=source_status,
        prediction_status=prediction_status,
        selected_tau=tau,
        selected_coverage=5 if tau is not None else None,
        adjacent_support=2 if tau is not None else None,
    )


def branch(name: str, result: SourceResult | None, *, input_status: str = "valid") -> BranchResult:
    return BranchResult(branch=name, input_status=input_status, source=result)


class StateMachineTests(unittest.TestCase):
    def test_hf_predictive_intends_adjusted_and_runs_both_branches(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        decision = intended_ulf_branches(hf, delta_hf_input_valid=True)
        self.assertEqual(decision.intended_primary_branch, "delta_hf_adjusted")
        self.assertEqual(decision.executable_branches, ("no_delta_hf", "delta_hf_adjusted"))
        self.assertEqual(decision.delta_hfscore_role, "primary_error_predictive_hf_adjustment")

    def test_hf_nonpredictive_intends_no_delta_and_adjusted_is_sensitivity(self) -> None:
        hf = source("scan_fallback_accepted", "error_nonpredictive")
        decision = intended_ulf_branches(hf, delta_hf_input_valid=True)
        self.assertEqual(decision.intended_primary_branch, "no_delta_hf")
        self.assertEqual(decision.executable_branches, ("no_delta_hf", "delta_hf_adjusted"))
        self.assertEqual(decision.delta_hfscore_role, "stable_error_nonpredictive_hf_adjustment_sensitivity")

    def test_hf_unavailable_runs_no_delta_only(self) -> None:
        for hf in (
            source("absent_no_stable_grid", "not_applicable", tau=None),
            source("", "not_applicable", input_status="input_failure", tau=None),
        ):
            with self.subTest(hf=hf):
                decision = intended_ulf_branches(hf, delta_hf_input_valid=False)
                self.assertEqual(decision.intended_primary_branch, "no_delta_hf")
                self.assertEqual(decision.executable_branches, ("no_delta_hf",))
                self.assertEqual(decision.delta_hfscore_role, "not_run_no_stable_hf_source")

    def test_adjusted_input_failure_preserves_intended_role_and_allows_no_delta_fallback(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        intended = intended_ulf_branches(hf, delta_hf_input_valid=False)
        self.assertEqual(intended.intended_primary_branch, "delta_hf_adjusted")
        self.assertEqual(intended.executable_branches, ("no_delta_hf",))

        final = realize_ulf_final(
            hf,
            {
                "delta_hf_adjusted": branch("delta_hf_adjusted", None, input_status="invalid_delta_hfscore"),
                "no_delta_hf": branch(
                    "no_delta_hf",
                    source("pre_specified_accepted", "error_nonpredictive"),
                ),
            },
        )
        self.assertEqual(final.intended_primary_branch, "delta_hf_adjusted")
        self.assertEqual(final.final_branch, "no_delta_hf")
        self.assertEqual(final.final_role, "fallback_final")
        self.assertEqual(final.final_status, "final_model_error_nonpredictive")

    def test_accepted_intended_branch_becomes_unique_primary(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        final = realize_ulf_final(
            hf,
            {
                "delta_hf_adjusted": branch(
                    "delta_hf_adjusted",
                    source("scan_fallback_accepted", "error_predictive", tau=220),
                ),
                "no_delta_hf": branch(
                    "no_delta_hf",
                    source("pre_specified_accepted", "error_nonpredictive"),
                ),
            },
        )
        self.assertEqual(final.final_branch, "delta_hf_adjusted")
        self.assertEqual(final.final_role, "primary")
        self.assertEqual(final.final_status, "final_model_error_predictive")

    def test_unstable_intended_branch_does_not_promote_comparison_branch(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        final = realize_ulf_final(
            hf,
            {
                "delta_hf_adjusted": branch(
                    "delta_hf_adjusted",
                    source("absent_no_stable_grid", "not_applicable", tau=None),
                ),
                "no_delta_hf": branch(
                    "no_delta_hf",
                    source("pre_specified_accepted", "error_predictive"),
                ),
            },
        )
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_role, "no_final_model")
        self.assertEqual(final.final_status, "no_final_model_absent_no_stable_grid")

    def test_no_delta_input_failure_cannot_fallback_to_adjusted(self) -> None:
        hf = source("pre_specified_accepted", "error_nonpredictive")
        final = realize_ulf_final(
            hf,
            {
                "no_delta_hf": branch("no_delta_hf", None, input_status="invalid_nuisance_design"),
                "delta_hf_adjusted": branch(
                    "delta_hf_adjusted",
                    source("pre_specified_accepted", "error_predictive"),
                ),
            },
        )
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_role, "no_final_model")
        self.assertEqual(final.final_status, "no_final_model_input_failure")

    def test_absent_hf_no_delta_branch_can_be_primary(self) -> None:
        hf = source("absent_no_stable_grid", "not_applicable", tau=None)
        final = realize_ulf_final(
            hf,
            {
                "no_delta_hf": branch(
                    "no_delta_hf",
                    source("pre_specified_accepted", "error_predictive"),
                )
            },
        )
        self.assertEqual(final.intended_primary_branch, "no_delta_hf")
        self.assertEqual(final.final_branch, "no_delta_hf")
        self.assertEqual(final.final_role, "primary")

    def test_both_branches_absent_has_explicit_no_final(self) -> None:
        hf = source("pre_specified_accepted", "error_predictive")
        absent = source("absent_no_stable_grid", "not_applicable", tau=None)
        final = realize_ulf_final(
            hf,
            {
                "delta_hf_adjusted": branch("delta_hf_adjusted", absent),
                "no_delta_hf": branch("no_delta_hf", absent),
            },
        )
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_role, "no_final_model")


if __name__ == "__main__":
    unittest.main()
