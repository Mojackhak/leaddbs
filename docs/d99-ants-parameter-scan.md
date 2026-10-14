# D99 ANTs parameter scan for sub-181101

## Authorized scope and output

Run the user-approved staged comparison for sub-181101. Preserve all existing
Lead-DBS files, preferences, transforms, and reconstruction results. Use the
`leaddbs` Conda environment and the bundled ANTs executable. Store all new
inputs, masks, commands, logs, transforms, measurements, and figures under
`/Volumes/VAL/VALPD/derivatives/ants_d99_sweep/sub-181101`.

The task prioritizes the thalamus, STN, and substantia nigra while retaining
reasonable whole-brain alignment. Results are image-based candidate rankings,
not independently established nucleus-localization accuracy. No independent
native nucleus annotations or anatomical landmarks are currently available.

## Inputs and masks

Copy the current anchor-native axial T1, D99 template, template brain mask,
existing ANTs results, and relevant atlas masks into the isolated output.
Record original paths, file sizes, modification times, geometry, and tools.
Do not estimate normalization from CT, SWI, or the additional T1/T2 images.
T2 and SWI may be resampled later for visual evaluation only.

The current ANTs result is sufficiently interpretable for a provisional native
brain-mask projection. Project the D99 brain mask through a preserved copy of
the existing inverse transform, retain its largest connected component, fill
enclosed holes, and inspect multi-slice overlays before accepting it. This is
an atlas-derived operational mask, not independent segmentation ground truth.
Do not use the failed EasyReg segmentation or transform. Preserve both the
projected mask and the accepted mask with their distinct roles documented.

Build bilateral thalamus, STN, and SN unions from the installed binary atlas
ROIs in physical coordinates. The deep optimization masks are their union
dilated by 2 mm or 4 mm and intersected with the template brain mask. Verify
full inclusion of the source target ROIs. The existing secondstepmask excludes
STN/SN and is not used for this scan.

## Candidate stages

All candidates use seed 1, one ITK thread, double precision, histogram matching
disabled, and unchanged copied images. Image smoothing is specified in mm.
SyN smoothing parameters are variances in voxel space. All convergence
thresholds/windows are 1e-6 and 10, respectively. Images are resampled linearly;
binary masks and labels use nearest-neighbor interpolation.

Stage A has four candidates: geometric-image-center versus binary-brain-mask
center-of-mass initialization, crossed with MI bins 32 versus 64. Each uses
Rigid[0.1] followed by Affine[0.1], Regular sampling 0.25, iterations
1000x500x250x100, shrink 12x8x4x2, and smoothing 1.5x1x0.5x0.25mm. Both brain
masks constrain the metrics. Review the outputs and retain two anatomically
reasonable affines before proceeding.

Stage B runs 32 combinations from each retained affine, for 64 candidates:

- Metric: dense MI32, dense MI64, dense CC radius 2, dense CC radius 4.
- SyN: [0.05,3,0], [0.1,3,0], [0.1,3,1], [0.1,4,2].
- Pyramid: iterations 100x70x50 / shrink 8x4x2 / smoothing 1x0.5x0.25mm;
  or iterations 100x70x50x20 / shrink 8x4x2x1 / smoothing 1x0.5x0.25x0mm.

Review the whole-brain and deep-region results and retain three candidates.
Stage C crosses the 2-mm/4-mm deep masks with SyN[0.05,3,1]/SyN[0.1,3,1] for
each retained candidate, for 12 refinements. It retains the parent's metric,
uses iterations 50x20, shrink 2x1, and smoothing 0.25x0mm. Keep the unrefined
parents in the final comparison. Local metric masks do not freeze deformation
outside those masks, so whole-brain evaluation remains required.

## Evaluation and reporting

Use identical fixed-space evaluation masks, intensity conventions, and voxel
sampling for every candidate. Compute normalized mutual information as
2*MI/(H_fixed+H_moving), and squared local normalized cross-correlation with a
1-mm Gaussian neighborhood. Report whole-brain values and separate thalamus,
STN, and SN values. Deep evaluation regions are each anatomical union dilated
by 2 mm within the brain mask, providing context around small nuclei.

