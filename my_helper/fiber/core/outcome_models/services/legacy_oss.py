"""Configured adapter for the normative-fiber OSS/pPAM numerical backend."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping

import numpy as np

from ..executor import TaskArtifact
from ..records import ArtifactRef, RecordError
from .formal import FormalRequest
from .legacy_formal import build_configured_formal_target
from .oss import OSSRequest, OSSServiceOutput


_PROHIBITED_FEEDBACK_KEYS = {
    "source_status",
    "prediction_status",
    "threshold_source",
    "final_role",
    "ulf_endpoint_model_status",
}
_PROHIBITED_FEEDBACK_SUFFIXES = (
    "_source_status",
    "_prediction_status",
    "_threshold_source",
    "_endpoint_model_status",
    "_branch_role",
    "_final_role",
)


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


def _run_root(request: OSSRequest) -> Path:
    output_root = Path(request.output_root).expanduser().resolve()
    try:
        run_root = output_root.parents[3]
    except IndexError as exc:
        raise RecordError("OSS output_root does not follow the configured run layout") from exc
    if output_root.parent.name != "tasks" or output_root.parents[2].name != "models":
        raise RecordError("OSS output_root must be run_root/models/endpoint/tasks/task")
    return run_root


def _artifact_path(run_root: Path, artifact: ArtifactRef) -> Path:
    path = (run_root / artifact.relative_path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError(f"OSS artifact escapes run root: {artifact.relative_path}") from exc
    if not path.is_file():
        raise RecordError(f"OSS artifact is missing: {path}")
    if _sha256(path) != artifact.sha256:
        raise RecordError(f"OSS artifact SHA-256 mismatch: {path}")
    return path


def _feature_axis_path(run_root: Path, request: OSSRequest) -> Path:
    path = Path(request.final.feature_axis.ids_path).expanduser()
    path = path.resolve() if path.is_absolute() else (run_root / path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise RecordError("OSS final feature-axis artifact is outside the configured run root") from exc
    if not path.is_file():
        raise RecordError(f"OSS final feature-axis artifact is missing: {path}")
    if _sha256(path) != request.final.feature_axis.sha256:
        raise RecordError("OSS final feature-axis SHA-256 mismatch")
    return path


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read OSS {label}: {path}") from exc
    if not isinstance(value, dict):
        raise RecordError(f"OSS {label} must be a JSON object")
    return value


def _subject_order(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        return tuple(item for item in value.split(";") if item)
    raise RecordError("OSS manifest subject_order must be a list or semicolon-delimited string")


def _required_text(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value:
        raise RecordError(f"OSS {label} is missing {key}")
    return value


def _required_float(mapping: Mapping[str, Any], key: str, label: str) -> float:
    if key not in mapping:
        raise RecordError(f"OSS {label} is missing {key}")
    try:
        value = float(mapping[key])
    except (TypeError, ValueError) as exc:
        raise RecordError(f"OSS {label} field {key} must be numeric") from exc
    if not np.isfinite(value) or value <= 0:
        raise RecordError(f"OSS {label} field {key} must be finite and positive")
    return value


def _validate_manifest_identity(
    request: OSSRequest,
    parameter: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> tuple[float, str, str | None]:
    final = request.final
    for label, payload in (("parameter manifest", parameter), ("activation metadata", metadata)):
        if _required_text(payload, "final_model_id", label) != final.final_model_id:
            raise RecordError(f"OSS {label} final_model_id mismatch")
        if _required_text(payload, "final_record_hash", label) != final.record_hash:
            raise RecordError(f"OSS {label} final-record hash mismatch")
        if _subject_order(payload.get("subject_order")) != final.subject_order:
            raise RecordError(f"OSS {label} subject order mismatch")
        if _required_text(payload, "canonical_hemisphere", label).lower() != "right":
            raise RecordError(f"OSS {label} is not right-canonical")
        if (
            _required_text(payload, "left_to_right_mapping_method", label)
            != "homologous_right_fiber_id"
        ):
            raise RecordError(f"OSS {label} lacks homologous left-to-right fiber mapping")
        if (
            _required_text(payload, "hemisphere_source_merge_rule", label)
            != request.hemisphere_merge_rule
        ):
            raise RecordError(f"OSS {label} hemisphere merge rule mismatch")

    if _required_text(parameter, "oss_model", "parameter manifest") != request.oss_model:
        raise RecordError("OSS model provenance mismatch")
    if (
        _required_text(parameter, "activation_model", "parameter manifest")
        != request.activation_model
    ):
        raise RecordError("OSS activation-model provenance mismatch")
    if _required_text(parameter, "connectome", "parameter manifest").lower() != "dtor":
        raise RecordError("OSS parameter manifest must identify the dTOR connectome")
    if _required_text(parameter, "endpoint_id", "parameter manifest") != final.endpoint_model_id:
        raise RecordError("OSS endpoint provenance mismatch")
    if float(parameter.get("selected_tau", np.nan)) != final.selected_tau:
        raise RecordError("OSS selected tau provenance mismatch")
    if int(parameter.get("selected_coverage", -1)) != final.selected_coverage:
        raise RecordError("OSS selected Coverage provenance mismatch")
    if (
        _required_text(parameter, "selected_source_feature_axis_sha256", "parameter manifest")
        != final.feature_axis.sha256
    ):
        raise RecordError("OSS selected-source feature-axis provenance mismatch")
    component = _required_text(parameter, "oss_exposure_component", "parameter manifest")
    if component != request.expected_component:
        raise RecordError(
            f"OSS exposure component mismatch: expected {request.expected_component}, got {component}"
        )
    hf_overlap_definition = None
    if request.task.endpoint.model_family == "ulf_fiber":
        if parameter.get("hf_overlap_exclusion_applied") is not True:
            raise RecordError("ULF OSS sidecar must apply the matched HF-overlap exclusion")
        hf_overlap_definition = _required_text(
            parameter,
            "hf_overlap_definition",
            "parameter manifest",
        )
        if hf_overlap_definition not in {
            "matched_hf_peak_efield_selected_tau",
            "hf_source_absent_all_false",
        }:
            raise RecordError("ULF OSS HF-overlap definition is invalid")

    requested_frequency = _required_float(
        parameter,
        "requested_frequency_hz",
        "parameter manifest",
    )
    modeled_frequency = _required_float(
        parameter,
        "oss_parameter_frequency_hz",
        "parameter manifest",
    )
    if requested_frequency != modeled_frequency:
        raise RecordError(
            "OSS requested frequency does not equal the modeled parameter frequency"
        )
    if "verified" not in _required_text(
        parameter,
        "frequency_validation_status",
        "parameter manifest",
    ).lower():
        raise RecordError("OSS frequency validation status is not verified")
    if not _required_text(parameter, "frequency_source", "parameter manifest"):
        raise RecordError("OSS frequency source is missing")
    if parameter.get("missing_subjects") not in ([], ()):
        raise RecordError("OSS sidecar has missing subjects")
    if parameter.get("failed_subjects") not in ([], ()):
        raise RecordError("OSS sidecar has failed subjects")

    activation_type = _required_text(
        metadata,
        "activation_value_type",
        "activation metadata",
    )
    if activation_type != "pPAM_activation_probability":
        raise RecordError("OSS activation metadata must contain pPAM probabilities")
    if _required_text(metadata, "finite_check_status", "activation metadata") != "passed":
        raise RecordError("OSS activation metadata finite check did not pass")
    return requested_frequency, component, hf_overlap_definition


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        temporary.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_npy(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}.npy")
    try:
        np.save(temporary, values)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class ConfiguredOSSTarget:
    model_id: str
    final_record_hash: str
    model_family: str
    output_root: Path
    output_prefix: str
    probability_path: Path
    fit_activation_path: Path
    fiber_ids_path: Path
    scores_csv: Path
    outcome_column: str
    nuisance_columns: tuple[str, ...]
    delta_hf_full_path: Path | None
    delta_hf_fold_path: Path | None
    scale_direction: str
    subject_order: tuple[str, ...]
    activation_threshold: float
    requested_frequency_hz: float
    exposure_component: str
    hf_overlap_definition: str | None
    parameter_manifest_path: Path
    activation_metadata_path: Path


def build_configured_oss_target(request: OSSRequest) -> ConfiguredOSSTarget:
    """Validate one explicit OSS sidecar bundle and build its locked fit target."""
    run_root = _run_root(request)
    probability_path = _artifact_path(
        run_root,
        request.sidecars.activation_probabilities,
    )
    sidecar_fiber_path = _artifact_path(run_root, request.sidecars.fiber_ids)
    parameter_path = _artifact_path(run_root, request.sidecars.parameter_manifest)
    metadata_path = _artifact_path(run_root, request.sidecars.activation_metadata)
    final_fiber_path = _feature_axis_path(run_root, request)
    parameter = _json_object(parameter_path, "parameter manifest")
    metadata = _json_object(metadata_path, "activation metadata")
    requested_frequency, component, hf_overlap_definition = _validate_manifest_identity(
        request,
        parameter,
        metadata,
    )

    if _required_text(parameter, "oss_fiber_ids_sha256", "parameter manifest") != request.sidecars.fiber_ids.sha256:
        raise RecordError("OSS parameter-manifest fiber hash mismatch")
    if _required_text(metadata, "oss_fiber_ids_sha256", "activation metadata") != request.sidecars.fiber_ids.sha256:
        raise RecordError("OSS activation-metadata fiber hash mismatch")
    sidecar_ids = np.asarray(np.load(sidecar_fiber_path, mmap_mode="r"))
    final_ids = np.asarray(np.load(final_fiber_path, mmap_mode="r"))
    expected_count = request.final.feature_axis.count
    if sidecar_ids.ndim != 1 or sidecar_ids.shape != (expected_count,):
        raise RecordError("OSS fiber axis shape does not match the immutable final record")
    if final_ids.ndim != 1 or final_ids.shape != (expected_count,):
        raise RecordError("final fiber axis shape is invalid")
    if not np.array_equal(sidecar_ids, final_ids):
        raise RecordError("OSS fiber order differs from the immutable final feature axis")

    probabilities = np.asarray(np.load(probability_path, mmap_mode="r"))
    expected_shape = (len(request.final.subject_order), expected_count)
    if probabilities.dtype != np.float32:
        raise RecordError("OSS activation probabilities must use float32 storage")
    if probabilities.shape != expected_shape:
        raise RecordError("OSS activation matrix shape does not match final subject/fiber order")
    if request.sidecars.activation_probabilities.shape != expected_shape:
        raise RecordError("OSS activation ArtifactRef shape is inconsistent")
    if tuple(metadata.get("matrix_shape", ())) != expected_shape:
        raise RecordError("OSS activation metadata matrix shape mismatch")
    if str(metadata.get("matrix_dtype", "")) != "float32":
        raise RecordError("OSS activation metadata dtype mismatch")
    if not np.all(np.isfinite(probabilities)):
        raise RecordError("OSS activation matrix contains non-finite values")
    if float(np.min(probabilities)) < 0.0 or float(np.max(probabilities)) > 1.0:
        raise RecordError("OSS activation probabilities fall outside [0, 1]")

    fit_activation = (probabilities >= request.activation_threshold).astype(np.float32)
    if not np.any(fit_activation):
        raise RecordError("OSS activation is degenerate after pPAM thresholding")
    request.output_root.mkdir(parents=True, exist_ok=True)
    fit_path = request.output_root / "X_oss_binary_p_ge_0_5_float32.npy"
    _atomic_npy(fit_path, fit_activation)

    formal_target = build_configured_formal_target(
        FormalRequest(
            task=request.task,
            final=request.final,
            output_root=request.output_root,
            permutations=request.smoke_permutations,
            bootstraps=0,
            seed=request.seed,
        )
    )
    return ConfiguredOSSTarget(
        model_id=request.final.final_model_id,
        final_record_hash=request.final.record_hash,
        model_family=request.task.endpoint.model_family,
        output_root=request.output_root,
        output_prefix=formal_target.output_prefix,
        probability_path=probability_path,
        fit_activation_path=fit_path,
        fiber_ids_path=sidecar_fiber_path,
        scores_csv=formal_target.scores_csv,
        outcome_column=formal_target.outcome_column,
        nuisance_columns=tuple(formal_target.nuisance_columns),
        delta_hf_full_path=getattr(formal_target, "delta_hf_full_path", None),
        delta_hf_fold_path=getattr(formal_target, "delta_hf_fold_path", None),
        scale_direction=formal_target.scale_direction,
        subject_order=tuple(formal_target.subject_order),
        activation_threshold=request.activation_threshold,
        requested_frequency_hz=requested_frequency,
        exposure_component=component,
        hf_overlap_definition=hf_overlap_definition,
        parameter_manifest_path=parameter_path,
        activation_metadata_path=metadata_path,
    )


def _run_oss_numerical_backend(
    target: ConfiguredOSSTarget,
    *,
    n_permutations: int,
    seed: int,
) -> dict[str, Any]:
    module = _load_analysis("stnsnr_normative_fiber_oss_sensitivity")
    x = np.asarray(np.load(target.fit_activation_path), dtype=np.float32)
    fiber_ids = np.asarray(np.load(target.fiber_ids_path), dtype=np.int64)
    columns = module._load_score_columns(target.scores_csv)
    subjects = [str(value) for value in columns["subject_id"]]
    if tuple(subjects) != target.subject_order:
        raise RecordError("OSS score-table subject order differs from final record")
    y_post = module._float_column(columns, target.outcome_column)
    nuisance = np.column_stack(
        [module._float_column(columns, name) for name in target.nuisance_columns]
    )
    fold_delta = None
    if target.delta_hf_full_path is not None:
        full_delta = np.asarray(np.load(target.delta_hf_full_path), dtype=float)
        if full_delta.shape != (x.shape[0],):
            raise RecordError("OSS DeltaHF full-score shape is invalid")
        nuisance = np.column_stack([nuisance, full_delta])
        if target.delta_hf_fold_path is None:
            raise RecordError("adjusted OSS target lacks fold-specific DeltaHF scores")
        fold_delta = np.asarray(np.load(target.delta_hf_fold_path), dtype=float)
        if fold_delta.shape != (x.shape[0], x.shape[0]):
            raise RecordError("OSS DeltaHF fold-score shape is invalid")

    fold_caches = module._build_oss_fold_caches(
        x,
        nuisance,
        fold_delta_scores=fold_delta,
    )
    observed, fold_rows = module._loocv_oss(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
        fold_caches=fold_caches,
    )
    weights, scores = module._full_sample_weights_scores(
        x=x,
        fiber_ids=fiber_ids,
        y_post=y_post,
        nuisance=nuisance,
        scale_direction=target.scale_direction,
    )
    plain = module._plain_activation_controls(x)
    y_permuted = module.freedman_lane_permuted_outcomes(
        y_post,
        nuisance,
        int(n_permutations),
        seed=int(seed),
    )
    null_stats = np.full(int(n_permutations), np.nan, dtype=float)
    for index, y_star in enumerate(y_permuted):
        permuted, _ = module._loocv_oss(
            x=x,
            fiber_ids=fiber_ids,
            y_post=y_star,
            nuisance=nuisance,
            scale_direction=target.scale_direction,
            fold_caches=fold_caches,
        )
        null_stats[index] = permuted["spearman_rho"]

    prefix = target.output_prefix
    weights_path = target.output_root / f"{prefix}_oss_weights.npy"
    scores_path = target.output_root / f"{prefix}_oss_scores.csv"
    predictions_path = target.output_root / f"{prefix}_oss_loocv_predictions.csv"
    null_path = target.output_root / f"{prefix}_oss_smoke_null.npy"
    permutation_path = target.output_root / f"{prefix}_oss_smoke_permutation.csv"
    _atomic_npy(weights_path, np.asarray(weights, dtype=np.float32))
    _atomic_npy(null_path, null_stats)
    score_name = "NetFiberScore_OSS" if target.model_family == "hf_fiber" else "NetULFFiberScore_OSS"
    score_rows = [
        {
            "subject_id": subject,
            "SweetPeak5_OSS": float(scores.sweet_peak5[index]),
            "SourPeak5_OSS": float(scores.sour_peak5[index]),
            score_name: float(scores.net_score[index]),
            "PlainOSSActivationCount": float(plain["PlainOSSActivationCount"][index]),
            "PlainOSSActivationSum": float(plain["PlainOSSActivationSum"][index]),
            "PlainOSSActivationTop5": float(plain["PlainOSSActivationTop5"][index]),
        }
        for index, subject in enumerate(subjects)
    ]
    _atomic_csv(scores_path, score_rows, list(score_rows[0]))
    prediction_rows = [
        {
            "subject_id": subject,
            "Y_post": float(y_post[index]),
            "prediction_oss": float(observed["predictions"][index]),
            "prediction_baseline": float(observed["baseline_predictions"][index]),
            score_name: float(scores.net_score[index]),
        }
        for index, subject in enumerate(subjects)
    ]
    _atomic_csv(predictions_path, prediction_rows, list(prediction_rows[0]))
    permutation = {
        "B": int(n_permutations),
        "seed": int(seed),
        "observed_loocv_spearman_rho": float(observed["spearman_rho"]),
        "observed_loocv_pearson_r": float(observed["pearson_r"]),
        "observed_mae": float(observed["mae"]),
        "observed_rmse": float(observed["rmse"]),
        "observed_q2": float(observed["q2"]),
        "p_plus_one_two_sided": float(
            module.plus_one_two_sided_p(float(observed["spearman_rho"]), null_stats)
        ),
        "null_finite_count": int(np.count_nonzero(np.isfinite(null_stats))),
        "fold_n_candidate_fibers_min": int(observed["fold_n_candidate_fibers_min"]),
        "all_predictions_finite": bool(observed["all_predictions_finite"]),
        "permutation_status": "complete",
        "resampling_tier": "oss_smoke",
    }
    _atomic_csv(permutation_path, [permutation], list(permutation))
    return {
        **permutation,
        "oss_result_status": "complete",
        "outputs": {
            "fit_activation_matrix": str(target.fit_activation_path),
            "weights_npy": str(weights_path),
            "scores_csv": str(scores_path),
            "loocv_predictions_csv": str(predictions_path),
            "permutation_null_npy": str(null_path),
            "permutation_summary_csv": str(permutation_path),
        },
        "fold_count": len(fold_rows),
    }


NumericalRunner = Callable[[ConfiguredOSSTarget], Mapping[str, Any]]


def _contains_feedback(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            token = str(key).lower()
            if (
                token in _PROHIBITED_FEEDBACK_KEYS
                or token.endswith(_PROHIBITED_FEEDBACK_SUFFIXES)
                or _contains_feedback(item)
            ):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_feedback(item) for item in value)
    return False


def _plain_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    return value


def run_configured_oss(
    request: OSSRequest,
    *,
    numerical_runner: NumericalRunner | None = None,
) -> OSSServiceOutput:
    """Run one final-linked OSS sensitivity and emit the planner artifact."""
    target = build_configured_oss_target(request)
    results = dict(
        numerical_runner(target)
        if numerical_runner is not None
        else _run_oss_numerical_backend(
            target,
            n_permutations=request.smoke_permutations,
            seed=request.seed,
        )
    )
    if _contains_feedback(results):
        raise RecordError("OSS numerical output must not feed back model classification")
    nested_outputs = results.pop("outputs", {})
    if not isinstance(nested_outputs, Mapping):
        raise RecordError("OSS numerical outputs field must be a mapping")
    result_path = request.output_root / "oss_activation_results.json"
    payload = {
        "schema_version": "four_model_v1",
        "artifact_kind": "oss_activation_results",
        "oss_sensitivity_status": "complete",
        "final_model_id": request.final.final_model_id,
        "final_record_hash": request.final.record_hash,
        "endpoint_model_id": request.final.endpoint_model_id,
        "model_family": request.task.endpoint.model_family,
        "connectome": request.task.endpoint.connectome,
        "selected_tau": request.final.selected_tau,
        "selected_coverage": request.final.selected_coverage,
        "candidate_fiber_count": request.final.feature_axis.count,
        "candidate_feature_axis_sha256": request.final.feature_axis.sha256,
        "subject_order": list(request.final.subject_order),
        "oss_model": request.oss_model,
        "activation_model": request.activation_model,
        "stored_activation_definition": "pPAM_activation_probability",
        "fit_activation_definition": "pPAM_probability_ge_0.5",
        "activation_threshold": request.activation_threshold,
        "canonical_hemisphere": request.canonical_hemisphere,
        "left_to_right_mapping_method": "homologous_right_fiber_id",
        "hemisphere_merge_rule": request.hemisphere_merge_rule,
        "oss_exposure_component": target.exposure_component,
        "hf_overlap_definition": target.hf_overlap_definition,
        "requested_frequency_hz": target.requested_frequency_hz,
        "smoke_permutations": request.smoke_permutations,
        "seed": request.seed,
        "classification_feedback": "none",
        "input_artifacts": request.sidecars.as_dict(),
        "numerical_results": _plain_value(results),
        "outputs": {
            "fit_activation_matrix": str(target.fit_activation_path),
            **_plain_value(dict(nested_outputs)),
        },
    }
    _atomic_json(result_path, payload)
    return OSSServiceOutput(
        artifacts=(TaskArtifact("oss_activation_results", result_path),),
    )


configured_oss_runner = run_configured_oss


__all__ = [
    "ConfiguredOSSTarget",
    "build_configured_oss_target",
    "configured_oss_runner",
    "run_configured_oss",
]
