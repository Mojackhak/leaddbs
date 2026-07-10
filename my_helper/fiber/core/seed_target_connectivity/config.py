"""Strict YAML configuration loading for seed-target connectivity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from .errors import ConfigurationError
from .models import (
    ConnectivityConfig,
    ExecutionConfig,
    IntersectionConfig,
    RankingConfig,
    SeedConfig,
    TargetConfig,
)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigurationError(f"duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / "config.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def resolve_config(document: Any) -> ConnectivityConfig:
    """Validate and resolve one public configuration mapping."""
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

    seed_document = dict(materialized.get("seed", {}))
    target_document = dict(materialized.get("targets", {}))
    intersection_document = dict(materialized.get("intersection", {}))
    execution_document = dict(materialized.get("execution", {}))
    ranking_document = dict(materialized.get("ranking", {}))

    resolved: dict[str, Any] = {
        "schema_version": 1,
        "seed": {"probability_threshold": seed_document.get("probability_threshold")},
        "targets": {
            "probability_threshold": target_document.get("probability_threshold"),
            "roi_thresholds": dict(sorted(dict(target_document.get("roi_thresholds", {})).items())),
        },
        "intersection": {
            "method": intersection_document.get("method", "segment_aware_voxel_traversal")
        },
        "execution": {
            "fiber_chunk_size": execution_document.get("fiber_chunk_size", 100_000),
            "cache_membership": execution_document.get("cache_membership", True),
        },
        "ranking": {"enabled": ranking_document.get("enabled", True)},
    }
    return ConnectivityConfig(
        schema_version=1,
        seed=SeedConfig(probability_threshold=resolved["seed"]["probability_threshold"]),
        targets=TargetConfig(
            probability_threshold=resolved["targets"]["probability_threshold"],
            roi_thresholds=MappingProxyType(dict(resolved["targets"]["roi_thresholds"])),
        ),
        intersection=IntersectionConfig(method=str(resolved["intersection"]["method"])),
        execution=ExecutionConfig(
            fiber_chunk_size=int(resolved["execution"]["fiber_chunk_size"]),
            cache_membership=bool(resolved["execution"]["cache_membership"]),
        ),
        ranking=RankingConfig(enabled=bool(resolved["ranking"]["enabled"])),
        resolved_mapping=_freeze(resolved),
        configuration_hash=_canonical_hash(resolved),
    )


def load_config(path: Path | str) -> ConnectivityConfig:
    """Load, validate, and resolve one YAML configuration file."""
    source = Path(path)
    try:
        document = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read configuration {source}: {exc}") from exc
    return resolve_config(document)
