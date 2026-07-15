"""Single application API shared by CLI, tests, and future transports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ..cache import ArtifactStore, ContentAddressedCache
from ..catalog import CatalogStatus, EndpointRecord, build_endpoint_catalog
from ..config import (
    ConfigurationError,
    ResolvedWorkflow,
    WorkflowOverrides,
    load_workflow,
    validate_study_compatibility,
)
from ..contracts import StudyBaseRecord, load_study_base
from ..reporting import build_report_documents
from ..workflow import (
    ConfigurationSource,
    ExecutionContext,
    ExecutionPlan,
    RunIdentity,
    RunResult,
    RunStore,
    RunStoreError,
    ServiceRegistry,
    build_default_registry,
    compile_execution_plan,
    execute_plan,
    plan_hash,
)


class ApplicationError(RuntimeError):
    """Raised when an application-level request cannot be completed."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class WorkflowRequest:
    """Explicit project input and profile paths for validate, plan, or run."""

    study_base: Path
    direct_voxel_model: Path
    normative_fiber_model: Path
    workflow_profile: Path
    overrides: WorkflowOverrides

    def __post_init__(self) -> None:
        for field in (
            "study_base",
            "direct_voxel_model",
            "normative_fiber_model",
            "workflow_profile",
        ):
            value = Path(getattr(self, field)).expanduser().resolve()
            if not value.is_file():
                raise ApplicationError(f"{field} does not exist: {value}")
            object.__setattr__(self, field, value)
        if not isinstance(self.overrides, WorkflowOverrides):
            raise ApplicationError("overrides must be WorkflowOverrides")


@dataclass(frozen=True)
class ValidatedWorkflow:
    """Validated study, profiles, and endpoint catalog."""

    request: WorkflowRequest
    study: StudyBaseRecord
    configuration: ResolvedWorkflow
    catalog: tuple[EndpointRecord, ...]


@dataclass(frozen=True)
class ValidationSummary:
    """Small JSON-safe validation result."""

    study_id: str
    study_base_sha256: str
    configuration_hash: str
    scientific_configuration_hash: str
    selected_scales: tuple[str, ...]
    endpoint_count: int
    available_endpoint_count: int

    def as_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class PlanBundle:
    """Validated inputs plus their compiled, non-executed DAG."""

    validated: ValidatedWorkflow
    plan: ExecutionPlan

    def as_dict(self) -> dict[str, Any]:
        return {
            "validation": WorkflowService.validation_summary(self.validated).as_dict(),
            "through": self.plan.through,
            "task_count": len(self.plan.tasks),
            "tasks": [_plain(task) for task in self.plan.tasks],
        }


