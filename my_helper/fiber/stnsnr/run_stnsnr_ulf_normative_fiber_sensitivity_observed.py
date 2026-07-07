#!/usr/bin/env python3
"""Pipeline entry point for D normative-fiber sensitivity outputs."""

from __future__ import annotations

import sys
from pathlib import Path


STNSNR_DEFAULTS = {
    "--output-root": "/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf",
    "--post-scale": "MDS-UPDRS III score (STN+SNr, 3 m)",
    "--hf-reference-scale": "MDS-UPDRS III score (STN, 3 m)",
    "--connectomes": "ppmi,dtor",
}


def with_stnsnr_defaults(argv: list[str], repo_root: Path) -> list[str]:
    args: list[str] = []
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

    from stnsnr_ulf_normative_fiber_sensitivity_observed import main as sensitivity_main

    return sensitivity_main(with_stnsnr_defaults(sys.argv[1:], repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
