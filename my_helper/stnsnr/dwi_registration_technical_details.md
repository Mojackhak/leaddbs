# STN/SNr DWI Registration Technical Details

Date: 2026-07-02

## Purpose

This document fixes the technical plan for registering the imported STN/SNr cohort DWI scans into the existing Lead-DBS subject spaces. The registration outputs are prerequisites for patient-specific seed-target tracking, VTA/ROI projection into DWI space, and native/MNI streamline display.

This stage performs DWI staging and b0-to-anchorNative T1 registration only. It does not run tractography, normative connectome analysis, or sweet/sour spot modeling.

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

The new DWI registration chain is:

```text
raw BIDS DWI
  -> derivatives/leaddbs/sub-*/preprocessing/dwi
  -> b0 extraction in native DWI space
  -> b0-to-anchorNative T1 ANTs linear registration
```

Tractography remains in native DWI space. MNI atlas ROIs should be projected into DWI space by:

```text
MNI ROI -> anchorNative T1 -> DWI/b0
```

DWI streamlines should be displayed in MNI space by:

```text
DWI streamline -> anchorNative T1 -> MNI
```

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

Expected registration files:

```text
coregistration/dwi/<b0base>2<anchorT1base>_ants1.mat
coregistration/dwi/<anchorT1base>2<b0base>_ants1.mat
coregistration/dwi/<b0base>2<anchorT1base>.nii
coregistration/dwi/<anchorT1base>2<b0base>.nii
```

The first transform maps DWI/b0 coordinates to anchorNative T1. The second transform maps anchorNative T1 and native-space ROIs back to DWI/b0.

## Coregistration Method

Use ANTs linear registration through Lead-DBS with a rigid stage followed by an affine stage. Do not use SyN/nonlinear DWI-to-T1 registration in the primary workflow, because nonlinear warping of diffusion space can distort downstream tractography interpretation.

Use the existing subject-specific `anchorNative` T1 as fixed image. Resolve the fixed image from:

```text
derivatives/leaddbs/sub-<Subject>/coregistration/anat/*space-anchorNative_desc-preproc*_T1w.nii
```

Prefer `acq-iso_T1w` when present; otherwise use `acq-ax_T1w` or the first non-AppleDouble anchorNative T1.

## QC Outputs

Each subject should receive:

```text
qc/dwi_registration/<Subject>_dwi_registration_qc.json
qc/dwi_registration/<Subject>_b0_on_anchorT1.png
qc/dwi_registration/<Subject>_anchorT1_on_b0.png
qc/dwi_registration/<Subject>_fa_on_anchorT1.png
```

The batch should also write an aggregate status table under:

```text
derivatives/leaddbs/import_logs/dwi_registration_status.csv
```

QC status must record:

- DWI, bval, bvec, and JSON presence.
- Number of DWI volumes and bval/bvec entries.
- Number of b0 volumes.
- Voxel size and image dimensions.
- Whether b0 spatial dimensions match the 4D DWI.
- Whether forward and inverse ANTs transforms exist.
- Whether optional FA and DWI-grid masks were generated.
- Low-resolution warning for through-plane resolution at or above 4 mm.

## Failure Handling

The batch is resumable. Existing outputs are reused unless `Force` is explicitly enabled.

A subject must be marked `registration_failed` and excluded from tracking if:

- required raw DWI sidecars are missing;
- bval/bvec entries do not match the number of DWI volumes;
- no b0 volume is detected;
- no anchorNative T1 can be resolved;
- ANTs registration fails;
- forward or inverse transform is missing after registration.

Low through-plane resolution is a QC warning, not an automatic exclusion.

## Pipeline Entry

The pipeline entry is:

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

## Limitations

No fieldmap or reverse phase-encoding correction is included in this primary batch because no valid fieldmap/reverse-PE DWI source was identified in the imported DWI set.

Several included DWI scans have low through-plane resolution. These cases can be staged and registered for exploratory analysis, but their tractography results must be interpreted with lower confidence and flagged in downstream reports.
