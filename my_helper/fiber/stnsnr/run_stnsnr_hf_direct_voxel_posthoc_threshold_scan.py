#!/usr/bin/env python3
"""Pipeline entry point for the HF direct voxel post-hoc threshold scan."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    core_analysis_dir = repo_root / "my_helper" / "fiber" / "core" / "analysis"
    sys.path.insert(0, str(core_analysis_dir))

    from stnsnr_hf_direct_voxel_posthoc_threshold_scan import main as scan_main

    return scan_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
