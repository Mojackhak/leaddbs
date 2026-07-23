"""Publish the accepted single-scale direct-voxel section checkpoint."""

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
import nibabel as nib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .plugin.default import get_voxel_section_cfg
from .published_artifacts import PublicationCatalog, PublishedArtifact
from .voxel_sections import plot_signed_voxel_sections


SCHEMA_VERSION = "dual_frequency_voxel_section_postprocess_v2"


@dataclass(frozen=True)
class _RoleSpec:
    role: str
    mask_key: str


_ROLE_SPECS = (
    _RoleSpec(role="reference", mask_key="reference_mask"),
    _RoleSpec(role="addon", mask_key="addon_mask"),
)

_DISPLAY_MAPS = (
    "benefit_map.nii.gz",
    "benefit_map_smooth_fwhm1mm.nii.gz",
    "benefit_map_smooth_fwhm2mm.nii.gz",
)

_REPORT_DISPLAY_MAPS = _DISPLAY_MAPS[1:]


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


def _sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resource_record(path: str | Path, kind: str) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"visualization resource is missing: {resolved}")
    image = nib.load(str(resolved))
    if len(image.shape) != 3:
        raise ValueError(f"visualization resource must be a 3D NIfTI: {resolved}")
    return {
        "kind": kind,
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
        "shape": [int(item) for item in image.shape],
        "dtype": str(image.get_data_dtype()),
        "orientation": list(nib.aff2axcodes(image.affine)),
        "affine": [[float(value) for value in row] for row in image.affine],
    }


def _references(scale_id: str, role: str) -> dict[str, dict[str, str]]:
    base = f"{scale_id}/{role}"
    references = {
        "final_model": {
            "publication": "direct_voxel_main",
            "relative_path": f"{base}/final_model.json",
        },
        "report_summary": {
            "publication": "direct_voxel_main",
            "relative_path": f"{base}/report/summary.json",
        },
    }
    for filename in _REPORT_DISPLAY_MAPS:
        references[filename] = {
            "publication": "direct_voxel_main",
            "relative_path": f"{base}/report/display/{filename}",
        }
    return references


def _selected_benefit_map_relative_path(
    final_model: Mapping[str, Any],
) -> str:
    paths = final_model.get("artifact_relative_paths")
    if not isinstance(paths, list):
        raise ValueError("final model lacks artifact_relative_paths")
    matches = [
        str(value)
        for value in paths
        if Path(str(value)).name == "benefit_map.nii.gz"
    ]
    if len(matches) != 1:
        raise ValueError(
            "final model must select exactly one benefit_map.nii.gz artifact"
        )
    return matches[0]


def _resolve_sources(
    catalog: PublicationCatalog,
    references: Mapping[str, object],
) -> dict[str, PublishedArtifact]:
    return {name: catalog.resolve(reference) for name, reference in references.items()}


def _validate_final_model(
    scale_id: str,
    role: str,
    final_model: Mapping[str, Any],
    report_summary: Mapping[str, Any],
) -> None:
    if str(final_model.get("final_status", "")).lower() not in {
        "complete",
        "completed",
        "final_model_realized",
    }:
        raise ValueError(f"direct-voxel final model is incomplete: {role}")
    if str(final_model.get("scale_id")) != scale_id:
        raise ValueError(f"direct-voxel final-model scale mismatch: {role}")
    if str(final_model.get("model_family")) != role:
        raise ValueError(f"direct-voxel final-model role mismatch: {role}")
    expected_summary = {
        "scale_id": scale_id,
        "model_family": role,
        "final_model_id": final_model.get("final_model_id"),
        "selected_tau_v_per_m": final_model.get("selected_tau_v_per_m"),
        "selected_coverage_subjects_min": final_model.get(
            "selected_coverage_subjects_min"
        ),
    }
    for summary_key, final_value in expected_summary.items():
        if summary_key in {"selected_tau_v_per_m", "selected_coverage_subjects_min"}:
            report_key = summary_key
        else:
            report_key = summary_key
        if str(report_summary.get(report_key)) != str(final_value):
            raise ValueError(
                f"direct-voxel report {report_key} mismatch for {role}"
            )
    if report_summary.get("display_only") is not True:
        raise ValueError(f"direct-voxel report is not marked display-only: {role}")


