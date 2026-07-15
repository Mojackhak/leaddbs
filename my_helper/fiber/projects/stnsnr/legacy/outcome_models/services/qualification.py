"""Fixed internal implementation qualification for configured model tasks."""

from __future__ import annotations

import csv
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..planner import TaskSpec
from ..records import FinalArtifactRecord, RecordError
from .formal import FormalRequest
from .record_io import load_final_record


_SEED = 42
_EQUIVALENCE_MAX_FEATURES = 1000
_EQUIVALENCE_ATOL = 1e-12
_EQUIVALENCE_RTOL = 1e-12
_FIBER_SMOKE_PERMUTATIONS = 1000
_FIBER_SMOKE_BOOTSTRAPS = 1000
_SUPPORTED_OPERATIONS = {
    "equivalence_smoke",
    "optimized_equivalence_smoke",
    "candidate_source_smoke",
}


def _load_analysis(name: str):
    analysis_root = Path(__file__).resolve().parents[5] / "core" / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module(name)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        temporary.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class QualificationRequest:
    """One final-record-locked technical qualification request."""

    task: TaskSpec
    final: FinalArtifactRecord
    output_root: Path
    operation: str

    @classmethod
    def from_context(
        cls,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
    ) -> "QualificationRequest":
        operation = task.key.execution_stage
        if operation not in _SUPPORTED_OPERATIONS:
            raise RecordError(f"unsupported qualification operation {operation!r}")
        if task.workflow_phase != "formal":
            raise RecordError("qualification request requires a formal-phase task")
        if task.key.source_reference != "final_model_record":
            raise RecordError("qualification task must reference an immutable final-model record")
        if final.endpoint_model_id != task.endpoint.identifier:
            raise RecordError("qualification final artifact belongs to another endpoint")
        if operation == "candidate_source_smoke" and task.endpoint.model_family not in {
            "hf_fiber",
            "ulf_fiber",
        }:
            raise RecordError("candidate-source smoke is only defined for normative-fiber models")
        return cls(
            task=task,
            final=final,
            output_root=(
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            ),
            operation=operation,
        )


@dataclass(frozen=True)
class QualificationRun:
    """Numerical qualification outcome without model-classification feedback."""

    passed: bool
    detail: str
    metrics: Mapping[str, object]


TargetBuilder = Callable[[FormalRequest], Any]
FiberPermutationRunner = Callable[..., Mapping[str, Any]]
FiberBootstrapRunner = Callable[..., Mapping[str, Any]]
QualificationRunner = Callable[[QualificationRequest], QualificationRun]
FinalLoader = Callable[[TaskSpec, RunContext], FinalArtifactRecord]


def _configured_target(request: QualificationRequest, target_builder: TargetBuilder | None) -> Any:
    if target_builder is None:
        from .legacy_formal import build_configured_formal_target

        target_builder = build_configured_formal_target
    formal_request = FormalRequest(
        task=request.task,
        final=request.final,
        output_root=request.output_root,
        permutations=_FIBER_SMOKE_PERMUTATIONS,
        bootstraps=_FIBER_SMOKE_BOOTSTRAPS,
        seed=_SEED,
    )
    return target_builder(formal_request)


def _float_column(rows: list[dict[str, str]], column: str) -> np.ndarray:
    if not rows or column not in rows[0]:
        raise RecordError(f"qualification score table is missing column {column!r}")
    try:
        return np.asarray([float(row[column]) for row in rows], dtype=float)
    except (TypeError, ValueError) as exc:
        raise RecordError(f"qualification score column {column!r} is not numeric") from exc


def _target_score_table(target: Any) -> Path:
    candidates = [
        Path(value)
        for name in ("subjects_csv", "scores_csv")
        if (value := getattr(target, name, None)) is not None
    ]
    if not candidates:
        raise RecordError(
            "qualification target requires subjects_csv or scores_csv"
        )
    if len(candidates) > 1 and candidates[0] != candidates[1]:
        raise RecordError("qualification target score-table fields disagree")
    return candidates[0]


