"""Deterministic signed-library weighted-peak scoring for normative fibers."""

from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json

import numpy as np

from ...cache import IndexedArrayReader
from ...contracts import NormativeFiberScoreSettings


class FiberScoreError(ValueError):
    """Raised when signed-fiber score inputs violate the contract."""


@dataclass(frozen=True)
class FiberScoreResult:
    """Patient scores and deterministic signed-fiber support provenance."""

    sweet_peak: np.ndarray
    sour_peak: np.ndarray
    net_score: np.ndarray
    sweet_fiber_ids: np.ndarray
    sour_fiber_ids: np.ndarray
    n_positive_valid_fibers: int
    n_negative_valid_fibers: int
    sweet_percentage_count: int
    sour_percentage_count: int
    sweet_actual_selected_count: int
    sour_actual_selected_count: int
    sweet_actual_peak_count: int
    sour_actual_peak_count: int
    sweet_minimum_count_dominated: bool
    sour_minimum_count_dominated: bool
    sweet_peak_minimum_count_dominated: bool
    sour_peak_minimum_count_dominated: bool
    fiber_score_support_status: str
    sweet_selected_fiber_id_hash: str
    sour_selected_fiber_id_hash: str

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, np.ndarray):
                value.flags.writeable = False


@dataclass(frozen=True)
class FiberScoreState:
    """Lightweight score and signed-support state for a null replicate."""

    net_score: np.ndarray
    n_positive_valid_fibers: int
    n_negative_valid_fibers: int
    fiber_score_support_status: str

    def __post_init__(self) -> None:
        self.net_score.flags.writeable = False


def _ordered_id_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.int64))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _count(fraction: float, available: int, minimum: int) -> tuple[int, int]:
    percentage = int(np.ceil(fraction * available)) if available else 0
    selected = min(available, max(percentage, minimum)) if available else 0
    return percentage, selected


def _support_status(
    n_positive: int,
    n_negative: int,
    settings: NormativeFiberScoreSettings,
) -> str:
    if n_positive == 0 and n_negative == 0:
        return "absent_no_valid_signed_fibers"
    if n_negative == 0:
        return "limited_positive_only"
    if n_positive == 0:
        return "limited_negative_only"
    if (
        n_positive >= settings.sweet_selected_min_count
        and n_negative >= settings.sour_selected_min_count
    ):
        return "adequate_two_sign"
    return "limited_two_sign"


def _top_mean_chunked(
    exposure: np.ndarray | IndexedArrayReader,
    weights: np.ndarray,
    columns: np.ndarray,
    count: int,
    *,
    chunk_size: int,
) -> np.ndarray:
    if count == 0:
        return np.zeros(exposure.shape[0], dtype=np.float64)
    retained = np.empty((exposure.shape[0], 0), dtype=np.float64)
    for start in range(0, columns.size, chunk_size):
        selected = columns[start : start + chunk_size]
        block = np.asarray(exposure[:, selected], dtype=np.float64) * weights[selected]
        if not np.all(np.isfinite(block)):
            raise FiberScoreError("exposure must contain only finite values")
        combined = np.concatenate((retained, block), axis=1)
        if combined.shape[1] > count:
            split = combined.shape[1] - count
            combined.partition(split, axis=1)
            retained = combined[:, split:]
        else:
            retained = combined
    return np.mean(retained, axis=1)


def _validate_exposure(
    exposure: np.ndarray | IndexedArrayReader,
    chunk_size: int,
) -> np.ndarray | IndexedArrayReader:
    matrix = (
        exposure
        if isinstance(exposure, IndexedArrayReader)
        else np.asanyarray(exposure)
    )
    if matrix.ndim != 2 or not all(dimension > 0 for dimension in matrix.shape):
        raise FiberScoreError("exposure must be a nonempty subject-by-fiber matrix")
    if matrix.dtype == object or not np.issubdtype(matrix.dtype, np.number):
        raise FiberScoreError("exposure must contain numeric values")
    if np.issubdtype(matrix.dtype, np.complexfloating):
        raise FiberScoreError("exposure must contain real values")
    for start in range(0, matrix.shape[1], chunk_size):
        if not np.all(np.isfinite(np.asarray(matrix[:, start : start + chunk_size]))):
            raise FiberScoreError("exposure must contain only finite values")
    return matrix


