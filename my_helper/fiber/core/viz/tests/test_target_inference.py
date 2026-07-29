"""Patient-level target-inference numerical and resume tests."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from ..target_inference import (
    compute_target_null_block,
    generate_permutation_plan,
    holm_adjust,
    prepare_target_inference,
    run_target_inference,
    summarize_target_inference,
)


def _example() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    outcome = np.asarray([1, 3, 2, 6, 5, 4, 8, 9, 7], dtype=np.float64)
    nuisance = np.asarray([2, 1, 3, 4, 6, 5, 9, 7, 8], dtype=np.float64)
    design = np.column_stack([np.ones(outcome.size), nuisance])
    exposure = np.asarray(
        [
            [1, 2, 1, 9, 3, 4],
            [2, 2, 3, 8, 2, 4],
            [3, 1, 2, 7, 1, 4],
            [4, 3, 4, 6, 6, 4],
            [5, 4, 6, 5, 5, 4],
            [6, 5, 5, 4, 4, 4],
            [7, 7, 7, 3, 7, 4],
            [8, 6, 9, 2, 9, 4],
            [9, 8, 8, 1, 8, 4],
        ],
        dtype=np.float64,
    )
    membership = np.asarray(
        [
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 0, 0],
            [1, 0, 1, 0],
            [1, 1, 1, 0],
        ],
        dtype=bool,
    )
    return outcome, exposure, design, membership


def _residualize(design: np.ndarray, values: np.ndarray) -> np.ndarray:
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ coefficients


def test_kernel_matches_brute_force_with_ties_multitarget_and_empty_target() -> None:
    outcome, exposure, design, membership = _example()
    prepared = prepare_target_inference(
        ranked_outcome=outcome,
        ranked_exposure=exposure,
        ranked_nuisance_design=design,
        target_membership=membership,
        benefit_direction="lower",
    )
    plan = generate_permutation_plan(
        subject_count=outcome.size,
        replicate_count=37,
        seed=42,
        exchangeability_blocks=["all"] * outcome.size,
    )
    optimized = compute_target_null_block(prepared, design, plan)

    brute = np.full(optimized.shape, np.nan, dtype=np.float64)
    fitted = outcome - _residualize(design, outcome)
    residual = outcome - fitted
    exposure_residual = _residualize(design, exposure)
    exposure_norm = np.linalg.norm(exposure_residual, axis=0)
    valid = prepared.valid_fiber_mask
    exposure_unit = exposure_residual[:, valid] / exposure_norm[valid]
    valid_membership = membership[valid]
    for replicate, order in enumerate(plan):
        pseudo = fitted + residual[order]
        pseudo_residual = _residualize(design, pseudo)
        pseudo_unit = pseudo_residual / np.linalg.norm(pseudo_residual)
        weights = -(pseudo_unit @ exposure_unit)
        for target_index in range(membership.shape[1]):
            selected = valid_membership[:, target_index]
            if np.any(selected):
                brute[replicate, target_index] = np.mean(weights[selected])

    assert np.nanmax(np.abs(optimized - brute)) < 1e-12
    assert prepared.inferential_fiber_counts.tolist() == [3, 3, 1, 0]
    assert np.isnan(prepared.observed_target_statistics[-1])


def test_restricted_permutation_stays_within_blocks() -> None:
    plan = generate_permutation_plan(
        subject_count=6,
        replicate_count=20,
        seed=11,
        exchangeability_blocks=["a", "a", "a", "b", "b", "b"],
    )
    assert np.all(plan[:, :3] < 3)
    assert np.all(plan[:, 3:] >= 3)
    assert np.all(np.sort(plan, axis=1) == np.arange(6))


def test_holm_and_plus_one_results_preserve_empty_target() -> None:
    outcome, exposure, design, membership = _example()
    prepared = prepare_target_inference(
        ranked_outcome=outcome,
        ranked_exposure=exposure,
        ranked_nuisance_design=design,
        target_membership=membership,
        benefit_direction="higher",
    )
    plan = generate_permutation_plan(
        subject_count=outcome.size,
        replicate_count=99,
        seed=4,
        exchangeability_blocks=["all"] * outcome.size,
    )
    null = compute_target_null_block(prepared, design, plan)
    rows = summarize_target_inference(
        target_ids=("a", "b", "c", "empty"),
        prepared=prepared,
        null_statistics=null,
    )

    assert rows[-1]["g_observed"] is None
    assert rows[-1]["p_net_targetwise"] is None
    for row in rows[:-1]:
        assert float(row["p_net_targetwise"]) >= 0.01
        assert float(row["p_net_holm_fwer"]) >= float(row["p_net_targetwise"])
        assert float(row["p_net_max_t_single_step"]) >= float(
            row["p_net_targetwise"]
        )
    adjusted = holm_adjust(np.asarray([0.03, 0.01, np.nan, 0.04]))
    assert np.allclose(adjusted[[0, 1, 3]], [0.06, 0.03, 0.06])
    assert np.isnan(adjusted[2])


def test_blockwise_run_resumes_missing_block_deterministically(tmp_path: Path) -> None:
    outcome, exposure, design, membership = _example()
    kwargs = {
        "output_root": tmp_path / "inference",
        "target_ids": ("a", "b", "c", "empty"),
        "ranked_outcome": outcome,
        "ranked_exposure": exposure,
        "ranked_nuisance_design": design,
        "target_membership": membership,
        "benefit_direction": "lower",
        "exchangeability_blocks": ["all"] * outcome.size,
        "replicate_count": 501,
        "seed": 42,
        "input_identity": {"fiber_axis_sha256": "a" * 64},
    }
    first = run_target_inference(**kwargs)
    original_null = np.load(
        tmp_path / "inference" / "target_group_permutation_null.npy",
        allow_pickle=False,
    )
    blocks = sorted((tmp_path / "inference" / ".blocks").rglob("block_*.npy"))
    assert len(blocks) == 3
    blocks[-1].rename(blocks[-1].with_name(blocks[-1].name + ".held-out"))

    second = run_target_inference(**kwargs)
    resumed_null = np.load(
        tmp_path / "inference" / "target_group_permutation_null.npy",
        allow_pickle=False,
    )
    with (
        tmp_path / "inference" / "target_group_permutation_summary.csv"
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert first["computed_block_count"] == 3
    assert second["computed_block_count"] == 1
    assert second["reused_block_count"] == 2
    assert np.array_equal(original_null, resumed_null, equal_nan=True)
    assert rows[-1]["target_id"] == "empty"
    assert rows[-1]["p_net_holm_fwer"] == ""

    blocks = sorted((tmp_path / "inference" / ".blocks").rglob("block_*.npy"))
    corrupt_path = blocks[0]
    corrupt_path.rename(corrupt_path.with_name(corrupt_path.name + ".valid-backup"))
    with corrupt_path.open("wb") as handle:
        np.save(handle, np.zeros((1, 1), dtype=np.float64))
    third = run_target_inference(**kwargs)
    assert third["computed_block_count"] == 1
    assert third["quarantined_block_count"] == 1
    assert list(corrupt_path.parent.glob(corrupt_path.name + ".invalid-*"))

    changed_kwargs = {
        **kwargs,
        "input_identity": {"fiber_axis_sha256": "b" * 64},
    }
    changed = run_target_inference(**changed_kwargs)
    assert changed["computed_block_count"] == 3
    assert changed["reused_block_count"] == 0
    assert changed["request_sha256"] != first["request_sha256"]
