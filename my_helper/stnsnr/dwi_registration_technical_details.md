# STN/SNr DWI Registration Technical Details

Date: 2026-07-03

## Purpose

This document fixes the technical plan for importing, preprocessing, and
reviewing the STN/SNr cohort DWI scans in the existing Lead-DBS subject spaces.
The corrected DWI and corrected pseudo `B0` outputs are prerequisites for
patient-specific seed-target tracking, VTA/ROI projection into DWI space, and
native/MNI streamline display.

The current cohort refresh rewrites raw BIDS DWI files from
`/Volumes/VAL/STNSNrdwi`, removes stale DWI derivatives, runs Synb0-DISCO,
topup, and eddy, and then exposes the corrected mean b0 as a Lead-DBS pseudo
`B0` volume. The workflow intentionally stops before the Lead-DBS UI
`Coregister Volumes` step so the user can select SPM, ANTs, or another available
method after manual QC.

Neither the import/preprocessing stage nor the later UI coregistration stage
runs tractography, normative connectome analysis, or sweet/sour spot modeling.

Earlier automatic T2 registration branches are retained only as historical
comparators. The first completed T2 branch used Lead-DBS ANTs linear
registration under `coregistration/dwi_t2/`. Because manual QC still showed
large residual errors in some subjects, the method-comparison pilot added two
branches for three subjects only:

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

Included subjects are the 16 DWI four-file sets from
`summary/cohort/subj/subj_effect.xlsx`, imported in cohort order:

```text
LinJia
HuFengXian
YuDongJian
WuYueFen
LiPing
MaoXiaoMing
ShengGuoLiang
ZhangXiaoHong
ZhengXiangQuan
ZhaoPeiGen
ChenLingHua
FanDongDong
HuangDan
ZhangMing
GengHui
ChenMeiJu
```

## Registration Chain

The existing anatomical normalization is reused:

```text
anchorNative T1 -> MNI152NLin2009bAsym
```

For the current fake-B0 workflow, the automatic preprocessing stage does not
write a b0-to-anatomy transform. The corrected b0 is exposed as pseudo `B0` for
the Lead-DBS UI, where SPM is the usual first-choice coregistration method and
the final method is selected by manual QC. The fixed anatomical image remains
the already coregistered anchorNative anatomy selected by Lead-DBS.

The current DWI preprocessing chain is:

```text
raw BIDS DWI
  -> derivatives/leaddbs/sub-*/preprocessing/dwi
  -> distorted mean b0 extraction
  -> Synb0-DISCO synthetic undistorted b0
  -> FSL topup susceptibility field estimation
  -> FSL eddy correction with rotated bvecs
  -> corrected DWI and corrected mean b0
  -> pseudo B0 exposed to Lead-DBS UI
```

For projects stored on external volumes, the Docker-facing Synb0 staging
directory can be moved to a local user path with `Synb0WorkRoot`. This avoids
Docker Desktop mount translation failures on `/Volumes/...` while keeping the
archived Synb0 outputs, eddy outputs, corrected DWI, and pseudo `B0` in the
project derivatives.

Some SaveBySlc-reconstructed DWI datasets have odd in-plane dimensions such as
`108x105x78`. Synb0-DISCO can still generate the synthetic undistorted b0, but
its bundled topup configuration may fail because the default `--subsamp=2`
levels are incompatible with the odd matrix. In that case the wrapper reruns
only topup with a fallback configuration that sets all subsampling levels to
`1`, then continues to eddy with the fallback topup outputs.

During DWI import and preprocessing, the raw DWI files are copied from
`rawdata` into `preprocessing/dwi`, then Synb0-DISCO, topup, and eddy write
corrected outputs:

```text
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.nii
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.bval
preprocessing/dwi/sub-<Subject>_ses-preop_dwi.bvec
  -> preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_dwi.nii
  -> preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_dwi.bval
  -> preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_dwi.bvec
  -> preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_b0.nii
```

The import helper defines b0 volumes as `bval < 10`. The backward-compatible
default for multiple b0 volumes is their mean. Motion-sensitive workflows may
instead configure an explicit selection strategy such as `last`; the selected
source volume index and hash must be recorded in provenance. A selected raw
b0 must not be averaged with a visibly displaced b0 before Synb0 or motion
correction. Existing staged b0 files are overwritten during import/staging so
the b0 always matches the current staged DWI, sidecars, and configured b0
selection strategy.

