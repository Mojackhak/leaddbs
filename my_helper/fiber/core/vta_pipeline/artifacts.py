"""Path-based VTA artifact state and publication helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .errors import ArtifactError


class LeafStatus(str, Enum):
    COMPLETE = "complete"
    MISSING = "missing"


def threshold_filename(threshold_v_per_m: float) -> str:
    token = f"{threshold_v_per_m / 1000:.2f}".replace(".", "p")
    return f"vta_threshold-{token}Vpermm.nii.gz"


def expected_artifacts(
    leaf: Path | str,
    thresholds_v_per_m: tuple[float, ...],
) -> tuple[Path, ...]:
    leaf_path = Path(leaf)
    return (
        leaf_path / "efield.nii.gz",
        *(
            leaf_path / threshold_filename(threshold)
            for threshold in thresholds_v_per_m
        ),
    )


def missing_artifacts(
    leaf: Path | str,
    thresholds_v_per_m: tuple[float, ...],
) -> tuple[Path, ...]:
    return tuple(
        path
        for path in expected_artifacts(leaf, thresholds_v_per_m)
        if not path.is_file()
    )


def leaf_status(
    leaf: Path | str,
    thresholds_v_per_m: tuple[float, ...],
) -> LeafStatus:
    return (
        LeafStatus.COMPLETE
        if not missing_artifacts(leaf, thresholds_v_per_m)
        else LeafStatus.MISSING
    )


def atomic_copy_missing(source: Path | str, destination: Path | str) -> str:
    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path.is_file():
        return "skipped_existing"
    if not source_path.is_file():
        raise ArtifactError(f"Donor artifact does not exist: {source_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source_path, temporary)
        if destination_path.is_file():
            return "skipped_existing"
        os.replace(temporary, destination_path)
        return "copied"
    except OSError as exc:
        raise ArtifactError(
            f"Unable to publish copied artifact: {destination_path}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def move_leaf_to_trash(
    leaf: Path | str,
    *,
    trash_root: Path | str | None = None,
) -> Path:
    leaf_path = Path(leaf)
    if not leaf_path.exists():
        return leaf_path
    destination_root = (
        Path(trash_root) if trash_root is not None else _default_trash_root(leaf_path)
    )
    try:
        destination_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArtifactError(f"Trash is unavailable: {destination_root}") from exc
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_root / (
        f"{leaf_path.name}_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    try:
        os.replace(leaf_path, destination)
    except OSError as exc:
        raise ArtifactError(f"Unable to move leaf to Trash: {leaf_path}") from exc
    return destination


def trash_root_for(path: Path | str) -> Path:
    """Return the persistent Trash root used for one artifact leaf."""

    return _default_trash_root(Path(path))


def _default_trash_root(path: Path) -> Path:
    resolved = path.resolve()
    volumes = Path("/Volumes")
    try:
        relative = resolved.relative_to(volumes)
    except ValueError:
        return Path.home() / ".Trash"
    if not relative.parts:
        raise ArtifactError(f"Unable to identify volume Trash for {path}")
    return volumes / relative.parts[0] / ".Trashes" / str(os.getuid())
