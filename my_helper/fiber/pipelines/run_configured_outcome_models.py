#!/usr/bin/env python3
"""Run the configured endpoint-aware four-model workflow."""

from __future__ import annotations

import sys
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from outcome_models.cli import main


if __name__ == "__main__":
    raise SystemExit(int(main()))
