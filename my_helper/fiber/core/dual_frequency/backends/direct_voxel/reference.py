"""Reference direct-voxel observed backend and run-scoped artifact publication."""

from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ArtifactRef,
    AxisRef,
    FeatureAxisRef,
    ObservedRequest,
    ObservedResult,
    SourceRecord,
    canonical_hash,
)
from ...contracts.requests import ScientificInput
from ..nuisance import NuisancePlan
from ..protocols import ArtifactPublisher
from .kernel import DirectVoxelGridWorkspace, GridCellComputation
from .source_resolver import SourceResolution, resolve_source


class ReferenceDirectVoxelBackendError(RuntimeError):
    """Raised when a reference direct-voxel request cannot be completed safely."""


def _materialize(
    value: ScientificInput,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    expected_space: str | None,
    artifact_store: ArtifactStore | None,
) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asarray(value, dtype=np.float64)
    if artifact_store is None:
        raise ReferenceDirectVoxelBackendError(
            f"{name} is artifact-backed but no ArtifactStore was provided"
        )
    if value.dtype is None or value.shape is None:
        raise ReferenceDirectVoxelBackendError(f"{name} must reference an array artifact")
    array = artifact_store.materialize(
        value,
        expected_dtype=value.dtype,
        expected_shape=value.shape,
        expected_axes=expected_axes,
        expected_units=expected_units,
        expected_space=expected_space,
    )
    return np.asarray(array, dtype=np.float64)


def _selected_axis(
    request: ObservedRequest,
    computation: GridCellComputation,
) -> tuple[FeatureAxisRef, np.ndarray]:
    if computation.arrays is None:
        raise ReferenceDirectVoxelBackendError("selected computation did not retain arrays")
    selected_union = computation.arrays.full_valid_mask | np.any(
        computation.arrays.fold_valid_masks,
        axis=0,
    )
    selected_indices = np.flatnonzero(selected_union).astype(np.int64)
    if selected_indices.size == 0:
        raise ReferenceDirectVoxelBackendError("accepted source has no finite selected features")
    selected = computation.metrics
    axis = AxisRef(
        axis_id=(
            f"{request.feature_axis.axis_id}:selected:"
            f"tau-{selected.tau:g}:coverage-{selected.coverage}"
        ),
        count=int(selected_indices.size),
        sha256=canonical_hash(
            {
                "parent_axis_sha256": request.feature_axis.sha256,
                "selected_indices": selected_indices.tolist(),
                "tau": selected.tau,
                "coverage": selected.coverage,
            }
        ),
    )
    return FeatureAxisRef(axis, "selected_direct_voxel_feature_union"), selected_indices


def _resolution_payload(
    resolution: SourceResolution,
    selected_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source_status": resolution.source_status,
        "prediction_status": resolution.prediction_status,
        "threshold_source": resolution.threshold_source,
        "selected_tau": resolution.selected.tau if resolution.selected is not None else None,
        "selected_coverage": (
            resolution.selected.coverage if resolution.selected is not None else None
        ),
        "adjacent_support": resolution.adjacent_support,
        "failure_reason": resolution.failure_reason,
        "selected_metrics": selected_metrics,
    }


