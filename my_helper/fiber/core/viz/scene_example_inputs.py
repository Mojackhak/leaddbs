"""Prepare interactive MATLAB scene inputs from canonical publications."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import savemat

from .published_artifacts import (
    PublicationCatalog,
    PublishedArtifact,
    PublishedArtifactError,
)


SCHEMA_VERSION = "dual_frequency_scene_example_input_v2"
_PUBLICATION_ALIAS = "main"
_MODEL_FAMILIES = {
    "reference_voxel": "voxel",
    "addon_voxel": "voxel",
    "reference_fiber": "fiber",
    "addon_fiber": "fiber",
}
_FORBIDDEN_SOURCE_PARTS = frozenset({".runs", "tasks", "work", "runtime_work"})


class SceneExampleInputError(RuntimeError):
    """Raised when a published final model cannot form a faithful scene input."""


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


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


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


def _catalog(publication_root: Path) -> PublicationCatalog:
    try:
        return PublicationCatalog.from_config(
            {
                _PUBLICATION_ALIAS: {
                    "root": str(publication_root),
                    "manifest": "model_manifest.json",
                }
            },
            config_base=publication_root.parent,
        )
    except PublishedArtifactError as exc:
        raise SceneExampleInputError(str(exc)) from exc


def _final_relative_path(scale_id: str, model_family: str) -> str:
    family = "reference" if model_family.startswith("reference_") else "addon"
    return f"{scale_id}/{family}/final_model.json"


def _published_final(
    catalog: PublicationCatalog, scale_id: str, model_family: str
) -> tuple[PublishedArtifact, dict[str, Any]]:
    try:
        artifact = catalog.resolve_relative(
            _PUBLICATION_ALIAS, _final_relative_path(scale_id, model_family)
        )
    except PublishedArtifactError as exc:
        raise SceneExampleInputError(str(exc)) from exc
    final_model = _read_json(artifact.path)
    final_role = str(final_model.get("final_role", ""))
    if final_role == "no_final_model" or not final_role:
        raise SceneExampleInputError(
            f"{scale_id} {model_family} does not have a realized published final model"
        )
    if final_model.get("scale_id") != scale_id:
        raise SceneExampleInputError("published final-model scale does not match the request")
    recorded_family = str(final_model.get("model_family", ""))
    allowed = {
        model_family,
        "reference" if model_family.startswith("reference_") else "addon",
    }
    if recorded_family and recorded_family not in allowed:
        raise SceneExampleInputError("published final-model family does not match the request")
    return artifact, final_model


def _resolver_directory(final_model: Mapping[str, Any]) -> Path:
    value = final_model.get("source_record_relative_path")
    if not value:
        value = final_model.get("resolver_relative_path")
    if not value:
        raise SceneExampleInputError("published final model lacks a resolver reference")
    path = Path(str(value))
    return path.parent if path.suffix else path


def _resolver_artifact(
    catalog: PublicationCatalog,
    final_model: Mapping[str, Any],
    filename: str,
    *,
    required: bool = True,
) -> PublishedArtifact | None:
    relative = (_resolver_directory(final_model) / filename).as_posix()
    try:
        return catalog.resolve_relative(_PUBLICATION_ALIAS, relative)
    except PublishedArtifactError as exc:
        if not required and relative not in catalog.indexed_paths(_PUBLICATION_ALIAS):
            return None
        raise SceneExampleInputError(str(exc)) from exc


def _study_sources(
    catalog: PublicationCatalog, publication_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = catalog.manifest(_PUBLICATION_ALIAS)
    raw_path = manifest.get("study_base_path")
    expected_sha = str(manifest.get("study_base_sha256", "")).lower()
    if not raw_path or len(expected_sha) != 64:
        raise SceneExampleInputError(
            "published model manifest lacks study-base path or SHA-256"
        )
    path = Path(str(raw_path)).expanduser().resolve()
    if any(part in _FORBIDDEN_SOURCE_PARTS for part in path.parts):
        raise SceneExampleInputError(
            "published study base cannot resolve through a run store"
        )
    if not path.is_file() or _sha256_file(path) != expected_sha:
        raise SceneExampleInputError("published study-base identity cannot be verified")
    payload = _read_json(path)
    study = payload.get("study")
    if not isinstance(study, Mapping):
        raise SceneExampleInputError("published study base lacks study")
    sources = study.get("spot_model_sources")
    if not isinstance(sources, Mapping):
        raise SceneExampleInputError("published study base lacks spot_model_sources")
    return dict(sources), {
        "path": str(path),
        "sha256": expected_sha,
        "publication_root": str(publication_root),
    }


def _array(path: Path, *, dtype: np.dtype[Any] | None = None) -> np.ndarray:
    value = np.load(path, allow_pickle=False)
    if dtype is not None and value.dtype != dtype:
        raise SceneExampleInputError(
            f"unexpected dtype for {path}: {value.dtype}; expected {dtype}"
        )
    return np.asarray(value)


def _connectome_path(sources: Mapping[str, Any], connectome_id: str) -> Path:
    entries = sources.get("connectomes")
    if not isinstance(entries, list):
        raise SceneExampleInputError("published study sources lack connectomes")
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping) and item.get("connectome_id") == connectome_id
    ]
    if len(matches) != 1:
        raise SceneExampleInputError(
            f"expected one published study connectome {connectome_id}; found {len(matches)}"
        )
    streamlines = matches[0].get("streamlines")
    if not isinstance(streamlines, Mapping) or not streamlines.get("path"):
        raise SceneExampleInputError(f"connectome {connectome_id} lacks a geometry path")
    path = Path(str(streamlines["path"])).expanduser().resolve()
    if any(part in _FORBIDDEN_SOURCE_PARTS for part in path.parts):
        raise SceneExampleInputError(
            f"connectome {connectome_id} geometry cannot resolve through a run store"
        )
    if not path.is_file():
        raise SceneExampleInputError(f"connectome geometry is missing: {path}")
    declared_sha = str(streamlines.get("sha256", "")).lower()
    if declared_sha and (len(declared_sha) != 64 or _sha256_file(path) != declared_sha):
        raise SceneExampleInputError(f"connectome geometry SHA-256 mismatch: {path}")
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


def _fiber_sources(
    catalog: PublicationCatalog, final_model: Mapping[str, Any]
) -> dict[str, PublishedArtifact | None]:
    return {
        "valid": _resolver_artifact(catalog, final_model, "valid_fiber_ids.npy"),
        "weights": _resolver_artifact(catalog, final_model, "full_weights.npy"),
        "sweet": _resolver_artifact(
            catalog, final_model, "selected_sweet_fiber_ids.npy", required=False
        ),
        "sour": _resolver_artifact(
            catalog, final_model, "selected_sour_fiber_ids.npy", required=False
        ),
    }


def _prepare_fiber(
    stage: Path,
    final_model: Mapping[str, Any],
    sources: Mapping[str, Any],
    artifacts: Mapping[str, PublishedArtifact | None],
    scale_id: str,
    model_family: str,
) -> tuple[Path, dict[str, Any]]:
    valid_ref = artifacts["valid"]
    weights_ref = artifacts["weights"]
    assert valid_ref is not None and weights_ref is not None
    valid_ids = _array(valid_ref.path, dtype=np.dtype(np.int64))
    weights = np.asarray(_array(weights_ref.path), dtype=np.float64)
    if valid_ids.ndim != 1 or weights.ndim != 1 or valid_ids.shape != weights.shape:
        raise SceneExampleInputError("published fiber IDs and weights must be matching vectors")
    if valid_ids.size == 0 or np.any(np.diff(valid_ids) <= 0):
        raise SceneExampleInputError("published fiber IDs must be ordered and unique")

    def selected(reference: PublishedArtifact | None) -> np.ndarray:
        if reference is None:
            return np.empty(0, dtype=np.int64)
        return _array(reference.path, dtype=np.dtype(np.int64))

    sweet_ids = selected(artifacts["sweet"])
    sour_ids = selected(artifacts["sour"])
    display_ids = np.unique(np.concatenate((sweet_ids, sour_ids))).astype(np.int64)
    if display_ids.size == 0:
        raise SceneExampleInputError("published final model has no selected display fibers")
    if np.intersect1d(sweet_ids, sour_ids).size:
        raise SceneExampleInputError("published sweet and sour fiber IDs overlap")
    positions = np.searchsorted(valid_ids, display_ids)
    if np.any(positions >= valid_ids.size) or not np.array_equal(valid_ids[positions], display_ids):
        raise SceneExampleInputError("published display fiber is outside the valid final axis")
    scores = weights[positions]
    if not np.all(np.isfinite(scores)) or not np.any(scores != 0.0):
        raise SceneExampleInputError("published display fiber weights are invalid")
    if sweet_ids.size and np.any(scores[np.searchsorted(display_ids, sweet_ids)] <= 0.0):
        raise SceneExampleInputError("published sweet fibers must have positive weights")
    if sour_ids.size and np.any(scores[np.searchsorted(display_ids, sour_ids)] >= 0.0):
        raise SceneExampleInputError("published sour fibers must have negative weights")

    connectome_id = str(final_model.get("formal_connectome_id", ""))
    if not connectome_id:
        raise SceneExampleInputError("published fiber final lacks formal_connectome_id")
    connectome = _connectome_path(sources, connectome_id)
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
        "connectome_id": connectome_id,
        "connectome_path": str(connectome),
        "display_fiber_count": int(display_ids.size),
        "sweet_fiber_count": int(sweet_ids.size),
        "sour_fiber_count": int(sour_ids.size),
        "point_count": int(fibers.shape[0]),
        "score_limit": float(np.max(np.abs(scores))),
    }


def prepare_scene_example_input(
    publication_root: str | Path,
    output_root: str | Path,
    *,
    scale_id: str,
    model_family: str,
) -> dict[str, Any]:
    """Prepare one request-addressed scene input from a canonical publication."""

    publication = Path(publication_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    if model_family not in _MODEL_FAMILIES:
        raise SceneExampleInputError(f"unsupported model_family: {model_family}")
    catalog = _catalog(publication)
    final_artifact, final_model = _published_final(catalog, scale_id, model_family)
    sources, study_identity = _study_sources(catalog, publication)
    domain = _MODEL_FAMILIES[model_family]
    if domain == "voxel":
        benefit_map = _resolver_artifact(catalog, final_model, "benefit_map.nii.gz")
        assert benefit_map is not None
        source_artifacts = [final_artifact, benefit_map]
        fiber_artifacts: dict[str, PublishedArtifact | None] = {}
    else:
        fiber_artifacts = _fiber_sources(catalog, final_model)
        source_artifacts = [final_artifact] + [
            artifact for artifact in fiber_artifacts.values() if artifact is not None
        ]
    request = {
        "schema_version": SCHEMA_VERSION,
        "publication_root": str(publication),
        "publication_manifest": catalog.publication_records()[0],
        "scale_id": scale_id,
        "model_family": model_family,
        "source_artifacts": [artifact.as_manifest_record() for artifact in source_artifacts],
        "study_base": study_identity,
    }
    request_hash = _canonical_hash(request)
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
    if domain == "voxel":
        input_path = benefit_map.path
        details = {
            "published_benefit_map": benefit_map.as_manifest_record(),
            "finite_voxel_count": None,
        }
    else:
        staged_input, details = _prepare_fiber(
            stage, final_model, sources, fiber_artifacts, scale_id, model_family
        )
        input_path = target / staged_input.name
    selected_tau = final_model.get(
        "selected_tau_v_per_m", final_model.get("selected_tau")
    )
    selected_coverage = final_model.get(
        "selected_coverage_subjects_min", final_model.get("selected_coverage")
    )
    final_branch = final_model.get(
        "realized_final_branch", final_model.get("final_branch")
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "request_hash": request_hash,
        "request": request,
        "scale_id": scale_id,
        "model_family": model_family,
        "domain": domain,
        "endpoint_id": f"{scale_id}:{model_family}",
        "connectome_id": final_model.get("formal_connectome_id"),
        "selected_tau": selected_tau,
        "selected_coverage": selected_coverage,
        "final_branch": final_branch,
        "published_final_model": final_artifact.as_manifest_record(),
        "input_path": str(input_path),
        "details": details,
    }
    _write_json(stage / "manifest.json", manifest)
    os.replace(stage, target)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--model-family", required=True, choices=sorted(_MODEL_FAMILIES))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = prepare_scene_example_input(
        args.publication_root,
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
