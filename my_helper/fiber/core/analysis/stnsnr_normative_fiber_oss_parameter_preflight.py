#!/usr/bin/env python3
"""Build fixed ten-sample pPAM parameter inputs for normative OSS rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scipy.io import loadmat

from stnsnr_four_model_readiness import DEFAULT_MATLAB, DEFAULT_VAL_ROOT
from stnsnr_hf_direct_voxel_smoke import matlab_string
from stnsnr_normative_fiber_smoke_permutation import iso_now, write_csv, write_json
from stnsnr_run_provenance import git_provenance


DEFAULT_WORKLIST = (
    DEFAULT_VAL_ROOT
    / "summary/four_model_execution/normative_fiber_oss_sidecar_worklist/normative_fiber_oss_sidecar_worklist.csv"
)
DEFAULT_OUTPUT_DIR = DEFAULT_VAL_ROOT / "summary/four_model_execution/normative_fiber_oss_parameter_preflight"
DEFAULT_OSS_CONVERTER = Path("/opt/anaconda3/envs/ossdbsv2/bin/leaddbs2ossdbs")
PAM_N_SAMPLES = 10


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")
    return slug or "row"


def _split_paths(value: str) -> list[Path]:
    return [Path(part).expanduser().resolve() for part in value.split(";") if part.strip()]


def _patient_dir_from_source(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if parent.name.startswith("sub-"):
            return parent
    raise RuntimeError(f"could not infer patient directory from {path}")


def _stimparameter_from_source(path: Path) -> Path:
    matches = sorted(
        item
        for item in path.parent.glob("*_desc-stimparameters.mat")
        if item.is_file() and not item.name.startswith("._")
    )
    if not matches:
        raise RuntimeError(f"no desc-stimparameters MAT file found next to {path}")
    if len(matches) > 1:
        raise RuntimeError(f"multiple desc-stimparameters MAT files found next to {path}: {matches}")
    return matches[0]


def _canonical_oss_hemi_side(row: dict[str, str]) -> int:
    side = str(row.get("side", "")).upper()
    mode = str(row.get("canonicalization_mode", ""))
    if side == "R" and mode in {"", "native_right"}:
        return 0
    if side == "L" and mode == "left_geometry_to_right":
        return 0
    raise ValueError(
        f"unsupported OSS canonicalization for side={side!r}, mode={mode!r}"
    )


def _matlab_side_index(side: str) -> int:
    if side == "R":
        return 1
    if side == "L":
        return 2
    raise RuntimeError(f"unsupported side: {side!r}")


def _transform_left_to_right_for_row(row: dict[str, str]) -> bool:
    side = str(row.get("side", "")).upper()
    mode = str(row.get("canonicalization_mode", ""))
    if side == "L" and mode == "left_geometry_to_right":
        return True
    if side == "R" and mode in {"", "native_right"}:
        return False
    raise ValueError(
        f"unsupported OSS canonicalization for side={side!r}, mode={mode!r}"
    )


def _read_source_frequency_hz(source_mat: Path, side: str) -> tuple[float | None, str]:
    mat = loadmat(source_mat, squeeze_me=True, struct_as_record=False)
    stim = mat.get("S")
    if stim is None:
        return None, "missing_S"
    side_prefix = "L" if side == "L" else "R"
    for source_index in range(1, 5):
        field = f"{side_prefix}s{source_index}"
        if not hasattr(stim, field):
            continue
        item = getattr(stim, field)
        amp = getattr(item, "amp", 0)
        try:
            amp_value = float(amp)
        except (TypeError, ValueError):
            amp_value = 0.0
        if amp_value == 0.0:
            continue
        freq = getattr(item, "frequency", None)
        if freq is None:
            continue
        try:
            return float(freq), field
        except (TypeError, ValueError):
            return None, f"{field}_invalid_frequency"
    freq = getattr(stim, "frequency", None)
    if freq is not None:
        try:
            return float(freq), "S.frequency"
        except (TypeError, ValueError):
            return None, "S.frequency_invalid"
    return None, "no_active_source_frequency"


def _validate_or_patch_converter_frequency(converter_json: Path, source_frequency_hz: float | None) -> dict[str, Any]:
    if source_frequency_hz is None:
        return {
            "frequency_validation_status": "failed_missing_source_frequency",
            "source_frequency_hz": "",
            "converter_frequency_hz_original": "",
            "converter_frequency_hz_final": "",
            "frequency_patch_applied": "false",
        }
    if not converter_json.is_file():
        return {
            "frequency_validation_status": "failed_missing_converter_json",
            "source_frequency_hz": source_frequency_hz,
            "converter_frequency_hz_original": "",
            "converter_frequency_hz_final": "",
            "frequency_patch_applied": "false",
        }
    data = json.loads(converter_json.read_text(encoding="utf-8"))
    signal = data.setdefault("StimulationSignal", {})
    original = signal.get("Frequency[Hz]")
    try:
        original_float = float(original)
    except (TypeError, ValueError):
        original_float = None
    patch_applied = False
    if original_float is None or abs(original_float - source_frequency_hz) > 1e-9:
        signal["Frequency[Hz]"] = float(source_frequency_hz)
        converter_json.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        patch_applied = True
    final = float(signal["Frequency[Hz]"])
    status = "frequency_validated"
    if patch_applied:
        status = "frequency_patched_from_source_S"
    return {
        "frequency_validation_status": status,
        "source_frequency_hz": source_frequency_hz,
        "converter_frequency_hz_original": "" if original_float is None else original_float,
        "converter_frequency_hz_final": final,
        "frequency_patch_applied": str(patch_applied).lower(),
    }


def _validate_or_patch_stimulation_folder(converter_json: Path, expected_folder: Path) -> dict[str, Any]:
    if not converter_json.is_file():
        return {
            "stimulation_folder_validation_status": "failed_missing_converter_json",
            "stimulation_folder_original": "",
            "stimulation_folder_final": "",
            "stimulation_folder_patch_applied": "false",
        }
    data = json.loads(converter_json.read_text(encoding="utf-8"))
    expected = str(expected_folder)
    original = str(data.get("StimulationFolder", ""))
    patch_applied = original != expected
    if patch_applied:
        data["StimulationFolder"] = expected
        converter_json.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return {
        "stimulation_folder_validation_status": "stimulation_folder_patched" if patch_applied else "stimulation_folder_validated",
        "stimulation_folder_original": original,
        "stimulation_folder_final": expected,
        "stimulation_folder_patch_applied": str(patch_applied).lower(),
    }


def _run_command(cmd: list[str], timeout_s: int | None = None) -> dict[str, Any]:
    started = iso_now()
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
    return {
        "cmd": cmd,
        "started_at": started,
        "finished_at": iso_now(),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _matlab_script(
    *,
    repo_root: Path,
    source_mat: Path,
    patient_dir: Path,
    row_dir: Path,
    matlab_side_index: int,
    transform_left_to_right: bool = False,
) -> str:
    stim_dir = row_dir / "lead_dbs_stimulations"
    transform_lines = []
    if transform_left_to_right:
        transform_lines = [
            "  if requested_side_idx ~= 2; error('left-to-right transform requires the left source side'); end",
            "  if isempty(settings.contactLocation{requested_side_idx}); error('left contact locations are missing'); end",
            "  settings.contactLocation{requested_side_idx} = ea_flip_lr_nonlinear(settings.contactLocation{requested_side_idx});",
            "  settings.Implantation_coordinate(requested_side_idx,:) = ea_flip_lr_nonlinear(settings.Implantation_coordinate(requested_side_idx,:));",
            "  settings.Second_coordinate(requested_side_idx,:) = ea_flip_lr_nonlinear(settings.Second_coordinate(requested_side_idx,:));",
            "  if all(isfinite(settings.yMarkerMNI(requested_side_idx,:)))",
            "    settings.yMarkerMNI(requested_side_idx,:) = ea_flip_lr_nonlinear(settings.yMarkerMNI(requested_side_idx,:));",
            "  end",
            "  if all(isfinite(settings.headMNI(requested_side_idx,:)))",
            "    settings.headMNI(requested_side_idx,:) = ea_flip_lr_nonlinear(settings.headMNI(requested_side_idx,:));",
            "  end",
            "  settings.contactLocation{1} = settings.contactLocation{requested_side_idx};",
            "  settings.Implantation_coordinate(1,:) = settings.Implantation_coordinate(requested_side_idx,:);",
            "  settings.Second_coordinate(1,:) = settings.Second_coordinate(requested_side_idx,:);",
            "  if isfield(settings, 'yMarkerMNI'); settings.yMarkerMNI(1,:) = settings.yMarkerMNI(requested_side_idx,:); end",
            "  if isfield(settings, 'headMNI'); settings.headMNI(1,:) = settings.headMNI(requested_side_idx,:); end",
            "  original_recon_file = options.subj.recon.recon;",
            "  canonical_recon_loaded = load(original_recon_file, 'reco');",
            "  if ~isfield(canonical_recon_loaded, 'reco') || ~isfield(canonical_recon_loaded.reco, 'mni') || ~iscell(canonical_recon_loaded.reco.mni.coords_mm)",
            "    error('MNI reconstruction coordinates are unavailable for right-canonical fiber allocation');",
            "  end",
            "  reco = canonical_recon_loaded.reco; %#ok<NASGU>",
            "  if numel(reco.mni.coords_mm) < requested_side_idx || isempty(reco.mni.coords_mm{requested_side_idx})",
            "    error('left reconstruction coordinates are missing for right-canonical fiber allocation');",
            "  end",
            "  reco.mni.coords_mm{1} = ea_flip_lr_nonlinear(reco.mni.coords_mm{requested_side_idx});",
            "  canonical_recon_file = fullfile(preflight_stim_dir, 'right_canonical_reconstruction.mat');",
            "  save(canonical_recon_file, 'reco', '-v7.3');",
            "  options.subj.recon.recon = canonical_recon_file;",
            "  fprintf('RIGHT_CANONICAL_RECONSTRUCTION=%s\\n', canonical_recon_file);",
            "  fprintf('LEFT_TO_RIGHT_TRANSFORM=ea_flip_lr_nonlinear\\n');",
        ]
    canonical_stimulation_lines = []
    if transform_left_to_right:
        canonical_stimulation_lines = [
            "  if size(settings.Phi_vector,1) < 2; error('left Phi_vector is missing'); end",
            "  settings.Phi_vector(1,:) = settings.Phi_vector(2,:);",
            "  if size(settings.current_control,1) < 2; error('left current_control is missing'); end",
            "  settings.current_control(1,:) = settings.current_control(2,:);",
            "  if isfield(settings, 'pulseWidth'); settings.pulseWidth(1,:) = settings.pulseWidth(2,:); end",
            "  if isfield(settings, 'Case_grounding'); settings.Case_grounding(1,:) = settings.Case_grounding(2,:); end",
            "  if isfield(settings, 'Activation_threshold_VTA'); settings.Activation_threshold_VTA(1,:) = settings.Activation_threshold_VTA(2,:); end",
            "  if isfield(settings, 'stim_center'); settings.stim_center(1,:) = settings.stim_center(2,:); end",
            "  fprintf('RIGHT_CANONICAL_STIMULATION_SLOT=1\\n');",
        ]
    return "\n".join(
        [
            "try",
            f"  repo_root = {matlab_string(repo_root)};",
            "  cd(repo_root);",
            "  addpath(genpath(repo_root));",
            f"  source_mat = {matlab_string(source_mat)};",
            f"  patient_path = {matlab_string(patient_dir)};",
            f"  preflight_stim_dir = {matlab_string(stim_dir)};",
            f"  requested_side_idx = {matlab_side_index};",
            "  if ~exist(preflight_stim_dir, 'dir'); mkdir(preflight_stim_dir); end",
            "  loaded = load(source_mat);",
            "  if isfield(loaded, 'S')",
            "    S = loaded.S;",
            "  else",
            "    error('source MAT does not contain S');",
            "  end",
            "  options = ea_get_OSS_DBS_options(patient_path, 0, '', 0);",
            "  options.native = 0;",
            "  options.subj.stimDir = preflight_stim_dir;",
            "  options.prefs.machine.vatsettings.butenko_cond_model = 'ColeCole4';",
            "  options.prefs.machine.vatsettings.butenko_prob_PAM = 1;",
            f"  options.prefs.machine.vatsettings.butenko_N_samples = {PAM_N_SAMPLES};",
            "  options.prefs.machine.vatsettings.butenko_probabilistic_parameter = 'Fiber Diameter';",
            "  options.prefs.machine.vatsettings.butenko_parameter_limits = [1, 4];",
            "  options.prefs.machine.vatsettings.butenko_sampling_distribution = 'Equidistant';",
            "  options.prefs.machine.vatsettings.butenko_calcPAM = 1;",
            "  options.prefs.machine.vatsettings.butenko_calcAxonActivation = 1;",
            "  options.prefs.machine.vatsettings.butenko_calcVAT = 0;",
            "  options.prefs.machine.vatsettings.butenko_tensorData = 0;",
            "  options.prefs.machine.vatsettings.butenko_connectome = 'dTOR-985 Full (Elias 2024)';",
            "  [settings, S, env] = ea_prepare_ossdbs(options, S); %#ok<ASGLU>",
            "  settings.outOfCore = 0;",
            "  settings.reuse_warped_connectome = 0;",
            "  outputPaths = ea_get_oss_outputPaths(options, S);",
            "  settings = ea_segment_MRI(options, settings, outputPaths);",
            "  settings.DTI_data_name = ea_prepare_DTI(options, outputPaths);",
            "  settings = ea_get_oss_reco(options, settings);",
            *transform_lines,
            "  [S, settings, activeSources] = ea_check_stimSources(options, S, settings);",
            "  active_for_side = activeSources(requested_side_idx, :);",
            "  source_index = active_for_side(find(~isnan(active_for_side), 1, 'first'));",
            "  if isempty(source_index)",
            "    source_index = find(any(~isnan(activeSources), 1), 1, 'first');",
            "  end",
            "  if isempty(source_index)",
            "    error('no active stimulation source found');",
            "  end",
            "  settings = ea_get_stimProtocol(options, S, settings, activeSources, source_index);",
            *canonical_stimulation_lines,
            "  if settings.calcAxonActivation",
            "    [settings, fibersFound] = ea_prepare_fibers(options, S, settings, outputPaths); %#ok<ASGLU>",
            "  end",
            "  parameterFile = ea_save_ossdbs_settings(options, S, settings, outputPaths);",
            "  if ~isfield(settings, 'Phi_vector'); error('settings.Phi_vector missing'); end",
            "  if ~isfield(settings, 'current_control'); error('settings.current_control missing'); end",
            "  if ~isfield(settings, 'Implantation_coordinate'); error('settings.Implantation_coordinate missing'); end",
            "  if settings.calcAxonActivation && ~isfield(settings, 'pathwayParameterFile'); error('settings.pathwayParameterFile missing'); end",
            "  outputPaths.HemiSimFolder = fullfile(outputPaths.outputDir, 'OSS_sim_files_rh');",
            "  if ~exist(outputPaths.HemiSimFolder, 'dir'); mkdir(outputPaths.HemiSimFolder); end",
            f"  for sample_i = 1:{PAM_N_SAMPLES}",
            "    settings = ea_updatePAM_parameter(options, settings, outputPaths, sample_i);",
            "    sample_dir = fullfile(preflight_stim_dir, 'pam_parameter_samples', sprintf('sample_%02d', sample_i));",
            "    if ~exist(sample_dir, 'dir'); mkdir(sample_dir); end",
            "    sample_parameter_file = fullfile(sample_dir, 'oss-dbs_parameters.mat');",
            "    copyfile(parameterFile, sample_parameter_file);",
            "    fprintf('SAMPLE_PARAMETER_FILE=%d|%s\\n', sample_i, sample_parameter_file);",
            "  end",
            "  fprintf('PARAMETER_FILE=%s\\n', parameterFile);",
            "  fprintf('SOURCE_INDEX=%d\\n', source_index);",
            "catch ME",
            "  fprintf(2, 'OSS_PARAMETER_PREFLIGHT_ERROR=%s\\n', ME.message);",
            "  for k = 1:numel(ME.stack)",
            "    fprintf(2, '  at %s:%d\\n', ME.stack(k).file, ME.stack(k).line);",
            "  end",
            "  exit(2);",
            "end",
            "exit(0);",
            "",
        ]
    )


def _parse_parameter_file(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("PARAMETER_FILE="):
            return line.split("=", 1)[1].strip()
    return ""


def _parse_sample_parameter_files(stdout: str) -> list[tuple[int, str]]:
    samples: list[tuple[int, str]] = []
    for line in stdout.splitlines():
        if not line.startswith("SAMPLE_PARAMETER_FILE="):
            continue
        payload = line.split("=", 1)[1].strip()
        sample_index_text, separator, parameter_file = payload.partition("|")
        if not separator or not parameter_file:
            raise RuntimeError(f"invalid sample parameter marker: {line!r}")
        samples.append((int(sample_index_text), parameter_file))
    return samples


def _run_row_preflight(
    *,
    row: dict[str, str],
    row_index: int,
    output_dir: Path,
    matlab_bin: Path,
    oss_converter: Path,
    run_converter: bool,
    matlab_timeout_s: int | None,
    converter_timeout_s: int | None,
) -> dict[str, Any]:
    source_paths = _split_paths(row.get("source_paths", ""))
    if not source_paths:
        return {
            "row_index": row_index,
            "model_id": row.get("model_id", ""),
            "subject_id": row.get("subject_id", ""),
            "side": row.get("side", ""),
            "preflight_status": "failed_no_source_paths",
        }

    source_path = source_paths[0]
    patient_dir = _patient_dir_from_source(source_path)
    source_mat = _stimparameter_from_source(source_path)
    source_frequency_hz, source_frequency_field = _read_source_frequency_hz(source_mat, row.get("side", ""))
    row_slug = "_".join(
        _safe_slug(str(part))
        for part in [f"row{row_index:04d}", row.get("model_id", ""), row.get("subject_id", ""), row.get("side", "")]
    )
    row_dir = output_dir / row_slug
    row_dir.mkdir(parents=True, exist_ok=True)
    script_path = row_dir / "run_oss_parameter_preflight.m"
    script_path.write_text(
        _matlab_script(
            repo_root=_repo_root(),
            source_mat=source_mat,
            patient_dir=patient_dir,
            row_dir=row_dir,
            matlab_side_index=_matlab_side_index(row.get("side", "")),
            transform_left_to_right=_transform_left_to_right_for_row(row),
        ),
        encoding="utf-8",
    )

    matlab_result = _run_command([str(matlab_bin), "-batch", f"run({matlab_string(script_path)})"], timeout_s=matlab_timeout_s)
    parameter_file = _parse_parameter_file(matlab_result["stdout"])
    try:
        parsed_samples = _parse_sample_parameter_files(matlab_result["stdout"])
    except (RuntimeError, ValueError):
        parsed_samples = []
    expected_sample_indexes = list(range(1, PAM_N_SAMPLES + 1))
    observed_sample_indexes = [sample_index for sample_index, _ in parsed_samples]
    sample_parameter_files = [Path(path).expanduser().resolve() for _, path in parsed_samples]
    sample_parameters_complete = (
        observed_sample_indexes == expected_sample_indexes
        and all(path.is_file() for path in sample_parameter_files)
    )
    sample_manifest_path = row_dir / "oss_parameter_samples_manifest.json"
    write_json(
        sample_manifest_path,
        {
            "generated_at": iso_now(),
            "pam_n_samples": PAM_N_SAMPLES,
            "probabilistic_parameter": "Fiber Diameter",
            "parameter_limits_um": [1.0, 4.0],
            "sampling_distribution": "Equidistant",
            "sample_generation": "ea_updatePAM_parameter_after_geometry_canonicalization",
            "sample_parameters_complete": sample_parameters_complete,
            "samples": [
                {
                    "sample_index": sample_index,
                    "parameter_file": str(path),
                    "parameter_file_exists": path.is_file(),
                }
                for (sample_index, _), path in zip(parsed_samples, sample_parameter_files, strict=True)
            ],
        },
    )
    converter_result: dict[str, Any] | None = None
    converter_json = ""
    if matlab_result["returncode"] == 0 and parameter_file and run_converter:
        converter_output = Path(parameter_file).parent
        converter_result = _run_command(
            [
                str(oss_converter),
                "--hemi_side",
                str(_canonical_oss_hemi_side(row)),
                parameter_file,
                "--output_path",
                str(converter_output),
            ],
            timeout_s=converter_timeout_s,
        )
        candidate_jsons = [
            Path(parameter_file).with_suffix(".json"),
        ]
        for candidate_json in candidate_jsons:
            if candidate_json.is_file():
                converter_json = str(candidate_json)
                break
    frequency_validation = _validate_or_patch_converter_frequency(Path(converter_json), source_frequency_hz) if converter_json else {
        "frequency_validation_status": "not_run_no_converter_json",
        "source_frequency_hz": "" if source_frequency_hz is None else source_frequency_hz,
        "converter_frequency_hz_original": "",
        "converter_frequency_hz_final": "",
        "frequency_patch_applied": "false",
    }
    stimulation_folder_validation = _validate_or_patch_stimulation_folder(Path(converter_json), Path(parameter_file).parent) if converter_json and parameter_file else {
        "stimulation_folder_validation_status": "not_run_no_converter_json",
        "stimulation_folder_original": "",
        "stimulation_folder_final": "",
        "stimulation_folder_patch_applied": "false",
    }
    if matlab_result["returncode"] != 0:
        status = "failed_matlab_parameter_dictionary"
    elif not parameter_file:
        status = "failed_missing_parameter_file_stdout"
    elif not sample_parameters_complete:
        status = "failed_incomplete_probabilistic_sample_parameters"
    elif run_converter and (converter_result is None or converter_result["returncode"] != 0):
        status = "failed_leaddbs2ossdbs_converter"
    elif run_converter and not converter_json:
        status = "failed_converter_json_missing"
    elif run_converter and str(frequency_validation["frequency_validation_status"]).startswith("failed"):
        status = "failed_frequency_validation"
    elif run_converter and str(stimulation_folder_validation["stimulation_folder_validation_status"]).startswith("failed"):
        status = "failed_stimulation_folder_validation"
    else:
        status = "parameter_preflight_passed"

    row_manifest_path = row_dir / "oss_parameter_preflight_row_manifest.json"
    write_json(
        row_manifest_path,
        {
            "generated_at": iso_now(),
            "row_index": row_index,
            "worklist_row": row,
            "source_path_used": str(source_path),
            "source_mat": str(source_mat),
            "source_frequency_hz": source_frequency_hz,
            "source_frequency_field": source_frequency_field,
            "patient_dir": str(patient_dir),
            "matlab_script": str(script_path),
            "parameter_file": parameter_file,
            "pam_n_samples": PAM_N_SAMPLES,
            "probabilistic_parameter": "Fiber Diameter",
            "parameter_limits_um": [1.0, 4.0],
            "sampling_distribution": "Equidistant",
            "sample_parameter_manifest": str(sample_manifest_path),
            "sample_parameter_files": [str(path) for path in sample_parameter_files],
            "sample_parameters_complete": sample_parameters_complete,
            "converter_json": converter_json,
            "frequency_validation": frequency_validation,
            "stimulation_folder_validation": stimulation_folder_validation,
            "preflight_status": status,
            "matlab_result": matlab_result,
            "converter_result": converter_result,
            "side_effects": "parameter_preflight_only_no_final_oss_sidecars_created",
        },
    )
    return {
        "row_index": row_index,
        "model_id": row.get("model_id", ""),
        "subject_id": row.get("subject_id", ""),
        "side": row.get("side", ""),
        "source_component": row.get("source_component", ""),
        "oss_fiber_ids_path": row.get("oss_fiber_ids_path", ""),
        "oss_n_fibers": row.get("oss_n_fibers", ""),
        "oss_fiber_ids_hash": row.get("oss_fiber_ids_hash", ""),
        "oss_fiber_id_status": row.get("oss_fiber_id_status", ""),
        "parent_fiber_ids_path": row.get("parent_fiber_ids_path", ""),
        "parent_n_fibers": row.get("parent_n_fibers", ""),
        "parent_fiber_id_status": row.get("parent_fiber_id_status", ""),
        "source_path_used": str(source_path),
        "source_mat": str(source_mat),
        "source_frequency_hz": "" if source_frequency_hz is None else source_frequency_hz,
        "source_frequency_field": source_frequency_field,
        "patient_dir": str(patient_dir),
        "row_output_dir": str(row_dir),
        "matlab_returncode": matlab_result["returncode"],
        "parameter_file": parameter_file,
        "pam_n_samples": PAM_N_SAMPLES,
        "probabilistic_parameter": "Fiber Diameter",
        "parameter_limits_um": "1;4",
        "sampling_distribution": "Equidistant",
        "sample_parameter_manifest": str(sample_manifest_path),
        "sample_parameter_files": ";".join(str(path) for path in sample_parameter_files),
        "sample_parameters_complete": str(sample_parameters_complete).lower(),
        "run_converter": str(bool(run_converter)).lower(),
        "converter_returncode": "" if converter_result is None else converter_result["returncode"],
        "converter_json": converter_json,
        **frequency_validation,
        **stimulation_folder_validation,
        "preflight_status": status,
        "row_manifest": str(row_manifest_path),
    }


def run_parameter_preflight(args: argparse.Namespace) -> int:
    worklist_csv = Path(args.worklist_csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_csv_rows(worklist_csv)
    if args.model_id:
        requested = set(args.model_id)
        rows = [row for row in rows if row.get("model_id") in requested]
    rows = [row for row in rows if row.get("side_input_status") == "ready_source_files"]
    if args.one_row_per_model:
        first_rows: list[dict[str, str]] = []
        seen_models: set[str] = set()
        for row in rows:
            model_id = row.get("model_id", "")
            if model_id and model_id not in seen_models:
                first_rows.append(row)
                seen_models.add(model_id)
        rows = first_rows
    if args.max_rows is None and not args.one_row_per_model:
        rows = rows[:1]
    elif args.max_rows is not None and args.max_rows > 0:
        rows = rows[: args.max_rows]
    if not rows:
        raise RuntimeError("no ready OSS worklist rows selected for parameter preflight")

    matlab_bin = Path(args.matlab_bin).expanduser().resolve()
    oss_converter = Path(args.oss_converter).expanduser().resolve()
    summary_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        print(f"OSS parameter preflight row {index}: {row.get('model_id')} {row.get('subject_id')} {row.get('side')}")
        summary_rows.append(
            _run_row_preflight(
                row=row,
                row_index=index,
                output_dir=output_dir,
                matlab_bin=matlab_bin,
                oss_converter=oss_converter,
                run_converter=not args.skip_converter,
                matlab_timeout_s=None if args.matlab_timeout_s <= 0 else args.matlab_timeout_s,
                converter_timeout_s=None if args.converter_timeout_s <= 0 else args.converter_timeout_s,
            )
        )

    summary_path = output_dir / "normative_fiber_oss_parameter_preflight_summary.csv"
    manifest_path = output_dir / "normative_fiber_oss_parameter_preflight_manifest.json"
    write_csv(summary_path, summary_rows, list(summary_rows[0].keys()))
    status_counts: dict[str, int] = {}
    for row in summary_rows:
        status = str(row.get("preflight_status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
    write_json(
        manifest_path,
        {
            "generated_at": iso_now(),
            "worklist_csv": str(worklist_csv),
            "output_dir": str(output_dir),
            "n_rows": len(summary_rows),
            "status_counts": status_counts,
            "matlab_bin": str(matlab_bin),
            "oss_converter": str(oss_converter),
            "skip_converter": bool(args.skip_converter),
            "pam_n_samples": PAM_N_SAMPLES,
            "sample_count_source": "internal_fixed_contract",
            "code_provenance": git_provenance(),
            "side_effects": "parameter_preflight_only_no_final_oss_sidecars_created",
            "outputs": {
                "summary_csv": str(summary_path),
                "manifest_json": str(manifest_path),
            },
        },
    )
    print(f"OSS parameter preflight summary: {summary_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worklist-csv", default=str(DEFAULT_WORKLIST), help="OSS sidecar worklist CSV.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Parameter preflight output directory.")
    parser.add_argument("--model-id", action="append", choices=["B_DTOR", "D_DTOR"], help="Optional model ID filter.")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Maximum ready worklist rows to preflight; default is 1 unless --one-row-per-model is set; <=0 means all.",
    )
    parser.add_argument(
        "--one-row-per-model",
        action="store_true",
        help="Preflight the first ready worklist row for each selected model before applying --max-rows.",
    )
    parser.add_argument("--matlab-bin", default=str(DEFAULT_MATLAB), help="MATLAB executable.")
    parser.add_argument("--oss-converter", default=str(DEFAULT_OSS_CONVERTER), help="leaddbs2ossdbs executable.")
    parser.add_argument("--skip-converter", action="store_true", help="Only run MATLAB parameter dictionary preparation.")
    parser.add_argument("--matlab-timeout-s", type=int, default=0, help="MATLAB timeout in seconds; <=0 disables timeout.")
    parser.add_argument("--converter-timeout-s", type=int, default=600, help="Converter timeout in seconds; <=0 disables timeout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_parameter_preflight(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
