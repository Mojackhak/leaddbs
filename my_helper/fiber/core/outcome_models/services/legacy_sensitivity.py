"""Configured adapters for final-record-driven sensitivity backends."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping

import numpy as np

from ..executor import TaskArtifact
from ..records import ArtifactRef, FinalArtifactRecord, RecordError
from .sensitivity import SensitivityRequest, SensitivityServiceOutput


@dataclass(frozen=True)
class ConfiguredSensitivityTarget:
    model_family: str
    operation: str
    final_model_id: str
    final_record_hash: str
    final_branch: str
    selected_tau: float
    selected_coverage: int
    scale_direction: str
    subject_order: tuple[str, ...]
    output_root: Path
    exposure_path: Path
    scores_path: Path
    feature_ids_path: Path
    spatial_reference_path: Path | None
    component_paths: Mapping[str, Path]
    delta_full_path: Path | None
    delta_fold_path: Path | None
    delta_support_path: Path | None
    delta_input_status: str | None
    delta_support_status: str | None
    jitter_input_manifest_path: Path | None
    jitter_input_manifest: Mapping[str, Any] | None
    matched_hf_final: FinalArtifactRecord | None
    matched_hf_paths: Mapping[str, Path]
    y_base_path: Path | None
    hf_overlap_tau: float | None


BackendRunner = Callable[..., Mapping[str, Any]]


SUPPORTED_SENSITIVITY_OPERATIONS: Mapping[tuple[str, str], str] = {
    ("hf_voxel", "spatial_jitter"): "jitter_results",
    ("hf_voxel", "selected_source_neighborhood"): "sensitivity_results",
    ("hf_fiber", "spatial_jitter"): "jitter_results",
    ("ulf_voxel", "spatial_jitter"): "jitter_results",
    ("ulf_voxel", "selected_source_neighborhood"): "sensitivity_results",
    ("ulf_voxel", "additional_sensitivities"): "sensitivity_results",
    ("ulf_fiber", "plain_burden_controls"): "control_metrics",
    ("ulf_fiber", "cheap_observed_sensitivity"): "sensitivity_results",
    ("ulf_fiber", "selected_source_neighborhood"): "sensitivity_results",
    ("ulf_fiber", "spatial_jitter"): "jitter_results",
}


def _load_analysis(name: str):
    analysis_root = Path(__file__).resolve().parents[2] / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module(name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _run_root(request: SensitivityRequest) -> Path:
    output_root = Path(request.output_root).expanduser().resolve()
    try:
        run_root = output_root.parents[3]
    except IndexError as exc:
        raise RecordError("sensitivity output_root does not follow the configured run layout") from exc
    if output_root.parent.name != "tasks" or output_root.parents[2].name != "models":
        raise RecordError("sensitivity output_root must be run_root/models/endpoint/tasks/task")
    return run_root


def _artifact_path(run_root: Path, artifact: ArtifactRef, *, label: str) -> Path:
    path = (run_root / artifact.relative_path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError(f"{label} artifact escapes the configured run root") from exc
    if not path.is_file():
        raise RecordError(f"{label} artifact is missing: {path}")
    if _sha256(path) != artifact.sha256:
        raise RecordError(f"{label} artifact SHA-256 mismatch: {path}")
    if path.suffix == ".npy" and artifact.shape:
        shape = tuple(int(value) for value in np.load(path, mmap_mode="r").shape)
        if shape != tuple(artifact.shape):
            raise RecordError(f"{label} artifact shape mismatch: {shape} != {artifact.shape}")
    return path


def _axis_path(run_root: Path, final: FinalArtifactRecord, *, label: str) -> Path:
    path = Path(final.feature_axis.ids_path).expanduser()
    path = path.resolve() if path.is_absolute() else (run_root / path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError(f"{label} feature axis escapes the configured run root") from exc
    if not path.is_file():
        raise RecordError(f"{label} feature-axis artifact is missing: {path}")
    values = np.load(path, mmap_mode="r")
    if values.ndim != 1 or int(values.shape[0]) != final.feature_axis.count:
        raise RecordError(f"{label} feature-axis count mismatch")
    identity_source = final.feature_axis.identity_source
    if identity_source == "candidate_flat_indices":
        observed_sha256 = _sha256(path)
    elif identity_source.endswith(":idx"):
        observed_sha256 = _array_sha256(values)
    else:
        raise RecordError(
            f"{label} feature-axis identity source is unsupported: {identity_source!r}"
        )
    if observed_sha256 != final.feature_axis.sha256:
        raise RecordError(f"{label} feature-axis SHA-256 mismatch: {path}")
    return path


def _score_subject_order(path: Path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "subject_id" not in (reader.fieldnames or ()):
            raise RecordError("sensitivity scores require a subject_id column")
        return tuple(str(row["subject_id"]) for row in reader)


def _validated_final_paths(
    run_root: Path,
    final: FinalArtifactRecord,
    *,
    label: str,
) -> dict[str, Path]:
    manifest = _artifact_path(run_root, final.manifest, label=f"{label} manifest")
    exposure = _artifact_path(run_root, final.exposure, label=f"{label} exposure")
    scores = _artifact_path(run_root, final.scores, label=f"{label} scores")
    axis = _axis_path(run_root, final, label=label)
    if _score_subject_order(scores) != final.subject_order:
        raise RecordError(f"{label} score subject order differs from its immutable final record")
    matrix = np.load(exposure, mmap_mode="r")
    expected = (len(final.subject_order), final.feature_axis.count)
    if tuple(matrix.shape) != expected:
        raise RecordError(f"{label} exposure does not match subject and feature order")
    paths = {
        "manifest": manifest,
        "exposure": exposure,
        "scores": scores,
        "feature_ids": axis,
    }
    if final.spatial_reference is not None:
        paths["spatial_reference"] = _artifact_path(
            run_root,
            final.spatial_reference,
            label=f"{label} spatial reference",
        )
    return paths


def _validate_jitter_manifest(
    path: Path,
    request: SensitivityRequest,
) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read sensitivity jitter input manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise RecordError("jitter input manifest must be a JSON object")
    expected = {
        "schema_version": "stnsnr_sensitivity_jitter_v1",
        "endpoint_model_id": request.final.endpoint_model_id,
        "final_model_id": request.final.final_model_id,
        "final_record_hash": request.final.record_hash,
        "model_family": request.task.endpoint.model_family,
        "subject_order": list(request.final.subject_order),
        "feature_axis_sha256": request.final.feature_axis.sha256,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise RecordError(f"jitter input manifest {key} does not match the immutable final record")
    if not isinstance(payload.get("geometry"), dict):
        raise RecordError("jitter input manifest requires a geometry object")
    return payload


def build_configured_sensitivity_target(
    request: SensitivityRequest,
) -> ConfiguredSensitivityTarget:
    """Resolve and validate every immutable input used by one sensitivity task."""
    if request.final.endpoint_model_id != request.task.endpoint.identifier:
        raise RecordError("sensitivity final record belongs to another endpoint")
    run_root = _run_root(request)
    final_paths = _validated_final_paths(run_root, request.final, label="final")

    component_paths: dict[str, Path] = {}
    expected_component_shape = (
        len(request.final.subject_order),
        request.final.feature_axis.count,
    )
    for artifact in request.component_exposures:
        if artifact.kind in component_paths:
            raise RecordError(f"duplicate sensitivity component artifact kind {artifact.kind!r}")
        path = _artifact_path(run_root, artifact, label=artifact.kind)
        if artifact.shape != expected_component_shape:
            raise RecordError(
                f"{artifact.kind} must match final subject and feature order"
            )
        component_paths[artifact.kind] = path

    delta_full_path = None
    delta_fold_path = None
    delta_support_path = None
    if request.delta_hf is not None:
        if request.delta_hf.full_scores is not None:
            delta_full_path = _artifact_path(
                run_root,
                request.delta_hf.full_scores,
                label="DeltaHF full scores",
            )
        if request.delta_hf.fold_scores is not None:
            delta_fold_path = _artifact_path(
                run_root,
                request.delta_hf.fold_scores,
                label="DeltaHF fold scores",
            )
        if request.delta_hf.support_rows is not None:
            delta_support_path = _artifact_path(
                run_root,
                request.delta_hf.support_rows,
                label="DeltaHF support rows",
            )

    y_base_path = (
        _artifact_path(run_root, request.y_base, label="Y_base")
        if request.y_base is not None
        else None
    )
    if request.y_base is not None and request.y_base.shape != (
        len(request.final.subject_order),
    ):
        raise RecordError("Y_base must have one value per final-model subject")

    jitter_manifest_path = None
    jitter_manifest = None
    if request.jitter_input_manifest is not None:
        jitter_manifest_path = _artifact_path(
            run_root,
            request.jitter_input_manifest,
            label="jitter input manifest",
        )
        jitter_manifest = _validate_jitter_manifest(jitter_manifest_path, request)

    matched_paths: dict[str, Path] = {}
    if request.matched_hf_final is not None:
        if request.matched_hf_final.final_branch != "hf_source":
            raise RecordError("matched HF sensitivity record must identify an hf_source final")
        if request.matched_hf_final.subject_order != request.final.subject_order:
            raise RecordError("matched HF final subject order differs from the ULF final model")
        matched_paths = _validated_final_paths(
            run_root,
            request.matched_hf_final,
            label="matched HF final",
        )

    request.output_root.mkdir(parents=True, exist_ok=True)
    return ConfiguredSensitivityTarget(
        model_family=request.task.endpoint.model_family,
        operation=request.task.key.execution_stage,
        final_model_id=request.final.final_model_id,
        final_record_hash=request.final.record_hash,
        final_branch=request.final.final_branch,
        selected_tau=float(request.final.selected_tau),
        selected_coverage=int(request.final.selected_coverage),
        scale_direction=request.final.scale_direction,
        subject_order=request.final.subject_order,
        output_root=request.output_root,
        exposure_path=final_paths["exposure"],
        scores_path=final_paths["scores"],
        feature_ids_path=final_paths["feature_ids"],
        spatial_reference_path=final_paths.get("spatial_reference"),
        component_paths=component_paths,
        delta_full_path=delta_full_path,
        delta_fold_path=delta_fold_path,
        delta_support_path=delta_support_path,
        delta_input_status=(
            request.delta_hf.input_status if request.delta_hf is not None else None
        ),
        delta_support_status=(
            request.delta_hf.support_status if request.delta_hf is not None else None
        ),
        jitter_input_manifest_path=jitter_manifest_path,
        jitter_input_manifest=jitter_manifest,
        matched_hf_final=request.matched_hf_final,
        matched_hf_paths=matched_paths,
        y_base_path=y_base_path,
        hf_overlap_tau=request.hf_overlap_tau,
    )


def _contains_classification_feedback(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            token = str(key)
            if token in {"classification_changes", "final_model_status"}:
                return True
            if token.endswith("source_status") or token.endswith("prediction_status"):
                return True
            if _contains_classification_feedback(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_classification_feedback(item) for item in value)
    return False


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, np.generic):
        return _json_ready(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_configured_sensitivity(
    request: SensitivityRequest,
    *,
    direct_neighborhood_runner: BackendRunner | None = None,
    fiber_neighborhood_runner: BackendRunner | None = None,
    direct_jitter_runner: BackendRunner | None = None,
    fiber_jitter_runner: BackendRunner | None = None,
    ulf_direct_additional_runner: BackendRunner | None = None,
    ulf_fiber_additional_runner: BackendRunner | None = None,
    ulf_fiber_plain_control_runner: BackendRunner | None = None,
    ulf_fiber_cheap_runner: BackendRunner | None = None,
) -> SensitivityServiceOutput:
    """Dispatch one configured sensitivity task and write its final-linked result."""
    target = build_configured_sensitivity_target(request)
    stage = target.operation
    family = target.model_family
    expected_kind = SUPPORTED_SENSITIVITY_OPERATIONS.get((family, stage))
    if expected_kind is None:
        raise RecordError(
            f"unsupported configured sensitivity operation {family}:{stage}"
        )
    kind: str
    if stage == "selected_source_neighborhood":
        if family.endswith("voxel"):
            runner = direct_neighborhood_runner or _load_analysis(
                "stnsnr_direct_voxel_formal_jitter"
            ).run_configured_neighborhood_sensitivity
        else:
            runner = fiber_neighborhood_runner or _load_analysis(
                "stnsnr_normative_fiber_formal_jitter"
            ).run_configured_neighborhood_sensitivity
        result = runner(target, tau_multipliers=request.selected_tau_multipliers)
        kind = "sensitivity_results"
    elif stage == "spatial_jitter":
        if target.jitter_input_manifest is None:
            raise RecordError("configured spatial jitter requires a validated jitter input manifest")
        if family.endswith("voxel"):
            runner = direct_jitter_runner or _load_analysis(
                "stnsnr_direct_voxel_formal_jitter"
            ).run_configured_jitter
        else:
            runner = fiber_jitter_runner or _load_analysis(
                "stnsnr_normative_fiber_formal_jitter"
            ).run_configured_jitter
        result = runner(
            target,
            n_jitters=request.jitter_resamples,
            jitter_fwhm_mm=request.jitter_fwhm_mm,
            seed=request.seed,
        )
        kind = "jitter_results"
    elif stage == "additional_sensitivities":
        if family == "ulf_voxel":
            runner = ulf_direct_additional_runner or _load_analysis(
                "stnsnr_ulf_direct_voxel_sensitivity_observed"
            ).run_configured_additional_sensitivities
        elif family == "ulf_fiber":
            runner = ulf_fiber_additional_runner or _load_analysis(
                "stnsnr_ulf_normative_fiber_sensitivity_observed"
            ).run_configured_additional_sensitivities
        else:
            raise RecordError("additional sensitivities are defined only for ULF models")
        result = runner(target, enabled_analyses=request.enabled_ulf_analyses)
        kind = "sensitivity_results"
    elif stage == "plain_burden_controls":
        if family != "ulf_fiber":
            raise RecordError("plain burden controls are defined only for ULF normative fiber")
        runner = ulf_fiber_plain_control_runner or _load_analysis(
            "stnsnr_ulf_normative_fiber_sensitivity_observed"
        ).run_configured_plain_burden_controls
        result = runner(target, enabled_analyses=request.enabled_ulf_analyses)
        kind = "control_metrics"
    elif stage == "cheap_observed_sensitivity":
        if family != "ulf_fiber":
            raise RecordError(
                "configured cheap observed sensitivity is defined only for ULF normative fiber"
            )
        runner = ulf_fiber_cheap_runner or _load_analysis(
            "stnsnr_ulf_normative_fiber_sensitivity_observed"
        ).run_configured_cheap_observed_sensitivity
        result = runner(
            target,
            enabled_analyses=request.enabled_ulf_analyses,
            tau_multipliers=request.selected_tau_multipliers,
        )
        kind = "sensitivity_results"
    else:
        raise RecordError(f"unsupported configured sensitivity operation {stage!r}")
    if kind != expected_kind:
        raise RuntimeError("configured sensitivity dispatch returned the wrong artifact kind")
    if not isinstance(result, Mapping):
        raise RuntimeError("configured sensitivity backend must return a mapping")
    if _contains_classification_feedback(result):
        raise RecordError("sensitivity backend attempted to emit classification feedback")
    result_payload = _json_ready(result)

    output_path = target.output_root / f"{kind}.json"
    _write_json_atomic(
        output_path,
        {
            "schema_version": "stnsnr_configured_sensitivity_v1",
            "final_model_id": target.final_model_id,
            "final_record_hash": target.final_record_hash,
            "endpoint_model_id": request.final.endpoint_model_id,
            "model_family": family,
            "operation": stage,
            "final_branch": target.final_branch,
            "selected_tau": target.selected_tau,
            "selected_coverage": target.selected_coverage,
            "classification_feedback": "prohibited",
            "results": result_payload,
        },
    )
    return SensitivityServiceOutput(
        artifacts=(TaskArtifact(kind, output_path),),
        detail=f"configured_{stage}_completed",
    )


configured_sensitivity_runner = run_configured_sensitivity


__all__ = [
    "ConfiguredSensitivityTarget",
    "SUPPORTED_SENSITIVITY_OPERATIONS",
    "build_configured_sensitivity_target",
    "configured_sensitivity_runner",
    "run_configured_sensitivity",
]
