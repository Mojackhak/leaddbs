"""Add-on normative-fiber preparation and observed backend."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...cache import ArtifactStore, IndexedArrayReader
from ...contracts import (
    ArtifactRef,
    BranchRecord,
    IndexedArrayView,
    ObservedRequest,
    SensitiveRecord,
    SourceRecord,
)
from ..nuisance import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    NuisancePlan,
    NuisancePlanError,
    build_addon_nuisance_plan,
)
from ..protocols import ArtifactPublisher
from .reference import (
    ReferenceFiberBackend,
    ReferenceFiberBackendError,
    _fiber_ids,
    _finite_vector,
    _materialize,
)


class AddonFiberBackendError(ReferenceFiberBackendError):
    """Raised when an add-on normative-fiber request cannot run safely."""


class AddonFiberDesignError(AddonFiberBackendError):
    """Expected branch-local nuisance input or design failure."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = str(status)
        self.detail = str(detail)


@dataclass(frozen=True)
class AddonFiberExposure:
    """Continuous add-on exposure after locked reference-overlap exclusion."""

    exposure: np.ndarray
    reference_active: np.ndarray
    selected_reference_tau: float | None

    def __post_init__(self) -> None:
        exposure = np.asanyarray(self.exposure)
        active = np.asanyarray(self.reference_active)
        if exposure.ndim != 2 or active.shape != exposure.shape:
            raise AddonFiberBackendError(
                "prepared exposure and reference-active mask must be matching matrices"
            )
        if exposure.dtype != np.dtype(np.float32) or active.dtype != np.dtype(bool):
            raise AddonFiberBackendError(
                "prepared exposure must be float32 and reference-active mask must be bool"
            )
        for start in range(0, exposure.shape[1], 65_536):
            block = np.asarray(exposure[:, start : start + 65_536])
            if not np.all(np.isfinite(block)) or np.any(block < 0):
                raise AddonFiberBackendError(
                    "prepared add-on exposure must contain finite nonnegative values"
                )
        if self.selected_reference_tau is not None:
            tau = float(self.selected_reference_tau)
            if not math.isfinite(tau) or tau <= 0:
                raise AddonFiberBackendError(
                    "selected_reference_tau must be finite and positive"
                )
            object.__setattr__(self, "selected_reference_tau", tau)
        exposure.flags.writeable = False
        active.flags.writeable = False
        object.__setattr__(self, "exposure", exposure)
        object.__setattr__(self, "reference_active", active)


def _reference_tau(
    reference_model: SourceRecord | SensitiveRecord,
    *,
    matched_reference_endpoint_id: str,
    matched_reference_connectome_id: str,
) -> float | None:
    endpoint_id = str(matched_reference_endpoint_id).strip()
    connectome_id = str(matched_reference_connectome_id).strip()
    if not endpoint_id:
        raise AddonFiberBackendError(
            "matched_reference_endpoint_id must be nonempty"
        )
    if not connectome_id or connectome_id == "none":
        raise AddonFiberBackendError(
            "matched_reference_connectome_id must identify a normative connectome"
        )
    if not isinstance(reference_model, (SourceRecord, SensitiveRecord)):
        raise TypeError("reference_model must be a SourceRecord or SensitiveRecord")
    if reference_model.endpoint.identifier != endpoint_id:
        raise AddonFiberBackendError(
            "reference overlap record does not match matched_reference_endpoint_id"
        )
    if reference_model.endpoint.connectome_id != connectome_id:
        raise AddonFiberBackendError(
            "reference overlap record does not match matched_reference_connectome_id"
        )
    if isinstance(reference_model, SourceRecord):
        if reference_model.endpoint.model_family != "reference_fiber":
            raise AddonFiberBackendError(
                "reference overlap requires a reference_fiber source"
            )
        if reference_model.input_status != "valid":
            raise AddonFiberBackendError(
                "reference input failure cannot be converted into absent overlap"
            )
        if reference_model.source_status not in {
            "pre_specified_accepted",
            "scan_fallback_accepted",
        }:
            return None
        if reference_model.selected_tau is None:
            raise AddonFiberBackendError("accepted reference source has no selected tau")
        return float(reference_model.selected_tau)
    if isinstance(reference_model, SensitiveRecord):
        if reference_model.endpoint.model_family != "reference_fiber":
            raise AddonFiberBackendError(
                "reference overlap requires reference_fiber sensitivity evidence"
            )
        if reference_model.cell_computability_status != "computable":
            raise AddonFiberBackendError(
                "reference overlap cannot use noncomputable sensitivity evidence"
            )
        return float(reference_model.evaluated_tau)
    raise AssertionError("unreachable reference-model type")


