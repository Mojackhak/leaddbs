"""Single application API shared by CLI, tests, and future transports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

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
from ..reporting import (
    build_formal_in_sample_results,
    build_report_documents,
    formal_in_sample_results_csv,
)
from ..workflow import (
    ConfigurationSource,
    ExecutionContext,
    ExecutionPlan,
    RunIdentity,
    RunResult,
    RunStore,
    RunStoreError,
    ServiceRegistry,
    SpawnWorkerSpec,
    build_default_registry,
    compile_execution_plan,
    execute_plan,
    plan_hash,
)
from .sensitivity import (
    SensitivityCheckpointError,
    compile_sensitivity_extension_plan,
    load_sensitivity_checkpoint,
    parent_manifest_sha256,
    publish_sensitivity_checkpoints,
    write_csv_snapshots,
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
class SensitivityExtensionRequest:
    """One immutable request to extend an existing final-model checkpoint."""

    base_run: Path
    analyses: tuple[str, ...]
    run_id: str
    workers: int
    allow_expensive_producers: bool = False
    resume: bool = False
    rebuild_request: WorkflowRequest | None = None
    rebuild_run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_run", Path(self.base_run).expanduser())
        analyses = tuple(dict.fromkeys(str(item).strip().lower() for item in self.analyses))
        allowed = {"jitter", "oss", "final_in_sample"}
        if not analyses or any(item not in allowed for item in analyses):
            raise ApplicationError(
                "analyses must select jitter, oss, final_in_sample, or a combination"
            )
        object.__setattr__(self, "analyses", analyses)
        run_id = str(self.run_id).strip()
        if not run_id or "/" in run_id or "\\" in run_id:
            raise ApplicationError("extension run_id must be a nonempty path-safe token")
        object.__setattr__(self, "run_id", run_id)
        if type(self.workers) is not int or self.workers < 1:
            raise ApplicationError("extension workers must be a positive integer")
        if type(self.allow_expensive_producers) is not bool or type(self.resume) is not bool:
            raise ApplicationError("extension flags must be boolean")
        if self.rebuild_request is not None and not isinstance(
            self.rebuild_request,
            WorkflowRequest,
        ):
            raise ApplicationError("rebuild_request must be a WorkflowRequest or None")
        if self.rebuild_run_id is not None:
            rebuild_run_id = str(self.rebuild_run_id).strip()
            if not rebuild_run_id or "/" in rebuild_run_id or "\\" in rebuild_run_id:
                raise ApplicationError("rebuild_run_id must be a path-safe token")
            object.__setattr__(self, "rebuild_run_id", rebuild_run_id)


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
        self._publish_input_bundle(store.root, validated)
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
                    scientific_cache=scientific_cache,
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
                spawn_worker_spec=(
                    SpawnWorkerSpec(
                        study=validated.study,
                        configuration=configuration,
                        catalog=validated.catalog,
                        work_root=store.root / "runtime_work",
                        artifact_roots=(store.root, output_root, cache_root),
                        cache_root=cache_root,
                    )
                    if self.registry is None and self.provider is None
                    else None
                ),
            )
            result = execute_plan(bundle.plan, context)
            typed_records = self._typed_records(result)
            documents = build_report_documents(
                bundle.plan,
                validated.catalog,
                result,
                typed_records,
            )
            publish_sensitivity_checkpoints(
                run_root=store.root,
                plan=bundle.plan,
                outcomes=result.outcomes,
                typed_records=typed_records,
                run_id=store.run_id,
                study_id=validated.study.study_id,
                model_set_ids={
                    "direct_voxel": configuration.direct_voxel.model_set_id,
                    "normative_fiber": configuration.normative_fiber.model_set_id,
                },
                cache_root=cache_root,
                output_root=output_root,
                source_identities=tuple(
                    {"uri": source.uri, "sha256": source.sha256}
                    for source in sources
                ),
                rng_profiles={
                    "direct_voxel": _plain(
                        configuration.direct_voxel.formal_resampling
                    ),
                    "normative_fiber": _plain(
                        configuration.normative_fiber.formal_resampling
                    ),
                },
            )
            self._publish_reporting_documents(
                store.root,
                documents,
                through=bundle.plan.through,
            )
            self._publish_formal_in_sample_results(
                store.root / "formal_results",
                typed_records,
                artifact_store,
                basename="paired_formal_results",
            )
            write_csv_snapshots(
                store.root,
                result.outcomes,
                documents["artifact_index.json"],
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

    def sensitivity(self, request: SensitivityExtensionRequest) -> RunResult:
        """Run selected final-linked analyses without mutating or rerunning the parent."""

        if not isinstance(request, SensitivityExtensionRequest):
            raise ApplicationError("request must be a SensitivityExtensionRequest")
        try:
            base_root = self._exact_run_root(request.base_run)
            workflow_request = self._extension_workflow_request(base_root, request)
            bundle = self.plan(workflow_request)
        except ApplicationError:
            if request.rebuild_request is None:
                raise
            rebuilt = self._rebuild_sensitivity_parent(request)
            return self.sensitivity(
                replace(request, base_run=rebuilt, rebuild_request=None)
            )
        validated = bundle.validated
        configuration = validated.configuration
        output_root = configuration.direct_voxel.output.root
        cache_root = configuration.workflow.storage.cache_root
        try:
            checkpoint = load_sensitivity_checkpoint(
                base_root,
                cache_root=cache_root,
                output_root=output_root,
            )
            if checkpoint.parent_manifest.get("study_id") != validated.study.study_id:
                raise SensitivityCheckpointError("base run study identity changed")
            if (
                checkpoint.parent_manifest.get("scientific_configuration_hash")
                != configuration.scientific_configuration_hash
            ):
                raise SensitivityCheckpointError(
                    "base run scientific configuration changed"
                )
            extension_plan = compile_sensitivity_extension_plan(
                bundle.plan,
                endpoint_ids=checkpoint.endpoint_ids,
                analyses=request.analyses,
                seed_task_ids=checkpoint.seed_task_ids,
                jitter_bases=(
                    checkpoint.bases
                    if self.provider is None
                    or callable(
                        getattr(
                            self.provider,
                            "build_jitter_physical_block",
                            None,
                        )
                    )
                    else None
                ),
            )
            checkpoint_root_ids = tuple(
                task.task_id for task in extension_plan.tasks if task.checkpoint_only
            )
            seed_outcomes = checkpoint.seed_outcomes_for(checkpoint_root_ids)
        except SensitivityCheckpointError as exc:
            if request.rebuild_request is not None:
                rebuilt = self._rebuild_sensitivity_parent(request)
                return self.sensitivity(
                    replace(request, base_run=rebuilt, rebuild_request=None)
                )
            raise ApplicationError(str(exc)) from exc

        target = (
            configuration.workflow.storage.run_root
            / validated.study.study_id
            / request.run_id
        )
        identity = RunIdentity(
            study_id=validated.study.study_id,
            run_id=request.run_id,
            study_base_sha256=validated.study.source_sha256,
            code_identity=self._code_identity(),
            configuration_hash=configuration.configuration_hash,
            scientific_configuration_hash=configuration.scientific_configuration_hash,
            plan_hash=plan_hash(extension_plan),
            parent_run_id=str(checkpoint.parent_manifest["run_id"]),
        )
        snapshot = self._resolved_snapshot(validated)
        sources = self._configuration_sources(validated)
        output_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        store = RunStore.open(
            target,
            identity,
            resolved_configuration=snapshot,
            configuration_sources=sources,
            allowed_artifact_roots=(output_root, cache_root, base_root),
            resume=request.resume,
        )
        annotations: dict[str, object] = {
            "run_type": "sensitivity_extension",
            "selected_sensitivity_analyses": list(request.analyses),
        }
        current_manifest = json.loads(
            (store.root / RunStore.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        if "resource_settings" not in current_manifest:
            annotations["resource_settings"] = {"workers": request.workers}
        store.annotate_manifest(annotations)
        base_reference = {
            "schema_version": "dual_frequency_base_run_reference_v1",
            "base_run_id": checkpoint.parent_manifest["run_id"],
            "base_run_path": str(base_root),
            "base_run_manifest_sha256": parent_manifest_sha256(base_root),
            "scientific_configuration_hash": configuration.scientific_configuration_hash,
            "checkpoint_endpoint_ids": list(checkpoint.endpoint_ids),
        }
        self._write_immutable_json(store.root / "base_run_reference.json", base_reference)
        persisted_extension_plan = _plain(extension_plan)
        persisted_extension_plan.pop("configuration_hash", None)
        self._write_immutable_json(
            store.root / "sensitivity_plan.json",
            {
                "schema_version": "dual_frequency_sensitivity_plan_v1",
                "analyses": list(request.analyses),
                "plan": persisted_extension_plan,
            },
        )
        for outcome in seed_outcomes:
            store.write_task_state(outcome.task_id, outcome.as_dict())

        result: RunResult | None = None
        failure: Exception | None = None
        final_status = "failed"
        try:
            artifact_store = ArtifactStore((store.root, base_root, output_root, cache_root))
            scientific_cache = ContentAddressedCache(cache_root)
            registry = self.registry if self.registry is not None else self._default_registry()
            provider = (
                self.provider
                if self.provider is not None
                else self._default_provider(
                    validated,
                    work_root=store.root / "runtime_work",
                    artifact_store=artifact_store,
                    scientific_cache=scientific_cache,
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
                allow_expensive_producers=request.allow_expensive_producers,
                continue_on_endpoint_failure=(
                    configuration.workflow.execution.continue_on_endpoint_failure
                ),
                workers=request.workers,
                artifact_store=artifact_store,
                scientific_cache=scientific_cache,
                resume=True,
                spawn_worker_spec=(
                    SpawnWorkerSpec(
                        study=validated.study,
                        configuration=configuration,
                        catalog=validated.catalog,
                        work_root=store.root / "runtime_work",
                        artifact_roots=(store.root, base_root, output_root, cache_root),
                        cache_root=cache_root,
                    )
                    if self.registry is None and self.provider is None
                    else None
                ),
            )
            result = execute_plan(extension_plan, context)
            typed_records = self._typed_records(result)
            endpoint_ids = {task.endpoint_id for task in extension_plan.tasks}
            selected_catalog = tuple(
                endpoint
                for endpoint in validated.catalog
                if endpoint.endpoint_id in endpoint_ids
            )
            documents = build_report_documents(
                extension_plan,
                selected_catalog,
                result,
                typed_records,
                external_causal_task_ids=checkpoint.seed_task_ids,
            )
            self._publish_reporting_documents(
                store.root,
                documents,
                through=extension_plan.through,
            )
            self._publish_formal_in_sample_results(
                store.root / "sensitivity_results",
                typed_records,
                artifact_store,
                basename="final_in_sample_results",
            )
            write_csv_snapshots(
                store.root,
                result.outcomes,
                documents["artifact_index.json"],
            )
            self._publish_extension_results(
                validated,
                request,
                checkpoint.parent_manifest,
                extension_plan,
                result,
                documents["artifact_index.json"],
            )
            final_status = "completed" if result.exit_code == 0 else "failed"
        except Exception as exc:
            failure = exc

        try:
            store.finalize(final_status)
        except Exception as exc:
            failure = exc if failure is None else ApplicationError(
                f"sensitivity extension failed ({failure}); finalization also failed ({exc})"
            )
        if failure is not None:
            if isinstance(failure, ApplicationError):
                raise failure
            raise ApplicationError(f"sensitivity extension failed: {failure}") from failure
        if result is None:
            raise ApplicationError("sensitivity extension completed without a result")
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
        scientific_cache: ContentAddressedCache | None = None,
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
            scientific_cache=scientific_cache,
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
    def _publish_input_bundle(run_root: Path, validated: ValidatedWorkflow) -> None:
        """Copy the small configuration authority needed to reopen a copied run."""

        sources = {
            "study_base": validated.request.study_base,
            "workflow_profile": validated.request.workflow_profile,
            "direct_voxel_model": validated.request.direct_voxel_model,
            "normative_fiber_model": validated.request.normative_fiber_model,
        }
        root = Path(run_root).resolve() / "inputs"
        root.mkdir(parents=True, exist_ok=True)
        names = [path.name for path in sources.values()]
        if len(set(names)) != len(names):
            raise ApplicationError("portable input bundle filenames must be unique")
        entries: dict[str, dict[str, str]] = {}
        for role, source in sources.items():
            target = root / source.name
            content = source.read_bytes()
            if target.exists():
                if not target.is_file() or target.read_bytes() != content:
                    raise ApplicationError(
                        f"portable input bundle conflicts with existing file: {target}"
                    )
            else:
                descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=root)
                temporary = Path(name)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            entries[role] = {
                "relative_path": target.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(target),
            }
        manifest = {
            "schema_version": "dual_frequency_input_bundle_v1",
            "files": entries,
        }
        path = root / "input_bundle.json"
        text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ApplicationError("portable input bundle manifest changed during resume")
        else:
            path.write_text(text, encoding="utf-8")

    @staticmethod
    def _extension_workflow_request(
        base_run: Path,
        request: SensitivityExtensionRequest,
    ) -> WorkflowRequest:
        bundle_path = base_run / "inputs" / "input_bundle.json"
        snapshot_path = base_run / "configuration_resolved.yaml"
        if not bundle_path.is_file() or not snapshot_path.is_file():
            raise ApplicationError(
                "base run lacks its portable input bundle; rebuild a new parent lineage"
            )
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            snapshot = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ApplicationError("base run input authority is unreadable") from exc
        if bundle.get("schema_version") != "dual_frequency_input_bundle_v1":
            raise ApplicationError("base run input bundle schema is unsupported")
        files = bundle.get("files")
        if not isinstance(files, dict):
            raise ApplicationError("base run input bundle files are invalid")

        def bundled(role: str) -> Path:
            item = files.get(role)
            if not isinstance(item, dict) or set(item) != {"relative_path", "sha256"}:
                raise ApplicationError(f"base run input bundle lacks {role}")
            path = (base_run / str(item["relative_path"])).resolve()
            if base_run not in path.parents or not path.is_file():
                raise ApplicationError(f"base run input bundle path is unsafe for {role}")
            if _sha256_file(path) != item["sha256"]:
                raise ApplicationError(f"base run input bundle failed SHA-256 for {role}")
            return path

        try:
            selected_scales = tuple(snapshot["study"]["selected_scales"])
            selected_models = tuple(snapshot["selection"]["models"])
            selected_connectomes = tuple(snapshot["selection"]["connectomes"])
        except (KeyError, TypeError) as exc:
            raise ApplicationError("base run resolved selection is incomplete") from exc
        overrides = WorkflowOverrides(
            scales=selected_scales,
            all_available=False,
            models=selected_models,
            connectomes=selected_connectomes,
            through="sensitivity",
            resume=False,
            force=False,
            allow_expensive_producers=request.allow_expensive_producers,
            workers=request.workers,
        )
        return WorkflowRequest(
            study_base=bundled("study_base"),
            direct_voxel_model=bundled("direct_voxel_model"),
            normative_fiber_model=bundled("normative_fiber_model"),
            workflow_profile=bundled("workflow_profile"),
            overrides=overrides,
        )

    def _rebuild_sensitivity_parent(
        self,
        request: SensitivityExtensionRequest,
    ) -> Path:
        source = request.rebuild_request
        if source is None:
            raise ApplicationError("missing or incomplete parent requires explicit rebuild inputs")
        selected = source.overrides
        overrides = WorkflowOverrides(
            scales=selected.scales,
            all_available=selected.all_available,
            models=selected.models,
            connectomes=selected.connectomes,
            through="observed",
            resume=False,
            force=False,
            allow_expensive_producers=False,
            workers=request.workers,
        )
        parent_request = WorkflowRequest(
            study_base=source.study_base,
            direct_voxel_model=source.direct_voxel_model,
            normative_fiber_model=source.normative_fiber_model,
            workflow_profile=source.workflow_profile,
            overrides=overrides,
        )
        validated = self.plan(parent_request).validated
        run_parent = (
            validated.configuration.workflow.storage.run_root
            / validated.study.study_id
        )
        run_id = request.rebuild_run_id or f"{request.run_id}-parent"
        if (run_parent / run_id).exists():
            run_id = self._force_run_id(run_parent, run_id)
        result = self.run(parent_request, run_id=run_id)
        if result.exit_code != 0:
            raise ApplicationError("rebuilt parent did not complete successfully")
        return run_parent / result.run_id

    @staticmethod
    def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
        text = json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
        if path.exists():
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                raise ApplicationError(f"immutable extension document changed: {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _replace_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(dict(payload), stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _replace_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _publish_formal_in_sample_results(
        cls,
        root: Path,
        typed_records: Mapping[str, object],
        artifact_store: ArtifactStore,
        *,
        basename: str,
    ) -> None:
        document = build_formal_in_sample_results(typed_records, artifact_store)
        if document["result_count"] < 1:
            return
        cls._replace_json(root / f"{basename}.json", document)
        cls._replace_text(
            root / f"{basename}.csv",
            formal_in_sample_results_csv(document),
        )

    def _publish_extension_results(
        self,
        validated: ValidatedWorkflow,
        request: SensitivityExtensionRequest,
        parent_manifest: Mapping[str, Any],
        plan: ExecutionPlan,
        result: RunResult,
        artifact_document: Mapping[str, Any],
    ) -> None:
        tasks = {task.task_id: task for task in plan.tasks}
        endpoints = {endpoint.endpoint_id: endpoint for endpoint in validated.catalog}
        stages = {
            "jitter": "spatial_jitter",
            "oss": "activation_sensitivity",
            "final_in_sample": "formal_in_sample",
        }
        analyses_by_stage = {stage: analysis for analysis, stage in stages.items()}
        selected_stages = {stages[analysis] for analysis in request.analyses}
        rows: list[dict[str, Any]] = []
        for outcome in result.outcomes:
            task = tasks[outcome.task_id]
            if task.phase != "sensitivity" or task.stage not in selected_stages:
                continue
            endpoint = endpoints[task.endpoint_id]
            rows.append(
                {
                    "task_id": task.task_id,
                    "endpoint_id": task.endpoint_id,
                    "scale_id": endpoint.key.scale_id,
                    "model_family": endpoint.key.model_family,
                    "model_role": (
                        "reference"
                        if endpoint.key.model_family.startswith("reference_")
                        else "addon"
                    ),
                    "analysis": analyses_by_stage[task.stage],
                    "status": outcome.status,
                    "reason": outcome.reason,
                    "record_id": (
                        None if outcome.result is None else outcome.result.record_id
                    ),
                    "artifact_ids": (
                        []
                        if outcome.result is None
                        else [artifact.identifier for artifact in outcome.result.artifacts]
                    ),
                }
            )
        extension_document = {
            "schema_version": "dual_frequency_extension_results_v1",
            "extension_id": request.run_id,
            "parent_run_id": parent_manifest["run_id"],
            "analyses": list(request.analyses),
            "status": "completed" if result.exit_code == 0 else "failed",
            "results": sorted(rows, key=lambda item: item["task_id"]),
        }
        self._replace_json(
            validated.configuration.workflow.storage.run_root
            / validated.study.study_id
            / request.run_id
            / "sensitivity_results"
            / "extension_results.json",
            extension_document,
        )

        domains = {
            "direct_voxel": validated.configuration.direct_voxel,
            "normative_fiber": validated.configuration.normative_fiber,
        }
        for model_type, profile in domains.items():
            suffix = "voxel" if model_type == "direct_voxel" else "fiber"
            domain_rows = [
                row for row in rows if str(row["model_family"]).endswith(suffix)
            ]
            if not domain_rows:
                continue
            root = (
                profile.output.root
                / model_type
                / profile.model_set_id
                / "extensions"
                / request.run_id
            )
            existing_manifest = root / "extension_manifest.json"
            if existing_manifest.is_file():
                existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
                if (
                    existing.get("extension_id") != request.run_id
                    or existing.get("parent_run_id") != parent_manifest["run_id"]
                    or existing.get("analyses") != list(request.analyses)
                ):
                    raise ApplicationError(
                        f"canonical extension path belongs to another identity: {root}"
                    )
            for scale_id in sorted({str(row["scale_id"]) for row in domain_rows}):
                for role in ("reference", "addon"):
                    selected = [
                        row
                        for row in domain_rows
                        if row["scale_id"] == scale_id and row["model_role"] == role
                    ]
                    if selected:
                        self._replace_json(
                            root / scale_id / role / "sensitivity" / "results.json",
                            {
                                "schema_version": "dual_frequency_extension_group_v1",
                                "extension_id": request.run_id,
                                "results": selected,
                            },
                        )
            relevant_task_ids = {str(row["task_id"]) for row in domain_rows}
            filtered_artifacts = []
            for artifact in artifact_document.get("artifacts", []):
                references = [
                    reference
                    for reference in artifact.get("task_references", [])
                    if reference.get("task_id") in relevant_task_ids
                ]
                if references:
                    item = dict(artifact)
                    item["task_references"] = references
                    filtered_artifacts.append(item)
            canonical_artifacts = {
                "schema_version": "dual_frequency_extension_artifact_index_v1",
                "extension_id": request.run_id,
                "artifacts": filtered_artifacts,
            }
            self._replace_json(root / "artifact_index.json", canonical_artifacts)
            write_csv_snapshots(root, (), canonical_artifacts)
            self._replace_json(
                existing_manifest,
                {
                    "schema_version": "dual_frequency_extension_manifest_v1",
                    "extension_id": request.run_id,
                    "parent_run_id": parent_manifest["run_id"],
                    "parent_scientific_configuration_hash": parent_manifest[
                        "scientific_configuration_hash"
                    ],
                    "analyses": list(request.analyses),
                    "workers": request.workers,
                    "status": extension_document["status"],
                },
            )

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
