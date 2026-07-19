"""Durable publication and restoration of pPAM permutation blocks."""

from __future__ import annotations

import numpy as np

from ..backends.formal.common import (
    PermutationBlockComputation,
    ReplicateBlock,
    materialize_array,
)
from ..backends.protocols import ArtifactPublisher
from ..contracts import (
    PPAMPermutationBlockRecord,
    ResamplingScheduleRecord,
    resampling_block_axis,
)


class PPAMPermutationBlockError(RuntimeError):
    """Raised when a pPAM null block violates its parent schedule contract."""


def publish_ppam_permutation_block(
    result: PermutationBlockComputation,
    schedule: ResamplingScheduleRecord,
    publisher: ArtifactPublisher,
) -> PPAMPermutationBlockRecord:
    """Publish one exact pPAM null-statistic interval and its typed record."""

    if not isinstance(result, PermutationBlockComputation):
        raise PPAMPermutationBlockError("pPAM permutation block result is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise PPAMPermutationBlockError("resampling schedule record is invalid")
    block = result.block
    if (
        schedule.resampling_kind != "permutation"
        or result.schedule_sha256 != schedule.schedule_sha256
        or block.total != schedule.replicate_count
    ):
        raise PPAMPermutationBlockError(
            "pPAM permutation block does not match its parent schedule"
        )
    block_axis = resampling_block_axis(
        schedule.replicate_axis,
        block.start,
        block.stop,
    )
    artifact = publisher.array(
        "ppam_permutation_null_statistics_block.npy",
        result.null_statistics,
        kind="ppam_permutation_null_statistics_block",
        axes=(block_axis,),
        units="loocv_spearman_rho",
        space=None,
    )
    finite_count = int(np.count_nonzero(np.isfinite(result.null_statistics)))
    return PPAMPermutationBlockRecord(
        target_id=schedule.target_id,
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


def load_ppam_permutation_block(
    record: PPAMPermutationBlockRecord,
    schedule: ResamplingScheduleRecord,
    artifact_store: object,
) -> PermutationBlockComputation:
    """Restore one pPAM block after validating its complete parent binding."""

    if not isinstance(record, PPAMPermutationBlockRecord):
        raise PPAMPermutationBlockError("pPAM permutation block record is invalid")
    if not isinstance(schedule, ResamplingScheduleRecord):
        raise PPAMPermutationBlockError("resampling schedule record is invalid")
    if (
        schedule.resampling_kind != "permutation"
        or record.target_id != schedule.target_id
        or record.schedule_id != schedule.identifier
        or record.replicate_axis != schedule.replicate_axis
        or record.total != schedule.replicate_count
        or record.schedule_sha256 != schedule.schedule_sha256
    ):
        raise PPAMPermutationBlockError(
            "pPAM permutation block record does not match its parent schedule"
        )
    block = ReplicateBlock(
        record.block_index,
        record.start,
        record.stop,
        record.total,
    )
    try:
        values = materialize_array(
            record.artifacts[0],
            name="ppam_permutation_null_statistics_block",
            expected_axes=(record.block_axis,),
            expected_units="loocv_spearman_rho",
            expected_space=None,
            artifact_store=artifact_store,
            memory_map=True,
        )
        return PermutationBlockComputation(
            block=block,
            schedule_sha256=record.schedule_sha256,
            null_statistics=np.asarray(values),
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise PPAMPermutationBlockError(str(error)) from error


__all__ = [
    "PPAMPermutationBlockError",
    "load_ppam_permutation_block",
    "publish_ppam_permutation_block",
]
