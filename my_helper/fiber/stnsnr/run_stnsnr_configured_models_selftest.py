#!/usr/bin/env python3
"""Run the configured four-model core regression suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
TEST_ROOT = CORE_ROOT / "outcome_models" / "tests"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(TEST_ROOT), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
