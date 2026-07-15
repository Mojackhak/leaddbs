"""Namespaced configured-run storage with auditable provenance."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .identity import canonical_hash


REQUIRED_RUN_ARTIFACTS = (
    "workflow_resolved.yaml",
    "endpoint_catalog.csv",
    "execution_plan.json",
    "task_status.csv",
    "run_manifest.json",
    "artifact_index.csv",
)

_TASK_STATUS_FIELDS = (
    "task_id",
    "endpoint_model_id",
    "status",
    "detail",
    "started_at",
    "finished_at",
    "dependency_ids",
    "final_model_id",
)
_ARTIFACT_INDEX_FIELDS = (
    "task_id",
    "kind",
    "relative_path",
    "sha256",
    "size_bytes",
)
_DEFAULT_LEGACY_ROOTS = (Path("/Volumes/VAL/STNSNr/summary"),)
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.-]+$")


class RunStoreError(RuntimeError):
    """Raised when configured-run storage cannot satisfy its safety contract."""


class RunIdentityMismatch(RunStoreError):
    """Raised when resume provenance differs from the recorded run identity."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a regular file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token or not _SAFE_TOKEN.fullmatch(token):
        raise RunStoreError(f"{field} contains unsafe path characters: {value!r}")
    return token


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalized_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    )


def _validate_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalized_mapping(provenance)
    missing = [key for key in ("configuration_hash", "input_hashes", "code_provenance") if key not in normalized]
    if missing:
        raise RunStoreError(f"missing run provenance fields: {','.join(missing)}")
    if not isinstance(normalized["input_hashes"], dict) or not isinstance(normalized["code_provenance"], dict):
        raise RunStoreError("input_hashes and code_provenance must be mappings")
    return normalized


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _atomic_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    _atomic_write(path, payload.encode("utf-8"))


def _atomic_yaml(path: Path, value: Mapping[str, Any]) -> None:
    payload = yaml.safe_dump(dict(value), sort_keys=False, allow_unicode=False)
    _atomic_write(path, payload.encode("utf-8"))


