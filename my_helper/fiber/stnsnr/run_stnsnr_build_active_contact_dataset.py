#!/opt/anaconda3/envs/leaddbs/bin/python
"""Pipeline: build the 16-subject active-contact coordinate dataset."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_DIR = Path("/Users/mojackhu/Github/leaddbs")
CORE_SCRIPT = REPO_DIR / "my_helper/fiber/core/datasets/mh_fiber_build_active_contact_dataset.py"
EXPECTED_PYTHON = Path("/opt/anaconda3/envs/leaddbs/bin/python")

if Path(sys.executable).resolve() != EXPECTED_PYTHON.resolve():
    print(
        f"Warning: expected {EXPECTED_PYTHON}, running with {sys.executable}. "
        "Use /opt/anaconda3/envs/leaddbs/bin/python for reproducibility.",
        file=sys.stderr,
    )

spec = importlib.util.spec_from_file_location("mh_fiber_build_active_contact_dataset", CORE_SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

result = module.build_active_contact_dataset()
print("Active-contact dataset written:")
print(result["active_csv"])
print(result["info_json"])
print(
    f"contacts={result['active_contacts']} subjects={result['active_subjects']} "
    f"max_match_distance_mm={result['max_match_distance_mm']:.12g}"
)
print(f"region_counts={result['region_counts']}")
print(f"region_programming_counts={result['region_programming_counts']}")
