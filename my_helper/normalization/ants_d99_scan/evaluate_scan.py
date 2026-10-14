#!/usr/bin/env python
"""Measure and render the documented, isolated D99 registration candidates."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ants_d99_matplotlib"))

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.io import loadmat
from send2trash import send2trash


REGIONS = ("thalamus", "stn", "sn")
COLORS = {"thalamus": "#ffcf55", "stn": "#35ddd2", "sn": "#ff6db4"}
STRIDE = 2
NMI_BINS = 64
EVALUATION_NOTE = (
    "Image-based comparison only; no independent native nucleus labels or landmarks. "
    "The atlas-derived native brain mask makes brain Dice a QC statistic, not independent accuracy."
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_volume(path: Path, reference: nib.spatialimages.SpatialImage | None = None):
    image = nib.load(path)
    data = np.asarray(image.dataobj, dtype=np.float32)
    if reference is not None:
        if image.shape[:3] != reference.shape[:3] or not np.allclose(image.affine, reference.affine, atol=1e-5):
            raise ValueError(f"Image grid differs from its declared reference: {path}")
    return image, data


def read_mask(path: Path, reference: nib.spatialimages.SpatialImage) -> np.ndarray:
    _, data = read_volume(path, reference)
    if data.ndim != 3 or not np.isfinite(data).all():
        raise ValueError(f"Mask must be a finite three-dimensional volume: {path}")
    return data > 0


def intensity_limits(data: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    values = data[mask & np.isfinite(data)]
    if values.size == 0:
        raise ValueError("Intensity-reference brain mask contains no finite voxels")
    low, high = np.percentile(values, [0.5, 99.5])
    if high <= low:
        raise ValueError("Intensity-reference brain image has no usable contrast")
    return float(low), float(high)


def normalize(data: np.ndarray, limits: tuple[float, float]) -> np.ndarray:
    result = np.array(data, dtype=np.float32, copy=True)
    result -= limits[0]
    result /= limits[1] - limits[0]
    np.clip(result, 0, 1, out=result)
    result[~np.isfinite(result)] = 0
    return result


def normalized_mutual_information(fixed: np.ndarray, moving: np.ndarray) -> float | None:
    if fixed.size == 0:
        return None
    histogram, _, _ = np.histogram2d(fixed, moving, bins=NMI_BINS, range=((0, 1), (0, 1)))
    probabilities = histogram / histogram.sum()
    p_fixed = probabilities.sum(axis=1)
    p_moving = probabilities.sum(axis=0)
    entropy_fixed = -np.sum(p_fixed[p_fixed > 0] * np.log(p_fixed[p_fixed > 0]))
    entropy_moving = -np.sum(p_moving[p_moving > 0] * np.log(p_moving[p_moving > 0]))
    nonzero = probabilities > 0
    product = p_fixed[:, None] * p_moving[None, :]
    mi = np.sum(probabilities[nonzero] * np.log(probabilities[nonzero] / product[nonzero]))
    denominator = entropy_fixed + entropy_moving
    return float(np.clip(2 * mi / denominator, 0, 1)) if denominator > 0 else 0.0


def squared_local_correlation(fixed: np.ndarray, moving: np.ndarray, spacing: np.ndarray) -> np.ndarray:
    sigma = 1.0 / spacing
    settings = {"sigma": sigma, "mode": "nearest", "truncate": 4.0}
    fixed_mean = gaussian_filter(fixed, **settings)
    moving_mean = gaussian_filter(moving, **settings)
    fixed_variance = gaussian_filter(fixed * fixed, **settings)
    fixed_variance -= fixed_mean * fixed_mean
    moving_variance = gaussian_filter(moving * moving, **settings)
    moving_variance -= moving_mean * moving_mean
    covariance = gaussian_filter(fixed * moving, **settings)
    covariance -= fixed_mean * moving_mean
    valid = (fixed_variance > np.finfo(np.float32).eps) & (moving_variance > np.finfo(np.float32).eps)
    denominator = fixed_variance * moving_variance
    np.square(covariance, out=covariance)
    np.divide(covariance, denominator, out=covariance, where=valid)
    covariance[~valid] = 0
    np.clip(covariance, 0, 1, out=covariance)
    return covariance


def finite_summary(values: np.ndarray, total: int | None = None) -> dict:
    finite = np.asarray(values)[np.isfinite(values)]
    count = int(finite.size)
    total = int(values.size if total is None else total)
    result = {"count": count, "total": total, "finite_fraction": count / total if total else None}
    if count:
        p01, median, p95, p99 = np.percentile(finite, [1, 50, 95, 99])
        result.update(mean=float(np.mean(finite, dtype=np.float64)), median=float(median),
                      p01=float(p01), p95=float(p95), p99=float(p99),
                      minimum=float(finite.min()), maximum=float(finite.max()))
    else:
        result.update({key: None for key in ("mean", "median", "p01", "p95", "p99", "minimum", "maximum")})
    return result


def load_ras_field(path: Path, reference: nib.spatialimages.SpatialImage) -> np.ndarray:
    _, field = read_volume(path, reference)
    if field.ndim == 5 and field.shape[-2] == 1:
        field = field[..., 0, :]
    if field.shape != reference.shape[:3] + (3,):
        raise ValueError(f"Expected a three-component ANTs displacement field: {path}")
    field[..., :2] *= -1
    return field


def world_points(indices: np.ndarray, affine: np.ndarray) -> np.ndarray:
    return indices @ affine[:3, :3].T + affine[:3, 3]


def voxel_points(points: np.ndarray, affine: np.ndarray) -> np.ndarray:
    inverse = np.linalg.inv(affine)
    return points @ inverse[:3, :3].T + inverse[:3, 3]


def sampled_indices(mask: np.ndarray) -> np.ndarray:
    return np.argwhere(mask[::STRIDE, ::STRIDE, ::STRIDE]) * STRIDE


def field_at_world(field: np.ndarray, affine: np.ndarray, points: np.ndarray):
    indices = voxel_points(points, affine)
    inside = np.isfinite(indices).all(axis=1)
    inside &= ((indices >= 0) & (indices <= np.asarray(field.shape[:3]) - 1)).all(axis=1)
    result = np.full((points.shape[0], 3), np.nan, dtype=np.float32)
    coordinates = indices[inside].T
    for component in range(3):
        result[inside, component] = map_coordinates(field[..., component], coordinates,
                                                   order=1, mode="constant", cval=np.nan, prefilter=False)
    return result, inside & np.isfinite(result).all(axis=1)


def jacobian_map(field: np.ndarray, affine: np.ndarray, slab_depth: int = 16) -> np.ndarray:
    """Differentiate x + d(x) in physical RAS coordinates on the full grid."""
    inverse_basis = np.linalg.inv(affine[:3, :3]).astype(np.float32)
    result = np.empty(field.shape[:3], dtype=np.float32)
    for first in range(0, field.shape[2], slab_depth):
        last = min(first + slab_depth, field.shape[2])
        halo_first, halo_last = max(0, first - 1), min(field.shape[2], last + 1)
        block = field[:, :, halo_first:halo_last]
        jacobian = np.empty(block.shape[:3] + (3, 3), dtype=np.float32)
        for component in range(3):
            derivatives = np.gradient(block[..., component], axis=(0, 1, 2), edge_order=1)
            for world_axis in range(3):
                jacobian[..., component, world_axis] = sum(
                    derivatives[axis] * inverse_basis[axis, world_axis] for axis in range(3)
                )
            jacobian[..., component, component] += 1
        result[:, :, first:last] = np.linalg.det(jacobian[:, :, first - halo_first:last - halo_first])
    return result


def affine_statistics(path: Path | None) -> dict:
    if path is None:
        return {"available": False, "reason": "No independent affine component was supplied"}
    matrices = []
    if path.suffix == ".h5":
        with h5py.File(path, "r") as stream:
            groups = stream["TransformGroup"]
            for key in sorted(groups, key=int):
                group = groups[key]
                kind = np.asarray(group["TransformType"]).ravel()[0]
                kind = kind.decode() if isinstance(kind, bytes) else str(kind)
                if "CompositeTransform" in kind:
                    continue
                if "AffineTransform" not in kind:
                    raise ValueError(f"Expected collapsed affine components in {path}; found {kind}")
                matrices.append(np.asarray(group["TransformParameters"]).ravel()[:9].reshape(3, 3))
    else:
        content = loadmat(path)
        key = next(key for key in content if key.startswith("AffineTransform"))
        matrices.append(content[key].ravel()[:9].reshape(3, 3))
    if not matrices:
        raise ValueError(f"No affine transform found in {path}")
    combined = np.eye(3)
    for matrix in matrices:
        combined = combined @ matrix
    return {"available": True, "path": str(path), "determinant": float(np.linalg.det(combined)),
            "principal_scales": np.linalg.svd(combined, compute_uv=False).tolist()}


class EvaluationContext:
    def __init__(self, output_root: Path):
        self.root = output_root
        self.fixed_image, fixed = read_volume(output_root / "inputs/fixed.nii.gz")
        self.moving_image, moving = read_volume(output_root / "inputs/moving.nii.gz")
        self.brain = read_mask(output_root / "masks/fixed_brain.nii.gz", self.fixed_image)
        self.native_brain = read_mask(output_root / "masks/moving_brain.nii.gz", self.moving_image)
        self.anatomical = {region: read_mask(output_root / f"masks/{region}.nii.gz", self.fixed_image)
                           for region in REGIONS}
        self.regions = {"wholebrain": self.brain}
        self.regions.update({region: read_mask(output_root / f"masks/eval_{region}.nii.gz", self.fixed_image)
                             for region in REGIONS})
        self.fixed_limits = intensity_limits(fixed, self.brain)
        self.moving_limits = intensity_limits(moving, self.native_brain)
        self.fixed_finite = np.isfinite(fixed)
        self.fixed = normalize(fixed, self.fixed_limits)
        self.spacing = nib.affines.voxel_sizes(self.fixed_image.affine)
        self.display_fixed = self.canonical(self.fixed)
        self.display_brain = self.canonical(self.brain)
        self.display_masks = {region: self.canonical(mask) for region, mask in self.anatomical.items()}
        self.display_affine = nib.as_closest_canonical(self.fixed_image).affine
        self.cuts = {"wholebrain": self.center(self.display_brain)}
        self.cuts.update({region: self.center(mask) for region, mask in self.display_masks.items()})
        self.crop_centers = {name: center.copy() for name, center in self.cuts.items()}
        for region, mask in self.display_masks.items():
            self.cuts[region][0] = int(np.argmax(mask.sum(axis=(1, 2))))

    def canonical(self, data: np.ndarray) -> np.ndarray:
        orientation = nib.orientations.io_orientation(self.fixed_image.affine)
        return nib.orientations.apply_orientation(data, orientation)

    @staticmethod
    def center(mask: np.ndarray) -> np.ndarray:
        positions = np.argwhere(mask)
        if positions.size == 0:
            raise ValueError("A required anatomical display mask is empty")
        return np.rint(np.median(positions, axis=0)).astype(int)

    def protocol(self) -> dict:
        return {"nmi_bins": NMI_BINS, "sample_stride": STRIDE, "sample_origin": [0, 0, 0],
                "fixed_intensity_limits": self.fixed_limits, "moving_intensity_limits": self.moving_limits,
                "local_correlation_sigma_mm": 1.0, "local_correlation_squared": True,
                "local_variance_zero_threshold": float(np.finfo(np.float32).eps),
                "brain_dice_role": "QC only; atlas-derived native mask, not independent ground truth",
                "cuts_ras_mm": {name: world_points(center[None, :], self.display_affine)[0].tolist()
                                for name, center in self.cuts.items()}, "note": EVALUATION_NOTE}


def measure_similarity(context: EvaluationContext, warped: np.ndarray) -> dict:
    moving_finite = np.isfinite(warped)
    normalized = normalize(warped, context.moving_limits)
    local = squared_local_correlation(context.fixed, normalized, context.spacing)
    selection = (slice(None, None, STRIDE),) * 3
    fixed_sample = context.fixed[selection]
    moving_sample = normalized[selection]
    local_sample = local[selection]
    finite_sample = (context.fixed_finite & moving_finite)[selection]
    result = {}
    for name, mask in context.regions.items():
        sampled_mask = mask[selection]
        valid = sampled_mask & finite_sample
        total, count = int(sampled_mask.sum()), int(valid.sum())
        result[name] = {"sample_count": count, "sample_total": total,
                        "finite_image_fraction": float(np.mean((context.fixed_finite & moving_finite)[mask])) if mask.any() else None,
                        "finite_sample_fraction": count / total if total else None,
                        "nmi": normalized_mutual_information(fixed_sample[valid], moving_sample[valid]),
                        "local_correlation_squared": float(local_sample[valid].mean(dtype=np.float64)) if count else None}
    return result


def measure_fields(context: EvaluationContext, candidate: Path) -> dict:
    forward = load_ras_field(candidate / "forward.nii.gz", context.fixed_image)
    inverse = load_ras_field(candidate / "inverse.nii.gz", context.moving_image)
    jacobian = jacobian_map(forward, context.fixed_image.affine)
    jacobian_masks = {"wholebrain": context.brain, **context.anatomical}
    jacobian_stats = {}
    for name, mask in jacobian_masks.items():
        values = jacobian[mask]
        stats = finite_summary(values)
        stats["nonpositive_count"] = int(np.count_nonzero(np.isfinite(values) & (values <= 0)))
        stats["nonpositive_fraction"] = stats["nonpositive_count"] / stats["count"] if stats["count"] else None
        jacobian_stats[name] = stats
    del jacobian

    indices = sampled_indices(context.brain)
    index_tuple = tuple(indices.T)
    points = world_points(indices, context.fixed_image.affine)
    displacement = forward[index_tuple]
    mapped = points + displacement
    sampled_inverse, inside = field_at_world(inverse, context.moving_image.affine, mapped)
    errors = np.linalg.norm(displacement + sampled_inverse, axis=1)
    roundtrip, coverage = {}, {}
    for name, mask in context.regions.items():
        selected = mask[index_tuple]
        valid = selected & inside & np.isfinite(displacement).all(axis=1)
        roundtrip[name] = finite_summary(errors[valid], total=int(selected.sum()))
        count = int(selected.sum())
        coverage[name] = {"sample_total": count,
                          "finite_forward_field_fraction": float(np.mean(np.isfinite(displacement[selected]).all(axis=1))) if count else None,
                          "mapped_inside_native_and_finite_inverse_fraction": float(valid.sum() / count) if count else None,
                          "displacement_mm": finite_summary(np.linalg.norm(displacement[selected], axis=1))}

    native_indices = sampled_indices(context.native_brain)
    native_points = world_points(native_indices, context.moving_image.affine)
    inverse_displacement = inverse[tuple(native_indices.T)]
    sampled_forward, valid_native = field_at_world(forward, context.fixed_image.affine,
                                                  native_points + inverse_displacement)
    native_errors = np.linalg.norm(inverse_displacement + sampled_forward, axis=1)
    valid_native &= np.isfinite(inverse_displacement).all(axis=1)
    native_roundtrip = finite_summary(native_errors[valid_native], total=len(native_indices))
    inverse_finite = float(np.mean(np.isfinite(inverse[context.native_brain]).all(axis=1)))
    return {"jacobian": jacobian_stats, "field_coverage": coverage,
            "native_brain_inverse_field_finite_fraction": inverse_finite,
            "fixed_to_native_to_fixed_mm": roundtrip, "native_to_fixed_to_native_mm": native_roundtrip}


def draw_plane(axis, data: np.ndarray, context: EvaluationContext, center: np.ndarray,
               plane: int, region: str | None, half_width_mm: float | None = None):
    dimensions = [dimension for dimension in range(3) if dimension != plane]
    index = int(center[plane])
    section = np.take(data, index, axis=plane).T
    step = np.diag(context.display_affine)[:3]
    offset = context.display_affine[:3, 3]
    extent = [offset[dimensions[0]] - 0.5 * step[dimensions[0]],
              offset[dimensions[0]] + (data.shape[dimensions[0]] - 0.5) * step[dimensions[0]],
              offset[dimensions[1]] - 0.5 * step[dimensions[1]],
              offset[dimensions[1]] + (data.shape[dimensions[1]] - 0.5) * step[dimensions[1]]]
    axis.imshow(section, cmap="gray", vmin=0, vmax=1, origin="lower", extent=extent,
                interpolation="nearest", aspect="equal")
    for name, mask in context.display_masks.items():
        contour = np.take(mask, index, axis=plane).T
        if contour.any() and not contour.all():
            axis.contour(contour, levels=[0.5], colors=[COLORS[name]], linewidths=0.8,
                         alpha=0.85, origin="lower", extent=extent)
    if region is None:
        contour = np.take(context.display_brain, index, axis=plane).T
        if contour.any() and not contour.all():
            axis.contour(contour, levels=[0.5], colors=["white"], linewidths=0.6,
                         alpha=0.5, origin="lower", extent=extent)
    if half_width_mm is not None:
        physical_center = world_points(context.crop_centers[region][None, :], context.display_affine)[0]
        axis.set_xlim(physical_center[dimensions[0]] + np.array([-half_width_mm, half_width_mm]))
        axis.set_ylim(physical_center[dimensions[1]] + np.array([-half_width_mm, half_width_mm]))
    axis.set_facecolor("black")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_xlabel(f"{'RAS'[dimensions[0]]} / {'RAS'[dimensions[1]]}", fontsize=7, labelpad=1)


def score_text(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "unavailable"


def render_candidate(context: EvaluationContext, candidate: Path, warped: np.ndarray, measurements: dict) -> None:
    display = context.canonical(normalize(warped, context.moving_limits))
    title = f"{measurements['id']} | deep score {score_text(measurements['deep_score'])} | image-based QC"
    figure, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for column, (plane, name) in enumerate(((0, "Sagittal"), (1, "Coronal"), (2, "Axial"))):
        for row, image in enumerate((context.display_fixed, display)):
            draw_plane(axes[row, column], image, context, context.cuts["wholebrain"], plane, None)
            axes[row, column].set_title(f"{'D99 reference' if row == 0 else 'Candidate'} — {name}", fontsize=10)
    figure.suptitle(title, fontsize=12)
    figure.savefig(candidate / "qa_wholebrain.png", dpi=140)
    plt.close(figure)

    figure, axes = plt.subplots(3, 6, figsize=(18, 10), constrained_layout=True)
    for row, region in enumerate(REGIONS):
        for pair, (plane, name) in enumerate(((0, "Sagittal"), (1, "Coronal"), (2, "Axial"))):
            for side, image in enumerate((context.display_fixed, display)):
                axis = axes[row, 2 * pair + side]
                draw_plane(axis, image, context, context.cuts[region], plane, region, 12.0)
                axis.set_title(f"{region.upper()} {name}\n{'D99 reference' if side == 0 else 'Candidate'}", fontsize=9)
    figure.suptitle(title + "\nYellow: thalamus; cyan: STN; pink: SN. Atlas contours are not independent truth.", fontsize=12)
    figure.savefig(candidate / "qa_deep.png", dpi=140)
    plt.close(figure)


def evaluate_candidate(context: EvaluationContext, candidate: Path) -> dict:
    outputs = [candidate / name for name in ("evaluation.json", "qa_wholebrain.png", "qa_deep.png")]
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError("Preserve existing evaluation outputs before remeasurement: " + ", ".join(existing))
    metadata = read_json(candidate / "candidate.json")
    _, warped = read_volume(candidate / "warped.nii.gz", context.fixed_image)
    warped_mask = read_mask(candidate / "warped_mask.nii.gz", context.fixed_image)
    similarity = measure_similarity(context, warped)
    deep_values = [similarity[region][metric] for region in REGIONS
                   for metric in ("nmi", "local_correlation_squared")]
    deep_score = float(np.mean(deep_values)) if all(value is not None for value in deep_values) else None
    denominator = int(context.brain.sum()) + int(warped_mask.sum())
    dice = 2 * np.count_nonzero(context.brain & warped_mask) / denominator if denominator else None
    affine_path = Path(metadata["affine_file"]) if metadata.get("affine_file") else None
    if affine_path is not None and not affine_path.is_absolute():
        affine_path = candidate / affine_path
    affine = affine_statistics(affine_path)
    measurements = {"id": metadata.get("id", candidate.name), "stage": metadata.get("stage"),
                    "parent": metadata.get("parent"), "candidate_dir": str(candidate),
                    "metadata": metadata, "protocol": context.protocol(), "similarity": similarity,
                    "deep_score": deep_score, "brain_dice": dice, "affine": affine,
                    **measure_fields(context, candidate)}
    flags = []
    if deep_score is None:
        flags.append("unavailable_deep_score")
    if any(item["finite_image_fraction"] != 1 for item in similarity.values()):
        flags.append("nonfinite_evaluation_image")
    if affine.get("available") and affine["determinant"] <= 0:
        flags.append("nonpositive_affine_determinant")
    if measurements["jacobian"]["wholebrain"]["nonpositive_count"]:
        flags.append("nonpositive_brain_jacobian")
    if measurements["jacobian"]["wholebrain"]["finite_fraction"] != 1:
        flags.append("nonfinite_brain_jacobian")
    if any(item["finite_forward_field_fraction"] != 1 for item in measurements["field_coverage"].values()):
        flags.append("nonfinite_forward_field")
    if measurements["native_brain_inverse_field_finite_fraction"] != 1:
        flags.append("nonfinite_native_inverse_field")
    measurements["numerical_flags"] = flags
    render_candidate(context, candidate, warped, measurements)
    write_json(candidate / "evaluation.json", measurements)
    return measurements


def comparison_row(record: dict, rank: int) -> dict:
    row = {"rank_by_deep_score": rank, "id": record["id"], "stage": record.get("stage"),
           "parent": record.get("parent"), "deep_score": record["deep_score"],
           "brain_dice_qc_only": record["brain_dice"], "numerical_flags": ";".join(record["numerical_flags"]),
           "affine_determinant": record["affine"].get("determinant"), "candidate_dir": record["candidate_dir"],
           "native_brain_inverse_field_finite_fraction": record["native_brain_inverse_field_finite_fraction"]}
    for region, metrics in record["similarity"].items():
        for name in ("nmi", "local_correlation_squared", "finite_image_fraction"):
            row[f"{region}_{name}"] = metrics[name]
    for region, metrics in record["jacobian"].items():
        for name in ("median", "p01", "p99", "minimum", "maximum", "nonpositive_count", "finite_fraction"):
            row[f"{region}_jacobian_{name}"] = metrics[name]
    for region, metrics in record["fixed_to_native_to_fixed_mm"].items():
        for name in ("mean", "median", "p95", "maximum", "finite_fraction"):
            row[f"{region}_roundtrip_{name}"] = metrics[name]
    return row


def render_comparison(context: EvaluationContext, records: list[dict], kind: str, destination: Path) -> None:
    figure, axes = plt.subplots(len(records), 3, figsize=(12, 2.5 * len(records)),
                                squeeze=False, constrained_layout=True)
    for row, record in enumerate(records):
        _, warped = read_volume(Path(record["candidate_dir"]) / "warped.nii.gz", context.fixed_image)
        display = context.canonical(normalize(warped, context.moving_limits))
        for column in range(3):
            if kind == "wholebrain":
                draw_plane(axes[row, column], display, context, context.cuts["wholebrain"], column, None)
            else:
                region = REGIONS[column]
                draw_plane(axes[row, column], display, context, context.cuts[region], 2, region, 12.0)
                if row == 0:
                    axes[row, column].set_title(region.upper(), fontsize=11)
        row_label = record["id"].replace("__", "\n") + f"\nscore {score_text(record['deep_score'])}"
        axes[row, 0].set_ylabel(row_label, fontsize=8, rotation=0, ha="right", va="center", labelpad=8)
        if record["numerical_flags"]:
            axes[row, 0].set_title("; ".join(record["numerical_flags"]), fontsize=7, color="darkred")
    figure.suptitle("Image-based candidate comparison | identical cuts, windows and atlas contours", fontsize=12)
    figure.savefig(destination, dpi=130, bbox_inches="tight")
    plt.close(figure)


def compare_candidates(context: EvaluationContext, candidates: list[Path]) -> dict:
    records = [read_json(candidate / "evaluation.json") for candidate in candidates]
    records.sort(key=lambda record: (record["deep_score"] is None,
                                    -(record["deep_score"] or 0), record["id"]))
    previous = [context.root / "evaluation.csv", context.root / "ranking.json"]
    previous += list(context.root.glob("qa_comparison_wholebrain*.png"))
    previous += list(context.root.glob("qa_comparison_deep*.png"))
    for path in previous:
        if path.exists():
            send2trash(str(path))
    rows = [comparison_row(record, rank + 1) for rank, record in enumerate(records)]
    with (context.root / "evaluation.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figures = []
    for first in range(0, len(records), 8):
        page = records[first:first + 8]
        suffix = "" if first == 0 else f"_page_{first // 8 + 1:02d}"
        for kind in ("wholebrain", "deep"):
            path = context.root / f"qa_comparison_{kind}{suffix}.png"
            render_comparison(context, page, kind, path)
            figures.append(str(path))
    result = {"note": EVALUATION_NOTE,
              "ranking_rule": "Descending declared deep score; numerical flags and human anatomical review remain separate",
              "protocol": context.protocol(), "candidates": rows, "figures": figures}
    write_json(context.root / "ranking.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--compare", nargs="+", type=Path)
    args = parser.parse_args()
    if args.candidate_dir is None and args.compare is None:
        parser.error("Provide --candidate-dir, --compare, or both")
    context = EvaluationContext(args.output_root.resolve())
    if args.candidate_dir is not None:
        result = evaluate_candidate(context, args.candidate_dir.resolve())
        print(json.dumps({"id": result["id"], "deep_score": result["deep_score"],
                          "numerical_flags": result["numerical_flags"]}, allow_nan=False))
    if args.compare is not None:
        result = compare_candidates(context, [path.resolve() for path in args.compare])
        print(json.dumps({"compared": len(result["candidates"]), "ranking": str(context.root / "ranking.json")}))


if __name__ == "__main__":
    main()
