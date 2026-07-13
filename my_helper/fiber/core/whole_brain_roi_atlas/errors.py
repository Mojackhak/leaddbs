"""Domain errors for whole-brain ROI atlas construction."""


class AtlasBuildError(RuntimeError):
    """Base class for atlas build failures."""


class ConfigurationError(AtlasBuildError):
    """Raised for invalid build configuration."""


class LabelError(AtlasBuildError):
    """Raised for invalid labeling metadata or voxel labels."""


class ResamplingError(AtlasBuildError):
    """Raised when integer label resampling fails validation."""


class EndpointCensusError(AtlasBuildError):
    """Raised for malformed connectomes or irreconcilable endpoint counts."""


class PublicationError(AtlasBuildError):
    """Raised when immutable atlas publication cannot proceed."""
