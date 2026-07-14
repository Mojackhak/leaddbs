"""Public validation, execution, and status orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Iterator, Mapping

from .config import load_config
from .errors import MrtrixSeedTargetError, PublicationError
from .identity import file_sha256
from .models import ResolvedSubjectInputs, ValidationBundle
from .preparation import prepare_subject
from .publication import OWNER, publish_subject
from .resources import ResourcePool
from .state import atomic_write_json, read_json
from .tck import validate_tck
from .tools import reset_stop_request
from .tracking import run_seedwide
from .validation import validate_config


ProgressCallback = Callable[[str], None]


def _default_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _run_provenance(validation: ValidationBundle) -> dict[str, str]:
    """Return the current commit plus layered content identities."""

    return {
        "lead_dbs_git_commit": validation.lead_dbs_git_commit,
        "code_hash": validation.code_hash,
        "preparation_code_hash": validation.preparation_code_hash,
        "tracking_code_hash": validation.tracking_code_hash,
        "publication_code_hash": validation.publication_code_hash,
    }


@contextmanager
def _subject_lock(work_root: Path) -> Iterator[None]:
    work_root.mkdir(parents=True, exist_ok=True)
    lock_path = work_root / "run.lock"
    with lock_path.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublicationError(
                f"another mrtrix-seed-target process owns {lock_path}"
            ) from exc
        stream.seek(0)
        stream.truncate()
        stream.write(f"pid={os.getpid()}\n")
        stream.flush()
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def validate_batch(path: Path | str) -> ValidationBundle:
    """Read and validate the complete batch without creating outputs."""

    return validate_config(path)


def _process_subject(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
    resources: ResourcePool,
    repo_root: Path,
    progress: ProgressCallback,
) -> dict[str, Any]:
    work_root = subject.output_root / "work"
    with _subject_lock(work_root):
        config_record = work_root / "configs" / f"{validation.config.configuration_hash}.json"
        if not config_record.exists():
            atomic_write_json(config_record, _thaw(validation.config.resolved_mapping))
        progress(f"[{subject.subject_id}] preparing DWI, FOD, and native-grid ROIs")
        with resources.reserve(
            validation.config.execution.preparation_threads_per_subject,
            validation.config.execution.preparation_memory_reservation_gb,
            label=f"{subject.subject_id}/preparation",
        ) as lease:
            preparation, preparation_action = prepare_subject(
                validation,
                subject,
                repo_root,
                memory_observer=lease.observe_memory_gb,
            )
        progress(f"[{subject.subject_id}] preparation {preparation_action}")

        seed_results: dict[str, Mapping[str, Any]] = {}
        errors: dict[str, str] = {}

        def run_one(seed):
            progress(f"[{subject.subject_id} {seed.key}] seed-wide generation started")
            with resources.reserve(
                validation.config.execution.mrtrix_threads_per_seedwide_job,
                validation.config.execution.seedwide_memory_reservation_gb,
                label=f"{subject.subject_id}/{seed.key}",
            ) as lease:
                result = run_seedwide(
                    config=validation.config,
                    subject_id=subject.subject_id,
                    seed=seed,
                    preparation=preparation,
                    tools=validation.tools,
                    code_hash=validation.tracking_code_hash,
                    work_root=work_root,
                    memory_observer=lease.observe_memory_gb,
                )
            progress(
                f"[{subject.subject_id} {seed.key}] {result['action']}: "
                f"{result['total_streamlines']} mother streamlines, minimum target "
                f"{result['minimum_target_streamlines']}"
            )
            return result

        with ThreadPoolExecutor(
            max_workers=min(
                validation.config.execution.seedwide_workers_per_subject,
                len(validation.config.atlas.seeds),
            ),
            thread_name_prefix=f"seedwide-{subject.subject_id}",
        ) as executor:
            future_to_seed = {
                executor.submit(run_one, seed): seed
                for seed in validation.config.atlas.seeds
            }
            for future in as_completed(future_to_seed):
                seed = future_to_seed[future]
                try:
                    seed_results[seed.key] = future.result()
                except Exception as exc:
                    errors[seed.key] = f"{type(exc).__name__}: {exc}"
        if errors:
            return {
                "status": "failed",
                "subject_id": subject.subject_id,
                "preparation_action": preparation_action,
                "seed_errors": errors,
            }
        ordered_results = {
            seed.key: seed_results[seed.key] for seed in validation.config.atlas.seeds
        }
        publication = publish_subject(
            config=validation.config,
            subject=subject,
            preparation=preparation,
            seed_results=ordered_results,
            run_provenance=_run_provenance(validation),
        )
        return {
            **publication,
            "preparation_action": preparation_action,
            "seeds": {
                key: {
                    "action": result["action"],
                    "total_streamlines": int(result["total_streamlines"]),
                    "target_hit_counts": [
                        int(value) for value in result["target_hit_counts"]
                    ],
                    "minimum_target_streamlines": int(
                        result["minimum_target_streamlines"]
                    ),
                }
                for key, result in ordered_results.items()
            },
        }


def run_batch(
    path: Path | str,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Validate, execute, and publish every configured subject."""

    reset_stop_request()
    emit = progress or _default_progress
    emit("Validating the complete YAML batch before creating outputs")
    validation = validate_config(path)
    emit(
        f"Validation complete: {len(validation.subjects)} subjects, "
        f"{len(validation.config.atlas.seeds)} seeds"
    )
    resources = ResourcePool(
        validation.config.execution.cpu_budget,
        validation.config.execution.memory_dispatch_capacity_gb,
    )
    repo_root = Path(__file__).resolve().parents[4]
    results_by_id: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(
        max_workers=validation.config.execution.subject_workers,
        thread_name_prefix="mrtrix-subject",
    ) as executor:
        futures = {
            executor.submit(
                _process_subject,
                validation,
                subject,
                resources,
                repo_root,
                emit,
            ): subject
            for subject in validation.subjects
        }
        for future in as_completed(futures):
            subject = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "status": "failed",
                    "subject_id": subject.subject_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            results_by_id[subject.subject_id] = result
            emit(f"[{subject.subject_id}] terminal status: {result['status']}")
    ordered = [results_by_id[subject.subject_id] for subject in validation.subjects]
    failed = [result for result in ordered if result["status"] not in {"complete"}]
    return {
        "status": "complete" if not failed else "partial_failure",
        "configuration_hash": validation.config.configuration_hash,
        "run_provenance": _run_provenance(validation),
        "subjects": ordered,
        "completed_subjects": len(ordered) - len(failed),
        "failed_subjects": len(failed),
        "resource_usage": resources.report(),
        "warnings": list(validation.warnings),
    }


