"""Production service registry for the configured four-model workflow."""

from __future__ import annotations

import importlib
import json
import math
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from ..executor import RunContext, ServiceRegistry, TaskArtifact
from ..planner import TaskSpec
from ..records import ArtifactRef, FinalArtifactRecord, RecordError, ULFBranchRecord
from ..run_store import sha256_file
from .component_availability import build_run_local_component_availability
from .formal import FormalService
from .legacy_formal import run_configured_formal
from .legacy_hf_direct import configured_hf_direct_runner, run_configured_hf_direct_sidecars
from .legacy_hf_fiber import (
    HFNormativeFiberRuntime,
    run_configured_hf_fiber_control,
    run_configured_hf_fiber_primary,
    run_configured_hf_fiber_resolver,
    run_configured_hf_fiber_sensitivity,
    run_configured_hf_fiber_sidecar,
)
from .legacy_oss import run_configured_oss
from .legacy_reporting import run_configured_reporting
from .legacy_sensitivity import run_configured_sensitivity
from .legacy_ulf_direct import (
    ConfiguredULFDirectPaths,
    configured_ulf_direct_delta_builder,
    run_configured_ulf_direct,
)
from .legacy_ulf_fiber import (
    ULFNormativeFiberBackendInputs,
    build_configured_ulf_fiber_delta,
    run_configured_ulf_fiber_resolver,
)
from .observed import HFObservedService
from .jitter_inputs import (
    build_direct_geometry,
    build_fiber_geometry,
    direct_sampling_rows,
    side_field_sampling_rows,
)
from .oss import OSSService
from .qualification import QualificationService
from .record_io import load_delta_bundle_for_final, load_final_record
from .reporting import ReportingService
from .sensitivity import SensitivityRuntimeInputs, SensitivityService
from .ulf_observed import DeltaBuilderOutput, ULFObservedRequest, ULFObservedService