def _result_reusable(result_path: Path, request_hash: str, root: Path) -> bool:
    if not result_path.is_file():
        return False
    try:
        payload = _read_json(result_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if payload.get("status") != "complete" or payload.get("request_hash") != request_hash:
        return False
    outputs = payload.get("outputs")
    return isinstance(outputs, list) and all(
        (root / str(relative)).is_file() for relative in outputs
    )


def _write_index(root: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "status",
        "scale_id",
        "model_role",
        "display_artifact_kind",
        "final_model_id",
        "final_branch",
        "selected_tau",
        "selected_coverage",
        "heat_vmin",
        "heat_vmax",
        "result_path",
    )
    temporary = root / "figure_index.csv.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in rows:
            limits = item.get("render_metadata", {}).get("heat_limits", [None, None])
            writer.writerow(
                {
                    "status": item.get("status"),
                    "scale_id": item.get("scale_id"),
                    "model_role": item.get("model_role"),
                    "display_artifact_kind": item.get("display_artifact_kind"),
                    "final_model_id": item.get("final_model_id"),
                    "final_branch": item.get("final_branch"),
                    "selected_tau": item.get("selected_tau"),
                    "selected_coverage": item.get("selected_coverage"),
                    "heat_vmin": limits[0] if len(limits) > 0 else None,
                    "heat_vmax": limits[1] if len(limits) > 1 else None,
                    "result_path": item.get("result_path"),
                }
            )
    temporary.replace(root / "figure_index.csv")


def _write_readme(root: Path, scale_id: str) -> None:
    text = f"""# PDQ-39 Direct-Voxel Spatial Postprocess

This checkpoint contains only the accepted direct-voxel section figures for
`{scale_id}`. It includes the reference and add-on final models and three
published maps per model: raw right-sided, FWHM 1 mm, and FWHM 2 mm.
It does not contain another scale or a fiber-density projection.

Browse the six figures under:

```text
scales/{scale_id}/reference/voxel/
scales/{scale_id}/addon/voxel/
```

Every figure has PNG, PDF, and JSON files. The JSON binds the canonical
publication source, final-model identity, anatomy, right-sided mask, slice
coordinates, display limits, and rendering parameters. `figure_index.csv`
provides a compact cross-figure index.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def render_voxel_section_components(
    *,
    scale_ids: Sequence[str],
    output_root: str | Path,
    catalog: PublicationCatalog,
    resources: Mapping[str, Mapping[str, Any]],
    style: Mapping[str, Any],
    force: bool = False,
) -> list[dict[str, Any]]:
    """Render direct-voxel components without writing root metadata."""

    root = Path(output_root).expanduser().resolve()
    normalized_scales = tuple(str(value).strip() for value in scale_ids)
    if not normalized_scales:
        raise ValueError("scale_ids must contain at least one scale")
    if len(set(normalized_scales)) != len(normalized_scales):
        raise ValueError("scale_ids must not contain duplicates")
    for scale_id in normalized_scales:
        if not scale_id or "/" in scale_id or ".." in scale_id:
            raise ValueError("every scale_id must be one safe path component")
    required_resources = {"background", "reference_mask", "addon_mask"}
    if not required_resources.issubset(resources):
        raise ValueError("voxel component resources are incomplete")

    results: list[dict[str, Any]] = []
    for scale_id in normalized_scales:
        for role_spec in _ROLE_SPECS:
            references = _references(scale_id, role_spec.role)
            try:
                sources = _resolve_sources(catalog, references)
                final_model = _read_json(sources["final_model"].path)
                report_summary = _read_json(sources["report_summary"].path)
                _validate_final_model(
                    scale_id, role_spec.role, final_model, report_summary
                )
                sources["benefit_map.nii.gz"] = catalog.resolve_relative(
                    "direct_voxel_main",
                    _selected_benefit_map_relative_path(final_model),
                )
            except Exception as error:  # noqa: BLE001 - role-local failure is recorded
                for filename in _DISPLAY_MAPS:
                    stem = filename.removesuffix(".nii.gz") + "_sections"
                    leaf = root / "scales" / scale_id / role_spec.role / "voxel"
                    result_path = leaf / f"{stem}.json"
                    item = {
                        "schema_version": SCHEMA_VERSION,
                        "status": "failed",
                        "scale_id": scale_id,
                        "model_role": role_spec.role,
                        "display_artifact_kind": filename.removesuffix(".nii.gz"),
                        "result_path": result_path.relative_to(root).as_posix(),
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                    _write_json_atomic(result_path, item)
                    results.append(item)
                continue

            shared_source_records = {
                name: artifact.as_manifest_record()
                for name, artifact in sources.items()
                if name in {"final_model", "report_summary"}
            }
            for filename in _DISPLAY_MAPS:
                stem = filename.removesuffix(".nii.gz") + "_sections"
                leaf = root / "scales" / scale_id / role_spec.role / "voxel"
                result_path = leaf / f"{stem}.json"
                heat_artifact = sources[filename]
                source_records = {
                    **shared_source_records,
                    "heatmap": heat_artifact.as_manifest_record(),
                }
                request_hash = _payload_hash(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "scale_id": scale_id,
                        "model_role": role_spec.role,
                        "display_artifact_kind": filename.removesuffix(".nii.gz"),
                        "source_artifacts": source_records,
                        "background": resources["background"],
                        "mask": resources[role_spec.mask_key],
                        "style": dict(style),
                    }
                )
                item: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION,
                    "status": "running",
                    "request_hash": request_hash,
                    "scale_id": scale_id,
                    "model_role": role_spec.role,
                    "model_unit": "voxel",
                    "display_artifact_kind": filename.removesuffix(".nii.gz"),
                    "result_path": result_path.relative_to(root).as_posix(),
                }
                try:
                    if not force and _result_reusable(result_path, request_hash, root):
                        restored = _read_json(result_path)
                        restored["resume_status"] = "reused"
                        results.append(restored)
                        continue
                    output_paths = [
                        leaf / f"{stem}.{str(extension).lower().lstrip('.')}"
                        for extension in style["formats"]
                    ]
                    relative_outputs = [
                        path.relative_to(root).as_posix() for path in output_paths
                    ]
                    figure = plot_signed_voxel_sections(
                        heat_artifact.path,
                        background_image=resources["background"]["path"],
                        mask_image=resources[role_spec.mask_key]["path"],
                        style_config=style,
                        output_paths=output_paths,
                    )
                    render_metadata = getattr(
                        figure, "_mh_viz_voxel_section_metadata"
                    )
                    plt.close(figure)
                    item.update(
                        {
                            "status": "complete",
                            "final_model_id": final_model.get("final_model_id"),
                            "final_branch": final_model.get(
                                "realized_final_branch",
                                final_model.get("final_branch"),
                            ),
                            "selected_tau": final_model.get("selected_tau_v_per_m"),
                            "selected_coverage": final_model.get(
                                "selected_coverage_subjects_min"
                            ),
                            "source_artifacts": source_records,
                            "resources": {
                                "background": dict(resources["background"]),
                                "mask": dict(resources[role_spec.mask_key]),
                            },
                            "style": dict(style),
                            "render_metadata": render_metadata,
                            "outputs": relative_outputs,
                        }
                    )
                except Exception as error:  # noqa: BLE001 - figure-local failure is recorded
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


def run_single_scale_voxel_section_postprocess(
    *,
    scale_id: str,
    output_root: str | Path,
    direct_voxel_publication_root: str | Path,
    background_path: str | Path,
    reference_mask_path: str | Path,
    addon_mask_path: str | Path,
    style_overrides: Mapping[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Render the six accepted direct-voxel section figures for one scale."""

    normalized_scale = str(scale_id).strip()
    if not normalized_scale or "/" in normalized_scale or ".." in normalized_scale:
        raise ValueError("scale_id must be one safe path component")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    catalog = PublicationCatalog.from_config(
        {
            "direct_voxel_main": {
                "root": str(Path(direct_voxel_publication_root).expanduser().resolve()),
                "manifest": "model_manifest.json",
            }
        },
        config_base=root,
    )
    style = get_voxel_section_cfg(style_overrides)
    resources = {
        "background": _resource_record(background_path, "anatomy_background"),
        "reference_mask": _resource_record(reference_mask_path, "reference_mask"),
        "addon_mask": _resource_record(addon_mask_path, "addon_mask"),
    }
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "scale_id": normalized_scale,
        "style": style,
        "resources": resources,
        "publications": catalog.publication_records(),
        "results": [],
    }
    _write_json_atomic(manifest_path, manifest)

    manifest["results"] = render_voxel_section_components(
        scale_ids=(normalized_scale,),
        output_root=root,
        catalog=catalog,
        resources=resources,
        style=style,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-id", default="pdq39_score")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--direct-voxel-root", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--reference-mask", required=True)
    parser.add_argument("--addon-mask", required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_single_scale_voxel_section_postprocess(
        scale_id=args.scale_id,
        output_root=args.output_root,
        direct_voxel_publication_root=args.direct_voxel_root,
        background_path=args.background,
        reference_mask_path=args.reference_mask,
        addon_mask_path=args.addon_mask,
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "render_voxel_section_components",
    "run_single_scale_voxel_section_postprocess",
]
