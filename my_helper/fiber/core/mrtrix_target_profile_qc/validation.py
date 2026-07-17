"""Read-only exact-identity validation for target-profile QC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import nibabel as nib
import numpy as np

from my_helper.fiber.core.mrtrix_seed_target.identity import (
    file_sha256,
    implementation_hash,
)
from my_helper.fiber.core.mrtrix_seed_target.preparation import preparation_identity
from my_helper.fiber.core.mrtrix_seed_target.state import read_json
from my_helper.fiber.core.mrtrix_seed_target.tck import validate_tck
from my_helper.fiber.core.mrtrix_seed_target.tracking import seedwide_identity
from my_helper.fiber.core.mrtrix_seed_target.validation import validate_config

from .config import PRESET
from .errors import ValidationError
from .models import QcConfig, QcValidation, SeedStateRecord


def _implementation_paths() -> tuple[Path, ...]:
    package = Path(__file__).resolve().parent
    paths = sorted(package.glob("*.py"))
    paths.extend(sorted((package / "schemas").glob("*.json")))
    cli = package.parents[1] / "pipelines" / "mrtrix-target-profile-qc"
    if cli.is_file():
        paths.append(cli)
    return tuple(paths)


def _require_file_hash(path_value: str, expected_hash: str, label: str) -> Path:
    path = Path(path_value)
    if not path.is_file():
        raise ValidationError(f"{label} does not exist: {path}")
    actual = file_sha256(path)
    if actual != expected_hash:
        raise ValidationError(
            f"{label} hash mismatch for {path}: expected {expected_hash}, got {actual}"
        )
    return path


def _verify_preparation(preparation: Mapping[str, Any], expected: str) -> None:
    if preparation.get("status") != "complete":
        raise ValidationError(f"preparation {expected} is not complete")
    if preparation.get("preparation_identity") != expected:
        raise ValidationError(f"preparation manifest identity mismatch: {expected}")
    for key, artifact in preparation.get("artifacts", {}).items():
        if not isinstance(artifact, Mapping):
            raise ValidationError(f"invalid preparation artifact record {key!r}")
        path = Path(str(artifact.get("path", "")))
        if not path.is_file():
            raise ValidationError(f"preparation artifact does not exist: {path}")
        if path.stat().st_size != int(artifact.get("size_bytes", -1)):
            raise ValidationError(f"preparation artifact size mismatch: {path}")


def _load_binary_roi(path: Path, expected_hash: str, label: str) -> tuple[Any, np.ndarray]:
    _require_file_hash(str(path), expected_hash, label)
    try:
        image = nib.load(path)
        data = np.asanyarray(image.dataobj)
    except Exception as exc:
        raise ValidationError(f"cannot read {label} {path}: {exc}") from exc
    if len(image.shape) != 3 or not np.all(np.isfinite(image.affine)):
        raise ValidationError(f"{label} has an invalid NIfTI grid: {path}")
    mask = np.asarray(data > 0, dtype=bool)
    if not np.any(mask):
        raise ValidationError(f"{label} is empty: {path}")
    return image, mask


def _verify_roi_grid(seed_record: Mapping[str, Any]) -> None:
    seed_path = Path(str(seed_record["path"]))
    seed_image, _ = _load_binary_roi(
        seed_path, str(seed_record["hash"]), f"seed {seed_record['key']}"
    )
    for target in seed_record.get("targets", []):
        target_path = Path(str(target["path"]))
        target_image, _ = _load_binary_roi(
            target_path, str(target["hash"]), f"target {target['key']}"
        )
        if target_image.shape != seed_image.shape or not np.allclose(
            target_image.affine,
            seed_image.affine,
            atol=1.0e-5,
            rtol=0,
        ):
            raise ValidationError(
                f"target {target['key']} grid differs from seed {seed_record['key']}"
            )


def _verify_staged_outputs(
    state: Mapping[str, Any],
    expected_target_keys: list[str],
    tckinfo: Path,
) -> None:
    outputs = state.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValidationError("staged_complete state does not contain outputs")
    mother = outputs.get("mother")
    if not isinstance(mother, Mapping):
        raise ValidationError("staged_complete state does not contain mother output")
    mother_path = _require_file_hash(
        str(mother["path"]), str(mother["sha256"]), "seed-wide output"
    )
    validate_tck(
        mother_path,
        tckinfo,
        expected_count=int(state["total_streamlines"]),
    )
    targets = outputs.get("targets")
    if not isinstance(targets, list) or [item.get("key") for item in targets] != expected_target_keys:
        raise ValidationError("staged target output order differs from tracking YAML")
    for target in targets:
        target_path = _require_file_hash(
            str(target["path"]),
            str(target["sha256"]),
            f"target output {target['key']}",
        )
        validate_tck(
            target_path,
            tckinfo,
            expected_count=int(target["streamline_count"]),
        )


def _verify_state(
    state: Mapping[str, Any],
    expected_identity: str,
    expected_target_keys: list[str],
    tckinfo: Path,
) -> None:
    if state.get("seedwide_identity") != expected_identity:
        raise ValidationError(f"seed state identity mismatch: {expected_identity}")
    accepted = set(PRESET["technical_qc"]["accepted_seed_state_statuses"])
    status = str(state.get("status", ""))
    if status not in accepted:
        raise ValidationError(
            f"seed state {expected_identity} has unsupported status {status!r}"
        )
    identity_targets = [
        str(target.get("key"))
        for target in state.get("identity_document", {}).get("targets", [])
    ]
    if identity_targets != expected_target_keys:
        raise ValidationError("seed state target order differs from tracking YAML")
    counts = state.get("target_hit_counts")
    if not isinstance(counts, list) or len(counts) != len(expected_target_keys):
        raise ValidationError("seed state target-hit vector has the wrong length")
    if any(not isinstance(value, int) or value < 0 for value in counts):
        raise ValidationError("seed state target-hit counts must be nonnegative integers")
    total = int(state.get("total_streamlines", -1))
    chunks = state.get("chunks")
    if not isinstance(chunks, list):
        raise ValidationError("seed state does not contain a chunk list")
    if sum(int(chunk.get("actual_streamlines", -1)) for chunk in chunks) != total:
        raise ValidationError("seed state chunk counts do not equal total_streamlines")
    if status == "staged_complete":
        _verify_staged_outputs(state, expected_target_keys, tckinfo)


def validate_inputs(config: QcConfig) -> QcValidation:
    """Resolve every current preparation and seed state by exact identity."""

    if not config.tracking_config.is_file():
        raise ValidationError(
            f"tracking configuration does not exist: {config.tracking_config}"
        )
    try:
        tracking = validate_config(config.tracking_config)
    except Exception as exc:
        raise ValidationError(f"tracking configuration validation failed: {exc}") from exc

    records: list[SeedStateRecord] = []
    warnings = list(tracking.warnings)
    tckinfo = tracking.tools["tckinfo"].executable
    for subject in tracking.subjects:
        prep_identity, _ = preparation_identity(tracking, subject)
        preparation_path = (
            subject.output_root
            / "work"
            / "preparations"
            / prep_identity
            / "prepared_subject.json"
        )
        if not preparation_path.is_file():
            raise ValidationError(
                f"current preparation is missing for {subject.subject_id}: "
                f"{preparation_path}"
            )
        try:
            preparation = read_json(preparation_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError(
                f"cannot read preparation manifest {preparation_path}: {exc}"
            ) from exc
        if not isinstance(preparation, Mapping):
            raise ValidationError(f"invalid preparation manifest: {preparation_path}")
        _verify_preparation(preparation, prep_identity)
        seeds = preparation.get("rois", {}).get("seeds", {})
        for seed in tracking.config.atlas.seeds:
            seed_record = seeds.get(seed.key)
            if not isinstance(seed_record, Mapping):
                raise ValidationError(
                    f"preparation {prep_identity} is missing seed {seed.key}"
                )
            _verify_roi_grid(seed_record)
            identity, _ = seedwide_identity(
                tracking.config,
                subject.subject_id,
                preparation,
                seed,
                seed_record,
                tracking.tools,
                tracking.tracking_code_hash,
            )
            state_path = (
                subject.output_root
                / "work"
                / "seedwide"
                / seed.side
                / seed.roi_id
                / identity
                / "seed_state.json"
            )
            if not state_path.is_file():
                raise ValidationError(
                    f"exact seed state is missing for {subject.subject_id} "
                    f"{seed.key}: {state_path}"
                )
            try:
                state = read_json(state_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ValidationError(f"cannot read seed state {state_path}: {exc}") from exc
            if not isinstance(state, Mapping):
                raise ValidationError(f"invalid seed state: {state_path}")
            target_keys = [target.key for target in seed.targets]
            _verify_state(state, identity, target_keys, tckinfo)
            if state.get("status") == "coverage_failed":
                warnings.append(
                    f"{subject.subject_id} {seed.key} has coverage_failed status"
                )
            records.append(
                SeedStateRecord(
                    subject_id=subject.subject_id,
                    subject_dir=subject.subject_dir,
                    seed=seed,
                    preparation_identity=prep_identity,
                    seedwide_identity=identity,
                    preparation_path=preparation_path,
                    state_path=state_path,
                    state_hash=file_sha256(state_path),
                    preparation=preparation,
                    state=state,
                )
            )

    expected_records = len(tracking.subjects) * len(tracking.config.atlas.seeds)
    if len(records) != expected_records:
        raise ValidationError(
            f"resolved {len(records)} seed states; expected {expected_records}"
        )
    return QcValidation(
        config=config,
        tracking=tracking,
        records=tuple(records),
        implementation_hash=implementation_hash(_implementation_paths()),
        warnings=tuple(warnings),
    )

