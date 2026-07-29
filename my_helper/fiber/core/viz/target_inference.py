"""Conditional patient-level inference for target-grouped normative fibers."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np


TARGET_INFERENCE_SCHEMA = "conditional_signed_target_inference_v1"
TARGET_INFERENCE_BLOCK_SIZE = 250


class TargetInferenceError(RuntimeError):
    """Raised when target inference inputs or checkpoints violate the contract."""


@dataclass(frozen=True)
class PreparedTargetInference:
    """Validated observed state and target kernels for permutation inference."""

    fitted_ranked_outcome: np.ndarray
    ranked_outcome_residual: np.ndarray
    fiber_unit_vectors: np.ndarray
    target_kernels: np.ndarray
    observed_fiber_weights: np.ndarray
    observed_target_statistics: np.ndarray
    valid_fiber_mask: np.ndarray
    inferential_fiber_counts: np.ndarray
    coverage_fiber_counts: np.ndarray
    benefit_multiplier: float


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _npy_bytes(values: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, np.asarray(values), allow_pickle=False)
    return stream.getvalue()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_npy(path: Path, values: np.ndarray) -> None:
    _atomic_bytes(path, _npy_bytes(values))


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: Iterable[Mapping[str, object]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=tuple(fields), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return stream.getvalue().encode("utf-8")


def _benefit_multiplier(direction: str) -> float:
    normalized = str(direction).strip().lower()
    if normalized == "lower":
        return -1.0
    if normalized == "higher":
        return 1.0
    raise TargetInferenceError("benefit direction must be 'lower' or 'higher'")


def _residualize_design(design: np.ndarray, values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(design, dtype=np.float64)
    array = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or array.ndim not in {1, 2}:
        raise TargetInferenceError("residualization inputs have invalid dimensions")
    one_dimensional = array.ndim == 1
    rhs = array[:, None] if one_dimensional else array
    if rhs.shape[0] != matrix.shape[0]:
        raise TargetInferenceError("residualization inputs do not share subjects")
    try:
        coefficients, *_ = np.linalg.lstsq(matrix, rhs, rcond=None)
    except np.linalg.LinAlgError as exc:
        raise TargetInferenceError("ranked nuisance residualization failed") from exc
    residual = rhs - matrix @ coefficients
    return residual[:, 0] if one_dimensional else residual


def prepare_target_inference(
    *,
    ranked_outcome: np.ndarray,
    ranked_exposure: np.ndarray,
    ranked_nuisance_design: np.ndarray,
    target_membership: np.ndarray,
    benefit_direction: str,
) -> PreparedTargetInference:
    """Build observed signed statistics and exact equal-weight target kernels."""

    outcome = np.asarray(ranked_outcome, dtype=np.float64)
    exposure = np.asarray(ranked_exposure, dtype=np.float64)
    design = np.asarray(ranked_nuisance_design, dtype=np.float64)
    membership = np.asarray(target_membership, dtype=np.bool_)
    if outcome.ndim != 1 or exposure.ndim != 2 or design.ndim != 2:
        raise TargetInferenceError("ranked inference arrays have invalid dimensions")
    if outcome.size != exposure.shape[0] or outcome.size != design.shape[0]:
        raise TargetInferenceError("ranked inference arrays do not share subjects")
    if membership.ndim != 2 or membership.shape[0] != exposure.shape[1]:
        raise TargetInferenceError("target membership does not match the fiber axis")
    if design.shape[1] < 1 or not np.allclose(design[:, 0], 1.0):
        raise TargetInferenceError("ranked nuisance design must include an intercept")
    if not (
        np.all(np.isfinite(outcome))
        and np.all(np.isfinite(exposure))
        and np.all(np.isfinite(design))
    ):
        raise TargetInferenceError("ranked inference arrays must be finite")
    design_rank = int(np.linalg.matrix_rank(design))
    if design_rank != design.shape[1] or outcome.size <= design_rank:
        raise TargetInferenceError("ranked nuisance design is not estimable")

    outcome_residual = _residualize_design(design, outcome)
    outcome_residual = outcome_residual - np.mean(outcome_residual)
    outcome_norm = float(np.linalg.norm(outcome_residual))
    if not np.isfinite(outcome_norm) or outcome_norm <= 0.0:
        raise TargetInferenceError("ranked outcome has zero nuisance-adjusted norm")
    outcome_unit = outcome_residual / outcome_norm
    exposure_residual = _residualize_design(design, exposure)
    exposure_residual = exposure_residual - np.mean(
        exposure_residual,
        axis=0,
        keepdims=True,
    )
    exposure_norms = np.linalg.norm(exposure_residual, axis=0)
    exposure_scales = np.maximum(1.0, np.linalg.norm(exposure, axis=0))
    zero_tolerance = (
        np.finfo(np.float64).eps
        * max(design.shape)
        * exposure_scales
    )
    valid_fibers = np.isfinite(exposure_norms) & (
        exposure_norms > zero_tolerance
    )
    fiber_units = np.zeros(exposure_residual.shape, dtype=np.float64)
    fiber_units[:, valid_fibers] = (
        exposure_residual[:, valid_fibers] / exposure_norms[valid_fibers]
    )

    multiplier = _benefit_multiplier(benefit_direction)
    observed_fiber_weights = np.full(exposure.shape[1], np.nan, dtype=np.float64)
    observed_fiber_weights[valid_fibers] = multiplier * (
        outcome_unit @ fiber_units[:, valid_fibers]
    )
    target_count = membership.shape[1]
    coverage_counts = np.sum(membership, axis=0, dtype=np.int64)
    inferential_membership = membership & valid_fibers[:, None]
    inferential_counts = np.sum(inferential_membership, axis=0, dtype=np.int64)
    kernels = np.full((outcome.size, target_count), np.nan, dtype=np.float64)
    observed_targets = np.full(target_count, np.nan, dtype=np.float64)
    for target_index in range(target_count):
        selected = inferential_membership[:, target_index]
        if not np.any(selected):
            continue
        kernels[:, target_index] = np.mean(fiber_units[:, selected], axis=1)
        observed_targets[target_index] = float(
            np.mean(observed_fiber_weights[selected])
        )

    fitted = outcome - outcome_residual
    return PreparedTargetInference(
        fitted_ranked_outcome=np.asarray(fitted, dtype=np.float64),
        ranked_outcome_residual=np.asarray(outcome_residual, dtype=np.float64),
        fiber_unit_vectors=fiber_units,
        target_kernels=kernels,
        observed_fiber_weights=observed_fiber_weights,
        observed_target_statistics=observed_targets,
        valid_fiber_mask=valid_fibers,
        inferential_fiber_counts=inferential_counts,
        coverage_fiber_counts=coverage_counts,
        benefit_multiplier=multiplier,
    )


def generate_permutation_plan(
    *,
    subject_count: int,
    replicate_count: int,
    seed: int,
    exchangeability_blocks: Sequence[str] | np.ndarray,
) -> np.ndarray:
    """Generate deterministic independent draws within exchangeability blocks."""

    if type(subject_count) is not int or subject_count < 2:
        raise TargetInferenceError("subject_count must be at least two")
    if type(replicate_count) is not int or replicate_count < 1:
        raise TargetInferenceError("replicate_count must be positive")
    if type(seed) is not int:
        raise TargetInferenceError("seed must be an integer")
    blocks = np.asarray(tuple(str(value) for value in exchangeability_blocks))
    if blocks.shape != (subject_count,) or np.any(blocks == ""):
        raise TargetInferenceError("exchangeability blocks must match subjects")
    block_indices = tuple(
        np.flatnonzero(blocks == label)
        for label in dict.fromkeys(blocks.tolist())
    )
    if not block_indices:
        raise TargetInferenceError("exchangeability plan has no blocks")

    generator = np.random.default_rng(seed)
    plan = np.empty((replicate_count, subject_count), dtype=np.int32)
    identity = np.arange(subject_count, dtype=np.int32)
    for replicate in range(replicate_count):
        row = identity.copy()
        for indices in block_indices:
            row[indices] = generator.permutation(indices).astype(np.int32, copy=False)
        plan[replicate] = row
    return plan


def compute_target_null_block(
    prepared: PreparedTargetInference,
    ranked_nuisance_design: np.ndarray,
    permutation_block: np.ndarray,
) -> np.ndarray:
    """Compute one block of signed target statistics from fixed permutations."""

    if not isinstance(prepared, PreparedTargetInference):
        raise TypeError("prepared must be a PreparedTargetInference")
    design = np.asarray(ranked_nuisance_design, dtype=np.float64)
    plan = np.asarray(permutation_block, dtype=np.int64)
    subject_count = prepared.ranked_outcome_residual.size
    if plan.ndim != 2 or plan.shape[1] != subject_count:
        raise TargetInferenceError("permutation block does not match subjects")
    expected = np.arange(subject_count)
    if any(not np.array_equal(np.sort(row), expected) for row in plan):
        raise TargetInferenceError("permutation block contains an invalid row")

    pseudo_outcomes = (
        prepared.fitted_ranked_outcome[:, None]
        + prepared.ranked_outcome_residual[plan].T
    )
    pseudo_residuals = _residualize_design(design, pseudo_outcomes)
    pseudo_residuals = pseudo_residuals - np.mean(
        pseudo_residuals,
        axis=0,
        keepdims=True,
    )
    norms = np.linalg.norm(pseudo_residuals, axis=0)
    if np.any(~np.isfinite(norms)) or np.any(norms <= 0.0):
        raise TargetInferenceError(
            "permutation produced a nonfinite or zero-norm outcome residual"
        )
    pseudo_units = pseudo_residuals / norms[None, :]
    return prepared.benefit_multiplier * (
        pseudo_units.T @ prepared.target_kernels
    )


def holm_adjust(p_values: np.ndarray) -> np.ndarray:
    """Return Holm strong-FWER adjusted p values while preserving NaNs."""

    values = np.asarray(p_values, dtype=np.float64)
    output = np.full(values.shape, np.nan, dtype=np.float64)
    finite_indices = np.flatnonzero(np.isfinite(values))
    if finite_indices.size == 0:
        return output
    order = finite_indices[np.argsort(values[finite_indices], kind="stable")]
    adjusted = np.empty(order.size, dtype=np.float64)
    running = 0.0
    count = order.size
    for rank, index in enumerate(order):
        candidate = min(1.0, float(values[index]) * (count - rank))
        running = max(running, candidate)
        adjusted[rank] = running
    output[order] = adjusted
    return output


def summarize_target_inference(
    *,
    target_ids: Sequence[str],
    prepared: PreparedTargetInference,
    null_statistics: np.ndarray,
) -> list[dict[str, object]]:
    """Compute plus-one targetwise, Holm, and complete-null maxT results."""

    targets = tuple(str(value) for value in target_ids)
    null = np.asarray(null_statistics, dtype=np.float64)
    observed = prepared.observed_target_statistics
    if null.ndim != 2 or null.shape[1] != observed.size:
        raise TargetInferenceError("null statistics do not match target statistics")
    if len(targets) != observed.size or len(set(targets)) != len(targets):
        raise TargetInferenceError("target IDs do not match the target axis")
    testable = np.isfinite(observed)
    if np.any(~np.all(np.isfinite(null[:, testable]), axis=0)):
        raise TargetInferenceError("testable target null statistics are nonfinite")
    replicate_count = null.shape[0]
    targetwise = np.full(observed.shape, np.nan, dtype=np.float64)
    for index in np.flatnonzero(testable):
        exceedances = int(
            np.count_nonzero(np.abs(null[:, index]) >= abs(observed[index]))
        )
        targetwise[index] = (exceedances + 1.0) / (replicate_count + 1.0)
    holm = holm_adjust(targetwise)
    max_t = np.full(observed.shape, np.nan, dtype=np.float64)
    if np.any(testable):
        complete_null_max = np.max(np.abs(null[:, testable]), axis=1)
        for index in np.flatnonzero(testable):
            exceedances = int(
                np.count_nonzero(complete_null_max >= abs(observed[index]))
            )
            max_t[index] = (exceedances + 1.0) / (replicate_count + 1.0)

    rows: list[dict[str, object]] = []
    for index, target_id in enumerate(targets):
        finite = bool(testable[index])
        values = null[:, index] if finite else np.asarray([], dtype=np.float64)
        rows.append(
            {
                "target_id": target_id,
                "coverage_fiber_count": int(prepared.coverage_fiber_counts[index]),
                "inferential_fiber_count": int(
                    prepared.inferential_fiber_counts[index]
                ),
                "excluded_nonfinite_count": 0,
                "excluded_zero_variance_count": int(
                    prepared.coverage_fiber_counts[index]
                    - prepared.inferential_fiber_counts[index]
                ),
                "g_observed": float(observed[index]) if finite else None,
                "p_net_targetwise": float(targetwise[index]) if finite else None,
                "p_net_holm_fwer": float(holm[index]) if finite else None,
                "p_net_max_t_single_step": float(max_t[index]) if finite else None,
                "null_mean_g": float(np.mean(values)) if finite else None,
                "null_sd_g": float(np.std(values, ddof=0)) if finite else None,
                "null_q025_g": float(np.quantile(values, 0.025)) if finite else None,
                "null_q975_g": float(np.quantile(values, 0.975)) if finite else None,
                "max_t_reference_null": "complete_null" if finite else None,
            }
        )
    return rows


def run_target_inference(
    *,
    output_root: Path,
    target_ids: Sequence[str],
    ranked_outcome: np.ndarray,
    ranked_exposure: np.ndarray,
    ranked_nuisance_design: np.ndarray,
    target_membership: np.ndarray,
    benefit_direction: str,
    exchangeability_blocks: Sequence[str] | np.ndarray,
    replicate_count: int,
    seed: int,
    input_identity: Mapping[str, object],
    expected_fiber_weights: np.ndarray | None = None,
    expected_target_statistics: np.ndarray | None = None,
    observed_parity_tolerance: float = 5e-7,
) -> dict[str, object]:
    """Run or resume deterministic blockwise target inference and publish outputs."""

    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    prepared = prepare_target_inference(
        ranked_outcome=ranked_outcome,
        ranked_exposure=ranked_exposure,
        ranked_nuisance_design=ranked_nuisance_design,
        target_membership=target_membership,
        benefit_direction=benefit_direction,
    )
    parity: dict[str, object] = {
        "tolerance": float(observed_parity_tolerance),
        "fiber_weights_checked": expected_fiber_weights is not None,
        "target_statistics_checked": expected_target_statistics is not None,
    }
    if expected_fiber_weights is not None:
        expected_weights = np.asarray(expected_fiber_weights, dtype=np.float64)
        observed_weights = prepared.observed_fiber_weights
        if expected_weights.shape != observed_weights.shape:
            raise TargetInferenceError(
                "expected fiber weights do not match the inference fiber axis"
            )
        if not np.array_equal(
            np.isfinite(expected_weights), np.isfinite(observed_weights)
        ):
            raise TargetInferenceError(
                "target inference changes observed fiber-weight finite support"
            )
        fiber_difference = np.abs(expected_weights - observed_weights)
        finite_fiber_difference = fiber_difference[np.isfinite(fiber_difference)]
        parity["fiber_weight_max_abs_difference"] = (
            float(np.max(finite_fiber_difference))
            if finite_fiber_difference.size
            else 0.0
        )
        if not np.allclose(
            expected_weights,
            observed_weights,
            rtol=0.0,
            atol=observed_parity_tolerance,
            equal_nan=True,
        ):
            raise TargetInferenceError(
                "target inference does not reproduce published fiber weights"
            )
    if expected_target_statistics is not None:
        expected_targets = np.asarray(expected_target_statistics, dtype=np.float64)
        observed_targets = prepared.observed_target_statistics
        if expected_targets.shape != observed_targets.shape:
            raise TargetInferenceError(
                "expected target statistics do not match the target axis"
            )
        if not np.array_equal(
            np.isfinite(expected_targets), np.isfinite(observed_targets)
        ):
            raise TargetInferenceError(
                "target inference changes observed target finite support"
            )
        target_difference = np.abs(expected_targets - observed_targets)
        finite_target_difference = target_difference[np.isfinite(target_difference)]
        parity["target_statistic_max_abs_difference"] = (
            float(np.max(finite_target_difference))
            if finite_target_difference.size
            else 0.0
        )
        if not np.allclose(
            expected_targets,
            observed_targets,
            rtol=0.0,
            atol=observed_parity_tolerance,
            equal_nan=True,
        ):
            raise TargetInferenceError(
                "target inference does not reproduce all-coverage target scores"
            )
    plan = generate_permutation_plan(
        subject_count=np.asarray(ranked_outcome).size,
        replicate_count=replicate_count,
        seed=seed,
        exchangeability_blocks=exchangeability_blocks,
    )
    plan_payload = _npy_bytes(plan)
    plan_sha256 = _sha256_bytes(plan_payload)
    plan_path = root / "permutation_plan.npy"
    if plan_path.is_file() and _sha256_file(plan_path) != plan_sha256:
        raise TargetInferenceError("existing permutation plan does not match the request")
    if not plan_path.is_file():
        _atomic_bytes(plan_path, plan_payload)

    request_payload = {
        "schema_version": TARGET_INFERENCE_SCHEMA,
        "target_ids": [str(value) for value in target_ids],
        "benefit_direction": str(benefit_direction),
        "replicate_count": replicate_count,
        "seed": seed,
        "permutation_plan_sha256": plan_sha256,
        "input_identity": dict(input_identity),
    }
    request_sha256 = _sha256_bytes(
        json.dumps(
            request_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    blocks_root = root / ".blocks" / request_sha256
    blocks_root.mkdir(parents=True, exist_ok=True)

    block_paths: list[Path] = []
    reused_blocks = 0
    computed_blocks = 0
    quarantined_blocks = 0
    testable_targets = np.isfinite(prepared.observed_target_statistics)
    for block_index, start in enumerate(
        range(0, replicate_count, TARGET_INFERENCE_BLOCK_SIZE)
    ):
        stop = min(start + TARGET_INFERENCE_BLOCK_SIZE, replicate_count)
        path = blocks_root / f"block_{block_index:04d}_{start:06d}_{stop:06d}.npy"
        expected_shape = (stop - start, len(tuple(target_ids)))
        if path.is_file():
            try:
                existing = np.load(path, allow_pickle=False)
                reusable = bool(
                    existing.shape == expected_shape
                    and np.all(np.isfinite(existing[:, testable_targets]))
                    and np.all(np.isnan(existing[:, ~testable_targets]))
                )
            except (OSError, ValueError):
                reusable = False
            if reusable:
                reused_blocks += 1
            else:
                digest = _sha256_file(path)[:12]
                quarantine = path.with_name(f"{path.name}.invalid-{digest}")
                suffix = 1
                while quarantine.exists():
                    quarantine = path.with_name(
                        f"{path.name}.invalid-{digest}-{suffix:02d}"
                    )
                    suffix += 1
                os.replace(path, quarantine)
                quarantined_blocks += 1
        if not path.is_file():
            values = compute_target_null_block(
                prepared,
                ranked_nuisance_design,
                plan[start:stop],
            )
            if values.shape != expected_shape:
                raise TargetInferenceError("computed target-inference block has wrong shape")
            _atomic_npy(path, values)
            computed_blocks += 1
        block_paths.append(path)

    null = np.concatenate(
        [np.asarray(np.load(path, allow_pickle=False), dtype=np.float64) for path in block_paths],
        axis=0,
    )
    if null.shape != (replicate_count, len(tuple(target_ids))):
        raise TargetInferenceError("target-inference blocks do not cover the request")
    rows = summarize_target_inference(
        target_ids=target_ids,
        prepared=prepared,
        null_statistics=null,
    )
    fields = tuple(rows[0]) if rows else (
        "target_id",
        "coverage_fiber_count",
        "inferential_fiber_count",
        "g_observed",
    )
    observed_fields = (
        "target_id",
        "coverage_fiber_count",
        "inferential_fiber_count",
        "excluded_nonfinite_count",
        "excluded_zero_variance_count",
        "g_observed",
    )
    _atomic_npy(root / "target_group_permutation_null.npy", null)
    _atomic_bytes(
        root / "target_group_observed.csv",
        _csv_bytes(rows, observed_fields),
    )
    _atomic_bytes(
        root / "target_group_permutation_summary.csv",
        _csv_bytes(rows, fields),
    )

    identity_rows = int(
        np.count_nonzero(np.all(plan == np.arange(plan.shape[1]), axis=1))
    )
    unique_replicates = len({row.tobytes() for row in plan})
    manifest: dict[str, object] = {
        "schema_version": TARGET_INFERENCE_SCHEMA,
        "status": "complete",
        "selection_scope": "conditional_on_published_final_model",
        "statistic": "signed_mean_benefit_partial_spearman",
        "permutation_method": "freedman_lane_in_rank_transformed_model_space",
        "pseudo_outcome_reranked": False,
        "requested_replicates": replicate_count,
        "completed_replicates": int(null.shape[0]),
        "unique_replicates": unique_replicates,
        "seed": seed,
        "permutation_sampling": "independent_draws_with_replacement",
        "identity_explicitly_included": False,
        "identity_draw_count": identity_rows,
        "generator_class": "numpy.random.Generator.permutation",
        "bit_generator_class": "PCG64",
        "permutation_plan_sha256": plan_sha256,
        "request_sha256": request_sha256,
        "block_size_internal": TARGET_INFERENCE_BLOCK_SIZE,
        "block_count": len(block_paths),
        "computed_block_count": computed_blocks,
        "reused_block_count": reused_blocks,
        "quarantined_block_count": quarantined_blocks,
        "block_directory": f".blocks/{request_sha256}",
        "target_count": len(tuple(target_ids)),
        "testable_target_count": int(
            np.count_nonzero(np.isfinite(prepared.observed_target_statistics))
        ),
        "multiplicity_primary": "holm_strong_fwer",
        "max_t_reference_null": "complete_null",
        "observed_parity": parity,
        "input_identity": dict(input_identity),
        "outputs": {
            "observed": "target_group_observed.csv",
            "permutation_null": "target_group_permutation_null.npy",
            "permutation_summary": "target_group_permutation_summary.csv",
            "permutation_plan": "permutation_plan.npy",
        },
    }
    _atomic_bytes(root / "target_group_permutation_manifest.json", _json_bytes(manifest))
    return manifest


__all__ = [
    "PreparedTargetInference",
    "TARGET_INFERENCE_BLOCK_SIZE",
    "TARGET_INFERENCE_SCHEMA",
    "TargetInferenceError",
    "compute_target_null_block",
    "generate_permutation_plan",
    "holm_adjust",
    "prepare_target_inference",
    "run_target_inference",
    "summarize_target_inference",
]