def _validate_fiber_ids(fiber_ids: np.ndarray, count: int) -> np.ndarray:
    ids = np.asarray(fiber_ids)
    if (
        ids.ndim != 1
        or ids.size != count
        or ids.dtype == object
        or not np.issubdtype(ids.dtype, np.integer)
    ):
        raise FiberScoreError(
            "fiber_ids must be a matching one-dimensional integer array"
        )
    if np.issubdtype(ids.dtype, np.unsignedinteger) and np.any(
        ids > np.iinfo(np.int64).max
    ):
        raise FiberScoreError("fiber_ids exceed the canonical int64 range")
    canonical = np.asarray(ids, dtype=np.int64)
    if np.unique(canonical).size != canonical.size:
        raise FiberScoreError("canonical fiber_ids must be unique")
    canonical = canonical.copy()
    canonical.flags.writeable = False
    return canonical


class PrevalidatedFiberScoreWorkspace:
    """Reuse invariant fiber-axis validation and bounded top-k scratch."""

    def __init__(
        self,
        exposure: np.ndarray | IndexedArrayReader,
        fiber_ids: np.ndarray,
        *,
        chunk_size: int = 8_192,
    ) -> None:
        if type(chunk_size) is not int or chunk_size < 1:
            raise FiberScoreError("chunk_size must be a positive integer")
        self.exposure = _validate_exposure(exposure, chunk_size)
        self.fiber_ids = _validate_fiber_ids(fiber_ids, self.exposure.shape[1])
        self.chunk_size = chunk_size
        self._scratch_capacity = 0
        self._retained_scratch = np.empty(
            (self.exposure.shape[0], 0),
            dtype=np.float64,
        )
        self._merge_scratch = np.empty(
            (self.exposure.shape[0], chunk_size),
            dtype=np.float64,
        )

    @property
    def scratch_capacity(self) -> int:
        """Return the current retained top-k capacity."""

        return self._scratch_capacity

    def _ensure_scratch(self, count: int) -> None:
        if count <= self._scratch_capacity:
            return
        self._scratch_capacity = count
        self._retained_scratch = np.empty(
            (self.exposure.shape[0], count),
            dtype=np.float64,
        )
        self._merge_scratch = np.empty(
            (self.exposure.shape[0], count + self.chunk_size),
            dtype=np.float64,
        )

    def _top_mean(
        self,
        weights: np.ndarray,
        columns: np.ndarray,
        count: int,
    ) -> np.ndarray:
        if count == 0:
            return np.zeros(self.exposure.shape[0], dtype=np.float64)
        self._ensure_scratch(count)
        retained_count = 0
        for start in range(0, columns.size, self.chunk_size):
            selected = columns[start : start + self.chunk_size]
            combined_count = retained_count + selected.size
            self._merge_scratch[:, :retained_count] = self._retained_scratch[
                :, :retained_count
            ]
            block = self._merge_scratch[:, retained_count:combined_count]
            np.multiply(
                np.asarray(self.exposure[:, selected], dtype=np.float64),
                weights[selected],
                out=block,
            )
            if not np.all(np.isfinite(block)):
                raise FiberScoreError("exposure must contain only finite values")
            combined = self._merge_scratch[:, :combined_count]
            if combined_count > count:
                split = combined_count - count
                combined.partition(split, axis=1)
                retained_count = count
                self._retained_scratch[:, :count] = combined[:, split:]
            else:
                retained_count = combined_count
                self._retained_scratch[:, :retained_count] = combined
        return np.mean(self._retained_scratch[:, :retained_count], axis=1)

    def score(
        self,
        weights: np.ndarray,
        settings: NormativeFiberScoreSettings,
        *,
        candidate_mask: np.ndarray,
    ) -> FiberScoreResult:
        """Score new outcome-specific weights without retaining fitted state."""

        result = _score_signed_fibers(
            self.exposure,
            weights,
            self.fiber_ids,
            settings,
            candidate_mask=candidate_mask,
            chunk_size=self.chunk_size,
            validate_exposure=False,
            workspace=self,
        )
        if not isinstance(result, FiberScoreResult):
            raise AssertionError("complete fiber scoring returned lightweight state")
        return result

    def score_state(
        self,
        weights: np.ndarray,
        settings: NormativeFiberScoreSettings,
        *,
        candidate_mask: np.ndarray,
    ) -> FiberScoreState:
        """Return only net scores and signed-support state for a null call."""

        result = _score_signed_fibers(
            self.exposure,
            weights,
            self.fiber_ids,
            settings,
            candidate_mask=candidate_mask,
            chunk_size=self.chunk_size,
            validate_exposure=False,
            workspace=self,
            retain_metadata=False,
        )
        if not isinstance(result, FiberScoreState):
            raise AssertionError("lightweight fiber scoring returned complete metadata")
        return result


