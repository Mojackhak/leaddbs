"""Narrow callable protocols implemented by extracted scientific backends."""

from __future__ import annotations

from typing import Protocol

from ..contracts.records import ArtifactRef, FinalModelRecord
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


class ObservedBackend(Protocol):
    def run_observed(self, request: ObservedRequest) -> ObservedResult: ...


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
