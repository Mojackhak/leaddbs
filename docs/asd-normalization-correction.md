# ASD T1-to-D99 normalization correction

## Authorized repair

Correct normalization for sub-008, sub-010seeg, and subsequently sub-091 after
its prior preset completed. Their retained bootstrap and linear images show
anatomical mismatch, so deep-only adjustment cannot resolve the demonstrated
failure. Preserve source images, native MRI anchors, postoperative coregistration
images/matrices, other subjects, and any active unrelated registration. Do not
change global normalization defaults, software versions, or unrelated code.

## Staged procedure

1. Inspect source T1 and D99 anatomy and construct a bounded anatomically
   oriented rigid initialization. Test only starts justified by the observed
   acquisition orientation. Estimate the initial rigid/affine alignment outside
   subject output folders and review it before nonlinear fitting.
2. Prepare and visually inspect a native operational brain mask using source
   anatomy and the corrected initial alignment. Do not reuse the native mask
   projected from the failed bootstrap or describe a projected mask as
   independent segmentation ground truth.
3. Reuse the existing D99 fixed brain mask and deep mask because their consumed
   template/atlas inputs are unchanged. Use the existing
   `ea_ants_d99_deep_run` prepared-mask interface for rigid/affine, whole-brain
   SyN, and deep refinement. If preorientation is represented by a temporary
   image-header rigid transform, preserve voxel intensities and explicitly
   compose that transform back to the original anchor coordinates in both
   final displacement fields. The public native anchor header is unchanged.
4. Apply the verified final maps to current preoperative and postoperative
   images. Generate native Lead-DBS check images and target-region overlays.
   Stage everything before replacing the formal normalization outputs.

## Verification and publication

Compare corrected and prior images across sagittal, coronal, and axial planes,
including ventricles, callosal/brainstem structures, NAc/ALIC, GPi/GPe, HIP/AMY,
and mPFC. Use common-mask similarity as supporting evidence. Check map direction
by independent resampling, inverse round trips, finite fields/output grids, and
sampled Jacobians. Image fit and atlas-derived masks do not establish small-
nucleus localization ground truth.

Before replacing or retiring any existing untracked file, move it to a
recoverable macOS Trash directory and record exact restore paths. Replace only
normalization fields/images/check images and method/procedure records. Preserve
history in the shared methods text, retain the recognized ANTs method label,
and keep normalization approval 0. Save actual commands, masks, initialization,
composition, validation, and before/after figures with the corrected results.

## Dependency boundary

Correcting the initial T1-to-template transform affects the bootstrap-derived
native mask, affine/linear alignment, whole-brain and deep transforms, and their
normalized-image derivatives. Fixed template masks and source inputs remain
valid. Retire only the superseded failed native-mask/registration branch after
successful publication; keep its recoverable original. Do not rerun CT/MRI
coregistration or invalidate unrelated atlas, subject, or pipeline caches.
Existing brain-shift, reconstruction, or WarpDrive results must be checked for
actual dependencies before publication; none of these targets had brain-shift or reconstruction
outputs when its repair began. No raw file hash is used as a rerun switch.

## Initial mask-constrained alignment

The first anatomical starts correct the major orientation difference but still
show incomplete intracranial alignment when the moving head is unmasked. Use
coarse, source-anatomy ellipsoids covering the cerebrum, cerebellum, and brainstem
as operational moving masks for the initial rigid/affine fit. Their purpose is
to exclude the observed scalp/orbital interference, not to claim a precise brain
segmentation. Review the mask and fitted brain coverage before the SyN stages.

## Estimation-intensity preparation

Windowed source inspection shows marked dorsal-to-ventral intensity variation,
particularly in sub-010seeg. The initial whole-head intensity range also gives
substantial weight to bright extracranial tissue. Prepare a working-image-only
N4 bias correction inside the anatomical mask, clip its intracranial 1st-99th
percentiles. The coarse initial fit zeros voxels outside its operational mask;
the final working image retains intensities and uses the inspected projected
whole-brain moving mask to restrict transform estimation. The
original MRI voxels and header remain unchanged; final formal images are
resampled from original intensities. Record the working-image preparation and
verify both raw and corrected-intensity anatomy when selecting the transform.

## Whole-brain support check

The separately installed `t1_brainmask.nii` differs substantially from the
preset's retained filled positive-support brain mask. Initial-fit projections
from the smaller mask under-cover source posterior/frontal tissue. Retain the
preset fixed mask and deep mask for the final candidate, and use the retained
whole-brain fixed mask for an additional bounded correlation-based initial
alignment on N4 working intensities. Verify projected source coverage before
nonlinear fitting. This corrects a demonstrated mask-domain issue rather than
adding a general fallback or changing the preset globally.

## Coordinate composition

