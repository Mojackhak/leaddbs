"""Content-identified subject DWI/FOD and native-grid ROI preparation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping
import uuid

from .errors import PublicationError, ValidationError
from .identity import canonical_hash, file_sha256
from .models import ResolvedSubjectInputs, ValidationBundle
from .roi import prepare_rois
from .state import atomic_write_json, read_json
from .tools import run_command


def _input_paths(subject: ResolvedSubjectInputs) -> dict[str, Path]:
    return {
        "dwi": subject.dwi,
        "bvec": subject.bvec,
        "bval": subject.bval,
        "b0": subject.b0,
        "brain_mask": subject.brain_mask,
        "tracking_mask": subject.tracking_mask,
        "anchor_native_reference": subject.anchor_native_reference,
        "target_to_anchor_image_deformation": (
            subject.target_to_anchor_image_deformation
        ),
        "anchor_to_b0_transform": subject.anchor_to_b0_transform,
        "coregistration_method_log": subject.coregistration_method_log,
    }


def preparation_identity(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
) -> tuple[str, dict[str, Any]]:
    """Return the complete scientific identity for one subject preparation."""

    input_hashes = {
        key: {"path": str(path), "sha256": file_sha256(path)}
        for key, path in _input_paths(subject).items()
    }
    document = {
        "identity_version": 1,
        "subject_id": subject.subject_id,
        "inputs": input_hashes,
        "b0_coregistration": {
            "method": subject.coregistration_method,
            "method_token": subject.coregistration_method_token,
            "approved": subject.coregistration_approved,
            "transform_direction": "anchorNative_world_to_b0_world",
        },
        "source_roi_hashes": dict(sorted(validation.source_roi_hashes.items())),
        "fod": {"response_algorithm": "tournier", "fod_algorithm": "csd"},
        "resampling": {
            "mni_to_anchor": "Lead-DBS inverse normalization GenericLabel",
            "anchor_to_b0": "direct tmat world affine nearest-neighbor",
            "target_cleaning": "target AND NOT seed on final DWI grid",
        },
        "tools": {
            name: identity.version
            for name, identity in sorted(validation.tools.items())
            if name in {"matlab", "mrconvert", "dwi2response", "dwi2fod"}
        },
        "code_hash": validation.preparation_code_hash,
    }
    return canonical_hash(document), document


def _replace_prefix(value: Any, source: Path, destination: Path) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _replace_prefix(item, source, destination)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_prefix(item, source, destination) for item in value]
    if isinstance(value, str):
        try:
            relative = Path(value).relative_to(source)
        except ValueError:
            return value
        return str(destination / relative)
    return value


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
    for seed in manifest.get("rois", {}).get("seeds", {}).values():
        seed_path = Path(seed.get("path", ""))
        if not seed_path.is_file() or file_sha256(seed_path) != seed.get("hash"):
            return None
        for target in seed.get("targets", []):
            target_path = Path(target.get("path", ""))
            if not target_path.is_file() or file_sha256(target_path) != target.get("hash"):
                return None
    return manifest


def prepare_subject(
    validation: ValidationBundle,
    subject: ResolvedSubjectInputs,
    repo_root: Path,
    memory_observer: Callable[[float], None] | None = None,
) -> tuple[dict[str, Any], str]:
    """Create or reuse one complete content-identified subject preparation."""

    identity, identity_document = preparation_identity(validation, subject)
    output_root = subject.output_root
    work_root = output_root / "work"
    final_dir = work_root / "preparations" / identity
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
    rois = prepare_rois(
        validation.config,
        subject,
        staging,
        tools["matlab"],
        repo_root,
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
    final_rois = _replace_prefix(rois, staging, final_dir)
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
        "rois": final_rois,
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
