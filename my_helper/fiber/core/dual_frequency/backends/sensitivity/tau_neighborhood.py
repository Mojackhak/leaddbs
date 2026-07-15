"""Exact-axis 0.9x/1.1x tau-neighborhood sensitivity."""

from __future__ import annotations

from dataclasses import dataclass

from ...contracts import ArtifactRef, SensitivityResult
from ..protocols import ArtifactPublisher
from .common import (
    FinalSensitivityTarget,
    ScientificArrayProvider,
    SensitivityStrategyError,
    evaluate_fixed_cell,
    publish_sensitivity_payload,
    selected_tau_coverage,
)


@dataclass(frozen=True, slots=True)
class TauNeighborhoodRequest:
    """A final-linked neighborhood request with no resolver inputs."""

    target: FinalSensitivityTarget

    def __post_init__(self) -> None:
        if not isinstance(self.target, FinalSensitivityTarget):
            raise SensitivityStrategyError(
                "tau-neighborhood target must be a FinalSensitivityTarget"
            )


class TauNeighborhoodStrategy:
    """Evaluate absolute 0.9x and 1.1x tau cells at selected Coverage."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        array_provider: ScientificArrayProvider | None = None,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        self.publisher = publisher
        self.array_provider = array_provider

    def run(self, request: TauNeighborhoodRequest) -> SensitivityResult:
        if not isinstance(request, TauNeighborhoodRequest):
            raise TypeError("request must be a TauNeighborhoodRequest")
        selected_tau, selected_coverage = selected_tau_coverage(
            request.target.final_model
        )
        cells = (
            ("lower_0p9", 0.9 * selected_tau),
            ("upper_1p1", 1.1 * selected_tau),
        )
        payload_cells: list[dict[str, object]] = []
        score_artifacts: list[ArtifactRef] = []
        for label, tau in cells:
            evidence = evaluate_fixed_cell(
                request.target,
                tau=tau,
                coverage=selected_coverage,
                array_provider=self.array_provider,
            )
            payload_cells.append({"neighborhood_cell": label, **evidence.as_payload()})
            if evidence.full_scores is not None:
                score_artifacts.append(
                    self.publisher.array(
                        f"tau_neighborhood_{label}_full_scores.npy",
                        evidence.full_scores,
                        kind="tau_neighborhood_continuous_dose_scores",
                        axes=(request.target.observed_request.subject_axis,),
                        units="V/m",
                        space=None,
                    )
                )
        payload = {
            "schema_version": "dual_frequency_tau_neighborhood_v1",
            "target_id": request.target.final_model.identifier,
            "selected_tau": selected_tau,
            "selected_coverage": selected_coverage,
            "tau_multipliers": [0.9, 1.1],
            "dose_rule": "continuous_inside_coverage_defined_support",
            "cells": payload_cells,
        }
        return publish_sensitivity_payload(
            publisher=self.publisher,
            target_id=request.target.final_model.identifier,
            sensitivity_kind="tau_neighborhood",
            filename="tau_neighborhood_metrics.json",
            artifact_kind="tau_neighborhood_metrics",
            payload=payload,
            extra_artifacts=tuple(score_artifacts),
        )


__all__ = ["TauNeighborhoodRequest", "TauNeighborhoodStrategy"]
