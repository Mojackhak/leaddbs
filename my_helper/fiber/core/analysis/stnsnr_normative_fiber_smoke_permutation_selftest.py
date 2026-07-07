#!/usr/bin/env python3
"""Self-tests for dTOR normative-fiber smoke permutation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from stnsnr_normative_fiber_smoke_permutation import (
    NormativeFiberTarget,
    file_prefix_for_manifest,
    normative_fiber_loocv_statistic,
    prepare_candidate_union,
    run_target_smoke_permutation,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def synthetic_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.array(
        [
            [0.0, 2.0, 4.0, 0.0, 3.0, 1.0],
            [1.0, 3.0, 5.0, 0.0, 0.0, 2.0],
            [2.0, 4.0, 6.0, 1.0, 0.0, 3.0],
            [3.0, 5.0, 7.0, 1.0, 2.0, 4.0],
            [4.0, 6.0, 8.0, 2.0, 2.0, 5.0],
            [5.0, 7.0, 9.0, 2.0, 4.0, 6.0],
        ],
        dtype=np.float32,
    )
    y = np.array([10.0, 9.0, 8.0, 6.0, 5.0, 4.0], dtype=float)
    nuisance = np.array([0.0, 0.1, 0.0, 0.2, 0.1, 0.2], dtype=float)
    fiber_ids = np.arange(x.shape[1], dtype=np.int64)
    return x, y, nuisance, fiber_ids


def test_candidate_union_keeps_fold_candidates() -> None:
    x, _, _, fiber_ids = synthetic_inputs()
    reduced = prepare_candidate_union(x=x, fiber_ids=fiber_ids, tau=0.5, min_coverage=2)
    assert_true(reduced.x.shape[1] <= x.shape[1], "candidate union should not expand features")
    assert_equal(len(reduced.fold_candidate_masks), x.shape[0], "one mask per fold")
    assert_true(all(mask.any() for mask in reduced.fold_candidate_masks), "all folds have candidates")


def test_loocv_statistic_is_finite() -> None:
    x, y, nuisance, fiber_ids = synthetic_inputs()
    reduced = prepare_candidate_union(x=x, fiber_ids=fiber_ids, tau=0.5, min_coverage=2)
    result = normative_fiber_loocv_statistic(
        reduced=reduced,
        y_post=y,
        nuisance=nuisance,
        scale_direction="lower",
    )
    assert_true(np.isfinite(result["spearman_rho"]), "observed Spearman should be finite")
    assert_equal(result["n_subjects"], 6, "subject count")
    assert_true(result["fold_n_candidate_fibers_min"] > 0, "fold candidates")


def test_file_prefix_for_manifest() -> None:
    assert_equal(
        file_prefix_for_manifest(Path("normative_HF_fiber_generation_manifest.json")),
        "normative_HF_fiber",
        "HF prefix",
    )
    assert_equal(
        file_prefix_for_manifest(Path("normative_ULF_fiber_generation_manifest.json")),
        "normative_ULF_fiber",
        "ULF prefix",
    )


def test_run_target_smoke_permutation_writes_outputs() -> None:
    x, y, nuisance, fiber_ids = synthetic_inputs()
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        x_path = branch_dir / "X.npy"
        fiber_ids_path = branch_dir / "fiber_ids.npy"
        scores_path = branch_dir / "scores.csv"
        manifest_path = branch_dir / "normative_HF_fiber_generation_manifest.json"
        np.save(x_path, x)
        np.save(fiber_ids_path, fiber_ids)
        scores_path.write_text(
            "subject_id,Y_post,Y_base\n"
            "s1,10,0.0\n"
            "s2,9,0.1\n"
            "s3,8,0.0\n"
            "s4,6,0.2\n"
            "s5,5,0.1\n"
            "s6,4,0.2\n",
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps({"outputs": {"generation_manifest_json": str(manifest_path)}}), encoding="utf-8")
        target = NormativeFiberTarget(
            model_id="B_DTOR",
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=x_path,
            fiber_ids_path=fiber_ids_path,
            scores_csv=scores_path,
            outcome_column="Y_post",
            nuisance_columns=("Y_base",),
            scale_direction="lower",
            tau=0.5,
            min_coverage=2,
        )

        row = run_target_smoke_permutation(target, n_permutations=7, seed=42)

        assert_equal(row["B"], 7, "permutation count")
        assert_true((branch_dir / "normative_HF_fiber_smoke_permutation_summary.csv").is_file(), "summary exists")
        null_stats = np.load(branch_dir / "normative_HF_fiber_smoke_permutation_null_stats.npy")
        assert_equal(null_stats.shape, (7,), "null-stat shape")


def test_run_target_formal_permutation_writes_formal_outputs() -> None:
    x, y, nuisance, fiber_ids = synthetic_inputs()
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        x_path = branch_dir / "X.npy"
        fiber_ids_path = branch_dir / "fiber_ids.npy"
        scores_path = branch_dir / "scores.csv"
        manifest_path = branch_dir / "normative_HF_fiber_generation_manifest.json"
        np.save(x_path, x)
        np.save(fiber_ids_path, fiber_ids)
        scores_path.write_text(
            "subject_id,Y_post,Y_base\n"
            "s1,10,0.0\n"
            "s2,9,0.1\n"
            "s3,8,0.0\n"
            "s4,6,0.2\n"
            "s5,5,0.1\n"
            "s6,4,0.2\n",
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps({"outputs": {"generation_manifest_json": str(manifest_path)}}), encoding="utf-8")
        target = NormativeFiberTarget(
            model_id="B_DTOR",
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=x_path,
            fiber_ids_path=fiber_ids_path,
            scores_csv=scores_path,
            outcome_column="Y_post",
            nuisance_columns=("Y_base",),
            scale_direction="lower",
            tau=0.5,
            min_coverage=2,
        )

        row = run_target_smoke_permutation(target, n_permutations=7, seed=42, tier="formal")

        assert_equal(row["resampling_tier"], "formal", "tier")
        assert_true((branch_dir / "normative_HF_fiber_permutation_summary.csv").is_file(), "formal summary exists")
        assert_true(not (branch_dir / "normative_HF_fiber_smoke_permutation_summary.csv").exists(), "smoke summary not written")
        null_stats = np.load(branch_dir / "normative_HF_fiber_permutation_null_stats.npy")
        assert_equal(null_stats.shape, (7,), "formal null-stat shape")


def main() -> int:
    test_candidate_union_keeps_fold_candidates()
    test_loocv_statistic_is_finite()
    test_file_prefix_for_manifest()
    test_run_target_smoke_permutation_writes_outputs()
    test_run_target_formal_permutation_writes_formal_outputs()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