class ReferenceDirectVoxelBackend:
    """Run one reference endpoint over its complete declared source grid."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        if not isinstance(publisher, ArtifactPublisher):
            raise TypeError("publisher must implement ArtifactPublisher")
        if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore or None")
        self.artifact_store = artifact_store
        self.publisher = publisher

    def run(self, request: ObservedRequest) -> ObservedResult:
        """Execute observed LOOCV, resolve one source, and publish bounded artifacts."""

        if not isinstance(request, ObservedRequest):
            raise TypeError("request must be an ObservedRequest")
        if request.endpoint.model_family != "reference_voxel":
            raise ReferenceDirectVoxelBackendError(
                "ReferenceDirectVoxelBackend requires a reference_voxel endpoint"
            )
        if request.branch != "reference":
            raise ReferenceDirectVoxelBackendError("reference direct-voxel branch must be 'reference'")
        if request.nuisance_inputs:
            raise ReferenceDirectVoxelBackendError(
                "reference direct-voxel accepts baseline as its only nuisance covariate"
            )
        if request.exposure_units != "V/m":
            raise ReferenceDirectVoxelBackendError(
                "reference direct-voxel exposure_units must be 'V/m'"
            )

        exposure = _materialize(
            request.exposure,
            name="exposure",
            expected_axes=(request.subject_axis, request.feature_axis),
            expected_units=request.exposure_units,
            expected_space=request.exposure_space,
            artifact_store=self.artifact_store,
        )
        outcome = _materialize(
            request.outcome,
            name="outcome",
            expected_axes=(request.subject_axis,),
            expected_units=(request.outcome.units if isinstance(request.outcome, ArtifactRef) else None),
            expected_space=(request.outcome.space if isinstance(request.outcome, ArtifactRef) else None),
            artifact_store=self.artifact_store,
        )
        baseline = _materialize(
            request.baseline,
            name="baseline",
            expected_axes=(request.subject_axis,),
            expected_units=(request.baseline.units if isinstance(request.baseline, ArtifactRef) else None),
            expected_space=(request.baseline.space if isinstance(request.baseline, ArtifactRef) else None),
            artifact_store=self.artifact_store,
        )
        nuisance = np.asarray(baseline, dtype=np.float64)[:, None]
        nuisance_plan = NuisancePlan(
            full_covariates=nuisance,
            fold_covariates=np.broadcast_to(
                nuisance,
                (outcome.size, outcome.size, nuisance.shape[1]),
            ),
        )
        workspace = DirectVoxelGridWorkspace(
            exposure,
            outcome,
            nuisance_plan,
            request.outcome_direction,
            request.hard_computability,
        )
        grid_metrics = workspace.evaluate_grid(
            request.source_grid.tau_values,
            request.source_grid.coverage_values,
        )
        resolution = resolve_source(grid_metrics, request.source_grid)
        grid_artifact = self.publisher.document(
            "grid_metrics.json",
            {
                "endpoint_id": request.endpoint.identifier,
                "cells": [cell.as_json_dict() for cell in grid_metrics],
            },
            kind="direct_voxel_grid_metrics",
        )
        artifacts: list[ArtifactRef] = [grid_artifact]
        selected_feature_axis: FeatureAxisRef | None = None
        selected_metrics: dict[str, Any] | None = None

        if resolution.selected is not None:
            selected_computation = workspace.evaluate_cell(
                resolution.selected.tau,
                resolution.selected.coverage,
                retain_arrays=True,
            )
            if selected_computation.metrics.as_json_dict() != resolution.selected.as_json_dict():
                raise ReferenceDirectVoxelBackendError(
                    "selected source recomputation differed from its scan result"
                )
            selected_feature_axis, selected_indices = _selected_axis(
                request,
                selected_computation,
            )
            selected_metrics = selected_computation.metrics.as_json_dict()
            arrays = selected_computation.arrays
            if arrays is None:
                raise AssertionError("selected arrays are missing")
            feature_space = request.exposure_space
            outcome_units = request.outcome.units if isinstance(request.outcome, ArtifactRef) else None
            artifacts.extend(
                (
                    self.publisher.array(
                        "selected_feature_indices.npy",
                        selected_indices,
                        kind="selected_feature_indices",
                        axes=(selected_feature_axis.axis,),
                        units=None,
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_full_weights.npy",
                        arrays.full_weights[selected_indices],
                        kind="benefit_oriented_feature_weights",
                        axes=(selected_feature_axis.axis,),
                        units="coefficient",
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_full_scores.npy",
                        arrays.full_scores,
                        kind="continuous_weighted_mean_scores",
                        axes=(request.subject_axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "selected_source_full_support_mask.npy",
                        arrays.full_support_mask,
                        kind="selected_source_full_support_mask",
                        axes=(request.feature_axis,),
                        units=None,
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_source_full_valid_mask.npy",
                        arrays.full_valid_mask,
                        kind="selected_source_full_valid_mask",
                        axes=(request.feature_axis,),
                        units=None,
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_source_fold_weights.npy",
                        arrays.fold_weights[:, selected_indices],
                        kind="loocv_benefit_oriented_feature_weights",
                        axes=(request.subject_axis, selected_feature_axis.axis),
                        units="coefficient",
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_source_fold_valid_masks.npy",
                        arrays.fold_valid_masks[:, selected_indices],
                        kind="loocv_valid_feature_masks",
                        axes=(request.subject_axis, selected_feature_axis.axis),
                        units=None,
                        space=feature_space,
                    ),
                    self.publisher.array(
                        "selected_fold_scores.npy",
                        arrays.fold_scores,
                        kind="loocv_fold_score_matrix",
                        axes=(request.subject_axis, request.subject_axis),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "selected_heldout_scores.npy",
                        arrays.heldout_scores,
                        kind="loocv_heldout_scores",
                        axes=(request.subject_axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "selected_heldout_predictions.npy",
                        arrays.heldout_predictions,
                        kind="loocv_model_predictions",
                        axes=(request.subject_axis,),
                        units=outcome_units,
                        space=None,
                    ),
                    self.publisher.array(
                        "selected_baseline_predictions.npy",
                        arrays.baseline_predictions,
                        kind="loocv_baseline_predictions",
                        axes=(request.subject_axis,),
                        units=outcome_units,
                        space=None,
                    ),
                )
            )

        resolution_artifact = self.publisher.document(
            "source_resolution.json",
            _resolution_payload(resolution, selected_metrics),
            kind="direct_voxel_source_resolution",
        )
        artifacts.append(resolution_artifact)
        source = SourceRecord(
            endpoint=request.endpoint,
            input_status="valid",
            source_status=resolution.source_status,
            prediction_status=resolution.prediction_status,
            threshold_source=resolution.threshold_source,
            selected_tau=(resolution.selected.tau if resolution.selected is not None else None),
            selected_coverage=(
                resolution.selected.coverage if resolution.selected is not None else None
            ),
            adjacent_support=resolution.adjacent_support,
            feature_axis=selected_feature_axis,
            artifacts=tuple(artifacts),
        )
        return ObservedResult(source=source, artifacts=tuple(artifacts))
