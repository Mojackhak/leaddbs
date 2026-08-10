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
from scipy.ndimage import map_coordinates
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
    inversion_max_iterations: int = 8
    inversion_tolerance_mm: float = 1e-5
    inversion_chunk_depth: int = 4


@dataclass(frozen=True)
class InstallPaths:
    """Input, output, and official target paths for installing one candidate."""

    lead_root: Path
    reconstruction_mat: Path
    cohort_pkl: Path
    current_forward: Path
    current_inverse: Path
    candidate_forward: Path
    candidate_inverse_point_exact: Path
    validation_summary: Path
    output_dir: Path
    subject_label: str = "Sub-ZhangMing"
    matlab_exe: Path = Path("/Applications/MATLAB_R2024b.app/bin/matlab")


@dataclass(frozen=True)
class InstallParams:
    """Safety thresholds and install behavior."""

    precision_decimals: int = 7
    max_point_exact_grid_error_mm: float = 1e-6
    max_derived_forward_contact_error_mm: float = 0.05
    max_round_trip_error_mm: float = 0.5
    abort_if_backup_exists: bool = True


RUN_OUTPUT_NAMES = (
    "landmarks.json",
    "landmarks.csv",
    "build_legacy_contact_compat.log",
    "residual_currentMni_to_legacyMni_rbf.h5",
    "residual_legacyMni_to_currentMni_rbf.h5",
    "residual_currentMni_to_legacyMni_rbf.nrrd",
    "residual_legacyMni_to_currentMni_rbf.nrrd",
    "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompat_ants.nii.gz",
    "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompatOrdinarySeed_ants.nii.gz",
    "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompat_ants.nii.gz",
    "candidate_from-MNI152NLin2009bAsym_to-anchorNative_desc-legacyContactCompatPointExact_ants.nii.gz",
    "validation_current_forward.csv",
    "validation_current_inverse.csv",
    "validation_candidate_forward.csv",
    "validation_candidate_forward_grid.csv",
    "validation_candidate_forward_parity.csv",
    "validation_candidate_inverse.csv",
    "validation_candidate_inverse_point_exact_grid.csv",
    "validation_candidate_inverse_point_exact_ants.csv",
    "validation_round_trip_anchor.csv",
    "validation_round_trip_mni.csv",
    "validation_residual_only.csv",
    "validation_summary.json",
    "numerical_inverse_summary.json",
)

