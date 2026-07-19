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


def test_postprocess_rejects_run_store_as_publication(tmp_path: Path) -> None:
    publication_root = tmp_path / ".runs" / "internal_run"
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
