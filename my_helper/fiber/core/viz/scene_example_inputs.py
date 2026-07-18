"""Prepare immutable final-model inputs for interactive MATLAB scene examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import h5py
import nibabel as nib
import numpy as np
from scipy.io import savemat

from .artifacts import restore_voxel_vector_to_nifti


SCHEMA_VERSION = "dual_frequency_scene_example_input_v1"
_MODEL_FAMILIES = {
    "reference_voxel": "voxel",
    "addon_voxel": "voxel",
    "reference_fiber": "fiber",
    "addon_fiber": "fiber",
}


class SceneExampleInputError(RuntimeError):
    """Raised when a final model cannot form a faithful scene input."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SceneExampleInputError(f"cannot read JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise SceneExampleInputError(f"JSON object required: {path}")
    return payload


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _completed_manifest(path: Path, request_hash: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = _read_json(path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    if payload.get("status") != "complete" or payload.get("request_hash") != request_hash:
        return None
    input_path = Path(str(payload.get("input_path", "")))
    return payload if input_path.is_file() else None


def _file_uri_path(uri: str) -> Path:
    parsed = urlparse(str(uri))
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise SceneExampleInputError(f"final artifact requires a local file URI: {uri}")
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_file():
        raise SceneExampleInputError(f"final artifact is missing: {path}")
    return path


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _verified_artifact_path(reference: Mapping[str, Any]) -> Path:
    path = _file_uri_path(str(reference.get("uri", "")))
    expected = str(reference.get("sha256", ""))
    if len(expected) != 64 or _sha256_file(path) != expected:
        raise SceneExampleInputError(f"final artifact SHA-256 mismatch: {path}")
    return path


def _artifact(final_model: Mapping[str, Any], kind: str, *, required: bool = True) -> dict[str, Any] | None:
    values = [
        item
        for item in final_model.get("artifacts", [])
        if isinstance(item, Mapping) and item.get("kind") == kind
    ]
    if len(values) > 1 or (required and len(values) != 1):
        raise SceneExampleInputError(
            f"final model requires exactly one {kind} artifact; found {len(values)}"
        )
    return dict(values[0]) if values else None


def _find_final_selection(
    run_root: Path, scale_id: str, model_family: str
) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    tasks_root = run_root / "tasks"
    if not tasks_root.is_dir():
        raise SceneExampleInputError(f"run tasks directory is missing: {tasks_root}")
    for path in sorted(tasks_root.glob("task_*.json")):
        payload = _read_json(path)
        result = payload.get("result")
        if payload.get("status") != "completed" or not isinstance(result, Mapping):
            continue
        if result.get("output_record_type") != "FinalSelectionRecord":
            continue
        record = result.get("payload")
        if not isinstance(record, Mapping):
            continue
        endpoint = record.get("endpoint")
        if not isinstance(endpoint, Mapping):
            continue
        if endpoint.get("scale_id") != scale_id or endpoint.get("model_family") != model_family:
            continue
        if record.get("selection_status") != "final_model_realized":
            raise SceneExampleInputError(
                f"{scale_id} {model_family} does not have a realized final model"
            )
        final_model = record.get("final_model")
        if not isinstance(final_model, Mapping):
            raise SceneExampleInputError("realized FinalSelectionRecord lacks final_model")
        matches.append((path, dict(final_model)))
    if len(matches) != 1:
        raise SceneExampleInputError(
            f"expected one completed {scale_id} {model_family} final selection; found {len(matches)}"
        )
    return matches[0]


def _study_sources(run_root: Path) -> dict[str, Any]:
    payload = _read_json(run_root / "inputs" / "study_base.json")
    study = payload.get("study")
    if not isinstance(study, Mapping):
        raise SceneExampleInputError("study_base.json lacks study")
    sources = study.get("spot_model_sources")
    if not isinstance(sources, Mapping):
        raise SceneExampleInputError("study_base.json lacks spot_model_sources")
    return dict(sources)


def _request_identity(
    *,
    run_root: Path,
    task_path: Path,
    final_model: Mapping[str, Any],
    scale_id: str,
    model_family: str,
    sources: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    artifacts = []
    for item in final_model.get("artifacts", []):
        if isinstance(item, Mapping):
            artifacts.append(
                {
                    "kind": item.get("kind"),
                    "sha256": item.get("sha256"),
                    "uri": item.get("uri"),
                }
            )
    geometry_sources: list[dict[str, Any]] = []
    domain = _MODEL_FAMILIES[model_family]
    if domain == "voxel":
        brainmask = sources.get("brainmask")
        if not isinstance(brainmask, Mapping) or not brainmask.get("path"):
            raise SceneExampleInputError("study sources lack a brainmask path")
        geometry_path = Path(str(brainmask["path"])).expanduser().resolve()
    else:
        endpoint = final_model.get("endpoint")
        connectome_id = endpoint.get("connectome_id") if isinstance(endpoint, Mapping) else None
        if not connectome_id:
            raise SceneExampleInputError("fiber final model lacks connectome_id")
        geometry_path = _connectome_path(sources, str(connectome_id))
    if not geometry_path.is_file():
        raise SceneExampleInputError(f"scene geometry source is missing: {geometry_path}")
    geometry_stat = geometry_path.stat()
    geometry_sources.append(
        {
            "path": str(geometry_path),
            "size": geometry_stat.st_size,
            "mtime_ns": geometry_stat.st_mtime_ns,
        }
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_root": str(run_root),
        "final_selection_task": task_path.stem,
        "scale_id": scale_id,
        "model_family": model_family,
        "endpoint": final_model.get("endpoint"),
        "final_key": final_model.get("final_key"),
        "artifacts": artifacts,
        "canonical_space": sources.get("canonical_space"),
        "hemisphere_mapping": sources.get("hemisphere_mapping"),
        "geometry_sources": geometry_sources,
    }
    return _canonical_hash(payload), payload


def _array(path: Path, *, dtype: np.dtype[Any] | None = None) -> np.ndarray:
    value = np.load(path, allow_pickle=False)
    if dtype is not None and value.dtype != dtype:
        raise SceneExampleInputError(
            f"unexpected dtype for {path}: {value.dtype}; expected {dtype}"
        )
    return np.asarray(value)


def _prepare_voxel(
    stage: Path,
    final_model: Mapping[str, Any],
    sources: Mapping[str, Any],
    scale_id: str,
    model_family: str,
) -> tuple[Path, dict[str, Any]]:
    positions_ref = _artifact(final_model, "selected_feature_indices")
    weights_ref = _artifact(final_model, "benefit_oriented_feature_weights")
    assert positions_ref is not None and weights_ref is not None
    positions_path = _verified_artifact_path(positions_ref)
    weights_path = _verified_artifact_path(weights_ref)
    positions = _array(positions_path, dtype=np.dtype(np.int64))
    weights = np.asarray(_array(weights_path), dtype=np.float64)
    if positions.ndim != 1 or weights.ndim != 1 or positions.shape != weights.shape:
        raise SceneExampleInputError("voxel positions and weights must be matching vectors")
    if positions.size == 0 or np.any(np.diff(positions) <= 0):
        raise SceneExampleInputError("voxel positions must be nonempty, ordered, and unique")

    brainmask = sources.get("brainmask")
    if not isinstance(brainmask, Mapping) or not brainmask.get("path"):
        raise SceneExampleInputError("study sources lack a brainmask path")
    brainmask_path = Path(str(brainmask["path"])).expanduser().resolve()
    if not brainmask_path.is_file():
        raise SceneExampleInputError(f"brainmask is missing: {brainmask_path}")
    image = nib.load(str(brainmask_path))
    mask = np.asarray(image.dataobj) > 0
    grid_indices = np.argwhere(mask)
    coordinates = nib.affines.apply_affine(image.affine, grid_indices)
    mapping = sources.get("hemisphere_mapping")
    canonical = mapping.get("canonical_hemisphere") if isinstance(mapping, Mapping) else None
    if canonical == "R":
        keep = coordinates[:, 0] > 0.0
    elif canonical == "L":
        keep = coordinates[:, 0] < 0.0
    else:
        raise SceneExampleInputError(f"unsupported canonical hemisphere: {canonical}")
    canonical_indices = grid_indices[keep]
    parent_ids = np.ravel_multi_index(
        tuple(canonical_indices[:, axis] for axis in range(3)), image.shape
    ).astype(np.int64)
    if positions[-1] >= parent_ids.size:
        raise SceneExampleInputError("selected voxel position is outside the canonical parent axis")
    voxel_ids = parent_ids[positions]
    output = stage / f"{scale_id}_{model_family}_signed_weight.nii.gz"
    restore_voxel_vector_to_nifti(
        weights,
        voxel_ids,
        image,
        output,
        index_base=0,
        flat_index_order="C",
        metadata={
            "scale_id": scale_id,
            "model_family": model_family,
            "selected_feature_count": int(positions.size),
            "source_positions_artifact": str(positions_path),
            "source_weights_artifact": str(weights_path),
        },
    )
    return output, {
        "selected_feature_count": int(positions.size),
        "finite_weight_count": int(np.count_nonzero(np.isfinite(weights))),
        "brainmask": str(brainmask_path),
    }


def _connectome_path(sources: Mapping[str, Any], connectome_id: str) -> Path:
    entries = sources.get("connectomes")
    if not isinstance(entries, list):
        raise SceneExampleInputError("study sources lack connectomes")
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping) and item.get("connectome_id") == connectome_id
    ]
    if len(matches) != 1:
        raise SceneExampleInputError(
            f"expected one study connectome {connectome_id}; found {len(matches)}"
        )
    streamlines = matches[0].get("streamlines")
    if not isinstance(streamlines, Mapping) or not streamlines.get("path"):
        raise SceneExampleInputError(f"connectome {connectome_id} lacks a streamline path")
    path = Path(str(streamlines["path"])).expanduser().resolve()
    if not path.is_file():
        raise SceneExampleInputError(f"connectome is missing: {path}")
    return path


def _selected_fiber_geometry(
    connectome_path: Path, fiber_ids: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    try:
        with h5py.File(connectome_path, "r") as handle:
            if "fibers" not in handle or "idx" not in handle:
                raise SceneExampleInputError("connectome lacks fibers or idx")
            fibers = handle["fibers"]
            raw_lengths = np.asarray(handle["idx"][...], dtype=np.float64).reshape(-1)
            lengths = np.rint(raw_lengths).astype(np.int64)
            if (
                raw_lengths.size == 0
                or not np.all(np.isfinite(raw_lengths))
                or not np.array_equal(raw_lengths, lengths.astype(np.float64))
                or np.any(lengths < 2)
            ):
                raise SceneExampleInputError("connectome idx contains invalid fiber lengths")
            if fibers.ndim != 2:
                raise SceneExampleInputError("connectome fibers must be two-dimensional")
            if fibers.shape[0] in {4, 5}:
                row_major = True
                total_points = int(fibers.shape[1])
            elif fibers.shape[1] in {4, 5}:
                row_major = False
                total_points = int(fibers.shape[0])
            else:
                raise SceneExampleInputError("connectome fibers lack coordinate rows")
            if int(np.sum(lengths, dtype=np.int64)) != total_points:
                raise SceneExampleInputError("connectome idx does not span its point matrix")
            if np.any(fiber_ids < 1) or np.any(fiber_ids > lengths.size):
                raise SceneExampleInputError("selected fiber ID is outside the connectome")
            stops = np.cumsum(lengths, dtype=np.int64)
            selected_lengths = lengths[fiber_ids - 1]
            points = np.empty(
                (int(np.sum(selected_lengths, dtype=np.int64)), 3), dtype=np.float32
            )
            cursor = 0
            for fiber_id, point_count in zip(
                fiber_ids.tolist(), selected_lengths.tolist(), strict=True
            ):
                index = int(fiber_id) - 1
                start = 0 if index == 0 else int(stops[index - 1])
                stop = int(stops[index])
                if row_major:
                    block = np.asarray(fibers[:3, start:stop], dtype=np.float32).T
                else:
                    block = np.asarray(fibers[start:stop, :3], dtype=np.float32)
                if block.shape != (point_count, 3) or not np.all(np.isfinite(block)):
                    raise SceneExampleInputError(
                        f"selected fiber {fiber_id} has invalid geometry"
                    )
                points[cursor : cursor + point_count] = block
                cursor += point_count
    except OSError as exc:
        raise SceneExampleInputError(f"cannot read connectome: {connectome_path}") from exc
    return points, selected_lengths


def _prepare_fiber(
    stage: Path,
    final_model: Mapping[str, Any],
    sources: Mapping[str, Any],
    scale_id: str,
    model_family: str,
) -> tuple[Path, dict[str, Any]]:
    valid_ref = _artifact(final_model, "normative_fiber_valid_union_ids")
    weights_ref = _artifact(final_model, "benefit_oriented_fiber_weights")
    sweet_ref = _artifact(final_model, "normative_fiber_sweet_selected_ids", required=False)
    sour_ref = _artifact(final_model, "normative_fiber_sour_selected_ids", required=False)
    assert valid_ref is not None and weights_ref is not None
    valid_path = _verified_artifact_path(valid_ref)
    weights_path = _verified_artifact_path(weights_ref)
    valid_ids = _array(valid_path, dtype=np.dtype(np.int64))
    weights = np.asarray(_array(weights_path), dtype=np.float64)
    if valid_ids.ndim != 1 or weights.ndim != 1 or valid_ids.shape != weights.shape:
        raise SceneExampleInputError("valid fiber IDs and weights must be matching vectors")
    if valid_ids.size == 0 or np.any(np.diff(valid_ids) <= 0):
        raise SceneExampleInputError("valid fiber IDs must be nonempty, ordered, and unique")

    def selected_ids(reference: dict[str, Any] | None) -> np.ndarray:
        if reference is None:
            return np.empty(0, dtype=np.int64)
        return _array(_verified_artifact_path(reference), dtype=np.dtype(np.int64))

    sweet_ids = selected_ids(sweet_ref)
    sour_ids = selected_ids(sour_ref)
    if sweet_ids.ndim != 1 or sour_ids.ndim != 1:
        raise SceneExampleInputError("selected sweet and sour fiber IDs must be vectors")
    display_ids = np.unique(np.concatenate((sweet_ids, sour_ids))).astype(np.int64)
    if display_ids.size == 0:
        raise SceneExampleInputError("final model has no selected sweet or sour fibers")
    if np.intersect1d(sweet_ids, sour_ids).size:
        raise SceneExampleInputError("sweet and sour selected fiber IDs overlap")
    positions = np.searchsorted(valid_ids, display_ids)
    if np.any(positions >= valid_ids.size) or not np.array_equal(valid_ids[positions], display_ids):
        raise SceneExampleInputError("selected display fiber is outside the valid final axis")
    scores = weights[positions]
    if not np.all(np.isfinite(scores)) or not np.any(scores != 0.0):
        raise SceneExampleInputError("selected display fiber weights are not finite and nonzero")
    sweet_positions = np.searchsorted(display_ids, sweet_ids)
    sour_positions = np.searchsorted(display_ids, sour_ids)
    if sweet_ids.size and np.any(scores[sweet_positions] <= 0.0):
        raise SceneExampleInputError("sweet selected fibers must have positive weights")
    if sour_ids.size and np.any(scores[sour_positions] >= 0.0):
        raise SceneExampleInputError("sour selected fibers must have negative weights")

    endpoint = final_model.get("endpoint")
    connectome_id = endpoint.get("connectome_id") if isinstance(endpoint, Mapping) else None
    if not connectome_id:
        raise SceneExampleInputError("fiber final model lacks connectome_id")
    connectome = _connectome_path(sources, str(connectome_id))
    fibers, point_counts = _selected_fiber_geometry(connectome, display_ids)
    output = stage / f"{scale_id}_{model_family}_scored_fibers.mat"
    savemat(
        output,
        {
            "fibers": fibers,
            "idx": point_counts.reshape(1, -1),
            "scores": scores.reshape(-1, 1),
            "fiber_ids": display_ids.reshape(-1, 1),
            "sweet_fiber_ids": sweet_ids.reshape(-1, 1),
            "sour_fiber_ids": sour_ids.reshape(-1, 1),
        },
        do_compression=True,
    )
    return output, {
        "connectome_id": str(connectome_id),
        "connectome_path": str(connectome),
        "display_fiber_count": int(display_ids.size),
        "sweet_fiber_count": int(sweet_ids.size),
        "sour_fiber_count": int(sour_ids.size),
        "point_count": int(fibers.shape[0]),
        "score_limit": float(np.max(np.abs(scores))),
    }


def prepare_scene_example_input(
    run_root: str | Path,
    output_root: str | Path,
    *,
    scale_id: str,
    model_family: str,
) -> dict[str, Any]:
    """Prepare one request-addressed voxel or fiber MATLAB scene input."""

    run = Path(run_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    if model_family not in _MODEL_FAMILIES:
        raise SceneExampleInputError(f"unsupported model_family: {model_family}")
    task_path, final_model = _find_final_selection(run, scale_id, model_family)
    sources = _study_sources(run)
    request_hash, request = _request_identity(
        run_root=run,
        task_path=task_path,
        final_model=final_model,
        scale_id=scale_id,
        model_family=model_family,
        sources=sources,
    )
    target = output / f"{scale_id}-{model_family}-{request_hash[:16]}"
    manifest_path = target / "manifest.json"
    reusable = _completed_manifest(manifest_path, request_hash)
    if reusable is not None:
        return reusable
    if target.exists():
        raise SceneExampleInputError(
            f"refusing to replace an incomplete scene-input directory: {target}"
        )

    output.mkdir(parents=True, exist_ok=True)
    stage = output / f".tmp-{target.name}-{uuid.uuid4().hex}"
    stage.mkdir()
    domain = _MODEL_FAMILIES[model_family]
    if domain == "voxel":
        input_path, details = _prepare_voxel(
            stage, final_model, sources, scale_id, model_family
        )
    else:
        input_path, details = _prepare_fiber(
            stage, final_model, sources, scale_id, model_family
        )
    final_key = final_model.get("final_key")
    endpoint = final_model.get("endpoint")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "request_hash": request_hash,
        "request": request,
        "scale_id": scale_id,
        "model_family": model_family,
        "domain": domain,
        "endpoint_id": final_key.get("endpoint_id") if isinstance(final_key, Mapping) else None,
        "connectome_id": endpoint.get("connectome_id") if isinstance(endpoint, Mapping) else None,
        "selected_tau": final_key.get("selected_tau") if isinstance(final_key, Mapping) else None,
        "selected_coverage": (
            final_key.get("selected_coverage") if isinstance(final_key, Mapping) else None
        ),
        "final_branch": final_key.get("final_branch") if isinstance(final_key, Mapping) else None,
        "final_selection_task": task_path.stem,
        "input_path": str(target / input_path.name),
        "details": details,
    }
    _write_json(stage / "manifest.json", manifest)
    os.replace(stage, target)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--model-family", required=True, choices=sorted(_MODEL_FAMILIES))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = prepare_scene_example_input(
        args.run_root,
        args.output_root,
        scale_id=args.scale_id,
        model_family=args.model_family,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "SceneExampleInputError",
    "prepare_scene_example_input",
]
