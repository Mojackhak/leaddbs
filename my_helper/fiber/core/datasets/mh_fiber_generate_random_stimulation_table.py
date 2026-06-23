#!/usr/bin/env python3
"""Generate a reproducible random test stimulation table for STN/SNr active contacts."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ACTIVE_CONTACTS_CSV = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/active_contacts.csv"
)
OUTPUT_DIR = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset"
)
OUTPUT_CSV = OUTPUT_DIR / "random_stimulation_parameters.csv"
OUTPUT_INFO_JSON = OUTPUT_DIR / "random_stimulation_parameters_info.json"

RANDOM_SEED = 20260624
VOLTAGE_RANGE_V = (2.0, 4.0)
PULSE_WIDTH_RANGE_US = (50, 90)
FREQUENCY_RANGES_HZ = {
    "SNr": (15, 40),
    "STN": (120, 180),
}


def generate_random_stimulation_table(
    active_contacts_csv: Path = ACTIVE_CONTACTS_CSV,
    output_csv: Path = OUTPUT_CSV,
    info_json: Path = OUTPUT_INFO_JSON,
    random_seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Generate random stimulation parameters for every active-contact row."""

    require_file(active_contacts_csv, "active contact CSV")
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    active = pd.read_csv(active_contacts_csv)
    validate_active_contacts(active)

    rng = np.random.default_rng(random_seed)
    rows: list[dict[str, Any]] = []
    for active_row_index, active_row in active.reset_index(drop=True).iterrows():
        frequency_group, frequency_rule = frequency_group_for_contact(active_row)
        frequency_min, frequency_max = FREQUENCY_RANGES_HZ[frequency_group]

        voltage = float(np.round(rng.uniform(VOLTAGE_RANGE_V[0], VOLTAGE_RANGE_V[1]), 1))
        pulse_width = int(rng.integers(PULSE_WIDTH_RANGE_US[0], PULSE_WIDTH_RANGE_US[1] + 1))
        frequency = int(rng.integers(frequency_min, frequency_max + 1))

        rows.append(
            {
                "ID": active_row["ID"],
                "Subject": active_row["Subject"],
                "subject_key": active_row["subject_key"],
                "Contact": int(active_row["Contact"]),
                "lead_contact": int(active_row["Contact"]) + 1,
                "Region": active_row["Region"],
                "Side": active_row["Side"],
                "side_code": side_code(active_row["Side"]),
                "Hemi": active_row["Hemi"],
                "Lead_idx": int(active_row["Lead_idx"]),
                "Lead_num": int(active_row["Lead_num"]),
                "MNI_x_flip": float(active_row["MNI_x_flip"]),
                "MNI_y_flip": float(active_row["MNI_y_flip"]),
                "MNI_z_flip": float(active_row["MNI_z_flip"]),
                "frequency_group": frequency_group,
                "frequency_rule": frequency_rule,
                "voltage_V": voltage,
                "pulse_width_us": pulse_width,
                "frequency_Hz": frequency,
                "unit": "V",
                "cathode": True,
                "anode": "case",
                "random_seed": int(random_seed),
                "active_contacts_row": int(active_row_index),
            }
        )

    stimulation = pd.DataFrame(rows)
    stimulation = stimulation[stimulation_columns()]
    validate_stimulation_table(stimulation)
    stimulation.to_csv(output_csv, index=False)

    info = build_info(active, stimulation, active_contacts_csv, output_csv, info_json, random_seed)
    info_json.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")

    return {
        "stimulation_csv": str(output_csv),
        "info_json": str(info_json),
        "rows": int(len(stimulation)),
        "subjects": int(stimulation["Subject"].nunique()),
        "random_seed": int(random_seed),
        "frequency_group_counts": int_key_counts(
            stimulation["frequency_group"].value_counts().to_dict()
        ),
        "region_counts": int_key_counts(stimulation["Region"].value_counts().to_dict()),
        "voltage_range_V": [
            float(stimulation["voltage_V"].min()),
            float(stimulation["voltage_V"].max()),
        ],
        "pulse_width_range_us": [
            int(stimulation["pulse_width_us"].min()),
            int(stimulation["pulse_width_us"].max()),
        ],
        "frequency_range_Hz": [
            int(stimulation["frequency_Hz"].min()),
            int(stimulation["frequency_Hz"].max()),
        ],
    }


