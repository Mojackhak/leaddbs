from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from my_helper.fiber.core.viz import formal_postprocess
from my_helper.fiber.core.viz import paired_fit_postprocess
from my_helper.fiber.core.viz.formal_postprocess import (
    run_formal_postprocess,
    validate_formal_postprocess,
    validate_formal_postprocess_output,
)
from my_helper.fiber.core.viz.paired_fit_postprocess import (
    render_paired_fit_components,
)
from my_helper.fiber.core.viz.plugin.default import get_fit_cfg
from my_helper.fiber.core.viz.published_artifacts import PublicationCatalog


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                        "in_sample_spearman_rho": 0.5,
                        "loocv_spearman_rho": 0.3,
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
    return PublicationCatalog.from_config(
        {
            alias: {
                "root": str(root),
                "manifest": (
                    "extension_manifest.json"
                    if alias.endswith("in_sample")
                    else "model_manifest.json"
                ),
            }
            for alias, root in roots.items()
        },
        config_base=tmp_path,
    )


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
        assert (result_path.parent / "in_sample_loocv_fit.png").is_file()

    second = render_paired_fit_components(
        scale_ids=("scale_a", "scale_b"),
        output_root=output_root,
        catalog=catalog,
        style=style,
    )
    assert len(second) == 8
    assert all(item.get("resume_status") == "reused" for item in second)


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
    assert (output_root / "request.json").is_file()
    assert (output_root / "resolved_request.json").is_file()
    assert (output_root / "endpoint_index.csv").is_file()
    assert (output_root / "README.md").is_file()
    assert (output_root / "manifest.json").is_file()
    assert all(
        item["status"] == "complete" for item in first["endpoint_results"]
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


def test_formal_postprocess_rejects_changed_request_in_existing_root(
    tmp_path: Path, monkeypatch
) -> None:
    _paired_fit_catalog(tmp_path)
    config_path = _formal_fit_config(tmp_path, "immutable_output")

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
    run_formal_postprocess(config_path)
    changed = json.loads(config_path.read_text(encoding="utf-8"))
    changed["styles"]["paired_fit"]["dpi"] = 96
    config_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ValueError, match="immutable postprocess request changed"):
        run_formal_postprocess(config_path)


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
