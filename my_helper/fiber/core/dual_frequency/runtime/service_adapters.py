"""Explicit production service adapters for the generic workflow runtime."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Callable, TypeVar

import numpy as np

from ..backends.activation.fitting import PPAMActivationBackend
from ..backends.activation.ossdbs import OSSRowBatchArtifact
from ..backends.delta_reference import (
    build_delta_reference_fiber,
    build_delta_reference_voxel,
)
from ..backends.direct_voxel.addon import (
    AddonDirectVoxelBackend,
    AddonDirectVoxelDesignError,
)
from ..backends.direct_voxel.reference import ReferenceDirectVoxelBackend
from ..backends.formal import DirectVoxelFormalBackend, NormativeFiberFormalBackend
from ..backends.interaction.branch_resolver import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    branch_failure_record,
    branch_record_from_observed,
)
from ..backends.normative_fiber.addon import AddonFiberBackend, AddonFiberDesignError
from ..backends.normative_fiber.reference import ReferenceFiberBackend
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
    BranchRecord,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    NormativeFiberScoreSettings,
    ObservedRequest,
    ObservedResult,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SensitivityResult,
    SourceRecord,
)
from ..contracts.records import ACCEPTED_SOURCE_STATUSES
from ..workflow.executor import ServiceResult, TaskExecutionRequest
from ..workflow.registry import RegisteredService, ServiceRegistry
from ..workflow.state import BranchPlan, derive_branch_plan, realize_final
from .activation_provider import OSSActivationProvider, OSSActivationRuntimeRequest
from .input_provider import RuntimeInputProvider, StudyRuntimeInputProvider
from .jitter_provider import StudyJitterReplicateProvider


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
    prepared = _one_record(request, PreparedExposureRecord)
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
        facts={
            "reference_source_accepted": computable,
            "formal_source_available": computable,
        },
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
    endpoint_input = _one_record(request, EndpointInputRecord)
    prepared = _one_record(request, PreparedExposureRecord)
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


def _run_formal(
    request: TaskExecutionRequest,
    *,
    model_family: str,
    resampling_kind: str,
) -> ServiceResult:
    formal_request = _formal_request(request, resampling_kind=resampling_kind)
    publisher = _publisher(request)
    nuisance_provider = (
        request.provider
        if isinstance(request.provider, BootstrapNuisanceProvider)
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
    prepared = _one_record(request, PreparedExposureRecord)
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
    # The strategy defines total exposure by disabling overlap-mask application
    # while retaining the exact realized request identity.
    total_request = observed

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
        total = np.mean(_materialize(request, prepared.total_exposure), axis=1)
        reference_component = np.mean(
            _materialize(request, prepared.addon_reference_component_exposure),
            axis=1,
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
    if isinstance(request.provider, JitterReplicateProvider):
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
        array_provider=request.artifact_store,
    ).run(jitter_request)
    return ServiceResult.from_record(result)


def _run_activation(request: TaskExecutionRequest) -> ServiceResult:
    endpoint_input = _endpoint_input_record(request, request.task.endpoint_id)
    prepared = _one_record(request, PreparedExposureRecord)
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
    runtime_request = runtime_method(
        selection.final_model,
        endpoint_input,
        prepared,
        publisher,
        workers=request.workers,
        allow_expensive_producers=request.allow_expensive_producers,
    )
    if not isinstance(runtime_request, OSSActivationRuntimeRequest):
        raise ServiceAdapterError(
            "activation_runtime_request must return OSSActivationRuntimeRequest"
        )
    toolchain_method = getattr(request.provider, "oss_producer_toolchain", None)
    toolchain = (
        toolchain_method()
        if request.allow_expensive_producers and callable(toolchain_method)
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
    result = PPAMActivationBackend(
        publisher,
        artifact_store=request.artifact_store,
    ).run_activation(activation_request)
    if not isinstance(result, ActivationArtifact):
        raise ServiceAdapterError("activation backend returned an invalid record")
    return ServiceResult.from_record(result)


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
