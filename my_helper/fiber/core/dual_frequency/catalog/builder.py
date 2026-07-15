"""Deterministic endpoint catalog construction without project discovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from ..config.models import EndpointBinding, ResolvedWorkflow
from ..contracts.identity import EndpointKey
from ..contracts.study_base import ProgramRecord, ScaleDefinition, StudyBaseRecord


MODEL_FAMILY_ORDER = (
    "reference_voxel",
    "reference_fiber",
    "addon_voxel",
    "addon_fiber",
)


class CatalogError(ValueError):
    """Raised when validated configuration cannot bind to the study catalog."""


class CatalogStatus(str, Enum):
    DATA_AVAILABLE = "data_available"
    NOT_CONFIGURED = "not_configured"
    INSUFFICIENT_SUBJECTS = "insufficient_subjects"


@dataclass(frozen=True)
class EndpointRecord:
    """One scale/model/connectome endpoint with explicit dependency identity."""

    key: EndpointKey
    scale_label: str
    scale_direction: str
    baseline_binding_id: str
    outcome_binding_id: str
    matched_reference_endpoint_id: str | None
    connectome_role: str
    final_eligible: bool
    requested: bool
    subject_ids: tuple[str, ...]
    minimum_subjects: int
    status: CatalogStatus

    def __post_init__(self) -> None:
        if self.scale_direction not in {"lower", "higher"}:
            raise CatalogError("endpoint scale direction must be lower or higher")
        if self.connectome_role not in {"none", "formal", "sensitive"}:
            raise CatalogError(f"unsupported connectome role {self.connectome_role!r}")
        if self.connectome_role == "sensitive" and self.final_eligible:
            raise CatalogError("sensitive connectome endpoints cannot be final-eligible")
        if self.key.model_family.endswith("voxel") and self.connectome_role != "none":
            raise CatalogError("direct-voxel endpoints cannot declare a connectome role")
        if self.key.model_family.endswith("fiber") and self.connectome_role == "none":
            raise CatalogError("normative-fiber endpoints require a connectome role")
        if self.key.model_family.startswith("addon_") and self.matched_reference_endpoint_id is None:
            raise CatalogError("add-on endpoints require a matched reference endpoint")
        if self.key.model_family.startswith("reference_") and self.matched_reference_endpoint_id is not None:
            raise CatalogError("reference endpoints cannot declare a matched reference endpoint")
        if self.minimum_subjects < 2:
            raise CatalogError("minimum_subjects must be at least two")
        expected_status = (
            CatalogStatus.DATA_AVAILABLE
            if len(self.subject_ids) >= self.minimum_subjects
            else CatalogStatus.INSUFFICIENT_SUBJECTS
        )
        if self.status not in {expected_status, CatalogStatus.NOT_CONFIGURED}:
            raise CatalogError("catalog status does not match endpoint subject availability")

    @property
    def endpoint_id(self) -> str:
        return self.key.identifier

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["endpoint_id"] = self.endpoint_id
        payload["status"] = self.status.value
        return payload


def _binding_id(role: str, binding: EndpointBinding) -> str:
    return f"{role}:{binding.identifier}"


def _program_for(subject_programs: tuple[ProgramRecord, ...], binding: EndpointBinding) -> ProgramRecord | None:
    matches = tuple(
        program
        for program in subject_programs
        if program.phase_id == binding.phase_id and program.program_id == binding.program_id
    )
    if len(matches) > 1:
        raise CatalogError(f"duplicate bound program {binding.identifier!r}")
    return matches[0] if matches else None


def _has_observed_scale(program: ProgramRecord | None, scale_id: str) -> bool:
    if program is None:
        return False
    matches = tuple(item for item in program.observations if item.scale_id == scale_id)
    if len(matches) != 1:
        raise CatalogError(
            f"program {program.identifier!r} must contain exactly one observation for {scale_id!r}"
        )
    return matches[0].status == "observed"


def _complete_subjects(
    study: StudyBaseRecord,
    scale_id: str,
    baseline: EndpointBinding,
    outcome: EndpointBinding,
) -> tuple[str, ...]:
    output: list[str] = []
    for subject in study.subjects:
        baseline_program = _program_for(subject.programs, baseline)
        outcome_program = _program_for(subject.programs, outcome)
        if _has_observed_scale(baseline_program, scale_id) and _has_observed_scale(
            outcome_program,
            scale_id,
        ):
            output.append(subject.subject_id)
    return tuple(output)


def _required_model_families(selected: tuple[str, ...]) -> tuple[str, ...]:
    required = set(selected)
    if "addon_voxel" in required:
        required.add("reference_voxel")
    if "addon_fiber" in required:
        required.add("reference_fiber")
    return tuple(item for item in MODEL_FAMILY_ORDER if item in required)


def _status(subject_ids: tuple[str, ...], minimum_subjects: int) -> CatalogStatus:
    if len(subject_ids) >= minimum_subjects:
        return CatalogStatus.DATA_AVAILABLE
    return CatalogStatus.INSUFFICIENT_SUBJECTS


def _endpoint_key(
    study_id: str,
    scale_id: str,
    model_family: str,
    endpoint_binding_id: str,
    connectome_id: str = "none",
) -> EndpointKey:
    return EndpointKey(
        study_id=study_id,
        scale_id=scale_id,
        endpoint_binding_id=endpoint_binding_id,
        model_family=model_family,
        connectome_id=connectome_id,
    )


def build_endpoint_catalog(
    config: ResolvedWorkflow,
    study: StudyBaseRecord,
) -> tuple[EndpointRecord, ...]:
    """Build requested endpoints plus exact matched-reference dependencies."""
    if not isinstance(config, ResolvedWorkflow):
        raise CatalogError("config must be a ResolvedWorkflow")
    if not isinstance(study, StudyBaseRecord):
        raise CatalogError("study must be a StudyBaseRecord")

    scales = {item.scale_id: item for item in study.scales}
    missing_scales = sorted(set(config.selected_scales) - set(scales))
    if missing_scales:
        raise CatalogError(f"configured scale IDs missing from study base: {missing_scales}")

    connectomes = {item.connectome_id: item for item in config.normative_fiber.connectomes}
    missing_connectomes = sorted(set(config.selected_connectomes) - set(connectomes))
    if missing_connectomes:
        raise CatalogError(f"selected connectomes are not configured: {missing_connectomes}")

    families = _required_model_families(config.selected_models)
    requested_families = set(config.selected_models)
    pair = config.direct_voxel.endpoint_pair
    minimum_subjects = config.direct_voxel.hard_computability.n_subjects_min
    reference_binding_id = _binding_id("reference", pair.reference)
    addon_binding_id = _binding_id("addon", pair.addon)
    records: list[EndpointRecord] = []

    for scale_id in config.selected_scales:
        scale: ScaleDefinition = scales[scale_id]
        reference_subjects = _complete_subjects(study, scale_id, pair.baseline, pair.reference)
        addon_subjects = _complete_subjects(study, scale_id, pair.reference, pair.addon)
        reference_ids: dict[tuple[str, str], str] = {}

        if "reference_voxel" in families:
            key = _endpoint_key(
                study.study_id,
                scale_id,
                "reference_voxel",
                reference_binding_id,
            )
            reference_ids[("reference_voxel", "none")] = key.identifier
            records.append(
                EndpointRecord(
                    key=key,
                    scale_label=scale.label,
                    scale_direction=scale.direction,
                    baseline_binding_id=_binding_id("baseline", pair.baseline),
                    outcome_binding_id=reference_binding_id,
                    matched_reference_endpoint_id=None,
                    connectome_role="none",
                    final_eligible=True,
                    requested="reference_voxel" in requested_families,
                    subject_ids=reference_subjects,
                    minimum_subjects=minimum_subjects,
                    status=_status(reference_subjects, minimum_subjects),
                )
            )

        if "reference_fiber" in families:
            for connectome_id in config.selected_connectomes:
                connectome = connectomes[connectome_id]
                key = _endpoint_key(
                    study.study_id,
                    scale_id,
                    "reference_fiber",
                    reference_binding_id,
                    connectome_id,
                )
                reference_ids[("reference_fiber", connectome_id)] = key.identifier
                records.append(
                    EndpointRecord(
                        key=key,
                        scale_label=scale.label,
                        scale_direction=scale.direction,
                        baseline_binding_id=_binding_id("baseline", pair.baseline),
                        outcome_binding_id=reference_binding_id,
                        matched_reference_endpoint_id=None,
                        connectome_role=connectome.role,
                        final_eligible=connectome.role == "formal",
                        requested="reference_fiber" in requested_families,
                        subject_ids=reference_subjects,
                        minimum_subjects=minimum_subjects,
                        status=_status(reference_subjects, minimum_subjects),
                    )
                )

        if "addon_voxel" in families:
            key = _endpoint_key(
                study.study_id,
                scale_id,
                "addon_voxel",
                addon_binding_id,
            )
            records.append(
                EndpointRecord(
                    key=key,
                    scale_label=scale.label,
                    scale_direction=scale.direction,
                    baseline_binding_id=reference_binding_id,
                    outcome_binding_id=addon_binding_id,
                    matched_reference_endpoint_id=reference_ids[("reference_voxel", "none")],
                    connectome_role="none",
                    final_eligible=True,
                    requested="addon_voxel" in requested_families,
                    subject_ids=addon_subjects,
                    minimum_subjects=minimum_subjects,
                    status=_status(addon_subjects, minimum_subjects),
                )
            )

        if "addon_fiber" in families:
            for connectome_id in config.selected_connectomes:
                connectome = connectomes[connectome_id]
                key = _endpoint_key(
                    study.study_id,
                    scale_id,
                    "addon_fiber",
                    addon_binding_id,
                    connectome_id,
                )
                records.append(
                    EndpointRecord(
                        key=key,
                        scale_label=scale.label,
                        scale_direction=scale.direction,
                        baseline_binding_id=reference_binding_id,
                        outcome_binding_id=addon_binding_id,
                        matched_reference_endpoint_id=reference_ids[("reference_fiber", connectome_id)],
                        connectome_role=connectome.role,
                        final_eligible=connectome.role == "formal",
                        requested="addon_fiber" in requested_families,
                        subject_ids=addon_subjects,
                        minimum_subjects=minimum_subjects,
                        status=_status(addon_subjects, minimum_subjects),
                    )
                )

    return tuple(records)
