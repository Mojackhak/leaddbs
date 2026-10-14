"""Convert the downloaded AAL3 1 mm labels from Colin27 to Lead-DBS 2009b."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import nibabel as nib
from nibabel.processing import resample_from_to
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPACE = ROOT / "templates/space/MNI152NLin2009bAsym"
WORK = ROOT / "templates/atlas_sources/AAL3 (Rolls 2020)"
SOURCE = WORK / "source"
REG = WORK / "registration"
QC = WORK / "qc"
OUTPUT = SPACE / "atlases/AAL3 (Rolls 2020)"
STAGING = WORK / "atlas_staging"
DOWNLOAD = Path("/Users/mojackhu/Downloads/AAL3")
LABELS = SOURCE / "AAL3v1_1mm.nii.gz"
TABLE = SOURCE / "AAL3v1_1mm.nii.txt"
MOVING = SOURCE / "colin27_t1_tal_lin.nii"
MOVING_MASK = SOURCE / "colin27_t1_tal_lin_mask.nii"
FIXED = REG / "MNI152NLin2009bAsym_T1_1mm.nii.gz"
FIXED_MASK = REG / "MNI152NLin2009bAsym_brainmask_1mm.nii.gz"
PREFIX = REG / "Colin27_to_MNI152NLin2009bAsym_"
WARPED_T1 = REG / "Colin27_T1_in_MNI152NLin2009bAsym.nii.gz"
WARPED_MASK = REG / "Colin27_brainmask_in_MNI152NLin2009bAsym.nii.gz"
WARPED_LABELS = REG / "AAL3_in_MNI152NLin2009bAsym.nii.gz"
ANTS = ROOT / "ext_libs/ANTs"
REGISTER = ANTS / "antsRegistration.maca64"
APPLY = ANTS / "antsApplyTransforms.maca64"
AFFINE = Path(str(PREFIX) + "0GenericAffine.mat")
WARP = Path(str(PREFIX) + "1Warp.nii.gz")


def write_json(path, payload):
    with Path(path).open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def save_on_grid(data, reference, path, dtype):
    header = reference.header.copy()
    header.set_data_dtype(dtype)
    image = nib.Nifti1Image(data.astype(dtype), reference.affine, header)
    image.set_qform(reference.affine, code=2)
    image.set_sform(reference.affine, code=2)
    nib.save(image, path)
    return image


def plot_labels(anatomy, labels, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = anatomy.get_fdata(dtype=np.float32)
    ids = np.asanyarray(labels.dataobj)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), facecolor="white")
    slices = [(2, z) for z in (-40, -25, -10, 5, 25, 50)] + [(1, -15), (0, 0)]
    vmax = np.percentile(data[data > 0], 99)
    for ax, (axis, mm) in zip(axes.flat, slices):
        index = int(round((mm - anatomy.affine[axis, 3]) / anatomy.affine[axis, axis]))
        background = np.take(data, index, axis=axis).T
        overlay = np.take(ids, index, axis=axis).T
        ax.imshow(background, origin="lower", cmap="gray", vmin=0, vmax=vmax)
        ax.imshow(np.ma.masked_where(overlay == 0, overlay), origin="lower",
                  cmap="turbo", vmin=1, vmax=170, alpha=0.35, interpolation="nearest")
        ax.set_title(f"{'xyz'[axis]} = {mm} mm")
        ax.axis("off")
    fig.suptitle(title + " | RAS display; image left is anatomical left", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def prepare():
    REG.mkdir()
    QC.mkdir()
    for name in (LABELS.name, TABLE.name):
        shutil.copy2(DOWNLOAD / name, SOURCE / name)
    source = nib.load(LABELS)
    moving = nib.load(MOVING)
    if source.shape != moving.shape or not np.array_equal(source.affine, moving.affine):
        raise ValueError("AAL3 and Colin27 do not share the expected source grid")
    ids = np.unique(np.asanyarray(source.dataobj))
    if not np.array_equal(ids, ids.astype(np.uint8)) or len(ids[ids > 0]) != 166:
        raise ValueError("Expected 166 nonzero integer AAL3 labels")

    original = nib.load(SPACE / "t1.nii")
    spacing = nib.affines.voxel_sizes(original.affine)
    shape = tuple(np.ceil(np.asarray(original.shape) * spacing).astype(int))
    affine = original.affine.copy()
    affine[:3, :3] /= spacing
    affine[:3, 3] += 0.5 * np.sum(affine[:3, :3] - original.affine[:3, :3], axis=1)
    reference = resample_from_to(original, (shape, affine), order=1)
    reference = save_on_grid(reference.get_fdata(dtype=np.float32), reference, FIXED, np.float32)
    mask = resample_from_to(nib.load(SPACE / "brainmask.nii.gz"), reference, order=0)
    save_on_grid(np.asanyarray(mask.dataobj) > 0, reference, FIXED_MASK, np.uint8)
    plot_labels(moving, source, QC / "source_AAL3_on_Colin27.png", "Source AAL3 on Colin27")
    write_json(QC / "input_geometry.json", {
        "source_shape": list(source.shape), "source_affine": source.affine.tolist(),
        "reference_shape": list(reference.shape), "reference_affine": reference.affine.tolist(),
        "nonzero_label_count": 166, "source_anatomy_grid_matches_labels": True,
        "source_url": "https://packages.bic.mni.mcgill.ca/mni-models/colin27/mni_colin27_1998_nifti.zip",
    })
    print(f"Prepared reference and source QC: {QC}", flush=True)


def register():
    command = [str(REGISTER), "--dimensionality", "3", "--float", "1",
        "--output", f"[{PREFIX},{WARPED_T1}]", "--interpolation", "Linear",
        "--winsorize-image-intensities", "[0.005,0.995]", "--use-histogram-matching", "0",
        "--initial-moving-transform", f"[{FIXED},{MOVING},1]",
        "--masks", f"[{FIXED_MASK},{MOVING_MASK}]", "--random-seed", "42"]
    for transform in ("Rigid[0.1]", "Affine[0.1]"):
        command += ["--transform", transform, "--metric", f"MI[{FIXED},{MOVING},1,32,Regular,0.25]",
            "--convergence", "[1000x500x250x100,1e-6,10]", "--shrink-factors", "8x4x2x1",
            "--smoothing-sigmas", "3x2x1x0mm"]
    command += ["--transform", "SyN[0.1,3,0]", "--metric", f"CC[{FIXED},{MOVING},1,4]",
        "--convergence", "[100x70x50x20,1e-6,10]", "--shrink-factors", "8x4x2x1",
        "--smoothing-sigmas", "3x2x1x0mm", "--verbose", "1"]
    version = subprocess.check_output([str(REGISTER), "--version"], text=True).strip()
    write_json(REG / "registration_command.json", {
        "command": command, "ants_version": version,
        "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": 4, "random_seed": 42,
    })
    env = dict(os.environ, ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="4")
    print(f"Registration started; log: {REG / 'registration.log'}", flush=True)
    with (REG / "registration.log").open("x") as log:
        subprocess.run(command, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    print("Anatomical registration finished", flush=True)


def apply_image(source, output):
    command = [str(APPLY), "-d", "3", "--float", "1", "-i", str(source), "-r", str(FIXED),
               "-o", str(output), "-n", "NearestNeighbor", "-t", str(WARP), "-t", str(AFFINE)]
    subprocess.run(command, check=True, env=dict(os.environ, ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="4"))
    return command


def anatomy_qc(reference):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fixed = reference.get_fdata(dtype=np.float32)
    before = resample_from_to(nib.load(MOVING), reference, order=1).get_fdata(dtype=np.float32)
    after = nib.load(WARPED_T1).get_fdata(dtype=np.float32)
    fixed_mask = np.asanyarray(nib.load(FIXED_MASK).dataobj) > 0
    before_mask = np.asanyarray(resample_from_to(nib.load(MOVING_MASK), reference, order=0).dataobj) > 0
    after_mask = np.asanyarray(nib.load(WARPED_MASK).dataobj) > 0
    def dice(mask):
        return float(2 * np.count_nonzero(mask & fixed_mask) / (np.count_nonzero(mask) + np.count_nonzero(fixed_mask)))
    metrics = {
        "brain_mask_dice_before": dice(before_mask), "brain_mask_dice_after": dice(after_mask),
        "T1_pearson_in_fixed_brain_before": float(np.corrcoef(fixed[fixed_mask], before[fixed_mask])[0, 1]),
        "T1_pearson_in_fixed_brain_after": float(np.corrcoef(fixed[fixed_mask], after[fixed_mask])[0, 1]),
    }
    slices = [(2, -30), (2, -10), (2, 10), (2, 40), (1, -20), (0, 0)]
    fig, axes = plt.subplots(len(slices), 3, figsize=(11, 19), facecolor="white")
    for row, (axis, mm) in enumerate(slices):
        index = int(round((mm - reference.affine[axis, 3]) / reference.affine[axis, axis]))
        for col, (array, name) in enumerate(((fixed, "Fixed 2009b"), (before, "Colin27 before"), (after, "Colin27 after"))):
            plane = np.take(array, index, axis=axis).T
            ax = axes[row, col]
            ax.imshow(plane, origin="lower", cmap="gray", vmin=0, vmax=np.percentile(array[fixed_mask], 99))
            ax.contour(np.take(fixed_mask, index, axis=axis).T, levels=[0.5], colors=["#00d6ff"], linewidths=0.5)
            ax.set_title(f"{name}; {'xyz'[axis]}={mm} mm")
            ax.axis("off")
    fig.suptitle("Colin27 to MNI152NLin2009bAsym | cyan: fixed brain boundary")
    fig.tight_layout()
    fig.savefig(QC / "registration_before_after.png", dpi=110)
    plt.close(fig)
    return metrics


def export():
    sys.path.insert(0, str(ROOT))
    from my_helper.fiber.core.whole_brain_roi_atlas.export import export_binary_rois
    from my_helper.fiber.core.whole_brain_roi_atlas.models import ResolvedLabel

    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite existing atlas: {OUTPUT}")
    STAGING.mkdir()
    transfer = apply_image(LABELS, WARPED_LABELS)
    apply_image(MOVING_MASK, WARPED_MASK)
    reference = nib.load(FIXED)
    source = nib.load(LABELS)
    source_data = np.asanyarray(source.dataobj)
    transferred = nib.load(WARPED_LABELS)
    if transferred.shape != reference.shape or not np.allclose(
        transferred.affine, reference.affine, atol=1e-5, rtol=0
    ):
        raise ValueError("Transferred labels do not match the requested output grid")
    data = np.asanyarray(transferred.dataobj)
    if not np.all(np.isfinite(data)) or not np.array_equal(data, np.rint(data)):
        raise ValueError("Transferred labels are not finite integers")
    if not np.array_equal(np.unique(data), np.unique(source_data)):
        raise ValueError("Label transfer lost or added label IDs")
    label_image = save_on_grid(data, reference, STAGING / "labels.nii.gz", np.uint8)
    rows = [line.split() for line in TABLE.read_text().splitlines() if line.strip()]
    names = {int(row[0]): row[1] for row in rows}
    if len(names) != len(rows):
        raise ValueError("Duplicate label IDs in the source table")
    records, label_stats = [], []
    for label_id in map(int, np.unique(data)[1:]):
        name = names[label_id]
        side = "L" if name.endswith("_L") else "R" if name.endswith("_R") else "M"
        base = name[:-2] if side in ("L", "R") else name
        voxels = np.argwhere(data == label_id)
        center = nib.affines.apply_affine(reference.affine, voxels.mean(axis=0))
        source_voxels = np.argwhere(source_data == label_id)
        source_center = nib.affines.apply_affine(source.affine, source_voxels.mean(axis=0))
        world_x = nib.affines.apply_affine(reference.affine, voxels)[:, 0]
        contra = float(np.mean(world_x > 0)) if side == "L" else float(np.mean(world_x < 0)) if side == "R" else 0.0
        if (side == "L" and center[0] >= 0) or (side == "R" and center[0] <= 0):
            raise ValueError(f"Unexpected hemisphere for {name}: {center.tolist()}")
        category = "cerebellum" if name.startswith(("Cerebellum_", "Vermis_")) else "AAL3"
        records.append(ResolvedLabel(label_id, name, name, base, category, "gray_matter", side,
            False, True, base + ".nii.gz", len(source_voxels), *map(float, center), contra))
        label_stats.append({"label_id": label_id, "name": name, "side": side,
            "source_volume_mm3": len(source_voxels), "output_volume_mm3": len(voxels),
            "volume_ratio": float(len(voxels) / len(source_voxels)),
            "source_centroid_mm": source_center.tolist(), "output_centroid_mm": center.tolist(),
            "contralateral_voxel_fraction": contra})
    artifacts = export_binary_rois(label_image, tuple(records), STAGING)
    rebuilt = np.zeros(data.shape, dtype=np.uint8)
    for artifact in artifacts:
        image = nib.load(STAGING / artifact.relative_path)
        if image.shape != reference.shape or not np.array_equal(image.affine, reference.affine):
            raise ValueError(f"Incorrect ROI geometry: {artifact.relative_path}")
        for form in ("qform", "sform"):
            matrix, code = getattr(image, f"get_{form}")(coded=True)
            if int(code) != 2 or not np.array_equal(matrix, reference.affine):
                raise ValueError(f"Incorrect {form}: {artifact.relative_path}")
        mask = np.asanyarray(image.dataobj)
        if not set(map(int, np.unique(mask))).issubset({0, 1}):
            raise ValueError(f"Non-binary ROI: {artifact.relative_path}")
        if np.any(rebuilt[mask > 0]):
            raise ValueError("Exported ROI masks overlap")
        rebuilt[mask > 0] = artifact.label_id
    if not np.array_equal(rebuilt, data):
        raise ValueError("ROI masks do not exactly reconstruct the label image")
    metrics = anatomy_qc(reference)
    plot_labels(reference, label_image, QC / "AAL3_on_MNI152NLin2009bAsym.png", "Transformed AAL3 on 2009bAsym")
    counts = {side: sum(rec.hemisphere == side for rec in records) for side in ("L", "R", "M")}
    report = {"technical_validation": "passed", "human_anatomical_review": "pending",
        "label_count": len(artifacts), "hemisphere_counts": counts,
        "all_labels_preserved": True, "mutually_exclusive": True, "exact_mask_reconstruction": True,
        "geometry_matches_reference": True, **metrics, "labels": label_stats}
    write_json(QC / "validation.json", report)
    write_json(STAGING / "roi_manifest.json", [asdict(item) for item in artifacts])
    shutil.copy2(TABLE, STAGING / "labels_source.txt")
    with (STAGING / "labels.txt").open("x") as stream:
        for rec in records:
            stream.write(f"{rec.label_id} {rec.source_label_name} {rec.label_id}\n")
    registration = json.loads((REG / "registration_command.json").read_text())
    write_json(STAGING / "provenance.json", {
        "atlas": "AAL3 (Rolls 2020)", "source_space": "Colin27 1998",
        "target_space": "MNI152NLin2009bAsym", "resolution_mm": [1, 1, 1],
        "source_labels": str(LABELS), "moving_anatomy": str(MOVING),
        "fixed_anatomy_original": str(SPACE / "t1.nii"), "output_reference": str(FIXED),
        "registration": registration, "label_transfer_command": transfer,
        "label_interpolation": "NearestNeighbor", "forward_transforms": [str(WARP), str(AFFINE)],
        "qc_directory": str(QC), "human_anatomical_review": "pending",
        "official_native_2009b_release": False,
    })
    readme = f"""# AAL3 (Rolls 2020) in MNI152NLin2009bAsym

