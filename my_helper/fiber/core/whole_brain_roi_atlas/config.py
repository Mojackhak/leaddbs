"""Strict YAML configuration for whole-brain ROI atlas builds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import yaml

from .errors import ConfigurationError
from .models import AtlasBuildConfig, LabelCategories


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


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _resolve_path(value: str, config_path: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def load_atlas_config(path: Path | str) -> AtlasBuildConfig:
    """Load and strictly validate one atlas build YAML file."""

    source = Path(path).expanduser().resolve()
    try:
        document = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read configuration {source}: {exc}") from exc
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

    inputs = dict(materialized["inputs"])
    output = dict(materialized["output"])
    labels = dict(materialized["labels"])
    expected = dict(materialized["expected"])
    execution = dict(materialized.get("execution", {}))
    resolved = {
        "schema_version": 1,
        "inputs": {
            key: str(_resolve_path(str(inputs[key]), source))
            for key in ("source_labeling", "source_labels", "reference_image", "connectome")
        },
        "output": {"atlas_root": str(_resolve_path(str(output["atlas_root"]), source))},
        "labels": {
            key: sorted(int(item) for item in labels[key])
            for key in (
                "cortical_limbic",
                "cerebellar_hemisphere",
                "cerebellar_midline",
                "subcortical",
                "white_matter",
            )
        },
        "expected": {
            "label_count": int(expected["label_count"]),
            "fiber_count": int(expected["fiber_count"]),
        },
        "execution": {"fiber_chunk_size": int(execution.get("fiber_chunk_size", 100_000))},
    }
    categories = LabelCategories(**{key: tuple(value) for key, value in resolved["labels"].items()})
    all_ids = categories.all_ids
    if len(all_ids) != len(set(all_ids)):
        raise ConfigurationError("label categories must be disjoint")
    if len(all_ids) != resolved["expected"]["label_count"]:
        raise ConfigurationError("configured label categories do not match expected label count")
    for key, value in resolved["inputs"].items():
        if not Path(value).is_file():
            raise ConfigurationError(f"input file does not exist: {key}={value}")
    if resolved["execution"]["fiber_chunk_size"] <= 0:
        raise ConfigurationError("fiber_chunk_size must be positive")
    return AtlasBuildConfig(
        schema_version=1,
        source_labeling=Path(resolved["inputs"]["source_labeling"]),
        source_labels=Path(resolved["inputs"]["source_labels"]),
        reference_image=Path(resolved["inputs"]["reference_image"]),
        connectome=Path(resolved["inputs"]["connectome"]),
        atlas_root=Path(resolved["output"]["atlas_root"]),
        categories=categories,
        expected_label_count=resolved["expected"]["label_count"],
        expected_fiber_count=resolved["expected"]["fiber_count"],
        fiber_chunk_size=resolved["execution"]["fiber_chunk_size"],
        resolved_mapping=_freeze(resolved),
        configuration_hash=_canonical_hash(resolved),
    )
