from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from my_helper.fiber.core.vta_pipeline.config import load_vta_model
from my_helper.fiber.core.vta_pipeline.errors import ConfigError


VALID_PROFILE = {
    "schema_version": "vta_model_v1",
    "profile_type": "vta_model",
    "fem": {
        "conductivity_s_per_m": {
            "gray_matter": 0.33,
            "white_matter": 0.14,
        },
        "atlas_set": "Custom_Ewert_Zhang_Middlebrooks",
    },
    "outputs": {
        "spaces": ["native", "MNI152NLin2009bAsym"],
        "binary_vta": {
            "primary_threshold_v_per_mm": 0.20,
            "sensitivity_thresholds_v_per_mm": [0.18, 0.22],
        },
    },
}


def write_profile(tmp_path: Path, profile: dict[str, object]) -> Path:
    path = tmp_path / "vta_model.yaml"
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return path


def test_load_vta_model_converts_thresholds_to_v_per_m(tmp_path: Path) -> None:
    config = load_vta_model(write_profile(tmp_path, VALID_PROFILE))

    assert config.atlas_set == "Custom_Ewert_Zhang_Middlebrooks"
    assert config.spaces == ("native", "MNI152NLin2009bAsym")
    assert config.thresholds_v_per_m == (180.0, 200.0, 220.0)


@pytest.mark.parametrize(
    "forbidden",
    ["backend_policy", "solve_unit", "remove_electrode", "smoke"],
)
def test_schema_rejects_internal_top_level_fields(
    tmp_path: Path,
    forbidden: str,
) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    profile[forbidden] = True

    with pytest.raises(ConfigError, match="Additional properties"):
        load_vta_model(write_profile(tmp_path, profile))


def test_schema_rejects_internal_nested_fields(tmp_path: Path) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    profile["fem"]["remove_electrode"] = True

    with pytest.raises(ConfigError, match="Additional properties"):
        load_vta_model(write_profile(tmp_path, profile))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fem", "conductivity_s_per_m", "gray_matter"), 0.0),
        (("fem", "conductivity_s_per_m", "white_matter"), -0.1),
        (("outputs", "binary_vta", "primary_threshold_v_per_mm"), 0.0),
    ],
)
def test_schema_rejects_nonpositive_numeric_values(
    tmp_path: Path,
    path: tuple[str, ...],
    value: float,
) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    cursor = profile
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value

    with pytest.raises(ConfigError):
        load_vta_model(write_profile(tmp_path, profile))


def test_schema_rejects_unapproved_atlas(tmp_path: Path) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    profile["fem"]["atlas_set"] = "Custom_Ewert_Zhang_Middlebrooks0.05"

    with pytest.raises(ConfigError):
        load_vta_model(write_profile(tmp_path, profile))


def test_schema_requires_exact_output_spaces(tmp_path: Path) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    profile["outputs"]["spaces"] = ["native"]

    with pytest.raises(ConfigError):
        load_vta_model(write_profile(tmp_path, profile))
