#!/usr/bin/env python3
"""Self-tests for the observed-only ULF direct voxel driver."""

from __future__ import annotations

import json

import numpy as np

from stnsnr_four_model_stats import suprathreshold_matrix, coverage_from_suprathreshold
from stnsnr_ulf_direct_voxel_observed import (
    compute_branch,
    delta_hf_scores_from_map,
    fit_baseline_with_covariates,
)


def test_baseline_with_covariates() -> None:
    y = np.array([1.0, 2.0, 3.0, 4.0])
    train_cov = np.array([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0], [3.0, 1.0]])
    test_cov = np.array([[4.0, 1.0]])
    pred, beta = fit_baseline_with_covariates(y, train_cov, test_cov)
    assert np.isfinite(pred).all()
    assert np.isfinite(beta).all()
    assert abs(float(pred[0]) - 5.0) < 1e-10


def test_delta_hf_scores_from_map() -> None:
    hf_reference = np.array([[1.0, 2.0, 0.0], [2.0, 2.0, 1.0]])
    hf_component = np.array([[2.0, 1.0, 0.0], [3.0, 4.0, 1.0]])
    weights = np.array([0.5, -0.25, np.nan])
    mask = np.array([True, True, False])
    delta, ref_score, component_score, n_valid = delta_hf_scores_from_map(hf_reference, hf_component, weights, mask)
    expected_ref = np.array([(1.0 * 0.5 + 2.0 * -0.25) / 2.0, (2.0 * 0.5 + 2.0 * -0.25) / 2.0])
    expected_component = np.array([(2.0 * 0.5 + 1.0 * -0.25) / 2.0, (3.0 * 0.5 + 4.0 * -0.25) / 2.0])
    assert n_valid == 2
    np.testing.assert_allclose(ref_score, expected_ref)
    np.testing.assert_allclose(component_score, expected_component)
    np.testing.assert_allclose(delta, expected_component - expected_ref)


def test_compute_branch_no_delta_and_delta() -> None:
    rng = np.random.default_rng(42)
    n_subjects = 8
    latent = np.linspace(0.0, 1.0, n_subjects)
    y_hf_ref = 20.0 - 4.0 * latent
    y_post = 18.0 - 5.0 * latent + rng.normal(0.0, 0.05, n_subjects)
    x = np.column_stack(
        [
            250.0 * latent + 20.0,
            230.0 * latent[::-1] + 25.0,
            rng.uniform(0.0, 300.0, n_subjects),
            100.0 + 50.0 * latent,
            rng.uniform(0.0, 50.0, n_subjects),
            260.0 * latent + rng.uniform(0.0, 5.0, n_subjects),
        ]
    ).astype(np.float32)
    s_tau = suprathreshold_matrix(x, 80.0)
    coverage = coverage_from_suprathreshold(s_tau)
    subject_ids = [f"SNr{idx:03d}" for idx in range(n_subjects)]
    no_delta = compute_branch(
        branch_name="test_no_delta",
        x_ulf_only=x,
        coverage=coverage,
        s_tau_ulf_only=s_tau,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=None,
        nuisance_fold_provider=None,
        scale_direction="lower",
        min_coverage=3,
        subject_ids=subject_ids,
    )
    delta = np.linspace(-0.1, 0.2, n_subjects)
    with_delta = compute_branch(
        branch_name="test_delta",
        x_ulf_only=x,
        coverage=coverage,
        s_tau_ulf_only=s_tau,
        y_post=y_post,
        y_hf_ref=y_hf_ref,
        nuisance_full=delta,
        nuisance_fold_provider=lambda _heldout: delta,
        scale_direction="lower",
        min_coverage=3,
        subject_ids=subject_ids,
    )
    assert no_delta["n_omega_voxels"] > 0
    assert with_delta["n_omega_voxels"] > 0
    assert len(no_delta["fold_rows"]) == n_subjects
    assert len(with_delta["fold_rows"]) == n_subjects
    assert np.isfinite(no_delta["metrics"]["spearman_rho"])
    assert np.isfinite(with_delta["metrics"]["spearman_rho"])
    assert "DeltaHFScore_LOOCV" in with_delta["fold_rows"][0]


def main() -> int:
    test_baseline_with_covariates()
    test_delta_hf_scores_from_map()
    test_compute_branch_no_delta_and_delta()
    print(json.dumps({"status": "PASS"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
