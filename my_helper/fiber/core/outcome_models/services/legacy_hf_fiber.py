"""Configured service adapter for the legacy HF normative-fiber analysis."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from ..executor import TaskArtifact
from .observed import FeatureAxisRef, HFNormativeFiberRequest, ObservedServiceOutput


@dataclass(frozen=True)
class HFNormativeFiberResolverPolicy:
    """Resolver stability policy not represented by the legacy request type."""

    minimum_adjacent_passing_cells: int = 2

    def __post_init__(self) -> None:
        if self.minimum_adjacent_passing_cells < 1:
            raise ValueError("minimum_adjacent_passing_cells must be positive")


@dataclass(frozen=True)
class HFNormativeFiberRuntime:
    """Operational controls that do not change the configured scientific model."""

    max_fibers: int = 0
    fiber_chunk_size: int = 10000
    matlab_bin: Path | None = None

    def __post_init__(self) -> None:
        if self.max_fibers < 0:
            raise ValueError("max_fibers cannot be negative")
        if self.fiber_chunk_size < 1:
            raise ValueError("fiber_chunk_size must be positive")


def _import_legacy_analysis() -> ModuleType:
    analysis_dir = Path(__file__).resolve().parents[2] / "analysis"
    path_token = str(analysis_dir)
    if path_token not in sys.path:
        sys.path.insert(0, path_token)
    return importlib.import_module("stnsnr_hf_normative_fiber_smoke")


def _load_legacy_analysis() -> ModuleType:
    return _import_legacy_analysis()


def build_legacy_hf_fiber_config(
    request: HFNormativeFiberRequest,
    *,
    resolver_policy: HFNormativeFiberResolverPolicy = HFNormativeFiberResolverPolicy(),
    runtime: HFNormativeFiberRuntime | None = None,
    max_fibers: int | None = None,
) -> Any:
    """Translate a configured request into the analysis module's dependency-free type."""
    legacy = _import_legacy_analysis()
    options = runtime or HFNormativeFiberRuntime(max_fibers=max_fibers or 0)
    if max_fibers is not None and runtime is not None and int(max_fibers) != runtime.max_fibers:
        raise ValueError("max_fibers conflicts with runtime.max_fibers")
    effective_max_fibers = options.max_fibers if max_fibers is None else int(max_fibers)
    cache_key = legacy.configured_sidecar_cache_key(
        clinical_table=request.clinical_table,
        stimulation_table=request.stimulation_table,
        connectome_path=request.connectome.path,
        scale=request.endpoint.scale_label,
        protocol=request.endpoint.outcome_protocol,
        phase=request.endpoint.outcome_phase,
        subject_order=request.endpoint.subject_ids,
        max_fibers=effective_max_fibers,
    )
    matlab_bin = options.matlab_bin or legacy.DEFAULT_MATLAB
    return legacy.HFNormativeFiberAnalysisConfig(
        scale=request.endpoint.scale_label,
        endpoint_protocol=request.endpoint.outcome_protocol,
        endpoint_phase=request.endpoint.outcome_phase,
        scale_direction=request.endpoint.direction,
        subject_order=tuple(request.endpoint.subject_ids),
        clinical_table=Path(request.clinical_table),
        stimulation_table=Path(request.stimulation_table),
        derivatives_root=Path(request.derivatives_root),
        repo_root=legacy.repo_root_from_file(),
        matlab_bin=Path(matlab_bin),
        connectome_id=request.connectome.connectome_id,
        connectome_label=request.connectome.label,
        connectome_path=Path(request.connectome.path),
        connectome_identity_source=request.connectome.fiber_identity_source,
        output_dir=Path(request.output_root),
        preprocess_dir=Path(request.model_root) / "cache" / f"hf_fiber_{cache_key}",
        tau_grid=tuple(float(value) for value in request.tau_grid),
        coverage_grid=tuple(int(value) for value in request.coverage_grid),
        primary_tau=float(request.primary_tau),
        primary_coverage=int(request.primary_coverage),
        sweet_fraction=float(request.score["sweet_fraction"]),
        sour_fraction=float(request.score["sour_fraction"]),
        weighted_peak_fraction=float(request.score["weighted_peak_fraction"]),
        sweet_selected_min_count=int(request.score["sweet_selected_min_count"]),
        sour_selected_min_count=int(request.score["sour_selected_min_count"]),
        weighted_peak_min_count=int(request.score["weighted_peak_min_count"]),
        sensitivity_high_tau=float(request.cheap_observed_sensitivity["high_tau_v_per_m"]),
        sensitivity_coverage=int(request.cheap_observed_sensitivity["coverage"]),
        sensitivity_sweet_count=int(request.cheap_observed_sensitivity["sweet_top_count"]),
        sensitivity_sour_count=int(request.cheap_observed_sensitivity["sour_top_count"]),
        resolver_minimum_adjacent_passing_cells=resolver_policy.minimum_adjacent_passing_cells,
        max_fibers=effective_max_fibers,
        fiber_chunk_size=options.fiber_chunk_size,
        force_flip=bool(request.force),
        force_rebuild=bool(request.force),
        dynamic_names=True,
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _observed_output(
    payload: Mapping[str, Any],
    request: HFNormativeFiberRequest,
) -> ObservedServiceOutput:
    axis_payload = payload.get("feature_axis")
    if not isinstance(axis_payload, Mapping):
        raise RuntimeError("configured HF fiber backend did not return a feature axis")
    feature_axis = FeatureAxisRef(
        ids_path=Path(str(axis_payload["ids_path"])),
        count=int(axis_payload["count"]),
        sha256=str(axis_payload["sha256"]),
        identity_source=str(axis_payload["identity_source"]),
    )
    if not feature_axis.ids_path.is_file():
        raise RuntimeError(f"configured HF fiber feature axis is missing: {feature_axis.ids_path}")
    if feature_axis.count < 0:
        raise RuntimeError("configured HF fiber feature count must be nonnegative")
    if feature_axis.identity_source != request.connectome.fiber_identity_source:
        raise RuntimeError(
            "configured HF fiber feature identity source mismatch: "
            f"expected {request.connectome.fiber_identity_source!r}, observed {feature_axis.identity_source!r}"
        )
    artifact_payload = payload.get("artifacts", {})
    if not isinstance(artifact_payload, Mapping):
        raise RuntimeError("configured HF fiber backend returned invalid artifacts")
    source_status = str(payload["source_status"])
    accepted_required = {
        "source_status",
        "selected_source",
        "selected_manifest",
        "exposure_matrix",
        "selected_scores",
        "selected_full_weights",
        "selected_fold_weights",
        "selected_fold_scores",
    }
    if source_status in {"pre_specified_accepted", "scan_fallback_accepted"}:
        missing = sorted(accepted_required - set(artifact_payload))
        if missing:
            raise RuntimeError("accepted configured HF fiber source is missing artifacts: " + ",".join(missing))
    artifacts = tuple(
        TaskArtifact(kind=str(kind), path=Path(str(path)))
        for kind, path in sorted(artifact_payload.items())
    )
    for artifact in artifacts:
        if not artifact.path.is_file():
            raise RuntimeError(f"configured HF fiber artifact is missing: {artifact.kind}:{artifact.path}")
        try:
            artifact.path.resolve().relative_to(request.model_root.resolve())
        except ValueError as exc:
            raise RuntimeError(f"configured HF fiber artifact is outside model root: {artifact.kind}") from exc
    subject_order = payload.get("subject_order", ())
    if not isinstance(subject_order, (list, tuple)):
        raise RuntimeError("configured HF fiber backend returned invalid subject order")
    normalized_subject_order = tuple(str(value) for value in subject_order)
    if normalized_subject_order != request.endpoint.subject_ids:
        raise RuntimeError(
            "configured HF fiber backend subject order mismatch: "
            f"expected {list(request.endpoint.subject_ids)!r}, observed {list(normalized_subject_order)!r}"
        )
    return ObservedServiceOutput(
        source_status=source_status,
        prediction_status=str(payload["prediction_status"]),
        threshold_source=str(payload["threshold_source"]),
        selected_tau=_optional_float(payload.get("selected_tau")),
        selected_coverage=_optional_int(payload.get("selected_coverage")),
        adjacent_support=_optional_int(payload.get("adjacent_support")),
        subject_order=normalized_subject_order,
        feature_axis=feature_axis,
        artifacts=artifacts,
    )


def run_configured_hf_fiber_primary(
    request: HFNormativeFiberRequest,
    *,
    runtime: HFNormativeFiberRuntime | None = None,
) -> ObservedServiceOutput:
    """Run the pre-specified HF fiber cell for one configured endpoint."""
    legacy = _load_legacy_analysis()
    config = build_legacy_hf_fiber_config(request, runtime=runtime)
    return _observed_output(legacy.run_hf_normative_fiber_primary_configured(config), request)


def run_configured_hf_fiber_resolver(
    request: HFNormativeFiberRequest,
    *,
    resolver_policy: HFNormativeFiberResolverPolicy = HFNormativeFiberResolverPolicy(),
    runtime: HFNormativeFiberRuntime | None = None,
) -> ObservedServiceOutput:
    """Resolve a configured HF fiber source from its declared grid and policy."""
    legacy = _load_legacy_analysis()
    config = build_legacy_hf_fiber_config(
        request,
        resolver_policy=resolver_policy,
        runtime=runtime,
    )
    return _observed_output(legacy.run_hf_normative_fiber_resolver_configured(config), request)


def _configured_artifact_output(
    payload: Mapping[str, Any],
    request: HFNormativeFiberRequest,
    *,
    expected_kinds: frozenset[str],
) -> tuple[TaskArtifact, ...]:
    artifact_payload = payload.get("artifacts")
    if not isinstance(artifact_payload, Mapping):
        raise RuntimeError("configured HF fiber stage did not return artifacts")
    observed_kinds = {str(kind) for kind in artifact_payload}
    if observed_kinds != expected_kinds:
        raise RuntimeError(
            "configured HF fiber stage artifact mismatch: "
            f"expected={sorted(expected_kinds)!r}, observed={sorted(observed_kinds)!r}"
        )
    artifacts = tuple(
        TaskArtifact(kind=str(kind), path=Path(str(path)))
        for kind, path in sorted(artifact_payload.items())
    )
    for artifact in artifacts:
        if not artifact.path.is_file():
            raise RuntimeError(f"configured HF fiber stage artifact is missing: {artifact.kind}:{artifact.path}")
        try:
            artifact.path.resolve().relative_to(request.output_root.resolve())
        except ValueError as exc:
            raise RuntimeError(f"configured HF fiber task artifact is outside task output root: {artifact.kind}") from exc
    return artifacts


def run_configured_hf_fiber_sidecar(
    request: HFNormativeFiberRequest,
    *,
    runtime: HFNormativeFiberRuntime | None = None,
) -> tuple[TaskArtifact, ...]:
    """Build or strictly reuse Round 1 sidecars and return planner artifact kinds."""
    legacy = _load_legacy_analysis()
    config = build_legacy_hf_fiber_config(request, runtime=runtime)
    payload = legacy.run_hf_normative_fiber_sidecar_configured(config)
    return _configured_artifact_output(payload, request, expected_kinds=frozenset({"sidecar_index", "qc"}))


def run_configured_hf_fiber_control(
    request: HFNormativeFiberRequest,
    *,
    runtime: HFNormativeFiberRuntime | None = None,
) -> tuple[TaskArtifact, ...]:
    """Run Round 3 plain connected-streamline control."""
    legacy = _load_legacy_analysis()
    config = build_legacy_hf_fiber_config(request, runtime=runtime)
    payload = legacy.run_hf_normative_fiber_plain_connected_control_configured(config)
    return _configured_artifact_output(payload, request, expected_kinds=frozenset({"control_metrics"}))


def run_configured_hf_fiber_sensitivity(
    request: HFNormativeFiberRequest,
    *,
    runtime: HFNormativeFiberRuntime | None = None,
) -> tuple[TaskArtifact, ...]:
    """Run Round 5 fixed high-tau and fixed top-count observed sensitivities."""
    legacy = _load_legacy_analysis()
    config = build_legacy_hf_fiber_config(request, runtime=runtime)
    payload = legacy.run_hf_normative_fiber_cheap_observed_sensitivity_configured(config)
    return _configured_artifact_output(payload, request, expected_kinds=frozenset({"sensitivity_results"}))


configured_hf_fiber_primary_runner = run_configured_hf_fiber_primary
configured_hf_fiber_resolver_runner = run_configured_hf_fiber_resolver
configured_hf_fiber_sidecar_runner = run_configured_hf_fiber_sidecar
configured_hf_fiber_control_runner = run_configured_hf_fiber_control
configured_hf_fiber_sensitivity_runner = run_configured_hf_fiber_sensitivity


__all__ = [
    "HFNormativeFiberResolverPolicy",
    "HFNormativeFiberRuntime",
    "build_legacy_hf_fiber_config",
    "configured_hf_fiber_control_runner",
    "configured_hf_fiber_primary_runner",
    "configured_hf_fiber_resolver_runner",
    "configured_hf_fiber_sensitivity_runner",
    "configured_hf_fiber_sidecar_runner",
    "run_configured_hf_fiber_control",
    "run_configured_hf_fiber_primary",
    "run_configured_hf_fiber_resolver",
    "run_configured_hf_fiber_sensitivity",
    "run_configured_hf_fiber_sidecar",
]
