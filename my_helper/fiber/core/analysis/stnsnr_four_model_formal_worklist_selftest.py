#!/usr/bin/env python3
"""Self-tests for the STN/SNr final-model formal target worklist."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from stnsnr_four_model_formal_worklist import formal_target_row, run_worklist


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_hf_ready_target() -> None:
    row = formal_target_row(
        {
            "model_id": "A",
            "model": "HF direct voxel",
            "hf_final_model_source": "pre_specified",
            "hf_final_model_role": "primary",
            "hf_final_model_status": "final_model_error_nonpredictive",
            "latest_manifest_provenance_status": "missing_git_or_patch_provenance",
            "latest_manifest_stale_status": "missing_code_provenance",
        }
    )
    assert_equal(row["model_family"], "hf", "HF family")
    assert_equal(row["formal_target_status"], "READY_FOR_FORMAL_RESAMPLING", "HF target")
    assert_equal(row["final_branch_or_source"], "pre_specified", "HF final source")
    assert_equal(
        row["latest_manifest_provenance_status"],
        "missing_git_or_patch_provenance",
        "HF provenance status",
    )
    assert_equal(row["latest_manifest_stale_status"], "missing_code_provenance", "HF stale status")


def test_observed_robustness_connectome_not_formal_target() -> None:
    row = formal_target_row(
        {
            "model_id": "B_PPMI",
            "model": "HF normative fiber PPMI",
            "hf_final_model_source": "pre_specified",
            "hf_final_model_role": "primary",
            "hf_final_model_status": "final_model_error_nonpredictive",
        }
    )
    assert_equal(row["model_family"], "hf", "B_PPMI family")
    assert_equal(
        row["formal_target_status"],
        "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING",
        "B_PPMI target status",
    )
    assert_equal(row["formal_target_reason"], "connectome_observed_robustness_only", "B_PPMI target reason")


def test_ulf_ready_target() -> None:
    row = formal_target_row(
        {
            "model_id": "D_DTOR",
            "model": "ULF add-on normative fiber dTOR",
            "ulf_final_model_branch": "no_delta_hf",
            "ulf_final_model_role": "primary",
            "ulf_final_model_status": "final_model_error_nonpredictive",
        }
    )
    assert_equal(row["model_family"], "ulf", "ULF family")
    assert_equal(row["formal_target_status"], "READY_FOR_FORMAL_RESAMPLING", "ULF target")
    assert_equal(row["final_branch_or_source"], "no_delta_hf", "ULF final branch")


def test_no_final_model_target() -> None:
    row = formal_target_row(
        {
            "model_id": "C",
            "model": "ULF add-on direct voxel",
            "ulf_final_model_branch": "none",
            "ulf_final_model_role": "no_final_model",
            "ulf_final_model_status": "no_final_model_absent_no_stable_grid",
        }
    )
    assert_equal(row["formal_target_status"], "NO_FINAL_MODEL", "no-final target")
    assert_equal(row["formal_target_reason"], "no_final_model_absent_no_stable_grid", "no-final reason")


def test_run_worklist_manifest_records_code_provenance() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        status_csv = root / "status.csv"
        output_dir = root / "formal_worklist"
        status_csv.write_text(
            "\n".join(
                [
                    "model_id,model,hf_final_model_source,hf_final_model_role,hf_final_model_status,branch,latest_manifest,latest_manifest_provenance_status,latest_manifest_stale_status",
                    "A,HF direct voxel,pre_specified,primary,final_model_error_nonpredictive,tau200/partial_spearman,/tmp/direct_voxel_HF_generation_manifest.json,missing_git_or_patch_provenance,missing_code_provenance",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        run_worklist(SimpleNamespace(status_csv=str(status_csv), output_dir=str(output_dir)))

        manifest = json.loads(
            (output_dir / "four_model_formal_target_worklist_manifest.json").read_text(encoding="utf-8")
        )
        if not manifest.get("code_provenance", {}).get("git_commit"):
            raise AssertionError("formal target worklist manifest records git commit")
        csv_text = (output_dir / "four_model_formal_target_worklist.csv").read_text(encoding="utf-8")
        if "latest_manifest_provenance_status" not in csv_text:
            raise AssertionError("formal target worklist CSV records provenance status field")
        if "missing_git_or_patch_provenance" not in csv_text:
            raise AssertionError("formal target worklist CSV preserves provenance status value")
        if "latest_manifest_stale_status" not in csv_text:
            raise AssertionError("formal target worklist CSV records stale status field")
        if "missing_code_provenance" not in csv_text:
            raise AssertionError("formal target worklist CSV preserves stale status value")


def main() -> int:
    test_hf_ready_target()
    test_observed_robustness_connectome_not_formal_target()
    test_ulf_ready_target()
    test_no_final_model_target()
    test_run_worklist_manifest_records_code_provenance()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
