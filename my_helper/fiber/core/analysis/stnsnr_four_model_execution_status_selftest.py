#!/usr/bin/env python3
"""Self-tests for consolidated four-model execution status helpers."""

from __future__ import annotations

import json

from stnsnr_four_model_execution_status import (
    classify_c_observed_state,
    classify_d_observed_state,
    classify_hf_model_state,
    classify_ulf_model_state,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_hf_error_nonpredictive_source_state() -> None:
    state = classify_hf_model_state(
        {
            "output_exists": True,
            "predictions_finite": True,
            "hf_voxel_source_status": "pre_specified_accepted",
            "hf_voxel_prediction_status": "error_nonpredictive",
            "spearman_rho": -0.03,
            "q2": -0.2,
        }
    )
    assert_equal(state["execution_status"], "SOURCE_ACCEPTED_ERROR_NONPREDICTIVE", "HF source status")
    assert_equal(state["formal_resampling_status"], "NOT_SELECTED_FOR_PREDICTIVE_FORMAL", "HF formal status")
    assert_equal(state["hf_prediction_validity_status"], "error_nonpredictive", "HF prediction status")


def test_hf_error_predictive_source_state() -> None:
    state = classify_hf_model_state(
        {
            "output_exists": True,
            "predictions_finite": True,
            "hf_norm_fiber_source_status": "scan_fallback_accepted",
            "hf_norm_fiber_prediction_status": "error_predictive",
            "spearman_rho": 0.3,
            "q2": 0.1,
        }
    )
    assert_equal(state["execution_status"], "READY_FOR_NEXT_ROUND", "HF pass status")
    assert_equal(state["formal_resampling_status"], "ELIGIBLE_AFTER_SOURCE_RESOLUTION", "HF pass formal status")


def test_legacy_hf_row_waits_for_resolver_refresh() -> None:
    state = classify_hf_model_state(
        {
            "decision": "STOP_FORMAL_REMAIN_EXPLORATORY",
            "output_exists": True,
            "predictions_finite": True,
            "hf_prediction_validity_status": "failed_unstable",
            "spearman_rho": -0.3,
            "q2": -0.4,
        }
    )
    assert_equal(state["execution_status"], "WAITING_FOR_HF_SOURCE_RESOLVER", "legacy HF waits for resolver")
    assert_equal(state["formal_resampling_status"], "NOT_APPLICABLE_WAITING_FOR_HF", "legacy HF formal status")


def test_ulf_input_failure_state() -> None:
    state = classify_ulf_model_state(
        hf_dependency_source_status="pre_specified_accepted",
        hf_dependency_prediction_status="error_nonpredictive",
        readiness_status="NOT_EXECUTABLE_INPUT_FAILURE",
        efield_summary={"n_efields_existing": 12, "n_rows": 64},
    )
    assert_equal(state["execution_status"], "NOT_EXECUTABLE_INPUT_FAILURE", "ULF input failure status")
    assert_equal(state["dependency_status"], "SOURCE_EXISTS_ERROR_NONPREDICTIVE", "ULF dependency status")
    assert_equal(state["formal_resampling_status"], "NOT_APPLICABLE_INPUT_FAILURE", "ULF formal status")


def test_c_observed_source_exists_state() -> None:
    state = classify_c_observed_state(
        hf_dependency_source_status="pre_specified_accepted",
        hf_dependency_prediction_status="error_nonpredictive",
        readiness_status="PASS_READY_FOR_ULF_PRIMARY",
        efield_summary={"n_efields_existing": 64, "n_rows": 64},
        c_outputs={
            "both_branches_exist": True,
            "branches": {
                "no_delta_hf": {
                    "ulf_voxel_source_status": "pending_source_resolver",
                    "ulf_prediction_status": "error_nonpredictive",
                    "baseline_comparison": {
                        "mae_model": 3.0,
                        "mae_baseline": 2.5,
                        "rmse_model": 4.0,
                        "rmse_baseline": 3.5,
                    },
                }
            },
        },
    )
    assert_equal(state["execution_status"], "OBSERVED_COMPLETE_WAITING_FOR_ULF_SOURCE_RESOLVER", "C observed status")
    assert_equal(state["dependency_status"], "SOURCE_EXISTS_ERROR_NONPREDICTIVE", "C dependency status")
    assert_equal(
        state["formal_resampling_status"], "NOT_APPLICABLE_WAITING_FOR_ULF_SOURCE_RESOLVER", "C formal status"
    )
    assert_equal(state["ulf_primary_branch"], "no_delta_hf", "C primary branch")
    assert_equal(state["ulf_prediction_status"], "error_nonpredictive", "C ULF prediction status")
    assert_equal(state["ulf_endpoint_model_status"], "pending_source_resolver", "C endpoint status")


def test_d_observed_source_absent_state() -> None:
    state = classify_d_observed_state(
        hf_dependency_source_status="absent_no_stable_grid",
        hf_dependency_prediction_status="not_applicable",
        readiness_status="PASS_READY_FOR_ULF_PRIMARY",
        efield_summary={"n_efields_existing": 64, "n_rows": 64},
        d_outputs={
            "both_branches_exist": True,
            "branches": {
                "no_delta_hf": {
                    "ulf_norm_fiber_source_status": "pending_source_resolver",
                    "ulf_prediction_status": "error_nonpredictive",
                    "baseline_comparison": {
                        "mae_model": 3.0,
                        "mae_baseline": 2.5,
                        "rmse_model": 4.0,
                        "rmse_baseline": 3.5,
                    },
                }
            },
        },
    )
    assert_equal(
        state["execution_status"], "OBSERVED_COMPLETE_WAITING_FOR_ULF_SOURCE_RESOLVER", "D observed source-absent status"
    )
    assert_equal(state["dependency_status"], "SOURCE_ABSENT", "D dependency status")
    assert_equal(
        state["formal_resampling_status"], "NOT_APPLICABLE_WAITING_FOR_ULF_SOURCE_RESOLVER", "D formal status"
    )


def main() -> int:
    test_hf_error_nonpredictive_source_state()
    test_hf_error_predictive_source_state()
    test_legacy_hf_row_waits_for_resolver_refresh()
    test_ulf_input_failure_state()
    test_c_observed_source_exists_state()
    test_d_observed_source_absent_state()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
