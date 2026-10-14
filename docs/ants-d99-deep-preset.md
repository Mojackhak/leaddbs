# Macaque D99v2 deep-nuclei ANTs preset


## Usage

Select D99v2 space and a preoperative T1w anchor. Reopen the ANTs Normalization
Settings window, choose `Macaque D99v2: Deep Nuclei (T1)` in Preset, and click
Save. Then use the normal normalization or checkreg recompute action. Merely
installing this code does not change the currently saved preset.

No previous normalization or manually prepared mask is required. Automatic
mode prepares the masks, retains the bootstrap affine for main initialization,
and runs the fixed main chain. The Image Processing Toolbox functions used for
connected components, hole filling and distance transforms are required during
execution. Preset discovery does not load or validate these image resources.
The resulting method log remains unapproved until the usual CheckReg review.

## Approved behavior

Add the selectable preset `Macaque D99v2: Deep Nuclei (T1)` without changing
the currently selected preset or existing preset behavior. Its function is
`ea_antspreset_macaque_d99_deep`. It is restricted to D99v2 and a preoperative
anchor T1. Only that image estimates the transform; all existing normalized
modalities are subsequently generated through the final transform.

The user requested automatic preparation even for subjects with no previous
normalization or native brain mask. Existing subject transforms must not be
used by this preparation. The profile was selected on sub-181101; automatic
mask preparation is a new component requiring separate validation.

## Fixed numerical recipe

All optimization and displacement composition use double precision, seed 1,
one ITK thread, histogram matching off, and convergence threshold/window
1e-6/10. Intensity resampling uses Linear interpolation; masks use nearest
neighbor. Restore process thread environment after execution.

The main stages reproduce the selected separate ANTs calls:

| Stage | Transform and metric | Iterations | Shrink | Smoothing in mm |
|---|---|---|---|---|
| Linear | Rigid[0.1], Affine[0.1]; MI32 Regular 0.25 | 1000x500x250x100 each | 12x8x4x2 | 1.5x1x0.5x0.25 |
| Whole brain | SyN[0.1,3,0]; MI32 dense | 100x70x50x20 | 8x4x2x1 | 1x0.5x0.25x0 |
| Deep | SyN[0.1,3,1]; MI32 dense | 50x20 | 2x1 | 0.25x0 |

With supplied checked masks, linear initialization is binary brain-mask center
of mass. Automatic mode retains the bootstrap affine as its initial transform.
Main-stage inputs
remain the original anchor image. The deep fixed mask is the bilateral union
of thalamus, STN and SN, dilated by 2 mm inside the fixed brain mask. The
moving mask remains the native brain mask.

## Automatic mask preparation

Build the fixed operational brain mask from the largest 6-connected strictly
positive D99 T1 component, filling enclosed holes. This avoids the installed
template mask's demonstrated cortical/cerebellar truncation. Build the deep
mask from the installed 66 thalamic, 2 STN and 8 SN binary ROIs in physical
coordinates. Retain the installed template and atlas files unchanged.

For a new native mask, run geometric-center initialized Rigid/Affine using
the main linear schedule with the fixed brain mask and no moving mask. Follow
with a short regularized MI32 SyN[0.1,3,1] stage: iterations 100x70x50,
shrink 8x4x2, smoothing 1x0.5x0.25mm. Project the fixed brain mask through
this bootstrap inverse with nearest-neighbor interpolation, retain the largest
6-connected component, and fill holes. The bootstrap inverse supplies the mask projection. Its affine component
initializes the main linear stage; its nonlinear component is not included in
the main transform chain.

Write mask overlays and source/geometry records. Reject empty/nonfinite masks,
invalid image geometry or failed ANTs commands at their input/output boundary.
Do not claim that automated masks are independent segmentation ground truth.
The bootstrap recipe is subject to the approved isolated cold-start validation.

## Implementation boundaries and interfaces

The preset definition owns the fixed stage parameters and label. The existing
settings window discovers the new file normally. Choosing it sets and locks
SyN, MI, subcortical refinement on, FA off, skullstripped off, start-from-scratch,
and one thread. Other presets regain their ordinary editable controls. Merely
opening the menu does no image preparation, registration or global selection
change.

The MATLAB execution entry point is:

`result = ea_ants_d99_deep_run(templateDir, movingImage, workDir, preparedMasks)`

The optional preparedMasks structure has `fixed`, `moving`, and `deep` paths
and supports the required checked-mask reproduction test. Ordinary preset
execution omits it and performs automatic preparation. The result exposes
`forward`, `inverse`, `warped`, `masks`, `provenance`, and `preset`.
It does not publish formal patient outputs itself. Use bundled ANTs executables
resolved through `ea_getExec`; no hard-coded subject, volume or Conda paths.
Use existing MATLAB/NIfTI, command execution and image-QC helpers.

The preset struct includes rigid/affine/syn/scrf fields following the existing
stage-specific preset format, plus `bootstrap`, `space`, `randomseed`,
`float`, `interpolation`, and `deepMarginMm`. Bootstrap linear fields match the
main linear fields; bootstrap.syn holds the short regularized schedule above.