_FIXED_POINT_MAX_ITERATIONS = 100
_FIXED_POINT_RELAXATION = 0.5


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
    ordinary_forward_seed = (
        paths.output_dir
        / "candidate_from-anchorNative_to-MNI152NLin2009bAsym_desc-legacyContactCompatOrdinarySeed_ants.nii.gz"
    )
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
        output_transform=ordinary_forward_seed,
        logger=logger,
        label="ordinary forward seed",
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
    write_point_exact_inverse_candidate(
        input_transform=candidate_inverse,
        output_transform=candidate_inverse_point_exact,
        source_ras=landmarks["source_for_forward"],
        target_ras=landmarks["legacy_mni"],
        logger=logger,
    )
    numerical_inverse = write_numerical_inverse_candidate(
        authoritative_transform=candidate_inverse_point_exact,
        initial_inverse_transform=ordinary_forward_seed,
        output_transform=candidate_forward,
        max_iterations=params.inversion_max_iterations,
        tolerance_mm=params.inversion_tolerance_mm,
        chunk_depth=params.inversion_chunk_depth,
        logger=logger,
    )
    with (paths.output_dir / "numerical_inverse_summary.json").open("w") as f:
        json.dump(numerical_inverse, f, indent=2)

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
        "ordinary_forward_seed": str(ordinary_forward_seed),
        "candidate_inverse": str(candidate_inverse),
        "candidate_inverse_point_exact": str(candidate_inverse_point_exact) if candidate_inverse_point_exact else None,
        "numerical_inverse": numerical_inverse,
        "validation": validation,
    }
    with (paths.output_dir / "validation_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)
    logger.write("Finished")
    return summary


def install_legacy_contact_compat(paths: InstallPaths, params: InstallParams) -> dict:
    """Install validated candidate transforms and legacy-compatible MNI reconstruction."""

    paths = _normalize_install_paths(paths)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    preflight = _preflight_install(paths, params)

    timestamp = datetime.now().isoformat(timespec="seconds")
    backup_dir = _subject_backup_dir(paths)
    backups = {
        "forward": _backup_path(paths.current_forward, backup_dir),
        "inverse": _backup_path(paths.current_inverse, backup_dir),
        "reconstruction": _backup_path(paths.reconstruction_mat, backup_dir),
    }
    targets = {
        "forward": paths.current_forward,
        "inverse": paths.current_inverse,
        "reconstruction": paths.reconstruction_mat,
    }
    sources = {
        "forward": paths.candidate_forward,
        "inverse": paths.candidate_inverse_point_exact,
    }

    with tempfile.TemporaryDirectory(prefix="warpslicer_install_") as tmp:
        tmp_path = Path(tmp)
        contacts_csv = tmp_path / "legacy_contacts_by_side.csv"
        updated_reconstruction = tmp_path / f"{paths.reconstruction_mat.stem}_installed.mat"
        _write_legacy_contacts_by_side_csv(contacts_csv, preflight["legacy_by_side"])
        _run_matlab_reconstruction_update(
            matlab_exe=paths.matlab_exe,
            lead_root=paths.lead_root,
            source_reconstruction=paths.reconstruction_mat,
            contacts_csv=contacts_csv,
            output_reconstruction=updated_reconstruction,
        )
        reconstruction_validation = _validate_reconstruction_mni(
            updated_reconstruction,
            preflight["legacy_by_side"],
            params.precision_decimals,
        )
        if not reconstruction_validation["rounded_exact"]:
            raise RuntimeError("Updated reconstruction does not match legacy contacts")

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            for key, backup in backups.items():
                shutil.move(str(targets[key]), str(backup))
            shutil.copy2(sources["forward"], paths.current_forward)
            shutil.copy2(sources["inverse"], paths.current_inverse)
            shutil.copy2(updated_reconstruction, paths.reconstruction_mat)

            post_validation = _post_validate_install(
                paths,
                params,
                preflight,
                backups,
                sources,
            )
        except Exception:
            _rollback_installed_files(backups, targets)
            raise

    install_record = {
        "installed_at": timestamp,
        "subject": paths.subject_label,
        "policy": "point_exact_authoritative_inverse_derived_forward",
        "targets": {key: str(path) for key, path in targets.items()},
        "sources": {key: str(path) for key, path in sources.items()},
        "backup_dir": str(backup_dir),
        "backups": {key: str(path) for key, path in backups.items()},
        "validation_summary": str(paths.validation_summary),
        "preflight_validation": preflight["validation"],
        "reconstruction_validation": reconstruction_validation,
        "post_install_validation": post_validation,
    }
    record_path = paths.output_dir / "install_legacy_contact_compat.json"
    with record_path.open("w") as f:
        json.dump(install_record, f, indent=2)
    install_record["install_record"] = str(record_path)
    return install_record


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


def write_numerical_inverse_candidate(
    authoritative_transform: Path,
    initial_inverse_transform: Path,
    output_transform: Path,
    max_iterations: int = 8,
    tolerance_mm: float = 1e-5,
    chunk_depth: int = 1,
    logger: "_Logger | None" = None,
) -> dict:
    """Numerically invert one authoritative displacement field on a target grid."""

    authoritative_transform = Path(authoritative_transform)
    initial_inverse_transform = Path(initial_inverse_transform)
    output_transform = Path(output_transform)
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm must be positive")
    if chunk_depth < 1:
        raise ValueError("chunk_depth must be at least 1")

    authoritative_img = nib.load(str(authoritative_transform))
    authoritative_raw = np.asarray(authoritative_img.dataobj, dtype=np.float32)
    authoritative_data, _ = _displacement_data_view(authoritative_raw)
    authoritative_shape = np.asarray(authoritative_data.shape[:3], dtype=int)
    authoritative_inverse_affine = np.linalg.inv(authoritative_img.affine)

    gradients = []
    for component in range(3):
        gradients.append(np.gradient(authoritative_data[..., component], edge_order=1))

    initial_img = nib.load(str(initial_inverse_transform))
    initial_raw = np.asarray(initial_img.dataobj, dtype=np.float32)
    initial_data, vector_axis_kind = _displacement_data_view(initial_raw)
    target_shape = tuple(int(value) for value in initial_data.shape[:3])

    output_transform.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(prefix="warpslicer_inverse_", suffix=".dat", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    output_memmap = np.memmap(temporary_path, dtype=np.float64, mode="w+", shape=target_shape + (3,))
    output_memmap[:] = 0.0

    total_points = int(np.prod(target_shape))
    candidate_count = 0
    converged_count = 0
    newton_converged_count = 0
    fixed_point_converged_count = 0
    residual_sum = 0.0
    residual_max = 0.0
    identity_count = 0
    if logger:
        logger.write(
            "Numerically inverting PointExact field "
            f"with {max_iterations} Newton iterations and {tolerance_mm:.9g} mm tolerance"
        )

    try:
        for z_start in range(0, target_shape[2], chunk_depth):
            z_stop = min(z_start + chunk_depth, target_shape[2])
            local_shape = (target_shape[0], target_shape[1], z_stop - z_start)
            indices = np.indices(local_shape, dtype=np.float64).reshape(3, -1).T
            indices[:, 2] += z_start
            target_points = nib.affines.apply_affine(initial_img.affine, indices)
            initial_displacement = np.asarray(
                initial_data[:, :, z_start:z_stop, :], dtype=np.float64
            ).reshape(-1, 3)
            estimates = target_points + initial_displacement
            source_indices = nib.affines.apply_affine(authoritative_inverse_affine, estimates)
            candidates = _indices_inside_volume(source_indices, authoritative_shape)
            identity_count += int((~candidates).sum())
            candidate_count += int(candidates.sum())

            candidate_rows = np.flatnonzero(candidates)
            initial_candidate_estimates = estimates[candidates].copy()
            candidate_estimates = initial_candidate_estimates.copy()
            candidate_targets = target_points[candidates]
            converged = np.zeros(len(candidate_rows), dtype=bool)
            active = np.ones(len(candidate_rows), dtype=bool)
            final_residuals = np.full(len(candidate_rows), np.inf, dtype=np.float64)

            for _iteration in range(max_iterations):
                active_rows = np.flatnonzero(active)
                if len(active_rows) == 0:
                    break
                active_estimates = candidate_estimates[active_rows]
                active_source_indices = nib.affines.apply_affine(
                    authoritative_inverse_affine,
                    active_estimates,
                )
                inside = _indices_inside_volume(active_source_indices, authoritative_shape)
                if not np.all(inside):
                    active[active_rows[~inside]] = False
                solve_rows = active_rows[inside]
                if len(solve_rows) == 0:
                    continue
                solve_indices = active_source_indices[inside]
                displacement = _sample_vector_data(authoritative_data, solve_indices)
                residual = candidate_estimates[solve_rows] + displacement - candidate_targets[solve_rows]
                residual_norm = np.linalg.norm(residual, axis=1)
                now_converged = residual_norm <= tolerance_mm
                if np.any(now_converged):
                    rows = solve_rows[now_converged]
                    converged[rows] = True
                    active[rows] = False
                    final_residuals[rows] = residual_norm[now_converged]

                update_rows = solve_rows[~now_converged]
                if len(update_rows) == 0:
                    continue
                update_indices = solve_indices[~now_converged]
                update_residual = residual[~now_converged]
                jacobian_index = _sample_displacement_gradient(gradients, update_indices)
                jacobian_world = jacobian_index @ authoritative_inverse_affine[:3, :3]
                jacobian = jacobian_world + np.eye(3, dtype=np.float64)[np.newaxis, :, :]
                determinant = np.linalg.det(jacobian)
                solvable = np.isfinite(determinant) & (np.abs(determinant) > 1e-6)
                if not np.all(solvable):
                    active[update_rows[~solvable]] = False
                if np.any(solvable):
                    delta = np.linalg.solve(
                        jacobian[solvable],
                        update_residual[solvable, :, np.newaxis],
                    )[:, :, 0]
                    candidate_estimates[update_rows[solvable]] -= delta

            remaining_rows = np.flatnonzero(active)
            if len(remaining_rows):
                remaining_indices = nib.affines.apply_affine(
                    authoritative_inverse_affine,
                    candidate_estimates[remaining_rows],
                )
                inside = _indices_inside_volume(remaining_indices, authoritative_shape)
                if np.any(inside):
                    rows = remaining_rows[inside]
                    displacement = _sample_vector_data(authoritative_data, remaining_indices[inside])
                    residual = candidate_estimates[rows] + displacement - candidate_targets[rows]
                    residual_norm = np.linalg.norm(residual, axis=1)
                    now_converged = residual_norm <= tolerance_mm
                    converged[rows[now_converged]] = True
                    final_residuals[rows[now_converged]] = residual_norm[now_converged]

            chunk_newton_converged_count = int(converged.sum())
            newton_converged_count += chunk_newton_converged_count
            fallback_rows = np.flatnonzero(~converged)
            if len(fallback_rows):
                fallback_estimates = initial_candidate_estimates[fallback_rows].copy()
                fallback_targets = candidate_targets[fallback_rows]
                fallback_converged = np.zeros(len(fallback_rows), dtype=bool)
                fallback_active = np.ones(len(fallback_rows), dtype=bool)
                fallback_residuals = np.full(len(fallback_rows), np.inf, dtype=np.float64)
                for _iteration in range(_FIXED_POINT_MAX_ITERATIONS + 1):
                    active_rows = np.flatnonzero(fallback_active)
                    if len(active_rows) == 0:
                        break
                    active_estimates = fallback_estimates[active_rows]
                    active_indices = nib.affines.apply_affine(
                        authoritative_inverse_affine,
                        active_estimates,
                    )
                    inside = _indices_inside_volume(active_indices, authoritative_shape)
                    if not np.all(inside):
                        fallback_active[active_rows[~inside]] = False
                    solve_rows = active_rows[inside]
                    if len(solve_rows) == 0:
                        continue
                    displacement = _sample_vector_data(authoritative_data, active_indices[inside])
                    residual = fallback_estimates[solve_rows] + displacement - fallback_targets[solve_rows]
                    residual_norm = np.linalg.norm(residual, axis=1)
                    now_converged = residual_norm <= tolerance_mm
                    if np.any(now_converged):
                        rows = solve_rows[now_converged]
                        fallback_converged[rows] = True
                        fallback_active[rows] = False
                        fallback_residuals[rows] = residual_norm[now_converged]
                    if _iteration == _FIXED_POINT_MAX_ITERATIONS:
                        continue
                    update_rows = solve_rows[~now_converged]
                    if len(update_rows):
                        fallback_estimates[update_rows] -= (
                            _FIXED_POINT_RELAXATION * residual[~now_converged]
                        )

                if np.any(fallback_converged):
                    solved_fallback_rows = fallback_rows[fallback_converged]
                    candidate_estimates[solved_fallback_rows] = fallback_estimates[fallback_converged]
                    converged[solved_fallback_rows] = True
                    final_residuals[solved_fallback_rows] = fallback_residuals[fallback_converged]
                    fixed_point_converged_count += int(fallback_converged.sum())

            if np.any(converged):
                solved_rows = candidate_rows[converged]
                solved_displacement = candidate_estimates[converged] - candidate_targets[converged]
                output_chunk = np.zeros(local_shape + (3,), dtype=np.float64)
                output_chunk_flat = output_chunk.reshape(-1, 3)
                output_chunk_flat[solved_rows] = solved_displacement
                output_memmap[:, :, z_start:z_stop, :] = output_chunk
                residuals = final_residuals[converged]
                converged_count += int(converged.sum())
                residual_sum += float(residuals.sum())
                residual_max = max(residual_max, float(residuals.max()))

            if logger and (z_stop == target_shape[2] or z_stop % max(1, target_shape[2] // 10) == 0):
                logger.write(f"Numerical inverse progress: {z_stop}/{target_shape[2]} slices")

        output_memmap.flush()
        header = initial_img.header.copy()
        header.set_data_dtype(np.float64)
        header.set_intent("displacement vector")
        output_data = _restore_displacement_data_shape(output_memmap, vector_axis_kind)
        output_img = nib.Nifti1Image(output_data, initial_img.affine, header=header)
        output_img.set_qform(initial_img.get_qform(), int(initial_img.header["qform_code"]))
        output_img.set_sform(initial_img.get_sform(), int(initial_img.header["sform_code"]))
        nib.save(output_img, str(output_transform))
    finally:
        del output_memmap
        temporary_path.unlink(missing_ok=True)

    summary = {
        "authoritative_transform": str(authoritative_transform),
        "initial_inverse_transform": str(initial_inverse_transform),
        "output_transform": str(output_transform),
        "method": "chunked_newton_with_damped_fixed_point_fallback",
        "max_iterations": int(max_iterations),
        "tolerance_mm": float(tolerance_mm),
        "total_grid_point_count": total_points,
        "candidate_point_count": candidate_count,
        "identity_outside_authoritative_domain_count": identity_count,
        "converged_point_count": converged_count,
        "newton_converged_point_count": newton_converged_count,
        "fixed_point_converged_point_count": fixed_point_converged_count,
        "fixed_point_max_iterations": _FIXED_POINT_MAX_ITERATIONS,
        "fixed_point_relaxation": _FIXED_POINT_RELAXATION,
        "nonconverged_point_count": candidate_count - converged_count,
        "mean_converged_residual_mm": residual_sum / converged_count if converged_count else None,
        "max_converged_residual_mm": residual_max if converged_count else None,
    }
    if logger:
        logger.write(
            "Numerical inverse convergence: "
            f"{converged_count}/{candidate_count}; "
            f"newton={newton_converged_count}; fixed_point={fixed_point_converged_count}; "
            f"nonconverged={candidate_count - converged_count}"
        )
        logger.write(f"Numerical inverse max converged residual: {residual_max:.9g} mm")
    return summary


def _indices_inside_volume(indices: np.ndarray, shape: np.ndarray) -> np.ndarray:
    return np.all((indices >= 0.0) & (indices <= (shape - 1)), axis=1)


def _sample_vector_data(data: np.ndarray, indices: np.ndarray) -> np.ndarray:
    coordinates = np.asarray(indices, dtype=np.float64).T
    return np.column_stack(
        [
            map_coordinates(data[..., component], coordinates, order=1, mode="nearest", prefilter=False)
            for component in range(3)
        ]
    )


def _sample_displacement_gradient(gradients: list[tuple[np.ndarray, ...]], indices: np.ndarray) -> np.ndarray:
    coordinates = np.asarray(indices, dtype=np.float64).T
    sampled = np.empty((len(indices), 3, 3), dtype=np.float64)
    for component in range(3):
        for axis in range(3):
            sampled[:, component, axis] = map_coordinates(
                gradients[component][axis],
                coordinates,
                order=1,
                mode="nearest",
                prefilter=False,
            )
    return sampled


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


def _normalize_install_paths(paths: InstallPaths) -> InstallPaths:
    values = {field: getattr(paths, field) for field in paths.__dataclass_fields__}
    for key, value in values.items():
        if key not in {"subject_label"} and value is not None:
            values[key] = Path(value)
    return InstallPaths(**values)


def _preflight_install(paths: InstallPaths, params: InstallParams) -> dict:
    required = [
        paths.reconstruction_mat,
        paths.cohort_pkl,
        paths.current_forward,
        paths.current_inverse,
        paths.candidate_forward,
        paths.candidate_inverse_point_exact,
        paths.validation_summary,
        paths.matlab_exe,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    backup_dir = _subject_backup_dir(paths)
    backups = [
        _backup_path(paths.current_forward, backup_dir),
        _backup_path(paths.current_inverse, backup_dir),
        _backup_path(paths.reconstruction_mat, backup_dir),
    ]
    existing_backups = [str(path) for path in backups if path.exists()]
    if existing_backups and params.abort_if_backup_exists:
        raise FileExistsError("Backup files already exist:\n" + "\n".join(existing_backups))

    with paths.validation_summary.open() as f:
        validation_summary = json.load(f)
    _require_summary_path(validation_summary, "candidate_forward", paths.candidate_forward)
    _require_summary_path(validation_summary, "candidate_inverse_point_exact", paths.candidate_inverse_point_exact)
    point_exact_grid = validation_summary["validation"]["candidate_inverse_point_exact_grid"]
    if not point_exact_grid["rounded_exact"]:
        raise ValueError("PointExact grid validation is not rounded-exact")
    if float(point_exact_grid["max_error_mm"]) > params.max_point_exact_grid_error_mm:
        raise ValueError(
            "PointExact grid max error exceeds threshold: "
            f"{point_exact_grid['max_error_mm']} > {params.max_point_exact_grid_error_mm}"
        )
    numerical_inverse = validation_summary.get("numerical_inverse")
    if not numerical_inverse:
        raise ValueError("Validation summary does not contain numerical inverse provenance")
    derived_forward = validation_summary["validation"]["candidate_forward_grid"]
    if float(derived_forward["max_error_mm"]) > params.max_derived_forward_contact_error_mm:
        raise ValueError(
            "Derived forward contact error exceeds threshold: "
            f"{derived_forward['max_error_mm']} > {params.max_derived_forward_contact_error_mm}"
        )
    for key in ("round_trip_anchor", "round_trip_mni"):
        round_trip = validation_summary["validation"][key]
        if float(round_trip["max_error_mm"]) > params.max_round_trip_error_mm:
            raise ValueError(
                f"{key} max error exceeds threshold: "
                f"{round_trip['max_error_mm']} > {params.max_round_trip_error_mm}"
            )

    legacy_by_side = _legacy_contacts_by_side(paths)
    reconstruction_validation = _validate_reconstruction_side_shapes(paths.reconstruction_mat, legacy_by_side)
    source_for_forward = _source_for_forward_points(paths)
    legacy_points = np.vstack(
        [legacy_by_side[side][["MNI_x", "MNI_y", "MNI_z"]].to_numpy(float) for side in (2, 1)]
    )
    return {
        "validation": point_exact_grid,
        "numerical_inverse": numerical_inverse,
        "derived_forward_validation": derived_forward,
        "legacy_by_side": legacy_by_side,
        "reconstruction_shape_validation": reconstruction_validation,
        "source_for_forward": source_for_forward,
        "legacy_points": legacy_points,
        "original_sizes": {
            "forward": paths.current_forward.stat().st_size,
            "inverse": paths.current_inverse.stat().st_size,
            "reconstruction": paths.reconstruction_mat.stat().st_size,
        },
    }


def _subject_backup_dir(paths: InstallPaths) -> Path:
    return paths.reconstruction_mat.parent.parent / "bak"


def _backup_path(path: Path, backup_dir: Path) -> Path:
    if path.name.endswith(".nii.gz"):
        return backup_dir / (path.name[:-7] + "-bak.nii.gz")
    return backup_dir / (path.stem + "-bak" + path.suffix)


def _require_summary_path(summary: dict, key: str, expected: Path) -> None:
    observed = Path(summary[key])
    if observed.resolve() != expected.resolve():
        raise ValueError(f"Validation summary {key} does not match expected path: {observed} != {expected}")


def _legacy_contacts_by_side(paths: InstallPaths) -> dict[int, pd.DataFrame]:
    cohort = pd.read_pickle(paths.cohort_pkl)
    rows = cohort[cohort["Subject"].eq(paths.subject_label)].sort_values("Contact")
    if len(rows) == 0:
        raise ValueError(f"No cohort rows found for {paths.subject_label}")
    required = {"Contact", "Side", "MNI_x", "MNI_y", "MNI_z"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"Missing legacy cohort columns: {sorted(missing)}")
    side_map = {1: "Right", 2: "Left"}
    by_side: dict[int, pd.DataFrame] = {}
    for side_index, side_label in side_map.items():
        side_rows = rows[rows["Side"].eq(side_label)].sort_values("Contact")
        if len(side_rows) == 0:
            raise ValueError(f"No {side_label} contacts found for {paths.subject_label}")
        by_side[side_index] = side_rows[["Contact", "Side", "MNI_x", "MNI_y", "MNI_z"]].copy()
    return by_side


def _validate_reconstruction_side_shapes(reconstruction_mat: Path, legacy_by_side: dict[int, pd.DataFrame]) -> dict:
    mat = loadmat(reconstruction_mat, squeeze_me=True, struct_as_record=False)
    reco = mat["reco"]
    coords = np.asarray(reco.mni.coords_mm, dtype=object)
    observed_counts = {}
    expected_counts = {}
    for side_index, side_rows in legacy_by_side.items():
        observed = np.asarray(coords[side_index - 1], dtype=float)
        observed_counts[str(side_index)] = int(observed.shape[0])
        expected_counts[str(side_index)] = int(len(side_rows))
        if observed.shape[0] != len(side_rows):
            raise ValueError(
                f"Side {side_index} reconstruction contact count mismatch: "
                f"{observed.shape[0]} != {len(side_rows)}"
            )
    return {"observed_counts": observed_counts, "expected_counts": expected_counts}


def _source_for_forward_points(paths: InstallPaths) -> np.ndarray:
    mat = loadmat(paths.reconstruction_mat, squeeze_me=True, struct_as_record=False)
    reco = mat["reco"]
    cohort = pd.read_pickle(paths.cohort_pkl)
    rows = cohort[cohort["Subject"].eq(paths.subject_label)].sort_values("Contact")
    source_coords = reco.scrf.coords_mm if hasattr(reco, "scrf") else reco.native.coords_mm
    return _coords_from_reco_by_contact_order(source_coords, rows)


def _write_legacy_contacts_by_side_csv(path: Path, legacy_by_side: dict[int, pd.DataFrame]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["side_index", "contact", "side", "mni_x", "mni_y", "mni_z"])
        for side_index in sorted(legacy_by_side):
            for _, row in legacy_by_side[side_index].iterrows():
                writer.writerow(
                    [
                        side_index,
                        int(row["Contact"]),
                        str(row["Side"]),
                        f"{float(row['MNI_x']):.9f}",
                        f"{float(row['MNI_y']):.9f}",
                        f"{float(row['MNI_z']):.9f}",
                    ]
                )


def _run_matlab_reconstruction_update(
    matlab_exe: Path,
    lead_root: Path,
    source_reconstruction: Path,
    contacts_csv: Path,
    output_reconstruction: Path,
) -> None:
    script = output_reconstruction.parent / "warpslicer_update_reconstruction_mni.m"
    script.write_text(
        _matlab_update_script(
            lead_root=lead_root,
            source_reconstruction=source_reconstruction,
            contacts_csv=contacts_csv,
            output_reconstruction=output_reconstruction,
        )
    )
    cmd = [str(matlab_exe), "-batch", f"run('{_matlab_quote(script)}')"]
    _run_command(cmd, "MATLAB reconstruction MNI update")


def _matlab_update_script(
    lead_root: Path,
    source_reconstruction: Path,
    contacts_csv: Path,
    output_reconstruction: Path,
) -> str:
    return f"""
addpath(genpath('{_matlab_quote(lead_root)}'));
contacts = readtable('{_matlab_quote(contacts_csv)}');
loaded = load('{_matlab_quote(source_reconstruction)}', 'reco');
reco = loaded.reco;
options = struct();
options.elmodel = reco.props(1).elmodel;
options = ea_resolve_elspec(options);
if numel(options.elspec.etageidx) > 8
    scaleFactor = options.elspec.contact_span * 1.5;
else
    scaleFactor = options.elspec.contact_span * 2;
end

reco = setLegacyMni(reco, contacts, options, scaleFactor);
save('{_matlab_quote(output_reconstruction)}', 'reco');
ea_recalc_angles('{_matlab_quote(output_reconstruction)}');
loaded = load('{_matlab_quote(output_reconstruction)}', 'reco');
reco = loaded.reco;
if ~isfield(reco, 'mni')
    error('Updated reconstruction does not contain reco.mni');
end
reco = setLegacyMni(reco, contacts, options, scaleFactor);
save('{_matlab_quote(output_reconstruction)}', 'reco');
loaded = load('{_matlab_quote(output_reconstruction)}', 'reco');
if ~isfield(loaded.reco, 'mni')
    error('Updated reconstruction does not contain reco.mni');
end

function reco = setLegacyMni(reco, contacts, options, scaleFactor)
for side = 1:2
    sideContacts = contacts(contacts.side_index == side, :);
    coords = [sideContacts.mni_x, sideContacts.mni_y, sideContacts.mni_z];
    if isempty(coords)
        error('No contacts were provided for side %d', side);
    end
    reco.mni.coords_mm{{side}} = coords;
    head = coords(1, :);
    tail = coords(end, :);
    reco.mni.markers(side).head = head;
    reco.mni.markers(side).tail = tail;
    trajvector = (tail - head) ./ norm(tail - head);
    reco.mni.trajvector{{side}} = trajvector;
    trajStart = head - trajvector * 5;
    trajEnd = tail + trajvector * scaleFactor;
    reco.mni.trajectory{{side}} = [ ...
        linspace(trajStart(1), trajEnd(1), 50)', ...
        linspace(trajStart(2), trajEnd(2), 50)', ...
        linspace(trajStart(3), trajEnd(3), 50)' ...
    ];
    if isfield(reco, 'native') && numel(reco.native.markers) >= side && ~isempty(reco.native.markers(side).y)
        [~, yvec] = ea_calc_rotation(reco.native.markers(side).y, reco.native.markers(side).head);
        [xunitv, yunitv] = ea_calcxy(head, tail, yvec);
    else
        [xunitv, yunitv] = ea_calcxy(head, tail);
    end
    reco.mni.markers(side).x = head + xunitv * (options.elspec.lead_diameter / 2);
    reco.mni.markers(side).y = head + yunitv * (options.elspec.lead_diameter / 2);
end
end
"""


def _matlab_quote(path: Path) -> str:
    return str(path).replace("'", "''")


def _validate_reconstruction_mni(
    reconstruction_mat: Path,
    legacy_by_side: dict[int, pd.DataFrame],
    decimals: int,
) -> dict:
    mat = loadmat(reconstruction_mat, squeeze_me=True, struct_as_record=False)
    reco = mat["reco"]
    coords = np.asarray(reco.mni.coords_mm, dtype=object)
    observed_all = []
    expected_all = []
    per_side = {}
    for side_index, side_rows in legacy_by_side.items():
        observed = np.asarray(coords[side_index - 1], dtype=float)
        expected = side_rows[["MNI_x", "MNI_y", "MNI_z"]].to_numpy(float)
        delta = observed - expected
        norms = np.linalg.norm(delta, axis=1)
        rounded_exact = bool(np.array_equal(np.round(observed, decimals), np.round(expected, decimals)))
        per_side[str(side_index)] = {
            "mean_error_mm": float(norms.mean()),
            "max_error_mm": float(norms.max()),
            "rounded_exact": rounded_exact,
            "contact_count": int(len(expected)),
        }
        observed_all.append(observed)
        expected_all.append(expected)
    observed_full = np.vstack(observed_all)
    expected_full = np.vstack(expected_all)
    norms_full = np.linalg.norm(observed_full - expected_full, axis=1)
    return {
        "mean_error_mm": float(norms_full.mean()),
        "max_error_mm": float(norms_full.max()),
        "rounded_exact": bool(
            np.array_equal(np.round(observed_full, decimals), np.round(expected_full, decimals))
        ),
        "rounded_decimals": decimals,
        "per_side": per_side,
    }


def _post_validate_install(
    paths: InstallPaths,
    params: InstallParams,
    preflight: dict,
    backups: dict[str, Path],
    sources: dict[str, Path],
) -> dict:
    size_validation = {
        "forward_matches_candidate": paths.current_forward.stat().st_size == sources["forward"].stat().st_size,
        "inverse_matches_candidate": paths.current_inverse.stat().st_size == sources["inverse"].stat().st_size,
        "forward_backup_matches_original": backups["forward"].stat().st_size == preflight["original_sizes"]["forward"],
        "inverse_backup_matches_original": backups["inverse"].stat().st_size == preflight["original_sizes"]["inverse"],
        "reconstruction_backup_matches_original": (
            backups["reconstruction"].stat().st_size == preflight["original_sizes"]["reconstruction"]
        ),
    }
    if not all(size_validation.values()):
        raise RuntimeError(f"Post-install size validation failed: {size_validation}")

    reconstruction_validation = _validate_reconstruction_mni(
        paths.reconstruction_mat,
        preflight["legacy_by_side"],
        params.precision_decimals,
    )
    if not reconstruction_validation["rounded_exact"]:
        raise RuntimeError("Installed reconstruction does not match legacy contacts")

    source_points = preflight["source_for_forward"]
    legacy_points = preflight["legacy_points"]
    observed = apply_grid_transform_to_points_ras(paths.current_inverse, source_points)
    grid_validation = _summarize_point_errors(observed, legacy_points, params.precision_decimals)
    if not grid_validation["rounded_exact"]:
        raise RuntimeError("Installed PointExact inverse grid validation is not rounded-exact")
    recovered_source = apply_grid_transform_to_points_ras(paths.current_forward, legacy_points)
    forward_validation = _summarize_point_errors(recovered_source, source_points, params.precision_decimals)
    if float(forward_validation["max_error_mm"]) > params.max_derived_forward_contact_error_mm:
        raise RuntimeError("Installed derived forward contact validation failed")
    anchor_round_trip = apply_grid_transform_to_points_ras(paths.current_forward, observed)
    mni_round_trip = apply_grid_transform_to_points_ras(paths.current_inverse, recovered_source)
    round_trip_anchor = _summarize_point_errors(anchor_round_trip, source_points, params.precision_decimals)
    round_trip_mni = _summarize_point_errors(mni_round_trip, legacy_points, params.precision_decimals)
    if max(round_trip_anchor["max_error_mm"], round_trip_mni["max_error_mm"]) > params.max_round_trip_error_mm:
        raise RuntimeError("Installed transform-pair round-trip validation failed")
    return {
        "sizes": size_validation,
        "reconstruction": reconstruction_validation,
        "installed_point_exact_grid": grid_validation,
        "installed_derived_forward_grid": forward_validation,
        "round_trip_anchor": round_trip_anchor,
        "round_trip_mni": round_trip_mni,
    }


def _summarize_point_errors(observed: np.ndarray, expected: np.ndarray, decimals: int) -> dict:
    delta = observed - expected
    norms = np.linalg.norm(delta, axis=1)
    return {
        "mean_error_mm": float(norms.mean()),
        "max_error_mm": float(norms.max()),
        "rms_error_mm": float(np.sqrt(np.mean(norms**2))),
        "rounded_exact": bool(np.array_equal(np.round(observed, decimals), np.round(expected, decimals))),
        "rounded_decimals": decimals,
    }


def _rollback_installed_files(backups: dict[str, Path], targets: dict[str, Path]) -> None:
    for key, backup in backups.items():
        if backup.is_file():
            shutil.copy2(backup, targets[key])


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
    candidate_inverse_point_exact: Path,
    logger: "_Logger",
) -> dict:
    current_from_current_transform = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(current_mni_ras), paths.current_forward)
    )
    current_from_current_inverse = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), paths.current_inverse)
    )
    candidate_forward_grid = apply_grid_transform_to_points_ras(candidate_forward, legacy_mni_ras)
    candidate_forward_ants = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(legacy_mni_ras), candidate_forward)
    )
    candidate_inverse_points = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), candidate_inverse)
    )
    candidate_inverse_point_exact_grid = apply_grid_transform_to_points_ras(
        candidate_inverse_point_exact,
        source_ras,
    )
    candidate_inverse_point_exact_ants = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(source_ras), candidate_inverse_point_exact)
    )
    anchor_round_trip = apply_grid_transform_to_points_ras(
        candidate_forward,
        candidate_inverse_point_exact_grid,
    )
    mni_round_trip = apply_grid_transform_to_points_ras(
        candidate_inverse_point_exact,
        candidate_forward_grid,
    )
    residual_only = lps_to_ras(
        apply_ants_transform_to_points(ants_points, ras_to_lps(current_mni_ras), residual_forward)
    )

    current_summary = _write_validation_csv(
        paths.output_dir / "validation_current_forward.csv",
        current_from_current_transform,
        source_ras,
        params.precision_decimals,
    )
    current_inverse_summary = _write_validation_csv(
        paths.output_dir / "validation_current_inverse.csv",
        current_from_current_inverse,
        current_mni_ras,
        params.precision_decimals,
    )
    candidate_forward_ants_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_forward.csv",
        candidate_forward_ants,
        source_ras,
        params.precision_decimals,
    )
    candidate_forward_grid_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_forward_grid.csv",
        candidate_forward_grid,
        source_ras,
        params.precision_decimals,
    )
    candidate_forward_parity_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_forward_parity.csv",
        candidate_forward_grid,
        candidate_forward_ants,
        params.precision_decimals,
    )
    candidate_inverse_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_inverse.csv",
        candidate_inverse_points,
        legacy_mni_ras,
        params.precision_decimals,
    )
    candidate_inverse_point_exact_grid_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_inverse_point_exact_grid.csv",
        candidate_inverse_point_exact_grid,
        legacy_mni_ras,
        params.precision_decimals,
    )
    candidate_inverse_point_exact_ants_summary = _write_validation_csv(
        paths.output_dir / "validation_candidate_inverse_point_exact_ants.csv",
        candidate_inverse_point_exact_ants,
        legacy_mni_ras,
        params.precision_decimals,
    )
    anchor_round_trip_summary = _write_validation_csv(
        paths.output_dir / "validation_round_trip_anchor.csv",
        anchor_round_trip,
        source_ras,
        params.precision_decimals,
    )
    mni_round_trip_summary = _write_validation_csv(
        paths.output_dir / "validation_round_trip_mni.csv",
        mni_round_trip,
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
    logger.write(f"Derived-forward grid max error: {candidate_forward_grid_summary['max_error_mm']:.9g} mm")
    logger.write(f"Derived-forward ANTs max error: {candidate_forward_ants_summary['max_error_mm']:.9g} mm")
    logger.write(f"Derived-forward grid/ANTs parity max error: {candidate_forward_parity_summary['max_error_mm']:.9g} mm")
    logger.write(
        "Point-exact inverse grid max error: "
        f"{candidate_inverse_point_exact_grid_summary['max_error_mm']:.9g} mm"
    )
    logger.write(
        "Point-exact inverse grid rounded exact: "
        f"{candidate_inverse_point_exact_grid_summary['rounded_exact']}"
    )
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
        "candidate_forward": candidate_forward_ants_summary,
        "candidate_forward_grid": candidate_forward_grid_summary,
        "candidate_forward_parity": candidate_forward_parity_summary,
        "candidate_inverse_point": candidate_inverse_summary,
        "candidate_inverse_point_exact_grid": candidate_inverse_point_exact_grid_summary,
        "candidate_inverse_point_exact_ants": candidate_inverse_point_exact_ants_summary,
        "round_trip_anchor": anchor_round_trip_summary,
        "round_trip_mni": mni_round_trip_summary,
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
        if np.any(index < 0.0) or np.any(index > max_index):
            raise ValueError(f"Point index {index.tolist()} is outside the displacement grid")
        lower = np.minimum(np.floor(index).astype(int), max_index - 1)
        upper = lower + 1
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
