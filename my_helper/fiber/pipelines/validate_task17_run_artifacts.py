#!/usr/bin/env python3
"""Validate a completed Task 17 run and every indexed artifact payload."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse


_SHA256 = re.compile(r"[0-9a-f]{64}")


class RunArtifactValidationError(RuntimeError):
    """Raised when a completed Task 17 run artifact closure is invalid."""


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunArtifactValidationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise RunArtifactValidationError(
            f"{label} must contain an object: {path}"
        )
    return value


def _sha(value: object, label: str) -> str:
    token = str(value).strip()
    if _SHA256.fullmatch(token) is None:
        raise RunArtifactValidationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return token


def _artifact_identity(
    raw: Mapping[str, Any],
    *,
    label: str,
) -> tuple[str, str, str]:
    kind = str(raw.get("kind", "")).strip()
    uri = str(raw.get("uri", "")).strip()
    digest = _sha(raw.get("sha256"), f"{label} SHA")
    if not kind or not uri:
        raise RunArtifactValidationError(f"{label} identity is incomplete")
    return kind, uri, digest


def _manifest(run_root: Path) -> dict[str, Any]:
    manifest = _read_json(run_root / "run_manifest.json", "run manifest")
    if manifest.get("final_status") != "completed":
        raise RunArtifactValidationError("run manifest is not terminal-completed")
    for key in (
        "run_id",
        "study_id",
        "study_base_sha256",
        "scientific_configuration_hash",
    ):
        if not str(manifest.get(key, "")).strip():
            raise RunArtifactValidationError(f"run manifest lacks {key}")
    _sha(manifest["study_base_sha256"], "study-base SHA")
    _sha(
        manifest["scientific_configuration_hash"],
        "scientific configuration SHA",
    )
    return manifest


def _task_closure(
    run_root: Path,
) -> tuple[
    dict[str, set[tuple[str, str, str]]],
    dict[tuple[str, str, str], set[str]],
    int,
    str,
]:
    paths = sorted((run_root / "tasks").glob("task_*.json"))
    if not paths:
        raise RunArtifactValidationError("run has no persisted task documents")
    by_task: dict[str, set[tuple[str, str, str]]] = {}
    tasks_by_artifact: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    reference_count = 0
    closure = hashlib.sha256()
    for path in paths:
        state = _read_json(path, "task document")
        task_id = str(state.get("task_id", "")).strip()
        if (
            not task_id
            or path.name != f"{task_id}.json"
            or task_id in by_task
            or state.get("status") != "completed"
            or str(state.get("reason", "")).strip() != "none"
        ):
            raise RunArtifactValidationError(
                f"task document is not uniquely completed: {path}"
            )
        result = state.get("result")
        if not isinstance(result, Mapping):
            raise RunArtifactValidationError(
                f"completed task lacks a typed result: {task_id}"
            )
        artifacts = result.get("artifacts")
        if not isinstance(artifacts, list):
            raise RunArtifactValidationError(
                f"completed task artifact list is invalid: {task_id}"
            )
        identities: set[tuple[str, str, str]] = set()
        for index, raw in enumerate(artifacts):
            if not isinstance(raw, Mapping):
                raise RunArtifactValidationError(
                    f"task artifact is not an object: {task_id}"
                )
            identity = _artifact_identity(
                raw,
                label=f"task {task_id} artifact {index}",
            )
            if identity in identities:
                raise RunArtifactValidationError(
                    f"task artifact identity is duplicated: {task_id}"
                )
            identities.add(identity)
            tasks_by_artifact[identity].add(task_id)
            reference_count += 1
        by_task[task_id] = identities
        digest = _sha256_file(path)
        closure.update(
            f"{path.name}\0{digest}\0{path.stat().st_size}\n".encode("utf-8")
        )
    return by_task, tasks_by_artifact, reference_count, closure.hexdigest()


def _validate_index(
    run_root: Path,
    run_id: str,
    by_task: Mapping[str, set[tuple[str, str, str]]],
    tasks_by_artifact: Mapping[tuple[str, str, str], set[str]],
) -> tuple[int, int, str, str]:
    index_path = run_root / "artifact_index.json"
    index = _read_json(index_path, "artifact index")
    if (
        index.get("schema_version") != "dual_frequency_artifact_index_v2"
        or index.get("run_id") != run_id
        or not isinstance(index.get("artifacts"), list)
        or not index["artifacts"]
    ):
        raise RunArtifactValidationError("artifact index identity is invalid")
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    artifact_ids: set[str] = set()
    uris: set[str] = set()
    for raw in index["artifacts"]:
        if not isinstance(raw, Mapping):
            raise RunArtifactValidationError(
                "artifact index row must contain an object"
            )
        identity = _artifact_identity(raw, label="indexed artifact")
        artifact_id = str(raw.get("artifact_id", "")).strip()
        if (
            not artifact_id
            or artifact_id in artifact_ids
            or identity in indexed
            or identity[1] in uris
        ):
            raise RunArtifactValidationError(
                "artifact index ID, identity, or URI is duplicated"
            )
        references = raw.get("task_references")
        if not isinstance(references, list) or not references:
            raise RunArtifactValidationError(
                f"indexed artifact lacks task references: {artifact_id}"
            )
        actual_task_ids: list[str] = []
        for reference in references:
            if not isinstance(reference, Mapping):
                raise RunArtifactValidationError(
                    f"artifact task reference is invalid: {artifact_id}"
                )
            task_id = str(reference.get("task_id", "")).strip()
            if not task_id or task_id not in by_task:
                raise RunArtifactValidationError(
                    f"artifact references an unknown task: {artifact_id}"
                )
            if identity not in by_task[task_id]:
                raise RunArtifactValidationError(
                    f"artifact reference differs from the task result: {artifact_id}"
                )
            actual_task_ids.append(task_id)
        if (
            len(set(actual_task_ids)) != len(actual_task_ids)
            or set(actual_task_ids) != tasks_by_artifact.get(identity, set())
        ):
            raise RunArtifactValidationError(
                f"artifact task-reference closure differs: {artifact_id}"
            )
        artifact_ids.add(artifact_id)
        uris.add(identity[1])
        indexed[identity] = raw
    expected = set(tasks_by_artifact)
    if set(indexed) != expected:
        raise RunArtifactValidationError(
            "artifact index and task-result identity closures differ"
        )

    total_bytes = 0
    identity_closure = hashlib.sha256()
    payload_closure = hashlib.sha256()
    for identity, raw in sorted(
        indexed.items(),
        key=lambda item: str(item[1]["artifact_id"]),
    ):
        kind, uri, expected_sha = identity
        artifact_id = str(raw["artifact_id"])
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise RunArtifactValidationError(
                f"artifact URI is not a local file URI: {artifact_id}"
            )
        path = Path(unquote(parsed.path))
        if path.is_symlink() or not path.is_file():
            raise RunArtifactValidationError(
                f"artifact payload is unavailable or symbolic: {artifact_id}"
            )
        resolved = path.resolve()
        if resolved != run_root and run_root not in resolved.parents:
            raise RunArtifactValidationError(
                f"artifact payload lies outside the run root: {artifact_id}"
            )
        actual_sha = _sha256_file(resolved)
        if actual_sha != expected_sha:
            raise RunArtifactValidationError(
                f"artifact payload SHA differs: {artifact_id}"
            )
        size = resolved.stat().st_size
        total_bytes += size
        identity_closure.update(
            f"{artifact_id}\0{kind}\0{uri}\0{expected_sha}\n".encode("utf-8")
        )
        payload_closure.update(
            f"{artifact_id}\0{uri}\0{actual_sha}\0{size}\n".encode("utf-8")
        )
    return (
        len(indexed),
        total_bytes,
        identity_closure.hexdigest(),
        payload_closure.hexdigest(),
    )


def validate(run_root: Path) -> dict[str, Any]:
    root = run_root.expanduser().resolve()
    manifest = _manifest(root)
    (
        by_task,
        tasks_by_artifact,
        reference_count,
        task_closure_sha,
    ) = _task_closure(root)
    (
        artifact_count,
        artifact_bytes,
        identity_closure_sha,
        payload_closure_sha,
    ) = _validate_index(
        root,
        str(manifest["run_id"]),
        by_task,
        tasks_by_artifact,
    )
    return {
        "artifact_bytes": artifact_bytes,
        "artifact_count": artifact_count,
        "artifact_index_identity_closure_sha256": identity_closure_sha,
        "artifact_index_sha256": _sha256_file(root / "artifact_index.json"),
        "indexed_payload_closure_sha256": payload_closure_sha,
        "run_id": manifest["run_id"],
        "run_manifest_sha256": _sha256_file(root / "run_manifest.json"),
        "run_root": str(root),
        "schema_version": "dual_frequency_task17_run_artifact_validation_v1",
        "scientific_configuration_sha256": manifest[
            "scientific_configuration_hash"
        ],
        "status": "validated",
        "study_base_sha256": manifest["study_base_sha256"],
        "study_id": manifest["study_id"],
        "task_artifact_reference_count": reference_count,
        "task_count": len(by_task),
        "task_document_closure_sha256": task_closure_sha,
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    target = path.expanduser().resolve()
    payload = _json_bytes(report)
    if target.is_file():
        if target.is_symlink() or target.read_bytes() != payload:
            raise RunArtifactValidationError(
                "run-artifact validation report differs from existing publication"
            )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=f".{uuid.uuid4().hex}.tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            if target.is_symlink() or target.read_bytes() != payload:
                raise RunArtifactValidationError(
                    "run-artifact validation report collision"
                )
        else:
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(arguments.run_root)
        if arguments.output is not None:
            _write_report(arguments.output, report)
    except RunArtifactValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
