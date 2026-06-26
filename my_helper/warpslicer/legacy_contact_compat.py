"""Build a residual warp that maps current contact coordinates to legacy ones.

The module calls SlicerForLeadDBS CLI executables directly. Coordinates stored
in Lead-DBS reconstruction files and cohort tables are RAS millimeter
coordinates; Slicer CLI point parameters and ANTs transforms use LPS
coordinates, so conversions are explicit at all external boundaries.
"""

from __future__ import annotations

import csv
import json
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import nibabel as nib
import numpy as np
import pandas as pd
from scipy.io import loadmat


@dataclass(frozen=True)
class CompatPaths:
    """Input and output paths for one compatibility-warp build."""

    lead_root: Path
    reconstruction_mat: Path
    cohort_pkl: Path
    template_reference: Path
    native_reference: Path
    current_forward: Path
    current_inverse: Path
    output_dir: Path
    subject_label: str = "Sub-ZhangMing"
    slicer_install: Path = Path.home() / ".leaddbs" / "SlicerForLeadDBS"
    legacy_target_override_csv: Path | None = None


@dataclass(frozen=True)
class CompatParams:
    """Numerical parameters for landmark residual construction."""

    rbf_radius_mm: float = 15.0
    stiffness: float = 0.0
    precision_decimals: int = 7
    overwrite_existing_outputs: bool = True
    write_point_exact_inverse: bool = True


RUN_OUTPUT_NAMES = (
    "landmarks.json",
    "landmarks.csv",
    "build_legacy_contact_compat.log",
    "residual_currentMni_to_legacyMni_rbf.h5",
    "residual_legacyMni_to_currentMni_rbf.h5",
    "residual_currentMni_to_legacyMni_rbf.nrrd",
    "residual_legacyMni_to_currentMni_rbf.nrrd",
    "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompat_ants.nii.gz",
    "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompat_ants.nii.gz",
    "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompatPointExact_ants.nii.gz",
    "validation_current_forward.csv",
    "validation_current_inverse.csv",
    "validation_candidate_forward.csv",
    "validation_candidate_inverse.csv",
    "validation_candidate_inverse_point_exact_grid.csv",
    "validation_candidate_inverse_point_exact_ants.csv",
    "validation_residual_only.csv",
    "validation_summary.json",
)


