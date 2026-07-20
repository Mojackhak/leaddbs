from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
import pandas as pd
import pytest
from scipy.io import loadmat

from my_helper.fiber.core.viz.artifacts import restore_voxel_vector_to_nifti
from my_helper.fiber.core.viz.layout import build_figure_layout
from my_helper.fiber.core.viz.model_fit import plot_in_sample_loocv_fit
from my_helper.fiber.core.viz.postprocess import SCHEMA_VERSION, run_postprocess
from my_helper.fiber.core.viz.published_artifacts import PublishedArtifactError
from my_helper.fiber.core.viz.scene_example_inputs import prepare_scene_example_input
from my_helper.fiber.core.viz.spatial import plot_sweet_sour_slices
from my_helper.fiber.core.viz.voxel_sections import plot_signed_voxel_sections
from my_helper.fiber.core.viz.voxel_section_postprocess import (
    run_single_scale_voxel_section_postprocess,
)


def _summary() -> dict[str, object]:
    return {
        "endpoint_id": "endpoint_test",
        "scale_id": "scale_test",
        "model_family": "addon_voxel",
        "final_model_id": "final_test",
        "selected_tau": 200.0,
        "selected_coverage": 5,
        "final_branch": "no_delta_reference",
        "candidate_axis_id": "axis_test",
        "in_sample_spearman_rho": 0.82,
        "in_sample_spearman_nominal_p": 0.001,
        "in_sample_permutation_p_plus_one_two_sided": 0.04,
        "in_sample_permutation_q_bh_model_family": 0.2,
        "in_sample_permutation_q_bh_all_endpoints": 0.4,
        "in_sample_pearson_r": 0.8,
        "in_sample_pearson_nominal_p": 0.002,
        "in_sample_permutations_requested": 10000,
        "in_sample_permutations_finite": 10000,
        "in_sample_n_subjects_finite": 12,
        "in_sample_rmse": 1.2,
        "in_sample_mae": 0.9,
        "in_sample_r2": 0.63,
        "in_sample_relative_r2": 0.41,
        "loocv_spearman_rho": 0.45,
        "loocv_spearman_nominal_p": 0.08,
        "loocv_permutation_p_plus_one_two_sided": 0.3,
        "loocv_permutation_q_bh_model_family": 0.6,
        "loocv_permutation_q_bh_all_endpoints": 0.8,
        "loocv_pearson_r": 0.42,
        "loocv_pearson_nominal_p": 0.1,
        "loocv_permutations_requested": 10000,
        "loocv_permutations_finite": 10000,
        "loocv_n_subjects_finite": 12,
        "loocv_rmse_model": 1.8,
        "loocv_mae_model": 1.4,
        "loocv_r2": 0.16,
        "loocv_q2": 0.12,
    }


def _subjects() -> pd.DataFrame:
    outcome = np.asarray([1.0, 2.2, 2.7, 4.1, 5.2, 5.8, 7.1, 7.9, 8.8, 10.0, 10.7, 12.2])
    return pd.DataFrame(
        {
            "subject_id": [f"sub-{index:02d}" for index in range(outcome.size)],
            "outcome": outcome,
            "in_sample_prediction": outcome * 0.93 + 0.35,
            "loocv_prediction": outcome * 0.64 + 1.2,
        }
    )


