"""Persistence boundary for pPAM observed state and operator scratch."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np

from ..backends.activation.operator_scratch import (
    PPAMOperatorScratchDescriptor,
    _publish_ppam_operator_scratch,
    cleanup_ppam_operator_scratch,
    close_ppam_operator_scratch,
    open_ppam_operator_scratch,
    reopen_ppam_permutation_workspace,
)
from ..backends.activation.fitting import PPAMPermutationWorkspace
from ..backends.formal.operator_scratch import ScratchArrayDescriptor
from ..contracts import (
    ActivationRequest,
    ArtifactRef,
    PPAMObservedWorkspaceRecord,
    ScratchArrayRecord,
    canonical_hash,
)


class PPAMObservedWorkspaceError(RuntimeError):
    """Raised when a durable pPAM workspace cannot be bound or reopened."""


def publish_ppam_operator_scratch(
    parent: Path,
    workspace: PPAMPermutationWorkspace,
) -> PPAMOperatorScratchDescriptor:
    """Publish one run-scoped pPAM operator generation."""

    return _publish_ppam_operator_scratch(parent, workspace)


def _artifact(value: object, field: str) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        raise PPAMObservedWorkspaceError(
            f"persisted pPAM {field} must be an ArtifactRef"
        )
    return value


def _artifact_identity(value: ArtifactRef | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "kind": value.kind,
        "schema_version": value.schema_version,
        "sha256": value.sha256,
        "dtype": value.dtype,
        "shape": value.shape,
        "axis_hashes": value.axis_hashes,
        "units": value.units,
        "space": value.space,
    }


def ppam_observed_input_identity(
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
) -> str:
    """Bind one durable pPAM workspace to exact scientific content."""

    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    activation_probability = _artifact(
        request.activation_probability,
        "activation_probability",
    )
    outcome = _artifact(request.outcome, "outcome")
    baseline = _artifact(request.baseline, "baseline")
    peak = _artifact(request.peak_final_score, "peak_final_score")
    feature_ids = _artifact(request.feature_ids, "feature_ids")
    activation_feature_ids = _artifact(
        request.activation_feature_ids,
        "activation_feature_ids",
    )
    overlap = (
        None
        if request.reference_overlap_mask is None
        else _artifact(request.reference_overlap_mask, "reference_overlap_mask")
    )
    nuisance = tuple(
        _artifact(value, f"nuisance_inputs[{index}]")
        for index, value in enumerate(request.nuisance_inputs)
    )
    return canonical_hash(
        {
            "schema_version": "dual_frequency_ppam_observed_input_v1",
            "final_model_id": request.final_model.identifier,
            "final_branch": request.final_model.final_key.final_branch,
            "subject_axis": asdict(request.subject_axis),
            "feature_axis": asdict(request.feature_axis),
            "activation_probability": _artifact_identity(activation_probability),
            "binary_exposure": _artifact_identity(binary),
            "outcome": _artifact_identity(outcome),
            "baseline": _artifact_identity(baseline),
            "peak_final_score": _artifact_identity(peak),
            "feature_ids": _artifact_identity(feature_ids),
            "activation_feature_ids": _artifact_identity(
                activation_feature_ids
            ),
            "reference_overlap_mask": _artifact_identity(overlap),
            "nuisance_inputs": tuple(
                _artifact_identity(value) for value in nuisance
            ),
            "outcome_direction": request.outcome_direction,
            "hard_computability": asdict(request.hard_computability),
            "connectome_role": request.connectome_role,
            "fiber_score_settings": asdict(request.fiber_score_settings),
            "fitting_probability_threshold": (
                request.fitting_probability_threshold
            ),
            "permutation_resamples": request.permutation_resamples,
            "seed": request.seed,
        }
    )


def ppam_observed_workspace_record(
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
    observed_artifacts: tuple[ArtifactRef, ...],
    technical_status: str,
    run_root: Path,
    descriptor: PPAMOperatorScratchDescriptor | None,
) -> PPAMObservedWorkspaceRecord:
    """Convert one observed state and optional scratch to a durable record."""

    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    activation_probability = _artifact(
        request.activation_probability,
        "activation_probability",
    )
    outcome = _artifact(request.outcome, "outcome")
    baseline = _artifact(request.baseline, "baseline")
    peak = _artifact(request.peak_final_score, "peak_final_score")
    feature_ids = _artifact(request.feature_ids, "feature_ids")
    activation_feature_ids = _artifact(
        request.activation_feature_ids,
        "activation_feature_ids",
    )
    overlap = (
        None
        if request.reference_overlap_mask is None
        else _artifact(request.reference_overlap_mask, "reference_overlap_mask")
    )
    nuisance = tuple(
        _artifact(value, f"nuisance_inputs[{index}]")
        for index, value in enumerate(request.nuisance_inputs)
    )
    family = request.final_model.endpoint.model_family
    if descriptor is None:
        operator_schema = None
        generation_path = None
        arrays: tuple[ScratchArrayRecord, ...] = ()
    else:
        if descriptor.model_family != family:
            raise PPAMObservedWorkspaceError(
                "pPAM scratch model family does not match the request"
            )
        root = Path(run_root).expanduser().resolve()
        try:
            relative = descriptor.root.resolve().relative_to(root)
        except ValueError as error:
            raise PPAMObservedWorkspaceError(
                "pPAM scratch generation is outside the run root"
            ) from error
        operator_schema = descriptor.schema_version
        generation_path = relative.as_posix()
        arrays = tuple(
            ScratchArrayRecord(
                name=item.name,
                filename=item.filename,
                dtype=item.dtype,
                shape=item.shape,
                fortran_order=item.fortran_order,
                nbytes=item.nbytes,
            )
            for item in descriptor.arrays
        )
    settings = request.fiber_score_settings
    limits = request.hard_computability
    fold_minimum = limits.fold_n_features_min
    if fold_minimum is None:
        raise PPAMObservedWorkspaceError("pPAM fold feature minimum is missing")
    return PPAMObservedWorkspaceRecord(
        target_id=request.final_model.identifier,
        model_family=family,
        final_branch=request.final_model.final_key.final_branch,
        subject_axis=request.subject_axis,
        feature_axis=request.feature_axis,
        input_identity=ppam_observed_input_identity(request, binary),
        technical_status=technical_status,
        outcome_direction=request.outcome_direction,
        n_subjects_min=limits.n_subjects_min,
        fold_n_features_min=fold_minimum,
        sweet_fraction=settings.sweet_fraction,
        sour_fraction=settings.sour_fraction,
        weighted_peak_fraction=settings.weighted_peak_fraction,
        sweet_selected_min_count=settings.sweet_selected_min_count,
        sour_selected_min_count=settings.sour_selected_min_count,
        weighted_peak_min_count=settings.weighted_peak_min_count,
        fitting_probability_threshold=request.fitting_probability_threshold,
        permutation_resamples=request.permutation_resamples,
        seed=request.seed,
        activation_probability=activation_probability,
        binary_exposure=binary,
        outcome=outcome,
        baseline=baseline,
        peak_final_score=peak,
        feature_ids=feature_ids,
        activation_feature_ids=activation_feature_ids,
        reference_overlap_mask=overlap,
        nuisance_inputs=nuisance,
        observed_artifacts=tuple(observed_artifacts),
        operator_schema=operator_schema,
        generation_path=generation_path,
        arrays=arrays,
        total_nbytes=sum(item.nbytes for item in arrays),
    )


def ppam_operator_scratch_descriptor(
    record: PPAMObservedWorkspaceRecord,
    run_root: Path,
) -> PPAMOperatorScratchDescriptor:
    """Resolve one recorded pPAM generation beneath the current run work root."""

    if not isinstance(record, PPAMObservedWorkspaceRecord):
        raise PPAMObservedWorkspaceError("pPAM observed workspace record is invalid")
    if (
        record.operator_schema is None
        or record.generation_path is None
        or not record.arrays
    ):
        raise PPAMObservedWorkspaceError("pPAM observed workspace has no scratch")
    root = Path(run_root).expanduser().resolve()
    work_root = (root / "work").resolve()
    generation = (root / record.generation_path).resolve()
    if generation == work_root or not generation.is_relative_to(work_root):
        raise PPAMObservedWorkspaceError(
            "pPAM scratch generation is outside the current run work root"
        )
    return PPAMOperatorScratchDescriptor(
        schema_version=record.operator_schema,
        model_family=record.model_family,
        root=generation,
        arrays=tuple(
            ScratchArrayDescriptor(
                name=item.name,
                filename=item.filename,
                dtype=item.dtype,
                shape=item.shape,
                fortran_order=item.fortran_order,
                nbytes=item.nbytes,
            )
            for item in record.arrays
        ),
    )


def _record_matches_request(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
) -> bool:
    settings = request.fiber_score_settings
    limits = request.hard_computability
    family = request.final_model.endpoint.model_family
    return bool(
        record.technical_status != "nuisance_not_estimable"
        and record.target_id == request.final_model.identifier
        and record.model_family == family
        and record.final_branch == request.final_model.final_key.final_branch
        and record.subject_axis == request.subject_axis
        and record.feature_axis == request.feature_axis
        and record.input_identity
        == ppam_observed_input_identity(request, binary_exposure)
        and record.outcome_direction == request.outcome_direction
        and record.n_subjects_min == limits.n_subjects_min
        and record.fold_n_features_min == limits.fold_n_features_min
        and record.sweet_fraction == settings.sweet_fraction
        and record.sour_fraction == settings.sour_fraction
        and record.weighted_peak_fraction == settings.weighted_peak_fraction
        and record.sweet_selected_min_count
        == settings.sweet_selected_min_count
        and record.sour_selected_min_count == settings.sour_selected_min_count
        and record.weighted_peak_min_count == settings.weighted_peak_min_count
        and record.fitting_probability_threshold
        == request.fitting_probability_threshold
        and record.permutation_resamples == request.permutation_resamples
        and record.seed == request.seed
        and record.activation_probability == request.activation_probability
        and record.binary_exposure == binary_exposure
        and record.outcome == request.outcome
        and record.baseline == request.baseline
        and record.peak_final_score == request.peak_final_score
        and record.feature_ids == request.feature_ids
        and record.activation_feature_ids == request.activation_feature_ids
        and record.reference_overlap_mask == request.reference_overlap_mask
        and record.nuisance_inputs == request.nuisance_inputs
    )


def validated_ppam_operator_scratch_descriptor(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure: ArtifactRef,
    run_root: Path,
) -> PPAMOperatorScratchDescriptor:
    """Bind and reopen one pPAM generation for the exact activation request."""

    if not isinstance(record, PPAMObservedWorkspaceRecord):
        raise PPAMObservedWorkspaceError("pPAM observed workspace record is invalid")
    if not isinstance(request, ActivationRequest):
        raise PPAMObservedWorkspaceError("activation request is invalid")
    binary = _artifact(binary_exposure, "binary_exposure")
    if not _record_matches_request(record, request, binary):
        raise PPAMObservedWorkspaceError(
            "pPAM observed workspace does not match the activation request"
        )
    descriptor = ppam_operator_scratch_descriptor(record, run_root)
    arrays = open_ppam_operator_scratch(descriptor)
    close_ppam_operator_scratch(arrays)
    return descriptor


def reopen_ppam_workspace_from_record(
    record: PPAMObservedWorkspaceRecord,
    request: ActivationRequest,
    binary_exposure_ref: ArtifactRef,
    binary_exposure: np.ndarray,
    outcome: np.ndarray,
    fiber_ids: np.ndarray,
    run_root: Path,
) -> tuple[PPAMPermutationWorkspace, dict[str, np.memmap]]:
    """Validate one record and reopen its block-ready numerical workspace."""

    descriptor = validated_ppam_operator_scratch_descriptor(
        record,
        request,
        binary_exposure_ref,
        run_root,
    )
    return reopen_ppam_permutation_workspace(
        descriptor,
        request,
        binary_exposure,
        outcome,
        fiber_ids,
    )


def cleanup_ppam_observed_workspace_record(
    record: PPAMObservedWorkspaceRecord,
    run_root: Path,
) -> None:
    """Remove only one record's enumerated pPAM scratch generation."""

    if record.technical_status == "nuisance_not_estimable":
        return
    cleanup_ppam_operator_scratch(
        ppam_operator_scratch_descriptor(record, run_root)
    )


__all__ = [
    "PPAMObservedWorkspaceError",
    "cleanup_ppam_observed_workspace_record",
    "ppam_observed_input_identity",
    "ppam_observed_workspace_record",
    "ppam_operator_scratch_descriptor",
    "publish_ppam_operator_scratch",
    "reopen_ppam_workspace_from_record",
    "validated_ppam_operator_scratch_descriptor",
]
