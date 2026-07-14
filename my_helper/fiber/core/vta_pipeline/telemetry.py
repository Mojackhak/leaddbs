"""Parse framed telemetry emitted by canonical VTA MATLAB processes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from typing import Any

from .errors import EventProtocolError, MatlabProcessError


EVENT_PREFIX = "MH_VTA_EVENT "
STAGE_STATUSES = frozenset({"executed", "not_applicable"})
CACHE_STATUSES = frozenset({"hit", "miss"})
TASK_OUTCOME_STATUSES = frozenset(
    {
        "generated",
        "copied",
        "skipped_existing",
        "recovered_complete",
        "failed",
        "skipped_dependency",
    }
)
STAGE_NAMES = frozenset(
    {
        "path_initialization",
        "manifest_decode_validation",
        "task_runtime_resolution",
        "subject_reconstruction_context",
        "headmodel_build_or_load",
        "active_contact_boundary",
        "fem_matrix_preparation",
        "fem_preconditioner",
        "fem_pcg_solve",
        "gradient_calculation",
        "electrode_removal_geometry",
        "native_grid_interpolation",
        "group_peak_composition",
        "threshold_generation",
        "native_to_mni_transform",
        "artifact_publication",
    }
)
EVENT_TYPES = frozenset(
    {
        "subject_ready",
        "task_started",
        "stage_timing",
        "task_outcome",
        "subject_summary",
    }
)


@dataclass(frozen=True)
class StageTiming:
    scope: str
    task_id: str | None
    stage: str
    stage_status: str
    cache_status: str | None
    duration_seconds: float


@dataclass(frozen=True)
class TaskOutcome:
    task_id: str
    status: str
    copied_artifact_count: int
    generated_artifact_count: int
    error_identifier: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ProcessObservation:
    run_id: str
    subject_id: str
    outcomes: tuple[TaskOutcome, ...]
    timings: tuple[StageTiming, ...]
    protocol_complete: bool
    returncode: int


class EventStreamParser:
    """Validate one ordered ``vta_event_v1`` process event stream."""

    def __init__(
        self,
        run_id: str,
        subject_id: str,
        task_ids: tuple[str, ...],
    ) -> None:
        self._run_id = run_id
        self._subject_id = subject_id
        self._task_ids = tuple(task_ids)
        self._next_sequence = 1
        self._next_task_index = 0
        self._active_task_id: str | None = None
        self._ready_seen = False
        self._summary_seen = False
        self._event_count = 0
        self._outcomes: list[TaskOutcome] = []
        self._timings: list[StageTiming] = []

    def feed_line(self, line: str) -> None:
        """Consume one stdout line, ignoring unframed diagnostic output."""

        if not line.startswith(EVENT_PREFIX):
            return None

        payload_text = line[len(EVENT_PREFIX) :]
        try:
            payload = json.loads(payload_text)
        except (json.JSONDecodeError, TypeError) as error:
            raise EventProtocolError(
                f"Malformed vta_event_v1 JSON: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise EventProtocolError("Framed vta_event_v1 JSON must be an object")

        self._validate_common_fields(payload)
        if self._summary_seen:
            raise EventProtocolError("No event may follow subject_summary")

        event_type = payload["event_type"]
        if event_type == "subject_ready":
            self._accept_subject_ready()
        elif event_type == "task_started":
            self._accept_task_started(payload)
        elif event_type == "stage_timing":
            self._accept_stage_timing(payload)
        elif event_type == "task_outcome":
            self._accept_task_outcome(payload)
        else:
            self._accept_subject_summary(payload)

        self._next_sequence += 1
        self._event_count += 1
        return None

    def finish(self, returncode: int) -> ProcessObservation:
        """Validate stream completion and return its immutable observation."""

        if self._event_count == 0:
            raise EventProtocolError("incomplete event protocol: no framed events")
        if not self._ready_seen:
            raise EventProtocolError(
                "incomplete event protocol: missing subject_ready"
            )
        if self._active_task_id is not None:
            raise EventProtocolError(
                f"incomplete event protocol: active task {self._active_task_id!r}"
            )
        if self._next_task_index != len(self._task_ids):
            raise EventProtocolError(
                "incomplete event protocol: not all expected tasks completed"
            )
        if not self._summary_seen:
            raise EventProtocolError("Missing subject_summary event")
        if returncode != 0:
            raise MatlabProcessError(
                f"MATLAB process exited unsuccessfully with return code {returncode}"
            )

        return ProcessObservation(
            run_id=self._run_id,
            subject_id=self._subject_id,
            outcomes=tuple(self._outcomes),
            timings=tuple(self._timings),
            protocol_complete=True,
            returncode=returncode,
        )

    def snapshot(self, returncode: int) -> ProcessObservation:
        """Return completed outcomes parsed before an interrupted protocol."""

        return ProcessObservation(
            run_id=self._run_id,
            subject_id=self._subject_id,
            outcomes=tuple(self._outcomes),
            timings=tuple(self._timings),
            protocol_complete=False,
            returncode=returncode,
        )

    def _validate_common_fields(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != "vta_event_v1":
            raise EventProtocolError("Invalid schema_version for framed telemetry")

        event_type = payload.get("event_type")
        if event_type not in EVENT_TYPES:
            raise EventProtocolError(f"Unsupported event_type: {event_type!r}")

        sequence = payload.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence != self._next_sequence
        ):
            raise EventProtocolError(
                f"Expected sequence {self._next_sequence}, received {sequence!r}"
            )
        if payload.get("run_id") != self._run_id:
            raise EventProtocolError(
                f"Unexpected run_id: {payload.get('run_id')!r}"
            )
        if payload.get("subject_id") != self._subject_id:
            raise EventProtocolError(
                f"Unexpected subject_id: {payload.get('subject_id')!r}"
            )

    def _accept_subject_ready(self) -> None:
        if self._ready_seen:
            raise EventProtocolError("subject_ready must be emitted exactly once")
        if self._active_task_id is not None or self._outcomes:
            raise EventProtocolError("subject_ready must precede all task events")
        self._ready_seen = True

    def _accept_task_started(self, payload: dict[str, Any]) -> None:
        if not self._ready_seen:
            raise EventProtocolError("task_started must follow subject_ready")
        if self._active_task_id is not None:
            raise EventProtocolError(
                f"Cannot start a second task while active task "
                f"{self._active_task_id!r} is unfinished"
            )

        task_id = self._require_string(payload, "task_id")
        if task_id not in self._task_ids:
            raise EventProtocolError(f"Unknown task_id: {task_id!r}")
        if self._next_task_index >= len(self._task_ids):
            raise EventProtocolError(f"Unexpected extra task_id: {task_id!r}")
        expected_task_id = self._task_ids[self._next_task_index]
        if task_id != expected_task_id:
            raise EventProtocolError(
                f"Task order violation: expected {expected_task_id!r}, "
                f"received {task_id!r}"
            )
        self._active_task_id = task_id

    def _accept_stage_timing(self, payload: dict[str, Any]) -> None:
        scope = self._require_string(payload, "scope")
        if scope not in {"subject", "task"}:
            raise EventProtocolError(f"Invalid timing scope: {scope!r}")

        raw_task_id = payload.get("task_id")
        if scope == "subject":
            if self._ready_seen:
                raise EventProtocolError(
                    "Subject timing must be emitted before subject_ready"
                )
            if raw_task_id is not None:
                raise EventProtocolError("Subject timing cannot include task_id")
            task_id = None
        else:
            if self._active_task_id is None:
                raise EventProtocolError("Task timing requires an active task")
            task_id = self._require_string(payload, "task_id")
            if task_id != self._active_task_id:
                raise EventProtocolError(
                    f"Task timing task_id {task_id!r} does not match active task "
                    f"{self._active_task_id!r}"
                )

        stage = self._require_string(payload, "stage")
        if stage not in STAGE_NAMES:
            raise EventProtocolError(f"Unknown timing stage: {stage!r}")
        stage_status = self._require_string(payload, "stage_status")
        if stage_status not in STAGE_STATUSES:
            raise EventProtocolError(
                f"Invalid stage_status: {stage_status!r}"
            )
        cache_status = self._optional_string(payload, "cache_status")
        if cache_status is not None and cache_status not in CACHE_STATUSES:
            raise EventProtocolError(
                f"Invalid cache_status: {cache_status!r}"
            )
        duration_seconds = self._require_duration(payload)
        if stage_status == "not_applicable":
            if cache_status is not None:
                raise EventProtocolError(
                    "not_applicable stage cannot include cache_status"
                )
            if duration_seconds != 0:
                raise EventProtocolError(
                    "not_applicable stage must have zero duration"
                )
        self._timings.append(
            StageTiming(
                scope=scope,
                task_id=task_id,
                stage=stage,
                stage_status=stage_status,
                cache_status=cache_status,
                duration_seconds=duration_seconds,
            )
        )

    def _accept_task_outcome(self, payload: dict[str, Any]) -> None:
        if self._active_task_id is None:
            raise EventProtocolError("task_outcome requires an active task")
        task_id = self._require_string(payload, "task_id")
        if task_id != self._active_task_id:
            raise EventProtocolError(
                f"Outcome task_id {task_id!r} does not match active task "
                f"{self._active_task_id!r}"
            )

        status = self._require_string(payload, "status")
        if status not in TASK_OUTCOME_STATUSES:
            raise EventProtocolError(f"Invalid task outcome status: {status!r}")
        outcome = TaskOutcome(
            task_id=task_id,
            status=status,
            copied_artifact_count=self._require_nonnegative_int(
                payload, "copied_artifact_count"
            ),
            generated_artifact_count=self._require_nonnegative_int(
                payload, "generated_artifact_count"
            ),
            error_identifier=self._optional_string(payload, "error_identifier"),
            error_message=self._optional_string(payload, "error_message"),
        )
        self._outcomes.append(outcome)
        self._active_task_id = None
        self._next_task_index += 1

    def _accept_subject_summary(self, payload: dict[str, Any]) -> None:
        if not self._ready_seen:
            raise EventProtocolError("subject_summary must follow subject_ready")
        if self._active_task_id is not None:
            raise EventProtocolError(
                "subject_summary cannot be emitted while a task is active"
            )
        if self._next_task_index != len(self._task_ids):
            raise EventProtocolError(
                "subject_summary cannot precede all expected task outcomes"
            )

        outcome_counts = Counter(outcome.status for outcome in self._outcomes)
        for status in TASK_OUTCOME_STATUSES:
            summary_count = self._require_nonnegative_int(payload, status)
            if summary_count != outcome_counts[status]:
                raise EventProtocolError(
                    f"subject_summary count mismatch for {status!r}: "
                    f"expected {outcome_counts[status]}, received {summary_count}"
                )
        process_success = payload.get("process_success")
        if not isinstance(process_success, bool):
            raise EventProtocolError(
                "subject_summary process_success must be a boolean"
            )
        expected_success = (
            outcome_counts["failed"] == 0
            and outcome_counts["skipped_dependency"] == 0
        )
        if process_success != expected_success:
            raise EventProtocolError(
                "subject_summary process_success does not match task outcomes"
            )
        self._summary_seen = True

    @staticmethod
    def _require_string(payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise EventProtocolError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(payload: dict[str, Any], field: str) -> str | None:
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            raise EventProtocolError(f"{field} must be null or a non-empty string")
        return value

    @staticmethod
    def _require_nonnegative_int(payload: dict[str, Any], field: str) -> int:
        value = payload.get(field)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise EventProtocolError(f"{field} must be a nonnegative integer")
        return value

    @staticmethod
    def _require_duration(payload: dict[str, Any]) -> float:
        value = payload.get("duration_seconds")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise EventProtocolError(
                "duration_seconds must be a finite nonnegative number"
            )
        return float(value)
