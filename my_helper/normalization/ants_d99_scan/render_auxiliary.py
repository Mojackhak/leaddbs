"""Apply saved transforms and render auxiliary T2/SWI deep-region visual QA."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import textwrap

from evaluate_scan import (
    EvaluationContext,
    REGIONS,
    draw_plane,
    intensity_limits,
    normalize,
    plt,
    read_volume,
)
from run_scan import APPLY, load_json, run_command, write_json


def render_auxiliary(output_root: Path, candidate: Path) -> dict:
    modalities = ("aux_t2", "aux_swi")
    owned = ["qa_auxiliary_deep.png", "auxiliary_render.json"]
    for name in modalities:
        owned.extend([f"{name}_warped.nii.gz", f"{name}_warp_command.json", f"{name}_warp.log"])
    existing = [str(candidate / name) for name in owned if (candidate / name).exists()]
    if existing:
        raise FileExistsError("Preserve existing auxiliary outputs before rerendering: " + ", ".join(existing))

    context = EvaluationContext(output_root)
    specification = load_json(candidate / "candidate.json")
    limits = {}
    for name in modalities:
        _, native = read_volume(output_root / f"inputs/{name}.nii.gz", context.moving_image)
        limits[name] = intensity_limits(native, context.native_brain)
    _, t1 = read_volume(candidate / "warped.nii.gz", context.fixed_image)
    displays = [context.display_fixed, context.canonical(normalize(t1, context.moving_limits))]
    environment = os.environ.copy()
    environment["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = "1"
    commands = {}
    for name in modalities:
        command = [
            str(APPLY), "--dimensionality", "3", "--float", "0",
            "--input", str(output_root / f"inputs/{name}.nii.gz"),
            "--reference-image", str(output_root / "inputs/fixed.nii.gz"),
            "--transform", str(candidate / "forward.nii.gz"),
            "--interpolation", "Linear",
            "--output", str(candidate / f"{name}_warped.nii.gz"),
        ]
        run_command(command, candidate, f"{name}_warp", environment)
        commands[name] = command
        _, warped = read_volume(candidate / f"{name}_warped.nii.gz", context.fixed_image)
        displays.append(context.canonical(normalize(warped, limits[name])))

    cuts = context.protocol()["cuts_ras_mm"]
    figure, axes = plt.subplots(3, 4, figsize=(14, 10), constrained_layout=True)
    headings = ("D99 reference", "Candidate T1", "Auxiliary T2", "Auxiliary SWI")
    for row, region in enumerate(REGIONS):
        for column, display in enumerate(displays):
            draw_plane(axes[row, column], display, context, context.cuts[region], 2, region, 12.0)
            axes[row, column].set_title(f"{headings[column]} | {region.upper()}", fontsize=10)
        axes[row, 0].set_ylabel(f"Axial z = {cuts[region][2]:.2f} mm", fontsize=10)
    candidate_id = specification["id"]
    title = textwrap.fill(candidate_id, width=105)
    figure.suptitle(
        title + "\nAuxiliary visual QA only: common axial cuts and modality-specific native-image windows"
        "\nYellow: thalamus; cyan: STN; pink: SN. Atlas contours are not independent ground truth.",
        fontsize=11,
    )
    figure_path = candidate / "qa_auxiliary_deep.png"
    figure.savefig(figure_path, dpi=140)
    plt.close(figure)
    record = {
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate),
        "role": "visual_review_only",
        "parameter_estimation_or_ranking_changed": False,
        "transform": str(candidate / "forward.nii.gz"),
        "interpolation": "Linear",
        "itk_threads": 1,
        "window_percentiles": [0.5, 99.5],
        "window_reference": "Copied native modality within the operational native brain mask; common across candidates",
        "intensity_limits": {"fixed_t1": context.fixed_limits, "moving_t1": context.moving_limits, **limits},
        "axial_cuts_ras_z_mm": {region: cuts[region][2] for region in REGIONS},
        "context_half_width_mm": 12.0,
        "auxiliary_source_metadata": str(output_root / "inputs/auxiliary_sources.json"),
        "commands": commands,
        "figure": str(figure_path),
        "note": "No registration was estimated. Atlas contours are explanatory references, not independent native nucleus annotations.",
    }
    write_json(candidate / "auxiliary_render.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    args = parser.parse_args()
    record = render_auxiliary(args.output_root.resolve(), args.candidate_dir.resolve())
    print(record["figure"])


if __name__ == "__main__":
    main()
