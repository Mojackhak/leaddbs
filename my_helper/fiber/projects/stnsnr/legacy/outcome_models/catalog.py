"""Profile-driven endpoint discovery and clinical readiness classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import EndpointBinding, ResolvedWorkflow, ScaleSpec
from .identity import EndpointModelKey


class CatalogStatus(str, Enum):
    DATA_AVAILABLE = "data_available"
    INPUT_FAILURE = "input_failure"
    NOT_CONFIGURED = "not_requested_or_not_configured"


@dataclass(frozen=True)
class EndpointRecord:
    key: EndpointModelKey
    endpoint_model_id: str
    scale_label: str
    direction: str
    outcome_protocol: str
    outcome_phase: str
    hf_reference_protocol: str
    hf_reference_phase: str
    n_subjects: int
    subject_ids: tuple[str, ...]
    status: CatalogStatus
    failure_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "endpoint_model_id": self.endpoint_model_id,
            **self.key.as_dict(),
            "scale_label": self.scale_label,
            "direction": self.direction,
            "outcome_protocol": self.outcome_protocol,
            "outcome_phase": self.outcome_phase,
            "hf_reference_protocol": self.hf_reference_protocol,
            "hf_reference_phase": self.hf_reference_phase,
            "n_subjects": self.n_subjects,
            "subject_ids": list(self.subject_ids),
            "status": self.status.value,
            "failure_reasons": list(self.failure_reasons),
        }


_MODEL_SELECTOR_MAP = {
    "hf-voxel": "hf_voxel",
    "hf-fiber": "hf_fiber",
    "ulf-voxel": "ulf_voxel",
    "ulf-fiber": "ulf_fiber",
}
_ALL_MODEL_FAMILIES = frozenset(_MODEL_SELECTOR_MAP.values())
_MODEL_ORDER = {"hf_voxel": 0, "hf_fiber": 1, "ulf_voxel": 2, "ulf_fiber": 3}


def _selected_model_families(config: ResolvedWorkflow) -> set[str]:
    selectors = set(config.workflow.selection.models)
    families = set(_ALL_MODEL_FAMILIES) if selectors == {"all"} else {_MODEL_SELECTOR_MAP[item] for item in selectors}
    if "ulf_voxel" in families:
        families.add("hf_voxel")
    if "ulf_fiber" in families:
        families.add("hf_fiber")
    return families


def _selected_scales(config: ResolvedWorkflow) -> tuple[ScaleSpec, ...]:
    if config.workflow.selection.all_available:
        return tuple(sorted(config.scales, key=lambda item: item.scale_id))
    selected = set(config.workflow.selection.scales)
    return tuple(sorted((item for item in config.scales if item.scale_id in selected), key=lambda item: item.scale_id))


def _read_clinical(path: Path) -> tuple[pd.DataFrame, str | None]:
    if not path.is_file():
        return pd.DataFrame(), f"missing_clinical_table:{path}"
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path), None
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path), None
        return pd.DataFrame(), f"unsupported_clinical_table_format:{path.suffix}"
    except Exception as exc:
        return pd.DataFrame(), f"clinical_table_read_failure:{exc}"


def _condition_rows(
    clinical: pd.DataFrame,
    *,
    scale_label: str,
    binding: EndpointBinding,
    columns,
) -> pd.DataFrame:
    return clinical[
        clinical[columns.scale].astype(str).eq(scale_label)
        & clinical[columns.protocol].astype(str).eq(binding.protocol)
        & clinical[columns.phase].astype(str).eq(binding.phase)
    ].copy()


def _usable_subjects(rows: pd.DataFrame, columns) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if rows.empty:
        return (), ()
    duplicate_mask = rows.duplicated(subset=[columns.subject_id], keep=False)
    duplicate_ids = tuple(sorted(rows.loc[duplicate_mask, columns.subject_id].astype(str).unique()))
    value = pd.to_numeric(rows[columns.value], errors="coerce").to_numpy(dtype=float)
    baseline = pd.to_numeric(rows[columns.baseline], errors="coerce").to_numpy(dtype=float)
    usable_mask = np.isfinite(value) & np.isfinite(baseline)
    subjects = tuple(sorted(rows.loc[usable_mask, columns.subject_id].astype(str).unique()))
    return subjects, duplicate_ids


def _record(
    config: ResolvedWorkflow,
    scale: ScaleSpec,
    *,
    model_family: str,
    endpoint_phase: str,
    connectome: str,
    outcome_binding: EndpointBinding | None,
    hf_binding: EndpointBinding,
    clinical: pd.DataFrame,
    global_failure: str | None,
    missing_columns: tuple[str, ...],
) -> EndpointRecord:
    key = EndpointModelKey(
        study_id=config.study.study_id,
        scale_id=scale.scale_id,
        endpoint_phase=endpoint_phase,
        model_family=model_family,
        connectome=connectome,
    )
    if outcome_binding is None:
        return EndpointRecord(
            key=key,
            endpoint_model_id=key.identifier,
            scale_label=scale.label,
            direction=scale.direction,
            outcome_protocol="",
            outcome_phase="",
            hf_reference_protocol=hf_binding.protocol,
            hf_reference_phase=hf_binding.phase,
            n_subjects=0,
            subject_ids=(),
            status=CatalogStatus.NOT_CONFIGURED,
            failure_reasons=(f"{endpoint_phase}_binding_omitted",),
        )

    base = {
        "key": key,
        "endpoint_model_id": key.identifier,
        "scale_label": scale.label,
        "direction": scale.direction,
        "outcome_protocol": outcome_binding.protocol,
        "outcome_phase": outcome_binding.phase,
        "hf_reference_protocol": hf_binding.protocol,
        "hf_reference_phase": hf_binding.phase,
    }
    if global_failure or missing_columns:
        reasons = []
        if global_failure:
            reasons.append(global_failure)
        if missing_columns:
            reasons.append(f"missing_clinical_columns:{','.join(missing_columns)}")
        return EndpointRecord(
            **base,
            n_subjects=0,
            subject_ids=(),
            status=CatalogStatus.INPUT_FAILURE,
            failure_reasons=tuple(reasons),
        )

    columns = config.study.clinical_columns
    outcome_rows = _condition_rows(clinical, scale_label=scale.label, binding=outcome_binding, columns=columns)
    outcome_subjects, outcome_duplicates = _usable_subjects(outcome_rows, columns)
    reasons: list[str] = []
    if outcome_duplicates:
        reasons.append(f"duplicate_outcome_rows:{','.join(outcome_duplicates)}")

    if model_family.startswith("hf_"):
        paired_subjects = outcome_subjects
    else:
        hf_rows = _condition_rows(clinical, scale_label=scale.label, binding=hf_binding, columns=columns)
        hf_subjects, hf_duplicates = _usable_subjects(hf_rows, columns)
        if hf_duplicates:
            reasons.append(f"duplicate_hf_reference_rows:{','.join(hf_duplicates)}")
        paired_subjects = tuple(sorted(set(outcome_subjects) & set(hf_subjects)))

    if len(paired_subjects) < scale.minimum_subjects:
        reasons.append(f"minimum_subjects:{len(paired_subjects)}<{scale.minimum_subjects}")
    status = CatalogStatus.INPUT_FAILURE if reasons else CatalogStatus.DATA_AVAILABLE
    return EndpointRecord(
        **base,
        n_subjects=len(paired_subjects),
        subject_ids=paired_subjects,
        status=status,
        failure_reasons=tuple(reasons),
    )


def _connectomes_for_family(config: ResolvedWorkflow, model_family: str) -> Iterable[str]:
    if model_family.endswith("_fiber"):
        return config.workflow.selection.connectomes
    return ("none",)


def build_endpoint_catalog(config: ResolvedWorkflow) -> tuple[EndpointRecord, ...]:
    """Build deterministic endpoint-model rows from profiles and clinical inputs."""
    clinical, global_failure = _read_clinical(config.study.paths.clinical_table)
    required_columns = tuple(vars(config.study.clinical_columns).values())
    missing_columns = tuple(sorted(column for column in required_columns if column not in clinical.columns))
    families = _selected_model_families(config)
    phases = set(config.workflow.selection.phases)
    records: list[EndpointRecord] = []

    for scale in _selected_scales(config):
        hf_binding = scale.endpoint_bindings["frequency_1_reference"]
        for family in ("hf_voxel", "hf_fiber"):
            if family not in families:
                continue
            for connectome in _connectomes_for_family(config, family):
                records.append(
                    _record(
                        config,
                        scale,
                        model_family=family,
                        endpoint_phase="reference",
                        connectome=connectome,
                        outcome_binding=hf_binding,
                        hf_binding=hf_binding,
                        clinical=clinical,
                        global_failure=global_failure,
                        missing_columns=missing_columns,
                    )
                )

        for endpoint_phase, binding_name in (
            ("chronic", "frequency_2_addon_chronic"),
            ("immediate", "frequency_2_addon_immediate"),
        ):
            if endpoint_phase not in phases:
                continue
            outcome_binding = scale.endpoint_bindings.get(binding_name)
            for family in ("ulf_voxel", "ulf_fiber"):
                if family not in families:
                    continue
                for connectome in _connectomes_for_family(config, family):
                    records.append(
                        _record(
                            config,
                            scale,
                            model_family=family,
                            endpoint_phase=endpoint_phase,
                            connectome=connectome,
                            outcome_binding=outcome_binding,
                            hf_binding=hf_binding,
                            clinical=clinical,
                            global_failure=global_failure,
                            missing_columns=missing_columns,
                        )
                    )

    return tuple(
        sorted(
            records,
            key=lambda row: (
                row.key.scale_id,
                _MODEL_ORDER[row.key.model_family],
                row.key.endpoint_phase,
                row.key.connectome,
            ),
        )
    )
