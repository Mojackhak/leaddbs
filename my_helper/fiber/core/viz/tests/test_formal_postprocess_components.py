from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr, spearmanr

from my_helper.fiber.core.viz import formal_postprocess
from my_helper.fiber.core.viz import paired_fit_postprocess
from my_helper.fiber.core.viz.formal_postprocess import (
    run_formal_postprocess,
    validate_formal_postprocess,
    validate_formal_postprocess_output,
)
from my_helper.fiber.core.viz.paired_fit_postprocess import (
    PAIRED_METRIC_FIELDS,
    render_paired_fit_components,
    run_single_scale_paired_fit_postprocess,
    validate_paired_metrics,
)
from my_helper.fiber.core.viz.plugin.default import get_fit_cfg
from my_helper.fiber.core.viz.published_artifacts import PublicationCatalog


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paired_metrics(subject_count: int = 3) -> dict[str, object]:
    if subject_count != 3:
        raise ValueError("paired metric fixture supports exactly three subjects")
    outcome = np.asarray([1.0, 2.0, 3.0])
    in_sample = np.asarray([1.1, 2.1, 2.9])
    loocv = np.asarray([1.2, 1.9, 2.8])
    in_sample_baseline = np.asarray([2.0, 2.0, 2.0])
    loocv_baseline = np.asarray([2.1, 2.1, 2.1])

    def metrics(
        prediction: np.ndarray,
        baseline: np.ndarray,
    ) -> dict[str, float]:
        model_error = outcome - prediction
        baseline_error = outcome - baseline
        model_sse = float(np.sum(model_error**2))
        baseline_sse = float(np.sum(baseline_error**2))
        total_sse = float(np.sum((outcome - np.mean(outcome)) ** 2))
        spearman = spearmanr(outcome, prediction)
        pearson = pearsonr(outcome, prediction)
        return {
            "spearman": float(spearman.statistic),
            "spearman_p": float(spearman.pvalue),
            "pearson": float(pearson.statistic),
            "pearson_p": float(pearson.pvalue),
            "r2": 1.0 - model_sse / total_sse,
            "relative_r2": 1.0 - model_sse / baseline_sse,
            "rmse": float(np.sqrt(np.mean(model_error**2))),
            "mae": float(np.mean(np.abs(model_error))),
            "rmse_baseline": float(np.sqrt(np.mean(baseline_error**2))),
            "mae_baseline": float(np.mean(np.abs(baseline_error))),
        }

    in_metrics = metrics(in_sample, in_sample_baseline)
    loocv_metrics = metrics(loocv, loocv_baseline)
    return {
        "in_sample_n_subjects_total": subject_count,
        "in_sample_n_subjects_finite": subject_count,
        "in_sample_predictions_all_finite": True,
        "in_sample_spearman_rho": in_metrics["spearman"],
        "in_sample_spearman_nominal_p": in_metrics["spearman_p"],
        "in_sample_pearson_r": in_metrics["pearson"],
        "in_sample_pearson_nominal_p": in_metrics["pearson_p"],
        "in_sample_r2": in_metrics["r2"],
        "in_sample_relative_r2": in_metrics["relative_r2"],
        "in_sample_rmse": in_metrics["rmse"],
        "in_sample_mae": in_metrics["mae"],
        "in_sample_rmse_baseline": in_metrics["rmse_baseline"],
        "in_sample_mae_baseline": in_metrics["mae_baseline"],
        "in_sample_permutation_p_plus_one_two_sided": 0.12,
        "in_sample_permutations_requested": 10000,
        "in_sample_permutations_finite": 10000,
        "in_sample_permutation_q_bh_model_family": 0.24,
        "in_sample_permutation_q_bh_all_endpoints": 0.36,
        "loocv_n_subjects_total": subject_count,
        "loocv_n_subjects_finite": subject_count,
        "loocv_predictions_all_finite": True,
        "loocv_spearman_rho": loocv_metrics["spearman"],
        "loocv_spearman_nominal_p": loocv_metrics["spearman_p"],
        "loocv_pearson_r": loocv_metrics["pearson"],
        "loocv_pearson_nominal_p": loocv_metrics["pearson_p"],
        "loocv_r2": loocv_metrics["r2"],
        "loocv_q2": loocv_metrics["relative_r2"],
        "loocv_rmse_model": loocv_metrics["rmse"],
        "loocv_mae_model": loocv_metrics["mae"],
        "loocv_rmse_baseline": loocv_metrics["rmse_baseline"],
        "loocv_mae_baseline": loocv_metrics["mae_baseline"],
        "loocv_permutation_p_plus_one_two_sided": 0.3,
        "loocv_permutations_requested": 10000,
        "loocv_permutations_finite": 10000,
        "loocv_permutation_q_bh_model_family": 0.45,
        "loocv_permutation_q_bh_all_endpoints": 0.55,
        "subject_mask_match": True,
        "spearman_optimism_gap": (
            in_metrics["spearman"] - loocv_metrics["spearman"]
        ),
        "pearson_optimism_gap": (
            in_metrics["pearson"] - loocv_metrics["pearson"]
        ),
        "r2_optimism_gap": in_metrics["r2"] - loocv_metrics["r2"],
        "relative_r2_q2_gap": (
            in_metrics["relative_r2"] - loocv_metrics["relative_r2"]
        ),
        "rmse_optimism_gap": loocv_metrics["rmse"] - in_metrics["rmse"],
        "mae_optimism_gap": loocv_metrics["mae"] - in_metrics["mae"],
    }


