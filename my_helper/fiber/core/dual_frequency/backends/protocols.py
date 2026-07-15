"""Narrow callable protocols implemented by extracted scientific backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

from ..contracts.records import ArtifactRef, AxisRef, FinalModelRecord
from ..contracts.requests import (
    ActivationArtifact,
    ActivationRequest,
    FormalRequest,
    FormalResult,
    ObservedRequest,
    ObservedResult,
    SensitivityRequest,
    SensitivityResult,
)


@runtime_checkable
class ArtifactPublisher(Protocol):
    """Publish immutable run-scoped artifacts without exposing paths to backends."""

    def array(
        self,
        filename: str,
        value: np.ndarray,
        *,
        kind: str,
        axes: tuple[AxisRef, ...],
        units: str | None,
        space: str | None,
    ) -> ArtifactRef: ...

    def document(
        self,
        filename: str,
        payload: dict[str, Any],
        *,
        kind: str,
    ) -> ArtifactRef: ...


class ObservedBackend(Protocol):
    def run(self, request: ObservedRequest) -> ObservedResult: ...


class FormalBackend(Protocol):
    def run_formal(self, request: FormalRequest) -> FormalResult: ...


class SensitivityBackend(Protocol):
    def run_sensitivity(self, request: SensitivityRequest) -> SensitivityResult: ...


class ActivationBackend(Protocol):
    def run_activation(self, request: ActivationRequest) -> ActivationArtifact: ...


class ReportingBackend(Protocol):
    def build_report(
        self,
        final_model: FinalModelRecord,
        artifacts: tuple[ArtifactRef, ...],
    ) -> tuple[ArtifactRef, ...]: ...
