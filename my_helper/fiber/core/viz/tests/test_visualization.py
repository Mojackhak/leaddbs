from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
import pandas as pd
import pytest

from my_helper.fiber.core.viz.artifacts import restore_voxel_vector_to_nifti
from my_helper.fiber.core.viz.layout import build_figure_layout
from my_helper.fiber.core.viz.model_fit import plot_in_sample_loocv_fit
from my_helper.fiber.core.viz.postprocess import SCHEMA_VERSION, run_postprocess
from my_helper.fiber.core.viz.spatial import plot_sweet_sour_slices


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
    assert "permutation p  0.040" in text
    assert "Q²  0.120" in text
    layout = getattr(figure, "_mh_viz_layout")
    assert layout.boxsize_mm == (45.0, 38.0)
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
    sweet, sour, background = _nifti_inputs(tmp_path)
    subjects_path = tmp_path / "subjects.csv"
    _subjects().to_csv(subjects_path, index=False)
    config_path = tmp_path / "postprocess.json"
    config = {
        "schema_version": SCHEMA_VERSION,
        "output_root": "outputs",
        "defaults": {"formats": ["png"], "dpi": 100},
        "endpoints": [
            {
                "endpoint_id": "endpoint_test",
                "summary": _summary(),
                "spatial_2d": {
                    "model_unit": "voxel",
                    "sweet_image": str(sweet),
                    "sour_image": str(sour),
                    "background_image": str(background),
                    "resolution_mm": 1.0,
                    "percent_list": [50.0],
                    "boxsize": [24.0, 22.0],
                },
                "statistics": {"subject_table": str(subjects_path)},
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
    subjects_path = tmp_path / "subjects.csv"
    _subjects().to_csv(subjects_path, index=False)
    config_path = tmp_path / "postprocess.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "output_root": "outputs",
                "defaults": {"formats": ["png"], "dpi": 100},
                "endpoints": [
                    {
                        "endpoint_id": "endpoint_other",
                        "summary": _summary(),
                        "statistics": {"subject_table": str(subjects_path)},
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


def test_legacy_matlab_visualization_functions_are_merged() -> None:
    viz_root = Path(__file__).resolve().parents[1]
    assert not (viz_root.parent / "visualization").exists()
    for name in (
        "mh_fiber_make_scene.m",
        "mh_fiber_open_scene.m",
        "mh_fiber_style_electrodes.m",
        "mh_viz_make_sweet_sour_scene.m",
        "mh_viz_show_scored_fibers.m",
    ):
        assert (viz_root / name).is_file()
