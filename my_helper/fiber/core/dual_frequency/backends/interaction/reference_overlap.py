"""Pure reference-overlap exclusion for add-on exposure preparation."""

from __future__ import annotations

from dataclasses import dataclass, fields
import math

import numpy as np

from ...contracts import SourceRecord
from ...contracts.records import ACCEPTED_SOURCE_STATUSES


class ReferenceOverlapError(ValueError):
    """Raised when overlap inputs do not share one finite exposure axis."""


@dataclass(frozen=True)
class ReferenceOverlapResult:
    """Prepared add-on exposure and the exact reference exclusion rule."""

    reference_threshold: float
    overlap_mask: np.ndarray
    addon_exposure: np.ndarray

    def __post_init__(self) -> None:
        threshold = float(self.reference_threshold)
        if not (threshold == math.inf or (math.isfinite(threshold) and threshold > 0)):
            raise ReferenceOverlapError(
                "reference_threshold must be positive finite or positive infinity"
            )
        if self.overlap_mask.ndim != 2 or self.overlap_mask.dtype != np.bool_:
            raise ReferenceOverlapError("overlap_mask must be a two-dimensional Boolean array")
        if self.addon_exposure.ndim != 2 or self.addon_exposure.shape != self.overlap_mask.shape:
            raise ReferenceOverlapError(
                "addon_exposure must share the two-dimensional overlap-mask axes"
            )
        for field in fields(self):
            if isinstance(getattr(self, field.name), np.ndarray):
                getattr(self, field.name).flags.writeable = False


def _finite_exposure(value: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 2:
        raise ReferenceOverlapError(f"{name} must be two-dimensional")
    if array.dtype == object or not np.issubdtype(array.dtype, np.number):
        raise ReferenceOverlapError(f"{name} must contain numeric values")
    if np.iscomplexobj(array):
        raise ReferenceOverlapError(f"{name} must contain real values")
    result = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ReferenceOverlapError(f"{name} must contain only finite values")
    return result


def prepare_reference_overlap(
    addon_exposure: np.ndarray,
    addon_reference_component_exposure: np.ndarray,
    reference_source: SourceRecord,
) -> ReferenceOverlapResult:
    """Exclude reference-active voxels, including the exact-tau boundary."""

    if not isinstance(reference_source, SourceRecord):
        raise TypeError("reference_source must be a SourceRecord")
    if reference_source.endpoint.model_family != "reference_voxel":
        raise ReferenceOverlapError(
            "direct-voxel overlap requires a reference_voxel source"
        )
    if reference_source.input_status != "valid":
        raise ReferenceOverlapError(
            "reference overlap requires a valid matched reference dependency"
        )
    addon = _finite_exposure(addon_exposure, "addon_exposure")
    reference = _finite_exposure(
        addon_reference_component_exposure,
        "addon_reference_component_exposure",
    )
    if addon.shape != reference.shape:
        raise ReferenceOverlapError(
            "add-on and reference-component exposures must have identical axes"
        )

    if reference_source.source_status in ACCEPTED_SOURCE_STATUSES:
        if reference_source.selected_tau is None:
            raise ReferenceOverlapError(
                "accepted reference source is missing selected tau"
            )
        threshold = float(reference_source.selected_tau)
    elif reference_source.source_status == "absent_no_stable_grid":
        threshold = math.inf
    else:
        raise ReferenceOverlapError(
            f"unsupported reference source status {reference_source.source_status!r}"
        )

    overlap_mask = reference >= threshold
    prepared = np.where(overlap_mask, 0.0, addon)
    return ReferenceOverlapResult(
        reference_threshold=threshold,
        overlap_mask=np.array(overlap_mask, dtype=bool, copy=True),
        addon_exposure=np.array(prepared, dtype=np.float64, copy=True),
    )