def _write_publication_index(
    root: Path,
    *,
    manifest_name: str,
    relative_paths: list[str],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / manifest_name).write_text(
        json.dumps({"status": "complete", "publication_id": root.name}),
        encoding="utf-8",
    )
    rows = []
    for relative in relative_paths:
        path = root / relative
        rows.append(
            {
                "relative_path": relative,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "status": "complete",
                "artifact_kind": path.suffix.lstrip("."),
            }
        )
    pd.DataFrame(rows).to_csv(root / "artifact_index.csv", index=False)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("in_sample_adjusted_r2", 0.2, "must not publish"),
        ("subject_mask_match", False, "must be true"),
        (
            "loocv_permutations_finite",
            9999,
            "finite permutations must cover",
        ),
        ("relative_r2_q2_gap", 0.9, "optimism gap"),
        ("in_sample_spearman_nominal_p", 1.1, "probability"),
        ("loocv_rmse_model", float("nan"), "must be finite"),
    ),
)
def test_paired_metric_contract_rejects_inconsistent_values(
    field: str,
    value: object,
    message: str,
) -> None:
    metrics = _paired_metrics()
    metrics[field] = value
    with pytest.raises(ValueError, match=message):
        validate_paired_metrics(metrics)


def _refresh_publication_index_entry(root: Path, relative_path: str) -> None:
    index_path = root / "artifact_index.csv"
    rows = pd.read_csv(index_path)
    selected = rows["relative_path"] == relative_path
    assert int(selected.sum()) == 1
    artifact = root / relative_path
    rows.loc[selected, "sha256"] = _sha256(artifact)
    rows.loc[selected, "size_bytes"] = artifact.stat().st_size
    rows.to_csv(index_path, index=False)


def _paired_fit_catalog(tmp_path: Path) -> PublicationCatalog:
    roots = {
        "direct_voxel_main": tmp_path / "direct_voxel_main",
        "direct_voxel_in_sample": tmp_path / "direct_voxel_in_sample",
        "normative_fiber_main": tmp_path / "normative_fiber_main",
        "normative_fiber_in_sample": tmp_path / "normative_fiber_in_sample",
    }
    main_paths = {"direct_voxel_main": [], "normative_fiber_main": []}
    extension_paths = {
        "direct_voxel_in_sample": [],
        "normative_fiber_in_sample": [],
    }
    families = (
        ("direct_voxel_main", "direct_voxel_in_sample", "reference", "reference_voxel"),
        ("direct_voxel_main", "direct_voxel_in_sample", "addon", "addon_voxel"),
        (
            "normative_fiber_main",
            "normative_fiber_in_sample",
            "reference",
            "reference_fiber",
        ),
        ("normative_fiber_main", "normative_fiber_in_sample", "addon", "addon_fiber"),
    )
    for scale_id in ("scale_a", "scale_b"):
        for main_alias, extension_alias, role, model_family in families:
            final_relative = f"{scale_id}/{role}/final_model.json"
            final_path = roots[main_alias] / final_relative
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_payload = {
                "final_status": "final_model_realized",
                "scale_id": scale_id,
                "model_family": model_family,
                "selected_tau_v_per_m": 200 if "voxel" in model_family else 400,
                "selected_coverage_subjects_min": 5,
                "realized_final_branch": "no_delta_reference",
            }
            if "voxel" in model_family:
                final_payload["final_model_id"] = f"{scale_id}_{model_family}"
            final_path.write_text(json.dumps(final_payload), encoding="utf-8")
            main_paths[main_alias].append(final_relative)

            summary_relative = (
                f"{scale_id}/{role}/sensitivity/final_in_sample/summary.json"
            )
            predictions_relative = (
                f"{scale_id}/{role}/sensitivity/final_in_sample/predictions.csv"
            )
            summary_path = roots[extension_alias] / summary_relative
            predictions_path = roots[extension_alias] / predictions_relative
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "technical_status": "complete",
                        "endpoint_id": f"endpoint_{scale_id}_{model_family}",
                        "scale_id": scale_id,
                        "model_family": model_family,
                        "final_model_id": f"{scale_id}_{model_family}",
                        "selected_tau": 200 if "voxel" in model_family else 400,
                        "selected_coverage": 5,
                        "final_branch": "no_delta_reference",
                        **_paired_metrics(),
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "subject_id": ["sub-01", "sub-02", "sub-03"],
                    "outcome": [1.0, 2.0, 3.0],
                    "in_sample_prediction": [1.1, 2.1, 2.9],
                    "loocv_prediction": [1.2, 1.9, 2.8],
                    "in_sample_baseline_prediction": [2.0, 2.0, 2.0],
                    "loocv_baseline_prediction": [2.1, 2.1, 2.1],
                }
            ).to_csv(predictions_path, index=False)
            extension_paths[extension_alias].extend(
                (summary_relative, predictions_relative)
            )

    for alias, relative_paths in main_paths.items():
        _write_publication_index(
            roots[alias], manifest_name="model_manifest.json", relative_paths=relative_paths
        )
    for alias, relative_paths in extension_paths.items():
        _write_publication_index(
            roots[alias],
            manifest_name="extension_manifest.json",
            relative_paths=relative_paths,
        )
    return _load_paired_fit_catalog(tmp_path)


