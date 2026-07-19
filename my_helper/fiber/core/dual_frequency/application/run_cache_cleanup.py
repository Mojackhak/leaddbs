"""Fail-closed cleanup for run-owned scratch after canonical publication."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Mapping, Sequence
import uuid

from ..contracts import (
    FinalSelectionRecord,
    FormalOperatorScratchRecord,
    PPAMObservedWorkspaceRecord,
)
from ..runtime.formal_operator_workspace import (
    cleanup_formal_operator_scratch_record,
    formal_operator_scratch_descriptor,
    validate_formal_operator_scratch_record,
)
from ..runtime.ppam_observed_workspace import (
    cleanup_ppam_observed_workspace_record,
    ppam_operator_scratch_descriptor,
    validate_ppam_observed_workspace_record,
)
from ..workflow.executor import TaskOutcome


CLEANUP_SCHEMA = "dual_frequency_run_cache_cleanup_v1"
CLEANUP_MARKER = "run_cache_cleanup.json"


class RunCacheCleanupError(RuntimeError):
    """Raised before unsafe or incomplete cleanup can mutate run scratch."""


@dataclass(frozen=True, slots=True)
class RunCacheCleanupResult:
    """Summary of one disabled, reused, or completed cleanup decision."""

    enabled: bool
    cleaned: bool
    reused: bool
    removed_generations: tuple[str, ...]
    runtime_work_removed: bool


def _json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunCacheCleanupError(f"required cleanup JSON is unreadable: {path}") from error
    if not isinstance(payload, dict):
        raise RunCacheCleanupError(f"required cleanup JSON is not an object: {path}")
    return payload


def _policy(resolved: Mapping[str, object]) -> bool:
    storage = resolved.get("storage")
    if not isinstance(storage, Mapping):
        raise RunCacheCleanupError("resolved storage policy is missing")
    enabled = storage.get("delete_run_cache_on_success")
    if type(enabled) is not bool:
        raise RunCacheCleanupError("run-cache cleanup policy must be boolean")
    return enabled


def _csv_rows(path: Path) -> tuple[dict[str, str], ...]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return tuple(dict(row) for row in csv.DictReader(stream))
    except OSError as error:
        raise RunCacheCleanupError(f"required cleanup CSV is unreadable: {path}") from error


def _validate_publication_root(
    root: Path,
    run_id: str,
    expected_scales: tuple[str, ...],
) -> None:
    manifest = _json_object(root / "model_manifest.json")
    if (
        manifest.get("final_status") != "completed"
        or manifest.get("source_run_id") != run_id
        or manifest.get("scale_count") != len(expected_scales)
    ):
        raise RunCacheCleanupError(
            f"canonical publication is not cleanup-complete: {root}"
        )
    index_rows = _csv_rows(root / "artifact_index.csv")
    if not index_rows or any(row.get("status") != "completed" for row in index_rows):
        raise RunCacheCleanupError(
            f"canonical artifact index is not cleanup-complete: {root}"
        )
    scale_rows = _csv_rows(root / "scale_status.csv")
    if (
        len(scale_rows) != len(expected_scales)
        or {row.get("scale_id") for row in scale_rows} != set(expected_scales)
        or any(row.get("overall_status") != "completed" for row in scale_rows)
    ):
        raise RunCacheCleanupError(
            f"canonical scale coverage is not cleanup-complete: {root}"
        )


def _preflight_generation(root: Path, filenames: tuple[str, ...]) -> None:
    generation = Path(root).resolve()
    if not generation.is_dir() or generation.is_symlink():
        raise RunCacheCleanupError(
            f"run-owned scratch generation is missing or unsafe: {generation}"
        )
    expected = set(filenames)
    actual = {path.name for path in generation.iterdir()}
    if not expected or actual != expected:
        raise RunCacheCleanupError(
            f"run-owned scratch generation is incomplete or untracked: {generation}"
        )


def _relative_generation(run_root: Path, generation: Path) -> str:
    try:
        return generation.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError as error:
        raise RunCacheCleanupError(
            f"run-owned scratch generation escapes the run: {generation}"
        ) from error


def _write_marker(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def cleanup_run_cache_after_publication(
    *,
    run_root: Path,
    resolved_configuration: Mapping[str, object],
    outcomes: Sequence[TaskOutcome],
    direct_voxel_publication: Path,
    normative_fiber_publication: Path,
) -> RunCacheCleanupResult:
    """Delete only validated run-owned scratch after complete publication."""

    enabled = _policy(resolved_configuration)
    if not enabled:
        return RunCacheCleanupResult(False, False, False, (), False)

    root = Path(run_root).expanduser().resolve()
    marker = root / CLEANUP_MARKER
    if marker.is_file():
        payload = _json_object(marker)
        generations = payload.get("removed_generations")
        runtime_removed = payload.get("runtime_work_removed")
        if (
            payload.get("schema_version") != CLEANUP_SCHEMA
            or payload.get("status") != "completed"
            or not isinstance(generations, list)
            or not all(type(value) is str and value for value in generations)
            or type(runtime_removed) is not bool
            or any((root / value).exists() for value in generations)
            or (runtime_removed and (root / "runtime_work").exists())
        ):
            raise RunCacheCleanupError("run-cache cleanup marker is inconsistent")
        return RunCacheCleanupResult(
            True,
            False,
            True,
            tuple(generations),
            runtime_removed,
        )

    run_manifest = _json_object(root / "run_manifest.json")
    run_id = run_manifest.get("run_id")
    selected = resolved_configuration.get("study")
    if (
        run_manifest.get("final_status") != "completed"
        or type(run_id) is not str
        or not run_id
        or not isinstance(selected, Mapping)
        or not isinstance(selected.get("selected_scales"), list)
        or not all(
            type(value) is str and value for value in selected["selected_scales"]
        )
    ):
        raise RunCacheCleanupError("source run is not cleanup-complete")
    if not outcomes or any(
        not isinstance(outcome, TaskOutcome)
        or outcome.status not in {"completed", "skipped"}
        for outcome in outcomes
    ):
        raise RunCacheCleanupError("source run retains failed or nonterminal tasks")
    artifact_index = _json_object(root / "artifact_index.json")
    if not isinstance(artifact_index.get("artifacts"), list):
        raise RunCacheCleanupError("source run artifact index is incomplete")

    expected_scales = tuple(str(value) for value in selected["selected_scales"])
    _validate_publication_root(
        Path(direct_voxel_publication).resolve(),
        run_id,
        expected_scales,
    )
    _validate_publication_root(
        Path(normative_fiber_publication).resolve(),
        run_id,
        expected_scales,
    )

    records = tuple(
        outcome.result.decode_record()
        for outcome in outcomes
        if outcome.status == "completed" and outcome.result is not None
    )
    finals = {
        record.final_model.identifier: record.final_model
        for record in records
        if isinstance(record, FinalSelectionRecord) and record.final_model is not None
    }
    formal = tuple(
        record for record in records if isinstance(record, FormalOperatorScratchRecord)
    )
    ppam = tuple(
        record for record in records if isinstance(record, PPAMObservedWorkspaceRecord)
    )
    generations: list[str] = []
    for record in formal:
        validate_formal_operator_scratch_record(record, root)
        descriptor = formal_operator_scratch_descriptor(record, root)
        _preflight_generation(
            descriptor.root,
            tuple(item.filename for item in descriptor.arrays),
        )
        generations.append(_relative_generation(root, descriptor.root))
    for record in ppam:
        if record.technical_status == "nuisance_not_estimable":
            continue
        final_model = finals.get(record.target_id)
        if final_model is None:
            raise RunCacheCleanupError(
                "pPAM scratch cleanup lacks its final model"
            )
        validate_ppam_observed_workspace_record(record, final_model, root)
        descriptor = ppam_operator_scratch_descriptor(record, root)
        _preflight_generation(
            descriptor.root,
            tuple(item.filename for item in descriptor.arrays),
        )
        generations.append(_relative_generation(root, descriptor.root))

    runtime_work = root / "runtime_work"
    runtime_exists = runtime_work.exists()
    if runtime_exists and (
        runtime_work.is_symlink()
        or not runtime_work.is_dir()
        or not runtime_work.resolve().is_relative_to(root)
    ):
        raise RunCacheCleanupError("runtime_work cleanup target is unsafe")

    for record in formal:
        cleanup_formal_operator_scratch_record(record, root)
    for record in ppam:
        cleanup_ppam_observed_workspace_record(record, root)
    if runtime_exists:
        shutil.rmtree(runtime_work)

    normalized_generations = tuple(sorted(generations))
    _write_marker(
        marker,
        {
            "schema_version": CLEANUP_SCHEMA,
            "status": "completed",
            "run_id": run_id,
            "removed_generations": list(normalized_generations),
            "runtime_work_removed": runtime_exists,
        },
    )
    return RunCacheCleanupResult(
        True,
        True,
        False,
        normalized_generations,
        runtime_exists,
    )


__all__ = [
    "CLEANUP_MARKER",
    "CLEANUP_SCHEMA",
    "RunCacheCleanupError",
    "RunCacheCleanupResult",
    "cleanup_run_cache_after_publication",
]
