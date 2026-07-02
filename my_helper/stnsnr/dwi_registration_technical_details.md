# STN/SNr DWI Registration Technical Details

Date: 2026-07-03

## Purpose

This document fixes the technical plan for importing, staging, and registering the STN/SNr cohort DWI scans into the existing Lead-DBS subject spaces. The staged DWI and b0 outputs are prerequisites for patient-specific seed-target tracking, VTA/ROI projection into DWI space, and native/MNI streamline display.

The import/staging stage refreshes raw BIDS DWI files, stages DWI derivatives, and extracts b0 images. Registration is a separate step and is not required for a staging-only refresh. Neither stage runs tractography, normative connectome analysis, or sweet/sour spot modeling.

The first completed T2 branch used Lead-DBS ANTs linear registration under `coregistration/dwi_t2/`. Because manual QC still showed large residual errors in some subjects, the next pilot adds two method-comparison branches for three subjects only:

```text
ChenMeiJu
ZhangXiaoHong
ZhangMing
```

## Data Sources

Study root:

```text
/Volumes/VAL/STNSNr
```

DWI source root:

```text
/Volumes/VAL/STNSNrdwi
```

DWI import logs are written to:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/dwi_import_<timestamp>.csv
```

Included subjects are the 16 valid DWI four-file sets:

```text
ChenLingHua
ChenMeiJu
FanDongDong
GengHui
HuFengXian
HuangDan
LiPing
LinJia
MaoXiaoMing
ShengGuoLiang
WuYueFen
YuDongJian
ZhangMing
ZhangXiaoHong
ZhaoPeiGen
ZhengXiangQuan
```

## Registration Chain

The existing anatomical normalization is reused:

```text
anchorNative T1 -> MNI152NLin2009bAsym
```

The fixed anatomical image for DWI registration is the already coregistered anchorNative T2. This uses the closer T2-like contrast between DWI b0 and anatomical T2, while still keeping all registration outputs in the same Lead-DBS anchorNative subject space.

The DWI registration chain is:

```text
raw BIDS DWI
  -> derivatives/leaddbs/sub-*/preprocessing/dwi
  -> automatic b0 extraction in native DWI space
  -> b0-to-anchorNative T2 linear registration
```

During DWI import/staging, Lead-DBS automatically recreates the staged b0 image from the imported 4D DWI and gradient sidecars:

```text
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.nii
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.bval
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.bvec
  -> preprocessing/dwi/sub-<Subject>_ses-preop_dwi_b0.nii
```

The import helper defines b0 volumes as `bval < 10`. If multiple b0 volumes are present, it writes their mean. Existing staged b0 files are overwritten during import/staging so the b0 always matches the current staged DWI and sidecars.

The b0 image must inherit the affine/header of the corresponding 4D DWI frame. It must not be independently recentered. This keeps b0, FA, masks, and tractography products on the same DWI grid.

For single-slice tiled DWI inputs, the extracted b0 must still preserve the
singleton z dimension, for example `X x Y x 1`, so file readers outside SPM do
not interpret the b0 as a two-dimensional image.

Tractography remains in native DWI space. MNI atlas ROIs should be projected into DWI space by:

```text
MNI ROI -> anchorNative T1/anchorNative T2 -> DWI/b0
```

DWI streamlines should be displayed in MNI space by:

```text
DWI streamline -> anchorNative T2/anchorNative T1 -> MNI
```

The previous direct b0-to-anchorNative T1 outputs under `coregistration/dwi/` remain available only for comparison. Coregister UI B0 outputs under `coregistration/anat/` and `coregistration/transformations/` are formal Lead-DBS UI products. The T2 registration pilot outputs remain separate method-comparison branches for downstream tracking evaluation.

The existing ANTs T2 output under `coregistration/dwi_t2/` remains available as the baseline comparator. The SPM and Hybrid pilot outputs must not overwrite it.

## Output Convention

Raw BIDS DWI files under `rawdata/sub-<Subject>/ses-preop/dwi/` may be refreshed from `/Volumes/VAL/STNSNrdwi` during a controlled re-import. Each imported source basename is normalized to the Lead-DBS BIDS basename:

```text
sub-<Subject>_ses-preop_dwi.nii.gz
sub-<Subject>_ses-preop_dwi.json
sub-<Subject>_ses-preop_dwi.bval
sub-<Subject>_ses-preop_dwi.bvec
```

Each included subject receives staged derivative files under:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-<Subject>/preprocessing/dwi
```