def build_legacy_contact_compat(paths: CompatPaths, params: CompatParams) -> dict:
    """Build candidate transforms and validate contact-level agreement."""

    paths = _normalize_paths(paths)
    _require_inputs(paths)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _prepare_outputs(paths.output_dir, params)

    log_path = paths.output_dir / "build_legacy_contact_compat.log"
    logger = _Logger(log_path)
    logger.write("Building legacy contact compatibility warp")
    logger.write(f"Subject: {paths.subject_label}")
    logger.write(f"Output directory: {paths.output_dir}")
    logger.write(f"RBF radius: {params.rbf_radius_mm:.6f} mm")
    logger.write(f"RBF stiffness: {params.stiffness:.6f}")

    landmarks = extract_contact_landmarks(paths)
    _write_landmarks(paths.output_dir, landmarks, params)

    cli = _slicer_cli_paths(paths.slicer_install)
    ants_points = _ants_apply_transforms_to_points(paths.lead_root)

    current_mni_lps = ras_to_lps(landmarks["current_mni"])
    rbf_target_mni_lps = ras_to_lps(landmarks["rbf_target_mni"])

    residual_forward = paths.output_dir / "residual_currentMni_to_legacyMni_rbf.nrrd"
    residual_inverse = paths.output_dir / "residual_legacyMni_to_currentMni_rbf.nrrd"
    candidate_forward = paths.output_dir / "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompat_ants.nii.gz"
    candidate_inverse = paths.output_dir / "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompat_ants.nii.gz"
    candidate_inverse_point_exact = (
        paths.output_dir
        / "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompatPointExact_ants.nii.gz"
    )

    _run_rbf_cli(
        cli["rbf"],
        paths.template_reference,
        moving_lps=current_mni_lps,
        fixed_lps=rbf_target_mni_lps,
        output_transform=residual_forward,
        radius_mm=params.rbf_radius_mm,
        stiffness=params.stiffness,
        logger=logger,
    )
    _run_rbf_cli(
        cli["rbf"],
        paths.template_reference,
        moving_lps=rbf_target_mni_lps,
        fixed_lps=current_mni_lps,
        output_transform=residual_inverse,
        radius_mm=params.rbf_radius_mm,
        stiffness=params.stiffness,
        logger=logger,
    )

    _run_composite_cli(
        cli["composite"],
        input_transform_1=paths.current_forward,
        input_transform_2=residual_forward,
        reference_volume=paths.template_reference,
        output_transform=candidate_forward,
        logger=logger,
        label="candidate forward",
    )
    _run_composite_cli(
        cli["composite"],
        input_transform_1=residual_inverse,
        input_transform_2=paths.current_inverse,
        reference_volume=paths.native_reference,
        output_transform=candidate_inverse,
        logger=logger,
        label="candidate inverse",
    )
    if params.write_point_exact_inverse:
        write_point_exact_inverse_candidate(
            input_transform=candidate_inverse,
            output_transform=candidate_inverse_point_exact,
            source_ras=landmarks["source_for_forward"],
            target_ras=landmarks["legacy_mni"],
            logger=logger,
        )
    else:
        candidate_inverse_point_exact = None

    validation = _validate_outputs(
        paths=paths,
        params=params,
        ants_points=ants_points,
        source_ras=landmarks["source_for_forward"],
        current_mni_ras=landmarks["current_mni"],
        legacy_mni_ras=landmarks["legacy_mni"],
        residual_forward=residual_forward,
        candidate_forward=candidate_forward,
        candidate_inverse=candidate_inverse,
        candidate_inverse_point_exact=candidate_inverse_point_exact,
        logger=logger,
    )

    summary = {
        "subject": paths.subject_label,
        "output_dir": str(paths.output_dir),
        "rbf_radius_mm": params.rbf_radius_mm,
        "stiffness": params.stiffness,
        "precision_decimals": params.precision_decimals,
        "residual_forward": str(residual_forward),
        "residual_inverse": str(residual_inverse),
        "candidate_forward": str(candidate_forward),
        "candidate_inverse": str(candidate_inverse),
        "candidate_inverse_point_exact": str(candidate_inverse_point_exact) if candidate_inverse_point_exact else None,
        "validation": validation,
    }
    with (paths.output_dir / "validation_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)
    logger.write("Finished")
    return summary


def write_point_exact_inverse_candidate(
    input_transform: Path,
    output_transform: Path,
    source_ras: np.ndarray,
    target_ras: np.ndarray,
    logger: "_Logger | None" = None,
) -> dict:
    """Write a grid-patched inverse transform that is exact at contact points."""

    input_transform = Path(input_transform)
    output_transform = Path(output_transform)
    source_ras = np.asarray(source_ras, dtype=float)
    target_ras = np.asarray(target_ras, dtype=float)
    if source_ras.shape != target_ras.shape:
        raise ValueError("Source and target point arrays must have the same shape")
    if source_ras.ndim != 2 or source_ras.shape[1] != 3:
        raise ValueError("Source and target point arrays must have shape (n, 3)")
    if logger:
        logger.write(f"Writing point-exact inverse candidate {output_transform.name}")

    img = nib.load(str(input_transform))
    raw = np.asarray(img.dataobj)
    data, vector_axis_kind = _displacement_data_view(raw)
    working = np.array(data, dtype=np.float64, copy=True)
    indices = _points_to_voxel_indices(img.affine, source_ras)
    entries = _trilinear_entries(indices, working.shape[:3])
    observed_before = source_ras + _sample_displacement_data(working, entries)
    residual = target_ras - observed_before

    vertex_to_column: dict[tuple[int, int, int], int] = {}
    for point_entries in entries:
        for vertex, _weight in point_entries:
            if vertex not in vertex_to_column:
                vertex_to_column[vertex] = len(vertex_to_column)

    design = np.zeros((len(entries), len(vertex_to_column)), dtype=np.float64)
    for row_index, point_entries in enumerate(entries):
        for vertex, weight in point_entries:
            design[row_index, vertex_to_column[vertex]] += weight

    corrections = np.zeros((len(vertex_to_column), 3), dtype=np.float64)
    for component in range(3):
        corrections[:, component] = np.linalg.lstsq(design, residual[:, component], rcond=None)[0]

    for vertex, column in vertex_to_column.items():
        working[vertex[0], vertex[1], vertex[2], :] += corrections[column]

    observed_after = source_ras + _sample_displacement_data(working, entries)
    output_data = _restore_displacement_data_shape(working, vector_axis_kind)
    output_img = nib.Nifti1Image(output_data, img.affine, header=img.header.copy())
    output_img.set_qform(img.get_qform(), int(img.header["qform_code"]))
    output_img.set_sform(img.get_sform(), int(img.header["sform_code"]))
    nib.save(output_img, str(output_transform))

    before_error = np.linalg.norm(observed_before - target_ras, axis=1)
    after_error = np.linalg.norm(observed_after - target_ras, axis=1)
    summary = {
        "input_transform": str(input_transform),
        "output_transform": str(output_transform),
        "point_count": int(source_ras.shape[0]),
        "edited_vertex_count": int(len(vertex_to_column)),
        "mean_error_before_mm": float(before_error.mean()),
        "max_error_before_mm": float(before_error.max()),
        "mean_error_after_mm": float(after_error.mean()),
        "max_error_after_mm": float(after_error.max()),
    }
    if logger:
        logger.write(f"Point-exact edited vertex count: {summary['edited_vertex_count']}")
        logger.write(f"Point-exact grid max error after patch: {summary['max_error_after_mm']:.9g} mm")
    return summary


def extract_contact_landmarks(paths: CompatPaths) -> dict:
    """Extract current and legacy contacts in a stable Contact-order table."""

    mat = loadmat(paths.reconstruction_mat, squeeze_me=True, struct_as_record=False)
    reco = mat["reco"]
    cohort = pd.read_pickle(paths.cohort_pkl)
    rows = cohort[cohort["Subject"].eq(paths.subject_label)].sort_values("Contact")
    if len(rows) == 0:
        raise ValueError(f"No cohort rows found for {paths.subject_label}")

    legacy = rows[["MNI_x", "MNI_y", "MNI_z"]].to_numpy(float)
    rbf_target = legacy
    if paths.legacy_target_override_csv is not None:
        rbf_target = _read_legacy_target_override(paths.legacy_target_override_csv, rows)
    current_mni = _coords_from_reco_by_contact_order(reco.mni.coords_mm, rows)
    native = _coords_from_reco_by_contact_order(reco.native.coords_mm, rows)
    source_for_forward = _coords_from_reco_by_contact_order(
        reco.scrf.coords_mm if hasattr(reco, "scrf") else reco.native.coords_mm,
        rows,
    )

    return {
        "subject": paths.subject_label,
        "contact_rows": rows[["Contact", "Side", "Region", "Hemi", "Lead_idx", "Lead_num"]].to_dict("records"),
        "current_mni": current_mni,
        "legacy_mni": legacy,
        "rbf_target_mni": rbf_target,
        "source_for_forward": source_for_forward,
        "native": native,
    }


def ras_to_lps(points_ras: np.ndarray) -> np.ndarray:
    """Convert RAS millimeter coordinates to LPS."""

    points = np.asarray(points_ras, dtype=float).copy()
    points[:, 0] *= -1
    points[:, 1] *= -1
    return points


def lps_to_ras(points_lps: np.ndarray) -> np.ndarray:
    """Convert LPS millimeter coordinates to RAS."""

    return ras_to_lps(points_lps)


def apply_ants_transform_to_points(
    ants_points_exe: Path,
    points_lps: np.ndarray,
    transform: Path,
) -> np.ndarray:
    """Apply one ANTs transform to LPS points and return LPS points."""

    points_lps = np.asarray(points_lps, dtype=float)
    with tempfile.TemporaryDirectory(prefix="warpslicer_points_") as tmp:
        tmp_path = Path(tmp)
        input_csv = tmp_path / "input.csv"
        output_csv = tmp_path / "output.csv"
        _write_ants_points_csv(input_csv, points_lps)
        cmd = [
            str(ants_points_exe),
            "--dimensionality",
            "3",
            "--precision",
            "0",
            "--input",
            str(input_csv),
            "--output",
            str(output_csv),
            "--transform",
            f"[{transform},0]",
        ]
        _run_command(cmd, "antsApplyTransformsToPoints")
        return _read_ants_points_csv(output_csv)


def _normalize_paths(paths: CompatPaths) -> CompatPaths:
    values = {field: getattr(paths, field) for field in paths.__dataclass_fields__}
    for key, value in values.items():
        if key not in {"subject_label"} and value is not None:
            values[key] = Path(value)
    return CompatPaths(**values)


def _require_inputs(paths: CompatPaths) -> None:
    required = [
        paths.reconstruction_mat,
        paths.cohort_pkl,
        paths.template_reference,
        paths.native_reference,
        paths.current_forward,
        paths.current_inverse,
    ]
    if paths.legacy_target_override_csv is not None:
        required.append(paths.legacy_target_override_csv)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))


