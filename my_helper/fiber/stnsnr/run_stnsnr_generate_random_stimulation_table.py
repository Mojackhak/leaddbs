#!/opt/anaconda3/envs/leaddbs/bin/python
"""Pipeline: generate a random test stimulation table for STN/SNr active contacts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_DIR = Path("/Users/mojackhu/Github/leaddbs")
CORE_SCRIPT = REPO_DIR / "my_helper/fiber/core/datasets/mh_fiber_generate_random_stimulation_table.py"
EXPECTED_PYTHON = Path("/opt/anaconda3/envs/leaddbs/bin/python")

if Path(sys.executable).resolve() != EXPECTED_PYTHON.resolve():
    print(
        f"Warning: expected {EXPECTED_PYTHON}, running with {sys.executable}. "
        "Use /opt/anaconda3/envs/leaddbs/bin/python for reproducibility.",
        file=sys.stderr,
    )

spec = importlib.util.spec_from_file_location("mh_fiber_generate_random_stimulation_table", CORE_SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

result = module.generate_random_stimulation_table()
print("Random test stimulation table written:")
print(result["stimulation_csv"])
print(result["info_json"])
print(
    f"rows={result['rows']} subjects={result['subjects']} "
    f"random_seed={result['random_seed']}"
)
print(f"frequency_group_counts={result['frequency_group_counts']}")
print(f"region_counts={result['region_counts']}")
print(f"voltage_range_V={result['voltage_range_V']}")
print(f"pulse_width_range_us={result['pulse_width_range_us']}")
print(f"frequency_range_Hz={result['frequency_range_Hz']}")
