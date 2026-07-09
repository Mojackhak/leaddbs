#!/usr/bin/env python3
"""Build a consolidated status report for the STN/SNr four-model execution plan."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_io import iso_now, manifest_provenance_status, manifest_stale_status, write_csv, write_json

HF_SOURCE_ACCEPTED = {"pre_specified_accepted", "scan_fallback_accepted"}
ULF_SOURCE_ACCEPTED = {"pre_specified_accepted", "scan_fallback_accepted"}
PENDING_ULF_SOURCE_RESOLVER = "pending_source_resolver"
OBSERVED_ROBUSTNESS_MODEL_IDS = {"B_PPMI", "B_MGH", "D_PPMI"}
def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_provenance(repo_root: Path) -> dict[str, Any]:
    dirty_files = run_git(repo_root, ["status", "--short"]).splitlines()
    return {
        "repo_root": str(repo_root),
        "branch": run_git(repo_root, ["branch", "--show-current"]),
        "head_commit": run_git(repo_root, ["rev-parse", "HEAD"]),
        "head_short": run_git(repo_root, ["rev-parse", "--short", "HEAD"]),
        "dirty": bool(dirty_files),
        "dirty_files": dirty_files,
    }


def annotate_latest_manifest_provenance(rows: list[dict[str, Any]], current_commit: str = "") -> None:
    for row in rows:
        manifest_path = str(row.get("latest_manifest", ""))
        row["latest_manifest_provenance_status"] = manifest_provenance_status(manifest_path)
        row["latest_manifest_stale_status"] = manifest_stale_status(manifest_path, current_commit)


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


def hf_final_model_fields(source_status: str, prediction_status: str) -> dict[str, str]:
    """Return final-source fields for a foundational HF model."""
    if source_status == "pre_specified_accepted":
        role = "primary"
        source = "pre_specified"
        reason = "pre_specified_source_accepted"
    elif source_status == "scan_fallback_accepted":
        role = "fallback_final"
        source = "scan_fallback"
        reason = "pre_specified_not_accepted_scan_fallback_accepted"
    elif source_status == "absent_no_stable_grid":
        return {
            "hf_final_model_source": "none",
            "hf_final_model_role": "no_final_model",
            "hf_final_model_status": "no_final_model_absent_no_stable_grid",
            "hf_final_model_selection_reason": "no_stable_hf_source",
        }
    else:
        return {
            "hf_final_model_source": "",
            "hf_final_model_role": "",
            "hf_final_model_status": "",
            "hf_final_model_selection_reason": "waiting_for_hf_source_resolver",
        }

    if prediction_status == "error_predictive":
        status = "final_model_error_predictive"
    elif prediction_status == "error_nonpredictive":
        status = "final_model_error_nonpredictive"
    else:
        status = "final_model_prediction_not_evaluable"
    return {
        "hf_final_model_source": source,
        "hf_final_model_role": role,
        "hf_final_model_status": status,
        "hf_final_model_selection_reason": reason,
    }


def classify_hf_model_state(gate_row: dict[str, Any]) -> dict[str, str]:
    """Classify a foundational HF model from source and prediction status fields."""
    source_status = hf_source_status_from_row(gate_row)
    prediction_status = hf_prediction_status_from_row(gate_row)
    final_fields = hf_final_model_fields(source_status, prediction_status)
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_predictive":
        return {
            "execution_status": "READY_FOR_NEXT_ROUND",
            "dependency_status": "NONE",
            "formal_resampling_status": "ELIGIBLE_AFTER_SOURCE_RESOLUTION",
            "hf_prediction_validity_status": prediction_status,
            **final_fields,
        }
    if source_status in HF_SOURCE_ACCEPTED and prediction_status == "error_nonpredictive":
        return {
            "execution_status": "SOURCE_ACCEPTED_ERROR_NONPREDICTIVE",
            "dependency_status": "NONE",
            "formal_resampling_status": "NOT_STARTED_FORMAL_RESAMPLING",
            "hf_prediction_validity_status": prediction_status,
            **final_fields,
        }
    if source_status == "absent_no_stable_grid":
        return {
            "execution_status": "ABSENT_NO_STABLE_GRID",
            "dependency_status": "NONE",
            "formal_resampling_status": "NOT_APPLICABLE_NO_STABLE_SOURCE",
            "hf_prediction_validity_status": prediction_status or "not_applicable",
            **final_fields,
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
        **final_fields,
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
        "ulf_primary_branch": "",
        "delta_hfscore_role": "",
        "ulf_source_status": "",
        "ulf_prediction_status": "",
        "ulf_endpoint_model_status": "",
        "ulf_final_model_branch": "",
        "ulf_final_model_role": "",
        "ulf_final_model_status": "",
        "ulf_final_model_selection_reason": "",
        "mae_model": "",
        "mae_baseline": "",
        "rmse_model": "",
        "rmse_baseline": "",
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
        primary_branch = "no_delta_hf"
        delta_role = "not_run_no_stable_hf_source"
    elif dependency_status == "SOURCE_EXISTS_ERROR_NONPREDICTIVE":
        primary_branch = "no_delta_hf"
        delta_role = "stable_error_nonpredictive_hf_adjustment_sensitivity"
    elif dependency_status == "SOURCE_EXISTS_ERROR_PREDICTIVE":
        primary_branch = "delta_hf_adjusted"
        delta_role = "primary_error_predictive_hf_adjustment"
    else:
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
        next_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
        primary_branch = ""
        delta_role = ""
        endpoint_state = {
            "ulf_source_status": "",
            "ulf_prediction_status": "",
            "ulf_endpoint_model_status": "",
            "ulf_final_model_branch": "",
            "ulf_final_model_role": "",
            "ulf_final_model_status": "",
            "ulf_final_model_selection_reason": "",
            "mae_model": "",
            "mae_baseline": "",
            "rmse_model": "",
            "rmse_baseline": "",
        }
        return {
            "execution_status": next_status,
            "dependency_status": dependency_status,
            "formal_resampling_status": formal_status,
            "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
            "ulf_primary_branch": primary_branch,
            "delta_hfscore_role": delta_role,
            **endpoint_state,
        }
    endpoint_state = endpoint_state_from_branch(c_outputs, primary_branch, source_key="ulf_voxel_source_status")
    final_fields = ulf_final_model_fields(
        c_outputs,
        primary_branch,
        endpoint_state,
        source_key="ulf_voxel_source_status",
    )
    next_status, formal_status = execution_status_from_endpoint_state(endpoint_state)
    return {
        "execution_status": next_status,
        "dependency_status": dependency_status,
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
        "ulf_primary_branch": primary_branch,
        "delta_hfscore_role": delta_role,
        **final_fields,
        **endpoint_state,
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
        primary_branch = "no_delta_hf"
        delta_role = "not_run_no_stable_hf_source"
    elif dependency_status == "SOURCE_EXISTS_ERROR_NONPREDICTIVE":
        primary_branch = "no_delta_hf"
        delta_role = "stable_error_nonpredictive_hf_adjustment_sensitivity"
    elif dependency_status == "SOURCE_EXISTS_ERROR_PREDICTIVE":
        primary_branch = "delta_hf_adjusted"
        delta_role = "primary_error_predictive_hf_adjustment"
    else:
        formal_status = "NOT_APPLICABLE_WAITING_FOR_HF"
        next_status = "WAITING_FOR_HF_SOURCE_RESOLVER"
        primary_branch = ""
        delta_role = ""
        endpoint_state = {
            "ulf_source_status": "",
            "ulf_prediction_status": "",
            "ulf_endpoint_model_status": "",
            "ulf_final_model_branch": "",
            "ulf_final_model_role": "",
            "ulf_final_model_status": "",
            "ulf_final_model_selection_reason": "",
            "mae_model": "",
            "mae_baseline": "",
            "rmse_model": "",
            "rmse_baseline": "",
        }
        return {
            "execution_status": next_status,
            "dependency_status": dependency_status,
            "formal_resampling_status": formal_status,
            "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
            "ulf_primary_branch": primary_branch,
            "delta_hfscore_role": delta_role,
            **endpoint_state,
        }
    endpoint_state = endpoint_state_from_branch(d_outputs, primary_branch, source_key="ulf_norm_fiber_source_status")
    final_fields = ulf_final_model_fields(
        d_outputs,
        primary_branch,
        endpoint_state,
        source_key="ulf_norm_fiber_source_status",
    )
    next_status, formal_status = execution_status_from_endpoint_state(endpoint_state)
    return {
        "execution_status": next_status,
        "dependency_status": dependency_status,
        "formal_resampling_status": formal_status,
        "hf_prediction_validity_status": hf_dependency_prediction_status or "not_evaluable",
        "ulf_primary_branch": primary_branch,
        "delta_hfscore_role": delta_role,
        **final_fields,
        **endpoint_state,
    }


def endpoint_state_from_branch(outputs: dict[str, Any], primary_branch: str, *, source_key: str) -> dict[str, Any]:
    """Return endpoint-level status fields from the HF-derived intended primary branch."""
    branch = outputs.get("branches", {}).get(primary_branch, {})
    source_status = str(branch.get(source_key, "") or "")
    prediction_status = str(branch.get("ulf_prediction_status", "") or "")
    endpoint_status = ulf_endpoint_status(source_status, prediction_status)
    metrics = branch.get("baseline_comparison", {})
    return {
        "ulf_source_status": source_status,
        "ulf_prediction_status": prediction_status,
        "ulf_endpoint_model_status": endpoint_status,
        "mae_model": metrics.get("mae_model", ""),
        "mae_baseline": metrics.get("mae_baseline", ""),
        "rmse_model": metrics.get("rmse_model", ""),
        "rmse_baseline": metrics.get("rmse_baseline", ""),
    }


def ulf_final_model_fields(
    outputs: dict[str, Any],
    intended_primary_branch: str,
    endpoint_state: dict[str, Any],
    *,
    source_key: str,
) -> dict[str, str]:
    """Return the unique final-model branch for a ULF endpoint."""
    endpoint_status = str(endpoint_state.get("ulf_endpoint_model_status", "") or "")
    if endpoint_status in {"primary_branch_error_predictive", "primary_branch_error_nonpredictive"}:
        prediction_status = str(endpoint_state.get("ulf_prediction_status", "") or "")
        return {
            "ulf_final_model_branch": intended_primary_branch,
            "ulf_final_model_role": "primary",
            "ulf_final_model_status": final_model_status_from_prediction(prediction_status),
            "ulf_final_model_selection_reason": "hf_derived_intended_primary_executable",
        }
    if endpoint_status == "primary_branch_input_failure":
        fallback = outputs.get("branches", {}).get("no_delta_hf", {})
        fallback_source = str(fallback.get(source_key, "") or "")
        fallback_prediction = str(fallback.get("ulf_prediction_status", "") or "")
        if fallback_source in ULF_SOURCE_ACCEPTED:
            return {
                "ulf_final_model_branch": "no_delta_hf",
                "ulf_final_model_role": "fallback_final",
                "ulf_final_model_status": final_model_status_from_prediction(fallback_prediction),
                "ulf_final_model_selection_reason": "intended_primary_input_failure_no_delta_hf_executable",
            }
        if fallback_source == "absent_no_stable_grid":
            status = "no_final_model_absent_no_stable_grid"
            reason = "intended_primary_input_failure_no_delta_hf_absent_no_stable_grid"
        else:
            status = "no_final_model_input_failure"
            reason = "intended_primary_input_failure_no_executable_fallback"
        return {
            "ulf_final_model_branch": "none",
            "ulf_final_model_role": "no_final_model",
            "ulf_final_model_status": status,
            "ulf_final_model_selection_reason": reason,
        }
    if endpoint_status == "absent_no_stable_ulf_grid":
        return {
            "ulf_final_model_branch": "none",
            "ulf_final_model_role": "no_final_model",
            "ulf_final_model_status": "no_final_model_absent_no_stable_grid",
            "ulf_final_model_selection_reason": "intended_primary_absent_no_stable_ulf_grid",
        }
    return {
        "ulf_final_model_branch": "",
        "ulf_final_model_role": "",
        "ulf_final_model_status": "",
        "ulf_final_model_selection_reason": "waiting_for_endpoint_source_resolution",
    }


def final_model_status_from_prediction(prediction_status: str) -> str:
    if prediction_status == "error_predictive":
        return "final_model_error_predictive"
    if prediction_status == "error_nonpredictive":
        return "final_model_error_nonpredictive"
    return "final_model_prediction_not_evaluable"


def ulf_endpoint_status(source_status: str, prediction_status: str) -> str:
    """Classify the realized ULF endpoint after branch role and branch source status are known."""
    if source_status in ULF_SOURCE_ACCEPTED and prediction_status == "error_predictive":
        return "primary_branch_error_predictive"
    if source_status in ULF_SOURCE_ACCEPTED and prediction_status == "error_nonpredictive":
        return "primary_branch_error_nonpredictive"
    if source_status == "absent_no_stable_grid":
        return "absent_no_stable_ulf_grid"
    if source_status == PENDING_ULF_SOURCE_RESOLVER:
        return PENDING_ULF_SOURCE_RESOLVER
    if prediction_status:
        return "pending_source_resolver"
    return ""


def execution_status_from_endpoint_state(endpoint_state: dict[str, Any]) -> tuple[str, str]:
    endpoint_status = str(endpoint_state.get("ulf_endpoint_model_status", "") or "")
    if endpoint_status == "primary_branch_error_predictive":
        return "OBSERVED_COMPLETE_PRIMARY_ERROR_PREDICTIVE", "NOT_STARTED_FORMAL_RESAMPLING"
    if endpoint_status == "primary_branch_error_nonpredictive":
        return "OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE", "NOT_STARTED_FORMAL_RESAMPLING"
    if endpoint_status == "absent_no_stable_ulf_grid":
        return "OBSERVED_COMPLETE_ABSENT_NO_STABLE_ULF_GRID", "NOT_APPLICABLE_NO_STABLE_ULF_SOURCE"
    if endpoint_status == PENDING_ULF_SOURCE_RESOLVER:
        return "OBSERVED_COMPLETE_WAITING_FOR_ULF_SOURCE_RESOLVER", "NOT_APPLICABLE_WAITING_FOR_ULF_SOURCE_RESOLVER"
    return "OBSERVED_COMPLETE_WAITING_FOR_ULF_SOURCE_RESOLVER", "NOT_APPLICABLE_WAITING_FOR_ULF_SOURCE_RESOLVER"


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


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def prediction_baseline_comparison(predictions_csv: Path) -> dict[str, Any]:
    """Compare observed-branch LOOCV predictions against the nuisance-only baseline."""
    if not predictions_csv.is_file():
        return {"prediction_status": "not_evaluable"}
    with predictions_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"prediction_status": "not_evaluable"}
    model_prediction_column = ""
    for candidate in ("prediction_ULFScore_model", "prediction_NetFiberScore_model"):
        if candidate in rows[0]:
            model_prediction_column = candidate
            break
    if not model_prediction_column or "prediction_baseline_only" not in rows[0] or "Y_post" not in rows[0]:
        return {"prediction_status": "not_evaluable"}

    model_errors: list[float] = []
    baseline_errors: list[float] = []
    for row in rows:
        y_post = _finite_float(row.get("Y_post"))
        model_prediction = _finite_float(row.get(model_prediction_column))
        baseline_prediction = _finite_float(row.get("prediction_baseline_only"))
        if y_post is None or model_prediction is None or baseline_prediction is None:
            return {"prediction_status": "not_evaluable"}
        model_errors.append(y_post - model_prediction)
        baseline_errors.append(y_post - baseline_prediction)
    if not model_errors:
        return {"prediction_status": "not_evaluable"}
    mae_model = sum(abs(error) for error in model_errors) / len(model_errors)
    mae_baseline = sum(abs(error) for error in baseline_errors) / len(baseline_errors)
    rmse_model = math.sqrt(sum(error * error for error in model_errors) / len(model_errors))
    rmse_baseline = math.sqrt(sum(error * error for error in baseline_errors) / len(baseline_errors))
    prediction_status = (
        "error_predictive" if mae_model < mae_baseline and rmse_model < rmse_baseline else "error_nonpredictive"
    )
    return {
        "prediction_status": prediction_status,
        "mae_model": mae_model,
        "mae_baseline": mae_baseline,
        "rmse_model": rmse_model,
        "rmse_baseline": rmse_baseline,
    }


def direct_voxel_formal_resampling_status(
    permutation_summary_csv: Path,
    bootstrap_summary_csv: Path | None = None,
    jitter_summary_csv: Path | None = None,
) -> str:
    """Return direct-voxel formal status from branch-level resampling summaries."""
    if jitter_summary_csv is not None and jitter_summary_csv.is_file():
        rows = read_csv_rows(jitter_summary_csv)
        if rows:
            row = rows[0]
            status = str(row.get("jitter_status", "")).strip().lower()
            try:
                n_jitters = int(float(row.get("B", 0) or 0))
            except (TypeError, ValueError):
                n_jitters = 0
            if status == "complete" and n_jitters >= 1000:
                return "FORMAL_RESAMPLING_JITTER_COMPLETE"
    if bootstrap_summary_csv is not None and bootstrap_summary_csv.is_file():
        rows = read_csv_rows(bootstrap_summary_csv)
        if rows:
            row = rows[0]
            status = str(row.get("bootstrap_status", "")).strip().lower()
            try:
                n_bootstraps = int(float(row.get("B", 0) or 0))
            except (TypeError, ValueError):
                n_bootstraps = 0
            if status == "complete" and n_bootstraps >= 10000:
                return "FORMAL_PERMUTATION_BOOTSTRAP_COMPLETE_JITTER_NOT_STARTED"
    if not permutation_summary_csv.is_file():
        return "NOT_STARTED_FORMAL_RESAMPLING"
    rows = read_csv_rows(permutation_summary_csv)
    if not rows:
        return "PERMUTATION_SUMMARY_EMPTY"
    row = rows[0]
    status = str(row.get("permutation_status", "")).strip().lower()
    try:
        n_permutations = int(float(row.get("B", 0) or 0))
    except (TypeError, ValueError):
        n_permutations = 0
    if status == "complete" and n_permutations >= 10000:
        return "FORMAL_PERMUTATION_COMPLETE_BOOTSTRAP_NOT_STARTED"
    if status == "complete" and n_permutations > 0:
        return "SMOKE_PERMUTATION_COMPLETE_FORMAL_NOT_STARTED"
    return "PERMUTATION_INCOMPLETE"


def model_formal_resampling_scope_status(model_id: str, current_status: str) -> str:
    """Apply model-family formal scope to a formal resampling status value."""
    if model_id in OBSERVED_ROBUSTNESS_MODEL_IDS:
        return "OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING"
    return current_status


def normative_fiber_formal_resampling_status(
    smoke_summary_csv: Path,
    formal_summary_csv: Path,
    bootstrap_summary_csv: Path | None = None,
    sensitivity_status_json: Path | None = None,
) -> str:
    """Return normative-fiber status from smoke/formal permutation/bootstrap summaries."""
    if bootstrap_summary_csv is not None and bootstrap_summary_csv.is_file():
        rows = read_csv_rows(bootstrap_summary_csv)
        if rows:
            row = rows[0]
            status = str(row.get("bootstrap_status", "")).strip().lower()
            try:
                n_bootstraps = int(float(row.get("B", 0) or 0))
            except (TypeError, ValueError):
                n_bootstraps = 0
            if status == "complete" and n_bootstraps >= 10000:
                if sensitivity_status_json is not None and sensitivity_status_json.is_file():
                    sensitivity = read_json(sensitivity_status_json)
                    oss_status = str(sensitivity.get("oss_sensitivity_status", "")).strip()
                    jitter_status = str(sensitivity.get("jitter_qc_status", "")).strip()
                    missing_oss_statuses = {"not_run_missing_oss_inputs"}
                    missing_jitter_statuses = {"not_run_missing_jitter_inputs"}
                    oss_ready = oss_status == "ready_for_oss_sensitivity" or oss_status.startswith("passed_")
                    jitter_ready = jitter_status == "complete" or jitter_status.startswith("ready_for_")
                    if oss_status in missing_oss_statuses and jitter_status in missing_jitter_statuses:
                        return "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING"
                    if oss_ready and jitter_ready:
                        return "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_READY"
                    if oss_status or jitter_status:
                        return "FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_PARTIAL"
                return "FORMAL_PERMUTATION_BOOTSTRAP_COMPLETE_JITTER_NOT_STARTED"
    if formal_summary_csv.is_file():
        rows = read_csv_rows(formal_summary_csv)
        if rows:
            row = rows[0]
            status = str(row.get("permutation_status", "")).strip().lower()
            try:
                n_permutations = int(float(row.get("B", 0) or 0))
            except (TypeError, ValueError):
                n_permutations = 0
            if status == "complete" and n_permutations >= 10000:
                return "FORMAL_PERMUTATION_COMPLETE_BOOTSTRAP_NOT_STARTED"
    if smoke_summary_csv.is_file():
        rows = read_csv_rows(smoke_summary_csv)
        if rows:
            row = rows[0]
            status = str(row.get("permutation_status", "")).strip().lower()
            tier = str(row.get("resampling_tier", "")).strip().lower()
            try:
                n_permutations = int(float(row.get("B", 0) or 0))
            except (TypeError, ValueError):
                n_permutations = 0
            if status == "complete" and tier == "smoke" and n_permutations >= 1000:
                return "SMOKE_PERMUTATION_COMPLETE_FORMAL_NOT_STARTED"
            if status == "complete" and n_permutations > 0:
                return "SMOKE_PERMUTATION_PARTIAL_FORMAL_NOT_STARTED"
    return "NOT_STARTED_FORMAL_RESAMPLING"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def default_c_output_root(val_root: Path) -> Path:
    return val_root / "summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200"


def default_d_output_root(val_root: Path, connectome_slug: str = "ppmi_85_ewert_2017", tau: int = 800) -> Path:
    return (
        val_root
        / "summary/normative_connectome_fiber/ulf"
        / connectome_slug
        / "mds_updrs_iii_score_stn_snr_3_m"
        / f"peak_efield_tau{tau}_observed"
    )


def read_c_observed_outputs(val_root: Path) -> dict[str, Any]:
    root = default_c_output_root(val_root)
    source_manifest = (
        root.parent
        / "tau_coverage_source_resolver_scan"
        / "direct_voxel_ULF_only_tau_coverage_source_resolver_manifest.json"
    )
    source_data = read_json(source_manifest)
    branch_resolutions = source_data.get("branch_resolutions", {})
    branches = {
        "no_delta_hf": root / "partial_spearman_no_delta_hf",
        "delta_hf_adjusted": root / "partial_spearman_delta_hf_adjusted",
    }
    out: dict[str, Any] = {
        "root": str(root),
        "source_resolver_manifest": str(source_manifest),
        "source_resolver_exists": source_manifest.is_file(),
        "ulf_endpoint_model_status": source_data.get("ulf_endpoint_model_status", ""),
        "branches": {},
        "both_branches_exist": False,
    }
    for key, branch_dir in branches.items():
        manifest = branch_dir / "direct_voxel_ULF_only_generation_manifest.json"
        qc = branch_dir / "direct_voxel_ULF_only_mapping_qc.json"
        scores = branch_dir / "direct_voxel_ULF_only_scores.csv"
        predictions = branch_dir / "direct_voxel_ULF_only_loocv_predictions.csv"
        manifest_data = read_json(manifest)
        qc_data = read_json(qc)
        baseline_comparison = prediction_baseline_comparison(predictions)
        resolved = branch_resolutions.get(key, {})
        source_status = manifest_data.get("ulf_voxel_source_status", "") or resolved.get("ulf_voxel_source_status", "")
        if not source_status and predictions.is_file():
            source_status = PENDING_ULF_SOURCE_RESOLVER
        out["branches"][key] = {
            "branch_dir": str(branch_dir),
            "manifest_path": str(manifest),
            "qc_path": str(qc),
            "predictions_path": str(predictions),
            "manifest_exists": manifest.is_file(),
            "qc_exists": qc.is_file(),
            "scores_exists": scores.is_file(),
            "predictions_exists": predictions.is_file(),
            "metrics": qc_data.get("loocv_metrics", {}),
            "baseline_comparison": baseline_comparison,
            "ulf_voxel_source_status": source_status,
            "ulf_prediction_status": manifest_data.get(
                "ulf_voxel_prediction_status",
                resolved.get("ulf_voxel_prediction_status", baseline_comparison.get("prediction_status", "")),
            ),
            "ulf_voxel_threshold_source": resolved.get("ulf_voxel_threshold_source", ""),
            "ulf_voxel_selected_tau_v_per_m": resolved.get("ulf_voxel_selected_tau_v_per_m", ""),
            "ulf_voxel_selected_coverage": resolved.get("ulf_voxel_selected_coverage", ""),
            "ulf_voxel_selected_adjacent_passing_grid_cells": resolved.get(
                "ulf_voxel_selected_adjacent_passing_grid_cells", ""
            ),
            "ulf_primary_branch": manifest_data.get("ulf_primary_branch", ""),
            "delta_hfscore_role": manifest_data.get("delta_hfscore_role", ""),
            "hf_prediction_validity_status": manifest_data.get("hf_prediction_validity_status", ""),
        }
    out["both_branches_exist"] = all(
        row["manifest_exists"] and row["qc_exists"] and row["scores_exists"] and row["predictions_exists"]
        for row in out["branches"].values()
    )
    return out


def read_d_observed_outputs(
    val_root: Path,
    *,
    connectome_slug: str = "ppmi_85_ewert_2017",
    connectome_label: str = "PPMI 85",
    status_connectome_key: str = "ppmi",
) -> dict[str, Any]:
    default_root = default_d_output_root(val_root, connectome_slug=connectome_slug, tau=800)
    source_manifest = (
        default_root
        / "tau_coverage_source_resolver_scan"
        / "normative_ULF_fiber_tau_coverage_source_resolver_manifest.json"
    )
    source_data = read_json(source_manifest)
    branch_resolutions = source_data.get("branch_resolutions", {})
    intended_primary = source_data.get("intended_primary_branch", source_data.get("ulf_primary_branch", "no_delta_hf"))
    selected_tau = (
        branch_resolutions.get(intended_primary, {}).get("ulf_norm_fiber_selected_tau_v_per_m")
        or branch_resolutions.get("no_delta_hf", {}).get("ulf_norm_fiber_selected_tau_v_per_m")
        or 800
    )
    try:
        selected_tau_int = int(float(selected_tau))
    except (TypeError, ValueError):
        selected_tau_int = 800
    root = default_d_output_root(val_root, connectome_slug=connectome_slug, tau=selected_tau_int)
    branches = {
        "no_delta_hf": root / f"ulf_peak_efield_tau{selected_tau_int}_no_delta_hf",
        "delta_hf_adjusted": root / f"ulf_peak_efield_tau{selected_tau_int}_delta_hf_adjusted",
    }
    out: dict[str, Any] = {
        "root": str(root),
        "connectome": connectome_label,
        "source_resolver_manifest": str(source_manifest),
        "source_resolver_exists": source_manifest.is_file(),
        "ulf_norm_fiber_endpoint_model_status": source_data.get("ulf_norm_fiber_endpoint_model_status", ""),
        "selected_tau": selected_tau_int,
        "status_branch": f"chronic/{status_connectome_key}/"
        f"peak_efield_tau{selected_tau_int}_no_delta_hf+delta_hf_adjusted",
        "branches": {},
        "both_branches_exist": False,
    }
    for key, branch_dir in branches.items():
        manifest = branch_dir / "normative_ULF_fiber_generation_manifest.json"
        qc = branch_dir / "normative_ULF_fiber_mapping_qc.json"
        scores = branch_dir / "normative_ULF_fiber_scores.csv"
        predictions = branch_dir / "normative_ULF_fiber_loocv_predictions.csv"
        manifest_data = read_json(manifest)
        qc_data = read_json(qc)
        baseline_comparison = prediction_baseline_comparison(predictions)
        resolved = branch_resolutions.get(key, {})
        source_status = manifest_data.get("ulf_norm_fiber_source_status", "") or resolved.get(
            "ulf_norm_fiber_source_status", ""
        )
        if not source_status and predictions.is_file():
            source_status = PENDING_ULF_SOURCE_RESOLVER
        out["branches"][key] = {
            "branch_dir": str(branch_dir),
            "manifest_path": str(manifest),
            "qc_path": str(qc),
            "predictions_path": str(predictions),
            "manifest_exists": manifest.is_file(),
            "qc_exists": qc.is_file(),
            "scores_exists": scores.is_file(),
            "predictions_exists": predictions.is_file(),
            "metrics": qc_data.get("loocv_metrics", {}),
            "baseline_comparison": baseline_comparison,
            "ulf_norm_fiber_source_status": source_status,
            "ulf_prediction_status": manifest_data.get(
                "ulf_norm_fiber_prediction_status",
                resolved.get("ulf_norm_fiber_prediction_status", baseline_comparison.get("prediction_status", "")),
            ),
            "ulf_norm_fiber_threshold_source": resolved.get("ulf_norm_fiber_threshold_source", ""),
            "ulf_norm_fiber_selected_tau_v_per_m": resolved.get("ulf_norm_fiber_selected_tau_v_per_m", ""),
            "ulf_norm_fiber_selected_coverage": resolved.get("ulf_norm_fiber_selected_coverage", ""),
            "ulf_norm_fiber_selected_adjacent_passing_grid_cells": resolved.get(
                "ulf_norm_fiber_selected_adjacent_passing_grid_cells", ""
            ),
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


def read_b_hf_norm_fiber_resolver_row(val_root: Path, connectome_slug: str) -> dict[str, Any]:
    """Read a B normative-fiber resolver manifest for the chronic total endpoint if available."""
    manifest_path = (
        val_root
        / "summary/normative_connectome_fiber/hf"
        / connectome_slug
        / "mds_updrs_iii_score_stn_3_m"
        / "tau_coverage_source_resolver_scan"
        / "normative_HF_fiber_tau_coverage_source_resolver_manifest.json"
    )
    if not manifest_path.is_file():
        return {}
    data = read_json(manifest_path)
    return {
        "hf_norm_fiber_source_status": data.get("hf_norm_fiber_source_status", ""),
        "hf_norm_fiber_prediction_status": data.get("hf_norm_fiber_prediction_status", ""),
        "hf_norm_fiber_threshold_source": data.get("hf_norm_fiber_threshold_source", ""),
        "hf_norm_fiber_selected_tau_v_per_m": data.get("hf_norm_fiber_selected_tau_v_per_m", ""),
        "hf_norm_fiber_selected_coverage": data.get("hf_norm_fiber_selected_coverage", ""),
        "hf_norm_fiber_selected_adjacent_passing_grid_cells": data.get(
            "hf_norm_fiber_selected_adjacent_passing_grid_cells", ""
        ),
        "hf_norm_fiber_source_failure_reasons": data.get("hf_norm_fiber_source_failure_reasons", ""),
        "manifest_path": str(manifest_path),
    }


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Four-Model Execution Status",
        "",
        "Current cohort size is `n=16`. These outputs remain hypothesis-generating unless a branch passes the declared gate and the corresponding formal validation is run.",
        "",
        "| Model | Status | Dependency | HF source | HF prediction | ULF primary | ULF source | ULF prediction | ULF endpoint | Formal resampling | Next action |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {model_id}: {model} | {execution_status} | {dependency_status} | "
            "{hf_source_status} | "
            "{hf_prediction_validity_status} | "
            "{ulf_primary_branch} | "
            "{ulf_source_status} | "
            "{ulf_prediction_status} | "
            "{ulf_endpoint_model_status} | "
            "{formal_resampling_status} | {next_action} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_status_rows(val_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gate_csv = val_root / "summary/four_model_execution/gate_status/four_model_gate_status.csv"
    gate_rows = read_gate_rows(gate_csv)
    a_resolver_row = read_a_hf_voxel_resolver_row(val_root)
    b_resolver_rows = {
        "B_PPMI": read_b_hf_norm_fiber_resolver_row(val_root, "ppmi_85_ewert_2017"),
        "B_MGH": read_b_hf_norm_fiber_resolver_row(val_root, "mgh_usc_hcp_32_horn_2017"),
        "B_DTOR": read_b_hf_norm_fiber_resolver_row(val_root, "dtor_985_full_elias_2024"),
    }
    ulf_root = val_root / "summary/four_model_execution/ulf_component_readiness"
    ulf_run = latest_run_dir(ulf_root)
    ulf_manifest_path = ulf_run / "ulf_component_readiness_manifest.json" if ulf_run else Path("")
    ulf_manifest = read_json(ulf_manifest_path)
    ulf_readiness_status = str(ulf_manifest.get("status", "MISSING_ULF_READINESS"))
    efield_summary = ulf_manifest.get("component_efield_summary", {})
    c_outputs = read_c_observed_outputs(val_root)
    d_outputs_by_model = {
        "D_PPMI": read_d_observed_outputs(
            val_root,
            connectome_slug="ppmi_85_ewert_2017",
            connectome_label="PPMI 85",
            status_connectome_key="ppmi",
        ),
        "D_DTOR": read_d_observed_outputs(
            val_root,
            connectome_slug="dtor_985_full_elias_2024",
            connectome_label="dTOR-985 Full (Elias 2024)",
            status_connectome_key="dtor",
        ),
    }

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
        if model_id in b_resolver_rows and b_resolver_rows[model_id]:
            resolver_row.update(b_resolver_rows[model_id])
        state = classify_hf_model_state(resolver_row)
        latest_manifest = str(gate_row.get("manifest_path", ""))
        if model_id == "A" and latest_manifest:
            branch_dir = Path(latest_manifest).parent
            formal_status = direct_voxel_formal_resampling_status(
                branch_dir / "direct_voxel_HF_permutation_summary.csv",
                branch_dir / "direct_voxel_HF_bootstrap_summary.csv",
                branch_dir / "direct_voxel_HF_jitter_summary.csv",
            )
            if formal_status != "NOT_STARTED_FORMAL_RESAMPLING":
                state["formal_resampling_status"] = formal_status
        if model_id == "B_DTOR" and latest_manifest:
            branch_dir = Path(latest_manifest).parent
            formal_status = normative_fiber_formal_resampling_status(
                branch_dir / "normative_HF_fiber_smoke_permutation_summary.csv",
                branch_dir / "normative_HF_fiber_permutation_summary.csv",
                branch_dir / "normative_HF_fiber_bootstrap_summary.csv",
                branch_dir / "normative_HF_fiber_sensitivity_readiness_status.json",
            )
            if formal_status != "NOT_STARTED_FORMAL_RESAMPLING":
                state["formal_resampling_status"] = formal_status
        state["formal_resampling_status"] = model_formal_resampling_scope_status(
            model_id, state.get("formal_resampling_status", "")
        )
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
                "latest_manifest": latest_manifest,
                "ulf_primary_branch": "",
                "ulf_source_status": "",
                "ulf_prediction_status": "",
                "ulf_endpoint_model_status": "",
                "delta_hfscore_role": "",
                "mae_model": "",
                "mae_baseline": "",
                "rmse_model": "",
                "rmse_baseline": "",
                "next_action": next_action_for_state(state),
                **state,
            }
        )

    for model_id, model_name, dependency_id, fallback_branch in [
        ("C", "ULF add-on direct voxel", "A", "chronic/tau200/partial_spearman_no_delta_hf+delta_hf_adjusted"),
        (
            "D_PPMI",
            "ULF add-on normative fiber PPMI",
            "B_PPMI",
            "",
        ),
        (
            "D_DTOR",
            "ULF add-on normative fiber dTOR",
            "B_DTOR",
            "",
        ),
    ]:
        branch = fallback_branch
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
                primary_branch = state.get("ulf_primary_branch", "")
                primary = c_outputs.get("branches", {}).get(primary_branch, {})
                primary_comparison = primary.get("baseline_comparison", {})
                input_summary = (
                    f"{input_summary}; C observed branches exist; "
                    f"no_delta rho={metrics.get('spearman_rho', '')}, Q2={metrics.get('q2', '')}; "
                    f"delta rho={delta.get('metrics', {}).get('spearman_rho', '')}, "
                    f"Q2={delta.get('metrics', {}).get('q2', '')}; "
                    f"primary {primary_branch} source={state.get('ulf_source_status', '')}; "
                    f"prediction={state.get('ulf_prediction_status', '')}; "
                    f"MAE/RMSE model={primary_comparison.get('mae_model', '')}/"
                    f"{primary_comparison.get('rmse_model', '')}; "
                    f"baseline={primary_comparison.get('mae_baseline', '')}/"
                    f"{primary_comparison.get('rmse_baseline', '')}"
                )
            final_branch = str(state.get("ulf_final_model_branch") or state.get("ulf_primary_branch") or "no_delta_hf")
            final_branch_row = c_outputs.get("branches", {}).get(final_branch, no_delta)
            latest_manifest = str(final_branch_row.get("manifest_path", ""))
            if latest_manifest:
                branch_dir = Path(latest_manifest).parent
                formal_status = direct_voxel_formal_resampling_status(
                    branch_dir / "direct_voxel_ULF_only_permutation_summary.csv",
                    branch_dir / "direct_voxel_ULF_only_bootstrap_summary.csv",
                    branch_dir / "direct_voxel_ULF_only_jitter_summary.csv",
                )
                if formal_status != "NOT_STARTED_FORMAL_RESAMPLING":
                    state["formal_resampling_status"] = formal_status
            spearman_rho = metrics.get("spearman_rho", "")
            q2 = metrics.get("q2", "")
        elif model_id in d_outputs_by_model:
            d_outputs = d_outputs_by_model[model_id]
            branch = str(d_outputs.get("status_branch") or fallback_branch)
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
                primary_branch = state.get("ulf_primary_branch", "")
                primary = d_outputs.get("branches", {}).get(primary_branch, {})
                primary_comparison = primary.get("baseline_comparison", {})
                input_summary = (
                    f"{input_summary}; {model_id} observed branches exist; "
                    f"no_delta rho={metrics.get('spearman_rho', '')}, Q2={metrics.get('q2', '')}; "
                    f"delta rho={delta.get('metrics', {}).get('spearman_rho', '')}, "
                    f"Q2={delta.get('metrics', {}).get('q2', '')}; "
                    f"primary {primary_branch} source={state.get('ulf_source_status', '')}; "
                    f"prediction={state.get('ulf_prediction_status', '')}; "
                    f"MAE/RMSE model={primary_comparison.get('mae_model', '')}/"
                    f"{primary_comparison.get('rmse_model', '')}; "
                    f"baseline={primary_comparison.get('mae_baseline', '')}/"
                    f"{primary_comparison.get('rmse_baseline', '')}"
                )
            latest_manifest = str(no_delta.get("manifest_path", ""))
            spearman_rho = metrics.get("spearman_rho", "")
            q2 = metrics.get("q2", "")
            if model_id == "D_DTOR" and latest_manifest:
                branch_dir = Path(latest_manifest).parent
                formal_status = normative_fiber_formal_resampling_status(
                    branch_dir / "normative_ULF_fiber_smoke_permutation_summary.csv",
                    branch_dir / "normative_ULF_fiber_permutation_summary.csv",
                    branch_dir / "normative_ULF_fiber_bootstrap_summary.csv",
                    branch_dir / "normative_ULF_fiber_sensitivity_readiness_status.json",
                )
                if formal_status != "NOT_STARTED_FORMAL_RESAMPLING":
                    state["formal_resampling_status"] = formal_status
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
        state["formal_resampling_status"] = model_formal_resampling_scope_status(
            model_id, state.get("formal_resampling_status", "")
        )
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
        "d_observed_outputs": d_outputs_by_model,
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
        return "record final source as error-nonpredictive; downstream ULF should use no_delta_hf as primary"
    if execution_status == "ABSENT_NO_STABLE_GRID":
        return "record no stable HF source; downstream ULF should run no_delta_hf only"
    if execution_status == "OBSERVED_COMPLETE_READY_FOR_ENDPOINT_RESOLVER":
        return "resolve endpoint primary branch and then decide formal resampling"
    if execution_status == "OBSERVED_COMPLETE_WAITING_FOR_ULF_SOURCE_RESOLVER":
        return "run branch-specific ULF source resolver before endpoint realization or formal resampling"
    if execution_status == "OBSERVED_COMPLETE_PRIMARY_ERROR_PREDICTIVE":
        return "run formal resampling for the final model branch"
    if execution_status == "OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE":
        return "record final model branch as error-nonpredictive; formal resampling attaches to this final model"
    if execution_status == "OBSERVED_COMPLETE_ABSENT_NO_STABLE_ULF_GRID":
        return "record no stable ULF source; do not run formal resampling for this endpoint branch"
    if execution_status == "OBSERVED_COMPLETE_NO_DELTA_PRIMARY":
        return "report no_delta_hf as primary because matched HF source is absent or error-nonpredictive"
    if execution_status == "OBSERVED_COMPLETE_DELTA_HF_PRIMARY":
        return "report delta_hf_adjusted as primary after verifying DeltaHFScore inputs"
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
    repo_root = Path(args.repo_root).expanduser().resolve()
    annotate_latest_manifest_provenance(rows, current_commit=run_git(repo_root, ["rev-parse", "HEAD"]))
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
        "hf_final_model_source",
        "hf_final_model_role",
        "hf_final_model_status",
        "hf_final_model_selection_reason",
        "ulf_primary_branch",
        "ulf_final_model_branch",
        "ulf_final_model_role",
        "ulf_final_model_status",
        "ulf_final_model_selection_reason",
        "delta_hfscore_role",
        "ulf_source_status",
        "ulf_prediction_status",
        "ulf_endpoint_model_status",
        "mae_model",
        "mae_baseline",
        "rmse_model",
        "rmse_baseline",
        "formal_resampling_status",
        "gate_decision",
        "spearman_rho",
        "q2",
        "readiness_status",
        "input_summary",
        "latest_manifest",
        "latest_manifest_provenance_status",
        "latest_manifest_stale_status",
        "next_action",
    ]
    write_csv(csv_path, rows, fieldnames)
    write_markdown(md_path, rows)
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "val_root": str(val_root),
            "git_provenance": git_provenance(repo_root),
            "inputs": manifest_inputs,
            "rows": rows,
            "outputs": {"csv": str(csv_path), "markdown": str(md_path), "manifest": str(manifest_path)},
        },
        add_code_provenance=True,
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
    parser.add_argument("--repo-root", default=str(default_repo_root()), help="Git worktree root for status provenance.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_status(args)


if __name__ == "__main__":
    raise SystemExit(main())
