#!/usr/bin/env python3
"""Pipeline entry point for STN/SNr dTOR normative-fiber formal bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "my_helper/fiber/core/analysis"))

from stnsnr_normative_fiber_formal_bootstrap import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
