"""Shared validation rules for scientific evidence payloads."""

from __future__ import annotations

from collections.abc import Mapping


_FORBIDDEN_CLASSIFICATION_KEYS = frozenset(
    {
        "source_status",
        "prediction_status",
        "branch_role",
        "intended_role",
        "endpoint_status",
        "endpoint_model_status",
        "final_status",
        "final_model_status",
        "source_classification_feedback",
        "classification_feedback",
    }
)
_FORBIDDEN_CLASSIFICATION_SUFFIXES = (
    "_source_status",
    "_prediction_status",
    "_branch_role",
    "_endpoint_status",
    "_endpoint_model_status",
    "_final_status",
    "_final_model_status",
)
_FORBIDDEN_CLASSIFICATION_VALUES = frozenset(
    {
        "pre_specified_accepted",
        "scan_fallback_accepted",
        "absent_no_stable_grid",
        "error_predictive",
        "error_nonpredictive",
        "final_model_realized",
        "fallback_final_realized",
        "no_final_model",
    }
)


def _classification_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return (
        normalized in _FORBIDDEN_CLASSIFICATION_KEYS
        or "classification" in normalized
        or normalized.endswith(_FORBIDDEN_CLASSIFICATION_SUFFIXES)
    )


def classification_feedback_violation(
    value: object,
    *,
    location: str = "payload",
) -> str | None:
    """Return the first classification-feedback violation in nested evidence."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            if _classification_key(key):
                return f"classification mutation key {key!r} is forbidden at {location}"
            violation = classification_feedback_violation(
                item,
                location=f"{location}.{key}",
            )
            if violation is not None:
                return violation
        return None
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            violation = classification_feedback_violation(
                item,
                location=f"{location}[{index}]",
            )
            if violation is not None:
                return violation
        return None
    if isinstance(value, str) and value.strip().lower() in _FORBIDDEN_CLASSIFICATION_VALUES:
        return f"classification value {value!r} is forbidden at {location}"
    return None


__all__ = ["classification_feedback_violation"]
