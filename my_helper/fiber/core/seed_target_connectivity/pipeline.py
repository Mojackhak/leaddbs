"""Reusable validation and run orchestration for seed-target connectivity."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .artifacts import (
    collect_code_provenance,
    verify_artifact_index,
    write_run_atomic,
)
from .config import effective_config, load_config, resolve_config
from .connectome import ConnectomeAdapter, open_connectome
from .engine import compute_memberships
from .errors import ArtifactError, ConfigurationError, ConnectomeError
from .identity import sha256_file
from .atlas import discover_targets
from .models import (
    BatchConnectivityConfig,
    BatchValidationReport,
    ConnectivityConfig,
    ConnectivityRunResult,
    ValidationReport,
)
from .roi import resolve_atlas, resolve_seed
from .statistics import compute_statistics


class ResolutionCache:
    """Exact-process cache for unchanged read-only seed and atlas resolution."""

    def __init__(self) -> None:
        self._seeds: dict[tuple[Any, ...], Any] = {}
        self._atlases: dict[tuple[Any, ...], Any] = {}

    @staticmethod
    def _file_state(path: Path) -> tuple[str, int, int]:
        resolved = path.expanduser().resolve()
        stat = resolved.stat()
        return str(resolved), stat.st_size, stat.st_mtime_ns

    def resolve_seed(self, path: Path | str, config: ConnectivityConfig):
        source = Path(path)
        key = (*self._file_state(source), config.seed.probability_threshold)
        if key not in self._seeds:
            self._seeds[key] = resolve_seed(source, config)
        return self._seeds[key]

    def resolve_atlas(self, root: Path | str, config: ConnectivityConfig):
        atlas_root = Path(root).expanduser().resolve()
        sources = discover_targets(atlas_root)
        source_state = tuple(self._file_state(source.path) for source in sources)
        key = (
            str(atlas_root),
            source_state,
            config.targets.probability_threshold,
            tuple(config.targets.roi_thresholds.items()),
        )
        if key not in self._atlases:
            self._atlases[key] = resolve_atlas(atlas_root, config)
        return self._atlases[key]


def _resolve_config(config: ConnectivityConfig | Mapping[str, Any] | Path | str) -> ConnectivityConfig:
    if isinstance(config, ConnectivityConfig):
        return config
    if isinstance(config, Mapping):
        return resolve_config(config)
    if isinstance(config, (Path, str)):
        return load_config(config)
    raise ConfigurationError(f"unsupported configuration input type: {type(config).__name__}")


def _resolve_batch_config(
    config: BatchConnectivityConfig | Mapping[str, Any] | Path | str,
) -> BatchConnectivityConfig:
    if isinstance(config, BatchConnectivityConfig):
        return config
    if isinstance(config, Mapping):
        return resolve_config(config)
    if isinstance(config, (Path, str)):
        return load_config(config)
    raise ConfigurationError(f"unsupported batch configuration input type: {type(config).__name__}")


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
    resolution_cache: ResolutionCache | None = None,
) -> ValidationReport:
    """Resolve all inputs without traversing full connectome geometry."""
    resolved_config = _resolve_config(config)
    if resolution_cache is None:
        resolved_seed = resolve_seed(seed_roi, resolved_config)
        resolved_atlas = resolve_atlas(target_atlas_root, resolved_config)
    else:
        resolved_seed = resolution_cache.resolve_seed(seed_roi, resolved_config)
        resolved_atlas = resolution_cache.resolve_atlas(target_atlas_root, resolved_config)
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


def validate_batch(
    config: BatchConnectivityConfig | Mapping[str, Any] | Path | str,
    *,
    connectome_override: ConnectomeAdapter | None = None,
) -> BatchValidationReport:
    """Resolve every named seed without traversing full connectome geometry."""

    batch = _resolve_batch_config(config)
    adapter = connectome_override or open_connectome(batch.inputs.connectome)
    resolution_cache = ResolutionCache()
    reports: dict[str, ValidationReport] = {}
    for seed_name in batch.inputs.seed_rois:
        effective = effective_config(batch, seed_name)
        reports[seed_name] = validate_inputs(
            target_atlas_root=batch.inputs.target_atlas_root,
            seed_roi=effective.seed_roi,
            connectome=adapter,
            config=effective,
            resolution_cache=resolution_cache,
        )
    return BatchValidationReport(
        config=batch,
        seeds=MappingProxyType(reports),
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
    resolution_cache: ResolutionCache | None = None,
) -> ConnectivityRunResult:
    """Compute target-wise statistics and publish one immutable run."""
    validation = validate_inputs(
        target_atlas_root=target_atlas_root,
        seed_roi=seed_roi,
        connectome=connectome,
        config=config,
        resolution_cache=resolution_cache,
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
