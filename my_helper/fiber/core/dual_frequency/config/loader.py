"""Strict loader for direct-voxel, normative-fiber, and workflow YAML profiles."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from ..contracts.identity import canonical_hash
from ..contracts.study_base import StudyBaseRecord
from .models import (
    AdequateSupportProfile,
    ConnectomeProfile,
    DeltaReferenceSupportProfile,
    DirectVoxelModelProfile,
    EndpointBinding,
    EndpointPair,
    ExecutionProfile,
    FiberDiameterProfile,
    FiberScoreProfile,
    FiberSensitivityProfile,
    FixedOuterLibraryProfile,
    FormalResamplingProfile,
    FrequencyClasses,
    FrequencyInterval,
    HardComputabilityProfile,
    InvalidSupportProfile,
    NormativeFiberModelProfile,
    OssProfile,
    OutputProfile,
    ResolvedWorkflow,
    SourceCell,
    SourceResolverProfile,
    StorageProfile,
    WorkflowOverrides,
    WorkflowProfile,
    WorkflowSelection,
)


MODEL_FAMILIES = (
    "reference_voxel",
    "reference_fiber",
    "addon_voxel",
    "addon_fiber",
)
THROUGH_PHASES = frozenset({"observed", "formal", "sensitivity", "report"})


class ConfigurationError(ValueError):
    """Raised when a public profile violates the configured runtime contract."""


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
            raise ConfigurationError(f"duplicate YAML key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"failed to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{path} must contain a YAML object")
    _reject_nonfinite(payload, str(path))
    return payload


def _reject_nonfinite(value: object, location: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError(f"{location} contains a nonfinite numeric value")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{location}[{index}]")


def _schema_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "schemas" / f"{name}.schema.json"


def _validate_schema(payload: Mapping[str, Any], name: str, path: Path) -> None:
    schema = json.loads(_schema_path(name).read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ConfigurationError(f"{path}:{location}: {error.message}")


def _binding(payload: Mapping[str, Any]) -> EndpointBinding:
    return EndpointBinding(phase_id=str(payload["phase_id"]), program_id=int(payload["program_id"]))


def _endpoint_pair(payload: Mapping[str, Any]) -> EndpointPair:
    return EndpointPair(
        baseline=_binding(payload["baseline"]),
        reference=_binding(payload["reference"]),
        addon=_binding(payload["addon"]),
    )


def _interval(payload: Mapping[str, Any]) -> FrequencyInterval:
    return FrequencyInterval(
        lower=float(payload["lower"]) if payload["lower"] is not None else None,
        lower_inclusive=bool(payload["lower_inclusive"]),
        upper=float(payload["upper"]) if payload["upper"] is not None else None,
        upper_inclusive=bool(payload["upper_inclusive"]),
    )


def _frequency_classes(payload: Mapping[str, Any]) -> FrequencyClasses:
    return FrequencyClasses(
        reference=_interval(payload["reference"]),
        addon=_interval(payload["addon"]),
    )


def _source(payload: Mapping[str, Any]) -> SourceResolverProfile:
    pre = payload["pre_specified"]
    scan = payload["scan"]
    return SourceResolverProfile(
        pre_specified=SourceCell(
            tau=float(pre["tau_v_per_m"]),
            coverage=int(pre["coverage_subjects_min"]),
        ),
        tau_values=tuple(float(value) for value in scan["tau_v_per_m"]),
        coverage_values=tuple(int(value) for value in scan["coverage_subjects_min"]),
        minimum_adjacent_passing_cells=int(payload["minimum_adjacent_passing_cells"]),
    )


def _formal(payload: Mapping[str, Any]) -> FormalResamplingProfile:
    return FormalResamplingProfile(
        seed=int(payload["seed"]),
        permutation_resamples=int(payload["permutation_resamples"]),
        bootstrap_resamples=int(payload["bootstrap_resamples"]),
        jitter_resamples=int(payload["jitter_resamples"]),
        jitter_translation_fwhm_mm=float(payload["jitter_translation_fwhm_mm"]),
    )


def _delta_support(payload: Mapping[str, Any]) -> DeltaReferenceSupportProfile:
    adequate = payload["adequate"]
    invalid = payload["invalid"]
    return DeltaReferenceSupportProfile(
        adequate=AdequateSupportProfile(
            cohort_median_out_support_max=float(adequate["cohort_median_out_support_max"]),
            subject_out_support_threshold=float(adequate["subject_out_support_threshold"]),
            subject_fraction_max=float(adequate["subject_fraction_max"]),
        ),
        invalid=InvalidSupportProfile(
            cohort_median_out_support_min_exclusive=float(
                invalid["cohort_median_out_support_min_exclusive"]
            ),
            subject_out_support_threshold=float(invalid["subject_out_support_threshold"]),
            subject_fraction_min_exclusive=float(invalid["subject_fraction_min_exclusive"]),
            individual_out_support_min_exclusive=float(
                invalid["individual_out_support_min_exclusive"]
            ),
        ),
    )


def _direct_profile(payload: Mapping[str, Any]) -> DirectVoxelModelProfile:
    shared = payload["shared"]
    hard = shared["hard_computability"]
    return DirectVoxelModelProfile(
        schema_version=str(payload["schema_version"]),
        model_set_id=str(payload["model_set_id"]),
        output=OutputProfile(root=Path(payload["output"]["root"]).expanduser().resolve()),
        scales=tuple(str(value) for value in payload["scales"]),
        endpoint_pair=_endpoint_pair(payload["endpoint_pair"]),
        frequency_classes=_frequency_classes(payload["frequency_classes"]),
        source=_source(shared["source"]),
        hard_computability=HardComputabilityProfile(
            n_subjects_min=int(hard["n_subjects_min"]),
            n_features_full_min=int(hard["n_voxels_full_min"]),
            fold_n_features_min=int(hard["fold_n_voxels_min"]),
        ),
        formal_resampling=_formal(shared["formal_resampling"]),
        selected_source_tau_multipliers=tuple(
            float(value) for value in shared["selected_source_sensitivity"]["tau_multipliers"]
        ),
        delta_reference_support=_delta_support(payload["addon"]["delta_reference_support"]),
    )


def _fiber_profile(payload: Mapping[str, Any]) -> NormativeFiberModelProfile:
    hard = payload["hard_computability"]
    score = payload["score"]
    sensitivity = payload["sensitivity"]
    high = sensitivity["high_threshold"]
    fixed = sensitivity["fixed_outer_library"]
    oss = payload["oss"]
    diameter = oss["fiber_diameter_um"]
    return NormativeFiberModelProfile(
        schema_version=str(payload["schema_version"]),
        model_set_id=str(payload["model_set_id"]),
        output=OutputProfile(root=Path(payload["output"]["root"]).expanduser().resolve()),
        scales=tuple(str(value) for value in payload["scales"]),
        endpoint_pair=_endpoint_pair(payload["endpoint_pair"]),
        frequency_classes=_frequency_classes(payload["frequency_classes"]),
        connectomes=tuple(
            ConnectomeProfile(
                connectome_id=str(item["connectome_id"]),
                label=str(item["label"]),
                path=Path(item["path"]).expanduser().resolve(),
                role=str(item["role"]),
                fold_candidate_fibers_min=int(item["fold_candidate_fibers_min"]),
            )
            for item in payload["connectomes"]["entries"]
        ),
        source=_source(payload["source"]),
        hard_computability=HardComputabilityProfile(n_subjects_min=int(hard["n_subjects_min"])),
        score=FiberScoreProfile(
            sweet_fraction=float(score["sweet_fraction"]),
            sour_fraction=float(score["sour_fraction"]),
            weighted_peak_fraction=float(score["weighted_peak_fraction"]),
            sweet_selected_min_count=int(score["sweet_selected_min_count"]),
            sour_selected_min_count=int(score["sour_selected_min_count"]),
            weighted_peak_min_count=int(score["weighted_peak_min_count"]),
        ),
        formal_resampling=_formal(payload["formal_resampling"]),
        sensitivity=FiberSensitivityProfile(
            selected_source_tau_multipliers=tuple(
                float(value) for value in sensitivity["selected_source_tau_multipliers"]
            ),
            high_threshold=SourceCell(
                tau=float(high["tau_v_per_m"]),
                coverage=int(high["coverage_subjects_min"]),
            ),
            fixed_outer_library=FixedOuterLibraryProfile(
                sweet_count=int(fixed["sweet_count"]),
                sour_count=int(fixed["sour_count"]),
            ),
        ),
        oss=OssProfile(
            model=str(oss["model"]),
            activation_model=str(oss["activation_model"]),
            fiber_diameter_um=FiberDiameterProfile(
                minimum=float(diameter["minimum"]),
                maximum=float(diameter["maximum"]),
                samples=int(diameter["samples"]),
                sampling=str(diameter["sampling"]),
            ),
            fitting_probability_threshold=float(oss["fitting_probability_threshold"]),
            permutation_resamples=int(oss["permutation_resamples"]),
        ),
        delta_reference_support=_delta_support(payload["addon"]["delta_reference_support"]),
    )


def _validate_source(source: SourceResolverProfile, label: str) -> None:
    if tuple(sorted(set(source.tau_values))) != source.tau_values:
        raise ConfigurationError(f"{label} tau scan must be unique and increasing")
    if tuple(sorted(set(source.coverage_values))) != source.coverage_values:
        raise ConfigurationError(f"{label} Coverage scan must be unique and increasing")
    if source.pre_specified.tau not in source.tau_values:
        raise ConfigurationError(f"{label} pre-specified tau must be present in the scan")
    if source.pre_specified.coverage not in source.coverage_values:
        raise ConfigurationError(f"{label} pre-specified Coverage must be present in the scan")
    if source.minimum_adjacent_passing_cells > 8:
        raise ConfigurationError(f"{label} minimum adjacent support cannot exceed 8")


def _validate_frequency_classes(classes: FrequencyClasses) -> None:
    for label, interval in (("reference", classes.reference), ("addon", classes.addon)):
        for value in (interval.lower, interval.upper):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ConfigurationError(f"{label} frequency boundaries must be finite and nonnegative")
        if interval.lower is None and interval.lower_inclusive:
            raise ConfigurationError(f"{label} unbounded lower limit cannot be inclusive")
        if interval.upper is None and interval.upper_inclusive:
            raise ConfigurationError(f"{label} unbounded upper limit cannot be inclusive")
        if interval.lower is not None and interval.upper is not None:
            if interval.lower > interval.upper:
                raise ConfigurationError(f"{label} lower frequency boundary exceeds upper boundary")
            if interval.lower == interval.upper and not (
                interval.lower_inclusive and interval.upper_inclusive
            ):
                raise ConfigurationError(f"{label} frequency interval is empty")
    addon_upper = classes.addon.upper
    reference_lower = classes.reference.lower
    if addon_upper is None or reference_lower is None:
        raise ConfigurationError("addon upper and reference lower frequency boundaries must be finite")
    if addon_upper > reference_lower:
        raise ConfigurationError("addon upper frequency must be less than or equal to reference lower frequency")
    if (
        addon_upper == reference_lower
        and classes.addon.upper_inclusive
        and classes.reference.lower_inclusive
    ):
        raise ConfigurationError("addon and reference frequency intervals cannot overlap")


def _validate_delta_support(profile: DeltaReferenceSupportProfile) -> None:
    if (
        profile.adequate.cohort_median_out_support_max
        >= profile.invalid.cohort_median_out_support_min_exclusive
    ):
        raise ConfigurationError("adequate and invalid cohort-median support thresholds must leave a limited range")
    if profile.invalid.individual_out_support_min_exclusive <= profile.invalid.subject_out_support_threshold:
        raise ConfigurationError("individual invalid support threshold must exceed the cohort subject threshold")


def _validate_profiles(
    direct: DirectVoxelModelProfile,
    fiber: NormativeFiberModelProfile,
) -> None:
    _validate_source(direct.source, "direct voxel")
    _validate_source(fiber.source, "normative fiber")
    _validate_frequency_classes(direct.frequency_classes)
    _validate_frequency_classes(fiber.frequency_classes)
    _validate_delta_support(direct.delta_reference_support)
    _validate_delta_support(fiber.delta_reference_support)

    direct_bindings = (
        direct.endpoint_pair.baseline,
        direct.endpoint_pair.reference,
        direct.endpoint_pair.addon,
    )
    if len(set(direct_bindings)) != 3:
        raise ConfigurationError("baseline, reference, and add-on endpoint bindings must be distinct")

    if direct.model_set_id != fiber.model_set_id:
        raise ConfigurationError("direct and fiber model_set_id values must match")
    if direct.output.root != fiber.output.root:
        raise ConfigurationError("direct and fiber output roots must match")
    if direct.scales != fiber.scales:
        raise ConfigurationError("direct and fiber scale order must match exactly")
    if direct.endpoint_pair != fiber.endpoint_pair:
        raise ConfigurationError("direct and fiber endpoint pairs must match exactly")
    if direct.frequency_classes != fiber.frequency_classes:
        raise ConfigurationError("direct and fiber frequency classes must match exactly")
    if direct.hard_computability.n_subjects_min != fiber.hard_computability.n_subjects_min:
        raise ConfigurationError("direct and fiber minimum-subject requirements must match")
    if direct.delta_reference_support != fiber.delta_reference_support:
        raise ConfigurationError("direct and fiber DeltaReferenceScore support thresholds must match")
    connectome_ids = tuple(item.connectome_id for item in fiber.connectomes)
    if len(set(connectome_ids)) != len(connectome_ids):
        raise ConfigurationError("normative-fiber connectome IDs must be unique")
    if sum(item.role == "formal" for item in fiber.connectomes) != 1:
        raise ConfigurationError("normative-fiber profile requires exactly one formal connectome")
    diameter = fiber.oss.fiber_diameter_um
    if (
        fiber.oss.model != "OSS-DBSv2"
        or fiber.oss.activation_model != "pPAM"
        or diameter.minimum != 1.0
        or diameter.maximum != 4.0
        or diameter.samples != 10
        or diameter.sampling != "equidistant"
        or fiber.oss.fitting_probability_threshold != 0.5
    ):
        raise ConfigurationError(
            "normative_fiber_model_v1 requires OSS-DBSv2 pPAM with "
            "1-4 um, 10 equidistant samples, and threshold 0.5"
        )


def _validate_override_selection(overrides: WorkflowOverrides) -> None:
    if not isinstance(overrides, WorkflowOverrides):
        raise ConfigurationError("overrides must be a WorkflowOverrides value")
    for field in ("scales", "models", "connectomes"):
        values = getattr(overrides, field)
        if not isinstance(values, tuple):
            raise ConfigurationError(f"override {field} must be a tuple")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ConfigurationError(f"override {field} must contain nonempty strings")
        if len(set(values)) != len(values):
            raise ConfigurationError(f"override {field} values must be unique")
    if type(overrides.all_available) is not bool:
        raise ConfigurationError("override all_available must be boolean")
    if overrides.through is not None:
        if not isinstance(overrides.through, str) or overrides.through not in THROUGH_PHASES:
            raise ConfigurationError("override through must be observed, formal, sensitivity, or report")
    for field in ("resume", "force", "allow_expensive_producers"):
        value = getattr(overrides, field)
        if value is not None and type(value) is not bool:
            raise ConfigurationError(f"override {field} must be boolean")
    if overrides.workers is not None:
        if type(overrides.workers) is not int:
            raise ConfigurationError("override workers must be an integer")
        if overrides.workers < 1:
            raise ConfigurationError("workers must be positive")
    if overrides.scales and overrides.all_available:
        raise ConfigurationError("--scale and --all-available are mutually exclusive")
    if not overrides.scales and not overrides.all_available:
        raise ConfigurationError("exactly one of --scale or --all-available is required")
    if len(set(overrides.scales)) != len(overrides.scales):
        raise ConfigurationError("--scale values must be unique")


def _resolve_selector(values: tuple[str, ...], available: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not values:
        raise ConfigurationError(f"{label} selector cannot be empty")
    if len(set(values)) != len(values):
        raise ConfigurationError(f"{label} selector values must be unique")
    if "all" in values:
        if len(values) != 1:
            raise ConfigurationError(f"{label} selector 'all' cannot be combined with named values")
        return available
    unknown = sorted(set(values) - set(available))
    if unknown:
        raise ConfigurationError(f"unknown {label}: {unknown}")
    return values


def _scientific_profile_payload(profile: object) -> dict[str, object]:
    payload = asdict(profile)
    payload.pop("schema_version", None)
    payload.pop("model_set_id", None)
    payload.pop("output", None)
    payload.pop("scales", None)
    connectomes = payload.get("connectomes")
    if isinstance(connectomes, (list, tuple)):
        for connectome in connectomes:
            if isinstance(connectome, dict):
                connectome.pop("label", None)
                connectome.pop("path", None)
    return payload


def _scientific_configuration_hash(
    direct: DirectVoxelModelProfile,
    fiber: NormativeFiberModelProfile,
    selected_scales: tuple[str, ...],
    selected_models: tuple[str, ...],
    selected_connectomes: tuple[str, ...],
) -> str:
    return canonical_hash(
        {
            "direct_voxel": _scientific_profile_payload(direct),
            "normative_fiber": _scientific_profile_payload(fiber),
            "selected_scales": selected_scales,
            "selected_models": selected_models,
            "selected_connectomes": selected_connectomes,
        }
    )


def _configuration_hash(
    direct: DirectVoxelModelProfile,
    fiber: NormativeFiberModelProfile,
    workflow: WorkflowProfile,
    selected_scales: tuple[str, ...],
    selected_models: tuple[str, ...],
    selected_connectomes: tuple[str, ...],
) -> str:
    execution = workflow.execution
    return canonical_hash(
        {
            "direct_voxel": direct,
            "normative_fiber": fiber,
            "selected_scales": selected_scales,
            "selected_models": selected_models,
            "selected_connectomes": selected_connectomes,
            "execution": {
                "through": execution.through,
                "continue_on_endpoint_failure": execution.continue_on_endpoint_failure,
                "allow_expensive_producers": execution.allow_expensive_producers,
                "workers": execution.workers,
            },
            "storage": workflow.storage,
        }
    )


def load_workflow(
    path: Path,
    overrides: WorkflowOverrides = WorkflowOverrides(),
) -> ResolvedWorkflow:
    """Load and cross-validate the three public YAML profiles."""
    _validate_override_selection(overrides)
    workflow_path = Path(path).expanduser().resolve()
    workflow_payload = _read_yaml(workflow_path)
    _validate_schema(workflow_payload, "workflow", workflow_path)

    model_paths = {
        key: (workflow_path.parent / value).resolve()
        for key, value in workflow_payload["model_profiles"].items()
    }
    for label, model_path in model_paths.items():
        if not model_path.is_file():
            raise ConfigurationError(f"{label} model profile does not exist: {model_path}")

    direct_payload = _read_yaml(model_paths["direct_voxel"])
    fiber_payload = _read_yaml(model_paths["normative_fiber"])
    _validate_schema(direct_payload, "direct_voxel_model", model_paths["direct_voxel"])
    _validate_schema(fiber_payload, "normative_fiber_model", model_paths["normative_fiber"])
    direct = _direct_profile(direct_payload)
    fiber = _fiber_profile(fiber_payload)
    _validate_profiles(direct, fiber)

    if overrides.all_available:
        selected_scales = direct.scales
    else:
        unknown_scales = sorted(set(overrides.scales) - set(direct.scales))
        if unknown_scales:
            raise ConfigurationError(f"unknown selected scale IDs: {unknown_scales}")
        selected_scales = tuple(overrides.scales)

    workflow_selection = workflow_payload["selection"]
    requested_models = tuple(overrides.models) or tuple(workflow_selection["models"])
    requested_connectomes = tuple(overrides.connectomes) or tuple(workflow_selection["connectomes"])
    selected_models = _resolve_selector(requested_models, MODEL_FAMILIES, "model families")
    connectome_ids = tuple(item.connectome_id for item in fiber.connectomes)
    selected_connectomes = _resolve_selector(requested_connectomes, connectome_ids, "connectomes")
    if any(model_family.endswith("fiber") for model_family in selected_models):
        formal_connectome_id = fiber.formal_connectome.connectome_id
        if formal_connectome_id not in selected_connectomes:
            raise ConfigurationError(
                "fiber model selection must include the configured formal connectome"
            )

    execution_payload = deepcopy(workflow_payload["execution"])
    for key in ("through", "resume", "force", "allow_expensive_producers", "workers"):
        value = getattr(overrides, key)
        if value is not None:
            execution_payload[key] = value
    if execution_payload["resume"] and execution_payload["force"]:
        raise ConfigurationError("resume and force cannot both be enabled")
    if execution_payload["workers"] < 1:
        raise ConfigurationError("workers must be positive")

    workflow = WorkflowProfile(
        direct_voxel_model_path=model_paths["direct_voxel"],
        normative_fiber_model_path=model_paths["normative_fiber"],
        selection=WorkflowSelection(
            models=tuple(workflow_selection["models"]),
            connectomes=tuple(workflow_selection["connectomes"]),
        ),
        execution=ExecutionProfile(
            through=execution_payload["through"],
            resume=execution_payload["resume"],
            force=execution_payload["force"],
            continue_on_endpoint_failure=execution_payload["continue_on_endpoint_failure"],
            allow_expensive_producers=execution_payload["allow_expensive_producers"],
            workers=execution_payload["workers"],
        ),
        storage=StorageProfile(
            cache_root=Path(workflow_payload["storage"]["cache_root"]).expanduser().resolve(),
            run_root=Path(workflow_payload["storage"]["run_root"]).expanduser().resolve(),
        ),
    )
    return ResolvedWorkflow(
        direct_voxel=direct,
        normative_fiber=fiber,
        workflow=workflow,
        selected_scales=selected_scales,
        selected_models=selected_models,
        selected_connectomes=selected_connectomes,
        configuration_hash=_configuration_hash(
            direct,
            fiber,
            workflow,
            selected_scales,
            selected_models,
            selected_connectomes,
        ),
        scientific_configuration_hash=_scientific_configuration_hash(
            direct,
            fiber,
            selected_scales,
            selected_models,
            selected_connectomes,
        ),
        source_paths=(
            workflow_path,
            model_paths["direct_voxel"],
            model_paths["normative_fiber"],
        ),
    )


def validate_study_compatibility(study: StudyBaseRecord, workflow: ResolvedWorkflow) -> None:
    """Validate study-defined scales, endpoint bindings, and connectome assets."""
    if not isinstance(study, StudyBaseRecord):
        raise ConfigurationError("study must be a StudyBaseRecord")
    missing_scales = sorted(set(workflow.direct_voxel.scales) - set(study.scale_ids))
    if missing_scales:
        raise ConfigurationError(f"configured scale IDs missing from study base: {missing_scales}")

    expected_roles = {
        "baseline": (workflow.direct_voxel.endpoint_pair.baseline, "none"),
        "reference": (workflow.direct_voxel.endpoint_pair.reference, "reference_only"),
        "addon": (workflow.direct_voxel.endpoint_pair.addon, "combined"),
    }
    for label, (binding, expected_role) in expected_roles.items():
        matches = tuple(
            program
            for program in study.programs
            if program.phase_id == binding.phase_id and program.program_id == binding.program_id
        )
        if not matches:
            raise ConfigurationError(
                f"configured {label} endpoint {binding.identifier!r} is absent from study base"
            )
        invalid_roles = sorted({item.condition_role for item in matches if item.condition_role != expected_role})
        if invalid_roles:
            raise ConfigurationError(
                f"configured {label} endpoint has unexpected condition roles {invalid_roles}"
            )

    study_connectomes = {item.connectome_id: item for item in study.spatial.connectomes}
    for configured in workflow.normative_fiber.connectomes:
        if configured.connectome_id not in study_connectomes:
            raise ConfigurationError(
                f"configured connectome {configured.connectome_id!r} is missing from study base"
            )
        study_connectome = study_connectomes[configured.connectome_id]
        if configured.path != study_connectome.streamlines_path:
            raise ConfigurationError(
                f"configured connectome path differs from study base for {configured.connectome_id!r}"
            )
