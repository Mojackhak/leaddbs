"""Import-isolation checks for the project-neutral runtime package."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[2]


class RuntimeImportIsolationTest(unittest.TestCase):
    def test_runtime_imports_and_constructs_with_project_namespaces_blocked(self) -> None:
        script = textwrap.dedent(
            """
            import importlib
            import importlib.abc
            import pkgutil
            import sys


            def is_blocked(fullname):
                parts = fullname.lower().split(".")
                if any(
                    part.startswith(("legacy_", "stnsnr_", "run_stnsnr_"))
                    for part in parts
                ):
                    return True
                normalized = fullname.lower()
                return normalized == "projects.stnsnr" or normalized.startswith(
                    ("projects.stnsnr.", "my_helper.fiber.projects.stnsnr")
                )


            class ProjectNamespaceBlocker(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if is_blocked(fullname):
                        raise ImportError(f"blocked project namespace import: {fullname}")
                    return None


            for module_name in tuple(sys.modules):
                if is_blocked(module_name):
                    del sys.modules[module_name]
            sys.meta_path.insert(0, ProjectNamespaceBlocker())

            package = importlib.import_module("dual_frequency")
            imported = []
            for module in pkgutil.walk_packages(
                package.__path__, package.__name__ + "."
            ):
                if ".tests." in module.name or module.name.endswith(".tests"):
                    continue
                importlib.import_module(module.name)
                imported.append(module.name)

            from dual_frequency.application import WorkflowService
            service = WorkflowService()
            registry = service._default_registry()
            assert registry.service_ids
            print(
                f"isolated_runtime_imports={len(imported)} "
                f"production_services={len(registry.service_ids)}"
            )
            """
        )
        environment = dict(os.environ)
        current_python_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(CORE_ROOT), current_python_path) if item
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertRegex(completed.stdout, r"isolated_runtime_imports=\d+")
        self.assertRegex(completed.stdout, r"production_services=\d+")
        self.assertNotIn("blocked project namespace import", completed.stderr)


if __name__ == "__main__":
    unittest.main()