The descriptive deep score is the mean of the three regions' normalized MI
and squared local correlation (equal weight for each region and each metric).
Keep all constituent metrics available; the score is a declared ranking
heuristic, not anatomical validation. Inspect deep and whole-brain overlays
before selecting stage winners. Do not compare raw optimization objective
values across MI and CC runs.

Report transformed-mask overlap, finite image/field coverage, affine
determinant and principal scales, displacement Jacobian distribution and
nonpositive-Jacobian counts, and forward/inverse consistency where available.
Clearly flag numerical failures, orientation reversal, folding, and visible
global misalignment. Any visual exclusion or change to the automatic order
must have an explicit reason in the selection record.

Deliver CSV/JSON measurements and rankings, recorded stage selections,
per-candidate commands and logs, masks with QA images, whole-brain and deep
comparison PNGs, and a concise source-grounded findings document. Include
the preserved existing ANTs result as a historical comparison.

## Reuse and validation boundaries

Each candidate has its own output prefix. A successful completed candidate
can be reused only when its explicit command, selected parent, and consumed
input metadata match. Do not use a repository/configuration hash or comments
as a global invalidation switch. Changed linear inputs affect their linear
candidate and descendants; changed SyN parameters affect only that candidate
and local descendants; changed local masks affect only local candidates;
changed evaluation rules require remeasurement/ranking, not registration.

## Frozen evaluation details

Use 64 histogram bins for evaluation NMI. Compute the 0.5th and 99.5th
percentiles once per evaluation context from the copied fixed image within
the fixed brain mask and the copied moving image within the accepted native
brain mask. These two intensity ranges are shared by every candidate; clip
and normalize each image to its corresponding range before scoring. Sampling
is anchored at fixed-grid index zero with stride two along each dimension.
Use all finite sampled voxels in each declared evaluation mask, including
zero-valued resampling background, and report coverage separately.

For squared local normalized correlation, apply Gaussian convolution with
sigma 1 mm to the normalized images on the original fixed grid, then sample
the resulting coefficient map on that same stride-two grid. Use the squared
covariance divided by the product of local variances, bounded to [0, 1];
neighborhoods with zero local variance contribute zero. Use a four-sigma
Gaussian support and nearest boundary extension consistently. Report the
mean coefficient over each evaluation mask.

Compute displacement Jacobians from the full-resolution fixed-grid pull map
in physical RAS millimeters, including the identity term, and summarize all
brain and anatomical thalamus/STN/SN voxels. Use bounded float32 slab
calculations with a one-voxel derivative halo. Do not estimate the Jacobian
from a coarse sample of the field. Report median, 1st/99th percentiles,
minimum/maximum, and nonpositive counts; include finite coverage.

For inverse consistency, sample the forward field at the same stride-two
fixed-grid points, interpolate the inverse field at the mapped native
coordinates, and measure the round-trip distance in millimeters. Also
measure the reverse round trip from stride-two native-brain points. Exclude
out-of-grid or nonfinite round trips from distance summaries and report
their valid coverage. Brain-mask Dice uses the full fixed grid. Anatomical
ROI masks and the atlas-derived native brain mask are operational evaluation
regions, not independent segmentation truth.

All candidate figures use identical physical cuts and intensity windows.
The deep score remains the equal mean of the six already declared regional
NMI and squared local-correlation values. Store its constituent values and
numerical flags alongside the ordering; do not automatically turn numerical
or image-similarity rankings into claims of anatomical accuracy.

Validate source geometry and CLI parameters at their reading/execution
boundaries. Run focused checks on candidate counts, transform composition,
mask geometry and inclusion, scoring behavior, and rendered figures. No
unrelated repository test suite or full pipeline rerun is required.

Normalized local variances at or below float32 machine epsilon are treated
as numerically zero. Empty evaluation regions produce unavailable metrics;
constant histograms with zero joint entropy produce NMI zero. Nonfinite
intensities are excluded from pointwise summaries and replaced by zero only
for local-convolution calculation, with numerical flags and coverage retained.
No candidate is promoted by silently dropping an unavailable deep metric.

