"""Publish one normative-fiber two-dimensional spatial checkpoint."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
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
from scipy import sparse

from my_helper.fiber.core.seed_target_connectivity.connectome import open_connectome

from .fiber_composition import (
    COMPOSITION_ALGORITHM,
    COMPOSITION_VERSION,
    SeedPatternCounts,
    TargetConditionedProjection,
    WholeConnectomeComposition,
    apply_target_scores_to_composition,
    build_whole_connectome_composition,
    compute_selected_target_scores,
    compute_target_scores,
    target_membership_from_bits,
)
from .fiber_projection import (
    PROJECTION_ALGORITHM,
    PROJECTION_VERSION,
    SelectedDirectProjection,
    compute_selected_direct_projection,
    load_binary_projection_mask,
    validate_exact_mask_geometry,
)
from .artifacts import create_display_nifti
from .plugin.default import get_fiber_section_cfg, get_target_score_raincloud_cfg
from .published_artifacts import PublicationCatalog, PublishedArtifact
from .spatial_result_config import load_spatial_result_config
from .target_score_raincloud import (
    build_target_fiber_distribution_rows,
    plot_target_score_dual_raincloud,
    shared_asymmetric_target_limits,
)
from .target_inference import TARGET_INFERENCE_SCHEMA, run_target_inference
from .voxel_sections import plot_signed_voxel_sections


SCHEMA_VERSION = "dual_frequency_fiber_section_postprocess_v12"

_TARGET_INFERENCE_BASIS = {
    "inference_valid_fiber_exposure": "valid_fiber_exposure.npy",
    "inference_ranked_valid_fiber_exposure": (
        "ranked_valid_fiber_exposure.npy"
    ),
    "inference_valid_fiber_ids": "valid_fiber_ids.npy",
    "inference_outcome": "outcome.npy",
    "inference_ranked_outcome": "ranked_outcome.npy",
    "inference_ranked_nuisance_design": "ranked_nuisance_design.npy",
    "inference_subject_order": "subject_order.csv",
    "inference_exchangeability_blocks": "exchangeability_blocks.csv",
    "inference_input": "inference_input.json",
}


@dataclass(frozen=True)
class _RoleSpec:
    role: str


@dataclass(frozen=True)
class _PreparedRole:
    artifacts: Mapping[str, PublishedArtifact]
    final_model: Mapping[str, Any]
    source_records: Mapping[str, Mapping[str, Any]]
    coverage_ids: np.ndarray
    coverage_scores: np.ndarray
    coverage_target_membership: np.ndarray
    selected_ids: np.ndarray
    selected_scores: np.ndarray
    selected_is_sweet: np.ndarray
    target_membership: np.ndarray
    coverage_target_scores: np.ndarray
    selected_target_scores: np.ndarray
    selected_projection_hash: str
    target_request_hash: str


_ROLE_SPECS = (_RoleSpec("reference"), _RoleSpec("addon"))


@dataclass(frozen=True)
class FiberSectionContext:
    """Shared validated resources for one formal fiber component process."""

    config: Mapping[str, Any]
    display_map: Mapping[str, Any]
    outline_isovalue: float
    config_record: Mapping[str, Any]
    background_path: Path
    background_record: Mapping[str, Any]
    formal_connectome_id: str
    connectome: Any
    connectome_record: Mapping[str, Any]
    targets: tuple[Any, ...]
    target_records: tuple[Mapping[str, Any], ...]
    seeds: Mapping[str, Any]
    seed_records: Mapping[str, Mapping[str, Any]]
    outline_paths: Mapping[str, Path | None]
    outline_records: Mapping[str, Mapping[str, Any] | None]


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
    inference_root = resolver_dir / "target_inference"
    indexed = set(catalog.indexed_paths("normative_fiber_main"))
    inference_paths = {
        key: (inference_root / name).as_posix()
        for key, name in _TARGET_INFERENCE_BASIS.items()
    }
    present = {
        key: relative
        for key, relative in inference_paths.items()
        if relative in indexed
    }
    if present and len(present) != len(inference_paths):
        missing = sorted(set(inference_paths) - set(present))
        raise ValueError(
            "normative-fiber target-inference basis is only partially published: "
            f"{missing}"
        )
    for key, relative in present.items():
        artifacts[key] = catalog.resolve_relative("normative_fiber_main", relative)
    return artifacts, final_model


def _fiber_data(
    artifacts: Mapping[str, PublishedArtifact],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
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
    return (
        valid_ids,
        full_weights,
        selected_ids[order],
        selected_scores[order],
        selected_is_sweet[order],
    )


def _projection_cache_payload(
    result: SelectedDirectProjection,
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
        key: np.asarray(value) for key, value in asdict(result).items()
    }
    payload.update(
        {"streamline_indptr": streamline_indptr, "streamline_points": points}
    )
    return payload


def _write_projection_cache(
    path: Path,
    result: SelectedDirectProjection,
    streamlines: Sequence[np.ndarray],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **_projection_cache_payload(result, streamlines))
    temporary.replace(path)


def _load_projection_cache(
    path: Path,
) -> tuple[SelectedDirectProjection, tuple[np.ndarray, ...]]:
    with np.load(path, allow_pickle=False) as payload:
        result = SelectedDirectProjection(
            fiber_ids=np.asarray(payload["fiber_ids"], dtype=np.int64),
            scores=np.asarray(payload["scores"], dtype=np.float64),
            is_sweet=np.asarray(payload["is_sweet"], dtype=np.bool_),
            voxel_indptr=np.asarray(payload["voxel_indptr"], dtype=np.int64),
            voxel_indices=np.asarray(payload["voxel_indices"], dtype=np.int64),
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
        )
        offsets = np.asarray(payload["streamline_indptr"], dtype=np.int64)
        points = np.asarray(payload["streamline_points"], dtype=np.float32)
    streamlines = tuple(
        points[int(offsets[index]) : int(offsets[index + 1])]
        for index in range(offsets.size - 1)
    )
    return result, streamlines


def _physical_cache_payload(
    result: WholeConnectomeComposition,
) -> dict[str, np.ndarray]:
    payload: dict[str, np.ndarray] = {
        "target_ids": np.asarray(result.target_ids, dtype=np.str_),
        "n_all_fibers": np.asarray(result.n_all_fibers, dtype=np.int64),
        "fiber_target_bits": np.asarray(result.fiber_target_bits, dtype=np.uint32),
        "fiber_chunk_size": np.asarray(result.fiber_chunk_size, dtype=np.int64),
        "ordered_fiber_id_hash": np.asarray(
            result.ordered_fiber_id_hash, dtype=np.str_
        ),
        "role_names": np.asarray([value.role for value in result.roles], dtype=np.str_),
    }
    for index, role in enumerate(result.roles):
        payload[f"seed_voxel_indices_{index}"] = role.seed_voxel_indices
        payload[f"voxel_pattern_indptr_{index}"] = role.voxel_pattern_indptr
        payload[f"pattern_bits_{index}"] = role.pattern_bits
        payload[f"pattern_counts_{index}"] = role.pattern_counts
    return payload


def _write_physical_cache(
    path: Path,
    result: WholeConnectomeComposition,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **_physical_cache_payload(result))
    temporary.replace(path)


def _load_physical_cache(path: Path) -> WholeConnectomeComposition:
    with np.load(path, allow_pickle=False) as payload:
        role_names = tuple(str(value) for value in payload["role_names"])
        roles = tuple(
            SeedPatternCounts(
                role=role,
                seed_voxel_indices=np.asarray(
                    payload[f"seed_voxel_indices_{index}"], dtype=np.int64
                ),
                voxel_pattern_indptr=np.asarray(
                    payload[f"voxel_pattern_indptr_{index}"], dtype=np.int64
                ),
                pattern_bits=np.asarray(
                    payload[f"pattern_bits_{index}"], dtype=np.uint32
                ),
                pattern_counts=np.asarray(
                    payload[f"pattern_counts_{index}"], dtype=np.int64
                ),
            )
            for index, role in enumerate(role_names)
        )
        result = WholeConnectomeComposition(
            target_ids=tuple(str(value) for value in payload["target_ids"]),
            n_all_fibers=int(payload["n_all_fibers"]),
            fiber_target_bits=np.asarray(
                payload["fiber_target_bits"], dtype=np.uint32
            ),
            roles=roles,
            fiber_chunk_size=int(payload["fiber_chunk_size"]),
            ordered_fiber_id_hash=str(payload["ordered_fiber_id_hash"]),
        )
    if result.fiber_target_bits.shape != (result.n_all_fibers,):
        raise ValueError("physical cache fiber-target bit axis is invalid")
    for role in result.roles:
        if role.voxel_pattern_indptr.shape != (role.seed_voxel_indices.size + 1,):
            raise ValueError(f"physical cache role {role.role!r} has invalid CSR")
        if role.voxel_pattern_indptr[-1] != role.pattern_bits.size:
            raise ValueError(f"physical cache role {role.role!r} CSR is incomplete")
        if role.pattern_bits.shape != role.pattern_counts.shape:
            raise ValueError(f"physical cache role {role.role!r} entries are misaligned")
    return result


def _sparse_nifti_image(
    *,
    seed_path: Path,
    voxel_indices: np.ndarray,
    values: np.ndarray,
    description: str,
) -> nib.Nifti1Image:
    """Restore one sparse score vector in memory for display-map creation."""

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
    return nib.Nifti1Image(
        volume.reshape(seed_image.shape, order="C"),
        np.asarray(seed_image.affine, dtype=np.float64),
        header,
    )


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


def _write_sparse_membership_atomic(path: Path, values: np.ndarray) -> None:
    membership = np.asarray(values, dtype=np.bool_)
    if membership.ndim != 2:
        raise ValueError("target membership must be a two-dimensional array")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".npz", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        sparse.save_npz(
            temporary,
            sparse.csr_matrix(membership, dtype=np.bool_),
            compressed=True,
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_ordered_subject_csv(
    artifact: PublishedArtifact,
    *,
    value_field: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    indices: list[str] = []
    subject_ids: list[str] = []
    values: list[str] = []
    with artifact.path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"subject_index", "subject_id", value_field}
        if not required.issubset(set(reader.fieldnames or ())):
            raise ValueError(
                f"target-inference CSV lacks required fields: {artifact.relative_path}"
            )
        for row in reader:
            indices.append(str(row["subject_index"]))
            subject_ids.append(str(row["subject_id"]))
            values.append(str(row[value_field]))
    expected = tuple(str(index) for index in range(len(indices)))
    if tuple(indices) != expected or any(not value for value in subject_ids):
        raise ValueError(
            f"target-inference subject order is invalid: {artifact.relative_path}"
        )
    return tuple(subject_ids), tuple(values)


def _run_role_target_inference(
    *,
    root: Path,
    target_root: Path,
    scale_id: str,
    role: str,
    artifacts: Mapping[str, PublishedArtifact],
    coverage_ids: np.ndarray,
    coverage_scores: np.ndarray,
    coverage_target_membership: np.ndarray,
    coverage_target_scores: np.ndarray,
    target_ids: Sequence[str],
    target_records: Sequence[Mapping[str, Any]],
    physical_cache_record: Mapping[str, Any],
    replicate_count: int,
    seed: int,
) -> tuple[
    dict[str, Any],
    dict[str, float | None],
    list[str],
]:
    """Publish target membership and run conditional patient-level inference."""

    if "inference_input" not in artifacts:
        return (
            {
                "status": "not_available_parent_publication_missing_basis",
                "schema_version": TARGET_INFERENCE_SCHEMA,
            },
            {},
            [],
        )
    parent_input = _read_json(artifacts["inference_input"].path)
    if parent_input.get("schema_version") != "conditional_signed_target_inference_input_v1":
        raise ValueError("unsupported parent target-inference input schema")
    if parent_input.get("scale_id") != scale_id:
        raise ValueError("parent target-inference scale does not match postprocess")
    if parent_input.get("model_role") != role:
        raise ValueError("parent target-inference model role does not match postprocess")
    benefit_direction = str(parent_input.get("benefit_direction", ""))
    if benefit_direction not in {"lower", "higher"}:
        raise ValueError("parent target-inference benefit direction is invalid")

    parent_hashes = parent_input.get("artifact_sha256")
    if not isinstance(parent_hashes, Mapping):
        raise ValueError("parent target-inference input lacks artifact hashes")
    for key, name in _TARGET_INFERENCE_BASIS.items():
        if key == "inference_input":
            continue
        expected = str(parent_hashes.get(name, ""))
        if expected != artifacts[key].sha256:
            raise ValueError(
                f"parent target-inference manifest hash mismatch for {name}"
            )

    inference_ids = np.asarray(
        np.load(artifacts["inference_valid_fiber_ids"].path, allow_pickle=False),
        dtype=np.int64,
    )
    if not np.array_equal(inference_ids, coverage_ids):
        raise ValueError(
            "parent target-inference fiber axis does not match all-coverage fibers"
        )
    ranked_exposure = np.asarray(
        np.load(
            artifacts["inference_ranked_valid_fiber_exposure"].path,
            mmap_mode="r",
            allow_pickle=False,
        ),
        dtype=np.float64,
    )
    ranked_outcome = np.asarray(
        np.load(artifacts["inference_ranked_outcome"].path, allow_pickle=False),
        dtype=np.float64,
    )
    ranked_design = np.asarray(
        np.load(
            artifacts["inference_ranked_nuisance_design"].path,
            allow_pickle=False,
        ),
        dtype=np.float64,
    )
    raw_exposure = np.load(
        artifacts["inference_valid_fiber_exposure"].path,
        mmap_mode="r",
        allow_pickle=False,
    )
    raw_outcome = np.load(
        artifacts["inference_outcome"].path,
        mmap_mode="r",
        allow_pickle=False,
    )
    expected_shape = (ranked_outcome.size, coverage_ids.size)
    if ranked_exposure.shape != expected_shape or raw_exposure.shape != expected_shape:
        raise ValueError("parent target-inference exposure shape is invalid")
    if raw_outcome.shape != ranked_outcome.shape:
        raise ValueError("parent target-inference outcome shape is invalid")
    if ranked_design.ndim != 2 or ranked_design.shape[0] != ranked_outcome.size:
        raise ValueError("parent target-inference nuisance design shape is invalid")

    subject_ids, order_values = _read_ordered_subject_csv(
        artifacts["inference_subject_order"],
        value_field="subject_id",
    )
    if subject_ids != order_values:
        raise ValueError("parent target-inference subject-order CSV is inconsistent")
    block_subject_ids, blocks = _read_ordered_subject_csv(
        artifacts["inference_exchangeability_blocks"],
        value_field="exchangeability_block",
    )
    if subject_ids != block_subject_ids or len(subject_ids) != ranked_outcome.size:
        raise ValueError("parent target-inference patient queues do not match")

    input_root = target_root / "inference" / "input"
    membership_path = input_root / "valid_fiber_target_membership.npz"
    target_ids_path = input_root / "target_ids.csv"
    local_input_path = input_root / "inference_input.json"
    _write_sparse_membership_atomic(
        membership_path,
        coverage_target_membership,
    )
    _write_csv_atomic(
        target_ids_path,
        ("target_index", "target_id"),
        [
            {"target_index": index, "target_id": target_id}
            for index, target_id in enumerate(target_ids)
        ],
    )
    local_input = {
        "schema_version": "conditional_signed_target_inference_postprocess_input_v1",
        "inference_schema_version": TARGET_INFERENCE_SCHEMA,
        "scale_id": scale_id,
        "model_role": role,
        "selection_scope": "conditional_on_published_final_model",
        "fiber_scope": "final_resolver_valid_fiber_axis",
        "target_membership": "independent_binary_segment_intersection",
        "multi_target_membership": "repeated_without_fractional_weighting",
        "parent_inference_input": artifacts[
            "inference_input"
        ].as_manifest_record(),
        "valid_fiber_target_membership": _file_record(
            membership_path,
            "target_inference_valid_fiber_target_membership",
        ),
        "target_ids": _file_record(target_ids_path, "target_inference_target_ids"),
        "target_records": list(target_records),
        "physical_cache": dict(physical_cache_record),
        "formal_resampling": {
            "permutation_resamples": replicate_count,
            "seed": seed,
            "configuration_source": "resolved_normative_fiber_model.yaml",
        },
    }
    _write_json_atomic(local_input_path, local_input)
    inference_root = target_root / "inference"
    inference_manifest = run_target_inference(
        output_root=inference_root,
        target_ids=target_ids,
        ranked_outcome=ranked_outcome,
        ranked_exposure=ranked_exposure,
        ranked_nuisance_design=ranked_design,
        target_membership=coverage_target_membership,
        benefit_direction=benefit_direction,
        exchangeability_blocks=blocks,
        replicate_count=replicate_count,
        seed=seed,
        input_identity={
            "parent_inference_input_sha256": artifacts["inference_input"].sha256,
            "postprocess_inference_input_sha256": _sha256_file(local_input_path),
            "membership_sha256": _sha256_file(membership_path),
            "target_ids_sha256": _sha256_file(target_ids_path),
        },
        expected_fiber_weights=coverage_scores,
        expected_target_statistics=coverage_target_scores,
    )

    summary_path = inference_root / "target_group_permutation_summary.csv"
    targetwise_by_target: dict[str, float | None] = {}
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = str(row.get("p_net_targetwise", "")).strip()
            target_id = str(row["target_id"])
            targetwise_by_target[target_id] = (
                None if not raw else float(raw)
            )
    if set(targetwise_by_target) != set(str(value) for value in target_ids):
        raise ValueError("target-inference summary target axis is incomplete")

    relative_outputs = [
        path.relative_to(root).as_posix()
        for path in sorted(inference_root.rglob("*"))
        if path.is_file()
    ]
    return (
        dict(inference_manifest),
        targetwise_by_target,
        relative_outputs,
    )


def _target_score_rows(
    *,
    target_ids: Sequence[str],
    target_membership: np.ndarray,
    target_scores: np.ndarray,
    target_score_fiber_scope: str,
    selected_is_sweet: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, target_id in enumerate(target_ids):
        hits = target_membership[:, index]
        score = target_scores[index]
        rows.append(
            {
                "target_id": target_id,
                "target_score": "" if not np.isfinite(score) else float(score),
                "fiber_count": int(np.sum(hits)),
                "sweet_fiber_count": (
                    ""
                    if selected_is_sweet is None
                    else int(np.sum(hits & selected_is_sweet))
                ),
                "sour_fiber_count": (
                    ""
                    if selected_is_sweet is None
                    else int(np.sum(hits & ~selected_is_sweet))
                ),
                "quantitative_mass": float(np.sum(hits, dtype=np.float64)),
                "streamline_weight_source": "uniform_one",
                "target_score_fiber_scope": target_score_fiber_scope,
            }
        )
    return rows


def _membership_rows(
    *,
    projection: SelectedDirectProjection,
    target_ids: Sequence[str],
    target_membership: np.ndarray,
    target_scores: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hit_counts = np.sum(target_membership, axis=1, dtype=np.int64)
    for fiber_index, fiber_id in enumerate(projection.fiber_ids):
        for target_index, target_id in enumerate(target_ids):
            rows.append(
                {
                    "fiber_id": int(fiber_id),
                    "fiber_class": (
                        "sweet" if projection.is_sweet[fiber_index] else "sour"
                    ),
                    "model_score": float(projection.scores[fiber_index]),
                    "target_id": target_id,
                    "binary_hit": int(target_membership[fiber_index, target_index]),
                    "target_hit_count": int(hit_counts[fiber_index]),
                    "target_score_finite": int(np.isfinite(target_scores[target_index])),
                    "streamline_weight": 1.0,
                }
            )
    return rows


def _target_score_qc(
    *,
    fiber_ids: np.ndarray,
    target_ids: Sequence[str],
    target_membership: np.ndarray,
    target_scores: np.ndarray,
    target_score_fiber_scope: str,
) -> dict[str, Any]:
    hit_counts = np.sum(target_membership, axis=1, dtype=np.int64)
    overlap = target_membership.astype(np.int64).T @ target_membership.astype(
        np.int64
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "target_ids": list(target_ids),
        "scoring_fiber_count": int(np.asarray(fiber_ids).size),
        "no_target_fiber_count": int(np.sum(hit_counts == 0)),
        "single_target_fiber_count": int(np.sum(hit_counts == 1)),
        "multiple_target_fiber_count": int(np.sum(hit_counts > 1)),
        "maximum_target_hits_per_fiber": int(np.max(hit_counts, initial=0)),
        "target_overlap_counts": overlap.tolist(),
        "target_hit_counts": [
            int(value) for value in np.sum(target_membership, axis=0)
        ],
        "finite_target_score_count": int(np.sum(np.isfinite(target_scores))),
        "target_scores": [
            None if not np.isfinite(value) else float(value) for value in target_scores
        ],
        "streamline_weight_source": "uniform_one",
        "target_score_fiber_scope": target_score_fiber_scope,
        "target_score_membership": "independent_binary",
    }


def _composition_qc(
    *,
    physical: WholeConnectomeComposition,
    composition: SeedPatternCounts,
    projection: TargetConditionedProjection,
    target_scores: np.ndarray,
    target_score_fiber_scope: str,
) -> dict[str, Any]:
    total = projection.all_streamline_support_count
    scored = projection.target_scored_streamline_count
    unscored = projection.target_unscored_streamline_count
    conservation_error = float(np.max(np.abs(total - scored - unscored), initial=0.0))
    finite_scores = target_scores[np.isfinite(target_scores)]
    finite_voxel_scores = projection.target_conditioned_score[
        np.isfinite(projection.target_conditioned_score)
    ]
    bound_violation = 0.0
    if finite_scores.size and finite_voxel_scores.size:
        lower = float(np.min(finite_scores))
        upper = float(np.max(finite_scores))
        bound_violation = max(
            0.0,
            lower - float(np.min(finite_voxel_scores)),
            float(np.max(finite_voxel_scores)) - upper,
        )
    assignment = projection.target_assignment_fraction[
        np.isfinite(projection.target_assignment_fraction)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": COMPOSITION_ALGORITHM,
        "algorithm_version": COMPOSITION_VERSION,
        "target_score_fiber_scope": target_score_fiber_scope,
        "voxel_composition_fiber_scope": "formal_connectome_all",
        "n_all_fibers": physical.n_all_fibers,
        "seed_voxel_count": int(composition.seed_voxel_indices.size),
        "seed_voxel_count_with_any_streamline": int(np.sum(total > 0.0)),
        "seed_voxel_count_with_scored_streamline": int(np.sum(scored > 0.0)),
        "all_streamline_incidence_sum": float(np.sum(total)),
        "scored_streamline_incidence_sum": float(np.sum(scored)),
        "unscored_streamline_incidence_sum": float(np.sum(unscored)),
        "support_conservation_max_abs_error": conservation_error,
        "target_score_bound_max_violation": float(bound_violation),
        "finite_target_score_count": projection.finite_target_count,
        "scored_pattern_count": projection.scored_pattern_count,
        "unscored_pattern_count": projection.unscored_pattern_count,
        "physical_pattern_entry_count": int(composition.pattern_bits.size),
        "distinct_physical_pattern_count": int(np.unique(composition.pattern_bits).size),
        "assignment_fraction_min": (
            None if assignment.size == 0 else float(np.min(assignment))
        ),
        "assignment_fraction_max": (
            None if assignment.size == 0 else float(np.max(assignment))
        ),
        "streamline_weight_source": "uniform_one",
        "streamline_target_score": "equal_mean_over_finite_target_scores",
        "no_scored_target_policy": "exclude_and_report",
    }


def _projection_qc(result: SelectedDirectProjection) -> dict[str, Any]:
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
        "direct_streamline_scope": "selected_sweet_sour_complete_path",
    }


def _completion_marker(result_path: Path) -> Path:
    return result_path.parent / "completion" / "fiber_2d" / "complete.json"


def _result_reusable(result_path: Path) -> bool:
    return result_path.is_file() and _completion_marker(result_path).is_file()


def _render_figure(
    *,
    heat_path: Path,
    background_path: Path,
    seed_path: Path,
    outline_path: Path | None,
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
        outline_image=outline_path,
        geometry_image=seed_path,
        geometry_threshold=0.0,
        style_config=style,
        output_paths=output_paths,
    )
    render_metadata = getattr(figure, "_mh_viz_voxel_section_metadata")
    plt.close(figure)
    relative_outputs = [path.relative_to(root).as_posix() for path in output_paths]
    result_path = figure_stem.parent / "result.json"
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


def _render_target_score_figure(
    *,
    target_ids: Sequence[str],
    target_display_labels: Sequence[str],
    target_order_policy: str,
    target_scores: np.ndarray,
    coverage_fiber_ids: np.ndarray,
    coverage_scores: np.ndarray,
    selected_fiber_ids: np.ndarray,
    selected_is_sweet: np.ndarray,
    coverage_target_membership: np.ndarray,
    scale_display_name: str,
    shared_y_limits: Sequence[float],
    targetwise_p_values: Mapping[str, float | None] | None,
    figure_stem: Path,
    style: Mapping[str, Any],
    figure_payload: Mapping[str, Any],
    root: Path,
) -> tuple[dict[str, Any], list[str]]:
    output_paths = [
        figure_stem.with_suffix(f".{str(extension).lower().lstrip('.')}")
        for extension in style["formats"]
    ]
    figure = plot_target_score_dual_raincloud(
        target_ids=target_ids,
        target_display_labels=target_display_labels,
        target_order_policy=target_order_policy,
        target_scores=target_scores,
        coverage_fiber_ids=coverage_fiber_ids,
        coverage_scores=coverage_scores,
        selected_fiber_ids=selected_fiber_ids,
        selected_is_sweet=selected_is_sweet,
        coverage_target_membership=coverage_target_membership,
        scale_display_name=scale_display_name,
        shared_y_limits=shared_y_limits,
        targetwise_p_values=targetwise_p_values,
        style_config=style,
        output_paths=output_paths,
    )
    render_metadata = getattr(figure, "_mh_viz_target_score_metadata")
    plt.close(figure)
    relative_outputs = [path.relative_to(root).as_posix() for path in output_paths]
    output_records = [
        _file_record(path, "target_score_dual_raincloud") for path in output_paths
    ]
    result_path = figure_stem.with_suffix(".json")
    payload = {
        **dict(figure_payload),
        "status": "complete",
        "style": dict(style),
        "render_metadata": render_metadata,
        "output_records": output_records,
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


def _write_readme(root: Path, scale_id: str, scale_display_name: str) -> None:
    text = f"""# {scale_display_name} Normative-Fiber Spatial Postprocess

