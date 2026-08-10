"""Verified batch-level cleanup of tool-owned MRtrix work caches."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from send2trash import send2trash

from .errors import PublicationError
from .identity import file_sha256
from .models import ValidationBundle
from .publication import OWNER
from .state import atomic_write_json, read_json
from .tck import validate_tck
from .visualization import visualization_state_errors


CACHE_DIRECTORY_NAMES = ("preparations", "seedwide", "staging", "rollback")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _verify_public_state(
    state: Mapping[str, Any],
    *,
    state_path: Path,
    tckinfo: Path,
    target_space: str,
    expected_semantic_keys: set[str],
    expected_scene_keys: set[str],
) -> None:
    if state.get("owner") != OWNER:
        raise PublicationError(
            f"non-tool-owned state blocks cache cleanup: {state_path}"
        )
    if state.get("status") != "complete":
        raise PublicationError(f"incomplete state blocks cache cleanup: {state_path}")
    if state.get("target_space") != target_space:
        raise PublicationError(f"target-space mismatch blocks cache cleanup: {state_path}")
    semantic_spaces: dict[str, set[str]] = {}
    for artifact in state.get("published_artifacts", []):
        path = Path(artifact["path"])
        if not path.is_file() or file_sha256(path) != artifact["sha256"]:
            raise PublicationError(f"artifact hash blocks cache cleanup: {path}")
        validate_tck(
            path,
            tckinfo,
            expected_count=int(artifact["streamline_count"]),
        )
        semantic_spaces.setdefault(str(artifact["semantic_key"]), set()).add(
            str(artifact["coordinate_space"])
        )
    if set(semantic_spaces) != expected_semantic_keys:
        raise PublicationError(
            f"published semantic keys block cache cleanup: {state_path}"
        )
    if any(
        spaces != {"native", target_space} for spaces in semantic_spaces.values()
    ):
        raise PublicationError(
            f"native/target-space artifact pairing blocks cache cleanup: {state_path}"
        )
    scene_errors = visualization_state_errors(
        state, expected_scene_keys=expected_scene_keys
    )
    if scene_errors:
        raise PublicationError(
            f"visualization blocks cache cleanup: {state_path}: {scene_errors[0]}"
        )


def cleanup_batch_work_caches(
    validation: ValidationBundle,
    *,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    """Clean eligible caches after a verified successful whole batch."""

    tckinfo = validation.tools["tckinfo"].executable
    states: dict[str, tuple[Path, dict[str, Any]]] = {}
    expected_semantic_keys = {
        key
        for seed in validation.config.atlas.seeds
        for key in (
            f"{seed.key}/seedwide",
            *(f"{seed.key}/target/{target.key}" for target in seed.targets),
        )
    }
    for subject in validation.subjects:
        state_path = subject.output_root / "work" / "state.json"
        state = read_json(state_path, default={})
        if not isinstance(state, dict):
            raise PublicationError(f"invalid state blocks cache cleanup: {state_path}")
        _verify_public_state(
            state,
            state_path=state_path,
            tckinfo=tckinfo,
            target_space=validation.config.atlas.space,
            expected_semantic_keys=expected_semantic_keys,
            expected_scene_keys={seed.key for seed in validation.config.atlas.seeds},
        )
        states[subject.subject_id] = (state_path, state)

    requested = validation.config.execution.cleanup_work_cache_after_success
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    for subject in validation.subjects:
        state_path, state = states[subject.subject_id]
        work_root = state_path.parent.resolve()
        if not requested:
            cleanup = {
                "requested": False,
                "status": "disabled",
                "selected_paths": [],
                "removed_paths": [],
                "pending_paths": [],
                "bytes_selected": 0,
                "completed_at_utc": _now_utc(),
            }
            state["cache_cleanup"] = cleanup
            atomic_write_json(state_path, state)
            results.append({"subject_id": subject.subject_id, **cleanup})
            continue

        selected: list[dict[str, Any]] = []
        for name in CACHE_DIRECTORY_NAMES:
            candidate = work_root / name
            if candidate.parent.resolve() != work_root:
                raise PublicationError(f"unsafe cache cleanup path: {candidate}")
            if candidate.exists():
                if not candidate.is_dir() or candidate.is_symlink():
                    raise PublicationError(
                        f"cache cleanup candidate is not a directory: {candidate}"
                    )
                selected.append(
                    {"path": str(candidate), "size_bytes": _tree_size(candidate)}
                )
        cleanup = {
            "requested": True,
            "status": "in_progress",
            "selected_paths": selected,
            "removed_paths": [],
            "pending_paths": [],
            "bytes_selected": sum(item["size_bytes"] for item in selected),
            "started_at_utc": _now_utc(),
        }
        state["cache_cleanup"] = cleanup
        atomic_write_json(state_path, state)
        progress(f"[{subject.subject_id}] moving verified work caches to Trash")
        for item in selected:
            path = Path(item["path"])
            try:
                send2trash(str(path))
                cleanup["removed_paths"].append(str(path))
            except Exception as exc:
                cleanup["pending_paths"].append(
                    {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}
                )
        cleanup["status"] = "complete" if not cleanup["pending_paths"] else "warning"
        cleanup["completed_at_utc"] = _now_utc()
        state["cache_cleanup"] = cleanup
        atomic_write_json(state_path, state)
        _verify_public_state(
            state,
            state_path=state_path,
            tckinfo=tckinfo,
            target_space=validation.config.atlas.space,
            expected_semantic_keys=expected_semantic_keys,
            expected_scene_keys={seed.key for seed in validation.config.atlas.seeds},
        )
        if cleanup["pending_paths"]:
            warnings.append(
                f"{subject.subject_id} cache cleanup has pending paths"
            )
        results.append({"subject_id": subject.subject_id, **cleanup})
    return {
        "requested": requested,
        "status": "complete" if not warnings else "warning",
        "subjects": results,
        "warnings": warnings,
    }