def _prepare_outputs(output_dir: Path, params: CompatParams) -> None:
    existing = [output_dir / name for name in RUN_OUTPUT_NAMES if (output_dir / name).exists()]
    if not existing:
        return
    if not params.overwrite_existing_outputs:
        raise FileExistsError("Existing output files found:\n" + "\n".join(map(str, existing)))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = output_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in existing:
        shutil.move(str(path), str(backup_dir / path.name))


def _coords_from_reco_by_contact_order(coords_by_side, cohort_rows: pd.DataFrame) -> np.ndarray:
    side_to_reco_index = {"Right": 0, "Left": 1}
    counters = {"Right": 0, "Left": 0}
    ordered = []
    for _, row in cohort_rows.iterrows():
        side = str(row["Side"])
        if side not in side_to_reco_index:
            raise ValueError(f"Unsupported side label: {side}")
        reco_index = side_to_reco_index[side]
        contact_index = counters[side]
        coords = np.asarray(coords_by_side[reco_index], dtype=float)
        if contact_index >= len(coords):
            raise IndexError(f"Contact index {contact_index} out of bounds for {side}")
        ordered.append(coords[contact_index])
        counters[side] += 1
    return np.vstack(ordered)


def _read_legacy_target_override(path: Path, cohort_rows: pd.DataFrame) -> np.ndarray:
    table = pd.read_csv(path)
    required = {"contact", "target_mni_x", "target_mni_y", "target_mni_z"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Missing target override columns in {path}: {sorted(missing)}")
    table = table.sort_values("contact")
    expected_contacts = cohort_rows["Contact"].astype(int).to_list()
    observed_contacts = table["contact"].astype(int).to_list()
    if observed_contacts != expected_contacts:
        raise ValueError(
            "Target override contacts do not match cohort order: "
            f"expected {expected_contacts}, observed {observed_contacts}"
        )
    return table[["target_mni_x", "target_mni_y", "target_mni_z"]].to_numpy(float)


def _write_landmarks(output_dir: Path, landmarks: dict, params: CompatParams) -> None:
    rows = []
    for idx, meta in enumerate(landmarks["contact_rows"]):
        current = landmarks["current_mni"][idx]
        legacy = landmarks["legacy_mni"][idx]
        rbf_target = landmarks["rbf_target_mni"][idx]
        source = landmarks["source_for_forward"][idx]
        native = landmarks["native"][idx]
        rows.append(
            {
                "contact": int(meta["Contact"]),
                "side": str(meta["Side"]),
                "region": str(meta["Region"]),
                "current_mni": current.tolist(),
                "legacy_mni": legacy.tolist(),
                "rbf_target_mni": rbf_target.tolist(),
                "delta_legacy_minus_current": (legacy - current).tolist(),
                "delta_rbf_target_minus_current": (rbf_target - current).tolist(),
                "source_for_forward": source.tolist(),
                "native": native.tolist(),
            }
        )
    payload = {
        "subject": landmarks["subject"],
        "legacy_precision_decimals": params.precision_decimals,
        "rows": rows,
    }
    with (output_dir / "landmarks.json").open("w") as f:
        json.dump(payload, f, indent=2)

    with (output_dir / "landmarks.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "contact",
                "side",
                "region",
                "current_mni_x",
                "current_mni_y",
                "current_mni_z",
                "legacy_mni_x",
                "legacy_mni_y",
                "legacy_mni_z",
                "rbf_target_mni_x",
                "rbf_target_mni_y",
                "rbf_target_mni_z",
                "delta_x",
                "delta_y",
                "delta_z",
                "rbf_target_delta_x",
                "rbf_target_delta_y",
                "rbf_target_delta_z",
                "source_x",
                "source_y",
                "source_z",
                "native_x",
                "native_y",
                "native_z",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["contact"],
                    row["side"],
                    row["region"],
                    *row["current_mni"],
                    *row["legacy_mni"],
                    *row["rbf_target_mni"],
                    *row["delta_legacy_minus_current"],
                    *row["delta_rbf_target_minus_current"],
                    *row["source_for_forward"],
                    *row["native"],
                ]
            )


