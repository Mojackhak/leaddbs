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
- Not yet complete: Synb0/eddy pilot runs, full-cohort preprocessing,
  Lead-DBS UI coregistration QC, and final subject-level processing record.

## Goal

Process the Meige cohort DWI images under `/Volumes/VAL/meige` with the same
project-agnostic DWI workflow used for STN/SNr:

1. stage raw BIDS DWI files into the Lead-DBS derivative tree;
2. run Synb0-DISCO, topup, and eddy distortion correction;
3. write corrected DWI and corrected mean b0 derivatives;
4. expose the corrected mean b0 as the Lead-DBS pseudo `B0` image;
5. complete b0-to-anchorNative anatomical alignment through the Lead-DBS
   Coregister Volumes UI with manual QC.

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
8. Use the Lead-DBS Coregister Volumes UI to align pseudo `B0` to the
   anchorNative anatomy, then manually accept or reject each subject.
9. Record final status, failures, reruns, and accepted UI coregistration method
   in a Meige processing record.

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

Before UI coregistration, successful subjects should report:

```text
status = pending_ui_coregistration
coregistration_status = pending_ui
synb0_status = ok
eddy_status = ok
```

After UI coregistration, the expected pseudo-B0 target is:

```text
derivatives/leaddbs/sub-<ID>/coregistration/anat/sub-<ID>_ses-preop_space-anchorNative_desc-preproc_B0.nii
```

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
4. all accepted pseudo-B0 images have Lead-DBS UI coregistration outputs;
5. no pseudo-B0 image is included in normalization inputs or outputs;
6. a final Meige processing record documents subject-level status, reruns, and
   accepted coregistration decisions.
