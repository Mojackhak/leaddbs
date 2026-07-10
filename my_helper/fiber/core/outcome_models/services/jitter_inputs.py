"""Strict hashed geometry inputs for configured spatial-jitter sensitivity."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


def _file_entry(path: Path) -> dict[str, str]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"jitter geometry input is missing: {resolved}")
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(resolved), "sha256": digest.hexdigest()}


def _ordered_subject_rows(
    rows: Iterable[dict[str, Any]],
    subject_order: tuple[str, ...],
) -> list[dict[str, Any]]:
    materialized = list(rows)
    observed = tuple(str(row.get("subject_id", "")) for row in materialized)
    if observed != tuple(subject_order) or len(set(observed)) != len(observed):
        raise ValueError(
            "jitter sampling subject order mismatch: "
            f"expected={list(subject_order)!r}, observed={list(observed)!r}"
        )
    return materialized


def direct_sampling_rows(
    rows: Iterable[dict[str, Any]],
    subject_order: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Hash direct-voxel sampling rows already resolved to canonical sides."""
    output: list[dict[str, Any]] = []
    for row in _ordered_subject_rows(rows, subject_order):
        normalized: dict[str, Any] = {"subject_id": str(row["subject_id"])}
        for side in ("right", "left_to_right"):
            entries = row.get(side, [])
            if not isinstance(entries, list):
                raise ValueError(f"jitter sampling {side} entries must be a list")
            paths: list[Path] = []
            for entry in entries:
                if not isinstance(entry, dict) or not str(entry.get("path", "")).strip():
                    raise ValueError(f"jitter sampling {side} entry requires a path")
                paths.append(Path(str(entry["path"])))
            normalized[side] = [_file_entry(path) for path in paths]
        output.append(normalized)
    return output


def side_field_sampling_rows(
    rows: Iterable[dict[str, Any]],
    subject_order: tuple[str, ...],
    *,
    flipped_root: Path,
) -> list[dict[str, Any]]:
    """Convert side-field provenance to canonical right/left-to-right rows."""
    by_subject: dict[str, dict[str, list[Path]]] = {
        subject_id: {"R": [], "L": []} for subject_id in subject_order
    }
    for row in rows:
        subject_id = str(row.get("subject_id", ""))
        side = str(row.get("side", ""))
        if subject_id not in by_subject or side not in {"R", "L"}:
            raise ValueError("jitter side-field rows contain an unexpected subject or side")
        if by_subject[subject_id][side]:
            raise ValueError(f"duplicate jitter side-field row for {subject_id}:{side}")
        raw_paths = row.get("source_paths", [])
        if not isinstance(raw_paths, list):
            raise ValueError("jitter side-field source_paths must be a list")
        by_subject[subject_id][side] = [Path(str(path)) for path in raw_paths]

    root = Path(flipped_root).expanduser().resolve()
    output: list[dict[str, Any]] = []
    for subject_id in subject_order:
        right_paths = by_subject[subject_id]["R"]
        left_sources = by_subject[subject_id]["L"]
        flipped_paths = [
            root / f"{subject_id}_hemi-L_src-{index:02d}_to_R.nii"
            for index in range(1, len(left_sources) + 1)
        ]
        output.append(
            {
                "subject_id": subject_id,
                "right": [_file_entry(path) for path in right_paths],
                "left_to_right": [_file_entry(path) for path in flipped_paths],
            }
        )
    return output


def build_direct_geometry(
    *,
    final_candidate_xyz: Path,
    hf_reference_sampling_qc: list[dict[str, Any]] | None = None,
    hf_component_sampling_qc: list[dict[str, Any]] | None = None,
    ulf_component_sampling_qc: list[dict[str, Any]] | None = None,
    matched_hf_candidate_xyz: Path | None = None,
    hf_support_xyz: Path | None = None,
    matched_hf_candidate_indices_in_support: Path | None = None,
) -> dict[str, Any]:
    """Build the exact geometry object consumed by direct jitter."""
    geometry: dict[str, Any] = {
        "builder": "direct_efield_resample_v1",
        "final_candidate_xyz": _file_entry(final_candidate_xyz),
    }
    optional_rows = {
        "hf_reference_sampling_qc": hf_reference_sampling_qc,
        "hf_component_sampling_qc": hf_component_sampling_qc,
        "ulf_component_sampling_qc": ulf_component_sampling_qc,
    }
    optional_paths = {
        "matched_hf_candidate_xyz": matched_hf_candidate_xyz,
        "hf_support_xyz": hf_support_xyz,
        "matched_hf_candidate_indices_in_support": matched_hf_candidate_indices_in_support,
    }
    geometry.update({key: value for key, value in optional_rows.items() if value is not None})
    geometry.update(
        {key: _file_entry(value) for key, value in optional_paths.items() if value is not None}
    )
    return geometry


def build_fiber_geometry(
    *,
    connectome_data_mat: Path,
    hf_reference_sampling_qc: list[dict[str, Any]] | None = None,
    hf_component_sampling_qc: list[dict[str, Any]] | None = None,
    ulf_component_sampling_qc: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the exact geometry object consumed by normative-fiber jitter."""
    geometry: dict[str, Any] = {
        "builder": "normative_fiber_efield_resample_v1",
        "connectome_data_mat": _file_entry(connectome_data_mat),
    }
    optional_rows = {
        "hf_reference_sampling_qc": hf_reference_sampling_qc,
        "hf_component_sampling_qc": hf_component_sampling_qc,
        "ulf_component_sampling_qc": ulf_component_sampling_qc,
    }
    geometry.update({key: value for key, value in optional_rows.items() if value is not None})
    return geometry


__all__ = [
    "build_direct_geometry",
    "build_fiber_geometry",
    "direct_sampling_rows",
    "side_field_sampling_rows",
]
