#!/usr/bin/env python3
"""Self-tests for the STN/SNr final-model formal readiness audit."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stnsnr_four_model_formal_readiness import (
    REQUIRED_FILES_BY_MANIFEST,
    formal_readiness_row,
    manifest_required_files,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")


def test_ready_hf_direct_voxel_branch() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir) / "branch"
        manifest = branch_dir / "direct_voxel_HF_generation_manifest.json"
        touch(manifest)
        for name in REQUIRED_FILES_BY_MANIFEST[manifest.name]:
            touch(branch_dir / name)

        row = formal_readiness_row(
            {
                "model_id": "A",
                "model": "HF direct voxel",
                "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                "latest_manifest": str(manifest),
            }
        )

        assert_equal(row["formal_readiness_status"], "READY_FOR_FORMAL_DRIVER", "ready branch")
        assert_equal(row["required_file_count"], 4, "required files include manifest")
        assert_equal(row["existing_required_file_count"], 4, "all required files exist")
        assert_equal(row["missing_required_files"], "", "no missing files")


def test_missing_required_branch_file() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir) / "branch"
        manifest = branch_dir / "normative_ULF_fiber_generation_manifest.json"
        touch(manifest)
        touch(branch_dir / "normative_ULF_fiber_mapping_qc.json")
        touch(branch_dir / "normative_ULF_fiber_scores.csv")

        row = formal_readiness_row(
            {
                "model_id": "D_DTOR",
                "model": "ULF normative fiber dTOR",
                "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                "latest_manifest": str(manifest),
            }
        )

        assert_equal(row["formal_readiness_status"], "NOT_READY_MISSING_REQUIRED_FILES", "missing branch file")
        assert_equal(row["required_file_count"], 4, "required file count")
        assert_equal(row["existing_required_file_count"], 3, "existing file count")
        assert_equal(
            row["missing_required_files"],
            str(branch_dir / "normative_ULF_fiber_loocv_predictions.csv"),
            "missing prediction file",
        )


def test_no_formal_target_is_not_ready_without_file_checks() -> None:
    row = formal_readiness_row(
        {
            "model_id": "C",
            "model": "ULF direct voxel",
            "formal_target_status": "NO_FINAL_MODEL",
            "latest_manifest": "/does/not/matter.json",
        }
    )
    assert_equal(row["formal_readiness_status"], "NOT_READY_NO_FORMAL_TARGET", "no target status")
    assert_equal(row["required_file_count"], 0, "no target required files")
    assert_equal(row["missing_required_files"], "", "no target missing list")


def test_unknown_manifest_type_is_explicit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        manifest = Path(tmp_dir) / "unknown_generation_manifest.json"
        touch(manifest)
        row = formal_readiness_row(
            {
                "model_id": "X",
                "model": "Unknown model",
                "formal_target_status": "READY_FOR_FORMAL_RESAMPLING",
                "latest_manifest": str(manifest),
            }
        )
    assert_equal(row["formal_readiness_status"], "NOT_READY_UNKNOWN_MANIFEST_TYPE", "unknown manifest")


def test_manifest_required_files_known_types() -> None:
    assert_equal(
        manifest_required_files(Path("normative_HF_fiber_generation_manifest.json")),
        [
            "normative_HF_fiber_mapping_qc.json",
            "normative_HF_fiber_scores.csv",
            "normative_HF_fiber_loocv_predictions.csv",
        ],
        "HF fiber required files",
    )


def main() -> int:
    test_ready_hf_direct_voxel_branch()
    test_missing_required_branch_file()
    test_no_formal_target_is_not_ready_without_file_checks()
    test_unknown_manifest_type_is_explicit()
    test_manifest_required_files_known_types()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
