"""Adapter from canonical study-base JSON to VTA records."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .errors import StudyBaseError
from .records import (
    ContactRecord,
    ElectrodeProgramRecord,
    FrequencyGroupRecord,
    ProgramRecord,
    SourceRecord,
    StudyBase,
    SubjectRecord,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FRACTION_TOLERANCE = 1e-9


def load_study_base(path: Path | str) -> StudyBase:
    """Load the VTA-relevant subset of a canonical study-base document."""

    source_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        if raw["schema_version"] != "dual_frequency_study_v1":
            raise StudyBaseError("Unsupported study-base schema_version")
        subjects_raw = raw["study"]["subjects"]
        subjects = tuple(
            _parse_subject(subject, source_path.parent) for subject in subjects_raw
        )
    except StudyBaseError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyBaseError(f"Unable to read study base: {source_path}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise StudyBaseError(f"Invalid study-base structure: {exc}") from exc

    if not subjects:
        raise StudyBaseError("Study base must contain at least one subject")
    if len({subject.subject_id for subject in subjects}) != len(subjects):
        raise StudyBaseError("subject_id values must be unique")
    return StudyBase(
        schema_version="dual_frequency_study_v1",
        source_path=source_path,
        subjects=subjects,
    )


def _parse_subject(raw: Mapping[str, Any], base: Path) -> SubjectRecord:
    subject_id = _safe_id(raw["subject_id"], "subject_id")
    subject_label = str(raw.get("subject_label", subject_id))
    sources = raw["subject_sources"]
    subject_dir = _resolve_path(sources["leaddbs_subject_dir"], base)
    reconstruction_path = _resolve_path(
        sources["electrode_reconstruction"]["path"], base
    )
    if not subject_dir.is_dir():
        raise StudyBaseError(f"subject directory does not exist: {subject_dir}")
    if not reconstruction_path.is_file():
        raise StudyBaseError(
            f"reconstruction does not exist: {reconstruction_path}"
        )

    electrode_defs = _parse_electrode_definitions(raw["electrodes"])
    numbering = raw["contact_numbering"]
    if numbering["convention"] != "bilateral_contiguous_zero_based":
        raise StudyBaseError("Unsupported contact_numbering convention")
    electrode_order = tuple(numbering["electrode_order"])
    if set(electrode_order) != set(electrode_defs):
        raise StudyBaseError("electrode_order must contain every electrode exactly once")

    programs: list[ProgramRecord] = []
    for phase in raw["phases"]:
        phase_id = _safe_id(phase["phase_id"], "phase_id")
        for program in phase["programs"]:
            programs.append(
                _parse_program(
                    phase_id,
                    program,
                    electrode_defs,
                    electrode_order,
                )
            )

    return SubjectRecord(
        subject_id=subject_id,
        subject_label=subject_label,
        subject_dir=subject_dir,
        reconstruction_path=reconstruction_path,
        programs=tuple(programs),
    )


def _parse_electrode_definitions(
    electrodes: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for electrode in electrodes:
        electrode_id = _safe_id(electrode["electrode_id"], "electrode_id")
        if electrode_id in parsed:
            raise StudyBaseError(f"duplicate electrode_id: {electrode_id}")
        hemisphere = str(electrode["hemisphere"])
        if hemisphere not in {"L", "R"}:
            raise StudyBaseError(f"invalid hemisphere: {hemisphere}")
        contact_count = electrode["contact_count"]
        if isinstance(contact_count, bool) or not isinstance(contact_count, int):
            raise StudyBaseError("contact_count must be an integer")
        if contact_count <= 0:
            raise StudyBaseError("contact_count must be positive")
        reconstruction_lead_id = electrode["reconstruction_lead_id"]
        if (
            isinstance(reconstruction_lead_id, bool)
            or not isinstance(reconstruction_lead_id, int)
            or reconstruction_lead_id <= 0
        ):
            raise StudyBaseError("reconstruction_lead_id must be a positive integer")
        parsed[electrode_id] = {
            "hemisphere": hemisphere,
            "electrode_model": str(electrode["electrode_model"]),
            "contact_count": contact_count,
            "reconstruction_lead_id": reconstruction_lead_id,
        }
    if not parsed:
        raise StudyBaseError("subject must define at least one electrode")
    return parsed


def _parse_program(
    phase_id: str,
    raw: Mapping[str, Any],
    electrode_defs: Mapping[str, Mapping[str, Any]],
    electrode_order: tuple[str, ...],
) -> ProgramRecord:
    program_id = raw["program_id"]
    if isinstance(program_id, bool) or not isinstance(program_id, int):
        raise StudyBaseError("program_id must be an integer")
    electrode_programs = tuple(
        _parse_electrode_program(
            item,
            electrode_defs,
            electrode_order,
        )
        for item in raw.get("electrode_programs", [])
    )
    if len({item.electrode_id for item in electrode_programs}) != len(
        electrode_programs
    ):
        raise StudyBaseError("program contains duplicate electrode_id values")
    return ProgramRecord(
        phase_id=phase_id,
        program_id=program_id,
        electrodes=electrode_programs,
    )


def _parse_electrode_program(
    raw: Mapping[str, Any],
    electrode_defs: Mapping[str, Mapping[str, Any]],
    electrode_order: tuple[str, ...],
) -> ElectrodeProgramRecord:
    electrode_id = _safe_id(raw["electrode_id"], "electrode_id")
    if electrode_id not in electrode_defs:
        raise StudyBaseError(f"unknown electrode_id: {electrode_id}")
    definition = electrode_defs[electrode_id]
    contact_counts = {
        key: int(value["contact_count"]) for key, value in electrode_defs.items()
    }
    groups = tuple(
        _parse_group(
            group,
            electrode_id,
            electrode_order,
            contact_counts,
        )
        for group in raw.get("frequency_groups", [])
    )
    if len({group.frequency_group_id for group in groups}) != len(groups):
        raise StudyBaseError("frequency_group_id values must be unique per electrode")
    return ElectrodeProgramRecord(
        electrode_id=electrode_id,
        hemisphere=definition["hemisphere"],
        electrode_model=definition["electrode_model"],
        reconstruction_lead_id=definition["reconstruction_lead_id"],
        groups=groups,
    )


def _parse_group(
    raw: Mapping[str, Any],
    electrode_id: str,
    electrode_order: tuple[str, ...],
    contact_counts: Mapping[str, int],
) -> FrequencyGroupRecord:
    group_id = _safe_id(raw["frequency_group_id"], "frequency_group_id")
    delivery_mode = str(raw["delivery_mode"])
    if delivery_mode not in {"continuous", "alternating"}:
        raise StudyBaseError(f"invalid delivery_mode: {delivery_mode}")
    sources = tuple(
        _parse_source(source, electrode_id, electrode_order, contact_counts)
        for source in raw["sources"]
    )
    if not sources:
        raise StudyBaseError(f"frequency group {group_id} has no sources")
    if len({source.source_id for source in sources}) != len(sources):
        raise StudyBaseError(f"duplicate source_id in frequency group {group_id}")
    control_modes = {source.control_mode for source in sources}
    if len(control_modes) != 1:
        raise StudyBaseError(
            f"frequency group {group_id} must use homogeneous control_mode"
        )
    frequencies = {source.frequency_hz for source in sources}
    if len(frequencies) != 1:
        raise StudyBaseError(
            f"frequency group {group_id} must use one frequency_hz"
        )
    if delivery_mode == "continuous":
        _validate_continuous_contact_ownership(group_id, sources)
    return FrequencyGroupRecord(
        frequency_group_id=group_id,
        delivery_mode=delivery_mode,
        control_mode=next(iter(control_modes)),
        frequency_hz=next(iter(frequencies)),
        sources=sources,
    )


def _parse_source(
    raw: Mapping[str, Any],
    electrode_id: str,
    electrode_order: tuple[str, ...],
    contact_counts: Mapping[str, int],
) -> SourceRecord:
    source_id = _safe_id(raw["source_id"], "source_id")
    frequency_hz = _positive_finite(raw["frequency_hz"], "frequency_hz")
    amplitude = _positive_finite(raw["amplitude"], "amplitude")
    pulse_width_us = _positive_finite(raw["pulse_width_us"], "pulse_width_us")
    control_mode = str(raw["control_mode"])
    if control_mode not in {"voltage", "current"}:
        raise StudyBaseError(f"invalid control_mode: {control_mode}")
    contacts = tuple(
        _parse_contact(contact, electrode_id, electrode_order, contact_counts)
        for contact in raw["contacts"]
    )
    _validate_source_contacts(source_id, contacts)
    return SourceRecord(
        source_id=source_id,
        frequency_hz=frequency_hz,
        control_mode=control_mode,
        amplitude=amplitude,
        pulse_width_us=pulse_width_us,
        contacts=contacts,
    )


def _parse_contact(
    raw: Mapping[str, Any],
    electrode_id: str,
    electrode_order: tuple[str, ...],
    contact_counts: Mapping[str, int],
) -> ContactRecord:
    raw_contact = raw["contact"]
    if raw_contact == "case":
        contact: int | str = "case"
    elif isinstance(raw_contact, int) and not isinstance(raw_contact, bool):
        contact = _to_side_local_contact(
            raw_contact,
            electrode_id,
            electrode_order,
            contact_counts,
        )
    else:
        raise StudyBaseError(f"invalid contact: {raw_contact}")
    polarity = str(raw["polarity"])
    if polarity not in {"cathode", "anode"}:
        raise StudyBaseError(f"invalid polarity: {polarity}")
    fraction = _positive_finite(raw["fraction"], "contact fraction")
    return ContactRecord(contact=contact, polarity=polarity, fraction=fraction)


def _to_side_local_contact(
    global_contact: int,
    electrode_id: str,
    electrode_order: tuple[str, ...],
    contact_counts: Mapping[str, int],
) -> int:
    electrode_index = electrode_order.index(electrode_id)
    offset = sum(contact_counts[item] for item in electrode_order[:electrode_index])
    local_zero_based = global_contact - offset
    if not 0 <= local_zero_based < contact_counts[electrode_id]:
        raise StudyBaseError(
            f"contact {global_contact} is outside electrode {electrode_id} range"
        )
    return local_zero_based + 1


def _validate_source_contacts(
    source_id: str,
    contacts: tuple[ContactRecord, ...],
) -> None:
    if not contacts:
        raise StudyBaseError(f"source {source_id} has no contacts")
    keys = [(contact.contact, contact.polarity) for contact in contacts]
    if len(set(keys)) != len(keys):
        raise StudyBaseError(f"source {source_id} contains duplicate contacts")
    for polarity in ("cathode", "anode"):
        total = sum(
            contact.fraction for contact in contacts if contact.polarity == polarity
        )
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_FRACTION_TOLERANCE):
            raise StudyBaseError(
                f"source {source_id} {polarity} fractions must sum to 1"
            )


def _validate_continuous_contact_ownership(
    group_id: str,
    sources: tuple[SourceRecord, ...],
) -> None:
    owners: dict[int, str] = {}
    for source in sources:
        for contact in source.contacts:
            if contact.contact == "case":
                continue
            owner = owners.get(contact.contact)
            if owner is not None and owner != source.source_id:
                raise StudyBaseError(
                    f"continuous group {group_id} reuses contact {contact.contact}"
                )
            owners[contact.contact] = source.source_id


def _positive_finite(value: Any, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise StudyBaseError(f"{field} must be finite and positive")
    return number


def _safe_id(value: Any, field: str) -> str:
    identifier = str(value)
    if _SAFE_ID.fullmatch(identifier) is None:
        raise StudyBaseError(f"unsafe {field}: {identifier}")
    return identifier


def _resolve_path(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
