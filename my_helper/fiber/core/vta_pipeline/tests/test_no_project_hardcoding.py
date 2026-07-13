from __future__ import annotations

import ast
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[5]
PYTHON_ROOT = REPO_ROOT / "my_helper" / "fiber" / "core" / "vta_pipeline"
MATLAB_ROOT = (
    REPO_ROOT / "my_helper" / "fiber" / "core" / "stimulation" / "model"
)

FORBIDDEN_EXACT_STRINGS = {
    "snr003",
    "stnsnr",
    "t1",
    "t2",
    "t3",
    "stn",
    "snr",
    "hf",
    "ulf",
    "chronic",
    "immediate",
}


def test_generic_python_control_flow_has_no_project_literals() -> None:
    violations: list[str] = []
    for path in sorted(PYTHON_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value.strip().lower() in FORBIDDEN_EXACT_STRINGS:
                violations.append(f"{path.name}:{node.lineno}:{node.value}")
    assert violations == []


def test_generic_matlab_has_no_project_named_environment_variable() -> None:
    pattern = re.compile(r"STNSNR_[A-Z0-9_]+")
    violations = [
        f"{path.name}:{match.group(0)}"
        for path in sorted(MATLAB_ROOT.rglob("*.m"))
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
    ]
    assert violations == []


def test_generic_matlab_control_flow_has_no_exact_project_literals() -> None:
    literals = "|".join(re.escape(item) for item in FORBIDDEN_EXACT_STRINGS)
    pattern = re.compile(rf"(['\"])(?:{literals})\1", re.IGNORECASE)
    violations = [
        f"{path.name}:{match.group(0)}"
        for path in sorted(MATLAB_ROOT.rglob("*.m"))
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
    ]
    assert violations == []
