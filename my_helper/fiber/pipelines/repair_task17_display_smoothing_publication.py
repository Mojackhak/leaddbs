#!/usr/bin/env python3
"""Stage, validate, and promote Task 17 direct-voxel display smoothing."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

import nibabel as nib
import numpy as np

CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.application.publication import (
    _json_bytes,
    _masked_normalized_gaussian_original_roi,
)


_SCHEMA = "task17_display_smoothing_publication_repair_stage_v1"
_TRANSACTION_SCHEMA = "task17_display_smoothing_promotion_v1"
_ALGORITHM = "masked_normalized_gaussian_original_roi_v2"
_SUPPORT_POLICY = "original_finite_benefit_roi"
_INDEX_NAME = "artifact_index.csv"
_MANIFEST_NAME = "model_manifest.json"
_MAINTENANCE_NAME = ".model_manifest.json.display-smoothing-repair"
_REPAIR_NAME = "repair_manifest.json"
_TRANSACTION_NAME = "promotion_transaction.json"


class DisplaySmoothingRepairError(RuntimeError):
    """Raised when a display-smoothing repair cannot proceed safely."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisplaySmoothingRepairError(f"cannot read JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise DisplaySmoothingRepairError(f"JSON payload must be an object: {path}")
    return payload


def _write_new_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise DisplaySmoothingRepairError(f"refusing to overwrite staged file: {path}") from exc


