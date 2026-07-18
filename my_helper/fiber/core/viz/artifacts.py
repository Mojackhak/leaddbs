"""Spatial artifact preparation for visualization without model refitting."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

try:
    import nibabel as nib
except ImportError:  # pragma: no cover - checked by public functions
    nib = None


def _require_nibabel() -> None:
    if nib is None:
        raise ImportError("spatial artifact preparation requires nibabel")


def _load_image(image: str | Path | Any) -> Any:
    _require_nibabel()
    loaded = nib.load(str(image)) if isinstance(image, (str, Path)) else image
    if not isinstance(loaded, nib.spatialimages.SpatialImage):
        raise TypeError("reference_image must be a path or nibabel spatial image")
    if len(loaded.shape) != 3:
        raise ValueError("reference_image must be three-dimensional")
    return loaded


def _write_nifti(data: np.ndarray, reference: Any, output_path: str | Path) -> Path:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = reference.header.copy()
    header.set_data_dtype(np.float32)
    image = nib.Nifti1Image(np.asarray(data, dtype=np.float32), reference.affine, header=header)
    nib.save(image, str(path))
    return path


def write_json_sidecar(nifti_path: str | Path, payload: Mapping[str, Any]) -> Path:
    """Write a JSON sidecar next to a NIfTI artifact."""

    path = Path(nifti_path).expanduser().resolve()
    name = path.name
    if name.endswith(".nii.gz"):
        sidecar = path.with_name(name[:-7] + ".json")
    elif name.endswith(".nii"):
        sidecar = path.with_suffix(".json")
    else:
        sidecar = path.with_name(name + ".json")
    temporary = sidecar.with_name(sidecar.name + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(sidecar)
    return sidecar


def restore_voxel_vector_to_nifti(
    values: Sequence[float] | np.ndarray,
    voxel_indices: Sequence[int] | Sequence[Sequence[int]] | np.ndarray,
    reference_image: str | Path | Any,
    output_path: str | Path,
    *,
    index_base: int = 0,
    flat_index_order: str = "C",
    outside_value: float = np.nan,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Restore a model vector to an explicit canonical NIfTI grid.

    ``voxel_indices`` may contain flat indices or explicit ``i, j, k`` rows.
    Index base and flat-index order are mandatory semantic inputs and are never
    inferred from the values.
    """

    reference = _load_image(reference_image)
    vector = np.asarray(values, dtype=float).reshape(-1)
    indices = np.asarray(voxel_indices)
    if vector.size != len(indices):
        raise ValueError("values and voxel_indices must contain the same number of entries")
    if index_base not in (0, 1):
        raise ValueError("index_base must be zero or one")
    order = str(flat_index_order).upper()
    if order not in ("C", "F"):
        raise ValueError("flat_index_order must be C or F")

    restored = np.full(reference.shape, float(outside_value), dtype=np.float32)
    shifted = indices.astype(np.int64, copy=False) - index_base
    if shifted.ndim == 1:
        if shifted.size and (np.min(shifted) < 0 or np.max(shifted) >= np.prod(reference.shape)):
            raise ValueError("flat voxel indices are outside the reference grid")
        coordinates = np.unravel_index(shifted, reference.shape, order=order)
    elif shifted.ndim == 2 and shifted.shape[1] == 3:
        if shifted.size:
            lower = np.min(shifted, axis=0)
            upper = np.max(shifted, axis=0)
            if np.any(lower < 0) or np.any(upper >= np.asarray(reference.shape)):
                raise ValueError("voxel coordinates are outside the reference grid")
        coordinates = tuple(shifted[:, axis] for axis in range(3))
    else:
        raise ValueError("voxel_indices must be flat or contain explicit i, j, k rows")
    restored[coordinates] = vector.astype(np.float32, copy=False)
    path = _write_nifti(restored, reference, output_path)
    if metadata is not None:
        write_json_sidecar(
            path,
            {
                **dict(metadata),
                "artifact_role": "voxel_model_visualization",
                "index_base": index_base,
                "flat_index_order": order,
                "outside_value": "NaN" if np.isnan(outside_value) else float(outside_value),
            },
        )
    return path


