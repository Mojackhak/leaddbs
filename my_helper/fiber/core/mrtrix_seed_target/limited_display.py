"""Coverage-limited MNI display derivatives; never native or full publication."""

from __future__ import annotations

import argparse
import csv
import json
import platform
from pathlib import Path

import nibabel as nib
import numpy as np

from .config import load_config
from .discovery import (
    _load_coregistration_method, _load_normalization_method,
    _select_anchor_reference, load_tmat,
)
from .errors import ValidationError
from .identity import file_sha256
from .state import atomic_write_json, read_json
from .tck import iter_tck, write_generated_tck, validate_tck
from .tractogram_space import (
    PointField, apply_affine, apply_point_field, ants_reference_transform,
    load_point_field, _domain_mask,
    _sample_point_field_displacement, _solve_paired_field_inverse,
    PAIRED_FIELD_INVERSE_TOLERANCE_MM, PAIRED_FIELD_INVERSE_MAX_ITERATIONS,
)
from .visualization import midpoint_stratified_ordinals


FRAGMENT_COLUMNS = [
    "fragment_ordinal_zero_based", "source_fiber_id", "source_ordinal_zero_based",
    "point_start_inclusive", "point_stop_exclusive", "truncated_start", "truncated_end",
]
AUDIT_COLUMNS = [
    "source_fiber_id", "source_ordinal_zero_based", "source_point_count", "status",
    "fragment_count", "first_fragment_ordinal_zero_based", "displayed_point_count",
    "inverse_recovered_point_count", "unresolved_point_count",
    "outside_mni_fov_point_count", "isolated_valid_point_count",
]


def map_display_points(anchor: np.ndarray, primary: PointField, reverse: PointField):
    """Return coordinates and per-vertex codes: direct, inverse, missing, outside FOV."""
    voxels = apply_affine(anchor, primary.inverse_affine)
    inside, _ = _domain_mask(voxels, primary.spatial_shape)
    mapped = np.full(anchor.shape, np.nan, dtype=np.float64)
    codes = np.full(len(anchor), 2, dtype=np.uint8)
    mapped[inside] = anchor[inside] + _sample_point_field_displacement(primary, voxels[inside])
    codes[inside] = 0
    outside = np.flatnonzero(~inside)
    if len(outside):
        # Boundary sampling is only an initial guess, never an accepted extrapolation.
        clipped = np.clip(voxels[outside], 0, np.asarray(primary.spatial_shape) - 1)
        initial = anchor[outside] + _sample_point_field_displacement(primary, clipped)
        solutions, _, converged = _solve_paired_field_inverse(
            anchor[outside], reverse_field=reverse, initial_target_points=initial,
        )
        rows = outside[converged]
        mapped[rows] = solutions[converged]
        codes[rows] = 1
    accepted = np.flatnonzero(codes < 2)
    target_inside, _ = _domain_mask(
        apply_affine(mapped[accepted], reverse.inverse_affine), reverse.spatial_shape,
    )
    rejected = accepted[~target_inside]
    codes[rejected] = 3
    mapped[rejected] = np.nan
    return mapped, codes


def contiguous_intervals(valid: np.ndarray) -> tuple[list[tuple[int, int]], int]:
    """Keep maximal valid original-vertex runs; isolated vertices are not lines."""
    transitions = np.diff(np.r_[False, valid, False].astype(np.int8))
    starts = np.flatnonzero(transitions == 1)
    stops = np.flatnonzero(transitions == -1)
    runs = [(int(a), int(b)) for a, b in zip(starts, stops) if b - a >= 2]
    return runs, int(np.count_nonzero(stops - starts == 1))


