#!/usr/bin/env python3
"""Validate canonical Task 17 model-set publications and every indexed byte."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


_SHA256 = re.compile(r"[0-9a-f]{64}")
_PROFILE_SCHEMAS = {
    "direct_voxel": "direct_voxel_model_manifest_v1",
    "normative_fiber": "normative_fiber_model_manifest_v1",
}
_FORBIDDEN_PARTS = frozenset({".runs", "tasks", "work", "runtime_work"})
_FINAL_ROLES = ("reference", "addon")


class ModelSetPublicationError(RuntimeError):
    """Raised when a canonical model-set publication is invalid."""


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
        raise ModelSetPublicationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ModelSetPublicationError(f"{label} must contain an object: {path}")
    return value


def _sha(value: object, label: str) -> str:
    token = str(value).strip()
    if _SHA256.fullmatch(token) is None:
        raise ModelSetPublicationError(
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
        or any(part in _FORBIDDEN_PARTS for part in path.parts)
    ):
        raise ModelSetPublicationError(
            f"{label} is not a safe publication-relative path: {token!r}"
        )
    return path.as_posix()


def _manifest(root: Path) -> dict[str, Any]:
    manifest = _read_json(root / "model_manifest.json", "model manifest")
    profile = str(manifest.get("profile_type", "")).strip()
    expected_schema = _PROFILE_SCHEMAS.get(profile)
    if (
        expected_schema is None
        or manifest.get("schema_version") != expected_schema
        or manifest.get("final_status") != "completed"
    ):
        raise ModelSetPublicationError(
            f"model manifest is not terminal-completed: {root}"
        )
    model_set_id = str(manifest.get("model_set_id", "")).strip()
    if not model_set_id or root.name != model_set_id or root.parent.name != profile:
        raise ModelSetPublicationError(
            f"model-set manifest identity differs from its root: {root}"
        )
    output_root = Path(str(manifest.get("output_root", ""))).expanduser().resolve()
    if output_root != root.parent.parent:
        raise ModelSetPublicationError(
            f"model-set output root differs from its location: {root}"
        )
    scale_ids = manifest.get("scale_ids")
    if (
        not isinstance(scale_ids, list)
        or not scale_ids
        or any(not isinstance(value, str) or not value.strip() for value in scale_ids)
        or len(set(scale_ids)) != len(scale_ids)
        or manifest.get("scale_count") != len(scale_ids)
    ):
        raise ModelSetPublicationError(
            f"model-set scale closure is invalid: {root}"
        )
    for key in ("source_run_id", "study_id"):
        if not str(manifest.get(key, "")).strip():
            raise ModelSetPublicationError(
                f"model manifest lacks {key}: {root}"
            )
    _sha(
        manifest.get("scientific_config_sha256"),
        "scientific configuration SHA",
    )
    return manifest


def _validate_bound_inputs(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    resolved_relative = _safe_relative(
        manifest.get("resolved_model_path", ""),
        "resolved model path",
    )
    resolved_path = root / resolved_relative
    if not resolved_path.is_file() or resolved_path.is_symlink():
        raise ModelSetPublicationError(
            f"resolved model is unavailable or symbolic: {resolved_path}"
        )
    resolved_sha = _sha(
        manifest.get("resolved_model_sha256"),
        "resolved model SHA",
    )
    if _sha256_file(resolved_path) != resolved_sha:
        raise ModelSetPublicationError(
            f"resolved model SHA differs: {resolved_path}"
        )
    study_path = Path(str(manifest.get("study_base_path", ""))).expanduser()
    if not study_path.is_absolute() or study_path.resolve() != root / "study_base.json":
        raise ModelSetPublicationError(
            f"study-base path differs from the publication root: {root}"
        )
    if not study_path.is_file() or study_path.is_symlink():
        raise ModelSetPublicationError(
            f"study-base file is unavailable or symbolic: {study_path}"
        )
    study_sha = _sha(manifest.get("study_base_sha256"), "study-base SHA")
    if _sha256_file(study_path) != study_sha:
        raise ModelSetPublicationError(
            f"study-base SHA differs: {study_path}"
        )
    return {
        "resolved_model_relative_path": resolved_relative,
        "resolved_model_sha256": resolved_sha,
        "study_base_sha256": study_sha,
    }


def _read_index(
    root: Path,
    profile: str,
    scale_ids: Sequence[str],
) -> dict[str, dict[str, str]]:
    path = root / "artifact_index.csv"
    required = {
        "scale_id",
        "model_family",
        "branch_id",
        "stage",
        "artifact_kind",
        "relative_path",
        "sha256",
        "size_bytes",
        "status",
    }
    if profile == "normative_fiber":
        required.update({"connectome_id", "connectome_role"})
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not required.issubset(set(reader.fieldnames or ())):
                raise ModelSetPublicationError(
                    f"artifact index lacks required columns: {path}"
                )
            rows: dict[str, dict[str, str]] = {}
            for raw in reader:
                relative = _safe_relative(
                    raw.get("relative_path", ""),
                    "artifact index path",
                )
                if relative in rows:
                    raise ModelSetPublicationError(
                        f"artifact index contains a duplicate path: {relative}"
                    )
                if str(raw.get("status", "")).strip() != "completed":
                    raise ModelSetPublicationError(
                        f"artifact index row is not completed: {relative}"
                    )
                _sha(raw.get("sha256"), f"artifact SHA for {relative}")
                try:
                    size = int(str(raw.get("size_bytes", "")))
                except ValueError as exc:
                    raise ModelSetPublicationError(
                        f"artifact byte count is invalid: {relative}"
                    ) from exc
                if size < 0:
                    raise ModelSetPublicationError(
                        f"artifact byte count is negative: {relative}"
                    )
                scale_id = str(raw.get("scale_id", "")).strip()
                if scale_id and scale_id not in scale_ids:
                    raise ModelSetPublicationError(
                        f"artifact scale is absent from the manifest: {relative}"
                    )
                rows[relative] = dict(raw)
    except OSError as exc:
        raise ModelSetPublicationError(
            f"cannot read artifact index: {path}"
        ) from exc
    if not rows:
        raise ModelSetPublicationError(f"artifact index is empty: {path}")
    return rows


def _validate_final_models(
    root: Path,
    manifest: Mapping[str, Any],
    rows: Mapping[str, Mapping[str, str]],
) -> int:
    profile = str(manifest["profile_type"])
    expected_schema = f"{profile}_final_model_v1"
    scientific_sha = str(manifest["scientific_config_sha256"])
    expected = {
        f"{scale_id}/{role}/final_model.json"
        for scale_id in manifest["scale_ids"]
        for role in _FINAL_ROLES
    }
    actual = {
        relative
        for relative in rows
        if relative.endswith("/final_model.json")
    }
    if actual != expected:
        raise ModelSetPublicationError(
            f"final-model index closure differs: {root}"
        )
    for relative in sorted(expected):
        scale_id, role, _name = Path(relative).parts
        document = _read_json(root / relative, "final-model record")
        if (
            document.get("schema_version") != expected_schema
            or document.get("final_status") != "final_model_realized"
            or document.get("scale_id") != scale_id
            or document.get("model_family") != role
        ):
            raise ModelSetPublicationError(
                f"final-model identity differs: {relative}"
            )
        if (
            "scientific_config_sha256" in document
            and document["scientific_config_sha256"] != scientific_sha
        ):
            raise ModelSetPublicationError(
                f"final-model scientific identity differs: {relative}"
            )
        linked: list[str] = []
        for key in (
            "source_record_relative_path",
            "resolver_relative_path",
            "valid_feature_axis_relative_path",
        ):
            if document.get(key):
                linked.append(
                    _safe_relative(document[key], f"{relative} {key}")
                )
        artifacts = document.get("artifact_relative_paths", [])
        if not isinstance(artifacts, list):
            raise ModelSetPublicationError(
                f"final-model artifact list is invalid: {relative}"
            )
        linked.extend(
            _safe_relative(value, f"{relative} artifact path")
            for value in artifacts
        )
        missing = sorted(value for value in linked if value not in rows)
        if missing:
            raise ModelSetPublicationError(
                f"final-model references unindexed payloads: {relative}"
            )
    return len(expected)


def validate_publication(publication_root: Path) -> dict[str, Any]:
    root = publication_root.expanduser().resolve()
    manifest = _manifest(root)
    profile = str(manifest["profile_type"])
    bound_inputs = _validate_bound_inputs(root, manifest)
    rows = _read_index(root, profile, tuple(manifest["scale_ids"]))
    total_bytes = 0
    closure = hashlib.sha256()
    for relative, row in sorted(rows.items()):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ModelSetPublicationError(
                f"indexed payload is unavailable or symbolic: {relative}"
            )
        resolved = path.resolve()
        if root not in resolved.parents:
            raise ModelSetPublicationError(
                f"indexed payload escapes the publication root: {relative}"
            )
        expected_size = int(row["size_bytes"])
        if path.stat().st_size != expected_size:
            raise ModelSetPublicationError(
                f"indexed payload byte count differs: {relative}"
            )
        actual_sha = _sha256_file(path)
        if actual_sha != row["sha256"]:
            raise ModelSetPublicationError(
                f"indexed payload SHA differs: {relative}"
            )
        total_bytes += expected_size
        closure.update(
            f"{relative}\0{actual_sha}\0{expected_size}\n".encode("utf-8")
        )
    final_model_count = _validate_final_models(root, manifest, rows)
    return {
        "artifact_bytes": total_bytes,
        "artifact_count": len(rows),
        "artifact_index_sha256": _sha256_file(root / "artifact_index.csv"),
        "final_model_count": final_model_count,
        "indexed_payload_closure_sha256": closure.hexdigest(),
        "model_manifest_sha256": _sha256_file(root / "model_manifest.json"),
        "model_set_id": manifest["model_set_id"],
        "profile_type": profile,
        "publication_root": str(root),
        "resolved_model_relative_path": bound_inputs[
            "resolved_model_relative_path"
        ],
        "resolved_model_sha256": bound_inputs["resolved_model_sha256"],
        "scale_count": manifest["scale_count"],
        "scientific_configuration_sha256": manifest[
            "scientific_config_sha256"
        ],
        "source_run_id": manifest["source_run_id"],
        "status": "validated",
        "study_base_sha256": bound_inputs["study_base_sha256"],
        "study_id": manifest["study_id"],
    }


def validate(publication_roots: Sequence[Path]) -> dict[str, Any]:
    if not publication_roots:
        raise ModelSetPublicationError(
            "at least one publication root is required"
        )
    publications = [
        validate_publication(root)
        for root in sorted(
            (Path(value) for value in publication_roots),
            key=lambda value: str(value.expanduser().resolve()),
        )
    ]
    profiles = [str(item["profile_type"]) for item in publications]
    if len(set(profiles)) != len(profiles):
        raise ModelSetPublicationError("publication profile types are duplicated")
    for field in (
        "model_set_id",
        "scale_count",
        "scientific_configuration_sha256",
        "source_run_id",
        "study_base_sha256",
        "study_id",
    ):
        if len({str(item[field]) for item in publications}) != 1:
            raise ModelSetPublicationError(
                f"publication roots disagree on {field}"
            )
    return {
        "artifact_bytes": sum(int(item["artifact_bytes"]) for item in publications),
        "artifact_count": sum(int(item["artifact_count"]) for item in publications),
        "model_set_id": publications[0]["model_set_id"],
        "publication_count": len(publications),
        "publications": publications,
        "schema_version": "dual_frequency_task17_model_set_validation_v1",
        "scientific_configuration_sha256": publications[0][
            "scientific_configuration_sha256"
        ],
        "source_run_id": publications[0]["source_run_id"],
        "status": "validated",
        "study_base_sha256": publications[0]["study_base_sha256"],
        "study_id": publications[0]["study_id"],
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    target = path.expanduser().resolve()
    payload = _json_bytes(report)
    if target.is_file():
        if target.is_symlink() or target.read_bytes() != payload:
            raise ModelSetPublicationError(
                "model-set validation report differs from existing publication"
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
                raise ModelSetPublicationError(
                    "model-set validation report collision"
                )
        else:
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate canonical Task 17 model-set publications and every "
            "indexed payload."
        )
    )
    parser.add_argument(
        "--publication-root",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(arguments.publication_root)
        if arguments.output is not None:
            _write_report(arguments.output, report)
    except ModelSetPublicationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
