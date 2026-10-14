"""Content-identified subject DWI/FOD and native-grid ROI preparation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
import uuid

from .errors import PublicationError, ValidationError
from .identity import canonical_hash, file_sha256, callable_implementation_hash
from .models import ResolvedSubjectInputs, ValidationBundle
from .roi import prepare_rois, roi_transform_inputs, roi_implementation_hash, target_qc, clean_target_mask
from .state import atomic_write_json, read_json
from .tools import run_command


def _input_paths(subject: ResolvedSubjectInputs) -> dict[str, Path]:
    return {
        "dwi": subject.dwi,
        "bvec": subject.bvec,
        "bval": subject.bval,
        "brain_mask": subject.brain_mask,
    }


def preparation_identity(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
) -> tuple[str, dict[str, Any]]:
    """Identify FOD preparation independently of ROI and tracking settings."""

    input_hashes = {
        key: {"path": str(path), "sha256": file_sha256(path)}
        for key, path in _input_paths(subject).items()
    }
    document = {
        "identity_version": 1,
        "subject_id": subject.subject_id,
        "inputs": input_hashes,
        "fod": {"response_algorithm": "tournier", "fod_algorithm": "csd"},
        "threads": validation.config.execution.preparation_threads_per_subject,
        "tools": {
            name: identity.version
            for name, identity in sorted(validation.tools.items())
            if name in {"mrconvert", "dwi2response", "dwi2fod"}
        },
        "code_hash": callable_implementation_hash(_prepare_fod, run_command, constants={}),
    }
    return canonical_hash(document), document


def _artifact_records(root: Path, paths: Mapping[str, Path]) -> dict[str, Any]:
    return {
        name: {
            "path": str(path),
            "relative_path": str(path.relative_to(root)),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in sorted(paths.items())
    }


def _verify_prepared(directory: Path, identity: str) -> dict[str, Any] | None:
    manifest_path = directory / "prepared_subject.json"
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or manifest.get("preparation_identity") != identity:
        return None
    for artifact in manifest.get("artifacts", {}).values():
        path = Path(artifact.get("path", ""))
        if not path.is_file() or file_sha256(path) != artifact.get("sha256"):
            return None
    return manifest


def _prepare_fod(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
    memory_observer: Callable[[float], None] | None = None,
    identity_record: tuple[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    """Create or reuse one complete content-identified subject preparation."""

    identity, identity_document = identity_record or preparation_identity(validation, subject)
    output_root = subject.output_root
    work_root = output_root / "work"
    final_dir = work_root / "preparations" / "fod" / identity
    existing = _verify_prepared(final_dir, identity) if final_dir.exists() else None
    if existing is not None:
        return existing, "reused"
    if final_dir.exists():
        raise PublicationError(
            f"invalid or non-tool-owned preparation directory blocks reuse: {final_dir}"
        )

    staging = work_root / "staging" / f"preparation-{identity}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    log_dir = staging / "logs"
    execution = validation.config.execution
    tools = validation.tools
    dwi_mif = staging / "dwi.mif"
    brain_mif = staging / "brainmask.mif"
    response = staging / "response_wm.txt"
    fod = staging / "wm_fod.mif"
    threads = str(execution.preparation_threads_per_subject)

    run_command(
        [
            tools["mrconvert"].executable,
            subject.dwi,
            dwi_mif,
            "-fslgrad",
            subject.bvec,
            subject.bval,
            "-nthreads",
            threads,
            "-force",
        ],
        log_path=log_dir / "mrconvert_dwi.log",
        memory_observer=memory_observer,
    )
    run_command(
        [
            tools["mrconvert"].executable,
            subject.brain_mask,
            brain_mif,
            "-datatype",
            "bit",
            "-nthreads",
            threads,
            "-force",
        ],
        log_path=log_dir / "mrconvert_brainmask.log",
        memory_observer=memory_observer,
    )
    run_command(
        [
            tools["dwi2response"].executable,
            "tournier",
            dwi_mif,
            response,
            "-mask",
            brain_mif,
            "-nthreads",
            threads,
            "-force",
        ],
        log_path=log_dir / "dwi2response.log",
        memory_observer=memory_observer,
    )
    run_command(
        [
            tools["dwi2fod"].executable,
            "csd",
            dwi_mif,
            response,
            fod,
            "-mask",
            brain_mif,
            "-nthreads",
            threads,
            "-force",
        ],
        log_path=log_dir / "dwi2fod.log",
        memory_observer=memory_observer,
    )
    for path in (dwi_mif, brain_mif, response, fod):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValidationError(f"preparation artifact is missing or empty: {path}")

    final_artifact_paths = {
        "dwi_mif": final_dir / dwi_mif.relative_to(staging),
        "brain_mask_mif": final_dir / brain_mif.relative_to(staging),
        "response_wm": final_dir / response.relative_to(staging),
        "wm_fod": final_dir / fod.relative_to(staging),
    }
    artifacts = _artifact_records(
        staging,
        {
            name: staging / path.relative_to(final_dir)
            for name, path in final_artifact_paths.items()
        },
    )
    for artifact in artifacts.values():
        artifact["path"] = str(final_dir / artifact["relative_path"])
    manifest = {
        "status": "complete",
        "subject_id": subject.subject_id,
        "subject_dir": str(subject.subject_dir),
        "preparation_identity": identity,
        "identity_document": identity_document,
        "generation_provenance": {
            "lead_dbs_git_commit": validation.lead_dbs_git_commit,
            "preparation_code_hash": validation.preparation_code_hash,
        },
        "artifacts": artifacts,
    }
    atomic_write_json(staging / "prepared_subject.json", manifest)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(staging, final_dir)
    except OSError as exc:
        raise PublicationError(
            f"cannot atomically publish preparation {final_dir}: {exc}"
        ) from exc
    verified = _verify_prepared(final_dir, identity)
    if verified is None:
        raise PublicationError(f"published preparation failed verification: {final_dir}")
    return verified, "generated"


def native_request_identity(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
    fod_identity: str,
    roi_inputs: Mapping[str, Any],
) -> str:
    """Identify native analysis inputs without display or other subjects."""

    from .tracking import generation_implementation_hash, classification_implementation_hash

    return canonical_hash({
        "fod": fod_identity,
        "roi_transform": dict(roi_inputs),
        "roi_code": roi_implementation_hash(),
        "matlab_version": validation.tools["matlab"].version,
        "roi_qc_code": callable_implementation_hash(prepare_rois, target_qc, clean_target_mask, constants={}),
        "roi_sources": dict(sorted(validation.source_roi_hashes.items())),
        "tracking_mask": file_sha256(subject.tracking_mask),
        "seeds": [
            {"key": seed.key, "source": str(seed.path),
             "targets": [{"key": t.key, "source": str(t.path)} for t in seed.targets]}
            for seed in validation.config.atlas.seeds
        ],
        "tracking": vars(validation.config.tracking),
        "chunk_size": validation.config.execution.generation_chunk_streamlines,
        "maximum": (None if validation.config.tracking.seedwide_streamlines is not None
                    else validation.config.execution.maximum_seedwide_streamlines),
        "threads": validation.config.execution.mrtrix_threads_per_seedwide_job,
        "tckgen": validation.tools["tckgen"].version,
        "generation_code": generation_implementation_hash(),
        "classification_code": classification_implementation_hash(),
    })


def prepare_subject(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
    repo_root: Path,
    memory_observer: Callable[[float], None] | None = None,
    identity_record: tuple[str, dict[str, Any]] | None = None,
    roi_inputs: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Compose reusable FOD preparation and individually identified native ROIs."""

    identity_record = identity_record or preparation_identity(validation, subject)
    inputs = dict(roi_inputs) if roi_inputs is not None else roi_transform_inputs(subject)
    rois = prepare_rois(
        validation.config, subject, subject.output_root / "work" / "preparations",
        validation.tools["matlab"], repo_root, memory_observer=memory_observer,
        transform_inputs=inputs, source_hashes=validation.source_roi_hashes,
    )
    tracking_mask = {"path": str(subject.tracking_mask), "sha256": file_sha256(subject.tracking_mask)}
    prior = read_json(subject.output_root / "work" / "state.json", default={})
    fod = prior.get("fod_preparation", {})
    reusable_seeds = {}
    if validation.config.tracking.seedwide_streamlines is not None:
        from .tracking import seedwide_identity
        for seed in validation.config.atlas.seeds:
            old = prior.get("seed_results", {}).get(seed.key, {})
            old_document = old.get("identity_document", {})
            if old_document.get("fod_input_identity") != identity_record[0]:
                continue
            candidate = {
                "preparation_identity": identity_record[0],
                "artifacts": old_document["preparation_artifacts"],
                "identity_document": {"inputs": {"tracking_mask": tracking_mask}},
            }
            identity, _ = seedwide_identity(validation.config, subject.subject_id, candidate,
                seed, rois["seeds"][seed.key], validation.tools, validation.tracking_code_hash,
                verify_artifacts=False)
            mother = next((row for row in prior.get("published_artifacts", [])
                           if row.get("semantic_key") == f"{seed.key}/seedwide"
                           and row.get("coordinate_space") == "native"), None)
            if (old.get("seedwide_identity") == identity and mother is not None
                    and Path(mother["path"]).is_file()
                    and file_sha256(mother["path"]) == mother["sha256"]):
                reusable_seeds[seed.key] = old
    if len(reusable_seeds) == len(validation.config.atlas.seeds):
        action = "reused_published_mothers"
    else:
        fod, action = _prepare_fod(validation, subject, memory_observer,
                                  identity_record=identity_record)
    result = {**fod, "rois": rois,
              "fod_preparation": fod, "reusable_published_seeds": reusable_seeds,
              "identity_document": {**fod["identity_document"],
                  "inputs": {**fod["identity_document"]["inputs"], "tracking_mask": tracking_mask}}}
    return result, action
