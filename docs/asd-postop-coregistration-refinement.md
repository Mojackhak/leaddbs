# ASD postoperative coregistration refinement

## Authorized scope

Publish the reviewed rigid refinements for `sub-008` and `sub-090` in
`/Users/mojackhu/Desktop/asd/derivatives/leaddbs`. Preserve `sub-091` and the
previously repaired `sub-010seeg` and `sub-092seeg`.

The preceding assessment and selected candidate transforms are stored under
`coregistration_qc/remaining-subject-review`. The user requested optimization
after reviewing the recommendation. Reuse those candidates because their
source image values/geometry and prior active transforms have been rechecked
against the current subject files; do not estimate identical transforms again.

## Intended behavior

- `sub-008`: replace the SPM postoperative MRI-to-anchor registration with the
  reviewed ANTs rigid refinement. The local correction was about 1.22 degrees,
  with a median brain-region displacement of 0.84 mm relative to the old fit.
  Equal-interpolation brain-region normalized mutual information improved from
  1.04223 to 1.04498. These are fit measures and candidate differences, not a
  measurement of electrode localization error.
- `sub-090`: replace the affine CT-to-anchor registration with the reviewed
  rigid refinement. This removes the old 0.9476-1.0171 principal scale factors.
  Equal-interpolation normalized mutual information improved from 1.04976 to
  1.05298. The original CT is 1.367 x 1.5 x 1.367 mm, which limits fine-detail
  interpretation even though the output grid is 0.7 mm.

Both candidates used ANTs Rigid[0.05], masked MI32 with regular sampling 0.5,
seed 1, four ITK threads, no histogram matching, a 4 x 2 x 1 pyramid, and
1 x 0.5 x 0 mm smoothing. The MRI candidate was initialized from the previous
SPM rigid transform. The CT candidate was initialized from the closest proper
rotation to the prior affine, preserving alignment at the MRI center; only its
registration intensities were clipped to [-200,1000] and shifted by 200.

Apply each accepted transform once to the original preprocessed postoperative
image using linear interpolation and the unchanged MRI-anchor grid. Use zero
outside the postoperative MRI and -1024 outside the CT. Preserve original
postoperative voxel intensities in the resampling source. Generate an inverse
ANTs transform, and convert both directions with `ea_antsmat2mat`. Reuse
`ea_tonemapct` for CT display and `ea_gencheckregpair` for native quality checks.

## Preservation and publication

Before replacing an untracked subject file, move its original to
`/Users/mojackhu/.Trash/leaddbs-asd-coregistration-refinement`, retaining the
subject-relative path in a restore manifest. Move obsolete postoperative SPM
matrices for `sub-008` there as well, preserving its separate pre-coregistration
matrix. Replace only postoperative registered images, transform pairs and
4-by-4 matrices, check images, and method/procedure provenance. Preserve the
historical methods text and append the actual rigid procedure.

Use the recognized ANTs method identifier and reset only the changed modality's
approval to 0. Keep native image names and existing data-format/software
versions. Record custom rigid settings separately from the stock ANTs method
label. Keep assessment artifacts unchanged, and save publication checks and
restore paths under `coregistration_qc/postop-refinement`.

## Dependency boundary

Only the changed postoperative image-to-anchor transform, its resampled image,
and its check image are directly invalidated. A normalized postoperative image,
brain-shift correction, or electrode coordinates would depend on that transform
if present. Refresh or retire only those affected derivatives, without deleting
preoperative normalization fields, masks, or cache stages.

The `sub-008` D99 preset estimates normalization from the preoperative T1 anchor
alone (`ea_normalize_ants_d99_deep.m`). Its completed and running estimation
stages do not read the postoperative MRI and remain valid. Check publication
state before writing so a concurrently produced normalized postoperative image
cannot silently retain the old coregistration. Neither subject currently has
published normalization images/fields, brain-shift, or reconstruction outputs.
Do not rerun preoperative normalization or its masks because of a postoperative
coregistration change.

## Focused verification

Verify the selected candidate still matches its reviewed input semantics; output
grid and finite voxel values; rigid orthogonality and determinant +1; paired
forward/inverse matrices and the actual Lead-DBS conversion; and independent
linear resampling samples from the original images. Review multiplane overlays
and native check images after full-intensity resampling. Verify exact subject
replacement/retirement scope, preservation of original and unrelated files, and
recoverability in Trash. Keep the original MRI anchors, preprocessing, raw data,
preferences, other subjects, and preoperative normalization inputs unchanged.

No source-code, global-default, version, cache-fingerprint, commit, remote-state,
full-suite, full-pipeline, or broad invalidation change is required.

## Staging result

The selected transforms were applied to original image intensities and passed
independent resampling checks at 6603 points for `sub-008` and 4760 points for
`sub-090`; the 99th-percentile absolute intensity differences were 0.0046 and
0.0035. Both matrices have unit principal scales within 1e-6, and the actual
Lead-DBS forward/inverse conversion checks passed. Nine overlay slices and the
native check image were reviewed for each staged output. The ongoing
`sub-008` normalization remains in its deep estimation stage, with no staged
or formal normalized postoperative image at the publication boundary.

## Recovery after an accidental sub-008 rerun

The user subsequently reran SPM coregistration for `sub-008`, replacing the
registered postoperative MRI, native check image, and active method record and
recreating four SPM matrices. The previously selected ANTs matrix pair and its
4-by-4 forms remain intact. The preprocessed postoperative MRI values/geometry
and the preoperative anchor are unchanged, so the reviewed ANTs estimate remains
valid and must not be re-estimated.

Recover only `sub-008`: reapply the intact optimized transform to the original
preprocessed postoperative MRI, restore the active ANTs method, refresh its
check image, and move the recreated SPM matrices to Trash. Preserve the separate
anchor pre-coregistration matrix and all valid ANTs matrices. Preserve the
historical methods text and append a recovery record. Keep modality approval 0.
Do not modify UI preferences or other subjects.

D99 normalization completed before the accidental SPM rerun. Verify its existing
normalized postoperative MRI against a fresh application of the unchanged D99
field to the recovered native MRI using the recorded Linear/double settings.
If parsed geometry and voxel values agree, retain that existing normalized image
and its check image. Otherwise replace only the normalized postoperative image
and its check image. Preserve preoperative normalized images, both nonlinear
fields, normalization approval/log, masks, and all estimation stages.

Before any untracked file is replaced or retired, move it to
`/Users/mojackhu/.Trash/leaddbs-sub-008-coregistration-recovery` and retain exact
restore mappings. Save the recovery verification under
`coregistration_qc/sub-008-recovery`. Review the native overlay, verify transform
and resampling consistency, and confirm retained source/normalization files are
unchanged. This is a local recovery; no pipeline-wide invalidation or rerun is
required.

Recovery verification found that the existing normalized postoperative MRI has
exactly the same parsed geometry and voxel values as applying the retained D99
field to the recovered native MRI (maximum intensity difference 0). Therefore
all normalization images, fields, logs, masks, and check images are retained.
The recovered native MRI also matches the previously verified optimized image
voxel-for-voxel with the same affine.
