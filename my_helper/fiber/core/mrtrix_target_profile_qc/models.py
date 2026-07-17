"""Immutable data contracts for target-profile quality control."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from my_helper.fiber.core.mrtrix_seed_target.models import (
    SeedSpec,
    ValidationBundle,
)


@dataclass(frozen=True)
class QcConfig:
    """Resolved compact QC configuration."""

    schema_version: int
    tracking_config: Path
    preset: str
    output_root: Path
    run_name: str
    source_path: Path
    resolved_mapping: Mapping[str, Any]
    configuration_hash: str

    @property
    def output_directory(self) -> Path:
        """Return the final run directory."""

        return self.output_root / self.run_name


@dataclass(frozen=True)
class SeedStateRecord:
    """One exact subject and seed-side tracking state."""

    subject_id: str
    subject_dir: Path
    seed: SeedSpec
    preparation_identity: str
    seedwide_identity: str
    preparation_path: Path
    state_path: Path
    state_hash: str
    preparation: Mapping[str, Any]
    state: Mapping[str, Any]


@dataclass(frozen=True)
class QcValidation:
    """Complete read-only QC validation bundle."""

    config: QcConfig
    tracking: ValidationBundle
    records: tuple[SeedStateRecord, ...]
    implementation_hash: str
    warnings: tuple[str, ...]

    def as_mapping(self) -> dict[str, Any]:
        """Return the concise public validation result."""

        target_rows = sum(len(record.seed.targets) for record in self.records)
        statuses: dict[str, int] = {}
        for record in self.records:
            status = str(record.state["status"])
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "status": "valid",
            "qc_configuration_hash": self.config.configuration_hash,
            "tracking_configuration_hash": self.tracking.config.configuration_hash,
            "preset": self.config.preset,
            "subject_count": len(self.tracking.subjects),
            "seed_profile_count": len(self.records),
            "target_observation_count": target_rows,
            "seed_state_statuses": dict(sorted(statuses.items())),
            "output_directory": str(self.config.output_directory),
            "warnings": list(self.warnings),
        }

