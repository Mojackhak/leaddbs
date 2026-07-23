"""Publish human-readable paired in-sample and LOOCV fit figures for one scale."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .model_fit import plot_in_sample_loocv_fit
from .plugin.default import get_fit_cfg
from .published_artifacts import PublicationCatalog, PublishedArtifact


SCHEMA_VERSION = "dual_frequency_paired_fit_postprocess_v1"


@dataclass(frozen=True)
class _ModelSpec:
    role: str
    unit: str
    model_family: str
    main_publication: str
    in_sample_publication: str


_MODEL_SPECS = (
    _ModelSpec(
        role="reference",
        unit="voxel",
        model_family="reference_voxel",
        main_publication="direct_voxel_main",
        in_sample_publication="direct_voxel_in_sample",
    ),
    _ModelSpec(
        role="reference",
        unit="fiber",
        model_family="reference_fiber",
        main_publication="normative_fiber_main",
        in_sample_publication="normative_fiber_in_sample",
    ),
    _ModelSpec(
        role="addon",
        unit="voxel",
        model_family="addon_voxel",
        main_publication="direct_voxel_main",
        in_sample_publication="direct_voxel_in_sample",
    ),
    _ModelSpec(
        role="addon",
        unit="fiber",
        model_family="addon_fiber",
        main_publication="normative_fiber_main",
        in_sample_publication="normative_fiber_in_sample",
    ),
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scientific_metrics(summary: Mapping[str, Any]) -> dict[str, Any]:
    prefixes = ("in_sample_", "loocv_")
    suffixes = ("_optimism_gap", "_q2_gap")
    return {
        key: value
        for key, value in summary.items()
        if key.startswith(prefixes) or key.endswith(suffixes)
    }


def _validate_endpoint(
    spec: _ModelSpec,
    scale_id: str,
    final_model: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    if str(summary.get("technical_status", "")).lower() not in {
        "complete",
        "completed",
    }:
        raise ValueError(f"final-in-sample summary is not complete: {spec.model_family}")
    if str(final_model.get("final_status", "")).lower() not in {
        "complete",
        "completed",
        "final_model_realized",
    }:
        raise ValueError(f"final model is not complete: {spec.model_family}")
    expected = {
        "scale_id": scale_id,
        "model_family": spec.model_family,
    }
    for key, value in expected.items():
        if str(summary.get(key)) != str(value):
            raise ValueError(
                f"published summary {key} mismatch for {spec.model_family}: "
                f"{summary.get(key)!r} versus {value!r}"
            )
    final_tau = final_model.get("selected_tau_v_per_m")
    final_coverage = final_model.get("selected_coverage_subjects_min")
    if float(summary.get("selected_tau")) != float(final_tau):
        raise ValueError(f"selected tau mismatch for {spec.model_family}")
    if int(summary.get("selected_coverage")) != int(final_coverage):
        raise ValueError(f"selected Coverage mismatch for {spec.model_family}")
    final_branch = final_model.get(
        "realized_final_branch", final_model.get("final_branch")
    )
    if str(summary.get("final_branch")) != str(final_branch):
        raise ValueError(f"final branch mismatch for {spec.model_family}")
    final_model_id = final_model.get("final_model_id")
    if final_model_id is not None and str(summary.get("final_model_id")) != str(
        final_model_id
    ):
        raise ValueError(f"final model ID mismatch for {spec.model_family}")


def _references(scale_id: str, spec: _ModelSpec) -> dict[str, dict[str, str]]:
    base = f"{scale_id}/{spec.role}"
    return {
        "final_model": {
            "publication": spec.main_publication,
            "relative_path": f"{base}/final_model.json",
        },
        "summary": {
            "publication": spec.in_sample_publication,
            "relative_path": f"{base}/sensitivity/final_in_sample/summary.json",
        },
        "predictions": {
            "publication": spec.in_sample_publication,
            "relative_path": f"{base}/sensitivity/final_in_sample/predictions.csv",
        },
    }


def _resolve_sources(
    catalog: PublicationCatalog,
    references: Mapping[str, object],
) -> dict[str, PublishedArtifact]:
    return {name: catalog.resolve(reference) for name, reference in references.items()}


def _relative_outputs(
    output_root: Path, leaf: Path, formats: Sequence[str]
) -> tuple[list[Path], list[str]]:
    normalized = tuple(str(item).lower().lstrip(".") for item in formats)
    invalid = sorted(set(normalized) - {"png", "pdf", "svg"})
    if invalid:
        raise ValueError(f"unsupported paired-fit output formats: {invalid}")
    paths = [leaf / f"in_sample_loocv_fit.{extension}" for extension in normalized]
    relative = [path.relative_to(output_root).as_posix() for path in paths]
    return paths, relative


def _is_reusable(result_path: Path, request_hash: str, output_root: Path) -> bool:
    if not result_path.is_file():
        return False
    try:
        result = _read_json(result_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if result.get("status") != "complete" or result.get("request_hash") != request_hash:
        return False
    outputs = result.get("outputs")
    return isinstance(outputs, list) and all(
        (output_root / str(relative)).is_file() for relative in outputs
    )


def _write_index(output_root: Path, items: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "status",
        "scale_id",
        "model_role",
        "model_unit",
        "model_family",
        "endpoint_id",
        "final_model_id",
        "final_branch",
        "selected_tau",
        "selected_coverage",
        "in_sample_n_subjects_finite",
        "in_sample_spearman_rho",
        "in_sample_spearman_nominal_p",
        "in_sample_permutation_p_plus_one_two_sided",
        "in_sample_permutation_q_bh_model_family",
        "loocv_spearman_rho",
        "loocv_spearman_nominal_p",
        "loocv_permutation_p_plus_one_two_sided",
        "loocv_permutation_q_bh_model_family",
        "result_path",
    )
    temporary = output_root / "endpoint_index.csv.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            metrics = item.get("metrics", {})
            writer.writerow(
                {
                    key: (
                        metrics.get(key)
                        if key.startswith(("in_sample_", "loocv_"))
                        else item.get(key)
                    )
                    for key in fields
                }
            )
    temporary.replace(output_root / "endpoint_index.csv")


def _write_readme(output_root: Path, scale_id: str) -> None:
    text = f"""# Paired In-Sample and LOOCV Fit Postprocess