def _load_paired_fit_catalog(tmp_path: Path) -> PublicationCatalog:
    return PublicationCatalog.from_config(
        _paired_fit_publications(tmp_path),
        config_base=tmp_path,
    )


def _paired_fit_publications(tmp_path: Path) -> dict[str, dict[str, str]]:
    aliases = (
        "direct_voxel_main",
        "direct_voxel_in_sample",
        "normative_fiber_main",
        "normative_fiber_in_sample",
    )
    return {
        alias: {
            "root": str(tmp_path / alias),
            "manifest": (
                "extension_manifest.json"
                if alias.endswith("in_sample")
                else "model_manifest.json"
            ),
        }
        for alias in aliases
    }


def test_paired_fit_components_preserve_two_scales_without_root_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    catalog = _paired_fit_catalog(tmp_path)
    output_root = tmp_path / "output"

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess, "plot_in_sample_loocv_fit", fake_plot
    )
    style = get_fit_cfg({"formats": ("png",), "dpi": 72})
    first = render_paired_fit_components(
        scale_ids=("scale_a", "scale_b"),
        output_root=output_root,
        catalog=catalog,
        style=style,
    )

    assert len(first) == 8
    assert all(item["status"] == "complete" for item in first)
    assert not (output_root / "manifest.json").exists()
    assert not (output_root / "endpoint_index.csv").exists()
    assert not (output_root / "README.md").exists()
    for item in first:
        result_path = output_root / item["result_path"]
        assert result_path.name == "in_sample_loocv_fit.json"
        assert result_path.is_file()
        assert (
            result_path.parent / "completion/paired_fit/complete.json"
        ).is_file()
        assert (result_path.parent / "in_sample_loocv_fit.png").is_file()

    monkeypatch.setattr(
        paired_fit_postprocess,
        "_resolve_sources",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed paired component reopened its sources")
        ),
    )
    second = render_paired_fit_components(
        scale_ids=("scale_a", "scale_b"),
        output_root=output_root,
        catalog=catalog,
        style=style,
    )
    assert len(second) == 8
    assert all(item.get("resume_status") == "reused" for item in second)


def test_single_scale_paired_fit_index_retains_complete_metrics(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess,
        "plot_in_sample_loocv_fit",
        fake_plot,
    )
    output_root = tmp_path / "single_scale"
    first = run_single_scale_paired_fit_postprocess(
        scale_id="scale_a",
        output_root=output_root,
        publications=_paired_fit_publications(tmp_path),
        style_overrides={"formats": ("png",), "dpi": 72},
    )
    assert first["status"] == "complete"
    assert first["completed_count"] == 4
    index = pd.read_csv(output_root / "endpoint_index.csv")
    assert len(index.index) == 4
    assert set(PAIRED_METRIC_FIELDS).issubset(index.columns)
    assert "complete paired in-sample and LOOCV metric" in (
        output_root / "README.md"
    ).read_text(encoding="utf-8")
    expected = _paired_metrics()
    assert index["in_sample_pearson_r"].tolist() == pytest.approx(
        [expected["in_sample_pearson_r"]] * 4
    )
    assert index["loocv_rmse_baseline"].tolist() == pytest.approx(
        [expected["loocv_rmse_baseline"]] * 4
    )
    assert index["relative_r2_q2_gap"].tolist() == pytest.approx(
        [expected["relative_r2_q2_gap"]] * 4
    )

    second = run_single_scale_paired_fit_postprocess(
        scale_id="scale_a",
        output_root=output_root,
        publications=_paired_fit_publications(tmp_path),
        style_overrides={"formats": ("png",), "dpi": 72},
    )
    assert second["status"] == "complete"
    assert second["reused_count"] == 4


