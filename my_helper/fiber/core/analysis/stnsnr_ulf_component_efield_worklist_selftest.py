#!/usr/bin/env python3
"""Self-tests for ULF component e-field worklist helpers."""

from __future__ import annotations

import json

from stnsnr_ulf_component_efield_worklist import build_missing_worklist_rows


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_missing_worklist_keeps_only_missing_counterfactual_rows() -> None:
    rows = [
        {
            "subject_id": "SNr003",
            "side": "L",
            "target": "SNr",
            "frequency_class": "HF",
            "path_mode": "observed_alternating_subprogram",
            "efield_exists": "True",
            "status": "PASS",
        },
        {
            "subject_id": "SNr011",
            "side": "L",
            "target": "SNr",
            "frequency_class": "ULF",
            "path_mode": "counterfactual_target_component_continuous_mixed",
            "efield_exists": "False",
            "status": "FAIL",
        },
        {
            "subject_id": "SNr011",
            "side": "L",
            "target": "STN",
            "frequency_class": "HF",
            "path_mode": "counterfactual_target_component_continuous_mixed",
            "efield_exists": "False",
            "status": "FAIL",
        },
    ]
    worklist = build_missing_worklist_rows(rows)
    assert_equal(len(worklist), 2, "missing worklist length")
    assert_equal(worklist[0]["worklist_index"], 1, "first worklist index")
    assert_equal(worklist[0]["subject_id"], "SNr011", "first subject")
    assert_equal(worklist[0]["generation_status"], "needs_counterfactual_target_component_efield", "generation status")
    assert_equal(worklist[1]["target"], "STN", "second target")


def main() -> int:
    test_missing_worklist_keeps_only_missing_counterfactual_rows()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