This checkpoint contains only the `{scale_id}` reference and add-on normative-
fiber spatial display derivatives and their conditional target inference. It
does not contain another clinical scale or a direct-voxel model.

Browse the role-local results under:

```text
scales/{scale_id}/reference/fiber/
scales/{scale_id}/addon/fiber/
```

Each role contains a selected-library direct complete-path streamline-score
mean and two seed-only target-conditioned branches. `all_coverage` is the
primary descriptive branch and scores targets from the complete final valid
fiber axis. `selected_sweet_sour` retains the selected-library target scores as
a visualization-only sensitivity branch. Both branches map their target scores
through every canonical streamline in the formal connectome. Each score-map
family contains one `display.nii.gz` and matching PNG and PDF figures. The
display map uses the shared Gaussian smoothing, output voxel size, and support
threshold without changing the scientific model inputs. Each role also contains
one mirrored target raincloud. Its left distribution contains the
selected sweet and sour library, its right distribution contains the complete
final valid fiber axis, and its central jitter shows every target-intersecting
valid fiber. Reference and add-on use one shared symmetric y-axis; repeated
multi-target fibers remain descriptive points rather than independent samples.
When the parent publication provides the patient-by-fiber inference basis, the
axes-internal stars report unadjusted two-sided patient-level rank-space
Freedman-Lane targetwise P values below 0.05. The test is conditional on the
published final tau, Coverage, branch, and valid fiber axis; exact targetwise,
Holm-adjusted, and single-step complete-null maxT values remain in the result
table. An older parent publication without the complete inference basis
produces no significance-star annotation. Branch-local support counts remain
available in the projection and composition QC JSON files.
`endpoint_index.csv` and `manifest.json` provide the compact cross-role index
and provenance.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def prepare_fiber_section_context(
    *,
    catalog: PublicationCatalog,
    spatial_config_path: str | Path,
    spatial_config: Mapping[str, Any] | None = None,
    background_record: Mapping[str, Any] | None = None,
) -> FiberSectionContext:
    """Validate and open shared fiber visualization resources once."""

    config_path = Path(spatial_config_path).expanduser().resolve()
    root_config = (
        load_spatial_result_config(config_path)
        if spatial_config is None
        else spatial_config
    )
    config = root_config["fiber"]
    display_map = root_config["display_map"]
    outline_isovalue = float(root_config["outline"]["continuous_isovalue"])
    config_record = _file_record(config_path, "spatial_result_visualization_config")
    background_path = Path(
        str(root_config["background"]["path"])
    ).expanduser().resolve()
    if background_record is None:
        resolved_background_record = _nifti_resource_record(
            background_path, "anatomy_background"
        )
    else:
        recorded_path = Path(str(background_record.get("path", ""))).resolve()
        if recorded_path != background_path:
            raise ValueError("shared anatomy record does not match fiber background")
        resolved_background_record = dict(background_record)

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
        raise ValueError(
            "normative-fiber publication does not identify one formal connectome"
        )
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
    target_display_labels = tuple(str(value["label"]) for value in target_specs)
    targets = tuple(
        load_binary_projection_mask(
            str(value["path"]), roi_id=str(value["name"]), role="target"
        )
        for value in target_specs
    )
    target_records: list[dict[str, Any]] = []
    for configured_index, (target, display_label) in enumerate(
        zip(targets, target_display_labels, strict=True)
    ):
        record = _nifti_resource_record(
            target.source_path,
            f"target:{target.roi_id}",
        )
        record.update(
            {
                "configured_index": configured_index,
                "display_label": display_label,
            }
        )
        target_records.append(record)
    seeds = {
        role_spec.role: load_binary_projection_mask(
            str(config["seeds"][role_spec.role]["path"]),
            roi_id=role_spec.role,
            role="seed",
        )
        for role_spec in _ROLE_SPECS
    }
    for seed in seeds.values():
        validate_exact_mask_geometry(seed, targets)
    seed_records = {
        role: _nifti_resource_record(seed.source_path, f"seed:{role}")
        for role, seed in seeds.items()
    }
    outline_paths: dict[str, Path | None] = {}
    outline_records: dict[str, Mapping[str, Any] | None] = {}
    for role_spec in _ROLE_SPECS:
        configured_path = config["seeds"][role_spec.role].get("outline_path")
        if configured_path is None:
            outline_paths[role_spec.role] = None
            outline_records[role_spec.role] = None
        else:
            outline_path = Path(str(configured_path)).expanduser().resolve()
            outline_paths[role_spec.role] = outline_path
            outline_records[role_spec.role] = _nifti_resource_record(
                outline_path,
                f"continuous_outline:{role_spec.role}",
            )
    return FiberSectionContext(
        config=config,
        display_map=display_map,
        outline_isovalue=outline_isovalue,
        config_record=config_record,
        background_path=background_path,
        background_record=resolved_background_record,
        formal_connectome_id=formal_connectome_id,
        connectome=connectome,
        connectome_record=connectome_record,
        targets=targets,
        target_records=tuple(target_records),
        seeds=seeds,
        seed_records=seed_records,
        outline_paths=outline_paths,
        outline_records=outline_records,
    )


