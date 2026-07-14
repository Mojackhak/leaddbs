"""Audited HybraPD label-only atlas and connectivity-result migration."""

from __future__ import annotations

import csv
import json
import os
import shutil
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import nibabel as nib
import numpy as np
from send2trash import send2trash

from my_helper.fiber.core.seed_target_connectivity.artifacts import (
    _write_index as write_connectivity_index,
    _write_text as write_connectivity_text,
    build_run_fingerprint,
    collect_code_provenance,
    stage_run_artifacts,
    verify_artifact_index,
)
from my_helper.fiber.core.seed_target_connectivity.cache import (
    cache_key,
    seed_cache_identity,
    target_cache_identity,
    write_target_cache,
)
from my_helper.fiber.core.seed_target_connectivity.config import (
    effective_config,
    load_config,
)
from my_helper.fiber.core.seed_target_connectivity.identity import canonical_hash
from my_helper.fiber.core.seed_target_connectivity.models import (
    ConnectomeMetadata,
    MembershipResult,
    ResolvedAtlas,
    StagedRunArtifacts,
    TargetFiberMembership,
)
from my_helper.fiber.core.seed_target_connectivity.pipeline import inspect_run_status
from my_helper.fiber.core.seed_target_connectivity.roi import resolve_atlas, resolve_seed
from my_helper.fiber.core.seed_target_connectivity.statistics import compute_statistics

from .artifacts import (
    REGION_FIELDS,
    sha256_file,
    verify_artifacts,
    write_artifact_index,
    write_csv,
    write_endpoint_qc,
    write_json,
    write_label_tables,
    write_readme,
    write_resolved_config,
    write_text,
)
from .config import load_atlas_config
from .labels import resolve_labels
from .models import EndpointCensus, EndpointLabelCount, ResolvedLabel
from .pipeline import _implementation_hash, inspect_atlas_status


CORRECTED_BASE_NAMES: Mapping[int, str] = {
    307: "Ventral_pallidum",
    308: "Ventral_pallidum",
    309: "External_globus_pallidus",
    310: "External_globus_pallidus",
    311: "Internal_globus_pallidus",
    312: "Internal_globus_pallidus",
    313: "Pars_reticulata_of_substantia_nigra",
    314: "Pars_reticulata_of_substantia_nigra",
    315: "Pars_compacta_of_substantia_nigra",
    316: "Pars_compacta_of_substantia_nigra",
    317: "Red_nucleus",
    318: "Red_nucleus",
    319: "Subthalamic_nucleus",
    320: "Subthalamic_nucleus",
    321: "Habenular_nucleus",
    322: "Habenular_nucleus",
    333: "Dentate_nucleus",
    334: "Dentate_nucleus",
}

EXPECTED_OFFICIAL_NAMES: Mapping[int, str] = {
    307: "Left VeP",
    308: "Right VeP",
    309: "Left GPe",
    310: "Right GPe",
    311: "Left GPi",
    312: "Right GPi",
    313: "Left SNr",
    314: "Right SNr",
    315: "Left SNc",
    316: "Right SNc",
    317: "Left RN",
    318: "Right RN",
    319: "Left STN",
    320: "Right STN",
    321: "Left HN",
    322: "Right HN",
    333: "Left DN",
    334: "Right DN",
}