Expected staged DWI files:

```text
sub-<Subject>_ses-preop_dwi.nii
sub-<Subject>_ses-preop_dwi.bval
sub-<Subject>_ses-preop_dwi.bvec
sub-<Subject>_ses-preop_dwi.json
sub-<Subject>_ses-preop_dwi_b0.nii
```

The b0 image must inherit the affine/header of the corresponding 4D DWI frame. It must not be independently recentered. This is intentionally different from workflows that correct only the b0 header, because tractography, FA, masks, and b0 must remain on the same DWI grid.

The staged b0 is exposed to the Lead-DBS Coregister UI as a pseudo-preop modality named `B0` when it exists under `preprocessing/dwi/`. `B0` is not an anatomical MRI modality; it is a DWI b0 image made visible in the anatomical coregistration interface so existing method selection, recompute, approval, and checkreg logic can be reused.

The Coregister UI `B0` output convention is:

```text
coregistration/anat/sub-<Subject>_ses-preop_space-anchorNative_desc-preproc_B0.nii
coregistration/transformations/sub-<Subject>_from-b0_to-anchorNative_desc-<method>.mat
coregistration/transformations/sub-<Subject>_from-anchorNative_to-b0_desc-<method>.mat
coregistration/checkreg/sub-<Subject>_ses-preop_space-anchorNative_desc-preproc_B0.png
```

The default formal Coregister UI target is the current anchorNative T1. The existing anchor selection and substitute-anchor controls remain available. The `B0` item is appended after anatomical preop modalities and must never become the default anchor.

Existing ANTs T2 comparison files:

```text
coregistration/dwi_t2/<b0base>2<anchorT2base>_ants1.mat
coregistration/dwi_t2/<anchorT2base>2<b0base>_ants1.mat
coregistration/dwi_t2/<b0base>2<anchorT2base>.nii
coregistration/dwi_t2/<anchorT2base>2<b0base>.nii
```

New SPM pilot files:

```text
coregistration/dwi_t2_spm/sub-<Subject>_from-b0_to-anchorNative_desc-spm.mat
coregistration/dwi_t2_spm/sub-<Subject>_from-anchorNative_to-b0_desc-spm.mat
coregistration/dwi_t2_spm/sub-<Subject>_b0_on_anchorT2.nii
coregistration/dwi_t2_spm/sub-<Subject>_anchorT2_on_b0.nii
```

New Hybrid SPM+ANTs pilot files:

```text
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-b0_to-anchorNative_desc-ants.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-anchorNative_to-b0_desc-ants.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-b0_to-anchorNative_desc-spm-init.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-anchorNative_to-b0_desc-spm-init.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_b0_on_anchorT2.nii
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_anchorT2_on_b0.nii
```

The first transform maps DWI/b0 coordinates to anchorNative T2. The second transform maps anchorNative T2 and native-space ROIs back to DWI/b0. The SPM branch is a single-step transform. The Hybrid branch is a two-step chain: `desc-spm-init` is the SPM initialization and `desc-ants` is the ANTs refinement after that initialization. Therefore the Hybrid `desc-ants` files must not be interpreted as standalone complete b0-to-anchorNative transforms.

The pilot branches use Lead-DBS UI-style `from-*_to-*_desc-*.mat` names inside branch-specific directories only. They must not be copied into `coregistration/transformations/` until manual QC selects a final method and the correct promotion logic is defined.

