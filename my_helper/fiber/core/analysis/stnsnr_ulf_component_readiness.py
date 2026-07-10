#!/usr/bin/env python3
"""ULF component readiness gate for the four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from stnsnr_four_model_readiness import parse_endpoint_scale


DEFAULT_VAL_ROOT = Path("/Volumes/VAL/STNSNr")
DEFAULT_CLINICAL_ROOT = Path("/Users/mojackhu/Research/STNSNr/summary/cohort/subj")
DEFAULT_RAW_CLINICAL = DEFAULT_CLINICAL_ROOT / "subject_effect_origin.xlsx"
DEFAULT_STIM_WORKBOOK = DEFAULT_CLINICAL_ROOT / "followup_stimulation.xlsx"
DEFAULT_STIM_SHEET = "Contact Parameters"
DEFAULT_DERIVATIVES_ROOT = DEFAULT_VAL_ROOT / "derivatives/leaddbs"
DEFAULT_GATE_STATUS = DEFAULT_VAL_ROOT / "summary/four_model_execution/gate_status/four_model_gate_status.csv"
DEFAULT_OUTPUT_ROOT = DEFAULT_VAL_ROOT / "summary/four_model_execution/ulf_component_readiness"

DEFAULT_HF_SCALE = "MDS-UPDRS III score (STN, 3 m)"
DEFAULT_ULF_POST_SCALE = "MDS-UPDRS III score (STN+SNr, 3 m)"


@dataclass
class CheckRow:
    category: str
    item: str
    status: str
    detail: str
    path: str = ""


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def timestamp_slug() -> str:
    return datetime.now().strftime("run-%Y%m%d-%H%M%S")


def sanitize(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_protocol_for_folder(protocol: Any) -> str:
    protocol_str = sanitize(protocol)
    if protocol_str == "STN+SNr":
        return "STNplusSNr"
    return protocol_str


def contact_token(value: Any) -> str:
    """Return the raw contact token used in Lead-DBS stimulation folder labels."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return sanitize(value)
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)


def classify_frequency_component(frequency_hz: Any) -> str:
    """Classify stimulation frequency into the fixed HF/ULF component labels."""
    try:
        frequency = float(frequency_hz)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if frequency >= 100:
        return "HF"
    if frequency <= 50:
        return "ULF"
    return "MID"


def component_efield_paths(derivatives_root: Path, row: dict[str, Any] | pd.Series) -> tuple[Path, Path]:
    """Return expected target-component folder and raw sim-efield path."""
    subject_id = sanitize(row.get("ID"))
    name = sanitize(row.get("NameEn"))
    phase = sanitize(row.get("Phase"))
    protocol = normalize_protocol_for_folder(row.get("Protocol"))
    side = sanitize(row.get("Side"))
    target = sanitize(row.get("Target"))
    folder = (
        derivatives_root
        / f"sub-{name}"
        / "stimulations"
        / "MNI152NLin2009bAsym"
        / f"stnsnr_target_component_{subject_id}_{phase}_{protocol}_{side}_{target}"
    )
    efield = folder / f"sub-{name}_sim-efield_model-simbio_hemi-{side}.nii"
    return folder, efield


def continuous_condition_efield_paths(derivatives_root: Path, row: dict[str, Any] | pd.Series) -> tuple[Path, Path]:
    """Return expected observed continuous-condition folder and raw sim-efield path."""
    subject_id = sanitize(row.get("ID"))
    name = sanitize(row.get("NameEn"))
    phase = sanitize(row.get("Phase"))
    protocol = normalize_protocol_for_folder(row.get("Protocol"))
    side = sanitize(row.get("Side"))
    folder = (
        derivatives_root
        / f"sub-{name}"
        / "stimulations"
        / "MNI152NLin2009bAsym"
        / f"stnsnr_vta_{subject_id}_{phase}_{protocol}_continuous"
    )
    efield = folder / f"sub-{name}_sim-efield_model-simbio_hemi-{side}.nii"
    return folder, efield


