#!/usr/bin/env python3
"""Build a consolidated status report for the STN/SNr four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT

HF_SOURCE_ACCEPTED = {"pre_specified_accepted", "scan_fallback_accepted"}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hf_source_status_from_row(row: dict[str, Any]) -> str:
    """Return the direct-voxel or normative-fiber HF source status from a status row."""
    for key in ("hf_voxel_source_status", "hf_norm_fiber_source_status", "source_status"):
        value = str(row.get(key, "") or "")
        if value:
            return value
    return ""


def hf_prediction_status_from_row(row: dict[str, Any]) -> str:
    """Return the direct-voxel or normative-fiber HF prediction status from a status row."""
    for key in (
        "hf_voxel_prediction_status",
        "hf_norm_fiber_prediction_status",
        "prediction_status",
        "hf_prediction_validity_status",
    ):
        value = str(row.get(key, "") or "")
        if value:
            return value
    return ""


def classify_hf_model_state(gate_row: dict[str, Any]) -> dict[str, str]:
    """Classify a foundational HF model from source and prediction status fields."""
    source_status = hf_source_status_from_row(gate_row)
    prediction_status = hf_prediction_status_from_row(gate_row)
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_predictive":
        return {
            "execution_status": "READY_FOR_NEXT_ROUND",
            "dependency_status": "NONE",
            "formal_resampling_status": "ELIGIBLE_AFTER_SOURCE_RESOLUTION",
            "hf_prediction_validity_status": prediction_status,
        }
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_nonpredictive":
        return {
            "execution_status": "SOURCE_ACCEPTED_ERROR_NONPREDICTIVE",
            "dependency_status": "NONE",
            "formal_resampling_status": "NOT_SELECTED_FOR_PREDICTIVE_FORMAL",
            "hf_prediction_validity_status": prediction_status,
        }
    if source_status == "absent_no_stable_grid":
        return {
            "execution_status": "ABSENT_NO_STABLE_GRID",
            "dependency_status": "NONE",
            "formal_resampling_status": "NOT_APPLICABLE_NO_STABLE_SOURCE",
            "hf_prediction_validity_status": prediction_status or "not_applicable",
        }

    # Legacy/current status rows without intended source fields must be refreshed
    # before they can drive downstream branch-role decisions.
    decision = str(gate_row.get("decision", "MISSING_OUTPUT"))
    output_exists = as_bool(gate_row.get("output_exists"))
    predictions_finite = as_bool(gate_row.get("predictions_finite"))
    if decision == "MISSING_OUTPUT" or not output_exists:
        execution_status = "MISSING_PRIMARY_OBSERVED_OUTPUT"
        formal_status = "NOT_APPLICABLE_MISSING_OUTPUT"
    elif output_exists and predictions_finite:
        execution_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
    else:
        execution_status = "ERROR_OR_INCOMPLETE"
        formal_status = "NOT_APPLICABLE_ERROR"
    return {
        "execution_status": execution_status,
        "dependency_status": "NONE",
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": prediction_status or "not_evaluable",
    }


def classify_ulf_model_state(
    *,
    hf_dependency_source_status: str = "",
    hf_dependency_prediction_status: str = "",
    hf_dependency_decision: str = "",
    readiness_status: str,
    efield_summary: dict[str, Any],
) -> dict[str, str]:
    """Classify a downstream ULF model from its HF dependency and component-readiness status."""
    dependency_status = classify_dependency(
        source_status=hf_dependency_source_status,
        prediction_status=hf_dependency_prediction_status,
        decision=hf_dependency_decision,
    )
    missing_inputs = int(efield_summary.get("n_rows", 0)) - int(efield_summary.get("n_efields_existing", 0))
    if readiness_status == "NOT_EXECUTABLE_INPUT_FAILURE" or missing_inputs > 0:
        execution_status = "NOT_EXECUTABLE_INPUT_FAILURE"
        formal_status = "NOT_APPLICABLE_INPUT_FAILURE"
    elif dependency_status in {"SOURCE_EXISTS_ERROR_PREDICTIVE", "SOURCE_EXISTS_ERROR_NONPREDICTIVE", "SOURCE_ABSENT"}:
        execution_status = "READY_FOR_PRIMARY_OBSERVED"
        formal_status = "NOT_STARTED_PRIMARY_OBSERVED_FIRST"
    elif readiness_status == "PASS_READY_FOR_ULF_PRIMARY":
        execution_status = "READY_FOR_PRIMARY_OBSERVED"
        formal_status = "NOT_STARTED_PRIMARY_OBSERVED_FIRST"
    elif dependency_status in {"MISSING", "UNKNOWN"}:
        execution_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
    else:
        execution_status = "UNKNOWN_READINESS_STATE"
        formal_status = "NOT_APPLICABLE_UNKNOWN"
    return {
        "execution_status": execution_status,
        "dependency_status": dependency_status,
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
    }


def classify_c_observed_state(
    *,
    hf_dependency_source_status: str = "",
    hf_dependency_prediction_status: str = "",
    hf_dependency_decision: str = "",
    readiness_status: str,
    efield_summary: dict[str, Any],
    c_outputs: dict[str, Any],
) -> dict[str, str]:
    """Classify C after its observed-only direct voxel branches exist."""
    if not c_outputs.get("both_branches_exist"):
        return classify_ulf_model_state(
            hf_dependency_source_status=hf_dependency_source_status,
            hf_dependency_prediction_status=hf_dependency_prediction_status,
            hf_dependency_decision=hf_dependency_decision,
            readiness_status=readiness_status,
            efield_summary=efield_summary,
        )
    dependency_status = classify_dependency(
        source_status=hf_dependency_source_status,
        prediction_status=hf_dependency_prediction_status,
        decision=hf_dependency_decision,
    )
    formal_status = "NOT_STARTED_FORMAL_RESAMPLING"
    if dependency_status == "SOURCE_ABSENT":
        next_status = "OBSERVED_COMPLETE_NO_DELTA_PRIMARY"
    elif dependency_status in {"SOURCE_EXISTS_ERROR_PREDICTIVE", "SOURCE_EXISTS_ERROR_NONPREDICTIVE"}:
        next_status = "OBSERVED_COMPLETE_READY_FOR_ENDPOINT_RESOLVER"
    else:
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
        next_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
    return {
        "execution_status": next_status,
        "dependency_status": dependency_status,
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
    }


def classify_d_observed_state(
    *,
    hf_dependency_source_status: str = "",
    hf_dependency_prediction_status: str = "",
    hf_dependency_decision: str = "",
    readiness_status: str,
    efield_summary: dict[str, Any],
    d_outputs: dict[str, Any],
) -> dict[str, str]:
    """Classify D after its observed-only normative fiber branches exist."""
    if not d_outputs.get("both_branches_exist"):
        return classify_ulf_model_state(
            hf_dependency_source_status=hf_dependency_source_status,
            hf_dependency_prediction_status=hf_dependency_prediction_status,
            hf_dependency_decision=hf_dependency_decision,
            readiness_status=readiness_status,
            efield_summary=efield_summary,
        )
    dependency_status = classify_dependency(
        source_status=hf_dependency_source_status,
        prediction_status=hf_dependency_prediction_status,
        decision=hf_dependency_decision,
    )
    formal_status = "NOT_STARTED_FORMAL_RESAMPLING"
    if dependency_status == "SOURCE_ABSENT":
        next_status = "OBSERVED_COMPLETE_NO_DELTA_PRIMARY"
    elif dependency_status in {"SOURCE_EXISTS_ERROR_PREDICTIVE", "SOURCE_EXISTS_ERROR_NONPREDICTIVE"}:
        next_status = "OBSERVED_COMPLETE_READY_FOR_ENDPOINT_RESOLVER"
    else:
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
        next_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
    return {
        "execution_status": next_status,
        "dependency_status": dependency_status,
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
    }


def classify_dependency(*, source_status: str = "", prediction_status: str = "", decision: str = "") -> str:
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_predictive":
        return "SOURCE_EXISTS_ERROR_PREDICTIVE"
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_nonpredictive":
        return "SOURCE_EXISTS_ERROR_NONPREDICTIVE"
    if source_status == "absent_no_stable_grid":
        return "SOURCE_ABSENT"
    if prediction_status == "predictive_valid":
        return "SOURCE_EXISTS_ERROR_PREDICTIVE"
    if prediction_status in {"stable_nonpredictive", "failed_unstable"}:
        return "UNKNOWN"
    if decision == "PASS_TO_NEXT_ROUND":
        return "SOURCE_EXISTS_ERROR_PREDICTIVE"
    if decision == "STOP_FORMAL_REMAIN_EXPLORATORY":
        return "UNKNOWN"
    if decision in {"MISSING_OUTPUT", ""}:
        return "MISSING"
    return "UNKNOWN"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def default_c_output_root(val_root: Path) -> Path:
    return val_root / "summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200"


def default_d_output_root(val_root: Path) -> Path:
    return (
        val_root
        / "summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/"
        "mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed"
    )


def read_c_observed_outputs(val_root: Path) -> dict[str, Any]:
    root = default_c_output_root(val_root)
    branches = {
        "no_delta_hf": root / "partial_spearman_no_delta_hf",
        "delta_hf_adjusted": root / "partial_spearman_delta_hf_adjusted",
    }
    out: dict[str, Any] = {"root": str(root), "branches": {}, "both_branches_exist": False}
    for key, branch_dir in branches.items():
        manifest = branch_dir / "direct_voxel_ULF_only_generation_manifest.json"
        qc = branch_dir / "direct_voxel_ULF_only_mapping_qc.json"
        scores = branch_dir / "direct_voxel_ULF_only_scores.csv"
        predictions = branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv"
        manifest_data = read_json(manifest)
        qc_data = read_json(qc)
        out["branches"][key] = {
            "branch_dir": str(branch_dir),
            "manifest_path": str(manifest),
            "qc_path": str(qc),
            "manifest_exists": manifest.is_file(),
            "qc_exists": qc.is_file(),
            "scores_exists": scores.is_file(),
            "predictions_exists": predictions.is_file(),
            "metrics": qc_data.get("loocv_metrics", {}),
            "ulf_primary_branch": manifest_data.get("ulf_primary_branch", ""),
            "delta_hfscore_role": manifest_data.get("delta_hfscore_role", ""),
            "hf_prediction_validity_status": manifest_data.get("hf_prediction_validity_status", ""),
        }
    out["both_branches_exist"] = all(
        row["manifest_exists"] and row["qc_exists"] and row["scores_exists"] and row["predictions_exists"]
        for row in out["branches"].values()
    )
    return out


def read_d_observed_outputs(val_root: Path) -> dict[str, Any]:
    root = default_d_output_root(val_root)
    branches = {
        "no_delta_hf": root / "ulf_peak_efield_tau800_no_delta_hf",
        "delta_hf_adjusted": root / "ulf_peak_efield_tau800_delta_hf_adjusted",
    }
    out: dict[str, Any] = {"root": str(root), "connectome": "PPMI 85", "branches": {}, "both_branches_exist": False}
    for key, branch_dir in branches.items():
        manifest = branch_dir / "normative_ULF_fiber_generation_manifest.json"
        qc = branch_dir / "normative_ULF_fiber_mapping_qc.json"
        scores = branch_dir / "normative_ULF_fiber_scores.csv"
        predictions = branch_dir / "normative_ULF_fiber_loocv_predictions.csv"
        manifest_data = read_json(manifest)
        qc_data = read_json(qc)
        out["branches"][key] = {
            "branch_dir": str(branch_dir),
            "manifest_path": str(manifest),
            "qc_path": str(qc),
            "manifest_exists": manifest.is_file(),
            "qc_exists": qc.is_file(),
            "scores_exists": scores.is_file(),
            "predictions_exists": predictions.is_file(),
            "metrics": qc_data.get("loocv_metrics", {}),
            "ulf_primary_branch": manifest_data.get("ulf_primary_branch", ""),
            "delta_hfscore_role": manifest_data.get("delta_hfscore_role", ""),
            "hf_prediction_validity_status": manifest_data.get("hf_prediction_validity_status", ""),
        }
    out["both_branches_exist"] = all(
        row["manifest_exists"] and row["qc_exists"] and row["scores_exists"] and row["predictions_exists"]
        for row in out["branches"].values()
    )
    return out


def latest_run_dir(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir() and path.name.startswith("run-")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.name)[-1]


def read_gate_rows(gate_csv: Path) -> dict[str, dict[str, Any]]:
    if not gate_csv.is_file():
        return {}
    table = pd.read_csv(gate_csv)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in table.iterrows():
        rows[str(row.get("model_id", ""))] = {column: row.get(column) for column in table.columns}
    return rows


def read_a_hf_voxel_resolver_row(val_root: Path) -> dict[str, Any]:
    """Read the current A direct-voxel resolver row for the chronic total endpoint if available."""
    summary_path = (
        val_root
        / "summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/"
        "all_scales_posthoc_threshold_scan_summary.csv"
    )
    if not summary_path.is_file():
        return {}
    table = pd.read_csv(summary_path)
    if table.empty:
        return {}
    if "scale_slug" in table.columns:
        matched = table[table["scale_slug"].astype(str).eq("mds_updrs_iii_score_stn_3_m")]
        if not matched.empty:
            return {column: matched.iloc[0].get(column) for column in table.columns}
    return {column: table.iloc[0].get(column) for column in table.columns}


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


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Four-Model Execution Status",
        "",
        "Current cohort size is `n=16`. These outputs remain hypothesis-generating unless a branch passes the declared gate and the corresponding formal validation is run.",
        "",
        "| Model | Status | Dependency | HF source | HF prediction | Formal resampling | Next action |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {execution_status} | {dependency_status} | "
            "{hf_source_status} | "
            "{hf_prediction_validity_status} | "
            "{formal_resampling_status} | {next_action} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_status_rows(val_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gate_csv = val_root / "summary/four_model_execution/gate_status/four_model_gate_status.csv"
    gate_rows = read_gate_rows(gate_csv)
    a_resolver_row = read_a_hf_voxel_resolver_row(val_root)
    ulf_root = val_root / "summary/four_model_execution/ulf_component_readiness"
    ulf_run = latest_run_dir(ulf_root)
    ulf_manifest_path = ulf_run / "ulf_component_readiness_manifest.json" if ulf_run else Path("")
    ulf_manifest = read_json(ulf_manifest_path)
    ulf_readiness_status = str(ulf_manifest.get("status", "MISSING_ULF_READINESS"))
    efield_summary = ulf_manifest.get("component_efield_summary", {})
    c_outputs = read_c_observed_outputs(val_root)
    d_outputs = read_d_observed_outputs(val_root)

    rows: list[dict[str, Any]] = []
    hf_dependency_rows: dict[str, dict[str, Any]] = {}
    for model_id, model_name in [
        ("A", "HF direct voxel"),
        ("B_PPMI", "HF normative fiber PPMI"),
        ("B_MGH", "HF normative fiber MGH"),
        ("B_DTOR", "HF normative fiber dTOR"),
    ]:
        gate_row = gate_rows.get(model_id, {"model_id": model_id, "model": model_name, "decision": "MISSING_OUTPUT"})
        resolver_row = dict(gate_row)
        if model_id == "A" and a_resolver_row:
            resolver_row.update(a_resolver_row)
        state = classify_hf_model_state(resolver_row)
        hf_dependency_rows[model_id] = resolver_row
        rows.append(
            {
                "model_id": model_id,
                "model": str(gate_row.get("model", model_name)),
                "branch": str(gate_row.get("branch", "")),
                "dependency_model": "none",
                "gate_decision": str(gate_row.get("decision", "MISSING_OUTPUT")),
                "hf_source_status": hf_source_status_from_row(resolver_row),
                "spearman_rho": gate_row.get("spearman_rho", ""),
                "q2": gate_row.get("q2", ""),
                "readiness_status": "",
                "input_summary": "",
                "latest_manifest": str(gate_row.get("manifest_path", "")),
                "next_action": next_action_for_state(state),
                **state,
            }
        )

    for model_id, model_name, dependency_id, branch in [
        ("C", "ULF add-on direct voxel", "A", "chronic/tau200/partial_spearman_no_delta_hf+delta_hf_adjusted"),
        ("D", "ULF add-on normative fiber PPMI", "B_PPMI", "chronic/ppmi/peak_efield_tau800_no_delta_hf+delta_hf_adjusted"),
    ]:
        dependency_row = hf_dependency_rows.get(dependency_id, gate_rows.get(dependency_id, {}))
        dependency_gate = str(dependency_row.get("decision", "MISSING_OUTPUT"))
        dependency_source_status = hf_source_status_from_row(dependency_row)
        dependency_prediction_status = hf_prediction_status_from_row(dependency_row)
        if model_id == "C":
            state = classify_c_observed_state(
                hf_dependency_source_status=dependency_source_status,
                hf_dependency_prediction_status=dependency_prediction_status,
                hf_dependency_decision=dependency_gate,
                readiness_status=ulf_readiness_status,
                efield_summary=efield_summary,
                c_outputs=c_outputs,
            )
            no_delta = c_outputs.get("branches", {}).get("no_delta_hf", {})
            delta = c_outputs.get("branches", {}).get("delta_hf_adjusted", {})
            metrics = no_delta.get("metrics", {})
            input_summary = component_summary_text(efield_summary)
            if c_outputs.get("both_branches_exist"):
                input_summary = (
                    f"{input_summary}; C observed branches exist; "
                    f"no_delta rho={metrics.get('spearman_rho', '')}, Q2={metrics.get('q2', '')}; "
                    f"delta rho={delta.get('metrics', {}).get('spearman_rho', '')}, "
                    f"Q2={delta.get('metrics', {}).get('q2', '')}"
                )
            latest_manifest = str(no_delta.get("manifest_path", ""))
            spearman_rho = metrics.get("spearman_rho", "")
            q2 = metrics.get("q2", "")
        elif model_id == "D":
            state = classify_d_observed_state(
                hf_dependency_source_status=dependency_source_status,
                hf_dependency_prediction_status=dependency_prediction_status,
                hf_dependency_decision=dependency_gate,
                readiness_status=ulf_readiness_status,
                efield_summary=efield_summary,
                d_outputs=d_outputs,
            )
            no_delta = d_outputs.get("branches", {}).get("no_delta_hf", {})
            delta = d_outputs.get("branches", {}).get("delta_hf_adjusted", {})
            metrics = no_delta.get("metrics", {})
            input_summary = component_summary_text(efield_summary)
            if d_outputs.get("both_branches_exist"):
                input_summary = (
                    f"{input_summary}; D PPMI observed branches exist; "
                    f"no_delta rho={metrics.get('spearman_rho', '')}, Q2={metrics.get('q2', '')}; "
                    f"delta rho={delta.get('metrics', {}).get('spearman_rho', '')}, "
                    f"Q2={delta.get('metrics', {}).get('q2', '')}"
                )
            latest_manifest = str(no_delta.get("manifest_path", ""))
            spearman_rho = metrics.get("spearman_rho", "")
            q2 = metrics.get("q2", "")
        else:
            state = classify_ulf_model_state(
                hf_dependency_source_status=dependency_source_status,
                hf_dependency_prediction_status=dependency_prediction_status,
                hf_dependency_decision=dependency_gate,
                readiness_status=ulf_readiness_status,
                efield_summary=efield_summary,
            )
            input_summary = component_summary_text(efield_summary)
            latest_manifest = str(ulf_manifest_path) if ulf_manifest_path else ""
            spearman_rho = ""
            q2 = ""
        rows.append(
            {
                "model_id": model_id,
                "model": model_name,
                "branch": branch,
                "dependency_model": dependency_id,
                "gate_decision": "",
                "hf_source_status": dependency_source_status,
                "spearman_rho": spearman_rho,
                "q2": q2,
                "readiness_status": ulf_readiness_status,
                "input_summary": input_summary,
                "latest_manifest": latest_manifest,
                "next_action": next_action_for_state(state),
                **state,
            }
        )

    manifest_inputs = {
        "gate_status_csv": str(gate_csv),
        "ulf_readiness_manifest": str(ulf_manifest_path) if ulf_manifest_path else "",
        "c_observed_outputs": c_outputs,
        "d_observed_outputs": d_outputs,
    }
    return rows, manifest_inputs


def component_summary_text(summary: dict[str, Any]) -> str:
    if not summary:
        return ""
    return "{}/{} component e-fields exist".format(summary.get("n_efields_existing", 0), summary.get("n_rows", 0))


def next_action_for_state(state: dict[str, str]) -> str:
    execution_status = state["execution_status"]
    if execution_status == "READY_FOR_NEXT_ROUND":
        return "run downstream branch-role resolution or smoke resampling before formal loops"
    if execution_status == "SOURCE_ACCEPTED_ERROR_NONPREDICTIVE":
        return "record source as error-nonpredictive; downstream ULF should use no_delta_hf as primary"
    if execution_status == "ABSENT_NO_STABLE_GRID":
        return "record no stable HF source; downstream ULF should run no_delta_hf only"
    if execution_status == "OBSERVED_COMPLETE_READY_FOR_ENDPOINT_RESOLVER":
        return "resolve endpoint primary branch and then decide formal resampling"
    if execution_status == "OBSERVED_COMPLETE_NO_DELTA_PRIMARY":
        return "report no_delta_hf as primary because matched HF source is absent"
    if execution_status == "WAITING_FOR_HF_SOURCE_RESOLVER":
        return "refresh matched HF source/prediction resolver before interpreting ULF branches"
    if execution_status == "OBSERVED_COMPLETE_STOPPED_BY_GATE":
        return "do not run formal resampling; report as exploratory/negative"
    if execution_status == "NOT_EXECUTABLE_INPUT_FAILURE":
        return "generate missing component-specific e-fields before any ULF execution"
    if execution_status == "EXPLORATORY_ONLY_UNSTABLE_HF_DEPENDENCY":
        return "ULF can only be exploratory unless matched HF dependency is locked"
    if execution_status == "OBSERVED_COMPLETE_EXPLORATORY":
        return "observed ULF branches complete; skip formal resampling unless matched HF dependency is locked"
    if execution_status == "OBSERVED_COMPLETE_READY_FOR_GATE":
        return "review observed ULF metrics before formal resampling"
    if execution_status == "MISSING_PRIMARY_OBSERVED_OUTPUT":
        return "run primary observed smoke branch first"
    return "inspect source manifests and QC"


def run_status(args: argparse.Namespace) -> int:
    val_root = Path(args.val_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    rows, manifest_inputs = build_status_rows(val_root)
    csv_path = output_dir / "four_model_execution_status.csv"
    md_path = output_dir / "four_model_execution_status.md"
    manifest_path = output_dir / "four_model_execution_status_manifest.json"
    fieldnames = [
        "model_id",
        "model",
        "branch",
        "execution_status",
        "dependency_model",
        "dependency_status",
        "hf_source_status",
        "hf_prediction_validity_status",
        "formal_resampling_status",
        "gate_decision",
        "spearman_rho",
        "q2",
        "readiness_status",
        "input_summary",
        "latest_manifest",
        "next_action",
    ]
    write_csv(csv_path, rows, fieldnames)
    write_markdown(md_path, rows)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "val_root": str(val_root),
            "inputs": manifest_inputs,
            "rows": rows,
            "outputs": {"csv": str(csv_path), "markdown": str(md_path), "manifest": str(manifest_path)},
        },
    )
    print(f"Execution status output: {csv_path}")
    for row in rows:
        print(f"{row['model_id']} {row['execution_status']}: {row['next_action']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val-root", default=str(DEFAULT_VAL_ROOT), help="STNSNr VAL root.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_VAL_ROOT / "summary/four_model_execution/status"),
        help="Execution status output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_status(args)


if __name__ == "__main__":
    raise SystemExit(main())
