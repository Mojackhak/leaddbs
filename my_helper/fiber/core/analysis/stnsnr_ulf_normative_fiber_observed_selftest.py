#!/usr/bin/env python3
"""Self-tests for the observed-only ULF normative fiber driver."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from stnsnr_four_model_stats import NormativeFiberScoreConfig
from stnsnr_ulf_normative_fiber_observed import (
    apply_ulf_only_fiber_rule,
    classify_b_dependency,
    component_phase_from_post_scale,
    delta_hf_fiber_scores_from_weights,
    find_reusable_component_preprocess_dir,
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

    configured = delta_hf_fiber_scores_from_weights(
        np.ones((2, 8), dtype=float),
        np.full((2, 8), 2.0, dtype=float),
        np.array([4.0, 3.0, 2.0, 1.0, -1.0, -2.0, -3.0, -4.0]),
        np.ones(8, dtype=bool),
        score_config=NormativeFiberScoreConfig(
            sweet_fraction=0.25,
            sour_fraction=0.25,
            weighted_peak_fraction=1.0,
            sweet_selected_min_count=1,
            sour_selected_min_count=1,
            weighted_peak_min_count=1,
        ),
    )
    assert configured["n_sweet_selected_fibers"] == 1
    assert configured["n_sour_selected_fibers"] == 1


def test_classify_b_dependency() -> None:
    locked = classify_b_dependency("PASS_TO_NEXT_ROUND")
    failed = classify_b_dependency("STOP_FORMAL_REMAIN_EXPLORATORY")
    assert locked["ulf_primary_branch"] == "delta_hf_adjusted"
    assert failed["ulf_primary_branch"] == "no_delta_hf"
    assert failed["delta_hfscore_role"] == "unstable_generated_covariate_sensitivity"


def test_component_phase_from_post_scale() -> None:
    assert component_phase_from_post_scale("MDS-UPDRS III score (STN+SNr, 3 m)") == "3m"
    assert component_phase_from_post_scale("MDS-UPDRS III score (STN+SNr, immediate)") == "immediate"


def _write_scores(path: Path, subject_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["subject_id,Y_post,Y_HF_ref,NetULFFiberScore"]
    rows.extend(f"{subject_id},1,1,0" for subject_id in subject_ids)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_find_reusable_component_preprocess_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache = (
            root
            / "ppmi_85_ewert_2017"
            / "mds_updrs_iii_axial_score_stn_snr_immediate"
            / "peak_efield_tau800_observed"
            / "preprocess"
        )
        cache.mkdir(parents=True)
        for name in [
            "X_HF_component_fiber_float32_subject_major.npy",
            "X_ULF_component_fiber_float32_subject_major.npy",
            "fiber_ids.npy",
        ]:
            (cache / name).write_bytes(b"placeholder")
        _write_scores(
            cache.parent / "ulf_peak_efield_tau800_no_delta_hf" / "normative_ULF_fiber_scores.csv",
            ["S1", "S2"],
        )
        found = find_reusable_component_preprocess_dir(
            root,
            connectome_slug="ppmi_85_ewert_2017",
            component_phase="immediate",
            subject_ids=["S1", "S2"],
            tau_name="tau800",
        )
        assert found == cache
        not_found = find_reusable_component_preprocess_dir(
            root,
            connectome_slug="ppmi_85_ewert_2017",
            component_phase="3m",
            subject_ids=["S1", "S2"],
            tau_name="tau800",
        )
        assert not_found is None


def main() -> int:
    test_apply_ulf_only_fiber_rule()
    test_delta_hf_fiber_scores_from_weights()
    test_classify_b_dependency()
    test_component_phase_from_post_scale()
    test_find_reusable_component_preprocess_dir()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
