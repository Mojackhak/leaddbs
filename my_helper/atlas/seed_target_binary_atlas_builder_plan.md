# Seed-Target Binary Atlas Builder Plan

Date: 2026-07-03

## Purpose

This document defines a reusable binary atlas builder for seed-target tractography. The builder converts a declarative ROI specification into Lead-DBS atlas folders containing binary MNI-space masks, provenance manifests, and QC tables.

The connected-region atlas instances are:

- `STN-connected regions`
- `SNr-connected regions`
- `STNSNr-connected regions`

The builder code and ROI specifications live under:

`/Users/mojackhu/Github/leaddbs/my_helper/atlas`

Generated atlas outputs live under:

`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases`

## Core Rules

- One seed corresponds to one connected-regions atlas.
- Each connected-regions atlas must contain the seed nucleus itself.
- STN and SNr are generated from the original `Custom_Ewert_Zhang_Middlebrooks` continuous maps with an explicit `> 0.05` threshold.
- `Custom_Ewert_Zhang_Middlebrooks0.05` is not used as the direct source for generated masks.
- GPe and GPi are generated from `DISTAL (Ewert 2017)` with `> 0.25`.
- Julich-Brain v3.1 thalamic probabilistic maps use `>= 25%` for the primary analysis.
- HCPex is a discrete label atlas and uses exact label membership.
- PPN and Allen superior colliculus single-mask atlases use `> 0`.
- Similar thalamic subnuclei are not merged. VA, VLA, VLP, VM, MD, CM, Pf, and sPf remain separate endpoints.
- `union` is only used when one anatomical or functional concept is represented by multiple labels in the same source atlas.
- `STNSNr` is the side-specific union of the primary STN and SNr masks.
- `STNSNrplus` is `STNSNr` with 2 mm dilation on the MNI reference grid.

## Threshold Rationale

STN and SNr use `> 0.05` because local overlap checks showed zero STN/SNr overlap at this threshold and higher thresholds shrink SNr substantially. This preserves SNr coverage while keeping STN and SNr anatomically distinct.

GPe and GPi use `> 0.25` because local overlap checks on DISTAL showed that `> 0.25` nearly eliminates GPe/GPi overlap while preserving about 86% of the `> 0.05` volume. `> 0.05` and `> 0.5` are retained as sensitivity options.

Julich-Brain v3.1 uses `>= 25%` because those files are probabilistic cytoarchitectonic maps. The `25%` threshold is a conventional balanced threshold for probabilistic atlases, while `> 0%` and `>= 50%` are liberal and conservative sensitivity options.

## Specification Schema

Each atlas is described by a JSON spec with these top-level fields:

```json
{
  "atlas_name": "STN-connected regions",
  "space": "MNI152NLin2009bAsym",
  "reference_image": "templates/space/MNI152NLin2009bAsym/t1.nii",
  "output_dir": "templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions",
  "rois": []
}
```

Each ROI entry contains:

```json
{
  "name": "STN",
  "role": "seed",
  "category": "primary",
  "operation": "threshold",
  "threshold": 0.05,
  "threshold_operator": ">",
  "sides": {
    "L": {"source_file": ".../lh/STN.nii.gz"},
    "R": {"source_file": ".../rh/STN.nii.gz"}
  },
  "notes": "Primary STN seed."
}
```

Supported operations:

- `threshold`: threshold a continuous or probabilistic source image.
- `copy_binary`: binarize a source mask using `> 0`.
- `label_union`: extract one or more integer labels from a discrete parcellation.
- `posterior_split`: extract posterior half or posterior third of a source mask along MNI y.
- `union`: combine previously defined ROI masks for the same anatomical or functional concept.
- `dilate_mm`: dilate a source mask by a millimeter radius on the reference grid.
- `probability_sum_threshold`: align cropped probability images on their shared
  voxel lattice, add their original values, and threshold the sum. Different
  voxel bases or non-integer offsets are errors; no probability interpolation,
  normalization, or threshold-before-sum is performed.
- `intersect`: reserved for future composite ROIs.
- `subtract`: reserved for future composite ROIs.

## STN-Connected Regions

Output directory:

`templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions`

