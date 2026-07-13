"""Immutable canonical records used by the VTA planner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Hemisphere = Literal["L", "R"]
ControlMode = Literal["voltage", "current"]
DeliveryMode = Literal["continuous", "alternating"]
Polarity = Literal["cathode", "anode"]


@dataclass(frozen=True)
class ContactRecord:
    contact: int | Literal["case"]
    polarity: Polarity
    fraction: float


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    frequency_hz: float
    control_mode: ControlMode
    amplitude: float
    pulse_width_us: float
    contacts: tuple[ContactRecord, ...]


@dataclass(frozen=True)
class FrequencyGroupRecord:
    frequency_group_id: str
    delivery_mode: DeliveryMode
    control_mode: ControlMode
    frequency_hz: float
    sources: tuple[SourceRecord, ...]


@dataclass(frozen=True)
class ElectrodeProgramRecord:
    electrode_id: str
    hemisphere: Hemisphere
    electrode_model: str
    reconstruction_lead_id: int
    groups: tuple[FrequencyGroupRecord, ...]


@dataclass(frozen=True)
class ProgramRecord:
    phase_id: str
    program_id: int
    electrodes: tuple[ElectrodeProgramRecord, ...]


@dataclass(frozen=True)
class SubjectRecord:
    subject_id: str
    subject_label: str
    subject_dir: Path
    reconstruction_path: Path
    programs: tuple[ProgramRecord, ...]


@dataclass(frozen=True)
class StudyBase:
    schema_version: str
    source_path: Path
    subjects: tuple[SubjectRecord, ...]

    def vta_semantic_payload(self) -> dict[str, object]:
        """Return only fields that can affect VTA task generation."""

        return {
            "schema_version": self.schema_version,
            "subjects": [
                {
                    "subject_id": subject.subject_id,
                    "subject_dir": str(subject.subject_dir),
                    "reconstruction_path": str(subject.reconstruction_path),
                    "programs": [
                        {
                            "phase_id": program.phase_id,
                            "program_id": program.program_id,
                            "electrodes": [
                                {
                                    "electrode_id": electrode.electrode_id,
                                    "hemisphere": electrode.hemisphere,
                                    "electrode_model": electrode.electrode_model,
                                    "reconstruction_lead_id": (
                                        electrode.reconstruction_lead_id
                                    ),
                                    "groups": [
                                        {
                                            "frequency_group_id": (
                                                group.frequency_group_id
                                            ),
                                            "delivery_mode": group.delivery_mode,
                                            "control_mode": group.control_mode,
                                            "frequency_hz": group.frequency_hz,
                                            "sources": [
                                                {
                                                    "source_id": source.source_id,
                                                    "frequency_hz": source.frequency_hz,
                                                    "control_mode": source.control_mode,
                                                    "amplitude": source.amplitude,
                                                    "pulse_width_us": (
                                                        source.pulse_width_us
                                                    ),
                                                    "contacts": [
                                                        {
                                                            "contact": contact.contact,
                                                            "polarity": contact.polarity,
                                                            "fraction": contact.fraction,
                                                        }
                                                        for contact in source.contacts
                                                    ],
                                                }
                                                for source in group.sources
                                            ],
                                        }
                                        for group in electrode.groups
                                    ],
                                }
                                for electrode in program.electrodes
                            ],
                        }
                        for program in subject.programs
                    ],
                }
                for subject in self.subjects
            ],
        }
