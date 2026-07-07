#!/usr/bin/env python3
"""Self-tests for dTOR normative-fiber sensitivity readiness audit."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stnsnr_normative_fiber_sensitivity_readiness import assess_target_sensitivity_readiness
from stnsnr_normative_fiber_smoke_permutation import NormativeFiberTarget


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_missing_oss_and_jitter_inputs_are_explicit_not_run() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        branch_dir = Path(tmp_dir)
        preprocess_dir = branch_dir / "preprocess"
        preprocess_dir.mkdir()
        manifest_path = branch_dir / "normative_HF_fiber_generation_manifest.json"
        manifest_path.write_text(json.dumps({"outputs": {"preprocess_dir": str(preprocess_dir)}}), encoding="utf-8")
        (branch_dir / "normative_HF_fiber_jitter_summary.csv").write_text(
            "model_id,jitter_qc_status\nB_DTOR,not_run_missing_jitter_inputs\n",
            encoding="utf-8",
        )
        target = NormativeFiberTarget(
            model_id="B_DTOR",
            manifest_path=manifest_path,
            branch_dir=branch_dir,
            x_path=preprocess_dir / "X.npy",
            fiber_ids_path=preprocess_dir / "fiber_ids.npy",
            scores_csv=branch_dir / "scores.csv",
            outcome_column="Y_post",
            nuisance_columns=("Y_base",),
            scale_direction="lower",
            tau=800,
            min_coverage=5,
        )

        row = assess_target_sensitivity_readiness(target)

        assert_equal(row["oss_sensitivity_status"], "not_run_missing_oss_inputs", "OSS status")
        assert_equal(row["jitter_qc_status"], "not_run_missing_jitter_inputs", "jitter status")
        assert_true((branch_dir / "normative_HF_fiber_sensitivity_readiness_status.json").is_file(), "status JSON exists")
        status = json.loads((branch_dir / "normative_HF_fiber_sensitivity_readiness_status.json").read_text(encoding="utf-8"))
        assert_true(bool(status.get("code_provenance", {}).get("git_commit")), "status records git commit")


def main() -> int:
    test_missing_oss_and_jitter_inputs_are_explicit_not_run()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
