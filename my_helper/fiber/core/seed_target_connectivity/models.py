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
class IntersectionConfig:
    """Streamline-to-voxel intersection settings."""

    method: str = "segment_aware_voxel_traversal"


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
class ConnectivityConfig:
    """Fully resolved algorithm configuration."""

    schema_version: int
    seed: SeedConfig
    targets: TargetConfig
    intersection: IntersectionConfig
    execution: ExecutionConfig
    ranking: RankingConfig
    resolved_mapping: Mapping[str, Any]
    configuration_hash: str


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
