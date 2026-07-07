#!/usr/bin/env python3
"""Self-tests for four-model gate classification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from stnsnr_four_model_gate_status import classify_gate, classify_hf_prediction_validity, run_gate_status


def run_selftest() -> dict[str, object]:
    passing = classify_gate({"spearman_rho": 0.2, "q2": 0.01}, predictions_finite=True, output_exists=True)
    stopping = classify_gate({"spearman_rho": -0.01, "q2": -0.2}, predictions_finite=True, output_exists=True)
    missing = classify_gate({}, predictions_finite=False, output_exists=False)
    predictive, predictive_reason = classify_hf_prediction_validity(
        {"spearman_rho": 0.2, "q2": 0.1},
        {
            "mae_model": 1.0,
            "mae_baseline": 2.0,
            "rmse_model": 1.5,
            "rmse_baseline": 2.5,
            "score_nonconstant": True,
            "residual_dominance_proxy_pass": True,
        },
        predictions_finite=True,
        output_exists=True,
    )
    failed, failed_reason = classify_hf_prediction_validity(
        {"spearman_rho": -0.01, "q2": -0.2},
        {"score_nonconstant": True},
        predictions_finite=True,
        output_exists=True,
    )
    stable, stable_reason = classify_hf_prediction_validity(
        {"spearman_rho": 0.2, "q2": 0.1},
        {
            "mae_model": 2.0,
            "mae_baseline": 1.0,
            "rmse_model": 2.0,
            "rmse_baseline": 1.0,
            "score_nonconstant": True,
            "residual_dominance_proxy_pass": True,
        },
        predictions_finite=True,
        output_exists=True,
    )
    if passing != "PASS_TO_NEXT_ROUND":
        raise AssertionError(f"expected PASS_TO_NEXT_ROUND, got {passing}")
    if stopping != "STOP_FORMAL_REMAIN_EXPLORATORY":
        raise AssertionError(f"expected STOP_FORMAL_REMAIN_EXPLORATORY, got {stopping}")
    if missing != "MISSING_OUTPUT":
        raise AssertionError(f"expected MISSING_OUTPUT, got {missing}")
    if predictive != "predictive_valid":
        raise AssertionError(f"expected predictive_valid, got {predictive}: {predictive_reason}")
    if failed != "failed_unstable":
        raise AssertionError(f"expected failed_unstable, got {failed}: {failed_reason}")
    if stable != "stable_nonpredictive":
        raise AssertionError(f"expected stable_nonpredictive, got {stable}: {stable_reason}")
    return {
        "status": "PASS",
        "passing": passing,
        "stopping": stopping,
        "missing": missing,
        "predictive": predictive,
        "failed": failed,
        "stable": stable,
    }


def test_run_gate_status_manifest_records_code_provenance() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        output_dir = root / "gate_status"
        with patch("stnsnr_four_model_gate_status.branch_specs", return_value=[]):
            run_gate_status(SimpleNamespace(val_root=str(root), output_dir=str(output_dir)))

        manifest = json.loads((output_dir / "four_model_gate_status_manifest.json").read_text(encoding="utf-8"))
        if not manifest.get("code_provenance", {}).get("git_commit"):
            raise AssertionError("gate status manifest records git commit")


def main() -> int:
    test_run_gate_status_manifest_records_code_provenance()
    print(json.dumps(run_selftest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
