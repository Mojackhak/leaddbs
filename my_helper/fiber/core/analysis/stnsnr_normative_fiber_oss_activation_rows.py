#!/usr/bin/env python3
"""Run and aggregate fixed ten-sample row-level OSS pPAM activations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

from stnsnr_four_model_readiness import DEFAULT_VAL_ROOT
from stnsnr_normative_fiber_smoke_permutation import iso_now, write_csv, write_json
from stnsnr_run_provenance import git_provenance


DEFAULT_PREFLIGHT_SUMMARY = (
    DEFAULT_VAL_ROOT
    / "summary/four_model_execution/normative_fiber_oss_parameter_preflight/"
    / "normative_fiber_oss_parameter_preflight_summary.csv"
)
DEFAULT_OUTPUT_DIR = DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_oss_activation_rows"
DEFAULT_PREPARE_AXON = Path("/opt/anaconda3/envs/ossdbsv2/bin/prepareaxonmodel")
DEFAULT_OSS_CONVERTER = Path("/opt/anaconda3/envs/ossdbsv2/bin/leaddbs2ossdbs")
DEFAULT_OSSDBS = Path("/opt/anaconda3/envs/ossdbsv2/bin/ossdbs")
DEFAULT_PATHWAY_ACTIVATION = Path("/opt/anaconda3/envs/ossdbsv2/bin/run_pathway_activation")
PAM_N_SAMPLES = 10
PAM_SCALING = 0.8


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("_") or "row"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _remove_tree_missing_ok(path: Path) -> None:
    path = Path(path)

    def onerror(function: Callable[..., Any], failed_path: str, error_info: tuple[Any, Any, Any]) -> None:
        del function, failed_path
        error = error_info[1]
        if isinstance(error, FileNotFoundError):
            return
        raise error

    try:
        shutil.rmtree(path, onerror=onerror)
    except FileNotFoundError:
        pass
    if path.exists():
        raise OSError(f"OSS ephemeral runtime cleanup did not remove {path}")


def _run_logged_command(
    *,
    cmd: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_s: int | None,
) -> dict[str, Any]:
    started_at = iso_now()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    cmd_parent = str(Path(cmd[0]).expanduser().resolve().parent)
    env["PATH"] = cmd_parent + os.pathsep + env.get("PATH", "")
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            proc = subprocess.run(cmd, stdout=stdout_handle, stderr=stderr_handle, text=True, timeout=timeout_s, env=env)
        return {
            "cmd": cmd,
            "started_at": started_at,
            "finished_at": iso_now(),
            "returncode": proc.returncode,
            "timed_out": False,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }
    except subprocess.TimeoutExpired as exc:
        _write_text(stderr_path, f"TIMEOUT after {timeout_s} seconds\n{exc}\n")
        return {
            "cmd": cmd,
            "started_at": started_at,
            "finished_at": iso_now(),
            "returncode": "timeout",
            "timed_out": True,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }
    except KeyboardInterrupt:
        _write_text(stderr_path, "INTERRUPTED by KeyboardInterrupt\n")
        return {
            "cmd": cmd,
            "started_at": started_at,
            "finished_at": iso_now(),
            "returncode": "interrupted",
            "timed_out": False,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }


def _row_slug(row_index: int, row: dict[str, str]) -> str:
    return "_".join(
        [
            f"row{row_index:04d}",
            _safe_slug(row.get("model_id", "")),
            _safe_slug(row.get("subject_id", "")),
            _safe_slug(row.get("side", "")),
        ]
    )


def _right_canonical_connectome_side(row: dict[str, str]) -> int:
    side = str(row.get("side", "")).upper()
    mode = str(row.get("canonicalization_mode", ""))
    if side == "R" and mode in {"", "native_right"}:
        return 0
    if side == "L" and mode == "left_geometry_to_right":
        return 0
    raise ValueError(
        f"unsupported OSS canonicalization for side={side!r}, mode={mode!r}"
    )


def _replace_path_prefix(value: Any, old_prefix: str, new_prefix: str) -> Any:
    if isinstance(value, str):
        if value == old_prefix:
            return new_prefix
        if value.startswith(old_prefix + "/"):
            return new_prefix + value[len(old_prefix) :]
        return value
    if isinstance(value, list):
        return [_replace_path_prefix(item, old_prefix, new_prefix) for item in value]
    if isinstance(value, dict):
        return {key: _replace_path_prefix(item, old_prefix, new_prefix) for key, item in value.items()}
    return value


def _copy_root_files(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.iterdir():
        if item.name.startswith("._") or item.is_dir():
            continue
        shutil.copy2(item, target_dir / item.name)


def _copy_hdf5_dataset(source: h5py.Dataset, target_group: h5py.Group, name: str, data: np.ndarray | None = None) -> None:
    dataset = target_group.create_dataset(name, data=source[()] if data is None else data)
    for key, value in source.attrs.items():
        dataset.attrs[key] = value


def _filter_leaddbs_connectome_mat(
    source_path: Path,
    target_path: Path,
    candidate_ids: np.ndarray,
    candidate_id_to_column: dict[int, int],
) -> dict[str, Any]:
    with h5py.File(source_path, "r") as source:
        if "fibers" not in source or "idx" not in source:
            shutil.copy2(source_path, target_path)
            return {"filter_status": "copied_not_leaddbs_fiber_file"}
        fibers = source["fibers"]
        if fibers.ndim != 2 or fibers.shape[0] < 5:
            shutil.copy2(source_path, target_path)
            return {"filter_status": "copied_no_original_fiber_id_row", "source_fibers_shape": tuple(int(x) for x in fibers.shape)}

        original_ids = np.asarray(fibers[4, :], dtype=np.int64)
        point_mask = np.isin(original_ids, np.asarray(candidate_ids, dtype=np.int64))
        selected_local_ids = np.unique(np.asarray(fibers[3, point_mask], dtype=np.int64))
        selected_local_ids = selected_local_ids[selected_local_ids > 0]
        if selected_local_ids.size == 0:
            shutil.copy2(source_path, target_path)
            return {
                "filter_status": "copied_no_local_candidate_overlap",
                "source_n_points": int(fibers.shape[1]),
                "source_n_local_fibers": int(np.asarray(source["idx"]).reshape(-1).size),
                "candidate_n_fibers": int(candidate_ids.size),
            }

        idx_full = np.asarray(source["idx"]).reshape(-1).astype(np.int64)
        offsets = np.concatenate([[0], np.cumsum(idx_full)])
        selected_lengths = idx_full[selected_local_ids - 1]
        filtered = np.empty((int(fibers.shape[0]), int(np.sum(selected_lengths))), dtype=np.float64)
        write_start = 0
        selected_original_ids: list[int] = []
        mapping_rows: list[dict[str, Any]] = []
        for new_id, local_id in enumerate(selected_local_ids, start=1):
            start = int(offsets[int(local_id) - 1])
            stop = int(offsets[int(local_id)])
            block = np.asarray(fibers[:, start:stop], dtype=np.float64)
            block_original_ids = np.unique(np.asarray(block[4, :], dtype=np.int64))
            original_id = int(block_original_ids[0])
            block[3, :] = float(new_id)
            n_points = int(block.shape[1])
            filtered[:, write_start : write_start + n_points] = block
            selected_original_ids.append(original_id)
            mapping_rows.append(
                {
                    "local_axon_index": int(new_id - 1),
                    "filtered_local_fiber_id": int(new_id),
                    "source_local_fiber_id": int(local_id),
                    "selected_candidate_fiber_id": original_id,
                    "candidate_column_index": int(candidate_id_to_column.get(original_id, -1)),
                    "source_n_points": n_points,
                    "original_id_consistency_status": "single_original_id"
                    if block_original_ids.size == 1
                    else "multiple_original_ids",
                    "n_original_ids_in_source_local_fiber": int(block_original_ids.size),
                }
            )
            write_start += n_points

        with h5py.File(target_path, "w") as target:
            _copy_hdf5_dataset(fibers, target, "fibers", filtered)
            _copy_hdf5_dataset(source["idx"], target, "idx", selected_lengths.reshape(1, -1).astype(np.float64))
            if "origNum" in source:
                _copy_hdf5_dataset(source["origNum"], target, "origNum")
            for key in source.keys():
                if key not in {"fibers", "idx", "origNum"}:
                    _copy_hdf5_dataset(source[key], target, key)
        return {
            "filter_status": "filtered_to_local_candidate_overlap",
            "source_n_points": int(fibers.shape[1]),
            "source_n_local_fibers": int(idx_full.size),
            "candidate_n_fibers": int(candidate_ids.size),
            "filtered_n_points": int(filtered.shape[1]),
            "filtered_n_local_fibers": int(selected_local_ids.size),
            "selected_original_fiber_ids_preview": selected_original_ids[:20],
            "mapping_rows": mapping_rows,
        }


def _copy_connectome_dirs(
    *,
    source_stimulation_folder: Path,
    target_stimulation_folder: Path,
    hemi_side: int,
    candidate_ids: np.ndarray,
    candidate_id_to_column: dict[int, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    active_name = f"data{hemi_side + 1}.mat"
    for item in source_stimulation_folder.iterdir():
        if not item.is_dir() or item.name.startswith("._"):
            continue
        data_files = sorted(path for path in item.glob("data*.mat") if path.is_file() and not path.name.startswith("._"))
        if not data_files:
            continue
        target_dir = target_stimulation_folder / item.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for data_file in data_files:
            target_path = target_dir / data_file.name
            if data_file.name == active_name and candidate_ids.size:
                metadata = _filter_leaddbs_connectome_mat(
                    data_file,
                    target_path,
                    candidate_ids,
                    candidate_id_to_column,
                )
            else:
                shutil.copy2(data_file, target_path)
                metadata = {"filter_status": "copied_inactive_hemi_or_no_candidate_ids"}
            metadata.update({"source_path": str(data_file), "target_path": str(target_path), "active_hemi_file": data_file.name == active_name})
            rows.append(metadata)
    return rows


OSS_MAPPING_FIELDNAMES = [
    "row_index",
    "model_id",
    "subject_id",
    "side",
    "connectome_name",
    "source_path",
    "target_path",
    "filtered_stimulation_folder",
    "local_axon_index",
    "filtered_local_fiber_id",
    "source_local_fiber_id",
    "selected_candidate_fiber_id",
    "candidate_column_index",
    "source_n_points",
    "oss_fiber_ids_path",
    "original_id_consistency_status",
    "n_original_ids_in_source_local_fiber",
]


def _write_local_to_candidate_mapping(
    *,
    row: dict[str, str],
    row_index: int,
    row_dir: Path,
    filtered_stimulation_folder: Path,
    oss_fiber_ids_path: Path,
    connectome_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    mapping_path = row_dir / "oss_local_to_candidate_fiber_mapping.csv"
    mapping_rows: list[dict[str, Any]] = []
    for connectome_row in connectome_rows:
        for mapping_row in connectome_row.get("mapping_rows", []):
            mapping_rows.append(
                {
                    "row_index": row_index,
                    "model_id": row.get("model_id", ""),
                    "subject_id": row.get("subject_id", ""),
                    "side": row.get("side", ""),
                    "connectome_name": Path(str(connectome_row.get("target_path", ""))).parent.name,
                    "source_path": connectome_row.get("source_path", ""),
                    "target_path": connectome_row.get("target_path", ""),
                    "filtered_stimulation_folder": str(filtered_stimulation_folder),
                    "local_axon_index": mapping_row.get("local_axon_index", ""),
                    "filtered_local_fiber_id": mapping_row.get("filtered_local_fiber_id", ""),
                    "source_local_fiber_id": mapping_row.get("source_local_fiber_id", ""),
                    "selected_candidate_fiber_id": mapping_row.get("selected_candidate_fiber_id", ""),
                    "candidate_column_index": mapping_row.get("candidate_column_index", ""),
                    "source_n_points": mapping_row.get("source_n_points", ""),
                    "oss_fiber_ids_path": str(oss_fiber_ids_path),
                    "original_id_consistency_status": mapping_row.get("original_id_consistency_status", ""),
                    "n_original_ids_in_source_local_fiber": mapping_row.get("n_original_ids_in_source_local_fiber", ""),
                }
            )
        connectome_row.pop("mapping_rows", None)
    write_csv(mapping_path, mapping_rows, OSS_MAPPING_FIELDNAMES)
    invalid_column_count = sum(1 for row_data in mapping_rows if str(row_data.get("candidate_column_index", "")) == "-1")
    return {
        "mapping_path": str(mapping_path),
        "mapping_exists": mapping_path.is_file(),
        "mapping_n_rows": len(mapping_rows),
        "mapping_invalid_candidate_column_count": invalid_column_count,
    }


def _prepare_filtered_runtime(
    *,
    row: dict[str, str],
    row_index: int,
    row_dir: Path,
    original_settings: dict[str, Any],
    original_converter_json: Path,
    original_parameter_file: Path,
    disable_candidate_filter: bool,
) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    if disable_candidate_filter:
        return (
            Path(original_settings["StimulationFolder"]).expanduser().resolve(),
            original_parameter_file,
            original_converter_json,
            original_settings,
            {"filter_status": "disabled"},
        )
    oss_fiber_ids_path = Path(row.get("oss_fiber_ids_path", "")).expanduser()
    if not row.get("oss_fiber_ids_path") or not oss_fiber_ids_path.is_file():
        return (
            Path(original_settings["StimulationFolder"]).expanduser().resolve(),
            original_parameter_file,
            original_converter_json,
            original_settings,
            {"filter_status": "not_available_missing_oss_fiber_ids"},
        )

    candidate_ids = np.asarray(np.load(oss_fiber_ids_path), dtype=np.int64).reshape(-1)
    candidate_id_to_column = {int(fiber_id): index for index, fiber_id in enumerate(candidate_ids.tolist())}
    source_stimulation_folder = Path(original_settings["StimulationFolder"]).expanduser().resolve()
    filtered_stimulation_folder = row_dir / "filtered_stimulation_folder"
    if filtered_stimulation_folder.exists():
        shutil.rmtree(filtered_stimulation_folder, ignore_errors=True)
    _copy_root_files(source_stimulation_folder, filtered_stimulation_folder)
    filtered_parameter_file = filtered_stimulation_folder / original_parameter_file.name
    if not filtered_parameter_file.is_file():
        shutil.copy2(original_parameter_file, filtered_parameter_file)
    hemi_side = _right_canonical_connectome_side(row)
    connectome_rows = _copy_connectome_dirs(
        source_stimulation_folder=source_stimulation_folder,
        target_stimulation_folder=filtered_stimulation_folder,
        hemi_side=hemi_side,
        candidate_ids=np.asarray(candidate_ids, dtype=np.int64),
        candidate_id_to_column=candidate_id_to_column,
    )
    mapping_metadata = _write_local_to_candidate_mapping(
        row=row,
        row_index=row_index,
        row_dir=row_dir,
        filtered_stimulation_folder=filtered_stimulation_folder,
        oss_fiber_ids_path=oss_fiber_ids_path,
        connectome_rows=connectome_rows,
    )
    oss_sim_dir = filtered_stimulation_folder / ("OSS_sim_files_rh" if hemi_side == 0 else "OSS_sim_files_lh")
    oss_sim_dir.mkdir(parents=True, exist_ok=True)
    results_dir = filtered_stimulation_folder / "Results"
    filtered_settings = _replace_path_prefix(
        original_settings,
        str(source_stimulation_folder),
        str(filtered_stimulation_folder),
    )
    filtered_settings["StimulationFolder"] = str(filtered_stimulation_folder)
    filtered_settings["OutputPath"] = str(results_dir)
    filtered_settings["PathwayFile"] = str(oss_sim_dir / "Allocated_axons_parameters.json")
    filtered_settings.setdefault("PointModel", {}).setdefault("Pathway", {})["FileName"] = str(oss_sim_dir / "Allocated_axons.h5")
    filtered_converter_json = row_dir / "filtered_oss-dbs_parameters.json"
    filtered_converter_json.write_text(json.dumps(filtered_settings, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return (
        filtered_stimulation_folder,
        filtered_parameter_file,
        filtered_converter_json,
        filtered_settings,
        {
            "filter_status": "prepared_filtered_stimulation_folder",
            "oss_fiber_ids_path": str(oss_fiber_ids_path),
            "oss_n_fibers": int(candidate_ids.size),
            "source_stimulation_folder": str(source_stimulation_folder),
            "filtered_stimulation_folder": str(filtered_stimulation_folder),
            "filtered_converter_json": str(filtered_converter_json),
            "local_to_candidate_mapping_path": mapping_metadata["mapping_path"],
            "local_to_candidate_mapping_exists": mapping_metadata["mapping_exists"],
            "local_to_candidate_mapping_n_rows": mapping_metadata["mapping_n_rows"],
            "local_to_candidate_mapping_invalid_candidate_column_count": mapping_metadata[
                "mapping_invalid_candidate_column_count"
            ],
            "connectome_files": connectome_rows,
        },
    )


def _any_existing_status(paths: list[Path]) -> str:
    return "complete" if paths and any(path.is_file() for path in paths) else "missing"


def _pathway_outputs(output_path: Path, scaling_index: int | None) -> list[Path]:
    if scaling_index is None:
        return [output_path / "Pathway_status.json", output_path / "Pathway_status_default.json"]
    return [output_path / f"Pathway_status_{scaling_index}.json", output_path / f"Pathway_status_default_{scaling_index}.json"]


def _select_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("preflight_status") == "parameter_preflight_passed"]
    if args.model_id:
        requested = set(args.model_id)
        selected = [row for row in selected if row.get("model_id") in requested]
    if args.one_row_per_model:
        one_each: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in selected:
            model_id = row.get("model_id", "")
            if model_id and model_id not in seen:
                one_each.append(row)
                seen.add(model_id)
        selected = one_each
    if args.max_rows is None and not args.one_row_per_model:
        selected = selected[:1]
    elif args.max_rows is not None and args.max_rows > 0:
        selected = selected[: args.max_rows]
    return selected


def _oss_success_flag_name(fail_flag: str) -> str:
    return f"success_{fail_flag}.txt" if fail_flag else "success.txt"


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _oss_success_flag_candidates(stimulation_folder: Path, converter_json: Path, fail_flag: str) -> list[Path]:
    marker_name = _oss_success_flag_name(fail_flag)
    return _unique_paths([stimulation_folder / marker_name, converter_json.parent / marker_name])


def _first_existing_file(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _run_required_command(
    *,
    command_runner: Callable[..., dict[str, Any]],
    cmd: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_s: int | None,
    step_name: str,
    sample_index: int,
) -> dict[str, Any]:
    result = command_runner(
        cmd=cmd,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_s=timeout_s,
    )
    if result.get("returncode") != 0:
        raise RuntimeError(
            f"sample {sample_index} {step_name} failed with return code "
            f"{result.get('returncode')!r}"
        )
    return result


def _sample_converter_json(hemi_folder: Path, parameter_file: Path) -> Path:
    expected = hemi_folder / f"{parameter_file.stem}.json"
    if expected.is_file():
        return expected
    candidates = sorted(path for path in hemi_folder.glob("*.json") if path.is_file())
    parameter_candidates = [path for path in candidates if "parameter" in path.stem.lower()]
    if len(parameter_candidates) == 1:
        return parameter_candidates[0]
    raise RuntimeError(
        f"converter did not create exactly one parameter JSON for {parameter_file}: "
        f"{[str(path) for path in candidates]}"
    )


def _configure_sample_converter_json(
    *,
    converter_json: Path,
    stimulation_folder: Path,
    hemi_folder: Path,
    source_frequency_hz: float,
) -> dict[str, Any]:
    if not np.isfinite(source_frequency_hz):
        raise ValueError("source stimulation frequency must be finite")
    settings = _load_json(converter_json)
    results_folder = hemi_folder / "Results"
    settings["StimulationFolder"] = str(stimulation_folder)
    settings["OutputPath"] = str(results_folder)
    settings["ModelSide"] = 0
    settings["FailFlag"] = "rh"
    settings["PathwayFile"] = str(hemi_folder / "Allocated_axons_parameters.json")
    settings.setdefault("PointModel", {}).setdefault("Pathway", {})["FileName"] = str(
        hemi_folder / "Allocated_axons.h5"
    )
    signal = settings.setdefault("StimulationSignal", {})
    original_frequency = signal.get("Frequency[Hz]")
    signal["Frequency[Hz]"] = float(source_frequency_hz)
    converter_json.write_text(
        json.dumps(settings, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return {
        "source_frequency_hz": float(source_frequency_hz),
        "converter_frequency_hz_original": original_frequency,
        "converter_frequency_hz_final": signal["Frequency[Hz]"],
        "frequency_preservation_status": "exact_source_frequency_written",
    }


def _find_sample_axon_state(output_path: Path, sample_index: int) -> Path:
    candidates = sorted(output_path.glob(f"Axon_state_*_{sample_index}.mat"))
    candidates.extend(sorted(output_path.glob(f"Axon_state_*_{sample_index}.csv")))
    stems = {path.stem for path in candidates}
    if len(stems) != 1:
        raise RuntimeError(
            f"sample {sample_index} must produce exactly one local-fiber Axon_state result; "
            f"found {[path.name for path in candidates]}"
        )
    mat_candidates = [path for path in candidates if path.suffix.lower() == ".mat"]
    return mat_candidates[0] if mat_candidates else candidates[0]


def _copy_compact_artifact(source: Path, destination: Path) -> dict[str, str]:
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"missing compact OSS source artifact: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "path": str(destination.resolve()),
        "sha256": _sha256_file(destination),
    }


def _compact_sample_record(
    *,
    sample_index: int,
    parameter_file: Path,
    stimulation_folder: Path,
    converter_json: Path,
    pathway_outputs: Sequence[Path],
    axon_state_path: Path,
    frequency_metadata: dict[str, Any],
    commands: dict[str, dict[str, Any]],
    compact_output_dir: Path,
    cleanup_ephemeral: bool,
) -> dict[str, Any]:
    sample_dir = Path(compact_output_dir) / f"sample_{sample_index:02d}"
    sample_dir.mkdir(parents=True, exist_ok=True)
    converter_ref = _copy_compact_artifact(
        converter_json,
        sample_dir / "converter_parameters.json",
    )
    axon_state_ref = _copy_compact_artifact(
        axon_state_path,
        sample_dir / f"axon_state{axon_state_path.suffix.lower()}",
    )
    pathway_refs = []
    for path in pathway_outputs:
        if Path(path).is_file():
            pathway_refs.append(
                _copy_compact_artifact(
                    Path(path),
                    sample_dir / Path(path).name,
                )
            )
    if not pathway_refs:
        raise RuntimeError(f"sample {sample_index} has no compact pathway status")

    command_records: dict[str, dict[str, Any]] = {}
    for name, command in commands.items():
        command_record = dict(command)
        for key in ("stdout_log", "stderr_log"):
            value = str(command_record.get(key, "")).strip()
            if value:
                log_path = Path(value).expanduser().resolve()
                if not log_path.is_file():
                    raise FileNotFoundError(
                        f"sample {sample_index} command log is missing: {log_path}"
                    )
                command_record[f"{key}_sha256"] = _sha256_file(log_path)
        command_records[name] = command_record

    parameter_file = Path(parameter_file).expanduser().resolve()
    manifest_path = sample_dir / "compact_sample_manifest.json"
    manifest = {
        "sample_index": sample_index,
        "pam_n_samples": PAM_N_SAMPLES,
        "parameter_file": str(parameter_file),
        "parameter_file_sha256": _sha256_file(parameter_file),
        "converter_json": converter_ref,
        "axon_state": axon_state_ref,
        "pathway_outputs": pathway_refs,
        "frequency": frequency_metadata,
        "commands": command_records,
        "ephemeral_runtime_policy": "delete_after_compact_validation",
    }
    _write_json_atomic(manifest_path, manifest)
    if _load_json(manifest_path) != manifest:
        raise RuntimeError(f"sample {sample_index} compact manifest validation failed")
    _load_json(Path(converter_ref["path"]))
    _load_local_activation_status(Path(axon_state_ref["path"]))

    if cleanup_ephemeral:
        _remove_tree_missing_ok(stimulation_folder)
    return {
        "sample_index": sample_index,
        "parameter_file": str(parameter_file),
        "parameter_file_sha256": manifest["parameter_file_sha256"],
        "hemi_side": 0,
        "canonicalization": "right",
        "converter_json": converter_ref["path"],
        "converter_json_sha256": converter_ref["sha256"],
        "pathway_outputs": [item["path"] for item in pathway_refs],
        "pathway_output_sha256": [item["sha256"] for item in pathway_refs],
        "axon_state_path": axon_state_ref["path"],
        "axon_state_sha256": axon_state_ref["sha256"],
        "frequency": frequency_metadata,
        "commands": command_records,
        "compact_sample_manifest": str(manifest_path.resolve()),
        "compact_sample_manifest_sha256": _sha256_file(manifest_path),
        "ephemeral_runtime_deleted": bool(cleanup_ephemeral),
    }


def _execute_probabilistic_sample_chain(
    *,
    sample_parameter_files: Sequence[Path],
    sample_stimulation_folders: Sequence[Path],
    source_frequency_hz: float,
    prepareaxonmodel_bin: Path,
    converter_bin: Path,
    ossdbs_bin: Path,
    pathway_activation_bin: Path,
    prepareaxon_timeout_s: int | None,
    converter_timeout_s: int | None,
    ossdbs_timeout_s: int | None,
    pathway_timeout_s: int | None,
    command_runner: Callable[..., dict[str, Any]] = _run_logged_command,
    compact_output_dir: Path | None = None,
    cleanup_ephemeral: bool = False,
    stimulation_template: Path | None = None,
) -> list[dict[str, Any]]:
    """Execute the complete right-canonical OSS chain for all ten pPAM samples."""
    parameter_files = [Path(path).expanduser().resolve() for path in sample_parameter_files]
    stimulation_folders = [Path(path).expanduser().resolve() for path in sample_stimulation_folders]
    if len(parameter_files) != PAM_N_SAMPLES or len(stimulation_folders) != PAM_N_SAMPLES:
        raise ValueError(f"probabilistic PAM requires exactly {PAM_N_SAMPLES} sample inputs")
    if len({str(path) for path in parameter_files}) != PAM_N_SAMPLES:
        raise ValueError("probabilistic PAM sample parameter files must be unique")
    if not all(path.is_file() for path in parameter_files):
        missing = [str(path) for path in parameter_files if not path.is_file()]
        raise FileNotFoundError(f"missing probabilistic PAM parameter files: {missing}")

    records: list[dict[str, Any]] = []
    for sample_index, (parameter_file, stimulation_folder) in enumerate(
        zip(parameter_files, stimulation_folders, strict=True),
        start=1,
    ):
        if stimulation_template is not None:
            _materialize_sample_stimulation_folder(
                Path(stimulation_template),
                stimulation_folder,
            )
        stimulation_folder.mkdir(parents=True, exist_ok=True)
        command_log_dir = stimulation_folder.parent / "command_logs"
        hemi_folder = stimulation_folder / "OSS_sim_files_rh"
        hemi_folder.mkdir(parents=True, exist_ok=True)
        axon_h5 = hemi_folder / "Allocated_axons.h5"
        pathway_file = hemi_folder / "Allocated_axons_parameters.json"

        prepare_result = _run_required_command(
            command_runner=command_runner,
            cmd=[
                str(Path(prepareaxonmodel_bin).expanduser().resolve()),
                str(stimulation_folder),
                "--hemi_side",
                "0",
                "--description_file",
                str(parameter_file),
            ],
            stdout_path=command_log_dir / "prepareaxonmodel_stdout.log",
            stderr_path=command_log_dir / "prepareaxonmodel_stderr.log",
            timeout_s=prepareaxon_timeout_s,
            step_name="prepareaxonmodel",
            sample_index=sample_index,
        )
        if not axon_h5.is_file() or not pathway_file.is_file():
            raise RuntimeError(f"sample {sample_index} prepareaxonmodel outputs are incomplete")

        converter_result = _run_required_command(
            command_runner=command_runner,
            cmd=[
                str(Path(converter_bin).expanduser().resolve()),
                "--hemi_side",
                "0",
                str(parameter_file),
                "--output_path",
                str(hemi_folder),
            ],
            stdout_path=command_log_dir / "leaddbs2ossdbs_stdout.log",
            stderr_path=command_log_dir / "leaddbs2ossdbs_stderr.log",
            timeout_s=converter_timeout_s,
            step_name="leaddbs2ossdbs",
            sample_index=sample_index,
        )
        converter_json = _sample_converter_json(hemi_folder, parameter_file)
        frequency_metadata = _configure_sample_converter_json(
            converter_json=converter_json,
            stimulation_folder=stimulation_folder,
            hemi_folder=hemi_folder,
            source_frequency_hz=source_frequency_hz,
        )
        settings = _load_json(converter_json)
        output_path = Path(settings["OutputPath"]).expanduser().resolve()

        ossdbs_result = _run_required_command(
            command_runner=command_runner,
            cmd=[str(Path(ossdbs_bin).expanduser().resolve()), str(converter_json)],
            stdout_path=command_log_dir / "ossdbs_stdout.log",
            stderr_path=command_log_dir / "ossdbs_stderr.log",
            timeout_s=ossdbs_timeout_s,
            step_name="ossdbs",
            sample_index=sample_index,
        )
        oss_time_result = output_path / "oss_time_result_PAM.h5"
        success_flags = _oss_success_flag_candidates(stimulation_folder, converter_json, "rh")
        success_flag = _first_existing_file(success_flags)
        if success_flag is None or not oss_time_result.is_file():
            raise RuntimeError(f"sample {sample_index} ossdbs outputs are incomplete")

        pathway_result = _run_required_command(
            command_runner=command_runner,
            cmd=[
                str(Path(pathway_activation_bin).expanduser().resolve()),
                str(converter_json),
                "--scaling_index",
                str(sample_index),
                "--scaling",
                str(PAM_SCALING),
            ],
            stdout_path=command_log_dir / "run_pathway_activation_stdout.log",
            stderr_path=command_log_dir / "run_pathway_activation_stderr.log",
            timeout_s=pathway_timeout_s,
            step_name="run_pathway_activation",
            sample_index=sample_index,
        )
        pathway_outputs = _pathway_outputs(output_path, sample_index)
        if _any_existing_status(pathway_outputs) != "complete":
            raise RuntimeError(f"sample {sample_index} pathway status output is missing")
        axon_state_path = _find_sample_axon_state(output_path, sample_index)
        record = {
                "sample_index": sample_index,
                "parameter_file": str(parameter_file),
                "stimulation_folder": str(stimulation_folder),
                "hemi_side": 0,
                "canonicalization": "right",
                "converter_json": str(converter_json),
                "output_path": str(output_path),
                "pathway_outputs": [str(path) for path in pathway_outputs],
                "axon_state_path": str(axon_state_path),
                "frequency": frequency_metadata,
                "commands": {
                    "prepareaxonmodel": prepare_result,
                    "leaddbs2ossdbs": converter_result,
                    "ossdbs": ossdbs_result,
                    "run_pathway_activation": pathway_result,
                },
            }
        if compact_output_dir is not None:
            record = _compact_sample_record(
                sample_index=sample_index,
                parameter_file=parameter_file,
                stimulation_folder=stimulation_folder,
                converter_json=converter_json,
                pathway_outputs=pathway_outputs,
                axon_state_path=axon_state_path,
                frequency_metadata=frequency_metadata,
                commands=record["commands"],
                compact_output_dir=Path(compact_output_dir),
                cleanup_ephemeral=cleanup_ephemeral,
            )
        records.append(record)
    return records


def _load_local_activation_status(path: Path) -> dict[int, int]:
    if not path.is_file():
        raise FileNotFoundError(f"missing sample Axon_state file: {path}")
    if path.suffix.lower() == ".mat":
        data = loadmat(path)
        if "fibers" not in data:
            raise ValueError(f"sample Axon_state MAT file has no fibers variable: {path}")
        fibers = np.asarray(data["fibers"], dtype=float)
    elif path.suffix.lower() == ".csv":
        fibers = np.asarray(np.loadtxt(path, delimiter=",", skiprows=1), dtype=float)
    else:
        raise ValueError(f"unsupported sample Axon_state format: {path}")
    if fibers.ndim == 1:
        fibers = fibers.reshape(1, -1)
    if fibers.ndim != 2 or fibers.shape[1] < 5:
        raise ValueError(f"invalid sample Axon_state shape in {path}: {fibers.shape}")
    local_id_values = fibers[:, 3]
    status_values = fibers[:, 4]
    if not np.all(np.isfinite(local_id_values)) or not np.all(np.isfinite(status_values)):
        raise ValueError(f"non-finite local fiber IDs or statuses in {path}")
    local_ids = np.rint(local_id_values).astype(np.int64)
    statuses = np.rint(status_values).astype(np.int64)
    if not np.allclose(local_id_values, local_ids) or not np.allclose(status_values, statuses):
        raise ValueError(f"non-integer local fiber IDs or statuses in {path}")
    status_by_local_id: dict[int, int] = {}
    for local_id in np.unique(local_ids):
        if local_id <= 0:
            continue
        local_statuses = np.unique(statuses[local_ids == local_id])
        if local_statuses.size != 1:
            raise ValueError(f"inconsistent status values for local fiber ID {local_id} in {path}")
        status_by_local_id[int(local_id)] = int(local_statuses[0])
    if not status_by_local_id:
        raise ValueError(f"sample Axon_state has no positive local fiber IDs: {path}")
    return status_by_local_id


def _mapping_by_local_id(
    mapping_rows: Sequence[dict[str, Any]],
    candidate_fiber_ids: np.ndarray,
) -> dict[int, int]:
    candidate_ids = np.asarray(candidate_fiber_ids, dtype=np.int64)
    if candidate_ids.ndim != 1 or candidate_ids.size == 0:
        raise ValueError("candidate mapping requires a nonempty one-dimensional fiber axis")
    if np.unique(candidate_ids).size != candidate_ids.size:
        raise ValueError("candidate mapping axis contains duplicate fiber IDs")
    mapping: dict[int, int] = {}
    used_columns: set[int] = set()
    for row in mapping_rows:
        try:
            local_id = int(str(row["filtered_local_fiber_id"]))
            candidate_column = int(str(row["candidate_column_index"]))
            selected_candidate_id = int(str(row["selected_candidate_fiber_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid candidate mapping row: {row}") from exc
        if local_id <= 0 or candidate_column < 0 or candidate_column >= candidate_ids.size:
            raise ValueError(f"candidate mapping index is out of range: {row}")
        if int(candidate_ids[candidate_column]) != selected_candidate_id:
            raise ValueError(
                "candidate mapping ID does not match the exact candidate-axis column: "
                f"{row}"
            )
        if local_id in mapping or candidate_column in used_columns:
            raise ValueError(f"candidate mapping contains duplicate local IDs or columns: {row}")
        mapping[local_id] = candidate_column
        used_columns.add(candidate_column)
    if not mapping:
        raise ValueError("candidate mapping is empty")
    return mapping


def _aggregate_local_activation_probabilities(
    *,
    sample_state_paths: Sequence[Path],
    mapping_rows: Sequence[dict[str, Any]],
    candidate_fiber_ids: np.ndarray,
) -> dict[str, np.ndarray]:
    """Aggregate exact local-fiber activation frequencies over ten samples."""
    paths = [Path(path).expanduser().resolve() for path in sample_state_paths]
    if len(paths) != PAM_N_SAMPLES:
        raise ValueError(f"probabilistic PAM aggregation requires exactly {PAM_N_SAMPLES} samples")
    if len({str(path) for path in paths}) != PAM_N_SAMPLES:
        raise ValueError("probabilistic PAM aggregation requires ten unique sample files")
    local_to_column = _mapping_by_local_id(mapping_rows, candidate_fiber_ids)
    expected_local_ids = set(local_to_column)
    activated_by_local = {local_id: 0 for local_id in expected_local_ids}
    for sample_index, path in enumerate(paths, start=1):
        status_by_local = _load_local_activation_status(path)
        observed_local_ids = set(status_by_local)
        if observed_local_ids != expected_local_ids:
            missing = sorted(expected_local_ids - observed_local_ids)
            extra = sorted(observed_local_ids - expected_local_ids)
            raise ValueError(
                f"sample {sample_index} local fiber IDs differ from the exact mapping; "
                f"missing={missing}, extra={extra}"
            )
        for local_id, status in status_by_local.items():
            if status == 1:
                activated_by_local[local_id] += 1

    candidate_ids = np.asarray(candidate_fiber_ids, dtype=np.int64)
    activated_counts = np.zeros(candidate_ids.size, dtype=np.int64)
    for local_id, candidate_column in local_to_column.items():
        activated_counts[candidate_column] = activated_by_local[local_id]
    probabilities = (activated_counts.astype(np.float64) / PAM_N_SAMPLES).astype(np.float32)
    return {
        "candidate_fiber_ids": candidate_ids.copy(),
        "activated_counts": activated_counts,
        "activation_probabilities": probabilities,
    }


def _write_probability_artifacts(
    *,
    row: dict[str, str],
    row_index: int,
    row_dir: Path,
    aggregation: dict[str, np.ndarray],
    mapping_rows: Sequence[dict[str, Any]],
    sample_records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if len(sample_records) != PAM_N_SAMPLES:
        raise ValueError(f"probability artifacts require exactly {PAM_N_SAMPLES} sample records")
    candidate_ids = np.asarray(aggregation["candidate_fiber_ids"], dtype=np.int64)
    activated_counts = np.asarray(aggregation["activated_counts"], dtype=np.int64)
    probabilities = np.asarray(aggregation["activation_probabilities"], dtype=np.float32)
    expected_shape = (candidate_ids.size,)
    if activated_counts.shape != expected_shape or probabilities.shape != expected_shape:
        raise ValueError("probability artifact arrays do not share the exact candidate axis")
    if np.any(activated_counts < 0) or np.any(activated_counts > PAM_N_SAMPLES):
        raise ValueError("activated counts fall outside the fixed sample range")
    if not np.all(np.isfinite(probabilities)) or np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise ValueError("activation probabilities fall outside [0, 1]")
    expected_probabilities = activated_counts.astype(np.float64) / PAM_N_SAMPLES
    if not np.array_equal(probabilities, expected_probabilities.astype(np.float32)):
        raise ValueError("activation probabilities are not exact activated_count/10 frequencies")

    local_to_column = _mapping_by_local_id(mapping_rows, candidate_ids)
    column_to_local = {column: local_id for local_id, column in local_to_column.items()}
    candidate_ids_path = row_dir / "right_canonical_candidate_fiber_ids.npy"
    probability_path = row_dir / "right_canonical_activation_probability.npy"
    probability_csv = row_dir / "right_canonical_activation_probability.csv"
    manifest_path = row_dir / "probabilistic_pam_row_manifest.json"
    np.save(candidate_ids_path, candidate_ids)
    np.save(probability_path, probabilities)
    probability_rows = [
        {
            "row_index": row_index,
            "model_id": row.get("model_id", ""),
            "subject_id": row.get("subject_id", ""),
            "source_side": row.get("side", ""),
            "canonical_side": "R",
            "candidate_column_index": column,
            "candidate_fiber_id": int(candidate_id),
            "filtered_local_fiber_id": column_to_local.get(column, ""),
            "activated_count": int(activated_counts[column]),
            "pam_n_samples": PAM_N_SAMPLES,
            "activation_probability": float(probabilities[column]),
        }
        for column, candidate_id in enumerate(candidate_ids)
    ]
    write_csv(probability_csv, probability_rows, list(probability_rows[0].keys()))
    manifest = {
        "generated_at": iso_now(),
        "row_index": row_index,
        "model_id": row.get("model_id", ""),
        "subject_id": row.get("subject_id", ""),
        "source_side": row.get("side", ""),
        "canonical_side": "R",
        "canonicalization_mode": row.get("canonicalization_mode", ""),
        "left_geometry_transform": (
            "ea_flip_lr_nonlinear"
            if row.get("side", "").upper() == "L"
            else "native_right"
        ),
        "pam_n_samples": PAM_N_SAMPLES,
        "sample_count_source": "internal_fixed_contract",
        "activation_value_type": "pPAM_activation_probability",
        "activation_value_subtype": "empirical_activated_count_over_10_samples",
        "aggregation_rule": "activated_count_divided_by_10",
        "candidate_axis_status": "exact_right_canonical_candidate_order",
        "n_candidate_fibers": int(candidate_ids.size),
        "n_mapped_local_fibers": len(local_to_column),
        "n_interior_probabilities": int(np.count_nonzero((probabilities > 0.0) & (probabilities < 1.0))),
        "probability_min": float(np.min(probabilities)),
        "probability_max": float(np.max(probabilities)),
        "candidate_fiber_ids_path": str(candidate_ids_path),
        "right_canonical_probability_path": str(probability_path),
        "right_canonical_probability_csv": str(probability_csv),
        "samples": list(sample_records),
    }
    write_json(manifest_path, manifest)
    return {
        "pam_n_samples": PAM_N_SAMPLES,
        "activation_value_type": manifest["activation_value_type"],
        "activation_value_subtype": manifest["activation_value_subtype"],
        "right_canonical_candidate_fiber_ids_path": str(candidate_ids_path),
        "right_canonical_probability_path": str(probability_path),
        "right_canonical_probability_csv": str(probability_csv),
        "probability_manifest": str(manifest_path),
        "probability_min": manifest["probability_min"],
        "probability_max": manifest["probability_max"],
        "n_interior_probabilities": manifest["n_interior_probabilities"],
    }


def _load_sample_parameter_files(row: dict[str, str]) -> list[Path]:
    manifest_value = str(row.get("sample_parameter_manifest", "")).strip()
    if not manifest_value:
        raise ValueError("preflight row is missing the probabilistic sample parameter manifest")
    manifest_path = Path(manifest_value).expanduser().resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing probabilistic sample parameter manifest: {manifest_path}")
    manifest = _load_json(manifest_path)
    if int(manifest.get("pam_n_samples", -1)) != PAM_N_SAMPLES:
        raise ValueError(f"sample parameter manifest must declare exactly {PAM_N_SAMPLES} samples")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or len(samples) != PAM_N_SAMPLES:
        raise ValueError(f"sample parameter manifest must contain exactly {PAM_N_SAMPLES} samples")
    observed_indexes = [int(sample.get("sample_index", -1)) for sample in samples]
    if observed_indexes != list(range(1, PAM_N_SAMPLES + 1)):
        raise ValueError("sample parameter manifest indexes must be exactly 1 through 10 in order")
    parameter_files = [
        Path(str(sample.get("parameter_file", ""))).expanduser().resolve()
        for sample in samples
    ]
    if len({str(path) for path in parameter_files}) != PAM_N_SAMPLES:
        raise ValueError("sample parameter manifest contains duplicate parameter files")
    missing = [str(path) for path in parameter_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"sample parameter files are missing: {missing}")
    return parameter_files


def _load_mapping_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_csv_rows(path)
    if not rows:
        raise ValueError(f"local-to-candidate mapping is empty: {path}")
    return rows


def _persist_compact_mapping(mapping_path: Path, compact_mapping_path: Path) -> list[dict[str, str]]:
    mapping_path = Path(mapping_path).expanduser().resolve()
    compact_mapping_path = Path(compact_mapping_path).expanduser().resolve()
    if mapping_path != compact_mapping_path:
        shutil.copy2(mapping_path, compact_mapping_path)
    return _load_mapping_rows(compact_mapping_path)


def _link_or_copy_file(source: str, target: str) -> str:
    try:
        os.link(source, target)
        return target
    except OSError:
        return shutil.copy2(source, target)


def _materialize_sample_stimulation_folder(template_folder: Path, target_folder: Path) -> None:
    if target_folder.exists():
        raise FileExistsError(f"sample runtime folder already exists: {target_folder}")
    target_folder.mkdir(parents=True)
    for item in template_folder.iterdir():
        if item.name.startswith("._") or item.name == "Results" or item.name.startswith("OSS_sim_files"):
            continue
        target = target_folder / item.name
        if item.is_dir():
            shutil.copytree(item, target, copy_function=_link_or_copy_file)
        else:
            _link_or_copy_file(str(item), str(target))


def _new_execution_dir(row_dir: Path) -> Path:
    stem = _safe_slug(f"pam_execution_{iso_now()}")
    candidate = row_dir / stem
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = row_dir / f"{stem}_{suffix:02d}"
    candidate.mkdir(parents=True)
    return candidate


_ROW_CHECKPOINT_ARTIFACT_KEYS = (
    "right_canonical_candidate_fiber_ids_path",
    "right_canonical_probability_path",
    "right_canonical_probability_csv",
    "probability_manifest",
    "row_status_json",
    "local_to_candidate_mapping_path",
)


def _row_checkpoint_artifact_paths(result: dict[str, Any]) -> dict[str, Path]:
    paths = {
        f"row.{key}": Path(str(result[key])).expanduser().resolve()
        for key in _ROW_CHECKPOINT_ARTIFACT_KEYS
    }
    status_doc = _load_json(paths["row.row_status_json"])
    for sample in status_doc.get("sample_records", []):
        sample_index = int(sample.get("sample_index", -1))
        prefix = f"sample_{sample_index:02d}"
        scalar_fields = (
            "parameter_file",
            "converter_json",
            "axon_state_path",
            "compact_sample_manifest",
        )
        for field in scalar_fields:
            value = str(sample.get(field, "")).strip()
            if value:
                paths[f"{prefix}.{field}"] = Path(value).expanduser().resolve()
        for index, value in enumerate(sample.get("pathway_outputs", [])):
            paths[f"{prefix}.pathway_output_{index:02d}"] = (
                Path(str(value)).expanduser().resolve()
            )
        for command_name, command in sample.get("commands", {}).items():
            for log_name in ("stdout_log", "stderr_log"):
                value = str(command.get(log_name, "")).strip()
                if value:
                    paths[f"{prefix}.{command_name}.{log_name}"] = (
                        Path(value).expanduser().resolve()
                    )
    return paths


def _valid_row_identity(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError("OSS row identity must be a full SHA-256 digest")
    return text


def _load_row_checkpoint(
    logical_row_dir: Path,
    expected_identity: str | None,
) -> dict[str, Any] | None:
    if expected_identity is None:
        return None
    checkpoint_path = logical_row_dir / "row_checkpoint.json"
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = _load_json(checkpoint_path)
        if checkpoint.get("oss_row_identity_sha256") != expected_identity:
            return None
        result = dict(checkpoint["result"])
        artifact_refs = checkpoint["artifacts"]
        expected_paths = _row_checkpoint_artifact_paths(result)
        if set(artifact_refs) != set(expected_paths):
            return None
        for key, expected_path in expected_paths.items():
            ref = artifact_refs[key]
            path = Path(str(ref["path"])).expanduser().resolve()
            if not path.is_file() or _sha256_file(path) != ref["sha256"]:
                return None
            if path != expected_path:
                return None
        candidate_ids = np.asarray(
            np.load(result["right_canonical_candidate_fiber_ids_path"], mmap_mode="r"),
            dtype=np.int64,
        )
        probabilities = np.asarray(
            np.load(result["right_canonical_probability_path"], mmap_mode="r"),
            dtype=np.float32,
        )
        if candidate_ids.ndim != 1 or probabilities.shape != candidate_ids.shape:
            return None
        if not np.all(np.isfinite(probabilities)) or np.any(
            (probabilities < 0.0) | (probabilities > 1.0)
        ):
            return None
        lattice = (np.rint(probabilities.astype(np.float64) * PAM_N_SAMPLES) / PAM_N_SAMPLES).astype(
            np.float32
        )
        if not np.array_equal(probabilities, lattice):
            return None
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    result["row_checkpoint_json"] = str(checkpoint_path.resolve())
    result["row_checkpoint_reused"] = True
    return result


def _write_row_checkpoint(
    *,
    logical_row_dir: Path,
    row_identity: str | None,
    result: dict[str, Any],
) -> Path | None:
    if row_identity is None:
        return None
    artifact_refs = {}
    for key, path in _row_checkpoint_artifact_paths(result).items():
        if not path.is_file():
            raise FileNotFoundError(f"row checkpoint artifact is missing: {path}")
        artifact_refs[key] = {"path": str(path), "sha256": _sha256_file(path)}
    checkpoint_path = logical_row_dir / "row_checkpoint.json"
    _write_json_atomic(
        checkpoint_path,
        {
            "checkpoint_version": 1,
            "generated_at": iso_now(),
            "oss_row_identity_sha256": row_identity,
            "artifacts": artifact_refs,
            "result": result,
        },
    )
    return checkpoint_path


def _remove_runtime_tree(path: Path, execution_dir: Path) -> None:
    path = Path(path).expanduser().resolve()
    execution_dir = Path(execution_dir).expanduser().resolve()
    if path == execution_dir or execution_dir not in path.parents:
        raise ValueError(f"refusing to remove OSS runtime outside execution directory: {path}")
    if path.exists():
        _remove_tree_missing_ok(path)


def _run_activation_row(
    *,
    row: dict[str, str],
    row_index: int,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if bool(getattr(args, "disable_candidate_filter", False)):
        raise ValueError("probabilistic PAM requires the exact local-to-candidate filter mapping")
    _right_canonical_connectome_side(row)
    source_frequency_text = str(row.get("source_frequency_hz", "")).strip()
    try:
        source_frequency_hz = float(source_frequency_text)
    except ValueError as exc:
        raise ValueError(f"invalid source stimulation frequency: {source_frequency_text!r}") from exc
    if not np.isfinite(source_frequency_hz):
        raise ValueError("source stimulation frequency must be finite")

    logical_row_dir = output_dir / _row_slug(row_index, row)
    logical_row_dir.mkdir(parents=True, exist_ok=True)
    row_identity = _valid_row_identity(row.get("oss_row_identity_sha256"))
    reused = _load_row_checkpoint(logical_row_dir, row_identity)
    if reused is not None:
        return reused
    execution_dir = _new_execution_dir(logical_row_dir)
    sample_parameter_files = _load_sample_parameter_files(row)
    original_converter_json = Path(row["converter_json"]).expanduser().resolve()
    original_parameter_file = Path(row["parameter_file"]).expanduser().resolve()
    original_settings = _load_json(original_converter_json)
    stimulation_template, _, _, _, filter_metadata = _prepare_filtered_runtime(
        row=row,
        row_index=row_index,
        row_dir=execution_dir,
        original_settings=original_settings,
        original_converter_json=original_converter_json,
        original_parameter_file=original_parameter_file,
        disable_candidate_filter=False,
    )
    mapping_path = Path(
        str(filter_metadata.get("local_to_candidate_mapping_path", ""))
    ).expanduser().resolve()
    if not bool(filter_metadata.get("local_to_candidate_mapping_exists", False)) or not mapping_path.is_file():
        raise RuntimeError("probabilistic PAM requires a persisted local-to-candidate mapping")
    invalid_mapping_count = int(
        filter_metadata.get("local_to_candidate_mapping_invalid_candidate_column_count", 0)
    )
    if invalid_mapping_count != 0:
        raise RuntimeError(
            f"local-to-candidate mapping has {invalid_mapping_count} invalid candidate columns"
        )

    compact_mapping_path = execution_dir / "oss_local_to_candidate_fiber_mapping.csv"
    mapping_rows = _persist_compact_mapping(mapping_path, compact_mapping_path)

    sample_stimulation_folders = [
        (
            execution_dir
            / "pam_samples"
            / f"sample_{sample_index:02d}"
            / "stimulation"
        )
        for sample_index in range(1, PAM_N_SAMPLES + 1)
    ]

    sample_records = _execute_probabilistic_sample_chain(
        sample_parameter_files=sample_parameter_files,
        sample_stimulation_folders=sample_stimulation_folders,
        source_frequency_hz=source_frequency_hz,
        prepareaxonmodel_bin=Path(args.prepareaxonmodel_bin),
        converter_bin=Path(args.oss_converter_bin),
        ossdbs_bin=Path(args.ossdbs_bin),
        pathway_activation_bin=Path(args.run_pathway_activation_bin),
        prepareaxon_timeout_s=None if args.prepareaxon_timeout_s <= 0 else args.prepareaxon_timeout_s,
        converter_timeout_s=None if args.converter_timeout_s <= 0 else args.converter_timeout_s,
        ossdbs_timeout_s=None if args.ossdbs_timeout_s <= 0 else args.ossdbs_timeout_s,
        pathway_timeout_s=None if args.pathway_timeout_s <= 0 else args.pathway_timeout_s,
        compact_output_dir=execution_dir / "compact_samples",
        cleanup_ephemeral=True,
        stimulation_template=stimulation_template,
    )
    sample_state_paths = [Path(str(record["axon_state_path"])) for record in sample_records]
    candidate_fiber_ids_path = Path(row.get("oss_fiber_ids_path", "")).expanduser().resolve()
    if not candidate_fiber_ids_path.is_file():
        raise FileNotFoundError(f"missing exact candidate fiber axis: {candidate_fiber_ids_path}")
    candidate_fiber_ids = np.asarray(np.load(candidate_fiber_ids_path), dtype=np.int64)
    aggregation = _aggregate_local_activation_probabilities(
        sample_state_paths=sample_state_paths,
        mapping_rows=mapping_rows,
        candidate_fiber_ids=candidate_fiber_ids,
    )
    artifacts = _write_probability_artifacts(
        row=row,
        row_index=row_index,
        row_dir=execution_dir,
        aggregation=aggregation,
        mapping_rows=mapping_rows,
        sample_records=sample_records,
    )
    for stimulation_folder in sample_stimulation_folders:
        if stimulation_folder.exists():
            _remove_runtime_tree(stimulation_folder, execution_dir)
    if (
        stimulation_template.exists()
        and execution_dir.resolve() in stimulation_template.resolve().parents
    ):
        _remove_runtime_tree(stimulation_template, execution_dir)
    filter_metadata = {
        **filter_metadata,
        "filtered_stimulation_folder": "",
        "local_to_candidate_mapping_path": str(compact_mapping_path.resolve()),
        "ephemeral_runtime_deleted": True,
    }
    status_path = execution_dir / "oss_activation_row_status.json"
    status_doc = {
        "generated_at": iso_now(),
        "row_index": row_index,
        "row": row,
        "row_status": "probabilistic_activation_complete",
        "pam_n_samples": PAM_N_SAMPLES,
        "sample_parameter_manifest": row.get("sample_parameter_manifest", ""),
        "sample_parameter_files": [str(path) for path in sample_parameter_files],
        "source_frequency_hz": source_frequency_hz,
        "canonical_side": "R",
        "candidate_filter": filter_metadata,
        "probability_artifacts": artifacts,
        "sample_records": sample_records,
        "completion_rule": "all_10_samples_and_exact_local_candidate_mapping_required",
        "deterministic_single_sample_fallback_allowed": False,
        "side_effects": "row_level_probability_outputs_only_no_branch_x_oss_written",
    }
    _write_json_atomic(status_path, status_doc)
    result = {
        "row_index": row_index,
        "model_id": row.get("model_id", ""),
        "subject_id": row.get("subject_id", ""),
        "side": row.get("side", ""),
        "canonicalization_mode": row.get("canonicalization_mode", ""),
        "canonical_side": "R",
        "row_status": "probabilistic_activation_complete",
        "row_output_dir": str(execution_dir),
        "row_status_json": str(status_path),
        "source_frequency_hz": source_frequency_hz,
        "sample_parameter_manifest": row.get("sample_parameter_manifest", ""),
        "oss_fiber_ids_path": row.get("oss_fiber_ids_path", ""),
        "oss_n_fibers": row.get("oss_n_fibers", ""),
        "oss_fiber_ids_hash": row.get("oss_fiber_ids_hash", ""),
        "candidate_filter_status": filter_metadata.get("filter_status", ""),
        "filtered_stimulation_folder": "",
        "local_to_candidate_mapping_path": str(compact_mapping_path.resolve()),
        "local_to_candidate_mapping_exists": True,
        "local_to_candidate_mapping_n_rows": len(mapping_rows),
        "local_to_candidate_mapping_invalid_candidate_column_count": 0,
        "ephemeral_runtime_deleted": True,
        **artifacts,
    }
    checkpoint_path = _write_row_checkpoint(
        logical_row_dir=logical_row_dir,
        row_identity=row_identity,
        result=result,
    )
    result["row_checkpoint_json"] = "" if checkpoint_path is None else str(checkpoint_path.resolve())
    result["row_checkpoint_reused"] = False
    return result


def run_activation_rows(args: argparse.Namespace) -> int:
    preflight_summary = Path(args.preflight_summary).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_rows = _select_rows(_read_csv_rows(preflight_summary), args)
    if not selected_rows:
        raise RuntimeError("no parameter_preflight_passed rows selected")

    summary_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(selected_rows):
        print(f"OSS activation row {row_index}: {row.get('model_id')} {row.get('subject_id')} {row.get('side')}")
        summary_rows.append(_run_activation_row(row=row, row_index=row_index, output_dir=output_dir, args=args))

    summary_path = output_dir / "normative_fiber_oss_activation_row_summary.csv"
    manifest_path = output_dir / "normative_fiber_oss_activation_row_manifest.json"
    write_csv(summary_path, summary_rows, list(summary_rows[0].keys()))
    status_counts: dict[str, int] = {}
    for row in summary_rows:
        status = str(row.get("row_status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "preflight_summary": str(preflight_summary),
            "output_dir": str(output_dir),
            "n_rows": len(summary_rows),
            "status_counts": status_counts,
            "pam_n_samples": PAM_N_SAMPLES,
            "sample_count_source": "internal_fixed_contract",
            "scaling_indexes": list(range(1, PAM_N_SAMPLES + 1)),
            "activation_value_type": "pPAM_activation_probability",
            "activation_value_subtype": "empirical_activated_count_over_10_samples",
            "code_provenance": git_provenance(),
            "side_effects": "row_level_probability_outputs_only_no_branch_x_oss_written",
            "outputs": {
                "summary_csv": str(summary_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    print(f"OSS activation row summary: {summary_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-summary", default=str(DEFAULT_PREFLIGHT_SUMMARY), help="OSS parameter preflight summary CSV.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="OSS row-level activation output directory.")
    parser.add_argument("--model-id", action="append", choices=["B_DTOR", "D_DTOR"], help="Optional model ID filter.")
    parser.add_argument("--max-rows", type=int, default=None, help="Maximum rows to run; default is 1 unless --one-row-per-model is set; <=0 means all.")
    parser.add_argument("--one-row-per-model", action="store_true", help="Run the first selected row for each model before applying --max-rows.")
    parser.add_argument("--prepareaxonmodel-bin", default=str(DEFAULT_PREPARE_AXON), help="prepareaxonmodel executable.")
    parser.add_argument("--oss-converter-bin", default=str(DEFAULT_OSS_CONVERTER), help="leaddbs2ossdbs executable.")
    parser.add_argument("--ossdbs-bin", default=str(DEFAULT_OSSDBS), help="ossdbs executable.")
    parser.add_argument("--run-pathway-activation-bin", default=str(DEFAULT_PATHWAY_ACTIVATION), help="run_pathway_activation executable.")
    parser.add_argument("--prepareaxon-timeout-s", type=int, default=0, help="prepareaxonmodel timeout; <=0 disables timeout.")
    parser.add_argument("--converter-timeout-s", type=int, default=0, help="leaddbs2ossdbs timeout; <=0 disables timeout.")
    parser.add_argument("--ossdbs-timeout-s", type=int, default=0, help="ossdbs timeout; <=0 disables timeout.")
    parser.add_argument("--pathway-timeout-s", type=int, default=0, help="run_pathway_activation timeout; <=0 disables timeout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_activation_rows(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
