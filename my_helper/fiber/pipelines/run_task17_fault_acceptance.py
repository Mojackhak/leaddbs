#!/usr/bin/env python3
"""Run Task 17 corruption, recovery, and rebuild cases in an isolated root."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


_SCHEMA = "dual_frequency_task17_fault_plan_v1"
_MARKER_SCHEMA = "dual_frequency_task17_fault_root_v1"
_REPORT_SCHEMA = "dual_frequency_task17_fault_acceptance_v1"


class FaultAcceptanceError(RuntimeError):
    """Raised when an isolated fault case is unsafe or fails its contract."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _sha(value: object, label: str) -> str:
    token = str(value).strip().lower()
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise FaultAcceptanceError(f"{label} must be a SHA-256 digest")
    return token


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FaultAcceptanceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise FaultAcceptanceError(f"{label} must contain an object")
    return value


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise FaultAcceptanceError(f"{label} fields differ from the schema")


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    text = json.dumps(
        dict(value),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _relative(value: object, label: str) -> Path:
    path = Path(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise FaultAcceptanceError(f"{label} must be a contained relative path")
    return path


def _path_under(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.expanduser().resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _load_plan(path: Path) -> tuple[dict[str, Any], str]:
    plan = _read_json(path, "fault plan")
    required = {
        "schema_version",
        "plan_id",
        "accepted_parent_root",
        "canonical_publication_roots",
        "shared_production_cache_root",
        "readonly_closure",
        "copied_artifacts",
        "conda_environment",
        "working_directory",
        "corruption_cases",
        "fail_once_case",
        "rebuild_case",
        "cache_replay_case",
    }
    if set(plan) != required or plan["schema_version"] != _SCHEMA:
        raise FaultAcceptanceError("fault plan fields or schema differ")
    if not isinstance(plan["plan_id"], str) or not plan["plan_id"]:
        raise FaultAcceptanceError("fault plan ID must be nonempty")
    if (
        not isinstance(plan["conda_environment"], str)
        or not plan["conda_environment"]
    ):
        raise FaultAcceptanceError("Conda environment must be nonempty")
    return plan, _sha256_file(path)


def _readonly_roots(plan: Mapping[str, object]) -> tuple[Path, ...]:
    parent = Path(str(plan["accepted_parent_root"])).expanduser().resolve()
    cache = Path(str(plan["shared_production_cache_root"])).expanduser().resolve()
    publications = plan["canonical_publication_roots"]
    if not isinstance(publications, list) or not publications:
        raise FaultAcceptanceError("canonical publication roots must be nonempty")
    roots = (parent, cache, *(Path(str(item)).expanduser().resolve() for item in publications))
    if any(not root.exists() for root in roots):
        raise FaultAcceptanceError("one or more read-only roots do not exist")
    parent_manifest = _read_json(parent / "run_manifest.json", "accepted parent manifest")
    if (
        not isinstance(parent_manifest.get("run_id"), str)
        or not parent_manifest["run_id"]
        or parent_manifest.get("final_status") != "completed"
    ):
        raise FaultAcceptanceError("accepted parent is not a completed run")
    return roots


def _validate_acceptance_root(root: Path, readonly_roots: Sequence[Path]) -> Path:
    resolved = root.expanduser().resolve()
    if _path_under(resolved, readonly_roots) or any(
        resolved in readonly.parents for readonly in readonly_roots
    ):
        raise FaultAcceptanceError(
            "acceptance root must be disjoint from read-only roots"
        )
    if resolved.exists() and resolved.is_symlink():
        raise FaultAcceptanceError("acceptance root cannot be a symlink")
    return resolved


def _readonly_snapshot(
    plan: Mapping[str, object],
    roots: Sequence[Path],
) -> list[dict[str, str]]:
    closure = plan["readonly_closure"]
    if not isinstance(closure, list) or not closure:
        raise FaultAcceptanceError("read-only closure must be nonempty")
    results: list[dict[str, str]] = []
    seen: set[Path] = set()
    for item in closure:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise FaultAcceptanceError("read-only closure row fields differ")
        path = Path(str(item["path"])).expanduser().resolve()
        if path in seen or not _path_under(path, roots) or not path.is_file():
            raise FaultAcceptanceError("read-only closure path is invalid")
        expected = _sha(item["sha256"], "read-only closure SHA")
        if _sha256_file(path) != expected:
            raise FaultAcceptanceError(f"read-only closure SHA differs: {path}")
        seen.add(path)
        results.append({"path": str(path), "sha256": expected})
    publication_roots = (roots[0], *roots[2:])
    required_files = {
        path.resolve()
        for root in publication_roots
        for path in root.rglob("*")
        if path.is_file()
        and not path.name.startswith("._")
        and path.name != ".DS_Store"
    }
    declared_files = {
        Path(item["path"]).resolve()
        for item in results
        if _path_under(Path(item["path"]), publication_roots)
    }
    if declared_files != required_files:
        raise FaultAcceptanceError(
            "read-only closure does not enumerate the complete parent/publication trees"
        )
    return results


def initialize(
    plan_path: Path,
    acceptance_root: Path,
) -> dict[str, object]:
    """Create and verify one marker-bound isolated acceptance root."""

    plan, plan_sha = _load_plan(plan_path.expanduser().resolve())
    readonly_roots = _readonly_roots(plan)
    root = _validate_acceptance_root(acceptance_root, readonly_roots)
    marker_path = root / ".task17_fault_acceptance_root.json"
    if root.exists() and not marker_path.is_file():
        if any(root.iterdir()):
            raise FaultAcceptanceError(
                "existing nonempty acceptance root lacks the harness marker"
            )
    root.mkdir(parents=True, exist_ok=True)
    snapshot = _readonly_snapshot(plan, readonly_roots)
    copied = plan["copied_artifacts"]
    if not isinstance(copied, list) or not copied:
        raise FaultAcceptanceError("copied artifact closure must be nonempty")
    copied_results: list[dict[str, str]] = []
    for item in copied:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"source_path", "relative_path", "sha256"}
        ):
            raise FaultAcceptanceError("copied artifact row fields differ")
        source = Path(str(item["source_path"])).expanduser().resolve()
        relative = _relative(item["relative_path"], "copied artifact path")
        destination = (root / "inputs" / relative).resolve()
        expected = _sha(item["sha256"], "copied artifact SHA")
        if (
            not _path_under(source, readonly_roots)
            or not source.is_file()
            or _sha256_file(source) != expected
            or root not in destination.parents
        ):
            raise FaultAcceptanceError("copied artifact source or identity differs")
        if destination.exists():
            if _sha256_file(destination) != expected:
                raise FaultAcceptanceError(
                    f"existing isolated copy differs: {destination}"
                )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if _sha256_file(destination) != expected:
                raise FaultAcceptanceError("isolated copy verification failed")
        copied_results.append(
            {
                "relative_path": str(relative),
                "sha256": expected,
            }
        )
    marker = {
        "schema_version": _MARKER_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha,
        "readonly_snapshot": snapshot,
        "copied_artifacts": copied_results,
    }
    if marker_path.exists() and _read_json(marker_path, "acceptance marker") != marker:
        raise FaultAcceptanceError("acceptance marker differs from the fault plan")
    _atomic_json(marker_path, marker)
    return marker


def _verify_marker(
    plan: Mapping[str, object],
    plan_sha: str,
    root: Path,
    readonly_roots: Sequence[Path],
) -> dict[str, Any]:
    marker = _read_json(root / ".task17_fault_acceptance_root.json", "acceptance marker")
    if (
        marker.get("schema_version") != _MARKER_SCHEMA
        or marker.get("plan_id") != plan["plan_id"]
        or marker.get("plan_sha256") != plan_sha
    ):
        raise FaultAcceptanceError("acceptance marker identity differs")
    if marker.get("readonly_snapshot") != _readonly_snapshot(plan, readonly_roots):
        raise FaultAcceptanceError("read-only closure changed")
    for item in marker.get("copied_artifacts", ()):
        path = root / "inputs" / _relative(item["relative_path"], "marker copy path")
        if not path.is_file() or _sha256_file(path) != item["sha256"]:
            raise FaultAcceptanceError("isolated copied artifact changed")
    return marker


def _expand_command(raw: object, root: Path) -> tuple[str, ...]:
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(item, str) or not item for item in raw)
    ):
        raise FaultAcceptanceError("fault command must be a nonempty argument array")
    return tuple(item.replace("{acceptance_root}", str(root)) for item in raw)


