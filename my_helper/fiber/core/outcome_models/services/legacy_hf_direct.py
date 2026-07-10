"""Configured adapter for the legacy HF direct-voxel analysis backend."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ..executor import TaskArtifact
from .observed import FeatureAxisRef, HFDirectVoxelRequest, ObservedServiceOutput

AnalysisRunner = Callable[..., dict[str, Any]]
PreprocessRunner = Callable[..., dict[str, Any]]
FlipBackend = Callable[..., tuple[dict[str, list[Path]], dict[str, Any]]]


def _load_analysis_module():
    analysis_root = Path(__file__).resolve().parents[2] / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module("stnsnr_hf_direct_voxel_posthoc_threshold_scan")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _number_token(value: int | float) -> str:
    return f"{float(value):g}".replace("-", "neg").replace(".", "p")


def _build_analysis_config(request: HFDirectVoxelRequest, analysis: Any) -> Any:
    cache_name = (
        f"{request.endpoint.endpoint_model_id}__"
        f"candidate_tau{_number_token(request.candidate_threshold)}__"
        f"{request.endpoint.hf_reference_protocol}_{request.endpoint.hf_reference_phase}"
    )
    return analysis.ConfiguredHFDirectVoxelRun.from_request_values(
        endpoint_id=request.endpoint.endpoint_model_id,
        scale_label=request.endpoint.scale_label,
        direction=request.endpoint.direction,
        protocol=request.endpoint.hf_reference_protocol,
        phase=request.endpoint.hf_reference_phase,
        clinical_table=request.clinical_table,
        stimulation_table=request.stimulation_table,
        derivatives_root=request.derivatives_root,
        brainmask=request.brainmask,
        asset_root=request.asset_root,
        output_root=request.output_root,
        tau_grid=request.tau_grid,
        coverage_grid=request.coverage_grid,
        primary_tau=request.primary_tau,
        primary_coverage=request.primary_coverage,
        candidate_threshold=request.candidate_threshold,
        force=request.force,
        subject_order=request.endpoint.subject_ids,
        cache_root=request.model_root / "cache" / cache_name,
    )


def run_configured_hf_direct_sidecars(
    request: HFDirectVoxelRequest,
    *,
    flip_backend: FlipBackend,
    preprocess_runner: PreprocessRunner | None = None,
) -> tuple[TaskArtifact, ...]:
    """Build or validate the shared HF direct preprocess cache for Round 1."""
    minimum_tau = min(request.tau_grid)
    if request.candidate_threshold != minimum_tau:
        raise ValueError(
            "candidate_threshold must equal the minimum tau in the configured tau grid: "
            f"{request.candidate_threshold:g} != {minimum_tau:g}"
        )
    analysis = _load_analysis_module()
    config = _build_analysis_config(request, analysis)
    runner = analysis.load_or_build_configured_preprocess if preprocess_runner is None else preprocess_runner
    result = runner(config, flip_backend=flip_backend)
    qc_path = Path(result["preprocess_qc_path"])
    completion_path = Path(result["completion_manifest_path"])
    for label, path in (("preprocess QC", qc_path), ("completion manifest", completion_path)):
        if not path.is_file():
            raise RuntimeError(f"configured HF direct {label} is missing: {path}")
    sidecar_index = request.output_root / "sidecar_index.json"
    _write_json_atomic(
        sidecar_index,
        {
            "endpoint_model_id": request.endpoint.endpoint_model_id,
            "preprocess_status": str(result["preprocess_status"]),
            "cache_validation": str(result["preprocess_cache_validation"]),
            "cache_root": str(result["preprocess_dir"]),
            "completion_manifest": str(completion_path),
            "subject_order": [str(value) for value in result["subject_ids"]],
        },
    )
    return (
        TaskArtifact("sidecar_index", sidecar_index),
        TaskArtifact("qc", qc_path),
    )


def run_configured_hf_direct(
    request: HFDirectVoxelRequest,
    *,
    flip_backend: FlipBackend,
    analysis_runner: AnalysisRunner | None = None,
) -> ObservedServiceOutput:
    """Execute a configured request and translate legacy results to service output."""
    minimum_tau = min(request.tau_grid)
    if request.candidate_threshold != minimum_tau:
        raise ValueError(
            "candidate_threshold must equal the minimum tau in the configured tau grid: "
            f"{request.candidate_threshold:g} != {minimum_tau:g}"
        )
    analysis = _load_analysis_module()
    config = _build_analysis_config(request, analysis)
    runner = analysis.run_configured_hf_direct_voxel if analysis_runner is None else analysis_runner
    result = runner(config, flip_backend=flip_backend)
    resolution = result["source_resolution"]
    feature_ids_path = Path(result["feature_ids_path"])
    feature_count = int(result["feature_count"])
    subject_order = tuple(str(value) for value in result["subject_ids"])
    if subject_order != request.endpoint.subject_ids:
        raise RuntimeError(
            "configured HF direct backend subject order mismatch: "
            f"expected {list(request.endpoint.subject_ids)!r}, observed {list(subject_order)!r}"
        )
    if not feature_ids_path.is_file():
        raise RuntimeError(f"configured HF direct feature axis is missing: {feature_ids_path}")
    if feature_count < 0:
        raise RuntimeError("configured HF direct feature count must be nonnegative")
    source_status_path = request.output_root / "source_status.json"
    selected_source_path = request.output_root / "selected_source.json"
    _write_json_atomic(
        source_status_path,
        {
            "endpoint_model_id": request.endpoint.endpoint_model_id,
            "source_status": str(resolution["source_status"]),
            "prediction_status": str(resolution["prediction_status"]),
            "threshold_source": str(resolution["threshold_source"]),
        },
    )
    _write_json_atomic(
        selected_source_path,
        {
            "endpoint_model_id": request.endpoint.endpoint_model_id,
            "selected_tau": _optional_float(resolution.get("selected_tau")),
            "selected_coverage": _optional_int(resolution.get("selected_coverage")),
            "adjacent_support": _optional_int(
                resolution.get("selected_adjacent_passing_grid_cells")
            ),
            "subject_order": list(subject_order),
            "feature_axis": {
                "ids_path": str(feature_ids_path),
                "count": feature_count,
                "sha256": _sha256(feature_ids_path),
                "identity_source": "candidate_flat_indices",
            },
            "artifacts": {
                str(kind): str(path)
                for kind, path in sorted(result.get("artifact_paths", {}).items())
            },
        },
    )
    artifacts_by_kind = {
        str(kind): TaskArtifact(kind=str(kind), path=Path(path))
        for kind, path in result.get("artifact_paths", {}).items()
    }
    artifacts_by_kind["source_status"] = TaskArtifact("source_status", source_status_path)
    artifacts_by_kind["selected_source"] = TaskArtifact("selected_source", selected_source_path)
    artifacts = tuple(artifacts_by_kind[kind] for kind in sorted(artifacts_by_kind))
    return ObservedServiceOutput(
        source_status=str(resolution["source_status"]),
        prediction_status=str(resolution["prediction_status"]),
        threshold_source=str(resolution["threshold_source"]),
        selected_tau=_optional_float(resolution.get("selected_tau")),
        selected_coverage=_optional_int(resolution.get("selected_coverage")),
        adjacent_support=_optional_int(resolution.get("selected_adjacent_passing_grid_cells")),
        subject_order=subject_order,
        feature_axis=FeatureAxisRef(
            ids_path=feature_ids_path,
            count=feature_count,
            sha256=_sha256(feature_ids_path),
            identity_source="candidate_flat_indices",
        ),
        artifacts=artifacts,
    )


def configured_hf_direct_runner(
    *,
    flip_backend: FlipBackend,
    analysis_runner: AnalysisRunner | None = None,
) -> Callable[[HFDirectVoxelRequest], ObservedServiceOutput]:
    """Bind explicit backend dependencies into the one-argument service runner."""

    def run(request: HFDirectVoxelRequest) -> ObservedServiceOutput:
        return run_configured_hf_direct(
            request,
            flip_backend=flip_backend,
            analysis_runner=analysis_runner,
        )

    return run
