#!/usr/bin/env python3
"""Smoke/equivalence tests for HF normative fiber helper functions."""

from __future__ import annotations

import json

import numpy as np

from stnsnr_hf_normative_fiber_smoke import (
    fiber_block_slices,
    normative_fiber_hard_computability_passes,
    reduce_point_values_to_fiber_peaks,
    resolve_normative_fiber_source,
)


def run_selftest() -> dict[str, object]:
    lengths = np.array([3, 2, 4], dtype=np.int64)
    blocks = list(fiber_block_slices(lengths, fiber_chunk_size=2))
    expected_blocks = [(0, 2, 0, 5), (2, 3, 5, 9)]
    if blocks != expected_blocks:
        raise AssertionError(f"unexpected block slices {blocks}; expected {expected_blocks}")

    point_values = np.array([1.0, 4.0, 2.0, 3.0, 9.0, 5.0, 8.0, 7.0, 6.0], dtype=np.float32)
    peaks = reduce_point_values_to_fiber_peaks(point_values, lengths)
    expected_peaks = np.array([4.0, 9.0, 8.0], dtype=np.float32)
    if not np.allclose(peaks, expected_peaks):
        raise AssertionError(f"unexpected peaks {peaks}; expected {expected_peaks}")

    ppmi_row = {
        "connectome": "ppmi",
        "n_subjects": 16,
        "n_candidate_fibers": 250,
        "fold_n_candidate_fibers_min": 120,
        "selected_fiber_pools_computable": True,
        "netfiberscore_nonconstant_all_folds": True,
        "y_base_nuisance_design_valid": True,
        "all_predictions_finite": True,
    }
    if not normative_fiber_hard_computability_passes(ppmi_row):
        raise AssertionError("PPMI row should pass the normative fiber hard filter")

    dtor_row = dict(ppmi_row)
    dtor_row["connectome"] = "dtor"
    if normative_fiber_hard_computability_passes(dtor_row):
        raise AssertionError("dTOR row with fewer than 1000 fold candidate fibers should fail")

    rows = []
    for tau, coverage in [(800, 5), (600, 5), (1000, 6)]:
        row = dict(ppmi_row)
        row.update(
            {
                "tau": tau,
                "coverage": coverage,
                "mae_model": 8.0,
                "mae_baseline": 10.0,
                "rmse_model": 9.0,
                "rmse_baseline": 11.0,
            }
        )
        rows.append(row)
    resolved = resolve_normative_fiber_source(rows, connectome="ppmi")
    if resolved["hf_norm_fiber_source_status"] != "pre_specified_accepted":
        raise AssertionError(f"unexpected normative source status: {resolved}")
    if resolved["hf_norm_fiber_prediction_status"] != "error_predictive":
        raise AssertionError(f"unexpected normative prediction status: {resolved}")

    return {
        "status": "PASS",
        "blocks": [list(item) for item in blocks],
        "peaks": peaks.astype(float).tolist(),
        "normative_source_status": resolved["hf_norm_fiber_source_status"],
    }


def main() -> int:
    print(json.dumps(run_selftest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
