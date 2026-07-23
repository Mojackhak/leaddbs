#!/usr/bin/env python3
"""Validate complete self-contained Task 17 extension-v2 publications."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_TEXT = ("file://", "/.runs/", "/tasks/", "/work/", "/runtime_work/")
_ANALYSIS_FILES = {
    "jitter": ("spatial_jitter_results.json", "spatial_jitter_results.csv"),
    "oss": ("oss_ppam_results.json", "oss_ppam_results.csv"),
}
_IGNORED_NAMES = frozenset({".DS_Store"})


class ExtensionPublicationError(RuntimeError):
    """Raised when a Task 17 extension publication is incomplete or corrupt."""


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtensionPublicationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ExtensionPublicationError(f"{label} must contain an object: {path}")
    return value


def _sha(value: object, label: str) -> str:
    token = str(value).strip()
    if _SHA256.fullmatch(token) is None:
        raise ExtensionPublicationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return token


def _safe_relative(value: object, label: str) -> str:
    token = str(value).strip()
    path = Path(token)
    if (
        not token
        or path.is_absolute()
        or ".." in path.parts
        or any(part in {".runs", "tasks", "work", "runtime_work"} for part in path.parts)
    ):
        raise ExtensionPublicationError(f"{label} is not a safe relative path: {token!r}")
    return path.as_posix()


def _is_sidecar(path: Path) -> bool:
    return path.name in _IGNORED_NAMES or path.name.startswith("._")


def _read_index(path: Path) -> dict[str, dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            required = {"relative_path", "sha256", "size_bytes", "status"}
            if not required.issubset(fields):
                raise ExtensionPublicationError(
                    f"artifact index lacks required columns: {path}"
                )
            rows: dict[str, dict[str, str]] = {}
            for raw in reader:
                relative = _safe_relative(
                    raw.get("relative_path", ""),
                    "artifact index path",
                )
                if relative in rows:
                    raise ExtensionPublicationError(
                        f"artifact index contains a duplicate path: {relative}"
                    )
                if str(raw.get("status", "")).strip() != "completed":
                    raise ExtensionPublicationError(
                        f"artifact index row is not completed: {relative}"
                    )
                _sha(raw.get("sha256"), f"artifact index SHA for {relative}")
                try:
                    size = int(str(raw.get("size_bytes", "")))
                except ValueError as exc:
                    raise ExtensionPublicationError(
                        f"artifact index byte count is invalid: {relative}"
                    ) from exc
                if size < 0:
                    raise ExtensionPublicationError(
                        f"artifact index byte count is negative: {relative}"
                    )
                rows[relative] = dict(raw)
    except OSError as exc:
        raise ExtensionPublicationError(
            f"cannot read artifact index: {path}"
        ) from exc
    if not rows:
        raise ExtensionPublicationError(f"artifact index is empty: {path}")
    return rows


def _source_identity(source_run: Path) -> dict[str, str]:
    root = source_run.expanduser().resolve()
    manifest_path = root / "run_manifest.json"
    manifest = _read_json(manifest_path, "source child manifest")
    if manifest.get("final_status") != "completed":
        raise ExtensionPublicationError("source child is not terminal-completed")
    run_id = str(manifest.get("run_id", "")).strip()
    parent_run_id = str(manifest.get("parent_run_id", "")).strip()
    scientific_hash = _sha(
        manifest.get("scientific_configuration_hash"),
        "source scientific configuration hash",
    )
    if not run_id or not parent_run_id:
        raise ExtensionPublicationError("source child identity is incomplete")
    base = _read_json(root / "base_run_reference.json", "base-run reference")
    if (
        str(base.get("base_run_id", "")).strip() != parent_run_id
        or str(base.get("scientific_configuration_hash", "")).strip()
        != scientific_hash
    ):
        raise ExtensionPublicationError(
            "source child and base-run reference identities differ"
        )
    analyses = manifest.get("selected_sensitivity_analyses")
    if (
        not isinstance(analyses, list)
        or not analyses
        or any(value not in _ANALYSIS_FILES for value in analyses)
    ):
        raise ExtensionPublicationError("source child analyses are invalid")
    return {
        "root": str(root),
        "run_id": run_id,
        "manifest_sha256": _sha256_file(manifest_path),
        "parent_run_id": parent_run_id,
        "scientific_configuration_hash": scientific_hash,
        "analyses": ",".join(str(value) for value in analyses),
    }


def _validate_parent(root: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    declared_root = Path(
        str(manifest.get("parent_publication_root", ""))
    ).expanduser().resolve()
    actual_root = root.parent.parent.resolve()
    if declared_root != actual_root:
        raise ExtensionPublicationError(
            "extension parent publication root differs from its location"
        )
    parent_path = actual_root / "model_manifest.json"
    parent = _read_json(parent_path, "parent publication manifest")
    if parent.get("final_status") != "completed":
        raise ExtensionPublicationError("parent publication is not completed")
    expected_sha = _sha(
        manifest.get("parent_publication_manifest_sha256"),
        "parent publication manifest SHA",
    )
    actual_sha = _sha256_file(parent_path)
    if actual_sha != expected_sha:
        raise ExtensionPublicationError(
            "parent publication manifest SHA differs"
        )
    parent_run_id = str(manifest.get("parent_run_id", "")).strip()
    if str(parent.get("source_run_id", "")).strip() != parent_run_id:
        raise ExtensionPublicationError(
            "parent publication run identity differs"
        )
    return {
        "root": str(actual_root),
        "manifest_sha256": actual_sha,
        "run_id": parent_run_id,
    }


def _validate_aggregates(
    root: Path,
    manifest: Mapping[str, Any],
    rows: Mapping[str, Mapping[str, str]],
) -> int:
    analyses = manifest.get("analyses")
    if (
        not isinstance(analyses, list)
        or not analyses
        or len(set(analyses)) != len(analyses)
        or any(value not in _ANALYSIS_FILES for value in analyses)
    ):
        raise ExtensionPublicationError("extension analyses are invalid")
    total = 0
    for analysis in analyses:
        json_name, csv_name = _ANALYSIS_FILES[str(analysis)]
        if json_name not in rows or csv_name not in rows:
            raise ExtensionPublicationError(
                f"extension aggregate is not indexed: {analysis}"
            )
        aggregate = _read_json(root / json_name, f"{analysis} aggregate")
        result_rows = aggregate.get("results")
        if not isinstance(result_rows, list):
            raise ExtensionPublicationError(
                f"{analysis} aggregate results are invalid"
            )
        count = aggregate.get("result_count")
        if type(count) is not int or count != len(result_rows) or count < 1:
            raise ExtensionPublicationError(
                f"{analysis} aggregate result count differs"
            )
        if (
            aggregate.get("source_extension_run_id")
            != manifest.get("source_extension_run_id")
            or aggregate.get("parent_run_id") != manifest.get("parent_run_id")
        ):
            raise ExtensionPublicationError(
                f"{analysis} aggregate identity differs"
            )
        try:
            with (root / csv_name).open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                csv_count = sum(1 for _ in csv.DictReader(handle))
        except OSError as exc:
            raise ExtensionPublicationError(
                f"cannot read {analysis} aggregate CSV"
            ) from exc
        if csv_count != count:
            raise ExtensionPublicationError(
                f"{analysis} aggregate CSV count differs"
            )
        total += count
    if total != manifest.get("result_count"):
        raise ExtensionPublicationError(
            "extension manifest result count differs from aggregates"
        )
    return total


def validate_extension(
    source: Mapping[str, str],
    extension_root: Path,
) -> dict[str, Any]:
    root = extension_root.expanduser().resolve()
    manifest_path = root / "extension_manifest.json"
    index_path = root / "artifact_index.csv"
    manifest = _read_json(manifest_path, "extension manifest")
    if (
        manifest.get("schema_version") != "dual_frequency_extension_manifest_v2"
        or manifest.get("status") != "completed"
        or manifest.get("publication_scope") != "complete"
        or manifest.get("selected_scales") != []
    ):
        raise ExtensionPublicationError(
            "extension manifest is not a complete v2 publication"
        )
    if str(manifest.get("extension_id", "")).strip() != root.name:
        raise ExtensionPublicationError("extension ID differs from its directory")
    if (
        manifest.get("source_extension_run_id") != source["run_id"]
        or _sha(
            manifest.get("source_extension_manifest_sha256"),
            "source child manifest SHA",
        )
        != source["manifest_sha256"]
        or manifest.get("parent_run_id") != source["parent_run_id"]
        or manifest.get("parent_scientific_configuration_hash")
        != source["scientific_configuration_hash"]
    ):
        raise ExtensionPublicationError(
            "extension and source child identities differ"
        )
    source_analyses = set(source["analyses"].split(","))
    if not set(manifest.get("analyses", ())).issubset(source_analyses):
        raise ExtensionPublicationError(
            "extension analyses are absent from the source child"
        )
    parent = _validate_parent(root, manifest)
    rows = _read_index(index_path)
    indexed = set(rows)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not _is_sidecar(path)
        and path.name not in {"artifact_index.csv", "extension_manifest.json"}
    }
    if actual != indexed:
        raise ExtensionPublicationError(
            "extension artifact index does not match the exact file closure"
        )
    total_bytes = 0
    for relative, row in sorted(rows.items()):
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ExtensionPublicationError(
                f"indexed payload is missing or escapes the root: {relative}"
            )
        expected_size = int(row["size_bytes"])
        if path.stat().st_size != expected_size:
            raise ExtensionPublicationError(
                f"indexed payload byte count differs: {relative}"
            )
        if _sha256_file(path) != row["sha256"]:
            raise ExtensionPublicationError(
                f"indexed payload SHA differs: {relative}"
            )
        total_bytes += expected_size
    result_count = _validate_aggregates(root, manifest, rows)
    metadata_paths = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not _is_sidecar(path)
        and path.suffix.lower() in {".json", ".csv"}
    ]
    for path in metadata_paths:
        text = path.read_text(encoding="utf-8")
        forbidden = next(
            (token for token in _FORBIDDEN_TEXT if token in text),
            None,
        )
        if forbidden is not None:
            raise ExtensionPublicationError(
                f"public metadata contains forbidden path text {forbidden}: {path}"
            )
    return {
        "extension_id": manifest["extension_id"],
        "publication_root": str(root),
        "analyses": list(manifest["analyses"]),
        "result_count": result_count,
        "artifact_count": len(rows),
        "artifact_bytes": total_bytes,
        "artifact_index_sha256": _sha256_file(index_path),
        "extension_manifest_sha256": _sha256_file(manifest_path),
        "parent_publication_root": parent["root"],
        "parent_publication_manifest_sha256": parent["manifest_sha256"],
        "status": "validated",
    }


def validate(
    source_run: Path,
    extension_roots: Sequence[Path],
) -> dict[str, Any]:
    if not extension_roots:
        raise ExtensionPublicationError("at least one extension root is required")
    source = _source_identity(source_run)
    publications = [
        validate_extension(source, root)
        for root in sorted(
            (Path(value) for value in extension_roots),
            key=lambda value: str(value.expanduser().resolve()),
        )
    ]
    return {
        "schema_version": "dual_frequency_task17_extension_validation_v1",
        "source_run_id": source["run_id"],
        "source_run_manifest_sha256": source["manifest_sha256"],
        "publication_count": len(publications),
        "publications": publications,
        "status": "validated",
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    serialized = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_text(encoding="utf-8") != serialized:
            raise ExtensionPublicationError(
                f"existing validation report differs: {destination}"
            )
        return
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument(
        "--extension-root",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(arguments.source_run, arguments.extension_root)
        if arguments.output is not None:
            _write_report(arguments.output, report)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except ExtensionPublicationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
