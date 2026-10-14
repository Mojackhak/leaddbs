"""Run the documented, isolated sub-181101 ANTs candidate stages."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time


REPOSITORY = Path(__file__).resolve().parents[3]
ANTS = REPOSITORY / "ext_libs/ANTs/antsRegistration.maca64"
APPLY = REPOSITORY / "ext_libs/ANTs/antsApplyTransforms.maca64"
EVALUATOR = Path(__file__).with_name("evaluate_scan.py")
METRICS = ("mi32", "mi64", "cc2", "cc4")
SYN = {"step005_u3_t0": "0.05,3,0", "step010_u3_t0": "0.1,3,0",
       "step010_u3_t1": "0.1,3,1", "step010_u4_t2": "0.1,4,2"}
PYRAMIDS = {"halfmm": ("100x70x50", "8x4x2", "1x0.5x0.25mm"),
            "quartermm": ("100x70x50x20", "8x4x2x1", "1x0.5x0.25x0mm")}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def load_json(path: Path):
    return json.loads(path.read_text())


def metric(name: str, fixed: Path, moving: Path, linear: bool = False) -> str:
    if name.startswith("mi"):
        sampling = "Regular,0.25" if linear else "None,1"
        return f"MI[{fixed},{moving},1,{name[2:]},{sampling}]"
    return f"CC[{fixed},{moving},1,{name[2:]}]"


def specifications(stage: str, parents: list[Path]) -> list[dict]:
    if stage == "linear":
        return [{"id": f"{init}_mi{bins}", "stage": stage, "initialization": init,
                 "metric": f"mi{bins}", "parent": None}
                for init, bins in itertools.product(("center", "braincom"), (32, 64))]
    result = []
    for parent in parents:
        saved = load_json(parent / "candidate.json")
        if stage == "wholebrain":
            for measure, syn, pyramid in itertools.product(METRICS, SYN, PYRAMIDS):
                result.append({"id": f"{parent.name}__{measure}__{syn}__{pyramid}",
                               "stage": stage, "parent": str(parent), "metric": measure,
                               "syn": SYN[syn], "pyramid": pyramid,
                               "affine_file": saved["affine_file"]})
        else:
            for margin, step in itertools.product((2, 4), ("0.05", "0.1")):
                tag = "005" if step == "0.05" else "010"
                result.append({"id": f"{parent.name}__roi{margin}__step{tag}",
                               "stage": stage, "parent": str(parent), "metric": saved["metric"],
                               "syn": f"{step},3,1", "margin_mm": margin,
                               "affine_file": saved["affine_file"]})
    return result


def command_for(root: Path, directory: Path, spec: dict) -> tuple[list[str], list[Path]]:
    fixed, moving = root / "inputs/fixed.nii.gz", root / "inputs/moving.nii.gz"
    fixed_mask, moving_mask = root / "masks/fixed_brain.nii.gz", root / "masks/moving_brain.nii.gz"
    prefix = directory / "transform_"
    stage = spec["stage"]
    inputs = [fixed, moving, fixed_mask, moving_mask]
    command = [str(ANTS), "--dimensionality", "3", "--float", "0", "--verbose", "1",
               "--random-seed", "1", "--use-histogram-matching", "0",
               "--interpolation", "Linear", "--output", f"[{prefix},{directory / 'warped.nii.gz'}]",
               "--write-composite-transform", "0" if stage == "local" else "1",
               "--collapse-output-transforms", "0" if stage == "local" else "1"]
    if stage == "linear":
        initialization = f"[{fixed},{moving},0]" if spec["initialization"] == "center" else f"[{fixed_mask},{moving_mask},1]"
        command.extend(["--initial-moving-transform", initialization])
        for model in ("Rigid", "Affine"):
            command.extend(["--transform", f"{model}[0.1]", "--metric", metric(spec["metric"], fixed, moving, True),
                            "--convergence", "[1000x500x250x100,1e-6,10]", "--shrink-factors", "12x8x4x2",
                            "--smoothing-sigmas", "1.5x1x0.5x0.25mm", "--masks", f"[{fixed_mask},{moving_mask}]"])
    else:
        parent = Path(spec["parent"])
        initial = parent / ("forward.nii.gz" if stage == "local" else "transform_Composite.h5")
        inputs.append(initial)
        command.extend(["--initial-moving-transform", str(initial)])
        if stage == "local":
            fixed_mask = root / f"masks/deep_{spec['margin_mm']}mm.nii.gz"
            inputs.extend([fixed_mask, parent / "inverse.nii.gz"])
            iterations, shrink, smoothing = "50x20", "2x1", "0.25x0mm"
        else:
            iterations, shrink, smoothing = PYRAMIDS[spec["pyramid"]]
        command.extend(["--transform", f"SyN[{spec['syn']}]", "--metric", metric(spec["metric"], fixed, moving),
                        "--convergence", f"[{iterations},1e-6,10]", "--shrink-factors", shrink,
                        "--smoothing-sigmas", smoothing, "--masks", f"[{fixed_mask},{moving_mask}]"])
    return command, inputs


def run_command(command: list[str], directory: Path, name: str, environment: dict) -> float:
    start = time.monotonic()
    write_json(directory / f"{name}_command.json", {"arguments": command, "started_utc": timestamp()})
    with (directory / f"{name}.log").open("x") as log:
        subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    return time.monotonic() - start


def field_commands(root: Path, directory: Path, spec: dict) -> list[tuple[str, list[str]]]:
    fixed, moving = root / "inputs/fixed.nii.gz", root / "inputs/moving.nii.gz"
    common = [str(APPLY), "--dimensionality", "3", "--float", "0"]
    if spec["stage"] == "local":
        parent = Path(spec["parent"])
        forward_chain = [directory / "transform_1Warp.nii.gz", parent / "forward.nii.gz"]
        inverse_chain = [parent / "inverse.nii.gz", directory / "transform_1InverseWarp.nii.gz"]
    else:
        forward_chain = [directory / "transform_Composite.h5"]
        inverse_chain = [directory / "transform_InverseComposite.h5"]
    result = []
    for name, reference, chain in [("forward", fixed, forward_chain), ("inverse", moving, inverse_chain)]:
        command = common + ["--reference-image", str(reference), "--output", f"[{directory / (name + '.nii.gz')},1]"]
        for transform in chain:
            command.extend(["--transform", str(transform)])
        result.append((f"compose_{name}", command))
    result.append(("warp_mask", common + ["--input", str(root / "masks/moving_brain.nii.gz"),
                    "--reference-image", str(fixed), "--output", str(directory / "warped_mask.nii.gz"),
                    "--interpolation", "NearestNeighbor", "--transform", str(directory / "forward.nii.gz")]))
    return result


def run_candidate(root: Path, spec: dict, environment: dict) -> dict:
    directory = root / spec["stage"] / spec["id"]
    if spec["stage"] == "linear":
        spec["affine_file"] = str(directory / "transform_Composite.h5")
    command, inputs = command_for(root, directory, spec)
    spec["registration_command"] = command
    spec["consumed_input_metadata"] = [{"path": str(path), "size": path.stat().st_size,
                                        "mtime_ns": path.stat().st_mtime_ns} for path in inputs]
    complete = directory / "complete.json"
    if complete.exists():
        if load_json(directory / "candidate.json") != spec:
            raise ValueError(f"Completed candidate has different consumed inputs or parameters: {directory}")
        return load_json(complete)
    directory.mkdir()
    write_json(directory / "candidate.json", spec)
    start = time.monotonic()
    print(json.dumps({"event": "started", "id": spec["id"], "utc": timestamp()}), flush=True)
    registration_seconds = run_command(command, directory, "registration", environment)
    for name, conversion in field_commands(root, directory, spec):
        run_command(conversion, directory, name, environment)
    run_command([sys.executable, str(EVALUATOR), "--output-root", str(root), "--candidate-dir", str(directory)],
                directory, "evaluation", environment)
    record = {"id": spec["id"], "stage": spec["stage"], "directory": str(directory),
              "completed_utc": timestamp(), "registration_seconds": registration_seconds,
              "total_seconds": time.monotonic() - start}
    write_json(complete, record)
    print(json.dumps({"event": "completed", **record}), flush=True)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("linear", "wholebrain", "local"))
    parser.add_argument("--parents", nargs="*", default=[], type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--list", action="store_true", help="Print the candidates without running them.")
    args = parser.parse_args()
    root = args.output_root.resolve()
    if args.stage != "linear" and not args.parents:
        parser.error("Selected parent directories are required for nonlinear stages.")
    specs = specifications(args.stage, [p.resolve() for p in args.parents])
    if args.list:
        print(json.dumps(specs, indent=2))
        return
    review = load_json(root / "masks/qc_review.json")
    if review["status"] != "accepted_for_comparative_registration":
        raise ValueError("Mask review must be completed before registration.")
    if not EVALUATOR.is_file():
        raise FileNotFoundError(EVALUATOR)
    environment = dict(os.environ, ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="1", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_candidate, root, spec, environment): spec for spec in specs}
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except (subprocess.CalledProcessError, OSError, ValueError) as error:
                # Preserve each failed candidate and report it while independent jobs finish.
                record = {"event": "failed", "id": spec["id"], "error": str(error), "utc": timestamp()}
                print(json.dumps(record), flush=True)
                errors.append(record)
    print(json.dumps({"stage": args.stage, "candidates": len(specs), "failures": errors}), flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
