# STN/SNr DWI Registration Technical Details

Date: 2026-07-02

## Purpose

This document fixes the technical plan for registering the imported STN/SNr cohort DWI scans into the existing Lead-DBS subject spaces. The registration outputs are prerequisites for patient-specific seed-target tracking, VTA/ROI projection into DWI space, and native/MNI streamline display.

This stage performs DWI staging and b0-to-anchorNative T2 registration only. It does not run tractography, normative connectome analysis, or sweet/sour spot modeling.

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

DWI import log:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/dwi_import_20260701_013240.csv
```

Included subjects are the 12 rows with copied volumetric DWI:

```text
LinJia
HuFengXian
YuDongJian
WuYueFen
LiPing
MaoXiaoMing
ChenLingHua
FanDongDong
HuangDan
ZhangMing
ZhangXiaoHong
ChenMeiJu
```

The following subjects are excluded from this registration batch because the import log indicates partial-recovery, single-slice, or tiled DWI exports:

```text
ShengGuoLiang
GengHui
ZhengXiangQuan
ZhaoPeiGen
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
  -> b0 extraction in native DWI space
  -> b0-to-anchorNative T2 linear registration
```

Tractography remains in native DWI space. MNI atlas ROIs should be projected into DWI space by:

```text
MNI ROI -> anchorNative T1/anchorNative T2 -> DWI/b0
```

DWI streamlines should be displayed in MNI space by:

```text
DWI streamline -> anchorNative T2/anchorNative T1 -> MNI
```

The previous direct b0-to-anchorNative T1 outputs under `coregistration/dwi/` remain available only for comparison. They are not the primary registration chain for downstream STN/SNr tracking.

The existing ANTs T2 output under `coregistration/dwi_t2/` remains available as the baseline comparator. The SPM and Hybrid pilot outputs must not overwrite it.

## Output Convention

The raw BIDS data under `rawdata/` must not be modified. Each included subject receives staged derivative files under:

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

Prefer `acq-iso_T2w` when present; otherwise use `acq-ax_T2w` or the first non-AppleDouble anchorNative T2. For this 12-subject batch, T2 is mandatory and there is no automatic T1 fallback.

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

The full 12-subject baseline ANTs T2 pipeline entry is:

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
