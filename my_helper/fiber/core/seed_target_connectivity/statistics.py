"""Exact descriptive seed-target connectivity statistics and ranking."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from .errors import StatisticsError
from .models import MembershipResult, ResolvedAtlas, TargetStatistic


def _rank(rows: list[TargetStatistic]) -> list[TargetStatistic]:
    rankable = [row for row in rows if row.target_status != "empty_after_threshold"]
    rankable.sort(
        key=lambda row: (
            0 if row.connectivity_lift is not None else 1,
            -row.connectivity_lift if row.connectivity_lift is not None else 0.0,
            -row.seed_normalized_fraction,
            -row.raw_fiber_count,
            row.target_id,
        )
    )
    ranks = {row.target_id: rank for rank, row in enumerate(rankable, start=1)}
    return [replace(row, rank=ranks.get(row.target_id)) for row in rows]


def compute_statistics(
    membership: MembershipResult,
    atlas: ResolvedAtlas,
    *,
    ranking_enabled: bool,
) -> tuple[TargetStatistic, ...]:
    """Compute the five exact target statistics and optional deterministic rank."""
    n_all = int(membership.n_all_fibers)
    n_seed = int(membership.seed_fiber_ids.size)
    if n_all <= 0:
        raise StatisticsError("connectome contains no valid fibers")
    if n_seed == 0:
        raise StatisticsError("seed membership is empty")
    target_ids = tuple(target.roi_id for target in atlas.targets)
    if membership.target_membership.target_ids != target_ids:
        raise StatisticsError("target membership order does not match resolved atlas")

    rows: list[TargetStatistic] = []
    for target_index, target in enumerate(atlas.targets):
        target_fiber_ids = membership.target_membership.ids_for(target_index)
        n_target = int(target_fiber_ids.size)
        n_joint = int(
            np.intersect1d(
                membership.seed_fiber_ids,
                target_fiber_ids,
                assume_unique=True,
            ).size
        )
        conditional = n_joint / n_seed
        prevalence = n_target / n_all
        if target.status == "empty_after_threshold":
            target_status = "empty_after_threshold"
            lift = None
            pmi = None
            pmi_status = "not_estimable_empty_target"
        elif n_target == 0:
            target_status = "no_connectome_support"
            lift = None
            pmi = None
            pmi_status = "not_estimable_no_target_support"
        else:
            target_status = "valid"
            lift = conditional / prevalence
            if lift == 0.0:
                pmi = None
                pmi_status = "negative_infinity"
            else:
                pmi = math.log2(lift)
                pmi_status = "estimable"
        rows.append(
            TargetStatistic(
                target_id=target.roi_id,
                target_group=target.target_group,
                relative_path=target.relative_path,
                source_value_type=target.source_value_type,
                probability_threshold=target.probability_threshold,
                threshold_source=target.threshold_source,
                target_status=target_status,
                n_all_fibers=n_all,
                n_seed_fibers=n_seed,
                n_target_fibers=n_target,
                n_seed_target_fibers=n_joint,
                raw_fiber_count=n_joint,
                seed_normalized_fraction=conditional,
                target_background_prevalence=prevalence,
                connectivity_lift=lift,
                connectivity_pmi=pmi,
                connectivity_pmi_status=pmi_status,
            )
        )
    if ranking_enabled:
        rows = _rank(rows)
    return tuple(rows)
