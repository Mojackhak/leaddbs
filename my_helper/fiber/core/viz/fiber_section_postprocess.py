"""Publish the PDQ-39 normative-fiber two-dimensional spatial checkpoint."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import nibabel as nib
import numpy as np
import yaml

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from my_helper.fiber.core.seed_target_connectivity.connectome import open_connectome

from .fiber_projection import (
    PROJECTION_ALGORITHM,
    PROJECTION_VERSION,
    FiberSpatialProjection,
    compute_fiber_spatial_projection,
    load_binary_projection_mask,
    validate_exact_mask_geometry,
)
from .plugin.default import get_fiber_section_cfg
from .published_artifacts import PublicationCatalog, PublishedArtifact
from .voxel_sections import plot_signed_voxel_sections


SCHEMA_VERSION = "dual_frequency_fiber_section_postprocess_v1"
SPATIAL_CONFIG_SCHEMA = "normative_fiber_spatial_projection_v1"


@dataclass(frozen=True)
class _RoleSpec:
    role: str
    direct_colorbar_label: str = "Mean selected-fiber model score"
    target_colorbar_label: str = "Target-conditioned model score"


_ROLE_SPECS = (_RoleSpec("reference"), _RoleSpec("addon"))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML object required: {path}")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_record(path: str | Path, kind: str) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"fiber spatial resource is missing: {resolved}")
    return {
        "kind": kind,
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _nifti_resource_record(path: str | Path, kind: str) -> dict[str, Any]:
    record = _file_record(path, kind)
    image = nib.load(record["path"])
    if len(image.shape) != 3:
        raise ValueError(f"fiber spatial NIfTI must be three-dimensional: {path}")
    record.update(
        {
            "shape": [int(value) for value in image.shape],
            "dtype": str(image.get_data_dtype()),
            "orientation": list(nib.aff2axcodes(image.affine)),
            "affine": [
                [float(value) for value in row]
                for row in np.asarray(image.affine, dtype=np.float64)
            ],
        }
    )
    return record


def _validate_spatial_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != SPATIAL_CONFIG_SCHEMA:
        raise ValueError("unsupported fiber spatial projection schema")
    background = config.get("background")
    projection = config.get("projection")
    seeds = config.get("seeds")
    targets = config.get("targets")
    if not isinstance(background, Mapping) or not background.get("path"):
        raise ValueError("fiber spatial config requires background.path")
    if not isinstance(projection, Mapping):
        raise ValueError("fiber spatial config requires projection settings")
    expected_projection = {
        "grid_source": "role_seed",
        "direct_streamline_scope": "complete_path",
        "target_conditioned_scope": "seed_only",
        "per_fiber_per_voxel": "once",
        "target_hit_method": "segment_intersection",
        "target_membership": "independent_binary",
        "target_composition": "fractional_by_hit_count",
        "streamline_weight_source": "uniform_one",
        "no_target_policy": "exclude_and_report",
    }
    for key, expected in expected_projection.items():
        if projection.get(key) != expected:
            raise ValueError(
                f"fiber spatial projection setting {key!r} must be {expected!r}"
            )
    if not isinstance(seeds, Mapping) or set(seeds) != {"reference", "addon"}:
        raise ValueError("fiber spatial config requires reference and addon seeds")
    for role in ("reference", "addon"):
        value = seeds[role]
        if not isinstance(value, Mapping) or value.get("side") != "rh" or not value.get("path"):
            raise ValueError(f"fiber spatial seed {role!r} must be an explicit rh path")
    if not isinstance(targets, list) or not targets:
        raise ValueError("fiber spatial config requires an ordered target list")
    names: list[str] = []
    for target in targets:
        if not isinstance(target, Mapping):
            raise ValueError("every fiber spatial target must be an object")
        name = str(target.get("name", "")).strip()
        if not name or target.get("side") != "rh" or not target.get("path"):
            raise ValueError("every fiber spatial target requires name, rh side, and path")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("fiber spatial target names must be unique")


def _resolve_role_artifacts(
    catalog: PublicationCatalog,
    *,
    scale_id: str,
    role: str,
) -> tuple[dict[str, PublishedArtifact], dict[str, Any]]:
    final_artifact = catalog.resolve_relative(
        "normative_fiber_main", f"{scale_id}/{role}/final_model.json"
    )
    final_model = _read_json(final_artifact.path)
    if final_model.get("final_status") != "final_model_realized":
        raise ValueError(f"normative-fiber final model is incomplete: {role}")
    if final_model.get("scale_id") != scale_id:
        raise ValueError(f"normative-fiber final-model scale mismatch: {role}")
    if final_model.get("model_family") != role:
        raise ValueError(f"normative-fiber final-model role mismatch: {role}")
    resolver_relative = str(final_model.get("resolver_relative_path", ""))
    if not resolver_relative:
        raise ValueError(f"normative-fiber final model lacks resolver path: {role}")
    resolver_dir = Path(resolver_relative).parent
    source_selection = catalog.resolve_relative(
        "normative_fiber_main", resolver_relative
    )
    valid_relative = str(final_model.get("valid_feature_axis_relative_path", ""))
    if not valid_relative:
        raise ValueError(f"normative-fiber final model lacks valid feature axis: {role}")
    artifacts = {
        "final_model": final_artifact,
        "source_selection": source_selection,
        "valid_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", valid_relative
        ),
        "full_weights": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "full_weights.npy"
        ),
        "selected_sweet_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "selected_sweet_fiber_ids.npy"
        ),
        "selected_sour_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "selected_sour_fiber_ids.npy"
        ),
    }
    return artifacts, final_model


def _selected_fiber_data(
    artifacts: Mapping[str, PublishedArtifact],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid_ids = np.asarray(np.load(artifacts["valid_fiber_ids"].path), dtype=np.int64)
    full_weights = np.asarray(np.load(artifacts["full_weights"].path), dtype=np.float64)
    sweet_ids = np.asarray(
        np.load(artifacts["selected_sweet_fiber_ids"].path), dtype=np.int64
    )
    sour_ids = np.asarray(
        np.load(artifacts["selected_sour_fiber_ids"].path), dtype=np.int64
    )
    if valid_ids.ndim != 1 or full_weights.shape != valid_ids.shape:
        raise ValueError("valid fiber axis and full weights are not aligned")
    if np.unique(valid_ids).size != valid_ids.size:
        raise ValueError("valid fiber axis contains duplicate canonical IDs")
    if sweet_ids.ndim != 1 or sour_ids.ndim != 1:
        raise ValueError("selected sweet and sour IDs must be vectors")
    if np.intersect1d(sweet_ids, sour_ids).size:
        raise ValueError("selected sweet and sour fiber libraries overlap")
    weight_by_id = {
        int(fiber_id): float(weight)
        for fiber_id, weight in zip(valid_ids, full_weights, strict=True)
    }
    selected_ids = np.concatenate((sweet_ids, sour_ids))
    selected_is_sweet = np.concatenate(
        (
            np.ones(sweet_ids.size, dtype=np.bool_),
            np.zeros(sour_ids.size, dtype=np.bool_),
        )
    )
    missing = [int(value) for value in selected_ids if int(value) not in weight_by_id]
    if missing:
        raise ValueError(f"selected fibers are absent from the valid axis: {missing[:10]}")
    selected_scores = np.asarray(
        [weight_by_id[int(value)] for value in selected_ids], dtype=np.float64
    )
    order = np.argsort(selected_ids, kind="stable")
    return selected_ids[order], selected_scores[order], selected_is_sweet[order]


def _projection_cache_payload(
    result: FiberSpatialProjection,
    streamlines: Sequence[np.ndarray],
) -> dict[str, np.ndarray]:
    lengths = np.asarray([len(value) for value in streamlines], dtype=np.int64)
    streamline_indptr = np.empty(len(streamlines) + 1, dtype=np.int64)
    streamline_indptr[0] = 0
    np.cumsum(lengths, out=streamline_indptr[1:])
    points = np.concatenate(
        [np.asarray(value, dtype=np.float32) for value in streamlines], axis=0
    )
    payload = {
        key: np.asarray(value)
        for key, value in asdict(result).items()
        if key not in {"target_ids", "mass_conservation_max_abs_error"}
    }
    payload.update(
        {
            "target_ids": np.asarray(result.target_ids, dtype=np.str_),
            "mass_conservation_max_abs_error": np.asarray(
                result.mass_conservation_max_abs_error, dtype=np.float64
            ),
            "streamline_indptr": streamline_indptr,
            "streamline_points": points,
        }
    )
    return payload


def _write_projection_cache(
    path: Path,
    result: FiberSpatialProjection,
    streamlines: Sequence[np.ndarray],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **_projection_cache_payload(result, streamlines))
    temporary.replace(path)


def _load_projection_cache(
    path: Path,
) -> tuple[FiberSpatialProjection, tuple[np.ndarray, ...]]:
    with np.load(path, allow_pickle=False) as payload:
        result = FiberSpatialProjection(
            fiber_ids=np.asarray(payload["fiber_ids"], dtype=np.int64),
            scores=np.asarray(payload["scores"], dtype=np.float64),
            is_sweet=np.asarray(payload["is_sweet"], dtype=np.bool_),
            voxel_indptr=np.asarray(payload["voxel_indptr"], dtype=np.int64),
            voxel_indices=np.asarray(payload["voxel_indices"], dtype=np.int64),
            target_ids=tuple(str(value) for value in payload["target_ids"]),
            target_membership=np.asarray(payload["target_membership"], dtype=np.bool_),
            target_membership_fraction=np.asarray(
                payload["target_membership_fraction"], dtype=np.float64
            ),
            target_scores=np.asarray(payload["target_scores"], dtype=np.float64),
            seed_hits=np.asarray(payload["seed_hits"], dtype=np.bool_),
            direct_voxel_indices=np.asarray(
                payload["direct_voxel_indices"], dtype=np.int64
            ),
            direct_score_mean=np.asarray(payload["direct_score_mean"], dtype=np.float64),
            direct_support_count=np.asarray(
                payload["direct_support_count"], dtype=np.float64
            ),
            direct_sweet_count=np.asarray(
                payload["direct_sweet_count"], dtype=np.float64
            ),
            direct_sour_count=np.asarray(
                payload["direct_sour_count"], dtype=np.float64
            ),
            seed_voxel_indices=np.asarray(
                payload["seed_voxel_indices"], dtype=np.int64
            ),
            target_conditioned_score=np.asarray(
                payload["target_conditioned_score"], dtype=np.float64
            ),
            target_assigned_mass=np.asarray(
                payload["target_assigned_mass"], dtype=np.float64
            ),
            target_unassigned_mass=np.asarray(
                payload["target_unassigned_mass"], dtype=np.float64
            ),
            target_assignment_fraction=np.asarray(
                payload["target_assignment_fraction"], dtype=np.float64
            ),
            target_composition_mass=np.asarray(
                payload["target_composition_mass"], dtype=np.float64
            ),
            mass_conservation_max_abs_error=float(
                payload["mass_conservation_max_abs_error"]
            ),
        )
        offsets = np.asarray(payload["streamline_indptr"], dtype=np.int64)
        points = np.asarray(payload["streamline_points"], dtype=np.float32)
    streamlines = tuple(
        points[int(offsets[index]) : int(offsets[index + 1])]
        for index in range(offsets.size - 1)
    )
    return result, streamlines


def _save_sparse_nifti(
    path: Path,
    *,
    seed_path: Path,
    voxel_indices: np.ndarray,
    values: np.ndarray,
    description: str,
) -> dict[str, Any]:
    seed_image = nib.as_closest_canonical(nib.load(str(seed_path)))
    total_voxels = int(np.prod(seed_image.shape, dtype=np.int64))
    indices = np.asarray(voxel_indices, dtype=np.int64)
    vector = np.asarray(values, dtype=np.float32)
    if indices.ndim != 1 or vector.shape != indices.shape:
        raise ValueError("sparse NIfTI indices and values must be aligned vectors")
    if np.any(indices < 0) or np.any(indices >= total_voxels):
        raise ValueError("sparse NIfTI index is outside the projection grid")
    volume = np.full(total_voxels, np.nan, dtype=np.float32)
    volume[indices] = vector
    header = seed_image.header.copy()
    header.set_data_dtype(np.float32)
    header["descrip"] = description[:79]
    image = nib.Nifti1Image(
        volume.reshape(seed_image.shape, order="C"),
        np.asarray(seed_image.affine, dtype=np.float64),
        header,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name.removesuffix(".nii.gz") + ".tmp.nii.gz")
    nib.save(image, str(temporary))
    temporary.replace(path)
    return _nifti_resource_record(path, description)


def _write_csv_atomic(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _target_score_rows(result: FiberSpatialProjection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, target_id in enumerate(result.target_ids):
        hits = result.target_membership[:, index]
        score = result.target_scores[index]
        rows.append(
            {
                "target_id": target_id,
                "target_score": "" if not np.isfinite(score) else float(score),
                "fiber_count": int(np.sum(hits)),
                "sweet_fiber_count": int(np.sum(hits & result.is_sweet)),
                "sour_fiber_count": int(np.sum(hits & ~result.is_sweet)),
                "quantitative_mass": float(np.sum(hits, dtype=np.float64)),
                "streamline_weight_source": "uniform_one",
            }
        )
    return rows


def _membership_rows(result: FiberSpatialProjection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hit_counts = np.sum(result.target_membership, axis=1, dtype=np.int64)
    for fiber_index, fiber_id in enumerate(result.fiber_ids):
        for target_index, target_id in enumerate(result.target_ids):
            rows.append(
                {
                    "fiber_id": int(fiber_id),
                    "fiber_class": "sweet" if result.is_sweet[fiber_index] else "sour",
                    "model_score": float(result.scores[fiber_index]),
                    "target_id": target_id,
                    "binary_hit": int(result.target_membership[fiber_index, target_index]),
                    "target_hit_count": int(hit_counts[fiber_index]),
                    "fractional_membership": float(
                        result.target_membership_fraction[fiber_index, target_index]
                    ),
                    "streamline_weight": 1.0,
                }
            )
    return rows


def _target_qc(result: FiberSpatialProjection) -> dict[str, Any]:
    hit_counts = np.sum(result.target_membership, axis=1, dtype=np.int64)
    overlap = result.target_membership.astype(np.int64).T @ result.target_membership.astype(
        np.int64
    )
    bound_violation = 0.0
    for voxel_index, score in enumerate(result.target_conditioned_score):
        if not np.isfinite(score):
            continue
        active = result.target_composition_mass[voxel_index] > 0.0
        local_scores = result.target_scores[active]
        lower = float(np.min(local_scores))
        upper = float(np.max(local_scores))
        bound_violation = max(bound_violation, lower - float(score), float(score) - upper)
    return {
        "schema_version": SCHEMA_VERSION,
        "target_ids": list(result.target_ids),
        "selected_fiber_count": int(result.fiber_ids.size),
        "no_target_fiber_count": int(np.sum(hit_counts == 0)),
        "single_target_fiber_count": int(np.sum(hit_counts == 1)),
        "multiple_target_fiber_count": int(np.sum(hit_counts > 1)),
        "maximum_target_hits_per_fiber": int(np.max(hit_counts, initial=0)),
        "target_overlap_counts": overlap.tolist(),
        "target_hit_counts": [
            int(value) for value in np.sum(result.target_membership, axis=0)
        ],
        "seed_voxel_count_with_selected_fiber": int(result.seed_voxel_indices.size),
        "assigned_mass_sum": float(np.sum(result.target_assigned_mass)),
        "unassigned_mass_sum": float(np.sum(result.target_unassigned_mass)),
        "mass_conservation_max_abs_error": result.mass_conservation_max_abs_error,
        "target_score_bound_max_violation": max(0.0, float(bound_violation)),
        "streamline_weight_source": "uniform_one",
        "target_score_membership": "independent_binary",
        "voxel_composition_membership": "fractional_by_hit_count",
    }


def _projection_qc(result: FiberSpatialProjection) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": PROJECTION_ALGORITHM,
        "algorithm_version": PROJECTION_VERSION,
        "selected_fiber_count": int(result.fiber_ids.size),
        "sweet_fiber_count": int(np.sum(result.is_sweet)),
        "sour_fiber_count": int(np.sum(~result.is_sweet)),
        "direct_finite_voxel_count": int(result.direct_voxel_indices.size),
        "direct_score_min": float(np.min(result.direct_score_mean)),
        "direct_score_max": float(np.max(result.direct_score_mean)),
        "direct_support_max": float(np.max(result.direct_support_count)),
        "per_fiber_per_voxel": "once",
        "streamline_weight_source": "uniform_one",
        "direct_streamline_scope": "complete_path",
    }


def _result_reusable(path: Path, request_hash: str, root: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    outputs = payload.get("outputs")
    return (
        payload.get("status") == "complete"
        and payload.get("request_hash") == request_hash
        and isinstance(outputs, list)
        and all((root / str(value)).is_file() for value in outputs)
    )


def _render_figure(
    *,
    heat_path: Path,
    background_path: Path,
    seed_path: Path,
    figure_stem: Path,
    style: Mapping[str, Any],
    figure_payload: Mapping[str, Any],
    root: Path,
) -> tuple[dict[str, Any], list[str]]:
    output_paths = [
        figure_stem.with_suffix(f".{str(extension).lower().lstrip('.')}")
        for extension in style["formats"]
    ]
    figure = plot_signed_voxel_sections(
        heat_path,
        background_image=background_path,
        mask_image=seed_path,
        geometry_image=seed_path,
        geometry_threshold=0.0,
        style_config=style,
        output_paths=output_paths,
    )
    render_metadata = getattr(figure, "_mh_viz_voxel_section_metadata")
    plt.close(figure)
    relative_outputs = [path.relative_to(root).as_posix() for path in output_paths]
    result_path = figure_stem.with_suffix(".json")
    payload = {
        **dict(figure_payload),
        "status": "complete",
        "heatmap": _nifti_resource_record(heat_path, "fiber_display_derivative"),
        "style": dict(style),
        "render_metadata": render_metadata,
        "outputs": relative_outputs,
    }
    _write_json_atomic(result_path, payload)
    return payload, [*relative_outputs, result_path.relative_to(root).as_posix()]


def _write_root_index(root: Path, results: Sequence[Mapping[str, Any]]) -> None:
    rows = []
    for result in results:
        rows.append(
            {
                "status": result.get("status"),
                "scale_id": result.get("scale_id"),
                "model_role": result.get("model_role"),
                "final_branch": result.get("final_branch"),
                "selected_tau": result.get("selected_tau"),
                "selected_coverage": result.get("selected_coverage"),
                "selected_fiber_count": result.get("selected_fiber_count"),
                "result_path": result.get("result_path"),
            }
        )
    _write_csv_atomic(
        root / "endpoint_index.csv",
        (
            "status",
            "scale_id",
            "model_role",
            "final_branch",
            "selected_tau",
            "selected_coverage",
            "selected_fiber_count",
            "result_path",
        ),
        rows,
    )


def _write_readme(root: Path, scale_id: str) -> None:
    text = f"""# PDQ-39 Normative-Fiber Spatial Postprocess

