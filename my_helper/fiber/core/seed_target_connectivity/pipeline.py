"""Reusable validation and run orchestration for seed-target connectivity."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import (
    collect_code_provenance,
    verify_artifact_index,
    write_run_atomic,
)
from .config import load_config, resolve_config
from .connectome import ConnectomeAdapter, open_connectome
from .engine import compute_memberships
from .errors import ArtifactError, ConfigurationError, ConnectomeError
from .identity import sha256_file
from .models import (
    ConnectivityConfig,
    ConnectivityRunResult,
    ValidationReport,
)
from .roi import resolve_atlas, resolve_seed
from .statistics import compute_statistics


def _resolve_config(config: ConnectivityConfig | Mapping[str, Any] | Path | str) -> ConnectivityConfig:
    if isinstance(config, ConnectivityConfig):
        return config
    if isinstance(config, Mapping):
        return resolve_config(config)
    if isinstance(config, (Path, str)):
        return load_config(config)
    raise ConfigurationError(f"unsupported configuration input type: {type(config).__name__}")


def _resolve_connectome(connectome: ConnectomeAdapter | Path | str) -> ConnectomeAdapter:
    if isinstance(connectome, (Path, str)):
        return open_connectome(connectome)
    if not hasattr(connectome, "metadata") or not callable(getattr(connectome, "iter_chunks", None)):
        raise ConnectomeError(f"unsupported connectome adapter type: {type(connectome).__name__}")
    return connectome


def validate_inputs(
    *,
    target_atlas_root: Path | str,
    seed_roi: Path | str,
    connectome: ConnectomeAdapter | Path | str,
    config: ConnectivityConfig | Mapping[str, Any] | Path | str,
) -> ValidationReport:
    """Resolve all inputs without traversing full connectome geometry."""
    resolved_config = _resolve_config(config)
    resolved_seed = resolve_seed(seed_roi, resolved_config)
    resolved_atlas = resolve_atlas(target_atlas_root, resolved_config)
    adapter = _resolve_connectome(connectome)
    metadata = adapter.metadata
    n_empty = sum(target.status == "empty_after_threshold" for target in resolved_atlas.targets)
    return ValidationReport(
        config=resolved_config,
        seed=resolved_seed,
        atlas=resolved_atlas,
        connectome=adapter,
        connectome_metadata=metadata,
        n_targets=len(resolved_atlas.targets),
        n_valid_targets=len(resolved_atlas.targets) - n_empty,
        n_empty_targets=n_empty,
        seed_voxel_count=resolved_seed.voxel_count,
    )


def compute_seed_target_statistics(
    *,
    target_atlas_root: Path | str,
    seed_roi: Path | str,
    connectome: ConnectomeAdapter | Path | str,
    config: ConnectivityConfig | Mapping[str, Any] | Path | str,
    output_root: Path | str,
    cache_root: Path | str | None = None,
    code_provenance: Mapping[str, Any] | None = None,
) -> ConnectivityRunResult:
    """Compute target-wise statistics and publish one immutable run."""
    validation = validate_inputs(
        target_atlas_root=target_atlas_root,
        seed_roi=seed_roi,
        connectome=connectome,
        config=config,
    )
    output = Path(output_root).expanduser().resolve()
    resolved_cache_root = (
        Path(cache_root).expanduser().resolve()
        if cache_root is not None
        else output / "membership_cache"
    )
    membership = compute_memberships(
        validation.connectome,
        validation.seed,
        validation.atlas,
        validation.config,
        resolved_cache_root,
    )
    statistics = compute_statistics(
        membership,
        validation.atlas,
        ranking_enabled=validation.config.ranking.enabled,
    )
    provenance = dict(code_provenance or collect_code_provenance())
    artifacts = write_run_atomic(
        output_root=output,
        config=validation.config,
        seed=validation.seed,
        atlas=validation.atlas,
        connectome_metadata=validation.connectome_metadata,
        membership=membership,
        statistics=statistics,
        code_provenance=provenance,
    )
    return ConnectivityRunResult(
        validation=validation,
        membership=membership,
        statistics=statistics,
        artifacts=artifacts,
    )


def inspect_run_status(run_dir: Path | str) -> dict[str, Any]:
    """Verify and summarize one immutable run directory."""
    root = Path(run_dir).expanduser().resolve()
    hashes = verify_artifact_index(root)
    try:
        manifest = json.loads((root / "analysis_manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        raise ArtifactError(f"failed to read run manifest {root}: {exc}") from exc
    return {
        "status": "complete",
        "run_dir": str(root),
        "run_fingerprint": manifest["run_fingerprint"],
        "created_at": manifest["created_at"],
        "configuration_hash": manifest["configuration_hash"],
        "artifact_count": len(hashes) + 1,
    }


def list_run_artifacts(run_dir: Path | str) -> tuple[dict[str, Any], ...]:
    """Verify and list indexed artifacts in deterministic index order."""
    root = Path(run_dir).expanduser().resolve()
    verify_artifact_index(root)
    try:
        with (root / "artifact_index.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        raise ArtifactError(f"failed to read artifact index from {root}: {exc}") from exc
    artifacts = [
        {
            "artifact_name": row["artifact_name"],
            "relative_path": row["relative_path"],
            "sha256": row["sha256"],
            "size_bytes": int(row["size_bytes"]),
        }
        for row in rows
    ]
    index_path = root / "artifact_index.csv"
    artifacts.append(
        {
            "artifact_name": index_path.name,
            "relative_path": index_path.name,
            "sha256": sha256_file(index_path),
            "size_bytes": index_path.stat().st_size,
        }
    )
    return tuple(artifacts)
