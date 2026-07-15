"""Exact ordered-axis operations for right-canonical activation rows.

This module accepts only explicitly supplied axes and rows. It does not search
for nearby axes, infer a reusable superset, or select a producer artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

import numpy as np

from .ppam import max_probability_union, validate_probabilities


LEFT_SIDE = "L"
RIGHT_SIDE = "R"

SideProbabilityRow: TypeAlias = tuple[np.ndarray, np.ndarray]
SideProbabilityRows: TypeAlias = Mapping[tuple[str, str], SideProbabilityRow]


class CanonicalMappingError(ValueError):
    """Raised when an activation axis or canonical side mapping is invalid."""


def _fiber_ids(value: np.ndarray, *, name: str) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalMappingError(f"{name} must be a one-dimensional int64 array") from exc
    if array.ndim != 1:
        raise CanonicalMappingError(f"{name} must be one-dimensional")
    if array.size == 0:
        raise CanonicalMappingError(f"{name} must be nonempty")
    if array.dtype != np.dtype(np.int64):
        raise CanonicalMappingError(f"{name} must use exact int64 dtype")
    if np.unique(array).size != array.size:
        raise CanonicalMappingError(f"{name} must contain unique fiber IDs")
    output = np.array(array, dtype=np.int64, order="C", copy=True)
    output.flags.writeable = False
    return output


def activation_universe(final_valid_fiber_ids: np.ndarray) -> np.ndarray:
    """Return the exact ordered final valid-feature axis without restriction."""

    return _fiber_ids(
        final_valid_fiber_ids,
        name="final_valid_fiber_ids",
    )


def _exact_axis_positions(
    source_fiber_ids: np.ndarray,
    requested_fiber_ids: np.ndarray,
) -> np.ndarray:
    source = _fiber_ids(source_fiber_ids, name="source_fiber_ids")
    requested = _fiber_ids(requested_fiber_ids, name="requested_fiber_ids")
    source_positions = {int(fiber_id): index for index, fiber_id in enumerate(source)}
    if any(int(fiber_id) not in source_positions for fiber_id in requested):
        raise CanonicalMappingError(
            "source axis does not contain all exact requested fiber IDs"
        )
    positions = np.fromiter(
        (source_positions[int(fiber_id)] for fiber_id in requested),
        dtype=np.int64,
        count=requested.size,
    )
    positions.flags.writeable = False
    return positions


def subset_probability_axis(
    probabilities: np.ndarray,
    *,
    source_fiber_ids: np.ndarray,
    requested_fiber_ids: np.ndarray,
) -> np.ndarray:
    """Subset an explicit source by exact IDs into the requested ordered axis."""

    source = _fiber_ids(source_fiber_ids, name="source_fiber_ids")
    requested = _fiber_ids(requested_fiber_ids, name="requested_fiber_ids")
    validated = validate_probabilities(probabilities)
    if validated.shape[-1] != source.size:
        raise CanonicalMappingError(
            "probabilities fiber-axis length must match source_fiber_ids"
        )
    positions = _exact_axis_positions(source, requested)
    subset = np.ascontiguousarray(np.take(validated, positions, axis=-1))
    subset.flags.writeable = False
    return subset


def _subject_order(subject_order: Sequence[str]) -> tuple[str, ...]:
    if isinstance(subject_order, (str, bytes)):
        raise CanonicalMappingError("subject_order must be a sequence of subject IDs")
    try:
        subjects = tuple(subject_order)
    except TypeError as exc:
        raise CanonicalMappingError(
            "subject_order must be a sequence of subject IDs"
        ) from exc
    if not subjects:
        raise CanonicalMappingError("subject_order must be nonempty")
    if any(not isinstance(subject, str) or not subject.strip() for subject in subjects):
        raise CanonicalMappingError("subject_order must contain nonempty string IDs")
    if len(set(subjects)) != len(subjects):
        raise CanonicalMappingError("subject_order must contain unique subject IDs")
    return subjects


def _row(
    value: SideProbabilityRow,
    *,
    key: tuple[str, str],
    valid_fiber_ids: np.ndarray,
) -> np.ndarray:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise CanonicalMappingError(
            f"side_probabilities[{key!r}] must contain fiber IDs and probabilities"
        )
    row_ids = _fiber_ids(value[0], name=f"side_probabilities[{key!r}] fiber IDs")
    if not np.array_equal(row_ids, valid_fiber_ids):
        raise CanonicalMappingError(
            f"side_probabilities[{key!r}] must use the exact final feature axis"
        )
    probabilities = validate_probabilities(
        value[1],
        name=f"side_probabilities[{key!r}] probabilities",
    )
    if probabilities.ndim != 1 or probabilities.shape != (valid_fiber_ids.size,):
        raise CanonicalMappingError(
            f"side_probabilities[{key!r}] must be one row on the exact final feature axis"
        )
    return probabilities


def merge_right_canonical_probabilities(
    *,
    subject_order: Sequence[str],
    valid_fiber_ids: np.ndarray,
    side_probabilities: SideProbabilityRows,
) -> np.ndarray:
    """Validate and merge exact L/R rows in the declared subject order."""

    subjects = _subject_order(subject_order)
    final_axis = activation_universe(valid_fiber_ids)
    if not isinstance(side_probabilities, Mapping):
        raise CanonicalMappingError("side_probabilities must be a mapping")
    expected_keys = {
        (subject, side)
        for subject in subjects
        for side in (LEFT_SIDE, RIGHT_SIDE)
    }
    if set(side_probabilities) != expected_keys:
        raise CanonicalMappingError(
            "side_probabilities must contain exact L/R rows for every ordered subject"
        )

    merged = np.empty((len(subjects), final_axis.size), dtype=np.float32)
    for index, subject in enumerate(subjects):
        right = _row(
            side_probabilities[(subject, RIGHT_SIDE)],
            key=(subject, RIGHT_SIDE),
            valid_fiber_ids=final_axis,
        )
        left_to_right = _row(
            side_probabilities[(subject, LEFT_SIDE)],
            key=(subject, LEFT_SIDE),
            valid_fiber_ids=final_axis,
        )
        merged[index] = max_probability_union(right, left_to_right)
    merged.flags.writeable = False
    return merged
