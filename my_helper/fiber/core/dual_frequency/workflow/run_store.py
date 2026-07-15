"""Atomic run-scoped status, configuration, and artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

import yaml

from ..contracts import ArtifactRef


class RunStoreError(RuntimeError):
    """Raised when a run store cannot be created, resumed, or updated safely."""


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise RunStoreError(f"{field} must be nonempty")
    return token


def _digest(value: str, field: str) -> str:
    digest = str(value).lower().strip()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise RunStoreError(f"{field} must be a SHA-256 digest")
    return digest


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class ConfigurationSource:
    """One immutable configuration or study input source."""

    uri: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "uri", _token(self.uri, "configuration source uri"))
        object.__setattr__(self, "sha256", _digest(self.sha256, "configuration source sha256"))
        if not urlparse(self.uri).scheme:
            raise RunStoreError("configuration source uri must include an explicit scheme")


@dataclass(frozen=True)
class RunIdentity:
    """Exact identity required to create or resume one run root."""

    study_id: str
    run_id: str
    study_base_sha256: str
    code_identity: str
    configuration_hash: str
    scientific_configuration_hash: str
    plan_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "study_id", _token(self.study_id, "study_id"))
        object.__setattr__(self, "run_id", _token(self.run_id, "run_id"))
        object.__setattr__(self, "study_base_sha256", _digest(self.study_base_sha256, "study_base_sha256"))
        object.__setattr__(self, "code_identity", _token(self.code_identity, "code_identity"))
        for field in ("configuration_hash", "scientific_configuration_hash", "plan_hash"):
            object.__setattr__(self, field, _digest(getattr(self, field), field))


class RunStore:
    """Atomic persistence for one exact workflow run."""

    MANIFEST_NAME = "run_manifest.json"

    def __init__(
        self,
        root: Path,
        identity: RunIdentity,
        allowed_artifact_roots: tuple[Path, ...],
    ) -> None:
        self.root = Path(root).resolve()
        self.identity = identity
        self.allowed_artifact_roots = tuple(Path(path).resolve() for path in allowed_artifact_roots)
        if self.root not in self.allowed_artifact_roots:
            self.allowed_artifact_roots = (self.root, *self.allowed_artifact_roots)
        self._lock = RLock()

    @classmethod
    def open(
        cls,
        root: Path,
        identity: RunIdentity,
        *,
        resolved_configuration: Mapping[str, Any],
        configuration_sources: tuple[ConfigurationSource, ...],
        allowed_artifact_roots: tuple[Path, ...] = (),
        resume: bool = False,
    ) -> "RunStore":
        root = Path(root).expanduser().resolve()
        if root.exists():
            if not resume:
                raise RunStoreError(f"run root already exists: {root}")
            store = cls(root, identity, allowed_artifact_roots)
            store._validate_resume(resolved_configuration, configuration_sources)
            return store
        if resume:
            raise RunStoreError(f"cannot resume missing run root: {root}")

        root.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{root.name}.",
                suffix=".tmp",
                dir=root.parent,
            )
        )
        try:
            cls._write_initial_files(
                temporary,
                identity,
                resolved_configuration,
                configuration_sources,
            )
            os.replace(temporary, root)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return cls(root, identity, allowed_artifact_roots)

    @staticmethod
    def _write_initial_files(
        root: Path,
        identity: RunIdentity,
        resolved_configuration: Mapping[str, Any],
        configuration_sources: tuple[ConfigurationSource, ...],
    ) -> None:
        (root / "tasks").mkdir(parents=True)
        manifest = {
            "schema_version": "dual_frequency_run_v1",
            **asdict(identity),
            "final_status": "running",
        }
        (root / RunStore.MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        configuration_text = yaml.safe_dump(
            dict(resolved_configuration),
            sort_keys=True,
            allow_unicode=False,
        )
        (root / "configuration_resolved.yaml").write_text(configuration_text, encoding="utf-8")
        sources_payload = {
            "schema_version": "dual_frequency_configuration_sources_v1",
            "sources": [asdict(source) for source in configuration_sources],
        }
        (root / "configuration_sources.json").write_text(
            json.dumps(sources_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (root / "artifact_index.json").write_text(
            json.dumps(
                {"schema_version": "dual_frequency_artifact_index_v1", "artifacts": []},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _validate_resume(
        self,
        resolved_configuration: Mapping[str, Any],
        configuration_sources: tuple[ConfigurationSource, ...],
    ) -> None:
        manifest = self.read_manifest()
        expected = asdict(self.identity)
        for field, value in expected.items():
            if manifest.get(field) != value:
                raise RunStoreError(f"resume identity mismatch for {field}")
        configuration_text = yaml.safe_dump(
            dict(resolved_configuration),
            sort_keys=True,
            allow_unicode=False,
        )
        existing_configuration = (self.root / "configuration_resolved.yaml").read_text(
            encoding="utf-8"
        )
        if existing_configuration != configuration_text:
            raise RunStoreError("resume resolved configuration mismatch")
        existing_sources = json.loads((self.root / "configuration_sources.json").read_text(encoding="utf-8"))
        expected_sources = [asdict(source) for source in configuration_sources]
        if existing_sources.get("sources") != expected_sources:
            raise RunStoreError("resume configuration source mismatch")

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    def read_manifest(self) -> dict[str, Any]:
        return json.loads((self.root / self.MANIFEST_NAME).read_text(encoding="utf-8"))

    def write_task_state(self, task_id: str, payload: Mapping[str, Any]) -> None:
        task_id = _token(task_id, "task_id")
        document = dict(payload)
        document["task_id"] = task_id
        with self._lock:
            _atomic_write_text(
                self.root / "tasks" / f"{task_id}.json",
                json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            )

    def read_task_state(self, task_id: str) -> dict[str, Any] | None:
        path = self.root / "tasks" / f"{_token(task_id, 'task_id')}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def task_states(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((self.root / "tasks").glob("task_*.json"))
        )

    def record_artifacts(self, artifacts: tuple[ArtifactRef, ...]) -> None:
        if not artifacts:
            return
        with self._lock:
            path = self.root / "artifact_index.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            indexed = {item["artifact_id"]: item for item in document["artifacts"]}
            for artifact in artifacts:
                if not isinstance(artifact, ArtifactRef):
                    raise RunStoreError("artifact index accepts only ArtifactRef values")
                self._validate_artifact_location(artifact)
                entry = {
                    "artifact_id": artifact.identifier,
                    "kind": artifact.kind,
                    "uri": artifact.uri,
                    "sha256": artifact.sha256,
                }
                previous = indexed.get(artifact.identifier)
                if previous is not None and previous != entry:
                    raise RunStoreError("artifact identifier collision")
                indexed[artifact.identifier] = entry
            document["artifacts"] = [indexed[key] for key in sorted(indexed)]
            _atomic_write_text(path, json.dumps(document, indent=2, sort_keys=True) + "\n")

    def _validate_artifact_location(self, artifact: ArtifactRef) -> None:
        parsed = urlparse(artifact.uri)
        if parsed.scheme != "file":
            raise RunStoreError("run artifacts must use file URIs")
        path = Path(unquote(parsed.path)).resolve()
        if not any(path == root or root in path.parents for root in self.allowed_artifact_roots):
            raise RunStoreError(f"artifact lies outside run/cache roots: {path}")
        if not path.is_file():
            raise RunStoreError(f"artifact file does not exist: {path}")
        if _sha256_file(path) != artifact.sha256:
            raise RunStoreError(f"artifact hash mismatch: {path}")

    def finalize(self, status: str) -> None:
        if status not in {"completed", "failed"}:
            raise RunStoreError("run final status must be completed or failed")
        with self._lock:
            manifest = self.read_manifest()
            manifest["final_status"] = status
            _atomic_write_text(
                self.root / self.MANIFEST_NAME,
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
