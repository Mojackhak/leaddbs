# Import DWI DICOM into BIDS Raw Data

## Purpose

Use `mh_fiber_convert_dicom_dwi_to_leaddbs` to convert one DWI DICOM series
directory into a BIDS-compatible DWI four-file set:

```text
<OutputBase>.nii.gz
<OutputBase>.json
<OutputBase>.bval
<OutputBase>.bvec
```

The converter runs `dcm2niix`, identifies a complete DWI candidate, verifies
that the NIfTI volume count matches the b-value and b-vector counts, and
requires at least one b0 volume with `bval < 10`. It also writes a conversion
QC record:

```text
<OutputBase>_dicom_conversion_qc.json
```

This operation only imports raw DWI data. It does not run Synb0-DISCO, topup,
eddy, Lead-DBS coregistration, or normalization.

## Runtime Setup

Use MATLAB with the Lead-DBS repository on the MATLAB path. The default runtime
environment for this repository is the Conda environment `leaddbs`.

```matlab
cd('leaddbs_repo_path');
addpath(genpath(pwd));
```

The converter resolves `dcm2niix` in this order:

1. the executable bundled with Lead-DBS;
2. the supported Slicer installation path;
3. `dcm2niix` available on `PATH`.

## Single-subject Example

### Existing destination

The destination currently contains:

```text
sub-subjectID_ses-preop_acq-ax_dwi.nii.gz
sub-subjectID_ses-preop_acq-ax_dwi.json
sub-subjectID_ses-preop_acq-ax_dwi.bval
sub-subjectID_ses-preop_acq-ax_dwi.bvec
```

Run a dry run first. This executes conversion and validation in a temporary
working directory but does not write into the destination directory:

```matlab
cd('leaddbs_repo_path');
addpath(genpath(pwd));

result = mh_fiber_convert_dicom_dwi_to_leaddbs( ...
    'DicomDir', 'dwi_dicom_source_path', ...
    'OutputDir', 'dwi_outputDir_path', ...
    'OutputBase', 'sub-subjectID_ses-preop_acq-ax_dwi', ...
    'RepoDir', pwd, ...
    'DryRun', true);

disp(result);
```

Expected dry-run statuses are:

- `dry_run_direct_dwi`: `dcm2niix` produced a normal multi-slice 4D DWI.
- `dry_run_mosaic_reconstruction`: the converted data require tiled mosaic
  reconstruction.

### First import into an empty destination

Use `Force=false` for a new import. The command stops instead of overwriting an
existing NIfTI, JSON, bval, bvec, or conversion QC file.

```matlab
result = mh_fiber_convert_dicom_dwi_to_leaddbs( ...
    'DicomDir', 'dwi_dicom_source_path', ...
    'OutputDir', 'dwi_outputDir_path', ...
    'OutputBase', 'sub-subjectID_ses-preop_acq-ax_dwi', ...
    'RepoDir', 'leaddbs_repo_path', ...
    'Force', false);

disp(result);
```

Successful statuses are:

- `converted_direct_dwi`: the normal multi-slice DWI was copied to the final
  BIDS names.
- `converted_mosaic_reconstructed`: a single-slice tiled mosaic was
  reconstructed and written as a normal 4D DWI.

## Parameters

### `DicomDir`

Required. Directory containing the source DWI DICOM files. The directory must
exist. It should contain one acquisition that can produce a complete DWI set.

```matlab
'DicomDir', '/path/to/dwi_dicoms'
```

### `OutputDir`

Required. Destination BIDS DWI directory. For a standard preoperative BIDS
subject, use:

```text
<study_root>/rawdata/sub-<ID>/ses-preop/dwi
```

The directory is created during a formal import if it does not exist. A dry run
does not create it.

### `OutputBase`

Required. Filename stem without an extension. Use a BIDS DWI name ending in
`_dwi`, for example:

```matlab
'OutputBase', 'sub-subjectID_ses-preop_acq-ax_dwi'
```

The same stem is used for the NIfTI, JSON, bval, bvec, and QC files.

### `RepoDir`

Optional. Lead-DBS repository root used to locate the bundled `dcm2niix`.
Normally set it explicitly or use `pwd` after changing to the repository root.
If omitted, the function attempts to resolve the repository from its own file
location.

Default: empty, with automatic repository discovery.

### `WorkDir`

Optional. Directory used for intermediate `dcm2niix` output.

- When empty, the converter creates an automatically cleaned temporary
  directory.
