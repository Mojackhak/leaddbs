#!/usr/bin/env python3
"""Self-tests for the STN/SNr final-model formal target worklist."""

from __future__ import annotations

import json

from stnsnr_four_model_formal_worklist import formal_target_row


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_hf_ready_target() -> None:
    row = formal_target_row(
        {
            "model_id": "A",
            "model": "HF direct voxel",
            "hf_final_model_source": "pre_specified",
            "hf_final_model_role": "primary",
            "hf_final_model_status": "final_model_error_nonpredictive",
        }
    )
    assert_equal(row["model_family"], "hf", "HF family")
    assert_equal(row["formal_target_status"], "READY_FOR_FORMAL_RESAMPLING", "HF target")
    assert_equal(row["final_branch_or_source"], "pre_specified", "HF final source")


def test_observed_robustness_connectome_not_formal_target() -> None:
    row = formal_target_row(
        {
            "model_id": "B_PPMI",
            "model": "HF normative fiber PPMI",
            "hf_final_model_source": "pre_specified",
            "hf_final_model_role": "primary",
            "hf_final_model_status": "final_model_error_nonpredictive",
        }
    )
    assert_equal(row["model_family"], "hf", "B_PPMI family")
    assert_equal(
        row["formal_target_status"],
        "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING",
        "B_PPMI target status",
    )
    assert_equal(row["formal_target_reason"], "connectome_observed_robustness_only", "B_PPMI target reason")


def test_ulf_ready_target() -> None:
    row = formal_target_row(
        {
            "model_id": "D_DTOR",
            "model": "ULF add-on normative fiber dTOR",
            "ulf_final_model_branch": "no_delta_hf",
            "ulf_final_model_role": "primary",
            "ulf_final_model_status": "final_model_error_nonpredictive",
        }
    )
    assert_equal(row["model_family"], "ulf", "ULF family")
    assert_equal(row["formal_target_status"], "READY_FOR_FORMAL_RESAMPLING", "ULF target")
    assert_equal(row["final_branch_or_source"], "no_delta_hf", "ULF final branch")


def test_no_final_model_target() -> None:
    row = formal_target_row(
        {
            "model_id": "C",
            "model": "ULF add-on direct voxel",
            "ulf_final_model_branch": "none",
            "ulf_final_model_role": "no_final_model",
            "ulf_final_model_status": "no_final_model_absent_no_stable_grid",
        }
    )
    assert_equal(row["formal_target_status"], "NO_FINAL_MODEL", "no-final target")
    assert_equal(row["formal_target_reason"], "no_final_model_absent_no_stable_grid", "no-final reason")


def main() -> int:
    test_hf_ready_target()
    test_observed_robustness_connectome_not_formal_target()
    test_ulf_ready_target()
    test_no_final_model_target()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
