"""Strict parsing for the compact target-profile QC YAML."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import yaml

from .errors import ConfigurationError
from .models import QcConfig


PRESET_NAME = "robust_target_profile_v1"

PRESET: Mapping[str, Any] = MappingProxyType(
    {
        "profile": {
            "value": "hit_fraction",
            "normalize_target_sum": False,
            "transform": "empirical_logit",
            "pseudocount": 0.5,
        },
        "robust_scaling": {
            "method": "median_mad",
            "mad_scale_constant": 1.4826,
            "minimum_mad": 1.0e-8,
        },
        "similarity": {
            "reference": "leave_one_out_median",
            "metrics": ["spearman", "pearson", "cosine"],
            "primary_metric": "spearman",
        },
        "multivariate_distance": {
            "method": "pca_whitened_distance",
            "variance_explained_threshold": 0.85,
            "maximum_components": 5,
        },
        "laterality": {"method": "asymmetry_index", "epsilon": 1.0e-6},
        "outliers": {
            "mad_multiplier": 3.0,
            "target_robust_z_threshold": 3.5,
            "single_target_review_threshold": 5.0,
            "minimum_extreme_targets": 3,
            "minimum_independent_statistical_flags": 2,
            "roi_mad_multiplier": 4.0,
        },
        "technical_qc": {
            "accepted_seed_state_statuses": [
                "staged_complete",
                "coverage_failed",
            ],
            "coverage_failed_is_hard_failure": True,
            "zero_target_hits_is_hard_failure": True,
            "automatic_exclusion": False,
        },
    }
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigurationError(f"duplicate YAML key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / "config.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def resolve_config(document: Any, *, source_path: Path | str) -> QcConfig:
    """Validate and resolve one compact in-memory QC configuration."""

    if not isinstance(document, Mapping):
        raise ConfigurationError("configuration must contain a YAML object")
    materialized = dict(document)
    errors = sorted(
        Draft202012Validator(_schema()).iter_errors(materialized),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ConfigurationError(f"configuration:{location}: {error.message}")

    source = Path(source_path).expanduser().resolve()
    base = source.parent
    tracking_config = _resolve_path(
        str(materialized["inputs"]["tracking_config"]), base
    )
    output_root = _resolve_path(str(materialized["output"]["root"]), base)
    resolved: dict[str, Any] = {
        "schema_version": 1,
        "inputs": {"tracking_config": str(tracking_config)},
        "qc": {
            "preset": PRESET_NAME,
            "resolved_preset": json.loads(json.dumps(dict(PRESET))),
        },
        "output": {
            "root": str(output_root),
            "run_name": str(materialized["output"]["run_name"]),
        },
    }
    return QcConfig(
        schema_version=1,
        tracking_config=tracking_config,
        preset=PRESET_NAME,
        output_root=output_root,
        run_name=str(materialized["output"]["run_name"]),
        source_path=source,
        resolved_mapping=MappingProxyType(resolved),
        configuration_hash=_canonical_hash(resolved),
    )


def load_config(path: Path | str) -> QcConfig:
    """Load one compact QC YAML from disk."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ConfigurationError(f"QC configuration does not exist: {source}")
    try:
        document = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"cannot parse QC YAML {source}: {exc}") from exc
    return resolve_config(document, source_path=source)
