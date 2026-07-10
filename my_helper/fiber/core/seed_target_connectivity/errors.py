"""Domain exceptions for seed-target connectivity statistics."""


class SeedTargetConnectivityError(RuntimeError):
    """Base exception for the reusable connectivity package."""


class ConfigurationError(SeedTargetConnectivityError, ValueError):
    """Raised when an algorithm configuration violates the public contract."""


class ROIResolutionError(SeedTargetConnectivityError, ValueError):
    """Raised when atlas discovery or ROI resolution cannot satisfy the contract."""


class ConnectomeError(SeedTargetConnectivityError, ValueError):
    """Raised when a streamline connectome violates its adapter contract."""


class TraversalError(SeedTargetConnectivityError, ValueError):
    """Raised when segment-aware voxel traversal receives invalid geometry."""


class MembershipError(SeedTargetConnectivityError, ValueError):
    """Raised when fiber membership cannot produce a valid run."""


class CacheError(SeedTargetConnectivityError, ValueError):
    """Raised when a membership cache is incomplete, incompatible, or corrupt."""


class StatisticsError(SeedTargetConnectivityError, ValueError):
    """Raised when connectivity statistics violate denominator contracts."""


class ArtifactError(SeedTargetConnectivityError, ValueError):
    """Raised when immutable run artifacts cannot satisfy their contract."""
