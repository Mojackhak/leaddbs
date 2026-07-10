#!/usr/bin/env python3
"""Deterministic minimum-count scoring for STN/SNr normative-fiber models."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class NormativeFiberScoreConfig:
    """Public normative-fiber score parameters."""

    sweet_fraction: float = 0.01
    sour_fraction: float = 0.005
    weighted_peak_fraction: float = 0.05
    sweet_selected_min_count: int = 200
    sour_selected_min_count: int = 100
    weighted_peak_min_count: int = 20

    def __post_init__(self) -> None:
        for name in ("sweet_fraction", "sour_fraction", "weighted_peak_fraction"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be finite and in (0, 1]")
        for name in (
            "sweet_selected_min_count",
            "sour_selected_min_count",
            "weighted_peak_min_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) != value or int(value) < 1:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "NormativeFiberScoreConfig":
        return cls(
            sweet_fraction=float(value["sweet_fraction"]),
            sour_fraction=float(value["sour_fraction"]),
            weighted_peak_fraction=float(value["weighted_peak_fraction"]),
            sweet_selected_min_count=value["sweet_selected_min_count"],
            sour_selected_min_count=value["sour_selected_min_count"],
            weighted_peak_min_count=value["weighted_peak_min_count"],
        )


@dataclass(frozen=True)
class FiberNetScoreResult:
    """Patient scores plus deterministic signed-fiber support provenance."""

    sweet_peak5: np.ndarray
    sour_peak5: np.ndarray
    net_score: np.ndarray
    sweet_fiber_ids: np.ndarray
    sour_fiber_ids: np.ndarray
    n_sweet_peak_fibers: int
    n_sour_peak_fibers: int
    n_positive_valid_fibers: int = 0
    n_negative_valid_fibers: int = 0
    sweet_percentage_count: int = 0
    sour_percentage_count: int = 0
    sweet_actual_selected_count: int = 0
    sour_actual_selected_count: int = 0
    sweet_actual_peak_count: int = 0
    sour_actual_peak_count: int = 0
    sweet_minimum_count_dominated: bool = False
    sour_minimum_count_dominated: bool = False
    sweet_peak_minimum_count_dominated: bool = False
    sour_peak_minimum_count_dominated: bool = False
    fiber_score_support_status: str = "absent_no_valid_signed_fibers"
    sweet_selected_fiber_id_hash: str = ""
    sour_selected_fiber_id_hash: str = ""


def _ordered_id_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.int64))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _percentage_count(fraction: float, available: int) -> int:
    return int(np.ceil(float(fraction) * available)) if available > 0 else 0


def _selected_count(available: int, requested: int, minimum: int) -> int:
    return min(available, max(requested, minimum)) if available > 0 else 0


def _weighted_top_mean(
    exposure: np.ndarray,
    weights: np.ndarray,
    columns: np.ndarray,
    count: int,
) -> np.ndarray:
    if count == 0:
        return np.zeros(exposure.shape[0], dtype=float)
    weighted = exposure[:, columns] * weights[columns]
    if count < columns.size:
        weighted.partition(columns.size - count, axis=1)
    return np.mean(weighted[:, -count:], axis=1)


def _fiber_ids_are_unique(ids: np.ndarray) -> bool:
    if ids.size < 2:
        return True
    if np.all(ids[1:] > ids[:-1]) or np.all(ids[1:] < ids[:-1]):
        return True
    return bool(np.unique(ids).size == ids.size)


def _matrix_is_finite(values: np.ndarray, chunk_size: int = 1_000_000) -> bool:
    for row in values:
        for start in range(0, row.size, chunk_size):
            if not np.all(np.isfinite(row[start : start + chunk_size])):
                return False
    return True


def _support_status(
    n_positive: int,
    n_negative: int,
    config: NormativeFiberScoreConfig,
) -> str:
    if n_positive == 0 and n_negative == 0:
        return "absent_no_valid_signed_fibers"
    if n_positive > 0 and n_negative == 0:
        return "limited_positive_only"
    if n_negative > 0 and n_positive == 0:
        return "limited_negative_only"
    if (
        n_positive >= config.sweet_selected_min_count
        and n_negative >= config.sour_selected_min_count
    ):
        return "adequate_two_sign"
    return "limited_two_sign"


def fiber_net_score(
    exposure: np.ndarray,
    weights: np.ndarray,
    candidate_mask: np.ndarray,
    *,
    sweet_percent: float | None = None,
    sour_percent: float | None = None,
    peak_percent: float | None = None,
    fiber_ids: Iterable[int] | None = None,
    score_config: NormativeFiberScoreConfig | None = None,
) -> FiberNetScoreResult:
    """Compute a weighted sweet-minus-sour score on valid candidate fibers."""
    if score_config is not None and any(
        value is not None for value in (sweet_percent, sour_percent, peak_percent)
    ):
        raise ValueError("score_config cannot be combined with legacy fraction overrides")
    config = score_config or NormativeFiberScoreConfig(
        sweet_fraction=0.01 if sweet_percent is None else sweet_percent,
        sour_fraction=0.005 if sour_percent is None else sour_percent,
        weighted_peak_fraction=0.05 if peak_percent is None else peak_percent,
    )

    x = np.asarray(exposure)
    w = np.asarray(weights, dtype=float)
    candidate = np.asarray(candidate_mask, dtype=bool)
    if x.ndim != 2:
        raise ValueError("exposure must be a subject-by-fiber matrix")
    if not _matrix_is_finite(x):
        raise ValueError("exposure must contain only finite values")
    if w.ndim != 1 or x.shape[1] != w.size:
        raise ValueError("exposure columns and weights length differ")
    if candidate.ndim != 1 or candidate.size != w.size:
        raise ValueError("candidate_mask and weights length differ")

    ids = (
        np.arange(w.size, dtype=np.int64)
        if fiber_ids is None
        else np.asarray(fiber_ids, dtype=np.int64)
    )
    if ids.ndim != 1 or ids.size != w.size:
        raise ValueError("fiber_ids length differs from weights length")
    if not _fiber_ids_are_unique(ids):
        raise ValueError("canonical fiber_ids must be unique")
    valid = candidate & np.isfinite(w)
    positive_cols = np.flatnonzero(valid & (w > 0))
    negative_cols = np.flatnonzero(valid & (w < 0))
    n_positive = int(positive_cols.size)
    n_negative = int(negative_cols.size)

    sweet_percentage = _percentage_count(config.sweet_fraction, n_positive)
    sour_percentage = _percentage_count(config.sour_fraction, n_negative)
    sweet_count = _selected_count(
        n_positive,
        sweet_percentage,
        config.sweet_selected_min_count,
    )
    sour_count = _selected_count(
        n_negative,
        sour_percentage,
        config.sour_selected_min_count,
    )

    sweet_order = np.lexsort((ids[positive_cols], -w[positive_cols]))
    sour_order = np.lexsort((ids[negative_cols], w[negative_cols]))
    sweet_cols = positive_cols[sweet_order[:sweet_count]].astype(np.int64)
    sour_cols = negative_cols[sour_order[:sour_count]].astype(np.int64)
    sweet_ids = ids[sweet_cols].astype(np.int64)
    sour_ids = ids[sour_cols].astype(np.int64)

    sweet_peak_percentage = _percentage_count(
        config.weighted_peak_fraction,
        sweet_count,
    )
    sour_peak_percentage = _percentage_count(
        config.weighted_peak_fraction,
        sour_count,
    )
    sweet_peak_count = _selected_count(
        sweet_count,
        sweet_peak_percentage,
        config.weighted_peak_min_count,
    )
    sour_peak_count = _selected_count(
        sour_count,
        sour_peak_percentage,
        config.weighted_peak_min_count,
    )

    sweet_peak = _weighted_top_mean(x, w, sweet_cols, sweet_peak_count)
    sour_peak = _weighted_top_mean(x, -w, sour_cols, sour_peak_count)
    return FiberNetScoreResult(
        sweet_peak5=sweet_peak,
        sour_peak5=sour_peak,
        net_score=sweet_peak - sour_peak,
        sweet_fiber_ids=sweet_ids,
        sour_fiber_ids=sour_ids,
        n_sweet_peak_fibers=sweet_peak_count,
        n_sour_peak_fibers=sour_peak_count,
        n_positive_valid_fibers=n_positive,
        n_negative_valid_fibers=n_negative,
        sweet_percentage_count=sweet_percentage,
        sour_percentage_count=sour_percentage,
        sweet_actual_selected_count=sweet_count,
        sour_actual_selected_count=sour_count,
        sweet_actual_peak_count=sweet_peak_count,
        sour_actual_peak_count=sour_peak_count,
        sweet_minimum_count_dominated=(
            n_positive > 0 and sweet_percentage < config.sweet_selected_min_count
        ),
        sour_minimum_count_dominated=(
            n_negative > 0 and sour_percentage < config.sour_selected_min_count
        ),
        sweet_peak_minimum_count_dominated=(
            sweet_count > 0 and sweet_peak_percentage < config.weighted_peak_min_count
        ),
        sour_peak_minimum_count_dominated=(
            sour_count > 0 and sour_peak_percentage < config.weighted_peak_min_count
        ),
        fiber_score_support_status=_support_status(n_positive, n_negative, config),
        sweet_selected_fiber_id_hash=_ordered_id_hash(sweet_ids),
        sour_selected_fiber_id_hash=_ordered_id_hash(sour_ids),
    )


def score_support_fields(
    result: FiberNetScoreResult,
    config: NormativeFiberScoreConfig,
) -> dict[str, object]:
    """Return the required full-sample or fold support fields."""
    return {
        "n_positive_valid_fibers": result.n_positive_valid_fibers,
        "n_negative_valid_fibers": result.n_negative_valid_fibers,
        "sweet_fraction_requested": config.sweet_fraction,
        "sour_fraction_requested": config.sour_fraction,
        "weighted_peak_fraction_requested": config.weighted_peak_fraction,
        "sweet_selected_k_min": config.sweet_selected_min_count,
        "sour_selected_k_min": config.sour_selected_min_count,
        "weighted_peak_k_min": config.weighted_peak_min_count,
        "sweet_percentage_count": result.sweet_percentage_count,
        "sour_percentage_count": result.sour_percentage_count,
        "sweet_actual_selected_count": result.sweet_actual_selected_count,
        "sour_actual_selected_count": result.sour_actual_selected_count,
        "sweet_actual_peak_count": result.sweet_actual_peak_count,
        "sour_actual_peak_count": result.sour_actual_peak_count,
        "sweet_minimum_count_dominated": result.sweet_minimum_count_dominated,
        "sour_minimum_count_dominated": result.sour_minimum_count_dominated,
        "sweet_peak_minimum_count_dominated": result.sweet_peak_minimum_count_dominated,
        "sour_peak_minimum_count_dominated": result.sour_peak_minimum_count_dominated,
        "fiber_score_support_status": result.fiber_score_support_status,
        "sweet_selected_fiber_id_hash": result.sweet_selected_fiber_id_hash,
        "sour_selected_fiber_id_hash": result.sour_selected_fiber_id_hash,
    }


__all__ = [
    "FiberNetScoreResult",
    "NormativeFiberScoreConfig",
    "fiber_net_score",
    "score_support_fields",
]
