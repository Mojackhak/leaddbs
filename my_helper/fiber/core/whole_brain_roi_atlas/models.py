"""Immutable public contracts for whole-brain ROI atlas construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class LabelCategories:
    """Disjoint anatomical label ID categories."""

    cortical_limbic: tuple[int, ...]
    cerebellar_hemisphere: tuple[int, ...]
    cerebellar_midline: tuple[int, ...]
    subcortical: tuple[int, ...]
    white_matter: tuple[int, ...]

    @property
    def all_ids(self) -> tuple[int, ...]:
        """Return all configured IDs in category order."""

        return (
            self.cortical_limbic
            + self.cerebellar_hemisphere
            + self.cerebellar_midline
            + self.subcortical
            + self.white_matter
        )

    def category_for(self, label_id: int) -> str:
        """Return the configured category for one label ID."""

        for name in (
            "cortical_limbic",
            "cerebellar_hemisphere",
            "cerebellar_midline",
            "subcortical",
            "white_matter",
        ):
            if label_id in getattr(self, name):
                return name
        raise KeyError(label_id)


@dataclass(frozen=True)
class AtlasBuildConfig:
    """Fully resolved atlas build configuration."""

    schema_version: int
    source_labeling: Path
    source_labels: Path
    reference_image: Path
    connectome: Path
    atlas_root: Path
    categories: LabelCategories
    expected_label_count: int
    expected_fiber_count: int
    fiber_chunk_size: int
    resolved_mapping: Mapping[str, Any]
    configuration_hash: str


@dataclass(frozen=True)
class AtlasLabel:
    """One source integer label and name."""

    label_id: int
    source_label_name: str


@dataclass(frozen=True)
class ResolvedLabel:
    """One classified label with spatially resolved laterality."""

    label_id: int
    source_label_name: str
    resolved_label_name: str
    base_name: str
    category: str
    tissue_type: str
    hemisphere: str
    laterality_corrected: bool
    include_in_region_ranking: bool
    paired_filename: str
    source_voxel_count: int
    centroid_x: float
    centroid_y: float
    centroid_z: float
    contralateral_voxel_fraction: float


@dataclass(frozen=True)
class AtlasBuildResult:
    """Published atlas identity and summary."""

    atlas_root: Path
    build_fingerprint: str
    label_count: int
    main_roi_count: int
    white_matter_roi_count: int
    n_fibers: int
    n_endpoints: int
    reused: bool


EMPTY_MAPPING: Mapping[str, Any] = MappingProxyType({})
