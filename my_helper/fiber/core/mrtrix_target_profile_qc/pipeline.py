"""Validation, analysis, publication, and status orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
import uuid

import yaml

from my_helper.fiber.core.mrtrix_seed_target.identity import (
    canonical_hash,
    file_sha256,
)

from .analysis import analyze
from .config import load_config
from .errors import PublicationError
from .models import QcConfig, QcValidation
from .reporting import write_analysis_outputs
from .validation import validate_inputs


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _fingerprint_document(validation: QcValidation) -> dict[str, Any]:
    return {
        "identity_version": 1,
        "qc_configuration": _json_safe(validation.config.resolved_mapping),
        "tracking_configuration_hash": validation.tracking.config.configuration_hash,
        "tracking_code_hash": validation.tracking.tracking_code_hash,
        "qc_implementation_hash": validation.implementation_hash,
        "inputs": [
            {
                "subject_id": record.subject_id,
                "seed_key": record.seed.key,
                "preparation_identity": record.preparation_identity,
                "seedwide_identity": record.seedwide_identity,
                "seed_state_sha256": record.state_hash,
            }
            for record in validation.records
        ],
    }


def _fingerprint(validation: QcValidation) -> tuple[str, dict[str, Any]]:
    document = _fingerprint_document(validation)
    return canonical_hash(document), document


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _artifact_records(directory: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name == "manifest.json":
            continue
        relative = path.relative_to(directory)
        if any(part.startswith("._") for part in relative.parts):
            continue
        artifacts.append(
            {
                "path": str(relative),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return artifacts


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _verify_output(directory: Path, expected_fingerprint: str | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    manifest_path = directory / "manifest.json"
    manifest = _read_json(manifest_path)
    if manifest is None:
        return False, [f"missing or invalid manifest: {manifest_path}"]
    if expected_fingerprint is not None and manifest.get("run_fingerprint") != expected_fingerprint:
        errors.append("run fingerprint differs from current inputs")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("manifest artifacts must be a list")
        return False, errors
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            errors.append("invalid artifact record")
            continue
        path = directory / str(artifact.get("path", ""))
        if not path.is_file():
            errors.append(f"missing artifact: {path}")
            continue
        if path.stat().st_size != int(artifact.get("size_bytes", -1)):
            errors.append(f"artifact size mismatch: {path}")
            continue
        if file_sha256(path) != artifact.get("sha256"):
            errors.append(f"artifact hash mismatch: {path}")
    return not errors, errors


def validate_qc(path: Path | str) -> QcValidation:
    """Validate one complete QC analysis without creating output."""

    return validate_inputs(load_config(path))


def _publish_stage(stage: Path, final: Path) -> Path | None:
    backup: Path | None = None
    if final.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = final.with_name(f"{final.name}.backup-{timestamp}-{uuid.uuid4().hex[:8]}")
        os.replace(final, backup)
    try:
        os.replace(stage, final)
    except Exception as exc:
        if backup is not None and backup.exists() and not final.exists():
            os.replace(backup, final)
        raise PublicationError(f"cannot atomically publish QC output: {exc}") from exc
    return backup


def run_qc(path: Path | str) -> dict[str, Any]:
    """Validate, analyze, and atomically publish one QC run."""

    validation = validate_qc(path)
    fingerprint, fingerprint_document = _fingerprint(validation)
    final = validation.config.output_directory
    if final.is_dir():
        valid, errors = _verify_output(final, fingerprint)
        if valid:
            recommendations = final / "inclusion_recommendation.csv"
            return {
                "status": "complete",
                "action": "reused",
                "run_fingerprint": fingerprint,
                "output_directory": str(final),
                "recommendations": str(recommendations),
                "warnings": list(validation.warnings),
            }
        if errors == ["run fingerprint differs from current inputs"]:
            pass

    validation.config.output_root.mkdir(parents=True, exist_ok=True)
    stage = validation.config.output_root / (
        f"{validation.config.run_name}.staging-{uuid.uuid4().hex}"
    )
    if stage.exists():
        raise PublicationError(f"staging path unexpectedly exists: {stage}")
    backup: Path | None = None
    try:
        result = analyze(validation)
        write_analysis_outputs(result, validation, stage)
        resolved = _json_safe(validation.config.resolved_mapping)
        (stage / "config_resolved.yaml").write_text(
            yaml.safe_dump(resolved, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        provenance = {
            "schema_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_fingerprint": fingerprint,
            "fingerprint_document": fingerprint_document,
            "qc_configuration_path": str(validation.config.source_path),
            "tracking_configuration_path": str(validation.config.tracking_config),
            "warnings": list(validation.warnings),
        }
        _write_json(stage / "provenance.json", provenance)
        recommendation_counts = (
            result.recommendations["recommendation"].value_counts().to_dict()
        )
        manifest = {
            "schema_version": 1,
            "status": "complete",
            "run_fingerprint": fingerprint,
            "subject_count": len(validation.tracking.subjects),
            "seed_profile_count": len(validation.records),
            "target_observation_count": len(result.profiles),
            "recommendation_counts": {
                str(key): int(value) for key, value in recommendation_counts.items()
            },
            "artifacts": _artifact_records(stage),
        }
        _write_json(stage / "manifest.json", manifest)
        valid, errors = _verify_output(stage, fingerprint)
        if not valid:
            raise PublicationError("staged QC output failed verification: " + "; ".join(errors))
        backup = _publish_stage(stage, final)
        valid, errors = _verify_output(final, fingerprint)
        if not valid:
            raise PublicationError("published QC output failed verification: " + "; ".join(errors))
        return {
            "status": "complete",
            "action": "generated",
            "run_fingerprint": fingerprint,
            "output_directory": str(final),
            "backup_directory": str(backup) if backup is not None else None,
            "recommendation_counts": manifest["recommendation_counts"],
            "warnings": list(validation.warnings),
        }
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def status_qc(path: Path | str) -> dict[str, Any]:
    """Verify the current output and compare it with exact current inputs."""

    config: QcConfig = load_config(path)
    final = config.output_directory
    if not final.is_dir():
        return {
            "status": "not_run",
            "output_directory": str(final),
        }
    validation = validate_inputs(config)
    fingerprint, _ = _fingerprint(validation)
    valid, errors = _verify_output(final, fingerprint)
    manifest = _read_json(final / "manifest.json") or {}
    return {
        "status": "complete" if valid else "incomplete",
        "output_directory": str(final),
        "run_fingerprint": manifest.get("run_fingerprint"),
        "current_fingerprint": fingerprint,
        "recommendation_counts": manifest.get("recommendation_counts", {}),
        "artifact_count": len(manifest.get("artifacts", [])),
        "errors": errors,
        "warnings": list(validation.warnings),
    }