Existing per-candidate evaluation files are not overwritten by the evaluator.
When comparison tables or contact sheets are refreshed, their previous files
are moved to the system Trash before replacement. Brain-mask Dice is only a
QC statistic: the native operational mask was derived from the preserved
existing ANTs transform, so this overlap is not independent evidence of
anatomical accuracy and is not included in the deep score.

## Verified staged transform composition

Synthetic noncommuting scale/translation tests verified image pull composition,
inverse order, Jacobian, and field-versus-chain resampling. A and B can write
Composite.h5/InverseComposite.h5 directly. C instead initializes from its
parent forward displacement NIfTI with write-composite-transform=0 and
collapse-output-transforms=0; this avoids ANTs omitting the inverse composite
when a nonlinear H5 initial transform has no serialized inverse. Compose C
forward with `-t residualWarp -t parentForward`, and C inverse with
`-t parentInverse -t residualInverseWarp`, on fixed and native reference grids
respectively. The parent's affine is already included and is not applied again.
The original moving image is used for all registration stages.

## Mask QA rendering

Mask QA panels use aspect-preserving tile enlargement and reserved label space.
Improving these figures rerenders existing prepared images and masks only;
it does not regenerate masks, replace input snapshots, or rerun registration.
The previous untracked preparation script and QA PNGs are preserved in the
system Trash before replacement.

For each bilateral deep-region sagittal panel, select the voxel column with
the greatest anatomical ROI cross-sectional area (first maximum if tied),
so a midline gap cannot hide the paired nuclei. Coronal and axial coordinates
remain the anatomical union medians. These cuts are fixed for all candidates
and recorded in physical RAS coordinates. Image finite coverage is measured
on every voxel of each evaluation region; the finite sampled fraction is
reported separately. Also report native-brain inverse-field finite coverage.

## Template-mask correction after the initial linear screen

Reference-image overlays exposed a concrete mask failure: the installed
77,801-mm3 t1_brainmask excludes frontal and temporal cortex and cerebellar
regions visible in D99 t1. The initial four linear runs are retained under
diagnostics/template_mask_mismatch and are excluded from the main scan.

For this brain-only ex-vivo template, the corrected operational mask uses
the largest 6-connected component of strictly positive template intensity,
with enclosed holes filled. The inspected candidate retains 99.9869% of
positive support, removes 968 detached voxels, fills 15,214 hole voxels, and
measures approximately 116,084 mm3. It must be visually checked on the fixed
image and projected again to native space before restarting Stage A.
The global template coverage check is saved as
`figures/fixed_brain_mask_qa.png`, with the corrected mask and the installed
mask comparison over the full fixed-brain extent. Native multi-slice and
template deep-mask QA figures are retained alongside it.
This changes the masks consumed by A and its descendants only. The current
clinical/native/normalization files remain untouched.

Deep-panel field-of-view centers remain at the bilateral anatomical medians,
independent of the off-midline sagittal slice chosen for visible ROI tissue.
This preserves bilateral coverage in coronal and axial panels.

## Auxiliary contrast for final visual review

Inspect the existing anchor-coregistered axial, coronal, and sagittal T2 images
and SWI without estimating another coregistration. Use the frozen baseline
inverse only to project the fixed anatomical and contextual deep masks for
input coverage and contrast checks. Select one T2 acquisition and the available
SWI, copy them to `inputs/aux_t2.nii.gz` and `inputs/aux_swi.nii.gz`, and record
original paths, sizes, modification times, geometry, and measured coverage in
`inputs/auxiliary_sources.json`. These inputs support final visual review only;
they are excluded from parameter estimation and numerical candidate ranking.
Projected masks are baseline-dependent operational regions, not independent
native nucleus annotations. Leave the registration inputs and masks unchanged.