This fit-only postprocess contains the four completed final models for
`{scale_id}`. It does not contain spatial visualization or results from another
scale. Scientific values come from completed canonical publications and are not
recomputed here.

Browse the results under:

```text
scales/{scale_id}/reference/voxel/
scales/{scale_id}/reference/fiber/
scales/{scale_id}/addon/voxel/
scales/{scale_id}/addon/fiber/
```

Each directory contains PNG and PDF figures plus `result.json`. The root
`endpoint_index.csv` provides a compact cross-model statistical index.
"""
    (output_root / "README.md").write_text(text, encoding="utf-8")


def render_paired_fit_components(
    *,
    scale_ids: Sequence[str],
    output_root: str | Path,
    catalog: PublicationCatalog,
    style: Mapping[str, Any],
    result_filename: str = "in_sample_loocv_fit.json",
    force: bool = False,
) -> list[dict[str, Any]]:
    """Render paired-fit endpoint components without writing root metadata."""

    root = Path(output_root).expanduser().resolve()
    normalized_scales = tuple(str(value).strip() for value in scale_ids)
    if not normalized_scales:
        raise ValueError("scale_ids must contain at least one scale")
    if len(set(normalized_scales)) != len(normalized_scales):
        raise ValueError("scale_ids must not contain duplicates")
    if Path(result_filename).name != result_filename or not result_filename.endswith(
        ".json"
    ):
        raise ValueError("result_filename must be one JSON filename")
    for scale_id in normalized_scales:
        if not scale_id or "/" in scale_id or ".." in scale_id:
            raise ValueError("every scale_id must be one safe path component")

    results: list[dict[str, Any]] = []
    for scale_id in normalized_scales:
        for spec in _MODEL_SPECS:
            leaf = root / "scales" / scale_id / spec.role / spec.unit
            result_path = leaf / result_filename
            item: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "status": "running",
                "scale_id": scale_id,
                "model_role": spec.role,
                "model_unit": spec.unit,
                "model_family": spec.model_family,
                "result_path": result_path.relative_to(root).as_posix(),
            }
            try:
                references = _references(scale_id, spec)
                sources = _resolve_sources(catalog, references)
                source_records = {
                    name: artifact.as_manifest_record()
                    for name, artifact in sources.items()
                }
                final_model = _read_json(sources["final_model"].path)
                summary = _read_json(sources["summary"].path)
                _validate_endpoint(spec, scale_id, final_model, summary)
                request_hash = _payload_hash(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "scale_id": scale_id,
                        "model_family": spec.model_family,
                        "sources": source_records,
                        "style": dict(style),
                    }
                )
                item["request_hash"] = request_hash
                if not force and _is_reusable(result_path, request_hash, root):
                    restored = _read_json(result_path)
                    restored["resume_status"] = "reused"
                    results.append(restored)
                    continue

                subjects = pd.read_csv(sources["predictions"].path)
                output_paths, relative_outputs = _relative_outputs(
                    root, leaf, style["formats"]
                )
                figure = plot_in_sample_loocv_fit(
                    subjects,
                    summary,
                    style_config=style,
                    output_paths=output_paths,
                )
                plt.close(figure)
                item.update(
                    {
                        "status": "complete",
                        "endpoint_id": summary.get("endpoint_id"),
                        "final_model_id": summary.get("final_model_id"),
                        "final_branch": summary.get("final_branch"),
                        "selected_tau": summary.get("selected_tau"),
                        "selected_coverage": summary.get("selected_coverage"),
                        "metrics": _scientific_metrics(summary),
                        "outputs": relative_outputs,
                        "source_artifacts": source_records,
                        "style": dict(style),
                    }
                )
            except Exception as error:  # noqa: BLE001 - model-local failure is intentional
                item.update(
                    {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                )
            _write_json_atomic(result_path, item)
            results.append(item)
    return results


def run_single_scale_paired_fit_postprocess(
    *,
    scale_id: str,
    output_root: str | Path,
    publications: Mapping[str, object],
    style_overrides: Mapping[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Render the four paired-fit figures for one explicit published scale."""

    normalized_scale = str(scale_id).strip()
    if not normalized_scale or "/" in normalized_scale or ".." in normalized_scale:
        raise ValueError("scale_id must be one safe path component")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    catalog = PublicationCatalog.from_config(publications, config_base=root)
    style = get_fit_cfg(style_overrides)
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "scale_id": normalized_scale,
        "style": style,
        "publications": catalog.publication_records(),
        "results": [],
    }
    _write_json_atomic(manifest_path, manifest)

    manifest["results"] = render_paired_fit_components(
        scale_ids=(normalized_scale,),
        output_root=root,
        catalog=catalog,
        style=style,
        result_filename="result.json",
        force=force,
    )
    failures = sum(item.get("status") != "complete" for item in manifest["results"])

    manifest["status"] = "complete" if failures == 0 else "completed_with_failures"
    manifest["completed_count"] = sum(
        item.get("status") == "complete" for item in manifest["results"]
    )
    manifest["reused_count"] = sum(
        item.get("resume_status") == "reused" for item in manifest["results"]
    )
    manifest["failed_count"] = failures
    _write_json_atomic(manifest_path, manifest)
    _write_index(root, manifest["results"])
    _write_readme(root, normalized_scale)
    return manifest


def _publication_arguments(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    return {
        "direct_voxel_main": {
            "root": args.direct_voxel_root,
            "manifest": "model_manifest.json",
        },
        "direct_voxel_in_sample": {
            "root": args.direct_voxel_extension_root,
            "manifest": "extension_manifest.json",
        },
        "normative_fiber_main": {
            "root": args.normative_fiber_root,
            "manifest": "model_manifest.json",
        },
        "normative_fiber_in_sample": {
            "root": args.normative_fiber_extension_root,
            "manifest": "extension_manifest.json",
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--direct-voxel-root", required=True)
    parser.add_argument("--direct-voxel-extension-root", required=True)
    parser.add_argument("--normative-fiber-root", required=True)
    parser.add_argument("--normative-fiber-extension-root", required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_single_scale_paired_fit_postprocess(
        scale_id=args.scale_id,
        output_root=args.output_root,
        publications=_publication_arguments(args),
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "render_paired_fit_components",
    "run_single_scale_paired_fit_postprocess",
]
