"""Stable subject-identity joins for add-on reference operators."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ...contracts import AxisRef


class DeltaReferenceCohortError(ValueError):
    """Raised when add-on subjects cannot map exactly to reference folds."""


def reference_fold_indices(
    *,
    addon_subject_ids: Sequence[str],
    reference_subject_ids: Sequence[str],
    addon_subject_axis: AxisRef,
    reference_subject_axis: AxisRef,
) -> np.ndarray:
    """Return reference-fold positions for the ordered add-on subject cohort."""

    if not isinstance(addon_subject_axis, AxisRef) or not isinstance(
        reference_subject_axis,
        AxisRef,
    ):
        raise TypeError(
            "addon_subject_axis and reference_subject_axis must be AxisRef values"
        )

    addon_ids = tuple(str(value).strip() for value in addon_subject_ids)
    reference_ids = tuple(str(value).strip() for value in reference_subject_ids)
    if any(not value for value in addon_ids + reference_ids):
        raise DeltaReferenceCohortError("subject IDs must be nonempty")
    if len(addon_ids) != addon_subject_axis.count:
        raise DeltaReferenceCohortError(
            "add-on subject IDs do not match the declared add-on subject axis"
        )
    if len(reference_ids) != reference_subject_axis.count:
        raise DeltaReferenceCohortError(
            "reference subject IDs do not match the declared reference subject axis"
        )
    if len(set(addon_ids)) != len(addon_ids):
        raise DeltaReferenceCohortError("add-on subject IDs must be unique")
    if len(set(reference_ids)) != len(reference_ids):
        raise DeltaReferenceCohortError("reference subject IDs must be unique")

    reference_positions = {
        subject_id: index for index, subject_id in enumerate(reference_ids)
    }
    if any(subject_id not in reference_positions for subject_id in addon_ids):
        raise DeltaReferenceCohortError(
            "every add-on subject must occur exactly once in the matched reference cohort"
        )
    return np.asarray(
        [reference_positions[subject_id] for subject_id in addon_ids],
        dtype=np.int64,
    )