This checkpoint contains only the `{scale_id}` reference and add-on normative-
fiber spatial display derivatives. It does not contain another clinical scale,
a direct-voxel model, or new statistical inference.

Browse the role-local results under:

```text
scales/{scale_id}/reference/fiber/
scales/{scale_id}/addon/fiber/
```

Each role contains a direct complete-path streamline-score mean and a seed-only
target-conditioned score. Support, assigned, and unassigned mass maps accompany
the signed figures. `endpoint_index.csv` and `manifest.json` provide the compact
cross-role index and provenance.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def run_single_scale_fiber_section_postprocess(
    *,
    scale_id: str,
    output_root: str | Path,
    normative_fiber_publication_root: str | Path,
    spatial_config_path: str | Path,
    style_overrides: Mapping[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Publish four PDQ-39 fiber section figures and their spatial derivatives."""

    normalized_scale = str(scale_id).strip()
    if not normalized_scale or "/" in normalized_scale or ".." in normalized_scale:
        raise ValueError("scale_id must be one safe path component")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    config_path = Path(spatial_config_path).expanduser().resolve()
    config = _read_yaml(config_path)
    _validate_spatial_config(config)
    config_record = _file_record(config_path, "fiber_spatial_projection_config")
    background_path = Path(str(config["background"]["path"])).expanduser().resolve()
    background_record = _nifti_resource_record(background_path, "anatomy_background")

    catalog = PublicationCatalog.from_config(
        {
            "normative_fiber_main": {
                "root": str(
                    Path(normative_fiber_publication_root).expanduser().resolve()
                ),
                "manifest": "model_manifest.json",
            }
        },
        config_base=root,
    )
    publication_manifest = catalog.manifest("normative_fiber_main")
    formal_connectome_id = str(publication_manifest.get("formal_connectome_id", ""))
    connectome_rows = publication_manifest.get("connectomes")
    if not isinstance(connectome_rows, list):
        raise ValueError("normative-fiber publication lacks connectome catalog")
    matches = [
        value
        for value in connectome_rows
        if isinstance(value, Mapping)
        and str(value.get("connectome_id")) == formal_connectome_id
    ]
    if len(matches) != 1:
        raise ValueError("normative-fiber publication does not identify one formal connectome")
    connectome = open_connectome(str(matches[0]["path"]))
    connectome_record = {
        "connectome_id": connectome.metadata.connectome_id,
        "path": str(connectome.metadata.source_path),
        "sha256": connectome.metadata.source_hash,
        "size_bytes": connectome.metadata.source_path.stat().st_size,
        "geometry_hash": connectome.metadata.geometry_hash,
        "ordered_fiber_id_hash": connectome.metadata.ordered_fiber_id_hash,
        "connectome_identity": connectome.metadata.connectome_identity,
        "n_fibers": connectome.metadata.n_fibers,
        "n_points": connectome.metadata.n_points,
    }

    target_specs = config["targets"]
    targets = tuple(
        load_binary_projection_mask(
            str(value["path"]), roi_id=str(value["name"]), role="target"
        )
        for value in target_specs
    )
    target_records = [
        _nifti_resource_record(value.source_path, f"target:{value.roi_id}")
        for value in targets
    ]
    base_style = get_fiber_section_cfg(style_overrides)
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "scale_id": normalized_scale,
        "spatial_config": config_record,
        "background": background_record,
        "connectome": connectome_record,
        "targets": target_records,
        "publications": catalog.publication_records(),
        "results": [],
    }
    _write_json_atomic(manifest_path, manifest)

    failures = 0
    for role_spec in _ROLE_SPECS:
        role_leaf = root / "scales" / normalized_scale / role_spec.role / "fiber"
        result_path = role_leaf / "result.json"
        try:
            artifacts, final_model = _resolve_role_artifacts(
                catalog, scale_id=normalized_scale, role=role_spec.role
            )
            if final_model.get("formal_connectome_id") != formal_connectome_id:
                raise ValueError(
                    f"final model formal connectome mismatch: {role_spec.role}"
                )
            seed_spec = config["seeds"][role_spec.role]
            seed = load_binary_projection_mask(
                str(seed_spec["path"]), roi_id=role_spec.role, role="seed"
            )
            validate_exact_mask_geometry(seed, targets)
            seed_record = _nifti_resource_record(
                seed.source_path, f"seed:{role_spec.role}"
            )
            source_records = {
                name: artifact.as_manifest_record()
                for name, artifact in artifacts.items()
            }
            projection_hash = _payload_hash(
                {
                    "schema_version": SCHEMA_VERSION,
                    "algorithm": PROJECTION_ALGORITHM,
                    "algorithm_version": PROJECTION_VERSION,
                    "scale_id": normalized_scale,
                    "model_role": role_spec.role,
                    "source_artifacts": source_records,
                    "connectome": connectome_record,
                    "spatial_config": config_record,
                    "seed": seed_record,
                    "targets": target_records,
                    "projection": config["projection"],
                }
            )
            request_hash = _payload_hash(
                {
                    "projection_hash": projection_hash,
                    "background": background_record,
                    "style": base_style,
                }
            )
            if not force and _result_reusable(result_path, request_hash, root):
                reused = _read_json(result_path)
                reused["resume_status"] = "reused"
                manifest["results"].append(reused)
                _write_json_atomic(manifest_path, manifest)
                continue

            selected_ids, selected_scores, selected_is_sweet = _selected_fiber_data(
                artifacts
            )
            cache_path = (
                root
                / ".cache"
                / normalized_scale
                / role_spec.role
                / f"fiber_projection_{projection_hash}.npz"
            )
            cache_status = "reused"
            if cache_path.is_file() and not force:
                projection, streamlines = _load_projection_cache(cache_path)
                if not np.array_equal(projection.fiber_ids, selected_ids):
                    raise ValueError("fiber projection cache selected-ID mismatch")
                if not np.array_equal(projection.scores, selected_scores):
                    raise ValueError("fiber projection cache score mismatch")
            else:
                streamlines = connectome.load_streamlines(selected_ids)
                projection = compute_fiber_spatial_projection(
                    fiber_ids=selected_ids,
                    scores=selected_scores,
                    is_sweet=selected_is_sweet,
                    streamlines=streamlines,
                    seed=seed,
                    targets=targets,
                )
                _write_projection_cache(cache_path, projection, streamlines)
                cache_status = "computed"

            direct_maps = role_leaf / "direct_streamline" / "maps"
            direct_figures = role_leaf / "direct_streamline" / "figures"
            target_maps = role_leaf / "target_conditioned" / "maps"
            target_tables = role_leaf / "target_conditioned" / "tables"
            target_figures = role_leaf / "target_conditioned" / "figures"
            outputs: list[str] = []
            map_specs = (
                (
                    direct_maps / "streamline_score_mean.nii.gz",
                    projection.direct_voxel_indices,
                    projection.direct_score_mean,
                    "mean selected-fiber model score",
                ),
                (
                    direct_maps / "streamline_support_count.nii.gz",
                    projection.direct_voxel_indices,
                    projection.direct_support_count,
                    "selected-fiber support count",
                ),
                (
                    direct_maps / "streamline_sweet_count.nii.gz",
                    projection.direct_voxel_indices,
                    projection.direct_sweet_count,
                    "selected sweet-fiber support count",
                ),
                (
                    direct_maps / "streamline_sour_count.nii.gz",
                    projection.direct_voxel_indices,
                    projection.direct_sour_count,
                    "selected sour-fiber support count",
                ),
                (
                    target_maps / "target_conditioned_score.nii.gz",
                    projection.seed_voxel_indices,
                    projection.target_conditioned_score,
                    "target-conditioned model score",
                ),
                (
                    target_maps / "target_assigned_mass.nii.gz",
                    projection.seed_voxel_indices,
                    projection.target_assigned_mass,
                    "target-assigned composition mass",
                ),
                (
                    target_maps / "target_unassigned_mass.nii.gz",
                    projection.seed_voxel_indices,
                    projection.target_unassigned_mass,
                    "target-unassigned composition mass",
                ),
                (
                    target_maps / "target_assignment_fraction.nii.gz",
                    projection.seed_voxel_indices,
                    projection.target_assignment_fraction,
                    "target-assignment fraction",
                ),
            )
            map_records: dict[str, dict[str, Any]] = {}
            for path, indices, values, description in map_specs:
                map_records[path.name] = _save_sparse_nifti(
                    path,
                    seed_path=seed.source_path,
                    voxel_indices=indices,
                    values=values,
                    description=description,
                )
                outputs.append(path.relative_to(root).as_posix())

            projection_qc_path = role_leaf / "direct_streamline" / "projection_qc.json"
            target_qc_path = role_leaf / "target_conditioned" / "target_membership_qc.json"
            _write_json_atomic(projection_qc_path, _projection_qc(projection))
            _write_json_atomic(target_qc_path, _target_qc(projection))
            outputs.extend(
                [
                    projection_qc_path.relative_to(root).as_posix(),
                    target_qc_path.relative_to(root).as_posix(),
                ]
            )
            target_score_path = target_tables / "target_scores.csv"
            membership_path = target_tables / "fiber_target_membership.csv"
            _write_csv_atomic(
                target_score_path,
                (
                    "target_id",
                    "target_score",
                    "fiber_count",
                    "sweet_fiber_count",
                    "sour_fiber_count",
                    "quantitative_mass",
                    "streamline_weight_source",
                ),
                _target_score_rows(projection),
            )
            _write_csv_atomic(
                membership_path,
                (
                    "fiber_id",
                    "fiber_class",
                    "model_score",
                    "target_id",
                    "binary_hit",
                    "target_hit_count",
                    "fractional_membership",
                    "streamline_weight",
                ),
                _membership_rows(projection),
            )
            outputs.extend(
                [
                    target_score_path.relative_to(root).as_posix(),
                    membership_path.relative_to(root).as_posix(),
                ]
            )

            common_figure_payload = {
                "schema_version": SCHEMA_VERSION,
                "scale_id": normalized_scale,
                "model_role": role_spec.role,
                "model_unit": "fiber_display_derivative",
                "source_artifacts": source_records,
                "connectome": connectome_record,
                "seed": seed_record,
                "background": background_record,
                "projection_hash": projection_hash,
            }
            direct_style = get_fiber_section_cfg(
                {**dict(style_overrides or {}), "colorbar_label": role_spec.direct_colorbar_label}
            )
            target_style = get_fiber_section_cfg(
                {**dict(style_overrides or {}), "colorbar_label": role_spec.target_colorbar_label}
            )
            _, direct_outputs = _render_figure(
                heat_path=direct_maps / "streamline_score_mean.nii.gz",
                background_path=background_path,
                seed_path=seed.source_path,
                figure_stem=direct_figures / "streamline_score_mean_sections",
                style=direct_style,
                figure_payload={
                    **common_figure_payload,
                    "display_artifact_kind": "direct_streamline_score_mean",
                },
                root=root,
            )
            _, target_outputs = _render_figure(
                heat_path=target_maps / "target_conditioned_score.nii.gz",
                background_path=background_path,
                seed_path=seed.source_path,
                figure_stem=target_figures / "target_conditioned_score_sections",
                style=target_style,
                figure_payload={
                    **common_figure_payload,
                    "display_artifact_kind": "target_conditioned_score",
                },
                root=root,
            )
            outputs.extend(direct_outputs)
            outputs.extend(target_outputs)
            result = {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "request_hash": request_hash,
                "projection_hash": projection_hash,
                "scale_id": normalized_scale,
                "model_role": role_spec.role,
                "final_branch": final_model.get("final_branch"),
                "selected_tau": final_model.get("selected_tau_v_per_m"),
                "selected_coverage": final_model.get(
                    "selected_coverage_subjects_min"
                ),
                "selected_fiber_count": int(selected_ids.size),
                "sweet_fiber_count": int(np.sum(selected_is_sweet)),
                "sour_fiber_count": int(np.sum(~selected_is_sweet)),
                "cache_status": cache_status,
                "cache_path": cache_path.relative_to(root).as_posix(),
                "source_artifacts": source_records,
                "map_records": map_records,
                "outputs": outputs,
                "result_path": result_path.relative_to(root).as_posix(),
            }
            _write_json_atomic(result_path, result)
            manifest["results"].append(result)
        except Exception as error:  # noqa: BLE001 - role-local failure is recorded
            failures += 1
            result = {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "scale_id": normalized_scale,
                "model_role": role_spec.role,
                "result_path": result_path.relative_to(root).as_posix(),
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
            _write_json_atomic(result_path, result)
            manifest["results"].append(result)
        _write_json_atomic(manifest_path, manifest)

    manifest["status"] = "complete" if failures == 0 else "completed_with_failures"
    manifest["completed_count"] = sum(
        value.get("status") == "complete" for value in manifest["results"]
    )
    manifest["reused_count"] = sum(
        value.get("resume_status") == "reused" for value in manifest["results"]
    )
    manifest["failed_count"] = failures
    _write_json_atomic(manifest_path, manifest)
    _write_root_index(root, manifest["results"])
    _write_readme(root, normalized_scale)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--normative-fiber-root", required=True)
    parser.add_argument("--spatial-config", required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_single_scale_fiber_section_postprocess(
        scale_id=args.scale_id,
        output_root=args.output_root,
        normative_fiber_publication_root=args.normative_fiber_root,
        spatial_config_path=args.spatial_config,
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "run_single_scale_fiber_section_postprocess"]
