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
    BatchConnectivityConfig,
    EffectiveConnectivityConfig,
    ExecutionConfig,
    InputConfig,
    OutputConfig,
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


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def resolve_config(
    document: Any,
    *,
    base_dir: Path | str | None = None,
) -> BatchConnectivityConfig:
    """Validate and resolve one public batch configuration mapping."""
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

    root = Path(base_dir).expanduser().resolve() if base_dir is not None else Path.cwd().resolve()
    input_document = dict(materialized["inputs"])
    output_document = dict(materialized["output"])
    seed_document = dict(materialized.get("seed", {}))
    target_document = dict(materialized.get("targets", {}))
    execution_document = dict(materialized.get("execution", {}))
    ranking_document = dict(materialized.get("ranking", {}))

    seed_rois = {
        str(name): _resolve_path(str(value), root)
        for name, value in sorted(dict(input_document["seed_rois"]).items())
    }
    target_atlas_root = _resolve_path(str(input_document["target_atlas_root"]), root)
    connectome = _resolve_path(str(input_document["connectome"]), root)
    output_root = _resolve_path(str(output_document["output_root"]), root)
    cache_value = output_document.get("cache_root")
    cache_root = (
        _resolve_path(str(cache_value), root)
        if cache_value is not None
        else output_root.parent / ".cache"
    )

    resolved: dict[str, Any] = {
        "schema_version": 2,
        "inputs": {
            "target_atlas_root": str(target_atlas_root),
            "seed_rois": {name: str(path) for name, path in seed_rois.items()},
            "connectome": str(connectome),
        },
        "output": {
            "output_root": str(output_root),
            "run_name": str(output_document["run_name"]),
            "cache_root": str(cache_root),
        },
        "seed": {"probability_threshold": seed_document.get("probability_threshold")},
        "targets": {
            "probability_threshold": target_document.get("probability_threshold"),
            "roi_thresholds": dict(sorted(dict(target_document.get("roi_thresholds", {})).items())),
        },
        "execution": {
            "fiber_chunk_size": execution_document.get("fiber_chunk_size", 100_000),
            "cache_membership": execution_document.get("cache_membership", True),
        },
        "ranking": {"enabled": ranking_document.get("enabled", True)},
    }
    return BatchConnectivityConfig(
        schema_version=2,
        inputs=InputConfig(
            target_atlas_root=target_atlas_root,
            seed_rois=MappingProxyType(seed_rois),
            connectome=connectome,
        ),
        output=OutputConfig(
            output_root=output_root,
            run_name=str(output_document["run_name"]),
            cache_root=cache_root,
        ),
        seed=SeedConfig(probability_threshold=resolved["seed"]["probability_threshold"]),
        targets=TargetConfig(
            probability_threshold=resolved["targets"]["probability_threshold"],
            roi_thresholds=MappingProxyType(dict(resolved["targets"]["roi_thresholds"])),
        ),
        execution=ExecutionConfig(
            fiber_chunk_size=int(resolved["execution"]["fiber_chunk_size"]),
            cache_membership=bool(resolved["execution"]["cache_membership"]),
        ),
        ranking=RankingConfig(enabled=bool(resolved["ranking"]["enabled"])),
        resolved_mapping=_freeze(resolved),
        batch_configuration_hash=_canonical_hash(resolved),
    )


def effective_config(
    batch: BatchConnectivityConfig,
    seed_name: str,
) -> EffectiveConnectivityConfig:
    """Resolve the scientific configuration for one named seed."""

    if seed_name not in batch.inputs.seed_rois:
        raise ConfigurationError(f"configuration does not contain seed {seed_name!r}")
    effective = {
        "schema_version": 2,
        "inputs": {
            "target_atlas_root": str(batch.inputs.target_atlas_root),
            "seed_name": seed_name,
            "seed_roi": str(batch.inputs.seed_rois[seed_name]),
            "connectome": str(batch.inputs.connectome),
        },
        "seed": _thaw(batch.resolved_mapping["seed"]),
        "targets": _thaw(batch.resolved_mapping["targets"]),
        "execution": _thaw(batch.resolved_mapping["execution"]),
        "ranking": _thaw(batch.resolved_mapping["ranking"]),
    }
    return EffectiveConnectivityConfig(
        schema_version=2,
        seed_name=seed_name,
        seed_roi=batch.inputs.seed_rois[seed_name],
        seed=batch.seed,
        targets=batch.targets,
        execution=batch.execution,
        ranking=batch.ranking,
        resolved_mapping=_freeze(effective),
        batch_resolved_mapping=batch.resolved_mapping,
        batch_configuration_hash=batch.batch_configuration_hash,
        effective_configuration_hash=_canonical_hash(effective),
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def load_config(path: Path | str) -> BatchConnectivityConfig:
    """Load, validate, and resolve one YAML configuration file."""
    source = Path(path)
    try:
        document = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read configuration {source}: {exc}") from exc
    return resolve_config(document, base_dir=source.parent)
