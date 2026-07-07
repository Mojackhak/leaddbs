# Meige DWI Synb0/Eddy Fake-B0 Goal

Date: 2026-07-06

Branch: `stnvop`

Implementation status:

- Goal definition: complete.
- Raw DWI basename discovery for Meige-style `*_acq-ax_dwi` files:
  implemented and covered by a focused MATLAB test.
- Meige read-only jobSpec validation: 22 subjects resolved to existing raw DWI
  four-file sets.
- Meige project wrapper with non-destructive `DryRun` mode: implemented and
  covered by a focused MATLAB test.
- Next implementation target: Synb0/eddy pilot execution for `Meige001`,
  `Meige008`, and `Meige021`.
- Pilot preflight: passed. Dry-run parameters match this document; raw DWI
  four-file sets, anchorNative T1w/T2w images, Docker, local Synb0 image, and
  FreeSurfer license are present for the pilot run.
- Pilot attempt 1: failed before Synb0. The raw `*_acq-ax_dwi.nii.gz` files
  were discovered correctly, but gzip staging wrote `*_acq-ax_dwi.nii` while
  downstream code expected the formal staged basename `sub-<ID>_ses-preop_dwi`.
  Gzip staging has been fixed so raw DWI inputs are decompressed to a temporary
  path and then copied to the formal staged output path.
- Regression tests after the staging fix: raw basename discovery passed,
  acquisition-labeled gzipped DWI staging passed, and the Meige wrapper dry-run
  test passed.
- Failed pilot staging artifacts for `Meige001`, `Meige008`, and `Meige021`,
  plus the attempt-1 status CSV, were moved to Trash before rerun:
  `/Volumes/VAL/.Trashes/501/meige_dwi_synb0_pilot_failed_stage_20260706_123734`.
- Pilot attempt 2: `Meige001` and `Meige008` completed Synb0/eddy and wrote
  corrected DWI derivatives. MATLAB was killed with exit code 137 immediately
  after starting `Meige021`, before the batch status CSV was written. The
  orphan `Meige021` Synb0 Docker container was monitored until it exited and
  produced `b0_u.nii.gz`, `topup_fieldcoef.nii.gz`, and `topup_movpar.txt` in
  the local Synb0 work root. Rerun the pilot with `Force=false` so `ea_synb0`
  reuses existing Synb0 outputs, completes `Meige021` eddy, and writes a
  complete three-row status CSV.
- Pilot attempt 3: `Meige021` completed Synb0/eddy by reusing the completed
  local Synb0 output. `Meige001` and `Meige008` incorrectly failed during
  rerun because `archive_synb0_result` treats an existing project Synb0 archive
  as an error when `Force=false`. Fix rerun idempotency so an existing archive
  can be reused when required archive outputs are already present, then rerun
  the pilot status table.
- Pilot attempt 4: passed. `Meige001`, `Meige008`, and `Meige021` all report
  `status=pending_ui_coregistration`, `synb0_status=ok`, `eddy_status=ok`, and
  `coregistration_status=pending_ui` in
  `/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_status.csv`.
  Corrected DWI, corrected b0, bval, bvec, and fake-B0 metadata files exist for
  all three pilot subjects. Fake-B0 metadata record
  `FakeCoregisterVolume=true`, `ExcludeFromNormalization=true`, and
  `PhaseEncodingVector=0 1 0`. `Meige001` used JSON readout `0.046215`;
  `Meige008` and `Meige021` used default readout `0.05`. `Meige008` has
  `low_resolution_warning=true` because its DWI voxel z-size is about 5 mm and
  should receive especially careful UI QC.
- Pilot visual QC: distorted-vs-corrected b0 overlays for `Meige001`,
  `Meige008`, and `Meige021` show no obvious phase-encoding polarity reversal
  or grossly worsened distortion. This supports proceeding to the remaining
  cohort under the accepted `[0 1 0]`, readout-fallback `0.05` policy, but does
  not replace the later Lead-DBS UI b0-to-anchorNative manual QC. Preserve the
  pilot status CSV before processing the remaining subjects so untracked pilot
  records are not overwritten.
- Remaining-cohort execution plan: archive the three-row pilot status CSV to a
  versioned import-log filename, then run the 19 non-pilot subjects
  (`Meige002-Meige007`, `Meige009-Meige020`, and `Dys022`) with `Force=false`,
  `MaxConcurrentSynb0=1`, and the same parameter policy. After the remaining
  run, combine pilot and remaining status rows into a 22-subject processing
  record.
