#!/usr/bin/env python3
"""Self-tests for dTOR normative-fiber formal bootstrap."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from stnsnr_normative_fiber_formal_bootstrap import run_target_bootstrap
from stnsnr_normative_fiber_smoke_permutation import NormativeFiberTarget


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def synthetic_inputs() -> tuple[np.ndarray, np.ndarray]:
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
    fiber_ids = np.arange(x.shape[1], dtype=np.int64)
    return x, fiber_ids


def test_run_target_bootstrap_writes_stability_outputs() -> None:
    x, fiber_ids = synthetic_inputs()
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

        row = run_target_bootstrap(target, n_bootstraps=9, seed=42)

        assert_equal(row["B"], 9, "bootstrap count")
        assert_equal(row["bootstrap_status"], "complete", "bootstrap status")
        assert_true((branch_dir / "normative_HF_fiber_bootstrap_summary.csv").is_file(), "summary exists")
        assert_true((branch_dir / "normative_HF_fiber_bootstrap_se.csv").is_file(), "se table exists")
        assert_true(
            (branch_dir / "normative_HF_fiber_bootstrap_selection_frequency.csv").is_file(),
            "selection frequency exists",
        )
        assert_true(
            (branch_dir / "normative_HF_fiber_bootstrap_sign_stability.csv").is_file(),
            "sign stability exists",
        )
        manifest = json.loads((branch_dir / "normative_HF_fiber_bootstrap_manifest.json").read_text(encoding="utf-8"))
        assert_true(bool(manifest.get("code_provenance", {}).get("git_commit")), "manifest records git commit")


def main() -> int:
    test_run_target_bootstrap_writes_stability_outputs()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
