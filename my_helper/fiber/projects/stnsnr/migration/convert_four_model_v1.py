"""Convert predecessor profiles into review-only dual-frequency drafts."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml


class MigrationError(ValueError):
    """Raised when predecessor profiles cannot be converted unambiguously."""


_PROFILE_TOP_LEVEL = {
    "workflow": {
        "schema_version",
        "profile_type",
        "study_profile",
        "scale_profile",
        "model_profile",
        "selection",
        "execution",
    },
    "study": {
        "schema_version",
        "profile_type",
        "study_id",
        "paths",
        "clinical_columns",
        "space",
        "components",
        "conditions",
        "efield_resolvers",
        "connectomes",
    },
    "scales": {"schema_version", "profile_type", "scales"},
    "model": {
        "schema_version",
        "profile_type",
        "profile_id",
        "direct_voxel",
        "normative_fiber",
        "resolver",
        "formal",
        "sensitivity",
        "oss",
        "reporting",
    },
}

_MAPPING_FIELDS = {
    "schema_version",
    "target_model_set_id",
    "target_endpoint_pair",
    "target_frequency_classes",
    "source_subscale_field",
    "source_subscale_selection_field",
    "component_roles",
    "condition_roles",
    "exposure_bindings",
    "subscale_bindings",
    "workflow_subscale_values",
    "model_section_map",
    "model_field_map",
    "drop_model_fields",
}


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MigrationError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise MigrationError(f"{label} must be a mapping")
    return payload


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise MigrationError(f"unknown fields in {label}: {', '.join(unknown)}")


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationError(f"{label} must be a mapping")
    return value


def _profile_path(workflow_path: Path, workflow: Mapping[str, Any], key: str) -> Path:
    value = workflow.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MigrationError(f"workflow {key} must be an explicit path")
    return (workflow_path.parent / value).resolve()


def _validate_source_profile(payload: Mapping[str, Any], label: str) -> None:
    _reject_unknown(payload, _PROFILE_TOP_LEVEL[label], f"{label} profile")
    if payload.get("schema_version") != "four_model_v1":
        raise MigrationError(f"{label} profile is not four_model_v1")


def _mapping_dict(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    return _require_mapping(mapping.get(key), f"migration mapping {key}")


def _nonempty_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MigrationError(f"{label} must be a non-empty list")
    result = [str(item).strip() for item in value]
    if any(not item for item in result) or len(result) != len(set(result)):
        raise MigrationError(f"{label} must contain unique non-empty strings")
    return result


def _convert_endpoint_pair(
    mapping: Mapping[str, Any],
    condition_roles: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    configured = _mapping_dict(mapping, "target_endpoint_pair")
    if set(configured) != {"baseline", "reference", "addon"}:
        raise MigrationError("target endpoint pair must define baseline, reference, and addon")
    target: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, int]] = set()
    for role in ("baseline", "reference", "addon"):
        row = _require_mapping(configured[role], f"target endpoint pair {role}")
        allowed = {"phase_id", "program_id"}
        if role != "baseline":
            allowed.add("source_condition_id")
        _reject_unknown(row, allowed, f"target endpoint pair {role}")
        phase_id = str(row.get("phase_id", "")).strip()
        program_id = row.get("program_id")
        if (
            not phase_id
            or isinstance(program_id, bool)
            or not isinstance(program_id, int)
            or program_id < 0
        ):
            raise MigrationError(f"target endpoint pair {role} has invalid phase/program identity")
        identity = (phase_id, program_id)
        if identity in identities:
            raise MigrationError("target endpoint pair identities must be distinct")
        identities.add(identity)
        target[role] = {"phase_id": phase_id, "program_id": program_id}
        evidence[role] = dict(target[role])
        if role == "baseline":
            continue
        source_condition_id = str(row.get("source_condition_id", "")).strip()
        expected_role = "reference_only" if role == "reference" else "combined"
        if condition_roles.get(source_condition_id) != expected_role:
            raise MigrationError(
                f"target endpoint pair {role} must map a {expected_role} source condition"
            )
        evidence[role]["source_condition_id"] = source_condition_id
    return target, evidence


def _convert_frequency_classes(mapping: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    configured = _mapping_dict(mapping, "target_frequency_classes")
    if set(configured) != {"reference", "addon"}:
        raise MigrationError("target frequency classes must define reference and addon")
    result: dict[str, dict[str, Any]] = {}
    required = {"lower", "lower_inclusive", "upper", "upper_inclusive"}
    for role in ("reference", "addon"):
        row = _require_mapping(configured[role], f"target frequency class {role}")
        if set(row) != required:
            raise MigrationError(f"target frequency class {role} fields are invalid")
        if not isinstance(row["lower_inclusive"], bool) or not isinstance(
            row["upper_inclusive"], bool
        ):
            raise MigrationError(f"target frequency class {role} inclusivity must be boolean")
        for bound in ("lower", "upper"):
            value = row[bound]
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise MigrationError(f"target frequency class {role} {bound} is invalid")
        result[role] = copy.deepcopy(row)
    return result


def _validate_exact_source_keys(
    observed: Mapping[str, Any],
    configured: Mapping[str, Any],
    label: str,
) -> None:
    missing = sorted(set(observed) - set(configured))
    extra = sorted(set(configured) - set(observed))
    if missing or extra:
        raise MigrationError(
            f"{label} mapping mismatch; unmapped={missing}, unknown_mapping={extra}"
        )


def _combined_condition(
    conditions: Mapping[str, Any],
    condition_roles: Mapping[str, Any],
    source_subscale_field: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for source_id, role in condition_roles.items():
        if role != "combined":
            continue
        source = _require_mapping(conditions[source_id], f"source condition {source_id}")
        normalized = {
            key: copy.deepcopy(value)
            for key, value in source.items()
            if key != source_subscale_field
        }
        rows.append(normalized)
    if not rows:
        raise MigrationError("combined condition mapping is empty")
    if any(row != rows[0] for row in rows[1:]):
        raise MigrationError(
            "combined stimulation definitions conflict after removing source subscale data"
        )
    return {
        "condition_role": "combined",
        "components": ["reference_component", "addon_component"],
        "source_stimulation_metadata": rows[0],
    }


def _reference_condition(
    conditions: Mapping[str, Any],
    condition_roles: Mapping[str, Any],
    source_subscale_field: str,
) -> dict[str, Any]:
    source_ids = [key for key, role in condition_roles.items() if role == "reference_only"]
    if len(source_ids) != 1:
        raise MigrationError("condition mapping must define exactly one reference_only source")
    source = _require_mapping(conditions[source_ids[0]], "source reference condition")
    metadata = {
        key: copy.deepcopy(value)
        for key, value in source.items()
        if key != source_subscale_field
    }
    return {
        "condition_role": "reference_only",
        "components": ["reference_component"],
        "source_stimulation_metadata": metadata,
    }


def _convert_scales(
    source: Mapping[str, Any],
    subscale_bindings: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_scales = source.get("scales")
    if not isinstance(source_scales, list):
        raise MigrationError("scale profile scales must be a list")
    converted: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    for row in source_scales:
        if not isinstance(row, dict):
            raise MigrationError("source scale row must be a mapping")
        _reject_unknown(
            row,
            {"scale_id", "label", "direction", "minimum_subjects", "endpoint_bindings"},
            "source scale row",
        )
        scale_id = str(row.get("scale_id", "")).strip()
        if not scale_id:
            raise MigrationError("source scale row has no scale_id")
        source_bindings = _require_mapping(
            row.get("endpoint_bindings"),
            f"scale {scale_id} bindings",
        )
        unknown = sorted(set(source_bindings) - set(subscale_bindings))
        if unknown:
            raise MigrationError(f"unmapped endpoint bindings for {scale_id}: {', '.join(unknown)}")
        target_bindings: list[dict[str, Any]] = []
        reference_id: str | None = None
        for source_binding_id, source_payload in source_bindings.items():
            mapped = _require_mapping(
                subscale_bindings[source_binding_id],
                f"subscale mapping {source_binding_id}",
            )
            _reject_unknown(
                mapped,
                {"endpoint_binding_suffix", "condition_role"},
                f"subscale mapping {source_binding_id}",
            )
            suffix = str(mapped.get("endpoint_binding_suffix", "")).strip()
            condition_role = str(mapped.get("condition_role", ""))
            if not suffix or condition_role not in {"reference_only", "combined"}:
                raise MigrationError(f"invalid subscale mapping for {source_binding_id}")
            target_id = f"{scale_id}__{suffix}"
            target = {
                "endpoint_binding_id": target_id,
                "condition_id": condition_role,
            }
            if condition_role == "reference_only":
                if reference_id is not None:
                    raise MigrationError(f"scale {scale_id} has multiple reference bindings")
                reference_id = target_id
            target_bindings.append(target)
            report_rows.append(
                {
                    "parent_scale_id": scale_id,
                    "source_binding_id": source_binding_id,
                    "source_binding": copy.deepcopy(source_payload),
                    "target_endpoint_binding_id": target_id,
                    "target_condition_id": condition_role,
                }
            )
        if reference_id is None:
            raise MigrationError(f"scale {scale_id} has no reference binding")
        for target in target_bindings:
            if target["condition_id"] == "combined":
                target["matched_reference_binding_id"] = reference_id
        converted.append(
            {
                "scale_id": scale_id,
                "label": row.get("label"),
                "direction": row.get("direction"),
                "minimum_subjects": row.get("minimum_subjects"),
                "endpoint_bindings": target_bindings,
            }
        )
    return (
        {
            "schema_version": "dual_frequency_v1",
            "profile_type": "scale_profile",
            "scales": converted,
        },
        report_rows,
    )


def _convert_model_sections(
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    section_map = _mapping_dict(mapping, "model_section_map")
    field_map = _mapping_dict(mapping, "model_field_map")
    converted: dict[str, Any] = {}
    for key, value in source.items():
        if key in {"schema_version", "profile_type", "profile_id"}:
            continue
        target_key = str(section_map.get(key, key))
        if target_key in converted:
            raise MigrationError(f"model section collision after mapping: {target_key}")
        payload = copy.deepcopy(value)
        mapped_fields = field_map.get(key, {})
        if mapped_fields:
            payload = _require_mapping(payload, f"model section {key}")
            mapped_fields = _require_mapping(mapped_fields, f"model field map {key}")
            unknown = sorted(set(mapped_fields) - set(payload))
            if unknown:
                raise MigrationError(f"model field mapping references unknown fields: {unknown}")
            payload = {
                str(mapped_fields.get(field, field)): item
                for field, item in payload.items()
            }
        converted[target_key] = payload
    for dotted in mapping.get("drop_model_fields", []):
        if not isinstance(dotted, str) or "." not in dotted:
            raise MigrationError("drop_model_fields entries must be section.field strings")
        section, field = dotted.split(".", 1)
        payload = converted.get(section)
        if not isinstance(payload, dict) or field not in payload:
            raise MigrationError(f"drop_model_fields target does not exist: {dotted}")
        del payload[field]
    return converted


def _write_text_new(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    created = False
    try:
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                created = True
                handle.write(content)
        except FileExistsError as exc:
            raise MigrationError(
                f"refusing to replace existing temporary migration output: {temporary}"
            ) from exc
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise MigrationError(f"refusing to replace existing migration output: {path}") from exc
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def _write_yaml_new(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_new(path, yaml.safe_dump(dict(payload), sort_keys=False))


def convert_profiles(
    source_workflow: Path,
    mapping_path: Path,
    output_dir: Path,
) -> Path:
    """Write review-only target drafts from explicitly mapped predecessor YAML."""
    source_workflow = Path(source_workflow).expanduser().resolve()
    mapping_path = Path(mapping_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    workflow = _load_yaml(source_workflow, "workflow profile")
    _validate_source_profile(workflow, "workflow")
    mapping = _load_yaml(mapping_path, "migration mapping")
    _reject_unknown(mapping, _MAPPING_FIELDS, "migration mapping")
    if mapping.get("schema_version") != "dual_frequency_migration_mapping_v1":
        raise MigrationError("unsupported migration mapping schema")
    study = _load_yaml(_profile_path(source_workflow, workflow, "study_profile"), "study profile")
    scales = _load_yaml(_profile_path(source_workflow, workflow, "scale_profile"), "scale profile")
    model = _load_yaml(_profile_path(source_workflow, workflow, "model_profile"), "model profile")
    for label, payload in (("study", study), ("scales", scales), ("model", model)):
        _validate_source_profile(payload, label)

    component_roles = _mapping_dict(mapping, "component_roles")
    condition_roles = _mapping_dict(mapping, "condition_roles")
    exposure_bindings = _mapping_dict(mapping, "exposure_bindings")
    subscale_bindings = _mapping_dict(mapping, "subscale_bindings")
    component_role_values = list(component_roles.values())
    if (
        len(component_role_values) != 2
        or not all(isinstance(role, str) for role in component_role_values)
        or set(component_role_values) != {"reference_component", "addon_component"}
    ):
        raise MigrationError(
            "component mapping must define one reference_component and one addon_component"
        )
    condition_role_values = list(condition_roles.values())
    if not all(isinstance(role, str) for role in condition_role_values) or set(
        condition_role_values
    ) != {"reference_only", "combined"}:
        raise MigrationError("condition mapping contains an unsupported target role")
    _validate_exact_source_keys(
        _require_mapping(study.get("components"), "source components"),
        component_roles,
        "component role",
    )
    source_conditions = _require_mapping(study.get("conditions"), "source conditions")
    _validate_exact_source_keys(source_conditions, condition_roles, "condition role")
    _validate_exact_source_keys(source_conditions, subscale_bindings, "subscale binding")
    for source_id, value in subscale_bindings.items():
        row = _require_mapping(value, f"subscale binding {source_id}")
        if row.get("condition_role") != condition_roles[source_id]:
            raise MigrationError(
                f"subscale binding {source_id} does not match its condition role"
            )
    _validate_exact_source_keys(
        _require_mapping(study.get("efield_resolvers"), "source exposure bindings"),
        exposure_bindings,
        "exposure binding",
    )
    exposure_role_pairs: set[tuple[str, str]] = set()
    for source_id, value in exposure_bindings.items():
        row = _require_mapping(value, f"exposure binding {source_id}")
        if set(row) != {"condition_role", "component_role"}:
            raise MigrationError(f"exposure binding {source_id} fields are invalid")
        pair = (str(row["condition_role"]), str(row["component_role"]))
        exposure_role_pairs.add(pair)
    if exposure_role_pairs != {
        ("reference_only", "reference_component"),
        ("combined", "reference_component"),
        ("combined", "addon_component"),
    }:
        raise MigrationError("exposure bindings do not cover the dual-frequency component roles")
    source_subscale_field = str(mapping.get("source_subscale_field", "")).strip()
    if not source_subscale_field:
        raise MigrationError("migration mapping source_subscale_field is required")
    components = {
        str(role): copy.deepcopy(study["components"][source_id])
        for source_id, role in component_roles.items()
    }
    conditions = {
        "reference_only": _reference_condition(
            source_conditions, condition_roles, source_subscale_field
        ),
        "combined": _combined_condition(
            source_conditions, condition_roles, source_subscale_field
        ),
    }

    target_scales, binding_report = _convert_scales(scales, subscale_bindings)
    source_selection = _require_mapping(workflow.get("selection"), "source workflow selection")
    source_selector = str(mapping.get("source_subscale_selection_field", "")).strip()
    if not source_selector:
        raise MigrationError("migration mapping source_subscale_selection_field is required")
    allowed_selection = {"scales", "models", "connectomes", source_selector}
    _reject_unknown(source_selection, allowed_selection, "workflow selection")
    selector_map = _mapping_dict(mapping, "workflow_subscale_values")
    selector_values = [str(value).strip() for value in selector_map.values()]
    if any(not value for value in selector_values) or len(selector_values) != len(
        set(selector_values)
    ):
        raise MigrationError("workflow subscale mapping values must be unique non-empty strings")
    selected_source_values = _nonempty_string_list(
        source_selection.get(source_selector),
        "source subscale selection",
    )
    unknown_selection = [value for value in selected_source_values if value not in selector_map]
    if unknown_selection:
        raise MigrationError(f"unmapped workflow subscale selections: {unknown_selection}")
    selected_scale_ids = _nonempty_string_list(
        source_selection.get("scales"),
        "source workflow scale selection",
    )
    available_scale_ids = {str(row["scale_id"]) for row in target_scales["scales"]}
    unknown_scales = sorted(set(selected_scale_ids) - available_scale_ids)
    if unknown_scales:
        raise MigrationError(f"unknown selected scales: {unknown_scales}")

    endpoint_pair, endpoint_pair_evidence = _convert_endpoint_pair(mapping, condition_roles)
    frequency_classes = _convert_frequency_classes(mapping)
    reference_condition_id = endpoint_pair_evidence["reference"]["source_condition_id"]
    addon_condition_id = endpoint_pair_evidence["addon"]["source_condition_id"]
    source_scale_rows = {str(row["scale_id"]): row for row in scales["scales"]}
    for scale_id in selected_scale_ids:
        bindings = _require_mapping(
            source_scale_rows[scale_id].get("endpoint_bindings"),
            f"source scale {scale_id} bindings",
        )
        missing_bindings = [
            source_id
            for source_id in (reference_condition_id, addon_condition_id)
            if source_id not in bindings
        ]
        if missing_bindings:
            raise MigrationError(
                f"selected scale {scale_id} lacks target endpoint bindings: {missing_bindings}"
            )

    mapped_source_values = [str(selector_map[value]) for value in selected_source_values]
    addon_subscale_mapping = _require_mapping(
        subscale_bindings[addon_condition_id],
        f"subscale mapping {addon_condition_id}",
    )
    selected_addon_suffix = str(addon_subscale_mapping.get("endpoint_binding_suffix", ""))
    if selected_addon_suffix not in mapped_source_values:
        raise MigrationError("target addon endpoint is absent from the source workflow selection")

    model_set_id = str(mapping.get("target_model_set_id", "")).strip()
    if not model_set_id:
        raise MigrationError("migration mapping target_model_set_id is required")
    output_root = str(
        _require_mapping(study.get("paths"), "source paths").get("output_root", "")
    ).strip()
    if not output_root:
        raise MigrationError("source output root is required for migration review")

    model_sections = _convert_model_sections(model, mapping)
    direct_parameters = _require_mapping(
        model_sections.pop("direct_voxel", None),
        "target direct_voxel section",
    )
    normative_parameters = _require_mapping(
        model_sections.pop("normative_fiber", None),
        "target normative_fiber section",
    )
    source_connectome_roles = _require_mapping(
        normative_parameters.pop("connectome_roles", None),
        "source connectome roles",
    )
    source_connectomes = _require_mapping(study.get("connectomes"), "source connectomes")
    _validate_exact_source_keys(source_connectomes, source_connectome_roles, "connectome role")
    fold_minimums: dict[str, Any] = {}
    hard_filter = normative_parameters.get("hard_filter")
    if isinstance(hard_filter, dict) and "fold_candidate_fibers_min_by_connectome" in hard_filter:
        fold_minimums = _require_mapping(
            hard_filter.get("fold_candidate_fibers_min_by_connectome"),
            "source connectome fold minimums",
        )
        _validate_exact_source_keys(source_connectomes, fold_minimums, "connectome fold minimum")

    target_connectome_entries: list[dict[str, Any]] = []
    connectome_role_conversions: dict[str, dict[str, str]] = {}
    role_map = {"observed_robustness": "sensitive", "formal": "formal"}
    for connectome_id, payload in source_connectomes.items():
        source_role = str(source_connectome_roles[connectome_id])
        target_role = role_map.get(source_role)
        if target_role is None:
            raise MigrationError(
                f"unknown source connectome role for {connectome_id}: {source_role}"
            )
        entry = {
            "connectome_id": str(connectome_id),
            **copy.deepcopy(_require_mapping(payload, f"source connectome {connectome_id}")),
            "role": target_role,
        }
        if connectome_id in fold_minimums:
            entry["fold_candidate_fibers_min"] = copy.deepcopy(fold_minimums[connectome_id])
        target_connectome_entries.append(entry)
        connectome_role_conversions[str(connectome_id)] = {
            "source_role": source_role,
            "target_role": target_role,
        }
    if sum(row["role"] == "formal" for row in target_connectome_entries) != 1:
        raise MigrationError("migration requires exactly one formal target connectome")

    shared_profile = {
        "schema_version": "dual_frequency_v1",
        "model_set_id": model_set_id,
        "output": {"root": output_root},
        "scales": selected_scale_ids,
        "endpoint_pair": endpoint_pair,
        "frequency_classes": frequency_classes,
    }
    target_direct = {
        **copy.deepcopy(shared_profile),
        "profile_type": "direct_voxel_model",
        "direct_voxel": direct_parameters,
    }
    target_normative = {
        **copy.deepcopy(shared_profile),
        "profile_type": "normative_fiber_model",
        "connectomes": {"entries": target_connectome_entries},
        "normative_fiber": normative_parameters,
    }
    for key in ("resolver", "formal", "sensitivity", "reporting"):
        if key in model_sections:
            target_direct[key] = copy.deepcopy(model_sections[key])
            target_normative[key] = copy.deepcopy(model_sections[key])
    if "activation" in model_sections:
        target_normative["activation"] = copy.deepcopy(model_sections["activation"])

    target_workflow = {
        "schema_version": "dual_frequency_v1",
        "profile_type": "workflow",
        "direct_voxel_profile": "direct_voxel_model.yaml",
        "normative_fiber_profile": "normative_fiber_model.yaml",
        "selection": {
            "models": copy.deepcopy(source_selection.get("models", [])),
            "connectomes": copy.deepcopy(source_selection.get("connectomes", [])),
        },
        "execution": copy.deepcopy(workflow.get("execution")),
    }

    output_names = (
        "direct_voxel_model.yaml",
        "normative_fiber_model.yaml",
        "workflow.yaml",
        "conversion_report.json",
    )
    existing = [name for name in output_names if (output_dir / name).exists()]
    if existing:
        raise MigrationError(f"refusing to replace existing migration outputs: {existing}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("direct_voxel_model.yaml", target_direct),
        ("normative_fiber_model.yaml", target_normative),
        ("workflow.yaml", target_workflow),
    ):
        _write_yaml_new(output_dir / name, payload)
    report = {
        "schema_version": "dual_frequency_migration_report_v1",
        "status": "draft_requires_review",
        "production_loader_imported": False,
        "study_base": {
            "required_external_input": True,
            "generated": False,
            "source_study_id": study.get("study_id"),
        },
        "source_workflow": str(source_workflow),
        "mapping_path": str(mapping_path),
        "target_component_evidence": components,
        "target_condition_evidence": conditions,
        "target_endpoint_pair_source_evidence": endpoint_pair_evidence,
        "connectome_role_conversions": connectome_role_conversions,
        "binding_conversions": binding_report,
        "source_selection_evidence": {
            "source_subscale_values": selected_source_values,
            "mapped_subscale_values": mapped_source_values,
            "target_addon_subscale_value": selected_addon_suffix,
            "unrepresented_source_subscale_values": [
                source_value
                for source_value, mapped_value in zip(
                    selected_source_values,
                    mapped_source_values,
                )
                if mapped_value != selected_addon_suffix
            ],
        },
        "source_import_config": {
            "paths": copy.deepcopy(study.get("paths")),
            "clinical_columns": copy.deepcopy(study.get("clinical_columns")),
            "exposure_resolvers": copy.deepcopy(study.get("efield_resolvers")),
            "exposure_binding_map": copy.deepcopy(exposure_bindings),
        },
        "target_profiles": [
            "direct_voxel_model.yaml",
            "normative_fiber_model.yaml",
            "workflow.yaml",
        ],
    }
    report_path = output_dir / "conversion_report.json"
    _write_text_new(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_path
