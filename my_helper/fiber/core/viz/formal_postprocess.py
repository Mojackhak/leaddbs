"""Run the all-scale postprocess transaction from canonical publications."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
from PIL import Image

from .fiber_section_postprocess import (
    prepare_fiber_section_context,
    render_fiber_section_components,
)
from .paired_fit_postprocess import render_paired_fit_components
from .plugin.default import get_fiber_section_cfg, get_fit_cfg, get_voxel_section_cfg
from .published_artifacts import PublicationCatalog, PublishedArtifact
from .voxel_section_postprocess import (
    _resource_record,
    render_voxel_section_components,
)


SCHEMA_VERSION = "dual_frequency_formal_postprocess_v1"
_COMPONENTS = frozenset({"paired_fit", "voxel_2d", "fiber_2d"})
_SAFE_SCALE = re.compile(r"^[^/]+$")


@dataclass(frozen=True)
class _ModelSpec:
    role: str
    unit: str
    model_family: str
    main_publication: str
    in_sample_publication: str


_MODEL_SPECS = (
    _ModelSpec(
        "reference",
        "voxel",
        "reference_voxel",
        "direct_voxel_main",
        "direct_voxel_in_sample",
    ),
    _ModelSpec(
        "reference",
        "fiber",
        "reference_fiber",
        "normative_fiber_main",
        "normative_fiber_in_sample",
    ),
    _ModelSpec(
        "addon",
        "voxel",
        "addon_voxel",
        "direct_voxel_main",
        "direct_voxel_in_sample",
    ),
    _ModelSpec(
        "addon",
        "fiber",
        "addon_fiber",
        "normative_fiber_main",
        "normative_fiber_in_sample",
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


def _file_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(block_size):
                digest.update(block)
    except OSError as exc:
        raise ValueError(f"cannot hash postprocess evidence: {path}") from exc
    return digest.hexdigest()


def _resolve_path(base: Path, value: object) -> Path:
    path = Path(str(value)).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _write_or_validate_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_file():
        current = _read_json(path)
        if _payload_hash(current) != _payload_hash(payload):
            raise ValueError(f"immutable postprocess request changed: {path}")
        return
    _write_json_atomic(path, payload)


def _artifact_record(artifact: PublishedArtifact) -> dict[str, Any]:
    record = artifact.as_manifest_record()
    record.pop("publication_root", None)
    return record


def _validate_declared_output(path: Path) -> None:
    """Perform bounded format-aware validation of one declared output."""

    if not path.is_file() or path.stat().st_size < 1:
        raise ValueError(f"formal postprocess declared output is empty: {path}")
    name = path.name.lower()
    if name.endswith(".png"):
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.width < 1 or image.height < 1:
                    raise ValueError("PNG dimensions are empty")
        except Exception as error:  # noqa: BLE001 - format errors are normalized
            raise ValueError(f"formal postprocess PNG is invalid: {path}") from error
        return
    if name.endswith(".pdf"):
        payload = path.read_bytes()
        if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-4096:]:
            raise ValueError(f"formal postprocess PDF envelope is invalid: {path}")
        command = shutil.which("pdffonts")
        if command is None:
            raise ValueError("formal postprocess PDF validation requires pdffonts")
        result = subprocess.run(
            (command, str(path)),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(f"formal postprocess PDF is invalid: {path}")
        if "arial" not in result.stdout.lower():
            raise ValueError(f"formal postprocess PDF lacks an Arial-family font: {path}")
        return
    if name.endswith(".svg"):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as error:
            raise ValueError(f"formal postprocess SVG is invalid: {path}") from error
        if not root.tag.lower().endswith("svg"):
            raise ValueError(f"formal postprocess SVG root differs: {path}")
        return
    if name.endswith(".json"):
        _read_json(path)
        return
    if name.endswith(".csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            if not csv.DictReader(handle).fieldnames:
                raise ValueError(f"formal postprocess CSV header is missing: {path}")
        return
    if name.endswith(".nii") or name.endswith(".nii.gz"):
        try:
            image = nib.load(str(path))
        except Exception as error:  # noqa: BLE001 - loader errors are normalized
            raise ValueError(f"formal postprocess NIfTI is invalid: {path}") from error
        if not image.shape or any(int(value) < 1 for value in image.shape):
            raise ValueError(f"formal postprocess NIfTI shape is empty: {path}")


def _available_scales(catalog: PublicationCatalog, alias: str) -> tuple[str, ...]:
    by_role: dict[str, set[str]] = {"reference": set(), "addon": set()}
    pattern = re.compile(r"^([^/]+)/(reference|addon)/final_model\.json$")
    for relative in catalog.indexed_paths(alias):
        match = pattern.match(relative)
        if match:
            by_role[match.group(2)].add(match.group(1))
    if not by_role["reference"] or by_role["reference"] != by_role["addon"]:
        raise ValueError(f"publication has an incomplete scale-role matrix: {alias}")
    return tuple(sorted(by_role["reference"]))


def _resolve_scales(config: Mapping[str, Any], catalog: PublicationCatalog) -> tuple[str, ...]:
    direct = _available_scales(catalog, "direct_voxel_main")
    fiber = _available_scales(catalog, "normative_fiber_main")
    if direct != fiber:
        raise ValueError("direct-voxel and normative-fiber scale sets differ")
    requested = config.get("scales", "all_available")
    if requested == "all_available":
        return direct
    if not isinstance(requested, list) or not requested:
        raise ValueError("scales must be all_available or a nonempty list")
    scales = tuple(str(value).strip() for value in requested)
    if len(set(scales)) != len(scales):
        raise ValueError("scales must not contain duplicates")
    if any(not value or not _SAFE_SCALE.fullmatch(value) or value == ".." for value in scales):
        raise ValueError("every scale must be one safe path component")
    missing = sorted(set(scales) - set(direct))
    if missing:
        raise ValueError(f"requested scales are absent from publications: {missing}")
    return scales


def _resolve_components(config: Mapping[str, Any]) -> tuple[str, ...]:
    requested = config.get("components", ["paired_fit", "voxel_2d", "fiber_2d"])
    if not isinstance(requested, list) or not requested:
        raise ValueError("components must be a nonempty list")
    components = tuple(str(value) for value in requested)
    if len(set(components)) != len(components):
        raise ValueError("components must not contain duplicates")
    invalid = sorted(set(components) - _COMPONENTS)
    if invalid:
        raise ValueError(f"unsupported formal postprocess components: {invalid}")
    return components


def _validate_render_tooling(
    config: Mapping[str, Any], components: Sequence[str]
) -> dict[str, Any]:
    styles = config.get("styles", {})
    if not isinstance(styles, Mapping):
        raise ValueError("styles must be an object")
    formats: set[str] = set()
    if "paired_fit" in components:
        formats.update(str(value).lower() for value in get_fit_cfg(styles.get("paired_fit"))["formats"])
    if "voxel_2d" in components:
        formats.update(
            str(value).lower()
            for value in get_voxel_section_cfg(styles.get("voxel_2d"))["formats"]
        )
    if "fiber_2d" in components:
        formats.update(
            str(value).lower()
            for value in get_fiber_section_cfg(styles.get("fiber_2d"))["formats"]
        )
    record: dict[str, Any] = {"formats": sorted(formats)}
    if "pdf" in formats:
        pdffonts = shutil.which("pdffonts")
        if pdffonts is None:
            raise ValueError("formal postprocess PDF output requires pdffonts")
        record["pdffonts"] = pdffonts
    return record


def _validate_final_and_summary(
    *,
    scale_id: str,
    spec: _ModelSpec,
    final_model: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    if str(final_model.get("final_status", "")).lower() not in {
        "complete",
        "completed",
        "final_model_realized",
    }:
        raise ValueError(f"final model is incomplete: {scale_id}/{spec.model_family}")
    if str(summary.get("technical_status", "")).lower() not in {
        "complete",
        "completed",
    }:
        raise ValueError(f"in-sample summary is incomplete: {scale_id}/{spec.model_family}")
    expected = {"scale_id": scale_id, "model_family": spec.model_family}
    if final_model.get("final_model_id") is not None:
        expected["final_model_id"] = final_model.get("final_model_id")
    for key, value in expected.items():
        if str(summary.get(key)) != str(value):
            raise ValueError(f"published {key} mismatch: {scale_id}/{spec.model_family}")
    if float(summary.get("selected_tau")) != float(
        final_model.get("selected_tau_v_per_m")
    ):
        raise ValueError(f"selected tau mismatch: {scale_id}/{spec.model_family}")
    if int(summary.get("selected_coverage")) != int(
        final_model.get("selected_coverage_subjects_min")
    ):
        raise ValueError(f"selected Coverage mismatch: {scale_id}/{spec.model_family}")
    final_branch = final_model.get(
        "realized_final_branch", final_model.get("final_branch")
    )
    if str(summary.get("final_branch")) != str(final_branch):
        raise ValueError(f"final branch mismatch: {scale_id}/{spec.model_family}")


def _validated_display_smoothing_metadata(
    artifact: PublishedArtifact,
    *,
    raw_artifact: PublishedArtifact,
    fwhm_mm: float,
) -> PublishedArtifact:
    relative = f"{artifact.relative_path}.metadata.json"
    path = Path(f"{artifact.path}.metadata.json").resolve()
    if artifact.publication_root not in path.parents or not path.is_file():
        raise ValueError(
            f"display smoothing metadata is missing: {artifact.relative_path}"
        )
    metadata = _read_json(path)
    if set(metadata) != {
        "schema_version",
        "artifact_kind",
        "published_relative_path",
        "payload_sha256",
        "size_bytes",
        "provenance",
    }:
        raise ValueError(
            f"display smoothing metadata fields differ: {artifact.relative_path}"
        )
    provenance = metadata.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != {
        "source_record_id",
        "input_relative_path",
        "fwhm_mm",
        "algorithm",
        "support_policy",
        "input_finite_voxels",
        "output_finite_voxels",
    }:
        raise ValueError(
            f"display smoothing provenance fields differ: {artifact.relative_path}"
        )
    input_count = provenance["input_finite_voxels"]
    output_count = provenance["output_finite_voxels"]
    if (
        metadata["schema_version"]
        != "dual_frequency_derived_artifact_metadata_v1"
        or metadata["artifact_kind"] != "benefit_map_smooth"
        or metadata["published_relative_path"] != artifact.relative_path
        or metadata["payload_sha256"] != artifact.sha256
        or type(metadata["size_bytes"]) is not int
        or metadata["size_bytes"] != artifact.size_bytes
        or not str(provenance["source_record_id"]).strip()
        or provenance["input_relative_path"] != raw_artifact.relative_path
        or type(provenance["fwhm_mm"]) not in {int, float}
        or float(provenance["fwhm_mm"]) != fwhm_mm
        or provenance["algorithm"]
        != "masked_normalized_gaussian_original_roi_v2"
        or provenance["support_policy"] != "original_finite_benefit_roi"
        or type(input_count) is not int
        or type(output_count) is not int
        or input_count < 1
        or output_count != input_count
    ):
        raise ValueError(
            f"display smoothing v2 contract differs: {artifact.relative_path}"
        )
    return PublishedArtifact(
        publication=artifact.publication,
        publication_root=artifact.publication_root,
        relative_path=relative,
        path=path,
        sha256=_file_sha256(path),
        size_bytes=path.stat().st_size,
        artifact_kind="benefit_map_smooth_metadata",
    )


def _voxel_spatial_sources(
    catalog: PublicationCatalog,
    *,
    scale_id: str,
    role: str,
    final_model: Mapping[str, Any],
) -> dict[str, PublishedArtifact]:
    paths = final_model.get("artifact_relative_paths")
    if not isinstance(paths, list):
        raise ValueError(f"voxel final model lacks artifact paths: {scale_id}/{role}")
    raw_matches = [str(value) for value in paths if Path(str(value)).name == "benefit_map.nii.gz"]
    if len(raw_matches) != 1:
        raise ValueError(f"voxel final model requires one benefit map: {scale_id}/{role}")
    base = f"{scale_id}/{role}"
    raw = catalog.resolve_relative("direct_voxel_main", raw_matches[0])
    smooth_1 = catalog.resolve_relative(
        "direct_voxel_main",
        f"{base}/report/display/benefit_map_smooth_fwhm1mm.nii.gz",
    )
    smooth_2 = catalog.resolve_relative(
        "direct_voxel_main",
        f"{base}/report/display/benefit_map_smooth_fwhm2mm.nii.gz",
    )
    return {
        "report_summary": catalog.resolve_relative(
            "direct_voxel_main", f"{base}/report/summary.json"
        ),
        "benefit_map": raw,
        "benefit_map_smooth_fwhm1mm": smooth_1,
        "benefit_map_smooth_fwhm1mm_metadata": (
            _validated_display_smoothing_metadata(
                smooth_1,
                raw_artifact=raw,
                fwhm_mm=1.0,
            )
        ),
        "benefit_map_smooth_fwhm2mm": smooth_2,
        "benefit_map_smooth_fwhm2mm_metadata": (
            _validated_display_smoothing_metadata(
                smooth_2,
                raw_artifact=raw,
                fwhm_mm=2.0,
            )
        ),
    }


def _fiber_spatial_sources(
    catalog: PublicationCatalog,
    *,
    final_model: Mapping[str, Any],
) -> dict[str, PublishedArtifact]:
    resolver_relative = str(final_model.get("resolver_relative_path", ""))
    valid_relative = str(final_model.get("valid_feature_axis_relative_path", ""))
    if not resolver_relative or not valid_relative:
        raise ValueError("fiber final model lacks resolver or valid-axis path")
    resolver_dir = Path(resolver_relative).parent
    return {
        "source_selection": catalog.resolve_relative(
            "normative_fiber_main", resolver_relative
        ),
        "valid_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", valid_relative
        ),
        "full_weights": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "full_weights.npy"
        ),
        "selected_sweet_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "selected_sweet_fiber_ids.npy"
        ),
        "selected_sour_fiber_ids": catalog.resolve_relative(
            "normative_fiber_main", resolver_dir / "selected_sour_fiber_ids.npy"
        ),
    }


def _resolve_endpoints(
    *,
    scales: Sequence[str],
    components: Sequence[str],
    catalog: PublicationCatalog,
) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    endpoint_ids: set[str] = set()
    for scale_id in scales:
        for spec in _MODEL_SPECS:
            base = f"{scale_id}/{spec.role}"
            core = {
                "final_model": catalog.resolve_relative(
                    spec.main_publication, f"{base}/final_model.json"
                ),
                "summary": catalog.resolve_relative(
                    spec.in_sample_publication,
                    f"{base}/sensitivity/final_in_sample/summary.json",
                ),
                "predictions": catalog.resolve_relative(
                    spec.in_sample_publication,
                    f"{base}/sensitivity/final_in_sample/predictions.csv",
                ),
            }
            final_model = _read_json(core["final_model"].path)
            summary = _read_json(core["summary"].path)
            _validate_final_and_summary(
                scale_id=scale_id,
                spec=spec,
                final_model=final_model,
                summary=summary,
            )
            endpoint_id = str(summary.get("endpoint_id", "")).strip()
            if not endpoint_id or endpoint_id in endpoint_ids:
                raise ValueError(f"endpoint identity is missing or duplicated: {endpoint_id!r}")
            endpoint_ids.add(endpoint_id)
            sources = dict(core)
            if spec.unit == "voxel" and "voxel_2d" in components:
                sources.update(
                    _voxel_spatial_sources(
                        catalog,
                        scale_id=scale_id,
                        role=spec.role,
                        final_model=final_model,
                    )
                )
            if spec.unit == "fiber" and "fiber_2d" in components:
                sources.update(
                    _fiber_spatial_sources(catalog, final_model=final_model)
                )
            endpoints.append(
                {
                    "endpoint_id": endpoint_id,
                    "scale_id": scale_id,
                    "model_role": spec.role,
                    "model_unit": spec.unit,
                    "model_family": spec.model_family,
                    "final_model_id": final_model.get(
                        "final_model_id", summary.get("final_model_id")
                    ),
                    "final_branch": final_model.get(
                        "realized_final_branch", final_model.get("final_branch")
                    ),
                    "selected_tau": final_model.get("selected_tau_v_per_m"),
                    "selected_coverage": final_model.get(
                        "selected_coverage_subjects_min"
                    ),
                    "source_artifacts": {
                        name: _artifact_record(artifact)
                        for name, artifact in sorted(sources.items())
                    },
                }
            )
    return endpoints


def _component_failure_rows(
    *,
    endpoints: Sequence[Mapping[str, Any]],
    unit: str,
    error: Exception,
) -> list[dict[str, Any]]:
    return [
        {
            "status": "failed",
            "scale_id": item["scale_id"],
            "model_role": item["model_role"],
            "model_unit": unit,
            "model_family": item["model_family"],
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        for item in endpoints
        if item["model_unit"] == unit
    ]


def _write_endpoint_index(root: Path, endpoints: Sequence[Mapping[str, Any]]) -> None:
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
        "paired_fit_status",
        "spatial_status",
        "component_manifest_count",
        "output_count",
    )
    temporary = root / "endpoint_index.csv.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in endpoints:
            writer.writerow({key: item.get(key) for key in fields})
    temporary.replace(root / "endpoint_index.csv")


def _write_readme(root: Path, scales: Sequence[str], components: Sequence[str]) -> None:
    text = f"""# Formal Dual-Frequency Postprocess

