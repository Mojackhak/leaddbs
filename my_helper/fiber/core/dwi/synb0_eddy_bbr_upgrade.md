# Synb0-DISCO, topup, eddy, and BBR DWI upgrade

This note documents the optional STN/SNr DWI preprocessing upgrade implemented for
`mh_fiber_register_imported_dwi_batch`.

## Goal

The existing imported-DWI registration path stages the raw DWI, extracts a mean
b0, and registers that distorted b0 directly to anchorNative anatomy. The
optional upgrade adds a distortion-correction branch:

1. Extract a distorted mean b0.
2. Run Synb0-DISCO from the distorted b0 and anchorNative T1w.
3. Use the Synb0-DISCO topup output with eddy for susceptibility, eddy-current,
   and motion correction.
4. Extract a corrected mean b0.
5. Register the corrected b0 to anchorNative anatomy with 6 DOF BBR when
   requested.

The default remains unchanged. The new branch only runs when
`DistortionCorrection` is set to `synb0`.

## Dependencies

- Synb0-DISCO through Docker or Singularity.
- A Synb0-DISCO image, configured through `Synb0Image`. The default is
  `leonyichencai/synb0-disco:v3.1`, matching the MASILab Synb0-DISCO Docker
  instructions.
- A FreeSurfer license file, configured through `FreeSurferLicense` or detected
  from `FS_LICENSE`, `$FREESURFER_HOME/license.txt`,
  `/Applications/freesurfer/*/license.txt`, or `~/license.txt`.
- FSL eddy/topup-compatible outputs. The wrapper prefers the bundled
  `ext_libs/dsi_studio/plugin/eddy.maca64` binary on macOS arm64.
- FLIRT/FAST for BBR through `ea_flirtbbr`; on Apple silicon these may require
  Rosetta if the bundled binaries are Intel-only.

## Important defaults

- `DistortionCorrection` defaults to `none`.
- Phase encoding defaults to `0 1 0`.
- `TotalReadoutTime` is read from the DWI JSON when available; otherwise the
  nominal value `0.05` is used and recorded in outputs.
- Single-shell DWI runs use `eddy --data_is_shelled`.
- The eddy index file is written as one space-delimited `1` per DWI volume, so
  each volume points to the first real phase-encoding row in `eddy_acqparams.txt`.
- BBR is optional through `CoregistrationMethod='FLIRTBBR'`; existing ANTs, SPM,
  and Hybrid SPM/ANTs paths remain available.
- If FLIRT BBR fails, the pilot path falls back to an ANTs linear registration
  so the corrected-b0 workflow can still produce reviewable overlays.
- QC includes both the corrected b0 on anchor anatomy and a distorted-b0 versus
  corrected-b0 overlay for polarity/readout review.
- Status CSV and subject QC JSON record phase-encoding and readout-time settings
  before Synb0 runs, so dependency failures still preserve the chosen risk
  parameters.
- The cohort runner keeps the historical `none`/ANTs behavior by default. Set
  `runMode = 'synb0_pilot'` in `run_stnsnr_dwi_registration.m` to run the
  single-subject Synb0/eddy/FLIRT BBR pilot.
- The Docker wrapper copies the FreeSurfer license into the Synb0 working
  directory before mounting it, avoiding Docker Desktop file-sharing failures
  for `/Applications`. It also requests `linux/amd64`, because the current
  Synb0-DISCO image is amd64-only.
- The Docker wrapper checks Docker's reported memory before running Synb0-DISCO.
  `Synb0MinDockerMemoryGB` defaults to `12`; set it to `0` only when intentionally
  bypassing this preflight.
- Forced pilot reruns use a fresh Synb0 run directory under
  `preprocessing/dwi/work/synb0_eddy/` so partial container outputs from a
  previous failed run cannot be mistaken for valid results. The wrapper writes
  the container stdout/stderr to `synb0.log` inside the run directory.
- If `synb0.log` reports `Killed` during `/extra/inference.py`, Docker did not
  provide enough memory for Synb0-DISCO inference. Increase Docker Desktop's
  memory limit and rerun the pilot with `Force=true`; the wrapper reports this
  as `ea_synb0:InferenceKilled` instead of a generic missing-output failure.

## Suggested pilot

Run the dedicated single-subject pilot script first:

```matlab
run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_synb0_bbr_pilot.m')
```

The equivalent direct call is:

```matlab
mh_fiber_register_imported_dwi_batch( ...
    'StudyRoot', '/Volumes/VAL/STNSNr', ...
    'RepoDir', '/Users/mojackhu/Github/leaddbs', ...
    'SubjectIds', {'ChenMeiJu'}, ...
    'DistortionCorrection', 'synb0', ...
    'CoregistrationMethod', 'FLIRTBBR', ...
    'CoregistrationTag', 'dwi_t2_synb0_flirtbbr', ...
    'Force', true);
```

Review the QC overlays before running the full cohort. If the corrected b0 is
worse than the distorted b0, rerun the pilot with the opposite phase-encoding
vector.