Let H map original native RAS points to the temporary preoriented image frame.
It is derived from the actual saved working-image affine relative to the
unchanged native affine. For a D99 point x and the staged image-resampling map
f(x), publish H^-1 f(x) as the D99-to-original-native pull map. For an original
native point y and staged inverse map g, publish g(Hy). Convert ITK vector
components between LPS and RAS explicitly and save the inverse on the original
native grid. No nonlinear field interpolation is needed for this header-only
preorientation because the original and preoriented images share voxel indices.

Verify the composed forward map by comparing original-image resampling through
it with resampling the same original intensities under the temporary oriented
header through the staged field. Check inverse round trips on original native
coordinates. Final preoperative/postoperative images retain original source
intensities; N4 working-image results are estimation/QA evidence only.

## Completed correction

Published the corrected forward/inverse fields, original-intensity normalized
preoperative/postoperative images, checkreg figures, and method/command history
for sub-008 and sub-010seeg. The latter also has a regenerated normalized CT
tonemap. Native coregistration images, matrices, and source headers are unchanged.
Those two publications did not change other subjects or the shared
registration implementation.

| Focused check | sub-008 | sub-010seeg |
| --- | --- | --- |
| Original-intensity whole-brain Pearson, prior to corrected | 0.385 to 0.852 | 0.167 to 0.430 |
| Original-intensity whole-brain NMI, prior to corrected | 1.025 to 1.137 | 1.021 to 1.044 |
| Inverse round-trip error, 95th percentile | 0.068 mm | 0.040 mm |
| Nonpositive sampled Jacobians at 0.75 mm | 0 | 0 |
| Sampled source-FOV coverage of all seven target groups | 100% | 100% |

Both cases passed independent preoperative/postoperative interpolation checks,
finite field/grid checks, and anatomical review of the original-intensity and
working-image overlays. The 010seeg original MRI retains intensity nonuniformity;
correlation alone is not an anatomical accuracy measure. Nucleus boundary
accuracy is limited by source image contrast/resolution and is not independently
established by atlas overlays. Normalization approval remains 0 for review.

The durable correction records, masks, actual commands, verification results,
and figures are under
`/Users/mojackhu/Desktop/asd/derivatives/leaddbs/normalization_qc/correction`.
`publication-receipt.json` records 9 and 10 published files respectively and
unchanged native coregistration. `restore-manifest.json` maps prior formal files
and the retired failed registration branch to
`/Users/mojackhu/.Trash/leaddbs-asd-normalization-correction`.
Fixed/deep template masks, source input caches, and historical publication
folders remain in place. Only normalization dependencies were recomputed; there
is no new broad validation/invalidation or change to global defaults.

## Extension to sub-091

The user subsequently authorized the same normalization repair for sub-091.
Its completed preset records and published check image show a persistent gross
MRI-to-template mismatch. Confirm no active sub-091 registration remains before
starting its isolated candidate. Inspect its own source anatomy, initialization,
and mask; do not transfer another subject's transform or anatomical coordinates.
Use the retained full-brain fixed mask in both the subject-specific MI64 seed
fit and the subsequent GC affine fit. Source-anatomy operational masks and N4
working intensities serve estimation only; final images retain source intensity.
Reuse the inspected fixed/deep masks and the existing prepared-mask pipeline,
coordinate composition, focused checks, and recoverable publication procedure.
Keep native postoperative coregistration, sub-008/sub-010seeg corrected results,
and all other subjects unchanged. Retain sub-091-specific inventories, commands,
figures, restore manifest, and publication receipt under its correction folder.

## Completed sub-091 correction

Published the sub-091 correction after the same focused anatomical and numerical
checks. Correcting its own initialization and operational moving mask required
new linear, whole-brain SyN and deep transforms and their normalized MRI/CT
outputs. The original native anchor header and postoperative coregistration
images/matrices are unchanged. No global preset, atlas, or other subject was
modified.

The original-intensity whole-brain Pearson increased from 0.216 to 0.532 and
NMI from 1.016 to 1.045 under the same retained full-brain fixed mask. The
inverse round-trip error at the 95th percentile was 0.038 mm. There were no
nonpositive sampled Jacobians at 0.75 mm, and sampled source-FOV coverage was
100% for NAc, ALIC, GPi, GPe, HIP, AMY and mPFC. Independent MRI/CT interpolation,
finite-field/grid checks, final CT tonemapping, and anatomical overlays passed.
Original intensity nonuniformity remains in the formal MRI; it was not replaced
with an N4 intensity derivative. Approval remains 0 for manual review.

Subject-specific records and figures are under
`/Users/mojackhu/Desktop/asd/derivatives/leaddbs/normalization_qc/correction/sub-091`.
Its `publication-receipt.json` records 10 published files. Its own
`restore-manifest.json` maps prior formal outputs and the retired failed cache
branch to `/Users/mojackhu/.Trash/leaddbs-asd-normalization-correction-sub-091`.
The earlier two-subject correction records remain unchanged. Only the affected
normalization branch was recomputed; there is no new broad validation or
invalidation behavior.
