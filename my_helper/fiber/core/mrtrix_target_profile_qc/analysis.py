"""Deterministic robust statistics for target-profile quality control."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.decomposition import PCA

from .config import PRESET
from .errors import ValidationError
from .models import QcValidation


@dataclass(frozen=True)
class AnalysisResult:
    """All tabular and matrix results for one QC run."""

    profiles: pd.DataFrame
    roi_qc: pd.DataFrame
    technical_qc: pd.DataFrame
    subject_metrics: pd.DataFrame
    robust_zscores: pd.DataFrame
    laterality: pd.DataFrame
    flags: pd.DataFrame
    recommendations: pd.DataFrame
    subject_similarity: dict[str, pd.DataFrame]
    target_similarity: dict[str, pd.DataFrame]
    pca_scores: pd.DataFrame


def _scaled_mad(values: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.nan, np.nan
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    scale = PRESET["robust_scaling"]["mad_scale_constant"] * mad
    if scale < PRESET["robust_scaling"]["minimum_mad"]:
        scale = np.nan
    return median, scale


def _robust_z(values: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
    base = values if reference is None else reference
    median, scale = _scaled_mad(np.asarray(base, dtype=float))
    if not np.isfinite(scale):
        return np.zeros_like(np.asarray(values, dtype=float))
    return (np.asarray(values, dtype=float) - median) / scale


def _safe_spearman(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or np.all(left == left[0]) or np.all(right == right[0]):
        return np.nan
    return float(spearmanr(left, right).statistic)


def _safe_pearson(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or np.allclose(left, left[0]) or np.allclose(right, right[0]):
        return np.nan
    return float(pearsonr(left, right).statistic)


def _safe_cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0:
        return np.nan
    return float(np.dot(left, right) / denominator)


def _pairwise_similarity(matrix: pd.DataFrame, method: str) -> pd.DataFrame:
    subjects = list(matrix.index)
    output = np.eye(len(subjects), dtype=float)
    function = {
        "spearman": _safe_spearman,
        "pearson": _safe_pearson,
        "cosine": _safe_cosine,
    }[method]
    values = matrix.to_numpy(dtype=float)
    for left in range(len(subjects)):
        for right in range(left + 1, len(subjects)):
            value = function(values[left], values[right])
            output[left, right] = value
            output[right, left] = value
    return pd.DataFrame(output, index=subjects, columns=subjects)


def _roi_geometry(path: Path) -> dict[str, float | int]:
    image = nib.load(path)
    mask = np.asanyarray(image.dataobj) > 0
    indices = np.argwhere(mask)
    count = int(indices.shape[0])
    voxel_volume = float(abs(np.linalg.det(np.asarray(image.affine)[:3, :3])))
    centroid_voxel = np.mean(indices, axis=0)
    centroid_world = nib.affines.apply_affine(image.affine, centroid_voxel)
    return {
        "voxel_count": count,
        "volume_mm3": count * voxel_volume,
        "centroid_x_mm": float(centroid_world[0]),
        "centroid_y_mm": float(centroid_world[1]),
        "centroid_z_mm": float(centroid_world[2]),
    }


def _extract_tables(validation: QcValidation) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile_rows: list[dict[str, Any]] = []
    roi_rows: list[dict[str, Any]] = []
    technical_rows: list[dict[str, Any]] = []
    expected_total = validation.tracking.config.tracking.seedwide_streamlines
    required_target = validation.tracking.config.tracking.minimum_streamlines_per_target

    for record in validation.records:
        seed_record = record.preparation["rois"]["seeds"][record.seed.key]
        state = record.state
        total = int(state["total_streamlines"])
        counts = [int(value) for value in state["target_hit_counts"]]
        reasons: list[str] = []
        if state["status"] == "coverage_failed":
            reasons.append("coverage_failed")
        if expected_total is not None and total != expected_total:
            reasons.append(f"seedwide_total:{total}!={expected_total}")
        zero_targets = [
            target.key for target, count in zip(record.seed.targets, counts, strict=True)
            if count == 0
        ]
        if zero_targets:
            reasons.append("zero_target_hits:" + "|".join(zero_targets))
        deficient = [
            target.key for target, count in zip(record.seed.targets, counts, strict=True)
            if count < required_target
        ]
        if deficient:
            reasons.append("below_required_target_hits:" + "|".join(deficient))

        technical_rows.append(
            {
                "subject_id": record.subject_id,
                "seed_key": record.seed.key,
                "seed_side": record.seed.side,
                "seed_state_status": state["status"],
                "total_streamlines": total,
                "minimum_target_streamlines": int(min(counts)),
                "hard_failure": bool(reasons),
                "hard_failure_reasons": ";".join(reasons),
                "preparation_identity": record.preparation_identity,
                "seedwide_identity": record.seedwide_identity,
                "state_path": str(record.state_path),
            }
        )

        seed_geometry = _roi_geometry(Path(seed_record["path"]))
        roi_rows.append(
            {
                "subject_id": record.subject_id,
                "seed_key": record.seed.key,
                "seed_side": record.seed.side,
                "roi_type": "seed",
                "roi_id": record.seed.roi_id,
                "roi_key": record.seed.key,
                "path": seed_record["path"],
                **seed_geometry,
            }
        )

        targets = seed_record["targets"]
        for target, target_record, count in zip(
            record.seed.targets, targets, counts, strict=True
        ):
            if target_record["key"] != target.key:
                raise ValidationError(
                    f"prepared target order mismatch for {record.subject_id} {target.key}"
                )
            geometry = _roi_geometry(Path(target_record["path"]))
            roi_rows.append(
                {
                    "subject_id": record.subject_id,
                    "seed_key": record.seed.key,
                    "seed_side": record.seed.side,
                    "roi_type": "target",
                    "roi_id": target.roi_id,
                    "roi_key": target.key,
                    "path": target_record["path"],
                    **geometry,
                }
            )
            fraction = float(count / total) if total else np.nan
            pseudocount = PRESET["profile"]["pseudocount"]
            adjusted = (count + pseudocount) / (total + 2 * pseudocount)
            transformed = float(np.log(adjusted / (1.0 - adjusted)))
            profile_rows.append(
                {
                    "subject_id": record.subject_id,
                    "seed_key": record.seed.key,
                    "seed_id": record.seed.roi_id,
                    "seed_side": record.seed.side,
                    "target_key": target.key,
                    "target_id": target.roi_id,
                    "target_side": target.side,
                    "feature_key": f"{record.seed.roi_id}/{target.roi_id}",
                    "total_streamlines": total,
                    "target_streamlines": count,
                    "hit_fraction": fraction,
                    "empirical_logit": transformed,
                    "seed_state_status": state["status"],
                    "hard_failure": bool(reasons),
                    "preparation_identity": record.preparation_identity,
                    "seedwide_identity": record.seedwide_identity,
                    "target_roi_voxel_count": geometry["voxel_count"],
                    "target_roi_volume_mm3": geometry["volume_mm3"],
                }
            )
    return (
        pd.DataFrame(profile_rows),
        pd.DataFrame(roi_rows),
        pd.DataFrame(technical_rows),
    )


def _add_roi_outliers(roi_qc: pd.DataFrame) -> pd.DataFrame:
    output = roi_qc.copy()
    output["volume_robust_z"] = 0.0
    output["centroid_distance_mm"] = 0.0
    output["centroid_distance_robust_z"] = 0.0
    grouping = ["seed_side", "roi_type", "roi_id"]
    for _, indices in output.groupby(grouping, sort=False).groups.items():
        index = list(indices)
        volumes = output.loc[index, "volume_mm3"].to_numpy(dtype=float)
        output.loc[index, "volume_robust_z"] = _robust_z(volumes)
        coordinates = output.loc[
            index, ["centroid_x_mm", "centroid_y_mm", "centroid_z_mm"]
        ].to_numpy(dtype=float)
        center = np.median(coordinates, axis=0)
        distances = np.linalg.norm(coordinates - center, axis=1)
        output.loc[index, "centroid_distance_mm"] = distances
        output.loc[index, "centroid_distance_robust_z"] = _robust_z(distances)
    threshold = PRESET["outliers"]["roi_mad_multiplier"]
    output["roi_outlier"] = (
        output["volume_robust_z"].abs().gt(threshold)
        | output["centroid_distance_robust_z"].gt(threshold)
    )
    return output


def _profile_matrix(profiles: pd.DataFrame, side: str) -> pd.DataFrame:
    subset = profiles.loc[profiles["seed_side"] == side].copy()
    matrix = subset.pivot(
        index="subject_id", columns="feature_key", values="empirical_logit"
    )
    return matrix.sort_index(axis=0).sort_index(axis=1)


def _analyze_matrix(
    matrix: pd.DataFrame,
    eligible_subjects: set[str],
    group: str,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    if matrix.shape[0] < 4 or matrix.shape[1] < 2:
        raise ValidationError(f"analysis group {group} has insufficient profiles")
    eligible = [subject for subject in matrix.index if subject in eligible_subjects]
    if len(eligible) < 3:
        raise ValidationError(f"analysis group {group} has fewer than three valid subjects")

    similarities = {
        method: _pairwise_similarity(matrix, method)
        for method in PRESET["similarity"]["metrics"]
    }
    metrics: list[dict[str, Any]] = []
    for subject in matrix.index:
        reference_subjects = [item for item in eligible if item != subject]
        reference = np.median(
            matrix.loc[reference_subjects].to_numpy(dtype=float), axis=0
        )
        values = matrix.loc[subject].to_numpy(dtype=float)
        metrics.append(
            {
                "subject_id": subject,
                "analysis_group": group,
                "spearman_to_reference": _safe_spearman(values, reference),
                "pearson_to_reference": _safe_pearson(values, reference),
                "cosine_to_reference": _safe_cosine(values, reference),
            }
        )

    reference_values = matrix.loc[eligible].to_numpy(dtype=float)
    medians = np.median(reference_values, axis=0)
    scales = np.median(np.abs(reference_values - medians), axis=0)
    scales *= PRESET["robust_scaling"]["mad_scale_constant"]
    scales[scales < PRESET["robust_scaling"]["minimum_mad"]] = 1.0
    standardized = (matrix.to_numpy(dtype=float) - medians) / scales
    reference_standardized = standardized[[matrix.index.get_loc(item) for item in eligible]]
    max_components = min(
        PRESET["multivariate_distance"]["maximum_components"],
        len(eligible) - 1,
        matrix.shape[1],
    )
    pca = PCA(n_components=max_components, whiten=True, svd_solver="full")
    pca.fit(reference_standardized)
    cumulative = np.cumsum(pca.explained_variance_ratio_)
    target = PRESET["multivariate_distance"]["variance_explained_threshold"]
    components = min(int(np.searchsorted(cumulative, target) + 1), max_components)
    scores = pca.transform(standardized)[:, :components]
    reference_scores = scores[[matrix.index.get_loc(item) for item in eligible]]
    score_center = np.median(reference_scores, axis=0)
    distances = np.linalg.norm(scores - score_center, axis=1)
    for row, distance in zip(metrics, distances, strict=True):
        row["pca_distance"] = float(distance)
        row["pca_components"] = components
        row["reference_eligible"] = row["subject_id"] in eligible_subjects
    score_columns = {f"pc{index + 1}": scores[:, index] for index in range(components)}
    pca_scores = pd.DataFrame(
        {"subject_id": matrix.index, "analysis_group": group, **score_columns}
    )

    z_values = (matrix.to_numpy(dtype=float) - medians) / scales
    zscores = matrix.copy()
    zscores.iloc[:, :] = z_values
    zscores.index.name = "subject_id"
    return pd.DataFrame(metrics), similarities, zscores, pca_scores


def _laterality_table(profiles: pd.DataFrame, eligible: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivot = profiles.pivot_table(
        index=["subject_id", "seed_id", "target_id"],
        columns="seed_side",
        values="hit_fraction",
        aggfunc="first",
    )
    if not {"lh", "rh"}.issubset(pivot.columns):
        return pd.DataFrame(), pd.DataFrame()
    pivot = pivot.dropna(subset=["lh", "rh"]).reset_index()
    epsilon = PRESET["laterality"]["epsilon"]
    pivot["asymmetry_index"] = (
        (pivot["lh"] - pivot["rh"]) / (pivot["lh"] + pivot["rh"] + epsilon)
    )
    pivot["feature_key"] = pivot["seed_id"] + "/" + pivot["target_id"]
    pivot["robust_z"] = 0.0
    for _, indices in pivot.groupby("feature_key", sort=False).groups.items():
        index = list(indices)
        reference = pivot.loc[
            pivot.index.isin(index) & pivot["subject_id"].isin(eligible),
            "asymmetry_index",
        ].to_numpy(dtype=float)
        pivot.loc[index, "robust_z"] = _robust_z(
            pivot.loc[index, "asymmetry_index"].to_numpy(dtype=float), reference
        )
    distances = (
        pivot.groupby("subject_id")["robust_z"]
        .apply(lambda values: float(np.sqrt(np.mean(np.square(values)))))
        .rename("laterality_distance")
        .reset_index()
    )
    return pivot, distances


def analyze(validation: QcValidation) -> AnalysisResult:
    """Run the complete preset analysis for one validated input bundle."""

    profiles, roi_qc, technical = _extract_tables(validation)
    roi_qc = _add_roi_outliers(roi_qc)
    hard_by_subject = (
        technical.groupby("subject_id")["hard_failure"].any().to_dict()
    )
    eligible_all = {
        subject for subject in profiles["subject_id"].unique()
        if not hard_by_subject.get(subject, False)
    }

    subject_metrics_parts: list[pd.DataFrame] = []
    pca_parts: list[pd.DataFrame] = []
    robust_parts: list[pd.DataFrame] = []
    subject_similarity: dict[str, pd.DataFrame] = {}
    target_similarity: dict[str, pd.DataFrame] = {}
    matrices: dict[str, pd.DataFrame] = {}
    for side in sorted(profiles["seed_side"].unique()):
        matrix = _profile_matrix(profiles, side)
        side_failures = set(
            technical.loc[
                (technical["seed_side"] == side) & technical["hard_failure"],
                "subject_id",
            ]
        )
        eligible = set(matrix.index) - side_failures
        metrics, similarities, zscores, pca_scores = _analyze_matrix(
            matrix, eligible, side
        )
        matrices[side] = matrix
        subject_metrics_parts.append(metrics)
        pca_parts.append(pca_scores)
        subject_similarity[side] = similarities["spearman"]
        target_similarity[side] = matrix.loc[sorted(eligible)].corr(
            method="spearman"
        )
        long_z = zscores.reset_index().melt(
            id_vars="subject_id", var_name="feature_key", value_name="robust_z"
        )
        long_z["analysis_group"] = side
        robust_parts.append(long_z)

    combined = pd.concat(
        [matrix.add_prefix(f"{side}|") for side, matrix in sorted(matrices.items())],
        axis=1,
        join="inner",
    )
    combined_metrics, combined_similarities, combined_z, combined_pca = _analyze_matrix(
        combined, eligible_all, "combined"
    )
    subject_metrics_parts.append(combined_metrics)
    pca_parts.append(combined_pca)
    subject_similarity["combined"] = combined_similarities["spearman"]
    combined_long_z = combined_z.reset_index().melt(
        id_vars="subject_id", var_name="feature_key", value_name="robust_z"
    )
    combined_long_z["analysis_group"] = "combined"
    robust_parts.append(combined_long_z)

    subject_metrics = pd.concat(subject_metrics_parts, ignore_index=True)
    pca_scores = pd.concat(pca_parts, ignore_index=True)
    robust_zscores = pd.concat(robust_parts, ignore_index=True)
    laterality, laterality_distance = _laterality_table(profiles, eligible_all)
    subject_metrics = subject_metrics.merge(
        laterality_distance, on="subject_id", how="left"
    )

    combined_rows = subject_metrics[subject_metrics["analysis_group"] == "combined"].copy()
    eligible_rows = combined_rows[combined_rows["subject_id"].isin(eligible_all)]
    corr_median, corr_scale = _scaled_mad(
        eligible_rows["spearman_to_reference"].to_numpy(dtype=float)
    )
    distance_median, distance_scale = _scaled_mad(
        eligible_rows["pca_distance"].to_numpy(dtype=float)
    )
    laterality_median, laterality_scale = _scaled_mad(
        eligible_rows["laterality_distance"].to_numpy(dtype=float)
    )
    multiplier = PRESET["outliers"]["mad_multiplier"]
    corr_threshold = (
        corr_median - multiplier * corr_scale if np.isfinite(corr_scale) else -np.inf
    )
    distance_threshold = (
        distance_median + multiplier * distance_scale
        if np.isfinite(distance_scale)
        else np.inf
    )
    laterality_threshold = (
        laterality_median + multiplier * laterality_scale
        if np.isfinite(laterality_scale)
        else np.inf
    )

    combined_subject_z = robust_zscores[
        robust_zscores["analysis_group"] == "combined"
    ]
    z_summary = combined_subject_z.groupby("subject_id")["robust_z"].agg(
        maximum_absolute_robust_z=lambda values: float(np.max(np.abs(values))),
        extreme_target_count=lambda values: int(
            np.sum(np.abs(values) > PRESET["outliers"]["target_robust_z_threshold"])
        ),
    ).reset_index()
    roi_summary = roi_qc.groupby("subject_id")["roi_outlier"].any().rename(
        "roi_outlier_review"
    ).reset_index()
    flags = combined_rows.merge(z_summary, on="subject_id", how="left").merge(
        roi_summary, on="subject_id", how="left"
    )
    flags["technical_failure"] = flags["subject_id"].map(hard_by_subject).fillna(False)
    flags["low_similarity"] = flags["spearman_to_reference"] < corr_threshold
    flags["high_multivariate_distance"] = flags["pca_distance"] > distance_threshold
    flags["target_extremes"] = (
        flags["extreme_target_count"]
        >= PRESET["outliers"]["minimum_extreme_targets"]
    )
    flags["single_target_review"] = (
        flags["maximum_absolute_robust_z"]
        > PRESET["outliers"]["single_target_review_threshold"]
    )
    flags["laterality_outlier"] = flags["laterality_distance"] > laterality_threshold
    statistical_columns = [
        "low_similarity",
        "high_multivariate_distance",
        "target_extremes",
        "laterality_outlier",
    ]
    flags["independent_statistical_flags"] = flags[statistical_columns].sum(axis=1)
    flags["statistical_outlier_candidate"] = (
        flags["independent_statistical_flags"]
        >= PRESET["outliers"]["minimum_independent_statistical_flags"]
    )
    flags["spearman_lower_threshold"] = corr_threshold
    flags["pca_distance_upper_threshold"] = distance_threshold
    flags["laterality_distance_upper_threshold"] = laterality_threshold

    technical_reasons = (
        technical.groupby("subject_id")["hard_failure_reasons"]
        .apply(lambda values: ";".join(item for item in values if item))
        .to_dict()
    )
    recommendations = flags[
        [
            "subject_id",
            "technical_failure",
            "statistical_outlier_candidate",
            "single_target_review",
            "roi_outlier_review",
            "independent_statistical_flags",
            "extreme_target_count",
            "maximum_absolute_robust_z",
        ]
    ].copy()
    recommendations["hard_failure_reasons"] = recommendations["subject_id"].map(
        technical_reasons
    )
    recommendations["recommendation"] = "include"
    review = (
        recommendations["statistical_outlier_candidate"]
        | recommendations["single_target_review"]
        | recommendations["roi_outlier_review"]
    )
    recommendations.loc[review, "recommendation"] = "review_required"
    recommendations.loc[
        recommendations["technical_failure"], "recommendation"
    ] = "technical_failure"

    return AnalysisResult(
        profiles=profiles,
        roi_qc=roi_qc,
        technical_qc=technical,
        subject_metrics=subject_metrics,
        robust_zscores=robust_zscores,
        laterality=laterality,
        flags=flags,
        recommendations=recommendations,
        subject_similarity=subject_similarity,
        target_similarity=target_similarity,
        pca_scores=pca_scores,
    )