def alternating_component_efield_paths(
    derivatives_root: Path,
    row: dict[str, Any] | pd.Series,
    alternating_row_index: int,
) -> tuple[Path, Path]:
    """Return expected observed alternating subprogram folder and raw sim-efield path."""
    subject_id = sanitize(row.get("ID"))
    name = sanitize(row.get("NameEn"))
    phase = sanitize(row.get("Phase"))
    protocol = normalize_protocol_for_folder(row.get("Protocol"))
    side = sanitize(row.get("Side"))
    target = sanitize(row.get("Target"))
    contact = contact_token(row.get("Contact"))
    folder = (
        derivatives_root
        / f"sub-{name}"
        / "stimulations"
        / "MNI152NLin2009bAsym"
        / f"stnsnr_vta_{subject_id}_{phase}_{protocol}_alt_{side}_{target}_c{contact}_row{int(alternating_row_index)}"
    )
    efield = folder / f"sub-{name}_sim-efield_model-simbio_hemi-{side}.nii"
    return folder, efield


def summarize_component_availability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    path_mode_counts: dict[str, int] = {}
    missing_by_path_mode: dict[str, int] = {}
    for row in rows:
        frequency_key = str(row.get("frequency_class", "UNKNOWN"))
        counts[frequency_key] = counts.get(frequency_key, 0) + 1
        path_key = str(row.get("path_mode", "UNKNOWN"))
        path_mode_counts[path_key] = path_mode_counts.get(path_key, 0) + 1
        if not bool(row.get("efield_exists")):
            missing_by_path_mode[path_key] = missing_by_path_mode.get(path_key, 0) + 1
    return {
        "n_rows": len(rows),
        "n_folders_existing": sum(1 for row in rows if bool(row.get("folder_exists"))),
        "n_efields_existing": sum(1 for row in rows if bool(row.get("efield_exists"))),
        "frequency_class_counts": counts,
        "path_mode_counts": path_mode_counts,
        "missing_by_path_mode": missing_by_path_mode,
    }


def add_check(rows: list[CheckRow], category: str, item: str, status: str, detail: str, path: Path | str = "") -> None:
    rows.append(CheckRow(category, item, status, detail, str(path) if path else ""))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _endpoint_rows(raw_df: pd.DataFrame, endpoint_scale: str) -> pd.DataFrame:
    base_scale, protocol, phase = parse_endpoint_scale(endpoint_scale)
    return raw_df[
        raw_df["Scale"].astype(str).eq(base_scale)
        & raw_df["Protocol"].astype(str).eq(protocol)
        & raw_df["Phase"].astype(str).eq(phase)
    ].copy()


def build_endpoint_reconstruction(raw_df: pd.DataFrame, hf_scale: str, post_scale: str) -> list[dict[str, Any]]:
    hf_rows = _endpoint_rows(raw_df, hf_scale)
    post_rows = _endpoint_rows(raw_df, post_scale)
    merged = hf_rows[["ID", "Value", "Baseline"]].rename(columns={"Value": "Y_HF_ref", "Baseline": "Baseline_HF"}).merge(
        post_rows[["ID", "Value", "Baseline"]].rename(columns={"Value": "Y_post_raw", "Baseline": "Baseline_post"}),
        on="ID",
        how="outer",
        indicator=True,
    )
    out: list[dict[str, Any]] = []
    for _, row in merged.sort_values("ID").iterrows():
        status = "PASS" if row["_merge"] == "both" and pd.notna(row["Y_HF_ref"]) and pd.notna(row["Y_post_raw"]) else "FAIL"
        delta_raw = ""
        if status == "PASS":
            delta_raw = float(row["Y_post_raw"]) - float(row["Y_HF_ref"])
        out.append(
            {
                "subject_id": sanitize(row.get("ID")),
                "hf_scale": hf_scale,
                "post_scale": post_scale,
                "Y_HF_ref": row.get("Y_HF_ref", ""),
                "Y_post_raw": row.get("Y_post_raw", ""),
                "Delta_raw": delta_raw,
                "Baseline_HF": row.get("Baseline_HF", ""),
                "Baseline_post": row.get("Baseline_post", ""),
                "status": status,
                "merge_status": row["_merge"],
            }
        )
    return out