def test_paired_fit_component_resume_preserves_complete_first_scale(
    tmp_path: Path, monkeypatch
) -> None:
    catalog = _paired_fit_catalog(tmp_path)
    output_root = tmp_path / "partial_output"

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess, "plot_in_sample_loocv_fit", fake_plot
    )
    original_validate = paired_fit_postprocess._validate_endpoint

    def fail_second_scale(spec, scale_id, final_model, summary):
        if scale_id == "scale_b":
            raise ValueError("synthetic second-scale failure")
        return original_validate(spec, scale_id, final_model, summary)

    monkeypatch.setattr(
        paired_fit_postprocess, "_validate_endpoint", fail_second_scale
    )
    style = get_fit_cfg({"formats": ("png",), "dpi": 72})
    first = render_paired_fit_components(
        scale_ids=("scale_a", "scale_b"),
        output_root=output_root,
        catalog=catalog,
        style=style,
    )
    assert sum(item["status"] == "complete" for item in first) == 4
    assert sum(item["status"] == "failed" for item in first) == 4

    monkeypatch.setattr(
        paired_fit_postprocess, "_validate_endpoint", original_validate
    )
    second = render_paired_fit_components(
        scale_ids=("scale_a", "scale_b"),
        output_root=output_root,
        catalog=catalog,
        style=style,
    )
    scale_a = [item for item in second if item["scale_id"] == "scale_a"]
    scale_b = [item for item in second if item["scale_id"] == "scale_b"]
    assert all(item.get("resume_status") == "reused" for item in scale_a)
    assert all(item["status"] == "complete" for item in scale_b)
    assert all("resume_status" not in item for item in scale_b)


def test_paired_fit_component_rejects_incomplete_metric_contract(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    relative = "scale_a/reference/sensitivity/final_in_sample/summary.json"
    summary_path = tmp_path / "direct_voxel_in_sample" / relative
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("in_sample_pearson_r")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    _refresh_publication_index_entry(
        tmp_path / "direct_voxel_in_sample",
        relative,
    )
    catalog = _load_paired_fit_catalog(tmp_path)

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess,
        "plot_in_sample_loocv_fit",
        fake_plot,
    )
    results = render_paired_fit_components(
        scale_ids=("scale_a",),
        output_root=tmp_path / "missing_metric",
        catalog=catalog,
        style=get_fit_cfg({"formats": ("png",), "dpi": 72}),
    )
    target = next(
        item for item in results if item["model_family"] == "reference_voxel"
    )
    assert target["status"] == "failed"
    assert "in_sample_pearson_r" in target["error_message"]
    assert not (
        tmp_path
        / "missing_metric/scales/scale_a/reference/voxel/in_sample_loocv_fit.png"
    ).exists()


def test_paired_fit_component_rejects_missing_baseline_prediction(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    relative = "scale_a/reference/sensitivity/final_in_sample/predictions.csv"
    predictions_path = tmp_path / "direct_voxel_in_sample" / relative
    predictions = pd.read_csv(predictions_path)
    predictions = predictions.drop(columns=["loocv_baseline_prediction"])
    predictions.to_csv(predictions_path, index=False)
    _refresh_publication_index_entry(
        tmp_path / "direct_voxel_in_sample",
        relative,
    )
    catalog = _load_paired_fit_catalog(tmp_path)

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess,
        "plot_in_sample_loocv_fit",
        fake_plot,
    )
    results = render_paired_fit_components(
        scale_ids=("scale_a",),
        output_root=tmp_path / "missing_baseline",
        catalog=catalog,
        style=get_fit_cfg({"formats": ("png",), "dpi": 72}),
    )
    target = next(
        item for item in results if item["model_family"] == "reference_voxel"
    )
    assert target["status"] == "failed"
    assert "loocv_baseline_prediction" in target["error_message"]
    assert not (
        tmp_path
        / "missing_baseline/scales/scale_a/reference/voxel/in_sample_loocv_fit.png"
    ).exists()


