"""Durable pPAM permutation-schedule publication and restoration."""

from __future__ import annotations

import numpy as np

from ..backends.formal.common import (
    FORMAL_REPLICATE_BLOCK_SIZE,
    RNG_SCHEDULE_SCHEMA,
    ResamplingSchedule,
    RngScheduleDescriptor,
    formal_resampling_schedule,
    materialize_array,
    validate_resampling_schedule,
)
from ..backends.protocols import ArtifactPublisher
from ..contracts import (
    ActivationRequest,
    AxisRef,
    ResamplingScheduleRecord,
    canonical_hash,
)


class PPAMResamplingError(RuntimeError):
    """Raised when a pPAM schedule violates its activation request."""


def ppam_resample_axis(request: ActivationRequest) -> AxisRef:
    """Build the deterministic replicate axis for one pPAM request."""

    if not isinstance(request, ActivationRequest):
        raise PPAMResamplingError("activation request is invalid")
    return AxisRef(
        "ppam_permutation_replicates",
        request.permutation_resamples,
        canonical_hash(
            {
                "final_model_id": request.final_model.identifier,
                "resampling_kind": "permutation",
                "resamples": request.permutation_resamples,
                "seed": request.seed,
            }
        ),
    )


def publish_ppam_resampling_schedule(
    request: ActivationRequest,
    publisher: ArtifactPublisher,
) -> ResamplingScheduleRecord:
    """Generate and publish one complete historical pPAM schedule."""

    if not isinstance(request, ActivationRequest):
        raise PPAMResamplingError("activation request is invalid")
    schedule = formal_resampling_schedule(
        "permutation",
        request.subject_axis.count,
        request.permutation_resamples,
        request.seed,
    )
    replicate_axis = ppam_resample_axis(request)
    artifact = publisher.array(
        "ppam_resampling_schedule.npy",
        schedule.indices,
        kind="formal_resampling_schedule",
        axes=(replicate_axis, request.subject_axis),
        units="subject_index",
        space=None,
    )
    descriptor = schedule.descriptor
    return ResamplingScheduleRecord(
        target_id=request.final_model.identifier,
        resampling_kind="permutation",
        subject_axis=request.subject_axis,
        replicate_axis=replicate_axis,
        seed=request.seed,
        replicate_count=request.permutation_resamples,
        block_size=FORMAL_REPLICATE_BLOCK_SIZE,
        schedule_schema=descriptor.schema_version,
        generator_class=descriptor.generator_class,
        bit_generator_class=descriptor.bit_generator_class,
        numpy_version=descriptor.numpy_version,
        environment_fingerprint=descriptor.environment_fingerprint,
        schedule_sha256=descriptor.schedule_sha256,
        schedule=artifact,
    )


def load_ppam_resampling_schedule(
    record: ResamplingScheduleRecord,
    request: ActivationRequest,
    artifact_store: object,
) -> ResamplingSchedule:
    """Restore and fully validate one pPAM permutation schedule."""

    if not isinstance(record, ResamplingScheduleRecord):
        raise PPAMResamplingError("pPAM schedule record is invalid")
    if not isinstance(request, ActivationRequest):
        raise PPAMResamplingError("activation request is invalid")
    expected_axis = ppam_resample_axis(request)
    if (
        record.target_id != request.final_model.identifier
        or record.resampling_kind != "permutation"
        or record.subject_axis != request.subject_axis
        or record.replicate_axis != expected_axis
        or record.seed != request.seed
        or record.replicate_count != request.permutation_resamples
        or record.block_size != FORMAL_REPLICATE_BLOCK_SIZE
        or record.schedule_schema != RNG_SCHEDULE_SCHEMA
    ):
        raise PPAMResamplingError(
            "pPAM schedule record does not match the activation request"
        )
    indices = materialize_array(
        record.schedule,
        name="ppam_resampling_schedule",
        expected_axes=(record.replicate_axis, record.subject_axis),
        expected_units="subject_index",
        expected_space=None,
        artifact_store=artifact_store,
        memory_map=True,
    )
    descriptor = RngScheduleDescriptor(
        schema_version=record.schedule_schema,
        schedule_kind="permutation",
        seed=record.seed,
        subject_count=record.subject_axis.count,
        replicate_count=record.replicate_count,
        dtype=np.asarray(indices).dtype.name,
        generator_class=record.generator_class,
        bit_generator_class=record.bit_generator_class,
        numpy_version=record.numpy_version,
        environment_fingerprint=record.environment_fingerprint,
        schedule_sha256=record.schedule_sha256,
    )
    try:
        schedule = ResamplingSchedule(descriptor, np.asarray(indices))
        validate_resampling_schedule(
            schedule,
            schedule_kind="permutation",
            subject_count=request.subject_axis.count,
            replicate_count=request.permutation_resamples,
            seed=request.seed,
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise PPAMResamplingError(str(error)) from error
    return schedule


__all__ = [
    "PPAMResamplingError",
    "load_ppam_resampling_schedule",
    "ppam_resample_axis",
    "publish_ppam_resampling_schedule",
]