def export_seed(*, source: Path, destination: Path, subject_id: str, seed_key: str,
                expected_count: int, matrix: np.ndarray, primary: PointField,
                reverse: PointField, preview_budget: int, point_budget: int = 500_000):
    """Stream one mother into fragments, exhaustive ID tables, and bounded previews."""
    destination.mkdir(parents=True, exist_ok=False)
    selected = set(midpoint_stratified_ordinals(expected_count, min(preview_budget, expected_count)))
    overview, detail = [], []
    counts = dict(source_fibers=0, intact=0, truncated=0, not_displayed=0,
                  fragments=0, source_points=0, displayed_points=0,
                  inverse_recovered_points=0, unresolved_points=0,
                  outside_mni_fov_points=0, isolated_valid_points=0)
    detail_ids = set()
    fragment_path = destination / "fragments.tck"
    with (destination / "fragment_map.csv").open("x", newline="") as ff, \
            (destination / "fiber_audit.csv").open("x", newline="") as af:
        fragments = csv.writer(ff)
        audits = csv.writer(af)
        fragments.writerow(FRAGMENT_COLUMNS)
        audits.writerow(AUDIT_COLUMNS)

        def flush(buffer):
            lengths = [len(p) for _, p in buffer]
            offsets = np.r_[0, np.cumsum(lengths)]
            anchor = apply_affine(np.concatenate([p for _, p in buffer]), matrix)
            mapped, codes = map_display_points(anchor, primary, reverse)
            for j, (ordinal, points) in enumerate(buffer):
                lo, hi = offsets[j:j + 2]
                pc = codes[lo:hi]
                runs, isolated = contiguous_intervals(pc < 2)
                n = len(points)
                status = "intact" if runs == [(0, n)] else ("truncated" if runs else "not_displayed")
                fiber_id = f"{subject_id}:{seed_key}:{ordinal}"
                retained = sum(b - a for a, b in runs)
                inverse = int(np.count_nonzero(pc == 1))
                missing = int(np.count_nonzero(pc == 2))
                outside_fov = int(np.count_nonzero(pc == 3))
                audits.writerow([fiber_id, ordinal, n, status, len(runs),
                                 counts["fragments"] if runs else -1, retained,
                                 inverse, missing, outside_fov, isolated])
                counts["source_fibers"] += 1
                counts[status] += 1
                counts["source_points"] += n
                for key, value in [("displayed_points", retained), ("inverse_recovered_points", inverse),
                                   ("unresolved_points", missing), ("outside_mni_fov_points", outside_fov),
                                   ("isolated_valid_points", isolated)]:
                    counts[key] += value
                is_detail = status == "truncated" and len(detail_ids) < 40
                if is_detail:
                    detail_ids.add(ordinal)
                for a, b in runs:
                    fragments.writerow([counts["fragments"], fiber_id, ordinal, a, b, int(a > 0), int(b < n)])
                    segment = mapped[lo + a:lo + b].astype(np.float32)
                    item = (fiber_id, status, a, b, n, segment)
                    if ordinal in selected:
                        overview.append(item)
                    if is_detail:
                        detail.append(item)
                    counts["fragments"] += 1
                    yield segment

        def generate():
            buffer, total = [], 0
            for ordinal, points in enumerate(iter_tck(source)):
                if len(points) < 2 or not np.isfinite(points).all():
                    raise ValidationError(f"invalid native streamline {seed_key}:{ordinal}")
                if buffer and total + len(points) > point_budget:
                    yield from flush(buffer)
                    buffer, total = [], 0
                buffer.append((ordinal, points))
                total += len(points)
            if buffer:
                yield from flush(buffer)

        # Nibabel finalizes the TCK header with the realized count after streaming.
        write_generated_tck(generate, fragment_path, expected_count=0)
    if counts["source_fibers"] != expected_count:
        raise ValidationError(f"native count differs from publication receipt: {seed_key}")
    if counts["source_points"] != sum(counts[k] for k in [
        "displayed_points", "unresolved_points", "outside_mni_fov_points", "isolated_valid_points",
    ]):
        raise ValidationError(f"display point accounting failed: {seed_key}")
    atomic_write_json(destination / "summary.json", counts)
    return counts, overview, detail