def build_component_availability(
    stim_df: pd.DataFrame,
    derivatives_root: Path,
    *,
    protocols: Iterable[str] = ("STN+SNr",),
    phases: Iterable[str] = ("3m", "immediate"),
) -> list[dict[str, Any]]:
    required_protocols = {str(value) for value in protocols}
    required_phases = {str(value) for value in phases}
    if not required_protocols or not required_phases:
        raise ValueError("component availability requires protocols and phases")
    required = stim_df[
        stim_df["Phase"].astype(str).isin(required_phases)
        & stim_df["Protocol"].astype(str).isin(required_protocols)
    ].copy()
    rows: list[dict[str, Any]] = []
    condition_keys = ["ID", "Phase", "Protocol"]
    for _, condition_rows in required.groupby(condition_keys, sort=False):
        alternating_row_index = 0
        for _, row in condition_rows.iterrows():
            pattern = sanitize(row.get("StimulationPattern")).lower()
            side = sanitize(row.get("Side"))
            path_mode = ""
            if pattern == "alternating":
                alternating_row_index += 1
                path_mode = "observed_alternating_subprogram"
                folder, efield = alternating_component_efield_paths(derivatives_root, row, alternating_row_index)
            elif pattern == "continuous":
                side_rows = condition_rows[condition_rows["Side"].astype(str) == side]
                side_targets = [target for target in side_rows["Target"].astype(str).str.strip().unique().tolist() if target]
                if len(side_targets) == 1:
                    path_mode = "observed_single_target_continuous_condition"
                    folder, efield = continuous_condition_efield_paths(derivatives_root, row)
                else:
                    path_mode = "counterfactual_target_component_continuous_mixed"
                    folder, efield = component_efield_paths(derivatives_root, row)
            else:
                path_mode = "unsupported_stimulation_pattern"
                folder, efield = component_efield_paths(derivatives_root, row)
            frequency_class = classify_frequency_component(row.get("Frequency"))
            rows.append(
                {
                    "subject_id": sanitize(row.get("ID")),
                    "name_en": sanitize(row.get("NameEn")),
                    "phase": sanitize(row.get("Phase")),
                    "protocol": sanitize(row.get("Protocol")),
                    "side": side,
                    "target": sanitize(row.get("Target")),
                    "contact": row.get("Contact", ""),
                    "frequency_hz": row.get("Frequency", ""),
                    "frequency_class": frequency_class,
                    "stimulation_pattern": sanitize(row.get("StimulationPattern")),
                    "path_mode": path_mode,
                    "alternating_row_index": alternating_row_index if pattern == "alternating" else "",
                    "folder_exists": folder.is_dir(),
                    "efield_exists": efield.is_file(),
                    "folder_path": str(folder),
                    "efield_path": str(efield),
                    "status": "PASS" if efield.is_file() and frequency_class in {"HF", "ULF"} else "FAIL",
                }
            )
    return rows


def read_gate_status(gate_status_path: Path) -> dict[str, dict[str, Any]]:
    if not gate_status_path.is_file():
        return {}
    table = pd.read_csv(gate_status_path)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in table.iterrows():
        rows[sanitize(row.get("model_id"))] = {key: row.get(key) for key in table.columns}
    return rows