def frequency_group_for_contact(row: pd.Series) -> tuple[str, str]:
    region = str(row["Region"])
    if region in FREQUENCY_RANGES_HZ:
        return region, "region"

    snr_norm = coordinate_norm(row, "SNr")
    stn_norm = coordinate_norm(row, "STN")
    if snr_norm < stn_norm:
        return "SNr", "nearest_target_from_relative_coordinates"
    return "STN", "nearest_target_from_relative_coordinates"


def coordinate_norm(row: pd.Series, prefix: str) -> float:
    coords = np.array([row[f"{prefix}_x"], row[f"{prefix}_y"], row[f"{prefix}_z"]], dtype=float)
    return float(np.linalg.norm(coords))


def side_code(side: Any) -> str:
    mapping = {"Left": "L", "Right": "R", "L": "L", "R": "R"}
    text = str(side)
    if text not in mapping:
        raise ValueError(f"Unsupported side value: {side!r}")
    return mapping[text]


def validate_active_contacts(active: pd.DataFrame) -> None:
    validate_required_columns(
        active,
        [
            "ID",
            "Subject",
            "subject_key",
            "Contact",
            "Region",
            "Side",
            "Hemi",
            "Lead_idx",
            "Lead_num",
            "MNI_x_flip",
            "MNI_y_flip",
            "MNI_z_flip",
            "SNr_x",
            "SNr_y",
            "SNr_z",
            "STN_x",
            "STN_y",
            "STN_z",
        ],
        "active_contacts.csv",
    )
    if len(active) != 64:
        raise ValueError(f"Expected 64 active contacts, found {len(active)}.")
    if active["Subject"].nunique() != 16:
        raise ValueError(f"Expected 16 active subjects, found {active['Subject'].nunique()}.")
    duplicates = active.duplicated(["subject_key", "Contact"], keep=False)
    if duplicates.any():
        raise ValueError("Duplicate (subject_key, Contact) rows found in active contacts.")


def validate_stimulation_table(stimulation: pd.DataFrame) -> None:
    if len(stimulation) != 64:
        raise ValueError(f"Expected 64 stimulation rows, found {len(stimulation)}.")
    if stimulation["Subject"].nunique() != 16:
        raise ValueError(f"Expected 16 subjects, found {stimulation['Subject'].nunique()}.")
    if stimulation.duplicated(["subject_key", "Contact"], keep=False).any():
        raise ValueError("Duplicate (subject_key, Contact) rows found in stimulation table.")
    if not stimulation["voltage_V"].between(*VOLTAGE_RANGE_V).all():
        raise ValueError("Voltage values are outside the configured test range.")
    if not stimulation["pulse_width_us"].between(*PULSE_WIDTH_RANGE_US).all():
        raise ValueError("Pulse-width values are outside the configured test range.")

    for frequency_group, (low, high) in FREQUENCY_RANGES_HZ.items():
        group_rows = stimulation[stimulation["frequency_group"] == frequency_group]
        if group_rows.empty:
            continue
        if not group_rows["frequency_Hz"].between(low, high).all():
            raise ValueError(f"{frequency_group} frequency values are outside {low}-{high} Hz.")