| ROI | Role | Source | Operation |
|---|---|---|---|
| `STN` | seed | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/STN.nii.gz` | `> 0.05` |
| `SNr` | target | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/SNr.nii.gz` | `> 0.05` |
| `M1` | target | HCPex `Primary_Motor_Cortex` | exact label membership |
| `SMA` | target | HCPex `Area_6m_anterior`, `Area_6mp`, `Supplementary_and_Cingulate_Eye_Field` | same-concept union |
| `preSMA` | target | HCPex `Area_6m_anterior`, `Area_6mp` | same-concept union |
| `premotor` | target | HCPex `Area_6_anterior`, `Rostral_Area_6`, `Ventral_Area_6`, `Premotor_Eye_Field` | same-concept union |
| `GPe` | target | `DISTAL (Ewert 2017)/{lh,rh}/GPe.nii.gz` | `> 0.25` |
| `GPi` | target | `DISTAL (Ewert 2017)/{lh,rh}/GPi.nii.gz` | `> 0.25` |
| `DLPFC` | target | HCPex Area 46, Area 9, and Area 8 labels | same-concept union |
| `ACC` | target | HCPex cingulate labels | same-concept union |
| `OFC` | target | HCPex OFC labels | same-concept union |
| `vmPFC` | target | HCPex medial/orbital prefrontal labels | same-concept union |

Sensitivity masks:

- STN/SNr: `thr025`, `thr05`
- GPe/GPi: `thr005`, `thr05`

## SNr-Connected Regions

Output directory:

`templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions`

| ROI | Role | Source | Operation |
|---|---|---|---|
| `SNr` | seed | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/SNr.nii.gz` | `> 0.05` |
| `STN` | target | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/STN.nii.gz` | `> 0.05` |
| `VA_thalamus` | target | Julich v3.1 `Thalamus-VA` | `>= 25%` |
| `VLA_thalamus` | target | Julich v3.1 `Thalamus-VLA` | `>= 25%` |
| `VLP_thalamus` | target | Julich v3.1 `Thalamus-VLP` | `>= 25%` |
| `VM_thalamus` | target | Julich v3.1 `Thalamus-VM` | `>= 25%` |
| `posterior_putamen` | target | HCPex Putamen | posterior MNI-y half |
| `caudate` | target | HCPex Caudate | exact label membership |
| `PPN` | target | `PPN_Atlas (Alho 2017)/{lh,rh}/PPN.nii.gz` | `> 0` |
| `superior_colliculus` | target | Allen `SC.nii.gz` | `> 0` |
| `MD_thalamus` | target | Julich v3.1 `Thalamus-MD` | `>= 25%` |
| `CM_thalamus` | target | Julich v3.1 `Thalamus-CM` | `>= 25%` |
| `Pf_thalamus` | target | Julich v3.1 `Thalamus-Pf` | `>= 25%` |
| `sPf_thalamus` | target | Julich v3.1 `Thalamus-sPf` | `>= 25%` |
| `FEF` | target | HCPex `Frontal_Eye_Fields` | exact label membership |
| `SMA` | target | HCPex SMA-related labels | same-concept union |
| `preSMA` | target | HCPex pre-SMA-related labels | same-concept union |
| `premotor` | target | HCPex premotor labels | same-concept union |
| `M1` | target | HCPex `Primary_Motor_Cortex` | exact label membership |
| `DLPFC` | target | HCPex Area 46, Area 9, and Area 8 labels | same-concept union |

Sensitivity masks:

- STN/SNr: `thr025`, `thr05`
- Julich nuclei: `thr0`, `thr50`
- posterior putamen: posterior third
- PPN: Snijders 2016

## STNSNr-Connected Regions

Output directory:

`templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions`

This atlas merges `STN-connected regions` and `SNr-connected regions` by ROI name. Identical ROI definitions are stored once. When the same ROI has different historical category labels, the merged atlas keeps the more primary category.