def _slicer_cli_paths(slicer_install: Path) -> dict[str, Path]:
    cli_dir = (
        slicer_install
        / "SlicerForLeadDBS.app"
        / "Contents"
        / "lib"
        / "SlicerForLeadDBS-5.2"
        / "cli-modules"
    )
    paths = {
        "rbf": cli_dir / "FiducialRegistrationVariableRBF",
        "composite": cli_dir / "CompositeToGridTransform",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing SlicerForLeadDBS CLI files:\n" + "\n".join(missing))
    return paths


def _ants_apply_transforms_to_points(lead_root: Path) -> Path:
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        suffix = "maca64" if machine == "arm64" else "maci64"
    elif system == "Linux":
        suffix = "glnxa64"
    elif system == "Windows":
        suffix = "exe"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")
    exe = lead_root / "ext_libs" / "ANTs" / f"antsApplyTransformsToPoints.{suffix}"
    if not exe.is_file():
        raise FileNotFoundError(exe)
    return exe


def _run_rbf_cli(
    cli_path: Path,
    reference_volume: Path,
    moving_lps: np.ndarray,
    fixed_lps: np.ndarray,
    output_transform: Path,
    radius_mm: float,
    stiffness: float,
    logger: "_Logger",
) -> None:
    if moving_lps.shape != fixed_lps.shape:
        raise ValueError("Moving and fixed landmarks must have the same shape")
    radii = ",".join([f"{radius_mm:.9f}" for _ in range(moving_lps.shape[0])])
    cmd = [str(cli_path), str(reference_volume)]
    for point in moving_lps:
        cmd.extend(["--movingFiducials", _format_point(point)])
    for point in fixed_lps:
        cmd.extend(["--fixedFiducials", _format_point(point)])
    cmd.extend(
        [
            "--rbfradius",
            radii,
            "--stiffness",
            f"{stiffness:.9f}",
            "--outputDisplacementField",
            str(output_transform),
        ]
    )
    _run_command(cmd, f"RBF output {output_transform.name}", logger=logger)


def _run_composite_cli(
    cli_path: Path,
    input_transform_1: Path,
    input_transform_2: Path,
    reference_volume: Path,
    output_transform: Path,
    logger: "_Logger",
    label: str,
) -> None:
    cmd = [
        str(cli_path),
        "--inputTransform1File",
        str(input_transform_1),
        "--inputTransform2File",
        str(input_transform_2),
        "--inputReferenceVolumeFile",
        str(reference_volume),
        "--outputFileName",
        str(output_transform),
    ]
    _run_command(cmd, f"CompositeToGridTransform {label}", logger=logger)


def _validate_outputs(
    paths: CompatPaths,
    params: CompatParams,
    ants_points: Path,
    source_ras: np.ndarray,
    current_mni_ras: np.ndarray,
    legacy_mni_ras: np.ndarray,
    residual_forward: Path,
    candidate_forward: Path,
    candidate_inverse: Path,
    candidate_inverse_point_exact: Path | None,
    logger: "_Logger",
) -> dict:
    current_from_current_transform = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), paths.current_forward)
    )
    current_from_current_inverse = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), paths.current_inverse)
    )
    candidate = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), candidate_forward)
    )
    candidate_inverse_points = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), candidate_inverse)
    )
    candidate_inverse_point_exact_grid = None
    candidate_inverse_point_exact_ants = None
    if candidate_inverse_point_exact is not None:
        candidate_inverse_point_exact_grid = apply_grid_transform_to_points_ras(
            candidate_inverse_point_exact,
            source_ras,
        )
        candidate_inverse_point_exact_ants = lps_to_ras(
            apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), candidate_inverse_point_exact)
        )
    residual_only = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(current_mni_ras), residual_forward)
    )

    current_summary = _write_validation_csv(
        paths.output_dir / "validation_current_forward.csv",
        current_from_current_transform,
        current_mni_ras,
        params.precision_decimals,
    )
    current_inverse_summary = _write_validation_csv(
        paths.output_dir / "validation_current_inverse.csv",
        current_from_current_inverse,
        current_mni_ras,
        params.precision_decimals,
    )
    candidate_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_forward.csv",
        candidate,
        legacy_mni_ras,
        params.precision_decimals,
    )
    candidate_inverse_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_inverse.csv",
        candidate_inverse_points,
        legacy_mni_ras,
        params.precision_decimals,
    )
    candidate_inverse_point_exact_grid_summary = None
    candidate_inverse_point_exact_ants_summary = None
    if candidate_inverse_point_exact_grid is not None:
        candidate_inverse_point_exact_grid_summary = _write_validation_csv(
            paths.output_dir / "validation_candidate_inverse_point_exact_grid.csv",
            candidate_inverse_point_exact_grid,
            legacy_mni_ras,
            params.precision_decimals,
        )
    if candidate_inverse_point_exact_ants is not None:
        candidate_inverse_point_exact_ants_summary = _write_validation_csv(
            paths.output_dir / "validation_candidate_inverse_point_exact_ants.csv",
            candidate_inverse_point_exact_ants,
            legacy_mni_ras,
            params.precision_decimals,
        )
    residual_summary = _write_validation_csv(
        paths.output_dir / "validation_residual_only.csv",
        residual_only,
        legacy_mni_ras,
        params.precision_decimals,
    )
    logger.write(f"Current-inverse point sanity mean error: {current_inverse_summary['mean_error_mm']:.9g} mm")
    logger.write(f"Candidate-inverse point mean error: {candidate_inverse_summary['mean_error_mm']:.9g} mm")
    logger.write(f"Candidate-inverse point max error: {candidate_inverse_summary['max_error_mm']:.9g} mm")
    logger.write(f"Candidate-inverse rounded exact: {candidate_inverse_summary['rounded_exact']}")
    if candidate_inverse_point_exact_grid_summary is not None:
        logger.write(
            "Point-exact inverse grid max error: "
            f"{candidate_inverse_point_exact_grid_summary['max_error_mm']:.9g} mm"
        )
        logger.write(
            "Point-exact inverse grid rounded exact: "
            f"{candidate_inverse_point_exact_grid_summary['rounded_exact']}"
        )
    if candidate_inverse_point_exact_ants_summary is not None:
        logger.write(
            "Point-exact inverse ANTs max error: "
            f"{candidate_inverse_point_exact_ants_summary['max_error_mm']:.9g} mm"
        )
        logger.write(
            "Point-exact inverse ANTs rounded exact: "
            f"{candidate_inverse_point_exact_ants_summary['rounded_exact']}"
        )
    return {
        "current_forward_sanity": current_summary,
        "current_inverse_point_sanity": current_inverse_summary,
        "candidate_forward": candidate_summary,
        "candidate_inverse_point": candidate_inverse_summary,
        "candidate_inverse_point_exact_grid": candidate_inverse_point_exact_grid_summary,
        "candidate_inverse_point_exact_ants": candidate_inverse_point_exact_ants_summary,
        "residual_only": residual_summary,
    }


