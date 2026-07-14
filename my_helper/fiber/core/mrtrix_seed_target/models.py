"""Immutable contracts for seed-wide MRtrix target-coverage tractography."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class RoiSpec:
    """One side-specific atlas ROI."""

    roi_id: str
    side: str
    path: Path

    @property
    def key(self) -> str:
        """Return the canonical side-qualified key."""

        return f"{self.side}/{self.roi_id}"


@dataclass(frozen=True)
class SeedSpec(RoiSpec):
    """One seed and its exact ordered target set."""

    targets: tuple[RoiSpec, ...] = ()


@dataclass(frozen=True)
class SubjectSpec:
    """One configured Lead-DBS subject."""

    subject_id: str
    subject_dir: Path
    path_overrides: Mapping[str, Path] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class TrackingConfig:
    """Seed-wide scientific tracking settings."""

    minimum_streamlines_per_target: int
    fod_cutoff: float
    min_length_mm: float
    max_length_mm: float
    random_seed: int


@dataclass(frozen=True)
class ExecutionConfig:
    """Bounded execution and scientific generation settings."""

    subject_workers: int
    preparation_threads_per_subject: int
    seedwide_workers_per_subject: int
    mrtrix_threads_per_seedwide_job: int
    cpu_budget: int
    memory_budget_gb: float
    memory_dispatch_fraction: float
    preparation_memory_reservation_gb: float
    seedwide_memory_reservation_gb: float
    generation_chunk_streamlines: int
    maximum_seedwide_streamlines: int
    matlab_executable: Path
    mrtrix_path_prefix: Path | None

    @property
    def memory_dispatch_capacity_gb(self) -> float:
        """Return the soft prospective memory dispatch capacity."""

        return self.memory_budget_gb * self.memory_dispatch_fraction


@dataclass(frozen=True)
class AtlasConfig:
    """Shared atlas and ordered seed definitions."""

    name: str
    space: str
    root: Path
    seeds: tuple[SeedSpec, ...]


@dataclass(frozen=True)
class BatchConfig:
    """Fully resolved strict YAML batch."""

    schema_version: int
    atlas: AtlasConfig
    subjects: tuple[SubjectSpec, ...]
    tracking: TrackingConfig
    execution: ExecutionConfig
    source_path: Path
    resolved_mapping: Mapping[str, Any]
    configuration_hash: str


@dataclass(frozen=True)
class ResolvedSubjectInputs:
    """Unambiguous real input set for one subject."""

    subject_id: str
    subject_dir: Path
    dwi: Path
    bvec: Path
    bval: Path
    b0: Path
    brain_mask: Path
    tracking_mask: Path
    anchor_native_reference: Path
    mni_to_anchor_transform: Path
    anchor_to_dwi_transform: Path
    coregistration_method_log: Path
    coregistration_method: str
    coregistration_method_token: str
    coregistration_approved: bool

    @property
    def output_root(self) -> Path:
        """Return the fixed subject-local module output root."""

        return (
            self.subject_dir
            / "connectomics"
            / "dMRI"
            / "mrtrix_seed_target"
        )


@dataclass(frozen=True)
class ToolIdentity:
    """Normalized external tool identity."""

    name: str
    executable: Path
    version: str


@dataclass(frozen=True)
class ValidationBundle:
    """Complete read-only validation result used by execution."""

    config: BatchConfig
    subjects: tuple[ResolvedSubjectInputs, ...]
    tools: Mapping[str, ToolIdentity]
    source_roi_hashes: Mapping[str, str]
    lead_dbs_git_commit: str
    code_hash: str
    preparation_code_hash: str
    tracking_code_hash: str
    publication_code_hash: str
    warnings: tuple[str, ...]

    def as_mapping(self) -> dict[str, Any]:
        """Return the public JSON-safe validation report."""

        return {
            "status": "valid",
            "configuration_hash": self.config.configuration_hash,
            "lead_dbs_git_commit": self.lead_dbs_git_commit,
            "code_hash": self.code_hash,
            "code_hashes": {
                "preparation": self.preparation_code_hash,
                "tracking": self.tracking_code_hash,
                "publication": self.publication_code_hash,
            },
            "atlas": {
                "name": self.config.atlas.name,
                "space": self.config.atlas.space,
                "root": str(self.config.atlas.root),
                "seed_count": len(self.config.atlas.seeds),
                "targets_per_seed": {
                    seed.key: len(seed.targets) for seed in self.config.atlas.seeds
                },
            },
            "subjects": [
                {
                    "id": subject.subject_id,
                    "subject_dir": str(subject.subject_dir),
                    "b0_coregistration_method": subject.coregistration_method,
                    "anchor_to_dwi_transform": str(
                        subject.anchor_to_dwi_transform
                    ),
                    "output_root": str(subject.output_root),
                }
                for subject in self.subjects
            ],
            "tools": {
                name: {
                    "executable": str(identity.executable),
                    "version": identity.version,
                }
                for name, identity in sorted(self.tools.items())
            },
            "warnings": list(self.warnings),
        }
