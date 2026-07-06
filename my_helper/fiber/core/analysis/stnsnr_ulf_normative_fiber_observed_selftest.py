#!/usr/bin/env python3
"""Self-tests for the observed-only ULF normative fiber driver."""

from __future__ import annotations

import json

import numpy as np

from stnsnr_ulf_normative_fiber_observed import (
    apply_ulf_only_fiber_rule,
    classify_b_dependency,
    delta_hf_fiber_scores_from_weights,
)


def test_apply_ulf_only_fiber_rule() -> None:
    hf = np.array([[900.0, 100.0, 850.0], [0.0, 900.0, 100.0]], dtype=np.float32)
    ulf = np.array([[950.0, 820.0, 100.0], [850.0, 920.0, 790.0]], dtype=np.float32)
    out = apply_ulf_only_fiber_rule(hf_component=hf, ulf_component=ulf, tau=800.0)
    expected = np.array([[0.0, 820.0, 0.0], [850.0, 0.0, 0.0]], dtype=np.float32)
    np.testing.assert_allclose(out, expected)


def test_delta_hf_fiber_scores_from_weights() -> None:
    hf_ref = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]], dtype=float)
    hf_component = np.array([[2.0, 1.0, 3.0], [3.0, 6.0, 6.0]], dtype=float)
    weights = np.array([0.5, -0.25, np.nan], dtype=float)
    candidate = np.array([True, True, True])
    result = delta_hf_fiber_scores_from_weights(hf_ref, hf_component, weights, candidate)
    expected_ref = np.array([1.0 * 0.5 - 2.0 * 0.25, 2.0 * 0.5 - 4.0 * 0.25])
    expected_component = np.array([2.0 * 0.5 - 1.0 * 0.25, 3.0 * 0.5 - 6.0 * 0.25])
    np.testing.assert_allclose(result["reference_score"], expected_ref)
    np.testing.assert_allclose(result["component_score"], expected_component)
    np.testing.assert_allclose(result["delta"], expected_component - expected_ref)
    assert result["n_sweet_selected_fibers"] == 1
    assert result["n_sour_selected_fibers"] == 1


def test_classify_b_dependency() -> None:
    locked = classify_b_dependency("PASS_TO_NEXT_ROUND")
    failed = classify_b_dependency("STOP_FORMAL_REMAIN_EXPLORATORY")
    assert locked["ulf_primary_branch"] == "delta_hf_adjusted"
    assert failed["ulf_primary_branch"] == "no_delta_hf"
    assert failed["delta_hfscore_role"] == "unstable_generated_covariate_sensitivity"


def main() -> int:
    test_apply_ulf_only_fiber_rule()
    test_delta_hf_fiber_scores_from_weights()
    test_classify_b_dependency()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
