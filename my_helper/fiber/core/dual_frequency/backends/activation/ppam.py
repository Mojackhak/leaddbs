"""Pure probability operations for pPAM activation sensitivity.

Continuous probabilities are validated on the closed unit interval. Binary
fitting exposure uses the fixed inclusive threshold ``p(A) >= 0.5``.
"""

from __future__ import annotations

import numpy as np


FITTING_PROBABILITY_THRESHOLD = 0.5


class PPAMError(ValueError):
    """Raised when activation probabilities violate the pPAM contract."""


def validate_probabilities(
    probabilities: np.ndarray,
    *,
    name: str = "probabilities",
) -> np.ndarray:
    """Return an immutable float32 copy of valid activation probabilities."""

    try:
        array = np.asarray(probabilities)
    except (TypeError, ValueError) as exc:
        raise PPAMError(f"{name} must be a real numeric array") from exc
    if (
        array.ndim < 1
        or array.size == 0
        or array.dtype == object
        or not np.issubdtype(array.dtype, np.number)
        or np.iscomplexobj(array)
    ):
        raise PPAMError(f"{name} must be a nonempty real numeric array")
    if not np.all(np.isfinite(array)):
        raise PPAMError(f"{name} must contain only finite values")
    if np.any((array < 0.0) | (array > 1.0)):
        raise PPAMError(f"{name} must contain probabilities in [0, 1]")
    output = np.array(array, dtype=np.float32, order="C", copy=True)
    output.flags.writeable = False
    return output


def max_probability_union(
    probability_right: np.ndarray,
    probability_left_to_right: np.ndarray,
) -> np.ndarray:
    """Merge right-canonical probability arrays by elementwise maximum."""

    right = validate_probabilities(
        probability_right,
        name="probability_right",
    )
    left_to_right = validate_probabilities(
        probability_left_to_right,
        name="probability_left_to_right",
    )
    if right.shape != left_to_right.shape:
        raise PPAMError("right and left-to-right probabilities must have the same shape")
    merged = np.maximum(right, left_to_right)
    merged.flags.writeable = False
    return merged


def binary_activation(probabilities: np.ndarray) -> np.ndarray:
    """Return float32 exposure using the inclusive ``p(A) >= 0.5`` rule."""

    validated = validate_probabilities(probabilities)
    binary = (validated >= FITTING_PROBABILITY_THRESHOLD).astype(
        np.float32,
        copy=False,
    )
    binary.flags.writeable = False
    return binary
