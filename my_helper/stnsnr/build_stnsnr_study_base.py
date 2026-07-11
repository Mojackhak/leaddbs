#!/usr/bin/env python3
"""Build the STNSNr dual-frequency study-base JSON document."""

from __future__ import annotations

from pathlib import Path
import sys


FIBER_ROOT = Path(__file__).resolve().parents[1] / "fiber"
if str(FIBER_ROOT) not in sys.path:
    sys.path.insert(0, str(FIBER_ROOT))

from projects.stnsnr.importer.study_base import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