def _nifti_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    shape = (21, 21, 21)
    affine = np.asarray(
        [
            [1.0, 0.0, 0.0, -10.0],
            [0.0, 1.0, 0.0, -10.0],
            [0.0, 0.0, 1.0, -10.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    coordinates = np.indices(shape, dtype=float)
    radius = np.sqrt(sum((coordinates[axis] - 10.0) ** 2 for axis in range(3)))
    background = np.clip(1.0 - radius / 18.0, 0.0, 1.0)
    sweet = np.zeros(shape, dtype=np.float32)
    sour = np.zeros(shape, dtype=np.float32)
    sweet[11:16, 8:13, 8:13] = 1.0
    sour[5:10, 8:13, 8:13] = 1.0
    paths = []
    for name, data in (("sweet", sweet), ("sour", sour), ("background", background)):
        path = tmp_path / f"{name}.nii.gz"
        nib.save(nib.Nifti1Image(data.astype(np.float32), affine), path)
        paths.append(path)
    return tuple(paths)


def _signed_voxel_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    heat_shape = (21, 21, 21)
    heat_affine = np.diag([0.5, 0.5, 0.5, 1.0])
    heat_affine[:3, 3] = -5.0
    heat = np.full(heat_shape, np.nan, dtype=np.float32)
    grid = np.indices(heat_shape, dtype=float)
    support = (
        ((grid[0] - 10.0) ** 2) / 25.0
        + ((grid[1] - 10.0) ** 2) / 16.0
        + ((grid[2] - 10.0) ** 2) / 9.0
    ) <= 1.0
    heat[support] = ((grid[0][support] - 10.0) / 5.0).astype(np.float32)
    heat_path = tmp_path / "benefit_map.nii.gz"
    nib.save(nib.Nifti1Image(heat, heat_affine), heat_path)

    anatomy_shape = (101, 101, 101)
    anatomy_affine = np.diag([0.1, 0.1, 0.1, 1.0])
    anatomy_affine[:3, 3] = -5.0
    anatomy_grid = np.indices(anatomy_shape, dtype=float)
    anatomy = np.clip(
        220.0
        - np.sqrt(
            sum((anatomy_grid[axis] - 50.0) ** 2 for axis in range(3))
        )
        * 4.0,
        0.0,
        255.0,
    ).astype(np.uint8)
    anatomy_path = tmp_path / "anatomy.nii.gz"
    nib.save(nib.Nifti1Image(anatomy, anatomy_affine), anatomy_path)

    center = np.asarray([65.0, 50.0, 50.0])[:, None, None, None]
    distance = np.sqrt(np.sum((anatomy_grid - center) ** 2, axis=0))
    mask = (distance <= 18.0).astype(np.uint8)
    mask_path = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(mask, anatomy_affine), mask_path)
    return heat_path, anatomy_path, mask_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_publication(
    root: Path,
    artifacts: dict[str, tuple[Path, str]],
    *,
    manifest: dict[str, object] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"final_status": "completed", "model_set_id": root.name, **(manifest or {})}
    (root / "model_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = []
    for relative_path, (path, kind) in artifacts.items():
        target = root / relative_path
        assert target.resolve() == path.resolve()
        rows.append(
            {
                "relative_path": relative_path,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "status": "completed",
                "artifact_kind": kind,
            }
        )
    pd.DataFrame(rows).to_csv(root / "artifact_index.csv", index=False)
    return root


def _scene_example_publications(tmp_path: Path) -> tuple[Path, Path]:

    shape = (5, 4, 3)
    affine = np.eye(4)
    affine[0, 3] = -2.0
    brainmask = tmp_path / "brainmask.nii.gz"
    nib.save(nib.Nifti1Image(np.ones(shape, dtype=np.float32), affine), brainmask)

    connectome = tmp_path / "connectome.mat"
    lengths = np.asarray([2, 2, 2, 2], dtype=np.float64)
    coordinates = np.asarray(
        [
            [-2.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0],
            [-1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [2.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )
    point_ids = np.repeat(np.arange(1, 5, dtype=np.float32), 2)
    with h5py.File(connectome, "w") as handle:
        handle.create_dataset("idx", data=lengths.reshape(1, -1))
        handle.create_dataset(
            "fibers", data=np.vstack((coordinates.T, point_ids.reshape(1, -1)))
        )

    study_path = tmp_path / "study_base.json"
    study = {
        "schema_version": "study_base_v1",
        "study": {
            "spot_model_sources": {
                "canonical_space": "MNI152NLin2009bAsym",
                "hemisphere_mapping": {"canonical_hemisphere": "R"},
                "brainmask": {"path": str(brainmask)},
                "connectomes": [
                    {
                        "connectome_id": "synthetic_connectome",
                        "streamlines": {
                            "path": str(connectome),
                            "sha256": _sha256(connectome),
                        },
                    }
                ],
            }
        },
    }
    study_path.write_text(json.dumps(study), encoding="utf-8")
    common_manifest = {
        "study_base_path": str(study_path),
        "study_base_sha256": _sha256(study_path),
    }

    direct_root = tmp_path / "direct_voxel" / "dual_frequency_four_model_v1"
    direct_resolver = direct_root / "pdq39_score" / "reference" / "resolver"
    direct_resolver.mkdir(parents=True)
    benefit_map = direct_resolver / "benefit_map.nii.gz"
    benefit_data = np.full(shape, np.nan, dtype=np.float32)
    benefit_data[2, 0, 0] = 0.7
    benefit_data[3, 1, 0] = -0.5
    nib.save(nib.Nifti1Image(benefit_data, affine), benefit_map)
    direct_final_path = direct_root / "pdq39_score" / "reference" / "final_model.json"
    direct_final_path.parent.mkdir(parents=True, exist_ok=True)
    direct_final = {
        "schema_version": "direct_voxel_final_model_v1",
        "scale_id": "pdq39_score",
        "model_family": "reference",
        "final_role": "primary",
        "realized_final_branch": "reference",
        "selected_tau_v_per_m": 200.0,
        "selected_coverage_subjects_min": 5,
        "source_record_relative_path": (
            "pdq39_score/reference/resolver/selected_source.json"
        ),
    }
    direct_final_path.write_text(json.dumps(direct_final), encoding="utf-8")
    _write_publication(
        direct_root,
        {
            "pdq39_score/reference/final_model.json": (
                direct_final_path,
                "final_model",
            ),
            "pdq39_score/reference/resolver/benefit_map.nii.gz": (
                benefit_map,
                "benefit_map",
            ),
        },
        manifest=common_manifest,
    )

    fiber_root = tmp_path / "normative_fiber" / "dual_frequency_four_model_v1"
    fiber_resolver = (
        fiber_root
        / "pdq39_score"
        / "reference"
        / "connectomes"
        / "synthetic_connectome"
        / "resolver"
    )
    fiber_resolver.mkdir(parents=True)
    valid_ids_path = fiber_resolver / "valid_fiber_ids.npy"
    fiber_weights_path = fiber_resolver / "full_weights.npy"
    sweet_path = fiber_resolver / "selected_sweet_fiber_ids.npy"
    sour_path = fiber_resolver / "selected_sour_fiber_ids.npy"
    np.save(valid_ids_path, np.asarray([1, 2, 3, 4], dtype=np.int64))
    np.save(fiber_weights_path, np.asarray([0.8, -0.6, 0.4, -0.2], dtype=np.float32))
    np.save(sweet_path, np.asarray([1, 3], dtype=np.int64))
    np.save(sour_path, np.asarray([2, 4], dtype=np.int64))
    fiber_final_path = fiber_root / "pdq39_score" / "reference" / "final_model.json"
    fiber_final_path.parent.mkdir(parents=True, exist_ok=True)
    resolver_relative = (
        "pdq39_score/reference/connectomes/synthetic_connectome/resolver"
    )
    fiber_final = {
        "schema_version": "normative_fiber_final_model_v1",
        "scale_id": "pdq39_score",
        "model_family": "reference",
        "formal_connectome_id": "synthetic_connectome",
        "final_branch": "reference",
        "final_role": "primary",
        "selected_tau_v_per_m": 400.0,
        "selected_coverage_subjects_min": 5,
        "resolver_relative_path": f"{resolver_relative}/source_selection.json",
    }
    fiber_final_path.write_text(json.dumps(fiber_final), encoding="utf-8")
    _write_publication(
        fiber_root,
        {
            "pdq39_score/reference/final_model.json": (
                fiber_final_path,
                "final_model",
            ),
            f"{resolver_relative}/valid_fiber_ids.npy": (
                valid_ids_path,
                "valid_fiber_ids",
            ),
            f"{resolver_relative}/full_weights.npy": (
                fiber_weights_path,
                "full_weights",
            ),
            f"{resolver_relative}/selected_sweet_fiber_ids.npy": (
                sweet_path,
                "selected_sweet_fiber_ids",
            ),
            f"{resolver_relative}/selected_sour_fiber_ids.npy": (
                sour_path,
                "selected_sour_fiber_ids",
            ),
        },
        manifest=common_manifest,
    )
    return direct_root, fiber_root


def _voxel_section_publication(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    heat_path, anatomy_path, mask_path = _signed_voxel_inputs(tmp_path / "resources")
    root = tmp_path / "direct_voxel" / "dual_frequency_four_model_v1"
    artifacts: dict[str, tuple[Path, str]] = {}
    for role in ("reference", "addon"):
        resolver_relative = (
            f"pdq39_score/{role}/resolver"
            if role == "reference"
            else "pdq39_score/addon/branches/no_delta_reference/resolver"
        )
        raw_relative = f"{resolver_relative}/benefit_map.nii.gz"
        raw_path = root / raw_relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(nib.load(heat_path), raw_path)
        artifacts[raw_relative] = (raw_path, "benefit_map")

        final_model_path = root / "pdq39_score" / role / "final_model.json"
        final_model_path.parent.mkdir(parents=True, exist_ok=True)
        final_model = {
            "schema_version": "direct_voxel_final_model_v1",
            "final_status": "final_model_realized",
            "final_model_id": f"final_{role}",
            "scale_id": "pdq39_score",
            "model_family": role,
            "realized_final_branch": (
                "reference" if role == "reference" else "no_delta_reference"
            ),
            "selected_tau_v_per_m": 200.0,
            "selected_coverage_subjects_min": 5,
            "artifact_relative_paths": [raw_relative],
        }
        final_model_path.write_text(json.dumps(final_model), encoding="utf-8")
        artifacts[f"pdq39_score/{role}/final_model.json"] = (
            final_model_path,
            "final_model",
        )

        report_root = root / "pdq39_score" / role / "report"
        display_root = report_root / "display"
        display_root.mkdir(parents=True, exist_ok=True)
        summary_path = report_root / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "direct_voxel_report_summary_v1",
                    "display_only": True,
                    "scale_id": "pdq39_score",
                    "model_family": role,
                    "final_model_id": f"final_{role}",
                    "selected_tau_v_per_m": 200.0,
                    "selected_coverage_subjects_min": 5,
                }
            ),
            encoding="utf-8",
        )
        artifacts[f"pdq39_score/{role}/report/summary.json"] = (
            summary_path,
            "report_summary",
        )
        for name in (
            "benefit_map_smooth_fwhm1mm.nii.gz",
            "benefit_map_smooth_fwhm2mm.nii.gz",
        ):
            target = display_root / name
            nib.save(nib.load(heat_path), target)
            artifacts[f"pdq39_score/{role}/report/display/{name}"] = (
                target,
                name.removesuffix(".nii.gz"),
            )
    _write_publication(root, artifacts)
    return root, anatomy_path, mask_path, mask_path


def test_layout_preserves_inner_boxsize() -> None:
    layout = build_figure_layout(
        2,
        3,
        boxsize=(48.0, 42.0),
        panel_gap=(5.0, 4.0),
        top_strip_mm=4.0,
        right_strip_mm=3.0,
    )
    figure_width, figure_height = layout.figure_size_mm
    for position in layout.panel_positions:
        assert position[2] * figure_width == pytest.approx(48.0)
        assert position[3] * figure_height == pytest.approx(42.0)


def test_fit_plot_exports_and_uses_stored_metrics(tmp_path: Path) -> None:
    output = tmp_path / "fit.png"
    figure = plot_in_sample_loocv_fit(
        _subjects(),
        _summary(),
        boxsize=(45.0, 38.0),
        output_paths=[output],
    )
    assert output.is_file()
    assert output.stat().st_size > 1000
    text = "\n".join(item.get_text() for axis in figure.axes for item in axis.texts)
    assert "ρ = 0.820" in text
    assert "p = 0.040 (*)" in text
    assert "nominal" not in text
    assert "family BH" not in text
    assert "Pearson" not in text
    assert "tau" not in text
    assert "Coverage" not in text
    layout = getattr(figure, "_mh_viz_layout")
    assert layout.boxsize_mm == (45.0, 38.0)
    panel_axes = [axis for axis in figure.axes if axis.has_data()]
    assert len(panel_axes) == 2
    assert all(axis.spines["top"].get_visible() for axis in panel_axes)
    assert all(axis.spines["right"].get_visible() for axis in panel_axes)
    assert all(len(axis.lines) == 1 for axis in panel_axes)
    assert panel_axes[0].get_xlim() == pytest.approx(panel_axes[1].get_xlim())
    assert panel_axes[0].get_ylim() == pytest.approx(panel_axes[1].get_ylim())
    assert any(label.get_visible() for label in panel_axes[0].get_yticklabels())
    assert not any(label.get_visible() for label in panel_axes[1].get_yticklabels())

    displays = getattr(figure, "_mh_viz_fit_displays")
    x_values = np.concatenate(
        [
            part
            for display in displays
            for part in (display.x, display.x_grid)
            if part.size
        ]
    )
    x_span = float(np.max(x_values) - np.min(x_values))
    expected_x = (
        float(np.min(x_values) - 0.05 * x_span),
        float(np.max(x_values) + 0.05 * x_span),
    )
    y_values = np.concatenate(
        [
            part
            for display in displays
            for part in (display.y, display.fitted, display.lower, display.upper)
            if part.size
        ]
    )
    y_span = float(np.max(y_values) - np.min(y_values))
    expected_y = (
        float(np.min(y_values) - 0.05 * y_span),
        float(np.max(y_values) + 0.05 * y_span),
    )
    assert panel_axes[0].get_xlim() == pytest.approx(expected_x)
    for axis, display in zip(panel_axes, displays, strict=True):
        assert axis.get_ylim() == pytest.approx(expected_y)
        if display.lower.size:
            assert float(np.min(display.lower)) > expected_y[0]
            assert float(np.max(display.upper)) < expected_y[1]
        annotation = next(item for item in axis.texts if "ρ =" in item.get_text())
        assert annotation.get_position() == pytest.approx((0.05, 0.95))
        assert annotation.get_horizontalalignment() == "left"
        assert annotation.get_verticalalignment() == "top"
    plt.close(figure)


@pytest.mark.parametrize(
    ("permutation_p", "expected"),
    [
        (0.2, "p = 0.200 (n.s.)"),
        (0.04, "p = 0.040 (*)"),
        (0.008, "p = 0.008 (**)"),
        (0.0005, "p < 0.001 (***)"),
    ],
)
def test_fit_plot_formats_permutation_significance(
    permutation_p: float,
    expected: str,
) -> None:
    summary = _summary()
    summary["in_sample_permutation_p_plus_one_two_sided"] = permutation_p
    figure = plot_in_sample_loocv_fit(_subjects(), summary)
    text = "\n".join(item.get_text() for axis in figure.axes for item in axis.texts)
    assert expected in text
    plt.close(figure)


def test_spatial_plot_uses_world_slices_and_boxsize(tmp_path: Path) -> None:
    sweet, sour, background = _nifti_inputs(tmp_path)
    output = tmp_path / "sections.png"
    figure = plot_sweet_sour_slices(
        sweet,
        sour,
        background_image=background,
        percent_list=(25.0, 50.0, 75.0),
        resolution_mm=1.0,
        boxsize=(30.0, 28.0),
        output_paths=[output],
    )
    assert output.is_file()
    metadata = getattr(figure, "_mh_viz_spatial_metadata")
    assert metadata["facets"] == ["Ax", "Cor", "Sag"]
    assert len(metadata["slice_coordinates_mm"]["Ax"]) == 3
    assert getattr(figure, "_mh_viz_layout").boxsize_mm == (30.0, 28.0)
    panels = [axis for axis in figure.axes if axis.images]
    assert len(panels) == 9
    assert all(not axis.get_xticklabels() for axis in panels[:6])
    assert all(axis.get_xticklabels() for axis in panels[6:])
    assert all(axis.get_yticklabels() for axis in panels[::3])
    assert all(
        not axis.get_yticklabels()
        for index, axis in enumerate(panels)
        if index % 3
    )
    assert [axis.get_xlabel() for axis in panels[6:]] == ["", "MNI y (mm)", ""]
    plt.close(figure)


def test_spatial_plot_projects_one_signed_map_into_sweet_and_sour(tmp_path: Path) -> None:
    signed, _, background = _nifti_inputs(tmp_path)
    signed_data = np.asarray(nib.load(signed).dataobj, dtype=np.float32)
    signed_data[3, 4, 5] = -2.0
    nib.save(nib.Nifti1Image(signed_data, np.eye(4)), signed)

    figure = plot_sweet_sour_slices(
        signed,
        signed,
        background_image=background,
        sweet_threshold=0.5,
        sour_threshold=0.5,
        sweet_value_mode="positive",
        sour_value_mode="negative_magnitude",
        percent_list=(50.0,),
        boxsize=(20.0, 18.0),
    )

    metadata = getattr(figure, "_mh_viz_spatial_metadata")
    assert metadata["sweet_value_mode"] == "positive"
    assert metadata["sour_value_mode"] == "negative_magnitude"
    plt.close(figure)


def test_restore_voxel_vector_requires_explicit_index_semantics(tmp_path: Path) -> None:
    reference = nib.Nifti1Image(np.zeros((4, 5, 6), dtype=np.float32), np.eye(4))
    output = tmp_path / "restored.nii.gz"
    restore_voxel_vector_to_nifti(
        [2.5, -1.5],
        [[1, 2, 3], [3, 4, 5]],
        reference,
        output,
        index_base=0,
        metadata={"model_family": "reference_voxel"},
    )
    data = nib.load(output).get_fdata()
    assert data[1, 2, 3] == pytest.approx(2.5)
    assert data[3, 4, 5] == pytest.approx(-1.5)
    assert np.isnan(data[0, 0, 0])
    sidecar = json.loads((tmp_path / "restored.json").read_text(encoding="utf-8"))
    assert sidecar["artifact_role"] == "voxel_model_visualization"


def test_manifest_postprocess_and_resume(tmp_path: Path) -> None:
    publication_root = tmp_path / "direct_voxel" / "model_set"
    scientific_root = publication_root / "scale_test" / "reference" / "report"
    scientific_root.mkdir(parents=True)
    sweet, sour, background = _nifti_inputs(scientific_root)
    summary_path = scientific_root / "summary.json"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    subjects_path = scientific_root / "subjects.csv"
    _subjects().to_csv(subjects_path, index=False)
    _write_publication(
        publication_root,
        {
            "scale_test/reference/report/sweet.nii.gz": (sweet, "sweet_map"),
            "scale_test/reference/report/sour.nii.gz": (sour, "sour_map"),
            "scale_test/reference/report/summary.json": (summary_path, "summary"),
            "scale_test/reference/report/subjects.csv": (
                subjects_path,
                "predictions",
            ),
        },
    )
    config_path = tmp_path / "postprocess.json"
    config = {
        "schema_version": SCHEMA_VERSION,
        "output_root": "outputs",
        "publications": {
            "main": {"root": str(publication_root), "manifest": "model_manifest.json"}
        },
        "defaults": {"formats": ["png"], "dpi": 100},
        "endpoints": [
            {
                "endpoint_id": "endpoint_test",
                "summary_json": {
                    "publication": "main",
                    "relative_path": "scale_test/reference/report/summary.json",
                },
                "spatial_2d": {
                    "model_unit": "voxel",
                    "sweet_image": {
                        "publication": "main",
                        "relative_path": "scale_test/reference/report/sweet.nii.gz",
                    },
                    "sour_image": {
                        "publication": "main",
                        "relative_path": "scale_test/reference/report/sour.nii.gz",
                    },
                    "background_image": str(background),
                    "resolution_mm": 1.0,
                    "percent_list": [50.0],
                    "boxsize": [24.0, 22.0],
                },
                "statistics": {
                    "subject_table": {
                        "publication": "main",
                        "relative_path": "scale_test/reference/report/subjects.csv",
                    }
                },
            }
        ],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    first = run_postprocess(config_path)
    assert first["status"] == "complete"
    assert first["completed_count"] == 1
    second = run_postprocess(config_path)
    assert second["status"] == "complete"
    assert second["reused_count"] == 1


def test_manifest_rejects_mismatched_endpoint_summary(tmp_path: Path) -> None:
    publication_root = tmp_path / "direct_voxel" / "model_set"
    scientific_root = publication_root / "scale_test" / "reference" / "report"
    scientific_root.mkdir(parents=True)
    summary_path = scientific_root / "summary.json"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    subjects_path = scientific_root / "subjects.csv"
    _subjects().to_csv(subjects_path, index=False)
    _write_publication(
        publication_root,
        {
            "scale_test/reference/report/summary.json": (summary_path, "summary"),
            "scale_test/reference/report/subjects.csv": (
                subjects_path,
                "predictions",
            ),
        },
    )
    config_path = tmp_path / "postprocess.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "output_root": "outputs",
                "publications": {"main": {"root": str(publication_root)}},
                "defaults": {"formats": ["png"], "dpi": 100},
                "endpoints": [
                    {
                        "endpoint_id": "endpoint_other",
                        "summary_json": {
                            "publication": "main",
                            "relative_path": "scale_test/reference/report/summary.json",
                        },
                        "statistics": {
                            "subject_table": {
                                "publication": "main",
                                "relative_path": "scale_test/reference/report/subjects.csv",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run_postprocess(config_path)
    assert result["status"] == "completed_with_failures"
    assert result["failed_count"] == 1
    assert "does not match" in result["endpoints"][0]["error_message"]


@pytest.mark.parametrize(
    "forbidden_part",
    (".runs", "tasks", "work", "runtime_work"),
)
def test_postprocess_rejects_run_store_as_publication(
    tmp_path: Path,
    forbidden_part: str,
) -> None:
    publication_root = tmp_path / forbidden_part / "internal_run"
    scientific_root = publication_root / "report"
    scientific_root.mkdir(parents=True)
    summary_path = scientific_root / "summary.json"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    _write_publication(
        publication_root,
        {"report/summary.json": (summary_path, "summary")},
    )
    config_path = tmp_path / "postprocess.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "output_root": "outputs",
                "publications": {"main": {"root": str(publication_root)}},
                "endpoints": [
                    {
                        "endpoint_id": "endpoint_test",
                        "summary_json": {
                            "publication": "main",
                            "relative_path": "report/summary.json",
                        },
                        "statistics": {
                            "subject_table": {
                                "publication": "main",
                                "relative_path": "report/summary.json",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PublishedArtifactError, match="cannot be inside a run store"):
        run_postprocess(config_path)


def test_scene_example_prepares_and_reuses_voxel_input(tmp_path: Path) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    first = prepare_scene_example_input(
        direct_root,
        tmp_path / "outputs",
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    second = prepare_scene_example_input(
        direct_root,
        tmp_path / "outputs",
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    assert first["input_path"] == second["input_path"]
    assert first["selected_tau"] == 200.0
    data = nib.load(first["input_path"]).get_fdata()
    finite = data[np.isfinite(data)]
    np.testing.assert_allclose(np.sort(finite), [-0.5, 0.7])


def test_scene_example_prepares_selected_scored_fibers(tmp_path: Path) -> None:
    _, fiber_root = _scene_example_publications(tmp_path)
    result = prepare_scene_example_input(
        fiber_root,
        tmp_path / "outputs",
        scale_id="pdq39_score",
        model_family="reference_fiber",
    )
    assert result["selected_tau"] == 400.0
    assert result["details"]["sweet_fiber_count"] == 2
    assert result["details"]["sour_fiber_count"] == 2
    payload = loadmat(result["input_path"])
    np.testing.assert_array_equal(payload["fiber_ids"].reshape(-1), [1, 2, 3, 4])
    np.testing.assert_allclose(payload["scores"].reshape(-1), [0.8, -0.6, 0.4, -0.2])
    np.testing.assert_array_equal(payload["idx"].reshape(-1), [2, 2, 2, 2])
    assert payload["fibers"].shape == (8, 3)


def test_signed_voxel_sections_match_the_accepted_layer_and_layout_contract(
    tmp_path: Path,
) -> None:
    heat_path, anatomy_path, mask_path = _signed_voxel_inputs(tmp_path)
    output = tmp_path / "sections.png"
    figure = plot_signed_voxel_sections(
        heat_path,
        background_image=anatomy_path,
        mask_image=mask_path,
        style_config={
            "dpi": 72,
            "resolution_mm": 0.5,
            "boxsize": (12.0, 10.0),
            "panel_gap": (1.0, 1.0),
        },
        output_paths=[output],
    )

    assert output.is_file()
    assert output.stat().st_size > 1000
    panel_axes = getattr(figure, "_mh_viz_panel_axes")
    assert len(panel_axes) == 9
    assert all(len(axis.images) == 2 for axis in panel_axes)
    assert all(axis.images[0].get_zorder() == 0 for axis in panel_axes)
    assert all(axis.images[1].get_zorder() == 2 for axis in panel_axes)
    contours = [
        collection
        for axis in panel_axes
        for collection in axis.collections
        if collection.get_zorder() == 4
    ]
    assert contours
    assert all(collection.get_alpha() == 1.0 for collection in contours)
    assert all(
        collection.get_linewidths()[0] == pytest.approx(0.5)
        for collection in contours
    )
    assert all(
        np.asarray(collection.get_edgecolor())[0, :3] == pytest.approx((0.0, 0.0, 0.0))
        for collection in contours
    )
    metadata = getattr(figure, "_mh_viz_voxel_section_metadata")
    assert metadata["background_full_float_loaded"] is False
    assert metadata["background_crop_bytes"] < np.prod(
        metadata["background_full_shape"]
    ) * np.dtype(np.float32).itemsize
    assert metadata["heat_limits"][0] == pytest.approx(-metadata["heat_limits"][1])
    assert metadata["mask_layer"] == "top"
    assert metadata["mask_color"] == "#000000"
    assert metadata["mask_linewidth_pt"] == 0.5
    assert metadata["colorbar_label"] == "Benefit-oriented partial Spearman ρ"
    plt.close(figure)


def test_single_scale_voxel_section_postprocess_writes_and_reuses_six_figures(
    tmp_path: Path,
) -> None:
    publication, anatomy, reference_mask, addon_mask = _voxel_section_publication(
        tmp_path
    )
    output_root = tmp_path / "postprocess"
    arguments = {
        "scale_id": "pdq39_score",
        "output_root": output_root,
        "direct_voxel_publication_root": publication,
        "background_path": anatomy,
        "reference_mask_path": reference_mask,
        "addon_mask_path": addon_mask,
        "style_overrides": {
            "dpi": 72,
            "resolution_mm": 0.5,
            "boxsize": (12.0, 10.0),
            "panel_gap": (1.0, 1.0),
        },
    }
    first = run_single_scale_voxel_section_postprocess(**arguments)
    assert first["status"] == "complete"
    assert first["completed_count"] == 6
    assert first["failed_count"] == 0
    assert first["reused_count"] == 0

    for role in ("reference", "addon"):
        leaf = output_root / "scales" / "pdq39_score" / role / "voxel"
        for stem in (
            "benefit_map_sections",
            "benefit_map_smooth_fwhm1mm_sections",
            "benefit_map_smooth_fwhm2mm_sections",
        ):
            for extension in ("png", "pdf", "json"):
                assert (leaf / f"{stem}.{extension}").is_file()
            result = json.loads((leaf / f"{stem}.json").read_text(encoding="utf-8"))
            assert result["status"] == "complete"
            assert result["model_role"] == role
            assert result["render_metadata"]["background_full_float_loaded"] is False
            assert result["render_metadata"]["mask_layer"] == "top"
            if stem == "benefit_map_sections":
                relative = result["source_artifacts"]["heatmap"]["relative_path"]
                assert relative.endswith("/resolver/benefit_map.nii.gz")
                assert "bilateral" not in relative

    second = run_single_scale_voxel_section_postprocess(**arguments)
    assert second["status"] == "complete"
    assert second["failed_count"] == 0
    assert second["reused_count"] == 6


def test_legacy_matlab_visualization_functions_are_merged() -> None:
    viz_root = Path(__file__).resolve().parents[1]
    assert not (viz_root.parent / "visualization").exists()
    for name in (
        "mh_fiber_make_scene.m",
        "mh_fiber_open_scene.m",
        "mh_fiber_style_electrodes.m",
        "mh_viz_make_sweet_sour_scene.m",
        "mh_viz_prepare_scene_example_input.m",
        "mh_viz_show_scored_fibers.m",
    ):
        assert (viz_root / name).is_file()
    for name in (
        "open_pdq39_reference_voxel_scene.m",
        "open_pdq39_reference_fiber_scene.m",
    ):
        assert (viz_root / "examples" / name).is_file()
    voxel_example_path = (
        viz_root / "examples" / "open_pdq39_reference_voxel_scene.m"
    )
    voxel_example = voxel_example_path.read_text(encoding="utf-8")
    assert "spec.VoxelSampleDepthMm = 0.5;" in voxel_example
