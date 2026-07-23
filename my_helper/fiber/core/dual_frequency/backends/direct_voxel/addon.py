"""Add-on direct-voxel observed backend with fold-specific nuisance inputs."""

from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ArtifactRef,
    AxisRef,
    FeatureAxisRef,
    IndexedArrayView,
    ObservedRequest,
    ObservedResult,
    SourceRecord,
    canonical_hash,
)
from ...contracts.requests import ScientificMatrixInput
from ..nuisance import (
    NuisancePlan,
    NuisancePlanError,
    build_addon_nuisance_plan as _build_shared_addon_nuisance_plan,
)
from ..protocols import ArtifactPublisher
from ..source_resolver import SourceResolution, resolve_source
from .kernel import (
    DirectVoxelGridWorkspace,
    GridCellComputation,
    GridCellMetrics,
)


NO_DELTA_BRANCH = "no_delta_reference"
ADJUSTED_BRANCH = "delta_reference_adjusted"


class AddonDirectVoxelBackendError(RuntimeError):
    """Raised when an add-on direct-voxel request cannot run safely."""


class AddonDirectVoxelDesignError(AddonDirectVoxelBackendError):
    """Expected branch-local nuisance input or design failure."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


CONTIGUOUS_VIEW_BUDGET_BYTES = 16 * 1024**3


def _materialize(
    value: ScientificMatrixInput,
    *,
    name: str,
    expected_axes: tuple[AxisRef, ...],
    expected_units: str | None,
    expected_space: str | None,
    artifact_store: ArtifactStore | None,
    view_max_bytes: int = CONTIGUOUS_VIEW_BUDGET_BYTES,
) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asarray(value, dtype=np.float64)
    if artifact_store is None:
        raise AddonDirectVoxelBackendError(
            f"{name} is artifact-backed but no ArtifactStore was provided"
        )
    if value.dtype is None or value.shape is None:
        raise AddonDirectVoxelBackendError(f"{name} must reference an array artifact")
    if isinstance(value, IndexedArrayView):
        materialized = artifact_store.materialize_indexed_array_view(
            value,
            max_bytes=view_max_bytes,
        )
    else:
        materialized = artifact_store.materialize(
            value,
            expected_dtype=value.dtype,
            expected_shape=value.shape,
            expected_axes=expected_axes,
            expected_units=expected_units,
            expected_space=expected_space,
        )
    return np.asarray(materialized, dtype=np.float64)


def _finite_vector(value: np.ndarray, name: str, count: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise AddonDirectVoxelDesignError(
            "invalid_nuisance_design",
            f"{name} must be a finite subject vector",
        )
    return array


def build_addon_nuisance_plan(
    reference_outcome: np.ndarray,
    branch: str,
    *,
    delta_full_scores: np.ndarray | None = None,
    delta_fold_scores: np.ndarray | None = None,
) -> NuisancePlan:
    """Preserve the direct-voxel API around the shared nuisance builder."""

    try:
        return _build_shared_addon_nuisance_plan(
            reference_outcome,
            branch,
            delta_full_scores=delta_full_scores,
            delta_fold_scores=delta_fold_scores,
        )
    except NuisancePlanError as exc:
        raise AddonDirectVoxelDesignError(exc.status, exc.detail) from exc


def evaluate_addon_grid(
    exposure: np.ndarray,
    outcome: np.ndarray,
    nuisance_plan: NuisancePlan,
    request: ObservedRequest,
) -> tuple[GridCellMetrics, ...]:
    """Evaluate the complete declared grid for one executable add-on branch."""

    return DirectVoxelGridWorkspace(
        exposure,
        outcome,
        nuisance_plan,
        request.outcome_direction,
        request.hard_computability,
    ).evaluate_grid(
        request.source_grid.tau_values,
        request.source_grid.coverage_values,
    )


def _selected_axis(
    request: ObservedRequest,
    computation: GridCellComputation,
) -> tuple[FeatureAxisRef, np.ndarray]:
    arrays = computation.arrays
    if arrays is None:
        raise AddonDirectVoxelBackendError("selected computation did not retain arrays")
    selected_union = arrays.full_valid_mask | np.any(arrays.fold_valid_masks, axis=0)
    selected_indices = np.flatnonzero(selected_union).astype(np.int64)
    if selected_indices.size == 0:
        raise AddonDirectVoxelBackendError("accepted source has no finite selected features")
    axis = AxisRef(
        axis_id=(
            f"{request.feature_axis.axis_id}:selected:{request.branch}:"
            f"tau-{computation.metrics.tau:g}:coverage-{computation.metrics.coverage}"
        ),
        count=int(selected_indices.size),
        sha256=canonical_hash(
            {
                "parent_axis_sha256": request.feature_axis.sha256,
                "branch": request.branch,
                "selected_indices": selected_indices.tolist(),
                "tau": computation.metrics.tau,
                "coverage": computation.metrics.coverage,
            }
        ),
    )
    return FeatureAxisRef(axis, "selected_addon_direct_voxel_feature_union"), selected_indices


def _resolution_payload(
    resolution: SourceResolution[GridCellMetrics],
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


class AddonDirectVoxelBackend:
    """Run one executable add-on direct-voxel branch over its source grid."""

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
        self.publisher = publisher
        self.artifact_store = artifact_store

    def _inputs(
        self,
        request: ObservedRequest,
    ) -> tuple[np.ndarray, np.ndarray, NuisancePlan]:
        if request.endpoint.model_family != "addon_voxel":
            raise AddonDirectVoxelBackendError(
                "AddonDirectVoxelBackend requires an addon_voxel endpoint"
            )
        if request.branch not in {NO_DELTA_BRANCH, ADJUSTED_BRANCH}:
            raise AddonDirectVoxelBackendError("unsupported add-on direct-voxel branch")
        if request.exposure_units != "V/m":
            raise AddonDirectVoxelBackendError("add-on direct-voxel exposure must use V/m")
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
        reference = _materialize(
            request.baseline,
            name="baseline",
            expected_axes=(request.subject_axis,),
            expected_units=(request.baseline.units if isinstance(request.baseline, ArtifactRef) else None),
            expected_space=(request.baseline.space if isinstance(request.baseline, ArtifactRef) else None),
            artifact_store=self.artifact_store,
        )
        count = request.subject_axis.count
        if exposure.shape != (count, request.feature_axis.count):
            raise AddonDirectVoxelBackendError("exposure shape changed after validation")
        outcome = _finite_vector(outcome, "outcome", count)
        reference = _finite_vector(reference, "reference outcome", count)

        delta_full: np.ndarray | None = None
        delta_folds: np.ndarray | None = None
        if request.branch == NO_DELTA_BRANCH:
            if request.nuisance_inputs:
                raise AddonDirectVoxelDesignError(
                    "invalid_nuisance_design",
                    "no-delta branch requires no nuisance_inputs",
                )
        else:
            if len(request.nuisance_inputs) != 2:
                raise AddonDirectVoxelDesignError(
                    "invalid_delta_reference_scaling",
                    "adjusted branch requires full and fold DeltaReferenceScore inputs",
                )
            delta_full = _materialize(
                request.nuisance_inputs[0],
                name="nuisance_inputs[0]",
                expected_axes=(request.subject_axis,),
                expected_units=(
                    request.nuisance_inputs[0].units
                    if isinstance(request.nuisance_inputs[0], ArtifactRef)
                    else None
                ),
                expected_space=(
                    request.nuisance_inputs[0].space
                    if isinstance(request.nuisance_inputs[0], ArtifactRef)
                    else None
                ),
                artifact_store=self.artifact_store,
            )
            delta_folds = _materialize(
                request.nuisance_inputs[1],
                name="nuisance_inputs[1]",
                expected_axes=(request.subject_axis, request.subject_axis),
                expected_units=(
                    request.nuisance_inputs[1].units
                    if isinstance(request.nuisance_inputs[1], ArtifactRef)
                    else None
                ),
                expected_space=(
                    request.nuisance_inputs[1].space
                    if isinstance(request.nuisance_inputs[1], ArtifactRef)
                    else None
                ),
                artifact_store=self.artifact_store,
            )
        plan = build_addon_nuisance_plan(
            reference,
            request.branch,
            delta_full_scores=delta_full,
            delta_fold_scores=delta_folds,
        )
        return exposure, outcome, plan

    def run(self, request: ObservedRequest) -> ObservedResult:
        """Evaluate and resolve one branch without assigning endpoint final role."""

        if not isinstance(request, ObservedRequest):
            raise TypeError("request must be an ObservedRequest")
        exposure, outcome, nuisance_plan = self._inputs(request)
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
                "branch": request.branch,
                "cells": [cell.as_json_dict() for cell in grid_metrics],
            },
            kind="addon_direct_voxel_grid_metrics",
        )
        artifacts: list[ArtifactRef] = [grid_artifact]
        selected_feature_axis: FeatureAxisRef | None = None
        selected_metrics: dict[str, Any] | None = None

        if resolution.selected is not None:
            selected = workspace.evaluate_cell(
                resolution.selected.tau,
                resolution.selected.coverage,
                retain_arrays=True,
            )
            if selected.metrics.as_json_dict() != resolution.selected.as_json_dict():
                raise AddonDirectVoxelBackendError(
                    "selected source recomputation differed from its scan result"
                )
            selected_feature_axis, selected_indices = _selected_axis(request, selected)
            selected_metrics = selected.metrics.as_json_dict()
            arrays = selected.arrays
            if arrays is None:
                raise AssertionError("selected arrays are missing")
            outcome_units = request.outcome.units if isinstance(request.outcome, ArtifactRef) else None
            artifacts.extend(
                (
                    self.publisher.array(
                        "selected_feature_indices.npy",
                        selected_indices,
                        kind="selected_feature_indices",
                        axes=(selected_feature_axis.axis,),
                        units=None,
                        space=request.exposure_space,
                    ),
                    self.publisher.array(
                        "selected_full_weights.npy",
                        arrays.full_weights[selected_indices],
                        kind="benefit_oriented_feature_weights",
                        axes=(selected_feature_axis.axis,),
                        units="coefficient",
                        space=request.exposure_space,
                    ),
                    self.publisher.array(
                        "selected_source_full_support_mask.npy",
                        arrays.full_support_mask,
                        kind="selected_source_full_support_mask",
                        axes=(request.feature_axis,),
                        units=None,
                        space=request.exposure_space,
                    ),
                    self.publisher.array(
                        "selected_source_full_valid_mask.npy",
                        arrays.full_valid_mask,
                        kind="selected_source_full_valid_mask",
                        axes=(request.feature_axis,),
                        units=None,
                        space=request.exposure_space,
                    ),
                    self.publisher.array(
                        "selected_source_fold_weights.npy",
                        arrays.fold_weights[:, selected_indices],
                        kind="loocv_benefit_oriented_feature_weights",
                        axes=(request.subject_axis, selected_feature_axis.axis),
                        units="coefficient",
                        space=request.exposure_space,
                    ),
                    self.publisher.array(
                        "selected_source_fold_valid_masks.npy",
                        arrays.fold_valid_masks[:, selected_indices],
                        kind="loocv_valid_feature_masks",
                        axes=(request.subject_axis, selected_feature_axis.axis),
                        units=None,
                        space=request.exposure_space,
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
            kind="addon_direct_voxel_source_resolution",
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


__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "AddonDirectVoxelBackend",
    "AddonDirectVoxelBackendError",
    "AddonDirectVoxelDesignError",
    "build_addon_nuisance_plan",
    "evaluate_addon_grid",
]
