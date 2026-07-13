"""Strict loader for the public VTA model profile."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .errors import ConfigError


_SCHEMA_PATH = Path(__file__).with_name("schemas") / "vta_model.schema.json"


@dataclass(frozen=True)
class VtaModelConfig:
    """Validated public VTA model settings."""

    gray_matter_s_per_m: float
    white_matter_s_per_m: float
    atlas_set: str
    spaces: tuple[str, ...]
    primary_threshold_v_per_mm: float
    sensitivity_thresholds_v_per_mm: tuple[float, ...]

    @property
    def thresholds_v_per_m(self) -> tuple[float, ...]:
        values = (
            *self.sensitivity_thresholds_v_per_mm,
            self.primary_threshold_v_per_mm,
        )
        return tuple(sorted({value * 1000.0 for value in values}))


def load_vta_model(path: Path | str) -> VtaModelConfig:
    """Load and validate a `vta_model_v1` YAML profile."""

    profile_path = Path(path).expanduser().resolve()
    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to read VTA model profile: {profile_path}") from exc

    try:
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Unable to read VTA model schema: {_SCHEMA_PATH}") from exc
    except jsonschema.ValidationError as exc:
        raise ConfigError(exc.message) from exc

    values = _numeric_values(raw)
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise ConfigError("Conductivities and thresholds must be finite and positive")

    fem = raw["fem"]
    conductivity = fem["conductivity_s_per_m"]
    binary_vta = raw["outputs"]["binary_vta"]
    return VtaModelConfig(
        gray_matter_s_per_m=float(conductivity["gray_matter"]),
        white_matter_s_per_m=float(conductivity["white_matter"]),
        atlas_set=str(fem["atlas_set"]),
        spaces=tuple(str(space) for space in raw["outputs"]["spaces"]),
        primary_threshold_v_per_mm=float(
            binary_vta["primary_threshold_v_per_mm"]
        ),
        sensitivity_thresholds_v_per_mm=tuple(
            float(value)
            for value in binary_vta["sensitivity_thresholds_v_per_mm"]
        ),
    )


def _numeric_values(raw: dict[str, Any]) -> tuple[float, ...]:
    conductivity = raw["fem"]["conductivity_s_per_m"]
    binary_vta = raw["outputs"]["binary_vta"]
    return (
        float(conductivity["gray_matter"]),
        float(conductivity["white_matter"]),
        float(binary_vta["primary_threshold_v_per_mm"]),
        *(
            float(value)
            for value in binary_vta["sensitivity_thresholds_v_per_mm"]
        ),
    )
