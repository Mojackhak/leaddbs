"""Configured adapter for the legacy ULF direct-voxel analysis backend."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..catalog import EndpointRecord
from ..executor import RunContext, TaskArtifact
from ..identity import canonical_hash
from ..planner import TaskSpec
from ..records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    HFSourceRecord,
    RecordError,
)
from .delta_hf import DeltaHFSupportAssessment, classify_delta_hf_support
from .observed import ObservedServiceOutput
from .ulf_observed import DeltaBuilderOutput, ULFObservedRequest

AnalysisRunner = Callable[..., dict[str, Any]]
FlipBackend = Callable[..., tuple[dict[str, list[Path]], dict[str, Any]]]


@dataclass(frozen=True)
class ConfiguredULFDirectPaths:
    """Explicit study paths that are intentionally absent from the branch request."""

    run_root: Path
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    brainmask: Path
    asset_root: Path
    readiness_csv: Path
    matlab_bin: Path

    def __post_init__(self) -> None:
        for field in (
            "run_root",
            "clinical_table",
            "stimulation_table",
            "derivatives_root",
            "brainmask",
            "asset_root",
            "readiness_csv",
            "matlab_bin",
        ):
            object.__setattr__(self, field, Path(getattr(self, field)).expanduser().resolve())


@dataclass(frozen=True)
class DeltaHFVoxelSupportQC:
    """Voxel-count support assessment with subject-ordered audit rows."""

    assessment: DeltaHFSupportAssessment
    rows: tuple[dict[str, Any], ...]
    fold_out_fractions: np.ndarray
    any_zero_total: bool


def score_delta_hf_locked_support(
    *,
    reference_exposure: np.ndarray,
    component_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Score continuous reference/component exposure inside each locked HF map support."""
    reference = np.asarray(reference_exposure, dtype=float)
    component = np.asarray(component_exposure, dtype=float)
    full = np.asarray(full_weights, dtype=float)
    folds = np.asarray(fold_weights, dtype=float)
    if reference.ndim != 2 or component.shape != reference.shape:
        raise RecordError("HF reference and add-on component exposure matrices must have equal 2D shapes")
    if not np.all(np.isfinite(reference)) or not np.all(np.isfinite(component)):
        raise RecordError("HF reference and add-on component exposure matrices must be finite")
    if full.shape != (reference.shape[1],):
        raise RecordError("selected full HF weights do not match the immutable feature axis")
    if folds.ndim != 2 or folds.shape[1] != reference.shape[1]:
        raise RecordError("selected fold HF weights do not match the immutable feature axis")
    full_support = np.isfinite(full)
    if not np.any(full_support):
        raise RecordError("selected full HF map has empty finite support")
    full_scores = np.mean(
        (component[:, full_support] - reference[:, full_support]) * full[full_support],
        axis=1,
    )
    fold_scores = np.empty((folds.shape[0], reference.shape[0]), dtype=float)
    for fold_index in range(folds.shape[0]):
        support = np.isfinite(folds[fold_index])
        if not np.any(support):
            raise RecordError(f"selected HF fold {fold_index + 1} has empty finite support")
        fold_scores[fold_index] = np.mean(
            (component[:, support] - reference[:, support]) * folds[fold_index, support],
            axis=1,
        )
    if not np.all(np.isfinite(full_scores)) or not np.all(np.isfinite(fold_scores)):
        raise RecordError("DeltaHFScore contains nonfinite values")
    return full_scores, fold_scores


