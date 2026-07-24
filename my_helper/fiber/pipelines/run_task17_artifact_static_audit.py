#!/usr/bin/env python3
"""Audit Task 17 artifacts and nested scientific executor construction."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlparse


class ArtifactStaticAuditError(RuntimeError):
    """Raised when a Task 17 artifact/static audit cannot be proven."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactStaticAuditError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ArtifactStaticAuditError(f"{label} must contain an object")
    return value


def _artifact_identity(raw: Mapping[str, object]) -> tuple[str, str, str]:
    kind = str(raw.get("kind", "")).strip()
    uri = str(raw.get("uri", "")).strip()
    digest = str(raw.get("sha256", "")).strip().lower()
    if (
        not kind
        or not uri
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ArtifactStaticAuditError("task artifact identity is invalid")
    return kind, uri, digest


def _retained_null(raw: Mapping[str, object]) -> bool:
    if "null" not in str(raw.get("kind", "")).lower():
        return False
    axes = raw.get("axis_refs")
    if not isinstance(axes, list):
        raise ArtifactStaticAuditError("task artifact axis references differ")
    tokens = tuple(
        str(axis.get("axis_id", "")).lower()
        for axis in axes
        if isinstance(axis, Mapping)
    )
    if len(tokens) != len(axes):
        raise ArtifactStaticAuditError("task artifact axis reference is invalid")
    return (
        any("permutation" in token for token in tokens)
        and any(
            any(label in token for label in ("feature", "fiber", "voxel"))
            for token in tokens
        )
    )


def _executor_name(function: ast.expr) -> str | None:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _static_executor_audit(source_root: Path) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    package_roots = tuple(
        source_root / name for name in ("runtime", "backends", "cache")
    )
    if any(not path.is_dir() for path in package_roots):
        raise ArtifactStaticAuditError("scientific source package root is missing")
    sites: list[dict[str, object]] = []
    sources: list[dict[str, str]] = []
    for package_root in package_roots:
        for path in sorted(package_root.rglob("*.py")):
            relative = path.relative_to(source_root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise ArtifactStaticAuditError(
                    f"scientific source cannot be parsed: {path}"
                ) from exc
            sources.append(
                {
                    "path": relative,
                    "sha256": _sha256_file(path),
                }
            )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _executor_name(node.func)
                if name in {"ProcessPoolExecutor", "ThreadPoolExecutor"}:
                    sites.append(
                        {
                            "path": relative,
                            "line": int(node.lineno),
                            "constructor": name,
                        }
                    )
    return sites, sources


def _atomic_publish(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(
        dict(payload),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ArtifactStaticAuditError(
                "artifact/static audit differs from existing publication"
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _inside_run(path: Path, run_root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved != run_root and run_root not in resolved.parents:
        raise ArtifactStaticAuditError(f"{label} lies outside the run root")
    return resolved


def audit(
    *,
    run_root: Path,
    segment_id: str,
    source_root: Path,
) -> Path:
    """Produce one deterministic artifact/static audit for a finished segment."""

    run_root = run_root.expanduser().resolve()
    source_root = source_root.expanduser().resolve()
    segment_id = str(segment_id).strip()
    if not segment_id.startswith("segment_"):
        raise ArtifactStaticAuditError("execution segment ID is invalid")
    manifest = _read_json(run_root / "run_manifest.json", "run manifest")
    if manifest.get("final_status") != "completed":
        raise ArtifactStaticAuditError("run manifest is not terminal completed")
    run_id = str(manifest.get("run_id", "")).strip()
    if not run_id:
        raise ArtifactStaticAuditError("run manifest lacks a run ID")
    segment_path = _inside_run(
        run_root / "execution_segments" / f"{segment_id}.json",
        run_root,
        "execution segment",
    )
    segment = _read_json(segment_path, "execution segment")
    if segment.get("status") != "finished":
        raise ArtifactStaticAuditError("execution segment is not finished")
    event_path = _inside_run(
        run_root / str(segment.get("performance_events_path", "")),
        run_root,
        "performance event report",
    )
    event_sha = str(segment.get("performance_events_sha256", ""))
    if (
        not event_path.is_file()
        or _sha256_file(event_path) != event_sha
    ):
        raise ArtifactStaticAuditError("performance event report binding differs")
    event_report = _read_json(event_path, "performance event report")
    fragments = event_report.get("fragments")
    if (
        event_report.get("segment_id") != segment_id
        or event_report.get("aggregation_status") != "complete"
        or not isinstance(fragments, list)
    ):
        raise ArtifactStaticAuditError("performance event report is incomplete")
    task_ids = sorted(
        {
            str(item.get("task_id", "")).strip()
            for item in fragments
            if isinstance(item, Mapping)
        }
    )
    if not task_ids or any(not task_id for task_id in task_ids):
        raise ArtifactStaticAuditError("performance task closure is invalid")

    artifact_index_path = _inside_run(
        run_root / "artifact_index.json",
        run_root,
        "artifact index",
    )
    artifact_index = _read_json(artifact_index_path, "artifact index")
    indexed_rows = artifact_index.get("artifacts")
    if not isinstance(indexed_rows, list):
        raise ArtifactStaticAuditError("artifact index rows differ")
    indexed: dict[tuple[str, str, str], str] = {}
    for row in indexed_rows:
        if not isinstance(row, Mapping):
            raise ArtifactStaticAuditError("artifact index row must be an object")
        identity = _artifact_identity(row)
        artifact_id = str(row.get("artifact_id", "")).strip()
        if not artifact_id or identity in indexed:
            raise ArtifactStaticAuditError(
                "artifact index identity is empty or duplicated"
            )
        indexed[identity] = artifact_id

    retained: set[str] = set()
    inspected_artifact_ids: set[str] = set()
    for task_id in task_ids:
        task_state_path = _inside_run(
            run_root / "tasks" / f"{task_id}.json",
            run_root,
            f"task state {task_id}",
        )
        state = _read_json(
            task_state_path,
            f"task state {task_id}",
        )
        result = state.get("result")
        if state.get("status") != "completed":
            raise ArtifactStaticAuditError(
                "audited task state is not completed"
            )
        if not isinstance(result, Mapping):
            raise ArtifactStaticAuditError("completed task lacks a result")
        artifacts = result.get("artifacts")
        if not isinstance(artifacts, list):
            raise ArtifactStaticAuditError("completed task artifacts differ")
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                raise ArtifactStaticAuditError("task artifact must be an object")
            identity = _artifact_identity(artifact)
            artifact_id = indexed.get(identity)
            if artifact_id is None:
                raise ArtifactStaticAuditError(
                    "task artifact is missing from the artifact index"
                )
            inspected_artifact_ids.add(artifact_id)
            parsed = urlparse(identity[1])
            if parsed.scheme != "file":
                raise ArtifactStaticAuditError("task artifact must use a file URI")
            path = Path(unquote(parsed.path)).resolve()
            if not path.is_file() or _sha256_file(path) != identity[2]:
                raise ArtifactStaticAuditError(
                    "task artifact payload SHA differs"
                )
            if _retained_null(artifact):
                retained.add(artifact_id)

    nested_sites, sources = _static_executor_audit(source_root)
    output = (
        run_root
        / "execution_segments"
        / f"artifact_static_audit_{segment_id}.json"
    )
    _atomic_publish(
        output,
        {
            "schema_version": "dual_frequency_artifact_static_audit_v1",
            "run_id": run_id,
            "segment_id": segment_id,
            "segment_sha256": _sha256_file(segment_path),
            "performance_event_report_path": str(event_path),
            "performance_event_report_sha256": event_sha,
            "artifact_index_path": str(artifact_index_path),
            "artifact_index_sha256": _sha256_file(artifact_index_path),
            "task_ids": task_ids,
            "inspected_artifact_ids": sorted(inspected_artifact_ids),
            "retained_null_n_by_f_artifact_ids": sorted(retained),
            "nested_executor_creation_sites": nested_sites,
            "scientific_source_root": str(source_root),
            "scientific_source_files": sources,
        },
    )
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "core"
            / "dual_frequency"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    output = audit(
        run_root=arguments.run_root,
        segment_id=arguments.segment_id,
        source_root=arguments.source_root,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