class WorkflowService:
    """Own validation, planning, execution, status, and artifact discovery."""

    def __init__(
        self,
        registry: ServiceRegistry | None = None,
        *,
        provider: object | None = None,
        code_root: Path | None = None,
    ) -> None:
        if registry is not None and not isinstance(registry, ServiceRegistry):
            raise TypeError("registry must be a ServiceRegistry or None")
        self.registry = registry
        self.provider = provider
        self.code_root = (code_root or Path(__file__).resolve().parents[1]).resolve()

    def validate(self, request: WorkflowRequest) -> ValidationSummary:
        return self.validation_summary(self._load(request))

    def plan(self, request: WorkflowRequest) -> PlanBundle:
        validated = self._load(request)
        return PlanBundle(
            validated=validated,
            plan=compile_execution_plan(validated.configuration, validated.catalog),
        )

    def run(self, request: WorkflowRequest, *, run_id: str | None = None) -> RunResult:
        bundle = self.plan(request)
        validated = bundle.validated
        configuration = validated.configuration
        execution = configuration.workflow.execution
        requested_run_id = run_id or f"{_utc_stamp()}_{configuration.configuration_hash[:10]}"
        if not requested_run_id.strip() or "/" in requested_run_id or "\\" in requested_run_id:
            raise ApplicationError("run_id must be a nonempty path-safe token")
        if execution.resume and run_id is None:
            raise ApplicationError("resume requires an explicit run_id")

        run_parent = configuration.workflow.storage.run_root / validated.study.study_id
        run_parent.mkdir(parents=True, exist_ok=True)
        target = run_parent / requested_run_id
        parent_run_id: str | None = None
        effective_run_id = requested_run_id
        if target.exists() and execution.force:
            parent_run_id = requested_run_id
            effective_run_id = self._force_run_id(run_parent, requested_run_id)
            target = run_parent / effective_run_id

        identity = RunIdentity(
            study_id=validated.study.study_id,
            run_id=effective_run_id,
            study_base_sha256=validated.study.source_sha256,
            code_identity=self._code_identity(),
            configuration_hash=configuration.configuration_hash,
            scientific_configuration_hash=configuration.scientific_configuration_hash,
            plan_hash=plan_hash(bundle.plan),
            parent_run_id=parent_run_id,
        )
        snapshot = self._resolved_snapshot(validated)
        sources = self._configuration_sources(validated)
        output_root = configuration.direct_voxel.output.root
        cache_root = configuration.workflow.storage.cache_root
        output_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        store = RunStore.open(
            target,
            identity,
            resolved_configuration=snapshot,
            configuration_sources=sources,
            allowed_artifact_roots=(output_root, cache_root),
            resume=execution.resume,
        )
        result: RunResult | None = None
        failure: Exception | None = None
        final_status = "failed"
        try:
            artifact_store = ArtifactStore((store.root, output_root, cache_root))
            scientific_cache = ContentAddressedCache(cache_root)
            registry = (
                self.registry if self.registry is not None else self._default_registry()
            )
            provider = (
                self.provider
                if self.provider is not None
                else self._default_provider(
                    validated,
                    work_root=store.root / "runtime_work",
                    artifact_store=artifact_store,
                )
            )
            endpoint_facts = {
                endpoint.endpoint_id: {
                    "catalog_data_available": endpoint.status
                    == CatalogStatus.DATA_AVAILABLE,
                }
                for endpoint in validated.catalog
            }
            context = ExecutionContext(
                run_store=store,
                registry=registry,
                provider=provider,
                endpoint_facts=endpoint_facts,
                allow_expensive_producers=(
                    configuration.workflow.execution.allow_expensive_producers
                ),
                continue_on_endpoint_failure=(
                    configuration.workflow.execution.continue_on_endpoint_failure
                ),
                workers=configuration.workflow.execution.workers,
                artifact_store=artifact_store,
                scientific_cache=scientific_cache,
                resume=execution.resume,
            )
            result = execute_plan(bundle.plan, context)
            typed_records = self._typed_records(result)
            documents = build_report_documents(
                bundle.plan,
                validated.catalog,
                result,
                typed_records,
            )
            self._publish_reporting_documents(
                store.root,
                documents,
                through=bundle.plan.through,
            )
            final_status = "completed" if result.exit_code == 0 else "failed"
        except Exception as exc:  # Finalization must also close failed aggregation runs.
            failure = exc

        try:
            store.finalize(final_status)
        except Exception as exc:
            if failure is None:
                failure = exc
            else:
                failure = ApplicationError(
                    "run orchestration failed before finalization "
                    f"({failure}); finalization also failed ({exc})"
                )

        if failure is not None:
            if isinstance(failure, ApplicationError):
                raise failure
            raise ApplicationError(f"run orchestration failed: {failure}") from failure
        if result is None:  # Defensive: the success path always assigns a RunResult.
            raise ApplicationError("run orchestration completed without a RunResult")
        return result

    def status(self, run_root: Path) -> dict[str, Any]:
        root = self._exact_run_root(run_root)
        manifest = json.loads((root / RunStore.MANIFEST_NAME).read_text(encoding="utf-8"))
        tasks = tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "tasks").glob("task_*.json"))
        )
        return {"run_manifest": manifest, "tasks": tasks}

    def artifacts(self, run_root: Path) -> dict[str, Any]:
        root = self._exact_run_root(run_root)
        path = root / "artifact_index.json"
        if not path.is_file():
            raise ApplicationError(f"artifact index is missing from exact run root: {root}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _default_registry() -> ServiceRegistry:
        """Build the production registry without importing it during validation."""

        try:
            registry = build_default_registry()
        except (ImportError, AttributeError) as exc:
            raise ApplicationError(
                "the production dual-frequency service registry is unavailable"
            ) from exc
        if not isinstance(registry, ServiceRegistry):
            raise ApplicationError(
                "build_default_registry must return a ServiceRegistry"
            )
        return registry

    @staticmethod
    def _default_provider(
        validated: ValidatedWorkflow,
        *,
        work_root: Path,
        artifact_store: ArtifactStore,
    ) -> object:
        """Construct the production provider from validated current-run inputs."""

        try:
            from ..runtime.input_provider import StudyRuntimeInputProvider
        except ImportError as exc:
            raise ApplicationError(
                "the production dual-frequency input provider is unavailable"
            ) from exc
        return StudyRuntimeInputProvider(
            validated.study,
            validated.configuration,
            validated.catalog,
            work_root=work_root,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _typed_records(result: RunResult) -> dict[str, object]:
        """Restore exactly one typed root for every completed task."""

        records: dict[str, object] = {}
        for outcome in result.outcomes:
            if outcome.status != "completed":
                continue
            if outcome.result is None:
                raise ApplicationError(
                    f"completed task {outcome.task_id!r} has no service result"
                )
            if outcome.task_id in records:
                raise ApplicationError(
                    f"duplicate completed task outcome {outcome.task_id!r}"
                )
            records[outcome.task_id] = outcome.result.decode_record()
        return records

    @staticmethod
    def _publish_reporting_documents(
        run_root: Path,
        documents: Mapping[str, Mapping[str, Any]],
        *,
        through: str,
    ) -> None:
        """Stage complete reporting documents and atomically replace each target."""

        required = {"final_decisions.json", "artifact_index.json"}
        if through == "report":
            required.update({"endpoint_summary.json", "run_report.json"})
        actual = set(documents)
        if actual != required:
            raise ApplicationError(
                "reporting document set does not match the execution cutoff; "
                f"expected={sorted(required)}, actual={sorted(actual)}"
            )

        root = Path(run_root).resolve()
        staging = Path(tempfile.mkdtemp(prefix=".reporting-stage-", dir=root))
        backup_root = staging / "backups"
        backup_root.mkdir()
        previous: dict[str, bool] = {}
        published: list[str] = []
        try:
            for name in sorted(required):
                document = documents[name]
                if not isinstance(document, Mapping):
                    raise ApplicationError(f"reporting document {name!r} must be a mapping")
                text = json.dumps(
                    dict(document),
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                ) + "\n"
                staged = staging / name
                with staged.open("w", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())

                target = root / name
                previous[name] = target.is_file()
                if previous[name]:
                    shutil.copy2(target, backup_root / name)

            for name in sorted(required):
                os.replace(staging / name, root / name)
                published.append(name)
        except Exception:
            for name in reversed(published):
                target = root / name
                backup = backup_root / name
                if previous.get(name, False) and backup.is_file():
                    os.replace(backup, target)
                elif target.exists():
                    target.unlink()
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _load(self, request: WorkflowRequest) -> ValidatedWorkflow:
        try:
            study = load_study_base(request.study_base)
            configuration = load_workflow(request.workflow_profile, request.overrides)
            if configuration.workflow.direct_voxel_model_path != request.direct_voxel_model:
                raise ApplicationError(
                    "explicit direct-voxel model path differs from workflow profile reference"
                )
            if configuration.workflow.normative_fiber_model_path != request.normative_fiber_model:
                raise ApplicationError(
                    "explicit normative-fiber model path differs from workflow profile reference"
                )
            validate_study_compatibility(study, configuration)
            catalog = build_endpoint_catalog(configuration, study)
        except (ConfigurationError, ValueError, OSError) as exc:
            if isinstance(exc, ApplicationError):
                raise
            raise ApplicationError(str(exc)) from exc
        return ValidatedWorkflow(request, study, configuration, catalog)

    @staticmethod
    def validation_summary(validated: ValidatedWorkflow) -> ValidationSummary:
        return ValidationSummary(
            study_id=validated.study.study_id,
            study_base_sha256=validated.study.source_sha256,
            configuration_hash=validated.configuration.configuration_hash,
            scientific_configuration_hash=validated.configuration.scientific_configuration_hash,
            selected_scales=validated.configuration.selected_scales,
            endpoint_count=len(validated.catalog),
            available_endpoint_count=sum(
                endpoint.status == CatalogStatus.DATA_AVAILABLE
                for endpoint in validated.catalog
            ),
        )

    def _code_identity(self) -> str:
        hasher = hashlib.sha256()
        for path in sorted(self.code_root.rglob("*.py")):
            hasher.update(path.relative_to(self.code_root).as_posix().encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(path.read_bytes())
            hasher.update(b"\0")
        return f"sha256:{hasher.hexdigest()}"

    @staticmethod
    def _configuration_sources(validated: ValidatedWorkflow) -> tuple[ConfigurationSource, ...]:
        paths = (validated.request.study_base, *validated.configuration.source_paths)
        return tuple(
            ConfigurationSource(path.as_uri(), _sha256_file(path))
            for path in paths
        )

    @staticmethod
    def _resolved_snapshot(validated: ValidatedWorkflow) -> dict[str, Any]:
        configuration = validated.configuration
        execution = configuration.workflow.execution
        return {
            "schema_version": "dual_frequency_resolved_configuration_v1",
            "study": {
                "study_id": validated.study.study_id,
                "study_base_sha256": validated.study.source_sha256,
                "selected_scales": list(configuration.selected_scales),
            },
            "direct_voxel": _plain(configuration.direct_voxel),
            "normative_fiber": _plain(configuration.normative_fiber),
            "selection": {
                "models": list(configuration.selected_models),
                "connectomes": list(configuration.selected_connectomes),
            },
            "execution": {
                "through": execution.through,
                "continue_on_endpoint_failure": execution.continue_on_endpoint_failure,
                "allow_expensive_producers": execution.allow_expensive_producers,
                "workers": execution.workers,
            },
            "storage": _plain(configuration.workflow.storage),
            "configuration_hash": configuration.configuration_hash,
            "scientific_configuration_hash": configuration.scientific_configuration_hash,
        }

    @staticmethod
    def _force_run_id(parent: Path, requested_run_id: str) -> str:
        base = f"{requested_run_id}-force-{_utc_stamp()}"
        candidate = base
        suffix = 1
        while (parent / candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    @staticmethod
    def _exact_run_root(run_root: Path) -> Path:
        supplied = Path(run_root).expanduser()
        if supplied.is_symlink():
            raise ApplicationError("run_root must be an exact physical directory, not a symlink")
        try:
            root = supplied.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError(f"run_root does not exist: {supplied}") from exc
        manifest_path = root / RunStore.MANIFEST_NAME
        if not root.is_dir() or not manifest_path.is_file():
            raise ApplicationError(f"path is not an exact dual-frequency run root: {root}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("run_id") != root.name:
            raise ApplicationError("run_root basename does not match manifest run_id")
        return root