def _score_signed_fibers(
    exposure: np.ndarray,
    weights: np.ndarray,
    fiber_ids: np.ndarray,
    settings: NormativeFiberScoreSettings,
    *,
    candidate_mask: np.ndarray | None = None,
    chunk_size: int = 8_192,
    validate_exposure: bool,
    workspace: PrevalidatedFiberScoreWorkspace | None = None,
    retain_metadata: bool = True,
) -> FiberScoreResult | FiberScoreState:
    if not isinstance(settings, NormativeFiberScoreSettings):
        raise FiberScoreError("settings must be NormativeFiberScoreSettings")
    if type(chunk_size) is not int or chunk_size < 1:
        raise FiberScoreError("chunk_size must be a positive integer")
    matrix = (
        workspace.exposure
        if workspace is not None
        else (
            _validate_exposure(exposure, chunk_size)
            if validate_exposure
            else np.asanyarray(exposure)
        )
    )
    if matrix.ndim != 2 or not all(dimension > 0 for dimension in matrix.shape):
        raise FiberScoreError("exposure must be a nonempty subject-by-fiber matrix")
    coefficients = np.asarray(weights, dtype=np.float64)
    if coefficients.ndim != 1 or coefficients.size != matrix.shape[1]:
        raise FiberScoreError("weights must match the fiber axis")

    ids = (
        workspace.fiber_ids
        if workspace is not None
        else _validate_fiber_ids(fiber_ids, coefficients.size)
    )

    if candidate_mask is None:
        candidate = np.ones(coefficients.size, dtype=bool)
    else:
        candidate = np.asarray(candidate_mask)
        if candidate.ndim != 1 or candidate.size != coefficients.size:
            raise FiberScoreError("candidate_mask must match the fiber axis")
        if candidate.dtype != np.dtype(bool):
            raise FiberScoreError("candidate_mask must be boolean")

    valid = candidate & np.isfinite(coefficients)
    positive = np.flatnonzero(valid & (coefficients > 0))
    negative = np.flatnonzero(valid & (coefficients < 0))
    n_positive = int(positive.size)
    n_negative = int(negative.size)
    sweet_percentage, sweet_count = _count(
        settings.sweet_fraction,
        n_positive,
        settings.sweet_selected_min_count,
    )
    sour_percentage, sour_count = _count(
        settings.sour_fraction,
        n_negative,
        settings.sour_selected_min_count,
    )

    sweet_order = np.lexsort((ids[positive], -coefficients[positive]))
    sour_order = np.lexsort((ids[negative], coefficients[negative]))
    sweet_columns = positive[sweet_order[:sweet_count]].astype(np.int64)
    sour_columns = negative[sour_order[:sour_count]].astype(np.int64)
    sweet_ids = ids[sweet_columns]
    sour_ids = ids[sour_columns]

    sweet_peak_percentage, sweet_peak_count = _count(
        settings.weighted_peak_fraction,
        sweet_count,
        settings.weighted_peak_min_count,
    )
    sour_peak_percentage, sour_peak_count = _count(
        settings.weighted_peak_fraction,
        sour_count,
        settings.weighted_peak_min_count,
    )
    if workspace is None:
        sweet_peak = _top_mean_chunked(
            matrix,
            coefficients,
            sweet_columns,
            sweet_peak_count,
            chunk_size=chunk_size,
        )
        sour_peak = _top_mean_chunked(
            matrix,
            -coefficients,
            sour_columns,
            sour_peak_count,
            chunk_size=chunk_size,
        )
    else:
        sweet_peak = workspace._top_mean(
            coefficients,
            sweet_columns,
            sweet_peak_count,
        )
        sour_peak = workspace._top_mean(
            -coefficients,
            sour_columns,
            sour_peak_count,
        )
    net_score = sweet_peak - sour_peak
    support_status = _support_status(n_positive, n_negative, settings)
    if not retain_metadata:
        return FiberScoreState(
            net_score=net_score,
            n_positive_valid_fibers=n_positive,
            n_negative_valid_fibers=n_negative,
            fiber_score_support_status=support_status,
        )
    return FiberScoreResult(
        sweet_peak=sweet_peak,
        sour_peak=sour_peak,
        net_score=net_score,
        sweet_fiber_ids=sweet_ids,
        sour_fiber_ids=sour_ids,
        n_positive_valid_fibers=n_positive,
        n_negative_valid_fibers=n_negative,
        sweet_percentage_count=sweet_percentage,
        sour_percentage_count=sour_percentage,
        sweet_actual_selected_count=sweet_count,
        sour_actual_selected_count=sour_count,
        sweet_actual_peak_count=sweet_peak_count,
        sour_actual_peak_count=sour_peak_count,
        sweet_minimum_count_dominated=(
            n_positive > 0 and sweet_percentage < settings.sweet_selected_min_count
        ),
        sour_minimum_count_dominated=(
            n_negative > 0 and sour_percentage < settings.sour_selected_min_count
        ),
        sweet_peak_minimum_count_dominated=(
            sweet_count > 0 and sweet_peak_percentage < settings.weighted_peak_min_count
        ),
        sour_peak_minimum_count_dominated=(
            sour_count > 0 and sour_peak_percentage < settings.weighted_peak_min_count
        ),
        fiber_score_support_status=support_status,
        sweet_selected_fiber_id_hash=_ordered_id_hash(sweet_ids),
        sour_selected_fiber_id_hash=_ordered_id_hash(sour_ids),
    )