def assess_delta_hf_voxel_support(
    *,
    component_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
    candidate_indices_in_support: np.ndarray | None = None,
    selected_tau: float,
    subject_order: tuple[str, ...],
) -> DeltaHFVoxelSupportQC:
    """Classify out-of-map support from suprathreshold HF-component voxel counts."""
    component = np.asarray(component_exposure, dtype=float)
    full = np.asarray(full_weights, dtype=float)
    folds = np.asarray(fold_weights, dtype=float)
    if component.ndim != 2 or component.shape[0] != len(subject_order):
        raise RecordError("HF-component exposure does not match the endpoint subject order")
    indices = (
        np.arange(component.shape[1], dtype=np.int64)
        if candidate_indices_in_support is None
        else np.asarray(candidate_indices_in_support, dtype=np.int64)
    )
    if full.shape != (indices.size,):
        raise RecordError("full HF weights do not match the immutable candidate axis")
    if folds.ndim != 2 or folds.shape[1] != indices.size:
        raise RecordError("fold HF weights do not match the immutable candidate axis")
    if (
        indices.ndim != 1
        or np.any(indices < 0)
        or np.any(indices >= component.shape[1])
        or np.unique(indices).size != indices.size
    ):
        raise RecordError("HF candidate indices are invalid in the support-QC voxel axis")
    if not np.all(np.isfinite(component)):
        raise RecordError("HF-component exposure must be finite for support QC")
    active = component > float(selected_tau)
    total_counts = np.count_nonzero(active, axis=1).astype(np.int64)
    full_support = np.zeros(component.shape[1], dtype=bool)
    full_support[indices] = np.isfinite(full)
    fold_support = np.zeros((folds.shape[0], component.shape[1]), dtype=bool)
    fold_support[:, indices] = np.isfinite(folds)
    if not np.any(full_support) or np.any(np.count_nonzero(fold_support, axis=1) == 0):
        raise RecordError("locked HF full/fold map support must be nonempty")
    full_out_counts = np.count_nonzero(active & ~full_support[None, :], axis=1).astype(np.int64)
    fold_out_counts = np.count_nonzero(
        active[None, :, :] & ~fold_support[:, None, :],
        axis=2,
    ).astype(np.int64)
    nonzero = total_counts > 0
    subject_fractions = np.ones(component.shape[0], dtype=float)
    subject_fractions[nonzero] = full_out_counts[nonzero] / total_counts[nonzero]
    fold_fractions = np.ones((folds.shape[0], component.shape[0]), dtype=float)
    fold_fractions[:, nonzero] = fold_out_counts[:, nonzero] / total_counts[None, nonzero]
    any_zero_total = bool(np.any(~nonzero))
    assessment = classify_delta_hf_support(
        subject_out_fractions=tuple(float(value) for value in subject_fractions),
        fold_out_fractions=tuple(float(value) for value in fold_fractions.ravel()),
        any_zero_total=any_zero_total,
        zero_status="invalid_no_hfcomponent_coverage",
    )
    rows = tuple(
        {
            "subject_id": subject,
            "total_suprathreshold_voxels": int(total_counts[index]),
            "full_in_support_voxels": int(total_counts[index] - full_out_counts[index]),
            "full_out_support_voxels": int(full_out_counts[index]),
            "full_out_support_fraction": float(subject_fractions[index]),
            "fold_out_support_fraction_median": float(np.median(fold_fractions[:, index])),
            "fold_out_support_fraction_max": float(np.max(fold_fractions[:, index])),
            "any_fold_out_fraction_gt_0_95": bool(np.any(fold_fractions[:, index] > 0.95)),
        }
        for index, subject in enumerate(subject_order)
    )
    return DeltaHFVoxelSupportQC(
        assessment=assessment,
        rows=rows,
        fold_out_fractions=fold_fractions,
        any_zero_total=any_zero_total,
    )


