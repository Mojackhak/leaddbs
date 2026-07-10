"""Configured adapters for the legacy formal-inference numerical backends."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from ..executor import TaskArtifact
from ..records import ArtifactRef, RecordError
from .formal import FormalRequest, FormalServiceOutput


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


def _run_root(request: FormalRequest) -> Path:
    output_root = Path(request.output_root).expanduser().resolve()
    try:
        run_root = output_root.parents[3]
    except IndexError as exc:
        raise RecordError("formal output_root does not follow the configured run layout") from exc
    if output_root.parent.name != "tasks" or output_root.parents[2].name != "models":
        raise RecordError("formal output_root must be run_root/models/endpoint/tasks/task")
    return run_root


def _artifact_path(run_root: Path, artifact: ArtifactRef) -> Path:
    path = (run_root / artifact.relative_path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError(f"formal artifact escapes run root: {artifact.relative_path}") from exc
    if not path.is_file():
        raise RecordError(f"formal artifact is missing: {path}")
    if _sha256(path) != artifact.sha256:
        raise RecordError(f"formal artifact SHA-256 mismatch: {path}")
    return path


def _feature_axis_path(run_root: Path, request: FormalRequest) -> Path:
    path = Path(request.final.feature_axis.ids_path).expanduser()
    path = path.resolve() if path.is_absolute() else (run_root / path).resolve()
    if not path.is_file():
        raise RecordError(f"formal feature-axis artifact is missing: {path}")
    if _sha256(path) != request.final.feature_axis.sha256:
        raise RecordError(f"formal feature-axis SHA-256 mismatch: {path}")
    values = np.load(path, mmap_mode="r")
    if values.ndim != 1 or int(values.shape[0]) != request.final.feature_axis.count:
        raise RecordError("formal feature-axis count does not match its immutable record")
    return path


def _normalized_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _column(header: tuple[str, ...], canonical: str) -> str:
    expected = _normalized_column(canonical)
    matches = [value for value in header if _normalized_column(value) == expected]
    if len(matches) != 1:
        raise RecordError(f"formal scores require exactly one {canonical!r} column")
    return matches[0]


def _score_contract(
    path: Path,
    expected_subject_order: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        rows = list(reader)
    if not header or not rows:
        raise RecordError("formal scores artifact must contain a header and subject rows")
    subject_column = _column(header, "subject_id")
    score_order = tuple(str(row[subject_column]) for row in rows)
    if score_order != expected_subject_order:
        raise RecordError("formal scores subject order does not match the immutable final record")
    return header, score_order


def _output_prefix(final_model_id: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", final_model_id).strip("._")
    if not token:
        raise RecordError("final_model_id cannot form a formal output prefix")
    return token


def _delta_artifacts(request: FormalRequest) -> tuple[ArtifactRef, ArtifactRef]:
    nuisance = request.final.nuisance
    full = getattr(nuisance, "delta_hf_full_scores", None)
    folds = getattr(nuisance, "delta_hf_fold_scores", None)
    if not isinstance(full, ArtifactRef) or not isinstance(folds, ArtifactRef):
        raise RecordError(
            "FinalArtifactRecord.nuisance must carry DeltaHF full_scores and fold_scores "
            "ArtifactRef values for delta_hf_adjusted formal inference"
        )
    return full, folds


def build_configured_formal_target(request: FormalRequest) -> Any:
    """Build one exact numerical target without status or path discovery."""
    final = request.final
    if final.endpoint_model_id != request.task.endpoint.identifier:
        raise RecordError("formal final record belongs to another endpoint")
    if final.nuisance.branch != final.final_branch:
        raise RecordError("formal final branch and nuisance branch differ")
    delta_refs: tuple[ArtifactRef, ArtifactRef] | None = None
    if final.final_branch == "delta_hf_adjusted":
        delta_refs = _delta_artifacts(request)
    elif final.final_branch not in {"hf_source", "no_delta_hf"}:
        raise RecordError(f"unsupported formal final branch {final.final_branch!r}")

    run_root = _run_root(request)
    manifest_path = _artifact_path(run_root, final.manifest)
    exposure_path = _artifact_path(run_root, final.exposure)
    scores_path = _artifact_path(run_root, final.scores)
    feature_axis_path = _feature_axis_path(run_root, request)
    spatial_reference_ref = getattr(final, "spatial_reference", None)
    spatial_reference_path = (
        _artifact_path(run_root, spatial_reference_ref)
        if isinstance(spatial_reference_ref, ArtifactRef)
        else None
    )
    delta_full_path = _artifact_path(run_root, delta_refs[0]) if delta_refs is not None else None
    delta_fold_path = _artifact_path(run_root, delta_refs[1]) if delta_refs is not None else None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RecordError(f"cannot read immutable final manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise RecordError("immutable final manifest must be a JSON object")
    scale_direction = final.scale_direction
    manifest_direction = str(manifest.get("scale_direction", "")).strip().lower()
    if manifest_direction and manifest_direction != scale_direction:
        raise RecordError("final manifest scale_direction conflicts with the immutable final record")
    manifest_order_value = manifest.get("subject_order")
    if manifest_order_value is not None:
        if not isinstance(manifest_order_value, list):
            raise RecordError("final manifest subject_order must be a list when present")
        if tuple(str(value) for value in manifest_order_value) != final.subject_order:
            raise RecordError("final manifest subject_order conflicts with the immutable final record")
    header, subject_order = _score_contract(scores_path, final.subject_order)
    outcome_column = _column(header, "Y_post")
    nuisance_columns = tuple(
        _column(header, value)
        for value in final.nuisance.columns
        if _normalized_column(value) != _normalized_column("DeltaHFScore")
    )
    if not nuisance_columns:
        raise RecordError("formal nuisance design must retain a non-Delta baseline column")

    exposure = np.load(exposure_path, mmap_mode="r")
    expected_shape = tuple(final.exposure.shape)
    if exposure.ndim != 2:
        raise RecordError("formal exposure must be a subject-by-feature matrix")
    if expected_shape and tuple(int(value) for value in exposure.shape) != expected_shape:
        raise RecordError("formal exposure shape does not match its immutable artifact record")
    if exposure.shape != (len(subject_order), final.feature_axis.count):
        raise RecordError("formal exposure shape does not match subject and feature order")
    if final.scores.shape and tuple(final.scores.shape) != (len(subject_order),):
        raise RecordError("formal scores shape does not match subject order")
    if delta_refs is not None:
        full_values = np.load(delta_full_path, mmap_mode="r")
        fold_values = np.load(delta_fold_path, mmap_mode="r")
        if tuple(delta_refs[0].shape) != (len(subject_order),) or full_values.shape != (
            len(subject_order),
        ):
            raise RecordError("DeltaHF full_scores must have one value per formal subject")
        if tuple(delta_refs[1].shape) != (len(subject_order), len(subject_order)) or fold_values.shape != (
            len(subject_order),
            len(subject_order),
        ):
            raise RecordError("DeltaHF fold_scores must be fold-by-subject in formal subject order")

    request.output_root.mkdir(parents=True, exist_ok=True)
    prefix = _output_prefix(final.final_model_id)
    family = request.task.endpoint.model_family
    common = {
        "model_id": final.final_model_id,
        "manifest_path": manifest_path,
        "branch_dir": request.output_root,
        "outcome_column": outcome_column,
        "nuisance_columns": nuisance_columns,
        "scale_direction": scale_direction,
        "tau": float(final.selected_tau),
        "min_coverage": int(final.selected_coverage),
        "subject_order": subject_order,
        "output_prefix": prefix,
        "final_record_hash": final.record_hash,
        "delta_hf_full_path": delta_full_path,
        "delta_hf_fold_path": delta_fold_path,
    }
    if family in {"hf_voxel", "ulf_voxel"}:
        module = _load_analysis("stnsnr_direct_voxel_formal_permutation")
        return module.DirectVoxelTarget(
            **common,
            x_path=exposure_path,
            subjects_csv=scores_path,
            feature_ids_path=feature_axis_path,
            spatial_reference_path=spatial_reference_path,
        )
    if family in {"hf_fiber", "ulf_fiber"}:
        module = _load_analysis("stnsnr_normative_fiber_smoke_permutation")
        return module.NormativeFiberTarget(
            **common,
            x_path=exposure_path,
            fiber_ids_path=feature_axis_path,
            scores_csv=scores_path,
        )
    raise RecordError(f"unsupported formal model family {family!r}")


def _summary_path(result: Mapping[str, Any], expected: Path) -> Path:
    value = result.get("summary_csv")
    path = Path(str(value)) if value else expected
    if not path.is_file():
        raise RuntimeError(f"configured formal backend did not write its summary: {path}")
    return path


def run_configured_formal(
    request: FormalRequest,
    *,
    direct_permutation_runner: Callable[..., Mapping[str, Any]] | None = None,
    direct_bootstrap_runner: Callable[..., Mapping[str, Any]] | None = None,
    fiber_permutation_runner: Callable[..., Mapping[str, Any]] | None = None,
    fiber_bootstrap_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> FormalServiceOutput:
    """Run the operation encoded by one final-record-bound formal request."""
    target = build_configured_formal_target(request)
    stage = request.task.key.execution_stage
    prefix = target.output_prefix
    artifacts: list[TaskArtifact] = []
    if request.task.endpoint.model_family in {"hf_voxel", "ulf_voxel"}:
        if stage == "formal_permutation":
            runner = direct_permutation_runner or _load_analysis(
                "stnsnr_direct_voxel_formal_permutation"
            ).run_target_permutation
            result = runner(target, n_permutations=request.permutations, seed=request.seed)
            path = _summary_path(result, target.branch_dir / f"{prefix}_permutation_summary.csv")
            artifacts.append(TaskArtifact("permutation_results", path))
        elif stage == "formal_bootstrap":
            if direct_bootstrap_runner is None and target.spatial_reference_path is None:
                raise RecordError(
                    "FinalArtifactRecord must carry a spatial_reference ArtifactRef "
                    "for configured direct-voxel bootstrap"
                )
            runner = direct_bootstrap_runner or _load_analysis(
                "stnsnr_direct_voxel_formal_bootstrap"
            ).run_target_bootstrap
            result = runner(target, n_bootstraps=request.bootstraps, seed=request.seed)
            path = _summary_path(result, target.branch_dir / f"{prefix}_bootstrap_summary.csv")
            artifacts.append(TaskArtifact("bootstrap_results", path))
        else:
            raise RecordError(f"unsupported direct formal stage {stage!r}")
    elif request.task.endpoint.model_family in {"hf_fiber", "ulf_fiber"}:
        if stage != "formal_permutation_bootstrap":
            raise RecordError(f"unsupported normative-fiber formal stage {stage!r}")
        permutation = fiber_permutation_runner or _load_analysis(
            "stnsnr_normative_fiber_smoke_permutation"
        ).run_target_smoke_permutation
        bootstrap = fiber_bootstrap_runner or _load_analysis(
            "stnsnr_normative_fiber_formal_bootstrap"
        ).run_target_bootstrap
        permutation_result = permutation(
            target,
            n_permutations=request.permutations,
            seed=request.seed,
            tier="formal",
        )
        bootstrap_result = bootstrap(
            target,
            n_bootstraps=request.bootstraps,
            seed=request.seed,
        )
        artifacts.extend(
            (
                TaskArtifact(
                    "permutation_results",
                    _summary_path(
                        permutation_result,
                        target.branch_dir / f"{prefix}_permutation_summary.csv",
                    ),
                ),
                TaskArtifact(
                    "bootstrap_results",
                    _summary_path(
                        bootstrap_result,
                        target.branch_dir / f"{prefix}_bootstrap_summary.csv",
                    ),
                ),
            )
        )
    else:  # pragma: no cover - guarded by target construction.
        raise RecordError(f"unsupported formal model family {request.task.endpoint.model_family!r}")
    return FormalServiceOutput(tuple(artifacts), detail="configured_formal_inference_completed")


configured_formal_runner = run_configured_formal


__all__ = [
    "build_configured_formal_target",
    "configured_formal_runner",
    "run_configured_formal",
]
