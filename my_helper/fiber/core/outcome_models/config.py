"""Strict YAML profile loading for configured outcome-model workflows."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator


class ConfigurationError(ValueError):
    """Raised when a public profile violates the configured workflow contract."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
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


@dataclass(frozen=True)
class WorkflowOverrides:
    scales: tuple[str, ...] = ()
    all_available: bool = False
    models: tuple[str, ...] = ()
    phases: tuple[str, ...] = ()
    connectomes: tuple[str, ...] = ()
    through: str | None = None
    resume: bool | None = None
    force: bool | None = None


@dataclass(frozen=True)
class PathProfile:
    clinical_table: Path
    stimulation_table: Path
    leaddbs_derivatives: Path
    asset_root: Path
    output_root: Path


@dataclass(frozen=True)
class ClinicalColumns:
    subject_id: str
    scale: str
    protocol: str
    phase: str
    value: str
    baseline: str


@dataclass(frozen=True)
class ConditionSpec:
    protocol: str
    phase: str


@dataclass(frozen=True)
class ConnectomeSpec:
    connectome_id: str
    label: str
    path: Path
    fiber_identity_source: str


@dataclass(frozen=True)
class StudyProfile:
    study_id: str
    paths: PathProfile
    clinical_columns: ClinicalColumns
    space: Mapping[str, Any]
    components: Mapping[str, Any]
    conditions: Mapping[str, ConditionSpec]
    efield_resolvers: Mapping[str, str]
    connectomes: Mapping[str, ConnectomeSpec]


@dataclass(frozen=True)
class EndpointBinding:
    protocol: str
    phase: str


@dataclass(frozen=True)
class ScaleSpec:
    scale_id: str
    label: str
    direction: str
    minimum_subjects: int
    endpoint_bindings: Mapping[str, EndpointBinding]


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    direct_voxel: Mapping[str, Any]
    normative_fiber: Mapping[str, Any]
    resolver: Mapping[str, Any]
    formal: Mapping[str, Any]
    sensitivity: Mapping[str, Any]
    oss: Mapping[str, Any]
    reporting: Mapping[str, Any]

    @property
    def direct_candidate_threshold_v_per_m(self) -> float:
        return float(min(self.direct_voxel["tau_grid_v_per_m"]))


@dataclass(frozen=True)
class SelectionProfile:
    scales: tuple[str, ...]
    all_available: bool
    phases: tuple[str, ...]
    models: tuple[str, ...]
    connectomes: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionProfile:
    through: str
    resume: bool
    force: bool
    continue_on_endpoint_failure: bool


@dataclass(frozen=True)
class WorkflowProfile:
    selection: SelectionProfile
    execution: ExecutionProfile


@dataclass(frozen=True)
class ResolvedWorkflow:
    study: StudyProfile
    scales: tuple[ScaleSpec, ...]
    model: ModelProfile
    workflow: WorkflowProfile
    configuration_hash: str
    source_paths: tuple[Path, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} must contain a YAML object")
    return value


def _schema_path(profile_type: str) -> Path:
    return Path(__file__).resolve().parent / "schemas" / f"{profile_type}.schema.json"