This self-contained index renders canonical publication artifacts only. It
contains {len(scales)} scales and the requested components
{', '.join(components)}. Scientific inputs remain in their canonical
publications; endpoint result JSON files bind their relative paths and hashes.

Browse endpoint outputs below `scales/<scale-id>/<role>/<unit>/` and use
`endpoint_index.csv` for the cross-scale status summary.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def _assemble_endpoint_results(
    *,
    resolved: Sequence[Mapping[str, Any]],
    components: Sequence[str],
    paired: Sequence[Mapping[str, Any]],
    voxel: Sequence[Mapping[str, Any]],
    fiber: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    endpoint_results: list[dict[str, Any]] = []
    for source in resolved:
        scale_id = source["scale_id"]
        role = source["model_role"]
        unit = source["model_unit"]
        fit_rows = [
            item
            for item in paired
            if item.get("scale_id") == scale_id
            and item.get("model_family") == source["model_family"]
        ]
        spatial_pool = voxel if unit == "voxel" else fiber
        spatial_rows = [
            item
            for item in spatial_pool
            if item.get("scale_id") == scale_id and item.get("model_role") == role
        ]
        required_fit = "paired_fit" in components
        required_spatial = (
            unit == "voxel" and "voxel_2d" in components
        ) or (unit == "fiber" and "fiber_2d" in components)
        expected_spatial = 3 if unit == "voxel" else 1
        fit_complete = (
            not required_fit
            or (len(fit_rows) == 1 and fit_rows[0].get("status") == "complete")
        )
        spatial_complete = (
            not required_spatial
            or (
                len(spatial_rows) == expected_spatial
                and all(item.get("status") == "complete" for item in spatial_rows)
            )
        )
        outputs: list[str] = []
        component_rows = (*fit_rows, *spatial_rows)
        component_manifests: list[str] = []
        for item in component_rows:
            values = item.get("outputs")
            if isinstance(values, list):
                outputs.extend(str(value) for value in values)
            result_path = item.get("result_path")
            if isinstance(result_path, str) and result_path:
                component_manifests.append(result_path)
        unique_component_manifests = sorted(set(component_manifests))
        manifest_closure = len(unique_component_manifests) == len(component_rows)
        endpoint_results.append(
            {
                **dict(source),
                "status": (
                    "complete"
                    if fit_complete and spatial_complete and manifest_closure
                    else "failed"
                ),
                "paired_fit_status": (
                    "not_requested" if not required_fit else "complete" if fit_complete else "failed"
                ),
                "spatial_status": (
                    "not_requested"
                    if not required_spatial
                    else "complete"
                    if spatial_complete
                    else "failed"
                ),
                "component_manifest_count": len(unique_component_manifests),
                "component_manifests": unique_component_manifests,
                "output_count": len(set(outputs)),
                "outputs": sorted(set(outputs)),
            }
        )
    return endpoint_results


def validate_formal_postprocess(config_path: str | Path) -> dict[str, Any]:
    """Validate formal publications, endpoint closure, and shared resources."""

    config_file = Path(config_path).expanduser().resolve()
    config = _read_json(config_file)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    base = config_file.parent
    catalog = PublicationCatalog.from_config(
        config.get("publications"), config_base=base
    )
    scales = _resolve_scales(config, catalog)
    components = _resolve_components(config)
    tooling = _validate_render_tooling(config, components)
    endpoints = _resolve_endpoints(
        scales=scales, components=components, catalog=catalog
    )
    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        raise ValueError("resources must be an object")
    resource_records: dict[str, Any] = {}
    shared_background = None
    if {"voxel_2d", "fiber_2d"}.intersection(components):
        shared_background = _resource_record(
            _resolve_path(base, resources["background"]), "anatomy_background"
        )
        resource_records["background"] = shared_background
    if "voxel_2d" in components:
        resource_records["reference_mask"] = _resource_record(
            _resolve_path(base, resources["reference_mask"]), "reference_mask"
        )
        resource_records["addon_mask"] = _resource_record(
            _resolve_path(base, resources["addon_mask"]), "addon_mask"
        )
    if "fiber_2d" in components:
        context = prepare_fiber_section_context(
            catalog=catalog,
            spatial_config_path=_resolve_path(
                base, resources["fiber_spatial_config"]
            ),
            background_record=shared_background,
        )
        resource_records["fiber_spatial_config"] = dict(context.config_record)
        resource_records["formal_connectome"] = dict(context.connectome_record)
        resource_records["fiber_background"] = dict(context.background_record)
        resource_records["fiber_target_count"] = len(context.target_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid",
        "output_root": str(_resolve_path(base, config.get("output_root"))),
        "components": list(components),
        "scale_count": len(scales),
        "scales": list(scales),
        "endpoint_count": len(endpoints),
        "publication_count": len(catalog.publication_records()),
        "resources": resource_records,
        "tooling": tooling,
    }


def validate_formal_postprocess_output(output_root: str | Path) -> dict[str, Any]:
    """Validate one terminal formal postprocess output without mutation."""

    root = Path(output_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"formal postprocess output root is missing: {root}")
    request_path = root / "request.json"
    resolved_path = root / "resolved_request.json"
    manifest_path = root / "manifest.json"
    index_path = root / "endpoint_index.csv"
    readme_path = root / "README.md"
    for path in (request_path, resolved_path, manifest_path, index_path, readme_path):
        if not path.is_file():
            raise ValueError(f"formal postprocess root file is missing: {path}")

    request = _read_json(request_path)
    resolved = _read_json(resolved_path)
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("formal postprocess manifest schema differs")
    if manifest.get("status") != "complete":
        raise ValueError("formal postprocess manifest is not terminal complete")
    request_hash = _payload_hash(request)
    if resolved.get("request_hash") != request_hash:
        raise ValueError("formal postprocess request hash differs")
    resolved_without_hash = dict(resolved)
    stored_resolved_hash = resolved_without_hash.pop("resolved_request_hash", None)
    resolved_hash = _payload_hash(resolved_without_hash)
    if stored_resolved_hash != resolved_hash:
        raise ValueError("formal postprocess resolved-request hash differs")
    if manifest.get("request_hash") != request_hash:
        raise ValueError("formal postprocess manifest request hash differs")
    if manifest.get("resolved_request_hash") != resolved_hash:
        raise ValueError("formal postprocess manifest resolved-request hash differs")

    resolved_endpoints = resolved.get("endpoints")
    endpoint_results = manifest.get("endpoint_results")
    if not isinstance(resolved_endpoints, list) or not isinstance(endpoint_results, list):
        raise ValueError("formal postprocess endpoint arrays are missing")
    expected_count = int(resolved.get("endpoint_count", -1))
    if expected_count < 1 or len(resolved_endpoints) != expected_count:
        raise ValueError("formal postprocess resolved endpoint count differs")
    if len(endpoint_results) != expected_count:
        raise ValueError("formal postprocess terminal endpoint count differs")
    if int(manifest.get("endpoint_count", -1)) != expected_count:
        raise ValueError("formal postprocess manifest endpoint count differs")
    if int(manifest.get("completed_count", -1)) != expected_count:
        raise ValueError("formal postprocess completed endpoint count differs")
    if int(manifest.get("failed_count", -1)) > 0:
        raise ValueError("formal postprocess manifest retains failures")

    resolved_ids = [str(item.get("endpoint_id", "")) for item in resolved_endpoints]
    result_ids = [str(item.get("endpoint_id", "")) for item in endpoint_results]
    if any(not value for value in resolved_ids) or len(set(resolved_ids)) != expected_count:
        raise ValueError("formal postprocess resolved endpoint IDs differ")
    if set(result_ids) != set(resolved_ids) or len(set(result_ids)) != expected_count:
        raise ValueError("formal postprocess terminal endpoint IDs differ")

    output_paths: set[str] = set()
    component_manifest_paths: set[str] = set()
    requested_components = resolved.get("components")
    if not isinstance(requested_components, list):
        raise ValueError("formal postprocess resolved components are missing")
    requested_component_set = {str(value) for value in requested_components}
    for item in endpoint_results:
        if item.get("status") != "complete":
            raise ValueError(
                f"formal postprocess endpoint is incomplete: {item.get('endpoint_id')}"
            )
        outputs = item.get("outputs")
        if not isinstance(outputs, list):
            raise ValueError("formal postprocess endpoint outputs are missing")
        component_manifests = item.get("component_manifests")
        if not isinstance(component_manifests, list):
            raise ValueError(
                "formal postprocess endpoint component manifests are missing"
            )
        normalized_manifests = [str(value) for value in component_manifests]
        unit = str(item.get("model_unit", ""))
        expected_manifest_count = int("paired_fit" in requested_component_set)
        if unit == "voxel" and "voxel_2d" in requested_component_set:
            expected_manifest_count += 3
        if unit == "fiber" and "fiber_2d" in requested_component_set:
            expected_manifest_count += 1
        if (
            int(item.get("component_manifest_count", -1))
            != len(normalized_manifests)
            or len(set(normalized_manifests)) != len(normalized_manifests)
            or len(normalized_manifests) != expected_manifest_count
        ):
            raise ValueError(
                "formal postprocess endpoint component manifest count differs"
            )
        if not normalized_manifests:
            raise ValueError(
                "formal postprocess endpoint component manifests are empty"
            )
        for relative_value in normalized_manifests:
            relative = Path(relative_value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(
                    "formal postprocess component manifest path is not contained"
                )
            path = (root / relative).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError(
                    f"formal postprocess component manifest is missing: {path}"
                )
            component = _read_json(path)
            if component.get("status") != "complete":
                raise ValueError(
                    f"formal postprocess component manifest is incomplete: {path}"
                )
            if component.get("scale_id") != item.get("scale_id"):
                raise ValueError(
                    f"formal postprocess component manifest scale differs: {path}"
                )
            if (
                component.get("model_role") is not None
                and component.get("model_role") != item.get("model_role")
            ):
                raise ValueError(
                    f"formal postprocess component manifest role differs: {path}"
                )
            if (
                component.get("model_family") is not None
                and component.get("model_family") != item.get("model_family")
            ):
                raise ValueError(
                    f"formal postprocess component manifest family differs: {path}"
                )
            component_manifest_paths.add(relative.as_posix())
        normalized = {str(value) for value in outputs}
        if int(item.get("output_count", -1)) != len(normalized):
            raise ValueError("formal postprocess endpoint output count differs")
        for relative_value in normalized:
            relative = Path(relative_value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("formal postprocess output path is not contained")
            path = (root / relative).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError(f"formal postprocess declared output is missing: {path}")
            _validate_declared_output(path)
            output_paths.add(relative.as_posix())

    component_results = manifest.get("component_results")
    if not isinstance(component_results, Mapping):
        raise ValueError("formal postprocess component results are missing")
    if {str(value) for value in component_results} != requested_component_set:
        raise ValueError("formal postprocess component result families differ")
    root_component_paths: list[str] = []
    for family in requested_component_set:
        family_rows = component_results.get(family)
        if not isinstance(family_rows, list):
            raise ValueError(
                f"formal postprocess component result family is missing: {family}"
            )
        for row in family_rows:
            if not isinstance(row, Mapping):
                raise ValueError("formal postprocess component result row is invalid")
            result_path = row.get("result_path")
            if not isinstance(result_path, str) or not result_path:
                raise ValueError(
                    "formal postprocess component result path is missing"
                )
            root_component_paths.append(result_path)
    if (
        len(set(root_component_paths)) != len(root_component_paths)
        or set(root_component_paths) != component_manifest_paths
    ):
        raise ValueError("formal postprocess component result closure differs")

    with index_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    index_ids = [str(row.get("endpoint_id", "")) for row in rows]
    if len(rows) != expected_count or set(index_ids) != set(resolved_ids):
        raise ValueError("formal postprocess endpoint index closure differs")
    if any(row.get("status") != "complete" for row in rows):
        raise ValueError("formal postprocess endpoint index retains incomplete rows")
    endpoint_by_id = {str(item["endpoint_id"]): item for item in endpoint_results}
    for row in rows:
        endpoint = endpoint_by_id[str(row["endpoint_id"])]
        if int(row.get("component_manifest_count", -1)) != int(
            endpoint["component_manifest_count"]
        ):
            raise ValueError(
                "formal postprocess endpoint index component count differs"
            )

    forbidden = ("file://", "/.runs/", "/runtime_work/", "/tasks/", "/work/")
    metadata_files = sorted(root.rglob("*.json")) + sorted(root.rglob("*.csv"))
    for path in metadata_files:
        text = path.read_text(encoding="utf-8")
        match = next((value for value in forbidden if value in text), None)
        if match is not None:
            raise ValueError(
                f"formal postprocess metadata contains forbidden path {match}: {path}"
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid",
        "output_root": str(root),
        "endpoint_count": expected_count,
        "declared_output_count": len(output_paths),
        "component_manifest_count": len(component_manifest_paths),
        "metadata_file_count": len(metadata_files),
        "request_hash": request_hash,
        "resolved_request_hash": resolved_hash,
    }


def run_formal_postprocess(
    config_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Execute one all-scale canonical-publication postprocess transaction."""

    config_file = Path(config_path).expanduser().resolve()
    config = _read_json(config_file)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    base = config_file.parent
    components = _resolve_components(config)
    _validate_render_tooling(config, components)
    output_root = _resolve_path(base, config.get("output_root"))
    output_root.mkdir(parents=True, exist_ok=True)
    request_payload = dict(config)
    request_payload["output_root"] = str(output_root)
    _write_or_validate_immutable(output_root / "request.json", request_payload)

    catalog = PublicationCatalog.from_config(
        config.get("publications"), config_base=base
    )
    scales = _resolve_scales(config, catalog)
    resolved_endpoints = _resolve_endpoints(
        scales=scales, components=components, catalog=catalog
    )
    resolved_payload = {
        "schema_version": SCHEMA_VERSION,
        "request_hash": _payload_hash(request_payload),
        "publications": catalog.publication_records(),
        "components": list(components),
        "scales": list(scales),
        "endpoint_count": len(resolved_endpoints),
        "endpoints": resolved_endpoints,
    }
    resolved_payload["resolved_request_hash"] = _payload_hash(resolved_payload)
    _write_or_validate_immutable(
        output_root / "resolved_request.json", resolved_payload
    )

    manifest_path = output_root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "request_hash": resolved_payload["request_hash"],
        "resolved_request_hash": resolved_payload["resolved_request_hash"],
        "scale_count": len(scales),
        "endpoint_count": len(resolved_endpoints),
        "components": list(components),
        "component_results": {},
    }
    _write_json_atomic(manifest_path, manifest)

    styles = config.get("styles", {})
    if not isinstance(styles, Mapping):
        raise ValueError("styles must be an object")
    paired_results: list[dict[str, Any]] = []
    voxel_results: list[dict[str, Any]] = []
    fiber_results: list[dict[str, Any]] = []

    if "paired_fit" in components:
        paired_results = render_paired_fit_components(
            scale_ids=scales,
            output_root=output_root,
            catalog=catalog,
            style=get_fit_cfg(styles.get("paired_fit")),
            force=force,
        )
        manifest["component_results"]["paired_fit"] = paired_results
        _write_json_atomic(manifest_path, manifest)

    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        raise ValueError("resources must be an object")
    shared_background = None
    if {"voxel_2d", "fiber_2d"}.intersection(components):
        try:
            shared_background = _resource_record(
                _resolve_path(base, resources["background"]),
                "anatomy_background",
            )
        except Exception as error:  # noqa: BLE001 - spatial failures remain isolated
            if "voxel_2d" in components:
                voxel_results = _component_failure_rows(
                    endpoints=resolved_endpoints, unit="voxel", error=error
                )
            if "fiber_2d" in components:
                fiber_results = _component_failure_rows(
                    endpoints=resolved_endpoints, unit="fiber", error=error
                )

    if "voxel_2d" in components:
        if not voxel_results:
            try:
                voxel_resources = {
                    "background": shared_background,
                    "reference_mask": _resource_record(
                        _resolve_path(base, resources["reference_mask"]),
                        "reference_mask",
                    ),
                    "addon_mask": _resource_record(
                        _resolve_path(base, resources["addon_mask"]), "addon_mask"
                    ),
                }
                voxel_results = render_voxel_section_components(
                    scale_ids=scales,
                    output_root=output_root,
                    catalog=catalog,
                    resources=voxel_resources,
                    style=get_voxel_section_cfg(styles.get("voxel_2d")),
                    force=force,
                )
            except Exception as error:  # noqa: BLE001 - component failure remains isolated
                voxel_results = _component_failure_rows(
                    endpoints=resolved_endpoints, unit="voxel", error=error
                )
        manifest["component_results"]["voxel_2d"] = voxel_results
        _write_json_atomic(manifest_path, manifest)

    if "fiber_2d" in components:
        if not fiber_results:
            try:
                context = prepare_fiber_section_context(
                    catalog=catalog,
                    spatial_config_path=_resolve_path(
                        base, resources["fiber_spatial_config"]
                    ),
                    background_record=shared_background,
                )
                fiber_results = render_fiber_section_components(
                    scale_ids=scales,
                    output_root=output_root,
                    catalog=catalog,
                    context=context,
                    style_overrides=styles.get("fiber_2d"),
                    force=force,
                )
            except Exception as error:  # noqa: BLE001 - component failure remains isolated
                fiber_results = _component_failure_rows(
                    endpoints=resolved_endpoints, unit="fiber", error=error
                )
        manifest["component_results"]["fiber_2d"] = fiber_results
        _write_json_atomic(manifest_path, manifest)

    endpoint_results = _assemble_endpoint_results(
        resolved=resolved_endpoints,
        components=components,
        paired=paired_results,
        voxel=voxel_results,
        fiber=fiber_results,
    )
    failed_count = sum(item["status"] != "complete" for item in endpoint_results)
    manifest.update(
        {
            "status": "complete" if failed_count == 0 else "completed_with_failures",
            "completed_count": len(endpoint_results) - failed_count,
            "failed_count": failed_count,
            "endpoint_results": endpoint_results,
        }
    )
    _write_endpoint_index(output_root, endpoint_results)
    _write_readme(output_root, scales, components)
    _write_json_atomic(manifest_path, manifest)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config")
    source.add_argument("--validate-output")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.validate_output:
        if args.force or args.validate_only:
            raise ValueError("output validation does not accept render options")
        print(
            json.dumps(
                validate_formal_postprocess_output(args.validate_output),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.validate_only:
        print(
            json.dumps(
                validate_formal_postprocess(args.config), indent=2, sort_keys=True
            )
        )
        return 0
    result = run_formal_postprocess(args.config, force=args.force)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "run_formal_postprocess",
    "validate_formal_postprocess",
    "validate_formal_postprocess_output",
]
