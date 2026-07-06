#!/usr/bin/env python3
"""Pipeline entry point for observed-only ULF normative fiber analysis."""

from __future__ import annotations

import sys
from pathlib import Path


STNSNR_DEFAULTS = {
    "--asset-root": "/Users/mojackhu/Github/leaddbs",
    "--clinical-root": "/Users/mojackhu/Research/STNSNr/summary/cohort/subj",
    "--readiness-root": "/Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_readiness",
    "--gate-status": "/Volumes/VAL/STNSNr/summary/four_model_execution/gate_status/four_model_gate_status.csv",
    "--output-root": "/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf",
    "--hf-output-root": "/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf",
    "--matlab-bin": "/Applications/MATLAB_R2024b.app/bin/matlab",
    "--post-scale": "MDS-UPDRS III score (STN+SNr, 3 m)",
    "--connectome": "ppmi",
}


def with_stnsnr_defaults(argv: list[str], repo_root: Path) -> list[str]:
    args = ["--repo-root", str(repo_root)]
    existing_flags = {item for item in argv if item.startswith("--")}
    for flag, value in STNSNR_DEFAULTS.items():
        if flag not in existing_flags:
            args.extend([flag, value])
    args.extend(argv)
    return args


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    core_analysis_dir = repo_root / "my_helper" / "fiber" / "core" / "analysis"
    sys.path.insert(0, str(core_analysis_dir))

    from stnsnr_ulf_normative_fiber_observed import main as observed_main

    return observed_main(with_stnsnr_defaults(sys.argv[1:], repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
