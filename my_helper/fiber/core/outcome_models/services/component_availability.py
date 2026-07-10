"""Run-local ULF component availability generated from configured study inputs."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ComponentAvailabilityOutput:
    csv_path: Path
    manifest_path: Path
    row_count: int
    stimulation_table_sha256: str


def _analysis_module():
    analysis_root = Path(__file__).resolve().parents[2] / "analysis"
    if str(analysis_root) not in sys.path:
        sys.path.insert(0, str(analysis_root))
    return importlib.import_module("stnsnr_ulf_component_readiness")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_stimulation_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name="Contact Parameters")
    raise ValueError(f"unsupported stimulation table format: {path}")


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({str(key) for row in rows for key in row})
    if not fields:
        fields = [
            "subject_id",
            "phase",
            "protocol",
            "frequency_class",
            "efield_path",
            "status",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_run_local_component_availability(
    *,
    stimulation_table: Path,
    derivatives_root: Path,
    run_root: Path,
    addon_protocols: tuple[str, ...],
    endpoint_phases: tuple[str, ...],
) -> ComponentAvailabilityOutput:
    """Write one deterministic configured component-availability sidecar."""
    stimulation_path = Path(stimulation_table).expanduser().resolve()
    derivatives_path = Path(derivatives_root).expanduser().resolve()
    configured_run_root = Path(run_root).expanduser().resolve()
    protocols = tuple(str(value).strip() for value in addon_protocols)
    phases = tuple(str(value).strip() for value in endpoint_phases)
    if not stimulation_path.is_file():
        raise FileNotFoundError(f"configured stimulation table is missing: {stimulation_path}")
    if not protocols or any(not value for value in protocols) or len(set(protocols)) != len(protocols):
        raise ValueError("add-on protocols must be nonempty and unique")
    if not phases or any(not value for value in phases) or len(set(phases)) != len(phases):
        raise ValueError("endpoint phases must be nonempty and unique")

    table = _read_stimulation_table(stimulation_path)
    required = {
        "ID",
        "NameEn",
        "Phase",
        "Protocol",
        "Side",
        "Target",
        "Contact",
        "Frequency",
        "StimulationPattern",
    }
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("stimulation table is missing component columns: " + ", ".join(missing))

    analysis = _analysis_module()
    rows = analysis.build_component_availability(
        table,
        derivatives_path,
        protocols=protocols,
        phases=phases,
    )
    output_root = configured_run_root / "shared" / "ulf_component_availability"
    csv_path = output_root / "component_availability.csv"
    manifest_path = output_root / "component_availability_manifest.json"
    stimulation_hash = _sha256(stimulation_path)
    _write_csv_atomic(csv_path, rows)
    _write_json_atomic(
        manifest_path,
        {
            "status": "complete",
            "stimulation_table": str(stimulation_path),
            "stimulation_table_sha256": stimulation_hash,
            "derivatives_root": str(derivatives_path),
            "addon_protocols": list(protocols),
            "endpoint_phases": list(phases),
            "row_count": len(rows),
            "component_availability_csv": str(csv_path),
            "component_availability_sha256": _sha256(csv_path),
            "summary": analysis.summarize_component_availability(rows),
        },
    )
    return ComponentAvailabilityOutput(
        csv_path=csv_path,
        manifest_path=manifest_path,
        row_count=len(rows),
        stimulation_table_sha256=stimulation_hash,
    )


__all__ = ["ComponentAvailabilityOutput", "build_run_local_component_availability"]
