"""Prepare isolated inputs and provisional masks for the documented D99 scan."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

import nibabel as nib
from nibabel.processing import resample_from_to, resample_to_output
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


def describe(path: Path) -> dict:
    stat = path.stat()
    result = {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }
    if path.name.endswith((".nii", ".nii.gz")):
        image = nib.load(path)
        result.update(shape=list(image.shape), affine=image.affine.tolist(),
                      voxel_size_mm=[float(v) for v in image.header.get_zooms()],
                      dtype=str(image.get_data_dtype()))
    return result


def binary_image(path: Path) -> tuple[nib.spatialimages.SpatialImage, np.ndarray]:
    image = nib.load(path)
    data = np.asarray(image.dataobj)
    if data.ndim != 3 or not np.isin(data, [0, 1]).all():
        raise ValueError(f"Expected a three-dimensional binary mask: {path}")
    return image, data.astype(bool)


def save_mask(path: Path, data: np.ndarray, reference) -> None:
    header = reference.header.copy()
    header.set_data_dtype(np.uint8)
    nib.save(nib.Nifti1Image(data.astype(np.uint8), reference.affine, header), path)


def atlas_union(paths: list[Path], reference) -> np.ndarray:
    """Place the installed grid-aligned atlas ROIs by their physical coordinates."""
    result = np.zeros(reference.shape, dtype=bool)
    for path in paths:
        image, data = binary_image(path)
        source_indices = np.column_stack(np.where(data))
        target_coordinates = nib.affines.apply_affine(
            np.linalg.inv(reference.affine) @ image.affine, source_indices)
        target_indices = np.rint(target_coordinates).astype(int)
        if not np.allclose(target_coordinates, target_indices, atol=1e-5, rtol=0):
            raise ValueError(f"Atlas ROI is not aligned to the D99 template grid: {path}")
        if (target_indices < 0).any() or (target_indices >= reference.shape).any():
            raise ValueError(f"Atlas ROI extends beyond the D99 template grid: {path}")
        result[tuple(target_indices.T)] = True
    return result


def mask_summary(data: np.ndarray, reference) -> dict:
    indices = np.column_stack(np.where(data))
    world = nib.affines.apply_affine(reference.affine, indices)
    return {
        "voxels": int(data.sum()),
        "volume_mm3": float(data.sum() * abs(np.linalg.det(reference.affine[:3, :3]))),
        "bounding_box_ras_mm": [world.min(axis=0).tolist(), world.max(axis=0).tolist()],
    }


def overlay_figure(path: Path, image_data: np.ndarray, affine: np.ndarray,
                   masks: list[tuple[np.ndarray, tuple[int, int, int], bool]],
                   extent_mask: np.ndarray, title: str, legend: str) -> None:
    """Render twelve RAS-oriented slices without writing intermediate volumes."""
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 19)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    cell, top, bottom = 330, 85, 36
    canvas = Image.new("RGB", (cell * 4, top + cell * 3 + bottom), (16, 16, 16))
    labels = []
    positive = image_data[extent_mask & (image_data > 0)]
    lo, hi = np.percentile(positive, [1, 99])
    gray = (np.clip((image_data - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    locations = np.column_stack(np.where(extent_mask))
    lower, upper = locations.min(axis=0), locations.max(axis=0)
    padding = np.ceil(12 / nib.affines.voxel_sizes(affine)).astype(int)
    crop_lower = np.maximum(0, lower - padding)
    crop_upper = np.minimum(image_data.shape, upper + padding + 1)
    for row, axis in enumerate([2, 1, 0]):
        for column, fraction in enumerate([0.08, 0.35, 0.65, 0.92]):
            index = int(round(lower[axis] + fraction * (upper[axis] - lower[axis])))
            selection = [slice(crop_lower[j], crop_upper[j]) for j in range(3)]
            selection[axis] = index
            plane = gray[tuple(selection)].T[::-1]
            rgb = np.repeat(plane[..., None], 3, axis=2).astype(float)
            for mask, color, fill in masks:
                mask_plane = mask[tuple(selection)].T[::-1]
                if fill:
                    rgb[mask_plane] = rgb[mask_plane] * 0.8 + np.array(color) * 0.2
                edge = mask_plane & ~ndimage.binary_erosion(mask_plane)
                rgb[edge] = color
            tile = Image.fromarray(rgb.astype(np.uint8))
            scale = min((cell - 12) / tile.width, (cell - 42) / tile.height)
            tile = tile.resize((round(tile.width * scale), round(tile.height * scale)), Image.Resampling.NEAREST)
            left, up = column * cell, top + row * cell
            canvas.paste(tile, (left + (cell - tile.width) // 2, up + 32))
            coordinate = affine[axis, axis] * index + affine[axis, 3]
            label = ["Sagittal x", "Coronal y", "Axial z"][axis]
            labels.append(((left + 10, up + 4), f"{label} = {coordinate:.1f} mm"))
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), title, font=font, fill="white")
    draw.text((16, 43), legend, font=small, fill="white")
    for position, label in labels:
        draw.text(position, label, font=small, fill="white")
    draw.text((16, canvas.height - 27), "RAS views; slice positions span the mask extent. Visual QC is required.", font=small, fill="white")
    canvas.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject-dir", required=True, type=Path)
    parser.add_argument("--template-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ants-apply", required=True, type=Path)
    args = parser.parse_args()
    subject, template, output = args.subject_dir, args.template_dir, args.output_dir
    stem = subject.name
    sources = {
        "inputs/fixed.nii.gz": template / "t1.nii",
        "inputs/moving.nii.gz": subject / "coregistration/anat" / f"{stem}_ses-preop_space-anchorNative_desc-preproc_acq-ax_T1w.nii",
        "inputs/baseline_forward.nii.gz": subject / "normalization/transformations" / f"{stem}_from-anchorNative_to-D99v2_desc-ants.nii.gz",
        "inputs/baseline_inverse.nii.gz": subject / "normalization/transformations" / f"{stem}_from-D99v2_to-anchorNative_desc-ants.nii.gz",
        "baseline/warped.nii.gz": subject / "normalization/anat" / f"{stem}_ses-preop_space-D99v2_desc-preproc_acq-ax_T1w.nii",
    }
    mask_names = ["fixed_brain", "moving_brain_projected", "moving_brain", "thalamus", "stn", "sn",
                  "deep_2mm", "deep_4mm", "eval_thalamus", "eval_stn", "eval_sn"]
    owned = list(sources) + [f"masks/{name}.nii.gz" for name in mask_names] + [
        "inputs/source_metadata.json", "masks/project_brainmask.log",
        "figures/native_brain_mask_qa.png", "figures/template_deep_masks_qa.png", "figures/fixed_brain_mask_qa.png"]
    occupied = [str(output / name) for name in owned if (output / name).exists()]
    if occupied:
        raise FileExistsError("Refusing to overwrite existing preparation outputs: " + ", ".join(occupied))

    fixed, moving = nib.load(sources["inputs/fixed.nii.gz"]), nib.load(sources["inputs/moving.nii.gz"])
    if len(fixed.shape) != 3 or len(moving.shape) != 3:
        raise ValueError("Fixed and moving intensity images must be three-dimensional.")
    installed_brain_image, installed_brain = binary_image(template / "t1_brainmask.nii")
    if installed_brain_image.shape != fixed.shape or not np.allclose(installed_brain_image.affine, fixed.affine):
        raise ValueError("Installed comparison mask does not match the fixed image grid.")
    positive_support = np.asarray(fixed.dataobj) > 0
    fixed_components, fixed_component_count = ndimage.label(positive_support)
    fixed_component_sizes = np.bincount(fixed_components.ravel())
    fixed_largest = fixed_components == (1 + fixed_component_sizes[1:].argmax())
    fixed_brain = ndimage.binary_fill_holes(fixed_largest)
    fixed_cleanup = {
        "positive_support_voxels": int(positive_support.sum()),
        "component_count": fixed_component_count,
        "discarded_component_voxels": int(positive_support.sum() - fixed_largest.sum()),
        "filled_hole_voxels": int(fixed_brain.sum() - fixed_largest.sum()),
        "positive_support_retained_fraction": float(fixed_largest.sum() / positive_support.sum()),
    }
    atlas_root = template / "atlases"
    deep_atlas = atlas_root / "D99 v2.0 VA_VL_STN_SN_RN_GP (Saleem KS 2021)"
    thalamus_atlas = atlas_root / "D99 v2.0 thalamus (Saleem KS 2021)"
    atlas_files = {
        "thalamus": sorted(thalamus_atlas.glob("[lr]h/*_Thalamus.nii")),
        "stn": sorted(deep_atlas.glob("[lr]h/STN.nii")),
        "sn": sorted(deep_atlas.glob("[lr]h/SN*.nii")),
    }
    if [len(atlas_files[k]) for k in ["thalamus", "stn", "sn"]] != [66, 2, 8]:
        raise ValueError("The installed atlas does not match the documented 66/2/8 thalamus/STN/SN ROI files.")
    groups = {name: atlas_union(paths, fixed) for name, paths in atlas_files.items()}
    deep = np.logical_or.reduce(list(groups.values()))
    if (deep & ~fixed_brain).any():
        raise ValueError("Source deep target ROIs extend outside the fixed brain mask.")

    for name in ["inputs", "masks", "baseline", "figures"]:
        (output / name).mkdir(parents=True, exist_ok=True)
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": {name: describe(path) for name, path in sources.items()},
        "fixed_mask_origin": "Largest 6-connected component of strictly positive D99 t1 intensity, with enclosed holes filled. The brain-only ex-vivo template supplies the operational whole-brain support.",
        "fixed_cleanup": fixed_cleanup,
        "installed_template_brain_mask_comparison": {
            "source": describe(template / "t1_brainmask.nii"),
            "summary": mask_summary(installed_brain, fixed),
            "used_for_registration_or_projection": False,
            "known_failure": "Truncates visible frontal and temporal cortex and cerebellar regions.",
        },
        "atlas_sources": {name: [describe(path) for path in paths] for name, paths in atlas_files.items()},
        "ants_apply": describe(args.ants_apply),
        "baseline_normalization_log": json.loads((subject / "normalization/log" / f"{stem}_desc-normmethod.json").read_text()),
        "native_mask_origin": "Corrected D99 operational brain mask from positive template support projected through the preserved existing ANTs inverse transform; largest 6-connected component and filled enclosed holes. Not independent native segmentation.",
        "native_mask_review_status": "pending_visual_review",
    }
    for name, source in sources.items():
        if source.name.endswith(".nii.gz"):
            shutil.copy2(source, output / name)
        else:
            nib.save(nib.load(source), output / name)
    save_mask(output / "masks/fixed_brain.nii.gz", fixed_brain, fixed)
    command = [str(args.ants_apply), "--dimensionality", "3", "--input", str(output / "masks/fixed_brain.nii.gz"),
               "--reference-image", str(output / "inputs/moving.nii.gz"),
               "--transform", str(output / "inputs/baseline_inverse.nii.gz"),
               "--interpolation", "NearestNeighbor", "--output", str(output / "masks/moving_brain_projected.nii.gz")]
    with (output / "masks/project_brainmask.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    projected_image, projected = binary_image(output / "masks/moving_brain_projected.nii.gz")
    components, component_count = ndimage.label(projected)
    sizes = np.bincount(components.ravel())
    if component_count == 0:
        raise ValueError("Projected native brain mask is empty.")
    largest = components == (1 + sizes[1:].argmax())
    moving_brain = ndimage.binary_fill_holes(largest)
    save_mask(output / "masks/moving_brain.nii.gz", moving_brain, moving)
    masks = {"fixed_brain": fixed_brain, **groups}
    spacing = nib.affines.voxel_sizes(fixed.affine)
    distance = ndimage.distance_transform_edt(~deep, sampling=spacing)
    for radius in [2, 4]:
        masks[f"deep_{radius}mm"] = (distance <= radius) & fixed_brain
    for name, group in groups.items():
        masks[f"eval_{name}"] = (ndimage.distance_transform_edt(~group, sampling=spacing) <= 2) & fixed_brain
    for name, mask in masks.items():
        if name != "fixed_brain":
            save_mask(output / f"masks/{name}.nii.gz", mask, fixed)
    metadata["mask_summaries"] = {name: mask_summary(mask, fixed) for name, mask in masks.items()}
    metadata["mask_summaries"].update(moving_brain_projected=mask_summary(projected, moving), moving_brain=mask_summary(moving_brain, moving))
    metadata["native_cleanup"] = {"component_count": component_count, "discarded_component_voxels": int(projected.sum() - largest.sum()),
                                  "filled_hole_voxels": int(moving_brain.sum() - largest.sum())}
    metadata["projection_command"] = command
    metadata["target_inclusion"] = {name: {region: float(mask[group].mean()) for region, group in groups.items()}
                                    for name, mask in masks.items() if name.startswith("deep_")}

    display_image = resample_to_output(moving, voxel_sizes=(0.6, 0.6, 0.6), order=1)
    display_grid = (display_image.shape, display_image.affine)
    display_projected = np.asarray(resample_from_to(projected_image, display_grid, order=0).dataobj) > 0
    clean_image = nib.Nifti1Image(moving_brain.astype(np.uint8), moving.affine)
    display_clean = np.asarray(resample_from_to(clean_image, display_grid, order=0).dataobj) > 0
    overlay_figure(output / "figures/native_brain_mask_qa.png", np.asarray(display_image.dataobj), display_image.affine,
                   [(display_projected, (255, 90, 210), False), (display_clean, (80, 255, 100), True)],
                   display_clean, "Provisional native brain mask: projected from the existing ANTs normalization",
                   "Green: cleaned mask; pink: original projection boundary. This is not independent segmentation.")
    overlay_figure(output / "figures/fixed_brain_mask_qa.png", np.asarray(fixed.dataobj), fixed.affine,
                   [(fixed_brain, (80, 255, 100), True), (installed_brain, (255, 90, 210), False)],
                   fixed_brain, "Corrected D99 whole-brain mask from template intensity support",
                   "Green: corrected mask; pink: installed mask for comparison only. Frontal, temporal and cerebellar coverage are included.")
    overlay_figure(output / "figures/template_deep_masks_qa.png", np.asarray(fixed.dataobj), fixed.affine,
                   [(masks["deep_4mm"], (255, 140, 60), False), (masks["deep_2mm"], (130, 150, 255), False),
                    (groups["thalamus"], (70, 230, 250), True), (groups["stn"], (255, 80, 220), True), (groups["sn"], (255, 230, 60), True)],
                   deep, "D99 target masks and deep optimization regions",
                   "Cyan: thalamus; pink: STN; yellow: SN; blue outline: 2 mm; orange outline: 4 mm.")
    metadata["copied_inputs"] = {name: describe(output / name) for name in sources}
    (output / "inputs/source_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"output_dir": str(output), "fixed_cleanup": fixed_cleanup, "native_cleanup": metadata["native_cleanup"],
                      "mask_summaries": metadata["mask_summaries"], "target_inclusion": metadata["target_inclusion"]}, indent=2))


if __name__ == "__main__":
    main()
