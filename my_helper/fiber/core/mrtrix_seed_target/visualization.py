"""Deterministic target-space display sampling and scene input generation."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Mapping, Sequence
import uuid

from matplotlib import colormaps
import numpy as np
from scipy.io import savemat

from .errors import ValidationError
from .identity import canonical_hash, file_sha256
from .models import BatchConfig, ResolvedSubjectInputs, SeedSpec, ToolIdentity
from .publication import OWNER
from .state import atomic_write_json, read_json
from .tck import iter_tck
from .tools import run_command
from .tractogram_space import streamline_digest


def resolve_target_colors(config: BatchConfig, seed: SeedSpec) -> np.ndarray:
    """Resolve one distinct RGB row per target in authoritative YAML order."""

    count = len(seed.targets)
    if count <= 0:
        raise ValidationError(f"seed {seed.key} has no display targets")
    positions = np.arange(count, dtype=np.float64) / float(count)
    colors = np.asarray(
        colormaps[config.visualization.target_colormap](positions)[:, :3],
        dtype=np.float64,
    )
    if colors.shape != (count, 3) or not np.all(np.isfinite(colors)):
        raise ValidationError("configured colormap returned an invalid RGB array")
    if np.any(colors < 0) or np.any(colors > 1):
        raise ValidationError("configured colormap returned RGB values outside [0, 1]")
    if np.unique(colors, axis=0).shape[0] != count:
        raise ValidationError(
            f"configured colormap {config.visualization.target_colormap!r} does not "
            f"produce {count} distinct sampled colors"
        )
    return colors


def largest_remainder_quotas(
    counts: Sequence[int],
    budget: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Allocate a bounded display budget with deterministic YAML-order ties."""

    values = np.asarray(counts, dtype=np.int64)
    if values.ndim != 1 or values.size == 0 or np.any(values < 0):
        raise ValidationError("membership counts must be one nonempty nonnegative vector")
    if int(budget) <= 0:
        raise ValidationError("display budget must be positive")
    total = int(values.sum())
    realized = min(int(budget), total)
    if total == 0:
        return np.zeros_like(values), np.zeros(values.size, dtype=np.float64)
    ideal = realized * values.astype(np.float64) / float(total)
    quotas = np.floor(ideal).astype(np.int64)
    remaining = realized - int(quotas.sum())
    if remaining:
        remainders = ideal - quotas
        order = np.lexsort((np.arange(values.size), -remainders))
        quotas[order[:remaining]] += 1
    if np.any(quotas > values) or int(quotas.sum()) != realized:
        raise ValidationError("largest-remainder allocation violated its contract")
    return quotas, ideal


def midpoint_stratified_ordinals(count: int, quota: int) -> np.ndarray:
    """Return deterministic unique zero-based rows spanning one ordered target TCK."""

    count_value = int(count)
    quota_value = int(quota)
    if count_value < 0 or quota_value < 0 or quota_value > count_value:
        raise ValidationError("display quota must satisfy 0 <= quota <= count")
    if quota_value == 0:
        return np.empty(0, dtype=np.int64)
    rows = np.floor(
        (np.arange(quota_value, dtype=np.float64) + 0.5)
        * count_value
        / quota_value
    ).astype(np.int64)
    if np.unique(rows).size != quota_value:
        raise ValidationError("midpoint-stratified selection produced duplicate rows")
    return rows


def _selected_streamlines(
    path: Path,
    ordinals: np.ndarray,
) -> list[tuple[int, np.ndarray, str]]:
    wanted = iter(int(value) for value in ordinals)
    current = next(wanted, None)
    selected: list[tuple[int, np.ndarray, str]] = []
    for index, streamline in enumerate(iter_tck(path)):
        if current is None:
            break
        if index != current:
            continue
        points = np.asarray(streamline, dtype=np.float32)
        selected.append((index, points, streamline_digest(points)))
        current = next(wanted, None)
    if current is not None:
        raise ValidationError(f"display ordinal {current} is outside TCK {path}")
    return selected


