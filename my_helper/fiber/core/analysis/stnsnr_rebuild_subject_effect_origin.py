#!/usr/bin/env python3
"""Rebuild subject_effect_origin.xlsx from the raw scale_subject workbook."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TRUE_RAW = Path("/Users/mojackhu/Research/STNSNr/summary/stats/clinic/effect/3m/scale_subject.xlsx")
DEFAULT_CLINICAL_ROOT = Path("/Users/mojackhu/Research/STNSNr/summary/cohort/subj")
DEFAULT_TARGET = DEFAULT_CLINICAL_ROOT / "subject_effect_origin.xlsx"
DEFAULT_SUBJ_EFFECT = DEFAULT_CLINICAL_ROOT / "subj_effect.xlsx"
DEFAULT_SUBJ_DELTA_EFFECT = DEFAULT_CLINICAL_ROOT / "subj_delta_effect.xlsx"
DEFAULT_STIM = DEFAULT_CLINICAL_ROOT / "followup_stimulation.xlsx"
DEFAULT_CONTACT_COORDS = Path("/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/active_contacts.csv")
DEFAULT_STALE_ROOT = Path("/Volumes/VAL/STNSNr/summary/direct_voxel/hf")

OUTPUT_COLUMNS = [
    "ID",
    "Protocol",
    "Phase",
    "Scale",
    "Value",
    "Baseline",
    "Contact",
    "MNI_x_flip",
    "MNI_y_flip",
    "MNI_z_flip",
]

CONDITION_TO_PROTOCOL_PHASE = {
    "STN (3 m)": ("STN", "3m"),
    "STN+SNr (3 m)": ("STN+SNr", "3m"),
    "STN (immediate)": ("STN", "immediate"),
    "STN+SNr (immediate)": ("STN+SNr", "immediate"),
}

REFERENCE_LABEL_TO_FEATURE = {
    "UPDRS-III": "MDS-UPDRS III score",
    "UPDRS-III axial": "MDS-UPDRS III axial score",
    "FOG-Q": "FOGQ score",
    "PDQ-39": "PDQ39 score",
    "KPPS": "KPPS score",
    "MADRS": "MADRS score",
    "ADL": "ADL",
    "SE-ADL": "SE-ADL score (%)",
}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sanitize_id(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def finite_or_nan(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


def mean_or_nan(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.mean()) if not numeric.empty else math.nan


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def build_old_metadata(old_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, float]]:
    metadata: dict[tuple[str, str, str], dict[str, float]] = {}
    if old_df.empty:
        return metadata
    required = {"ID", "Protocol", "Phase", "Contact", "MNI_x_flip", "MNI_y_flip", "MNI_z_flip"}
    if not required.issubset(old_df.columns):
        return metadata
    for (subject_id, protocol, phase), group in old_df.groupby(["ID", "Protocol", "Phase"], dropna=False):
        metadata[(sanitize_id(subject_id), str(protocol), str(phase))] = {
            "Contact": mean_or_nan(group["Contact"]),
            "MNI_x_flip": mean_or_nan(group["MNI_x_flip"]),
            "MNI_y_flip": mean_or_nan(group["MNI_y_flip"]),
            "MNI_z_flip": mean_or_nan(group["MNI_z_flip"]),
        }
    return metadata


def build_stim_metadata(stim_df: pd.DataFrame, coords_df: pd.DataFrame) -> tuple[dict[tuple[str, str, str], dict[str, float]], list[dict[str, Any]]]:
    if stim_df.empty:
        return {}, []
    side_map = {"Left": "L", "Right": "R"}
    coord_cols = ["ID", "Contact", "region_programming", "Side", "MNI_x_flip", "MNI_y_flip", "MNI_z_flip"]
    coords = coords_df[coord_cols].copy() if set(coord_cols).issubset(coords_df.columns) else pd.DataFrame(columns=coord_cols)
    coords = coords.rename(columns={"region_programming": "Target"})
    coords["ID"] = coords["ID"].map(sanitize_id)
    coords["Side"] = coords["Side"].map(side_map).fillna(coords["Side"])
    coords["Contact"] = pd.to_numeric(coords["Contact"], errors="coerce")

    rows = stim_df.copy()
    rows["ID"] = rows["ID"].map(sanitize_id)
    rows["Contact"] = pd.to_numeric(rows["Contact"], errors="coerce")
    merged = rows.merge(coords, on=["ID", "Contact", "Target", "Side"], how="left", indicator=True)
    qc_rows: list[dict[str, Any]] = []
    metadata: dict[tuple[str, str, str], dict[str, float]] = {}
    for (subject_id, protocol, phase), group in merged.groupby(["ID", "Protocol", "Phase"], dropna=False):
        key = (sanitize_id(subject_id), str(protocol), str(phase))
        matched = group[group["_merge"].eq("both")]
        metadata[key] = {
            "Contact": mean_or_nan(group["Contact"]),
            "MNI_x_flip": mean_or_nan(matched["MNI_x_flip"]),
            "MNI_y_flip": mean_or_nan(matched["MNI_y_flip"]),
            "MNI_z_flip": mean_or_nan(matched["MNI_z_flip"]),
        }
        qc_rows.append(
            {
                "check_type": "metadata_join",
                "item": f"{subject_id}|{protocol}|{phase}",
                "subject_id": sanitize_id(subject_id),
                "scale": "",
                "condition": "",
                "reference_column": "",
                "computed": int(len(matched)),
                "reference": int(len(group)),
                "diff": int(len(group) - len(matched)),
                "status": "PASS" if len(matched) == len(group) else "WARN",
                "detail": f"{len(matched)}/{len(group)} stimulation contact rows matched to coordinates",
            }
        )
    return metadata, qc_rows


def metadata_for(
    subject_id: str,
    protocol: str,
    phase: str,
    old_metadata: dict[tuple[str, str, str], dict[str, float]],
    stim_metadata: dict[tuple[str, str, str], dict[str, float]],
) -> dict[str, float]:
    key = (subject_id, protocol, phase)
    if phase == "3m" and key in old_metadata:
        return old_metadata[key]
    return stim_metadata.get(key, {"Contact": math.nan, "MNI_x_flip": math.nan, "MNI_y_flip": math.nan, "MNI_z_flip": math.nan})


def build_raw_origin(
    true_raw_df: pd.DataFrame,
    old_metadata: dict[tuple[str, str, str], dict[str, float]],
    stim_metadata: dict[tuple[str, str, str], dict[str, float]],
) -> pd.DataFrame:
    required = {"ID", "Feature", "Condition", "Value"}
    missing = sorted(required.difference(true_raw_df.columns))
    if missing:
        raise ValueError("true raw workbook is missing " + ", ".join(missing))
    features = true_raw_df["Feature"].dropna().drop_duplicates().astype(str).tolist()
    ids = true_raw_df["ID"].dropna().drop_duplicates().map(sanitize_id).tolist()
    value_map = {
        (sanitize_id(row.ID), str(row.Feature), str(row.Condition)): row.Value
        for row in true_raw_df.itertuples(index=False)
    }
    rows: list[dict[str, Any]] = []
    for feature in features:
        available_conditions = set(true_raw_df.loc[true_raw_df["Feature"].astype(str).eq(feature), "Condition"].astype(str))
        for condition, (protocol, phase) in CONDITION_TO_PROTOCOL_PHASE.items():
            if condition not in available_conditions:
                continue
            for subject_id in ids:
                baseline = value_map.get((subject_id, feature, "Pre-op"), math.nan)
                value = value_map.get((subject_id, feature, condition), math.nan)
                metadata = metadata_for(subject_id, protocol, phase, old_metadata, stim_metadata)
                rows.append(
                    {
                        "ID": subject_id,
                        "Protocol": protocol,
                        "Phase": phase,
                        "Scale": feature,
                        "Value": value,
                        "Baseline": baseline,
                        "Contact": metadata.get("Contact", math.nan),
                        "MNI_x_flip": metadata.get("MNI_x_flip", math.nan),
                        "MNI_y_flip": metadata.get("MNI_y_flip", math.nan),
                        "MNI_z_flip": metadata.get("MNI_z_flip", math.nan),
                    }
                )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def value_lookup(origin_df: pd.DataFrame) -> dict[tuple[str, str, str, str], tuple[float, float]]:
    lookup: dict[tuple[str, str, str, str], tuple[float, float]] = {}
    for row in origin_df.itertuples(index=False):
        lookup[(sanitize_id(row.ID), str(row.Scale), str(row.Protocol), str(row.Phase))] = (finite_or_nan(row.Value), finite_or_nan(row.Baseline))
    return lookup


def improvement_percent(raw_post: float, baseline: float, higher_is_better: bool) -> float:
    if not math.isfinite(baseline) or baseline == 0 or not math.isfinite(raw_post):
        return math.nan
    if higher_is_better:
        return (raw_post - baseline) / baseline * 100.0
    return (baseline - raw_post) / baseline * 100.0


def compare_value(
    qc_rows: list[dict[str, Any]],
    check_type: str,
    item: str,
    subject_id: str,
    scale: str,
    condition: str,
    reference_column: str,
    computed: float,
    reference: float,
    tolerance: float,
    relaxed_tolerance: float,
    detail: str = "",
) -> None:
    comp = finite_or_nan(computed)
    ref = finite_or_nan(reference)
    if not math.isfinite(comp) and not math.isfinite(ref):
        status = "PASS"
        diff = math.nan
    elif math.isfinite(comp) and math.isfinite(ref):
        diff = comp - ref
        abs_diff = abs(diff)
        if abs_diff <= tolerance:
            status = "PASS"
        elif abs_diff <= relaxed_tolerance:
            status = "PASS_RELAXED"
        else:
            status = "FAIL"
    else:
        diff = math.nan
        status = "FAIL"
    qc_rows.append(
        {
            "check_type": check_type,
            "item": item,
            "subject_id": subject_id,
            "scale": scale,
            "condition": condition,
            "reference_column": reference_column,
            "computed": comp,
            "reference": ref,
            "diff": diff,
            "status": status,
            "detail": detail,
        }
    )


def add_zero_baseline_check(
    qc_rows: list[dict[str, Any]],
    check_type: str,
    item: str,
    subject_id: str,
    scale: str,
    condition: str,
    reference_column: str,
    reference: float,
) -> None:
    ref = finite_or_nan(reference)
    status = "PASS" if (not math.isfinite(ref)) or abs(ref) <= 1e-12 else "FAIL"
    detail = "zero_baseline_reference_missing" if not math.isfinite(ref) else "zero_baseline_reference_zero"
    qc_rows.append(
        {
            "check_type": check_type,
            "item": item,
            "subject_id": subject_id,
            "scale": scale,
            "condition": condition,
            "reference_column": reference_column,
            "computed": math.nan,
            "reference": ref,
            "diff": math.nan,
            "status": status,
            "detail": detail if status == "PASS" else "zero_baseline_reference_nonzero",
        }
    )


def validate_subj_effect(
    origin_df: pd.DataFrame,
    subj_effect_df: pd.DataFrame,
    qc_rows: list[dict[str, Any]],
    tolerance: float,
    relaxed_tolerance: float,
) -> None:
    lookup = value_lookup(origin_df)
    condition_columns = [
        ("STN", "immediate", "STN, immed"),
        ("STN", "3m", "STN, 3m"),
        ("STN+SNr", "immediate", "STN+SNr, immed"),
        ("STN+SNr", "3m", "STN+SNr, 3m"),
    ]
    for label, feature in REFERENCE_LABEL_TO_FEATURE.items():
        higher = feature == "SE-ADL score (%)"
        for protocol, phase, suffix in condition_columns:
            column = f"{label} Δ% ({suffix})"
            if column not in subj_effect_df.columns:
                continue
            for _, row in subj_effect_df.iterrows():
                subject_id = sanitize_id(row["ID"])
                raw_post, baseline = lookup.get((subject_id, feature, protocol, phase), (math.nan, math.nan))
                reference = row[column]
                if not math.isfinite(baseline) or baseline == 0:
                    add_zero_baseline_check(qc_rows, "subj_effect", column, subject_id, feature, f"{protocol}|{phase}", column, reference)
                    continue
                computed = improvement_percent(raw_post, baseline, higher)
                compare_value(qc_rows, "subj_effect", column, subject_id, feature, f"{protocol}|{phase}", column, computed, reference, tolerance, relaxed_tolerance)


def validate_subj_delta_effect(
    origin_df: pd.DataFrame,
    subj_delta_df: pd.DataFrame,
    qc_rows: list[dict[str, Any]],
    tolerance: float,
    relaxed_tolerance: float,
) -> None:
    lookup = value_lookup(origin_df)
    for label, feature in REFERENCE_LABEL_TO_FEATURE.items():
        higher = feature == "SE-ADL score (%)"
        for phase, suffix in [("immediate", "immed"), ("3m", "3m")]:
            stn_column = f"{label} Δ% (STN, {suffix})"
            delta_column = f"Δ{label} Δ% (+SNr, {suffix})"
            if stn_column not in subj_delta_df.columns and delta_column not in subj_delta_df.columns:
                continue
            for _, row in subj_delta_df.iterrows():
                subject_id = sanitize_id(row["ID"])
                stn_raw, baseline = lookup.get((subject_id, feature, "STN", phase), (math.nan, math.nan))
                post_raw, post_baseline = lookup.get((subject_id, feature, "STN+SNr", phase), (math.nan, math.nan))
                baseline = baseline if math.isfinite(baseline) else post_baseline
                if stn_column in subj_delta_df.columns:
                    if not math.isfinite(baseline) or baseline == 0:
                        add_zero_baseline_check(qc_rows, "subj_delta_effect", stn_column, subject_id, feature, f"STN|{phase}", stn_column, row[stn_column])
                    else:
                        computed_stn = improvement_percent(stn_raw, baseline, higher)
                        compare_value(qc_rows, "subj_delta_effect", stn_column, subject_id, feature, f"STN|{phase}", stn_column, computed_stn, row[stn_column], tolerance, relaxed_tolerance)
                if delta_column in subj_delta_df.columns:
                    if not math.isfinite(baseline) or baseline == 0:
                        add_zero_baseline_check(qc_rows, "subj_delta_effect", delta_column, subject_id, feature, f"STN+SNr-STN|{phase}", delta_column, row[delta_column])
                    else:
                        computed_stn = improvement_percent(stn_raw, baseline, higher)
                        computed_post = improvement_percent(post_raw, baseline, higher)
                        computed_delta = computed_post - computed_stn
                        compare_value(
                            qc_rows,
                            "subj_delta_effect",
                            delta_column,
                            subject_id,
                            feature,
                            f"STN+SNr-STN|{phase}",
                            delta_column,
                            computed_delta,
                            row[delta_column],
                            tolerance,
                            relaxed_tolerance,
                        )


def spot_checks(origin_df: pd.DataFrame, qc_rows: list[dict[str, Any]], tolerance: float) -> None:
    checks = [
        ("SNr003", "MDS-UPDRS III score", "STN", "3m", 34, 40),
        ("SNr003", "MDS-UPDRS III score", "STN+SNr", "3m", 22, 40),
        ("SNr003", "MDS-UPDRS III score", "STN+SNr", "immediate", 17, 40),
        ("SNr003", "SE-ADL score (%)", "STN+SNr", "3m", 90, 50),
    ]
    lookup = value_lookup(origin_df)
    for subject_id, scale, protocol, phase, expected_value, expected_baseline in checks:
        value, baseline = lookup.get((subject_id, scale, protocol, phase), (math.nan, math.nan))
        compare_value(qc_rows, "spot_check", "Value", subject_id, scale, f"{protocol}|{phase}", "expected_value", value, expected_value, tolerance, tolerance)
        compare_value(qc_rows, "spot_check", "Baseline", subject_id, scale, f"{protocol}|{phase}", "expected_baseline", baseline, expected_baseline, tolerance, tolerance)


def validate_structure(origin_df: pd.DataFrame, qc_rows: list[dict[str, Any]]) -> None:
    expected_scales = 28
    expected_rows = 960
    checks = [
        ("row_count", len(origin_df), expected_rows),
        ("scale_count", origin_df["Scale"].nunique(), expected_scales),
        ("delta_scale_count", int(origin_df["Scale"].astype(str).str.startswith("Δ").sum()), 0),
        ("required_value_missing", int(origin_df[["ID", "Protocol", "Phase", "Scale", "Value", "Baseline"]].isna().any(axis=1).sum()), 0),
    ]
    for item, computed, reference in checks:
        status = "PASS" if computed == reference else "FAIL"
        qc_rows.append(
            {
                "check_type": "structure",
                "item": item,
                "subject_id": "",
                "scale": "",
                "condition": "",
                "reference_column": "",
                "computed": computed,
                "reference": reference,
                "diff": computed - reference,
                "status": status,
                "detail": "",
            }
        )


def move_to_trash(path: Path) -> Path:
    trash = Path.home() / ".Trash"
    trash.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = trash / f"{path.stem}_old_{timestamp}{path.suffix}"
    counter = 1
    while destination.exists():
        destination = trash / f"{path.stem}_old_{timestamp}_{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(destination))
    return destination


def mark_stale_outputs(stale_root: Path, manifest: dict[str, Any]) -> Path | None:
    if not stale_root.exists():
        return None
    path = stale_root / "stale_due_to_subject_effect_origin_rebuild.json"
    write_json(
        path,
        {
            "generated_at": iso_now(),
            "reason": "subject_effect_origin.xlsx was rebuilt from raw scale_subject.xlsx; previous HF direct voxel post-hoc outputs used stale clinical endpoint semantics",
            "subject_effect_origin": manifest["target_path"],
            "rebuild_manifest": manifest["manifest_path"],
        },
    )
    return path


def run(args: argparse.Namespace) -> int:
    true_raw_path = Path(args.true_raw).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve()
    old_path = target_path
    subj_effect_path = Path(args.subj_effect).expanduser().resolve()
    subj_delta_path = Path(args.subj_delta_effect).expanduser().resolve()
    stim_path = Path(args.stim).expanduser().resolve()
    coords_path = Path(args.contact_coords).expanduser().resolve()
    qc_path = target_path.with_name("subject_effect_origin_rebuild_qc.csv")
    manifest_path = target_path.with_name("subject_effect_origin_rebuild_manifest.json")
    tmp_path = target_path.with_name(f".{target_path.stem}_new_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target_path.suffix}")

    true_raw_df = pd.read_excel(true_raw_path)
    old_df = pd.read_excel(old_path) if old_path.is_file() else pd.DataFrame()
    stim_df = pd.read_excel(stim_path, sheet_name="Contact Parameters")
    coords_df = pd.read_csv(coords_path)
    old_metadata = build_old_metadata(old_df)
    stim_metadata, metadata_qc = build_stim_metadata(stim_df, coords_df)
    origin_df = build_raw_origin(true_raw_df, old_metadata, stim_metadata)

    qc_rows: list[dict[str, Any]] = []
    qc_rows.extend(metadata_qc)
    validate_structure(origin_df, qc_rows)
    spot_checks(origin_df, qc_rows, args.tolerance)
    validate_subj_effect(origin_df, pd.read_excel(subj_effect_path), qc_rows, args.tolerance, args.relaxed_tolerance)
    validate_subj_delta_effect(origin_df, pd.read_excel(subj_delta_path), qc_rows, args.tolerance, args.relaxed_tolerance)
    qc_df = pd.DataFrame(qc_rows)
    fail_count = int(qc_df["status"].eq("FAIL").sum()) if not qc_df.empty else 0
    relaxed_count = int(qc_df["status"].eq("PASS_RELAXED").sum()) if not qc_df.empty else 0
    warn_count = int(qc_df["status"].eq("WARN").sum()) if not qc_df.empty else 0
    subj_effect_mismatch_count = int(qc_df["check_type"].eq("subj_effect").mul(qc_df["status"].eq("FAIL")).sum()) if not qc_df.empty else 0
    subj_delta_mismatch_count = int(qc_df["check_type"].eq("subj_delta_effect").mul(qc_df["status"].eq("FAIL")).sum()) if not qc_df.empty else 0
    zero_baseline_exception_count = int(qc_df["detail"].astype(str).str.startswith("zero_baseline_reference_").sum()) if not qc_df.empty else 0
    metadata_warn_count = int(qc_df["check_type"].eq("metadata_join").mul(qc_df["status"].eq("WARN")).sum()) if not qc_df.empty else 0

    if fail_count:
        qc_df.to_csv(qc_path, index=False)
        raise RuntimeError(f"subject_effect_origin rebuild validation failed with {fail_count} FAIL rows; see {qc_path}")

    origin_df.to_excel(tmp_path, index=False)
    trash_path = move_to_trash(target_path) if target_path.exists() else None
    shutil.move(str(tmp_path), str(target_path))
    qc_df.to_csv(qc_path, index=False)
    manifest = {
        "generated_at": iso_now(),
        "status": "PASS",
        "target_path": str(target_path),
        "manifest_path": str(manifest_path),
        "old_file_moved_to_trash": str(trash_path) if trash_path else "",
        "sources": {
            "true_raw": str(true_raw_path),
            "subj_effect": str(subj_effect_path),
            "subj_delta_effect": str(subj_delta_path),
            "stimulation": str(stim_path),
            "contact_coordinates": str(coords_path),
        },
        "row_count": int(len(origin_df)),
        "scale_count": int(origin_df["Scale"].nunique()),
        "subject_count": int(origin_df["ID"].nunique()),
        "phase_counts": {str(key): int(value) for key, value in origin_df["Phase"].value_counts().to_dict().items()},
        "protocol_counts": {str(key): int(value) for key, value in origin_df["Protocol"].value_counts().to_dict().items()},
        "qc_counts": {str(key): int(value) for key, value in qc_df["status"].value_counts().to_dict().items()},
        "fail_count": fail_count,
        "warn_count": warn_count,
        "pass_relaxed_count": relaxed_count,
        "subj_effect_mismatch_count": subj_effect_mismatch_count,
        "subj_delta_effect_mismatch_count": subj_delta_mismatch_count,
        "zero_baseline_exception_count": zero_baseline_exception_count,
        "metadata_warn_count": metadata_warn_count,
        "qc_csv": str(qc_path),
    }
    stale_path = mark_stale_outputs(Path(args.stale_root).expanduser().resolve(), manifest)
    if stale_path:
        manifest["stale_marker"] = str(stale_path)
    write_json(manifest_path, manifest)
    print(f"Rebuilt raw clinical origin: {target_path}")
    print(f"Old file moved to Trash: {trash_path}")
    print(f"QC: {qc_path}")
    print(f"Manifest: {manifest_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--true-raw", default=str(DEFAULT_TRUE_RAW), help="Raw scale_subject.xlsx source.")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="subject_effect_origin.xlsx target.")
    parser.add_argument("--subj-effect", default=str(DEFAULT_SUBJ_EFFECT), help="subj_effect.xlsx validation source.")
    parser.add_argument("--subj-delta-effect", default=str(DEFAULT_SUBJ_DELTA_EFFECT), help="subj_delta_effect.xlsx validation source.")
    parser.add_argument("--stim", default=str(DEFAULT_STIM), help="followup_stimulation.xlsx source.")
    parser.add_argument("--contact-coords", default=str(DEFAULT_CONTACT_COORDS), help="Contact coordinate CSV source.")
    parser.add_argument("--stale-root", default=str(DEFAULT_STALE_ROOT), help="Output root to mark stale after rebuild.")
    parser.add_argument("--tolerance", type=float, default=1e-6, help="Strict numeric tolerance.")
    parser.add_argument("--relaxed-tolerance", type=float, default=1e-4, help="Relaxed numeric tolerance.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
