"""Compatibility exports for the shared tau/Coverage source resolver."""

from ..source_resolver import (
    ABSENT_NO_STABLE_GRID,
    PRE_SPECIFIED_ACCEPTED,
    SCAN_FALLBACK_ACCEPTED,
    GridCellMetric,
    SourceResolution,
    SourceResolverError,
    adjacent_passing_count,
    is_adjacent,
    resolve_source,
)

__all__ = [
    "ABSENT_NO_STABLE_GRID",
    "GridCellMetric",
    "PRE_SPECIFIED_ACCEPTED",
    "SCAN_FALLBACK_ACCEPTED",
    "SourceResolution",
    "SourceResolverError",
    "adjacent_passing_count",
    "is_adjacent",
    "resolve_source",
]