def _load_analysis_module():
    analysis_root = Path(__file__).resolve().parents[5] / "core" / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module("stnsnr_ulf_direct_voxel_observed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_npy_atomic(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("wb") as handle:
        np.save(handle, values)
    os.replace(temporary, path)


def _write_csv_atomic(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    if not rows:
        raise RecordError("support CSV requires at least one subject row")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _artifact_ref_for_output(
    path: Path,
    *,
    kind: str,
    task: TaskSpec,
    run_root: Path,
    shape: tuple[int, ...],
) -> ArtifactRef:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(run_root).as_posix()
    except ValueError as exc:
        raise RecordError(f"DeltaHF output escapes configured run root: {resolved}") from exc
    return ArtifactRef(task.task_id, kind, relative, _sha256(resolved), shape)


def _artifact_path(reference: ArtifactRef, run_root: Path) -> Path:
    path = Path(reference.relative_path)
    resolved = path.resolve() if path.is_absolute() else (run_root / path).resolve()
    if not resolved.is_relative_to(run_root):
        raise RecordError(f"DeltaHF artifact escapes configured run root: {reference.relative_path}")
    if not resolved.is_file():
        raise RecordError(f"DeltaHF artifact is missing: {resolved}")
    if _sha256(resolved) != reference.sha256:
        raise RecordError(f"DeltaHF artifact hash mismatch: {resolved}")
    return resolved


def _load_npy_artifact(
    reference: ArtifactRef,
    run_root: Path,
    *,
    dtype: Any,
) -> tuple[Path, np.ndarray]:
    path = _artifact_path(reference, run_root)
    values = np.asarray(np.load(path, allow_pickle=False), dtype=dtype)
    if tuple(int(value) for value in values.shape) != reference.shape:
        raise RecordError(f"immutable HF artifact shape metadata mismatch: {reference.kind}")
    return path, values


def _required_hf_artifacts(source: HFSourceRecord) -> dict[str, ArtifactRef]:
    by_kind: dict[str, ArtifactRef] = {}
    for artifact in source.artifacts:
        if artifact.kind in by_kind:
            raise RecordError(f"immutable HF source has duplicate artifact kind {artifact.kind!r}")
        by_kind[artifact.kind] = artifact
    required = {
        "selected_full_weights",
        "selected_fold_weights",
        "exposure_matrix",
        "candidate_flat_indices",
    }
    missing = sorted(required - set(by_kind))
    if missing:
        raise RecordError("immutable HF source is missing DeltaHF artifacts: " + ",".join(missing))
    return by_kind


@dataclass(frozen=True)
class ConfiguredULFDirectDeltaBuilder:
    """Callable DeltaBuilder for direct-voxel ULF preprocessing sidecars."""

    paths: ConfiguredULFDirectPaths
    flip_backend: FlipBackend

    def __call__(
        self,
        endpoint: EndpointRecord,
        source: HFSourceRecord,
        task: TaskSpec,
        context: RunContext,
    ) -> DeltaBuilderOutput:
        if endpoint.key.model_family != "ulf_voxel":
            raise RecordError("direct-voxel DeltaBuilder requires a ulf_voxel endpoint")
        if task.endpoint.identifier != endpoint.endpoint_model_id:
            raise RecordError("DeltaBuilder task endpoint does not match the endpoint record")
        if task.key.execution_stage != "preprocessing_sidecars":
            raise RecordError("DeltaBuilder may only run for preprocessing_sidecars")
        if not source.accepted or source.selected_tau is None or source.selected_coverage is None:
            raise RecordError("DeltaBuilder requires an accepted immutable HF source")
        if source.subject_order != endpoint.subject_ids:
            raise RecordError("immutable HF source subject order does not match the ULF endpoint")
        if source.feature_axis is None:
            raise RecordError("immutable HF source is missing its feature axis")
        run_root = Path(context.store.run_root).expanduser().resolve()
        if self.paths.run_root != run_root:
            raise RecordError("configured DeltaBuilder paths belong to a different run root")

        refs = _required_hf_artifacts(source)
        candidate_ref = refs["candidate_flat_indices"]
        if (
            source.feature_axis.sha256 != candidate_ref.sha256
            or candidate_ref.shape != (source.feature_axis.count,)
            or source.feature_axis.identity_source != "candidate_flat_indices"
        ):
            raise RecordError("immutable HF feature axis does not match candidate flat IDs")
        _, candidate_flat = _load_npy_artifact(candidate_ref, run_root, dtype=np.int64)
        _, full_weights = _load_npy_artifact(
            refs["selected_full_weights"], run_root, dtype=float
        )
        _, fold_weights = _load_npy_artifact(
            refs["selected_fold_weights"], run_root, dtype=float
        )
        _, reference_exposure = _load_npy_artifact(
            refs["exposure_matrix"], run_root, dtype=float
        )
        n_subjects = len(endpoint.subject_ids)
        n_features = source.feature_axis.count
        if candidate_flat.shape != (n_features,):
            raise RecordError("candidate flat-ID artifact shape does not match the HF feature axis")
        if full_weights.shape != (n_features,):
            raise RecordError("selected full-weight artifact shape does not match the HF feature axis")
        if fold_weights.shape != (n_subjects, n_features):
            raise RecordError(
                "selected fold-weight artifact must have shape n_folds x features with one fold per subject"
            )
        if reference_exposure.shape != (n_subjects, n_features):
            raise RecordError("HF reference exposure artifact does not match subject and feature identity")

        task_root = run_root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
        analysis = _load_analysis_module()
        _, _, _, right_support_flat = analysis.right_brainmask_voxels_from_path(
            self.paths.brainmask
        )
        candidate_indices = np.searchsorted(right_support_flat, candidate_flat)
        if (
            np.any(candidate_indices >= right_support_flat.size)
            or not np.array_equal(right_support_flat[candidate_indices], candidate_flat)
        ):
            raise RecordError("immutable HF candidate voxels are not contained in the right brainmask")
        component_support_exposure, component_qc = analysis.build_configured_hf_component_exposure_on_axis(
            subject_order=endpoint.subject_ids,
            outcome_protocol=endpoint.outcome_protocol,
            outcome_phase=endpoint.outcome_phase,
            readiness_csv=self.paths.readiness_csv,
            brainmask=self.paths.brainmask,
            asset_root=self.paths.asset_root,
            matlab_bin=self.paths.matlab_bin,
            candidate_flat=right_support_flat,
            sidecar_root=task_root,
            flip_backend=self.flip_backend,
        )
        component_exposure = component_support_exposure[:, candidate_indices]
        if component_exposure.shape != reference_exposure.shape:
            raise RecordError("HF-component exposure does not match immutable HF reference exposure")
        full_scores, fold_scores = score_delta_hf_locked_support(
            reference_exposure=reference_exposure,
            component_exposure=component_exposure,
            full_weights=full_weights,
            fold_weights=fold_weights,
        )
        support = assess_delta_hf_voxel_support(
            component_exposure=component_support_exposure,
            full_weights=full_weights,
            fold_weights=fold_weights,
            candidate_indices_in_support=candidate_indices,
            selected_tau=float(source.selected_tau),
            subject_order=endpoint.subject_ids,
        )

        full_path = task_root / "full.npy"
        folds_path = task_root / "folds.npy"
        support_path = task_root / "support.csv"
        support_qc_path = task_root / "support_qc.json"
        _write_npy_atomic(full_path, full_scores.astype(np.float64))
        _write_npy_atomic(folds_path, fold_scores.astype(np.float64))
        _write_csv_atomic(support_path, support.rows)
        _write_json_atomic(
            support_qc_path,
            {
                "status": support.assessment.status,
                "endpoint_model_id": endpoint.endpoint_model_id,
                "hf_source_record_hash": source.record_hash,
                "selected_hf_tau_v_per_m": float(source.selected_tau),
                "selected_hf_coverage": int(source.selected_coverage),
                "subject_order": list(endpoint.subject_ids),
                "support_definition": "HF-component suprathreshold voxel counts on locked HF map support",
                "threshold_rule": "E_HF_component > selected_hf_tau",
                "support_axis": "configured right-canonical brainmask",
                "support_axis_voxel_count": int(right_support_flat.size),
                "hf_candidate_axis_voxel_count": int(candidate_flat.size),
                "cohort_median_subject_out_fraction": support.assessment.cohort_median,
                "subject_fraction_over_0_50": support.assessment.subject_fraction_over_0_50,
                "subject_fraction_over_0_80": support.assessment.subject_fraction_over_0_80,
                "maximum_required_fraction": support.assessment.maximum_required_fraction,
                "any_zero_total": support.any_zero_total,
                "fold_out_fractions": support.fold_out_fractions.tolist(),
                "component_exposure_qc": component_qc,
                "immutable_hf_artifacts": {
                    kind: reference.as_dict() for kind, reference in sorted(refs.items())
                },
            },
        )
        full_ref = _artifact_ref_for_output(
            full_path,
            kind="delta_hf_full_scores",
            task=task,
            run_root=run_root,
            shape=(n_subjects,),
        )
        folds_ref = _artifact_ref_for_output(
            folds_path,
            kind="delta_hf_fold_scores",
            task=task,
            run_root=run_root,
            shape=(n_subjects, n_subjects),
        )
        support_ref = _artifact_ref_for_output(
            support_path,
            kind="delta_hf_support_rows",
            task=task,
            run_root=run_root,
            shape=(n_subjects,),
        )
        valid = support.assessment.valid
        bundle = DeltaHFBundle(
            input_status="valid" if valid else "invalid",
            support_status=support.assessment.status,
            selected_hf_tau=float(source.selected_tau),
            selected_hf_coverage=int(source.selected_coverage),
            full_scores=full_ref,
            fold_scores=folds_ref,
            support_rows=support_ref,
            failure_stage="" if valid else "support_qc",
            failure_detail="" if valid else support.assessment.status,
        )
        return DeltaBuilderOutput(
            bundle=bundle,
            artifacts=(
                TaskArtifact("delta_hf_full_scores", full_path),
                TaskArtifact("delta_hf_fold_scores", folds_path),
                TaskArtifact("delta_hf_support_rows", support_path),
                TaskArtifact("delta_hf_support_qc", support_qc_path),
            ),
        )


def configured_ulf_direct_delta_builder(
    *,
    paths: ConfiguredULFDirectPaths,
    flip_backend: FlipBackend,
) -> ConfiguredULFDirectDeltaBuilder:
    """Return a ULFObservedService-compatible direct-voxel DeltaBuilder."""
    return ConfiguredULFDirectDeltaBuilder(paths=paths, flip_backend=flip_backend)


def _copy_atomic(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)
    return destination


def _materialize_delta_inputs(
    request: ULFObservedRequest,
    paths: ConfiguredULFDirectPaths,
) -> tuple[Path, Path, Path, tuple[TaskArtifact, ...]]:
    bundle = request.delta_hf
    if bundle is None or not bundle.valid:
        raise RecordError("delta_hf_adjusted requires a valid adequate-or-limited DeltaHF bundle")
    assert bundle.full_scores is not None
    assert bundle.fold_scores is not None
    assert bundle.support_rows is not None
    source_by_kind = {
        "delta_hf_full_scores": _artifact_path(bundle.full_scores, paths.run_root),
        "delta_hf_fold_scores": _artifact_path(bundle.fold_scores, paths.run_root),
        "delta_hf_support_rows": _artifact_path(bundle.support_rows, paths.run_root),
    }
    destination_dir = request.output_root / "delta_hf_inputs" / bundle.record_hash
    copied = {
        kind: _copy_atomic(source, destination_dir / source.name)
        for kind, source in source_by_kind.items()
    }
    return (
        copied["delta_hf_full_scores"],
        copied["delta_hf_fold_scores"],
        copied["delta_hf_support_rows"],
        tuple(TaskArtifact(kind, copied[kind]) for kind in sorted(copied)),
    )


def _validate_branch_request(request: ULFObservedRequest) -> None:
    if request.hf_source.accepted:
        if request.hf_source.subject_order != request.endpoint.subject_ids:
            raise RecordError("matched HF source subject order does not match the ULF endpoint")
        if (
            float(request.hf_overlap_tau) != float(request.hf_source.selected_tau)
            or int(request.hf_overlap_coverage) != int(request.hf_source.selected_coverage)
        ):
            raise RecordError("selected HF tau/Coverage must drive ULF HF-overlap exclusion")
    elif not math.isinf(request.hf_overlap_tau) or request.hf_overlap_coverage is not None:
        raise RecordError("absent HF source requires infinite overlap tau and no overlap coverage")
    if request.branch == "no_delta_hf":
        if request.nuisance.columns != ("Y_HF_ref",):
            raise RecordError("no_delta_hf requires the Y_HF_ref-only nuisance plan")
        return
    if request.branch != "delta_hf_adjusted":
        raise RecordError(f"unsupported ULF direct-voxel branch {request.branch!r}")
    if not request.hf_source.accepted:
        raise RecordError("delta_hf_adjusted cannot run without an accepted matched HF source")
    if request.delta_hf is None or not request.delta_hf.valid:
        raise RecordError("delta_hf_adjusted requires a valid adequate-or-limited DeltaHF bundle")
    if request.nuisance.columns != ("Y_HF_ref", "DeltaHFScore"):
        raise RecordError("delta_hf_adjusted requires the branch-specific DeltaHFScore nuisance plan")
    if (
        float(request.hf_overlap_tau) != float(request.hf_source.selected_tau)
        or int(request.hf_overlap_coverage) != int(request.hf_source.selected_coverage)
        or float(request.delta_hf.selected_hf_tau) != float(request.hf_source.selected_tau)
        or int(request.delta_hf.selected_hf_coverage) != int(request.hf_source.selected_coverage)
    ):
        raise RecordError("selected HF tau/Coverage must drive overlap, DeltaHFScore, and support QC")


def _ensure_output_path(path: Path, *, task_root: Path, cache_root: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_relative_to(task_root) and not resolved.is_relative_to(cache_root):
        raise RecordError(f"configured ULF direct output escapes task/cache roots: {resolved}")
    if not resolved.is_file():
        raise RecordError(f"configured ULF direct output is missing: {resolved}")
    return resolved


def _optional_float(value: Any) -> float | None:
    return None if value in {None, ""} else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value in {None, ""} else int(value)


def run_configured_ulf_direct(
    request: ULFObservedRequest,
    *,
    paths: ConfiguredULFDirectPaths,
    flip_backend: FlipBackend,
    analysis_runner: AnalysisRunner | None = None,
) -> ObservedServiceOutput:
    """Run one configured ULF branch without consulting legacy scale or gate defaults."""
    _validate_branch_request(request)
    task_root = request.output_root.resolve()
    model_root = request.model_root.resolve()
    if not task_root.is_relative_to(model_root):
        raise RecordError("configured ULF direct task output must be nested under its model root")

    delta_full: Path | None = None
    delta_folds: Path | None = None
    delta_support: Path | None = None
    delta_artifacts: tuple[TaskArtifact, ...] = ()
    if request.branch == "delta_hf_adjusted":
        delta_full, delta_folds, delta_support, delta_artifacts = _materialize_delta_inputs(request, paths)

    analysis = _load_analysis_module()
    configuration_payload = {
        "endpoint_model_id": request.endpoint.endpoint_model_id,
        "branch": request.branch,
        "subject_order": request.endpoint.subject_ids,
        "tau_grid": request.tau_grid,
        "coverage_grid": request.coverage_grid,
        "primary_tau": request.primary_tau,
        "primary_coverage": request.primary_coverage,
        "hf_source_hash": request.hf_source.record_hash,
        "delta_hf_hash": (
            request.delta_hf.record_hash if request.branch == "delta_hf_adjusted" else "none"
        ),
    }
    cache_key = canonical_hash(configuration_payload)
    model_cache_root = model_root / "cache" / cache_key
    branch_name = analysis.ulf_direct_branch_name(
        request.branch,
        request.primary_tau,
        request.primary_coverage,
    )
    config = analysis.ConfiguredULFDirectVoxelRun(
        endpoint_id=request.endpoint.endpoint_model_id,
        scale_label=request.endpoint.scale_label,
        direction=request.endpoint.direction,
        outcome_protocol=request.endpoint.outcome_protocol,
        outcome_phase=request.endpoint.outcome_phase,
        hf_reference_protocol=request.endpoint.hf_reference_protocol,
        hf_reference_phase=request.endpoint.hf_reference_phase,
        subject_order=request.endpoint.subject_ids,
        branch=request.branch,
        branch_name=branch_name,
        nuisance_columns=request.nuisance.columns,
        clinical_table=paths.clinical_table,
        stimulation_table=paths.stimulation_table,
        derivatives_root=paths.derivatives_root,
        brainmask=paths.brainmask,
        asset_root=paths.asset_root,
        readiness_csv=paths.readiness_csv,
        matlab_bin=paths.matlab_bin,
        model_cache_root=model_cache_root,
        output_root=task_root,
        tau_grid=request.tau_grid,
        coverage_grid=request.coverage_grid,
        primary_tau=request.primary_tau,
        primary_coverage=request.primary_coverage,
        hf_overlap_tau=request.hf_overlap_tau,
        hf_overlap_coverage=request.hf_overlap_coverage,
        delta_hf_tau=(
            float(request.delta_hf.selected_hf_tau)
            if request.branch == "delta_hf_adjusted" and request.delta_hf is not None
            else None
        ),
        delta_hf_coverage=(
            int(request.delta_hf.selected_hf_coverage)
            if request.branch == "delta_hf_adjusted" and request.delta_hf is not None
            else None
        ),
        delta_full_scores=delta_full,
        delta_fold_scores=delta_folds,
        delta_support_rows=delta_support,
    )
    runner = analysis.run_configured_ulf_direct_voxel if analysis_runner is None else analysis_runner
    try:
        result = runner(config, flip_backend=flip_backend)
    except Exception:
        if request.branch == "delta_hf_adjusted":
            for path in (task_root / "source_status.json", task_root / "selected_source.json"):
                path.unlink(missing_ok=True)
        raise

    if str(result.get("branch", "")) != request.branch:
        raise RecordError("configured ULF direct backend returned a different branch")
    resolution = result["source_resolution"]
    selected_tau = _optional_float(resolution.get("selected_tau"))
    selected_coverage = _optional_int(resolution.get("selected_coverage"))
    expected_branch_name = (
        analysis.ulf_direct_branch_name(request.branch, selected_tau, selected_coverage)
        if selected_tau is not None and selected_coverage is not None
        else branch_name
    )
    if str(result.get("branch_name", "")) != expected_branch_name:
        raise RecordError("configured ULF direct backend returned a nonconfigured branch name")
    subject_order = tuple(str(value) for value in result.get("subject_ids", ()))
    if subject_order != request.endpoint.subject_ids:
        raise RecordError("configured ULF direct backend subject order mismatch")
    feature_ids_path = _ensure_output_path(
        Path(result["feature_ids_path"]),
        task_root=task_root,
        cache_root=model_cache_root,
    )
    feature_count = int(result["feature_count"])
    source_status_path = task_root / "source_status.json"
    selected_source_path = task_root / "selected_source.json"
    _write_json_atomic(
        source_status_path,
        {
            "endpoint_model_id": request.endpoint.endpoint_model_id,
            "branch": request.branch,
            "branch_name": expected_branch_name,
            "input_status": str(resolution.get("input_status", "valid")),
            "source_status": str(resolution["source_status"]),
            "prediction_status": str(resolution["prediction_status"]),
            "threshold_source": str(resolution["threshold_source"]),
        },
    )
    _write_json_atomic(
        selected_source_path,
        {
            "endpoint_model_id": request.endpoint.endpoint_model_id,
            "branch": request.branch,
            "selected_tau": _optional_float(resolution.get("selected_tau")),
            "selected_coverage": _optional_int(resolution.get("selected_coverage")),
            "adjacent_support": _optional_int(
                resolution.get("selected_adjacent_passing_grid_cells")
            ),
            "hf_source_record_hash": request.hf_source.record_hash,
            "delta_hf_record_hash": (
                request.delta_hf.record_hash if request.branch == "delta_hf_adjusted" else None
            ),
            "subject_order": list(subject_order),
        },
    )
    artifacts_by_kind = {
        str(kind): TaskArtifact(
            str(kind),
            _ensure_output_path(Path(path), task_root=task_root, cache_root=model_cache_root),
        )
        for kind, path in result.get("artifact_paths", {}).items()
    }
    artifacts_by_kind.update({artifact.kind: artifact for artifact in delta_artifacts})
    artifacts_by_kind["source_status"] = TaskArtifact("source_status", source_status_path)
    artifacts_by_kind["selected_source"] = TaskArtifact("selected_source", selected_source_path)
    artifacts = tuple(artifacts_by_kind[kind] for kind in sorted(artifacts_by_kind))
    return ObservedServiceOutput(
        source_status=str(resolution["source_status"]),
        prediction_status=str(resolution["prediction_status"]),
        threshold_source=str(resolution["threshold_source"]),
        selected_tau=selected_tau,
        selected_coverage=selected_coverage,
        adjacent_support=_optional_int(resolution.get("selected_adjacent_passing_grid_cells")),
        subject_order=subject_order,
        feature_axis=FeatureAxisRef(
            ids_path=feature_ids_path,
            count=feature_count,
            sha256=_sha256(feature_ids_path),
            identity_source="candidate_flat_indices",
        ),
        artifacts=artifacts,
        input_status=str(resolution.get("input_status", "valid")),
    )


def configured_ulf_direct_runner(
    *,
    paths: ConfiguredULFDirectPaths,
    flip_backend: FlipBackend,
    analysis_runner: AnalysisRunner | None = None,
) -> Callable[[ULFObservedRequest], ObservedServiceOutput]:
    """Bind explicit backend dependencies into a one-argument branch runner."""

    def run(request: ULFObservedRequest) -> ObservedServiceOutput:
        return run_configured_ulf_direct(
            request,
            paths=paths,
            flip_backend=flip_backend,
            analysis_runner=analysis_runner,
        )

    return run
