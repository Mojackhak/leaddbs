"""Deterministic profile fixtures for configured outcome-model tests."""

from __future__ import annotations

from copy import deepcopy
import csv
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import yaml
import pandas as pd


def valid_study_profile(root: Path) -> dict[str, Any]:
    return {
        "schema_version": "four_model_v1",
        "profile_type": "study_profile",
        "study_id": "synthetic_study",
        "paths": {
            "clinical_table": str(root / "clinical.csv"),
            "stimulation_table": str(root / "stimulation.csv"),
            "leaddbs_derivatives": str(root / "derivatives"),
            "asset_root": str(root / "assets"),
            "output_root": str(root / "outputs"),
        },
        "clinical_columns": {
            "subject_id": "ID",
            "scale": "Scale",
            "protocol": "Protocol",
            "phase": "Phase",
            "value": "Value",
            "baseline": "Baseline",
        },
        "space": {
            "name": "MNI152NLin2009bAsym",
            "reference_image": str(root / "assets" / "brainmask.nii.gz"),
            "brainmask": str(root / "assets" / "brainmask.nii.gz"),
            "canonical_hemisphere": "right",
            "left_to_right_transform": "ea_flip_lr_nonlinear",
        },
        "components": {
            "frequency_1_reference": {
                "alias": "HF",
                "frequency_metadata_binding": "Frequency",
            },
            "frequency_2_addon": {
                "alias": "ULF",
                "frequency_metadata_binding": "Frequency",
            },
        },
        "conditions": {
            "frequency_1_reference": {"protocol": "STN", "phase": "3m"},
            "frequency_2_addon_chronic": {"protocol": "STN+SNr", "phase": "3m"},
            "frequency_2_addon_immediate": {"protocol": "STN+SNr", "phase": "immediate"},
        },
        "efield_resolvers": {
            "frequency_1_reference": "stnsnr_hf_reference",
            "frequency_1_component_under_addon": "stnsnr_hf_component",
            "frequency_2_component_under_addon": "stnsnr_ulf_component",
        },
        "connectomes": {
            "dtor": {
                "label": "dTOR",
                "path": str(root / "connectomes" / "dtor" / "data.mat"),
                "fiber_identity_source": "data.mat:idx",
            }
        },
    }


def valid_scale_profile() -> dict[str, Any]:
    return {
        "schema_version": "four_model_v1",
        "profile_type": "scale_profile",
        "scales": [
            {
                "scale_id": "scale_one",
                "label": "Scale One",
                "direction": "lower",
                "minimum_subjects": 12,
                "endpoint_bindings": {
                    "frequency_1_reference": {"protocol": "STN", "phase": "3m"},
                    "frequency_2_addon_chronic": {"protocol": "STN+SNr", "phase": "3m"},
                },
            }
        ],
    }


def valid_model_profile() -> dict[str, Any]:
    return {
        "schema_version": "four_model_v1",
        "profile_type": "model_profile",
        "profile_id": "four_model_v1",
        "direct_voxel": {
            "estimator": "partial_spearman",
            "pre_specified_tau_v_per_m": 200,
            "pre_specified_coverage": 5,
            "tau_grid_v_per_m": [100, 150, 180, 200, 220, 250, 300, 350, 400, 500],
            "coverage_grid": [5, 6, 7, 8, 10, 12],
            "hard_filter": {
                "n_subjects_min": 12,
                "n_voxels_full_min": 20,
                "fold_n_voxels_min": 10,
                "score_nonconstant_all_folds": True,
                "predictions_finite": True,
            },
        },
        "normative_fiber": {
            "exposure": "peak_efield",
            "pre_specified_tau_v_per_m": 800,
            "pre_specified_coverage": 5,
            "tau_grid_v_per_m": [400, 600, 800, 1000, 1200, 1500, 2000],
            "coverage_grid": [5, 6, 7, 8, 10, 12],
            "hard_filter": {
                "n_subjects_min": 12,
                "fold_candidate_fibers_min_by_connectome": {"dtor": 1000},
                "score_nonconstant_all_folds": True,
                "predictions_finite": True,
            },
            "score": {
                "sweet_fraction": 0.01,
                "sour_fraction": 0.005,
                "weighted_peak_fraction": 0.05,
            },
            "connectome_roles": {"dtor": "formal"},
        },
        "resolver": {"minimum_adjacent_passing_cells": 2},
        "formal": {
            "permutations": 10000,
            "bootstraps": 10000,
            "jitter_resamples": 1000,
            "seed": 42,
        },
        "sensitivity": {
            "selected_tau_multipliers": [0.9, 1.1],
            "ulf_nonfinal_branch": True,
            "ulf_gain": True,
            "ulf_total_exposure": True,
            "ulf_support": True,
            "ulf_collinearity": True,
            "plain_burden_controls": True,
            "cross_connectome": True,
        },
        "oss": {
            "model": "OSS-DBSv2",
            "deterministic_activation_threshold": 0.5,
            "hemisphere_merge_rule": "max_probability_union",
            "canonical_hemisphere": "right",
            "final_dtor_only": True,
        },
        "reporting": {
            "fdr": True,
            "density": True,
            "labels": True,
            "numeric_first": True,
        },
    }


