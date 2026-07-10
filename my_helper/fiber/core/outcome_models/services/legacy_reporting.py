"""Configured final-record reporting adapter with no legacy discovery."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..executor import TaskArtifact
from ..records import ArtifactRef, RecordError
from .reporting import ReportingRequest


FDR_ARTIFACT_KINDS = frozenset({"fdr_cache", "fdr_results", "fiber_fdr_results"})
DENSITY_ARTIFACT_KINDS = frozenset(
    {"density_cache", "density_results", "fiber_density_results"}
)
LABEL_ARTIFACT_KINDS = frozenset(
    {"label_cache", "label_results", "fiber_label_results"}
)


@dataclass(frozen=True)
class ConfiguredReportingOutput:
    artifacts: tuple[TaskArtifact, ...]
    facts: Mapping[str, Any]
    detail: str = "configured_endpoint_reporting_completed"


@dataclass
class _NumericAccumulator:
    count: int = 0
    total: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf

    def add(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self.count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def as_metric(self, name: str) -> dict[str, str]:
        return {
            "metric_name": name,
            "metric_status": "reported_numeric_summary",
            "numeric_count": str(self.count),
            "numeric_value": _number(self.minimum) if self.count == 1 else "",
            "numeric_min": _number(self.minimum),
            "numeric_max": _number(self.maximum),
            "numeric_mean": _number(self.total / self.count),
        }


def _number(value: float) -> str:
    return format(float(value), ".17g")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_root(request: ReportingRequest) -> Path:
    output_root = Path(request.output_root).expanduser().resolve()
    try:
        run_root = output_root.parents[3]
    except IndexError as exc:
        raise RecordError("reporting output_root does not follow the configured run layout") from exc
    if output_root.parent.name != "tasks" or output_root.parents[2].name != "models":
        raise RecordError("reporting output_root must be run_root/models/endpoint/tasks/task")
    return run_root


def _artifact_path(run_root: Path, artifact: ArtifactRef) -> Path:
    path = (run_root / artifact.relative_path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError(f"reporting artifact escapes run root: {artifact.relative_path}") from exc
    if not path.is_file():
        raise RecordError(f"reporting artifact is missing: {path}")
    if _sha256(path) != artifact.sha256:
        raise RecordError(f"reporting artifact SHA-256 mismatch: {path}")
    return path


def _parse_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _csv_metrics(path: Path) -> list[dict[str, str]]:
    accumulators: dict[str, _NumericAccumulator] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for name, raw_value in row.items():
                parsed = _parse_number(raw_value)
                if parsed is None:
                    continue
                accumulators.setdefault(str(name), _NumericAccumulator()).add(parsed)
    return [accumulators[name].as_metric(name) for name in sorted(accumulators)]


def _flatten_json_numbers(value: object, prefix: str = "") -> Iterable[tuple[str, float]]:
    parsed = _parse_number(value)
    if parsed is not None:
        yield prefix or "value", parsed
        return
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_json_numbers(value[key], child)
    elif isinstance(value, list):
        child = f"{prefix}[]" if prefix else "[]"
        for item in value:
            yield from _flatten_json_numbers(item, child)


def _json_metrics(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read reporting JSON artifact {path}: {exc}") from exc
    accumulators: dict[str, _NumericAccumulator] = {}
    for name, value in _flatten_json_numbers(payload):
        accumulators.setdefault(name, _NumericAccumulator()).add(value)
    return [accumulators[name].as_metric(name) for name in sorted(accumulators)]


def _numeric_metrics(path: Path, *, enabled: bool) -> list[dict[str, str]]:
    if not enabled:
        return []
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _csv_metrics(path)
    if suffix == ".json":
        return _json_metrics(path)
    return []


def _optional_status(enabled: bool, kinds: set[str], accepted: frozenset[str]) -> str:
    if not enabled:
        return "disabled_by_profile"
    if kinds & accepted:
        return "available_explicit_artifact"
    return "missing_optional_artifact"


def _identity(request: ReportingRequest) -> dict[str, str]:
    final = request.final
    endpoint = request.task.endpoint
    final_values = (
        {
            "final_model_id": final.final_model_id,
            "final_record_hash": final.record_hash,
            "final_branch": final.final_branch,
            "final_role": final.final_role,
            "selected_tau": _number(final.selected_tau),
            "selected_coverage": str(final.selected_coverage),
            "estimator": final.estimator,
            "scale_direction": final.scale_direction,
            "n_subjects": str(len(final.subject_order)),
            "n_features": str(final.feature_axis.count),
            "nuisance_columns": json.dumps(
                list(final.nuisance.columns),
                separators=(",", ":"),
            ),
        }
        if final is not None
        else {
            "final_model_id": "",
            "final_record_hash": "",
            "final_branch": "",
            "final_role": "",
            "selected_tau": "",
            "selected_coverage": "",
            "estimator": "",
            "scale_direction": "",
            "n_subjects": "",
            "n_features": "",
            "nuisance_columns": "[]",
        }
    )
    return {
        "endpoint_model_id": endpoint.identifier,
        "study_id": endpoint.study_id,
        "scale_id": endpoint.scale_id,
        "model_family": endpoint.model_family,
        "endpoint_phase": endpoint.endpoint_phase,
        "connectome": endpoint.connectome,
        "endpoint_terminal_status": request.endpoint_terminal_status,
        "endpoint_terminal_detail": request.endpoint_terminal_detail,
        **final_values,
    }


def _write_csv_atomic(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


_IDENTITY_FIELDS = (
    "endpoint_model_id",
    "study_id",
    "scale_id",
    "model_family",
    "endpoint_phase",
    "connectome",
    "endpoint_terminal_status",
    "endpoint_terminal_detail",
    "final_model_id",
    "final_record_hash",
    "final_branch",
    "final_role",
    "selected_tau",
    "selected_coverage",
    "estimator",
    "scale_direction",
    "n_subjects",
    "n_features",
    "nuisance_columns",
)

_OPTIONAL_FIELDS = (
    "fdr_status",
    "density_status",
    "labels_status",
)

_METRIC_FIELDS = (
    "source_task_id",
    "source_artifact_kind",
    "source_artifact_path",
    "source_artifact_sha256",
    "metric_name",
    "metric_status",
    "numeric_count",
    "numeric_value",
    "numeric_min",
    "numeric_max",
    "numeric_mean",
)


def _validated_inputs(
    request: ReportingRequest,
    run_root: Path,
) -> list[tuple[ArtifactRef, Path]]:
    inputs: list[tuple[ArtifactRef, Path]] = []
    seen: set[tuple[str, str]] = set()
    for linked in request.artifacts:
        artifact = linked.artifact
        key = (artifact.kind, artifact.relative_path)
        if key in seen:
            raise RecordError(f"duplicate reporting artifact: {artifact.kind}:{artifact.relative_path}")
        seen.add(key)
        inputs.append((artifact, _artifact_path(run_root, artifact)))
    return inputs


def _metric_rows(
    request: ReportingRequest,
    inputs: list[tuple[ArtifactRef, Path]],
    statuses: dict[str, str],
) -> list[dict[str, str]]:
    identity = _identity(request)
    rows: list[dict[str, str]] = []
    for artifact, path in inputs:
        metrics = _numeric_metrics(path, enabled=request.numeric_first)
        if not metrics:
            metrics = [
                {
                    "metric_name": "",
                    "metric_status": (
                        "no_scalar_numeric_metrics"
                        if request.numeric_first
                        else "numeric_reporting_disabled"
                    ),
                    "numeric_count": "0",
                    "numeric_value": "",
                    "numeric_min": "",
                    "numeric_max": "",
                    "numeric_mean": "",
                }
            ]
        for metric in metrics:
            rows.append(
                {
                    **identity,
                    **statuses,
                    "source_task_id": artifact.task_id,
                    "source_artifact_kind": artifact.kind,
                    "source_artifact_path": artifact.relative_path,
                    "source_artifact_sha256": artifact.sha256,
                    **metric,
                }
            )
    if not rows:
        rows.append(
            {
                **identity,
                **statuses,
                "source_task_id": "",
                "source_artifact_kind": "",
                "source_artifact_path": "",
                "source_artifact_sha256": "",
                "metric_name": "",
                "metric_status": "no_linked_reporting_artifacts",
                "numeric_count": "0",
                "numeric_value": "",
                "numeric_min": "",
                "numeric_max": "",
                "numeric_mean": "",
            }
        )
    return rows


def _summary_row(
    request: ReportingRequest,
    inputs: list[tuple[ArtifactRef, Path]],
    statuses: dict[str, str],
) -> dict[str, str]:
    metrics = sum(
        len(_numeric_metrics(path, enabled=request.numeric_first))
        for _, path in inputs
    )
    return {
        **_identity(request),
        **statuses,
        "numeric_reporting_status": (
            "complete_numeric_first" if request.numeric_first else "disabled_by_profile"
        ),
        "linked_artifact_count": str(len(inputs)),
        "numeric_metric_count": str(metrics),
    }


def _artifact_index_rows(
    request: ReportingRequest,
    inputs: list[tuple[ArtifactRef, Path]],
    report_path: Path,
    run_root: Path,
) -> list[dict[str, str]]:
    final = request.final
    identity = {
        "endpoint_model_id": request.task.endpoint.identifier,
        "endpoint_terminal_status": request.endpoint_terminal_status,
        "endpoint_terminal_detail": request.endpoint_terminal_detail,
        "final_model_id": final.final_model_id if final is not None else "",
        "final_record_hash": final.record_hash if final is not None else "",
    }
    rows = [
        {
            **identity,
            "artifact_role": "input",
            "artifact_kind": artifact.kind,
            "artifact_path": artifact.relative_path,
            "artifact_sha256": artifact.sha256,
            "source_task_id": artifact.task_id,
            "shape": json.dumps(list(artifact.shape), separators=(",", ":")),
        }
        for artifact, _ in inputs
    ]
    rows.append(
        {
            **identity,
            "artifact_role": "output",
            "artifact_kind": "endpoint_report",
            "artifact_path": report_path.relative_to(run_root).as_posix(),
            "artifact_sha256": _sha256(report_path),
            "source_task_id": request.task.task_id,
            "shape": "[]",
        }
    )
    return rows


def run_configured_reporting(request: ReportingRequest) -> ConfiguredReportingOutput:
    """Write one endpoint's report from its immutable final record and explicit artifacts."""
    stage = request.task.key.execution_stage
    if stage not in {"endpoint_summary", "endpoint_report"}:
        raise RecordError(f"unsupported configured reporting stage {stage!r}")
    if (
        request.final is not None
        and request.final.endpoint_model_id != request.task.endpoint.identifier
    ):
        raise RecordError("reporting final record belongs to another endpoint")

    run_root = _run_root(request)
    inputs = _validated_inputs(request, run_root)
    kinds = {artifact.kind for artifact, _ in inputs}
    if request.final is None:
        not_applicable = f"not_applicable_{request.endpoint_terminal_status}"
        statuses = {
            "fdr_status": not_applicable,
            "density_status": not_applicable,
            "labels_status": not_applicable,
        }
    else:
        statuses = {
            "fdr_status": _optional_status(request.fdr, kinds, FDR_ARTIFACT_KINDS),
            "density_status": _optional_status(
                request.density,
                kinds,
                DENSITY_ARTIFACT_KINDS,
            ),
            "labels_status": _optional_status(
                request.labels,
                kinds,
                LABEL_ARTIFACT_KINDS,
            ),
        }
    request.output_root.mkdir(parents=True, exist_ok=True)

    if stage == "endpoint_summary":
        summary_path = request.output_root / "endpoint_summary.csv"
        _write_csv_atomic(
            summary_path,
            [_summary_row(request, inputs, statuses)],
            _IDENTITY_FIELDS
            + _OPTIONAL_FIELDS
            + ("numeric_reporting_status", "linked_artifact_count", "numeric_metric_count"),
        )
        artifacts = (TaskArtifact("endpoint_summary", summary_path),)
    else:
        report_path = request.output_root / "endpoint_report.csv"
        _write_csv_atomic(
            report_path,
            _metric_rows(request, inputs, statuses),
            _IDENTITY_FIELDS + _OPTIONAL_FIELDS + _METRIC_FIELDS,
        )
        index_path = request.output_root / "artifact_index.csv"
        _write_csv_atomic(
            index_path,
            _artifact_index_rows(request, inputs, report_path, run_root),
            (
                "endpoint_model_id",
                "endpoint_terminal_status",
                "endpoint_terminal_detail",
                "final_model_id",
                "final_record_hash",
                "artifact_role",
                "artifact_kind",
                "artifact_path",
                "artifact_sha256",
                "source_task_id",
                "shape",
            ),
        )
        artifacts = (
            TaskArtifact("endpoint_report", report_path),
            TaskArtifact("artifact_index", index_path),
        )

    return ConfiguredReportingOutput(
        artifacts=artifacts,
        facts={
            "reporting_complete": True,
            "endpoint_terminal_status": request.endpoint_terminal_status,
            "endpoint_terminal_detail": request.endpoint_terminal_detail,
            "final_model_id": (
                request.final.final_model_id if request.final is not None else ""
            ),
            "final_record_hash": (
                request.final.record_hash if request.final is not None else ""
            ),
            "reporting_stage": stage,
            **statuses,
        },
    )


configured_reporting_runner = run_configured_reporting


__all__ = [
    "ConfiguredReportingOutput",
    "configured_reporting_runner",
    "run_configured_reporting",
]
