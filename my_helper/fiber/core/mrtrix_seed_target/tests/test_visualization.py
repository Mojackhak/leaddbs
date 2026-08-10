"""Dynamic target-color and display-sampling tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ..config import resolve_config
from ..errors import ConfigurationError, ValidationError
from .. import visualization as visualization_module
from ..models import ToolIdentity
from ..visualization import (
    display_fingerprints,
    largest_remainder_quotas,
    midpoint_stratified_ordinals,
    render_display_scene,
    resolve_target_colors,
)
from .helpers import minimal_document, write_nifti


def _config_with_targets(tmp_path: Path, count: int, colormap: str = "hsv"):
    document = minimal_document(tmp_path)
    template = document["atlas"]["seeds"][0]["targets"][0]
    document["atlas"]["seeds"][0]["targets"] = [
        {
            **template,
            "id": f"Target{index:02d}",
            "path": str(tmp_path / "atlas" / "lh" / f"Target{index:02d}.nii.gz"),
        }
        for index in range(count)
    ]
    document["visualization"]["target_colormap"] = colormap
    return resolve_config(document, source_path=tmp_path / "config.yaml")


@pytest.mark.parametrize("count", [2, 7, 17, 23])
def test_colormap_sampling_returns_exact_dynamic_region_count(
    tmp_path: Path, count: int
) -> None:
    config = _config_with_targets(tmp_path, count)
    colors = resolve_target_colors(config, config.atlas.seeds[0])
    assert colors.shape == (count, 3)
    assert np.unique(colors, axis=0).shape[0] == count
    expected = np.arange(count) / count
    assert np.allclose(
        colors,
        __import__("matplotlib").colormaps["hsv"](expected)[:, :3],
    )


def test_unknown_colormap_and_malformed_seed_color_are_rejected(tmp_path: Path) -> None:
    document = minimal_document(tmp_path)
    document["visualization"]["target_colormap"] = "not-a-real-colormap"
    with pytest.raises(ConfigurationError, match="not registered"):
        resolve_config(document, source_path=tmp_path / "config.yaml")
    document = minimal_document(tmp_path)
    document["visualization"]["seed_wireframe_color"] = "gray"
    with pytest.raises(ConfigurationError, match="does not match"):
        resolve_config(document, source_path=tmp_path / "config.yaml")


def test_largest_remainder_uses_yaml_order_for_exact_ties() -> None:
    quotas, ideal = largest_remainder_quotas([1, 1, 1, 1], 3)
    assert ideal.tolist() == [0.75, 0.75, 0.75, 0.75]
    assert quotas.tolist() == [1, 1, 1, 0]


def test_largest_remainder_uses_all_available_when_below_budget() -> None:
    quotas, _ideal = largest_remainder_quotas([2, 1, 0], 3000)
    assert quotas.tolist() == [2, 1, 0]


@pytest.mark.parametrize(
    ("count", "quota", "expected"),
    [
        (10, 1, [5]),
        (10, 3, [1, 5, 8]),
        (5, 5, [0, 1, 2, 3, 4]),
        (0, 0, []),
    ],
)
def test_midpoint_stratified_selection_is_unique_and_deterministic(
    count: int, quota: int, expected: list[int]
) -> None:
    assert midpoint_stratified_ordinals(count, quota).tolist() == expected


def test_duplicate_sampled_colormap_rows_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_with_targets(tmp_path, 3)

    class ConstantMap:
        def __call__(self, values):
            return np.tile([0.2, 0.3, 0.4, 1.0], (len(values), 1))

    monkeypatch.setattr(visualization_module, "colormaps", {"hsv": ConstantMap()})
    with pytest.raises(ValidationError, match="distinct sampled colors"):
        resolve_target_colors(config, config.atlas.seeds[0])


def test_surface_mask_content_only_invalidates_style_fingerprint(
    tmp_path: Path,
) -> None:
    config = _config_with_targets(tmp_path, 3)
    seed = config.atlas.seeds[0]
    for index, roi in enumerate((seed, *seed.targets), start=1):
        data = np.zeros((3, 3, 3), dtype=np.uint8)
        data[index % 3, 1, 1] = 1
        write_nifti(roi.path, data)
    records = [
        {
            "semantic_key": f"{seed.key}/target/{target.key}",
            "sha256": f"source-{index}",
            "streamline_count": 100 + index,
        }
        for index, target in enumerate(seed.targets)
    ]
    before = display_fingerprints(
        config=config,
        seed=seed,
        target_records=records,
        code_hash="code",
    )
    changed = np.zeros((3, 3, 3), dtype=np.uint8)
    changed[2, 2, 2] = 1
    write_nifti(seed.targets[1].path, changed)
    after = display_fingerprints(
        config=config,
        seed=seed,
        target_records=records,
        code_hash="code",
    )
    assert after["sampling"] == before["sampling"]
    assert after["color"] == before["color"]
    assert after["style_camera"] != before["style_camera"]


def test_missing_scene_completion_is_a_cache_miss(tmp_path: Path) -> None:
    assert (
        visualization_module._verify_scene_complete(
            tmp_path / "complete.json",
            fingerprints={"sampling": "expected"},
        )
        is None
    )


def test_matlab_scene_render_disables_all_figure_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_root = tmp_path / "scene"
    scene_root.mkdir()
    commands: list[list[str]] = []

    def fake_run_command(command, *, log_path):
        resolved = [str(item) for item in command]
        commands.append(resolved)
        figure_dir = log_path.parent / "figures"
        figure_dir.mkdir()
        outputs = {
            "figure_path": figure_dir / "scene.fig",
            "png_path": figure_dir / "scene.png",
            "pdf_path": figure_dir / "scene.pdf",
        }
        for path in outputs.values():
            path.write_bytes(b"rendered")
        (log_path.parent / "scene_result.json").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "fiber_layer_count": 1,
                    "target_surface_count": 1,
                    "seed_wireframe_count": 1,
                    "control_count": 5,
                    **{key: str(path) for key, path in outputs.items()},
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(visualization_module, "run_command", fake_run_command)
    display = {
        "sampling_manifest_path": str(scene_root / "sampling_manifest.json"),
        "geometry_path": str(scene_root / "display_geometry.mat"),
        "fingerprints": {"sampling": "sampling", "color": "color"},
        "ordered_target_ids": ["Target01"],
        "subject_id": "sub-Test",
        "side": "lh",
        "seed_id": "Seed",
        "target_space": "MNI",
        "target_colormap_name": "hsv",
        "targets": [{"id": "Target01"}],
        "seed_wireframe_color": [0.5, 0.5, 0.5],
    }
    render_display_scene(
        display=display,
        matlab=ToolIdentity(
            name="matlab", executable=Path("/opt/matlab"), version="test"
        ),
        repo_root=Path(__file__).resolve().parents[5],
        code_hash="code",
    )

    assert commands == [
        [
            "/opt/matlab",
            "-noFigureWindows",
            "-nosplash",
            "-batch",
            commands[0][-1],
        ]
    ]


def test_matlab_scene_legend_renders_target_ids_literally() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "viz"
        / "mh_fiber_render_seed_target_space_scene.m"
    ).read_text(encoding="utf-8")
    assert "'Interpreter', 'none'" in source