def prepare_addon_fiber_exposure(
    addon_exposure: np.ndarray,
    reference_component_exposure: np.ndarray,
    reference_model: SourceRecord | SensitiveRecord,
    *,
    matched_reference_endpoint_id: str,
    matched_reference_connectome_id: str,
    destination: np.ndarray | None = None,
    reference_active_destination: np.ndarray | None = None,
    feature_chunk_size: int = 65_536,
) -> AddonFiberExposure:
    """Apply inclusive reference overlap before add-on Coverage is evaluated."""

    addon = np.asanyarray(addon_exposure)
    reference = np.asanyarray(reference_component_exposure)
    if addon.ndim != 2 or reference.shape != addon.shape:
        raise AddonFiberBackendError(
            "add-on and reference-component exposures must be matching matrices"
        )
    if addon.dtype == object or reference.dtype == object:
        raise AddonFiberBackendError(
            "component exposures must contain numeric values"
        )
    if not np.issubdtype(addon.dtype, np.number) or not np.issubdtype(
        reference.dtype, np.number
    ):
        raise AddonFiberBackendError("component exposures must contain numeric values")
    if np.iscomplexobj(addon) or np.iscomplexobj(reference):
        raise AddonFiberBackendError("component exposures must contain real values")
    if type(feature_chunk_size) is not int or feature_chunk_size < 1:
        raise AddonFiberBackendError("feature_chunk_size must be a positive integer")

    if destination is None:
        prepared = np.empty(addon.shape, dtype=np.float32)
    else:
        prepared = np.asanyarray(destination)
        if prepared.shape != addon.shape or prepared.dtype != np.dtype(np.float32):
            raise AddonFiberBackendError(
                "destination must be a matching writable float32 matrix"
            )
        if not prepared.flags.writeable:
            raise AddonFiberBackendError("destination must be writable")
        if np.shares_memory(prepared, addon) or np.shares_memory(prepared, reference):
            raise AddonFiberBackendError("destination must not alias an input exposure")

    if reference_active_destination is None:
        reference_active = np.empty(addon.shape, dtype=bool)
    else:
        reference_active = np.asanyarray(reference_active_destination)
        if reference_active.shape != addon.shape or reference_active.dtype != np.dtype(bool):
            raise AddonFiberBackendError(
                "reference_active_destination must be a matching writable bool matrix"
            )
        if not reference_active.flags.writeable:
            raise AddonFiberBackendError("reference_active_destination must be writable")
        if np.shares_memory(reference_active, addon) or np.shares_memory(
            reference_active, reference
        ):
            raise AddonFiberBackendError(
                "reference_active_destination must not alias an input exposure"
            )
    if np.shares_memory(prepared, reference_active):
        raise AddonFiberBackendError(
            "prepared and reference-active destinations must not alias"
        )

    tau = _reference_tau(
        reference_model,
        matched_reference_endpoint_id=matched_reference_endpoint_id,
        matched_reference_connectome_id=matched_reference_connectome_id,
    )
    for start in range(0, addon.shape[1], feature_chunk_size):
        stop = min(start + feature_chunk_size, addon.shape[1])
        addon_block = np.asarray(addon[:, start:stop], dtype=np.float32)
        reference_block = np.asarray(reference[:, start:stop], dtype=np.float32)
        if (
            not np.all(np.isfinite(addon_block))
            or not np.all(np.isfinite(reference_block))
            or np.any(addon_block < 0)
            or np.any(reference_block < 0)
        ):
            raise AddonFiberBackendError(
                "component exposures must contain finite nonnegative values"
            )
        active_block = (
            np.zeros(addon_block.shape, dtype=bool)
            if tau is None
            else reference_block >= tau
        )
        reference_active[:, start:stop] = active_block
        prepared[:, start:stop] = np.where(active_block, 0.0, addon_block)
    for value in (prepared, reference_active):
        flush = getattr(value, "flush", None)
        if callable(flush):
            flush()
    return AddonFiberExposure(
        exposure=prepared,
        reference_active=reference_active,
        selected_reference_tau=tau,
    )


