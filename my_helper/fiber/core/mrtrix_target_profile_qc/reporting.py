"""CSV, figure, and Markdown reporting for target-profile QC."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .analysis import AnalysisResult
from .models import QcValidation


def _write_csv(frame: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    frame.to_csv(path, index=index, float_format="%.10g", lineterminator="\n")


def _heatmap(
    frame: pd.DataFrame,
    path: Path,
    *,
    title: str,
    center: float | None = None,
    cmap: str = "viridis",
) -> None:
    width = max(8.0, min(18.0, frame.shape[1] * 0.45))
    height = max(5.0, min(14.0, frame.shape[0] * 0.38))
    figure, axis = plt.subplots(figsize=(width, height))
    sns.heatmap(
        frame,
        ax=axis,
        cmap=cmap,
        center=center,
        cbar_kws={"shrink": 0.75},
    )
    axis.set_title(title)
    axis.set_xlabel("")
    axis.set_ylabel("")
    figure.tight_layout()
    figure.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _write_profile_figures(result: AnalysisResult, figures: Path) -> None:
    for side in sorted(result.profiles["seed_side"].unique()):
        subset = result.profiles[result.profiles["seed_side"] == side]
        matrix = subset.pivot(
            index="subject_id", columns="feature_key", values="hit_fraction"
        ).sort_index(axis=0).sort_index(axis=1)
        _heatmap(
            matrix,
            figures / f"target_profile_heatmap_{side}.png",
            title=f"Target hit fractions: {side}",
        )
        _heatmap(
            result.subject_similarity[side],
            figures / f"subject_similarity_heatmap_{side}.png",
            title=f"Subject Spearman similarity: {side}",
            center=0.0,
            cmap="vlag",
        )
    _heatmap(
        result.subject_similarity["combined"],
        figures / "subject_similarity_combined.png",
        title="Combined subject Spearman similarity",
        center=0.0,
        cmap="vlag",
    )


def _write_pca_figure(result: AnalysisResult, figures: Path) -> None:
    scores = result.pca_scores[result.pca_scores["analysis_group"] == "combined"].copy()
    if "pc1" not in scores:
        return
    if "pc2" not in scores:
        scores["pc2"] = 0.0
    recommendations = result.recommendations.set_index("subject_id")["recommendation"]
    colors = {
        "include": "#2b8cbe",
        "review_required": "#fdae6b",
        "technical_failure": "#de2d26",
    }
    figure, axis = plt.subplots(figsize=(8, 6))
    for _, row in scores.iterrows():
        recommendation = recommendations.get(row["subject_id"], "include")
        axis.scatter(row["pc1"], row["pc2"], color=colors[recommendation], s=55)
        axis.annotate(
            row["subject_id"],
            (row["pc1"], row["pc2"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    axis.set_xlabel("PC1")
    axis.set_ylabel("PC2")
    axis.set_title("Combined target-profile PCA")
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(figures / "pca_subjects.png", dpi=300, bbox_inches="tight")
    plt.close(figure)


def _write_secondary_figures(result: AnalysisResult, figures: Path) -> None:
    zscores = result.robust_zscores[
        result.robust_zscores["analysis_group"] == "combined"
    ].pivot(index="subject_id", columns="feature_key", values="robust_z")
    _heatmap(
        zscores.sort_index(axis=0).sort_index(axis=1),
        figures / "target_robust_zscores.png",
        title="Robust target-profile z-scores",
        center=0.0,
        cmap="vlag",
    )
    roi = result.roi_qc.copy()
    roi["feature_key"] = (
        roi["seed_side"] + "|" + roi["roi_type"] + "|" + roi["roi_id"]
    )
    roi_matrix = roi.pivot(
        index="subject_id", columns="feature_key", values="volume_robust_z"
    )
    _heatmap(
        roi_matrix.sort_index(axis=0).sort_index(axis=1),
        figures / "roi_volume_qc.png",
        title="DWI-space ROI volume robust z-scores",
        center=0.0,
        cmap="vlag",
    )
    if not result.laterality.empty:
        laterality = result.laterality.pivot(
            index="subject_id", columns="feature_key", values="asymmetry_index"
        )
        _heatmap(
            laterality.sort_index(axis=0).sort_index(axis=1),
            figures / "laterality_asymmetry.png",
            title="Target laterality asymmetry",
            center=0.0,
            cmap="vlag",
        )


def _markdown_table(frame: pd.DataFrame, columns: Iterable[str]) -> str:
    subset = frame[list(columns)].copy()
    headers = list(subset.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in subset.iterrows():
        values = [str(row[column]).replace("|", "\\|") for column in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _write_report(result: AnalysisResult, validation: QcValidation, path: Path) -> None:
    counts = result.recommendations["recommendation"].value_counts().to_dict()
    table = _markdown_table(
        result.recommendations.sort_values("subject_id"),
        [
            "subject_id",
            "recommendation",
            "technical_failure",
            "statistical_outlier_candidate",
            "independent_statistical_flags",
            "extreme_target_count",
            "hard_failure_reasons",
        ],
    )
    path.write_text(
        "\n".join(
            [
                "# MRtrix Target-Profile QC Report",
                "",
                f"- Preset: `{validation.config.preset}`",
                f"- Tracking configuration: `{validation.config.tracking_config}`",
                f"- Subjects: {len(validation.tracking.subjects)}",
                f"- Seed profiles: {len(validation.records)}",
                f"- Include: {counts.get('include', 0)}",
                f"- Review required: {counts.get('review_required', 0)}",
                f"- Technical failure: {counts.get('technical_failure', 0)}",
                "- Automatic exclusion: disabled",
                "",
                "Statistical outliers are review candidates, not automatic exclusions.",
                "",
                "## Subject recommendations",
                "",
                table,
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_analysis_outputs(
    result: AnalysisResult,
    validation: QcValidation,
    directory: Path,
) -> None:
    """Write all deterministic analysis tables and diagnostic figures."""

    directory.mkdir(parents=True, exist_ok=False)
    figures = directory / "figures"
    figures.mkdir()

    inventory = pd.DataFrame(
        [
            {
                "subject_id": record.subject_id,
                "subject_dir": str(record.subject_dir),
                "seed_key": record.seed.key,
                "preparation_identity": record.preparation_identity,
                "seedwide_identity": record.seedwide_identity,
                "seed_state_status": record.state["status"],
                "seed_state_path": str(record.state_path),
                "seed_state_sha256": record.state_hash,
            }
            for record in validation.records
        ]
    )
    _write_csv(inventory, directory / "input_inventory.csv")
    _write_csv(result.profiles, directory / "target_profiles_long.csv")
    _write_csv(result.roi_qc, directory / "roi_qc.csv")
    _write_csv(result.technical_qc, directory / "technical_qc.csv")
    _write_csv(result.subject_metrics, directory / "subject_qc_metrics.csv")
    _write_csv(result.robust_zscores, directory / "target_robust_zscores.csv")
    _write_csv(result.laterality, directory / "laterality_asymmetry.csv")
    _write_csv(result.flags, directory / "qc_flags.csv")
    _write_csv(result.recommendations, directory / "inclusion_recommendation.csv")
    for group, matrix in result.subject_similarity.items():
        _write_csv(
            matrix,
            directory / f"subject_similarity_{group}.csv",
            index=True,
        )
    for side, matrix in result.target_similarity.items():
        _write_csv(
            matrix,
            directory / f"target_similarity_{side}.csv",
            index=True,
        )

    sns.set_theme(style="whitegrid", context="notebook")
    _write_profile_figures(result, figures)
    _write_pca_figure(result, figures)
    _write_secondary_figures(result, figures)
    _write_report(result, validation, directory / "report.md")

