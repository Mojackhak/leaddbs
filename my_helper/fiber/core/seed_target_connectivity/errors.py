"""Domain exceptions for seed-target connectivity statistics."""


class SeedTargetConnectivityError(RuntimeError):
    """Base exception for the reusable connectivity package."""


class ConfigurationError(SeedTargetConnectivityError, ValueError):
    """Raised when an algorithm configuration violates the public contract."""


class ROIResolutionError(SeedTargetConnectivityError, ValueError):
    """Raised when atlas discovery or ROI resolution cannot satisfy the contract."""
