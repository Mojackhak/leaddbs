"""Tests for complete canonical Task 17 model-set payload validation."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "pipelines"
    / "validate_task17_model_set_publication.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_task17_model_set_publication",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Task 17 model-set publication validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_publication(
    output_root: Path,
    profile: str,
    *,
    scientific_hash: str = "a" * 64,
) -> Path:
    model_set_id = "model-set"
    root = output_root / profile / model_set_id
    root.mkdir(parents=True)
    study = root / "study_base.json"
    resolved_name = f"resolved_{profile}_model.yaml"
    resolved = root / resolved_name
    _write_json(study, {"study_id": "study"})
    resolved.write_text("model_set_id: model-set\n", encoding="utf-8")
    scales = ("scale_a", "scale_b")
    paths: list[Path] = [study, resolved]
    for scale in scales:
        for role in ("reference", "addon"):
            base = root / scale / role
            source = base / "source.json"
            _write_json(source, {"status": "completed"})
            final = {
                "schema_version": f"{profile}_final_model_v1",
                "final_status": "final_model_realized",
                "scale_id": scale,
                "model_family": role,
                "scientific_config_sha256": scientific_hash,
            }
            if profile == "direct_voxel":
                final["source_record_relative_path"] = (
                    source.relative_to(root).as_posix()
                )
                final["artifact_relative_paths"] = [
                    source.relative_to(root).as_posix()
                ]
            else:
                final["resolver_relative_path"] = (
                    source.relative_to(root).as_posix()
                )
            final_path = base / "final_model.json"
            _write_json(final_path, final)
            paths.extend((source, final_path))
    manifest = {
        "final_status": "completed",
        "model_set_id": model_set_id,
        "output_root": str(output_root),
        "profile_type": profile,
        "resolved_model_path": resolved_name,
        "resolved_model_sha256": validator._sha256_file(resolved),
        "scale_count": len(scales),
        "scale_ids": list(scales),
        "schema_version": f"{profile}_model_manifest_v1",
        "scientific_config_sha256": scientific_hash,
        "source_run_id": "parent-run",
        "study_base_path": str(study),
        "study_base_sha256": validator._sha256_file(study),
        "study_id": "study",
    }
    _write_json(root / "model_manifest.json", manifest)
    fields = [
        "scale_id",
        "model_family",
        "branch_id",
        "stage",
        "artifact_kind",
        "relative_path",
        "sha256",
        "size_bytes",
        "status",
    ]
    if profile == "normative_fiber":
        fields[3:3] = ["connectome_id", "connectome_role"]
    with (root / "artifact_index.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for path in sorted(paths):
            relative = path.relative_to(root).as_posix()
            parts = Path(relative).parts
            scale = parts[0] if parts[0] in scales else ""
            role = parts[1] if len(parts) > 1 and parts[1] in {"reference", "addon"} else ""
            row = {
                "scale_id": scale,
                "model_family": role,
                "branch_id": "",
                "stage": "final" if path.name == "final_model.json" else "configuration",
                "artifact_kind": path.stem,
                "relative_path": relative,
                "sha256": validator._sha256_file(path),
                "size_bytes": path.stat().st_size,
                "status": "completed",
            }
            if profile == "normative_fiber":
                row["connectome_id"] = "formal-connectome"
                row["connectome_role"] = "formal"
            writer.writerow(row)
    return root


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    output_root = tmp_path / "published"
    direct = _build_publication(output_root, "direct_voxel")
    fiber = _build_publication(output_root, "normative_fiber")
    return direct, fiber


def test_complete_publications_and_same_byte_report_pass(tmp_path: Path) -> None:
    direct, fiber = _fixture(tmp_path)
    report = validator.validate((direct, fiber))

    assert report["status"] == "validated"
    assert report["publication_count"] == 2
    assert report["artifact_count"] == 20
    assert {
        publication["profile_type"]
        for publication in report["publications"]
    } == {"direct_voxel", "normative_fiber"}
    assert {
        publication["final_model_count"]
        for publication in report["publications"]
    } == {4}

    output = tmp_path / "validation.json"
    validator._write_report(output, report)
    first_stat = output.stat()
    validator._write_report(output, report)
    assert output.stat().st_mtime_ns == first_stat.st_mtime_ns
    changed = dict(report)
    changed["status"] = "changed"
    with pytest.raises(
        validator.ModelSetPublicationError,
        match="differs",
    ):
        validator._write_report(output, changed)


def test_indexed_payload_corruption_fails(tmp_path: Path) -> None:
    direct, fiber = _fixture(tmp_path)
    path = direct / "scale_a/reference/source.json"
    path.write_text("corrupt\n", encoding="utf-8")

    with pytest.raises(
        validator.ModelSetPublicationError,
        match="byte count differs|SHA differs",
    ):
        validator.validate((direct, fiber))


def test_duplicate_index_path_fails(tmp_path: Path) -> None:
    direct, _fiber = _fixture(tmp_path)
    index = direct / "artifact_index.csv"
    lines = index.read_text(encoding="utf-8").splitlines()
    index.write_text("\n".join((*lines, lines[1])) + "\n", encoding="utf-8")

    with pytest.raises(
        validator.ModelSetPublicationError,
        match="duplicate path",
    ):
        validator.validate((direct,))


def test_cross_domain_scientific_identity_mismatch_fails(tmp_path: Path) -> None:
    output_root = tmp_path / "published"
    direct = _build_publication(output_root, "direct_voxel")
    fiber = _build_publication(
        output_root,
        "normative_fiber",
        scientific_hash="b" * 64,
    )

    with pytest.raises(
        validator.ModelSetPublicationError,
        match="scientific_configuration_sha256",
    ):
        validator.validate((direct, fiber))


def test_missing_final_model_index_row_fails(tmp_path: Path) -> None:
    direct, _fiber = _fixture(tmp_path)
    index = direct / "artifact_index.csv"
    with index.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        rows = [
            row
            for row in reader
            if row["relative_path"] != "scale_a/reference/final_model.json"
        ]
    with index.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(
        validator.ModelSetPublicationError,
        match="final-model index closure differs",
    ):
        validator.validate((direct,))