def _read_index(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = tuple(reader.fieldnames or ())
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DisplaySmoothingRepairError(f"cannot read artifact index: {path}") from exc
    required = {
        "relative_path",
        "sha256",
        "size_bytes",
        "status",
    }
    if not required.issubset(fields):
        raise DisplaySmoothingRepairError(f"artifact index fields are incomplete: {path}")
    paths = [row["relative_path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise DisplaySmoothingRepairError(f"artifact index paths are not unique: {path}")
    return fields, rows


def _index_bytes(fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=tuple(fields), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(dict(row) for row in rows)
    return stream.getvalue().encode("utf-8")


def _safe_relative(value: object) -> str:
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise DisplaySmoothingRepairError(f"unsafe publication path: {value!r}")
    return relative.as_posix()


def _indexed_rows(root: Path) -> tuple[tuple[str, ...], list[dict[str, str]], dict[str, dict[str, str]]]:
    fields, rows = _read_index(root / _INDEX_NAME)
    by_path = {row["relative_path"]: row for row in rows}
    return fields, rows, by_path


def _verify_indexed_file(
    root: Path,
    relative: str,
    row: Mapping[str, str],
) -> Path:
    relative = _safe_relative(relative)
    if row.get("status") != "completed":
        raise DisplaySmoothingRepairError(f"artifact index row is not completed: {relative}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise DisplaySmoothingRepairError(f"indexed artifact is missing or unsafe: {path}")
    try:
        expected_size = int(row["size_bytes"])
    except (TypeError, ValueError) as exc:
        raise DisplaySmoothingRepairError(f"invalid indexed byte count: {relative}") from exc
    if path.stat().st_size != expected_size:
        raise DisplaySmoothingRepairError(f"indexed byte count differs: {relative}")
    if _sha256_file(path) != row["sha256"]:
        raise DisplaySmoothingRepairError(f"indexed SHA-256 differs: {relative}")
    return path


def _selected_models(root: Path) -> list[tuple[Path, dict[str, Any], str]]:
    selected: list[tuple[Path, dict[str, Any], str]] = []
    for final_path in sorted(root.rglob("final_model.json")):
        payload = _json_object(final_path)
        artifact_paths = payload.get("artifact_relative_paths")
        if not isinstance(artifact_paths, list):
            raise DisplaySmoothingRepairError(
                f"final model lacks artifact paths: {final_path}"
            )
        raw = [
            _safe_relative(value)
            for value in artifact_paths
            if str(value).endswith("/benefit_map.nii.gz")
        ]
        if len(raw) != 1:
            raise DisplaySmoothingRepairError(
                f"final model must select exactly one benefit map: {final_path}"
            )
        scale = str(payload.get("scale_id", "")).strip()
        role = str(payload.get("model_family", "")).strip()
        if not scale or role not in {"reference", "addon"}:
            raise DisplaySmoothingRepairError(
                f"final model display identity is invalid: {final_path}"
            )
        selected.append((final_path, payload, raw[0]))
    if not selected:
        raise DisplaySmoothingRepairError("publication contains no selected final models")
    identities = {
        (str(payload["scale_id"]), str(payload["model_family"]))
        for _, payload, _ in selected
    }
    if len(identities) != len(selected):
        raise DisplaySmoothingRepairError("selected final model identities are duplicated")
    return selected


def _smooth_image(raw_image: nib.spatialimages.SpatialImage, fwhm: float) -> tuple[nib.Nifti1Image, int]:
    raw = np.asarray(raw_image.get_fdata(dtype=np.float32), dtype=np.float32)
    finite = np.isfinite(raw)
    coordinates = np.column_stack(np.nonzero(finite))
    if not coordinates.size:
        raise DisplaySmoothingRepairError("selected raw benefit map has empty support")
    lower = coordinates.min(axis=0)
    upper = coordinates.max(axis=0) + 1
    zooms = np.asarray(raw_image.header.get_zooms()[:3], dtype=float)
    if zooms.shape != (3,) or not np.all(np.isfinite(zooms)) or np.any(zooms <= 0.0):
        raise DisplaySmoothingRepairError("selected raw benefit map has invalid voxel sizes")
    sigma = float(fwhm) / 2.354820045 / zooms
    pad = np.ceil(4.0 * sigma).astype(int)
    crop_lower = np.maximum(lower - pad, 0)
    crop_upper = np.minimum(upper + pad, raw_image.shape)
    crop_shape = tuple((crop_upper - crop_lower).tolist())
    local_values = np.zeros(crop_shape, dtype=np.float32)
    local_mask = np.zeros(crop_shape, dtype=np.float32)
    selected_coordinates = coordinates - crop_lower
    local_values[tuple(selected_coordinates.T)] = raw[finite]
    local_mask[tuple(selected_coordinates.T)] = 1.0
    local_smoothed = _masked_normalized_gaussian_original_roi(
        local_values,
        local_mask,
        sigma,
    )
    volume = np.full(raw_image.shape, np.nan, dtype=np.float32)
    slices = tuple(
        slice(int(crop_lower[axis]), int(crop_upper[axis]))
        for axis in range(3)
    )
    volume[slices] = local_smoothed
    image = nib.Nifti1Image(volume, raw_image.affine, raw_image.header)
    image.set_data_dtype(np.float32)
    output_support = int(np.count_nonzero(np.isfinite(volume)))
    input_support = int(np.count_nonzero(finite))
    if output_support != input_support or not np.array_equal(np.isfinite(volume), finite):
        raise DisplaySmoothingRepairError("v2 smoothing changed the selected raw support")
    return image, input_support


def _metadata(
    *,
    relative: str,
    digest: str,
    size_bytes: int,
    source_record_id: str,
    input_relative_path: str,
    fwhm: float,
    finite_voxels: int,
) -> dict[str, Any]:
    return {
        "schema_version": "dual_frequency_derived_artifact_metadata_v1",
        "artifact_kind": "benefit_map_smooth",
        "published_relative_path": relative,
        "payload_sha256": digest,
        "size_bytes": size_bytes,
        "provenance": {
            "source_record_id": source_record_id,
            "input_relative_path": input_relative_path,
            "fwhm_mm": fwhm,
            "algorithm": _ALGORITHM,
            "support_policy": _SUPPORT_POLICY,
            "input_finite_voxels": finite_voxels,
            "output_finite_voxels": finite_voxels,
        },
    }


def stage(publication_root: Path, stage_root: Path) -> dict[str, Any]:
    """Create one deterministic local repair stage from canonical raw maps."""

    publication_root = Path(publication_root).expanduser().resolve()
    stage_root = Path(stage_root).expanduser()
    if stage_root.exists():
        raise DisplaySmoothingRepairError(f"stage root already exists: {stage_root}")
    stage_root.mkdir(parents=True)
    stage_root = stage_root.resolve()
    fields, rows, by_path = _indexed_rows(publication_root)
    source_index_sha = _sha256_file(publication_root / _INDEX_NAME)
    replacements: dict[str, tuple[str, str]] = {}
    records: list[dict[str, Any]] = []
    try:
        for _, final, raw_relative in _selected_models(publication_root):
            raw_row = by_path.get(raw_relative)
            if raw_row is None:
                raise DisplaySmoothingRepairError(
                    f"selected raw map is absent from artifact index: {raw_relative}"
                )
            raw_path = _verify_indexed_file(publication_root, raw_relative, raw_row)
            raw_image = nib.load(str(raw_path))
            scale = str(final["scale_id"])
            role = str(final["model_family"])
            base = Path(scale) / role / "report" / "display"
            for fwhm in (1.0, 2.0):
                name = f"benefit_map_smooth_fwhm{int(fwhm)}mm.nii.gz"
                relative = (base / name).as_posix()
                old_row = by_path.get(relative)
                if old_row is None:
                    raise DisplaySmoothingRepairError(
                        f"display derivative is absent from artifact index: {relative}"
                    )
                old_path = _verify_indexed_file(publication_root, relative, old_row)
                old_metadata_path = Path(f"{old_path}.metadata.json")
                old_metadata = _json_object(old_metadata_path)
                provenance = old_metadata.get("provenance")
                if not isinstance(provenance, dict):
                    raise DisplaySmoothingRepairError(
                        f"display derivative metadata lacks provenance: {old_metadata_path}"
                    )
                source_record_id = str(provenance.get("source_record_id", "")).strip()
                if not source_record_id:
                    raise DisplaySmoothingRepairError(
                        f"display derivative metadata lacks source identity: {old_metadata_path}"
                    )
                image, finite_voxels = _smooth_image(raw_image, fwhm)
                output = stage_root / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                nib.save(image, output)
                digest = _sha256_file(output)
                size_bytes = output.stat().st_size
                metadata = _metadata(
                    relative=relative,
                    digest=digest,
                    size_bytes=size_bytes,
                    source_record_id=source_record_id,
                    input_relative_path=raw_relative,
                    fwhm=fwhm,
                    finite_voxels=finite_voxels,
                )
                metadata_path = Path(f"{output}.metadata.json")
                _write_new_bytes(metadata_path, _json_bytes(metadata))
                old_digest = str(old_row["sha256"])
                records.append(
                    {
                        "relative_path": relative,
                        "old_sha256": old_digest,
                        "new_sha256": digest,
                        "old_algorithm": provenance.get("algorithm"),
                        "byte_changed": old_digest != digest,
                        "finite_support_preserved": True,
                        "size_bytes": size_bytes,
                        "metadata_sha256": _sha256_file(metadata_path),
                    }
                )
                replacements[relative] = (digest, str(size_bytes))
        candidate_rows = [dict(row) for row in rows]
        seen: set[str] = set()
        for row in candidate_rows:
            replacement = replacements.get(row["relative_path"])
            if replacement is not None:
                row["sha256"], row["size_bytes"] = replacement
                seen.add(row["relative_path"])
        if seen != set(replacements):
            raise DisplaySmoothingRepairError("candidate index missed staged derivatives")
        candidate_index = stage_root / _INDEX_NAME
        _write_new_bytes(candidate_index, _index_bytes(fields, candidate_rows))
        manifest = {
            "schema_version": _SCHEMA,
            "canonical_root": str(publication_root),
            "source_artifact_index_sha256": source_index_sha,
            "staged_artifact_index_sha256": _sha256_file(candidate_index),
            "selected_final_model_count": len(_selected_models(publication_root)),
            "staged_nifti_count": len(records),
            "changed_nifti_count": sum(int(item["byte_changed"]) for item in records),
            "unchanged_nifti_count": sum(
                int(not item["byte_changed"]) for item in records
            ),
            "support_preserved_count": sum(
                int(item["finite_support_preserved"]) for item in records
            ),
            "index_replacement_count": len(seen),
            "records": records,
        }
        _write_new_bytes(stage_root / _REPAIR_NAME, _json_bytes(manifest))
        return {
            "status": "staged",
            "publication_root": str(publication_root),
            "stage_root": str(stage_root),
            "repair_manifest_sha256": _sha256_file(stage_root / _REPAIR_NAME),
            "staged_nifti_count": len(records),
            "changed_nifti_count": manifest["changed_nifti_count"],
        }
    except BaseException:
        raise


def _load_repair_manifest(
    publication_root: Path,
    stage_root: Path,
) -> dict[str, Any]:
    manifest = _json_object(stage_root / _REPAIR_NAME)
    if manifest.get("schema_version") != _SCHEMA:
        raise DisplaySmoothingRepairError("repair manifest schema differs")
    if Path(str(manifest.get("canonical_root", ""))).resolve() != publication_root:
        raise DisplaySmoothingRepairError("repair manifest canonical root differs")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise DisplaySmoothingRepairError("repair manifest records are empty")
    if not all(isinstance(item, dict) for item in records):
        raise DisplaySmoothingRepairError("repair manifest records are invalid")
    paths = [_safe_relative(item.get("relative_path")) for item in records]
    if len(paths) != len(records) or len(paths) != len(set(paths)):
        raise DisplaySmoothingRepairError("repair manifest paths are invalid")
    for item in records:
        old_sha = str(item.get("old_sha256", ""))
        new_sha = str(item.get("new_sha256", ""))
        metadata_sha = str(item.get("metadata_sha256", ""))
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in (old_sha, new_sha, metadata_sha)
        ):
            raise DisplaySmoothingRepairError("repair manifest SHA-256 value is invalid")
        if type(item.get("byte_changed")) is not bool or bool(
            item["byte_changed"]
        ) != (old_sha != new_sha):
            raise DisplaySmoothingRepairError("repair manifest byte-change flag differs")
        if item.get("finite_support_preserved") is not True:
            raise DisplaySmoothingRepairError("repair manifest support verdict differs")
        try:
            size_bytes = int(item["size_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DisplaySmoothingRepairError(
                "repair manifest byte count is invalid"
            ) from exc
        if size_bytes < 1:
            raise DisplaySmoothingRepairError("repair manifest byte count is invalid")
    expected_counts = {
        "staged_nifti_count": len(records),
        "changed_nifti_count": sum(int(item["byte_changed"]) for item in records),
        "unchanged_nifti_count": sum(
            int(not item["byte_changed"]) for item in records
        ),
        "support_preserved_count": len(records),
        "index_replacement_count": len(records),
    }
    for field, expected in expected_counts.items():
        if manifest.get(field) != expected:
            raise DisplaySmoothingRepairError(
                f"repair manifest {field} differs from its records"
            )
    return manifest


def _validate_candidate_index(
    publication_root: Path,
    stage_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], set[str]]:
    old_fields, old_rows = _read_index(publication_root / _INDEX_NAME)
    new_fields, new_rows = _read_index(stage_root / _INDEX_NAME)
    if old_fields != new_fields or len(old_rows) != len(new_rows):
        raise DisplaySmoothingRepairError("candidate artifact index shape differs")
    old_by = {row["relative_path"]: row for row in old_rows}
    new_by = {row["relative_path"]: row for row in new_rows}
    if set(old_by) != set(new_by):
        raise DisplaySmoothingRepairError("candidate artifact index path closure differs")
    targets = {
        _safe_relative(item["relative_path"])
        for item in manifest["records"]
    }
    records_by_path = {
        _safe_relative(item["relative_path"]): item
        for item in manifest["records"]
    }
    current_index_sha = _sha256_file(publication_root / _INDEX_NAME)
    source_state = current_index_sha == manifest.get(
        "source_artifact_index_sha256"
    )
    for relative, record in records_by_path.items():
        candidate = new_by.get(relative)
        if (
            candidate is None
            or candidate.get("sha256") != record["new_sha256"]
            or candidate.get("size_bytes") != str(record["size_bytes"])
            or candidate.get("status") != "completed"
        ):
            raise DisplaySmoothingRepairError(
                f"candidate artifact index target differs: {relative}"
            )
        if source_state and old_by[relative].get("sha256") != record["old_sha256"]:
            raise DisplaySmoothingRepairError(
                f"source artifact index target differs: {relative}"
            )
    for relative, old in old_by.items():
        new = new_by[relative]
        if old == new:
            continue
        allowed = dict(old)
        allowed["sha256"] = new["sha256"]
        allowed["size_bytes"] = new["size_bytes"]
        if relative not in targets or allowed != new:
            raise DisplaySmoothingRepairError(
                f"candidate artifact index changes a forbidden field: {relative}"
            )
    if _sha256_file(stage_root / _INDEX_NAME) != manifest.get(
        "staged_artifact_index_sha256"
    ):
        raise DisplaySmoothingRepairError("candidate artifact index SHA-256 differs")
    return old_rows, new_rows, targets


def _validate_staged_files(
    publication_root: Path,
    stage_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    by_path = _indexed_rows(publication_root)[2]
    selected = {
        (str(payload["scale_id"]), str(payload["model_family"])): raw
        for _, payload, raw in _selected_models(publication_root)
    }
    for record in manifest["records"]:
        relative = _safe_relative(record["relative_path"])
        output = stage_root / relative
        metadata_path = Path(f"{output}.metadata.json")
        if not output.is_file() or output.is_symlink():
            raise DisplaySmoothingRepairError(f"staged payload is missing: {relative}")
        if _sha256_file(output) != record.get("new_sha256"):
            raise DisplaySmoothingRepairError(f"staged payload SHA-256 differs: {relative}")
        if output.stat().st_size != int(record.get("size_bytes", -1)):
            raise DisplaySmoothingRepairError(f"staged payload byte count differs: {relative}")
        if not metadata_path.is_file() or metadata_path.is_symlink():
            raise DisplaySmoothingRepairError(f"staged metadata is missing: {relative}")
        if _sha256_file(metadata_path) != record.get("metadata_sha256"):
            raise DisplaySmoothingRepairError(f"staged metadata SHA-256 differs: {relative}")
        metadata = _json_object(metadata_path)
        provenance = metadata.get("provenance")
        if (
            metadata.get("published_relative_path") != relative
            or metadata.get("payload_sha256") != record.get("new_sha256")
            or metadata.get("size_bytes") != int(record.get("size_bytes", -1))
            or not isinstance(provenance, dict)
            or provenance.get("algorithm") != _ALGORITHM
            or provenance.get("support_policy") != _SUPPORT_POLICY
            or provenance.get("input_finite_voxels")
            != provenance.get("output_finite_voxels")
        ):
            raise DisplaySmoothingRepairError(f"staged metadata contract differs: {relative}")
        parts = Path(relative).parts
        if len(parts) < 5:
            raise DisplaySmoothingRepairError(f"staged display path is invalid: {relative}")
        identity = (parts[0], parts[1])
        raw_relative = selected.get(identity)
        if raw_relative is None or provenance.get("input_relative_path") != raw_relative:
            raise DisplaySmoothingRepairError(f"staged raw-map binding differs: {relative}")
        raw_row = by_path.get(raw_relative)
        if raw_row is None:
            raise DisplaySmoothingRepairError(f"staged raw map is not indexed: {relative}")
        raw = np.isfinite(
            np.asanyarray(
                nib.load(str(_verify_indexed_file(publication_root, raw_relative, raw_row))).dataobj
            )
        )
        staged = np.isfinite(np.asanyarray(nib.load(str(output)).dataobj))
        if not np.array_equal(raw, staged):
            raise DisplaySmoothingRepairError(f"staged finite support differs: {relative}")


def validate(publication_root: Path, stage_root: Path) -> dict[str, Any]:
    """Validate a staged or fully promoted repair closure."""

    publication_root = Path(publication_root).expanduser().resolve()
    stage_root = Path(stage_root).expanduser().resolve()
    manifest = _load_repair_manifest(publication_root, stage_root)
    _validate_staged_files(publication_root, stage_root, manifest)
    _, candidate_rows, targets = _validate_candidate_index(
        publication_root,
        stage_root,
        manifest,
    )
    current_index_sha = _sha256_file(publication_root / _INDEX_NAME)
    source_sha = str(manifest["source_artifact_index_sha256"])
    staged_sha = str(manifest["staged_artifact_index_sha256"])
    if current_index_sha == source_sha:
        state = "staged"
    elif current_index_sha == staged_sha:
        state = "promoted"
    else:
        raise DisplaySmoothingRepairError("canonical artifact index changed unexpectedly")
    if state == "promoted":
        candidate_by = {row["relative_path"]: row for row in candidate_rows}
        for record in manifest["records"]:
            relative = _safe_relative(record["relative_path"])
            row = candidate_by[relative]
            _verify_indexed_file(publication_root, relative, row)
            metadata = Path(f"{publication_root / relative}.metadata.json")
            if _sha256_file(metadata) != record["metadata_sha256"]:
                raise DisplaySmoothingRepairError(
                    f"promoted metadata SHA-256 differs: {relative}"
                )
        model_manifest = _json_object(publication_root / _MANIFEST_NAME)
        if model_manifest.get("final_status") != "completed":
            raise DisplaySmoothingRepairError("promoted model manifest is not completed")
    return {
        "status": "validated",
        "state": state,
        "publication_root": str(publication_root),
        "stage_root": str(stage_root),
        "repair_manifest_sha256": _sha256_file(stage_root / _REPAIR_NAME),
        "target_count": len(targets),
        "changed_nifti_count": int(manifest["changed_nifti_count"]),
    }


def _copy_to_temporary_sibling(source: Path, target: Path, expected_sha: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".repair.tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output:
            shutil.copyfileobj(input_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if _sha256_file(temporary) != expected_sha:
            raise DisplaySmoothingRepairError(f"temporary copy SHA-256 differs: {target}")
        return temporary
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _archive_and_install(
    *,
    source: Path,
    target: Path,
    archive: Path,
    new_sha: str,
    old_sha: str | None,
) -> None:
    if target.is_file() and _sha256_file(target) == new_sha:
        return
    temporary = _copy_to_temporary_sibling(source, target, new_sha)
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise DisplaySmoothingRepairError(f"canonical target is unsafe: {target}")
            current_sha = _sha256_file(target)
            if old_sha is not None and current_sha != old_sha:
                raise DisplaySmoothingRepairError(f"canonical target changed: {target}")
            if archive.exists():
                if not archive.is_file() or _sha256_file(archive) != current_sha:
                    raise DisplaySmoothingRepairError(f"Trash archive differs: {archive}")
                target.unlink()
            else:
                os.replace(target, archive)
        elif not archive.is_file():
            raise DisplaySmoothingRepairError(
                f"canonical target and Trash archive are both missing: {target}"
            )
        os.replace(temporary, target)
        if _sha256_file(target) != new_sha:
            raise DisplaySmoothingRepairError(f"installed target SHA-256 differs: {target}")
    finally:
        temporary.unlink(missing_ok=True)


def _old_metadata_is_acceptable(path: Path, record: Mapping[str, Any]) -> str:
    payload = _json_object(path)
    provenance = payload.get("provenance")
    if (
        payload.get("published_relative_path") != record["relative_path"]
        or payload.get("payload_sha256") != record["old_sha256"]
        or not isinstance(provenance, dict)
        or provenance.get("algorithm") != record.get("old_algorithm")
    ):
        raise DisplaySmoothingRepairError(f"canonical metadata changed: {path}")
    return _sha256_file(path)


def _validate_trash_root(publication_root: Path, trash_root: Path) -> None:
    parts = trash_root.parts
    expected = (".Trashes", str(os.getuid()))
    if not any(parts[index : index + 2] == expected for index in range(len(parts) - 1)):
        raise DisplaySmoothingRepairError(
            "promotion Trash root must be below .Trashes for the current user"
        )
    anchor = trash_root
    while not anchor.exists():
        if anchor.parent == anchor:
            raise DisplaySmoothingRepairError("promotion Trash root has no existing parent")
        anchor = anchor.parent
    if os.stat(anchor).st_dev != os.stat(publication_root).st_dev:
        raise DisplaySmoothingRepairError("promotion Trash root is not on the publication volume")


def promote(publication_root: Path, stage_root: Path, trash_root: Path) -> dict[str, Any]:
    """Promote one validated stage while preserving fail-closed recovery."""

    publication_root = Path(publication_root).expanduser().resolve()
    stage_root = Path(stage_root).expanduser().resolve()
    trash_root = Path(trash_root).expanduser()
    _validate_trash_root(publication_root, trash_root)
    manifest = _load_repair_manifest(publication_root, stage_root)
    repair_sha = _sha256_file(stage_root / _REPAIR_NAME)
    source_index_sha = str(manifest["source_artifact_index_sha256"])
    staged_index_sha = str(manifest["staged_artifact_index_sha256"])
    model_path = publication_root / _MANIFEST_NAME
    maintenance_path = publication_root / _MAINTENANCE_NAME
    current_index_sha = _sha256_file(publication_root / _INDEX_NAME)
    if (
        current_index_sha == staged_index_sha
        and model_path.is_file()
        and not maintenance_path.exists()
    ):
        result = validate(publication_root, stage_root)
        return {**result, "status": "promoted", "trash_root": str(trash_root.resolve())}
    if current_index_sha not in {source_index_sha, staged_index_sha}:
        raise DisplaySmoothingRepairError("canonical artifact index changed unexpectedly")
    _validate_staged_files(publication_root, stage_root, manifest)
    _validate_candidate_index(publication_root, stage_root, manifest)
    trash_root.mkdir(parents=True, exist_ok=True)
    trash_root = trash_root.resolve()
    _validate_trash_root(publication_root, trash_root)
    transaction_path = trash_root / _TRANSACTION_NAME
    model_sha: str
    if model_path.is_file():
        model_document = _json_object(model_path)
        if model_document.get("final_status") != "completed":
            raise DisplaySmoothingRepairError("canonical model manifest is not completed")
        model_sha = _sha256_file(model_path)
    elif maintenance_path.is_file():
        model_sha = _sha256_file(maintenance_path)
    else:
        raise DisplaySmoothingRepairError("canonical model manifest is unavailable")
    transaction = {
        "schema_version": _TRANSACTION_SCHEMA,
        "publication_root": str(publication_root),
        "stage_root": str(stage_root),
        "repair_manifest_sha256": repair_sha,
        "model_manifest_sha256": model_sha,
        "source_artifact_index_sha256": source_index_sha,
        "staged_artifact_index_sha256": staged_index_sha,
    }
    transaction_bytes = _json_bytes(transaction)
    if transaction_path.exists():
        if transaction_path.read_bytes() != transaction_bytes:
            raise DisplaySmoothingRepairError("existing promotion transaction differs")
    else:
        _write_new_bytes(transaction_path, transaction_bytes)
    archived_model = trash_root / _MANIFEST_NAME
    if model_path.is_file():
        if maintenance_path.exists():
            raise DisplaySmoothingRepairError(
                "canonical and maintenance model manifests both exist"
            )
        if archived_model.exists():
            if _sha256_file(archived_model) != model_sha:
                raise DisplaySmoothingRepairError("archived model manifest differs")
        else:
            temporary_model = _copy_to_temporary_sibling(
                model_path,
                archived_model,
                model_sha,
            )
            try:
                os.replace(temporary_model, archived_model)
            finally:
                temporary_model.unlink(missing_ok=True)
        os.replace(model_path, maintenance_path)
    if _sha256_file(maintenance_path) != model_sha:
        raise DisplaySmoothingRepairError("maintenance model manifest differs")
    try:
        for record in manifest["records"]:
            relative = _safe_relative(record["relative_path"])
            if not bool(record["byte_changed"]):
                target = publication_root / relative
                metadata_target = Path(f"{target}.metadata.json")
                if (
                    _sha256_file(target) != record["new_sha256"]
                    or _sha256_file(metadata_target) != record["metadata_sha256"]
                ):
                    raise DisplaySmoothingRepairError(
                        f"unchanged v2 derivative differs: {relative}"
                    )
                continue
            target = publication_root / relative
            source = stage_root / relative
            archive = trash_root / "canonical" / relative
            _archive_and_install(
                source=source,
                target=target,
                archive=archive,
                new_sha=str(record["new_sha256"]),
                old_sha=str(record["old_sha256"]),
            )
            metadata_target = Path(f"{target}.metadata.json")
            metadata_source = Path(f"{source}.metadata.json")
            metadata_archive = Path(f"{archive}.metadata.json")
            if (
                metadata_target.is_file()
                and _sha256_file(metadata_target) == record["metadata_sha256"]
            ):
                continue
            old_metadata_sha = (
                _old_metadata_is_acceptable(metadata_target, record)
                if metadata_target.is_file()
                else None
            )
            _archive_and_install(
                source=metadata_source,
                target=metadata_target,
                archive=metadata_archive,
                new_sha=str(record["metadata_sha256"]),
                old_sha=old_metadata_sha,
            )
        index_target = publication_root / _INDEX_NAME
        if _sha256_file(index_target) != staged_index_sha:
            index_archive = trash_root / "canonical" / _INDEX_NAME
            _archive_and_install(
                source=stage_root / _INDEX_NAME,
                target=index_target,
                archive=index_archive,
                new_sha=staged_index_sha,
                old_sha=source_index_sha,
            )
        if _sha256_file(index_target) != staged_index_sha:
            raise DisplaySmoothingRepairError("promoted artifact index differs")
        candidate_by = {
            row["relative_path"]: row
            for row in _read_index(stage_root / _INDEX_NAME)[1]
        }
        for record in manifest["records"]:
            relative = _safe_relative(record["relative_path"])
            _verify_indexed_file(publication_root, relative, candidate_by[relative])
            metadata_target = Path(f"{publication_root / relative}.metadata.json")
            if _sha256_file(metadata_target) != record["metadata_sha256"]:
                raise DisplaySmoothingRepairError(
                    f"promoted metadata differs before commit: {relative}"
                )
        os.replace(maintenance_path, model_path)
    except BaseException:
        raise
    result = validate(publication_root, stage_root)
    return {
        **result,
        "status": "promoted",
        "trash_root": str(trash_root),
        "model_manifest_sha256": model_sha,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair Task 17 canonical direct-voxel display smoothing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("stage", "validate", "promote"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--publication-root", type=Path, required=True)
        subparser.add_argument("--stage-root", type=Path, required=True)
        if command == "promote":
            subparser.add_argument("--trash-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "stage":
            result = stage(arguments.publication_root, arguments.stage_root)
        elif arguments.command == "validate":
            result = validate(arguments.publication_root, arguments.stage_root)
        else:
            result = promote(
                arguments.publication_root,
                arguments.stage_root,
                arguments.trash_root,
            )
    except (DisplaySmoothingRepairError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