Implementation intermediates generated by SPM and ANTs may use legacy Lead-DBS names internally, but they should be kept under the branch `work/` subfolder. The branch root should contain only UI-style transform names and final resliced NIfTI outputs.

## Coregistration Method

The baseline T2 branch uses ANTs linear registration through Lead-DBS with a rigid stage followed by an affine stage.

The three-subject pilot compares:

```text
ANTs baseline:     existing coregistration/dwi_t2/
SPM branch:        SPM NMI estimate/write via ea_spm_coreg
Hybrid branch:     Lead-DBS Hybrid SPM & ANTs
```

Do not use SyN/nonlinear DWI-to-T2 registration in this workflow, because nonlinear warping of diffusion space can distort downstream tractography interpretation.

Use the existing subject-specific `anchorNative` T2 as fixed image. Resolve the fixed image from:

```text
derivatives/leaddbs/sub-<Subject>/coregistration/anat/*space-anchorNative_desc-preproc*_T2w.nii
```

Prefer `acq-iso_T2w` when present; otherwise use `acq-ax_T2w` or the first non-AppleDouble anchorNative T2. For the 16-subject STN/SNr DWI cohort, T2 is mandatory for registration and there is no automatic T1 fallback.

## QC Outputs

The baseline ANTs branch writes:

```text
qc/dwi_registration_t2/<Subject>_dwi_registration_qc.json
qc/dwi_registration_t2/<Subject>_b0_on_anchorT2.png
qc/dwi_registration_t2/<Subject>_anchorT2_on_b0.png
qc/dwi_registration_t2/<Subject>_fa_on_anchorT2.png
```

The SPM and Hybrid pilot branches write the same PNG/JSON naming pattern under:

```text
qc/dwi_registration_t2_spm/
qc/dwi_registration_t2_hybrid_spm_ants/
```

The baseline batch writes an aggregate status table under:

```text
derivatives/leaddbs/import_logs/dwi_registration_t2_status.csv
```

The pilot branches write:

```text
derivatives/leaddbs/import_logs/dwi_registration_t2_spm_status.csv
derivatives/leaddbs/import_logs/dwi_registration_t2_hybrid_spm_ants_status.csv
```

QC status must record:

- DWI, bval, bvec, and JSON presence.
- Number of DWI volumes and bval/bvec entries.
- Number of b0 volumes.
- Voxel size and image dimensions.
- Whether b0 spatial dimensions match the 4D DWI.
- Fixed anchor modality and anchor anatomical file.
- Whether forward and inverse ANTs transforms exist.
- Whether optional FA and DWI-grid masks were generated.
- Low-resolution warning for through-plane resolution at or above 4 mm.

## Failure Handling

The batch is resumable. Existing outputs are reused unless `Force` is explicitly enabled.

A subject must be marked `registration_failed` for the branch being run if:

- required raw DWI sidecars are missing;
- bval/bvec entries do not match the number of DWI volumes;
- no b0 volume is detected;
- no anchorNative T2 can be resolved;
- the selected registration method fails;
- forward or inverse transform is missing after registration.

Low through-plane resolution is a QC warning, not an automatic exclusion.

## Pipeline Entry

The 16-subject raw DWI re-import and staging-only entry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_import_stage.m
```

Run command:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_import_stage.m')"
```

The baseline ANTs T2 registration entry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration.m
```

The `stnsnr/` script should only orchestrate the batch. Reusable staging, registration, transform validation, and QC code belongs under:

```text
/Users/mojackhu/Github/leaddbs/my_helper/fiber/core/dwi
```

Run command:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration.m')"
```

The three-subject method-comparison pilot entry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration_method_pilot.m
```

Run command:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration_method_pilot.m')"
```

## Limitations

No fieldmap or reverse phase-encoding correction is included in this primary batch because no valid fieldmap/reverse-PE DWI source was identified in the imported DWI set.

Several included DWI scans have low through-plane resolution. These cases can be staged and registered for exploratory analysis, but their tractography results must be interpreted with lower confidence and flagged in downstream reports.
