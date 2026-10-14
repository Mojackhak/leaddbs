"""Keep Numba cache imports consistent between pytest and the public CLI."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_pytest_and_cli_share_the_canonical_traversal_cache(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[5]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["NUMBA_CACHE_DIR"] = str(tmp_path / "numba")
    environment["NUMBA_DEBUG_CACHE"] = "1"
    environment["MPLCONFIGDIR"] = str(tmp_path / "matplotlib")
    script = """
from pathlib import Path
import sys
import numpy as np

if sys.argv[1] == "pytest":
    sys.path.insert(0, str(Path.cwd() / "my_helper/fiber"))
    from core.mrtrix_seed_target import classification
else:
    from my_helper.fiber.core.mrtrix_seed_target import classification

from my_helper.fiber.core.seed_target_connectivity import traversal
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import resolved_mask

assert classification.optimized_membership is traversal.optimized_membership
assert classification.FiberChunk.__module__ == (
    "my_helper.fiber.core.seed_target_connectivity.models"
)
lookup = traversal.build_sparse_lookup([resolved_mask([(1, 1, 1)])])
streamlines = [np.asarray([[-1., 1., 1.], [3., 1., 1.]])]
assert classification.classify_streamlines(streamlines, lookup).tolist() == [[True]]
"""
    for mode in ("pytest", "cli"):
        result = subprocess.run(
            [sys.executable, "-c", script, mode],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        if mode == "cli":
            assert "[cache] data loaded from" in result.stdout
