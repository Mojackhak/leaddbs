"""Pure activation-axis, canonical mapping, and pPAM primitives."""

from .canonical_mapping import (
    LEFT_SIDE,
    RIGHT_SIDE,
    CanonicalMappingError,
    activation_universe,
    merge_right_canonical_probabilities,
    subset_probability_axis,
)
from .ppam import (
    FITTING_PROBABILITY_THRESHOLD,
    PPAMError,
    binary_activation,
    max_probability_union,
    validate_probabilities,
)

__all__ = [
    "FITTING_PROBABILITY_THRESHOLD",
    "LEFT_SIDE",
    "RIGHT_SIDE",
    "CanonicalMappingError",
    "PPAMError",
    "activation_universe",
    "binary_activation",
    "max_probability_union",
    "merge_right_canonical_probabilities",
    "subset_probability_axis",
    "validate_probabilities",
]
