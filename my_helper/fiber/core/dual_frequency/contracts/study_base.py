"""Read-only loading of the canonical dual-frequency study-base document."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_hash


_CONTACT_NUMBERING_CONVENTION = "bilateral_contiguous_zero_based"
_POLARITY_FRACTION_ABSOLUTE_TOLERANCE = 1e-9


class StudyBaseError(ValueError):
    """Raised when study-base schema or semantic validation fails."""


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    label: str


@dataclass(frozen=True)
class SubscaleDefinition:
    subscale_id: str
    label: str


@dataclass(frozen=True)
class ScaleDefinition:
    scale_id: str
    label: str
    value_type: str
    unit: str
    direction: str
    subscales: tuple[SubscaleDefinition, ...]


@dataclass(frozen=True)
class ConnectomeDefinition:
    connectome_id: str
    label: str
    space: str
    streamlines_path: Path
    metadata_path: Path | None


@dataclass(frozen=True)
class SpatialDefinition:
    canonical_space: str
    canonical_hemisphere: str
    left_to_right_transform: Path
    brainmask_id: str
    brainmask_path: Path
    connectomes: tuple[ConnectomeDefinition, ...]


@dataclass(frozen=True)
class ElectrodeDefinition:
    electrode_id: str
    hemisphere: str
    electrode_model: str
    contact_count: int
    reconstruction_lead_id: int


@dataclass(frozen=True)
class ContactRecord:
    contact: int | str
    polarity: str
    fraction: float


@dataclass(frozen=True)
class StimulationSource:
    subject_id: str
    phase_id: str
    program_id: int
    electrode_id: str
    frequency_group_id: str
    delivery_mode: str
    source_id: str
    source_label: str
    component_id: str
    frequency_hz: float
    control_mode: str
    amplitude: float
    pulse_width_us: float
    contacts: tuple[ContactRecord, ...]

    @property
    def identifier(self) -> str:
        return "source_" + canonical_hash(
            {
                "subject_id": self.subject_id,
                "phase_id": self.phase_id,
                "program_id": self.program_id,
                "electrode_id": self.electrode_id,
                "frequency_group_id": self.frequency_group_id,
                "source_id": self.source_id,
            },
            length=20,
        )


@dataclass(frozen=True)
class ClinicalObservation:
    observation_id: str
    subject_id: str
    phase_id: str
    program_id: int
    scale_id: str
    subscale_id: str
    value: int | None
    status: str


@dataclass(frozen=True)
class ProgramRecord:
    subject_id: str
    phase_id: str
    phase_label: str
    program_id: int
    program_label: str
    condition_role: str
    stimulation_state: str
    assessment_order: int
    duration_label: str
    stimulation_start_date: str | None
    assessment_date: str | None
    exposure_days: int | None
    observations: tuple[ClinicalObservation, ...]
    stimulation_sources: tuple[StimulationSource, ...]

    @property
    def identifier(self) -> str:
        return f"{self.subject_id}:{self.phase_id}:{self.program_id}"


@dataclass(frozen=True)
class SubjectRecord:
    subject_id: str
    subject_label: str
    leaddbs_subject_dir: Path
    electrode_reconstruction: Path
    electrodes: tuple[ElectrodeDefinition, ...]
    programs: tuple[ProgramRecord, ...]
    contact_numbering_convention: str = ""
    electrode_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class StudyBaseRecord:
    schema_version: str
    study_id: str
    study_label: str
    data_version: str
    components: tuple[ComponentDefinition, ...]
    scales: tuple[ScaleDefinition, ...]
    spatial: SpatialDefinition
    subjects: tuple[SubjectRecord, ...]
    source_path: Path
    source_sha256: str

    @property
    def scale_ids(self) -> tuple[str, ...]:
        return tuple(item.scale_id for item in self.scales)

    @property
    def subject_ids(self) -> tuple[str, ...]:
        return tuple(item.subject_id for item in self.subjects)

    @property
    def programs(self) -> tuple[ProgramRecord, ...]:
        return tuple(program for subject in self.subjects for program in subject.programs)

    @property
    def observations(self) -> tuple[ClinicalObservation, ...]:
        return tuple(observation for program in self.programs for observation in program.observations)

    @property
    def stimulation_sources(self) -> tuple[StimulationSource, ...]:
        return tuple(source for program in self.programs for source in program.stimulation_sources)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "schemas" / "study_base.schema.json"


def _schema_errors(payload: Mapping[str, object]) -> list[str]:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    output: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        output.append(f"{location}: {error.message}")
    return output


def _unique(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise StudyBaseError(f"duplicate {label} {value!r}")
        seen.add(value)


def _finite(value: object, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise StudyBaseError(f"{label} must be finite")
    return numeric


def _contact_ranges(
    subject_id: str,
    electrode_order: list[str],
    electrodes: Mapping[str, Mapping[str, object]],
) -> dict[str, range]:
    offset = 0
    ranges: dict[str, range] = {}
    for electrode_id in electrode_order:
        contact_count = int(electrodes[electrode_id]["contact_count"])
        ranges[electrode_id] = range(offset, offset + contact_count)
        offset += contact_count
    if not ranges:
        raise StudyBaseError(f"{subject_id} must declare at least one electrode")
    return ranges


def _validate_source_contacts(
    *,
    source: Mapping[str, object],
    source_context: str,
    electrode_id: str,
    valid_contacts: range,
) -> None:
    source_id = str(source["source_id"])
    contacts = source["contacts"]
    assert isinstance(contacts, list)
    contact_tokens = [contact["contact"] for contact in contacts]
    if len(contact_tokens) != len(set(contact_tokens)):
        raise StudyBaseError(f"{source_context} source {source_id!r} has duplicate contacts")

    polarity_fractions: dict[str, list[float]] = {"anode": [], "cathode": []}
    for contact in contacts:
        token = contact["contact"]
        if isinstance(token, int) and token not in valid_contacts:
            raise StudyBaseError(
                f"{source_context} source {source_id!r} contact {token} is outside "
                f"the {electrode_id!r} range "
                f"[{valid_contacts.start}, {valid_contacts.stop - 1}]"
            )
        fraction = _finite(
            contact["fraction"],
            f"{source_context} source {source_id} contact fraction",
        )
        polarity_fractions[str(contact["polarity"])].append(fraction)

    missing_polarities = [
        polarity for polarity, fractions in polarity_fractions.items() if not fractions
    ]
    if missing_polarities:
        raise StudyBaseError(
            f"{source_context} source {source_id!r} must include at least one "
            "anode and cathode"
        )
    for polarity, fractions in polarity_fractions.items():
        total = math.fsum(fractions)
        if not math.isclose(
            total,
            1.0,
            rel_tol=0.0,
            abs_tol=_POLARITY_FRACTION_ABSOLUTE_TOLERANCE,
        ):
            raise StudyBaseError(
                f"{source_context} source {source_id!r} {polarity} fractions "
                f"must sum to 1; got {total:.17g}"
            )


def validate_study_base(payload: Mapping[str, object]) -> None:
    """Validate the repository schema plus generic runtime semantics."""
    if not isinstance(payload, Mapping):
        raise StudyBaseError("study base must be a JSON object")
    schema_errors = _schema_errors(payload)
    if schema_errors:
        raise StudyBaseError(schema_errors[0])

    study = payload["study"]
    assert isinstance(study, Mapping)
    components = study["stimulation_components"]
    scales = study["scale_definitions"]
    subjects = study["subjects"]
    assert isinstance(components, list) and isinstance(scales, list) and isinstance(subjects, list)

    component_ids = [str(item["component_id"]) for item in components]
    _unique(component_ids, "component_id")
    component_labels = {str(item["component_id"]): str(item["label"]) for item in components}

    scale_ids = [str(item["scale_id"]) for item in scales]
    _unique(scale_ids, "scale_id")
    for scale in scales:
        if scale["direction"] not in {"lower", "higher"}:
            raise StudyBaseError(
                f"scale {scale['scale_id']!r} direction must be 'lower' or 'higher'"
            )

    subject_ids = [str(item["subject_id"]) for item in subjects]
    _unique(subject_ids, "subject_id")
    observation_ids: list[str] = []
    for subject in subjects:
        subject_id = str(subject["subject_id"])
        electrode_ids = [str(item["electrode_id"]) for item in subject["electrodes"]]
        _unique(electrode_ids, f"electrode_id for {subject_id}")
        contact_numbering = subject["contact_numbering"]
        convention = str(contact_numbering["convention"])
        if convention != _CONTACT_NUMBERING_CONVENTION:
            raise StudyBaseError(
                f"{subject_id} contact numbering convention {convention!r} is unsupported"
            )
        electrode_order = [str(item) for item in contact_numbering["electrode_order"]]
        _unique(electrode_order, f"electrode_order for {subject_id}")
        if len(electrode_order) != len(electrode_ids) or set(electrode_order) != set(
            electrode_ids
        ):
            missing = sorted(set(electrode_ids) - set(electrode_order))
            extra = sorted(set(electrode_order) - set(electrode_ids))
            raise StudyBaseError(
                f"{subject_id} electrode_order must contain every declared electrode "
                f"exactly once; missing={missing}, extra={extra}"
            )
        electrode_definitions = {
            str(item["electrode_id"]): item for item in subject["electrodes"]
        }
        contact_ranges = _contact_ranges(
            subject_id,
            electrode_order,
            electrode_definitions,
        )
        phase_ids = [str(item["phase_id"]) for item in subject["phases"]]
        _unique(phase_ids, f"phase_id for {subject_id}")
        for phase in subject["phases"]:
            phase_id = str(phase["phase_id"])
            program_ids = [str(item["program_id"]) for item in phase["programs"]]
            _unique(program_ids, f"program_id for {subject_id}/{phase_id}")
            for program in phase["programs"]:
                program_id = int(program["program_id"])
                observations = program["clinical_observations"]
                program_scale_ids = [str(item["scale_id"]) for item in observations]
                _unique(program_scale_ids, f"observation scale for {subject_id}/{phase_id}/{program_id}")
                if program_scale_ids != scale_ids:
                    missing = sorted(set(scale_ids) - set(program_scale_ids))
                    extra = sorted(set(program_scale_ids) - set(scale_ids))
                    order_detail = ""
                    if not missing and not extra:
                        order_detail = "; observation order differs from scale_definitions"
                    raise StudyBaseError(
                        f"{subject_id}/{phase_id}/{program_id} observation scale closure failed; "
                        f"missing={missing}, extra={extra}{order_detail}"
                    )
                for observation in observations:
                    observation_ids.append(str(observation["observation_id"]))
                    if observation["status"] == "observed":
                        _finite(
                            observation["value"],
                            f"observation {observation['observation_id']} value",
                        )

                program_electrodes = [str(item["electrode_id"]) for item in program["electrode_programs"]]
                _unique(program_electrodes, f"electrode program for {subject_id}/{phase_id}/{program_id}")
                unknown_electrodes = sorted(set(program_electrodes) - set(electrode_ids))
                if unknown_electrodes:
                    raise StudyBaseError(
                        f"{subject_id}/{phase_id}/{program_id} references unknown electrodes {unknown_electrodes}"
                    )
                for electrode_program in program["electrode_programs"]:
                    electrode_id = str(electrode_program["electrode_id"])
                    group_ids = [str(item["frequency_group_id"]) for item in electrode_program["frequency_groups"]]
                    _unique(
                        group_ids,
                        f"frequency_group_id for {subject_id}/{phase_id}/{program_id}/{electrode_id}",
                    )
                    for group in electrode_program["frequency_groups"]:
                        group_sources = group["sources"]
                        group_source_ids = [str(item["source_id"]) for item in group_sources]
                        _unique(
                            group_source_ids,
                            f"source_id for {subject_id}/{phase_id}/{program_id}/"
                            f"{electrode_id}/{group['frequency_group_id']}",
                        )
                        frequencies = {
                            _finite(
                                item["frequency_hz"],
                                f"source {item['source_id']} frequency_hz",
                            )
                            for item in group_sources
                        }
                        control_modes = {str(item["control_mode"]) for item in group_sources}
                        if len(frequencies) != 1:
                            raise StudyBaseError(
                                f"frequency group {group['frequency_group_id']!r} must use one frequency"
                            )
                        if len(control_modes) != 1:
                            raise StudyBaseError(
                                f"frequency group {group['frequency_group_id']!r} cannot mix control modes"
                            )
                        for source in group_sources:
                            source_id = str(source["source_id"])
                            component_id = str(source["component_id"])
                            if component_id not in component_labels:
                                raise StudyBaseError(f"source {source_id!r} references unknown component")
                            if str(source["source_label"]) != component_labels[component_id]:
                                raise StudyBaseError(f"source {source_id!r} label does not match component")
                            _finite(source["amplitude"], f"source {source_id} amplitude")
                            _finite(source["pulse_width_us"], f"source {source_id} pulse_width_us")
                            _validate_source_contacts(
                                source=source,
                                source_context=(
                                    f"{subject_id}/{phase_id}/{program_id}/"
                                    f"{electrode_id}/{group['frequency_group_id']}"
                                ),
                                electrode_id=electrode_id,
                                valid_contacts=contact_ranges[electrode_id],
                            )

    _unique(observation_ids, "observation_id")


def _path(value: object, base_directory: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve()


def _program_record(subject_id: str, phase: Mapping[str, Any], program: Mapping[str, Any]) -> ProgramRecord:
    phase_id = str(phase["phase_id"])
    program_id = int(program["program_id"])
    observations = tuple(
        ClinicalObservation(
            observation_id=str(item["observation_id"]),
            subject_id=subject_id,
            phase_id=phase_id,
            program_id=program_id,
            scale_id=str(item["scale_id"]),
            subscale_id=str(item["subscale_id"]),
            value=int(item["value"]) if item["value"] is not None else None,
            status=str(item["status"]),
        )
        for item in program["clinical_observations"]
    )
    sources: list[StimulationSource] = []
    for electrode_program in program["electrode_programs"]:
        electrode_id = str(electrode_program["electrode_id"])
        for group in electrode_program["frequency_groups"]:
            for item in group["sources"]:
                sources.append(
                    StimulationSource(
                        subject_id=subject_id,
                        phase_id=phase_id,
                        program_id=program_id,
                        electrode_id=electrode_id,
                        frequency_group_id=str(group["frequency_group_id"]),
                        delivery_mode=str(group["delivery_mode"]),
                        source_id=str(item["source_id"]),
                        source_label=str(item["source_label"]),
                        component_id=str(item["component_id"]),
                        frequency_hz=float(item["frequency_hz"]),
                        control_mode=str(item["control_mode"]),
                        amplitude=float(item["amplitude"]),
                        pulse_width_us=float(item["pulse_width_us"]),
                        contacts=tuple(
                            ContactRecord(
                                contact=contact["contact"],
                                polarity=str(contact["polarity"]),
                                fraction=float(contact["fraction"]),
                            )
                            for contact in item["contacts"]
                        ),
                    )
                )
    exposure = program["exposure"]
    return ProgramRecord(
        subject_id=subject_id,
        phase_id=phase_id,
        phase_label=str(phase["phase_label"]),
        program_id=program_id,
        program_label=str(program["program_label"]),
        condition_role=str(program["condition_role"]),
        stimulation_state=str(program["stimulation_state"]),
        assessment_order=int(program["assessment_order"]),
        duration_label=str(exposure["duration_label"]),
        stimulation_start_date=exposure["stimulation_start_date"],
        assessment_date=exposure["assessment_date"],
        exposure_days=int(exposure["exposure_days"]) if exposure["exposure_days"] is not None else None,
        observations=observations,
        stimulation_sources=tuple(sources),
    )


def _study_record(payload: Mapping[str, Any], source_path: Path, source_sha256: str) -> StudyBaseRecord:
    study = payload["study"]
    spot = study["spot_model_sources"]
    base_directory = source_path.parent
    spatial = SpatialDefinition(
        canonical_space=str(spot["canonical_space"]),
        canonical_hemisphere=str(spot["hemisphere_mapping"]["canonical_hemisphere"]),
        left_to_right_transform=_path(
            spot["hemisphere_mapping"]["left_to_right_transform"]["path"],
            base_directory,
        ),
        brainmask_id=str(spot["brainmask"]["brainmask_id"]),
        brainmask_path=_path(spot["brainmask"]["path"], base_directory),
        connectomes=tuple(
            ConnectomeDefinition(
                connectome_id=str(item["connectome_id"]),
                label=str(item["label"]),
                space=str(item["space"]),
                streamlines_path=_path(item["streamlines"]["path"], base_directory),
                metadata_path=(
                    _path(item["metadata"]["path"], base_directory)
                    if item["metadata"]["path"] is not None
                    else None
                ),
            )
            for item in spot["connectomes"]
        ),
    )
    subjects = tuple(
        SubjectRecord(
            subject_id=str(subject["subject_id"]),
            subject_label=str(subject["subject_label"]),
            leaddbs_subject_dir=_path(
                subject["subject_sources"]["leaddbs_subject_dir"],
                base_directory,
            ),
            electrode_reconstruction=_path(
                subject["subject_sources"]["electrode_reconstruction"]["path"],
                base_directory,
            ),
            electrodes=tuple(
                ElectrodeDefinition(
                    electrode_id=str(item["electrode_id"]),
                    hemisphere=str(item["hemisphere"]),
                    electrode_model=str(item["electrode_model"]),
                    contact_count=int(item["contact_count"]),
                    reconstruction_lead_id=int(item["reconstruction_lead_id"]),
                )
                for item in subject["electrodes"]
            ),
            programs=tuple(
                _program_record(str(subject["subject_id"]), phase, program)
                for phase in subject["phases"]
                for program in phase["programs"]
            ),
            contact_numbering_convention=str(subject["contact_numbering"]["convention"]),
            electrode_order=tuple(
                str(item) for item in subject["contact_numbering"]["electrode_order"]
            ),
        )
        for subject in study["subjects"]
    )
    return StudyBaseRecord(
        schema_version=str(payload["schema_version"]),
        study_id=str(study["study_id"]),
        study_label=str(study["study_label"]),
        data_version=str(study["data_version"]),
        components=tuple(
            ComponentDefinition(component_id=str(item["component_id"]), label=str(item["label"]))
            for item in study["stimulation_components"]
        ),
        scales=tuple(
            ScaleDefinition(
                scale_id=str(item["scale_id"]),
                label=str(item["label"]),
                value_type=str(item["value_type"]),
                unit=str(item["unit"]),
                direction=str(item["direction"]),
                subscales=tuple(
                    SubscaleDefinition(
                        subscale_id=str(subscale["subscale_id"]),
                        label=str(subscale["label"]),
                    )
                    for subscale in item["subscales"]
                ),
            )
            for item in study["scale_definitions"]
        ),
        spatial=spatial,
        subjects=subjects,
        source_path=source_path,
        source_sha256=source_sha256,
    )


def load_study_base(path: Path) -> StudyBaseRecord:
    """Load, validate, and freeze an existing study-base JSON file."""
    source_path = Path(path).expanduser().resolve()
    try:
        content = source_path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudyBaseError(f"failed to read {source_path}: {exc}") from exc
    validate_study_base(payload)
    return _study_record(payload, source_path, hashlib.sha256(content).hexdigest())
