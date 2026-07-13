"""Parse and spatially resolve integer atlas labels."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import nibabel as nib
import numpy as np

from .errors import LabelError
from .models import AtlasBuildConfig, AtlasLabel, ResolvedLabel


_LINE = re.compile(r"^(\d+)\s+(.+?)\s*$")


def parse_label_table(path: Path | str) -> tuple[AtlasLabel, ...]:
    """Parse a Lead-DBS integer label table with unique IDs."""

    labels: list[AtlasLabel] = []
    seen: set[int] = set()
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        match = _LINE.match(raw)
        if match is None:
            raise LabelError(f"invalid label table line {line_number}: {raw!r}")
        label_id = int(match.group(1))
        if label_id <= 0:
            raise LabelError("label IDs must be positive")
        if label_id in seen:
            raise LabelError(f"duplicate label ID {label_id}")
        seen.add(label_id)
        labels.append(AtlasLabel(label_id=label_id, source_label_name=match.group(2)))
    if not labels:
        raise LabelError("label table is empty")
    return tuple(labels)


def _declared_side(name: str) -> str:
    if name.endswith("_L"):
        return "L"
    if name.endswith("_R"):
        return "R"
    return "M"


def _replace_side(name: str, side: str) -> str:
    base = name[:-2] if name.endswith(("_L", "_R")) else name
    return f"{base}_{side}" if side in ("L", "R") else base


def _base_name(name: str) -> str:
    base = name[:-2] if name.endswith(("_L", "_R")) else name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not safe:
        raise LabelError(f"label name cannot produce a safe filename: {name!r}")
    return safe


def resolve_labels(
    config: AtlasBuildConfig,
    source_image: nib.spatialimages.SpatialImage,
) -> tuple[ResolvedLabel, ...]:
    """Validate the voxel labels and resolve category and laterality metadata."""

    table = parse_label_table(config.source_labels)
    table_ids = {item.label_id for item in table}
    configured_ids = set(config.categories.all_ids)
    raw = np.asanyarray(source_image.dataobj)
    if not np.all(np.isfinite(raw)) or not np.all(raw == np.rint(raw)):
        raise LabelError("source labeling must contain finite integer values")
    data = raw.astype(np.int64, copy=False)
    voxel_ids = set(int(item) for item in np.unique(data) if int(item) != 0)
    if table_ids != configured_ids or voxel_ids != configured_ids:
        raise LabelError(
            "label table, voxel labels, and configured category partition must contain identical IDs"
        )

    resolved: list[ResolvedLabel] = []
    for item in table:
        indices = np.argwhere(data == item.label_id)
        if indices.size == 0:
            raise LabelError(f"label {item.label_id} is empty")
        coordinates = nib.affines.apply_affine(source_image.affine, indices)
        centroid = coordinates.mean(axis=0)
        category = config.categories.category_for(item.label_id)
        declared = _declared_side(item.source_label_name)
        if category == "white_matter" and declared in ("L", "R"):
            hemisphere = "L" if float(centroid[0]) < 0.0 else "R"
        else:
            hemisphere = declared
        if hemisphere == "L":
            contralateral = float(np.mean(coordinates[:, 0] >= 0.0))
        elif hemisphere == "R":
            contralateral = float(np.mean(coordinates[:, 0] <= 0.0))
        else:
            contralateral = 0.0
        corrected = hemisphere != declared
        resolved_name = _replace_side(item.source_label_name, hemisphere) if corrected else item.source_label_name
        base = _base_name(resolved_name)
        resolved.append(
            ResolvedLabel(
                label_id=item.label_id,
                source_label_name=item.source_label_name,
                resolved_label_name=resolved_name,
                base_name=base,
                category=category,
                tissue_type="white_matter" if category == "white_matter" else "gray_matter",
                hemisphere=hemisphere,
                laterality_corrected=corrected,
                include_in_region_ranking=category != "white_matter",
                paired_filename=f"{base}.nii.gz",
                source_voxel_count=int(indices.shape[0]),
                centroid_x=float(centroid[0]),
                centroid_y=float(centroid[1]),
                centroid_z=float(centroid[2]),
                contralateral_voxel_fraction=contralateral,
            )
        )
    by_base: dict[tuple[str, str], list[int]] = {}
    for index, label in enumerate(resolved):
        by_base.setdefault((label.tissue_type, label.base_name), []).append(index)
    for indices in by_base.values():
        by_side = {
            side: sorted(
                (index for index in indices if resolved[index].hemisphere == side),
                key=lambda index: resolved[index].label_id,
            )
            for side in ("L", "R", "M")
        }
        if max(len(items) for items in by_side.values()) <= 1:
            continue
        if len(by_side["L"]) == len(by_side["R"]) and not by_side["M"]:
            for pair_number, (left_index, right_index) in enumerate(
                zip(by_side["L"], by_side["R"]),
                start=1,
            ):
                filename = f"{resolved[left_index].base_name}__pair-{pair_number}.nii.gz"
                resolved[left_index] = replace(resolved[left_index], paired_filename=filename)
                resolved[right_index] = replace(resolved[right_index], paired_filename=filename)
        else:
            for index in indices:
                label = resolved[index]
                resolved[index] = replace(
                    label,
                    paired_filename=f"{label.base_name}__label-{label.label_id}.nii.gz",
                )
    return tuple(sorted(resolved, key=lambda label: label.label_id))
