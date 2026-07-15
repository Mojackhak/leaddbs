#!/usr/bin/env python3
"""Repository entrypoint for the generic dual-frequency workflow service."""

from __future__ import annotations

import sys
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.application.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
