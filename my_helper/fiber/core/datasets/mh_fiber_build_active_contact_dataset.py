#!/usr/bin/env python3
"""Build the STN/SNr active-contact coordinate dataset."""

from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_DIR = Path("/Users/mojackhu/Github/leaddbs")
SCALE_XLSX = Path(
    "/Users/mojackhu/Research/STNSNr/summary/stats/clinic/coords/scale/scale_contact_only.xlsx"
)
CONTACT_RECO_PKL = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl"
)
SUBJECT_COORDS_CONFIG_JSON = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/lead/subject_coords_config.json"
)
OUTPUT_DIR = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset"
)
MATCH_TOLERANCE_MM = 1e-6
EXPECTED_REGION_COUNTS = {"SNr": 26, "STN": 24, "EXT": 9, "Mid": 5}


def build_active_contact_dataset(
    scale_xlsx: Path = SCALE_XLSX,
    contact_reco_pkl: Path = CONTACT_RECO_PKL,
    subject_coords_config_json: Path = SUBJECT_COORDS_CONFIG_JSON,
    output_dir: Path = OUTPUT_DIR,
    match_tolerance_mm: float = MATCH_TOLERANCE_MM,
) -> dict[str, Any]:
    """Build active_contacts.csv and active_contacts_info.json."""

    require_file(scale_xlsx, "active contact coordinate Excel")
    require_file(contact_reco_pkl, "contact reconstruction pickle")
    require_file(subject_coords_config_json, "subject coordinate config JSON")
    output_dir.mkdir(parents=True, exist_ok=True)

    scale = pd.read_excel(scale_xlsx).reset_index().rename(columns={"index": "active_scale_row"})
    with contact_reco_pkl.open("rb") as f:
        reco = pickle.load(f)
    config = json.loads(subject_coords_config_json.read_text())

    validate_required_columns(
        scale,
        ["Subject", "MNI_x_flip", "MNI_y_flip", "MNI_z_flip"],
        "scale_contact_only.xlsx",
    )
    validate_required_columns(
        reco,
        [
            "ID",
            "Subject",
            "Contact",
            "Region",
            "Side",
            "Hemi",
            "Lead_idx",
            "Lead_num",
            "MNI_x",
            "MNI_y",
            "MNI_z",
            "SNr_in",
            "SNr_x",
            "SNr_y",
            "SNr_z",
            "STN_in",
            "STN_x",
            "STN_y",
            "STN_z",
            "MNI_x_flip",
            "MNI_y_flip",
            "MNI_z_flip",
        ],
        "contact_reco_space_locs.pkl",
    )
    if not isinstance(config, dict) or "subjects" not in config:
        raise ValueError("subject_coords_config.json must contain a top-level 'subjects' object.")

    scale["subject_key"] = scale["Subject"].map(normalize_subject)
    reco = reco.copy()
    reco["subject_key"] = reco["Subject"].map(normalize_subject)

    active_rows: list[dict[str, Any]] = []
    used_matches: set[tuple[str, int]] = set()
    for _, scale_row in scale.iterrows():
        candidates = reco[reco["subject_key"] == scale_row["subject_key"]]
        if candidates.empty:
            raise ValueError(f"No reconstructed contacts found for active subject {scale_row['Subject']!r}.")

        target = scale_row[["MNI_x_flip", "MNI_y_flip", "MNI_z_flip"]].to_numpy(dtype=float)
        coords = candidates[["MNI_x_flip", "MNI_y_flip", "MNI_z_flip"]].to_numpy(dtype=float)
        distances = np.sqrt(((coords - target) ** 2).sum(axis=1))
        best_pos = int(np.argmin(distances))
        match_distance = float(distances[best_pos])
        if match_distance > match_tolerance_mm:
            raise ValueError(
                "Active contact could not be matched within tolerance: "
                f"row={int(scale_row['active_scale_row'])}, subject={scale_row['Subject']}, "
                f"distance={match_distance:.12g} mm"
            )

        match = candidates.iloc[best_pos]
        match_key = (str(match["subject_key"]), int(match["Contact"]))
        if match_key in used_matches:
            raise ValueError(f"Duplicate active contact match for {match_key}.")
        used_matches.add(match_key)

        electrode = electrode_config_for_match(config, match)
        active_rows.append(
            {
                "ID": match["ID"],
                "Subject": match["Subject"],
                "subject_key": match["subject_key"],
                "Contact": int(match["Contact"]),
                "Region": match["Region"],
                "Side": match["Side"],
                "Hemi": match["Hemi"],
                "Lead_idx": int(match["Lead_idx"]),
                "Lead_num": int(match["Lead_num"]),
                "MNI_x": float(match["MNI_x"]),
                "MNI_y": float(match["MNI_y"]),
                "MNI_z": float(match["MNI_z"]),
                "MNI_x_flip": float(match["MNI_x_flip"]),
                "MNI_y_flip": float(match["MNI_y_flip"]),
                "MNI_z_flip": float(match["MNI_z_flip"]),
                "SNr_in": bool(match["SNr_in"]),
                "SNr_x": float(match["SNr_x"]),
                "SNr_y": float(match["SNr_y"]),
                "SNr_z": float(match["SNr_z"]),
                "STN_in": bool(match["STN_in"]),
                "STN_x": float(match["STN_x"]),
                "STN_y": float(match["STN_y"]),
                "STN_z": float(match["STN_z"]),
                "lead_model": electrode["lead"],
                "lead_dist_mm": json.dumps(electrode["dist"], ensure_ascii=False),
                "lead_offset_mm": json.dumps(electrode["offset"], ensure_ascii=False),
                "units": config.get("units", "mm"),
                "active_scale_row": int(scale_row["active_scale_row"]),
                "match_distance_mm": match_distance,
            }
        )

    active = pd.DataFrame(active_rows)
    active = active[active_columns()]
    validate_active_dataset(active, match_tolerance_mm)

    active_csv = output_dir / "active_contacts.csv"
    info_json = output_dir / "active_contacts_info.json"
    active.to_csv(active_csv, index=False)

    info = build_info(
        active,
        scale,
        reco,
        config,
        scale_xlsx,
        contact_reco_pkl,
        subject_coords_config_json,
        active_csv,
        info_json,
        match_tolerance_mm,
    )
    info_json.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")

    return {
        "active_csv": str(active_csv),
        "info_json": str(info_json),
        "active_contacts": len(active),
        "active_subjects": int(active["Subject"].nunique()),
        "max_match_distance_mm": float(active["match_distance_mm"].max()),
        "region_counts": active["Region"].value_counts().to_dict(),
    }