def verify_fragments(destination: Path, expected: dict, reference: PointField) -> dict:
    """Independently reconcile TCKs, exhaustive source audit, and fragment intervals."""
    with (destination / "fiber_audit.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected["source_fibers"]:
        raise ValidationError("audit source count mismatch")
    point_count = 0
    observed = np.zeros(len(rows), dtype=np.int64)
    retained = np.zeros(len(rows), dtype=np.int64)
    previous = (-1, 0)
    with (destination / "fragment_map.csv").open() as handle:
        mappings = iter(csv.DictReader(handle))
        count = 0
        for count, points in enumerate(iter_tck(destination / "fragments.tck"), start=1):
            row = next(mappings, None)
            if row is None or int(row["fragment_ordinal_zero_based"]) != count - 1:
                raise ValidationError("fragment TCK and ID map differ")
            source = int(row["source_ordinal_zero_based"])
            start, stop = int(row["point_start_inclusive"]), int(row["point_stop_exclusive"])
            if (row["source_fiber_id"] != rows[source]["source_fiber_id"] or
                    not 0 <= start < stop <= int(rows[source]["source_point_count"]) or
                    stop - start != len(points) or len(points) < 2):
                raise ValidationError("fragment source interval mismatch")
            if source < previous[0] or (source == previous[0] and start <= previous[1]):
                raise ValidationError("fragment intervals overlap or bridge a missing vertex")
            previous = source, stop
            _, excess = _domain_mask(apply_affine(points, reference.inverse_affine), reference.spatial_shape)
            # Float32 TCK serialization may round a boundary coordinate by a few micrometres.
            if not np.isfinite(points).all() or np.max(excess, initial=0) > 2e-5:
                raise ValidationError("fragment has nonfinite or outside-FOV coordinates")
            observed[source] += 1
            retained[source] += len(points)
            point_count += len(points)
        if next(mappings, None) is not None:
            raise ValidationError("ID map contains extra fragments")
    for i, row in enumerate(rows):
        if int(row["source_ordinal_zero_based"]) != i or observed[i] != int(row["fragment_count"]) or retained[i] != int(row["displayed_point_count"]):
            raise ValidationError("source audit does not reconcile with fragments")
    if count != expected["fragments"] or point_count != expected["displayed_points"]:
        raise ValidationError("fragment totals mismatch")
    return {"fragment_count": count, "point_count": point_count, "id_intervals_verified": True}


def preservation_snapshot(paths: list[Path], small_files: list[Path]) -> dict:
    """Record existing publication metadata, hashing only small scientific receipts."""
    return {
        "file_metadata": {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in sorted(set(paths))},
        "small_file_sha256": {str(p): file_sha256(p) for p in sorted(set(small_files))},
    }


def render_preview(output: Path, template: Path, results: list, subject_id: str) -> None:
    """Export anatomical projections of sampled valid fragments, not new statistics."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    image = nib.load(template)
    data = np.asarray(image.dataobj)
    vmax = float(np.percentile(data, 99.5))
    affine = image.affine
    ix = int(round(nib.affines.apply_affine(np.linalg.inv(affine), [0, 0, 0])[0]))
    iy = int(round(nib.affines.apply_affine(np.linalg.inv(affine), [0, -20, 0])[1]))
    low = nib.affines.apply_affine(affine, [-.5, -.5, -.5])
    high = nib.affines.apply_affine(affine, np.asarray(image.shape) - .5)
    backgrounds = [(data[ix, :, :].T, [low[1], high[1], low[2], high[2]], [1, 2], "Y (posterior to anterior, mm)", "Sagittal projection; T1 at X = 0"),
                   (data[:, iy, :].T, [low[0], high[0], low[2], high[2]], [0, 2], "X (left to right, mm)", "Coronal projection; T1 at Y = -20")]
    with (output / "preview_selection.csv").open("x", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["preview", "seed_key", "source_fiber_id", "point_start_inclusive", "point_stop_exclusive"])
        for mode, item_index, title in [("overview", 2, "Deterministic source-ordinal sample"),
                                        ("truncation_detail", 3, "First 40 truncated source fibers per seed (illustrative)")]:
            fig, axes = plt.subplots(len(results), 2, figsize=(13, 16), constrained_layout=True)
            fig.suptitle(f"{subject_id} | Coverage-limited MNI display\n{title}", fontsize=17)
            for row_index, (seed, counts, overview, detail) in enumerate(results):
                items = (seed, counts, overview, detail)[item_index]
                for item in items:
                    writer.writerow([mode, seed, item[0], item[2], item[3]])
                for column, (background, extent, dims, xlabel, view_title) in enumerate(backgrounds):
                    ax = axes[row_index, column]
                    ax.imshow(background, extent=extent, origin="lower", cmap="gray", vmin=0, vmax=vmax, alpha=.45)
                    for status, color, width, alpha in [("intact", "#196a9a", .28, .18), ("truncated", "#c66a13", .65, .65)]:
                        lines = [item[5][:, dims] for item in items if item[1] == status]
                        ax.add_collection(LineCollection(lines, colors=color, linewidths=width, alpha=alpha, rasterized=True))
                    ends = [item[5][k, dims] for item in items for k, cut in [(0, item[2] > 0), (-1, item[3] < item[4])] if cut]
                    if ends:
                        points = np.array(ends)
                        ax.scatter(points[:, 0], points[:, 1], s=7, facecolors="none", edgecolors="#7d3500", linewidths=.5)
                    ax.axhline(low[2], color="#333333", linestyle="--", linewidth=.8)
                    ax.set(xlim=(-115, 85) if column == 0 else (-90, 90), ylim=(-78, 95), xlabel=xlabel, ylabel="Z (inferior to superior, mm)")
                    ax.set_aspect("equal")
                    shown = len({item[0] for item in items})
                    ax.set_title(f"{seed} | {shown:,} sampled source fibers\n{view_title}", fontsize=10)
                    ax.tick_params(labelsize=8)
            handles = [Line2D([0], [0], color="#196a9a", label="Intact source fiber"),
                       Line2D([0], [0], color="#c66a13", label="Valid fragment of truncated source fiber"),
                       Line2D([0], [0], marker="o", linestyle="none", markerfacecolor="none", color="#7d3500", label="Cut endpoint"),
                       Line2D([0], [0], linestyle="--", color="#333333", label="MNI field-of-view lower edge")]
            fig.legend(handles=handles, loc="outside lower center", ncol=2, fontsize=10)
            fig.savefig(output / f"{mode}.png", dpi=180)
            plt.close(fig)


def roundtrip_metrics(values) -> dict:
    """Report the existing full-conversion thresholds without filtering geometry."""
    values = np.asarray(values)
    if not len(values):
        return {"count": 0, "thresholds_met": None}
    median, p95, maximum = float(np.median(values)), float(np.percentile(values, 95)), float(np.max(values))
    return {"count": len(values), "median_mm": median, "p95_mm": p95, "max_mm": maximum,
            "thresholds_met": median <= .05 and p95 <= .2 and maximum <= .5}


def geometry_qc(*, source, destination, subject_id, seed_key, expected_count,
                matrix, inverse, primary, reverse, ants) -> dict:
    """Audit sampled source intervals and paired geometry; preserve QC warnings."""
    midpoints = set(int(x) for x in midpoint_stratified_ordinals(expected_count, min(200, expected_count)))
    affected = []
    with (destination / "fiber_audit.csv").open() as handle:
        for row in csv.DictReader(handle):
            if row["status"] == "truncated" and len(affected) < 40:
                affected.append(int(row["source_ordinal_zero_based"]))
    selected = midpoints | set(affected)
    expected, errors, middle_errors, outliers = {}, [], [], []
    per_method = {0: [], 1: []}
    parity_anchor, parity_target, inverse_anchor, inverse_target = [], [], [], []
    for ordinal, points in enumerate(iter_tck(source)):
        if ordinal not in selected:
            continue
        anchor = apply_affine(points, matrix)
        mapped, codes = map_display_points(anchor, primary, reverse)
        mid = len(points) // 2
        if ordinal in midpoints and codes[mid] < 2:
            returned = apply_affine(apply_point_field(mapped[mid:mid + 1], reverse), inverse)
            middle_errors.append(float(np.linalg.norm(returned[0] - points[mid])))
        intervals, _ = contiguous_intervals(codes < 2)
        for a, b in intervals:
            expected[(ordinal, a, b)] = mapped[a:b].astype(np.float32)
            restored = apply_affine(apply_point_field(mapped[a:b], reverse), inverse)
            residual = np.linalg.norm(restored - points[a:b], axis=1)
            errors.extend(residual)
            for code in (0, 1):
                per_method[code].extend(residual[codes[a:b] == code])
            for local in np.flatnonzero(residual > .5):
                index = a + int(local)
                outliers.append({"source_fiber_id": f"{subject_id}:{seed_key}:{ordinal}",
                                 "point_ordinal_zero_based": index, "residual_mm": float(residual[local]),
                                 "anchor_ras": anchor[index].tolist(), "mni_ras": mapped[index].tolist(),
                                 "mapping_code": int(codes[index])})
            for k in range(a, b):
                if codes[k] == 0 and len(parity_anchor) < 16:
                    parity_anchor.append(anchor[k]); parity_target.append(mapped[k])
                if codes[k] == 1 and len(inverse_anchor) < 16:
                    inverse_anchor.append(anchor[k]); inverse_target.append(mapped[k])
    matched, source_max = 0, 0.
    with (destination / "fragment_map.csv").open() as handle:
        for points, row in zip(iter_tck(destination / "fragments.tck"), csv.DictReader(handle), strict=True):
            ordinal = int(row["source_ordinal_zero_based"])
            if ordinal not in selected:
                continue
            key = ordinal, int(row["point_start_inclusive"]), int(row["point_stop_exclusive"])
            target = expected.pop(key)
            if target.shape != points.shape:
                raise ValidationError("sampled fragment shape differs from source interval")
            source_max = max(source_max, float(np.max(np.abs(target - points))))
            matched += 1
    if expected or source_max != 0:
        raise ValidationError("sampled fragments do not exactly match mapped native intervals")
    parity_results = {}
    worst = sorted((p for p in outliers if p["mapping_code"] == 0), key=lambda p: p["residual_mm"], reverse=True)[:16]
    for name, inputs, targets, field in [
        ("primary", parity_anchor, parity_target, primary),
        ("inverse", inverse_target, inverse_anchor, reverse),
        ("outlier_primary", [p["anchor_ras"] for p in worst], [p["mni_ras"] for p in worst], primary),
    ]:
        if inputs:
            actual = ants_reference_transform(np.asarray(inputs), field_path=field.path,
                                              executable=ants, work_dir=destination / "geometry_qc" / name)
            maximum = float(np.max(np.linalg.norm(actual - targets, axis=1)))
            parity_results[name] = {"count": len(inputs), "max_mm": maximum, "threshold_met": maximum <= 1e-4}
        else:
            parity_results[name] = {"count": 0, "threshold_met": None}
    expanded = roundtrip_metrics(errors)
    midpoint_metrics = roundtrip_metrics(middle_errors)
    warnings = []
    for name, metrics in [("expanded_roundtrip", expanded), ("midpoint_roundtrip", midpoint_metrics)]:
        if metrics["thresholds_met"] is not True:
            warnings.append(f"{name}_threshold_failed" if metrics["count"] else f"{name}_no_valid_sample")
    for name, metrics in parity_results.items():
        if metrics["threshold_met"] is False:
            warnings.append(f"ants_{name}_threshold_failed")
    return {"source_fibers_sampled": len(selected), "fragments_matched_to_source": matched,
            "source_coordinate_max_abs_difference_mm": source_max,
            "sampling": "200 midpoint-stratified source fibers plus first 40 truncated fibers; all retained vertices",
            "expanded_roundtrip": expanded, "original_midpoint_sampling_metrics": midpoint_metrics,
            "missing_sampled_midpoints": len(midpoints) - len(middle_errors),
            "direct_roundtrip": roundtrip_metrics(per_method[0]), "inverse_roundtrip": roundtrip_metrics(per_method[1]),
            "ants_parity": parity_results, "expanded_sample_points_over_0_5_mm": outliers,
            "warnings": warnings}


def matrix_pair_qc(matrix, inverse, *, allow_failure=False) -> dict:
    """Keep the original threshold; only an explicit display opt-in retains failure."""
    error = max(float(np.max(np.abs(matrix @ inverse - np.eye(4)))), float(np.max(np.abs(inverse @ matrix - np.eye(4)))))
    report = {"max_abs_error": error, "threshold": 1e-8, "threshold_met": error <= 1e-8,
              "display_warning_authorized": allow_failure}
    if not report["threshold_met"] and not allow_failure:
        raise ValidationError(f"paired b0/anchor matrices are not inverse: {error}")
    return report


def run_subject(config, spec, *, allow_matrix_qc_warning=False) -> dict:
    """Create one approved display derivative without calling pipeline stages."""
    root = spec.subject_dir / "connectomics/dMRI/mrtrix_seed_target"
    output = root / "display_limited_mni"
    state_path = root / "work/state.json"
    state = read_json(state_path)
    if state["configuration_hash"] != config.configuration_hash:
        raise ValidationError("display configuration does not match the native publication")
    records = [r for r in state["published_artifacts"] if r.get("coordinate_space") == "native"]
    mothers = {r["semantic_key"]: r for r in records if r["semantic_key"].endswith("/seedwide")}
    small = [state_path, config.source_path] + [Path(r["path"]) for r in state["summary_artifacts"]]
    for r in state["summary_artifacts"]:
        if file_sha256(r["path"]) != r["sha256"]:
            raise ValidationError("native summary differs from publication receipt")
    paths = [Path(r["path"]) for r in records] + small
    anatomy = spec.subject_dir / "coregistration"
    _, method, _ = _load_coregistration_method(anatomy / "log" / f"{spec.subject_id}_desc-coregmethod.json")
    anchor = spec.path_overrides.get("anchor_native_reference") or _select_anchor_reference(spec.subject_dir, spec.subject_id)
    matrix_path = spec.path_overrides.get("b0_to_anchor_transform") or anatomy / "transformations" / f"{spec.subject_id}_from-b0_to-anchorNative_desc-{method}44.mat"
    inverse_path = spec.path_overrides.get("anchor_to_b0_transform") or anatomy / "transformations" / f"{spec.subject_id}_from-anchorNative_to-b0_desc-{method}44.mat"
    norm_log = spec.path_overrides.get("normalization_method_log") or spec.subject_dir / "normalization/log" / f"{spec.subject_id}_desc-normmethod.json"
    _, approval = _load_normalization_method(norm_log)
    transform_root = spec.subject_dir / "normalization/transformations"
    primary_path = spec.path_overrides.get("target_to_anchor_image_deformation") or transform_root / f"{spec.subject_id}_from-{config.atlas.space}_to-anchorNative_desc-ants.nii.gz"
    reverse_path = spec.path_overrides.get("anchor_to_target_image_deformation") or transform_root / f"{spec.subject_id}_from-anchorNative_to-{config.atlas.space}_desc-ants.nii.gz"
    paths += [anchor, matrix_path, inverse_path, primary_path, reverse_path, norm_log]
    before = preservation_snapshot(paths, small)
    primary = load_point_field(primary_path, reference_path=anchor, label="display primary field")
    reverse = load_point_field(reverse_path, reference_path=config.atlas.seeds[0].path, label="display paired field")
    matrix = load_tmat(matrix_path)
    inverse = load_tmat(inverse_path)
    matrix_qc = matrix_pair_qc(matrix, inverse, allow_failure=allow_matrix_qc_warning)
    repo = Path(__file__).resolve().parents[4]
    ants = repo / "ext_libs/ANTs" / ("antsApplyTransformsToPoints.maca64" if platform.machine() == "arm64" else "antsApplyTransformsToPoints.maci64")
    output.mkdir(exist_ok=False)
    atomic_write_json(output / "preservation_before.json", before)
    provenance = {
        "subject_id": spec.subject_id, "execution_scope": "coverage_limited_mni_display",
        "status": "running", "not_for_connectivity_statistics": True,
        "native_request_identity": state["native_request_identity"], "configuration_hash": config.configuration_hash,
        "native_receipts": list(mothers.values()), "native_hashes_rechecked": False,
        "source_id": "subject:seed_key:zero_based_native_mother_ordinal",
        "point_intervals": "zero_based_half_open_original_vertices",
        "solver_tolerance_mm": PAIRED_FIELD_INVERSE_TOLERANCE_MM,
        "solver_max_iterations": PAIRED_FIELD_INVERSE_MAX_ITERATIONS,
        "display_only_minimum_run_vertices": 2, "brain_mask_filter": False,
        "primary_field_sha256": file_sha256(primary_path), "paired_field_sha256": file_sha256(reverse_path),
        "b0_to_anchor": matrix.tolist(), "display_code_sha256": file_sha256(__file__),
        "normalization_approval": approval,
        "matrix_pair_qc": matrix_qc,
        "point_code_sha256": file_sha256(Path(__file__).with_name("tractogram_space.py")),
        "preview_sampling": {"overview": "midpoint-stratified original source ordinals", "budget_per_seed": config.visualization.target_fiber_display_budget,
                             "detail": "first 40 truncated source fibers; illustrative, not representative"},
    }
    # An initial manifest is not a success receipt; final status is written after verification.
    atomic_write_json(output / "provenance.json", provenance)
    results, verification, geometry = [], {}, {}
    warnings = [] if approval == 1 else [f"normalization approval is {approval:g}; accepted with provenance"]
    if not matrix_qc["threshold_met"]:
        warnings.append(f"paired_matrix_qc_failed: {matrix_qc['max_abs_error']:.17g} > 1e-8; user-authorized display warning; matrices unchanged")
    for seed in config.atlas.seeds:
        record = mothers[f"{seed.key}/seedwide"]
        print(f"Exporting {spec.subject_id} {seed.key}", flush=True)
        counts, overview, detail = export_seed(
            source=Path(record["path"]), destination=output / seed.key,
            subject_id=spec.subject_id, seed_key=seed.key,
            expected_count=int(record["streamline_count"]), matrix=matrix,
            primary=primary, reverse=reverse, preview_budget=config.visualization.target_fiber_display_budget,
        )
        validate_tck(output / seed.key / "fragments.tck", config.execution.mrtrix_path_prefix / "tckinfo", expected_count=counts["fragments"])
        verification[seed.key] = verify_fragments(output / seed.key, counts, reverse)
        geometry[seed.key] = geometry_qc(source=Path(record["path"]), destination=output / seed.key,
                                       subject_id=spec.subject_id, seed_key=seed.key,
                                       expected_count=int(record["streamline_count"]), matrix=matrix,
                                       inverse=inverse, primary=primary, reverse=reverse, ants=ants)
        warnings.extend(f"{seed.key}: {warning}" for warning in geometry[seed.key]["warnings"])
        results.append((seed.key, counts, overview, detail))
        print(json.dumps({"seed": seed.key, **counts}), flush=True)
    render_preview(output, config.atlas.root.parent / "t1.nii", results, spec.subject_id)
    after = preservation_snapshot(paths, small)
    if before != after:
        raise ValidationError("native publication metadata or scientific summaries changed during display export")
    summary = {"status": "coverage_limited_display_complete", "subject_id": spec.subject_id,
               "native_unchanged": True, "full_mni_publication": False,
               "seeds": {seed: counts for seed, counts, _, _ in results}, "verification": verification,
               "warnings": warnings, "output_directory": str(output)}
    atomic_write_json(output / "geometry_qc.json", {"matrix_inverse_max_abs_error": matrix_qc["max_abs_error"], "matrix_pair_qc": matrix_qc, "seeds": geometry})
    atomic_write_json(output / "review.json", {"status": "display_ready_with_warnings" if warnings else "display_ready",
                      "subject_id": spec.subject_id, "warnings": warnings,
                      "native_and_connection_statistics_unchanged": True, "full_mni_publication": False,
                      "point_convention": "RAS+ world millimetres", "target_space": config.atlas.space,
                      "evidence": ["summary.json", "geometry_qc.json", "preservation_check.json", "overview.png", "truncation_detail.png"]})
    atomic_write_json(output / "summary.json", summary)
    atomic_write_json(output / "preservation_check.json", {"unchanged": True, "after": after})
    provenance["status"] = summary["status"]
    atomic_write_json(output / "provenance.json", provenance)
    print(json.dumps(summary), flush=True)
    return summary


def run_selected(config_path: Path, subject_ids: list[str], summary_dir: Path, *, resume=False,
                 matrix_qc_warning_subjects=()) -> dict:
    """Run an explicit subject list, preserving the reviewed pilot and other outputs."""
    config = load_config(config_path)
    subjects = {s.subject_id: s for s in config.subjects}
    if not subject_ids or len(set(subject_ids)) != len(subject_ids) or set(subject_ids) - subjects.keys():
        raise ValidationError("select unique subject IDs present in the configuration")
    if set(matrix_qc_warning_subjects) - set(subject_ids):
        raise ValidationError("matrix QC warning opt-in must name selected subjects")
    if resume:
        batch = read_json(summary_dir / "summary.json")
        completed = [s["subject_id"] for s in batch["subjects"]]
        if (batch["status"] not in {"running", "stopped_qc_failure"} or batch["configuration_hash"] != config.configuration_hash
                or batch["requested_subjects"] != subject_ids or completed != subject_ids[:len(completed)]):
            raise ValidationError("resume receipt does not match this interrupted display batch")
    else:
        summary_dir.mkdir(parents=True, exist_ok=False)
        batch = {"status": "running", "execution_scope": "coverage_limited_mni_display",
                 "configuration_hash": config.configuration_hash, "requested_subjects": subject_ids,
                 "full_mni_publication": False, "subjects": []}
    batch["status"] = "running"
    batch["matrix_qc_warning_subjects"] = list(matrix_qc_warning_subjects)
    for subject_id in subject_ids[len(batch["subjects"]):]:
        batch["active_subject"] = subject_id
        atomic_write_json(summary_dir / "summary.json", batch)
        batch["subjects"].append(run_subject(config, subjects[subject_id],
                                 allow_matrix_qc_warning=subject_id in matrix_qc_warning_subjects))
        atomic_write_json(summary_dir / "summary.json", batch)
    batch.pop("active_subject")
    if "failure" in batch:
        failure = batch.pop("failure")
        failure["requires_user_decision"] = False
        failure["resolution"] = "user-authorized display-only warning; QC remains failed"
        batch["retained_qc_failure_authorized_for_display"] = failure
    batch["status"] = "coverage_limited_display_complete"
    batch["completed_subjects"] = len(batch["subjects"])
    atomic_write_json(summary_dir / "summary.json", batch)
    with (summary_dir / "subject_seed_summary.csv").open("x", newline="") as handle:
        rows = [{"subject_id": s["subject_id"], "seed": key, **counts,
                 "warnings": "; ".join(s["warnings"]), "preview": str(Path(s["output_directory"]) / "overview.png")}
                for s in batch["subjects"] for key, counts in s["seeds"].items()]
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return batch


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--subjects", nargs="+", required=True)
    parser.add_argument("--summary-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Continue an interrupted display receipt; existing subject directories still refuse overwrite")
    parser.add_argument("--matrix-qc-warning-subjects", nargs="*", default=[], help="Explicitly authorized subjects retaining a failed matrix QC as a display-only warning")
    args = parser.parse_args()
    run_selected(args.config, args.subjects, args.summary_dir, resume=args.resume,
                 matrix_qc_warning_subjects=args.matrix_qc_warning_subjects)