EXPECTED_OLD_NAMES: Mapping[int, str] = {
    307: "Extended_amygdala_L",
    308: "Extended_amygdala_R",
    309: "Ventral_pallidum_L",
    310: "Ventral_pallidum_R",
    311: "External_globus_pallidus_L",
    312: "External_globus_pallidus_R",
    313: "Internal_globus_pallidus_L",
    314: "Internal_globus_pallidus_R",
    315: "Pars_reticulata_of_substantia_nigra_L",
    316: "Pars_reticulata_of_substantia_nigra_R",
    317: "Pars_compacta_of_substantia_nigra_L",
    318: "Pars_compacta_of_substantia_nigra_R",
    319: "Red_nucleus_L",
    320: "Red_nucleus_R",
    321: "Subthalamic_nucleus_L",
    322: "Subthalamic_nucleus_R",
    333: "Thalamus_L",
    334: "Thalamus_R",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_itksnap_label_file(path: Path | str) -> dict[int, str]:
    """Parse one ITK-SNAP label description file, including Unicode quotes."""

    records: dict[int, str] = {}
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=7)
        if len(parts) != 8:
            raise ValueError(f"invalid ITK-SNAP label line {line_number}: {raw!r}")
        try:
            label_id = int(parts[0])
            rgb = tuple(int(parts[index]) for index in (1, 2, 3))
            alpha = float(parts[4])
            flags = tuple(int(parts[index]) for index in (5, 6))
        except ValueError as exc:
            raise ValueError(f"invalid ITK-SNAP numeric fields on line {line_number}") from exc
        if label_id in records:
            raise ValueError(f"duplicate ITK-SNAP label ID {label_id}")
        if any(value < 0 or value > 255 for value in rgb) or not 0.0 <= alpha <= 1.0:
            raise ValueError(f"invalid ITK-SNAP display values on line {line_number}")
        if any(value not in (0, 1) for value in flags):
            raise ValueError(f"invalid ITK-SNAP visibility flag on line {line_number}")
        name = parts[7].strip()
        quote_pairs = (("\"", "\""), ("“", "”"))
        for opening, closing in quote_pairs:
            if name.startswith(opening) and name.endswith(closing):
                name = name[len(opening) : len(name) - len(closing)]
                break
        if not name:
            raise ValueError(f"empty ITK-SNAP label name on line {line_number}")
        records[label_id] = name
    if 0 not in records or len(records) != 199:
        raise ValueError("ITK-SNAP table must contain background plus exactly 198 labels")
    return records


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _canonical_names(
    old_rows: Sequence[Mapping[str, Any]],
    official_names: Mapping[int, str],
) -> dict[int, str]:
    old_by_id = {int(row["label_id"]): str(row["resolved_label_name"]) for row in old_rows}
    expected_ids = set(old_by_id)
    if set(official_names) - {0} != expected_ids:
        raise ValueError("official label IDs do not match the existing 198-label atlas")
    for label_id, expected in EXPECTED_OFFICIAL_NAMES.items():
        if official_names[label_id] != expected:
            raise ValueError(
                f"official label {label_id} is {official_names[label_id]!r}, expected {expected!r}"
            )
        if old_by_id[label_id] != EXPECTED_OLD_NAMES[label_id]:
            raise ValueError(
                f"existing label {label_id} is {old_by_id[label_id]!r}, expected the known erroneous mapping"
            )
    names = dict(old_by_id)
    for label_id, base in CORRECTED_BASE_NAMES.items():
        names[label_id] = f"{base}_{'L' if label_id % 2 else 'R'}"
    return names


def _desired_relative_path(label: ResolvedLabel) -> Path:
    side = {"L": "lh", "R": "rh", "M": "midline"}[label.hemisphere]
    if label.tissue_type == "white_matter":
        return Path(".qc") / "white_matter" / side / label.paired_filename
    return Path(side) / label.paired_filename


def _source_name_side(name: str) -> str:
    if name.startswith("Left ") or name.endswith("_L"):
        return "L"
    if name.startswith("Right ") or name.endswith("_R"):
        return "R"
    return "M"


def _validate_official_laterality(
    official_names: Mapping[int, str],
    source_image: nib.spatialimages.SpatialImage,
) -> None:
    data = np.asanyarray(source_image.dataobj)
    for label_id, name in official_names.items():
        if label_id == 0:
            continue
        side = _source_name_side(name)
        if side == "M":
            continue
        indices = np.argwhere(data == label_id)
        centroid_x = float(nib.affines.apply_affine(source_image.affine, indices).mean(axis=0)[0])
        spatial_side = "L" if centroid_x < 0.0 else "R"
        if side != spatial_side:
            raise ValueError(
                f"official label {label_id} side {side} disagrees with MNI centroid x={centroid_x}"
            )


def _build_census(rows: Sequence[Mapping[str, Any]], atlas_root: Path) -> EndpointCensus:
    old_manifest = _read_json(atlas_root / "build_manifest.json")
    endpoint_rows = _read_csv(atlas_root / "dtor_endpoint_qc.csv")
    unassigned = next(row for row in endpoint_rows if int(row["label_id"]) == 0)
    return EndpointCensus(
        n_fibers=int(old_manifest["n_fibers"]),
        n_endpoints=int(old_manifest["n_endpoints"]),
        labels=tuple(
            EndpointLabelCount(
                label_id=int(row["label_id"]),
                endpoint_count=int(row["endpoint_count"]),
                endpoint_fraction=float(row["endpoint_fraction"]),
                fiber_count=int(row["fiber_count"]),
                fiber_fraction=float(row["fiber_fraction"]),
            )
            for row in rows
        ),
        unassigned_endpoint_count=int(unassigned["endpoint_count"]),
        unassigned_endpoint_fraction=float(unassigned["endpoint_fraction"]),
        unassigned_fiber_count=int(unassigned["fiber_count"]),
        unassigned_fiber_fraction=float(unassigned["fiber_fraction"]),
        connectome_source_hash=str(old_manifest["input_hashes"]["connectome"]),
    )


