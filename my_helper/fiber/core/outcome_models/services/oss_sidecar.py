"""Endpoint-local preparation contracts for normative-fiber OSS sidecars."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable, Mapping

import numpy as np

from ..executor import RunContext, TaskArtifact, TaskResult, TaskStatus
from ..identity import canonical_hash
from ..planner import TaskSpec
from ..records import ArtifactRef, FinalArtifactRecord, RecordError
from .oss import OSSSidecarBundle
from .record_io import load_final_record
from .observed import normative_fiber_score_settings


class OSSSidecarInputsUnavailable(RecordError):
    """Raised when endpoint-local OSS preparation inputs are incomplete."""


DEFAULT_OSS_ROW_WORKERS = 3

# Frozen for configured_oss_row_v1. Bump these hashes for any numerical change
# in either module; scheduler and checkpoint-discovery changes preserve them.
_OSS_SCIENTIFIC_SCHEDULER_LOCKED_SHA256 = {
    "oss_sidecar_service": "cac387c3e6141f42aa6343bede05ecb6acbd8cb39ace8f40f4312aef40ef62cc",
}


@dataclass(frozen=True)
class OSSSideInput:
    """One subject-side stimulation input for OSS preparation."""

    subject_id: str
    side: str
    source_paths: tuple[Path, ...]
    source_sha256: tuple[str, ...]
    requested_frequency_hz: float
    modeled_frequency_hz: float
    stimulation_parameter_paths: tuple[Path, ...] = ()
    stimulation_parameter_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        subject_id = str(self.subject_id).strip()
        side = str(self.side).strip().upper()
        if not subject_id:
            raise RecordError("OSS side input subject_id must be nonempty")
        if side not in {"L", "R"}:
            raise RecordError("OSS side input side must be L or R")
        if not self.source_paths or len(self.source_paths) != len(self.source_sha256):
            raise RecordError("OSS side input paths and hashes must be nonempty and aligned")
        if any(len(str(value)) != 64 for value in self.source_sha256):
            raise RecordError("OSS side input hashes must be full SHA-256 digests")
        if self.stimulation_parameter_paths or self.stimulation_parameter_sha256:
            if (
                len(self.stimulation_parameter_paths) != len(self.source_paths)
                or len(self.stimulation_parameter_sha256) != len(self.source_paths)
            ):
                raise RecordError(
                    "OSS stimulation-parameter paths and hashes must align with source paths"
                )
            if any(len(str(value)) != 64 for value in self.stimulation_parameter_sha256):
                raise RecordError(
                    "OSS stimulation-parameter hashes must be full SHA-256 digests"
                )
        requested = float(self.requested_frequency_hz)
        modeled = float(self.modeled_frequency_hz)
        if requested <= 0.0 or modeled <= 0.0 or requested != modeled:
            raise RecordError("OSS requested and modeled side frequencies must match and be positive")
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "source_paths", tuple(Path(path) for path in self.source_paths))
        object.__setattr__(
            self,
            "stimulation_parameter_paths",
            tuple(Path(path) for path in self.stimulation_parameter_paths),
        )
        object.__setattr__(self, "requested_frequency_hz", requested)
        object.__setattr__(self, "modeled_frequency_hz", modeled)


def validate_oss_side_inputs(
    subject_order: tuple[str, ...],
    rows: tuple[OSSSideInput, ...],
) -> tuple[OSSSideInput, ...]:
    """Require exactly one L and one R input for every final subject."""
    keys = [(row.subject_id, row.side) for row in rows]
    if len(set(keys)) != len(keys):
        raise OSSSidecarInputsUnavailable("duplicate subject-side OSS inputs")
    expected = {
        (str(subject_id), side)
        for subject_id in subject_order
        for side in ("L", "R")
    }
    observed = set(keys)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise OSSSidecarInputsUnavailable(
            f"expected exact subject-side OSS inputs; missing={missing}; extra={extra}"
        )
    by_key = {key: row for key, row in zip(keys, rows, strict=True)}
    return tuple(
        by_key[(str(subject_id), side)]
        for subject_id in subject_order
        for side in ("L", "R")
    )


_OSS_COMPATIBILITY_FIELDS = {
    "source_stimulation_input_hashes",
    "subject_order",
    "requested_frequencies_hz",
    "modeled_frequencies_hz",
    "canonical_hemisphere",
    "left_to_right_mapping",
    "hemisphere_merge_rule",
    "component_identity",
    "hf_overlap_definition",
    "ordered_valid_fiber_ids",
    "valid_fiber_axis_sha256",
    "parent_feature_axis_sha256",
    "connectome_input_sha256",
    "generator_identity_sha256",
    "oss_toolchain_sha256",
    "oss_environment_sha256",
    "oss_model",
    "ppam_sample_count",
    "ppam_sampling",
}


def oss_compatibility_hash(payload: Mapping[str, Any]) -> str:
    """Return the exact canonical identity for reusable OSS matrix content."""
    normalized = dict(payload)
    missing = sorted(_OSS_COMPATIBILITY_FIELDS - set(normalized))
    extra = sorted(set(normalized) - _OSS_COMPATIBILITY_FIELDS)
    if missing:
        raise RecordError("OSS compatibility payload is missing: " + ",".join(missing))
    if extra:
        raise RecordError("OSS compatibility payload has unknown fields: " + ",".join(extra))
    if str(normalized["canonical_hemisphere"]).lower() != "right":
        raise RecordError("OSS compatibility payload must be right-canonical")
    if normalized["hemisphere_merge_rule"] != "max_probability_union":
        raise RecordError("OSS compatibility payload merge rule is invalid")
    if normalized["oss_model"] != "OSS-DBSv2":
        raise RecordError("OSS compatibility payload model is invalid")
    if int(normalized["ppam_sample_count"]) != 10:
        raise RecordError("OSS compatibility pPAM sample count must be 10")
    if normalized["ppam_sampling"] != {
        "probabilistic_parameter": "Fiber Diameter",
        "parameter_limits_um": [1.0, 4.0],
        "sampling_distribution": "Equidistant",
    }:
        raise RecordError("OSS compatibility pPAM sampling contract is invalid")
    component = str(normalized["component_identity"])
    overlap = str(normalized["hf_overlap_definition"])
    if component == "HF_only_reference":
        if overlap != "not_applicable":
            raise RecordError("HF OSS overlap definition must be not_applicable")
    elif component == "ULF_addon_component":
        if overlap not in {
            "matched_hf_peak_efield_selected_tau",
            "hf_source_absent_all_false",
        }:
            raise RecordError("ULF OSS overlap definition is invalid")
    else:
        raise RecordError("OSS compatibility component identity is invalid")
    mapping = normalized["left_to_right_mapping"]
    if not isinstance(mapping, Mapping) or set(mapping) != {
        "method",
        "code_sha256",
        "transform_sha256",
    }:
        raise RecordError("OSS compatibility left-to-right mapping identity is invalid")
    if mapping["method"] != "ea_flip_lr_nonlinear":
        raise RecordError("OSS compatibility left-to-right method is invalid")
    if any(len(str(mapping[key])) != 64 for key in ("code_sha256", "transform_sha256")):
        raise RecordError("OSS compatibility transform hashes must be full SHA-256 digests")
    subject_order = tuple(str(value) for value in normalized["subject_order"])
    if not subject_order or len(set(subject_order)) != len(subject_order):
        raise RecordError("OSS compatibility subject order must be nonempty and unique")
    fiber_ids = tuple(int(value) for value in normalized["ordered_valid_fiber_ids"])
    if not fiber_ids or len(set(fiber_ids)) != len(fiber_ids):
        raise RecordError("OSS compatibility valid fiber IDs must be nonempty and unique")
    for key in (
        "valid_fiber_axis_sha256",
        "parent_feature_axis_sha256",
        "connectome_input_sha256",
        "generator_identity_sha256",
        "oss_environment_sha256",
    ):
        if len(str(normalized[key])) != 64:
            raise RecordError(f"OSS compatibility {key} must be a full SHA-256 digest")
    for key in (
        "source_stimulation_input_hashes",
        "requested_frequencies_hz",
        "modeled_frequencies_hz",
    ):
        if not isinstance(normalized[key], Mapping) or not normalized[key]:
            raise RecordError(f"OSS compatibility {key} must be a nonempty mapping")
    for identity in normalized["source_stimulation_input_hashes"].values():
        if not isinstance(identity, Mapping) or set(identity) != {
            "efield_sha256",
            "stimulation_parameter_sha256",
        }:
            raise RecordError("OSS compatibility source input identity is invalid")
        if any(len(str(value)) != 64 for value in identity.values()):
            raise RecordError("OSS compatibility source input identity hashes are invalid")
    toolchain_hashes = normalized["oss_toolchain_sha256"]
    if not isinstance(toolchain_hashes, Mapping) or set(toolchain_hashes) != {
        "matlab",
        "leaddbs2ossdbs",
        "prepareaxonmodel",
        "ossdbs",
        "run_pathway_activation",
    }:
        raise RecordError("OSS compatibility toolchain identity is invalid")
    if any(len(str(value)) != 64 for value in toolchain_hashes.values()):
        raise RecordError("OSS compatibility toolchain hashes are invalid")
    requested = normalized["requested_frequencies_hz"]
    modeled = normalized["modeled_frequencies_hz"]
    if set(requested) != set(modeled):
        raise RecordError("OSS requested and modeled frequency keys differ")
    for key in requested:
        if float(requested[key]) != float(modeled[key]):
            raise RecordError(f"OSS requested and modeled frequency differ for {key}")
    return canonical_hash(normalized)


@dataclass(frozen=True)
class OSSSidecarPreparationRequest:
    """One final-record-locked OSS sidecar preparation request."""

    task: TaskSpec
    final: FinalArtifactRecord
    output_root: Path
    compatibility_hash: str
    side_inputs: tuple[OSSSideInput, ...] = ()
    compatibility_payload: Mapping[str, Any] = field(default_factory=dict)
    toolchain: Mapping[str, Path] = field(default_factory=dict)
    score: Mapping[str, float | int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.task.key.execution_stage != "oss_sidecar_preparation":
            raise RecordError("OSS sidecar request requires an oss_sidecar_preparation task")
        if self.task.workflow_phase != "sensitivity":
            raise RecordError("OSS sidecar preparation must run in the sensitivity phase")
        if self.task.endpoint.model_family not in {"hf_fiber", "ulf_fiber"}:
            raise RecordError("OSS sidecar preparation is defined only for fiber models")
        if str(self.task.endpoint.connectome).lower() != "dtor":
            raise RecordError("OSS sidecar preparation is restricted to dTOR")
        if self.final.endpoint_model_id != self.task.endpoint.identifier:
            raise RecordError("OSS sidecar final belongs to another endpoint")
        if self.final.valid_feature_axis is None:
            raise RecordError("OSS sidecar preparation requires the realized valid fiber axis")
        if len(str(self.compatibility_hash)) != 64:
            raise RecordError("OSS compatibility hash must be a full SHA-256 digest")
        if self.side_inputs:
            validate_oss_side_inputs(self.final.subject_order, self.side_inputs)
        if self.compatibility_payload:
            expected_hash = oss_compatibility_hash(self.compatibility_payload)
            if expected_hash != self.compatibility_hash:
                raise RecordError("OSS compatibility payload hash mismatch")
        object.__setattr__(self, "output_root", Path(self.output_root).expanduser().resolve())


def _load_analysis(name: str):
    analysis_root = Path(__file__).resolve().parents[2] / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module(name)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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


def _prior_oss_activation_roots(
    cache_root: Path,
    compatibility_hash: str,
) -> tuple[Path, ...]:
    cache_root = Path(cache_root).expanduser().resolve()
    if cache_root.parent.name != "oss_content_cache":
        return ()
    study_root = cache_root.parent.parent.parent
    current_activation_root = (
        cache_root / "external_generation" / "activation_rows"
    ).resolve()
    candidates = []
    for path in study_root.glob(
        f"*/oss_content_cache/{compatibility_hash}/external_generation/activation_rows"
    ):
        resolved = path.resolve()
        if resolved != current_activation_root and resolved.is_dir():
            candidates.append(resolved)
    return tuple(sorted(set(candidates), key=str))


def _activation_root_run_id(activation_root: Path) -> str:
    path = Path(activation_root).expanduser().resolve()
    if (
        path.name == "activation_rows"
        and path.parent.name == "external_generation"
        and len(path.parents) > 3
        and path.parents[2].name == "oss_content_cache"
    ):
        return path.parents[3].name
    return ""


def _oss_row_reuse_identity_sha256(row: Mapping[str, Any]) -> str:
    """Return the cross-run scientific identity for one OSS source row."""
    return canonical_hash(
        {
            "checkpoint_contract": "configured_oss_row_v2",
            "compatibility_hash": str(row["oss_compatibility_hash"]),
            "final_model_id": str(row["model_id"]),
            "subject_id": str(row["subject_id"]),
            "side": str(row["side"]),
            "source_index": int(row["source_index"]),
            "source_path": str(Path(row["source_paths"]).expanduser().resolve()),
            "source_sha256": str(row["source_sha256"]),
            "canonicalization_mode": str(row["canonicalization_mode"]),
        }
    )


def _legacy_oss_row_identity_sha256(
    row: Mapping[str, Any],
    final_record_hash: str,
) -> str:
    """Reconstruct configured_oss_row_v1 for validated legacy imports."""
    stimulation_parameter_path = str(
        row.get("stimulation_parameter_path", "") or ""
    )
    return canonical_hash(
        {
            "checkpoint_contract": "configured_oss_row_v1",
            "compatibility_hash": str(row["oss_compatibility_hash"]),
            "final_model_id": str(row["model_id"]),
            "final_record_hash": str(final_record_hash),
            "subject_id": str(row["subject_id"]),
            "side": str(row["side"]),
            "source_index": int(row["source_index"]),
            "source_path": str(Path(row["source_paths"]).expanduser().resolve()),
            "source_sha256": str(row["source_sha256"]),
            "stimulation_parameter_path": (
                ""
                if not stimulation_parameter_path
                else str(Path(stimulation_parameter_path).expanduser().resolve())
            ),
            "stimulation_parameter_sha256": str(
                row.get("stimulation_parameter_sha256", "") or ""
            ),
            "source_frequency_hz": float(row["source_frequency_hz"]),
            "canonicalization_mode": str(row["canonicalization_mode"]),
        }
    )


def _load_legacy_prior_row_checkpoint(
    *,
    activation: Any,
    row: Mapping[str, Any],
    row_index: int,
    output_dir: Path,
) -> Mapping[str, Any] | None:
    logical_row_dir = Path(output_dir) / activation._row_slug(row_index, row)
    checkpoint_path = logical_row_dir / "row_checkpoint.json"
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_identity = activation._valid_row_identity(
            checkpoint.get("oss_row_identity_sha256")
        )
        if checkpoint_identity is None:
            return None
        validated = activation._load_row_checkpoint(
            logical_row_dir,
            checkpoint_identity,
        )
        if validated is None:
            return None
        status_doc = json.loads(
            Path(validated["row_status_json"]).read_text(encoding="utf-8")
        )
        legacy_row = status_doc["row"]
        legacy_final_record_hash = str(legacy_row["final_record_hash"])
        if checkpoint_identity != _legacy_oss_row_identity_sha256(
            row,
            legacy_final_record_hash,
        ):
            return None
        if _oss_row_reuse_identity_sha256(legacy_row) != (
            _oss_row_reuse_identity_sha256(row)
        ):
            return None
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return {**validated, "row_checkpoint_legacy_import": True}


def _generator_identity_sha256(paths: Mapping[str, Path]) -> str:
    normalized: dict[str, str] = {}
    for name, raw_path in sorted(paths.items()):
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise OSSSidecarInputsUnavailable(
                f"OSS generator dependency is missing: {path}"
            )
        normalized[str(name)] = _sha256_file(path)
    if not normalized:
        raise RecordError("OSS generator identity requires at least one source file")
    return canonical_hash(normalized)


def _scientific_generator_identity_sha256(paths: Mapping[str, Path]) -> str:
    """Hash numerical dependencies while version-locking scheduler-only modules."""
    normalized: dict[str, str] = {}
    for name, raw_path in sorted(paths.items()):
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise OSSSidecarInputsUnavailable(
                f"OSS generator dependency is missing: {path}"
            )
        if str(name) in _OSS_SCIENTIFIC_SCHEDULER_LOCKED_SHA256:
            normalized[str(name)] = _OSS_SCIENTIFIC_SCHEDULER_LOCKED_SHA256[
                str(name)
            ]
        else:
            normalized[str(name)] = _sha256_file(path)
    if not normalized:
        raise RecordError("OSS generator identity requires at least one source file")
    return canonical_hash(normalized)


def _validated_axis_path(
    axis: Any,
    run_root: Path,
    label: str,
) -> tuple[Path, np.ndarray]:
    path = Path(axis.ids_path).expanduser()
    path = path.resolve() if path.is_absolute() else (run_root / path).resolve()
    try:
        path.relative_to(run_root.resolve())
    except ValueError as exc:
        raise RecordError(f"OSS {label} axis is outside the configured run root") from exc
    if not path.is_file():
        raise OSSSidecarInputsUnavailable(f"OSS {label} axis is missing: {path}")
    if not str(axis.identity_source).endswith(":idx"):
        raise RecordError(f"OSS {label} axis identity source is unsupported")
    values = np.asarray(np.load(path, mmap_mode="r", allow_pickle=False))
    if values.ndim != 1 or values.shape != (int(axis.count),):
        raise RecordError(f"OSS {label} axis shape is invalid")
    if values.dtype.kind not in {"i", "u"}:
        raise RecordError(f"OSS {label} axis must contain integer fiber IDs")
    if np.unique(values).size != values.size:
        raise RecordError(f"OSS {label} axis contains duplicate fiber IDs")
    if _array_sha256(values) != axis.sha256:
        raise RecordError(f"OSS {label} axis SHA-256 mismatch")
    return path, values.astype(np.int64, copy=False)


def _validated_final_axes(
    final: FinalArtifactRecord,
    context: RunContext,
) -> tuple[np.ndarray, np.ndarray]:
    valid_axis = final.valid_feature_axis
    if valid_axis is None:
        raise RecordError("OSS preparation requires a realized valid fiber axis")
    _, parent = _validated_axis_path(
        final.feature_axis,
        context.store.run_root,
        "parent feature",
    )
    _, valid = _validated_axis_path(
        valid_axis,
        context.store.run_root,
        "valid feature",
    )
    if valid.size == 0:
        raise RecordError("OSS valid feature axis must be nonempty")
    parent_positions = np.flatnonzero(np.isin(parent, valid))
    if parent_positions.size != valid.size or not np.array_equal(
        parent[parent_positions],
        valid,
    ):
        raise RecordError("OSS valid feature axis is not an ordered parent-axis subset")
    return parent, valid


def _run_artifact_path(context: RunContext, relative_path: str) -> Path:
    path = (context.store.run_root / relative_path).resolve()
    try:
        path.relative_to(context.store.run_root)
    except ValueError as exc:
        raise RecordError("OSS preparation artifact escapes the configured run root") from exc
    if not path.is_file():
        raise OSSSidecarInputsUnavailable(f"OSS preparation artifact is missing: {path}")
    return path


def _indexed_sidecar_qc(
    final: FinalArtifactRecord,
    context: RunContext,
) -> dict[str, Any]:
    stage = (
        "sidecar_equivalence"
        if final.final_branch == "hf_source"
        else "preprocessing_sidecars"
    )
    records = [
        record
        for record in context.results.values()
        if record.task.endpoint.identifier == final.endpoint_model_id
        and record.task.key.execution_stage == stage
    ]
    if len(records) != 1:
        raise OSSSidecarInputsUnavailable(
            f"expected one completed {stage} task for OSS source rows; found {len(records)}"
        )
    record = records[0]
    if record.result.status != TaskStatus.COMPLETED:
        raise OSSSidecarInputsUnavailable(
            f"OSS source-row task {record.task.task_id} is not completed"
        )
    artifacts = [
        artifact for artifact in record.result.artifacts if artifact.kind == "qc"
    ]
    if len(artifacts) != 1:
        raise OSSSidecarInputsUnavailable(
            f"OSS source-row task must expose one QC artifact; found {len(artifacts)}"
        )
    run_root = context.store.run_root.resolve()
    qc_path = Path(artifacts[0].path).expanduser().resolve()
    try:
        relative_path = qc_path.relative_to(run_root).as_posix()
    except ValueError as exc:
        raise RecordError("OSS source-row QC is outside the configured run root") from exc
    indexed = [
        row
        for row in context.store.load_artifact_index()
        if row.get("task_id") == record.task.task_id and row.get("kind") == "qc"
    ]
    if len(indexed) != 1:
        raise RecordError(
            f"OSS source-row QC must have one artifact-index entry; found {len(indexed)}"
        )
    if str(indexed[0].get("relative_path", "")) != relative_path:
        raise RecordError("OSS source-row QC path does not match the artifact index")
    if not qc_path.is_file():
        raise OSSSidecarInputsUnavailable(f"OSS source-row QC is missing: {qc_path}")
    if str(indexed[0].get("sha256", "")) != _sha256_file(qc_path):
        raise RecordError("OSS source-row QC SHA-256 does not match the artifact index")
    try:
        payload = json.loads(qc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OSSSidecarInputsUnavailable("cannot read the indexed OSS source-row QC") from exc
    if not isinstance(payload, dict):
        raise RecordError("OSS source-row QC payload must be a mapping")
    return payload


def _source_rows(final: FinalArtifactRecord, context: RunContext) -> list[dict[str, Any]]:
    worklist = _load_analysis("stnsnr_normative_fiber_oss_sidecar_worklist")
    qc = _indexed_sidecar_qc(final, context)
    if final.final_branch == "hf_source":
        rows = list(qc.get("sampler_qc", {}).get("side_fields", []))
    else:
        rows = worklist._ulf_source_rows(qc)
        manifest_path = _run_artifact_path(context, final.manifest.relative_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OSSSidecarInputsUnavailable(
                "cannot read the selected final manifest"
            ) from exc
        derivatives_root = worklist._derivatives_root(manifest)
        recovered = []
        for row in rows:
            item = dict(row)
            if not item.get("source_paths"):
                paths, mode = worklist._recover_ulf_source_paths(item, derivatives_root)
                item["source_paths"] = paths
                item["path_mode"] = [mode] if mode else []
            recovered.append(item)
        rows = recovered
    return worklist._ordered_subject_side_rows(final.subject_order, rows)


def _hf_overlap_definition(
    model_family: str,
    selected_manifest: Mapping[str, Any],
) -> str:
    if model_family == "hf_fiber":
        return "not_applicable"
    if model_family != "ulf_fiber":
        raise RecordError("OSS overlap definition is restricted to fiber model families")
    status = str(
        selected_manifest.get(
            "hf_source_status",
            selected_manifest.get("hf_norm_fiber_source_status", ""),
        )
    ).strip()
    if status in {"pre_specified_accepted", "scan_fallback_accepted"}:
        return "matched_hf_peak_efield_selected_tau"
    if status == "absent_no_stable_grid":
        return "hf_source_absent_all_false"
    raise OSSSidecarInputsUnavailable(
        "selected ULF manifest does not define a recognized HF source status"
    )


def _validate_formal_dependency(
    task: TaskSpec,
    context: RunContext,
    final: FinalArtifactRecord,
) -> None:
    facts = context.dependency_facts(task, "formal_permutation_bootstrap")
    if facts.get("formal_complete") is not True:
        raise OSSSidecarInputsUnavailable("OSS producer lacks a completed formal dependency")
    if str(facts.get("final_model_id", "")) != final.final_model_id:
        raise OSSSidecarInputsUnavailable("OSS formal dependency final-model identity mismatch")
    if str(facts.get("final_artifact_record_hash", "")) != final.record_hash:
        raise OSSSidecarInputsUnavailable("OSS formal dependency final-record hash mismatch")


def _side_inputs(final: FinalArtifactRecord, context: RunContext) -> tuple[OSSSideInput, ...]:
    preflight = _load_analysis("stnsnr_normative_fiber_oss_parameter_preflight")
    rows = _source_rows(final, context)
    inputs = []
    for row in rows:
        paths = tuple(Path(value).expanduser().resolve() for value in row.get("source_paths", ()))
        if not paths or any(not path.is_file() for path in paths):
            raise OSSSidecarInputsUnavailable(
                f"missing source stimulation files for {(row['subject_id'], row['side'])}"
            )
        frequencies = []
        stimulation_paths = []
        for path in paths:
            source_mat = preflight._stimparameter_from_source(path)
            if not source_mat.is_file():
                raise OSSSidecarInputsUnavailable(
                    f"missing source stimulation parameters: {source_mat}"
                )
            frequency, _ = preflight._read_source_frequency_hz(source_mat, row["side"])
            if frequency is None:
                raise OSSSidecarInputsUnavailable(f"missing source frequency in {source_mat}")
            frequencies.append(float(frequency))
            stimulation_paths.append(source_mat.resolve())
        if len(set(frequencies)) != 1:
            raise OSSSidecarInputsUnavailable(
                f"inconsistent source frequencies for {(row['subject_id'], row['side'])}"
            )
        inputs.append(
            OSSSideInput(
                subject_id=row["subject_id"],
                side=row["side"],
                source_paths=paths,
                source_sha256=tuple(_sha256_file(path) for path in paths),
                requested_frequency_hz=frequencies[0],
                modeled_frequency_hz=frequencies[0],
                stimulation_parameter_paths=tuple(stimulation_paths),
                stimulation_parameter_sha256=tuple(
                    _sha256_file(path) for path in stimulation_paths
                ),
            )
        )
    return validate_oss_side_inputs(final.subject_order, tuple(inputs))


def build_configured_oss_sidecar_request(
    task: TaskSpec,
    context: RunContext,
    final: FinalArtifactRecord,
) -> OSSSidecarPreparationRequest:
    """Build one exact configured request before invoking external tools."""
    if context.config is None:
        raise RecordError("OSS sidecar preparation requires resolved workflow context")
    _validate_formal_dependency(task, context, final)
    valid_axis = final.valid_feature_axis
    if valid_axis is None:
        raise RecordError("OSS sidecar preparation requires a realized valid fiber axis")
    _, valid_ids = _validated_final_axes(final, context)
    side_inputs = _side_inputs(final, context)
    asset_root = context.config.study.paths.asset_root.resolve()
    transform_code = asset_root / "helpers" / "ea_flip_lr_nonlinear.m"
    transform_field = (
        asset_root
        / "templates"
        / "space"
        / "MNI152NLin2009bAsym"
        / "fliplr"
        / "InverseComposite.nii.gz"
    )
    environment_yml = asset_root / "classes" / "conda_utils" / "environments" / "OSS-DBSv2.yml"
    for path in (transform_code, transform_field, environment_yml):
        if not path.is_file():
            raise OSSSidecarInputsUnavailable(f"required OSS identity input is missing: {path}")
    envs_root = Path(sys.executable).resolve().parents[2]
    oss_bin = envs_root / "ossdbsv2" / "bin"
    toolchain = {
        "leaddbs2ossdbs": oss_bin / "leaddbs2ossdbs",
        "prepareaxonmodel": oss_bin / "prepareaxonmodel",
        "ossdbs": oss_bin / "ossdbs",
        "run_pathway_activation": oss_bin / "run_pathway_activation",
    }
    readiness = _load_analysis("stnsnr_four_model_readiness")
    toolchain["matlab"] = Path(readiness.DEFAULT_MATLAB).expanduser().resolve()
    missing_tools = [str(path) for path in toolchain.values() if not path.is_file()]
    if missing_tools:
        raise OSSSidecarInputsUnavailable(
            "required OSS executables are missing: " + ",".join(missing_tools)
        )
    source_hashes = {
        f"{row.subject_id}:{row.side}:{index}": {
            "efield_sha256": value,
            "stimulation_parameter_sha256": row.stimulation_parameter_sha256[index],
        }
        for row in side_inputs
        for index, value in enumerate(row.source_sha256)
    }
    requested = {
        f"{row.subject_id}:{row.side}": row.requested_frequency_hz
        for row in side_inputs
    }
    modeled = {
        f"{row.subject_id}:{row.side}": row.modeled_frequency_hz
        for row in side_inputs
    }
    component = (
        "HF_only_reference"
        if task.endpoint.model_family == "hf_fiber"
        else "ULF_addon_component"
    )
    selected_manifest_path = _run_artifact_path(context, final.manifest.relative_path)
    try:
        selected_manifest = json.loads(selected_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OSSSidecarInputsUnavailable("cannot read the selected final manifest") from exc
    connectome = context.config.study.connectomes[str(task.endpoint.connectome)]
    connectome_path = Path(connectome.path).expanduser().resolve()
    if not connectome_path.is_file():
        raise OSSSidecarInputsUnavailable(
            f"configured dTOR connectome is missing: {connectome_path}"
        )
    input_hashes = context.store.provenance.get("input_hashes", {})
    connectome_hash = str(
        input_hashes.get(f"connectome_{task.endpoint.connectome}", "")
    )
    if len(connectome_hash) != 64:
        connectome_hash = _sha256_file(connectome_path)
    generator_files: dict[str, Path] = {
        "oss_sidecar_service": Path(__file__).resolve(),
        "parameter_preflight": Path(
            _load_analysis("stnsnr_normative_fiber_oss_parameter_preflight").__file__
        ).resolve(),
        "activation_rows": Path(
            _load_analysis("stnsnr_normative_fiber_oss_activation_rows").__file__
        ).resolve(),
        "sidecar_merge": Path(
            _load_analysis("stnsnr_normative_fiber_oss_sidecar_merge").__file__
        ).resolve(),
    }
    matlab_generator_root = asset_root / "ext_libs" / "OSS-DBS" / "genvat_butenko"
    for path in sorted(matlab_generator_root.rglob("*.m")):
        generator_files[
            f"genvat_butenko/{path.relative_to(matlab_generator_root).as_posix()}"
        ] = path
    for relative in (
        "ea_load_reconstruction.m",
        "helpers/ea_flip_lr_nonlinear.m",
    ):
        generator_files[f"leaddbs/{relative}"] = asset_root / relative
    generator_identity = _scientific_generator_identity_sha256(generator_files)
    toolchain_hashes = {
        name: _sha256_file(Path(path).resolve())
        for name, path in toolchain.items()
    }
    payload = {
        "source_stimulation_input_hashes": source_hashes,
        "subject_order": list(final.subject_order),
        "requested_frequencies_hz": requested,
        "modeled_frequencies_hz": modeled,
        "canonical_hemisphere": "right",
        "left_to_right_mapping": {
            "method": "ea_flip_lr_nonlinear",
            "code_sha256": _sha256_file(transform_code),
            "transform_sha256": _sha256_file(transform_field),
        },
        "hemisphere_merge_rule": "max_probability_union",
        "component_identity": component,
        "hf_overlap_definition": _hf_overlap_definition(
            task.endpoint.model_family,
            selected_manifest,
        ),
        "ordered_valid_fiber_ids": valid_ids.tolist(),
        "valid_fiber_axis_sha256": valid_axis.sha256,
        "parent_feature_axis_sha256": final.feature_axis.sha256,
        "connectome_input_sha256": connectome_hash,
        "generator_identity_sha256": generator_identity,
        "oss_toolchain_sha256": toolchain_hashes,
        "oss_environment_sha256": _sha256_file(environment_yml),
        "oss_model": "OSS-DBSv2",
        "ppam_sample_count": 10,
        "ppam_sampling": {
            "probabilistic_parameter": "Fiber Diameter",
            "parameter_limits_um": [1.0, 4.0],
            "sampling_distribution": "Equidistant",
        },
    }
    compatibility_hash = oss_compatibility_hash(payload)
    return OSSSidecarPreparationRequest(
        task=task,
        final=final,
        output_root=(
            context.store.run_root
            / "models"
            / task.endpoint.identifier
            / "tasks"
            / task.task_id
        ),
        compatibility_hash=compatibility_hash,
        side_inputs=side_inputs,
        compatibility_payload=payload,
        toolchain=toolchain,
        score=normative_fiber_score_settings(
            context.config.model.normative_fiber["score"]
        ),
    )


@dataclass(frozen=True)
class OSSGeneratedContent:
    """Content-addressable probability matrix and ordered fiber axis."""

    activation_probabilities: Path
    fiber_ids: Path


ContentGenerator = Callable[
    [OSSSidecarPreparationRequest, Path],
    OSSGeneratedContent,
]


def generate_configured_oss_content(
    request: OSSSidecarPreparationRequest,
    cache_root: Path,
    *,
    preflight_runner: Callable[..., Mapping[str, Any]] | None = None,
    activation_runner: Callable[..., Mapping[str, Any]] | None = None,
    row_checkpoint_loader: Callable[..., Mapping[str, Any] | None] | None = None,
    row_workers: int = DEFAULT_OSS_ROW_WORKERS,
) -> OSSGeneratedContent:
    """Generate continuous right-canonical pPAM rows for one immutable final."""
    ordered_inputs = validate_oss_side_inputs(
        request.final.subject_order,
        request.side_inputs,
    )
    required_tools = {
        "matlab",
        "leaddbs2ossdbs",
        "prepareaxonmodel",
        "ossdbs",
        "run_pathway_activation",
    }
    missing_tools = sorted(required_tools - set(request.toolchain))
    if missing_tools:
        raise OSSSidecarInputsUnavailable(
            "OSS toolchain is incomplete: " + ",".join(missing_tools)
        )
    preflight = _load_analysis("stnsnr_normative_fiber_oss_parameter_preflight")
    activation = _load_analysis("stnsnr_normative_fiber_oss_activation_rows")
    merge = _load_analysis("stnsnr_normative_fiber_oss_sidecar_merge")
    if int(preflight.PAM_N_SAMPLES) != 10 or int(activation.PAM_N_SAMPLES) != 10:
        raise RecordError("configured OSS pPAM implementations must use exactly 10 samples")
    preflight_runner = preflight_runner or preflight._run_row_preflight
    activation_runner = activation_runner or activation._run_activation_row
    if row_checkpoint_loader is None:
        def row_checkpoint_loader(**kwargs: Any) -> Mapping[str, Any] | None:
            row = kwargs["row"]
            row_identity = activation._valid_row_identity(
                row.get("oss_row_identity_sha256")
            )
            logical_row_dir = Path(kwargs["output_dir"]) / activation._row_slug(
                int(kwargs["row_index"]),
                row,
            )
            return activation._load_row_checkpoint(logical_row_dir, row_identity)
    if int(row_workers) < 1:
        raise ValueError("OSS row_workers must be at least 1")
    scheduler_identity = _generator_identity_sha256(
        {
            "oss_sidecar_service": Path(__file__).resolve(),
            "activation_rows": Path(activation.__file__).resolve(),
        }
    )

    cache_root = Path(cache_root).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    fiber_path = cache_root / "oss_fiber_ids.npy"
    probability_path = cache_root / "X_oss_float32_fiber_major.npy"
    valid_ids = np.asarray(
        request.compatibility_payload["ordered_valid_fiber_ids"],
        dtype=np.int64,
    )
    np.save(fiber_path, valid_ids)
    external_root = cache_root / "external_generation"
    preflight_root = external_root / "parameter_preflight"
    activation_root = external_root / "activation_rows"
    preflight_root.mkdir(parents=True, exist_ok=True)
    activation_root.mkdir(parents=True, exist_ok=True)
    prior_activation_roots = _prior_oss_activation_roots(
        cache_root,
        request.compatibility_hash,
    )
    activation_args = SimpleNamespace(
        prepareaxonmodel_bin=str(request.toolchain["prepareaxonmodel"]),
        oss_converter_bin=str(request.toolchain["leaddbs2ossdbs"]),
        ossdbs_bin=str(request.toolchain["ossdbs"]),
        run_pathway_activation_bin=str(request.toolchain["run_pathway_activation"]),
        prepareaxon_timeout_s=0,
        converter_timeout_s=0,
        ossdbs_timeout_s=0,
        pathway_timeout_s=0,
        disable_candidate_filter=False,
    )
    work_items: list[tuple[int, OSSSideInput, int, Path]] = []
    row_index = 0
    for side_input in ordered_inputs:
        for source_index, source_path in enumerate(side_input.source_paths):
            work_items.append((row_index, side_input, source_index, source_path))
            row_index += 1

    def run_row(
        work_item: tuple[int, OSSSideInput, int, Path],
    ) -> tuple[int, tuple[str, str], np.ndarray, dict[str, Any]]:
        row_index, side_input, source_index, source_path = work_item
        stimulation_parameter_path = (
            side_input.stimulation_parameter_paths[source_index]
            if side_input.stimulation_parameter_paths
            else None
        )
        stimulation_parameter_sha256 = (
            side_input.stimulation_parameter_sha256[source_index]
            if side_input.stimulation_parameter_sha256
            else ""
        )
        row = {
            "model_id": request.final.final_model_id,
            "subject_id": side_input.subject_id,
            "side": side_input.side,
            "source_index": str(source_index),
            "source_paths": str(source_path),
            "source_component": str(request.compatibility_payload["component_identity"]),
            "source_sha256": side_input.source_sha256[source_index],
            "final_record_hash": request.final.record_hash,
            "oss_compatibility_hash": request.compatibility_hash,
            "canonicalization_mode": (
                "left_geometry_to_right"
                if side_input.side == "L"
                else "native_right"
            ),
            "oss_fiber_ids_path": str(fiber_path),
            "oss_n_fibers": str(valid_ids.size),
            "oss_fiber_ids_hash": request.final.valid_feature_axis.sha256,
            "oss_fiber_id_status": "immutable_final_valid_axis",
            "parent_fiber_ids_path": str(request.final.feature_axis.ids_path),
            "parent_n_fibers": str(request.final.feature_axis.count),
            "parent_fiber_id_status": "selected_source_parent_axis",
            "stimulation_parameter_path": (
                ""
                if stimulation_parameter_path is None
                else str(Path(stimulation_parameter_path).expanduser().resolve())
            ),
            "stimulation_parameter_sha256": stimulation_parameter_sha256,
            "source_frequency_hz": side_input.modeled_frequency_hz,
        }
        row["oss_row_identity_sha256"] = _oss_row_reuse_identity_sha256(row)
        reused_result = row_checkpoint_loader(
            row=row,
            row_index=row_index,
            output_dir=activation_root,
        )
        checkpoint_source_kind = "current_run"
        checkpoint_source_root = activation_root
        if reused_result is None:
            for prior_activation_root in prior_activation_roots:
                reused_result = row_checkpoint_loader(
                    row=row,
                    row_index=row_index,
                    output_dir=prior_activation_root,
                )
                if reused_result is None:
                    reused_result = _load_legacy_prior_row_checkpoint(
                        activation=activation,
                        row=row,
                        row_index=row_index,
                        output_dir=prior_activation_root,
                    )
                if reused_result is not None:
                    checkpoint_source_kind = "prior_run"
                    checkpoint_source_root = prior_activation_root
                    break
        if reused_result is not None:
            preflight_result = {"preflight_status": "skipped_exact_row_checkpoint"}
            activation_result = dict(reused_result)
        else:
            preflight_result = dict(
                preflight_runner(
                    row=row,
                    row_index=row_index,
                    output_dir=preflight_root,
                    matlab_bin=Path(request.toolchain["matlab"]),
                    oss_converter=Path(request.toolchain["leaddbs2ossdbs"]),
                    run_converter=True,
                    matlab_timeout_s=None,
                    converter_timeout_s=None,
                )
            )
            if preflight_result.get("preflight_status") != "parameter_preflight_passed":
                raise RuntimeError(
                    "OSS parameter preflight failed for "
                    f"{(side_input.subject_id, side_input.side, source_index)}: "
                    f"{preflight_result.get('preflight_status', '')}"
                )
            activation_row = {**row, **preflight_result}
            activation_result = dict(
                activation_runner(
                    row=activation_row,
                    row_index=row_index,
                    output_dir=activation_root,
                    args=activation_args,
                )
            )
        if activation_result.get("row_status") != "probabilistic_activation_complete":
            raise RuntimeError(
                "OSS probabilistic activation failed for "
                f"{(side_input.subject_id, side_input.side, source_index)}: "
                f"{activation_result.get('row_status', '')}"
            )
        observed_ids = np.asarray(
            np.load(
                Path(
                    activation_result["right_canonical_candidate_fiber_ids_path"]
                ),
                mmap_mode="r",
            ),
            dtype=np.int64,
        )
        observed_probabilities = np.asarray(
            np.load(
                Path(activation_result["right_canonical_probability_path"]),
                mmap_mode="r",
            ),
            dtype=np.float32,
        )
        if not np.array_equal(observed_ids, valid_ids):
            raise RecordError("OSS row candidate axis differs from the final valid axis")
        if observed_probabilities.shape != (valid_ids.size,):
            raise RecordError("OSS row probability shape differs from the final valid axis")
        if not np.all(np.isfinite(observed_probabilities)) or np.any(
            (observed_probabilities < 0.0) | (observed_probabilities > 1.0)
        ):
            raise RecordError("OSS row probabilities fall outside [0, 1]")
        generation_row = {
            "row_index": row_index,
            "subject_id": side_input.subject_id,
            "side": side_input.side,
            "source_index": source_index,
            "source_path": str(source_path),
            "preflight_status": preflight_result["preflight_status"],
            "activation_status": activation_result["row_status"],
            "row_checkpoint_json": activation_result.get("row_checkpoint_json", ""),
            "row_checkpoint_reused": bool(
                activation_result.get("row_checkpoint_reused", False)
            ),
            "row_checkpoint_legacy_import": bool(
                activation_result.get("row_checkpoint_legacy_import", False)
            ),
            "row_checkpoint_source_kind": (
                checkpoint_source_kind
                if bool(activation_result.get("row_checkpoint_reused", False))
                else "generated"
            ),
            "row_checkpoint_source_root": (
                str(checkpoint_source_root)
                if bool(activation_result.get("row_checkpoint_reused", False))
                else str(activation_root)
            ),
            "row_checkpoint_source_run_id": _activation_root_run_id(
                checkpoint_source_root
                if bool(activation_result.get("row_checkpoint_reused", False))
                else activation_root
            ),
            "row_checkpoint_sha256": (
                _sha256_file(Path(activation_result["row_checkpoint_json"]))
                if str(activation_result.get("row_checkpoint_json", "")).strip()
                and Path(activation_result["row_checkpoint_json"]).is_file()
                else ""
            ),
            "probability_manifest": activation_result.get("probability_manifest", ""),
        }
        return (
            row_index,
            (side_input.subject_id, side_input.side),
            observed_probabilities.copy(),
            generation_row,
        )

    completed_rows: list[
        tuple[int, tuple[str, str], np.ndarray, dict[str, Any]]
    ] = []
    futures: dict[Future[Any], int] = {}
    with ThreadPoolExecutor(max_workers=int(row_workers)) as executor:
        for work_item in work_items:
            future = executor.submit(run_row, work_item)
            futures[future] = work_item[0]
        try:
            for future in as_completed(futures):
                completed_rows.append(future.result())
        except BaseException:
            # Running rows finish their atomic checkpoints; only queued rows cancel.
            for future in futures:
                future.cancel()
            raise

    side_sources: dict[tuple[str, str], list[np.ndarray]] = {}
    generation_rows: list[dict[str, Any]] = []
    for _, side_key, observed_probabilities, generation_row in sorted(
        completed_rows,
        key=lambda item: item[0],
    ):
        side_sources.setdefault(side_key, []).append(observed_probabilities)
        generation_rows.append(generation_row)

    side_probabilities = {
        key: (valid_ids, np.maximum.reduce(values).astype(np.float32, copy=False))
        for key, values in side_sources.items()
    }
    probabilities = merge.merge_right_canonical_probabilities(
        subject_order=request.final.subject_order,
        valid_fiber_ids=valid_ids,
        side_probabilities=side_probabilities,
    )
    np.save(probability_path, probabilities.astype(np.float32, copy=False))
    _write_json_atomic(
        external_root / "configured_oss_generation_manifest.json",
        {
            "compatibility_hash": request.compatibility_hash,
            "final_model_id": request.final.final_model_id,
            "final_record_hash": request.final.record_hash,
            "pam_n_samples": 10,
            "row_workers": int(row_workers),
            "scheduler_identity_sha256": scheduler_identity,
            "n_rows_reused": sum(
                bool(row["row_checkpoint_reused"]) for row in generation_rows
            ),
            "n_rows_generated": sum(
                not bool(row["row_checkpoint_reused"]) for row in generation_rows
            ),
            "n_subjects": len(request.final.subject_order),
            "n_subject_side_sources": len(generation_rows),
            "source_merge_rule": "max_probability_union",
            "hemisphere_merge_rule": "max_probability_union",
            "rows": generation_rows,
        },
    )
    return OSSGeneratedContent(probability_path, fiber_path)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
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


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _content_paths(cache_root: Path) -> OSSGeneratedContent:
    return OSSGeneratedContent(
        cache_root / "X_oss_float32_fiber_major.npy",
        cache_root / "oss_fiber_ids.npy",
    )


def _validate_generated_content(
    request: OSSSidecarPreparationRequest,
    content: OSSGeneratedContent,
) -> tuple[np.ndarray, np.ndarray]:
    probability_path = Path(content.activation_probabilities).resolve()
    fiber_path = Path(content.fiber_ids).resolve()
    if not probability_path.is_file() or not fiber_path.is_file():
        raise RecordError("OSS generated content is incomplete")
    probabilities = np.asarray(np.load(probability_path, mmap_mode="r"))
    fiber_ids = np.asarray(np.load(fiber_path, mmap_mode="r"), dtype=np.int64)
    expected_ids = np.asarray(
        request.compatibility_payload["ordered_valid_fiber_ids"],
        dtype=np.int64,
    )
    expected_shape = (len(request.final.subject_order), expected_ids.size)
    if probabilities.dtype != np.float32 or probabilities.shape != expected_shape:
        raise RecordError("OSS generated probability matrix shape or dtype is invalid")
    if not np.all(np.isfinite(probabilities)):
        raise RecordError("OSS generated probability matrix contains non-finite values")
    if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise RecordError("OSS generated probabilities fall outside [0, 1]")
    activated_counts = np.rint(
        probabilities.astype(np.float64) * 10.0
    ).astype(np.int64)
    expected_probabilities = (
        activated_counts.astype(np.float64) / 10.0
    ).astype(np.float32)
    if not np.array_equal(probabilities, expected_probabilities):
        raise RecordError("OSS generated probabilities are not on the ten-sample lattice")
    if not np.array_equal(fiber_ids, expected_ids):
        raise RecordError("OSS generated fiber IDs differ from the exact valid axis")
    return probabilities, fiber_ids


def _cache_valid(
    request: OSSSidecarPreparationRequest,
    cache_root: Path,
) -> OSSGeneratedContent | None:
    manifest_path = cache_root / "content_manifest.json"
    content = _content_paths(cache_root)
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        if manifest.get("compatibility_hash") != request.compatibility_hash:
            return None
        if manifest.get("compatibility_payload") != dict(request.compatibility_payload):
            return None
        if not content.activation_probabilities.is_file() or not content.fiber_ids.is_file():
            return None
        if manifest.get("activation_probabilities_file_sha256") != _sha256_file(
            content.activation_probabilities
        ):
            return None
        if manifest.get("fiber_ids_file_sha256") != _sha256_file(content.fiber_ids):
            return None
        _validate_generated_content(request, content)
    except (OSError, RecordError, ValueError):
        return None
    return content


def _artifact_ref(
    request: OSSSidecarPreparationRequest,
    *,
    kind: str,
    path: Path,
    shape: tuple[int, ...] = (),
) -> ArtifactRef:
    run_root = request.output_root.parents[3]
    return ArtifactRef(
        task_id=request.task.task_id,
        kind=kind,
        relative_path=path.resolve().relative_to(run_root).as_posix(),
        sha256=_sha256_file(path.resolve()),
        shape=shape,
    )


def run_configured_oss_sidecar_preparation(
    request: OSSSidecarPreparationRequest,
    *,
    generator: ContentGenerator | None = None,
) -> TaskResult:
    """Generate or exactly reuse content and publish destination-local sidecars."""
    run_root = request.output_root.parents[3]
    cache_root = run_root / "oss_content_cache" / request.compatibility_hash
    content = _cache_valid(request, cache_root)
    reused = content is not None
    if content is None:
        generator = generator or generate_configured_oss_content
        generated = generator(request, cache_root)
        probabilities, fiber_ids = _validate_generated_content(request, generated)
        cache_root.mkdir(parents=True, exist_ok=True)
        canonical = _content_paths(cache_root)
        if Path(generated.activation_probabilities).resolve() != canonical.activation_probabilities.resolve():
            _copy_atomic(Path(generated.activation_probabilities), canonical.activation_probabilities)
        if Path(generated.fiber_ids).resolve() != canonical.fiber_ids.resolve():
            _copy_atomic(Path(generated.fiber_ids), canonical.fiber_ids)
        content = canonical
        _write_json_atomic(
            cache_root / "content_manifest.json",
            {
                "compatibility_hash": request.compatibility_hash,
                "compatibility_payload": dict(request.compatibility_payload),
                "activation_probabilities_file_sha256": _sha256_file(
                    content.activation_probabilities
                ),
                "fiber_ids_file_sha256": _sha256_file(content.fiber_ids),
                "matrix_shape": list(probabilities.shape),
                "matrix_dtype": str(probabilities.dtype),
                "ordered_fiber_ids": fiber_ids.tolist(),
            },
        )
    probabilities, fiber_ids = _validate_generated_content(request, content)

    request.output_root.mkdir(parents=True, exist_ok=True)
    destination_probability = request.output_root / "X_oss_float32_fiber_major.npy"
    destination_fibers = request.output_root / "oss_fiber_ids.npy"
    _copy_atomic(content.activation_probabilities, destination_probability)
    _copy_atomic(content.fiber_ids, destination_fibers)
    frequency_values = {
        float(value)
        for value in request.compatibility_payload["modeled_frequencies_hz"].values()
    }
    uniform_frequency = (
        next(iter(frequency_values)) if len(frequency_values) == 1 else None
    )
    frequency_scope = (
        "uniform" if uniform_frequency is not None else "subject_side_specific"
    )
    component = str(request.compatibility_payload["component_identity"])
    parameter_path = request.output_root / "oss_parameter_manifest.json"
    metadata_path = request.output_root / "oss_activation_sidecar_metadata.json"
    fiber_file_hash = _sha256_file(destination_fibers)
    mapping = dict(request.compatibility_payload["left_to_right_mapping"])
    parameter = {
        "schema_version": "four_model_v1_oss_parameter_manifest",
        "endpoint_id": request.final.endpoint_model_id,
        "final_model_id": request.final.final_model_id,
        "final_record_hash": request.final.record_hash,
        "compatibility_hash": request.compatibility_hash,
        "connectome": "dtor",
        "oss_model": "OSS-DBSv2",
        "activation_model": "pPAM",
        "ppam_sample_count": int(request.compatibility_payload["ppam_sample_count"]),
        "ppam_sampling": dict(request.compatibility_payload["ppam_sampling"]),
        "oss_exposure_component": component,
        "frequency_scope": frequency_scope,
        "requested_frequency_hz": uniform_frequency,
        "oss_parameter_frequency_hz": uniform_frequency,
        "frequency_source": "source_stimulation_mat",
        "frequency_validation_status": (
            "verified_exact_match"
            if uniform_frequency is not None
            else "verified_exact_match_per_subject_side"
        ),
        "canonical_hemisphere": "right",
        "left_to_right_mapping_method": mapping["method"],
        "left_to_right_mapping_identity": mapping,
        "hemisphere_source_merge_rule": "max_probability_union",
        "subject_order": list(request.final.subject_order),
        "selected_tau": request.final.selected_tau,
        "selected_coverage": request.final.selected_coverage,
        "selected_source_feature_axis_sha256": request.final.feature_axis.sha256,
        "valid_feature_axis_sha256": request.final.valid_feature_axis.sha256,
        "parent_feature_axis_sha256": request.compatibility_payload[
            "parent_feature_axis_sha256"
        ],
        "connectome_input_sha256": request.compatibility_payload[
            "connectome_input_sha256"
        ],
        "generator_identity_sha256": request.compatibility_payload[
            "generator_identity_sha256"
        ],
        "oss_toolchain_sha256": dict(
            request.compatibility_payload["oss_toolchain_sha256"]
        ),
        "oss_environment_sha256": request.compatibility_payload[
            "oss_environment_sha256"
        ],
        "oss_fiber_ids_sha256": fiber_file_hash,
        "missing_subjects": [],
        "failed_subjects": [],
        "score": dict(request.score),
        "source_stimulation_input_hashes": dict(
            request.compatibility_payload["source_stimulation_input_hashes"]
        ),
        "requested_frequencies_hz": dict(
            request.compatibility_payload["requested_frequencies_hz"]
        ),
        "modeled_frequencies_hz": dict(
            request.compatibility_payload["modeled_frequencies_hz"]
        ),
    }
    if request.task.endpoint.model_family == "ulf_fiber":
        parameter.update(
            {
                "hf_overlap_exclusion_applied": True,
                "hf_overlap_definition": request.compatibility_payload[
                    "hf_overlap_definition"
                ],
            }
        )
    _write_json_atomic(parameter_path, parameter)
    metadata = {
        "schema_version": "four_model_v1_oss_activation_metadata",
        "endpoint_id": request.final.endpoint_model_id,
        "final_model_id": request.final.final_model_id,
        "final_record_hash": request.final.record_hash,
        "compatibility_hash": request.compatibility_hash,
        "activation_value_type": "pPAM_activation_probability",
        "ppam_sample_count": int(request.compatibility_payload["ppam_sample_count"]),
        "ppam_sampling": dict(request.compatibility_payload["ppam_sampling"]),
        "matrix_shape": list(probabilities.shape),
        "matrix_dtype": str(probabilities.dtype),
        "matrix_range": [float(np.min(probabilities)), float(np.max(probabilities))],
        "finite_check_status": "passed",
        "canonical_hemisphere": "right",
        "left_to_right_mapping_method": mapping["method"],
        "left_to_right_mapping_identity": mapping,
        "hemisphere_source_merge_rule": "max_probability_union",
        "subject_order": list(request.final.subject_order),
        "valid_feature_axis_sha256": request.final.valid_feature_axis.sha256,
        "parent_feature_axis_sha256": request.compatibility_payload[
            "parent_feature_axis_sha256"
        ],
        "connectome_input_sha256": request.compatibility_payload[
            "connectome_input_sha256"
        ],
        "generator_identity_sha256": request.compatibility_payload[
            "generator_identity_sha256"
        ],
        "oss_toolchain_sha256": dict(
            request.compatibility_payload["oss_toolchain_sha256"]
        ),
        "oss_environment_sha256": request.compatibility_payload[
            "oss_environment_sha256"
        ],
        "oss_fiber_ids_sha256": fiber_file_hash,
        "content_reused": reused,
    }
    _write_json_atomic(metadata_path, metadata)

    probability_ref = _artifact_ref(
        request,
        kind="oss_activation_probabilities",
        path=destination_probability,
        shape=probabilities.shape,
    )
    fiber_ref = _artifact_ref(
        request,
        kind="oss_fiber_ids",
        path=destination_fibers,
        shape=fiber_ids.shape,
    )
    parameter_ref = _artifact_ref(
        request,
        kind="oss_parameter_manifest",
        path=parameter_path,
    )
    metadata_ref = _artifact_ref(
        request,
        kind="oss_activation_metadata",
        path=metadata_path,
    )
    bundle = OSSSidecarBundle(
        final_model_id=request.final.final_model_id,
        final_record_hash=request.final.record_hash,
        compatibility_hash=request.compatibility_hash,
        activation_probabilities=probability_ref,
        fiber_ids=fiber_ref,
        parameter_manifest=parameter_ref,
        activation_metadata=metadata_ref,
    )
    return TaskResult(
        TaskStatus.COMPLETED,
        "configured_oss_sidecars_prepared",
        facts={
            "oss_sidecar_preparation_complete": True,
            "final_model_id": request.final.final_model_id,
            "final_record_hash": request.final.record_hash,
            "compatibility_hash": request.compatibility_hash,
            "oss_content_reused": reused,
            "oss_sidecar_bundle": bundle.as_dict(),
        },
        artifacts=(
            TaskArtifact("oss_activation_probabilities", destination_probability),
            TaskArtifact("oss_fiber_ids", destination_fibers),
            TaskArtifact("oss_parameter_manifest", parameter_path),
            TaskArtifact("oss_activation_metadata", metadata_path),
        ),
    )


RequestFactory = Callable[
    [TaskSpec, RunContext, FinalArtifactRecord],
    OSSSidecarPreparationRequest,
]
PreparationRunner = Callable[[OSSSidecarPreparationRequest], TaskResult]
FinalLoader = Callable[[TaskSpec, RunContext], FinalArtifactRecord]


class OSSSidecarPreparationService:
    """Prepare one sidecar bundle without cancelling unrelated endpoints."""

    def __init__(
        self,
        *,
        request_factory: RequestFactory,
        runner: PreparationRunner,
        final_loader: FinalLoader = load_final_record,
    ) -> None:
        self._request_factory = request_factory
        self._runner = runner
        self._final_loader = final_loader

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        final: FinalArtifactRecord | None = None
        try:
            final = self._final_loader(task, context)
            request = self._request_factory(task, context, final)
            result = self._runner(request)
            if not isinstance(result, TaskResult):
                raise RecordError("OSS sidecar runner returned an invalid result")
            return result
        except OSSSidecarInputsUnavailable as exc:
            return TaskResult(
                TaskStatus.INPUT_FAILURE,
                f"oss_sidecar_inputs_unavailable:{exc}",
                facts=_failure_facts(final),
            )
        except (OSError, RecordError, RuntimeError, ValueError) as exc:
            return TaskResult(
                TaskStatus.EXECUTION_FAILURE,
                f"oss_sidecar_preparation_failure:{exc}",
                facts=_failure_facts(final),
            )


def _failure_facts(final: FinalArtifactRecord | None) -> dict[str, Any]:
    facts: dict[str, Any] = {"oss_sidecar_preparation_complete": False}
    if final is not None:
        facts.update(
            {
                "final_model_id": final.final_model_id,
                "final_record_hash": final.record_hash,
            }
        )
    return facts


__all__ = [
    "OSSGeneratedContent",
    "OSSSideInput",
    "OSSSidecarInputsUnavailable",
    "OSSSidecarPreparationRequest",
    "OSSSidecarPreparationService",
    "build_configured_oss_sidecar_request",
    "generate_configured_oss_content",
    "oss_compatibility_hash",
    "run_configured_oss_sidecar_preparation",
    "validate_oss_side_inputs",
]
