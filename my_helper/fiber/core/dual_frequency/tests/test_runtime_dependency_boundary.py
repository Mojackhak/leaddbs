"""Static dependency boundaries for generic production runtime modules."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PACKAGE_ROOT / "backends"

PROJECT_IMPORT_PREFIXES = (
    "projects.stnsnr",
    "my_helper.fiber.projects.stnsnr",
)
PROJECT_IMPORT_COMPONENT_PREFIXES = (
    "legacy_",
    "stnsnr_",
    "run_stnsnr_",
)
FORBIDDEN_RUNTIME_STRINGS = (
    "/volumes/val/stnsnr",
    "/users/mojackhu/github/leaddbs",
    "summary/spot",
    "run_configured_outcome_models",
    "peak_efield_tau800_primary",
    "ulf_peak_efield_tau800",
)


def _production_python_files(root: Path = PACKAGE_ROOT) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob("*.py"))
        if "tests" not in path.relative_to(root).parts
        and "__pycache__" not in path.parts
    )


def _is_project_import(module_name: str) -> bool:
    normalized = module_name.lower().lstrip(".")
    if any(
        normalized == prefix or normalized.startswith(prefix + ".")
        for prefix in PROJECT_IMPORT_PREFIXES
    ):
        return True
    return any(
        component.startswith(PROJECT_IMPORT_COMPONENT_PREFIXES)
        for component in normalized.split(".")
    )


def _annotation_contains_path(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    return any(
        (isinstance(node, ast.Name) and node.id == "Path")
        or (isinstance(node, ast.Attribute) and node.attr == "Path")
        for node in ast.walk(annotation)
    )


class RuntimeDependencyBoundaryTest(unittest.TestCase):
    def test_production_modules_do_not_import_project_namespaces(self) -> None:
        violations: list[str] = []
        for path in _production_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names = (node.module or "",)
                else:
                    continue
                for name in names:
                    if _is_project_import(name):
                        violations.append(f"{path}:{node.lineno}: {name}")
        self.assertEqual(violations, [])

    def test_production_modules_do_not_embed_project_paths_or_legacy_names(self) -> None:
        violations: list[str] = []
        for path in _production_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                normalized = node.value.lower()
                for forbidden in FORBIDDEN_RUNTIME_STRINGS:
                    if forbidden in normalized:
                        violations.append(f"{path}:{node.lineno}: {forbidden}")
        self.assertEqual(violations, [])

    def test_public_scientific_backend_signatures_do_not_accept_raw_paths(self) -> None:
        violations: list[str] = []
        for path in _production_python_files(BACKEND_ROOT):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("_"):
                    continue
                arguments = (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                for argument in arguments:
                    if _annotation_contains_path(argument.annotation):
                        violations.append(
                            f"{path}:{node.lineno}: {node.name}({argument.arg}: Path)"
                        )
                if _annotation_contains_path(node.returns):
                    violations.append(f"{path}:{node.lineno}: {node.name} -> Path")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
