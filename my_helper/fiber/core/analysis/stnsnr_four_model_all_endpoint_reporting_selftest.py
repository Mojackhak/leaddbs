#!/usr/bin/env python3
"""Self-tests for STN/SNr four-model all-endpoint reporting."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from stnsnr_four_model_all_endpoint_reporting import build_all_endpoint_reporting


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_complete_branch(branch_dir: Path, manifest_name: str, prefix: str) -> None:
    branch_dir.mkdir(parents=True, exist_ok=True)
    (branch_dir / manifest_name).write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    (branch_dir / f"{prefix}_mapping_qc.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    (branch_dir / f"{prefix}_scores.csv").write_text("subject_id,score\ns1,1\n", encoding="utf-8")
    (branch_dir / f"{prefix}_loocv_predictions.csv").write_text("subject_id,y_pred\ns1,1\n", encoding="utf-8")


def test_all_endpoint_reporting_summarizes_existing_outputs_and_missing_sensitivities() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        hf_scan_csv = root / "all_scales_posthoc_threshold_scan_summary.csv"
        write_csv(
            hf_scan_csv,
            [
                {
                    "scale": "MDS-UPDRS III score (STN, 3 m)",
                    "scale_slug": "mds_updrs_iii_score_stn_3_m",
                    "endpoint_family": "hf_stn3m",
                    "n_subjects": "16",
                    "hf_voxel_source_status": "pre_specified_accepted",
                    "hf_voxel_prediction_status": "error_nonpredictive",
                    "hf_voxel_threshold_source": "pre_specified",
                    "hf_voxel_selected_tau_v_per_m": "200",
                    "hf_voxel_selected_coverage": "5",
                    "selected_loocv_spearman_rho": "-0.0265",
                    "selected_q2": "-0.2230",
                },
                {
                    "scale": "Bradykinesia subscore (Med OFF) (STN, 3 m)",
                    "scale_slug": "bradykinesia_subscore_med_off_stn_3_m",
                    "endpoint_family": "hf_stn3m",
                    "n_subjects": "16",
                    "hf_voxel_source_status": "pre_specified_accepted",
                    "hf_voxel_prediction_status": "error_predictive",
                    "hf_voxel_threshold_source": "pre_specified",
                    "hf_voxel_selected_tau_v_per_m": "200",
                    "hf_voxel_selected_coverage": "5",
                    "selected_loocv_spearman_rho": "0.5870",
                    "selected_q2": "0.0049",
                },
            ],
        )
        observed_csv = root / "four_model_observed_branch_summary.csv"
        write_csv(
            observed_csv,
            [
                {
                    "model_id": "A_TOTAL",
                    "model": "HF direct voxel",
                    "scale_slug": "mds_updrs_iii_score_stn_3_m",
                    "branch": "partial_spearman",
                    "output_exists": "True",
                    "spearman_rho": "-0.0265",
                    "q2": "-0.2230",
                    "manifest_path": str(root / "A/direct_voxel_HF_generation_manifest.json"),
                    "qc_path": str(root / "A/direct_voxel_HF_mapping_qc.json"),
                    "predictions_path": str(root / "A/direct_voxel_HF_loocv_predictions.csv"),
                }
            ],
        )
        final_report_csv = root / "four_model_final_report.csv"
        write_csv(
            final_report_csv,
            [
                {
                    "model_id": "A",
                    "model": "HF direct voxel",
                    "final_branch_or_source": "pre_specified",
                    "final_model_status": "final_model_error_nonpredictive",
                    "formal_resampling_status": "FORMAL_RESAMPLING_JITTER_COMPLETE",
                    "figure_output_status": "ready_from_existing_direct_voxel_maps",
                    "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
                    "latest_manifest_stale_status": "manifest_missing_code_provenance",
                }
            ],
        )
        c_branch = root / "direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200/partial_spearman_no_delta_hf"
        write_complete_branch(c_branch, "direct_voxel_ULF_only_generation_manifest.json", "direct_voxel_ULF_only")
        misleading_hf_immediate = root / "direct_voxel/hf/_shared/posthoc_threshold_scan/preprocess_candidate_tau100/stn_immediate"
        misleading_hf_immediate.mkdir(parents=True)
        (misleading_hf_immediate / "candidate_mask.nii.gz").write_text("not a ULF immediate output\n", encoding="utf-8")
        d_branch = root / "normative_connectome_fiber/ulf/dtor/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau400_observed/ulf_peak_efield_tau400_no_delta_hf"
        write_complete_branch(d_branch, "normative_ULF_fiber_generation_manifest.json", "normative_ULF_fiber")

        result = build_all_endpoint_reporting(
            hf_direct_scan_summary_csv=hf_scan_csv,
            observed_branch_summary_csv=observed_csv,
            final_report_csv=final_report_csv,
            manifest_roots=[root / "direct_voxel", root / "normative_connectome_fiber"],
            missing_work_search_roots=[root / "direct_voxel", root / "normative_connectome_fiber"],
            output_dir=root / "all_endpoint_reporting",
        )

        report_rows = read_csv(Path(result["all_endpoint_report_csv"]))
        missing_rows = read_csv(Path(result["missing_work_csv"]))
        assert_equal(len([row for row in report_rows if row["source_table"] == "hf_direct_voxel_all_endpoint_scan"]), 2, "HF scan rows")
        final_rows = [row for row in report_rows if row["source_table"] == "four_model_final_report"]
        assert_equal(len(final_rows), 1, "final report rows")
        assert_true(
            "latest_manifest_provenance_status" in final_rows[0],
            "all-endpoint report carries provenance status field",
        )
        assert_equal(
            final_rows[0]["latest_manifest_provenance_status"],
            "missing_git_or_patch_provenance",
            "all-endpoint final-report provenance status",
        )
        assert_true(
            "latest_manifest_stale_status" in final_rows[0],
            "all-endpoint report carries stale status field",
        )
        assert_equal(
            final_rows[0]["latest_manifest_stale_status"],
            "manifest_missing_code_provenance",
            "all-endpoint final-report stale status",
        )
        assert_true(
            any(row["source_table"] == "discovered_branch_manifest" and row["model_id"] == "C" for row in report_rows),
            "C branch discovered",
        )
        discovered_c_rows = [
            row for row in report_rows if row["source_table"] == "discovered_branch_manifest" and row["model_id"] == "C"
        ]
        assert_equal(
            discovered_c_rows[0]["latest_manifest_provenance_status"],
            "missing_git_or_patch_provenance",
            "C discovered manifest provenance audit",
        )
        assert_equal(
            discovered_c_rows[0]["latest_manifest_stale_status"],
            "missing_code_provenance",
            "C discovered manifest stale audit",
        )
        assert_true(
            any(row["source_table"] == "discovered_branch_manifest" and row["model_id"] == "D_DTOR" for row in report_rows),
            "D branch discovered",
        )
        missing_by_id = {row["work_item_id"]: row for row in missing_rows}
        assert_equal(
            missing_by_id["C_total_ulf_exposure_sensitivity"]["work_status"],
            "not_run_missing_observed_outputs",
            "C total ULF missing",
        )
        assert_equal(
            missing_by_id["C_same_day_immediate_endpoint_family"]["work_status"],
            "not_run_missing_observed_outputs",
            "C immediate ignores HF-only immediate preprocess",
        )
        assert_equal(
            missing_by_id["C_chronic_gain_endpoint_sensitivity"]["work_status"],
            "not_run_missing_observed_outputs",
            "C gain missing",
        )
        assert_equal(
            missing_by_id["D_same_day_immediate_endpoint_family"]["work_status"],
            "not_run_missing_observed_outputs",
            "D immediate missing",
        )
        manifest = json.loads(Path(result["manifest_json"]).read_text(encoding="utf-8"))
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")
        assert_equal(
            manifest.get("manifest_provenance_counts", {}).get("missing_git_or_patch_provenance"),
            3,
            "manifest records missing-provenance counts",
        )
        assert_equal(
            manifest.get("manifest_provenance_counts", {}).get("missing_manifest"),
            3,
            "manifest records missing-manifest provenance counts",
        )
        assert_equal(
            manifest.get("manifest_stale_counts", {}).get("missing_code_provenance"),
            2,
            "manifest records missing-code-provenance stale counts",
        )
        assert_equal(
            manifest.get("manifest_stale_counts", {}).get("missing_manifest"),
            3,
            "manifest records missing-manifest stale counts",
        )


def main() -> int:
    test_all_endpoint_reporting_summarizes_existing_outputs_and_missing_sensitivities()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
