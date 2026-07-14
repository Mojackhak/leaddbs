"""Typed failures for the seed-wide MRtrix pipeline."""


class MrtrixSeedTargetError(RuntimeError):
    """Base class for expected pipeline failures."""


class ConfigurationError(MrtrixSeedTargetError):
    """Raised when the YAML contract is invalid."""


class DiscoveryError(MrtrixSeedTargetError):
    """Raised when a subject input cannot be resolved unambiguously."""


class ValidationError(MrtrixSeedTargetError):
    """Raised when a resolved input violates the scientific contract."""


class ToolError(MrtrixSeedTargetError):
    """Raised when an external tool fails or produces an invalid artifact."""


class ExecutionInterrupted(MrtrixSeedTargetError):
    """Raised after an explicit stop request terminates active producers."""


class CoverageError(MrtrixSeedTargetError):
    """Raised when the seed-wide budget cannot cover every target."""


class PublicationError(MrtrixSeedTargetError):
    """Raised when safe transactional publication cannot complete."""
