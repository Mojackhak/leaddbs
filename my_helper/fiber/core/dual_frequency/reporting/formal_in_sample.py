"""Paired final in-sample and LOOCV reporting with prespecified BH scopes."""

from __future__ import annotations

import csv
import io
import math
from typing import Any, Mapping, Sequence

from ..cache import ArtifactStore
from ..contracts import FormalResult


EXPECTED_ENDPOINTS_PER_MODEL_FAMILY = 28
EXPECTED_ENDPOINTS_ALL_FAMILIES = 112


class FormalInSampleReportingError(RuntimeError):
    """Raised when a completed in-sample record has invalid report artifacts."""


def _artifact(record: FormalResult, kind: str):
    matches = tuple(item for item in record.artifacts if item.kind == kind)
    if len(matches) != 1:
        raise FormalInSampleReportingError(
            f"in-sample result requires exactly one {kind!r} artifact"
        )
    return matches[0]


def _probability(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        return None
    return result


def _benjamini_hochberg(values: Sequence[float]) -> list[float]:
    count = len(values)
    order = sorted(range(count), key=lambda index: values[index])
    adjusted = [1.0] * count
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = count - reverse_rank + 1
        running = min(running, values[index] * count / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def _apply_scope(
    rows: list[dict[str, Any]],
    indices: Sequence[int],
    *,
    raw_field: str,
    output_field: str,
    expected_count: int,
) -> str:
    values = [_probability(rows[index].get(raw_field)) for index in indices]
    if len(indices) != expected_count or any(value is None for value in values):
        for index in indices:
            rows[index][output_field] = None
        return "incomplete_scope"
    adjusted = _benjamini_hochberg([float(value) for value in values])
    for index, value in zip(indices, adjusted, strict=True):
        rows[index][output_field] = value
    return "completed"


def build_formal_in_sample_results(
    typed_records: Mapping[str, object],
    artifact_store: ArtifactStore,
) -> dict[str, Any]:
    """Build paired endpoint rows and apply only the frozen formal BH families."""

    rows: list[dict[str, Any]] = []
    for task_id, value in typed_records.items():
        if not isinstance(value, FormalResult) or value.resampling_kind != "in_sample_permutation":
            continue
        document = artifact_store.materialize_document(
            _artifact(value, "formal_in_sample_summary"),
            expected_kind="formal_in_sample_summary",
        )
        required_mappings = ("in_sample", "loocv", "optimism_gaps")
        if any(not isinstance(document.get(name), Mapping) for name in required_mappings):
            raise FormalInSampleReportingError(
                "formal in-sample summary lacks paired metric mappings"
            )
        row: dict[str, Any] = {
            "task_id": task_id,
            "endpoint_id": document.get("endpoint_id"),
            "scale_id": document.get("scale_id"),
            "model_family": document.get("model_family"),
            "final_model_id": document.get("final_model_id"),
            "selected_tau": document.get("selected_tau"),
            "selected_coverage": document.get("selected_coverage"),
            "final_branch": document.get("final_branch"),
            "conditioning_label": document.get("conditioning_label"),
            "candidate_axis_id": document.get("candidate_axis_id"),
            "candidate_axis_sha256": document.get("candidate_axis_sha256"),
            "candidate_feature_count": document.get("candidate_feature_count"),
            "subject_axis_id": document.get("subject_axis_id"),
            "subject_axis_sha256": document.get("subject_axis_sha256"),
            "schedule_pairing_status": document.get("schedule_pairing_status"),
            "subject_mask_match": document.get("subject_mask_match"),
            "technical_status": document.get("technical_status"),
        }
        row.update(dict(document["in_sample"]))
        row.update(dict(document["loocv"]))
        row.update(dict(document["optimism_gaps"]))
        rows.append(row)
    rows.sort(key=lambda item: (str(item["model_family"]), str(item["scale_id"])))

    family_status: dict[str, dict[str, str]] = {}
    families = sorted({str(row["model_family"]) for row in rows})
    for family in families:
        indices = [
            index
            for index, row in enumerate(rows)
            if row["model_family"] == family
        ]
        family_status[family] = {
            "in_sample": _apply_scope(
                rows,
                indices,
                raw_field="in_sample_permutation_p_plus_one_two_sided",
                output_field="in_sample_permutation_q_bh_model_family",
                expected_count=EXPECTED_ENDPOINTS_PER_MODEL_FAMILY,
            ),
            "loocv": _apply_scope(
                rows,
                indices,
                raw_field="loocv_permutation_p_plus_one_two_sided",
                output_field="loocv_permutation_q_bh_model_family",
                expected_count=EXPECTED_ENDPOINTS_PER_MODEL_FAMILY,
            ),
        }

    all_indices = list(range(len(rows)))
    global_status = {
        "in_sample": _apply_scope(
            rows,
            all_indices,
            raw_field="in_sample_permutation_p_plus_one_two_sided",
            output_field="in_sample_permutation_q_bh_all_endpoints",
            expected_count=EXPECTED_ENDPOINTS_ALL_FAMILIES,
        ),
        "loocv": _apply_scope(
            rows,
            all_indices,
            raw_field="loocv_permutation_p_plus_one_two_sided",
            output_field="loocv_permutation_q_bh_all_endpoints",
            expected_count=EXPECTED_ENDPOINTS_ALL_FAMILIES,
        ),
    }
    return {
        "schema_version": "formal_in_sample_paired_results_v1",
        "primary_statistic": "in_sample_spearman_rho",
        "conditioning_scope": "conditional_on_final_model",
        "nominal_p_values_are_descriptive": True,
        "bh_contract": {
            "expected_endpoints_per_model_family": EXPECTED_ENDPOINTS_PER_MODEL_FAMILY,
            "expected_endpoints_all_families": EXPECTED_ENDPOINTS_ALL_FAMILIES,
            "model_family_status": family_status,
            "all_endpoints_status": global_status,
        },
        "result_count": len(rows),
        "results": rows,
    }


def formal_in_sample_results_csv(document: Mapping[str, Any]) -> str:
    """Render the paired rows as one deterministic interoperable CSV."""

    values = document.get("results")
    if not isinstance(values, list) or not values:
        return ""
    rows = [dict(value) for value in values if isinstance(value, Mapping)]
    if len(rows) != len(values):
        raise FormalInSampleReportingError("paired result rows must be mappings")
    preferred = [
        "endpoint_id",
        "scale_id",
        "model_family",
        "selected_tau",
        "selected_coverage",
        "final_branch",
        "in_sample_spearman_rho",
        "loocv_spearman_rho",
        "in_sample_permutation_p_plus_one_two_sided",
        "loocv_permutation_p_plus_one_two_sided",
    ]
    fields = [name for name in preferred if any(name in row for row in rows)]
    fields.extend(sorted({key for row in rows for key in row} - set(fields)))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


__all__ = [
    "EXPECTED_ENDPOINTS_ALL_FAMILIES",
    "EXPECTED_ENDPOINTS_PER_MODEL_FAMILY",
    "FormalInSampleReportingError",
    "build_formal_in_sample_results",
    "formal_in_sample_results_csv",
]
