#!/usr/bin/env python3
"""Smoke/equivalence tests for HF normative fiber helper functions."""

from __future__ import annotations

import json

import numpy as np

from stnsnr_hf_normative_fiber_smoke import fiber_block_slices, reduce_point_values_to_fiber_peaks


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

    return {
        "status": "PASS",
        "blocks": [list(item) for item in blocks],
        "peaks": peaks.astype(float).tolist(),
    }


def main() -> int:
    print(json.dumps(run_selftest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
