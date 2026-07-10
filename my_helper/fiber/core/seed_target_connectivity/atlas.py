"""Deterministic Lead-DBS target-atlas directory discovery."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import ROIResolutionError
from .models import TargetSource


def _nifti_suffix_length(name: str) -> int:
    lower = name.lower()
    if lower.endswith(".nii.gz"):
        return len(".nii.gz")
    if lower.endswith(".nii"):
        return len(".nii")
    return 0


def discover_targets(atlas_root: Path | str) -> tuple[TargetSource, ...]:
    """Discover every eligible target NIfTI below, but not in, an atlas root."""
    root = Path(atlas_root).expanduser()
    if not root.is_dir():
        raise ROIResolutionError(f"atlas root is not an existing directory: {root}")
    root = root.resolve()
    discovered: list[TargetSource] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if not name.startswith(".") and not (directory_path / name).is_symlink()
        )
        relative_directory = directory_path.relative_to(root)
        if not relative_directory.parts:
            continue
        for name in sorted(file_names):
            suffix_length = _nifti_suffix_length(name)
            if not suffix_length or name.startswith("._"):
                continue
            path = directory_path / name
            relative_path = path.relative_to(root).as_posix()
            target_id = relative_path[:-suffix_length]
            discovered.append(
                TargetSource(
                    target_id=target_id,
                    target_group=relative_directory.as_posix(),
                    relative_path=relative_path,
                    path=path,
                )
            )
    discovered.sort(key=lambda target: target.target_id)
    if not discovered:
        raise ROIResolutionError(f"no target NIfTI files were discovered below atlas root {root}")
    return tuple(discovered)
