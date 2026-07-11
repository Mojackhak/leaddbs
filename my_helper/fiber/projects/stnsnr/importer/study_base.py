"""Build the strict STNSNr dual-frequency study-base document."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator, FormatChecker
import numpy as np
import pandas as pd
from scipy.io import loadmat


class StudyBaseImportError(ValueError):
    """Raised when source data cannot be mapped without ambiguity."""


_CONDITION_MAP = {
    ("Pre-op", "A"): ("T0", 0, "Preoperative", "none", "preoperative", 0),
    ("STN (immediate)", "B"): ("T1", 1, "STN immediate", "reference_only", "immediate", 1),
    ("STN (3 m)", "D"): ("T2", 1, "STN 3m", "reference_only", "3m", 1),
    ("STN+SNr (immediate)", "C"): ("T2", 2, "STN+SNr immediate", "combined", "immediate", 2),
    ("STN+SNr (3 m)", "E"): ("T3", 2, "STN+SNr 3m", "combined", "3m", 1),
}
_PROGRAM_SPECS = tuple(_CONDITION_MAP.items())
_PROGRAMMING_MAP = {
    ("immediate", "STN"): ("T1", 1),
    ("3m", "STN"): ("T2", 1),
    ("immediate", "STN+SNr"): ("T2", 2),
    ("3m", "STN+SNr"): ("T3", 2),
}
_TARGET_COMPONENT = {
    "STN": "frequency_1_reference",
    "SNr": "frequency_2_addon",
}
_ELECTRODE_MODEL_CONTACTS = {
    "Medtronic 3387": 4,
    "SceneRay SR1200": 4,
    "SceneRay SR1202": 8,
}

_DEFAULT_CLINICAL = Path("/Volumes/VAL/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx")
_DEFAULT_STIMULATION = Path("/Volumes/VAL/STNSNr/summary/cohort/subj/followup_stimulation.xlsx")
_DEFAULT_LEADDBS_ROOT = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs")
_DEFAULT_ASSET_ROOT = Path("/Users/mojackhu/Github/leaddbs")
_DEFAULT_OUTPUT = Path("/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json")


def sanitize_scale_id(label: str, *, existing: Mapping[str, str] | None = None) -> str:
    """Create a stable scale ID and reject normalization collisions."""
    normalized = unicodedata.normalize("NFKC", str(label)).lower()
    scale_id = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not scale_id:
        raise StudyBaseImportError(f"scale label has no usable identifier: {label!r}")
    if existing is not None and scale_id in existing and existing[scale_id] != label:
        raise StudyBaseImportError(
            f"scale ID collision: {existing[scale_id]!r} and {label!r} -> {scale_id}"
        )
    return scale_id


def _as_side_list(value: Any, label: str) -> list[Any]:
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            rows = list(value.reshape(-1))
        elif value.ndim >= 3 and value.shape[0] == 2:
            rows = [value[0], value[1]]
        else:
            rows = list(value)
    elif isinstance(value, (list, tuple)):
        rows = list(value)
    else:
        raise StudyBaseImportError(f"reconstruction {label} is not bilateral")
    if len(rows) != 2:
        raise StudyBaseImportError(f"reconstruction {label} must contain two sides")
    return rows


def _coord_count(value: Any, label: str) -> int:
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[1] != 3 or array.shape[0] < 1:
        raise StudyBaseImportError(f"reconstruction {label} must be an n-by-3 array")
    return int(array.shape[0])


def extract_electrodes(reconstruction_path: str | Path) -> list[dict[str, Any]]:
    """Extract bilateral electrode hardware in JSON left-then-right order."""
    path = Path(reconstruction_path)
    try:
        payload = loadmat(path, simplify_cells=True)
        reco = payload["reco"]
        props = _as_side_list(reco["props"], "props")
        mni = _as_side_list(reco["mni"]["coords_mm"], "MNI coordinates")
        native = _as_side_list(reco["native"]["coords_mm"], "native coordinates")
    except StudyBaseImportError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise StudyBaseImportError(f"cannot read reconstruction: {path}") from exc

    extracted: dict[str, dict[str, Any]] = {}
    for source_index, hemisphere in ((0, "R"), (1, "L")):
        prop = props[source_index]
        model = prop.get("elmodel") if isinstance(prop, dict) else None
        if not isinstance(model, str) or not model.strip():
            raise StudyBaseImportError(f"reconstruction electrode model missing for {hemisphere}")
        mni_count = _coord_count(mni[source_index], f"MNI {hemisphere}")
        native_count = _coord_count(native[source_index], f"native {hemisphere}")
        if mni_count != native_count:
            raise StudyBaseImportError(
                f"native and MNI contact counts differ for {hemisphere}: {native_count} != {mni_count}"
            )
        expected = _ELECTRODE_MODEL_CONTACTS.get(model)
        if expected is None:
            raise StudyBaseImportError(
                f"unsupported electrode model for {hemisphere}: {model}"
            )
        if expected != mni_count:
            raise StudyBaseImportError(
                f"electrode model/contact-count inconsistency for {hemisphere}: {model} expects {expected}, got {mni_count}"
            )
        extracted[hemisphere] = {
            "electrode_id": f"lead-{hemisphere}",
            "hemisphere": hemisphere,
            "electrode_model": model,
            "contact_count": mni_count,
            "reconstruction_lead_id": source_index + 1,
        }
    return [extracted["L"], extracted["R"]]


def _read_excel(path: Path, *, sheet_name: str | int = 0) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet_name, dtype={"ID": str})
    except (OSError, ValueError) as exc:
        raise StudyBaseImportError(f"cannot read workbook {path}, sheet {sheet_name!r}") from exc


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise StudyBaseImportError(f"missing required {label} columns: {', '.join(missing)}")


def _scale_catalog(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, str]]:
    labels = sorted({str(value) for value in frame["Feature"]})
    seen: dict[str, str] = {}
    for label in labels:
        scale_id = sanitize_scale_id(label, existing=seen)
        seen[scale_id] = label
    definitions = [
        {
            "scale_id": scale_id,
            "label": label,
            "value_type": "integer",
            "unit": "score",
            "direction": "unknown",
            "subscales": [{"subscale_id": "total", "label": "Total"}],
        }
        for scale_id, label in sorted(seen.items())
    ]
    return definitions, {label: scale_id for scale_id, label in seen.items()}


def _validate_clinical(frame: pd.DataFrame) -> None:
    _require_columns(frame, {"ID", "Feature", "Condition", "Value", "Group"}, "clinical")
    if frame[["ID", "Feature", "Condition", "Value", "Group"]].isna().any().any():
        raise StudyBaseImportError("clinical source contains missing required cells")
    duplicates = frame.duplicated(["ID", "Feature", "Condition"], keep=False)
    if duplicates.any():
        raise StudyBaseImportError("duplicate clinical ID/Feature/Condition keys")
    for row_index, row in frame.iterrows():
        key = (str(row["Condition"]), str(row["Group"]))
        if key not in _CONDITION_MAP:
            raise StudyBaseImportError(f"unknown clinical Condition/Group at source row {row_index + 2}: {key}")
        value = row["Value"]
        if not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(float(value)) or not float(value).is_integer():
            raise StudyBaseImportError(f"clinical Value is not a finite integer at source row {row_index + 2}")


def _clinical_lookup(frame: pd.DataFrame) -> dict[tuple[str, str, str], int]:
    return {
        (str(row.ID), str(row.Feature), str(row.Condition)): int(row.Value)
        for row in frame.itertuples(index=False)
    }


def _program_skeletons(
    subject_id: str,
    scale_definitions: Sequence[Mapping[str, Any]],
    clinical: Mapping[tuple[str, str, str], int],
) -> dict[tuple[str, int], dict[str, Any]]:
    programs: dict[tuple[str, int], dict[str, Any]] = {}
    for (condition, _group), (phase_id, program_id, label, role, duration, order) in _PROGRAM_SPECS:
        observations = []
        for scale in scale_definitions:
            key = (subject_id, str(scale["label"]), condition)
            observed = key in clinical
            observations.append(
                {
                    "observation_id": f"{subject_id}__{phase_id.lower()}__program{program_id}__{scale['scale_id']}__total",
                    "scale_id": scale["scale_id"],
                    "subscale_id": "total",
                    "value": clinical[key] if observed else None,
                    "status": "observed" if observed else "not_assessed",
                }
            )
        programs[(phase_id, program_id)] = {
            "program_id": program_id,
            "program_label": label,
            "condition_role": role,
            "stimulation_state": "none" if role == "none" else "active",
            "assessment_order": order,
            "exposure": {
                "duration_label": duration,
                "stimulation_start_date": None,
                "assessment_date": None,
                "exposure_days": None,
            },
            "clinical_observations": observations,
            "electrode_programs": [],
        }
    return programs


def _finite_number(value: Any, label: str, source_row: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StudyBaseImportError(f"{label} is invalid at source row {source_row}") from exc
    if not math.isfinite(number):
        raise StudyBaseImportError(f"{label} is not finite at source row {source_row}")
    return number


def _validate_stimulation(frame: pd.DataFrame) -> None:
    required = {
        "ID", "NameEn", "Phase", "Protocol", "Contact", "Target", "Side",
        "Voltage", "PulseWidth", "Frequency", "StimulationPattern",
        "AlternatingGroup",
    }
    _require_columns(frame, required, "stimulation")
    nonnullable = sorted(required - {"AlternatingGroup"})
    if frame[nonnullable].isna().any().any():
        raise StudyBaseImportError("stimulation source contains missing required cells")
    if frame.duplicated(keep=False).any():
        raise StudyBaseImportError("duplicate stimulation rows are ambiguous")
    for row_index, row in frame.iterrows():
        source_row = int(row_index) + 2
        phase_protocol = (str(row["Phase"]), str(row["Protocol"]))
        if phase_protocol not in _PROGRAMMING_MAP:
            raise StudyBaseImportError(
                f"unknown programming Phase/Protocol at source row {source_row}: {phase_protocol}"
            )
        if str(row["Side"]) not in {"L", "R"}:
            raise StudyBaseImportError(
                f"unknown Side at source row {source_row}: {row['Side']}"
            )
        if str(row["Target"]) not in _TARGET_COMPONENT:
            raise StudyBaseImportError(
                f"unknown Target at source row {source_row}: {row['Target']}"
            )
        contact = _finite_number(row["Contact"], "Contact", source_row)
        if not contact.is_integer():
            raise StudyBaseImportError(
                f"Contact must be an integer at source row {source_row}"
            )


def _stimulation_programs(
    subject_id: str,
    frame: pd.DataFrame,
    electrodes: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    subject_rows = frame[frame["ID"].astype(str) == subject_id].copy()
    left_count = int(next(row["contact_count"] for row in electrodes if row["hemisphere"] == "L"))
    total_count = sum(int(row["contact_count"]) for row in electrodes)
    grouped_programs: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for (source_phase, protocol), program_key in _PROGRAMMING_MAP.items():
        rows = subject_rows[(subject_rows["Phase"] == source_phase) & (subject_rows["Protocol"] == protocol)].copy()
        if rows.empty:
            raise StudyBaseImportError(f"missing programming rows for subject {subject_id}, {source_phase}/{protocol}")
        electrode_programs = []
        for side in ("L", "R"):
            side_rows = rows[rows["Side"] == side].copy()
            if side_rows.empty:
                raise StudyBaseImportError(f"missing {side} programming rows for subject {subject_id}, {source_phase}/{protocol}")
            group_keys: list[tuple[str, str]] = []
            for row_index, row in side_rows.iterrows():
                mode = str(row["StimulationPattern"])
                if mode == "alternating":
                    alternating = row["AlternatingGroup"]
                    if pd.isna(alternating) or not str(alternating).strip():
                        raise StudyBaseImportError(f"alternating row without AlternatingGroup at source row {row_index + 2}")
                    key = (mode, str(alternating))
                elif mode == "continuous":
                    key = (mode, f"{float(row['Frequency']):g}")
                else:
                    raise StudyBaseImportError(f"unknown StimulationPattern at source row {row_index + 2}: {mode}")
                group_keys.append(key)
            side_rows["_group_key"] = group_keys
            frequency_groups = []
            for group_number, (group_key, group) in enumerate(side_rows.groupby("_group_key", sort=True), start=1):
                frequencies = sorted({_finite_number(value, "Frequency", int(index) + 2) for index, value in group["Frequency"].items()})
                if len(frequencies) != 1:
                    raise StudyBaseImportError(f"mixed frequencies in alternating group for subject {subject_id}")
                sources = []
                source_rows = []
                for row_index, row in group.iterrows():
                    target = str(row["Target"])
                    if target not in _TARGET_COMPONENT:
                        raise StudyBaseImportError(f"unknown Target at source row {row_index + 2}: {target}")
                    try:
                        contact = int(row["Contact"])
                    except (TypeError, ValueError) as exc:
                        raise StudyBaseImportError(f"invalid Contact at source row {row_index + 2}") from exc
                    valid = 0 <= contact < left_count if side == "L" else left_count <= contact < total_count
                    if not valid:
                        raise StudyBaseImportError(f"contact {contact} is outside {side} electrode range at source row {row_index + 2}")
                    source_rows.append((contact, int(row_index), row, target))
                for source_number, (contact, row_index, row, target) in enumerate(sorted(source_rows), start=1):
                    sources.append(
                        {
                            "source_id": f"source-{source_number}",
                            "source_label": target,
                            "component_id": _TARGET_COMPONENT[target],
                            "control_mode": "voltage",
                            "amplitude": _finite_number(row["Voltage"], "Voltage", row_index + 2),
                            "pulse_width_us": _finite_number(row["PulseWidth"], "PulseWidth", row_index + 2),
                            "contacts": [
                                {"contact": contact, "polarity": "cathode", "fraction": 1.0},
                                {"contact": "case", "polarity": "anode", "fraction": 1.0},
                            ],
                        }
                    )
                frequency_groups.append(
                    {
                        "frequency_group_id": f"group-{group_number}",
                        "frequency_hz": frequencies[0],
                        "delivery_mode": group_key[0],
                        "sources": sources,
                    }
                )
            electrode_programs.append({"electrode_id": f"lead-{side}", "frequency_groups": frequency_groups})
        grouped_programs[program_key] = electrode_programs
    return grouped_programs


def _asset_sources(asset_root: Path) -> dict[str, Any]:
    relative_paths = {
        "t1": "templates/space/MNI152NLin2009bAsym/t1.nii",
        "t2": "templates/space/MNI152NLin2009bAsym/t2.nii",
        "mask": "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz",
        "flip": "templates/space/MNI152NLin2009bAsym/fliplr/Composite.nii.gz",
        "ppmi": "connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat",
        "mgh": "connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat",
        "dtor": "connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat",
    }
    paths = {key: (asset_root / value).resolve() for key, value in relative_paths.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise StudyBaseImportError(f"missing study-level source file: {missing[0]}")
    connectome_specs = (
        ("ppmi_85_ewert_2017", "PPMI 85 (Ewert 2017)", paths["ppmi"]),
        ("mgh_usc_hcp_32_horn_2017", "MGH-USC HCP 32 (Horn 2017)", paths["mgh"]),
        ("dtor_985_full_elias_2024", "dTOR-985 Full (Elias 2024)", paths["dtor"]),
    )
    connectomes = []
    for connectome_id, label, streamlines in connectome_specs:
        metadata = streamlines.parent / "dataset_info.json"
        connectomes.append(
            {
                "connectome_id": connectome_id,
                "label": label,
                "space": "MNI152NLin2009bAsym",
                "modality": "diffusion",
                "representation": "streamlines",
                "streamlines": {"format": "leaddbs_data_mat_v7_3", "path": str(streamlines)},
                "metadata": {"path": str(metadata) if metadata.is_file() else None},
            }
        )
    return {
        "canonical_space": "MNI152NLin2009bAsym",
        "hemisphere_mapping": {
            "canonical_hemisphere": "R",
            "left_to_right_transform": {"path": str(paths["flip"])},
        },
        "reference_images": [
            {"image_id": "canonical_t1w", "modality": "T1w", "label": "MNI152NLin2009bAsym T1w", "path": str(paths["t1"])},
            {"image_id": "canonical_t2w", "modality": "T2w", "label": "MNI152NLin2009bAsym T2w", "path": str(paths["t2"])},
        ],
        "brainmask": {"brainmask_id": "mni152nlin2009basym_brainmask", "space": "MNI152NLin2009bAsym", "path": str(paths["mask"])},
        "connectomes": connectomes,
    }


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise StudyBaseImportError("created_at clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_commit(asset_root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=asset_root, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_study_base(
    clinical_workbook: str | Path,
    stimulation_workbook: str | Path,
    stimulation_sheet: str,
    leaddbs_root: str | Path,
    asset_root: str | Path,
    *,
    created_at: Callable[[], datetime] | None = None,
    code_commit: str | None = None,
) -> dict[str, Any]:
    """Build and semantically validate the STNSNr study-base payload."""
    clinical_path = Path(clinical_workbook).resolve()
    stimulation_path = Path(stimulation_workbook).resolve()
    reconstruction_root = Path(leaddbs_root).resolve()
    assets = Path(asset_root).resolve()
    clinical_frame = _read_excel(clinical_path)
    stimulation_frame = _read_excel(stimulation_path, sheet_name=stimulation_sheet)
    _validate_clinical(clinical_frame)
    _validate_stimulation(stimulation_frame)
    clinical_subjects = sorted(set(clinical_frame["ID"].astype(str)))
    stimulation_subjects = sorted(set(stimulation_frame["ID"].astype(str)))
    if clinical_subjects != stimulation_subjects:
        raise StudyBaseImportError("clinical/stimulation subject-set mismatch")
    scale_definitions, _ = _scale_catalog(clinical_frame)
    lookup = _clinical_lookup(clinical_frame)
    subjects = []
    for subject_id in clinical_subjects:
        reconstruction = reconstruction_root / f"sub-{subject_id}" / "reconstruction" / f"sub-{subject_id}_desc-reconstruction.mat"
        if not reconstruction.is_file():
            raise StudyBaseImportError(f"missing reconstruction for subject {subject_id}: {reconstruction}")
        electrodes = extract_electrodes(reconstruction)
        programs = _program_skeletons(subject_id, scale_definitions, lookup)
        stimulation_programs = _stimulation_programs(subject_id, stimulation_frame, electrodes)
        for key, electrode_programs in stimulation_programs.items():
            programs[key]["electrode_programs"] = electrode_programs
        phase_rows = []
        for phase_id, phase_label in (("T0", "Preoperative"), ("T1", "Immediate reference"), ("T2", "Reference 3m and combined immediate"), ("T3", "Combined 3m")):
            phase_programs = [program for (candidate_phase, _), program in programs.items() if candidate_phase == phase_id]
            phase_rows.append(
                {
                    "phase_id": phase_id,
                    "phase_label": phase_label,
                    "date": {"window_start_date": None, "window_end_date": None},
                    "programs": sorted(phase_programs, key=lambda row: (row["assessment_order"], row["program_id"])),
                }
            )
        names = sorted({str(value) for value in stimulation_frame.loc[stimulation_frame["ID"].astype(str) == subject_id, "NameEn"] if pd.notna(value)})
        if len(names) != 1:
            raise StudyBaseImportError(f"subject {subject_id} must have exactly one NameEn")
        subjects.append(
            {
                "subject_id": subject_id,
                "subject_label": names[0],
                "subject_sources": {"leaddbs_subject_dir": str(reconstruction.parent.parent), "electrode_reconstruction": {"path": str(reconstruction)}},
                "contact_numbering": {"convention": "bilateral_contiguous_zero_based", "electrode_order": ["lead-L", "lead-R"]},
                "electrodes": electrodes,
                "phases": phase_rows,
            }
        )
    now = created_at or (lambda: datetime.now(timezone.utc))
    payload = {
        "schema_version": "dual_frequency_study_v1",
        "study": {
            "study_id": "stnsnr_frequency_addon",
            "study_label": "STNSNr frequency add-on",
            "data_version": "1",
            "frequency_components": [
                {"component_id": "frequency_1_reference", "label": "HF"},
                {"component_id": "frequency_2_addon", "label": "ULF"},
            ],
            "scale_definitions": scale_definitions,
            "spot_model_sources": _asset_sources(assets),
            "subjects": subjects,
            "provenance": {
                "created_at": _utc_timestamp(now()),
                "importer": {"name": "build_stnsnr_study_base", "version": "1", "code_commit": code_commit if code_commit is not None else _git_commit(assets)},
                "source_files": [
                    {"role": "clinical", "path": str(clinical_path)},
                    {"role": "programming", "path": str(stimulation_path)},
                ],
                "notes": None,
            },
        },
    }
    _validate_semantics(payload)
    return payload


def _validate_semantics(payload: Mapping[str, Any]) -> None:
    study = payload["study"]
    scale_ids = [row["scale_id"] for row in study["scale_definitions"]]
    if len(scale_ids) != len(set(scale_ids)):
        raise StudyBaseImportError("duplicate scale_id")
    subject_ids = [row["subject_id"] for row in study["subjects"]]
    if len(subject_ids) != len(set(subject_ids)):
        raise StudyBaseImportError("duplicate subject_id")
    expected_programs = {
        "T0": [(0, "none", "preoperative", 0)],
        "T1": [(1, "reference_only", "immediate", 1)],
        "T2": [(1, "reference_only", "3m", 1), (2, "combined", "immediate", 2)],
        "T3": [(2, "combined", "3m", 1)],
    }
    observation_ids: set[str] = set()
    for subject in study["subjects"]:
        phases = subject["phases"]
        if [phase["phase_id"] for phase in phases] != ["T0", "T1", "T2", "T3"]:
            raise StudyBaseImportError("subject phase topology must be T0, T1, T2, T3")
        electrode_by_id = {row["electrode_id"]: row for row in subject["electrodes"]}
        expected_electrodes = {
            "lead-L": ("L", 2),
            "lead-R": ("R", 1),
        }
        if set(electrode_by_id) != set(expected_electrodes):
            raise StudyBaseImportError("subject electrode topology must be lead-L and lead-R")
        for electrode_id, (hemisphere, lead_id) in expected_electrodes.items():
            electrode = electrode_by_id[electrode_id]
            if (electrode["hemisphere"], electrode["reconstruction_lead_id"]) != (hemisphere, lead_id):
                raise StudyBaseImportError("electrode hemisphere/reconstruction lead mapping is invalid")
        left_count = int(electrode_by_id["lead-L"]["contact_count"])
        total_count = left_count + int(electrode_by_id["lead-R"]["contact_count"])
        for phase in subject["phases"]:
            topology = [
                (
                    program["program_id"],
                    program["condition_role"],
                    program["exposure"]["duration_label"],
                    program["assessment_order"],
                )
                for program in phase["programs"]
            ]
            if topology != expected_programs[phase["phase_id"]]:
                raise StudyBaseImportError(
                    f"program topology is invalid for phase {phase['phase_id']}"
                )
            for program in phase["programs"]:
                observed_scale_ids = [row["scale_id"] for row in program["clinical_observations"]]
                if observed_scale_ids != scale_ids:
                    raise StudyBaseImportError("program clinical observations do not match the scale catalog")
                for observation in program["clinical_observations"]:
                    if observation["observation_id"] in observation_ids:
                        raise StudyBaseImportError("duplicate observation_id")
                    observation_ids.add(observation["observation_id"])
                    expected_null = observation["status"] == "not_assessed"
                    if expected_null != (observation["value"] is None):
                        raise StudyBaseImportError("observation status/value mismatch")
                components = set()
                program_electrode_ids: list[str] = []
                for electrode_program in program["electrode_programs"]:
                    electrode_id = electrode_program["electrode_id"]
                    program_electrode_ids.append(electrode_id)
                    if electrode_id not in electrode_by_id:
                        raise StudyBaseImportError("electrode program references an unknown electrode")
                    group_ids: list[str] = []
                    for group in electrode_program["frequency_groups"]:
                        group_ids.append(group["frequency_group_id"])
                        source_ids: list[str] = []
                        for source in group["sources"]:
                            source_ids.append(source["source_id"])
                            component = source["component_id"]
                            components.add(component)
                            if _TARGET_COMPONENT.get(source["source_label"]) != component:
                                raise StudyBaseImportError("source label/component mapping is invalid")
                            contacts = source["contacts"]
                            cathodes = [row for row in contacts if row["polarity"] == "cathode"]
                            anodes = [row for row in contacts if row["polarity"] == "anode"]
                            if len(cathodes) != 1 or len(anodes) != 1 or anodes[0]["contact"] != "case":
                                raise StudyBaseImportError("source contact polarity structure is invalid")
                            contact = cathodes[0]["contact"]
                            valid = (
                                isinstance(contact, int)
                                and (
                                    0 <= contact < left_count
                                    if electrode_id == "lead-L"
                                    else left_count <= contact < total_count
                                )
                            )
                            if not valid:
                                raise StudyBaseImportError("source contact is outside its electrode range")
                        if len(source_ids) != len(set(source_ids)):
                            raise StudyBaseImportError("duplicate source_id within frequency group")
                    if len(group_ids) != len(set(group_ids)):
                        raise StudyBaseImportError("duplicate frequency_group_id within electrode program")
                if len(program_electrode_ids) != len(set(program_electrode_ids)):
                    raise StudyBaseImportError("duplicate electrode program")
                role = program["condition_role"]
                if role == "none" and (program["stimulation_state"] != "none" or components):
                    raise StudyBaseImportError("none program contains stimulation")
                if role == "reference_only" and components != {"frequency_1_reference"}:
                    raise StudyBaseImportError("reference_only program component closure failed")
                if role == "combined" and not {"frequency_1_reference", "frequency_2_addon"}.issubset(components):
                    raise StudyBaseImportError("combined program component closure failed")


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parents[4] / "stnsnr" / "study_base.schema.json"


def validate_study_base(payload: Mapping[str, Any], schema_path: str | Path | None = None) -> None:
    """Validate the document against JSON Schema and semantic constraints."""
    path = Path(schema_path) if schema_path is not None else _default_schema_path()
    schema = json.loads(path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise StudyBaseImportError(f"schema validation failed at {location}: {error.message}")
    _validate_semantics(payload)


def serialize_study_base(payload: Mapping[str, Any]) -> bytes:
    """Serialize strict JSON with stable formatting."""
    return (json.dumps(payload, indent=2, sort_keys=False, allow_nan=False) + "\n").encode("utf-8")


def write_study_base_atomic(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    force: bool = False,
    schema_path: str | Path | None = None,
) -> Path:
    """Validate and atomically write one study-base document."""
    destination = Path(path)
    if destination.exists() and not force:
        raise FileExistsError(f"output exists; pass force to replace it: {destination}")
    validate_study_base(payload, schema_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialize_study_base(payload))
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"output exists; pass force to replace it: {destination}"
                ) from exc
            temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def program_to_vta_spec(
    program: Mapping[str, Any],
    electrodes: Sequence[Mapping[str, Any]],
    *,
    component_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Adapt global zero-based study contacts to local one-based VTA contacts."""
    ordered = sorted(electrodes, key=lambda row: 0 if row["hemisphere"] == "L" else 1)
    offsets: dict[str, int] = {}
    offset = 0
    for electrode in ordered:
        offsets[str(electrode["electrode_id"])] = offset
        offset += int(electrode["contact_count"])
    result: dict[str, list[dict[str, Any]]] = {str(row["electrode_id"]): [] for row in ordered}
    for electrode_program in program["electrode_programs"]:
        electrode_id = str(electrode_program["electrode_id"])
        for group in electrode_program["frequency_groups"]:
            for source in group["sources"]:
                if component_id is not None and source["component_id"] != component_id:
                    continue
                converted = dict(source)
                converted["frequency_hz"] = group.get("frequency_hz")
                converted["delivery_mode"] = group.get("delivery_mode")
                converted["contacts"] = [
                    {
                        **contact,
                        "contact": contact["contact"] if contact["contact"] == "case" else int(contact["contact"]) - offsets[electrode_id] + 1,
                    }
                    for contact in source["contacts"]
                ]
                result[electrode_id].append(converted)
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the STNSNr importer command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clinical-workbook", type=Path, default=_DEFAULT_CLINICAL)
    parser.add_argument("--stimulation-workbook", type=Path, default=_DEFAULT_STIMULATION)
    parser.add_argument("--stimulation-sheet", default="Contact Parameters")
    parser.add_argument("--leaddbs-root", type=Path, default=_DEFAULT_LEADDBS_ROOT)
    parser.add_argument("--asset-root", type=Path, default=_DEFAULT_ASSET_ROOT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--schema", type=Path, default=_default_schema_path())
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the importer CLI."""
    args = build_parser().parse_args(argv)
    payload = build_study_base(
        clinical_workbook=args.clinical_workbook,
        stimulation_workbook=args.stimulation_workbook,
        stimulation_sheet=args.stimulation_sheet,
        leaddbs_root=args.leaddbs_root,
        asset_root=args.asset_root,
    )
    validate_study_base(payload, args.schema)
    if not args.validate_only:
        write_study_base_atomic(
            args.output,
            payload,
            force=args.force,
            schema_path=args.schema,
        )
    return 0
