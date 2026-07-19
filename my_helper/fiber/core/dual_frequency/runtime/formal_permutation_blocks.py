"""Durable publication and restoration of formal permutation blocks."""

from __future__ import annotations

import numpy as np

from ..backends.formal.common import (
    PermutationBlockComputation,
    ReplicateBlock,
    materialize_array,
)
from ..backends.protocols import ArtifactPublisher
from ..contracts import (
    ResamplingBlockRecord,
    ResamplingScheduleRecord,
    resampling_block_axis,
)


class FormalPermutationBlockError(RuntimeError):
    """Raised when one block does not match its published parent schedule."""


def publish_formal_permutation_block(
    result: PermutationBlockComputation,
    schedule: ResamplingScheduleRecord,
    publisher: ArtifactPublisher,
) -> ResamplingBlockRecord:
    """Publish one exact null-statistic interval and its typed record."""

    if not isinstance(result, PermutationBlockComputation):
        raise FormalPermutationBlockError("permutation block result is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise FormalPermutationBlockError("resampling schedule record is invalid")
    block = result.block
    if (
        schedule.resampling_kind != "permutation"
        or result.schedule_sha256 != schedule.schedule_sha256
        or block.total != schedule.replicate_count
    ):
        raise FormalPermutationBlockError(
            "permutation block does not match its parent schedule"
        )
    block_axis = resampling_block_axis(
        schedule.replicate_axis,
        block.start,
        block.stop,
    )
    artifact = publisher.array(
        "formal_permutation_null_statistics_block.npy",
        result.null_statistics,
        kind="formal_permutation_null_statistics_block",
        axes=(block_axis,),
        units="spearman_rho",
        space=None,
    )
    finite_count = int(np.count_nonzero(np.isfinite(result.null_statistics)))
    return ResamplingBlockRecord(
        target_id=schedule.target_id,
        resampling_kind="permutation",
        schedule_id=schedule.identifier,
        replicate_axis=schedule.replicate_axis,
        block_axis=block_axis,
        block_index=block.index,
        start=block.start,
        stop=block.stop,
        total=block.total,
        schedule_sha256=schedule.schedule_sha256,
        technical_status=(
            "completed"
            if finite_count == block.count
            else "completed_with_nonfinite_replicates"
        ),
        artifacts=(artifact,),
    )


def load_formal_permutation_block(
    record: ResamplingBlockRecord,
    schedule: ResamplingScheduleRecord,
    artifact_store: object,
) -> PermutationBlockComputation:
    """Restore one block only after validating its complete parent binding."""

    if not isinstance(record, ResamplingBlockRecord):
        raise FormalPermutationBlockError("permutation block record is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise FormalPermutationBlockError("resampling schedule record is invalid")
    if (
        record.target_id != schedule.target_id
        or record.resampling_kind != schedule.resampling_kind
        or record.schedule_id != schedule.identifier
        or record.replicate_axis != schedule.replicate_axis
        or record.total != schedule.replicate_count
        or record.schedule_sha256 != schedule.schedule_sha256
    ):
        raise FormalPermutationBlockError(
            "permutation block record does not match its parent schedule"
        )
    block = ReplicateBlock(
        record.block_index,
        record.start,
        record.stop,
        record.total,
    )
    values = materialize_array(
        record.artifacts[0],
        name="formal_permutation_null_statistics_block",
        expected_axes=(record.block_axis,),
        expected_units="spearman_rho",
        expected_space=None,
        artifact_store=artifact_store,
        memory_map=True,
    )
    try:
        return PermutationBlockComputation(
            block=block,
            schedule_sha256=record.schedule_sha256,
            null_statistics=np.asarray(values),
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise FormalPermutationBlockError(str(error)) from error


__all__ = [
    "FormalPermutationBlockError",
    "load_formal_permutation_block",
    "publish_formal_permutation_block",
]