def display_fingerprints(
    *,
    config: BatchConfig,
    seed: SeedSpec,
    target_records: Sequence[Mapping[str, object]],
    code_hash: str,
) -> dict[str, str]:
    """Return separate sampling, color, and style fingerprints."""

    sources = [
        {
            "semantic_key": record["semantic_key"],
            "sha256": record["sha256"],
            "streamline_count": int(record["streamline_count"]),
        }
        for record in target_records
    ]
    sampling = canonical_hash(
        {
            "target_fiber_display_budget": (
                config.visualization.target_fiber_display_budget
            ),
            "sources": sources,
            "selection": "largest_remainder_then_midpoint_stratified",
            "code_hash": code_hash,
        }
    )
    color = canonical_hash(
        {
            "target_colormap": config.visualization.target_colormap,
            "ordered_target_ids": [target.roi_id for target in seed.targets],
            "sampling_positions": [
                index / len(seed.targets) for index in range(len(seed.targets))
            ],
            "code_hash": code_hash,
        }
    )
    style = canonical_hash(
        {
            "seed_wireframe_color": config.visualization.seed_wireframe_color,
            "surface_masks": {
                "seed": {
                    "key": seed.key,
                    "sha256": file_sha256(seed.path),
                },
                "targets": [
                    {
                        "key": target.key,
                        "sha256": file_sha256(target.path),
                    }
                    for target in seed.targets
                ],
            },
            "target_face_alpha": 0.15,
            "seed_edge_alpha": 0.15,
            "seed_reduce_factor": 0.5,
            "fiber_line_width": 0.25,
            "fiber_alpha": 1.0,
            "view_helper": "mh_viz_default_fiber_views",
            "scene_helper": "mh_viz_default_fiber_scene_spec",
            "target_space": config.atlas.space,
            "code_hash": code_hash,
        }
    )
    return {"sampling": sampling, "color": color, "style_camera": style}


