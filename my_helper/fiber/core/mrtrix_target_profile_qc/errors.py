"""Domain exceptions for target-profile quality control."""


class TargetProfileQcError(RuntimeError):
    """Base class for expected QC failures."""


class ConfigurationError(TargetProfileQcError):
    """Raised when the compact QC YAML is invalid."""


class ValidationError(TargetProfileQcError):
    """Raised when an exact tracking input cannot be validated."""


class PublicationError(TargetProfileQcError):
    """Raised when QC artifacts cannot be safely published."""

