"""Read-only whole-batch validation for the seed-wide MRtrix pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import nibabel as nib
import numpy as np

from .config import load_config
from .discovery import discover_subject, iter_all_roi_paths
from .errors import ValidationError
from .identity import file_sha256, implementation_hash
from .models import BatchConfig, ValidationBundle
from .tools import resolve_tool_identities


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_source_rois(config: BatchConfig) -> dict[str, str]:
    root = config.atlas.root.resolve()
    if not root.is_dir():
        raise ValidationError(f"atlas root does not exist: {root}")
    hashes: dict[str, str] = {}
    reference_shape: tuple[int, ...] | None = None
    reference_affine: np.ndarray | None = None
    for path in iter_all_roi_paths(config.atlas.seeds):
        if not _inside(path, root):
            raise ValidationError(f"ROI resolves outside atlas root {root}: {path}")
        if not path.is_file():
            raise ValidationError(f"ROI does not exist: {path}")
        try:
            image = nib.load(path)
            data = np.asanyarray(image.dataobj)
        except Exception as exc:
            raise ValidationError(f"cannot read ROI NIfTI {path}: {exc}") from exc
        if len(image.shape) != 3:
            raise ValidationError(f"ROI must be three-dimensional: {path}")
        if not np.all(np.isfinite(image.affine)):
            raise ValidationError(f"ROI affine contains nonfinite values: {path}")
        if not np.all(np.isfinite(data)):
            raise ValidationError(f"ROI contains nonfinite values: {path}")
        binary = data > 0
        if not np.any(binary):
            raise ValidationError(f"ROI is empty: {path}")
        unique = np.unique(data)
        if unique.size > 2 or not set(float(value) for value in unique).issubset(
            {0.0, 1.0}
        ):
            raise ValidationError(f"ROI must be binary with values 0 and 1: {path}")
        if reference_shape is None:
            reference_shape = tuple(image.shape)
            reference_affine = np.asarray(image.affine, dtype=np.float64)
        elif tuple(image.shape) != reference_shape or not np.allclose(
            image.affine, reference_affine, atol=1e-6, rtol=0
        ):
            raise ValidationError(
                f"all atlas ROIs must share one exact MNI grid; mismatch at {path}"
            )
        hashes[str(path)] = file_sha256(path)
    return hashes


def _implementation_paths(repo_root: Path) -> Iterable[Path]:
    package = repo_root / "my_helper" / "fiber" / "core" / "mrtrix_seed_target"
    for pattern in ("*.py", "schemas/*.json"):
        yield from sorted(package.glob(pattern))
    for path in (
        repo_root
        / "my_helper"
        / "fiber"
        / "core"
        / "tracking"
        / "mh_fiber_prepare_mrtrix_seed_target_subject.m",
        repo_root / "my_helper" / "fiber" / "pipelines" / "mrtrix-seed-target",
    ):
        if path.is_file():
            yield path


def _layer_paths(repo_root: Path, layer: str) -> tuple[Path, ...]:
    package = repo_root / "my_helper" / "fiber" / "core" / "mrtrix_seed_target"
    shared = {
        "config.py",
        "errors.py",
        "identity.py",
        "models.py",
        "schemas/config.schema.json",
        "tools.py",
    }
    layer_names = {
        "preparation": shared
        | {
            "discovery.py",
            "preparation.py",
            "roi.py",
        },
        "tracking": shared
        | {
            "classification.py",
            "state.py",
            "tck.py",
            "tracking.py",
        },
        "publication": shared
        | {
            "cli.py",
            "pipeline.py",
            "publication.py",
            "resources.py",
            "state.py",
        },
    }
    paths = [package / name for name in sorted(layer_names[layer])]
    if layer == "preparation":
        paths.append(
            repo_root
            / "my_helper"
            / "fiber"
            / "core"
            / "tracking"
            / "mh_fiber_prepare_mrtrix_seed_target_subject.m"
        )
    if layer == "tracking":
        paths.extend(
            [
                repo_root
                / "my_helper"
                / "fiber"
                / "core"
                / "seed_target_connectivity"
                / "models.py",
                repo_root
                / "my_helper"
                / "fiber"
                / "core"
                / "seed_target_connectivity"
                / "traversal.py",
            ]
        )
    if layer == "publication":
        paths.append(repo_root / "my_helper" / "fiber" / "pipelines" / "mrtrix-seed-target")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValidationError(
            f"implementation files are missing for {layer}: "
            + ", ".join(str(path) for path in missing)
        )
    return tuple(paths)


def _resource_warnings(config: BatchConfig) -> tuple[str, ...]:
    execution = config.execution
    warnings: list[str] = []
    if (
        execution.subject_workers * execution.preparation_threads_per_subject
        > execution.cpu_budget
    ):
        warnings.append(
            "requested concurrent preparations exceed the CPU budget; the "
            "resource scheduler will reduce attained concurrency"
        )
    if (
        execution.subject_workers
        * execution.seedwide_workers_per_subject
        * execution.mrtrix_threads_per_seedwide_job
        > execution.cpu_budget
    ):
        warnings.append(
            "requested concurrent seed-wide jobs exceed the CPU budget; the "
            "resource scheduler will reduce attained concurrency"
        )
    if (
        execution.subject_workers * execution.preparation_memory_reservation_gb
        > execution.memory_dispatch_capacity_gb
    ):
        warnings.append(
            "requested concurrent preparations exceed the memory dispatch "
            "capacity; the resource scheduler will reduce attained concurrency"
        )
    if (
        execution.subject_workers
        * execution.seedwide_workers_per_subject
        * execution.seedwide_memory_reservation_gb
        > execution.memory_dispatch_capacity_gb
    ):
        warnings.append(
            "requested concurrent seed-wide jobs exceed the memory dispatch "
            "capacity; the resource scheduler will reduce attained concurrency"
        )
    if execution.mrtrix_threads_per_seedwide_job > 1:
        warnings.append(
            "MRtrix jobs use more than one thread; regenerated probabilistic "
            "streamlines may not be byte-identical"
        )
    return tuple(warnings)


def validate_config(path: Path | str) -> ValidationBundle:
    """Resolve the complete batch without creating subject outputs."""

    config = load_config(path)
    source_hashes = _validate_source_rois(config)
    subjects = tuple(discover_subject(subject) for subject in config.subjects)
    tools = resolve_tool_identities(config)
    repo_root = Path(__file__).resolve().parents[4]
    code_hash = implementation_hash(_implementation_paths(repo_root))
    preparation_code_hash = implementation_hash(
        _layer_paths(repo_root, "preparation")
    )
    tracking_code_hash = implementation_hash(_layer_paths(repo_root, "tracking"))
    publication_code_hash = implementation_hash(
        _layer_paths(repo_root, "publication")
    )
    warnings = list(_resource_warnings(config))
    for configured, resolved in zip(config.subjects, subjects, strict=True):
        if configured.subject_dir.name != configured.subject_id:
            warnings.append(
                f"subject id {configured.subject_id!r} differs from directory "
                f"basename {configured.subject_dir.name!r}"
            )
        if not resolved.anchor_to_dwi_transform.name.endswith("44.mat"):
            warnings.append(
                f"subject {resolved.subject_id} explicitly selected a transform "
                "whose filename does not end in 44.mat"
            )
    return ValidationBundle(
        config=config,
        subjects=subjects,
        tools=tools,
        source_roi_hashes=source_hashes,
        code_hash=code_hash,
        preparation_code_hash=preparation_code_hash,
        tracking_code_hash=tracking_code_hash,
        publication_code_hash=publication_code_hash,
        warnings=tuple(warnings),
    )
