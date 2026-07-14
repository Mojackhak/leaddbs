"""Strict YAML parsing for seed-wide MRtrix target-coverage tractography."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import yaml

from .errors import ConfigurationError
from .models import (
    AtlasConfig,
    BatchConfig,
    ExecutionConfig,
    RoiSpec,
    SeedSpec,
    SubjectSpec,
    TrackingConfig,
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


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


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


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


def _validate_document(document: Any) -> dict[str, Any]:
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
    return materialized


def resolve_config(
    document: Any,
    *,
    source_path: Path | str,
) -> BatchConfig:
    """Validate and resolve one in-memory YAML document."""

    materialized = _validate_document(document)
    source = Path(source_path).expanduser().resolve()
    base_dir = source.parent
    atlas_document = dict(materialized["atlas"])

    seeds: list[SeedSpec] = []
    seed_keys: set[str] = set()
    for seed_document_value in atlas_document["seeds"]:
        seed_document = dict(seed_document_value)
        targets: list[RoiSpec] = []
        target_keys: set[str] = set()
        for target_document_value in seed_document["targets"]:
            target_document = dict(target_document_value)
            target = RoiSpec(
                roi_id=str(target_document["id"]),
                side=str(target_document["side"]),
                path=_resolve_path(str(target_document["path"]), base_dir),
            )
            if target.key in target_keys:
                raise ConfigurationError(
                    f"seed {seed_document['side']}/{seed_document['id']} has "
                    f"duplicate target {target.key}"
                )
            target_keys.add(target.key)
            targets.append(target)
        seed = SeedSpec(
            roi_id=str(seed_document["id"]),
            side=str(seed_document["side"]),
            path=_resolve_path(str(seed_document["path"]), base_dir),
            targets=tuple(targets),
        )
        if seed.key in seed_keys:
            raise ConfigurationError(f"duplicate seed {seed.key}")
        seed_keys.add(seed.key)
        seeds.append(seed)

    subjects: list[SubjectSpec] = []
    subject_ids: set[str] = set()
    subject_dirs: set[Path] = set()
    for subject_document_value in materialized["subjects"]:
        subject_document = dict(subject_document_value)
        subject_id = str(subject_document["id"])
        subject_dir = _resolve_path(str(subject_document["subject_dir"]), base_dir)
        overrides = {
            str(key): _resolve_path(str(value), base_dir)
            for key, value in dict(subject_document.get("paths", {})).items()
        }
        if subject_id in subject_ids:
            raise ConfigurationError(f"duplicate subject id {subject_id!r}")
        if subject_dir in subject_dirs:
            raise ConfigurationError(
                f"duplicate resolved subject directory {subject_dir}"
            )
        subject_ids.add(subject_id)
        subject_dirs.add(subject_dir)
        subjects.append(
            SubjectSpec(
                subject_id=subject_id,
                subject_dir=subject_dir,
                path_overrides=MappingProxyType(overrides),
            )
        )

    tracking_document = dict(materialized["tracking"])
    execution_document = dict(materialized["execution"])
    mrtrix_prefix_value = str(execution_document["mrtrix_path_prefix"])
    mrtrix_prefix = (
        _resolve_path(mrtrix_prefix_value, base_dir)
        if mrtrix_prefix_value
        else None
    )
    atlas_root = _resolve_path(str(atlas_document["root"]), base_dir)

    resolved: dict[str, Any] = {
        "schema_version": 1,
        "atlas": {
            "name": str(atlas_document["name"]),
            "space": str(atlas_document["space"]),
            "root": str(atlas_root),
            "seeds": [
                {
                    "id": seed.roi_id,
                    "side": seed.side,
                    "path": str(seed.path),
                    "targets": [
                        {
                            "id": target.roi_id,
                            "side": target.side,
                            "path": str(target.path),
                        }
                        for target in seed.targets
                    ],
                }
                for seed in seeds
            ],
        },
        "subjects": [
            {
                "id": subject.subject_id,
                "subject_dir": str(subject.subject_dir),
                **(
                    {
                        "paths": {
                            key: str(path)
                            for key, path in sorted(subject.path_overrides.items())
                        }
                    }
                    if subject.path_overrides
                    else {}
                ),
            }
            for subject in subjects
        ],
        "tracking": {
            key: tracking_document[key]
            for key in (
                "minimum_streamlines_per_target",
                "fod_cutoff",
                "min_length_mm",
                "max_length_mm",
                "random_seed",
            )
        },
        "execution": {
            **{
                key: execution_document[key]
                for key in (
                    "subject_workers",
                    "preparation_threads_per_subject",
                    "seedwide_workers_per_subject",
                    "mrtrix_threads_per_seedwide_job",
                    "cpu_budget",
                    "memory_budget_gb",
                    "memory_dispatch_fraction",
                    "preparation_memory_reservation_gb",
                    "seedwide_memory_reservation_gb",
                    "generation_chunk_streamlines",
                    "maximum_seedwide_streamlines",
                )
            },
            "matlab_executable": str(
                _resolve_path(str(execution_document["matlab_executable"]), base_dir)
            ),
            "mrtrix_path_prefix": str(mrtrix_prefix) if mrtrix_prefix else "",
        },
    }

    tracking = TrackingConfig(
        minimum_streamlines_per_target=int(
            tracking_document["minimum_streamlines_per_target"]
        ),
        fod_cutoff=float(tracking_document["fod_cutoff"]),
        min_length_mm=float(tracking_document["min_length_mm"]),
        max_length_mm=float(tracking_document["max_length_mm"]),
        random_seed=int(tracking_document["random_seed"]),
    )
    if tracking.min_length_mm > tracking.max_length_mm:
        raise ConfigurationError(
            "tracking.min_length_mm must not exceed tracking.max_length_mm"
        )

    execution = ExecutionConfig(
        subject_workers=int(execution_document["subject_workers"]),
        preparation_threads_per_subject=int(
            execution_document["preparation_threads_per_subject"]
        ),
        seedwide_workers_per_subject=int(
            execution_document["seedwide_workers_per_subject"]
        ),
        mrtrix_threads_per_seedwide_job=int(
            execution_document["mrtrix_threads_per_seedwide_job"]
        ),
        cpu_budget=int(execution_document["cpu_budget"]),
        memory_budget_gb=float(execution_document["memory_budget_gb"]),
        memory_dispatch_fraction=float(
            execution_document["memory_dispatch_fraction"]
        ),
        preparation_memory_reservation_gb=float(
            execution_document["preparation_memory_reservation_gb"]
        ),
        seedwide_memory_reservation_gb=float(
            execution_document["seedwide_memory_reservation_gb"]
        ),
        generation_chunk_streamlines=int(
            execution_document["generation_chunk_streamlines"]
        ),
        maximum_seedwide_streamlines=int(
            execution_document["maximum_seedwide_streamlines"]
        ),
        matlab_executable=_resolve_path(
            str(execution_document["matlab_executable"]), base_dir
        ),
        mrtrix_path_prefix=mrtrix_prefix,
    )
    if execution.generation_chunk_streamlines > execution.maximum_seedwide_streamlines:
        raise ConfigurationError(
            "execution.generation_chunk_streamlines must not exceed "
            "execution.maximum_seedwide_streamlines"
        )
    if execution.preparation_threads_per_subject > execution.cpu_budget:
        raise ConfigurationError(
            "one preparation task cannot fit within execution.cpu_budget"
        )
    if execution.mrtrix_threads_per_seedwide_job > execution.cpu_budget:
        raise ConfigurationError(
            "one seed-wide task cannot fit within execution.cpu_budget"
        )
    if (
        execution.preparation_memory_reservation_gb
        > execution.memory_dispatch_capacity_gb
    ):
        raise ConfigurationError(
            "one preparation reservation cannot fit within the memory dispatch capacity"
        )
    if (
        execution.seedwide_memory_reservation_gb
        > execution.memory_dispatch_capacity_gb
    ):
        raise ConfigurationError(
            "one seed-wide reservation cannot fit within the memory dispatch capacity"
        )

    return BatchConfig(
        schema_version=1,
        atlas=AtlasConfig(
            name=str(atlas_document["name"]),
            space=str(atlas_document["space"]),
            root=atlas_root,
            seeds=tuple(seeds),
        ),
        subjects=tuple(subjects),
        tracking=tracking,
        execution=execution,
        source_path=source,
        resolved_mapping=_freeze(resolved),
        configuration_hash=_canonical_hash(resolved),
    )


def load_config(path: Path | str) -> BatchConfig:
    """Load, strictly validate, and resolve one YAML configuration."""

    source = Path(path).expanduser().resolve()
    try:
        document = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read configuration {source}: {exc}") from exc
    return resolve_config(document, source_path=source)
