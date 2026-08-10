"""Space-aware tractogram transformation with explicit image/point directions."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Iterable, Iterator, Mapping, Sequence
import uuid

import nibabel as nib
import numpy as np
from scipy.ndimage import map_coordinates
from send2trash import send2trash

from .discovery import load_tmat
from .errors import MrtrixSeedTargetError, ValidationError
from .identity import canonical_hash, file_sha256
from .models import BatchConfig, ResolvedSubjectInputs, SeedSpec, ToolIdentity
from .publication import OWNER
from .state import atomic_write_json, read_json
from .tck import (
    iter_tck,
    validate_tck,
    write_generated_tck,
    write_ordinal_subset_tck,
)


DISPLACEMENT_INTENT = 1006
DISPLACEMENT_LAYOUT = "X_Y_Z_1_3"
POINT_BACKEND = "nibabel_trilinear_ras"
PAIRED_FIELD_INVERSE_BACKEND = "nibabel_trilinear_ras_paired_field_inverse"
PAIRED_FIELD_INVERSE_MAX_ITERATIONS = 64
PAIRED_FIELD_INVERSE_RELAXATION = 0.5
PAIRED_FIELD_INVERSE_TOLERANCE_MM = 1e-5
_POINT_FIELD_TRANSFORM_LOCK = threading.Lock()


def _callable_source_hash(
    *functions: object,
    constants: Mapping[str, object],
) -> str:
    """Hash the explicit scientific callables and constants for one component."""

    document = {
        "callables": [
            {
                "module": getattr(function, "__module__", ""),
                "qualname": getattr(function, "__qualname__", ""),
                "source": inspect.getsource(function),
            }
            for function in functions
        ],
        "constants": dict(constants),
    }
    return canonical_hash(document)


@dataclass(frozen=True)
class PointField:
    """One validated RAS world-mm displacement field."""

    path: Path
    image: nib.spatialimages.SpatialImage
    vectors: np.ndarray
    inverse_affine: np.ndarray

    @property
    def spatial_shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.image.shape[:3])


@dataclass
class DomainStats:
    """Mutable bounded summary of production-field domain coverage."""

    total_point_count: int = 0
    inside_domain_point_count: int = 0
    outside_domain_point_count: int = 0
    outside_domain_streamline_count: int = 0
    maximum_voxel_distance_beyond_domain: float = 0.0
    outside_coordinate_min: np.ndarray | None = None
    outside_coordinate_max: np.ndarray | None = None
    paired_field_inverse_solved_point_count: int = 0
    paired_field_inverse_nonconverged_point_count: int = 0
    paired_field_inverse_max_residual_mm: float = 0.0
    unresolved_domain_point_count: int = 0

    def as_mapping(self) -> dict[str, object]:
        return {
            "total_point_count": self.total_point_count,
            "inside_domain_point_count": self.inside_domain_point_count,
            "outside_domain_point_count": self.outside_domain_point_count,
            "outside_domain_streamline_count": self.outside_domain_streamline_count,
            "maximum_voxel_distance_beyond_domain": (
                self.maximum_voxel_distance_beyond_domain
            ),
            "outside_coordinate_min": (
                self.outside_coordinate_min.tolist()
                if self.outside_coordinate_min is not None
                else None
            ),
            "outside_coordinate_max": (
                self.outside_coordinate_max.tolist()
                if self.outside_coordinate_max is not None
                else None
            ),
            "paired_field_inverse_solved_point_count": (
                self.paired_field_inverse_solved_point_count
            ),
            "paired_field_inverse_nonconverged_point_count": (
                self.paired_field_inverse_nonconverged_point_count
            ),
            "paired_field_inverse_max_residual_mm": (
                self.paired_field_inverse_max_residual_mm
            ),
            "unresolved_domain_point_count": self.unresolved_domain_point_count,
        }


def load_point_field(
    path: Path | str,
    *,
    reference_path: Path | str,
    label: str,
) -> PointField:
    """Load one displacement field and validate its complete NIfTI contract."""

    source = Path(path).expanduser().resolve()
    reference_source = Path(reference_path).expanduser().resolve()
    try:
        image = nib.load(source)
        reference = nib.load(reference_source)
    except Exception as exc:
        raise ValidationError(f"cannot load {label}: {exc}") from exc
    if tuple(image.shape[-2:]) != (1, 3) or len(image.shape) != 5:
        raise ValidationError(
            f"{label} must use vector layout (X, Y, Z, 1, 3): {source}"
        )
    if int(image.header["intent_code"]) != DISPLACEMENT_INTENT:
        raise ValidationError(
            f"{label} must use NIfTI displacement intent {DISPLACEMENT_INTENT}: {source}"
        )
    affine = np.asarray(image.affine, dtype=np.float64)
    if not np.all(np.isfinite(affine)) or abs(np.linalg.det(affine[:3, :3])) < 1e-12:
        raise ValidationError(f"{label} has a nonfinite or singular affine: {source}")
    if tuple(image.shape[:3]) != tuple(reference.shape[:3]) or not np.allclose(
        affine, reference.affine, atol=1e-5, rtol=1e-7
    ):
        raise ValidationError(
            f"{label} does not match expected reference grid {reference_source}"
        )
    vectors = np.asarray(image.dataobj[..., 0, :], dtype=np.float32)
    if vectors.shape != (*image.shape[:3], 3) or not np.all(np.isfinite(vectors)):
        raise ValidationError(f"{label} contains invalid displacement vectors: {source}")
    vectors.setflags(write=False)
    return PointField(
        path=source,
        image=image,
        vectors=vectors,
        inverse_affine=np.linalg.inv(affine),
    )


def apply_affine(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply one direct 4x4 RAS world-coordinate affine."""

    values = np.asarray(points, dtype=np.float64)
    transform = np.asarray(matrix, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValidationError("point array must have shape N x 3")
    if transform.shape != (4, 4) or not np.all(np.isfinite(transform)):
        raise ValidationError("point affine must be one finite 4 x 4 matrix")
    return values @ transform[:3, :3].T + transform[:3, 3]


def _domain_mask(voxels: np.ndarray, shape: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    lower_excess = np.maximum(-0.5 - voxels, 0.0)
    upper = np.asarray(shape, dtype=np.float64) - 0.5
    upper_excess = np.maximum(voxels - upper, 0.0)
    excess = np.maximum(lower_excess, upper_excess)
    return np.all(excess == 0.0, axis=1), excess


def _apply_point_field_values(
    values: np.ndarray,
    field: PointField,
    *,
    stats: DomainStats | None = None,
    streamline_offsets: np.ndarray | None = None,
) -> np.ndarray:
    """Apply one already validated point array within the process-local lock."""

    voxels = apply_affine(values, field.inverse_affine)
    inside, excess = _domain_mask(voxels, field.spatial_shape)
    if stats is not None:
        stats.total_point_count += int(values.shape[0])
        stats.inside_domain_point_count += int(np.count_nonzero(inside))
        outside_count = int(np.count_nonzero(~inside))
        stats.outside_domain_point_count += outside_count
        if outside_count:
            outside_values = values[~inside]
            minimum = outside_values.min(axis=0)
            maximum = outside_values.max(axis=0)
            stats.outside_coordinate_min = (
                minimum
                if stats.outside_coordinate_min is None
                else np.minimum(stats.outside_coordinate_min, minimum)
            )
            stats.outside_coordinate_max = (
                maximum
                if stats.outside_coordinate_max is None
                else np.maximum(stats.outside_coordinate_max, maximum)
            )
            stats.maximum_voxel_distance_beyond_domain = max(
                stats.maximum_voxel_distance_beyond_domain,
                float(np.max(np.linalg.norm(excess[~inside], axis=1))),
            )
            if streamline_offsets is not None:
                outside_rows = np.flatnonzero(~inside)
                streamline_rows = np.searchsorted(
                    streamline_offsets[1:], outside_rows, side="right"
                )
                stats.outside_domain_streamline_count += int(
                    np.unique(streamline_rows).size
                )
    if not np.all(inside):
        raise ValidationError(
            f"point_transform_domain_failed: {int(np.count_nonzero(~inside))} "
            f"points fall outside {field.path}"
        )
    coordinates = voxels.T
    displacement = np.column_stack(
        [
            map_coordinates(
                field.vectors[..., axis],
                coordinates,
                order=1,
                mode="nearest",
                prefilter=False,
            )
            for axis in range(3)
        ]
    )
    return values + displacement


def apply_point_field(
    points: np.ndarray,
    field: PointField,
    *,
    stats: DomainStats | None = None,
    streamline_offsets: np.ndarray | None = None,
) -> np.ndarray:
    """Sample stored RAS displacements and add them directly to RAS points."""

    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or not np.all(np.isfinite(values)):
        raise ValidationError("point-field input must be one finite N x 3 array")
    with _POINT_FIELD_TRANSFORM_LOCK:
        return _apply_point_field_values(
            values,
            field,
            stats=stats,
            streamline_offsets=streamline_offsets,
        )


def _sample_point_field_displacement(
    field: PointField,
    voxels: np.ndarray,
) -> np.ndarray:
    """Sample one validated field at already validated voxel coordinates."""

    coordinates = np.asarray(voxels, dtype=np.float64).T
    return np.column_stack(
        [
            map_coordinates(
                field.vectors[..., axis],
                coordinates,
                order=1,
                mode="nearest",
                prefilter=False,
            )
            for axis in range(3)
        ]
    )


def _solve_paired_field_inverse(
    anchor_points: np.ndarray,
    *,
    reverse_field: PointField,
    initial_target_points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve target plus paired displacement equals each anchor point."""

    targets = np.asarray(anchor_points, dtype=np.float64)
    estimates = np.asarray(initial_target_points, dtype=np.float64).copy()
    converged = np.zeros(targets.shape[0], dtype=bool)
    residual_norms = np.full(targets.shape[0], np.inf, dtype=np.float64)
    active = np.ones(targets.shape[0], dtype=bool)
    for iteration in range(PAIRED_FIELD_INVERSE_MAX_ITERATIONS + 1):
        active_rows = np.flatnonzero(active)
        if active_rows.size == 0:
            break
        active_estimates = estimates[active_rows]
        voxels = apply_affine(active_estimates, reverse_field.inverse_affine)
        inside, _excess = _domain_mask(voxels, reverse_field.spatial_shape)
        if not np.all(inside):
            active[active_rows[~inside]] = False
        solve_rows = active_rows[inside]
        if solve_rows.size == 0:
            continue
        displacement = _sample_point_field_displacement(
            reverse_field,
            voxels[inside],
        )
        residual = estimates[solve_rows] + displacement - targets[solve_rows]
        norms = np.linalg.norm(residual, axis=1)
        now_converged = norms <= PAIRED_FIELD_INVERSE_TOLERANCE_MM
        if np.any(now_converged):
            rows = solve_rows[now_converged]
            converged[rows] = True
            active[rows] = False
            residual_norms[rows] = norms[now_converged]
        if iteration == PAIRED_FIELD_INVERSE_MAX_ITERATIONS:
            continue
        update_rows = solve_rows[~now_converged]
        if update_rows.size:
            estimates[update_rows] -= (
                PAIRED_FIELD_INVERSE_RELAXATION * residual[~now_converged]
            )
    return estimates, residual_norms, converged


def _apply_point_field_with_paired_inverse_values(
    values: np.ndarray,
    production_field: PointField,
    reverse_field: PointField,
    *,
    stats: DomainStats,
    streamline_offsets: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the primary field and exactly solve its outside-domain points."""

    voxels = apply_affine(values, production_field.inverse_affine)
    inside, excess = _domain_mask(voxels, production_field.spatial_shape)
    stats.total_point_count += int(values.shape[0])
    stats.inside_domain_point_count += int(np.count_nonzero(inside))
    outside_rows = np.flatnonzero(~inside)
    outside_count = int(outside_rows.size)
    stats.outside_domain_point_count += outside_count
    transformed = np.empty_like(values, dtype=np.float64)
    if np.any(inside):
        transformed[inside] = _apply_point_field_values(
            values[inside],
            production_field,
        )
    if outside_count == 0:
        return transformed

    outside_values = values[outside_rows]
    minimum = outside_values.min(axis=0)
    maximum = outside_values.max(axis=0)
    stats.outside_coordinate_min = (
        minimum
        if stats.outside_coordinate_min is None
        else np.minimum(stats.outside_coordinate_min, minimum)
    )
    stats.outside_coordinate_max = (
        maximum
        if stats.outside_coordinate_max is None
        else np.maximum(stats.outside_coordinate_max, maximum)
    )
    stats.maximum_voxel_distance_beyond_domain = max(
        stats.maximum_voxel_distance_beyond_domain,
        float(np.max(np.linalg.norm(excess[outside_rows], axis=1))),
    )
    if streamline_offsets is not None:
        streamline_rows = np.searchsorted(
            streamline_offsets[1:],
            outside_rows,
            side="right",
        )
        stats.outside_domain_streamline_count += int(np.unique(streamline_rows).size)

    clipped_voxels = np.clip(
        voxels[outside_rows],
        np.zeros(3, dtype=np.float64),
        np.asarray(production_field.spatial_shape, dtype=np.float64) - 1.0,
    )
    initial_target_points = outside_values + _sample_point_field_displacement(
        production_field,
        clipped_voxels,
    )
    solutions, residual_norms, converged = _solve_paired_field_inverse(
        outside_values,
        reverse_field=reverse_field,
        initial_target_points=initial_target_points,
    )
    solved_count = int(np.count_nonzero(converged))
    nonconverged_count = outside_count - solved_count
    stats.paired_field_inverse_solved_point_count += solved_count
    stats.paired_field_inverse_nonconverged_point_count += nonconverged_count
    stats.unresolved_domain_point_count += nonconverged_count
    if solved_count:
        stats.paired_field_inverse_max_residual_mm = max(
            stats.paired_field_inverse_max_residual_mm,
            float(np.max(residual_norms[converged])),
        )
    if nonconverged_count:
        raise ValidationError(
            "point_inverse_solver_failed: "
            f"{nonconverged_count} of {outside_count} outside-primary points "
            "did not converge within the paired field"
        )
    transformed[outside_rows] = solutions
    return transformed


def apply_point_field_with_paired_inverse(
    points: np.ndarray,
    production_field: PointField,
    reverse_field: PointField,
    *,
    stats: DomainStats,
    streamline_offsets: np.ndarray | None = None,
) -> np.ndarray:
    """Use a paired-field inverse only for primary-field outside points."""

    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or not np.all(np.isfinite(values)):
        raise ValidationError("point-field input must be one finite N x 3 array")
    with _POINT_FIELD_TRANSFORM_LOCK:
        return _apply_point_field_with_paired_inverse_values(
            values,
            production_field,
            reverse_field,
            stats=stats,
            streamline_offsets=streamline_offsets,
        )


def streamline_digest(streamline: np.ndarray) -> str:
    """Hash point count plus exact little-endian float32 point bytes."""

    points = np.asarray(streamline, dtype="<f4", order="C")
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
        raise ValidationError("cannot digest an invalid streamline")
    digest = hashlib.sha256()
    digest.update(int(points.shape[0]).to_bytes(8, "little", signed=False))
    digest.update(points.tobytes(order="C"))
    return digest.hexdigest()


def ordered_target_memberships(
    seedwide_path: Path | str,
    target_paths: Mapping[str, Path | str],
) -> tuple[int, dict[str, tuple[int, ...]]]:
    """Map each exact target streamline to its unique seed-wide source ordinal."""

    seed_ordinals: dict[str, int] = {}
    seed_count = 0
    for seed_count, streamline in enumerate(iter_tck(seedwide_path), start=1):
        digest = streamline_digest(streamline)
        if digest in seed_ordinals:
            raise ValidationError(
                f"ambiguous duplicated seed-wide streamline digest in {seedwide_path}"
            )
        seed_ordinals[digest] = seed_count - 1
    memberships: dict[str, tuple[int, ...]] = {}
    for key, target_path in target_paths.items():
        ordinals: list[int] = []
        previous = -1
        for streamline in iter_tck(target_path):
            digest = streamline_digest(streamline)
            if digest not in seed_ordinals:
                raise ValidationError(
                    f"target streamline is missing from seed-wide TCK: {target_path}"
                )
            ordinal = seed_ordinals[digest]
            if ordinal <= previous:
                raise ValidationError(
                    f"target TCK is duplicated or out of seed-wide order: {target_path}"
                )
            ordinals.append(ordinal)
            previous = ordinal
        memberships[str(key)] = tuple(ordinals)
    return seed_count, memberships


def _buffered_transformed_streamlines(
    input_path: Path | str,
    *,
    b0_to_anchor: np.ndarray,
    production_field: PointField,
    stats: DomainStats,
    point_budget: int,
) -> Iterator[np.ndarray]:
    buffer: list[np.ndarray] = []
    point_count = 0

    def flush() -> Iterable[np.ndarray]:
        if not buffer:
            return ()
        offsets = np.zeros(len(buffer) + 1, dtype=np.int64)
        for index, streamline in enumerate(buffer):
            offsets[index + 1] = offsets[index] + streamline.shape[0]
        points = np.concatenate(buffer, axis=0)
        anchor = apply_affine(points, b0_to_anchor)
        transformed = apply_point_field(
            anchor,
            production_field,
            stats=stats,
            streamline_offsets=offsets,
        )
        return (
            transformed[offsets[index] : offsets[index + 1]].astype(
                np.float32, copy=False
            )
            for index in range(len(buffer))
        )

    for streamline in iter_tck(input_path):
        points = np.asarray(streamline, dtype=np.float32)
        if buffer and point_count + points.shape[0] > point_budget:
            yield from flush()
            buffer = []
            point_count = 0
        buffer.append(points)
        point_count += int(points.shape[0])
    yield from flush()


def transform_seedwide_and_targets(
    *,
    native_seedwide: Path,
    native_targets: Mapping[str, Path],
    target_seedwide: Path,
    target_targets: Mapping[str, Path],
    b0_to_anchor_transform: Path,
    production_field: PointField,
    point_budget: int = 500_000,
    stats: DomainStats | None = None,
) -> tuple[DomainStats, dict[str, tuple[int, ...]]]:
    """Transform a seed-wide TCK once and reconstruct its exact ordered subsets."""

    if point_budget <= 0:
        raise ValidationError("point budget must be positive")
    seed_count, memberships = ordered_target_memberships(
        native_seedwide, native_targets
    )
    if set(memberships) != set(target_targets):
        raise ValidationError("native and target-space target keys differ")
    matrix = load_tmat(b0_to_anchor_transform)
    realized_stats = stats if stats is not None else DomainStats()

    def generate() -> Iterator[np.ndarray]:
        yield from _buffered_transformed_streamlines(
            native_seedwide,
            b0_to_anchor=matrix,
            production_field=production_field,
            stats=realized_stats,
            point_budget=point_budget,
        )

    write_generated_tck(generate, target_seedwide, seed_count)
    for key, ordinals in memberships.items():
        write_ordinal_subset_tck(
            target_seedwide,
            ordinals,
            target_targets[key],
        )
    return realized_stats, memberships


def _buffered_transformed_streamlines_with_paired_inverse(
    input_path: Path | str,
    *,
    b0_to_anchor: np.ndarray,
    production_field: PointField,
    reverse_field: PointField,
    stats: DomainStats,
    point_budget: int,
) -> Iterator[np.ndarray]:
    buffer: list[np.ndarray] = []
    point_count = 0

    def flush() -> Iterable[np.ndarray]:
        if not buffer:
            return ()
        offsets = np.zeros(len(buffer) + 1, dtype=np.int64)
        for index, streamline in enumerate(buffer):
            offsets[index + 1] = offsets[index] + streamline.shape[0]
        points = np.concatenate(buffer, axis=0)
        anchor = apply_affine(points, b0_to_anchor)
        transformed = apply_point_field_with_paired_inverse(
            anchor,
            production_field,
            reverse_field,
            stats=stats,
            streamline_offsets=offsets,
        )
        return (
            transformed[offsets[index] : offsets[index + 1]].astype(
                np.float32,
                copy=False,
            )
            for index in range(len(buffer))
        )

    for streamline in iter_tck(input_path):
        points = np.asarray(streamline, dtype=np.float32)
        if buffer and point_count + points.shape[0] > point_budget:
            yield from flush()
            buffer = []
            point_count = 0
        buffer.append(points)
        point_count += int(points.shape[0])
    yield from flush()


def transform_seedwide_and_targets_with_paired_inverse(
    *,
    native_seedwide: Path,
    native_targets: Mapping[str, Path],
    target_seedwide: Path,
    target_targets: Mapping[str, Path],
    b0_to_anchor_transform: Path,
    production_field: PointField,
    reverse_field: PointField,
    point_budget: int = 500_000,
    stats: DomainStats | None = None,
) -> tuple[DomainStats, dict[str, tuple[int, ...]]]:
    """Transform once while solving only primary-field outside points."""

    if point_budget <= 0:
        raise ValidationError("point budget must be positive")
    seed_count, memberships = ordered_target_memberships(
        native_seedwide,
        native_targets,
    )
    if set(memberships) != set(target_targets):
        raise ValidationError("native and target-space target keys differ")
    matrix = load_tmat(b0_to_anchor_transform)
    realized_stats = stats if stats is not None else DomainStats()

    def generate() -> Iterator[np.ndarray]:
        yield from _buffered_transformed_streamlines_with_paired_inverse(
            native_seedwide,
            b0_to_anchor=matrix,
            production_field=production_field,
            reverse_field=reverse_field,
            stats=realized_stats,
            point_budget=point_budget,
        )

    write_generated_tck(generate, target_seedwide, seed_count)
    for key, ordinals in memberships.items():
        write_ordinal_subset_tck(
            target_seedwide,
            ordinals,
            target_targets[key],
        )
    return realized_stats, memberships


def _native_paths(
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    root = subject.output_root / "tractograms" / "native"
    for seed in config.atlas.seeds:
        seed_root = root / seed.side / seed.roi_id
        paths[f"{seed.key}/seedwide"] = seed_root / "seedwide.tck"
        for target in seed.targets:
            paths[f"{seed.key}/target/{target.key}"] = (
                seed_root / "targets" / target.side / f"{target.roi_id}.tck"
            )
    return paths


def verify_native_publication(
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    *,
    tckinfo: Path,
) -> dict[str, object]:
    """Verify the exact native artifact set in place without restaging it."""

    state_path = subject.output_root / "work" / "state.json"
    state = read_json(state_path, default={})
    if not isinstance(state, dict) or state.get("owner") != OWNER:
        raise ValidationError(f"native publication state is missing or foreign: {state_path}")
    expected = _native_paths(config, subject)
    records = {
        str(record.get("semantic_key")): record
        for record in state.get("published_artifacts", [])
        if record.get("coordinate_space") == "native"
    }
    if set(records) != set(expected):
        missing = sorted(set(expected) - set(records))
        extra = sorted(set(records) - set(expected))
        raise ValidationError(
            f"native artifact semantics differ for {subject.subject_id}; "
            f"missing={missing}, extra={extra}"
        )
    for key, path in expected.items():
        record = records[key]
        if Path(str(record.get("path", ""))).resolve() != path.resolve():
            raise ValidationError(f"native artifact path mismatch for {key}: {path}")
        if not path.is_file() or file_sha256(path) != record.get("sha256"):
            raise ValidationError(f"native artifact hash mismatch for {key}: {path}")
        validate_tck(
            path,
            tckinfo,
            expected_count=int(record["streamline_count"]),
        )
    return state


def coordinate_implementation_hash() -> str:
    """Return the code identity for target-space coordinate byte generation."""

    return _callable_source_hash(
        load_tmat,
        iter_tck,
        write_generated_tck,
        write_ordinal_subset_tck,
        load_point_field,
        apply_affine,
        _domain_mask,
        _apply_point_field_values,
        apply_point_field,
        streamline_digest,
        ordered_target_memberships,
        _buffered_transformed_streamlines,
        transform_seedwide_and_targets,
        constants={
            "displacement_intent": DISPLACEMENT_INTENT,
            "displacement_layout": DISPLACEMENT_LAYOUT,
            "point_backend": POINT_BACKEND,
        },
    )


def coordinate_fingerprint(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    state: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    """Return the semantic fingerprint for target-space coordinate bytes."""

    native = [
        {
            "semantic_key": record["semantic_key"],
            "sha256": record["sha256"],
            "streamline_count": int(record["streamline_count"]),
        }
        for record in state.get("published_artifacts", [])
        if record.get("coordinate_space") == "native"
    ]
    native.sort(key=lambda item: str(item["semantic_key"]))
    document: dict[str, object] = {
        "target_space": config.atlas.space,
        "native_artifacts": native,
        "b0_to_anchor_transform": {
            "path": str(subject.b0_to_anchor_transform),
            "sha256": file_sha256(subject.b0_to_anchor_transform),
        },
        "target_to_anchor_image_deformation": {
            "path": str(subject.target_to_anchor_image_deformation),
            "sha256": file_sha256(subject.target_to_anchor_image_deformation),
            "point_direction": "anchor_to_target",
        },
        "backend": POINT_BACKEND,
        "implementation_hash": coordinate_implementation_hash(),
    }
    return canonical_hash(document), document


def paired_field_inverse_implementation_hash() -> str:
    """Return the isolated identity of outside-primary coordinate solving."""

    return _callable_source_hash(
        load_tmat,
        iter_tck,
        write_generated_tck,
        write_ordinal_subset_tck,
        load_point_field,
        apply_affine,
        _domain_mask,
        _apply_point_field_values,
        _sample_point_field_displacement,
        _solve_paired_field_inverse,
        _apply_point_field_with_paired_inverse_values,
        apply_point_field_with_paired_inverse,
        streamline_digest,
        ordered_target_memberships,
        _buffered_transformed_streamlines_with_paired_inverse,
        transform_seedwide_and_targets_with_paired_inverse,
        constants={
            "displacement_intent": DISPLACEMENT_INTENT,
            "displacement_layout": DISPLACEMENT_LAYOUT,
            "point_backend": PAIRED_FIELD_INVERSE_BACKEND,
            "max_iterations": PAIRED_FIELD_INVERSE_MAX_ITERATIONS,
            "relaxation": PAIRED_FIELD_INVERSE_RELAXATION,
            "tolerance_mm": PAIRED_FIELD_INVERSE_TOLERANCE_MM,
        },
    )


def paired_field_inverse_fingerprint(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    state: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    """Return the coordinate identity for paired-field outside-point solving."""

    _primary_identity, primary_document = coordinate_fingerprint(
        config=config,
        subject=subject,
        state=state,
    )
    document = dict(primary_document)
    document["anchor_to_target_image_deformation"] = {
        "path": str(subject.anchor_to_target_image_deformation),
        "sha256": file_sha256(subject.anchor_to_target_image_deformation),
        "point_direction": "target_to_anchor",
        "role": "paired_field_numerical_inverse",
    }
    document["backend"] = PAIRED_FIELD_INVERSE_BACKEND
    document["implementation_hash"] = paired_field_inverse_implementation_hash()
    return canonical_hash(document), document


def roundtrip_implementation_hash() -> str:
    """Return the code identity for reverse and external-reference QC."""

    return _callable_source_hash(
        _sample_streamline_points,
        ants_reference_transform,
        _roundtrip_qc,
        constants={
            "external_point_convention": "LPS_world_mm",
            "input_point_convention": "RAS_world_mm",
        },
    )


def roundtrip_fingerprint(
    *,
    coordinate_identity: str,
    subject: ResolvedSubjectInputs,
    ants: ToolIdentity,
) -> tuple[str, dict[str, object]]:
    """Return the semantic fingerprint for paired reverse and parity QC."""

    document: dict[str, object] = {
        "coordinate_fingerprint": coordinate_identity,
        "anchor_to_b0_transform": {
            "path": str(subject.anchor_to_b0_transform),
            "sha256": file_sha256(subject.anchor_to_b0_transform),
        },
        "anchor_to_target_image_deformation": {
            "path": str(subject.anchor_to_target_image_deformation),
            "sha256": file_sha256(subject.anchor_to_target_image_deformation),
            "point_direction": "target_to_anchor",
        },
        "external_reference": {
            "path": str(ants.executable),
            "version": ants.version,
            "point_convention": "LPS_world_mm",
        },
        "implementation_hash": roundtrip_implementation_hash(),
    }
    return canonical_hash(document), document


def _target_side_paths(
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    side: str,
    *,
    root: Path,
) -> tuple[Path, dict[str, Path]]:
    seeds = [seed for seed in config.atlas.seeds if seed.side == side]
    if len(seeds) != 1:
        raise ValidationError(f"expected exactly one configured seed for side {side}")
    seed = seeds[0]
    seed_root = root / side / seed.roi_id
    targets = {
        target.key: seed_root / "targets" / target.side / f"{target.roi_id}.tck"
        for target in seed.targets
    }
    return seed_root / "seedwide.tck", targets


def _sample_streamline_points(
    path: Path,
    *,
    streamline_count: int,
    sample_count: int = 200,
) -> np.ndarray:
    realized = min(int(streamline_count), int(sample_count))
    if realized <= 0:
        raise ValidationError(f"cannot sample an empty seed-wide TCK: {path}")
    ordinals = {
        int(np.floor((index + 0.5) * streamline_count / realized))
        for index in range(realized)
    }
    points: list[np.ndarray] = []
    for index, streamline in enumerate(iter_tck(path)):
        if index in ordinals:
            values = np.asarray(streamline, dtype=np.float64)
            points.append(values[values.shape[0] // 2])
    if len(points) != realized:
        raise ValidationError(f"could not collect deterministic point samples from {path}")
    return np.asarray(points, dtype=np.float64)


def ants_reference_transform(
    points_ras: np.ndarray,
    *,
    field_path: Path,
    executable: Path,
    work_dir: Path,
) -> np.ndarray:
    """Apply the external ANTs LPS point reference to deterministic RAS samples."""

    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "ants_reference_input.csv"
    output_path = work_dir / "ants_reference_output.csv"
    lps = np.asarray(points_ras, dtype=np.float64).copy()
    lps[:, :2] *= -1.0
    with input_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("x", "y", "z", "t"))
        for point in lps:
            writer.writerow((*[format(value, ".17g") for value in point], "0"))
    result = subprocess.run(
        [
            str(executable),
            "-d",
            "3",
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-t",
            f"[{field_path},0]",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=300,
    )
    (work_dir / "ants_reference.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0 or not output_path.is_file():
        raise ValidationError(
            f"antsApplyTransformsToPoints reference failed: {result.stdout.strip()}"
        )
    rows: list[list[float]] = []
    with output_path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append([float(row[name]) for name in ("x", "y", "z")])
    if len(rows) != len(points_ras):
        raise ValidationError("ANTs reference returned an unexpected point count")
    ras = np.asarray(rows, dtype=np.float64)
    ras[:, :2] *= -1.0
    return ras


def _roundtrip_qc(
    *,
    native_seedwide: Path,
    streamline_count: int,
    subject: ResolvedSubjectInputs,
    production_field: PointField,
    reverse_field: PointField,
    ants: ToolIdentity,
    work_dir: Path,
) -> dict[str, object]:
    b0_to_anchor = load_tmat(subject.b0_to_anchor_transform)
    anchor_to_b0 = load_tmat(subject.anchor_to_b0_transform)
    product_error = max(
        float(np.max(np.abs(b0_to_anchor @ anchor_to_b0 - np.eye(4)))),
        float(np.max(np.abs(anchor_to_b0 @ b0_to_anchor - np.eye(4)))),
    )
    if product_error > 1e-8:
        raise ValidationError(
            f"paired b0/anchor matrices are not inverse: max error {product_error:.6g}"
        )
    native = _sample_streamline_points(
        native_seedwide, streamline_count=streamline_count
    )
    anchor = apply_affine(native, b0_to_anchor)
    target = apply_point_field(anchor, production_field)
    parity_count = min(16, len(anchor))
    ants_target = ants_reference_transform(
        anchor[:parity_count],
        field_path=production_field.path,
        executable=ants.executable,
        work_dir=work_dir,
    )
    parity_error = np.linalg.norm(target[:parity_count] - ants_target, axis=1)
    parity_max = float(np.max(parity_error))
    if parity_max > 1e-4:
        raise ValidationError(
            f"all-RAS production mapping differs from ANTs: max error {parity_max:.6g} mm"
        )
    restored_anchor = apply_point_field(target, reverse_field)
    restored_native = apply_affine(restored_anchor, anchor_to_b0)
    errors = np.linalg.norm(restored_native - native, axis=1)
    metrics = {
        "sample_count": int(errors.size),
        "median_mm": float(np.median(errors)),
        "p95_mm": float(np.percentile(errors, 95)),
        "max_mm": float(np.max(errors)),
        "matrix_inverse_max_abs_error": product_error,
        "ants_parity_sample_count": parity_count,
        "ants_parity_max_mm": parity_max,
    }
    if (
        metrics["median_mm"] > 0.05
        or metrics["p95_mm"] > 0.2
        or metrics["max_mm"] > 0.5
    ):
        raise ValidationError(f"round-trip QC thresholds failed: {metrics}")
    return metrics


def _target_records(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    side: str,
    final_seedwide: Path,
    final_targets: Mapping[str, Path],
    native_records: Mapping[str, Mapping[str, object]],
    coordinate_identity: str,
    coordinate_document: Mapping[str, object],
    roundtrip_identity: str,
    roundtrip_document: Mapping[str, object],
    domain_stats: DomainStats,
    roundtrip_qc: Mapping[str, object],
    point_backend: str = POINT_BACKEND,
) -> list[dict[str, object]]:
    seed = next(seed for seed in config.atlas.seeds if seed.side == side)
    records: list[dict[str, object]] = []
    keys_and_paths = [(f"{seed.key}/seedwide", final_seedwide)] + [
        (f"{seed.key}/target/{target.key}", final_targets[target.key])
        for target in seed.targets
    ]
    for semantic_key, path in keys_and_paths:
        native = native_records[semantic_key]
        records.append(
            {
                "semantic_key": semantic_key,
                "coordinate_space": config.atlas.space,
                "path": str(path),
                "sha256": "",
                "streamline_count": int(native["streamline_count"]),
                "source_native_sha256": native["sha256"],
                "coordinate_fingerprint": coordinate_identity,
                "roundtrip_qc_fingerprint": roundtrip_identity,
                "coordinate_identity_document": dict(coordinate_document),
                "roundtrip_identity_document": dict(roundtrip_document),
                "domain_stats": domain_stats.as_mapping(),
                "roundtrip_qc": dict(roundtrip_qc),
                "production_point_direction": "anchor_to_target",
                "bulk_point_backend": point_backend,
                "bulk_input_point_convention": "RAS_world_mm",
                "field_voxel_lookup": "inverse_nifti_affine",
                "displacement_nifti_intent": DISPLACEMENT_INTENT,
                "displacement_vector_layout": DISPLACEMENT_LAYOUT,
                "displacement_storage_convention": "RAS_world_mm",
                "external_reference_backend": "antsApplyTransformsToPoints",
                "external_reference_point_convention": "LPS_world_mm",
            }
        )
    return records


def _recover_target_space_intent(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    seed: SeedSpec,
    state: dict[str, object],
    state_path: Path,
    tckinfo: Path,
    coordinate_identity: str,
    roundtrip_identity: str,
    final_side_root: Path,
) -> bool:
    """Recover one interrupted side publication using its recorded intent."""

    intent = state.get("target_space_intent", {})
    if not isinstance(intent, Mapping) or not intent:
        return False
    if intent.get("side") != seed.side:
        return False
    records = intent.get("artifacts", [])
    if not isinstance(records, list) or any(
        not isinstance(record, Mapping) for record in records
    ):
        raise ValidationError(f"invalid target-space intent: {state_path}")
    expected_semantics = {
        f"{seed.key}/seedwide",
        *(f"{seed.key}/target/{target.key}" for target in seed.targets),
    }
    expected_seedwide, expected_targets = _target_side_paths(
        config,
        subject,
        seed.side,
        root=subject.output_root / "tractograms" / config.atlas.space,
    )
    expected_paths = {
        str(expected_seedwide.resolve()),
        *(str(path.resolve()) for path in expected_targets.values()),
    }
    record_semantics = {str(record.get("semantic_key", "")) for record in records}
    record_paths = {
        str(Path(str(record.get("path", ""))).resolve()) for record in records
    }
    if record_semantics != expected_semantics or record_paths != expected_paths:
        raise ValidationError(f"target-space intent contract mismatch: {state_path}")
    if any(
        record.get("coordinate_space") != config.atlas.space
        or record.get("coordinate_fingerprint") != coordinate_identity
        or record.get("roundtrip_qc_fingerprint") != roundtrip_identity
        for record in records
    ):
        raise ValidationError(f"target-space intent fingerprint mismatch: {state_path}")

    complete = True
    for record in records:
        artifact_path = Path(str(record["path"]))
        if not artifact_path.is_file() or file_sha256(artifact_path) != record.get(
            "sha256"
        ):
            complete = False
            break
        try:
            validate_tck(
                artifact_path,
                tckinfo,
                expected_count=int(record["streamline_count"]),
            )
        except MrtrixSeedTargetError:
            complete = False
            break
    if complete:
        prior_artifacts = [
            record
            for record in state.get("published_artifacts", [])
            if not (
                record.get("coordinate_space") == config.atlas.space
                and str(record.get("semantic_key", "")).startswith(f"{seed.key}/")
            )
        ]
        state["published_artifacts"] = [*prior_artifacts, *records]
        first = records[0]
        state.setdefault("target_space_sides", {})[seed.side] = {
            "coordinate_fingerprint": coordinate_identity,
            "roundtrip_qc_fingerprint": roundtrip_identity,
            "domain_stats": first.get("domain_stats", {}),
            "roundtrip_qc": first.get("roundtrip_qc", {}),
        }
        state["target_space_intent"] = {}
        atomic_write_json(state_path, state)
        return True

    transaction_id = str(intent.get("transaction_id", ""))
    if len(transaction_id) != 32 or any(
        character not in "0123456789abcdef" for character in transaction_id
    ):
        raise ValidationError(f"invalid target-space transaction id: {state_path}")
    rollback = subject.output_root / "work" / "rollback" / transaction_id / seed.side
    if final_side_root.exists():
        actual_paths = {
            str(path.resolve())
            for path in final_side_root.rglob("*")
            if path.is_file() and not path.name.startswith("._")
        }
        if not actual_paths.issubset(expected_paths):
            raise ValidationError(
                f"foreign target-space path blocks intent recovery: {final_side_root}"
            )
        send2trash(str(final_side_root))
    if rollback.exists():
        final_side_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(rollback, final_side_root)
    state["target_space_intent"] = {}
    state["status"] = "native_complete"
    atomic_write_json(state_path, state)
    return False


def convert_subject_target_space(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    tckinfo: Path,
    ants: ToolIdentity,
    code_hash: str,
) -> dict[str, object]:
    """Generate, validate, and atomically publish each configured target-space side."""

    state_path = subject.output_root / "work" / "state.json"
    state = verify_native_publication(config, subject, tckinfo=tckinfo)
    primary_coordinate_identity, primary_coordinate_document = coordinate_fingerprint(
        config=config,
        subject=subject,
        state=state,
    )
    inverse_coordinate_identity, inverse_coordinate_document = (
        paired_field_inverse_fingerprint(
            config=config,
            subject=subject,
            state=state,
        )
    )
    primary_roundtrip_identity, primary_roundtrip_document = roundtrip_fingerprint(
        coordinate_identity=primary_coordinate_identity,
        subject=subject,
        ants=ants,
    )
    inverse_roundtrip_identity, inverse_roundtrip_document = roundtrip_fingerprint(
        coordinate_identity=inverse_coordinate_identity,
        subject=subject,
        ants=ants,
    )
    coordinate_candidates = {
        primary_coordinate_identity: (
            primary_coordinate_document,
            primary_roundtrip_identity,
            primary_roundtrip_document,
            POINT_BACKEND,
        ),
        inverse_coordinate_identity: (
            inverse_coordinate_document,
            inverse_roundtrip_identity,
            inverse_roundtrip_document,
            PAIRED_FIELD_INVERSE_BACKEND,
        ),
    }
    state["space_conversion_module_hash"] = code_hash
    target_root = subject.output_root / "tractograms" / config.atlas.space
    target_reference = config.atlas.seeds[0].path
    production_field = load_point_field(
        subject.target_to_anchor_image_deformation,
        reference_path=subject.anchor_native_reference,
        label="production anchor-to-target point field",
    )
    reverse_field = load_point_field(
        subject.anchor_to_target_image_deformation,
        reference_path=target_reference,
        label="reverse-QC target-to-anchor point field",
    )
    native_records = {
        str(record["semantic_key"]): record
        for record in state["published_artifacts"]
        if record.get("coordinate_space") == "native"
    }
    completed_sides: list[str] = []
    side_coordinate_fingerprints: dict[str, str] = {}
    side_roundtrip_fingerprints: dict[str, str] = {}
    for seed in config.atlas.seeds:
        side = seed.side
        final_seedwide, final_targets = _target_side_paths(
            config, subject, side, root=target_root
        )
        final_side_root = target_root / side
        intent = state.get("target_space_intent", {})
        intent_records = intent.get("artifacts", []) if isinstance(intent, Mapping) else []
        intent_coordinate_identity = (
            str(intent_records[0].get("coordinate_fingerprint", ""))
            if intent_records and isinstance(intent_records[0], Mapping)
            else primary_coordinate_identity
        )
        if intent_coordinate_identity not in coordinate_candidates:
            raise ValidationError(
                f"target-space intent has an unknown coordinate fingerprint: {state_path}"
            )
        (
            _intent_coordinate_document,
            intent_roundtrip_identity,
            _intent_roundtrip_document,
            _intent_backend,
        ) = coordinate_candidates[intent_coordinate_identity]
        if _recover_target_space_intent(
            config=config,
            subject=subject,
            seed=seed,
            state=state,
            state_path=state_path,
            tckinfo=tckinfo,
            coordinate_identity=intent_coordinate_identity,
            roundtrip_identity=intent_roundtrip_identity,
            final_side_root=final_side_root,
        ):
            side_coordinate_fingerprints[side] = intent_coordinate_identity
            side_roundtrip_fingerprints[side] = intent_roundtrip_identity
            completed_sides.append(side)
            continue
        expected_records = [
            record
            for record in state.get("published_artifacts", [])
            if record.get("coordinate_space") == config.atlas.space
            and str(record.get("semantic_key", "")).startswith(f"{seed.key}/")
        ]
        reusable_identity = None
        if len(expected_records) == 1 + len(seed.targets):
            for candidate_identity, candidate_values in coordinate_candidates.items():
                candidate_roundtrip_identity = candidate_values[1]
                if all(
                    record.get("coordinate_fingerprint") == candidate_identity
                    and record.get("roundtrip_qc_fingerprint")
                    == candidate_roundtrip_identity
                    and Path(str(record["path"])).is_file()
                    and file_sha256(Path(str(record["path"]))) == record["sha256"]
                    for record in expected_records
                ):
                    reusable_identity = candidate_identity
                    break
        if reusable_identity is not None:
            for record in expected_records:
                validate_tck(
                    Path(str(record["path"])),
                    tckinfo,
                    expected_count=int(record["streamline_count"]),
                )
            side_coordinate_fingerprints[side] = reusable_identity
            side_roundtrip_fingerprints[side] = coordinate_candidates[
                reusable_identity
            ][1]
            completed_sides.append(side)
            continue

        coordinate_identity = primary_coordinate_identity
        coordinate_document = primary_coordinate_document
        roundtrip_identity = primary_roundtrip_identity
        roundtrip_document = primary_roundtrip_document
        point_backend = POINT_BACKEND

        transaction_id = uuid.uuid4().hex
        transaction_root = (
            subject.output_root
            / "work"
            / "staging"
            / f"target-space-{config.atlas.space}-{side}-{transaction_id}"
        )
        staged_root = transaction_root / config.atlas.space
        staged_seedwide, staged_targets = _target_side_paths(
            config, subject, side, root=staged_root
        )
        native_seedwide, native_targets = _target_side_paths(
            config,
            subject,
            side,
            root=subject.output_root / "tractograms" / "native",
        )
        domain_stats = DomainStats()
        try:
            domain_stats, _memberships = transform_seedwide_and_targets(
                native_seedwide=native_seedwide,
                native_targets=native_targets,
                target_seedwide=staged_seedwide,
                target_targets=staged_targets,
                b0_to_anchor_transform=subject.b0_to_anchor_transform,
                production_field=production_field,
                stats=domain_stats,
            )
        except MrtrixSeedTargetError as exc:
            if "point_transform_domain_failed:" not in str(exc):
                raise
            state["status"] = "transform_domain_resolving"
            state["target_space_failure"] = {
                "side": side,
                "reason": str(exc),
                "primary_domain_stats_at_detection": domain_stats.as_mapping(),
                "resolution": "paired_field_numerical_inverse",
            }
            atomic_write_json(state_path, state)
            coordinate_identity = inverse_coordinate_identity
            coordinate_document = inverse_coordinate_document
            roundtrip_identity = inverse_roundtrip_identity
            roundtrip_document = inverse_roundtrip_document
            point_backend = PAIRED_FIELD_INVERSE_BACKEND
            transaction_id = uuid.uuid4().hex
            transaction_root = (
                subject.output_root
                / "work"
                / "staging"
                / f"target-space-{config.atlas.space}-{side}-{transaction_id}"
            )
            staged_root = transaction_root / config.atlas.space
            staged_seedwide, staged_targets = _target_side_paths(
                config,
                subject,
                side,
                root=staged_root,
            )
            domain_stats = DomainStats()
            try:
                domain_stats, _memberships = (
                    transform_seedwide_and_targets_with_paired_inverse(
                        native_seedwide=native_seedwide,
                        native_targets=native_targets,
                        target_seedwide=staged_seedwide,
                        target_targets=staged_targets,
                        b0_to_anchor_transform=subject.b0_to_anchor_transform,
                        production_field=production_field,
                        reverse_field=reverse_field,
                        stats=domain_stats,
                    )
                )
            except MrtrixSeedTargetError as inverse_exc:
                state["status"] = "transform_domain_failed"
                state["target_space_failure"] = {
                    "side": side,
                    "reason": str(inverse_exc),
                    "domain_stats": domain_stats.as_mapping(),
                    "resolution": "paired_field_numerical_inverse",
                }
                atomic_write_json(state_path, state)
                raise
        paths = [staged_seedwide, *staged_targets.values()]
        semantic_keys = [f"{seed.key}/seedwide", *[
            f"{seed.key}/target/{target.key}" for target in seed.targets
        ]]
        for semantic_key, path in zip(semantic_keys, paths, strict=True):
            validate_tck(
                path,
                tckinfo,
                expected_count=int(native_records[semantic_key]["streamline_count"]),
                full_coordinate_check=True,
            )
        roundtrip_qc = _roundtrip_qc(
            native_seedwide=native_seedwide,
            streamline_count=int(native_records[f"{seed.key}/seedwide"]["streamline_count"]),
            subject=subject,
            production_field=production_field,
            reverse_field=reverse_field,
            ants=ants,
            work_dir=transaction_root / "qc",
        )
        staged_side_root = staged_root / side
        desired_records = _target_records(
            config=config,
            subject=subject,
            side=side,
            final_seedwide=final_seedwide,
            final_targets=final_targets,
            native_records=native_records,
            coordinate_identity=coordinate_identity,
            coordinate_document=coordinate_document,
            roundtrip_identity=roundtrip_identity,
            roundtrip_document=roundtrip_document,
            domain_stats=domain_stats,
            roundtrip_qc=roundtrip_qc,
            point_backend=point_backend,
        )
        for record, staged_path in zip(desired_records, paths, strict=True):
            record["sha256"] = file_sha256(staged_path)
        state["status"] = "target_space_transforming"
        state["target_space_intent"] = {
            "transaction_id": transaction_id,
            "side": side,
            "artifacts": desired_records,
        }
        atomic_write_json(state_path, state)
        rollback = (
            subject.output_root / "work" / "rollback" / transaction_id / side
        )
        if final_side_root.exists():
            owned_paths = {str(record["path"]) for record in expected_records}
            actual_paths = {
                str(path)
                for path in final_side_root.rglob("*")
                if path.is_file() and not path.name.startswith("._")
            }
            if actual_paths != owned_paths:
                raise ValidationError(
                    f"foreign target-space path blocks side publication: {final_side_root}"
                )
            rollback.parent.mkdir(parents=True, exist_ok=True)
            os.replace(final_side_root, rollback)
        final_side_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(staged_side_root, final_side_root)
            for record in desired_records:
                path = Path(str(record["path"]))
                if not path.is_file() or file_sha256(path) != record["sha256"]:
                    raise ValidationError(f"target-space publication hash failed: {path}")
        except BaseException:
            if final_side_root.exists():
                shutil.rmtree(final_side_root)
            if rollback.exists():
                os.replace(rollback, final_side_root)
            raise
        prior_artifacts = [
            record
            for record in state.get("published_artifacts", [])
            if not (
                record.get("coordinate_space") == config.atlas.space
                and str(record.get("semantic_key", "")).startswith(f"{seed.key}/")
            )
        ]
        state["published_artifacts"] = [*prior_artifacts, *desired_records]
        state["target_space_intent"] = {}
        state.setdefault("target_space_sides", {})[side] = {
            "coordinate_fingerprint": coordinate_identity,
            "roundtrip_qc_fingerprint": roundtrip_identity,
            "domain_stats": domain_stats.as_mapping(),
            "roundtrip_qc": roundtrip_qc,
        }
        side_coordinate_fingerprints[side] = coordinate_identity
        side_roundtrip_fingerprints[side] = roundtrip_identity
        atomic_write_json(state_path, state)
        if rollback.exists():
            send2trash(str(rollback))
        if transaction_root.exists():
            try:
                send2trash(str(transaction_root))
            except Exception as exc:
                state.setdefault("cleanup_pending", []).append(
                    {
                        "path": str(transaction_root),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                atomic_write_json(state_path, state)
        completed_sides.append(side)
    state["status"] = "target_space_complete"
    state["target_space"] = config.atlas.space
    state["coordinate_fingerprints_by_side"] = side_coordinate_fingerprints
    state["roundtrip_qc_fingerprints_by_side"] = side_roundtrip_fingerprints
    unique_coordinate_fingerprints = set(side_coordinate_fingerprints.values())
    unique_roundtrip_fingerprints = set(side_roundtrip_fingerprints.values())
    if len(unique_coordinate_fingerprints) == 1:
        state["coordinate_fingerprint"] = next(iter(unique_coordinate_fingerprints))
    else:
        state.pop("coordinate_fingerprint", None)
    if len(unique_roundtrip_fingerprints) == 1:
        state["roundtrip_qc_fingerprint"] = next(iter(unique_roundtrip_fingerprints))
    else:
        state.pop("roundtrip_qc_fingerprint", None)
    state["target_space_intent"] = {}
    state.pop("target_space_failure", None)
    atomic_write_json(state_path, state)
    return {
        "status": "target_space_complete",
        "subject_id": subject.subject_id,
        "target_space": config.atlas.space,
        "completed_sides": completed_sides,
        "coordinate_fingerprint": state.get("coordinate_fingerprint"),
        "roundtrip_qc_fingerprint": state.get("roundtrip_qc_fingerprint"),
        "coordinate_fingerprints_by_side": side_coordinate_fingerprints,
        "roundtrip_qc_fingerprints_by_side": side_roundtrip_fingerprints,
    }