def _selected_streamlines(
    streamlines: Iterable[np.ndarray], selected_ids: np.ndarray
) -> Iterable[tuple[int, np.ndarray]]:
    selected_set = set(int(item) for item in selected_ids)
    for index, streamline in enumerate(streamlines):
        if index in selected_set:
            yield index, np.asarray(streamline, dtype=float)


def voxelize_selected_fibers(
    tractogram_path: str | Path,
    selected_streamline_indices: Sequence[int] | np.ndarray,
    reference_image: str | Path | Any,
    output_path: str | Path,
    *,
    streamline_index_base: int = 0,
    normalization: str = "count",
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Create a display density NIfTI from selected TCK or TRK streamlines.

    Every selected streamline contributes at most once to each traversed voxel.
    This avoids density inflation from streamline point sampling frequency.
    Canonical fiber IDs must be resolved to tractogram indices before calling
    this function; the two identities are never assumed to be interchangeable.
    """

    _require_nibabel()
    reference = _load_image(reference_image)
    tract_path = Path(tractogram_path).expanduser().resolve()
    if tract_path.suffix.lower() not in (".tck", ".trk"):
        raise ValueError("fiber density input must be a TCK or TRK tractogram")
    indices = (
        np.asarray(selected_streamline_indices, dtype=np.int64).reshape(-1)
        - int(streamline_index_base)
    )
    if indices.size and np.min(indices) < 0:
        raise ValueError(
            "selected streamline indices are below the declared streamline_index_base"
        )
    if normalization not in ("count", "fraction", "binary"):
        raise ValueError("normalization must be count, fraction, or binary")

    tractogram = nib.streamlines.load(str(tract_path), lazy_load=True)
    inverse = np.linalg.inv(reference.affine)
    voxel_sizes = nib.affines.voxel_sizes(reference.affine)
    sample_step = max(float(np.min(voxel_sizes)) * 0.5, 0.1)
    density = np.zeros(reference.shape, dtype=np.float32)
    selected_count = 0

    for _, streamline in _selected_streamlines(tractogram.streamlines, indices):
        if streamline.ndim != 2 or streamline.shape[0] < 1 or streamline.shape[1] < 3:
            continue
        sampled_parts: list[np.ndarray] = [streamline[:1, :3]]
        for start, end in zip(streamline[:-1, :3], streamline[1:, :3], strict=True):
            length = float(np.linalg.norm(end - start))
            steps = max(1, int(np.ceil(length / sample_step)))
            fractions = np.linspace(0.0, 1.0, steps + 1, endpoint=True)[1:]
            sampled_parts.append(start[None, :] + fractions[:, None] * (end - start)[None, :])
        points = np.concatenate(sampled_parts, axis=0)
        voxels = np.rint(nib.affines.apply_affine(inverse, points)).astype(np.int64)
        inside = np.all((voxels >= 0) & (voxels < np.asarray(reference.shape)), axis=1)
        voxels = np.unique(voxels[inside], axis=0)
        if not voxels.size:
            continue
        density[voxels[:, 0], voxels[:, 1], voxels[:, 2]] += 1.0
        selected_count += 1

    if normalization == "fraction" and selected_count > 0:
        density /= float(selected_count)
    elif normalization == "binary":
        density = (density > 0).astype(np.float32)

    path = _write_nifti(density, reference, output_path)
    write_json_sidecar(
        path,
        {
            **dict(metadata or {}),
            "artifact_role": "fiber_density_visualization_derivative",
            "tractogram_path": str(tract_path),
            "streamline_index_base": int(streamline_index_base),
            "selected_streamline_index_count": int(indices.size),
            "rendered_fiber_count": int(selected_count),
            "normalization": normalization,
            "statistical_unit": "fiber",
        },
    )
    return path


__all__ = [
    "restore_voxel_vector_to_nifti",
    "voxelize_selected_fibers",
    "write_json_sidecar",
]