`render_auxiliary.py --output-root OUT --candidate-dir CAND` applies the saved
candidate forward displacement field to the copied T2 and SWI using linear
interpolation and one ITK thread. It does not estimate a transform. It saves
`aux_t2_warped.nii.gz`, `aux_swi_warped.nii.gz`, each application command and
log, `auxiliary_render.json`, and `qa_auxiliary_deep.png` inside the candidate.
Existing outputs cause refusal before writes. The panel contains thalamus,
STN, and SN rows with D99-reference, candidate-T1, auxiliary-T2, and auxiliary-SWI
columns at the evaluator's identical axial cuts and 12-mm context half-width.
Each modality uses its own 0.5th/99.5th-percentile window from its copied native
image within the operational native brain mask, shared across candidates;
the D99 column retains the evaluator's fixed-image window. Atlas contours are
explanatory references rather than independent nucleus ground truth. These
outputs do not alter optimization, evaluation scores, or candidate rankings.

Comparison contact sheets display candidate identifiers horizontally, wrapped
at their double-underscore separators, with right-aligned row labels. This
prevents the observed overlap and clipping of long candidate identifiers.
This figure-layout change does not alter scores, fields, candidate metrics,
image windows, anatomical contours, or physical cuts.

## Local-transform integration check

Before launching Stage C, run one test-only SyN iteration on the actual fixed
and oblique native grids using the completed parent
`braincom_mi32__mi32__step010_u3_t0__quartermm`. Retain the copied original T1
images, the 2-mm deep fixed mask, and the accepted native brain mask. Use dense
MI32, SyN[0.05,3,1], shrink 2, smoothing 0.25 mm, seed 1, double precision, and
one ITK thread. Initialize from the parent's complete forward NIfTI field and
write the residual pair with composite output and output collapse disabled.
Compose the full forward and inverse fields using the previously verified
ordering, then compare direct ANTs resampling with an independent field-based
resampling and measure roundtrip distances at deep-region points. Preserve all
commands, logs, fields, images, and measurements under
`diagnostics/local_transform_check`; these outputs are excluded from candidate
ranking. This check exercises actual optimization on differing grids without
changing the accepted candidate design or rerunning a candidate.

The single shrink-2 test retains its residual fields on the optimizer's coarse
grid. Residual displacement measurements must therefore interpolate in physical
coordinates using each field's own affine; fixed-grid voxel indices cannot be
reused for those residuals. The composed forward and inverse fields still use
the full fixed and native reference grids, respectively.

Comparison PNG export includes the complete artist bounding box so the
observed constrained-layout title clipping cannot hide the figure heading.
This export-only correction leaves every numerical evaluation unchanged.


## Observed storage interruption and scoped continuation

At 13:50:46 UTC on 2026-10-14, the Stage C dispatcher could not stat the copied
fixed input on /Volumes/VAL (ENOENT). Three active local registrations exited
without complete results, and six queued candidates never started. Three other
local candidates finished successfully at 13:52 UTC after path access returned.
The precise external-storage cause is not established. Preserve the incomplete
candidate directories under diagnostics/storage_interruption, with relocation
and observed-error records, before resuming the remaining nine candidates.
Check the three completed C payloads and grids because their writes overlapped
the incident. Reuse those completed candidates only through the runner's existing
per-candidate command/input check. Do not rerun A or B, replace completed outputs,
or add an automatic retry mechanism to the runner.


## Completed scan and deliverables

All 4 accepted-mask linear candidates, 64 whole-brain candidates and 12 local
candidates completed. The final local continuation reported no failures; three
completed local candidates were retained after the targeted storage-incident
payload check. Four early mask-diagnostic runs, the one-iteration integration
check and three interrupted attempts are excluded from the main ranking.

The selected image-score leader is
`braincom_mi32__mi32__step010_u3_t0__quartermm__roi2__step010`, deep score
0.36155256, compared with historical ANTs 0.24033646 and its unrefined parent
0.34760324. Top-three anatomical review retained the prespecified score order.
Stronger SN mapping deformation and incompletely visible nucleus boundaries
remain explicit limitations, not evidence of established localization accuracy.

