#!/usr/bin/env python3
"""Self-tests for STN/SNr four-model final reporting readiness."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from stnsnr_four_model_final_reporting import build_final_reporting


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def touch_many(root: Path, filenames: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        (root / filename).write_text("placeholder\n", encoding="utf-8")


def test_final_reporting_records_unique_final_models_and_missing_fiber_figure_inputs() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        output_dir = root / "final_reporting"
        a_dir = root / "A"
        b_dir = root / "B_DTOR"
        c_dir = root / "C"
        d_dir = root / "D_DTOR"
        touch_many(
            a_dir,
            [
                "direct_voxel_HF_generation_manifest.json",
                "direct_voxel_HF_coef.nii.gz",
                "direct_voxel_HF_sweet_sour.nii.gz",
                "direct_voxel_HF_stability.nii.gz",
                "direct_voxel_HF_bootstrap_se.nii.gz",
                "direct_voxel_HF_jitter_se.nii.gz",
            ],
        )
        touch_many(b_dir, ["normative_HF_fiber_generation_manifest.json"])
        touch_many(
            c_dir,
            [
                "direct_voxel_ULF_only_generation_manifest.json",
                "direct_voxel_ULF_only_coef.nii.gz",
                "direct_voxel_ULF_only_sweet_sour.nii.gz",
                "direct_voxel_ULF_only_stability.nii.gz",
                "direct_voxel_ULF_only_bootstrap_se.nii.gz",
                "direct_voxel_ULF_only_jitter_se.nii.gz",
            ],
        )
        touch_many(d_dir, ["normative_ULF_fiber_generation_manifest.json"])

        status_csv = root / "status.csv"
        write_csv(
            status_csv,
            [
                {
                    "model_id": "A",
                    "model": "HF direct voxel",
                    "branch": "tau200/partial_spearman",
                    "hf_final_model_source": "pre_specified",
                    "hf_final_model_role": "primary",
                    "hf_final_model_status": "final_model_error_nonpredictive",
                    "ulf_final_model_branch": "",
                    "ulf_final_model_role": "",
                    "ulf_final_model_status": "",
                    "formal_resampling_status": "FORMAL_RESAMPLING_JITTER_COMPLETE",
                    "latest_manifest": str(a_dir / "direct_voxel_HF_generation_manifest.json"),
                    "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
                    "latest_manifest_stale_status": "manifest_missing_code_provenance",
                },
                {
                    "model_id": "B_DTOR",
                    "model": "HF normative fiber dTOR",
                    "branch": "peak_efield_tau800_primary",
                    "hf_final_model_source": "pre_specified",
                    "hf_final_model_role": "primary",
                    "hf_final_model_status": "final_model_error_nonpredictive",
                    "ulf_final_model_branch": "",
                    "ulf_final_model_role": "",
                    "ulf_final_model_status": "",
                    "formal_resampling_status": "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING",
                    "latest_manifest": str(b_dir / "normative_HF_fiber_generation_manifest.json"),
                    "latest_manifest_provenance_status": "has_git_or_patch_provenance",
                    "latest_manifest_stale_status": "manifest_from_current_head",
                },
                {
                    "model_id": "C",
                    "model": "ULF direct voxel",
                    "branch": "partial_spearman_no_delta_hf",
                    "hf_final_model_source": "",
                    "hf_final_model_role": "",
                    "hf_final_model_status": "",
                    "ulf_final_model_branch": "no_delta_hf",
                    "ulf_final_model_role": "primary",
                    "ulf_final_model_status": "final_model_error_nonpredictive",
                    "formal_resampling_status": "FORMAL_RESAMPLING_JITTER_COMPLETE",
                    "latest_manifest": str(c_dir / "direct_voxel_ULF_only_generation_manifest.json"),
                    "latest_manifest_provenance_status": "has_git_or_patch_provenance",
                    "latest_manifest_stale_status": "manifest_from_different_commit",
                },
                {
                    "model_id": "D_DTOR",
                    "model": "ULF normative fiber dTOR",
                    "branch": "ulf_peak_efield_tau400_no_delta_hf",
                    "hf_final_model_source": "",
                    "hf_final_model_role": "",
                    "hf_final_model_status": "",
                    "ulf_final_model_branch": "no_delta_hf",
                    "ulf_final_model_role": "primary",
                    "ulf_final_model_status": "final_model_error_nonpredictive",
                    "formal_resampling_status": "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING",
                    "latest_manifest": str(d_dir / "normative_ULF_fiber_generation_manifest.json"),
                    "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
                    "latest_manifest_stale_status": "manifest_missing_code_provenance",
                },
            ],
        )
        worklist_csv = root / "worklist.csv"
        write_csv(
            worklist_csv,
            [
                {
                    "model_id": model_id,
                    "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                    "final_branch_or_source": final_branch_or_source,
                    "final_model_role": "primary",
                    "final_model_status": "final_model_error_nonpredictive",
                    "latest_manifest": manifest,
                }
                for model_id, final_branch_or_source, manifest in [
                    ("A", "pre_specified", str(a_dir / "direct_voxel_HF_generation_manifest.json")),
                    ("B_DTOR", "pre_specified", str(b_dir / "normative_HF_fiber_generation_manifest.json")),
                    ("C", "no_delta_hf", str(c_dir / "direct_voxel_ULF_only_generation_manifest.json")),
                    ("D_DTOR", "no_delta_hf", str(d_dir / "normative_ULF_fiber_generation_manifest.json")),
                ]
            ],
        )
        readiness_csv = root / "readiness.csv"
        write_csv(
            readiness_csv,
            [
                {
                    "model_id": model_id,
                    "formal_readiness_status": "READY_FOR_FORMAL_DRIVER",
                    "formal_readiness_reason": "all_required_branch_files_present",
                }
                for model_id in ["A", "B_DTOR", "C", "D_DTOR"]
            ],
        )
        direct_permutation_csv = root / "direct_permutation.csv"
        write_csv(
            direct_permutation_csv,
            [
                {"model_id": "A", "p_plus_one_two_sided": "0.9455", "permutation_status": "complete"},
                {"model_id": "C", "p_plus_one_two_sided": "0.2325", "permutation_status": "complete"},
            ],
        )
        direct_bootstrap_csv = root / "direct_bootstrap.csv"
        write_csv(
            direct_bootstrap_csv,
            [
                {"model_id": "A", "bootstrap_status": "complete", "finite_bootstrap_count": "10000"},
                {"model_id": "C", "bootstrap_status": "complete", "finite_bootstrap_count": "10000"},
            ],
        )
        direct_jitter_csv = root / "direct_jitter.csv"
        write_csv(
            direct_jitter_csv,
            [
                {"model_id": "A", "jitter_status": "complete", "finite_jitter_count": "1000"},
                {"model_id": "C", "jitter_status": "complete", "finite_jitter_count": "1000"},
            ],
        )
        fiber_permutation_csv = root / "fiber_permutation.csv"
        write_csv(
            fiber_permutation_csv,
            [
                {"model_id": "B_DTOR", "p_plus_one_two_sided": "0.9471", "permutation_status": "complete"},
                {"model_id": "D_DTOR", "p_plus_one_two_sided": "0.0890", "permutation_status": "complete"},
            ],
        )
        fiber_bootstrap_csv = root / "fiber_bootstrap.csv"
        write_csv(
            fiber_bootstrap_csv,
            [
                {"model_id": "B_DTOR", "bootstrap_status": "complete", "finite_bootstrap_count": "10000"},
                {"model_id": "D_DTOR", "bootstrap_status": "complete", "finite_bootstrap_count": "10000"},
            ],
        )
        sensitivity_csv = root / "fiber_sensitivity.csv"
        write_csv(
            sensitivity_csv,
            [
                {
                    "model_id": "B_DTOR",
                    "oss_sensitivity_status": "not_run_missing_oss_inputs",
                    "jitter_qc_status": "not_run_missing_jitter_inputs",
                    "oss_missing_inputs": "/tmp/missing_oss.npy",
                    "jitter_missing_inputs": "no_jitter_inputs_found_in_search_roots",
                    "jitter_input_search_roots": "/tmp/branch;/tmp/preprocess",
                },
                {
                    "model_id": "D_DTOR",
                    "oss_sensitivity_status": "not_run_missing_oss_inputs",
                    "jitter_qc_status": "not_run_missing_jitter_inputs",
                    "oss_missing_inputs": "/tmp/missing_d_oss.npy",
                    "jitter_missing_inputs": "no_jitter_inputs_found_in_search_roots",
                    "jitter_input_search_roots": "/tmp/d_branch;/tmp/d_preprocess",
                },
            ],
        )

        result = build_final_reporting(
            status_csv=status_csv,
            worklist_csv=worklist_csv,
            readiness_csv=readiness_csv,
            direct_permutation_csv=direct_permutation_csv,
            direct_bootstrap_csv=direct_bootstrap_csv,
            direct_jitter_csv=direct_jitter_csv,
            fiber_permutation_csv=fiber_permutation_csv,
            fiber_bootstrap_csv=fiber_bootstrap_csv,
            fiber_sensitivity_csv=sensitivity_csv,
            output_dir=output_dir,
            cohort_n=16,
            density_cache_roots=[root / "missing_density_caches"],
        )

        report_rows = read_csv(Path(result["final_report_csv"]))
        readiness_rows = read_csv(Path(result["figure_readiness_csv"]))
        report_by_id = {row["model_id"]: row for row in report_rows}
        readiness_by_id = {row["model_id"]: row for row in readiness_rows}
        assert_equal(set(report_by_id), {"A", "B_DTOR", "C", "D_DTOR"}, "final report models")
        assert_equal(report_by_id["A"]["final_branch_or_source"], "pre_specified", "A final source")
        assert_equal(report_by_id["C"]["final_branch_or_source"], "no_delta_hf", "C final branch")
        assert_equal(report_by_id["D_DTOR"]["formal_p_plus_one_two_sided"], "0.0890", "D formal p")
        assert_equal(report_by_id["B_DTOR"]["hypothesis_generating"], "true", "B interpretation flag")
        assert_true(
            "latest_manifest_provenance_status" in report_by_id["A"],
            "final report carries provenance status field",
        )
        assert_equal(
            report_by_id["A"]["latest_manifest_provenance_status"],
            "missing_git_or_patch_provenance",
            "A provenance status",
        )
        assert_true(
            "latest_manifest_stale_status" in report_by_id["A"],
            "final report carries stale status field",
        )
        assert_equal(
            report_by_id["A"]["latest_manifest_stale_status"],
            "manifest_missing_code_provenance",
            "A stale status",
        )
        assert_equal(
            report_by_id["C"]["latest_manifest_stale_status"],
            "manifest_from_different_commit",
            "C stale status",
        )
        assert_equal(readiness_by_id["A"]["direct_voxel_display_status"], "ready_from_existing_maps", "A display status")
        assert_true(
            "latest_manifest_provenance_status" in readiness_by_id["A"],
            "figure readiness carries provenance status field",
        )
        assert_equal(
            readiness_by_id["B_DTOR"]["latest_manifest_provenance_status"],
            "has_git_or_patch_provenance",
            "B readiness provenance status",
        )
        assert_true(
            "latest_manifest_stale_status" in readiness_by_id["A"],
            "figure readiness carries stale status field",
        )
        assert_equal(
            readiness_by_id["B_DTOR"]["latest_manifest_stale_status"],
            "manifest_from_current_head",
            "B readiness stale status",
        )
        assert_equal(
            readiness_by_id["A"]["formal_resampling_status"],
            "FORMAL_RESAMPLING_JITTER_COMPLETE",
            "A readiness formal status",
        )
        assert_equal(readiness_by_id["C"]["direct_voxel_display_status"], "ready_from_existing_maps", "C display status")
        assert_equal(
            readiness_by_id["B_DTOR"]["fiber_density_label_cache_status"],
            "not_run_missing_density_label_cache",
            "B fiber cache status",
        )
        assert_equal(
            report_by_id["B_DTOR"]["oss_missing_inputs"],
            "/tmp/missing_oss.npy",
            "B final report OSS missing inputs",
        )
        assert_equal(
            report_by_id["B_DTOR"]["jitter_missing_inputs"],
            "no_jitter_inputs_found_in_search_roots",
            "B final report jitter missing inputs",
        )
        assert_equal(
            readiness_by_id["D_DTOR"]["jitter_input_search_roots"],
            "/tmp/d_branch;/tmp/d_preprocess",
            "D readiness jitter search roots",
        )
        assert_equal(
            readiness_by_id["D_DTOR"]["fiber_density_label_cache_status"],
            "not_run_missing_density_label_cache",
            "D fiber cache status",
        )
        markdown = Path(result["final_report_md"]).read_text(encoding="utf-8")
        assert_true("n=16" in markdown, "markdown records cohort size")
        assert_true("hypothesis-generating" in markdown, "markdown records interpretation")
        manifest = json.loads(Path(result["manifest_json"]).read_text(encoding="utf-8"))
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_final_reporting_records_unique_final_models_and_missing_fiber_figure_inputs()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