def normalize_subject(value: Any) -> str:
    text = str(value)
    if text.startswith("Sub-"):
        return "sub-" + text[4:]
    return text


def electrode_config_for_match(config: dict[str, Any], match: pd.Series) -> dict[str, Any]:
    subjects = config["subjects"]
    subject_key = str(match["subject_key"])
    if subject_key not in subjects:
        raise ValueError(f"No electrode config found for subject {subject_key}.")

    side_key = {"Left": "L", "Right": "R"}.get(str(match["Side"]))
    if side_key is None:
        raise ValueError(f"Unsupported contact side for electrode config lookup: {match['Side']!r}.")

    subject_config = subjects[subject_key]
    if side_key not in subject_config:
        raise ValueError(f"No {side_key} electrode config found for subject {subject_key}.")

    electrode = subject_config[side_key]
    for field in ["lead", "dist", "offset"]:
        if field not in electrode:
            raise ValueError(f"Electrode config for {subject_key} {side_key} is missing {field!r}.")
    return electrode


def validate_active_dataset(active: pd.DataFrame, match_tolerance_mm: float) -> None:
    if len(active) != 64:
        raise ValueError(f"Expected 64 active contacts, found {len(active)}.")
    if active["Subject"].nunique() != 16:
        raise ValueError(f"Expected 16 active subjects, found {active['Subject'].nunique()}.")
    if (active["match_distance_mm"] > match_tolerance_mm).any():
        bad = active[active["match_distance_mm"] > match_tolerance_mm]
        raise ValueError(f"{len(bad)} active contacts exceed match tolerance.")
    duplicates = active.duplicated(["subject_key", "Contact"], keep=False)
    if duplicates.any():
        raise ValueError("Duplicate (subject_key, Contact) rows found in active contacts.")

    region_counts = active["Region"].value_counts().to_dict()
    if region_counts != EXPECTED_REGION_COUNTS:
        raise ValueError(f"Unexpected Region counts: {region_counts}; expected {EXPECTED_REGION_COUNTS}.")

    if active[["lead_model", "lead_dist_mm", "lead_offset_mm"]].isna().any().any():
        raise ValueError("Missing electrode fields in active contacts.")


