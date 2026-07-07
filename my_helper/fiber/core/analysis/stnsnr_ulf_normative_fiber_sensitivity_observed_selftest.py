#!/usr/bin/env python3
"""Self-tests for observed-only D normative-fiber sensitivity branches."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from stnsnr_ulf_normative_fiber_sensitivity_observed import (
    FiberSensitivityInputs,
    build_sensitivity_branches,
)


def test_build_sensitivity_branches_writes_gain_and_total_ulf_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_root = Path(tmp)
        subject_ids = [f"S{idx}" for idx in range(1, 7)]
        y_post = np.array([20.0, 19.0, 18.0, 15.0, 14.0, 13.0], dtype=float)
        y_hf_ref = np.array([22.0, 21.0, 20.0, 17.0, 16.0, 15.0], dtype=float)
        gain = y_hf_ref - y_post
        delta = np.array([0.1, 0.2, 0.4, 0.8, 1.0, 1.2], dtype=float)
        x_ulf_only = np.array(
            [
                [2.1, 0.0, 1.4, 0.2, 1.8],
                [2.0, 1.1, 1.2, 0.1, 1.6],
                [1.8, 1.3, 1.0, 0.0, 1.5],
                [1.2, 1.8, 0.4, 1.1, 0.8],
                [1.1, 2.0, 0.3, 1.2, 0.7],
                [0.9, 2.2, 0.2, 1.4, 0.6],
            ],
            dtype=np.float32,
        )
        x_ulf_total = x_ulf_only + np.array(
            [
                [0.2, 0.5, 0.1, 0.0, 0.1],
                [0.1, 0.3, 0.1, 0.0, 0.2],
                [0.2, 0.2, 0.0, 0.1, 0.1],
                [0.3, 0.1, 0.2, 0.1, 0.0],
                [0.4, 0.0, 0.2, 0.2, 0.0],
                [0.5, 0.0, 0.3, 0.2, 0.1],
            ],
            dtype=np.float32,
        )
        inputs = FiberSensitivityInputs(
            subject_ids=subject_ids,
            y_post=y_post,
            y_hf_ref=y_hf_ref,
            gain=gain,
            delta_hfscore=delta,
            x_ulf_only=x_ulf_only,
            x_ulf_total=x_ulf_total,
            fiber_ids=np.arange(1, x_ulf_only.shape[1] + 1, dtype=np.int64),
            scale_direction="lower",
            tau=1.0,
            min_coverage=2,
            output_root=output_root,
            post_scale="MDS-UPDRS III score (STN+SNr, 3 m)",
            hf_reference_scale="MDS-UPDRS III score (STN, 3 m)",
            connectome_key="ppmi",
            connectome_slug="ppmi_85_ewert_2017",
            selected_tau=600.0,
            selected_coverage=5,
        )
        rows = build_sensitivity_branches(inputs)
        assert {row["branch"] for row in rows} == {
            "normative_fiber_gain_endpoint",
            "normative_fiber_total_ulf_exposure",
        }
        for row in rows:
            branch_dir = Path(row["branch_dir"])
            assert (branch_dir / "normative_ULF_fiber_generation_manifest.json").is_file()
            assert (branch_dir / "normative_ULF_fiber_mapping_qc.json").is_file()
            assert (branch_dir / "normative_ULF_fiber_scores.csv").is_file()
            assert (branch_dir / "normative_ULF_fiber_loocv_predictions.csv").is_file()
            assert (branch_dir / "normative_ULF_fiber_weights.csv").is_file()
            assert row["resampling_status"] == "not_run_observed_only"


def main() -> int:
    test_build_sensitivity_branches_writes_gain_and_total_ulf_outputs()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
