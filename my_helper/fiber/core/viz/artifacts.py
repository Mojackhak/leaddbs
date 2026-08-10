"""Spatial artifact preparation for visualization without model refitting."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import affine_transform, gaussian_filter

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


def _trash_existing_display_outputs(paths: Sequence[Path]) -> None:
    existing = [path for path in paths if path.exists()]
    if existing:
        subprocess.run(
            ("/usr/bin/trash", *(str(path) for path in existing)),
            check=True,
        )


def create_display_nifti(
    source_image: str | Path | Any,
    output_path: str | Path,
    *,
    fwhm_mm: float,
    voxel_size_mm: float,
    support_weight_threshold: float,
    force: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Create the single smoothed high-resolution display-only NIfTI."""

    destination = Path(output_path).expanduser().resolve()
    if type(fwhm_mm) not in {int, float} or float(fwhm_mm) <= 0.0:
        raise ValueError("fwhm_mm must be positive")
    if voxel_size_mm <= 0:
        raise ValueError("voxel_size_mm must be positive")
    if not 0.0 < float(support_weight_threshold) < 1.0:
        raise ValueError(
            "support_weight_threshold must be greater than 0 and less than 1"
        )
    if destination.is_file() and not force:
        return destination, {
            "artifact_kind": "display_nifti",
            "display_only": True,
            "fwhm_mm": float(fwhm_mm),
            "output_voxel_size_mm": float(voxel_size_mm),
            "support_weight_threshold": float(support_weight_threshold),
            "resume_status": "reused",
        }
    if destination.exists() and not force:
        raise FileExistsError("display output path is not a file")

    source = _load_image(source_image)
    data = np.asarray(source.dataobj, dtype=np.float32)
    finite = np.isfinite(data)
    finite_coordinates = np.argwhere(finite)
    if finite_coordinates.size == 0:
        raise ValueError("source_image must contain finite display voxels")

    source_voxel_sizes = np.asarray(
        nib.affines.voxel_sizes(source.affine), dtype=float
    )
    sigma_voxels = (
        float(fwhm_mm) / 2.354820045 / source_voxel_sizes
    )
    padding_voxels = np.ceil(4.0 * sigma_voxels).astype(int)
    lower = np.maximum(finite_coordinates.min(axis=0) - padding_voxels, 0)
    upper = np.minimum(
        finite_coordinates.max(axis=0) + padding_voxels,
        np.asarray(source.shape, dtype=int) - 1,
    )
    slices = tuple(
        slice(int(lower[axis]), int(upper[axis]) + 1) for axis in range(3)
    )
    cropped_data = data[slices]
    cropped_finite = finite[slices]

    crop_affine = np.asarray(source.affine, dtype=float).copy()
    crop_affine[:3, 3] = nib.affines.apply_affine(source.affine, lower)
    directions = crop_affine[:3, :3] / source_voxel_sizes
    target_affine = crop_affine.copy()
    target_affine[:3, :3] = directions * float(voxel_size_mm)
    extent_mm = (
        np.asarray(cropped_data.shape, dtype=float) - 1.0
    ) * source_voxel_sizes
    target_shape = tuple(
        int(round(value / voxel_size_mm)) + 1 for value in extent_mm
    )

    target_to_source = np.linalg.inv(crop_affine) @ target_affine
    transform = target_to_source[:3, :3]
    offset = target_to_source[:3, 3]
    smoothed_numerator = gaussian_filter(
        np.where(cropped_finite, cropped_data, 0.0),
        sigma=sigma_voxels,
        mode="constant",
        cval=0.0,
    )
    smoothed_weight = gaussian_filter(
        cropped_finite.astype(np.float32),
        sigma=sigma_voxels,
        mode="constant",
        cval=0.0,
    )
    numerator = affine_transform(
        smoothed_numerator,
        transform,
        offset=offset,
        output_shape=target_shape,
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    weight = affine_transform(
        smoothed_weight,
        transform,
        offset=offset,
        output_shape=target_shape,
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    target_finite = weight > float(support_weight_threshold)
    output = np.full(target_shape, np.nan, dtype=np.float32)
    output[target_finite] = (
        numerator[target_finite] / weight[target_finite]
    ).astype(np.float32)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_nifti = destination.with_name(
        f"{destination.name.removesuffix('.nii.gz')}.tmp.nii.gz"
    )
    header = source.header.copy()
    header.set_data_dtype(np.float32)
    image = nib.Nifti1Image(output, target_affine, header=header)
    image.set_qform(target_affine)
    image.set_sform(target_affine)
    nib.save(image, str(temporary_nifti))
    if force and destination.exists():
        _trash_existing_display_outputs((destination,))
    temporary_nifti.replace(destination)

    metadata = {
        "artifact_kind": "display_nifti",
        "display_only": True,
        "fwhm_mm": float(fwhm_mm),
        "support_weight_threshold": float(support_weight_threshold),
        "source_path": (
            str(Path(source_image).expanduser().resolve())
            if isinstance(source_image, (str, Path))
            else None
        ),
        "source_shape": [int(value) for value in source.shape],
        "source_voxel_size_mm": [float(value) for value in source_voxel_sizes],
        "source_finite_voxel_count": int(finite.sum()),
        "crop_source_index_lower": [int(value) for value in lower],
        "crop_source_index_upper": [int(value) for value in upper],
        "source_halo_voxels": [int(value) for value in padding_voxels],
        "source_halo_mm": [float(value) for value in source_voxel_sizes],
        "source_halo_is_final_support": False,
        "output_shape": [int(value) for value in target_shape],
        "output_voxel_size_mm": [float(voxel_size_mm)] * 3,
        "output_affine": [
            [float(value) for value in row] for row in target_affine
        ],
        "output_finite_voxel_count": int(target_finite.sum()),
        "gaussian_sigma_voxels": [float(value) for value in sigma_voxels],
        "gaussian_truncate_sigma": 4.0,
        "scalar_interpolation": "masked_normalized_gaussian_then_linear",
        "support_interpolation": "linear_gaussian_weight_threshold",
        "outside_value": "NaN",
    }
    return destination, metadata


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