def prepare_display_input(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    seed: SeedSpec,
    state: Mapping[str, object],
    code_hash: str,
) -> dict[str, object]:
    """Write one complete deterministic subject-side MATLAB display input."""

    target_records_by_key = {
        str(record["semantic_key"]): record
        for record in state.get("published_artifacts", [])
        if record.get("coordinate_space") == config.atlas.space
    }
    target_records: list[Mapping[str, object]] = []
    target_paths: list[Path] = []
    counts: list[int] = []
    for target in seed.targets:
        key = f"{seed.key}/target/{target.key}"
        if key not in target_records_by_key:
            raise ValidationError(f"target-space display source is missing: {key}")
        record = target_records_by_key[key]
        path = Path(str(record["path"]))
        if not path.is_file() or file_sha256(path) != record["sha256"]:
            raise ValidationError(f"target-space display source hash failed: {path}")
        target_records.append(record)
        target_paths.append(path)
        counts.append(int(record["streamline_count"]))
    colors = resolve_target_colors(config, seed)
    quotas, ideal = largest_remainder_quotas(
        counts, config.visualization.target_fiber_display_budget
    )
    fingerprints = display_fingerprints(
        config=config,
        seed=seed,
        target_records=target_records,
        code_hash=code_hash,
    )
    scene_root = (
        subject.output_root
        / "visualization"
        / config.atlas.space
        / seed.side
        / seed.roi_id
    )
    input_root = scene_root / "inputs"
    input_root.mkdir(parents=True, exist_ok=True)
    points: list[np.ndarray] = []
    offsets = [0]
    fiber_target_indices: list[int] = []
    membership_rows: list[dict[str, object]] = []
    unique_digests: set[str] = set()
    for target_index, (target, path, count, quota) in enumerate(
        zip(seed.targets, target_paths, counts, quotas, strict=True), start=1
    ):
        rows = midpoint_stratified_ordinals(count, int(quota))
        for ordinal, streamline, digest in _selected_streamlines(path, rows):
            points.append(streamline)
            offsets.append(offsets[-1] + int(streamline.shape[0]))
            fiber_target_indices.append(target_index)
            unique_digests.add(digest)
            membership_rows.append(
                {
                    "target_id": target.roi_id,
                    "target_key": target.key,
                    "source_row_ordinal": ordinal,
                    "streamline_digest": digest,
                }
            )
    all_points = (
        np.concatenate(points, axis=0)
        if points
        else np.empty((0, 3), dtype=np.float32)
    )
    geometry_path = input_root / "display_geometry.mat"
    membership_path = input_root / "display_membership.csv"
    geometry_temp = input_root / f".{geometry_path.name}.{uuid.uuid4().hex}.tmp"
    savemat(
        geometry_temp,
        {
            "fiber_points": all_points,
            "fiber_offsets_zero_based": np.asarray(offsets, dtype=np.int64),
            "fiber_target_indices_one_based": np.asarray(
                fiber_target_indices, dtype=np.int32
            ),
            "target_ids": np.asarray(
                [target.roi_id for target in seed.targets], dtype=object
            ),
            "target_keys": np.asarray(
                [target.key for target in seed.targets], dtype=object
            ),
            "target_colors": colors,
            "target_mask_paths": np.asarray(
                [str(target.path) for target in seed.targets], dtype=object
            ),
            "target_available_counts": np.asarray(counts, dtype=np.int64),
            "target_display_counts": quotas.astype(np.int64),
            "seed_mask_path": np.asarray([str(seed.path)], dtype=object),
            "seed_wireframe_color": np.asarray(
                config.visualization.seed_wireframe_color, dtype=np.float64
            ),
            "subject_id": np.asarray([subject.subject_id], dtype=object),
            "side": np.asarray([seed.side], dtype=object),
            "seed_id": np.asarray([seed.roi_id], dtype=object),
            "target_space": np.asarray([config.atlas.space], dtype=object),
        },
        appendmat=False,
        do_compression=True,
    )
    os.replace(geometry_temp, geometry_path)
    membership_temp = input_root / f".{membership_path.name}.{uuid.uuid4().hex}.tmp"
    with membership_temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "target_id",
                "target_key",
                "source_row_ordinal",
                "streamline_digest",
            ),
        )
        writer.writeheader()
        writer.writerows(membership_rows)
    os.replace(membership_temp, membership_path)
    manifest = {
        "status": "display_input_complete",
        "subject_id": subject.subject_id,
        "side": seed.side,
        "seed_id": seed.roi_id,
        "target_space": config.atlas.space,
        "target_fiber_display_budget": (
            config.visualization.target_fiber_display_budget
        ),
        "realized_membership_instance_count": len(membership_rows),
        "unique_displayed_streamline_count": len(unique_digests),
        "cross_target_duplicate_instance_count": (
            len(membership_rows) - len(unique_digests)
        ),
        "target_colormap_name": config.visualization.target_colormap,
        "colormap_sample_positions": [
            index / len(seed.targets) for index in range(len(seed.targets))
        ],
        "ordered_target_ids": [target.roi_id for target in seed.targets],
        "targets": [
            {
                "target_id": target.roi_id,
                "target_key": target.key,
                "resolved_rgb": colors[index].tolist(),
                "target_mask_path": str(target.path),
                "target_mask_sha256": file_sha256(target.path),
                "source_target_tck_path": str(target_paths[index]),
                "source_target_tck_sha256": target_records[index]["sha256"],
                "streamline_count": counts[index],
                "membership_share": (
                    counts[index] / sum(counts) if sum(counts) else 0.0
                ),
                "ideal_quota": float(ideal[index]),
                "integer_quota": int(quotas[index]),
            }
            for index, target in enumerate(seed.targets)
        ],
        "seed_mask_path": str(seed.path),
        "seed_mask_sha256": file_sha256(seed.path),
        "seed_wireframe_color": list(config.visualization.seed_wireframe_color),
        "fingerprints": fingerprints,
        "geometry_path": str(geometry_path),
        "geometry_sha256": file_sha256(geometry_path),
        "membership_path": str(membership_path),
        "membership_sha256": file_sha256(membership_path),
    }
    manifest_path = scene_root / "sampling_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return {**manifest, "sampling_manifest_path": str(manifest_path)}


