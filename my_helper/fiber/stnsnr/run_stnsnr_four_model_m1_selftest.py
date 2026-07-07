#!/usr/bin/env python3
"""Pipeline entry point for four-model M1 shared-kernel self-tests."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    core_analysis_dir = repo_root / "my_helper" / "fiber" / "core" / "analysis"
    sys.path.insert(0, str(core_analysis_dir))

    from stnsnr_four_model_resolver_selftest import main as resolver_selftest_main
    from stnsnr_four_model_stats_selftest import main as stats_selftest_main

    stats_status = stats_selftest_main()
    resolver_status = resolver_selftest_main()
    return 0 if stats_status == 0 and resolver_status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
