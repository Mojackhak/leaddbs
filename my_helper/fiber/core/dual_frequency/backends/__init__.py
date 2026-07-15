"""Backend protocols for the generic dual-frequency runtime."""

from .protocols import (
    ActivationBackend,
    ArtifactPublisher,
    FormalBackend,
    ObservedBackend,
    ReportingBackend,
)

__all__ = [
    "ActivationBackend",
    "ArtifactPublisher",
    "FormalBackend",
    "ObservedBackend",
    "ReportingBackend",
]
