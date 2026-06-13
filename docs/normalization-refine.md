# Cross-method normalization refinement

Lead-DBS normalization recompute uses a shared refinement layer before the
method-specific registration is launched. When a valid previous transform pair
exists for the same subject and template space, interactive sessions ask the
user whether to `Refine` or `Start from scratch`. Non-interactive sessions start
from scratch unless the normalization options explicitly request refinement.

## Transform selection

The shared layer scans `normalization/transformations` for current-subject
forward and inverse transform pairs from `anchorNative` to the active template
space. Supported previous transform formats are:

- `desc-ants.nii.gz`
- `desc-ants.mat`
- `desc-fnirt.nii`
- `desc-fnirt.nii.gz`

Only complete forward/inverse pairs are eligible. Temporary residual files and
unpaired outputs are ignored. If several pairs are available, the newest pair by
file modification time is used.

## Refine mode

In refine mode, the selected previous transform is transform `A`. The shared
layer first warps the preoperative normalization inputs from native space into
template space and places them in a temporary directory while preserving BIDS
suffixes so modality matching still works. The selected normalization method is
then run on those prewarped inputs and estimates only a residual transform `B`.

Method-specific application of normalization is deferred during residual
estimation. After the method returns, the shared layer writes final composite
transforms in ANTs displacement-field format:

- forward native-to-template: residual `B` followed by prior `A`
- inverse template-to-native: prior `A` inverse followed by residual `B` inverse

The final files are saved as:

- `options.subj.norm.transform.forwardBaseName + 'ants.nii.gz'`
- `options.subj.norm.transform.inverseBaseName + 'ants.nii.gz'`

The method log records `refine.mode`, selected prior transform paths, the
residual method, and `transform.format = 'ants'` so later apply operations use
the composite ANTs field even when the method name is FNIRT, SPM, EasyReg, or
SynthMorph.

## Start from scratch

Start-from-scratch mode keeps the existing overwrite behavior. Existing forward
and inverse transforms for the current subject transform base are removed before
the selected method runs, and the selected method writes its normal output.

## Method notes

ANTs no longer prompts independently for refinement when it is invoked through
the shared normalization entry point. The shared layer decides whether an ANTs
run is a fresh registration or residual refinement.

EasyReg, SynthMorph, SPM, and FNIRT remain responsible for estimating their
method-specific transform. The shared layer handles prewarping, deferred apply,
format conversion when needed, and final composition. FNIRT fields are converted
by applying the FSL warp to source-coordinate images and subtracting reference
coordinates before the LPS sign conversion used by ANTs displacement fields.
Because FNIRT-to-ANTs displacement conversion is sensitive to coordinate
conventions, cross-method refinement involving FNIRT is guarded by default and
must be explicitly enabled only after local image-equivalence validation.
