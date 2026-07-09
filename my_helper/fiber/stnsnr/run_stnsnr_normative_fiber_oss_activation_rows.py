#!/usr/bin/env python3
"""Pipeline entry point for normative-fiber OSS activation rows."""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "my_helper/fiber/core/analysis"))

from stnsnr_normative_fiber_oss_activation_rows import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