This is a locally derived 1 mm atlas, not an official native-2009b release.
AAL3v1_1mm was transferred from Colin27 1998 through a rigid, affine, and
SyN registration of the matched T1 anatomy to the installed Lead-DBS template.
The integer label map was sampled once with nearest-neighbor interpolation.
No label dilation, smoothing, or renumbering was performed.

There are {len(artifacts)} labels: {counts['L']} left, {counts['R']} right,
and {counts['M']} midline. Source IDs 35, 36, 81, and 82 are unused.
Binary masks exactly reconstruct labels.nii.gz and are mutually exclusive.

Technical checks passed. Human anatomical review remains pending, especially
for small brainstem and thalamic nuclei. Do not infer individual nuclear
accuracy from a successful template registration.

QC and registration assets: {WORK}
QC montage: {QC / 'AAL3_on_MNI152NLin2009bAsym.png'}
Validation report: {QC / 'validation.json'}

Existing AAL3, STNVOplus, and patient data were not modified. Lead-DBS UI
caches are not generated here. See provenance.json for commands and software.
"""
    with (STAGING / "README.md").open("x") as stream:
        stream.write(readme)
    STAGING.rename(OUTPUT)
    print(json.dumps({"atlas_root": str(OUTPUT), "qc": str(QC), "label_count": len(artifacts),
                      "hemisphere_counts": counts, **metrics}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "register", "export"))
    selected = parser.parse_args().step
    {"prepare": prepare, "register": register, "export": export}[selected]()