def _write_crosswalk(
    path: Path,
    old_rows: Sequence[Mapping[str, Any]],
    labels: Sequence[ResolvedLabel],
    official_names: Mapping[int, str],
) -> None:
    old_by_id = {int(row["label_id"]): row for row in old_rows}
    fields = [
        "label_id",
        "official_label_name",
        "previous_resolved_label_name",
        "corrected_resolved_label_name",
        "correction_type",
    ]
    rows = []
    for label in labels:
        previous = str(old_by_id[label.label_id]["resolved_label_name"])
        if label.label_id in CORRECTED_BASE_NAMES:
            correction_type = "anatomical_id_name_correction"
        elif previous != label.resolved_label_name:
            correction_type = "laterality_or_canonical_name_normalization"
        else:
            correction_type = "unchanged"
        rows.append(
            {
                "label_id": label.label_id,
                "official_label_name": official_names[label.label_id],
                "previous_resolved_label_name": previous,
                "corrected_resolved_label_name": label.resolved_label_name,
                "correction_type": correction_type,
            }
        )
    write_csv(path, rows, fields)


def _update_region_rows(
    old_rows: Sequence[Mapping[str, Any]],
    labels: Sequence[ResolvedLabel],
) -> list[dict[str, Any]]:
    old_by_id = {int(row["label_id"]): dict(row) for row in old_rows}
    rows: list[dict[str, Any]] = []
    for label in labels:
        row = old_by_id[label.label_id]
        row.update(
            {
                "label_id": label.label_id,
                "source_label_name": label.source_label_name,
                "resolved_label_name": label.resolved_label_name,
                "base_name": label.base_name,
                "hemisphere": label.hemisphere,
                "category": label.category,
                "tissue_type": label.tissue_type,
                "include_in_region_ranking": label.include_in_region_ranking,
                "laterality_corrected": label.laterality_corrected,
                "source_voxel_count": label.source_voxel_count,
                "centroid_x": label.centroid_x,
                "centroid_y": label.centroid_y,
                "centroid_z": label.centroid_z,
                "contralateral_voxel_fraction": label.contralateral_voxel_fraction,
                "relative_path": _desired_relative_path(label).as_posix(),
            }
        )
        rows.append(row)
    return rows


def _validate_roi_files(
    atlas_root: Path,
    labels: Sequence[ResolvedLabel],
) -> None:
    label_image = nib.load(atlas_root / "labels.nii.gz")
    label_data = np.asanyarray(label_image.dataobj).astype(np.int64, copy=False)
    inverse = np.linalg.inv(label_image.affine)
    for label in labels:
        path = atlas_root / _desired_relative_path(label)
        image = nib.load(path)
        data = np.asanyarray(image.dataobj)
        nonzero = np.argwhere(data != 0)
        expected_count = int(np.count_nonzero(label_data == label.label_id))
        if nonzero.shape[0] != expected_count:
            raise ValueError(
                f"ROI {path} has {nonzero.shape[0]} voxels, expected {expected_count} for label {label.label_id}"
            )
        mapping = inverse @ image.affine
        full_indices = nib.affines.apply_affine(mapping, nonzero)
        rounded = np.rint(full_indices).astype(np.int64)
        if not np.allclose(full_indices, rounded, atol=1e-5, rtol=0.0):
            raise ValueError(f"ROI {path} is not aligned to the multi-label image grid")
        if np.any(rounded < 0) or np.any(rounded >= np.asarray(label_data.shape)):
            raise ValueError(f"ROI {path} maps outside the multi-label image")
        if not np.all(label_data[tuple(rounded.T)] == label.label_id):
            raise ValueError(f"ROI {path} contains voxels outside label {label.label_id}")


