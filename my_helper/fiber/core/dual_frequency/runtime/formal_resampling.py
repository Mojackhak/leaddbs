"""Typed publication and restoration of complete formal RNG schedules."""

from __future__ import annotations

import numpy as np

from ..backends.formal.common import (
    FORMAL_REPLICATE_BLOCK_SIZE,
    RNG_SCHEDULE_SCHEMA,
    ResamplingSchedule,
    RngScheduleDescriptor,
    formal_resampling_schedule,
    materialize_array,
    resample_axis,
    validate_resampling_schedule,
)
from ..backends.protocols import ArtifactPublisher
from ..contracts import FormalRequest, ResamplingScheduleRecord


class FormalResamplingError(RuntimeError):
    """Raised when a durable schedule does not match its formal request."""


def publish_formal_resampling_schedule(
    request: FormalRequest,
    publisher: ArtifactPublisher,
) -> ResamplingScheduleRecord:
    """Generate and publish one complete historical formal schedule."""

    if not isinstance(request, FormalRequest):
        raise FormalResamplingError("formal request is invalid")
    schedule = formal_resampling_schedule(
        request.resampling_kind,
        request.subject_axis.count,
        request.resamples,
        request.seed,
    )
    replicate_axis = resample_axis(request)
    artifact = publisher.array(
        "formal_resampling_schedule.npy",
        schedule.indices,
        kind="formal_resampling_schedule",
        axes=(replicate_axis, request.subject_axis),
        units="subject_index",
        space=None,
    )
    descriptor = schedule.descriptor
    return ResamplingScheduleRecord(
        target_id=request.final_model.identifier,
        resampling_kind=request.resampling_kind,
        subject_axis=request.subject_axis,
        replicate_axis=replicate_axis,
        seed=request.seed,
        replicate_count=request.resamples,
        block_size=FORMAL_REPLICATE_BLOCK_SIZE,
        schedule_schema=descriptor.schema_version,
        generator_class=descriptor.generator_class,
        bit_generator_class=descriptor.bit_generator_class,
        numpy_version=descriptor.numpy_version,
        environment_fingerprint=descriptor.environment_fingerprint,
        schedule_sha256=descriptor.schedule_sha256,
        schedule=artifact,
    )


def load_formal_resampling_schedule(
    record: ResamplingScheduleRecord,
    request: FormalRequest,
    artifact_store: object,
) -> ResamplingSchedule:
    """Restore and fully validate one immutable parent-pregenerated schedule."""

    if not isinstance(record, ResamplingScheduleRecord):
        raise FormalResamplingError("resampling schedule record is invalid")
    if not isinstance(request, FormalRequest):
        raise FormalResamplingError("formal request is invalid")
    expected_axis = resample_axis(request)
    if (
        record.target_id != request.final_model.identifier
        or record.resampling_kind != request.resampling_kind
        or record.subject_axis != request.subject_axis
        or record.replicate_axis != expected_axis
        or record.seed != request.seed
        or record.replicate_count != request.resamples
        or record.block_size != FORMAL_REPLICATE_BLOCK_SIZE
        or record.schedule_schema != RNG_SCHEDULE_SCHEMA
    ):
        raise FormalResamplingError(
            "resampling schedule record does not match the formal request"
        )
    indices = materialize_array(
        record.schedule,
        name="formal_resampling_schedule",
        expected_axes=(record.replicate_axis, record.subject_axis),
        expected_units="subject_index",
        expected_space=None,
        artifact_store=artifact_store,
        memory_map=True,
    )
    descriptor = RngScheduleDescriptor(
        schema_version=record.schedule_schema,
        schedule_kind=record.resampling_kind,
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
            schedule_kind=request.resampling_kind,
            subject_count=request.subject_axis.count,
            replicate_count=request.resamples,
            seed=request.seed,
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise FormalResamplingError(str(error)) from error
    return schedule


__all__ = [
    "FormalResamplingError",
    "load_formal_resampling_schedule",
    "publish_formal_resampling_schedule",
]