def _validate(document: dict[str, Any], profile_type: str, path: Path) -> None:
    schema = json.loads(_schema_path(profile_type).read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ConfigurationError(f"{path}:{location}: {error.message}")


def _validate_selection(selection: Mapping[str, Any]) -> None:
    has_scales = "scales" in selection and bool(selection.get("scales"))
    has_all = selection.get("all_available") is True
    if has_scales and has_all:
        raise ConfigurationError("selection.scales and selection.all_available are mutually exclusive")
    if not has_scales and not has_all:
        raise ConfigurationError("selection requires exactly one of scales or all_available")


def _apply_overrides(workflow: dict[str, Any], overrides: WorkflowOverrides) -> dict[str, Any]:
    result = deepcopy(workflow)
    selection = result.setdefault("selection", {})
    execution = result.setdefault("execution", {})
    if overrides.scales and overrides.all_available:
        raise ConfigurationError("override scales and all_available are mutually exclusive")
    if overrides.scales:
        selection["scales"] = list(overrides.scales)
        selection.pop("all_available", None)
    elif overrides.all_available:
        selection["all_available"] = True
        selection.pop("scales", None)
    if overrides.models:
        selection["models"] = list(overrides.models)
    if overrides.phases:
        selection["phases"] = list(overrides.phases)
    if overrides.connectomes:
        selection["connectomes"] = list(overrides.connectomes)
    if overrides.through is not None:
        execution["through"] = overrides.through
    if overrides.resume is not None:
        execution["resume"] = overrides.resume
    if overrides.force is not None:
        execution["force"] = overrides.force
    return result


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _study_from(document: dict[str, Any]) -> StudyProfile:
    paths = document["paths"]
    columns = document["clinical_columns"]
    conditions = {
        key: ConditionSpec(protocol=value["protocol"], phase=value["phase"])
        for key, value in document["conditions"].items()
    }
    connectomes = {
        key: ConnectomeSpec(
            connectome_id=key,
            label=value["label"],
            path=Path(value["path"]).expanduser().resolve(),
            fiber_identity_source=value["fiber_identity_source"],
        )
        for key, value in document["connectomes"].items()
    }
    return StudyProfile(
        study_id=document["study_id"],
        paths=PathProfile(**{key: Path(value).expanduser().resolve() for key, value in paths.items()}),
        clinical_columns=ClinicalColumns(**columns),
        space=_freeze(document["space"]),
        components=_freeze(document["components"]),
        conditions=MappingProxyType(conditions),
        efield_resolvers=MappingProxyType(dict(document["efield_resolvers"])),
        connectomes=MappingProxyType(connectomes),
    )


def _scales_from(document: dict[str, Any]) -> tuple[ScaleSpec, ...]:
    output: list[ScaleSpec] = []
    seen: set[str] = set()
    for item in document["scales"]:
        scale_id = item["scale_id"]
        if scale_id in seen:
            raise ConfigurationError(f"duplicate scale_id {scale_id!r}")
        seen.add(scale_id)
        bindings = {
            key: EndpointBinding(protocol=value["protocol"], phase=value["phase"])
            for key, value in item["endpoint_bindings"].items()
        }
        output.append(
            ScaleSpec(
                scale_id=scale_id,
                label=item["label"],
                direction=item["direction"],
                minimum_subjects=int(item["minimum_subjects"]),
                endpoint_bindings=MappingProxyType(bindings),
            )
        )
    return tuple(output)


def _model_from(document: dict[str, Any]) -> ModelProfile:
    return ModelProfile(
        profile_id=document["profile_id"],
        direct_voxel=_freeze(document["direct_voxel"]),
        normative_fiber=_freeze(document["normative_fiber"]),
        resolver=_freeze(document["resolver"]),
        formal=_freeze(document["formal"]),
        sensitivity=_freeze(document["sensitivity"]),
        oss=_freeze(document["oss"]),
        reporting=_freeze(document["reporting"]),
    )


def _workflow_from(document: dict[str, Any]) -> WorkflowProfile:
    selection = document["selection"]
    execution = document["execution"]
    return WorkflowProfile(
        selection=SelectionProfile(
            scales=tuple(selection.get("scales", ())),
            all_available=bool(selection.get("all_available", False)),
            phases=tuple(selection["phases"]),
            models=tuple(selection["models"]),
            connectomes=tuple(selection["connectomes"]),
        ),
        execution=ExecutionProfile(
            through=execution["through"],
            resume=bool(execution["resume"]),
            force=bool(execution["force"]),
            continue_on_endpoint_failure=bool(execution["continue_on_endpoint_failure"]),
        ),
    )


def _configuration_hash(documents: Mapping[str, dict[str, Any]]) -> str:
    payload = json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_cross_profile_semantics(documents: Mapping[str, dict[str, Any]]) -> None:
    model = documents["model"]
    workflow = documents["workflow"]
    study = documents["study"]

    for family in ("direct_voxel", "normative_fiber"):
        settings = model[family]
        if settings["pre_specified_tau_v_per_m"] not in settings["tau_grid_v_per_m"]:
            raise ConfigurationError(
                f"{family}.pre_specified_tau_v_per_m must be present in {family}.tau_grid_v_per_m"
            )
        if settings["pre_specified_coverage"] not in settings["coverage_grid"]:
            raise ConfigurationError(
                f"{family}.pre_specified_coverage must be present in {family}.coverage_grid"
            )

    cheap_sensitivity = model["normative_fiber"]["cheap_observed_sensitivity"]
    normative_fiber = model["normative_fiber"]
    if cheap_sensitivity["high_tau_v_per_m"] not in normative_fiber["tau_grid_v_per_m"]:
        raise ConfigurationError(
            "normative_fiber.cheap_observed_sensitivity.high_tau_v_per_m must be present in "
            "normative_fiber.tau_grid_v_per_m"
        )
    if cheap_sensitivity["coverage"] not in normative_fiber["coverage_grid"]:
        raise ConfigurationError(
            "normative_fiber.cheap_observed_sensitivity.coverage must be present in "
            "normative_fiber.coverage_grid"
        )

    selected_models = tuple(workflow["selection"]["models"])
    if "all" in selected_models and len(selected_models) != 1:
        raise ConfigurationError("model selector 'all' cannot be combined with specific models")

    selected_connectomes = set(workflow["selection"]["connectomes"])
    study_connectomes = set(study["connectomes"])
    role_connectomes = set(model["normative_fiber"]["connectome_roles"])
    unknown = sorted(selected_connectomes - (study_connectomes & role_connectomes))
    if unknown:
        raise ConfigurationError(f"unknown selected connectome IDs: {unknown}")

    unconfigured_roles = sorted(role_connectomes - study_connectomes)
    if unconfigured_roles:
        raise ConfigurationError(f"model connectome roles missing from study profile: {unconfigured_roles}")


def load_resolved_workflow(
    workflow_path: Path,
    overrides: WorkflowOverrides = WorkflowOverrides(),
) -> ResolvedWorkflow:
    workflow_path = Path(workflow_path).expanduser().resolve()
    workflow_document = _apply_overrides(_read_yaml(workflow_path), overrides)
    _validate_selection(workflow_document.get("selection", {}))
    _validate(workflow_document, "workflow", workflow_path)

    source_paths = {
        name: (workflow_path.parent / workflow_document[f"{name}_profile"]).resolve()
        for name in ("study", "scale", "model")
    }
    documents = {
        "study": _read_yaml(source_paths["study"]),
        "scale": _read_yaml(source_paths["scale"]),
        "model": _read_yaml(source_paths["model"]),
        "workflow": workflow_document,
    }
    for name in ("study", "scale", "model"):
        _validate(documents[name], f"{name}_profile", source_paths[name])
    _validate_cross_profile_semantics(documents)

    scales = _scales_from(documents["scale"])
    scale_ids = {item.scale_id for item in scales}
    selected = set(workflow_document["selection"].get("scales", ()))
    unknown = sorted(selected - scale_ids)
    if unknown:
        raise ConfigurationError(f"unknown selected scale IDs: {unknown}")

    return ResolvedWorkflow(
        study=_study_from(documents["study"]),
        scales=scales,
        model=_model_from(documents["model"]),
        workflow=_workflow_from(workflow_document),
        configuration_hash=_configuration_hash(documents),
        source_paths=(workflow_path, source_paths["study"], source_paths["scale"], source_paths["model"]),
    )