def _csv_text(rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output.getvalue()


def _catalog_fields(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    if not rows:
        return ("endpoint_model_id", "status")
    fields: set[str] = set()
    for row in rows:
        fields.update(str(key) for key in row)
    preferred = ["endpoint_model_id", "study_id", "scale_id", "endpoint_phase", "model_family", "connectome", "status"]
    ordered = [field for field in preferred if field in fields]
    ordered.extend(sorted(fields - set(ordered)))
    return tuple(ordered)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class ConfiguredRunStore:
    """Filesystem namespace and provenance contract for one configured run."""

    output_root: Path
    study_id: str
    run_id: str
    run_fingerprint: str
    run_root: Path
    provenance: Mapping[str, Any]
    started_at: str
    supersedes_run_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        output_root: Path,
        study_id: str,
        provenance: Mapping[str, Any],
        started_at: datetime | None = None,
        supersedes_run_id: str | None = None,
        legacy_roots: Iterable[Path] = _DEFAULT_LEGACY_ROOTS,
    ) -> "ConfiguredRunStore":
        resolved_output = Path(output_root).expanduser().resolve()
        for legacy_root in legacy_roots:
            resolved_legacy = Path(legacy_root).expanduser().resolve()
            if _is_within(resolved_output, resolved_legacy):
                raise RunStoreError(f"configured runs cannot be created inside legacy output root {resolved_legacy}")

        safe_study = _safe_token(study_id, "study_id")
        normalized_provenance = _validate_provenance(provenance)
        provenance_hash = canonical_hash(normalized_provenance)
        fingerprint = provenance_hash[:16]
        timestamp = started_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise RunStoreError("started_at must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
        started_text = timestamp.isoformat().replace("+00:00", "Z")
        run_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{fingerprint}"
        if supersedes_run_id is not None:
            _safe_token(supersedes_run_id, "supersedes_run_id")

        run_root = resolved_output / "configured_model_runs" / safe_study / run_id
        try:
            run_root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise RunStoreError(f"configured run already exists: {run_root}") from exc
        return cls(
            output_root=resolved_output,
            study_id=safe_study,
            run_id=run_id,
            run_fingerprint=fingerprint,
            run_root=run_root,
            provenance=normalized_provenance,
            started_at=started_text,
            supersedes_run_id=supersedes_run_id,
        )

    @classmethod
    def resume(
        cls,
        *,
        output_root: Path,
        study_id: str,
        run_id: str,
        expected_provenance: Mapping[str, Any],
    ) -> "ConfiguredRunStore":
        resolved_output = Path(output_root).expanduser().resolve()
        safe_study = _safe_token(study_id, "study_id")
        safe_run = _safe_token(run_id, "run_id")
        run_root = resolved_output / "configured_model_runs" / safe_study / safe_run
        manifest_path = run_root / "run_manifest.json"
        if not manifest_path.is_file():
            raise RunStoreError(f"run manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        normalized_provenance = _validate_provenance(expected_provenance)
        expected_hash = canonical_hash(normalized_provenance)
        if manifest.get("provenance_hash") != expected_hash:
            raise RunIdentityMismatch(
                f"run {safe_run} provenance does not match the requested configuration and inputs"
            )
        return cls(
            output_root=resolved_output,
            study_id=safe_study,
            run_id=safe_run,
            run_fingerprint=str(manifest["run_fingerprint"]),
            run_root=run_root,
            provenance=normalized_provenance,
            started_at=str(manifest["started_at"]),
            supersedes_run_id=manifest.get("supersedes_run_id"),
        )

    def initialize(
        self,
        *,
        resolved_workflow: Mapping[str, Any],
        endpoint_catalog: Sequence[Mapping[str, Any]],
        execution_plan: Mapping[str, Any],
    ) -> None:
        if any((self.run_root / name).exists() for name in REQUIRED_RUN_ARTIFACTS):
            raise RunStoreError(f"configured run is already initialized: {self.run_root}")
        catalog_rows = [dict(row) for row in endpoint_catalog]
        run_manifest = {
            "run_id": self.run_id,
            "study_id": self.study_id,
            "started_at": self.started_at,
            "run_fingerprint": self.run_fingerprint,
            "provenance_hash": canonical_hash(self.provenance),
            "configuration_hash": self.provenance["configuration_hash"],
            "input_hashes": self.provenance["input_hashes"],
            "code_provenance": self.provenance["code_provenance"],
            "supersedes_run_id": self.supersedes_run_id,
            "status": "initialized",
        }
        _atomic_yaml(self.run_root / "workflow_resolved.yaml", resolved_workflow)
        _atomic_write(
            self.run_root / "endpoint_catalog.csv",
            _csv_text(catalog_rows, _catalog_fields(catalog_rows)).encode("utf-8"),
        )
        _atomic_json(self.run_root / "execution_plan.json", execution_plan)
        _atomic_write(self.run_root / "task_status.csv", _csv_text([], _TASK_STATUS_FIELDS).encode("utf-8"))
        _atomic_json(self.run_root / "run_manifest.json", run_manifest)
        _atomic_write(
            self.run_root / "artifact_index.csv",
            _csv_text([], _ARTIFACT_INDEX_FIELDS).encode("utf-8"),
        )

    def write_task_statuses(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._require_initialized()
        _atomic_write(
            self.run_root / "task_status.csv",
            _csv_text([dict(row) for row in rows], _TASK_STATUS_FIELDS).encode("utf-8"),
        )

    def load_task_statuses(self) -> tuple[dict[str, str], ...]:
        self._require_initialized()
        return tuple(_read_csv(self.run_root / "task_status.csv"))

    def load_run_manifest(self) -> dict[str, Any]:
        self._require_initialized()
        return json.loads((self.run_root / "run_manifest.json").read_text(encoding="utf-8"))

    def update_run_manifest(self, updates: Mapping[str, Any]) -> None:
        manifest = self.load_run_manifest()
        immutable = {"run_id", "study_id", "started_at", "run_fingerprint", "provenance_hash"}
        changed = sorted(key for key in immutable if key in updates and updates[key] != manifest.get(key))
        if changed:
            raise RunStoreError(f"cannot change immutable run manifest fields: {','.join(changed)}")
        manifest.update(dict(updates))
        _atomic_json(self.run_root / "run_manifest.json", manifest)

    def load_artifact_index(self) -> tuple[dict[str, str], ...]:
        self._require_initialized()
        return tuple(_read_csv(self.run_root / "artifact_index.csv"))

    def recover_interrupted_tasks(self) -> tuple[str, ...]:
        self._require_initialized()
        rows = _read_csv(self.run_root / "task_status.csv")
        interrupted: list[str] = []
        for row in rows:
            if row["status"] == "running":
                row["status"] = "interrupted"
                row["detail"] = row["detail"] or "recovered_after_interruption"
                interrupted.append(row["task_id"])
        if interrupted:
            self.write_task_statuses(rows)
        return tuple(interrupted)

    def write_task_manifest(self, *, task_id: str, manifest: Mapping[str, Any]) -> Path:
        self._require_initialized()
        safe_task = _safe_token(task_id, "task_id")
        payload = dict(manifest)
        payload.update(
            {
                "task_id": safe_task,
                "configuration_hash": self.provenance["configuration_hash"],
                "input_hashes": self.provenance["input_hashes"],
                "code_provenance": self.provenance["code_provenance"],
            }
        )
        path = self.run_root / "tasks" / safe_task / "task_manifest.json"
        _atomic_json(path, payload)
        return path

    def load_task_manifest(self, task_id: str) -> dict[str, Any] | None:
        self._require_initialized()
        safe_task = _safe_token(task_id, "task_id")
        path = self.run_root / "tasks" / safe_task / "task_manifest.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def record_artifact(self, *, task_id: str, kind: str, path: Path) -> None:
        self._require_initialized()
        safe_task = _safe_token(task_id, "task_id")
        safe_kind = _safe_token(kind, "kind")
        artifact_path = Path(path).expanduser().resolve()
        if not artifact_path.is_file():
            raise RunStoreError(f"artifact does not exist: {artifact_path}")
        if not _is_within(artifact_path, self.run_root):
            raise RunStoreError(f"artifact must be inside configured run root: {artifact_path}")
        relative_path = artifact_path.relative_to(self.run_root).as_posix()
        rows = _read_csv(self.run_root / "artifact_index.csv")
        record = {
            "task_id": safe_task,
            "kind": safe_kind,
            "relative_path": relative_path,
            "sha256": sha256_file(artifact_path),
            "size_bytes": str(artifact_path.stat().st_size),
        }
        rows = [
            row
            for row in rows
            if (row["task_id"], row["kind"], row["relative_path"])
            != (safe_task, safe_kind, relative_path)
        ]
        rows.append(record)
        rows.sort(key=lambda row: (row["task_id"], row["kind"], row["relative_path"]))
        _atomic_write(
            self.run_root / "artifact_index.csv",
            _csv_text(rows, _ARTIFACT_INDEX_FIELDS).encode("utf-8"),
        )

    def _require_initialized(self) -> None:
        missing = [name for name in REQUIRED_RUN_ARTIFACTS if not (self.run_root / name).is_file()]
        if missing:
            raise RunStoreError(f"configured run is not initialized; missing {','.join(missing)}")