def _run_command(
    command: Sequence[str],
    *,
    environment: str,
    working_directory: Path,
    allowed_argument_roots: Sequence[Path],
    log_root: Path,
    label: str,
) -> dict[str, object]:
    for argument in command:
        candidate = argument.split("=", 1)[-1] if "=" in argument else argument
        if candidate.startswith("/"):
            path = Path(candidate).expanduser().resolve()
            if not _path_under(path, allowed_argument_roots):
                raise FaultAcceptanceError(
                    f"command absolute path escapes allowed roots: {path}"
                )
    log_root.mkdir(parents=True, exist_ok=True)
    invocation = (
        "conda",
        "run",
        "--no-capture-output",
        "-n",
        environment,
        *command,
    )
    result = subprocess.run(
        invocation,
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = log_root / f"{label}.stdout.txt"
    stderr = log_root / f"{label}.stderr.txt"
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    return {
        "command": list(command),
        "exit_code": result.returncode,
        "stdout_sha256": _sha256_file(stdout),
        "stderr_sha256": _sha256_file(stderr),
        "combined_output": result.stdout + result.stderr,
    }


def _expect_failure(
    result: Mapping[str, object],
    expected_exit_code: object,
    expected_text: object,
) -> None:
    if type(expected_exit_code) is not int or expected_exit_code < 1:
        raise FaultAcceptanceError("expected failure exit code must be positive")
    if result["exit_code"] != expected_exit_code:
        raise FaultAcceptanceError("fault command exit code differs")
    text = str(expected_text)
    if not text or text not in str(result["combined_output"]):
        raise FaultAcceptanceError("fault command rejection text differs")


def _attempt_root(case_root: Path) -> Path:
    attempts = tuple(
        int(path.name.removeprefix("attempt_"))
        for path in case_root.glob("attempt_*")
        if path.is_dir() and path.name.removeprefix("attempt_").isdigit()
    )
    attempt = case_root / f"attempt_{max(attempts, default=0) + 1:04d}"
    attempt.mkdir(parents=True)
    return attempt


def _attempt_inventory(case_root: Path) -> list[dict[str, str]]:
    paths = tuple(
        path
        for attempt in sorted(case_root.glob("attempt_*"))
        if attempt.is_dir()
        for path in sorted(attempt.rglob("*"))
        if path.is_file()
    )
    return [
        {
            "relative_path": str(path.relative_to(case_root)),
            "sha256": _sha256_file(path),
        }
        for path in paths
    ]


def _reuse_case(terminal: Path, label: str) -> dict[str, Any]:
    result = _read_json(terminal, label)
    expected = result.get("attempt_inventory")
    if not isinstance(expected, list) or expected != _attempt_inventory(terminal.parent):
        raise FaultAcceptanceError(f"{label} attempt inventory differs")
    if result.get("status") != "validated":
        raise FaultAcceptanceError(f"{label} is not validated")
    return result


def _withhold(path: Path, quarantine: Path) -> None:
    if not path.is_file():
        raise FaultAcceptanceError(f"isolated fault target is missing: {path}")
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    if quarantine.exists():
        raise FaultAcceptanceError("quarantine target already exists")
    os.replace(path, quarantine)


def _restore(path: Path, quarantine: Path, observed: Path | None = None) -> None:
    if path.exists():
        if observed is None:
            raise FaultAcceptanceError("fault target exists before restoration")
        observed.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, observed)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(quarantine, path)