class AddonFiberBackend(ReferenceFiberBackend):
    """Run one add-on normative-fiber branch using the shared fiber engine."""

    def __init__(
        self,
        publisher: ArtifactPublisher,
        *,
        artifact_store: ArtifactStore | None = None,
        feature_chunk_size: int = 65_536,
    ) -> None:
        super().__init__(
            publisher,
            artifact_store=artifact_store,
            feature_chunk_size=feature_chunk_size,
        )

    def _inputs(
        self,
        request: ObservedRequest,
    ) -> tuple[np.ndarray | IndexedArrayReader, np.ndarray, NuisancePlan, np.ndarray]:
        if request.endpoint.model_family != "addon_fiber":
            raise AddonFiberBackendError(
                "AddonFiberBackend requires an addon_fiber endpoint"
            )
        if request.branch not in {NO_DELTA_BRANCH, ADJUSTED_BRANCH}:
            raise AddonFiberBackendError("unsupported add-on normative-fiber branch")
        if request.feature_ids is None:
            raise AddonFiberBackendError("add-on normative fiber requires feature_ids")

        exposure: np.ndarray | IndexedArrayReader | None = None
        if not isinstance(request.exposure, IndexedArrayView):
            exposure = _materialize(
                request.exposure,
                name="exposure",
                expected_axes=(request.subject_axis, request.feature_axis),
                expected_units=request.exposure_units,
                expected_space=request.exposure_space,
                artifact_store=self.artifact_store,
                memory_map=True,
                max_block_columns=self.feature_chunk_size,
            )
        outcome = _materialize(
            request.outcome,
            name="outcome",
            expected_axes=(request.subject_axis,),
            expected_units=(
                request.outcome.units if isinstance(request.outcome, ArtifactRef) else None
            ),
            expected_space=(
                request.outcome.space if isinstance(request.outcome, ArtifactRef) else None
            ),
            artifact_store=self.artifact_store,
            memory_map=False,
        )
        reference_outcome = _materialize(
            request.baseline,
            name="baseline",
            expected_axes=(request.subject_axis,),
            expected_units=(
                request.baseline.units if isinstance(request.baseline, ArtifactRef) else None
            ),
            expected_space=(
                request.baseline.space if isinstance(request.baseline, ArtifactRef) else None
            ),
            artifact_store=self.artifact_store,
            memory_map=False,
        )
        feature_ids = _materialize(
            request.feature_ids,
            name="feature_ids",
            expected_axes=(request.feature_axis,),
            expected_units=(
                request.feature_ids.units
                if isinstance(request.feature_ids, ArtifactRef)
                else None
            ),
            expected_space=(
                request.feature_ids.space
                if isinstance(request.feature_ids, ArtifactRef)
                else None
            ),
            artifact_store=self.artifact_store,
            memory_map=True,
        )
        n_subjects = request.subject_axis.count
        outcome_vector = _finite_vector(outcome, "outcome", n_subjects)
        reference_vector = _finite_vector(
            reference_outcome,
            "reference outcome",
            n_subjects,
        )

        delta_full: np.ndarray | None = None
        delta_folds: np.ndarray | None = None
        if request.branch == NO_DELTA_BRANCH:
            if request.nuisance_inputs:
                raise AddonFiberDesignError(
                    "invalid_nuisance_design",
                    "no-delta branch requires no nuisance_inputs",
                )
        else:
            if len(request.nuisance_inputs) != 2:
                raise AddonFiberDesignError(
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
                memory_map=False,
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
                memory_map=False,
            )
        try:
            nuisance_plan = build_addon_nuisance_plan(
                reference_vector,
                request.branch,
                delta_full_scores=delta_full,
                delta_fold_scores=delta_folds,
            )
        except NuisancePlanError as exc:
            raise AddonFiberDesignError(exc.status, exc.detail) from exc
        canonical_fiber_ids = _fiber_ids(feature_ids, request.feature_axis.count)
        if exposure is None:
            exposure = _materialize(
                request.exposure,
                name="exposure",
                expected_axes=(request.subject_axis, request.feature_axis),
                expected_units=request.exposure_units,
                expected_space=request.exposure_space,
                artifact_store=self.artifact_store,
                memory_map=True,
                max_block_columns=self.feature_chunk_size,
            )
        try:
            if exposure.shape != (n_subjects, request.feature_axis.count):
                raise AddonFiberBackendError(
                    "exposure shape changed after validation"
                )
            for start in range(0, exposure.shape[1], self.feature_chunk_size):
                block = np.asarray(
                    exposure[:, start : start + self.feature_chunk_size]
                )
                if not np.all(np.isfinite(block)) or np.any(block < 0):
                    raise AddonFiberBackendError(
                        "prepared add-on exposure must contain finite "
                        "nonnegative values"
                    )
        except Exception:
            if isinstance(exposure, IndexedArrayReader):
                exposure.close()
            raise
        return (
            exposure,
            outcome_vector,
            nuisance_plan,
            canonical_fiber_ids,
        )

    def evaluate_sensitive_at_formal_branch(
        self,
        request: ObservedRequest,
        formal_branch: BranchRecord,
    ) -> SensitiveRecord:
        """Evaluate sensitive evidence only at the matching formal branch source."""

        if not isinstance(formal_branch, BranchRecord):
            raise TypeError("formal_branch must be a BranchRecord")
        if formal_branch.branch != request.branch:
            raise AddonFiberBackendError(
                "sensitive add-on branch does not match the formal selected branch"
            )
        if formal_branch.source is None:
            raise AddonFiberBackendError("formal branch has no accepted source")
        return super().evaluate_sensitive_at_formal_source(
            request,
            formal_branch.source,
        )


__all__ = [
    "ADJUSTED_BRANCH",
    "NO_DELTA_BRANCH",
    "AddonFiberBackend",
    "AddonFiberBackendError",
    "AddonFiberDesignError",
    "AddonFiberExposure",
    "prepare_addon_fiber_exposure",
]
