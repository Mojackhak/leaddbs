"""Pipeline-specific exceptions."""


class VtaPipelineError(RuntimeError):
    """Base error for deterministic VTA pipeline failures."""


class ConfigError(VtaPipelineError):
    """Raised when a public VTA model profile is invalid."""


class StudyBaseError(VtaPipelineError):
    """Raised when canonical study stimulation records are invalid."""