def _run_corruption_cases(
    plan: Mapping[str, object],
    root: Path,
    environment: str,
    working_directory: Path,
    readonly_roots: Sequence[Path],
) -> list[dict[str, object]]:
    cases = plan["corruption_cases"]
    if not isinstance(cases, list) or {item.get("kind") for item in cases if isinstance(item, Mapping)} != {"payload", "shard", "axis"}:
        raise FaultAcceptanceError("corruption cases must cover payload, shard, and axis")
    results: list[dict[str, object]] = []
    for raw in cases:
        if not isinstance(raw, Mapping):
            raise FaultAcceptanceError("corruption case must be an object")
        _exact_keys(
            raw,
            {
                "id",
                "kind",
                "relative_path",
                "command",
                "expected_exit_code",
                "expected_error_substring",
            },
            "corruption case",
        )
        case_id = str(raw.get("id", ""))
        if not case_id:
            raise FaultAcceptanceError("corruption case ID must be nonempty")
        terminal = root / "cases" / case_id / "result.json"
        if terminal.exists():
            results.append(_reuse_case(terminal, f"case {case_id}"))
            continue
        attempt = _attempt_root(terminal.parent)
        target = root / "inputs" / _relative(raw["relative_path"], "corruption path")
        original_sha = _sha256_file(target)
        quarantine = attempt / "quarantine" / "original"
        _withhold(target, quarantine)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                quarantine.read_bytes()
                + f"\nTASK17_{raw['kind']}_CORRUPTION\n".encode("ascii")
            )
            command_result = _run_command(
                _expand_command(raw["command"], root),
                environment=environment,
                working_directory=working_directory,
                allowed_argument_roots=(root, working_directory, *readonly_roots),
                log_root=attempt / "logs",
                label="reject",
            )
            _expect_failure(
                command_result,
                raw["expected_exit_code"],
                raw["expected_error_substring"],
            )
        finally:
            _restore(
                target,
                quarantine,
                attempt / "quarantine" / "corrupted_observed",
            )
        if _sha256_file(target) != original_sha:
            raise FaultAcceptanceError("corruption case did not restore its input")
        result = {
            "case_id": case_id,
            "kind": raw["kind"],
            "status": "validated",
            "original_sha256": original_sha,
            "command_exit_code": command_result["exit_code"],
            "stdout_sha256": command_result["stdout_sha256"],
            "stderr_sha256": command_result["stderr_sha256"],
            "attempt_inventory": _attempt_inventory(terminal.parent),
        }
        _atomic_json(terminal, result)
        results.append(result)
    return results