def run_single_scale_fiber_section_postprocess(
    *,
    scale_id: str,
    output_root: str | Path,
    normative_fiber_publication_root: str | Path,
    spatial_config_path: str | Path,
    shared_cache_root: str | Path | None = None,
    style_overrides: Mapping[str, Any] | None = None,
    force: bool = False,
    rebuild_physical_cache: bool = False,
    _catalog: PublicationCatalog | None = None,
    _context: FiberSectionContext | None = None,
    _write_root_metadata: bool = True,
    _result_filename: str = "result.json",
) -> dict[str, Any]:
    """Publish four PDQ-39 fiber section figures and their spatial derivatives."""

    normalized_scale = str(scale_id).strip()
    if not normalized_scale or "/" in normalized_scale or ".." in normalized_scale:
        raise ValueError("scale_id must be one safe path component")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if Path(_result_filename).name != _result_filename or not _result_filename.endswith(
        ".json"
    ):
        raise ValueError("_result_filename must be one JSON filename")
    catalog = _catalog or PublicationCatalog.from_config(
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
    context = _context or prepare_fiber_section_context(
        catalog=catalog, spatial_config_path=spatial_config_path
    )
    config = context.config
    display_map = context.display_map
    outline_isovalue = context.outline_isovalue
    config_record = context.config_record
    background_path = context.background_path
    background_record = context.background_record
    formal_connectome_id = context.formal_connectome_id
    connectome = context.connectome
    connectome_record = context.connectome_record
    targets = context.targets
    target_records = context.target_records
    target_display_labels = tuple(
        str(record["display_label"]) for record in target_records
    )
    seeds = context.seeds
    seed_records = context.seed_records
    outline_paths = context.outline_paths
    outline_records = context.outline_records

    resolved_profile_artifact = catalog.resolve_relative(
        "normative_fiber_main",
        "resolved_normative_fiber_model.yaml",
    )
    resolved_profile = _read_yaml(resolved_profile_artifact.path)
    formal_resampling = resolved_profile.get("formal_resampling")
    if not isinstance(formal_resampling, Mapping):
        raise ValueError("resolved normative-fiber profile lacks formal_resampling")
    permutation_resamples = formal_resampling.get("permutation_resamples")
    permutation_seed = formal_resampling.get("seed")
    if (
        type(permutation_resamples) is not int
        or permutation_resamples < 1
        or type(permutation_seed) is not int
    ):
        raise ValueError(
            "resolved normative-fiber permutation_resamples and seed are invalid"
        )
    normalized_display_name, study_scale_definition_record = (
        catalog.resolve_scale_display_name(
            "normative_fiber_main",
            normalized_scale,
        )
    )
    direct_colorbar_semantic_label = str(
        config["labels"]["direct_streamline_colorbar_template"]
    ).format(scale_display_name=normalized_display_name)
    target_colorbar_semantic_label = str(
        config["labels"]["target_conditioned_colorbar_template"]
    ).format(scale_display_name=normalized_display_name)
    direct_colorbar_render_label = (
        "Mean selected-fiber partial Spearman ρ\n"
        f"with {normalized_display_name}"
    )
    target_colorbar_render_label = (
        "Target-derived fiber partial Spearman ρ\n"
        f"with {normalized_display_name}"
    )
    base_style = get_fiber_section_cfg(style_overrides)
    base_style["mask_threshold"] = outline_isovalue
    target_style_defaults = get_target_score_raincloud_cfg()
    target_chart_style = get_target_score_raincloud_cfg(
        {
            key: value
            for key, value in dict(style_overrides or {}).items()
            if key in target_style_defaults
        }
    )
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "preparing_physical_cache",
        "scale_id": normalized_scale,
        "scale_display_name": normalized_display_name,
        "study_scale_definition": study_scale_definition_record,
        "spatial_config": config_record,
        "display_map": dict(display_map),
        "outline_isovalue": outline_isovalue,
        "background": background_record,
        "connectome": connectome_record,
        "seeds": seed_records,
        "outlines": outline_records,
        "targets": target_records,
        "target_chart": dict(config["target_chart"]),
        "target_score_chart_style": target_chart_style,
        "formal_target_inference": {
            "schema_version": TARGET_INFERENCE_SCHEMA,
            "permutation_resamples": permutation_resamples,
            "seed": permutation_seed,
            "configuration": resolved_profile_artifact.as_manifest_record(),
            "multiplicity_primary": "holm_strong_fwer",
            "max_t_status": "supplementary_complete_null_single_step",
        },
        "publications": catalog.publication_records(),
        "results": [],
    }
    if _write_root_metadata:
        _write_json_atomic(manifest_path, manifest)

    physical_cache_hash = _payload_hash(
        {
            "algorithm": COMPOSITION_ALGORITHM,
            "algorithm_version": COMPOSITION_VERSION,
            "connectome_identity": connectome_record["connectome_identity"],
            "ordered_fiber_id_hash": connectome_record["ordered_fiber_id_hash"],
            "n_fibers": connectome_record["n_fibers"],
            "seeds": seed_records,
            "targets": target_records,
            "voxel_composition_fiber_scope": "formal_connectome_all",
            "per_fiber_per_voxel": "once",
            "target_hit_method": "segment_intersection",
        }
    )
    shared_root = (
        Path(shared_cache_root).expanduser().resolve()
        if shared_cache_root is not None
        else root.parent / ".cache" / "fiber_spatial"
    )
    physical_cache_path = (
        shared_root / f"whole_connectome_patterns_{physical_cache_hash}.npz"
    )
    physical_cache_status = "reused"
    try:
        if physical_cache_path.is_file() and not rebuild_physical_cache:
            physical = _load_physical_cache(physical_cache_path)
        else:
            physical = build_whole_connectome_composition(
                connectome=connectome,
                seeds=seeds,
                targets=targets,
                fiber_chunk_size=int(config["cache"]["fiber_chunk_size"]),
                progress_callback=lambda value: print(
                    json.dumps({"physical_cache_progress": dict(value)}),
                    file=sys.stderr,
                    flush=True,
                ),
            )
            _write_physical_cache(physical_cache_path, physical)
            physical_cache_status = "computed"
        if physical.target_ids != tuple(value.roi_id for value in targets):
            raise ValueError("physical cache target order does not match configuration")
        if physical.n_all_fibers != connectome.metadata.n_fibers:
            raise ValueError("physical cache formal-connectome fiber count changed")
        if physical.ordered_fiber_id_hash != connectome.metadata.ordered_fiber_id_hash:
            raise ValueError("physical cache canonical fiber identity changed")
        for role, seed in seeds.items():
            if not np.array_equal(
                physical.for_role(role).seed_voxel_indices,
                seed.flat_voxel_indices,
            ):
                raise ValueError(f"physical cache seed voxel axis changed: {role}")
        physical_cache_record = _file_record(
            physical_cache_path, "whole_connectome_seed_voxel_target_patterns"
        )
        physical_cache_record.update(
            {
                "cache_key": physical_cache_hash,
                "cache_status": physical_cache_status,
                "algorithm": COMPOSITION_ALGORITHM,
                "algorithm_version": COMPOSITION_VERSION,
                "n_all_fibers": physical.n_all_fibers,
                "target_count": len(physical.target_ids),
            }
        )
        manifest["physical_cache"] = physical_cache_record
        manifest["status"] = "running"
        if _write_root_metadata:
            _write_json_atomic(manifest_path, manifest)
    except Exception as error:  # noqa: BLE001 - global physical failure is terminal
        manifest.update(
            {
                "status": "failed_physical_cache",
                "failed_count": len(_ROLE_SPECS),
                "completed_count": 0,
                "reused_count": 0,
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )
        if _write_root_metadata:
            _write_json_atomic(manifest_path, manifest)
            _write_root_index(root, manifest["results"])
            _write_readme(root, normalized_scale, normalized_display_name)
        return manifest

    prepared_roles: dict[str, _PreparedRole] = {}
    preparation_errors: dict[str, dict[str, str]] = {}
    for role_spec in _ROLE_SPECS:
        role_leaf = root / "scales" / normalized_scale / role_spec.role / "fiber"
        result_path = role_leaf / _result_filename
        if not force and _result_reusable(result_path):
            reused = _read_json(result_path)
            reused["resume_status"] = "reused"
            manifest["results"].append(reused)
            if _write_root_metadata:
                _write_json_atomic(manifest_path, manifest)
            continue
        try:
            artifacts, final_model = _resolve_role_artifacts(
                catalog, scale_id=normalized_scale, role=role_spec.role
            )
            if final_model.get("formal_connectome_id") != formal_connectome_id:
                raise ValueError(
                    f"final model formal connectome mismatch: {role_spec.role}"
                )
            source_records = {
                name: artifact.as_manifest_record()
                for name, artifact in artifacts.items()
            }
            (
                coverage_ids,
                coverage_scores,
                selected_ids,
                selected_scores,
                selected_is_sweet,
            ) = _fiber_data(artifacts)
            coverage_target_membership = target_membership_from_bits(
                physical.fiber_target_bits,
                coverage_ids,
                len(targets),
            )
            target_membership = target_membership_from_bits(
                physical.fiber_target_bits,
                selected_ids,
                len(targets),
            )
            selected_target_scores = compute_selected_target_scores(
                selected_scores=selected_scores,
                target_membership=target_membership,
            )
            coverage_target_scores = compute_target_scores(
                fiber_scores=coverage_scores,
                target_membership=coverage_target_membership,
            )
            seed_record = seed_records[role_spec.role]
            selected_projection_hash = _payload_hash(
                {
                    "schema_version": SCHEMA_VERSION,
                    "algorithm": PROJECTION_ALGORITHM,
                    "algorithm_version": PROJECTION_VERSION,
                    "scale_id": normalized_scale,
                    "model_role": role_spec.role,
                    "source_artifacts": source_records,
                    "connectome": connectome_record,
                    "seed": seed_record,
                    "direct_streamline_scope": config["projection"][
                        "direct_streamline_scope"
                    ],
                    "per_fiber_per_voxel": "once",
                }
            )
            target_request_hash = _payload_hash(
                {
                    "physical_cache_hash": physical_cache_hash,
                    "source_artifacts": source_records,
                    "primary_target_score_fiber_scope": (
                        "final_resolver_valid_fiber_axis"
                    ),
                    "sensitivity_target_score_fiber_scope": (
                        "selected_sweet_sour"
                    ),
                    "target_distribution_fiber_scope": (
                        "final_resolver_valid_fiber_axis"
                    ),
                    "streamline_target_score": (
                        "equal_mean_over_finite_target_scores"
                    ),
                    "missing_target_score_policy": (
                        "exclude_target_then_renormalize_per_streamline"
                    ),
                }
            )
            prepared_roles[role_spec.role] = _PreparedRole(
                artifacts=artifacts,
                final_model=final_model,
                source_records=source_records,
                coverage_ids=coverage_ids,
                coverage_scores=coverage_scores,
                coverage_target_membership=coverage_target_membership,
                selected_ids=selected_ids,
                selected_scores=selected_scores,
                selected_is_sweet=selected_is_sweet,
                target_membership=target_membership,
                coverage_target_scores=coverage_target_scores,
                selected_target_scores=selected_target_scores,
                selected_projection_hash=selected_projection_hash,
                target_request_hash=target_request_hash,
            )
        except Exception as error:  # noqa: BLE001 - recorded as role-local failure
            preparation_errors[role_spec.role] = {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }

    shared_scatter_arrays = []
    for prepared in prepared_roles.values():
        plotted = np.any(prepared.coverage_target_membership, axis=1)
        shared_scatter_arrays.append(prepared.coverage_scores[plotted])
    lower_padding_fraction = float(
        target_chart_style["axis_lower_padding_fraction"]
    )
    upper_padding_fraction = float(
        target_chart_style["axis_upper_padding_fraction"]
    )
    try:
        target_chart_y_limits = shared_asymmetric_target_limits(
            shared_scatter_arrays,
            lower_padding_fraction=lower_padding_fraction,
            upper_padding_fraction=upper_padding_fraction,
        )
        finite_scatter_scores = np.concatenate(
            [
                values[np.isfinite(values)]
                for values in shared_scatter_arrays
                if np.any(np.isfinite(values))
            ]
        )
        target_chart_scatter_bounds = (
            float(np.min(finite_scatter_scores)),
            float(np.max(finite_scatter_scores)),
        )
    except ValueError as error:
        for role in prepared_roles:
            preparation_errors[role] = {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        target_chart_y_limits = (-1.0, 1.0)
        target_chart_scatter_bounds = (None, None)
    target_chart_shared_hash = _payload_hash(
        {
            "schema_version": SCHEMA_VERSION,
            "scale_id": normalized_scale,
            "scale_display_name": normalized_display_name,
            "physical_cache_hash": physical_cache_hash,
            "role_source_artifacts": {
                role: prepared.source_records
                for role, prepared in sorted(prepared_roles.items())
            },
            "preparation_errors": preparation_errors,
            "style": target_chart_style,
            "shared_y_limits": list(target_chart_y_limits),
            "shared_scatter_bounds": list(target_chart_scatter_bounds),
            "axis_lower_padding_fraction": lower_padding_fraction,
            "axis_upper_padding_fraction": upper_padding_fraction,
            "target_order": list(physical.target_ids),
            "target_display_labels": list(target_display_labels),
            "target_order_policy": config["target_chart"]["order_policy"],
            "formal_target_inference": manifest["formal_target_inference"],
        }
    )
    manifest["target_score_chart"] = {
        "shared_contract_hash": target_chart_shared_hash,
        "shared_y_limits": list(target_chart_y_limits),
        "shared_scatter_bounds": list(target_chart_scatter_bounds),
        "axis_lower_padding_fraction": lower_padding_fraction,
        "axis_upper_padding_fraction": upper_padding_fraction,
        "prepared_roles": sorted(prepared_roles),
        "preparation_errors": preparation_errors,
        "descriptive_jitter_only": True,
        "coverage_distribution_scope": "final_resolver_valid_fiber_axis",
        "all_coverage_distribution_includes_selected": True,
        "target_order": list(physical.target_ids),
        "target_display_labels": list(target_display_labels),
        "target_order_policy": config["target_chart"]["order_policy"],
    }
    if _write_root_metadata:
        _write_json_atomic(manifest_path, manifest)

    failures = 0
    for role_spec in _ROLE_SPECS:
        role_leaf = root / "scales" / normalized_scale / role_spec.role / "fiber"
        result_path = role_leaf / _result_filename
        if (
            role_spec.role not in prepared_roles
            and role_spec.role not in preparation_errors
        ):
            continue
        try:
            if role_spec.role in preparation_errors:
                error = preparation_errors[role_spec.role]
                raise ValueError(
                    "target-score preflight failed: "
                    f"{error['error_type']}: {error['error_message']}"
                )
            prepared = prepared_roles[role_spec.role]
            artifacts = prepared.artifacts
            final_model = prepared.final_model
            seed = seeds[role_spec.role]
            seed_record = seed_records[role_spec.role]
            outline_path = outline_paths[role_spec.role]
            outline_record = outline_records[role_spec.role]
            source_records = prepared.source_records
            selected_projection_hash = prepared.selected_projection_hash
            target_request_hash = prepared.target_request_hash

            selected_ids = prepared.selected_ids
            selected_scores = prepared.selected_scores
            selected_is_sweet = prepared.selected_is_sweet
            coverage_ids = prepared.coverage_ids
            coverage_scores = prepared.coverage_scores
            coverage_target_membership = prepared.coverage_target_membership
            cache_path = (
                root
                / ".cache"
                / normalized_scale
                / role_spec.role
                / f"selected_direct_projection_{selected_projection_hash}.npz"
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
                projection = compute_selected_direct_projection(
                    fiber_ids=selected_ids,
                    scores=selected_scores,
                    is_sweet=selected_is_sweet,
                    streamlines=streamlines,
                    seed=seed,
                )
                _write_projection_cache(cache_path, projection, streamlines)
                cache_status = "computed"

            target_membership = prepared.target_membership
            selected_target_scores = prepared.selected_target_scores
            coverage_target_scores = prepared.coverage_target_scores
            composition = physical.for_role(role_spec.role)
            target_score_branches = {
                "all_coverage": {
                    "analysis_role": "primary",
                    "fiber_ids": coverage_ids,
                    "scores": coverage_target_scores,
                    "membership": coverage_target_membership,
                    "selected_is_sweet": None,
                    "scope": "final_resolver_valid_fiber_axis",
                },
                "selected_sweet_sour": {
                    "analysis_role": "sensitivity_visualization",
                    "fiber_ids": selected_ids,
                    "scores": selected_target_scores,
                    "membership": target_membership,
                    "selected_is_sweet": projection.is_sweet,
                    "scope": "selected_sweet_sour",
                },
            }
            target_projections = {
                branch: apply_target_scores_to_composition(
                    composition=composition,
                    target_scores=spec["scores"],
                )
                for branch, spec in target_score_branches.items()
            }

            direct_maps = role_leaf / "direct_streamline" / "maps"
            direct_figures = role_leaf / "direct_streamline" / "figures"
            target_root = role_leaf / "target_conditioned"
            target_tables = target_root / "tables"
            target_figures = target_root / "figures"
            outputs: list[str] = []
            (
                target_inference_manifest,
                target_inference_targetwise,
                target_inference_outputs,
            ) = _run_role_target_inference(
                root=root,
                target_root=target_root,
                scale_id=normalized_scale,
                role=role_spec.role,
                artifacts=artifacts,
                coverage_ids=coverage_ids,
                coverage_scores=coverage_scores,
                coverage_target_membership=coverage_target_membership,
                coverage_target_scores=coverage_target_scores,
                target_ids=physical.target_ids,
                target_records=target_records,
                physical_cache_record=physical_cache_record,
                replicate_count=permutation_resamples,
                seed=permutation_seed,
            )
            outputs.extend(target_inference_outputs)
            score_map_families: list[
                tuple[Path, np.ndarray, np.ndarray, str]
            ] = [
                (
                    direct_maps,
                    projection.direct_voxel_indices,
                    projection.direct_score_mean,
                    "mean selected-fiber model score",
                ),
            ]
            for branch, branch_projection in target_projections.items():
                score_map_families.append(
                    (
                        target_root / branch / "maps",
                        branch_projection.seed_voxel_indices,
                        branch_projection.target_conditioned_score,
                        (
                            f"{branch.replace('_', '-')} "
                            "target-conditioned model score"
                        ),
                    )
                )
            map_records: dict[str, dict[str, Any]] = {}
            display_transforms: dict[str, dict[str, Any]] = {}
            for map_directory, indices, values, description in score_map_families:
                display_path = map_directory / "display.nii.gz"
                source_image = _sparse_nifti_image(
                    seed_path=seed.source_path,
                    voxel_indices=indices,
                    values=values,
                    description=description,
                )
                _, display_transform = create_display_nifti(
                    source_image,
                    display_path,
                    fwhm_mm=float(display_map["fwhm_mm"]),
                    voxel_size_mm=float(display_map["voxel_size_mm"]),
                    support_weight_threshold=float(
                        display_map["support_weight_threshold"]
                    ),
                    force=force,
                )
                record_key = display_path.relative_to(role_leaf).as_posix()
                map_records[record_key] = _nifti_resource_record(
                    display_path, "fiber_display_derivative"
                )
                display_transforms[record_key] = display_transform
                outputs.append(display_path.relative_to(root).as_posix())

            projection_qc_path = role_leaf / "direct_streamline" / "projection_qc.json"
            _write_json_atomic(projection_qc_path, _projection_qc(projection))
            outputs.append(projection_qc_path.relative_to(root).as_posix())
            for branch, spec in target_score_branches.items():
                branch_root = target_root / branch
                target_qc_path = branch_root / "target_score_qc.json"
                composition_qc_path = branch_root / "voxel_composition_qc.json"
                _write_json_atomic(
                    target_qc_path,
                    _target_score_qc(
                        fiber_ids=spec["fiber_ids"],
                        target_ids=physical.target_ids,
                        target_membership=spec["membership"],
                        target_scores=spec["scores"],
                        target_score_fiber_scope=str(spec["scope"]),
                    ),
                )
                _write_json_atomic(
                    composition_qc_path,
                    _composition_qc(
                        physical=physical,
                        composition=composition,
                        projection=target_projections[branch],
                        target_scores=spec["scores"],
                        target_score_fiber_scope=str(spec["scope"]),
                    ),
                )
                outputs.extend(
                    [
                        target_qc_path.relative_to(root).as_posix(),
                        composition_qc_path.relative_to(root).as_posix(),
                    ]
                )

                target_score_path = branch_root / "tables" / "target_scores.csv"
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
                        "target_score_fiber_scope",
                    ),
                    _target_score_rows(
                        target_ids=physical.target_ids,
                        target_membership=spec["membership"],
                        target_scores=spec["scores"],
                        target_score_fiber_scope=str(spec["scope"]),
                        selected_is_sweet=spec["selected_is_sweet"],
                    ),
                )
                outputs.append(target_score_path.relative_to(root).as_posix())

            membership_path = (
                target_root
                / "selected_sweet_sour"
                / "tables"
                / "fiber_target_membership.csv"
            )
            target_fiber_distribution_path = (
                target_tables / "target_fiber_distributions.csv"
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
                    "target_score_finite",
                    "streamline_weight",
                ),
                _membership_rows(
                    projection=projection,
                    target_ids=physical.target_ids,
                    target_membership=target_membership,
                    target_scores=selected_target_scores,
                ),
            )
            _write_csv_atomic(
                target_fiber_distribution_path,
                (
                    "model_role",
                    "target_rank",
                    "configured_target_index",
                    "target_id",
                    "fiber_id",
                    "fiber_score",
                    "is_selected",
                    "fiber_class",
                    "selected_target_score",
                    "all_coverage_target_mean",
                    "selected_target_fiber_count",
                    "coverage_target_fiber_count",
                ),
                build_target_fiber_distribution_rows(
                    model_role=role_spec.role,
                    target_ids=physical.target_ids,
                    target_scores=selected_target_scores,
                    coverage_fiber_ids=coverage_ids,
                    coverage_scores=coverage_scores,
                    selected_fiber_ids=selected_ids,
                    selected_is_sweet=selected_is_sweet,
                    coverage_target_membership=coverage_target_membership,
                    target_order_policy=config["target_chart"]["order_policy"],
                ),
            )
            outputs.extend(
                [
                    membership_path.relative_to(root).as_posix(),
                    target_fiber_distribution_path.relative_to(root).as_posix(),
                ]
            )

            common_figure_payload = {
                "schema_version": SCHEMA_VERSION,
                "scale_id": normalized_scale,
                "scale_display_name": normalized_display_name,
                "study_scale_definition": study_scale_definition_record,
                "model_role": role_spec.role,
                "model_unit": "fiber_display_derivative",
                "source_artifacts": source_records,
                "connectome": connectome_record,
                "seed": seed_record,
                "outline": outline_record or seed_record,
                "background": background_record,
                "selected_projection_hash": selected_projection_hash,
                "target_request_hash": target_request_hash,
                "target_chart_shared_hash": target_chart_shared_hash,
                "target_chart_shared_y_limits": list(target_chart_y_limits),
                "target_chart_shared_scatter_bounds": list(
                    target_chart_scatter_bounds
                ),
                "target_chart_axis_lower_padding_fraction": (
                    lower_padding_fraction
                ),
                "target_chart_axis_upper_padding_fraction": (
                    upper_padding_fraction
                ),
                "physical_cache": physical_cache_record,
                "target_order": list(physical.target_ids),
                "target_display_labels": list(target_display_labels),
                "target_order_policy": config["target_chart"]["order_policy"],
                "target_distribution_fiber_scope": (
                    "final_resolver_valid_fiber_axis"
                ),
                "all_coverage_distribution_includes_selected": True,
                "target_inference": target_inference_manifest,
                "voxel_composition_fiber_scope": "formal_connectome_all",
                "display_map_contract": dict(display_map),
            }
            direct_style = get_fiber_section_cfg(
                {
                    **dict(style_overrides or {}),
                    "mask_threshold": outline_isovalue,
                    "colorbar_label": direct_colorbar_render_label,
                }
            )
            target_style = get_fiber_section_cfg(
                {
                    **dict(style_overrides or {}),
                    "mask_threshold": outline_isovalue,
                    "colorbar_label": target_colorbar_render_label,
                }
            )
            figure_families: list[
                tuple[Path, Path, str, Mapping[str, Any], str, str | None, str]
            ] = [
                (
                    direct_maps,
                    direct_figures,
                    "direct_streamline_score_mean",
                    direct_style,
                    direct_colorbar_semantic_label,
                    None,
                    "direct_visualization",
                ),
            ]
            for branch, spec in target_score_branches.items():
                figure_families.append(
                    (
                        target_root / branch / "maps",
                        target_root / branch / "figures",
                        f"target_conditioned_score_{branch}",
                        target_style,
                        target_colorbar_semantic_label,
                        str(spec["scope"]),
                        str(spec["analysis_role"]),
                    )
                )
            for (
                map_directory,
                figure_directory,
                artifact_kind,
                style,
                semantic_colorbar_label,
                target_score_fiber_scope,
                analysis_role,
            ) in figure_families:
                display_path = map_directory / "display.nii.gz"
                display_key = display_path.relative_to(role_leaf).as_posix()
                _, figure_outputs = _render_figure(
                    heat_path=display_path,
                    background_path=background_path,
                    seed_path=seed.source_path,
                    outline_path=outline_path,
                    figure_stem=figure_directory / "display",
                    style=style,
                    figure_payload={
                        **common_figure_payload,
                        "display_artifact_kind": artifact_kind,
                        "display_transform": display_transforms[display_key],
                        "colorbar_semantic_label": semantic_colorbar_label,
                        "target_score_fiber_scope": target_score_fiber_scope,
                        "analysis_role": analysis_role,
                    },
                    root=root,
                )
                outputs.extend(figure_outputs)
            _, target_chart_outputs = _render_target_score_figure(
                target_ids=physical.target_ids,
                target_display_labels=target_display_labels,
                target_order_policy=config["target_chart"]["order_policy"],
                target_scores=selected_target_scores,
                coverage_fiber_ids=coverage_ids,
                coverage_scores=coverage_scores,
                selected_fiber_ids=selected_ids,
                selected_is_sweet=selected_is_sweet,
                coverage_target_membership=coverage_target_membership,
                scale_display_name=normalized_display_name,
                shared_y_limits=target_chart_y_limits,
                targetwise_p_values=(
                    target_inference_targetwise
                    if target_inference_manifest.get("status") == "complete"
                    else None
                ),
                figure_stem=(
                    target_figures / "target_score_dual_raincloud"
                ),
                style=target_chart_style,
                figure_payload={
                    **common_figure_payload,
                    "display_artifact_kind": "target_score_dual_raincloud",
                    "target_score_fiber_scope": (
                        "paired_selected_sweet_sour_and_final_resolver_valid_fiber_axis"
                    ),
                    "analysis_role": "descriptive_comparison",
                    "target_chart_shared_hash": target_chart_shared_hash,
                    "target_chart_shared_y_limits": list(
                        target_chart_y_limits
                    ),
                    "target_chart_shared_scatter_bounds": list(
                        target_chart_scatter_bounds
                    ),
                    "target_chart_axis_lower_padding_fraction": (
                        lower_padding_fraction
                    ),
                    "target_chart_axis_upper_padding_fraction": (
                        upper_padding_fraction
                    ),
                    "target_fiber_distribution_table": (
                        target_fiber_distribution_path.relative_to(root).as_posix()
                    ),
                    "jitter_inference_scope": "descriptive_only",
                    "formal_target_inference_scope": (
                        "all_coverage_conditional_on_published_final_model"
                        if target_inference_manifest.get("status") == "complete"
                        else "not_available_parent_publication_missing_basis"
                    ),
                    "formal_target_inference_manifest": (
                        "target_conditioned/inference/"
                        "target_group_permutation_manifest.json"
                        if target_inference_manifest.get("status") == "complete"
                        else None
                    ),
                    "plotted_p_value": (
                        "p_net_targetwise_significance_stars"
                        if target_inference_manifest.get("status") == "complete"
                        else None
                    ),
                },
                root=root,
            )
            outputs.extend(target_chart_outputs)
            result = {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "selected_projection_hash": selected_projection_hash,
                "target_request_hash": target_request_hash,
                "target_chart_shared_hash": target_chart_shared_hash,
                "physical_cache_hash": physical_cache_hash,
                "scale_id": normalized_scale,
                "scale_display_name": normalized_display_name,
                "model_role": role_spec.role,
                "final_branch": final_model.get("final_branch"),
                "selected_tau": final_model.get("selected_tau_v_per_m"),
                "selected_coverage": final_model.get(
                    "selected_coverage_subjects_min"
                ),
                "selected_fiber_count": int(selected_ids.size),
                "coverage_qualified_fiber_count": int(coverage_ids.size),
                "sweet_fiber_count": int(np.sum(selected_is_sweet)),
                "sour_fiber_count": int(np.sum(~selected_is_sweet)),
                "primary_target_score_fiber_scope": (
                    "final_resolver_valid_fiber_axis"
                ),
                "sensitivity_target_score_fiber_scope": "selected_sweet_sour",
                "finite_target_score_count": {
                    branch: int(np.sum(np.isfinite(spec["scores"])))
                    for branch, spec in target_score_branches.items()
                },
                "target_conditioned_finite_voxel_count": {
                    branch: int(
                        np.sum(np.isfinite(branch_projection.target_conditioned_score))
                    )
                    for branch, branch_projection in target_projections.items()
                },
                "voxel_composition_fiber_scope": "formal_connectome_all",
                "n_all_composition_fibers": physical.n_all_fibers,
                "display_map": dict(display_map),
                "figure_count": 4,
                "cache_status": cache_status,
                "cache_path": cache_path.relative_to(root).as_posix(),
                "physical_cache_status": physical_cache_status,
                "physical_cache_path": str(physical_cache_path),
                "target_inference": target_inference_manifest,
                "source_artifacts": source_records,
                "map_records": map_records,
                "outputs": outputs,
                "result_path": result_path.relative_to(root).as_posix(),
            }
            _write_json_atomic(result_path, result)
            _write_json_atomic(
                _completion_marker(result_path),
                {"status": "complete"},
            )
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
        if _write_root_metadata:
            _write_json_atomic(manifest_path, manifest)

    manifest["status"] = "complete" if failures == 0 else "completed_with_failures"
    manifest["completed_count"] = sum(
        value.get("status") == "complete" for value in manifest["results"]
    )
    manifest["reused_count"] = sum(
        value.get("resume_status") == "reused" for value in manifest["results"]
    )
    manifest["failed_count"] = failures
    if _write_root_metadata:
        _write_json_atomic(manifest_path, manifest)
        _write_root_index(root, manifest["results"])
        _write_readme(root, normalized_scale, normalized_display_name)
    return manifest


