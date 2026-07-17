"""Chunked seed-wide iFOD2 generation, coverage accumulation, and extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .classification import (
    CLASSIFIER_NAME,
    CLASSIFIER_VERSION,
    build_target_lookup,
    classify_streamlines,
)
from .errors import CoverageError, ToolError, ValidationError
from .identity import canonical_hash, file_sha256
from .models import BatchConfig, SeedSpec, ToolIdentity
from .state import atomic_write_json, read_json
from .tck import (
    load_tck_streamlines,
    validate_tck,
    write_concatenated_tck,
    write_selected_tck,
)
from .tools import run_command


def coverage_complete(hit_counts: Sequence[int], required: int) -> bool:
    """Return whether every configured target has reached the global minimum."""

    if not hit_counts:
        raise ValidationError("coverage requires at least one target")
    return all(int(value) >= int(required) for value in hit_counts)


def generation_complete(
    total_streamlines: int,
    hit_counts: Sequence[int],
    required_per_target: int,
    fixed_seedwide_streamlines: int | None,
) -> bool:
    """Return whether generation should stop under the configured mode."""

    if fixed_seedwide_streamlines is not None:
        return int(total_streamlines) >= int(fixed_seedwide_streamlines)
    return coverage_complete(hit_counts, required_per_target)


def next_chunk_request(total: int, chunk_size: int, maximum: int) -> int:
    """Return the exact next request without crossing the seed-wide maximum."""

    remaining = int(maximum) - int(total)
    return 0 if remaining <= 0 else min(int(chunk_size), remaining)


def derive_chunk_rng_seed(
    base_seed: int,
    seedwide_identity: str,
    subject_id: str,
    seed_key: str,
    chunk_index: int,
) -> int:
    """Derive one positive, deterministic, chunk-distinct MRtrix RNG seed."""

    payload = (
        f"{base_seed}\0{seedwide_identity}\0{subject_id}\0{seed_key}\0{chunk_index}"
    ).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return 1 + ((int(base_seed) + value) % (2**31 - 2))


def build_tckgen_command(
    executable: Path,
    fod_path: Path,
    output_path: Path,
    seed_path: Path,
    tracking_mask_path: Path,
    config: BatchConfig,
    requested_streamlines: int,
) -> list[str]:
    """Build the fixed unconditioned seed-wide iFOD2 command."""

    tracking = config.tracking
    execution = config.execution
    return [
        str(executable),
        str(fod_path),
        str(output_path),
        "-algorithm",
        "iFOD2",
        "-seed_image",
        str(seed_path),
        "-mask",
        str(tracking_mask_path),
        "-select",
        str(int(requested_streamlines)),
        "-cutoff",
        format(tracking.fod_cutoff, ".17g"),
        "-minlength",
        format(tracking.min_length_mm, ".17g"),
        "-maxlength",
        format(tracking.max_length_mm, ".17g"),
        "-nthreads",
        str(execution.mrtrix_threads_per_seedwide_job),
        "-force",
    ]


def source_tracking_mask_path(preparation: Mapping[str, Any]) -> Path:
    """Return the validated native-DWI tracking-mask NIfTI from provenance."""

    try:
        record = preparation["identity_document"]["inputs"]["tracking_mask"]
        path = Path(record["path"])
        expected_hash = str(record["sha256"])
    except (KeyError, TypeError) as exc:
        raise ValidationError(
            "prepared subject does not record its source tracking-mask path"
        ) from exc
    if not path.is_file() or file_sha256(path) != expected_hash:
        raise ValidationError(
            f"source tracking mask no longer matches preparation identity: {path}"
        )
    return path


def seedwide_identity(
    config: BatchConfig,
    subject_id: str,
    preparation: Mapping[str, Any],
    seed: SeedSpec,
    seed_record: Mapping[str, Any],
    tools: Mapping[str, ToolIdentity],
    code_hash: str,
) -> tuple[str, dict[str, Any]]:
    """Return the scientific identity for one subject and seed side."""

    document = {
        "identity_version": 1,
        "subject_id": subject_id,
        "preparation_identity": preparation["preparation_identity"],
        "seed": {
            "key": seed.key,
            "path": seed_record["path"],
            "hash": seed_record["hash"],
        },
        "targets": [
            {
                "key": target["key"],
                "path": target["path"],
                "hash": target["hash"],
            }
            for target in seed_record["targets"]
        ],
        "tracking": {
            "seedwide_streamlines": config.tracking.seedwide_streamlines,
            "minimum_streamlines_per_target": config.tracking.minimum_streamlines_per_target,
            "fod_cutoff": config.tracking.fod_cutoff,
            "min_length_mm": config.tracking.min_length_mm,
            "max_length_mm": config.tracking.max_length_mm,
            "random_seed": config.tracking.random_seed,
        },
        "generation": {
            "chunk_streamlines": config.execution.generation_chunk_streamlines,
            "maximum_seedwide_streamlines": config.execution.maximum_seedwide_streamlines,
            "mrtrix_threads": config.execution.mrtrix_threads_per_seedwide_job,
        },
        "classifier": {
            "name": CLASSIFIER_NAME,
            "version": CLASSIFIER_VERSION,
            "membership": "any segment intersects target voxel",
        },
        "tools": {
            "tckgen": tools["tckgen"].version,
            "tckinfo": tools["tckinfo"].version,
        },
        "code_hash": code_hash,
    }
    return canonical_hash(document), document


def _load_membership(path: Path, expected_shape: tuple[int, int]) -> np.ndarray:
    try:
        with np.load(path, allow_pickle=False) as archive:
            membership = np.asarray(archive["membership"], dtype=bool)
    except Exception as exc:
        raise ValidationError(f"cannot read membership artifact {path}: {exc}") from exc
    if membership.shape != expected_shape:
        raise ValidationError(
            f"membership shape mismatch for {path}: {membership.shape} versus {expected_shape}"
        )
    return membership


def _verify_chunk(
    record: Mapping[str, Any],
    expected_identity: str,
    target_count: int,
    tckinfo_executable: Path,
) -> bool:
    try:
        if record.get("status") != "complete" or record.get("identity") != expected_identity:
            return False
        actual = int(record["actual_streamlines"])
        chunk_path = Path(record["path"])
        if file_sha256(chunk_path) != record["sha256"]:
            return False
        validate_tck(chunk_path, tckinfo_executable, expected_count=actual)
        membership_path = Path(record["membership_path"])
        if file_sha256(membership_path) != record["membership_sha256"]:
            return False
        membership = _load_membership(membership_path, (actual, target_count))
        hit_counts = [int(value) for value in membership.sum(axis=0)]
        if hit_counts != [int(value) for value in record["target_hit_counts"]]:
            return False
        target_chunks = record["target_chunks"]
        if len(target_chunks) != target_count:
            return False
        for index, target_chunk in enumerate(target_chunks):
            path = Path(target_chunk["path"])
            if file_sha256(path) != target_chunk["sha256"]:
                return False
            validate_tck(
                path,
                tckinfo_executable,
                expected_count=hit_counts[index],
            )
    except (OSError, KeyError, TypeError, ValueError, ValidationError, ToolError):
        return False
    return True


def _verify_outputs(
    state: Mapping[str, Any],
    target_count: int,
    tckinfo_executable: Path,
) -> bool:
    try:
        if state.get("status") != "staged_complete":
            return False
        total = int(state["total_streamlines"])
        outputs = state["outputs"]
        mother = outputs["mother"]
        mother_path = Path(mother["path"])
        if file_sha256(mother_path) != mother["sha256"]:
            return False
        validate_tck(mother_path, tckinfo_executable, expected_count=total)
        targets = outputs["targets"]
        if len(targets) != target_count:
            return False
        for target in targets:
            path = Path(target["path"])
            if file_sha256(path) != target["sha256"]:
                return False
            validate_tck(
                path,
                tckinfo_executable,
                expected_count=int(target["streamline_count"]),
            )
    except (OSError, KeyError, TypeError, ValueError, ValidationError, ToolError):
        return False
    return True


def _chunk_identity(
    identity: str,
    index: int,
    requested: int,
    rng_seed: int,
) -> str:
    return canonical_hash(
        {
            "seedwide_identity": identity,
            "chunk_index": index,
            "requested_streamlines": requested,
            "rng_seed": rng_seed,
        }
    )


def _generate_chunk(
    *,
    config: BatchConfig,
    subject_id: str,
    seed: SeedSpec,
    identity: str,
    index: int,
    requested: int,
    rng_seed: int,
    seed_record: Mapping[str, Any],
    preparation: Mapping[str, Any],
    target_lookup,
    seed_work: Path,
    tools: Mapping[str, ToolIdentity],
    memory_observer: Callable[[float], None] | None,
) -> dict[str, Any]:
    attempt = uuid.uuid4().hex
    inflight = seed_work / "inflight" / f"chunk-{index:06d}-{attempt}.partial.tck"
    completed = seed_work / "chunks" / f"chunk-{index:06d}-{attempt}.tck"
    inflight.parent.mkdir(parents=True, exist_ok=True)
    completed.parent.mkdir(parents=True, exist_ok=True)
    command = build_tckgen_command(
        tools["tckgen"].executable,
        Path(preparation["artifacts"]["wm_fod"]["path"]),
        inflight,
        Path(seed_record["path"]),
        source_tracking_mask_path(preparation),
        config,
        requested,
    )
    run_command(
        command,
        log_path=seed_work / "logs" / f"chunk-{index:06d}-{attempt}.log",
        environment={"MRTRIX_RNG_SEED": str(rng_seed)},
        memory_observer=memory_observer,
    )
    actual = validate_tck(inflight, tools["tckinfo"].executable)
    if actual > requested:
        raise ValidationError(
            f"chunk {index} generated {actual} streamlines, exceeding request {requested}"
        )
    if actual == 0:
        raise ToolError(f"seed-wide tckgen chunk {index} produced zero streamlines")
    streamlines = load_tck_streamlines(inflight)
    if len(streamlines) != actual:
        raise ValidationError(
            f"chunk {index} Nibabel count {len(streamlines)} differs from tckinfo {actual}"
        )
    membership = classify_streamlines(streamlines, target_lookup)
    membership_path = (
        seed_work / "membership" / f"chunk-{index:06d}-{attempt}.npz"
    )
    membership_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(membership_path, membership=membership)
    hit_counts = [int(value) for value in membership.sum(axis=0)]
    target_chunks: list[dict[str, Any]] = []
    for target_index, target in enumerate(seed_record["targets"]):
        target_chunk = (
            seed_work
            / "target_chunks"
            / target["side"]
            / target["id"]
            / f"chunk-{index:06d}-{attempt}.tck"
        )
        written = write_selected_tck(
            streamlines,
            membership[:, target_index],
            target_chunk,
        )
        if written != hit_counts[target_index]:
            raise ValidationError("selected target chunk count differs from membership")
        validate_tck(
            target_chunk,
            tools["tckinfo"].executable,
            expected_count=written,
        )
        target_chunks.append(
            {
                "key": target["key"],
                "path": str(target_chunk),
                "streamline_count": written,
                "sha256": file_sha256(target_chunk),
            }
        )
    completed.parent.mkdir(parents=True, exist_ok=True)
    inflight.replace(completed)
    return {
        "status": "complete",
        "identity": _chunk_identity(identity, index, requested, rng_seed),
        "index": index,
        "requested_streamlines": requested,
        "actual_streamlines": actual,
        "yield_status": "full" if actual == requested else "underfilled",
        "rng_seed": rng_seed,
        "path": str(completed),
        "sha256": file_sha256(completed),
        "membership_path": str(membership_path),
        "membership_sha256": file_sha256(membership_path),
        "target_hit_counts": hit_counts,
        "target_chunks": target_chunks,
    }


def _build_outputs(
    state: dict[str, Any],
    seed_record: Mapping[str, Any],
    seed_work: Path,
    tools: Mapping[str, ToolIdentity],
) -> dict[str, Any]:
    output_dir = seed_work / "outputs" / uuid.uuid4().hex
    mother_path = output_dir / "seedwide.tck"
    chunks = state["chunks"]
    total = int(state["total_streamlines"])
    write_concatenated_tck(
        [Path(chunk["path"]) for chunk in chunks], mother_path, total
    )
    validate_tck(
        mother_path,
        tools["tckinfo"].executable,
        expected_count=total,
        full_coordinate_check=True,
    )
    targets: list[dict[str, Any]] = []
    for target_index, target in enumerate(seed_record["targets"]):
        count = int(state["target_hit_counts"][target_index])
        target_path = (
            output_dir
            / "targets"
            / target["side"]
            / f"{target['id']}.tck"
        )
        write_concatenated_tck(
            [Path(chunk["target_chunks"][target_index]["path"]) for chunk in chunks],
            target_path,
            count,
        )
        validate_tck(
            target_path,
            tools["tckinfo"].executable,
            expected_count=count,
            full_coordinate_check=True,
        )
        targets.append(
            {
                "id": target["id"],
                "side": target["side"],
                "key": target["key"],
                "path": str(target_path),
                "streamline_count": count,
                "hit_fraction": count / total,
                "sha256": file_sha256(target_path),
                "size_bytes": target_path.stat().st_size,
            }
        )
    return {
        "mother": {
            "path": str(mother_path),
            "streamline_count": total,
            "sha256": file_sha256(mother_path),
            "size_bytes": mother_path.stat().st_size,
        },
        "targets": targets,
    }


def run_seedwide(
    *,
    config: BatchConfig,
    subject_id: str,
    seed: SeedSpec,
    preparation: Mapping[str, Any],
    tools: Mapping[str, ToolIdentity],
    code_hash: str,
    work_root: Path,
    memory_observer: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Generate or resume one subject-side seed-wide target-coverage unit."""

    seed_record = preparation["rois"]["seeds"][seed.key]
    identity, identity_document = seedwide_identity(
        config,
        subject_id,
        preparation,
        seed,
        seed_record,
        tools,
        code_hash,
    )
    seed_work = work_root / "seedwide" / seed.side / seed.roi_id / identity
    state_path = seed_work / "seed_state.json"
    state = read_json(state_path, default={})
    if not isinstance(state, dict) or state.get("seedwide_identity") != identity:
        state = {
            "status": "running",
            "subject_id": subject_id,
            "seed_key": seed.key,
            "seedwide_identity": identity,
            "identity_document": identity_document,
            "chunks": [],
            "total_streamlines": 0,
            "target_hit_counts": [0] * len(seed.targets),
        }
    if _verify_outputs(state, len(seed.targets), tools["tckinfo"].executable):
        state["action"] = "reused"
        return state

    target_ids = [target["key"] for target in seed_record["targets"]]
    target_paths = [Path(target["path"]) for target in seed_record["targets"]]
    lookup = build_target_lookup(target_ids, target_paths)
    valid_chunks: list[dict[str, Any]] = []
    total = 0
    cumulative = np.zeros(len(seed.targets), dtype=np.int64)
    generation_limit = (
        config.tracking.seedwide_streamlines
        if config.tracking.seedwide_streamlines is not None
        else config.execution.maximum_seedwide_streamlines
    )
    for index, record in enumerate(state.get("chunks", [])):
        requested = int(record.get("requested_streamlines", 0))
        expected_request = next_chunk_request(
            total,
            config.execution.generation_chunk_streamlines,
            generation_limit,
        )
        if requested != expected_request or expected_request <= 0:
            break
        rng_seed = derive_chunk_rng_seed(
            config.tracking.random_seed,
            identity,
            subject_id,
            seed.key,
            index,
        )
        expected_identity = _chunk_identity(identity, index, requested, rng_seed)
        if not _verify_chunk(
            record,
            expected_identity,
            len(seed.targets),
            tools["tckinfo"].executable,
        ):
            break
        valid_chunks.append(dict(record))
        total += int(record["actual_streamlines"])
        cumulative += np.asarray(record["target_hit_counts"], dtype=np.int64)
        if generation_complete(
            total,
            cumulative.tolist(),
            config.tracking.minimum_streamlines_per_target,
            config.tracking.seedwide_streamlines,
        ):
            break
    state["chunks"] = valid_chunks
    state["total_streamlines"] = total
    state["target_hit_counts"] = [int(value) for value in cumulative]
    state["status"] = "running"
    state.pop("coverage_failed", None)
    atomic_write_json(state_path, state)

    while not generation_complete(
        total,
        cumulative.tolist(),
        config.tracking.minimum_streamlines_per_target,
        config.tracking.seedwide_streamlines,
    ):
        requested = next_chunk_request(
            total,
            config.execution.generation_chunk_streamlines,
            generation_limit,
        )
        if requested <= 0:
            break
        index = len(valid_chunks)
        rng_seed = derive_chunk_rng_seed(
            config.tracking.random_seed,
            identity,
            subject_id,
            seed.key,
            index,
        )
        record = _generate_chunk(
            config=config,
            subject_id=subject_id,
            seed=seed,
            identity=identity,
            index=index,
            requested=requested,
            rng_seed=rng_seed,
            seed_record=seed_record,
            preparation=preparation,
            target_lookup=lookup,
            seed_work=seed_work,
            tools=tools,
            memory_observer=memory_observer,
        )
        valid_chunks.append(record)
        total += int(record["actual_streamlines"])
        cumulative += np.asarray(record["target_hit_counts"], dtype=np.int64)
        state["chunks"] = valid_chunks
        state["total_streamlines"] = total
        state["target_hit_counts"] = [int(value) for value in cumulative]
        state["minimum_target_streamlines"] = int(np.min(cumulative))
        atomic_write_json(state_path, state)

    if not coverage_complete(
        cumulative.tolist(), config.tracking.minimum_streamlines_per_target
    ):
        deficient = [
            {
                "target": seed_record["targets"][index]["key"],
                "actual_streamlines": int(value),
                "required_streamlines": config.tracking.minimum_streamlines_per_target,
            }
            for index, value in enumerate(cumulative)
            if value < config.tracking.minimum_streamlines_per_target
        ]
        state["status"] = "coverage_failed"
        state["coverage_failed"] = deficient
        state["total_streamlines"] = total
        state["minimum_target_streamlines"] = int(np.min(cumulative))
        atomic_write_json(state_path, state)
        mode = (
            f"fixed total {config.tracking.seedwide_streamlines}"
            if config.tracking.seedwide_streamlines is not None
            else f"maximum {config.execution.maximum_seedwide_streamlines}"
        )
        raise CoverageError(
            f"{subject_id} {seed.key} reached {mode} with {total} seed-wide "
            f"streamlines without covering all targets: {json.dumps(deficient)}"
        )

    state["outputs"] = _build_outputs(state, seed_record, seed_work, tools)
    state["status"] = "staged_complete"
    state["action"] = "generated"
    state["minimum_target_streamlines"] = int(np.min(cumulative))
    atomic_write_json(state_path, state)
    return state
