"""Public orchestration for immutable whole-brain ROI atlas builds."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from my_helper.fiber.core.seed_target_connectivity.connectome import open_connectome
from my_helper.fiber.core.seed_target_connectivity.identity import canonical_hash

from .artifacts import (
    REGION_FIELDS,
    region_rows,
    sha256_file,
    verify_artifacts,
    write_artifact_index,
    write_csv,
    write_endpoint_qc,
    write_json,
    write_label_tables,
    write_readme,
    write_resolved_config,
)
from .endpoints import compute_endpoint_census
from .errors import PublicationError
from .export import export_binary_rois
from .labels import resolve_labels
from .models import AtlasBuildConfig, AtlasBuildResult
from .resampling import resample_integer_labels


def _implementation_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _input_hashes(config: AtlasBuildConfig, connectome_hash: str) -> dict[str, str]:
    return {
        "source_labeling": sha256_file(config.source_labeling),
        "source_labels": sha256_file(config.source_labels),
        "reference_image": sha256_file(config.reference_image),
        "connectome": connectome_hash,
    }


def _result_from_manifest(root: Path, reused: bool) -> AtlasBuildResult:
    manifest = json.loads((root / "build_manifest.json").read_text(encoding="utf-8"))
    return AtlasBuildResult(
        atlas_root=root,
        build_fingerprint=manifest["build_fingerprint"],
        label_count=int(manifest["label_count"]),
        main_roi_count=int(manifest["main_roi_count"]),
        white_matter_roi_count=int(manifest["white_matter_roi_count"]),
        n_fibers=int(manifest["n_fibers"]),
        n_endpoints=int(manifest["n_endpoints"]),
        reused=reused,
    )


def inspect_atlas_status(atlas_root: Path | str) -> dict[str, Any]:
    """Return verified immutable status for one published atlas."""

    root = Path(atlas_root).expanduser().resolve()
    manifest_path = root / "build_manifest.json"
    if not manifest_path.is_file():
        raise PublicationError(f"build manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_count = verify_artifacts(root)
    return {
        "status": manifest.get("status"),
        "atlas_root": str(root),
        "build_fingerprint": manifest.get("build_fingerprint"),
        "label_count": manifest.get("label_count"),
        "main_roi_count": manifest.get("main_roi_count"),
        "white_matter_roi_count": manifest.get("white_matter_roi_count"),
        "n_fibers": manifest.get("n_fibers"),
        "n_endpoints": manifest.get("n_endpoints"),
        "artifact_count": artifact_count,
    }


def validate_atlas_config(config: AtlasBuildConfig) -> dict[str, Any]:
    """Inspect all inputs without writing atlas artifacts."""

    source = nib.load(config.source_labeling)
    labels = resolve_labels(config, source)
    connectome = open_connectome(config.connectome)
    if connectome.metadata.n_fibers != config.expected_fiber_count:
        raise PublicationError(
            f"expected {config.expected_fiber_count} fibers, found {connectome.metadata.n_fibers}"
        )
    return {
        "status": "valid",
        "label_count": len(labels),
        "main_roi_count": sum(item.include_in_region_ranking for item in labels),
        "white_matter_roi_count": sum(not item.include_in_region_ranking for item in labels),
        "n_fibers": connectome.metadata.n_fibers,
        "n_endpoints": 2 * connectome.metadata.n_fibers,
        "connectome_source_hash": connectome.metadata.source_hash,
    }


def build_whole_brain_roi_atlas(config: AtlasBuildConfig) -> AtlasBuildResult:
    """Build or verify and reuse one immutable whole-brain ROI atlas."""

    source = nib.load(config.source_labeling)
    reference = nib.load(config.reference_image)
    labels = resolve_labels(config, source)
    connectome = open_connectome(config.connectome)
    if connectome.metadata.n_fibers != config.expected_fiber_count:
        raise PublicationError(
            f"expected {config.expected_fiber_count} fibers, found {connectome.metadata.n_fibers}"
        )
    input_hashes = _input_hashes(config, connectome.metadata.source_hash)
    implementation_hash = _implementation_hash()
    fingerprint = canonical_hash(
        {
            "configuration_hash": config.configuration_hash,
            "input_hashes": input_hashes,
            "implementation_hash": implementation_hash,
        }
    )
    root = config.atlas_root
    if root.exists():
        manifest_path = root / "build_manifest.json"
        if not manifest_path.is_file():
            raise PublicationError(f"existing atlas has no build manifest: {root}")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("build_fingerprint") != fingerprint:
            raise PublicationError("existing atlas has a different build fingerprint")
        verify_artifacts(root)
        return _result_from_manifest(root, reused=True)

    staging = root.parent / f".{root.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        image = resample_integer_labels(source, reference)
        output_ids = {
            int(item)
            for item in np.unique(np.asanyarray(image.dataobj))
            if int(item) != 0
        }
        expected_ids = {item.label_id for item in labels}
        if output_ids != expected_ids:
            missing = sorted(expected_ids - output_ids)
            raise PublicationError(f"resampling produced empty label {missing[0] if missing else 'unknown'}")
        nib.save(image, staging / "labels.nii.gz")
        rois = export_binary_rois(image, labels, staging)
        census = compute_endpoint_census(connectome, image, labels, config.fiber_chunk_size)
        rows = region_rows(labels, rois, census)
        write_label_tables(staging, labels)
        write_csv(staging / "region_manifest.csv", rows, REGION_FIELDS)
        write_json(staging / "region_manifest.json", rows)
        write_endpoint_qc(staging, rows, census)
        write_resolved_config(staging, config.resolved_mapping)
        write_readme(staging, rows, census)
        main_count = sum(item.include_in_region_ranking for item in labels)
        white_count = len(labels) - main_count
        write_json(
            staging / "build_manifest.json",
            {
                "status": "complete",
                "build_fingerprint": fingerprint,
                "configuration_hash": config.configuration_hash,
                "implementation_hash": implementation_hash,
                "input_hashes": input_hashes,
                "label_count": len(labels),
                "main_roi_count": main_count,
                "white_matter_roi_count": white_count,
                "n_fibers": census.n_fibers,
                "n_endpoints": census.n_endpoints,
                "assigned_endpoint_count": census.n_endpoints - census.unassigned_endpoint_count,
                "unassigned_endpoint_count": census.unassigned_endpoint_count,
                "atlas_index_generated": False,
                "gm_mask_generated": False,
            },
        )
        write_artifact_index(staging)
        root.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return _result_from_manifest(root, reused=False)
