#!/usr/bin/env python3
"""M0 readiness checks for the STN/SNr four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DEFAULT_CANONICAL_ASSET_ROOT = Path("/Users/mojackhu/Github/leaddbs")
DEFAULT_VAL_ROOT = Path("/Volumes/VAL/STNSNr")
DEFAULT_CLINICAL_ROOT = Path("/Users/mojackhu/Research/STNSNr/summary/cohort/subj")
DEFAULT_CONDA = Path("/opt/anaconda3/bin/conda")
DEFAULT_MATLAB = Path("/Applications/MATLAB_R2024b.app/bin/matlab")

RAW_CLINICAL_FILE = "subject_effect_origin.xlsx"
STIM_FILE = "followup_stimulation.xlsx"
STIM_SHEET = "Contact Parameters"

HF_DEFAULT_SCALES = [
    "MDS-UPDRS III score (STN, 3 m)",
    "MDS-UPDRS III axial score (STN, 3 m)",
]

ULF_CHRONIC_DELTA_SCALES = [
    "ΔMDS-UPDRS III score (+SNr, 3 m)",
    "ΔMDS-UPDRS III axial score (+SNr, 3 m)",
]

RAW_REQUIRED_COLUMNS = [
    "ID",
    "Protocol",
    "Phase",
    "Scale",
    "Value",
    "Baseline",
]

STIM_REQUIRED_COLUMNS = [
    "ID",
    "NameEn",
    "Phase",
    "Protocol",
    "Contact",
    "Target",
    "Side",
    "Voltage",
    "PulseWidth",
    "Frequency",
    "StimulationPattern",
]

CONNECTOME_PATHS = {
    "PPMI 85 (Ewert 2017)": Path("connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat"),
    "MGH-USC HCP 32 (Horn 2017)": Path("connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat"),
    "dTOR-985 Full (Elias 2024)": Path("connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat"),
}

ATLAS_DIRS = {
    "STN-connected regions": Path("templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions"),
    "SNr-connected regions": Path("templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions"),
    "STNSNr-connected regions": Path("templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions"),
    "Custom_Ewert_Zhang_Middlebrooks0.05": Path("templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05"),
}


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


def repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[4]


def has_asset_layout(root: Path) -> bool:
    return (
        (root / "helpers/ea_flip_lr_nonlinear.m").exists()
        and (root / CONNECTOME_PATHS["PPMI 85 (Ewert 2017)"]).exists()
        and (root / ATLAS_DIRS["STN-connected regions"]).exists()
    )


def detect_asset_root(repo_root: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit.expanduser().resolve()
    if has_asset_layout(repo_root):
        return repo_root
    if has_asset_layout(DEFAULT_CANONICAL_ASSET_ROOT):
        return DEFAULT_CANONICAL_ASSET_ROOT
    return repo_root


def add_check(rows: list[CheckRow], category: str, item: str, status: str, detail: str, path: Path | str = "") -> None:
    rows.append(CheckRow(category, item, status, detail, str(path) if path else ""))


def file_sha256(path: Path, block_size: int = 1024 * 1024) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def run_command(cmd: list[str], timeout_s: int = 120) -> dict[str, Any]:
    started = iso_now()
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
        return {
            "cmd": cmd,
            "started_at": started,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "started_at": started,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }


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


def sanitize(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_protocol_for_folder(protocol: str) -> str:
    protocol = sanitize(protocol)
    if protocol == "STN+SNr":
        return "STNplusSNr"
    return protocol


def _efield_file_in_folder(folder: Path, subject_name: str, side: str) -> Path:
    return folder / f"sub-{subject_name}_sim-efield_model-simbio_hemi-{side}.nii"


def _contact_token(value: Any) -> str:
    if pd.isna(value):
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return sanitize(value)


def expected_efield_paths(leaddbs_derivatives: Path, row: pd.Series) -> list[Path]:
    name = sanitize(row.get("NameEn"))
    subject_id = sanitize(row.get("ID"))
    phase = sanitize(row.get("Phase"))
    protocol = normalize_protocol_for_folder(row.get("Protocol"))
    pattern = sanitize(row.get("StimulationPattern")) or "continuous"
    side = sanitize(row.get("Side"))
    target = sanitize(row.get("Target"))
    base_dir = leaddbs_derivatives / f"sub-{name}" / "stimulations" / "MNI152NLin2009bAsym"
    if pattern == "alternating":
        contact = _contact_token(row.get("Contact"))
        folder_glob = f"stnsnr_vta_{subject_id}_{phase}_{protocol}_alt_{side}_{target}_c{contact}_row*"
        paths = [_efield_file_in_folder(folder, name, side) for folder in sorted(base_dir.glob(folder_glob))]
        if not paths:
            fallback_glob = f"stnsnr_vta_{subject_id}_{phase}_{protocol}_alt_{side}_{target}_c*_row*"
            paths = [_efield_file_in_folder(folder, name, side) for folder in sorted(base_dir.glob(fallback_glob))]
        return [path for path in paths if path.name.startswith(f"sub-{name}_")]

    folder = base_dir / f"stnsnr_vta_{subject_id}_{phase}_{protocol}_{pattern}"
    return [_efield_file_in_folder(folder, name, side)]


def scale_base_name(scale: str) -> str:
    base = re.sub(r"^Δ", "", scale)
    base = re.sub(r"\s*\((STN|\+SNr),\s*3\s*m\)\s*$", "", base)
    base = base.strip()
    return base


def infer_scale_direction(scale: str) -> tuple[str, str]:
    if "SE-ADL" in scale:
        return "higher", "builtin: SE-ADL higher-is-better"
    known_lower = [
        "UPDRS",
        "MDS-UPDRS",
        "FOGQ",
        "FOG-Q",
        "PDQ",
        "KPPS",
        "MADRS",
        "ADL",
        "BDI",
    ]
    if any(token in scale for token in known_lower):
        return "lower", "builtin: motor/non-motor symptom scales lower-is-better"
    return "unknown", "requires explicit pre-run direction"


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ["pandas", "openpyxl", "numpy", "scipy", "nibabel", "matplotlib"]:
        try:
            module = __import__(name)
            versions[name] = str(getattr(module, "__version__", "installed"))
        except Exception as exc:  # pragma: no cover - readiness should record import failures.
            versions[name] = f"missing: {exc}"
    return versions


def capture_environment_files(output_dir: Path, conda_bin: Path, checks: list[CheckRow]) -> dict[str, str]:
    env_dir = output_dir / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    commands = {
        "conda_leaddbs_explicit": [str(conda_bin), "list", "--explicit", "-n", "leaddbs"],
        "pip_freeze": [sys.executable, "-m", "pip", "freeze"],
    }
    for label, cmd in commands.items():
        result = run_command(cmd, timeout_s=180)
        out_path = env_dir / f"{label}.txt"
        content = result["stdout"] or ""
        if result["stderr"]:
            content += "\n# STDERR\n" + result["stderr"]
        out_path.write_text(content, encoding="utf-8")
        outputs[label] = str(out_path)
        status = "PASS" if result["returncode"] == 0 and not result["timed_out"] else "WARN"
        detail = "captured" if status == "PASS" else f"capture issue returncode={result['returncode']} timed_out={result['timed_out']}"
        add_check(checks, "environment", label, status, detail, out_path)
    return outputs


def check_matlab_flip(repo_root: Path, matlab_bin: Path, run_check: bool) -> dict[str, Any]:
    if not matlab_bin.exists():
        return {"status": "FAIL", "detail": "MATLAB executable missing", "result": None}
    if not run_check:
        return {"status": "WARN", "detail": "MATLAB executable exists; callability check not run", "result": None}
    matlab_cmd = (
        "cd('%s'); addpath(genpath(pwd)); "
        "assert(exist('ea_flip_lr_nonlinear','file')==2); "
        "disp(which('ea_flip_lr_nonlinear'));"
    ) % str(repo_root).replace("'", "''")
    result = run_command([str(matlab_bin), "-batch", matlab_cmd], timeout_s=180)
    if result["returncode"] == 0 and "ea_flip_lr_nonlinear" in result["stdout"]:
        return {"status": "PASS", "detail": "ea_flip_lr_nonlinear callable", "result": result}
    return {"status": "FAIL", "detail": "ea_flip_lr_nonlinear check failed", "result": result}


def build_endpoint_availability(raw_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scale in HF_DEFAULT_SCALES:
        subset = raw_df[raw_df["Scale"].astype(str).eq(scale)]
        rows.append(
            {
                "model": "A/B HF",
                "endpoint": "HF-only 3m",
                "scale": scale,
                "available_subjects": subset["ID"].nunique(),
                "rows": len(subset),
                "status": "PASS" if subset["ID"].nunique() >= 12 else "FAIL",
                "notes": "raw HF endpoint",
            }
        )
    for scale in ULF_CHRONIC_DELTA_SCALES:
        subset = raw_df[raw_df["Scale"].astype(str).eq(scale)]
        rows.append(
            {
                "model": "C/D ULF",
                "endpoint": "chronic 3m delta/reconstructible",
                "scale": scale,
                "available_subjects": subset["ID"].nunique(),
                "rows": len(subset),
                "status": "PASS" if subset["ID"].nunique() >= 12 else "FAIL",
                "notes": "delta rows present; raw post-score reconstruction must be handled by model code",
            }
        )
    immediate_mask = raw_df["Scale"].astype(str).str.contains("immediate", case=False, na=False) | raw_df["Phase"].astype(str).str.contains(
        "immediate", case=False, na=False
    )
    immediate = raw_df[immediate_mask]
    rows.append(
        {
            "model": "C/D ULF",
            "endpoint": "same-day immediate",
            "scale": "any immediate raw scale",
            "available_subjects": immediate["ID"].nunique() if not immediate.empty else 0,
            "rows": len(immediate),
            "status": "WARN" if immediate.empty else "PASS",
            "notes": "key secondary endpoint; current raw clinical table may not contain immediate rows",
        }
    )
    return rows


def build_scale_direction_table(raw_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scale in sorted(raw_df["Scale"].dropna().astype(str).unique()):
        direction, source = infer_scale_direction(scale)
        rows.append(
            {
                "scale": scale,
                "base_scale": scale_base_name(scale),
                "direction": direction,
                "source": source,
            }
        )
    return rows


def build_efield_availability(stim_df: pd.DataFrame, leaddbs_derivatives: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in stim_df.iterrows():
        expected_paths = expected_efield_paths(leaddbs_derivatives, row)
        existing_paths = [path for path in expected_paths if path.is_file()]
        if len(existing_paths) == 1:
            status = "PASS"
        elif len(existing_paths) > 1:
            status = "MULTIPLE"
        else:
            status = "MISSING"
        rows.append(
            {
                "ID": sanitize(row.get("ID")),
                "NameEn": sanitize(row.get("NameEn")),
                "Phase": sanitize(row.get("Phase")),
                "Protocol": sanitize(row.get("Protocol")),
                "Target": sanitize(row.get("Target")),
                "Side": sanitize(row.get("Side")),
                "Frequency": sanitize(row.get("Frequency")),
                "StimulationPattern": sanitize(row.get("StimulationPattern")),
                "expected_path": ";".join(str(path) for path in expected_paths),
                "matched_paths": ";".join(str(path) for path in existing_paths),
                "n_matches": len(existing_paths),
                "exists": len(existing_paths) > 0,
                "status": status,
            }
        )
    return rows


def create_output_roots(val_root: Path) -> list[Path]:
    roots = [
        val_root / "summary/direct_voxel/hf",
        val_root / "summary/direct_voxel/ulf",
        val_root / "summary/normative_connectome_fiber/hf",
        val_root / "summary/normative_connectome_fiber/ulf",
        val_root / "summary/four_model_execution",
    ]
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    return roots


def run_readiness(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else repo_root_from_file()
    asset_root = detect_asset_root(repo_root, Path(args.asset_root) if args.asset_root else None)
    val_root = Path(args.val_root).expanduser().resolve()
    clinical_root = Path(args.clinical_root).expanduser().resolve()
    leaddbs_derivatives = Path(args.leaddbs_derivatives).expanduser().resolve()
    output_parent = Path(args.output_root).expanduser().resolve()
    output_dir = output_parent / timestamp_slug()
    output_dir.mkdir(parents=True, exist_ok=False)

    checks: list[CheckRow] = []
    manifest: dict[str, Any] = {
        "generated_at": iso_now(),
        "plan": "four_model_execution_plan.md",
        "stage": "M0 readiness",
        "random_seed": 42,
        "repo_root": str(repo_root),
        "asset_root": str(asset_root),
        "val_root": str(val_root),
        "clinical_root": str(clinical_root),
        "leaddbs_derivatives": str(leaddbs_derivatives),
        "output_dir": str(output_dir),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
            "package_versions": package_versions(),
        },
    }

    add_check(checks, "paths", "repo_root", "PASS" if repo_root.exists() else "FAIL", "repo root exists" if repo_root.exists() else "missing", repo_root)
    add_check(
        checks,
        "paths",
        "asset_root",
        "PASS" if has_asset_layout(asset_root) else "FAIL",
        "asset layout found" if has_asset_layout(asset_root) else "templates/helpers layout missing",
        asset_root,
    )
    for label, path in [
        ("val_root", val_root),
        ("reference_dir", val_root / "reference"),
        ("summary_dir", val_root / "summary"),
        ("clinical_root", clinical_root),
        ("leaddbs_derivatives", leaddbs_derivatives),
    ]:
        add_check(checks, "paths", label, "PASS" if path.exists() else "FAIL", "exists" if path.exists() else "missing", path)

    if args.create_output_roots:
        roots = create_output_roots(val_root)
        manifest["created_output_roots"] = [str(path) for path in roots]
        for root in roots:
            add_check(checks, "paths", "output_root", "PASS", "created or already existed", root)

    conda_bin = Path(args.conda_bin).expanduser().resolve()
    add_check(checks, "environment", "conda_bin", "PASS" if conda_bin.exists() else "FAIL", "exists" if conda_bin.exists() else "missing", conda_bin)
    env_files = capture_environment_files(output_dir, conda_bin, checks) if conda_bin.exists() else {}
    manifest["environment_files"] = env_files

    matlab_result = check_matlab_flip(repo_root, Path(args.matlab_bin).expanduser().resolve(), args.run_matlab_check)
    add_check(checks, "environment", "matlab_ea_flip_lr_nonlinear", matlab_result["status"], matlab_result["detail"], args.matlab_bin)
    manifest["matlab_check"] = matlab_result

    raw_path = clinical_root / RAW_CLINICAL_FILE
    stim_path = clinical_root / STIM_FILE
    add_check(checks, "clinical", "raw_clinical_file", "PASS" if raw_path.is_file() else "FAIL", "exists" if raw_path.is_file() else "missing", raw_path)
    add_check(checks, "clinical", "stimulation_file", "PASS" if stim_path.is_file() else "FAIL", "exists" if stim_path.is_file() else "missing", stim_path)

    raw_df = pd.DataFrame()
    stim_df = pd.DataFrame()
    if raw_path.is_file():
        raw_df = pd.read_excel(raw_path)
        missing = [col for col in RAW_REQUIRED_COLUMNS if col not in raw_df.columns]
        add_check(checks, "clinical", "raw_required_columns", "PASS" if not missing else "FAIL", "missing: " + ", ".join(missing) if missing else "all present", raw_path)
        add_check(checks, "clinical", "raw_subject_count", "PASS" if raw_df.get("ID", pd.Series(dtype=str)).nunique() >= 12 else "FAIL", f"n={raw_df.get('ID', pd.Series(dtype=str)).nunique()}", raw_path)
        manifest["raw_clinical_sha256"] = file_sha256(raw_path)
    if stim_path.is_file():
        xl = pd.ExcelFile(stim_path)
        add_check(checks, "clinical", "contact_parameters_sheet", "PASS" if STIM_SHEET in xl.sheet_names else "FAIL", f"sheets={xl.sheet_names}", stim_path)
        if STIM_SHEET in xl.sheet_names:
            stim_df = pd.read_excel(stim_path, sheet_name=STIM_SHEET)
            missing = [col for col in STIM_REQUIRED_COLUMNS if col not in stim_df.columns]
            add_check(checks, "clinical", "stimulation_required_columns", "PASS" if not missing else "FAIL", "missing: " + ", ".join(missing) if missing else "all present", stim_path)
            add_check(checks, "clinical", "stimulation_subject_count", "PASS" if stim_df.get("ID", pd.Series(dtype=str)).nunique() >= 12 else "FAIL", f"n={stim_df.get('ID', pd.Series(dtype=str)).nunique()}", stim_path)
            manifest["stimulation_sha256"] = file_sha256(stim_path)

    endpoint_rows = build_endpoint_availability(raw_df) if not raw_df.empty else []
    write_csv(
        output_dir / "four_model_m0_endpoint_availability.csv",
        endpoint_rows,
        ["model", "endpoint", "scale", "available_subjects", "rows", "status", "notes"],
    )
    for row in endpoint_rows:
        add_check(checks, "clinical", f"endpoint:{row['model']}:{row['endpoint']}:{row['scale']}", row["status"], f"subjects={row['available_subjects']} rows={row['rows']}")

    scale_rows = build_scale_direction_table(raw_df) if not raw_df.empty else []
    write_csv(output_dir / "scale_direction_table.csv", scale_rows, ["scale", "base_scale", "direction", "source"])
    unknown_scales = [row["scale"] for row in scale_rows if row["direction"] == "unknown"]
    add_check(
        checks,
        "clinical",
        "scale_direction_table",
        "PASS" if not unknown_scales else "FAIL",
        "all directions inferred" if not unknown_scales else "unknown: " + "; ".join(unknown_scales),
        output_dir / "scale_direction_table.csv",
    )

    efield_rows = build_efield_availability(stim_df, leaddbs_derivatives) if not stim_df.empty else []
    write_csv(
        output_dir / "four_model_m0_efield_availability.csv",
        efield_rows,
        [
            "ID",
            "NameEn",
            "Phase",
            "Protocol",
            "Target",
            "Side",
            "Frequency",
            "StimulationPattern",
            "expected_path",
            "matched_paths",
            "n_matches",
            "exists",
            "status",
        ],
    )
    if efield_rows:
        found = sum(1 for row in efield_rows if row["exists"])
        missing = sum(1 for row in efield_rows if row["status"] == "MISSING")
        multiple = sum(1 for row in efield_rows if row["status"] == "MULTIPLE")
        status = "PASS" if missing == 0 and multiple == 0 else ("WARN" if found > 0 else "FAIL")
        add_check(
            checks,
            "efield",
            "raw_mni_sim_efield_availability",
            status,
            f"found={found} missing={missing} multiple={multiple} total={len(efield_rows)}",
            output_dir / "four_model_m0_efield_availability.csv",
        )

    for name, rel in CONNECTOME_PATHS.items():
        path = asset_root / rel
        add_check(checks, "connectomes", name, "PASS" if path.is_file() else "FAIL", "data.mat exists" if path.is_file() else "missing data.mat", path)
    for name, rel in ATLAS_DIRS.items():
        path = asset_root / rel
        add_check(checks, "atlases", name, "PASS" if path.is_dir() else "FAIL", "atlas directory exists" if path.is_dir() else "missing atlas directory", path)

    check_dicts = [asdict(row) for row in checks]
    status_order = {"FAIL": 2, "WARN": 1, "PASS": 0}
    worst = max(checks, key=lambda row: status_order.get(row.status, 2)).status if checks else "FAIL"
    fail_count = sum(1 for row in checks if row.status == "FAIL")
    warn_count = sum(1 for row in checks if row.status == "WARN")
    pass_count = sum(1 for row in checks if row.status == "PASS")
    manifest["overall_status"] = worst
    manifest["check_counts"] = {"PASS": pass_count, "WARN": warn_count, "FAIL": fail_count}
    manifest["outputs"] = {
        "checks_csv": str(output_dir / "four_model_m0_readiness_checks.csv"),
        "endpoint_availability_csv": str(output_dir / "four_model_m0_endpoint_availability.csv"),
        "efield_availability_csv": str(output_dir / "four_model_m0_efield_availability.csv"),
        "scale_direction_table_csv": str(output_dir / "scale_direction_table.csv"),
        "manifest_json": str(output_dir / "four_model_m0_readiness_manifest.json"),
    }

    write_csv(output_dir / "four_model_m0_readiness_checks.csv", check_dicts, ["category", "item", "status", "detail", "path"])
    write_json(output_dir / "four_model_m0_readiness_manifest.json", manifest)

    print(f"M0 readiness output: {output_dir}")
    print(f"Overall status: {worst} (PASS={pass_count}, WARN={warn_count}, FAIL={fail_count})")
    if args.strict and fail_count:
        return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Code repo root. Defaults to the current file's repository.")
    parser.add_argument("--asset-root", default="", help="Lead-DBS asset root with templates/connectomes. Defaults to auto-detect.")
    parser.add_argument("--val-root", default=str(DEFAULT_VAL_ROOT), help="STNSNr VAL root.")
    parser.add_argument("--clinical-root", default=str(DEFAULT_CLINICAL_ROOT), help="Clinical workbook directory.")
    parser.add_argument("--leaddbs-derivatives", default=str(DEFAULT_VAL_ROOT / "derivatives/leaddbs"), help="Lead-DBS derivatives directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/m0_readiness"), help="M0 output parent directory.")
    parser.add_argument("--conda-bin", default=str(DEFAULT_CONDA), help="Conda executable.")
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--run-matlab-check", action="store_true", help="Run MATLAB batch to verify ea_flip_lr_nonlinear callability.")
    parser.add_argument("--no-create-output-roots", dest="create_output_roots", action="store_false", help="Do not create model output roots.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any FAIL check is present.")
    parser.set_defaults(create_output_roots=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_readiness(args)


if __name__ == "__main__":
    raise SystemExit(main())