- Remaining-cohort preprocessing completed for the 19 non-pilot subjects.
  Lead-DBS UI B0-to-anchorNative coregistration and manual QC are
  user-performed follow-up steps, not Codex automation requirements.
- UI staging issue found during manual normalization approval for `Meige008`:
  Lead-DBS expects the pseudo-B0 image at
  `coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.nii`.
  The automated preprocessing must stage this image and its JSON sidecar from
  the corrected mean b0 so the user can perform manual UI coreg/QC later.
  This staging does not run or approve UI coregistration.
- Regression coverage should assert that the Synb0 path copies the corrected
  mean b0 to the Lead-DBS coregistration target and writes sidecar fields that
  mark it as coregistration-only and excluded from normalization.
- Staging fix verification passed with
  `test_fake_b0_coreg_target_staging_static.m`,
  `test_process_imported_dwi_acq_labeled_gz_stage.m`, and
  `test_synb0_archive_idempotent_reuse_static.m`.
- Backfill required for subjects that finished before the staging fix:
  `Meige001`, `Meige002`, `Meige003`, and `Meige008` currently have corrected
  b0 sidecars but are missing the Lead-DBS UI target NIfTI. `Meige021` already
  has the target. Copy-only backfill must not overwrite existing targets.
- Copy-only backfill completed for `Meige001`, `Meige002`, `Meige003`, and
  `Meige008`; all pilot/completed subjects checked so far have the UI target
  NIfTI plus JSON sidecar with `FakeCoregisterVolume=true`,
  `ExcludeFromNormalization=true`, and `IntendedUse=coregistration_qc_only`.
- `Meige004` finished from a MATLAB process that had started before the staging
  fix, so it also requires copy-only backfill of the UI target NIfTI.
- Copy-only backfill completed for `Meige004`; it now has the UI target NIfTI
  and JSON sidecar.
- Final 22-subject processing record written to
  `/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_status_final_20260706_213641.csv`.
- Final verification record written to
  `/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_verification_final_20260706_213641.json`.
  It verifies 22/22 subjects with `status=pending_ui_coregistration`,
  `synb0_status=ok`, `eddy_status=ok`, `PhaseEncodingVector=0 1 0`, required
  corrected DWI/bval/bvec/b0 outputs, UI pseudo-B0 NIfTI/JSON targets, and
  JSON flags `FakeCoregisterVolume=true`, `ExcludeFromNormalization=true`, and
  `IntendedUse=coregistration_qc_only`.
- Final audit passed: the five focused MATLAB regression tests passed, and a
  normalization tree search found zero DWI/B0 files under
  `/Volumes/VAL/meige/derivatives/leaddbs/sub-*/normalization`.
- Manual normalization attempt for `Meige008` reached EasyReg completion but
  failed while converting EasyReg's FreeSurfer-format backward field to ITK h5:
  `load_nii` rejected the generated `*_fs_inv_field.nii` because its affine
  matrix contains non-orthogonal rotation/shearing. This is a transform-field
  conversion issue, not a pseudo-B0 inclusion issue; the converter should read
  EasyReg warp fields with an untouch NIfTI loader and keep geometry handling
  through `ea_get_affine`/`ea_fslhd`.
- EasyReg converter fix verification passed with
  `test_easyreg_warp_field_untouch_loader_static.m`, and the existing
  `Meige008` EasyReg inverse field loaded successfully with `load_untouch_nii`
  as a `218 x 262 x 165 x 3` transform field.
- Follow-up normalization attempt showed that `load_untouch_nii` preserves the
  integer storage class of EasyReg fields. The converter must cast field values
  to `double` before subtracting double-precision voxel mm coordinates.

## Goal

Process the Meige cohort DWI images under `/Volumes/VAL/meige` with the same
project-agnostic DWI workflow used for STN/SNr:

1. stage raw BIDS DWI files into the Lead-DBS derivative tree;
2. run Synb0-DISCO, topup, and eddy distortion correction;
3. write corrected DWI and corrected mean b0 derivatives;
4. expose the corrected mean b0 as the Lead-DBS pseudo `B0` image;
5. prepare the pseudo `B0` image and metadata for later user-performed
   Lead-DBS Coregister Volumes UI alignment and manual QC.

The workflow must preserve rawdata provenance and must not write DWI-derived
images into the normalization input set.

