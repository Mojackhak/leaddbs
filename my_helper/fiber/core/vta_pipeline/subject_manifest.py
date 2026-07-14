"""Deterministic subject execution manifests for canonical VTA tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .artifacts import threshold_filename
from .errors import SubjectManifestError
from .paths import canonical_head_model_path, leaf_directory
from .planner import SubjectPlan, VtaTask, equivalent_task_key


SCHEMA_VERSION = "vta_subject_manifest_v1"


def build_subject_manifest(
    subject: SubjectPlan,
    run_id: str,
) -> dict[str, object]:
    """Build and validate one deterministic subject execution payload."""

    donor_tasks, reuse_ids = _validate_plan(subject, run_id)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "subject_id": subject.subject_id,
        "tasks": [
            {
                "task": task.to_payload(),
                "output_leaves": _canonical_leaves(task),
                "reuse_candidate_ids": list(reuse_ids[task.task_id]),
            }
            for task in subject.tasks
        ],
        "reuse_donors": [
            {
                "donor_id": donor.task_id,
                "output_leaves": _canonical_leaves(donor),
            }
            for donor in donor_tasks
        ],
    }
    validate_subject_manifest(payload, subject, run_id)
    return payload


def validate_subject_manifest(
    payload: Mapping[str, object],
    subject: SubjectPlan,
    run_id: str,
) -> None:
    """Validate a manifest against its authoritative selected subject plan."""

    root = _require_mapping(payload, "manifest")
    _require_exact_keys(
        root,
        {"schema_version", "run_id", "subject_id", "tasks", "reuse_donors"},
        "manifest",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise SubjectManifestError("Unsupported subject manifest schema_version")
    expected_run_id = _require_nonempty_string(run_id, "expected run_id")
    manifest_run_id = _require_nonempty_string(root["run_id"], "run_id")
    subject_id = _require_nonempty_string(root["subject_id"], "subject_id")
    donor_tasks, reuse_ids = _validate_plan(subject, expected_run_id)
    if manifest_run_id != expected_run_id:
        raise SubjectManifestError("Manifest run_id does not match expected run_id")
    if subject_id != subject.subject_id:
        raise SubjectManifestError("Manifest subject_id does not match SubjectPlan")

    task_entries = _require_array(root["tasks"], "tasks")
    donor_entries = _require_array(root["reuse_donors"], "reuse_donors")
    if len(task_entries) != len(subject.tasks):
        raise SubjectManifestError("Manifest task count does not match SubjectPlan")
    if len(donor_entries) != len(donor_tasks):
        raise SubjectManifestError("Manifest donor count does not match SubjectPlan")

    seen_task_ids: set[str] = set()
    for index, (raw_entry, task) in enumerate(zip(task_entries, subject.tasks)):
        label = f"tasks[{index}]"
        entry = _require_mapping(raw_entry, label)
        _require_exact_keys(
            entry,
            {"task", "output_leaves", "reuse_candidate_ids"},
            label,
        )
        task_payload = _require_mapping(entry["task"], f"{label}.task")
        task_id = _require_nonempty_string(
            task_payload.get("task_id"), f"{label}.task.task_id"
        )
        if task_id in seen_task_ids:
            raise SubjectManifestError(f"Duplicate selected task ID: {task_id}")
        seen_task_ids.add(task_id)
        if task_id != task.task_id or dict(task_payload) != task.to_payload():
            raise SubjectManifestError(
                f"Manifest task definition does not match SubjectPlan: {task_id}"
            )
        _validate_leaf_mapping(
            entry["output_leaves"], task, f"{label}.output_leaves"
        )
        candidate_ids = _require_string_array(
            entry["reuse_candidate_ids"], f"{label}.reuse_candidate_ids"
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise SubjectManifestError(
                f"Duplicate reuse candidate ID for task: {task_id}"
            )
        if tuple(candidate_ids) != reuse_ids[task_id]:
            raise SubjectManifestError(
                f"Reuse candidates are unknown, non-equivalent, or out of order: {task_id}"
            )

    seen_donor_ids: set[str] = set()
    for index, (raw_entry, donor) in enumerate(zip(donor_entries, donor_tasks)):
        label = f"reuse_donors[{index}]"
        entry = _require_mapping(raw_entry, label)
        _require_exact_keys(entry, {"donor_id", "output_leaves"}, label)
        donor_id = _require_nonempty_string(entry["donor_id"], f"{label}.donor_id")
        if donor_id in seen_donor_ids:
            raise SubjectManifestError(f"Duplicate donor ID: {donor_id}")
        seen_donor_ids.add(donor_id)
        if donor_id != donor.task_id:
            raise SubjectManifestError("Manifest donor order does not match SubjectPlan")
        _validate_leaf_mapping(
            entry["output_leaves"], donor, f"{label}.output_leaves"
        )

    if not seen_task_ids.issubset(seen_donor_ids):
        raise SubjectManifestError("Every selected task must appear in reuse_donors")


def write_subject_manifest(
    destination: Path | str,
    subject: SubjectPlan,
    run_id: str,
) -> Path:
    """Atomically write deterministic UTF-8 JSON for one subject manifest."""

    payload = build_subject_manifest(subject, run_id)
    encoded = _encode_manifest(payload)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return path


def _validate_plan(
    subject: SubjectPlan,
    run_id: str,
) -> tuple[tuple[VtaTask, ...], dict[str, tuple[str, ...]]]:
    _require_nonempty_string(run_id, "run_id")
    subject_id = _require_nonempty_string(subject.subject_id, "SubjectPlan.subject_id")
    if not subject.tasks:
        raise SubjectManifestError("SubjectPlan must contain at least one selected task")

    selected_by_id: dict[str, VtaTask] = {}
    all_selected_ids = {task.task_id for task in subject.tasks}
    seen_topology: set[str] = set()
    writable_leaves: list[tuple[str, Path]] = []
    headmodel_contexts: dict[Path, tuple[object, ...]] = {}
    canonical_subject_dir = subject.subject_dir.resolve(strict=False)
    if not subject.subject_dir.is_absolute():
        raise SubjectManifestError("SubjectPlan.subject_dir must be absolute")
    canonical_reconstruction: Path | None = None
    for task in subject.tasks:
        task_id = _validate_task_identity(
            task, subject_id, canonical_subject_dir, "selected task"
        )
        resolved_reconstruction = task.reconstruction_path.resolve(strict=False)
        if canonical_reconstruction is None:
            canonical_reconstruction = resolved_reconstruction
        elif resolved_reconstruction != canonical_reconstruction:
            raise SubjectManifestError(
                f"Selected task uses inconsistent reconstruction: {task_id}"
            )
        if task_id in selected_by_id:
            raise SubjectManifestError(f"Duplicate selected task ID: {task_id}")
        selected_by_id[task_id] = task
        if len(task.dependencies) != len(set(task.dependencies)):
            raise SubjectManifestError(f"Duplicate dependency for task: {task_id}")
        for dependency in task.dependencies:
            _require_nonempty_string(dependency, f"dependency of {task_id}")
            if dependency not in selected_by_id:
                if dependency in all_selected_ids:
                    raise SubjectManifestError(
                        f"Forward dependency for task {task_id}: {dependency}"
                    )
                raise SubjectManifestError(
                    f"Unknown dependency for task {task_id}: {dependency}"
                )
            if dependency not in seen_topology:
                raise SubjectManifestError(
                    f"Forward dependency for task {task_id}: {dependency}"
                )
        seen_topology.add(task_id)
        _validate_threshold_filenames(task)
        headmodel_path = canonical_head_model_path(task).resolve(strict=False)
        headmodel_context = _headmodel_context(task)
        existing_context = headmodel_contexts.setdefault(
            headmodel_path, headmodel_context
        )
        if existing_context != headmodel_context:
            raise SubjectManifestError(
                f"Tasks sharing headmodel have conflicting inputs: {headmodel_path}"
            )
        for leaf in _canonical_leaf_paths(task).values():
            writable_leaves.append((task_id, leaf))
    _reject_writable_leaf_overlap(writable_leaves)

    source_donors = subject.reuse_candidates or subject.tasks
    donor_by_id: dict[str, VtaTask] = {}
    donor_tasks: list[VtaTask] = []
    for donor in source_donors:
        donor_id = _validate_task_identity(
            donor, subject_id, canonical_subject_dir, "reuse donor"
        )
        if donor.reconstruction_path.resolve(strict=False) != canonical_reconstruction:
            raise SubjectManifestError(
                f"Reuse donor uses inconsistent reconstruction: {donor_id}"
            )
        if donor_id in donor_by_id:
            raise SubjectManifestError(f"Duplicate donor ID: {donor_id}")
        donor_by_id[donor_id] = donor
        donor_tasks.append(donor)

    for task in subject.tasks:
        existing = donor_by_id.get(task.task_id)
        if existing is None:
            donor_by_id[task.task_id] = task
            donor_tasks.append(task)
            continue
        if (
            existing.to_payload() != task.to_payload()
            or _canonical_leaves(existing) != _canonical_leaves(task)
        ):
            raise SubjectManifestError(
                f"Selected task conflicts with donor definition: {task.task_id}"
            )

    reuse_ids: dict[str, tuple[str, ...]] = {}
    for task in subject.tasks:
        task_key = equivalent_task_key(task)
        candidates: list[str] = []
        for donor in donor_tasks:
            if donor.task_id == task.task_id:
                continue
            if equivalent_task_key(donor) != task_key:
                continue
            candidates.append(donor.task_id)
        reuse_ids[task.task_id] = tuple(candidates)
        for donor_id in candidates:
            donor = donor_by_id[donor_id]
            if donor.subject_id != task.subject_id:
                raise SubjectManifestError("Reuse candidate crosses subject boundary")
            if equivalent_task_key(donor) != task_key:
                raise SubjectManifestError("Reuse candidate is not physically equivalent")
    return tuple(donor_tasks), reuse_ids


def _validate_task_identity(
    task: VtaTask,
    subject_id: str,
    subject_dir: Path,
    label: str,
) -> str:
    task_id = _require_nonempty_string(task.task_id, f"{label}.task_id")
    task_subject = _require_nonempty_string(
        task.subject_id, f"{label}.subject_id"
    )
    if task_subject != subject_id:
        raise SubjectManifestError(f"Cross-subject {label}: {task_id}")
    if task.subject_dir.resolve(strict=False) != subject_dir:
        raise SubjectManifestError(f"Cross-subject path for {label}: {task_id}")
    _canonical_leaf_paths(task, subject_dir)
    return task_id


def _canonical_leaf_paths(
    task: VtaTask, subject_dir: Path | None = None
) -> dict[str, Path]:
    spaces = tuple(task.model.spaces)
    if not spaces or len(spaces) != len(set(spaces)):
        raise SubjectManifestError(
            f"Task must define unique output spaces: {task.task_id}"
        )
    try:
        leaves = {space: leaf_directory(task, space) for space in spaces}
    except Exception as error:
        raise SubjectManifestError(
            f"Cannot derive canonical output leaves for task: {task.task_id}"
        ) from error
    stimulation_root = (
        (subject_dir or task.subject_dir) / "stimulations"
    ).resolve(strict=False)
    resolved_leaves: dict[str, Path] = {}
    for space, leaf in leaves.items():
        resolved = leaf.resolve(strict=False)
        if not resolved.is_relative_to(stimulation_root):
            raise SubjectManifestError(
                f"Canonical output leaf is outside subject stimulation tree: {leaf}"
            )
        resolved_leaves[space] = resolved
    return resolved_leaves


def _validate_threshold_filenames(task: VtaTask) -> None:
    names = tuple(
        threshold_filename(value) for value in task.model.thresholds_v_per_m
    )
    if len(names) != len(set(names)):
        raise SubjectManifestError(
            f"Thresholds produce colliding artifact file names: {task.task_id}"
        )


def _headmodel_context(task: VtaTask) -> tuple[object, ...]:
    return (
        task.subject_dir.resolve(strict=False),
        task.reconstruction_path.resolve(strict=False),
        task.hemisphere,
        task.reconstruction_lead_id,
        task.electrode_model,
        task.model.atlas_set,
        task.model.gray_matter_s_per_m,
        task.model.white_matter_s_per_m,
    )


def _canonical_leaves(task: VtaTask) -> dict[str, str]:
    return {space: str(path) for space, path in _canonical_leaf_paths(task).items()}


def _validate_leaf_mapping(raw: object, task: VtaTask, label: str) -> None:
    leaves = _require_mapping(raw, label)
    expected = _canonical_leaves(task)
    if set(leaves) != set(expected):
        raise SubjectManifestError(f"{label} does not contain canonical spaces")
    for space, expected_path in expected.items():
        actual = _require_nonempty_string(leaves[space], f"{label}.{space}")
        if actual != expected_path:
            raise SubjectManifestError(
                f"Non-canonical output leaf for task {task.task_id}: {space}"
            )


def _reject_writable_leaf_overlap(leaves: Sequence[tuple[str, Path]]) -> None:
    normalized: list[tuple[str, Path]] = [
        (task_id, path.resolve(strict=False)) for task_id, path in leaves
    ]
    for index, (task_id, path) in enumerate(normalized):
        for other_task_id, other in normalized[:index]:
            if path == other:
                raise SubjectManifestError(
                    f"Duplicate writable output leaf: {task_id} and {other_task_id}"
                )
            if path.is_relative_to(other) or other.is_relative_to(path):
                raise SubjectManifestError(
                    "Writable output leaves have ancestor/descendant overlap: "
                    f"{task_id} and {other_task_id}"
                )


def _encode_manifest(payload: Mapping[str, object]) -> bytes:
    try:
        text = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SubjectManifestError("Subject manifest is not JSON serializable") from error
    return (text + "\n").encode("utf-8")


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubjectManifestError(f"{label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise SubjectManifestError(f"{label} keys must be strings")
    return value


def _require_array(value: object, label: str) -> list[object] | tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise SubjectManifestError(f"{label} must be an array")
    return value


def _require_string_array(value: object, label: str) -> list[str]:
    array = _require_array(value, label)
    return [
        _require_nonempty_string(item, f"{label}[{index}]")
        for index, item in enumerate(array)
    ]


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SubjectManifestError(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(
    value: Mapping[str, object], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise SubjectManifestError(f"{label} has unsupported or missing fields")
