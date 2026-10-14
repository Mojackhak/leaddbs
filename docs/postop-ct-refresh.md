# Postoperative CT input refresh

## Approved operation

Prepare `sub-200169` for a new CT coregistration using
`/Volumes/VAL/VALPD/rawdata/sub-200169/ses-postop/anat/sub-200169_ses-postop_CT.nii.gz`.
The subject derivatives directory is
`/Volumes/VAL/VALPD/derivatives/leaddbs/sub-200169`.

Move these existing postoperative CT results to macOS Trash while preserving
their relative paths:

- One CT image under `preprocessing/anat`.
- The CT and tone-mapped CT under `coregistration/anat`.
- Eight CT-to-anchorNative and anchorNative-to-CT transformation files,
  including the old ANTs and BRAINSFit matrices and their 4-by-4 forms.
- The postoperative CT check image under each of `coregistration/checkreg`
  and `normalization/checkreg`.

These are 13 files. Also preserve the original shared coregistration method log
in the same Trash directory before replacing its subject copy. Change only
`approval.CT` from `1` to `0`; preserve all other log values and formatting.

Decompress the new raw CT to
`preprocessing/anat/sub-200169_ses-postop_desc-preproc_CT.nii` without changing
its NIfTI header, voxel values, or spatial geometry. Keep the raw source intact.
Record the exact restore mapping and focused verification outside the patient
directory.

## Invalidation and execution boundaries

The new postoperative CT invalidates only its preprocessing copy, CT
coregistration images and transforms, and CT check images. The CT approval flag
must be reset because Lead-DBS skips approved coregistration results even when
their image files are missing. Existing preprocessing images are otherwise
reused rather than refreshed from raw data.

Preserve preoperative MRI and CT0/CT1 data, their registrations and approval
flags, D99v2 normalization fields and log, WarpDrive files, raw-image mappings,
and UI preferences. Do not run coregistration, normalization, brainshift,
electrode reconstruction, or other processing stages in this operation.

## Focused verification

Check all 13 approved paths before moving them. Preserve a size and modification
time inventory of the remaining subject files. Confirm that the Trash copies
retain their original sizes and times, the old CT results are absent, and the
new preprocessing CT has the same header, voxel values, and affine as the raw
source. Compare the parsed method log against the original with only
`approval.CT = 0`, and verify that all retained files and the raw source are
unchanged. No broad validation, global invalidation, or cache fingerprint
change is required.
