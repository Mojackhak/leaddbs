"""Verify D99 mask contracts and render source-backed atlas quality checks."""

from pathlib import Path
import csv
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/d99-limbic-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def main():
    spec = json.loads((Path(__file__).with_name("specs") / "d99_limbic_regions.json").read_text())
    output = ROOT / spec["output_dir"]
    reference = nib.load(ROOT / spec["reference_image"])
    anatomical = np.asarray(reference.dataobj)
    source = np.asarray(nib.load(ROOT / spec["label_image"]).dataobj)
    manifest = json.loads((output / "roi_manifest.json").read_text())
    qc = []
    for record in manifest["rois"]:
        image = nib.load(record["output_file"])
        mask = np.asarray(image.dataobj)
        assert image.shape == reference.shape
        assert image.get_data_dtype() == np.dtype("uint8")
        assert np.array_equal(image.affine, reference.affine)
        assert np.allclose(image.get_qform(), reference.get_qform(), atol=1e-6)
        assert np.allclose(image.get_sform(), reference.get_sform(), atol=1e-6)
        assert np.isin(mask, [0, 1]).all()
        count = int(np.count_nonzero(mask))
        assert count == record["voxel_count"] and count > 0
        if record["kind"] == "label":
            assert np.array_equal(mask.astype(bool), source == record["source_labels"][0])
        elif record["kind"] == "union":
            children = np.zeros(reference.shape, dtype=np.uint8)
            for member in record["members"]:
                children += np.asarray(nib.load(output / record["side"] / (member + ".nii.gz")).dataobj)
            assert children.max() == 1, "Subregions within a family must be disjoint."
            assert np.array_equal(mask, children), "Merged masks must exactly equal their children."
        else:
            original = nib.load(record["source_file"])
            coords = np.array(np.where(np.asarray(original.dataobj) > 0)).T
            world = nib.affines.apply_affine(original.affine, coords)
            mapped = np.rint(nib.affines.apply_affine(np.linalg.inv(reference.affine), world)).astype(int)
            assert len(coords) == count
            assert np.all(mask[tuple(mapped.T)] == 1)
            assert np.all(source[mask > 0] == record["source_labels"][0])
        voxels = np.array(np.where(mask > 0)).T
        world = nib.affines.apply_affine(reference.affine, voxels)
        assert np.all(world[:, 0] <= 1e-6) if record["side"] == "lh" else np.all(world[:, 0] >= -1e-6)
        qc.append({
            "roi_name": record["roi_name"], "side": record["side"], "kind": record["kind"],
            "parent": record["parent"], "voxel_count": count,
            "volume_mm3": count * abs(float(np.linalg.det(reference.affine[:3, :3]))),
            "centroid_x": float(world[:, 0].mean()), "centroid_y": float(world[:, 1].mean()),
            "centroid_z": float(world[:, 2].mean()), "reference_grid_match": True,
            "source_support_match": True,
        })
    assert len(qc) == 72
    for path, expected in json.loads((output / "source_inventory.json").read_text()).items():
        current = Path(path).stat()
        assert current.st_size == expected["size"] and current.st_mtime_ns == expected["mtime_ns"]
    with (output / "roi_qc.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(qc[0]))
        writer.writeheader()
        writer.writerows(qc)
    qc_dir = output / "qc"
    qc_dir.mkdir(exist_ok=True)
    maximum = np.percentile(anatomical[anatomical > 0], 99.5)
    merged = ["NAc", "ALIC", "GPi", "GPe", "AMY", "HIP", "mPFC"]
    fig, axes = plt.subplots(7, 3, figsize=(11, 22))
    for row, name in enumerate(merged):
        left = np.asarray(nib.load(output / "lh" / (name + ".nii.gz")).dataobj)
        right = np.asarray(nib.load(output / "rh" / (name + ".nii.gz")).dataobj)
        center = np.rint(np.array(np.where(left > 0)).mean(1)).astype(int)
        for axis in range(3):
            ax = axes[row, axis]
            ax.imshow(np.take(anatomical, center[axis], axis=axis).T, origin="lower", cmap="gray", vmin=0, vmax=maximum)
            for mask, color in ((left, [0.95, .25, .2]), (right, [.2, .65, 1.])):
                plane = np.take(mask, center[axis], axis=axis).T
                rgba = np.zeros((*plane.shape, 4))
                rgba[..., :3] = color
                rgba[..., 3] = plane * .75
                ax.imshow(rgba, origin="lower")
            ax.set_title(f"{name}: axis {axis}, voxel {center[axis]}")
            ax.axis("off")
    fig.suptitle("D99 merged regions: left red, right blue; exact 0.25 mm lattice")
    fig.tight_layout(rect=(0, 0, 1, .98))
    fig.savefig(qc_dir / "merged_template_overlays.png", dpi=130)
    plt.close(fig)
    for family in ("AMY", "HIP", "mPFC"):
        members = next(roi["members"] for roi in spec["rois"] if roi["name"] == family)
        colors = plt.get_cmap("tab20")(np.linspace(0, 1, len(members)))
        composite = np.zeros(reference.shape, dtype=np.uint8)
        for number, member in enumerate(members, 1):
            for side in ("lh", "rh"):
                child = np.asarray(nib.load(output / side / (member + ".nii.gz")).dataobj)
                composite[child > 0] = number
        coords = np.array(np.where(composite > 0)).T
        low, high = coords.min(0), coords.max(0)
        fig, axes = plt.subplots(3, 3, figsize=(12, 12))
        cmap = ListedColormap(np.vstack([[0, 0, 0, 0], colors]))
        for axis in range(3):
            for column, fraction in enumerate((.25, .5, .75)):
                pos = int(round(low[axis] + (high[axis] - low[axis]) * fraction))
                ax = axes[axis, column]
                ax.imshow(np.take(anatomical, pos, axis=axis).T, origin="lower", cmap="gray", vmin=0, vmax=maximum)
                ax.imshow(np.take(composite, pos, axis=axis).T, origin="lower", cmap=cmap, vmin=0, vmax=len(members), alpha=.8, interpolation="nearest")
                ax.set_title(f"axis {axis}, voxel {pos}")
                ax.axis("off")
        fig.suptitle(f"D99 {family}: retained subregions")
        fig.legend(handles=[Patch(color=color, label=name) for color, name in zip(colors, members)],
                   loc="lower center", ncol=4, fontsize=9)
        fig.tight_layout(rect=(0, .09, 1, .98))
        fig.savefig(qc_dir / (family + "_subregion_overlays.png"), dpi=140)
        plt.close(fig)
    report = {"binary_masks": 72, "bilateral_entries": 36, "direct_label_masks": 64,
              "derived_ALIC_masks": 2, "exact_parent_unions": 6,
              "reference_grid_and_forms_match": True, "all_nonempty": True,
              "hemisphere_checks_passed": True, "source_files_unchanged": True,
              "interpolation_registration_smoothing_dilation": "None"}
    (output / "mask_verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
