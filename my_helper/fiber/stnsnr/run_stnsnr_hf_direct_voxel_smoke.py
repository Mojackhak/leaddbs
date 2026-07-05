#!/usr/bin/env python3
"""Pipeline entry point for HF direct voxel observed smoke analysis."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    core_analysis_dir = repo_root / "my_helper" / "fiber" / "core" / "analysis"
    sys.path.insert(0, str(core_analysis_dir))

    from stnsnr_hf_direct_voxel_smoke import main as smoke_main

    return smoke_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