When the selected b0 is intended to define the eddy reference and the bundled
eddy executable does not expose a reference-scan option, the DWI volumes,
b-values, and b-vectors are reordered together so the selected b0 is first.
The source-to-eddy volume mapping is mandatory provenance. A moved but
otherwise valid b0 can remain in the series for eddy correction; a corrupted
or slice-inconsistent b0 may be removed only after separate QC approval.

For the approved SNr017, SNr020, SNr022, and SNr026 reprocessing batch, the
reference strategy is `last`: the final volume satisfying the configured b0
threshold is moved to the first eddy input position. This policy controls the
Synb0 distorted-b0 input, the eddy reference ordering, and the formal
post-eddy b0. It does not hard-code a particular volume number, although the
current four series all resolve to source volume 2.

The reference-first ordering is an eddy implementation detail. After eddy,
the corrected DWI and rotated b-vectors are restored to source acquisition
order. The formal b-values remain in source order, and the formal corrected
b0 is extracted from the restored volume matching the selected source b0.

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

The approved, not-yet-implemented publication update is specified in
`my_helper/stnsnr/mrtrix_seed_target_space_aware_tractogram_plan.md`. It keeps
tracking in native DWI space and will publish parallel TCK trees under:

```text
tractograms/native/
tractograms/<target_space>/
```

`<target_space>` is read from the authoritative YAML as
`config.atlas.space`; it is not a fixed runtime directory name. The direct
approved B0-to-anchorNative matrix maps published native TCK coordinates into
anchorNative space. The production point backend then remains entirely in RAS
world millimetres: it uses the inverse full NIfTI affine to locate each
anchorNative point in the displacement grid, trilinearly samples the stored RAS
world-mm vector, and adds that vector directly to the RAS point. The deformation
named `from-<target_space>_to-anchorNative` is used because its image-resampling
direction is opposite to its direct point direction. The paired
`from-anchorNative_to-<target_space>` deformation supplies the reverse point
leg of round-trip QC. Both fields are accepted only with NIfTI displacement
intent `1006`, vector layout `(X, Y, Z, 1, 3)`, a finite invertible affine, and
the expected anchorNative or target-space grid. RAS-to-LPS conversion occurs
only in the independent `antsApplyTransformsToPoints` reference helper, never
in bulk production. This publication update must reuse valid native TCKs and
must not rerun tracking solely because their directory changes.

The previous direct b0-to-anchorNative T1 outputs under `coregistration/dwi/`
remain available only for comparison. Coregister UI B0 outputs under
`coregistration/anat/` and `coregistration/transformations/` are formal Lead-DBS
UI products after manual UI execution. The T2 registration pilot outputs remain
separate method-comparison branches for downstream tracking evaluation.

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

Expected corrected fake-B0 preprocessing files:

```text
sub-<Subject>_ses-preop_desc-preproc_dwi.nii
sub-<Subject>_ses-preop_desc-preproc_dwi.bval
sub-<Subject>_ses-preop_desc-preproc_dwi.bvec
sub-<Subject>_ses-preop_desc-preproc_b0.nii
sub-<Subject>_ses-preop_desc-preproc_b0.json
```

The corrected b0 JSON sidecar records:

```text
FakeCoregisterVolume=true
IntendedUse=coregistration_qc_only
ExcludeFromNormalization=true
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

The re-import/preprocessing batch is intentionally destructive only to the
target DWI products. Existing rawdata DWI files, subject `preprocessing/dwi`
contents, and pseudo `B0` coregistration files are moved to macOS Trash before
replacement. The source `/Volumes/VAL/STNSNrdwi` files are never modified.

The preprocessing batch uses `Force=true` after this cleanup so corrected DWI
and pseudo `B0` outputs are regenerated from the current rawdata.

A subject must be marked `registration_failed` for the branch being run if:

- required raw DWI sidecars are missing;
- bval/bvec entries do not match the number of DWI volumes;
- no b0 volume is detected;
- no anchorNative T2 can be resolved;
- the selected registration method fails;
- forward or inverse transform is missing after registration.

For the fake-B0 preprocessing branch, successful rows must be marked:

```text
status=pending_ui_coregistration
coregistration_status=pending_ui
```

The row must not be marked `registered` before manual Lead-DBS UI
coregistration.

Low through-plane resolution is a QC warning, not an automatic exclusion.

## Pipeline Entry

The 16-subject raw DWI re-import, cleanup, Synb0-DISCO, topup, eddy, and
fake-B0 preprocessing entry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_reimport_preprocess_fakeb0.m
```

Run command:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_reimport_preprocess_fakeb0.m')"
```

The previous 16-subject raw DWI re-import and staging-only entry is retained for
historical comparison:

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
