"""Resolve and verify scientific inputs from canonical publications only."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FORBIDDEN_PARTS = frozenset({".runs", "tasks", "work", "runtime_work"})
_COMPLETED_STATUSES = frozenset({"complete", "completed"})


class PublishedArtifactError(ValueError):
    """Raised when a canonical publication or artifact is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishedArtifactError(f"cannot read publication JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PublishedArtifactError(f"publication JSON object required: {path}")
    return payload


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _contains_forbidden_part(path: Path) -> bool:
    return any(part in _FORBIDDEN_PARTS for part in path.parts)


def _validated_relative_path(value: object) -> Path:
    raw = str(value).strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise PublishedArtifactError(f"indexed artifact path must be relative: {raw!r}")
    if _contains_forbidden_part(path):
        raise PublishedArtifactError(f"run-store artifact path is forbidden: {raw}")
    return path


def _completed_manifest_status(payload: Mapping[str, Any]) -> str:
    value = payload.get("final_status", payload.get("status", ""))
    return str(value).strip().lower()


@dataclass(frozen=True)
class PublishedArtifact:
    """One verified artifact from a canonical publication index."""

    publication: str
    publication_root: Path
    relative_path: str
    path: Path
    sha256: str
    size_bytes: int
    artifact_kind: str | None

    def as_manifest_record(self) -> dict[str, Any]:
        return {
            "publication": self.publication,
            "publication_root": str(self.publication_root),
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "artifact_kind": self.artifact_kind,
        }


@dataclass(frozen=True)
class _Publication:
    alias: str
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    artifacts: dict[str, dict[str, str]]


class PublicationCatalog:
    """Process-local verifier for one or more canonical publications."""

    def __init__(self, publications: Mapping[str, _Publication]) -> None:
        self._publications = dict(publications)
        self._verified: dict[tuple[str, str], PublishedArtifact] = {}

    @classmethod
    def from_config(
        cls, value: object, *, config_base: str | Path
    ) -> "PublicationCatalog":
        if not isinstance(value, Mapping) or not value:
            raise PublishedArtifactError("publications must be a nonempty object")
        base = Path(config_base).expanduser().resolve()
        publications: dict[str, _Publication] = {}
        for raw_alias, raw_spec in value.items():
            alias = str(raw_alias).strip()
            if not alias or not isinstance(raw_spec, Mapping):
                raise PublishedArtifactError("each publication requires a named object")
            raw_root = Path(str(raw_spec.get("root", ""))).expanduser()
            root = (base / raw_root).resolve() if not raw_root.is_absolute() else raw_root.resolve()
            if _contains_forbidden_part(root):
                raise PublishedArtifactError(
                    f"publication root cannot be inside a run store: {root}"
                )
            if not root.is_dir():
                raise PublishedArtifactError(f"publication root is missing: {root}")
            manifest_relative = _validated_relative_path(
                raw_spec.get("manifest", "model_manifest.json")
            )
            manifest_path = (root / manifest_relative).resolve()
            if manifest_path.parent != root and root not in manifest_path.parents:
                raise PublishedArtifactError("publication manifest escapes its root")
            manifest = _read_json(manifest_path)
            status = _completed_manifest_status(manifest)
            if status not in _COMPLETED_STATUSES:
                raise PublishedArtifactError(
                    f"publication manifest is not complete: {manifest_path}"
                )
            index_path = root / "artifact_index.csv"
            if not index_path.is_file():
                raise PublishedArtifactError(f"publication artifact index is missing: {index_path}")
            artifacts = cls._read_index(index_path)
            publications[alias] = _Publication(
                alias=alias,
                root=root,
                manifest_path=manifest_path,
                manifest=manifest,
                artifacts=artifacts,
            )
        return cls(publications)

    @staticmethod
    def _read_index(path: Path) -> dict[str, dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = set(reader.fieldnames or ())
                required = {"relative_path", "sha256", "size_bytes", "status"}
                if not required.issubset(fields):
                    missing = sorted(required - fields)
                    raise PublishedArtifactError(
                        f"publication artifact index lacks columns {missing}: {path}"
                    )
                artifacts: dict[str, dict[str, str]] = {}
                for row in reader:
                    relative = _validated_relative_path(row.get("relative_path", "")).as_posix()
                    if relative in artifacts:
                        raise PublishedArtifactError(
                            f"duplicate publication artifact path {relative}: {path}"
                        )
                    artifacts[relative] = dict(row)
        except OSError as exc:
            raise PublishedArtifactError(f"cannot read publication artifact index: {path}") from exc
        return artifacts

    def publication_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for alias, publication in sorted(self._publications.items()):
            records.append(
                {
                    "alias": alias,
                    "root": str(publication.root),
                    "manifest": str(publication.manifest_path),
                    "extension_id": publication.manifest.get("extension_id"),
                    "status": _completed_manifest_status(publication.manifest),
                }
            )
        return records

    def manifest(self, alias: str) -> dict[str, Any]:
        """Return a copy of one verified publication manifest."""

        if alias not in self._publications:
            raise PublishedArtifactError(f"unknown publication alias: {alias!r}")
        return dict(self._publications[alias].manifest)

    def resolve_scale_display_name(
        self,
        alias: str,
        scale_id: str,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve one exact scale label from the publication-local study base."""

        if alias not in self._publications:
            raise PublishedArtifactError(f"unknown publication alias: {alias!r}")
        publication = self._publications[alias]
        declared_path = str(publication.manifest.get("study_base_path", "")).strip()
        declared_sha256 = str(
            publication.manifest.get("study_base_sha256", "")
        ).strip().lower()
        if not declared_path or len(declared_sha256) != 64:
            raise PublishedArtifactError(
                f"publication {alias!r} lacks a valid study_base path or SHA-256"
            )
        study_path = publication.root / Path(declared_path).name
        if not study_path.is_file():
            raise PublishedArtifactError(
                f"publication-local study_base is missing: {study_path}"
            )
        actual_sha256 = _sha256_file(study_path)
        if actual_sha256 != declared_sha256:
            raise PublishedArtifactError(
                "publication-local study_base SHA-256 does not match manifest"
            )
        payload = _read_json(study_path)
        study = payload.get("study")
        if not isinstance(study, Mapping):
            raise PublishedArtifactError("study_base requires a study object")
        definitions = study.get("scale_definitions")
        if not isinstance(definitions, list) or not definitions:
            raise PublishedArtifactError(
                "study_base requires nonempty study.scale_definitions"
            )
        matches = [
            value
            for value in definitions
            if isinstance(value, Mapping) and value.get("scale_id") == scale_id
        ]
        if len(matches) != 1:
            raise PublishedArtifactError(
                "study.scale_definitions must contain exactly one "
                f"{scale_id!r} entry"
            )
        label = matches[0].get("label")
        if (
            not isinstance(label, str)
            or not label
            or label != label.strip()
            or any(marker in label for marker in ("\n", "\r"))
        ):
            raise PublishedArtifactError(
                f"study scale {scale_id!r} requires a clean nonempty label"
            )
        return label, {
            "kind": "study_base",
            "path": str(study_path),
            "sha256": actual_sha256,
            "size_bytes": study_path.stat().st_size,
            "manifest_declared_path": declared_path,
            "manifest_declared_sha256": declared_sha256,
            "label_source": "study.scale_definitions[].label",
            "scale_definition_count": len(definitions),
            "resolved_scale_id": scale_id,
            "resolved_scale_display_name": label,
        }

    def indexed_paths(self, alias: str) -> tuple[str, ...]:
        """Return the publication's ordered indexed relative paths."""

        if alias not in self._publications:
            raise PublishedArtifactError(f"unknown publication alias: {alias!r}")
        return tuple(sorted(self._publications[alias].artifacts))

    def resolve_relative(self, alias: str, relative_path: str | Path) -> PublishedArtifact:
        """Resolve a relative path from a named publication."""

        return self.resolve(
            {"publication": alias, "relative_path": Path(relative_path).as_posix()}
        )

    def resolve(self, reference: object) -> PublishedArtifact:
        if not isinstance(reference, Mapping):
            raise PublishedArtifactError(
                "scientific input must be a publication artifact reference"
            )
        alias = str(reference.get("publication", "")).strip()
        if alias not in self._publications:
            raise PublishedArtifactError(f"unknown publication alias: {alias!r}")
        relative = _validated_relative_path(reference.get("relative_path", "")).as_posix()
        key = (alias, relative)
        if key in self._verified:
            return self._verified[key]
        publication = self._publications[alias]
        row = publication.artifacts.get(relative)
        if row is None:
            raise PublishedArtifactError(
                f"scientific input is not indexed by publication {alias}: {relative}"
            )
        status = str(row.get("status", "")).strip().lower()
        if status not in _COMPLETED_STATUSES:
            raise PublishedArtifactError(
                f"published artifact is not complete: {alias}:{relative}"
            )
        expected_sha = str(row.get("sha256", "")).strip().lower()
        if len(expected_sha) != 64:
            raise PublishedArtifactError(
                f"published artifact has invalid SHA-256: {alias}:{relative}"
            )
        try:
            expected_size = int(str(row.get("size_bytes", "")))
        except ValueError as exc:
            raise PublishedArtifactError(
                f"published artifact has invalid byte count: {alias}:{relative}"
            ) from exc
        path = (publication.root / relative).resolve()
        if publication.root not in path.parents:
            raise PublishedArtifactError(
                f"published artifact escapes publication root: {alias}:{relative}"
            )
        if _contains_forbidden_part(path):
            raise PublishedArtifactError(f"run-store artifact path is forbidden: {path}")
        if not path.is_file():
            raise PublishedArtifactError(f"published artifact is missing: {path}")
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise PublishedArtifactError(
                f"published artifact byte count mismatch: {path}"
            )
        if _sha256_file(path) != expected_sha:
            raise PublishedArtifactError(f"published artifact SHA-256 mismatch: {path}")
        artifact = PublishedArtifact(
            publication=alias,
            publication_root=publication.root,
            relative_path=relative,
            path=path,
            sha256=expected_sha,
            size_bytes=expected_size,
            artifact_kind=(
                str(row.get("artifact_kind") or row.get("kind"))
                if row.get("artifact_kind") or row.get("kind")
                else None
            ),
        )
        self._verified[key] = artifact
        return artifact


__all__ = [
    "PublicationCatalog",
    "PublishedArtifact",
    "PublishedArtifactError",
]
