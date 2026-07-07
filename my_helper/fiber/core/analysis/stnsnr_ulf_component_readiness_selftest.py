#!/usr/bin/env python3
"""Self-tests for ULF component readiness helpers."""

from __future__ import annotations

from pathlib import Path

from stnsnr_ulf_component_readiness import (
    alternating_component_efield_paths,
    build_component_availability,
    classify_frequency_component,
    component_efield_paths,
    dependency_rows,
    summarize_component_availability,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_frequency_classification() -> None:
    assert_equal(classify_frequency_component(130), "HF", "130 Hz should be HF")
    assert_equal(classify_frequency_component(100), "HF", "100 Hz should be HF")
    assert_equal(classify_frequency_component(50), "ULF", "50 Hz should be ULF")
    assert_equal(classify_frequency_component(30), "ULF", "30 Hz should be ULF")
    assert_equal(classify_frequency_component(75), "MID", "75 Hz should be MID")


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


def test_alternating_observed_path_construction() -> None:
    row = {
        "ID": "SNr007",
        "NameEn": "HuFengXian",
        "Phase": "3m",
        "Protocol": "STN+SNr",
        "Side": "L",
        "Target": "SNr",
        "Contact": 0,
    }
    folder, efield = alternating_component_efield_paths(Path("/tmp/leaddbs"), row, 1)
    assert_equal(
        str(folder),
        "/tmp/leaddbs/sub-HuFengXian/stimulations/MNI152NLin2009bAsym/stnsnr_vta_SNr007_3m_STNplusSNr_alt_L_SNr_c0_row1",
        "alternating observed folder path",
    )
    assert_equal(
        efield.name,
        "sub-HuFengXian_sim-efield_model-simbio_hemi-L.nii",
        "alternating observed efield file name",
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


def test_component_availability_includes_immediate_phase() -> None:
    import pandas as pd

    rows = []
    for phase in ["3m", "immediate"]:
        rows.append(
            {
                "ID": "SNr001",
                "NameEn": "Example",
                "Phase": phase,
                "Protocol": "STN+SNr",
                "Side": "L",
                "Target": "STN",
                "Contact": 1,
                "Frequency": 125,
                "StimulationPattern": "alternating",
            }
        )
        rows.append(
            {
                "ID": "SNr001",
                "NameEn": "Example",
                "Phase": phase,
                "Protocol": "STN+SNr",
                "Side": "L",
                "Target": "SNr",
                "Contact": 0,
                "Frequency": 30,
                "StimulationPattern": "alternating",
            }
        )
    availability = build_component_availability(pd.DataFrame(rows), Path("/tmp/leaddbs"))
    phases = sorted({row["phase"] for row in availability})
    assert_equal(phases, ["3m", "immediate"], "component availability phases")


def test_dependency_rows_use_explicit_connectome_id() -> None:
    rows = dependency_rows(
        {
            "A": {
                "decision": "STOP_FORMAL_REMAIN_EXPLORATORY",
                "hf_prediction_validity_status": "failed_unstable",
                "spearman_rho": -0.1,
                "q2": -0.2,
            },
            "B_PPMI": {
                "decision": "STOP_FORMAL_REMAIN_EXPLORATORY",
                "hf_prediction_validity_status": "failed_unstable",
                "spearman_rho": -0.3,
                "q2": -0.4,
            },
        }
    )
    assert_equal(rows[0]["hf_model_id"], "A", "C dependency model")
    assert_equal(rows[1]["hf_model_id"], "B_PPMI", "D dependency model")
    assert_equal(rows[1]["downstream_model_id"], "D", "D downstream model")
    assert_equal(rows[1]["dependency_status"], "EXPLORATORY_UNSTABLE", "D dependency status")
    assert_equal(rows[1]["hf_prediction_validity_status"], "failed_unstable", "D HF validity status")


def main() -> int:
    test_frequency_classification()
    test_component_path_construction()
    test_alternating_observed_path_construction()
    test_availability_summary()
    test_component_availability_includes_immediate_phase()
    test_dependency_rows_use_explicit_connectome_id()
    print("ULF component readiness self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