def _build_atlas_stage(
    *,
    atlas_config_path: Path,
    official_label_path: Path,
    label_table_stage: Path,
    atlas_stage: Path,
    applied_at: str,
) -> tuple[tuple[ResolvedLabel, ...], list[dict[str, Any]], dict[int, str], str]:
    config = load_atlas_config(atlas_config_path)
    old_root = config.atlas_root
    old_rows = _read_json(old_root / "region_manifest.json")
    official = parse_itksnap_label_file(official_label_path)
    source_image = nib.load(config.source_labeling)
    source_ids = {int(value) for value in np.unique(np.asanyarray(source_image.dataobj)) if int(value)}
    if set(official) - {0} != source_ids:
        raise ValueError("official label IDs do not exactly match the source NIfTI")
    _validate_official_laterality(official, source_image)
    canonical_names = _canonical_names(old_rows, official)
    write_text(
        label_table_stage,
        "\n".join(f"{label_id} {canonical_names[label_id]}" for label_id in sorted(canonical_names)),
    )
    temporary_config = replace(config, source_labels=label_table_stage)
    labels = resolve_labels(temporary_config, source_image)
    if len(labels) != 198 or sum(label.laterality_corrected for label in labels) != 0:
        raise ValueError("corrected canonical table must resolve 198 labels with no side corrections")

    atlas_stage.mkdir(parents=True, exist_ok=False)
    shutil.copy2(old_root / "labels.nii.gz", atlas_stage / "labels.nii.gz")
    old_by_id = {int(row["label_id"]): row for row in old_rows}
    occupied: set[Path] = set()
    for label in labels:
        old_path = old_root / str(old_by_id[label.label_id]["relative_path"])
        relative = _desired_relative_path(label)
        if relative in occupied:
            raise ValueError(f"corrected labels collide at {relative}")
        occupied.add(relative)
        new_path = atlas_stage / relative
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_path, new_path)
    for directory in ("lh", "rh", "midline", "mixed"):
        (atlas_stage / directory).mkdir(parents=True, exist_ok=True)
    if (old_root / "gm_mask.nii.gz").is_file():
        shutil.copy2(old_root / "gm_mask.nii.gz", atlas_stage / "gm_mask.nii.gz")
    shutil.copy2(official_label_path, atlas_stage / "labels_source_itksnap.label")

    rows = _update_region_rows(old_rows, labels)
    census = _build_census(rows, old_root)
    write_label_tables(atlas_stage, labels)
    write_csv(atlas_stage / "region_manifest.csv", rows, REGION_FIELDS)
    write_json(atlas_stage / "region_manifest.json", rows)
    write_endpoint_qc(atlas_stage, rows, census)
    write_resolved_config(atlas_stage, config.resolved_mapping)
    write_readme(atlas_stage, rows, census)
    _write_crosswalk(atlas_stage / "label_mapping_correction.csv", old_rows, labels, official)

    old_manifest = _read_json(old_root / "build_manifest.json")
    implementation_hash = _implementation_hash()
    input_hashes = {
        "source_labeling": sha256_file(config.source_labeling),
        "source_labels": sha256_file(label_table_stage),
        "reference_image": sha256_file(config.reference_image),
        "connectome": str(old_manifest["input_hashes"]["connectome"]),
    }
    fingerprint = canonical_hash(
        {
            "configuration_hash": config.configuration_hash,
            "input_hashes": input_hashes,
            "implementation_hash": implementation_hash,
        }
    )
    manifest = dict(old_manifest)
    manifest.update(
        {
            "build_fingerprint": fingerprint,
            "configuration_hash": config.configuration_hash,
            "implementation_hash": implementation_hash,
            "input_hashes": input_hashes,
            "atlas_index_generated": False,
            "gm_mask_generated": (atlas_stage / "gm_mask.nii.gz").is_file(),
            "label_correction": {
                "applied_at": applied_at,
                "source_label_file": str(official_label_path.resolve()),
                "source_label_sha256": sha256_file(official_label_path),
                "previous_build_fingerprint": old_manifest["build_fingerprint"],
                "corrected_label_ids": sorted(CORRECTED_BASE_NAMES),
                "canonical_naming": "expanded_english_with_L_R_suffixes",
                "multi_label_voxel_data_modified": False,
                "binary_roi_voxel_data_modified": False,
                "endpoint_counts_reused_by_label_id": True,
                "atlas_index_invalidated": True,
            },
        }
    )
    write_json(atlas_stage / "build_manifest.json", manifest)
    write_artifact_index(atlas_stage)
    verify_artifacts(atlas_stage)
    _validate_roi_files(atlas_stage, labels)
    return labels, rows, official, fingerprint


