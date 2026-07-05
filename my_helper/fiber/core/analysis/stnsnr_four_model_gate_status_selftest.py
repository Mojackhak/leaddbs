#!/usr/bin/env python3
"""Self-tests for four-model gate classification."""

from __future__ import annotations

import json

from stnsnr_four_model_gate_status import classify_gate


def run_selftest() -> dict[str, object]:
    passing = classify_gate({"spearman_rho": 0.2, "q2": 0.01}, predictions_finite=True, output_exists=True)
    stopping = classify_gate({"spearman_rho": -0.01, "q2": -0.2}, predictions_finite=True, output_exists=True)
    missing = classify_gate({}, predictions_finite=False, output_exists=False)
    if passing != "PASS_TO_NEXT_ROUND":
        raise AssertionError(f"expected PASS_TO_NEXT_ROUND, got {passing}")
    if stopping != "STOP_FORMAL_REMAIN_EXPLORATORY":
        raise AssertionError(f"expected STOP_FORMAL_REMAIN_EXPLORATORY, got {stopping}")
    if missing != "MISSING_OUTPUT":
        raise AssertionError(f"expected MISSING_OUTPUT, got {missing}")
    return {"status": "PASS", "passing": passing, "stopping": stopping, "missing": missing}


def main() -> int:
    print(json.dumps(run_selftest(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