`ea_normalize_ants_d99_deep(options)` owns validation of D99/T1 selection,
calling the execution entry, staging all formal outputs, and publication.
Dispatch to it before the generic existing-transform cleanup. Keep registration
work under the subject's dedicated `masks/ants_d99_deep` directory, outside
generic `masks/mask_*` names read by legacy presets. Staging and backups also
remain outside the formal normalization directory until publication succeeds.
Retain original intensity/coregistration inputs and previous formal outputs.

Method logs retain `ANTs (Avants 2008)` and format `ants`. Set
`settings.preset_id = ea_antspreset_macaque_d99_deep`, `interpolation = Linear`,
and `precision = double`, and record the actual stage chain/mask provenance.
Bulk reapplication reads these stored values, not a later global preset choice.
Other method logs and manual transform calls retain their existing behavior.

The publication path uses existing image application, CT tone mapping and
checkreg functions against staged paths. Preserve replaced untracked originals
in Trash and a recoverable backup. Retain approval zero. Archive old WarpDrive
source/target/info session constraints when replacing its normalization.
Do not automatically alter UI preferences outside explicit preset Save.

The internal publisher lives under `ext_libs/ANTs`, so it is not discovered as
another root-level normalization method. Both the main normalization dispatcher
and the direct ANTs entry delegate before generic refinement preparation. The
publisher validates the selected space and T1 anchor before creating work files.
Each publication stages only affected normalization files and the appended
methods record outside the formal directory. It validates all expected staged
images and QC figures before preserving replaced files in a recoverable backup
and Trash. If publication itself fails, restore those affected files from the
backup and surface the error; no unrelated case files are removed.
Existing SCRF files remain preserved, but are not applied to the new normalized
images because their normalization-dependent validity is stale. Record the
need to rerun brainshift and reset an existing brainshift approval to zero in
the same backed-up publication. Retain the existing rerun warning without
adding broad segmentation cleanup to this preset.
The `requires_rerun` explanation belongs to normalization provenance; the
brainshift log changes only its existing approval field. An enabled MATLAB
diary is also written in staging and published after it is closed.
Preserve and append the actual bootstrap and main-stage command text to the
formal subject `*_desc-antscmd.txt` within the same staged publication. Validate
the anchor's BIDS T1w filename suffix, rather than constraining its internal
modality alias. A partially copied new output is included in failure cleanup
even when the copy operation did not return successfully.

## Reuse and failure behavior

Successful execution stages have separate records of the resolved numerical
parameters and inputs actually consumed. Reuse matching completed stages.
Preserve superseded/incomplete stage outputs before replacing them; do not add
automatic retries. Configuration source formatting and documentation changes
are not numerical inputs and must not trigger recomputation.

Template/ROI inputs affect the derived masks; bootstrap inputs affect the native
mask; native brain masks or main linear parameters affect the linear stage and
descendants; whole-brain parameters affect that stage and deep descendants;
the deep mask affects the deep stage only. Display changes affect QC only.
No repository-wide cache or invalidation key is introduced.

## Focused validation

Test preset discovery/values, UI constraints and restoration of editability,
T1-only dispatch, legacy behavior, stored Linear/double reapplication, command
construction, transform order, mask geometry and stage-specific reuse. Validate
the actual grid and masking contract, including floating-point affine rounding.

Run an isolated checked-mask reproduction using sub-181101's frozen inputs,
then an isolated cold start with no previous fields or supplied native mask.
Compare masks, whole-brain/deep images, declared image scores, Jacobians and
inverse consistency. Never replace the currently installed winning result
during these tests. Full parameter rescanning and unrelated repository suites
are outside scope. Whole-brain QC remains required after local refinement.

## Stored reapplication contract

`ea_gettransformfiles(options)` retains its existing single-output behavior and
may also return the already parsed normalization-method log as a second output.
Its existing connectome fallback returns an empty second output. Bulk ANTs
reapplication uses that log to select the recorded interpolation and precision
for `settings.preset_id = ea_antspreset_macaque_d99_deep`, avoiding a second JSON
parse or a global preference read. The publisher records those values under
`settings.interpolation` and `settings.precision`. Legacy logs and positional
manual calls retain their existing interpolation and single-precision defaults.
Source/reference/transform selection and ordinary approved postoperative
brain-shift header adjustment retain their existing behavior.

For the stored D99 preset, a nonzero ANTs image-application exit status raises
an error before publication. This is the command execution boundary required
by staging; legacy logs and positional manual calls retain their prior status
handling. No additional image resampling or command retries are introduced.

Engine reuse tests use small real NIfTI images and supplied masks while mocking
only external ANTs execution and QA rendering. They verify that an unchanged
rerun performs no registration, a supplied deep-mask or resolved SCRF-parameter
change preserves linear/whole-brain results and reruns only the deep stage,
and completion-record formatting/key ordering does not invalidate stages.
Command traces verify the forward/inverse residual composition ordering;
actual full-grid transform physics is covered by the isolated real-image runs.

