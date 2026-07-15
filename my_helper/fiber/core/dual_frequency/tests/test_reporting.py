"""Record-only reporting primitives for generic dual-frequency runs."""

from __future__ import annotations

import json
import unittest

from dual_frequency.contracts import ArtifactRef, AxisRef
from dual_frequency.reporting import ArtifactIndexError, build_artifact_index
from dual_frequency.workflow import RunResult, ServiceResult, TaskOutcome


def _artifact(kind: str, digest: str) -> ArtifactRef:
    axis = AxisRef("subjects", 3, "a" * 64)
    return ArtifactRef(
        kind=kind,
        schema_version="synthetic_v1",
        uri=f"memory://current-run/{kind}",
        sha256=digest,
        dtype="float32",
        shape=(3,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="score",
        space=None,
        producer_id="synthetic_service",
        producer_version="1",
    )


def _completed(
    task_id: str,
    endpoint_id: str,
    artifact: ArtifactRef,
) -> TaskOutcome:
    return TaskOutcome(
        task_id=task_id,
        endpoint_id=endpoint_id,
        service_id=f"service_{task_id}",
        status="completed",
        reason="none",
        result=ServiceResult.create(
            "ObservedResult",
            f"record_{task_id}",
            {"status": "completed"},
            artifacts=(artifact,),
        ),
    )


def _terminal(task_id: str, endpoint_id: str, status: str) -> TaskOutcome:
    return TaskOutcome(
        task_id=task_id,
        endpoint_id=endpoint_id,
        service_id=f"service_{task_id}",
        status=status,
        reason="synthetic_terminal_state",
        result=None,
    )


class ArtifactIndexTest(unittest.TestCase):
    def test_index_is_deterministic_record_only_and_groups_task_references(self) -> None:
        shared = _artifact("observed_scores", "b" * 64)
        unique = _artifact("observed_weights", "c" * 64)
        outcomes = (
            _completed("task_b", "endpoint_2", shared),
            _terminal("task_failed", "endpoint_3", "failed"),
            _completed("task_a", "endpoint_1", shared),
            _completed("task_c", "endpoint_1", unique),
            _terminal("task_skipped", "endpoint_4", "skipped"),
        )
        forward = build_artifact_index(RunResult("run_1", outcomes, exit_code=1))
        reverse = build_artifact_index(
            RunResult("run_1", tuple(reversed(outcomes)), exit_code=1)
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(forward["schema_version"], "dual_frequency_artifact_index_v2")
        self.assertEqual(forward["run_id"], "run_1")
        self.assertEqual(len(forward["artifacts"]), 2)
        by_kind = {item["kind"]: item for item in forward["artifacts"]}
        self.assertEqual(
            [item["task_id"] for item in by_kind["observed_scores"]["task_references"]],
            ["task_a", "task_b"],
        )
        self.assertEqual(
            by_kind["observed_weights"]["task_references"][0]["endpoint_id"],
            "endpoint_1",
        )
        serialized = json.dumps(forward, sort_keys=True, allow_nan=False)
        self.assertNotIn("legacy", serialized.lower())
        self.assertNotIn("summary/spot", serialized.lower())

    def test_duplicate_task_outcome_is_rejected(self) -> None:
        artifact = _artifact("scores", "d" * 64)
        outcome = _completed("task_a", "endpoint_1", artifact)
        with self.assertRaisesRegex(ArtifactIndexError, "duplicate task outcome"):
            build_artifact_index(RunResult("run_1", (outcome, outcome), exit_code=0))

    def test_requires_a_typed_run_result(self) -> None:
        with self.assertRaisesRegex(TypeError, "RunResult"):
            build_artifact_index({})


if __name__ == "__main__":
    unittest.main()