- When specified, intermediate files remain available for inspection.
- Do not point this parameter at raw data, derivatives, or any directory that
  contains files that must be preserved.
- If a specified `WorkDir` already exists and `Force=true`, the current
  implementation removes that entire directory before conversion.

Default: empty.

### `ReferenceNifti`

Optional. Same-protocol reference NIfTI used only when the converted DWI is a
single-slice tiled mosaic and its geometry cannot be derived reliably from the
DICOM metadata. The reference supplies tile dimensions and slice count. DICOM
geometry remains preferred.

Default: empty.

### `TileOrder`

Optional. Tile traversal order used only for mosaic reconstruction.

Supported values:

- `row_major_right_to_left`: default; read each tile row from right to left.
- `row_major_left_to_right`: read each tile row from left to right.

This option does not affect normal multi-slice DWI conversion. Review mosaic
orientation before downstream preprocessing if a non-default value is needed.

### `Parallel`

Optional logical flag controlling parallel reconstruction of mosaic volumes.
It does not parallelize normal direct conversion.

Default: `false`.

### `ParallelWorkers`

Optional positive scalar specifying the maximum worker count for mosaic volume
reconstruction when `Parallel=true`. The value is rounded to an integer and
clamped to at least one.

Default: `4`.

### `Force`

Optional logical flag controlling replacement of existing output files.

- `false`: stop with `OutputExists` if any final output already exists.
- `true`: allow final output replacement. When a custom existing `WorkDir` is
  also supplied, that working directory is removed before conversion.

Default: `false`.

Do not use `Force=true` for a subject with existing preprocessing or
coregistration results unless the downstream DWI-derived results will also be
invalidated and regenerated. Preserve existing raw files before replacement.

### `DryRun`

Optional logical flag for conversion preflight.

- `true`: run `dcm2niix`, select and validate the DWI candidate, determine
  whether mosaic reconstruction is required, and write nothing to `OutputDir`.
- `false`: perform the formal import and write the final files.

Default: `false`.

`DryRun=true` is computational work, not a syntax-only check. It writes only to
the temporary or explicitly selected `WorkDir`.

## Reusable Template

```matlab
repoDir = 'leaddbs_repo_path';
dicomDir = 'dwi_dicom_source_path';
outputDir = 'dwi_outputDir_path';
outputBase = 'sub-subjectID_ses-preop_acq-ax_dwi';

cd(repoDir);
addpath(genpath(repoDir));

result = mh_fiber_convert_dicom_dwi_to_leaddbs( ...
    'DicomDir', dicomDir, ...
    'OutputDir', outputDir, ...
    'OutputBase', outputBase, ...
    'RepoDir', repoDir, ...
    'WorkDir', '', ...
    'ReferenceNifti', '', ...
    'TileOrder', 'row_major_right_to_left', ...
    'Parallel', false, ...
    'ParallelWorkers', 4, ...
    'Force', false, ...
    'DryRun', true);

disp(result);
```

After reviewing the dry-run result, set `DryRun=false` for a new destination.
Keep `Force=false` unless replacement has been explicitly planned.

## Result Fields to Review

Review at least these fields after every run:

- `Status`: dry-run or conversion outcome.
- `Decision`: `direct_dwi` or `mosaic_reconstruction`.
- `Dcm2niixPath` and `Dcm2niixSource`: executable used for conversion.
- `Dcm2niixStatus`: process exit status; zero indicates success.
- `ConvertedImageSize`: image dimensions produced by `dcm2niix`.
- `ConvertedVolumeCount`: number of DWI volumes.
- `OutputImageSize`: expected or written final dimensions.
- `OutputNifti`, `OutputJson`, `OutputBval`, and `OutputBvec`: final paths.
- `QcJson`: formal conversion QC path.

## Existing Data and Re-imports

If the four-file set already exists, a normal command with `Force=false` stops
before conversion. This is the safe behavior.

Before a planned re-import:

1. preserve the existing NIfTI, JSON, bval, bvec, and conversion QC files;
2. identify DWI-derived files under `derivatives/leaddbs/sub-<ID>`;
3. treat preprocessing, corrected DWI, B0, DWI coregistration, and dependent QC
   as stale after raw DWI replacement;
4. rerun the required downstream workflow from the new raw DWI;
5. verify image geometry, gradient count, b0 presence, and coregistration.

When the destination is already populated and Lead-DBS derivatives exist, do
not run the formal import with `Force=true` without first planning preservation
and downstream regeneration.
