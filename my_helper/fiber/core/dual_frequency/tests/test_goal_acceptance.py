"""Final structural and bounded acceptance guards for the generic runtime."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from dual_frequency.tests import test_activation_provider
from dual_frequency.tests import test_runtime_import_isolation
from dual_frequency.tests.test_runtime_dependency_boundary import (
    FORBIDDEN_RUNTIME_STRINGS,
    _is_project_import,
    _production_python_files,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
PIPELINE_ENTRYPOINT = (
    REPOSITORY_ROOT / "my_helper/fiber/pipelines/run_dual_frequency_models.py"
)
ACCEPTANCE_ROOT = (
    REPOSITORY_ROOT / "my_helper/fiber/projects/stnsnr/acceptance"
)
APPROVED_ALLOWLIST = ACCEPTANCE_ROOT / "approved_task_allowlist.json"
BOUNDED_COMPARATOR = ACCEPTANCE_ROOT / "compare_bounded_fixtures.py"

PROJECT_TEXT_PATTERNS = (
    re.compile(r"projects\.stnsnr"),
    re.compile(r"my_helper\.fiber\.projects\.stnsnr"),
    re.compile(r"legacy_"),
    re.compile(r"stnsnr_"),
    re.compile(r"run_stnsnr"),
    re.compile(r"frequency_1_reference"),
    re.compile(r"frequency_2_addon"),
    re.compile(r"/Volumes/VAL/STNSNr"),
    re.compile(r"/Users/mojackhu/Research/STNSNr"),
    re.compile(r"four_model_execution"),
    re.compile(r"\bHF\b"),
    re.compile(r"\bULF\b"),
    re.compile(r"\bSTN\b"),
    re.compile(r"\bSNr\b"),
    re.compile(r"\bdTOR\b"),
)
SUBJECT_COLLECTION_NAME = re.compile(
    r"(?:"
    r"^(?:subjects?|participants?)$"
    r"|"
    r"(?:subject|participant).*(?:allow|include|exclude|white|black|ids?|list)"
    r"|"
    r"(?:allow|include|exclude|white|black).*(?:subject|participant)"
    r")",
    re.IGNORECASE,
)
SUBJECT_IDENTIFIER = re.compile(
    r"(?:"
    r"(?:sub(?:ject)?|participant)[-_][A-Za-z0-9][A-Za-z0-9._-]*"
    r"|"
    r"[A-Za-z]{2,12}[0-9]{3,}"
    r")"
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"JSON root must be an object: {path}")
    return payload


def _fixture_manifest_path(allowlist: dict[str, object]) -> Path:
    source_run = allowlist.get("source_run")
    if not isinstance(source_run, dict):
        raise AssertionError("approved allowlist has no source_run object")
    run_id = source_run.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise AssertionError("approved allowlist has no source run ID")
    return ACCEPTANCE_ROOT / "frozen" / run_id / "bounded_fixture_manifest.json"


def _approved_tasks(
    allowlist: dict[str, object],
) -> dict[str, tuple[dict[str, object], dict[str, object]]]:
    scopes = allowlist.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise AssertionError("approved allowlist must contain scopes")
    result: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for scope in scopes:
        if not isinstance(scope, dict):
            raise AssertionError("approved allowlist scope must be an object")
        tasks = scope.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise AssertionError("approved allowlist scope must contain tasks")
        for task in tasks:
            if not isinstance(task, dict):
                raise AssertionError("approved allowlist task must be an object")
            task_id = task.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise AssertionError("approved allowlist task has no task ID")
            if task_id in result:
                raise AssertionError(f"duplicate approved task ID: {task_id}")
            result[task_id] = (scope, task)
    return result


def _production_files() -> tuple[Path, ...]:
    return (*_production_python_files(), PIPELINE_ENTRYPOINT)


def _target_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Attribute):
        return (target.attr,)
    if isinstance(target, (ast.Tuple, ast.List)):
        return tuple(name for item in target.elts for name in _target_names(item))
    return ()


def _literal_strings(node: ast.AST | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if isinstance(node, ast.Constant):
        return (node.value,) if isinstance(node.value, str) else ()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return tuple(value for item in node.elts for value in _literal_strings(item))
    if isinstance(node, ast.Dict):
        return tuple(
            value
            for item in (*node.keys, *node.values)
            for value in _literal_strings(item)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
        "frozenset",
        "list",
        "set",
        "tuple",
    }:
        return tuple(value for item in node.args for value in _literal_strings(item))
    return ()


def _literal_collection_strings(node: ast.AST | None) -> tuple[str, ...]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return _literal_strings(node)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
        "frozenset",
        "list",
        "set",
        "tuple",
    }:
        return _literal_strings(node)
    return ()


def _expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expression_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _subject_allowlist_violations(path: Path, source: str) -> tuple[str, ...]:
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []

    def record(node: ast.AST, names: tuple[str, ...], value: ast.AST | None) -> None:
        literals = _literal_collection_strings(value)
        if not literals:
            return
        semantic_name = any(SUBJECT_COLLECTION_NAME.search(name) for name in names)
        identifier_set = len(literals) >= 2 and all(
            SUBJECT_IDENTIFIER.fullmatch(item) for item in literals
        )
        if semantic_name or identifier_set:
            violations.append(
                f"{path}:{getattr(node, 'lineno', 0)}: literal subject collection "
                f"assigned to {', '.join(names) or '<unknown>'}"
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = tuple(
                name for target in node.targets for name in _target_names(target)
            )
            record(node, names, node.value)
        elif isinstance(node, ast.AnnAssign):
            record(node, _target_names(node.target), node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = (*node.args.posonlyargs, *node.args.args)
            for argument, default in zip(
                positional[-len(node.args.defaults) :],
                node.args.defaults,
            ):
                record(node, (argument.arg,), default)
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                record(node, (argument.arg,), default)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg is not None:
                    record(node, (keyword.arg,), keyword.value)

        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(operator, (ast.In, ast.NotIn)) for operator in node.ops):
            continue
        expression_name = _expression_name(node.left)
        if not re.search(r"subject|participant", expression_name, re.IGNORECASE):
            continue
        if any(_literal_collection_strings(item) for item in node.comparators):
            violations.append(
                f"{path}:{node.lineno}: subject membership uses a literal collection"
            )

    return tuple(violations)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compare_bounded_fixture(expected: Path, observed: Path) -> dict[str, object]:
    script = """
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("_bounded_fixture_comparator", sys.argv[1])
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load bounded fixture comparator")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.compare_fixture(Path(sys.argv[2]), Path(sys.argv[3]))
print(json.dumps({"passed": result.passed, "differences": list(result.differences)}))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(BOUNDED_COMPARATOR),
            str(expected),
            str(observed),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise AssertionError("bounded comparator returned a non-object result")
    return result