def apply_grid_transform_to_points_ras(transform: Path, points_ras: np.ndarray) -> np.ndarray:
    """Apply a displacement-grid transform to RAS points using trilinear sampling."""

    img = nib.load(str(transform))
    raw = np.asarray(img.dataobj)
    data, _vector_axis_kind = _displacement_data_view(raw)
    entries = _trilinear_entries(_points_to_voxel_indices(img.affine, points_ras), data.shape[:3])
    return np.asarray(points_ras, dtype=float) + _sample_displacement_data(data, entries)


def _displacement_data_view(data: np.ndarray) -> tuple[np.ndarray, str]:
    if data.ndim == 5 and data.shape[3] == 1 and data.shape[4] == 3:
        return data[:, :, :, 0, :], "nifti_5d_singleton"
    if data.ndim == 4 and data.shape[3] == 3:
        return data, "nifti_4d"
    raise ValueError(f"Unsupported displacement field shape: {data.shape}")


def _restore_displacement_data_shape(data: np.ndarray, vector_axis_kind: str) -> np.ndarray:
    if vector_axis_kind == "nifti_5d_singleton":
        return data[:, :, :, np.newaxis, :]
    if vector_axis_kind == "nifti_4d":
        return data
    raise ValueError(f"Unsupported displacement field axis kind: {vector_axis_kind}")