def dependency_rows(gate_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for model_id, downstream in [("A", "C"), ("B_PPMI", "D")]:
        row = gate_rows.get(model_id, {})
        decision = sanitize(row.get("decision")) if row else "MISSING_GATE_STATUS"
        validity_status = sanitize(row.get("hf_prediction_validity_status")) if row else ""
        if validity_status == "predictive_valid":
            dependency_status = "LOCKED"
        elif validity_status in {"stable_nonpredictive", "failed_unstable"}:
            dependency_status = "EXPLORATORY_UNSTABLE"
        elif decision == "PASS_TO_NEXT_ROUND":
            dependency_status = "LOCKED"
        elif decision == "MISSING_GATE_STATUS":
            dependency_status = "UNKNOWN"
        else:
            dependency_status = "EXPLORATORY_UNSTABLE"
        out.append(
            {
                "hf_model_id": model_id,
                "downstream_model_id": downstream,
                "hf_gate_decision": decision,
                "hf_prediction_validity_status": validity_status,
                "dependency_status": dependency_status,
                "spearman_rho": row.get("spearman_rho", ""),
                "q2": row.get("q2", ""),
            }
        )
    return out


def determine_overall_status(checks: list[CheckRow], dependency: list[dict[str, Any]]) -> str:
    if any(row.status == "FAIL" and row.category in {"clinical", "component_efield", "stimulation"} for row in checks):
        return "NOT_EXECUTABLE_INPUT_FAILURE"
    if any(row.get("dependency_status") != "LOCKED" for row in dependency):
        return "EXPLORATORY_ONLY_UNSTABLE_HF_DEPENDENCY"
    return "PASS_READY_FOR_ULF_PRIMARY"


def run_readiness(args: argparse.Namespace) -> int:
    raw_clinical = Path(args.raw_clinical).expanduser().resolve()
    stim_workbook = Path(args.stim_workbook).expanduser().resolve()
    derivatives_root = Path(args.derivatives_root).expanduser().resolve()
    gate_status_path = Path(args.gate_status).expanduser().resolve()
    output_base = Path(args.output_root).expanduser().resolve()
    output_dir = output_base / timestamp_slug()
    checks: list[CheckRow] = []

    add_check(checks, "input", "raw_clinical_workbook", "PASS" if raw_clinical.is_file() else "FAIL", "raw clinical workbook", raw_clinical)
    add_check(checks, "input", "stimulation_workbook", "PASS" if stim_workbook.is_file() else "FAIL", "stimulation workbook", stim_workbook)
    add_check(checks, "input", "derivatives_root", "PASS" if derivatives_root.is_dir() else "FAIL", "Lead-DBS derivatives root", derivatives_root)
    add_check(checks, "input", "gate_status", "PASS" if gate_status_path.is_file() else "WARN", "A/B gate status table", gate_status_path)

    if any(row.status == "FAIL" for row in checks):
        endpoint_rows: list[dict[str, Any]] = []
        efield_rows: list[dict[str, Any]] = []
        dependencies = dependency_rows(read_gate_status(gate_status_path))
    else:
        raw_df = pd.read_excel(raw_clinical)
        stim_df = pd.read_excel(stim_workbook, sheet_name=DEFAULT_STIM_SHEET)
        endpoint_rows = build_endpoint_reconstruction(raw_df, args.hf_scale, args.post_scale)
        n_endpoint_pass = sum(1 for row in endpoint_rows if row["status"] == "PASS")
        add_check(
            checks,
            "clinical",
            "chronic_endpoint_reconstruction",
            "PASS" if n_endpoint_pass >= int(args.min_subjects) else "FAIL",
            f"{n_endpoint_pass} subjects reconstructible for {args.post_scale}",
            raw_clinical,
        )
        has_immediate = bool((raw_df["Phase"].astype(str).str.lower() == "immediate").any())
        add_check(
            checks,
            "clinical",
            "same_day_immediate_endpoint_rows",
            "PASS" if has_immediate else "WARN",
            "raw clinical table contains immediate rows" if has_immediate else "raw clinical table has no immediate rows",
            raw_clinical,
        )
        efield_rows = build_component_availability(stim_df, derivatives_root)
        summary = summarize_component_availability(efield_rows)
        n_mid_unknown = summary["frequency_class_counts"].get("MID", 0) + summary["frequency_class_counts"].get("UNKNOWN", 0)
        add_check(
            checks,
            "stimulation",
            "frequency_component_classification",
            "PASS" if n_mid_unknown == 0 else "FAIL",
            f"frequency class counts: {summary['frequency_class_counts']}",
            stim_workbook,
        )
        add_check(
            checks,
            "component_efield",
            "component_specific_raw_sim_efield",
            "PASS" if summary["n_efields_existing"] == summary["n_rows"] and summary["n_rows"] > 0 else "FAIL",
            f"{summary['n_efields_existing']}/{summary['n_rows']} component e-fields exist; {summary['n_folders_existing']} folders exist",
            derivatives_root,
        )
        dependencies = dependency_rows(read_gate_status(gate_status_path))
        for dep in dependencies:
            add_check(
                checks,
                "dependency",
                f"{dep['hf_model_id']}_to_{dep['downstream_model_id']}",
                "PASS" if dep["dependency_status"] == "LOCKED" else "WARN",
                f"HF gate decision {dep['hf_gate_decision']} -> {dep['dependency_status']}",
                gate_status_path,
            )

    overall_status = determine_overall_status(checks, dependencies)
    output_dir.mkdir(parents=True, exist_ok=True)
    checks_path = output_dir / "ulf_component_readiness_checks.csv"
    endpoint_path = output_dir / "ulf_component_endpoint_reconstruction.csv"
    efield_path = output_dir / "ulf_component_efield_availability.csv"
    manifest_path = output_dir / "ulf_component_readiness_manifest.json"

    write_csv(checks_path, [asdict(row) for row in checks], ["category", "item", "status", "detail", "path"])
    write_csv(
        endpoint_path,
        endpoint_rows,
        [
            "subject_id",
            "hf_scale",
            "post_scale",
            "Y_HF_ref",
            "Y_post_raw",
            "Delta_raw",
            "Baseline_HF",
            "Baseline_post",
            "status",
            "merge_status",
        ],
    )
    write_csv(
        efield_path,
        efield_rows,
        [
            "subject_id",
            "name_en",
            "phase",
            "protocol",
            "side",
            "target",
            "contact",
            "frequency_hz",
            "frequency_class",
            "stimulation_pattern",
            "path_mode",
            "alternating_row_index",
            "folder_exists",
            "efield_exists",
            "folder_path",
            "efield_path",
            "status",
        ],
    )
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "status": overall_status,
            "raw_clinical": str(raw_clinical),
            "stim_workbook": str(stim_workbook),
            "stim_sheet": DEFAULT_STIM_SHEET,
            "derivatives_root": str(derivatives_root),
            "gate_status_path": str(gate_status_path),
            "hf_scale": args.hf_scale,
            "post_scale": args.post_scale,
            "min_subjects": int(args.min_subjects),
            "endpoint_summary": {
                "n_rows": len(endpoint_rows),
                "n_pass": sum(1 for row in endpoint_rows if row.get("status") == "PASS"),
            },
            "component_efield_summary": summarize_component_availability(efield_rows),
            "dependency_rows": dependencies,
            "outputs": {
                "checks": str(checks_path),
                "endpoint_reconstruction": str(endpoint_path),
                "component_efield_availability": str(efield_path),
                "manifest": str(manifest_path),
            },
            "interpretation": "C/D ULF models must not use mixed STN+SNr e-fields as substitutes for component-specific HF/ULF e-fields.",
        },
    )
    print(f"ULF component readiness output: {output_dir}")
    print(f"Status: {overall_status}")
    if args.strict and overall_status != "PASS_READY_FOR_ULF_PRIMARY":
        return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-clinical", default=str(DEFAULT_RAW_CLINICAL), help="Raw clinical workbook.")
    parser.add_argument("--stim-workbook", default=str(DEFAULT_STIM_WORKBOOK), help="Stimulation workbook.")
    parser.add_argument("--derivatives-root", default=str(DEFAULT_DERIVATIVES_ROOT), help="Lead-DBS derivatives root.")
    parser.add_argument("--gate-status", default=str(DEFAULT_GATE_STATUS), help="A/B gate status CSV.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for timestamped readiness runs.")
    parser.add_argument("--hf-scale", default=DEFAULT_HF_SCALE, help="HF reference scale.")
    parser.add_argument("--post-scale", default=DEFAULT_ULF_POST_SCALE, help="ULF raw post scale.")
    parser.add_argument("--delta-scale", dest="post_scale", help="Deprecated alias for --post-scale.")
    parser.add_argument("--min-subjects", type=int, default=12, help="Minimum reconstructible subjects.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless fully ready for primary ULF execution.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_readiness(args)


if __name__ == "__main__":
    raise SystemExit(main())