def _matlab_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def _verify_scene_complete(
    complete_path: Path,
    *,
    fingerprints: Mapping[str, str],
) -> dict[str, object] | None:
    try:
        document = read_json(complete_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(document, Mapping):
        return None
    if document.get("status") != "complete" or document.get("fingerprints") != dict(
        fingerprints
    ):
        return None
    for artifact in document.get("artifacts", []):
        path = Path(str(artifact.get("path", "")))
        if (
            not path.is_file()
            or path.stat().st_size <= 0
            or file_sha256(path) != artifact.get("sha256")
        ):
            return None
    return document


def visualization_state_errors(
    state: Mapping[str, object],
    *,
    expected_scene_keys: set[str],
) -> list[str]:
    """Return exact scene-publication errors without changing external state."""

    errors: list[str] = []
    scenes = state.get("visualization_scenes", {})
    if not isinstance(scenes, Mapping):
        return ["visualization_scenes is not a mapping"]
    actual_keys = set(str(key) for key in scenes)
    if actual_keys != expected_scene_keys:
        missing = sorted(expected_scene_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_scene_keys)
        errors.append(
            f"visualization scene keys differ: missing={missing}, unexpected={unexpected}"
        )
    for key in sorted(expected_scene_keys & actual_keys):
        record = scenes[key]
        if not isinstance(record, Mapping):
            errors.append(f"visualization scene record is invalid: {key}")
            continue
        complete_path = Path(str(record.get("complete_path", "")))
        try:
            complete = read_json(complete_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"visualization completion cannot be read: {complete_path}: {exc}")
            continue
        if complete.get("status") != "complete":
            errors.append(f"visualization completion is not complete: {complete_path}")
        if complete.get("fingerprints") != record.get("fingerprints"):
            errors.append(f"visualization fingerprint mismatch: {complete_path}")
        artifacts = complete.get("artifacts", [])
        if not isinstance(artifacts, list):
            errors.append(f"visualization artifact list is invalid: {complete_path}")
            continue
        suffixes = [
            Path(str(item.get("path", ""))).suffix.lower()
            for item in artifacts
            if isinstance(item, Mapping)
        ]
        if sorted(suffixes) != [".fig", ".pdf", ".png"]:
            errors.append(
                f"visualization artifacts must be exactly FIG, PNG, and PDF: {complete_path}"
            )
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                errors.append(f"visualization artifact record is invalid: {complete_path}")
                continue
            path = Path(str(artifact.get("path", "")))
            if (
                not path.is_file()
                or path.stat().st_size <= 0
                or file_sha256(path) != artifact.get("sha256")
            ):
                errors.append(f"visualization artifact failed: {path}")
        scene_root = complete_path.parent
        if scene_root.is_dir() and any(scene_root.rglob("*.svg")):
            errors.append(f"visualization contains prohibited SVG: {scene_root}")
    return errors


def render_display_scene(
    *,
    display: Mapping[str, object],
    matlab: ToolIdentity,
    repo_root: Path,
    code_hash: str,
) -> dict[str, object]:
    """Render and verify one repository-owned MATLAB subject-side scene."""

    sampling_manifest_path = Path(str(display["sampling_manifest_path"]))
    scene_root = sampling_manifest_path.parent
    complete_path = scene_root / "complete.json"
    fingerprints = dict(display["fingerprints"])
    existing = _verify_scene_complete(complete_path, fingerprints=fingerprints)
    if existing is not None:
        return {**existing, "action": "reused"}
    result_path = scene_root / "scene_result.json"
    log_path = scene_root / "render.log"
    geometry_path = Path(str(display["geometry_path"]))
    batch = (
        f"addpath(genpath('{_matlab_quote(repo_root)}')); "
        "mh_fiber_render_seed_target_space_scene("
        f"'{_matlab_quote(geometry_path)}',"
        f"'{_matlab_quote(scene_root)}',"
        f"'{_matlab_quote(result_path)}');"
    )
    run_command(
        [
            matlab.executable,
            "-noFigureWindows",
            "-nosplash",
            "-batch",
            batch,
        ],
        log_path=log_path,
    )
    result = read_json(result_path)
    if result.get("status") != "complete":
        raise ValidationError(f"MATLAB scene did not report complete: {result_path}")
    expected_controls = 2 * len(display["ordered_target_ids"]) + 3
    if (
        int(result.get("fiber_layer_count", -1)) != len(display["ordered_target_ids"])
        or int(result.get("target_surface_count", -1))
        != len(display["ordered_target_ids"])
        or int(result.get("seed_wireframe_count", -1)) != 1
        or int(result.get("control_count", -1)) != expected_controls
    ):
        raise ValidationError(f"MATLAB scene layer/control contract failed: {result_path}")
    output_paths = [
        Path(str(result["figure_path"])),
        Path(str(result["png_path"])),
        Path(str(result["pdf_path"])),
    ]
    for path in output_paths:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValidationError(f"scene output is missing or empty: {path}")
    svg_paths = list(scene_root.rglob("*.svg"))
    if svg_paths:
        raise ValidationError(f"SVG output is prohibited: {svg_paths}")
    generator = (
        repo_root
        / "my_helper"
        / "fiber"
        / "core"
        / "viz"
        / "mh_fiber_render_seed_target_space_scene.m"
    )
    scene_manifest = {
        "status": "complete",
        "subject_id": display["subject_id"],
        "side": display["side"],
        "seed_id": display["seed_id"],
        "target_space": display["target_space"],
        "ordered_target_ids": display["ordered_target_ids"],
        "target_colormap_name": display["target_colormap_name"],
        "targets": display["targets"],
        "seed_wireframe_color": display["seed_wireframe_color"],
        "styles": {
            "target_face_alpha": 0.15,
            "seed_face_color": "none",
            "seed_edge_alpha": 0.15,
            "seed_surface_reduce_factor": 0.5,
            "fiber_line_width": 0.25,
            "fiber_alpha": 1.0,
        },
        "fingerprints": fingerprints,
        "matlab": {"path": str(matlab.executable), "version": matlab.version},
        "generator": {
            "path": str(generator),
            "sha256": file_sha256(generator),
            "code_hash": code_hash,
        },
        "render_result": result,
        "artifacts": [
            {
                "path": str(path),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in output_paths
        ],
    }
    scene_manifest_path = scene_root / "scene_manifest.json"
    atomic_write_json(scene_manifest_path, scene_manifest)
    complete = {
        **scene_manifest,
        "scene_manifest_path": str(scene_manifest_path),
        "scene_manifest_sha256": file_sha256(scene_manifest_path),
    }
    atomic_write_json(complete_path, complete)
    return {**complete, "action": "generated"}


def generate_subject_visualizations(
    *,
    config: BatchConfig,
    subject: ResolvedSubjectInputs,
    matlab: ToolIdentity,
    repo_root: Path,
    code_hash: str,
) -> dict[str, object]:
    """Prepare, render, and verify every configured scene for one subject."""

    state_path = subject.output_root / "work" / "state.json"
    state = read_json(state_path, default={})
    if (
        not isinstance(state, dict)
        or state.get("owner") != OWNER
        or state.get("status") not in {
            "target_space_complete",
            "visualization_preparing",
            "visualization_rendering",
            "complete",
        }
    ):
        raise ValidationError(
            f"target-space completion is required before visualization: {state_path}"
        )
    results: list[dict[str, object]] = []
    for seed in config.atlas.seeds:
        state["status"] = "visualization_preparing"
        atomic_write_json(state_path, state)
        display = prepare_display_input(
            config=config,
            subject=subject,
            seed=seed,
            state=state,
            code_hash=code_hash,
        )
        state["status"] = "visualization_rendering"
        atomic_write_json(state_path, state)
        result = render_display_scene(
            display=display,
            matlab=matlab,
            repo_root=repo_root,
            code_hash=code_hash,
        )
        results.append(result)
        state.setdefault("visualization_scenes", {})[seed.key] = {
            "complete_path": str(
                subject.output_root
                / "visualization"
                / config.atlas.space
                / seed.side
                / seed.roi_id
                / "complete.json"
            ),
            "fingerprints": display["fingerprints"],
            "action": result["action"],
        }
        atomic_write_json(state_path, state)
    state["status"] = "complete"
    state["visualization_target_space"] = config.atlas.space
    atomic_write_json(state_path, state)
    return {
        "status": "complete",
        "subject_id": subject.subject_id,
        "visualization_scenes": results,
        "generated_scenes": sum(result["action"] == "generated" for result in results),
        "reused_scenes": sum(result["action"] == "reused" for result in results),
    }