def _points_to_voxel_indices(affine: np.ndarray, points_ras: np.ndarray) -> np.ndarray:
    points = np.asarray(points_ras, dtype=float)
    homogeneous = np.c_[points, np.ones(points.shape[0])]
    return (np.linalg.inv(affine) @ homogeneous.T).T[:, :3]


def _trilinear_entries(indices: np.ndarray, shape: tuple[int, int, int]) -> list[list[tuple[tuple[int, int, int], float]]]:
    entries: list[list[tuple[tuple[int, int, int], float]]] = []
    max_index = np.asarray(shape, dtype=int) - 1
    for index in np.asarray(indices, dtype=float):
        lower = np.floor(index).astype(int)
        upper = lower + 1
        if np.any(lower < 0) or np.any(upper > max_index):
            raise ValueError(f"Point index {index.tolist()} is outside the displacement grid")
        fraction = index - lower
        point_entries: list[tuple[tuple[int, int, int], float]] = []
        for dx in (0, 1):
            wx = fraction[0] if dx else 1.0 - fraction[0]
            for dy in (0, 1):
                wy = fraction[1] if dy else 1.0 - fraction[1]
                for dz in (0, 1):
                    wz = fraction[2] if dz else 1.0 - fraction[2]
                    vertex = tuple((lower + np.array([dx, dy, dz], dtype=int)).tolist())
                    point_entries.append((vertex, float(wx * wy * wz)))
        entries.append(point_entries)
    return entries


