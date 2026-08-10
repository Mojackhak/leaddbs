"""Observed backend for individualized target activation burden."""

from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import ArtifactStore
from ...contracts import (
    ArtifactRef,
    AxisRef,
    FeatureAxisRef,
    ObservedResult,
    SourceRecord,
    TargetObservedRequest,
    canonical_hash,
)
from ..nuisance import NuisancePlan, NuisancePlanError, build_addon_nuisance_plan
from ..protocols import ArtifactPublisher
from ..source_resolver import SourceResolution, resolve_source
from .kernel import IndividualizedTargetGridWorkspace


class IndividualizedTargetBackendError(RuntimeError):
    """Raised when an individualized target request cannot be completed."""


class IndividualizedTargetDesignError(IndividualizedTargetBackendError):
    """Expected branch-local nuisance-design failure."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _materialize(
    artifact: ArtifactRef,
    store: ArtifactStore | None,
) -> np.ndarray:
    if store is None:
        raise IndividualizedTargetBackendError(
            "artifact-backed target input requires an ArtifactStore"
        )
    return np.asarray(
        store.materialize(
            artifact,
            expected_dtype=artifact.dtype,
            expected_shape=artifact.shape,
            expected_axes=artifact.axis_refs,
            expected_units=artifact.units,
            expected_space=artifact.space,
        )
    )


def _resolution_payload(
    resolution: SourceResolution,
    selected_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source_status": resolution.source_status,
        "prediction_status": resolution.prediction_status,
        "threshold_source": resolution.threshold_source,
        "selected_tau": (
            resolution.selected.tau if resolution.selected is not None else None
        ),
        "selected_coverage": (
            resolution.selected.coverage
            if resolution.selected is not None
            else None
        ),
        "adjacent_support": resolution.adjacent_support,
        "failure_reason": resolution.failure_reason,
        "selected_metrics": selected_metrics,
    }


def build_target_nuisance_plan(
    request: TargetObservedRequest,
    baseline: np.ndarray,
    artifact_store: ArtifactStore | None,
) -> NuisancePlan:
    """Build the branch-specific nuisance plan for one target request."""

    if request.branch == "reference":
        if request.nuisance_inputs:
            raise IndividualizedTargetBackendError(
                "reference individualized targets accept baseline as the only "
                "nuisance covariate"
            )
        full_nuisance = np.asarray(baseline, dtype=np.float64)[:, None]
        return NuisancePlan(
            full_covariates=full_nuisance,
            fold_covariates=np.broadcast_to(
                full_nuisance,
                (
                    request.subject_axis.count,
                    request.subject_axis.count,
                    1,
                ),
            ),
        )
    delta_full: np.ndarray | None = None
    delta_folds: np.ndarray | None = None
    if request.branch == "delta_reference_adjusted":
        if len(request.nuisance_inputs) != 2:
            raise IndividualizedTargetDesignError(
                "invalid_delta_reference_scaling",
                "adjusted target branch requires full and fold "
                "DeltaReferenceScore inputs",
            )
        delta_full = np.asarray(
            _materialize(request.nuisance_inputs[0], artifact_store),
            dtype=np.float64,
        )
        delta_folds = np.asarray(
            _materialize(request.nuisance_inputs[1], artifact_store),
            dtype=np.float64,
        )
    elif request.nuisance_inputs:
        raise IndividualizedTargetDesignError(
            "invalid_nuisance_design",
            "no-delta target branch cannot receive extra nuisance inputs",
        )
    try:
        return build_addon_nuisance_plan(
            baseline,
            request.branch,
            delta_full_scores=delta_full,
            delta_fold_scores=delta_folds,
        )
    except NuisancePlanError as exc:
        raise IndividualizedTargetDesignError(
            exc.status,
            exc.detail,
        ) from exc


class IndividualizedTargetBackend:
    """Run one reference or add-on target endpoint over its source grid."""

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

    def run(self, request: TargetObservedRequest) -> ObservedResult:
        """Execute observed target LOOCV and publish the selected source."""

        if not isinstance(request, TargetObservedRequest):
            raise TypeError("request must be a TargetObservedRequest")
        burdens = np.asarray(
            _materialize(request.patient_burdens, self.artifact_store),
            dtype=np.float64,
        )
        support = np.asarray(
            _materialize(request.patient_support, self.artifact_store),
            dtype=bool,
        )
        outcome = np.asarray(
            _materialize(request.outcome, self.artifact_store),
            dtype=np.float64,
        )
        baseline = np.asarray(
            _materialize(request.baseline, self.artifact_store),
            dtype=np.float64,
        )
        nuisance_plan = build_target_nuisance_plan(
            request,
            baseline,
            self.artifact_store,
        )
        workspace = IndividualizedTargetGridWorkspace(
            burdens,
            support,
            request.source_grid.tau_values,
            outcome,
            nuisance_plan,
            request.outcome_direction,
            request.hard_computability,
        )
        grid_metrics = workspace.evaluate_grid(request.source_grid.coverage_values)
        resolution = resolve_source(grid_metrics, request.source_grid)
        artifacts: list[ArtifactRef] = [
            self.publisher.document(
                "grid_metrics.json",
                {
                    "endpoint_id": request.endpoint.identifier,
                    "cells": [cell.as_json_dict() for cell in grid_metrics],
                },
                kind="individualized_target_grid_metrics",
            )
        ]
        selected_axis: FeatureAxisRef | None = None
        selected_metrics: dict[str, Any] | None = None

        if resolution.selected is not None:
            computation = workspace.evaluate_cell(
                resolution.selected.tau,
                resolution.selected.coverage,
                retain_arrays=True,
            )
            selected_metrics = computation.metrics.as_json_dict()
            arrays = computation.arrays
            if arrays is None:
                raise IndividualizedTargetBackendError(
                    "selected target computation lacks retained arrays"
                )
            selected_union = arrays.full_valid_mask | np.any(
                arrays.fold_valid_masks,
                axis=0,
            )
            selected_indices = np.flatnonzero(selected_union).astype(np.int64)
            if selected_indices.size == 0:
                raise IndividualizedTargetBackendError(
                    "accepted target source has no finite selected targets"
                )
            target_ids = np.asarray(
                _materialize(request.target_ids, self.artifact_store)
            )
            selected_ids = target_ids[selected_indices]
            axis = AxisRef(
                axis_id=(
                    f"{request.target_axis.axis_id}:selected:"
                    f"tau-{resolution.selected.tau:g}:"
                    f"coverage-{resolution.selected.coverage}"
                ),
                count=int(selected_indices.size),
                sha256=canonical_hash(
                    {
                        "parent_axis": request.target_axis.sha256,
                        "selected_target_ids": selected_ids.tolist(),
                        "tau": resolution.selected.tau,
                        "coverage": resolution.selected.coverage,
                    }
                ),
            )
            selected_axis = FeatureAxisRef(
                axis,
                "selected_individualized_target_union",
            )
            artifacts.extend(
                (
                    self.publisher.array(
                        "all_target_ids.npy",
                        target_ids,
                        kind="individualized_all_target_ids",
                        axes=(request.target_axis,),
                        units="target_id",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_weights.npy",
                        arrays.full_weights,
                        kind="individualized_all_full_target_weights",
                        axes=(request.target_axis,),
                        units="coefficient",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_nominal_p.npy",
                        arrays.full_nominal_p,
                        kind="individualized_all_full_target_nominal_p",
                        axes=(request.target_axis,),
                        units="probability",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_fdr_q.npy",
                        arrays.full_fdr_q,
                        kind="individualized_all_full_target_fdr_q",
                        axes=(request.target_axis,),
                        units="probability",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_support_mask.npy",
                        arrays.full_support_mask,
                        kind="individualized_all_full_target_support_mask",
                        axes=(request.target_axis,),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_centers.npy",
                        arrays.full_centers,
                        kind="individualized_all_full_target_centers",
                        axes=(request.target_axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_scales.npy",
                        arrays.full_scales,
                        kind="individualized_all_full_target_scales",
                        axes=(request.target_axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_full_valid_mask.npy",
                        arrays.full_valid_mask,
                        kind="individualized_all_full_target_valid_mask",
                        axes=(request.target_axis,),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_fold_weights.npy",
                        arrays.fold_weights,
                        kind="individualized_all_fold_target_weights",
                        axes=(request.subject_axis, request.target_axis),
                        units="coefficient",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_fold_centers.npy",
                        arrays.fold_centers,
                        kind="individualized_all_fold_target_centers",
                        axes=(request.subject_axis, request.target_axis),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_fold_scales.npy",
                        arrays.fold_scales,
                        kind="individualized_all_fold_target_scales",
                        axes=(request.subject_axis, request.target_axis),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_fold_support_masks.npy",
                        arrays.fold_support_masks,
                        kind="individualized_all_fold_target_support_masks",
                        axes=(request.subject_axis, request.target_axis),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "all_fold_valid_masks.npy",
                        arrays.fold_valid_masks,
                        kind="individualized_all_fold_target_valid_masks",
                        axes=(request.subject_axis, request.target_axis),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "selected_target_indices.npy",
                        selected_indices,
                        kind="individualized_selected_target_indices",
                        axes=(axis,),
                        units="index",
                        space=None,
                    ),
                    self.publisher.array(
                        "target_ids.npy",
                        selected_ids,
                        kind="individualized_target_ids",
                        axes=(axis,),
                        units="target_id",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_weights.npy",
                        arrays.full_weights[selected_indices],
                        kind="individualized_full_target_weights",
                        axes=(axis,),
                        units="coefficient",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_centers.npy",
                        arrays.full_centers[selected_indices],
                        kind="individualized_full_target_centers",
                        axes=(axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_scales.npy",
                        arrays.full_scales[selected_indices],
                        kind="individualized_full_target_scales",
                        axes=(axis,),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_scores.npy",
                        arrays.full_scores,
                        kind="individualized_full_target_scores",
                        axes=(request.subject_axis,),
                        units="score",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_support_mask.npy",
                        arrays.full_support_mask[selected_indices],
                        kind="individualized_full_target_support_mask",
                        axes=(axis,),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "full_valid_mask.npy",
                        arrays.full_valid_mask[selected_indices],
                        kind="individualized_full_target_valid_mask",
                        axes=(axis,),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_weights.npy",
                        arrays.fold_weights[:, selected_indices],
                        kind="individualized_fold_target_weights",
                        axes=(request.subject_axis, axis),
                        units="coefficient",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_centers.npy",
                        arrays.fold_centers[:, selected_indices],
                        kind="individualized_fold_target_centers",
                        axes=(request.subject_axis, axis),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_scales.npy",
                        arrays.fold_scales[:, selected_indices],
                        kind="individualized_fold_target_scales",
                        axes=(request.subject_axis, axis),
                        units="V/m",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_support_masks.npy",
                        arrays.fold_support_masks[:, selected_indices],
                        kind="individualized_fold_target_support_masks",
                        axes=(request.subject_axis, axis),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_valid_masks.npy",
                        arrays.fold_valid_masks[:, selected_indices],
                        kind="individualized_fold_target_valid_masks",
                        axes=(request.subject_axis, axis),
                        units="binary",
                        space=None,
                    ),
                    self.publisher.array(
                        "fold_scores.npy",
                        arrays.fold_scores,
                        kind="individualized_fold_target_scores",
                        axes=(request.subject_axis, request.subject_axis),
                        units="score",
                        space=None,
                    ),
                    self.publisher.array(
                        "heldout_scores.npy",
                        arrays.heldout_scores,
                        kind="individualized_loocv_heldout_scores",
                        axes=(request.subject_axis,),
                        units="score",
                        space=None,
                    ),
                    self.publisher.array(
                        "heldout_predictions.npy",
                        arrays.heldout_predictions,
                        kind="loocv_model_predictions",
                        axes=(request.subject_axis,),
                        units=request.outcome.units,
                        space=None,
                    ),
                    self.publisher.array(
                        "baseline_predictions.npy",
                        arrays.baseline_predictions,
                        kind="loocv_baseline_predictions",
                        axes=(request.subject_axis,),
                        units=request.outcome.units,
                        space=None,
                    ),
                )
            )

        artifacts.append(
            self.publisher.document(
                "source_resolution.json",
                _resolution_payload(resolution, selected_metrics),
                kind="individualized_target_source_resolution",
            )
        )
        source = SourceRecord(
            endpoint=request.endpoint,
            input_status="valid",
            source_status=resolution.source_status,
            prediction_status=resolution.prediction_status,
            threshold_source=resolution.threshold_source,
            selected_tau=(
                resolution.selected.tau if resolution.selected is not None else None
            ),
            selected_coverage=(
                resolution.selected.coverage
                if resolution.selected is not None
                else None
            ),
            adjacent_support=resolution.adjacent_support,
            feature_axis=selected_axis,
            artifacts=tuple(artifacts),
        )
        return ObservedResult(source=source, artifacts=tuple(artifacts))


__all__ = [
    "IndividualizedTargetBackend",
    "IndividualizedTargetBackendError",
    "IndividualizedTargetDesignError",
    "build_target_nuisance_plan",
]