def score_signed_fibers(
    exposure: np.ndarray,
    weights: np.ndarray,
    fiber_ids: np.ndarray,
    settings: NormativeFiberScoreSettings,
    *,
    candidate_mask: np.ndarray | None = None,
    chunk_size: int = 8_192,
) -> FiberScoreResult:
    """Compute continuous-dose sweet-minus-sour scores on valid candidate fibers."""

    result = _score_signed_fibers(
        exposure,
        weights,
        fiber_ids,
        settings,
        candidate_mask=candidate_mask,
        chunk_size=chunk_size,
        validate_exposure=True,
    )
    if not isinstance(result, FiberScoreResult):
        raise AssertionError("public fiber scoring returned lightweight state")
    return result


def _score_signed_fibers_prevalidated(
    exposure: np.ndarray,
    weights: np.ndarray,
    fiber_ids: np.ndarray,
    settings: NormativeFiberScoreSettings,
    *,
    candidate_mask: np.ndarray,
    chunk_size: int,
) -> FiberScoreResult:
    """Score an exposure matrix already validated by the coverage pass."""

    result = _score_signed_fibers(
        exposure,
        weights,
        fiber_ids,
        settings,
        candidate_mask=candidate_mask,
        chunk_size=chunk_size,
        validate_exposure=False,
    )
    if not isinstance(result, FiberScoreResult):
        raise AssertionError("prevalidated fiber scoring returned lightweight state")
    return result


def score_support_fields(
    result: FiberScoreResult,
    settings: NormativeFiberScoreSettings,
) -> dict[str, object]:
    """Return the required full-sample or fold support fields."""

    if not isinstance(result, FiberScoreResult):
        raise FiberScoreError("result must be FiberScoreResult")
    return {
        "n_positive_valid_fibers": result.n_positive_valid_fibers,
        "n_negative_valid_fibers": result.n_negative_valid_fibers,
        "sweet_fraction_requested": settings.sweet_fraction,
        "sour_fraction_requested": settings.sour_fraction,
        "weighted_peak_fraction_requested": settings.weighted_peak_fraction,
        "sweet_selected_k_min": settings.sweet_selected_min_count,
        "sour_selected_k_min": settings.sour_selected_min_count,
        "weighted_peak_k_min": settings.weighted_peak_min_count,
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