def build_info(
    active: pd.DataFrame,
    stimulation: pd.DataFrame,
    active_contacts_csv: Path,
    output_csv: Path,
    info_json: Path,
    random_seed: int,
) -> dict[str, Any]:
    return {
        "name": "STN/SNr random test stimulation parameter table",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "random_seed": int(random_seed),
        "inputs": {
            "active_contacts_csv": file_info(active_contacts_csv),
        },
        "outputs": {
            "random_stimulation_parameters_csv": str(output_csv),
            "random_stimulation_parameters_info_json": str(info_json),
        },
        "randomization": {
            "voltage_V": {
                "distribution": "uniform",
                "minimum": VOLTAGE_RANGE_V[0],
                "maximum": VOLTAGE_RANGE_V[1],
                "round_decimals": 1,
            },
            "pulse_width_us": {
                "distribution": "discrete_uniform_integer",
                "minimum": PULSE_WIDTH_RANGE_US[0],
                "maximum": PULSE_WIDTH_RANGE_US[1],
            },
            "frequency_Hz": {
                "SNr": {
                    "distribution": "discrete_uniform_integer",
                    "minimum": FREQUENCY_RANGES_HZ["SNr"][0],
                    "maximum": FREQUENCY_RANGES_HZ["SNr"][1],
                },
                "STN": {
                    "distribution": "discrete_uniform_integer",
                    "minimum": FREQUENCY_RANGES_HZ["STN"][0],
                    "maximum": FREQUENCY_RANGES_HZ["STN"][1],
                },
            },
            "non_target_region_rule": (
                "Rows with Region other than SNr/STN are assigned to the nearest target by "
                "the Euclidean norm of SNr_x/SNr_y/SNr_z versus STN_x/STN_y/STN_z."
            ),
        },
        "qc": {
            "active_contacts_rows": int(len(active)),
            "stimulation_rows": int(len(stimulation)),
            "subjects": int(stimulation["Subject"].nunique()),
            "region_counts": int_key_counts(stimulation["Region"].value_counts().to_dict()),
            "frequency_group_counts": int_key_counts(
                stimulation["frequency_group"].value_counts().to_dict()
            ),
            "frequency_rule_counts": int_key_counts(
                stimulation["frequency_rule"].value_counts().to_dict()
            ),
            "voltage_range_V": [
                float(stimulation["voltage_V"].min()),
                float(stimulation["voltage_V"].max()),
            ],
            "pulse_width_range_us": [
                int(stimulation["pulse_width_us"].min()),
                int(stimulation["pulse_width_us"].max()),
            ],
            "frequency_range_Hz": [
                int(stimulation["frequency_Hz"].min()),
                int(stimulation["frequency_Hz"].max()),
            ],
        },
        "schema": stimulation_schema(),
        "notes": [
            "This table is for testing only and is not a clinical programming record.",
            "lead_contact is one-based and can be passed to helpers that require Lead-DBS contact numbering.",
            "Contact preserves the source contact index from active_contacts.csv.",
        ],
    }


def stimulation_columns() -> list[str]:
    return [
        "ID",
        "Subject",
        "subject_key",
        "Contact",
        "lead_contact",
        "Region",
        "Side",
        "side_code",
        "Hemi",
        "Lead_idx",
        "Lead_num",
        "MNI_x_flip",
        "MNI_y_flip",
        "MNI_z_flip",
        "frequency_group",
        "frequency_rule",
        "voltage_V",
        "pulse_width_us",
        "frequency_Hz",
        "unit",
        "cathode",
        "anode",
        "random_seed",
        "active_contacts_row",
    ]


def stimulation_schema() -> dict[str, str]:
    return {
        "ID": "Clinical/reconstruction subject ID from active_contacts.csv.",
        "Subject": "Subject name from active_contacts.csv.",
        "subject_key": "Normalized subject identifier used for joins.",
        "Contact": "Source contact index from active_contacts.csv.",
        "lead_contact": "One-based contact index for Lead-DBS stimulation helpers.",
        "Region": "Contact region label from active_contacts.csv.",
        "Side": "Contact side label.",
        "side_code": "Single-letter side code, L or R.",
        "Hemi": "Hemisphere classification from active_contacts.csv.",
        "Lead_idx": "Lead index from active_contacts.csv.",
        "Lead_num": "Lead number from active_contacts.csv.",
        "MNI_x_flip/MNI_y_flip/MNI_z_flip": "Flipped MNI coordinate from active_contacts.csv.",
        "frequency_group": "Target group used to choose the frequency range.",
        "frequency_rule": "Rule used to assign frequency_group.",
        "voltage_V": "Random test voltage in volts.",
        "pulse_width_us": "Random test pulse width in microseconds.",
        "frequency_Hz": "Random test frequency in hertz.",
        "unit": "Voltage unit.",
        "cathode": "Whether the contact is treated as a cathode.",
        "anode": "Anode label.",
        "random_seed": "Random seed used for reproducible generation.",
        "active_contacts_row": "Zero-based row index in active_contacts.csv.",
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
    result = generate_random_stimulation_table()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
