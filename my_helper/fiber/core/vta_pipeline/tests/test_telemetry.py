from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from my_helper.fiber.core.vta_pipeline.errors import (
    EventProtocolError,
    MatlabProcessError,
)
from my_helper.fiber.core.vta_pipeline.telemetry import (
    EVENT_PREFIX,
    EventStreamParser,
)


def event(sequence: int, event_type: str, **fields: object) -> dict[str, object]:
    return {
        "schema_version": "vta_event_v1",
        "event_type": event_type,
        "sequence": sequence,
        "run_id": "run",
        "subject_id": "SNr003",
        **fields,
    }


def feed(parser: EventStreamParser, payload: dict[str, object]) -> None:
    assert parser.feed_line(
        EVENT_PREFIX + json.dumps(payload, separators=(",", ":"))
    ) is None


def summary(sequence: int, **overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "generated": 1,
        "copied": 0,
        "skipped_existing": 0,
        "recovered_complete": 0,
        "failed": 0,
        "skipped_dependency": 0,
        "process_success": True,
    }
    fields.update(overrides)
    return event(sequence, "subject_summary", **fields)


def feed_complete_one_task_protocol(parser: EventStreamParser) -> None:
    for payload in (
        event(
            1,
            "stage_timing",
            scope="subject",
            stage="manifest_decode_validation",
            stage_status="executed",
            duration_seconds=0.1,
        ),
        event(2, "subject_ready"),
        event(3, "task_started", task_id="task-1"),
        event(
            4,
            "stage_timing",
            scope="task",
            task_id="task-1",
            stage="fem_pcg_solve",
            stage_status="executed",
            cache_status="miss",
            duration_seconds=0.2,
        ),
        event(
            5,
            "task_outcome",
            task_id="task-1",
            status="generated",
            copied_artifact_count=0,
            generated_artifact_count=8,
        ),
        summary(6),
    ):
        feed(parser, payload)


def test_accepts_complete_one_task_protocol() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))

    feed_complete_one_task_protocol(parser)
    result = parser.finish(returncode=0)

    assert result.run_id == "run"
    assert result.subject_id == "SNr003"
    assert result.returncode == 0
    assert result.protocol_complete
    assert result.outcomes[0].status == "generated"
    assert result.outcomes[0].generated_artifact_count == 8
    assert result.timings[0].task_id is None
    assert result.timings[1].cache_status == "miss"
    with pytest.raises(FrozenInstanceError):
        result.protocol_complete = False


def test_ignores_unprefixed_diagnostic_lines() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))

    assert parser.feed_line("MATLAB diagnostic output\n") is None
    feed_complete_one_task_protocol(parser)

    assert parser.finish(returncode=0).protocol_complete


def test_rejects_malformed_prefixed_json() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))

    with pytest.raises(EventProtocolError, match="JSON"):
        parser.feed_line(EVENT_PREFIX + "{not-json}")


def test_partial_snapshot_preserves_completed_outcomes() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1", "task-2"))
    feed(parser, event(1, "subject_ready"))
    feed(parser, event(2, "task_started", task_id="task-1"))
    feed(
        parser,
        event(
            3,
            "task_outcome",
            task_id="task-1",
            status="generated",
            copied_artifact_count=0,
            generated_artifact_count=8,
        ),
    )
    feed(parser, event(4, "task_started", task_id="task-2"))

    snapshot = parser.snapshot(-1)

    assert snapshot.protocol_complete is False
    assert snapshot.returncode == -1
    assert [outcome.task_id for outcome in snapshot.outcomes] == ["task-1"]


def test_rejects_sequence_gap() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="sequence"):
        feed(parser, event(3, "task_started", task_id="task-1"))


@pytest.mark.parametrize(
    ("field", "value"),
    (("run_id", "other-run"), ("subject_id", "SNr006")),
)
def test_rejects_wrong_stream_identity(field: str, value: str) -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    payload = event(1, "subject_ready")
    payload[field] = value

    with pytest.raises(EventProtocolError, match=field):
        feed(parser, payload)


def test_rejects_wrong_task_id() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="task_id"):
        feed(parser, event(2, "task_started", task_id="unknown-task"))


def test_rejects_task_started_out_of_manifest_order() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1", "task-2"))
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="order"):
        feed(parser, event(2, "task_started", task_id="task-2"))


