"""Immutable public data contracts for seed-target connectivity."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


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
