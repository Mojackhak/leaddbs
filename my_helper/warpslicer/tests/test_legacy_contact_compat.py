from pathlib import Path

import nibabel as nib
import numpy as np

from my_helper.warpslicer.legacy_contact_compat import (
    apply_grid_transform_to_points_ras,
    write_numerical_inverse_candidate,
)


def _write_displacement(path: Path, data: np.ndarray, affine: np.ndarray) -> None:
    header = nib.Nifti1Header()
    header.set_data_dtype(np.float64)
    header.set_intent("displacement vector")
    image = nib.Nifti1Image(data[:, :, :, np.newaxis, :], affine, header=header)
    image.set_qform(affine, 1)
    image.set_sform(affine, 1)
    nib.save(image, str(path))


def test_numerical_inverse_is_derived_from_authoritative_field(tmp_path: Path) -> None:
    shape = (8, 8, 8)
    affine = np.eye(4)
    indices = np.indices(shape, dtype=np.float64).reshape(3, -1).T
    points = nib.affines.apply_affine(affine, indices)
    linear = np.diag([1.05, 1.03, 1.02])
    displacement = (points @ linear.T - points).reshape(shape + (3,))

    authoritative = tmp_path / "authoritative.nii.gz"
    ordinary_seed = tmp_path / "ordinary_seed.nii.gz"
    derived = tmp_path / "derived.nii.gz"
    _write_displacement(authoritative, displacement, affine)
    _write_displacement(ordinary_seed, np.zeros(shape + (3,), dtype=np.float64), affine)

    summary = write_numerical_inverse_candidate(
        authoritative_transform=authoritative,
        initial_inverse_transform=ordinary_seed,
        output_transform=derived,
        max_iterations=4,
        tolerance_mm=1e-7,
        chunk_depth=2,
    )

    assert summary["nonconverged_point_count"] == 0
    assert summary["max_converged_residual_mm"] < 1e-7
    assert nib.load(str(derived)).header.get_intent()[0] == "displacement vector"

    target_points = points
    recovered_source = apply_grid_transform_to_points_ras(derived, target_points)
    round_trip = apply_grid_transform_to_points_ras(authoritative, recovered_source)
    np.testing.assert_allclose(round_trip, target_points, atol=1e-6)


def test_numerical_inverse_writes_identity_outside_authoritative_domain(tmp_path: Path) -> None:
    authoritative_shape = (5, 5, 5)
    target_shape = (7, 7, 7)
    affine = np.eye(4)
    authoritative = tmp_path / "authoritative.nii.gz"
    ordinary_seed = tmp_path / "ordinary_seed.nii.gz"
    derived = tmp_path / "derived.nii.gz"
    _write_displacement(
        authoritative,
        np.zeros(authoritative_shape + (3,), dtype=np.float64),
        affine,
    )
    _write_displacement(
        ordinary_seed,
        np.ones(target_shape + (3,), dtype=np.float64),
        affine,
    )

    summary = write_numerical_inverse_candidate(
        authoritative_transform=authoritative,
        initial_inverse_transform=ordinary_seed,
        output_transform=derived,
        max_iterations=2,
        tolerance_mm=1e-10,
        chunk_depth=2,
    )

    output = np.asarray(nib.load(str(derived)).dataobj)[:, :, :, 0, :]
    assert summary["identity_outside_authoritative_domain_count"] > 0
    np.testing.assert_array_equal(output[6, 6, 6], np.zeros(3))


def test_numerical_inverse_uses_authoritative_fixed_point_fallback(tmp_path: Path) -> None:
    shape = (8, 8, 8)
    affine = np.eye(4)
    displacement = np.zeros(shape + (3,), dtype=np.float64)
    x = np.arange(shape[0], dtype=np.float64)
    displacement[..., 0] = 0.4 * np.sin(np.pi * x[:, np.newaxis, np.newaxis] / (shape[0] - 1))

    authoritative = tmp_path / "authoritative.nii.gz"
    ordinary_seed = tmp_path / "ordinary_seed.nii.gz"
    derived = tmp_path / "derived.nii.gz"
    _write_displacement(authoritative, displacement, affine)
    _write_displacement(ordinary_seed, np.zeros(shape + (3,), dtype=np.float64), affine)

    summary = write_numerical_inverse_candidate(
        authoritative_transform=authoritative,
        initial_inverse_transform=ordinary_seed,
        output_transform=derived,
        max_iterations=1,
        tolerance_mm=1e-7,
        chunk_depth=2,
    )

    assert summary["fixed_point_converged_point_count"] > 0
    assert summary["nonconverged_point_count"] == 0
    points = np.indices(shape, dtype=np.float64).reshape(3, -1).T
    recovered_source = apply_grid_transform_to_points_ras(derived, points)
    round_trip = apply_grid_transform_to_points_ras(authoritative, recovered_source)
    np.testing.assert_allclose(round_trip, points, atol=1e-6)
