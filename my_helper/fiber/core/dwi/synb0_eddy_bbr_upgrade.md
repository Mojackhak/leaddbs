# Synb0-DISCO, topup, eddy, and fake B0 UI-coreg DWI upgrade

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
5. Expose the corrected b0 as Lead-DBS' existing pseudo `B0` coregistration
   volume so the UI can run and review the `B0` to anchorNative registration.

The default remains unchanged. The new branch only runs when
`DistortionCorrection` is set to `synb0`.

The previous pilot path that directly registered corrected b0 to T2w with
FLIRT BBR is not the recommended workflow. It produced technically successful
but QC-failed results when BBR was applied to T2w. The supported minimal-change
path stops after the corrected b0 is generated and lets Lead-DBS' standard
coregistration UI handle the `B0` volume.

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
- Lead-DBS coregistration tools for the later UI-driven `B0` to anchorNative
  registration.

## Important defaults

- `DistortionCorrection` defaults to `none`.
- Phase encoding defaults to `0 1 0`.
- `TotalReadoutTime` is read from the DWI JSON when available; otherwise the
  nominal value `0.05` is used and recorded in outputs.
- Single-shell DWI runs use `eddy --data_is_shelled`.
- The eddy index file is written as one space-delimited `1` per DWI volume, so
  each volume points to the first real phase-encoding row in `eddy_acqparams.txt`.
- The Synb0 branch writes the corrected b0 to
  `preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_b0.nii`.
- The corrected b0 is also exposed as Lead-DBS' pseudo `B0` modality for UI
  coregistration. It is marked as a fake coregistration volume in JSON metadata
  and is intended for coregistration QC only.
- The batch runner records `pending_ui` coregistration status for Synb0 outputs
  unless explicit script-driven coregistration is requested.
- `ea_normalize` filters `B0` from its local normalization options before calling
  any normalization backend, so fake `B0` volumes do not enter normalize
  volumes through the standard UI path.
- QC includes a distorted-b0 versus corrected-b0 overlay for polarity/readout
  review. The corrected b0 to anatomy overlay is produced later by the
  Lead-DBS UI coregistration path.
- Status CSV and subject QC JSON record phase-encoding and readout-time settings
  before Synb0 runs, so dependency failures still preserve the chosen risk
  parameters.
- The cohort runner keeps the historical `none`/ANTs behavior by default. Use
  the fake-B0 pilot to run Synb0/eddy and defer `B0` coregistration to the
  Lead-DBS UI.
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
    'RunCoregistration', false, ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'Force', true);
```

Review the QC overlays before running the full cohort. If the corrected b0 is
worse than the distorted b0, rerun the pilot with the opposite phase-encoding
vector.

After a corrected b0 passes review, load the subject in Lead-DBS and use the
standard Coregister Volumes UI to register the pseudo `B0` volume. The expected
UI output path is:

```text
coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.nii
```

Do not use this fake `B0` as a normalization input. The standard
`ea_normalize(options)` entry point removes `B0` from its local
`options.subj.coreg.anat.preop` copy before dispatching to normalization
backends.