def _task_status(root: Path, relative: object, expected: str) -> str:
    path = root / _relative(relative, "task-state path")
    document = _read_json(path, "task state")
    if document.get("status") != expected:
        raise FaultAcceptanceError(f"task state is not {expected}: {path}")
    return _sha256_file(path)


def _run_fail_once(
    raw: object,
    root: Path,
    environment: str,
    working_directory: Path,
    readonly_roots: Sequence[Path],
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise FaultAcceptanceError("fail-once case must be an object")
    _exact_keys(
        raw,
        {
            "id",
            "withheld_relative_path",
            "first_command",
            "resume_command",
            "expected_exit_code",
            "expected_error_substring",
            "failed_task_state",
            "descendant_task_states",
            "protected_artifacts",
        },
        "fail-once case",
    )
    case_id = str(raw.get("id", ""))
    terminal = root / "cases" / case_id / "result.json"
    if terminal.exists():
        return _reuse_case(terminal, "fail-once result")
    attempt = _attempt_root(terminal.parent)
    target = root / "inputs" / _relative(raw["withheld_relative_path"], "fail-once path")
    quarantine = attempt / "quarantine" / "withheld"
    protected = raw["protected_artifacts"]
    if not isinstance(protected, list):
        raise FaultAcceptanceError("protected artifacts must be an array")
    protected_before = {
        str(item["relative_path"]): _sha(item["sha256"], "protected artifact SHA")
        for item in protected
    }
    for relative, expected in protected_before.items():
        if _sha256_file(
            root / _relative(relative, "protected artifact path")
        ) != expected:
            raise FaultAcceptanceError("protected artifact SHA differs before failure")
    _withhold(target, quarantine)
    try:
        first = _run_command(
            _expand_command(raw["first_command"], root),
            environment=environment,
            working_directory=working_directory,
            allowed_argument_roots=(root, working_directory, *readonly_roots),
            log_root=attempt / "logs",
            label="first",
        )
        _expect_failure(first, raw["expected_exit_code"], raw["expected_error_substring"])
        failed_sha = _task_status(root, raw["failed_task_state"], "failed")
        skipped = [
            _task_status(root, relative, "skipped")
            for relative in raw["descendant_task_states"]
        ]
    finally:
        _restore(target, quarantine)
    resume = _run_command(
        _expand_command(raw["resume_command"], root),
        environment=environment,
        working_directory=working_directory,
        allowed_argument_roots=(root, working_directory, *readonly_roots),
        log_root=attempt / "logs",
        label="resume",
    )
    if resume["exit_code"] != 0:
        raise FaultAcceptanceError("fail-once resume did not complete")
    completed_sha = _task_status(root, raw["failed_task_state"], "completed")
    descendant_completed = [
        _task_status(root, relative, "completed")
        for relative in raw["descendant_task_states"]
    ]
    protected_after = {
        relative: _sha256_file(root / _relative(relative, "protected artifact path"))
        for relative in protected_before
    }
    if protected_after != protected_before:
        raise FaultAcceptanceError("pre-failure scientific artifacts changed")
    result = {
        "case_id": case_id,
        "status": "validated",
        "first_exit_code": first["exit_code"],
        "resume_exit_code": resume["exit_code"],
        "failed_task_sha256": failed_sha,
        "completed_task_sha256": completed_sha,
        "skipped_descendant_sha256": skipped,
        "completed_descendant_sha256": descendant_completed,
        "protected_artifacts": protected_after,
        "attempt_inventory": _attempt_inventory(terminal.parent),
    }
    _atomic_json(terminal, result)
    return result


def _compare_outputs(
    root: Path,
    comparisons: object,
    readonly_roots: Sequence[Path],
) -> list[dict[str, object]]:
    if not isinstance(comparisons, list) or not comparisons:
        raise FaultAcceptanceError("one-shot comparisons must be nonempty")
    results: list[dict[str, object]] = []
    for item in comparisons:
        if not isinstance(item, Mapping):
            raise FaultAcceptanceError("one-shot comparison must be an object")
        _exact_keys(
            item,
            {
                "rebuilt_relative_path",
                "one_shot_path",
                "kind",
                "atol",
                "rtol",
            },
            "one-shot comparison",
        )
        rebuilt = root / _relative(item["rebuilt_relative_path"], "rebuilt output")
        one_shot = Path(str(item["one_shot_path"])).expanduser().resolve()
        if not _path_under(one_shot, readonly_roots) or not one_shot.is_file():
            raise FaultAcceptanceError("one-shot comparison source is not read-only")
        kind = item["kind"]
        if kind == "exact":
            passed = rebuilt.read_bytes() == one_shot.read_bytes()
            difference = 0.0 if passed else math.inf
        elif kind == "npy":
            rebuilt_values = np.load(rebuilt, allow_pickle=False)
            one_shot_values = np.load(one_shot, allow_pickle=False)
            atol = float(item["atol"])
            rtol = float(item["rtol"])
            passed = (
                rebuilt_values.shape == one_shot_values.shape
                and np.allclose(
                    rebuilt_values,
                    one_shot_values,
                    atol=atol,
                    rtol=rtol,
                    equal_nan=True,
                )
            )
            delta = np.abs(rebuilt_values - one_shot_values)
            finite = delta[np.isfinite(delta)]
            difference = 0.0 if finite.size < 1 else float(np.max(finite))
        else:
            raise FaultAcceptanceError("comparison kind must be exact or npy")
        if not passed:
            raise FaultAcceptanceError("rebuilt output differs from one-shot output")
        results.append(
            {
                "rebuilt_relative_path": str(item["rebuilt_relative_path"]),
                "one_shot_sha256": _sha256_file(one_shot),
                "rebuilt_sha256": _sha256_file(rebuilt),
                "kind": kind,
                "maximum_absolute_difference": difference,
            }
        )
    return results


def _run_rebuild(
    raw: object,
    root: Path,
    environment: str,
    working_directory: Path,
    command_readonly_roots: Sequence[Path],
    comparison_readonly_roots: Sequence[Path],
    accepted_parent_run_id: str,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise FaultAcceptanceError("rebuild case must be an object")
    _exact_keys(
        raw,
        {
            "id",
            "required_artifact_relative_path",
            "plain_extension_command",
            "expected_exit_code",
            "expected_error_substring",
            "rebuild_command",
            "rebuilt_run_relative_path",
            "rebuilt_run_id",
            "extension_command",
            "one_shot_comparisons",
        },
        "rebuild case",
    )
    case_id = str(raw.get("id", ""))
    terminal = root / "cases" / case_id / "result.json"
    if terminal.exists():
        return _reuse_case(terminal, "rebuild result")
    attempt = _attempt_root(terminal.parent)
    target = root / "inputs" / _relative(raw["required_artifact_relative_path"], "required artifact")
    quarantine = attempt / "quarantine" / "withheld"
    _withhold(target, quarantine)
    try:
        plain = _run_command(
            _expand_command(raw["plain_extension_command"], root),
            environment=environment,
            working_directory=working_directory,
            allowed_argument_roots=(
                root,
                working_directory,
                *command_readonly_roots,
            ),
            log_root=attempt / "logs",
            label="plain",
        )
        _expect_failure(plain, raw["expected_exit_code"], raw["expected_error_substring"])
        rebuilt = _run_command(
            _expand_command(raw["rebuild_command"], root),
            environment=environment,
            working_directory=working_directory,
            allowed_argument_roots=(
                root,
                working_directory,
                *command_readonly_roots,
            ),
            log_root=attempt / "logs",
            label="rebuild",
        )
        if rebuilt["exit_code"] != 0:
            raise FaultAcceptanceError("rebuild command did not complete")
        rebuilt_root = root / _relative(raw["rebuilt_run_relative_path"], "rebuilt run")
        rebuilt_manifest = _read_json(rebuilt_root / "run_manifest.json", "rebuilt manifest")
        if (
            rebuilt_manifest.get("run_id") != raw["rebuilt_run_id"]
            or rebuilt_manifest.get("final_status") != "completed"
            or rebuilt_manifest.get("run_id")
            == accepted_parent_run_id
        ):
            raise FaultAcceptanceError("rebuilt main lineage identity differs")
        extension = _run_command(
            _expand_command(raw["extension_command"], root),
            environment=environment,
            working_directory=working_directory,
            allowed_argument_roots=(
                root,
                working_directory,
                *command_readonly_roots,
            ),
            log_root=attempt / "logs",
            label="extension",
        )
        if extension["exit_code"] != 0:
            raise FaultAcceptanceError("rebuilt extension did not complete")
        comparisons = _compare_outputs(
            root,
            raw["one_shot_comparisons"],
            comparison_readonly_roots,
        )
    finally:
        _restore(target, quarantine)
    result = {
        "case_id": case_id,
        "status": "validated",
        "plain_exit_code": plain["exit_code"],
        "rebuild_exit_code": rebuilt["exit_code"],
        "extension_exit_code": extension["exit_code"],
        "rebuilt_run_id": raw["rebuilt_run_id"],
        "rebuilt_manifest_sha256": _sha256_file(rebuilt_root / "run_manifest.json"),
        "comparisons": comparisons,
        "attempt_inventory": _attempt_inventory(terminal.parent),
    }
    _atomic_json(terminal, result)
    return result


def _run_cache_replay(
    raw: object,
    root: Path,
    environment: str,
    working_directory: Path,
    readonly_roots: Sequence[Path],
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise FaultAcceptanceError("cache replay case must be an object")
    _exact_keys(
        raw,
        {
            "id",
            "command",
            "forbidden_argument",
            "expected_outputs",
        },
        "cache replay case",
    )
    case_id = str(raw.get("id", ""))
    terminal = root / "cases" / case_id / "result.json"
    if terminal.exists():
        return _reuse_case(terminal, "cache replay result")
    attempt = _attempt_root(terminal.parent)
    command = _expand_command(raw["command"], root)
    forbidden = str(raw["forbidden_argument"])
    if forbidden in command:
        raise FaultAcceptanceError("cache replay command contains forbidden authorization")
    execution = _run_command(
        command,
        environment=environment,
        working_directory=working_directory,
        allowed_argument_roots=(root, working_directory, *readonly_roots),
        log_root=attempt / "logs",
        label="cache_replay",
    )
    if execution["exit_code"] != 0:
        raise FaultAcceptanceError("copied-cache replay did not complete")
    outputs: list[dict[str, str]] = []
    for item in raw["expected_outputs"]:
        path = root / _relative(item["relative_path"], "cache replay output")
        expected = _sha(item["sha256"], "cache replay output SHA")
        if _sha256_file(path) != expected:
            raise FaultAcceptanceError("cache replay output SHA differs")
        outputs.append({"relative_path": str(item["relative_path"]), "sha256": expected})
    result = {
        "case_id": case_id,
        "status": "validated",
        "exit_code": execution["exit_code"],
        "outputs": outputs,
        "attempt_inventory": _attempt_inventory(terminal.parent),
    }
    _atomic_json(terminal, result)
    return result


def run(plan_path: Path, acceptance_root: Path) -> dict[str, object]:
    """Execute or reuse every isolated fault case and validate read-only roots."""

    plan, plan_sha = _load_plan(plan_path.expanduser().resolve())
    readonly_roots = _readonly_roots(plan)
    command_readonly_roots: tuple[Path, ...] = ()
    root = _validate_acceptance_root(acceptance_root, readonly_roots)
    marker = _verify_marker(plan, plan_sha, root, readonly_roots)
    environment = str(plan["conda_environment"])
    working_directory = Path(str(plan["working_directory"])).expanduser().resolve()
    if not working_directory.is_dir():
        raise FaultAcceptanceError("fault working directory does not exist")
    corruption = _run_corruption_cases(
        plan,
        root,
        environment,
        working_directory,
        command_readonly_roots,
    )
    fail_once = _run_fail_once(
        plan["fail_once_case"],
        root,
        environment,
        working_directory,
        command_readonly_roots,
    )
    rebuild = _run_rebuild(
        plan["rebuild_case"],
        root,
        environment,
        working_directory,
        command_readonly_roots,
        (readonly_roots[0], *readonly_roots[2:]),
        str(
            _read_json(
                readonly_roots[0] / "run_manifest.json",
                "accepted parent manifest",
            )["run_id"]
        ),
    )
    cache_replay = _run_cache_replay(
        plan["cache_replay_case"],
        root,
        environment,
        working_directory,
        command_readonly_roots,
    )
    final_snapshot = _readonly_snapshot(plan, readonly_roots)
    if final_snapshot != marker["readonly_snapshot"]:
        raise FaultAcceptanceError("read-only roots changed during fault acceptance")
    report = {
        "schema_version": _REPORT_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha,
        "status": "validated",
        "corruption_cases": corruption,
        "fail_once_case": fail_once,
        "rebuild_case": rebuild,
        "cache_replay_case": cache_replay,
        "readonly_snapshot": final_snapshot,
    }
    _atomic_json(root / "fault_acceptance.json", report)
    return report


def validate_existing(
    plan_path: Path,
    acceptance_root: Path,
) -> dict[str, object]:
    """Validate a terminal fault report without executing missing cases."""

    plan, _plan_sha = _load_plan(plan_path.expanduser().resolve())
    expected_case_ids = {
        str(item["id"]) for item in plan["corruption_cases"]
    } | {
        str(plan["fail_once_case"]["id"]),
        str(plan["rebuild_case"]["id"]),
        str(plan["cache_replay_case"]["id"]),
    }
    root = acceptance_root.expanduser().resolve()
    for case_id in expected_case_ids:
        terminal = root / "cases" / case_id / "result.json"
        if not terminal.is_file():
            raise FaultAcceptanceError(
                f"terminal fault case is missing: {case_id}"
            )
    report = run(plan_path, acceptance_root)
    stored = _read_json(root / "fault_acceptance.json", "fault acceptance report")
    if stored != report:
        raise FaultAcceptanceError("terminal fault acceptance report differs")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "run", "validate"))
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--acceptance-root", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.operation == "init":
            report = initialize(arguments.plan, arguments.acceptance_root)
        elif arguments.operation == "validate":
            report = validate_existing(arguments.plan, arguments.acceptance_root)
        else:
            report = run(arguments.plan, arguments.acceptance_root)
    except FaultAcceptanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