def test_rejects_timing_after_summary() -> None:
    parser = EventStreamParser("run", "SNr003", ())
    feed(parser, event(1, "subject_ready"))
    feed(parser, summary(2, generated=0))

    with pytest.raises(EventProtocolError, match="summary"):
        feed(
            parser,
            event(
                3,
                "stage_timing",
                scope="subject",
                stage="path_initialization",
                stage_status="executed",
                duration_seconds=0.1,
            ),
        )


def test_rejects_task_timing_without_active_task() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="active task"):
        feed(
            parser,
            event(
                2,
                "stage_timing",
                scope="task",
                task_id="task-1",
                stage="task_runtime_resolution",
                stage_status="executed",
                duration_seconds=0.1,
            ),
        )


def test_rejects_outcome_without_start() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="active task"):
        feed(
            parser,
            event(
                2,
                "task_outcome",
                task_id="task-1",
                status="generated",
                copied_artifact_count=0,
                generated_artifact_count=8,
            ),
        )


def test_rejects_two_active_tasks() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1", "task-2"))
    feed(parser, event(1, "subject_ready"))
    feed(parser, event(2, "task_started", task_id="task-1"))

    with pytest.raises(EventProtocolError, match="active task"):
        feed(parser, event(3, "task_started", task_id="task-2"))


def test_rejects_summary_count_mismatch() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))
    feed(parser, event(2, "task_started", task_id="task-1"))
    feed(
        parser,
        event(
            3,
            "task_outcome",
            task_id="task-1",
            status="generated",
            copied_artifact_count=0,
            generated_artifact_count=8,
        ),
    )

    with pytest.raises(EventProtocolError, match="summary"):
        feed(parser, summary(4, generated=0, copied=1))


def test_rejects_summary_success_inconsistent_with_failed_outcome() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed(parser, event(1, "subject_ready"))
    feed(parser, event(2, "task_started", task_id="task-1"))
    feed(
        parser,
        event(
            3,
            "task_outcome",
            task_id="task-1",
            status="failed",
            copied_artifact_count=0,
            generated_artifact_count=0,
        ),
    )

    with pytest.raises(EventProtocolError, match="process_success"):
        feed(parser, summary(4, generated=0, failed=1, process_success=True))


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("stage_status", "unknown", "stage_status"),
        ("cache_status", "stale", "cache_status"),
    ),
)
def test_rejects_invalid_stage_metadata(
    field: str,
    value: str,
    match: str,
) -> None:
    parser = EventStreamParser("run", "SNr003", ())
    payload = event(
        1,
        "stage_timing",
        scope="subject",
        stage="manifest_decode_validation",
        stage_status="executed",
        duration_seconds=0.1,
    )
    payload[field] = value

    with pytest.raises(EventProtocolError, match=match):
        feed(parser, payload)


@pytest.mark.parametrize(
    ("extra", "match"),
    (
        ({"duration_seconds": 0.1}, "zero duration"),
        ({"cache_status": "hit"}, "cache_status"),
    ),
)
def test_rejects_inconsistent_not_applicable_timing(
    extra: dict[str, object],
    match: str,
) -> None:
    parser = EventStreamParser("run", "SNr003", ())
    fields: dict[str, object] = {
        "scope": "subject",
        "stage": "path_initialization",
        "stage_status": "not_applicable",
        "duration_seconds": 0.0,
    }
    fields.update(extra)
    payload = event(1, "stage_timing", **fields)

    with pytest.raises(EventProtocolError, match=match):
        feed(parser, payload)


def test_rejects_missing_summary() -> None:
    parser = EventStreamParser("run", "SNr003", ())
    feed(parser, event(1, "subject_ready"))

    with pytest.raises(EventProtocolError, match="summary"):
        parser.finish(returncode=0)


def test_rejects_exit_zero_with_incomplete_protocol() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))

    with pytest.raises(EventProtocolError, match="incomplete"):
        parser.finish(returncode=0)


def test_validates_protocol_before_nonzero_process_exit() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))

    with pytest.raises(EventProtocolError):
        parser.finish(returncode=1)


def test_raises_process_error_after_valid_nonzero_process_exit() -> None:
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    feed_complete_one_task_protocol(parser)

    with pytest.raises(MatlabProcessError, match="1"):
        parser.finish(returncode=1)
