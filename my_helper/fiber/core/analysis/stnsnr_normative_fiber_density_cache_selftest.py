#!/usr/bin/env python3
"""Self-tests for STN/SNr normative-fiber basic density-cache generation."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import h5py
import nibabel as nib
import numpy as np

from stnsnr_normative_fiber_density_cache import build_density_cache_for_branch, build_density_cache_from_final_report


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_weights(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"fiber_id": "1", "M_HF": "2.0", "is_candidate": "True"},
        {"fiber_id": "3", "M_HF": "-3.0", "is_candidate": "True"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fiber_id", "M_HF", "is_candidate"])
        writer.writeheader()
        writer.writerows(rows)


def write_tiny_connectome(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Three fibers with lengths [2, 1, 2]. The second fiber is not selected.
    coords = np.array(
        [
            [1, 1, 2, 3, 3],
            [1, 2, 2, 3, 4],
            [1, 1, 2, 3, 3],
            [0, 0, 0, 0, 0],
        ],
        dtype=np.float32,
    )
    with h5py.File(path, "w") as handle:
        handle.create_dataset("fibers", data=coords)
        handle.create_dataset("idx", data=np.array([[2, 1, 2]], dtype=np.float64))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_density_cache_writes_voxel_and_weighted_maps() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        branch_dir = root / "branch"
        weights_csv = branch_dir / "normative_HF_fiber_weights.csv"
        data_mat = root / "data.mat"
        template_path = root / "brainmask.nii.gz"
        write_weights(weights_csv)
        write_tiny_connectome(data_mat)
        template_img = nib.Nifti1Image(np.ones((5, 5, 5), dtype=np.uint8), np.eye(4))
        nib.save(template_img, str(template_path))

        outputs = build_density_cache_for_branch(
            model_id="B_DTOR",
            branch_dir=branch_dir,
            weights_csv=weights_csv,
            data_mat=data_mat,
            template_path=template_path,
            output_prefix="normative_HF",
        )

        density = np.asarray(nib.load(outputs["density_map"]).dataobj)
        weighted = np.asarray(nib.load(outputs["weighted_density_map"]).dataobj)
        positive = np.asarray(nib.load(outputs["positive_weighted_density_map"]).dataobj)
        negative = np.asarray(nib.load(outputs["negative_weighted_density_map"]).dataobj)
        assert_equal(float(density[1, 1, 1]), 1.0, "first selected fiber first voxel count")
        assert_equal(float(density[1, 2, 1]), 1.0, "first selected fiber second voxel count")
        assert_equal(float(density[3, 3, 3]), 1.0, "negative selected fiber first voxel count")
        assert_equal(float(density[3, 4, 3]), 1.0, "negative selected fiber second voxel count")
        assert_equal(float(weighted[1, 1, 1]), 2.0, "positive fiber weighted density")
        assert_equal(float(positive[1, 1, 1]), 2.0, "positive density")
        assert_equal(float(weighted[3, 3, 3]), -3.0, "negative fiber weighted density")
        assert_equal(float(negative[3, 3, 3]), -3.0, "negative density")
        assert_true(Path(outputs["density_cache_npz"]).is_file(), "density cache npz should exist")
        manifest = json.loads(Path(outputs["manifest_json"]).read_text(encoding="utf-8"))
        assert_equal(manifest["n_selected_fibers"], 2, "manifest selected fiber count")
        assert_equal(manifest["n_density_voxels_nonzero"], 4, "manifest density voxel count")


def test_final_report_default_processes_all_normative_fiber_rows() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        asset_root = root / "asset"
        template_path = asset_root / "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz"
        template_path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(nib.Nifti1Image(np.ones((5, 5, 5), dtype=np.uint8), np.eye(4)), str(template_path))
        for rel in [
            "connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat",
            "connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat",
        ]:
            write_tiny_connectome(asset_root / rel)

        ppmi_branch = (
            root
            / "summary/normative_connectome_fiber/hf/ppmi_85_ewert_2017/scale/peak_efield_tau800_primary"
        )
        dtor_branch = (
            root
            / "summary/normative_connectome_fiber/hf/dtor_985_full_elias_2024/scale/peak_efield_tau800_primary"
        )
        direct_branch = root / "summary/direct_voxel/hf/scale/tau200/partial_spearman"
        write_weights(ppmi_branch / "normative_HF_fiber_weights.csv")
        write_weights(dtor_branch / "normative_HF_fiber_weights.csv")
        (ppmi_branch / "normative_HF_fiber_generation_manifest.json").write_text("{}\n", encoding="utf-8")
        (dtor_branch / "normative_HF_fiber_generation_manifest.json").write_text("{}\n", encoding="utf-8")
        (direct_branch / "direct_voxel_HF_generation_manifest.json").parent.mkdir(parents=True, exist_ok=True)
        (direct_branch / "direct_voxel_HF_generation_manifest.json").write_text("{}\n", encoding="utf-8")
        final_report_csv = root / "final_report.csv"
        write_csv(
            final_report_csv,
            [
                {
                    "model_id": "A",
                    "analysis_family": "direct_voxel",
                    "latest_manifest": str(direct_branch / "direct_voxel_HF_generation_manifest.json"),
                },
                {
                    "model_id": "B_PPMI",
                    "analysis_family": "normative_fiber",
                    "latest_manifest": str(ppmi_branch / "normative_HF_fiber_generation_manifest.json"),
                },
                {
                    "model_id": "B_DTOR",
                    "analysis_family": "normative_fiber",
                    "latest_manifest": str(dtor_branch / "normative_HF_fiber_generation_manifest.json"),
                },
            ],
        )

        outputs = build_density_cache_from_final_report(
            final_report_csv=final_report_csv,
            asset_root=asset_root,
            output_dir=root / "density_summary",
            model_ids=None,
        )

        rows = read_csv(Path(outputs["summary_csv"]))
        assert_equal([row["model_id"] for row in rows], ["B_PPMI", "B_DTOR"], "processed normative rows")
        assert_true(
            (ppmi_branch / "normative_HF_streamline_voxel_density_cache.npz").is_file(),
            "PPMI density cache should be written",
        )
        assert_true(
            (dtor_branch / "normative_HF_streamline_voxel_density_cache.npz").is_file(),
            "dTOR density cache should be written",
        )


def main() -> int:
    test_density_cache_writes_voxel_and_weighted_maps()
    test_final_report_default_processes_all_normative_fiber_rows()
    print("stnsnr_normative_fiber_density_cache_selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
