"""Immutable public data contracts for seed-target connectivity."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class SeedConfig:
    """Seed-mask resolution settings."""

    probability_threshold: float | None = None


@dataclass(frozen=True)
class TargetConfig:
    """Target-mask resolution settings."""

    probability_threshold: float | None = None
    roi_thresholds: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ExecutionConfig:
    """Bounded execution and cache settings."""

    fiber_chunk_size: int = 100_000
    cache_membership: bool = True


@dataclass(frozen=True)
class RankingConfig:
    """Convenience ranking settings."""

    enabled: bool = True


@dataclass(frozen=True)
class InputConfig:
    """Resolved shared scientific input paths for one batch."""

    target_atlas_root: Path
    seed_rois: Mapping[str, Path]
    connectome: Path


@dataclass(frozen=True)
class OutputConfig:
    """Resolved semantic publication settings for one batch."""

    output_root: Path
    run_name: str
    cache_root: Path


@dataclass(frozen=True)
class BatchConnectivityConfig:
    """Fully resolved YAML configuration for named seed runs."""

    schema_version: int
    inputs: InputConfig
    output: OutputConfig
    seed: SeedConfig
    targets: TargetConfig
    execution: ExecutionConfig
    ranking: RankingConfig
    resolved_mapping: Mapping[str, Any]
    batch_configuration_hash: str


@dataclass(frozen=True)
class EffectiveConnectivityConfig:
    """Side-specific scientific configuration used by single-seed primitives."""

    schema_version: int
    seed_name: str
    seed_roi: Path
    seed: SeedConfig
    targets: TargetConfig
    execution: ExecutionConfig
    ranking: RankingConfig
    resolved_mapping: Mapping[str, Any]
    batch_resolved_mapping: Mapping[str, Any]
    batch_configuration_hash: str
    effective_configuration_hash: str

    @property
    def configuration_hash(self) -> str:
        """Return the effective hash expected by single-seed primitives."""

        return self.effective_configuration_hash


ConnectivityConfig = EffectiveConnectivityConfig


@dataclass(frozen=True)
class TargetSource:
    """One deterministically discovered target NIfTI source."""

    target_id: str
    target_group: str
    relative_path: str
    path: Path


@dataclass(frozen=True)
class ResolvedMask:
    """One validated and resolved binary voxel mask."""

    roi_id: str
    role: str
    source_path: Path
    relative_path: str
    target_group: str
    source_value_type: str
    probability_threshold: float | None
    threshold_source: str
    source_hash: str
    voxel_count: int
    physical_volume_mm3: float
    resolved_mask_hash: str
    status: str
    shape: tuple[int, int, int]
    affine: np.ndarray
    flat_voxel_indices: np.ndarray


@dataclass(frozen=True)
class ResolvedAtlas:
    """An ordered target catalog with a stable resolved identity."""

    root: Path
    targets: tuple[ResolvedMask, ...]
    atlas_hash: str


@dataclass(frozen=True)
class ConnectomeMetadata:
    """Stable identity and dimensions exposed by one connectome adapter."""

    connectome_id: str
    source_path: Path
    source_hash: str
    geometry_hash: str
    ordered_fiber_id_hash: str
    connectome_identity: str
    identity_source: str
    adapter_name: str
    adapter_version: str
    n_fibers: int
    n_points: int


@dataclass(frozen=True)
class FiberChunk:
    """One bounded block of canonical fiber IDs and ordered points."""

    fiber_ids: np.ndarray
    point_offsets: np.ndarray
    points: np.ndarray

    def streamline(self, index: int) -> np.ndarray:
        """Return the ordered points for one zero-based fiber within the chunk."""
        start = int(self.point_offsets[index])
        stop = int(self.point_offsets[index + 1])
        return self.points[start:stop]


@dataclass(frozen=True)
class TargetFiberMembership:
    """CSR-style canonical fiber IDs for an ordered target catalog."""

    target_ids: tuple[str, ...]
    indptr: np.ndarray
    fiber_ids: np.ndarray

    def ids_for(self, target: str | int) -> np.ndarray:
        """Return canonical IDs for one target ID or zero-based target index."""
        index = self.target_ids.index(target) if isinstance(target, str) else int(target)
        start = int(self.indptr[index])
        stop = int(self.indptr[index + 1])
        return self.fiber_ids[start:stop]


@dataclass(frozen=True)
class MembershipResult:
    """Whole-connectome seed and target membership with cache provenance."""

    n_all_fibers: int
    seed_fiber_ids: np.ndarray
    target_membership: TargetFiberMembership
    seed_cache_key: str
    target_cache_key: str
    seed_cache_hit: bool
    target_cache_hit: bool
    seed_cache_path: Path | None
    target_cache_path: Path | None


@dataclass(frozen=True)
class TargetStatistic:
    """One target row under the exact descriptive statistics contract."""

    target_id: str
    target_group: str
    relative_path: str
    source_value_type: str
    probability_threshold: float | None
    threshold_source: str
    target_status: str
    n_all_fibers: int
    n_seed_fibers: int
    n_target_fibers: int
    n_seed_target_fibers: int
    raw_fiber_count: int
    seed_normalized_fraction: float
    target_background_prevalence: float
    connectivity_lift: float | None
    connectivity_pmi: float | None
    connectivity_pmi_status: str
    rank: int | None = None

    def as_serializable_mapping(self) -> dict[str, Any]:
        """Return a JSON-safe mapping with no nonfinite numeric values."""
        return {
            "target_id": self.target_id,
            "target_group": self.target_group,
            "relative_path": self.relative_path,
            "source_value_type": self.source_value_type,
            "probability_threshold": self.probability_threshold,
            "threshold_source": self.threshold_source,
            "target_status": self.target_status,
            "n_all_fibers": self.n_all_fibers,
            "n_seed_fibers": self.n_seed_fibers,
            "n_target_fibers": self.n_target_fibers,
            "n_seed_target_fibers": self.n_seed_target_fibers,
            "raw_fiber_count": self.raw_fiber_count,
            "seed_normalized_fraction": self.seed_normalized_fraction,
            "target_background_prevalence": self.target_background_prevalence,
            "connectivity_lift": self.connectivity_lift,
            "connectivity_pmi": self.connectivity_pmi,
            "connectivity_pmi_status": self.connectivity_pmi_status,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class RunArtifacts:
    """One immutable content-addressed run directory."""

    run_dir: Path
    run_fingerprint: str
    artifact_hashes: Mapping[str, str]
    reused: bool


@dataclass(frozen=True)
class ValidationReport:
    """Resolved inputs produced without full-connectome traversal."""

    config: ConnectivityConfig
    seed: ResolvedMask
    atlas: ResolvedAtlas
    connectome: Any
    connectome_metadata: ConnectomeMetadata
    n_targets: int
    n_valid_targets: int
    n_empty_targets: int
    seed_voxel_count: int

    def as_serializable_mapping(self) -> dict[str, Any]:
        """Return a compact JSON-safe validation summary."""
        return {
            "status": "valid",
            "configuration_hash": self.config.configuration_hash,
            "n_targets": self.n_targets,
            "n_valid_targets": self.n_valid_targets,
            "n_empty_targets": self.n_empty_targets,
            "seed_voxel_count": self.seed_voxel_count,
            "seed_resolved_mask_hash": self.seed.resolved_mask_hash,
            "target_atlas_resolved_mask_hash": self.atlas.atlas_hash,
            "connectome_id": self.connectome_metadata.connectome_id,
            "connectome_identity": self.connectome_metadata.connectome_identity,
            "n_all_fibers": self.connectome_metadata.n_fibers,
            "n_all_points": self.connectome_metadata.n_points,
        }


@dataclass(frozen=True)
class BatchValidationReport:
    """Resolved shared inputs and ordered per-seed validation reports."""

    config: BatchConnectivityConfig
    seeds: Mapping[str, ValidationReport]

    def as_serializable_mapping(self) -> dict[str, Any]:
        """Return a compact JSON-safe batch validation summary."""

        return {
            "status": "valid",
            "batch_configuration_hash": self.config.batch_configuration_hash,
            "seeds": {
                name: report.as_serializable_mapping()
                for name, report in self.seeds.items()
            },
        }


@dataclass(frozen=True)
class ConnectivityRunResult:
    """Complete public API result for one immutable connectivity run."""

    validation: ValidationReport
    membership: MembershipResult
    statistics: tuple[TargetStatistic, ...]
    artifacts: RunArtifacts
