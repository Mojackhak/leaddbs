"""Configured service adapter for the legacy ULF normative-fiber analysis."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

import numpy as np

from ..catalog import EndpointRecord
from ..config import ConnectomeSpec
from ..executor import RunContext, TaskArtifact
from ..planner import TaskSpec
from ..records import ArtifactRef, DeltaHFBundle, HFSourceRecord, RecordError
from ..run_store import sha256_file
from .delta_hf import DeltaHFSupportAssessment, classify_delta_hf_support
from .observed import ObservedServiceOutput
from .ulf_observed import DeltaBuilderOutput, ULFObservedRequest, validate_hf_source_for_ulf


@dataclass(frozen=True)
class ULFNormativeFiberBackendInputs:
    """Explicit study and runtime inputs that are not carried by a branch request."""

    connectome: ConnectomeSpec
    clinical_table: Path
    stimulation_table: Path
    readiness_csv: Path
    derivatives_root: Path
    asset_root: Path
    matlab_bin: Path
    run_root: Path
    clinical_columns: Mapping[str, str]
    max_fibers: int = 0
    fiber_chunk_size: int = 10000
    force: bool = False

    def __post_init__(self) -> None:
        for name in (
            "clinical_table",
            "stimulation_table",
            "readiness_csv",
            "derivatives_root",
            "asset_root",
            "matlab_bin",
            "run_root",
        ):
            value = Path(getattr(self, name))
            if not str(value).strip():
                raise ValueError(f"{name} must be explicit")
            object.__setattr__(self, name, value)
        if self.max_fibers < 0:
            raise ValueError("max_fibers cannot be negative")
        if self.fiber_chunk_size < 1:
            raise ValueError("fiber_chunk_size must be positive")
        required_columns = {"subject_id", "scale", "protocol", "phase", "value", "baseline"}
        if set(self.clinical_columns) != required_columns:
            raise ValueError("clinical_columns must explicitly define subject_id/scale/protocol/phase/value/baseline")
        if any(not str(value).strip() for value in self.clinical_columns.values()):
            raise ValueError("clinical column names must be nonempty")


@dataclass(frozen=True)
class ULFNormativeFiberAnalysisConfig:
    """Dependency-free configured input consumed by the analysis module."""

    scale: str
    endpoint_protocol: str
    endpoint_phase: str
    hf_reference_protocol: str
    hf_reference_phase: str
    scale_direction: str
    subject_order: tuple[str, ...]
    branch: str
    nuisance_columns: tuple[str, ...]
    clinical_table: Path
    clinical_columns: Mapping[str, str]
    stimulation_table: Path
    readiness_csv: Path
    derivatives_root: Path
    asset_root: Path
    matlab_bin: Path
    connectome_id: str
    connectome_label: str
    connectome_path: Path
    connectome_identity_source: str
    model_root: Path
    output_dir: Path
    preprocess_dir: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    hf_source_status: str
    hf_prediction_status: str
    hf_source_record_hash: str
    hf_overlap_tau: float
    hf_overlap_coverage: int | None
    hf_feature_axis_sha256: str | None
    delta_hf_record_hash: str | None
    delta_support_status: str | None
    delta_full_scores_path: Path | None
    delta_fold_scores_path: Path | None
    delta_support_rows_path: Path | None
    delta_full_scores_shape: tuple[int, ...] | None
    delta_fold_scores_shape: tuple[int, ...] | None
    max_fibers: int
    fiber_chunk_size: int
    force_flip: bool
    force_rebuild: bool
    dynamic_names: bool


@dataclass(frozen=True)
class ULFNormativeFiberDeltaExposureConfig:
    """Explicit inputs for the HF component exposure used by DeltaHFScore."""

    scale: str
    endpoint_protocol: str
    endpoint_phase: str
    hf_reference_protocol: str
    hf_reference_phase: str
    subject_order: tuple[str, ...]
    clinical_table: Path
    clinical_columns: Mapping[str, str]
    stimulation_table: Path
    readiness_csv: Path
    derivatives_root: Path
    asset_root: Path
    matlab_bin: Path
    connectome_id: str
    connectome_label: str
    connectome_path: Path
    connectome_identity_source: str
    output_dir: Path
    max_fibers: int
    fiber_chunk_size: int
    force_flip: bool
    force_rebuild: bool


def _import_legacy_analysis() -> ModuleType:
    analysis_dir = Path(__file__).resolve().parents[2] / "analysis"
    path_token = str(analysis_dir)
    if path_token not in sys.path:
        sys.path.insert(0, path_token)
    return importlib.import_module("stnsnr_ulf_normative_fiber_observed")


def _load_legacy_analysis() -> ModuleType:
    return _import_legacy_analysis()


def _artifact_path(root: Path, artifact: ArtifactRef | None, kind: str) -> Path:
    if artifact is None:
        raise RecordError(f"adjusted ULF fiber branch requires {kind}")
    path = Path(artifact.relative_path)
    run_root = Path(root).expanduser().resolve()
    resolved = (path if path.is_absolute() else run_root / path).expanduser().resolve()
    if not resolved.is_relative_to(run_root):
        raise RecordError(f"artifact escapes configured run root for {kind}: {resolved}")
    if not resolved.is_file():
        raise RecordError(f"artifact is missing for {kind}: {resolved}")
    if sha256_file(resolved) != artifact.sha256:
        raise RecordError(f"artifact hash mismatch for {kind}: {resolved}")
    return resolved


def _validate_array_shape(path: Path, expected: tuple[int, ...], kind: str) -> None:
    try:
        observed = tuple(int(value) for value in np.load(path, mmap_mode="r").shape)
    except Exception as exc:
        raise RecordError(f"cannot read DeltaHF {kind}: {path}") from exc
    if observed != expected:
        raise RecordError(f"DeltaHF {kind} shape mismatch: expected {expected}, observed {observed}")


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _out_candidate_fractions(
    touched: np.ndarray,
    candidate: np.ndarray,
) -> np.ndarray:
    outside = np.count_nonzero(touched & ~candidate[None, :], axis=1).astype(np.float64)
    totals = np.count_nonzero(touched, axis=1).astype(np.float64)
    return np.divide(outside, totals, out=np.zeros_like(outside), where=totals > 0)


def _assess_hf_component_fiber_support(
    *,
    component_exposure: np.ndarray,
    full_candidate: np.ndarray,
    fold_candidates: np.ndarray,
    selected_tau: float,
    subject_ids: tuple[str, ...],
) -> tuple[DeltaHFSupportAssessment, list[dict[str, object]], dict[str, object]]:
    """Classify weighted suprathreshold component exposure outside immutable HF candidates."""
    component = np.asarray(component_exposure, dtype=float)
    full = np.asarray(full_candidate, dtype=bool)
    folds = np.asarray(fold_candidates, dtype=bool)
    if component.ndim != 2:
        raise RecordError("HF component exposure must be subject by fiber")
    if component.shape[0] != len(subject_ids):
        raise RecordError("HF component exposure subject order length mismatch")
    if full.shape != (component.shape[1],):
        raise RecordError("full HF candidate mask does not match the fiber axis")
    if folds.shape != (component.shape[0], component.shape[1]):
        raise RecordError("fold HF candidate masks must be fold by fiber")
    if not np.all(np.isfinite(component)):
        raise RecordError("HF component exposure must be finite")

    touched = component > float(selected_tau)
    suprathreshold = np.where(touched, component, 0.0)
    touched_counts = np.sum(touched, axis=1, dtype=np.int64)
    total_exposure = np.sum(suprathreshold, axis=1, dtype=np.float64)
    full_fractions = _out_candidate_fractions(touched, full)
    fold_fractions = np.vstack(
        [_out_candidate_fractions(touched, candidate) for candidate in folds]
    )
    any_zero = bool(np.any(touched_counts == 0) or np.any(total_exposure <= 0))
    assessment = classify_delta_hf_support(
        subject_out_fractions=tuple(float(value) for value in full_fractions),
        fold_out_fractions=tuple(float(value) for value in fold_fractions.ravel()),
        any_zero_total=any_zero,
        zero_status="invalid_no_hfcomponent_exposure",
    )
    rows = [
        {
            "subject_id": subject_id,
            "selected_hf_tau_v_per_m": float(selected_tau),
            "suprathreshold_touched_count": int(touched_counts[index]),
            "total_suprathreshold_exposure": float(total_exposure[index]),
            "full_candidate_fiber_count": int(np.count_nonzero(full)),
            "suprathreshold_in_candidate_count": int(np.count_nonzero(touched[index] & full)),
            "suprathreshold_out_candidate_count": int(np.count_nonzero(touched[index] & ~full)),
            "subject_out_candidate_fraction": float(full_fractions[index]),
            "maximum_fold_out_candidate_fraction": float(np.max(fold_fractions[:, index])),
            "fold_out_candidate_fractions": json.dumps(
                [float(value) for value in fold_fractions[:, index]],
                separators=(",", ":"),
            ),
            "support_status": assessment.status,
        }
        for index, subject_id in enumerate(subject_ids)
    ]
    qc = {
        "support_status": assessment.status,
        "out_candidate_fraction_definition": "suprathreshold_touched_fiber_count",
        "selected_hf_tau_v_per_m": float(selected_tau),
        "cohort_median_subject_out_candidate_fraction": assessment.cohort_median,
        "subject_fraction_over_0_50": assessment.subject_fraction_over_0_50,
        "subject_fraction_over_0_80": assessment.subject_fraction_over_0_80,
        "maximum_required_out_candidate_fraction": assessment.maximum_required_fraction,
        "adequate_median_upper_bound": 0.20,
        "adequate_subject_fraction_over_0_50_upper_bound": 0.25,
        "invalid_median_lower_bound_exclusive": 0.50,
        "invalid_subject_fraction_over_0_80_lower_bound_exclusive": 0.25,
        "invalid_required_fraction_lower_bound_exclusive": 0.95,
        "any_zero_touched_or_nonpositive_total": any_zero,
        "n_required_subjects": int(component.shape[0]),
        "n_required_folds": int(folds.shape[0]),
        "n_required_fold_subject_pairs": int(folds.shape[0] * component.shape[0]),
    }
    return assessment, rows, qc


def _compute_delta_hf_fiber_arrays(
    *,
    reference_exposure: np.ndarray,
    component_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
    fiber_ids: np.ndarray,
    selected_tau: float,
    selected_coverage: int,
    subject_ids: tuple[str, ...],
    fiber_net_score: Callable[..., Any],
) -> tuple[np.ndarray, np.ndarray, DeltaHFSupportAssessment, list[dict[str, object]], dict[str, object]]:
    reference = np.asarray(reference_exposure, dtype=float)
    component = np.asarray(component_exposure, dtype=float)
    weights = np.asarray(full_weights, dtype=float)
    weights_by_fold = np.asarray(fold_weights, dtype=float)
    ids = np.asarray(fiber_ids, dtype=np.int64)
    n_subjects = len(subject_ids)
    if reference.shape != component.shape:
        raise RecordError("HF reference and component exposure matrices must have identical shapes")
    if reference.shape[0] != n_subjects:
        raise RecordError("HF reference exposure rows do not match the endpoint subject order")
    if ids.shape != (reference.shape[1],):
        raise RecordError("fiber IDs do not match HF exposure columns")
    if weights.shape != (reference.shape[1],):
        raise RecordError("immutable full HF weights do not match the fiber axis")
    if weights_by_fold.shape != (n_subjects, reference.shape[1]):
        raise RecordError("immutable fold HF weights must be n_folds by fibers")
    if not np.all(np.isfinite(reference)) or not np.all(np.isfinite(component)):
        raise RecordError("HF reference and component exposures must be finite")

    active = reference > float(selected_tau)
    coverage = np.sum(active, axis=0, dtype=np.int32)
    full_candidate = (coverage >= int(selected_coverage)) & np.isfinite(weights)
    full_reference_score = fiber_net_score(reference, weights, full_candidate, fiber_ids=ids).net_score
    full_component_score = fiber_net_score(component, weights, full_candidate, fiber_ids=ids).net_score
    full_delta = np.asarray(full_component_score - full_reference_score, dtype=np.float64)

    fold_candidates = np.empty((n_subjects, reference.shape[1]), dtype=bool)
    fold_delta = np.empty((n_subjects, n_subjects), dtype=np.float64)
    for heldout in range(n_subjects):
        candidate = (
            (coverage - active[heldout].astype(np.int32)) >= int(selected_coverage)
        ) & np.isfinite(weights_by_fold[heldout])
        fold_candidates[heldout] = candidate
        fold_reference_score = fiber_net_score(
            reference,
            weights_by_fold[heldout],
            candidate,
            fiber_ids=ids,
        ).net_score
        fold_component_score = fiber_net_score(
            component,
            weights_by_fold[heldout],
            candidate,
            fiber_ids=ids,
        ).net_score
        fold_delta[heldout] = fold_component_score - fold_reference_score

    assessment, support_rows, support_qc = _assess_hf_component_fiber_support(
        component_exposure=component,
        full_candidate=full_candidate,
        fold_candidates=fold_candidates,
        selected_tau=selected_tau,
        subject_ids=subject_ids,
    )
    support_qc.update(
        {
            "selected_hf_coverage": int(selected_coverage),
            "full_candidate_fiber_count": int(np.count_nonzero(full_candidate)),
            "fold_candidate_fiber_counts": [
                int(np.count_nonzero(candidate)) for candidate in fold_candidates
            ],
        }
    )
    return full_delta, fold_delta, assessment, support_rows, support_qc


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")


def _write_npy_atomic(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        with temporary.open("wb") as handle:
            np.save(handle, values)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_csv_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RecordError("DeltaHF support rows cannot be empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _delta_artifact_ref(artifact: TaskArtifact, *, task_id: str, run_root: Path) -> ArtifactRef:
    path = Path(artifact.path).expanduser().resolve()
    try:
        relative_path = path.relative_to(run_root).as_posix()
    except ValueError as exc:
        raise RecordError(f"DeltaHF artifact {artifact.kind!r} escapes the configured run root") from exc
    shape: tuple[int, ...] = ()
    if path.suffix == ".npy":
        shape = tuple(int(value) for value in np.load(path, mmap_mode="r").shape)
    elif artifact.kind == "delta_hf_support_rows":
        with path.open(newline="", encoding="utf-8") as handle:
            shape = (sum(1 for _ in csv.DictReader(handle)),)
    return ArtifactRef(
        task_id=task_id,
        kind=artifact.kind,
        relative_path=relative_path,
        sha256=sha256_file(path),
        shape=shape,
    )


def _source_artifact_map(source: HFSourceRecord) -> dict[str, ArtifactRef]:
    artifacts: dict[str, ArtifactRef] = {}
    for artifact in source.artifacts:
        if artifact.kind in artifacts:
            raise RecordError(f"matched HF source has duplicate artifact kind {artifact.kind!r}")
        artifacts[artifact.kind] = artifact
    required = {
        "selected_manifest",
        "exposure_matrix",
        "selected_full_weights",
        "selected_fold_weights",
    }
    missing = sorted(required - set(artifacts))
    if missing:
        raise RecordError("matched HF source is missing immutable artifacts: " + ",".join(missing))
    return artifacts


def _verify_artifact_shape(reference: ArtifactRef, observed: tuple[int, ...]) -> None:
    if reference.shape and tuple(reference.shape) != tuple(observed):
        raise RecordError(
            f"immutable HF artifact shape mismatch for {reference.kind}: "
            f"expected {reference.shape}, observed {observed}"
        )


def _resolve_feature_axis(source: HFSourceRecord, run_root: Path) -> tuple[Path, np.ndarray]:
    if source.feature_axis is None:
        raise RecordError("accepted matched HF fiber source has no feature axis")
    path = Path(source.feature_axis.ids_path)
    resolved = (path if path.is_absolute() else run_root / path).expanduser().resolve()
    if not resolved.is_relative_to(run_root):
        raise RecordError("matched HF feature axis escapes the configured run root")
    if not resolved.is_file():
        raise RecordError(f"matched HF feature axis is missing: {resolved}")
    fiber_ids = np.asarray(np.load(resolved), dtype=np.int64)
    if fiber_ids.shape != (source.feature_axis.count,):
        raise RecordError("matched HF feature axis count does not match its immutable record")
    if _array_sha256(fiber_ids) != source.feature_axis.sha256:
        raise RecordError("matched HF feature axis hash mismatch")
    return resolved, fiber_ids


def _verify_selected_manifest(
    path: Path,
    *,
    source: HFSourceRecord,
) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read immutable HF selected manifest: {path}") from exc
    if manifest.get("status") != "complete":
        raise RecordError("immutable HF selected manifest is not complete")
    if float(manifest.get("selected_tau_v_per_m")) != float(source.selected_tau):
        raise RecordError("immutable HF selected manifest tau mismatch")
    if int(manifest.get("selected_coverage")) != int(source.selected_coverage):
        raise RecordError("immutable HF selected manifest coverage mismatch")
    if tuple(str(value) for value in manifest.get("subject_order", ())) != source.subject_order:
        raise RecordError("immutable HF selected manifest subject order mismatch")
    axis = manifest.get("feature_axis")
    if not isinstance(axis, Mapping) or source.feature_axis is None:
        raise RecordError("immutable HF selected manifest has no feature axis")
    if (
        int(axis.get("count", -1)) != source.feature_axis.count
        or str(axis.get("sha256", "")) != source.feature_axis.sha256
        or str(axis.get("identity_source", "")) != source.feature_axis.identity_source
    ):
        raise RecordError("immutable HF selected manifest feature axis mismatch")


def build_configured_ulf_fiber_delta(
    endpoint: EndpointRecord,
    source: HFSourceRecord,
    task: TaskSpec,
    context: RunContext,
    *,
    inputs: ULFNormativeFiberBackendInputs,
    component_runner: Callable[[ULFNormativeFiberDeltaExposureConfig], Mapping[str, Any]] | None = None,
) -> DeltaBuilderOutput:
    """Build DeltaHFFiberScore only from immutable HF source artifacts and endpoint HF component exposure."""
    if endpoint.key.model_family != "ulf_fiber":
        raise RecordError("ULF normative-fiber Delta builder requires an ulf_fiber endpoint")
    if not source.accepted:
        raise RecordError("ULF normative-fiber Delta builder requires an accepted matched HF source")
    if task.key.execution_stage != "preprocessing_sidecars":
        raise RecordError("ULF normative-fiber Delta builder may only run in preprocessing_sidecars")
    run_root = Path(context.store.run_root).expanduser().resolve()
    if Path(inputs.run_root).expanduser().resolve() != run_root:
        raise RecordError("ULF normative-fiber backend run root does not match the execution context")
    if endpoint.key.connectome != inputs.connectome.connectome_id:
        raise RecordError("ULF normative-fiber Delta endpoint/connectome identity mismatch")
    if endpoint.subject_ids != source.subject_order:
        raise RecordError("ULF endpoint subject order does not match the immutable HF source")
    if source.selected_tau is None or source.selected_coverage is None:
        raise RecordError("accepted matched HF source has no selected tau/Coverage")
    if source.feature_axis is None or source.feature_axis.identity_source != inputs.connectome.fiber_identity_source:
        raise RecordError("matched HF source feature identity does not match the configured connectome")

    source_artifacts = _source_artifact_map(source)
    resolved_artifacts = {
        kind: _artifact_path(run_root, source_artifacts[kind], kind)
        for kind in source_artifacts
        if kind in {
            "selected_manifest",
            "exposure_matrix",
            "selected_full_weights",
            "selected_fold_weights",
        }
    }
    _verify_selected_manifest(resolved_artifacts["selected_manifest"], source=source)
    _, fiber_ids = _resolve_feature_axis(source, run_root)
    reference_exposure = np.asarray(np.load(resolved_artifacts["exposure_matrix"]), dtype=float)
    full_weights = np.asarray(np.load(resolved_artifacts["selected_full_weights"]), dtype=float)
    fold_weights = np.asarray(np.load(resolved_artifacts["selected_fold_weights"]), dtype=float)
    _verify_artifact_shape(source_artifacts["exposure_matrix"], tuple(reference_exposure.shape))
    _verify_artifact_shape(source_artifacts["selected_full_weights"], tuple(full_weights.shape))
    _verify_artifact_shape(source_artifacts["selected_fold_weights"], tuple(fold_weights.shape))

    task_root = run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
    component_root = task_root / "hf_component_exposure"
    force = bool(
        context.config is not None
        and getattr(getattr(context.config.workflow, "execution", None), "force", False)
    )
    component_config = ULFNormativeFiberDeltaExposureConfig(
        scale=endpoint.scale_label,
        endpoint_protocol=endpoint.outcome_protocol,
        endpoint_phase=endpoint.outcome_phase,
        hf_reference_protocol=endpoint.hf_reference_protocol,
        hf_reference_phase=endpoint.hf_reference_phase,
        subject_order=endpoint.subject_ids,
        clinical_table=inputs.clinical_table,
        clinical_columns=dict(inputs.clinical_columns),
        stimulation_table=inputs.stimulation_table,
        readiness_csv=inputs.readiness_csv,
        derivatives_root=inputs.derivatives_root,
        asset_root=inputs.asset_root,
        matlab_bin=inputs.matlab_bin,
        connectome_id=inputs.connectome.connectome_id,
        connectome_label=inputs.connectome.label,
        connectome_path=inputs.connectome.path,
        connectome_identity_source=inputs.connectome.fiber_identity_source,
        output_dir=component_root,
        max_fibers=inputs.max_fibers,
        fiber_chunk_size=inputs.fiber_chunk_size,
        force_flip=force or inputs.force,
        force_rebuild=force or inputs.force,
    )
    analysis = _load_legacy_analysis()
    runner = component_runner or analysis.build_ulf_normative_fiber_hf_component_configured
    component_payload = runner(component_config)
    component_path = Path(str(component_payload["exposure_matrix"])).expanduser().resolve()
    component_ids_path = Path(str(component_payload["fiber_ids"])).expanduser().resolve()
    for path in (component_path, component_ids_path):
        if not path.is_relative_to(task_root) or not path.is_file():
            raise RecordError(f"configured HF component artifact is outside the sidecar task root: {path}")
    if str(component_payload.get("exposure_sha256", "")) != sha256_file(component_path):
        raise RecordError("configured HF component exposure hash mismatch")
    if str(component_payload.get("fiber_ids_file_sha256", "")) != sha256_file(component_ids_path):
        raise RecordError("configured HF component fiber-ID file hash mismatch")
    component_subject_order = tuple(str(value) for value in component_payload.get("subject_order", ()))
    if component_subject_order != endpoint.subject_ids:
        raise RecordError("configured HF component exposure subject order mismatch")
    component_ids = np.asarray(np.load(component_ids_path), dtype=np.int64)
    if not np.array_equal(component_ids, fiber_ids):
        raise RecordError("configured HF component fiber IDs do not match the immutable HF feature axis")
    component_axis_hash = _array_sha256(component_ids)
    if (
        component_axis_hash != source.feature_axis.sha256
        or str(component_payload.get("feature_axis_sha256", "")) != source.feature_axis.sha256
    ):
        raise RecordError("configured HF component fiber axis hash mismatch")
    component_exposure = np.asarray(np.load(component_path), dtype=float)
    if component_exposure.shape != reference_exposure.shape:
        raise RecordError("configured HF component exposure shape does not match immutable HF reference exposure")

    full_delta, fold_delta, assessment, support_rows, support_qc = _compute_delta_hf_fiber_arrays(
        reference_exposure=reference_exposure,
        component_exposure=component_exposure,
        full_weights=full_weights,
        fold_weights=fold_weights,
        fiber_ids=fiber_ids,
        selected_tau=float(source.selected_tau),
        selected_coverage=int(source.selected_coverage),
        subject_ids=endpoint.subject_ids,
        fiber_net_score=analysis.fiber_net_score,
    )
    support_qc.update(
        {
            "endpoint_model_id": endpoint.endpoint_model_id,
            "connectome_id": endpoint.key.connectome,
            "subject_order": list(endpoint.subject_ids),
            "feature_axis_sha256": source.feature_axis.sha256,
            "hf_source_record_hash": source.record_hash,
            "immutable_hf_artifacts": {
                kind: {
                    "relative_path": reference.relative_path,
                    "sha256": reference.sha256,
                    "shape": list(reference.shape),
                }
                for kind, reference in source_artifacts.items()
                if kind in resolved_artifacts
            },
            "hf_component_exposure": {
                "path": str(component_path),
                "sha256": sha256_file(component_path),
                "shape": list(component_exposure.shape),
            },
        }
    )

    full_path = task_root / "full.npy"
    folds_path = task_root / "folds.npy"
    support_path = task_root / "support.csv"
    support_qc_path = task_root / "support_qc.json"
    _write_npy_atomic(full_path, full_delta)
    _write_npy_atomic(folds_path, fold_delta)
    _write_csv_atomic(support_path, support_rows)
    _write_json_atomic(support_qc_path, support_qc)
    task_artifacts = (
        TaskArtifact("delta_hf_full_scores", full_path),
        TaskArtifact("delta_hf_fold_scores", folds_path),
        TaskArtifact("delta_hf_support_rows", support_path),
        TaskArtifact("delta_hf_support_qc", support_qc_path),
    )
    references = {
        artifact.kind: _delta_artifact_ref(artifact, task_id=task.task_id, run_root=run_root)
        for artifact in task_artifacts
    }
    valid = assessment.valid
    bundle = DeltaHFBundle(
        input_status="valid" if valid else "invalid",
        support_status=assessment.status,
        selected_hf_tau=source.selected_tau,
        selected_hf_coverage=source.selected_coverage,
        full_scores=references["delta_hf_full_scores"],
        fold_scores=references["delta_hf_fold_scores"],
        support_rows=references["delta_hf_support_rows"],
        failure_stage="" if valid else "support_qc",
        failure_detail="" if valid else assessment.status,
    )
    return DeltaBuilderOutput(bundle=bundle, artifacts=task_artifacts)


def configured_ulf_fiber_delta_builder(
    *,
    inputs: ULFNormativeFiberBackendInputs,
    component_runner: Callable[[ULFNormativeFiberDeltaExposureConfig], Mapping[str, Any]] | None = None,
) -> Callable[[EndpointRecord, HFSourceRecord, TaskSpec, RunContext], DeltaBuilderOutput]:
    """Bind explicit component dependencies into the shared DeltaBuilder signature."""

    def build(
        endpoint: EndpointRecord,
        source: HFSourceRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> DeltaBuilderOutput:
        return build_configured_ulf_fiber_delta(
            endpoint,
            source,
            task,
            context,
            inputs=inputs,
            component_runner=component_runner,
        )

    return build


def build_legacy_ulf_fiber_config(
    request: ULFObservedRequest,
    inputs: ULFNormativeFiberBackendInputs,
) -> ULFNormativeFiberAnalysisConfig:
    """Translate immutable configured records without consulting legacy defaults."""
    if request.endpoint.key.model_family != "ulf_fiber":
        raise RecordError("configured ULF normative-fiber backend requires an ulf_fiber endpoint")
    if request.endpoint.key.connectome != inputs.connectome.connectome_id:
        raise RecordError("configured ULF fiber endpoint/connectome identity mismatch")
    if request.branch not in {"no_delta_hf", "delta_hf_adjusted"}:
        raise RecordError(f"unsupported ULF fiber branch {request.branch!r}")

    source = request.hf_source
    if source.accepted:
        if source.feature_axis is None:
            raise RecordError("accepted matched HF fiber source has no feature axis")
        if source.feature_axis.identity_source != inputs.connectome.fiber_identity_source:
            raise RecordError("matched HF source connectome feature identity is incompatible")
        validate_hf_source_for_ulf(
            source,
            expected_subject_order=request.endpoint.subject_ids,
            expected_feature_sha=source.feature_axis.sha256,
        )
    elif request.branch == "delta_hf_adjusted":
        raise RecordError("delta_hf_adjusted cannot run without an accepted matched HF source")

    expected_nuisance = ("Y_HF_ref",) if request.branch == "no_delta_hf" else ("Y_HF_ref", "DeltaHFScore")
    if tuple(request.nuisance.columns) != expected_nuisance:
        raise RecordError("ULF fiber request has a branch-incompatible nuisance design")

    delta_full_path: Path | None = None
    delta_fold_path: Path | None = None
    delta_support_path: Path | None = None
    delta_full_shape: tuple[int, ...] | None = None
    delta_fold_shape: tuple[int, ...] | None = None
    delta_record_hash: str | None = None
    delta_support_status: str | None = None
    if request.branch == "delta_hf_adjusted":
        delta = request.delta_hf
        if delta is None or not delta.valid:
            raise RecordError("delta_hf_adjusted requires valid adequate-or-limited DeltaHF inputs")
        if not source.accepted:
            raise RecordError("delta_hf_adjusted cannot run without an accepted matched HF source")
        if (
            float(delta.selected_hf_tau) != float(source.selected_tau)
            or int(delta.selected_hf_coverage) != int(source.selected_coverage)
            or float(request.hf_overlap_tau) != float(source.selected_tau)
            or int(request.hf_overlap_coverage) != int(source.selected_coverage)
        ):
            raise RecordError("HF overlap, DeltaHF, and matched HF source must use one selected tau/Coverage")
        delta_full_path = _artifact_path(inputs.run_root, delta.full_scores, "full scores")
        delta_fold_path = _artifact_path(inputs.run_root, delta.fold_scores, "fold-by-subject scores")
        delta_support_path = _artifact_path(inputs.run_root, delta.support_rows, "support rows")
        delta_full_shape = tuple(delta.full_scores.shape)
        delta_fold_shape = tuple(delta.fold_scores.shape)
        _validate_array_shape(delta_full_path, delta_full_shape, "full scores")
        _validate_array_shape(delta_fold_path, delta_fold_shape, "fold-by-subject scores")
        delta_record_hash = delta.record_hash
        delta_support_status = delta.support_status
    elif source.accepted:
        if float(request.hf_overlap_tau) != float(source.selected_tau):
            raise RecordError("no-delta HF-overlap exclusion must use the matched HF selected tau")
        if int(request.hf_overlap_coverage) != int(source.selected_coverage):
            raise RecordError("no-delta HF-overlap exclusion must retain the matched HF selected coverage")
    elif not math.isinf(float(request.hf_overlap_tau)) or request.hf_overlap_coverage is not None:
        raise RecordError("absent HF source requires infinite overlap tau and no overlap coverage")

    return ULFNormativeFiberAnalysisConfig(
        scale=request.endpoint.scale_label,
        endpoint_protocol=request.endpoint.outcome_protocol,
        endpoint_phase=request.endpoint.outcome_phase,
        hf_reference_protocol=request.endpoint.hf_reference_protocol,
        hf_reference_phase=request.endpoint.hf_reference_phase,
        scale_direction=request.endpoint.direction,
        subject_order=tuple(request.endpoint.subject_ids),
        branch=request.branch,
        nuisance_columns=expected_nuisance,
        clinical_table=inputs.clinical_table,
        clinical_columns=dict(inputs.clinical_columns),
        stimulation_table=inputs.stimulation_table,
        readiness_csv=inputs.readiness_csv,
        derivatives_root=inputs.derivatives_root,
        asset_root=inputs.asset_root,
        matlab_bin=inputs.matlab_bin,
        connectome_id=inputs.connectome.connectome_id,
        connectome_label=inputs.connectome.label,
        connectome_path=inputs.connectome.path,
        connectome_identity_source=inputs.connectome.fiber_identity_source,
        model_root=request.model_root,
        output_dir=request.output_root,
        preprocess_dir=request.model_root / "cache" / f"ulf_fiber_{inputs.connectome.connectome_id}_{request.endpoint.key.endpoint_phase}",
        tau_grid=tuple(float(value) for value in request.tau_grid),
        coverage_grid=tuple(int(value) for value in request.coverage_grid),
        primary_tau=float(request.primary_tau),
        primary_coverage=int(request.primary_coverage),
        hf_source_status=source.source_status,
        hf_prediction_status=source.prediction_status,
        hf_source_record_hash=source.record_hash,
        hf_overlap_tau=float(request.hf_overlap_tau),
        hf_overlap_coverage=request.hf_overlap_coverage,
        hf_feature_axis_sha256=source.feature_axis.sha256 if source.feature_axis is not None else None,
        delta_hf_record_hash=delta_record_hash,
        delta_support_status=delta_support_status,
        delta_full_scores_path=delta_full_path,
        delta_fold_scores_path=delta_fold_path,
        delta_support_rows_path=delta_support_path,
        delta_full_scores_shape=delta_full_shape,
        delta_fold_scores_shape=delta_fold_shape,
        max_fibers=inputs.max_fibers,
        fiber_chunk_size=inputs.fiber_chunk_size,
        force_flip=inputs.force,
        force_rebuild=inputs.force,
        dynamic_names=True,
    )


def _optional_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def _observed_output(payload: Mapping[str, Any], request: ULFObservedRequest, inputs: ULFNormativeFiberBackendInputs) -> ObservedServiceOutput:
    subject_order = payload.get("subject_order", ())
    if not isinstance(subject_order, (list, tuple)):
        raise RuntimeError("configured ULF fiber backend returned invalid subject order")
    normalized_subject_order = tuple(str(value) for value in subject_order)
    if normalized_subject_order != request.endpoint.subject_ids:
        raise RuntimeError("configured ULF fiber backend subject order mismatch")

    axis_payload = payload.get("feature_axis")
    if not isinstance(axis_payload, Mapping):
        raise RuntimeError("configured ULF fiber backend did not return a feature axis")
    from ..records import FeatureAxisRef

    feature_axis = FeatureAxisRef(
        ids_path=Path(str(axis_payload["ids_path"])),
        count=int(axis_payload["count"]),
        sha256=str(axis_payload["sha256"]),
        identity_source=str(axis_payload["identity_source"]),
    )
    if not feature_axis.ids_path.is_file():
        raise RuntimeError(f"configured ULF fiber feature axis is missing: {feature_axis.ids_path}")
    if feature_axis.identity_source != inputs.connectome.fiber_identity_source:
        raise RuntimeError("configured ULF fiber feature identity source mismatch")
    source_axis = request.hf_source.feature_axis
    if source_axis is not None and feature_axis.sha256 != source_axis.sha256:
        raise RuntimeError("configured ULF fiber feature axis does not match the immutable HF source feature axis")

    artifact_payload = payload.get("artifacts", {})
    if not isinstance(artifact_payload, Mapping):
        raise RuntimeError("configured ULF fiber backend returned invalid artifacts")
    artifacts = tuple(
        TaskArtifact(kind=str(kind), path=Path(str(path)))
        for kind, path in sorted(artifact_payload.items())
    )
    return ObservedServiceOutput(
        source_status=str(payload["source_status"]),
        prediction_status=str(payload["prediction_status"]),
        threshold_source=str(payload["threshold_source"]),
        selected_tau=_optional_float(payload.get("selected_tau")),
        selected_coverage=_optional_int(payload.get("selected_coverage")),
        adjacent_support=_optional_int(payload.get("adjacent_support")),
        subject_order=normalized_subject_order,
        feature_axis=feature_axis,
        artifacts=artifacts,
    )


def run_configured_ulf_fiber_resolver(
    request: ULFObservedRequest,
    inputs: ULFNormativeFiberBackendInputs,
) -> ObservedServiceOutput:
    """Run exactly one configured ULF fiber branch and its source resolver."""
    config = build_legacy_ulf_fiber_config(request, inputs)
    legacy = _load_legacy_analysis()
    payload = legacy.run_ulf_normative_fiber_configured(config)
    if str(payload.get("branch", "")) != request.branch:
        raise RuntimeError("configured ULF fiber backend did not realize the exact requested branch")
    return _observed_output(payload, request, inputs)


configured_ulf_fiber_resolver_runner = run_configured_ulf_fiber_resolver


__all__ = [
    "ULFNormativeFiberAnalysisConfig",
    "ULFNormativeFiberBackendInputs",
    "ULFNormativeFiberDeltaExposureConfig",
    "build_configured_ulf_fiber_delta",
    "build_legacy_ulf_fiber_config",
    "configured_ulf_fiber_delta_builder",
    "configured_ulf_fiber_resolver_runner",
    "run_configured_ulf_fiber_resolver",
]
