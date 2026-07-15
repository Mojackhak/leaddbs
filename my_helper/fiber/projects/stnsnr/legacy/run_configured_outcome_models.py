#!/usr/bin/env python3
"""Run the configured endpoint-aware four-model workflow."""

from __future__ import annotations

import sys
from pathlib import Path


LEGACY_ROOT = Path(__file__).resolve().parent
ANALYSIS_ROOT = Path(__file__).resolve().parents[3] / "core" / "analysis"
for import_root in (ANALYSIS_ROOT, LEGACY_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from outcome_models.cli import main


if __name__ == "__main__":
    raise SystemExit(int(main()))
