from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np
import yaml

from my_helper.fiber.core.viz.fiber_section_postprocess import (
    prepare_fiber_section_context,
    render_fiber_section_components,
    run_single_scale_fiber_section_postprocess,
)
from my_helper.fiber.core.viz.fiber_projection import (
    compute_fiber_spatial_projection,
    load_binary_projection_mask,
    streamline_flat_voxels,
)
from my_helper.fiber.core.viz.published_artifacts import PublicationCatalog


def _write_mask(
    path: Path,
    voxels: list[tuple[int, int, int]],
    *,
    shape: tuple[int, int, int] = (5, 5, 5),
) -> Path:
    data = np.zeros(shape, dtype=np.uint8)
    for voxel in voxels:
        data[voxel] = 1
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fiber_publication(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "publication"
    connectome_path = tmp_path / "connectome" / "data.mat"
    connectome_path.parent.mkdir(parents=True)
    streamlines = (
        np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 1.0, 0.0]]),
        np.asarray([[0.0, 0.0, 0.0], [2.0, 1.0, 0.0]]),
        np.asarray([[1.0, 0.0, 0.0], [1.0, 0.0, 1.0]]),
        np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
    )
    lengths = np.asarray([len(value) for value in streamlines], dtype=np.float64)
    coordinates = np.concatenate(streamlines, axis=0).astype(np.float32)
    point_ids = np.repeat(np.arange(1, 5, dtype=np.float32), lengths.astype(int))
    with h5py.File(connectome_path, "w") as handle:
        handle.create_dataset("idx", data=lengths.reshape(1, -1))
        handle.create_dataset(
            "fibers",
            data=np.vstack((coordinates.T, point_ids.reshape(1, -1))),
        )

    rows: list[dict[str, object]] = []
    for role in ("reference", "addon"):
        resolver_relative = (
            f"pdq39_score/{role}/connectomes/synthetic_connectome/resolver"
        )
        resolver = root / resolver_relative
        resolver.mkdir(parents=True)
        artifacts = {
            "valid_fiber_ids.npy": np.asarray([1, 2, 3, 4], dtype=np.int64),
            "full_weights.npy": np.asarray([2.0, -1.0, 1.0, -0.5]),
            "selected_sweet_fiber_ids.npy": np.asarray([1, 3], dtype=np.int64),
            "selected_sour_fiber_ids.npy": np.asarray([2, 4], dtype=np.int64),
        }
        for name, value in artifacts.items():
            path = resolver / name
            np.save(path, value)
            rows.append(
                {
                    "relative_path": f"{resolver_relative}/{name}",
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                    "status": "completed",
                    "artifact_kind": name.removesuffix(".npy"),
                }
            )
        source_selection_path = resolver / "source_selection.json"
        source_selection_path.write_text(
            json.dumps({"schema_version": "normative_fiber_source_selection_v1"}),
            encoding="utf-8",
        )
        rows.append(
            {
                "relative_path": f"{resolver_relative}/source_selection.json",
                "sha256": _sha256(source_selection_path),
                "size_bytes": source_selection_path.stat().st_size,
                "status": "completed",
                "artifact_kind": "source_selection",
            }
        )
        final_path = root / "pdq39_score" / role / "final_model.json"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(
            json.dumps(
                {
                    "schema_version": "normative_fiber_final_model_v1",
                    "scale_id": "pdq39_score",
                    "model_family": role,
                    "formal_connectome_id": "synthetic_connectome",
                    "final_branch": "reference" if role == "reference" else "delta_reference_adjusted",
                    "final_status": "final_model_realized",
                    "selected_tau_v_per_m": 400.0,
                    "selected_coverage_subjects_min": 5,
                    "resolver_relative_path": f"{resolver_relative}/source_selection.json",
                    "valid_feature_axis_relative_path": f"{resolver_relative}/valid_fiber_ids.npy",
                }
            ),
            encoding="utf-8",
        )
        rows.append(
            {
                "relative_path": f"pdq39_score/{role}/final_model.json",
                "sha256": _sha256(final_path),
                "size_bytes": final_path.stat().st_size,
                "status": "completed",
                "artifact_kind": "final_model",
            }
        )
    manifest = {
        "final_status": "completed",
        "model_set_id": "synthetic",
        "formal_connectome_id": "synthetic_connectome",
        "connectomes": [
            {
                "connectome_id": "synthetic_connectome",
                "path": str(connectome_path),
                "role": "formal",
            }
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (root / "artifact_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "relative_path",
                "sha256",
                "size_bytes",
                "status",
                "artifact_kind",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    return root, connectome_path


def test_streamline_projection_uses_segment_aware_once_per_voxel_incidence() -> None:
    streamline = np.asarray([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    voxels = streamline_flat_voxels(
        streamline,
        affine=np.eye(4),
        shape=(5, 5, 5),
    )
    expected = np.asarray(
        [np.ravel_multi_index((index, 0, 0), (5, 5, 5)) for index in range(4)]
    )
    np.testing.assert_array_equal(voxels, expected)


def test_target_score_and_fractional_seed_composition_are_separate(
    tmp_path: Path,
) -> None:
    seed = load_binary_projection_mask(
        _write_mask(
            tmp_path / "seed.nii.gz",
            [(0, 0, 0), (1, 0, 0), (1, 0, 1)],
        ),
        roi_id="seed",
        role="seed",
    )
    targets = (
        load_binary_projection_mask(
            _write_mask(tmp_path / "target_a.nii.gz", [(2, 0, 0)]),
            roi_id="target_a",
            role="target",
        ),
        load_binary_projection_mask(
            _write_mask(tmp_path / "target_b.nii.gz", [(2, 1, 0)]),
            roi_id="target_b",
            role="target",
        ),
        load_binary_projection_mask(
            _write_mask(tmp_path / "target_empty.nii.gz", []),
            roi_id="target_empty",
            role="target",
        ),
    )
    streamlines = (
        np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 1.0, 0.0]]),
        np.asarray([[0.0, 0.0, 0.0], [2.0, 1.0, 0.0]]),
        np.asarray([[1.0, 0.0, 0.0], [1.0, 0.0, 1.0]]),
    )
    result = compute_fiber_spatial_projection(
        fiber_ids=np.asarray([1, 2, 3]),
        scores=np.asarray([2.0, -1.0, 1.0]),
        is_sweet=np.asarray([True, False, True]),
        streamlines=streamlines,
        seed=seed,
        targets=targets,
    )

    np.testing.assert_array_equal(
        result.target_membership,
        np.asarray(
            [
                [True, True, False],
                [False, True, False],
                [False, False, False],
            ]
        ),
    )
    np.testing.assert_allclose(result.target_scores[:2], [2.0, 0.5])
    assert np.isnan(result.target_scores[2])
    np.testing.assert_allclose(
        result.target_membership_fraction[0], [0.5, 0.5, 0.0]
    )
    np.testing.assert_allclose(
        result.target_membership_fraction[1], [0.0, 1.0, 0.0]
    )
    assert result.mass_conservation_max_abs_error < 1e-12
    np.testing.assert_allclose(
        result.target_composition_mass.sum(axis=1),
        result.target_assigned_mass,
    )
    assert np.all(
        (result.target_assignment_fraction >= 0.0)
        & (result.target_assignment_fraction <= 1.0)
    )
    assert np.all(np.isfinite(result.target_conditioned_score[result.target_assigned_mass > 0]))


def test_projection_rejects_selected_fiber_outside_seed(tmp_path: Path) -> None:
    seed = load_binary_projection_mask(
        _write_mask(tmp_path / "seed.nii.gz", [(0, 0, 0)]),
        roi_id="seed",
        role="seed",
    )
    target = load_binary_projection_mask(
        _write_mask(tmp_path / "target.nii.gz", [(4, 4, 4)]),
        roi_id="target",
        role="target",
    )
    try:
        compute_fiber_spatial_projection(
            fiber_ids=[1],
            scores=[1.0],
            is_sweet=[True],
            streamlines=[np.asarray([[3.0, 3.0, 3.0], [4.0, 4.0, 4.0]])],
            seed=seed,
            targets=(target,),
        )
    except ValueError as error:
        assert "configured role seed" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("projection accepted a selected fiber outside the seed")


def test_single_scale_fiber_postprocess_writes_and_reuses_two_roles(
    tmp_path: Path,
) -> None:
    publication, _ = _write_fiber_publication(tmp_path)
    resources = tmp_path / "resources"
    resources.mkdir()
    seed = _write_mask(
        resources / "seed.nii.gz",
        [(0, 0, 0), (1, 0, 0), (1, 0, 1)],
    )
    target_a = _write_mask(resources / "target_a.nii.gz", [(2, 0, 0)])
    target_b = _write_mask(resources / "target_b.nii.gz", [(2, 1, 0)])
    anatomy_data = np.arange(125, dtype=np.float32).reshape((5, 5, 5))
    anatomy = resources / "anatomy.nii"
    nib.save(nib.Nifti1Image(anatomy_data, np.eye(4)), anatomy)
    config = {
        "schema_version": "normative_fiber_spatial_projection_v1",
        "background": {
            "path": str(anatomy),
            "loading": "panel_local_lazy",
            "role": "display_only",
        },
        "projection": {
            "grid_source": "role_seed",
            "direct_streamline_scope": "complete_path",
            "target_conditioned_scope": "seed_only",
            "per_fiber_per_voxel": "once",
            "target_hit_method": "segment_intersection",
            "target_membership": "independent_binary",
            "target_composition": "fractional_by_hit_count",
            "streamline_weight_source": "uniform_one",
            "no_target_policy": "exclude_and_report",
        },
        "seeds": {
            "reference": {"side": "rh", "path": str(seed)},
            "addon": {"side": "rh", "path": str(seed)},
        },
        "targets": [
            {"name": "target_a", "side": "rh", "path": str(target_a)},
            {"name": "target_b", "side": "rh", "path": str(target_b)},
        ],
    }
    config_path = tmp_path / "fiber_spatial_projection.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    output = tmp_path / "postprocess"
    arguments = {
        "scale_id": "pdq39_score",
        "output_root": output,
        "normative_fiber_publication_root": publication,
        "spatial_config_path": config_path,
        "style_overrides": {
            "dpi": 72,
            "resolution_mm": 1.0,
            "boxsize": (12.0, 10.0),
            "panel_gap": (1.0, 1.0),
            "formats": ("png",),
        },
    }

    first = run_single_scale_fiber_section_postprocess(**arguments)
    assert first["status"] == "complete"
    assert first["completed_count"] == 2
    assert first["failed_count"] == 0
    assert first["reused_count"] == 0
    for role in ("reference", "addon"):
        leaf = output / "scales" / "pdq39_score" / role / "fiber"
        assert (leaf / "direct_streamline/maps/streamline_score_mean.nii.gz").is_file()
        assert (leaf / "target_conditioned/maps/target_conditioned_score.nii.gz").is_file()
        assert (leaf / "target_conditioned/tables/target_scores.csv").is_file()
        assert (
            leaf / "direct_streamline/figures/streamline_score_mean_sections.png"
        ).is_file()
        assert (
            leaf / "target_conditioned/figures/target_conditioned_score_sections.png"
        ).is_file()
        target_qc = json.loads(
            (leaf / "target_conditioned/target_membership_qc.json").read_text(
                encoding="utf-8"
            )
        )
        assert target_qc["mass_conservation_max_abs_error"] < 1e-12
        figure_json = json.loads(
            (
                leaf
                / "target_conditioned/figures/target_conditioned_score_sections.json"
            ).read_text(encoding="utf-8")
        )
        assert figure_json["render_metadata"]["slice_support_source"] == (
            "positive_geometry_image"
        )
        assert figure_json["render_metadata"]["background_loading_mode"] == (
            "panel_local_lazy"
        )

    second = run_single_scale_fiber_section_postprocess(**arguments)
    assert second["status"] == "complete"
    assert second["failed_count"] == 0
    assert second["reused_count"] == 2

    formal_output = tmp_path / "formal_components"
    catalog = PublicationCatalog.from_config(
        {
            "normative_fiber_main": {
                "root": str(publication),
                "manifest": "model_manifest.json",
            }
        },
        config_base=tmp_path,
    )
    context = prepare_fiber_section_context(
        catalog=catalog, spatial_config_path=config_path
    )
    component_first = render_fiber_section_components(
        scale_ids=("pdq39_score",),
        output_root=formal_output,
        catalog=catalog,
        context=context,
        style_overrides=arguments["style_overrides"],
    )
    assert len(component_first) == 2
    assert all(item["status"] == "complete" for item in component_first)
    assert all(Path(item["result_path"]).name == "fiber_spatial.json" for item in component_first)
    assert not (formal_output / "manifest.json").exists()
    assert not (formal_output / "endpoint_index.csv").exists()
    assert not (formal_output / "README.md").exists()

    component_second = render_fiber_section_components(
        scale_ids=("pdq39_score",),
        output_root=formal_output,
        catalog=catalog,
        context=context,
        style_overrides=arguments["style_overrides"],
    )
    assert all(item.get("resume_status") == "reused" for item in component_second)