## Cohort

Study root:

```text
/Volumes/VAL/meige
```

Subjects:

```text
Meige001-Meige021
Dys022
```

Current raw DWI pattern:

```text
/Volumes/VAL/meige/rawdata/sub-<ID>/ses-preop/dwi/sub-<ID>_ses-preop_acq-ax_dwi.nii.gz
/Volumes/VAL/meige/rawdata/sub-<ID>/ses-preop/dwi/sub-<ID>_ses-preop_acq-ax_dwi.json
/Volumes/VAL/meige/rawdata/sub-<ID>/ses-preop/dwi/sub-<ID>_ses-preop_acq-ax_dwi.bval
/Volumes/VAL/meige/rawdata/sub-<ID>/ses-preop/dwi/sub-<ID>_ses-preop_acq-ax_dwi.bvec
```

All checked subjects have a 33-volume DWI series, 33 bval entries, 33 bvec
columns, and one b0 volume.

## Parameter Decision

Use a single phase-encoding vector policy for the cohort:

```matlab
'PhaseEncodingVector', [0 1 0]
'DefaultTotalReadoutTime', 0.05
```

UIH subjects have DICOM/BIDS metadata that provide:

```text
PhaseEncodingDirection = j
TotalReadoutTime = 0.046215
EffectiveEchoSpacing = 0.000395
```

For these subjects, the pipeline should read `TotalReadoutTime` from the raw
DWI JSON rather than using the default.

Philips subjects (`Dys022`, `Meige008`, `Meige009`, `Meige021`) have DICOM
metadata that confirm the phase-encoding axis:

```text
InPlanePhaseEncodingDirectionDICOM = COL
PhaseEncodingAxis = j
```

Their exported DICOM and BIDS JSON do not provide `PhaseEncodingDirection`
sign, `TotalReadoutTime`, `EffectiveEchoSpacing`, WaterFatShift, or EPIFactor.
The accepted project decision is therefore to use positive j-axis encoding
(`[0 1 0]`) and `DefaultTotalReadoutTime = 0.05` for these subjects.

## Required Code Adaptation

The current project-agnostic DWI job spec builder expects raw DWI basenames like:

```text
sub-<ID>_ses-preop_dwi
```

Meige rawdata uses:

```text
sub-<ID>_ses-preop_acq-ax_dwi
```

Before running preprocessing, update `mh_fiber_dwi_bids_jobspec` so it can
resolve the raw DWI four-file set by discovering the unique
`*_dwi.nii.gz` or `*_dwi.nii` file in
`rawdata/sub-<ID>/ses-preop/dwi/`, then deriving the matching JSON, bval, and
bvec paths from that source basename.

The formal corrected outputs should remain acq-label-free and compatible with
the existing Lead-DBS pseudo-B0 workflow:

```text
derivatives/leaddbs/sub-<ID>/preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_dwi.nii
derivatives/leaddbs/sub-<ID>/preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_dwi.bval
derivatives/leaddbs/sub-<ID>/preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_dwi.bvec
derivatives/leaddbs/sub-<ID>/preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_b0.nii
derivatives/leaddbs/sub-<ID>/preprocessing/dwi/sub-<ID>_ses-preop_desc-preproc_b0.json
derivatives/leaddbs/sub-<ID>/coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.nii
derivatives/leaddbs/sub-<ID>/coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.json
```

## Execution Parameters

Use the Lead-DBS Conda environment for command-line MATLAB execution:

```text
leaddbs
```

Core runner parameters:

```matlab
'StudyRoot', '/Volumes/VAL/meige'
'RepoDir', '/Users/mojackhu/Github/leaddbs'
'DistortionCorrection', 'synb0'
'RunCoregistration', false
'CoregistrationTag', 'dwi_synb0_fakeb0'
'AnchorModality', 'T2w'
'AllowT1Fallback', false
'FreeSurferLicense', '/Applications/freesurfer/8.2.0/license.txt'
'PhaseEncodingVector', [0 1 0]
'DefaultTotalReadoutTime', 0.05
'Synb0MinDockerMemoryGB', 12
'MaxConcurrentSynb0', 1
'Force', false
```

Use a local Synb0 work root if Docker mount behavior on `/Volumes/VAL` is slow
or unstable:

```text
/Users/mojackhu/Library/Caches/leaddbs/meige_synb0_work
```

