"""Persistence boundary for non-artifact formal operator scratch generations."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..backends.formal.operator_scratch import (
    FormalOperatorScratchDescriptor,
    ScratchArrayDescriptor,
    cleanup_operator_scratch,
    close_operator_scratch,
    open_operator_scratch,
)
from ..contracts import (
    FormalOperatorScratchRecord,
    FormalRequest,
    ScratchArrayRecord,
    canonical_hash,
)


class FormalOperatorWorkspaceError(RuntimeError):
    """Raised when a scratch descriptor cannot be bound to the current run."""


def formal_operator_input_identity(request: FormalRequest) -> str:
    """Bind operator scratch to exact scientific inputs without repository code."""

    if not isinstance(request, FormalRequest):
        raise FormalOperatorWorkspaceError("formal request is invalid")
    return canonical_hash({"formal_request": asdict(request)})


def formal_operator_scratch_record(
    descriptor: FormalOperatorScratchDescriptor,
    request: FormalRequest,
    run_root: Path,
) -> FormalOperatorScratchRecord:
    """Convert one internal generation to a portable run-relative record."""

    if not isinstance(descriptor, FormalOperatorScratchDescriptor):
        raise FormalOperatorWorkspaceError("operator scratch descriptor is invalid")
    if not isinstance(request, FormalRequest):
        raise FormalOperatorWorkspaceError("formal request is invalid")
    root = Path(run_root).expanduser().resolve()
    generation = descriptor.root.resolve()
    try:
        relative = generation.relative_to(root)
    except ValueError as error:
        raise FormalOperatorWorkspaceError(
            "operator scratch generation is outside the run root"
        ) from error
    expected_family = (
        "direct_voxel"
        if request.final_model.endpoint.model_family.endswith("voxel")
        else "normative_fiber"
    )
    if descriptor.model_family != expected_family:
        raise FormalOperatorWorkspaceError(
            "operator scratch model family does not match the formal request"
        )
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
    return FormalOperatorScratchRecord(
        target_id=request.final_model.identifier,
        model_family=expected_family,
        subject_axis=request.subject_axis,
        feature_axis=request.feature_axis,
        input_identity=formal_operator_input_identity(request),
        operator_schema=descriptor.schema_version,
        technical_status="completed",
        generation_path=relative.as_posix(),
        arrays=arrays,
        total_nbytes=sum(item.nbytes for item in arrays),
    )


def formal_operator_scratch_descriptor(
    record: FormalOperatorScratchRecord,
    run_root: Path,
) -> FormalOperatorScratchDescriptor:
    """Resolve one record only beneath the current run's work directory."""

    if not isinstance(record, FormalOperatorScratchRecord):
        raise FormalOperatorWorkspaceError("operator scratch record is invalid")
    root = Path(run_root).expanduser().resolve()
    work_root = (root / "work").resolve()
    generation = (root / record.generation_path).resolve()
    if generation == work_root or not generation.is_relative_to(work_root):
        raise FormalOperatorWorkspaceError(
            "operator scratch generation is outside the current run work root"
        )
    return FormalOperatorScratchDescriptor(
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


def validate_formal_operator_scratch_record(
    record: FormalOperatorScratchRecord,
    run_root: Path,
) -> None:
    """Require every recorded NPY array to reopen read-only in this run."""

    descriptor = formal_operator_scratch_descriptor(record, run_root)
    arrays = open_operator_scratch(descriptor)
    close_operator_scratch(arrays)


def validated_formal_operator_scratch_descriptor(
    record: FormalOperatorScratchRecord,
    request: FormalRequest,
    run_root: Path,
) -> FormalOperatorScratchDescriptor:
    """Bind and reopen one scratch record for the exact formal request."""

    if not isinstance(record, FormalOperatorScratchRecord):
        raise FormalOperatorWorkspaceError("operator scratch record is invalid")
    if not isinstance(request, FormalRequest):
        raise FormalOperatorWorkspaceError("formal request is invalid")
    expected_family = (
        "direct_voxel"
        if request.final_model.endpoint.model_family.endswith("voxel")
        else "normative_fiber"
    )
    if (
        record.target_id != request.final_model.identifier
        or record.model_family != expected_family
        or record.subject_axis != request.subject_axis
        or record.feature_axis != request.feature_axis
        or record.input_identity != formal_operator_input_identity(request)
        or record.technical_status != "completed"
    ):
        raise FormalOperatorWorkspaceError(
            "operator scratch record does not match the formal request"
        )
    descriptor = formal_operator_scratch_descriptor(record, run_root)
    arrays = open_operator_scratch(descriptor)
    close_operator_scratch(arrays)
    return descriptor


def cleanup_formal_operator_scratch_record(
    record: FormalOperatorScratchRecord,
    run_root: Path,
) -> None:
    """Remove only one validated record's enumerated generation files."""

    cleanup_operator_scratch(formal_operator_scratch_descriptor(record, run_root))


__all__ = [
    "FormalOperatorWorkspaceError",
    "cleanup_formal_operator_scratch_record",
    "formal_operator_input_identity",
    "formal_operator_scratch_descriptor",
    "formal_operator_scratch_record",
    "validated_formal_operator_scratch_descriptor",
    "validate_formal_operator_scratch_record",
]