def _sample_displacement_data(
    data: np.ndarray,
    entries: list[list[tuple[tuple[int, int, int], float]]],
) -> np.ndarray:
    samples = np.zeros((len(entries), 3), dtype=np.float64)
    for point_index, point_entries in enumerate(entries):
        for vertex, weight in point_entries:
            samples[point_index] += weight * data[vertex[0], vertex[1], vertex[2], :]
    return samples


def _write_validation_csv(
    output_csv: Path,
    observed: np.ndarray,
    expected: np.ndarray,
    decimals: int,
) -> dict:
    delta = observed - expected
    norms = np.linalg.norm(delta, axis=1)
    rounded_exact = bool(np.array_equal(np.round(observed, decimals), np.round(expected, decimals)))
    with output_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "contact_index",
                "observed_x",
                "observed_y",
                "observed_z",
                "expected_x",
                "expected_y",
                "expected_z",
                "delta_x",
                "delta_y",
                "delta_z",
                "error_mm",
                f"rounded_{decimals}_exact",
            ]
        )
        rounded_observed = np.round(observed, decimals)
        rounded_expected = np.round(expected, decimals)
        for idx in range(len(observed)):
            writer.writerow(
                [
                    idx,
                    *observed[idx],
                    *expected[idx],
                    *delta[idx],
                    norms[idx],
                    bool(np.array_equal(rounded_observed[idx], rounded_expected[idx])),
                ]
            )
    return {
        "mean_error_mm": float(norms.mean()),
        "max_error_mm": float(norms.max()),
        "rms_error_mm": float(np.sqrt(np.mean(norms**2))),
        "rounded_exact": rounded_exact,
        "rounded_decimals": decimals,
    }


def _write_ants_points_csv(path: Path, points_lps: np.ndarray) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y", "z", "t"])
        for point in points_lps:
            writer.writerow([f"{point[0]:.9f}", f"{point[1]:.9f}", f"{point[2]:.9f}", "0"])


def _read_ants_points_csv(path: Path) -> np.ndarray:
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append([float(row["x"]), float(row["y"]), float(row["z"])])
    return np.asarray(rows, dtype=float)


def _format_point(point: Iterable[float]) -> str:
    return ",".join(f"{float(value):.9f}" for value in point)


def _run_command(cmd: list[str], label: str, logger: "_Logger | None" = None) -> subprocess.CompletedProcess:
    if logger:
        logger.write(f"Running {label}")
        logger.write(" ".join(cmd))
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if logger and completed.stdout:
        logger.write(completed.stdout.rstrip())
    if logger and completed.stderr:
        logger.write(completed.stderr.rstrip())
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


class _Logger:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            path.unlink()

    def write(self, message: str) -> None:
        print(message)
        with self.path.open("a") as f:
            f.write(message + "\n")
