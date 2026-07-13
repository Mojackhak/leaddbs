"""Deterministic artifact rendering and integrity verification."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .errors import PublicationError
from .models import EndpointCensus, ResolvedLabel, RoiArtifact


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def materialize(value: Any) -> Any:
    """Convert immutable mappings and tuples into serialization-safe values."""

    if isinstance(value, Mapping):
        return {str(key): materialize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [materialize(item) for item in value]
    return value


def write_text(path: Path, payload: str) -> None:
    """Write UTF-8 text with one trailing newline."""

    path.write_text(payload.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    """Write stable pretty JSON."""

    write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> None:
    """Write deterministic CSV fields and rows."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def region_rows(
    labels: tuple[ResolvedLabel, ...],
    rois: tuple[RoiArtifact, ...],
    census: EndpointCensus,
) -> list[dict[str, Any]]:
    """Join anatomical, ROI, and endpoint metadata by label ID."""

    roi_by_id = {item.label_id: item for item in rois}
    endpoint_by_id = {item.label_id: item for item in census.labels}
    rows: list[dict[str, Any]] = []
    for label in labels:
        roi = roi_by_id[label.label_id]
        endpoint = endpoint_by_id[label.label_id]
        rows.append(
            {
                "label_id": label.label_id,
                "source_label_name": label.source_label_name,
                "resolved_label_name": label.resolved_label_name,
                "base_name": label.base_name,
                "hemisphere": label.hemisphere,
                "category": label.category,
                "tissue_type": label.tissue_type,
                "include_in_region_ranking": label.include_in_region_ranking,
                "laterality_corrected": label.laterality_corrected,
                "source_voxel_count": label.source_voxel_count,
                "resampled_voxel_count": roi.voxel_count,
                "volume_mm3": roi.volume_mm3,
                "centroid_x": label.centroid_x,
                "centroid_y": label.centroid_y,
                "centroid_z": label.centroid_z,
                "contralateral_voxel_fraction": label.contralateral_voxel_fraction,
                "endpoint_count": endpoint.endpoint_count,
                "endpoint_fraction": endpoint.endpoint_fraction,
                "fiber_count": endpoint.fiber_count,
                "fiber_fraction": endpoint.fiber_fraction,
                "relative_path": roi.relative_path,
            }
        )
    return rows


REGION_FIELDS = [
    "label_id",
    "source_label_name",
    "resolved_label_name",
    "base_name",
    "hemisphere",
    "category",
    "tissue_type",
    "include_in_region_ranking",
    "laterality_corrected",
    "source_voxel_count",
    "resampled_voxel_count",
    "volume_mm3",
    "centroid_x",
    "centroid_y",
    "centroid_z",
    "contralateral_voxel_fraction",
    "endpoint_count",
    "endpoint_fraction",
    "fiber_count",
    "fiber_fraction",
    "relative_path",
]


def write_label_tables(root: Path, labels: tuple[ResolvedLabel, ...]) -> None:
    """Write resolved and original Lead-DBS integer label tables."""

    write_text(
        root / "labels.txt",
        "\n".join(f"{item.label_id} {item.resolved_label_name}" for item in labels),
    )
    write_text(
        root / "labels_source.txt",
        "\n".join(f"{item.label_id} {item.source_label_name}" for item in labels),
    )


def write_endpoint_qc(root: Path, rows: list[dict[str, Any]], census: EndpointCensus) -> None:
    """Write label rows plus the strict unassigned endpoint summary."""

    endpoint_rows = [
        {
            "label_id": row["label_id"],
            "resolved_label_name": row["resolved_label_name"],
            "category": row["category"],
            "endpoint_count": row["endpoint_count"],
            "endpoint_fraction": row["endpoint_fraction"],
            "fiber_count": row["fiber_count"],
            "fiber_fraction": row["fiber_fraction"],
        }
        for row in rows
    ]
    endpoint_rows.append(
        {
            "label_id": 0,
            "resolved_label_name": "unassigned",
            "category": "unassigned",
            "endpoint_count": census.unassigned_endpoint_count,
            "endpoint_fraction": census.unassigned_endpoint_fraction,
            "fiber_count": census.unassigned_fiber_count,
            "fiber_fraction": census.unassigned_fiber_fraction,
        }
    )
    write_csv(
        root / "dtor_endpoint_qc.csv",
        endpoint_rows,
        [
            "label_id",
            "resolved_label_name",
            "category",
            "endpoint_count",
            "endpoint_fraction",
            "fiber_count",
            "fiber_fraction",
        ],
    )


def write_readme(root: Path, rows: list[dict[str, Any]], census: EndpointCensus) -> None:
    """Write a complete categorized region inventory and build interpretation."""

    lines = [
        "# HybraPD Whole-Brain ROI Atlas",
        "",
        "This atlas is a deterministic mapping of HybraPD Whole Brain labels to the Lead-DBS MNI152NLin2009bAsym reference grid. dTOR provides streamline endpoints and does not define the anatomy.",
        "",
        f"- Fibers: {census.n_fibers}",
        f"- Endpoints: {census.n_endpoints}",
        f"- Strictly unassigned endpoints: {census.unassigned_endpoint_count}",
        "- Endpoint rule: containing voxel only; no distance fallback",
        "- `atlas_index.mat` and `gm_mask.nii.gz` are generated by Lead-DBS on first UI use.",
        "",
        "## Complete Region Inventory",
        "",
    ]
    category_order = (
        "cortical_limbic",
        "cerebellar_hemisphere",
        "cerebellar_midline",
        "subcortical",
        "white_matter",
    )
    for category in category_order:
        selected = [row for row in rows if row["category"] == category]
        lines.extend(
            [
                f"### {category} ({len(selected)})",
                "",
                "| ID | Resolved name | Source name | Side | Endpoints | Ranking |",
                "|---:|---|---|:---:|---:|:---:|",
            ]
        )
        for row in selected:
            lines.append(
                f"| {row['label_id']} | {row['resolved_label_name']} | {row['source_label_name']} | {row['hemisphere']} | {row['endpoint_count']} | {str(row['include_in_region_ranking']).lower()} |"
            )
        lines.append("")
    write_text(root / "README.md", "\n".join(lines))


def write_artifact_index(root: Path) -> int:
    """Hash every published file except the self-referential index itself."""

    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "artifact_index.csv"):
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_csv(root / "artifact_index.csv", rows, ["relative_path", "size_bytes", "sha256"])
    return len(rows)


def verify_artifacts(root: Path) -> int:
    """Verify every entry in an immutable artifact index."""

    index = root / "artifact_index.csv"
    if not index.is_file():
        raise PublicationError(f"artifact index does not exist: {index}")
    with index.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        path = root / row["relative_path"]
        if not path.is_file():
            raise PublicationError(f"indexed artifact is missing: {row['relative_path']}")
        if path.stat().st_size != int(row["size_bytes"]) or sha256_file(path) != row["sha256"]:
            raise PublicationError(f"indexed artifact hash mismatch: {row['relative_path']}")
    return len(rows)


def write_resolved_config(root: Path, mapping: Mapping[str, Any]) -> None:
    """Write stable resolved YAML."""

    write_text(root / "config_resolved.yaml", yaml.safe_dump(materialize(mapping), sort_keys=True))
