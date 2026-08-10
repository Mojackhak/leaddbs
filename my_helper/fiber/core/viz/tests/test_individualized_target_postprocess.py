from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from my_helper.fiber.core.viz.fiber_composition import SeedPatternCounts
from my_helper.fiber.core.viz.individualized_target_postprocess import (
    _load_role_projection,
    _render_target_stability,
    _streamline_scores,
    _write_role_projection,
)
from my_helper.fiber.core.viz.spatial_result_config import (
    load_spatial_result_config,
)


def test_spatial_config_declares_individualized_ppmi_projection() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    config = load_spatial_result_config(
        repository_root
        / "my_helper/stnsnr/config/four_model_v1/"
        "spatial_result_visualization.yaml"
    )

    fiber = config["fiber"]
    individualized = fiber["individualized_seed_target"]
    assert individualized["projection_connectome_id"] == "ppmi_85_ewert_2017"
    assert individualized["projection_connectome_path"].endswith("/data.mat")
    assert fiber["color_limits"] == {
        "center": 0.0,
        "scope": "scale_role",
        "symmetric": True,
    }
    assert len(fiber["targets"]) == 17
    assert "PreSMA" not in {target["name"] for target in fiber["targets"]}


def test_streamline_scores_average_only_finite_hit_targets() -> None:
    membership = sparse.csr_matrix(
        [
            [1, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 1],
            [0, 1, 0, 0],
        ],
        dtype=np.bool_,
    )

    scores, finite_hit_counts = _streamline_scores(
        membership,
        np.asarray([2.0, np.nan, -1.0, 3.0]),
    )

    np.testing.assert_allclose(scores[:3], [2.0, -1.0, 1.0])
    assert np.isnan(scores[3])
    np.testing.assert_array_equal(finite_hit_counts, [1, 1, 2, 0])


def test_role_projection_round_trip_writes_complete_last(tmp_path: Path) -> None:
    leaf = tmp_path / "reference"
    fiber_ids = np.asarray([2, 5], dtype=np.int64)
    projection = SeedPatternCounts(
        role="reference",
        seed_voxel_indices=np.asarray([1, 4], dtype=np.int64),
        voxel_pattern_indptr=np.asarray([0, 1, 2], dtype=np.int64),
        pattern_bits=np.asarray([1, 3], dtype=np.uint32),
        pattern_counts=np.asarray([2, 1], dtype=np.int64),
        fiber_ids=fiber_ids,
    )
    membership = sparse.csr_matrix(
        np.asarray(
            [
                [True] + [False] * 16,
                [True, True] + [False] * 15,
            ],
            dtype=np.bool_,
        )
    )
    seed = SimpleNamespace(
        source_path=tmp_path / "seed.nii.gz",
        shape=(2, 2, 2),
        affine=np.eye(4),
    )

    _write_role_projection(
        leaf,
        role="reference",
        connectome_id="ppmi_85_ewert_2017",
        target_ids=[f"target_{index}" for index in range(17)],
        target_labels=[f"Target {index}" for index in range(17)],
        seed=seed,
        projection=projection,
        membership=membership,
    )

    restored = _load_role_projection(leaf, "reference")
    np.testing.assert_array_equal(restored.fiber_ids, fiber_ids)
    np.testing.assert_array_equal(
        restored.target_membership.toarray(),
        membership.toarray(),
    )
    np.testing.assert_array_equal(
        restored.voxel_patterns.pattern_bits,
        projection.pattern_bits,
    )
    assert (leaf / "complete.json").is_file()
    assert json.loads((leaf / "complete.json").read_text()) == {
        "status": "complete"
    }
    metadata = json.loads((leaf / "metadata.json").read_text())
    assert "seed_path" not in metadata
    assert metadata["seed_shape"] == [2, 2, 2]


def test_target_stability_writes_png_pdf_and_reuses_component(
    tmp_path: Path,
) -> None:
    target_ids = tuple(f"target_{index}" for index in range(17))
    target_labels = tuple(f"Target {index}" for index in range(17))
    stability = [
        {
            "benefit_oriented_coefficient": str((index - 8) / 20.0),
            "fold_coefficient_percentile_2_5": str((index - 9) / 20.0),
            "fold_coefficient_percentile_97_5": str((index - 7) / 20.0),
            "fold_selection_frequency": "0.75",
            "full_coverage_subjects": "12",
            "nominal_p": "0.04",
            "fdr_q": "0.04" if index == 0 else "0.08",
        }
        for index in range(17)
    ]
    bootstrap = [
        {
            "coefficient_percentile_2_5": str((index - 10) / 20.0),
            "coefficient_percentile_97_5": str((index - 6) / 20.0),
            "positive_sign_frequency": "0.6",
        }
        for index in range(17)
    ]

    first = _render_target_stability(
        endpoint_root=tmp_path,
        scale_id="pdq39",
        scale_display_name="PDQ-39",
        role="reference",
        target_ids=target_ids,
        target_labels=target_labels,
        stability=stability,
        bootstrap=bootstrap,
        force=False,
    )
    figure = (
        tmp_path
        / "visualization/target_coefficient_stability/"
        "target_coefficient_stability.png"
    )
    first_mtime = figure.stat().st_mtime_ns
    second = _render_target_stability(
        endpoint_root=tmp_path,
        scale_id="pdq39",
        scale_display_name="PDQ-39",
        role="reference",
        target_ids=target_ids,
        target_labels=target_labels,
        stability=stability,
        bootstrap=bootstrap,
        force=False,
    )

    component = tmp_path / "visualization/target_coefficient_stability"
    assert first == second
    assert figure.stat().st_mtime_ns == first_mtime
    assert (component / "target_coefficient_stability.pdf").is_file()
    assert (component / "target_statistics.csv").is_file()
    assert (component / "result.json").is_file()
    assert (component / "complete.json").is_file()
    assert json.loads((component / "complete.json").read_text()) == {
        "status": "complete"
    }
    assert not list(component.glob("*.svg"))
