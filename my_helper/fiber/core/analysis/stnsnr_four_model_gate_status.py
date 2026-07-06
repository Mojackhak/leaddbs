#!/usr/bin/env python3
"""Summarize gate status for the STN/SNr four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def classify_gate(metrics: dict[str, Any], *, predictions_finite: bool, output_exists: bool) -> str:
    """Classify whether a branch can enter the next expensive round."""
    if not output_exists:
        return "MISSING_OUTPUT"
    if not predictions_finite:
        return "ERROR"
    try:
        rho = float(metrics.get("spearman_rho", np.nan))
        q2 = float(metrics.get("q2", np.nan))
    except (TypeError, ValueError):
        return "ERROR"
    if not np.isfinite(rho) or not np.isfinite(q2):
        return "ERROR"
    if rho > 0 and q2 >= 0:
        return "PASS_TO_NEXT_ROUND"
    return "STOP_FORMAL_REMAIN_EXPLORATORY"


def finite_float(value: Any) -> float:
    """Convert a value to float, returning NaN on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def prediction_diagnostics(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Compute prediction diagnostics needed by the stricter HF validity state."""
    empty = {
        "mae_model": np.nan,
        "mae_baseline": np.nan,
        "rmse_model": np.nan,
        "rmse_baseline": np.nan,
        "score_std": np.nan,
        "score_nonconstant": False,
        "residual_dominance_fraction": np.nan,
        "residual_dominance_proxy_pass": False,
    }
    if not path.is_file():
        return empty
    table = pd.read_csv(path)
    if table.empty:
        return empty

    model_col, baseline_col = spec["prediction_columns"]
    required = ["Y_post", model_col, baseline_col]
    if any(column not in table.columns for column in required):
        return empty

    y = pd.to_numeric(table["Y_post"], errors="coerce").to_numpy(dtype=float)
    pred_model = pd.to_numeric(table[model_col], errors="coerce").to_numpy(dtype=float)
    pred_baseline = pd.to_numeric(table[baseline_col], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(y) & np.isfinite(pred_model) & np.isfinite(pred_baseline)
    if not np.any(finite):
        return empty

    resid_model = y[finite] - pred_model[finite]
    resid_baseline = y[finite] - pred_baseline[finite]
    abs_resid = np.abs(resid_model)
    abs_sum = float(np.sum(abs_resid))
    residual_dominance_fraction = float(np.max(abs_resid) / abs_sum) if abs_sum > 0 else 0.0

    score_col = spec.get("score_column", "")
    score_std = np.nan
    score_nonconstant = False
    if score_col and score_col in table.columns:
        scores = pd.to_numeric(table[score_col], errors="coerce").to_numpy(dtype=float)
        finite_scores = scores[np.isfinite(scores)]
        if finite_scores.size >= 2:
            score_std = float(np.std(finite_scores))
            score_nonconstant = bool(score_std > 1e-12)

    return {
        "mae_model": float(np.mean(np.abs(resid_model))),
        "mae_baseline": float(np.mean(np.abs(resid_baseline))),
        "rmse_model": float(np.sqrt(np.mean(resid_model * resid_model))),
        "rmse_baseline": float(np.sqrt(np.mean(resid_baseline * resid_baseline))),
        "score_std": score_std,
        "score_nonconstant": score_nonconstant,
        "residual_dominance_fraction": residual_dominance_fraction,
        "residual_dominance_proxy_pass": bool(residual_dominance_fraction < 0.5),
    }


def classify_hf_prediction_validity(
    metrics: dict[str, Any],
    diagnostics: dict[str, Any],
    *,
    predictions_finite: bool,
    output_exists: bool,
) -> tuple[str, str]:
    """Classify a foundational HF branch using the documented strict state labels."""
    reasons: list[str] = []
    if not output_exists:
        return "failed_unstable", "missing_output"
    if not predictions_finite:
        return "failed_unstable", "nonfinite_predictions"

    rho = finite_float(metrics.get("spearman_rho", np.nan))
    q2 = finite_float(metrics.get("q2", np.nan))
    if not np.isfinite(rho):
        reasons.append("nonfinite_spearman_rho")
    elif rho <= 0:
        reasons.append("rho_le_0")
    if not np.isfinite(q2):
        reasons.append("nonfinite_q2")
    elif q2 <= 0:
        reasons.append("q2_le_0")
    if reasons:
        return "failed_unstable", ";".join(reasons)

    if not bool(diagnostics.get("score_nonconstant", False)):
        return "failed_unstable", "score_constant_or_unavailable"

    mae_model = finite_float(diagnostics.get("mae_model", np.nan))
    mae_baseline = finite_float(diagnostics.get("mae_baseline", np.nan))
    rmse_model = finite_float(diagnostics.get("rmse_model", np.nan))
    rmse_baseline = finite_float(diagnostics.get("rmse_baseline", np.nan))
    residual_proxy_pass = bool(diagnostics.get("residual_dominance_proxy_pass", False))
    if (
        np.isfinite(mae_model)
        and np.isfinite(mae_baseline)
        and np.isfinite(rmse_model)
        and np.isfinite(rmse_baseline)
        and mae_model < mae_baseline
        and rmse_model < rmse_baseline
        and residual_proxy_pass
    ):
        return "predictive_valid", "all_available_predictive_checks_pass"

    if not np.isfinite(mae_model) or not np.isfinite(mae_baseline):
        reasons.append("mae_unavailable")
    elif mae_model >= mae_baseline:
        reasons.append("mae_not_better_than_baseline")
    if not np.isfinite(rmse_model) or not np.isfinite(rmse_baseline):
        reasons.append("rmse_unavailable")
    elif rmse_model >= rmse_baseline:
        reasons.append("rmse_not_better_than_baseline")
    if not residual_proxy_pass:
        reasons.append("residual_dominance_proxy_failed")
    return "stable_nonpredictive", ";".join(reasons) if reasons else "predictive_checks_incomplete"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def predictions_are_finite(path: Path, prediction_columns: list[str]) -> bool:
    if not path.is_file():
        return False
    table = pd.read_csv(path)
    if table.empty:
        return False
    for column in prediction_columns:
        if column not in table.columns:
            return False
        values = pd.to_numeric(table[column], errors="coerce").to_numpy(dtype=float)
        if not np.all(np.isfinite(values)):
            return False
    return True


def branch_specs(val_root: Path) -> list[dict[str, Any]]:
    hf_direct_root = val_root / "summary/direct_voxel/hf/mds_updrs_iii_score_stn_3_m/tau200/partial_spearman"
    specs = [
        {
            "model_id": "A",
            "model": "HF direct voxel",
            "branch": "tau200/partial_spearman",
            "root": hf_direct_root,
            "qc": hf_direct_root / "direct_voxel_HF_mapping_qc.json",
            "manifest": hf_direct_root / "direct_voxel_HF_generation_manifest.json",
            "predictions": hf_direct_root / "direct_voxel_HF_loocv_predictions.csv",
            "prediction_columns": ["prediction_HFScore_model", "prediction_baseline_only"],
            "score_column": "HFScore_LOOCV",
            "dependency": "none",
        },
    ]
    for connectome_id, connectome_label, connectome_slug in [
        ("B_PPMI", "HF normative fiber PPMI", "ppmi_85_ewert_2017"),
        ("B_MGH", "HF normative fiber MGH", "mgh_usc_hcp_32_horn_2017"),
        ("B_DTOR", "HF normative fiber dTOR", "dtor_985_full_elias_2024"),
    ]:
        hf_fiber_root = (
            val_root
            / "summary/normative_connectome_fiber/hf"
            / connectome_slug
            / "mds_updrs_iii_score_stn_3_m/peak_efield_tau800_primary"
        )
        specs.append(
            {
                "model_id": connectome_id,
                "model": connectome_label,
                "branch": "peak_efield_tau800_primary",
                "root": hf_fiber_root,
                "qc": hf_fiber_root / "normative_HF_fiber_mapping_qc.json",
                "manifest": hf_fiber_root / "normative_HF_fiber_generation_manifest.json",
                "predictions": hf_fiber_root / "normative_HF_fiber_loocv_predictions.csv",
                "prediction_columns": ["prediction_NetFiberScore_model", "prediction_baseline_only"],
                "score_column": "NetFiberScore_LOOCV",
                "dependency": "none",
            }
        )
    return specs


def summarize_branch(spec: dict[str, Any]) -> dict[str, Any]:
    qc = read_json(spec["qc"])
    manifest = read_json(spec["manifest"])
    output_exists = spec["qc"].is_file() and spec["manifest"].is_file() and spec["predictions"].is_file()
    finite_predictions = predictions_are_finite(spec["predictions"], spec["prediction_columns"])
    metrics = qc.get("loocv_metrics", {}) if qc else {}
    decision = classify_gate(metrics, predictions_finite=finite_predictions, output_exists=output_exists)
    diagnostics = prediction_diagnostics(spec["predictions"], spec)
    validity_status, validity_reason = classify_hf_prediction_validity(
        metrics,
        diagnostics,
        predictions_finite=finite_predictions,
        output_exists=output_exists,
    )
    return {
        "model_id": spec["model_id"],
        "model": spec["model"],
        "branch": spec["branch"],
        "decision": decision,
        "hf_prediction_validity_status": validity_status,
        "hf_prediction_validity_reason": validity_reason,
        "dependency": spec["dependency"],
        "spearman_rho": metrics.get("spearman_rho", ""),
        "q2": metrics.get("q2", ""),
        "pearson_r": metrics.get("pearson_r", ""),
        "mae": metrics.get("mae", ""),
        "rmse": metrics.get("rmse", ""),
        "mae_baseline": diagnostics.get("mae_baseline", ""),
        "rmse_baseline": diagnostics.get("rmse_baseline", ""),
        "score_std": diagnostics.get("score_std", ""),
        "score_nonconstant": diagnostics.get("score_nonconstant", ""),
        "residual_dominance_fraction": diagnostics.get("residual_dominance_fraction", ""),
        "residual_dominance_proxy_pass": diagnostics.get("residual_dominance_proxy_pass", ""),
        "predictions_finite": finite_predictions,
        "output_exists": output_exists,
        "qc_path": str(spec["qc"]),
        "manifest_path": str(spec["manifest"]),
        "predictions_path": str(spec["predictions"]),
        "manifest_status": manifest.get("status", "") if manifest else "",
        "next_action": next_action(decision, spec["model_id"]),
    }


def next_action(decision: str, model_id: str) -> str:
    if decision == "PASS_TO_NEXT_ROUND":
        return "eligible_for_smoke_resampling_or_next_gate"
    if decision == "STOP_FORMAL_REMAIN_EXPLORATORY":
        if model_id == "A" or model_id.startswith("B_"):
            return "do_not_start_formal_resampling; downstream ULF dependency remains exploratory"
        return "do_not_start_formal_resampling"
    if decision == "MISSING_OUTPUT":
        return "run_primary_observed_smoke_first"
    return "inspect_qc_and_predictions"


def run_gate_status(args: argparse.Namespace) -> int:
    val_root = Path(args.val_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [summarize_branch(spec) for spec in branch_specs(val_root)]
    fieldnames = [
        "model_id",
        "model",
        "branch",
        "decision",
        "hf_prediction_validity_status",
        "hf_prediction_validity_reason",
        "dependency",
        "spearman_rho",
        "q2",
        "pearson_r",
        "mae",
        "rmse",
        "mae_baseline",
        "rmse_baseline",
        "score_std",
        "score_nonconstant",
        "residual_dominance_fraction",
        "residual_dominance_proxy_pass",
        "predictions_finite",
        "output_exists",
        "manifest_status",
        "next_action",
        "qc_path",
        "manifest_path",
        "predictions_path",
    ]
    csv_path = output_dir / "four_model_gate_status.csv"
    manifest_path = output_dir / "four_model_gate_status_manifest.json"
    write_csv(csv_path, rows, fieldnames)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "val_root": str(val_root),
            "gate_rule": "PASS only if output exists, predictions finite, LOOCV Spearman rho > 0, and Q2 >= 0",
            "hf_prediction_validity_rule": (
                "predictive_valid requires rho > 0, Q2 > 0, model MAE/RMSE better than baseline, "
                "nonconstant score, and residual-dominance proxy pass; failed_unstable is assigned for "
                "missing/nonfinite outputs, rho <= 0, Q2 <= 0, or degenerate scores"
            ),
            "rows": rows,
            "outputs": {"csv": str(csv_path), "manifest": str(manifest_path)},
        },
    )
    print(f"Gate status output: {csv_path}")
    for row in rows:
        print(
            f"{row['model_id']} {row['model']}: {row['decision']} "
            f"validity={row['hf_prediction_validity_status']} rho={row['spearman_rho']} q2={row['q2']}"
        )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val-root", default=str(DEFAULT_VAL_ROOT), help="STNSNr VAL root.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/gate_status"),
        help="Gate status output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_gate_status(args)


if __name__ == "__main__":
    raise SystemExit(main())