def _target_id(relative_path: str) -> str:
    lower = relative_path.lower()
    if lower.endswith(".nii.gz"):
        return relative_path[:-7]
    if lower.endswith(".nii"):
        return relative_path[:-4]
    raise ValueError(f"not a NIfTI relative path: {relative_path}")


def remap_target_membership(
    old_membership: TargetFiberMembership,
    old_target_to_label: Mapping[str, int],
    new_target_to_label: Mapping[str, int],
    new_target_order: Sequence[str],
) -> TargetFiberMembership:
    """Reorder existing target segments by immutable anatomical label ID."""

    old_label_to_target = {label_id: target_id for target_id, label_id in old_target_to_label.items()}
    if len(old_label_to_target) != len(old_target_to_label):
        raise ValueError("old target catalog does not map one-to-one to label IDs")
    if set(old_membership.target_ids) != set(old_target_to_label):
        raise ValueError("old target membership IDs do not match the old atlas catalog")
    if set(new_target_order) != set(new_target_to_label):
        raise ValueError("new target order does not match the corrected atlas catalog")
    parts: list[np.ndarray] = []
    for target_id in new_target_order:
        label_id = new_target_to_label[target_id]
        old_target = old_label_to_target[label_id]
        parts.append(np.asarray(old_membership.ids_for(old_target), dtype=np.int64).copy())
    indptr = np.empty(len(parts) + 1, dtype=np.int64)
    indptr[0] = 0
    for index, values in enumerate(parts):
        indptr[index + 1] = indptr[index] + values.size
    fiber_ids = np.concatenate(parts) if parts else np.empty(0, dtype=np.int64)
    indptr.setflags(write=False)
    fiber_ids.setflags(write=False)
    return TargetFiberMembership(
        target_ids=tuple(new_target_order),
        indptr=indptr,
        fiber_ids=fiber_ids,
    )


def _load_target_membership(path: Path) -> TargetFiberMembership:
    with np.load(path, allow_pickle=False) as archive:
        target_ids = tuple(str(value) for value in archive["target_ids"].tolist())
        indptr = np.asarray(archive["indptr"], dtype=np.int64)
        fiber_ids = np.asarray(archive["fiber_ids"], dtype=np.int64)
    indptr.setflags(write=False)
    fiber_ids.setflags(write=False)
    return TargetFiberMembership(target_ids=target_ids, indptr=indptr, fiber_ids=fiber_ids)


def _connectome_metadata(provenance: Mapping[str, Any]) -> ConnectomeMetadata:
    item = provenance["connectome"]
    return ConnectomeMetadata(
        connectome_id=str(item["connectome_id"]),
        source_path=Path(item["source_path"]),
        source_hash=str(item["source_hash"]),
        geometry_hash=str(item["geometry_hash"]),
        ordered_fiber_id_hash=str(item["ordered_fiber_id_hash"]),
        connectome_identity=str(item["connectome_identity"]),
        identity_source=str(item["identity_source"]),
        adapter_name="leaddbs_hdf5_idx",
        adapter_version="1",
        n_fibers=int(item["n_fibers"]),
        n_points=int(item["n_points"]),
    )


def _atlas_with_final_paths(stage_atlas: ResolvedAtlas, final_root: Path) -> ResolvedAtlas:
    targets = tuple(
        replace(target, source_path=(final_root / target.relative_path).resolve())
        for target in stage_atlas.targets
    )
    return replace(stage_atlas, root=final_root.resolve(), targets=targets)


