"""Manifest-driven endpoint visualization postprocessor."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .model_fit import plot_in_sample_loocv_fit
from .published_artifacts import PublicationCatalog, PublishedArtifact
from .spatial import SpatialLayer, plot_sweet_sour_slices

SCHEMA_VERSION = "dual_frequency_postprocess_v2"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_path(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _summary(
    endpoint: Mapping[str, Any], publications: PublicationCatalog
) -> dict[str, Any]:
    if "summary" in endpoint:
        raise ValueError("inline scientific summaries are forbidden")
    summary_json = endpoint.get("summary_json")
    if summary_json is None:
        raise ValueError("endpoint requires a published summary_json artifact")
    return _read_json(publications.resolve(summary_json).path)


def _scientific_sources(
    endpoint: Mapping[str, Any], publications: PublicationCatalog
) -> list[PublishedArtifact]:
    references: list[object] = []
    if "summary" in endpoint:
        raise ValueError("inline scientific summaries are forbidden")
    references.append(endpoint.get("summary_json"))
    spatial = endpoint.get("spatial_2d")
    if spatial is not None:
        if not isinstance(spatial, Mapping):
            raise ValueError("spatial_2d must be an object")
        references.extend((spatial.get("sweet_image"), spatial.get("sour_image")))
    statistics = endpoint.get("statistics")
    if statistics is not None:
        if not isinstance(statistics, Mapping):
            raise ValueError("statistics must be an object")
        references.append(statistics.get("subject_table"))
    if any(reference is None for reference in references):
        raise ValueError("every scientific postprocess input requires a publication reference")
    unique: dict[tuple[str, str], PublishedArtifact] = {}
    for reference in references:
        artifact = publications.resolve(reference)
        unique[(artifact.publication, artifact.relative_path)] = artifact
    return [unique[key] for key in sorted(unique)]


def _output_paths(directory: Path, stem: str, formats: Sequence[str]) -> list[Path]:
    normalized = [str(item).lower().lstrip(".") for item in formats]
    allowed = {"png", "pdf", "svg"}
    invalid = sorted(set(normalized) - allowed)
    if invalid:
        raise ValueError(f"unsupported output formats: {invalid}")
    return [directory / f"{stem}.{extension}" for extension in normalized]


def _completed_reusable(manifest_path: Path, request_hash: str) -> bool:
    if not manifest_path.is_file():
        return False
    try:
        payload = _read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if payload.get("status") != "complete" or payload.get("request_hash") != request_hash:
        return False
    outputs = payload.get("outputs")
    return isinstance(outputs, list) and all(Path(item).is_file() for item in outputs)


def _atlas_layers(specs: Sequence[Mapping[str, Any]], base: Path) -> list[SpatialLayer]:
    layers: list[SpatialLayer] = []
    for spec in specs:
        layers.append(
            SpatialLayer(
                image=_resolve_path(base, spec["image"]),
                label=str(spec["label"]),
                color=str(spec.get("color", "#606060")),
                threshold=float(spec.get("threshold", 0.5)),
                alpha=float(spec.get("alpha", 0.65)),
                sampling_order=int(spec.get("sampling_order", 0)),
                outline_only=True,
                linewidth=float(spec.get("linewidth", 0.8)),
            )
        )
    return layers


def _run_statistics(
    endpoint: Mapping[str, Any],
    summary: Mapping[str, Any],
    publications: PublicationCatalog,
    endpoint_dir: Path,
    defaults: Mapping[str, Any],
) -> list[Path]:
    spec = endpoint.get("statistics")
    if spec is None:
        return []
    if not isinstance(spec, Mapping):
        raise ValueError("statistics must be an object")
    table_path = publications.resolve(spec["subject_table"]).path
    table = pd.read_csv(table_path)
    formats = spec.get("formats", defaults.get("formats", ["png", "pdf"]))
    output_dir = endpoint_dir / "statistics"
    paths = _output_paths(output_dir, "in_sample_loocv_fit", formats)
    figure = plot_in_sample_loocv_fit(
        table,
        summary,
        subject_id_column=str(spec.get("subject_id_column", "subject_id")),
        outcome_column=str(spec.get("outcome_column", "outcome")),
        in_sample_column=str(spec.get("in_sample_column", "in_sample_prediction")),
        loocv_column=str(spec.get("loocv_column", "loocv_prediction")),
        boxsize=tuple(spec.get("boxsize", defaults.get("fit_boxsize", [48.0, 42.0]))),
        panel_gap=tuple(spec.get("panel_gap", defaults.get("panel_gap", [6.0, 3.0]))),
        dpi=int(spec.get("dpi", defaults.get("dpi", 300))),
        output_paths=paths,
        transparent=bool(spec.get("transparent", defaults.get("transparent", False))),
    )
    plt.close(figure)
    return paths


def _run_spatial(
    endpoint: Mapping[str, Any],
    publications: PublicationCatalog,
    base: Path,
    endpoint_dir: Path,
    defaults: Mapping[str, Any],
) -> list[Path]:
    spec = endpoint.get("spatial_2d")
    if spec is None:
        return []
    if not isinstance(spec, Mapping):
        raise ValueError("spatial_2d must be an object")
    formats = spec.get("formats", defaults.get("formats", ["png", "pdf"]))
    model_unit = str(spec.get("model_unit", "voxel"))
    if model_unit not in ("voxel", "fiber"):
        raise ValueError("spatial_2d model_unit must be voxel or fiber")
    output_dir = endpoint_dir / "spatial" / model_unit
    paths = _output_paths(output_dir, "sections", formats)
    figure = plot_sweet_sour_slices(
        publications.resolve(spec["sweet_image"]).path,
        publications.resolve(spec["sour_image"]).path,
        background_image=(
            _resolve_path(base, spec["background_image"])
            if spec.get("background_image")
            else None
        ),
        atlas_layers=_atlas_layers(spec.get("atlas_layers", []), base),
        sweet_label=str(spec.get("sweet_label", "Sweet")),
        sour_label=str(spec.get("sour_label", "Sour")),
        sweet_color=str(spec.get("sweet_color", "#C43C4E")),
        sour_color=str(spec.get("sour_color", "#3268A8")),
        sweet_threshold=float(spec.get("sweet_threshold", 0.5)),
        sour_threshold=float(spec.get("sour_threshold", 0.5)),
        sweet_value_mode=str(spec.get("sweet_value_mode", "raw")),
        sour_value_mode=str(spec.get("sour_value_mode", "raw")),
        layer_alpha=float(spec.get("layer_alpha", 0.68)),
        percent_list=tuple(spec.get("percent_list", [25.0, 50.0, 75.0])),
        slice_coordinates_mm=spec.get("slice_coordinates_mm"),
        facets=tuple(spec.get("facets", ["Ax", "Cor", "Sag"])),
        resolution_mm=float(spec.get("resolution_mm", 0.5)),
        boxsize=tuple(spec.get("boxsize", defaults.get("spatial_boxsize", [36.0, 32.0]))),
        panel_gap=tuple(spec.get("panel_gap", defaults.get("panel_gap", [3.0, 3.0]))),
        title=str(spec.get("title", "")) or None,
        dpi=int(spec.get("dpi", defaults.get("dpi", 300))),
        output_paths=paths,
        transparent=bool(spec.get("transparent", defaults.get("transparent", False))),
    )
    plt.close(figure)
    return paths


def run_postprocess(config_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    """Execute a postprocess visualization manifest."""

    config_file = Path(config_path).expanduser().resolve()
    config = _read_json(config_file)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    endpoints = config.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("endpoints must be a nonempty list")
    base = config_file.parent
    publications = PublicationCatalog.from_config(
        config.get("publications"), config_base=base
    )
    output_root = _resolve_path(base, config["output_root"])
    defaults = config.get("defaults", {})
    if not isinstance(defaults, Mapping):
        raise ValueError("defaults must be an object")

    aggregate: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "source_config": str(config_file),
        "publications": publications.publication_records(),
        "endpoints": [],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    aggregate_path = output_root / "manifest.json"
    _write_json_atomic(aggregate_path, aggregate)

    failures = 0
    for endpoint in endpoints:
        if not isinstance(endpoint, Mapping):
            raise ValueError("each endpoint entry must be an object")
        endpoint_id = str(endpoint.get("endpoint_id", "")).strip()
        if not endpoint_id:
            raise ValueError("each endpoint requires endpoint_id")
        endpoint_dir = output_root / "endpoints" / endpoint_id
        endpoint_manifest = endpoint_dir / "manifest.json"
        item: dict[str, Any] = {
            "endpoint_id": endpoint_id,
            "status": "running",
            "outputs": [],
        }
        try:
            source_artifacts = _scientific_sources(endpoint, publications)
            source_records = [item.as_manifest_record() for item in source_artifacts]
            request_hash = _canonical_payload_hash(
                {"endpoint": dict(endpoint), "source_artifacts": source_records}
            )
            if not force and _completed_reusable(endpoint_manifest, request_hash):
                restored = _read_json(endpoint_manifest)
                restored["resume_status"] = "reused"
                aggregate["endpoints"].append(restored)
                continue
            item.update(
                {
                    "request_hash": request_hash,
                    "source_artifacts": source_records,
                }
            )
            _write_json_atomic(endpoint_manifest, item)
            summary = _summary(endpoint, publications)
            summary_endpoint_id = summary.get("endpoint_id")
            if summary_endpoint_id is not None and str(summary_endpoint_id) != endpoint_id:
                raise ValueError(
                    "endpoint_id does not match the endpoint summary: "
                    f"{endpoint_id!r} versus {summary_endpoint_id!r}"
                )
            outputs = [
                *_run_spatial(endpoint, publications, base, endpoint_dir, defaults),
                *_run_statistics(
                    endpoint, summary, publications, endpoint_dir, defaults
                ),
            ]
            if not outputs:
                raise ValueError("endpoint contains neither spatial_2d nor statistics work")
            item.update(
                {
                    "status": "complete",
                    "outputs": [str(path) for path in outputs],
                    "final_model_key": {
                        key: summary.get(key)
                        for key in (
                            "endpoint_id",
                            "scale_id",
                            "model_family",
                            "final_model_id",
                            "selected_tau",
                            "selected_coverage",
                            "final_branch",
                        )
                    },
                }
            )
        except Exception as error:  # noqa: BLE001 - item-local failure boundary is intentional
            failures += 1
            item.setdefault("request_hash", _canonical_payload_hash(endpoint))
            item.update(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
        _write_json_atomic(endpoint_manifest, item)
        aggregate["endpoints"].append(item)
        _write_json_atomic(aggregate_path, aggregate)

    aggregate["status"] = "complete" if failures == 0 else "completed_with_failures"
    aggregate["completed_count"] = sum(item.get("status") == "complete" for item in aggregate["endpoints"])
    aggregate["reused_count"] = sum(item.get("resume_status") == "reused" for item in aggregate["endpoints"])
    aggregate["failed_count"] = failures
    _write_json_atomic(aggregate_path, aggregate)
    return aggregate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="postprocess JSON manifest")
    parser.add_argument("--force", action="store_true", help="regenerate completed outputs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_postprocess(args.config, force=args.force)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "run_postprocess"]