def _analysis_module(name: str):
    analysis_root = Path(__file__).resolve().parents[2] / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module(name)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_npy_atomic(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("wb") as handle:
        np.save(handle, np.asarray(values))
    os.replace(temporary, path)


class _ConfiguredRuntime:
    def __init__(self, context: RunContext) -> None:
        if context.config is None:
            raise RecordError("default configured services require a resolved workflow")
        self.context = context
        self._availability_csv: Path | None = None
        readiness = _analysis_module("stnsnr_four_model_readiness")
        self.matlab_bin = Path(readiness.DEFAULT_MATLAB).expanduser().resolve()
        direct_analysis = _analysis_module("stnsnr_hf_direct_voxel_smoke")

        def flip_backend(*, side_paths, preprocess_dir, force):
            return direct_analysis.flip_left_fields_with_matlab(
                repo_root=self.context.config.study.paths.asset_root,
                matlab_bin=self.matlab_bin,
                side_paths=side_paths,
                preprocess_dir=preprocess_dir,
                force=force,
            )

        self.flip_backend = flip_backend

    def component_availability_csv(self) -> Path:
        if self._availability_csv is not None:
            return self._availability_csv
        conditions = [
            value
            for key, value in self.context.config.study.conditions.items()
            if str(key).startswith("frequency_2_addon")
        ]
        protocols = tuple(dict.fromkeys(value.protocol for value in conditions))
        phases = tuple(dict.fromkeys(value.phase for value in conditions))
        output = build_run_local_component_availability(
            stimulation_table=self.context.config.study.paths.stimulation_table,
            derivatives_root=self.context.config.study.paths.leaddbs_derivatives,
            run_root=self.context.store.run_root,
            addon_protocols=protocols,
            endpoint_phases=phases,
        )
        self._availability_csv = output.csv_path
        return output.csv_path

    def direct_paths(self) -> ConfiguredULFDirectPaths:
        config = self.context.config
        return ConfiguredULFDirectPaths(
            run_root=self.context.store.run_root,
            clinical_table=config.study.paths.clinical_table,
            stimulation_table=config.study.paths.stimulation_table,
            derivatives_root=config.study.paths.leaddbs_derivatives,
            brainmask=Path(config.study.space["brainmask"]),
            asset_root=config.study.paths.asset_root,
            readiness_csv=self.component_availability_csv(),
            matlab_bin=self.matlab_bin,
        )

    def fiber_inputs(self, connectome_id: str) -> ULFNormativeFiberBackendInputs:
        config = self.context.config
        try:
            connectome = config.study.connectomes[connectome_id]
        except KeyError as exc:
            raise RecordError(f"unknown configured connectome {connectome_id!r}") from exc
        return ULFNormativeFiberBackendInputs(
            connectome=connectome,
            clinical_table=config.study.paths.clinical_table,
            stimulation_table=config.study.paths.stimulation_table,
            readiness_csv=self.component_availability_csv(),
            derivatives_root=config.study.paths.leaddbs_derivatives,
            asset_root=config.study.paths.asset_root,
            matlab_bin=self.matlab_bin,
            run_root=self.context.store.run_root,
            clinical_columns=asdict(config.study.clinical_columns),
            force=bool(config.workflow.execution.force),
        )

    def direct_delta(self, endpoint, source, task, context) -> DeltaBuilderOutput:
        return configured_ulf_direct_delta_builder(
            paths=self.direct_paths(),
            flip_backend=self.flip_backend,
        )(endpoint, source, task, context)

    def fiber_delta(self, endpoint, source, task, context) -> DeltaBuilderOutput:
        return build_configured_ulf_fiber_delta(
            endpoint,
            source,
            task,
            context,
            inputs=self.fiber_inputs(endpoint.key.connectome),
        )

    def delta_builder(self, endpoint, source, task, context) -> DeltaBuilderOutput:
        if endpoint.key.model_family == "ulf_voxel":
            return self.direct_delta(endpoint, source, task, context)
        if endpoint.key.model_family == "ulf_fiber":
            return self.fiber_delta(endpoint, source, task, context)
        raise RecordError(f"unsupported DeltaHF model family {endpoint.key.model_family!r}")

    def direct_ulf_runner(self, request: ULFObservedRequest):
        return run_configured_ulf_direct(
            request,
            paths=self.direct_paths(),
            flip_backend=self.flip_backend,
        )

    def fiber_ulf_runner(self, request: ULFObservedRequest):
        return run_configured_ulf_fiber_resolver(
            request,
            self.fiber_inputs(request.endpoint.key.connectome),
        )

    @staticmethod
    def _ulf_branch_record(final: FinalArtifactRecord, context: RunContext) -> ULFBranchRecord:
        matches: list[ULFBranchRecord] = []
        for execution in context.results.values():
            if execution.task.endpoint.identifier != final.endpoint_model_id:
                continue
            payload = execution.result.facts.get("ulf_branch_record")
            if not isinstance(payload, dict):
                continue
            record = ULFBranchRecord.from_dict(dict(payload))
            if record.branch == final.final_branch:
                matches.append(record)
        if len(matches) != 1:
            raise RecordError(
                f"expected one realized ULF branch record for sensitivity; found {len(matches)}"
            )
        return matches[0]

    @staticmethod
    def _matched_hf_final(task: TaskSpec, context: RunContext) -> FinalArtifactRecord | None:
        expected_family = "hf_voxel" if task.endpoint.model_family == "ulf_voxel" else "hf_fiber"
        matches: dict[str, FinalArtifactRecord] = {}
        for execution in context.results.values():
            endpoint = execution.task.endpoint
            if (
                endpoint.study_id != task.endpoint.study_id
                or endpoint.scale_id != task.endpoint.scale_id
                or endpoint.model_family != expected_family
                or endpoint.connectome != task.endpoint.connectome
            ):
                continue
            payload = execution.result.facts.get("final_model_record")
            if isinstance(payload, dict):
                final = FinalArtifactRecord.from_dict(dict(payload))
                matches[final.record_hash] = final
        if len(matches) > 1:
            raise RecordError("multiple matched HF final records found for sensitivity")
        return next(iter(matches.values()), None)

    @staticmethod
    def _execution_for_stage(
        context: RunContext,
        *,
        endpoint_model_id: str,
        execution_stage: str,
    ):
        matches = [
            execution
            for execution in context.results.values()
            if execution.task.endpoint.identifier == endpoint_model_id
            and execution.task.key.execution_stage == execution_stage
        ]
        if len(matches) != 1:
            raise RecordError(
                f"expected one {execution_stage} task for {endpoint_model_id}; "
                f"found {len(matches)}"
            )
        return matches[0]

    @staticmethod
    def _task_artifact_path(execution, kind: str) -> Path:
        matches = [
            Path(item.path).expanduser().resolve()
            for item in execution.result.artifacts
            if item.kind == kind
        ]
        if len(matches) != 1:
            raise RecordError(
                f"expected one {kind} artifact from {execution.task.task_id}; found {len(matches)}"
            )
        path = matches[0]
        if not path.is_file():
            raise RecordError(f"{kind} artifact is missing: {path}")
        return path

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RecordError(f"invalid {label} JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise RecordError(f"{label} must contain a JSON object")
        return payload

    @staticmethod
    def _record_artifact_path(
        context: RunContext,
        artifact: ArtifactRef,
        label: str,
    ) -> Path:
        path = (context.store.run_root / artifact.relative_path).resolve()
        if not path.is_relative_to(context.store.run_root) or not path.is_file():
            raise RecordError(f"{label} artifact is missing or outside the run root")
        if sha256_file(path) != artifact.sha256:
            raise RecordError(f"{label} artifact SHA-256 mismatch")
        return path

    def _hf_direct_sidecar_inputs(
        self,
        context: RunContext,
        *,
        endpoint_model_id: str,
        subject_order: tuple[str, ...],
    ) -> tuple[Path, list[dict[str, Any]]]:
        execution = self._execution_for_stage(
            context,
            endpoint_model_id=endpoint_model_id,
            execution_stage="preprocessing_sidecars",
        )
        qc = self._read_json(
            self._task_artifact_path(execution, "qc"),
            "HF direct sidecar QC",
        )
        sidecar = self._read_json(
            self._task_artifact_path(execution, "sidecar_index"),
            "HF direct sidecar index",
        )
        cache_root = Path(str(sidecar.get("cache_root", ""))).expanduser().resolve()
        raw_rows = qc.get("sampling_qc")
        if not isinstance(raw_rows, list):
            raise RecordError("HF direct sidecar QC is missing sampling_qc rows")
        return cache_root / "candidate_xyz.npy", direct_sampling_rows(raw_rows, subject_order)

    def _hf_direct_jitter_geometry(
        self,
        context: RunContext,
        final: FinalArtifactRecord,
    ) -> dict[str, Any]:
        candidate_xyz, sampling_rows = self._hf_direct_sidecar_inputs(
            context,
            endpoint_model_id=final.endpoint_model_id,
            subject_order=final.subject_order,
        )
        return build_direct_geometry(
            final_candidate_xyz=candidate_xyz,
            hf_reference_sampling_qc=sampling_rows,
        )

    @staticmethod
    def _direct_component_sampling_rows(
        value: Any,
        subject_order: tuple[str, ...],
        *,
        allow_empty: bool,
    ) -> list[dict[str, Any]]:
        raw_rows = (
            [
                row
                for row in value
                if isinstance(row, dict) and "right" in row and "left_to_right" in row
            ]
            if isinstance(value, list)
            else []
        )
        if not raw_rows and allow_empty:
            raw_rows = [
                {"subject_id": subject_id, "right": [], "left_to_right": []}
                for subject_id in subject_order
            ]
        if not raw_rows:
            raise RecordError("ULF direct source manifest is missing component sampling rows")
        return direct_sampling_rows(raw_rows, subject_order)

    def _ulf_direct_jitter_geometry(
        self,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        matched_hf: FinalArtifactRecord | None,
    ) -> dict[str, Any]:
        branch = self._ulf_branch_record(final, context)
        artifacts = {artifact.kind: artifact for artifact in branch.artifacts}
        required = {"source_scan_manifest", "candidate_xyz"}
        missing = sorted(required - set(artifacts))
        if missing:
            raise RecordError("ULF direct branch is missing jitter inputs: " + ",".join(missing))
        source_manifest = self._read_json(
            self._record_artifact_path(
                context,
                artifacts["source_scan_manifest"],
                "ULF direct source manifest",
            ),
            "ULF direct source manifest",
        )
        hf_rows = self._direct_component_sampling_rows(
            source_manifest.get("hf_component_qc"),
            final.subject_order,
            allow_empty=matched_hf is None,
        )
        ulf_rows = self._direct_component_sampling_rows(
            source_manifest.get("ulf_component_qc"),
            final.subject_order,
            allow_empty=False,
        )
        kwargs: dict[str, Any] = {
            "final_candidate_xyz": self._record_artifact_path(
                context,
                artifacts["candidate_xyz"],
                "ULF direct candidate XYZ",
            ),
            "hf_component_sampling_qc": hf_rows,
            "ulf_component_sampling_qc": ulf_rows,
        }
        if matched_hf is not None:
            if matched_hf.endpoint_model_id == final.endpoint_model_id:
                raise RecordError("matched HF final cannot belong to the ULF endpoint")
            matched_xyz, reference_rows = self._hf_direct_sidecar_inputs(
                context,
                endpoint_model_id=matched_hf.endpoint_model_id,
                subject_order=final.subject_order,
            )
            feature_ids_path = Path(matched_hf.feature_axis.ids_path).expanduser()
            if not feature_ids_path.is_absolute():
                feature_ids_path = context.store.run_root / feature_ids_path
            feature_ids_path = feature_ids_path.resolve()
            if not feature_ids_path.is_file() or not feature_ids_path.is_relative_to(
                context.store.run_root
            ):
                raise RecordError("matched HF feature IDs are missing or outside the run root")
            if sha256_file(feature_ids_path) != matched_hf.feature_axis.sha256:
                raise RecordError("matched HF feature-ID artifact SHA-256 mismatch")
            candidate_flat = np.asarray(np.load(feature_ids_path, mmap_mode="r"), dtype=np.int64)
            analysis = _analysis_module("stnsnr_hf_direct_voxel_smoke")
            _, _, support_xyz, support_flat = analysis.right_brainmask_voxels_from_path(
                Path(context.config.study.space["brainmask"])
            )
            candidate_indices = np.searchsorted(support_flat, candidate_flat)
            if (
                np.any(candidate_indices >= support_flat.size)
                or not np.array_equal(support_flat[candidate_indices], candidate_flat)
            ):
                raise RecordError("matched HF candidate voxels are not contained in the right brainmask")
            task_root = (
                context.store.run_root
                / "models"
                / task.endpoint.identifier
                / "tasks"
                / task.task_id
            )
            support_xyz_path = task_root / "hf_support_xyz.npy"
            candidate_indices_path = task_root / "matched_hf_candidate_indices_in_support.npy"
            _write_npy_atomic(support_xyz_path, np.asarray(support_xyz, dtype=np.float32))
            _write_npy_atomic(candidate_indices_path, candidate_indices.astype(np.int64))
            kwargs.update(
                {
                    "matched_hf_candidate_xyz": matched_xyz,
                    "hf_support_xyz": support_xyz_path,
                    "matched_hf_candidate_indices_in_support": candidate_indices_path,
                    "hf_reference_sampling_qc": reference_rows,
                }
            )
        return build_direct_geometry(**kwargs)

    def _hf_fiber_jitter_geometry(
        self,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
    ) -> dict[str, Any]:
        reference_rows = self._hf_fiber_sidecar_rows(
            context,
            endpoint_model_id=final.endpoint_model_id,
            subject_order=final.subject_order,
        )
        try:
            connectome = context.config.study.connectomes[task.endpoint.connectome]
        except KeyError as exc:
            raise RecordError(
                f"unknown configured connectome {task.endpoint.connectome!r}"
            ) from exc
        return build_fiber_geometry(
            connectome_data_mat=connectome.path,
            hf_reference_sampling_qc=reference_rows,
        )

    def _hf_fiber_sidecar_rows(
        self,
        context: RunContext,
        *,
        endpoint_model_id: str,
        subject_order: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        execution = self._execution_for_stage(
            context,
            endpoint_model_id=endpoint_model_id,
            execution_stage="sidecar_equivalence",
        )
        qc = self._read_json(
            self._task_artifact_path(execution, "qc"),
            "HF fiber sidecar QC",
        )
        sidecar = self._read_json(
            self._task_artifact_path(execution, "sidecar_index"),
            "HF fiber sidecar index",
        )
        sampler_qc = qc.get("sampler_qc")
        if not isinstance(sampler_qc, dict) or not isinstance(
            sampler_qc.get("side_fields"), list
        ):
            raise RecordError("HF fiber sidecar QC is missing sampler_qc.side_fields")
        cache_root = Path(str(sidecar.get("cache_root", ""))).expanduser().resolve()
        return side_field_sampling_rows(
            sampler_qc["side_fields"],
            subject_order,
            flipped_root=cache_root / "flipped_left_to_right",
        )

    def _ulf_fiber_jitter_geometry(
        self,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        matched_hf: FinalArtifactRecord | None,
    ) -> dict[str, Any]:
        branch = self._ulf_branch_record(final, context)
        artifacts = {artifact.kind: artifact for artifact in branch.artifacts}
        required = {
            "selected_manifest",
            "hf_component_exposure",
            "ulf_component_exposure",
        }
        missing = sorted(required - set(artifacts))
        if missing:
            raise RecordError("ULF fiber branch is missing jitter inputs: " + ",".join(missing))
        selected_manifest = self._read_json(
            self._record_artifact_path(
                context,
                artifacts["selected_manifest"],
                "ULF fiber selected manifest",
            ),
            "ULF fiber selected manifest",
        )
        component_qc = selected_manifest.get("component_sampler_qc")
        if not isinstance(component_qc, dict):
            raise RecordError("ULF fiber selected manifest is missing component_sampler_qc")
        hf_component_path = self._record_artifact_path(
            context,
            artifacts["hf_component_exposure"],
            "ULF fiber HF-component exposure",
        )
        ulf_component_path = self._record_artifact_path(
            context,
            artifacts["ulf_component_exposure"],
            "ULF fiber ULF-component exposure",
        )
        if hf_component_path.parent != ulf_component_path.parent:
            raise RecordError("ULF fiber component exposures do not share one preprocess root")
        preprocess_root = hf_component_path.parent

        def component_rows(label: str) -> list[dict[str, Any]]:
            payload = component_qc.get(label)
            if not isinstance(payload, dict) or not isinstance(payload.get("side_paths"), list):
                raise RecordError(
                    f"ULF fiber selected manifest is missing {label} component side paths"
                )
            return side_field_sampling_rows(
                payload["side_paths"],
                final.subject_order,
                flipped_root=(
                    preprocess_root
                    / f"{label.lower()}_component"
                    / "flipped_left_to_right"
                ),
            )

        try:
            connectome = context.config.study.connectomes[task.endpoint.connectome]
        except KeyError as exc:
            raise RecordError(
                f"unknown configured connectome {task.endpoint.connectome!r}"
            ) from exc
        reference_rows = (
            self._hf_fiber_sidecar_rows(
                context,
                endpoint_model_id=matched_hf.endpoint_model_id,
                subject_order=final.subject_order,
            )
            if matched_hf is not None
            else None
        )
        return build_fiber_geometry(
            connectome_data_mat=connectome.path,
            hf_component_sampling_qc=component_rows("HF"),
            ulf_component_sampling_qc=component_rows("ULF"),
            hf_reference_sampling_qc=reference_rows,
        )

    def _jitter_manifest(
        self,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
        component_exposures: tuple[ArtifactRef, ...],
        *,
        matched_hf: FinalArtifactRecord | None = None,
    ) -> ArtifactRef:
        path = (
            context.store.run_root
            / "models"
            / task.endpoint.identifier
            / "tasks"
            / task.task_id
            / "jitter_input_manifest.json"
        )
        if task.endpoint.model_family == "hf_voxel":
            geometry = self._hf_direct_jitter_geometry(context, final)
        elif task.endpoint.model_family == "hf_fiber":
            geometry = self._hf_fiber_jitter_geometry(task, context, final)
        elif task.endpoint.model_family == "ulf_voxel":
            geometry = self._ulf_direct_jitter_geometry(task, context, final, matched_hf)
        elif task.endpoint.model_family == "ulf_fiber":
            geometry = self._ulf_fiber_jitter_geometry(task, context, final, matched_hf)
        else:
            raise RecordError(
                f"strict jitter geometry is not implemented for {task.endpoint.model_family}"
            )
        _write_json_atomic(
            path,
            {
                "schema_version": "stnsnr_sensitivity_jitter_v1",
                "endpoint_model_id": final.endpoint_model_id,
                "final_model_id": final.final_model_id,
                "final_record_hash": final.record_hash,
                "model_family": task.endpoint.model_family,
                "subject_order": list(final.subject_order),
                "feature_axis_sha256": final.feature_axis.sha256,
                "geometry": geometry,
                "component_exposures": [artifact.as_dict() for artifact in component_exposures],
            },
        )
        return ArtifactRef(
            task_id=task.task_id,
            kind="jitter_input_manifest",
            relative_path=path.relative_to(context.store.run_root).as_posix(),
            sha256=sha256_file(path),
        )

    def sensitivity_inputs(
        self,
        task: TaskSpec,
        context: RunContext,
        final: FinalArtifactRecord,
    ) -> SensitivityRuntimeInputs:
        delta = load_delta_bundle_for_final(final, context)
        component_exposures: tuple[ArtifactRef, ...] = ()
        y_base: ArtifactRef | None = None
        matched_hf: FinalArtifactRecord | None = None
        hf_overlap_tau: float | None = None
        if task.endpoint.model_family.startswith("ulf_"):
            branch = self._ulf_branch_record(final, context)
            by_kind = {artifact.kind: artifact for artifact in branch.artifacts}
            component_exposures = tuple(
                by_kind[kind]
                for kind in ("hf_component_exposure", "ulf_component_exposure")
                if kind in by_kind
            )
            y_base = by_kind.get("y_base")
            matched_hf = self._matched_hf_final(task, context)
            hf_overlap_tau = (
                float(matched_hf.selected_tau) if matched_hf is not None else math.inf
            )
        elif task.key.execution_stage == "spatial_jitter":
            component_exposures = (final.exposure,)
        jitter_manifest = (
            self._jitter_manifest(
                task,
                context,
                final,
                component_exposures,
                matched_hf=matched_hf,
            )
            if task.key.execution_stage == "spatial_jitter"
            else None
        )
        return SensitivityRuntimeInputs(
            delta_hf=delta,
            component_exposures=component_exposures,
            jitter_input_manifest=jitter_manifest,
            matched_hf_final=matched_hf,
            y_base=y_base,
            hf_overlap_tau=hf_overlap_tau,
        )


def build_default_service_registry(context: RunContext) -> ServiceRegistry:
    """Bind every executable planner operation to its production service."""
    runtime = _ConfiguredRuntime(context)
    hf_fiber_runtime = HFNormativeFiberRuntime(matlab_bin=runtime.matlab_bin)
    hf_observed = HFObservedService(
        direct_runner=configured_hf_direct_runner(flip_backend=runtime.flip_backend),
        direct_sidecar_runner=lambda request: run_configured_hf_direct_sidecars(
            request,
            flip_backend=runtime.flip_backend,
        ),
        fiber_primary_runner=lambda request: run_configured_hf_fiber_primary(
            request,
            runtime=hf_fiber_runtime,
        ),
        fiber_resolver_runner=lambda request: run_configured_hf_fiber_resolver(
            request,
            runtime=hf_fiber_runtime,
        ),
        fiber_sidecar_runner=lambda request: run_configured_hf_fiber_sidecar(
            request,
            runtime=hf_fiber_runtime,
        ),
        fiber_control_runner=lambda request: run_configured_hf_fiber_control(
            request,
            runtime=hf_fiber_runtime,
        ),
        fiber_sensitivity_runner=lambda request: run_configured_hf_fiber_sensitivity(
            request,
            runtime=hf_fiber_runtime,
        ),
    )
    ulf_observed = ULFObservedService(
        direct_runner=runtime.direct_ulf_runner,
        fiber_runner=runtime.fiber_ulf_runner,
        delta_builder=runtime.delta_builder,
    )
    qualification = QualificationService()
    formal = FormalService(runner=run_configured_formal, final_loader=load_final_record)
    sensitivity = SensitivityService(
        runner=run_configured_sensitivity,
        final_loader=load_final_record,
        inputs_loader=runtime.sensitivity_inputs,
    )
    oss = OSSService(runner=run_configured_oss)
    reporting = ReportingService(runner=run_configured_reporting)

    services: dict[tuple[str, str], Any] = {}

    def bind(families: tuple[str, ...], operations: tuple[str, ...], service: Any) -> None:
        for family in families:
            for operation in operations:
                services[(family, operation)] = service

    bind(
        ("hf_voxel",),
        ("input_readiness", "preprocessing_sidecars", "observed_source_resolver"),
        hf_observed,
    )
    bind(
        ("hf_fiber",),
        (
            "version_input_freeze",
            "sidecar_equivalence",
            "observed_primary",
            "plain_connected_control",
            "cheap_observed_sensitivity",
            "observed_source_resolver",
        ),
        hf_observed,
    )
    bind(
        ("ulf_voxel", "ulf_fiber"),
        (
            "input_hf_lock",
            "preprocessing_sidecars",
            "observed_branch_resolver",
            "final_model_realization",
        ),
        ulf_observed,
    )
    bind(("hf_voxel", "ulf_voxel"), ("equivalence_smoke",), qualification)
    bind(("hf_fiber", "ulf_fiber"), ("candidate_source_smoke",), qualification)
    bind(("hf_voxel", "ulf_voxel"), ("formal_permutation", "formal_bootstrap"), formal)
    bind(("hf_fiber", "ulf_fiber"), ("formal_permutation_bootstrap",), formal)
    bind(
        ("hf_voxel", "ulf_voxel", "hf_fiber", "ulf_fiber"),
        ("spatial_jitter", "selected_source_neighborhood"),
        sensitivity,
    )
    bind(("ulf_voxel",), ("additional_sensitivities",), sensitivity)
    bind(("ulf_fiber",), ("plain_burden_controls", "cheap_observed_sensitivity"), sensitivity)
    bind(("hf_fiber", "ulf_fiber"), ("oss_sensitivity",), oss)
    bind(
        ("hf_voxel", "ulf_voxel", "hf_fiber", "ulf_fiber"),
        ("endpoint_summary", "endpoint_report"),
        reporting,
    )
    return ServiceRegistry(by_operation=services)


__all__ = ["build_default_service_registry"]
