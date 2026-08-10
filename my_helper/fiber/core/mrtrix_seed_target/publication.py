"""Safe transactional subject-level publication of staged TCK artifacts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence
import uuid

from send2trash import send2trash

from .errors import PublicationError
from .identity import file_sha256
from .models import BatchConfig, ResolvedSubjectInputs, SeedSpec
from .state import atomic_write_json, read_json


OWNER = "mrtrix_seed_target_seedwide_v1"


def _desired_artifacts(
    subject: ResolvedSubjectInputs,
    seeds: Sequence[SeedSpec],
    seed_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for seed in seeds:
        result = seed_results[seed.key]
        output_root = (
            subject.output_root
            / "tractograms"
            / "native"
            / seed.side
            / seed.roi_id
        )
        mother = result["outputs"]["mother"]
        artifacts.append(
            {
                "semantic_key": f"{seed.key}/seedwide",
                "coordinate_space": "native",
                "source_path": mother["path"],
                "path": str(output_root / "seedwide.tck"),
                "sha256": mother["sha256"],
                "streamline_count": int(mother["streamline_count"]),
                "seedwide_identity": result["seedwide_identity"],
            }
        )
        for target in result["outputs"]["targets"]:
            artifacts.append(
                {
                    "semantic_key": f"{seed.key}/target/{target['key']}",
                    "coordinate_space": "native",
                    "source_path": target["path"],
                    "path": str(
                        output_root
                        / "targets"
                        / target["side"]
                        / f"{target['id']}.tck"
                    ),
                    "sha256": target["sha256"],
                    "streamline_count": int(target["streamline_count"]),
                    "hit_fraction": float(target["hit_fraction"]),
                    "seedwide_identity": result["seedwide_identity"],
                }
            )
    return artifacts


def _owned_records(
    state: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    records: dict[str, list[Mapping[str, Any]]] = {}
    for key in ("published_artifacts", "publication_intent"):
        for artifact in state.get(key, []) if isinstance(state, Mapping) else []:
            path = str(artifact.get("path", ""))
            if path:
                records.setdefault(path, []).append(artifact)
    return records


def _matching_owned_record(
    candidates: Sequence[Mapping[str, Any]], current_hash: str
) -> Mapping[str, Any] | None:
    """Return the ownership record matching the file currently on disk."""

    return next(
        (record for record in candidates if record.get("sha256") == current_hash),
        None,
    )


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _trash_appledouble_sidecars(root: Path) -> tuple[list[str], list[str]]:
    """Move macOS AppleDouble metadata out of the public tractogram tree."""

    moved: list[str] = []
    failed: list[str] = []
    if not root.is_dir():
        return moved, failed
    for path in sorted(root.rglob("._*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        try:
            send2trash(str(path))
            moved.append(str(path))
        except Exception:
            failed.append(str(path))
    return moved, failed


def publish_subject(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    preparation: Mapping[str, Any],
    seed_results: Mapping[str, Mapping[str, Any]],
    run_provenance: Mapping[str, str],
) -> dict[str, Any]:
    """Publish every changed seed-side TCK as one recoverable subject transaction."""

    work_root = subject.output_root / "work"
    state_path = work_root / "state.json"
    prior = read_json(state_path, default={})
    if prior and prior.get("owner") != OWNER:
        raise PublicationError(f"non-tool-owned state file blocks publication: {state_path}")
    desired = _desired_artifacts(subject, config.atlas.seeds, seed_results)
    owned = _owned_records(prior)
    desired_paths = {artifact["path"] for artifact in desired}
    public_root = (subject.output_root / "tractograms" / "native").resolve()

    if public_root.is_dir():
        for existing in sorted(
            (path for path in public_root.rglob("*") if path.is_file()),
            key=lambda path: path.as_posix(),
        ):
            if existing.name.startswith("._"):
                continue
            path_text = str(existing)
            if path_text not in desired_paths and path_text not in owned:
                raise PublicationError(
                    f"non-tool-owned stale path blocks publication: {existing}"
                )

    replacements: list[dict[str, Any]] = []
    reused: list[str] = []
    for artifact in desired:
        source = Path(artifact["source_path"])
        final = Path(artifact["path"])
        if not source.is_file() or file_sha256(source) != artifact["sha256"]:
            raise PublicationError(f"staged artifact failed hash verification: {source}")
        if final.exists():
            candidates = owned.get(str(final), [])
            if not candidates:
                raise PublicationError(
                    f"non-tool-owned final path blocks publication: {final}"
                )
            current_hash = file_sha256(final)
            if _matching_owned_record(candidates, current_hash) is None:
                raise PublicationError(
                    f"tool ownership hash no longer matches final path: {final}"
                )
            if current_hash == artifact["sha256"]:
                reused.append(str(final))
                continue
        replacements.append(artifact)

    stale: list[Path] = []
    for path_text, candidates in sorted(owned.items()):
        if path_text in desired_paths:
            continue
        path = Path(path_text)
        if not path.exists():
            continue
        try:
            path.resolve().relative_to(public_root)
        except ValueError as exc:
            raise PublicationError(
                f"owned stale path resolves outside the public root: {path}"
            ) from exc
        if not path.is_file():
            raise PublicationError(f"owned stale path is not a file: {path}")
        current_hash = file_sha256(path)
        if _matching_owned_record(candidates, current_hash) is None:
            raise PublicationError(
                f"tool ownership hash no longer matches stale path: {path}"
            )
        stale.append(path)

    transaction_id = uuid.uuid4().hex
    transaction_root = work_root / "staging" / f"publication-{transaction_id}"
    rollback_root = work_root / "rollback" / transaction_id
    prepared_files: dict[str, Path] = {}
    for index, artifact in enumerate(replacements):
        prepared = transaction_root / f"artifact-{index:04d}.tck"
        _link_or_copy(Path(artifact["source_path"]), prepared)
        if file_sha256(prepared) != artifact["sha256"]:
            raise PublicationError(f"publication copy hash mismatch: {prepared}")
        prepared_files[artifact["path"]] = prepared

    intent_state = {
        "owner": OWNER,
        "status": "publishing",
        "transaction_id": transaction_id,
        "configuration_hash": config.configuration_hash,
        "subject_id": subject.subject_id,
        "subject_dir": str(subject.subject_dir),
        "run_provenance": dict(run_provenance),
        "preparation_identity": preparation["preparation_identity"],
        "published_artifacts": prior.get("published_artifacts", []),
        "publication_intent": desired,
        "cleanup_pending": prior.get("cleanup_pending", []),
    }
    atomic_write_json(state_path, intent_state)

    moved_old: dict[str, Path] = {}
    installed: list[Path] = []
    try:
        for index, artifact in enumerate(replacements):
            final = Path(artifact["path"])
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                rollback = rollback_root / f"artifact-{index:04d}.tck"
                rollback.parent.mkdir(parents=True, exist_ok=True)
                os.replace(final, rollback)
                moved_old[str(final)] = rollback
            os.replace(prepared_files[str(final)], final)
            installed.append(final)
        for index, final in enumerate(stale):
            rollback = rollback_root / f"stale-{index:04d}.tck"
            rollback.parent.mkdir(parents=True, exist_ok=True)
            os.replace(final, rollback)
            moved_old[str(final)] = rollback
        for artifact in desired:
            final = Path(artifact["path"])
            if not final.is_file() or file_sha256(final) != artifact["sha256"]:
                raise PublicationError(f"published artifact failed verification: {final}")
    except BaseException as exc:
        rollback_errors: list[str] = []
        for final in reversed(installed):
            try:
                if final.exists():
                    recovery = transaction_root / f"failed-{uuid.uuid4().hex}.tck"
                    recovery.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(final, recovery)
            except OSError as rollback_exc:
                rollback_errors.append(f"{final}: {rollback_exc}")
        for final_text, old in reversed(tuple(moved_old.items())):
            final = Path(final_text)
            try:
                if old.exists():
                    final.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(old, final)
            except OSError as rollback_exc:
                rollback_errors.append(f"{final}: {rollback_exc}")
        failure_state = {
            **intent_state,
            "status": "publication_failed",
            "error": str(exc),
            "rollback_errors": rollback_errors,
        }
        atomic_write_json(state_path, failure_state)
        raise PublicationError(
            f"subject publication failed for {subject.subject_id}: {exc}; "
            f"rollback errors: {rollback_errors}"
        ) from exc

    complete_state = {
        "owner": OWNER,
        "status": "native_complete",
        "transaction_id": transaction_id,
        "configuration_hash": config.configuration_hash,
        "subject_id": subject.subject_id,
        "subject_dir": str(subject.subject_dir),
        "run_provenance": dict(run_provenance),
        "preparation_identity": preparation["preparation_identity"],
        "seed_results": {
            key: {
                "seedwide_identity": result["seedwide_identity"],
                "identity_document": result["identity_document"],
                "preparation_artifact_set_hash": result["identity_document"][
                    "preparation_artifact_set_hash"
                ],
                "total_streamlines": int(result["total_streamlines"]),
                "target_hit_counts": [
                    int(value) for value in result["target_hit_counts"]
                ],
                "targets": [
                    {
                        "key": target["key"],
                        "streamline_count": int(target["streamline_count"]),
                        "hit_fraction": float(target["hit_fraction"]),
                    }
                    for target in result["outputs"]["targets"]
                ],
                "minimum_target_streamlines": int(
                    result["minimum_target_streamlines"]
                ),
            }
            for key, result in seed_results.items()
        },
        "published_artifacts": desired,
        "publication_intent": [],
        "cleanup_pending": [],
    }
    atomic_write_json(state_path, complete_state)

    cleanup_pending: list[str] = []
    for rollback in moved_old.values():
        if not rollback.exists():
            continue
        try:
            send2trash(str(rollback))
        except Exception:
            cleanup_pending.append(str(rollback))
    appledouble_trashed, appledouble_failed = _trash_appledouble_sidecars(
        subject.output_root / "tractograms" / "native"
    )
    cleanup_pending.extend(appledouble_failed)
    if cleanup_pending:
        complete_state["status"] = "cleanup_pending"
        complete_state["cleanup_pending"] = cleanup_pending
        atomic_write_json(state_path, complete_state)

    return {
        "status": complete_state["status"],
        "subject_id": subject.subject_id,
        "output_root": str(subject.output_root),
        "generated_artifacts": len(replacements),
        "reused_artifacts": len(reused),
        "retired_artifacts": len(stale),
        "published_artifacts": desired,
        "cleanup_pending": cleanup_pending,
        "appledouble_trashed": appledouble_trashed,
    }