def status_batch(path: Path | str) -> dict[str, Any]:
    """Inspect current public state without starting MATLAB or tractography."""

    config = load_config(path)
    tckinfo = (
        config.execution.mrtrix_path_prefix / "tckinfo"
        if config.execution.mrtrix_path_prefix is not None
        else Path("tckinfo")
    )
    subjects: list[dict[str, Any]] = []
    for subject_config in config.subjects:
        output_root = (
            subject_config.subject_dir
            / "connectomics"
            / "dMRI"
            / "mrtrix_seed_target"
        )
        state_path = output_root / "work" / "state.json"
        state = read_json(state_path, default={})
        if not state:
            subjects.append(
                {
                    "subject_id": subject_config.subject_id,
                    "status": "not_run",
                    "output_root": str(output_root),
                }
            )
            continue
        if state.get("owner") != OWNER:
            subjects.append(
                {
                    "subject_id": subject_config.subject_id,
                    "status": "unknown_state_owner",
                    "state_path": str(state_path),
                }
            )
            continue
        artifact_errors: list[str] = []
        for artifact in state.get("published_artifacts", []):
            artifact_path = Path(artifact["path"])
            try:
                if file_sha256(artifact_path) != artifact["sha256"]:
                    artifact_errors.append(f"hash mismatch: {artifact_path}")
                    continue
                validate_tck(
                    artifact_path,
                    tckinfo,
                    expected_count=int(artifact["streamline_count"]),
                )
            except Exception as exc:
                artifact_errors.append(f"{artifact_path}: {exc}")
        status = state.get("status", "unknown")
        if artifact_errors and status == "complete":
            status = "artifact_error"
        subjects.append(
            {
                "subject_id": subject_config.subject_id,
                "status": status,
                "output_root": str(output_root),
                "configuration_hash": state.get("configuration_hash"),
                "run_provenance": state.get("run_provenance", {}),
                "seed_results": state.get("seed_results", {}),
                "artifact_count": len(state.get("published_artifacts", [])),
                "artifact_errors": artifact_errors,
                "cleanup_pending": state.get("cleanup_pending", []),
            }
        )
    valid_statuses = {"complete"}
    return {
        "status": (
            "complete"
            if all(subject["status"] in valid_statuses for subject in subjects)
            else "incomplete"
        ),
        "configuration_hash": config.configuration_hash,
        "subjects": subjects,
    }
