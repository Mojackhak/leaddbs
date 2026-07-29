"""Atomic run-scoped status, configuration, and artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

import yaml

from ..contracts import ArtifactRef
from ..instrumentation import increment_performance_event


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
    """Creation fields and invocation provenance that do not gate resume."""

    study_id: str
    run_id: str
    study_base_sha256: str
    code_identity: str
    configuration_hash: str
    scientific_configuration_hash: str
    plan_hash: str
    parent_run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "study_id", _token(self.study_id, "study_id"))
        object.__setattr__(self, "run_id", _token(self.run_id, "run_id"))
        object.__setattr__(self, "study_base_sha256", _digest(self.study_base_sha256, "study_base_sha256"))
        object.__setattr__(self, "code_identity", _token(self.code_identity, "code_identity"))
        for field in ("configuration_hash", "scientific_configuration_hash", "plan_hash"):
            object.__setattr__(self, field, _digest(getattr(self, field), field))
        if self.parent_run_id is not None:
            object.__setattr__(self, "parent_run_id", _token(self.parent_run_id, "parent_run_id"))
            if self.parent_run_id == self.run_id:
                raise RunStoreError("parent_run_id must differ from run_id")


class RunStore:
    """Atomic persistence for one exact workflow run."""

    MANIFEST_NAME = "run_manifest.json"
    COMPLETE_NAME = "complete.json"

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
        force: bool = False,
    ) -> "RunStore":
        root = Path(root).expanduser().resolve()
        if resume and force:
            raise RunStoreError("resume and force cannot both be enabled")
        if root.exists():
            if force:
                try:
                    subprocess.run(
                        ("/usr/bin/trash", str(root)),
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except (OSError, subprocess.CalledProcessError) as exc:
                    raise RunStoreError(
                        f"cannot move existing run root to Trash: {root}"
                    ) from exc
            elif not resume:
                raise RunStoreError(f"run root already exists: {root}")
            else:
                return cls(root, identity, allowed_artifact_roots)
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
        published = False
        try:
            cls._write_initial_files(
                temporary,
                identity,
                resolved_configuration,
                configuration_sources,
            )
            os.replace(temporary, root)
            published = True
        finally:
            if not published and temporary.exists():
                shutil.rmtree(temporary)
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

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    def read_manifest(self) -> dict[str, Any]:
        return json.loads((self.root / self.MANIFEST_NAME).read_text(encoding="utf-8"))

    def annotate_manifest(self, values: Mapping[str, Any]) -> None:
        """Atomically add immutable run-type metadata without changing identity fields."""

        protected = {"schema_version", "final_status", *asdict(self.identity)}
        if any(key in protected for key in values):
            raise RunStoreError("manifest annotations cannot replace identity or status fields")
        with self._lock:
            manifest = self.read_manifest()
            for key, value in values.items():
                if key in manifest and manifest[key] != value:
                    raise RunStoreError(f"run manifest annotation changed for {key}")
                manifest[key] = value
            _atomic_write_text(
                self.root / self.MANIFEST_NAME,
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            )

    def write_task_state(self, task_id: str, payload: Mapping[str, Any]) -> None:
        task_id = _token(task_id, "task_id")
        document = dict(payload)
        document["task_id"] = task_id
        with self._lock:
            state_path = self.root / "tasks" / f"{task_id}.json"
            complete_path = self.root / "tasks" / task_id / self.COMPLETE_NAME
            _atomic_write_text(
                state_path,
                json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            )
            if document.get("status") == "completed":
                _atomic_write_text(
                    complete_path,
                    json.dumps(
                        {
                            "schema_version": "dual_frequency_task_complete_v1",
                            "task_state": f"../{task_id}.json",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )


    def read_task_state(self, task_id: str) -> dict[str, Any] | None:
        path = self.root / "tasks" / f"{_token(task_id, 'task_id')}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def read_task_completion(self, task_id: str) -> dict[str, Any] | None:
        task_id = _token(task_id, "task_id")
        state_path = self.root / "tasks" / f"{task_id}.json"
        complete_path = self.root / "tasks" / task_id / self.COMPLETE_NAME
        if not state_path.is_file() or not complete_path.is_file():
            return None
        return json.loads(state_path.read_text(encoding="utf-8"))

    def task_states(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((self.root / "tasks").glob("task_*.json"))
        )

    def begin_execution_segment(self, payload: Mapping[str, Any]) -> str:
        """Append one parent-owned execution segment and return its stable ID."""

        with self._lock:
            root = self.root / "execution_segments"
            root.mkdir(parents=True, exist_ok=True)
            indexes = tuple(
                int(path.stem.removeprefix("segment_"))
                for path in root.glob("segment_*.json")
                if path.stem.removeprefix("segment_").isdigit()
            )
            index = max(indexes, default=0) + 1
            segment_id = f"segment_{index:04d}"
            document = {
                "schema_version": "dual_frequency_execution_segment_v1",
                "segment_id": segment_id,
                "status": "running",
                **dict(payload),
            }
            _atomic_write_text(
                root / f"{segment_id}.json",
                json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            )
            return segment_id

    def finish_execution_segment(
        self,
        segment_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Atomically close one execution segment without changing its settings."""

        segment_id = _token(segment_id, "execution segment ID")
        path = self.root / "execution_segments" / f"{segment_id}.json"
        with self._lock:
            if not path.is_file():
                raise RunStoreError(f"execution segment does not exist: {segment_id}")
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("status") != "running":
                raise RunStoreError(f"execution segment is already closed: {segment_id}")
            additions = dict(payload)
            replaceable = {"pool_generation_count"}
            if any(
                key in document
                for key in additions
                if key != "status" and key not in replaceable
            ):
                raise RunStoreError("execution segment completion cannot replace settings")
            if "pool_generation_count" in additions:
                initial_count = document.get("pool_generation_count")
                final_count = additions["pool_generation_count"]
                if (
                    type(initial_count) is not int
                    or type(final_count) is not int
                    or initial_count < 1
                    or final_count < initial_count
                ):
                    raise RunStoreError(
                        "execution segment pool generation count cannot decrease"
                    )
            document.update(additions)
            document["status"] = "finished"
            _atomic_write_text(
                path,
                json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            )

    def write_execution_segment_scheduler_windows(
        self,
        segment_id: str,
        rows: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        """Publish terminal scheduler windows beside one execution segment."""

        segment_id = _token(segment_id, "execution segment ID")
        if not segment_id.startswith("segment_"):
            raise RunStoreError("execution segment ID is invalid")
        normalized = [dict(row) for row in rows]
        if not normalized:
            raise RunStoreError("scheduler-window payload must contain rows")
        payload = {
            "schema_version": "dual_frequency_scheduler_windows_v1",
            "segment_id": segment_id,
            "rows": normalized,
        }
        path = (
            self.root
            / "execution_segments"
            / f"scheduler_windows_{segment_id}.json"
        )
        with self._lock:
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != payload:
                    raise RunStoreError(
                        "scheduler-window payload differs from existing publication"
                    )
            else:
                _atomic_write_text(
                    path,
                    json.dumps(
                        payload,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n",
                )
        return {
            "scheduler_windows_path": str(path.relative_to(self.root)),
            "scheduler_windows_sha256": _sha256_file(path),
            "scheduler_window_count": len(normalized),
        }

    def write_execution_segment_performance_events(
        self,
        segment_id: str,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        """Publish one parent-owned worker event report beside a segment."""

        segment_id = _token(segment_id, "execution segment ID")
        if not segment_id.startswith("segment_"):
            raise RunStoreError("execution segment ID is invalid")
        document = dict(payload)
        if (
            document.get("schema_version")
            != "dual_frequency_performance_event_report_v1"
        ):
            raise RunStoreError("performance event report schema differs")
        document["segment_id"] = segment_id
        path = (
            self.root
            / "execution_segments"
            / f"performance_events_{segment_id}.json"
        )
        with self._lock:
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != document:
                    raise RunStoreError(
                        "performance event report differs from existing publication"
                    )
            else:
                _atomic_write_text(
                    path,
                    json.dumps(
                        document,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n",
                )
        return {
            "performance_events_path": str(path.relative_to(self.root)),
            "performance_events_sha256": _sha256_file(path),
            "performance_fragment_count": int(
                document.get("fragment_count", 0)
            ),
            "performance_missing_fragment_count": int(
                document.get("missing_fragment_count", 0)
            ),
        }

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
                axis_tokens = tuple(
                    axis.axis_id.lower() for axis in artifact.axis_refs
                )
                if (
                    "null" in artifact.kind.lower()
                    and any("permutation" in token for token in axis_tokens)
                    and any(
                        any(label in token for label in ("feature", "fiber", "voxel"))
                        for token in axis_tokens
                    )
                ):
                    increment_performance_event(
                        "retained_null_n_by_f_output",
                        key=artifact.identifier,
                    )
                entry = {
                    "artifact_id": artifact.identifier,
                    "kind": artifact.kind,
                    "uri": artifact.uri,
                    "sha256": artifact.sha256,
                }
                previous = indexed.get(artifact.identifier)
                if previous is not None:
                    previous_identity = {
                        key: previous.get(key)
                        for key in ("artifact_id", "kind", "uri", "sha256")
                    }
                    if previous_identity != entry:
                        raise RunStoreError("artifact identifier collision")
                    indexed[artifact.identifier] = previous
                else:
                    indexed[artifact.identifier] = entry
            document["artifacts"] = [indexed[key] for key in sorted(indexed)]
            _atomic_write_text(path, json.dumps(document, indent=2, sort_keys=True) + "\n")
            increment_performance_event("artifact_index_snapshot")

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
            complete_path = self.root / self.COMPLETE_NAME
            if status == "completed":
                _atomic_write_text(
                    complete_path,
                    json.dumps(
                        {
                            "schema_version": "dual_frequency_run_complete_v1",
                            "run_id": self.run_id,
                            "status": "completed",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )


def migrate_completion_markers(root: Path) -> dict[str, Any]:
    """Create path-based completion markers for one pre-marker run."""

    root = Path(root).expanduser().resolve()
    tasks_root = root / "tasks"
    manifest_path = root / RunStore.MANIFEST_NAME
    if not root.is_dir() or not tasks_root.is_dir() or not manifest_path.is_file():
        raise RunStoreError(f"source run root is incomplete: {root}")

    task_states = 0
    completed_states = 0
    task_markers_created = 0
    task_markers_existing = 0
    for state_path in sorted(tasks_root.glob("*.json")):
        if state_path.name.startswith("._") or not state_path.is_file():
            continue
        task_states += 1
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunStoreError(f"cannot read task state: {state_path}") from exc
        if not isinstance(payload, Mapping):
            raise RunStoreError(f"task state must be a JSON object: {state_path}")
        if payload.get("status") != "completed":
            continue
        completed_states += 1
        task_id = _token(str(payload.get("task_id", "")), "task_id")
        if task_id != state_path.stem:
            raise RunStoreError(
                f"task state filename does not match task_id: {state_path}"
            )
        marker_path = tasks_root / task_id / RunStore.COMPLETE_NAME
        if marker_path.exists():
            if not marker_path.is_file():
                raise RunStoreError(f"task completion marker is not a file: {marker_path}")
            task_markers_existing += 1
            continue
        _atomic_write_text(
            marker_path,
            json.dumps(
                {
                    "schema_version": "dual_frequency_task_complete_v1",
                    "task_state": f"../{task_id}.json",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        task_markers_created += 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunStoreError(f"cannot read run manifest: {manifest_path}") from exc
    if not isinstance(manifest, Mapping):
        raise RunStoreError(f"run manifest must be a JSON object: {manifest_path}")

    run_marker_path = root / RunStore.COMPLETE_NAME
    run_marker_created = False
    if manifest.get("final_status") == "completed":
        run_id = _token(str(manifest.get("run_id", "")), "run_id")
        if run_marker_path.exists():
            if not run_marker_path.is_file():
                raise RunStoreError(
                    f"run completion marker is not a file: {run_marker_path}"
                )
        else:
            _atomic_write_text(
                run_marker_path,
                json.dumps(
                    {
                        "schema_version": "dual_frequency_run_complete_v1",
                        "run_id": run_id,
                        "status": "completed",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            run_marker_created = True
    elif run_marker_path.exists():
        raise RunStoreError(
            "run completion marker exists but run manifest is not completed"
        )

    return {
        "run_root": str(root),
        "task_states": task_states,
        "completed_states": completed_states,
        "task_markers_created": task_markers_created,
        "task_markers_existing": task_markers_existing,
        "run_marker_created": run_marker_created,
        "run_complete": run_marker_path.is_file(),
    }
