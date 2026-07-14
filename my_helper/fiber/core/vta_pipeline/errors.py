"""Pipeline-specific exceptions."""


class VtaPipelineError(RuntimeError):
    """Base error for deterministic VTA pipeline failures."""


class ConfigError(VtaPipelineError):
    """Raised when a public VTA model profile is invalid."""


class StudyBaseError(VtaPipelineError):
    """Raised when canonical study stimulation records are invalid."""


class PlanningError(VtaPipelineError):
    """Raised when VTA task selection or DAG construction is invalid."""


class SubjectManifestError(VtaPipelineError):
    """Raised when a subject execution manifest violates its contract."""


class ArtifactError(VtaPipelineError):
    """Raised when artifact state cannot be changed without data loss."""


class RuntimeInputError(VtaPipelineError):
    """Raised when Lead-DBS runtime inputs are unavailable or ambiguous."""


class ExecutionUnavailableError(VtaPipelineError):
    """Raised while the execution bridge is intentionally disconnected."""


class EventProtocolError(VtaPipelineError):
    """Raised when framed MATLAB telemetry violates vta_event_v1."""


class MatlabProcessError(VtaPipelineError):
    """Raised when a MATLAB process exits unsuccessfully."""