def _target_arrays(target: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    exposure = np.asarray(np.load(Path(target.x_path), mmap_mode="r"), dtype=float)
    if exposure.ndim != 2 or exposure.shape[1] < 1:
        raise RecordError("qualification exposure must be a nonempty subject-by-feature matrix")
    with _target_score_table(target).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != exposure.shape[0]:
        raise RecordError("qualification score and exposure subject counts differ")
    outcome = _float_column(rows, str(target.outcome_column))
    nuisance_columns = tuple(str(value) for value in target.nuisance_columns)
    nuisance = (
        np.column_stack([_float_column(rows, column) for column in nuisance_columns])
        if nuisance_columns
        else None
    )
    delta_path = getattr(target, "delta_hf_full_path", None)
    if delta_path is not None:
        delta = np.asarray(np.load(Path(delta_path), mmap_mode="r"), dtype=float)
        if delta.shape != (exposure.shape[0],):
            raise RecordError("qualification DeltaHF full score shape is invalid")
        nuisance = delta[:, None] if nuisance is None else np.column_stack([nuisance, delta])
    return exposure, outcome, nuisance


def _equivalence_metrics(target: Any) -> tuple[bool, dict[str, object]]:
    stats = _load_analysis("stnsnr_four_model_stats")
    exposure, outcome, nuisance = _target_arrays(target)
    n_features = min(int(exposure.shape[1]), _EQUIVALENCE_MAX_FEATURES)
    rng = np.random.default_rng(_SEED)
    selected = np.sort(rng.choice(exposure.shape[1], size=n_features, replace=False))
    subset = exposure[:, selected]
    optimized = np.asarray(stats.partial_spearman_matrix(outcome, subset, nuisance), dtype=float)
    reference = np.asarray(stats.partial_spearman_loop_reference(outcome, subset, nuisance), dtype=float)
    finite = np.isfinite(optimized) & np.isfinite(reference)
    finite_count = int(np.count_nonzero(finite))
    matching_nan = np.array_equal(np.isnan(optimized), np.isnan(reference))
    equivalent = bool(
        finite_count > 0
        and matching_nan
        and np.allclose(
            optimized[finite],
            reference[finite],
            atol=_EQUIVALENCE_ATOL,
            rtol=_EQUIVALENCE_RTOL,
        )
    )
    max_difference = (
        float(np.max(np.abs(optimized[finite] - reference[finite])))
        if finite_count
        else None
    )
    return equivalent, {
        "optimized_kernel": "partial_spearman_matrix",
        "reference_kernel": "partial_spearman_loop_reference",
        "seed": _SEED,
        "feature_count": n_features,
        "finite_comparison_count": finite_count,
        "matching_nan_pattern": matching_nan,
        "absolute_tolerance": _EQUIVALENCE_ATOL,
        "relative_tolerance": _EQUIVALENCE_RTOL,
        "max_abs_difference": max_difference,
    }


def _candidate_smoke_metrics(
    target: Any,
    *,
    permutation_runner: FiberPermutationRunner | None,
    bootstrap_runner: FiberBootstrapRunner | None,
) -> tuple[bool, dict[str, object]]:
    if permutation_runner is None:
        permutation_runner = _load_analysis(
            "stnsnr_normative_fiber_smoke_permutation"
        ).run_target_smoke_permutation
    if bootstrap_runner is None:
        bootstrap_runner = _load_analysis(
            "stnsnr_normative_fiber_formal_bootstrap"
        ).run_target_bootstrap
    permutation = permutation_runner(
        target,
        n_permutations=_FIBER_SMOKE_PERMUTATIONS,
        seed=_SEED,
        tier="smoke",
    )
    bootstrap = bootstrap_runner(
        target,
        n_bootstraps=_FIBER_SMOKE_BOOTSTRAPS,
        seed=_SEED,
    )
    p_value = float(permutation.get("p_plus_one_two_sided", np.nan))
    null_finite_count = int(permutation.get("null_finite_count", 0))
    fold_candidate_min = int(permutation.get("fold_n_candidate_fibers_min", 0))
    finite_bootstrap_count = int(bootstrap.get("finite_bootstrap_count", 0))
    passed = bool(
        permutation.get("permutation_status") == "complete"
        and bootstrap.get("bootstrap_status") == "complete"
        and np.isfinite(p_value)
        and null_finite_count > 0
        and fold_candidate_min > 0
        and finite_bootstrap_count > 0
    )
    return passed, {
        "smoke_seed": _SEED,
        "smoke_permutations": _FIBER_SMOKE_PERMUTATIONS,
        "smoke_bootstraps": _FIBER_SMOKE_BOOTSTRAPS,
        "permutation_status": str(permutation.get("permutation_status", "missing")),
        "bootstrap_status": str(bootstrap.get("bootstrap_status", "missing")),
        "plus_one_p_computable": bool(np.isfinite(p_value)),
        "null_finite_count": null_finite_count,
        "fold_candidate_fibers_min": fold_candidate_min,
        "finite_bootstrap_count": finite_bootstrap_count,
    }


def run_technical_qualification(
    request: QualificationRequest,
    *,
    target_builder: TargetBuilder | None = None,
    fiber_permutation_runner: FiberPermutationRunner | None = None,
    fiber_bootstrap_runner: FiberBootstrapRunner | None = None,
) -> QualificationRun:
    """Run deterministic kernel equivalence and, for fiber tasks, fixed smoke resampling."""
    target = _configured_target(request, target_builder)
    equivalent, metrics = _equivalence_metrics(target)
    if not equivalent:
        return QualificationRun(False, "optimized_reference_mismatch", metrics)
    if request.operation != "candidate_source_smoke":
        return QualificationRun(True, "optimized_reference_equivalent", metrics)
    smoke_passed, smoke_metrics = _candidate_smoke_metrics(
        target,
        permutation_runner=fiber_permutation_runner,
        bootstrap_runner=fiber_bootstrap_runner,
    )
    combined = {**metrics, **smoke_metrics}
    return QualificationRun(
        smoke_passed,
        "candidate_source_smoke_completed" if smoke_passed else "candidate_source_smoke_failed",
        combined,
    )


class QualificationService:
    """Execute a fixed qualification task without changing model classification."""

    def __init__(
        self,
        *,
        final_loader: FinalLoader = load_final_record,
        runner: QualificationRunner = run_technical_qualification,
    ) -> None:
        self.final_loader = final_loader
        self.runner = runner

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        final: FinalArtifactRecord | None = None
        request: QualificationRequest | None = None
        try:
            final = self.final_loader(task, context)
            request = QualificationRequest.from_context(task, context, final)
            run = self.runner(request)
        except (ImportError, OSError, RecordError, RuntimeError, ValueError) as exc:
            if request is None:
                output_root = (
                    context.store.run_root
                    / "models"
                    / task.endpoint.identifier
                    / "tasks"
                    / task.task_id
                )
                operation = task.key.execution_stage
            else:
                output_root = request.output_root
                operation = request.operation
            run = QualificationRun(False, f"qualification_service_failure:{exc}", {})
        else:
            output_root = request.output_root
            operation = request.operation

        status_path = output_root / "qualification_status.json"
        payload: dict[str, object] = {
            "schema_version": "1",
            "operation": operation,
            "qualification_passed": bool(run.passed),
            "detail": run.detail,
            "metrics": dict(run.metrics),
        }
        if final is not None:
            payload.update(
                {
                    "final_model_id": final.final_model_id,
                    "final_record_hash": final.record_hash,
                }
            )
        _atomic_json(status_path, payload)
        facts: dict[str, object] = {
            "qualification_complete": bool(run.passed),
            "qualification_passed": bool(run.passed),
        }
        if final is not None:
            facts.update(
                {
                    "final_model_id": final.final_model_id,
                    "final_record_hash": final.record_hash,
                }
            )
        return TaskResult(
            status=TaskStatus.COMPLETED if run.passed else TaskStatus.EXECUTION_FAILURE,
            detail=run.detail,
            facts=facts,
            artifacts=(TaskArtifact("qualification_status", status_path),),
        )


__all__ = [
    "QualificationRequest",
    "QualificationRun",
    "QualificationService",
    "run_technical_qualification",
]
