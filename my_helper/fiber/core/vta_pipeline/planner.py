"""Deterministic VTA task DAG construction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Literal

from .config import VtaModelConfig
from .errors import PlanningError
from .records import SourceRecord, StudyBase, SubjectRecord


class TaskKind(str, Enum):
    CONTINUOUS_JOINT = "continuous_joint"
    ALTERNATING_SOURCE = "alternating_source"
    ALTERNATING_GROUP_PEAK = "alternating_group_peak"


@dataclass(frozen=True)
class Selection:
    subject_ids: tuple[str, ...] = ()
    all_subjects: bool = False
    phase_ids: tuple[str, ...] = ()
    program_ids: tuple[int, ...] = ()
    electrode_ids: tuple[str, ...] = ()
    frequency_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VtaTask:
    task_id: str
    kind: TaskKind
    subject_id: str
    subject_dir: Path
    reconstruction_path: Path
    phase_id: str
    program_id: int
    electrode_id: str
    hemisphere: Literal["L", "R"]
    electrode_model: str
    reconstruction_lead_id: int
    frequency_group_id: str
    delivery_mode: Literal["continuous", "alternating"]
    sources: tuple[SourceRecord, ...]
    group_sources: tuple[SourceRecord, ...]
    dependencies: tuple[str, ...]
    model: VtaModelConfig

    def to_payload(self) -> dict[str, object]:
        payload = _task_payload_without_id(
            kind=self.kind,
            subject_id=self.subject_id,
            subject_dir=self.subject_dir,
            reconstruction_path=self.reconstruction_path,
            phase_id=self.phase_id,
            program_id=self.program_id,
            electrode_id=self.electrode_id,
            hemisphere=self.hemisphere,
            electrode_model=self.electrode_model,
            reconstruction_lead_id=self.reconstruction_lead_id,
            frequency_group_id=self.frequency_group_id,
            delivery_mode=self.delivery_mode,
            sources=self.sources,
            dependencies=self.dependencies,
            model=self.model,
        )
        return {"task_id": self.task_id, **payload}


@dataclass(frozen=True)
class SubjectPlan:
    subject_id: str
    subject_dir: Path
    headmodel_sides: tuple[Literal["L", "R"], ...]
    tasks: tuple[VtaTask, ...]
    reuse_candidates: tuple[VtaTask, ...] = ()


def build_plan(
    study: StudyBase,
    model: VtaModelConfig,
    selection: Selection,
) -> tuple[SubjectPlan, ...]:
    """Build a deterministic subject-level VTA execution plan."""

    selected_subjects = _select_subjects(study, selection)
    _validate_selectors(selected_subjects, selection)
    plans: list[SubjectPlan] = []
    for subject in selected_subjects:
        reuse_candidates = tuple(_subject_tasks(subject, model, Selection()))
        tasks = _subject_tasks(subject, model, selection)
        if not tasks:
            continue
        sides = tuple(sorted({task.hemisphere for task in tasks}))
        plans.append(
            SubjectPlan(
                subject_id=subject.subject_id,
                subject_dir=subject.subject_dir,
                headmodel_sides=sides,
                tasks=tuple(tasks),
                reuse_candidates=reuse_candidates,
            )
        )
    if not plans:
        raise PlanningError("Selection produced no VTA solve tasks")
    return tuple(plans)


def _select_subjects(
    study: StudyBase,
    selection: Selection,
) -> tuple[SubjectRecord, ...]:
    if selection.all_subjects == bool(selection.subject_ids):
        raise PlanningError("Specify exactly one subject selection mode")
    available = {subject.subject_id: subject for subject in study.subjects}
    if selection.all_subjects:
        return tuple(sorted(study.subjects, key=lambda item: item.subject_id))
    unknown = sorted(set(selection.subject_ids) - set(available))
    if unknown:
        raise PlanningError(f"Unknown subject selector: {unknown[0]}")
    return tuple(available[item] for item in sorted(set(selection.subject_ids)))


def _validate_selectors(
    subjects: tuple[SubjectRecord, ...],
    selection: Selection,
) -> None:
    phase_ids = {program.phase_id for subject in subjects for program in subject.programs}
    program_ids = {
        program.program_id for subject in subjects for program in subject.programs
    }
    electrode_ids = {
        electrode.electrode_id
        for subject in subjects
        for program in subject.programs
        for electrode in program.electrodes
    }
    group_ids = {
        group.frequency_group_id
        for subject in subjects
        for program in subject.programs
        for electrode in program.electrodes
        for group in electrode.groups
    }
    _reject_unknown("phase", selection.phase_ids, phase_ids)
    _reject_unknown("program", selection.program_ids, program_ids)
    _reject_unknown("electrode", selection.electrode_ids, electrode_ids)
    _reject_unknown(
        "frequency-group",
        selection.frequency_group_ids,
        group_ids,
    )


def _reject_unknown(label: str, requested: tuple, available: set) -> None:
    unknown = sorted(set(requested) - available)
    if unknown:
        raise PlanningError(f"Unknown {label} selector: {unknown[0]}")


def _subject_tasks(
    subject: SubjectRecord,
    model: VtaModelConfig,
    selection: Selection,
) -> list[VtaTask]:
    tasks: list[VtaTask] = []
    programs = sorted(
        subject.programs,
        key=lambda item: (item.phase_id, item.program_id),
    )
    for program in programs:
        if selection.phase_ids and program.phase_id not in selection.phase_ids:
            continue
        if selection.program_ids and program.program_id not in selection.program_ids:
            continue
        for electrode in sorted(program.electrodes, key=lambda item: item.electrode_id):
            if (
                selection.electrode_ids
                and electrode.electrode_id not in selection.electrode_ids
            ):
                continue
            for group in sorted(
                electrode.groups,
                key=lambda item: item.frequency_group_id,
            ):
                if (
                    selection.frequency_group_ids
                    and group.frequency_group_id not in selection.frequency_group_ids
                ):
                    continue
                shared = {
                    "subject": subject,
                    "program": program,
                    "electrode": electrode,
                    "group_id": group.frequency_group_id,
                    "group_sources": tuple(
                        sorted(group.sources, key=lambda item: item.source_id)
                    ),
                    "model": model,
                }
                if group.delivery_mode == "continuous":
                    tasks.append(
                        _make_task(
                            kind=TaskKind.CONTINUOUS_JOINT,
                            delivery_mode="continuous",
                            sources=tuple(
                                sorted(group.sources, key=lambda item: item.source_id)
                            ),
                            dependencies=(),
                            **shared,
                        )
                    )
                    continue
                source_tasks = [
                    _make_task(
                        kind=TaskKind.ALTERNATING_SOURCE,
                        delivery_mode="alternating",
                        sources=(source,),
                        dependencies=(),
                        **shared,
                    )
                    for source in sorted(group.sources, key=lambda item: item.source_id)
                ]
                tasks.extend(source_tasks)
                tasks.append(
                    _make_task(
                        kind=TaskKind.ALTERNATING_GROUP_PEAK,
                        delivery_mode="alternating",
                        sources=tuple(
                            sorted(group.sources, key=lambda item: item.source_id)
                        ),
                        dependencies=tuple(task.task_id for task in source_tasks),
                        **shared,
                    )
                )
    return tasks


def _make_task(
    *,
    kind: TaskKind,
    subject: SubjectRecord,
    program,
    electrode,
    group_id: str,
    group_sources: tuple[SourceRecord, ...],
    delivery_mode: Literal["continuous", "alternating"],
    sources: tuple[SourceRecord, ...],
    dependencies: tuple[str, ...],
    model: VtaModelConfig,
) -> VtaTask:
    values = {
        "kind": kind,
        "subject_id": subject.subject_id,
        "subject_dir": subject.subject_dir,
        "reconstruction_path": subject.reconstruction_path,
        "phase_id": program.phase_id,
        "program_id": program.program_id,
        "electrode_id": electrode.electrode_id,
        "hemisphere": electrode.hemisphere,
        "electrode_model": electrode.electrode_model,
        "reconstruction_lead_id": electrode.reconstruction_lead_id,
        "frequency_group_id": group_id,
        "delivery_mode": delivery_mode,
        "sources": sources,
        "group_sources": group_sources,
        "dependencies": dependencies,
        "model": model,
    }
    payload = _task_payload_without_id(
        **{key: value for key, value in values.items() if key != "group_sources"}
    )
    task_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return VtaTask(task_id=task_id, **values)


def _task_payload_without_id(
    *,
    kind: TaskKind,
    subject_id: str,
    subject_dir: Path,
    reconstruction_path: Path,
    phase_id: str,
    program_id: int,
    electrode_id: str,
    hemisphere: str,
    electrode_model: str,
    reconstruction_lead_id: int,
    frequency_group_id: str,
    delivery_mode: str,
    sources: tuple[SourceRecord, ...],
    dependencies: tuple[str, ...],
    model: VtaModelConfig,
) -> dict[str, object]:
    return {
        "kind": kind.value,
        "subject_id": subject_id,
        "subject_dir": str(subject_dir),
        "reconstruction_path": str(reconstruction_path),
        "phase_id": phase_id,
        "program_id": program_id,
        "electrode_id": electrode_id,
        "hemisphere": hemisphere,
        "electrode_model": electrode_model,
        "reconstruction_lead_id": reconstruction_lead_id,
        "frequency_group_id": frequency_group_id,
        "delivery_mode": delivery_mode,
        "sources": [_source_payload(source) for source in sources],
        "dependencies": list(dependencies),
        "model": {
            "gray_matter_s_per_m": model.gray_matter_s_per_m,
            "white_matter_s_per_m": model.white_matter_s_per_m,
            "atlas_set": model.atlas_set,
            "spaces": list(model.spaces),
            "thresholds_v_per_m": list(model.thresholds_v_per_m),
        },
    }


def _source_payload(source: SourceRecord) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "frequency_hz": source.frequency_hz,
        "control_mode": source.control_mode,
        "amplitude": source.amplitude,
        "pulse_width_us": source.pulse_width_us,
        "contacts": [
            {
                "contact": contact.contact,
                "polarity": contact.polarity,
                "fraction": contact.fraction,
            }
            for contact in source.contacts
        ],
    }


def normalized_frequency_group(task: VtaTask) -> tuple[object, ...]:
    """Return the project-identifier-free physical record for one group."""

    return (
        task.hemisphere,
        task.electrode_model,
        task.reconstruction_lead_id,
        task.delivery_mode,
        tuple(sorted(_normalized_source(source) for source in task.group_sources)),
        task.model.gray_matter_s_per_m,
        task.model.white_matter_s_per_m,
        task.model.atlas_set,
        tuple(task.model.spaces),
        tuple(task.model.thresholds_v_per_m),
    )


def equivalent_task_key(task: VtaTask) -> tuple[object, ...]:
    """Return the same-subject donor matching key for one task artifact."""

    if task.kind is TaskKind.ALTERNATING_SOURCE:
        return (
            task.kind.value,
            _normalized_execution_context(task),
            _normalized_source(task.sources[0]),
        )
    return (task.kind.value, normalized_frequency_group(task))


def _normalized_execution_context(task: VtaTask) -> tuple[object, ...]:
    return (
        task.hemisphere,
        task.electrode_model,
        task.reconstruction_lead_id,
        task.delivery_mode,
        task.model.gray_matter_s_per_m,
        task.model.white_matter_s_per_m,
        task.model.atlas_set,
        tuple(task.model.spaces),
        tuple(task.model.thresholds_v_per_m),
    )


def _normalized_source(source: SourceRecord) -> tuple[object, ...]:
    contacts = tuple(
        sorted(
            (
                str(contact.contact),
                contact.polarity,
                contact.fraction,
            )
            for contact in source.contacts
        )
    )
    return (
        source.frequency_hz,
        source.control_mode,
        source.amplitude,
        source.pulse_width_us,
        contacts,
    )
