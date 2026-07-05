#!/usr/bin/env python3
"""Self-tests for ULF component readiness helpers."""

from __future__ import annotations

from pathlib import Path

from stnsnr_ulf_component_readiness import (
    classify_frequency_component,
    component_efield_paths,
    reconstruct_post_score_from_delta,
    summarize_component_availability,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_close(actual: float, expected: float, message: str, tol: float = 1e-9) -> None:
    if abs(actual - expected) > tol:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_frequency_classification() -> None:
    assert_equal(classify_frequency_component(130), "HF", "130 Hz should be HF")
    assert_equal(classify_frequency_component(100), "HF", "100 Hz should be HF")
    assert_equal(classify_frequency_component(50), "ULF", "50 Hz should be ULF")
    assert_equal(classify_frequency_component(30), "ULF", "30 Hz should be ULF")
    assert_equal(classify_frequency_component(75), "MID", "75 Hz should be MID")


def test_delta_score_reconstruction() -> None:
    assert_close(reconstruct_post_score_from_delta(34, -12), 22, "lower-is-better raw delta score")
    assert_close(reconstruct_post_score_from_delta(70, 20), 90, "higher-is-better raw delta score")


def test_component_path_construction() -> None:
    row = {
        "ID": "SNr011",
        "NameEn": "WuYueFen",
        "Phase": "3m",
        "Protocol": "STN+SNr",
        "Side": "L",
        "Target": "SNr",
    }
    folder, efield = component_efield_paths(Path("/tmp/leaddbs"), row)
    assert_equal(
        str(folder),
        "/tmp/leaddbs/sub-WuYueFen/stimulations/MNI152NLin2009bAsym/stnsnr_target_component_SNr011_3m_STNplusSNr_L_SNr",
        "component folder path",
    )
    assert_equal(
        efield.name,
        "sub-WuYueFen_sim-efield_model-simbio_hemi-L.nii",
        "component efield file name",
    )


def test_availability_summary() -> None:
    rows = [
        {"folder_exists": True, "efield_exists": False, "frequency_class": "HF"},
        {"folder_exists": False, "efield_exists": False, "frequency_class": "ULF"},
        {"folder_exists": True, "efield_exists": True, "frequency_class": "ULF"},
    ]
    summary = summarize_component_availability(rows)
    assert_equal(summary["n_rows"], 3, "row count")
    assert_equal(summary["n_folders_existing"], 2, "folder count")
    assert_equal(summary["n_efields_existing"], 1, "efield count")
    assert_equal(summary["frequency_class_counts"], {"HF": 1, "ULF": 2}, "frequency class counts")


def main() -> int:
    test_frequency_classification()
    test_delta_score_reconstruction()
    test_component_path_construction()
    test_availability_summary()
    print("ULF component readiness self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
