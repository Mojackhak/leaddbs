"""Backend protocols for the generic dual-frequency runtime."""

from .protocols import (
    ActivationBackend,
    FormalBackend,
    ObservedBackend,
    ReportingBackend,
    SensitivityBackend,
)

__all__ = [
    "ActivationBackend",
    "FormalBackend",
    "ObservedBackend",
    "ReportingBackend",
    "SensitivityBackend",
]