def _run_existing_case(case: unittest.TestCase) -> None:
    result = unittest.TestResult()
    case.run(result)
    if result.wasSuccessful():
        return
    details = [
        *(f"failure: {traceback}" for _, traceback in result.failures),
        *(f"error: {traceback}" for _, traceback in result.errors),
    ]
    raise AssertionError("\n".join(details))


class GoalAcceptanceTest(unittest.TestCase):
    """Close the static, bounded, and no-producer portions of Task 16."""

    def test_bounded_manifest_exactly_matches_reviewed_allowlist(self) -> None:
        allowlist = _load_json(APPROVED_ALLOWLIST)
        manifest = _load_json(_fixture_manifest_path(allowlist))
        approved = _approved_tasks(allowlist)
        eligible_rows = manifest.get("eligible_tasks")
        self.assertIsInstance(eligible_rows, list)
        eligible: dict[str, dict[str, object]] = {}
        for row in eligible_rows:
            self.assertIsInstance(row, dict)
            task_id = row.get("task_id")
            self.assertIsInstance(task_id, str)
            self.assertNotIn(task_id, eligible)
            eligible[task_id] = row

        self.assertEqual(set(eligible), set(approved))
        self.assertEqual(
            manifest.get("source_run_id"),
            allowlist["source_run"]["run_id"],  # type: ignore[index]
        )
        source_run = allowlist["source_run"]
        self.assertIsInstance(source_run, dict)
        source_identity = {
            "source_run_commit": "commit",
            "configuration_hash": "configuration_hash",
            "source_provenance_hash": "provenance_hash",
            "source_run_status": "status",
            "source_run_dirty": "dirty",
        }
        for manifest_field, allowlist_field in source_identity.items():
            self.assertEqual(
                manifest.get(manifest_field),
                source_run.get(allowlist_field),
                manifest_field,
            )
        self.assertEqual(manifest.get("allowlist_sha256"), _sha256(APPROVED_ALLOWLIST))
        for task_id, (scope, task) in approved.items():
            row = eligible[task_id]
            for field in (
                "execution_stage",
                "branch",
                "artifact_kind_conversions",
            ):
                self.assertEqual(row.get(field), task.get(field), f"{task_id}:{field}")
            for field in (
                "scope_id",
                "parent_scale_id",
                "model_family",
                "source_binding_role",
                "source_connectome_role",
                "target_connectome_roles",
            ):
                self.assertEqual(row.get(field), scope.get(field), f"{task_id}:{field}")
            self.assertEqual(row.get("status"), task.get("expected_status"))

        excluded = manifest.get("excluded_tasks")
        self.assertIsInstance(excluded, dict)
        self.assertTrue(excluded)
        self.assertTrue(set(eligible).isdisjoint(excluded))

    def test_bounded_comparison_rejects_excluded_task_expansion(self) -> None:
        allowlist = _load_json(APPROVED_ALLOWLIST)
        manifest_path = _fixture_manifest_path(allowlist)
        expanded = _load_json(manifest_path)
        eligible = expanded.get("eligible_tasks")
        excluded = expanded.get("excluded_tasks")
        self.assertIsInstance(eligible, list)
        self.assertIsInstance(excluded, dict)
        self.assertTrue(eligible)
        self.assertTrue(excluded)

        added_task_id = sorted(excluded)[0]
        added = dict(eligible[0])
        added["task_id"] = added_task_id
        eligible.append(added)
        with tempfile.TemporaryDirectory() as temporary_directory:
            expanded_path = Path(temporary_directory) / "expanded_manifest.json"
            expanded_path.write_text(
                json.dumps(expanded, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = _compare_bounded_fixture(manifest_path, expanded_path)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("task IDs differ" in item for item in result["differences"])
        )

    def test_missing_fixture_cannot_start_expensive_producer(self) -> None:
        _run_existing_case(
            test_activation_provider.OSSActivationProviderTest(
                "test_unauthorized_miss_fails_before_producer_invocation"
            )
        )

    def test_production_runtime_has_no_project_or_legacy_coupling(self) -> None:
        violations: list[str] = []
        for path in _production_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported = (node.module or "",)
                else:
                    continue
                for module_name in imported:
                    if _is_project_import(module_name):
                        violations.append(f"{path}:{node.lineno}: import {module_name}")
            normalized = source.lower()
            for forbidden in FORBIDDEN_RUNTIME_STRINGS:
                if forbidden in normalized:
                    violations.append(f"{path}: forbidden runtime string {forbidden!r}")
            for pattern in PROJECT_TEXT_PATTERNS:
                for match in pattern.finditer(source):
                    line = source.count("\n", 0, match.start()) + 1
                    violations.append(f"{path}:{line}: {match.group(0)!r}")

        self.assertEqual(violations, [])

    def test_production_runtime_has_no_literal_subject_allowlists(self) -> None:
        violations: list[str] = []
        for path in _production_files():
            violations.extend(
                _subject_allowlist_violations(path, path.read_text(encoding="utf-8"))
            )

        self.assertEqual(violations, [])

    def test_subject_allowlist_guard_rejects_literal_inclusion_rules(self) -> None:
        sample = """
SUBJECT_ALLOWLIST = ("candidate-a", "candidate-b")

def execute(subject_ids=("candidate-c", "candidate-d")):
    return subject_ids
"""
        violations = _subject_allowlist_violations(Path("synthetic.py"), sample)
        self.assertEqual(len(violations), 2)

    def test_runtime_import_isolation_contract_remains_executable(self) -> None:
        _run_existing_case(
            test_runtime_import_isolation.RuntimeImportIsolationTest(
                "test_runtime_imports_and_constructs_with_project_namespaces_blocked"
            )
        )

    def test_bounded_task_manifests_are_terminal_and_consistent(self) -> None:
        allowlist = _load_json(APPROVED_ALLOWLIST)
        manifest = _load_json(_fixture_manifest_path(allowlist))
        rows = manifest.get("eligible_tasks")
        self.assertIsInstance(rows, list)
        configuration_hash = manifest.get("configuration_hash")
        self.assertIsInstance(configuration_hash, str)
        sensitivity_tokens = ("sensitivity", "jitter", "oss")

        for row in rows:
            self.assertIsInstance(row, dict)
            task_id = row["task_id"]
            task_manifest_ref = row.get("task_manifest")
            self.assertIsInstance(task_manifest_ref, dict)
            task_manifest_path = Path(task_manifest_ref["path"])
            self.assertTrue(task_manifest_path.is_file(), task_manifest_path)
            self.assertEqual(task_manifest_path.stat().st_size, task_manifest_ref["size_bytes"])
            self.assertEqual(_sha256(task_manifest_path), task_manifest_ref["sha256"])

            relative_path = Path(task_manifest_ref["relative_path"])
            self.assertFalse(relative_path.is_absolute())
            self.assertNotIn("..", relative_path.parts)
            self.assertTrue(
                task_manifest_path.as_posix().endswith("/" + relative_path.as_posix())
            )

            task_manifest = _load_json(task_manifest_path)
            self.assertEqual(task_manifest.get("task_id"), task_id)
            self.assertEqual(task_manifest.get("status"), "completed")
            self.assertEqual(task_manifest.get("configuration_hash"), configuration_hash)
            task_spec = task_manifest.get("task")
            self.assertIsInstance(task_spec, dict)
            self.assertEqual(task_spec.get("task_id"), task_id)
            self.assertEqual(task_spec.get("execution_stage"), row.get("execution_stage"))

            stage = str(row.get("execution_stage", ""))
            if any(token in stage for token in sensitivity_tokens):
                self.assertNotIn("final_model_id", task_manifest)

            artifacts = row.get("artifacts")
            self.assertIsInstance(artifacts, list)
            for artifact in artifacts:
                self.assertIsInstance(artifact, dict)
                artifact_path = Path(artifact["path"])
                self.assertTrue(artifact_path.is_file(), artifact_path)
                self.assertEqual(artifact_path.stat().st_size, artifact["size_bytes"])
                self.assertEqual(_sha256(artifact_path), artifact["sha256"])
                artifact_relative_path = Path(artifact["relative_path"])
                self.assertFalse(artifact_relative_path.is_absolute())
                self.assertNotIn("..", artifact_relative_path.parts)
                self.assertTrue(
                    artifact_path.as_posix().endswith(
                        "/" + artifact_relative_path.as_posix()
                    )
                )


if __name__ == "__main__":
    unittest.main()
