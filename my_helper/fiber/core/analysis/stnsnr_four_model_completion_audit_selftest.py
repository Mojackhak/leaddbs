#!/usr/bin/env python3
"""Self-tests for STN/SNr four-model completion/blocker audit."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from stnsnr_four_model_completion_audit import build_completion_audit


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_completion_audit_classifies_finished_observed_and_blocked_rows() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        final_report_csv = root / "final_report.csv"
        figure_readiness_csv = root / "figure_readiness.csv"
        all_endpoint_missing_work_csv = root / "all_endpoint_missing_work.csv"
        manifest_schema_audit_csv = root / "manifest_schema_audit.csv"
        output_dir = root / "completion_audit"

        write_csv(
            final_report_csv,
            [
                {
                    "model_id": "A",
                    "model": "HF direct voxel",
                    "analysis_family": "direct_voxel",
                    "final_model_status": "final_model_error_nonpredictive",
                    "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                    "formal_readiness_status": "READY_FOR_FORMAL_DRIVER",
                    "formal_resampling_status": "FORMAL_RESAMPLING_JITTER_COMPLETE",
                    "figure_output_status": "ready_from_existing_direct_voxel_maps",
                    "oss_sensitivity_status": "",
                    "oss_missing_inputs": "",
                    "fiber_jitter_qc_status": "",
                    "jitter_missing_inputs": "",
                    "latest_manifest": "/tmp/A_manifest.json",
                    "latest_manifest_provenance_status": "has_git_or_patch_provenance",
                    "latest_manifest_stale_status": "current_head",
                },
                {
                    "model_id": "B_PPMI",
                    "model": "HF normative fiber PPMI",
                    "analysis_family": "normative_fiber",
                    "final_model_status": "final_model_error_nonpredictive",
                    "formal_target_status": "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING",
                    "formal_readiness_status": "NOT_READY_NO_FORMAL_TARGET",
                    "formal_resampling_status": "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING",
                    "figure_output_status": "not_run_missing_density_label_cache",
                    "oss_sensitivity_status": "",
                    "oss_missing_inputs": "",
                    "fiber_jitter_qc_status": "",
                    "jitter_missing_inputs": "",
                    "latest_manifest": "/tmp/B_PPMI_manifest.json",
                    "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
                    "latest_manifest_stale_status": "missing_code_provenance",
                },
                {
                    "model_id": "B_DTOR",
                    "model": "HF normative fiber dTOR",
                    "analysis_family": "normative_fiber",
                    "final_model_status": "final_model_error_nonpredictive",
                    "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                    "formal_readiness_status": "READY_FOR_FORMAL_DRIVER",
                    "formal_resampling_status": "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING",
                    "figure_output_status": "not_run_missing_density_label_cache",
                    "oss_sensitivity_status": "not_run_missing_oss_inputs",
                    "oss_missing_inputs": "/tmp/X_oss.npy;/tmp/oss_manifest.json",
                    "fiber_jitter_qc_status": "not_run_missing_jitter_inputs",
                    "jitter_missing_inputs": "no_jitter_inputs_found_in_search_roots",
                    "latest_manifest": "/tmp/B_DTOR_manifest.json",
                    "latest_manifest_provenance_status": "has_git_or_patch_provenance",
                    "latest_manifest_stale_status": "different_commit",
                },
                {
                    "model_id": "D_DTOR",
                    "model": "ULF normative fiber dTOR",
                    "analysis_family": "normative_fiber",
                    "final_model_status": "final_model_error_nonpredictive",
                    "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                    "formal_readiness_status": "READY_FOR_FORMAL_DRIVER",
                    "formal_resampling_status": "FORMAL_BOOTSTRAP_COMPLETE",
                    "figure_output_status": "ready_for_density_label_outputs",
                    "oss_sensitivity_status": "complete",
                    "oss_missing_inputs": "",
                    "fiber_jitter_qc_status": "complete",
                    "jitter_missing_inputs": "",
                    "latest_manifest": "/tmp/D_DTOR_manifest.json",
                    "latest_manifest_provenance_status": "has_git_or_patch_provenance",
                    "latest_manifest_stale_status": "current_head",
                },
            ],
        )
        write_csv(
            figure_readiness_csv,
            [
                {"model_id": "A", "fiber_density_label_cache_status": "not_applicable_not_normative_fiber"},
                {"model_id": "B_PPMI", "fiber_density_label_cache_status": "not_run_missing_density_label_cache"},
                {"model_id": "B_DTOR", "fiber_density_label_cache_status": "not_run_missing_density_label_cache"},
                {
                    "model_id": "D_DTOR",
                    "fiber_density_label_cache_status": "ready_from_existing_density_label_cache_missing_fdr_enrichment",
                    "fiber_basic_density_cache_status": "ready_from_existing_basic_density_cache",
                    "fiber_label_cache_status": "ready_from_existing_label_cache",
                    "fiber_fdr_cache_status": "definition_documented_cache_not_generated",
                    "fiber_enrichment_cache_status": "definition_documented_cache_not_generated",
                },
            ],
        )
        write_csv(
            all_endpoint_missing_work_csv,
            [
                {"work_item_id": "C_gain", "model_id": "C", "work_type": "gain_endpoint_sensitivity", "work_status": "observed_outputs_detected"},
                {"work_item_id": "D_gain", "model_id": "D", "work_type": "gain_endpoint_sensitivity", "work_status": "not_run_missing_observed_outputs"},
            ],
        )
        write_csv(
            manifest_schema_audit_csv,
            [
                {"manifest_path": "/tmp/A_manifest.json", "schema_status": "schema_complete"},
                {"manifest_path": "/tmp/B_DTOR_manifest.json", "schema_status": "schema_missing_recommended_fields"},
                {"manifest_path": "/tmp/D_DTOR_manifest.json", "schema_status": "schema_complete"},
            ],
        )

        outputs = build_completion_audit(
            final_report_csv=final_report_csv,
            figure_readiness_csv=figure_readiness_csv,
            all_endpoint_missing_work_csv=all_endpoint_missing_work_csv,
            manifest_schema_audit_csv=manifest_schema_audit_csv,
            output_dir=output_dir,
        )

        rows = read_csv(Path(outputs["completion_audit_csv"]))
        by_id = {row["model_id"]: row for row in rows}
        assert_equal(by_id["A"]["completion_status"], "complete_to_current_spec", "direct voxel completion")
        assert_equal(by_id["A"]["blocking_status"], "not_blocked", "direct voxel blocking")
        assert_equal(by_id["B_PPMI"]["completion_status"], "observed_robustness_no_formal_target", "observed branch status")
        assert_equal(by_id["B_DTOR"]["completion_status"], "blocked_missing_fiber_inputs", "fiber final target status")
        assert_true("oss_inputs" in by_id["B_DTOR"]["blocker_categories"], "OSS blocker should be recorded")
        assert_true("jitter_inputs" in by_id["B_DTOR"]["blocker_categories"], "jitter blocker should be recorded")
        assert_true("density_label_cache" in by_id["B_DTOR"]["blocker_categories"], "density blocker should be recorded")
        assert_equal(by_id["D_DTOR"]["completion_status"], "blocked_missing_fiber_inputs", "label-only fiber target status")
        assert_true("fdr_cache" in by_id["D_DTOR"]["blocker_categories"], "FDR blocker should be recorded")
        assert_true("enrichment_cache" in by_id["D_DTOR"]["blocker_categories"], "enrichment blocker should be recorded")
        assert_true(
            "fdr_enrichment_cache" not in by_id["D_DTOR"]["blocker_categories"],
            "combined FDR/enrichment blocker should not hide component status",
        )
        assert_equal(by_id["B_DTOR"]["schema_status"], "schema_missing_recommended_fields", "schema audit join")

        manifest = json.loads(Path(outputs["manifest_json"]).read_text(encoding="utf-8"))
        assert_equal(manifest["n_rows"], 4, "manifest row count")
        assert_equal(manifest["completion_status_counts"]["complete_to_current_spec"], 1, "complete count")
        assert_equal(manifest["all_endpoint_missing_work_counts"]["not_run_missing_observed_outputs"], 1, "missing work count")


def main() -> int:
    test_completion_audit_classifies_finished_observed_and_blocked_rows()
    print("stnsnr_four_model_completion_audit_selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