def valid_workflow_profile() -> dict[str, Any]:
    return {
        "schema_version": "four_model_v1",
        "profile_type": "workflow",
        "study_profile": "study.yaml",
        "scale_profile": "scales.yaml",
        "model_profile": "model.yaml",
        "selection": {
            "scales": ["scale_one"],
            "phases": ["chronic"],
            "models": ["all"],
            "connectomes": ["dtor"],
        },
        "execution": {
            "through": "observed",
            "resume": False,
            "force": False,
            "continue_on_endpoint_failure": True,
        },
    }


def write_profile_bundle(
    root: Path,
    *,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    profiles = {
        "study": valid_study_profile(root),
        "scales": valid_scale_profile(),
        "model": valid_model_profile(),
        "workflow": valid_workflow_profile(),
    }
    if mutate is not None:
        mutate(profiles)
    for name, document in profiles.items():
        (root / f"{name}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False),
            encoding="utf-8",
        )
    return root / "workflow.yaml"


def cloned_profiles(root: Path) -> dict[str, Any]:
    return {
        "study": deepcopy(valid_study_profile(root)),
        "scales": deepcopy(valid_scale_profile()),
        "model": deepcopy(valid_model_profile()),
        "workflow": deepcopy(valid_workflow_profile()),
    }


def write_clinical_rows(root: Path, rows: list[dict[str, Any]]) -> Path:
    path = root / "clinical.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def clinical_rows_for_scale(
    scale: str,
    *,
    n_subjects: int = 12,
    include_chronic: bool = True,
    include_immediate: bool = False,
    subject_prefix: str = "sub",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(n_subjects):
        subject = f"{subject_prefix}-{index + 1:02d}"
        baseline = float(40 + index)
        rows.append(
            {
                "ID": subject,
                "Scale": scale,
                "Protocol": "STN",
                "Phase": "3m",
                "Value": float(30 + index),
                "Baseline": baseline,
            }
        )
        if include_chronic:
            rows.append(
                {
                    "ID": subject,
                    "Scale": scale,
                    "Protocol": "STN+SNr",
                    "Phase": "3m",
                    "Value": float(25 + index),
                    "Baseline": baseline,
                }
            )
        if include_immediate:
            rows.append(
                {
                    "ID": subject,
                    "Scale": scale,
                    "Protocol": "STN+SNr",
                    "Phase": "immediate",
                    "Value": float(27 + index),
                    "Baseline": baseline,
                }
            )
    return rows


def clinical_rows(
    *,
    scale: str = "Scale One",
    protocol: str,
    phase: str,
    subject_ids: Iterable[str] = tuple(f"sub-{index:02d}" for index in range(1, 13)),
    value_offset: float = 0.0,
) -> list[dict[str, Any]]:
    """Build deterministic synthetic clinical rows for one condition."""
    return [
        {
            "ID": subject_id,
            "Scale": scale,
            "Protocol": protocol,
            "Phase": phase,
            "Value": value_offset + index,
            "Baseline": 100.0 + index,
        }
        for index, subject_id in enumerate(subject_ids, start=1)
    ]


def write_clinical_table(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write a synthetic CSV or XLSX clinical table."""
    materialized = [dict(row) for row in rows]
    if path.suffix.lower() == ".csv":
        fieldnames = list(materialized[0]) if materialized else [
            "ID",
            "Scale",
            "Protocol",
            "Phase",
            "Value",
            "Baseline",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(materialized)
        return
    if path.suffix.lower() == ".xlsx":
        import pandas as pd

        pd.DataFrame(materialized).to_excel(path, index=False)
        return
    raise ValueError(f"unsupported synthetic clinical table extension: {path.suffix}")