def build_info(
    active: pd.DataFrame,
    scale: pd.DataFrame,
    reco: pd.DataFrame,
    config: dict[str, Any],
    scale_xlsx: Path,
    contact_reco_pkl: Path,
    subject_coords_config_json: Path,
    active_csv: Path,
    info_json: Path,
    match_tolerance_mm: float,
) -> dict[str, Any]:
    return {
        "name": "STN/SNr active contact coordinate dataset",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "match_rule": {
            "subject_key": "normalize Subject by converting leading 'Sub-' to 'sub-'",
            "coordinate_columns": ["MNI_x_flip", "MNI_y_flip", "MNI_z_flip"],
            "method": "nearest reconstructed contact within same subject",
            "max_allowed_distance_mm": match_tolerance_mm,
        },
        "inputs": {
            "scale_contact_only_xlsx": file_info(scale_xlsx),
            "contact_reco_space_locs_pkl": file_info(contact_reco_pkl),
            "subject_coords_config_json": file_info(subject_coords_config_json),
        },
        "outputs": {
            "active_contacts_csv": str(active_csv),
            "active_contacts_info_json": str(info_json),
        },
        "source_row_counts": {
            "scale_contact_only_rows": int(len(scale)),
            "contact_reco_rows": int(len(reco)),
            "subject_coords_config_subjects": int(len(config["subjects"])),
        },
        "qc": {
            "active_contacts": int(len(active)),
            "active_subjects": int(active["Subject"].nunique()),
            "max_match_distance_mm": float(active["match_distance_mm"].max()),
            "region_counts": int_key_counts(active["Region"].value_counts().to_dict()),
            "expected_region_counts": EXPECTED_REGION_COUNTS,
            "contact_counts": int_key_counts(active["Contact"].value_counts().sort_index().to_dict()),
            "subject_active_counts": int_key_counts(active["Subject"].value_counts().sort_index().to_dict()),
            "lead_model_counts": int_key_counts(active["lead_model"].value_counts().to_dict()),
        },
        "schema": dataset_schema(),
        "notes": [
            "This dataset includes only subjects and contacts present in scale_contact_only.xlsx.",
            "Programming/stimulation parameters are intentionally excluded and should be joined later.",
            "lead_dist_mm and lead_offset_mm are JSON-encoded arrays in CSV cells.",
        ],
    }


def active_columns() -> list[str]:
    return [
        "ID",
        "Subject",
        "subject_key",
        "Contact",
        "Region",
        "Side",
        "Hemi",
        "Lead_idx",
        "Lead_num",
        "MNI_x",
        "MNI_y",
        "MNI_z",
        "MNI_x_flip",
        "MNI_y_flip",
        "MNI_z_flip",
        "SNr_in",
        "SNr_x",
        "SNr_y",
        "SNr_z",
        "STN_in",
        "STN_x",
        "STN_y",
        "STN_z",
        "lead_model",
        "lead_dist_mm",
        "lead_offset_mm",
        "units",
        "active_scale_row",
        "match_distance_mm",
    ]


def dataset_schema() -> dict[str, str]:
    return {
        "ID": "Clinical/reconstruction subject ID from contact_reco_space_locs.pkl.",
        "Subject": "Subject name from contact reconstruction table.",
        "subject_key": "Normalized subject identifier used for joins.",
        "Contact": "Global contact index from contact reconstruction table.",
        "Region": "Contact region label from contact reconstruction table.",
        "Side": "Contact side label.",
        "Hemi": "Hemisphere classification from contact reconstruction table.",
        "Lead_idx": "Lead index from contact reconstruction table.",
        "Lead_num": "Lead number from contact reconstruction table.",
        "MNI_x/MNI_y/MNI_z": "Original MNI coordinate from contact reconstruction table.",
        "MNI_x_flip/MNI_y_flip/MNI_z_flip": "Flipped MNI coordinate used for active-contact matching.",
        "SNr_in": "Whether the contact is marked inside SNr in contact reconstruction table.",
        "SNr_x/SNr_y/SNr_z": "SNr-relative coordinate fields from contact reconstruction table.",
        "STN_in": "Whether the contact is marked inside STN in contact reconstruction table.",
        "STN_x/STN_y/STN_z": "STN-relative coordinate fields from contact reconstruction table.",
        "lead_model": "Electrode model from subject_coords_config.json.",
        "lead_dist_mm": "JSON-encoded contact distance array from subject_coords_config.json.",
        "lead_offset_mm": "JSON-encoded offset array from subject_coords_config.json.",
        "units": "Units from subject_coords_config.json.",
        "active_scale_row": "Zero-based row index in scale_contact_only.xlsx.",
        "match_distance_mm": "Nearest-neighbor distance between active Excel coordinate and matched reconstructed contact.",
    }


def validate_required_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def int_key_counts(counts: dict[Any, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in counts.items()}


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")


def main() -> None:
    result = build_active_contact_dataset()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
