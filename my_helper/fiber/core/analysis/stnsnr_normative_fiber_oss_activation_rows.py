#!/usr/bin/env python3
"""Run resumable row-level OSS/pPAM activation steps for normative fibers."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import h5py
import numpy as np

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
DEFAULT_OSSDBS = Path("/opt/anaconda3/envs/ossdbsv2/bin/ossdbs")
DEFAULT_PATHWAY_ACTIVATION = Path("/opt/anaconda3/envs/ossdbsv2/bin/run_pathway_activation")


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
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            proc = subprocess.run(cmd, stdout=stdout_handle, stderr=stderr_handle, text=True, timeout=timeout_s)
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


def _hemi_side(side: str) -> int:
    if side == "R":
        return 0
    if side == "L":
        return 1
    raise RuntimeError(f"unsupported side: {side!r}")


def _oss_sim_folder_name(side: str) -> str:
    if side == "R":
        return "OSS_sim_files_rh"
    if side == "L":
        return "OSS_sim_files_lh"
    raise RuntimeError(f"unsupported side: {side!r}")


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


def _filter_leaddbs_connectome_mat(source_path: Path, target_path: Path, candidate_ids: np.ndarray) -> dict[str, Any]:
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
        for new_id, local_id in enumerate(selected_local_ids, start=1):
            start = int(offsets[int(local_id) - 1])
            stop = int(offsets[int(local_id)])
            block = np.asarray(fibers[:, start:stop], dtype=np.float64)
            block[3, :] = float(new_id)
            n_points = int(block.shape[1])
            filtered[:, write_start : write_start + n_points] = block
            selected_original_ids.append(int(block[4, 0]))
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
        }


def _copy_connectome_dirs(
    *,
    source_stimulation_folder: Path,
    target_stimulation_folder: Path,
    hemi_side: int,
    candidate_ids: np.ndarray,
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
                metadata = _filter_leaddbs_connectome_mat(data_file, target_path, candidate_ids)
            else:
                shutil.copy2(data_file, target_path)
                metadata = {"filter_status": "copied_inactive_hemi_or_no_candidate_ids"}
            metadata.update({"source_path": str(data_file), "target_path": str(target_path), "active_hemi_file": data_file.name == active_name})
            rows.append(metadata)
    return rows


def _prepare_filtered_runtime(
    *,
    row: dict[str, str],
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

    candidate_ids = np.load(oss_fiber_ids_path)
    source_stimulation_folder = Path(original_settings["StimulationFolder"]).expanduser().resolve()
    filtered_stimulation_folder = row_dir / "filtered_stimulation_folder"
    if filtered_stimulation_folder.exists():
        shutil.rmtree(filtered_stimulation_folder)
    _copy_root_files(source_stimulation_folder, filtered_stimulation_folder)
    filtered_parameter_file = filtered_stimulation_folder / original_parameter_file.name
    if not filtered_parameter_file.is_file():
        shutil.copy2(original_parameter_file, filtered_parameter_file)
    hemi_side = _hemi_side(row.get("side", ""))
    connectome_rows = _copy_connectome_dirs(
        source_stimulation_folder=source_stimulation_folder,
        target_stimulation_folder=filtered_stimulation_folder,
        hemi_side=hemi_side,
        candidate_ids=np.asarray(candidate_ids, dtype=np.int64),
    )
    oss_sim_dir = filtered_stimulation_folder / _oss_sim_folder_name(row.get("side", ""))
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
            "connectome_files": connectome_rows,
        },
    )


def _step_existing_status(paths: list[Path]) -> str:
    return "complete" if paths and all(path.is_file() for path in paths) else "missing"


def _pathway_outputs(output_path: Path, scaling_index: int | None) -> list[Path]:
    if scaling_index is None:
        return [output_path / "Pathway_status.json"]
    return [output_path / f"Pathway_status_{scaling_index}.json"]


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


def _status_rank(status: str) -> int:
    order = {
        "pending": 0,
        "prepareaxonmodel_complete": 1,
        "ossdbs_complete": 2,
        "pathway_activation_complete": 3,
    }
    return order.get(status, -1)


def _run_activation_row(
    *,
    row: dict[str, str],
    row_index: int,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    row_dir = output_dir / _row_slug(row_index, row)
    row_dir.mkdir(parents=True, exist_ok=True)
    original_converter_json = Path(row["converter_json"]).expanduser().resolve()
    original_parameter_file = Path(row["parameter_file"]).expanduser().resolve()
    original_settings = _load_json(original_converter_json)
    stimulation_folder, parameter_file, converter_json, settings, filter_metadata = _prepare_filtered_runtime(
        row=row,
        row_dir=row_dir,
        original_settings=original_settings,
        original_converter_json=original_converter_json,
        original_parameter_file=original_parameter_file,
        disable_candidate_filter=args.disable_candidate_filter,
    )
    stimulation_folder = Path(settings["StimulationFolder"]).expanduser().resolve()
    output_path = Path(settings["OutputPath"]).expanduser().resolve()
    pathway_file = Path(settings["PathwayFile"]).expanduser().resolve()
    axon_h5 = Path(settings["PointModel"]["Pathway"]["FileName"]).expanduser().resolve()
    fail_flag = str(settings.get("FailFlag", ""))
    success_flag = stimulation_folder / f"success_{fail_flag}.txt" if fail_flag else stimulation_folder / "success.txt"
    oss_time_result = output_path / "oss_time_result_PAM.h5"
    scaling_index = None if args.pathway_scaling_index <= 0 else args.pathway_scaling_index
    pathway_outputs = _pathway_outputs(output_path, scaling_index)

    status = "pending"
    step_results: dict[str, Any] = {}
    if _step_existing_status([axon_h5, pathway_file]) == "complete":
        status = "prepareaxonmodel_complete"
        step_results["prepareaxonmodel"] = {"skipped_existing_outputs": True}
    else:
        cmd = [
            str(Path(args.prepareaxonmodel_bin).expanduser().resolve()),
            str(stimulation_folder),
            "--hemi_side",
            str(_hemi_side(row.get("side", ""))),
            "--description_file",
            str(parameter_file),
        ]
        result = _run_logged_command(
            cmd=cmd,
            stdout_path=row_dir / "prepareaxonmodel_stdout.log",
            stderr_path=row_dir / "prepareaxonmodel_stderr.log",
            timeout_s=None if args.prepareaxon_timeout_s <= 0 else args.prepareaxon_timeout_s,
        )
        step_results["prepareaxonmodel"] = result
        if result["returncode"] == 0 and _step_existing_status([axon_h5, pathway_file]) == "complete":
            status = "prepareaxonmodel_complete"
        elif result["returncode"] in {"timeout", "interrupted"}:
            status = "timeout_or_interrupted"
        else:
            status = "prepareaxonmodel_failed"

    if args.stop_after_step == "prepareaxonmodel" or _status_rank(status) < _status_rank("prepareaxonmodel_complete"):
        return _finalize_row_status(row, row_index, row_dir, status, step_results, settings, pathway_outputs, filter_metadata)

    if success_flag.is_file() and oss_time_result.is_file():
        status = "ossdbs_complete"
        step_results["ossdbs"] = {"skipped_existing_outputs": True}
    else:
        cmd = [str(Path(args.ossdbs_bin).expanduser().resolve()), str(converter_json)]
        result = _run_logged_command(
            cmd=cmd,
            stdout_path=row_dir / "ossdbs_stdout.log",
            stderr_path=row_dir / "ossdbs_stderr.log",
            timeout_s=None if args.ossdbs_timeout_s <= 0 else args.ossdbs_timeout_s,
        )
        step_results["ossdbs"] = result
        if result["returncode"] == 0 and success_flag.is_file() and oss_time_result.is_file():
            status = "ossdbs_complete"
        elif result["returncode"] in {"timeout", "interrupted"}:
            status = "timeout_or_interrupted"
        else:
            status = "ossdbs_failed"

    if args.stop_after_step == "ossdbs" or _status_rank(status) < _status_rank("ossdbs_complete"):
        return _finalize_row_status(row, row_index, row_dir, status, step_results, settings, pathway_outputs, filter_metadata)

    if _step_existing_status(pathway_outputs) == "complete":
        status = "pathway_activation_complete"
        step_results["run_pathway_activation"] = {"skipped_existing_outputs": True}
    else:
        cmd = [str(Path(args.run_pathway_activation_bin).expanduser().resolve()), str(converter_json)]
        if scaling_index is not None:
            cmd.extend(["--scaling_index", str(scaling_index)])
        result = _run_logged_command(
            cmd=cmd,
            stdout_path=row_dir / "run_pathway_activation_stdout.log",
            stderr_path=row_dir / "run_pathway_activation_stderr.log",
            timeout_s=None if args.pathway_timeout_s <= 0 else args.pathway_timeout_s,
        )
        step_results["run_pathway_activation"] = result
        if result["returncode"] == 0 and _step_existing_status(pathway_outputs) == "complete":
            status = "pathway_activation_complete"
        elif result["returncode"] in {"timeout", "interrupted"}:
            status = "timeout_or_interrupted"
        else:
            status = "pathway_activation_failed"

    return _finalize_row_status(row, row_index, row_dir, status, step_results, settings, pathway_outputs, filter_metadata)


def _finalize_row_status(
    row: dict[str, str],
    row_index: int,
    row_dir: Path,
    status: str,
    step_results: dict[str, Any],
    settings: dict[str, Any],
    pathway_outputs: list[Path],
    filter_metadata: dict[str, Any],
) -> dict[str, Any]:
    stimulation_folder = Path(settings["StimulationFolder"]).expanduser().resolve()
    output_path = Path(settings["OutputPath"]).expanduser().resolve()
    pathway_file = Path(settings["PathwayFile"]).expanduser().resolve()
    axon_h5 = Path(settings["PointModel"]["Pathway"]["FileName"]).expanduser().resolve()
    fail_flag = str(settings.get("FailFlag", ""))
    success_flag = stimulation_folder / f"success_{fail_flag}.txt" if fail_flag else stimulation_folder / "success.txt"
    oss_time_result = output_path / "oss_time_result_PAM.h5"
    status_path = row_dir / "oss_activation_row_status.json"
    status_doc = {
        "generated_at": iso_now(),
        "row_index": row_index,
        "row": row,
        "row_status": status,
        "stimulation_folder": str(stimulation_folder),
        "output_path": str(output_path),
        "oss_fiber_ids_path": row.get("oss_fiber_ids_path", ""),
        "oss_n_fibers": row.get("oss_n_fibers", ""),
        "oss_fiber_ids_hash": row.get("oss_fiber_ids_hash", ""),
        "oss_fiber_id_status": row.get("oss_fiber_id_status", ""),
        "parent_fiber_ids_path": row.get("parent_fiber_ids_path", ""),
        "parent_n_fibers": row.get("parent_n_fibers", ""),
        "parent_fiber_id_status": row.get("parent_fiber_id_status", ""),
        "expected_outputs": {
            "allocated_axons_h5": str(axon_h5),
            "pathway_file": str(pathway_file),
            "oss_success_flag": str(success_flag),
            "oss_time_result": str(oss_time_result),
            "pathway_outputs": [str(path) for path in pathway_outputs],
        },
        "existing_outputs": {
            "allocated_axons_h5": axon_h5.is_file(),
            "pathway_file": pathway_file.is_file(),
            "oss_success_flag": success_flag.is_file(),
            "oss_time_result": oss_time_result.is_file(),
            "pathway_outputs": [path.is_file() for path in pathway_outputs],
        },
        "step_results": step_results,
        "candidate_filter": filter_metadata,
        "side_effects": "row_level_activation_only_no_branch_x_oss_written",
    }
    write_json(status_path, status_doc)
    return {
        "row_index": row_index,
        "model_id": row.get("model_id", ""),
        "subject_id": row.get("subject_id", ""),
        "side": row.get("side", ""),
        "row_status": status,
        "row_output_dir": str(row_dir),
        "row_status_json": str(status_path),
        "stimulation_folder": str(stimulation_folder),
        "output_path": str(output_path),
        "oss_fiber_ids_path": row.get("oss_fiber_ids_path", ""),
        "oss_n_fibers": row.get("oss_n_fibers", ""),
        "oss_fiber_ids_hash": row.get("oss_fiber_ids_hash", ""),
        "oss_fiber_id_status": row.get("oss_fiber_id_status", ""),
        "parent_fiber_ids_path": row.get("parent_fiber_ids_path", ""),
        "parent_n_fibers": row.get("parent_n_fibers", ""),
        "parent_fiber_id_status": row.get("parent_fiber_id_status", ""),
        "allocated_axons_h5_exists": axon_h5.is_file(),
        "pathway_file_exists": pathway_file.is_file(),
        "oss_success_flag_exists": success_flag.is_file(),
        "oss_time_result_exists": oss_time_result.is_file(),
        "pathway_outputs_exist": all(path.is_file() for path in pathway_outputs),
        "candidate_filter_status": filter_metadata.get("filter_status", ""),
        "filtered_stimulation_folder": filter_metadata.get("filtered_stimulation_folder", ""),
        "filtered_converter_json": filter_metadata.get("filtered_converter_json", ""),
    }


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
            "stop_after_step": args.stop_after_step,
            "pathway_scaling_index": args.pathway_scaling_index,
            "code_provenance": git_provenance(),
            "side_effects": "row_level_activation_only_no_branch_x_oss_written",
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
    parser.add_argument("--stop-after-step", choices=["prepareaxonmodel", "ossdbs", "all"], default="all", help="Stop after the requested step.")
    parser.add_argument("--pathway-scaling-index", type=int, default=1, help="Scaling index for run_pathway_activation; <=0 omits --scaling_index.")
    parser.add_argument("--prepareaxonmodel-bin", default=str(DEFAULT_PREPARE_AXON), help="prepareaxonmodel executable.")
    parser.add_argument("--ossdbs-bin", default=str(DEFAULT_OSSDBS), help="ossdbs executable.")
    parser.add_argument("--run-pathway-activation-bin", default=str(DEFAULT_PATHWAY_ACTIVATION), help="run_pathway_activation executable.")
    parser.add_argument("--prepareaxon-timeout-s", type=int, default=0, help="prepareaxonmodel timeout; <=0 disables timeout.")
    parser.add_argument("--ossdbs-timeout-s", type=int, default=0, help="ossdbs timeout; <=0 disables timeout.")
    parser.add_argument("--pathway-timeout-s", type=int, default=0, help="run_pathway_activation timeout; <=0 disables timeout.")
    parser.add_argument("--disable-candidate-filter", action="store_true", help="Disable row-local filtered stimulation folders and use the original preflight folder.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_activation_rows(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
