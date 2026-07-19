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
    PPAM_SAMPLE_COUNT,
    PPAMError,
    binary_activation,
    max_probability_union,
    validate_probabilities,
    validate_ten_sample_probabilities,
)
from .fitting import (
    PPAMActivationBackend,
    PPAMFitResult,
    PPAMFittingError,
    compute_ppam_permutation_block,
    fit_ppam_activation,
)
from .ossdbs import (
    DEFAULT_ROW_WORKERS,
    MissingAcceptanceFixture,
    OSSBackendError,
    OSSRowBatchArtifact,
    OSSRowBatchRequest,
    OSSRowInput,
    OSSRowMaterializer,
    OSSRowProduct,
    OSSScientificSettings,
    build_oss_row_cache_key,
)

__all__ = [
    "FITTING_PROBABILITY_THRESHOLD",
    "PPAM_SAMPLE_COUNT",
    "DEFAULT_ROW_WORKERS",
    "LEFT_SIDE",
    "RIGHT_SIDE",
    "CanonicalMappingError",
    "PPAMError",
    "PPAMActivationBackend",
    "PPAMFitResult",
    "PPAMFittingError",
    "compute_ppam_permutation_block",
    "MissingAcceptanceFixture",
    "OSSBackendError",
    "OSSRowBatchArtifact",
    "OSSRowBatchRequest",
    "OSSRowInput",
    "OSSRowMaterializer",
    "OSSRowProduct",
    "OSSScientificSettings",
    "activation_universe",
    "binary_activation",
    "build_oss_row_cache_key",
    "fit_ppam_activation",
    "max_probability_union",
    "merge_right_canonical_probabilities",
    "subset_probability_axis",
    "validate_probabilities",
    "validate_ten_sample_probabilities",
]