| ROI | Role | Source | Operation |
|---|---|---|---|
| `STNSNr` | seed | thresholded STN and SNr from `Custom_Ewert_Zhang_Middlebrooks` | same-side union |
| `STNSNrplus` | seed_margin | `STNSNr` | 2 mm dilation |
| `STN` | component | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/STN.nii.gz` | `> 0.05` |
| `SNr` | component | `Custom_Ewert_Zhang_Middlebrooks/{lh,rh}/SNr.nii.gz` | `> 0.05` |

The remaining endpoint and sensitivity ROIs are the deduplicated union of the STN and SNr connected-region specs. The expected atlas contains 53 ROI names and 106 side-specific manifest/QC records.

## STNVOplus Atlas

The approved `STNVOplus (Ewert 2017)` atlas contains only bilateral
`STNplus.nii.gz` and `VOplus.nii.gz`. Its inputs are the STN, Voa, and Vop
probability images in `DISTAL STN_Vop_main (Ewert 2017)`.

- STNplus: threshold STN at the absolute value `>= 0.05`, resample the binary
  mask with nearest-neighbor interpolation to `MNI152NLin2009bAsym/t1.nii`,
  then dilate by a Euclidean voxel-center distance of `<= 2 mm`.
- VOplus: align Voa and Vop on their common 0.25 mm lattice, zero-pad their
  different crop extents, add the original probability values, and apply
  `>= 0.05`. Resample that binary mask to the same reference and dilate by
  `<= 2 mm`. In particular, `0.03 + 0.03` passes the threshold.
- The reference grid is 0.5 mm isotropic. Final uint8 binary masks retain its
  shape, affine, qform, and sform. Dilation takes place on the reference grid,
  not within the cropped source image.
- The selected source Voa has already been restricted to its largest component
  at approximately 0.5 probability. Its removed low-probability voxels are not
  restored or replaced from another atlas.
- Preserve STNplus/VOplus overlap. Do not smooth, fill holes, select further
  components, clip to gray matter, or construct an exclusive label image.
- Record source paths, thresholds, operation order, volume, side, and overlap.
  Do not copy the source atlas index or gray-matter cache.
- Build only a new destination. Existing atlas directories must not be
  overwritten; source images, subject data, and tracking settings stay intact.

Focused validation covers sum-before-threshold, crop alignment and extent,
inclusive thresholding, physical-radius dilation, reference geometry, binary
values, and actual four-mask overlap. Inspect three-plane T1 overlays.
This adds no cache or invalidation mechanism: the new specification only builds
this atlas when explicitly requested, and unrelated atlas outputs are unchanged.

## Outputs

Each generated atlas writes:

```text
README.md
roi_manifest.csv
roi_manifest.json
roi_qc.csv
lh/*.nii.gz
rh/*.nii.gz
```

`roi_manifest` records ROI provenance, source files, operation, threshold, labels, output files, and notes.

`roi_qc` records voxel count, volume, centroid, reference-grid match, side consistency, and empty-mask status.

Generated binary mask headers use unit scaling and zero offset so downstream MRtrix thresholding interprets stored zeros and ones directly.

## Fiber Tracking Use

Seed-target tractography should use these generated binary masks as the ROI source. The tracking pipeline should not parse raw Custom, DISTAL, Julich, HCPex, PPN, or Allen sources directly.

## Acceptance Checks

- All source files exist.
- All connected-region specs build successfully.
- All primary masks are non-empty.
- All output masks match the MNI reference grid.
- Left-sided centroids are left of midline and right-sided centroids are right of midline.
- `STNSNr` equals the side-specific `STN | SNr` union.
- `STNSNrplus` contains every `STNSNr` voxel and has larger volume after 2 mm dilation.
- STN/SNr overlap is computed and reported at `> 0.05`. The current generated 0.5 mm reference-grid atlas has non-zero overlap after resampling: 500 voxels left and 586 voxels right, equal to 62.5 mm3 and 73.25 mm3. This is not automatically subtracted because subtraction would change the explicitly defined source ROIs.
- GPe/GPi overlap is near-zero at `> 0.25`. The current generated 0.5 mm reference-grid STN atlas has 4 voxels left and 19 voxels right, equal to 0.5 mm3 and 2.375 mm3.
- Every ROI has complete manifest provenance.

## Current Build Notes

- `VM_thalamus_thr50` is empty for both left and right sides. This is expected for the conservative Julich 50% sensitivity threshold and does not affect the primary `VM_thalamus` mask at `>= 25%`.
- Generated atlas NIfTI files are stored under the Lead-DBS `templates/.../atlases` tree, which is ignored by Git in this repository. The reproducible source of truth is the builder code, JSON specs, and generated `roi_manifest` files in each atlas output folder.
