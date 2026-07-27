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


_BENCHMARK_OSS_FIXTURE_SCHEMA = (
    "dual_frequency_task17_injected_oss_fixture_v1"
)


def _sha256(value: object, label: str) -> str:
    token = str(value).strip().lower()
    if len(token) != 64 or any(
        character not in "0123456789abcdef" for character in token
    ):
        raise ValueError(f"{label} must be a SHA-256 digest")
    return token


@dataclass(frozen=True)
class BenchmarkOSSInjectedFixtureSpec:
    """Immutable benchmark-only authority for deterministic OSS row injection."""

    schema_version: str
    cache_root: Path
    accepted_closure_sha256: str
    permitted_row_identities: tuple[str, ...]

    def validate(self) -> None:
        """Reject a changed or noncanonical benchmark fixture descriptor."""

        root = Path(self.cache_root).expanduser().resolve()
        identities = tuple(str(value) for value in self.permitted_row_identities)
        if (
            self.schema_version != _BENCHMARK_OSS_FIXTURE_SCHEMA
            or root != self.cache_root
            or not root.is_dir()
            or root.is_symlink()
            or not identities
            or identities != tuple(sorted(identities))
            or len(set(identities)) != len(identities)
        ):
            raise ValueError("benchmark OSS fixture descriptor differs")
        _sha256(
            self.accepted_closure_sha256,
            "accepted OSS fixture closure",
        )
        for identity in identities:
            _sha256(identity, "permitted OSS row identity")


class _BenchmarkOSSInjectedToolchain:
    """Reconstruct deterministic ten-sample evidence from accepted OSS rows."""

    def __init__(self, spec: BenchmarkOSSInjectedFixtureSpec) -> None:
        spec.validate()
        self._cache = ContentAddressedCache(spec.cache_root)
        self._permitted = frozenset(spec.permitted_row_identities)

    def produce_with_evidence(self, request: object):
        """Return exact sample states only for one permitted runtime row."""

        import numpy as np

        from ..backends.activation.ossdbs import (
            OSSRowMaterializer,
            OSSRowProduct,
        )
        from ..backends.activation.ppam import (
            PPAM_LATTICE_ABSOLUTE_TOLERANCE,
        )
        from ..runtime.oss_toolchain import OSSRowExecutionEvidence

        identity = getattr(request, "scientific_identity", None)
        row = getattr(request, "row", None)
        if (
            type(identity) is not str
            or identity not in self._permitted
            or row is None
        ):
            raise ValueError(
                "injected OSS request is outside the benchmark fixture"
            )
        entry = self._cache.resolve_identity("oss_rows", identity)
        if entry is None:
            raise ValueError("accepted injected OSS row is unavailable")
        product = OSSRowMaterializer._validated_row_product(entry, row)
        counts_float = product.probabilities.astype(np.float64) * 10.0
        counts = np.rint(counts_float).astype(np.int64)
        if (
            np.any(counts < 0)
            or np.any(counts > 10)
            or not np.allclose(
                counts_float,
                counts,
                rtol=0.0,
                atol=PPAM_LATTICE_ABSOLUTE_TOLERANCE,
            )
        ):
            raise ValueError(
                "accepted OSS probabilities cannot reconstruct ten samples"
            )
        sample_numbers = np.arange(10, dtype=np.int64)[:, None]
        states = np.where(sample_numbers < counts[None, :], 1, 0).astype(
            np.int8
        )
        injected_product = OSSRowProduct(
            product.feature_ids,
            product.probabilities,
            producer_implementation_attestation=(
                "task17-performance-injected-oss-v1"
            ),
        )
        return OSSRowExecutionEvidence(injected_product, states)


@dataclass(frozen=True)
class SpawnWorkerSpec:
    """Small immutable authority used to reconstruct one worker-local runtime."""

    study: StudyBaseRecord
    configuration: ResolvedWorkflow
    catalog: tuple[EndpointRecord, ...]
    work_root: Path
    artifact_roots: tuple[Path, ...]
    cache_root: Path
    benchmark_oss_fixture: BenchmarkOSSInjectedFixtureSpec | None = None


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
    provider_arguments = {
        "work_root": worker_root,
        "artifact_store": _ARTIFACT_STORE,
        "scientific_cache": _SCIENTIFIC_CACHE,
    }
    if spec.benchmark_oss_fixture is None:
        _PROVIDER = StudyRuntimeInputProvider(
            spec.study,
            spec.configuration,
            spec.catalog,
            **provider_arguments,
        )
    else:
        injected_toolchain = _BenchmarkOSSInjectedToolchain(
            spec.benchmark_oss_fixture
        )

        class _BenchmarkInjectedProvider(StudyRuntimeInputProvider):
            def oss_producer_toolchain(self):
                return injected_toolchain

        _PROVIDER = _BenchmarkInjectedProvider(
            spec.study,
            spec.configuration,
            spec.catalog,
            **provider_arguments,
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
    "BenchmarkOSSInjectedFixtureSpec",
    "SpawnWorkerSpec",
    "WorkerCommand",
    "execute_worker_command",
    "initialize_worker",
]