`ranking.csv` contains 81 rows (80 main candidates plus historical ANTs), inherited
parameters, component scores and local-parent changes. `evaluation.csv` and
`ranking.json` retain detailed measurements; `selection.json` records final
review and exact output paths. `FINDINGS.md` gives the results and limitations.
The focused deep/whole-brain PNGs show baseline then final ranks 1, 2 and 3;
22 paginated contact sheets retain every measured candidate. `build_report.py`
in the output scripts directory records report generation. Source snapshots
are provenance copies and do not change the application pipeline.


## Authorized promotion into the formal case

The user subsequently requested that rank 1 be applied to the formal
`sub-181101/normalization` directory and related files. Prepare the complete
replacement under the scan output's `promotion` directory before installing it.
Preserve the current normalization directory, UI preferences, and methods log
in an accessible backup there; move replaced original untracked files/directories
to the system Trash before installing staged replacements.

Install the selected full forward/inverse ANTs displacement fields under the
existing `desc-ants.nii.gz` filenames without changing vector conventions,
reapplying the affine, or reducing field precision. Resample the eight preoperative
anchor-native images and raw postoperative CT with Linear interpolation/double
precision, matching the scan's convention. Generate normalized tone-mapped CT
from the newly normalized raw CT with `ea_tonemapct`, and regenerate all nine
normalization checkreg PNGs with `ea_gencheckregpair` against the D99 T1 reference.
Do not estimate another registration or alter coregistration/native inputs.

Retain method `ANTs (Avants 2008)` and transform format `ants` for existing image
and point consumers. Replace stale preset/refinement descriptions with the actual
selected stage chain, copied-input provenance, interpolation and scan selection.
Preserve command/method history and append the installation event. Keep the
existing normalization approval value of zero for the GUI review workflow.
Update only `normalize.method` in the case UI preferences from EasyReg to ANTs.
Do not change global defaults or unrelated UI preferences.

There are no reconstruction, stimulation, brainshift, native-atlas or tractography
products in this case requiring downstream recomputation. Inspect the old WarpDrive
session files separately before deciding whether their retained state is applicable.
The dependency scope is the normalization fields, their normalized image consumers,
tone-mapped CT, corresponding QC images, and method/UI records. Validate staged
image grids and finite data, selected-field identity, anchor-T1 agreement with the
ranked result, original-input preservation, and Lead-DBS's own transform resolver.
A full application pipeline or repository test suite is not required.


The prior WarpDrive source.json, target.json and info.json will also be archived
from the active case. Existing equal source/target fiducials are fixed-point
constraints retained by WarpDrive after hardening; the next session would load
them on the newly installed transform. Preserve all three files in backup and
Trash, retaining historical logs. No other downstream products exist to clear.


## Completed formal installation

Rank 1 was installed at 2026-10-14T16:53:50.210432+00:00 into
`/Volumes/VAL/VALPD/derivatives/leaddbs/sub-181101/normalization`. The installed directory contains 2 selected full ANTs
fields, 10 normalized images, 9 refreshed Lead-DBS checkreg PNGs and 2 method/command
logs. The subject methods history was appended; only `normalize.method` changed
in UI preferences. The prior WarpDrive source/target/info JSON files were archived
from active paths because their fixed-point constraints belonged to the previous
normalization. Native/coregistered images remain unchanged.

The prior normalization, UI preferences, methods history and WarpDrive session
are recoverable under `/Volumes/VAL/VALPD/derivatives/ants_d99_sweep/sub-181101/promotion/backup`. Replaced originals also went to the system
Trash. Completed staged directories were moved into the formal case; staged
paths in command/review records describe their locations at execution time.

`installation.json` records the installed files and backup; the MATLAB and
post-installation validation records confirm canonical formal paths, ANTs dispatch,
exact selected-field byte identity, file counts and preserved native inputs.
The anchor image agrees with the ranked image to floating-point rounding. All
nine checkreg PNGs passed rendering/application review. Approval remains 0 for
the existing GUI review workflow. No registration optimization or broader
application pipeline was rerun.
