from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np
import pytest
import yaml
from scipy.stats import rankdata

from my_helper.fiber.core.viz import fiber_section_postprocess
from my_helper.fiber.core.seed_target_connectivity.connectome import open_connectome
from my_helper.fiber.core.viz.fiber_composition import (
    apply_target_scores_to_composition,
    build_whole_connectome_composition,
    compute_selected_target_scores,
    compute_target_scores,
    target_membership_from_bits,
)
from my_helper.fiber.core.viz.fiber_section_postprocess import (
    prepare_fiber_section_context,
    render_fiber_section_components,
    run_single_scale_fiber_section_postprocess,
)
from my_helper.fiber.core.viz.fiber_projection import (
    compute_selected_direct_projection,
    load_binary_projection_mask,
    streamline_flat_voxels,
)
from my_helper.fiber.core.viz.published_artifacts import PublicationCatalog
from my_helper.fiber.core.viz.target_inference import prepare_target_inference


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


def test_formal_target_catalog_excludes_presma_and_uses_fixed_chart_order() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    config_path = (
        repository_root
        / "my_helper/stnsnr/config/four_model_v1/"
        "spatial_result_visualization.yaml"
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    fiber = config["fiber"]
    assert fiber["target_chart"]["order_policy"] == "configured_target_catalog"
    assert [target["name"] for target in fiber["targets"]] == [
        "GPe",
        "GPi",
        "caudate",
        "posterior_putamen",
        "VLP_thalamus",
        "VLA_thalamus",
        "RN",
        "VA_thalamus",
        "VM_thalamus",
        "PPN",
        "SMA",
        "M1",
        "sPf_thalamus",
        "premotor",
        "CM_thalamus",
        "DLPFC",
        "Pf_thalamus",
    ]
    assert [target["label"] for target in fiber["targets"]] == [
        "GPe",
        "GPi",
        "Caudate",
        "Posterior putamen",
        "VLP thalamus",
        "VLA thalamus",
        "RN",
        "VA thalamus",
        "VM thalamus",
        "PPN",
        "SMA",
        "M1",
        "sPf thalamus",
        "Premotor",
        "CM thalamus",
        "DLPFC",
        "Pf thalamus",
    ]


def _write_fiber_publication(
    tmp_path: Path,
    *,
    with_target_inference: bool = False,
) -> tuple[Path, Path]:
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
    inference_arrays: dict[str, np.ndarray] | None = None
    inference_weights = np.asarray([2.0, -1.0, 1.0, -0.5])
    if with_target_inference:
        outcome = np.asarray([7.0, 3.0, 6.0, 2.0, 5.0, 1.0])
        baseline = np.asarray([1.0, 4.0, 2.0, 6.0, 3.0, 5.0])
        exposure = np.asarray(
            [
                [1.0, 3.0, 6.0, 2.0],
                [2.0, 6.0, 1.0, 4.0],
                [3.0, 2.0, 5.0, 6.0],
                [4.0, 5.0, 2.0, 1.0],
                [5.0, 1.0, 4.0, 3.0],
                [6.0, 4.0, 3.0, 5.0],
            ]
        )
        ranked_outcome = rankdata(outcome, method="average")
        ranked_exposure = np.column_stack(
            [rankdata(exposure[:, index], method="average") for index in range(4)]
        )
        ranked_design = np.column_stack(
            [np.ones(outcome.size), rankdata(baseline, method="average")]
        )
        prepared = prepare_target_inference(
            ranked_outcome=ranked_outcome,
            ranked_exposure=ranked_exposure,
            ranked_nuisance_design=ranked_design,
            target_membership=np.ones((4, 1), dtype=np.bool_),
            benefit_direction="lower",
        )
        inference_weights = prepared.observed_fiber_weights
        inference_arrays = {
            "valid_fiber_exposure.npy": exposure,
            "ranked_valid_fiber_exposure.npy": ranked_exposure,
            "valid_fiber_ids.npy": np.asarray([1, 2, 3, 4], dtype=np.int64),
            "outcome.npy": outcome,
            "ranked_outcome.npy": ranked_outcome,
            "ranked_nuisance_design.npy": ranked_design,
        }
    for role in ("reference", "addon"):
        resolver_relative = (
            f"pdq39_score/{role}/connectomes/synthetic_connectome/resolver"
        )
        resolver = root / resolver_relative
        resolver.mkdir(parents=True)
        artifacts = {
            "valid_fiber_ids.npy": np.asarray([1, 2, 3, 4], dtype=np.int64),
            "full_weights.npy": inference_weights,
            "selected_sweet_fiber_ids.npy": np.asarray([1], dtype=np.int64),
            "selected_sour_fiber_ids.npy": np.asarray([2], dtype=np.int64),
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
        if inference_arrays is not None:
            inference_root = resolver / "target_inference"
            inference_root.mkdir()
            inference_hashes: dict[str, str] = {}
            for name, values in inference_arrays.items():
                path = inference_root / name
                np.save(path, values)
                inference_hashes[name] = _sha256(path)
                rows.append(
                    {
                        "relative_path": (
                            f"{resolver_relative}/target_inference/{name}"
                        ),
                        "sha256": inference_hashes[name],
                        "size_bytes": path.stat().st_size,
                        "status": "completed",
                        "artifact_kind": f"target_inference_{name}",
                    }
                )
            subject_order = inference_root / "subject_order.csv"
            exchangeability = inference_root / "exchangeability_blocks.csv"
            with subject_order.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("subject_index", "subject_id"),
                )
                writer.writeheader()
                writer.writerows(
                    {"subject_index": index, "subject_id": f"s{index + 1}"}
                    for index in range(6)
                )
            with exchangeability.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "subject_index",
                        "subject_id",
                        "exchangeability_block",
                    ),
                )
                writer.writeheader()
                writer.writerows(
                    {
                        "subject_index": index,
                        "subject_id": f"s{index + 1}",
                        "exchangeability_block": "all_subjects",
                    }
                    for index in range(6)
                )
            for path, kind in (
                (subject_order, "target_inference_subject_order"),
                (exchangeability, "target_inference_exchangeability_blocks"),
            ):
                inference_hashes[path.name] = _sha256(path)
                rows.append(
                    {
                        "relative_path": (
                            f"{resolver_relative}/target_inference/{path.name}"
                        ),
                        "sha256": inference_hashes[path.name],
                        "size_bytes": path.stat().st_size,
                        "status": "completed",
                        "artifact_kind": kind,
                    }
                )
            inference_input = inference_root / "inference_input.json"
            inference_input.write_text(
                json.dumps(
                    {
                        "schema_version": (
                            "conditional_signed_target_inference_input_v1"
                        ),
                        "scale_id": "pdq39_score",
                        "model_role": role,
                        "benefit_direction": "lower",
                        "artifact_sha256": inference_hashes,
                    }
                ),
                encoding="utf-8",
            )
            rows.append(
                {
                    "relative_path": (
                        f"{resolver_relative}/target_inference/inference_input.json"
                    ),
                    "sha256": _sha256(inference_input),
                    "size_bytes": inference_input.stat().st_size,
                    "status": "completed",
                    "artifact_kind": "target_inference_input_manifest",
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
    manifest["study_base_path"] = "/original-machine/publication/study_base.json"
    manifest["study_base_sha256"] = _sha256(study_base_path)
    resolved_profile_path = root / "resolved_normative_fiber_model.yaml"
    resolved_profile_path.write_text(
        yaml.safe_dump(
            {
                "formal_resampling": {
                    "seed": 42,
                    "permutation_resamples": 8,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    rows.append(
        {
            "relative_path": "resolved_normative_fiber_model.yaml",
            "sha256": _sha256(resolved_profile_path),
            "size_bytes": resolved_profile_path.stat().st_size,
            "status": "completed",
            "artifact_kind": "resolved_model_profile",
        }
    )
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


def test_selected_target_scores_and_all_connectome_composition_are_separate(
    tmp_path: Path,
) -> None:
    _, connectome_path = _write_fiber_publication(tmp_path)
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
    physical = build_whole_connectome_composition(
        connectome=open_connectome(connectome_path),
        seeds={"reference": seed, "addon": seed},
        targets=targets,
        fiber_chunk_size=2,
    )
    selected_ids = np.asarray([1, 2], dtype=np.int64)
    selected_scores = np.asarray([2.0, -1.0])
    membership = target_membership_from_bits(
        physical.fiber_target_bits,
        selected_ids,
        len(targets),
    )
    np.testing.assert_array_equal(
        membership,
        np.asarray(
            [
                [True, True, False],
                [False, True, False],
            ]
        ),
    )
    target_scores = compute_selected_target_scores(
        selected_scores=selected_scores,
        target_membership=membership,
    )
    np.testing.assert_allclose(target_scores[:2], [2.0, 0.5])
    assert np.isnan(target_scores[2])
    coverage_ids = np.asarray([1, 2, 3, 4], dtype=np.int64)
    coverage_scores = np.asarray([2.0, -1.0, 1.0, -0.5])
    coverage_membership = target_membership_from_bits(
        physical.fiber_target_bits,
        coverage_ids,
        len(targets),
    )
    coverage_target_scores = compute_target_scores(
        fiber_scores=coverage_scores,
        target_membership=coverage_membership,
    )
    np.testing.assert_allclose(coverage_target_scores[:2], [0.75, 0.5])
    assert np.isnan(coverage_target_scores[2])
    result = apply_target_scores_to_composition(
        composition=physical.for_role("reference"),
        target_scores=target_scores,
    )
    voxel_zero = int(np.ravel_multi_index((0, 0, 0), seed.shape, order="C"))
    position = int(np.searchsorted(result.seed_voxel_indices, voxel_zero))
    assert result.all_streamline_support_count[position] == 3.0
    assert result.target_scored_streamline_count[position] == 3.0
    assert result.target_unscored_streamline_count[position] == 0.0
    assert result.target_conditioned_score[position] == 1.25
    assert physical.n_all_fibers == 4

    missing_target = apply_target_scores_to_composition(
        composition=physical.for_role("reference"),
        target_scores=np.asarray([2.0, np.nan, np.nan]),
    )
    assert missing_target.all_streamline_support_count[position] == 3.0
    assert missing_target.target_scored_streamline_count[position] == 2.0
    assert missing_target.target_unscored_streamline_count[position] == 1.0
    assert missing_target.target_conditioned_score[position] == 2.0

    one_fiber_chunks = build_whole_connectome_composition(
        connectome=open_connectome(connectome_path),
        seeds={"reference": seed, "addon": seed},
        targets=targets,
        fiber_chunk_size=1,
    )
    np.testing.assert_array_equal(
        one_fiber_chunks.fiber_target_bits,
        physical.fiber_target_bits,
    )
    for role in ("reference", "addon"):
        expected = physical.for_role(role)
        observed = one_fiber_chunks.for_role(role)
        np.testing.assert_array_equal(
            observed.seed_voxel_indices, expected.seed_voxel_indices
        )
        np.testing.assert_array_equal(
            observed.voxel_pattern_indptr, expected.voxel_pattern_indptr
        )
        np.testing.assert_array_equal(observed.pattern_bits, expected.pattern_bits)
        np.testing.assert_array_equal(observed.pattern_counts, expected.pattern_counts)


def test_projection_retains_selected_fiber_outside_seed(tmp_path: Path) -> None:
    seed = load_binary_projection_mask(
        _write_mask(tmp_path / "seed.nii.gz", [(0, 0, 0)]),
        roi_id="seed",
        role="seed",
    )
    result = compute_selected_direct_projection(
        fiber_ids=[1],
        scores=[1.0],
        is_sweet=[True],
        streamlines=[np.asarray([[3.0, 3.0, 3.0], [4.0, 4.0, 4.0]])],
        seed=seed,
    )

    np.testing.assert_array_equal(result.fiber_ids, [1])
    np.testing.assert_array_equal(result.seed_hits, [False])
    assert result.direct_support_count.sum() > 0


def test_scale_display_name_comes_from_study_definition(tmp_path: Path) -> None:
    publication, _ = _write_fiber_publication(tmp_path)
    manifest = json.loads(
        (publication / "model_manifest.json").read_text(encoding="utf-8")
    )
    catalog = PublicationCatalog.from_config(
        {"main": {"root": str(publication)}},
        config_base=tmp_path,
    )
    display_name, record = catalog.resolve_scale_display_name(
        "main", "pdq39_score"
    )

    assert display_name == "PDQ39 score"
    assert record["kind"] == "study_base"
    assert record["label_source"] == "study.scale_definitions[].label"
    assert record["scale_definition_count"] == 1
    assert record["resolved_scale_id"] == "pdq39_score"
    assert record["resolved_scale_display_name"] == "PDQ39 score"
    assert record["sha256"] == manifest["study_base_sha256"]


@pytest.mark.parametrize("with_target_inference", [False, True])
def test_single_scale_fiber_postprocess_writes_and_reuses_two_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_target_inference: bool,
) -> None:
    publication, _ = _write_fiber_publication(
        tmp_path,
        with_target_inference=with_target_inference,
    )
    resources = tmp_path / "resources"
    resources.mkdir()
    seed = _write_mask(
        resources / "seed.nii.gz",
        [(0, 0, 0), (1, 0, 0), (1, 0, 1)],
    )
    outline = _write_mask(
        resources / "outline.nii.gz",
        [(0, 0, 0), (1, 0, 0), (1, 0, 1)],
    )
    target_a = _write_mask(resources / "target_a.nii.gz", [(2, 0, 0)])
    target_b = _write_mask(resources / "target_b.nii.gz", [(2, 1, 0)])
    anatomy_data = np.arange(125, dtype=np.float32).reshape((5, 5, 5))
    anatomy = resources / "anatomy.nii"
    nib.save(nib.Nifti1Image(anatomy_data, np.eye(4)), anatomy)
    config = {
        "background": {
            "path": str(anatomy),
            "loading": "panel_local_lazy",
        },
        "display_map": {
            "fwhm_mm": 1.0,
            "voxel_size_mm": 0.1,
            "support_weight_threshold": 0.5,
        },
        "outline": {"continuous_isovalue": 0.05},
        "voxel": {
            "masks": {"reference": str(seed), "addon": str(seed)},
            "labels": {
                "colorbar_template": (
                    "Benefit-oriented partial Spearman ρ with "
                    "{scale_display_name}"
                )
            },
        },
        "fiber": {
            "projection": {
            "grid_source": "role_seed",
            "direct_streamline_scope": "selected_sweet_sour_complete_path",
            "primary_target_score_fiber_scope": (
                "final_resolver_valid_fiber_axis"
            ),
            "sensitivity_target_score_fiber_scope": "selected_sweet_sour",
            "voxel_composition_fiber_scope": "formal_connectome_all",
            "target_conditioned_scope": "seed_only",
            "per_fiber_per_voxel": "once",
            "target_hit_method": "segment_intersection",
            "target_membership": "independent_binary",
            "streamline_target_score": "equal_mean_over_finite_target_scores",
            "target_composition": "seed_voxel_target_pattern_counts",
            "streamline_weight_source": "uniform_one",
            "missing_target_score_policy": "exclude_target_then_renormalize_per_streamline",
            "no_scored_target_policy": "exclude_and_report",
        },
            "cache": {
            "physical_cache_kind": "whole_connectome_seed_voxel_target_patterns",
            "fiber_chunk_size": 2,
        },
            "labels": {
            "direct_streamline_colorbar_template": (
                "Mean selected-fiber partial Spearman ρ with "
                "{scale_display_name}"
            ),
            "target_conditioned_colorbar_template": (
                "Target-derived fiber partial Spearman ρ with "
                "{scale_display_name}"
            ),
        },
            "target_chart": {"order_policy": "configured_target_catalog"},
            "seeds": {
            "reference": {
                "side": "rh",
                "path": str(seed),
                "outline_path": str(outline),
            },
            "addon": {
                "side": "rh",
                "path": str(seed),
                "outline_path": str(outline),
            },
        },
            "targets": [
            {
                "name": "target_a",
                "label": "Target A",
                "side": "rh",
                "path": str(target_a),
            },
            {
                "name": "target_b",
                "label": "Target B",
                "side": "rh",
                "path": str(target_b),
            },
            ],
        },
    }
    config_path = tmp_path / "spatial_result_visualization.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    output = tmp_path / "postprocess"
    arguments = {
        "scale_id": "pdq39_score",
        "output_root": output,
        "normative_fiber_publication_root": publication,
        "spatial_config_path": config_path,
        "shared_cache_root": tmp_path / "shared_cache",
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
    assert first["physical_cache"]["cache_status"] == "computed"
    assert (output / "README.md").read_text(encoding="utf-8").startswith(
        "# PDQ39 score Normative-Fiber Spatial Postprocess"
    )
    scatter_min, scatter_max = first["target_score_chart"][
        "shared_scatter_bounds"
    ]
    scatter_span = scatter_max - scatter_min
    assert first["target_score_chart"]["shared_y_limits"] == pytest.approx(
        (
            scatter_min - 0.10 * scatter_span,
            scatter_max + 0.15 * scatter_span,
        )
    )
    assert first["target_score_chart"]["axis_lower_padding_fraction"] == 0.10
    assert first["target_score_chart"]["axis_upper_padding_fraction"] == 0.15
    for role in ("reference", "addon"):
        leaf = output / "scales" / "pdq39_score" / role / "fiber"
        assert (leaf / "completion/fiber_2d/complete.json").is_file()
        for family in (
            Path("direct_streamline"),
            Path("target_conditioned/all_coverage"),
            Path("target_conditioned/selected_sweet_sour"),
        ):
            display_path = leaf / family / "maps/display.nii.gz"
            assert display_path.is_file()
            assert np.allclose(
                nib.load(display_path).header.get_zooms()[:3],
                (0.1, 0.1, 0.1),
            )
            assert (leaf / family / "figures/display.png").is_file()
            assert (leaf / family / "figures/result.json").is_file()
        for branch, scope in (
            ("all_coverage", "final_resolver_valid_fiber_axis"),
            ("selected_sweet_sour", "selected_sweet_sour"),
        ):
            branch_root = leaf / "target_conditioned" / branch
            assert not (branch_root / "maps/all_streamline_support_count.nii.gz").exists()
            assert not (
                branch_root / "maps/target_scored_streamline_count.nii.gz"
            ).exists()
            assert (branch_root / "tables/target_scores.csv").is_file()
            target_qc = json.loads(
                (branch_root / "target_score_qc.json").read_text(encoding="utf-8")
            )
            assert target_qc["target_score_fiber_scope"] == scope
            composition_qc = json.loads(
                (branch_root / "voxel_composition_qc.json").read_text(
                    encoding="utf-8"
                )
            )
            assert composition_qc["support_conservation_max_abs_error"] < 1e-12
            assert composition_qc["target_score_fiber_scope"] == scope
            assert composition_qc["voxel_composition_fiber_scope"] == (
                "formal_connectome_all"
            )
            assert composition_qc["n_all_fibers"] == 4
        with (
            leaf
            / "target_conditioned/all_coverage/tables/target_scores.csv"
        ).open(encoding="utf-8", newline="") as handle:
            coverage_rows = {
                row["target_id"]: row for row in csv.DictReader(handle)
            }
        with (
            leaf
            / "target_conditioned/selected_sweet_sour/tables/target_scores.csv"
        ).open(encoding="utf-8", newline="") as handle:
            selected_rows = {
                row["target_id"]: row for row in csv.DictReader(handle)
            }
        published_weights = np.load(
            publication
            / "pdq39_score"
            / role
            / "connectomes/synthetic_connectome/resolver/full_weights.npy",
            allow_pickle=False,
        )
        expected_coverage_a = float(np.mean(published_weights[[0, 3]]))
        expected_selected_a = float(published_weights[0])
        assert float(coverage_rows["target_a"]["target_score"]) == pytest.approx(
            expected_coverage_a
        )
        assert int(coverage_rows["target_a"]["fiber_count"]) == 2
        assert float(selected_rows["target_a"]["target_score"]) == pytest.approx(
            expected_selected_a
        )
        assert int(selected_rows["target_a"]["fiber_count"]) == 1
        coverage_map = np.asarray(
            nib.load(
                leaf
                / "target_conditioned/all_coverage/maps/display.nii.gz"
            ).dataobj,
            dtype=np.float32,
        )
        selected_map = np.asarray(
            nib.load(
                leaf
                / "target_conditioned/selected_sweet_sour/maps/"
                "display.nii.gz"
            ).dataobj,
            dtype=np.float32,
        )
        common_finite = np.isfinite(coverage_map) & np.isfinite(selected_map)
        assert np.any(common_finite)
        assert not np.allclose(
            coverage_map[common_finite], selected_map[common_finite]
        )
        assert (
            leaf / "target_conditioned/tables/target_fiber_distributions.csv"
        ).is_file()
        assert (
            leaf / "direct_streamline/figures/display.png"
        ).is_file()
        assert (
            leaf
            / "target_conditioned/all_coverage/figures/"
            "display.png"
        ).is_file()
        target_chart_path = (
            leaf
            / "target_conditioned/figures/target_score_dual_raincloud.png"
        )
        assert target_chart_path.is_file()
        figure_json = json.loads(
            (
                leaf
                / "target_conditioned/all_coverage/figures/"
                "result.json"
            ).read_text(encoding="utf-8")
        )
        assert figure_json["analysis_role"] == "primary"
        assert figure_json["target_score_fiber_scope"] == (
            "final_resolver_valid_fiber_axis"
        )
        assert figure_json["render_metadata"]["slice_support_source"] == (
            "positive_geometry_image"
        )
        assert figure_json["render_metadata"]["mask_sampling_representation"] == (
            "continuous_atlas"
        )
        assert figure_json["render_metadata"]["mask_contour_level"] == 0.05
        assert figure_json["outline"]["path"] == str(outline.resolve())
        assert figure_json["seed"]["path"] == str(seed.resolve())
        assert figure_json["render_metadata"]["background_loading_mode"] == (
            "panel_local_lazy"
        )
        assert figure_json["display_transform"]["fwhm_mm"] == 1.0
        assert figure_json["display_transform"]["support_weight_threshold"] == 0.5
        assert figure_json["scale_display_name"] == "PDQ39 score"
        assert figure_json["colorbar_semantic_label"] == (
            "Target-derived fiber partial Spearman ρ with PDQ39 score"
        )
        assert figure_json["style"]["colorbar_label"] == (
            "Target-derived fiber partial Spearman ρ\nwith PDQ39 score"
        )
        direct_figure_json = json.loads(
            (
                leaf
                / "direct_streamline/figures/result.json"
            ).read_text(encoding="utf-8")
        )
        assert direct_figure_json["colorbar_semantic_label"] == (
            "Mean selected-fiber partial Spearman ρ with PDQ39 score"
        )
        assert direct_figure_json["style"]["colorbar_label"] == (
            "Mean selected-fiber partial Spearman ρ\nwith PDQ39 score"
        )
        result_json = json.loads((leaf / "result.json").read_text(encoding="utf-8"))
        assert result_json["figure_count"] == 4
        assert set(result_json["finite_target_score_count"]) == {
            "all_coverage",
            "selected_sweet_sour",
        }
        assert len(
            [
                value
                for value in result_json["outputs"]
                if value.endswith(".png")
            ]
        ) == 4
        target_chart_json = json.loads(
            (
                leaf
                / "target_conditioned/figures/target_score_dual_raincloud.json"
            ).read_text(encoding="utf-8")
        )
        assert target_chart_json["render_metadata"]["boxsize_mm"] == [16.0, 25.0]
        assert target_chart_json["render_metadata"]["target_order"] == [
            "target_a",
            "target_b",
        ]
        assert target_chart_json["render_metadata"]["target_display_labels"] == [
            "Target A",
            "Target B",
        ]
        assert target_chart_json["render_metadata"]["target_order_policy"] == (
            "configured_target_catalog"
        )
        assert target_chart_json["render_metadata"]["jitter_is_descriptive_only"]
        assert target_chart_json["style"]["negative_color"] == "#0E6AAF"
        assert target_chart_json["style"]["coverage_color"] == "#CCCCCC"
        assert target_chart_json["render_metadata"][
            "all_coverage_distribution_includes_selected"
        ] is True
        assert target_chart_json["render_metadata"]["shared_y_limits"] == (
            first["target_score_chart"]["shared_y_limits"]
        )
        if with_target_inference:
            inference_root = leaf / "target_conditioned/inference"
            inference_manifest = json.loads(
                (
                    inference_root / "target_group_permutation_manifest.json"
                ).read_text(encoding="utf-8")
            )
            assert inference_manifest["status"] == "complete"
            assert inference_manifest["requested_replicates"] == 8
            assert inference_manifest["multiplicity_primary"] == (
                "holm_strong_fwer"
            )
            assert inference_manifest["observed_parity"][
                "fiber_weight_max_abs_difference"
            ] < 1e-12
            assert inference_manifest["observed_parity"][
                "target_statistic_max_abs_difference"
            ] < 1e-12
            assert (
                inference_root / "input/valid_fiber_target_membership.npz"
            ).is_file()
            assert target_chart_json["plotted_p_value"] == (
                "p_net_targetwise_significance_stars"
            )
            assert target_chart_json["render_metadata"][
                "formal_inference_annotation"
            ] == "p_net_targetwise_significance_stars"
            assert target_chart_json["render_metadata"]["annotation_strip_mm"] == 0.0
            assert set(
                target_chart_json["render_metadata"][
                    "targetwise_significance_star_by_target"
                ].values()
            ) == {None}
        else:
            assert result_json["target_inference"]["status"] == (
                "not_available_parent_publication_missing_basis"
            )
            assert target_chart_json["plotted_p_value"] is None
            assert target_chart_json["render_metadata"][
                "formal_inference_annotation"
            ] is None

    second = run_single_scale_fiber_section_postprocess(**arguments)
    assert second["status"] == "complete"
    assert second["failed_count"] == 0
    assert second["reused_count"] == 2
    assert second["physical_cache"]["cache_status"] == "reused"

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

    monkeypatch.setattr(
        fiber_section_postprocess,
        "_resolve_role_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed fiber component reopened its sources")
        ),
    )
    component_second = render_fiber_section_components(
        scale_ids=("pdq39_score",),
        output_root=formal_output,
        catalog=catalog,
        context=context,
        style_overrides=arguments["style_overrides"],
    )
    assert all(item.get("resume_status") == "reused" for item in component_second)
