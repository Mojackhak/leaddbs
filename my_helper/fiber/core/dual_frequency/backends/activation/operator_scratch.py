"""Run-scoped read-only pPAM fixed-operator generations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ...contracts import (
    ActivationRequest,
    PPAM_OPERATOR_SCRATCH_ARRAY_NAMES,
    PPAM_OPERATOR_SCRATCH_SCHEMA,
)
from ..formal.operator_scratch import (
    OperatorScratchError,
    ScratchArrayDescriptor,
    _cleanup_scratch_arrays,
    _open_scratch_arrays,
    _publish_scratch_arrays,
    close_operator_scratch,
)
from .fitting import (
    PPAMPermutationWorkspace,
    ppam_operator_scratch_arrays,
    restore_ppam_permutation_workspace,
)


class PPAMOperatorScratchError(RuntimeError):
    """Raised when pPAM fixed-operator scratch is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class PPAMOperatorScratchDescriptor:
    """Small picklable descriptor for one pPAM operator generation."""

    schema_version: str
    model_family: str
    root: Path
    arrays: tuple[ScratchArrayDescriptor, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PPAM_OPERATOR_SCRATCH_SCHEMA:
            raise PPAMOperatorScratchError("pPAM operator scratch schema is unsupported")
        family = str(self.model_family).strip().lower()
        if family not in {"reference_fiber", "addon_fiber"}:
            raise PPAMOperatorScratchError(
                "pPAM operator scratch model family is unsupported"
            )
        root = Path(self.root).expanduser().resolve()
        arrays = tuple(self.arrays)
        if not arrays or not all(
            isinstance(item, ScratchArrayDescriptor) for item in arrays
        ):
            raise PPAMOperatorScratchError("pPAM operator scratch arrays are invalid")
        if {item.name for item in arrays} != PPAM_OPERATOR_SCRATCH_ARRAY_NAMES:
            raise PPAMOperatorScratchError(
                "pPAM operator scratch array set is incomplete"
            )
        if len({item.filename for item in arrays}) != len(arrays):
            raise PPAMOperatorScratchError(
                "pPAM operator scratch filenames are duplicated"
            )
        object.__setattr__(self, "model_family", family)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "arrays", arrays)


def _publish_ppam_operator_scratch(
    parent: Path,
    workspace: PPAMPermutationWorkspace,
) -> PPAMOperatorScratchDescriptor:
    """Atomically publish one pPAM workspace's fixed numerical state."""

    if not isinstance(workspace, PPAMPermutationWorkspace):
        raise PPAMOperatorScratchError(
            "workspace must be a PPAMPermutationWorkspace"
        )
    family = workspace.request.final_model.endpoint.model_family
    try:
        root, arrays = _publish_scratch_arrays(
            parent,
            "ppam-generation-",
            ppam_operator_scratch_arrays(workspace),
        )
        return PPAMOperatorScratchDescriptor(
            schema_version=PPAM_OPERATOR_SCRATCH_SCHEMA,
            model_family=family,
            root=root,
            arrays=arrays,
        )
    except (OperatorScratchError, ValueError, TypeError) as error:
        raise PPAMOperatorScratchError(
            "pPAM operator scratch publication failed"
        ) from error


def open_ppam_operator_scratch(
    descriptor: PPAMOperatorScratchDescriptor,
) -> dict[str, np.memmap]:
    """Validate and reopen a complete pPAM generation as read-only memmaps."""

    if not isinstance(descriptor, PPAMOperatorScratchDescriptor):
        raise PPAMOperatorScratchError("pPAM operator scratch descriptor is invalid")
    try:
        return _open_scratch_arrays(descriptor.root, descriptor.arrays)
    except OperatorScratchError as error:
        raise PPAMOperatorScratchError(
            "pPAM operator scratch cannot be reopened"
        ) from error


def reopen_ppam_permutation_workspace(
    descriptor: PPAMOperatorScratchDescriptor,
    request: ActivationRequest,
    binary_exposure: np.ndarray,
    outcome: np.ndarray,
    fiber_ids: np.ndarray,
) -> tuple[PPAMPermutationWorkspace, dict[str, np.memmap]]:
    """Reopen scratch and reconstruct one block-ready pPAM workspace."""

    arrays = open_ppam_operator_scratch(descriptor)
    try:
        workspace = restore_ppam_permutation_workspace(
            request,
            binary_exposure,
            outcome,
            fiber_ids,
            arrays,
        )
    except Exception:
        close_ppam_operator_scratch(arrays)
        raise
    return workspace, arrays


def close_ppam_operator_scratch(arrays: dict[str, np.ndarray]) -> None:
    """Close every distinct memmap owned by one reopened pPAM generation."""

    close_operator_scratch(arrays)


def cleanup_ppam_operator_scratch(
    descriptor: PPAMOperatorScratchDescriptor,
) -> None:
    """Remove only one descriptor's enumerated pPAM generation."""

    if not isinstance(descriptor, PPAMOperatorScratchDescriptor):
        raise PPAMOperatorScratchError("pPAM operator scratch descriptor is invalid")
    try:
        _cleanup_scratch_arrays(descriptor.root, descriptor.arrays)
    except OperatorScratchError as error:
        raise PPAMOperatorScratchError(
            "pPAM operator scratch cleanup failed"
        ) from error


__all__ = [
    "PPAMOperatorScratchDescriptor",
    "PPAMOperatorScratchError",
    "cleanup_ppam_operator_scratch",
    "close_ppam_operator_scratch",
    "open_ppam_operator_scratch",
    "reopen_ppam_permutation_workspace",
]
