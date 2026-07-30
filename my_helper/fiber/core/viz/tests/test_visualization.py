from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.text import Text
import nibabel as nib
import numpy as np
import pandas as pd
import pytest
from scipy.io import loadmat

from my_helper.fiber.core.viz import (
    formal_postprocess,
    postprocess,
    scene_example_inputs,
    voxel_section_postprocess,
)
from my_helper.fiber.core.viz.artifacts import restore_voxel_vector_to_nifti
from my_helper.fiber.core.viz.layout import build_figure_layout
from my_helper.fiber.core.viz.model_fit import plot_in_sample_loocv_fit
from my_helper.fiber.core.viz.postprocess import SCHEMA_VERSION, run_postprocess
from my_helper.fiber.core.viz.plugin.default import get_voxel_section_cfg
from my_helper.fiber.core.viz.published_artifacts import (
    PublicationCatalog,
    PublishedArtifactError,
)
from my_helper.fiber.core.viz.scene_example_inputs import (
    SceneExampleInputError,
    prepare_scene_example_input,
)
from my_helper.fiber.core.viz.spatial import plot_sweet_sour_slices
from my_helper.fiber.core.viz.voxel_sections import plot_signed_voxel_sections
from my_helper.fiber.core.viz.voxel_section_postprocess import (
    _resource_record,
    render_voxel_section_components,
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
        "in_sample_n_subjects_total": 12,
        "in_sample_n_subjects_finite": 12,
        "in_sample_predictions_all_finite": True,
        "in_sample_rmse": 1.2,
        "in_sample_mae": 0.9,
        "in_sample_rmse_baseline": 2.0,
        "in_sample_mae_baseline": 1.6,
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
        "loocv_n_subjects_total": 12,
        "loocv_n_subjects_finite": 12,
        "loocv_predictions_all_finite": True,
        "loocv_rmse_model": 1.8,
        "loocv_mae_model": 1.4,
        "loocv_rmse_baseline": 2.1,
        "loocv_mae_baseline": 1.7,
        "loocv_r2": 0.16,
        "loocv_q2": 0.12,
        "subject_mask_match": True,
        "spearman_optimism_gap": 0.37,
        "pearson_optimism_gap": 0.38,
        "r2_optimism_gap": 0.47,
        "relative_r2_q2_gap": 0.29,
        "rmse_optimism_gap": 0.6,
        "mae_optimism_gap": 0.5,
    }


