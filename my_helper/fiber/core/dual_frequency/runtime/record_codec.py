"""Explicit v1 codec for persisted dual-frequency scientific records."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import fields
from typing import Any

from ..contracts import (
    ActivationArtifact,
    ArtifactRef,
    AxisRef,
    BootstrapBlockRecord,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalDecisionRecord,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    FormalOperatorScratchRecord,
    FormalResult,
    ObservedResult,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    ResamplingBlockRecord,
    ResamplingScheduleRecord,
    ScratchArrayRecord,
    SensitiveRecord,
    SensitivityResult,
    SourceRecord,
    SubjectExclusionRecord,
)


class RecordCodecError(ValueError):
    """Raised when a persisted record fails the closed codec contract."""


_ROOT_TYPES = {
    "EndpointInputRecord": EndpointInputRecord,
    "PreparedExposureRecord": PreparedExposureRecord,
    "ArtifactRef": ArtifactRef,
    "BootstrapBlockRecord": BootstrapBlockRecord,
    "ObservedResult": ObservedResult,
    "SourceRecord": SourceRecord,
    "ReferenceDependencyRecord": ReferenceDependencyRecord,
    "ResamplingScheduleRecord": ResamplingScheduleRecord,
    "ResamplingBlockRecord": ResamplingBlockRecord,
    "DeltaReferenceBundle": DeltaReferenceBundle,
    "BranchRecord": BranchRecord,
    "FinalModelRecord": FinalModelRecord,
    "FinalSelectionRecord": FinalSelectionRecord,
    "FormalOperatorScratchRecord": FormalOperatorScratchRecord,
    "SensitiveRecord": SensitiveRecord,
    "FormalResult": FormalResult,
    "SensitivityResult": SensitivityResult,
    "ActivationArtifact": ActivationArtifact,
}

_NESTED_TYPES = frozenset(
    {
        EndpointKey,
        FinalModelKey,
        AxisRef,
        FeatureAxisRef,
        SubjectExclusionRecord,
        FinalDecisionRecord,
        ScratchArrayRecord,
        *_ROOT_TYPES.values(),
    }
)
_HELPER_ROOT_TYPES = frozenset({FinalDecisionRecord, *_ROOT_TYPES.values()})


def _encode_value(value: object, location: str) -> Any:
    value_type = type(value)
    if value_type in _NESTED_TYPES:
        return {
            field.name: _encode_value(
                getattr(value, field.name),
                f"{location}.{field.name}",
            )
            for field in fields(value)
        }
    if isinstance(value, tuple):
        return [
            _encode_value(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise RecordCodecError(f"{location} contains a nonfinite float")
        return value
    raise RecordCodecError(
        f"{location} contains unsupported value type {value_type.__name__!r}"
    )


def encode_record(record: object) -> dict[str, Any]:
    """Encode one exact allowlisted root to a JSON-safe field mapping."""

    record_type = type(record)
    if record_type not in _ROOT_TYPES.values():
        raise RecordCodecError(
            f"{record_type.__name__!r} is not an allowlisted root record type"
        )
    payload = _encode_value(record, record_type.__name__)
    if not isinstance(payload, dict):
        raise RecordCodecError("encoded root record must be a mapping")
    return payload


def _mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordCodecError(f"{location} must be an object")
    if not all(type(key) is str for key in value):
        raise RecordCodecError(f"{location} keys must be strings")
    return value


def _object(
    value: object,
    location: str,
    expected_fields: frozenset[str],
) -> Mapping[str, Any]:
    payload = _mapping(value, location)
    actual_fields = frozenset(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        raise RecordCodecError(
            f"{location} fields do not match; missing={missing}, extra={extra}"
        )
    return payload


def _array(value: object, location: str) -> list[Any]:
    if type(value) is not list:
        raise RecordCodecError(f"{location} must be an array")
    return value


def _text(value: object, location: str) -> str:
    if type(value) is not str:
        raise RecordCodecError(f"{location} must be a string")
    if not value or value != value.strip():
        raise RecordCodecError(f"{location} must be a canonical nonempty string")
    return value


def _optional_text(value: object, location: str) -> str | None:
    if value is None:
        return None
    return _text(value, location)


def _integer(value: object, location: str) -> int:
    if type(value) is not int:
        raise RecordCodecError(f"{location} must be an integer")
    return value


def _boolean(value: object, location: str) -> bool:
    if type(value) is not bool:
        raise RecordCodecError(f"{location} must be a boolean")
    return value


def _optional_integer(value: object, location: str) -> int | None:
    if value is None:
        return None
    return _integer(value, location)


def _number(value: object, location: str) -> float:
    if type(value) is not float:
        raise RecordCodecError(f"{location} must be a floating-point number")
    if not math.isfinite(value):
        raise RecordCodecError(f"{location} must be finite")
    return value


def _optional_number(value: object, location: str) -> float | None:
    if value is None:
        return None
    return _number(value, location)


def _tuple_of(
    value: object,
    location: str,
    decoder: Callable[[object, str], Any],
) -> tuple[Any, ...]:
    return tuple(
        decoder(item, f"{location}[{index}]")
        for index, item in enumerate(_array(value, location))
    )


def _optional(
    value: object,
    location: str,
    decoder: Callable[[object, str], Any],
) -> Any | None:
    if value is None:
        return None
    return decoder(value, location)


_AXIS_FIELDS = frozenset({"axis_id", "count", "sha256"})
_FEATURE_AXIS_FIELDS = frozenset({"axis", "identity_source"})
_ENDPOINT_FIELDS = frozenset(
    {
        "study_id",
        "scale_id",
        "endpoint_binding_id",
        "model_family",
        "connectome_id",
    }
)
_FINAL_KEY_FIELDS = frozenset(
    {
        "endpoint_id",
        "final_branch",
        "selected_tau",
        "selected_coverage",
        "estimator",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "uri",
        "sha256",
        "dtype",
        "shape",
        "axis_refs",
        "axis_hashes",
        "units",
        "space",
        "producer_id",
        "producer_version",
    }
)
_SUBJECT_EXCLUSION_FIELDS = frozenset({"subject_id", "reason_code"})
_ENDPOINT_INPUT_FIELDS = frozenset(
    {
        "endpoint",
        "readiness_status",
        "candidate_subject_ids",
        "included_subject_ids",
        "exclusions",
        "minimum_subjects",
        "subject_axis",
        "baseline",
        "outcome",
    }
)
_PREPARED_EXPOSURE_FIELDS = frozenset(
    {
        "endpoint",
        "subject_axis",
        "feature_axis",
        "exposure",
        "feature_ids",
        "delta_reference_input_status",
        "delta_reference_reason_code",
        "auxiliary_readiness",
        "reference_condition_exposure",
        "addon_reference_component_exposure",
        "reference_overlap_mask",
        "total_exposure",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "endpoint",
        "input_status",
        "source_status",
        "prediction_status",
        "threshold_source",
        "selected_tau",
        "selected_coverage",
        "adjacent_support",
        "feature_axis",
        "artifacts",
    }
)
_DELTA_REFERENCE_FIELDS = frozenset(
    {
        "input_status",
        "support_status",
        "selected_reference_tau",
        "selected_reference_coverage",
        "full_scores",
        "fold_scores",
        "support_rows",
        "support_qc",
        "failure_stage",
        "failure_detail",
    }
)
_SENSITIVE_FIELDS = frozenset(
    {
        "endpoint",
        "formal_endpoint_id",
        "evaluated_tau",
        "evaluated_coverage",
        "input_status",
        "cell_computability_status",
        "prediction_status",
        "feature_axis",
        "artifacts",
    }
)
_REFERENCE_DEPENDENCY_FIELDS = frozenset(
    {
        "addon_endpoint",
        "matched_reference_endpoint_id",
        "dependency_status",
        "reference_record",
        "delta_reference",
    }
)
_BRANCH_FIELDS = frozenset(
    {
        "endpoint",
        "branch",
        "intended_role",
        "input_status",
        "nuisance_design_status",
        "source",
        "artifacts",
        "failure_stage",
        "failure_detail",
    }
)
_FINAL_MODEL_FIELDS = frozenset(
    {
        "endpoint",
        "final_status",
        "realization_role",
        "final_key",
        "selected_source",
        "selected_branch",
        "artifacts",
    }
)
_FINAL_SELECTION_FIELDS = frozenset(
    {
        "endpoint",
        "selection_status",
        "final_model",
        "reason_codes",
        "causal_task_ids",
    }
)
_OBSERVED_RESULT_FIELDS = frozenset({"source", "artifacts"})
_FORMAL_RESULT_FIELDS = frozenset(
    {"final_model_id", "resampling_kind", "technical_status", "artifacts"}
)
_RESAMPLING_SCHEDULE_FIELDS = frozenset(
    {
        "target_id",
        "resampling_kind",
        "subject_axis",
        "replicate_axis",
        "seed",
        "replicate_count",
        "block_size",
        "schedule_schema",
        "generator_class",
        "bit_generator_class",
        "numpy_version",
        "environment_fingerprint",
        "schedule_sha256",
        "schedule",
    }
)
_RESAMPLING_BLOCK_FIELDS = frozenset(
    {
        "target_id",
        "resampling_kind",
        "schedule_id",
        "replicate_axis",
        "block_axis",
        "block_index",
        "start",
        "stop",
        "total",
        "schedule_sha256",
        "technical_status",
        "artifacts",
    }
)
_BOOTSTRAP_BLOCK_FIELDS = frozenset(
    {
        "target_id",
        "schedule_id",
        "feature_axis",
        "feature_space",
        "replicate_axis",
        "block_axis",
        "block_index",
        "start",
        "stop",
        "total",
        "schedule_sha256",
        "selection_mode",
        "nuisance_evidence_mode",
        "technical_status",
        "artifacts",
    }
)
_SCRATCH_ARRAY_FIELDS = frozenset(
    {"name", "filename", "dtype", "shape", "fortran_order", "nbytes"}
)
_FORMAL_OPERATOR_SCRATCH_FIELDS = frozenset(
    {
        "target_id",
        "model_family",
        "subject_axis",
        "feature_axis",
        "input_identity",
        "operator_schema",
        "technical_status",
        "generation_path",
        "arrays",
        "total_nbytes",
    }
)
_SENSITIVITY_RESULT_FIELDS = frozenset(
    {"target_id", "sensitivity_kind", "artifacts"}
)
_ACTIVATION_ARTIFACT_FIELDS = frozenset(
    {
        "final_model_id",
        "feature_axis",
        "activation_probability",
        "binary_exposure",
        "artifacts",
    }
)


def _decode_axis(value: object, location: str) -> AxisRef:
    payload = _object(value, location, _AXIS_FIELDS)
    return AxisRef(
        axis_id=_text(payload["axis_id"], f"{location}.axis_id"),
        count=_integer(payload["count"], f"{location}.count"),
        sha256=_text(payload["sha256"], f"{location}.sha256"),
    )


def _decode_feature_axis(value: object, location: str) -> FeatureAxisRef:
    payload = _object(value, location, _FEATURE_AXIS_FIELDS)
    return FeatureAxisRef(
        axis=_decode_axis(payload["axis"], f"{location}.axis"),
        identity_source=_text(
            payload["identity_source"],
            f"{location}.identity_source",
        ),
    )


def _decode_endpoint(value: object, location: str) -> EndpointKey:
    payload = _object(value, location, _ENDPOINT_FIELDS)
    return EndpointKey(
        study_id=_text(payload["study_id"], f"{location}.study_id"),
        scale_id=_text(payload["scale_id"], f"{location}.scale_id"),
        endpoint_binding_id=_text(
            payload["endpoint_binding_id"],
            f"{location}.endpoint_binding_id",
        ),
        model_family=_text(payload["model_family"], f"{location}.model_family"),
        connectome_id=_text(payload["connectome_id"], f"{location}.connectome_id"),
    )


def _decode_final_key(value: object, location: str) -> FinalModelKey:
    payload = _object(value, location, _FINAL_KEY_FIELDS)
    return FinalModelKey(
        endpoint_id=_text(payload["endpoint_id"], f"{location}.endpoint_id"),
        final_branch=_text(payload["final_branch"], f"{location}.final_branch"),
        selected_tau=_number(payload["selected_tau"], f"{location}.selected_tau"),
        selected_coverage=_integer(
            payload["selected_coverage"],
            f"{location}.selected_coverage",
        ),
        estimator=_text(payload["estimator"], f"{location}.estimator"),
    )


def _decode_artifact(value: object, location: str) -> ArtifactRef:
    payload = _object(value, location, _ARTIFACT_FIELDS)
    shape_value = payload["shape"]
    shape = None
    if shape_value is not None:
        shape = _tuple_of(shape_value, f"{location}.shape", _integer)
    return ArtifactRef(
        kind=_text(payload["kind"], f"{location}.kind"),
        schema_version=_text(
            payload["schema_version"],
            f"{location}.schema_version",
        ),
        uri=_text(payload["uri"], f"{location}.uri"),
        sha256=_text(payload["sha256"], f"{location}.sha256"),
        dtype=_optional_text(payload["dtype"], f"{location}.dtype"),
        shape=shape,
        axis_refs=_tuple_of(
            payload["axis_refs"],
            f"{location}.axis_refs",
            _decode_axis,
        ),
        axis_hashes=_tuple_of(
            payload["axis_hashes"],
            f"{location}.axis_hashes",
            _text,
        ),
        units=_optional_text(payload["units"], f"{location}.units"),
        space=_optional_text(payload["space"], f"{location}.space"),
        producer_id=_text(payload["producer_id"], f"{location}.producer_id"),
        producer_version=_text(
            payload["producer_version"],
            f"{location}.producer_version",
        ),
    )


def _decode_subject_exclusion(
    value: object,
    location: str,
) -> SubjectExclusionRecord:
    payload = _object(value, location, _SUBJECT_EXCLUSION_FIELDS)
    return SubjectExclusionRecord(
        subject_id=_text(payload["subject_id"], f"{location}.subject_id"),
        reason_code=_text(payload["reason_code"], f"{location}.reason_code"),
    )


def _decode_endpoint_input(value: object, location: str) -> EndpointInputRecord:
    payload = _object(value, location, _ENDPOINT_INPUT_FIELDS)
    return EndpointInputRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        readiness_status=_text(
            payload["readiness_status"],
            f"{location}.readiness_status",
        ),
        candidate_subject_ids=_tuple_of(
            payload["candidate_subject_ids"],
            f"{location}.candidate_subject_ids",
            _text,
        ),
        included_subject_ids=_tuple_of(
            payload["included_subject_ids"],
            f"{location}.included_subject_ids",
            _text,
        ),
        exclusions=_tuple_of(
            payload["exclusions"],
            f"{location}.exclusions",
            _decode_subject_exclusion,
        ),
        minimum_subjects=_integer(
            payload["minimum_subjects"],
            f"{location}.minimum_subjects",
        ),
        subject_axis=_optional(
            payload["subject_axis"],
            f"{location}.subject_axis",
            _decode_axis,
        ),
        baseline=_optional(
            payload["baseline"],
            f"{location}.baseline",
            _decode_artifact,
        ),
        outcome=_optional(
            payload["outcome"],
            f"{location}.outcome",
            _decode_artifact,
        ),
    )


def _decode_prepared_exposure(
    value: object,
    location: str,
) -> PreparedExposureRecord:
    payload = _object(value, location, _PREPARED_EXPOSURE_FIELDS)
    return PreparedExposureRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        subject_axis=_decode_axis(
            payload["subject_axis"],
            f"{location}.subject_axis",
        ),
        feature_axis=_decode_axis(
            payload["feature_axis"],
            f"{location}.feature_axis",
        ),
        exposure=_decode_artifact(payload["exposure"], f"{location}.exposure"),
        feature_ids=_decode_artifact(
            payload["feature_ids"],
            f"{location}.feature_ids",
        ),
        delta_reference_input_status=_text(
            payload["delta_reference_input_status"],
            f"{location}.delta_reference_input_status",
        ),
        delta_reference_reason_code=_text(
            payload["delta_reference_reason_code"],
            f"{location}.delta_reference_reason_code",
        ),
        auxiliary_readiness=_optional(
            payload["auxiliary_readiness"],
            f"{location}.auxiliary_readiness",
            _decode_artifact,
        ),
        reference_condition_exposure=_optional(
            payload["reference_condition_exposure"],
            f"{location}.reference_condition_exposure",
            _decode_artifact,
        ),
        addon_reference_component_exposure=_optional(
            payload["addon_reference_component_exposure"],
            f"{location}.addon_reference_component_exposure",
            _decode_artifact,
        ),
        reference_overlap_mask=_optional(
            payload["reference_overlap_mask"],
            f"{location}.reference_overlap_mask",
            _decode_artifact,
        ),
        total_exposure=_optional(
            payload["total_exposure"],
            f"{location}.total_exposure",
            _decode_artifact,
        ),
    )


def _decode_source(value: object, location: str) -> SourceRecord:
    payload = _object(value, location, _SOURCE_FIELDS)
    return SourceRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        input_status=_text(payload["input_status"], f"{location}.input_status"),
        source_status=_text(payload["source_status"], f"{location}.source_status"),
        prediction_status=_text(
            payload["prediction_status"],
            f"{location}.prediction_status",
        ),
        threshold_source=_text(
            payload["threshold_source"],
            f"{location}.threshold_source",
        ),
        selected_tau=_optional_number(
            payload["selected_tau"],
            f"{location}.selected_tau",
        ),
        selected_coverage=_optional_integer(
            payload["selected_coverage"],
            f"{location}.selected_coverage",
        ),
        adjacent_support=_optional_integer(
            payload["adjacent_support"],
            f"{location}.adjacent_support",
        ),
        feature_axis=_optional(
            payload["feature_axis"],
            f"{location}.feature_axis",
            _decode_feature_axis,
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_delta_reference(
    value: object,
    location: str,
) -> DeltaReferenceBundle:
    payload = _object(value, location, _DELTA_REFERENCE_FIELDS)
    return DeltaReferenceBundle(
        input_status=_text(payload["input_status"], f"{location}.input_status"),
        support_status=_text(payload["support_status"], f"{location}.support_status"),
        selected_reference_tau=_optional_number(
            payload["selected_reference_tau"],
            f"{location}.selected_reference_tau",
        ),
        selected_reference_coverage=_optional_integer(
            payload["selected_reference_coverage"],
            f"{location}.selected_reference_coverage",
        ),
        full_scores=_optional(
            payload["full_scores"],
            f"{location}.full_scores",
            _decode_artifact,
        ),
        fold_scores=_optional(
            payload["fold_scores"],
            f"{location}.fold_scores",
            _decode_artifact,
        ),
        support_rows=_optional(
            payload["support_rows"],
            f"{location}.support_rows",
            _decode_artifact,
        ),
        support_qc=_optional(
            payload["support_qc"],
            f"{location}.support_qc",
            _decode_artifact,
        ),
        failure_stage=_text(
            payload["failure_stage"],
            f"{location}.failure_stage",
        ),
        failure_detail=_text(
            payload["failure_detail"],
            f"{location}.failure_detail",
        ),
    )


def _decode_sensitive(value: object, location: str) -> SensitiveRecord:
    payload = _object(value, location, _SENSITIVE_FIELDS)
    return SensitiveRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        formal_endpoint_id=_text(
            payload["formal_endpoint_id"],
            f"{location}.formal_endpoint_id",
        ),
        evaluated_tau=_number(
            payload["evaluated_tau"],
            f"{location}.evaluated_tau",
        ),
        evaluated_coverage=_integer(
            payload["evaluated_coverage"],
            f"{location}.evaluated_coverage",
        ),
        input_status=_text(payload["input_status"], f"{location}.input_status"),
        cell_computability_status=_text(
            payload["cell_computability_status"],
            f"{location}.cell_computability_status",
        ),
        prediction_status=_text(
            payload["prediction_status"],
            f"{location}.prediction_status",
        ),
        feature_axis=_optional(
            payload["feature_axis"],
            f"{location}.feature_axis",
            _decode_feature_axis,
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_reference_record(value: object, location: str) -> SourceRecord | SensitiveRecord:
    payload = _mapping(value, location)
    payload_fields = frozenset(payload)
    if payload_fields == _SOURCE_FIELDS:
        return _decode_source(payload, location)
    if payload_fields == _SENSITIVE_FIELDS:
        return _decode_sensitive(payload, location)
    raise RecordCodecError(
        f"{location} fields do not match SourceRecord or SensitiveRecord"
    )


def _decode_reference_dependency(
    value: object,
    location: str,
) -> ReferenceDependencyRecord:
    payload = _object(value, location, _REFERENCE_DEPENDENCY_FIELDS)
    return ReferenceDependencyRecord(
        addon_endpoint=_decode_endpoint(
            payload["addon_endpoint"],
            f"{location}.addon_endpoint",
        ),
        matched_reference_endpoint_id=_text(
            payload["matched_reference_endpoint_id"],
            f"{location}.matched_reference_endpoint_id",
        ),
        dependency_status=_text(
            payload["dependency_status"],
            f"{location}.dependency_status",
        ),
        reference_record=_optional(
            payload["reference_record"],
            f"{location}.reference_record",
            _decode_reference_record,
        ),
        delta_reference=_optional(
            payload["delta_reference"],
            f"{location}.delta_reference",
            _decode_delta_reference,
        ),
    )


def _decode_branch(value: object, location: str) -> BranchRecord:
    payload = _object(value, location, _BRANCH_FIELDS)
    return BranchRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        branch=_text(payload["branch"], f"{location}.branch"),
        intended_role=_text(
            payload["intended_role"],
            f"{location}.intended_role",
        ),
        input_status=_text(payload["input_status"], f"{location}.input_status"),
        nuisance_design_status=_text(
            payload["nuisance_design_status"],
            f"{location}.nuisance_design_status",
        ),
        source=_optional(
            payload["source"],
            f"{location}.source",
            _decode_source,
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
        failure_stage=_text(
            payload["failure_stage"],
            f"{location}.failure_stage",
        ),
        failure_detail=_text(
            payload["failure_detail"],
            f"{location}.failure_detail",
        ),
    )


def _decode_final_model(value: object, location: str) -> FinalModelRecord:
    payload = _object(value, location, _FINAL_MODEL_FIELDS)
    return FinalModelRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        final_status=_text(payload["final_status"], f"{location}.final_status"),
        realization_role=_text(
            payload["realization_role"],
            f"{location}.realization_role",
        ),
        final_key=_optional(
            payload["final_key"],
            f"{location}.final_key",
            _decode_final_key,
        ),
        selected_source=_optional(
            payload["selected_source"],
            f"{location}.selected_source",
            _decode_source,
        ),
        selected_branch=_optional(
            payload["selected_branch"],
            f"{location}.selected_branch",
            _decode_branch,
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_final_selection(
    value: object,
    location: str,
) -> FinalSelectionRecord:
    payload = _object(value, location, _FINAL_SELECTION_FIELDS)
    return FinalSelectionRecord(
        endpoint=_decode_endpoint(payload["endpoint"], f"{location}.endpoint"),
        selection_status=_text(
            payload["selection_status"],
            f"{location}.selection_status",
        ),
        final_model=_optional(
            payload["final_model"],
            f"{location}.final_model",
            _decode_final_model,
        ),
        reason_codes=_tuple_of(
            payload["reason_codes"],
            f"{location}.reason_codes",
            _text,
        ),
        causal_task_ids=_tuple_of(
            payload["causal_task_ids"],
            f"{location}.causal_task_ids",
            _text,
        ),
    )


def _decode_observed_result(value: object, location: str) -> ObservedResult:
    payload = _object(value, location, _OBSERVED_RESULT_FIELDS)
    return ObservedResult(
        source=_optional(
            payload["source"],
            f"{location}.source",
            _decode_source,
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_formal_result(value: object, location: str) -> FormalResult:
    payload = _object(value, location, _FORMAL_RESULT_FIELDS)
    return FormalResult(
        final_model_id=_text(
            payload["final_model_id"],
            f"{location}.final_model_id",
        ),
        resampling_kind=_text(
            payload["resampling_kind"],
            f"{location}.resampling_kind",
        ),
        technical_status=_text(
            payload["technical_status"],
            f"{location}.technical_status",
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_resampling_schedule(
    value: object,
    location: str,
) -> ResamplingScheduleRecord:
    payload = _object(value, location, _RESAMPLING_SCHEDULE_FIELDS)
    return ResamplingScheduleRecord(
        target_id=_text(payload["target_id"], f"{location}.target_id"),
        resampling_kind=_text(
            payload["resampling_kind"],
            f"{location}.resampling_kind",
        ),
        subject_axis=_decode_axis(
            payload["subject_axis"],
            f"{location}.subject_axis",
        ),
        replicate_axis=_decode_axis(
            payload["replicate_axis"],
            f"{location}.replicate_axis",
        ),
        seed=_integer(payload["seed"], f"{location}.seed"),
        replicate_count=_integer(
            payload["replicate_count"],
            f"{location}.replicate_count",
        ),
        block_size=_integer(payload["block_size"], f"{location}.block_size"),
        schedule_schema=_text(
            payload["schedule_schema"],
            f"{location}.schedule_schema",
        ),
        generator_class=_text(
            payload["generator_class"],
            f"{location}.generator_class",
        ),
        bit_generator_class=_text(
            payload["bit_generator_class"],
            f"{location}.bit_generator_class",
        ),
        numpy_version=_text(
            payload["numpy_version"],
            f"{location}.numpy_version",
        ),
        environment_fingerprint=_text(
            payload["environment_fingerprint"],
            f"{location}.environment_fingerprint",
        ),
        schedule_sha256=_text(
            payload["schedule_sha256"],
            f"{location}.schedule_sha256",
        ),
        schedule=_decode_artifact(
            payload["schedule"],
            f"{location}.schedule",
        ),
    )


def _decode_resampling_block(
    value: object,
    location: str,
) -> ResamplingBlockRecord:
    payload = _object(value, location, _RESAMPLING_BLOCK_FIELDS)
    return ResamplingBlockRecord(
        target_id=_text(payload["target_id"], f"{location}.target_id"),
        resampling_kind=_text(
            payload["resampling_kind"],
            f"{location}.resampling_kind",
        ),
        schedule_id=_text(payload["schedule_id"], f"{location}.schedule_id"),
        replicate_axis=_decode_axis(
            payload["replicate_axis"],
            f"{location}.replicate_axis",
        ),
        block_axis=_decode_axis(
            payload["block_axis"],
            f"{location}.block_axis",
        ),
        block_index=_integer(
            payload["block_index"],
            f"{location}.block_index",
        ),
        start=_integer(payload["start"], f"{location}.start"),
        stop=_integer(payload["stop"], f"{location}.stop"),
        total=_integer(payload["total"], f"{location}.total"),
        schedule_sha256=_text(
            payload["schedule_sha256"],
            f"{location}.schedule_sha256",
        ),
        technical_status=_text(
            payload["technical_status"],
            f"{location}.technical_status",
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_bootstrap_block(
    value: object,
    location: str,
) -> BootstrapBlockRecord:
    payload = _object(value, location, _BOOTSTRAP_BLOCK_FIELDS)
    return BootstrapBlockRecord(
        target_id=_text(payload["target_id"], f"{location}.target_id"),
        schedule_id=_text(payload["schedule_id"], f"{location}.schedule_id"),
        feature_axis=_decode_axis(
            payload["feature_axis"],
            f"{location}.feature_axis",
        ),
        feature_space=_text(
            payload["feature_space"],
            f"{location}.feature_space",
        ),
        replicate_axis=_decode_axis(
            payload["replicate_axis"],
            f"{location}.replicate_axis",
        ),
        block_axis=_decode_axis(
            payload["block_axis"],
            f"{location}.block_axis",
        ),
        block_index=_integer(
            payload["block_index"],
            f"{location}.block_index",
        ),
        start=_integer(payload["start"], f"{location}.start"),
        stop=_integer(payload["stop"], f"{location}.stop"),
        total=_integer(payload["total"], f"{location}.total"),
        schedule_sha256=_text(
            payload["schedule_sha256"],
            f"{location}.schedule_sha256",
        ),
        selection_mode=_text(
            payload["selection_mode"],
            f"{location}.selection_mode",
        ),
        nuisance_evidence_mode=_text(
            payload["nuisance_evidence_mode"],
            f"{location}.nuisance_evidence_mode",
        ),
        technical_status=_text(
            payload["technical_status"],
            f"{location}.technical_status",
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_scratch_array(
    value: object,
    location: str,
) -> ScratchArrayRecord:
    payload = _object(value, location, _SCRATCH_ARRAY_FIELDS)
    return ScratchArrayRecord(
        name=_text(payload["name"], f"{location}.name"),
        filename=_text(payload["filename"], f"{location}.filename"),
        dtype=_text(payload["dtype"], f"{location}.dtype"),
        shape=_tuple_of(payload["shape"], f"{location}.shape", _integer),
        fortran_order=_boolean(
            payload["fortran_order"],
            f"{location}.fortran_order",
        ),
        nbytes=_integer(payload["nbytes"], f"{location}.nbytes"),
    )


def _decode_formal_operator_scratch(
    value: object,
    location: str,
) -> FormalOperatorScratchRecord:
    payload = _object(value, location, _FORMAL_OPERATOR_SCRATCH_FIELDS)
    return FormalOperatorScratchRecord(
        target_id=_text(payload["target_id"], f"{location}.target_id"),
        model_family=_text(payload["model_family"], f"{location}.model_family"),
        subject_axis=_decode_axis(
            payload["subject_axis"],
            f"{location}.subject_axis",
        ),
        feature_axis=_decode_axis(
            payload["feature_axis"],
            f"{location}.feature_axis",
        ),
        input_identity=_text(
            payload["input_identity"],
            f"{location}.input_identity",
        ),
        operator_schema=_text(
            payload["operator_schema"],
            f"{location}.operator_schema",
        ),
        technical_status=_text(
            payload["technical_status"],
            f"{location}.technical_status",
        ),
        generation_path=_text(
            payload["generation_path"],
            f"{location}.generation_path",
        ),
        arrays=_tuple_of(
            payload["arrays"],
            f"{location}.arrays",
            _decode_scratch_array,
        ),
        total_nbytes=_integer(
            payload["total_nbytes"],
            f"{location}.total_nbytes",
        ),
    )


def _decode_sensitivity_result(
    value: object,
    location: str,
) -> SensitivityResult:
    payload = _object(value, location, _SENSITIVITY_RESULT_FIELDS)
    return SensitivityResult(
        target_id=_text(payload["target_id"], f"{location}.target_id"),
        sensitivity_kind=_text(
            payload["sensitivity_kind"],
            f"{location}.sensitivity_kind",
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


def _decode_activation_artifact(
    value: object,
    location: str,
) -> ActivationArtifact:
    payload = _object(value, location, _ACTIVATION_ARTIFACT_FIELDS)
    return ActivationArtifact(
        final_model_id=_text(
            payload["final_model_id"],
            f"{location}.final_model_id",
        ),
        feature_axis=_decode_axis(
            payload["feature_axis"],
            f"{location}.feature_axis",
        ),
        activation_probability=_decode_artifact(
            payload["activation_probability"],
            f"{location}.activation_probability",
        ),
        binary_exposure=_decode_artifact(
            payload["binary_exposure"],
            f"{location}.binary_exposure",
        ),
        artifacts=_tuple_of(
            payload["artifacts"],
            f"{location}.artifacts",
            _decode_artifact,
        ),
    )


_ROOT_DECODERS: dict[str, Callable[[object, str], object]] = {
    "EndpointInputRecord": _decode_endpoint_input,
    "PreparedExposureRecord": _decode_prepared_exposure,
    "ArtifactRef": _decode_artifact,
    "ObservedResult": _decode_observed_result,
    "SourceRecord": _decode_source,
    "ReferenceDependencyRecord": _decode_reference_dependency,
    "DeltaReferenceBundle": _decode_delta_reference,
    "BranchRecord": _decode_branch,
    "FinalModelRecord": _decode_final_model,
    "FinalSelectionRecord": _decode_final_selection,
    "FormalOperatorScratchRecord": _decode_formal_operator_scratch,
    "SensitiveRecord": _decode_sensitive,
    "FormalResult": _decode_formal_result,
    "ResamplingScheduleRecord": _decode_resampling_schedule,
    "ResamplingBlockRecord": _decode_resampling_block,
    "BootstrapBlockRecord": _decode_bootstrap_block,
    "SensitivityResult": _decode_sensitivity_result,
    "ActivationArtifact": _decode_activation_artifact,
}
if frozenset(_ROOT_DECODERS) != frozenset(_ROOT_TYPES):
    raise RuntimeError("record codec root encoders and decoders must match exactly")


def record_identifier(record: object) -> str:
    """Return the canonical identifier for one codec or aggregate record."""

    if type(record) not in _HELPER_ROOT_TYPES:
        raise RecordCodecError(
            f"{type(record).__name__!r} has no codec record identifier"
        )
    identifier = getattr(record, "identifier", None)
    if type(identifier) is not str or not identifier:
        raise RecordCodecError(
            f"{type(record).__name__!r} has no valid identifier property"
        )
    return identifier


def record_artifacts(record: object) -> tuple[ArtifactRef, ...]:
    """Return the deterministic de-duplicated transitive artifact closure."""

    if type(record) not in _HELPER_ROOT_TYPES:
        raise RecordCodecError(
            f"{type(record).__name__!r} has no codec artifact closure"
        )
    output: list[ArtifactRef] = []
    seen: dict[str, ArtifactRef] = {}

    def visit(value: object, location: str) -> None:
        if type(value) is ArtifactRef:
            artifact_id = value.identifier
            previous = seen.get(artifact_id)
            if previous is not None:
                if previous != value:
                    raise RecordCodecError(
                        f"{location} collides with a different artifact identity"
                    )
                return
            seen[artifact_id] = value
            output.append(value)
            return
        if type(value) in _NESTED_TYPES:
            for field in fields(value):
                visit(getattr(value, field.name), f"{location}.{field.name}")
            return
        if isinstance(value, tuple):
            for index, item in enumerate(value):
                visit(item, f"{location}[{index}]")
            return
        if value is None or type(value) in {str, int, float, bool}:
            return
        raise RecordCodecError(
            f"{location} contains unsupported closure value {type(value).__name__!r}"
        )

    visit(record, type(record).__name__)
    return tuple(output)


def decode_record(
    output_record_type: str,
    payload: Mapping[str, Any],
    *,
    record_id: str,
    artifacts: tuple[ArtifactRef, ...],
) -> object:
    """Decode and validate one complete persisted service-result envelope."""

    if (
        type(output_record_type) is not str
        or not output_record_type
        or output_record_type != output_record_type.strip()
    ):
        raise RecordCodecError("output_record_type must be a nonempty string")
    decoder = _ROOT_DECODERS.get(output_record_type)
    if decoder is None:
        raise RecordCodecError(f"unknown record type {output_record_type!r}")
    if type(record_id) is not str or not record_id or record_id != record_id.strip():
        raise RecordCodecError("record_id must be a nonempty string")
    if type(artifacts) is not tuple or not all(
        type(artifact) is ArtifactRef for artifact in artifacts
    ):
        raise RecordCodecError("artifacts must be a tuple of ArtifactRef values")

    try:
        record = decoder(payload, output_record_type)
    except RecordCodecError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordCodecError(
            f"invalid {output_record_type} payload: {exc}"
        ) from exc

    decoded_type = type(record).__name__
    if decoded_type != output_record_type:
        raise RecordCodecError(
            f"record type mismatch: declared {output_record_type!r}, "
            f"decoded {decoded_type!r}"
        )
    computed_id = record_identifier(record)
    if computed_id != record_id:
        raise RecordCodecError(
            f"record identifier mismatch: declared {record_id!r}, "
            f"computed {computed_id!r}"
        )
    closure = record_artifacts(record)
    if closure != artifacts:
        raise RecordCodecError(
            "artifact closure mismatch: persisted artifacts must exactly match "
            "the decoded record closure"
        )
    return record
