#!/usr/bin/env python3
"""Self-tests for ULF direct voxel same-day immediate endpoint discovery."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from stnsnr_four_model_readiness import RAW_CLINICAL_FILE
from stnsnr_ulf_direct_voxel_immediate_observed import discover_immediate_endpoint_rows


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_discover_immediate_endpoint_rows_requires_paired_hf_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        clinical_root = Path(tmp_dir)
        rows = []
        for subject_idx in range(12):
            subject_id = f"SNr{subject_idx:03d}"
            rows.append(
                {
                    "ID": subject_id,
                    "Protocol": "STN+SNr",
                    "Phase": "immediate",
                    "Scale": "MDS-UPDRS III score",
                    "Value": 20 + subject_idx,
                    "Baseline": 40,
                }
            )
            rows.append(
                {
                    "ID": subject_id,
                    "Protocol": "STN",
                    "Phase": "3m",
                    "Scale": "MDS-UPDRS III score",
                    "Value": 25 + subject_idx,
                    "Baseline": 40,
                }
            )
            rows.append(
                {
                    "ID": subject_id,
                    "Protocol": "STN+SNr",
                    "Phase": "immediate",
                    "Scale": "MDS-UPDRS III axial score",
                    "Value": 5 + subject_idx,
                    "Baseline": 10,
                }
            )
        pd.DataFrame(rows).to_excel(clinical_root / RAW_CLINICAL_FILE, index=False)

        endpoints = discover_immediate_endpoint_rows(clinical_root, min_subjects=12)

        assert_equal(len(endpoints), 1, "endpoint count")
        assert_equal(endpoints[0].post_scale, "MDS-UPDRS III score (STN+SNr, immediate)", "post scale")
        assert_equal(endpoints[0].n_subjects, 12, "paired subject count")


def main() -> int:
    test_discover_immediate_endpoint_rows_requires_paired_hf_reference()
    print("ULF direct voxel immediate self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