def _subjects() -> pd.DataFrame:
    outcome = np.asarray([1.0, 2.2, 2.7, 4.1, 5.2, 5.8, 7.1, 7.9, 8.8, 10.0, 10.7, 12.2])
    return pd.DataFrame(
        {
            "subject_id": [f"sub-{index:02d}" for index in range(outcome.size)],
            "outcome": outcome,
            "in_sample_prediction": outcome * 0.93 + 0.35,
            "loocv_prediction": outcome * 0.64 + 1.2,
            "in_sample_baseline_prediction": np.full(outcome.size, outcome.mean()),
            "loocv_baseline_prediction": np.full(outcome.size, outcome.mean() + 0.1),
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
            "scale_definitions": [
                {"scale_id": "pdq39_score", "label": "PDQ39 score"}
            ],
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
    (direct_root / study_path.name).write_bytes(study_path.read_bytes())
    benefit_map = direct_resolver / "benefit_map.nii.gz"
    benefit_data = np.full(shape, np.nan, dtype=np.float32)
    benefit_data[2, 0, 0] = 0.7
    benefit_data[3, 1, 0] = -0.5
    nib.save(nib.Nifti1Image(benefit_data, affine), benefit_map)
    display_map = (
        direct_root
        / "pdq39_score/reference/report/display/"
        "benefit_map_smooth_fwhm1mm.nii.gz"
    )
    display_map.parent.mkdir(parents=True)
    display_data = np.full(shape, np.nan, dtype=np.float32)
    display_data[2, 0, 0] = 0.6
    display_data[3, 1, 0] = -0.4
    nib.save(nib.Nifti1Image(display_data, affine), display_map)
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
            (
                "pdq39_score/reference/report/display/"
                "benefit_map_smooth_fwhm1mm.nii.gz"
            ): (display_map, "benefit_map_smooth_fwhm1mm"),
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
    (fiber_root / study_path.name).write_bytes(study_path.read_bytes())
    valid_ids_path = fiber_resolver / "valid_fiber_ids.npy"
    candidate_ids_path = fiber_resolver / "candidate_fiber_ids.npy"
    fiber_weights_path = fiber_resolver / "full_weights.npy"
    sweet_path = fiber_resolver / "selected_sweet_fiber_ids.npy"
    sour_path = fiber_resolver / "selected_sour_fiber_ids.npy"
    np.save(valid_ids_path, np.asarray([1, 2, 3, 4], dtype=np.int64))
    np.save(candidate_ids_path, np.asarray([1, 2, 3, 4], dtype=np.int64))
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
            f"{resolver_relative}/candidate_fiber_ids.npy": (
                candidate_ids_path,
                "candidate_fiber_ids",
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
            relative = f"pdq39_score/{role}/report/display/{name}"
            artifacts[relative] = (
                target,
                name.removesuffix(".nii.gz"),
            )
            fwhm = 1.0 if "fwhm1mm" in name else 2.0
            metadata = {
                "schema_version": "dual_frequency_derived_artifact_metadata_v1",
                "artifact_kind": "benefit_map_smooth",
                "published_relative_path": relative,
                "payload_sha256": _sha256(target),
                "size_bytes": target.stat().st_size,
                "provenance": {
                    "source_record_id": f"source_{role}",
                    "input_relative_path": raw_relative,
                    "fwhm_mm": fwhm,
                    "algorithm": "masked_normalized_gaussian_original_roi_v2",
                    "support_policy": "original_finite_benefit_roi",
                    "input_finite_voxels": 27,
                    "output_finite_voxels": 27,
                },
            }
            Path(f"{target}.metadata.json").write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )
    study_base_path = root / "study_base.json"
    study_base_path.write_text(
        json.dumps(
            {
                "schema_version": "synthetic_study_base_v1",
                "study": {
                    "scale_definitions": [
                        {"scale_id": "pdq39_score", "label": "PDQ39 score"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    _write_publication(
        root,
        artifacts,
        manifest={
            "study_base_path": "/original-machine/publication/study_base.json",
            "study_base_sha256": _sha256(study_base_path),
        },
    )
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


def test_manifest_postprocess_and_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    output_root = tmp_path / "outputs"
    root_complete = output_root / "complete.json"
    endpoint_root = output_root / "endpoints" / "endpoint_test"
    endpoint_manifest = endpoint_root / "manifest.json"
    endpoint_complete = endpoint_root / "complete.json"
    assert root_complete.is_file()
    assert endpoint_complete.is_file()
    assert "request_hash" not in json.loads(
        endpoint_manifest.read_text(encoding="utf-8")
    )
    endpoint_mtime = endpoint_manifest.stat().st_mtime_ns

    root_complete.replace(tmp_path / "removed-root-complete.json")
    second = run_postprocess(config_path)
    assert second["status"] == "complete"
    assert second["reused_count"] == 1
    assert root_complete.is_file()
    assert endpoint_manifest.stat().st_mtime_ns == endpoint_mtime

    trashed: list[Path] = []

    def move_to_trash(path: Path) -> None:
        target = tmp_path / f"trashed-{len(trashed)}"
        path.replace(target)
        trashed.append(target)

    monkeypatch.setattr(postprocess, "_trash", move_to_trash)
    forced = run_postprocess(config_path, force=True)
    assert forced["status"] == "complete"
    assert trashed == [tmp_path / "trashed-0"]
    assert (trashed[0] / "complete.json").is_file()
    assert root_complete.is_file()
    assert endpoint_complete.is_file()

    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with monkeypatch.context() as context:
        context.setattr(
            postprocess.PublicationCatalog,
            "from_config",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("terminal postprocess reopened its publications")
            ),
        )
        restored = run_postprocess(config_path)
    assert restored["resume_status"] == "reused"
    assert restored["reused_count"] == 1

    endpoint_text = endpoint_manifest.read_text(encoding="utf-8")
    root_complete.replace(tmp_path / "removed-root-complete-again.json")
    endpoint_complete.replace(tmp_path / "removed-endpoint-complete.json")
    with monkeypatch.context() as context:
        context.setattr(
            postprocess,
            "_trash",
            lambda _path: (_ for _ in ()).throw(ValueError("trash unavailable")),
        )
        with pytest.raises(ValueError, match="trash unavailable"):
            run_postprocess(config_path)
    assert endpoint_manifest.read_text(encoding="utf-8") == endpoint_text


def test_manifest_postprocess_force_validates_before_trash(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    sentinel = output_root / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    config_path = tmp_path / "postprocess.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "output_root": "outputs",
                "publications": {"main": {"root": str(tmp_path / "missing")}},
                "endpoints": [{"endpoint_id": "endpoint_test"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublishedArtifactError):
        run_postprocess(config_path, force=True)
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_manifest_postprocess_validates_required_fields_before_resume(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    (output_root / "manifest.json").write_text(
        json.dumps({"status": "complete"}),
        encoding="utf-8",
    )
    (output_root / "complete.json").write_text("{}\n", encoding="utf-8")
    config_path = tmp_path / "postprocess.json"
    base = {
        "schema_version": SCHEMA_VERSION,
        "output_root": "outputs",
        "endpoints": [{"endpoint_id": "endpoint_test"}],
    }
    config_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="publications must be a nonempty object"):
        run_postprocess(config_path)

    duplicate = dict(base)
    duplicate["publications"] = {"main": {}}
    duplicate["endpoints"] = [
        {"endpoint_id": "endpoint_test"},
        {"endpoint_id": "endpoint_test"},
    ]
    config_path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="endpoint IDs must be unique"):
        run_postprocess(config_path)

    for endpoint_id in (".", "..", "../escape", "nested/escape"):
        unsafe = dict(base)
        unsafe["publications"] = {"main": {}}
        unsafe["endpoints"] = [{"endpoint_id": endpoint_id}]
        config_path.write_text(json.dumps(unsafe), encoding="utf-8")
        with pytest.raises(
            ValueError,
            match="endpoint_id must be one safe path component",
        ):
            run_postprocess(config_path)


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


def test_scene_example_prepares_and_reuses_voxel_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    output_root = tmp_path / "outputs"
    first = prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    target = output_root / "pdq39_score-reference_voxel"
    assert (target / "manifest.json").is_file()
    assert (target / "complete.json").is_file()
    monkeypatch.setattr(
        scene_example_inputs,
        "_catalog",
        lambda publication: (_ for _ in ()).throw(
            AssertionError("completed scene input reopened its publication")
        ),
    )
    second = prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    assert first["input_path"] == second["input_path"]
    assert first["scale_display_name"] == "PDQ39 score"
    assert first["selected_tau"] == 200.0
    assert first["details"]["display_smoothing_fwhm_mm"] == 1.0
    assert first["details"]["display_only"] is True
    data = nib.load(first["input_path"]).get_fdata()
    finite = data[np.isfinite(data)]
    np.testing.assert_allclose(np.sort(finite), [-0.4, 0.6])


def test_scene_example_force_replaces_completed_target_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    output_root = tmp_path / "outputs"
    prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    target = output_root / "pdq39_score-reference_voxel"
    trashed = tmp_path / "trashed-scene-input"

    monkeypatch.setattr(scene_example_inputs, "_trash", lambda path: path.rename(trashed))
    result = prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
        force=True,
    )

    assert result["status"] == "complete"
    assert (trashed / "complete.json").is_file()
    assert (target / "complete.json").is_file()


def test_scene_example_rebuilds_only_incomplete_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    output_root = tmp_path / "outputs"
    prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    target = output_root / "pdq39_score-reference_voxel"
    incomplete = tmp_path / "incomplete-scene-input"
    (target / "complete.json").unlink()
    monkeypatch.setattr(
        scene_example_inputs, "_trash", lambda path: path.rename(incomplete)
    )

    result = prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )

    assert result["status"] == "complete"
    assert not (incomplete / "complete.json").exists()
    assert (target / "complete.json").is_file()


def test_scene_example_force_validates_before_replacing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    output_root = tmp_path / "outputs"
    prepare_scene_example_input(
        direct_root,
        output_root,
        scale_id="pdq39_score",
        model_family="reference_voxel",
    )
    target = output_root / "pdq39_score-reference_voxel"
    (direct_root / "model_manifest.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        scene_example_inputs,
        "_trash",
        lambda path: (_ for _ in ()).throw(
            AssertionError("invalid source replaced the completed target")
        ),
    )

    with pytest.raises(SceneExampleInputError):
        prepare_scene_example_input(
            direct_root,
            output_root,
            scale_id="pdq39_score",
            model_family="reference_voxel",
            force=True,
        )
    assert (target / "complete.json").is_file()


def test_scene_example_prepares_all_categorical_candidate_fibers(
    tmp_path: Path,
) -> None:
    _, fiber_root = _scene_example_publications(tmp_path)
    result = prepare_scene_example_input(
        fiber_root,
        tmp_path / "outputs",
        scale_id="pdq39_score",
        model_family="reference_fiber",
    )
    assert result["scale_display_name"] == "PDQ39 score"
    assert result["selected_tau"] == 400.0
    assert result["details"]["sweet_fiber_count"] == 2
    assert result["details"]["sour_fiber_count"] == 2
    assert result["details"]["candidate_fiber_count"] == 4
    assert result["details"]["unselected_candidate_fiber_count"] == 0
    payload = loadmat(result["input_path"])
    np.testing.assert_array_equal(payload["fiber_ids"].reshape(-1), [1, 2, 3, 4])
    np.testing.assert_allclose(payload["scores"].reshape(-1), [0.8, -0.6, 0.4, -0.2])
    np.testing.assert_array_equal(
        payload["fiber_roles"].reshape(-1), [1, -1, 1, -1]
    )
    np.testing.assert_array_equal(payload["idx"].reshape(-1), [2, 2, 2, 2])
    assert payload["fibers"].shape == (8, 3)


def test_scene_example_rejects_run_store_study_base(tmp_path: Path) -> None:
    direct_root, _ = _scene_example_publications(tmp_path)
    manifest_path = direct_root / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = Path(manifest["study_base_path"])
    forbidden = tmp_path / ".runs" / "inputs" / "study_base.json"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_bytes(source.read_bytes())
    manifest["study_base_path"] = str(forbidden)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        SceneExampleInputError,
        match="study base cannot resolve through a run store",
    ):
        prepare_scene_example_input(
            direct_root,
            tmp_path / "outputs",
            scale_id="pdq39_score",
            model_family="reference_voxel",
        )


def test_scene_example_rejects_run_store_connectome_geometry(
    tmp_path: Path,
) -> None:
    _, fiber_root = _scene_example_publications(tmp_path)
    manifest_path = fiber_root / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    study_path = fiber_root / Path(manifest["study_base_path"]).name
    manifest["study_base_path"] = str(study_path)
    study = json.loads(study_path.read_text(encoding="utf-8"))
    streamlines = study["study"]["spot_model_sources"]["connectomes"][0][
        "streamlines"
    ]
    source = Path(streamlines["path"])
    forbidden = tmp_path / ".runs" / "connectomes" / "connectome.mat"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_bytes(source.read_bytes())
    streamlines["path"] = str(forbidden)
    study_path.write_text(json.dumps(study), encoding="utf-8")
    manifest["study_base_sha256"] = _sha256(study_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        SceneExampleInputError,
        match="geometry cannot resolve through a run store",
    ):
        prepare_scene_example_input(
            fiber_root,
            tmp_path / "outputs",
            scale_id="pdq39_score",
            model_family="reference_fiber",
        )


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
        collection.get_linewidths()[0] == pytest.approx(1.0)
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
    assert metadata["mask_linewidth_pt"] == 1.0
    assert metadata["colorbar_label"] == "Benefit-oriented partial Spearman ρ"
    assert metadata["global_box_span_mm"] == [12.0, 10.0]
    assert metadata["font_family"] == "Arial"
    assert metadata["label_top_bg_color"] == "#D7E3E0"
    assert metadata["label_right_bg_color"] == "#E3DCCF"
    assert metadata["strip_background_alpha"] == 1.0
    for panel_range in metadata["panel_ranges_mm"].values():
        assert panel_range["xlim"][1] - panel_range["xlim"][0] == pytest.approx(12.0)
        assert panel_range["ylim"][1] - panel_range["ylim"][0] == pytest.approx(10.0)
    top_strips = [axis for axis in figure.axes if axis.get_gid() == "voxel-top-strip"]
    right_strips = [
        axis for axis in figure.axes if axis.get_gid() == "voxel-right-strip"
    ]
    assert len(top_strips) == 3
    assert len(right_strips) == 3
    assert all(axis.patch.get_alpha() == 1.0 for axis in top_strips + right_strips)
    top_rgba = (*tuple(np.asarray((0xD7, 0xE3, 0xE0)) / 255.0), 1.0)
    right_rgba = (*tuple(np.asarray((0xE3, 0xDC, 0xCF)) / 255.0), 1.0)
    assert all(axis.get_facecolor() == pytest.approx(top_rgba) for axis in top_strips)
    assert all(
        axis.get_facecolor() == pytest.approx(right_rgba) for axis in right_strips
    )
    assert all(
        text.get_fontfamily()[0] == "Arial"
        for text in figure.findobj(Text)
        if text.get_text()
    )
    rendered = plt.imread(output)
    top_rgb = np.asarray((0xD7, 0xE3, 0xE0), dtype=float) / 255.0
    right_rgb = np.asarray((0xE3, 0xDC, 0xCF), dtype=float) / 255.0
    assert np.count_nonzero(
        np.all(np.isclose(rendered[..., :3], top_rgb, atol=2.0 / 255.0), axis=-1)
    ) > 10
    assert np.count_nonzero(
        np.all(np.isclose(rendered[..., :3], right_rgb, atol=2.0 / 255.0), axis=-1)
    ) > 10
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
            assert (
                leaf
                / "completion"
                / "voxel_2d"
                / stem
                / "complete.json"
            ).is_file()
            result = json.loads((leaf / f"{stem}.json").read_text(encoding="utf-8"))
            assert result["status"] == "complete"
            assert result["model_role"] == role
            assert result["scale_display_name"] == "PDQ39 score"
            assert result["colorbar_semantic_label"] == (
                "Benefit-oriented partial Spearman ρ with PDQ39 score"
            )
            assert result["style"]["colorbar_label"] == (
                "Benefit-oriented partial Spearman ρ\nwith PDQ39 score"
            )
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


def test_voxel_components_do_not_write_formal_root_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    publication, anatomy, reference_mask, addon_mask = _voxel_section_publication(
        tmp_path
    )
    output_root = tmp_path / "formal_components"
    catalog = PublicationCatalog.from_config(
        {
            "direct_voxel_main": {
                "root": str(publication),
                "manifest": "model_manifest.json",
            }
        },
        config_base=tmp_path,
    )
    resources = {
        "background": _resource_record(anatomy, "anatomy_background"),
        "reference_mask": _resource_record(reference_mask, "reference_mask"),
        "addon_mask": _resource_record(addon_mask, "addon_mask"),
    }
    style = get_voxel_section_cfg(
        {
            "formats": ("png",),
            "dpi": 72,
            "resolution_mm": 0.5,
            "boxsize": (12.0, 10.0),
            "panel_gap": (1.0, 1.0),
        }
    )

    first = render_voxel_section_components(
        scale_ids=("pdq39_score",),
        output_root=output_root,
        catalog=catalog,
        resources=resources,
        style=style,
    )
    assert len(first) == 6
    assert all(item["status"] == "complete" for item in first)
    assert not (output_root / "manifest.json").exists()
    assert not (output_root / "figure_index.csv").exists()
    assert not (output_root / "README.md").exists()

    monkeypatch.setattr(
        voxel_section_postprocess,
        "_resolve_sources",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed voxel component reopened its sources")
        ),
    )
    second = render_voxel_section_components(
        scale_ids=("pdq39_score",),
        output_root=output_root,
        catalog=catalog,
        resources=resources,
        style=style,
    )
    assert all(item.get("resume_status") == "reused" for item in second)


def test_formal_voxel_preflight_requires_v2_smoothing_metadata(
    tmp_path: Path,
) -> None:
    publication, _, _, _ = _voxel_section_publication(tmp_path)
    catalog = PublicationCatalog.from_config(
        {
            "direct_voxel_main": {
                "root": str(publication),
                "manifest": "model_manifest.json",
            }
        },
        config_base=tmp_path,
    )
    final_model_path = (
        publication / "pdq39_score" / "reference" / "final_model.json"
    )
    final_model = json.loads(final_model_path.read_text(encoding="utf-8"))
    sources = formal_postprocess._voxel_spatial_sources(
        catalog,
        scale_id="pdq39_score",
        role="reference",
        final_model=final_model,
    )
    assert (
        sources["benefit_map_smooth_fwhm1mm_metadata"].artifact_kind
        == "benefit_map_smooth_metadata"
    )

    derivative = (
        publication
        / "pdq39_score/reference/report/display"
        / "benefit_map_smooth_fwhm1mm.nii.gz"
    )
    metadata_path = Path(f"{derivative}.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["provenance"]["algorithm"] = "masked_normalized_gaussian_v1"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="display smoothing v2 contract differs"):
        formal_postprocess._voxel_spatial_sources(
            catalog,
            scale_id="pdq39_score",
            role="reference",
            final_model=final_model,
        )


def test_legacy_matlab_visualization_functions_are_merged() -> None:
    viz_root = Path(__file__).resolve().parents[1]
    assert not (viz_root.parent / "visualization").exists()
    for name in (
        "mh_fiber_make_scene.m",
        "mh_fiber_open_scene.m",
        "mh_fiber_style_electrodes.m",
        "mh_viz_default_fiber_scene_spec.m",
        "mh_viz_default_fiber_views.m",
        "mh_viz_default_model_views.m",
        "mh_viz_apply_soft_camera_lighting.m",
        "mh_viz_export_pdq39_fiber_coefficient_pdfs.m",
        "mh_viz_export_pdq39_fiber_pdfs.m",
        "mh_viz_export_pdq39_voxel_pdfs.m",
        "mh_viz_export_scene_views.m",
        "mh_viz_make_sweet_sour_scene.m",
        "mh_viz_prepare_scene_example_input.m",
        "mh_viz_show_categorical_fibers.m",
        "mh_viz_show_coefficient_fibers.m",
        "mh_viz_show_scored_fibers.m",
    ):
        assert (viz_root / name).is_file()
    for name in (
        "open_pdq39_reference_voxel_scene.m",
        "open_pdq39_reference_fiber_scene.m",
        "open_pdq39_addon_voxel_scene.m",
        "open_pdq39_addon_fiber_scene.m",
        "open_pdq39_reference_fiber_coefficient_scene.m",
        "open_pdq39_addon_fiber_coefficient_scene.m",
    ):
        assert (viz_root / "examples" / name).is_file()
    voxel_example_path = (
        viz_root / "examples" / "open_pdq39_reference_voxel_scene.m"
    )
    voxel_example = voxel_example_path.read_text(encoding="utf-8")
    voxel_exporter = (
        viz_root / "mh_viz_export_pdq39_voxel_pdfs.m"
    ).read_text(encoding="utf-8")
    addon_voxel_example = (
        viz_root / "examples" / "open_pdq39_addon_voxel_scene.m"
    ).read_text(encoding="utf-8")
    assert "spec.VoxelSampleDepthMm = 1.0;" in voxel_example
    assert "spec.VoxelSampleDepthMm = 1.0;" in addon_voxel_example
    assert "spec.VoxelSampleDepthMm = 1.0;" in voxel_exporter
    prepare_scene_helper = (
        viz_root / "mh_viz_prepare_scene_example_input.m"
    ).read_text(encoding="utf-8")
    assert "addParameter(parser, 'Force', false" in prepare_scene_helper
    assert "commandParts{end + 1} = '--force';" in prepare_scene_helper
    assert "spec.AtlasName = 'Custom_STNSNr';" in voxel_example
    assert "spec.AtlasRoiIndices = 2;" in voxel_example
    assert "spec.ViewStruct = modelViews.reference{1};" in voxel_example
    assert "spec.AtlasEdgeAlpha = 0.15;" in voxel_example
    assert "Benefit-oriented partial Spearman ρ with %s" in voxel_example
    fiber_example = (
        viz_root / "examples" / "open_pdq39_reference_fiber_scene.m"
    ).read_text(encoding="utf-8")
    assert "spec.FiberCategoricalMat = pdq39FiberInput.input_path;" in (
        fiber_example
    )
    assert "fiberStyle = mh_viz_default_fiber_scene_spec();" in fiber_example
    assert "spec.CandidateFiberAlpha = fiberStyle.CandidateFiberAlpha;" in (
        fiber_example
    )
    assert "spec.FiberLegendTextColor = fiberStyle.FiberLegendTextColor;" in (
        fiber_example
    )
    assert "spec.BackgroundColor = fiberStyle.BackgroundColor;" in fiber_example
    assert "spec.AddRASTriad = fiberStyle.AddRASTriad;" in fiber_example
    assert "spec.AnatomyNifti = fiberStyle.AnatomyNifti;" in fiber_example
    assert "spec.AtlasRoiIndices = 2;" in fiber_example
    assert "fiberViews = mh_viz_default_fiber_views();" in fiber_example
    assert "spec.ViewStruct = fiberViews.reference{1};" in fiber_example
    for model_family, scene_kind in (
        ("addon_voxel", "voxel"),
        ("addon_fiber", "fiber"),
    ):
        addon_example = (
            viz_root / "examples" / f"open_pdq39_addon_{scene_kind}_scene.m"
        ).read_text(encoding="utf-8")
        assert f"publicationRoot, '{model_family}'" in addon_example
        assert "spec.AtlasRoiIndices = 1;" in addon_example
        if scene_kind == "voxel":
            assert "spec.ViewStruct = modelViews.addon{1};" in addon_example
        else:
            assert "spec.ViewStruct = fiberViews.addon{1};" in addon_example
    scene_source = (viz_root / "mh_viz_make_sweet_sour_scene.m").read_text(
        encoding="utf-8"
    )
    assert "defaults.VoxelSampleDepthMm = 1.0;" in scene_source
    assert "defaults.AtlasName = 'Custom_STNSNr';" in scene_source
    assert "defaults.AtlasReduceFactor = 0.5;" in scene_source
    assert "defaults.AtlasEdgeAlpha = 0.15;" in scene_source
    assert "defaults.AtlasRoiIndices = [];" in scene_source
    assert "defaults.FigureBackend = 'leaddbs';" in scene_source
    assert "defaults.StrictHeadless = false;" in scene_source
    assert "defaults.FiberCategoricalMat = '';" in scene_source
    assert "defaults.FiberCoefficientMat = '';" in scene_source
    assert "defaults.CandidateFiberColor = [204, 204, 204] / 255;" in (
        scene_source
    )
    assert "defaults.CandidateFiberAlpha = 1.0;" in scene_source
    assert "defaults.CoefficientFiberAlpha = 1.0;" in scene_source
    assert "defaults.CoefficientFiberLineWidth = 0.25;" in scene_source
    assert "defaults.SweetFiberColor = [242, 0, 14] / 255;" in scene_source
    assert "defaults.SourFiberColor = [14, 106, 175] / 255;" in scene_source
    assert "defaults.SelectedFiberRenderMode = 'tube';" in scene_source
    assert "defaults.SelectedFiberLineWidth = 0.50;" in scene_source
    assert "mh_viz_show_categorical_fibers(" in scene_source
    assert "mh_viz_show_coefficient_fibers(" in scene_source
    assert "'SelectedRenderMode', spec.SelectedFiberRenderMode" in scene_source
    assert "'SelectedLineWidth', spec.SelectedFiberLineWidth" in scene_source
    assert "'%s: %d'" in scene_source
    assert "'LineStyle', '-'" in scene_source
    assert "'Marker', 'none'" in scene_source
    assert "'Tag', 'mh_viz_fiber_legend'" in scene_source
    assert "hLegend.Position = [0.72, 0.43, 0.25, 0.14];" in scene_source
    assert "'TextColor', spec.FiberLegendTextColor" in scene_source
    assert "'mh_viz_fiber_legend_colors'" in scene_source
    assert "'mh_viz_fiber_legend_labels'" in scene_source
    assert "local_apply_categorical_fiber_layer_order(hAx, objects);" in (
        scene_source
    )
    assert "set(hAx, 'SortMethod', 'childorder');" in scene_source
    assert "objects.fiberCandidate," in scene_source
    assert "objects.fiberSweet," in scene_source
    assert "objects.fiberSour};" in scene_source
    assert "uistack(handles, 'top');" in scene_source
    assert "plotConfig.FigureBackend = char(string(spec.FigureBackend));" in (
        scene_source
    )
    assert "plotConfig.StrictHeadless = logical(spec.StrictHeadless);" in (
        scene_source
    )
    assert "mh_viz_make_sweet_sour_scene:StrictHeadlessVisibleFigure" in (
        scene_source
    )
    assert "clear visibilityCleanup;" not in scene_source
    assert "defaults.RASShowLabels = true;" in scene_source
    assert "fiberDefaults = mh_viz_default_fiber_scene_spec();" in scene_source
    assert "local_add_explicit_anatomy_slice(hFig, hAx, spec)" in scene_source
    assert "volume = nifti(pathValue);" in scene_source
    assert "handle = slice3i(" in scene_source
    assert "set(hFig, 'Color', spec.BackgroundColor);" in scene_source
    assert "set(hAx, 'Color', 'none');" in scene_source
    assert "if ~isempty(spec.ViewStruct)" in scene_source
    assert "elseif ~usesReferenceVoxelHeatmap" in scene_source
    assert "mh_viz_apply_soft_camera_lighting(hAx);" in scene_source
    surface_defaults = (
        viz_root / "surface/batch_helper/default_nifti2patch_config.m"
    ).read_text(encoding="utf-8")
    assert "cfg_nifti2patch.SampleDepthMm              = 1.0;" in (
        surface_defaults
    )
    model_views = (viz_root / "mh_viz_default_model_views.m").read_text(
        encoding="utf-8"
    )
    assert "views.reference = {reference1, reference2};" in model_views
    assert "views.addon = {addon1, addon2};" in model_views
    assert "reference1.camva = 0.3500;" in model_views
    assert "reference1.campos = [-841.1497 -1.6125e+03 481.0182];" in model_views
    assert "addon1.camva = 0.5000;" in model_views
    assert "reference1.camtarget = [9.8725 -14.8273 -6.5437];" in model_views
    assert "reference2.camtarget = [8.5895 -16.9006 -8.6190];" in model_views
    assert "addon2.camtarget = [9.1244 -16.2821 -12.1207];" in model_views
    assert "addon1.camtarget = [9.6266 -16.6089 -12.8113];" in model_views
    fiber_views = (viz_root / "mh_viz_default_fiber_views.m").read_text(
        encoding="utf-8"
    )
    assert "fiberView.az = 0;" in fiber_views
    assert "fiberView.el = 0;" in fiber_views
    assert "fiberView.camva = 3.8000;" in fiber_views
    assert "fiberView.camup = [0 0 1];" in fiber_views
    assert "fiberView.camproj = 'orthographic';" in fiber_views
    assert "fiberView.camtarget = [9.8538 -48.8761 9.6955];" in fiber_views
    assert "fiberView.campos = [1.8846e+03 -48.8761 9.6955];" in fiber_views
    assert "views.reference = {fiberView};" in fiber_views
    assert "views.addon = {fiberView};" in fiber_views
    fiber_style = (
        viz_root / "mh_viz_default_fiber_scene_spec.m"
    ).read_text(encoding="utf-8")
    assert "spec.CandidateFiberAlpha = 1.0;" in fiber_style
    assert "spec.CoefficientFiberAlpha = 1.0;" in fiber_style
    assert "spec.CoefficientFiberLineWidth = 0.25;" in fiber_style
    assert "spec.FiberColorbarTextColor = [1, 1, 1];" in fiber_style
    assert "spec.SelectedFiberRenderMode = 'line';" in fiber_style
    assert "spec.SelectedFiberLineWidth = 0.50;" in fiber_style
    assert "spec.FiberLegendTextColor = [1, 1, 1];" in fiber_style
    assert "spec.BackgroundColor = [0, 0, 0];" in fiber_style
    assert "spec.AddRASTriad = false;" in fiber_style
    assert "spec.AnatomySliceAlpha = 1.0;" in fiber_style
    assert "spec.AnatomySlicePlane = 'x';" in fiber_style
    assert "spec.AnatomySliceCoordinateMm = 5;" in fiber_style
    assert "spec.AnatomySliceTransparencyPercent = 100;" in fiber_style
    assert "7T_100um_Edlow_2019.nii" in fiber_style
    exporter = (viz_root / "mh_viz_export_scene_views.m").read_text(
        encoding="utf-8"
    )
    assert "{'reference', 'addon'}" in exporter
    assert "'Transparent', false" in exporter
    assert "addParameter(parser, 'ContentType', 'mixed'" in exporter
    assert "addParameter(parser, 'IncludeAnatomySlices', false" in exporter
    assert "addParameter(parser, 'RequireRASLabels', true" in exporter
    assert "requiredRoiIndex = 2;" in exporter
    assert "requiredRoiIndex = 1;" in exporter
    assert "'Custom_STNSNr'" in exporter
    assert "mh_viz_export_scene_views:MissingRoleRoi" in exporter
    assert "mh_viz_export_scene_views:CameraMismatch" in exporter
    assert "local_assert_camera(hAx, viewSpec, role, viewIndex);" in exporter
    assert "local_apply_camera_lighting(hAx);" in exporter
    mixed_pdf_exporter = (
        viz_root / "surface/render/ea_export_figure_transparent.m"
    ).read_text(encoding="utf-8")
    assert "fiberLegendSpecs = local_capture_fiber_legends(hFig);" in (
        mixed_pdf_exporter
    )
    assert "set(fiberLegends(i), 'Visible', 'off');" in (
        mixed_pdf_exporter
    )
    assert "local_draw_vector_fiber_legend(compFig, fiberLegendSpecs(i));" in (
        mixed_pdf_exporter
    )
    assert "local_capture_vector_fiber_layers" not in mixed_pdf_exporter
    assert "convertDataSpaceCoordsToViewerCoords" not in mixed_pdf_exporter
    assert "set(fiberGraphics(i), 'Visible', 'off');" not in (
        mixed_pdf_exporter
    )
    assert "'Tag', 'mh_viz_fiber_legend_matte'" in mixed_pdf_exporter
    assert "'Color', spec.TextColor" in mixed_pdf_exporter
    assert "maxLabelLength = 0.90;" in mixed_pdf_exporter
    assert "labelFontSize = max(12" in mixed_pdf_exporter
    silent_exporter = (
        viz_root / "mh_viz_export_pdq39_voxel_pdfs.m"
    ).read_text(encoding="utf-8")
    assert "spec.FigureVisible = 'off';" in silent_exporter
    assert "spec.FigureBackend = 'matlab';" in silent_exporter
    assert "spec.StrictHeadless = true;" in silent_exporter
    assert "oldDefaultFigureVisible = get(groot, 'DefaultFigureVisible');" in (
        silent_exporter
    )
    assert "groot, 'DefaultFigureVisible', oldDefaultFigureVisible" in (
        silent_exporter
    )
    assert silent_exporter.count("local_assert_hidden(newFigures);") == 2
    assert "spec.AtlasEdgeAlpha = 0.15;" in silent_exporter
    assert "mh_viz_export_pdq39_voxel_pdfs:VisibleFigure" in silent_exporter
    assert "numel(exports) ~= 4" in silent_exporter
    fiber_exporter = (
        viz_root / "mh_viz_export_pdq39_fiber_pdfs.m"
    ).read_text(encoding="utf-8")
    assert "spec.FiberCategoricalMat = prepared.input_path;" in fiber_exporter
    assert "addParameter(parser, 'Views', mh_viz_default_fiber_views()" in (
        fiber_exporter
    )
    assert "fiberStyle = mh_viz_default_fiber_scene_spec();" in fiber_exporter
    assert "spec.CandidateFiberAlpha = fiberStyle.CandidateFiberAlpha;" in (
        fiber_exporter
    )
    assert (
        "spec.SelectedFiberRenderMode = fiberStyle.SelectedFiberRenderMode;"
        in fiber_exporter
    )
    assert (
        "spec.SelectedFiberLineWidth = fiberStyle.SelectedFiberLineWidth;"
        in fiber_exporter
    )
    assert "spec.BackgroundColor = fiberStyle.BackgroundColor;" in fiber_exporter
    assert "spec.AddRASTriad = fiberStyle.AddRASTriad;" in fiber_exporter
    assert "spec.AnatomyNifti = fiberStyle.AnatomyNifti;" in fiber_exporter
    assert "spec.FigureVisible = 'off';" in fiber_exporter
    assert "spec.FigureBackend = 'matlab';" in fiber_exporter
    assert "spec.StrictHeadless = true;" in fiber_exporter
    assert "oldDefaultFigureVisible = get(groot, 'DefaultFigureVisible');" in (
        fiber_exporter
    )
    assert "groot, 'DefaultFigureVisible', oldDefaultFigureVisible" in (
        fiber_exporter
    )
    assert fiber_exporter.count("local_assert_hidden(newFigures);") == 2
    assert "spec.AddToolbarToggles = false;" in fiber_exporter
    assert "'BackgroundColor', fiberStyle.BackgroundColor" in fiber_exporter
    assert "'IncludeAnatomySlices', true" in fiber_exporter
    assert "'RequireRASLabels', false" in fiber_exporter
    assert "numel(exports) ~= expectedExportCount" in fiber_exporter
    assert "'candidate_alpha_hex', 'FF'" in fiber_exporter
    assert "'legend_symbol', 'horizontal_line'" in fiber_exporter
    assert "'legend_text_color', '#FFFFFF'" in fiber_exporter
    assert "'background_color', '#000000'" in fiber_exporter
    assert "'ras_triad_default_enabled', false" in fiber_exporter
    assert "'scene_alignment', 'single_native_3d_axes'" in fiber_exporter
    assert "'axes_sort_method', 'childorder'" in fiber_exporter
    assert (
        "'fiber_layer_order', 'candidate_back_sweet_sour_front'"
        in fiber_exporter
    )
    assert "'fiber_pdf_layer', 'same_axes_raster'" in fiber_exporter
    assert "'anatomy_atlas_pdf_layer', 'same_axes_raster'" in fiber_exporter
    assert "addParameter(parser, 'Resolution', 600" in fiber_exporter
    assert "'anatomy_atlas_raster_dpi', resolution" in fiber_exporter
    assert "'legend_pdf_layer', 'vector'" in fiber_exporter
    assert "pdq39_categorical_fiber_3d_export_v7" in fiber_exporter
    assert "local_assert_layer_order(scene, role);" in fiber_exporter
    assert "metadata.rendered_fiber_count ~= metadata.candidate_fiber_count" in (
        fiber_exporter
    )
    categorical_renderer = (
        viz_root / "mh_viz_show_categorical_fibers.m"
    ).read_text(encoding="utf-8")
    assert "'CandidateColor', [204, 204, 204] / 255" in categorical_renderer
    assert "'CandidateAlpha', 1.0" in categorical_renderer
    assert "'SweetColor', [242, 0, 14] / 255" in categorical_renderer
    assert "'SourColor', [14, 106, 175] / 255" in categorical_renderer
    assert "'SelectedRenderMode', 'line'" in categorical_renderer
    assert "'SelectedLineWidth', 0.50" in categorical_renderer
    assert "handles.sweet = local_selected_patch(" in categorical_renderer
    assert "handles.sour = local_selected_patch(" in categorical_renderer
    assert "maximumRenderedFibers" not in categorical_renderer
    assert "numFiberThreshold" not in categorical_renderer
    assert "metadata.rendered_fiber_count ~= fiberCount" in categorical_renderer
    coefficient_renderer = (
        viz_root / "mh_viz_show_coefficient_fibers.m"
    ).read_text(encoding="utf-8")
    assert "ea_colormap_vik(256)" in coefficient_renderer
    assert "'EdgeColor', 'flat'" in coefficient_renderer
    assert "'FaceVertexCData', vertexColors" in coefficient_renderer
    assert "'Tag', 'mh_viz_fiber_coefficient'" in coefficient_renderer
    assert "maximumRenderedFibers" not in coefficient_renderer
    assert "streamtube" not in coefficient_renderer
    coefficient_exporter = (
        viz_root / "mh_viz_export_pdq39_fiber_coefficient_pdfs.m"
    ).read_text(encoding="utf-8")
    assert "spec.FiberCoefficientMat = prepared.input_path;" in (
        coefficient_exporter
    )
    assert "spec.ShowFiberLegend = false;" in coefficient_exporter
    assert "oldDefaultFigureVisible = get(groot, 'DefaultFigureVisible');" in (
        coefficient_exporter
    )
    assert "groot, 'DefaultFigureVisible', oldDefaultFigureVisible" in (
        coefficient_exporter
    )
    assert coefficient_exporter.count("local_assert_hidden(newFigures);") == 2
    assert "'colormap', 'vik'" in coefficient_exporter
    assert "'colormap_samples', 256" in coefficient_exporter
    assert "'fiber_sampling', 'none'" in coefficient_exporter
    assert "'point_sampling', 'none'" in coefficient_exporter
    assert "'count_legend', false" in coefficient_exporter
    assert "'right_colorbar', true" in coefficient_exporter
    assert "'colorbar_text_color', '#FFFFFF'" in coefficient_exporter
    assert "pdq39_coefficient_fiber_3d_export_v2" in coefficient_exporter
    for role in ("reference", "addon"):
        coefficient_example = (
            viz_root
            / "examples"
            / f"open_pdq39_{role}_fiber_coefficient_scene.m"
        ).read_text(encoding="utf-8")
        assert (
            "spec.FiberCoefficientMat = pdq39FiberInput.input_path;"
            in coefficient_example
        )
        assert "spec.ShowFiberLegend = false;" in coefficient_example
        assert "Benefit-oriented partial Spearman ρ with %s" in (
            coefficient_example
        )
    lighting_source = (
        viz_root / "mh_viz_apply_soft_camera_lighting.m"
    ).read_text(encoding="utf-8")
    assert "'Tag', 'mh_viz_camera_key_light'" in lighting_source
    assert "camlight(keyLight, 'headlight');" in lighting_source
    assert "'Tag', 'mh_viz_camera_fill_light'" in lighting_source
    assert "camlight(leftLight, 'left');" in lighting_source
    assert "'Tag', 'mh_viz_camera_ceiling_light'" in lighting_source
    assert "'AmbientStrength', 0.78" in lighting_source
    assert "'DiffuseStrength', 0.22" in lighting_source
    assert "'Color', [0.98, 0.98, 0.98]" in lighting_source
    assert "'Color', [0.14, 0.14, 0.14]" in lighting_source
    assert "'Color', [0.08, 0.08, 0.08]" in lighting_source
    assert "'SpecularStrength', 0.12" in lighting_source
    assert "'SpecularExponent', 24" in lighting_source
    assert "'SpecularColorReflectance', 0.20" in lighting_source
    assert "getappdata(hFig, appDataName)" in lighting_source
    assert "setappdata(hFig, 'CamLight', keyLight);" in lighting_source
    assert "setappdata(hFig, 'RightLight', rightLight);" in lighting_source
    assert "setappdata(hFig, 'LeftLight', leftLight);" in lighting_source
    assert "setappdata(hFig, 'CeilingLight', ceilingLight);" in lighting_source
    assert "setappdata(hFig, 'mh_viz_lighting_preset', preset);" in lighting_source
    assert "mh_viz_open_elvis_lighting_control(hFig)" in lighting_source
    assert "set(rightLight, 'Visible', 'off'" in lighting_source
    assert "'Visible', 'on'" in lighting_source
    assert "delete(existingLights);" not in lighting_source
    assert "findall(hFig, 'Type', 'patch')" in lighting_source
    assert "findall(hFig, 'Type', 'surface')" in lighting_source
    assert "FaceColor" not in lighting_source
    lighting_adapter = (
        viz_root / "mh_viz_open_elvis_lighting_control.m"
    ).read_text(encoding="utf-8")
    assert "app = ea_set_lighting(hFig);" in lighting_adapter
    assert "app.AmbientStrengthSlider.Value" in lighting_adapter
    assert "app.DiffuseStrengthSlider.Value" in lighting_adapter
    assert "app.SpecularStrengthSlider.Value" in lighting_adapter
    assert "app.SpecularExponentSlider.Value" in lighting_adapter
    assert "app.SpecularColorReflectanceSlider.Value" in lighting_adapter
    repo_root = viz_root.parents[3]
    default_view_source = (repo_root / "ea_defaultview.m").read_text(
        encoding="utf-8"
    )
    assert "[resultfig, arguments] = local_resolve_figure(varargin);" in (
        default_view_source
    )
    assert "isgraphics(arguments{1}, 'figure')" in default_view_source
    transition_source = (
        repo_root / "ea_defaultview_transition.m"
    ).read_text(encoding="utf-8")
    assert "[resultfig, v, ~] = local_resolve_inputs(varargin);" in (
        transition_source
    )
    elvis_source = (repo_root / "ea_elvis.m").read_text(encoding="utf-8")
    assert (
        "'ClickedCallback',{@save_currentview_callback,resultfig}"
        in elvis_source
    )
    assert (
        "'ClickedCallback',{@set_defaultview_callback,resultfig}"
        in elvis_source
    )
    assert "ea_defaultview_transition(resultfig,v,togglestates);" in elvis_source
    mouse_camera_source = (
        repo_root / "helpers/gui/ea_mouse_camera.m"
    ).read_text(encoding="utf-8")
    assert "ea_defaultview_transition(hfig,v,togglestates);" in (
        mouse_camera_source
    )
    view_application = (
        viz_root / "surface/render/ea_apply_view_struct.m"
    ).read_text(encoding="utf-8")
    assert "camproj(hAx, char(v.camproj));" in view_application
    assert "camva(hAx, double(v.camva));" in view_application
    assert "camup(hAx, double(v.camup(:))');" in view_application
    assert "camtarget(hAx, double(v.camtarget(:))');" in view_application
    assert "campos(hAx, double(v.campos(:))');" in view_application
    ras_triad = (
        viz_root / "surface/render/ea_add_ras_triad.m"
    ).read_text(encoding="utf-8")
    assert "addParameter(ip, 'ShowLabels', true" in ras_triad
    for label in ("R", "A", "S"):
        assert f"EA_RAS_TRIAD_LABEL_{label}" in ras_triad