Because local `/Users` disk space is limited, keep Synb0 concurrency low and
clean completed temporary work directories after outputs are verified and
archived.

## Proposed Implementation Order

1. Write/update this goal document before code changes.
2. Add a focused test that constructs a Meige-style raw DWI directory with
   `sub-<ID>_ses-preop_acq-ax_dwi.*` and verifies that the BIDS job spec resolves
   the four-file set.
3. Update `mh_fiber_dwi_bids_jobspec` to discover the raw DWI source basename.
4. Add a Meige project wrapper under `my_helper/stnvop/` or another approved
   project folder. The wrapper should pass explicit subject IDs and the parameter
   policy recorded above.
5. Run a pilot set before cohort execution:
   - `Meige001`: UIH group with complete readout metadata.
   - `Meige008`: Philips 24-slice group with missing readout metadata.
   - `Meige021`: Philips 60-slice group with missing readout metadata.
6. Review pilot QC outputs before running all 22 subjects.
7. Run the full cohort serially or with `MaxConcurrentSynb0 = 1`.
8. Record final preprocessing status, failures, and reruns in a Meige
   processing record.
9. Leave Lead-DBS Coregister Volumes UI alignment and manual accept/reject QC
   to the user as a follow-up step outside this automated goal.

## Pilot QC Criteria

For each pilot subject, inspect:

1. distorted b0 versus corrected b0 overlay;
2. corrected b0 brain outline and ventricular geometry;
3. corrected b0 agreement with anchorNative T1w/T2w at the brain outline,
   ventricles, basal ganglia, midbrain, and brainstem;
4. DWI volume count, bval count, and rotated bvec count;
5. pseudo-B0 metadata fields:
   - `FakeCoregisterVolume = true`
   - `ExcludeFromNormalization = true`

The corrected b0 must not look more distorted than the source b0. If a Philips
pilot shows a clear polarity failure, rerun that pilot with `[0 -1 0]` before
cohort execution.

## Expected Batch Status

Successful automated preprocessing should report:

```text
status = pending_ui_coregistration
coregistration_status = pending_ui
synb0_status = ok
eddy_status = ok
```

The expected pseudo-B0 target prepared for later manual UI coregistration is:

```text
derivatives/leaddbs/sub-<ID>/coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.nii
```

## Final Processing Record

Status sources:

```text
/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_status_pilot_20260706_142338.csv
/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_synb0_fakeb0_subject_status_20260706_142338/
```

Final merged records:

```text
/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_status_final_20260706_213641.csv
/Volumes/VAL/meige/derivatives/leaddbs/import_logs/dwi_registration_synb0_fakeb0_verification_final_20260706_213641.json
```

Verified final counts:

```text
subjects = 22
status = pending_ui_coregistration: 22
synb0_status = ok: 22
eddy_status = ok: 22
phase_encoding_vector = 0 1 0: 22
total_readout_time_source = json: 18, default: 4
low_resolution_warning = false: 12, true: 10
all_required_outputs_ok = true
normalization_dwi_or_b0_files = 0
```

Subjects using the default readout fallback are the Philips group:
`Dys022`, `Meige008`, `Meige009`, and `Meige021`.

Lead-DBS UI B0-to-anchorNative coregistration and approve/reject QC remain
manual user follow-up steps. The automated goal only prepares the UI target
files and metadata.

## Risks

The highest-risk parameter is the Philips phase-encoding sign. Current DICOM
metadata confirm the axis (`j`) but not the sign. The project decision is to use
positive j-axis encoding; therefore pilot QC is mandatory before full-cohort
acceptance.

The readout-time fallback (`0.05`) affects correction magnitude. If the value is
too high, correction can be excessive; if too low, susceptibility distortion can
remain. This risk is lower than a phase-encoding sign error but should still be
reviewed in the pilot overlays.

The Meige raw DWI basename includes `acq-ax`. Running the existing job spec
without adaptation will fail to find raw DWI inputs.

## Completion Criteria

The goal is complete when:

1. the raw DWI basename adaptation is implemented and tested;
2. pilot subjects pass QC under the accepted parameter policy;
3. all included subjects have corrected DWI, corrected b0, b0 metadata, and
   status rows;
4. pseudo-B0 targets are prepared for later user-performed Lead-DBS UI
   coregistration;
5. no pseudo-B0 image is included in normalization inputs or outputs;
6. a final Meige processing record documents subject-level preprocessing
   status and reruns.
