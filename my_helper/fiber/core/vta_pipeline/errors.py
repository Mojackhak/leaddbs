"""Pipeline-specific exceptions."""


class VtaPipelineError(RuntimeError):
    """Base error for deterministic VTA pipeline failures."""


class ConfigError(VtaPipelineError):
    """Raised when a public VTA model profile is invalid."""


class StudyBaseError(VtaPipelineError):
    """Raised when canonical study stimulation records are invalid."""


class PlanningError(VtaPipelineError):
    """Raised when VTA task selection or DAG construction is invalid."""


class ArtifactError(VtaPipelineError):
    """Raised when artifact state cannot be changed without data loss."""