def _augment_result_provenance(
    staged: StagedRunArtifacts,
    *,
    previous: Mapping[str, Any],
    source_label_path: Path,
    source_label_hash: str,
    atlas_previous_fingerprint: str,
    applied_at: str,
) -> None:
    if staged.staging_dir is None:
        raise ValueError("label correction unexpectedly reused an existing result")
    root = staged.staging_dir
    provenance_path = root / "provenance.json"
    provenance = _read_json(provenance_path)
    provenance["label_mapping_correction"] = {
        "applied_at": applied_at,
        "source_label_file": str(source_label_path.resolve()),
        "source_label_sha256": source_label_hash,
        "corrected_label_ids": sorted(CORRECTED_BASE_NAMES),
        "previous_run_fingerprint": previous["run_fingerprint"],
        "previous_atlas_build_fingerprint": atlas_previous_fingerprint,
        "connectome_streamline_geometry_read": False,
        "seed_membership_reused": True,
        "target_membership_reused_by_label_id": True,
        "statistics_recomputed_from_existing_membership": True,
        "migration_kind": "label_only",
    }
    write_connectivity_text(
        provenance_path,
        json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
    )
    indexed_hashes = {
        **dict(provenance["artifact_hashes"]),
        "provenance.json": sha256_file(provenance_path),
    }
    write_connectivity_index(
        root,
        indexed_hashes,
        {
            "configuration_hash": provenance["effective_configuration_hash"],
            "batch_configuration_hash": provenance["batch_configuration_hash"],
            "effective_configuration_hash": provenance["effective_configuration_hash"],
            "run_fingerprint": provenance["run_fingerprint"],
            "source_file_hashes_json": json.dumps(
                {
                    "seed": provenance["seed"]["source_hash"],
                    "targets": provenance["target_atlas"]["target_source_hashes"],
                    "connectome": provenance["connectome"]["source_hash"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            "connectome_identity": provenance["connectome"]["connectome_identity"],
            "ordered_fiber_id_hash": provenance["connectome"]["ordered_fiber_id_hash"],
            "algorithm_version": provenance["algorithm"]["intersection_version"],
            "fiber_chunk_size": provenance["algorithm"]["fiber_chunk_size"],
            "resolved_mask_hashes_json": json.dumps(
                {
                    "seed": provenance["seed"]["resolved_mask_hash"],
                    "target_atlas": provenance["target_atlas"]["resolved_mask_hash"],
                    "targets": provenance["target_atlas"]["target_resolved_mask_hashes"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            "code_provenance_json": json.dumps(
                provenance["code_provenance"],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "created_at": provenance["created_at"],
        },
    )
    verify_artifact_index(root)


def _compare_statistics_by_label(
    old_result_root: Path,
    old_target_to_label: Mapping[str, int],
    new_statistics: Sequence[Any],
    new_target_to_label: Mapping[str, int],
) -> None:
    old_rows = _read_csv(old_result_root / "target_connectivity.csv")
    old_by_label = {old_target_to_label[row["target_id"]]: row for row in old_rows}
    for row in new_statistics:
        label_id = new_target_to_label[row.target_id]
        old = old_by_label[label_id]
        expected = (
            int(old["n_all_fibers"]),
            int(old["n_seed_fibers"]),
            int(old["n_target_fibers"]),
            int(old["n_seed_target_fibers"]),
            int(old["raw_fiber_count"]),
        )
        actual = (
            row.n_all_fibers,
            row.n_seed_fibers,
            row.n_target_fibers,
            row.n_seed_target_fibers,
            row.raw_fiber_count,
        )
        if actual != expected:
            raise ValueError(f"fiber statistics changed for anatomical label {label_id}")


def _stage_results(
    *,
    connectivity_config_path: Path,
    atlas_stage: Path,
    atlas_final: Path,
    old_rows: Sequence[Mapping[str, Any]],
    new_rows: Sequence[Mapping[str, Any]],
    official_label_path: Path,
    applied_at: str,
    atlas_previous_fingerprint: str,
) -> tuple[dict[str, StagedRunArtifacts], ResolvedAtlas, TargetFiberMembership]:
    batch = load_config(connectivity_config_path)
    if batch.inputs.target_atlas_root.resolve() != atlas_final.resolve():
        raise ValueError("connectivity config does not point to the repaired atlas root")
    old_target_to_label = {
        _target_id(str(row["relative_path"])): int(row["label_id"])
        for row in old_rows
        if bool(row["include_in_region_ranking"])
    }
    new_target_to_label = {
        _target_id(str(row["relative_path"])): int(row["label_id"])
        for row in new_rows
        if bool(row["include_in_region_ranking"])
    }
    first_side = next(iter(batch.inputs.seed_rois))
    stage_resolved = resolve_atlas(atlas_stage, effective_config(batch, first_side))
    atlas = _atlas_with_final_paths(stage_resolved, atlas_final)
    new_target_order = tuple(target.roi_id for target in atlas.targets)
    if len(new_target_order) != 150:
        raise ValueError(f"corrected target atlas contains {len(new_target_order)} targets, expected 150")

    staged: dict[str, StagedRunArtifacts] = {}
    shared_membership: TargetFiberMembership | None = None
    source_label_hash = sha256_file(official_label_path)
    code_provenance = collect_code_provenance()
    metadata_identity: str | None = None
    for side in batch.inputs.seed_rois:
        final = batch.output.output_root / side / batch.output.run_name
        verify_artifact_index(final)
        previous = _read_json(final / "provenance.json")
        metadata = _connectome_metadata(previous)
        if metadata_identity is None:
            metadata_identity = metadata.connectome_identity
        elif metadata.connectome_identity != metadata_identity:
            raise ValueError("left and right results use different connectome identities")
        old_membership = _load_target_membership(final / "target_fiber_membership.npz")
        remapped = remap_target_membership(
            old_membership,
            old_target_to_label,
            new_target_to_label,
            new_target_order,
        )
        if shared_membership is None:
            shared_membership = remapped
        elif not (
            shared_membership.target_ids == remapped.target_ids
            and np.array_equal(shared_membership.indptr, remapped.indptr)
            and np.array_equal(shared_membership.fiber_ids, remapped.fiber_ids)
        ):
            raise ValueError("left and right result directories contain different target memberships")

        config = effective_config(batch, side)
        seed = resolve_seed(config.seed_roi, config)
        seed_ids = np.asarray(np.load(final / "seed_connected_fiber_ids.npy", allow_pickle=False), dtype=np.int64)
        seed_ids.setflags(write=False)
        seed_key = cache_key(seed_cache_identity(metadata, seed))
        if seed_key != previous["membership_cache"]["seed_cache_key"]:
            raise ValueError(f"seed cache identity changed unexpectedly for {side}")
        target_key = cache_key(target_cache_identity(metadata, atlas))
        membership = MembershipResult(
            n_all_fibers=metadata.n_fibers,
            seed_fiber_ids=seed_ids,
            target_membership=remapped,
            seed_cache_key=seed_key,
            target_cache_key=target_key,
            seed_cache_hit=bool(previous["membership_cache"]["seed_cache_hit"]),
            target_cache_hit=False,
            seed_cache_path=None,
            target_cache_path=None,
        )
        statistics = compute_statistics(membership, atlas, ranking_enabled=config.ranking.enabled)
        _compare_statistics_by_label(
            final,
            old_target_to_label,
            statistics,
            new_target_to_label,
        )
        staged_run = stage_run_artifacts(
            batch=batch,
            config=config,
            seed=seed,
            atlas=atlas,
            connectome_metadata=metadata,
            membership=membership,
            statistics=statistics,
            code_provenance=code_provenance,
        )
        expected_fingerprint = build_run_fingerprint(
            config=config,
            seed=seed,
            atlas=atlas,
            connectome_metadata=metadata,
            code_provenance=code_provenance,
        )
        if staged_run.run_fingerprint != expected_fingerprint:
            raise ValueError("staged run fingerprint is inconsistent")
        _augment_result_provenance(
            staged_run,
            previous=previous,
            source_label_path=official_label_path,
            source_label_hash=source_label_hash,
            atlas_previous_fingerprint=atlas_previous_fingerprint,
            applied_at=applied_at,
        )
        staged[side] = staged_run
    assert shared_membership is not None
    return staged, atlas, shared_membership


def _publish_transaction(
    replacements: Sequence[tuple[Path, Path]],
    validators: Sequence[Any],
) -> list[Path]:
    rollbacks: list[tuple[Path, Path]] = []
    published: list[tuple[Path, Path]] = []
    try:
        for staging, final in replacements:
            if not staging.exists() or not final.exists():
                raise ValueError(f"publication path is missing: staging={staging}, final={final}")
            rollback = final.parent / f".{final.name}.{uuid.uuid4().hex}.rollback"
            os.replace(final, rollback)
            rollbacks.append((rollback, final))
        for staging, final in replacements:
            os.replace(staging, final)
            published.append((final, staging))
        for validator in validators:
            validator()
    except Exception:
        for final, staging in reversed(published):
            if final.exists():
                os.replace(final, staging)
        for rollback, final in reversed(rollbacks):
            if rollback.exists():
                os.replace(rollback, final)
        raise
    trashed: list[Path] = []
    for rollback, _ in rollbacks:
        send2trash(str(rollback))
        trashed.append(rollback)
    return trashed


def repair_hybrapd_label_mapping(
    *,
    official_label_path: Path | str,
    atlas_config_path: Path | str,
    connectivity_config_path: Path | str,
) -> dict[str, Any]:
    """Repair the atlas and two result sides without reading streamline geometry."""

    official_path = Path(official_label_path).expanduser().resolve()
    atlas_config_file = Path(atlas_config_path).expanduser().resolve()
    connectivity_config_file = Path(connectivity_config_path).expanduser().resolve()
    atlas_config = load_atlas_config(atlas_config_file)
    atlas_final = atlas_config.atlas_root
    label_final = atlas_config.source_labels
    batch = load_config(connectivity_config_file)
    applied_at = _utc_now()
    token = uuid.uuid4().hex
    label_stage = label_final.parent / f".{label_final.name}.{token}.staging"
    atlas_stage = atlas_final.parent / f".{atlas_final.name}.{token}.staging"
    staged_results: dict[str, StagedRunArtifacts] = {}
    try:
        labels, new_rows, official, build_fingerprint = _build_atlas_stage(
            atlas_config_path=atlas_config_file,
            official_label_path=official_path,
            label_table_stage=label_stage,
            atlas_stage=atlas_stage,
            applied_at=applied_at,
        )
        old_rows = _read_json(atlas_final / "region_manifest.json")
        old_manifest = _read_json(atlas_final / "build_manifest.json")
        staged_results, resolved_atlas, shared_membership = _stage_results(
            connectivity_config_path=connectivity_config_file,
            atlas_stage=atlas_stage,
            atlas_final=atlas_final,
            old_rows=old_rows,
            new_rows=new_rows,
            official_label_path=official_path,
            applied_at=applied_at,
            atlas_previous_fingerprint=old_manifest["build_fingerprint"],
        )
        replacements: list[tuple[Path, Path]] = [
            (label_stage, label_final),
            (atlas_stage, atlas_final),
        ]
        for side in sorted(staged_results):
            staged = staged_results[side]
            if staged.staging_dir is None:
                raise ValueError(f"missing staged result for {side}")
            replacements.append((staged.staging_dir, staged.final_dir))

        def validate_labels() -> None:
            current = load_atlas_config(atlas_config_file)
            current_labels = resolve_labels(current, nib.load(current.source_labeling))
            if tuple(item.resolved_label_name for item in current_labels) != tuple(
                item.resolved_label_name for item in labels
            ):
                raise ValueError("published canonical label table differs from staging")

        def validate_atlas() -> None:
            inspect_atlas_status(atlas_final)
            _validate_roi_files(atlas_final, labels)

        validators = [validate_labels, validate_atlas]
        validators.extend(
            lambda root=staged.final_dir: inspect_run_status(root)
            for staged in staged_results.values()
        )
        _publish_transaction(replacements, validators)

        metadata = _connectome_metadata(
            _read_json(next(iter(staged_results.values())).final_dir / "provenance.json")
        )
        cache_path: Path | None = None
        cache_error: str | None = None
        try:
            cache_path = write_target_cache(
                batch.output.cache_root,
                target_cache_identity(metadata, resolved_atlas),
                shared_membership,
            )
        except Exception as exc:
            cache_error = f"{type(exc).__name__}: {exc}"
        result = {
            "status": "complete",
            "applied_at": applied_at,
            "source_label_sha256": sha256_file(official_path),
            "corrected_label_ids": sorted(CORRECTED_BASE_NAMES),
            "label_count": len(official) - 1,
            "atlas_build_fingerprint": build_fingerprint,
            "atlas_root": str(atlas_final),
            "atlas_index_invalidated": True,
            "target_cache_path": str(cache_path) if cache_path is not None else None,
            "results": {
                side: {
                    "run_dir": str(staged.final_dir),
                    "run_fingerprint": _read_json(staged.final_dir / "provenance.json")[
                        "run_fingerprint"
                    ],
                }
                for side, staged in staged_results.items()
            },
            "connectome_streamline_geometry_read": False,
        }
        if cache_error is not None:
            result["target_cache_warning"] = cache_error
        return result
    except Exception:
        if label_stage.exists():
            label_stage.unlink()
        if atlas_stage.exists():
            shutil.rmtree(atlas_stage)
        for staged in staged_results.values():
            if staged.staging_dir is not None and staged.staging_dir.exists():
                shutil.rmtree(staged.staging_dir)
        raise
