"""Transactional Task 17 display-smoothing publication repair tests."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "pipelines"
    / "repair_task17_display_smoothing_publication.py"
)
SPEC = importlib.util.spec_from_file_location(
    "repair_task17_display_smoothing_publication",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load display-smoothing repair command")
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _metadata(
    *,
    relative: str,
    payload: Path,
    raw_relative: str,
    source_id: str,
    algorithm: str,
    finite_voxels: int,
) -> dict[str, object]:
    return {
        "schema_version": "dual_frequency_derived_artifact_metadata_v1",
        "artifact_kind": "benefit_map_smooth",
        "published_relative_path": relative,
        "payload_sha256": _sha256(payload),
        "size_bytes": payload.stat().st_size,
        "provenance": {
            "source_record_id": source_id,
            "input_relative_path": raw_relative,
            "fwhm_mm": 1.0 if "fwhm1mm" in relative else 2.0,
            "algorithm": algorithm,
            **(
                {
                    "support_policy": repair._SUPPORT_POLICY,
                    "input_finite_voxels": finite_voxels,
                    "output_finite_voxels": finite_voxels,
                }
                if algorithm == repair._ALGORITHM
                else {}
            ),
        },
    }


def _publication(root: Path) -> tuple[Path, str]:
    root.mkdir(parents=True)
    model_manifest = root / "model_manifest.json"
    _write_json(
        model_manifest,
        {
            "schema_version": "direct_voxel_model_manifest_v1",
            "final_status": "completed",
            "source_run_id": "parent",
        },
    )
    rows: list[dict[str, object]] = []
    affine = np.eye(4, dtype=float)
    for scale, old_algorithm in (
        ("old_scale", "masked_normalized_gaussian_v1"),
        ("current_scale", repair._ALGORITHM),
    ):
        raw_relative = f"{scale}/reference/resolver/benefit_map.nii.gz"
        raw_path = root / raw_relative
        raw_path.parent.mkdir(parents=True)
        raw = np.full((7, 7, 7), np.nan, dtype=np.float32)
        raw[3, 3, 3] = 1.0
        raw[3, 4, 3] = -0.5
        raw_image = nib.Nifti1Image(raw, affine)
        raw_image.set_data_dtype(np.float32)
        nib.save(raw_image, raw_path)
        rows.append(
            {
                "relative_path": raw_relative,
                "sha256": _sha256(raw_path),
                "size_bytes": raw_path.stat().st_size,
                "status": "completed",
            }
        )
        _write_json(
            root / scale / "reference" / "final_model.json",
            {
                "scale_id": scale,
                "model_family": "reference",
                "artifact_relative_paths": [raw_relative],
            },
        )
        for fwhm in (1.0, 2.0):
            relative = (
                f"{scale}/reference/report/display/"
                f"benefit_map_smooth_fwhm{int(fwhm)}mm.nii.gz"
            )
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if old_algorithm == repair._ALGORITHM:
                image, finite_voxels = repair._smooth_image(raw_image, fwhm)
                nib.save(image, path)
            else:
                expanded = np.full(raw.shape, np.nan, dtype=np.float32)
                expanded[2:5, 2:6, 2:5] = 0.25
                image = nib.Nifti1Image(expanded, affine)
                image.set_data_dtype(np.float32)
                nib.save(image, path)
                finite_voxels = int(np.count_nonzero(np.isfinite(raw)))
            metadata = _metadata(
                relative=relative,
                payload=path,
                raw_relative=raw_relative,
                source_id=f"source-{scale}",
                algorithm=old_algorithm,
                finite_voxels=finite_voxels,
            )
            _write_json(Path(f"{path}.metadata.json"), metadata)
            rows.append(
                {
                    "relative_path": relative,
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                    "status": "completed",
                }
            )
    with (root / "artifact_index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("relative_path", "sha256", "size_bytes", "status"),
        )
        writer.writeheader()
        writer.writerows(rows)
    return model_manifest, _sha256(model_manifest)


def test_stage_validate_promote_and_repeat_are_fail_closed(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    model_manifest, model_sha = _publication(publication)
    stage_root = tmp_path / "stage"

    staged = repair.stage(publication, stage_root)
    assert staged["status"] == "staged"
    assert staged["changed_nifti_count"] == 2
    validated = repair.validate(publication, stage_root)
    assert validated["state"] == "staged"
    assert validated["target_count"] == 4

    trash = tmp_path / ".Trashes" / str(os.getuid()) / "display-repair"
    promoted = repair.promote(publication, stage_root, trash)
    assert promoted["status"] == "promoted"
    assert promoted["state"] == "promoted"
    assert _sha256(model_manifest) == model_sha
    assert not (publication / repair._MAINTENANCE_NAME).exists()
    assert (
        trash
        / "canonical"
        / "old_scale/reference/report/display/benefit_map_smooth_fwhm1mm.nii.gz"
    ).is_file()
    assert not (
        trash
        / "canonical"
        / "current_scale/reference/report/display/benefit_map_smooth_fwhm1mm.nii.gz"
    ).exists()

    repeated = repair.promote(publication, stage_root, trash)
    assert repeated["status"] == "promoted"
    assert repeated["state"] == "promoted"
    assert repair.validate(publication, stage_root)["state"] == "promoted"


def test_stage_refuses_existing_destination(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    _publication(publication)
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    with pytest.raises(repair.DisplaySmoothingRepairError, match="already exists"):
        repair.stage(publication, stage_root)


def test_changed_source_index_blocks_promotion(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    _publication(publication)
    stage_root = tmp_path / "stage"
    repair.stage(publication, stage_root)
    with (publication / "artifact_index.csv").open("ab") as stream:
        stream.write(b"\n")
    trash = tmp_path / ".Trashes" / str(os.getuid()) / "display-repair"
    with pytest.raises(
        repair.DisplaySmoothingRepairError,
        match="artifact index changed",
    ):
        repair.promote(publication, stage_root, trash)
    assert (publication / "model_manifest.json").is_file()


def test_promotion_requires_same_volume_user_trash(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    _publication(publication)
    stage_root = tmp_path / "stage"
    repair.stage(publication, stage_root)
    with pytest.raises(
        repair.DisplaySmoothingRepairError,
        match="below .Trashes",
    ):
        repair.promote(publication, stage_root, tmp_path / "ordinary-archive")
    assert (publication / "model_manifest.json").is_file()


def test_interrupted_promotion_resumes_before_manifest_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    model_manifest, model_sha = _publication(publication)
    stage_root = tmp_path / "stage"
    repair.stage(publication, stage_root)
    trash = tmp_path / ".Trashes" / str(os.getuid()) / "display-repair"
    original = repair._archive_and_install
    calls = 0

    def interrupt_after_first_install(**arguments: object) -> None:
        nonlocal calls
        original(**arguments)
        calls += 1
        if calls == 1:
            raise RuntimeError("injected interruption")

    monkeypatch.setattr(repair, "_archive_and_install", interrupt_after_first_install)
    with pytest.raises(RuntimeError, match="injected interruption"):
        repair.promote(publication, stage_root, trash)
    assert not model_manifest.exists()
    assert (publication / repair._MAINTENANCE_NAME).is_file()

    monkeypatch.setattr(repair, "_archive_and_install", original)
    resumed = repair.promote(publication, stage_root, trash)
    assert resumed["state"] == "promoted"
    assert _sha256(model_manifest) == model_sha
    assert not (publication / repair._MAINTENANCE_NAME).exists()


def test_tampered_stage_fails_before_manifest_withdrawal(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    model_manifest, model_sha = _publication(publication)
    stage_root = tmp_path / "stage"
    repair.stage(publication, stage_root)
    manifest = json.loads((stage_root / repair._REPAIR_NAME).read_text())
    target = stage_root / manifest["records"][0]["relative_path"]
    with target.open("r+b") as stream:
        stream.seek(-1, 2)
        final_byte = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([final_byte[0] ^ 1]))
    trash = tmp_path / ".Trashes" / str(os.getuid()) / "display-repair"
    with pytest.raises(
        repair.DisplaySmoothingRepairError,
        match="staged payload SHA-256 differs",
    ):
        repair.promote(publication, stage_root, trash)
    assert _sha256(model_manifest) == model_sha
    assert not (publication / repair._MAINTENANCE_NAME).exists()
