"""Hash-safe leaf provenance and recoverable artifact state transitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Literal, Mapping
import uuid

from .errors import ArtifactError


_PROVENANCE_KEYS = (
    "schema_version",
    "run_id",
    "input_hash",
    "study_base_sha256",
    "vta_model_sha256",
    "code_commit",
    "efield_sha256",
    "final_status",
)


class LeafStatus(str, Enum):
    MISSING = "missing"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True)
class ProvenanceContext:
    run_id: str
    input_hash: str
    study_base_sha256: str
    vta_model_sha256: str
    code_commit: str | None


@dataclass(frozen=True)
class LeafProvenance:
    schema_version: str
    run_id: str
    input_hash: str
    study_base_sha256: str
    vta_model_sha256: str
    code_commit: str | None
    efield_sha256: str | None
    final_status: Literal["completed", "failed"]


class LeafStore:
    """Own one native or MNI artifact leaf."""

    def __init__(self, leaf: Path | str, *, trash_root: Path | str | None = None):
        self.leaf = Path(leaf).expanduser().resolve()
        self._trash_root = (
            Path(trash_root).expanduser().resolve()
            if trash_root is not None
            else None
        )

    def prepare(
        self,
        context: ProvenanceContext,
        *,
        force: bool,
        resume: bool,
    ) -> Literal["run", "reuse"]:
        if force and resume:
            raise ArtifactError("force and resume are mutually exclusive")
        status = read_leaf_status(self.leaf, context.input_hash)
        if force:
            if self.leaf.exists():
                self._move_leaf_to_trash()
            return "run"
        if resume:
            if status is LeafStatus.COMPLETED:
                return "reuse"
            if status is LeafStatus.MISSING:
                return "run"
            raise ArtifactError(f"Cannot resume {status.value} leaf without force")
        if status is not LeafStatus.MISSING:
            raise ArtifactError(
                f"Leaf already exists with status {status.value}; use resume or force"
            )
        return "run"

    def complete(self, context: ProvenanceContext, efield_path: Path | str) -> None:
        efield = Path(efield_path).expanduser().resolve()
        if not efield.is_file():
            raise ArtifactError(f"E-field does not exist: {efield}")
        if efield.parent != self.leaf:
            raise ArtifactError("E-field must be written directly in its leaf")
        self._write(
            LeafProvenance(
                schema_version="vta_leaf_provenance_v1",
                run_id=context.run_id,
                input_hash=context.input_hash,
                study_base_sha256=context.study_base_sha256,
                vta_model_sha256=context.vta_model_sha256,
                code_commit=context.code_commit,
                efield_sha256=file_sha256(efield),
                final_status="completed",
            )
        )

    def fail(self, context: ProvenanceContext) -> None:
        if self.leaf.exists() and any(self.leaf.iterdir()):
            self._move_leaf_to_trash()
        self.leaf.mkdir(parents=True, exist_ok=True)
        self._write(
            LeafProvenance(
                schema_version="vta_leaf_provenance_v1",
                run_id=context.run_id,
                input_hash=context.input_hash,
                study_base_sha256=context.study_base_sha256,
                vta_model_sha256=context.vta_model_sha256,
                code_commit=context.code_commit,
                efield_sha256=None,
                final_status="failed",
            )
        )

    def _write(self, provenance: LeafProvenance) -> None:
        self.leaf.mkdir(parents=True, exist_ok=True)
        destination = self.leaf / "provenance.json"
        temporary = destination.with_suffix(".json.tmp")
        payload = asdict(provenance)
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def _move_leaf_to_trash(self) -> Path:
        trash_root = self._trash_root or _default_trash_root(self.leaf)
        try:
            trash_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ArtifactError(f"Trash is unavailable: {trash_root}") from exc
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = trash_root / (
            f"{self.leaf.name}_{stamp}_{uuid.uuid4().hex[:8]}"
        )
        try:
            os.replace(self.leaf, destination)
        except OSError as exc:
            raise ArtifactError(
                f"Unable to move leaf to Trash: {self.leaf}"
            ) from exc
        return destination


def compute_input_hash(
    task_payload: Mapping[str, object],
    *,
    study_base_sha256: str,
    vta_model_sha256: str,
    implementation_sha256: str,
    code_commit: str | None,
) -> str:
    payload = {
        "task": task_payload,
        "study_base_sha256": study_base_sha256,
        "vta_model_sha256": vta_model_sha256,
        "implementation_sha256": implementation_sha256,
        "code_commit": code_commit,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_leaf_status(
    leaf: Path | str,
    expected_input_hash: str | None = None,
) -> LeafStatus:
    leaf_path = Path(leaf)
    provenance_path = leaf_path / "provenance.json"
    if not provenance_path.is_file():
        return LeafStatus.MISSING if not leaf_path.exists() else LeafStatus.STALE
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LeafStatus.STALE
    if tuple(payload) != _PROVENANCE_KEYS:
        return LeafStatus.STALE
    if payload.get("schema_version") != "vta_leaf_provenance_v1":
        return LeafStatus.STALE
    if expected_input_hash is not None and payload.get("input_hash") != expected_input_hash:
        return LeafStatus.STALE
    final_status = payload.get("final_status")
    if final_status == "failed":
        return LeafStatus.FAILED if payload.get("efield_sha256") is None else LeafStatus.STALE
    if final_status != "completed":
        return LeafStatus.STALE
    efield = leaf_path / "efield.nii.gz"
    expected_hash = payload.get("efield_sha256")
    if not isinstance(expected_hash, str) or not efield.is_file():
        return LeafStatus.STALE
    return (
        LeafStatus.COMPLETED
        if file_sha256(efield) == expected_hash
        else LeafStatus.STALE
    )


def _default_trash_root(path: Path) -> Path:
    resolved = path.resolve()
    volumes = Path("/Volumes")
    try:
        relative = resolved.relative_to(volumes)
    except ValueError:
        return Path.home() / ".Trash"
    if not relative.parts:
        raise ArtifactError(f"Unable to identify volume Trash for {path}")
    volume_root = volumes / relative.parts[0]
    return volume_root / ".Trashes" / str(os.getuid())
