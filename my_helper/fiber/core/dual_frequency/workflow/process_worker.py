"""Spawn-safe worker runtime for dual-frequency task services."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from ..cache import ArtifactStore, ContentAddressedCache
from ..catalog import EndpointRecord
from ..config import ResolvedWorkflow
from ..contracts import StudyBaseRecord
from ..instrumentation import (
    performance_snapshot,
    write_performance_fragment,
)
from .planner import TaskSpec


@dataclass(frozen=True)
class SpawnWorkerSpec:
    """Small immutable authority used to reconstruct one worker-local runtime."""

    study: StudyBaseRecord
    configuration: ResolvedWorkflow
    catalog: tuple[EndpointRecord, ...]
    work_root: Path
    artifact_roots: tuple[Path, ...]
    cache_root: Path


@dataclass(frozen=True)
class WorkerCommand:
    """Pure-data command containing only one task and direct dependency envelopes."""

    task: TaskSpec
    dependencies: Mapping[str, object]
    run_id: str
    output_dir: Path
    allow_expensive_producers: bool


_REGISTRY = None
_PROVIDER = None
_ARTIFACT_STORE = None
_SCIENTIFIC_CACHE = None
_THREAD_LIMITER = None


def initialize_worker(spec: SpawnWorkerSpec) -> None:
    """Construct process-local services after limiting numerical-library threads."""

    global _REGISTRY, _PROVIDER, _ARTIFACT_STORE, _SCIENTIFIC_CACHE, _THREAD_LIMITER
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            pass
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"
    try:
        from threadpoolctl import threadpool_limits

        _THREAD_LIMITER = threadpool_limits(limits=1)
    except ImportError:
        _THREAD_LIMITER = None

    from ..runtime.input_provider import StudyRuntimeInputProvider
    from .registry import build_default_registry

    worker_root = Path(spec.work_root) / f"worker-{os.getpid()}"
    worker_root.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_STORE = ArtifactStore(spec.artifact_roots)
    _SCIENTIFIC_CACHE = ContentAddressedCache(spec.cache_root)
    _PROVIDER = StudyRuntimeInputProvider(
        spec.study,
        spec.configuration,
        spec.catalog,
        work_root=worker_root,
        artifact_store=_ARTIFACT_STORE,
        scientific_cache=_SCIENTIFIC_CACHE,
    )
    _REGISTRY = build_default_registry()


def execute_worker_command(command: WorkerCommand):
    """Invoke one service without mutating RunStore or the artifact index."""

    if any(
        value is None
        for value in (_REGISTRY, _PROVIDER, _ARTIFACT_STORE, _SCIENTIFIC_CACHE)
    ):
        raise RuntimeError("spawn worker runtime is not initialized")
    from .executor import TaskExecutionRequest, _validate_service_result

    before = performance_snapshot()
    try:
        service = _REGISTRY.resolve(command.task.service_id)
        request = TaskExecutionRequest(
            task=command.task,
            dependencies=command.dependencies,
            run_id=command.run_id,
            output_dir=command.output_dir,
            provider=_PROVIDER,
            artifact_store=_ARTIFACT_STORE,
            scientific_cache=_SCIENTIFIC_CACHE,
            allow_expensive_producers=command.allow_expensive_producers,
            workers=1,
        )
        return _validate_service_result(command.task, service(request))
    finally:
        write_performance_fragment(
            command.output_dir,
            task_id=command.task.task_id,
            before=before,
            after=performance_snapshot(),
        )


__all__ = [
    "SpawnWorkerSpec",
    "WorkerCommand",
    "execute_worker_command",
    "initialize_worker",
]
