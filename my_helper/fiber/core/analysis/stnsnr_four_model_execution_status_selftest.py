#!/usr/bin/env python3
"""Self-tests for consolidated four-model execution status helpers."""

from __future__ import annotations

import json

from stnsnr_four_model_execution_status import classify_c_observed_state, classify_hf_model_state, classify_ulf_model_state


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_hf_stop_gate_state() -> None:
    state = classify_hf_model_state(
        {
            "decision": "STOP_FORMAL_REMAIN_EXPLORATORY",
            "output_exists": True,
            "predictions_finite": True,
            "spearman_rho": -0.03,
            "q2": -0.2,
        }
    )
    assert_equal(state["execution_status"], "OBSERVED_COMPLETE_STOPPED_BY_GATE", "HF stopped status")
    assert_equal(state["formal_resampling_status"], "SKIP_GATE_FAILED", "HF formal status")


def test_hf_pass_gate_state() -> None:
    state = classify_hf_model_state(
        {
            "decision": "PASS_TO_NEXT_ROUND",
            "output_exists": True,
            "predictions_finite": True,
            "spearman_rho": 0.3,
            "q2": 0.1,
        }
    )
    assert_equal(state["execution_status"], "READY_FOR_NEXT_ROUND", "HF pass status")
    assert_equal(state["formal_resampling_status"], "ELIGIBLE_AFTER_SMOKE_RESAMPLING", "HF pass formal status")


def test_ulf_input_failure_state() -> None:
    state = classify_ulf_model_state(
        hf_dependency_decision="STOP_FORMAL_REMAIN_EXPLORATORY",
        readiness_status="NOT_EXECUTABLE_INPUT_FAILURE",
        efield_summary={"n_efields_existing": 12, "n_rows": 64},
    )
    assert_equal(state["execution_status"], "NOT_EXECUTABLE_INPUT_FAILURE", "ULF input failure status")
    assert_equal(state["dependency_status"], "EXPLORATORY_UNSTABLE", "ULF dependency status")
    assert_equal(state["formal_resampling_status"], "NOT_APPLICABLE_INPUT_FAILURE", "ULF formal status")


def test_c_observed_exploratory_state() -> None:
    state = classify_c_observed_state(
        hf_dependency_decision="STOP_FORMAL_REMAIN_EXPLORATORY",
        readiness_status="EXPLORATORY_ONLY_UNSTABLE_HF_DEPENDENCY",
        efield_summary={"n_efields_existing": 64, "n_rows": 64},
        c_outputs={"both_branches_exist": True},
    )
    assert_equal(state["execution_status"], "OBSERVED_COMPLETE_EXPLORATORY", "C observed exploratory status")
    assert_equal(state["dependency_status"], "EXPLORATORY_UNSTABLE", "C dependency status")
    assert_equal(state["formal_resampling_status"], "NOT_APPLICABLE_DEPENDENCY_UNSTABLE", "C formal status")


def main() -> int:
    test_hf_stop_gate_state()
    test_hf_pass_gate_state()
    test_ulf_input_failure_state()
    test_c_observed_exploratory_state()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
