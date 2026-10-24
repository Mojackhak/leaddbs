# SEEG CT-to-MRI coregistration repair

## Scope and diagnosis

Repair only postoperative CT coregistration for `sub-010seeg` and
`sub-092seeg` in `/Users/mojackhu/Desktop/asd/derivatives/leaddbs`.

The existing ANTs/BRAINSFit runs completed but produced anatomically incorrect
CT-to-MRI overlays. A completed optimizer is not an anatomical acceptance test.
The source headers have consistent qform/sform orientation; no source-header
repair was required.

The main demonstrated problem is initialization across different acquisition
orientations and fields of view. `sub-010seeg` requires a near-half-turn
three-dimensional rotation in addition to pitch; starts varying pitch alone
remain incorrect. `sub-092seeg` requires a substantial pitch rotation. CT also
includes more face/neck than MRI, so aligning image geometry centers does not
align brain anatomy. CT scanner z coordinates are several hundred millimeters
from the MRI coordinates; this offset requires translation initialization and
is not by itself evidence of a corrupt header.

The default `ext_libs/ANTs/ea_ants_linear.m` first initializes from intensity
moments, enables histogram matching, and estimates rigid followed by affine
transforms. These CTs contain negative air (-1024) and metal above 40000.
Intensity moments are therefore a poor anatomical center proxy. The old ANTs
linear blocks have singular values 0.865-1.146 for `sub-010seeg` and 0.871-1.089
for `sub-092seeg`: affine scale/shear compensated for an incorrect fit. The
contribution of histogram matching versus clipping was not separately isolated.

The original `sub-092seeg` MRI has 1 x 1 x 0.5 mm acquired voxels and limited
coverage. Its existing 0.7 mm derivative does not add acquired spatial detail.
No normalization/template change is needed to repair CT-to-anchor coregistration.

## Selected procedure

Use `/opt/anaconda3/envs/leaddbs/bin/python`, bundled Apple Silicon ANTs, and
existing Lead-DBS MATLAB functions. Preserve the MRI anchor and original CT.
Prepare a registration-only CT by sampling every third voxel, clipping to
[-200,1000], and shifting intensities to [0,1200]. Estimate a rigid transform
with mutual information, without histogram matching or an affine stage:

- MI: 32 bins, regular sampling at 0.5; random seed 1; four ITK threads.
- Iterations: 500 x 300 x 200 x 100; convergence 1e-7 over 15 iterations.
- Shrink factors: 8 x 4 x 2 x 1; smoothing: 2 x 1 x 0.5 x 0 mm.
- `sub-010seeg`: initialize at visually located globe centers; compare a finite
  pitch range together with a proper 180-degree RAS z rotation. Refine the
  selected -55-degree pitch start. The result has RAS XYZ Euler angles about
  (31.20, 2.16, -162.90) degrees.
- `sub-092seeg`: initialize a rigid transform from bilateral globe centers and
  a posterior skull point, then refine. The result has RAS XYZ Euler angles
  about (-57.45, -9.78, -6.27) degrees.

Euler angles describe coordinate transformations, not independent anatomical
head-position measurements. The `sub-010seeg` operation is a proper 3D rotation,
not a reflection or a change to source-image headers. Both selected refinements
use whole-image MI; a trial brain-region mask was not needed in the final fit.

Apply the selected transform once to the original full-resolution preprocessed
CT using linear interpolation and -1024 outside the CT field of view. Create the
inverse transform with `antsApplyTransforms`. Convert both matrices with
`ea_antsmat2mat`, tone-map with `ea_tonemapct`, and refresh check images with
`ea_gencheckregpair`. Keep the recognized ANTs method identifier and CT approval
= 0 for user review. Record the actual custom rigid settings separately so the
method identifier cannot be mistaken for the default rigid-plus-affine recipe.

## Publication and recovery

All replaced, untracked subject files must first be moved to
`/Users/mojackhu/.Trash/leaddbs-seeg-coregistration`, preserving subject-relative
paths. Preserve obsolete alternative CT transforms there as well, because they
no longer describe the current registered CT. Record exact restore paths.

Publish only CT coregistration images, four ANTs matrix files per subject, CT
method/procedure logs, and CT check images. Preserve and extend the historical
methods text rather than erasing previous run descriptions. Store the selected
registration inputs, initialization, command, execution log, multiplane overlays,
verification, and restore manifest under
`/Users/mojackhu/Desktop/asd/derivatives/leaddbs/coregistration_qc`.

## Focused verification

- Inspect nine sagittal/coronal/axial slices per subject and the native Lead-DBS
  check images. The repaired skull, orbits, and brain boundaries agree across
  planes. This does not establish millimeter electrode-localization accuracy.
- Verify rigid orthogonality, determinant +1, and forward/inverse agreement;
  all selected linear singular values are within 1e-6 of 1.
- Verify `ea_antsmat2mat` conversion and CT-to-MRI direction. Independently
  reproduce linear interpolation from the original CT at 17761 points for
  `sub-010seeg` and 3924 points for `sub-092seeg`. The 99th-percentile intensity
  differences are 0.011 and 0.030, respectively.
- Verify output dimensions and affine against each existing MRI anchor.
- On a common dense MRI-foreground sample, normalized MI improves from 1.0093
  to 1.0208 and from 1.0036 to 1.0154, respectively. This is supporting fit
  evidence only; competing wrong basins motivated the anatomical checks.
- Inventory source/retained files by size and modification time before
  publication, verify exact replacement scope and recoverable originals, and
  check CT approval remains 0. No whole-file hashes are introduced.

## Dependency and execution boundary

CT intensity preparation, initialization, and optimization settings affect only
the CT transform and CT resampling/check-image derivatives. CT normalization,
brain-shift correction, or electrode coordinates would depend on that transform
if they existed; neither subject currently has those downstream results.
Preoperative MRI normalization does not depend on the CT transform.

Preserve raw data, preprocessing, MRI anchors, UI preferences, other subjects,
software versions, global defaults, and unrelated repository files. No full
pipeline, full test suite, broad validation, global cache invalidation, commits,
or remote operations are required or performed. Trial starts are a finite
subject-specific investigation, not an added global retry/fallback policy.
