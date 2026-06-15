#!/usr/bin/env python3
"""Convert a numerically ordered DICOM slice folder into NIfTI."""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pydicom


warnings.filterwarnings("ignore", message="Invalid value for VR UI.*")

DEFAULT_SLICE_THICKNESS_MM = 0.625
DEFAULT_SLICE_DIRECTION = "+z"


class ConversionError(RuntimeError):
    """Raised when the DICOM series cannot be converted safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a single-folder DICOM series to NIfTI by sorting files by "
            "numeric filename and applying an explicit slice spacing."
        )
    )
    parser.add_argument(
        "dicom_dir",
        type=Path,
        help="Folder containing one numerically ordered DICOM series.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output folder. Defaults to a sibling folder named <dicom_dir>_nifti.",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Output basename without extension. Defaults to the DICOM folder name.",
    )
    parser.add_argument(
        "--slice-thickness",
        type=float,
        default=DEFAULT_SLICE_THICKNESS_MM,
        help=f"Synthetic z spacing in millimeters. Default: {DEFAULT_SLICE_THICKNESS_MM}.",
    )
    parser.add_argument(
        "--slice-direction",
        choices=("+z", "-z"),
        default=DEFAULT_SLICE_DIRECTION,
        help=f"Synthetic slice direction. Default: {DEFAULT_SLICE_DIRECTION}.",
    )
    return parser.parse_args()


def numeric_sort_key(path: Path) -> tuple[int, int | str]:
    """Sort numeric file stems before non-numeric stems."""

    stem = path.stem
    if re.fullmatch(r"\d+", stem):
        return (0, int(stem))
    return (1, stem)


def find_dicom_files(dicom_dir: Path) -> list[Path]:
    if not dicom_dir.is_dir():
        raise ConversionError(f"DICOM directory does not exist: {dicom_dir}")

    files = sorted(
        [path for path in dicom_dir.iterdir() if path.is_file() and path.suffix.lower() == ".dcm"],
        key=numeric_sort_key,
    )
    if not files:
        raise ConversionError(f"No .dcm files found in: {dicom_dir}")

    non_numeric = [path.name for path in files if not re.fullmatch(r"\d+", path.stem)]
    if non_numeric:
        raise ConversionError(
            "All DICOM file stems must be numeric for deterministic slice ordering. "
            f"Non-numeric examples: {', '.join(non_numeric[:5])}"
        )

    return files


def read_datasets(files: list[Path]) -> list[pydicom.dataset.FileDataset]:
    datasets = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Invalid value for VR UI.*")
        for path in files:
            datasets.append(pydicom.dcmread(str(path), force=True))
    return datasets


def get_required_float_array(ds: pydicom.dataset.Dataset, keyword: str, length: int) -> np.ndarray:
    value = getattr(ds, keyword, None)
    if value is None:
        raise ConversionError(f"Required DICOM field is missing: {keyword}")

    arr = np.asarray([float(item) for item in value], dtype=np.float64)
    if arr.shape != (length,):
        raise ConversionError(f"DICOM field {keyword} must have {length} values, got {arr.size}")
    return arr


def get_optional_float_array(
    ds: pydicom.dataset.Dataset,
    keyword: str,
    length: int,
) -> np.ndarray | None:
    value = getattr(ds, keyword, None)
    if value is None:
        return None

    arr = np.asarray([float(item) for item in value], dtype=np.float64)
    if arr.shape != (length,):
        raise ConversionError(f"DICOM field {keyword} must have {length} values, got {arr.size}")
    return arr


def get_float(ds: pydicom.dataset.Dataset, keyword: str, default: float) -> float:
    value = getattr(ds, keyword, None)
    if value is None:
        return default
    return float(value)


def unique_values(datasets: list[pydicom.dataset.FileDataset], keyword: str) -> set[str]:
    values = set()
    for ds in datasets:
        value = getattr(ds, keyword, None)
        if value is not None:
            values.add(str(value))
    return values


def validate_series(
    datasets: list[pydicom.dataset.FileDataset],
) -> dict[str, Any]:
    first = datasets[0]

    series_uids = unique_values(datasets, "SeriesInstanceUID")
    if len(series_uids) > 1:
        raise ConversionError(f"Input contains multiple SeriesInstanceUID values: {len(series_uids)}")

    rows = int(getattr(first, "Rows", 0))
    cols = int(getattr(first, "Columns", 0))
    if rows <= 0 or cols <= 0:
        raise ConversionError("Rows and Columns must be present and positive.")

    pixel_spacing = get_required_float_array(first, "PixelSpacing", 2)
    image_orientation = get_required_float_array(first, "ImageOrientationPatient", 6)
    image_position = get_optional_float_array(first, "ImagePositionPatient", 3)
    if image_position is None:
        raise ConversionError("ImagePositionPatient is required to construct the NIfTI affine.")

    rescale_slope = get_float(first, "RescaleSlope", 1.0)
    rescale_intercept = get_float(first, "RescaleIntercept", 0.0)

    for index, ds in enumerate(datasets, start=1):
        file_label = f"DICOM #{index}"
        if int(getattr(ds, "Rows", 0)) != rows or int(getattr(ds, "Columns", 0)) != cols:
            raise ConversionError(f"{file_label} has inconsistent Rows/Columns.")

        current_spacing = get_required_float_array(ds, "PixelSpacing", 2)
        if not np.allclose(current_spacing, pixel_spacing, rtol=0.0, atol=1e-6):
            raise ConversionError(f"{file_label} has inconsistent PixelSpacing.")

        current_orientation = get_required_float_array(ds, "ImageOrientationPatient", 6)
        if not np.allclose(current_orientation, image_orientation, rtol=0.0, atol=1e-6):
            raise ConversionError(f"{file_label} has inconsistent ImageOrientationPatient.")

        current_slope = get_float(ds, "RescaleSlope", 1.0)
        current_intercept = get_float(ds, "RescaleIntercept", 0.0)
        if not np.isclose(current_slope, rescale_slope, rtol=0.0, atol=1e-8):
            raise ConversionError(f"{file_label} has inconsistent RescaleSlope.")
        if not np.isclose(current_intercept, rescale_intercept, rtol=0.0, atol=1e-8):
            raise ConversionError(f"{file_label} has inconsistent RescaleIntercept.")

        frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        if frames != 1:
            raise ConversionError(f"{file_label} is multi-frame; this helper expects single-frame files.")

    missing_fields = [
        keyword
        for keyword in (
            "InstanceNumber",
            "SliceLocation",
            "SliceThickness",
            "SpacingBetweenSlices",
        )
        if getattr(first, keyword, None) is None
    ]

    return {
        "rows": rows,
        "cols": cols,
        "pixel_spacing": pixel_spacing,
        "image_orientation": image_orientation,
        "image_position": image_position,
        "rescale_slope": rescale_slope,
        "rescale_intercept": rescale_intercept,
        "series_uid_present": bool(series_uids),
        "series_number": str(getattr(first, "SeriesNumber", "")),
        "series_description": str(getattr(first, "SeriesDescription", "")),
        "modality": str(getattr(first, "Modality", "")),
        "missing_geometry_fields": missing_fields,
    }


def build_volume(
    datasets: list[pydicom.dataset.FileDataset],
    rescale_slope: float,
    rescale_intercept: float,
) -> np.ndarray:
    slices = []
    use_float = not (
        np.isclose(rescale_slope, 1.0, rtol=0.0, atol=1e-8)
        and np.isclose(rescale_intercept, 0.0, rtol=0.0, atol=1e-8)
    )

    for index, ds in enumerate(datasets, start=1):
        array = ds.pixel_array
        if array.ndim != 2:
            raise ConversionError(f"DICOM #{index} pixel data is not 2D.")

        if use_float:
            array = array.astype(np.float32) * np.float32(rescale_slope) + np.float32(rescale_intercept)
        slices.append(array)

    volume = np.stack(slices, axis=2)
    if use_float:
        return volume.astype(np.float32, copy=False)
    return volume


def build_affine(
    pixel_spacing: np.ndarray,
    image_orientation: np.ndarray,
    image_position: np.ndarray,
    slice_thickness: float,
    slice_direction: str,
) -> np.ndarray:
    row_spacing_mm = float(pixel_spacing[0])
    col_spacing_mm = float(pixel_spacing[1])
    row_direction_lps = image_orientation[:3]
    col_direction_lps = image_orientation[3:]
    slice_direction_lps = np.cross(row_direction_lps, col_direction_lps)

    if slice_direction == "-z":
        slice_direction_lps = -slice_direction_lps

    lps_to_ras = np.diag([-1.0, -1.0, 1.0])

    affine = np.eye(4, dtype=np.float64)
    affine[:3, 0] = lps_to_ras @ (col_direction_lps * row_spacing_mm)
    affine[:3, 1] = lps_to_ras @ (row_direction_lps * col_spacing_mm)
    affine[:3, 2] = lps_to_ras @ (slice_direction_lps * slice_thickness)
    affine[:3, 3] = lps_to_ras @ image_position
    return affine


def normalize_output_name(output_name: str) -> str:
    for suffix in (".nii.gz", ".nii"):
        if output_name.endswith(suffix):
            return output_name[: -len(suffix)]
    return output_name


def resolve_output_dir(requested_output_dir: Path) -> tuple[Path, bool]:
    if not requested_output_dir.exists():
        requested_output_dir.mkdir(parents=True)
        return requested_output_dir, False

    if not requested_output_dir.is_dir():
        raise ConversionError(f"Output path exists but is not a directory: {requested_output_dir}")

    if not any(requested_output_dir.iterdir()):
        return requested_output_dir, False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = requested_output_dir.with_name(f"{requested_output_dir.name}_{timestamp}")
    suffix = 1
    while candidate.exists():
        candidate = requested_output_dir.with_name(f"{requested_output_dir.name}_{timestamp}_{suffix}")
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate, True


def write_nifti(volume: np.ndarray, affine: np.ndarray, output_path: Path) -> None:
    image = nib.Nifti1Image(volume, affine)
    image.header.set_xyzt_units("mm")
    image.header.set_data_dtype(volume.dtype)
    image.set_qform(affine, code=1)
    image.set_sform(affine, code=1)
    nib.save(image, str(output_path))


def write_metadata(
    metadata_path: Path,
    dicom_dir: Path,
    files: list[Path],
    output_nifti: Path,
    requested_output_dir: Path,
    actual_output_dir: Path,
    used_timestamped_dir: bool,
    output_name: str,
    validation: dict[str, Any],
    affine: np.ndarray,
    volume: np.ndarray,
    slice_thickness: float,
    slice_direction: str,
) -> None:
    pixel_spacing = validation["pixel_spacing"]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": Path(__file__).name,
        "source_dicom_dir": str(dicom_dir),
        "source_file_count": len(files),
        "first_source_file": files[0].name,
        "last_source_file": files[-1].name,
        "requested_output_dir": str(requested_output_dir),
        "actual_output_dir": str(actual_output_dir),
        "used_timestamped_output_dir": used_timestamped_dir,
        "output_name": output_name,
        "output_nifti": str(output_nifti),
        "shape": list(volume.shape),
        "voxel_size_mm": [
            float(pixel_spacing[0]),
            float(pixel_spacing[1]),
            float(slice_thickness),
        ],
        "slice_direction": slice_direction,
        "slice_order": "numeric_filename_stem",
        "affine_ras": affine.tolist(),
        "modality": validation["modality"],
        "series_number": validation["series_number"],
        "series_description": validation["series_description"],
        "series_uid_present": validation["series_uid_present"],
        "rescale_slope": validation["rescale_slope"],
        "rescale_intercept": validation["rescale_intercept"],
        "missing_geometry_fields": validation["missing_geometry_fields"],
        "assumptions": [
            "The source DICOM files were not modified.",
            "Slices were sorted by numeric filename stem.",
            "Per-slice geometry was synthesized from the selected slice thickness and direction.",
        ],
    }
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def convert(args: argparse.Namespace) -> tuple[Path, Path, bool]:
    if args.slice_thickness <= 0:
        raise ConversionError("--slice-thickness must be positive.")

    dicom_dir = args.dicom_dir.expanduser().resolve()
    files = find_dicom_files(dicom_dir)
    datasets = read_datasets(files)
    validation = validate_series(datasets)

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = dicom_dir.with_name(f"{dicom_dir.name}_nifti")
    requested_output_dir = output_dir.expanduser().resolve()
    actual_output_dir, used_timestamped_dir = resolve_output_dir(requested_output_dir)

    output_name = normalize_output_name(args.output_name or dicom_dir.name)
    output_nifti = actual_output_dir / f"{output_name}.nii.gz"
    metadata_path = actual_output_dir / f"{output_name}_conversion.json"

    if output_nifti.exists() or metadata_path.exists():
        raise ConversionError(f"Output files already exist in: {actual_output_dir}")

    volume = build_volume(
        datasets,
        validation["rescale_slope"],
        validation["rescale_intercept"],
    )
    affine = build_affine(
        validation["pixel_spacing"],
        validation["image_orientation"],
        validation["image_position"],
        float(args.slice_thickness),
        args.slice_direction,
    )

    write_nifti(volume, affine, output_nifti)
    write_metadata(
        metadata_path,
        dicom_dir,
        files,
        output_nifti,
        requested_output_dir,
        actual_output_dir,
        used_timestamped_dir,
        output_name,
        validation,
        affine,
        volume,
        float(args.slice_thickness),
        args.slice_direction,
    )

    return output_nifti, metadata_path, used_timestamped_dir


def main() -> int:
    args = parse_args()
    try:
        output_nifti, metadata_path, used_timestamped_dir = convert(args)
    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if used_timestamped_dir:
        print("Requested output directory was not empty; wrote to a timestamped sibling directory.")
    print(f"Wrote NIfTI: {output_nifti}")
    print(f"Wrote metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