def _formal_fit_config(tmp_path: Path, output_name: str) -> Path:
    config = {
        "schema_version": "dual_frequency_formal_postprocess_v1",
        "output_root": str(tmp_path / output_name),
        "publications": {
            alias: {
                "root": str(tmp_path / alias),
                "manifest": (
                    "extension_manifest.json"
                    if alias.endswith("in_sample")
                    else "model_manifest.json"
                ),
            }
            for alias in (
                "direct_voxel_main",
                "direct_voxel_in_sample",
                "normative_fiber_main",
                "normative_fiber_in_sample",
            )
        },
        "scales": "all_available",
        "components": ["paired_fit"],
        "styles": {"paired_fit": {"formats": ["png"], "dpi": 72}},
    }
    path = tmp_path / f"{output_name}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("missing_metric", "in_sample_pearson_r"),
        ("missing_prediction_column", "loocv_baseline_prediction"),
        (
            "prediction_metric_mismatch",
            "prediction table metric in_sample_pearson_r differs",
        ),
    ),
)
def test_formal_validate_only_enforces_complete_paired_source_contract(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    _paired_fit_catalog(tmp_path)
    root = tmp_path / "direct_voxel_in_sample"
    if case == "missing_metric":
        relative = "scale_a/reference/sensitivity/final_in_sample/summary.json"
        path = root / relative
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary.pop("in_sample_pearson_r")
        path.write_text(json.dumps(summary), encoding="utf-8")
    elif case == "missing_prediction_column":
        relative = "scale_a/reference/sensitivity/final_in_sample/predictions.csv"
        path = root / relative
        predictions = pd.read_csv(path).drop(
            columns=["loocv_baseline_prediction"]
        )
        predictions.to_csv(path, index=False)
    else:
        relative = "scale_a/reference/sensitivity/final_in_sample/predictions.csv"
        path = root / relative
        predictions = pd.read_csv(path)
        predictions.loc[0, "in_sample_prediction"] += 0.5
        predictions.to_csv(path, index=False)
    _refresh_publication_index_entry(root, relative)

    config_path = _formal_fit_config(tmp_path, f"preflight_{case}")
    with pytest.raises(ValueError, match=message):
        validate_formal_postprocess(config_path)
    assert not (tmp_path / f"preflight_{case}").exists()


def test_formal_validate_only_accepts_independent_loocv_secondary_metrics(
    tmp_path: Path,
) -> None:
    _paired_fit_catalog(tmp_path)
    root = tmp_path / "direct_voxel_in_sample"
    relative = "scale_a/reference/sensitivity/final_in_sample/summary.json"
    path = root / relative
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["loocv_pearson_r"] = float(summary["loocv_pearson_r"]) - 0.001
    summary["pearson_optimism_gap"] = (
        float(summary["in_sample_pearson_r"]) - float(summary["loocv_pearson_r"])
    )
    path.write_text(json.dumps(summary), encoding="utf-8")
    _refresh_publication_index_entry(root, relative)

    result = validate_formal_postprocess(
        _formal_fit_config(tmp_path, "preflight_independent_loocv")
    )

    assert result["status"] == "valid"
    assert result["endpoint_count"] == 8


def test_formal_endpoint_resolution_preserves_nondefault_selected_cells(
    tmp_path: Path,
) -> None:
    _paired_fit_catalog(tmp_path)
    cases = (
        (
            "direct_voxel_main",
            "direct_voxel_in_sample",
            "scale_a/reference",
            "endpoint_scale_a_reference_voxel",
            180,
            8,
        ),
        (
            "normative_fiber_main",
            "normative_fiber_in_sample",
            "scale_b/addon",
            "endpoint_scale_b_addon_fiber",
            600,
            10,
        ),
    )
    for (
        main_alias,
        in_sample_alias,
        base,
        _endpoint_id,
        selected_tau,
        selected_coverage,
    ) in cases:
        final_relative = f"{base}/final_model.json"
        final_path = tmp_path / main_alias / final_relative
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["selected_tau_v_per_m"] = selected_tau
        final["selected_coverage_subjects_min"] = selected_coverage
        final_path.write_text(json.dumps(final), encoding="utf-8")
        _refresh_publication_index_entry(
            tmp_path / main_alias,
            final_relative,
        )

        summary_relative = (
            f"{base}/sensitivity/final_in_sample/summary.json"
        )
        summary_path = tmp_path / in_sample_alias / summary_relative
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["selected_tau"] = selected_tau
        summary["selected_coverage"] = selected_coverage
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        _refresh_publication_index_entry(
            tmp_path / in_sample_alias,
            summary_relative,
        )

    config_path = _formal_fit_config(tmp_path, "nondefault_parameters")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    catalog = PublicationCatalog.from_config(
        config["publications"],
        config_base=tmp_path,
    )
    endpoints = formal_postprocess._resolve_endpoints(
        scales=("scale_a", "scale_b"),
        components=("paired_fit",),
        catalog=catalog,
    )
    by_id = {item["endpoint_id"]: item for item in endpoints}
    for (
        _main_alias,
        _in_sample_alias,
        _base,
        endpoint_id,
        selected_tau,
        selected_coverage,
    ) in cases:
        assert by_id[endpoint_id]["selected_tau"] == selected_tau
        assert by_id[endpoint_id]["selected_coverage"] == selected_coverage


def test_formal_postprocess_commits_root_only_after_all_endpoints_complete(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    config_path = _formal_fit_config(tmp_path, "formal_output")

    def fake_plot(*args, output_paths, **kwargs):
        del args, kwargs
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess, "plot_in_sample_loocv_fit", fake_plot
    )
    output_root = tmp_path / "formal_output"
    validation = validate_formal_postprocess(config_path)
    assert validation["status"] == "valid"
    assert validation["scale_count"] == 2
    assert validation["endpoint_count"] == 8
    assert not output_root.exists()

    first = run_formal_postprocess(config_path)
    assert first["status"] == "complete"
    assert first["endpoint_count"] == 8
    assert first["completed_count"] == 8
    assert first["failed_count"] == 0
    assert (output_root / "complete.json").is_file()
    assert (output_root / "request.json").is_file()
    assert (output_root / "resolved_request.json").is_file()
    assert (output_root / "endpoint_index.csv").is_file()
    assert (output_root / "README.md").is_file()
    assert (output_root / "manifest.json").is_file()
    assert all(
        item["status"] == "complete" for item in first["endpoint_results"]
    )
    endpoint_index = pd.read_csv(output_root / "endpoint_index.csv")
    assert set(PAIRED_METRIC_FIELDS).issubset(endpoint_index.columns)
    assert len(endpoint_index.index) == 8
    first_endpoint = first["endpoint_results"][0]
    assert set(first_endpoint["metrics"]) == set(PAIRED_METRIC_FIELDS)
    expected_metrics = _paired_metrics()
    first_index_row = endpoint_index.loc[
        endpoint_index["endpoint_id"] == first_endpoint["endpoint_id"]
    ].iloc[0]
    assert first_index_row["in_sample_pearson_r"] == pytest.approx(
        expected_metrics["in_sample_pearson_r"]
    )
    assert first_index_row["loocv_rmse_baseline"] == pytest.approx(
        expected_metrics["loocv_rmse_baseline"]
    )
    assert first_index_row["relative_r2_q2_gap"] == pytest.approx(
        expected_metrics["relative_r2_q2_gap"]
    )

    second = run_formal_postprocess(config_path)
    assert second["status"] == "complete"
    assert all(
        item.get("resume_status") == "reused"
        for item in second["component_results"]["paired_fit"]
    )
    terminal = validate_formal_postprocess_output(output_root)
    assert terminal["status"] == "valid"
    assert terminal["endpoint_count"] == 8
    assert terminal["declared_output_count"] == 8
    assert terminal["component_manifest_count"] == 8

    complete_path = output_root / "complete.json"
    held_complete = output_root / "complete.held.json"
    complete_path.rename(held_complete)
    with pytest.raises(ValueError, match="root file is missing"):
        validate_formal_postprocess_output(output_root)
    held_complete.rename(complete_path)

    original_index = (output_root / "endpoint_index.csv").read_text(
        encoding="utf-8"
    )
    index_path = output_root / "endpoint_index.csv"
    with index_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        changed_rows = list(reader)
        fieldnames = tuple(reader.fieldnames or ())
    changed_rows[0]["pearson_optimism_gap"] = "0.9"
    with index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(changed_rows)
    with pytest.raises(
        ValueError,
        match="endpoint index metric pearson_optimism_gap differs",
    ):
        validate_formal_postprocess_output(output_root)
    (output_root / "endpoint_index.csv").write_text(
        original_index,
        encoding="utf-8",
    )

    component_manifest = output_root / second["endpoint_results"][0][
        "component_manifests"
    ][0]
    component_payload = json.loads(component_manifest.read_text(encoding="utf-8"))
    component_payload["status"] = "running"
    component_manifest.write_text(json.dumps(component_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="component manifest is incomplete"):
        validate_formal_postprocess_output(output_root)
    component_payload["status"] = "complete"
    component_manifest.write_text(json.dumps(component_payload), encoding="utf-8")

    root_manifest_path = output_root / "manifest.json"
    root_manifest = json.loads(root_manifest_path.read_text(encoding="utf-8"))
    root_manifest["component_results"]["paired_fit"].append(
        dict(root_manifest["component_results"]["paired_fit"][0])
    )
    root_manifest_path.write_text(json.dumps(root_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="component result closure differs"):
        validate_formal_postprocess_output(output_root)
    root_manifest["component_results"]["paired_fit"].pop()
    root_manifest_path.write_text(json.dumps(root_manifest), encoding="utf-8")

    root_manifest["component_results"]["unrequested"] = []
    root_manifest_path.write_text(json.dumps(root_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="component result families differ"):
        validate_formal_postprocess_output(output_root)
    root_manifest["component_results"].pop("unrequested")
    root_manifest_path.write_text(json.dumps(root_manifest), encoding="utf-8")

    missing = output_root / second["endpoint_results"][0]["outputs"][0]
    missing.unlink()
    with pytest.raises(ValueError, match="declared output is missing"):
        validate_formal_postprocess_output(output_root)


def test_formal_postprocess_never_marks_missing_component_rows_complete(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    config_path = _formal_fit_config(tmp_path, "failed_output")
    monkeypatch.setattr(formal_postprocess, "render_paired_fit_components", lambda **kwargs: [])

    result = run_formal_postprocess(config_path)
    assert result["status"] == "completed_with_failures"
    assert result["completed_count"] == 0
    assert result["failed_count"] == 8
    assert all(item["status"] == "failed" for item in result["endpoint_results"])


def test_formal_postprocess_reuses_completed_root_until_force(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    config_path = _formal_fit_config(tmp_path, "immutable_output")

    render_count = 0

    def fake_plot(*args, output_paths, **kwargs):
        nonlocal render_count
        del args, kwargs
        render_count += 1
        figure = plt.figure()
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path)
        return figure

    monkeypatch.setattr(
        paired_fit_postprocess, "plot_in_sample_loocv_fit", fake_plot
    )
    first = run_formal_postprocess(config_path)
    assert first["status"] == "complete"
    assert render_count == 8
    output_root = tmp_path / "immutable_output"
    manifest_path = output_root / "manifest.json"
    manifest_mtime = manifest_path.stat().st_mtime_ns
    changed = json.loads(config_path.read_text(encoding="utf-8"))
    changed["styles"]["paired_fit"]["dpi"] = 96
    config_path.write_text(json.dumps(changed), encoding="utf-8")

    original_catalog_loader = formal_postprocess.PublicationCatalog.from_config
    monkeypatch.setattr(
        formal_postprocess.PublicationCatalog,
        "from_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed formal root reopened publications")
        ),
    )
    reused = run_formal_postprocess(config_path)
    assert reused["resume_status"] == "reused"
    assert render_count == 8
    assert manifest_path.stat().st_mtime_ns == manifest_mtime

    malformed_requests = (
        ("output_root", None, "output_root must be a nonempty path"),
        ("publications", {}, "publications must be a nonempty object"),
        ("styles", [], "styles must be an object"),
        ("resources", [], "resources must be an object"),
    )
    for field, value, message in malformed_requests:
        malformed = dict(changed)
        malformed[field] = value
        config_path.write_text(json.dumps(malformed), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            run_formal_postprocess(config_path)
    config_path.write_text(json.dumps(changed), encoding="utf-8")

    monkeypatch.setattr(
        formal_postprocess.PublicationCatalog,
        "from_config",
        original_catalog_loader,
    )

    invalid = dict(changed)
    invalid["styles"] = []
    config_path.write_text(json.dumps(invalid), encoding="utf-8")
    monkeypatch.setattr(
        formal_postprocess,
        "_trash",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("force trashed output before request admission")
        ),
    )
    with pytest.raises(ValueError, match="styles must be an object"):
        run_formal_postprocess(config_path, force=True)
    config_path.write_text(json.dumps(changed), encoding="utf-8")

    trashed = tmp_path / "trashed_formal_output"

    def move_to_trash(path: Path) -> None:
        path.rename(trashed)

    monkeypatch.setattr(formal_postprocess, "_trash", move_to_trash)
    forced = run_formal_postprocess(config_path, force=True)
    assert forced["status"] == "complete"
    assert render_count == 16
    assert (trashed / "complete.json").is_file()
    assert (output_root / "complete.json").is_file()


def test_formal_postprocess_keeps_all_three_component_families_for_two_scales(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    config_path = _formal_fit_config(tmp_path, "all_components_output")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["components"] = ["paired_fit", "voxel_2d", "fiber_2d"]
    config["resources"] = {
        "background": "background.nii.gz",
        "reference_mask": "reference.nii.gz",
        "addon_mask": "addon.nii.gz",
        "fiber_spatial_config": "fiber.yaml",
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    resolved = []
    for scale_id in ("scale_a", "scale_b"):
        for role, unit, family in (
            ("reference", "voxel", "reference_voxel"),
            ("reference", "fiber", "reference_fiber"),
            ("addon", "voxel", "addon_voxel"),
            ("addon", "fiber", "addon_fiber"),
        ):
            resolved.append(
                {
                    "endpoint_id": f"{scale_id}_{family}",
                    "scale_id": scale_id,
                    "model_role": role,
                    "model_unit": unit,
                    "model_family": family,
                    "final_model_id": f"final_{scale_id}_{family}",
                    "final_branch": "reference" if role == "reference" else "no_delta_reference",
                    "selected_tau": 200 if unit == "voxel" else 400,
                    "selected_coverage": 5,
                    "source_artifacts": {},
                }
            )

    monkeypatch.setattr(
        formal_postprocess, "_resolve_endpoints", lambda **kwargs: resolved
    )
    monkeypatch.setattr(
        formal_postprocess,
        "render_paired_fit_components",
        lambda **kwargs: [
            {
                "status": "complete",
                "scale_id": item["scale_id"],
                "model_family": item["model_family"],
                "result_path": f"fit/{item['endpoint_id']}.json",
                "outputs": [f"fit/{item['endpoint_id']}.png"],
                "metrics": _paired_metrics(),
            }
            for item in resolved
        ],
    )
    monkeypatch.setattr(
        formal_postprocess,
        "_resource_record",
        lambda path, kind: {"path": str(path), "kind": kind},
    )
    monkeypatch.setattr(
        formal_postprocess,
        "render_voxel_section_components",
        lambda **kwargs: [
            {
                "status": "complete",
                "scale_id": scale_id,
                "model_role": role,
                "result_path": f"voxel/{scale_id}/{role}/{index}.json",
                "outputs": [f"voxel/{scale_id}/{role}/{index}.png"],
            }
            for scale_id in ("scale_a", "scale_b")
            for role in ("reference", "addon")
            for index in range(3)
        ],
    )
    monkeypatch.setattr(
        formal_postprocess, "prepare_fiber_section_context", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        formal_postprocess,
        "render_fiber_section_components",
        lambda **kwargs: [
            {
                "status": "complete",
                "scale_id": scale_id,
                "model_role": role,
                "result_path": f"fiber/{scale_id}/{role}.json",
                "outputs": [f"fiber/{scale_id}/{role}.png"],
            }
            for scale_id in ("scale_a", "scale_b")
            for role in ("reference", "addon")
        ],
    )

    result = run_formal_postprocess(config_path)
    assert result["status"] == "complete"
    assert result["completed_count"] == 8
    assert result["failed_count"] == 0
    assert set(result["component_results"]) == {
        "paired_fit",
        "voxel_2d",
        "fiber_2d",
    }
    assert {item["model_unit"]: item["output_count"] for item in result["endpoint_results"]} == {
        "voxel": 4,
        "fiber": 2,
    }
    assert {
        item["model_unit"]: item["component_manifest_count"]
        for item in result["endpoint_results"]
    } == {"voxel": 4, "fiber": 2}


def test_output_validator_allows_zero_components_for_inapplicable_model_unit(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "voxel_only_output"
    output_root.mkdir()
    voxel_rows = []
    for index in range(3):
        voxel_output = (
            f"scales/scale_a/reference/voxel/benefit_map_{index}_data.json"
        )
        voxel_manifest = (
            f"scales/scale_a/reference/voxel/benefit_map_{index}_sections.json"
        )
        formal_postprocess._write_json_atomic(
            output_root / voxel_output,
            {"value": index},
        )
        voxel_row = {
            "status": "complete",
            "scale_id": "scale_a",
            "model_role": "reference",
            "model_family": "reference_voxel",
            "result_path": voxel_manifest,
            "outputs": [voxel_output],
        }
        voxel_rows.append(voxel_row)
        formal_postprocess._write_json_atomic(
            output_root / voxel_manifest,
            voxel_row,
        )
        formal_postprocess._write_json_atomic(
            formal_postprocess._component_completion_marker(
                output_root,
                "voxel_2d",
                voxel_manifest,
            ),
            {"status": "complete"},
        )
    resolved_endpoints = [
        {
            "endpoint_id": "endpoint_voxel",
            "scale_id": "scale_a",
            "model_role": "reference",
            "model_unit": "voxel",
            "model_family": "reference_voxel",
            "final_model_id": "final_voxel",
            "final_branch": "reference",
            "selected_tau": 200,
            "selected_coverage": 5,
        },
        {
            "endpoint_id": "endpoint_fiber",
            "scale_id": "scale_a",
            "model_role": "reference",
            "model_unit": "fiber",
            "model_family": "reference_fiber",
            "final_model_id": "final_fiber",
            "final_branch": "reference",
            "selected_tau": 400,
            "selected_coverage": 5,
        },
    ]
    endpoint_results = formal_postprocess._assemble_endpoint_results(
        resolved=resolved_endpoints,
        components=["voxel_2d"],
        paired=[],
        voxel=voxel_rows,
        fiber=[],
    )
    assert {
        item["model_unit"]: item["component_manifest_count"]
        for item in endpoint_results
    } == {"voxel": 3, "fiber": 0}
    formal_postprocess._write_json_atomic(
        output_root / "request.json",
        {"schema_version": formal_postprocess.SCHEMA_VERSION},
    )
    formal_postprocess._write_json_atomic(
        output_root / "resolved_request.json",
        {
            "schema_version": formal_postprocess.SCHEMA_VERSION,
            "components": ["voxel_2d"],
            "endpoint_count": 2,
            "endpoints": resolved_endpoints,
        },
    )
    formal_postprocess._write_json_atomic(
        output_root / "manifest.json",
        {
            "schema_version": formal_postprocess.SCHEMA_VERSION,
            "status": "complete",
            "endpoint_count": 2,
            "completed_count": 2,
            "failed_count": 0,
            "components": ["voxel_2d"],
            "component_results": {"voxel_2d": voxel_rows},
            "endpoint_results": endpoint_results,
        },
    )
    formal_postprocess._write_json_atomic(
        output_root / "complete.json",
        {"status": "complete"},
    )
    formal_postprocess._write_endpoint_index(output_root, endpoint_results)
    formal_postprocess._write_readme(
        output_root,
        ["scale_a"],
        ["voxel_2d"],
    )

    terminal = validate_formal_postprocess_output(output_root)

    assert terminal["status"] == "valid"
    assert terminal["endpoint_count"] == 2
    assert terminal["declared_output_count"] == 3
    assert terminal["component_manifest_count"] == 3


def test_declared_pdf_requires_successful_poppler_parse_and_arial(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "figure.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(formal_postprocess.shutil, "which", lambda name: "/pdffonts")
    monkeypatch.setattr(
        formal_postprocess.subprocess,
        "run",
        lambda *args, **kwargs: formal_postprocess.subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ABCDEF+ArialMT TrueType", stderr=""
        ),
    )
    formal_postprocess._validate_declared_output(path)

    monkeypatch.setattr(
        formal_postprocess.subprocess,
        "run",
        lambda *args, **kwargs: formal_postprocess.subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ABCDEF+Helvetica TrueType", stderr=""
        ),
    )
    with pytest.raises(ValueError, match="lacks an Arial-family font"):
        formal_postprocess._validate_declared_output(path)