When the stored D99 normalization provenance marks
`downstream.brainshift.requires_rerun = true`, bulk reapplication skips an
existing SCRF matrix until the current brain-shift log has `approval = 1`.
An absent or unapproved brain-shift log does not authorize the stale matrix.
After renewed brain-shift approval, the normal temporary-header application
resumes without clearing the historical normalization provenance marker.
This gate applies only to D99 bulk reapplication; legacy logs and positional
manual calls retain their behavior. Resolve the normalization log once before
constructing source images, and read brain-shift approval only when an SCRF
would otherwise be used and the D99 provenance requires its renewal.


## Validated cold-start failure and approved initialization correction

The first cold-start test produced a plausible native brain mask (103,069 mm3),
but restarting the main linear optimizer from mask centers lost the correct
orientation already found by bootstrap. The resulting linear QA had a conspicuous
tilt. The user explicitly approved retaining the bootstrap affine in automatic
mode. Extract its single collapsed AffineTransform_double_3_3 component without
coordinate conversion and initialize the main rigid/affine call with it. This
preserves the main stage schedules and the original image, and does not reapply
the bootstrap nonlinear warp. Supplied-mask reproduction retains the original
brain-mask COM initialization. Record the actual initialization in provenance.
Keep the failed initialization diagnostics; only main linear and descendants
need rerunning after this correction. Bootstrap and mask results remain reusable.

## Recomputing from an already open checkreg window

The checkreg figure retains its options in appdata. Saving a different ANTs
preset in the separate settings window previously left those options stale,
and the recompute callback deleted normalized images before dispatching the
normalization method. This bypassed the D99 publisher's preservation boundary.

For normalization recomputation, resolve the method selected in checkreg and
reload the saved machine normalization settings before deleting any files.
Keep other subject-specific preferences and paths unchanged, and retain the
refreshed options in the figure. For ANTs with the D99 deep preset, call the
normalization entry point without legacy pre-deletion. Let the staged publisher
own image replacement, QC generation, approval logging and downstream handling;
do not repeat the callback's legacy QC/log/segmentation cleanup afterward.
Other normalization methods and presets keep that legacy callback behavior.
If D99 execution fails, the prior normalized images and method log must remain
available. Callback tests use isolated figures, temporary files and mocked
publication; no patient data or persisted user preferences are changed.


The bootstrap affine is serialized with ITK's existing text-transform format
(.tfm), preserving its double parameters and fixed center. MATLAB's -v4 writer
rejects the long ITK affine variable name, so that attempted serializer was
rejected by ANTs before any optimization. The text representation uses 17
significant digits and does not alter the physical transform convention.

The execution engine consumes seed, precision and interpolation from the resolved
preset, alongside stage parameters. Image and mask parsing is performed once
per required read; copying an input does not add a duplicate immediate parse.


## Completed validation on 2026-10-14

All 42 focused MATLAB tests passed together in Conda `leaddbs`: 7 preset/UI,
16 stored reapplication/SCRF, 5 engine reuse/transform-order, 10 publication,
and 4 checkreg dispatch tests. They cover preservation on failure and legacy
behavior as well as the new profile. A typo in the initial combined-test filename
was corrected before the successful complete run; no numerical result depended
on that failed test invocation.

With the previously checked masks, the full new engine reproduced the selected
scan result exactly: zero maximum difference in the loaded warped T1, full
forward field, and full inverse field; all affines match. Its deep image score
therefore remains 0.3615525562 under the frozen comparison protocol.

The automatic cold start used no prior subject normalization. Its fixed brain
and deep masks match the checked template masks voxel for voxel. Its generated
native operational mask is approximately 103,069 mm3; boundaries differ from
the prior projected mask. After the user-approved bootstrap-affine initialization
correction, the final deep score is 0.3598102389, whole-brain NMI 0.3040621006,
and squared local correlation 0.7060835019. All evaluated images/fields are
finite and the brain has zero nonpositive Jacobians. Fixed-grid roundtrip P95
is 0.0494453 mm; this is transform consistency, not anatomical registration
error. Visual review found no gross orientation, coverage or collapse failure.

The first COM-reset cold-start attempt is retained as a diagnostic (deep score
0.2799886983). It illustrates why numerical finite/Jacobian checks alone are
insufficient. The invalid MATLAB affine serialization is also preserved as a
pre-optimization diagnostic. Neither failed attempt is used by the delivered
automatic path.

A real one-T1 publication fixture exercised actual ANTs image application,
FSL/MATLAB checkreg, method/command logs, backup/Trash and publication; only the
expensive engine was replaced with its completed validation result. Published
fields were byte-identical to the engine fields; T1 maximum intensity difference
was 3.17e-12 from final-field resampling. All 138 protected real-case/template
file metadata records remained unchanged. The currently installed sub-181101
normalization was not replaced during implementation or validation.

Validation evidence is under
`/Volumes/VAL/VALPD/derivatives/ants_d99_sweep/sub-181101/preset_validation`.
This is a single-subject functional and image-fit validation, not independent
small-nucleus localization accuracy or a claim of a universally optimal recipe.
No unrelated repository suite, global invalidation, version change, commit or
push was performed. Whole-brain QC remains because deep refinement can affect
anatomy outside the metric mask.
