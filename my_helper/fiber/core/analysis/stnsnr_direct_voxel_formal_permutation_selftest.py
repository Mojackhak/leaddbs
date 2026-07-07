#!/usr/bin/env python3
"""Self-tests for direct-voxel final-model formal permutation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from stnsnr_direct_voxel_formal_permutation import (
    DirectVoxelTarget,
    direct_voxel_loocv_statistic,
    file_prefix_for_manifest,
    run_target_permutation,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def synthetic_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.array(
        [
            [0.0, 2.0, 4.0, 0.0, 3.0],
            [1.0, 3.0, 5.0, 0.0, 0.0],
            [2.0, 4.0, 6.0, 1.0, 0.0],
            [3.0, 5.0, 7.0, 1.0, 2.0],
            [4.0, 6.0, 8.0, 2.0, 2.0],
            [5.0, 7.0, 9.0, 2.0, 4.0],
        ],
        dtype=np.float32,
    )
    nuisance = np.array([0.0, 0.1, 0.0, 0.2, 0.1, 0.2], dtype=float)
    y = np.array([10.0, 9.0, 8.0, 6.0, 5.0, 4.0], dtype=float)
    return x, y, nuisance


def test_loocv_statistic_is_full_process_and_finite() -> None:
    x, y, nuisance = synthetic_inputs()
    result = direct_voxel_loocv_statistic(
        x=x,
        y_post=y,
        nuisance=nuisance,
        scale_direction="lower",
        tau=0.5,
        min_coverage=2,
    )
    assert_true(np.isfinite(result["spearman_rho"]), "observed Spearman should be finite")
    assert_true(np.isfinite(result["q2"]), "observed Q2 should be finite")
    assert_equal(result["n_subjects"], 6, "subject count")
    assert_true(result["fold_n_valid_score_voxels_min"] > 0, "fold score support")


def test_file_prefix_for_manifest() -> None:
    assert_equal(
        file_prefix_for_manifest(Path("direct_voxel_HF_generation_manifest.json")),
        "direct_voxel_HF",
        "HF prefix",
    )
    assert_equal(
        file_prefix_for_manifest(Path("direct_voxel_ULF_only_generation_manifest.json")),
        "direct_voxel_ULF_only",
        "ULF prefix",
    )


def test_run_target_permutation_writes_summary_and_null_stats() -> None:
    x, y, nuisance = synthetic_inputs()
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        x_path = branch_dir / "X.npy"
        subjects_path = branch_dir / "subjects.csv"
        manifest_path = branch_dir / "direct_voxel_HF_generation_manifest.json"
        np.save(x_path, x)
        subjects_path.write_text(
            "subject_id,y_post,y_base\n"
            "s1,10,0.0\n"
            "s2,9,0.1\n"
            "s3,8,0.0\n"
            "s4,6,0.2\n"
            "s5,5,0.1\n"
            "s6,4,0.2\n",
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps({"outputs": {"generation_manifest_json": str(manifest_path)}}), encoding="utf-8")
        target = DirectVoxelTarget(
            model_id="A",
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=x_path,
            subjects_csv=subjects_path,
            outcome_column="y_post",
            nuisance_columns=("y_base",),
            scale_direction="lower",
            tau=0.5,
            min_coverage=2,
        )

        row = run_target_permutation(target, n_permutations=7, seed=42)

        assert_equal(row["B"], 7, "permutation count")
        assert_true(0.0 <= row["p_plus_one_two_sided"] <= 1.0, "plus-one p range")
        assert_true((branch_dir / "direct_voxel_HF_permutation_summary.csv").is_file(), "summary exists")
        null_stats = np.load(branch_dir / "direct_voxel_HF_permutation_null_stats.npy")
        assert_equal(null_stats.shape, (7,), "null-stat shape")
        manifest = json.loads((branch_dir / "direct_voxel_HF_formal_permutation_manifest.json").read_text(encoding="utf-8"))
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_loocv_statistic_is_full_process_and_finite()
    test_file_prefix_for_manifest()
    test_run_target_permutation_writes_summary_and_null_stats()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
