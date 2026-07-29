"""Explicit production service adapters for the generic workflow runtime."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
import json
from typing import Callable, TypeVar

import numpy as np

from ..backends.activation.canonical_mapping import activation_universe
from ..backends.activation.fitting import (
    PPAMActivationBackend,
    aggregate_ppam_observed_state,
    compute_ppam_permutation_block_from_workspace,
    ppam_observed_state,
    prepare_ppam_fit_workspace,
)
from ..backends.activation.operator_scratch import close_ppam_operator_scratch
from ..backends.activation.ossdbs import OSSRowBatchArtifact
from ..backends.activation.ppam import (
    binary_activation,
    validate_ten_sample_probabilities,
)
from ..backends.delta_reference import (
    build_delta_reference_fiber,
    build_delta_reference_voxel,
)
from ..backends.direct_voxel.addon import (
    AddonDirectVoxelBackend,
    AddonDirectVoxelDesignError,
)
from ..backends.direct_voxel.reference import ReferenceDirectVoxelBackend
from ..backends.formal import (
    DirectVoxelFormalBackend,
    FinalInSampleBackend,
    NormativeFiberFormalBackend,
    compute_direct_voxel_bootstrap_block,
    compute_normative_fiber_bootstrap_block,
)
from ..backends.formal.common import (
    canonical_fiber_ids,
    combine_bootstrap_blocks,
    finite_exposure,
    finite_vector,
    materialize_array,
)
from ..backends.interaction.branch_resolver import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    branch_failure_record,
    branch_record_from_observed,
)
from ..backends.normative_fiber.addon import AddonFiberBackend, AddonFiberDesignError
from ..backends.normative_fiber.reference import ReferenceFiberBackend
from ..backends.nuisance import NuisancePlanError
from ..backends.protocols import BootstrapNuisanceProvider
from ..backends.sensitivity import (
    AddonExposureSensitivityRequest,
    AddonExposureSensitivityStrategy,
    CollinearityInput,
    FinalFiberControlRequest,
    FinalFiberControlStrategy,
    FinalSensitivityTarget,
    JitterReplicateProvider,
    ObservedFiberControlRequest,
    ObservedFiberControlStrategy,
    SpatialJitterRequest,
    SpatialJitterSettings,
    SpatialJitterStrategy,
    SupportDiagnosticInput,
    TauNeighborhoodRequest,
    TauNeighborhoodStrategy,
)
from ..cache import ArtifactStore, ContentAddressedCache, RunScopedArtifactPublisher
from ..catalog import EndpointRecord
from ..config import ResolvedWorkflow
from ..contracts import (
    ActivationArtifact,
    ActivationRequest,
    ArtifactRef,
    BootstrapBlockRecord,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    FormalOperatorScratchRecord,
    FormalRequest,
    FormalResult,
    IndexedArrayView,
    NormativeFiberScoreSettings,
    ObservedRequest,
    ObservedResult,
    OSSSharedOmegaGroupRecord,
    PreparedExposureRecord,
    PPAMObservedWorkspaceRecord,
    PPAMPermutationBlockRecord,
    ReferenceDependencyRecord,
    ResamplingBlockRecord,
    ResamplingScheduleRecord,
    SensitiveRecord,
    SensitivityResult,
    ScientificArrayRef,
    SourceRecord,
)
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from ..workflow.executor import ServiceResult, TaskExecutionRequest
from ..workflow.registry import RegisteredService, ServiceRegistry
from ..workflow.state import BranchPlan, derive_branch_plan, realize_final
from .activation_provider import OSSActivationProvider, OSSActivationRuntimeRequest
from .bootstrap_provider import (
    StudyBootstrapNuisanceProvider,
    StudyBootstrapNuisanceProviderError,
)
from .formal_operator_workspace import (
    formal_operator_scratch_record,
    validated_formal_operator_scratch_descriptor,
)
from .formal_bootstrap_blocks import (
    load_formal_bootstrap_block,
    publish_formal_bootstrap_block,
)
from .formal_permutation_blocks import (
    load_formal_permutation_block,
    publish_formal_permutation_block,
)
from .formal_resampling import (
    load_formal_resampling_schedule,
    publish_formal_resampling_schedule,
)
from .input_provider import RuntimeInputProvider, StudyRuntimeInputProvider
from .jitter_blocks import (
    CachedJitterReplicateProvider,
    prepare_jitter_exposure_block,
)
from .jitter_provider import StudyJitterReplicateProvider
from .oss_shared_omega import (
    omega_ids_for_shared_group,
    prepare_oss_omega_max_rows,
)
from .ppam_observed_workspace import (
    activation_request_from_ppam_workspace,
    load_ppam_observed_state,
    ppam_observed_workspace_record,
    publish_ppam_activation_result,
    publish_ppam_nuisance_failure,
    publish_ppam_observed_state,
    publish_ppam_operator_scratch,
    reopen_ppam_workspace_from_record,
)
from .ppam_permutation_blocks import (
    load_ppam_permutation_block,
    publish_ppam_permutation_block,
)
from .ppam_resampling import (
    load_ppam_resampling_schedule,
    publish_ppam_resampling_schedule,
)


ADAPTER_VERSION = "1"


class ServiceAdapterError(RuntimeError):
    """Raised when a planned task lacks a valid typed adapter input."""


class ServiceAdapterCapabilityError(ServiceAdapterError):
    """Raised when a required provider capability is unavailable."""


RecordT = TypeVar("RecordT")
ServiceHandler = Callable[[TaskExecutionRequest], ServiceResult]


def _provider(request: TaskExecutionRequest) -> RuntimeInputProvider:
    provider = request.provider
    if not isinstance(provider, RuntimeInputProvider):
        raise ServiceAdapterError(
            "task provider must implement the RuntimeInputProvider protocol"
        )
    return provider


def _configuration(request: TaskExecutionRequest) -> ResolvedWorkflow:
    configuration = getattr(request.provider, "configuration", None)
    if not isinstance(configuration, ResolvedWorkflow):
        raise ServiceAdapterCapabilityError(
            "provider must expose the validated ResolvedWorkflow as configuration"
        )
    return configuration


def _artifact_store(request: TaskExecutionRequest) -> ArtifactStore:
    if not isinstance(request.artifact_store, ArtifactStore):
        raise ServiceAdapterCapabilityError(
            "artifact-backed numerical services require an ArtifactStore"
        )
    return request.artifact_store


def _publisher(request: TaskExecutionRequest) -> RunScopedArtifactPublisher:
    return RunScopedArtifactPublisher(
        request.output_dir,
        request.task.task_id,
        ADAPTER_VERSION,
    )


def _run_root(request: TaskExecutionRequest) -> Path:
    """Resolve the run root from historical or attempt-isolated work paths."""

    for parent in request.output_dir.parents:
        if parent.name == "work":
            return parent.parent
    raise ServiceAdapterError(
        "task output directory is not beneath the run work root"
    )


def _records(request: TaskExecutionRequest, record_type: type[RecordT]) -> tuple[RecordT, ...]:
    return tuple(
        state.record
        for state in request.dependencies.values()
        if isinstance(state.record, record_type)
    )


def _one_record(
    request: TaskExecutionRequest,
    record_type: type[RecordT],
    *,
    required: bool = True,
) -> RecordT | None:
    records = _records(request, record_type)
    if len(records) > 1:
        raise ServiceAdapterError(
            f"task {request.task.task_id!r} received multiple {record_type.__name__} records"
        )
    if not records:
        if required:
            raise ServiceAdapterError(
                f"task {request.task.task_id!r} requires one {record_type.__name__}"
            )
        return None
    return records[0]


def _endpoint_input_record(
    request: TaskExecutionRequest,
    endpoint_id: str,
) -> EndpointInputRecord:
    matches = tuple(
        record
        for record in _records(request, EndpointInputRecord)
        if record.endpoint.identifier == endpoint_id
    )
    if len(matches) != 1:
        raise ServiceAdapterError(
            f"task {request.task.task_id!r} requires exactly one EndpointInputRecord "
            f"for endpoint {endpoint_id!r}"
        )
    return matches[0]


def _prepared_exposure_record(
    request: TaskExecutionRequest,
    endpoint_id: str,
) -> PreparedExposureRecord:
    matches = tuple(
        record
        for record in _records(request, PreparedExposureRecord)
        if record.endpoint.identifier == endpoint_id
    )
    if len(matches) != 1:
        raise ServiceAdapterError(
            f"task {request.task.task_id!r} requires exactly one PreparedExposureRecord "
            f"for endpoint {endpoint_id!r}"
        )
    return matches[0]


def _endpoint(request: TaskExecutionRequest) -> EndpointRecord:
    endpoint = _provider(request).endpoint(request.task.endpoint_id)
    if endpoint.endpoint_id != request.task.endpoint_id:
        raise ServiceAdapterError("provider returned a different endpoint identity")
    return endpoint


def _artifact(record: SourceRecord | SensitiveRecord, kind: str) -> ArtifactRef:
    matches = tuple(item for item in record.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise ServiceAdapterError(
            f"{type(record).__name__} requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _reference_evidence_accepted(record: SourceRecord | SensitiveRecord | None) -> bool:
    if isinstance(record, SourceRecord):
        return (
            record.input_status == "valid"
            and record.source_status in ACCEPTED_SOURCE_STATUSES
        )
    if isinstance(record, SensitiveRecord):
        return (
            record.input_status == "valid"
            and record.cell_computability_status == "computable"
        )
    return False


def _reference_prediction_status(
    record: SourceRecord | SensitiveRecord | None,
) -> str | None:
    if not _reference_evidence_accepted(record):
        return None
    assert record is not None
    return record.prediction_status


def _selected_tau_coverage(
    record: SourceRecord | SensitiveRecord,
) -> tuple[float, int]:
    if isinstance(record, SourceRecord):
        if record.selected_tau is None or record.selected_coverage is None:
            raise ServiceAdapterError("accepted source has no selected tau/Coverage")
        return float(record.selected_tau), int(record.selected_coverage)
    return float(record.evaluated_tau), int(record.evaluated_coverage)


def _final_estimator(model_family: str) -> str:
    return (
        "continuous_dose_signed_peak"
        if model_family.endswith("fiber")
        else "continuous_dose_mean"
    )


def _final_model_from_source(source: SourceRecord) -> FinalModelRecord:
    tau, coverage = _selected_tau_coverage(source)
    return FinalModelRecord(
        endpoint=source.endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            source.endpoint.identifier,
            "reference",
            tau,
            coverage,
            _final_estimator(source.endpoint.model_family),
        ),
        selected_source=source,
        selected_branch=None,
        artifacts=source.artifacts,
    )


def _final_model_from_branch(
    branch: BranchRecord,
    *,
    fallback: bool,
) -> FinalModelRecord:
    if branch.source is None:
        raise ServiceAdapterError("realized add-on branch has no selected source")
    tau, coverage = _selected_tau_coverage(branch.source)
    return FinalModelRecord(
        endpoint=branch.endpoint,
        final_status=(
            "fallback_final_realized" if fallback else "final_model_realized"
        ),
        realization_role="fallback_final" if fallback else "primary",
        final_key=FinalModelKey(
            branch.endpoint.identifier,
            branch.branch,
            tau,
            coverage,
            _final_estimator(branch.endpoint.model_family),
        ),
        selected_source=None,
        selected_branch=branch,
        artifacts=branch.artifacts,
    )


def _branch_intent(
    dependency: ReferenceDependencyRecord,
) -> tuple[str, bool]:
    prediction = _reference_prediction_status(dependency.reference_record)
    if prediction == "error_predictive":
        return ADJUSTED_BRANCH, True
    return NO_DELTA_BRANCH, False


def _branch_plan(
    dependency: ReferenceDependencyRecord,
    delta: DeltaReferenceBundle | None,
) -> BranchPlan:
    delta_status = delta.input_status if delta is not None else "missing"
    return derive_branch_plan(dependency, delta_status)


def _selection_facts(selection: FinalSelectionRecord) -> dict[str, bool]:
    realized = selection.final_model is not None
    return {
        "final_model_realized": realized,
        "formal_source_available": realized,
    }


def _validate_endpoint_input(request: TaskExecutionRequest) -> ServiceResult:
    record = _provider(request).publish_endpoint_input(
        request.task.endpoint_id,
        _publisher(request),
    )
    return ServiceResult.from_record(
        record,
        facts={"endpoint_input_ready": record.readiness_status == "ready"},
    )


def _prepare_exposure(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    dependency = _one_record(request, ReferenceDependencyRecord, required=False)
    assert endpoint_input is not None
    record = _provider(request).publish_prepared_exposure(
        endpoint_input,
        dependency,
        _publisher(request),
    )
    return ServiceResult.from_record(record)


def _run_reference_observed(
    request: TaskExecutionRequest,
    *,
    model_family: str,
) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    prepared = _one_record(request, PreparedExposureRecord)
    assert endpoint_input is not None and prepared is not None
    observed_request = _provider(request).observed_request(
        endpoint_input,
        prepared,
        branch="reference",
    )
    publisher = _publisher(request)
    if model_family == "reference_voxel":
        result = ReferenceDirectVoxelBackend(
            publisher,
            artifact_store=request.artifact_store,
        ).run(observed_request)
    elif model_family == "reference_fiber":
        result = ReferenceFiberBackend(
            publisher,
            artifact_store=request.artifact_store,
        ).run(observed_request)
    else:
        raise ServiceAdapterError(f"unsupported observed model family {model_family!r}")
    return ServiceResult.from_record(result)


def _resolve_reference_source(request: TaskExecutionRequest) -> ServiceResult:
    observed = _one_record(request, ObservedResult)
    if observed is None or observed.source is None:
        raise ServiceAdapterError("reference resolver requires an observed SourceRecord")
    accepted = observed.source.source_status in ACCEPTED_SOURCE_STATUSES
    return ServiceResult.from_record(
        observed.source,
        facts={
            "reference_source_accepted": accepted,
            "formal_source_available": accepted,
        },
    )


def _realize_reference_final(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    source = _one_record(request, SourceRecord, required=False)
    assert endpoint_input is not None
    causal = tuple(request.task.dependencies)
    if endpoint_input.readiness_status != "ready":
        selection = FinalSelectionRecord(
            endpoint=endpoint_input.endpoint,
            selection_status="no_final_model",
            final_model=None,
            reason_codes=("endpoint_input_not_ready",),
            causal_task_ids=causal,
        )
    elif source is None:
        selection = FinalSelectionRecord(
            endpoint=endpoint_input.endpoint,
            selection_status="dependency_failure",
            final_model=None,
            reason_codes=("source_record_unavailable",),
            causal_task_ids=causal,
        )
    elif source.source_status in ACCEPTED_SOURCE_STATUSES:
        selection = FinalSelectionRecord(
            endpoint=source.endpoint,
            selection_status="final_model_realized",
            final_model=_final_model_from_source(source),
            reason_codes=("selected_primary",),
            causal_task_ids=causal,
        )
    else:
        status = (
            "execution_failure"
            if source.input_status == "execution_failure"
            else "no_final_model"
        )
        selection = FinalSelectionRecord(
            endpoint=source.endpoint,
            selection_status=status,
            final_model=None,
            reason_codes=(
                "source_execution_failure"
                if status == "execution_failure"
                else "absent_no_stable_grid",
            ),
            causal_task_ids=causal,
        )
    return ServiceResult.from_record(selection, facts=_selection_facts(selection))


def _bind_reference_dependency(request: TaskExecutionRequest) -> ServiceResult:
    endpoint = _endpoint(request)
    candidates = (
        *_records(request, SourceRecord),
        *_records(request, SensitiveRecord),
    )
    if len(candidates) > 1:
        raise ServiceAdapterError(
            "reference dependency received multiple SourceRecord or SensitiveRecord values"
        )
    reference = candidates[0] if candidates else None
    input_status = reference.input_status if reference is not None else "input_failure"
    dependency_status = (
        "execution_failure"
        if input_status == "execution_failure"
        else "input_failure"
        if input_status != "valid"
        else "ready"
    )
    if endpoint.matched_reference_endpoint_id is None:
        raise ServiceAdapterError("add-on endpoint has no matched reference identity")
    record = ReferenceDependencyRecord(
        addon_endpoint=endpoint.key,
        matched_reference_endpoint_id=endpoint.matched_reference_endpoint_id,
        dependency_status=dependency_status,
        reference_record=reference,
        delta_reference=None,
    )
    return ServiceResult.from_record(
        record,
        facts={
            "reference_dependency_ready": dependency_status == "ready",
            "reference_source_accepted": _reference_evidence_accepted(reference),
        },
    )


def _invalid_delta_from_preparation(
    prepared: PreparedExposureRecord,
    reference: SourceRecord | SensitiveRecord,
) -> DeltaReferenceBundle:
    tau, coverage = _selected_tau_coverage(reference)
    return DeltaReferenceBundle(
        input_status="input_failure",
        support_status="not_applicable",
        selected_reference_tau=tau,
        selected_reference_coverage=coverage,
        full_scores=None,
        fold_scores=None,
        support_rows=None,
        support_qc=None,
        failure_stage="prepared_exposure",
        failure_detail=prepared.delta_reference_reason_code,
    )


def _fiber_score_settings(configuration: ResolvedWorkflow) -> NormativeFiberScoreSettings:
    score = configuration.normative_fiber.score
    return NormativeFiberScoreSettings(
        sweet_fraction=score.sweet_fraction,
        sour_fraction=score.sour_fraction,
        weighted_peak_fraction=score.weighted_peak_fraction,
        sweet_selected_min_count=score.sweet_selected_min_count,
        sour_selected_min_count=score.sour_selected_min_count,
        weighted_peak_min_count=score.weighted_peak_min_count,
    )


def _build_delta_reference(
    request: TaskExecutionRequest,
    *,
    model_family: str,
) -> ServiceResult:
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    dependency = _one_record(request, ReferenceDependencyRecord)
    prepared = _prepared_exposure_record(request, request.task.endpoint_id)
    assert endpoint_input is not None and dependency is not None and prepared is not None
    reference_input = _endpoint_input_record(
        request,
        dependency.matched_reference_endpoint_id,
    )
    reference = dependency.reference_record
    if reference is None or not _reference_evidence_accepted(reference):
        raise ServiceAdapterError("DeltaReferenceScore requires accepted reference evidence")
    if prepared.delta_reference_input_status != "ready":
        invalid = _invalid_delta_from_preparation(prepared, reference)
        return ServiceResult.from_record(invalid, facts={"delta_inputs_valid": False})
    if (
        endpoint_input.subject_axis is None
        or reference_input.subject_axis is None
        or prepared.reference_condition_exposure is None
        or prepared.addon_reference_component_exposure is None
    ):
        raise ServiceAdapterError("DeltaReferenceScore prepared artifacts are incomplete")

    configuration = _configuration(request)
    publisher = _publisher(request)
    store = _artifact_store(request)
    if model_family == "addon_voxel":
        if not isinstance(reference, SourceRecord):
            raise ServiceAdapterError("add-on voxel requires a SourceRecord dependency")
        record = build_delta_reference_voxel(
            matched_reference_endpoint_id=dependency.matched_reference_endpoint_id,
            reference_source=reference,
            selected_feature_indices=_artifact(reference, "selected_feature_indices"),
            full_weights=_artifact(reference, "benefit_oriented_feature_weights"),
            fold_weights=_artifact(reference, "loocv_benefit_oriented_feature_weights"),
            reference_condition_exposure=prepared.reference_condition_exposure,
            addon_reference_component_exposure=(
                prepared.addon_reference_component_exposure
            ),
            subject_axis=endpoint_input.subject_axis,
            reference_subject_axis=reference_input.subject_axis,
            addon_subject_ids=endpoint_input.included_subject_ids,
            reference_subject_ids=reference_input.included_subject_ids,
            parent_feature_axis=prepared.feature_axis,
            support_profile=configuration.direct_voxel.delta_reference_support,
            publisher=publisher,
            artifact_store=store,
        )
    elif model_family == "addon_fiber":
        reference_prepared = _prepared_exposure_record(
            request,
            dependency.matched_reference_endpoint_id,
        )
        record = build_delta_reference_fiber(
            matched_reference_endpoint_id=dependency.matched_reference_endpoint_id,
            matched_reference_connectome_id=prepared.endpoint.connectome_id,
            reference_record=reference,
            parent_fiber_ids=prepared.feature_ids,
            valid_fiber_ids=_artifact(reference, "normative_fiber_valid_union_ids"),
            full_weights=_artifact(reference, "benefit_oriented_fiber_weights"),
            fold_weights=_artifact(reference, "loocv_benefit_oriented_fiber_weights"),
            fold_valid_masks=_artifact(reference, "loocv_valid_fiber_masks"),
            reference_condition_exposure=prepared.reference_condition_exposure,
            addon_reference_component_exposure=(
                prepared.addon_reference_component_exposure
            ),
            subject_axis=endpoint_input.subject_axis,
            reference_subject_axis=reference_input.subject_axis,
            addon_subject_ids=endpoint_input.included_subject_ids,
            reference_subject_ids=reference_input.included_subject_ids,
            parent_fiber_axis=prepared.feature_axis,
            reference_parent_fiber_axis=reference_prepared.feature_axis,
            fiber_score_settings=_fiber_score_settings(configuration),
            support_profile=configuration.normative_fiber.delta_reference_support,
            publisher=publisher,
            artifact_store=store,
        )
    else:
        raise ServiceAdapterError(f"unsupported Delta model family {model_family!r}")
    return ServiceResult.from_record(record, facts={"delta_inputs_valid": record.valid})


def _run_addon_branch(
    request: TaskExecutionRequest,
    *,
    model_family: str,
    sensitive: bool,
) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    dependency = _one_record(request, ReferenceDependencyRecord)
    prepared = _one_record(request, PreparedExposureRecord)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    assert endpoint_input is not None and dependency is not None and prepared is not None
    branch = request.task.key.branch
    intended, fallback = _branch_intent(dependency)
    if branch == ADJUSTED_BRANCH and (delta is None or not delta.valid):
        record = branch_failure_record(
            endpoint_input.endpoint,
            branch,
            intended_branch=intended,
            fallback_eligible=fallback,
            input_status="input_failure",
            nuisance_design_status="invalid_delta_reference_scaling",
            failure_stage="input",
            failure_detail="DeltaReferenceScore input is unavailable",
        )
        return ServiceResult.from_record(record)

    observed_request = _provider(request).observed_request(
        endpoint_input,
        prepared,
        branch=branch,
        delta_reference=delta,
    )
    publisher = _publisher(request)
    try:
        if model_family == "addon_voxel":
            observed = AddonDirectVoxelBackend(
                publisher,
                artifact_store=request.artifact_store,
            ).run(observed_request)
        elif model_family == "addon_fiber":
            observed = AddonFiberBackend(
                publisher,
                artifact_store=request.artifact_store,
            ).run(observed_request)
        else:
            raise ServiceAdapterError(f"unsupported add-on model family {model_family!r}")
    except (AddonDirectVoxelDesignError, AddonFiberDesignError) as exc:
        record = branch_failure_record(
            endpoint_input.endpoint,
            branch,
            intended_branch=intended,
            fallback_eligible=fallback,
            input_status="valid",
            nuisance_design_status=exc.status,
            failure_stage="nuisance_design",
            failure_detail=exc.detail,
        )
        return ServiceResult.from_record(record)

    if sensitive:
        record = BranchRecord(
            endpoint=endpoint_input.endpoint,
            branch=branch,
            intended_role=(
                "primary"
                if branch == intended
                else "fallback_eligible"
                if branch == NO_DELTA_BRANCH and fallback
                else "comparison"
            ),
            input_status="valid",
            nuisance_design_status="valid",
            source=None,
            artifacts=observed.artifacts,
        )
    else:
        record = branch_record_from_observed(
            endpoint_input.endpoint,
            branch,
            observed,
            intended_branch=intended,
            fallback_eligible=fallback,
        )
    return ServiceResult.from_record(record)


def _realize_addon_final(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    dependency = _one_record(request, ReferenceDependencyRecord)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    assert endpoint_input is not None and dependency is not None
    causal = tuple(request.task.dependencies)
    if endpoint_input.readiness_status != "ready":
        selection = FinalSelectionRecord(
            endpoint=endpoint_input.endpoint,
            selection_status="no_final_model",
            final_model=None,
            reason_codes=("endpoint_input_not_ready",),
            causal_task_ids=causal,
        )
        return ServiceResult.from_record(selection, facts=_selection_facts(selection))

    plan = _branch_plan(dependency, delta)
    branches = {record.branch: record for record in _records(request, BranchRecord)}
    decision = realize_final(plan, branches)
    if decision.selected_branch is None:
        reason = {
            "dependency_failure": "reference_dependency_failure",
            "execution_failure": "branch_execution_failure",
            "no_final_model": "no_accepted_branch_source",
        }[decision.final_status]
        selection = FinalSelectionRecord(
            endpoint=endpoint_input.endpoint,
            selection_status=decision.final_status,
            final_model=None,
            reason_codes=(reason,),
            causal_task_ids=causal,
        )
    else:
        fallback = decision.final_status == "fallback_final_realized"
        selection = FinalSelectionRecord(
            endpoint=endpoint_input.endpoint,
            selection_status=decision.final_status,
            final_model=_final_model_from_branch(
                decision.selected_branch,
                fallback=fallback,
            ),
            reason_codes=("selected_fallback" if fallback else "selected_primary",),
            causal_task_ids=causal,
        )
    return ServiceResult.from_record(selection, facts=_selection_facts(selection))


def _evaluate_sensitive_reference(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    prepared = _one_record(request, PreparedExposureRecord)
    observed = _one_record(request, ObservedResult)
    formal_source = _one_record(request, SourceRecord)
    assert (
        endpoint_input is not None
        and prepared is not None
        and observed is not None
        and formal_source is not None
    )
    observed_request = _provider(request).observed_request(
        endpoint_input,
        prepared,
        branch="reference",
    )
    result = ReferenceFiberBackend(
        _publisher(request),
        artifact_store=request.artifact_store,
    ).evaluate_sensitive_at_formal_source(observed_request, formal_source)
    computable = result.cell_computability_status == "computable"
    return ServiceResult.from_record(
        result,
        facts={"reference_source_accepted": computable},
    )


def _evaluate_sensitive_addon(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    prepared = _one_record(request, PreparedExposureRecord)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    final_selection = _one_record(request, FinalSelectionRecord)
    assert endpoint_input is not None and prepared is not None and final_selection is not None
    final = final_selection.final_model
    if final is None or final.selected_branch is None or final.final_key is None:
        raise ServiceAdapterError("sensitive add-on evaluation requires a realized formal branch")
    branch_name = final.final_key.final_branch
    branch_records = {
        item.branch: item for item in _records(request, BranchRecord)
    }
    local_branch = branch_records.get(branch_name)
    tau = float(final.final_key.selected_tau)
    coverage = int(final.final_key.selected_coverage)
    if (
        local_branch is None
        or local_branch.input_status != "valid"
        or local_branch.nuisance_design_status != "valid"
    ):
        evidence = _publisher(request).document(
            "sensitive_cell_status.json",
            {
                "schema_version": "dual_frequency_sensitive_cell_status_v1",
                "technical_status": "not_computable",
                "reason_code": "local_branch_input_or_design_failure",
            },
            kind="normative_fiber_sensitive_cell_status",
        )
        result = SensitiveRecord(
            endpoint=endpoint_input.endpoint,
            formal_endpoint_id=final.endpoint.identifier,
            evaluated_tau=tau,
            evaluated_coverage=coverage,
            input_status="input_failure",
            cell_computability_status="not_computable",
            prediction_status="not_applicable",
            feature_axis=None,
            artifacts=(evidence,),
        )
        return ServiceResult.from_record(result)

    observed_request = _provider(request).observed_request(
        endpoint_input,
        prepared,
        branch=branch_name,
        delta_reference=delta,
    )
    result = AddonFiberBackend(
        _publisher(request),
        artifact_store=request.artifact_store,
    ).evaluate_sensitive_at_formal_branch(observed_request, final.selected_branch)
    return ServiceResult.from_record(result)


def _final_selection(request: TaskExecutionRequest) -> FinalSelectionRecord:
    selection = _one_record(request, FinalSelectionRecord)
    if selection is None or selection.final_model is None:
        raise ServiceAdapterError("final-linked task requires a realized final selection")
    return selection


def _formal_request(
    request: TaskExecutionRequest,
    *,
    resampling_kind: str,
):
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    prepared = _prepared_exposure_record(request, request.task.endpoint_id)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    selection = _final_selection(request)
    assert endpoint_input is not None and prepared is not None
    method = getattr(request.provider, "formal_request", None)
    if not callable(method):
        raise ServiceAdapterCapabilityError(
            "provider does not expose the typed formal_request capability"
        )
    return method(
        selection.final_model,
        endpoint_input,
        prepared,
        _publisher(request),
        resampling_kind=resampling_kind,
        delta_reference=delta,
    )


def _formal_permutation_request(request: TaskExecutionRequest) -> FormalRequest:
    formal_request = _formal_request(request, resampling_kind="permutation")
    if formal_request.final_model.endpoint.model_family != request.task.model_family:
        raise ServiceAdapterError(
            "formal predecessor service model family does not match final"
        )
    return formal_request


def _prepare_formal_permutation_schedule(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_permutation_request(request)
    record = publish_formal_resampling_schedule(
        formal_request,
        _publisher(request),
    )
    return ServiceResult.from_record(record)


def _prepare_formal_operator_workspace(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_permutation_request(request)
    backend = _formal_permutation_backend(request, formal_request)
    descriptor = backend._prepare_permutation_operator_scratch(
        formal_request,
        request.output_dir,
    )
    record = formal_operator_scratch_record(
        descriptor,
        formal_request,
        _run_root(request),
    )
    return ServiceResult.from_record(record)


def _formal_permutation_backend(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
):
    publisher = _publisher(request)
    model_family = formal_request.final_model.endpoint.model_family
    if model_family.endswith("voxel"):
        return DirectVoxelFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
        )
    if model_family.endswith("fiber"):
        return NormativeFiberFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
        )
    raise ServiceAdapterError(
        f"unsupported formal model family {model_family!r}"
    )


def _formal_permutation_predecessors(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
):
    schedule_record = _one_record(request, ResamplingScheduleRecord)
    scratch_record = _one_record(request, FormalOperatorScratchRecord)
    assert schedule_record is not None and scratch_record is not None
    schedule = load_formal_resampling_schedule(
        schedule_record,
        formal_request,
        request.artifact_store,
    )
    descriptor = validated_formal_operator_scratch_descriptor(
        scratch_record,
        formal_request,
        _run_root(request),
    )
    return schedule_record, schedule, descriptor


def _run_formal_permutation_block(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_permutation_request(request)
    schedule_record, schedule, descriptor = _formal_permutation_predecessors(
        request,
        formal_request,
    )
    try:
        block_index = int(request.task.execution_parameter("block_index"))
        if block_index < 0:
            raise ValueError("block index is negative")
        block = schedule.blocks()[block_index]
    except (IndexError, TypeError, ValueError) as error:
        raise ServiceAdapterError(
            "formal permutation block_index is invalid"
        ) from error
    backend = _formal_permutation_backend(request, formal_request)
    result = backend._run_permutation_block_from_scratch(
        formal_request,
        schedule,
        block,
        descriptor,
    )
    record = publish_formal_permutation_block(
        result,
        schedule_record,
        _publisher(request),
    )
    return ServiceResult.from_record(record)


def _aggregate_formal_permutation(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_permutation_request(request)
    schedule_record, schedule, descriptor = _formal_permutation_predecessors(
        request,
        formal_request,
    )
    block_records = _records(request, ResamplingBlockRecord)
    if not block_records:
        raise ServiceAdapterError(
            "formal permutation aggregate requires block records"
        )
    blocks = tuple(
        load_formal_permutation_block(
            record,
            schedule_record,
            request.artifact_store,
        )
        for record in block_records
    )
    backend = _formal_permutation_backend(request, formal_request)
    result = backend._aggregate_permutation_blocks_from_scratch(
        formal_request,
        schedule,
        blocks,
        descriptor,
        schedule_record.schedule,
    )
    return ServiceResult.from_record(result, facts={"formal_complete": True})


def _formal_bootstrap_request(request: TaskExecutionRequest) -> FormalRequest:
    formal_request = _formal_request(request, resampling_kind="bootstrap")
    if formal_request.final_model.endpoint.model_family != request.task.model_family:
        raise ServiceAdapterError(
            "formal bootstrap service model family does not match final"
        )
    return formal_request


def _prepare_formal_bootstrap_schedule(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_bootstrap_request(request)
    record = publish_formal_resampling_schedule(
        formal_request,
        _publisher(request),
    )
    return ServiceResult.from_record(record)


def _bootstrap_nuisance_provider(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
) -> BootstrapNuisanceProvider | None:
    nuisance_provider = (
        request.provider
        if isinstance(request.provider, BootstrapNuisanceProvider)
        else None
    )
    if (
        nuisance_provider is not None
        or formal_request.final_model.final_key is None
        or formal_request.final_model.final_key.final_branch != ADJUSTED_BRANCH
    ):
        return nuisance_provider
    runtime_provider = request.provider
    if not isinstance(runtime_provider, StudyRuntimeInputProvider):
        raise ServiceAdapterCapabilityError(
            "adjusted production bootstrap requires StudyRuntimeInputProvider"
        )
    dependency = _one_record(request, ReferenceDependencyRecord)
    delta_reference = _one_record(request, DeltaReferenceBundle)
    assert dependency is not None and delta_reference is not None
    addon_input = _endpoint_input_record(request, request.task.endpoint_id)
    addon_prepared = _prepared_exposure_record(
        request,
        request.task.endpoint_id,
    )
    reference_input = _endpoint_input_record(
        request,
        dependency.matched_reference_endpoint_id,
    )
    reference_prepared = _prepared_exposure_record(
        request,
        dependency.matched_reference_endpoint_id,
    )
    try:
        return StudyBootstrapNuisanceProvider(
            runtime_provider,
            _artifact_store(request),
            formal_request,
            addon_input,
            addon_prepared,
            reference_input,
            reference_prepared,
            dependency,
            delta_reference,
        )
    except StudyBootstrapNuisanceProviderError as error:
        raise ServiceAdapterError(str(error)) from error


def _formal_bootstrap_backend(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
    nuisance_provider: BootstrapNuisanceProvider | None,
):
    publisher = _publisher(request)
    model_family = formal_request.final_model.endpoint.model_family
    if model_family.endswith("voxel"):
        return DirectVoxelFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
            bootstrap_nuisance_provider=nuisance_provider,
        )
    if model_family.endswith("fiber"):
        return NormativeFiberFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
            bootstrap_nuisance_provider=nuisance_provider,
        )
    raise ServiceAdapterError(
        f"unsupported formal model family {model_family!r}"
    )


def _optional_bootstrap_vector(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
    value: ArtifactRef | np.ndarray | None,
    *,
    name: str,
) -> np.ndarray | None:
    if value is None:
        return None
    array = materialize_array(
        value,
        name=name,
        expected_axes=(formal_request.subject_axis,),
        expected_units=(value.units if isinstance(value, ArtifactRef) else None),
        expected_space=(value.space if isinstance(value, ArtifactRef) else None),
        artifact_store=request.artifact_store,
    )
    return finite_vector(array, name, formal_request.subject_axis.count)


def _formal_bootstrap_inputs(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
) -> tuple[
    np.ndarray,
    np.ndarray | None,
    np.ndarray,
    np.ndarray,
    np.ndarray | None,
    np.ndarray | None,
]:
    exposure = finite_exposure(
        materialize_array(
            formal_request.exposure,
            name="exposure",
            expected_axes=(
                formal_request.subject_axis,
                formal_request.feature_axis,
            ),
            expected_units=formal_request.exposure_units,
            expected_space=formal_request.exposure_space,
            artifact_store=request.artifact_store,
            memory_map=True,
        ),
        formal_request,
    )
    outcome = finite_vector(
        materialize_array(
            formal_request.outcome,
            name="outcome",
            expected_axes=(formal_request.subject_axis,),
            expected_units=(
                formal_request.outcome.units
                if isinstance(formal_request.outcome, ArtifactRef)
                else None
            ),
            expected_space=(
                formal_request.outcome.space
                if isinstance(formal_request.outcome, ArtifactRef)
                else None
            ),
            artifact_store=request.artifact_store,
        ),
        "outcome",
        formal_request.subject_axis.count,
    )
    baseline = finite_vector(
        materialize_array(
            formal_request.baseline,
            name="baseline",
            expected_axes=(formal_request.subject_axis,),
            expected_units=(
                formal_request.baseline.units
                if isinstance(formal_request.baseline, ArtifactRef)
                else None
            ),
            expected_space=(
                formal_request.baseline.space
                if isinstance(formal_request.baseline, ArtifactRef)
                else None
            ),
            artifact_store=request.artifact_store,
        ),
        "baseline",
        formal_request.subject_axis.count,
    )
    delta_full = _optional_bootstrap_vector(
        request,
        formal_request,
        formal_request.delta_reference_full,
        name="delta_reference_full",
    )
    delta_folds = None
    if formal_request.delta_reference_folds is not None:
        value = formal_request.delta_reference_folds
        delta_folds = np.asarray(
            materialize_array(
                value,
                name="delta_reference_folds",
                expected_axes=(
                    formal_request.subject_axis,
                    formal_request.subject_axis,
                ),
                expected_units=(
                    value.units if isinstance(value, ArtifactRef) else None
                ),
                expected_space=(
                    value.space if isinstance(value, ArtifactRef) else None
                ),
                artifact_store=request.artifact_store,
            ),
            dtype=np.float64,
        )
        expected = (
            formal_request.subject_axis.count,
            formal_request.subject_axis.count,
        )
        if delta_folds.shape != expected or not np.all(np.isfinite(delta_folds)):
            raise ServiceAdapterError(
                "delta_reference_folds must be a finite fold-by-subject matrix"
            )
    fiber_ids = None
    if formal_request.final_model.endpoint.model_family.endswith("fiber"):
        if formal_request.feature_ids is None:
            raise ServiceAdapterError("fiber bootstrap requires feature IDs")
        value = formal_request.feature_ids
        fiber_ids = canonical_fiber_ids(
            materialize_array(
                value,
                name="feature_ids",
                expected_axes=(formal_request.feature_axis,),
                expected_units=(
                    value.units if isinstance(value, ArtifactRef) else None
                ),
                expected_space=(
                    value.space if isinstance(value, ArtifactRef) else None
                ),
                artifact_store=request.artifact_store,
            ),
            formal_request.feature_axis.count,
        )
    return exposure, fiber_ids, outcome, baseline, delta_full, delta_folds


def _formal_bootstrap_predecessor(
    request: TaskExecutionRequest,
    formal_request: FormalRequest,
):
    schedule_record = _one_record(request, ResamplingScheduleRecord)
    assert schedule_record is not None
    schedule = load_formal_resampling_schedule(
        schedule_record,
        formal_request,
        request.artifact_store,
    )
    return schedule_record, schedule


def _run_formal_bootstrap_block(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_bootstrap_request(request)
    schedule_record, schedule = _formal_bootstrap_predecessor(
        request,
        formal_request,
    )
    try:
        block_index = int(request.task.execution_parameter("block_index"))
        if block_index < 0:
            raise ValueError("block index is negative")
        block = schedule.blocks()[block_index]
    except (IndexError, TypeError, ValueError) as error:
        raise ServiceAdapterError(
            "formal bootstrap block_index is invalid"
        ) from error
    nuisance_provider = _bootstrap_nuisance_provider(request, formal_request)
    exposure, fiber_ids, outcome, baseline, delta_full, delta_folds = (
        _formal_bootstrap_inputs(request, formal_request)
    )
    model_family = formal_request.final_model.endpoint.model_family
    if model_family.endswith("voxel"):
        result = compute_direct_voxel_bootstrap_block(
            formal_request,
            exposure,
            outcome,
            baseline,
            nuisance_provider,
            schedule,
            block,
            original_delta_full=delta_full,
            original_delta_folds=delta_folds,
        )
    elif model_family.endswith("fiber"):
        assert fiber_ids is not None
        result = compute_normative_fiber_bootstrap_block(
            formal_request,
            exposure,
            fiber_ids,
            outcome,
            baseline,
            nuisance_provider,
            schedule,
            block,
            original_delta_full=delta_full,
            original_delta_folds=delta_folds,
        )
    else:
        raise ServiceAdapterError(
            f"unsupported formal model family {model_family!r}"
        )
    record = publish_formal_bootstrap_block(
        result,
        schedule_record,
        formal_request.feature_axis,
        formal_request.exposure_space,
        _publisher(request),
    )
    return ServiceResult.from_record(record)


def _aggregate_formal_bootstrap(
    request: TaskExecutionRequest,
) -> ServiceResult:
    formal_request = _formal_bootstrap_request(request)
    schedule_record, schedule = _formal_bootstrap_predecessor(
        request,
        formal_request,
    )
    block_records = _records(request, BootstrapBlockRecord)
    if not block_records:
        raise ServiceAdapterError(
            "formal bootstrap aggregate requires block records"
        )
    blocks = tuple(
        load_formal_bootstrap_block(
            record,
            schedule_record,
            formal_request.feature_axis,
            formal_request.exposure_space,
            request.artifact_store,
        )
        for record in block_records
    )
    result = combine_bootstrap_blocks(schedule, blocks)
    backend = _formal_bootstrap_backend(request, formal_request, None)
    formal_result = backend._publish_bootstrap(formal_request, result)
    return ServiceResult.from_record(
        formal_result,
        facts={"formal_complete": True},
    )


def _run_formal(
    request: TaskExecutionRequest,
    *,
    model_family: str,
    resampling_kind: str,
) -> ServiceResult:
    formal_request = _formal_request(request, resampling_kind=resampling_kind)
    publisher = _publisher(request)
    nuisance_provider = (
        _bootstrap_nuisance_provider(request, formal_request)
        if resampling_kind == "bootstrap"
        else None
    )
    if model_family.endswith("voxel"):
        backend = DirectVoxelFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
            bootstrap_nuisance_provider=nuisance_provider,
        )
    elif model_family.endswith("fiber"):
        backend = NormativeFiberFormalBackend(
            publisher,
            artifact_store=request.artifact_store,
            bootstrap_nuisance_provider=nuisance_provider,
        )
    else:
        raise ServiceAdapterError(f"unsupported formal model family {model_family!r}")
    result = backend.run_formal(formal_request)
    return ServiceResult.from_record(result, facts={"formal_complete": True})


def _run_in_sample(
    request: TaskExecutionRequest,
    *,
    model_family: str,
) -> ServiceResult:
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    prepared = _prepared_exposure_record(request, request.task.endpoint_id)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    selection = _final_selection(request)
    loocv_results = tuple(
        record
        for record in _records(request, FormalResult)
        if record.resampling_kind == "permutation"
    )
    if len(loocv_results) != 1:
        raise ServiceAdapterError(
            "final in-sample inference requires one matching LOOCV permutation result"
        )
    if selection.final_model.endpoint.model_family != model_family:
        raise ServiceAdapterError("in-sample service model family does not match final")
    method = getattr(request.provider, "in_sample_request", None)
    if not callable(method):
        raise ServiceAdapterCapabilityError(
            "provider does not expose the typed in_sample_request capability"
        )
    in_sample_request = method(
        selection.final_model,
        endpoint_input,
        prepared,
        loocv_results[0],
        delta_reference=delta,
    )
    result = FinalInSampleBackend(
        _publisher(request),
        artifact_store=_artifact_store(request),
    ).run(in_sample_request)
    return ServiceResult.from_record(result, facts={"formal_complete": True})


def _selected_feature_indices(
    request: TaskExecutionRequest,
    final: FinalModelRecord,
    prepared: PreparedExposureRecord,
) -> np.ndarray:
    source = final.selected_source
    if source is None and final.selected_branch is not None:
        source = final.selected_branch.source
    if source is None:
        raise ServiceAdapterError("realized final lacks a selected source")
    selected_axis = final.valid_feature_axis.axis
    if final.endpoint.model_family.endswith("voxel"):
        candidates = tuple(
            artifact
            for artifact in source.artifacts
            if artifact.kind == "selected_feature_indices"
        )
        if len(candidates) != 1:
            raise ServiceAdapterError(
                "direct final requires one selected_feature_indices artifact"
            )
        indices = np.asarray(_materialize(request, candidates[0]), dtype=np.int64)
    else:
        candidates = tuple(
            artifact
            for artifact in source.artifacts
            if artifact.kind == "normative_fiber_valid_union_ids"
        )
        if len(candidates) != 1:
            raise ServiceAdapterError(
                "fiber final requires one normative_fiber_valid_union_ids artifact"
            )
        parent_ids = np.asarray(_materialize(request, prepared.feature_ids))
        selected_ids = np.asarray(_materialize(request, candidates[0]), dtype=np.int64)
        indices = np.searchsorted(parent_ids, selected_ids)
        if np.any(indices >= parent_ids.size) or not np.array_equal(
            parent_ids[indices],
            selected_ids,
        ):
            raise ServiceAdapterError("selected fiber IDs are outside the parent axis")
    if indices.shape != (selected_axis.count,):
        raise ServiceAdapterError("selected feature indices differ from the final axis")
    if indices.size and (
        indices[0] < 0
        or indices[-1] >= prepared.feature_axis.count
        or np.any(np.diff(indices) <= 0)
    ):
        raise ServiceAdapterError(
            "selected feature indices must be ordered, unique, and in bounds"
        )
    return indices


def _selected_overlap_for_final(
    request: TaskExecutionRequest,
    final: FinalModelRecord,
    prepared: PreparedExposureRecord,
) -> ArtifactRef | None:
    if final.endpoint.model_family.startswith("reference_"):
        return None
    if prepared.reference_overlap_mask is None:
        raise ServiceAdapterError("add-on final lacks a reference-overlap mask")
    indices = _selected_feature_indices(request, final, prepared)
    parent_overlap = np.asarray(
        _materialize(request, prepared.reference_overlap_mask),
        dtype=bool,
    )
    return _publisher(request).array(
        "selected_reference_overlap_mask.npy",
        parent_overlap[:, indices],
        kind="final_selected_reference_overlap_mask",
        axes=(prepared.subject_axis, final.valid_feature_axis.axis),
        units="binary",
        space=prepared.reference_overlap_mask.space,
    )


def _observed_request_for_final(
    request: TaskExecutionRequest,
) -> tuple[
    FinalModelRecord,
    EndpointInputRecord,
    PreparedExposureRecord,
    ObservedRequest,
    ArtifactRef | None,
]:
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    prepared = _prepared_exposure_record(request, request.task.endpoint_id)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    selection = _final_selection(request)
    assert endpoint_input is not None and prepared is not None
    final = selection.final_model
    assert final is not None and final.final_key is not None
    provider = _provider(request)
    observed = provider.observed_request(
        endpoint_input,
        prepared,
        branch=final.final_key.final_branch,
        delta_reference=delta,
    )
    selected_method = getattr(provider, "selected_exposure", None)
    if not callable(selected_method):
        raise ServiceAdapterError(
            "final-linked task requires a provider selected_exposure method"
        )
    selected_exposure, selected_feature_ids = selected_method(
        final,
        prepared,
        _publisher(request),
    )
    if not isinstance(selected_exposure, ArtifactRef):
        raise ServiceAdapterError("selected_exposure must return an ArtifactRef")
    selected_axis = final.valid_feature_axis.axis
    if selected_exposure.axis_refs != (prepared.subject_axis, selected_axis):
        raise ServiceAdapterError("selected exposure does not bind the final feature axis")
    observed = replace(
        observed,
        exposure=selected_exposure,
        feature_axis=selected_axis,
        feature_ids=selected_feature_ids,
    )

    selected_overlap = _selected_overlap_for_final(request, final, prepared)
    return final, endpoint_input, prepared, observed, selected_overlap


def _final_target(request: TaskExecutionRequest) -> FinalSensitivityTarget:
    final, _endpoint_input, _prepared, observed, selected_overlap = (
        _observed_request_for_final(request)
    )
    return FinalSensitivityTarget(
        final_model=final,
        observed_request=observed,
        reference_overlap_mask=selected_overlap,
    )


def _run_tau_neighborhood(request: TaskExecutionRequest) -> ServiceResult:
    result = TauNeighborhoodStrategy(
        _publisher(request),
        array_provider=request.artifact_store,
    ).run(TauNeighborhoodRequest(_final_target(request)))
    return ServiceResult.from_record(result)


def _run_reference_fiber_control(
    request: TaskExecutionRequest,
    *,
    cheap: bool,
) -> ServiceResult:
    endpoint_input = _one_record(request, EndpointInputRecord)
    prepared = _one_record(request, PreparedExposureRecord)
    observed = _one_record(request, ObservedResult)
    assert endpoint_input is not None and prepared is not None and observed is not None
    observed_request = _provider(request).observed_request(
        endpoint_input,
        prepared,
        branch="reference",
    )
    diagnostic_observed = ObservedResult(source=None, artifacts=observed.artifacts)
    configuration = _configuration(request)
    sensitivity = configuration.normative_fiber.sensitivity
    control_request = ObservedFiberControlRequest(
        observed_request=observed_request,
        observed_result=diagnostic_observed,
        high_threshold_tau=(sensitivity.high_threshold.tau if cheap else None),
        high_threshold_coverage=(
            sensitivity.high_threshold.coverage if cheap else None
        ),
        fixed_sweet_count=(
            sensitivity.fixed_outer_library.sweet_count if cheap else None
        ),
        fixed_sour_count=(
            sensitivity.fixed_outer_library.sour_count if cheap else None
        ),
    )
    result = ObservedFiberControlStrategy(
        _publisher(request),
        array_provider=request.artifact_store,
    ).run(control_request)
    return ServiceResult.from_record(result)


def _run_final_fiber_control(request: TaskExecutionRequest) -> ServiceResult:
    result = FinalFiberControlStrategy(
        _publisher(request),
        array_provider=request.artifact_store,
    ).run(FinalFiberControlRequest(_final_target(request)))
    return ServiceResult.from_record(result)


def _materialize(request: TaskExecutionRequest, artifact: ArtifactRef) -> np.ndarray:
    return np.asarray(
        _artifact_store(request).materialize(
            artifact,
            expected_dtype=artifact.dtype,
            expected_shape=artifact.shape,
            expected_axes=artifact.axis_refs,
            expected_units=artifact.units,
            expected_space=artifact.space,
        )
    )


_SCIENTIFIC_ARRAY_BLOCK_COLUMNS = 65_536


def _selected_scientific_columns(
    request: TaskExecutionRequest,
    value: ScientificArrayRef,
    indices: np.ndarray,
) -> np.ndarray:
    positions = np.asarray(indices)
    if positions.ndim != 1 or positions.dtype != np.dtype(np.int64):
        raise ServiceAdapterError(
            "selected scientific-array positions must be one-dimensional int64"
        )
    if positions.size and (
        int(positions.min()) < 0
        or int(positions.max()) >= value.shape[1]
        or np.unique(positions).size != positions.size
    ):
        raise ServiceAdapterError(
            "selected scientific-array positions must be unique and in bounds"
        )
    if isinstance(value, ArtifactRef):
        return np.asarray(_materialize(request, value))[:, positions]
    if not isinstance(value, IndexedArrayView):
        raise TypeError("scientific array must be an ArtifactRef or IndexedArrayView")
    output = np.empty(
        (value.shape[0], positions.size),
        dtype=np.dtype(value.dtype),
    )
    block_width = max(
        1,
        min(_SCIENTIFIC_ARRAY_BLOCK_COLUMNS, positions.size),
    )
    max_block_bytes = (
        value.shape[0] * block_width * np.dtype(value.dtype).itemsize
    )
    with _artifact_store(request).open_indexed_array_view(
        value,
        max_block_bytes=max_block_bytes,
    ) as reader:
        for start in range(0, positions.size, block_width):
            stop = min(start + block_width, positions.size)
            output[:, start:stop] = reader[:, positions[start:stop]]
    return output


def _scientific_row_mean(
    request: TaskExecutionRequest,
    value: ScientificArrayRef,
) -> np.ndarray:
    if isinstance(value, ArtifactRef):
        return np.mean(_materialize(request, value), axis=1)
    if not isinstance(value, IndexedArrayView):
        raise TypeError("scientific array must be an ArtifactRef or IndexedArrayView")
    sums = np.zeros(value.shape[0], dtype=np.dtype(value.dtype))
    for _start, _stop, block in _artifact_store(
        request
    ).iter_indexed_array_view_blocks(
        value,
        block_columns=_SCIENTIFIC_ARRAY_BLOCK_COLUMNS,
    ):
        sums += np.sum(block, axis=1, dtype=np.dtype(value.dtype))
    return np.asarray(sums / value.shape[1], dtype=np.dtype(value.dtype))


def _addon_exposure_sensitivity(request: TaskExecutionRequest) -> ServiceResult:
    final, endpoint_input, prepared, observed, selected_overlap = (
        _observed_request_for_final(request)
    )
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    publisher = _publisher(request)
    target = FinalSensitivityTarget(
        final,
        observed,
        reference_overlap_mask=selected_overlap,
    )

    opposite = {
        NO_DELTA_BRANCH: ADJUSTED_BRANCH,
        ADJUSTED_BRANCH: NO_DELTA_BRANCH,
    }[observed.branch]
    nonfinal_request = None
    if opposite == NO_DELTA_BRANCH or (delta is not None and delta.valid):
        nonfinal_request = _provider(request).observed_request(
            endpoint_input,
            prepared,
            branch=opposite,
            delta_reference=delta,
        )
        nonfinal_request = replace(
            nonfinal_request,
            exposure=observed.exposure,
            feature_axis=observed.feature_axis,
            feature_ids=observed.feature_ids,
        )

    baseline = _materialize(request, endpoint_input.baseline)
    outcome = _materialize(request, endpoint_input.outcome)
    gain = (
        baseline - outcome
        if _endpoint(request).scale_direction == "lower"
        else outcome - baseline
    )
    gain_artifact = publisher.array(
        "direction_normalized_addon_gain.npy",
        np.asarray(gain, dtype=np.float64),
        kind="direction_normalized_addon_gain",
        axes=(prepared.subject_axis,),
        units=endpoint_input.outcome.units,
        space=None,
    )
    gain_request = replace(observed, outcome=gain_artifact, outcome_direction="higher")
    total_request = None
    if prepared.total_exposure is not None:
        selected_indices = _selected_feature_indices(request, final, prepared)
        selected_total_exposure = publisher.array(
            "selected_total_exposure.npy",
            _selected_scientific_columns(
                request,
                prepared.total_exposure,
                selected_indices,
            ),
            kind="raw_addon_component_exposure",
            axes=(prepared.subject_axis, final.valid_feature_axis.axis),
            units=prepared.total_exposure.units,
            space=prepared.total_exposure.space,
        )
        total_request = replace(observed, exposure=selected_total_exposure)

    support_input = None
    if delta is not None and delta.support_rows is not None:
        rows = np.asarray(_materialize(request, delta.support_rows), dtype=np.float64)
        if rows.ndim != 2 or rows.shape[1] < 4:
            raise ServiceAdapterError("Delta support rows have an invalid shape")
        subject_fraction = rows[:, 2]
        fold_fraction = np.nanmax(rows[:, 3:], axis=1)
        support_input = SupportDiagnosticInput(
            subject_axis=prepared.subject_axis,
            subject_out_support_fraction=publisher.array(
                "subject_out_support_fraction.npy",
                subject_fraction,
                kind="subject_out_support_fraction",
                axes=(prepared.subject_axis,),
                units="fraction",
                space=None,
            ),
            fold_maximum_out_support_fraction=publisher.array(
                "fold_maximum_out_support_fraction.npy",
                fold_fraction,
                kind="fold_maximum_out_support_fraction",
                axes=(prepared.subject_axis,),
                units="fraction",
                space=None,
            ),
        )

    collinearity_input = None
    if (
        prepared.total_exposure is not None
        and prepared.addon_reference_component_exposure is not None
    ):
        total = _scientific_row_mean(request, prepared.total_exposure)
        reference_component = _scientific_row_mean(
            request,
            prepared.addon_reference_component_exposure,
        )
        collinearity_input = CollinearityInput(
            subject_axis=prepared.subject_axis,
            column_names=("mean_total_exposure", "mean_reference_component_exposure"),
            columns=(
                publisher.array(
                    "mean_total_exposure.npy",
                    total,
                    kind="mean_total_exposure",
                    axes=(prepared.subject_axis,),
                    units="V/m",
                    space=None,
                ),
                publisher.array(
                    "mean_reference_component_exposure.npy",
                    reference_component,
                    kind="mean_reference_component_exposure",
                    axes=(prepared.subject_axis,),
                    units="V/m",
                    space=None,
                ),
            ),
        )

    result = AddonExposureSensitivityStrategy(
        publisher,
        array_provider=request.artifact_store,
    ).run(
        AddonExposureSensitivityRequest(
            target=target,
            nonfinal_request=nonfinal_request,
            gain_request=gain_request,
            total_exposure_request=total_request,
            support_input=support_input,
            collinearity_input=collinearity_input,
        )
    )
    return ServiceResult.from_record(result)


def _run_jitter(request: TaskExecutionRequest) -> ServiceResult:
    configuration = _configuration(request)
    profile = (
        configuration.direct_voxel.formal_resampling
        if request.task.model_family.endswith("voxel")
        else configuration.normative_fiber.formal_resampling
    )
    settings = SpatialJitterSettings(
        replicates=profile.jitter_resamples,
        seed=profile.seed,
        translation_fwhm_mm=profile.jitter_translation_fwhm_mm,
    )
    target = _final_target(request)
    block_group_id = dict(request.task.execution_parameters).get(
        "jitter_block_group_id"
    )
    array_provider = request.artifact_store
    if block_group_id is not None:
        if not isinstance(request.provider, StudyRuntimeInputProvider):
            raise ServiceAdapterCapabilityError(
                "cached spatial jitter requires StudyRuntimeInputProvider"
            )
        endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
        dependency = _one_record(request, ReferenceDependencyRecord, required=False)
        replicate_provider = CachedJitterReplicateProvider(
            request=request,
            target=target,
            endpoint_input=endpoint_input,
            reference_dependency=dependency,
            settings=settings,
            group_id=block_group_id,
        )
        array_provider = replicate_provider.array_provider
    elif isinstance(request.provider, JitterReplicateProvider):
        replicate_provider = request.provider
    elif isinstance(request.provider, StudyRuntimeInputProvider):
        endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
        dependency = _one_record(request, ReferenceDependencyRecord, required=False)
        reference_input = (
            None
            if dependency is None
            else _endpoint_input_record(
                request,
                dependency.matched_reference_endpoint_id,
            )
        )
        replicate_provider = StudyJitterReplicateProvider(
            provider=request.provider,
            endpoint_input=endpoint_input,
            reference_input=reference_input,
            reference_dependency=dependency,
            final_model=target.final_model,
            original_delta=_one_record(
                request,
                DeltaReferenceBundle,
                required=False,
            ),
            publisher=_publisher(request),
            artifact_store=_artifact_store(request),
            settings=settings,
        )
    else:
        raise ServiceAdapterCapabilityError(
            "spatial jitter requires a production or injected replicate provider"
        )
    jitter_request = SpatialJitterRequest(
        target=target,
        settings=settings,
        replicate_provider=replicate_provider,
    )
    result = SpatialJitterStrategy(
        _publisher(request),
        array_provider=array_provider,
    ).run(jitter_request)
    return ServiceResult.from_record(result)


def _activation_fitting_request(
    request: TaskExecutionRequest,
) -> ActivationRequest:
    """Materialize physical OSS rows once and return the typed fitting request."""

    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    prepared = _prepared_exposure_record(request, request.task.endpoint_id)
    delta = _one_record(request, DeltaReferenceBundle, required=False)
    selection = _final_selection(request)
    assert endpoint_input is not None and prepared is not None
    runtime_method = getattr(request.provider, "activation_runtime_request", None)
    fitting_method = getattr(request.provider, "activation_fitting_request", None)
    if not callable(runtime_method) or not callable(fitting_method):
        raise ServiceAdapterCapabilityError(
            "provider does not expose typed activation runtime and fitting capabilities"
        )
    if not isinstance(request.scientific_cache, ContentAddressedCache):
        raise ServiceAdapterCapabilityError(
            "activation requires the configured content-addressed scientific cache"
        )
    publisher = _publisher(request)
    simulation_arguments: dict[str, object] = {}
    omega_records = tuple(
        record
        for record in _records(request, OSSSharedOmegaGroupRecord)
        if request.task.endpoint_id in record.endpoint_ids
    )
    if len(omega_records) > 1:
        raise ServiceAdapterError(
            "activation task received multiple OSS physical-row authorities"
        )
    omega_row_ids: frozenset[str] | None = None
    if omega_records:
        group = omega_records[0]
        if (
            group.model_family != selection.final_model.endpoint.model_family
            or group.final_feature_axis
            != selection.final_model.valid_feature_axis.axis
            or group.preparation_status != "omega_max_ready"
        ):
            raise ServiceAdapterError(
                "shared Omega-max group differs from the selected final model"
            )
        try:
            omega_ids = omega_ids_for_shared_group(
                group,
                request.scientific_cache,
            )
        except RuntimeError as exc:
            raise ServiceAdapterError(str(exc)) from exc
        simulation_arguments = {
            "simulation_feature_axis": group.omega_feature_axis,
            "simulation_feature_ids": omega_ids,
        }
        omega_row_ids = frozenset(group.omega_row_ids)
    runtime_request = runtime_method(
        selection.final_model,
        endpoint_input,
        prepared,
        publisher,
        workers=request.workers,
        allow_expensive_producers=(
            False
            if omega_row_ids is not None
            else request.allow_expensive_producers
        ),
        **simulation_arguments,
    )
    if not isinstance(runtime_request, OSSActivationRuntimeRequest):
        raise ServiceAdapterError(
            "activation_runtime_request must return OSSActivationRuntimeRequest"
        )
    if omega_row_ids is not None:
        requested_row_ids = frozenset(
            item.scientific_identity
            for item in OSSActivationProvider._producer_requests(runtime_request)
        )
        if not requested_row_ids or not requested_row_ids.issubset(omega_row_ids):
            raise ServiceAdapterError(
                "activation requests rows outside the shared Omega-max closure"
            )
    toolchain_method = getattr(request.provider, "oss_producer_toolchain", None)
    toolchain = (
        toolchain_method()
        if (
            omega_row_ids is None
            and request.allow_expensive_producers
            and callable(toolchain_method)
        )
        else None
    )
    materialized_rows = OSSActivationProvider(
        request.scientific_cache,
        producer_toolchain=toolchain,
    ).materialize(runtime_request, publisher)
    if not isinstance(materialized_rows, OSSRowBatchArtifact):
        raise ServiceAdapterError(
            "activation row materializer returned an invalid artifact"
        )
    selected_overlap = _selected_overlap_for_final(
        request,
        selection.final_model,
        prepared,
    )
    activation_request = fitting_method(
        selection.final_model,
        endpoint_input,
        prepared,
        materialized_rows,
        selected_overlap,
        publisher,
        delta_reference=delta,
    )
    if not isinstance(activation_request, ActivationRequest):
        raise ServiceAdapterError(
            "activation_fitting_request must return ActivationRequest"
        )
    return activation_request


class _LazyOSSProducerToolchain:
    """Resolve the project toolchain only when a cache miss invokes it."""

    def __init__(self, factory: Callable[[], object]) -> None:
        if not callable(factory):
            raise TypeError("factory must be callable")
        self._factory = factory
        self._toolchain: object | None = None

    def produce_with_evidence(self, request: object):
        if self._toolchain is None:
            self._toolchain = self._factory()
        method = getattr(self._toolchain, "produce_with_evidence", None)
        if not callable(method):
            raise ServiceAdapterCapabilityError(
                "OSS producer toolchain lacks exact sample-evidence capabilities"
            )
        return method(request)


def _prepare_oss_omega_max_rows(
    request: TaskExecutionRequest,
) -> ServiceResult:
    """Restore or produce the immutable Omega-max-only group closure."""

    if not isinstance(request.provider, StudyRuntimeInputProvider):
        raise ServiceAdapterCapabilityError(
            "shared Omega-max preparation requires StudyRuntimeInputProvider"
        )
    if not isinstance(request.scientific_cache, ContentAddressedCache):
        raise ServiceAdapterCapabilityError(
            "shared Omega-max preparation requires the scientific cache"
        )
    try:
        descriptor = json.loads(request.task.execution_parameter("group_descriptor"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ServiceAdapterError(
            "shared Omega-max group descriptor is invalid"
        ) from exc
    endpoint_ids = tuple(str(value) for value in descriptor.get("endpoint_ids", ()))
    endpoint_inputs = {
        record.endpoint.identifier: record
        for record in _records(request, EndpointInputRecord)
        if record.endpoint.identifier in endpoint_ids
    }
    prepared_exposures = {
        record.endpoint.identifier: record
        for record in _records(request, PreparedExposureRecord)
        if record.endpoint.identifier in endpoint_ids
    }
    final_selections = {
        record.endpoint.identifier: record
        for record in _records(request, FinalSelectionRecord)
        if record.endpoint.identifier in endpoint_ids
    }
    toolchain_method = getattr(request.provider, "oss_producer_toolchain", None)
    record = prepare_oss_omega_max_rows(
        descriptor=descriptor,
        endpoint_inputs=endpoint_inputs,
        prepared_exposures=prepared_exposures,
        final_selections=final_selections,
        provider=request.provider,
        cache=request.scientific_cache,
        publisher=_publisher(request),
        toolchain=(
            _LazyOSSProducerToolchain(toolchain_method)
            if callable(toolchain_method)
            else object()
        ),
        workers=request.workers,
        allow_expensive_producers=request.allow_expensive_producers,
    )
    return ServiceResult.from_record(record)


def _run_activation(request: TaskExecutionRequest) -> ServiceResult:
    activation_request = _activation_fitting_request(request)
    result = PPAMActivationBackend(
        _publisher(request),
        artifact_store=request.artifact_store,
    ).run_activation(activation_request)
    if not isinstance(result, ActivationArtifact):
        raise ServiceAdapterError("activation backend returned an invalid record")
    return ServiceResult.from_record(result)


def _materialize_ppam_fit_inputs(
    backend: PPAMActivationBackend,
    activation_request: ActivationRequest,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[np.ndarray, ...],
]:
    shape = (
        activation_request.subject_axis.count,
        activation_request.feature_axis.count,
    )
    axes = (
        activation_request.subject_axis,
        activation_request.feature_axis,
    )
    probability = validate_ten_sample_probabilities(
        backend._array(
            activation_request.activation_probability,
            shape=shape,
            axes=axes,
            dtype=np.dtype(np.float32),
            units="probability",
            space="right_canonical",
        )
    )
    outcome = backend._array(
        activation_request.outcome,
        shape=(activation_request.subject_axis.count,),
        axes=(activation_request.subject_axis,),
    )
    baseline = backend._array(
        activation_request.baseline,
        shape=(activation_request.subject_axis.count,),
        axes=(activation_request.subject_axis,),
    )
    peak_score = backend._array(
        activation_request.peak_final_score,
        shape=(activation_request.subject_axis.count,),
        axes=(activation_request.subject_axis,),
    )
    fiber_ids = activation_universe(
        backend._array(
            activation_request.feature_ids,
            shape=(activation_request.feature_axis.count,),
            axes=(activation_request.feature_axis,),
            dtype=np.dtype(np.int64),
            units="fiber_id",
            space="right_canonical",
        )
    )
    activation_feature_ids = activation_universe(
        backend._array(
            activation_request.activation_feature_ids,
            shape=(activation_request.feature_axis.count,),
            axes=(activation_request.feature_axis,),
            dtype=np.dtype(np.int64),
            units="fiber_id",
            space="right_canonical",
        )
    )
    if not np.array_equal(fiber_ids, activation_feature_ids):
        raise ServiceAdapterError(
            "activation feature IDs differ from the final feature axis"
        )
    if activation_request.reference_overlap_mask is None:
        overlap = np.zeros(shape, dtype=bool)
    else:
        overlap = backend._array(
            activation_request.reference_overlap_mask,
            shape=shape,
            axes=axes,
            dtype=np.dtype(bool),
            units="binary",
            space="right_canonical",
        )
        if overlap.dtype != np.dtype(bool):
            raise ServiceAdapterError(
                "reference overlap must materialize as boolean data"
            )
    nuisance = tuple(
        backend._array(
            value,
            shape=(
                (activation_request.subject_axis.count,)
                if index == 0
                else (
                    activation_request.subject_axis.count,
                    activation_request.subject_axis.count,
                )
            ),
            axes=(
                (activation_request.subject_axis,)
                if index == 0
                else (
                    activation_request.subject_axis,
                    activation_request.subject_axis,
                )
            ),
        )
        for index, value in enumerate(activation_request.nuisance_inputs)
    )
    return (
        probability,
        outcome,
        baseline,
        peak_score,
        fiber_ids,
        overlap,
        nuisance,
    )


def _prepare_ppam_observed_workspace(
    request: TaskExecutionRequest,
) -> ServiceResult:
    activation_request = _activation_fitting_request(request)
    publisher = _publisher(request)
    backend = PPAMActivationBackend(
        publisher,
        artifact_store=_artifact_store(request),
    )
    (
        probability,
        outcome,
        baseline,
        peak_score,
        fiber_ids,
        overlap,
        nuisance,
    ) = _materialize_ppam_fit_inputs(backend, activation_request)
    binary = np.where(
        overlap,
        0.0,
        binary_activation(probability),
    ).astype(np.float32, copy=False)
    probability_ref = backend._publish_probability(
        activation_request,
        probability,
    )
    binary_ref = publisher.array(
        "oss_binary_exposure.npy",
        binary,
        kind="oss_binary_activation",
        axes=(activation_request.subject_axis, activation_request.feature_axis),
        units="binary",
        space="right_canonical",
    )

    def persisted_array(
        value: object,
        materialized: np.ndarray,
        filename: str,
        kind: str,
        axes: tuple,
        units: str | None,
        space: str | None,
    ) -> ArtifactRef:
        if isinstance(value, ArtifactRef):
            return value
        return publisher.array(
            filename,
            materialized,
            kind=kind,
            axes=axes,
            units=units,
            space=space,
        )

    subject = (activation_request.subject_axis,)
    feature = (activation_request.feature_axis,)
    subject_subject = (
        activation_request.subject_axis,
        activation_request.subject_axis,
    )
    persisted_nuisance = tuple(
        persisted_array(
            value,
            nuisance[index],
            f"oss_nuisance_input_{index}.npy",
            f"oss_nuisance_input_{index}",
            subject if index == 0 else subject_subject,
            "score",
            None,
        )
        for index, value in enumerate(activation_request.nuisance_inputs)
    )
    persisted_request = replace(
        activation_request,
        activation_probability=probability_ref,
        reference_overlap_mask=(
            None
            if activation_request.reference_overlap_mask is None
            else persisted_array(
                activation_request.reference_overlap_mask,
                overlap,
                "oss_reference_overlap_mask.npy",
                "oss_reference_overlap_mask",
                (activation_request.subject_axis, activation_request.feature_axis),
                "binary",
                "right_canonical",
            )
        ),
        outcome=persisted_array(
            activation_request.outcome,
            outcome,
            "oss_outcome.npy",
            "oss_outcome",
            subject,
            "score",
            None,
        ),
        baseline=persisted_array(
            activation_request.baseline,
            baseline,
            "oss_baseline.npy",
            "oss_baseline",
            subject,
            "score",
            None,
        ),
        peak_final_score=persisted_array(
            activation_request.peak_final_score,
            peak_score,
            "oss_peak_final_score.npy",
            "oss_peak_final_score",
            subject,
            "score",
            None,
        ),
        nuisance_inputs=persisted_nuisance,
        feature_ids=persisted_array(
            activation_request.feature_ids,
            fiber_ids,
            "oss_final_feature_ids.npy",
            "oss_final_feature_ids",
            feature,
            "fiber_id",
            "right_canonical",
        ),
        activation_feature_ids=persisted_array(
            activation_request.activation_feature_ids,
            fiber_ids,
            "oss_activation_feature_ids.npy",
            "oss_activation_feature_ids",
            feature,
            "fiber_id",
            "right_canonical",
        ),
    )
    try:
        workspace = prepare_ppam_fit_workspace(
            persisted_request,
            probability,
            overlap,
            outcome,
            baseline,
            peak_score,
            fiber_ids,
            nuisance,
        )
    except NuisancePlanError as error:
        observed_artifacts = publish_ppam_nuisance_failure(
            persisted_request,
            error.status,
            error.detail,
            publisher,
        )
        technical_status = "nuisance_not_estimable"
        descriptor = None
    else:
        observed = ppam_observed_state(workspace)
        observed_artifacts = publish_ppam_observed_state(
            observed,
            fiber_ids,
            publisher,
        )
        technical_status = (
            "permutation_ready"
            if observed.can_permute
            else "observed_not_permutation_ready"
        )
        descriptor = publish_ppam_operator_scratch(
            request.output_dir,
            workspace.permutation,
        )
    record = ppam_observed_workspace_record(
        persisted_request,
        binary_ref,
        observed_artifacts,
        technical_status,
        _run_root(request),
        descriptor,
    )
    return ServiceResult.from_record(
        record,
        facts={"ppam_permutation_ready": technical_status == "permutation_ready"},
    )


def _ppam_workspace_request(
    request: TaskExecutionRequest,
) -> tuple[PPAMObservedWorkspaceRecord, ActivationRequest]:
    record = _one_record(request, PPAMObservedWorkspaceRecord)
    selection = _final_selection(request)
    assert record is not None and selection.final_model is not None
    activation_request = activation_request_from_ppam_workspace(
        record,
        selection.final_model,
    )
    return record, activation_request


def _prepare_ppam_permutation_schedule(
    request: TaskExecutionRequest,
) -> ServiceResult:
    record, activation_request = _ppam_workspace_request(request)
    if record.technical_status != "permutation_ready":
        raise ServiceAdapterError(
            "pPAM schedule requires a permutation-ready observed workspace"
        )
    schedule = publish_ppam_resampling_schedule(
        activation_request,
        _publisher(request),
    )
    return ServiceResult.from_record(schedule)


def _run_ppam_permutation_block(
    request: TaskExecutionRequest,
) -> ServiceResult:
    record, activation_request = _ppam_workspace_request(request)
    if record.technical_status != "permutation_ready":
        raise ServiceAdapterError(
            "pPAM block requires a permutation-ready observed workspace"
        )
    schedule_record = _one_record(request, ResamplingScheduleRecord)
    assert schedule_record is not None
    schedule = load_ppam_resampling_schedule(
        schedule_record,
        activation_request,
        _artifact_store(request),
    )
    try:
        block_index = int(request.task.execution_parameter("block_index"))
        if block_index < 0:
            raise ValueError("block index is negative")
        block = schedule.blocks()[block_index]
    except (IndexError, TypeError, ValueError) as error:
        raise ServiceAdapterError("pPAM permutation block_index is invalid") from error
    binary = materialize_array(
        record.binary_exposure,
        name="oss_binary_activation",
        expected_axes=(record.subject_axis, record.feature_axis),
        expected_units="binary",
        expected_space="right_canonical",
        artifact_store=_artifact_store(request),
        memory_map=True,
    )
    outcome = materialize_array(
        record.outcome,
        name="outcome",
        expected_axes=(record.subject_axis,),
        expected_units=record.outcome.units,
        expected_space=record.outcome.space,
        artifact_store=_artifact_store(request),
        memory_map=True,
    )
    fiber_ids = materialize_array(
        record.feature_ids,
        name="feature_ids",
        expected_axes=(record.feature_axis,),
        expected_units="fiber_id",
        expected_space="right_canonical",
        artifact_store=_artifact_store(request),
        memory_map=True,
    )
    workspace, arrays = reopen_ppam_workspace_from_record(
        record,
        activation_request,
        record.binary_exposure,
        binary,
        outcome,
        fiber_ids,
        _run_root(request),
    )
    try:
        computed = compute_ppam_permutation_block_from_workspace(
            workspace,
            schedule,
            block,
        )
    finally:
        close_ppam_operator_scratch(arrays)
    block_record = publish_ppam_permutation_block(
        computed,
        schedule_record,
        _publisher(request),
    )
    return ServiceResult.from_record(block_record)


def _aggregate_ppam_activation(
    request: TaskExecutionRequest,
) -> ServiceResult:
    record, activation_request = _ppam_workspace_request(request)
    schedule_record = _one_record(
        request,
        ResamplingScheduleRecord,
        required=False,
    )
    block_records = _records(request, PPAMPermutationBlockRecord)
    if record.technical_status == "permutation_ready":
        if schedule_record is None or not block_records:
            raise ServiceAdapterError(
                "permutation-ready pPAM aggregate requires schedule and blocks"
            )
        schedule = load_ppam_resampling_schedule(
            schedule_record,
            activation_request,
            _artifact_store(request),
        )
        blocks = tuple(
            load_ppam_permutation_block(
                block_record,
                schedule_record,
                _artifact_store(request),
            )
            for block_record in block_records
        )
        observed = load_ppam_observed_state(
            record,
            activation_request,
            _artifact_store(request),
        )
        result = aggregate_ppam_observed_state(observed, schedule, blocks)
    elif schedule_record is not None or block_records:
        raise ServiceAdapterError(
            "non-permutation pPAM aggregate cannot receive schedule or blocks"
        )
    elif record.technical_status == "observed_not_permutation_ready":
        observed = load_ppam_observed_state(
            record,
            activation_request,
            _artifact_store(request),
        )
        result = aggregate_ppam_observed_state(observed, None, ())
    else:
        result = None
    activation = publish_ppam_activation_result(
        record,
        activation_request,
        result,
        _publisher(request),
        _artifact_store(request),
    )
    return ServiceResult.from_record(
        activation,
        facts={"activation_complete": True},
    )


def _technical_sensitivity(
    request: TaskExecutionRequest,
    reason_code: str,
) -> ServiceResult:
    selection = _one_record(request, FinalSelectionRecord, required=False)
    target_id = (
        selection.final_model.identifier
        if selection is not None and selection.final_model is not None
        else request.task.endpoint_id
    )
    artifact = _publisher(request).document(
        "technical_status.json",
        {
            "schema_version": "dual_frequency_sensitivity_technical_status_v1",
            "technical_status": "not_run",
            "reason_code": reason_code,
            "service_id": request.task.service_id,
            "stage": request.task.stage,
        },
        kind="sensitivity_technical_status",
    )
    return ServiceResult.from_record(
        SensitivityResult(
            target_id=target_id,
            sensitivity_kind=request.task.stage,
            artifacts=(artifact,),
        )
    )


def _run_sensitive_addon_branch(request: TaskExecutionRequest) -> ServiceResult:
    return _run_addon_branch(request, model_family="addon_fiber", sensitive=True)


def _run_reference_voxel_observed(request: TaskExecutionRequest) -> ServiceResult:
    return _run_reference_observed(request, model_family="reference_voxel")


def _run_reference_fiber_observed(request: TaskExecutionRequest) -> ServiceResult:
    return _run_reference_observed(request, model_family="reference_fiber")


def _run_addon_voxel_branch(request: TaskExecutionRequest) -> ServiceResult:
    return _run_addon_branch(request, model_family="addon_voxel", sensitive=False)


def _run_addon_fiber_branch(request: TaskExecutionRequest) -> ServiceResult:
    return _run_addon_branch(request, model_family="addon_fiber", sensitive=False)


PRODUCTION_SERVICE_HANDLERS: tuple[tuple[str, ServiceHandler], ...] = (
    ("prepare_jitter_exposure_block", prepare_jitter_exposure_block),
    ("prepare_oss_omega_max_rows", _prepare_oss_omega_max_rows),
    ("prepare_ppam_observed_workspace", _prepare_ppam_observed_workspace),
    ("prepare_ppam_permutation_schedule", _prepare_ppam_permutation_schedule),
    ("run_ppam_permutation_block", _run_ppam_permutation_block),
    ("aggregate_ppam_activation", _aggregate_ppam_activation),
    (
        "prepare_formal_permutation_schedule",
        _prepare_formal_permutation_schedule,
    ),
    (
        "prepare_formal_operator_workspace",
        _prepare_formal_operator_workspace,
    ),
    ("run_formal_permutation_block", _run_formal_permutation_block),
    ("aggregate_formal_permutation", _aggregate_formal_permutation),
    (
        "prepare_formal_bootstrap_schedule",
        _prepare_formal_bootstrap_schedule,
    ),
    ("run_formal_bootstrap_block", _run_formal_bootstrap_block),
    ("aggregate_formal_bootstrap", _aggregate_formal_bootstrap),
    ("validate_reference_voxel_input", _validate_endpoint_input),
    ("prepare_reference_voxel_exposure", _prepare_exposure),
    ("run_reference_voxel_observed_grid", _run_reference_voxel_observed),
    ("resolve_reference_voxel_source", _resolve_reference_source),
    ("realize_reference_final", _realize_reference_final),
    (
        "run_reference_voxel_formal_permutation",
        partial(
            _run_formal,
            model_family="reference_voxel",
            resampling_kind="permutation",
        ),
    ),
    (
        "run_reference_voxel_formal_bootstrap",
        partial(
            _run_formal,
            model_family="reference_voxel",
            resampling_kind="bootstrap",
        ),
    ),
    (
        "run_reference_voxel_formal_in_sample",
        partial(_run_in_sample, model_family="reference_voxel"),
    ),
    ("run_reference_voxel_jitter", _run_jitter),
    ("run_reference_voxel_source_neighborhood", _run_tau_neighborhood),
    ("validate_reference_fiber_input", _validate_endpoint_input),
    ("prepare_reference_fiber_sidecar", _prepare_exposure),
    ("run_reference_fiber_observed_grid", _run_reference_fiber_observed),
    ("resolve_reference_fiber_source", _resolve_reference_source),
    (
        "run_reference_fiber_formal_permutation",
        partial(
            _run_formal,
            model_family="reference_fiber",
            resampling_kind="permutation",
        ),
    ),
    (
        "run_reference_fiber_formal_bootstrap",
        partial(
            _run_formal,
            model_family="reference_fiber",
            resampling_kind="bootstrap",
        ),
    ),
    (
        "run_reference_fiber_formal_in_sample",
        partial(_run_in_sample, model_family="reference_fiber"),
    ),
    (
        "run_reference_fiber_plain_control",
        partial(_run_reference_fiber_control, cheap=False),
    ),
    (
        "run_reference_fiber_cheap_sensitivity",
        partial(_run_reference_fiber_control, cheap=True),
    ),
    ("run_reference_fiber_activation", _run_activation),
    ("run_reference_fiber_jitter", _run_jitter),
    ("evaluate_sensitive_connectome_at_formal_source", _evaluate_sensitive_reference),
    ("validate_addon_voxel_input", _validate_endpoint_input),
    ("bind_reference_dependency", _bind_reference_dependency),
    ("prepare_addon_voxel_exposure", _prepare_exposure),
    (
        "build_voxel_delta_reference_input",
        partial(_build_delta_reference, model_family="addon_voxel"),
    ),
    ("run_addon_voxel_branch", _run_addon_voxel_branch),
    ("realize_addon_final", _realize_addon_final),
    (
        "run_addon_voxel_formal_permutation",
        partial(
            _run_formal,
            model_family="addon_voxel",
            resampling_kind="permutation",
        ),
    ),
    (
        "run_addon_voxel_formal_bootstrap",
        partial(
            _run_formal,
            model_family="addon_voxel",
            resampling_kind="bootstrap",
        ),
    ),
    (
        "run_addon_voxel_formal_in_sample",
        partial(_run_in_sample, model_family="addon_voxel"),
    ),
    ("run_addon_voxel_jitter", _run_jitter),
    ("run_addon_voxel_source_neighborhood", _run_tau_neighborhood),
    ("run_addon_voxel_additional_sensitivities", _addon_exposure_sensitivity),
    ("validate_addon_fiber_input", _validate_endpoint_input),
    ("prepare_addon_fiber_sidecars", _prepare_exposure),
    (
        "build_fiber_delta_reference_input",
        partial(_build_delta_reference, model_family="addon_fiber"),
    ),
    ("run_addon_fiber_branch", _run_addon_fiber_branch),
    (
        "run_addon_fiber_formal_permutation",
        partial(
            _run_formal,
            model_family="addon_fiber",
            resampling_kind="permutation",
        ),
    ),
    (
        "run_addon_fiber_formal_bootstrap",
        partial(
            _run_formal,
            model_family="addon_fiber",
            resampling_kind="bootstrap",
        ),
    ),
    (
        "run_addon_fiber_formal_in_sample",
        partial(_run_in_sample, model_family="addon_fiber"),
    ),
    ("run_addon_fiber_plain_burden_controls", _run_final_fiber_control),
    ("run_addon_fiber_cheap_sensitivity", _addon_exposure_sensitivity),
    ("run_addon_fiber_source_neighborhood", _run_tau_neighborhood),
    ("run_addon_fiber_activation", _run_activation),
    ("run_addon_fiber_jitter", _run_jitter),
    ("run_sensitive_addon_fiber_branch", _run_sensitive_addon_branch),
    ("evaluate_sensitive_addon_at_formal_final", _evaluate_sensitive_addon),
)


def production_registered_services() -> tuple[RegisteredService, ...]:
    """Return every production service as an explicit immutable registration."""

    identifiers = tuple(service_id for service_id, _handler in PRODUCTION_SERVICE_HANDLERS)
    if len(set(identifiers)) != len(identifiers):
        raise ServiceAdapterError("production service identifiers must be unique")
    return tuple(
        RegisteredService(service_id, handler)
        for service_id, handler in PRODUCTION_SERVICE_HANDLERS
    )


def build_default_service_registry() -> ServiceRegistry:
    """Build the complete project-neutral production service registry."""

    return ServiceRegistry(production_registered_services())


__all__ = [
    "PRODUCTION_SERVICE_HANDLERS",
    "ServiceAdapterCapabilityError",
    "ServiceAdapterError",
    "build_default_service_registry",
    "production_registered_services",
]