def render_fiber_section_components(
    *,
    scale_ids: Sequence[str],
    output_root: str | Path,
    catalog: PublicationCatalog,
    context: FiberSectionContext,
    style_overrides: Mapping[str, Any] | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Render fiber endpoint components with one shared connectome context."""

    normalized_scales = tuple(str(value).strip() for value in scale_ids)
    if not normalized_scales:
        raise ValueError("scale_ids must contain at least one scale")
    if len(set(normalized_scales)) != len(normalized_scales):
        raise ValueError("scale_ids must not contain duplicates")
    for scale_id in normalized_scales:
        if not scale_id or "/" in scale_id or ".." in scale_id:
            raise ValueError("every scale_id must be one safe path component")

    results: list[dict[str, Any]] = []
    for scale_id in normalized_scales:
        component = run_single_scale_fiber_section_postprocess(
            scale_id=scale_id,
            output_root=output_root,
            normative_fiber_publication_root=output_root,
            spatial_config_path=str(context.config_record["path"]),
            style_overrides=style_overrides,
            force=force,
            _catalog=catalog,
            _context=context,
            _write_root_metadata=False,
            _result_filename="fiber_spatial.json",
        )
        results.extend(component["results"])
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--normative-fiber-root", required=True)
    parser.add_argument("--spatial-config", required=True)
    parser.add_argument("--shared-cache-root")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild-physical-cache", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_single_scale_fiber_section_postprocess(
        scale_id=args.scale_id,
        output_root=args.output_root,
        normative_fiber_publication_root=args.normative_fiber_root,
        spatial_config_path=args.spatial_config,
        shared_cache_root=args.shared_cache_root,
        force=args.force,
        rebuild_physical_cache=args.rebuild_physical_cache,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FiberSectionContext",
    "SCHEMA_VERSION",
    "prepare_fiber_section_context",
    "render_fiber_section_components",
    "run_single_scale_fiber_section_postprocess",
]
